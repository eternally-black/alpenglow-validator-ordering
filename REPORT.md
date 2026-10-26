# Inside the Block — report

**Question.** By what rule does each validator order the transactions in its block, how strictly does the rule
hold, and is there a rule at all?

**Answer (post-Alpenglow mainnet, our own probe transactions; two pre-registered studies, 2026-10-24 and
2026-10-25).** Every validator group we measured orders our probes by **Agave's priority, reward ÷ (cost + 1)**.
That covers 6 core and 4 extended targets and 8 client types, including BAM nodes and Harmonic block builders.
- Eight groups follow it outright.
- One extended group carries "(assumes selection)" (`5Cchr1XG`) and one is `partial` (Rakurai, §2). Neither
CU price nor lamport fee explains the order, and neither does arrival order. **On the second day, a separate
pre-registered study replicated the result for all six core targets.**

- **Cost counts.** The *requested* compute and loaded-data limits enter the cost. A probe that pays the higher CU
  price but requests a 64 MiB data limit is placed after a cheaper one.
- **How strictly the rule holds depends on the client and on when the transactions arrive.**
  - Firedancer, BAM and Harmonic follow the rule in nearly every window, also for transactions arriving during the
    slot.
  - The Agave family (Agave, Jito-Solana, Rakurai) follows it perfectly for transactions already pending when the slot
    starts. For transactions arriving during its slot, it does not.
  - Study 2 measured how far each one reorders against arrival. In the Agave family, a higher-priority transaction
    overtakes a 2 ms head start in only 20 % of races, and a 5 ms one never.
  - Firedancer and the Harmonic builders overtake a 2 ms head start in 97–100 % of races (both pre-registered and
    supported). Their horizons run from 5–10 ms to beyond 50 ms (exploratory).
- **Ties.** Of two identical buffered probes, Firedancer lands the later-sent one first, in 50 of 54 pairs
  (pre-registered, supported).

