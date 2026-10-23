# Inside the Block — Master Plan (v1, 2026-10-23)

> **Status: v1 DRAFT → external review (Fable, DeepSeek-v4-flash, GPT-6 Astra) → v2 for maintainer approval.**
> Inputs: [BOUNTY.md](BOUNTY.md) (verbatim brief) and research notes [01](research/01-alpenglow-and-network-state.md), [02](research/02-transaction-path-and-tooling.md), [03](research/03-client-schedulers.md).
> Deadline: **2026-11-05 21:59:59 UTC**. Internal submit target: 2026-11-05 12:00 UTC.

---

## 0. Thesis — what we will claim, and why a judge will believe it

For each of **≥ 12 mainnet validators spanning 8 client/fork types**, we will name the ordering rule and say how strictly it holds. The client types are AgaveBam, JitoLabs, HarmonicAgave, HarmonicFiredancer, Firedancer, FireBAM, Rakurai and vanilla Agave. Together they hold 99.9 % of stake post-Alpenglow; the brief's minimum is 6 validators and 3 clients.

Each named rule decomposes into:

1. **Key** — what is sorted on. Candidates:
   - Agave priority `reward·10⁶/(cost+1)`;
   - CU price;
   - total priority fee;
   - arrival order;
   - none.
2. **Scope** — how long transactions are buffered before ordering. Candidates:
   - per scheduler pass (streaming);
   - per ~50 ms auction batch;
   - whole-slot;
   - pre-window buffer.
3. **Strictness** — the violation rate ε with a confidence interval, and where violations happen.
4. **Tie-break** — what happens at equal key, e.g. Agave's predicted *reverse-arrival* tie-break.
5. **Or:** "no rule detectable at our power", when that is what the data say.

Every claim is backed by transactions **we sent ourselves**, with signatures and slots, and is re-checkable by one command. That command re-fetches `getBlock` for every claimed slot and asserts each signature's index.

**Why we can beat a passive study** (e.g. Chorus One, Mar 2026). Passive data confounds the key, arrival time, contention and batching. We set those variables per probe, at random, against a pre-registered analysis plan.

---

## 1. Facts that shape the design (verified 2026-10-23)

| # | Fact | Consequence |
|---|---|---|
| F1 | Alpenglow gate `A1pengvu…` active at slot 459,648,000; first Alpenglow block 459,653,008. | All runs assert the gate is active and every analysed slot ≥ 459,653,008. **No pre-Alpenglow data, ever.** |
| F2 | **200 ms slots** (since Oct 9), leader window = 4 slots = **800 ms**, blockhash ≈ 30 s, epoch ≈ 24 h. | Timing engine must be ~±30 ms accurate. Send offsets are expressed in ms relative to the predicted window start. |
| F3 | No vote txs in blocks; `meta.costUnits` present; **v1 txs** (lamport-total `priorityFee`) are ~30–45 % of txs. | Parser handles legacy/v0/v1. Passive priority for v1 uses `transactionConfig`. |
| F4 | `clientId` in `getClusterNodes`; **dynamic** (BAM/Harmonic flip on connect/disconnect). | Gossip snapshot within ≤ 60 s of every target window. Plus a Kobe `running_bam` snapshot per run. The leader type is recorded per window, never assumed. |
| F5 | **TPU ingress ≠ validator for ~69 % of stake:** BAM node (17 shared IPs, port 5010) and Harmonic Remote TPU (6 shared IPs, port 9007). | "Leader type" = (clientId, ingress kind). For BAM/Harmonic the external builder orders. Shared ingress can route our tx to whichever BAM/Harmonic leader is current → spill-over is a measured outcome. |
| F6 | Agave unstaked QUIC: 20 streams / 100 ms per peer, 8 connections per peer. Non-leaders never forward unstaked txs. | ≤ 18 probes per window, burst ≤ 14 at once. Direct QUIC to the target's `tpuQuic` is the primary path. A tx that misses its leader is dropped, which is clean for attribution. |
| F7 | Agave priority = reward·10⁶/(cost+1). Cost includes the **requested** CU limit and the loaded-data limit (default 64 MiB = 16,384 CU). | We can move priority **for free** by changing cost. This decouples "reward/cost" from "CU price" from "total fee". |
| F8 | Firedancer divides reward for txs that allocate data. | A Firedancer-only discriminator probe (optional module). |
| F9 | Public RPC `getBlock` ≈ 6 / 10 s. | Collector needs a keyed RPC (Helius free tier, 10 RPS). The verifier has a rate-limited public-RPC mode. |
| F10 | No official Agave 4.x Docker image. | Build our own `solana-test-validator` image from the v4.3.2 release tarball (pinned SHA256). |

