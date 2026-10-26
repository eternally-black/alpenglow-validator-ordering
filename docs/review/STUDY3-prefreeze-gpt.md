# Study 3 pre-freeze review — 2026-10-26

**Verdict: do not freeze this snapshot.** Findings 1–2 are blockers. This review includes concurrent, uncommitted edits over HEAD `34e072072033bf705eadcc949373a873e1cd7ce2`; the original selection-qualifier omission was corrected during review. Only this report was written by this reviewer.

## BLOCKER

1. **The executable template and registered design disagree.** `crates/itb/src/probe.rs:125` now defines Y as **L=1,500, price=4,000,000**, cost 2,835, priority 2,997,179. `docs/PREREGISTRATION-3.md:44`, `docs/STUDY3-PLAN.md:12`, and every Y in `design/design-study3.jsonl` still specify **L=3,000, price=2,000,000**, cost 4,335. `design.rs:772` validates each label against the current library, so the existing design fails before collection. The Python fixtures still exercise the old Y, explaining why their tests pass.

   The revision also matters scientifically: with the original Y, a builder using retained reward/requested CU puts **A first**: 3,500/1,000 > 8,500/3,000. A builder using total charged fees/full modeled cost also puts A first: 6,000/2,335 > 11,000/4,335. Neither is Agave's formula, but both are plausible builder comparators. The revised Y avoids these reversals.

   **Fix:** choose one Y before freezing; synchronize both documents, generated design, fixtures, golden arithmetic and operating characteristics. Regenerate and validate with the final binary, then hash those exact inputs. Keep the original 08:53 dry run labeled as testing the original design.

2. **A new verdict converts non-significance into rejection.** `analysis/itb_analysis/study3.py:124–125` says “C4 rejects reward ÷ cost” whenever H5 is supported but H4 is not. This contradicts `PREREGISTRATION-3.md:86–87,98`. Reproduced with all controls passing: a non-control target with **C4=20/32**, adjusted p=**0.107664**, and **C5=32/32** receives that verdict, although C4's estimate is **0.625**, in reward/cost's direction. `test_study3.py:98` currently asserts the incorrect wording.

   **Fix:** report “equal-cost reward effect supported; C4 inconclusive.” Describe a cost-first/reward-tie-break model as compatible only when warranted; do not identify it from failure to reject. Keep the registered below-0.5 interval diagnostic explicitly descriptive, or register a separately corrected opposite-direction test.

## SHOULD-FIX

