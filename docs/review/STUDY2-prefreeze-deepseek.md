# Study 2 pre-freeze review — DeepSeek (deepseek-v4-flash, thinking, effort max), 2026-10-25

Files given: PREREGISTRATION-2.md, STUDY2-PLAN.md, study2.py, test_study2.py, design.rs, POWER-2.md, freeze.py,
PREREGISTRATION.md, outcomes.py (commit `518d7fb`). Verbatim answer; dispositions in
[STUDY2-prefreeze-dispositions.md](STUDY2-prefreeze-dispositions.md).

---

**BLOCKER**
1. `analysis/itb_analysis/study2.py` — `analyse()` / `published()` never applies PREREG-2 §8 row 1. `compute()` calls `report.compute` but discards its replication gates; H1–H3 can be published `supported` even if a Study 2 positive control fails. Fix: extract replication gate status and annotate/withdraw H1–H3 with “method check failed in replication”; make `published()` require it.

2. `crates/itb/src/design.rs` — `generate_study2` emits all windows target-by-target; H3 in `study2.py` `_selected()` pools 35 `EvnRmnMr` R-window equal-key pairs (Streaming, with 3 races) and 24 `9eGrDohd` E-window pairs (Buffered, alone). Failure: H3 confounds tie-break with target, window context, and session time (E block likely late). Fix: dedicated E windows for both Firedancer targets, interleaved targets; or pre-register H3 per target/stratified and require homogeneity before pooling.

3. `design.rs` — `race_sets[i % n_r].push(r)` over concatenated `STUDY2_RACE_CELLS`; since Δt=2 has 35 = `n_r`, every R window carries a 2 ms race, and other cells’ co-occurrence patterns are fixed. Failure: O(2) and exploratory O(Δt) are mixture effects under a fixed co-send pattern; same-window interference confounds the horizon curve. Fix: independently randomise cell-to-window assignment with at most one cell per window, balance co-occurrence, include isolated-cell windows, or pre-specify the mixture estimand.

**SHOULD-FIX**
4. `study2.py compute()` — Hypothesis R is not operationalised. It returns Study 2’s replication computation but never compares per-core-target published claims to Study 1’s frozen `reward_cost` claims. Failure: “replicated” is analyst-defined. Fix: load frozen Study 1 claims and emit a `replicated` boolean per core target in the analysis output.

5. `study2.py gates()` / `published()` — Gap gate only appends the achieved gap; it does not change the verdict. `evaluate()` still tests nominal Δt=2. Failure: H1/H2 can be `supported` with median achieved gap 3.5 ms while the hypothesis says 2 ms. Fix: pre-specify that `gap_flag` downgrades to not evaluable, or replaces the claim with an achieved-gap estimand/test.

6. `study2.py gates()` — Control-loss gate uses all hi-first controls in the group; `STUDY2_RACE_CELLS` has no hi-first controls at Δt=2 (only 5 and 25). Failure: the 2 ms hypotheses can be withdrawn/passed by controls at different head starts. Fix: add hi-first controls at Δt=2 or explicitly scope the gate.

7. `scripts/freeze.py study2_fields()` — Writes hypotheses/analysis tree but does not audit the frozen design against planned counts: 35 two-ms races per R target, 59 H3 pairs, `e_windows`, `equal_key_in_r`, target groups. `design.rs validate()` also does not enforce Study 2 one-cell-per-window / one-equal-key-per-E invariants. Failure: a malformed target file freezes a design with different n while the manifest still claims planned n. Fix: add a pre-freeze audit and extend `validate()`.

8. `design.rs equal_key_pair()` — For non-direct ingress it uses `RACE_START_OFFSET_MS`, not “both pending at slot start” as PREREG-2 §2 states. Failure: any shared-ingress equal-key output is not the pre-registered estimand. Fix: restrict equal-key pairs to direct ingress or amend the estimand and design.

**NIT**
9. `docs/POWER-2.md` — “That is the family-wise error … observed at zero” over 40 reps is misleading; 0/40 does not demonstrate FWER control. Report the upper bound or phrase as consistent-with.

10. `study2.py horizon()` — Uses only `max(above)` and the next data point; non-monotone crossings are hidden. Pre-specify the horizon definition or report all crossings.

11. `study2.py gates()` — Gap median includes incomplete pairs while control losses exclude them; document the asymmetry or align filters.
