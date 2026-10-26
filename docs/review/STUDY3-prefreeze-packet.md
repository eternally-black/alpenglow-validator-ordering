# Review packet — Study 3 pre-registration, before freezing (advisory only)

You are an independent reviewer. **Do not modify any project file.** Write your full report to
`docs/review/STUDY3-prefreeze-gpt.md` (create it) and nothing else.

## Context

The final review of this bounty submission found that Studies 1 and 2 cannot separate Agave's priority,
reward ÷ (cost + 1), from ordering by requested cost alone: every contrast they ran ranks the probes by cost the same
way (REPORT.md §9, docs/review/FINAL-gpt.md finding 1). Study 3 is a small pre-registered study to close that gap. Its
pre-registration, design and manifest hashes go into a mainnet Memo; after that, changes are reported deviations.

Read:
1. `docs/STUDY3-PLAN.md` and `docs/PREREGISTRATION-3.md` (normative).
2. `analysis/itb_analysis/study3.py`, `analysis/tests/test_study3.py`, and the C4/C5 parts of
   `analysis/itb_analysis/outcomes.py` and `analysis/itb_analysis/sim.py`.
3. `crates/itb/src/probe.rs` (templates, cost, priority, the Rule enum and its tests) and `crates/itb/src/design.rs`
   (`generate_study3`, `validate`).
4. `docs/POWER-3.md`, `scripts/oc_study3.py`, `scripts/freeze.py` (`study3_fields`).
5. For reference: `docs/PREREGISTRATION.md`, `docs/PREREGISTRATION-2.md`, `REPORT.md` §2, §6, §9, and
   `docs/research/03-client-schedulers.md` (what the clients' code does).

## What to look for (concrete: file, line or section, failure scenario, fix)

1. **Do C4 and C5 actually separate the hypotheses** under each client's *real* priority computation? Check Agave
   (reward definition: priority fee plus the unburned half of the signature fee; cost model), Firedancer's pack
   (its own cost estimate and reward), and what BAM and Harmonic builders might do. Is there any plausible key under
   which reward ÷ cost would still lose C4, or under which cost alone would still win C4? Any key that would fake
   the reward ÷ cost pattern on C4 and C5 and is not already excluded by Studies 1 and 2?
2. **Statistics:** the one-sided tests, Holm over twelve, the selection bound, the positive-control gate (is it too
   strict or too lax?), the identification verdict's logic of combining Study 3 with the Study 1 and 2 claims.
3. **Does the code test what the pre-registration says?** Estimand, group filters, which member is x, censored
   coding, the verdict texts.
4. **Design:** balance, regimes, budget (worst case vs cap headroom), anything that could make the run fail or bias
   the result.
5. **Ambiguities** that would let two analysts reach different verdicts; anything to fix BEFORE freezing
   (BLOCKER / SHOULD-FIX / NIT).

Keep the report under ~1,500 words, ranked by severity, each with a concrete fix.
