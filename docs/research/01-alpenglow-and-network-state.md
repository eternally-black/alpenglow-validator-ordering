# Research note 01 — Alpenglow and the post-upgrade network state

Compiled 2026-10-23. `[RPC]` = checked directly against `api.mainnet-beta.solana.com`
(node 4.3.2, slot ≈ 460.47 M, epoch 1065). Everything else cites a source.

## Alpenglow activation (we measure strictly AFTER it)

| Fact | Value | Source |
|---|---|---|
| Feature gate | `A1pengvuM6JEcyNuTnMqepBKhwHE3N6PmUrdATGawhJS` | [agave feature-set](https://raw.githubusercontent.com/anza-xyz/agave/master/feature-set/src/lib.rs), [solana.com/upgrades/alpenglow](https://solana.com/upgrades/alpenglow) |
| Gate activation slot | 459,648,000 (first slot of epoch 1064, 2026-10-21 13:36:05 UTC) | [RPC] feature account: byte0 = 1, bytes1..9 = u64 LE slot |
| Last TowerBFT block | 459,652,999 | [RPC] `getAgGenesisCert` |
| First Alpenglow block | 459,653,008 (parent 459,652,999, 13:54:03 UTC) | [RPC] |
| What is live | Votor only; Rotor not live; `FastLeaderHandover…` gate absent | [RPC], [anza.xyz/alpenglow](https://anza.xyz/alpenglow) |

The SIMD-0384 text lists a different key (`a1penGLz8…`) that does not exist on mainnet — use `A1peng…`.
The Foundation recommends gating code on `getAgGenesisCert`, not on dates.

**Design consequence:** every run asserts (a) the gate account is activated and (b) every slot we analyse is
≥ 459,653,008. Analysis refuses mixed data.

## What changed in blocks

- **No vote transactions in blocks** (votes are off-chain BLS; certificates live in a block footer visible only to Geyser).
  [RPC] sampled blocks: 0 `Vote111…` txs; `numTransactions == numNonVoteTransactions`.
- **Transaction v1** (SIMD-0385, gate `txv1aq4pp281K9um3tnPgkfX8UqtFT6wcVW3hNezGLL`, active since epoch 1035):
  - `getBlock` needs `maxSupportedTransactionVersion: 1`, else error −32015 [RPC].
  - In samples: ~35–45 % of txs are v1 [RPC].
  - A v1 priority fee is a **lamport total** in `message.transactionConfig.priorityFee`. Compute Budget instructions are ignored for v1.
- **`meta.costUnits`** is present for every tx [RPC]. This is the cost-model cost, so reward/cost priority can be computed for every tx in a block.
- **Slot time is 200 ms** (SIMD-0525, since epoch 1053, 2026-10-09). [RPC] measured ≈ 210 ms.
  - Leader window = 4 consecutive slots = 800 ms.
  - Epoch = 432,000 slots ≈ 24 h.
  - Blockhash validity = 150 blocks ≈ 30 s.
- **Commitment:** `confirmed` == `finalized` under Votor [RPC].
- **`blockTime`** is now leader-set within bounds, so it is not a precise clock.
- **PoH tick entries removed;** a `bank_id` field distinguishes competing blocks in the same slot.
- **Skip rate** post-migration ≈ 1.0–1.6 % [RPC].

## Limits and fees

- **Block limit:** 100 M CU blocks (SIMD-0286) scaled by SIMD-0525 → **50 M CU per block** at 200 ms.
- **Per-writable-account limit:** 40 % of the block limit (SIMD-0306) → **20 M CU per account**.
- **Fees:** base fee 5000 lamports/signature, 50 % burned. SIMD-0096 is active (100 % of the priority fee to the leader).
- **Not active:** SIMD-0553 (resource-fee burn) [RPC].

## Client landscape at capture time ([RPC] `getClusterNodes.clientId` × `getVoteAccounts` stake)

| clientId | stake % | version | top validator (≈ leader slots/epoch) |
|---|---|---|---|
| AgaveBam | 36.45 | 4.3.2 | DRpbCBMx… (≈12.4k) |
| JitoLabs | 23.03 | 4.3.2 | HEL1USMZ… (≈15.8k) |
| HarmonicAgave | 21.13 | 4.3.2 | Fd7btgyS… (≈16.9k) |
| HarmonicFiredancer | 8.70 | 26.10.4 | JUPiTERr… (≈9.6k) |
| Firedancer | 6.70 | 26.10.4 | EvnRmnMr… (≈7.7k) |
| FireBAM | 1.56 | 26.10.4 | 9jxgosAf… (≈4.4k) |
| Rakurai | 1.17 | 4.3.2 | ana2y2Yv… (≈2.2k) |
| Agave | 1.11 | 4.3.2 | 7QQGNm3p… (≈1.9k) |
| Raiku | 0.08 | 4.3.2 | 9xcXe4WR… |

Caveats:
- **BAM** was put in maintenance mode before activation. Its validators fell back to the regular Jito Block Engine, and BAM nodes are returning gradually ([bam.dev changelog](https://bam.dev/blog/bam-changelog-sept-23-oct-9/)). So `clientId = AgaveBam` does **not** prove a block was BAM-assembled. This must be detected per window, not assumed.
- **Leader schedule** can be keyed by vote account (`keyByVoteAccount`, Agave 4.3).
- **No multiple concurrent leaders** on mainnet; Constellation is still a proposal.
- **TPU** is QUIC-only since Agave 4.0. The greedy scheduler has been the default since Agave 4.1. The external-scheduler interface is at v5 in 4.4.
