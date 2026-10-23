# Gate 1b independent re-review

**Live-mainnet pilot readiness: NO.** The expiry-release proof still admits inconsistent RPC evidence; deadlines do not bound actual writes; recovery and reconciliation do not reliably stop or preserve the experiment. Separately, balanced outcome selection can still produce a confident, false economic-rule verdict.

Reviewed on 2026-10-23 at HEAD `0b57bb39446387fb3e74d71114433e9c1c7f5958`, including the changes in `c0910245fdfaf1ccf6bc2d5b5e379d1596cb656f`, `7115f6c346482d1b5e1feb82bc00cd35a9224eee`, and `014cc7dfe17d590adf792bc7eae1a4bb456b87af`. The normative contract is `docs/PREREGISTRATION.md`; previous finding numbers below refer to `docs/review/CODE-gate1-gpt.md`. CLOSED means the original defect is repaired, not that every adjacent property is verified. PARTIAL means a material part remains or the failure moved to another path.

This was an advisory review. No implementation files were edited. No cargo, Docker, or network commands were run; no live send, Rust build, or current mainnet/provider behavior was independently verified. The assumed deployment is one campaign using one ledger, with the documented smoke/setup/reconcile commands and restarts; those commands must share the invariants claimed for `run`.

## Verification and workspace accounting

- Ran the requested Python suite using the PowerShell equivalent of `PYTHONPATH=analysis .venv/Scripts/python -m pytest analysis/tests -q`, with `PYTHONDONTWRITEBYTECODE=1` and pytest's cache provider disabled.
- First execution: **18 passed, 12 setup errors**, caused by access to the existing shared `pytest-of-valera` temp directory.
- Rerun with a fresh pytest base directory: **30 passed in 21.79 seconds, exit 0**. This is the successful suite result; the initial environment failure is not counted as a pass.
- Additional read-only, in-memory calculations reproduced the balanced-selection false verdict, incomplete-window strictness, predicted-offset substitution, missing endpoint acceptance, a selection-invalid positive control, and acceptance of an extra serialized signature. These did not send requests or create test files. One missing-state calculation raised the TypeError described in N12; it was not silently treated as passing.
- The fresh base-directory value was parsed by pytest into the workspace scratch directory `UsersvaleraAppDataLocalTempcodex-gate1b-e8457d77f56b473894b02bc4fcb16769/`. Automatic approval review rejected removal of that generated test directory, without returning a detailed reason; it remains. The only intentionally authored project file is this report. Existing `docs/review/packet-code-gate1b.md` was left alone; `docs/POWER.md` also appeared as untracked during the review and was left alone.

## 1. Disposition of all 30 previous findings

**Totals: 10 CLOSED / 19 PARTIAL / 1 OPEN.** Each row gives current-tree evidence and one sentence explaining the disposition. Detailed residual scenarios follow the table.

