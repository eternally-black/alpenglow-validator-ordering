# Pre-registration 3 — Inside the Block, Study 3: does the reward enter the key?

> **Status: to be frozen before the first Study 3 probe.** This document is the **normative** analysis plan for
> Study 3. PREREGISTRATION.md and PREREGISTRATION-2.md stay normative for Studies 1 and 2. The rationale is in
> [STUDY3-PLAN.md](STUDY3-PLAN.md).
>
> On freezing:
> - `scripts/freeze.py --study 3` writes `design/campaign-study3.json`: the Study 1 fields, plus the hypotheses of §4
>   with their planned n, the carried-over cost of Studies 1 and 2, and `analysis_tree` (the git tree of `analysis/`
>   at the freeze commit);
> - the SHA-256 of this file, of `design/design-study3.jsonl` and of the manifest are posted in a mainnet Memo signed
>   by the Study 3 measurement wallet;
> - any later change is a deviation, reported in REPORT.md with its reason.
>
> **Frozen inputs.**
> - **Targets:** `design/targets-study3.json`: the six core targets of Studies 1 and 2, in the same frozen groups.
> - **Design:** `design/design-study3.jsonl`, written by `itb design --study 3 --seed 20261026`: 192 windows,
>   32 per target, worst-case fees 5,952,000 lamports.
> - **Execution parameters (as in Studies 1 and 2):** `--anchor-event first-shred`, `--max-lateness-ms 100`,
>   `--concurrency 2`, `--obs-lag-ms 0`.
>   - budget `study3`, capped at 6,500,000 lamports;
>   - ledger `state/ledger-study3.sqlite` under the compiled 0.05 SOL cap, holding the 42,926,000 lamports that
>     Studies 1 and 2 cost as a carry-over, so the three studies together cannot pass 0.05 SOL;
>   - `--not-after 2026-11-03T23:59:00Z`.
> - **Implementation:** `analysis/itb_analysis/study3.py` (§3–§8) and `itb run` (§7).
>
> Study 3 data never enter a Study 1 or Study 2 estimate. Runs are selected by manifest: budget, design hash, freeze
> time and cutoff. The identification verdict (§5) reads the committed Study 1 and Study 2 claims; it does not
> recompute them.

## 1. The question

Studies 1 and 2 rejected CU price, lamport fee, arrival order (FIFO) and "no rule" for all six core targets, twice.
Every contrast they ran, though, ranks our probes by *requested cost* exactly as reward ÷ (cost + 1) does. A rule
that orders by requested cost alone, cheapest first, would have produced the same data (REPORT §9).

Study 3 asks one question per target: **does the reward enter the ordering key?**

## 2. Probes and contrasts

| Probe | CU limit L | CU price (µlamports) | Data limit D | Cost | Reward | Agave priority |
|---|---|---|---|---|---|---|
| A | 1,000 | 1,000,000 | 32 KiB | 2,335 | 3,500 | 1,498,287 |
| Y | 3,000 | 2,000,000 | 32 KiB | 4,335 | 8,500 | 1,960,332 |
| hi | 1,000 | 3,000,000 | 32 KiB | 2,335 | 5,500 | 2,354,452 |

Cost and priority follow the Agave cost model and priority formula (`probe.rs`, golden-tested; `scripts/contrasts.py`).
Reward is the priority fee plus the unburned half of the 5,000-lamport signature fee.

| Contrast (x vs y) | CU price | Lamport fee | Reward ÷ cost | **Cost alone** | FIFO / random |
|---|---|---|---|---|---|
| **C4**: Y vs A | x | x | x | **y** | tie |
| **C5**: hi vs A | x | x | x | **tie** | tie |

- **C4 decides the question.** Y costs more than A, but pays more per cost unit. Reward ÷ cost puts Y first; cost alone
  puts A first.
- **C5 confirms it at equal cost.** The two probes cost the same, so cost alone has no preference; reward ÷ cost puts
  the higher reward first.
