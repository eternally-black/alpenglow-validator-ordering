//! Thin QUIC sender to a leader's (or builder's) advertised `tpuQuic` address.
//!
//! The TLS/transport setup mirrors agave v4.3.2 `tpu-client-next/src/quic_networking.rs` (ALPN `solana-tpu`,
//! self-signed ed25519 client certificate, 10 s idle timeout, 1 s keep-alive, CUBIC with a 128-packet initial window),
//! so the server treats us exactly like any unstaked agave client. Unlike `tpu-client-next` we schedule every stream
//! ourselves and timestamp it, because send order and send time are experimental variables here.
//!
//! Server-side limits we stay under (agave `streamer/src/quic.rs`): 8 connections per unstaked peer, 8 *new*
//! connections per IP per minute (excess silently ignored), 20 streams per 100 ms per unstaked connection (excess
//! delayed). Our own limits are enforced at runtime, per connection and across all callers: ≤ 4 new connections per
//! IP per minute and ≤ 14 streams per rolling 100 ms. Every item carries a deadline: if it cannot be put on the wire in
//! time, its stream is never opened and the record says so (the transaction provably did not leave this process).

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
use std::time::{Duration, Instant};

pub const ALPN_TPU_PROTOCOL_ID: &[u8] = b"solana-tpu";
const QUIC_MAX_TIMEOUT: Duration = Duration::from_secs(10);
const QUIC_KEEP_ALIVE: Duration = Duration::from_secs(1);
const PACKET_DATA_SIZE: u64 = 1232;
const INITIAL_CONGESTION_WINDOW: u64 = 128 * PACKET_DATA_SIZE;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(5);
const STREAM_TIMEOUT: Duration = Duration::from_millis(500);
/// Half of the server's 8/min per-IP allowance, so retries and shared builder IPs never trip it.
pub const MAX_NEW_CONNECTIONS_PER_IP_PER_MINUTE: usize = 4;
/// Below the 20-streams-per-100-ms unstaked throttle with margin; enforced per connection at runtime.
pub const MAX_STREAMS_PER_100MS: usize = 14;
const STREAM_WINDOW: Duration = Duration::from_millis(100);

#[derive(Debug, Clone, Serialize)]
pub struct ConnectReport {
    pub addr: String,
    pub reused: bool,
    pub handshake_us: Option<u64>,
    pub error: Option<String>,
    pub at_unix_ns: i64,
}

/// One transaction to put on its own uni-stream at (or right after) `at`, and never after `deadline`.
pub struct Outgoing {
    pub probe_id: String,
    pub wire: Vec<u8>,
    pub at: tokio::time::Instant,
    pub deadline: tokio::time::Instant,
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
    /// Time spent waiting for our own per-connection stream budget.
    pub limiter_delay_us: u64,
    /// True when no stream was opened: the transaction provably did not leave this process.
    pub never_opened: bool,
    pub error: Option<String>,
}

struct ConnState {
    conn: Connection,
    /// Stream-open instants within the last 100 ms (shared by every caller using this connection).
    recent_streams: VecDeque<Instant>,
}

