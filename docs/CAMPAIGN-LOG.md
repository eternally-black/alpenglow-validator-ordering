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
