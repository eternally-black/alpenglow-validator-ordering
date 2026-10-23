//! Time bases and the slot clock.
//!
//! `RunClock` converts the monotonic clock into Unix nanoseconds anchored once per run, so timestamps in our logs
//! never jump when the wall clock is adjusted.
//!
//! `SlotClock` follows slot progress through an RPC WebSocket (`slotsUpdatesSubscribe`, falling back to
//! `slotSubscribe`) and records when *we observed* each slot's first shred. Observation lags the leader by shred
//! propagation and RPC processing, so everything here is in the observer's frame.
//!
//! Mainnet cadence is not uniform (dry-run, 2026-10-23): first shreds of slots inside a leader window arrive every
//! ≈130 ms, while the hand-over into a new leader's window takes ≈560 ms (≈235 ms per slot on average, not 200).
//! Sends are therefore anchored on observed events where possible (the previous leader's last slot for the buffered
//! regime, the target's first slot for streaming) and extrapolated with the split cadence only for far-ahead sends.

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
    /// First time we saw each slot's first shred (or its slot notification, if the provider lacks slot updates).
    first_shred: BTreeMap<u64, i64>,
    events: Vec<SlotEvent>,
}

/// Leader windows are 4 slots aligned to multiples of 4 (`NUM_CONSECUTIVE_LEADER_SLOTS`).
pub const SLOTS_PER_WINDOW: u64 = 4;

pub fn is_window_start(slot: u64) -> bool {
    slot % SLOTS_PER_WINDOW == 0
}

/// Observed cadence, split into increments inside a leader window and at the hand-over into a new window.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct Cadence {
    pub inside_ms: f64,
    pub boundary_ms: f64,
    pub samples_inside: usize,
    pub samples_boundary: usize,
}

impl Cadence {
    pub fn mean_slot_ms(&self) -> f64 {
        (self.inside_ms * 3.0 + self.boundary_ms) / 4.0
    }

    fn increment_ms(&self, slot: u64) -> f64 {
        if is_window_start(slot) { self.boundary_ms } else { self.inside_ms }
    }
}

