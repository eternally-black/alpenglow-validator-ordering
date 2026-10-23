# Gate 1 independent code and measurement review

**Verdict: DO NOT pass the live-spend or confirmatory-analysis gate yet.** The reservation release protocol can undercount real fees; the analysis can admit ineligible windows and make incorrect rule decisions. These are reachable correctness defects, not requests for additional polish.

Reviewed on 2026-10-23 against repository HEAD `0b5789369787affa34d9c27a98fba32c65c1017b`, plus the working tree. During the review another process changed `stats.py`, `oc.py`, both Python test modules and `PREREGISTRATION.md`. This report includes the additions of `conflict_weight`, `diagnosis`, and the revised OC verdict accounting observed at approximately 20:55 Europe/Kyiv. References below use that working-tree version. No implementation changes were made by this reviewer.

The audit covered all Rust source modules, all Python analysis modules, the four requested specification documents, relevant tests and Compose configuration. Static traces were supplemented with read-only, in-memory counterexamples and the existing dry-run/localnet artifacts. No live transaction was sent. No new test files or fixtures were created. Rust builds and file-producing simulation/integration tests were not run because the instruction permits writing only this report. Existing artifacts are evidence of their contents, not a claim that this reviewer independently reproduced their original runs.

Verification performed:

- `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider analysis/tests/test_stats.py -q`: **10 passed** after the concurrent edits (9 passed before them). Python 3.13.4, NumPy 2.5.4, SciPy 1.18.1, pandas 3.1.0. Bytecode and pytest cache writes were disabled.
- In-memory calls reproduced the pooled-order error, missing-evidence eligibility, spurious mixture diagnosis, verifier acceptance of invalid claims, and simulation of post-window arrivals as target landings. Their inputs and outputs are specified in the findings.
- Read the pinned upstream Agave v4.3.2 cost model, priority calculation, compute-budget fee calculation and fee distribution. The named library templates have the correct arithmetic; see the preservation notes at the end. The cited Firedancer tag could not be fetched through the web tool, so no independent Firedancer-source verification is claimed.

## Findings, most severe first

### 1. [BLOCKER] Expiry releases use a signature lookup made before the expiry barrier

**Locations:** `crates/itb/src/collect.rs:86-98,171-174`; `crates/itb/src/setup.rs:50-62`; `crates/itb/src/rpc.rs:265-273`; `crates/itb/src/ledger.rs:135-147`.

**Failure:** Let a transaction's last valid height be H. `getSignatureStatuses` returns null while the cluster is at H−1. The transaction lands at H while the following height request is delayed. `getBlockHeight(finalized)` then returns H+1. Both collectors release the reservation, although the transaction paid its fee. For example, with a 50,000,000-lamport cap and 49,994,000 already spent, falsely releasing a 6,000-lamport transaction permits another 6,000-lamport send: actual spend becomes 50,006,000. A load-balanced endpoint returning a stale status response makes the problem easier to trigger. The wrapper also discards the status response's context.

This violates the stated requirement that the signature **still** be absent after finalized expiry. A null before the barrier proves neither non-inclusion nor that the transaction cannot subsequently land. Solana's [status RPC returns a context and per-signature confirmation information](https://solana.com/docs/rpc/http/getsignaturestatuses); neither is used to establish this ordering.

**Fix:** Observe a finalized expiry barrier first, then obtain fresh history-capable signature evidence from a backend demonstrably caught up with that barrier. Preserve context and the evidence in the journal. If consistent history/non-inclusion cannot be established, retain the reservation. Use one shared resolution implementation for setup and probes. A deterministic delayed-response test must cover the null → landing → finalized-height sequence.

### 2. [BLOCKER] Rule decisions pool three dependent order contrasts instead of applying the six preregistered predictions

**Locations:** `analysis/itb_analysis/stats.py:100-125,190-208`; `analysis/tests/test_stats.py:33-60`; `docs/PREREGISTRATION.md:30,50-60`.

**Failure:** Although `order_by_contrast` is calculated, `rule_status` consumes only a pooled `order`. Give C1, C2 and C3 order counts 40/40, 0/40 and 20/40, with label counts 20/40 each. Both C1 and C2 contradict an order tie, so the random rule must be rejected. The implementation instead calls the pooled 60/120 order tie confirmed and returns random `UNDETERMINED`.

Pooling also manufactures precision: with perfectly correlated order outcomes across the three contrasts in each of 40 windows, 26/40 yields an adjusted interval `[0.387402, 0.860156]`, but the duplicated 78/120 yields `[0.500880, 0.781054]` and confirms an order direction. There were 40 independent windows, not 120. The existing unit tests explicitly encode this pooled API, so passing them does not establish preregistration compliance.

**Fix:** Evaluate L_C1, L_C2, L_C3, O_C1, O_C2 and O_C3 separately for every rule. Reject on any contradicted prediction; apply SUPPORTED/CONFIRMED to all required predictions. Keep any pooled estimate descriptive or use a separately specified window-cluster method. Update the tests to include cancellation and perfectly correlated contrasts.

### 3. [BLOCKER] The new mixture diagnostic identifies an economic key in label-blind transport noise

**Locations:** `analysis/itb_analysis/stats.py:219-256`; `docs/PREREGISTRATION.md:67-77`.

