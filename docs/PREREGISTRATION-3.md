# Pre-registration 3 — Inside the Block, Study 3: does the reward enter the key?

> **Status: to be frozen before the first Study 3 probe.** This document is the **normative** analysis plan for
> Study 3. PREREGISTRATION.md and PREREGISTRATION-2.md stay normative for Studies 1 and 2. The rationale is in
> [STUDY3-PLAN.md](STUDY3-PLAN.md).
>
> On freezing:
> - `scripts/freeze.py --study 3` writes `design/campaign-study3.json`. It holds the Study 1 fields plus:
>   - the hypotheses of §4 with their planned n;
>   - the Study 1 and Study 2 published claims of each core target (`prior_claims`), with the hash and commit of the
>     results files they come from (`prior_claims_source`);
>   - the carried-over cost of Studies 1 and 2;
>   - `analysis_tree`, the git tree of `analysis/` at the freeze commit.
> - The SHA-256 of this file, of `design/design-study3.jsonl` and of the manifest are posted in a mainnet Memo signed
>   by the Study 3 measurement wallet.
> - Any later change is a deviation, reported in REPORT.md with its reason.
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
> - **Implementation:** `analysis/itb_analysis/study3.py` (§3–§9) and `itb run` (§7).
>
> Study 3 data never enter a Study 1 or Study 2 estimate. Runs are selected by manifest: budget, design hash, freeze
> time and cutoff. The identification verdict (§5) reads the Study 1 and Study 2 claims frozen in the manifest; it
> does not recompute them.

## 1. The question

Studies 1 and 2 rejected CU price, lamport fee, arrival order (FIFO) and "no rule" for all six core targets, twice.
Every contrast they ran, though, ranks our probes by *requested cost* exactly as reward ÷ (cost + 1) does. A rule
that orders by requested cost alone would have produced the same data (REPORT §9).

**Cost alone** means ascending requested cost, cheapest first, with requested cost as the Agave cost model computes
it from the transaction's requested limits.

Study 3 asks one question per target: **does the reward enter the ordering key?**

## 2. Probes and contrasts

| Probe | CU limit L | CU price (µlamports) | Data limit D | Cost | Reward | Agave priority |
|---|---|---|---|---|---|---|
| A | 1,000 | 1,000,000 | 32 KiB | 2,335 | 3,500 | 1,498,287 |
| Y | 1,500 | 4,000,000 | 32 KiB | 2,835 | 8,500 | 2,997,179 |
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

**Robust to the reward and cost definitions.** Let b be the share of the signature fee that a client counts as
reward, and c₀ ≥ 0 any per-transaction cost overhead that the two probes share. Y has the higher reward per cost unit
whenever b < 10·c₀ + 9,000. This covers:
- priority fee only (b = 0);
- Agave's reward (b = 2,500);
- the total fee (b = 5,000).

It holds even under a cost model with no overhead at all. With Agave's overhead and the + 1 of its formula
(c₀ = 1,336) the bound is b < 22,360.
At equal cost, C5 puts hi first for every b ≥ 0. A Rust test checks C4 and C5 for b ∈ {0, 2,500, 5,000}
(`probe.rs`, `study3_contrasts_separate_cost_only_from_reward_cost`).

**Ties under cost alone.** C5 is at its null (L = 0.5) under cost alone only if equal-cost ties are broken by
something independent of the label. The design makes that so:
- send order is balanced per contrast;
- the pair order inside a burst is shuffled;
- both members of a pair write the same lock account;
- payers are drawn per window in a seeded random order (the seed is recorded), so neither the payer key nor the
  signature lines up with the label.

A scheduler that breaks equal-cost ties by reward is one where the reward enters the key, and C5 is meant to detect
it (§5, the row "H5 supported, H4 not").

## 3. Unit, eligibility, estimand

- **Unit: one window.** Each window carries one C4 and one C5 pair, each on its own lock. Send order is balanced per
  contrast, and the pair order inside the burst is shuffled.
- **Regime:**
  - direct ingress sends buffered, at −150 ms, so both members are meant to be pending at slot start;
  - shared ingress (BAM, Harmonic) sends inside the window, at a uniform offset of 40–500 ms clear of the measured
    slot boundaries (198 ms).
- **Eligibility:** PREREGISTRATION.md §2 (a)–(e), verbatim.
- **Groups:** each target's frozen (client, ingress) group is confirmatory. Windows of the same target in any other
  group are exploratory (§9).
- **Estimand:** L_C = P(x lands before y), over evaluable windows where both members landed (complete case).
  "Lands before" is the order (slot, index in block) over the targeted window, for verified landings only.

## 4. Hypotheses: the confirmatory family of twelve

For each of the six core targets t:
- **H4-t:** L_C4 > 0.5 (Y before A);
- **H5-t:** L_C5 > 0.5 (hi before A).