Everything here is recomputed from raw data by `docker compose up`, and every landing is checkable on chain (§10).
Both studies were pre-registered before their first probe. The hashes are in mainnet Memos
[`5vRM47a8…QcyG`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg) (Study 1, slot 460,779,153) and
[`2T6ha9FD…D5ww`](https://explorer.solana.com/tx/2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww) (Study 2, slot 461,151,605).

## 1. When each measurement was taken (UTC, slots ≥ 460,725,000, post-Alpenglow)

| Date | Time (UTC) | What | Data | Role |
|---|---|---|---|---|
| 10-24 | 05:23 | Live smoke: reachability per ingress kind | `data/smoke/20261024T052311Z-smoke-live-f540` | engineering check |
| 10-24 | 07:18–07:48 | Pilot, stages 1 and 2 (70 windows) | `data/pilot/20261024T0718*`, `…0738*` | calibration, not confirmatory |
| 10-24 | 07:59–08:12 | Second pilot (30 windows), after execution fixes | `data/pilot/20261024T0759*`, `…0804*` | calibration, not confirmatory |
| 10-24 | 08:16:46 | **Pre-registration frozen**; Memo on mainnet | `docs/PREREGISTRATION.md`, `design/` | — |
| 10-24 | 10:31–12:58 | **Study 1, Stage 1** (413 windows) | `data/raw/20261024T103156Z-s1-live-916e` | **confirmatory** |
| 10-24 | 13:38–14:53 | Study 1, Stage 2 (T, H, S kits; 156 windows) | `data/raw/20261024T133825Z-s2-live-4ab3` | exploratory |
| 10-25 | 03:53–03:57 | Mainnet dry run of the Study 2 design (12 windows, nothing sent) | local only (`data/dryrun/`) | engineering check |
| 10-25 | 04:27 / 06:14 | **Pre-registration 2 frozen** / its Memo on mainnet | `docs/PREREGISTRATION-2.md`, `design/*study2*` | — |
| 10-25 | 06:15–09:04 | **Study 2, Stage 1**: replication (316 windows) | `data/raw/20261025T061534Z-s1-live-4e60` | **confirmatory** |
| 10-25 | 09:05–11:16 | **Study 2, Stage 2**: races and equal-key pairs (234 windows) | `data/raw/20261025T090530Z-s2-live-0b4f` | **confirmatory** (H1–H3) |

Each step, its cost and its problems are in [docs/CAMPAIGN-LOG.md](docs/CAMPAIGN-LOG.md).

**Targets as identified at measurement time.** Client and version are what each validator advertised in gossip
(`target_states.jsonl` in every run), identical in every snapshot: 219 in Study 1, 301 in Study 2. The ingress kind
is the endpoint we actually reached.

| Validator | Gossip client | Version | Ingress | Study 1 | Study 2 |
|---|---|---|---|---|---|
| `7QQGNm3p…` | Agave | 4.3.2 | direct | core | core (K, R) |
| `HEL1USMZ…` | JitoLabs (Jito-Solana) | 4.3.2 | direct | core | core (K, R) |
| `EvnRmnMr…` | Firedancer | 26.10.4 | direct | core | core (K, R) |
| `DRpbCBMx…` | AgaveBam | 4.3.2 | BAM node | core | core (K, R) |
| `Fd7btgyS…` | HarmonicAgave | 4.3.2 | Harmonic remote TPU | core | core (K, R) |
| `JUPiTERr…` | HarmonicFiredancer | 26.10.4 | Harmonic remote TPU | core | core (K, R) |
| `9eGrDohd…` | Firedancer | 26.10.4 | direct | extended | equal-key windows (E) |
| `9jxgosAf…` | FireBAM | 26.10.4 | BAM node | extended | — |
| `5Cchr1XG…` | AgaveBam | 4.3.2 | BAM node | extended | — |
| `ana2y2Yv…` | Rakurai | 4.3.2 | direct | extended | — |

Full identities: [`design/targets.json`](design/targets.json), [`design/targets-study2.json`](design/targets-study2.json).

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
  p = 0.00036, which is the floor of 1/100,001 for 100,000 draws after Holm's factor of 36. Every send-order effect
  has p = 1.0.
- **Gates (§9).** Both positive controls, Agave `7QQGNm3p` and Firedancer `EvnRmnMr`, recovered their known rule. No
  buffer or streaming gate fired, and the selection-balance check passed for every contrast (all p ≥ 0.15).
- **Inclusion (co-primary, PREREGISTRATION §1.3).** Within every group and contrast, the two members landed at the
  same rate: per-label landing rates 0.80–1.00, exact McNemar p = 1.0 in all 30 group × contrast cells
  (`inclusion` in `results.json`). Whether a probe landed did not depend on its label, which also supports the
  selection assumption behind the complete-case estimates.
- **Mixture diagnostic.** In every group the key-dependent component is reward/cost's, and only reward/cost's
  (`mixture` in `results.json`).
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
  priority every time. When they are sent 0.05 ms apart during the slot, the order looks unrelated to the label. It is
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

## 5. Exploratory (Study 1, Stage 2, PREREGISTRATION §7)

All of this section is **exploratory** (PREREGISTRATION §7), descriptive, with plain 95 % Clopper–Pearson
intervals and no multiplicity claims. Study 2 (§6) then tested its race and tie-break findings confirmatorily. Full tables: [`data/derived/exploratory_stage2.md`](data/derived/exploratory_stage2.md),
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

**Uncontended C2: the same A′ and B probes on separate locks.** These are independent transactions that a
scheduler may run in parallel, so the probes need not land in priority order.
- Firedancer, Firedancer + BAM and Agave + BAM put B (the reward/cost-preferred one) first in every pair: 0/40, 0/19,
  0/36, 0/20 and 0/20 with A′ first.
- The Agave family and the Harmonic builders do not: A′ first in 13/40 (Agave), 18/40 (Jito-Solana), 5/20 (Rakurai),
  22/40 (Agave + Harmonic) and 12/42 (Firedancer + Harmonic).
- Only conflicting transactions are ordered strictly by the key everywhere.

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

## 6. Study 2: a second day, and how far each client reorders (pre-registered)

Study 2 was planned after Study 1 to close what Study 1 left open ([plan](docs/STUDY2-PLAN.md)):
- one day only;
- streaming samples of 5–11 windows;
- race cells of 1–7 races;
- a tie-break result two pairs short of its threshold.

It has its own normative plan, [PREREGISTRATION-2.md](docs/PREREGISTRATION-2.md), frozen after two independent reviews
([dispositions](docs/review/STUDY2-prefreeze-dispositions.md)). The hashes of that plan, the design and the manifest
are in mainnet Memo [`2T6ha9FD…D5ww`](https://explorer.solana.com/tx/2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww), posted before the first probe. The manifest also pins the git tree of the
analysis code. Operating characteristics, simulated under known schedulers: [POWER-2.md](docs/POWER-2.md).

Study 2 ran with a new wallet and its own ledger. That ledger carries Study 1's cost, so the compiled 0.05 SOL cap
covers both studies. Full tables: [`data/derived/study2/summary.md`](data/derived/study2/summary.md).

### 6.1 Replication (hypothesis R)

The Study 1 confirmatory procedure (PREREGISTRATION §1–§9), unchanged:
- the same six core targets in the same frozen groups;
- the same 36-effect family;
- the same decision rules and gates.

A target replicates when its published claim is the same as in Study 1.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/study2-replication-dark.svg">
  <img src="figures/study2-replication.svg" width="100%" alt="Forest plot of the three label contrasts for the six core targets, Study 1 in grey and Study 2 in blue. Both studies sit near 1, 0 and 1 for every target: the reward-divided-by-cost pattern, again.">
</picture>

| Target | Client | Ingress | Study 2: L_C1 / L_C2 / L_C3 | Study 1 claim | Study 2 claim | Replicated |
|---|---|---|---|---|---|---|
| `7QQGNm3p` | Agave | direct | 0.88 / 0.07 / 0.93 (n=40) | reward_cost | **reward_cost** | yes |
| `HEL1USMZ` | Jito-Solana | direct | 0.93 / 0.05 / 0.95 (n=40) | reward_cost | **reward_cost** | yes |
| `EvnRmnMr` | Firedancer | direct | 0.98 / 0.00 / 1.00 (n=45 / 38 / 45) | reward_cost | **reward_cost** | yes |
| `DRpbCBMx` | Agave + BAM | BAM node | 1.00 / 0.00 / 1.00 (n=39) | reward_cost | **reward_cost** | yes |
| `Fd7btgyS` | Agave + Harmonic | Harmonic remote TPU | 1.00 / 0.00 / 1.00 (n=40 / 40 / 43) | reward_cost | **reward_cost** | yes |
| `JUPiTERr` | Firedancer + Harmonic | Harmonic remote TPU | 1.00 / 0.00 / 0.98 (n=40 / 43 / 41) | reward_cost | **reward_cost** | yes |

- **Everything replicated:** all six claims, both positive controls, and selection-robustness for every claim. Send
  order again sits near 0.5: 0.425–0.575 for every core contrast.
- **The regime split replicated too:**
  - Agave and Jito-Solana follow the rule in every buffered window, but not in streaming ones:
    - Agave: 1.00 / 0.00 / 1.00 with n = 30, against 0.50 / 0.30 / 0.70 with n = 10;
    - Jito-Solana: 1.00 / 0.00 / 1.00, against 0.70 / 0.20 / 0.80.
  - Firedancer stays at 1.00 / 0.00 / 1.00 in streaming windows (n = 14).
- **Stopping:** `DRpbCBMx` (39) and Firedancer's C2 (38) used all 56 plans. That is the pre-registered stop on
  exhausted plans.

### 6.2 Hypotheses H1–H3 (confirmatory)

A race pairs `hi` against `lo`, which ranks below it under every key, with `lo` sent Δt ms earlier. The two start
5 ms after the target's first shred. O(Δt) is the share of races in which `hi` still landed first.

The confirmatory test is in the 2 ms cell:
- one-sided exact binomial test against one half;
- Holm over six hypotheses;
- a selection bound;
- two gates.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/study2-races-dark.svg">
  <img src="figures/study2-races.svg" width="100%" alt="Six small panels, one per validator group, of the share of races in which the high-priority probe overtook a low-priority one sent 0, 2, 5, 10, 25 or 50 ms earlier. Agave and Jito-Solana fall from most races at 0 ms to 7 of 35 and 6 of 29 at 2 ms and to none from 5 ms on. Firedancer EvnRmnMr overtakes at every head start up to 50 ms. The Harmonic builders overtake 2 ms head starts almost always and fall to none by 50 ms; Agave plus BAM falls to none at 50 ms.">
</picture>

| Hypothesis | k / n | Estimate [95 % CI] | Holm p | Published claim |
|---|---|---|---|---|
| `H1-agave`: Agave, `hi` overtakes a 2 ms head start in fewer than half of the races | 7 / 35 | 0.20 [0.08, 0.37] | 0.0005 | **supported** |
| `H1-jito`: Jito-Solana, the same | 6 / 29 | 0.21 [0.08, 0.40] | 0.0012 | **supported** |
| `H2-firedancer`: Firedancer `EvnRmnMr`, in more than half | 31 / 31 | 1.00 [0.89, 1.00] | < 10⁻⁷ | **supported** |
| `H2-firedancer-harmonic`: Firedancer + Harmonic, the same | 32 / 33 | 0.97 [0.84, 1.00] | < 10⁻⁷ | **supported** |
| `H2-agave-harmonic`: Agave + Harmonic, the same | 30 / 31 | 0.97 [0.83, 1.00] | < 10⁻⁷ | **supported** |
| `H3-firedancer-ties`: of two identical buffered probes 10 ms apart, the later-sent one lands first in more than half of the pairs (first-sent first: k / n) | 4 / 54 | 0.07 [0.02, 0.18] | < 10⁻⁷ | **supported** |

- **Every claim is selection-robust, and no gate fired.**
  - Every probe Stage 2 sent landed, so no pair was incomplete.
  - The hi-first controls lost 0 of their 5–6 races per group.
  - The achieved send gaps had medians of 2.20–2.23 ms in the 2 ms cells and 10.25 ms for the equal-key pairs.
- **H3 per target:** `EvnRmnMr` 1/31 and `9eGrDohd` 3/23, the same direction.
  - In every one of the 54 pairs, both probes were sent before the leader's first shred.
  - Reading the result as a tie-break by later *arrival* assumes the network kept our send order (PREREGISTRATION-2
    §2).
- **Sensitivity:** all five pre-specified analyses give the same six verdicts:
  - censored coding;
  - including transition-ambiguous windows;
  - achieved gap within 0.5 ms;
  - same-slot pairs;
  - buffering evidence ("equal key both sent before first shred" in the summary table).

### 6.3 How far each client reorders (exploratory)

Cells: races in which `hi` landed first / races, both landed, evaluable windows. At 0 ms both probes go out together,
counted in either stream order.

| Group | 0 ms | 2 ms | 5 ms | 10 ms | 25 ms | 50 ms | Horizon bracket | Equal key, first-sent first (10 ms) |
|---|---|---|---|---|---|---|---|---|
| Agave `7QQGNm3p` | 10/12 | 7/35 | 0/15 | 0/12 | 0/12 | 0/13 | 0–2 ms | 23/35 |
| Jito-Solana `HEL1USMZ` | 7/10 | 6/29 | 0/13 | 0/9 | 0/10 | 0/11 | 0–2 ms | 10/29 |
| Firedancer + Harmonic `JUPiTERr` | 12/12 | 32/33 | 7/13 | 4/12 | 1/12 | 0/11 | 5–10 ms | – |
| Agave + Harmonic `Fd7btgyS` | 10/10 | 30/31 | 11/13 | 7/12 | 1/10 | 0/11 | 10–25 ms | – |
| Agave + BAM `DRpbCBMx` | 3/3 | 14/14 | 4/6 | 5/5 | 3/6 | 0/5 | 25–50 ms (non-monotone, small cells) | – |
| Firedancer `EvnRmnMr` | 10/10 | 31/31 | 13/13 | 10/10 | 10/10 | 12/13 | > 50 ms | 1/31 |
| Firedancer `9eGrDohd` (equal-key windows only) | – | – | – | – | – | – | – | 3/23 |

- **Agave family: priority acts only over a couple of milliseconds.**
  - Sent together at the start of the slot, the higher-priority probe lands first in 17 of 22 races.
  - With a 2 ms head start for the other one, it lands first in 13 of 64. From 5 ms on, it never does (0 of 95).
  - Together with the regime split, this fits a scheduler that orders what is waiting at the same moment. A
    transaction arriving a few milliseconds later meets one that is already being processed.
- **Firedancer `EvnRmnMr` held priority order against every head start up to 50 ms** (12 of 13 at 50 ms). In Study 1
  the Firedancer direct group reordered within about 5–25 ms. That group was pooled with `9eGrDohd` and had 3–7 races
  per cell. `EvnRmnMr` advertised the same version, 26.10.4, on both days. So the horizon is a property of a
  validator's setup on a given day, not a constant of the client or its version. Pack's scheduling intervals are
  configurable; we cannot see which setting changed.
- **The builders** reorder over 5–10 ms (Firedancer + Harmonic), 10–25 ms (Agave + Harmonic) and 25–50 ms
  (Agave + BAM). Study 1 had too few races to measure BAM at all.
- **Equal keys in the Agave family are not plain FIFO.** Both studies sent these pairs buffered (−150 ms,
  direct ingress), 10 ms apart:
  - Study 1: first-sent first in 7/7 pairs for Agave, 5/7 for Jito-Solana.
  - Study 2: 23/35 for Agave, 10/29 for Jito-Solana.

  It is descriptive, and outside any hypothesis.

### 6.4 What Study 2 changes in the answer

- The rule is not an artefact of one day or one session: the confirmatory procedure, rerun unchanged, gives the same
  claim for every core target.
- "How strictly" now has a measured scale. The Agave family's priority ordering spans about 2 ms of arrival. Firedancer
  and the builders reorder over tens of milliseconds, and the span differs between validators and days.
- Firedancer's equal-priority tie-break, unidentified in Study 1, is now confirmed among buffered probes:
  later-sent first.

## 7. What went wrong

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
  the draft's illustrative censored-coding figures. Censored coding recovered reward/cost in 50 % of campaigns at
  90 % landing (complete case: 99 %) and in 0 % at 50 % landing (complete case: 51 %). On the frozen design the
  figures are 47 % vs 99 % and 0 % vs 48 %.
- **Slot cadence assumed in the design.** The design took ≈ 130 ms per in-window slot (≈ 560 ms at the hand-over)
  from an early dry run. Every campaign run then measured ≈ 198 ms per in-window slot and ≈ 268 ms at the hand-over
  (median `cadence_at_prep`). The consequences:
  - The planned offsets only become more conservative. A race ending at +55 ms is further inside a 198 ms slot.
  - The shared-ingress burst offsets avoided ±15 ms around multiples of 130 ms instead of the real slot boundaries.
  - The estimands are window-wide, so a pair that crosses a slot boundary is analysed as planned (Study 2 has a
    same-slot sensitivity). POWER.md simulated 130 ms slots.
- **Line endings.** `design/targets.json` had CRLF endings from a Python text-mode write. It was normalised to LF
  before freezing, with its content unchanged. `scripts/freeze.py` now writes LF and refuses CR bytes in hashed files.
- **Study 2: the same weak spots, smaller.**
  - The far BAM node `DRpbCBMx` again lost the most probes before sending: 39 pairs from all 56 plans.
  - 288 of 1,896 Stage-1 probes and 244 of 1,518 Stage-2 probes were never sent (no fee). Every probe that was sent
    in Stage 2 landed.
  - The concurrency fix (§8) made Study 2 about three times faster than Study 1.
- **Study 2: problems found before the freeze.**
  - The two independent reviews found five blocking problems in the draft pre-registration and analysis. One example:
    simultaneous races counted as controls, where noise could withdraw a valid result.
  - Each was fixed, with a test, before the Memo
    ([dispositions](docs/review/STUDY2-prefreeze-dispositions.md)).
- **Study 2: a platform-dependent string.** The Study 2 results first recorded the manifest path with a Windows
  backslash, so the Linux reproduction differed in that one field. The calling code now passes the path in POSIX
  form; the frozen decision code was not touched.
- **Earlier problems** found by the code reviews, the pilots and the localnet tests are listed with their fixes in
  [docs/review/CODE-gate1b-dispositions.md](docs/review/CODE-gate1b-dispositions.md) and
  [docs/CAMPAIGN-LOG.md](docs/CAMPAIGN-LOG.md).

## 8. Deviations from the pre-registrations

- **Analysis plan:** none. Estimands, decision rules, family, gates and stopping were applied as frozen.
- **Execution:** none. The frozen design (hash checked at run time) and the frozen parameters were used.
- **Exploratory items not computed (reporting deviation).** PREREGISTRATION §7 listed three exploratory analyses
  that we did not run:
  - block-structure statistics: a Chorus-style footrule, descending-run counts, and each probe's block-index
    percentile against its priority percentile;
  - the formal horizon-model fits (step, pending queue, linear batch, constant);
  - stratification by block fullness.

  The race tables and horizon brackets (§5, §6.3) are reported instead. The archived block excerpts in `data/raw`
  hold everything these analyses need.
- **Reporting fix after the freeze, no effect on any estimate:** the funnel labels a window that was skipped before
  any send (3 in Stage 1) only by its skip reason. Before the fix it was also labelled `design_mismatch` and so on.
- **Study 1 results file after Study 2:** `data/derived/results.json` now lists the two Study 2 runs under
  `rejected_runs` (other budget and design). Every number is unchanged.

**Study 2 (PREREGISTRATION-2):**
- **Analysis plan:** none. Hypotheses, tests, Holm, selection bound, gates and sensitivity analyses were applied as
  frozen.
- **Execution:** none. The frozen design (hash checked at run time) and the frozen parameters were used.
- **Send concurrency:** a window now holds its concurrency slot only while preparing and sending, not during outcome
  collection. This tool change was announced in the plan and the pre-registration before the freeze, so it is not a
  deviation.
- **Analysis code:** the decision code (`study2.py` and the modules it uses) is byte-identical to the tree pinned in
  the manifest (`cd83bbc9`). Reporting code (tables, figures, the reproduce hook) was added after the freeze.
  `scripts/verify_frozen_study2.py` re-decides Study 2 with the pinned tree and reproduces every number.

## 9. What this design does not separate

- **Priority fee vs total fee.** With one signature they rank our probes identically.
- **A builder's own sort vs the validator's scheduler behind it.** BAM and Harmonic groups are reported as the
  ingress path we measured.
- **The Agave mechanism for streaming arrivals.** We observe that the label stops mattering, not the internal queue.
- **External validity.** Our probes are tiny, untipped, legacy transactions with one signature, two writable accounts
  and 600 CU executed. Heavier transactions, Jito bundles and tips, v1 transactions and contended accounts were out of
  scope.
- **Staked or SWQoS senders.** We are an unstaked sender. Eviction, landing and timing may differ for staked
  connections.
- **Send-side gaps (Study 2).** Δt is the gap between our two sends, measured at the sender. The gap at the scheduler
  can be larger or smaller. Equal-key results read as an arrival tie-break only if the network kept the send order.
- **Why a horizon is what it is.** We measure how far a validator reorders, not its scheduler's settings. Firedancer
  `EvnRmnMr`'s horizon differed between the two days for reasons we cannot see.

## 10. Verify and reproduce

```bash
docker compose up --build                       # both studies: recompute every number, redraw every figure, diff all
docker compose --profile verify up              # re-check a sample of landings against mainnet blocks
sha256sum docs/PREREGISTRATION.md design/design.jsonl design/campaign.json   # = the hashes in the Study 1 Memo
sha256sum docs/PREREGISTRATION-2.md design/design-study2.jsonl design/campaign-study2.json   # = the Study 2 Memo
python scripts/verify_frozen_study2.py          # re-decide Study 2 with the analysis tree pinned in its manifest
```

**Probe explorer:** [docs/explorer](docs/explorer/index.html). Every window and every probe of both studies, with
eligibility, landing slot and index, each linked to Solana Explorer (`python scripts/build_explorer.py`).

- **Archive check:** all 2,553 Stage-1 landing claims verified, with 26 checks each (signed bytes, signature,
  probe atom, block index, on-chain message, fee, leader, window). The completeness check found no probe in any of the
  1,640 archived window blocks without a matching claim.
- **Chain check:** a random sample of 60 claims verified against mainnet blocks fetched again from the RPC.
  [`data/derived/verify-archive.json`](data/derived/verify-archive.json),
  [`data/derived/verify-chain-sample.json`](data/derived/verify-chain-sample.json).
- **Study 2:** all 2,795 landings verified against the archive. The completeness check covered 2,200 archived window
  blocks and found no unclaimed probe. A random sample of 60 was verified against public mainnet RPC:
  [`data/derived/study2/verify-archive.json`](data/derived/study2/verify-archive.json),
  [`verify-chain-sample.json`](data/derived/study2/verify-chain-sample.json).

## 11. Cost

**Both studies together: 42,926,000 lamports (0.0429 SOL) on chain**, everything included, under the 0.05 SOL cap. The
cap is compiled into the binary and enforced over both studies by the Study 2 ledger, which carries Study 1's cost.

**Study 1.** All amounts in lamports, from the spend ledger (`state/ledger.sqlite`). The owned accounts' on-chain balances agree
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

The cap was 0.05 SOL, compiled into the binary and enforced by the ledger. The highest charge it ever held, after closing, was
0.0256 SOL (24,712,500 landed in its ledger plus 886,500 for expired probes). The wallet received 0.1 SOL, plus 13,023 lamports of spam deposits, and returned 75,295,523 lamports to its funder
([`5j8PEKpj…LA3D`](https://explorer.solana.com/tx/5j8PEKpj5djzEbXGwcqxqdut6HTkMG9h71TV16EoRKfXVfKKq3L1iSGM7AVJv79BjDjvUp5pCVcPUp62d4mJLA3D)). The difference, 24,717,500 lamports, is the whole cost of the measurement.

**Study 2.** From its ledger (`state/ledger-study2.sqlite`), opened with the compiled cap and Study 1's 24,717,500
lamports as a carry-over. The owned accounts' on-chain balances agree to the lamport.

| Step | Landed fees | Charged for expired probes | Probes never sent (no fee) |
|---|---|---|---|
| Setup: Memo, payer funding (2), top-up (2), sweep (24) | 145,000 | 0 | — |
| Stage 1, replication (316 windows) | 9,376,500 | 539,500 | 288 |
| Stage 2, races and equal keys (234 windows) | 8,682,000 | 0 | 244 |
| Closing: return of the remainder to the funder | 5,000 | 0 | — |
| **Total** | **18,208,500 (0.0182 SOL)** | **539,500** | |

The wallet received 0.06 SOL and held 41,796,500 lamports after the sweep, exactly 60,000,000 − 18,203,500. It returned
41,791,500 to its funder ([`3eZAJYz5…SHjHK`](https://explorer.solana.com/tx/3eZAJYz5rNbucd1Yu246uENE2gpseEDzbteA4jVswvuWt7nxXrS7nCsgSHnvTMLb1EDKYNEQhXqHdxWdS2rSHjHK), fee 5,000). The difference,
18,208,500 lamports (0.0182 SOL), is the whole cost of Study 2.
