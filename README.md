# Inside the Block — how Solana validators order transactions (post-Alpenglow mainnet)

**A pre-registered measurement on Solana mainnet.** We send pairs of our own probe transactions into the leader windows of ≥ 6 validators across ≥ 5 client/fork types (Agave, Jito-Solana, Jito BAM, Harmonic, Firedancer …). The pairs are built so that the candidate ordering rules *disagree* about which member should land first. Every claim can be re-checked on chain with one command.

> Bounty: [Superteam Ukraine — Inside the Block](https://superteam.fun/earn/listing/inside-the-block-how-solana-validators-order-transactions) · verbatim brief in [docs/BOUNTY.md](docs/BOUNTY.md)
> All measurements are **after** the Alpenglow upgrade: feature gate `A1pengvu…` active at slot 459,648,000; first Alpenglow block 459,653,008. This is enforced in code.

| | |
|---|---|
| **Status** | Code, analysis and simulation complete; localnet end-to-end green. Mainnet campaign 2026-10-27 → 10-29 (hard stop `--not-after`), then [REPORT.md](REPORT.md) with per-validator verdicts, intervals, measurement dates and the "what went wrong" log |
| **Reproduce (offline, no keys)** | `docker compose up --build` |
| **Re-check claims on chain** | `docker compose --profile verify up` |
| **Pre-registration** | [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md), the normative analysis plan, frozen on 2026-10-24 before the campaign. Its SHA-256 and those of [the design](design/design.jsonl) and [the manifest](design/campaign.json) are in mainnet Memo [`5vRM47a8…QcyG`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg) (slot 460,779,153, signed by the measurement wallet). Check: `sha256sum docs/PREREGISTRATION.md design/design.jsonl design/campaign.json` |
| **Does the method work?** | [docs/POWER.md](docs/POWER.md): the analysis is run on simulated schedulers with known rules, including look-alikes built to fool it |

---

## 1. The question, made measurable

The brief asks: *by what rule does each validator order the transactions in its block, how strictly does the rule hold, and is there a rule at all?*

A passive look at blocks cannot answer this. A transaction's position mixes the fee, the cost, its arrival time, account conflicts and batching, and an observer controls none of them. We control them ourselves:

**Probe atom — identical shape for every probe** ([`probe.rs`](crates/itb/src/probe.rs)):
- 1 signature, 2 writable accounts (payer + a fresh, unfunded "lock"), 31 bytes of instruction data;
- `SetComputeUnitLimit(L)`, `SetComputeUnitPrice(p)`, `SetLoadedAccountsDataSizeLimit(D)`, and a 0-lamport System transfer to the lock.

Only **L, p and D** vary between probes. Agave's priority is `reward·10⁶/(cost+1)`, and `cost` contains the *requested* L and D. So we can move a probe's priority **without paying for it** and pull apart three rules that usually move together.

**Contrast library** ([`scripts/contrasts.py`](scripts/contrasts.py); golden-tested in Rust):

| Probe | L | p (µL/CU) | D | priority fee | Agave priority |
|---|---|---|---|---|---|
| A | 1000 | 1,000,000 | 32 KiB | 1000 | 1,498,287 |
| B | 3000 | 500,000 | 32 KiB | 1500 | 922,509 |
| A′ | 1000 | 1,000,000 | 64 MiB | 1000 | 187,045 |

| Contrast | CU-price rule says | Lamport-fee rule says | Reward/cost rule says |
|---|---|---|---|
| **C1** A vs B | A | **B** | A |
| **C2** A′ vs B | **A′** | B | B |
| **C3** A vs A′ | tie | tie | **A** |

- **Send order is randomised and balanced inside every pair, independently of the labels.** An arrival-order (FIFO) rule therefore shows up only when the outcomes are coded by send order. A random rule shows up in neither coding.
- **Conflict windows.** In half the windows the economic key and the arrival order disagree. The outcome in those windows measures *how strictly* a rule overrides arrival.

## 2. Why this design

Each decision links to the evidence behind it.

| Decision | Why | Evidence |
|---|---|---|
| **Primary evidence = our own probes only** (other txs are supplementary) | Brief requirement; only our probes have known keys and send times | [docs/BOUNTY.md](docs/BOUNTY.md) |
| **Leader type = clientId × ingress kind**, per window | ≈ 69 % of stake advertises a TPU that is a **shared BAM node or Harmonic Remote TPU**; there an external builder, not the validator, orders. `clientId` flips when BAM/Harmonic connect or disconnect | [research 02](docs/research/02-transaction-path-and-tooling.md), [research 03](docs/research/03-client-schedulers.md) |
| **Buffered regime for direct ingress** (probes sent ≈ 150 ms before the window, in 3 of every 4 windows; the 4th streams, as a built-in check of the buffer assumption) | Agave holds packets that arrive ≤ 20 slots before its window, and Firedancer keeps pending txs. So every member of a pair is in the queue when the leader starts, and the scheduler's key is isolated from arrival | agave v4.3.2 `decision_maker.rs`; firedancer `default.toml` (research 02 errata) |
| **Streaming regime for shared ingress** | Pre-window sends to a shared builder land with whichever leader is current (spill-over). They are measured separately as a spill-over map | [PLAN §2.4](docs/PLAN.md) |
| **Event-anchored send times** | After Alpenglow a slot inside a leader window is observed every ≈ 130 ms, but the hand-over between leaders takes ≈ 560 ms (≈ 235 ms per slot, not 200). We send relative to *observed* first shreds, not an extrapolated clock | dry-run data, [`timing.rs`](crates/itb/src/timing.rs) |
| **Window = statistical unit**; exact binomial intervals; Bonferroni over 36 effects; randomisation tests that follow the real assignment | Pairs inside one window are not independent | [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md) §4 |
| **Positive controls first** (vanilla Agave, Firedancer) | Their rule is public. If we cannot recover it, nothing else in the report should be believed | PREREGISTRATION §9 |
| **Stopping by landed pairs, not by results** | Probes that do not land cost nothing. Low-landing ingress gets more windows, without a peek at the ordering | PREREGISTRATION §5 |
| **Simulation before live data** | The full published procedure runs on 1,700 simulated campaigns with known rules, look-alikes and failure injection. For every strict rule at 90 % landing it names the true rule for 96–100 % of core validators. A wrong claim *without* the "(assumes selection)" qualifier never occurs, in any scenario. Qualified wrong claims appear only for FIFO (2 % of core validators) and in the reviewer's selection counterexample, which the qualifier exists to catch | [docs/POWER.md](docs/POWER.md) |

## 3. How the design handles each item in "what you will have to account for"

| Brief item | Handling | Deliberately not separated |
|---|---|---|
| **Leader schedule and leader types** | `getLeaderSchedule` → 4-slot aligned windows. Gossip snapshot every 60 s (clientId, version, `tpuQuic`, ingress kind) and a mode per window: stable / transition-ambiguous / unknown. Which of the window's slots were produced (`getBlocks`). Kobe `running_bam` snapshot | Private operator configuration (Firedancer pacing, Harmonic strategy, BAM plugins): we observe behaviour, not config |
| **Path from our backend to the executing node** | Our own QUIC client, TLS/transport identical to agave's `tpu-client-next`, pinned to the advertised `tpuQuic`. Per-stream open/write/finish timestamps. Ingress kind per window. Spill-over map. Hold-cliff test (Agave drops packets > 20 slots early; Firedancer keeps them) | Arrival time at the leader is unobservable (we log send time). Staked/SWQoS paths: we are an unstaked sender |
| **Interaction of our own transactions** | Conflicts only through designed lock accounts. Distinct payers, randomly assigned. ≤ 14 streams per burst (below the 20/100 ms unstaked throttle). One persistent connection per IP (agave allows 8 new connections/IP/min) | Sub-millisecond stream processing order inside the receiver |
| **Competition inside the block** | Every produced block of every probed window is archived as an excerpt: all signatures in order, per-transaction fee, CU and cost, the leader, and our probes in full. Block fullness and our probes' priority percentile are covariates. Inclusion is a co-primary outcome | Other senders' arrival times and the scheduler's internal queue |
| **Send order** | Randomised and balanced within each pair; independent of every key by construction; analysed as its own coding | — |
| **Noise vs rule** | Pre-registered rules and decision thresholds; random rule as a candidate; equivalence tests for "tie" predictions; window-level strictness; a mixture diagnostic; simulation-calibrated operating characteristics; null results reported as findings | Effects smaller than the documented minimum detectable effect |
| **Alpenglow (do not mix)** | Feature gate checked by every run; slots below 459,653,008 rejected at ingest and analysis | — |

### What this design does NOT separate (also in REPORT.md)

- **Priority fee vs total charged fee.** With one signature both rank probes identically; we report them as one class.
- **The validator's own scheduler vs an upstream builder** that uses the same comparator. Final blocks cannot tell these apart, so we report the ingress topology instead.
- **Streaming priority vs a short batch auction** when only a smooth reordering curve is observed. We report an "effective reordering horizon" and do not claim a batch period.
- **A relayer co-located on the validator's own IP, on a non-standard port,** would be classified as direct ingress. Only known relayer ports and shared BAM/Harmonic endpoints are recognised. The ingress kind is recorded per window, and every group is reported separately.
- **Our probes vs application transactions.** Our results are scoped to untipped, legacy, tiny probes on the measured path and dates. v1 transactions and heavy programs are external-validity limits.

## 4. Verify it yourself

```bash
docker compose up --build                  # recompute every number from data/raw (no network, no keys) and diff
docker compose --profile verify up         # re-fetch blocks for a sample of claims from mainnet and check them
VERIFY_SAMPLE=0 docker compose --profile verify up   # all claims (slow on the public RPC: ~6 getBlock / 10 s)
```

For each landed probe, the verifier checks that:
- the signed bytes we logged before sending carry a valid ed25519 signature by the claimed payer;
- its signature sits at the claimed index of the claimed block;
- the transaction decodes to the claimed L, p, D, payer and lock;
- the fee equals `5000 + ⌈L·p/10⁶⌉`;
- the slot's leader is the target (from the block's fee-reward recipient).

