# Adversarial review of PLAN.md v1 — Fable (design validity / confounds / statistics / feasibility)

Reviewer role: independent senior reviewer (Solana core internals, experimental design, statistics), reading as a bounty judge would (Design Validity 35 %, Verifiability 25 %, Analysis Quality 25 %, Engineering 15 %).
Inputs read: `docs/BOUNTY.md`, `docs/PLAN.md` (v1, 2026-10-23), `docs/research/01..03`.
Sources re-checked by me on 2026-10-23 at the pinned tags (anza-xyz/agave v4.3.2, jito-foundation/jito-solana v4.3.2-jito, firedancer-io/firedancer v26.10.4, jito-omnidocs @ 4cd4e24, docs.harmonic.gg). URLs are in Appendix A; each factual correction below cites one.

Bottom line first. The plan is unusually strong on intent (self-sent probes, pre-registration, simulation-calibrated thresholds, layered spend cap) and would already beat most passive submissions. But as written it has two design defects that would make the pre-registered procedure either unrunnable (F2) or mis-targeted for ~69 % of stake (F1), one analysis defect that would turn the headline "scope" result into an artefact of queueing (F3), a tie-break hypothesis that the source does not support (F4), and a statistics section whose decision thresholds cannot be met at the planned N (F5). All are fixable in a day of planning if done before P1. The schedule, not the budget, is the binding constraint (F7).

---

## Numbered findings (most severe first)

### F1 [BLOCKER] Shared-ingress targets (BAM + Harmonic ≈ 69 % of stake, 8–10 of the 12–14 planned validators) are mis-probed by the plan's τ = pre regime, and unstaked QUIC acceptance at those ingresses is unverified until Oct 28

**Issue.** §2.3 randomises τ ∈ {pre, early, mid} per window across *all* validators and names *pre* (−150 ms) as the regime that "isolates the scheduler's key from arrival". §2.3 also says that for BAM/Harmonic "pre is expected to spill into the previous leader. That is measured and reported, not hidden." That understates the problem: for shared ingress, a pre-window probe does not test the target validator at all, and the plan spends a third of every shared-ingress validator's windows on it.

**Why.**
- Harmonic: the Remote TPU "continuously aggregates incoming transactions and forwards them to the validator and to all connected block builders"; the block engine then "routes the validator's stream to its currently bound builder" *for each validator's leader window* (docs.harmonic.gg/concepts/harmonic-architecture). Builders therefore hold the whole Harmonic order flow continuously. A probe arriving at a Harmonic IP before V's window sits in a builder pool and is most plausibly emitted by the *next Harmonic leader* (Harmonic ≈ 30 % of slots), not by V. Your "target" for pre-window sends is the Harmonic network, not a validator.
- BAM: the node sends transactions "to a confirmed, connected validator when their leader rotation arrives", and "a BAM Validator can connect to only one BAM Node at a time" (omnidocs bam-overview). What happens to a tx that arrives while no validator connected to that node is leader (held for the next one? dropped? forwarded to another node?) is undocumented at the pinned commit. Note also: "Transactions sent directly to the TPU port are also processed through BAM before execution" — so sending to the validator's real IP does not bypass BAM.
- Acceptance: whether BAM nodes / Harmonic Remote TPUs accept *unstaked* QUIC connections at all, how many streams they allow, and whether they drop zero-priority-fee txs is unknown. §9 lists this as a risk resolved at the P3 pilot (Oct 28) — one day before the campaign. The "mainnet dry-run" gate (P2) cannot answer it: a successful handshake says nothing about acceptance.
- Limits at shared IPs: if those ingresses run an Agave-derived streamer, the limits are 8 concurrent connections per unstaked peer and 8 *new* connections per IP per minute; an excess connection is silently ignored (`incoming.ignore()`), which your sender will see as a handshake timeout (agave `streamer/src/quic.rs`, `nonblocking/quic.rs`). §3 pre-opens a fresh connection per window; two or three BAM targets behind one node IP plus retries will cross 8/min.

**Fix.**
1. Assign τ **by ingress kind**, do not randomise it uniformly:
   - *Direct ingress* (vanilla Agave, JitoLabs without relayer, Firedancer, Rakurai): Kit A/C in the **buffered** regime (τ = pre) for ~75 % of windows, streaming for ~25 %. This is source-backed: Agave buffers packets from 20 slots (≈ 4 s) before its window and drops them unparsed earlier than that (`decision_maker.rs` + `receive_and_buffer.rs`, see F10); Firedancer's pack "receives transactions while it is waiting to become leader and stores them for future execution" (default.toml, `[tiles.pack]`).
   - *Shared ingress* (BAM node, Harmonic Remote TPU, Jito relayer): streaming only, τ ∈ {+60, +250, +450} ms, with a **separate, small spill-over sub-experiment** (2 probes per window at −150 ms and −1 s) whose *outcome* is "which leader/ingress got it, after how long". That is a path finding the brief explicitly asks for, not noise to be hidden.
2. Move a **0.001 SOL mainnet smoke test** to the end of P1 (Oct 25–26): 1 window × 3 probes × {Agave direct, Firedancer direct, one BAM node IP, one Harmonic IP, one Jito relayer}. Use the crudest sender that works. Gate the rest of the architecture (and the target list) on its landing rates. The brief's "do not pay for development" path is advice, not a rule; 0.001 SOL buys the single most important fact in the project.
3. For builders, report per **ingress endpoint (node IP)** as well as per validator: the scheduler under test is the builder, the validator "execute[s] all received transactions in that exact order" (omnidocs). Choose at least one pair of targets that share an endpoint to measure cross-routing directly.
4. Sender: one persistent QUIC connection per ingress IP (keep-alive; Agave idle timeout is quinn's 30 s default, Firedancer's is 10 s with QUIC Retry enabled, so pre-open ≥ 2 RTT ahead), a per-IP new-connection counter capped at 4/min, and never more than 8 concurrent.

