#!/usr/bin/env bash
# End-to-end test against the local Agave 4.3.2 test validator (free; throwaway keys):
#   keys -> airdrop -> payer pool -> funding through the ledger -> design for the localnet leader ->
#   live stage-1 and stage-2 runs over QUIC -> outcomes -> analysis + archive verification.
#
#   docker compose --profile localnet up -d --build --wait localnet
#   bash scripts/e2e-localnet.sh
#
# Everything is written under data/scratch/e2e (git-ignored). Localnet slots are ~400 ms, single leader.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1 # Git Bash on Windows would otherwise rewrite container paths like /work/...

E2E=data/scratch/e2e
KEYS=$E2E/keys
rm -rf "$E2E" && mkdir -p "$KEYS" "$E2E/raw"
export ITB_KEYS_DIR=./$KEYS
host_path() { if command -v cygpath >/dev/null; then cygpath -wa "$1"; else realpath "$1"; fi; }
rpc() { curl -s http://127.0.0.1:8899 -H 'Content-Type: application/json' -d "$1"; }
live() { docker compose --profile live run --rm -T -e RPC_URL=http://localnet:8899 -e WS_URL=ws://localnet:8900 live "$@"; }

echo "== master key + airdrop"
docker run --rm --entrypoint solana-keygen -v "$(host_path "$KEYS"):/k" itb-localnet:4.3.2 \
  new --no-bip39-passphrase --silent --force -o /k/master.json >/dev/null
MASTER=$(docker run --rm --entrypoint solana-keygen -v "$(host_path "$KEYS"):/k" itb-localnet:4.3.2 pubkey /k/master.json)
rpc "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"requestAirdrop\",\"params\":[\"$MASTER\",10000000000]}" >/dev/null
sleep 3

echo "== payer pool + funding (through the spend ledger)"
docker compose --profile keys run --rm -T keys-init >/dev/null
COMMON=(--live --max-spend-sol 0.05 --ledger /work/$E2E/ledger.sqlite)
live setup fund --lamports-per-payer 5000000 "${COMMON[@]}"

echo "== design for the localnet leader"
IDENTITY=$(rpc '{"jsonrpc":"2.0","id":1,"method":"getIdentity"}' | python -c 'import json,sys;print(json.load(sys.stdin)["result"]["identity"])')
cat > $E2E/targets.json <<EOF
[{"identity": "$IDENTITY", "client_id": "Agave", "ingress": "direct", "tier": "core", "k_windows": 6, "t_windows": 2, "hs_windows": 2}]
EOF
live design --targets $E2E/targets.json --seed 1 --out $E2E/design.jsonl

echo "== wait for 200 slots of history (aged blockhashes)"
until [ "$(rpc '{"jsonrpc":"2.0","id":1,"method":"getSlot"}' | python -c 'import json,sys;print(json.load(sys.stdin)["result"])')" -gt 200 ]; do sleep 5; done

RUN=(--design $E2E/design.jsonl --out $E2E/raw --progress /work/$E2E/progress.jsonl --nominal-slot-ms 400 --concurrency 1)
echo "== stage 1 (K windows), live over QUIC"
live run "${COMMON[@]}" "${RUN[@]}" --stage 1 --max-windows 6
echo "== stage 2 (T + H windows), live over QUIC"
live run "${COMMON[@]}" "${RUN[@]}" --stage 2 --max-windows 4
echo "== sweep payers back"
live setup sweep "${COMMON[@]}"

echo "== analysis + archive verification"
PY=${PYTHON:-.venv/Scripts/python}; [ -x "$PY" ] || PY=python3
PYTHONPATH=analysis "$PY" -m itb_analysis.cli report --raw $E2E/raw --derived $E2E/derived
PYTHONPATH=analysis "$PY" -m itb_analysis.cli verify --raw $E2E/raw --source archive --sample 0
