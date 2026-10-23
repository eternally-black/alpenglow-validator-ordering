You are an independent senior reviewer (Solana core internals + experimental design + statistics). Read these files in this repository:
- docs/BOUNTY.md (verbatim bounty brief, judging weights)
- docs/PLAN.md (the plan under review, v1)
- docs/research/01-alpenglow-and-network-state.md, 02-transaction-path-and-tooling.md, 03-client-schedulers.md (verified facts as of 2026-10-23, post-Alpenglow mainnet)

Task: adversarially review PLAN.md as a bounty judge would (Design Validity 35%, Verifiability 25%, Analysis Quality 25%, Engineering 15%). Find everything wrong, confounded, missing, unrealistic or over-engineered. Specifically check:
1. Can the probe kits truly discriminate the candidate ordering keys (Agave reward/cost priority vs CU price vs total fee vs arrival order) and scopes (streaming pass vs ~50 ms batch auctions vs pre-window buffering) given how Agave's greedy scheduler, BAM, Harmonic fba and Firedancer pack actually work? Propose better designs if not.
2. Hidden confounds: QUIC stream processing order, unstaked throttling, shared BAM/Harmonic ingress routing, pacing, slot boundaries, the assumption that a 0-lamport transfer to a non-existent account succeeds, payer rotation, blockhash choice, leader handover.
3. Statistics: dependence between pairwise comparisons inside a window, the decision thresholds, power/simulation approach, multiple testing, what to pre-register.
4. Feasibility of the 13-day timeline (deadline 2026-11-05) and 0.05 SOL budget; what to cut first.
5. What judges would reward that the plan misses.

Write your FULL report yourself into the file docs/review/PLAN-v1-gpt.md (create it). Format: numbered findings, most severe first, each tagged [BLOCKER|MAJOR|MINOR] with: issue — why (cite plan section) — concrete fix. Then a section "Ideas that would materially raise the score". Do not modify any other file. In your final reply give only a 15-25 line summary.
