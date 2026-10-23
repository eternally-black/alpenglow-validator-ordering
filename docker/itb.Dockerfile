# The measurement binary `itb` (Rust). Built with the pinned toolchain and Cargo.lock; runs as non-root.
#
#   docker build -f docker/itb.Dockerfile -t itb:local .
#
# Keys are never baked in: mount them read-only at runtime (see docker-compose.yml, profile `live`).

FROM rust:1.97.1-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends pkg-config build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY crates ./crates
RUN cargo build --release --locked -p itb \
 && install -m 0755 target/release/itb /itb

# Same base image as docker/localnet.Dockerfile (digest-pinned).
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 itb
COPY --from=build /itb /usr/local/bin/itb
USER itb
WORKDIR /work
ENTRYPOINT ["/usr/bin/tini", "--", "itb"]
CMD ["--help"]
