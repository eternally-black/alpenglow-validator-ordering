# Study 3 results text — review dispositions

Three independent reviews of the Study 3 text in REPORT.md and README.md ran on 2026-10-26, before publication, from
the packet [STUDY3-results-packet.md](STUDY3-results-packet.md):
- GPT (gpt-6.1-sol), through the user's `codex exec` orchestrator: [STUDY3-results-gpt.md](STUDY3-results-gpt.md);
- Claude Fable, reading as a bounty judge: [STUDY3-results-fable.md](STUDY3-results-fable.md);
- DeepSeek (deepseek-flash): [STUDY3-results-deepseek.md](STUDY3-results-deepseek.md).

All three were advisory; the author made every change. None found a numerical discrepancy: GPT and Fable checked
the counts, intervals, p-values, windows, slots and lamports against the results files, ledgers and raw data. Fable
scored the whole submission design 9, verifiability 9, analysis 8, engineering 8.

## Changes

| Source | Finding | Disposition |
|---|---|---|
| GPT 1 | "order our probes exactly as … predicts" overstates the three-study headline | **Fixed:** "as … predicts, though not equally strictly". The perfect order is claimed only for Study 3's complete pairs |
| GPT 2 | "Robust to selection" needs its boundary: the bound covers evaluable windows, not excluded ones | **Fixed** in the REPORT answer, §6.5 and the README Study 3 row. §6.5 adds that no probe was sent in any excluded window, so they cannot select by label |
| GPT 3 | The README omits the assumption that each key was stable across the three days | **Fixed:** the README limitation bullet states it and links REPORT §9; the REPORT answer and §6.6 state it too |
| GPT 4 | §7 lists the never-sent probes but not the 12 expired ones | **Fixed:** 648 sent, 636 landed, 12 expired, the four probes of each of the BAM node's three lost windows (#10, #14, #18), and the 93,000-lamport ledger charge that cost nothing on chain |
| Fable | The 30 excluded windows were whole bursts skipped before any send, with reasons recorded; the text said "a probe that was never sent" | **Fixed** after checking `windows.jsonl`: 26 late against the 100 ms bound, 3 BAM windows whose stream the node closed, 1 Agave window whose stream timed out before opening. No window sent a partial burst. In §6.5 and §7 |
| Fable | "The reward numerator is established" presupposes the ratio form | **Fixed:** "reward term", in §6.6 and §9 |
| Fable | §6.6's list of what is not separated omits the change of key over time | **Fixed** |
| Fable, DeepSeek 7 | The README shows the priority fee, REPORT the reward, and nothing relates them; cost units are not stated | **Fixed:** §6.5 gives the cost formula (cost-model units) and the reward (priority fee + 2,500 lamports); the README defines `reward` where it gives the priority formula |
| Fable, DeepSeek 2 | "About 10⁻⁶" for the BAM node's Holm p | **Fixed:** the exact value is 2 × 0.5²¹ = 9.5 × 10⁻⁷, so all twelve Holm p-values are below 10⁻⁶. The text now says so, notes the stored six-decimal `1e-06`, and keeps the worst-case bound labelled as a separate statistic |
| DeepSeek 3 | Name the positive controls | **Fixed:** Agave `7QQGNm3p` and Firedancer `EvnRmnMr` |
| DeepSeek 4 | The BAM node's excluded and lost windows should read as disjoint | **Fixed:** "three of its 24 evaluable windows" |
| DeepSeek 5 | The bold "The key is identified" should carry the scope | **Fixed:** "The key is identified among the registered candidates" |
| DeepSeek 1 | "318 complete pairs" conflates pairs and windows | **Clarified, not an error:** 159 windows with both probes landed, two pairs each (C4, C5), give 318 pairs. The answer now says "(C4 and C5 in 159 windows)" |
| DeepSeek 6 | "Holds whatever share of the signature fee" reads as a claim about reward variants | **Clarified, not an error:** it is the registered robustness of C4's prediction (PREREGISTRATION-3 §2), not a claim to separate the variants. The sentence now adds that this is why Study 3 cannot tell those variants apart |

## Not changed

| Source | Finding | Why |
|---|---|---|
| Fable (NIT) | Figure labels are glyph paths, not selectable text | Deliberate: text as paths keeps every figure byte-identical across platforms, which `docker compose up` checks. Each figure has full alt text, and the numbers are in the tables beside it |
| DeepSeek 8, 10, 11 | Exact p phrasing; the "no fee" gloss; use "ascending requested cost" once | The p phrasing is covered by the fix above. "No fee" is accurate (never-sent probes are not charged), and PREREGISTRATION-3 §1 defines cost alone as ascending requested cost |