**Failure reproduced:** Construct 80 complete windows per contrast with 40 x-first and 40 y-first assignments. In each assignment group, 26 obey FIFO and 14 reverse it. Thus the mechanism is label-blind: every label rate is 0.5 and every order rate is 0.65. The current code returns:

```text
economic rules: all REJECTED; fifo: SUPPORTED
diagnosis: mixed:fifo+reward_cost; key_weight: 0.35
cu_price conflict:    28/80,  interval [0.192790, 0.534136]
lamport_fee conflict: 28/80,  interval [0.192790, 0.534136]
reward_cost conflict: 42/120, interval [0.218946, 0.499120]
```

Reward/cost wins solely because it has three directional contrasts and consequently a larger pooled denominator. A late-sent member winning is not evidence that its economic key caused it to win: network reordering and random execution can do the same. The 0.2 threshold assumes a noise ceiling that has neither been measured nor derived. This counterexample addresses the diagnostic's logic, irrespective of whether the usual stopping rule supplies this much data in a particular campaign.

**Fix:** Do not label this quantity an identified mixture weight or name an economic component from it. Report descriptive overtaking probabilities. Identifying a component requires a model/control that distinguishes key-dependent reversal from label-blind reversal, with per-window uncertainty and a preregistered comparison. A candidate already rejected by the economic contrasts cannot be reintroduced merely by taking the largest lower bound.

### 4. [BLOCKER] Eligibility fails open when required evidence is missing

**Locations:** `analysis/itb_analysis/outcomes.py:52-68,77-95`; `crates/itb/src/run.rs:627-632`; `docs/PREREGISTRATION.md:31-36`.

**Failure reproduced:** A post-upgrade window with two probe records and `sent_ok=2`, but no gossip snapshots and no `produced_slots`, becomes `mode=stable_one_sided`, `target_produced=True`, `evaluable=True`. A single snapshot is also accepted, although §2 requires agreement before and after the window. A `getBlocks` error becomes missing `produced_slots`, hence positive evidence of production. Missing/NaN values in that column also default to true. Finally, the planned count comes from the probes successfully logged, not the frozen plan: six logged/sent probes from an intended eight can satisfy `all_sent`.

**Fix:** Join each attempt to the frozen plan and require its exact member set. Require two valid bracketing snapshots agreeing on the specified fields, and affirmative block-production evidence. Missing evidence is unknown/ineligible, with explicit funnel reasons. Synthetic fixtures should supply their own evidence instead of weakening live-data eligibility globally.

### 5. [MAJOR] Payer leases are lost on restart and are released for unresolved transactions

**Locations:** `crates/itb/src/run.rs:102-137,228-239,654-688`; `crates/itb/src/ledger.rs:67-75,151-155`.

**Failure:** Send from payer P, then terminate the process before collection. The restarted process constructs an empty `busy` set and can use P immediately even while the earlier transaction remains valid and queued. Two concurrent invocations sharing the same ledger likewise have separate payer pools. Within one invocation, `collect::resolve` can return `Unresolved`, or a provisional landed outcome without a block; line 688 nevertheless releases every payer. The ledger conservatively retains the fee but does not retain payer ownership. Consequently the new probes acquire unintended shared write locks with earlier probes, violating PLAN §2.2 and potentially changing inclusion and order.

**Fix:** Persist leases keyed by payer pubkey and attempt/signature, restore them before allocation, and coordinate invocations through the same campaign store or an exclusive campaign lock. Release a lease only for a verified terminal state. An unknown outcome must remain leased until reconciled; elapsed collection timeout alone is insufficient.

### 6. [MAJOR] Distinct payer indices do not provide distinct or independently randomised payer identities

**Locations:** `crates/itb/src/keys.rs:32-43`; `crates/itb/src/run.rs:110-129,234-238,496-500`; `crates/itb/src/design.rs:140-150`; `docs/PLAN.md:78-83,101`.

**Failure:** Copy the same keypair into two `payer-*.json` files: both load successfully, and two different indices can be assigned to one window. The transactions now share a payer despite the allocator's uniqueness test. Even with distinct keys, allocation is deterministic rotation, not random assignment. With eight-member K windows and the 24-payer pool, first members consistently use one parity of payer indices and second members the other; shuffling pair order does not break this association. Payer-specific balance, account history or processing effects can masquerade as send-order effects.

**Fix:** Reject duplicate pubkeys, including inappropriate overlap with the setup/master role. Independently shuffle the selected distinct payers using a recorded, reproducible assignment seed before mapping them to members. Validate independence from both label and send position, not just absence of duplicate vector indices.

### 7. [MAJOR] Attempt journalling is too late to prevent plan reuse or preserve crash evidence

**Locations:** `crates/itb/src/run.rs:180-220,368-378,485-488,614,646-651,685-688`; `crates/itb/src/store.rs:16-18,55-60,68-72`.

**Failure:** Crash after transmitting a window but before appending progress at line 685. On restart, the same `(target, seq)` plan is eligible again, with new locks/signatures/run identity, so it becomes another paid observation. A collection error has the same effect because the task error is merely logged. Sends are held in memory until all phases and the three-second production wait finish; slot events are saved only at run end. These can be lost even after transactions were sent. `flush()` does not make the JSONL journal power-loss durable. Two processes can also generate the same second-resolution run ID and append into the same directory.

