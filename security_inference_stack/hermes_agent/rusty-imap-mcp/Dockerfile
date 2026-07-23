# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder

ARG MCP_PROXY_COMMIT=f1ae01420086011ae53e6d895b1cd02838b34f42
ARG MCP_PROXY_SHA256=e8b2c07638826e168e24083e684f4308256caa96de49f5f580f07ce41c92d65a
ARG RUSTY_IMAP_MCP_VERSION=0.1.0
ARG RUSTY_IMAP_MCP_SHA256=784ab5b5295ff2412555c4a8a883e2f440c780dad588003162e7e311291c5c21

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

WORKDIR /build
RUN curl --fail --location --silent --show-error --retry 3 \
        --output rusty-imap-mcp.tar.gz \
        "https://github.com/randomparity/rusty-imap-mcp/releases/download/v${RUSTY_IMAP_MCP_VERSION}/rusty-imap-mcp-v${RUSTY_IMAP_MCP_VERSION}-x86_64-unknown-linux-gnu.tar.gz" \
    && echo "${RUSTY_IMAP_MCP_SHA256}  rusty-imap-mcp.tar.gz" | sha256sum --check --strict \
    && mkdir rusty-imap-mcp \
    && tar -xzf rusty-imap-mcp.tar.gz --strip-components=1 -C rusty-imap-mcp \
    && install -m 0755 rusty-imap-mcp/rusty-imap-mcp /out-rusty-imap-mcp

# The upstream x86-64 release is built on Ubuntu 24.04 and requires GLIBC_2.38.
FROM python:3.13.13-slim-trixie@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286

LABEL org.opencontainers.image.title="Rusty IMAP MCP for Hermes" \
      org.opencontainers.image.description="Pinned rusty-imap-mcp behind a pinned Streamable HTTP MCP proxy" \
      org.opencontainers.image.source="https://github.com/randomparity/rusty-imap-mcp" \
      org.opencontainers.image.version="0.1.0"

ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/mcp-proxy/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

COPY --from=builder /opt/mcp-proxy /opt/mcp-proxy
COPY --from=builder /out-rusty-imap-mcp /usr/local/bin/rusty-imap-mcp

RUN rusty-imap-mcp --version \
    && mkdir -p /var/lib/rusty-imap-mcp \
    && chown -R 65532:65532 /var/lib/rusty-imap-mcp

USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/opt/mcp-proxy/bin/mcp-proxy"]
CMD ["--help"]
