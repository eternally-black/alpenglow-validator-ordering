# Final publication review — 2026-10-26

**Verdict: fix BLOCKER 1 before publishing.** The numerical analysis reproduces, but the exact-comparator headline exceeds what the design identifies.

Read all requested documents and relevant collection, inference, verification and reproduction code. Reconciled concurrent editorial changes through commit `06779083635b056d04667413c50ca6cde9fa08b2`; findings below concern that snapshot. Independently reproduced both results JSON files and every figure using the existing Python environment; the pinned Study 2 analysis tree also reproduced its results. All six frozen-file SHA-256 values match CAMPAIGN-LOG. Docker engine access was denied here, so container execution remains unverified. No fresh mainnet verification or full-history secrets scan was performed. This review modified only this file.

## BLOCKER

1. **The exact reward/cost comparator is not identified.** `README.md:10`, §1 contrast library; `REPORT.md:7,93–94`; `scripts/contrasts.py:21–40`. A scheduler sorting solely by **ascending requested cost** predicts exactly the same winners: A costs 2,335, B 4,335, A′ 18,711; therefore C1=A, C2=B, C3=A. The race pair also agrees: hi costs 2,335 versus lo's 18,711. Thus even perfect results cannot distinguish reward/cost from cost alone, or establish the reward numerator. **Fix:** describe the result as consistent with Agave priority among the preregistered candidates, explicitly naming cost-only as an unresolved alternative. Identifying the formula requires additional contrasts where those comparators disagree; any new measurement needs its own registration.

## SHOULD-FIX

2. **The headline still does not label the extended findings exploratory.** `README.md:10`; `REPORT.md:6–12`, versus its table at `88–91` and `PREREGISTRATION.md:105,142`. The revised headline now retains selection and partial qualifiers, but “all 10” combines six confirmatory targets with four exploratory targets without that distinction. **Fix:** lead with the six core targets and their six-target replication; explicitly label the other four exploratory, retaining the existing partial and selection qualifications.

3. **The censored sensitivity description is factually false.** `REPORT.md:144–145` says estimates are identical and no evaluable pair had exactly one landing. In `data/derived/results.json`, Firedancer `EvnRmnMr` C3 changes from **40/40 to 40/41**, and `JUPiTERr` C2 from **0/40 to 2/43**, under `sensitivity.censored`. The inclusion counts imply four single-landed pairs across these cells. **Fix:** report the changed estimates and distinguish unchanged conclusions from unchanged estimates; show the relevant inclusion denominators and intervals.

4. **Failure to detect send-order effects becomes proof that arrival does not matter.** `README.md:10`; `REPORT.md:11,93–98`; `docs/CAMPAIGN-LOG.md:130`. Every core reward/cost send-order prediction is **undetermined**, in both studies' results, rather than equivalence-confirmed. The implemented distinction between SUPPORTED and CONFIRMED is explicit in `stats.py:91–119`. Intervals containing 0.5 and p=1 do not establish absence of an effect. **Fix:** say the pooled contrasts reject pure FIFO as a complete explanation; state that send-order equivalence was not established. Keep the descriptive regime split and its small samples visible.

5. **Several displayed denominators are wrong.** `REPORT.md:128` gives Firedancer's buffered contrasts one n=32, but the JSON has **32/32/31**. `REPORT.md:273` gives Study 2 Firedancer streaming n=14, but its three denominators are **14/10/12**. These differences matter precisely because inclusion varies across contrasts. **Fix:** print per-contrast denominators from the results objects, including in regime tables, instead of applying one cell's n to an entire row.

6. **Small nonzero p-values are published as zero.** `data/derived/study2/summary.md:18–21` and the corresponding results JSON contain zero p-values because `report.py:37–45` rounds every float to six decimals. For example, 31/31 has exact one-sided p≈4.66×10⁻¹⁰ and Holm p≈2.33×10⁻⁹. REPORT §6.2 correctly uses a bound. **Fix:** preserve scientific precision in published numerical artifacts or show an explicit bound. Document any serialization correction while preserving the frozen analysis and its provenance.

7. **Sender observations become unobserved arrival and builder mechanisms.** `README.md:92` guarantees coexistence in the queue; REPORT §§3, 5 “Spill-over,” and 6.4 describe actual arrivals, buffering and holding behavior. The records establish send times relative to the observer's first-shred event, not scheduler arrival or the location of buffering. The limitations in REPORT §9 are better calibrated. Moreover, `README.md:93` says shared ingress forwards pre-window probes to the current leader, whereas REPORT's spill-over result observes 28/29 in the target window and none with the previous leader. **Fix:** use send-side gaps and buffering proxies consistently; describe mechanisms as possibilities, and update the contradicted streaming-design rationale.