**Fix:** Claim a unique campaign/design/target/sequence attempt durably before any send, with explicit prepared/sending/resolving/terminal states and resumable reconciliation. Persist individual send events immediately. Give runs collision-resistant IDs and refuse existing directories. Fsync critical journal transitions or put them in the same transactional store as reservations. Surface incomplete attempts in the funnel and in the process exit status instead of silently treating the invocation as successful.

### 8. [MAJOR] A normal CLI dry run consumes the live campaign's plans

**Locations:** `crates/itb/src/main.rs:120-123`; `crates/itb/src/run.rs:180-220,685-687`; `docker-compose.yml:46-47`.

**Failure:** Run `itb run --max-windows 10` with default paths, then run the same command with `--live` and the required cap/key options. Dry-run attempts were appended to `state/progress.jsonl`; `load_progress` ignores the `live` field and removes them from the live design. A full dry run can cause the live run to say nothing remains. Compose happens to override the dry-run progress path, but the binary's documented safe default does not.

**Fix:** Separate dry/live progress namespaces by default and validate campaign mode/design identity when loading progress. Dry-run records must never advance live stopping counters or consume confirmatory assignments.

### 9. [MAJOR] Partial reservations and interrupted setup sends have no recovery path

**Locations:** `crates/itb/src/run.rs:344-350,610-614`; `crates/itb/src/smoke.rs:206-210`; `crates/itb/src/setup.rs:42-49`; `crates/itb/src/ledger.rs:67-75,151-155`.

**Failure:** Two in-flight windows each pass the earlier headroom check. One consumes headroom before the other reserves its phase. The other successfully reserves a prefix, then fails on a later member; it sends none of that phase and never resolves the prefix. These fees remain charged forever and its payers remain busy until restart. A setup send that returns an ambiguous transport error also leaves a reservation without a persisted blockhash/last-valid-height or a recovery command. `open_signatures` is unused by production recovery code. This is conservative about money, but can exhaust the small campaign budget with transactions that never went on the wire.

**Fix:** Reserve each intended send group atomically; persist its signed transaction, expiry and state before transmission. A recovery command/startup pass must reconcile every open reservation. Distinguish provably never-sent reservations, which can be cancelled transactionally, from possibly-sent reservations, which require terminal evidence. Do not indiscriminately release on an error.

### 10. [MAJOR] A status response is promoted to a landed outcome without proving block inclusion

**Locations:** `crates/itb/src/collect.rs:91-95,111-129,148-169`; `crates/itb/src/rpc.rs:69-74`; `analysis/itb_analysis/outcomes.py:99-101`; `crates/itb/src/run.rs:662-675`.

**Failure:** The first returned status is `processed`, or its block is not yet available. The collector removes it from pending without checking `confirmation_status`. If block retries return nothing, or the returned block lacks the signature, the outcome is still `landed_target` with `index_in_block=None`. The stopping counter counts it as informative. Analysis later executes `int(None)`/`int(NaN)` and fails instead of representing observation uncertainty. If the provisional fork disappears, the reported slot is never corrected. Fee reservation may remain open while the payer is released and the progress count advances.

**Fix:** Keep positive statuses provisional until the chosen commitment is reached and the archived block actually contains the signature with usable metadata/index. Continue resolving status changes; preserve unresolved observation failures separately. Only verified target landings should contribute to complete-case counts. Finalize/archive the evidence level needed for judge reproduction and state that level explicitly.

### 11. [MAJOR] Endpoint and client attribution can describe a different path from the one actually used

**Locations:** `crates/itb/src/run.rs:248-285,335-343,463-467`; `analysis/itb_analysis/outcomes.py:52-68`; `analysis/itb_analysis/report.py:34-39`; `crates/itb/src/targets.rs:52-64`.

**Failure:** At startup a target advertises endpoint E1/direct Agave. Later it switches to E2/BAM and both nearest snapshots around a window agree on E2. The runner still uses the startup `addr_of` entry E1; `_gossip_mode` compares the two snapshots to each other, not to the endpoint actually contacted. The window can be declared stable, while its row retains the old client/ingress. Reporting then labels every run for that validator using the first window's metadata. A separate topology problem is classifying every same-IP Jito TPU as direct: a self-hosted relayer can share the validator IP. The repository's own research note acknowledges this case (`docs/research/03-client-schedulers.md:30`).

**Fix:** Refresh/revalidate the endpoint and mode before preparation, record the exact assignment and actual connection, and require bracketing state to agree with that path. Partition analyses when endpoint/client/version changes instead of taking the first row's label. Treat IP equality as a heuristic, not proof of direct ingress; retain unknown/proxy topology unless supported by endpoint/configuration evidence.

### 12. [MAJOR] `createdBank` can permanently replace the first-shred timestamp

**Locations:** `crates/itb/src/timing.rs:283-315`; `crates/itb/src/run.rs:585-606`; `docs/DATA.md:20-25`; `docs/PLAN.md:165-170`.

