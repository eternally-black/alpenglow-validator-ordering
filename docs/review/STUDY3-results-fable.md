# Study 3 results text — judge's review (Claude Fable), 2026-10-26

Verbatim report of a read-only review of the Study 3 additions to REPORT.md and README.md, reading as a bounty judge.
Dispositions: [STUDY3-results-dispositions.md](STUDY3-results-dispositions.md).

---

**1. Clear in 30 seconds?** Yes. README "Result" bullet 2 and REPORT answer bullet 2 say the same thing in the same words: Studies 1–2 could not tell reward ÷ cost from cost alone; Study 3 added a costlier-but-better-paying probe (C4) and an equal-cost pair (C5); 318 of 318 pairs went the reward's way; "identified among the registered candidates". The figure's alt text states what cost alone would have predicted (0 and 0.5), which is exactly the contrast a reader needs.

What would trip me: the README probe table lists A/Y/hi with a **priority fee** column (1,000 / 6,000 / 3,000) while REPORT §6.5 lists the same probes with a **Reward** column (3,500 / 8,500 / 5,500). Nothing says reward = priority fee + 2,500, so the two tables look like they disagree about A. Second, §6.5 says each excluded window "had a probe that was never sent"; the raw run shows every one of the 30 windows sent *nothing* (120 = 30 × 4), and no reason is given.

**2. Overclaim / missing limitation.**
- The verdict wording is carried faithfully: README, REPORT top, §6.5 table footnote and §6.6 all say "among the registered candidates", and both say reward − λ·cost is not excluded. Good.
- Overreach in two places: §6.6 "The reward **numerator** is established" and §9 "the reward **numerator** stayed open … closed it". "Numerator" presupposes the ratio form, which PREREGISTRATION-3 §10 says Study 3 cannot establish. The pre-reg's own vocabulary is "reward term / reward effect".
- §6.6's "still not separated" list omits **change over time**, the one assumption the verdict itself rests on (three days combined; PREREG §10 bullet 2). It is in §9, but §6.6 is where the verdict is asserted.
- Missing explanation: `windows.jsonl` shows 26 of the 30 skipped windows were skipped as `late`, 3 BAM windows as `open_uni: closed by peer: dropped`, 1 Agave as a timed-out stream — all four probes each time, before any send. PREREG §9 promises "the reasons for each exclusion"; `not_all_sent` is a category, not a reason. The upside is unstated too: a window skipped before any send cannot select by label.

**3. Numbers cross-checked (README / REPORT / summary.md / results.json / raw / pre-reg):**
318 = 2×(31+29+24+21+24+30) ✓ · 162/192 evaluable, exclusions 1/8/8/8/3/2 ✓ · exact lower bounds 0.89/0.88/0.86/0.84/0.88 = 0.025^(1/n) ✓ · BAM Holm p: 2·0.5²¹ ≈ 9.5×10⁻⁷, reported "about 10⁻⁶", results `1e-06` ✓ · BAM worst case 2325/2²⁴ = 1.39×10⁻⁴, reported 1.4×10⁻⁴, results `0.000139` ✓ · send-order 11/24 = 0.46 … 13/24 = 0.54 ✓ (all twelve cells match summary) · priorities 1,498,287 / 2,997,179 / 2,354,452 recompute from reward·10⁶/(cost+1) ✓ · λ=1 values 1,165 / 5,665 / 3,165 / −335 / −15,211 ✓ · bound b < 10c₀ + 9,000 and 22,360 ✓ · landed fees 4,929,000 = 159 complete windows × 31,000 ✓; 93,000 expired = 3 BAM windows × 31,000 ✓; 636 = 162×4 − 12 ✓; 120 = 30×4 ✓; 5,069,000 and 47,995,000 totals, 42,926,000 carry-over, 5,952,000 worst case ✓ · Memo id and slot 461,631,524 identical in both files ✓ · `analysis_tree be2eaf04…`, prior-claim commit `ba141b8…`, 624 gossip snapshots all match manifest/raw ✓. No inconsistency found.

**4. Scores (whole submission as it now reads).** Study 3 raises design and analysis clearly, verifiability slightly, engineering about neutral.
- Design **9/10**: Study 3 closes the one identifiability hole the authors themselves flagged, with pre-registered contrasts robust to the reward definition, positive controls, and OC simulation including the `cost_only` and `additive` cases.
- Verifiability **9/10**: Memo-anchored hashes, pinned analysis tree, prior claims frozen in the manifest, `verify_frozen_study3.py`, ledger export and archive checks make every number traceable.
- Analysis **8/10**: scope is stated honestly and intervals/selection bounds are exact; held back by the "numerator" slip and the unexplained exclusions.
- Engineering **8/10**: everything sent landed except 3 BAM windows, but 30 of 192 bursts (25 % on three targets) were skipped as late and the text does not say so.

**5. Fixes.**

BLOCKER — none.

SHOULD-FIX
- REPORT §6.5, "Windows" bullet: replace with "**Windows:** 162 of 192 were evaluable. In each of the other 30 the whole burst was skipped before any send, so all four probes were never sent (no fee): 26 because the burst would have been late (> 100 ms past its planned time), 3 BAM windows because the node closed the stream, 1 Agave window on a timed-out stream. Skips per target: 8 each for Firedancer, Agave + BAM and Agave + Harmonic, 3 for Jito-Solana, 2 for Firedancer + Harmonic, 1 for Agave. A window skipped before any send cannot select by label."
- REPORT §6.6 first bullet: "The reward numerator is established" → "The reward term is established".
- REPORT §9 first bullet: "the reward numerator stayed open" → "the reward term stayed open".
- REPORT §6.6, under "What is still not separated", add: "a change of key between the three days; the verdict assumes each target's key held from Study 1 to Study 3".
- REPORT §7 "Study 3: probes never sent": append "All were whole-burst skips: 26 windows late against the 100 ms bound, 3 BAM windows with the stream closed by the peer, 1 Agave window on a stream timeout."

NIT
- REPORT §6.5 table caption (or README §1): add "Reward = priority fee + 2,500 lamports, the unburned half of the signature fee; the README table shows the priority fee."
- REPORT §6.5: "about 10⁻⁶ for the BAM node's two" → "9.5 × 10⁻⁷ for the BAM node's two".
- figures/study3-contrasts.svg renders all labels as glyph paths (no `<text>` nodes), so numbers are not selectable or searchable; regenerate with `svg.fonttype: none`. The alt text already compensates.