8. **The new inclusion paragraph asserts equality that the data contradict.** `REPORT.md:102–105` says the two members landed “at the same rate” and landing “did not depend on its label.” Firedancer C3 is **40/41 versus 41/41**; Jupiter C2 is **42/43 versus 41/43** (`results.json`, respective `inclusion` objects). McNemar p=1 establishes neither equality nor label-independent selection; the preregistration explicitly gives a balanced-selection counterexample (§1). **Fix:** report “no significant marginal inclusion asymmetry detected,” with intervals. Clarify that selection robustness bounds incomplete pairs inside evaluable windows, not excluded sending failures. Also change `README.md:107` from analyzed “covariates” to archived quantities: REPORT §8 now acknowledges the omitted fullness/position analyses.

9. **Exploratory horizon brackets hide sampling uncertainty.** `PREREGISTRATION-2.md:154–156` promises exact intervals and non-monotonicity labels. REPORT §6.3 and `study2/summary.md:35–43` give counts and brackets without intervals; the generated summary also omits BAM's non-monotonicity warning, although REPORT includes it. `study2.py:199–206` brackets the last observed proportion ≥0.5, not an uncertainty interval for a true horizon. **Fix:** provide per-cell exact intervals and label brackets as descriptive grid crossings. Preserve non-monotonicity warnings in generated summaries and keep these findings explicitly exploratory in the README headline.

10. **“Every number” overstates the reproduction command's coverage.** `README.md:123`; REPORT introduction and §10; `cli.py:72–102`. The command compares the two statistical results files and figures. It does not regenerate the operating-characteristic simulations, check all Markdown tables, or reconstruct the expense account. The ledgers cited in REPORT §11 are under ignored `state/`. **Fix:** describe exactly what the command verifies. Supply a public fee/accounting export with transaction signatures and adjustments if the complete cost reconciliation is meant to be independently reproduced offline. The final arithmetic, 24,717,500 + 18,208,500 = 42,926,000 lamports, is consistent.

11. **GitHub readers cannot open the explorer directly from its link.** `README.md:17`, REPORT §10. The revised embedded-data HTML fixes opening from a clone, but the relative GitHub link still opens repository HTML source, rather than a running page. The introductory table also remains dense despite the new bullets. **Fix:** link a hosted explorer or explicitly instruct readers to download/open the embedded HTML. Keep a short result and reproduce command above the long provenance rows.

## NIT

12. **The weekday replication rationale was not realized.** `STUDY2-PLAN.md:9,92` promises a weekday/Monday replication; the actual measurement was **Sunday, October 25** (`REPORT.md:43–44`). **Fix:** record the scheduling change and retain the defensible claim of replication on a second day. Do not imply weekday coverage.

13. **POWER-2 attributes pilot landing rates to Study 1.** `POWER-2.md:64–65` says sent probes landed at 100% for 8/10 validators. The cited 8/10 statistic belongs to the pilots (`CAMPAIGN-LOG.md:86–87`). Study 1 Stage 1 outcomes show **5/10** targets with no expired sent probes. **Fix:** identify the pilot explicitly or replace the statistic with the campaign result.

## Brief coverage and evidence findability

| Requirement | Assessment and evidence |
|---|---|
| Mainnet only; no pre/post mixing | Met for the four study runs: recorded mainnet genesis, post-upgrade slots, collection/analysis filters. `run_start.json`, `alpenglow.rs`, `outcomes.py`. |
| ≥6 validators; ≥3 client/fork types | Six core plus four extended targets; Agave, Jito-Solana and Firedancer are represented. Per-window attribution is archived; the new README target/version index improves findability. |
| Fee cap; explicit live flag; dry-run default | Implemented in `auth.rs:20–48`, `ledger.rs`, `campaign.rs` and CLI defaults. Cumulative Study 2 carry-over is recorded. Final reported spend is below 0.05 SOL. |
| Keys via volume/env | Compose mounts keys separately; `.env`, `keys/` and `keys-study2/` are untracked. This is not a history-wide secrets certification. |
| Own transactions; raw signatures and slots | Present in probes, sends, outcomes and archived blocks; verifier and published archive/chain-sample records are easy to locate. |
| One-command Compose reproduction | Configured with offline default and no keys; underlying Python reproduction passed. Docker execution was inaccessible here; see finding 10 for scope. |
| README rationale, considerations, unseparated factors | Present in §§2–3; findings 1, 4, 7–8 require corrections or clearer limits. |
| Measurement dates; “what went wrong” | Present in REPORT §§1 and 7 and CAMPAIGN-LOG; correct the scheduling discrepancy above. |
| Public repository submission | Publication/access and actual bounty submission remain outside this local prepublication review. |
