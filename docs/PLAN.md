# Inside the Block — Master Plan v2 (2026-10-23)

> **Status:** v2 (approved 2026-10-23), amended after the gate-1 code review ([CODE-gate1-gpt.md](review/CODE-gate1-gpt.md)).
> **For the analysis, [PREREGISTRATION.md](PREREGISTRATION.md) is normative** (complete-case primary estimand, six
> per-contrast predictions, selection check, window-level strictness, landing-based stopping). For timing, sends are
> anchored on observed first shreds (§2.5 note below); races use Δt ∈ {5, 25, 60, 100} ms from the target's first slot;
> H-kit offsets are −0.5 s, −3 s, −7 s.
> - GPT-6 Astra (via the Codex orchestrator): [review](review/PLAN-v1-gpt.md)
> - Claude Fable 5.1, source-checked at the pinned tags: [review](review/PLAN-v1-fable.md)
> - DeepSeek-V4.1-Flash: [review](review/PLAN-v1-deepseek.md)
>
> v1 is archived at [review/PLAN-v1.md](review/PLAN-v1.md). Each review finding and what we did about it is in §12.
> v2 was re-checked by DeepSeek-V4.1 ([review](review/PLAN-v2-deepseek.md)). Its 10 findings are fixed in place: the two-coding estimand for FIFO, Holm/TOST bounds, the budget recount to 0.028 SOL, ≥ 40 Firedancer equal-key pairs, the smoke test moved to Oct 24, and pre-committed fallback coverage.
>
> Inputs: [BOUNTY.md](BOUNTY.md) and research notes [01](research/01-alpenglow-and-network-state.md), [02](research/02-transaction-path-and-tooling.md), [03](research/03-client-schedulers.md).
> **Deadline 2026-11-05 21:59:59 UTC; internal submit target 2026-11-05 12:00 UTC.**

---

## 0. What we will claim (and the language we will use)

The brief asks, per validator: *what decides earlier vs later, how strictly, and is there a rule at all.*
We answer with **randomised economic contrasts**. These are pairs of our own probes that the candidate rules rank differently. We record what the chain does with them.

The estimand, stated exactly: for target validator **V** reached through ingress endpoint **E** on dates **D**, we measure the effect of a randomised fee/cost contrast on two outcomes.
1. **Inclusion:** whether each probe lands in V's window. This is a co-primary outcome.
2. **Ledger order:** whether member A lands before member B, using lexicographic (slot, index) over the whole window.

From these we report the **set of rules compatible with the data**, with interval estimates. We do not crown a single winner when two rules are observationally equivalent on our probes.

Pre-committed claim language (from the GPT review):

> *"For untipped legacy probes of shape S sent through endpoint E on dates D, contrast C1 favoured lower requested cost in X of Y evaluable windows (95 % CI […]); inclusion differed by Z. CU-price-only ordering is inconsistent with C2; reward/cost ordering at the ingress or validator remains compatible."*

**Positive controls first.** Vanilla Agave and Firedancer are open source with known comparators, and they anchor the study. *If we cannot recover the published reward/cost rule on them, the method is broken and nothing else in the report should be believed.* This gate is stated in the README.

---

## 1. Facts that shape the design (verified 2026-10-23; sources in research notes)

| # | Fact | Consequence |
|---|---|---|
| F1 | Alpenglow gate `A1pengvu…` active from slot 459,648,000; first Alpenglow block 459,653,008 | Every run asserts the gate; ingest and analysis reject slots < 459,653,008. **Post-Alpenglow only.** |
| F2 | 200 ms slots; leader window = 4 slots = 800 ms; blockhash valid for 150 blocks (≈ 30 s) | Offsets are in ms relative to the *predicted* window start; the *achieved* offset is classified post hoc (§4.4). |
| F3 | No vote txs; `meta.costUnits` present; v1 txs (lamport-total `priorityFee`) are ≈ 30–45 % of traffic | Parser handles legacy/v0/v1. Probes stay legacy (scope limit stated). |
| F4 | `getClusterNodes.clientId` is **dynamic** (BAM/Harmonic flip on connect/disconnect) | Gossip + Kobe snapshots immediately before *and* after each window; mode = stable / transition-ambiguous / unknown. |
| F5 | **≈ 69 % of stake ingests via shared builders.** BAM node: 17 IPs, :5010. Harmonic Remote TPU: 6 IPs, :9007. Harmonic forwards to the validator **and all connected builders**; BAM delivers "when their leader rotation arrives"; direct-to-validator TPU txs also go through BAM. | For BAM/Harmonic **the builder is the scheduler under test**. Report per endpoint and per validator. A pre-window send tests routing, not the validator. |
| F6 | Agave 4.3.2 unstaked QUIC: 20 streams / 100 ms **per connection** (excess *delayed*, not dropped); 8 connections per peer; **8 new connections per IP per minute (excess silently ignored)**; 2000 unstaked total | One persistent connection per ingress IP; ≤ 4 new connections/min per IP; ≤ 14 streams per burst. |
| F7 | **Agave holds** packets that arrive ≤ 20 slots (≈ 4 s) before its window and **drops them unparsed** earlier; its container is cleared between windows. **Firedancer keeps** pending txs across windows until blockhash expiry (65,524-slot pending treap). | The *buffered regime* exists for direct ingress. A free step-function test separates the two clients (H-windows). |
| F8 | Agave priority = ⌊reward·10⁶/(cost+1)⌋, reward = priority fee + 50 % of base fee, cost from **requested** CU limit and loaded-data limit. Firedancer uses the same quantities by exact cross-multiplication. | Priority can be moved **for free** through cost. This lets us decouple reward/cost from CU price from lamport fee. |
| F9 | Tie-breaks: Agave orders by (priority, `TransactionId`), and the id is a **reused `Slab` key**, so the tie order is implementation-defined. Firedancer's treap inserts equal elements "epsilon larger" and iterates in reverse, so **the later-arrived equal tx goes first**. | Kit-C hypotheses per client (§2.4); Firedancer has a sharp falsifiable prediction. |
| F10 | Cadence: BAM's Oct 9 changelog says rounds tightened **25 → 20 ms** with 200 ms slots; BAM docs still say "~50 ms"; Harmonic FBA = 50 ms double buffer. | Separate BAM / Harmonic hypotheses; the cadence range {20, 50} is kept open. |
| F11 | Mainnet `simulateTransaction`: 3 ComputeBudget ixs + a 0-lamport transfer to a non-existent account **succeeds at L = 600** and fails at 450 (every ix costs 150 CU) | Atom fixed (§2.2); no rent used for lock accounts. |
| F12 | Public RPC `getBlock` ≈ 6 / 10 s | Collector uses a keyed RPC. Offline reproduction needs no RPC. The public-RPC verifier samples ≤ 30 blocks. |

