//! `itb run`: executes the frozen design (PLAN §2) against mainnet leader windows.
//!
//! For each target, the k-th window we *attempt* executes the k-th plan of that target in `design.jsonl`
//! (progress is journalled, so a restarted run continues where it stopped and never re-uses a plan).
//! Each window: pre-connect → (aged) blockhash → distinct payers from the pool → sign → reserve every probe in the
//! ledger → send over one QUIC connection, anchored on observed slot events → resolve outcomes → release payers.
//! Gossip is snapshotted every 60 s so the analysis can classify each window's leader mode as stable or ambiguous.

use crate::alpenglow;
use crate::auth::{LiveAuthorization, sol_to_lamports};
use crate::collect::{self, Tracked};
use crate::design::{self, Kit, WindowPlan};
use crate::keys::{load_payers, read_keypair};
use crate::ledger::{Kind, Ledger, reconcile};
use crate::quic::{ConnectReport, Outgoing, QuicClient};
use crate::rpc::Rpc;
use crate::smoke::redact_url;
use crate::store::{Jsonl, RunDir, new_run_id, utc_now_rfc3339};
use crate::targets::{self, Validator};
use crate::timing::{RunClock, SlotClock};
use anyhow::{Context, Result, bail};
use base64::Engine;
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use solana_keypair::Keypair;
use solana_pubkey::Pubkey;
use solana_signer::Signer;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub struct RunArgs {
    pub live: bool,
    pub max_spend_sol: Option<f64>,
    pub ledger: PathBuf,
    pub keypair: Option<PathBuf>,
    pub payer_dir: PathBuf,
    pub design: PathBuf,
    pub design_sha256: Option<String>,
    pub stage: u8,
    pub out: PathBuf,
    pub progress: PathBuf,
    pub targets: Vec<String>,
    pub max_windows: usize,
    pub max_minutes: u64,
    pub concurrency: usize,
    /// Observer-lag compensation from the pilot: sends move this many ms *earlier* than the plan's nominal instant.
    pub obs_lag_ms: f64,
    pub nominal_slot_ms: f64,
    /// Replace every target's advertised TPU address (localnet tests from the host).
    pub tpu_override: Option<SocketAddr>,
}

/// What a send instant is measured from (PLAN §2.5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    /// Far ahead of the window (H/S kits): extrapolated from the cadence at preparation time.
    Estimate,
    /// First shred of the previous leader's last slot, plus the observed hand-over gap (buffered regime).
    PrevSlot,
    /// First shred of the target's first slot (streaming regime).
    WindowSlot,
}

#[derive(Serialize)]
struct ProbeRecord<'a> {
    run_id: &'a str,
    probe_id: String,
    target_identity: &'a str,
    seq: u32,
    stage: u8,
    kit: Kit,
    regime: design::Regime,
    pair_id: &'a str,
    pair_kind: design::PairKind,
    label: &'a str,
    send_position_in_pair: usize,
    race_dt_ms: Option<f64>,
    template: crate::probe::Template,
    priority_fee: u64,
    total_fee: u64,
    cost: u64,
    agave_priority: u64,
    lock: String,
    lock_index: u32,
    payer: String,
    signature: String,
    blockhash: String,
    blockhash_slot: u64,
    last_valid_block_height: u64,
    window_first_slot: u64,
    window_last_slot: u64,
    anchor: Anchor,
    nominal_offset_ms: f64,
    wire_base64: String,
}

/// Payer pool: a payer is never used twice in one window nor while one of its transactions is unresolved.
struct PayerPool {
    keys: Vec<Arc<Keypair>>,
    busy: Mutex<HashSet<usize>>,
    cursor: Mutex<usize>,
}

