//! `itb run`: executes the frozen design (PLAN §2) against mainnet leader windows.
//!
//! For each target, the k-th window we *attempt* executes the k-th plan of that target in `design.jsonl`. Attempts
//! are journalled durably *before* anything is sent ("claimed") and again when resolved ("terminal"), so a crash can
//! never re-run a plan, and dry runs keep a separate journal that can never consume live plans.
//!
//! Each window: refresh the target's endpoint from the latest gossip snapshot → pre-connect → (aged) blockhash →
//! distinct, randomly assigned payers not leased in the ledger → sign → claim → for each send phase: wait for its
//! observed anchor, check the deadline, reserve the phase atomically, send with per-probe deadlines, cancel what was
//! provably never sent → resolve outcomes → release payers whose outcomes are terminal → journal.

use crate::alpenglow;
use crate::auth::{LiveAuthorization, sol_to_lamports};
use crate::collect::{self, Status, Tracked};
use crate::design::{self, Kit, WindowPlan};
use crate::keys::{load_payers, read_keypair};
use crate::ledger::{Kind, Ledger, Reservation, reconcile};
use crate::quic::{ConnectReport, Outgoing, QuicClient};
use crate::rpc::{MAINNET_GENESIS_HASH, Rpc, redact_url};
use crate::store::{Jsonl, RunDir, new_run_id, utc_now_rfc3339};
use crate::targets::{self, Validator};
use crate::timing::{AnchorEvent, RunClock, SlotClock};
use anyhow::{Context, Result, bail};
use base64::Engine;
use rand::seq::SliceRandom;
use rand::SeedableRng;
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use solana_keypair::Keypair;
use solana_pubkey::Pubkey;
use solana_signer::Signer;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};
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
    /// Campaign cutoff (Unix seconds): no window is prepared and nothing is sent after it.
    pub not_after_unix: Option<i64>,
    pub concurrency: usize,
    /// Observer-lag compensation from the pilot: sends move this many ms *earlier* than the plan's nominal instant.
    pub obs_lag_ms: f64,
    pub nominal_slot_ms: f64,
    pub anchor_event: AnchorEvent,
    /// A probe whose send instant has passed by more than this is not sent (and is provably unsent).
    pub max_lateness_ms: f64,
    /// Sub-budget this run's probes count against (inside the campaign cap), and its cap if being defined now.
    pub budget: String,
    pub budget_cap_sol: Option<f64>,
    /// Refuse to run unless the RPC is mainnet-beta (genesis hash). Off only for localnet tests.
    pub require_mainnet: bool,
    /// Replace every target's advertised TPU address (localnet tests from the host).
    pub tpu_override: Option<SocketAddr>,
}

/// What a send instant is measured from (PLAN §2.5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Anchor {
    /// Far ahead of the window (H/S kits): extrapolated from the cadence at preparation time.
    Estimate,
    /// Observed anchor event of the previous leader's last slot, plus the observed hand-over gap (buffered regime).
    PrevSlot,
    /// Observed anchor event of the target's first slot (streaming regime).
    WindowSlot,
}

/// Sends inside the hand-over gap are anchored on the previous leader's last slot; the gap is ≥ ~280 ms in every
/// observation so far, so −250 ms is the deepest offset that still lands after the anchor event.
pub const PREV_SLOT_MAX_LEAD_MS: f64 = 250.0;
/// Tolerance for on-chain reconciliation vs ledger-committed fees (rounding of in-flight resolution).
const RECONCILE_TOLERANCE_LAMPORTS: u64 = 10_000;

fn anchor_for(nominal_ms: f64) -> Anchor {
    if nominal_ms >= 0.0 {
        Anchor::WindowSlot
    } else if nominal_ms >= -PREV_SLOT_MAX_LEAD_MS {
        Anchor::PrevSlot
    } else {
        Anchor::Estimate
    }
}

#[derive(Serialize)]
struct ProbeRecord<'a> {
    run_id: &'a str,
    probe_id: String,
    target_identity: &'a str,
    seq: u32,
    stage: u8,
    tier: &'a str,
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

/// Payer pool. A payer is never used twice in one window, never while one of its transactions is unresolved (the
/// ledger's open reservations lease it, across restarts), and is assigned to members at random.
struct PayerPool {
    keys: Vec<Arc<Keypair>>,
    busy: Mutex<HashSet<usize>>,
}

