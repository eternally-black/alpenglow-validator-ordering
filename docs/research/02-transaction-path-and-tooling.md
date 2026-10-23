# Research note 02 — Transaction path, tooling, data sources

Compiled 2026-10-23. `[RPC]` = measured read-only against mainnet today.

## The path from our backend to the executing node

| Hop | What happens | Can reorder / delay / drop? | Source |
|---|---|---|---|
| RPC `sendTransaction` | Send-transaction-service retries every 2 s to `leader_forward_count = 2` leaders via `tpu-client-next`. Staked only if the RPC is peered via `--staked-nodes-overrides`. | Yes: hides send time and target, retries, picks leaders | [send_transaction_service.rs](https://github.com/anza-xyz/agave/blob/master/send-transaction-service/src/send_transaction_service.rs), [retry guide](https://solana.com/developers/guides/advanced/retry) |
| Direct QUIC → `tpuQuic` (unstaked) | Agave 4.3 limits: 3000 unstaked connections total, 8 per peer, 8 new connections/IP/min; **200 TPS per peer = 20 streams / 100 ms** | Throttle beyond 20 streams/100 ms | [quic.rs](https://github.com/anza-xyz/agave/blob/master/streamer/src/quic.rs), [stream_throttle.rs v4.3](https://github.com/anza-xyz/agave/blob/v4.3/streamer/src/nonblocking/stream_throttle.rs) |
| Gossip TPU address | **[RPC] TPU IP ≠ gossip IP for all AgaveBam (36.4 %), HarmonicAgave (21.1 %), HarmonicFiredancer (8.7 %), FireBAM; only 11/145 JitoLabs.** About 69 % of stake ingests through a BAM node or Harmonic "Remote TPU". | External builder decides order; limits and delays unknown | [relayer_stage.rs](https://github.com/jito-foundation/jito-solana/blob/master/core/src/proxy/relayer_stage.rs), [Harmonic docs](https://docs.harmonic.gg/) |
| Jito relayer (legacy) | Repo archived 2025-12-30; default `packet_delay_ms = 50` (200 ms historically) | Delay | [jito-relayer main.rs](https://github.com/jito-foundation/jito-relayer/blob/master/transaction-relayer/src/main.rs) |
| Non-leader forwarding | `ForwardingStage` forwards only packets from staked nodes, and non-votes only with `--staked-nodes-overrides`. **An unstaked tx sent to a non-leader is never forwarded.** | Drop | [forwarding_stage.rs](https://github.com/anza-xyz/agave/blob/master/core/src/forwarding_stage.rs) |
| Sigverify | Dedup filter resets every 2 s; under saturation drops packets below a scheduler-set priority floor | Drop | [sigverify_stage.rs](https://github.com/anza-xyz/agave/blob/v4.3/core/src/sigverify_stage.rs) |
| Agave container | Fixed capacity; when full the lowest priority is evicted | Drop | [transaction_state_container.rs](https://github.com/anza-xyz/agave/blob/master/core/src/banking_stage/transaction_scheduler/transaction_state_container.rs) |
| Agave scheduler | Greedy (default since 4.1), priority order, lock-conflict aware, 4 workers; **priority = reward × 10⁶ / (cost + 1)**. External schedulers pluggable since 4.0. | Rule under test | [transaction_priority.rs](https://github.com/anza-xyz/agave/blob/master/core/src/transaction_priority.rs) |
| Firedancer | quic → verify → dedup → pack (default strategy `balanced`) → bank | Rule under test | [default.toml](https://github.com/firedancer-io/firedancer/blob/main/src/app/firedancer/config/default.toml) |

- **Gossip fields:** UDP `tpu` is null since Agave 4.0 (UDP ingest removed); use `tpuQuic`.
- **Client id:** `clientId` is exposed by `getClusterNodes` [RPC].

## Tooling decisions

- **Sender:** Rust, `solana-tpu-client-next` 4.3.2.
  - Requires feature `agave-unstable-api`.
  - `create_pinned_leader_updater(addr)` pins one target; `leader_send_fanout` is also available.
  - Pin SDK crates to the versions Agave 4.3.2 uses (`solana-transaction ^4.2`, `solana-message ^4.5`, `solana-keypair ^3.1.2`) to avoid type mismatches.
- **TS / Python:** RPC only; no vetted QUIC TPU client.
  - A Python `aioquic` client would need ALPN `solana-tpu`, a self-signed ed25519 cert and one tx per unidirectional stream.
  - So we use Python only for analysis.
- **Entry boundaries** (txs in one entry execute in parallel) — no JSON-RPC method exposes them. Options:
  - **Old Faithful archive:** free; contains `Entry` nodes; available 10–20 h after the epoch ends.
  - **Yellowstone gRPC `entry` filter:** has `starting_transaction_index` and `executed_transaction_count`; live-only and paid (Helius Business+, Chainstack add-on, Alchemy PAYG).
  - **Bigtable `entries` table:** needs your own GCP credentials.
- **Local:** no official Agave 4.x Docker image (`anzaxyz/agave` stopped at v3.1.14). Build from the v4.3.2 release tarball. solana-test-validator covers parsing, v0/v1 decoding, pinned QUIC send and entry boundaries (ledger-tool / geyser).
- **Devnet:** Alpenglow live since 2026-09-25. Faucet: 2 req / 8 h (more with GitHub login), and it asks AI agents not to use it → **funding devnet is a human step**.

## RPC budget

- **Public mainnet:**
  - Documented: 100 req / 10 s, 40 per method, 40 concurrent connections.
  - **[RPC] `getBlock`: 6 / 10 s** (429, Retry-After 10). A full block is ≈ 2.9 MB.
  - WebSocket subscriptions: 10.
- **Helius free:** 1 M credits, 10 RPS, `sendTransaction` 1/s, WebSocket included.
- **Chainstack free:** 3 M RU, 25 RPS, no archive.

## Fees and cost model (for probe design)

- **Fees:**
  - Base 5000 lamports/signature, 50 % burned → reward share 2500.
  - Priority fee = ceil(µlamports/CU × CU limit / 10⁶), 100 % to the leader.
  - v1 txs carry a lamport-total `priorityFee`.
- **Cost model:**
  - 720 per signature, 300 per write lock, instruction data bytes / 4.
  - Plus the requested CU limit (builtins default 3000 CU per instruction).
  - Plus 8 CU per 32 KiB of loaded-accounts-data limit: the default 64 MiB costs **16,384**; `SetLoadedAccountsDataSizeLimit(32768)` costs **8**.
  - Execution: System transfer and each ComputeBudget instruction cost 150 CU.
- **Example probe:** transfer + 3 ComputeBudget ixs, limit 600, 32 KiB data limit → cost ≈ 1,935 (vs ≈ 18,300 with defaults).
  - With CU price 0, priority ≈ 2,500 × 10⁶ / 1,936 ≈ 1.29 M. Moving priority noticeably needs priority fees on the order of the 2,500-lamport base share.
- **Rent-exempt minimum** for a 0-byte account: **650,240 lamports** [RPC]. Query at runtime (SIMD-0437 steps continue in 4.4).
- **Budget:** 0.05 SOL ≈ 9,900 base-fee-only probes.

### Verified by mainnet `simulateTransaction` (2026-10-23; sigVerify off, nothing sent)

| Probe | Result |
|---|---|
| SetCULimit(600) + SetCUPrice(1000) + SetLoadedAccountsDataSizeLimit(32768) + Transfer(0 → fresh non-existent pubkey) | **success**, 600 CU consumed, fee 5001 |
| same, but transfer to self | success, 600 CU |
| same ixs with SetCULimit(450) | **fails: ComputationalBudgetExceeded** at the transfer (450 CU used) |
| SetCULimit(600) + Transfer only | success, 300 CU |

Consequences:
- **Every instruction costs 150 CU, ComputeBudget ones included.** So a 3-CB-ix + transfer probe needs L ≥ 600.
- **The 0-lamport transfer to a non-existent account works.** Conflict "locks" therefore cost no rent.
- **Keep the instruction set identical across probes,** with the "default" loaded-data level written explicitly as 64 MiB. Then the data-bytes and execution cost stay constant and only L, p and D vary.

Script: [`scripts/sim_probe.py`](../../scripts/sim_probe.py).

## Errata (from the v1 plan reviews, source-checked by Fable at agave v4.3.2)

- **Unstaked limits:**
  - `DEFAULT_MAX_UNSTAKED_CONNECTIONS = 2000` (not 3000).
  - The 20-streams/100 ms throttle applies **per connection**, and excess streams are **delayed** (`throttle_stream` sleeps), not dropped.
  - `DEFAULT_MAX_CONNECTIONS_PER_IPADDR_PER_MINUTE = 8`: excess connections are **silently ignored** (`incoming.ignore()`), which the client sees as a handshake timeout.
  - Other limits: idle timeout 30 s; `wait_for_chunk_timeout` 2 s.
- **No coalescing:** each QUIC stream becomes `PacketBatch::Single` and is forwarded immediately. There is no 5 ms coalesce.
- **Pinned updater:** `create_pinned_leader_updater` is behind Cargo feature **`dev-context-only-utils`**, not `agave-unstable-api`. Implement our own `LeaderUpdater`, or our own thin `quinn` sender.
- **Agave pre-window handling** (`decision_maker.rs`; constants in solana-sdk `clock`):
  - `Forward` (drop unparsed) when ≥ `HOLD_TRANSACTIONS_SLOT_OFFSET = 20` slots before the window;
  - `ForwardAndHold` (buffer) when within 20 slots;
  - `Hold` when within 2 slots;
  - `Consume` with a working bank.
  - The container is cleared on `Forward`.
- **Firedancer pending transactions:** pack keeps pending txs while not leader (`max_pending_transactions = 65524`, lowest-profit eviction) until blockhash expiry. QUIC idle timeout 10 s, Retry enabled.
