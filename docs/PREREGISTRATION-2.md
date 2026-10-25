# Pre-registration 2 — Inside the Block, Study 2

> **Status: to be frozen before the first Study 2 probe.** This document is the **normative** analysis plan for
> Study 2. [PREREGISTRATION.md](PREREGISTRATION.md) stays normative for Study 1, and for the Study 2 replication where
> §1 below says so. The rationale is in [STUDY2-PLAN.md](STUDY2-PLAN.md).
>
> On freezing:
> - `scripts/freeze.py --study 2` writes `design/campaign-study2.json`. Besides the Study 1 fields, it holds the
>   hypotheses of §3, the carried-over Study 1 cost, and `analysis_tree`, the git tree id of `analysis/` at the freeze
>   commit. So the code that decides the hypotheses is fixed too: `git rev-parse <commit>:analysis` must equal it;
>
> - the SHA-256 of this file, of `design/design-study2.jsonl` and of the manifest are posted on Solana mainnet in a
>   Memo signed by the Study 2 measurement wallet;
> - the Memo signature is added to the README. Any later change is listed under "Deviations" in REPORT.md, with its
>   reason.
>
> **Frozen inputs.**
> - **Targets:** `design/targets-study2.json`: the six Study 1 core targets, each with the same frozen
>   (client, ingress) group, and Firedancer `9eGrDohd…` as an extended target for equal-key windows only.
> - **Design:** `design/design-study2.jsonl`, written by `itb design --study 2 --seed 20261025`: 570 windows, worst-case
>   fees 22,800,000 lamports (0.0228 SOL).
> - **Execution parameters (as in Study 1):** `--anchor-event first-shred`, `--max-lateness-ms 100`, `--concurrency 2`
>   (windows preparing and sending at once; outcome collection no longer holds a slot), `--obs-lag-ms 0`.
>   - budget `study2`, capped at 23,500,000 lamports;
>   - ledger `state/ledger-study2.sqlite` under the compiled 0.05 SOL cap, holding Study 1's 24,717,500 lamports as a
>     carry-over, so the two studies together cannot pass 0.05 SOL;
>   - `--not-after 2026-10-30T23:59:00Z`.
> - **Implementation:**
>   - `analysis/itb_analysis/study2.py` (§2–§8);
>   - `report.py` with the Study 2 manifest (§1);
>   - `itb run` (§5).
>
> Study 2 data never enter a Study 1 estimate, and Study 1 data never enter a Study 2 estimate. Runs are selected by
> manifest: budget, design hash, freeze time and cutoff.

## 1. Hypothesis R: replication of Study 1

- PREREGISTRATION.md §1–§6 and §9 apply **unchanged** to Study 2's stage-1 K windows, with the Study 2 manifest,
  design and budget:
  - the same estimands and eligibility;
  - the same 36-effect family and decision rules;
  - the same verdicts, gates and published claims.
- Study 2's K kit carries C1, C2 and C3 only, so the uncontended-C2 item of the Study 1 §7 does not arise.
- §5 stopping applies with **at most 56 plans per core target** (Study 1: 80) and the Study 2 cutoff.
- **Replication criterion, per core target:** the Study 2 published claim equals the Study 1 published claim (for all
  six: `reward_cost`). Each target is reported as replicated or not replicated, with both claims side by side. Windows
  of the two studies are never pooled.

## 2. Unit, eligibility, estimands (H1–H3)

- **Unit: one window.**
  - An R window carries at most one race per Δt cell: the generator deals the races so, and its tests check it. It
    also carries at most one equal-key pair.
  - An E window carries one equal-key pair.
  - So within a cell every observation comes from a different window, and windows are treated as independent, as in
    Study 1.
- **Eligibility:** PREREGISTRATION.md §2 (a)–(e), verbatim, for R and E windows.
- **Groups:** a window belongs to the (client, ingress) group it showed. A hypothesis' frozen groups (manifest) are
  confirmatory. Windows of the same target in any other group are exploratory.
- **"Lands before"** is the order (slot, index in block) over the targeted window, for verified landings only (as in
  Study 1).
- **Race estimand:** O_g(Δt) = P(`hi` lands before `lo` | `lo` was sent Δt ms earlier).
  - `hi`: 3,000,000 µlamports/CU, 32 KiB data limit. `lo`: 1,000,000 µlamports/CU, 64 MiB data limit.
  - `hi` outranks `lo` under every candidate key (CU price, fee, reward/cost), so O measures only how far a client
    reorders against arrival.
  - Races start 5 ms after the observed first shred of the target's first slot.
  - The primary estimate uses the races of the cell where both members landed (complete case).
  - Races with `hi` sent first are controls (§8), not part of O.
- **Equal-key estimand:** E_g(Δt) = P(first-sent member lands first), for two identical A probes Δt ms apart, both
  pending at slot start (direct ingress: −150 ms), both landed.

