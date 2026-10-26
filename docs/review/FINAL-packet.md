# Final review packet — before publication (advisory only)

You are an independent reviewer. **Do not modify any project file.** Write your full report to
`docs/review/FINAL-gpt.md` (create it) and nothing else.

## Context

A bounty submission: a pre-registered measurement of how Solana validators order transactions, on post-Alpenglow
mainnet. Brief and judging criteria (verbatim): `docs/BOUNTY.md`. Two studies:
- Study 1 (2026-10-24): `docs/PREREGISTRATION.md`, results `data/derived/results.json`, exploratory
  `data/derived/exploratory_stage2.md`;
- Study 2 (2026-10-25): `docs/PREREGISTRATION-2.md`, results `data/derived/study2/results.json` and `summary.md`.

Everything is about to go public (GitHub). This is the last review: find what a careful judge or a hostile expert
would find.

Read: `README.md`, `REPORT.md`, `docs/BOUNTY.md`, `docs/CAMPAIGN-LOG.md`, `docs/PREREGISTRATION.md`,
`docs/PREREGISTRATION-2.md`, `docs/STUDY2-PLAN.md`, `docs/POWER.md`, `docs/POWER-2.md`, and as needed the code
(`crates/itb/src/*.rs`, `analysis/itb_analysis/*.py`, `scripts/*.py`) and results files.

## What to look for (concrete: file, line or section, why, fix)

1. **Claims vs evidence.** Any sentence in README or REPORT that the data or the pre-registered procedure does not
   support, overstates, or words more strongly than the test (e.g. "never", "always", causal mechanisms stated as
   fact). Distinguish confirmatory from exploratory everywhere.
2. **Internal consistency.** Numbers that disagree between README, REPORT, CAMPAIGN-LOG, the summary tables and the
   results files (counts, n, intervals, p-values, costs, dates, slots, signatures).
3. **The brief.** Every requirement in `docs/BOUNTY.md` (mainnet only, ≥ 6 validators and ≥ 3 client types, the fee
   cap enforced in code, dry-run default, own transactions as primary evidence, no pre/post-Alpenglow mixing, Docker
   Compose one command, raw data with signatures and slots, README design rationale / how each consideration is
   handled / what is not separated, REPORT with measurement dates and a "what went wrong" section). Is each one met
   and is the evidence easy to find? Anything missing or hard to find?
4. **Methodological weak points** a judge could attack, and whether the text acknowledges them honestly.
5. **Presentation.** What would make a judge lose patience: walls of text, jargon, unclear first screen, broken
   structure, missing links. Be specific.

Rank findings: BLOCKER (must fix before publishing) / SHOULD-FIX / NIT. Keep the report under ~1,800 words.
