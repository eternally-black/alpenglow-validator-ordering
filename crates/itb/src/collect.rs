//! Turns sent signatures into outcomes (PREREGISTRATION §1) and archives the blocks they landed in.
//!
//! Status taxonomy:
//! - `landed_target` / `spillover_same_validator_other_window` / `spillover_other_leader`: the signature has a
//!   confirmed status **and** was found in the archived block (index, fee and metadata known);
//! - `landed_unverified`: confirmed status, but the block could not be fetched or did not contain the signature —
//!   charged in the ledger, never used as an ordering observation;
//! - `expired_confirmed`: a finalized block whose height is above the transaction's last valid height was observed
//!   *first* (slot and height from that one block), and a history-capable status lookup answered at or past that slot
//!   *afterwards* still returned nothing. This is a measurement status: the ledger keeps the fee charged anyway
//!   (`Ledger::expire_charged`), because a lookup from a lagging backend cannot prove past non-inclusion. Landings in
//!   the targeted window are cross-checked against the archived window blocks by the verifier;
//! - `unresolved`: neither could be proven before the timeout (stays charged in the ledger);
//! - `not_sent`: never put on the wire.

use crate::ledger::Ledger;
use crate::rpc::Rpc;
use crate::store::{RunDir, write_zst};
use anyhow::Result;
use serde::Serialize;
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::time::Duration;

#[derive(Debug, Clone, Serialize)]
pub struct Tracked {
    pub probe_id: String,
    pub signature: String,
    pub target_identity: String,
    pub window_first_slot: u64,
    pub window_last_slot: u64,
    pub last_valid_block_height: u64,
    pub max_fee: u64,
    pub transport_error: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    LandedTarget,
    SpilloverSameValidatorOtherWindow,
    SpilloverOtherLeader,
    LandedUnverified,
    ExpiredConfirmed,
    Unresolved,
    /// Never put on the wire (anchor missed, deadline passed, cap reached); cannot land.
    NotSent,
}