impl PayerPool {
    fn new(keys: Vec<Keypair>, master: Option<&Pubkey>, leased: &HashSet<String>) -> Result<Self> {
        let mut seen = HashSet::new();
        for k in &keys {
            let pk = k.pubkey();
            if !seen.insert(pk) {
                bail!("payer {pk} appears twice in the payer directory");
            }
            if Some(&pk) == master {
                bail!("the master key must not also be a payer");
            }
        }
        let busy = keys.iter().enumerate().filter(|(_, k)| leased.contains(&k.pubkey().to_string())).map(|(i, _)| i).collect();
        Ok(Self { keys: keys.into_iter().map(Arc::new).collect(), busy: Mutex::new(busy) })
    }

    /// `n` distinct free payers in random order (seeded per window, recorded).
    fn take(&self, n: usize, rng: &mut rand_chacha::ChaCha20Rng) -> Option<Vec<usize>> {
        let mut busy = self.busy.lock().expect("pool");
        let mut free: Vec<usize> = (0..self.keys.len()).filter(|i| !busy.contains(i)).collect();
        if free.len() < n {
            return None;
        }
        free.shuffle(rng);
        free.truncate(n);
        busy.extend(free.iter().copied());
        Some(free)
    }

    fn release(&self, idx: impl IntoIterator<Item = usize>) {
        let mut busy = self.busy.lock().expect("pool");
        for i in idx {
            busy.remove(&i);
        }
    }

    fn busy_count(&self) -> usize {
        self.busy.lock().expect("pool").len()
    }
}

/// One live campaign process at a time per ledger (two processes would not share payer leases in memory).
struct CampaignLock(PathBuf);

impl CampaignLock {
    fn acquire(ledger: &Path, run_id: &str) -> Result<Self> {
        let path = ledger.with_extension("lock");
        let mut f = std::fs::OpenOptions::new().write(true).create_new(true).open(&path).with_context(|| {
            format!("{} exists: another live run holds the campaign lock (remove it only if no itb process is running)", path.display())
        })?;
        use std::io::Write;
        writeln!(f, "{run_id} pid {}", std::process::id())?;
        Ok(Self(path))
    }
}

impl Drop for CampaignLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

fn lock_for(run_id: &str, target: &str, seq: u32, lock_index: u32) -> Pubkey {
    let h = Sha256::digest(format!("itb-lock/{run_id}/{target}/{seq}/{lock_index}").as_bytes());
    Pubkey::new_from_array(h.into())
}

fn window_seed(run_id: &str, target: &str, seq: u32) -> u64 {
    u64::from_le_bytes(Sha256::digest(format!("itb-payers/{run_id}/{target}/{seq}").as_bytes())[..8].try_into().expect("8 bytes"))
}

/// Leader windows per target, fetched once per epoch (the schedule is fixed for an epoch).
#[derive(Default)]
struct ScheduleCache {
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

/// Journal state recovered at start: plans already claimed (never re-run) and stage-1 informative counts.
struct Progress {
    claimed: HashMap<String, HashSet<u32>>,
    informative: HashMap<String, [u32; 3]>,
}

fn load_progress(path: &Path, live: bool) -> Result<Progress> {
    let mut p = Progress { claimed: HashMap::new(), informative: HashMap::new() };
    if let Ok(text) = std::fs::read_to_string(path) {
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            let v: serde_json::Value = serde_json::from_str(line)?;
            if v["live"].as_bool() != Some(live) {
                continue; // dry-run records never consume live plans, and vice versa
            }
            let (Some(t), Some(seq)) = (v["target_identity"].as_str(), v["seq"].as_u64()) else { continue };
            p.claimed.entry(t.to_string()).or_default().insert(seq as u32);
            if v["state"] == "terminal" {
                if let Some(arr) = v["informative_pairs"].as_array() {
                    let e = p.informative.entry(t.to_string()).or_default();
                    for (i, n) in arr.iter().enumerate().take(3) {
                        e[i] += n.as_u64().unwrap_or(0) as u32;
                    }
                }
            }
        }
    }
    Ok(p)
}

struct Logs {
    probes: Jsonl,
    sends: Jsonl,
    windows: Jsonl,
    outcomes: Jsonl,
    progress: Jsonl,
}

struct Live {
    auth: Arc<LiveAuthorization>,
    ledger: Arc<Ledger>,
    budget: String,
    owned: Vec<String>,
    opening: u64,
}

