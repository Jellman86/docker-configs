# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

FROM rust:1.89.0-bookworm@sha256:c9ac3fa8945b61dede1e4500d25028aa8fd8a8fe46365fcf9c0422f8d999b9b0 AS spider-builder

ARG SPIDER_COMMIT=de35b3a9dd740542070fa2ee0e70bc804dde07ee
ARG SPIDER_SOURCE_SHA256=45a9e775ba8d0ec16b6f9d7f768c453c8528dc4dc6644eb0c6c93610823fee93

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        clang \
        cmake \
        curl \
        libssl-dev \
        patch \
        pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && rustup component add rustfmt

WORKDIR /build
RUN curl --fail --location --silent --show-error --retry 3 \
        --output spider.tar.gz \
        "https://codeload.github.com/spider-rs/spider/tar.gz/${SPIDER_COMMIT}" \
    && echo "${SPIDER_SOURCE_SHA256}  spider.tar.gz" | sha256sum --check --strict \
    && mkdir spider \
    && tar -xzf spider.tar.gz --strip-components=1 -C spider \
    && rm spider.tar.gz

COPY hardening.patch /build/hardening.patch
WORKDIR /build/spider
RUN patch --batch --forward -p1 < /build/hardening.patch \
    && cargo fmt --all -- --check \
    && cargo test --locked -p spider_mcp --no-default-features --features chrome \
    && cargo build --locked --release -p spider_mcp --no-default-features --features chrome \
    && strip target/release/spider-mcp \
    && install -m 0755 target/release/spider-mcp /out-spider-mcp

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS proxy-builder

ARG MCP_PROXY_COMMIT=f1ae01420086011ae53e6d895b1cd02838b34f42
ARG MCP_PROXY_SHA256=e8b2c07638826e168e24083e684f4308256caa96de49f5f580f07ce41c92d65a

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl --fail --location --silent --show-error --retry 3 \
        --output mcp-proxy.tar.gz \
        "https://codeload.github.com/sparfenyuk/mcp-proxy/tar.gz/${MCP_PROXY_COMMIT}" \
    && echo "${MCP_PROXY_SHA256}  mcp-proxy.tar.gz" | sha256sum --check --strict \
    && mkdir mcp-proxy \
    && tar -xzf mcp-proxy.tar.gz --strip-components=1 -C mcp-proxy \
    && rm mcp-proxy.tar.gz

COPY mcp-proxy.uv.lock /build/mcp-proxy/uv.lock
WORKDIR /build/mcp-proxy
ENV UV_PROJECT_ENVIRONMENT=/opt/mcp-proxy
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13.13-slim-trixie@sha256:7ba5f5888fbe0014ab9edb2278922995c2201fc3752c46b0be24763eb46fa9f3

LABEL org.opencontainers.image.title="Hardened Spider MCP for Hermes" \
      org.opencontainers.image.description="Pinned Spider MCP with bounded public-web tools behind a pinned Streamable HTTP proxy" \
      org.opencontainers.image.source="https://github.com/spider-rs/spider" \
      org.opencontainers.image.revision="de35b3a9dd740542070fa2ee0e70bc804dde07ee" \
      org.opencontainers.image.licenses="MIT"

ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/mcp-proxy/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libssl3t64 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=proxy-builder /opt/mcp-proxy /opt/mcp-proxy
COPY --from=spider-builder /out-spider-mcp /usr/local/bin/spider-mcp

RUN spider-mcp --help >/dev/null

USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/opt/mcp-proxy/bin/mcp-proxy"]
CMD ["--help"]