| Previous finding | Status | Current evidence and reasoning |
|---|---|---|
| 1. Expiry lookup predates barrier | **PARTIAL** | `crates/itb/src/collect.rs:139-162`; `crates/itb/src/rpc.rs:309-328`: the lookup now follows the barrier, but independently fetched finalized height and slot can come from inconsistent backends, so the freshness comparison can still release an already-landed transaction (R1). |
| 2. Pooled order contrasts | **CLOSED** | `analysis/itb_analysis/stats.py:99-120,180-189`: rule status now evaluates six separate contrast/coding effects and never uses a pooled order denominator. |
| 3. Noise called an economic mixture | **CLOSED** | `analysis/itb_analysis/stats.py:261-299,311-315`: the old pooled conflict-weight winner is replaced by a window-level test, a three-rule Holm correction, directional consistency, and FIFO-only mixture naming, removing the original label-blind 0.65-order counterexample. |
| 4. Missing evidence eligible | **PARTIAL** | `analysis/itb_analysis/outcomes.py:59-75,88-100,109-129`: missing production and bracketing evidence now exclude windows, but missing used-endpoint fields bypass path matching and the planned count remains self-reported rather than checked against the frozen member set (N2, N12). |
| 5. Lost/released payer leases | **PARTIAL** | `crates/itb/src/run.rs:189-207,411-415,1038-1043`; `crates/itb/src/main.rs:446-476,483-521`: run restores open-reservation leases and keeps unresolved payers busy, but smoke/setup/reconcile do not acquire its campaign lock or consistently honor those leases (N7). |
| 6. Payer identity and randomization | **CLOSED** | `crates/itb/src/run.rs:141-174,783-789,800-802`: the pool rejects duplicate/master pubkeys and shuffles distinct free payers using the recorded per-window seed before assigning them to members. |
| 7. Late attempt journaling/crash replay | **PARTIAL** | `crates/itb/src/run.rs:864-866,943-947,628-635,1091-1093`; `crates/itb/src/store.rs:75-84`: a durable pre-send claim prevents ordinary replay, but sends are still logged after the whole phase, task failures still return overall success, and claims/recovery are not bound to campaign/design identity (N5, N6, N8). |
| 8. Dry run consumes live progress | **CLOSED** | `crates/itb/src/main.rs:398-404`; `crates/itb/src/run.rs:281-283`: default journals are separate and loading additionally filters by live/dry mode even if a path is explicitly shared. |
| 9. Partial reservations/no recovery | **PARTIAL** | `crates/itb/src/ledger.rs:186-243`; `crates/itb/src/main.rs:450-476`: phase reservation is atomic and recovery now exists for fees, but it discards target/window provenance and never repairs raw observations or stopping progress (N6). |
| 10. Provisional status counted as landing | **CLOSED** | `crates/itb/src/collect.rs:108-112,133-136,203-230`; `crates/itb/src/run.rs:1051-1054`: processed statuses remain pending, and a signature missing from the fetched block becomes charged `landed_unverified`, excluded from target-landing counts. |
| 11. Wrong endpoint/client attribution | **PARTIAL** | `crates/itb/src/run.rs:739-759`; `analysis/itb_analysis/report.py:173-175`; `crates/itb/src/targets.rs:65-75`: refreshing the path and grouping fix stale startup attribution, but same-IP Jito relayers on a non-default port are still positively classified as direct without topology evidence. |
| 12. createdBank replaces first shred | **PARTIAL** | `crates/itb/src/timing.rs:93-109,222-226,398-417`; `analysis/itb_analysis/outcomes.py:94-129`: event maps are separate and kinds are recorded, but mainnet fallback/createdBank timing is not excluded or separated by analysis, and the promised second-provider comparison is absent. |
| 13. Missing send/campaign deadlines | **PARTIAL** | `crates/itb/src/run.rs:923-943`; `crates/itb/src/quic.rs:256-275`; `crates/itb/src/main.rs:153-155`: late-open checks and an optional cutoff exist, but neither the actual open/write nor a future scheduled send is bounded by the campaign cutoff or run deadline (R3). |
| 14. Old 200 ms race grid | **PARTIAL** | `crates/itb/src/design.rs:117-122,217-225`; `crates/itb/src/run.rs:877-920`; `analysis/itb_analysis/report.py:71-91`: the generator uses 130 ms and a first-slot anchor, but actual slot crossings/member gaps are not classified, and achieved offsets substitute a predicted start for the observed first shred (N9). |
| 15. Stream limit is only a constant | **CLOSED** | `crates/itb/src/quic.rs:203-218,237-261`: callers sharing a connection serialize through one mutex and one rolling 14-stream/100-ms budget with recorded limiter delay. |
| 16. Key-tied contrast rejects comparator | **CLOSED** | `analysis/itb_analysis/stats.py:31-32,82-83,110-111`: CU-price and lamport-fee rules use `any` for O_C3, so FIFO/LIFO tie-breaking there no longer rejects the economic key. |
| 17. Complete-case selection invalidates inference | **OPEN** | `analysis/itb_analysis/stats.py:213-227,302-307`; `analysis/itb_analysis/report.py:116-125`; `docs/PREREGISTRATION.md:30-33`: balance testing cannot establish selection invariance, and the original balanced-selection counterexample still gives a confident economic verdict with reassuring bounds (R2). |
| 18. Dependent strictness/conflict trials | **CLOSED** | `analysis/itb_analysis/stats.py:230-258,274-298`: strictness now has one trial per window and mixture testing operates on window summaries with its stated secondary Holm family, repairing the correlated-copy denominator defect; incomplete-window semantics are a separate new issue (N10). |
| 19. No frozen cohort/fixed family | **PARTIAL** | `analysis/itb_analysis/report.py:44-68,160-175,197-215`; `scripts/freeze.py:31-50`: a manifest and fixed-family Holm option exist, but missing manifests fail open, pilot/date provenance and realized design are unchecked, and multiple groups expand the interval family (N1, N2, N4). |
| 20. Missing sensitivities/inclusion/gates | **PARTIAL** | `analysis/itb_analysis/report.py:181-222,258-268`; `analysis/itb_analysis/stats.py:190-201`: inclusion intervals and all six sensitivity categories now have output paths, but achieved timing is wrong, several sensitivities expose labels only, and control withdrawals do not reach the summary verdict (N3, N9). |
| 21. Verifier accepts wrong window/status/empty set | **PARTIAL** | `analysis/itb_analysis/verify.py:211-255,258-260`; `analysis/itb_analysis/cli.py:63-68`: window, leader, signature, nonnegative index and empty-coverage checks are repaired, but the promised frozen-assignment validation and recomputation of pair/report claims are still absent. |
| 22. Decoder accepts non-atom transactions | **PARTIAL** | `analysis/itb_analysis/verify.py:67-97,100-135,138-150`: exact instructions and cryptographic message binding are substantially stronger, but signature-vector length is not checked against the header and an invalid full transaction can still pass (N13). |
| 23. Simulator forces late target landings | **PARTIAL** | `analysis/itb_analysis/sim.py:269-277,296-304`: finite-window overflow now spills/expires instead of clamping, but every simulated window still has perfect production/send evidence and failed observations never exercise unresolved/missing-block collection states. |
| 24. OC hides wrong mixtures/different output | **PARTIAL** | `analysis/itb_analysis/oc.py:26-46,71-86,107-129`; `analysis/itb_analysis/report.py:175-222`: explicit compatible truth sets and campaign-any-error scoring fix the mixture exemption, but OC still bypasses report gates/grouping and uses a different stopping definition (N11). |
| 25. Wrong informative count/overshoot | **PARTIAL** | `crates/itb/src/run.rs:551-580,1046-1075`; `analysis/itb_analysis/oc.py:60-67`; `docs/PREREGISTRATION.md:107-112`: verified/error-free counts and one same-target window in flight fix the runner, but OC still conditions stopping on gossip eligibility whereas the normative operational rule explicitly does not. |
| 26. Missing sub-caps/cumulative reconciliation | **PARTIAL** | `crates/itb/src/ledger.rs:159-243,349-438`; `crates/itb/src/run.rs:402-404,1077-1086`; `crates/itb/src/smoke.rs:87-89,318-320`: named budgets and a cumulative baseline now exist, but pilot/run/validator caps remain optional, smoke/setup lack that reconciliation, and a reconciliation failure does not stop other run tasks (N8). |
| 27. Credential leakage | **CLOSED** | `crates/itb/src/rpc.rs:107-116,135-137,408-418`; `crates/itb/src/timing.rs:333-339`; `crates/itb/src/smoke.rs:285-286`: the previously identified path/query/user-info and transport-error URL leaks are removed by shared redaction and sanitized transport errors. |
| 28. Failed setup reported successful | **CLOSED** | `crates/itb/src/setup.rs:93-119`: setup now resolves through the confirmed/block-verified collector and returns an error for expiry, unresolved/unverified inclusion, or a non-null execution error. |
| 29. Design regeneration appends duplicates | **PARTIAL** | `crates/itb/src/main.rs:525-549`; `crates/itb/src/design.rs:412-453`; `analysis/itb_analysis/outcomes.py:146-151`: exclusive design creation and duplicate-plan checks fix regeneration, but validation still does not enforce actual contrast labels/templates/locks, and analysis silently skips duplicate-member groups rather than rejecting them (N2). |
| 30. Contradictory documents | **PARTIAL** | `docs/PLAN.md:4-7,44,106,239-249`; `docs/PREREGISTRATION.md:63-82`; `crates/itb/src/design.rs:393`: normative precedence and H offsets are clarified, but incompatible inference/lifetime prose and stale claims remain (N14). |