**Failure observed in existing data:** In `data/scratch/runs/20261023T162534Z-s1-dry/slot_events.json.zst`, 383 slots contain both event kinds; in 22, `createdBank` arrived first. The largest first-shred-minus-createdBank difference is **161.660204 ms**. The code inserts createdBank with `or_insert`, so the genuine later first-shred event never replaces it. Nevertheless `wait_first_shred` returns the createdBank time as an observed first shred. The fallback `slotNotification` is also treated as the same anchor. The resulting send timing and cadence are materially different from the declared anchor, especially for 5–60 ms races.

**Fix:** Store timestamps separately by event kind and record the kind used for every anchor. Mainnet first-shred analysis must use actual first-shred events. Define explicit fallback eligibility/sensitivity rules for missing first shreds; localnet createdBank support must not silently alter mainnet semantics. Implement the planned second-provider comparison or explicitly revise the timing claims before freezing.

### 13. [MAJOR] There is no send deadline, and the preregistered Stage-1 cutoff is not enforced

**Locations:** `crates/itb/src/run.rs:304-311,352,471-480,585-614`; `crates/itb/src/timing.rs:218-220`; `crates/itb/src/quic.rs:155-175`; `crates/itb/src/rpc.rs:87-91,100-128`; `docs/PREREGISTRATION.md:84-89`.

**Failure:** A slow blockhash RPC or a blocked `open_uni()` finishes after the intended window. Observed anchors remain in memory, `sleep_until` on a past time returns immediately, and the code sends the probes anyway. Stream/write waits have no experiment deadline. A disconnected slot stream can leave `wait_for_slot` waiting indefinitely. `max_minutes` bounds the outer scheduling loop, not queued tasks or their sends; there is no check for **2026-10-29 23:59 UTC**. A window chosen before the run deadline may be transmitted long afterward.

**Fix:** Pass explicit preparation, phase, window and campaign deadlines into execution and transport. Recheck current slot, blockhash validity and allowed lateness immediately before reserving/sending. Cancel and journal overdue probes; keep reservations for any bytes that might already have been transmitted. Implement the calendar cutoff and bound slot/stream waits. Separate delayed collection, which may continue, from prohibited late sending.

### 14. [MAJOR] Race and shared-ingress offsets still assume 200 ms slots despite the new 130/560 ms cadence

**Locations:** `crates/itb/src/design.rs:118-119,180-185,229-234,364-368`; `crates/itb/src/timing.rs:10-13,163-186`; `crates/itb/src/run.rs:577-606`; `docs/PLAN.md:134,141-142`.

**Failure:** With the clock's documented 130 ms within-window increments, first shreds occur near offsets 0, 130, 260 and 390 ms. A race scheduled at 220 and 370 ms crosses the 260 ms slot boundary even though `races_stay_inside_one_slot` passes because 370 < 400. A shared burst at 260 ms is allowed by the avoidance test, which excludes only neighborhoods of 200 and 400. Slot availability/pacing can then produce apparent reordering horizons unrelated to a batch period. Sequential `write_all` calls also provide no guarantee that the back-to-back pair remains below 1 ms under load; the analysis does not measure/enforce that premise.

**Fix:** Anchor a race to the actual selected slot and its empirically supported safe horizon, and classify crossings and realized member gaps from the logs. Use achieved timing for the promised sensitivity analysis. Do not assert within-batch probability ≥0.95 solely from a nominal zero offset or the old 200 ms grid.

### 15. [MAJOR] The stream limit is a test constant, not a runtime limiter

**Locations:** `crates/itb/src/quic.rs:30-33,96-107,149-190`; `crates/itb/src/design.rs:309-314`; `crates/itb/src/main.rs:69-70,130-131`; `crates/itb/src/smoke.rs:154-210`.

**Failure:** `itb smoke --live ... --probes 21` schedules 21 streams at the same instant without rejecting or delaying them locally. Concurrent calls sharing an endpoint also share a connection but do not share a 100 ms stream budget or a sending queue. Server-side throttling can delay selected members and manufacture order/batch effects. The per-IP new-connection limiter exists, but it does not solve stream scheduling; `MAX_STREAMS_PER_BURST` is only consulted by a generator unit test.

**Fix:** Enforce a per-connection rolling stream budget and one coordinated sending queue across all callers, with per-pair ordering and deadline checks. Reject experiment plans/CLI settings whose timing cannot fit the allowance. Record limiter delays separately from intended schedule offsets. Check same-endpoint concurrency and smoke inputs at runtime.

### 16. [MAJOR] Economic-key rules incorrectly require send-order ties even where the economic key is tied

**Locations:** `analysis/itb_analysis/stats.py:25-30,113-115`; `analysis/itb_analysis/sim.py:95,121-134`; `docs/PREREGISTRATION.md:40-46`; `docs/PLAN.md:129-134`.

**Failure reproduced:** Consider a scheduler sorting strictly by CU price and using FIFO only to break equal prices. C1 and C2 favor x, while C3 has equal prices and follows arrival. With 40 balanced pairs per contrast, L counts are `(40,40,20)` and O counts `(20,20,40)`. This is a valid CU-price comparator, but the implementation rejects `cu_price` because pooled O is 80/120. Correcting finding 2 would still reject it through O_C3. The batch simulator randomizes ties, so its positive control omits this ordinary counterexample.

