# Local single-node Solana cluster for integration tests: solana-test-validator + solana CLI
# from the official Agave v4.3.2 release (the mainnet release this project measures against).
#
# There is no official Docker image for Agave 4.x (anzaxyz/agave stops at 3.1.14), so we take the
# upstream release tarball, verify its SHA-256 and copy the three binaries we need, unmodified,
# into a slim runtime image. See docker/LOCALNET.md for usage.
#
#   docker build -f docker/localnet.Dockerfile -t itb-localnet:4.3.2 docker
#   docker run --rm --security-opt seccomp=unconfined -p 127.0.0.1:8899-8900:8899-8900 \
#       -p 127.0.0.1:8002:8002/udp itb-localnet:4.3.2 [--alpenglow]
# (seccomp=unconfined: Agave 4.x requires io_uring, which Docker's default seccomp profile blocks.)
#
# Base image pinned by digest for reproducibility (debian:bookworm-slim as pulled 2026-10-23).
# Bookworm ships glibc 2.36; the Agave binaries need >= 2.34. Every shared library they link
# (libc, libm, libgcc_s, libstdc++6, libudev1, libcap2) is already in bookworm-slim, so the
# runtime stage installs only tini.
ARG BASE_IMAGE=debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8

# ---------------------------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS fetch

ARG AGAVE_VERSION=v4.3.2
# SHA-256 of solana-release-x86_64-unknown-linux-gnu.tar.bz2 (84,744,766 bytes) for v4.3.2.
# Source: the asset digest GitHub publishes for the release
#   gh api repos/anza-xyz/agave/releases/tags/v4.3.2 --jq '.assets[].digest'
# cross-checked 2026-10-23 by downloading the asset and running sha256sum (identical).
# The release has no separate checksum file. Commit a203300045b405f86c9c84308b2eae76af69ac3b.
ARG AGAVE_SHA256=5c9599d7fa397375df69d58e8d4f550ee45463dd6d1ecad9e5a1f053ce8e0933

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl bzip2 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/agave
RUN curl -fsSL --retry 5 --retry-delay 3 -o solana-release.tar.bz2 \
      "https://github.com/anza-xyz/agave/releases/download/${AGAVE_VERSION}/solana-release-x86_64-unknown-linux-gnu.tar.bz2" \
 && echo "${AGAVE_SHA256}  solana-release.tar.bz2" | sha256sum -c - \
 && tar -xjf solana-release.tar.bz2 \
      solana-release/bin/solana-test-validator \
      solana-release/bin/solana \
      solana-release/bin/solana-keygen \
      solana-release/version.yml \
 && grep -qx "channel: ${AGAVE_VERSION}" solana-release/version.yml \
 && mkdir /out \
 && install -m 0755 solana-release/bin/solana-test-validator solana-release/bin/solana \
      solana-release/bin/solana-keygen /out/ \
 && install -m 0644 solana-release/version.yml /out/agave-version.yml

# ---------------------------------------------------------------------------------------------
FROM ${BASE_IMAGE}

# tini as PID 1: solana-test-validator does not handle SIGTERM itself, and as PID 1 it would
# ignore it, so `docker stop` would wait the full timeout and then SIGKILL.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

# Official release binaries, byte-for-byte (not stripped, so panics keep symbolised backtraces).
COPY --from=fetch /out/solana-test-validator /out/solana /out/solana-keygen /usr/local/bin/
COPY --from=fetch /out/agave-version.yml /usr/local/share/agave-version.yml
COPY --chmod=0755 localnet-entrypoint.sh /usr/local/bin/localnet-entrypoint

# Non-root user; it owns the ledger directory so the anonymous volume inherits that ownership.
RUN useradd --uid 10001 --user-group --create-home --home-dir /home/solana \
      --shell /usr/sbin/nologin solana \
 && mkdir /ledger && chown solana:solana /ledger
USER solana
WORKDIR /home/solana
VOLUME ["/ledger"]

# Port contract (fixed by the entrypoint; keep in sync with docker-compose.yml):
#   8899/tcp  JSON-RPC          8900/tcp  RPC PubSub (WebSocket)
#   8000-8029 tcp+udp gossip / TVU / TPU (TPU QUIC = 8002/udp)   9900/tcp faucet
EXPOSE 8899/tcp 8900/tcp 8002/udp 8000/tcp 8000/udp 9900/tcp

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/localnet-entrypoint"]
CMD []
