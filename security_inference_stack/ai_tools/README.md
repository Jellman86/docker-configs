# AI tools on Quark

This standalone Git-backed Dockhand stack provides shared AI support services
without running an agent runtime. It is intentionally separate from
`security_inference_stack/docker-compose.yml`, so tool upgrades do not recreate
Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

The stack was renamed from `hermes_agent` to `ai_tools` when the Hermes Agent
service was retired. OpenViking's existing data directories and least-privilege
tenant keys are deliberately retained, so the rename does not discard shared
memory or invalidate configured clients.

## Services

| Service | Role | Network exposure |
|---|---|---|
| `playwright-mcp` | Isolated interactive browser MCP | `general_brg` and the private research network; no host port |
| `research-egress` | Squid public-web policy gateway | Private research networks plus isolated egress |
| `spider-chromium` | Spider-only rendered-page browser/CDP | Private Spider browser network only |
| `spider-mcp` | Bounded scrape, link-map, and crawl MCP | Private Spider/research networks |
| `searxng` | Search JSON API | Private search/research networks |
| `openviking` | Shared hierarchical memory and MCP | Private OpenViking network and `npm_proxy_backends` |
| `openviking-bootstrap` | One-shot least-privilege tenant provisioning | Private OpenViking network only |
| `openviking-ollama` | Private embedding model server | Private OpenViking network only |
| `openviking-ollama-model` | One-shot embedding-model pull | Private OpenViking network only |
| `rusty-imap-mcp` | iCloud IMAP/SMTP MCP with non-destructive limits | `general_brg` and a dedicated private network; no host port |

No service publishes a host port. `general_brg` and `npm_proxy_backends` are
external networks. The stack-owned `ai_tools_research_private` network is also
used by autoFPL so it can reuse Spider and the research egress layer.

## Host preparation

Create the non-root persistent directories before the first OpenViking
deployment:

```bash
install -d -m 0700 /mnt/apps/docker/openviking
install -d -m 0700 /mnt/apps/docker/openviking-ollama
```

Both directories are owned by UID/GID 1000. OpenViking stores its configuration,
encrypted context database, and dedicated `codex_auth.json` under the first
path; Ollama stores the embedding model under the second.

OpenViking uses a separate ChatGPT/Codex device login. Place its token store at:

```text
/mnt/apps/docker/openviking/codex_auth.json
```

## Dockhand stack

Create or migrate the Git stack with:

- Stack name: `ai_tools`
- Compose path: `security_inference_stack/ai_tools/docker-compose.yml`
- Context directory: the Compose file's directory/default
- Re-pull images: enabled
- Build images: enabled
- Force recreation: enabled for deliberate upgrades

Copy the required values from the ignored `.env` into Dockhand's stack-variable
panel. Mark `RUSTY_IMAP_MCP_IMAP_PASSWORD`, `SEARXNG_SECRET`,
`OPENVIKING_ROOT_API_KEY`, both OpenViking key seeds, and both derived user keys
as secrets. Never commit generated keys or `.env.dockhand`.

The OpenViking account and shared user still use the historical `hermes` names.
This is a data-compatibility identifier, not a running Hermes service. Changing
it would make existing encrypted memory and client credentials inaccessible.
The bootstrap job creates or repairs the least-privilege `hermes/hermes` shared
user and the `hermes/codex` recovery user. The root key remains confined to
OpenViking and the short-lived bootstrap container.

Derive each user key locally from its dedicated seed with the v0.4.11 codec:

```python
import base64, hashlib

b64 = lambda value: base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

def user_key(user, seed):
    secret = hashlib.sha256(f"{user}\0{seed}".encode()).hexdigest()
    return f"{b64('hermes')}.{b64(user)}.{b64(secret)}"
```

The local embedding model is pulled automatically before OpenViking starts.
Neither OpenViking port 1933 nor Ollama port 11434 is published to the host.

## Tool access

Playwright MCP is available to containers on `general_brg` at:

```text
http://playwright-mcp:8931/mcp
```

Trusted LAN clients use the authenticated TLS proxy:

```text
https://quark.pownet.uk/mcp
```

Rusty IMAP MCP is available to trusted containers on `general_brg` at:

```text
http://rusty-imap-mcp:8080/mcp
```

Spider MCP and SearXNG remain on the private research network. autoFPL consumes
Spider there without publishing it to the host. Public web traffic from
Playwright, Spider, and SearXNG crosses the non-caching Squid gateway, which
denies private, loopback, link-local, metadata, multicast, reserved, and
Docker-internal destinations after DNS resolution.

OpenViking remains available through the existing private-LAN compatibility URL:

```text
https://hermes.pownet.uk/mcp
```

Only the `/mcp` route is retained; the former dashboard route no longer has a
backend. Existing clients should continue to use the shared least-privilege key
and `X-OpenViking-Agent: hermes` header until a separately planned endpoint and
tenant migration is completed. Never configure a client with the root key.

## Security boundaries

- Playwright MCP owns an isolated ephemeral browser and forces browser egress
  through Squid.
- Spider uses a separate Chromium process and cannot enumerate Playwright
  contexts.
- The hardened Spider MCP accepts absolute public HTTP/HTTPS URLs only, obeys
  robots.txt, strips caller-controlled proxy/cookie/browser targets, and caps
  scrape, link, crawl, depth, concurrency, and output sizes.
- Browser, mail, memory, search, CDP, and embedding services publish no host
  ports and mount neither a host workspace nor the Docker socket.
- Persistent OpenViking data remains under `/mnt/apps/docker`; removing the old
  `/mnt/apps/docker/hermes` directory is a separate manual cleanup decision.

## Deployment and rollback

Deploy only through Dockhand after the Git change has reached the configured
branch. For the one-time rename, take the old `hermes_agent` Compose project
down through Dockhand without volumes, update the Git-stack name and Compose
path, sync, and deploy `ai_tools`. Then redeploy autoFPL so it joins
`ai_tools_research_private`.

Rollback by reverting the relevant Git change and repeating the Dockhand
sync/deploy workflow. Restore a persistent store only from a verified backup
and only after stopping the affected service through Dockhand.

## Verification

1. Confirm `hermes-agent` is absent and no service publishes a host port.
2. Confirm all long-running services are running and healthy.
3. Confirm `openviking-ollama-model` and `openviking-bootstrap` exit successfully.
4. Confirm OpenViking rejects unauthenticated requests and accepts an
   authenticated memory search/remember request through the compatibility URL.
5. Confirm autoFPL is attached to `ai_tools_research_private` and can reach
   `spider-mcp:8080`.
6. Confirm Playwright can load a harmless public page but private, loopback,
   link-local, and metadata targets fail.
7. Confirm the IMAP MCP health endpoint responds from a trusted `general_brg`
   client and message body fetches do not set `\\Seen`.
