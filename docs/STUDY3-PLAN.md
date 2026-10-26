# Study 3 — plan (normative text: [PREREGISTRATION-3.md](PREREGISTRATION-3.md))

**Why.** The final review found a gap Studies 1 and 2 cannot close. Every contrast they ran ranks our probes by
requested cost the same way reward ÷ (cost + 1) does (A 2,335 < B 4,335 < A′ 18,711; hi 2,335 < lo 18,711). A
scheduler that ordered by cost alone would have produced the same data. The cost term is established, by C3, where
price and fee tie. The reward numerator is not (REPORT §9, [final-review dispositions](review/FINAL-dispositions.md)).

**What.** Two new contrasts, on the six core targets:

| Contrast | Reward ÷ cost | Cost alone |
|---|---|---|
| **C4**: Y (L 3,000, 2,000,000 µlamports/CU: cost 4,335, reward 8,500) vs A (cost 2,335, reward 3,500) | Y first | **A first** |
| **C5**: hi (cost 2,335, reward 5,500) vs A (cost 2,335, reward 3,500) | hi first | **tie** |

- C4 decides between the two rules: they predict opposite winners.
- C5 checks the reward effect at equal cost.
- A target's key counts as identified when both are supported and its Study 1 and Study 2 claims are `reward_cost`.

**Design.** 32 windows per target, one C4 and one C5 pair in each:
- direct ingress buffered (−150 ms), shared ingress inside the window;
- send order balanced per contrast; every plan executed, no data-dependent stopping;
- 192 windows, 768 probes, worst-case fees 5,952,000 lamports (0.0060 SOL).

**Hypotheses.** H4-t (L_C4 > 0.5) and H5-t (L_C5 > 0.5) for each target: twelve tests, one-sided exact binomial,
Holm at 0.05, a selection bound, and the Agave and Firedancer positive-control gate. Operating characteristics,
simulated on the frozen design: [POWER-3.md](POWER-3.md).

**Budget: still one cap for everything.**
- A new ledger (`state/ledger-study3.sqlite`) is opened with the compiled 0.05 SOL cap, carrying Studies 1 and 2's
  42,926,000 lamports.
- Headroom: 7,074,000 lamports. The `study3` budget is 6,500,000, which covers the worst case (5,952,000). Setup (Memo,
  payer funding, sweep) takes about 135,000.
- The three studies together cannot pass 0.05 SOL.

**Wallet.** A new master (`DrMFg9Fg…bDxex`) and 24 payers in `keys-study3/` (git-ignored). Funding about 0.04 SOL
covers payer rent and fees; everything left returns to the funder.

**Gate before freezing.**
- Rust and Python tests;
- the frozen Study 1 and 2 designs still regenerating byte for byte;
- a mainnet dry run of the Study 3 design (done 2026-10-26 08:53 UTC, 8 windows, clean);
- independent reviews of this plan, the pre-registration and the code.

**Schedule.** Freeze, Memo and funding on approval. The run takes about 2–3 hours, set by Agave's ≈ 12 windows an
hour; the cutoff is 2026-11-03T23:59Z. Results then go into REPORT §6 and the answer, before the 2026-11-05
deadline.