- CU price and lamport fee predict x on both contrasts. Studies 1 and 2 rejected both on C2 and C3 for every core
  target, so Study 3 does not need to separate them again.

## 3. Unit, eligibility, estimand

- **Unit: one window.** Each window carries one C4 and one C5 pair, each on its own lock. Send order is balanced per
  contrast, and the pair order inside the burst is shuffled.
- **Regime:**
  - direct ingress sends buffered, at −150 ms, so both members are meant to be pending at slot start;
  - shared ingress (BAM, Harmonic) sends inside the window, at a uniform offset of 40–500 ms clear of the measured
    slot boundaries (198 ms).
- **Eligibility:** PREREGISTRATION.md §2 (a)–(e), verbatim.
- **Groups:** each target's frozen (client, ingress) group is confirmatory. Windows of the same target in any other
  group are exploratory.
- **Estimand:** L_C = P(x lands before y), over evaluable windows where both members landed (complete case).
  "Lands before" is the order (slot, index in block) over the targeted window, for verified landings only.

## 4. Hypotheses: the confirmatory family of twelve

For each of the six core targets t:
- **H4-t:** L_C4 > 0.5 (Y before A);
- **H5-t:** L_C5 > 0.5 (hi before A).

**Inference.**
- **Test:** one-sided exact binomial test against 0.5.
- **Multiplicity:** Holm over all twelve at family α = 0.05. A hypothesis with no informative pair is not evaluable
  and enters Holm with p = 1.
- **Decision:** supported when the Holm-adjusted p-value is below α, otherwise not supported. Not supported is not
  evidence for the other direction; its estimate and exact 95 % interval are reported.
- **Selection bound:** every pair of the hypothesis' contrast in evaluable windows with fewer than two members landed
  counts against it. A supported hypothesis is selection-robust if that worst case still gives p < 0.05/12.
  Otherwise it is published with "(assumes selection)".

## 5. Identification verdict, per core target

| Study 3 result | Verdict |
|---|---|
| H4 and H5 published as supported, and the target's Study 1 and Study 2 published claims are `reward_cost` | **reward ÷ (cost + 1) identified**, among all registered candidates: CU price, lamport fee, cost alone, FIFO, random |
| H4 supported, H5 not | Cost alone rejected; the equal-cost reward effect is not shown |
| H4 not supported | The reward term is not shown, and cost alone is not rejected. If L_C4 < 0.5 with its whole exact interval below 0.5, the report says that the order follows cost against reward |

## 6. Positive controls (gate)

The frozen direct-ingress Agave (`7QQGNm3p`) and Firedancer (`EvnRmnMr`) targets are positive controls: their public
code orders by reward ÷ cost. If either does not end with both H4 and H5 supported, the method check has failed.
Every other target's claims are then withdrawn ("method check failed"); the controls' own results are reported as
they are.

## 7. Stopping

Every one of the 32 plans per target is executed in design order. There is no data-dependent stopping. A target stops
when any of these happens:
- its plans run out;
- the ledger's headroom falls below one window's worst-case fee;
- the cutoff passes.

## 8. Pre-specified sensitivity analyses (all emitted by `study3.py`)

1. **Censored coding:** a member that did not land is placed after one that did.
2. **Including transition-ambiguous windows.**
3. **Same slot:** complete pairs whose two members landed in the same slot.

## 9. Exploratory

- Send order per contrast: the first-sent member's share of landing first, descriptive.
- Landing rate per label.

## 10. What Study 3 will not separate

- **Variants of the reward:** priority fee alone, or with the unburned part of the signature fee. With one signature
  per probe, both rank our probes the same way.
- **Requested vs consumed compute in the cost.** Every probe consumes 600 CU. Study 1's C3 showed that the requested
  loaded-data limit counts, so the cost is a requested cost, but Study 3 does not test that again.
- **Mechanism:** we see final block order, not the scheduler's queue.

## Deviations

(none yet; filled in REPORT.md after freezing)
