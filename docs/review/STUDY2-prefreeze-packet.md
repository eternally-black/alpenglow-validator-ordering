# Review packet — Study 2 pre-registration, before freezing (advisory only)

You are an independent reviewer. **Do not modify any project file.** Write your full report to
`review/STUDY2-prefreeze-gpt.md` (create it) and nothing else.

## Context

A pre-registered mainnet measurement of how Solana validators order transactions (bounty: docs/BOUNTY.md). Study 1 is
done (REPORT.md, docs/PREREGISTRATION.md). Study 2 is about to be frozen: its pre-registration, design and manifest
hashes go into a mainnet Memo, after which nothing can be changed without a reported deviation. Your review is the
last chance to find a flaw.

Read, in this order:
1. `docs/STUDY2-PLAN.md` — why Study 2, what it adds.
2. `docs/PREREGISTRATION-2.md` — the normative plan (hypotheses, unit, tests, Holm, selection bound, gates).
3. `analysis/itb_analysis/study2.py` — the code that will decide the hypotheses.
4. `analysis/tests/test_study2.py` — its tests (simulated schedulers with known horizons).
5. `crates/itb/src/design.rs` — `generate_study2`, `STUDY2_RACE_CELLS`, `equal_key_pair`, `validate`.
6. `docs/POWER-2.md` and `scripts/oc_study2.py` — operating characteristics.
7. `scripts/freeze.py` — what goes into the manifest.
8. For reference: `docs/PREREGISTRATION.md` (Study 1, normative for the replication), `analysis/itb_analysis/outcomes.py`
   (window eligibility), `analysis/itb_analysis/sim.py` (simulator).

## What to look for (be concrete: file, line, failure scenario)

- Statistical validity: independence (the window as unit, one race per Δt cell per window), the one-sided tests,
  Holm with a not-evaluable hypothesis at p = 1, the selection bound and the robustness threshold, the gates (hi-first
  controls; achieved send gap), censored coding. Anything that makes a published claim wrong or unfalsifiable.
- Whether the hypotheses as stated are actually tested by the code (estimand definitions, group filters, Δt
  matching, which member counts as "success" for races vs equal-key pairs).
- Design: can `generate_study2` violate the stated properties? Is the race start (+5 ms after first shred) plus
  Δt up to 50 ms safe? Equal-key pairs buffered at −150 ms on direct ingress: is the 10 ms gap meaningful there?
- Anything in the pre-registration that is ambiguous enough that two analysts could reach different verdicts.
- Anything that should be changed BEFORE freezing (rank: blocker / should-fix / nit).

Keep the report under ~1,500 words, findings ranked by severity, each with a concrete fix.