fn median(mut v: Vec<f64>) -> Option<f64> {
    if v.is_empty() {
        return None;
    }
    v.sort_by(|a, b| a.total_cmp(b));
    Some(v[v.len() / 2])
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
            let mut backoff = Duration::from_millis(250);
            loop {
                let connected_at = Instant::now();
                if let Err(e) = follow(&url, &st, &tx, clock).await {
                    tracing::warn!(error = %e, "slot stream dropped; reconnecting");
                }
                // A connection that lived a while was healthy: reconnect quickly next time.
                if connected_at.elapsed() > Duration::from_secs(10) {
                    backoff = Duration::from_millis(250);
                }
                tokio::time::sleep(backoff).await;
                backoff = (backoff * 2).min(Duration::from_secs(8));
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

    pub fn first_shred_unix_ns(&self, slot: u64) -> Option<i64> {
        self.state.lock().expect("slot state").first_shred.get(&slot).copied()
    }

    /// Median observed increments over the last 256 slots, split by inside-window vs window-boundary slots.
    pub fn cadence(&self) -> Cadence {
        let st = self.state.lock().expect("slot state");
        let pts: Vec<(u64, i64)> = st.first_shred.iter().rev().take(257).map(|(s, t)| (*s, *t)).collect();
        let (mut inside, mut boundary) = (vec![], vec![]);
        for w in pts.windows(2) {
            let ((s1, t1), (s0, t0)) = (w[0], w[1]);
            if s1 != s0 + 1 || t1 < t0 {
                continue;
            }
            let d = (t1 - t0) as f64 / 1e6;
            if is_window_start(s1) {
                boundary.push(d)
            } else {
                inside.push(d)
            }
        }
        let (ni, nb) = (inside.len(), boundary.len());
        Cadence {
            inside_ms: median(inside).filter(|_| ni >= 8).unwrap_or(self.nominal_slot_ms),
            boundary_ms: median(boundary).filter(|_| nb >= 4).unwrap_or(self.nominal_slot_ms),
            samples_inside: ni,
            samples_boundary: nb,
        }
    }

    pub fn slot_ms_estimate(&self) -> f64 {
        self.cadence().mean_slot_ms()
    }

    /// Estimated first-shred observation time of `slot`: observed if we have it, otherwise extrapolated from the
    /// nearest earlier observation using the inside/boundary cadence.
    pub fn estimate_unix_ns(&self, slot: u64) -> Option<i64> {
        let c = self.cadence();
        let st = self.state.lock().expect("slot state");
        if let Some(t) = st.first_shred.get(&slot) {
            return Some(*t);
        }
        if let Some((&s0, &t0)) = st.first_shred.range(..slot).next_back() {
            let ms: f64 = (s0 + 1..=slot).map(|s| c.increment_ms(s)).sum();
            return Some(t0 + (ms * 1e6) as i64);
        }
        let (&s0, &t0) = st.first_shred.iter().next()?;
        let ms: f64 = (slot + 1..=s0).map(|s| c.increment_ms(s)).sum();
        Some(t0 - (ms * 1e6) as i64)
    }

    pub fn predict_unix_ns(&self, slot: u64) -> Option<i64> {
        self.estimate_unix_ns(slot)
    }

    pub fn predict_instant(&self, slot: u64) -> Option<Instant> {
        self.predict_unix_ns(slot).map(|ns| self.clock.unix_ns_to_instant(ns))
    }

    pub async fn wait_for_slot(&self, slot: u64) -> Result<()> {
        let mut rx = self.latest.clone();
        rx.wait_for(|s| *s >= slot).await.map_err(|_| anyhow!("slot stream ended"))?;
        Ok(())
    }

    /// Waits for the first shred of `slot`. Returns `None` if a later slot shows up first (the event was missed, e.g.
    /// during a reconnect) or the timeout passes — callers then fall back to the estimate.
    pub async fn wait_first_shred(&self, slot: u64, timeout: Duration) -> Option<i64> {
        let mut rx = self.latest.clone();
        let deadline = tokio::time::Instant::now() + timeout;
        loop {
            if let Some(t) = self.first_shred_unix_ns(slot) {
                return Some(t);
            }
            if *rx.borrow() > slot + 1 {
                return None;
            }
            match tokio::time::timeout_at(deadline, rx.changed()).await {
                Ok(Ok(())) => continue,
                _ => return self.first_shred_unix_ns(slot),
            }
        }
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
    let mut ping = tokio::time::interval(Duration::from_secs(15));
    ping.tick().await;
    loop {
        let msg = tokio::select! {
            m = ws.next() => match m {
                Some(m) => m?,
                None => break,
            },
            _ = ping.tick() => {
                ws.send(Message::Ping(Vec::new().into())).await?;
                continue;
            }
        };
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
        // Only first-shred (or plain slot) notifications time the clock; later lifecycle events are logged only.
        let timing_event = kind == "firstShredReceived" || kind == "slotNotification";
        let mut st = state.lock().expect("slot state");
        if timing_event {
            st.first_shred.entry(slot).or_insert(recv);
            while st.first_shred.len() > 4096 {
                st.first_shred.pop_first();
            }
        }
        st.events.push(SlotEvent { slot, kind, recv_unix_ns: recv, server_ms });
        drop(st);
        if timing_event {
            tx.send_if_modified(|cur| {
                if slot > *cur {
                    *cur = slot;
                    true
                } else {
                    false
                }
            });
        }
    }
    Err(anyhow!("websocket closed"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn window_alignment() {
        assert!(is_window_start(460_507_680));
        assert!(!is_window_start(460_507_681));
    }

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

    #[test]
    fn cadence_split_and_extrapolation() {
        let (_tx, rx) = watch::channel(0u64);
        let clock = SlotClock { state: Arc::new(Mutex::new(State::default())), latest: rx, clock: RunClock::new(), nominal_slot_ms: 200.0 };
        {
            let mut st = clock.state.lock().unwrap();
            let mut t = 0i64;
            for s in 1_000u64..1_200 {
                t += if is_window_start(s) { 560_000_000 } else { 130_000_000 };
                st.first_shred.insert(s, t);
            }
        }
        let c = clock.cadence();
        assert!((c.inside_ms - 130.0).abs() < 1e-9 && (c.boundary_ms - 560.0).abs() < 1e-9);
        let last = clock.first_shred_unix_ns(1_199).unwrap();
        // 1200 is a window start: one boundary increment.
        assert_eq!(clock.estimate_unix_ns(1_200).unwrap(), last + 560_000_000);
        assert_eq!(clock.estimate_unix_ns(1_201).unwrap(), last + 690_000_000);
    }
}
