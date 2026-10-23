# Pre-registration — Inside the Block

> **Status: DRAFT.** Frozen after the pilot, before Stage 1 (target date 2026-10-27). This document is the
> **normative** analysis plan. Where PLAN.md or other documents differ, this document wins.
>
> On freezing:
> - the SHA-256 of this file, of `design/design.jsonl` and of `design/campaign.json` (the campaign manifest: core targets, positive controls, design and genesis hashes, stop date) are posted on Solana mainnet in a Memo transaction signed by the measurement wallet. `scripts/freeze.py` writes the manifest and prints the Memo text;
> - the Memo signature is added to the README;
> - any later change is listed under "Deviations" in REPORT.md, with its reason.
>
> Pilot data are kept and reported, and excluded from confirmatory inference.
>
> Implementation: `analysis/itb_analysis/stats.py` (§3–§4), `outcomes.py` (§1–§2), `report.py` (§6, §9), and `itb run` (§5).

## 1. Estimands

For each target validator **V**, reached through the ingress endpoint actually used in each window, on the campaign dates:

1. **Label effect** of contrast C ∈ {C1, C2, C3}: **L_C = P(x lands before y)**. x is the first label of the contrast table (C1: A, C2: A′, C3: A); y is the second (C1: B, C2: B, C3: A′).
2. **Send-order effect** of the same pairs: **O_C = P(the first-sent member lands before the second-sent member)**.
3. **Inclusion**: P(member lands in V's targeted window), per label.

"Lands before" uses the lexicographic order (slot, index-in-block) over the whole targeted window. Only verified landings count: the signature has a confirmed status **and** was found in the archived block.

- **Primary (complete-case):** L and O are estimated over pairs where **both** members landed in the targeted window: "when both are included, which comes first".
- **Co-primary inclusion analysis (estimand 3).**
- **Sensitivity (censored coding, §6):** a non-landed member counts as after every landed one. Simulation (POWER.md) shows this coding loses most of its power at landing rates ≤ 0.6, which is why it is not primary.
- **Pairs where neither member landed** contribute nothing; they are counted in the funnel.

**Selection assumption.** The complete-case comparison and its randomisation tests are valid if the set of analysed pairs does not depend on the send-order assignment. This is checked, not assumed:
- among analysed pairs, the share with x sent first must be compatible with 0.5 (exact binomial, two-sided, p ≥ 0.01, per contrast);
- if it is not, the validator's verdict is **unidentified:selection** and no label/order claim is made for it;
- the worst-case bounds of §6 show how far single-landed pairs could move each L_C.

These are statements about our probes' ledger outcomes on that path. They are not observations of the scheduler's internal state.

## 2. Unit, eligibility, exclusions

- **Unit:** one targeted leader window. Each K-window gives **one binary observation per contrast and coding**. Windows are treated as independent; §6 adds a session-cluster bootstrap.
- **Evaluable K-window** — every one of these must be *established*. Missing evidence is ineligible, never assumed:
  - (a) every planned probe (count from the frozen plan) was logged and written to the QUIC stream with no transport error and none left unsent;
  - (b) the leader mode is **stable**: one gossip snapshot at or before and one after the window's estimated start, both within 90 s, agree with each other on `clientId`, `tpuQuic` and ingress kind, *and* with the endpoint the window actually used;
  - (c) `getBlocks` affirmatively shows at least one block produced in the window's slots;
  - (d) the window's slots are ≥ 459,653,008 (post-Alpenglow), on the mainnet-beta genesis.
- **Excluded windows** are counted by reason in the funnel (`exclusion` field). They are never silently dropped.
- **Grouping:** a validator is analysed separately for each (clientId, ingress kind) observed in its windows.

## 3. Rule predictions

| Rule | L_C1 | L_C2 | L_C3 | O_C1 | O_C2 | O_C3 |
|---|---|---|---|---|---|---|
| CU price | x | x | tie | tie | tie | any |
| lamport fee (≡ total fee at 1 signature) | y | y | tie | tie | tie | any |
| reward/cost (Agave/Firedancer priority) | x | y | x | tie | tie | tie |
| arrival (FIFO) | tie | tie | tie | first | first | first |
| no rule (random) | tie | tie | tie | tie | tie | tie |

- **"any"** = no prediction. On a contrast where the rule's key is tied, the tie-break is unspecified (FIFO, LIFO, …), and a tie-break must not count as evidence against the comparator.
- **Why "tie" in the send-order coding:** for a deterministic key, the first-sent member wins exactly when it is the key-preferred one. That happens in half the windows by design.

## 4. Inference

**Confirmatory family:** 6 core validators (from the manifest) × 3 contrasts × 2 codings = **36** effects. Each is a binomial proportion over evaluable windows; the contrasts are never pooled into one denominator.

**Decision rules:**
- **Intervals:** exact Clopper–Pearson, **Bonferroni-adjusted** (two-sided level 1 − 0.05/36).
- **Directional prediction** (x / y / first): confirmed if the adjusted interval lies entirely on the predicted side of 0.5; contradicted if entirely on the other side.
- **Tie prediction:** confirmed by TOST equivalence (interval at level 1 − 2·0.05/36 within **[0.35, 0.65]**); contradicted if the adjusted interval excludes 0.5; otherwise undetermined.

**Rule status per validator**, over its six predictions ("any" ignored):
- **REJECTED** — any contradicted;
- **CONFIRMED** — all confirmed;
- **SUPPORTED** — all directional predictions confirmed and no tie contradicted;
- **UNDETERMINED** — otherwise.

Every pair of non-random rules differs in at least one directional prediction, so at most one can be SUPPORTED.

**Randomisation p-values (two-sided)**, under sharp nulls that respect the balanced send-order assignment:
- **label null** — z_w fixed, assignment re-drawn;
- **order null** — y_w fixed, assignment re-drawn.

Settings: 100,000 seeded draws, Holm over the fixed family of 36 (missing effects count as p = 1).

**Verdict per validator:**

| Verdict | Condition |
|---|---|
| **R** | exactly one economic rule R is SUPPORTED/CONFIRMED |
| **fifo** | FIFO is SUPPORTED and the mixture diagnostic names nothing |
| **mixed:fifo+R** | FIFO is SUPPORTED and the mixture diagnostic names exactly one R |
| **unidentified** | no rule is SUPPORTED, but random is REJECTED (systematic, not one of ours) |
| **none** | no rule SUPPORTED and random not rejected (no rule detectable at our power) |
| **unidentified:selection** | the selection check (§1) failed; overrides every other verdict |

**Secondary diagnostics** (outside the 36-effect family; reported with their own Holm correction):
- **Strictness** of rule R, computed at the window level: the share of windows in which *all* of R's directional label predictions held. One Bernoulli trial per window, with a one-sided 95 % Clopper–Pearson lower bound. For FIFO: windows where the first-sent member won in every contrast.
- **Mixture diagnostic.** Per window, d_w = (share of R's directional contrasts won by R's preferred member) − 0.5.
  - A sign-flip randomisation test over windows tests whether a key-dependent component exists.
  - The test is valid because, under any label-blind mechanism (arrival order plus label-blind noise), d_w is symmetric about 0.
  - R is named only if Holm-significant over the three economic rules **and** every directional contrast of R points R's way.
  - It never resurrects a rule outside the FIFO-supported case.
- **Inclusion:** per-label landing rates with Bonferroni-adjusted Clopper–Pearson intervals, and the exact McNemar test for the paired x-vs-y difference.

## 5. Stopping, sample size

- **Target per validator:** 40 informative pairs for each of C1, C2, C3 (core) or 20 (extended).
- **One operational definition, shared by `itb run` and the simulation.** An informative pair needs all of:
  - its window had every planned probe sent without transport error;
  - `getBlocks` showed the target produced a block in it;
  - both members of the pair landed (verified) in the targeted window.

  Gossip mode stability is known only after the next snapshot, so it is not part of the stopping count. Windows later found transition-ambiguous are excluded from inference; the resulting shortfall is reported.
- **The design holds 80 (core) / 40 (extended) K-window plans**, executed in order, at most one window in flight per target. Probes that do not land cost nothing.
- **Stop a target when any of these happens:**
  - the informative target is reached;
  - its plans run out;
  - the ledger's headroom falls below one window's worst-case fee;
  - **2026-10-29 23:59 UTC** (`--not-after`).
- **The rule counts landing only, never ordering outcomes.** Each count is journalled durably per window (`informative_pairs` in the attempt journal).

## 6. Pre-specified sensitivity analyses (all emitted by `report.py`)

1. **Censored coding**: non-landed members ordered last.
2. **Worst-case bounds**: every single-landed pair counted against / for x (L_min, L_max).
3. **Session-cluster bootstrap** (sessions = run invocations): percentile intervals for L_C.
4. **Regime split** (buffered vs streaming).
5. **Achieved-offset bins**: first stream finished vs the observed first shred of the target's first slot; bins <−100, −100..0, 0..100, >100 ms.
6. **Including transition-ambiguous windows.**

## 7. Exploratory (labelled as such everywhere)

- **Uncontended vs contended C2.**
- **T-kit effective reordering horizon**, stratified by block fullness. The candidate models:
  - step;
  - pending-queue;
  - linear-batch (T ∈ [10, 80] ms);
  - constant.

  Equivalent fits are reported as unidentified. Races are anchored on the target's first slot, with Δt ∈ {5, 25, 60, 100} ms.
- **Equal-key order**, with the Firedancer later-arrival-first prediction. Identified only with ≥ 40 informative pairs.
- **H-kit hold cliff:** sends at −0.5 s, −3 s and −7 s. Agave holds ≤ 20 slots (≈ 4.7 s); Firedancer keeps until blockhash expiry.
- **S-kit spill-over map.**
- **Block structure:**
  - a Chorus-style footrule;
  - descending-run counts (descriptive);
  - each probe's block-index percentile vs its priority percentile.

## 8. Stage-2 parameter function (deterministic)

- **Races:** the "hi" and "lo" race templates stay as designed if Stage 1 leaves reward/cost or CU price SUPPORTED/UNDETERMINED for a mechanism group. In both cases both members are above the block marginal on that key.
- **Lamport-fee groups:** if Stage 1 SUPPORTS the lamport-fee rule for a group, its races are declared "not above marginal" and the race analysis is descriptive only.

## 9. What would change our mind (implemented as report gates)

| Observation | Conclusion |
|---|---|
| reward/cost not SUPPORTED/CONFIRMED on the positive controls (vanilla Agave, Firedancer) | The method failed on a known rule. The report states it, and conclusions for closed-source clients are withdrawn (`closed_source_conclusions_withdrawn`). |
| O_C confirmed "first" on direct ingress in the buffered regime | The buffer assumption is wrong (probes did not coexist in the queue). Key conclusions for that group are withdrawn (`gates.buffer_assumption_broken`, `key_conclusions_withdrawn`). |
| Label effects only in streaming windows | The ordering happens upstream of the regime we thought we controlled; reported as such (`gates.label_effects_streaming_only`). |
| Selection check fails | `unidentified:selection` for that validator. |

## Deviations

(none yet — filled in REPORT.md after freezing)
