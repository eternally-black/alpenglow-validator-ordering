# Research note 03 — Per-client ordering hypotheses

Compiled 2026-10-23 from source at release tags and vendor docs.

Link bases:
- AG = `https://github.com/anza-xyz/agave/blob/v4.3.2/`
- JS = `https://github.com/jito-foundation/jito-solana/blob/v4.3.2-jito/`
- FD = `https://github.com/firedancer-io/firedancer/blob/v26.10.4/`
- OD = `https://github.com/jito-foundation/jito-omnidocs/blob/4cd4e24cfe38e5c0e733ca4e0828bf2453e2fd86/`

## Identification

- **`getClusterNodes.clientId`** (Agave ≥ 4.0). Enum (AG `version/src/client_ids.rs`):
  0 SolanaLabs, 1 JitoLabs, 2 Frankendancer, 3 Agave, 4 AgavePaladin, 5 Firedancer, 6 AgaveBam, 7 Sig, 8 Rakurai,
  9 HarmonicFiredancer, 10 HarmonicAgave, 11 HarmonicFrankendancer, 12 FireBAM, 13 Raiku.
- **The id is dynamic:**
  - The BAM manager switches it to AgaveBam and repoints the TPU to the BAM node while connected. It falls back to JitoLabs on disconnect (JS `core/src/bam_manager.rs`).
  - Harmonic Salsa restores its own TPU when its scheduler disconnects.
  - → Snapshot gossip near every target window.
- **Version strings carry no fork suffix**; Firedancer uses calendar versions (26.10.x).
- **Jito Kobe** `https://kobe.mainnet.jito.network/api/v1/validators` (no auth): `running_bam`, `bam_connection_rate`.
- **validators.app** `/api/v1/validators/mainnet.json` (token): `software_client`, `software_client_id`, `software_version`, `jito`.

## Ingress topology at capture time ([RPC] `getClusterNodes`)

| clientId | where `tpuQuic` points |
|---|---|
| AgaveBam / FireBAM | BAM node, port 5010, 17 shared IPs |
| HarmonicAgave / HarmonicFiredancer | Harmonic Remote TPU, port 9007, 6 shared IPs |
| JitoLabs | Own IP. 40 nodes advertise 11228 (self-hosted relayer default, `packet_delay_ms = 50`); only 11 on a different IP |
| Firedancer, Rakurai, Agave, Raiku | Own IP |

## Hypotheses and observable signatures

| Client | Hypothesised rule | Signature in our probes / `getBlock` | Evidence |
|---|---|---|---|
| Agave | Greedy streaming scheduler, 4 workers. Each pass pops the highest **P = reward·10⁶/(cost+1)** it can lock. **reward** = priority fee + 50 % of signature fee. **cost** = 720·sigs + 300·writable + data/4 + requested CU limit + 8·⌈loaded-data-limit/32 KiB⌉. Ties broken by transaction id (`pop_last` on a BTreeSet → the higher id wins ⇒ **later arrival first among equals**). Batches ≤ 64 txs per worker = one entry. CU budget released linearly over the slot (pacing). | Simultaneous probes in descending P. At equal fee, a lower CU limit or a `SetLoadedAccountsDataSizeLimit` wins. Staggered probes land in arrival order. Equal-P contended probes in the same pass come out in reverse arrival order. | AG `core/src/transaction_priority.rs#L32-L66`, `runtime/src/bank/fee_distribution.rs#L97-L106`, `cost-model/src/cost_model.rs#L103-L201`, `…/transaction_state_container.rs#L161-L163`, `…/transaction_priority_id.rs#L4-L8`, `…/greedy_scheduler.rs#L38-L48,#L130-L230`, `…/scheduler_controller.rs#L63-L65,#L520-L540` |
| Jito-Solana | Agave scheduler unchanged for non-bundle txs. Bundles run FIFO in their own stage, contiguous and atomic. The tip-crank tx comes at slot start. | As Agave; plus contiguous tip-paying runs (excluded from analysis) | JS `…/greedy_scheduler.rs#L271-L285`, `core/src/bundle_stage.rs#L629-L700` |
| BAM (AgaveBam / FireBAM) | BAM node (TEE) runs an auction every **~50 ms**. Per batch: maker-plugin txs first, then bundles + txs by one "priority score". The validator executes **in received order** (FIFO by sequence id). | Sawtooth of descending runs per slot. A higher-fee probe sent < ~50 ms later can overtake; sent later than that, it cannot. | OD `bam/maker-plugin/how-it-works/index.md#L31-L33`, `bam/bam-overview/index.md#L35`, JS `…/bam_scheduler.rs#L1-L3` |
| Firedancer | Pack treap ordered by **rewards / compute_est**, with Agave-equivalent constants. Rewards are divided down for txs that **allocate account data**. Accounts with > 64 pending refs go to per-account penalty treaps. Bundles first. One tx per normal microblock (entry). Pacing: `balanced` (default) or `perf`; **`revenue` was removed**. | Strongest priority alignment expected. An allocating probe ranks below an equal-fee non-allocating one (unique to Firedancer). | FD `src/disco/pack/fd_pack.c#L227,#L553,#L1036-L1090,#L2765-L2790`, `fd_pack_cost.h#L88-L93`, `fd_microblock.h#L69-L71`, `src/app/shared/fd_config.c#L461` |
| Harmonic (Salsa = Agave fork, Samba = Firedancer fork) | Builders via Remote TPU; default strategy `fba` = **50 ms buffers sorted by "priority fees and tips"**; `fifo` and `mrev` (proprietary) also exist. Salsa uses Agave's external-scheduler bindings. | Sawtooth like BAM. If the key is total fee (not per CU), the equal-fee / different-CU-limit test separates it from Agave/Firedancer. | [docs.harmonic.gg scheduling-strategies](https://docs.harmonic.gg/concepts/scheduling-strategies), [salsa-4](https://docs.harmonic.gg/run-a-validator/setup/salsa/salsa-4.md) |
| Rakurai | Closed-source scheduler in a Jito fork; falls back to Jito behaviour | Unknown — measure | Figment write-up (secondary) |
| Raiku | 1 staked node; unknown | — | — |

