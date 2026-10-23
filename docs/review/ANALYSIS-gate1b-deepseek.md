# Analysis review after gate 1b — DeepSeek V4 Flash (advisory)

2026-10-23. Scope: the decisions added while addressing gate 1b — the strictness split (R vs partial:R), the
selection-robust qualifier, the verdict table and the §9 gates. Inputs: PREREGISTRATION.md, stats.py, report.py. The
review is summarised below; each finding is followed by its disposition.

| # | Finding (summary) | Disposition |
|---|---|---|
| 1 [MAJOR] | Complete-window strictness is computed on a selected denominator: 40 complete windows all following R certify "R" even if 60 incomplete windows would not. | **Addressed.** The split no longer uses window strictness (see #7). Strictness is now descriptive and also reported without the selection assumption (`lower95_worst`: incomplete windows count as failures). Any claim that rests on complete-case selection already carries "(assumes selection)" unless it survives the worst-case bounds. |
| 2 [MAJOR] | The strictness gate is tested on the same windows as the rule status (post-selection), so it is not an unconditional 95 % gate. | **Accepted and stated.** The split can only weaken a claim (R → partial:R), never create one. PREREGISTRATION §4 now says its level is nominal. |
| 3 [MAJOR] | "(assumes selection)" still publishes a rule name; require selection-robustness for any rule claim. | **Kept, with reasons.** The complete-case quantity ("when both are included, which comes first") is a legitimate pre-registered estimand. The qualifier states exactly which interpretation rests on the assumption, and the worst-case bounds are published beside it. Requiring robustness would erase every finding for low-landing ingress, where the estimand is still informative. |
| 4 [MAJOR] | `mixed:fifo+R` checked robustness and strictness only for FIFO. | **Fixed.** A mixture is never selection-robust (its economic component cannot be bounded from complete-case windows), so it is always published with the qualifier. Test `test_a_mixture_is_never_selection_robust`. |
| 5 [MAJOR] | The buffer gate omits mixed verdicts. | **Fixed differently.** In buffered windows, order effects are what a mixture's FIFO component predicts, so they are no evidence against it. What does contradict a mixture is a key effect that appears only in streaming windows (probes not coexisting). That case now withdraws the mixture claim (`withdrawal_reason`). Test `test_a_mixture_with_key_effects_only_in_streaming_windows_is_withdrawn`. |
| 6 [MINOR] | A failed positive control publishes its own raw verdict. | **Fixed.** It is published as "control failed: …". Test `test_a_failed_control_does_not_publish_its_raw_verdict`. |
| 7 [MINOR→MAJOR] | Requiring all three contrasts complete in one window starves reward/cost strictness at low landing. Positive controls then become partial:reward_cost, fail §9 and withdraw everything. | **Fixed.** The R vs partial:R split now uses the *governed share*. Each contrast won by R's preferred member with probability L = (1 + s)/2 gives s ≥ 2·L_lower − 1 (one-sided 95 %), taken as the minimum over R's directional predictions, using every complete pair of each contrast. Test `test_the_majority_split_does_not_starve_when_no_window_is_complete_in_every_contrast`. |

Sound, per the review: exact Clopper–Pearson; window-level Bernoulli scoring; conservative worst-case extremes; the
fixed 36-effect Bonferroni family; frozen positive controls and confirmatory groups; the buffer-gate concept.
