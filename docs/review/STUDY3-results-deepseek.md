# Study 3 results text — DeepSeek review, 2026-10-26

Summary of DeepSeek's (deepseek-flash, via its API) review of the Study 3 text in REPORT.md against the frozen output.
It received the text and the summary tables inline, not the repository. Its findings, as it ranked them, with the
author's assessment in the dispositions: [STUDY3-results-dispositions.md](STUDY3-results-dispositions.md).

| # | DeepSeek's severity | Finding (condensed) |
|---|---|---|
| 1 | BLOCKER | "318 complete pairs" conflates pairs and windows: complete windows sum to 159 |
| 2 | BLOCKER | "about 10⁻⁶" for the BAM node's Holm p is imprecise, and its worst-case bound (1.4 × 10⁻⁴) should be labelled as a different statistic |
| 3 | SHOULD-FIX | "Both positive controls" should name them |
| 4 | SHOULD-FIX | The BAM node's 8 excluded windows and its 3 lost evaluable windows should be stated as disjoint |
| 5 | SHOULD-FIX | §6.6's bold "The key is identified" should carry "among the registered candidates" itself |
| 6 | SHOULD-FIX | "This holds whatever share of the signature fee a client counts as reward" reads as a robustness claim the pre-registration does not make about reward variants |
| 7 | SHOULD-FIX | Equal cost for A and hi with different prices is not obviously reproducible; show the cost formula |
| 8 | NIT | Use the exact stored p phrasing |
| 9 | NIT | Send-order endpoints confirmed (11/24, 13/24) |
| 10 | NIT | The "no fee" gloss on `not_all_sent` |
| 11 | NIT | Use the registered name "ascending requested cost" once |

It confirmed 162 of 192 evaluable windows, the 30 exclusions per target, and the C4/C5 predictions.