---

## 2. Experiment design

### 2.1 Unit, targets, replication

- **Experimental unit:** one leader window *W* (4 consecutive slots) of target validator *V*.
- **Targets (pre-registered list, finalised at the dry-run gate):**
  - 2 validators each for AgaveBam, JitoLabs, HarmonicAgave, HarmonicFiredancer, Firedancer;
  - 1–2 each for FireBAM, Rakurai, Agave;
  - → 12–14 validators.
  - Selection: highest stake (most windows) with distinct operators. The current `clientId` must be stable over the prior 24 h of snapshots.
  - Backups are listed for each.
- **Replication:** ≥ 16 windows per validator, spread over ≥ 3 sessions on ≥ 2 days at different hours (load varies).
  - The power analysis (§4.4) fixes the final N before the campaign.
- **Randomisation:** every design variable is drawn from a seeded RNG. The master seed is committed. Per-window seed = H(master_seed ‖ run_id ‖ window_id).
  - The full per-window design (`design.jsonl`) is generated and **committed before sending** (pre-registration of each run).

### 2.2 Probe transaction (the "atom")

```
legacy message, 1 signature (payer_i)
  ix0 ComputeBudget::SetComputeUnitLimit(L)
  ix1 ComputeBudget::SetComputeUnitPrice(p)          # µlamports/CU
  ix2 ComputeBudget::SetLoadedAccountsDataSizeLimit(D)   # omitted ⇒ default 64 MiB
  ix3 System::Transfer { from: payer_i, to: lock_k, lamports: 0 }
```

- **Conflicts are controlled only through `lock_k`.** It is a fresh, unfunded pubkey marked writable.
  - Contended probes share a `lock_k`; uncontended probes each get a unique one.
  - Payers are always distinct within a window, so the fee payer is never an accidental shared lock.
  - Hypothesis to verify on localnet: a 0-lamport transfer to a non-existent account succeeds, so no rent is used. Fallback: a self-transfer plus an extra writable account.
- **Fee per probe** = 5000 + ⌈L·p/10⁶⌉ lamports.
- **Agave cost estimate** = 720 + 300·2 + data/4 + L + 8·⌈D/32Ki⌉. Implemented once in `itb-probe::cost` and unit-tested against Agave's formulas with golden vectors.
- **Priority levers:**
  - reward via p (costs lamports);
  - cost via L and D (free).
  - E.g. L ∈ {450 … 50,000} and D ∈ {32 KiB, 1 MiB, default} span P by ≈ 30× at zero priority fee.
- **Every probe's design row records:** P_agave, CU price p, priority fee, total fee, cost estimate, send offset, lock group, payer index, kit and role.

### 2.3 Per-window kit (18 probes, ≤ 14 in the first burst)

| Kit | Probes | Construction | Tests |
|---|---|---|---|
| **A — Decomposition ladder** | 5 contended (one shared lock) + 5 uncontended (unique locks), the same 5 (p, L, D) tuples in both halves | Tuples drawn by rejection sampling. Rankings by the four keys (P_agave, CU price, priority fee, total fee) must have pairwise **\|Kendall τ\| ≤ 0.2**, with no ties within any key. All 10 are sent as **one burst** (back-to-back streams on one QUIC connection, < 2 ms) in a **random permutation** independent of every key. | Which key? (contended = forced sequential decision). Does the rule extend to non-conflicting txs (uncontended half)? Send order vs key. |
| **B — Race pairs** | 3 pairs, each on its own lock | Low-key probe at t₀, dominant high-key probe (higher on **all** keys) at t₀+Δt. Δt drawn from {0, 5, 10, 20, 35, 50, 75, 100, 150, 250} ms, stratified. | Buffering/batching scope: P(overtake \| Δt) curve. FIFO ⇒ ≈ 0 for Δt > 0. Batch auction of interval T ⇒ max(0, 1 − Δt/T). Deep buffer ⇒ ≈ 1. |
| **C — Tie pair** | 1 pair on its own lock | Two probes identical in every key (only payer/lock differ), sent back-to-back, A then B. | Tie-break rule (Agave predicts B first, reverse arrival). Also gives the **path-reordering noise floor**. |

