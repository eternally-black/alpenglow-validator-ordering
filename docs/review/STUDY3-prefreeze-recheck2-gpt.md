# Study 3 pre-freeze second re-check — 2026-10-26

Reviewed HEAD `e8421cb21f8dd2387c8998f946134454a5e1719d`, limited to R1–R4 and regressions introduced by their fixes. Only this report was written in the project.

1. **R1 — RESOLVED.** The empty logged-probe table now has the three named index levels required by the merge (`analysis/itb_analysis/outcomes.py:143–149`). Independently reproduced the earlier six-window case: a loaded temporary run, two windows per target, all marked `connect_failed`, with empty probe/send/outcome logs. Calling `study3.analyse` with the parent function reproduces `ValueError: len(left_on) must equal the number of levels in the index of "right"`. At HEAD, the same call returns all six hypotheses with n = 0 and “not evaluable”; the funnel is six attempted, zero evaluable, six `skipped:connect_failed`. Both positive controls fail and both non-control hypotheses are withdrawn. `report2.study3_summary` completes and prints three exclusion rows, each with count two. The committed 90-window regression also passes (`analysis/tests/test_study3.py:172–185`).

2. **R2 — RESOLVED.** The neither-supported branch appends the same selection qualifier as the other verdict branches, before any descriptive suffix (`analysis/itb_analysis/study3.py:135–155`). The conditional-gate test passes for supported, unsupported and unevaluable combinations, both descriptive suffixes, and withdrawal (`analysis/tests/test_study3.py:188–209`).

3. **R3 — RESOLVED.** The summary renders per-target attempted/evaluable windows and exclusion counts, plus total/evaluable pairs for every diagnostic group (`analysis/itb_analysis/report2.py:123–138`). Independently induced 30 transition-ambiguous windows: the rendered table contains `mode:transition_ambiguous 30`; all six diagnostic rows match their source counts, including 30 total / zero evaluable for the excluded target's contrasts.

4. **R4 — RESOLVED.** Both 86/92 and 87/94 round to 0.93. The exact inputs remain unchanged (`scripts/oc_study3.py:35`); the corrected descriptions agree (`scripts/oc_study3.py:39`, `docs/POWER-3.md:31`, `data/derived/oc-study3.json:209`). Parent/HEAD OC JSON is identical after normalizing that description alone.

**Study 1/2 isolation:** Only the zero-probe branch changed; the nonempty branch and empty-window return are untouched (`outcomes.py:140–147`). The old zero-probe/nonempty-window path crashed before producing any result. All four manifest-selected historical runs contain probes. Exact parent/HEAD DataFrame comparison, including dtypes, passes for Study 1 (4,322 probes; 569 windows) and Study 2 (3,414 probes; 550 windows). Their callers consume this unchanged table (`analysis/itb_analysis/report.py:218–220`, `analysis/itb_analysis/study2.py:235–237`), so R1 cannot change their existing results.

Verification: **39 tests passed** across `test_study3`, `test_outcomes`, `test_study2`, `test_report`, and `test_report2`, using the existing Python environment with bytecode/cache writes disabled. No new BLOCKER or SHOULD-FIX was found within this change.

**FREEZE OK — R1–R4 are resolved, Study 1/2 results are unaffected, and no blocking regression was found.**