**Fix:** Define complete candidate mechanisms including tie-breaks, or leave order predictions unspecified on key-tied contrasts and report those tie outcomes separately. A FIFO/LIFO tie-break must not be mistaken for evidence against the primary economic comparator. Include economic-key-plus-FIFO/LIFO tie scenarios in validation.

### 17. [MAJOR] Complete-case randomisation inference needs a selection-invariance assumption that the design does not establish

**Locations:** `analysis/itb_analysis/outcomes.py:119-147`; `analysis/itb_analysis/stats.py:129-151,192-199`; `docs/PREREGISTRATION.md:21-24,62-65`.

**Failure scenario:** Across 80 assigned windows, let the potential ordering depend only on send position, with 40 fixed first-position wins and 40 fixed second-position wins. Let pair inclusion retain the 40 windows where assignment makes x the winner, dropping both members in the other 40. The retained set can contain 20 x-first and 20 y-first assignments, yet y_w=1 in all 40 cases. The implemented permutation test returns approximately `p_label=0.000010`; both labels have the same 50% marginal inclusion and McNemar p=1. It has detected a combination of selection and assignment, not established an ordering-key effect among a fixed population.

Permuting the retained assignment vector is valid **conditional on assignment-invariant eligibility/complete-case membership**; simply conditioning on its realized number of x-first assignments is not itself a bug. The missing piece is that invariant selection is not warranted by this experiment, which explicitly anticipates label-dependent drops and timing-dependent eligibility. If “sharp null” includes the entire inclusion process, rejection must be described as rejection of that stronger joint null, not proof of an ordering rule.

**Fix:** State the exact potential-outcome null and required missingness assumptions before freezing. Distinguish ordering-only claims from joint inclusion/ordering claims, implement the prespecified missingness bounds, and simulate correlated pair loss with equal label marginals. Do not imply that the co-primary marginal inclusion test eliminates this selection problem.

### 18. [MAJOR] Strictness and conflict weights reuse dependent pairs as binomial trials; the new verdict tests are outside the 36-effect family

**Locations:** `analysis/itb_analysis/stats.py:19-22,219-256,259-273`; `docs/PREREGISTRATION.md:30,50-51,66-77`.

**Failure reproduced:** Forty windows with all three reward/cost contrasts agreeing produce strictness `120/120` and a one-sided 95% lower bound **0.975345**. If outcomes within each window are perfectly correlated, the supported 40/40 bound is **0.927842**. The descriptive average can be pooled, but the binomial denominator cannot count correlated copies as independent evidence. `conflict_weight` repeats the same pooling and the new diagnosis selects among three economic-rule bounds. That adds up to 18 validator/key effects, yet `alpha_adj` remains `0.05/36`; §4's family still names only label/order effects.

**Fix:** Define uncertainty at the window level for pooled agreement and conflict statistics, and use session clustering where promised. Mark new diagnostics exploratory or explicitly expand/control their family and selection procedure. This is also a preregistration design defect: implementing its pooled CP instruction literally does not make the coverage guarantee valid.

### 19. [MAJOR] Confirmatory cohort, target tier and multiplicity are not tied to a frozen manifest

**Locations:** `analysis/itb_analysis/load.py:86-118,121-123`; `analysis/itb_analysis/report.py:20-51`; `analysis/itb_analysis/stats.py:188-199`; `crates/itb/src/run.rs:202-214,287-292`; `crates/itb/src/alpenglow.rs:33-45`.

**Failure:** Put a synthetic or pilot K run under the supplied raw root: `report.compute` pools it with the campaign because mode, stage provenance, tier, location and frozen design hash are not eligibility gates. Simulated runs are particularly easy to admit because of finding 4. If all ten drafted core/extended targets are present, all get nominally confirmatory rule statuses with the same 36-effect interval correction, while Holm is calculated over however many non-NaN p-values happened to be loaded. The loader never verifies the signed realization against the design. The Rust hash comparison is optional, and no genesis hash binds a run to mainnet; an active feature account alone is not a mainnet identity check.

**Fix:** Require a frozen campaign manifest defining six core targets, endpoints, design/preregistration hashes, chain genesis, sessions and exclusion categories. Validate run membership and realized assignments against it. Separate pilot, simulation, extended and confirmatory results. Define missing effects explicitly in the fixed family and do not silently resize it with available rows. Record and enforce the mainnet identity for confirmatory runs.

### 20. [MAJOR] The report omits the prespecified sensitivities and part of the co-primary inclusion output

**Locations:** `analysis/itb_analysis/report.py:20-52`; `analysis/itb_analysis/stats.py:178-205`; `analysis/itb_analysis/outcomes.py:161-174`; `docs/PREREGISTRATION.md:78,91-98,116-120`.

**Failure:** Running the report produces only complete-case inference. `estimand="censored"` is supported by a helper but never invoked by the reporting path. There are no worst-case missingness bounds, session-cluster intervals, direct buffered/streaming splits, achieved-offset bins or transition-ambiguous sensitivity outputs. Inclusion reports rates and McNemar p-values but omits the specified per-label CP intervals. The funnel does not enumerate all exclusion reasons or joint/same-slot/error stages. A finding that disappears when timing or missingness is considered can therefore be published as the only available result. There is also no reporting gate that withdraws closed-source key conclusions after failed positive controls or failed buffering assumptions (§9).