---

## 2. Experiment design

### 2.1 Units, mechanism groups, targets

- **Unit:** one leader window (4 slots) of target V. Within-window probes are never treated as independent observations.
- **Mechanism group:** defined by ingress kind × client.

  | Group | Ingress kind | Who orders | Regime used for key identification |
  |---|---|---|---|
  | G-AG | direct | Agave greedy scheduler (vanilla) | **buffered** (pre-window) + some streaming |
  | G-JD | direct | Jito-Solana (= Agave scheduler for non-bundles) | buffered + streaming |
  | G-FD | direct | Firedancer pack | buffered + streaming |
  | G-BAM | BAM node | BAM auction (TEE) → validator executes in received order | streaming only |
  | G-HAR | Harmonic Remote TPU | Harmonic builder (FBA default) | streaming only |
  | G-RLY / G-RAK | Jito relayer / Rakurai direct | Agave + relayer delay / closed scheduler | streaming (exploratory) |

- **Targets.** The list is frozen at the pre-registration gate. Each target has one backup on a *different* endpoint.

  | Tier | Validators | Windows each |
  |---|---|---|
  | **Core (6 validators, ≥ 5 client labels, all mechanism groups)** | vanilla Agave (positive control) · Firedancer (positive control) · JitoLabs-direct · AgaveBam (`running_bam`) · HarmonicAgave · HarmonicFiredancer | ≥ 40 K-windows + 16 T-windows + 6 H/S-windows |
  | Extended (exploratory) | 2nd Firedancer · 2nd AgaveBam on a **different BAM node** · Rakurai · FireBAM | 20 K-windows + 6 T-windows |

  This satisfies the brief (≥ 6 validators, ≥ 3 client labels) on the core tier alone. We report measured-validator stake separately from represented-client stake. We do not claim to have "measured 99.9 % of stake".
- **Randomisation.** A seeded RNG; the master seed is committed. Per-window seed = H(seed ‖ run_id ‖ window_id). Randomised per window:
  - kit assignment (blocked by validator);
  - within-pair send order (balanced A-first/B-first);
  - pair order within the burst;
  - payer identities (independent of treatment);
  - the offset within its stratum.

  The *template* design is frozen before the run. The *signed realisation* (bytes, blockhash, send timestamps) is appended immutably during it.

### 2.2 The probe atom (identical shape for every probe)

```
legacy message · 1 signature (payer) · 2 writable accounts (payer, lock) · 31 bytes of ix data
  ix0 ComputeBudget.SetComputeUnitLimit(L)            L ≥ 1000 (600 consumed; margin)
  ix1 ComputeBudget.SetComputeUnitPrice(p)            µlamports/CU
  ix2 ComputeBudget.SetLoadedAccountsDataSizeLimit(D) D ∈ {32 KiB, 64 MiB}, always explicit
  ix3 System.Transfer{ payer → lock, 0 lamports }     lock = fresh unfunded pubkey
```

- **Fee and cost.** fee = 5000 + ⌈L·p/10⁶⌉. Cost = 1,327 + L + 8·⌈D/32 KiB⌉ (720 sig + 600 write locks + 7 data). Golden-tested against the pinned Agave and Firedancer sources.
- **Kept constant across probes:** instruction set, account count and message length. Only L, p and D vary.
- **Every template must be simulated successfully** (`err == null`) before the design is frozen.
- **Locks.** Each pair gets fresh lock pubkeys. A shared lock forces a sequential decision; the uncontended arm uses distinct locks.
- **Payers.** Every probe in a window has a **distinct payer**, drawn at random from the 24-payer pool. A payer is never reused within a window or while one of its txs is unresolved. Assignments are logged.
- **Blockhash.** One blockhash per window group, **aged ≈ 120–135 slots** at send time. Probes then expire ≈ 3–6 s after send (≈ 2–5 s after the window ends), which:
  - bounds spill-over;
  - removes Firedancer carry-over into the next window;
  - halves the payer pool.

  The pilot measures the cost in extra expiries. H-windows use a fresh blockhash because they need the long horizon.
