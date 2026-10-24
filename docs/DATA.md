# Raw data layout and schema

Everything a run observes is appended to files under `data/raw/<run_id>/` as it happens. The analysis reads only
these files (plus `design/design.jsonl`). Pilot and smoke data live under `data/pilot/` and `data/smoke/` and are
labelled as such in every table.

- **Run id:** `<UTC yyyymmddThhmmssZ>-s<stage>-<live|dry>`.
- **Timestamps:**
  - `*_unix_ns` = Unix nanoseconds from a monotonic clock, anchored once per run (`RunClock`). They never jump with wall-clock adjustments.
  - All times are in the **observer frame**: our machine, our RPC's view of the chain.
- **API keys never appear in any file.** RPC URLs are redacted to `scheme://host/path?<redacted>`.

## Files per run

| File | One record per | Written when | Key fields |
|---|---|---|---|
| `run_start.json` | run | start | `mode` (`live`/`dry_run`), `stage`, `started_at`, `genesis_hash`, `alpenglow` gate status, `design_file`, `design_sha256`, `budget`, `anchor_event`, `not_after_unix`, `stop_at_unix_ns`, `obs_lag_ms`, `max_lateness_ms`, `targets`, `campaign_opening_lamports`, `itb_version` |
| `run_end.json` | run | end | `windows_started`, `window_failures`, `cadence` (inside/boundary ms), `anchor_event`, `payers_still_leased`, `ledger` totals, `owned_lamports_drop_since_campaign_opening` or `reconciliation_error`, `sending_stopped` |
| `probes.jsonl` | probe | **before** sending (signed realisation) | see below |
| `sends.jsonl` | probe | right after its phase is sent | live: `record` = `{probe_id, addr, scheduled_unix_ns, open_unix_ns, written_unix_ns, finished_unix_ns, stream_index_in_burst, limiter_delay_us, never_opened, error}`; dry-run: `{probe_id, would_send_unix_ns}` |
| `windows.jsonl` | attempted window | after sending | `target_identity`, `client_id`, `ingress`, `tpu_quic`, `version`, `seq`, `stage`, `kit`, `regime`, `burst_offset_ms`, `window_first_slot`, `window_last_slot`, `cadence_at_prep`, `connect` (handshake µs / error), `estimated_window_start_unix_ns`, `anchors` (per phase: slot, anchor time, observed?, event kind), `planned_probes`, `sent_ok`, `not_sent` + `not_sent_reasons`, `transport_errors`, `produced_slots` (or `produced_slots_error`), `archived_slots`, `reconnects` (connections re-established after the server evicted them), `payer_assignment_seed`, `blockhash_slot`, `last_valid_block_height`, `skipped` (reason) |
| `outcomes.jsonl` | probe | after resolution | `outcome` = `{probe_id, signature, status, slot, index_in_block, block_tx_count, leader, fee, err, cost_units, compute_units_consumed, confirmation_status, transport_error, expiry_evidence}` |
| `state/progress.jsonl` (attempt journal) | window | `claimed` (fsync) before any send; `terminal` (fsync) after resolution | `{state, run_id, target_identity, seq, live, design_sha256, budget, informative_pairs, recovered?}` — a claimed plan is never re-run within the same (mode, design, budget); one terminal record per window counts; dry runs use `state/progress.dryrun.jsonl` |
| `target_states.jsonl` | target × gossip snapshot (60 s) | periodically | `at_unix_ns`, `identity`, `state` (clientId, version, tpuQuic, gossip, ingress, stake) or null |
| `gossip/<unix_ns>.json.zst` | snapshot | periodically | raw `getClusterNodes` |
| `slot_events.json.zst` | slot notification | end | `{slot, kind, recv_unix_ns, server_ms}`; kinds from `slotsUpdatesSubscribe` |
| `blocks/<slot>.json.zst` | every produced slot of a live window, and every block a probe landed in | after the window / at resolution | **excerpt** of `getBlock` (`maxSupportedTransactionVersion: 1`, full, rewards): `blockhash`, `previousBlockhash`, `parentSlot`, `blockHeight`, `blockTime`, Fee `rewards` (the leader), `tx_count`, and per transaction in block order `signatures[i]`, `fees[i]`, `compute_units[i]`, `cost_units[i]`, `failed[i]`; our probes in full (transaction + meta) under `probe_transactions[<index>]`. ~30 KB instead of ~300 KB per block; `verify --source chain` compares against full blocks |

### `probes.jsonl` fields

| Field | Meaning |
|---|---|
| `probe_id` | `<target8>/<seq>/<pair>/<label>`, e.g. `7QQGNm3p/012/c1/A` |
| `target_identity`, `seq`, `stage`, `kit`, `regime` | design keys (`kit` ∈ k,t,h,s; `regime` ∈ buffered, streaming, pre_window) |
| `pair_id`, `pair_kind` | `pair_kind` ∈ c1, c2, c3, c2_uncontended, race, equal_key, single |
| `label` | library label: A, B, A', hi, lo, A#2 |
| `send_position_in_pair` | 0 = sent first, 1 = sent second |
| `race_dt_ms` | planned gap between the two members (race / equal-key pairs) |
| `template` | `{cu_limit, cu_price_micro_lamports, loaded_data_limit}` |
| `priority_fee`, `total_fee`, `cost`, `agave_priority` | predictions computed from the template (`crates/itb/src/probe.rs`) |
| `lock`, `lock_index` | the writable lock pubkey; equal `lock_index` within a window ⇒ shared lock |
| `payer` | fee payer pubkey (random pool assignment) |
| `signature` | the transaction signature — the key for chain verification |
| `blockhash`, `blockhash_slot`, `last_valid_block_height` | validity context |
| `window_first_slot`, `window_last_slot` | the targeted leader window |
| `anchor`, `nominal_offset_ms` | send-time anchor (estimate / prev_slot / window_slot) and offset |
| `wire_base64` | the exact signed bytes |

### Outcome status

| Status | Meaning |
|---|---|
| `landed_target` | confirmed status **and** found in the archived block, in a slot of the targeted window produced by the target |
| `landed_unverified` | confirmed status, but the block could not be fetched or lacked the signature — charged, never used as an ordering observation |
| `spillover_same_validator_other_window` | produced by the target, but in another of its windows (earlier or later) |
| `spillover_other_leader` | produced by a different leader |
| `expired_confirmed` | a finalized block height above the last valid height was observed first, then a status lookup answered at or past that finalized slot still found nothing (`expiry_evidence`) |
| `unresolved` | neither could be proven before the collection timeout (stays charged in the ledger; `itb reconcile` resolves it later) |
| `not_sent` | never put on the wire (anchor missed, deadline passed, cap reached, stream never opened) — never reserved or reservation cancelled |

## Verifying a claim by hand

```bash
# the block that contains a probe, and the probe's position in it
curl -s https://api.mainnet-beta.solana.com -H 'Content-Type: application/json' -d \
  '{"jsonrpc":"2.0","id":1,"method":"getBlock","params":[<slot>,{"maxSupportedTransactionVersion":1,"transactionDetails":"signatures"}]}' \
  | jq '.result.signatures | index("<signature>")'
```

`itb verify` (and `docker compose --profile verify up`) does this for every claim and also decodes each probe's
instructions to confirm L, p, D and the lock account.