## Errata (from the v1 plan reviews; supersede the table above where they conflict)

- **Agave tie-break.** The table says "later arrival first among equals". That is **not supported**.
  - `TransactionId` is `usize`, taken from a **reused `Slab` key** (`transaction_state_container.rs` `insert_map_only` → `vacant_entry().key()`).
  - "Later arrival ⇒ higher id" holds only on a fresh slab, for example right after the container is cleared.
  - Prechecks drain out of order, too. So the tie order is implementation-defined and treated as descriptive.
- **Firedancer tie-break.** `fd_treap` inserts an equal element "epsilon larger" and pack walks `treap_rev_iter` from the best. ⇒ **the later-arrived equal tx is scheduled first**, deterministically. This is a falsifiable prediction.
- **Firedancer microblocks.** Normal txs are batched up to `max_txn_per_microblock`; it is *bundle* txs that go one per microblock. Re-check the configured limit before using this as an entry-structure prediction.
- **Firedancer rewards** = priority fee + 50 % × 5000 × sigs. Ordering uses exact cross-multiplication rather than Agave's floor(reward·10⁶/(cost+1)); this only matters at exact ties.
- **BAM cadence.** BAM's 2026-10-09 changelog says auction rounds tightened **25 → 20 ms** with 200 ms slots ([bam.dev](https://bam.dev/blog/bam-changelog-sept-23-oct-9/)). The omnidocs still say "~50 ms". Keep both in the hypothesis range.
- **BAM source path.** `core/src/banking_stage/transaction_scheduler/bam_scheduler.rs` **404s at v4.3.2-jito**. The BAM code lives in `core/src/bam_manager.rs`, `bam_connection.rs` and `bam_dependencies.rs`.
- **BAM routing.** Txs sent directly to a BAM validator's TPU are "also processed through BAM before execution" (omnidocs bam-overview).
- **Harmonic routing.** The Remote TPU forwards to the validator **and all connected builders**. The block engine routes per leader window and can fail over to another builder mid-slot. The validator falls back to its in-client scheduler as a last resort ([harmonic-architecture](https://docs.harmonic.gg/concepts/harmonic-architecture)).
- **Agave in-slot CU pacing** (`--block-production-pacing-fill-time-millis`) is cited from research but **not verified** at v4.3.2. Treat it as a hypothesis.

## Prior empirical work

- **Chorus One, "The State of Schedulers on Solana" (Mar 2026)** — passive, Dune data. Uses the normalised Spearman footrule *D* between actual order and fee-per-CU order (0 = perfect, ≈ 0.67 = random).
  - Agave ≈ 0.66 (arrival-driven); BAM ≈ 0.6; Harmonic ≈ 0.6 with a left tail; Firedancer ≈ 0.40–0.45.
  - https://chorus.one/reports-research/the-state-of-schedulers-on-solana-2
- **Gap we fill:** controlled, self-sent probes that separate the *key* (reward/cost vs CU price vs total fee), *timing* (batching interval, buffering), *contention* and *tie-breaking*. Passive analysis cannot separate these.