## 2. Critical residual failure paths

These extend previous findings rather than being counted again as newly discovered defects.

### R1. [BLOCKER] The new expiry barrier is not a consistent height/slot observation

**Evidence:** `crates/itb/src/collect.rs:139-162,232-236`; `crates/itb/src/rpc.rs:309-328`; `crates/itb/src/ledger.rs:278-280`.

**Inputs -> wrong result:** backend A answers finalized height H+1 after the transaction landed at H; a lagging backend B answers the separate finalized-slot request with slot S0 from before that landing; backend C answers the subsequent history lookup with null and context S1, where S0 <= S1 but S1 is also before the landing. The new condition succeeds even though C has not reached A's expiry barrier. With 49,994,000 lamports already accounted and a 6,000-lamport reservation, that transaction can spend the remaining allowance, be falsely released, and a subsequent one-probe smoke send can raise actual campaign fees to 50,006,000 while the ledger still shows 50,000,000. Smoke has no cumulative balance check.

The response context also establishes a processed view, not the completeness of historical signature indexing; requesting history is not a locally verified history-availability guarantee. This matters especially for old reservations reconciled after recent status-cache coverage has passed.

**Fix:** derive slot and height from the same finalized block observation, then require a responder with a view and history demonstrably covering that barrier; retain the reservation when non-inclusion is unprovable. A dedicated consistent archival backend is an acceptable operational constraint if enforced. Preserve the evidence durably before release. Test the different-backend sequence as well as the original delayed-null race; the current collector tests only locate signatures and distinguish processed/confirmed.