### F2 [BLOCKER] The Kit A orthogonality constraint is unsatisfiable: with one signature, "priority fee" and "total fee" are the same ranking

**Issue.** §2.2 fixes the atom at 1 signature, so total fee = 5000 + priority fee for every probe. §2.3 requires pairwise |Kendall τ| ≤ 0.2 between the rankings induced by P_agave, CU price, priority fee and total fee. Two of those rankings are identical (τ = 1); the rejection sampler never terminates and the pre-registered design cannot be generated. (Agave's `reward` = priority fee + 2,500 is also the same ranking; what differs is reward/cost.)

**Fix.**
- Redefine the key set: K1 reward/cost (Agave/Firedancer), K2 CU price (µlamports/CU), K3 priority-fee lamports (≡ total fee at fixed signature count — state this explicitly in "what we do not separate"), K4 arrival order, K5 reverse arrival. Apply the orthogonality constraint to K1–K3 only (5 items, 10 pairs: |τ| ≤ 0.2 means the keys disagree on ≥ 4 of 10 pairs — adequate).
- If you want total fee as a separate key for Harmonic ("priority fees and tips") add a 2-signature variant in a subset of Harmonic/BAM windows (+5,000 lamports, cost +720, reward +2,500 — re-derive all keys per probe).
- Add the three minimal pairwise contrasts from Ideas §I-6; they are what a judge can check with two signatures and they make the ladder's statistics explainable.

### F3 [MAJOR] Kit B measures the low-key probe's queueing delay, not the batching scope, unless both probes sit above the block's marginal priority on the scheduler's actual key; and Δt is crossed with τ in a way that mixes regimes

**Issue.** §2.3 Kit B and §4.2.2 fit P(overtake | Δt) under {step-FIFO, constant, linear batch, exponential} and read the AIC winner as the scope (streaming / 50 ms batch / deep buffer).

**Why.**
- Any scheduler with a continuous priority queue lets a high-key probe overtake at *any* Δt as long as the low-key probe is still pending. Firedancer's default `schedule_strategy = "balanced"` is exactly that: "fill the block at a rate that is just fast enough to fill it by the end" — CUs are released over the slot and pack keeps picking the best pending tx (default.toml). Research note 03 claims Agave 4.3 also paces (I did not verify this; if true the same applies). Under load, "overtake probability" then depends on the low-key probe's rank against the block's marginal priority and on load — not on a batch interval. The model set will pick "constant/exponential", which §4.2.2 would report as "deep buffer".
- The candidate keys matter here: with L = 600 and D = 32 KiB, a p = 0 probe has P_agave ≈ 2,500·10⁶/1,937 ≈ 1.3·10⁶, far above a typical mainnet tx (10,000-lamport fee at 200k CU ⇒ P ≈ 6·10⁴). So on reward/cost schedulers your "low-key" probe is actually top-of-block and is scheduled immediately — Kit B then measures pass granularity as intended. On a CU-price scheduler the same probe is bottom-of-block and may wait or be dropped — Kit B then measures its queueing delay. On a lamport-total scheduler nothing affordable puts you above marginal.
- τ = pre (−150 ms) with Δt = 250 ms places the second probe 100 ms *into* slot 0: the first is buffered, the second is streaming. Mixed regime, uninterpretable.
- Power: 3 pairs × 16 windows = 48 pairs over 10 Δt levels per validator ≈ 5 per level. That cannot select among four models or put a CI on T per validator.
- For Agave the source-backed streaming expectation is a cliff at the receive/scheduling-pass granularity, *not* at a 5 ms coalesce: in 4.3.2 each QUIC stream becomes `PacketBatch::Single(packet)` and is forwarded immediately (`nonblocking/quic.rs`); sigverify and `receive_and_buffer` (≤ 512 packets per call) do the batching opportunistically.

**Fix.**
1. Two-stage campaign, pre-registered as such: Stage 1 (Kit A + C) identifies the key per mechanism group; Stage 2 constructs Kit B pairs with **both** probes above the observed block marginal *on that key* (free for reward/cost; ≈ 600 lamports at p = 10⁶ µlamports/CU with L = 600 for CU price; declared unseparated for lamport-total).
2. Add a "pending-queue" model to the set: overtake ⇔ the low-key probe has not been scheduled by the time the high-key one arrives; estimate the low-key probe's own scheduling delay from its landing slot/index and block fullness.
3. Define all offsets relative to predicted window start; never let a pair straddle the predicted slot-0 start; reduce Δt to 4 levels {5, 25, 60, 150} ms, stratified; pool Kit B by mechanism group (ingress endpoint / client), and make per-validator T claims only with ≥ 40 pairs.
4. Stratify by block CU fullness (you already store the blocks) and report the overtake curve separately for < 60 % and > 90 % full blocks.

### F4 [MAJOR] The Agave tie-break prediction ("reverse arrival, B first") is not supported by v4.3.2 source; Kit C also confounds path reordering with the tie rule

**Issue.** §2.3 Kit C and §4.2.3: "Agave predicts B first (reverse arrival)". Research 03 derives this from "pop_last on a BTreeSet → the higher id wins".

**Why.** In v4.3.2 `TransactionId` is `pub type TransactionId = usize;` (`scheduler_messages.rs`) and the id is a **`Slab` key**: `insert_map_only` takes `vacant_entry()` and uses `entry.key()` (`transaction_state_container.rs`). The queue is `BTreeSet<TransactionPriorityId>` with derived `Ord` over (`priority`, `id`) and `pop_last()`. Slab reuses freed keys (most-recently-freed first), so "later arrival ⇒ higher id" holds only while the slab has no holes — i.e. right after `clear_container` (the Forward decision) and before any pops or `clean_queue` removals. During a slot, hundreds of pops free keys and the tie order becomes implementation-defined. In addition, `receive_and_buffer` dispatches prechecks to a check-work queue and drains results as they complete, so insertion order within a burst need not equal arrival order. Kit C's observable P(B first) therefore mixes (i) path reordering, (ii) precheck reordering, (iii) slab state.

By contrast, Firedancer's treap inserts an element that compares equal to the **right** ("treated as if being epsilon larger than all existing equal elements", `fd_treap.c`), and pack schedules by walking `treap_rev_iter` from the best (`fd_pack.c`, `COMPARE_WORSE` cross-multiplication of rewards × compute_est). So Firedancer **deterministically schedules the later-arrived equal transaction first**. That is a sharp, falsifiable prediction the plan does not have. Harmonic says FBA ties are "tiebroken deterministically" without naming the rule.

**Fix.**
- Re-state Kit C hypotheses per client: Firedancer → P(B first) ≈ 1 in the buffered regime; Agave → P(B first) high only in *pre* windows (fresh slab), uninformative in streaming; BAM/Harmonic → unknown deterministic rule; FIFO ⇒ A first.
- Separate the path-noise floor from the tie rule: send tie pairs with Δt ∈ {0, 10, 40} ms **in the buffered regime** (both still pending when the slot starts). Path reordering vanishes by ~10 ms on one QUIC connection; a persistent B-first at 40 ms is the scheduler, not the path.
- Correct research note 03's Agave citation and its "later arrival first among equals" claim.

### F5 [MAJOR] Statistics: dependent pairs, unreachable thresholds at N = 16, uncalibrated LR, and key-dependent selection on "same slot"

**Issue.** §4.2.1 computes pairwise concordance over 10 pairs per window from 5 contended probes, fits a per-key "noisy-deterministic" model by ML, and requires ε ≤ 0.10, LR ≥ 20 vs runner-up, Holm p < 0.01. §4.1 restricts the primary analysis to same-slot pairs.

**Why.**
- Ten pairs from one 5-permutation are one observation, not ten. The ML fit and the LR assume independence; the LR will be inflated by roughly the within-window pair count.
- With violations clustering by window (a burst that straddles two passes, a slot boundary, a builder failover), the effective N is the number of windows. The 95 % upper bound on the window-level violation probability with zero observed violations is ≈ 3/w: 16 windows → 19 %, 30 → 10 %, 45 → 6.5 %. So "ε ≤ 0.10 with a 95 % CI" cannot be shown at 16 windows even if the rule is perfectly strict.
- Same-slot conditioning is selection on the outcome: under a CU-price/fee-keyed builder, p = 0 probes are the ones deferred to later slots or dropped, so the retained pairs are the ones where the key mattered least. A probe pushed to slot 2 by the scheduler *was ordered later*; that is the evidence, not a different mechanism.
- Attrition is absent from the power model: with 5 contended probes and 60 % landing you have ≈ 3 landed → 3 pairs per window.

**Fix.**
- Unit = window. Per-window statistic = Kendall τ_b between observed (slot, index) order and the key's ranking (or the exact-match indicator). Null = within-window permutation of design labels (120 permutations of 5), combined across windows by the sum of τ with ≥ 10⁴ Monte Carlo draws. Key selection = paired per-window τ differences (sign test / Wilcoxon / bootstrap over windows); pre-register "K* is at least as good as the runner-up in ≥ 75 % of windows and the bootstrap CI of the mean Δτ excludes 0". Report pair-level ε with a cluster bootstrap by window and state the window-level bound above.
- Choose N from the bound: ≥ 30 windows for the 6 core validators rather than 16 for 14 (budget is not the constraint: 6 × 30 × 18 × 6,800 ≈ 0.022 SOL).
- Primary ordering outcome = lexicographic (slot, index) over **all landed probes in the target window**; same-slot-only as a pre-registered sensitivity analysis. Cross-window landings are spill-over, analysed under F1.
- Add landing as a co-primary outcome (F9) and attrition (40–80 % landing) to `make power`.
- Pre-register exclusion rules (leader-type change within the window, skipped slot, < 3 landed probes), the multiple-testing family (validators × primary hypothesis), and a budget stopping rule.

### F6 [MAJOR] Slot-clock bias is of the same order as the τ strata

**Issue.** §1 F2 asks for ±30 ms timing; §2.3 uses offsets −150 / +60 / +460 ms; §9 says the strata are "±100 ms tolerant".

**Why.** An RPC node's `slotSubscribe` notifications lag the leader by shred propagation plus replay — tens to hundreds of ms, varying by leader location and load. A slot↔time regression removes jitter, not the bias. Under Alpenglow without the fast-handover gate, slot 0 of a window starts when the leader has the parent, so the first slot's start jitters independently. "+60 ms" can be pre-window in reality and "−150 ms" can be mid-slot-0; you would then be labelling regimes wrongly in the primary analysis.

**Fix.**
- Use `slotsUpdatesSubscribe` and take `firstShredReceived` of the *previous leader's* slots from ≥ 2 RPC endpoints; subtract measured one-way latency (handshake RTT/2 to the RPC and to the target); predict the target's slot-0 start locally from the last 2–3 slots, not from a long regression.
- Calibrate the residual bias in the pilot by sweeping send offsets and reading the landed slot; expect a per-region offset.
- Classify every window **post hoc by achieved offset** (send timestamp vs `firstShredReceived` of the target's slot 0) and analyse on achieved bins; pre-register that the intended τ is the assignment and the achieved τ is the analysis variable.
- Make the Frankfurt VPS the default, not optional; Kyiv → US validators is 120–150 ms one-way with large variance.

### F7 [MAJOR] Scope and timeline: the plan is over-engineered for 13 days, and the critical path (sender, clock, pilot) is squeezed into Oct 26–28

**Issue.** §5–§7: 8 Rust crates, a simulator with 5 schedulers, proptest + cargo-mutants, an interactive GitHub Pages site, Old Faithful entry fetching, a ≥ 300-blocks-per-client passive census, three optional modules, 14 validators, byte-identical reproduction, 7 CI jobs — with P1+P2 at 4 days and a 3-day campaign.

**Why.** Judges weight design (35) and analysis (25) over engineering (15), and the engineering criterion names exactly four things: dry-run, spend cap, logging, containerisation. Everything else is unpaid. The things that can sink the submission (F1, F6) are discovered only when real probes hit real ingresses, which the schedule puts on day 6 of 13.

**Fix (cut list, in order).**
1. Old Faithful entries (stretch, keep as a sentence in "future work").
2. Interactive site → static figures in `REPORT.md`.
3. cargo-mutants / proptest → unit tests plus one integration test that tries to overspend the cap.
4. Modules E and F; keep D only as a 2-window add-on if Firedancer results are clean (it is a genuinely unique FD discriminator — see F11 for the arithmetic).
5. Passive census → the blocks you already fetch for probed windows plus one Chorus-style footrule number per validator for comparability.
6. 14 validators → 8–10, with ≥ 30 windows for the 6 core ones: vanilla Agave (anchor), Firedancer (anchor), HarmonicAgave, HarmonicFiredancer, AgaveBam (if `running_bam`), JitoLabs-direct; then Rakurai, FireBAM, JitoLabs-relayer if time. The brief's floor is 6 validators / 3 clients; depth beats breadth in the 35 % and 25 % criteria.
7. Byte-identical derived data → deterministic numbers compared with tolerance; figures and timestamps excluded.
8. v1 transaction support in the parser only.
9. 8 crates → one binary crate with modules plus one Python package.
10. Schedule: smoke test Oct 25–26 (F1), pilot Oct 27, Stage-1 campaign Oct 28–30, Stage-2 Oct 31–Nov 1, analysis Nov 1–3, audit Nov 4–5.

### F8 [MAJOR] Per-window "leader type" can be wrong in ways gossip and Kobe cannot see

**Issue.** §3 row 1 classifies by clientId × version × ingress × Kobe `running_bam` per window.

**Why.** Harmonic's validator "falls back to its in-client scheduler as a last resort", and the block engine "fails over to another builder running the same scheduling strategy" mid-slot (harmonic-architecture, streaming-mode). Harmonic also offers FIFO, MREV and "Custom Scheduler" strategies per validator; none of this is visible in gossip. BAM nodes were "returning gradually" after maintenance. A window can therefore be assembled by a different mechanism than its label says.

**Fix.** Add block-level mechanism covariates per window from the blocks you already store: descending-run ("sawtooth") count and run-length distribution, position of your probes, and (to investigate, not assume) whether BAM/Harmonic blocks contain a recognisable builder-fee transfer from the leader identity (jito-solana's `bam_manager.rs` applies a `block_builder_fee_info` from the BAM config). Flag windows whose structure contradicts the label and analyse them separately; report the flag rate.

### F9 [MAJOR] Landing is itself an outcome that depends on the key; conditioning the order analysis on landed probes is biased, and the plan treats landing as bookkeeping

**Issue.** §4.1 records landing outcomes; §4.2 analyses order among landed probes.

**Why.** Under reward/cost schedulers your tiny-cost probes are top priority and always land; under CU-price or lamport-fee keyed builders the p = 0 probes are the first to be deferred or dropped; Agave's container evicts the lowest (priority, id) when full; sigverify discards under saturation. Firedancer keeps a missed probe pending until blockhash expiry (≈ 30 s), so a high-stake FD validator (JUPiTERr: ≈ 9.6k slots/epoch ⇒ a window every ~36 s on average) can land a probe from window W in its *next* window — your spill-over classifier must allow "same validator, later window".

**Fix.** Pre-register P(land | key, ingress kind, τ) as a co-primary outcome; show the landing-by-key table per validator next to the order result; run the order analysis with and without a censoring assumption (non-landed = after all landed). The aged-blockhash idea (I-7) bounds the horizon and removes most same-validator carry-over.

### F10 [MINOR] Factual corrections to §1/§2 and the research notes (each with the source)

- **No 5 ms TPU coalesce in 4.3.2.** Each completed stream becomes `PacketBatch::Single(packet)` and is `try_send`-forwarded immediately (`streamer/src/nonblocking/quic.rs`). "One burst → one scheduling pass" is probabilistic in the streaming regime; in the buffered regime it is guaranteed.
- **Unstaked stream throttle** = `MAX_UNSTAKED_TPS (200) × 100 / 1000` = 20 streams per 100 ms **per connection**, and exceeding it *delays* the stream until the interval ends (`throttle_stream` sleeps) rather than dropping it (`stream_throttle.rs`). A 14-probe burst is safe; the research note's "throttle beyond 20" is right but the plan should say "delayed", not "dropped".
- **Connection limits** (`streamer/src/quic.rs`, `nonblocking/quic.rs`): `DEFAULT_MAX_QUIC_CONNECTIONS_PER_UNSTAKED_PEER = 8`, `DEFAULT_MAX_CONNECTIONS_PER_IPADDR_PER_MINUTE = 8` (excess *ignored* silently), `DEFAULT_MAX_UNSTAKED_CONNECTIONS = 2000` (research 02 says 3000; refused when full), `DEFAULT_MAX_STREAMS_PER_MS = 500`, idle timeout 30 s, per-stream `wait_for_chunk_timeout` 2 s.
- **Agave pre-window buffering is source-defined**: decision `Forward` (drop unparsed) when ≥ `HOLD_TRANSACTIONS_SLOT_OFFSET = 20` slots away or after the last leader slot; `ForwardAndHold` (buffer) inside 20 slots; `Hold` inside `FORWARD_TRANSACTIONS_TO_LEADER_AT_SLOT_OFFSET = 2` slots; `Consume` with a working bank. The Alpenglow path uses the slot clock ("PoH tick height no longer advances after Alpenglow activation") (`core/src/banking_stage/decision_maker.rs`, constants in solana-sdk `clock`). The container is cleared on `Forward`, so nothing carries over between an Agave validator's windows. This is a cheap, testable prediction (I-3).
- **Firedancer buffers always**: `[tiles.pack]` "receives transactions while it is waiting to become leader and stores them for future execution", `max_pending_transactions = 65524` with lowest-profit eviction (default.toml); `fd_pack_end_block` does not touch pending treaps; expiry is by blockhash (`fd_pack_expire_before`).
- **Firedancer rewards** = priority fee + `FD_PACK_FEE_PER_SIGNATURE × sigs × FD_PACK_TXN_FEE_BURN_PCT / 100` (`fd_pack_estimate_rewards_and_compute`, fd_pack.c) — i.e. Agave-equivalent; ordering is by exact cross-multiplication rather than Agave's floor(reward·10⁶/(cost+1)), which only matters at exact ties. Cost constants match Agave (720 / 300 / 1 CU per 4 data bytes / 8 CU per 32 KiB page; `fd_pack_cost.h`, agave `block_cost_limits.rs`, `cost_model.rs`). Agave counts the fee payer's write lock and demoted write locks (`cost_model.rs` tests) — your "300·2" is right.
- **Firedancer microblocks**: normal txs are batched up to `max_txn_per_microblock`; it is bundle txs that are one per microblock (fd_pack.c). Research 03's "one tx per normal microblock" should be re-checked against the configured limit before being used as an entry-structure prediction.
- **Agave reward**: `deposit = priority_fee + transaction_fee − burn`, burn "statically 50 %" (`runtime/src/bank/fee_distribution.rs`); priority = `reward·1_000_000 / (cost + 1)` with cost from `CostModel::calculate_cost_for_executed_transaction(tx, compute_unit_limit, loaded_accounts_data_size_limit, …)` (`core/src/transaction_priority.rs`). Confirms §1 F7.
- **Greedy scheduler mechanics** (`greedy_scheduler.rs`): pops in priority order, `max_scanned_transactions_per_scheduling_pass = 100_000`, a tx conflicting with one thread's in-flight/batched work goes to that thread (so your 5 contended probes serialise on one worker in pop order, and a conflicting pair *can* share a batch); conflicts across ≥ 2 threads make it unschedulable and it is re-queued for the next pass; batches are flushed at the per-batch tx target, at a *bytes* target ("15 % of a batch" of shred bytes — new in 4.x) and at the end of the pass. Your uncontended half will spread over 4 workers and come out in worker-completion order — expected, and worth saying in the README as the reason that half is noisier.
- **`create_pinned_leader_updater`** is behind the Cargo feature `dev-context-only-utils`, not `agave-unstable-api` (`tpu-client-next/src/leader_updater.rs`). Implement your own `LeaderUpdater` (public trait, two methods).
- **jito-solana v4.3.2-jito**: BAM code is `core/src/bam_manager.rs`, `bam_connection.rs`, `bam_dependencies.rs`; the cited `…/bam_scheduler.rs` path returns 404 at the tag — fix the citation in research 03. `bam_manager.rs` switches `clientId` to AgaveBam on connect and back to `JitoLabs` on disconnect, stores BAM's TPU/TPU-forward sockets from the BAM config, and resets builder-fee info on disconnect; the gossip repoint itself lives elsewhere but your `getClusterNodes` snapshot already confirms it empirically.
- **BAM docs at the pinned commit do not define the priority score**; they give "~50 ms" rounds with maker-plugin txs structurally first ("cannot be changed by paying higher fees or tips"), then "bundles and regular transactions compete on the same priority score" (maker-plugin/how-it-works). So in a BAM block your probes are never first in a batch; the leading plugin run must be excluded from sawtooth statistics.
- **Harmonic FBA**: "collects all incoming transactions over a 50 ms buffer" (double-buffered), "sequences them by descending priority fees and tips", ties "tiebroken deterministically"; FIFO ("strictly in the order they arrived at the builder") and MREV (proprietary, streaming) exist; both Salsa and Samba "default to fba" (scheduling-strategies). "Priority fees" is ambiguous between lamport total and per-CU — which is exactly your test, so say so.
- **`MAX_BLOCK_UNITS`** in the v4.3.2 cost-model is 60 M / 100 M (SIMD-0286); the 50 M figure comes from SIMD-0525 runtime scaling — cite accordingly in §1.

### F11 [MINOR] Probe atom details

- **0-lamport transfer to a non-existent account**: at the program level there is no destination or rent check and `test_transfer_lamports` covers zero (`programs/system/src/system_processor.rs`); a 0-lamport account is not rent-paying, so the runtime's rent-state check does not fire. Keep the localnet check as a formality and also assert `meta.err == null` and that the lock account does not exist afterwards.
- **CU floor**: 3 ComputeBudget ixs + 1 System transfer consume 4 × 150 = 600 CU; §2.2's L ∈ {450 …} lands and *fails* when ix2 is present. Raise the floor to 600 (or 450 only when `SetLoadedAccountsDataSizeLimit` is omitted). Failed probes still order correctly, but judges will ask why you paid for failures.
- **D = 32 KiB** is safe only if every loaded account's data fits (payer 0 B, lock 0 B, System and ComputeBudget builtin accounts are tiny); assert `meta.costUnits` equals your model on localnet and on the first mainnet pilot before relying on it.
- **Module D arithmetic** (if kept): FD's divisor = 1 + (allocated_data × max_cost_per_block) / (cost_estimate × max_allocated_data_per_block). With a 2-sig probe (cost ≈ 2,650), 50 M CU blocks and 100 MB data delta, `Allocate(10_240)` gives divisor 2 → rewards halved; `Allocate` on a 0-lamport signer passes the program (no lamport check) and fails the post-execution rent check, so no rent is spent — consistent with §2.3.
- Firedancer's penalty treap (`PENALTY_TREAP_THRESHOLD 64UL` refs) is irrelevant at 5 contended probes.

### F12 [MINOR] Budget and engineering

- The compiled hard maximum of 0.1 SOL (§5.1) contradicts the brief's "≈ 0.05 SOL"; set the compiled maximum to 0.05 and the planned spend to ≤ 0.035. Say in the README that wallet funding (0.09) ≠ spend and that 0.026 is refundable rent.
- The payer pool can be ≈ 20 instead of 40 with the aged-blockhash idea (I-7); locked rent halves.
- `docker compose up` should finish in ≤ 5 minutes on the public RPC: verify a sample of claims, regenerate the report, diff numbers with tolerance. Put the 10-minute mainnet dry-run and the live run behind profiles. "No keys needed" must be literally true (public RPC at 6 `getBlock`/10 s ⇒ sample ≤ 30 blocks).
- Commit slim extracts only for probed slots; full blocks as a release asset with a manifest. 50 KB × ~1,000 blocks in git is tolerable but unnecessary.
- Research 02's `packet_delay_ms = 50` for the self-hosted Jito relayer means JitoLabs-relayer validators get Agave's rule shifted by ≥ 50 ms plus relayer batching; treat "relayer" as its own ingress kind (the plan does) and do not pool it with JitoLabs-direct until shown equal.

### F13 [MINOR] Pre-registration gaps

§4 should also freeze: the target list with ingress IPs and backups; N per validator and per τ bin; one primary endpoint per validator; exclusion rules; spill-over handling; the Kit B model set and pooling level; the stopping rule; and "what would change our mind" for each hypothesis. Timestamp the hash of `PREREGISTRATION.md` with a Memo transaction on mainnet (≈ 5,000 lamports) in addition to the git commit.

### F14 [MINOR] Pooling level

§3 row 1 is right to report per validator first. Add the "mechanism group" level (ingress endpoint for builders; client for direct) with a heterogeneity test (per-window τ by validator within group) before pooling, and say explicitly that for BAM/Harmonic the validator is not the scheduler.

### F15 [MINOR] The P2 "mainnet dry-run" gate overstates what it learns

A handshake to a BAM/Harmonic IP proves reachability, not acceptance, throttling or routing. The gate text should say so, and F1's 0.001 SOL smoke test should be the actual gate for the target list.

---

## Can the kits discriminate what the plan claims? (direct answer to packet item 1)

| Claim | Discriminable as designed? | With the fixes above |
|---|---|---|
| Key: reward/cost vs CU price vs lamport fee | **No** — constraint unsatisfiable (F2) | Yes for K1–K3, in the buffered regime for direct ingress and the 50 ms-batch regime for builders; lamport total vs priority fee only with 2-sig variants |
| Key vs arrival order | Yes in the buffered regime; weak in streaming on Agave (pass splitting) | Yes; assign τ by ingress kind (F1) |
| Scope: streaming pass vs ~50 ms batch | Partly — confounded with queueing (F3) | Yes, when both probes are above marginal on the identified key and Δt stays inside one regime |
| Scope: pre-window buffer | Not for shared ingress (F1); yes for direct | Yes; add the Agave 20-slot cliff vs Firedancer keep-everything test (I-3) |
| Scope: whole-slot auction vs pending queue under pacing | **No** | Still no — declare unseparated unless stratified by load; say so in "what we do not separate" |
| Tie-break | Confounded with path noise; Agave hypothesis unsupported (F4) | Yes for Firedancer (deterministic LIFO among equals), descriptive for others, with Δt-spaced tie pairs |
| Strictness ε with CI | Not at N = 16 (F5) | Yes at ≥ 30 windows with window-level inference |
| Contention effect | Yes (same tuples in both halves is a good design) | Note that on Agave the uncontended half is worker-completion order by construction; on Firedancer it may stay in treap order within a microblock — itself a client discriminator |

## Hidden confounds checklist (packet item 2) — status after the fixes

QUIC stream processing order: one connection per ingress, order ≈ FIFO into sigverify; sub-ms reorder possible via the precheck pool — measured by Δt-spaced tie pairs (F4). Unstaked throttling: 20/100 ms per connection, delay not drop — stay ≤ 14 per burst; connection rate limits handled by persistent connections (F1/F10). Shared ingress routing: redesigned τ, spill-over sub-experiment, per-endpoint reporting (F1). Pacing: covered by the pending-queue model and load stratification (F3). Slot boundaries: analyse (slot, index) over the whole window, same-slot as sensitivity (F5). 0-lamport transfer: confirmed (F11). Payer rotation: fine; shorten with aged blockhashes (I-7). Blockhash choice: aged blockhash bounds spill-over and carry-over (I-7, F9). Leader handover: achieved-offset classification (F6). Builder fallback/failover: block-structure covariates (F8).

---

## Ideas that would materially raise the score

**I-1. Positive controls on open-source clients, framed as method validation.** Make vanilla Agave and Firedancer the anchors with the most windows and state up front: "if we cannot recover the published reward/cost rule with ε ≈ 0 on these, our method is broken and nothing below should be believed." Judges reward a measurement project that calibrates itself.

**I-2. The "free priority" figure.** A probe with p = 0, L = 600, D = 32 KiB has P_agave ≈ 1.3·10⁶ — above almost every paying transaction. On reward/cost schedulers it should land in the first few indices of the slot; on CU-price or lamport-fee builders near the bottom or not at all. One scatter per validator (our probes' block-index percentile vs. key percentile, coloured by key) is the most convincing single exhibit you can produce, and it costs nothing extra.

**I-3. The pre-window cliff.** Send 1–2 probes per window at −0.5 s, −3 s and −5 s to a direct Agave and a direct Firedancer validator. Agave drops anything earlier than 20 slots (4 s) before its window and buffers inside it; Firedancer keeps everything until the blockhash expires. Source-backed, cheap, and it answers "pre-window buffering scope" with a step function.

**I-4. The Firedancer tie-break prediction.** Later-arrived equal transaction first, deterministically (treap "epsilon larger" + reverse iteration). State it before measuring; it is the kind of falsifiable detail that distinguishes measurement from storytelling.

**I-5. Spill-over map.** For every probe sent to a shared ingress outside the target's window: which leader, which ingress kind, how many ms later, in which slot of that leader's window. Present it as "where does a transaction sent to validator X's advertised TPU actually go?" — the brief's "path" item answered empirically.

**I-6. Minimal pairwise contrasts (Kit A′), 6 probes per window, verifiable by eye.** (i) Equal priority fee, L = 600 vs 20,000: CU price differs 33×, lamport fee equal → CU price vs lamport fee. (ii) Equal p, equal L, D = 32 KiB vs default: identical CU price and fee, cost differs ≈ 9× → reward/cost vs CU price. (iii) Equal P_agave with different p and L → reward/cost vs everything else. A judge can confirm each with two `getBlock` lookups. Keep the 10-ladder for the statistics.

**I-7. Aged blockhash.** Use a blockhash that is ≈ 120–135 slots old at send time, so probes expire 3–6 s after the target window instead of 30 s. Benefits: bounded spill-over horizon, no same-validator carry-over on Firedancer, half the payer pool, no fee spent in windows you did not intend. Cost: a few per cent more "expired" probes if the leader's bank is ahead of your view — measure in the pilot and report the trade-off.

**I-8. Two-stage adaptive design, pre-registered.** Stage 1 identifies the key per mechanism group; Stage 2 builds Kit B and Kit C pairs on that key with both probes above marginal. Say in the pre-registration that Stage 2 parameters are a deterministic function of Stage 1 results.

**I-9. Block-structure covariates per window.** Sawtooth count, run lengths, position of your probes, block fullness; use them to flag windows whose mechanism contradicts the label (F8) and to stratify Kit B by load (F3).

**I-10. Verification UX.** `itb verify --public-rpc` that prints a claim-by-claim table (validator, window, slot, signature, predicted rank, observed index, pass/fail) within the public rate limit, and an on-chain Memo of the pre-registration hash. Both are cheap and map directly onto the 25 % verifiability criterion.

**I-11. One diagram and one honesty table.** A single figure of the transaction path per ingress kind (direct / relayer / BAM node / Harmonic Remote TPU) with the hop that reorders in each, and a table "we can / cannot separate X from Y — because Z" in one line each. Judges read these first.

**I-12. Report calibrated ambition.** A short "with 10× budget and 2 more weeks we would …" section (staked connection for SWQoS contrast, entry-level ground truth, more Rakurai/FireBAM windows) shows you know the limits you chose.

---

## Appendix A — sources checked (2026-10-23)

Agave v4.3.2
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/transaction_scheduler/transaction_state_container.rs — Slab ids, `BTreeSet`, `pop_last`, lowest dropped when full
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/transaction_scheduler/transaction_priority_id.rs — derived `Ord` on (priority, id)
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/scheduler_messages.rs — `pub type TransactionId = usize;`
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/decision_maker.rs — Consume / Hold / ForwardAndHold / Forward, Alpenglow slot-clock path
- https://github.com/anza-xyz/solana-sdk/blob/master/clock/src/lib.rs — `FORWARD_TRANSACTIONS_TO_LEADER_AT_SLOT_OFFSET = 2`, `HOLD_TRANSACTIONS_SLOT_OFFSET = 20`, `MAX_PROCESSING_AGE = 150`
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/transaction_scheduler/receive_and_buffer.rs — drop-without-parsing on Forward, check-work queue, `MAX_PACKET_RECEIVES = 512`
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/banking_stage/transaction_scheduler/greedy_scheduler.rs — pass structure, conflict-to-same-thread, unschedulables re-queued, batch flush conditions
- https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/transaction_priority.rs — `reward·1_000_000/(cost+1)`
- https://github.com/anza-xyz/agave/blob/v4.3.2/runtime/src/bank/fee_distribution.rs — 50 % base-fee burn, priority fee fully deposited
- https://github.com/anza-xyz/agave/blob/v4.3.2/cost-model/src/block_cost_limits.rs — 720 / 300 / 4 bytes per CU / 60 M–100 M block units
- https://github.com/anza-xyz/agave/blob/v4.3.2/cost-model/src/cost_model.rs — requested CU limit, 32 KiB pages × heap cost, write locks incl. payer and demoted
- https://github.com/anza-xyz/agave/blob/v4.3.2/streamer/src/nonblocking/stream_throttle.rs — `MAX_UNSTAKED_TPS = 200`, 20 streams / 100 ms per connection, sleep on excess
- https://github.com/anza-xyz/agave/blob/v4.3.2/streamer/src/quic.rs — 8 per unstaked peer, 8 per IP per minute, 2000 unstaked, 500 streams/ms, 30 s idle
- https://github.com/anza-xyz/agave/blob/v4.3.2/streamer/src/nonblocking/quic.rs — `PacketBatch::Single` per stream, `incoming.ignore()` on per-IP rate limit, `too_many` close, 2 s chunk timeout
- https://github.com/anza-xyz/agave/blob/v4.3.2/programs/system/src/system_processor.rs — transfer / allocate semantics
- https://github.com/anza-xyz/agave/blob/v4.3.2/tpu-client-next/src/leader_updater.rs — `create_pinned_leader_updater` behind `dev-context-only-utils`

Jito
- https://github.com/jito-foundation/jito-solana/tree/v4.3.2-jito/core/src — `bam_manager.rs`, `bam_connection.rs`, `bam_dependencies.rs`; no `bam_scheduler.rs` under `core/src/banking_stage/`
- https://github.com/jito-foundation/jito-solana/blob/v4.3.2-jito/core/src/bam_manager.rs — clientId switch, BAM TPU config, builder-fee info
- https://github.com/jito-foundation/jito-omnidocs/blob/4cd4e24cfe38e5c0e733ca4e0828bf2453e2fd86/bam/bam-overview/index.md — routing "when their leader rotation arrives", one node per validator, execute in exact order, direct-TPU txs go through BAM
- https://github.com/jito-foundation/jito-omnidocs/blob/4cd4e24cfe38e5c0e733ca4e0828bf2453e2fd86/bam/maker-plugin/how-it-works/index.md — "~50 ms" rounds, plugin phase first, shared priority score (undefined)

Harmonic
- https://docs.harmonic.gg/concepts/scheduling-strategies — FBA 50 ms double buffer, "priority fees and tips", deterministic ties, FIFO / MREV / Custom, fba default
- https://docs.harmonic.gg/concepts/harmonic-architecture — Remote TPU forwards to the validator and all builders; block engine routes per leader window; builder failover; in-client fallback
- https://docs.harmonic.gg/concepts/streaming-mode — sequenced microbatches during the slot

Firedancer v26.10.4
- https://github.com/firedancer-io/firedancer/blob/v26.10.4/src/disco/pack/fd_pack.c — `COMPARE_WORSE`, `fd_pack_estimate_rewards_and_compute`, allocation divisor, `PENALTY_TREAP_THRESHOLD 64`, rev-iter scheduling, pending treaps persist across blocks
- https://github.com/firedancer-io/firedancer/blob/v26.10.4/src/util/tmpl/fd_treap.c — equal element inserted to the right, "epsilon larger"
- https://github.com/firedancer-io/firedancer/blob/v26.10.4/src/disco/pack/fd_pack_cost.h — 720 / 300 / 4, requested CU limit, loaded-data pages
- https://github.com/firedancer-io/firedancer/blob/v26.10.4/src/app/firedancer/config/default.toml — `[tiles.pack]` stores txs while waiting to be leader, `max_pending_transactions = 65524`, `schedule_strategy = "balanced"`; `[tiles.quic]` 10 s idle, `retry = true`

Not verified by me (flagged where used): Agave 4.3 in-slot CU pacing (research 03); BAM node behaviour for transactions arriving when no connected validator is leader; unstaked acceptance policy at BAM nodes and Harmonic Remote TPUs; whether BAM/Harmonic blocks carry a recognisable builder-fee transaction.
