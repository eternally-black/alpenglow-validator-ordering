# Inside the Block — how Solana validators order transactions (post-Alpenglow mainnet)

**Three pre-registered studies on Solana mainnet.** We send pairs of our own probe transactions into the leader windows of 10 validators. They run four scheduler code bases (Agave 4.3.2, Jito-Solana 4.3.2, Rakurai 4.3.2, Firedancer 26.10.4), reached directly or through BAM and Harmonic block builders: 8 gossip client types in all. The pairs are built so that the candidate ordering rules *disagree* about which member should land first. Every claim can be re-checked on chain with one command.

> Bounty: [Superteam Ukraine — Inside the Block](https://superteam.fun/earn/listing/inside-the-block-how-solana-validators-order-transactions) · verbatim brief in [docs/BOUNTY.md](docs/BOUNTY.md)
> All measurements are **after** the Alpenglow upgrade: feature gate `A1pengvu…` active at slot 459,648,000; first Alpenglow block 459,653,008. This is enforced in code.

| | |
|---|---|
| **Result** | • **The rule:** all 6 core targets (confirmatory) order our probes as Agave's **reward ÷ (cost + 1)** priority predicts. The 4 extended targets (exploratory) agree, two outright, one "assumes selection", one `partial`. CU price, lamport fee and arrival order are rejected.<br>• **The reward counts, not just the cost:** a third study pitted reward ÷ cost against ordering by requested cost alone. In 318 of 318 pairs the higher reward per cost unit landed first, so each core target's key is identified as reward ÷ (cost + 1) among the registered candidates ([REPORT §6.5](REPORT.md#65-study-3-does-the-reward-count-confirmatory-h4-h5)).<br>• **Replicated:** a second pre-registered study on the next day gave the same claim for all 6 core targets.<br>• **How strictly:** Firedancer, BAM and Harmonic hold it in almost every window and reorder over 5 to more than 50 ms of arrival. The Agave family holds it for transactions pending at slot start or sent together, but a 2 ms head start already wins 80 % of races.<br>Full report with intervals, measurement times and what went wrong: [REPORT.md](REPORT.md) |
| **Brief compliance** | Mainnet only, all after Alpenglow · 10 validators, 8 gossip client types, versions 4.3.2 and 26.10.4 ([table](#validators-measured)) · our own transactions as primary evidence · fee cap compiled into the binary and enforced by a ledger (0.0480 of 0.05 SOL spent, three studies) · dry run by default · one-command Docker reproduction · raw data with every signature and slot ([requirement → evidence](#requirement--evidence)) |
| **Reproduce (offline, no keys)** | `docker compose up --build`: a few minutes including the image build; the raw data are 181 MB of the clone |
| **Re-check claims on chain** | `docker compose --profile verify up` |
| **Pre-registration** | [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md), the normative analysis plan, frozen on 2026-10-24 before the campaign. Its SHA-256 and those of [the design](design/design.jsonl) and [the manifest](design/campaign.json) are in mainnet Memo [`5vRM47a8…QcyG`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg) (slot 460,779,153, signed by the measurement wallet). Check: `sha256sum docs/PREREGISTRATION.md design/design.jsonl design/campaign.json` |
| **Does the method work?** | [docs/POWER.md](docs/POWER.md): the analysis is run on simulated schedulers with known rules, including look-alikes built to fool it |
| **Study 2 (2026-10-25)** | A pre-registered replication plus head-start races on a fine grid ([plan](docs/STUDY2-PLAN.md), [pre-registration 2](docs/PREREGISTRATION-2.md), [operating characteristics](docs/POWER-2.md), [results](REPORT.md#61-replication-hypothesis-r)). Replication 6/6; all six hypotheses supported, no gate fired. Hashes, including the analysis code's git tree, in mainnet Memo [`2T6ha9FD…D5ww`](https://explorer.solana.com/tx/2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww) (slot 461,151,605) |
| **Study 3 (2026-10-26)** | Does the reward count, or only the cost? Two new contrasts on which reward ÷ cost and cost alone disagree ([plan](docs/STUDY3-PLAN.md), [pre-registration 3](docs/PREREGISTRATION-3.md), [operating characteristics](docs/POWER-3.md), [results](REPORT.md#65-study-3-does-the-reward-count-confirmatory-h4-h5)). All twelve hypotheses supported, all robust to selection within the evaluable windows; 318 of 318 pairs in reward ÷ cost order. Frozen after two reviews and two re-checks. Hashes, the analysis tree and the frozen Study 1 / 2 claims in mainnet Memo [`2C57e22K…beUz5`](https://explorer.solana.com/tx/2C57e22K29Hj1v5z1J3Wrp3gXS717KQBrzVuMgPQKWhMX7Lv38VZmsWybxHK8A5JErxRW3JHq6dkXRtisRxbeUz5) (slot 461,631,524) |
| **Probe explorer** | [docs/explorer/index.html](docs/explorer/index.html): every window and probe of the three studies, each linked to Solana Explorer. The data are embedded: open the file from a clone (GitHub's file view shows its source) |
| **Cost** | All three studies together: 0.0480 SOL on chain, under the 0.05 SOL cap compiled into the binary. Each later ledger carries the cost of the studies before it, so the cap held over all three |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/identification-dark.svg">
  <img src="figures/identification.svg" width="100%" alt="Three panels, one per contrast (C1 A vs B, C2 A-prime vs B, C3 A vs A-prime), ten validator groups each. Priority-label estimates sit near 1, 0 and 1, the pattern only reward divided by cost predicts; send-order estimates sit near 0.5 inside the tie band for every group.">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/study3-contrasts-dark.svg">
  <img src="figures/study3-contrasts.svg" width="100%" alt="Study 3, pre-registered: two panels, C4 (Y vs A) and C5 (hi vs A), six core targets each. The priority-label estimates sit at 1 for every target in both panels, far from what cost alone predicts (0 on C4, 0.5 on C5). Send-order estimates sit near 0.5.">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/arrival-dark.svg">
  <img src="figures/arrival.svg" width="100%" alt="One dot per leader window, positioned by when our first probe finished sending relative to the leader's first shred. Agave, Jito-Solana and Rakurai follow reward divided by cost in every window queued before the slot (75 of 75) but in only 8 of 25 windows that arrive during the slot. Firedancer and the BAM and Harmonic builders follow it in 215 of 216 windows either way.">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/study2-races-dark.svg">
  <img src="figures/study2-races.svg" width="100%" alt="Study 2, pre-registered: six panels of the share of races in which a higher-priority probe overtook a lower-priority one sent 0 to 50 ms earlier. Agave and Jito-Solana: 7 of 35 and 6 of 29 at 2 ms, none from 5 ms on. Firedancer EvnRmnMr: nearly all, up to 50 ms. The Harmonic builders and Agave plus BAM: nearly all at 2 ms, falling to none by 50 ms.">
</picture>

---

## 1. The question, made measurable

The brief asks: *by what rule does each validator order the transactions in its block, how strictly does the rule hold, and is there a rule at all?*

A passive look at blocks cannot answer this. A transaction's position mixes the fee, the cost, its arrival time, account conflicts and batching, and an observer controls none of them. We control them ourselves:

**Probe atom — identical shape for every probe** ([`probe.rs`](crates/itb/src/probe.rs)):
- 1 signature, 2 writable accounts (payer + a fresh, unfunded "lock"), 31 bytes of instruction data;
- `SetComputeUnitLimit(L)`, `SetComputeUnitPrice(p)`, `SetLoadedAccountsDataSizeLimit(D)`, and a 0-lamport System transfer to the lock.

Only **L, p and D** vary between probes. Agave's priority is `reward·10⁶/(cost+1)`, where `reward` is the priority fee plus 2,500 lamports (the unburned half of the signature fee) and `cost` contains the *requested* L and D. So we can move a probe's priority **without paying for it** and pull apart three rules that usually move together.

**Contrast library** ([`scripts/contrasts.py`](scripts/contrasts.py); golden-tested in Rust):

| Probe | L | p (µL/CU) | D | priority fee | Agave priority |
|---|---|---|---|---|---|
| A | 1000 | 1,000,000 | 32 KiB | 1000 | 1,498,287 |
| B | 3000 | 500,000 | 32 KiB | 1500 | 922,509 |
| A′ | 1000 | 1,000,000 | 64 MiB | 1000 | 187,045 |
| Y (Study 3) | 1500 | 4,000,000 | 32 KiB | 6000 | 2,997,179 |
| hi (Studies 2, 3) | 1000 | 3,000,000 | 32 KiB | 3000 | 2,354,452 |

| Contrast | CU-price rule says | Lamport-fee rule says | Cost-alone rule says | Reward/cost rule says |
|---|---|---|---|---|
| **C1** A vs B | A | **B** | A | A |
| **C2** A′ vs B | **A′** | B | B | B |
| **C3** A vs A′ | tie | tie | A | **A** |
| **C4** Y vs A (Study 3) | Y | Y | **A** | Y |
| **C5** hi vs A (Study 3) | hi | hi | **tie** | hi |

Studies 1 and 2 ran C1–C3, where cost alone and reward/cost agree. Study 3 added C4 and C5 to tell those two apart.

- **Send order is randomised and balanced inside every pair, independently of the labels.** An arrival-order (FIFO) rule therefore shows up only when the outcomes are coded by send order. A random rule shows up in neither coding.
- **Conflict windows.** In half the windows the economic key and the arrival order disagree. The outcome in those windows measures *how strictly* a rule overrides arrival.

### Validators measured

Client and version as each validator advertised them in gossip at measurement time, identical in every snapshot
(`target_states.jsonl` in each run). Ingress is the endpoint we actually reached.

| Validator | Gossip client | Version | Ingress | Study 1 | Study 2 | Study 3 |
|---|---|---|---|---|---|---|
| `7QQGNm3p…` | Agave | 4.3.2 | direct | core | core (K, R) | core (N) |
| `HEL1USMZ…` | JitoLabs (Jito-Solana) | 4.3.2 | direct | core | core (K, R) | core (N) |
| `EvnRmnMr…` | Firedancer | 26.10.4 | direct | core | core (K, R) | core (N) |
| `DRpbCBMx…` | AgaveBam | 4.3.2 | BAM node | core | core (K, R) | core (N) |
| `Fd7btgyS…` | HarmonicAgave | 4.3.2 | Harmonic remote TPU | core | core (K, R) | core (N) |
| `JUPiTERr…` | HarmonicFiredancer | 26.10.4 | Harmonic remote TPU | core | core (K, R) | core (N) |
| `9eGrDohd…` | Firedancer | 26.10.4 | direct | extended | equal-key windows (E) | — |
| `9jxgosAf…` | FireBAM | 26.10.4 | BAM node | extended | — | — |
| `5Cchr1XG…` | AgaveBam | 4.3.2 | BAM node | extended | — | — |
| `ana2y2Yv…` | Rakurai | 4.3.2 | direct | extended | — | — |

## 2. Why this design

Each decision links to the evidence behind it.

| Decision | Why | Evidence |
|---|---|---|
| **Primary evidence = our own probes only** (other txs are supplementary) | Brief requirement; only our probes have known keys and send times | [docs/BOUNTY.md](docs/BOUNTY.md) |
| **Leader type = clientId × ingress kind**, per window | ≈ 69 % of stake advertises a TPU that is a **shared BAM node or Harmonic Remote TPU**; there an external builder, not the validator, orders. `clientId` flips when BAM/Harmonic connect or disconnect | [research 02](docs/research/02-transaction-path-and-tooling.md), [research 03](docs/research/03-client-schedulers.md) |
| **Buffered regime for direct ingress** (probes sent ≈ 150 ms before the window, in 3 of every 4 windows; the 4th streams, as a built-in check of the buffer assumption) | Agave holds packets that arrive ≤ 20 slots before its window, and Firedancer keeps pending txs. So both members of a pair should be pending when the leader starts, isolating the scheduler's key from arrival. We observe send times, not the queue | agave v4.3.2 `decision_maker.rs`; firedancer `default.toml` (research 02 errata) |
| **Streaming regime for shared ingress** | We expected pre-window sends to a shared builder to land with whichever leader is current (spill-over), so shared ingress gets in-window sends, and pre-window sends are measured separately as a spill-over map. The map found the opposite: 28 of 29 pre-window probes landed in the target window (REPORT §5) | [PLAN §2.4](docs/PLAN.md) |
| **Event-anchored send times** | Slot times after Alpenglow are not the nominal 400 ms, nor a steady 200 ms. In all five campaign runs the median was ≈ 198 ms per slot inside a leader window and 266–272 ms across the hand-over between leaders (the design's early dry-run estimate, 130 / 560 ms, was off: REPORT §7). So we send relative to *observed* first shreds, not an extrapolated clock | `cadence_at_prep` in every run's `windows.jsonl`, [`timing.rs`](crates/itb/src/timing.rs) |
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
| **Competition inside the block** | Every produced block of every probed window is archived as an excerpt: all signatures in order, per-transaction fee, CU and cost, the leader, and our probes in full. Block fullness and our probes' priority percentile are archived, but were not analysed (REPORT §8). Inclusion is a co-primary outcome | Other senders' arrival times and the scheduler's internal queue |
| **Send order** | Randomised and balanced within each pair; independent of every key by construction; analysed as its own coding | — |
| **Noise vs rule** | Pre-registered rules and decision thresholds; random rule as a candidate; equivalence tests for "tie" predictions; window-level strictness; a mixture diagnostic; simulation-calibrated operating characteristics; null results reported as findings | Effects smaller than the documented minimum detectable effect |
| **Alpenglow (do not mix)** | Feature gate checked by every run; slots below 459,653,008 rejected at ingest and analysis | — |

### What this design does NOT separate (also in REPORT.md)

- **Keys outside the registered candidates.** Study 3 separated reward ÷ cost from cost alone. An additive key, reward − λ·cost, still ranks every pair of the three studies the same way as reward ÷ cost, so "identified" means among the registered candidates (CU price, lamport fee, cost alone, FIFO, random). The identification also combines the three studies and assumes each target's key did not change between their dates ([REPORT §9](REPORT.md#9-what-this-design-does-not-separate)).
- **Priority fee vs total charged fee.** With one signature both rank probes identically; we report them as one class.
- **The validator's own scheduler vs an upstream builder** that uses the same comparator. Final blocks cannot tell these apart, so we report the ingress topology instead.
- **Streaming priority vs a short batch auction** when only a smooth reordering curve is observed. We report an "effective reordering horizon" and do not claim a batch period.
- **A relayer co-located on the validator's own IP, on a non-standard port,** would be classified as direct ingress. Only known relayer ports and shared BAM/Harmonic endpoints are recognised. The ingress kind is recorded per window, and every group is reported separately.
- **Our probes vs application transactions.** Our results are scoped to untipped, legacy, tiny probes on the measured path and dates. v1 transactions and heavy programs are external-validity limits.

## 4. Verify it yourself

```bash
docker compose up --build                  # all three studies: recompute every results file and redraw every figure from data/raw (no network, no keys), diff all
docker compose --profile verify up         # re-fetch blocks for a sample of claims from mainnet and check them
VERIFY_SAMPLE=0 docker compose --profile verify up   # all claims (slow on the public RPC: ~6 getBlock / 10 s)
sha256sum docs/PREREGISTRATION-2.md design/design-study2.jsonl design/campaign-study2.json   # = the Study 2 Memo
sha256sum docs/PREREGISTRATION-3.md design/design-study3.jsonl design/campaign-study3.json   # = the Study 3 Memo
python scripts/verify_frozen_study2.py     # re-decide Study 2 with the analysis code pinned in its manifest
python scripts/verify_frozen_study3.py     # the same for Study 3
```

For each landed probe, the verifier checks that:
- the signed bytes we logged before sending carry a valid ed25519 signature by the claimed payer;
- its signature sits at the claimed index of the claimed block;
- the transaction decodes to the claimed L, p, D, payer and lock;
- the fee equals `5000 + ⌈L·p/10⁶⌉`;
- the slot's leader is the target (from the block's fee-reward recipient).

A completeness check runs over the archived window blocks: no probe may sit in a block of its window unless its outcome claims exactly that landing. This catches an RPC that answered "not found" for a transaction that was included. The verifier separates **chain-verifiable** facts from **locally recorded** ones (send timestamps). Raw data layout: [docs/DATA.md](docs/DATA.md).

### Requirement → evidence

| Brief requirement (docs/BOUNTY.md) | Where it is met |
|---|---|
| Mainnet only | Every live run checks the genesis hash; each study's manifest freezes it ([`design/campaign.json`](design/campaign.json), [`design/campaign-study2.json`](design/campaign-study2.json), [`design/campaign-study3.json`](design/campaign-study3.json)). Non-mainnet needs `--allow-non-mainnet`, used by the localnet tests only |
| ≥ 6 validators across ≥ 3 client types, identifiable by version string | [Validators measured](#validators-measured): 10 validators, 8 gossip client types, versions 4.3.2 and 26.10.4 as advertised in gossip |
| The whole measurement within ≈ 0.05 SOL, enforced in code | `COMPILED_MAX_SPEND_LAMPORTS` in [`auth.rs`](crates/itb/src/auth.rs); every fee reserved before sending in [`ledger.rs`](crates/itb/src/ledger.rs); 0.0480 SOL spent for the three studies ([REPORT §11](REPORT.md)) |
| Dry run by default, live only behind a flag and a cap | `LiveAuthorization` in [`auth.rs`](crates/itb/src/auth.rs); `docker compose --profile dryrun up` |
| Our own transactions as the primary evidence | Every estimand is computed on our probes ([PREREGISTRATION §1](docs/PREREGISTRATION.md), [PREREGISTRATION-2 §2](docs/PREREGISTRATION-2.md), [PREREGISTRATION-3 §3](docs/PREREGISTRATION-3.md)); other transactions appear only as block context |
| Pre- and post-Alpenglow data never mixed | Gate in [`alpenglow.rs`](crates/itb/src/alpenglow.rs); every slot ≥ 459,653,008; eligibility (d) rejects earlier slots ([`outcomes.py`](analysis/itb_analysis/outcomes.py)) |
| Docker Compose, one command | `docker compose up --build`: offline, `network_mode: none`, recomputes all three studies and every figure |
| Raw data with signatures and slots | [`data/raw/`](data/raw) (format: [docs/DATA.md](docs/DATA.md)); [probe explorer](docs/explorer/index.html) |
| README: why this design, how each consideration is handled, what is not separated | [§2](#2-why-this-design), [§3](#3-how-the-design-handles-each-item-in-what-you-will-have-to-account-for), [What this design does NOT separate](#what-this-design-does-not-separate-also-in-reportmd) |
| REPORT: the date of every measurement and what went wrong | [REPORT.md](REPORT.md) §1 (timeline) and §7 (what went wrong) |
| Keys only through a volume or env | [§5](#5-engineering); `.gitignore` covers `keys/` and `keys-*/`; gitleaks in CI |
| Jito bundles and tips out of scope | Untipped single transactions, no bundles ([REPORT §9](REPORT.md)) |

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
analysis/            analysis package (Python): outcomes, stats, sim, oc, verify, report, exploratory, figures
design/              target list, frozen design and campaign manifest (hashes in the Memo; scripts/freeze.py)
data/raw/<run_id>/   every observation of every run (signed probes, sends, outcomes, blocks, gossip)
data/derived/        numbers in the report, regenerated by `docker compose up`
figures/             light and dark SVG figures; `docker compose up` checks them byte for byte, `--profile figures` redraws
docs/explorer/       probe explorer page (static; `python scripts/build_explorer.py` rebuilds its data)
docs/                PLAN, PREREGISTRATION, POWER, DATA, research notes, independent reviews
docker/              Dockerfiles; docker/LOCALNET.md
```

## 7. Process

- Study 3's pre-registration was reviewed before its freeze by GPT and DeepSeek. GPT re-checked the fixes twice; the first re-check found one more blocker, the second gave "FREEZE OK" ([dispositions](docs/review/STUDY3-prefreeze-dispositions.md)). Its results text was reviewed before publication by GPT, DeepSeek and Claude Fable; no number was wrong, and the wording fixes are in [STUDY3-results-dispositions.md](docs/review/STUDY3-results-dispositions.md).
- Study 2's pre-registration was reviewed before its freeze by GPT (gpt-6.1-sol) and DeepSeek (deepseek-v4-flash): five blocking problems, all fixed with tests ([dispositions](docs/review/STUDY2-prefreeze-dispositions.md)). The finished submission had a last review by both, plus Claude Fable reading it as a judge ([FINAL-dispositions.md](docs/review/FINAL-dispositions.md)).
- The plan was reviewed adversarially by three independent models before any code: GPT-6 Astra, Claude Fable and DeepSeek-V4.1-Flash. Their reviews and every disposition are in [docs/review/](docs/review/) and [PLAN §12](docs/PLAN.md).
- The code was reviewed at the first gate by GPT-6 Astra ([CODE-gate1-gpt.md](docs/review/CODE-gate1-gpt.md), 30 findings). It was then re-reviewed adversarially after the fixes ([CODE-gate1b-gpt.md](docs/review/CODE-gate1b-gpt.md): 10 closed, 19 partial, 1 open, 14 new). Every gate-1b item and how it was handled: [docs/review/CODE-gate1b-dispositions.md](docs/review/CODE-gate1b-dispositions.md).

License: [Apache-2.0](LICENSE).
