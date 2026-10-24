# Inside the Block — report

**Question.** By what rule does each validator order the transactions in its block, how strictly does the rule
hold, and is there a rule at all?

**Answer (post-Alpenglow mainnet, 2026-10-24, our probe transactions).** Every validator group we measured orders our
probes by **Agave's priority, reward ÷ (cost + 1)**: 6 core and 4 extended targets, 8 client types, including BAM
nodes and Harmonic block builders. Neither CU price nor lamport fee, and not arrival order.

- **Cost counts.** The *requested* compute and loaded-data limits enter the cost, so a probe that pays the higher CU
  price but requests a 64 MiB data limit is placed after a cheaper one.
- **Strictness depends on the client and on when the transactions arrive.** Firedancer, BAM and Harmonic follow the
  rule in nearly every window, also for transactions arriving during the slot. The Agave family (Agave, Jito-Solana,
  Rakurai) follows it perfectly for transactions already pending when the slot starts. For transactions arriving
  during its slot, its order no longer follows any of the candidate keys.

Everything here is recomputed from raw data by `docker compose up`, and every landing is checkable on chain
(§7). The analysis was pre-registered before the campaign: hashes in mainnet Memo
[`5vRM47a8…QcyG`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg),
slot 460,779,153.

## 1. When each measurement was taken (all 2026-10-24, UTC, slots ≥ 460,725,000, post-Alpenglow)

| Time (UTC) | What | Data | Role |
|---|---|---|---|
| 05:23 | Live smoke: reachability per ingress kind | `data/smoke/20261024T052311Z-smoke-live-f540` | engineering check |
| 07:18–07:48 | Pilot, stages 1 and 2 (70 windows) | `data/pilot/20261024T0718*`, `…0738*` | calibration, not confirmatory |
| 07:59–08:12 | Second pilot (30 windows), after execution fixes | `data/pilot/20261024T0759*`, `…0804*` | calibration, not confirmatory |
| 08:16:46 | **Pre-registration frozen**; Memo on mainnet | `docs/PREREGISTRATION.md`, `design/` | — |
| 10:31–12:58 | **Campaign Stage 1** (413 windows) | `data/raw/20261024T103156Z-s1-live-916e` | **confirmatory** |
| 13:38–14:53 | Campaign Stage 2 (T, H, S kits; 156 windows) | `data/raw/20261024T133825Z-s2-live-4ab3` | exploratory |

Each step, its cost and its problems are in [docs/CAMPAIGN-LOG.md](docs/CAMPAIGN-LOG.md).

## 2. Confirmatory result (PREREGISTRATION §1–§5)

L_C = P(x lands before y), with exact Clopper–Pearson intervals, Bonferroni-adjusted over the 36-effect family.
Windows are the unit, so n is the number of evaluable windows where both members of the pair landed.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/identification-dark.svg">
  <img src="figures/identification.svg" width="100%" alt="Three panels, one per contrast (C1 A vs B, C2 A-prime vs B, C3 A vs A-prime), ten validator groups each. Priority-label estimates sit near 1, 0 and 1, the pattern only reward divided by cost predicts; send-order estimates sit near 0.5 inside the tie band for every group.">
</picture>