- **Window-level factor τ (send offset vs predicted window start):** randomised per window, blocked by validator.
  - **pre** = −150 ms: arrive before the leader starts, so all probes sit in the buffer → isolates the scheduler's key from arrival.
  - **early** = +60 ms: slot 0, streaming.
  - **mid** = +460 ms: slot 2, streaming.
  - For shared-ingress leaders (BAM/Harmonic), *pre* is expected to spill into the previous leader. That is measured and reported, not hidden.
- **Optional modules** (only if budget and time allow, decided at the pilot gate):
  - **D — Firedancer allocation discriminator:** equal-fee pair. One probe has `System::Allocate(space>0)` on a 0-lamport fresh signer, so it fails at execution with no rent taken. The other is identical with space 0. Both have 2 signatures.
  - **E — Path factor:** a small share of windows sent via RPC `sendTransaction` instead of direct QUIC.
  - **F — Format factor:** a legacy vs v1 equal-key pair.

### 2.4 Budget arithmetic (cap 0.05 SOL; plan ≤ 0.035 SOL)

| Item | Lamports |
|---|---|
| Probe average fee (5000 base + ≈ 1,800 avg priority fee; most priority spread comes free from L/D) | ≈ 6,800 |
| Per window (18 probes) | ≈ 122,400 |
| 14 validators × 16 windows = 224 windows | ≈ 27.4 M (0.0274 SOL) |
| Pilot (≈ 12 windows) + optional modules + fund/sweep txs | ≈ 3.5 M |
| **Planned total** | **≈ 0.031 SOL** (cap 0.05; ≈ 38 % headroom) |
| Temporarily locked rent (40-payer pool × 650,240), fully swept back at the end | 26 M (0.026 SOL), not spent |

- Probes that do not land cost nothing. Landed-but-failed probes cost their fee; this is counted.
- **Wallet to fund (human):** ≈ 0.09 SOL.

---

## 3. How the design answers each item in "what you will have to account for"

| Brief item | Our handling | What remains unseparated (stated in README) |
|---|---|---|
| **Leader schedule and leader types** | `getLeaderSchedule` (epoch, identity) gives windows; confirmed by `getSlotLeaders` before firing. Leader type = **clientId (gossip snapshot ≤ 60 s before the window) × version × ingress kind** (direct / relayer / BAM node / Harmonic Remote TPU) × Kobe `running_bam`. Classification is per window, so a validator that flips BAM→Jito mid-campaign is split correctly. | Private operator config: Firedancer pacing, Harmonic strategy (`fba`/`fifo`/`mrev`), BAM plugins. We infer behaviour, not config. Validator ≠ client: same-client validators may differ, so we report per validator first and pool per client only when consistent. |
| **Path from backend to the executing node** | Primary path: direct unstaked QUIC to the advertised `tpuQuic`, pinned per window, connection pre-opened ≈ 2 s ahead. We log the handshake RTT, the send timestamps (monotonic ns) and the stream order. Ingress kind is recorded (BAM node / Harmonic proxy / relayer / validator). The documented hops are QUIC throttle → sigverify/dedup → container → scheduler → workers → entries. Optional E: the RPC path as a contrast. | The **arrival time at the leader is unobservable**; we observe send time. The tie pairs measure how much the path reorders back-to-back sends. Arrival vs send drift for Δt below that noise floor is not separated. Staked-sender (SWQoS) behaviour is out of scope: we are unstaked. |
| **Interaction of own transactions** | Conflicts only through designed locks; payers distinct; each payer rotated out until its previous tx is resolved (no cross-window locking). Unique signatures (no dedup collisions). ≤ 20 streams / 100 ms (no self-throttling). Negligible CU. | Effects of our own burst on the leader's QUIC queueing at sub-ms scale. |
| **Competition inside the block** | Per window we store full blocks for all 4 slots. Covariates: tx count, CU used vs the 50 M limit, our probes' P percentile within the block. Jito tip/bundle txs are flagged and excluded from passive stats. The analysis is stratified by load. | Other senders' arrival times and the scheduler's internal queue state. Competition is treated as noise and bounded, not controlled. |
| **Send order** | A random permutation inside each burst, independent of all keys by construction. Deliberate Δt offsets (Kit B). Exact send timestamps logged. | Sub-millisecond QUIC stream processing order at the receiver. |
| **Noise vs rule** | Pre-registered hypotheses and decision rules. Null model = uniformly random order (permutation tests). Window-level bootstrap CIs. Holm correction across validators. Simulation-calibrated thresholds and power. Tie pairs give the noise floor. Null results reported as findings. | Rules whose effect is smaller than our power (documented minimum detectable effect). |
| **Alpenglow (do not mix)** | The gate check is part of every run; slots < 459,653,008 are rejected at ingest and again at analysis. | — |

