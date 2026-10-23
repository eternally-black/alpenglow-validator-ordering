//! Thin QUIC sender to a leader's (or builder's) advertised `tpuQuic` address.
//!
//! The TLS/transport setup mirrors agave v4.3.2 `tpu-client-next/src/quic_networking.rs` (ALPN `solana-tpu`,
//! self-signed ed25519 client certificate, 10 s idle timeout, 1 s keep-alive, CUBIC with a 128-packet initial window),
//! so the server treats us exactly like any unstaked agave client. Unlike `tpu-client-next` we schedule every stream
//! ourselves and timestamp it, because send order and send time are experimental variables here.
//!
//! Server-side limits we stay under (agave `streamer/src/quic.rs`): 8 connections per unstaked peer, 8 *new*
//! connections per IP per minute (excess silently ignored), 20 streams per 100 ms per unstaked connection.

use crate::auth::LiveAuthorization;
use crate::timing::RunClock;
use anyhow::{Context, Result, anyhow};
use quinn::congestion::CubicConfig;
use quinn::crypto::rustls::QuicClientConfig;
use quinn::{ClientConfig, Connection, Endpoint, IdleTimeout, TransportConfig};
use serde::Serialize;
use solana_tls_utils::{QuicClientCertificate, tls_client_config_builder};
use std::collections::{HashMap, VecDeque};
use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub const ALPN_TPU_PROTOCOL_ID: &[u8] = b"solana-tpu";
const QUIC_MAX_TIMEOUT: Duration = Duration::from_secs(10);
const QUIC_KEEP_ALIVE: Duration = Duration::from_secs(1);
const PACKET_DATA_SIZE: u64 = 1232;
const INITIAL_CONGESTION_WINDOW: u64 = 128 * PACKET_DATA_SIZE;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(5);
/// Half of the server's 8/min per-IP allowance, so retries and shared builder IPs never trip it.
pub const MAX_NEW_CONNECTIONS_PER_IP_PER_MINUTE: usize = 4;
/// Stay below the 20-streams-per-100-ms unstaked throttle with margin.
pub const MAX_STREAMS_PER_BURST: usize = 14;

#[derive(Debug, Clone, Serialize)]
pub struct ConnectReport {
    pub addr: String,
    pub reused: bool,
    pub handshake_us: Option<u64>,
    pub error: Option<String>,
    pub at_unix_ns: i64,
}

/// One transaction to put on its own uni-stream at (or right after) `at`.
pub struct Outgoing {
    pub probe_id: String,
    pub wire: Vec<u8>,
    pub at: tokio::time::Instant,
}

/// Locally observable facts about one send. Arrival at the server is *not* observable and is not recorded here.
#[derive(Debug, Clone, Serialize)]
pub struct StreamRecord {
    pub probe_id: String,
    pub addr: String,
    pub scheduled_unix_ns: i64,
    pub open_unix_ns: Option<i64>,
    pub written_unix_ns: Option<i64>,
    pub finished_unix_ns: Option<i64>,
    pub stream_index_in_burst: usize,
    pub error: Option<String>,
}

pub struct QuicClient {
    endpoint: Endpoint,
    conns: tokio::sync::Mutex<HashMap<SocketAddr, Connection>>,
    new_conn_log: Mutex<HashMap<IpAddr, VecDeque<std::time::Instant>>>,
    clock: RunClock,
}

impl QuicClient {
    pub fn new(clock: RunClock) -> Result<Self> {
        let cert = QuicClientCertificate::new(None);
        let mut crypto = tls_client_config_builder()
            .with_client_auth_cert(vec![cert.certificate.clone()], cert.key.clone_key())
            .context("client certificate")?;
        crypto.enable_early_data = true;
        crypto.alpn_protocols = vec![ALPN_TPU_PROTOCOL_ID.to_vec()];

        let mut transport = TransportConfig::default();
        transport.max_idle_timeout(Some(IdleTimeout::try_from(QUIC_MAX_TIMEOUT)?));
        transport.keep_alive_interval(Some(QUIC_KEEP_ALIVE));
        transport.datagram_receive_buffer_size(None);
        transport.send_fairness(false); // streams leave in the order we open them
        let mut cubic = CubicConfig::default();
        cubic.initial_window(INITIAL_CONGESTION_WINDOW);
        transport.congestion_controller_factory(Arc::new(cubic));

        let mut config = ClientConfig::new(Arc::new(QuicClientConfig::try_from(crypto)?));
        config.transport_config(Arc::new(transport));
        let mut endpoint = Endpoint::client("0.0.0.0:0".parse().expect("bind addr")).context("binding QUIC endpoint")?;
        endpoint.set_default_client_config(config);
        Ok(Self { endpoint, conns: Default::default(), new_conn_log: Default::default(), clock })
    }