| Validator | Client | Ingress | L_C1 (A before B) | L_C2 (A′ before B) | L_C3 (A before A′) | Published claim | Strictness ≥ | Selection-robust |
|---|---|---|---|---|---|---|---|---|
| `7QQGNm3p` | Agave | direct | 0.90 [0.67, 0.99] n=40 | 0.12 [0.02, 0.36] n=40 | 0.88 [0.64, 0.98] n=40 | **reward_cost** | 0.70 | yes |
| `EvnRmnMr` | Firedancer | direct | 1.00 [0.84, 1.00] n=41 | 0.00 [0.00, 0.16] n=41 | 1.00 [0.83, 1.00] n=40 | **reward_cost** | 0.93 | yes |
| `HEL1USMZ` | Jito-Solana | direct | 0.88 [0.64, 0.98] n=40 | 0.03 [0.00, 0.22] n=40 | 0.93 [0.70, 1.00] n=40 | **reward_cost** | 0.70 | yes |
| `DRpbCBMx` | Agave + BAM | BAM node | 1.00 [0.82, 1.00] n=36 | 0.00 [0.00, 0.18] n=36 | 1.00 [0.82, 1.00] n=36 | **reward_cost** | 0.92 | yes |
| `Fd7btgyS` | Agave + Harmonic | Harmonic remote TPU | 1.00 [0.83, 1.00] n=40 | 0.03 [0.00, 0.22] n=40 | 1.00 [0.83, 1.00] n=40 | **reward_cost** | 0.89 | yes |
| `JUPiTERr` | Firedancer + Harmonic | Harmonic remote TPU | 1.00 [0.84, 1.00] n=43 | 0.00 [0.00, 0.17] n=40 | 1.00 [0.84, 1.00] n=43 | **reward_cost** | 0.93 | yes |
| `9eGrDohd` | Firedancer | direct | 1.00 [0.70, 1.00] n=20 | 0.00 [0.00, 0.30] n=20 | 1.00 [0.70, 1.00] n=20 | exploratory: reward_cost | 0.86 | yes |
| `9jxgosAf` | Firedancer + BAM | BAM node | 1.00 [0.70, 1.00] n=20 | 0.00 [0.00, 0.30] n=20 | 1.00 [0.70, 1.00] n=20 | exploratory: reward_cost | 0.86 | yes |
| `5Cchr1XG` | Agave + BAM | BAM node | 1.00 [0.70, 1.00] n=20 | 0.00 [0.00, 0.30] n=20 | 1.00 [0.70, 1.00] n=20 | exploratory: reward_cost (assumes selection) | 0.86 | no |
| `ana2y2Yv` | Rakurai | direct | 0.90 [0.54, 1.00] n=20 | 0.10 [0.00, 0.46] n=20 | 0.95 [0.61, 1.00] n=20 | exploratory: partial:reward_cost | 0.66 | yes |

- **Prediction pattern.** The pattern (x, y, x) on C1–C3 is the one only reward/cost predicts. CU price predicts
  (x, x, tie) and lamport fee (y, y, tie). Both are rejected for every group. So are FIFO and "no rule", because the
  label effects are far from 0.5 while the send-order effects are not.
- **Send order.** P(first-sent member lands first) lies between 0.40 and 0.63 for every core contrast, and every
  interval contains 0.5. Randomisation p-values over the fixed family of 36 effects, Holm-adjusted: every label effect
  p = 0.00036, the floor for 100,000 draws; every send-order effect p = 1.0.
- **Gates (§9).** Both positive controls, Agave `7QQGNm3p` and Firedancer `EvnRmnMr`, recovered their known rule. No
  buffer or streaming gate fired, and the selection-balance check passed for every contrast (all p ≥ 0.15).
- **Stopping (§5).** Five core targets reached ≥ 40 informative pairs per contrast. `DRpbCBMx` used all 80 of its
  plans and stopped at 36, the pre-registered stop on exhausted plans. Its intervals are correspondingly wider, and
  the claim stands.

## 3. How strictly the rule holds — and when it does not

Strictness is the share of complete windows where *all three* contrasts went reward/cost's way (one-sided 95 %
lower bound). The send regime explains the gap between the two groups (sensitivity §6.4, regime split):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/arrival-dark.svg">
  <img src="figures/arrival.svg" width="100%" alt="One dot per leader window, positioned by when our first probe finished sending relative to the leader's first shred. Agave, Jito-Solana and Rakurai follow reward divided by cost in every window queued before the slot (75 of 75) but in only 8 of 25 windows that arrive during the slot. Firedancer and the BAM and Harmonic builders follow it in 215 of 216 windows either way.">
</picture>


