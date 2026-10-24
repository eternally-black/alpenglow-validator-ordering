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