pub async fn run(rpc: Arc<Rpc>, ws_url: &str, args: RunArgs) -> Result<()> {
    let clock = RunClock::new();
    let run_id = new_run_id(&format!("s{}-{}", args.stage, if args.live { "live" } else { "dry" }));
    let gate = alpenglow::require_active(&rpc).await?;
    let genesis = rpc.genesis_hash().await?;
    if args.require_mainnet && genesis != MAINNET_GENESIS_HASH {
        bail!("RPC genesis {genesis} is not mainnet-beta ({MAINNET_GENESIS_HASH}); pass --allow-non-mainnet only for localnet tests");
    }
    let not_after_ns = args.not_after_unix.map(|s| s as i64 * 1_000_000_000);
    if not_after_ns.is_some_and(|t| clock.now_unix_ns() >= t) {
        bail!("campaign cutoff (--not-after) has passed");
    }

    // ---- the frozen design ----
    let design_bytes = std::fs::read(&args.design).with_context(|| format!("reading {}", args.design.display()))?;
    let design_sha = format!("{:x}", Sha256::digest(&design_bytes));
    if let Some(expected) = &args.design_sha256 {
        if !expected.eq_ignore_ascii_case(&design_sha) {
            bail!("design sha256 {design_sha} does not match the pre-registered {expected}");
        }
    }
    let all_plans: Vec<WindowPlan> =
        String::from_utf8(design_bytes)?.lines().filter(|l| !l.trim().is_empty()).map(serde_json::from_str).collect::<std::result::Result<_, _>>()?;
    design::validate(&all_plans)?;
    let mut plans: BTreeMap<String, Vec<WindowPlan>> = BTreeMap::new();
    for p in all_plans {
        if p.stage == args.stage && (args.targets.is_empty() || args.targets.contains(&p.target_identity)) {
            plans.entry(p.target_identity.clone()).or_default().push(p);
        }
    }
    let progress = load_progress(&args.progress, args.live)?;
    for (t, ps) in plans.iter_mut() {
        ps.sort_by_key(|p| p.seq);
        let done = progress.claimed.get(t).cloned().unwrap_or_default();
        ps.retain(|p| !done.contains(&p.seq));
    }
    plans.retain(|_, ps| !ps.is_empty());
    if plans.is_empty() {
        bail!("nothing left to run for stage {}", args.stage);
    }
    let max_probes = plans.values().flatten().map(design::probe_count).max().unwrap_or(0);

    // ---- live prerequisites ----
    let _campaign_lock = if args.live { Some(CampaignLock::acquire(&args.ledger, &run_id)?) } else { None };
    let run = Arc::new(RunDir::create(args.out.join(&run_id))?);
    std::fs::create_dir_all(run.path.join("gossip"))?;
    let (live, pool) = if args.live {
        let cap = sol_to_lamports(args.max_spend_sol.context("--live requires --max-spend-sol")?)?;
        let ledger = Arc::new(Ledger::open(&args.ledger, cap)?);
        let auth = Arc::new(LiveAuthorization::grant(true, args.max_spend_sol, &gate, &ledger)?);
        if let Some(b) = args.budget_cap_sol {
            ledger.define_budget(&args.budget, sol_to_lamports(b)?)?;
        }
        let master = read_keypair(args.keypair.as_deref().context("--live requires --keypair")?)?.pubkey();
        let pool = PayerPool::new(load_payers(&args.payer_dir)?, Some(&master), &ledger.leased_payers()?)?;
        if pool.keys.len() < max_probes * 2 {
            bail!("payer pool has {} keys; need at least {} (two windows in flight)", pool.keys.len(), max_probes * 2);
        }
        let owned: Vec<String> = std::iter::once(master.to_string()).chain(pool.keys.iter().map(|k| k.pubkey().to_string())).collect();
        let current: u64 = rpc.balances(&owned).await?.iter().sum();
        let opening = ledger.campaign_opening(&owned, current)?;
        reconcile(opening, ledger.external_deposits()?, current, ledger.totals()?.committed(), cap, RECONCILE_TOLERANCE_LAMPORTS)?;
        (Some(Live { auth, ledger, budget: args.budget.clone(), owned, opening }), Arc::new(pool))
    } else {
        let keys = (0..max_probes * 3).map(|_| Keypair::new()).collect();
        (None, Arc::new(PayerPool::new(keys, None, &HashSet::new())?))
    };
    let live = live.map(Arc::new);

    // ---- gossip snapshots every 60 s; the current endpoint of each target is refreshed from them ----
    let target_ids: Vec<String> = plans.keys().cloned().collect();
    let current_state: Arc<RwLock<HashMap<String, Validator>>> = Arc::new(RwLock::new(HashMap::new()));
    let states = Arc::new(run.jsonl("target_states.jsonl")?);
    let snapshot_once = {
        let (rpc, run, states, ids, cur) = (rpc.clone(), run.clone(), states.clone(), target_ids.clone(), current_state.clone());
        move || {
            let (rpc, run, states, ids, cur) = (rpc.clone(), run.clone(), states.clone(), ids.clone(), cur.clone());
            async move {
                let (vals, raw) = targets::snapshot(&rpc).await?;
                let at = clock.now_unix_ns();
                run.write_zst(&format!("gossip/{at}.json.zst"), &raw)?;
                let mut map = cur.write().expect("state lock");
                for id in &ids {
                    let v = vals.iter().find(|v| &v.identity == id);
                    states.append(&json!({"at_unix_ns": at, "identity": id, "state": v}))?;
                    match v {
                        Some(v) => {
                            map.insert(id.clone(), v.clone());
                        }
                        None => {
                            map.remove(id);
                        }
                    }
                }
                anyhow::Ok(())
            }
        }
    };
    snapshot_once().await?;
    {
        let snap = snapshot_once.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(60)).await;
                if let Err(e) = snap().await {
                    tracing::warn!(error = %e, "gossip snapshot failed");
                }
            }
        });
    }

    let slot_clock = SlotClock::start(ws_url, clock, args.nominal_slot_ms, args.anchor_event).await?;
    let quic = Arc::new(QuicClient::new(clock)?);
    let logs = Arc::new(Logs {
        probes: run.jsonl("probes.jsonl")?,
        sends: run.jsonl("sends.jsonl")?,
        windows: run.jsonl("windows.jsonl")?,
        outcomes: run.jsonl("outcomes.jsonl")?,
        progress: Jsonl::open(&args.progress)?,
    });

    run.write_json("run_start.json", &json!({
        "run_id": run_id, "mode": if args.live { "live" } else { "dry_run" }, "stage": args.stage,
        "started_at": utc_now_rfc3339(), "rpc": redact_url(rpc.url()), "ws": redact_url(ws_url), "genesis_hash": genesis,
        "alpenglow": gate, "design_file": args.design, "design_sha256": design_sha, "obs_lag_ms": args.obs_lag_ms,
        "anchor_event": args.anchor_event, "max_lateness_ms": args.max_lateness_ms, "budget": args.budget,
        "not_after_unix": args.not_after_unix, "tpu_override": args.tpu_override, "targets": target_ids,
        "campaign_opening_lamports": live.as_ref().map(|l| l.opening), "itb_version": env!("CARGO_PKG_VERSION"),
    }))?;

    // Warm-up: the cadence estimate needs a few window hand-overs before anchors and estimates are trustworthy.
    let warm_deadline = tokio::time::Instant::now() + Duration::from_secs(90);
    while slot_clock.cadence().samples_boundary < 8 && tokio::time::Instant::now() < warm_deadline {
        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    let informative: Arc<Mutex<HashMap<String, [u32; 3]>>> = Arc::new(Mutex::new(progress.informative));
    let in_flight: Arc<Mutex<HashSet<String>>> = Arc::new(Mutex::new(HashSet::new()));
    let deadline = tokio::time::Instant::now() + Duration::from_secs(args.max_minutes * 60);
    let semaphore = Arc::new(tokio::sync::Semaphore::new(args.concurrency.max(1)));
    let mut handles = vec![];
    let mut windows_started = 0usize;
    let mut next_from: HashMap<String, u64> = HashMap::new();
    let mut schedule = ScheduleCache::default();

    loop {
        if windows_started >= args.max_windows || tokio::time::Instant::now() >= deadline {
            break;
        }
        if not_after_ns.is_some_and(|t| clock.now_unix_ns() >= t) {
            tracing::warn!("campaign cutoff reached; no more windows");
            break;
        }
        // Stage-1 stopping (PREREGISTRATION §5).
        for (t, ps) in plans.iter_mut() {
            if args.stage == 1
                && ps.first().is_some_and(|p| {
                    let need = design::informative_target(&p.tier);
                    informative.lock().expect("informative").get(t).is_some_and(|c| c.iter().all(|n| *n >= need))
                })
            {
                tracing::info!(target = %t, "stage-1 informative target reached; no more windows for this target");
                ps.clear();
            }
        }
        if plans.values().all(|ps| ps.is_empty()) {
            break;
        }
        // Next upcoming window across targets that have plans and no window in flight.
        let now_slot = slot_clock.latest_slot();
        let busy: HashSet<String> = in_flight.lock().expect("in flight").clone();
        let mut best: Option<(u64, u64, String)> = None;
        for (t, ps) in &plans {
            if ps.is_empty() || busy.contains(t) {
                continue;
            }
            let from = (*next_from.get(t).unwrap_or(&0)).max(now_slot + 40);
            if let Some((s, e)) = schedule.upcoming(&rpc, t, from).await? {
                if best.as_ref().is_none_or(|b| s < b.0) {
                    best = Some((s, e, t.clone()));
                }
            }
        }
        let Some((first, last, target)) = best else {
            tokio::time::sleep(Duration::from_millis(500)).await;
            continue;
        };
        next_from.insert(target.clone(), last + 1);
        let plan = plans.get_mut(&target).expect("target").remove(0);
        let permit = semaphore.clone().acquire_owned().await?;
        in_flight.lock().expect("in flight").insert(target.clone());
        windows_started += 1;
        let ctx = WindowCtx {
            rpc: rpc.clone(),
            quic: quic.clone(),
            slot_clock: slot_clock.clone(),
            clock,
            pool: pool.clone(),
            live: live.clone(),
            run_id: run_id.clone(),
            logs: logs.clone(),
            run: run.clone(),
            obs_lag_ms: args.obs_lag_ms,
            max_lateness_ms: args.max_lateness_ms,
            not_after_ns,
            informative: informative.clone(),
            current_state: current_state.clone(),
            tpu_override: args.tpu_override,
        };
        let in_flight = in_flight.clone();
        handles.push(tokio::spawn(async move {
            let t = plan.target_identity.clone();
            let r = execute_window(ctx, plan, (first, last)).await;
            in_flight.lock().expect("in flight").remove(&t);
            drop(permit);
            if let Err(e) = r {
                tracing::error!(target = %t, error = %e, "window failed");
            }
        }));
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    for h in handles {
        let _ = h.await;
    }

    let mut summary = json!({"run_id": run_id, "windows_started": windows_started, "finished_at": utc_now_rfc3339(),
                             "cadence": slot_clock.cadence(), "anchor_event": slot_clock.anchor_kind(),
                             "payers_still_leased": pool.busy_count()});
    if let Some(l) = &live {
        let current: u64 = rpc.balances(&l.owned).await?.iter().sum();
        let t = l.ledger.totals()?;
        summary["owned_lamports_drop_since_campaign_opening"] =
            json!(reconcile(l.opening, l.ledger.external_deposits()?, current, t.committed(), t.cap, RECONCILE_TOLERANCE_LAMPORTS)?);
        summary["ledger"] = serde_json::to_value(t)?;
    }
    quic.close_all().await;
    run.write_zst("slot_events.json.zst", &slot_clock.take_events())?;
    run.write_json("run_end.json", &summary)?;
    eprintln!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}

struct WindowCtx {
    rpc: Arc<Rpc>,
    quic: Arc<QuicClient>,
    slot_clock: SlotClock,
    clock: RunClock,
    pool: Arc<PayerPool>,
    live: Option<Arc<Live>>,
    run_id: String,
    logs: Arc<Logs>,
    run: Arc<RunDir>,
    obs_lag_ms: f64,
    max_lateness_ms: f64,
    not_after_ns: Option<i64>,
    informative: Arc<Mutex<HashMap<String, [u32; 3]>>>,
    current_state: Arc<RwLock<HashMap<String, Validator>>>,
    tpu_override: Option<SocketAddr>,
}

struct Pending {
    probe_id: String,
    signature: String,
    payer_idx: usize,
    wire: Vec<u8>,
    anchor: Anchor,
    nominal_ms: f64,
    reservation: Reservation,
}

async fn wait_slot_bounded(sc: &SlotClock, slot: u64) -> Result<()> {
    let expected_ms = sc.estimate_unix_ns(slot).map(|t| (t - sc_now(sc)) / 1_000_000).unwrap_or(0).max(0) as u64;
    tokio::time::timeout(Duration::from_millis(expected_ms + 30_000), sc.wait_for_slot(slot))
        .await
        .map_err(|_| anyhow::anyhow!("slot stream stalled waiting for slot {slot}"))?
}

fn sc_now(_sc: &SlotClock) -> i64 {
    RunClock::new().now_unix_ns()
}

async fn execute_window(ctx: WindowCtx, plan: WindowPlan, window: (u64, u64)) -> Result<()> {
    let target = plan.target_identity.clone();
    let cadence = ctx.slot_clock.cadence();
    let slot_ms = cadence.mean_slot_ms();
    let nominal = |offset: f64| plan.burst_offset_ms + offset - ctx.obs_lag_ms;
    let earliest_ms = plan.pairs.iter().flat_map(|p| &p.members).map(|m| nominal(m.send_offset_ms)).fold(0.0f64, f64::min);
    let prep_slots = (((-earliest_ms).max(0.0) + 1_500.0) / slot_ms).ceil() as u64;
    let mut row = json!({
        "run_id": ctx.run_id, "target_identity": target, "tier": plan.tier, "seq": plan.seq, "stage": plan.stage,
        "kit": plan.kit, "regime": plan.regime, "burst_offset_ms": plan.burst_offset_ms, "obs_lag_ms": ctx.obs_lag_ms,
        "window_first_slot": window.0, "window_last_slot": window.1, "cadence_at_prep": cadence,
        "planned_probes": design::probe_count(&plan), "live": ctx.live.is_some(),
    });
    let skip = |row: &mut serde_json::Value, reason: &str| -> Result<()> {
        row["skipped"] = json!(reason);
        ctx.logs.windows.append(row)
    };

    if let Err(e) = wait_slot_bounded(&ctx.slot_clock, window.0.saturating_sub(prep_slots + 12)).await {
        return skip(&mut row, &format!("before_connect: {e}"));
    }
    // The endpoint actually used comes from the latest gossip snapshot, not the run's start.
    let Some(mut v) = ctx.current_state.read().expect("state lock").get(&target).cloned() else {
        return skip(&mut row, "target_not_in_latest_gossip");
    };
    if let Some(o) = ctx.tpu_override {
        v.tpu_quic = Some(o.to_string());
    }
    row["client_id"] = json!(v.client_id);
    row["ingress"] = json!(v.ingress);
    row["tpu_quic"] = json!(v.tpu_quic);
    row["version"] = json!(v.version);
    let Some(addr) = v.tpu_addr() else { return skip(&mut row, "no_tpu_quic") };
    let connect: ConnectReport = ctx.quic.connect(addr).await;
    row["connect"] = serde_json::to_value(&connect)?;
    if ctx.live.is_some() && connect.error.is_some() {
        return skip(&mut row, "connect_failed");
    }

    if let Err(e) = wait_slot_bounded(&ctx.slot_clock, window.0.saturating_sub(prep_slots)).await {
        return skip(&mut row, &format!("before_prepare: {e}"));
    }
    let bh = if plan.blockhash_age_slots > 0 {
        ctx.rpc.aged_blockhash(plan.blockhash_age_slots.saturating_sub(prep_slots)).await?
    } else {
        ctx.rpc.latest_blockhash().await?
    };
    let est_start = ctx.slot_clock.estimate_unix_ns(window.0).context("no slot estimate")?;
    row["estimated_window_start_unix_ns"] = json!(est_start);
    row["blockhash_slot"] = json!(bh.slot);
    row["last_valid_block_height"] = json!(bh.last_valid_block_height);

    let n = design::probe_count(&plan);
    let seed = window_seed(&ctx.run_id, &target, plan.seq);
    let mut rng = rand_chacha::ChaCha20Rng::seed_from_u64(seed);
    let Some(payer_idx) = ctx.pool.take(n, &mut rng) else { return skip(&mut row, "payer_pool_exhausted") };
    row["payer_assignment_seed"] = json!(seed);

    // Build and sign every probe; log the signed realisation before anything is sent.
    let budget = ctx.live.as_ref().map(|l| l.budget.clone()).unwrap_or_default();
    let mut pending = vec![];
    let mut k = 0usize;
    for pair in &plan.pairs {
        for (pos, m) in pair.members.iter().enumerate() {
            let pi = payer_idx[k];
            let payer = ctx.pool.keys[pi].clone();
            k += 1;
            let lock = lock_for(&ctx.run_id, &target, plan.seq, m.lock_index);
            let tx = m.template.build(&payer, &lock, bh.blockhash.clone());
            let wire = bincode::serialize(&tx)?;
            let signature = tx.signatures[0].to_string();
            let nominal_ms = nominal(m.send_offset_ms);
            let anchor = anchor_for(nominal_ms);
            let probe_id = format!("{}/{}", pair.pair_id, m.label);
            ctx.logs.probes.append(&ProbeRecord {
                run_id: &ctx.run_id,
                probe_id: probe_id.clone(),
                target_identity: &target,
                seq: plan.seq,
                stage: plan.stage,
                tier: &plan.tier,
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
            let reservation = Reservation {
                signature: signature.clone(),
                kind: Kind::Probe,
                label: format!("{}/{probe_id}", ctx.run_id),
                max_fee: m.template.total_fee(),
                payer: payer.pubkey().to_string(),
                last_valid_block_height: bh.last_valid_block_height,
                budget: budget.clone(),
            };
            pending.push(Pending { probe_id, signature, payer_idx: pi, wire, anchor, nominal_ms, reservation });
        }
    }

    // Durable claim: from here on this plan is consumed, whatever happens.
    ctx.logs.progress.append_durable(&json!({"state": "claimed", "run_id": ctx.run_id, "target_identity": target,
                                             "seq": plan.seq, "live": ctx.live.is_some(), "at": utc_now_rfc3339()}))?;

    let mut not_sent: HashMap<String, String> = HashMap::new();
    let mut transport_errors: HashMap<String, String> = HashMap::new();
    let mut anchors = serde_json::Map::new();
    let max_late = Duration::from_micros((ctx.max_lateness_ms * 1000.0) as u64);
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
            json!({"slot": anchor_slot, "anchor_unix_ns": anchor_ns, "observed": observed, "extra_ms": extra_ms,
                   "event": ctx.slot_clock.anchor_kind()}),
        );
        let mark = |reason: &str, not_sent: &mut HashMap<String, String>| {
            for p in &items {
                not_sent.insert(p.probe_id.clone(), reason.to_string());
            }
        };
        if phase != Anchor::Estimate && !observed {
            mark("anchor_missed", &mut not_sent);
            continue;
        }
        let outgoing: Vec<Outgoing> = items
            .iter()
            .map(|p| {
                let at_ns = anchor_ns + ((extra_ms + p.nominal_ms) * 1e6) as i64;
                let at = tokio::time::Instant::from_std(ctx.clock.unix_ns_to_instant(at_ns));
                Outgoing { probe_id: p.probe_id.clone(), wire: p.wire.clone(), at, deadline: at + max_late }
            })
            .collect();
        let earliest = outgoing.iter().map(|o| o.at).min().expect("non-empty");
        if tokio::time::Instant::now() > earliest + max_late {
            mark("late", &mut not_sent);
            continue;
        }
        if ctx.not_after_ns.is_some_and(|t| ctx.clock.now_unix_ns() >= t) {
            mark("campaign_cutoff", &mut not_sent);
            continue;
        }
        match &ctx.live {
            Some(l) => {
                let batch: Vec<Reservation> = items.iter().map(|p| p.reservation.clone()).collect();
                if let Err(e) = l.ledger.reserve_batch(&batch) {
                    tracing::warn!(error = %e, "phase not reserved; not sending it");
                    mark("not_reserved", &mut not_sent);
                    continue;
                }
                let records = ctx.quic.send_scheduled(&l.auth, addr, outgoing).await;
                for r in &records {
                    ctx.logs.sends.append(&json!({"run_id": ctx.run_id, "dry_run": false, "record": r}))?;
                    let sig = &items.iter().find(|p| p.probe_id == r.probe_id).expect("item").signature;
                    if r.never_opened {
                        // Provably never left this process: release its reservation.
                        l.ledger.cancel_unsent(sig)?;
                        not_sent.insert(r.probe_id.clone(), r.error.clone().unwrap_or_else(|| "never_opened".into()));
                    } else if let Some(e) = &r.error {
                        transport_errors.insert(r.probe_id.clone(), e.clone());
                    }
                }
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
    row["not_sent_reasons"] = json!(not_sent);
    row["transport_errors"] = json!(transport_errors.len());
    row["sent_ok"] = json!(if ctx.live.is_some() { pending.len() - not_sent.len() - transport_errors.len() } else { 0 });

    // Which of the window's slots the target actually produced (eligibility criterion (c)).
    tokio::time::sleep(Duration::from_secs(3)).await;
    let produced = match ctx.rpc.blocks_in_range(window.0, window.1).await {
        Ok(slots) => {
            row["produced_slots"] = json!(slots);
            Some(!slots.is_empty())
        }
        Err(e) => {
            row["produced_slots_error"] = json!(e.to_string());
            None
        }
    };
    ctx.logs.windows.append(&row)?;

    let mut informative_pairs = [0u32; 3];
    let mut release: Vec<usize> = pending.iter().filter(|p| not_sent.contains_key(&p.probe_id)).map(|p| p.payer_idx).collect();
    if let Some(l) = &ctx.live {
        let tracked: Vec<Tracked> = pending
            .iter()
            .map(|p| Tracked {
                probe_id: p.probe_id.clone(),
                signature: p.signature.clone(),
                target_identity: target.clone(),
                window_first_slot: window.0,
                window_last_slot: window.1,
                last_valid_block_height: bh.last_valid_block_height,
                max_fee: p.reservation.max_fee,
                transport_error: transport_errors.get(&p.probe_id).cloned().or_else(|| not_sent.get(&p.probe_id).map(|r| format!("not_sent: {r}"))),
            })
            .collect();
        let (unsent, sent): (Vec<Tracked>, Vec<Tracked>) = tracked.into_iter().partition(|t| not_sent.contains_key(&t.probe_id));
        let mut outcomes = collect::resolve(&ctx.rpc, Some(&l.ledger), &sent, Some(&ctx.run), Duration::from_secs(90)).await?;
        outcomes.extend(unsent.iter().map(collect::not_sent_outcome));
        for o in &outcomes {
            ctx.logs.outcomes.append(&json!({"run_id": ctx.run_id, "outcome": o}))?;
        }
        // Payers of terminal outcomes are free again; unresolved ones stay leased (also in the ledger).
        for p in &pending {
            if outcomes.iter().any(|o| o.probe_id == p.probe_id && o.status.is_terminal() && o.status != Status::NotSent) {
                release.push(p.payer_idx);
            }
        }
        // Shared stopping definition (PREREGISTRATION §5): all planned probes sent without transport error, the target
        // produced a block in the window, and both members of the pair landed in the window (verified in the block).
        let window_ok = not_sent.is_empty() && transport_errors.is_empty() && produced == Some(true);
        if plan.kit == Kit::K && window_ok {
            let landed: HashSet<&str> = outcomes.iter().filter(|o| o.status == Status::LandedTarget).map(|o| o.probe_id.as_str()).collect();
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
            let e = inf.entry(target.clone()).or_default();
            for (acc, n) in e.iter_mut().zip(informative_pairs) {
                *acc += n;
            }
        }
        let current: u64 = ctx.rpc.balances(&l.owned).await?.iter().sum();
        let t = l.ledger.totals()?;
        reconcile(l.opening, l.ledger.external_deposits()?, current, t.committed(), t.cap, RECONCILE_TOLERANCE_LAMPORTS)?;
    } else {
        release.extend(pending.iter().map(|p| p.payer_idx));
    }
    ctx.pool.release(release);
    ctx.logs.progress.append_durable(&json!({"state": "terminal", "run_id": ctx.run_id, "target_identity": target, "seq": plan.seq,
                                             "live": ctx.live.is_some(), "informative_pairs": informative_pairs,
                                             "at": utc_now_rfc3339()}))?;
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

    fn rng(seed: u64) -> rand_chacha::ChaCha20Rng {
        rand_chacha::ChaCha20Rng::seed_from_u64(seed)
    }

    #[test]
    fn payer_pool_leases_shuffles_and_rejects_duplicates() {
        let keys: Vec<Keypair> = (0..10).map(|_| Keypair::new()).collect();
        let leased: HashSet<String> = [keys[0].pubkey().to_string()].into();
        let pool = PayerPool::new(keys, None, &leased).unwrap();
        let a = pool.take(8, &mut rng(1)).unwrap();
        assert!(!a.contains(&0), "leased payer from the ledger is never handed out");
        assert!(pool.take(2, &mut rng(2)).is_none(), "only 1 free");
        pool.release(a.clone());
        let b = pool.take(8, &mut rng(3)).unwrap();
        assert_ne!(a, b, "assignment is randomised");

        let k = Keypair::new();
        let dup = vec![k.insecure_clone(), k.insecure_clone()];
        assert!(PayerPool::new(dup, None, &HashSet::new()).is_err());
        let m = Keypair::new();
        assert!(PayerPool::new(vec![m.insecure_clone()], Some(&m.pubkey()), &HashSet::new()).is_err());
    }

    #[test]
    fn progress_separates_dry_and_live_and_counts_only_terminal() {
        let dir = std::env::temp_dir().join(format!("itb-progress-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("progress.jsonl");
        std::fs::write(
            &p,
            [
                r#"{"state":"claimed","target_identity":"T","seq":0,"live":false}"#,
                r#"{"state":"claimed","target_identity":"T","seq":1,"live":true}"#,
                r#"{"state":"claimed","target_identity":"T","seq":2,"live":true}"#,
                r#"{"state":"terminal","target_identity":"T","seq":2,"live":true,"informative_pairs":[1,1,0]}"#,
            ]
            .join("\n"),
        )
        .unwrap();
        let live = load_progress(&p, true).unwrap();
        assert_eq!(live.claimed["T"], [1, 2].into(), "dry-run claims never consume live plans; a crashed claim does");
        assert_eq!(live.informative["T"], [1, 1, 0]);
        let dry = load_progress(&p, false).unwrap();
        assert_eq!(dry.claimed["T"], [0].into());
    }

    #[test]
    fn campaign_lock_is_exclusive() {
        let dir = std::env::temp_dir().join(format!("itb-lock-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        let ledger = dir.join("ledger.sqlite");
        let a = CampaignLock::acquire(&ledger, "run-a").unwrap();
        assert!(CampaignLock::acquire(&ledger, "run-b").is_err());
        drop(a);
        assert!(CampaignLock::acquire(&ledger, "run-c").is_ok());
    }
}