**Fix:** Implement and emit the six §6 analyses and inclusion intervals from the same cohort definitions, with explicit unavailable/insufficient-session outcomes. Add the stated control/withdrawal decisions to the report. Require these outputs before freezing/reporting confirmatory claims; helpers that are never called do not satisfy the plan.

### 21. [MAJOR] Verification can certify a transaction in the wrong window, a wrong status class, or no evidence at all

**Locations:** `analysis/itb_analysis/verify.py:96-148`; `analysis/itb_analysis/cli.py:61-66`; `docs/PLAN.md:440-443`.

**Failure reproduced:** Using an existing archived probe/block entirely in memory, move its claimed target window 1,000 slots forward and keep `status="landed_target"`. Archive verification still returns **1/1 claims OK**. Neither source checks slot membership in the claimed window. Chain verification distinguishes other-leader versus same-leader status but not `landed_target` versus same-validator/different-window spillover. Archive verification performs no leader check. The probe's recorded signature is not bound to the outcome's signature. Negative indices are also accepted by Python indexing. `verify([])` returns 0 checked/0 OK, which the CLI treats as successful verification.

**Fix:** Validate all identifiers, nonnegative indices, signatures, target/window boundaries and exact status class against authenticated chain/archived evidence. Declare checks unavailable instead of silently omitting them. Make empty/no-coverage verification a distinct non-success result. Recompute pair order and the claimed statistics from the verified subset as promised, rather than validating isolated transaction rows only.

### 22. [MAJOR] Instruction decoding accepts transactions that are not the declared probe atom

**Locations:** `analysis/itb_analysis/verify.py:43-62,132-145`; `crates/itb/src/probe.rs:91-103`; `docs/DATA.md:46,67-68`.

**Failure reproduced:** Append an extra instruction to the in-memory archived transaction while preserving its original signature string, four expected instructions and fee. The verifier still returns **1/1 OK**. It scans for recognized instructions and ignores everything else; duplicate recognized instructions overwrite earlier values. It does not verify the transfer source, exact instruction lengths/order/count, signer count, writable-account set, message version, signed bytes or their cryptographic binding. Missing payer/lock claims default to the decoded values and therefore pass tautologically.

**Fix:** Decode and validate the exact legacy atom, including header, account roles and the zero-lamport transfer from the actual payer. Require all claimed fields, bind the signature to the message/wire bytes, reject unexpected/duplicate instructions, and check realized templates/locks/payers against the frozen assignment. Archive integrity must be authenticated separately from merely parsing JSON.

### 23. [MAJOR] The simulator forces arbitrarily late transactions into the target window

**Locations:** `analysis/itb_analysis/sim.py:23-25,217-219,235-261`; `crates/itb/src/timing.rs:10-13`; `docs/PLAN.md:256-268`.

**Failure reproduced:** Give a streaming pair nominal arrivals at 950 ms, zero latency/jitter, landing probability 1 and a nominal four-by-200 ms window. Both are emitted as `landed_target` in slot `first+3`, because the slot mapping clamps with `min(3, ...)`. A paced queue draining after window end is treated the same way. Blockhash expiry, actual finite window availability and observation/phase errors are not represented. All failed landings become `expired_confirmed`; there are no unresolved collection states, missing-block observations or real eligibility snapshots. Thus simulated power can remain good precisely where the real timing/expiry path fails.

**Fix:** Model a finite target window and validity horizon: late items must spill, expire or remain pending according to the stated scenario. Generate the evidence/uncertainty fields consumed by live eligibility. Parameterize the observed nonuniform cadence, shared transport effects, phase error, pair loss and nonrandom tie-breaks. Keep implementation truth and deliberately simplified models separate in OC claims.

### 24. [MAJOR] Operating-characteristic scoring can hide wrong mixtures and evaluates a different output from the report

**Locations:** `analysis/itb_analysis/oc.py:60-70,89-111`; `analysis/itb_analysis/report.py:35-46,85-92`; `analysis/itb_analysis/stats.py:209-210`.

**Failure:** The newly edited OC code scores `eff["diagnosis"]["verdict"]`, but production reporting emits only `rules` and never exposes `diagnosis` or `conflict`. Its claimed validated verdict therefore is not the verdict shown by the reporting path. More directly, `wrong_rule` exempts **every** label starting with `mixed:` regardless of truth. For example, `expected="lamport_fee"` and `label="mixed:fifo+reward_cost"` contributes zero wrong rules. The same exemption applies under a random/no-key scenario. These summaries can conceal finding 3. OC outputs are averaged across target-runs rather than establishing the probability of any false claim across a full six-validator confirmatory family.

**Fix:** Score the exact same final inferential object the report publishes. Use an explicit truth/compatible-set mapping that counts unsupported extra mechanisms as errors; unknown is not the same as correct. Add label-blind reordering and correlated-window scenarios, and report campaign-level family error with uncertainty. Do not interpret a low value from the current `wrong_rule` column as validation.

### 25. [MAJOR] Live stopping counts unevaluable observations and can overshoot the target

