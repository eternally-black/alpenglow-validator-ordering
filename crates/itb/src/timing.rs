//! Time bases and the slot clock.
//!
//! `RunClock` converts the monotonic clock into Unix nanoseconds anchored once per run, so timestamps in our logs
//! never jump when the wall clock is adjusted.
//!
//! `SlotClock` follows slot progress through an RPC WebSocket (`slotsUpdatesSubscribe`, falling back to
//! `slotSubscribe`) and records when *we observed* each slot first. Observation lags the leader by shred
//! propagation and RPC processing, so predictions are in the observer's frame; the pilot calibrates the offset, and
//! every window is classified post hoc by achieved offset (PLAN §2.5).

use anyhow::{Context, Result, anyhow};
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::watch;
use tokio_tungstenite::tungstenite::Message;

#[derive(Clone, Copy, Debug)]
pub struct RunClock {
    start: Instant,
    start_unix_ns: i64,
}

impl RunClock {
    pub fn new() -> Self {
        let start_unix_ns = SystemTime::now().duration_since(UNIX_EPOCH).expect("clock after 1970").as_nanos() as i64;
        Self { start: Instant::now(), start_unix_ns }
    }

    pub fn now_unix_ns(&self) -> i64 {
        self.instant_to_unix_ns(Instant::now())
    }

    pub fn instant_to_unix_ns(&self, t: Instant) -> i64 {
        if t >= self.start {
            self.start_unix_ns + t.duration_since(self.start).as_nanos() as i64
        } else {
            self.start_unix_ns - self.start.duration_since(t).as_nanos() as i64
        }
    }

    pub fn unix_ns_to_instant(&self, unix_ns: i64) -> Instant {
        let delta = unix_ns - self.start_unix_ns;
        if delta >= 0 {
            self.start + Duration::from_nanos(delta as u64)
        } else {
            self.start - Duration::from_nanos((-delta) as u64)
        }
    }
}

impl Default for RunClock {
    fn default() -> Self {
        Self::new()
    }
}

/// One slot-progress notification as received.
#[derive(Debug, Clone, Serialize)]
pub struct SlotEvent {
    pub slot: u64,
    pub kind: String,
    pub recv_unix_ns: i64,
    /// Server-side timestamp (ms) when the RPC provides one (`slotsUpdatesSubscribe`).
    pub server_ms: Option<u64>,
}

#[derive(Default)]
struct State {
    first_seen: BTreeMap<u64, i64>,
    events: Vec<SlotEvent>,
}

#[derive(Clone)]
pub struct SlotClock {
    state: Arc<Mutex<State>>,
    latest: watch::Receiver<u64>,
    clock: RunClock,
    nominal_slot_ms: f64,
}

impl SlotClock {
    /// Connects and starts following slots in a background task (reconnecting on errors). Returns once the first
    /// notification has arrived.
    pub async fn start(ws_url: &str, clock: RunClock, nominal_slot_ms: f64) -> Result<Self> {
        let (tx, rx) = watch::channel(0u64);
        let state = Arc::new(Mutex::new(State::default()));
        let url = ws_url.to_string();
        let st = state.clone();
        tokio::spawn(async move {
            let mut backoff = Duration::from_millis(500);
            loop {
                if let Err(e) = follow(&url, &st, &tx, clock).await {
                    tracing::warn!(error = %e, "slot stream dropped; reconnecting");
                }
                tokio::time::sleep(backoff).await;
                backoff = (backoff * 2).min(Duration::from_secs(10));
            }
        });
        let mut rx2 = rx.clone();
        tokio::time::timeout(Duration::from_secs(20), rx2.wait_for(|s| *s > 0))
            .await
            .map_err(|_| anyhow!("no slot notification within 20 s from {ws_url}"))?
            .map_err(|_| anyhow!("slot stream task ended"))?;
        Ok(Self { state, latest: rx, clock, nominal_slot_ms })
    }

    pub fn latest_slot(&self) -> u64 {
        *self.latest.borrow()
    }

    pub fn first_seen_unix_ns(&self, slot: u64) -> Option<i64> {
        self.state.lock().expect("slot state").first_seen.get(&slot).copied()
    }

