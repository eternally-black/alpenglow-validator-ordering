# Review of PLAN v1 — DeepSeek-V4.1-Flash (1017 build), thinking=max

Received 2026-10-23 via the `deepseek_ask` bridge (31k reasoning tokens). Verbatim answer below.

---

1. [BLOCKER] Kit A cannot separate "total priority fee" from "total fee" — with one signature, total fee = 5,000 + priority fee, so their rankings are identical (τ=1), violating §2.3's pairwise |Kendall τ|≤0.2 and making §4.2 key identification mathematically impossible. Fix: drop one candidate or vary signature count/base fee; pre-register them as an equivalence class.

2. [BLOCKER] The "pre" τ=−150 ms buffer assumption is invalid for direct Agave/Firedancer/Jito ingress — F6 says non-leaders never forward unstaked txs, so probes are dropped, not buffered; for BAM/Harmonic they spill to the previous leader. §2.3/§3. Fix: remove "pre" as a target-key test for direct ingress; treat it only as a spill-over control; use +5–20 ms bursts and explicitly model streaming.

3. [BLOCKER] Kit C tests the wrong Agave tie-break — source says BTreeSet pops highest transaction id, not reverse arrival; "A then B" will measure signature-hash order, and §4.4's simulator is calibrated to a false rule. Fix: compute predicted tx-id order, grind/select pairs with id-order opposite send-order, randomise send order, and fit id-delta vs send-delta.

4. [BLOCKER] A <2 ms burst of 10 streams does not guarantee all Kit A probes are in Agave's container before a scheduler pass — greedy streaming may execute the first arrivals, so contended order becomes arrival order, not priority. §2.3/§3. Fix: validate on real Agave v4.3.2 localnet; if passes split the burst, scope the claim to "streaming priority" and do not claim to separate key for non-buffering clients.

5. [MAJOR] Timing is not credible from a home connection in Ukraine — F2 requires ~±30 ms, §9 tolerates ±100 ms, but BAM/Harmonic auctions are ~50 ms and slots are 200 ms; RTT jitter will blur Kit B and cross slot boundaries. Fix: require a low-latency VPS (Frankfurt/Amsterdam), per-target RTT compensation, or abandon absolute τ and rely only on within-burst Δt.

6. [MAJOR] Informative censoring/selection bias — low-priority probes may not land in full blocks or BAM/Harmonic auctions; §4.2 then computes concordance only on landed pairs, biasing ε and creating false "rules." Fix: model landing as an outcome, report landing rates by key, stratify by block load, and pre-register a censoring sensitivity analysis.

7. [MAJOR] Payer pool is underfunded — 40 payers × 650,240 lamports is rent-exempt only; ~4,032 probes / 40 ≈ 101 probes/payer × ~6,800 lamports ≈ 687k fees, exceeding each payer's balance. §2.4/§5.1. Fix: fund payers with rent + allocated fees (~1.4M each), or top-up from a ledger; use 80+ payers and test depletion.

8. [MAJOR] Kit B has a slot-boundary confound — early τ=+60 ms plus Δt up to 250 ms crosses into the next slot; §4.1 says cross-slot is a different mechanism, yet §4.2 fits one overtake curve. Fix: restrict same-slot pairs (e.g. t0=+10 ms, Δt≤150 ms) or pre-register separate same-slot/cross-slot models.

9. [MAJOR] BAM/Harmonic "leader type" is not a per-validator client scheduler — shared ingress/external builder decides order, and a ≤60 s gossip snapshot is stale for an 800 ms window; §2.1/F4/F5. Fix: snapshot immediately pre/post window, use Kobe + block features, capture validators.app per window (make H5 required), and label results as ingress/auction, not client pack.

10. [MAJOR] Kit B cannot distinguish "no buffer/streaming" from "FIFO buffer" — both give P(overtake)≈0 for Δt>0; §4.2's model selection will mislabel Agave. Fix: add simultaneous-burst/arrival-order tests, estimate pass interval directly, and use passive sawtooth only as corroboration.

11. [MAJOR] Statistical plan treats pairwise comparisons as independent Bernoulli and uses arbitrary LR≥20 thresholds — pairs share transactions, keys are selected over 6 candidates, and testing is across validators/keys; §4.2/§4.4. Fix: window-level cluster/permutation inference, simulate the full selection procedure, pre-register equivalence classes, and report CIs/MDE rather than pass/fail.

12. [MAJOR] 13-day timeline and 12–14 validators are over-scoped versus the 6-validator/3-client minimum — P1–P2 build Rust QUIC/clock/ledger/simulator/localnet in 4 days, pilot covers only 4 validators, and campaign is 3 days; §2.1/§7. Fix: cut to 6–8 validators and 4 client types, 24+ windows each, drop optional modules/site, and pilot one window per ingress type.

13. [MINOR] The 0-lamport transfer to a non-existent account is an avoidable unverified risk; §2.2 admits fallback. Fix: make the fallback primary — 0-lamport self-transfer plus a dummy writable account in the message — and verify on localnet.

14. [MINOR] The uncontended half is confounded by 4 workers/parallel entry packing; §4.2's "contention effect" difference is not clean. Fix: use contended pairs for primary key inference and report uncontended only as a parallel-scheduling observation.

15. [MINOR] Over-engineering — static site, Old Faithful entries, ≥300 blocks/client, cargo-mutants, 5-model cross-review (§4.3/§5/§7) consume time without improving the core claim. Fix: defer until after a defensible 6-validator dataset exists.

## Ideas that would materially raise the score
- Run the full probe kit against real Agave v4.3.2 localnet and publish whether it recovers P vs CU price vs arrival; this directly validates Design Validity.
- Use signature grinding to control tx-id order for tie-break, and multi-signature probes to break total-fee/priority-fee equivalence.
- Add a low-latency VPS and per-target RTT compensation; measure QUIC stream completion/ACK order as an arrival proxy.
- Pre-register landing/censoring models and report landing rates per client/ingress; "no rule" is stronger when you show why probes vanished.
- Use matched windows by block load and include a negative control sent to a non-leader.
- Prioritise 6–8 validators, 4 client types, 32+ windows, and clear equivalence classes over breadth.

---

## Triage notes (lead, 2026-10-23)

- **#13 is already resolved.** The mainnet simulation (research note 02) shows the 0-lamport transfer to a non-existent account succeeds.
- **#2 conflates two different things.** "Never forwarded by a non-leader" is not the same as "not held by the upcoming leader itself". We send directly to the upcoming leader. Whether it holds early packets is checked against source (Fable review) and in the pilot offset sweep.
- **#3:** the tie-break comparator uses the container's internal id, not arrival. Kit C becomes a descriptive equal-key experiment (agrees with the GPT review, #9).
