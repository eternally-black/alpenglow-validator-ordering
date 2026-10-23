#!/bin/sh
# Entrypoint of the localnet image: run solana-test-validator with fixed, predictable ports.
#
# Agave 4.3.2's solana-test-validator has no --gossip-host: the address it advertises in gossip
# (and therefore in getClusterNodes: gossip, tpuQuic, ...) is its --bind-address, except that
# 0.0.0.0 / 127.0.0.1 are advertised as 127.0.0.1. To advertise an address that other containers
# can reach, we bind to this container's own IPv4 address on its network. Docker's port
# publishing forwards to that address, so the host reaches the same ports via 127.0.0.1.
# RPC (8899), PubSub (8900) and the faucet (9900) always listen on 0.0.0.0.
#
# Ports inside --dynamic-port-range are handed out sequentially from the bottom of the range, so
# in a fresh container the layout is deterministic: gossip 8000, TPU QUIC 8002 (see LOCALNET.md).
#
# Extra arguments (compose `command:` or `docker run ... IMAGE <args>`) are appended, e.g.
# --alpenglow, --ticks-per-slot N, --bpf-program ID FILE.SO. Override the bind/advertise
# address with LOCALNET_BIND_ADDRESS (it must be an address of this container).
set -eu

bind="${LOCALNET_BIND_ADDRESS:-}"
if [ -z "$bind" ]; then
    # `hostname -i` lists this container's addresses from /etc/hosts; take the first IPv4.
    bind="$(hostname -i | tr ' ' '\n' | grep -m1 -E '^[0-9]+(\.[0-9]+){3}$' || true)"
fi
if [ -z "$bind" ]; then
    echo "localnet: cannot determine this container's IPv4 address; set LOCALNET_BIND_ADDRESS" >&2
    exit 1
fi
echo "localnet: $(solana-test-validator --version); bind/advertise ${bind}; RPC :8899 WS :8900" >&2

exec solana-test-validator \
    --ledger /ledger \
    --reset \
    --quiet \
    --bind-address "$bind" \
    --gossip-port 8000 \
    --dynamic-port-range 8000-8030 \
    --rpc-port 8899 \
    --faucet-port 9900 \
    "$@"
