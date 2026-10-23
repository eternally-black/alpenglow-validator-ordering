# Pre-registration — Inside the Block

> **Status: DRAFT.** Frozen after the pilot, before Stage 1 (target date 2026-10-27).
> On freezing:
> - the SHA-256 of this file and of `design/design.jsonl` are posted on Solana mainnet in a Memo transaction signed by the measurement wallet;
> - the Memo signature is added to the README;
> - any later change is listed under "Deviations" in REPORT.md, with its reason.
>
> Pilot data are kept and reported, and excluded from confirmatory inference.

## 1. Estimands

For each target validator **V**, reached through its advertised ingress endpoint **E**, on the campaign dates:

1. **Label effect** of contrast C ∈ {C1, C2, C3}: **L_C = P(x lands before y)**. Here x is the first label of the contrast table (C1: A, C2: A′, C3: A) and y is the second (C1: B, C2: B, C3: A′). Probabilities are averaged over the balanced, randomised send order.
2. **Send-order effect** of the same pairs: **O_C = P(the first-sent member lands before the second-sent member)**.
3. **Inclusion**: P(member lands in V's targeted window), per label.

"Lands before" uses the lexicographic order (slot, index-in-block) over the whole targeted window. A member that did not land in the window (expired, spill-over or unresolved) is ordered **after** every member that did. A pair where neither member landed contributes no ordering observation; it is counted in the funnel.

These are statements about our probes' ledger outcomes on that path. They are not observations of the scheduler's internal state.

## 2. Unit, eligibility, exclusions

- **Unit:** one targeted leader window. Each K-window gives **one binary observation per contrast** (y_w for L, z_w for O). Windows are treated as independent; §6 gives a session-cluster sensitivity analysis.
- **Evaluable K-window** — all must hold:
  - (a) every planned probe was written to the QUIC stream without transport error;
  - (b) the leader mode is **stable**: the nearest gossip snapshots before and after the window agree on `clientId`, `tpuQuic` and ingress kind;
  - (c) the target produced at least one block in the window;
  - (d) the window's slots are ≥ 459,653,008 (post-Alpenglow).
- **Excluded windows** are counted by reason in the funnel. They are never silently dropped.

## 3. Rule predictions (label coding)

| Rule | C1 (A vs B) | C2 (A′ vs B) | C3 (A vs A′) | Send-order coding |
|---|---|---|---|---|
| CU price | x (A) | x (A′) | tie | tie |
| lamport fee (≡ total fee at 1 signature) | y (B) | y (B) | tie | tie |
| reward/cost (Agave/Firedancer priority) | x (A) | y (B) | x (A) | tie |
| arrival (FIFO) | tie | tie | tie | first-sent first |
| no rule (random) | tie | tie | tie | tie |

## 4. Inference (confirmatory family)

- **Family:** 6 core validators × 3 contrasts × 2 codings = **36** effects. Each estimate is a binomial proportion over evaluable windows.
- **Intervals:** exact Clopper–Pearson, **Bonferroni-adjusted for the family** (two-sided level 1 − 0.05/36).
- **Directional prediction ("favours x"):** confirmed if the adjusted interval lies entirely above 0.5. Contradicted if it lies entirely below.
- **Tie prediction:** confirmed by equivalence (TOST): the adjusted interval at level 1 − 2·0.05/36 lies within **[0.35, 0.65]**. Contradicted if the adjusted interval excludes 0.5. Otherwise undetermined.
- **Rule status per validator:**
  - **REJECTED** = any prediction contradicted;
  - **CONFIRMED** = every prediction confirmed, ties by equivalence;
  - **SUPPORTED** = every *directional* prediction confirmed and no tie prediction contradicted. At 40 windows a family-level equivalence test is usually too wide to confirm a tie (a perfect 20/40 does not pass), so ties are allowed to be undetermined here;
  - **UNDETERMINED** = otherwise.
  - The "random" rule makes no directional prediction, so it can only be CONFIRMED, REJECTED or UNDETERMINED (= not rejected).
  - Every pair of candidate rules differs in at least one directional prediction (§3), so at most one non-random rule can be SUPPORTED for a validator.
- **Reporting:** we report the full set of non-rejected rules. "No rule detectable at our power" means no non-random rule is SUPPORTED or CONFIRMED; that is reported as a finding.
- **Randomisation p-values** accompany every estimate, under sharp nulls that respect the actual assignment (the within-pair send order, balanced by design):
  - **Label null** ("outcome depends only on send position"): z_w is fixed; re-draw the balanced send-order assignment; y_w is recomputed.
  - **Order null** ("outcome depends only on label"): y_w is fixed; re-draw the assignment; z_w is recomputed.
  - 100,000 Monte Carlo draws, seeded. Holm over the 36 p-values.
- **Strictness** of a confirmed rule = the share of evaluable windows (pooled over the contrasts where it predicts a direction) whose outcome matches, with a one-sided 95 % Clopper–Pearson lower bound.
- **Inclusion:** per-label landing rates with Clopper–Pearson intervals. The paired x-vs-y difference within windows uses an exact McNemar test (exploratory if it is not part of a rule decision).

## 5. Stopping, sample size

- **Target: 40 K-windows** per core validator, 20 per extended validator.
- **Stop when any of these happens:**
  - the target is reached;
  - the spend ledger's headroom falls below one window's worst-case fee;
  - **2026-10-29 23:59 UTC** (end of Stage 1).
- **No early stopping on results.** Shortfalls are reported as such.

## 6. Pre-specified sensitivity analyses

1. Complete-case: only windows where both members landed in the target window.
2. Worst-case bounds: non-landed members placed adversarially (first / last).
3. Session-cluster bootstrap (sessions = contiguous run invocations): intervals for L and O.
4. Regime split for direct ingress: buffered vs streaming.
5. Achieved-offset bins (send time vs the observed first shred of the anchor slot).
6. Including transition-ambiguous windows.

## 7. Exploratory (labelled as such everywhere)

- uncontended C2 vs contended C2;
- T-kit effective reordering horizon (step / pending-queue / linear-batch(T ∈ [10, 80] ms) / constant), stratified by block fullness. Equivalent fits are reported as unidentified;
- equal-key order, with the Firedancer later-arrival-first prediction. This counts as identified only with ≥ 40 informative pairs;
- H-kit hold cliff (Agave ≤ 20 slots; Firedancer keeps until blockhash expiry);
- S-kit spill-over map;
- block structure: Chorus-style footrule, descending-run counts (descriptive), probe block-index percentile vs priority percentile.

## 8. Stage-2 parameter function (deterministic)

- **Races:** for each mechanism group, the "hi" and "lo" race templates stay as designed if Stage 1 confirms or leaves undetermined reward/cost or CU price for that group. In both cases both race members are above the observed block marginal on that key: our probes' P ≈ 10⁶ ≫ typical, and p = 10⁶–3·10⁶ µL/CU ≫ the median CU price.
- **Lamport-fee groups:** if Stage 1 confirms the lamport-fee rule for a group, its race members are declared "not above marginal". The race analysis for that group is then descriptive only.

## 9. What would change our mind

| Observation | Conclusion we would draw |
|---|---|
| L_C3 ≈ 0.5 with equivalence on Agave/Firedancer (positive controls) | Our method fails to detect the documented reward/cost rule → the report says so, and no conclusion is drawn for closed-source clients. |
| O_C ≫ 0.5 on direct ingress in the buffered regime | The buffer assumption is wrong (probes did not coexist in the queue); key conclusions for that group are withdrawn. |
| Strong label effects only in streaming windows | The ordering happens upstream of the regime we thought we controlled → reported as such. |

## Deviations

(none yet — filled in REPORT.md after freezing)