### R2. [BLOCKER] The new selection check still certifies the old balanced-selection counterexample

**Evidence:** `analysis/itb_analysis/stats.py:124-147,213-227,302-307`; `analysis/itb_analysis/report.py:116-125`; `docs/PREREGISTRATION.md:30-33`.

**Inputs -> wrong result:** for C1 and C2, use a label-blind mechanism whose fixed potential winner is first position in half the windows and second position in half; retain both members only when their assignment makes x win, losing both in the other windows. The retained 40 observations can have exactly 20 x-first assignments and 20 y-first assignments, with x winning all 40. Make C3 balanced FIFO. Both labels have equal marginal inclusion, no discordant inclusion, and no single-landed pairs. This requires no economic ordering mechanism.

**Reproduced output:** `diagnosis.verdict = cu_price`; all three selection p-values are **1.0**; C1/C2 missingness bounds are **[1.0, 1.0]**. Those bounds cover only single-landed pairs and cannot expose assignment-dependent loss of both members. The new balance diagnostic rejects some selection mechanisms, but its non-rejection is not a test establishing the required counterfactual invariance. The wording “checked, not assumed” is false.

**Fix:** keep complete-case rates descriptive unless the ordering interpretation has an explicit, defensible selection assumption; define the sharp joint inclusion/ordering null correctly and report selection-robust identification limits when it cannot be separated. Include the balanced, double-loss counterexample in validation. Merely adding more balanced retained observations or an inclusion McNemar test does not repair identification.

### R3. [MAJOR] Deadlines are checked before waiting, not enforced on transaction writes

**Evidence:** `crates/itb/src/main.rs:153-155`; `crates/itb/src/run.rs:536-549,616,923-943`; `crates/itb/src/quic.rs:237-275`.

**Inputs -> wrong result:** a streaming phase is prepared 10 ms before `--not-after`, with its send scheduled 60 ms after the observed anchor; the current-time check passes, then `sleep_until` sends after the cutoff because Outgoing has no campaign deadline. Independently, `open_uni()` can begin before a 20-ms lateness deadline, return 400 ms later, and then write the full transaction because both waits use separate 500-ms timeouts. The max-minutes deadline is not passed into window tasks at all. Omitting the optional `--not-after` also disables the preregistered calendar stop.

**Fix:** pass one effective absolute deadline, the minimum of phase/window/run/campaign deadlines, through preparation and transport; use `timeout_at` on open and write and recheck before writing bytes. Clamp future scheduled sends to the cutoff, enforce it from the campaign configuration, and retain exposure whenever bytes might already have left. Collection may continue after sends stop.

## 3. New findings and newly exposed defects

### N1. [MAJOR] Manifest selection fails open and admits pre-freeze pilot data

**Evidence:** `analysis/itb_analysis/report.py:44-68,160,197,211-215`; `analysis/itb_analysis/cli.py:27-28`; `scripts/freeze.py:42-50`; `docs/PREREGISTRATION.md:3-11`.