A completeness check runs over the archived window blocks: no probe may sit in a block of its window unless its outcome claims exactly that landing. This catches an RPC that answered "not found" for a transaction that was included. The verifier separates **chain-verifiable** facts from **locally recorded** ones (send timestamps). Raw data layout: [docs/DATA.md](docs/DATA.md).

## 5. Engineering

- **Dry-run by default, type-enforced.** Transaction bytes can only be written with a `LiveAuthorization`. The CLI builds one only after it has checked `--live`, `--max-spend-sol`, the keypair and the Alpenglow gate ([`auth.rs`](crates/itb/src/auth.rs)). A dry run still uses the real schedule, gossip and QUIC handshakes.
- **Spend cap, layered** ([`ledger.rs`](crates/itb/src/ledger.rs), [`campaign.rs`](crates/itb/src/campaign.rs)):
  - (1) every transaction is reserved at its worst-case fee *before* sending, in a crash-safe SQLite ledger. A fee is released only if the transaction provably never left the process. An expired transaction frees its payer but stays charged: RPC "not found" answers never release money. The frozen design's worst case (0.039 SOL) fits under the cap by itself;
  - (2) cumulative on-chain reconciliation over all owned accounts before any send, in every live command, with no tolerance. An unexplained drop is charged and stops every further send;
  - (3) every send counts against a named sub-budget with its own cap (smoke, setup, pilot, campaign), inside a compiled maximum of 0.05 SOL;
  - (4) one cumulative ledger for everything, held by one process at a time (an OS file lock released on process death). Deadlines bound every stream open and write; live runs require the pre-registered `--not-after`.