impl PayerPool {
    fn take(&self, n: usize) -> Option<Vec<usize>> {
        let mut busy = self.busy.lock().expect("pool");
        let mut cursor = self.cursor.lock().expect("pool");
        let mut picked = vec![];
        for step in 0..self.keys.len() {
            let i = (*cursor + step) % self.keys.len();
            if !busy.contains(&i) {
                picked.push(i);
                if picked.len() == n {
                    break;
                }
            }
        }
        if picked.len() < n {
            return None;
        }
        // Rotate the start so payer identity is spread evenly over treatments.
        *cursor = (picked[n - 1] + 1) % self.keys.len();
        busy.extend(picked.iter().copied());
        Some(picked)
    }

    fn release(&self, idx: &[usize]) {
        let mut busy = self.busy.lock().expect("pool");
        for i in idx {
            busy.remove(i);
        }
    }
}

fn lock_for(run_id: &str, target: &str, seq: u32, lock_index: u32) -> Pubkey {
    let h = Sha256::digest(format!("itb-lock/{run_id}/{target}/{seq}/{lock_index}").as_bytes());
    Pubkey::new_from_array(h.into())
}

/// Leader windows of `identity` starting after `from_slot`, looking into the next epoch if needed.
/// Leader windows per target, fetched once per epoch (the schedule is fixed for an epoch).
#[derive(Default)]
struct ScheduleCache {
    /// (target, epoch first slot) -> windows
    windows: HashMap<(String, u64), Vec<(u64, u64)>>,
    epoch: Option<crate::rpc::EpochInfo>,
}

impl ScheduleCache {
    async fn upcoming(&mut self, rpc: &Rpc, identity: &str, from_slot: u64) -> Result<Option<(u64, u64)>> {
        let stale = self.epoch.as_ref().is_none_or(|e| from_slot >= e.first_slot_of_epoch() + e.slots_in_epoch);
        if stale {
            self.epoch = Some(rpc.get_epoch_info().await?);
        }
        let e = self.epoch.clone().expect("epoch info");
        let first = e.first_slot_of_epoch();
        let mut epochs = vec![first];
        if (first + e.slots_in_epoch).saturating_sub(from_slot) < 20_000 {
            epochs.push(first + e.slots_in_epoch);
        }
        for ep_first in epochs {
            let key = (identity.to_string(), ep_first);
            if !self.windows.contains_key(&key) {
                let slots = rpc.leader_slots(ep_first, identity, ep_first).await.unwrap_or_default();
                self.windows.insert(key.clone(), targets::windows(slots));
            }
            if let Some(w) = self.windows[&key].iter().find(|(s, _)| *s > from_slot) {
                return Ok(Some(*w));
            }
        }
        Ok(None)
    }
}

fn load_progress(path: &PathBuf) -> Result<HashMap<String, HashSet<u32>>> {
    let mut done: HashMap<String, HashSet<u32>> = HashMap::new();
    if let Ok(text) = std::fs::read_to_string(path) {
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            let v: serde_json::Value = serde_json::from_str(line)?;
            if let (Some(t), Some(s)) = (v["target_identity"].as_str(), v["seq"].as_u64()) {
                done.entry(t.to_string()).or_default().insert(s as u32);
            }
        }
    }
    Ok(done)
}