**Inputs -> wrong result:** pass a misspelled `--manifest` path, or use the default before `design/campaign.json` exists: `load_manifest` returns None, all runs are selected, and every validator gets `confirmatory=True`, including simulated/localnet/pilot data. This directly contradicts CLI help saying these outputs are non-confirmatory. With a manifest present, an earlier live pilot using the same design/genesis also passes because `frozen_at`, measurement dates, stage and pilot provenance are not checked and the generated exclusion list is empty.

**Fix:** an explicitly requested missing manifest must fail; allow preview analysis only through an explicit mode that marks every result non-confirmatory. Require a validated campaign/session membership rule and enforce pilot exclusion plus freeze/start/cutoff bounds, rather than relying on the directory chosen by the operator. Verify the preregistration/design commitments used for that campaign.

### N2. [MAJOR] Eligibility and inference never validate the realized treatment against the frozen design

**Evidence:** `analysis/itb_analysis/outcomes.py:84-100,146-151`; `analysis/itb_analysis/report.py:54-61,154-175`; `crates/itb/src/design.rs:412-453`; `analysis/itb_analysis/verify.py:100-120`.

**Inputs -> wrong result:** a frozen K plan contains eight members, but six records are logged and `planned_probes=sent_ok=6`, `not_sent=transport_errors=0`; valid snapshots and production make the window evaluable despite two missing frozen members. More seriously, exchange the A/B templates while retaining their label strings: runtime validation accepts the structure, the verifier compares the bytes only to those same self-reported templates, and inference still interprets label A as the preregistered economic intervention. Repeatedly ordered identical or inverted treatments can therefore produce the wrong named comparator. Duplicate member/outcome joins are also silently skipped or multiplied rather than rejected at ingestion.

**Fix:** load the committed design in analysis and validate the exact target/stage/sequence, pair kinds, unique members, label-to-template mapping, positions and lock relationships before computing outcomes; compare signed realizations to that independent assignment. Validate per-probe send evidence rather than accepting aggregate counters as the frozen plan. Reject malformed/duplicate records with an explicit exclusion/error.

### N3. [MAJOR] Positive controls can pass after selection failure, and withdrawal disappears from the summary

**Evidence:** `analysis/itb_analysis/report.py:219-222,258-268`; `analysis/itb_analysis/stats.py:302-307`; `scripts/freeze.py:35-38`; `docs/PREREGISTRATION.md:157`.

**Inputs -> wrong result:** an economic positive control has 40 perfect reward/cost outcomes but x was sent first in 29 windows; reproduced output is `reward_cost=SUPPORTED`, selection p **0.006426576**, and final diagnosis `unidentified:selection`. The positive-control gate checks the pre-override rule status, so it calls this unusable control successful. It also accepts any group for the identity, even if that validator changed from the specified direct public client to another client/ingress. Conversely, when a control really fails, JSON sets `closed_source_conclusions_withdrawn=True`, but `markdown_summary` still prints a bold closed-source economic verdict without that withdrawal; it renders only buffer/streaming flags.

**Fix:** specify and enforce the eligible client/ingress of each control, require a valid final selection/gate state, and propagate control failure into every affected group's publishable conclusion and all summary renderers. Preserve raw rule scores separately from an explicitly withdrawn final claim.

### N4. [MAJOR] Client/ingress partitioning expands the interval family beyond 36

**Evidence:** `analysis/itb_analysis/report.py:173-175,197-215`; `analysis/itb_analysis/stats.py:23-24,180-188`; `docs/PREREGISTRATION.md:46,63-66`.

**Inputs -> wrong result:** each of six core identities has two stable client/ingress groups during the campaign. The report issues 72 contrast/coding intervals and associated rule decisions, each with alpha `0.05/36`, while advertising a 36-effect confirmatory family. Holm grows with the available p-value count, but the intervals that drive rule decisions do not. Data-dependent deployment changes have created additional claim opportunities without the stated simultaneous coverage guarantee.

**Fix:** freeze the actual confirmatory groups or preallocate each validator's alpha across all permitted groups; make interval, equivalence and p-value families agree. Mark additional groups exploratory when they are outside that allocation.

### N5. [MAJOR] Pilot progress and stopping counts leak into the campaign

**Evidence:** `crates/itb/src/run.rs:273-299,365-369,551-565,864-866,1091-1093`; `crates/itb/src/main.rs:398-404`; `docs/PREREGISTRATION.md:11`.