impl Status {
    pub fn is_terminal(self) -> bool {
        !matches!(self, Status::Unresolved)
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Outcome {
    pub probe_id: String,
    pub signature: String,
    pub status: Status,
    pub slot: Option<u64>,
    pub index_in_block: Option<usize>,
    pub block_tx_count: Option<usize>,
    pub leader: Option<String>,
    pub fee: Option<u64>,
    pub err: Option<Value>,
    pub cost_units: Option<u64>,
    pub compute_units_consumed: Option<u64>,
    pub confirmation_status: Option<String>,
    pub transport_error: Option<String>,
    /// How non-inclusion was proven: finalized height and the status response's context slot.
    pub expiry_evidence: Option<Value>,
}

fn blank(t: &Tracked, status: Status) -> Outcome {
    Outcome {
        probe_id: t.probe_id.clone(),
        signature: t.signature.clone(),
        status,
        slot: None,
        index_in_block: None,
        block_tx_count: None,
        leader: None,
        fee: None,
        err: None,
        cost_units: None,
        compute_units_consumed: None,
        confirmation_status: None,
        transport_error: t.transport_error.clone(),
        expiry_evidence: None,
    }
}

pub fn not_sent_outcome(t: &Tracked) -> Outcome {
    blank(t, Status::NotSent)
}

/// The archived form of a block (`blocks/<slot>.json.zst`, docs/DATA.md): every transaction's first signature in
/// block order, its fee, compute units consumed, cost units and failure flag, the leader's fee reward, the block's
/// identity fields, and the full JSON (transaction + meta) of our own probes keyed by index. About 30 KB compressed
/// instead of ~300 KB for the full block: enough to verify every claimed index offline, to check that no unclaimed
/// probe sits in a window block, and for block fullness and priority percentiles — the chain re-check (`verify
/// --source chain`) is the independent comparison against full blocks.
pub fn excerpt(block: &Value, ours: &HashSet<&str>) -> Value {
    let txs = block["transactions"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    let (mut sigs, mut fees, mut cus, mut costs, mut failed) =
        (vec![], vec![], vec![], vec![], vec![]);
    let mut probes = serde_json::Map::new();
    for (i, tx) in txs.iter().enumerate() {
        let sig = tx["transaction"]["signatures"][0]
            .as_str()
            .unwrap_or_default();
        if ours.contains(sig) {
            probes.insert(i.to_string(), tx.clone());
        }
        sigs.push(Value::from(sig));
        fees.push(tx["meta"]["fee"].clone());
        cus.push(tx["meta"]["computeUnitsConsumed"].clone());
        costs.push(tx["meta"]["costUnits"].clone());
        failed.push(Value::from(!tx["meta"]["err"].is_null()));
    }
    let fee_rewards: Vec<Value> = block["rewards"]
        .as_array()
        .map(|r| {
            r.iter()
                .filter(|x| x["rewardType"] == "Fee")
                .cloned()
                .collect()
        })
        .unwrap_or_default();
    serde_json::json!({
        "excerpt": 1, "blockhash": block["blockhash"], "previousBlockhash": block["previousBlockhash"],
        "parentSlot": block["parentSlot"], "blockHeight": block["blockHeight"], "blockTime": block["blockTime"],
        "rewards": fee_rewards, "tx_count": txs.len(), "signatures": sigs, "fees": fees, "compute_units": cus,
        "cost_units": costs, "failed": failed, "probe_transactions": probes,
    })
}

/// Archives the excerpt of `block` at `slot` into the run, unless that slot is archived already.
pub fn archive(run: &RunDir, slot: u64, block: &Value, ours: &HashSet<&str>) -> Result<()> {
    let path = run.path.join("blocks").join(format!("{slot}.json.zst"));
    if !path.exists() {
        write_zst(&path, &excerpt(block, ours))?;
    }
    Ok(())
}

/// Finds `signature` in a raw `getBlock` result: (index, meta).
pub fn locate(block: &Value, signature: &str) -> Option<(usize, Value)> {
    block["transactions"]
        .as_array()?
        .iter()
        .enumerate()
        .find_map(|(i, tx)| {
            let sig = tx["transaction"]["signatures"].get(0)?.as_str()?;
            (sig == signature).then(|| (i, tx["meta"].clone()))
        })
}

fn confirmed(st: &crate::rpc::SignatureStatus) -> bool {
    matches!(
        st.confirmation_status.as_deref(),
        Some("confirmed") | Some("finalized")
    )
}

pub async fn resolve(
    rpc: &Rpc,
    ledger: Option<&Ledger>,
    tracked: &[Tracked],
    run: Option<&RunDir>,
    timeout: Duration,
) -> Result<Vec<Outcome>> {
    let mut pending: Vec<&Tracked> = tracked.iter().collect();
    let mut landed: HashMap<String, (u64, Option<String>)> = HashMap::new();
    let mut expired: HashMap<String, Value> = HashMap::new();
    let deadline = tokio::time::Instant::now() + timeout;

    while !pending.is_empty() {
        let sigs: Vec<String> = pending.iter().map(|t| t.signature.clone()).collect();
        let (_, statuses) = rpc.signature_statuses(&sigs).await?;
        let mut still = vec![];
        for (t, st) in pending.into_iter().zip(statuses) {
            match st {
                Some(s) if confirmed(&s) => {
                    landed.insert(t.signature.clone(), (s.slot, s.confirmation_status.clone()));
                }
                _ => still.push(t), // unknown or only `processed`: keep waiting
            }
        }
        // Expiry protocol: barrier first (slot and height of one finalized block), fresh lookup second.
        let (fin_slot, fin_height) = rpc.finalized_barrier().await?;
        let (cands, keep): (Vec<&Tracked>, Vec<&Tracked>) = still
            .into_iter()
            .partition(|t| fin_height > t.last_valid_block_height);
        pending = keep;
        if !cands.is_empty() {
            let sigs: Vec<String> = cands.iter().map(|t| t.signature.clone()).collect();
            let (context_slot, statuses) = rpc.signature_statuses(&sigs).await?;
            for (t, st) in cands.into_iter().zip(statuses) {
                match st {
                    Some(s) if confirmed(&s) => {
                        landed.insert(t.signature.clone(), (s.slot, s.confirmation_status.clone()));
                    }
                    None if context_slot >= fin_slot => {
                        expired.insert(
                            t.signature.clone(),
                            serde_json::json!({"finalized_block_height": fin_height, "finalized_slot": fin_slot,
                                               "last_valid_block_height": t.last_valid_block_height,
                                               "status_context_slot": context_slot}),
                        );
                    }
                    _ => pending.push(t), // stale responder or still provisional: retry
                }
            }
        }
        if pending.is_empty() || tokio::time::Instant::now() >= deadline {
            break;
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }

    // Fetch each landing block once; archive its excerpt.
    let ours: HashSet<&str> = tracked.iter().map(|t| t.signature.as_str()).collect();
    let mut blocks: HashMap<u64, Option<Value>> = HashMap::new();
    let mut leaders: HashMap<u64, String> = HashMap::new();
    for slot in landed.values().map(|(s, _)| *s).collect::<HashSet<_>>() {
        let mut block = None;
        for _ in 0..10 {
            block = rpc.block_raw(slot, "confirmed").await?;
            if block.is_some() {
                break;
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        if let (Some(b), Some(run)) = (&block, run) {
            archive(run, slot, b, &ours)?;
        }
        blocks.insert(slot, block);
        if let Some(l) = rpc.slot_leaders(slot, 1).await?.into_iter().next() {
            leaders.insert(slot, l);
        }
    }

    let mut out = Vec::with_capacity(tracked.len());
    for t in tracked {
        let mut o = blank(t, Status::Unresolved);
        if let Some((slot, conf)) = landed.get(&t.signature) {
            o.slot = Some(*slot);
            o.confirmation_status = conf.clone();
            o.leader = leaders.get(slot).cloned();
            let found = blocks
                .get(slot)
                .and_then(|b| b.as_ref())
                .and_then(|b| locate(b, &t.signature).map(|(i, m)| (i, m, b)));
            match found {
                Some((idx, meta, block)) => {
                    let same_leader = o.leader.as_deref() == Some(t.target_identity.as_str());
                    let in_window = (t.window_first_slot..=t.window_last_slot).contains(slot);
                    o.status = match (same_leader, in_window) {
                        (true, true) => Status::LandedTarget,
                        (true, false) => Status::SpilloverSameValidatorOtherWindow,
                        _ => Status::SpilloverOtherLeader,
                    };
                    o.index_in_block = Some(idx);
                    o.block_tx_count = block["transactions"].as_array().map(Vec::len);
                    o.fee = meta["fee"].as_u64();
                    o.err = meta.get("err").filter(|e| !e.is_null()).cloned();
                    o.cost_units = meta["costUnits"].as_u64();
                    o.compute_units_consumed = meta["computeUnitsConsumed"].as_u64();
                }
                None => {
                    o.status = Status::LandedUnverified;
                    o.fee = rpc.transaction_fee(&t.signature).await.ok().flatten();
                }
            }
            if let Some(l) = ledger {
                // An unknown fee is charged at the worst case.
                l.resolve_landed(&t.signature, o.fee.unwrap_or(t.max_fee))?;
            }
        } else if let Some(ev) = expired.get(&t.signature) {
            o.status = Status::ExpiredConfirmed;
            o.expiry_evidence = Some(ev.clone());
            if let Some(l) = ledger {
                l.expire_charged(&t.signature)?; // payer free, fee still charged
            }
        }
        out.push(o);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn locates_signature_and_meta() {
        let block = json!({"transactions": [
            {"transaction": {"signatures": ["aaa"]}, "meta": {"fee": 5000}},
            {"transaction": {"signatures": ["bbb"]}, "meta": {"fee": 6000, "err": null, "costUnits": 2335}},
        ]});
        let (i, meta) = locate(&block, "bbb").unwrap();
        assert_eq!(i, 1);
        assert_eq!(meta["costUnits"], 2335);
        assert!(locate(&block, "ccc").is_none());
    }

    #[test]
    fn excerpt_keeps_order_costs_leader_and_our_transactions_only() {
        let block = json!({"blockhash": "H", "parentSlot": 9, "blockHeight": 7, "rewards": [
            {"pubkey": "L", "rewardType": "Fee", "lamports": 1}, {"pubkey": "V", "rewardType": "Voting"}],
        "transactions": [
            {"transaction": {"signatures": ["aaa"]}, "meta": {"fee": 5000, "err": null, "computeUnitsConsumed": 150}},
            {"transaction": {"signatures": ["ours"]}, "meta": {"fee": 6000, "err": null, "costUnits": 2335}},
            {"transaction": {"signatures": ["ccc"]}, "meta": {"fee": 7000, "err": {"x": 1}}},
        ]});
        let e = excerpt(&block, &HashSet::from(["ours"]));
        assert_eq!(e["signatures"], json!(["aaa", "ours", "ccc"]));
        assert_eq!(e["fees"], json!([5000, 6000, 7000]));
        assert_eq!(e["failed"], json!([false, false, true]));
        assert_eq!(e["tx_count"], 3);
        assert_eq!(
            e["rewards"],
            json!([{"pubkey": "L", "rewardType": "Fee", "lamports": 1}])
        );
        assert_eq!(e["probe_transactions"]["1"]["meta"]["costUnits"], 2335);
        assert!(
            e["probe_transactions"].get("0").is_none(),
            "other senders' transactions are not stored in full"
        );
    }

    #[test]
    fn only_confirmed_statuses_count_as_landed() {
        let st = |c: &str| crate::rpc::SignatureStatus {
            slot: 1,
            confirmations: None,
            err: None,
            confirmation_status: Some(c.into()),
        };
        assert!(confirmed(&st("confirmed")) && confirmed(&st("finalized")));
        assert!(!confirmed(&st("processed")));
    }
}