**Inference.**
- **Test:** one-sided exact binomial test against 0.5. Its calibration assumes windows are independent: each window
  is a separate leader slot with fresh payers, locks and blockhash.
- **Multiplicity:** Holm over all twelve at family α = 0.05. Holm is valid under any dependence between hypotheses.
- **Decision:** supported when the Holm-adjusted p-value is below α, otherwise not supported. Not supported is not
  evidence for the other direction; its estimate and exact 95 % interval are reported.
- **Not evaluable:** a hypothesis with no informative pair. It enters Holm with p = 1 and counts as not supported in
  §5. Every hypothesis and every §5 row is emitted even when no run is selected.
- **Selection bound:** every pair of the hypothesis' contrast in evaluable windows with fewer than two members landed
  counts against it. A supported hypothesis is selection-robust if that worst case still gives p < 0.05/12.
  Otherwise it is published with "(assumes selection)".

## 5. Identification verdict, per core target

The verdict combines the target's two Study 3 published claims (§4, after the gate of §6) with its Study 1 and Study 2
published claims as frozen in the manifest. It is scoped to the **registered candidates**: CU price, lamport fee, cost
alone, FIFO and random. Rows are checked from top to bottom:

| Result | Verdict |
|---|---|
| Either Study 3 claim withdrawn (§6) | **withdrawn: method check failed** |
| H4 and H5 supported, Study 1 and Study 2 claims both `reward_cost` | **reward ÷ (cost + 1) identified among the registered candidates** |
| H4 and H5 supported, an earlier claim not `reward_cost` | Cost alone rejected and the reward effect shown; the Study 1 / Study 2 claims are stated |
| H4 supported, H5 not | Cost alone rejected; the equal-cost reward effect is not shown |
| H5 supported, H4 not | The equal-cost reward effect is supported; C4 is inconclusive |
| Neither supported | The reward term is not shown; cost alone is not rejected |

**Descriptive notes.** These are not tests.
- In the row "H5 supported, H4 not": if C4's whole exact 95 % interval lies below 0.5, the report adds that the data
  are compatible with ordering by cost first and by reward only between equal costs.
- In the row "neither supported": under the same condition, the report adds that the order follows cost against
  reward.

**The selection qualifier.** A verdict carries "(assumes selection)" when either of the target's Study 3 claims
carries it, or when a positive control passed the gate only under the selection assumption (§6). The results record
two booleans per target:
- `reward_cost_identified`: the identified row, with no qualifier anywhere;
- `reward_cost_identified_assuming_selection`: the identified row, qualifier allowed.

## 6. Positive controls (gate)

The frozen direct-ingress Agave (`7QQGNm3p`) and Firedancer (`EvnRmnMr`) targets are positive controls: their public
code orders by reward ÷ cost.
- **Failed:** either control does not end with both H4 and H5 supported. Every other target's claims are then
  withdrawn ("method check failed"); the controls' own results are reported as they are.
- **Passed conditionally:** both controls have both hypotheses supported, but at least one of those four is supported
  only with "(assumes selection)". Every target's §5 verdict then carries the qualifier.
- **Passed:** otherwise.

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

## 9. Diagnostics (descriptive)

Per target, per observed (client, ingress) group and per contrast:
- windows and evaluable windows;
- landing per label, as numerator and denominator;
- pairs with both members landed;
- send order: the first-sent member's share of landing first.

Rows for a group other than the target's frozen one are marked off-group and exploratory. Beside every published
claim, the report gives the target's evaluable and attempted windows, and the reasons for each exclusion. Those
windows are outside the selection bound, which covers incomplete pairs in evaluable windows only.

## 10. What Study 3 will not separate

- **Keys outside the registered candidates.** An additive key, reward − λ·cost, ranks every registered pair as
  reward ÷ cost does. With λ = 1 it gives A 1,165, Y 5,665, hi 3,165, B −335 and A′ −15,211: Y and hi beat A, and
  A > B > A′ as in Studies 1 and 2. "Identified" therefore means *among the registered candidates*, not among all
  conceivable keys. The operating characteristics show this case ([POWER-3.md](POWER-3.md), scenario `additive`).
- **Change over time.** The verdict combines three studies run on different days. It assumes each target's key did
  not change between them.
- **Variants of the reward:** priority fee alone, with half or with all of the signature fee. With one signature per
  probe, all of them rank our probes the same way (§2).
- **Requested vs consumed compute in the cost.** Every probe consumes 600 CU. Study 1's C3 showed that the requested
  loaded-data limit counts, so the cost is a requested cost, but Study 3 does not test that again.
- **Mechanism:** we see final block order, not the scheduler's queue.

## Deviations

(none yet; filled in REPORT.md after freezing)