- **Crash recovery is experiment recovery.** `itb reconcile` resolves open reservations and writes each probe's outcome and landing block back into its original run. Restored windows never count towards stopping.
- **Keys** only via a mounted volume or env. The default reproduction runs with `network_mode: none`. gitleaks runs in CI.
- **Logging:** structured JSON per window and per probe; the signed bytes of every probe are logged *before* sending.
- **Containers:** one Compose file with profiles `reproduce` (default), `verify`, `dryrun`, `live`, `keys`, `localnet` (a pinned Agave 4.3.2 test validator built from the SHA-256-verified release).
- **Tests:**
  - Rust unit tests, including golden cost/priority vectors and ledger crash/restart tests;
  - Python tests for the statistics (including counterexamples from the code review), the simulator and the verifier;
  - an end-to-end test that sends live probes over QUIC to a local Agave 4.3.2 node, collects outcomes and verifies every claim from the archived blocks ([`scripts/e2e-localnet.sh`](scripts/e2e-localnet.sh)).

## 6. Repository map

```
crates/itb/          measurement binary (Rust): probe, design, quic, timing, ledger, run, collect, setup
analysis/            analysis package (Python): outcomes, stats, sim, oc, verify, report
design/              target list, frozen design and campaign manifest (hashes in the Memo; scripts/freeze.py)
data/raw/<run_id>/   every observation of every run (signed probes, sends, outcomes, blocks, gossip)
data/derived/        numbers in the report, regenerated by `docker compose up`
docs/                PLAN, PREREGISTRATION, POWER, DATA, research notes, independent reviews
docker/              Dockerfiles; docker/LOCALNET.md
```

## 7. Process

- The plan was reviewed adversarially by three independent models before any code: GPT-6 Astra, Claude Fable and DeepSeek-V4.1-Flash. Their reviews and every disposition are in [docs/review/](docs/review/) and [PLAN §12](docs/PLAN.md).
- The code was reviewed at the first gate by GPT-6 Astra ([CODE-gate1-gpt.md](docs/review/CODE-gate1-gpt.md), 30 findings). It was then re-reviewed adversarially after the fixes ([CODE-gate1b-gpt.md](docs/review/CODE-gate1b-gpt.md): 10 closed, 19 partial, 1 open, 14 new). Every gate-1b item and how it was handled: [docs/review/CODE-gate1b-dispositions.md](docs/review/CODE-gate1b-dispositions.md).

License: [Apache-2.0](LICENSE).