- **No application retries** in primary arms. We record hash, context slot, `lastValidBlockHeight`, serialized bytes and every transport attempt.

### 2.3 Contrast library (what each pair separates)

Values from `scripts/contrasts.py`. P = Agave priority.

| Probe | L | p (µL/CU) | D | prio fee | total fee | cost | P |
|---|---|---|---|---|---|---|---|
| A | 1000 | 1,000,000 | 32 KiB | 1000 | 6000 | 2,335 | 1,498,287 |
| B | 3000 | 500,000 | 32 KiB | 1500 | 6500 | 4,335 | 922,509 |
| A′ | 1000 | 1,000,000 | 64 MiB | 1000 | 6000 | 18,711 | 187,045 |
| hi | 1000 | 3,000,000 | 32 KiB | 3000 | 8000 | 2,335 | 2,354,452 |
| lo (= A′) | 1000 | 1,000,000 | 64 MiB | 1000 | 6000 | 18,711 | 187,045 |

| Contrast | Pair | CU-price rule predicts | Lamport-fee rule predicts | Reward/cost rule predicts | P ratio (max/min) |
|---|---|---|---|---|---|
| **C1** price vs fee | A vs B | A | **B** | A | 1.62 |
| **C2** price vs reward/cost | A′ vs B | **A′** | B | B | 4.93 |
| **C3** pure requested cost | A vs A′ | tie | tie | **A** | 8.01 |
| Dominance (T-kits) | hi vs lo | hi | hi | hi | 12.6 |

- **Patterns are distinct under two codings.** Every pair is analysed twice:
  - **by label** (A vs B): economic keys give CU price → (A, A′, tie), lamport fee → (B, B, tie), reward/cost → (A, B, A);
  - **by send order** (first-sent vs second-sent): an arrival/FIFO rule gives "first-sent lands first", and it shows *only* in this coding, because send order is randomised independently of the label.

  A random rule shows in neither coding. An economic key and FIFO can therefore never be confused. Where a mechanism mixes them (e.g. key within a batch, FIFO across batches), both effects show and are reported.
- **Shared ingress (BAM/Harmonic).** The two members of a pair are sent as back-to-back streams (< 1 ms apart), so they fall into the same 20/50 ms auction batch with probability ≥ 0.95. Economic-key claims for shared ingress are made only from these within-batch pairs. If the data show a send-order effect instead, the key is reported as "unidentified behind a FIFO stage".
- **"Free priority" exhibit.** Our cheap probes have P ≈ 10⁶, far above a typical paying tx (≈ 6·10⁴). On reward/cost schedulers they should sit at the top of the slot. On CU-price or lamport-fee builders they should sit low or not land at all.

### 2.4 Kits (one kit type per window — compact primary groups)

