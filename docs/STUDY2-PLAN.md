# Study 2 — plan (approved 2026-10-25; normative text: [PREREGISTRATION-2.md](PREREGISTRATION-2.md))

Study 1 (2026-10-24, [REPORT.md](../REPORT.md)) answered the brief's three questions for 10 validator groups. It left
four things open, and Study 2 is built to close exactly those, with a second pre-registration and a second mainnet
Memo before any Study 2 probe is sent:

| Open after Study 1 | Why it matters | Study 2 answer |
|---|---|---|
| One day, one session | A single day cannot separate the rule from that day's conditions (load, relayer configuration) | **Replication**: the Study 1 confirmatory procedure, unchanged, on a weekday |
| Agave family in streaming windows: n = 5–11 per group | The most interesting result (no priority order for transactions arriving during the slot) rests on 25 windows | **Race curve** with simultaneous and staggered arrivals inside the slot, 35 races (one per window) in the cell that matters |
| Reordering horizons from 1–7 races per cell | "Agave < 5 ms, Firedancer 5–25 ms, Harmonic 25–60 ms" is suggestive, not established | **Fine Δt grid** 0, 2, 5, 10, 25, 50 ms; two pre-registered directional hypotheses |
| Firedancer equal-key tie-break: n = 38 (< 40 pre-registered) | Firedancer's code predicts later-arrival-first; Study 1 saw it at 10 ms but could not claim it | **Confirmatory test** with ≈ 60 pairs |

Study 1 data and conclusions are not touched: Study 2 runs carry their own budget name and manifest, and every Study 1
number reproduces exactly as before.

## 1. Hypotheses (confirmatory)

Estimand for races: **O_g(Δt) = P(hi lands before lo | lo was sent Δt ms earlier)**, over race pairs in evaluable
windows where both landed. `hi` outranks `lo` under every candidate key (CU price, fee, reward/cost), so O measures
only how far a client reorders against arrival.

| ID | Hypothesis | Basis in Study 1 | Test |
|---|---|---|---|
| **R** | The Study 1 confirmatory result replicates: same 6 core targets, same K kit, same analysis code, same 36-effect family | all 6 claims reward/cost | Identical to Study 1 (PREREGISTRATION §1–§9) |
| **H1** | In the Agave family, `hi` overtakes a 2 ms send-side head start in fewer than half of the races: O(2) < 0.5 for Agave `7QQGNm3p` and Jito-Solana `HEL1USMZ` | 0/10 overtakes at 5 ms; streaming windows look arrival-driven | one-sided exact binomial |
| **H2** | In Firedancer and the Harmonic builders, it does so in more than half: O(2) > 0.5 for Firedancer `EvnRmnMr`, Firedancer + Harmonic `JUPiTERr`, Agave + Harmonic `Fd7btgyS` | 5/7, 5/7, 5/6 overtakes at 5 ms | one-sided exact binomial |
| **H3** | Of two identical buffered probes sent 10 ms apart, Firedancer lands the later-sent one first in more than half of the pairs: P(first-sent lands first) < 0.5, pooled over `EvnRmnMr` and `9eGrDohd` (a later-*arrival* tie-break, if the network keeps the send order) | 4/20 at 10 ms | one-sided exact binomial |

H1–H3 are six tests, Holm-adjusted at family α = 0.05. R keeps its own Bonferroni family exactly as in Study 1.
Planned power (exact, at the Bonferroni worst case α = 0.05/6): H1 ≥ 0.84 if the true O(2) ≤ 0.15; H2 ≥ 0.90 if
O(2) ≥ 0.85, 0.62 if 0.75; H3 0.99 if the true rate is 0.2, 0.70 if 0.3.

**Exploratory, pre-specified estimands:** the full curve O_g(Δt) for each group with exact intervals; the horizon
(Δt where O crosses 0.5, bracketed by grid points); O_g(0) (simultaneous sends), which re-measures the Study 1
streaming effect with a pair on which every key agrees; Agave-family equal-key order (FIFO predicts ≈ 1);
Agave + BAM `DRpbCBMx` (no Study 1 prediction, so not in the confirmatory family).

## 2. Design

