# Rusty IMAP MCP sidecar

This image packages the attested `randomparity/rusty-imap-mcp` v0.1.0 Linux x86-64 release behind `sparfenyuk/mcp-proxy` v0.12.0 for Hermes-compatible Streamable HTTP.

## Supply-chain pins

- Rusty release archive SHA-256: `784ab5b5295ff2412555c4a8a883e2f440c780dad588003162e7e311291c5c21`
- MCP proxy source commit: `f1ae01420086011ae53e6d895b1cd02838b34f42` (v0.12.0)
- MCP proxy source SHA-256: `e8b2c07638826e168e24083e684f4308256caa96de49f5f580f07ce41c92d65a`
- Audited upgraded MCP proxy lock SHA-256: `bec6e6f2e7ca70eb25a76c42bd4b42a4c9387956a130f4a30b19f77db48ac322`
- Builder and runtime base images are pinned to manifest digests.

The Rusty release archive was additionally verified with GitHub artifact attestations before integration. The upstream v0.12.0 proxy lock had known vulnerable transitive versions as of 2026-07-23, so `mcp-proxy.uv.lock` was regenerated from that pinned source's declared constraints with `uv 0.11.31`, committed, and audited before deployment.

## Credential mapping

Dockhand must provide one secret variable:

```text
RUSTY_IMAP_MCP_IMAP_PASSWORD=<iCloud app-specific password>
```

The value is migrated from the former `ICLOUD_APP_PASSWORD` variable without being written to Git or printed. The current `ICLOUD_IMAP_LOGIN` value (`scott.powdrill@icloud.com`) becomes Rusty's non-secret `username` in `config.toml`; the duplicate `ICLOUD_EMAIL` value is no longer needed. Upstream Rusty supports host, port, and username in TOML rather than environment variables.

## Security boundary

- Rusty posture is `readonly`.
- Attachment download and raw message export are explicitly denied.
- No SMTP configuration or credential is present.
- Hermes independently allowlists only read/search/fetch and metadata tools.
- The container runs as UID/GID 65532 with a read-only root filesystem, all capabilities dropped, `no-new-privileges`, bounded resources/logs, and tmpfs-only writable storage.
- Port 8080 is available only on the private Compose network; no host port is published.
- IMAP mailbox selection uses `EXAMINE`; body fetches use `BODY.PEEK[]`, preserving unread state.

## Endpoint

Hermes connects to:

```text
http://rusty-imap-mcp:8080/mcp
```

The proxy status endpoint is `/status` and is used by the Compose healthcheck.