**Locations:** `crates/itb/src/run.rs:301-320,335-374,661-687`; `analysis/itb_analysis/oc.py:45-57`; `docs/PREREGISTRATION.md:82-89`.

**Failure:** A K window has both members land for each contrast but one transport error or a mode transition makes it ineligible. Rust increments all three informative counters anyway; OC increments only for `both_landed and evaluable`. A target can stop at 40 collected pairs while the analysis has fewer usable observations. The literal definition of informative in §5 mentions both members landing, whereas §2 limits inference to evaluable windows: this ambiguity must be settled, not concealed by simulating a different stopping rule from the runner. Multiple future windows for the same target can be queued before any of them resolves; clearing plans at the outer check does not cancel already queued attempts. Increasing concurrency makes the excess large. Date cutoff is separately absent as described in finding 13.

**Fix:** Specify one operational stopping definition shared by Rust, Python and the preregistration. Count only the observations that definition permits, journal why each count changes, and allow at most the explicitly budgeted number of unresolved same-target assignments before rescheduling. If eligibility cannot be known until a later snapshot, delay the count or explicitly preregister the resulting shortfall/overshoot policy.

### 26. [MAJOR] The promised sub-caps and campaign-wide reconciliation layer are absent

**Locations:** `crates/itb/src/auth.rs:21-38`; `crates/itb/src/run.rs:244-245,344-350,383-386`; `crates/itb/src/smoke.rs:88-93,260-263`; `crates/itb/src/ledger.rs:194-201`; `docs/PLAN.md:182,322-328`.

**Failure:** With a campaign ledger fixed at 0.05 SOL, smoke has no separate 0.001 SOL cap and can consume the entire remaining campaign allowance. Passing `--max-spend-sol 0.001` instead conflicts with the ledger's fixed cap; creating the ledger at 0.001 prevents reopening it at 0.05 later. No run/validator/pilot sub-cap exists. On-chain reconciliation resets `initial_total` every run and is absent from setup/smoke, so an earlier undercount is incorporated into the next baseline and cannot be detected as cumulative campaign spend. It also does not compare observed loss with accounted ledger fees or reserve space for an unaccounted discrepancy before additional sends.

**Fix:** Keep one campaign cap and add separately persisted stage/run/validator budgets. Persist the campaign's owned-account set, opening balance and external-deposit ledger. Reconcile cumulative finalized loss and unresolved exposure before admitting new sends, while accounting for in-flight internal transfers. This complements, rather than substitutes for, the correct expiry protocol in finding 1.

### 27. [MAJOR] API credentials can leak into artifacts and error logs despite the redaction guarantee

**Locations:** `crates/itb/src/smoke.rs:71-75`; `crates/itb/src/run.rs:287-290`; `crates/itb/src/rpc.rs:105-113`; `crates/itb/src/timing.rs:136-150,249-250`; `docs/DATA.md:11`.

**Failure:** The synthetic URL `https://rpc.example/v2/TEST_API_TOKEN` is returned unchanged by `redact_url` and written into run metadata. User-info credentials are also retained. Separately, WebSocket errors explicitly interpolate the entire raw URL; HTTP transport errors are logged without removing their URL. A query-key URL that is sanitized on the happy path can therefore leak on failure. This is material because raw data and logs are intended for publication.

**Fix:** Parse URLs and store only an approved credential-free endpoint identity, normally scheme plus hostname/port and an allowlisted nonsecret path. Strip URL material from transport errors before persistence/logging; avoid embedding raw URLs in error context. Test query, path-token, user-info and connection-failure cases with dummy credentials.

### 28. [MAJOR] Failed setup transactions are reported as successful funding/sweeping/Memo operations

**Locations:** `crates/itb/src/setup.rs:50-58,91-98,103-112,117-127`.

**Failure:** A setup transaction returns a status with `err != null`—for example, a funding transfer fails after a competing balance change. The code logs an error, accounts for the fee and returns `Ok(signature)`. The caller prints “funded”/“swept”; a failed Memo can be surfaced as the preregistration signature even though the claimed operation did not execute. Any processed status is accepted, and `transaction_fee(...)=None` substitutes a guessed fee and exits.

**Fix:** Preserve the charge/reservation accounting but return an explicit failed-operation result after confirmed failure. Require appropriate commitment and the expected on-chain effect for successful setup; require a successful, verified Memo before treating the freeze as anchored. Do not equate “a signature was observed” with “setup completed.”

### 29. [MAJOR] Regenerating the design appends duplicate assignments instead of producing one frozen design

**Locations:** `crates/itb/src/main.rs:344-359`; `crates/itb/src/store.rs:50-52`; `crates/itb/src/run.rs:209-220,335`; `analysis/itb_analysis/outcomes.py:43,112-117`.

**Failure:** Run the design command twice with the same output path. It appends a second complete plan. The printed window count/budget describes only the newly generated vector, while the printed hash covers both copies. The runner validates neither unique `(target, stage, seq)` nor unique pair IDs, and filters progress only at invocation startup, so duplicate plans can execute in one run. Duplicate probe IDs then multiply outcome joins or cause `pair_table` to silently discard groups with more than one member per label.

