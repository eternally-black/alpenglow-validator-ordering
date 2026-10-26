# Campaign log

Every live action on mainnet, in order, with its UTC time, run directory and cost; problems are written down when they
happen (they feed REPORT.md's "what went wrong"). Ledger: `state/ledger.sqlite`, cap 0.05 SOL. Measurement wallet
`3SXcVVweK3tSSavEDyh91LvqD9eX2b48U2NXR9cLALt7`, created for this campaign only. It was funded with 0.1 SOL on
2026-10-24 and is emptied back to the funder and destroyed after the campaign.

## 2026-10-24 05:23 UTC — live smoke (reachability, not an ordering measurement)

- **Run:** [`data/smoke/20261024T052311Z-smoke-live-f540`](../data/smoke/20261024T052311Z-smoke-live-f540). Command: `itb smoke --live --max-spend-sol 0.05 --budget-sol 0.001`.
- **What was sent:** three identical template-A probes into the next leader window of 12 validators (two per client/ingress group), slots 460,730,128–460,730,657, post-Alpenglow.
- **Cost:** 162,000 lamports = 27 × 6,000. The ledger and the on-chain balance drop of the owned accounts agree exactly; 9 probes never left the process and cost nothing.

| Validator | Client | Ingress | Result | Block index of the 3 probes / block size |
|---|---|---|---|---|
| `Fd7btgyS` | HarmonicAgave | Harmonic remote TPU | 3/3 landed in window | 290, 291, 305 / 395 |
| `9eGrDohd` | Firedancer | direct | 3/3 | 20, 37, 39 / 420 |
| `CAo1dCGY` | HarmonicAgave | Harmonic remote TPU | 3/3 | 59, 60, 62 / 341 |
| `EvnRmnMr` | Firedancer | direct | 3/3 | 369, 370, 371 / 391 |
| `E1r4Psq8` | JitoLabs | direct | 3/3 | 76, 77, 78 / 416 |
| `JUPiTERr` | HarmonicFiredancer | Harmonic remote TPU | 3/3 | 2, 3, 4 / 652 |
| `DRpbCBMx` | AgaveBam | BAM node | 3/3 | 24, 28, 32 / 573 |
| `5Cchr1XG` | AgaveBam | BAM node | 3/3 | 5, 8, 10 / 298 |
| `HEL1USMZ` | JitoLabs | direct | 3/3 | 19, 20, 21 / 320 |
| `9jxgosAf` | FireBAM | BAM node | 0/3 sent — connection evicted | — |
| `GnC339vk` | JitoLabs | Jito relayer | 0/3 sent — connection evicted | — |
| `5pPRHnie` | JitoLabs | Jito relayer | 0/3 sent — connection evicted | — |

**What it shows.** Unstaked QUIC probes are accepted and land in the targeted window through every ingress kind of
the core design: direct Agave-family and Firedancer TPUs, Harmonic remote TPUs and BAM nodes. Positions differ a lot
between validators: from the very top (`JUPiTERr`) to the very end of the block (`EvnRmnMr`). These are identical
probes, so this is descriptive only; the ordering question is what the campaign's contrasts are for.

**What went wrong.** For three targets the handshake ~15 slots before the window succeeded, but by send time the
server had closed the connection: `open_uni: closed by peer: dropped (code 1)`. That is the Agave QUIC server evicting
an unstaked connection from its full table. Nothing was written, so the probes are `never_opened` and their
reservations were released. Affected: one BAM node (FireBAM `9jxgosAf`, an extended target) and both Jito relayers
(not campaign targets).
**Fix (before the pilot):** `itb run` re-checks the connection right after each phase's anchor is observed and
re-handshakes if it was evicted (`reconnects` in `windows.jsonl`). A re-handshake that makes a send late is caught by
the send deadline, as before.

## 2026-10-24 07:17 UTC — payer funding

`itb setup fund --lamports-per-payer 3000000`: two transfers from the master to the 24 payers, 0.072 SOL between owned
accounts (not spent) and 10,000 lamports of fees. The fee reserve per payer (3,000,000 minus the rent-exempt
minimum) covers the whole campaign's worst case.

## 2026-10-24 07:18–07:33 UTC — pilot stage 1 (budget `pilot`, design `design.pilot.jsonl`, not confirmatory)

- **Run:** [`data/pilot/20261024T071849Z-s1-live-1ef8`](../data/pilot/20261024T071849Z-s1-live-1ef8). Preceded by a 3-window dry run (`…071806Z-s1-dry-d05f`).
- **Scope:** 40 K windows, 4 per target, 10 targets, 8 client types, slots ≈ 460,73x,xxx (post-Alpenglow).
- **Result:** of 272 sent probes, 263 landed in the target window (96.7 %) and 9 expired; 48 were never sent (no fee). 34 of 40 windows are evaluable; every exclusion is "not all probes sent". Pairs with both members landed: 93 % in buffered windows, 75 % in streaming windows (unsent probes count as not landed).
- **Timing:** buffered sends on direct ingress were achieved at −150 to −181 ms (median) against the observed first shred, as designed. Cadence over the run: 199 ms inside a window, 257 ms at hand-over.
- **Reconnect fix confirmed:** FireBAM `9jxgosAf`, evicted in the smoke, re-handshook 4 times and landed 32/32.
- **What went wrong:**
  - A connection re-established right before the send waited one round trip for stream credits. That made 4 windows (a far BAM node, `5Cchr1XG`, 165–189 ms handshakes; one at `ana2y2Yv`) miss the 20 ms lateness budget.
  - Two windows were prepared too late ("late").
  - Fixed before stage 2: the connection is re-checked before the anchor wait too, and the lateness budget is 100 ms for stage 2.

## 2026-10-24 07:38–07:48 UTC — pilot stage 2

- **Run:** [`data/pilot/20261024T073832Z-s2-live-3b84`](../data/pilot/20261024T073832Z-s2-live-3b84), `--max-lateness-ms 100`. 30 windows: T races, H hold-cliff, S spill-over.
- **T races:** 72/80 landed in the window.
- **S spill-over:** 16 landed in the window, 1 landed with another leader, 1 expired.
- **H kit (descriptive, exploratory):**
  - Agave `7QQGNm3p` and the Agave fork Rakurai `ana2y2Yv`: probes sent 7 s ahead expired, those sent 3 s and 0.5 s ahead landed. That matches Agave holding packets for ≤ 20 slots.
  - Firedancer `EvnRmnMr`: the probe sent 7 s ahead landed in the validator's next window. That matches Firedancer keeping pending transactions until the blockhash expires.
  - JitoLabs `HEL1USMZ`: one 7 s probe expired, one landed in the next window.
- **What went wrong:** 19 probes "late". Two causes: a whole send phase was cancelled when its earliest send was late, including later sends still on time (H kit), and preparation had only a 1.5 s margin. Fixed after the pilot: lateness per probe, and a 3 s preparation margin.

## 2026-10-24 — external deposit

A stranger sent 8,505 lamports to payer `7dXoiEPr…` (slot 460,763,291, fee payer `3fjTE8io…`), a typical spam "dust"
transfer. Reconciliation stayed safe: the balances fell by less than the fees charged. The deposit was recorded with
`itb ledger --add-deposit-lamports 8505`, after which ledger and chain agree to the lamport.

**Cost so far:** 2,479,000 lamports of landed fees (smoke, setup, pilot) plus 92,000 lamports charged for expired
probes. That is 0.0026 SOL of the 0.05 SOL cap.

## 2026-10-24 07:59–08:12 UTC — second pilot (validates the post-pilot execution fixes)

- **Runs:** [`…075910Z-s1-live-c37d`](../data/pilot/20261024T075910Z-s1-live-c37d) and [`…080412Z-s2-live-03e3`](../data/pilot/20261024T080412Z-s2-live-03e3). Design `design.pilot2.jsonl`: 2 K and 1 H/S window per target; same budget `pilot`; `--max-lateness-ms 100`. Before it ran, the same code passed the localnet end-to-end test (70/70 claims, 10/10 windows evaluable).
- **K windows:** all 136 sent probes landed in their target windows. 24 were not sent: evicted connections and fresh connections still waiting for stream credits.
- **H/S windows:** per-probe lateness works. Only the late −7 s probes were skipped; the −3 s and −0.5 s sends went out.
- **Both pilots together** (`scripts/pilot_summary.py`):
  - Once a K probe left the process, it landed in the target window for 100 % of probes at 8 of 10 validators, 98 % at `Fd7btgyS` and 80 % at `DRpbCBMx`.
  - The losses are probes that could not be sent. The worst case is the far BAM node `5Cchr1XG` (16 of 48 sent, an extended target). Next are `ana2y2Yv` (32/48), `9eGrDohd` and `DRpbCBMx` (40/48).
  - Pairs with both members landed: 92 % in buffered windows, 76 % in streaming windows.
- **Second external deposit:** 4,518 lamports to payer `CtkaziuR…` (slot 460,774,514, fee payer `HhQXNqM1…`), recorded with `itb ledger --add-deposit-lamports 4518`. `scripts/foreign_transfers.py` lists every foreign transaction touching the owned accounts: the funding and these two deposits.

**Pilot cost (both pilots, budget `pilot`):** 3,256,500 lamports of landed fees plus 98,000 lamports charged for expired probes. **Campaign total so far:** 3,428,500 lamports of landed fees plus 98,000 expired, 0.0035 SOL of the 0.05 SOL cap. The ledger and the chain agree to the lamport once the two recorded deposits are counted.

## 2026-10-24 08:16 UTC — freeze

- **Inputs:** after both pilots, the targets were checked against live gossip: all 10 still show the client and ingress kind of `design/targets.json`.
- **Frozen files** (commit `5ddcc97`):

  | File | SHA-256 |
  |---|---|
  | `docs/PREREGISTRATION.md` | `478b09b618d5a6f455302149ad3cc607468b0949153fdaf62a75f3105f944c55` |
  | `design/design.jsonl` (`itb design --seed 20261023`, 796 windows, worst case 0.0387 SOL) | `cdca861b32af78fe89417a4348f118481f1153adde7616aef227487cb6f5d828` |
  | `design/campaign.json` | `857825e066f341b3755ddfc60ff43e8437a5c3ebd90c980a675bc07640022bc7` |

- **Memo:** [`5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg), finalized in slot 460,779,153 at 08:16:46 UTC. Program spl-memo, signer the measurement wallet, text `itb-prereg v1 prereg=… design=… manifest=…` with the three hashes above. Fee: 5,000 lamports.
- **Re-checked from git:** the committed blobs of the three files hash to exactly these values; the repository stores LF, and `scripts/freeze.py` refuses CR bytes.
- **What went wrong:**
  - The draft design that POWER.md was simulated on (`design.draft.jsonl`) came from an older build of the generator. It still had streaming offsets on multiples of 130 ms, so it is not byte-identical to the frozen design. The simulation is rerun on the frozen design, and POWER.md is updated with the result, as it promised.
  - `design/targets.json` had CRLF endings from a Python text-mode write. It was normalised to LF before hashing, with its content unchanged.

## 2026-10-24 — simulation study rerun on the frozen design (before Stage 1)

- **Scope:** 17 scenarios × 100 campaigns plus the censored-coding comparison, on `design/design.jsonl`. Results in [`data/derived/oc.json`](../data/derived/oc.json) and [POWER.md](POWER.md).
- **Comparison with the pre-freeze run:** same picture within 3 percentage points in every cell. No wrong claim survives the worst-case selection bounds in any scenario.
- **Note for REPORT.md:** the frozen pre-registration (§1) quotes the pre-freeze censored-coding figures, 50 % vs 99 % and 0 % vs 51 %. On the frozen design they are 47 % vs 99 % and 0 % vs 48 %. These are illustrative numbers; the analysis plan itself is unchanged.
- **Scoring fix:** `unidentified:selection` was not counted as an honest non-claim in two scenarios (`fifo_reorder`, `mode_switch_rc_fifo`). Those two were re-scored on the same seeds: same claims, now counted correctly.

## 2026-10-24 10:31–12:58 UTC — campaign Stage 1 (confirmatory)

- **Run:** [`data/raw/20261024T103156Z-s1-live-916e`](../data/raw/20261024T103156Z-s1-live-916e). Frozen design (hash checked by `--design-sha256`), budget `campaign` capped at 0.044 SOL, parameters as frozen in PREREGISTRATION. The PC was idle during the run.
- **Scope:** 413 windows, 3,280 probes. 2,553 landed in their target windows (15,797,000 lamports of fees) and 111 expired (686,500 lamports charged). 616 were never sent, at no cost. The ledger and the chain agree to the lamport.
  - Correction: an earlier version of this entry gave the cumulative ledger totals since the campaign opened, which include the smoke test and the pilots (3,105 landed, 19,230,500 lamports, 127 expired, 722 unsent), as Stage 1's.
- **Stopping:**
  - 40 or more informative pairs per contrast for five core targets: `7QQGNm3p` (in 42 windows), `EvnRmnMr`, `Fd7btgyS`, `HEL1USMZ`, `JUPiTERr`.
  - 20 for each extended target.
  - `DRpbCBMx` (AgaveBam, core) used all 80 plans and finished with 36, the pre-registered stop on exhausted plans.
- **What went wrong:**
  - About half of `DRpbCBMx`'s streaming windows were "late", plus BAM-node evictions. A likely cause is the frozen concurrency of 2: a window that waits for a slot held by a previous window's outcome collection starts too close to its leader slot.
  - Slow-schedule targets needed most of the 2.5 hours.
- **Confirmatory analysis** (`itb_analysis.cli report --manifest design/campaign.json`): every validator group orders our probes by Agave's reward/cost priority. A goes before B in C1; B goes before A′ in C2, although A′ pays the higher CU price, because its 64 MiB loaded-data request raises its cost; A goes before A′ in C3. The send order does not matter (O ≈ 0.5 everywhere).
  - Both positive controls passed, no §9 gate fired, and the selection check passed everywhere.
  - All six core claims are `reward_cost` and selection-robust.
  - Strictness lower bounds: 0.89–0.93 for Firedancer, Harmonic and BAM; 0.70 for Agave and JitoLabs, where B went before A in a few windows.
  - Extended targets (exploratory): `9eGrDohd` and `9jxgosAf` reward_cost; `5Cchr1XG` reward_cost (assumes selection); `ana2y2Yv` partial:reward_cost.
- **Verification:** all 2,553 claims check out against the archive, and no window block holds an unclaimed probe (1,640 blocks). A random sample of 60 claims checks out against mainnet blocks fetched again from the RPC. Files: [`data/derived/verify-archive.json`](../data/derived/verify-archive.json), [`data/derived/verify-chain-sample.json`](../data/derived/verify-chain-sample.json).

## 2026-10-24 13:38–14:53 UTC — campaign Stage 2 (exploratory)

- **Run:** [`data/raw/20261024T133825Z-s2-live-4ab3`](../data/raw/20261024T133825Z-s2-live-4ab3). Frozen design and parameters, budget `campaign`.
- **Scope:** 156 windows (T races, H hold cliff, S spill-over), 1,042 probes. 807 landed in their target windows (5,362,000 lamports) and 16 expired (102,000 charged); 219 were never sent. The ledger and the chain agree to the lamport.
- **Results** (REPORT.md §5, `data/derived/exploratory_stage2.md`):
  - **Effective reordering horizon:** under 5 ms for the Agave family, about 5–25 ms for Firedancer and Harmonic/Firedancer, about 25–60 ms for Harmonic/Agave.
  - **Equal key:** Agave is FIFO; Firedancer leans later-arrival-first at 10 ms, below the pre-registered identification threshold.
  - **Hold cliff:** confirmed. Agave and Jito-Solana drop the 7 s probes; Firedancer keeps them.
  - **Spill-over:** pre-window sends to BAM and Harmonic land in the target window, never with the previous leader.
- **Final confirmatory report**, rerun with both runs present: identical validator-level results, Holm p-values and positive controls; only the funnel now also counts Stage-2 windows. The offline `docker compose up` reproduction passes.

**Campaign total:** 24,592,500 lamports of landed fees plus 886,500 charged for expired probes, i.e. 0.0255 SOL of the 0.05 SOL cap.

## 2026-10-24 16:55–18:14 UTC — closing the wallet

- **Sweep** (16:55): `itb setup sweep` returned every payer's balance to the master, in 24 transfers costing 120,000 lamports of fees. All payers are empty. The master then held 75,300,523 lamports, exactly the opening 0.1 SOL plus the 13,023 lamports of recorded deposits minus 24,712,500 lamports of fees charged by the ledger.
- **Return to the funder** (18:14:23): 75,295,523 lamports sent to `3cB1N3xVpPjfjnZmYEsijL5znEKudNGMCMQmse9BoD5Y`, the address that funded the wallet. Transaction [`5j8PEKpj…LA3D`](https://explorer.solana.com/tx/5j8PEKpj5djzEbXGwcqxqdut6HTkMG9h71TV16EoRKfXVfKKq3L1iSGM7AVJv79BjDjvUp5pCVcPUp62d4mJLA3D), slot 460,948,160, fee 5,000. The wallet owner ran it, not the tool. The master balance is 0.
- **Total cost of the whole measurement:** 100,000,000 + 13,023 − 75,295,523 = 24,717,500 lamports (0.0247 SOL). That covers smoke, setup, pilots, both campaign stages, the sweep and the return.
- The keypairs (`keys/`, never in git) are deleted by the wallet owner after this entry.

# Study 2

Plan: [STUDY2-PLAN.md](STUDY2-PLAN.md), approved by the wallet owner on 2026-10-25. Normative analysis plan:
[PREREGISTRATION-2.md](PREREGISTRATION-2.md).

## 2026-10-24/25 — wallet, payers and ledger (offline)

- **Master** `6hoQGYN4Di3aseUv32YLoJQiTMeAZRAJPeWCx8tHdp4q`, generated with `solana-keygen` for Study 2 only, in
  `keys-study2/` (git-ignored like every `keys-*` directory). Funded by the wallet owner; everything left at the end
  returns to the funder.
- **Payers:** 24 fresh keypairs (`keys-init`, `keys-study2/payers/`).
- **Ledger** `state/ledger-study2.sqlite`, opened with the compiled 0.05 SOL cap. Before anything else it records
  Study 1's total cost, 24,717,500 lamports, as a carry-over (`itb ledger --carry-over-lamports`). Headroom for
  Study 2: 25,282,500 lamports. The ledger refuses any reservation that would take the two studies together past
  0.05 SOL; on-chain reconciliation still compares only the Study 2 accounts' drop with what this ledger committed.

## 2026-10-25 03:53–03:57 UTC — mainnet dry run of the Study 2 design

- Design `design/design-study2.jsonl` (`itb design --study 2 --seed 20261025`, 570 windows, worst case 0.0228 SOL,
  SHA-256 `2c9a18fb…87f3`), with the frozen execution parameters and budget `study2`. Dry run: nothing signed or sent.
- `20261025T035350Z-s1-dry-d3d1`: 4 K windows (Jito-Solana, Agave + Harmonic, Agave + BAM, Firedancer + Harmonic).
- `20261025T035515Z-s2-dry-e963`: 8 stage-2 windows, 7 R (Firedancer, both Harmonic builders, Agave + BAM) and 1 E
  (`9eGrDohd`).
- Every window anchored and scheduled every planned probe; no skip, no failure. The output is local
  (`data/dryrun/`, git-ignored).

## 2026-10-25 — operating characteristics of the Study 2 hypotheses

The frozen design, simulated under known schedulers at 90 % landing with Study 1's observation failures, 100
campaigns per scenario, published claims after the gates ([POWER-2.md](POWER-2.md), `scripts/oc_study2.py`; rerun
after the pre-freeze reviews). If Study 1's exploratory picture holds, each hypothesis is supported in 98–100 % of
campaigns. With every hypothesis false, false support appears in 0 of 100 campaigns (wide margin) and 4 of 100 at the
exact null boundary.

## 2026-10-25 — independent pre-freeze reviews

GPT (gpt-6.1-sol, `codex exec`) and DeepSeek (deepseek-v4-flash, thinking) reviewed the pre-registration, analysis,
generator, simulation and freeze script at `518d7fb`. GPT found 2 blockers and 5 should-fix items; DeepSeek found 3
blockers, 5 should-fix items and 3 nits, partly overlapping. Every one was checked against the code. All were fixed
or scoped in the text before freezing, each fix with a test that fails on the reviewed version:
[docs/review/STUDY2-prefreeze-dispositions.md](review/STUDY2-prefreeze-dispositions.md). The design was regenerated
(same seed) and the operating characteristics rerun.

## 2026-10-25 04:22 UTC — funding

- 60,000,000 lamports (0.06 SOL) from `3cB1N3xVpPjfjnZmYEsijL5znEKudNGMCMQmse9BoD5Y` (the wallet owner) to the Study 2
  master: transaction [`4KSDo1hb…2Ubx`](https://explorer.solana.com/tx/4KSDo1hbbdLofuHYryWijwgiPeR9E3aySDVzEc6f9qoJwSTTECCp4hgmu4SgYezJfiMYnzrKuiySLwwrkuTx2Ubx),
  slot 461,120,139. The first live command records this balance as the Study 2 opening.

## 2026-10-25 04:27–06:15 UTC — freeze, Memo, payer funding

- **Freeze** (04:27): `scripts/freeze.py --study 2` wrote `design/campaign-study2.json` at commit `bb4f5f4`
  (manifest committed in `a556cbf`):

  | Frozen file | SHA-256 |
  |---|---|
  | `docs/PREREGISTRATION-2.md` | `d970ef987aa29460e8aa1520e11e1eb88aec16510454f41b973795a770a028eb` |
  | `design/design-study2.jsonl` (`itb design --study 2 --seed 20261025`, 570 windows, worst case 0.0228 SOL) | `3df240b1a989249723c3282f41c1c5fe07fd06e72ca6ad63c239b34d3f9d0fdd` |
  | `design/campaign-study2.json` (hypotheses with planned n, budget `study2`, cutoff 2026-10-30T23:59Z, carry-over, `analysis_tree` `cd83bbc90773b2ee53a958eb17f92ad5eaff2a14`) | `36a6416bd8a7e80eee68346f437091872c1cd6f034265a59afe89fc47a9d4519` |

- **Binary:** the `itb:local` image rebuilt from the freeze commit before any live action.
- **Memo** (06:14:18): transaction [`2T6ha9FD…D5ww`](https://explorer.solana.com/tx/2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww),
  slot 461,151,605, signed by the Study 2 master, fee 5,000. Its text, re-read from the chain, equals
  `itb-prereg v2 prereg=<sha> design=<sha> manifest=<sha>` for the three files above. It was the first live command
  on the Study 2 ledger, so it also recorded the opening: master 60,000,000 lamports, 24 empty payers.
- **Payer funding** (06:14:47, 06:14:50): `itb setup fund --lamports-per-payer 2000000`, two transfers (16 and 8
  payers), fees 10,000. Study 2 spend so far: 15,000 lamports.

## 2026-10-25 06:15–09:04 UTC — Study 2 Stage 1 (replication, confirmatory)

- **Run:** [`data/raw/20261025T061534Z-s1-live-4e60`](../data/raw/20261025T061534Z-s1-live-4e60), the frozen design
  (hash checked at run time) and the frozen parameters, on the binary rebuilt from the freeze commit.
- **Pace:** 316 windows in 2 h 49 min. With the send-only concurrency fix, windows no longer waited for another
  window's outcome collection: 200 windows in the first 45 minutes, about three times Study 1's pace.
- **Probes:** 1,896 planned. 288 were never sent; they cost nothing and their windows are excluded. Of the 1,608
  sent, 1,521 landed in the target window (94.6 %) and 87 expired.
- **Stopping (§5 with ≤ 56 plans):**
  - Jito-Solana, Agave + Harmonic and Firedancer + Harmonic reached 40 informative pairs per contrast.
  - Agave also reached 40, last, at 09:04; its ≈ 12 windows an hour set the pace.
  - Agave + BAM `DRpbCBMx` (39) and Firedancer C2 (38) used all 56 plans: the pre-registered stop on exhausted plans.
    `DRpbCBMx`'s far BAM node again lost the most probes before sending.
- **End:** no window failure, no open reservation. Reconciliation: the owned balance fell by 9,391,500 lamports,
  exactly the fees the ledger recorded.
- **Payer top-up** (09:05): `itb setup fund --lamports-per-payer 2000000`, two transfers, fees 10,000.

## 2026-10-25 09:05–11:16 UTC — Study 2 Stage 2 (races and equal-key pairs, confirmatory H1–H3)

- **Run:** [`data/raw/20261025T090530Z-s2-live-0b4f`](../data/raw/20261025T090530Z-s2-live-0b4f), 234 windows:
  35 R windows for each of the six race targets and 24 E windows for `9eGrDohd`. Every plan was executed.
- **Probes:** 1,518 planned. 244 were never sent. **All 1,274 sent probes landed in the target window.**
- **Achieved send gaps** (stream finish to stream finish, medians):

  | Planned gap | Achieved median |
  |---|---|
  | 2 ms | 2.20–2.23 ms per group |
  | 5 ms | 4.65 ms |
  | 10 ms | 10.07 ms |
  | 25 ms | 25.0 ms |
  | 50 ms | 50.1 ms |
  | Equal-key 10 ms | 10.25 ms |
  | Simultaneous | 0.003 ms |

  Every gate of PREREGISTRATION-2 §8 passed.
- **End:** no window failure, no open reservation. Reconciliation: the owned balance fell by 18,083,500 lamports
  since the opening, exactly the fees recorded.

## 2026-10-25 11:17 UTC — sweep

- `itb setup sweep`: 24 transfers returned every payer's balance to the master, fees 120,000. All payers are empty.
- The master holds 41,796,500 lamports: exactly 60,000,000 − 18,203,500, the Study 2 fees the ledger recorded
  (Memo, three funding transfers, both stages, the sweep). The ledger also charges 539,500 lamports of expired probes
  at their worst case. Those never left the accounts on chain, so its committed total, 43,460,500 with the carry-over,
  is above the true spend.
- **Total cost of both studies on chain:** 24,717,500 (Study 1) + 18,203,500 (Study 2) = 42,921,000 lamports
  (0.0429 SOL), before the final return transfer (5,000).

## 2026-10-25 — Study 2 analysis and verification

- `itb-analysis study2 report` → [`data/derived/study2/`](../data/derived/study2/summary.md).
  - Replication: 6 of 6 core targets keep their Study 1 claim (`reward_cost`). Both positive controls passed, and every
    claim is selection-robust.
  - H1–H3: 6 of 6 supported and selection-robust, with no gate fired.
- `scripts/verify_frozen_study2.py`: the analysis tree frozen in the manifest (`cd83bbc9`) reproduces every number.
- Archive check: all 2,795 Study 2 landings verified (26 checks each). The completeness check found no probe in any of
  the 2,200 archived window blocks without a matching claim. Chain check: a random sample of 60 verified against
  public mainnet RPC.
- `docker compose up` reproduces Study 1, every figure (Study 2's included) and Study 2.

## 2026-10-26 07:45 UTC — closing the Study 2 wallet

- **Return to the funder** (07:45:10): 41,791,500 lamports sent to `3cB1N3xVpPjfjnZmYEsijL5znEKudNGMCMQmse9BoD5Y`,
  transaction [`3eZAJYz5…SHjHK`](https://explorer.solana.com/tx/3eZAJYz5rNbucd1Yu246uENE2gpseEDzbteA4jVswvuWt7nxXrS7nCsgSHnvTMLb1EDKYNEQhXqHdxWdS2rSHjHK), slot 461,584,040,
  fee 5,000. The wallet owner ran it, not the tool. The master and all 24 payers now hold 0 lamports.
- **Total cost of Study 2:** 60,000,000 − 41,791,500 = 18,208,500 lamports (0.0182 SOL), the return transfer included.
- **Total cost of both studies:** 24,717,500 + 18,208,500 = **42,926,000 lamports (0.0429 SOL)**, under the 0.05 SOL cap.
- The Study 2 keypairs (`keys-study2/`, never in git) are deleted by the wallet owner after this entry, as are
  Study 1's (`keys/`).

## 2026-10-26 08:53–08:56 UTC — Study 3 prepared: first dry run, wallet, ledger

- **Why Study 3:** the final review found that Studies 1 and 2 cannot separate reward ÷ (cost + 1) from ordering by
  requested cost alone ([STUDY3-PLAN.md](STUDY3-PLAN.md)). Two new contrasts, C4 (Y vs A) and C5 (hi vs A), separate
  them.
- **Wallet** (08:55 UTC): a new master `DrMFg9FgLhiJqD5BjiqDVK7cobZU8Web8H6DGbdbDxex` and 24 payers in `keys-study3/` (never in git).
- **Ledger:** `state/ledger-study3.sqlite`, opened under the compiled 0.05 SOL cap with Studies 1 and 2's
  42,926,000 lamports as a carry-over. Headroom: 7,074,000 lamports.
- **First dry run** (08:53 UTC, `20261026T085305Z-s1-dry-1cf9`, 8 windows, clean). It tested the **first draft** of the design,
  whose Y was (L 3,000, 2,000,000 µlamports/CU). That design was withdrawn before freezing (next entry); the dry run
  does not count for the final design.

## 2026-10-26 09:00–09:35 UTC — Study 3 pre-freeze review and final design

- **Reviews:** GPT ([STUDY3-prefreeze-gpt.md](review/STUDY3-prefreeze-gpt.md)) and DeepSeek. All findings are fixed
  or disclosed ([STUDY3-prefreeze-dispositions.md](review/STUDY3-prefreeze-dispositions.md)). The main changes:
  - **Y is now (L 1,500, 4,000,000 µlamports/CU):** cost 2,835, priority 2,997,179. The first-draft Y lost C4 under
    total fee ÷ cost. The new one wins it for any share of the signature fee counted as reward, under any shared
    cost overhead.
  - **Verdicts:** "H5 supported, H4 not" no longer reads as a rejection. Identification is scoped to the registered
    candidates, and the selection qualifier reaches every verdict.
  - **Freeze:** the Study 1 and Study 2 claims are frozen into the manifest.
  - **Analysis:** an empty run yields all twelve hypotheses, and there are per-target diagnostics.
- **Final design:** `design/design-study3.jsonl` (`itb design --study 3 --seed 20261026`, 192 windows, worst case
  5,952,000 lamports), SHA-256 `bfaa83b62ac3b0987ce636367fdc8b638362942d65f571eacffc16542c60340d`. The frozen Study 1
  and Study 2 designs still regenerate byte for byte.
- **Final dry run** (09:33–09:34 UTC, `20261026T093300Z-s1-dry-9959`):
  - ran with `--design-sha256` of the final design, the frozen execution parameters and budget `study3`; nothing was
    signed or sent;
  - 8 windows: Agave ×2, Firedancer ×2, Agave + Harmonic ×2, Jito-Solana, Firedancer + Harmonic;
  - 32 probes (A 16, Y 8, hi 8), every window anchored, no failure;
  - measured cadence 198.5 ms inside a window and 267.7 ms at the hand-over.
