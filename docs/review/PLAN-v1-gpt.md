# Adversarial review of PLAN v1

Reviewed 2026-10-23 against `docs/BOUNTY.md`, `docs/PLAN.md`, and research notes 01–03. References below use the sections and line numbers of the supplied v1. This is a design review, not a claim to have rerun its RPC observations or sent transactions. The supplied post-Alpenglow network state is the baseline; a material contradiction found in a primary source is identified explicitly below.

**Judgment:** do not start the campaign with v1. The main threats are to Design Validity (35%) and Analysis Quality (25%): an impossible probe constraint, unobserved eligibility/arrival, selection of surviving pairs, and an invalid likelihood comparison. More client labels and more engineering will not repair those problems. Verifiability (25%) should receive effort before optional protocol probes or a large passive census; Engineering receives 15%.

## Numbered findings

1. **[BLOCKER] Kit A's rejection-sampling constraint is mathematically impossible.**

   **Issue —** Its four independently ranked fee/priority keys do not exist for these transactions.

   **Why — PLAN §2.2, L72–89; §2.3, L95; §4.2, L153–156; §6, L256.** Every atom has one signature, so `total_fee = 5000 + priority_fee`. Their rankings are identical: Kendall's tau is 1 whenever there are no ties. No tuple set can satisfy the required pairwise `|tau| <= 0.2`. The generator can reject forever, and the primary analysis cannot choose between these two candidates even with infinite observations. With fixed signature count, validator reward is also an additive constant plus priority fee, so reward-only and priority-fee-only sorting are indistinguishable.

   **Concrete fix —** Collapse equivalent hypotheses before generating probes. For the primary experiment use three distinguishable economic keys: CU price, priority-fee total, and reward/cost; test send order separately. Replace global orthogonality with explicit contrasts on which those models disagree. Deliberate ties in two keys are useful controls, not a design failure. If distinguishing total charged fee from priority fee is essential, introduce a separately budgeted signature-count intervention, calculate its extra cost and verification overhead, and acknowledge the new confounds. Otherwise report the equivalence class.

2. **[BLOCKER] The design does not establish that transactions being compared were simultaneously eligible for scheduling.**

   **Issue —** A global ranking of landed probes is being interpreted as a scheduler comparator.

   **Why — PLAN §0, L15–27; §2.3, L95–103; §3, L130–134; §4.2, L152–163.** Agave prioritizes transactions currently available to a scheduling pass. An earlier low-priority transaction may already be dispatched when a higher-priority transaction arrives. A shared writable account prevents concurrent conflicting execution, but does not undo an earlier dispatch or prove that all five probes shared a queue. Conversely, pacing or an occupied worker can make a streaming priority scheduler look buffered. Firedancer pack also selects from the currently available, feasible set. Thus low global concordance need not falsify a priority comparator, and high concordance need not locate sorting inside the validator. Research note 03 already describes these queue- and lock-dependent mechanisms.

   **Concrete fix —** Make the estimand explicit: the effect of a randomized fee/cost contrast on observed inclusion and ledger order over a specified ingress path. Use narrow, contended contrast groups, independently randomized send order, and a separately validated pre-leader holding arm. Claim a scheduler key only conditionally on evidence supporting shared eligibility. Where that evidence is unavailable, report “consistent with reward/cost ordering on this path,” with alternatives. Do not promise identification of an internal comparator from every validator.

3. **[BLOCKER] The primary likelihood ratio treats dependent comparisons as independent evidence.**

   **Issue —** The proposed noisy-pair model does not specify a valid likelihood for the observed rankings.

   **Why — PLAN §2.1, L57; §4.2, L153–157.** Five contended probes create ten pair comparisons, but only one realized ordering. Those comparisons share transactions and must satisfy transitivity: there are at most `5! = 120` complete rankings, not `2^10` freely varying pair outcomes. Multiplying Bernoulli agreement probabilities produces a composite score, not the claimed likelihood ratio with a defensible threshold of 20. A window bootstrap around epsilon does not retroactively calibrate that ratio. Multiple race pairs also share the window's clock error, ingress state, and background load.

   **Concrete fix —** Use a window-level contrast score and randomization inference respecting the actual treatment assignment, or specify a normalized ranking model with a window/session dependence structure. Compare candidates only on contrasts where their predictions differ. Calibrate the entire selection procedure, including choosing the best key, on clustered simulations. Resample whole windows within the blocking structure; use session/endpoint sensitivity analyses where common conditions persist across windows. Never use the number of pair comparisons as the independent sample size.

4. **[BLOCKER] Same-slot complete-pair filtering can manufacture the ordering result.**

   **Issue —** The primary sample is selected using outcomes affected by the treatment.

   **Why — PLAN §4.1, L143–148; §4.2, L153; §3, L132.** Changing price, requested CU limit, or data limit affects admission, eviction, feasibility, and landing as well as order. Requiring both probes to land in the target window and same slot selects a nonrandom subset. Low-priority probes can disappear from the comparison; slow probes can move into the next slot. A perfect ordering among survivors can coexist with substantial treatment-dependent exclusion. The longest race gaps are especially likely to be removed by this filter.

   **Concrete fix —** Preserve the assigned cohort and publish its complete outcome funnel. Analyze inclusion in the intended window, spillover, failure, and unresolved/expired outcomes before conditional ordering. Define ordering among jointly landed probes as a conditional descriptive estimand. Report cross-slot races as outcomes, not merely discard them. Show sensitivity to missing pairs, including worst-case bounds or explicit selection scenarios. A treatment that changes landing substantially must not receive an unconditional “scheduler rule” label from survivor concordance.

