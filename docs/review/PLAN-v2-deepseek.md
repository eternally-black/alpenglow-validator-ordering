# Re-check of PLAN v2 — DeepSeek-V4.1-Flash (1017), thinking=high

Received 2026-10-23. The answer is reproduced verbatim below. All 10 findings were fixed in place in PLAN.md, as listed in its header.

---

Not sound. Contrast table recomputes exactly with the stated formula: A cost 2,335/P 1,498,287; B 4,335/922,509; A′ 18,711/187,045; hi 2,335/2,354,452; fees 6,000/6,500/8,000; ratios 1.62/4.93/8.01/12.6. §2.6 K=49,500 and T=54,000 also check arithmetically. All v1 BLOCKERs are substantively addressed; the v1 MAJOR timeline finding is only partially resolved (5).

1. [MAJOR] §2.3/§2.4/§4.2 — For shared ingress the design is "streaming only"; C1–C3 require both members simultaneously eligible. If the builder is streaming, first-sent wins and C1–C3 cannot separate economic key from FIFO/random. §2.3 says arrival and random both give 50/50, so "patterns are distinct" is false; §3.1 nevertheless says priority-vs-arrival is identified. Fix: gate shared-ingress C1–C3 key claims on per-window auction/batch evidence, send pairs as simultaneously as possible, and add a first-sent conditional estimand plus FIFO/random to the compatible set; otherwise label key "unidentified" for shared ingress.

2. [MAJOR] §4.2 — Compatible-set inference contradicts the multiplicity plan. It uses one-sided 95% bounds per contrast but declares an 18-test Holm family; joint 3-contrast coverage is not 95%. "Ties must be compatible with 0.5" also needs an equivalence interval, not a one-sided bound. Fix: pre-specify Holm/simultaneous bounds and an equivalence margin; keep unadjusted bounds exploratory.

3. [MAJOR] §2.6 — Worst-case budget arithmetic is wrong. Smoke ≤0.001 SOL = 1.0M lamports and pilot ≤0.004 SOL = 4.0M, already 5.0M, but the line "Smoke + pilot + funding/sweep + Memo" is 3.6M. Corrected worst-case is at least 28.46M (0.0285 SOL), not 26.5M/0.0265; headroom is ~43%, not 47%. Cap still safe. Fix: recompute with caps; update wallet/headroom.

4. [MAJOR] §2.4/§3.1 — Firedancer LIFO is called "identified" with too few equal-key pairs. Core FD has 16 T-windows, one equal-key pair/window split over Δt∈{0,10,40} (~5/level); core+extended FD gives ~15 informative Δt>0 pairs, not 29. Zero failures in 15 gives 95% lower bound ~0.82, not P≈1/0.9. Fix: increase equal-key pairs or label descriptive, not identified.

5. [MAJOR] §7 — v1 timeline MAJOR only partially resolved. Oct 24 builds crate+localnet+QUIC v0; Oct 25 collector+e2e+dry-run+5-ingress smoke; Oct 26 pilot+sim; Oct 27 freeze+Memo+Stage1. Any BAM/Harmonic smoke failure at the Oct 25 hard stop leaves no time to find backups before Stage1. Fix: pre-build sender before Oct 24, run smoke earlier, pre-identify backup endpoints, and pre-commit fallback coverage.

6. [MINOR] §2.6/§2.4 — T-window 54,000 assumes the equal-key pair uses 6,000-lamport probes; §2.4 never specifies that template. If equal-key uses hi (8,000 each), T=58,000 and worst case rises by ~480k. Fix: state equal-key L/p/D and recompute.

7. [MINOR] §2.6 — H/S split is unspecified. Core 17.6M assumes 3H+3S = 90k/validator; six H-windows cost 108k, making core 17.7M. Fix: specify H/S counts.

8. [MINOR] §2.2 — "Expire 3–6 s after the window" is off: aged 120–135 slots at send leaves 3–6 s after send, i.e. ~2.05–5.05 s after window end. Fix wording.

9. [MINOR] §2.3 — "P ratio" orientation is inconsistent: C1 A/B, C2 B/A′, C3 A/A′. Fix: label max/min or state numerator.

10. [MINOR] §2.2/§2.4 — "One payer per probe per window" does not explicitly forbid payer reuse within a window; payers are writable, so reuse creates cross-pair conflicts. Fix: assign eight distinct payers per window from the 24-pool and log assignments.