    /// Median spacing of first observations over the last 64 consecutive slots, clamped to a sane range.
    pub fn slot_ms_estimate(&self) -> f64 {
        let st = self.state.lock().expect("slot state");
        let pts: Vec<(u64, i64)> = st.first_seen.iter().rev().take(65).map(|(s, t)| (*s, *t)).collect();
        let mut diffs: Vec<f64> = pts
            .windows(2)
            .filter(|w| w[0].0 == w[1].0 + 1)
            .map(|w| (w[0].1 - w[1].1) as f64 / 1e6)
            .collect();
        if diffs.len() < 8 {
            return self.nominal_slot_ms;
        }
        diffs.sort_by(|a, b| a.total_cmp(b));
        diffs[diffs.len() / 2].clamp(self.nominal_slot_ms * 0.7, self.nominal_slot_ms * 1.5)
    }

    /// Predicted first-observation time of `slot`, extrapolated from the most recent observation.
    pub fn predict_unix_ns(&self, slot: u64) -> Option<i64> {
        let ms = self.slot_ms_estimate();
        let st = self.state.lock().expect("slot state");
        let (&s0, &t0) = st.first_seen.iter().next_back()?;
        Some(t0 + ((slot as i64 - s0 as i64) as f64 * ms * 1e6) as i64)
    }

    pub fn predict_instant(&self, slot: u64) -> Option<Instant> {
        self.predict_unix_ns(slot).map(|ns| self.clock.unix_ns_to_instant(ns))
    }

    pub async fn wait_for_slot(&self, slot: u64) -> Result<()> {
        let mut rx = self.latest.clone();
        rx.wait_for(|s| *s >= slot).await.map_err(|_| anyhow!("slot stream ended"))?;
        Ok(())
    }

    /// Drains recorded events (for the raw log).
    pub fn take_events(&self) -> Vec<SlotEvent> {
        std::mem::take(&mut self.state.lock().expect("slot state").events)
    }
}

async fn follow(url: &str, state: &Arc<Mutex<State>>, tx: &watch::Sender<u64>, clock: RunClock) -> Result<()> {
    let (mut ws, _) = tokio_tungstenite::connect_async(url).await.with_context(|| format!("websocket {url}"))?;
    ws.send(Message::text(json!({"jsonrpc": "2.0", "id": 1, "method": "slotsUpdatesSubscribe"}).to_string())).await?;
    let mut fallback_sent = false;
    while let Some(msg) = ws.next().await {
        let msg = msg?;
        let text = match msg {
            Message::Text(t) => t.to_string(),
            Message::Ping(p) => {
                ws.send(Message::Pong(p)).await?;
                continue;
            }
            Message::Close(_) => break,
            _ => continue,
        };
        let recv = clock.now_unix_ns();
        let v: Value = serde_json::from_str(&text)?;
        if v.get("error").is_some() && !fallback_sent {
            // Provider without slotsUpdatesSubscribe: fall back to plain slot notifications.
            ws.send(Message::text(json!({"jsonrpc": "2.0", "id": 2, "method": "slotSubscribe"}).to_string())).await?;
            fallback_sent = true;
            continue;
        }
        let (slot, kind, server_ms) = match v.get("method").and_then(Value::as_str) {
            Some("slotsUpdatesNotification") => {
                let r = &v["params"]["result"];
                (r["slot"].as_u64(), r["type"].as_str().unwrap_or("?").to_string(), r["timestamp"].as_u64())
            }
            Some("slotNotification") => (v["params"]["result"]["slot"].as_u64(), "slotNotification".to_string(), None),
            _ => continue,
        };
        let Some(slot) = slot else { continue };
        let mut st = state.lock().expect("slot state");
        st.first_seen.entry(slot).or_insert(recv);
        st.events.push(SlotEvent { slot, kind, recv_unix_ns: recv, server_ms });
        while st.first_seen.len() > 4096 {
            st.first_seen.pop_first();
        }
        drop(st);
        tx.send_if_modified(|cur| {
            if slot > *cur {
                *cur = slot;
                true
            } else {
                false
            }
        });
    }
    Err(anyhow!("websocket closed"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_clock_roundtrip() {
        let c = RunClock::new();
        let now = Instant::now();
        let ns = c.instant_to_unix_ns(now);
        let back = c.unix_ns_to_instant(ns);
        let diff = if back > now { back - now } else { now - back };
        assert!(diff < Duration::from_micros(2));
        let past = c.start - Duration::from_millis(5);
        assert_eq!(c.instant_to_unix_ns(past), c.start_unix_ns - 5_000_000);
    }
}