| Group | Buffered windows: probes arrive ≈ 150 ms before the leader's slot | Streaming windows: probes arrive during the window |
|---|---|---|
| Agave `7QQGNm3p` | L = 1.00 / 0.00 / 1.00 (n=31) | L = 0.56 / 0.56 / 0.44 (n=9) |
| Jito-Solana `HEL1USMZ` | 1.00 / 0.00 / 1.00 (n=29) | 0.55 / 0.09 / 0.73 (n=11) |
| Rakurai `ana2y2Yv` | 1.00 / 0.00 / 1.00 (n=15) | 0.60 / 0.40 / 0.80 (n=5) |
| Firedancer `EvnRmnMr` | 1.00 / 0.00 / 1.00 (n=32) | 1.00 / 0.00 / 1.00 (n=9) |
| Firedancer `9eGrDohd` | 1.00 / 0.00 / 1.00 (n=15) | 1.00 / 0.00 / 1.00 (n=5) |
| BAM and Harmonic builders (shared ingress: every window streaming) | — | 1.00 / 0.00–0.03 / 1.00 (n=20–43 per group) |

- **Agave family.** When both members of a pair are already pending as the slot starts, the scheduler picks by
  priority every time. When they arrive 0.05 ms apart during the slot, the order looks unrelated to the label. It is
  also unrelated to the send order: the first-sent member wins between 27 % and 100 % of the time per contrast, all with wide intervals. That is
  consistent with Agave's multi-threaded banking stage, where near-simultaneous arrivals are taken by whichever thread
  is free. We cannot see the internal queue, and the streaming samples are small (n = 5–11), so this part is
  descriptive.
- **Firedancer (pack).** It keeps priority order even for transactions arriving during the slot.
- **Builders.** BAM nodes and Harmonic remote TPUs order by the same reward/cost key, even though they receive
  everything during the window. That fits a builder that collects and sorts before forwarding.

## 4. Sensitivity analyses (PREREGISTRATION §6)

1. **Censored coding.** It gives the same estimates as the primary analysis. No evaluable window had a pair with
   exactly one member landed, so the coding of a non-landed member never comes into play.
2. **Worst-case selection bounds.** Every core claim survives them, so it is selection-robust. `5Cchr1XG` does not:
   4 evaluable windows lost both members, so its claim carries "(assumes selection)".
3. **Session bootstrap.** Not informative: Stage 1 was a single run (one session).
4. **Regime split.** See §3.
5. **Achieved offsets** (C1). In every group, each window whose first send finished before the leader's first slot
   (bins < −100 ms and −100..0 ms) put A before B. The Agave-family exceptions are sends during the slot: the
   0..+100 ms bin, plus one Jito-Solana window above +100 ms.
6. **Including transition-ambiguous windows.** No campaign window was transition-ambiguous, so the analysis is
   identical.

## 5. Exploratory (Stage 2, PREREGISTRATION §7)

All of this section is **exploratory** (PREREGISTRATION §7), descriptive, with plain 95 % Clopper–Pearson
intervals and no multiplicity claims. Full tables: [`data/derived/exploratory_stage2.md`](data/derived/exploratory_stage2.md),
from `scripts/exploratory_stage2.py`. 156 windows, 118 of them evaluable.

**Races: how big a head start can a higher-priority transaction overcome?**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/races-dark.svg">
  <img src="figures/races.svg" width="100%" alt="Four small panels: the share of races in which the higher-priority probe overtook the lower-priority one's head start, against head starts of 5, 25, 60 and 100 ms. Agave family: never (horizon under 5 ms). Firedancer and Firedancer plus Harmonic: about 5 to 25 ms. Agave plus Harmonic: about 25 to 60 ms.">
</picture>

- Each race pairs `hi` (3,000,000 µlamports/CU) against `lo` (1,000,000 µlamports/CU with a 64 MiB data request),
  one sent Δt ms after the other, starting just after the target's first shred. `hi` has the higher priority under
  every candidate key.
- When `hi` is sent first, it lands first in every race, at every Δt and every validator.
- When `lo` gets the head start:

| Group (targets) | Δt = 5 ms | 25 ms | 60 ms | 100 ms | Effective reordering horizon |
|---|---|---|---|---|---|
| Agave (`7QQGNm3p`) | 0/7 | 0/4 | 0/6 | 0/7 | < 5 ms |
| Jito-Solana (`HEL1USMZ`) | 0/3 | 0/7 | 0/5 | 0/5 | < 5 ms |
| Rakurai (`ana2y2Yv`) | 0/1 | 0/2 | 0/1 | 0/3 | < 5 ms (few races) |
| Firedancer, direct (`EvnRmnMr`, `9eGrDohd`) | 5/7 | 2/6 | 0/3 | 0/4 | ≈ 5–25 ms |
| Firedancer + Harmonic (`JUPiTERr`) | 5/7 | 1/6 | 0/4 | 0/6 | ≈ 5–25 ms |
| Agave + Harmonic (`Fd7btgyS`) | 5/6 | 3/4 | 0/5 | 0/4 | ≈ 25–60 ms |
| Agave + BAM (`DRpbCBMx`, `5Cchr1XG`) | 0/1 | 1/4 | 0/1 | 0/5 | too few races |
| Firedancer + BAM (`9jxgosAf`) | 2/2 | – | 2/2 | 0/1 | too few races |