## 3. Hypotheses: the confirmatory family of six

Each hypothesis is fixed in the manifest together with its frozen groups:

| ID | Hypothesis | Estimand | Direction | Basis in Study 1 |
|---|---|---|---|---|
| `H1-agave` | Agave `7QQGNm3p` does not reorder against a 2 ms head start | O(2 ms) | < 0.5 | 0/7 overtakes at 5 ms; streaming windows arrival-driven |
| `H1-jito` | Jito-Solana `HEL1USMZ` does not either | O(2 ms) | < 0.5 | 0/3 at 5 ms |
| `H2-firedancer` | Firedancer `EvnRmnMr` reorders against a 2 ms head start | O(2 ms) | > 0.5 | 5/7 at 5 ms (with `9eGrDohd`) |
| `H2-firedancer-harmonic` | Firedancer + Harmonic `JUPiTERr` does | O(2 ms) | > 0.5 | 5/7 at 5 ms |
| `H2-agave-harmonic` | Agave + Harmonic `Fd7btgyS` does | O(2 ms) | > 0.5 | 5/6 at 5 ms |
| `H3-firedancer-ties` | Firedancer breaks equal-priority ties later-arrival-first (`EvnRmnMr` and `9eGrDohd` pooled) | E(10 ms) | < 0.5 | 4/20 at 10 ms (n = 38 < 40) |

## 4. Inference

- **Test:** one-sided exact binomial test against 0.5, in the hypothesis' direction.
- **Multiplicity:** Holm over the six at family α = 0.05. A hypothesis with no informative pair is **not evaluable**
  and enters Holm with p = 1.
- **Decision:** **supported** if the Holm-adjusted p < 0.05, otherwise **not supported**. "Not supported" is not
  evidence for the opposite direction; its estimate and interval are reported.
- **Reported for every hypothesis:**
  - k and n, the estimate, and the exact two-sided 95 % Clopper–Pearson interval;
  - p and the Holm-adjusted p;
  - the published claim (§8).
- **Selection bound:**
  - Every race or pair of the hypothesis' cell in evaluable windows with fewer than two landed members is counted
    against it: as an overtake for `<` hypotheses, as a non-overtake for `>` hypotheses.
  - A supported hypothesis is **selection-robust** if this worst case still gives p < 0.05/6.
  - Otherwise it is published with **"(assumes selection)"**, as in Study 1.

## 5. Stopping and sample size

- **Stage 1 (K):** as §1.
- **Stage 2 (R, E):** every plan is executed in design order. There is no data-dependent stopping. A target stops
  when any of these happens:
  - its plans run out;
  - the ledger headroom falls below one window's worst-case fee;
  - the cutoff passes.
- **Planned informative pairs if every probe lands:**
  - H1 and H2: 35 races with a 2 ms head start per group;
  - H3: 59 equal-key pairs, from 35 `EvnRmnMr` R windows and 24 `9eGrDohd` E windows.
- **Operating characteristics:** [POWER-2.md](POWER-2.md). The frozen design is simulated at 90 % landing with
  Study 1's observation failures, under schedulers with known horizons, and analysed by this module.

## 6. Pre-specified sensitivity analyses (all emitted by `study2.py`)

1. **Censored coding:** a member that did not land is placed after one that did. Pairs with at least one landed
   member count.
2. **Including transition-ambiguous windows.**
3. **Achieved gap:** races whose measured gap between the two streams' finish times is within 0.5 ms of the nominal
   Δt (all Δt = 0 races and equal-key pairs kept). The median achieved gap per cell is reported in every case.

## 7. Exploratory (labelled as such everywhere)

- The full curve O_g(Δt), Δt ∈ {0, 2, 5, 10, 25, 50} ms, for every observed group, with exact intervals.
- The horizon bracket: the last Δt with O ≥ 0.5 and the next Δt with data.
- O_g(0), simultaneous sends, both stream orders. It re-measures Study 1's streaming effect with a pair on which every
  key agrees.
- Equal-key order in Agave and Jito-Solana (FIFO predicts ≈ 1).
- Agave + BAM `DRpbCBMx`: no Study 1 prediction, so outside the family.
- Study 1 vs Study 2 races at the shared Δt (5, 25 ms), descriptive.

## 8. What would change our mind (implemented as gates)

| Observation | Conclusion |
|---|---|
| A positive control fails in the replication (PREREGISTRATION.md §9) | As in Study 1: the replication's other claims are withdrawn. H1–H3 are reported with the note "method check failed in the replication" |
| `hi`, sent first, loses to `lo` more than once among a race hypothesis' groups (both landed) | The pair did not compete on priority as designed: the hypothesis is **withdrawn** |
| The median achieved gap of a race hypothesis' cell differs from the nominal 2 ms by more than 1 ms | Published with the achieved gap. The claim is about the gap actually sent |

## Deviations

(none yet; filled in REPORT.md after freezing)
