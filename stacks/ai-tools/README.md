# AI tools on Quark

Deployment entrypoint: [`compose.yaml`](compose.yaml). See the [deployment map](../../docs/compose-layout.md) before changing a live project.

This standalone Git-backed Dockhand stack runs OpenKnowledge, the shared
Playwright browser MCP and SearXNG metasearch for agents. It is intentionally separate from
`stacks/home-automation/compose.yaml`, so tool upgrades do not recreate
Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

The active project name is `ai-tools`.

## Services

| Service | Role | Network exposure |
|---|---|---|
| `openknowledge` | AI-native markdown knowledge base, editor and MCP | `npm_proxy_backends` only; no host port |
| `playwright-mcp` | Isolated interactive browser MCP | `general_brg`; no host port |
| `searxng` | Private metasearch (HTML + JSON) for agents and humans | `general_brg` and `npm_proxy_backends`; no host port |

No service publishes a host port. `general_brg` and `npm_proxy_backends` are
external networks. Playwright reaches the public web directly over `general_brg`.

## Decommission: Hermes and OpenViking (2026-10-18)

Hermes, OpenViking (server, bootstrap, Ollama and its model job) and the
Hermes-only Rusty IMAP MCP were totally removed: containers, provisioning,
tests and persistent data. No archive was retained, at the owner's explicit
decision. The full rationale, replacement mapping and sequence are recorded
in OpenKnowledge at `agent-info/decommission-hermes-openviking`; the summary:

- OpenKnowledge now owns static knowledge: what exists on Quark, how to
  deploy, credentials, standing preferences, and project context. The
  durable OpenViking memory core (preferences, entity facts) was distilled
  into it first (`agent-info/preferences`, `agent-info/personal-and-projects`).
- The remaining memory corpus was episodic trajectories, dated events and
  evaluation rubrics, and several extracted memories already contradicted
  the live systems. Semantic recall over drifting summaries was producing
  confident wrong answers.
- OpenViking's Ollama embedding queue could block this stack's health
  gates for tens of minutes after any restart, and its tenant-key and
  embedding-rebuild machinery was disproportionate for a home lab.
- Hermes' unique surface was Telegram. Coding agents on the Mac and Quark
  cover the work side and are all wired to OpenKnowledge's MCP.
- Rusty IMAP MCP had no remaining consumer once Hermes was gone.

Restoring either service means a fresh deployment from this repo's Git
history, starting empty. There is no data rollback.

## Host preparation

Before the first OpenKnowledge deployment, create its project directory
(owned by UID/GID 1000):

```bash
install -d -m 0700 -o 1000 -g 1000 /mnt/apps/docker/openknowledge
```

## Dockhand stack

Create or migrate the Git stack with:

- Stack name: `ai_tools`
- Compose path: `stacks/ai-tools/compose.yaml`
- Context directory: the Compose file's directory/default
- Re-pull images: enabled
- Build images: enabled
- Force recreation: enabled for deliberate upgrades

One secret stack variable is required: `SEARXNG_SECRET` (SearXNG's
`server.secret_key`, via env override; never in `settings.yml` or Git). The optional non-secret sizing and
URL values are listed in [`.env.example`](.env.example). Never commit
generated keys or `.env.dockhand`.

Before publishing: run the unittest suite below, render Compose with
placeholder values, verify any pinned image manifest, and review the diff.
Deploy only through Dockhand. Sync via
`POST /api/git/stacks/{id}/sync`, then deploy via
`POST /api/git/stacks/{id}/deploy` with `Accept: application/json`. Keep the
connection open and require `success: true`; verify stack revision and health.
The environment API accepts a replacement `variables` array, so GET/merge/PUT
the full set and preserve secret flags. Revalidate these routes after upgrades.

```bash
python -m unittest discover -s stacks/ai-tools/tests -v
```

## Tool access

OpenKnowledge is available at:

```text
https://openknowledge.pownet.uk/        (editor)
https://openknowledge.pownet.uk/mcp     (agents)
```

Its private URL host resolves via UniFi to Quark at `192.168.213.102`. Do not
add a public DNS record or Cloudflare Tunnel route. The application has no
login of its own; reachability on the private LAN/Tailscale is the boundary,
accepted for this home lab service. NPM must preserve the client `Host`, set
`X-Forwarded-Proto: https`, allow WebSockets and never buffer `/mcp`. Agent
setup details are in [openknowledge/README.md](openknowledge/README.md).

SearXNG is available to containers on `general_brg` at
`http://searxng:8080`, and to trusted LAN/Tailscale agents and humans at:

```text
https://searxng.pownet.uk/
https://searxng.pownet.uk/search?q=<query>&format=json
```

Agents should use the JSON format. It has no login; private-network
reachability is the boundary, as for OpenKnowledge. Its settings live in
[`searxng/settings.yml`](searxng/settings.yml) (JSON enabled, limiter off so
programmatic clients are not rejected as bots, upstream valkey sidecar
deliberately omitted: it is only needed for the limiter). The image is the
newest stable upstream release pinned by digest; bump the tag and digest
together. A SearXNG instance was previously retired on 2026-08-23 as part of
the Hermes research stack; this one returns as a standalone agent tool.

Playwright MCP is available to containers on `general_brg` at:

```text
http://playwright-mcp:8931/mcp
```

Trusted LAN clients use the TLS proxy (NPM access list retained for this
pre-existing service):

```text
https://playwright-mcp.pownet.uk/mcp
```

Playwright reaches the public web directly. The Squid egress gateway that
previously denied private and internal destinations was removed on
2026-08-23, so the browser can now reach the local network. Its remaining
boundary is `--isolated`, the `--allowed-hosts` list and
`--block-service-workers`.

## Security boundaries

- Browser and knowledge services publish no host ports and mount neither a
  host workspace nor the Docker socket.
- Playwright MCP owns an isolated ephemeral browser with a restricted
  `--allowed-hosts` list.
- OpenKnowledge runs exactly one replica against its live git repository
  at `/mnt/apps/docker/openknowledge`.

## Deployment and rollback

Deploy only through Dockhand after the Git change has reached the configured
branch. Rollback by reverting the relevant Git change and repeating the
Dockhand sync/deploy workflow.

## Verification

1. Confirm all long-running services are running and healthy, and no service
   publishes a host port.
2. Confirm OpenKnowledge's editor loads, its MCP `initialize` plus a search
   succeed through `https://openknowledge.pownet.uk/mcp`, and its lint/audit
   tools report no problems.
3. Confirm Playwright can load a harmless public page, and a SearXNG
   `search?q=quark&format=json` returns results internally and through NPM.
4. Confirm `hermes-agent`, `openviking`, `openviking-ollama` and
   `rusty-imap-mcp` containers are absent.