**Inputs -> wrong result:** run a live pilot with the default progress path, then freeze/regenerate the campaign design and run Stage 1 using the same ledger/path. Progress keys contain only target/sequence/live, not campaign, design, stage or pilot purpose. Pilot sequence claims consume campaign assignments and its informative counts can stop the campaign after fewer than 40 new pairs, or immediately if the pilot already reached 40. Excluding pilot files from the report does not undo that stopping decision.

**Fix:** bind progress to campaign/design identity, stage and measurement purpose; refuse mismatched journals and exclude pilot counts from confirmatory stopping. Keep the fee ledger cumulative across both purposes. Journal an idempotent terminal transition per unique attempt so repeated terminal records cannot inflate counts.

### N6. [MAJOR] Recovery fixes accounting while permanently losing the measurement and stopping evidence

**Evidence:** `crates/itb/src/main.rs:450-475`; `crates/itb/src/ledger.rs:64-70,288-302`; `crates/itb/src/run.rs:1024-1036,1091-1093`; `analysis/itb_analysis/outcomes.py:47-48`.

**Inputs -> wrong result:** a phase is sent and the process dies before outcomes/terminal progress are written. `itb reconcile` reconstructs every reservation with empty target identity, window [0,0], and `run=None`; an actual target landing is thus classified as other-leader spillover, its block is not archived into the run, its outcome is printed only, and its ledger row becomes terminal. A later reconcile no longer sees it, the claimed plan cannot rerun, and analysis retains an unresolved/missing observation. A crash after some terminal ledger updates but before outcome logging creates the same unrecoverable split. This can selectively lose whole sessions and alter the landing-based stopping rule.

**Fix:** persist run/attempt/probe/target/window provenance and signed realization durably with reservations; make reconciliation write idempotent original-run outcomes and archives, then reconstruct terminal progress and informative counts. Accounting recovery alone must not be presented as experiment recovery.

### N7. [MAJOR] The new campaign lock and payer leases protect only `run`

**Evidence:** `crates/itb/src/run.rs:189-207,383-415`; `crates/itb/src/main.rs:446-476,483-521`; `crates/itb/src/smoke.rs:82-95,233-245`; `crates/itb/src/setup.rs:163-190`; `crates/itb/src/ledger.rs:234-240`.

**Inputs -> wrong result:** while a run has a valid pending probe from payer P, execute `setup sweep` over that payer directory; it does not acquire the lock or check P's lease and can drain P while the probe remains queued. A simultaneous smoke/restarted smoke likewise ignores existing payer reservations. SQLite prevents spending the same fee headroom twice, but it does not prevent these unintended payer write locks/balance changes, which alter inclusion and order. After a crash, the persisted lock file also needs manual removal; it is not a process-lifetime lock.

**Fix:** enforce the same exclusive campaign/process-lifetime lock and payer ownership rules for every sending or reconciling entry point; refuse sweep/fund operations involving leased accounts until terminal resolution. Use a lock that releases on process death without unsafe manual deletion, or provide validated stale-lock recovery.

### N8. [MAJOR] A failed cumulative reconciliation is logged and other live sends continue

**Evidence:** `crates/itb/src/run.rs:628-635,935-943,1077-1086`; `crates/itb/src/ledger.rs:427-436`; `crates/itb/src/smoke.rs:318-320`; `crates/itb/src/main.rs:491-523`; `docs/PLAN.md:329-331`.

**Inputs -> wrong result:** reconciliation for one completed window detects an unaccounted balance loss and returns an error, while another task is waiting to send and the ledger still has headroom. The wrapper logs “window failed”, drops its permit, and continues scheduling/sending; there is no shared abort flag, and the end-of-run error arrives after the extra exposure. The 10,000-lamport tolerance is also neither charged nor subtracted from headroom: an allowed discrepancy can be followed by sends spending the whole recorded cap, leaving actual spend above it. Smoke/setup do not invoke this layer at all. A pilot with `--budget pilot` but no `--budget-sol` has no 0.004-SOL sub-cap.

**Fix:** make failed reconciliation a campaign-wide send stop checked immediately before reservation/write; perform shared finalized/context-consistent reconciliation before admitting further exposure in every live command. Charge or hold headroom for unexplained loss, fail closed on invalid balance responses, and enforce the documented smoke/pilot/stage/run/validator budget policy rather than optional names. Continue collecting already-sent transactions after stopping new sends.

