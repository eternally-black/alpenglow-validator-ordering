//! `itb smoke`: the cheapest mainnet question first (PLAN §7, Oct 24) — does each ingress kind accept unstaked QUIC
//! probes, and where do they land? Sends a few identical template-A probes into the next leader window of one or two
//! validators per mechanism group, then resolves every signature.
//!
//! Dry-run (default) does everything except putting transaction bytes on the wire: real leader schedule, gossip,
//! QUIC handshakes (reachability + RTT), signed probes, and a full would-send log.

use crate::alpenglow;
use crate::campaign::{Campaign, OpenArgs};
use crate::collect::{self, Tracked};
use crate::keys::read_keypair;
use crate::ledger::{Kind, Provenance, Reservation};
use crate::probe::library;
use crate::quic::{Outgoing, QuicClient};
use crate::rpc::{Rpc, redact_url};
use crate::store::{RunDir, new_run_id, utc_now_rfc3339};
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
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

pub struct SmokeArgs {
    pub live: bool,
    pub max_spend_sol: Option<f64>,
    pub ledger: PathBuf,
    pub keypair: Option<PathBuf>,
    /// Payer directory: part of the campaign's owned-account set even though smoke signs with the master.
    pub payer_dir: PathBuf,
    pub out: PathBuf,
    pub targets: Vec<String>,
    pub per_group: usize,
    pub probes: usize,
    pub offset_ms: i64,
    pub blockhash_age_slots: u64,
    pub max_targets: usize,
    pub budget_sol: f64,
}

#[derive(Serialize)]
struct PlannedProbe<'a> {
    probe_id: String,
    target_identity: &'a str,
    client_id: &'a str,
    ingress: targets::IngressKind,
    tpu_quic: Option<&'a str>,
    window_first_slot: u64,
    window_last_slot: u64,
    template: crate::probe::Template,
    lock: String,
    payer: String,
    signature: String,
    blockhash: String,
    blockhash_slot: u64,
    last_valid_block_height: u64,
    wire_base64: String,
    max_fee: u64,
}

/// Deterministic, fresh lock address: sha256(run_id ‖ probe_id) — reproducible from the logs, never a real account.
fn lock_for(run_id: &str, probe_id: &str) -> Pubkey {
    let h = Sha256::digest(format!("itb-lock/{run_id}/{probe_id}").as_bytes());
    Pubkey::new_from_array(h.into())
}