---

## 4. Analysis plan (to be frozen as `docs/PREREGISTRATION.md` before the main campaign)

### 4.1 Outcomes

- **Landing outcome per probe:**
  - landed in the target window (in-scope);
  - landed elsewhere (spill-over: record which leader and its type);
  - not landed (expired).
- **Order:** for in-scope probes, the observed order is the lexicographic (slot, index).
- **Same-slot vs cross-slot:** pairs in the same slot are analysed for the scheduler rule. Cross-slot pairs are reported separately; a slot boundary is a different mechanism.

### 4.2 Primary analyses

1. **Key identification (Kit A, contended half; per validator).**
   - For each key K ∈ {P_agave, CU price, priority fee, total fee, send order, reverse send order}, compute the pairwise concordance c_K over same-slot pairs.
   - Fit a noisy-deterministic model per key, P(pair agrees with K) = 1 − ε_K, by maximum likelihood.
   - Pick K* = argmin ε_K. Report ε with a window-bootstrap 95 % CI and the likelihood ratio vs the runner-up.
   - **Decision rule:** "rule K*" if ε_K* ≤ 0.10, the LR vs the runner-up ≥ 20, and the random null is rejected at Holm-adjusted p < 0.01. "Partial rule" if the null is rejected but the other criteria fail. Otherwise "no detectable rule".
   - A pairwise logistic model with Δ-features of all keys plus Δsend runs as a robustness check.
2. **Scope / batching (Kit B; per validator and per client).**
   - Fit P(overtake | Δt) under four models: step-FIFO (0), constant (deep buffer), linear batch window max(0, 1 − Δt/T), exponential decay.
   - Select by AIC and report T with a CI. Expected: BAM/Harmonic T ≈ 50 ms; Agave a short pass-scale window; Firedancer TBD.
3. **Tie-break (Kit C):** P(B first) with a CI. Agave predicts ≫ 0.5 (reverse arrival).
4. **Contention effect:** concordance(contended) − concordance(uncontended) with a CI.
5. **Timing effect:** strictness by τ (pre / early / mid).

### 4.3 Supplementary (other people's txs; labelled supplementary everywhere)

- **Passive census:** all blocks of the target validators during the campaign, plus ≥ 300 random blocks per client type.
  - Compute the normalised Spearman footrule D vs P_agave and vs CU price (comparable to Chorus One).
  - Compute descending-run segmentation per slot ("sawtooth" count). This gives an independent estimate of batches per slot; for BAM/Harmonic it should agree with T from Kit B.
  - P is computed from **requested** limits parsed from compute-budget ixs or the v1 `transactionConfig`. `meta.costUnits` is used only as a cross-check.
- **Entry ground truth (stretch):** Old Faithful archives (free, ≈ 10–20 h after epoch end) contain `Entry` nodes. For our slots, fetch them by HTTP range to check:
  - whether uncontended probes share entries;
  - Firedancer's one-tx-per-microblock;
  - Agave's ≤ 64-tx batches.
  - This turns "unseparated: entry boundaries" into "separated, for N slots".

