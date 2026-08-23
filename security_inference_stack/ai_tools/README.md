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
| `openviking` | Shared hierarchical memory and MCP | Private OpenViking network and `npm_proxy_backends` |
| `openviking-bootstrap` | One-shot least-privilege tenant provisioning | Private OpenViking network only |
| `openviking-ollama` | Private embedding model server | Private OpenViking network only |
| `openviking-ollama-model` | One-shot embedding-model pull | Private OpenViking network only |
| `rusty-imap-mcp` | iCloud IMAP/SMTP MCP with non-destructive limits | `general_brg` and a dedicated private network; no host port |

No service publishes a host port. `general_brg` and `npm_proxy_backends` are
external networks. The stack-owned `ai_tools_research_private` network carries the browser and
the egress proxy.

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
panel. Mark `RUSTY_IMAP_MCP_IMAP_PASSWORD`,
`OPENVIKING_ROOT_API_KEY`, `OPENROUTER_API_KEY`, both OpenViking key seeds, and
both derived user keys as secrets. Never commit generated keys or `.env.dockhand`.

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

Public web traffic from Playwright crosses the non-caching Squid gateway, which
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
- Browser, mail, memory, and embedding services publish no host
  ports and mount neither a host workspace nor the Docker socket.
- Persistent OpenViking data remains under `/mnt/apps/docker`; removing the old
  `/mnt/apps/docker/hermes` directory is a separate manual cleanup decision.

## Deployment and rollback

Deploy only through Dockhand after the Git change has reached the configured
branch.

Changing the embedding model or its dimension invalidates the existing vector
collection: OpenViking refuses to start with
`EmbeddingRebuildRequiredError`. Stop the service, move
`data/vectordb/context` aside, start it so a fresh collection is created at the
new dimension, then rebuild vectors with
`POST /api/v1/content/reindex` (`mode: vectors_only`) against
`viking://user/<user>/peers/<user>`. Memory content under `data/viking` is not
touched by this.

Rollback by reverting the relevant Git change and repeating the Dockhand
sync/deploy workflow. Restore a persistent store only from a verified backup
and only after stopping the affected service through Dockhand.

## Verification

1. Confirm `hermes-agent` is absent and no service publishes a host port.
2. Confirm all long-running services are running and healthy.
3. Confirm `openviking-ollama-model` and `openviking-bootstrap` exit successfully.
4. Confirm OpenViking rejects unauthenticated requests and accepts an
   authenticated memory search/remember request through the compatibility URL.
5. Confirm Playwright can load a harmless public page but private, loopback,
   link-local, and metadata targets fail.
6. Confirm the IMAP MCP health endpoint responds from a trusted `general_brg`
   client and message body fetches do not set `\\Seen`.
