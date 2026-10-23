//! `itb reconcile`: experiment recovery, not only accounting recovery. After a crash or a collection timeout, every
//! open reservation is resolved on chain evidence *and* written back where it belongs:
//! - each probe's outcome is appended to its original run's `outcomes.jsonl` (marked `recovered`), and its landing
//!   block is archived into that run's `blocks/`, from the provenance stored with the reservation;
//! - each restored window of an `itb run` gets a terminal record in the attempt journal with zero informative pairs.
//!   Recovery never adds to the stopping count: an under-count can only make the campaign attempt more of its frozen
//!   plans (bounded by the design), an over-count could stop it early on unverified evidence.
//!
//! Setup transactions (no provenance) are resolved for accounting only.

use crate::campaign::Campaign;
use crate::collect::{self, Tracked};
use crate::ledger::OpenReservation;
use crate::rpc::Rpc;
use crate::store::{Jsonl, RunDir, utc_now_rfc3339};
use anyhow::Result;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// `T8/seq/kind/label` → seq.
fn seq_of(probe_id: &str) -> Option<u32> {
    probe_id.split('/').nth(1)?.parse().ok()
}

fn tracked(r: &OpenReservation) -> Tracked {
    let p = r.provenance.as_ref();
    Tracked {
        probe_id: p.map_or_else(|| r.label.clone(), |p| p.probe_id.clone()),
        signature: r.signature.clone(),
        target_identity: p.map(|p| p.target_identity.clone()).unwrap_or_default(),
        window_first_slot: p.map_or(0, |p| p.window_first_slot),
        window_last_slot: p.map_or(0, |p| p.window_last_slot),
        last_valid_block_height: r.last_valid_block_height,
        max_fee: r.max_fee,
        transport_error: None,
    }
}

pub async fn reconcile(
    rpc: &Rpc,
    campaign: &Campaign,
    runs: &[PathBuf],
    progress: &Path,
) -> Result<serde_json::Value> {
    let open = campaign.ledger.open_reservations()?;
    let mut groups: BTreeMap<Option<String>, Vec<OpenReservation>> = BTreeMap::new();
    for r in open {
        groups
            .entry(r.provenance.as_ref().map(|p| p.run_id.clone()))
            .or_default()
            .push(r);
    }
    let journal = Jsonl::open(progress)?;
    let mut report = vec![];
    for (run_id, rs) in groups {
        let dir = run_id
            .as_ref()
            .and_then(|id| runs.iter().map(|root| root.join(id)).find(|d| d.is_dir()));
        let run = dir.map(RunDir::open_existing).transpose()?;
        let tracked: Vec<Tracked> = rs.iter().map(tracked).collect();
        let outcomes = collect::resolve(
            rpc,
            Some(&campaign.ledger),
            &tracked,
            run.as_ref(),
            Duration::from_secs(180),
        )
        .await?;
        let Some(run) = run else {
            for o in &outcomes {
                report.push(
                    json!({"run_id": run_id, "signature": o.signature, "status": o.status,
                                   "restored_into_run": false}),
                );
            }
            continue;
        };
        // `itb run` directories carry run_start.json and the wrapped outcome format; smoke runs write bare outcomes.
        let start: Option<serde_json::Value> =
            std::fs::read_to_string(run.path.join("run_start.json"))
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok());
        let out = run.jsonl("outcomes.jsonl")?;
        let at = utc_now_rfc3339();
        for o in &outcomes {
            let mut v = serde_json::to_value(o)?;
            v["recovered"] = json!(true);
            v["recovered_at"] = json!(at);
            if start.is_some() {
                out.append_durable(&json!({"run_id": run_id, "outcome": v, "recovered": true}))?;
            } else {
                out.append_durable(&v)?;
            }
            report.push(
                json!({"run_id": run_id, "signature": o.signature, "status": o.status,
                               "restored_into_run": true}),
            );
        }
        if let Some(start) = start {
            let windows: BTreeSet<(String, u32)> = tracked
                .iter()
                .filter_map(|t| Some((t.target_identity.clone(), seq_of(&t.probe_id)?)))
                .collect();
            for (target, seq) in windows {
                journal.append_durable(&json!({
                    "state": "terminal", "run_id": run_id, "target_identity": target, "seq": seq,
                    "live": start["mode"] == "live", "design_sha256": start["design_sha256"],
                    "budget": start["budget"], "informative_pairs": [0, 0, 0], "recovered": true, "at": at,
                }))?;
            }
        }
    }
    Ok(json!({"resolved": report, "ledger": campaign.ledger.totals()?}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seq_comes_from_the_pair_id() {
        assert_eq!(seq_of("7QQGNm3p/017/c1/A"), Some(17));
        assert_eq!(
            seq_of("7QQGNm3p-w1-p0"),
            None,
            "smoke probe ids carry no plan sequence"
        );
    }
}
