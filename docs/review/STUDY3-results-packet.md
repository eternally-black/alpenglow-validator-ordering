# Review packet — Study 3 results text, before publication (advisory only)

You are an independent reviewer of a bounty submission. **Do not modify any project file.** Write your report to
`docs/review/STUDY3-results-gpt.md` (create it) and nothing else.

## Context

Studies 1 and 2 (already reviewed) found that six Solana validators order our probe transactions as Agave's priority,
reward ÷ (cost + 1), predicts, but could not separate that from ordering by requested cost alone. Study 3 was
pre-registered to separate the two (`docs/PREREGISTRATION-3.md`, frozen; hashes in mainnet Memo `2C57e22K…`), run on
2026-10-26, and analysed with the frozen code. The text describing it was just written. It goes public next.

## What to review

New or changed text:
- `REPORT.md`: the answer at the top (first ~45 lines), §1 (the three Study 3 timeline rows, the targets table's
  Study 3 column), §2 (one sentence pointing to §6.5), §6 heading, **§6.5 and §6.6**, the Study 3 items in §7 and §8,
  §9 (first three bullets), §10 (Study 3 lines), §11 (all-studies line and the Study 3 table).
- `README.md`: the Result and Study 3 rows of the top table, the cost and compliance cells, the contrast tables in
  §1, the validators table's Study 3 column, the first bullet of "What this design does NOT separate", §4, §7.
- `figures/study3-contrasts.svg` (drawn by `fig_study3` in `analysis/itb_analysis/figures.py`).

Sources of truth to check every number against:
- `data/derived/study3/results.json` and `summary.md` (the frozen analysis output);
- `data/derived/study3/verify-archive.json`, `verify-chain-sample.json`;
- `data/derived/ledgers/study3.csv`, `summary.json`;
- `docs/CAMPAIGN-LOG.md` (Study 3 entries at the end), `design/campaign-study3.json`;
- `docs/PREREGISTRATION-3.md` (normative: verdict wording §5, scope §10), `docs/POWER-3.md`.

## What to look for (concrete: file, line, what is wrong, fix)

1. **Every number** in the new text: counts, intervals, p-values, the send-order range, window and exclusion counts,
   slots, times, lamports. Does each match its source exactly?
2. **Overclaiming.** Does any sentence say more than the pre-registered verdict allows ("identified among the
   registered candidates", the additive-key limit, reward variants, cross-study stability, regimes tested)? Is
   anything stated as tested that was not?
3. **Consistency** between README, REPORT, the campaign log, the figure and the results files, and with the frozen
   §5 verdict texts.
4. **Honesty of §7 and §8:** are the Study 3 problems and deviations complete and accurately described (for example
   the prior-claim files whose hashes changed, the pinned analysis tree, the dry runs)?
5. **Reader clarity** for a bounty judge: anything confusing, contradictory, or missing that a judge would need.

Rank findings BLOCKER / SHOULD-FIX / NIT. Keep the report under ~1,200 words.