### 4.4 Validation of the analysis itself (before any live data)

- **Simulator** (`analysis/sim`) implements candidate schedulers:
  - Agave-greedy-pass (P key, pass interval, 4 workers, reverse-arrival tie);
  - batch-auction(T, key);
  - Firedancer-treap(P, alloc penalty);
  - FIFO;
  - random.
  - It also models a network jitter calibrated from the tie pairs, and runs **our exact kit design** through each.
- **Outputs:**
  - (a) a confusion matrix: true rule → identified rule;
  - (b) the false-"rule" rate under random (target ≤ 1 %);
  - (c) windows-per-validator needed for ≥ 95 % correct identification;
  - (d) the minimum detectable ε.
- Committed as `docs/POWER.md`, generated by `make power`. This is how we show that **the experiment measures what it claims** (35 % criterion).

---

## 5. System architecture

```
repo/
├─ crates/                      Rust workspace (sender side; precision timing + QUIC)
│  ├─ itb-core     config, types (WindowPlan, ProbeSpec, SendRecord, Outcome), seeded design generator
│  ├─ itb-chain    RPC: leader schedule, slot leaders, cluster nodes (clientId/tpuQuic), Kobe, Alpenglow gate check
│  ├─ itb-clock    slot clock: slot notifications → (slot ↔ time) regression; latency calibration
│  ├─ itb-probe    probe builder (legacy; v1 optional), Agave cost model, fee math
│  ├─ itb-budget   spend ledger (SQLite WAL), reservations, on-chain balance guard, cap enforcement
│  ├─ itb-send     Sender trait: DryRunSender (no network) | QuicSender (tpu-client-next, pinned) | RpcSender
│  ├─ itb-collect  signature statuses → landing; getBlock (v1) → raw store; attribution to leader/window
│  └─ itb          CLI: check | targets | plan | run [--live --max-spend-sol X] | collect | fund | sweep | status
├─ analysis/                    Python 3.12 package (pandas/numpy/scipy/statsmodels/matplotlib)
│  ├─ itb_analysis/ load, costmodel, metrics, models, sim, passive, entries, report, site, verify
│  └─ tests/
├─ data/raw/<run_id>/           COMMITTED: design.jsonl (pre-send), sends.jsonl, outcomes.jsonl,
│                               gossip/*.json.zst, kobe.json.zst, blocks-slim/<slot>.jsonl.zst, logs.jsonl.zst
├─ data/derived/                regenerated by `analysis report` (byte-identical check)
├─ docs/  PLAN, SPEC, PREREGISTRATION, POWER, METHODS, research/
├─ site/                        static interactive report (GitHub Pages)
├─ docker/  itb.Dockerfile, analysis.Dockerfile, localnet.Dockerfile (agave 4.3.2 tarball, SHA256-pinned)
└─ docker-compose.yml
```

**Data volume.**
- Full `getBlock` JSON ≈ 0.5–3 MB per block, so ~1,000 blocks ≈ GBs.
- We commit **slim block extracts**: every tx's index, signature, version, fee, requested CU/limits, writable count, costUnits, CU consumed, err, program ids, tip flag. Size ≈ 50 KB per block zstd. Our probes' full tx JSON is also committed.
- Full raw blocks go to a GitHub Release asset with a SHA-256 manifest.
- The verifier re-fetches from chain anyway.

### 5.1 Safety engineering (Engineering 15 %)

- **Dry-run by default, enforced by types.**
  - Only `DryRunSender` exists unless `--live` is passed *and* `--max-spend-sol` is given.
  - `QuicSender::new` requires a `LiveAuthorization` value. It can only be built by the CLI validator after the cap, the keypair and the Alpenglow checks pass.
  - The dry-run does everything else: real schedule, real windows, real gossip, real QUIC handshake RTT (no tx bytes sent), `simulateTransaction` on a sample, and a full "would-send" log.