(Cells: races in which `hi` overtook `lo`'s head start.)

- **Agave family:** once a transaction has arrived during the slot, a later one does not overtake it, even 5 ms later.
  That is consistent with the streaming-window result of §3.
- **Firedancer and the Harmonic builders:** they reorder within a short horizon.
- **BAM:** our race samples are too small to say.

**Equal-key order: two identical probes Δt apart.**
- Agave and Rakurai: the first-sent probe landed first in all 20 pairs (FIFO).
- Firedancer direct (`EvnRmnMr`, `9eGrDohd`): the *later* probe tended to land first at Δt = 10 ms (first-sent first
  4/20, CI 0.06–0.44), and not at 40 ms (8/18). The 10 ms result is the later-arrival-first tie-break that Firedancer's code predicts. With 38
  pairs, below the pre-registered threshold of 40, it counts as not identified.
- Harmonic and BAM groups: mostly FIFO (first-sent first 0.50–1.00 per group and Δt, small samples).

**Hold cliff: identical probes sent 7 s, 3 s and 0.5 s before the window.**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/hold-dark.svg">
  <img src="figures/hold.svg" width="100%" alt="Unit chart: probes sent 7, 3 and 0.5 seconds before the target window. Agave and Jito-Solana: all 8 probes sent 7 s early expired, all sent 3 s and 0.5 s early landed. Firedancer: all probes landed, including the 7 s ones.">
</picture>

- Agave and Jito-Solana: every probe sent 7 s early expired (8/8). Those sent 3 s and 0.5 s early landed (21/21).
  Agave drops packets held longer than 20 slots (≈ 4 s at the observed cadence).
- Firedancer: the 7 s probes landed in the target window (4/4). It keeps pending transactions until their blockhash
  expires.
- Both match the predictions from the clients' code, and the pilot.

**Spill-over: pre-window sends to shared ingress.**
- Probes sent 1 s and 150 ms before the target's window to a BAM node (`DRpbCBMx`) or a Harmonic remote TPU
  (`Fd7btgyS`, `JUPiTERr`): 28 of the 29 sent landed in the target window and 1 expired. None landed with the
  previous leader.
- The builders hold a transaction for the leader it was addressed to, rather than passing it to whoever leads at the
  moment.

## 6. What went wrong

- **Connection eviction.** Busy servers evict unstaked QUIC connections from full tables between our pre-connect and
  the send. We first saw this in the smoke test; the worst cases are BAM nodes. Mitigation, before the freeze: the
  connection is re-checked before and after each anchor and re-handshaken when needed. Residual effect: 616 of 3,280
  Stage-1 probes were never sent. They cost nothing and their windows are excluded as `not_all_sent`.
- **`DRpbCBMx` fell short.** About half of its streaming windows were "late". A likely cause is the frozen concurrency
  of 2, which makes a window wait for a slot held by a previous window's outcome collection. It used all 80 plans and
  stopped at 36 informative pairs instead of 40.
- **Spam deposits.** Two strangers sent "dust" (8,505 and 4,518 lamports) to our payers. Reconciliation stayed safe,
  because the balances fell less than the fees charged. Both are recorded as external deposits
  (`scripts/foreign_transfers.py`).
- **Pre-freeze simulation design.** The simulation in POWER.md was first run on a draft design from an older build of
  the generator. It was rerun on the frozen design: same picture within 3 points. The frozen pre-registration quotes
  the draft's illustrative censored-coding figures (50 % / 51 %); the frozen-design figures are 47 % / 48 %.
- **Line endings.** Two files to be hashed had CRLF endings from Windows writes. They were normalised to LF before
  hashing, and `scripts/freeze.py` now refuses CR bytes.
- **Earlier problems** found by the code reviews, the pilots and the localnet tests are listed with their fixes in
  [docs/review/CODE-gate1b-dispositions.md](docs/review/CODE-gate1b-dispositions.md) and
  [docs/CAMPAIGN-LOG.md](docs/CAMPAIGN-LOG.md).

## 7. Deviations from the pre-registration

- **Analysis plan:** none. Estimands, decision rules, family, gates and stopping were applied as frozen.
- **Execution:** none. The frozen design (hash checked at run time) and the frozen parameters were used.
- **Reporting fix after the freeze, no effect on any estimate:** the funnel labels a window that was skipped before
  any send (3 in Stage 1) only by its skip reason. Before the fix it was also labelled `design_mismatch` and so on.

## 8. What this design does not separate

- **Priority fee vs total fee.** With one signature they rank our probes identically.
- **A builder's own sort vs the validator's scheduler behind it.** BAM and Harmonic groups are reported as the
  ingress path we measured.
- **The Agave mechanism for streaming arrivals.** We observe that the label stops mattering, not the internal queue.
- **External validity.** Our probes are tiny, untipped, legacy transactions with one signature, two writable accounts
  and 600 CU executed. Heavier transactions, Jito bundles and tips, v1 transactions and contended accounts were out of
  scope.
- **Staked or SWQoS senders.** We are an unstaked sender. Eviction, landing and timing may differ for staked
  connections.

## 9. Verify and reproduce

```bash
docker compose up --build                       # recompute every number and redraw every figure from data/raw (offline), diff both
docker compose --profile verify up              # re-check a sample of landings against mainnet blocks
sha256sum docs/PREREGISTRATION.md design/design.jsonl design/campaign.json   # = the hashes in the Memo
```

- **Archive check:** all 2,553 Stage-1 landing claims verified, with 26 checks each (signed bytes, signature,
  probe atom, block index, on-chain message, fee, leader, window). The completeness check found no probe in any of the
  1,640 archived window blocks without a matching claim.
- **Chain check:** a random sample of 60 claims verified against mainnet blocks fetched again from the RPC.
  [`data/derived/verify-archive.json`](data/derived/verify-archive.json),
  [`data/derived/verify-chain-sample.json`](data/derived/verify-chain-sample.json).

## 10. Cost

All amounts in lamports, from the spend ledger (`state/ledger.sqlite`). The owned accounts' on-chain balances agree
to the lamport, once the two recorded spam deposits are counted.

| Step | Landed fees | Charged for expired probes | Probes never sent (no fee) |
|---|---|---|---|
| Smoke | 162,000 | 0 | 9 |
| Setup: payer funding (2) and pre-registration Memo | 15,000 | 0 | — |
| Pilots (100 windows) | 3,256,500 | 98,000 | 97 |
| Campaign Stage 1 (413 windows) | 15,797,000 | 686,500 | 616 |
| Campaign Stage 2 (156 windows) | 5,362,000 | 102,000 | 219 |
| Closing: sweep of the 24 payers and return of the remainder to the funder | 125,000 | 0 | — |
| **Total** | **24,717,500 (0.0247 SOL)** | **886,500** | |

The cap was 0.05 SOL, compiled into the binary and enforced by the ledger. The highest charge it ever held was
0.0255 SOL. The wallet received 0.1 SOL, plus 13,023 lamports of spam deposits, and returned 75,295,523 lamports to its funder
([`5j8PEKpj…LA3D`](https://explorer.solana.com/tx/5j8PEKpj5djzEbXGwcqxqdut6HTkMG9h71TV16EoRKfXVfKKq3L1iSGM7AVJv79BjDjvUp5pCVcPUp62d4mJLA3D)). The difference, 24,717,500 lamports, is the whole cost of the measurement.
