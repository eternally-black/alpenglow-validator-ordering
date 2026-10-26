# Re-check packet — Study 3, fixed snapshot, before freezing (advisory only)

You are an independent reviewer. **Do not modify any project file.** Write your report to
`docs/review/STUDY3-prefreeze-recheck-gpt.md` (create it) and nothing else.

## Context

Your earlier review of Study 3 (`docs/review/STUDY3-prefreeze-gpt.md`) said "do not freeze this snapshot", with two
blockers and six should-fix findings. DeepSeek reviewed the same files. The author's fixes are committed at HEAD
(`git log -1`), and each finding's disposition is in `docs/review/STUDY3-prefreeze-dispositions.md`. After this
check, the pre-registration, design and manifest hashes go into a mainnet Memo; any later change is a reported
deviation.

## What to do

1. For **each** of your eight findings and DeepSeek's seven, check against the code and documents at HEAD whether the
   stated disposition is true. Verdict per finding: RESOLVED / PARTLY / NOT RESOLVED, with file:line evidence.
2. Look for anything the fixes **introduced**: regressions, contradictions between `docs/PREREGISTRATION-3.md` and
   `analysis/itb_analysis/study3.py`, verdict texts that differ between §5 and the code, arithmetic errors in §2
   (costs, priorities, the bound b < 10·c₀ + 9,000) or §10 (additive scores).
3. Check that `design/design-study3.jsonl` matches the templates in `crates/itb/src/probe.rs` (every Y is L 1,500,
   4,000,000 µlamports/CU) and that `docs/POWER-3.md` matches `data/derived/oc-study3.md`.
4. Final line: **FREEZE OK** or **DO NOT FREEZE**, with the blocking reasons.

Files: `docs/PREREGISTRATION-3.md`, `docs/STUDY3-PLAN.md`, `docs/POWER-3.md`, `analysis/itb_analysis/study3.py`,
`analysis/itb_analysis/report2.py` (`study3_summary`), `analysis/tests/test_study3.py`, `analysis/itb_analysis/sim.py`,
`scripts/freeze.py` (`prior_claims`, `study3_fields`), `scripts/oc_study3.py`, `crates/itb/src/probe.rs`,
`design/design-study3.jsonl`, `data/derived/oc-study3.md`.

Keep the report under ~1,000 words, ranked by severity (BLOCKER / SHOULD-FIX / NIT), each with a concrete fix.
