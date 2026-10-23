You are an independent senior reviewer (Rust, Solana internals, applied statistics). ADVISORY ROLE ONLY: read the code and write a review report. Do not modify, create or delete any file except the report named below.

Repository: a Solana mainnet measurement project for the bounty in `docs/BOUNTY.md`. Plan: `docs/PLAN.md`; frozen-to-be analysis plan: `docs/PREREGISTRATION.md`; data schema: `docs/DATA.md`.

Review these for correctness bugs, safety holes and plan/code mismatches, most severe first:
1. `crates/itb/src/` (Rust): especially `ledger.rs` + `auth.rs` + `run.rs` + `setup.rs` (can any path spend more than the cap, send transaction bytes in dry-run mode, double-count or lose a reservation, release a reservation for a tx that could still land, reuse a payer within a window?), `quic.rs` (stream scheduling/timestamps, limiter), `timing.rs` (event anchoring, cadence model), `collect.rs` (status classification, expiry proof), `design.rs` (randomisation balance, lock/payer independence), `probe.rs` (fee/cost/priority formulas vs agave v4.3.2 cost model and fee distribution).
2. `analysis/itb_analysis/` (Python): `outcomes.py` (pair coding, complete-case vs censored, eligibility), `stats.py` (Clopper–Pearson, Bonferroni/TOST, randomisation tests under the sharp nulls, rule statuses) — check against PREREGISTRATION.md §1–§6 exactly; `verify.py` (instruction decoding, checks); `sim.py`/`oc.py` (does the simulator encode the scenarios as described; any way the analysis could look validated while being wrong?).
3. Anything in the design that a bounty judge would attack on "does the experiment measure what it claims".

Write the FULL report to `docs/review/CODE-gate1-gpt.md`: numbered findings, each tagged [BLOCKER|MAJOR|MINOR], with file:line, the failure scenario (concrete inputs → wrong result), and the fix. End with a short list of the strongest parts (so they are not regressed). Your final reply: a 15-line summary.
