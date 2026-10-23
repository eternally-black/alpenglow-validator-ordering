//! Turns sent signatures into outcomes (PLAN §4.1) and archives the blocks they landed in.
//!
//! Status taxonomy: `landed_target`, `spillover_same_validator_later`, `spillover_other_leader`,
//! `expired_confirmed` (last valid block height finalized and the signature still unknown), `unresolved`
//! (we could not prove either way before the timeout). Unknown outcomes stay charged in the spend ledger.

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
    pub transport_error: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    LandedTarget,
    SpilloverSameValidatorLater,
    SpilloverOtherLeader,
    ExpiredConfirmed,
    Unresolved,
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
    pub transport_error: Option<String>,
}

/// Finds `signature` in a raw `getBlock` result: (index, meta).
pub fn locate(block: &Value, signature: &str) -> Option<(usize, Value)> {
    block["transactions"].as_array()?.iter().enumerate().find_map(|(i, tx)| {
        let sig = tx["transaction"]["signatures"].get(0)?.as_str()?;
        (sig == signature).then(|| (i, tx["meta"].clone()))
    })
}

pub async fn resolve(rpc: &Rpc, ledger: Option<&Ledger>, tracked: &[Tracked], run: &RunDir, timeout: Duration) -> Result<Vec<Outcome>> {
    let mut pending: Vec<&Tracked> = tracked.iter().collect();
    let mut landed: HashMap<String, u64> = HashMap::new();
    let mut expired: HashSet<String> = HashSet::new();
    let deadline = tokio::time::Instant::now() + timeout;

    while !pending.is_empty() && tokio::time::Instant::now() < deadline {
        let sigs: Vec<String> = pending.iter().map(|t| t.signature.clone()).collect();
        let statuses = rpc.signature_statuses(&sigs).await?;
        let finalized_height = rpc.get_block_height("finalized").await?;
        let mut still = vec![];
        for (t, st) in pending.into_iter().zip(statuses) {
            match st {
                Some(s) => {
                    landed.insert(t.signature.clone(), s.slot);
                }
                None if finalized_height > t.last_valid_block_height => {
                    expired.insert(t.signature.clone());
                }
                None => still.push(t),
            }
        }
        pending = still;
        if !pending.is_empty() {
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
    }

    // Fetch each landing block once; archive it verbatim.
    let mut blocks: HashMap<u64, Option<Value>> = HashMap::new();
    let mut leaders: HashMap<u64, String> = HashMap::new();
    for slot in landed.values().copied().collect::<HashSet<_>>() {
        let mut block = None;
        for _ in 0..10 {
            block = rpc.block_raw(slot, "confirmed").await?;
            if block.is_some() {
                break;
            }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        if let Some(b) = &block {
            let path = run.path.join("blocks").join(format!("{slot}.json.zst"));
            if !path.exists() {
                write_zst(&path, b)?;
            }
        }
        blocks.insert(slot, block);
        if let Some(l) = rpc.slot_leaders(slot, 1).await?.into_iter().next() {
            leaders.insert(slot, l);
        }
    }

    let mut out = Vec::with_capacity(tracked.len());
    for t in tracked {
        let mut o = Outcome {
            probe_id: t.probe_id.clone(),
            signature: t.signature.clone(),
            status: Status::Unresolved,
            slot: None,
            index_in_block: None,
            block_tx_count: None,
            leader: None,
            fee: None,
            err: None,
            cost_units: None,
            compute_units_consumed: None,
            transport_error: t.transport_error.clone(),
        };
        if let Some(&slot) = landed.get(&t.signature) {
            o.slot = Some(slot);
            o.leader = leaders.get(&slot).cloned();
            let same_leader = o.leader.as_deref() == Some(t.target_identity.as_str());
            let in_window = (t.window_first_slot..=t.window_last_slot).contains(&slot);
            o.status = match (same_leader, in_window) {
                (true, true) => Status::LandedTarget,
                (true, false) => Status::SpilloverSameValidatorLater,
                _ => Status::SpilloverOtherLeader,
            };
            if let Some(Some(block)) = blocks.get(&slot) {
                o.block_tx_count = block["transactions"].as_array().map(Vec::len);
                if let Some((idx, meta)) = locate(block, &t.signature) {
                    o.index_in_block = Some(idx);
                    o.fee = meta["fee"].as_u64();
                    o.err = meta.get("err").filter(|e| !e.is_null()).cloned();
                    o.cost_units = meta["costUnits"].as_u64();
                    o.compute_units_consumed = meta["computeUnitsConsumed"].as_u64();
                }
            }
            if let (Some(l), Some(fee)) = (ledger, o.fee) {
                l.resolve_landed(&t.signature, fee)?;
            }
        } else if expired.contains(&t.signature) {
            o.status = Status::ExpiredConfirmed;
            if let Some(l) = ledger {
                l.resolve_expired(&t.signature)?;
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
}
