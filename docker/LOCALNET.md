# Localnet: single-node test validator (Agave v4.3.2)

`solana-test-validator` and the `solana` / `solana-keygen` CLIs from the official
[Agave v4.3.2 release](https://github.com/anza-xyz/agave/releases/tag/v4.3.2), the mainnet
release. The tarball is SHA-256 pinned in `localnet.Dockerfile` and the binaries are copied in
unmodified. The image is about 205 MB unpacked (69 MB compressed) and runs as a non-root user.
It starts with a fresh ledger every time (`--reset`, anonymous volume) and Alpenglow active at genesis.

## Start / stop

```sh
docker compose --profile localnet up -d --build --wait localnet   # healthy in ~7 s
docker compose --profile localnet down -v                         # stop and drop the ledger volume
docker compose --profile localnet exec localnet tail -f /ledger/validator.log   # --quiet: logs go here (~4 MB/min)
```

The service needs `security_opt: seccomp=unconfined`, which is already set. Agave 4.x panics with
`assertion failed: io_uring_supported()` when Docker's default seccomp profile blocks io_uring.

## Ports and addresses

| Port | Proto | Host (`127.0.0.1`) | Purpose |
|---|---|---|---|
| 8899 | tcp | published | JSON-RPC |
| 8900 | tcp | published | RPC PubSub (WebSocket) |
| 8002 | udp | published | TPU QUIC (`tpuQuic`) |
| 8000–8017 | udp/tcp | internal | gossip 8000, TVU 8001, TPU-forwards QUIC 8003, … |
| 9900 | tcp | internal | faucet (used by `requestAirdrop`) |

The validator binds to, and advertises, its own IP on the compose network. As a result,
`getClusterNodes` reports for example `"tpuQuic":"172.24.0.2:8002"`.

- **Other compose services** can use those addresses as reported, or `localnet:8899` / `localnet:8002`.
- **Host clients** reach the same ports on `127.0.0.1`. Docker Desktop cannot route to the
  container IP, so a host-side QUIC sender has to swap the IP in `tpuQuic` for `127.0.0.1`
  (the port stays the same).

Ports are allocated sequentially from `--dynamic-port-range 8000-8030`, so the layout is the
same on every start. The entrypoint sets this; `command:` in compose appends further flags.

## Verified (2026-10-23, Docker Desktop, engine 29.7.2, WSL2 backend)

- `getVersion` → `solana-core 4.3.2`, feature-set 3383571666.
- `getSlot` advances. `requestAirdrop` of 2 SOL to a fresh pubkey, then `getBalance` = 2000000000.
- **Slot time is ~400 ms, not 200 ms.** Measured over a 20 s window:

  | Mode | Slot time | Finalized lag |
  |---|---|---|
  | `--alpenglow` (the default here) | 370 ms/slot | 0 slots |
  | TowerBFT (no flag) | 400 ms/slot | ~31 slots |
  | `--clone-feature-set` (mainnet features) | 385 ms/slot | — |

  Under Alpenglow, blocks carry no vote transactions.
- **`getBlock` with `maxSupportedTransactionVersion: 1`** succeeds. The value is not validated
  (2 is accepted too), and only legacy transactions were present. Decoding a real v1
  transaction was not exercised, because the 4.3.2 CLI cannot build one.
- **TPU QUIC:**
  - From the host, `127.0.0.1:8002/udp` answers QUIC version negotiation.
  - From a sibling container, `solana program write-buffer` sent 75 transactions over QUIC to
    the advertised `tpuQuic`. The validator logged 1 new unstaked connection and 75 streams.

## Feature gates vs mainnet (checked 2026-10-23 with `solana feature status`)

| Gate | mainnet | localnet default (`--alpenglow`) | without `--alpenglow` |
|---|---|---|---|
| `A1pengvuM6JEcyNuTnMqepBKhwHE3N6PmUrdATGawhJS` Alpenglow (SIMD-0326) | active since epoch 1064 (slot 459648000) | active at slot 0 | inactive (test validator deactivates it) |
| `txv1aq4pp281K9um3tnPgkfX8UqtFT6wcVW3hNezGLL` Transaction v1 (SIMD-0385) | active since epoch 1035 (slot 447120000) | active at slot 0 | active at slot 0 |

The test validator activates **all 287** features that 4.3.2 knows about. Mainnet has 252 active
and 35 inactive, so 35 features are active here but not on mainnet. Among them:

- base fee includes loaded-accounts data size (#30657)
- rent lamports-per-byte changes (SIMD-0437/0438)
- block revenue sharing (SIMD-0123)
- Alpenglow fast leader handover
- SBPF v0–v2 deploys disabled (SIMD-0500)
- account lock limit 128
- CPI nesting 8, Loader-v4, zk-token, blake3/sha512 syscalls

For exact mainnet parity, use `command: ["--clone-feature-set", "--url", "mainnet-beta"]`.
This was verified to give 0 differences, with Alpenglow active. It needs internet access at
startup and follows whatever mainnet has activated on that day.

## What it can and cannot test

**Can:**
- RPC and WebSocket clients, transaction building and signing, fees, and `simulateTransaction`
  (subject to the feature differences above)
- landing transactions over TPU QUIC at a known address
- `getBlock` / `getSignatureStatuses` collection
- airdrop-funded spend-ledger tests, at no cost

**Cannot:**
- Multiple leaders: there is a single node (100 % stake, always leader). It cannot exercise
  leader rotation, the leader schedule, forwarding, or stake-weighted QoS (its own RPC holds the
  only staked connection).
- Jito / BAM / Harmonic block engines, relayers, bundles, or Firedancer.
- Realistic congestion, skipped slots, or mainnet network latency.
- Mainnet's account state (only what `--clone` copies).

## Upgrading

Change `AGAVE_VERSION` and `AGAVE_SHA256` in `localnet.Dockerfile`. Get the digest with
`gh api repos/anza-xyz/agave/releases/tags/<tag> --jq '.assets[] | select(.name=="solana-release-x86_64-unknown-linux-gnu.tar.bz2") | .digest'`
and cross-check it with `sha256sum` on the downloaded tarball. Then re-run the checks above.