pub async fn run(rpc: Arc<Rpc>, ws_url: &str, args: RunArgs) -> Result<()> {
    let clock = RunClock::new();
    let run_id = new_run_id(&format!("s{}-{}", args.stage, if args.live { "live" } else { "dry" }));
    let run = Arc::new(RunDir::create(args.out.join(&run_id))?);
    std::fs::create_dir_all(run.path.join("gossip"))?;
    let started_at = utc_now_rfc3339();
    let gate = alpenglow::require_active(&rpc).await?;

    // ---- the frozen design ----
    let design_bytes = std::fs::read(&args.design).with_context(|| format!("reading {}", args.design.display()))?;
    let design_sha = format!("{:x}", Sha256::digest(&design_bytes));
    if let Some(expected) = &args.design_sha256 {
        if !expected.eq_ignore_ascii_case(&design_sha) {
            bail!("design sha256 {design_sha} does not match the pre-registered {expected}");
        }
    }
    let mut plans: BTreeMap<String, Vec<WindowPlan>> = BTreeMap::new();
    for line in String::from_utf8(design_bytes)?.lines().filter(|l| !l.trim().is_empty()) {
        let p: WindowPlan = serde_json::from_str(line)?;
        if p.stage == args.stage && (args.targets.is_empty() || args.targets.contains(&p.target_identity)) {
            plans.entry(p.target_identity.clone()).or_default().push(p);
        }
    }
    let done = load_progress(&args.progress)?;
    for (t, ps) in plans.iter_mut() {
        ps.sort_by_key(|p| p.seq);
        let d = done.get(t).cloned().unwrap_or_default();
        ps.retain(|p| !d.contains(&p.seq));
    }
    plans.retain(|_, ps| !ps.is_empty());
    if plans.is_empty() {
        bail!("nothing left to run for stage {}", args.stage);
    }
    let max_probes = plans.values().flatten().map(design::probe_count).max().unwrap_or(0);

    // ---- live prerequisites ----
    let (ledger, auth, pool, master) = if args.live {
        let cap = sol_to_lamports(args.max_spend_sol.context("--live requires --max-spend-sol")?)?;
        let ledger = Arc::new(Ledger::open(&args.ledger, cap)?);
        let auth = Arc::new(LiveAuthorization::grant(true, args.max_spend_sol, &gate, &ledger)?);
        let master = read_keypair(args.keypair.as_deref().context("--live requires --keypair")?)?;
        let payers = load_payers(&args.payer_dir)?;
        if payers.len() < max_probes * 2 {
            bail!("payer pool has {} keys; need at least {} (two windows in flight)", payers.len(), max_probes * 2);
        }
        let pool = PayerPool { keys: payers.into_iter().map(Arc::new).collect(), busy: Default::default(), cursor: Mutex::new(0) };
        (Some(ledger), Some(auth), Arc::new(pool), Some(master.pubkey()))
    } else {
        let keys = (0..max_probes * 3).map(|_| Arc::new(Keypair::new())).collect();
        (None, None, Arc::new(PayerPool { keys, busy: Default::default(), cursor: Mutex::new(0) }), None)
    };
    let owned: Vec<String> = master.iter().map(|m| m.to_string()).chain(pool.keys.iter().map(|k| k.pubkey().to_string())).collect();
    let initial_total: u64 = if args.live { rpc.balances(&owned).await?.iter().sum() } else { 0 };

    // ---- gossip snapshots every 60 s ----
    let (validators, raw) = targets::snapshot(&rpc).await?;
    run.write_zst(&format!("gossip/{}.json.zst", clock.now_unix_ns()), &raw)?;
    let states = Arc::new(run.jsonl("target_states.jsonl")?);
    let target_ids: Vec<String> = plans.keys().cloned().collect();
    let at = clock.now_unix_ns();
    for id in &target_ids {
        states.append(&json!({"at_unix_ns": at, "identity": id, "state": validators.iter().find(|v| &v.identity == id)}))?;
    }
    {
        let (rpc, run, states, ids) = (rpc.clone(), run.clone(), states.clone(), target_ids.clone());
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(60)).await;
                match targets::snapshot(&rpc).await {
                    Ok((vals, raw)) => {
                        let at = clock.now_unix_ns();
                        let _ = run.write_zst(&format!("gossip/{at}.json.zst"), &raw);
                        for id in &ids {
                            let v = vals.iter().find(|v| &v.identity == id);
                            let _ = states.append(&json!({"at_unix_ns": at, "identity": id, "state": v}));
                        }
                    }
                    Err(e) => tracing::warn!(error = %e, "gossip snapshot failed"),
                }
            }
        });
    }

    let slot_clock = SlotClock::start(ws_url, clock, args.nominal_slot_ms).await?;
    let quic = Arc::new(QuicClient::new(clock)?);
    let logs = Arc::new(Logs {
        probes: run.jsonl("probes.jsonl")?,
        sends: run.jsonl("sends.jsonl")?,
        windows: run.jsonl("windows.jsonl")?,
        outcomes: run.jsonl("outcomes.jsonl")?,
        progress: Jsonl::open(&args.progress)?,
    });
    let addr_of: HashMap<String, Validator> = validators.iter().map(|v| (v.identity.clone(), v.clone())).collect();

    run.write_json("run_start.json", &json!({
        "run_id": run_id, "mode": if args.live { "live" } else { "dry_run" }, "stage": args.stage,
        "started_at": started_at, "rpc": redact_url(rpc.url()), "ws": redact_url(ws_url), "alpenglow": gate,
        "design_file": args.design, "design_sha256": design_sha, "obs_lag_ms": args.obs_lag_ms,
        "tpu_override": args.tpu_override, "targets": target_ids, "initial_owned_lamports": initial_total,
        "itb_version": env!("CARGO_PKG_VERSION"),
    }))?;

    // Warm-up: the cadence estimate needs a few window hand-overs before anchors and estimates are trustworthy.
    let warm_deadline = tokio::time::Instant::now() + Duration::from_secs(90);
    while slot_clock.cadence().samples_boundary < 8 && tokio::time::Instant::now() < warm_deadline {
        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    // Stage-1 stopping (PREREGISTRATION §5): per target, pairs with both members landed, for C1, C2, C3.
    let informative: Arc<Mutex<HashMap<String, [u32; 3]>>> = Arc::new(Mutex::new(load_informative(&args.progress)?));

    let deadline = tokio::time::Instant::now() + Duration::from_secs(args.max_minutes * 60);
    let semaphore = Arc::new(tokio::sync::Semaphore::new(args.concurrency.max(1)));
    let mut handles = vec![];
    let mut windows_started = 0usize;
    let mut next_from: HashMap<String, u64> = HashMap::new();
    let mut schedule = ScheduleCache::default();

    while windows_started < args.max_windows && tokio::time::Instant::now() < deadline {
        // Next upcoming window across all targets that still have plans.
        let now_slot = slot_clock.latest_slot();
        let mut best: Option<(u64, u64, String)> = None;
        for (t, ps) in plans.iter_mut() {
            if args.stage == 1 && ps.first().is_some_and(|p| {
                let need = design::informative_target(&p.tier);
                informative.lock().expect("informative").get(t).is_some_and(|c| c.iter().all(|n| *n >= need))
            }) {
                tracing::info!(target = %t, "stage-1 informative target reached; no more windows for this target");
                ps.clear();
            }
            if ps.is_empty() {
                continue;
            }
            let from = (*next_from.get(t).unwrap_or(&0)).max(now_slot + 40);
            if let Some((s, e)) = schedule.upcoming(&rpc, t, from).await? {
                if best.as_ref().is_none_or(|b| s < b.0) {
                    best = Some((s, e, t.clone()));
                }
            }
        }
        let Some((first, last, target)) = best else { break };
        next_from.insert(target.clone(), last + 1);
        let plan = plans.get_mut(&target).expect("target").remove(0);
        let Some(mut validator) = addr_of.get(&target).cloned() else {
            tracing::warn!(%target, "target not in gossip snapshot; skipping its plans");
            plans.get_mut(&target).expect("target").clear();
            continue;
        };
        if let Some(o) = args.tpu_override {
            validator.tpu_quic = Some(o.to_string());
        }
        if let Some(l) = &ledger {
            if l.totals()?.headroom() < design::max_fee(&plan) {
                tracing::warn!("spend cap reached; stopping");
                break;
            }
            let current: u64 = rpc.balances(&owned).await?.iter().sum();
            reconcile(initial_total, 0, current, l.cap())?;
        }
        let permit = semaphore.clone().acquire_owned().await?;
        windows_started += 1;
        let ctx = WindowCtx {
            rpc: rpc.clone(),
            quic: quic.clone(),
            slot_clock: slot_clock.clone(),
            clock,
            pool: pool.clone(),
            ledger: ledger.clone(),
            auth: auth.clone(),
            run_id: run_id.clone(),
            logs: logs.clone(),
            run: run.clone(),
            obs_lag_ms: args.obs_lag_ms,
            informative: informative.clone(),
        };
        handles.push(tokio::spawn(async move {
            let r = execute_window(ctx, validator, plan, (first, last)).await;
            drop(permit);
            if let Err(e) = r {
                tracing::error!(error = %e, "window failed");
            }
        }));
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    for h in handles {
        let _ = h.await;
    }

    let mut summary = json!({"run_id": run_id, "windows_started": windows_started, "finished_at": utc_now_rfc3339(),
                             "cadence": slot_clock.cadence()});
    if let Some(l) = &ledger {
        let current: u64 = rpc.balances(&owned).await?.iter().sum();
        summary["owned_lamports_drop_on_chain"] = json!(reconcile(initial_total, 0, current, l.cap())?);
        summary["ledger"] = serde_json::to_value(l.totals()?)?;
    }
    quic.close_all().await;
    run.write_zst("slot_events.json.zst", &slot_clock.take_events())?;
    run.write_json("run_end.json", &summary)?;
    eprintln!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}

struct Logs {
    probes: Jsonl,
    sends: Jsonl,
    windows: Jsonl,
    outcomes: Jsonl,
    progress: Jsonl,
}

struct WindowCtx {
    rpc: Arc<Rpc>,
    quic: Arc<QuicClient>,
    slot_clock: SlotClock,
    clock: RunClock,
    pool: Arc<PayerPool>,
    ledger: Option<Arc<Ledger>>,
    auth: Option<Arc<LiveAuthorization>>,
    run_id: String,
    logs: Arc<Logs>,
    run: Arc<RunDir>,
    obs_lag_ms: f64,
    informative: Arc<Mutex<HashMap<String, [u32; 3]>>>,
}

/// Rebuilds the stage-1 informative counters from earlier runs' progress records.
fn load_informative(progress: &PathBuf) -> Result<HashMap<String, [u32; 3]>> {
    let mut out: HashMap<String, [u32; 3]> = HashMap::new();
    if let Ok(text) = std::fs::read_to_string(progress) {
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            let v: serde_json::Value = serde_json::from_str(line)?;
            if let (Some(t), Some(arr)) = (v["target_identity"].as_str(), v["informative_pairs"].as_array()) {
                let e = out.entry(t.to_string()).or_default();
                for (i, n) in arr.iter().enumerate().take(3) {
                    e[i] += n.as_u64().unwrap_or(0) as u32;
                }
            }
        }
    }
    Ok(out)
}