pub struct QuicClient {
    endpoint: Endpoint,
    conns: tokio::sync::Mutex<HashMap<SocketAddr, Arc<tokio::sync::Mutex<ConnState>>>>,
    new_conn_log: Mutex<HashMap<IpAddr, VecDeque<Instant>>>,
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
        let mut endpoint = Endpoint::client("0.0.0.0:0".parse().expect("bind addr"))
            .context("binding QUIC endpoint")?;
        endpoint.set_default_client_config(config);
        Ok(Self {
            endpoint,
            conns: Default::default(),
            new_conn_log: Default::default(),
            clock,
        })
    }

    fn allow_new_connection(&self, ip: IpAddr) -> bool {
        let mut log = self.new_conn_log.lock().expect("limiter mutex");
        let q = log.entry(ip).or_default();
        let now = Instant::now();
        while q
            .front()
            .is_some_and(|t| now.duration_since(*t) > Duration::from_secs(60))
        {
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
            if c.lock().await.conn.close_reason().is_none() {
                return ConnectReport {
                    addr: addr.to_string(),
                    reused: true,
                    handshake_us: None,
                    error: None,
                    at_unix_ns,
                };
            }
            conns.remove(&addr);
        }
        if !self.allow_new_connection(addr.ip()) {
            return ConnectReport {
                addr: addr.to_string(),
                reused: false,
                handshake_us: None,
                error: Some(
                    "local limiter: too many new connections to this IP in the last minute".into(),
                ),
                at_unix_ns,
            };
        }
        let started = Instant::now();
        let result = async {
            let connecting = self
                .endpoint
                .connect(addr, "connect")
                .map_err(|e| anyhow!("connect: {e}"))?;
            tokio::time::timeout(HANDSHAKE_TIMEOUT, connecting)
                .await
                .map_err(|_| anyhow!("handshake timed out after {HANDSHAKE_TIMEOUT:?}"))?
                .map_err(|e| anyhow!("handshake: {e}"))
        }
        .await;
        match result {
            Ok(conn) => {
                let handshake_us = started.elapsed().as_micros() as u64;
                conns.insert(
                    addr,
                    Arc::new(tokio::sync::Mutex::new(ConnState {
                        conn,
                        recent_streams: VecDeque::new(),
                    })),
                );
                ConnectReport {
                    addr: addr.to_string(),
                    reused: false,
                    handshake_us: Some(handshake_us),
                    error: None,
                    at_unix_ns,
                }
            }
            Err(e) => ConnectReport {
                addr: addr.to_string(),
                reused: false,
                handshake_us: None,
                error: Some(e.to_string()),
                at_unix_ns,
            },
        }
    }

    /// Sends each transaction on its own uni-stream at its scheduled instant, in schedule order. Items sharing an
    /// instant go out back-to-back on the same connection. The connection is held for the whole call, so concurrent
    /// callers to one endpoint queue behind each other and share one stream budget. No retries.
    pub async fn send_scheduled(
        &self,
        _auth: &LiveAuthorization,
        addr: SocketAddr,
        mut items: Vec<Outgoing>,
    ) -> Vec<StreamRecord> {
        items.sort_by_key(|o| o.at);
        let state = self.conns.lock().await.get(&addr).cloned();
        let mut out = Vec::with_capacity(items.len());
        let mut guard = match &state {
            Some(s) => Some(s.lock().await),
            None => None,
        };
        for (i, o) in items.into_iter().enumerate() {
            let mut rec = StreamRecord {
                probe_id: o.probe_id,
                addr: addr.to_string(),
                scheduled_unix_ns: self.clock.instant_to_unix_ns(o.at.into_std()),
                open_unix_ns: None,
                written_unix_ns: None,
                finished_unix_ns: None,
                stream_index_in_burst: i,
                limiter_delay_us: 0,
                never_opened: true,
                error: None,
            };
            let Some(st) = guard.as_deref_mut() else {
                rec.error = Some("no open connection".into());
                out.push(rec);
                continue;
            };
            tokio::time::sleep_until(o.at).await;
            // Our own stream budget: wait for room in the rolling 100 ms window.
            let wait_start = Instant::now();
            loop {
                let now = Instant::now();
                while st
                    .recent_streams
                    .front()
                    .is_some_and(|t| now.duration_since(*t) >= STREAM_WINDOW)
                {
                    st.recent_streams.pop_front();
                }
                if st.recent_streams.len() < MAX_STREAMS_PER_100MS {
                    break;
                }
                let oldest = *st.recent_streams.front().expect("non-empty");
                tokio::time::sleep(STREAM_WINDOW.saturating_sub(now.duration_since(oldest))).await;
            }
            rec.limiter_delay_us = wait_start.elapsed().as_micros() as u64;
            if tokio::time::Instant::now() > o.deadline {
                rec.error = Some("deadline passed before the stream could be opened".into());
                out.push(rec);
                continue;
            }
            st.recent_streams.push_back(Instant::now());
            match tokio::time::timeout(STREAM_TIMEOUT, st.conn.open_uni()).await {
                Ok(Ok(mut s)) => {
                    rec.never_opened = false;
                    rec.open_unix_ns = Some(self.clock.now_unix_ns());
                    match tokio::time::timeout(STREAM_TIMEOUT, s.write_all(&o.wire)).await {
                        Ok(Ok(())) => {
                            rec.written_unix_ns = Some(self.clock.now_unix_ns());
                            match s.finish() {
                                Ok(()) => rec.finished_unix_ns = Some(self.clock.now_unix_ns()),
                                Err(e) => rec.error = Some(format!("finish: {e}")),
                            }
                        }
                        Ok(Err(e)) => rec.error = Some(format!("write: {e}")),
                        Err(_) => rec.error = Some("write timed out".into()),
                    }
                }
                Ok(Err(e)) => rec.error = Some(format!("open_uni: {e}")),
                // A timed-out open never returned a stream: nothing was written.
                Err(_) => rec.error = Some("open_uni timed out".into()),
            }
            out.push(rec);
        }
        drop(guard);
        out
    }

    pub async fn close_all(&self) {
        for (_, c) in self.conns.lock().await.drain() {
            c.lock().await.conn.close(0u32.into(), b"done");
        }
        self.endpoint.wait_idle().await;
    }
}