### N9. [MAJOR] “Achieved first-shred offset” is a predicted offset in buffered windows

**Evidence:** `analysis/itb_analysis/report.py:71-91,189-191`; `analysis/itb_analysis/load.py:31-42,86-101`; `crates/itb/src/run.rs:877-899,655`; `docs/PREREGISTRATION.md:127`.

**Inputs -> wrong result:** previous-slot anchor is t=0, estimated handover is 560 ms, and first stream finishes at 410 ms; the helper reports **-150 ms** (reproduced). If the target's recorded first shred was actually at 400 ms, the achieved offset is **+10 ms**, which belongs in another bin and was not buffered. The report never reads the slot-event archive; it adds the predicted boundary gap to the previous anchor. It also ignores anchor event kind, allowing slotNotification/createdBank to stand in for firstShredReceived. Many primary direct-ingress windows use only the previous-slot anchor.

**Fix:** derive the reference from the actual target-first-slot firstShredReceived event, keyed by run and slot, and report timing unavailable when it is absent. Keep planned/estimated offsets separate; enforce or stratify anchor kinds and measure actual pair gaps/slot crossings. Do not use the resulting estimated bins as the promised achieved-timing sensitivity.

### N10. [MAJOR] Window strictness counts “all predictions” even when most were never observed

**Evidence:** `analysis/itb_analysis/stats.py:230-258`; `docs/PREREGISTRATION.md:96`.

**Inputs -> wrong result:** in 40 eligible K windows only C1 has two landed members, and its winner always matches reward/cost; C2 and C3 are unobserved. Reproduced output nevertheless says **40/40 windows_all_agree**, rate **1.0**, lower95 **0.9278424755**. FIFO has the same problem through a minimum over whichever contrasts remain. The fixed denominator no longer duplicates windows, but now substitutes an easier, selected “all available” event for the specified “all directional predictions” event.

**Fix:** require the complete set of relevant contrasts before scoring that window's all-predictions event, or preregister/report a different partially observed estimand with explicit bounds and denominators. Do not certify full-rule strictness from one surviving contrast.

### N11. [MAJOR] Operating characteristics still validate a different final procedure

**Evidence:** `analysis/itb_analysis/oc.py:49-77,81-86,107-129`; `analysis/itb_analysis/sim.py:296-304,332-335`; `analysis/itb_analysis/report.py:173-222`; `docs/PREREGISTRATION.md:107-112`.

**Inputs -> wrong result:** put ten otherwise error-free, both-landed windows across a mode transition before later stable windows. Rust counts those ten toward its stop, as §5 expressly requires, but OC skips them because `evaluable` is false and samples more windows. OC also scores `stats.validator_effects` directly, without the report's positive-control, buffer or grouping gates; a raw economic verdict withdrawn by the report is still a detection/error in OC. The simulator's always-complete evidence conceals these differences. A low `family_wrong_rate` therefore does not establish the performance of the published procedure, despite the module's “same analysis” claim.

**Fix:** share one operational stopping predicate and one final claim/gate object with production reporting, then simulate mode/transport/observation failures and score that object. Report replicate-level error uncertainty as well as a point fraction; do not equate a small number of zero-error campaigns with a demonstrated 5% guarantee.

### N12. [MAJOR] Missing attribution is either accepted or crashes the complete report

**Evidence:** `analysis/itb_analysis/outcomes.py:66-75`; `analysis/itb_analysis/load.py:67-81`.

**Inputs -> wrong result:** with two valid matching gossip snapshots but all three used-path fields absent, `_gossip_mode` returns **stable** (reproduced), since the comparison is skipped rather than failing closed. If a present snapshot instead has a missing TPU/client/ingress field, pandas in the installed environment preserves a missing float through `astype(str)` and `"|".join` raises **TypeError: sequence item 0: expected str instance, float found** (reproduced). A validator losing its advertised TPU between the before/after snapshots should produce an exclusion, not crash analysis of every other validator.

**Fix:** explicitly require non-missing attribution fields on the used path and both snapshots before comparing typed tuples; classify incomplete evidence as unknown/ineligible and actual changes as transition-ambiguous. Do not fix this by converting missing values into equal string keys.