    fn allow_new_connection(&self, ip: IpAddr) -> bool {
        let mut log = self.new_conn_log.lock().expect("limiter mutex");
        let q = log.entry(ip).or_default();
        let now = std::time::Instant::now();
        while q.front().is_some_and(|t| now.duration_since(*t) > Duration::from_secs(60)) {
            q.pop_front();
        }
        if q.len() >= MAX_NEW_CONNECTIONS_PER_IP_PER_MINUTE {
            return false;
        }
        q.push_back(now);
        true
    }

    /// Opens (or reuses) the connection to `addr`. Performing the handshake sends no transaction bytes, so the dry run
    /// may call this to measure reachability and handshake RTT.
    pub async fn connect(&self, addr: SocketAddr) -> ConnectReport {
        let at_unix_ns = self.clock.now_unix_ns();
        let mut conns = self.conns.lock().await;
        if let Some(c) = conns.get(&addr) {
            if c.close_reason().is_none() {
                return ConnectReport { addr: addr.to_string(), reused: true, handshake_us: None, error: None, at_unix_ns };
            }
            conns.remove(&addr);
        }
        if !self.allow_new_connection(addr.ip()) {
            return ConnectReport {
                addr: addr.to_string(),
                reused: false,
                handshake_us: None,
                error: Some("local limiter: too many new connections to this IP in the last minute".into()),
                at_unix_ns,
            };
        }
        let started = std::time::Instant::now();
        let result = async {
            let connecting = self.endpoint.connect(addr, "connect").map_err(|e| anyhow!("connect: {e}"))?;
            tokio::time::timeout(HANDSHAKE_TIMEOUT, connecting)
                .await
                .map_err(|_| anyhow!("handshake timed out after {HANDSHAKE_TIMEOUT:?}"))?
                .map_err(|e| anyhow!("handshake: {e}"))
        }
        .await;
        match result {
            Ok(conn) => {
                let handshake_us = started.elapsed().as_micros() as u64;
                conns.insert(addr, conn);
                ConnectReport { addr: addr.to_string(), reused: false, handshake_us: Some(handshake_us), error: None, at_unix_ns }
            }
            Err(e) => ConnectReport { addr: addr.to_string(), reused: false, handshake_us: None, error: Some(e.to_string()), at_unix_ns },
        }
    }

    /// Sends each transaction on its own uni-stream at its scheduled instant, in schedule order. Items sharing an
    /// instant go out back-to-back on the same connection. No retries: a failed stream is recorded, not resent.
    pub async fn send_scheduled(&self, _auth: &LiveAuthorization, addr: SocketAddr, mut items: Vec<Outgoing>) -> Vec<StreamRecord> {
        items.sort_by_key(|o| o.at);
        let conn = self.conns.lock().await.get(&addr).cloned();
        let mut out = Vec::with_capacity(items.len());
        for (i, o) in items.into_iter().enumerate() {
            tokio::time::sleep_until(o.at).await;
            let mut rec = StreamRecord {
                probe_id: o.probe_id,
                addr: addr.to_string(),
                scheduled_unix_ns: self.clock.instant_to_unix_ns(o.at.into_std()),
                open_unix_ns: None,
                written_unix_ns: None,
                finished_unix_ns: None,
                stream_index_in_burst: i,
                error: None,
            };
            let Some(conn) = conn.as_ref() else {
                rec.error = Some("no open connection".into());
                out.push(rec);
                continue;
            };
            match conn.open_uni().await {
                Ok(mut s) => {
                    rec.open_unix_ns = Some(self.clock.now_unix_ns());
                    match s.write_all(&o.wire).await {
                        Ok(()) => {
                            rec.written_unix_ns = Some(self.clock.now_unix_ns());
                            match s.finish() {
                                Ok(()) => rec.finished_unix_ns = Some(self.clock.now_unix_ns()),
                                Err(e) => rec.error = Some(format!("finish: {e}")),
                            }
                        }
                        Err(e) => rec.error = Some(format!("write: {e}")),
                    }
                }
                Err(e) => rec.error = Some(format!("open_uni: {e}")),
            }
            out.push(rec);
        }
        out
    }

    pub async fn close_all(&self) {
        for (_, c) in self.conns.lock().await.drain() {
            c.close(0u32.into(), b"done");
        }
        self.endpoint.wait_idle().await;
    }
}
