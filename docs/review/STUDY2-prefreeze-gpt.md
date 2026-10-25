# Study 2 pre-freeze review

**Verdict: resolve the blockers before freezing.** Reviewed commit `518d7fb`, including the generated 570-window design. Findings are ranked below; each fix belongs before the Memo.

**Scope:** concurrent source and design edits appeared during final verification. Findings, line references and the test result below apply to the reviewed version at `518d7fb`; subsequent working-tree changes have not been re-reviewed.

## Blocker

1. **Simultaneous races can wrongly withdraw a valid 2 ms result.**

   **Evidence:** `crates/itb/src/design.rs:144–150`; `analysis/itb_analysis/study2.py:167–175`; `docs/PREREGISTRATION-2.md:139`.

   `gates()` treats every race labelled `first_label == "hi"` as a positive control, including the six nominally simultaneous races. A simultaneous send has no meaningful head start; small path noise can reverse receipt order without invalidating a 2 ms experiment. Concrete counterexample: all 35 primary races support H1, all six genuine 5/25 ms hi-first controls win, but three simultaneous hi-first races lose. The implemented gate withdraws H1. If those six simultaneous outcomes are fair coins, the probability of at least two losses is **89.1%**.

   **Fix:** freeze controls as strictly positive-gap hi-first races, with an achieved-gap requirement. Keep zero-gap races exploratory. Specify minimum informative control coverage and an unavailable-control outcome; currently zero informative controls also silently pass.

2. **The required replication-failure note never reaches H1–H3.**

   **Evidence:** `docs/PREREGISTRATION-2.md:138`; `analysis/itb_analysis/study2.py:225–228,250–257`; `analysis/itb_analysis/report.py:293–299`.

   The replication computes positive-control failure, but Study 2 merely nests that result beside independently generated hypothesis claims. Nothing propagates failure into their `published_claim`. Thus a failed Agave/Firedancer replication check can coexist with six unqualified H1–H3 results, contrary to the normative publication gate.

   **Fix:** pass the replication check into final claim construction and append exactly “method check failed in the replication” to every affected H1–H3 result. Define missing replication/control evidence explicitly. The registration requires a note here, not automatic withdrawal of H1–H3.

## Should-fix

3. **The operating characteristics score an earlier procedure, and do not establish null calibration.**

   **Evidence:** `scripts/oc_study2.py:67–76`; `docs/POWER-2.md:31–37,51–62`; `analysis/tests/test_study2.py:37–50`.

   The OC script calls `evaluate()`, never `gates()` or `published()`, and does not supply send records to `pair_table()`. Its “published as supported” rates therefore omit withdrawals and timing checks. The tests’ main known-scheduler helper has the same omission. Finding 1 can make these rates materially different.

   Also, the `opposite` scenario puts hypotheses well inside their null regions; it does not test the difficult boundary at probability 0.5. Zero false-positive campaigns out of 40 has a one-sided 95% upper rate of **7.2%**, so “no hypothesis is ever supported” is not established.

   **Fix:** score final gated claims using send records, regenerate the table, and include boundary-null scenarios. Report the campaign-level event “any false support,” with Monte Carlo uncertainty; retain Holm’s analytical guarantee separately.

4. **H3 can claim a 10 ms effect without achieving that gap or establishing the stated buffering interpretation.**

   **Evidence:** `crates/itb/src/design.rs:455–475`; `docs/PREREGISTRATION-2.md:69–70,83,121–122`; `analysis/itb_analysis/study2.py:165–166,230–231`.

   Equal-key pairs are nominally sent at −150/−140 ms. Their gap is not gated, and they are retained unconditionally even in the achieved-gap sensitivity. An in-memory example with 59 later-member wins and an achieved gap of **0.1 ms** still returns unqualified, selection-robust H3 support. Sender delays can compress nominal gaps because overdue streams are sent back-to-back (`crates/itb/src/quic.rs:214–239`).

   Even an achieved 10 ms send gap does not establish a 10 ms separation, or preserved arrival order, when buffered packets reach the scheduler. A buffered later-sent-first result does not by itself identify an internal later-arrival-first tie-break.

   **Fix:** report H3’s achieved gaps and both members’ offsets from the observed first shred; add a valid-gap sensitivity and a rule for failed buffering evidence. State the result as **later-sent-first among buffered probes**, with receipt-order preservation an explicit assumption for the scheduler interpretation.

5. **The 55 ms nominal endpoint does not guarantee first-slot containment.**

   **Evidence:** `docs/STUDY2-PLAN.md:54–56`; `docs/PREREGISTRATION-2.md:22–23,66`; `crates/itb/src/run.rs:1011–1018`; `analysis/itb_analysis/study2.py:171–175`.

   The generated offsets are nominally safe: 5 + 50 = 55 ms, below the assumed 130 ms cadence. Execution permits 100 ms lateness, however, so an allowed stream opening can occur around +155 ms, before considering path delay. The analysis checks only the within-pair gap, not absolute timing or crossing into another slot. A curve can therefore mix first-slot races with later-slot conditions while being described as inside the first slot.

   **Fix:** freeze reporting and sensitivity rules based on achieved per-member offsets and observed slot boundaries. Separate same-slot and crossing races, and describe the primary estimand as window-wide if crossings remain eligible. Do not treat the nominal-offset test as proof of realised containment.

6. **O(0) discards half the balanced simultaneous allocation.**

   **Evidence:** `docs/PREREGISTRATION-2.md:128–129`; `crates/itb/src/design.rs:145`; `analysis/itb_analysis/study2.py:207–214`.

   The registration requests simultaneous sends in both stream orders, but `curves()` keeps only `first_label == "lo"` for every Δt. At zero this retains six races and moves the other six into controls. Under pure stream-order FIFO, the intended balanced O(0) is 6/12 = 0.5; the emitted overtake cell is 0/6. This also changes the descriptive horizon bracket.

   **Fix:** include both stream orders in the zero-gap overtake cell, always scoring `hi` landing first. Preserve lo-first filtering for positive gaps and keep zero-gap races out of the withdrawal controls.

7. **H1’s verbal claim is stronger than its registered test.**

   **Evidence:** `docs/PREREGISTRATION-2.md:78–79,87–91`; `analysis/itb_analysis/study2.py:44–47,129–132`.

   “Does not reorder” is not established by O(2) < 0.5. With **7 overtakes in 35 races**, H1 is supported even under the worst Holm multiplier of six: adjusted p ≤ **0.001525**. Yet overtaking occurred in 20% of the observed races.

   **Fix:** change the hypothesis statements, including the manifest’s generated statements, to “hi overtakes a 2 ms send-side head start in fewer than half of complete pairs.” If the intended claim is negligible reordering, freeze a meaningful nonzero tolerance and the corresponding test instead.

## Verification and limits

Ran `.venv/Scripts/python.exe -B -m pytest analysis/tests/test_study2.py -q -p no:cacheprovider` with a temporary base directory: **9 passed**. Independently reproduced findings 1, 4 and 6 in memory. Inspected the generated design: no repeated Δt cell within any R window; all nominal race starts are +5 ms and endpoints are at most +55 ms.

The one-sided tails, frozen-group filters, race-versus-equal-key success coding, censored coding, Holm inclusion of p = 1, and complete-case worst-case bound at α/6 match the stated procedure. This does not establish independence across successive windows; it remains an assumption. Rust, localnet, mainnet execution and the full OC rerun were not performed. This review wrote only this report in the project.