- **Spend cap, layered:**
  - (1) **Reservation ledger.** Before signing, reserve the worst-case fee 5000·sigs + ⌈L·p/10⁶⌉. Refuse if spent + open reservations + new > cap. Resolve to the actual `meta.fee` on landing, or release after blockhash expiry is finalized. Crash-safe: open reservations survive restart and count as spent until re-resolved.
  - (2) **On-chain guard.** Before each window, sum the balances of master + payers. Abort if (initial − current − rent_moved) > cap.
  - (3) **Per-validator and per-window sub-caps.**
  - (4) **Compiled hard maximum** of 0.1 SOL. Override is impossible without a code change.
  - (5) **Wallet funded with only ≈ 0.09 SOL** (the physical cap).
  - Fund and sweep txs also go through the ledger.
  - Property-based tests and cargo-mutants on `itb-budget`.
- **Keys:**
  - Master keypair via a read-only volume (`/keys/master.json`) or env `ITB_KEYPAIR_PATH`.
  - The payer pool is generated into the same volume at `fund` time.
  - Nothing key-like is ever in the repo: gitleaks runs in CI and pre-commit.
- **Logging:** `tracing` JSON lines with run_id, window_id and probe_id on every event; monotonic + UTC timestamps; committed (sanitised) as raw data. The "What went wrong" report section is generated from error/warn events plus human notes.
- **Containerisation:**
  - `docker compose up` = **reproduce** (no keys needed): Alpenglow check → ~10-min mainnet dry-run (window-hit stats) → verify a sample of claims against chain → regenerate all derived data and the report → diff against committed (fail on mismatch).
  - Profiles: `live` (keys + flag + cap), `localnet` (test validator e2e), `verify-all`.

---

## 6. Test strategy (how we know each layer is right)

| Layer | Test | Where |
|---|---|---|
| Probe builder & cost model | Golden vectors vs Agave formulas; fee math; `simulateTransaction` on localnet returns the expected CU; our cost estimate == `meta.costUnits` on localnet probes | `itb-probe` unit + localnet |
| Design generator | Determinism by seed; orthogonality constraint (\|τ\| ≤ 0.2); no ties; balanced τ/Δt strata | unit + property tests |
| Spend ledger | Random interleavings of reserve/resolve/crash/restart never exceed the cap; mutation-tested | `itb-budget` proptest + cargo-mutants |
| Slot clock | Synthetic notifications with jitter/gaps → prediction error bounds; dry-run on mainnet reports real error | unit + mainnet dry-run |
| Window planner | Epoch boundaries, skipped slots, leader identity changes | unit |
| Sender | Localnet: pinned QUIC to the test-validator TPU lands probes; dry-run sends zero bytes (asserted via a socket counter) | localnet e2e |
| Collector/attribution | Localnet blocks; recorded mainnet fixtures (v0/v1/legacy); spill-over classification | unit + fixtures |
| Analysis | The simulator recovers known rules (confusion matrix); permutation-test calibration under the null; golden metric tests | pytest |
| Reproducibility | Clean clone → `docker compose up` → byte-identical derived data | CI + final gate |
| End-to-end | **localnet** (free) → **devnet** live run (free, human-funded) → **mainnet dry-run** → **mainnet pilot** (cap 0.004 SOL) → campaign | gates |

CI (GitHub Actions; badges only for checks we actually run): fmt, clippy, cargo test, pytest, docker build, localnet e2e, gitleaks.

---

## 7. Phases & gates (HARD STOP = commit, gate report, independent reproduction, maintainer review)

| Phase | Dates (2026) | Scope | Gate |
|---|---|---|---|
| P0 Plan | Oct 23 | Research ✔, PLAN v1 → 3-model review → v2; maintainer approval | **HARD STOP** (this document) |
| P1 Foundations | Oct 24–25 | Workspace, config, itb-chain, itb-probe + cost model, itb-budget, DryRunSender, localnet image; analysis skeleton, **simulator + power analysis** | **HARD STOP**: tests green, POWER.md, ledger mutation report |
| P2 Engine | Oct 26–27 | itb-clock, QuicSender (pinned), itb-collect, `run` loop; localnet e2e; **devnet live e2e**; **mainnet dry-run** (window-hit accuracy, ingress reachability per target) | **HARD STOP**: dry-run report, target list frozen |
| P3 Pilot | Oct 28 | Mainnet live pilot, cap 0.004 SOL, 4 validators × 3 windows. Landing rates per ingress kind; τ calibration; fix. **Freeze PREREGISTRATION.md** (git timestamp) | **HARD STOP**: maintainer approves campaign spend |
| P4 Campaign | Oct 29–31 | ≥ 3 sessions, ≥ 2 days, all targets, ≥ 16 windows each. Passive census collection. Old Faithful entries as they appear | soft (daily data report) |
| P5 Analysis | Nov 1–3 | Primary + supplementary analyses, figures, REPORT.md (dates of every measurement, "What went wrong"), verifier, interactive site, README | soft, then external review of the analysis by 3 models |
| P6 Audit & submit | Nov 4–5 | Clean-clone reproduction, secrets sweep, README render check, Pages live, repo public, submission | **HARD STOP** before public flip + submit |