**Fix:** Create the frozen design exclusively or replace it atomically under an explicit regeneration operation; never append whole designs. Validate unique full target/sequence/pair/member identities, valid bounds/templates, planned lock structure and fee budget before signing. Require the loader to reject duplicate IDs rather than silently dropping or multiplying observations.

### 30. [MINOR] PLAN, preregistration and schema still disagree on analysis and timing contracts

**Locations:** `docs/PLAN.md:102-107,141-144,231-245,252`; `docs/PREREGISTRATION.md:21-24,50-66`; `docs/DATA.md:48-56`; `crates/itb/src/design.rs:120-123,266-267`; `crates/itb/src/collect.rs:35-36`.

**Failure:** PLAN calls censored coding primary and complete-case a sensitivity, while the preregistration reverses them. PLAN describes window bootstrap/Holm bounds, while the preregistration uses Bonferroni CP intervals plus Holm p-values. H-kit prose and comments still specify −5 seconds, while the generator sends −7 seconds. The schema omits `not_sent`, and the stated slot-aged hash policy does not itself guarantee a remaining lifetime of 3–6 seconds when slots are skipped or RPC views lag. A judge following different documents can reproduce different estimands or misinterpret the realized hold-cliff intervention.

**Fix:** Make the preregistration the explicit normative analysis source and update the other documents/schema to match the final implementation. Describe blockhash lifetime in verified block heights, distinguish planned slot age from achieved validity, and record all deviations before the on-chain freeze.

## Preregistration §1–§6 disposition

| Section | Assessment |
|---|---|
| §1 estimands | Label mapping and lexicographic `(slot,index)` coding are correct for valid unique records. Complete-case and censored columns are distinct. Selection interpretation needs finding 17; publication currently omits sensitivities. |
| §2 unit/eligibility | One pair row per contrast/window is the intended structure, but missing evidence fails open, duplicates are not rejected, and pooled statistics violate the independent-window unit. Findings 2, 4–7, 10–12, 18–19, 29. |
| §3 predictions | Named economic contrasts separate the three keys algebraically. Arrival predictions for key-tied contrasts are not justified; comparator and tie-break must be separated. Finding 16. |
| §4 inference | Scalar CP endpoints, one-sided beta bound, TOST interval level, and basic Holm/McNemar formulas are correct. Their application is incorrect for pooled dependent trials; six predictions are collapsed; extra diagnostic tests are unaccounted; inclusion intervals are missing. Findings 2–3, 17–20, 24. |
| §5 stopping | Landing-only intent is good, but collector truth, eligibility, pending work, dry-run progress, crash replay and calendar cutoff do not match a single operational definition. Findings 7–10, 13, 25–26. |
| §6 sensitivities | The six promised outputs are not implemented in the report path. Finding 20. |

## Strongest parts to preserve

- **The named probe arithmetic matches pinned Agave v4.3.2.** For one signature and two writes, costs for A/B/A′ are 2,335/4,335/18,711; priority fees are 1,000/1,500/1,000; priorities are 1,498,287/922,509/187,045. The [cost constants](https://github.com/anza-xyz/agave/blob/v4.3.2/cost-model/src/block_cost_limits.rs), [requested-cost calculation](https://github.com/anza-xyz/agave/blob/v4.3.2/cost-model/src/cost_model.rs), [8-CU page cost](https://github.com/anza-xyz/agave/blob/v4.3.2/program-runtime/src/execution_budget.rs), [priority calculation](https://github.com/anza-xyz/agave/blob/v4.3.2/core/src/transaction_priority.rs), [50% base-fee burn/full priority-fee reward](https://github.com/anza-xyz/agave/blob/v4.3.2/runtime/src/bank/fee_distribution.rs), and [ceiling fee calculation](https://github.com/anza-xyz/agave/blob/v4.3.2/compute-budget/src/compute_budget_limits.rs) support these values. Keep requested scheduling cost separate from executed `meta.costUnits`. General, unvalidated integer inputs still need checked/saturating arithmetic rather than assuming these small template values.
- **The C1/C2/C3 intervention is useful:** changing requested data cost at equal price/fee gives a genuine separation that passive fee-versus-index plots cannot. The shared-lock arm and uncontended C2 arm are valuable once payer and timing invariants are enforced.
- **The core reservation primitive is strong:** `BEGIN IMMEDIATE`, WAL/FULL synchronization, a fixed ledger cap and signature primary keys prevent competing successful reservations from independently spending the same headroom. Unknown outcomes remain charged. Repair the evidence/state transitions without weakening these properties.
- **Current CLI dry-run branches do not submit transaction payloads.** Run/smoke use throwaway signers and avoid `send_scheduled`; setup refuses authorization without `--live`. QUIC handshakes in dry run are intentional. The type-level claim is narrower than the comments suggest because `Rpc::send_transaction` itself does not take authorization, so retain call-site auditing or strengthen that boundary.
- **Whole-window pair coding is sensible:** correct C1/C2/C3 labels, lexicographic slot/index ordering, separate complete-case/censored columns, and neither-landed pairs represented as uninformative rather than forced ties.
- **Monotonic local timestamps, archived signed bytes/blocks, explicit ingress uncertainty, compatible-set reporting, and the willingness to publish null results** are the right foundations. Preserve those distinctions while fixing eligibility, provenance and inference.