5. **[BLOCKER] The atom's allowed CU range includes a known failing transaction and its instruction shape is inconsistent.**

   **Issue —** The plan has not incorporated its own verified probe results.

   **Why — PLAN §2.2, L75–88; research note 02, L63–75.** The note reports success for the exact three-ComputeBudget-plus-transfer atom at 600 CU, and failure at 450 CU. The plan nevertheless proposes `L` starting at 450 and permits omission of the data-limit instruction. Omitting that instruction changes instruction bytes, execution work, and cost alongside the intended data-limit treatment. Failed transactions may still be recorded and charged; their execution path is not a valid replacement for the intended successful probe.

   **Concrete fix —** Always emit the same three ComputeBudget instructions, including explicit 64 MiB for the high-data-limit arm. Choose a conservative lower CU limit above the measured requirement, then simulate every distinct template against the relevant active feature set before freezing it. Reject any main experiment template with non-null `err`. The 0-lamport transfer to a nonexistent destination is supported by the supplied mainnet simulation; do not invent a rent failure for it. Still validate signatures, payer balances, writable flags, and success with the actual live builder. If a fallback is needed, validate its equal account/lock/instruction shape rather than silently substituting a self-transfer.

6. **[MAJOR] The BAM cadence hypothesis is contradicted by the dated primary source already cited in the research.**

   **Issue —** BAM and Harmonic are assigned the same approximately 50 ms signature.

   **Why — PLAN §0, L23; §2.3, L96; §4.2, L160; research note 03, L39–41.** BAM's October 9 changelog states that the move to 200 ms slots tightens its auction rounds from 25 ms to **20 ms**. It also documents maintenance fallback and gradual restoration. This contradicts treating 50 ms as the current BAM expectation. Harmonic's documented FBA still uses 50 ms filling/draining buffers. Neither statement proves the live strategy of a particular window. Sources: [BAM changelog](https://bam.dev/blog/bam-changelog-sept-23-oct-9/), [Harmonic scheduling strategies](https://docs.harmonic.gg/concepts/scheduling-strategies).

   **Concrete fix —** Record this source conflict in the amended research and preregistration. Use separate BAM and Harmonic hypotheses, retain a cadence range including 20 and 50 ms, and avoid forcing an estimate toward either value. Verify availability and configuration evidence during the pilot. Treat a client label as insufficient proof of active auction mode.

7. **[MAJOR] The race-pair curve does not uniquely identify batching, and its proposed formula lacks its necessary assumptions.**

   **Issue —** A triangular overtaking curve is treated as a batch detector.

   **Why — PLAN §2.3, L96; §4.2, L158–160.** `max(0, 1 - delta/T)` requires uniformly distributed arrival phase within a fixed batch period, deterministic within-batch priority, both members admitted, no carryover, and a known arrival gap. The plan fixes three window offsets and observes send gaps. A streaming scheduler with a suitable residual wait distribution can produce the same curve. Relayer delay, pacing, backlog, and shared ingress can all contribute. A “deep buffer” also does not imply constant overtaking probability near a flush or slot end. Harmonic's filling/draining implementation additionally separates eligibility from subsequent streaming to the validator; its 50 ms cadence is not a guarantee that a transaction lands within 50 ms. [Harmonic scheduling strategies](https://docs.harmonic.gg/concepts/scheduling-strategies).

   **Concrete fix —** Randomize the start phase over an explicitly defined interval, balance both high-first and low-first races, and include equal-key controls. Predefine a small delay grid informative around both candidate cadences. Fit an observable overtaking response first; label any inferred time scale an effective reordering horizon. Require stronger phase/cadence or operator evidence before naming a batch duration. Include streaming-with-pacing and transport-buffer models among the competing explanations. AIC cannot resolve observational equivalence.

8. **[MAJOR] The pre-window and fixed-offset arms do not isolate the mechanisms claimed.**

   **Issue —** “Pre” is assumed to imply a common scheduler buffer, while the race schedule crosses multiple causal boundaries.

   **Why — PLAN §1 F2/F6; §2.3, L99–103; §4.1, L148.** At `t0 = -150 ms`, a pair with `delta = 250 ms` has its second member sent at `+100 ms`; it is not wholly pre-window. At `+60 ms`, longer races cross a 200 ms slot boundary. At `+460 ms`, a 250 ms race reaches `+710 ms`, leaving little margin before handover. Failure to forward an unstaked packet does not establish whether an upcoming leader buffered it locally. Shared ingress may instead route the early packet to the preceding leader. A planned send offset is not proof of arrival before leadership.

   **Concrete fix —** Separate a compact pre-leader holding experiment from within-slot races. Finish all pre-buffer probes before the chosen safety margin. Define intended leader, intended slot, actual leader, and boundary-relative phase separately. Use a standalone boundary/handover arm for long gaps. Evaluate pre-send landing probability over a small offset sweep per ingress kind before using that arm to support a buffering explanation. Otherwise describe it only as early submission.

9. **[MAJOR] Tie pairs cannot simultaneously identify the tie-breaker and calibrate path noise.**

   **Issue —** The same binary observation is assigned two incompatible explanatory jobs.

   **Why — PLAN §2.3, L97; §3, L130/134; §4.2, L161; §4.4, L185.** A B-before-A result can reflect receiver reordering, internal transaction-ID order, queue co-residence, or a genuine tie-break. Agave's tie comparator uses its internal ID, not a timestamp from the sender. An earlier tied transaction dispatched before the second exists will not be overtaken. A single reversal probability cannot identify a jitter distribution in milliseconds. The source establishes an ordering by priority and ID, not reverse order of the client's QUIC stream writes. [Agave priority-ID comparator](https://raw.githubusercontent.com/anza-xyz/agave/v4.3.2/core/src/banking_stage/transaction_scheduler/transaction_priority_id.rs).

   **Concrete fix —** Relabel Kit C as a descriptive equal-key order experiment. Randomize payer assignment and which labeled member is sent first; give both members the same lock if contention is intended. Use controlled receiver instrumentation on localnet to validate the transport/scheduler mapping. On mainnet, carry a range of unobserved receiver jitter through sensitivity analysis. Do not turn Kit C into a measured network noise floor or claim internal-ID order was observed.

10. **[MAJOR] Clock precision is confused with clock accuracy.**

   **Issue —** Nanosecond send logs and a handshake RTT do not validate 5–20 ms causal timing claims.

   **Why — PLAN §1 F2; §3, L130; §5, L202/231; §6, L258; §9, L311.** Slot notifications reach an RPC observer after network and processing delays. Their regression cannot by itself recover the actual leader's slot start. Handshake RTT is neither a receiver timestamp nor a stable one-way delay. An advertised ±30 ms target, and especially a ±100 ms mitigation, are too coarse to distinguish 20 ms from 50 ms boundaries using phase. Dry-run notifications can measure consistency with that observer, not independently establish arrival accuracy at the leader.

   **Concrete fix —** Log scheduled time, stream-open time, bytes queued, write completion, connection events, and notification receive time separately. Report local scheduling error independently from uncertainty in remote arrival and slot phase. Use one stable deployment location throughout the confirmatory campaign; compare locations only as a separate factor. Prefer relative-gap effects and broad offset strata where absolute phase is uncertain. Gate any millisecond cadence claim on an uncertainty analysis that can actually resolve it.

11. **[MAJOR] Transport controls do not enforce the advertised burst limit or eliminate self-throttling.**

   **Issue —** A one-connection burst is not an arrival-order guarantee, and per-window counts are not a rate limiter.

   **Why — PLAN §1 F6; §2.3, L91–97; §3, L130–133.** Ten A probes, three B starters, and two C members already make 15 sends if launched together, exceeding the stated first-burst limit of 14; zero-delay B followers can raise that further. Consecutive target windows sharing an endpoint, retries, and multiple connections can aggregate within a throttle interval. QUIC streams are independently processed; congestion, flow-control credit, loss, and receiver scheduling can change availability. A completed local write is not proof of delivery. The Agave implementation documents a 200 TPS unstaked allowance and a 100 ms throttle interval, but this does not establish identical policies at BAM/Harmonic endpoints. [Agave stream throttle](https://raw.githubusercontent.com/anza-xyz/agave/v4.3.2/streamer/src/nonblocking/stream_throttle.rs).

   **Concrete fix —** Specify an exact stream schedule and an endpoint/peer-aware limiter across windows, with conservative headroom. Use warm reused connections and bounded reconnection/backoff; record throttling and transport errors. Audit the pinned client's buffering, reconnect, retry, and send ordering behavior. Independently randomize stream order relative to treatment. Keep a compact primary group together; schedule supplementary probes in separate windows rather than perturbing it with the rest of the kit.

12. **[MAJOR] Pinning a shared TPU address does not pin an executing validator or an independent experimental unit.**

   **Issue —** Validator-specific labels conceal shared infrastructure and routing decisions.

   **Why — PLAN §1 F5; §2.1, L57–64; §3, L129–130; research note 03, L24–31.** Multiple BAM or Harmonic validators share an ingress endpoint. Pinning that socket cannot encode a guarantee that the intended validator executes the transaction. A neighboring leader using the same service can receive it, and different operators can share builder, queue, and transport conditions. Distinct operators therefore do not guarantee independent scheduler implementations. Treating spillover as a label without modeling its selection is insufficient.

   **Concrete fix —** Record the identity/vote-account mapping, endpoint, predecessor and successor leaders, and their ingress families for every attempt. Report intended-target and actual-producer results separately; do not retroactively count opportunistic spillover as a successful targeted replication. Cluster or stratify by endpoint/session where appropriate. State that remote-ingress results describe the builder-to-validator path, and avoid counting multiple consumers of one builder as independent confirmations of its policy.

13. **[MAJOR] Per-window client classification is overclaimed relative to the snapshots.**

   **Issue —** A snapshot up to 60 seconds old and one Kobe snapshot per run cannot establish an 800 ms execution mode.

   **Why — PLAN §1 F4; §2.1, L62; §3, L129; §9, L310.** Gossip is observed through another node and may lag. The notes themselves warn of maintenance, disconnects, and dynamic IDs. A stable prior 24 hours is a target-selection criterion, not proof of mode at execution. The plan says flips will be split correctly without specifying how a flip between observations is located. Client/version identity also does not reveal Harmonic strategy, BAM plugins, or Firedancer pacing.

   **Concrete fix —** Preserve nearest before/after observations and source timestamps where available. Mark mode as stable-observed, transition-ambiguous, or unknown; do not manufacture exact transition times. Apply predeclared handling of ambiguous windows. Treat operator confirmation or authenticated builder evidence as optional corroboration. Verify the bounty's minimum three documented software/fork labels independently of inferred behavioral classes.

14. **[MAJOR] The cost-model validation conflates requested scheduling cost with execution accounting.**

   **Issue —** Equality with `meta.costUnits` is not a universal oracle for the scheduling denominator.

   **Why — PLAN §1 F3/F7; §2.2, L84; §4.3, L170; §6, L255.** The plan deliberately varies requested CU/data limits while executing nearly identical work. Agave's priority function passes requested limits into its cost calculation; the cost-model API also supports actual executed work and loaded bytes, and the consumer updates accounting after execution. Consequently a test demanding requested-cost equality with returned execution metadata can reject a correct priority model or encourage an incorrect replacement. Sources: [priority calculation](https://raw.githubusercontent.com/anza-xyz/agave/v4.3.2/core/src/transaction_priority.rs), [cost model](https://raw.githubusercontent.com/anza-xyz/agave/v4.3.2/cost-model/src/cost_model.rs), [consumer accounting](https://raw.githubusercontent.com/anza-xyz/agave/v4.3.2/core/src/banking_stage/consumer.rs).

   **Concrete fix —** Store separately: serialized requested limits, reconstructed pre-scheduling cost/reward/priority, executed CU, and returned cost metadata. Validate the scheduling calculation against the exact pinned source path using integer arithmetic, rounding, saturation, and feature flags. Trace the metadata field's producer before defining a cross-check. A high-`L`, high-`D`, low-actual-work probe should explicitly demonstrate the distinction. Share recorded feature values, not an assumed universal formula, between Rust and analysis.

15. **[MAJOR] Firedancer is not adequately represented by an Agave score plus an “allocates” boolean.**

   **Issue —** The primary kit may only identify a broad reward/cost class, and optional D may not activate the intended penalty.

   **Why — PLAN §1 F8; §2.3, L105; §4.4, L182; research note 03, L40.** Pack's reward/compute comparator need not equal Agave's integer `reward/(cost+1)` ordering near ties. The supplied note describes pacing, feasibility, and penalty treaps; the proposed five-reference fresh lock does not exercise a threshold above 64 pending references. Nor does `space > 0` necessarily imply a meaningful allocation penalty. The currently accessible main-branch implementation uses an integer divisor depending on allocation, estimated cost, and block limits, which can remain 1 for small allocations. This is a diagnostic warning, not verification of the unavailable v26.10.4 source. [Firedancer pack implementation](https://raw.githubusercontent.com/firedancer-io/firedancer/main/src/disco/pack/fd_pack.c).

   **Concrete fix —** Pin and evaluate the deployed release's actual pack score and rounding before claiming a Firedancer-specific prediction. State when its ordering is indistinguishable from Agave on the chosen probes. Cut allocation D from the minimum campaign. If retained, choose a magnitude that demonstrably changes the release-specific divisor, match signatures/instructions/locks, and verify where both transactions fail or succeed. Execution-failing allocation probes test treatment of such packets; they do not establish production ordering of successful allocating transactions. Do not claim to test penalty treaps or “strongest alignment” with this kit.

16. **[MAJOR] Blockhash choice, signature uniqueness, and retry policy are missing experimental controls.**

   **Issue —** Transaction validity and duplicate suppression can become hidden treatments.

   **Why — PLAN §2.1, L67; §3, L131; §5.1, L233.** Generating a design in advance is different from signing it with a fresh blockhash. Different hash ages across roles affect validity and potentially retries. The same payer, instructions, lock, and blockhash produce the same signed transaction; “unique signatures” needs a construction, not an assertion. Client reconnects or RPC retries can resubmit packets and shift exposure across a handover. Wall-clock estimates of approximately 30 seconds do not define expiration.

   **Concrete fix —** Use one sufficiently recent blockhash and validity context per comparison group, fetched before its send-critical path, with a minimum block-height validity margin. Record the hash, context slot, `lastValidBlockHeight`, serialized bytes, and all attempts. Give each experiment fresh lock identities while preserving within-group conflicts; verify uniqueness before sending. Freeze randomized templates before the run, then append the immutable signed realization. Explicitly disable application retries for the primary experiment or define them as a separate arm; record any library retransmission behavior.

17. **[MAJOR] The payer pool can introduce treatment-correlated availability, balance, and lock effects.**

   **Issue —** Distinct payers within a window solve only one part of the payer problem.

   **Why — PLAN §2.2, L81; §2.4, L118; §3, L131; §5.1, L238.** Payers are writable. Recycling by “previous transaction resolved” makes availability depend on prior landing outcomes; unresolved probes can occupy a 40-account pool across several windows. Fee-heavy roles can deplete certain payers faster. Account funding/refills/sweeps can overlap probes. Rent-exempt principal must remain available alongside fees, and account/address-specific deterministic tie-breaks remain possible even with distinct payers.

   **Concrete fix —** Randomly and evenly assign payer identities to roles independently of fee treatments. Fund enough fee headroom per payer, preflight balances outside the critical path, and log the assignment and state. Keep unresolved transactions isolated until adjudicated; skip a whole planned group if the pool cannot satisfy its rules. Do not refill during an active group. Measure the pool's occupancy during the pilot before fixing its size. Sweep only after all outstanding signatures are reconciled, budgeting sweep fees.

18. **[MAJOR] Sixteen windows cannot support the advertised resolution across keys, timing strata, and delays.**

   **Issue —** Breadth consumes the independent replication needed for the main claims.

   **Why — PLAN §2.1, L59–65; §2.3, L96/99; §4.4, L189.** Sixteen windows yield roughly five or six windows per timing stratum. Three races per window provide 48 races over ten delay levels: only 4.8 per delay before splitting timing, load, landing, or mode. These are still clustered within 16 windows. As an illustrative independent-window calculation, 16 successes out of 16 give a one-sided 95% lower success bound of `0.05^(1/16) = 0.829`; six of six give 0.607. Even a zero-failure threshold above 90% needs at least 29 independent Bernoulli units at this confidence level, before multiplicity. These calculations are not a substitute for design-specific power, but expose the optimistic precision implied by the plan.

   **Concrete fix —** Fund repetitions before extra client labels. Start with the bounty minimum of six validators, with backup identities and at least three documented client/fork labels. Reduce the number of primary factors and delay levels. Let pilot-based landing and variance determine attempted windows needed for the prespecified precision. Set a feasible inconclusive outcome if the cap cannot buy that precision; do not increase pair counts and call it power.

19. **[MAJOR] The null hypothesis and multiplicity correction do not match the scientific claims.**

   **Issue —** Rejecting uniformly random ledger order does not identify a fee rule, and correcting only across validators misses selection within each validator.

   **Why — PLAN §3, L134; §4.2, L153–163.** FIFO is a systematic rule; priority queues can look FIFO when arrivals are separated. Neither is a uniform random permutation of every observed comparison. Choosing among keys, timing strata, contention arms, scope models, client pools, and optional modules generates additional opportunities for a favorable result. P-values computed after selecting the best key must include that selection. Feature-correlated admission also threatens a naive permutation of only surviving transactions.

   **Concrete fix —** Define a small confirmatory family, such as the randomized economic contrast effect per target, and apply Holm or a max-statistic calibration over the complete family. Recreate the actual assignment mechanism in randomization tests; do not freely shuffle dependent pair rows. Treat cadence, tie-break, passive plots, and post-hoc pools as exploratory unless separately powered and registered. Distinguish “no detectable fee effect,” “send-order association,” and “insufficient information”; none means the validator has no scheduling rule.

20. **[MAJOR] The 10% error threshold, LR 20, and AIC winner overstate certainty.**

   **Issue —** Hard labels are based on point estimates and comparisons against a potentially incomplete model set.

   **Why — PLAN §0, L26–28; §4.2, L155–160.** A point estimate `epsilon <= 0.10` does not establish strictness below 10%. Ordinary bootstrap intervals can degenerate at zero observed errors in a small sample. A best candidate can be wrong when every candidate misses pacing or admission. AIC is not a posterior probability that a scheduler is a batch auction, and comparing boundary-valued models with sparse, clustered binary data requires care. The proposed multifeature logistic robustness check also has exact collinearity between total and priority fee and cannot repair causal ambiguity.

   **Concrete fix —** Report interval estimates and model disagreement on discriminating contrasts. If using “at least 90% agreement,” require an appropriate one-sided confidence bound rather than a point estimate. Permit a set of compatible keys, not just one winner. Use cluster-aware held-out predictive comparisons where sample size permits, with an explicit misspecified/unknown outcome. State whether epsilon describes this experiment's ledger outcomes or internal scheduler violations; only the former is directly observable.

21. **[MAJOR] The simulator risks proving only that the analysis recognizes its own simplified assumptions.**

   **Issue —** A clean confusion matrix is presented as proof of mainnet identifiability.

   **Why — PLAN §4.4, L177–191; §6, L262.** An Agave model reduced to a pass interval and reverse-arrival tie omits readiness, in-flight locks, worker queues, admission filters, and pacing. A treap model omits feasible packing and downstream execution. Jitter cannot be calibrated from tie reversals, and a closed-source builder cannot be made known by naming a model after it. The ordering of phases is also inconsistent: P1 promises power before any live data while the proposed jitter calibration requires live tie pairs.

   **Concrete fix —** Use simulation for operating characteristics under declared scenarios, not implementation truth. Include adversarial alternatives that can imitate the headline result: streaming plus periodic pacing, FIFO plus reordered ingress, selective dropping, phase error, mode switches, and incomplete observation. The expected answer for observationally equivalent scenarios must be “unidentified.” In P1 use broad parameter ranges; update nuisance ranges from a separately labeled pilot, then freeze the confirmatory design. Verify key source-level behavior with small instrumented local examples rather than building a full validator simulator.

22. **[MAJOR] Preregistration is named but not specified tightly enough to prevent outcome-driven decisions.**

   **Issue —** Several major researcher choices remain open after pilot observation or campaign failures.

   **Why — PLAN §2.1, L62–67; §2.3, L104; §4; §7, L277–279.** A seed and committed design do not define exclusions, replacements, stopping, pooling, missing-data handling, or how an estimate becomes a claim. A local Git timestamp is not an independent proof of prior commitment. Selecting optional modules or targets after seeing favorable orderings changes the testing family. Pilot transactions are part of the spend even if excluded from confirmatory inference.

   **Concrete fix —** Freeze: primary estimands and equivalence classes; target/backup and eligibility rules; template values and exact assignment schedule; endpoint/connection/retry and blockhash policy; sample size or fixed budget/time stopping; primary outcomes and inclusion rules; missing, failed, cross-slot, and ambiguous-mode handling; inference and multiplicity; strictness thresholds; pooling criteria; simulation scenarios; and the report's permitted claim language. Publish or externally timestamp the hash before confirmatory sends. Label pilot data separately; retain and report it. Adapt only using prespecified feasibility rules, not favorable ordering effects.

23. **[MAJOR] The passive census is vastly larger than the data-volume and collection estimates.**

   **Issue —** “All blocks of the target validators” is not a roughly 1,000-block task.

   **Why — PLAN §4.3, L167; §5, L220–224; §7 P4.** Research note 01 lists approximately 12,400, 15,800, and 16,900 leader slots per epoch for just three large targets. Those alone sum to about 45,100 slots per approximately daily epoch. Three campaign days can therefore mean around 135,300 target slots before the other validators, skips, and the additional 300-block-per-client sample. At the plan's 0.5–3 MB per full block, that is roughly 68–406 GB for these three targets alone. An ideal 10 requests/second still needs about 3.8 hours merely to issue one request per slot; credits, payload bandwidth, retries, and analysis storage add constraints.

   **Concrete fix —** Cut the census. Archive all blocks containing probes, the necessary neighboring slots for attribution, and a small preregistered time/load-matched passive sample. Separate RPC request, credit, bandwidth, storage, and archive-retention budgets. Use cached raw assets for ordinary reproduction; make additional passive collection explicitly optional.

24. **[MAJOR] Passive sawtooth and bundle filtering are not independent ground truth.**

   **Issue —** Supplementary plots are assigned causal interpretations they cannot support.

   **Why — PLAN §3, L132; §4.3, L168–175.** Descending-run boundaries can arise from arrival bursts, worker completion, tied scores, heterogeneous programs, and changing admission pressure. They do not timestamp auctions. Tip transfers do not identify every transaction in every Jito bundle, and a tip-paying transaction is not a complete bundle-membership oracle. Excluding guessed bundle rows can alter the reference distribution. Passive cost reconstruction across legacy/v0/v1 additionally needs resolved addresses, signature/precompile costs, defaults, active features, and exact fee semantics. A footrule result is incomparable with prior work unless normalization, ties, filtering, and population match.

   **Concrete fix —** Call sawtooth segmentation descriptive and bundle labels heuristic; show sensitivity with and without those exclusions. Do not claim another estimate of batch count from runs. Validate a bounded passive parser fixture set, and omit unsupported rows explicitly. Entry archives can establish ledger entry groupings for retrieved slots, but do not expose queue arrival or the number of scheduler passes. Treat that as a targeted structural check, not full scheduler ground truth.

25. **[MAJOR] The budget arithmetic is plausible, but the hard cap's lifecycle and reconciliation rules are incomplete.**

   **Issue —** The safety layers can disagree and expiration alone does not prove an unobserved transaction was free.

   **Why — PLAN §2.4; §5.1, L232–239; §7 P3.** `224 * 18 * 6800 = 27,417,600` lamports is correct, but the average priority fee is not established by a feasible design generator. Pilot, funding, sweeps, replacements, and optional probes must share one cumulative cap, not independent run allowances. Releasing a reservation after expiry is unsafe if the transaction landed earlier but its status was missed. If master and payers are all included in the summed balance, transfers between them—including rent-exempt principal—cancel; subtracting `rent_moved` again can hide spend. A 0.1 SOL compiled maximum and 0.09 SOL wallet are not physical enforcement of the 0.05 SOL requirement.

   **Concrete fix —** Price the finalized finite design exactly and cap the entire campaign, including setup and cleanup. Persist signed-transaction identity with its reservation; make retry resolution idempotent. Unknown historical outcomes remain charged conservatively until reconciled. Distinguish expiry from proof of non-inclusion. Reconcile total balances using explicit external deposits/withdrawals and all owned accounts, with no double rent adjustment. Reserve cleanup fees and payer headroom before starting. Property tests should target these specific cap failure modes. The 0.09 SOL funding request is reasonable only as separate fee allowance plus recoverable working capital, not as the promised fee cap.

26. **[MAJOR] The 13-day schedule prioritizes breadth and infrastructure before the hardest feasibility result.**

   **Issue —** Reliable mainnet ingress and useful experimental contrasts are discovered too late.

   **Why — PLAN §5; §6; §7; §8.** P1–P2 attempt a multi-crate Rust system, a cost model, a crash-safe budget ledger, a scheduler simulator, source-pinned localnet, devnet, and a timing engine in four days. The pilot then gets one day across only four validators before a broad 12–14-target campaign. The report, verifier, site, and substantial analysis arrive together near the deadline. Multiple independent reproductions and maintainer waits add real elapsed time. No measured engineering velocity or fallback schedule supports this scope.

   **Concrete fix —** Move the smallest authorized capped mainnet pilot onto the critical path immediately after sender, collector, and cap validation. Establish at least one usable endpoint in every required family before freezing coverage. Keep one Rust package with internal modules and one Python analysis package unless a real boundary requires more. Cut allocation/format/RPC-path modules first, then the passive census, extra client labels, full scheduler emulation, and elaborate UI. Preserve the cap, raw logs, six-validator/three-client requirement, honest inference, and offline reproduction. A concrete revised calendar appears below.

27. **[MAJOR] Default reproduction depends on mutable network state and combines two different promises.**

   **Issue —** A historical result cannot be byte-identically reproduced by first performing a new live dry-run.

   **Why — PLAN §5.1, L246–247; §6, L263–264; §10, L326.** Current gossip, endpoints, block availability, provider limits, and an Alpenglow check can change after submission. New dry-run timings are necessarily different. A ten-minute network exercise adds failure modes before a judge reaches the saved evidence. “Byte-identical derived data” also needs a defined scope: timestamps, compression metadata, plot metadata, and dependency differences can change bytes without changing the result.

   **Concrete fix —** Make the default Compose command replay the frozen dataset, validate hashes/schema, recompute numerical claims, and produce the report without keys or live dependencies. Offer separate explicit commands for chain verification, live dry-run, and capped sending. Pin dependencies and seeds. Specify which machine-readable outputs must be byte-identical and normalize nonsemantic metadata; validate figures by their underlying data unless bitwise plotting reproducibility is intentionally supported.

28. **[MAJOR] The verifier proves less than the central claim suggests.**

   **Issue —** Checking a signature at a transaction index verifies placement, not the experimental design or inference.

   **Why — PLAN §0, L30; §5, L211–224; §10, L329.** A judge must also establish that the transaction was the claimed probe, used the claimed fee/limits/locks, was attributed to the right producer, and entered the metric under the declared rules. On-chain data cannot authenticate local send timestamps, the absence of retries, or receiver arrival. A SHA-256 manifest protects asset integrity but does not prove when a design or send log was created.

   **Concrete fix —** Verify signatures against serialized messages; decode instructions and account roles; recompute each candidate prediction; check fee, success/failure, slot/block identity, actual leader, pair membership, and cohort exclusions; then recompute the reported statistic. Preserve the preregistration commit/hash, raw attempts, collection timestamps, RPC parameters, and feature/client snapshots. Explicitly separate chain-verifiable facts from locally recorded facts and unobserved quantities. Add a tiny judge-facing example that walks through this chain end to end.

29. **[MAJOR] Outcome collection lacks a sufficiently explicit unknown state and completeness rule.**

   **Issue —** “Not landed (expired)” risks becoming a catch-all for collector failures and missed spillover.

   **Why — PLAN §4.1, L143–146; §5, L206/211–224; §9, L312.** A missing signature response, unavailable block, HTTP 429, skipped slot, and canonical non-inclusion are different facts. Collecting only the four intended slots cannot discover all remote-ingress spillover or delayed retries. Polling stops and provider history limits can create outcome-dependent missingness. A slot alone should not silently stand in for the identity of a particular collected block when the supplied research discusses competing banks.

   **Concrete fix —** Define statuses for pending, canonical landed success, canonical landed failure, spillover, expired with adequate reconciliation, and unresolved due to observation failure. Record blockhash/parent information and bank identity where exposed. Collect out-of-window landing slots discovered by signature status; retain unsuccessful RPC responses and retry/backoff metadata. Use last-valid block height and the chosen commitment consistently. Unknowns must remain visible in the report and conservatively reserved in the spend ledger.

30. **[MAJOR] Legacy zero-value probes do not establish a universal rule for all transactions in a validator's blocks.**

   **Issue —** The opening promise is broader than the population actually intervened on.

   **Why — PLAN §0, L11–32; §2.2; §2.3, L107; §3, L132.** The probes are tiny, unstaked, legacy System transactions with fresh locks, no tips, almost no execution work, and deliberately manipulated requested limits. The notes say a large share of production transactions are v1; arbitrary programs, bundles, allocation, hot accounts, and builder plugins can follow different paths. Background traffic is not merely random noise when it changes feasibility and queue state. Low-cost probes can receive unusually favorable priority relative to normal application transactions.

   **Concrete fix —** Scope the headline to untipped standalone probes of the specified shape over the observed path and dates. Describe application transactions and v1 as external-validity limits. Report load descriptively and avoid treating realized block load as an exogenous adjustment variable. A second transaction family is useful only after primary identification and replication are secure; it is not necessary to promise a universal rule to satisfy the bounty.

31. **[MINOR] Target counts and claimed coverage are internally inconsistent.**

   **Issue —** The numerical ambition is not a precise sampling plan.

   **Why — PLAN §0, L11; §2.1, L59–61; §2.4, L115.** Five families with two validators plus three families with one or two gives 13–16 validators, not 12–14. Sampling a few high-stake operators from families whose aggregate stake approaches the whole network is not measurement of 99.9% of stake. Stable, high-stake selection also favors reachable incumbents and does not justify population-level claims about every deployment of a fork.

   **Concrete fix —** Publish an exact minimum target table, backups, and selection rules. Report measured-validator stake separately from represented-client-family stake. Keep inference per measured validator/path; any family-wide generalization needs replication and explicit assumptions.

32. **[MINOR] Key-volume permissions contradict the funding workflow.**

   **Issue —** The payer generator cannot write into the specified read-only key mount.

   **Why — PLAN §5.1, L240–243; §10, L327.** The plan puts the master on a read-only volume and generates the payer pool into that same volume at fund time. Sweep operations also require a recoverable pool and outstanding-attempt ledger after a restart.

   **Concrete fix —** Give an explicit initialization command a narrowly scoped writable payer directory, then mount keys read-only for measurement. Keep the master secret and generated pool paths unambiguous, persist the ledger separately, and document recovery/sweep behavior. No additional service or secret-management platform is needed.

33. **[MINOR] Several test assertions validate the wrong contract.**

   **Issue —** The test plan can fail correct behavior or give false reassurance.

   **Why — PLAN §5, L205; §5.1, L231; §6, L255–263.** A dry-run that performs QUIC handshakes sends network bytes, so a socket assertion of zero bytes contradicts that behavior. A localnet build with a release tag does not automatically reproduce mainnet's active feature set. Raw local timing precision cannot validate remote arrival accuracy. The impossible orthogonality assertion and requested-cost/actual-cost equality also need removal, as above.

   **Concrete fix —** Assert zero transaction payload submission in dry-run while allowing documented handshake/RPC traffic. Keep live authorization at the send boundary. Validate the exact mainnet feature assumptions used by probe simulation, and limit localnet claims to what was exercised. Prefer a few meaningful fixtures and failure-path checks for cap, attribution, parser, and inference over broad coverage badges or tests that restate the implementation.

## Ideas that would materially raise the score

1. **Replace the random ladder with a small, interpretable contrast library.** This directly improves Design Validity and makes the evidence inspectable. Keep one signature, identical instruction structure, two writable accounts, and equal message lengths. Let `F = ceil(L*p/10^6)` and `C0` be the release-verified constant part of cost, so `P = floor((2500+F)*10^6/(C0+L+8*ceil(D/32768)+1))` for this atom. The following are candidate templates to validate, not claimed live observations:

   | Contrast | Member A | Member B | Discriminating prediction |
   |---|---|---|---|
   | Price versus fee | `L=1000, p=2,000,000, D=32 KiB`, so `F=2000` | `L=4000, p=750,000, D=32 KiB`, so `F=3000` | CU price favors A; fee total favors B; the supplied Agave cost model favors A |
   | Price versus reward/cost | Same A but `D=64 MiB` | Same B as above | CU price still favors A; fee total and reward/cost favor B |
   | Pure requested-data contrast | Equal `L=1000, p=2,000,000`, `D=32 KiB` | Equal `L` and `p`, `D=64 MiB` | Price and fee tie; reward/cost favors A |

   The first two contrasts give the three economic candidates different joint prediction patterns; the third isolates the requested-data lever. Reverse send order equally often and swap payer identities independently. Use a shared lock within each pair. Include a smaller matched uncontended arm to show how ledger-order interpretation changes. Do not put every arm into every burst. Preserve the distinction between a cost-dependent inclusion effect and conditional ordering among survivors.

2. **Publish an identifiability table before publishing a winner.** For each pair of mechanisms, state the intervention that separates them and what observation would refute each. Examples: fixed-signature priority fee versus total charged fee is unidentifiable; source comparator versus an upstream identical comparator is unidentifiable from final blocks alone; FIFO versus a priority scheduler under nonoverlapping arrivals is unidentifiable; 20/50 ms batching versus paced streaming requires more than a smooth overtaking curve. This is unusually strong evidence of scientific restraint under the 35%/25% criteria. Include a “compatible mechanisms” column in the results table.

3. **Make one compact mainnet result the pilot's acceptance test.** Before infrastructure expands, produce a complete exhibit: preregistered template, signed bytes, actual send attempts, intended and actual leader, decoded block placement, all missing/failed members, and a correctly scoped effect estimate. Repeat it through at least one endpoint from each planned family. Fix ingress, parsing, and payer validity before spending on breadth. A failed path is itself a useful measured result, but it does not replace the required usable multi-validator coverage.

4. **Use the budget for independent windows.** A feasible starting allocation is six validators across at least three documented families; if reachable, two Agave baselines, two Firedancer validators, one BAM, and one Harmonic endpoint provide four useful behavioral contexts. The singleton remote-builder results remain per-target findings. Keep backups within the required labels. As an illustration, `6 * 40 * 12 * 6800 = 19,584,000` lamports buys 240 attempted windows and 2,880 probes at the plan's assumed mean fee, leaving room for a pilot, setup/cleanup, replacements, and additional repetitions. This is an allocation example, not a power guarantee: price the actual templates, account for losses, and set final N by the frozen precision analysis. Separate key and timing windows; use a few useful delays rather than ten sparsely populated cells.

5. **Adopt a deadline-driven minimum campaign and explicit cut order.**

   | Dates | Concrete result required |
   |---|---|
   | Oct 24–25 | One package builds/sends/collects; cap survives restart; valid templates; local end-to-end and mainnet dry-run |
   | Oct 26 | Small authorized mainnet pilot; endpoint reachability, landing, payer pool, and block parsing demonstrated |
   | Oct 27 | Freeze primary design, targets/backups, inference, exact budget, and exclusions; publish its hash |
   | Oct 28–Nov 1 | Campaign over several sessions/days; reconcile and archive data continuously; reserve replacement time |
   | Nov 2–3 | Primary analysis and claim verifier; one-page results table; limitations and failed attempts |
   | Nov 4 | Clean offline reproduction, sampled chain verification, independent audit, report freeze |
   | Nov 5 | Submit before the internal noon-UTC target; retain deadline margin |

   Cut first: allocation D, RPC-path E, and format F; then exhaustive passive collection; then additional client labels beyond compliant coverage; then entry-archive integration and elaborate interactive UI. Avoid building a full protocol simulator or separate crate for every noun. Do not cut the spend cap, primary repetitions, recorded failures, raw transaction evidence, or one-command reproduction. External approvals and credentials need explicit readiness dates; a delayed pilot should trigger the preset scope reduction.

6. **Give judges a claim ledger instead of asking them to trust a report generator.** Each headline should link to its preregistered contrast, included/excluded attempt counts, exact signature/slot evidence, decoded transaction features, point estimate and interval, plausible alternatives, and a single reproduce command. Provide three human-readable worked examples: a key-discriminating pair, a boundary/spillover failure, and a genuinely inconclusive result. Make an offline result view immediately usable; a thin static interactive filter is valuable only after its underlying evidence is correct.

7. **Make missingness and contradictions first-class results.** Show a funnel per target/path: planned groups, attempted groups, transport errors, any landing, joint landing, same-slot landing, failures, spillover, and unresolved outcomes. Add a compact sensitivity panel showing how the conclusion changes with timing uncertainty, selection assumptions, and ambiguous builder mode. Report the BAM cadence source conflict and any runtime disagreement instead of smoothing them away. Supported null or non-identification results can score well under the bounty's explicit analysis criterion.

8. **Predefine the language of the final conclusions.** A defensible conclusion would read: “For these untipped legacy probes sent through endpoint E on dates D, randomized contrast A favored lower requested cost in X of Y evaluable windows; inclusion differed by Z; the interval is [...]. CU-price-only sorting is inconsistent with contrast B, while reward/cost sorting at the ingress or validator remains compatible. The observed overtaking horizon does not uniquely identify an auction period.” That answers the bounty with an auditable measurement and a clear boundary on what was learned. It is substantially stronger than a client-wide badge saying “priority scheduler, 93% strict.”