### N13. [MINOR] Signature verification binds the message but not the validity of the full serialized transaction

**Evidence:** `analysis/itb_analysis/verify.py:69-75,96-104,124-135,138-150`.

**Inputs -> wrong result:** take a genuine one-signature probe, change its serialized signature count from 1 to 2, and insert a second arbitrary 64-byte signature before the unchanged message. Reproduced checks report two signatures, every `check_atom` result true, valid payer signature/claim binding, and on-chain-message equality. The message still requires one signature, so the full logged wire transaction is invalid and cannot be the exact transaction sent. The verifier never compares the complete signature vector to the on-chain vector. ComputeBudget account lists are also not constrained to the atom's empty lists.

**Fix:** require exactly one signature, match that count to the message header and the complete on-chain signature vector, require the exact expected instruction account lists, and validate the complete canonical wire structure. This is an evidence-integrity defect, not proof that a genuine chain landing or its fee is wrong.

### N14. [MINOR] Judge-facing completion and timing claims still exceed the implementation

**Evidence:** `README.md:10,57,130`; `docs/PLAN.md:44,106,239-249,329`; `crates/itb/src/design.rs:393`; `crates/itb/src/main.rs:153-170`; `docs/PREREGISTRATION.md:66-82`.

**Inputs -> wrong result:** a judge following PLAN's window-bootstrap/Holm-bound instructions reproduces a different inferential procedure from the normative CP/Bonferroni implementation; the old 200-ms/3–6-second lifetime claims also survive beside the new cadence, and a comment still calls the H intervention -5 seconds. README says all 30 findings are addressed and the campaign has a hard stop, although several remain open/partial and the cutoff is optional. The promised per-run/per-validator caps are not automatic.

**Fix:** replace, rather than merely supersede, contradictory operational/inference prose; state measured block-height validity instead of promising lifetime from slot age; correct the H comment and qualify review/completion claims. Link to actual current validation evidence and the residual gate status. Normative precedence resolves which document wins but does not make contradictory judge-facing claims true.

## 4. Minimal changes before a live pilot

**No, this design is not ready for a live mainnet pilot in its current state.** The following is the minimum operational gate; it does not require finishing every exploratory analysis before collecting calibration data.

1. **Repair terminal non-inclusion proof (R1):** do not release exposure on inconsistent/unknown history; retain reservations until consistent evidence exists. Cover delayed responses, lagging backends, history gaps and restart reconciliation with deterministic tests.
2. **Bound actual sends (R3):** apply campaign/run/window deadlines to stream open and write, including tasks already queued, with conservative accounting after ambiguous partial transmission.
3. **Make the entire campaign fail closed (N7–N8):** all live commands share locking/leases, the pilot has an enforced 4,000,000-lamport allowance inside the same 50,000,000-lamport campaign ledger, cumulative discrepancies reserve headroom, and reconciliation failure stops further sends globally.
4. **Make a paid attempt recoverable (N5–N6 and finding 7):** durable realization/send/provenance records, resumable original-run block/outcome collection, idempotent progress, explicit process failure on incomplete windows, and pilot-specific progress that cannot consume confirmatory plans.
5. **Make pilot calibration measure the intended path/time (findings 11–14, N9, N12):** fail closed on missing attribution, keep uncertain relayers out of a proven-direct stratum, retain actual first-shred evidence and pair gaps, and report timing/eligibility failures explicitly rather than substituting estimated anchors.

The all-dry paths inspected still require no transaction submission: run/smoke branch away from `send_scheduled`, setup requires live authorization, and both RPC submission and QUIC sending require `LiveAuthorization` (`crates/itb/src/run.rs:935-970`; `crates/itb/src/smoke.rs:225-265`; `crates/itb/src/rpc.rs:388-395`). QUIC handshakes remain intentional dry-run network traffic. No reachable transaction-payload send in dry-run was found by static review; this is not a packet-capture verification.

**Before freezing or publishing confirmatory verdicts**, additionally resolve R2 and N1–N4/N10–N11, validate frozen treatment realizations (N2), make withdrawals visible in the final claim, and rerun operating characteristics against that exact procedure. Pilot data can be used for calibration after the operational gate above, but must remain excluded from confirmatory inference and stopping counts. Passing the current 30 Python tests does not close the RPC/transport/crash invariants that those tests do not exercise.
