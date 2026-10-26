# Study 3 pre-freeze re-check — 2026-10-26

Reviewed HEAD `43844180a253f10f5f459a36111a5cb560ea9f31`. DeepSeek IDs refer to the seven findings summarized in `STUDY3-prefreeze-dispositions.md`; its original response is not present. Eleven dispositions are RESOLVED; four are PARTLY. Only this report was written.

## BLOCKER

1. **GPT 7 — PARTLY: a loaded all-skipped run still crashes.** The no-run and empty-pair cases work, but `study3.py:190` calls `outcomes.window_table` before `_frame`. With nonempty windows and no probes, `analysis/itb_analysis/outcomes.py:145–147` merges three keys against an empty single-level index. Reproduced through `study3.analyse` on a temporary loaded run with all six windows marked `connect_failed`: `ValueError: len(left_on) must equal the number of levels in the index of "right"`. No hypotheses, withdrawal or funnel are returned, contrary to `docs/PREREGISTRATION-3.md:117–118`. `analysis/tests/test_study3.py:105–117` tests empty frames and no selected run, not this case. **Fix:** give the empty logged-probe table a three-level index named by `keys`, or merge on explicit key columns; exercise an actual loaded all-skipped run.

## SHOULD-FIX

2. **GPT 4 — PARTLY; DeepSeek 3 — PARTLY: the qualifier misses the neither-supported verdict.** Robust/conditional identification and the positive-result branches are fixed (`analysis/itb_analysis/study3.py:102–160`). However, the final branch at `study3.py:152–155` omits `+ q`, contradicting `docs/PREREGISTRATION-3.md:144–157`. Reproduction: each control hypothesis has 20/20 successes plus 12 incomplete pairs (Holm p ≈ 0.00001144; worst-case p ≈ 0.107664); another target has 16/32 on both contrasts. The gate passes conditionally, but that target receives unqualified “the reward term is not shown; cost alone is not rejected.” **Fix:** append the qualifier in the final branch and cover conditional-gate cases for every verdict row, including descriptive suffixes.

3. **GPT 8 — PARTLY: the rendered report still omits promised exclusion reasons.** Grouped/off-group diagnostics and JSON funnels now exist (`analysis/itb_analysis/study3.py:164–219`). But `analysis/itb_analysis/report2.py:110–134` renders only evaluable/attempted totals, omitting every exclusion reason and each diagnostic group's total pair count. This falls short of `docs/PREREGISTRATION-3.md:176–184` and the disposition's report claim. Reproduced six transition-excluded windows: JSON records `mode:transition_ambiguous: 6`; the summary contains no reason. **Fix:** render the existing per-target exclusion counts and diagnostic `pairs` totals alongside the current tables.

## NIT

4. **Observed-landing prose rounds one builder rate incorrectly.** `scripts/oc_study3.py:35` uses 86/92 = 0.934783 and 87/94 = 0.925532 for the two Harmonic targets: both round to 0.93. `docs/POWER-3.md:31` and `scripts/oc_study3.py:39` instead say 0.93 and 0.94. **Fix:** print the fractions or correct the rounded descriptions; the simulation inputs and result tables need no numerical change.

## Resolved dispositions

These rows require no further fix; references identify the implemented correction.

| Finding, original severity | Verdict | HEAD evidence |
|---|---|---|
| GPT 1, BLOCKER | RESOLVED | Final Y is defined at `crates/itb/src/probe.rs:125` and registered at `docs/PREREGISTRATION-3.md:50`, `docs/STUDY3-PLAN.md:12`. Every production and fixture member matches its Rust template. `docs/CAMPAIGN-LOG.md:303–324` distinguishes the two dry runs. |
| GPT 2, BLOCKER | RESOLVED | H5-only support now says C4 is inconclusive; below-0.5 wording is explicitly descriptive (`analysis/itb_analysis/study3.py:148–155`; `docs/PREREGISTRATION-3.md:135–142`; `analysis/tests/test_study3.py:149–154`). |
| DeepSeek 1, BLOCKER | RESOLVED | Revised Y removes the fee-definition reversal (`crates/itb/src/probe.rs:223–244`). Cross-multiplication gives −500b + 5,000c₀ + 4,500,000 > 0, hence b < 10c₀ + 9,000; c₀ = 1,336 gives 22,360, as registered (`docs/PREREGISTRATION-3.md:68–78`). |
| GPT 3, SHOULD-FIX | RESOLVED | Candidate scope appears in the verdict (`analysis/itb_analysis/study3.py:143`); requested-cost definition, additive counterexample and temporal stability are explicit (`docs/PREREGISTRATION-3.md:40–41,188–197`). |
| GPT 5, SHOULD-FIX | RESOLVED | Slot duration is parameterized (`analysis/itb_analysis/sim.py:87,312–314`); OC uses 198 ms and separate conditional, robust and gate counts with exact intervals (`scripts/oc_study3.py:31,54–96`). POWER tables match derived output; independence and simulation limitations are disclosed (`docs/POWER-3.md:19–20,99–101`). |
| GPT 6, SHOULD-FIX | RESOLVED | Committed prior blobs, cleanliness checks, hashes and commit are frozen (`scripts/freeze.py:116–150`); identification reads manifest claims (`analysis/itb_analysis/study3.py:128–137`). |
| DeepSeek 2, SHOULD-FIX | RESOLVED | Reward variants' observational equivalence is disclosed (`docs/PREREGISTRATION-3.md:194–195`); identification is candidate-scoped (`study3.py:143`). |
| DeepSeek 4, SHOULD-FIX | RESOLVED | Tie independence is stated (`docs/PREREGISTRATION-3.md:80–89`); balanced/shuffled design and randomized distinct payers are implemented (`crates/itb/src/design.rs:642–681`; `crates/itb/src/run.rs:170–180,827–845`). |
| DeepSeek 5, SHOULD-FIX | RESOLVED | Both-supported/prior-not-`reward_cost` row agrees (`docs/PREREGISTRATION-3.md:133`; `analysis/itb_analysis/study3.py:144–145`). |
| DeepSeek 6, NIT | RESOLVED | Optional race timing uses `.get`; zero planned pairs abort freezing (`scripts/freeze.py:95,143–147`). |
| DeepSeek 7, NIT | RESOLVED | Funding principal versus transaction fees is explicit (`docs/STUDY3-PLAN.md:36–40`). |

Verification: existing Study 3 tests passed **9/9**. Full design scan: **192 windows, 768 probes, 192 correct Ys**, 16/16 send-order balance per contrast/target, SHA-256 `bfaa83b62ac3b0987ce636367fdc8b638362942d65f571eacffc16542c60340d`. §2 costs/priorities and §10 additive scores are correct. Fees total 5,952,000 lamports; with 135,000 setup, cumulative headroom is 987,000. Read-only freeze-field evaluation returned twelve hypotheses with planned n = 32 and twelve prior `reward_cost` claims. OC JSON regenerates committed Markdown exactly; all POWER result cells agree. No full 600-replicate rerun, Rust rebuild or live transaction was performed.

**DO NOT FREEZE — the loaded all-skipped path crashes; the registered qualifier and rendered exclusion requirements also remain incomplete.**