3. **The combined result identifies a finite candidate set, not the formula.** `PREREGISTRATION-3.md:96,126–132` and `study3.py:119` need the same scope. A concrete surviving alternative is descending **reward − λ·requested cost**, with λ=1 lamport/cost-unit. Scores for A, B, A′, original Y, hi are **1,165; −335; −15,211; 4,165; 3,165**. Revised Y scores 5,665. This gives the reward/cost winners on **C1–C5**, the dominance race and equal-template ties. A revenue optimizer using a shadow price for capacity could implement it.

   Combining prior claims also assumes a stable comparator across dates and regimes; the frozen client/ingress names do not establish builder strategy stability. [Harmonic documents multiple strategies and custom schedulers](https://docs.harmonic.gg/concepts/scheduling-strategies). BAM/Harmonic observations identify the measured path, not its internal queue. Cost-only using consumed CU would tie these 600-CU probes rather than predict A strictly on C4.

   **Fix:** preserve “among the registered candidates” in generated verdicts; name the additive counterexample and the cross-study stability assumption in §10. Define the rejected cost-only model specifically as ascending registered requested cost. A broader formula claim needs further contrasts.

4. **Selection qualifications and the control gate remain inconsistent.** `study3.py:89–97,110–125`; `PREREGISTRATION-3.md:88–104`. Both-supported verdicts now retain “assumes selection,” but H4-only support still produces unqualified “cost alone rejected.” Controls can also pass the gate with both claims conditional on selection. For example, **20 complete successes plus 12 incomplete pairs** gives strong complete-case support but worst-case p=**0.107664**; such controls permit unqualified identification for other targets. Separately, the new identification Boolean requires robustness, while normative §5 only requires published support.

   **Fix:** propagate selection qualifications through every derived verdict. Specify whether conditional control support passes, fails, or makes downstream identification conditional. Define separate conditional-support and robust-identification fields, and align §5, the gate, summaries and power counting.

5. **The power table no longer describes the decision code.** `docs/POWER-3.md:35,48–56`; `scripts/oc_study3.py:65–66`; `study3.py:111–113`. The documented reward/cost identification rate is 1.00 everywhere. Running the existing OC function on seeds 0–2 with the revised Boolean gives **2/3 Agave and Jito; 1/3 Firedancer and each builder target**. This small replay demonstrates staleness, not a precise replacement estimate. The strict four-test control gate compounds power loss under weaker effects; its safety benefit is conservative withdrawal, not proof that every failure is methodological.

   Also, `sim.py:26–28` still uses 130-ms slots/520-ms windows, while the new shared-ingress design avoids boundaries at 198 ms (`design.rs:168–170`). Late simulated probes can therefore be censored under a different timing regime.

   **Fix:** rerun the registered 100 replicates after finalizing design and verdict semantics. Report conditional support, robust identification, and gate-pass rates separately, with Monte Carlo intervals. Align timing or add a 198-ms scenario. State that exact-binomial calibration assumes independent windows; Holm tolerates dependence between hypotheses, not invalid marginal p-values. Describe 100/100 as a simulation result, not guaranteed power.

6. **Historical claims are mutable inputs to identification.** `scripts/freeze.py:111–120` pins `analysis/`, but `study3.compute:175–176` reads whichever Study 1/2 result files are present. Two analysts can use different revisions of those files and obtain different identification verdicts from identical Study 3 data.

   **Fix:** include the two prior-result SHA-256 hashes, or an exact commit plus paths, in the manifest and verify them before analysis. Record the candidate scope and published claims used.

7. **An entirely uninformative run crashes instead of returning twelve p=1 entries.** `outcomes.py:246–247` returns a columnless frame when no probes were logged; `study3._selected:57` then raises **KeyError: target_identity**. This covers a selected live run whose windows all skip before probe logging. If no runs are selected, `compute:178` emits no hypothesis or identification rows either, leaving “not evaluable” implicit.

   **Fix:** return all twelve registered hypotheses with n=0, p=1 and “not evaluable,” plus failed-control withdrawal and the exclusion funnel. Add these boundary cases to the existing tests.

8. **Promised exploratory diagnostics are missing or pooled.** `PREREGISTRATION-3.md:71–72,123–124` promises exploratory off-group windows and landing rates by label. `study3.analyse:154–164` emits neither; its send-order diagnostic pools targets and observed groups. A routing change or label-dependent loss can disappear inside those totals. The selection bound covers incomplete pairs only within evaluable windows, not excluded transport failures.

   **Fix:** emit descriptive tables by target, observed client/ingress and contrast, including per-label landing numerators/denominators and send order. Label off-group results exploratory and show excluded-window counts beside selection-robust claims.

## Verification and limits

The original design has **192 windows, 768 probes, 16/16 send-order balance per contrast per target**, and worst-case fees **5,952,000 lamports**. Including the stated 135,000 setup cost leaves **987,000** under the cumulative cap; the study sub-budget has 548,000 probe-fee headroom. No arithmetic budget blocker found.

Agave's [priority](https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/transaction_priority.rs), [cost model](https://github.com/anza-xyz/agave/blob/v4.3.2/cost-model/src/cost_model.rs), and [fee distribution](https://github.com/anza-xyz/agave/blob/v4.3.2/runtime/src/bank/fee_distribution.rs) support the original table. Retrieved Firedancer [cost estimation](https://github.com/firedancer-io/firedancer/blob/main/src/disco/pack/fd_pack_cost.h) and [pack comparison](https://github.com/firedancer-io/firedancer/blob/main/src/disco/pack/fd_pack.c) give the same component costs and retained rewards, exact ratio comparisons, and no allocation penalty for these transfers: C4/C5 prefer x; requested-cost-only prefers A/ties. The stated Firedancer release tag could not be fetched, so this is a `main` source cross-check, not deployed-version proof.

Complete-case ordering, x-label mapping, frozen-group filtering, one-sided tails, Holm adjustment and censored coding were traced. The latest existing Study 3 tests pass **5/5**; finding 2 shows why green tests do not validate verdict meaning. No Rust rebuild or live mainnet transaction was performed.