| Kit | Probes | Content | Regime |
|---|---|---|---|
| **K (primary)** | 8 | C1, C2 and C3 pairs, each on its own shared lock, plus one **uncontended** C2 pair (distinct locks). One burst on one QUIC connection; within-pair order randomised; pair order randomised. | Direct ingress: **buffered** (−150 ms) in 75 % of windows, streaming (+60 ms) in 25 %. Shared ingress: streaming at a random offset in [+40, +500] ms, never straddling a predicted slot boundary. |
| **T (secondary, Stage 2)** | 8 | 3 dominance races hi/lo with Δt ∈ {5, 25, 60, 100} ms (anchored 5 ms after the target's first shred, inside the ≈130 ms observed slot), balanced hi-first/lo-first. One **equal-key pair** (template A, both members) at Δt ∈ {10, 40} ms. Both race members are kept above the marginal priority *on the key identified in Stage 1*. **For Firedancer targets, one race is replaced by a second equal-key pair** (2 races + 2 equal-key pairs), so the LIFO prediction gets ≥ 40 informative pairs. | Buffered regime for direct ingress (equal-key pairs); streaming for races; pairs never straddle a predicted slot start. |
| **H (direct ingress, exploratory)** | 3 | Identical template-A probes sent at −0.5 s, −3 s, −7 s (fresh blockhash). Predictions: Agave lands −0.5/−3 and drops −7 (the 20-slot ≈ 4.7 s cliff); Firedancer lands all three. **6 H-windows per direct core validator.** | pre-window |
| **S (shared ingress, exploratory)** | 2 | Template-A probes at −150 ms and −1 s → **spill-over map**: which leader / ingress / slot actually included it, and after how many ms. **6 S-windows per shared core validator.** | pre-window |

**Hypotheses for the equal-key pairs (Kit C inside T):**
- Firedancer → later-arrived first (P ≈ 1);
- Agave → implementation-defined (descriptive only);
- BAM/Harmonic → an undocumented deterministic rule (descriptive);
- FIFO → first-sent first.

These pairs are not used as a "network noise floor".

**Two stages (pre-registered as such):**
- **Stage 1** = K-windows; identifies the compatible key set per mechanism group.
- **Stage 2** = T, H and S windows. Their parameters are a deterministic function of Stage 1 results; the function is written in the pre-registration.

### 2.5 Transport and timing

- **Sender: our own thin QUIC client.**
  - Built on `quinn` + `solana-tls-utils`: ALPN `solana-tpu`, a self-signed ed25519 client certificate, one tx per uni-stream.
  - This gives full control and logging of stream-open, write-complete and connection events.
  - `tpu-client-next` is the fallback. Its `create_pinned_leader_updater` needs `dev-context-only-utils`, so in that case we implement our own `LeaderUpdater`.
  - Connections: one persistent connection per ingress IP, opened ≥ 2 s ahead, kept alive (Agave idle timeout 30 s, Firedancer 10 s with Retry). An endpoint-aware limiter caps new connections and streams.
- **Clock.**
  - Use `slotsUpdatesSubscribe` (`firstShredReceived`) from ≥ 2 RPC endpoints. Predict the target slot-0 start from the last 2–3 slots, and subtract the measured RPC lag.
  - Log scheduled time, stream-open, write-complete and notification-receive times separately.
  - **Report local scheduling error separately from remote-arrival uncertainty.**
  - **One stable deployment location for the whole confirmatory campaign.** Default: a Frankfurt VPS (maintainer decision H2).
- **Achieved offset.** Every window is classified *post hoc* by achieved offset (send time vs. the observed `firstShredReceived` of the target's slot 0). The intended offset is the assignment; the achieved offset is the analysis variable.

### 2.6 Budget (cap 0.05 SOL, enforced; worst case when every probe lands)

| Item | Lamports |
|---|---|
| K-window (8 probes: C1 12,500 + C2 12,500 + C3 12,000 + uncontended C2 12,500) | 49,500 |
| T-window (3 races × 14,000 + equal-key pair 12,000; FD variant 2 × 14,000 + 2 × 12,000 = 52,000) | 54,000 |
| H-window (3 × 6,000) / S-window (2 × 6,000) | 18,000 / 12,000 |
| Core direct ×3: 40 K + 16 T + 6 H = 2,952,000 each | 8.86 M |
| Core shared ×3: 40 K + 16 T + 6 S = 2,916,000 each | 8.75 M |
| Extended ×4: 20 K + 6 T = 1,314,000 each | 5.26 M |
| Smoke test (cap 1.0 M) + pilot (cap 4.0 M) + funding/sweep/Memo (≈ 0.1 M) | 5.10 M |
| **Worst-case total** | **27.96 M ≈ 0.028 SOL** (44 % headroom under the cap) |
| Working capital (not spend): 24 payers × rent 650,240 + fee headroom; swept back | ≈ 0.016 SOL rent |

**Wallet to fund: ≈ 0.07 SOL.** Funding ≠ spend: the README states the cap, the planned spend and the refundable rent separately.

---

## 3. "What you will have to account for" — handling and what stays unseparated

| Brief item | Handling | Not separated (README) |
|---|---|---|
| **Leader schedule & leader types** | `getLeaderSchedule` + `getSlotLeaders` confirm windows. Leader type = clientId × version × ingress kind × Kobe `running_bam`, from snapshots before and after each window. Mode = stable / transition-ambiguous / unknown. Predecessor and successor leaders and their ingress families are recorded. **Block-structure covariates** (descending-run count, probe positions, fullness) flag windows whose structure contradicts the label. | Operator config (Firedancer pacing, Harmonic strategy, BAM plugins). Builder failover inside a slot. Per-validator ≠ per-client generalisation. |
| **Path backend → executing node** | Direct QUIC to the advertised `tpuQuic`; ingress kind recorded per window. Path diagram per ingress kind (direct / relayer / BAM node / Harmonic Remote TPU) showing the hop that reorders. **Spill-over map** (S-windows). Agave hold cliff vs Firedancer keep-all (H-windows). | Arrival time at the leader (we observe send time). The comparator inside the validator vs an identical one upstream (not identifiable from blocks). Staked/SWQoS paths (we are unstaked). |
| **Interaction of own txs** | Conflicts only through designed locks; one payer per probe per window; payers assigned at random; fresh locks; unique signatures verified before send; ≤ 14 streams per burst; persistent connections. | Sub-ms stream processing order at the receiver. |
| **Competition inside the block** | Full blocks stored for probed windows; fullness and load covariates; probe P percentile within the block; landing (inclusion) is a co-primary outcome. Load is reported descriptively, not as an exogenous adjustment. | Other senders' arrivals; the internal queue state. |
| **Send order** | Within-pair order is randomised and balanced, independent of every key. Δt races. Exact send-event logs. | — |
| **Noise vs rule** | Window = unit. Randomisation inference that follows the real assignment. Compatible-set reporting with one-sided bounds. Holm over a small confirmatory family. Simulation operating characteristics including adversarial look-alikes. Null results are first-class. | Effects below the documented minimum detectable effect. |
| **Alpenglow** | Gate check every run; slot floor at ingest and analysis. | — |

### 3.1 Identifiability table (published in the README before any result)

| Mechanisms | Separating intervention | Status |
|---|---|---|
| reward/cost vs CU price | C2, C3 | identified |
| reward/cost vs lamport fee | C1, C3 | identified |
| CU price vs lamport fee | C1, C2 | identified |
| priority fee vs total charged fee | — (1 signature ⇒ identical ranking) | **unidentified, declared** |
| priority key vs arrival (FIFO) | randomised within-pair send order, analysed in two codings (label vs send order) | identified (direct, buffered); identified within a batch for shared ingress; "unidentified behind a FIFO stage" if only a send-order effect appears |
| streaming priority vs batch auction (20/50 ms) | T-race overtaking curve | **partially**: reported as an "effective reordering horizon"; pacing/pending-queue look-alike declared |
| validator scheduler vs upstream builder with the same comparator | — | **unidentified** (topology reported instead) |
| Agave 20-slot hold vs Firedancer keep-all | H-windows | identified |
| tie rule (Firedancer LIFO prediction) | equal-key pairs at Δt ∈ {10, 40} ms in the buffered regime | identified for FD if ≥ 40 informative pairs (core + extended FD); descriptive otherwise and for other clients |

---

## 4. Analysis plan (frozen as `docs/PREREGISTRATION.md`; its hash is posted on-chain via a Memo tx before Stage 1)

### 4.1 Outcomes and cohort

- **Per probe**, one of:
  - `landed_target` (success | failure);
  - `spillover_same_validator_other_window_window`;
  - `spillover_other_leader`;
  - `expired_confirmed` (after `lastValidBlockHeight` is finalized, signature-history lookup is null);
  - `unresolved_observation_failure`;
  - `not_sent` (transport error, with reason).
- **The assigned cohort is preserved.** The funnel per target is planned → sent → any landing → joint landing → same slot → failures → spill-over → unresolved.

### 4.2 Primary (confirmatory) — per core validator × contrast C1, C2, C3

- **Window outcome** ∈ {A first, B first, only A, only B, neither} on (slot, index) over the whole window.
- **Primary estimand:** superseded — see PREREGISTRATION §1 (complete-case primary; censored coding and worst-case bounds are sensitivity analyses).
- **Inference:** randomisation test on the actual assignment (within-pair send order and labels), with window-level bootstrap CIs. The three contrasts in one window share the window, so resampling is by window.
- **Inclusion co-primary:** P(land | member), per contrast.
- **Two codings per contrast:** by label (economic key) and by send order (arrival). Both are in the confirmatory family.
- **Compatible set**, using **Holm-adjusted** one-sided bounds so that the joint coverage of the family is 95 %:
  - "favours A" requires the adjusted lower bound of P(A first) > 0.5;
  - a predicted **tie** (C3 under CU-price/lamport-fee rules, or the label coding under FIFO) requires **equivalence by TOST** with margin ±0.15 around 0.5;
  - a rule is compatible if every one of its predictions passes.

  Unadjusted bounds are shown as exploratory.
- **Strictness** = observed agreement with a Holm-adjusted one-sided lower bound. It describes ledger outcomes for our probes, not internal violations.
- **Family:** 6 core validators × {C1, C2, C3} × {label, send-order} = 36 tests, Holm at family-wise α = 0.05. Everything else is exploratory.

### 4.3 Secondary / exploratory (labelled as such everywhere)

1. **Uncontended vs contended C2** — parallel workers make the uncontended arm worker-completion order by construction on Agave. On Firedancer it may keep pack order, which would itself discriminate the clients.
2. **Effective reordering horizon** from T-races, stratified by block fullness (< 60 % vs > 90 %). The model set: step, pending-queue, linear-batch(T ∈ [10, 80] ms), constant. **Equivalent fits are reported as "unidentified".**
3. **Equal-key order** (Firedancer LIFO test; descriptive otherwise).
4. **H-cliff** (Agave −7 s drop vs Firedancer keep) and the **S spill-over map**.
5. **Block-structure:** a Chorus-comparable footrule per validator for the probed windows only (normalisation stated). Sawtooth runs are *descriptive*; BAM's leading plugin run is excluded. Bundle labels are heuristic, shown with and without exclusion.
6. **Absolute position:** probe block-index percentile vs P percentile ("free priority" figure).

### 4.4 Validation of the analysis before live data

- **Simulator** (`analysis/sim`, deliberately small). It gives operating characteristics under declared scenarios, *not* implementation truth.
- **Scenarios:**
  - reward/cost greedy-pass;
  - CU-price batch(20 | 50 ms);
  - lamport-fee batch;
  - FIFO;
  - random;
  - **adversarial look-alikes:** streaming + pacing, FIFO + ingress reordering, selective dropping of low-key probes, phase error, mode switches mid-campaign.
- **Outputs:** the probability that the compatible set contains the truth; the false-"rule" rate under random; the windows needed for a one-sided lower bound ≥ 0.9 at the expected landing rate (40–100 %).
- **Expected results:** "unidentified" for observationally equivalent scenarios.
- **Calibration:** nuisance ranges are broad in P1 and updated from the labelled pilot, then frozen.
- **Scale check:** zero violations in *w* windows gives a 95 % upper bound ≈ 3/w. This is why the core tier gets ≥ 40 K-windows.

### 4.5 Pre-registration contents (frozen before Stage 1)

- estimands and equivalence classes;
- target list with endpoints, backups and eligibility rules;
- template values and the assignment schedule;
- endpoint, connection, retry and blockhash policy;
- per-target N and the budget/time stopping rule;
- outcome definitions;
- exclusion rules (leader-type change in the window, skipped target slots, mode ambiguous, < 2 landed probes for order metrics);
- handling of missing, cross-slot and spill-over probes;
- the inference and multiplicity family;
- pooling criteria (heterogeneity check within a mechanism group);
- simulation scenarios;
- the Stage-2 parameter function;
- permitted claim language;
- "what would change our mind" per hypothesis.

Pilot data are labelled, kept and reported, and excluded from confirmatory inference.

---

## 5. System architecture (lean)

```
crates/itb/            ONE Rust binary crate, modules: config · rpc (schedule, nodes, slot updates, Kobe, Alpenglow gate)
                       · probe (atom, cost model) · design (templates, assignment) · ledger (spend cap, SQLite WAL)
                       · quic (thin sender) · clock · collect (statuses, getBlock v1, attribution) · cli
analysis/itb_analysis/ ONE Python package: load · costmodel · outcomes · stats · sim · passive · report · verify
data/raw/<run_id>/     COMMITTED: design.jsonl (frozen pre-send) · realisation.jsonl (signed bytes, sends) · outcomes.jsonl
                       · snapshots/ (gossip, Kobe, validators.app) · blocks-slim/ (probed windows only) · logs.jsonl.zst
data/derived/          regenerated offline by `docker compose up`
docs/                  PLAN · SPEC · PREREGISTRATION (+ on-chain Memo sig) · POWER · research/ · review/
docker/                itb.Dockerfile · analysis.Dockerfile · localnet.Dockerfile (agave v4.3.2 tarball, SHA-256 pinned)
```

- **Raw data.** Slim block extracts for probed windows are committed. Full raw `getBlock` JSON goes to a GitHub Release asset with a SHA-256 manifest.
- **Reproduction is offline:** `docker compose up` replays the frozen dataset with **no network and no keys, ≤ 5 min**. It:
  - validates hashes and schema;
  - recomputes every number;
  - regenerates REPORT tables/figures;
  - compares numbers with a stated tolerance (not byte-for-byte figures).
- **Separate explicit commands:**
  - `verify` — chain re-check: public-RPC sample ≤ 30 blocks by default, `--all` with a keyed RPC;
  - `dryrun` — live mainnet, no tx bytes;
  - `live` — capped sending.

### 5.1 Safety engineering (the four things Engineering 15 % names)

- **Dry-run by default, type-enforced.**
  - The transaction-submission path requires a `LiveAuthorization` value. Only the CLI can build it, and only after it has validated `--live`, `--max-spend-sol`, the keypair and the Alpenglow gate.
  - The dry-run *may* open QUIC handshakes and call RPC. The test asserts **zero transaction payload bytes submitted**.
- **Spend cap.**
  - (1) **Reservation ledger.** Reserve the worst-case fee per signed tx *before* it is sent. Unknown or unresolved outcomes stay charged. Release only on `expired_confirmed`. Retries are idempotent by signature.
  - (2) **On-chain reconciliation** over **all owned accounts**; internal transfers cancel, with no double rent adjustment. Abort if the total drop exceeds the cap.
  - (3) Per-validator and per-run sub-caps.
  - (4) **Compiled maximum = 0.05 SOL.**
  - (5) A single cumulative ledger covers smoke, pilot, campaign, funding, sweeps and the Memo.
  - **Tests:** an integration test that tries to overspend through crash/restart/unknown outcomes, and a manual mutation check (break the guard → the test must fail).
- **Keys.**
  - The master is mounted read-only at `/keys/master.json`.
  - `itb init-payers` writes the pool to a separate writable `/keys/payers/`.
  - Measurement mounts both read-only.
  - The ledger lives in `/state`.
  - gitleaks runs in CI and pre-commit. Nothing key-like is ever in the repo.
- **Logging:** `tracing` JSON with run/window/probe ids; monotonic + UTC timestamps; committed sanitised. The "What went wrong" section is generated from warn/error events plus human notes.
- **Containers:** one Compose file. Profiles: default (offline reproduce), `verify`, `dryrun`, `live`, `localnet`. Dependencies are pinned.

---

## 6. Tests (focused on what can be wrong)

| Area | Test |
|---|---|
| Cost / priority | Golden vectors from the pinned Agave/Firedancer formulas (integer rounding); `simulateTransaction` of every template (`err == null`). Requested-cost model ≠ executed `costUnits`: stored and validated separately. |
| Design | Seed determinism; contrast predictions match the table; balanced assignment; unique signatures. |
| Ledger | Overspend integration test (crash/restart/unknown/retry); reconciliation arithmetic; manual mutation check. |
| Clock | Synthetic notification streams; pilot-measured residuals. |
| QUIC sender | Localnet: probes land via the pinned connection. Limiter respects per-IP limits. Dry-run submits 0 tx bytes. |
| Collector | Fixtures for legacy/v0/v1 blocks; spill-over classes; `expired_confirmed` vs `unresolved`. |
| Analysis | Simulator scenarios recover the compatible set; random → false-rule rate ≤ 5 % per test; worked-example fixtures. |
| Reproduction | Clean clone → `docker compose up` offline → numbers within tolerance. |

**End-to-end path:**
1. **localnet** (free, solana-test-validator 4.3.2);
2. **mainnet dry-run**;
3. **mainnet smoke test ≤ 0.001 SOL** (5 ingress kinds);
4. **pilot ≤ 0.004 SOL**;
5. campaign.

Devnet is skipped: one client and empty blocks, and the faucet bars agents. Localnet plus the cheap smoke test cover it better.

**CI** (badges only for checks we run): fmt, clippy, cargo test, pytest, docker build, gitleaks.

---

## 7. Timeline & gates (HARD STOP = commit + gate report + independent clean-clone reproduction + maintainer review)

| Date (2026) | Deliverable | Gate |
|---|---|---|
| Oct 23 | Research ✔ · v1 ✔ · 3 reviews ✔ · **v2 (this)** | **HARD STOP: maintainer approval** |
| Oct 24 | **Critical path first:** probe builder + QUIC sender v0 + minimal status poller. Then the rest of the crate (config, rpc, golden cost tests, design, ledger, dry-run) and the localnet image. **Smoke test ≤ 0.001 SOL on the evening of Oct 24** if H4 is done, using the minimal sender. Targets: direct Agave, direct FD, two BAM nodes, two Harmonic IPs, one Jito relayer. Backup endpoints are pre-listed today from gossip. | soft |
| Oct 25 | Collector; localnet e2e; mainnet dry-run (clock residuals, reachability); smoke-test re-run for any failed ingress kind | **HARD STOP: target list gated on landing per ingress** |
| Oct 26 | **Pilot ≤ 0.004 SOL:** offset sweep / clock calibration, aged-blockhash trade-off, payer-pool occupancy. Analysis skeleton + simulator operating characteristics (POWER.md) | soft |
| Oct 27 | **Freeze PREREGISTRATION.md, post its hash on-chain (Memo)**; Stage 1 starts | **HARD STOP: maintainer approves campaign spend** |
| Oct 27–29 | Stage 1 (K-windows), ≥ 3 sessions, ≥ 2 days, continuous reconciliation and archiving | daily data report |
| Oct 30–31 | Stage 2 (T, H, S windows); replacements | daily data report |
| Nov 1 | Data freeze; full collection | soft |
| Nov 1–3 | Primary + exploratory analysis; verifier (claim ledger); REPORT.md (date of every measurement, "What went wrong"); README (considerations, identifiability table, path diagram, 3 worked examples) | soft → 3-model review of analysis |
| Nov 4 | Clean-clone offline reproduction; sampled chain verification; secrets sweep; independent audit; fixes | **HARD STOP before public flip** |
| Nov 5 | Repo public; submit by 12:00 UTC | — |

**Cut order** if behind:
1. S/H windows;
2. extended tier;
3. T-windows down to 2 Δt levels;
4. any interactive page.

**Never cut:** the cap, ≥ 40 K-windows on ≥ 6 validators / ≥ 3 clients, raw evidence, failures in the report, offline one-command reproduction.

**Cross-model protocol:**
- Opus 5.5 (lead) writes the core.
- **Codex (GPT-6 Astra / 6.1 Sol, via the orchestrator)** does the code review at each HARD STOP and the statistics review of PREREGISTRATION.
- **DeepSeek-V4.1-Flash** does the whole-repo consistency sweep (1 M context).
- **Fable** re-runs the adversarial design check on the frozen pre-registration and on the final report.
- At each HARD STOP an independent agent reproduces the gate from a clean clone.

---

## 8. Human steps (the agent stops and waits at each)

| # | By | Action |
|---|---|---|
| H1 | now | Approve PLAN v2 (or request changes). |
| H2 | Oct 25 | **Measurement location:** rent a small Frankfurt VPS (≈ €5/mo, Docker installed) and give the agent SSH access — *recommended*. Or decide to run from the home PC; the stated cost is coarser timing for distant validators. |
| H3 | Oct 24 | One or two keyed mainnet RPC endpoints with WebSocket (Helius free tier is enough; a second provider for the dual-RPC clock is a plus). Put them in `.env` as `RPC_URL`, `WS_URL`, `RPC_URL_2`, `WS_URL_2` — never in chat. |
| H4 | **Oct 24** (smoke test that evening) | `solana-keygen new -o <path outside repo>`, fund it with **≈ 0.07 SOL**, and tell the agent the *path* only. The 0.07 is the cap of 0.05 plus ≈ 0.016 refundable payer rent; the planned worst-case spend is ≈ 0.028. |
| H5 | optional | validators.app API token in `.env` (cross-check of client labels). |
| H6 | Nov 4–5 | Approve making the GitHub repo public (agent uses `gh` as `eternally-black`); submit on Superteam Earn; sweep the remaining SOL afterwards. |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| BAM/Harmonic reject or throttle unstaked QUIC | Smoke test on Oct 24–25 decides; acceptance is reported as a finding; backups on other endpoints. **Pre-committed fallback coverage:** (a) reach that group via RPC `sendTransaction` from one keyed provider, reported as a different path with its own caveats; (b) if a group is unreachable by any path, the core tier becomes Agave, Firedancer ×2, JitoLabs-direct, Rakurai and JitoLabs-relayer — still ≥ 6 validators and ≥ 3 client labels. Unreachability is itself reported. |
| Clock bias ≈ size of the strata | Dual-RPC `firstShredReceived`, pilot calibration, achieved-offset analysis, VPS. |
| BAM maintenance / Harmonic failover | Before/after snapshots, block-structure flags, mode ambiguity rules. |
| Survivorship (low-key probes vanish) | Inclusion is co-primary; censoring sensitivity; funnel. |
| Windows too few or too many lost | 40 K-windows per core validator; Stage-1 progress tracked daily; budget headroom 44 %. |
| RPC limits | Keyed RPC; collection decoupled; full blocks only for probed windows. |
| Over-claiming | Compatible-set language, pre-registration + on-chain hash, identifiability table. |

---

## 10. Deliverables ↔ Submission Requirements

| Requirement (verbatim key) | Deliverable |
|---|---|
| Repository | Public GitHub repo, Apache-2.0 |
| Reproducibility — one command, Docker Compose | `docker compose up` (offline replay → report); `--profile verify`, `--profile dryrun`, `--profile live` |
| Keys only via volume/env | `/keys` mounts, `ITB_KEYPAIR_PATH`; gitleaks |
| Dry-run default, live behind explicit flag with spend cap | `LiveAuthorization` type gate; compiled cap 0.05 SOL; reservation ledger |
| Raw data incl. signatures + slots | `data/raw/**`, release asset + manifest, `verify` with claim ledger |
| README: why this design / considerations / what it does NOT separate | README §Design, §Considerations, §Identifiability, §Not separated |
| Report with date of every measurement + "what went wrong" | REPORT.md (per-run UTC, epochs, slot ranges, funnel, "What went wrong") |

---

## 11. Verification UX for judges

- **`verify` prints a claim ledger.** For each claim it shows: validator, window, contrast, signatures, slot, observed indices, decoded L/p/D and fee, predicted order per rule, and pass/fail. It recomputes the statistic from the chain-verified rows.
- **Fact provenance is separated:** *chain-verifiable* (index, fee, instructions, leader), *locally recorded* (send timestamps, transport events) and *unobservable* (arrival at the leader).
- **Three worked examples** in the README:
  - a key-discriminating pair;
  - a spill-over / boundary case;
  - a genuinely inconclusive window.
- **The pre-registration hash** is posted in a mainnet Memo; its signature is in the README.

---

## 12. Review dispositions (v1 → v2)

| Finding (reviewers) | Disposition |
|---|---|
| Kit A orthogonality impossible; priority fee ≡ total fee (all 3) | **Fixed:** contrast library C1–C3; equivalence class declared. |
| Pre-window regime invalid for shared ingress (Fable, DS) | **Fixed:** regime assigned by ingress kind; S-windows as a spill-over map. |
| BAM/Harmonic unstaked acceptance unknown until the pilot (Fable) | **Fixed:** smoke test Oct 25 is a HARD STOP. |
| Simultaneous eligibility not established (GPT, DS) | **Fixed:** buffered regime for direct ingress, source-backed (Agave hold ≤ 20 slots, FD keep-all); claims conditional. |
| Survivorship / same-slot selection (all 3) | **Fixed:** inclusion co-primary; whole-window (slot, index); censoring sensitivity; funnel. |
| Dependent pairs, LR 20, ε ≤ 0.10 unreachable at N = 16 (all 3) | **Fixed:** window = unit, randomisation inference, compatible sets, one-sided bounds, ≥ 40 K-windows. |
| Agave reverse-arrival tie-break unsupported (Fable, DS, GPT) | **Fixed:** Slab-id ⇒ descriptive; Firedancer LIFO prediction added; tie pairs Δt-spaced. |
| BAM cadence 20 ms vs 50 ms (GPT) | **Fixed:** separate hypotheses, horizon range kept open. |
| Kit B measures queueing unless above marginal (Fable); Kit B slot-crossing (DS, GPT) | **Fixed:** Stage-2 races above marginal on the identified key; no straddling; pending-queue model; load strata. |
| Clock precision ≠ accuracy (GPT, Fable, DS) | **Fixed:** dual-RPC `firstShredReceived`, separate logs, achieved offset, single location, VPS default. |
| Atom L = 450 fails; omitted ix changes shape (GPT, Fable) | **Fixed:** L ≥ 1000, 3 CB ixs always, D explicit. |
| Connection limits (8 new/IP/min silently ignored) (Fable) | **Fixed:** persistent connection per IP + limiter. |
| Payer pool underfunded / treatment-correlated (DS, GPT) | **Fixed:** random assignment, fee headroom, aged blockhash, isolation until resolved. |
| Requested cost ≠ `costUnits` (GPT) | **Fixed:** stored and validated separately. |
| Firedancer allocation module weak (GPT) | **Cut** from the minimum campaign. |
| Passive census infeasible (GPT) | **Cut** to probed windows plus a comparability metric. |
| Over-engineering / timeline (all 3) | **Fixed:** one crate, one package; no site/Old Faithful/mutants in the critical path; smoke test and pilot moved earlier. |
| Default reproduce depends on the live network (GPT) | **Fixed:** offline replay by default; network commands separate. |
| Verifier proves too little (GPT) | **Fixed:** claim ledger with decoding, predictions, recomputed stats, provenance classes. |
| Outcome states incomplete (GPT) | **Fixed:** explicit status taxonomy incl. `unresolved`. |
| Scope over-claims universality (GPT) | **Fixed:** claims scoped to probe shape / endpoint / dates; v1 and app txs are external-validity limits. |
| Compiled max 0.1 SOL contradicts brief (Fable) | **Fixed:** 0.05 SOL. |
| Key volume read-only vs payer generation (GPT) | **Fixed:** separate writable `/keys/payers` init step. |
| Pre-registration timestamp (GPT, Fable) | **Fixed:** on-chain Memo of the hash. |
| Kit C as noise floor (GPT) | **Fixed:** descriptive equal-key experiment only. |
| VPS required (DS, Fable) | **Adopted as default** (maintainer decision H2). |
| Signature grinding for tie ids (DS) | **Rejected:** Agave ids are Slab keys, not derivable from signatures. |
