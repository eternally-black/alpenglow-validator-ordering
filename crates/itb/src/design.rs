//! Frozen experimental design (PLAN §2.1, §2.4). Generated from a committed seed *before* any live send and written
//! to `design.jsonl`; its SHA-256 goes into the pre-registration. At run time the k-th attempted window of a target
//! executes the k-th plan in that target's list, so nothing about the treatment is decided after seeing data.
//!
//! Randomised per window: kit order (blocked), regime (blocked, by ingress kind), pair order inside the burst,
//! within-pair send order (balanced per contrast), race Δt (balanced). Payers are assigned at run time from the pool,
//! independently of treatment.

use crate::probe::{Template, library};
use crate::targets::IngressKind;
use rand::seq::SliceRandom;
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha20Rng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kit {
    /// Stage 1, primary: C1, C2, C3 contended pairs + one uncontended C2 pair, one burst.
    K,
    /// Stage 2: dominance races (Δt) + equal-key pairs.
    T,
    /// Stage 2, direct ingress: pre-window holding cliff (−0.5 s, −3 s, −5 s).
    H,
    /// Stage 2, shared ingress: spill-over map (−150 ms, −1 s).
    S,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Regime {
    /// Sent before the window so every probe is pending when the leader starts (direct ingress only).
    Buffered,
    /// Sent inside the window.
    Streaming,
    /// Deliberately early sends (H/S kits).
    PreWindow,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PairKind {
    C1,
    C2,
    C3,
    C2Uncontended,
    Race,
    EqualKey,
    Single,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MemberPlan {
    /// Library label: "A", "B", "A'", "hi", "lo".
    pub label: String,
    pub template: Template,
    /// Send time relative to the window's burst instant, ms (negative = earlier).
    pub send_offset_ms: f64,
    /// Members with the same lock index inside a window share a writable lock (forced sequential decision).
    pub lock_index: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PairPlan {
    pub pair_id: String,
    pub kind: PairKind,
    /// Members in *send* order (first element is sent first). The analysis recovers label vs send order from this.
    pub members: Vec<MemberPlan>,
    /// For pairs: which library label was sent first (redundant with `members[0].label`, kept for readability).
    pub first_sent_label: String,
    pub race_dt_ms: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowPlan {
    pub target_identity: String,
    /// "core" or "extended": sets the stage-1 stopping target (PREREGISTRATION §5).
    #[serde(default = "default_tier")]
    pub tier: String,
    pub seq: u32,
    pub stage: u8,
    pub kit: Kit,
    pub regime: Regime,
    /// Burst instant relative to the predicted (observed-frame) window start, ms.
    pub burst_offset_ms: f64,
    /// Blockhash age at send time in slots (aged ⇒ short expiry; H kits use a fresh one).
    pub blockhash_age_slots: u64,
    pub pairs: Vec<PairPlan>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TargetSpec {
    pub identity: String,
    pub client_id: String,
    pub ingress: IngressKind,
    pub tier: String,
    pub k_windows: u32,
    pub t_windows: u32,
    pub hs_windows: u32,
}

fn default_tier() -> String {
    "core".into()
}

/// Stage-1 stopping: a target is done once each of C1, C2, C3 has this many pairs with both members landed in the
/// targeted window. The design holds twice as many K-window plans so low landing rates can be compensated.
pub fn informative_target(tier: &str) -> u32 {
    if tier == "extended" { 20 } else { 40 }
}

pub const AGED_BLOCKHASH_SLOTS: u64 = 125;
pub const BUFFERED_OFFSET_MS: f64 = -150.0;
pub const STREAMING_DIRECT_OFFSET_MS: f64 = 60.0;
/// Observed post-Alpenglow cadence: ≈130 ms between first shreds inside a leader window (≈560 ms at hand-over).
pub const OBSERVED_INSIDE_SLOT_MS: f64 = 130.0;
pub const RACE_DTS_MS: [f64; 4] = [5.0, 25.0, 60.0, 100.0];
pub const EQUAL_KEY_DTS_MS: [f64; 2] = [10.0, 40.0];
/// Races start this far after the observed first shred of the target's first slot, so the longest race
/// (5 + 100 ms) ends before the next slot's first shred (≈130 ms). Crossings are still classified from the data.
pub const RACE_START_OFFSET_MS: f64 = 5.0;
/// Agave holds packets that arrive ≤ 20 slots before its window. 20 slots ≈ 4.7 s of real time at the observed
/// ≈235 ms/slot, so −3 s is safely inside the hold horizon and −7 s (≈30 slots) safely outside it.
pub const H_OFFSETS_MS: [f64; 3] = [-500.0, -3_000.0, -7_000.0];
pub const S_OFFSETS_MS: [f64; 2] = [-150.0, -1_000.0];

fn is_direct(ingress: IngressKind) -> bool {
    matches!(ingress, IngressKind::Direct)
}

fn is_firedancer(client_id: &str) -> bool {
    client_id == "Firedancer"
}

/// Balanced sequence of booleans (half true) in random order, for within-pair send order.
fn balanced_flags(n: usize, rng: &mut ChaCha20Rng) -> Vec<bool> {
    let mut v: Vec<bool> = (0..n).map(|i| i % 2 == 0).collect();
    v.shuffle(rng);
    v
}

#[allow(clippy::too_many_arguments)] // one call site per pair kind; a builder would only add noise
fn pair(
    pair_id: String,
    kind: PairKind,
    x: (&str, Template),
    y: (&str, Template),
    x_first: bool,
    dt_ms: f64,
    shared_lock: bool,
    lock_base: u32,
) -> PairPlan {
    let (first, second) = if x_first { (x, y) } else { (y, x) };
    let second_lock = if shared_lock {
        lock_base
    } else {
        lock_base + 1
    };
    PairPlan {
        pair_id,
        kind,
        first_sent_label: first.0.to_string(),
        race_dt_ms: matches!(kind, PairKind::Race | PairKind::EqualKey).then_some(dt_ms),
        members: vec![
            MemberPlan {
                label: first.0.into(),
                template: first.1,
                send_offset_ms: 0.0,
                lock_index: lock_base,
            },
            MemberPlan {
                label: second.0.into(),
                template: second.1,
                send_offset_ms: dt_ms,
                lock_index: second_lock,
            },
        ],
    }
}

/// Generates every window plan for every target. Deterministic in (`seed`, `targets`).
pub fn generate(seed: u64, targets: &[TargetSpec]) -> Vec<WindowPlan> {
    let mut out = vec![];
    for t in targets {
        let tseed = u64::from_le_bytes(
            Sha256::digest(format!("{seed}/{}", t.identity).as_bytes())[..8]
                .try_into()
                .expect("8 bytes"),
        );
        let mut rng = ChaCha20Rng::seed_from_u64(tseed);
        let direct = is_direct(t.ingress);
        let n_k = t.k_windows as usize;

        // ---- Stage 1: K windows ----
        // Regime blocks of 4 for direct ingress: 3 buffered + 1 streaming.
        let mut regimes: Vec<Regime> = (0..n_k)
            .map(|i| {
                if direct && i % 4 != 3 {
                    Regime::Buffered
                } else {
                    Regime::Streaming
                }
            })
            .collect();
        for block in regimes.chunks_mut(4) {
            block.shuffle(&mut rng);
        }
        let mut order_c1 = balanced_flags(n_k, &mut rng);
        let mut order_c2 = balanced_flags(n_k, &mut rng);
        let mut order_c3 = balanced_flags(n_k, &mut rng);
        let mut order_c2u = balanced_flags(n_k, &mut rng);
        for (seq, regime) in regimes.into_iter().enumerate() {
            let burst_offset_ms = match (regime, direct) {
                (Regime::Buffered, _) => BUFFERED_OFFSET_MS,
                (_, true) => STREAMING_DIRECT_OFFSET_MS,
                // Shared ingress: uniform in [40, 500] ms after the window's first shred, avoiding ±15 ms around the
                // observed in-window slot boundaries (k·130 ms).
                (_, false) => loop {
                    let x: f64 = rng.gen_range(40.0..500.0);
                    if [1.0, 2.0, 3.0]
                        .iter()
                        .all(|k| (x - k * OBSERVED_INSIDE_SLOT_MS).abs() > 15.0)
                    {
                        break x.round();
                    }
                },
            };
            let id = |p: &str| format!("{}/{seq:03}/{p}", &t.identity[..8]);
            let mut pairs = vec![
                pair(
                    id("c1"),
                    PairKind::C1,
                    ("A", library::A),
                    ("B", library::B),
                    order_c1.pop().unwrap(),
                    0.0,
                    true,
                    0,
                ),
                pair(
                    id("c2"),
                    PairKind::C2,
                    ("A'", library::A_PRIME),
                    ("B", library::B),
                    order_c2.pop().unwrap(),
                    0.0,
                    true,
                    2,
                ),
                pair(
                    id("c3"),
                    PairKind::C3,
                    ("A", library::A),
                    ("A'", library::A_PRIME),
                    order_c3.pop().unwrap(),
                    0.0,
                    true,
                    4,
                ),
                pair(
                    id("c2u"),
                    PairKind::C2Uncontended,
                    ("A'", library::A_PRIME),
                    ("B", library::B),
                    order_c2u.pop().unwrap(),
                    0.0,
                    false,
                    6,
                ),
            ];
            pairs.shuffle(&mut rng); // pair order inside the burst
            out.push(WindowPlan {
                target_identity: t.identity.clone(),
                tier: t.tier.clone(),
                seq: seq as u32,
                stage: 1,
                kit: Kit::K,
                regime,
                burst_offset_ms,
                blockhash_age_slots: AGED_BLOCKHASH_SLOTS,
                pairs,
            });
        }

        // ---- Stage 2: T windows, then H (direct) or S (shared) windows, interleaved at random ----
        let mut stage2: Vec<Kit> = std::iter::repeat_n(Kit::T, t.t_windows as usize)
            .chain(std::iter::repeat_n(
                if direct { Kit::H } else { Kit::S },
                t.hs_windows as usize,
            ))
            .collect();
        stage2.shuffle(&mut rng);
        let fd = is_firedancer(&t.client_id);
        let n_races = if fd { 2 } else { 3 };
        let n_equal = if fd { 2 } else { 1 };
        let n_t = t.t_windows as usize;
        let mut race_hi_first = balanced_flags(n_t * n_races, &mut rng);
        let mut equal_dt_cycle = (0..n_t * n_equal)
            .map(|i| EQUAL_KEY_DTS_MS[i % 2])
            .collect::<Vec<_>>();
        equal_dt_cycle.shuffle(&mut rng);
        for (k, kit) in stage2.into_iter().enumerate() {
            let seq = (n_k + k) as u32;
            let id = |p: &str| format!("{}/{seq:03}/{p}", &t.identity[..8]);
            let plan = match kit {
                Kit::T => {
                    let mut dts = RACE_DTS_MS.to_vec();
                    dts.shuffle(&mut rng);
                    let mut pairs = vec![];
                    for (r, dt) in dts.into_iter().take(n_races).enumerate() {
                        let mut p = pair(
                            id(&format!("race{r}")),
                            PairKind::Race,
                            ("hi", library::HI),
                            ("lo", library::LO),
                            race_hi_first.pop().unwrap(),
                            dt,
                            true,
                            (r * 2) as u32,
                        );
                        for m in &mut p.members {
                            m.send_offset_ms += RACE_START_OFFSET_MS;
                        }
                        pairs.push(p);
                    }
                    for e in 0..n_equal {
                        let dt = equal_dt_cycle.pop().unwrap();
                        let mut p = pair(
                            id(&format!("eq{e}")),
                            PairKind::EqualKey,
                            ("A", library::A),
                            ("A", library::A),
                            true,
                            dt,
                            true,
                            (10 + e * 2) as u32,
                        );
                        // Equal-key pairs go out in the buffered regime for direct ingress (both pending at slot start).
                        let base = if direct {
                            BUFFERED_OFFSET_MS
                        } else {
                            RACE_START_OFFSET_MS
                        };
                        for m in &mut p.members {
                            m.send_offset_ms += base;
                        }
                        p.members[1].label = "A#2".into();
                        pairs.push(p);
                    }
                    WindowPlan {
                        target_identity: t.identity.clone(),
                        tier: t.tier.clone(),
                        seq,
                        stage: 2,
                        kit,
                        regime: Regime::Streaming,
                        burst_offset_ms: 0.0,
                        blockhash_age_slots: AGED_BLOCKHASH_SLOTS,
                        pairs,
                    }
                }
                Kit::H | Kit::S => {
                    let offsets: &[f64] = if kit == Kit::H {
                        &H_OFFSETS_MS
                    } else {
                        &S_OFFSETS_MS
                    };
                    let pairs = offsets
                        .iter()
                        .enumerate()
                        .map(|(i, off)| PairPlan {
                            pair_id: id(&format!("pre{i}")),
                            kind: PairKind::Single,
                            first_sent_label: "A".into(),
                            race_dt_ms: None,
                            members: vec![MemberPlan {
                                label: "A".into(),
                                template: library::A,
                                send_offset_ms: *off,
                                lock_index: (20 + i) as u32,
                            }],
                        })
                        .collect();
                    WindowPlan {
                        target_identity: t.identity.clone(),
                        tier: t.tier.clone(),
                        seq,
                        stage: 2,
                        kit,
                        regime: Regime::PreWindow,
                        burst_offset_ms: 0.0,
                        // H needs the long horizon to observe the −5 s probe; S keeps the aged hash.
                        blockhash_age_slots: if kit == Kit::H {
                            0
                        } else {
                            AGED_BLOCKHASH_SLOTS
                        },
                        pairs,
                    }
                }
                Kit::K => unreachable!(),
            };
            out.push(plan);
        }
    }
    out
}

/// Structural checks before a design may be frozen or executed: unique (target, stage, seq) and pair ids, the
/// expected member count per pair kind, and templates above the CU floor.
pub fn validate(plans: &[WindowPlan]) -> anyhow::Result<()> {
    use std::collections::HashSet;
    let mut keys = HashSet::new();
    let mut pair_ids = HashSet::new();
    for p in plans {
        if !keys.insert((p.target_identity.clone(), p.stage, p.seq)) {
            anyhow::bail!("duplicate plan {}/{}/{}", p.target_identity, p.stage, p.seq);
        }
        for q in &p.pairs {
            if !pair_ids.insert((p.target_identity.clone(), q.pair_id.clone())) {
                anyhow::bail!("duplicate pair id {}", q.pair_id);
            }
            let expected = if q.kind == PairKind::Single { 1 } else { 2 };
            if q.members.len() != expected {
                anyhow::bail!(
                    "pair {} has {} members, expected {expected}",
                    q.pair_id,
                    q.members.len()
                );
            }
            for m in &q.members {
                if m.template.cu_limit < crate::probe::ATOM_EXECUTED_CU {
                    anyhow::bail!(
                        "pair {}: CU limit {} below the atom's {} CU",
                        q.pair_id,
                        m.template.cu_limit,
                        crate::probe::ATOM_EXECUTED_CU
                    );
                }
            }
        }
        if probe_count(p) > crate::quic::MAX_STREAMS_PER_100MS {
            anyhow::bail!(
                "plan {}/{} has {} probes > {} per burst",
                p.target_identity,
                p.seq,
                probe_count(p),
                crate::quic::MAX_STREAMS_PER_100MS
            );
        }
    }
    Ok(())
}

/// Worst-case fee of a plan: what the ledger will reserve.
pub fn max_fee(plan: &WindowPlan) -> u64 {
    plan.pairs
        .iter()
        .flat_map(|p| &p.members)
        .map(|m| m.template.total_fee())
        .sum()
}

pub fn probe_count(plan: &WindowPlan) -> usize {
    plan.pairs.iter().map(|p| p.members.len()).sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(id: &str, client: &str, ingress: IngressKind) -> TargetSpec {
        TargetSpec {
            identity: id.into(),
            client_id: client.into(),
            ingress,
            tier: "core".into(),
            k_windows: 40,
            t_windows: 16,
            hs_windows: 6,
        }
    }

    fn targets() -> Vec<TargetSpec> {
        vec![
            spec(
                "AGAVExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1",
                "Agave",
                IngressKind::Direct,
            ),
            spec(
                "FIREDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1",
                "Firedancer",
                IngressKind::Direct,
            ),
            spec(
                "BAMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1",
                "AgaveBam",
                IngressKind::BamNode,
            ),
        ]
    }

    #[test]
    fn deterministic_in_seed() {
        assert_eq!(generate(7, &targets()), generate(7, &targets()));
        assert_ne!(generate(7, &targets()), generate(8, &targets()));
    }

    #[test]
    fn window_counts_and_budget() {
        let plans = generate(1, &targets());
        assert_eq!(plans.len(), 3 * (40 + 16 + 6));
        for p in &plans {
            assert!(
                probe_count(p) <= crate::quic::MAX_STREAMS_PER_100MS,
                "{} probes",
                probe_count(p)
            );
        }
        let k = plans.iter().find(|p| p.kit == Kit::K).unwrap();
        assert_eq!(max_fee(k), 49_500);
        let t_agave = plans
            .iter()
            .find(|p| p.kit == Kit::T && p.target_identity.starts_with("AGAVE"))
            .unwrap();
        assert_eq!(max_fee(t_agave), 54_000);
        let t_fd = plans
            .iter()
            .find(|p| p.kit == Kit::T && p.target_identity.starts_with("FIRED"))
            .unwrap();
        assert_eq!(max_fee(t_fd), 52_000);
    }

    #[test]
    fn send_order_is_balanced_per_contrast() {
        let plans = generate(3, &targets());
        // x = the label listed first in the contrast table (PLAN §2.3).
        for (kind, x) in [
            (PairKind::C1, "A"),
            (PairKind::C2, "A'"),
            (PairKind::C3, "A"),
            (PairKind::C2Uncontended, "A'"),
        ] {
            let firsts: Vec<&str> = plans
                .iter()
                .filter(|p| p.target_identity.starts_with("BAM") && p.kit == Kit::K)
                .flat_map(|p| {
                    p.pairs
                        .iter()
                        .filter(|q| q.kind == kind)
                        .map(|q| q.first_sent_label.as_str())
                })
                .collect();
            let x_first = firsts.iter().filter(|l| **l == x).count();
            assert_eq!(x_first * 2, firsts.len(), "{kind:?} not balanced");
        }
    }

    #[test]
    fn regimes_follow_ingress_kind() {
        let plans = generate(5, &targets());
        let k_direct: Vec<_> = plans
            .iter()
            .filter(|p| p.kit == Kit::K && p.target_identity.starts_with("AGAVE"))
            .collect();
        let buffered = k_direct
            .iter()
            .filter(|p| p.regime == Regime::Buffered)
            .count();
        assert_eq!(buffered, 30); // 3 of every 4
        assert!(
            plans
                .iter()
                .filter(|p| p.target_identity.starts_with("BAM"))
                .all(|p| p.regime != Regime::Buffered)
        );
        assert!(
            plans
                .iter()
                .filter(|p| p.target_identity.starts_with("BAM"))
                .all(|p| p.kit != Kit::H)
        );
    }

    #[test]
    fn contended_pairs_share_a_lock_and_uncontended_do_not() {
        let plans = generate(9, &targets());
        for p in plans.iter().filter(|p| p.kit == Kit::K) {
            for q in &p.pairs {
                let same = q.members[0].lock_index == q.members[1].lock_index;
                assert_eq!(same, q.kind != PairKind::C2Uncontended, "{:?}", q.kind);
            }
            let mut locks: Vec<u32> = p
                .pairs
                .iter()
                .flat_map(|q| q.members.iter().map(|m| m.lock_index))
                .collect();
            locks.sort();
            locks.dedup();
            assert_eq!(locks.len(), 5, "pairs must not share locks with each other");
        }
    }

    #[test]
    fn races_stay_inside_one_observed_slot() {
        for p in generate(11, &targets()).iter().filter(|p| p.kit == Kit::T) {
            for q in p.pairs.iter().filter(|q| q.kind == PairKind::Race) {
                let end = q
                    .members
                    .iter()
                    .map(|m| m.send_offset_ms)
                    .fold(f64::MIN, f64::max);
                assert!(end < OBSERVED_INSIDE_SLOT_MS, "race ends at {end} ms");
            }
        }
    }

    #[test]
    fn generated_designs_validate_and_duplicates_are_rejected() {
        let plans = generate(13, &targets());
        validate(&plans).unwrap();
        let mut dup = plans.clone();
        dup.push(plans[0].clone());
        assert!(validate(&dup).is_err());
    }

    #[test]
    fn shared_offsets_avoid_observed_slot_boundaries() {
        for p in generate(17, &targets())
            .iter()
            .filter(|p| p.kit == Kit::K && p.target_identity.starts_with("BAM"))
        {
            for k in 1..=3 {
                assert!((p.burst_offset_ms - k as f64 * OBSERVED_INSIDE_SLOT_MS).abs() > 15.0);
            }
        }
    }
}
