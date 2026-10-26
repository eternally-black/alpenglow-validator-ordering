# Final pre-publication review — dispositions (2026-10-26)

Three independent reviews of the finished submission:
- **GPT** (gpt-6.1-sol via `codex exec`): method and facts, [FINAL-gpt.md](FINAL-gpt.md); packet
  [FINAL-packet.md](FINAL-packet.md).
- **DeepSeek** (deepseek-v4-flash, thinking, effort max): every number in README and REPORT against the results and
  the log. Its answer is quoted below.
- **Claude Fable**: a fresh judge's reading against the brief's four criteria. Its scores: Design 9, Verifiability 8,
  Analysis 8, Engineering 9 (of 10). Quoted below where it drives a change.

Every finding was checked against the code and data before acting.

Automated checks run alongside:
- both Memos re-read from the chain: all six frozen files match;
- 108 local links, none broken;
- 49 Rust and 66 Python tests;
- `cargo fmt --check` and clippy `-D warnings` clean;
- `docker compose up` reproducing both studies and every figure;
- the frozen-tree verifier.

## GPT

| # | Finding | Disposition |
|---|---|---|
| 1 BLOCKER | Ordering by requested cost alone predicts every winner reward ÷ cost does (A 2,335 < B 4,335 < A′ 18,711; hi 2,335 < lo 18,711): the reward numerator is not identified | **Confirmed and disclosed.** The README result, the REPORT answer and §2 now say that the pre-registered alternatives are rejected and cost-only is not separated. REPORT §9 explains why and what pair would separate them. Resolving it needs new data under a new registration |
| 2 | The headline mixes confirmatory and exploratory targets | **Fixed:** the six core targets and their replication lead; the four extended ones are labelled exploratory with their qualifiers |
| 3 | The censored sensitivity text says the estimates are unchanged; two Study 1 cells change | **Fixed** (REPORT §4.1, with the two cells). The Study 2 censored changes were added to §6.1 |
| 4 | Undetermined send-order effects presented as proof that arrival does not matter | **Fixed:** FIFO is rejected; send-order equivalence is stated as not established (REPORT §2) |
| 5 | One n printed for a whole row where contrasts differ | **Fixed:** Firedancer buffered n = 32/32/31 (§3), Study 2 Firedancer streaming n = 14/10/12 (§6.1). The other rows have equal n |
| 6 | p-values below 10⁻⁶ shown as 0 (six-decimal serialisation) | **Fixed in display:** `summary.md` prints "< 10⁻⁶"; REPORT §6.2 already gave bounds. The frozen serialisation is unchanged |
| 7 | Send-side observations described as queue or arrival mechanisms; the README spill-over rationale contradicts the result | **Fixed:** README §2 wording (pending vs observed), the spill-over rationale with its contradicting result, and builder mechanisms stated as "consistent with" (REPORT §3, §5) |
| 8 | The inclusion paragraph asserted equality | **Fixed:** "no label asymmetry detected", the two non-identical cells, and the limits of the inference (REPORT §2). README §3 no longer calls fullness and position "covariates" |
| 9 | Horizon brackets without intervals | **Fixed:** exact intervals per cell in `summary.md` (and in the figure). Brackets are labelled descriptive grid crossings, and non-monotone curves are flagged automatically |
| 10 | "Every number" overstates what the reproduction checks; the cost accounting is not public | **Fixed:** the reproduction's scope is stated exactly (REPORT §10). Both spend ledgers are exported with every signature and fee to `data/derived/ledgers/` (`scripts/export_ledgers.py`) |
| 11 | The explorer link shows source on GitHub | **Fixed:** the data are embedded, so the page opens from a clone. The README says to open it from a clone; a hosted page needs GitHub Pages at publication |
| 12 | The planned weekday replication ran on a Sunday | **Disclosed** in REPORT §7 |
| 13 | POWER-2 attributes a pilot statistic to Study 1 | **Fixed** with the campaign figure (5 of 10 targets with every sent probe landed) |

## DeepSeek (verbatim, condensed to the findings)

| Finding | Disposition |
|---|---|
| "All 10 groups … reward ÷ cost" ignores the selection and partial qualifiers | **Fixed** (README, REPORT answer) |
| README "within about 2 ms" overstates the Agave result | **Fixed:** sent together vs a 2 ms head start that wins 80 % |
| README cadence 130 / 560 ms contradicts the measured cadence | **Confirmed:** every campaign run measured ≈ 198 / 268 ms. The README is corrected, and the stale design assumption and its consequences are disclosed (REPORT §7) |
| Sensitivity label differs from the summary's | **Fixed** (REPORT §6.2) |
| Pre-freeze simulation figures given half-paired | **Fixed** (REPORT §7) |
| "Two files" had CRLF; the log names one | **Fixed:** `design/targets.json` (REPORT §7) |
| Peak charge 0.0255 vs 0.0256 SOL | **Fixed:** 0.0256 SOL after closing (REPORT §11) |
| Version strings not shown (brief: "identifiable by version string") | **Fixed:** a validators table with gossip client and version in README §1 and REPORT §1 |

## Fable (judge reading)

| Finding | Disposition |
|---|---|
| Explorer does not open from a file or GitHub | **Fixed** (data embedded; see GPT 11) |
| No validators/version table; "8 client types" framing | **Fixed:** the table, and the framing "four scheduler code bases, reached directly or through BAM and Harmonic: 8 gossip client types" |
| Pre-registered items unreported while §8 says "none" | **Fixed:** inclusion, mixture diagnostic and uncontended C2 are reported. The exploratory items never computed (block-structure statistics, horizon-model fits, fullness strata) are listed as a reporting deviation (REPORT §8) |
| Equal-key comparison mixes regimes | **Checked, not so for the Agave family:** both studies sent its pairs buffered at −150 ms. The comparison is now stated per study with the 10 ms cells (Study 1: Agave 7/7, Jito-Solana 5/7) |
| First screen dense; no compliance row | **Fixed:** the result in three points, a brief-compliance row, a requirement → evidence table (README §4), runtime and data size |
| Tracked drafts look like clutter | **Kept and labelled:** `design/README.md` says what each file is. The drafts are referenced by the campaign log |
| Reviewer model names inconsistent | **Fixed:** README §7 names the Study 2 and final reviews with their model ids. The Study 1 names match their review files |
| "One ledger" vs two ledger files | **Fixed** wording (README cost row) |
| Cost table lacks the return row | **Fixed** (REPORT §11) |
| "arrive 0.05 ms apart" (send spacing) | **Fixed** ("are sent") |
| p-floor wording | **Fixed:** 1/100,001 after Holm × 36 |
| SVG text as paths, no `<title>` | **Kept:** paths make the figures byte-identical across platforms (checked by `reproduce`). Each figure has alt text in README and REPORT |
