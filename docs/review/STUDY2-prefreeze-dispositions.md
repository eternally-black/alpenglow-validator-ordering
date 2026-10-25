# Study 2 pre-freeze reviews — dispositions

Two independent reviews of commit `518d7fb`, before the Study 2 freeze:
- GPT (gpt-6.1-sol via `codex exec`): [STUDY2-prefreeze-gpt.md](STUDY2-prefreeze-gpt.md);
- DeepSeek (deepseek-v4-flash, thinking, effort max): [STUDY2-prefreeze-deepseek.md](STUDY2-prefreeze-deepseek.md).

Every finding was checked against the code before acting on it. All changes are in the freeze commit; the tests
named below fail on the reviewed version.

| # | Finding | Disposition |
|---|---|---|
| GPT 1 | Simultaneous (Δt = 0) hi-first races counted as controls; noise could withdraw a valid 2 ms result (P ≈ 0.89 of ≥ 2 losses among six coin flips) | **Fixed.** Controls are hi-first races with Δt > 0 (5 and 25 ms). No informative control is stated in the claim. `test_simultaneous_races_are_not_controls_and_count_both_orders_at_zero` |
| GPT 2, DS 1 | The replication's positive-control failure never reached H1–H3 | **Fixed**, stricter than the note GPT read in the draft: H1–H3 are withdrawn ("method check failed in the replication"). The same pipeline observes the races. PREREGISTRATION-2 §8. `test_a_missed_gap_or_a_failed_control_withdraws` |
| GPT 3 | Operating characteristics scored `evaluate()` without gates or send records; no boundary null; "never supported" overstated | **Fixed.** `oc_study2.py` scores published claims after the gates, with send records. A `boundary_null` scenario puts every group exactly at O = 0.5 / E = 0.5. Campaign-level "any false support" is reported with its exact upper bound (POWER-2) |
| GPT 4 | H3: no gap check, and later-*sent*-first among buffered probes does not by itself identify a later-*arrival* tie-break | **Fixed.** The gap gate applies to equal-key pairs. The achieved-gap sensitivity includes them. A buffering-evidence sensitivity (§6.5) is added. H3 is stated as later-sent-first, with the arrival reading flagged as an assumption. `test_equal_key_gap_is_gated_too` |
| GPT 5 | The nominal +55 ms end does not guarantee first-slot containment (100 ms lateness allowed) | **Fixed in the text:** the estimands are stated as window-wide, and a same-slot sensitivity is added (§6.4). The plan says "nominally inside" |
| GPT 6 | O(0) kept only lo-first simultaneous races | **Fixed:** O(0) uses both stream orders, scoring `hi` first. Tested in the GPT 1 test |
| GPT 7 | "Does not reorder" is stronger than O(2) < 0.5 | **Fixed:** H1/H2 (manifest statements, pre-registration, plan) now say "in fewer / more than half of the races". The size is carried by the estimate and interval |
| DS 2 | H3 pools targets and window contexts | **Kept as the confirmatory test** (the claim is about the client). Per-target counts (`by_target`) are now emitted for every hypothesis. A direction disagreement is reported next to the pooled claim (§3) |
| DS 3 | Round-robin deal fixes which Δt cells share a window (5 of 10 possible sets) | **Fixed:** after the deal, 20,000 random swaps that keep every window valid randomise co-occurrence. `study2_mixes_which_cells_share_a_window`. The 2 ms race is in every window by design, one per window |
| DS 4 | Replication criterion not computed | **Fixed:** `replication_summary` emits `replicated` per core target against the committed Study 1 claims. `test_replication_compares_published_claims_per_core_target` |
| DS 5 | Gap gate only annotated | **Fixed:** a missed gap withdraws the claim (§8) |
| DS 6 | Controls only at 5 and 25 ms, not 2 ms | **Scoped explicitly** (§8). A 2 ms hi-first control would need a second 2 ms race in some window, breaking the one-cell-per-window unit. Hi-first controls test the same thing at any positive gap: priority and arrival agree |
| DS 7 | No audit of planned counts at freeze; `validate` does not enforce the Study 2 invariants | **Fixed:** `freeze.py` writes each hypothesis' `planned_n` from the design and refuses zero. `validate` refuses an R window with a repeated cell and an E window not holding exactly one equal-key pair. `study2_invariants_are_enforced` |
| DS 8 | Equal-key pairs on shared ingress would not be "pending at slot start" | **Fixed:** the generator refuses them |
| DS 9 | "Observed at zero" overstated error control | **Fixed** with GPT 3 |
| DS 10 | Horizon definition hides non-monotone curves | **Fixed in the text:** every cell is shown, and a non-monotone bracket is labelled so (§7) |
| DS 11 | Gap median over all pairs, controls over complete pairs | **Documented** (§6.3): sending does not depend on landing |
| GPT (limits) | Independence across successive windows is an assumption | Stated in §2, as in Study 1 |