**Cross-model protocol:**
- Opus 5.5 (lead) writes the core.
- **Codex** is the second implementer for selected modules and does a code review at each HARD STOP.
- **DeepSeek-v4-flash** (1 M context) does whole-repo consistency and bug sweeps.
- **GPT-6 Astra** reviews the statistics (preregistration, models, power).
- **Fable** does adversarial design review ("does it measure what it claims?").
- At every HARD STOP an independent agent reproduces the gate from a clean clone.

---

## 8. Human steps (maintainer) — the agent stops and waits at each

| # | When | Action |
|---|---|---|
| H1 | now | Approve PLAN v2 (or request changes). |
| H2 | before P2 | Get a free Helius (or similar) mainnet RPC key → put it in `.env` as `RPC_URL=` / `WS_URL=`. Never paste it in chat. |
| H3 | before P2 | Devnet: create a devnet keypair and get ≈ 2 devnet SOL from faucet.solana.com (GitHub login). Agents must not use the faucet. |
| H4 | before P3 | Mainnet: `solana-keygen new -o <path outside repo>`, fund with ≈ 0.09 SOL, give the agent the **path only**. |
| H5 | optional | validators.app API token in `.env` (cross-check of client labels). |
| H6 | P6 | Approve creating/flipping the GitHub repo public (agent can run `gh` as `eternally-black`). Submit on Superteam Earn (account-bound). Afterwards sweep the remaining SOL. |

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Unstaked direct QUIC is throttled or dropped by BAM/Harmonic ingress | Pilot measures landing per ingress kind. Fallbacks: small bursts; optional RPC path; report landing rates as findings. |
| BAM flapping (maintenance) / Harmonic disconnects | Per-window classification (§3); backups per client. |
| Timing error from a home connection in Ukraine | Calibrate RTT per target. τ strata are wide (±100 ms tolerant). Optional cheap VPS in Frankfurt (compose makes it portable). |
| RPC rate limits | Keyed RPC; backoff; collection decoupled from sending. |
| Too few windows for minor clients (Agave 1.1 %, Rakurai 1.2 %) | Their top validator still has ≈ 450–560 windows/day; schedule-driven targeting. |
| Budget overrun | 5-layer cap; ≥ 38 % headroom planned. |
| Data too large for git | Slim extracts in git + full raw as a release asset + SHA-256 manifest. |
| Old Faithful lag | Stretch goal only; never blocks the report. |
| Over-claiming | Pre-registration; simulation-calibrated decision rules; "no detectable rule" is an allowed outcome. |

---

## 10. Deliverables checklist (maps to Submission Requirements)

| Requirement (verbatim key) | Deliverable |
|---|---|
| Repository | Public GitHub repo, MIT/Apache-2.0 |
| Reproducibility — one command, Docker Compose | `docker compose up` (reproduce profile) + `docker compose --profile live run itb run --live --max-spend-sol 0.05` |
| Keys only via volume/env | `/keys` read-only volume / `ITB_KEYPAIR_PATH`; gitleaks CI |
| Dry-run default, live behind explicit flag with spend cap | `LiveAuthorization` type gate; 5-layer cap |
| Raw data incl. signatures + slot numbers | `data/raw/**` + release asset + `verify` command |
| README: why this design / considerations / what it does NOT separate | README §Design, §Considerations table, §Not separated |
| Report with date of every measurement + "what went wrong" | `REPORT.md` (per-run UTC timestamps, epoch, slot ranges) |
