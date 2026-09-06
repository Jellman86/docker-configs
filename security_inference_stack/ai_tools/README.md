# AI tools on Quark

This standalone Git-backed Dockhand stack runs Hermes and shared AI support
services. It is intentionally separate from
`security_inference_stack/docker-compose.yml`, so tool upgrades do not recreate
Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

The stack was renamed from `hermes_agent` to `ai_tools` when Hermes was retired.
Hermes was restored on 2026-09-06 using its retained state and model login;
OpenViking's existing data directories and least-privilege tenant keys are unchanged.

## Hermes dashboard and integrations

- Private URL: `https://hermes.pownet.uk`; UniFi static A record points to Quark
  at `192.168.213.102`. Do not add a public DNS record or Cloudflare Tunnel route.
- Quark NPM terminates TLS with the existing `*.pownet.uk` certificate and proxies
  HTTP/WebSockets to `hermes-dashboard:9119` on `npm_proxy_backends`. This alias
  ensures requests arrive from the dedicated proxy network trusted by Hermes.
- Hermes enforces its own password login. NPM additionally restricts the route
  to private LAN and Tailscale source ranges. API server and external messaging
  adapters remain disabled. Existing dashboard credentials are stored in Dockhand.
- The pinned upstream image runs s6 bootstrap as root, then gateway/dashboard
  as UID/GID 1000. It is resource-limited, has no host ports or Docker socket,
  and keeps state at `/mnt/apps/docker/hermes`. Never share this directory
  with a second gateway. Back it up before upgrades.
- Read-only managed config in `managed/config.yaml` supplies operational rules,
  manual approvals, the existing SSH terminal backend, browser/mail/memory MCP,
  native OpenViking memory and optional native Home Assistant tools. SSH uses
  the existing dedicated key; its account permissions remain a trust boundary,
  not a read-only sandbox. No sudo password is injected.
- `HASS_TOKEN` is a dedicated Home Assistant long-lived token supplied through
  Dockhand secrets. It enables the native `ha_*` tools. Upstream v2026.8.31 also
  forces an idle HA event connection despite `enabled: false`; its lazy platform
  loader bypasses plugin disabling. Pinned empty event filters and `watch_all:
  false` drop all events, preventing unsolicited agent runs. Do not test it by
  toggling devices.
- The historical `hermes/hermes` identity and `hermes` agent scope remain fixed.
  MCP additionally sends `X-OpenViking-Agent: hermes`. Never pass root/recovery
  keys or seeds to Hermes. SearXNG and Spider remain retired.
- A Git deploy does not restart a container just because a read-only bind-mounted
  config changed. After such a change, use Dockhand's discovered container
  `POST /api/containers/{id}/restart?env={environmentId}` endpoint, then verify
  its new start time and effective config. Never use a direct Docker restart.
- Before publishing: run both unittest suites below, render Compose with
  placeholder secrets, verify the pinned image manifest, and review the diff.
  Deploy only through Dockhand. On 1.0.44, the running route implementation was
  checked: sync via `POST /api/git/stacks/{id}/sync`, then deploy via
  `POST /api/git/stacks/{id}/deploy` with `Accept: application/json`. Keep the
  connection open and require `success: true`; verify stack revision and health.
  The environment API accepts a replacement `variables` array, so GET/merge/PUT
  the full set and preserve secret flags. Revalidate these routes after upgrades.

```bash
python -m unittest discover -s security_inference_stack/ai_tools/tests -v
python -m unittest discover -s security_inference_stack/ai_tools/openviking -v
```

## Services

| Service | Role | Network exposure |
|---|---|---|
| `hermes-agent` | Authenticated agent dashboard, tools and shared memory | Private proxy network and internal tool networks; no host port |
| `playwright-mcp` | Isolated interactive browser MCP | `general_brg` and the private research network; no host port |
| `openviking` | Shared hierarchical memory and MCP | Private OpenViking network and `npm_proxy_backends` |
| `openviking-bootstrap` | One-shot least-privilege tenant provisioning | Private OpenViking network only |
| `openviking-ollama` | Private embedding model server | Private OpenViking network only |
| `openviking-ollama-model` | One-shot embedding-model pull | Private OpenViking network only |
| `rusty-imap-mcp` | iCloud IMAP/SMTP MCP with non-destructive limits | `general_brg` and a dedicated private network; no host port |

No service publishes a host port. `general_brg` and `npm_proxy_backends` are
external networks. Playwright reaches the public web directly over `general_brg`.

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
This is a data-compatibility identifier independent of the running agent. Changing
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

Playwright reaches the public web directly. The Squid egress gateway that
previously denied private, loopback, link-local, metadata, multicast, reserved
and Docker-internal destinations was removed on 2026-08-23, so the browser can
now reach the local network. Its remaining boundary is `--isolated`, the
`--allowed-hosts` list and `--block-service-workers`.

OpenViking is reached on the private LAN at:

```text
https://openviking.pownet.uk/mcp
```

The old `hermes.pownet.uk` memory compatibility URL was retired on 2026-08-23;
that hostname now serves the authenticated Hermes dashboard, not OpenViking.
Memory clients use `openviking.pownet.uk`, the shared least-privilege key and
the `X-OpenViking-Agent: hermes` header. That header and the `hermes/hermes`
account are a data-compatibility identity, not a hostname, and must not be
renamed - doing so makes existing encrypted memory unreadable. Never configure
a client with the root key.

## Security boundaries

- Playwright MCP owns an isolated ephemeral browser with a restricted
  `--allowed-hosts` list. Browser egress is no longer proxy-confined.
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

1. Confirm exactly one `hermes-agent` runs and no service publishes a host port.
2. Confirm all long-running services are running and healthy.
3. Confirm `openviking-ollama-model` and `openviking-bootstrap` exit successfully.
4. Confirm OpenViking rejects unauthenticated requests and accepts an
   authenticated memory search/remember request through `openviking.pownet.uk`.
5. Confirm Playwright can load a harmless public page.
6. Confirm the IMAP MCP health endpoint responds from a trusted `general_brg`
   client and message body fetches do not set `\\Seen`.
7. Confirm DNS resolves to Quark, TLS validates, anonymous dashboard API requests
   are denied, login works, and browser/mail/memory/HA tools are available.
