# Does the method work? — operating characteristics

Before any live data, the pre-registered procedure is run on **simulated campaigns whose true ordering mechanism is
known**. The simulation is written in the exact raw format of [DATA.md](DATA.md). What gets scored is the
**published claim** of each validator, produced by `report.analyse`, the same function that produces REPORT.md. That
covers:

- design validation and eligibility;
- the (client, ingress) grouping;
- the 36-effect inference;
- the strictness split (R vs partial:R);
- the selection check;
- the §9 gates (positive controls, buffer assumption).

Before scoring, the pre-registered stopping rule truncates each simulated campaign using the very predicate `itb run`
uses.

- Simulator: [`analysis/itb_analysis/sim.py`](../analysis/itb_analysis/sim.py)
- Scoring: [`analysis/itb_analysis/oc.py`](../analysis/itb_analysis/oc.py)

## Reproduce

```bash
PYTHONPATH=analysis python -m itb_analysis.oc --design design/design.jsonl --targets design/targets.json \
  --reps 100 --n-draws 2000 --out data/derived/oc.json --markdown data/derived/oc.md
```

- Replicate *r* of every scenario uses seed 1000 + *r*, so the numbers do not depend on `--jobs`.
- Design: the **frozen** `design/design.jsonl`, SHA-256 `cdca861b32af78fe89417a4348f118481f1153adde7616aef227487cb6f5d828` (in the pre-registration Memo), written by `itb design --seed 20261023`: 10 targets (6 core, 4 extended), 796 windows.
- A pre-freeze run of this study on a draft design gave the same picture within 3 percentage points in every cell. The draft came from an older build of the generator. The frozen pre-registration quotes that run's censored-coding figures (50 % and 51 %); the frozen-design figures are below (47 % and 48 %).

## What is simulated

**Windows.** Each leader window is finite: four slots of ≈ 130 ms, the observed post-Alpenglow in-window cadence.
- Each probe arrives at its designed send offset plus 30 ms of path latency and 0.02 ms of independent jitter; back-to-back streams are 0.05 ms apart.
- A probe scheduled after the window spills to the next leader (shared ingress) or expires (direct ingress).
- Landed probes get random positions in blocks of 200–1500 transactions, in the scheduler's order.

**Landing and observation.**
- Each probe lands independently with probability 0.9 (0.5 in the low-landing scenarios).
- In every window there is a 2 % chance that one stream fails (a transport error), a 2 % chance that the leader produces no block, and a 3 % chance that gossip changes the advertised TPU mid-window.
- These exercise the eligibility rules and the stopping predicate: transitions still count for stopping but are excluded from inference, exactly as on mainnet.

**Positive controls.** The two positive controls (the direct-ingress Agave and Firedancer core targets) follow reward/cost in every scenario, as their public code does. Every other target follows the scenario's mechanism. If a control fails, the §9 gate withdraws every other claim, and that shows up as "withdrawn" (an honest non-claim) below.

| Scenario | Mechanism | Why it is here |
|---|---|---|
| `reward_cost_greedy` | Streaming priority scheduler: a pass every 1 ms (random phase), available items in reward/cost order | Agave / Firedancer, the positive controls |
| `reward_cost_batch_20` | 20 ms auctions by reward/cost | A batching builder with the Agave comparator |
| `cu_price_batch_20`, `cu_price_batch_50` | 20 / 50 ms auctions by CU price | A builder ranking by CU price |
| `cu_price_fifo_tie` | CU-price auctions; key ties broken by arrival | Tie-breaks must not count against the comparator ("any") |
| `lamport_fee_batch_50` | 50 ms auctions by lamport fee | The third comparator |
| `fifo` | Arrival order | Rule without a key |
| `random` | Random order | No rule |
| `streaming_pacing` | One item every 20 ms, best reward/cost first | Look-alike: pacing that distorts arrival |
| `fifo_reorder` | Arrival order plus 2 ms label-blind noise | Look-alike: noisy FIFO |
| `label_blind_reorder` | FIFO, each pair reversed with p = 0.35 regardless of labels | Look-alike built to fool a mixture diagnostic |
| `selective_drop_cu_price` | CU-price auctions; the lower-key member is dropped with p = 0.5 | Inclusion and ordering that both depend on the key |
| `correlated_pair_loss` | FIFO; whole pairs lost (p = 0.8) when x was sent second | Selection that unbalances send order: must end in `unidentified:selection` |
| `balanced_double_loss` | Label-blind order (the winning *send position* is drawn per window); both members of a C1/C2 pair are lost whenever that order would make y win | The gate-1b counterexample: the retained pairs are balanced and x wins all of them. The balance check cannot see it; the worst-case bounds must |
| `mode_switch_rc_fifo` | Each window is reward/cost or FIFO with p = ½ | A leader that changes mode (BAM/Harmonic connects and disconnects) |
| `low_landing_reward_cost`, `low_landing_cu_price` | As above, landing probability 0.5 instead of 0.9 | Power at poor inclusion |