| Stage | Kit | Targets | Per window | Windows per target |
|---|---|---|---|---|
| 1 | **K** (Study 1 kit without the exploratory uncontended pair) | 6 core: Agave, Jito-Solana, Firedancer, Agave + BAM, Agave + Harmonic, Firedancer + Harmonic | C1, C2, C3 pairs; direct ingress 3 buffered : 1 streaming | stop at 40 informative pairs per contrast, ≤ 56 plans |
| 2 | **R** (race curve) | Agave, Jito-Solana, Firedancer `EvnRmnMr`, Agave + BAM, Agave + Harmonic, Firedancer + Harmonic | 3 hi/lo races starting 5 ms after the first shred; direct ingress also 1 equal-key pair (buffered, 10 ms apart) | 35 |
| 2 | **E** (equal key) | Firedancer `9eGrDohd` | 1 equal-key pair, buffered, 10 ms apart | 24 |

Race allocation per R target (105 races, balanced and shuffled across its 35 windows):

| Δt (ms) | 0 | 2 | 5 | 10 | 25 | 50 |
|---|---|---|---|---|---|---|
| lo sent first (head start) | 6 + 6 (simultaneous, order balanced) | **35** | 15 | 12 | 12 | 13 |
| hi sent first (control) | — | — | 3 | — | 3 | — |

Each window carries a Δt cell at most once (the races are dealt over the windows), so the window stays the unit of
analysis, as in Study 1; for the same reason an E window carries one equal-key pair. The longest race ends 55 ms
after the first shred, nominally inside the ≈ 130 ms in-window slot (same-slot pairs are a sensitivity analysis). Randomisation, seeds, locks
and payer assignment work exactly as in Study 1 (`design.rs`): the design is generated from a committed seed and
frozen before the Memo.

## 3. Budget: one cap over both studies, enforced in code

- Study 2 uses a **new ledger** (`state/ledger-study2.sqlite`) opened with the **compiled 0.05 SOL cap**. Before
  anything else, Study 1's measured total cost, **24,717,500 lamports** (CAMPAIGN-LOG: 0.1 SOL + 13,023 deposits −
  75,295,523 returned), is recorded in it as a carry-over charge. The ledger then refuses any reservation that would
  take Study 1 + Study 2 past 0.05 SOL. No hand-picked Study 2 cap is involved.
- Budgets inside that ledger: `setup` 1,000,000 (funding, top-up, sweep, Memo); `study2` 23,500,000.
- Worst case if every planned probe is sent: K 12.4M + R 8.8M + equal key 1.6M = 22.8M lamports. Probes that are
  never sent cost nothing; expired ones are charged at full fee, as in Study 1.
- Wallet: new master `6hoQGYN4…dp4q`, 24 fresh payers, funded from 0.06 SOL. Payers are topped up between the stages;
  everything left returns to the funder at the end.

## 4. Tool changes before Study 2 (behaviour-preserving for Study 1)

1. **Send concurrency.** A window now releases its concurrency slot when its last probe is sent, not after outcome
   collection. In Study 1 a window waiting for a slot held by another window's collection started too late
   (about half of `DRpbCBMx`'s streaming windows were "late"). Collection still runs to completion; payers stay leased
   until their outcomes are terminal.
2. **Ledger carry-over:** `itb ledger --carry-over-lamports N --carry-over-reason TEXT`, allowed once, on a ledger
   with no reservations.
3. **Generator:** `itb design --study 2` adds the R and E kits; the Study 1 generator is untouched, so
   `design/design.jsonl` still regenerates byte for byte from its seed.
4. **Analysis:** Study 2 module for H1–H3 and the curves; run selection by manifest and budget, so Study 1 and
   Study 2 runs never mix. Figures gain the race curve with the fine grid.

Gate before freezing: Rust and Python tests, the localnet end-to-end run, and a mainnet dry run of the Study 2 design.

## 5. Schedule

| When (UTC) | What |
|---|---|
| 2026-10-25 | Tool changes, tests, localnet e2e; pre-registration 2 and design frozen; Memo on mainnet |
| 2026-10-26 (Mon) | Setup (payers, funding), Stage 1 then Stage 2, one session |
| `not_after` 2026-10-30T23:59Z | Pre-registered cutoff; anything later is not Study 2 |
| by 2026-11-01 | REPORT with both studies, figures, verification of every Study 2 landing |

## 6. What Study 2 will still not separate

- Arrival at the leader vs our send time: Δt is a send-side gap. A 2 ms gap can shrink or grow on the network;
  O(Δt) is a send-side curve, and every send timestamp is published.
- One location (our sender), one sender identity (unstaked).
- The scheduler's internal batching from a smooth curve: we report horizons, not batch periods.