struct Pending {
    probe_id: String,
    wire: Vec<u8>,
    anchor: Anchor,
    nominal_ms: f64,
}

/// Sends inside the hand-over gap are anchored on the previous leader's last slot; the gap is ≥ ~280 ms in every
/// observation so far, so −250 ms is the deepest offset that still lands after the anchor event.
pub const PREV_SLOT_MAX_LEAD_MS: f64 = 250.0;

fn anchor_for(nominal_ms: f64) -> Anchor {
    if nominal_ms >= 0.0 {
        Anchor::WindowSlot
    } else if nominal_ms >= -PREV_SLOT_MAX_LEAD_MS {
        Anchor::PrevSlot
    } else {
        Anchor::Estimate
    }
}

async fn execute_window(ctx: WindowCtx, v: Validator, plan: WindowPlan, window: (u64, u64)) -> Result<()> {
    let cadence = ctx.slot_clock.cadence();
    let slot_ms = cadence.mean_slot_ms();
    let nominal = |offset: f64| plan.burst_offset_ms + offset - ctx.obs_lag_ms;
    let earliest_ms = plan.pairs.iter().flat_map(|p| &p.members).map(|m| nominal(m.send_offset_ms)).fold(0.0f64, f64::min);
    // Prepare ≥ 1.5 s before the earliest send.
    let prep_slots = (((-earliest_ms).max(0.0) + 1_500.0) / slot_ms).ceil() as u64;
    let mut row = json!({
        "run_id": ctx.run_id, "target_identity": v.identity, "client_id": v.client_id, "ingress": v.ingress,
        "tpu_quic": v.tpu_quic, "version": v.version, "seq": plan.seq, "stage": plan.stage, "kit": plan.kit,
        "regime": plan.regime, "burst_offset_ms": plan.burst_offset_ms, "obs_lag_ms": ctx.obs_lag_ms,
        "window_first_slot": window.0, "window_last_slot": window.1, "cadence_at_prep": cadence,
    });

    let addr = v.tpu_addr().context("no tpuQuic")?;
    ctx.slot_clock.wait_for_slot(window.0.saturating_sub(prep_slots + 12)).await?;
    let connect: ConnectReport = ctx.quic.connect(addr).await;
    row["connect"] = serde_json::to_value(&connect)?;

    ctx.slot_clock.wait_for_slot(window.0.saturating_sub(prep_slots)).await?;
    let bh = if plan.blockhash_age_slots > 0 {
        ctx.rpc.aged_blockhash(plan.blockhash_age_slots.saturating_sub(prep_slots)).await?
    } else {
        ctx.rpc.latest_blockhash().await?
    };
    let est_start = ctx.slot_clock.estimate_unix_ns(window.0).context("no slot estimate")?;
    row["estimated_window_start_unix_ns"] = json!(est_start);

    let n = design::probe_count(&plan);
    let Some(payer_idx) = ctx.pool.take(n) else {
        row["skipped"] = json!("payer_pool_exhausted");
        ctx.logs.windows.append(&row)?;
        return Ok(());
    };

    // Build and sign every probe; log the signed realisation before anything is sent.
    let mut pending = vec![];
    let mut tracked = vec![];
    let mut max_fees = vec![];
    let mut k = 0usize;
    for pair in &plan.pairs {
        for (pos, m) in pair.members.iter().enumerate() {
            let payer = ctx.pool.keys[payer_idx[k]].clone();
            k += 1;
            let lock = lock_for(&ctx.run_id, &v.identity, plan.seq, m.lock_index);
            let tx = m.template.build(&payer, &lock, bh.blockhash.clone());
            let wire = bincode::serialize(&tx)?;
            let signature = tx.signatures[0].to_string();
            let nominal_ms = nominal(m.send_offset_ms);
            let anchor = anchor_for(nominal_ms);
            let probe_id = format!("{}/{}", pair.pair_id, m.label);
            ctx.logs.probes.append(&ProbeRecord {
                run_id: &ctx.run_id,
                probe_id: probe_id.clone(),
                target_identity: &v.identity,
                seq: plan.seq,
                stage: plan.stage,
                kit: plan.kit,
                regime: plan.regime,
                pair_id: &pair.pair_id,
                pair_kind: pair.kind,
                label: &m.label,
                send_position_in_pair: pos,
                race_dt_ms: pair.race_dt_ms,
                template: m.template,
                priority_fee: m.template.priority_fee(),
                total_fee: m.template.total_fee(),
                cost: m.template.cost(),
                agave_priority: m.template.agave_priority(),
                lock: lock.to_string(),
                lock_index: m.lock_index,
                payer: payer.pubkey().to_string(),
                signature: signature.clone(),
                blockhash: bh.blockhash.to_string(),
                blockhash_slot: bh.slot,
                last_valid_block_height: bh.last_valid_block_height,
                window_first_slot: window.0,
                window_last_slot: window.1,
                anchor,
                nominal_offset_ms: nominal_ms,
                wire_base64: base64::engine::general_purpose::STANDARD.encode(&wire),
            })?;
            tracked.push(Tracked {
                probe_id: probe_id.clone(),
                signature,
                target_identity: v.identity.clone(),
                window_first_slot: window.0,
                window_last_slot: window.1,
                last_valid_block_height: bh.last_valid_block_height,
                transport_error: None,
            });
            max_fees.push(m.template.total_fee());
            pending.push(Pending { probe_id, wire, anchor, nominal_ms });
        }
    }

    let live = match (&ctx.auth, &ctx.ledger) {
        (Some(auth), Some(ledger)) => {
            if connect.error.is_some() {
                row["skipped"] = json!("connect_failed");
                ctx.logs.windows.append(&row)?;
                ctx.pool.release(&payer_idx);
                return Ok(());
            }
            Some((auth.clone(), ledger.clone()))
        }
        _ => None,
    };
    let fee_of: HashMap<String, u64> = tracked.iter().zip(&max_fees).map(|(t, f)| (t.probe_id.clone(), *f)).collect();
    let sig_of: HashMap<String, String> = tracked.iter().map(|t| (t.probe_id.clone(), t.signature.clone())).collect();
    let mut not_sent: HashMap<String, &'static str> = HashMap::new();

    // Phases in time order. An event anchor that is not observed (stream gap, skipped slot) cancels its phase:
    // those probes are never reserved nor sent, rather than being sent at a badly estimated time.
    let mut records = vec![];
    let mut anchors = serde_json::Map::new();
    for phase in [Anchor::Estimate, Anchor::PrevSlot, Anchor::WindowSlot] {
        let items: Vec<&Pending> = pending.iter().filter(|p| p.anchor == phase).collect();
        if items.is_empty() {
            continue;
        }
        let (anchor_slot, extra_ms) = match phase {
            Anchor::Estimate => (window.0, 0.0),
            Anchor::PrevSlot => (window.0 - 1, cadence.boundary_ms),
            Anchor::WindowSlot => (window.0, 0.0),
        };
        let (anchor_ns, observed) = if phase == Anchor::Estimate {
            (est_start, false)
        } else {
            let est = ctx.slot_clock.estimate_unix_ns(anchor_slot).unwrap_or(est_start);
            let wait = Duration::from_nanos((est - ctx.clock.now_unix_ns()).max(0) as u64) + Duration::from_millis(800);
            match ctx.slot_clock.wait_first_shred(anchor_slot, wait).await {
                Some(t) => (t, true),
                None => (est, false),
            }
        };
        anchors.insert(
            format!("{phase:?}"),
            json!({"slot": anchor_slot, "anchor_unix_ns": anchor_ns, "observed": observed, "extra_ms": extra_ms}),
        );
        if phase != Anchor::Estimate && !observed {
            for p in &items {
                not_sent.insert(p.probe_id.clone(), "anchor_missed");
            }
            continue;
        }
        let outgoing: Vec<Outgoing> = items
            .iter()
            .map(|p| {
                let at_ns = anchor_ns + ((extra_ms + p.nominal_ms) * 1e6) as i64;
                Outgoing { probe_id: p.probe_id.clone(), wire: p.wire.clone(), at: tokio::time::Instant::from_std(ctx.clock.unix_ns_to_instant(at_ns)) }
            })
            .collect();
        match &live {
            Some((auth, ledger)) => {
                for p in &items {
                    ledger.reserve(&sig_of[&p.probe_id], Kind::Probe, &p.probe_id, fee_of[&p.probe_id])?;
                }
                records.extend(ctx.quic.send_scheduled(auth, addr, outgoing).await)
            }
            None => {
                for o in outgoing {
                    tokio::time::sleep_until(o.at).await;
                    ctx.logs.sends.append(&json!({"run_id": ctx.run_id, "dry_run": true, "probe_id": o.probe_id,
                                                  "would_send_unix_ns": ctx.clock.instant_to_unix_ns(o.at.into_std())}))?;
                }
            }
        }
    }
    row["anchors"] = serde_json::Value::Object(anchors);
    row["not_sent"] = json!(not_sent.len());
    // Which of the window's slots the target actually produced (eligibility criterion (c)); give the cluster a moment.
    tokio::time::sleep(Duration::from_secs(3)).await;
    match ctx.rpc.blocks_in_range(window.0, window.1).await {
        Ok(slots) => row["produced_slots"] = json!(slots),
        Err(e) => row["produced_slots_error"] = json!(e.to_string()),
    }
    for t in &mut tracked {
        if let Some(reason) = not_sent.get(&t.probe_id) {
            t.transport_error = Some(format!("not_sent: {reason}"));
        }
    }

    if live.is_some() {
        let by_id: HashMap<&str, &crate::quic::StreamRecord> = records.iter().map(|r| (r.probe_id.as_str(), r)).collect();
        for t in &mut tracked {
            if let Some(r) = by_id.get(t.probe_id.as_str()) {
                t.transport_error = r.error.clone();
            }
        }
        for r in &records {
            ctx.logs.sends.append(&json!({"run_id": ctx.run_id, "dry_run": false, "record": r}))?;
        }
        row["sent_ok"] = json!(records.iter().filter(|r| r.error.is_none()).count());
    }
    ctx.logs.windows.append(&row)?;

    let mut informative_pairs = [0u32; 3];
    if live.is_some() {
        let (unsent, sent): (Vec<Tracked>, Vec<Tracked>) = tracked.into_iter().partition(|t| not_sent.contains_key(&t.probe_id));
        let mut outcomes = collect::resolve(&ctx.rpc, ctx.ledger.as_deref(), &sent, &ctx.run, Duration::from_secs(90)).await?;
        outcomes.extend(unsent.iter().map(collect::not_sent_outcome));
        for o in &outcomes {
            ctx.logs.outcomes.append(&json!({"run_id": ctx.run_id, "outcome": o}))?;
        }
        if plan.kit == Kit::K {
            let landed: HashSet<&str> = outcomes
                .iter()
                .filter(|o| o.status == collect::Status::LandedTarget)
                .map(|o| o.probe_id.as_str())
                .collect();
            for pair in &plan.pairs {
                let idx = match pair.kind {
                    design::PairKind::C1 => 0,
                    design::PairKind::C2 => 1,
                    design::PairKind::C3 => 2,
                    _ => continue,
                };
                if pair.members.iter().all(|m| landed.contains(format!("{}/{}", pair.pair_id, m.label).as_str())) {
                    informative_pairs[idx] += 1;
                }
            }
            let mut inf = ctx.informative.lock().expect("informative");
            let e = inf.entry(v.identity.clone()).or_default();
            for (acc, n) in e.iter_mut().zip(informative_pairs) {
                *acc += n;
            }
        }
    }
    ctx.logs.progress.append(&json!({"run_id": ctx.run_id, "target_identity": v.identity, "seq": plan.seq,
                                     "live": live.is_some(), "informative_pairs": informative_pairs,
                                     "at": utc_now_rfc3339()}))?;
    ctx.pool.release(&payer_idx);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn anchors_by_offset() {
        assert_eq!(anchor_for(60.0), Anchor::WindowSlot);
        assert_eq!(anchor_for(0.0), Anchor::WindowSlot);
        assert_eq!(anchor_for(-150.0), Anchor::PrevSlot);
        assert_eq!(anchor_for(-250.0), Anchor::PrevSlot);
        assert_eq!(anchor_for(-600.0), Anchor::Estimate);
        assert_eq!(anchor_for(-7_000.0), Anchor::Estimate);
    }

    #[test]
    fn payer_pool_never_hands_out_busy_payers() {
        let pool = PayerPool { keys: (0..10).map(|_| Arc::new(Keypair::new())).collect(), busy: Default::default(), cursor: Mutex::new(0) };
        let a = pool.take(8).unwrap();
        assert!(pool.take(3).is_none(), "only 2 free");
        let b = pool.take(2).unwrap();
        assert!(a.iter().all(|i| !b.contains(i)));
        pool.release(&a);
        assert_eq!(pool.take(8).unwrap().len(), 8);
    }
}