pub async fn run(rpc: Arc<Rpc>, ws_url: &str, args: SmokeArgs) -> Result<()> {
    let clock = RunClock::new();
    let run_id = new_run_id(if args.live { "smoke-live" } else { "smoke-dry" });
    let run = Arc::new(RunDir::create(args.out.join(&run_id))?);
    let started_at = utc_now_rfc3339();
    tracing::info!(%run_id, live = args.live, "smoke run starting");

    let gate = alpenglow::require_active(&rpc).await?;

    // Live mode: the campaign guard (lock, ledger, cap, reconciliation) and the master keypair; dry mode signs with a
    // throwaway key.
    let (payer, campaign) = if args.live {
        let campaign = Campaign::open(
            &rpc,
            &gate,
            OpenArgs {
                ledger: &args.ledger,
                max_spend_sol: args.max_spend_sol,
                keypair: args.keypair.as_deref(),
                payer_dir: &args.payer_dir,
                holder: &run_id,
            },
        )
        .await?;
        campaign.budget("smoke", Some(args.budget_sol))?;
        let kp = read_keypair(
            args.keypair
                .as_deref()
                .context("--live requires --keypair (or ITB_KEYPAIR_PATH)")?,
        )?;
        (Arc::new(kp), Some(Arc::new(campaign)))
    } else {
        (Arc::new(Keypair::new()), None)
    };

    let (validators, raw_gossip) = targets::snapshot(&rpc).await?;
    run.write_zst("gossip.json.zst", &raw_gossip)?;
    let chosen: Vec<Validator> = if args.targets.is_empty() {
        targets::top_per_group(&validators, args.per_group.saturating_sub(1))
            .into_iter()
            .take(args.max_targets)
            .collect()
    } else {
        args.targets
            .iter()
            .map(|id| {
                validators
                    .iter()
                    .find(|v| &v.identity == id)
                    .cloned()
                    .with_context(|| format!("{id} not staked / not in gossip"))
            })
            .collect::<Result<_>>()?
    };
    if chosen.is_empty() {
        bail!("no targets selected");
    }

    let epoch = rpc.get_epoch_info().await?;
    let now_slot = epoch.absolute_slot;
    let mut plan: Vec<(Validator, (u64, u64))> = vec![];
    for v in chosen {
        let slots = rpc
            .leader_slots(now_slot, &v.identity, epoch.first_slot_of_epoch())
            .await?;
        match targets::windows(slots)
            .into_iter()
            .find(|(s, _)| *s > now_slot + 25)
        {
            Some(w) => plan.push((v, w)),
            None => {
                tracing::warn!(identity = %v.identity, "no upcoming window in this epoch; skipped")
            }
        }
    }
    plan.sort_by_key(|(_, w)| w.0);

    let preview: Vec<_> = plan
        .iter()
        .map(|(v, w)| json!({"identity": v.identity, "client_id": v.client_id, "ingress": v.ingress, "tpu_quic": v.tpu_quic,
                              "stake": v.activated_stake, "window": [w.0, w.1], "slots_from_now": w.0 - now_slot}))
        .collect();
    eprintln!("{}", serde_json::to_string_pretty(&preview)?);

    let slot_clock =
        SlotClock::start(ws_url, clock, 200.0, crate::timing::AnchorEvent::FirstShred).await?;
    let quic = Arc::new(QuicClient::new(clock)?);
    let planned = Arc::new(run.jsonl("plan.jsonl")?);
    let sends = Arc::new(run.jsonl("sends.jsonl")?);
    let connects = Arc::new(run.jsonl("connects.jsonl")?);

    let mut tasks = vec![];
    for (v, window) in plan {
        let (rpc, quic, slot_clock, payer, campaign, run_id) = (
            rpc.clone(),
            quic.clone(),
            slot_clock.clone(),
            payer.clone(),
            campaign.clone(),
            run_id.clone(),
        );
        let (planned, sends, connects) = (planned.clone(), sends.clone(), connects.clone());
        let (probes, offset_ms, age) = (args.probes, args.offset_ms, args.blockhash_age_slots);
        tasks.push(tokio::spawn(async move {
            let res: Result<Vec<Tracked>> = async {
                let Some(addr) = v.tpu_addr() else { bail!("{} has no tpuQuic", v.identity) };
                slot_clock.wait_for_slot(window.0.saturating_sub(15)).await?;
                let report = quic.connect(addr).await;
                connects.append(&json!({"target_identity": v.identity, "report": report}))?;

                let bh = rpc.aged_blockhash(age).await?;
                let template = library::A;
                let mut items = vec![];
                let mut tracked = vec![];
                for i in 0..probes {
                    let probe_id = format!("{}-w{}-p{i}", &v.identity[..8], window.0);
                    let lock = lock_for(&run_id, &probe_id);
                    let tx = template.build(&payer, &lock, bh.blockhash.clone());
                    let wire = bincode::serialize(&tx)?;
                    let signature = tx.signatures[0].to_string();
                    planned.append(&PlannedProbe {
                        probe_id: probe_id.clone(),
                        target_identity: &v.identity,
                        client_id: &v.client_id,
                        ingress: v.ingress,
                        tpu_quic: v.tpu_quic.as_deref(),
                        window_first_slot: window.0,
                        window_last_slot: window.1,
                        template,
                        lock: lock.to_string(),
                        payer: payer.pubkey().to_string(),
                        signature: signature.clone(),
                        blockhash: bh.blockhash.to_string(),
                        blockhash_slot: bh.slot,
                        last_valid_block_height: bh.last_valid_block_height,
                        wire_base64: base64::engine::general_purpose::STANDARD.encode(&wire),
                        max_fee: template.total_fee(),
                    })?;
                    tracked.push(Tracked {
                        probe_id: probe_id.clone(),
                        signature,
                        target_identity: v.identity.clone(),
                        window_first_slot: window.0,
                        window_last_slot: window.1,
                        last_valid_block_height: bh.last_valid_block_height,
                        max_fee: template.total_fee(),
                        transport_error: None,
                    });
                    items.push((probe_id, wire));
                }

                let at = slot_clock
                    .predict_instant(window.0)
                    .map(|t| {
                        let t = tokio::time::Instant::from_std(t);
                        if offset_ms >= 0 { t + Duration::from_millis(offset_ms as u64) } else { t - Duration::from_millis((-offset_ms) as u64) }
                    })
                    .unwrap_or_else(tokio::time::Instant::now);

                match &campaign {
                    Some(campaign) => {
                        if report.error.is_some() {
                            for t in &mut tracked {
                                t.transport_error = Some(format!("connect: {}", report.error.clone().unwrap_or_default()));
                            }
                            return Ok(vec![]); // nothing reserved, nothing sent
                        }
                        campaign.ensure_running()?;
                        let batch: Vec<Reservation> = tracked
                            .iter()
                            .map(|t| Reservation {
                                signature: t.signature.clone(),
                                kind: Kind::Probe,
                                label: t.probe_id.clone(),
                                max_fee: t.max_fee,
                                payer: payer.pubkey().to_string(),
                                last_valid_block_height: t.last_valid_block_height,
                                budget: "smoke".into(),
                                provenance: Some(Provenance {
                                    run_id: run_id.clone(),
                                    probe_id: t.probe_id.clone(),
                                    target_identity: t.target_identity.clone(),
                                    window_first_slot: t.window_first_slot,
                                    window_last_slot: t.window_last_slot,
                                }),
                            })
                            .collect();
                        let ledger = &campaign.ledger;
                        ledger.reserve_batch(&batch)?;
                        let deadline = at + Duration::from_millis(200);
                        let outgoing = items.into_iter().map(|(probe_id, wire)| Outgoing { probe_id, wire, at, deadline }).collect();
                        let records = quic.send_scheduled(&campaign.auth, addr, outgoing).await;
                        for (t, r) in tracked.iter_mut().zip(&records) {
                            t.transport_error = r.error.clone();
                            if r.never_opened {
                                ledger.cancel_unsent(&t.signature)?; // provably never left this process
                            }
                            sends.append(&json!({"dry_run": false, "record": r, "target_identity": v.identity}))?;
                        }
                        // Probes that never left are resolved as not sent, not polled for.
                        let unsent: std::collections::HashSet<String> = records.iter().filter(|r| r.never_opened).map(|r| r.probe_id.clone()).collect();
                        tracked.retain(|t| !unsent.contains(&t.probe_id));
                    }
                    _ => {
                        let scheduled_unix_ns = crate::timing::RunClock::new().instant_to_unix_ns(at.into_std());
                        for (probe_id, _) in &items {
                            sends.append(&json!({"dry_run": true, "probe_id": probe_id, "target_identity": v.identity,
                                                 "would_send_unix_ns": scheduled_unix_ns}))?;
                        }
                    }
                }
                Ok(tracked)
            }
            .await;
            res.map_err(|e| {
                tracing::error!(identity = %v.identity, error = %e, "target failed");
                e
            })
        }));
    }

    let mut tracked = vec![];
    for t in tasks {
        if let Ok(Ok(mut v)) = t.await {
            tracked.append(&mut v);
        }
    }

    let mut summary = json!({"run_id": run_id, "mode": if args.live { "live" } else { "dry_run" }, "started_at": started_at,
                             "rpc": redact_url(rpc.url()), "alpenglow": gate, "probes_planned": tracked.len()});
    if let Some(campaign) = &campaign {
        let outcomes = collect::resolve(
            &rpc,
            Some(&campaign.ledger),
            &tracked,
            Some(&run),
            Duration::from_secs(120),
        )
        .await?;
        let out = run.jsonl("outcomes.jsonl")?;
        for o in &outcomes {
            out.append(o)?;
        }
        eprintln!(
            "\n{:<10} {:<14} {:<28} {:>6} {:>8}",
            "target", "status", "signature", "slot", "index"
        );
        for o in &outcomes {
            eprintln!(
                "{:<10} {:<14} {:<28} {:>6} {:>8}",
                &o.probe_id[..8],
                serde_json::to_value(o.status)?.as_str().unwrap_or("?"),
                &o.signature[..24],
                o.slot
                    .map(|s| (s % 1_000_000).to_string())
                    .unwrap_or_default(),
                o.index_in_block
                    .map(|i| format!("{i}/{}", o.block_tx_count.unwrap_or(0)))
                    .unwrap_or_default()
            );
        }
        summary["owned_lamports_drop_since_campaign_opening"] =
            serde_json::to_value(campaign.reconcile_now(&rpc).await?)?;
        summary["ledger"] = serde_json::to_value(campaign.ledger.totals()?)?;
        summary["outcomes"] = serde_json::to_value(&outcomes)?;
    }
    quic.close_all().await;
    run.write_zst("slot_events.json.zst", &slot_clock.take_events())?;
    summary["finished_at"] = json!(utc_now_rfc3339());
    run.write_json("run.json", &summary)?;
    eprintln!("\nrun written to {}", run.path.display());
    Ok(())
}