**Scoring.**
- *Correct*: the claim names the true mechanism. For a mode-switching leader, `partial:R` and `mixed:fifo+R` name it.
- *Honest non-claim*: `none`, `unidentified`, `unidentified:selection`, a withdrawn claim, or an under-claim (`partial:R` when the truth is R: R's key named, majority not proven). Not a full detection, but not a false statement either.
- *Wrong*: any other claim, i.e. a rule or mixture the scenario does not contain.
- *Any core target wrong*: the share of replicate campaigns in which at least one of the core validators (the controls excluded) got a wrong claim. This is the family-wise error a reader cares about; the exact 95 % upper bound is in brackets.
- *Robust wrong*: the same, counting only wrong claims that survive the worst-case selection bounds, i.e. claims published *without* the "(assumes selection)" qualifier.
- *Controls pass*: replicates in which both positive controls ended with a reward/cost claim (`reward_cost` or `partial:reward_cost`), the §9 condition.

## Results (the published procedure, 100 replicate campaigns per scenario)

| Scenario | True mechanism | Correct | Honest non-claim | Wrong | Any core target wrong (≤ 95 % bound) | Robust wrong | Controls pass | Median C1 pairs |
|---|---|---|---|---|---|---|---|---|
| `reward_cost_greedy` | reward_cost | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 34 |
| `reward_cost_batch_20` | reward_cost | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `cu_price_batch_20` | cu_price | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `cu_price_batch_50` | cu_price | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `cu_price_fifo_tie` | cu_price | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `lamport_fee_batch_50` | lamport_fee | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `fifo` | fifo | 96 % | 3 % | 2 % | 7 % (≤ 13 %) | 0 % | 100 % | 34 |
| `random` | none | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `streaming_pacing` | reward_cost | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `fifo_reorder` | none | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `label_blind_reorder` | fifo / partial:fifo | 0 % | 100 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `selective_drop_cu_price` | cu_price | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 21 |
| `correlated_pair_loss` | unidentified:selection | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 26 |
| `balanced_double_loss` | none / unidentified / unidentified:selection | 0 % | 0 % | 100 % | 100 % (≤ 100 %) | 0 % | 100 % | 21 |
| `mode_switch_rc_fifo` | mixed:fifo+reward_cost / partial:reward_cost / partial:fifo | 14 % | 86 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `low_landing_reward_cost` | reward_cost | 48 % | 52 % | 0 % | 0 % (≤ 3 %) | 0 % | 83 % | 13 |
| `low_landing_cu_price` | cu_price | 78 % | 22 % | 0 % | 0 % (≤ 3 %) | 0 % | 83 % | 13 |

Raw numbers: [`data/derived/oc.json`](../data/derived/oc.json), computed on 2026-10-24 on the frozen design, with the procedure at the commit that adds these numbers.

**Reading the table.**
- **Strict rules at 90 % landing** — every economic rule, FIFO, and the pacing and tie-break look-alikes. The published claim names the true mechanism for 96–100 % of core validators, and the family-wise error is at most 3 % (exact 95 % bound), except FIFO.
- **FIFO:** a 7 % family-wise error, ≤ 13 % bound. Its wrong claims (2 % of core validators) are `mixed:fifo+R`, which is never selection-robust and is always published with "(assumes selection)". "Robust wrong" is 0 % in every scenario.
- **`balanced_double_loss` (the gate-1b counterexample):** the complete-case analysis is fooled almost every time, exactly as the reviewer showed. The balance check cannot see it. Not one of those claims survives the worst-case selection bounds, so every one is published with the qualifier. The qualifier is what keeps a selection artefact from being reported as a finding.
- **Look-alikes that a correct analysis should *not* call a rule** — `random`, `fifo_reorder` (2 ms label-blind noise against 0.05 ms send spacing) and `label_blind_reorder` (FIFO reversed in 35 % of pairs regardless of labels). They end as `none` or `unidentified`. For `label_blind_reorder` that is an under-detection of a weak FIFO, never a false key.
- **`mode_switch_rc_fifo`:** no wrong claim. 14 % name the switch (`partial:reward_cost`, `partial:fifo`, `mixed:fifo+reward_cost`); the rest are honest non-claims. Without the governed-share split, this scenario produced a plain "reward_cost" for 10 % of core validators (an earlier run of this study).
- **Low landing (0.5).** Power drops: 48 % / 78 % correct, still with no wrong claim. The 80-window plans run out at a median of 13 complete pairs per contrast. In 17 % of campaigns a positive control misses reward/cost at that sample size, and the §9 gate then withdraws every other claim (counted as honest). The live campaign checks landing rates in the pilot and reports them per validator.
- **Median complete pairs per contrast (≈ 35 at 90 % landing).** This is below the stopping target of 40. Stopping counts windows that later turn out transition-ambiguous (3 % per window here), and those are excluded from inference. PREREGISTRATION §5 reports the shortfall.

## Censored coding (sensitivity) vs complete-case (primary)

| Scenario | True mechanism | Correct | Honest non-claim | Wrong | Any core target wrong (≤ 95 % bound) | Robust wrong | Controls pass | Median C1 pairs |
|---|---|---|---|---|---|---|---|---|
| `reward_cost_greedy` | reward_cost | 47 % | 53 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 42 |
| `cu_price_batch_20` | cu_price | 79 % | 21 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 42 |
| `low_landing_reward_cost` | reward_cost | 0 % | 100 % | 0 % | 0 % (≤ 3 %) | 0 % | 0 % | 44 |
| `low_landing_cu_price` | cu_price | 0 % | 100 % | 0 % | 0 % (≤ 3 %) | 0 % | 0 % | 39 |

The censored coding counts a member that did not land as ordered after every member that landed. It recovers reward/cost in 47 % of campaigns at 90 % landing (complete-case: 99 %) and in 0 % at 50 % landing (complete-case: 48 %). Landing noise enters every observation, which is why complete-case is the pre-registered primary estimand and censored coding a sensitivity analysis (PREREGISTRATION §1, §6). Raw numbers: [`data/derived/oc.censored.json`](../data/derived/oc.censored.json).

## What this does not show

- **The simulated schedulers are stylised.** They model observable consequences (queueing, auctions, pacing, loss), not any client's code. A real mechanism outside this list can produce `unidentified` or `none`. It produces a confident wrong rule only if it mimics one of the prediction patterns, and then the strictness, selection and gate diagnostics are what remain.
- **Unresolved outcomes are not simulated.** A probe whose status could not be resolved leaves its pair incomplete, exactly like a non-landing, and the low-landing scenarios cover that.
- **Landing is independent across probes**, except in the selection scenarios.
- **The p-values here use 2,000 randomisation draws**; the report uses 100,000. Verdicts rest on the Clopper–Pearson / TOST decisions, which do not depend on draws. The mixture diagnostic does, but 2,000 draws resolve p ≈ 5·10⁻⁴, below its Holm thresholds.
