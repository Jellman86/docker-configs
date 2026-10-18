# Quark home lab

Docker Compose applications and native host configuration for Quark, the Fedora
server. This repository describes deployment; live application data and secrets
belong on the server and in Dockhand's encrypted variable store.

**Current state, 18 October:** the normalized layout is live and accepted across
12 Dockhand stacks and 32 running containers. Canonical NPM targets and private
DNS checks pass. The previous automatic Git schedules are restored. Private Forgejo and native T3 Code have NPM/UniFi routes; T3 also has private tailnet HTTPS. The separate
independent USB backup remains incomplete after recurrent transport errors; its
partial copy is preserved and the spare is unmounted pending investigation.

## Start here

- [Layout and naming](docs/compose-layout.md): stack boundaries, entrypoints and stable state.
- [Operations](docs/operations.md): validation, updates, checks and rollback.
- [Ingress and DNS](docs/ingress-dns.md): canonical URLs, NPM targets and UniFi records.
- [Quark host](host/quark/README.md): storage, restart guard, backups, SMB and Tailscale.
- [Upstream review](host/quark/UPSTREAM_REVIEW.md): supported contracts and deliberate tradeoffs.

## Repository structure

```text
stacks/<name>/
  compose.yaml          normal deployment entrypoint
  compose.base.yaml     reusable definitions, where needed
  README.md             services, variables, state and checks
  .env.example          non-secret examples, where useful
  ...                   application provisioning and policy tests
tools/                  manual maintenance, rehearsal and acceptance jobs
host/quark/             native host safeguards and example configuration
scripts/                repository validation
docs/                   operations, routing and the staged cutover
  history/              historical references, not current instructions
```

Each complete entrypoint can be selected directly in Dockhand. Its `extends`
references load the base definitions automatically. Do not deploy base files or
combine entrypoints with `-f` overlays. The separate photo worker uses
`stacks/immich/compose.ml.yaml` and project `immich-ml`.

## Applications

| Stack | Purpose |
|---|---|
| [management](stacks/management/README.md) | Dockhand control plane |
| [ingress](stacks/ingress/README.md) | Nginx Proxy Manager and Cloudflare Tunnel |
| [home-automation](stacks/home-automation/README.md) | Cameras, bird detection, MQTT and Home Assistant |
| [ai-tools](stacks/ai-tools/README.md) | OpenKnowledge, Playwright browser MCP and SearXNG |
| [arr](stacks/arr/README.md) | VPN, downloads, indexers and media requests |
| [media](stacks/media/README.md) | Plex, Jellyfin and Optimisarr |
| [immich / immich-ml](stacks/immich/README.md) | Photos, database/cache and Intel inference worker |
| [optimisarr-sidecar](stacks/optimisarr-sidecar/README.md) | Separate development worker |
| [stirling-pdf](stacks/stirling-pdf/README.md) | PDF and OCR toolkit |
| [forgejo](stacks/forgejo/README.md) | Private Git repositories, SQLite and SSH |
| [twenty](stacks/twenty/README.md) | Private research workbench |
| [autofpl](stacks/autofpl/README.md) | Optional API and analytics |
| [monitoring](stacks/monitoring/README.md) | Optional metrics and dashboards |

Names use lowercase kebab-case. Container/service names describe applications;
they do not repeat the physical host or an unnecessary `_stack` suffix. Existing
bind paths, shared networks and named volumes remain operational identities.
Renaming the repository does not justify copying data or creating replacement volumes.

## Validate and deploy

Render every manifest without contacting a Docker engine:

```sh
python3 scripts/validate-compose.py
```

The script supplies synthetic secrets and checks explicit project identities,
existing state volumes, bounded Docker logs and one-shot restart behavior. CI also
runs application and host policy tests. Required tooling is Python 3 and Docker
Compose v2; individual policy tests additionally use PyYAML.

Deployment follows **Git →
passing CI/image publication → Dockhand sync → Dockhand deploy → acceptance**.
All starts, stops, recreations and rollbacks go through Dockhand. Never use Docker
CLI lifecycle commands or edit generated `.env.dockhand` files. See the
[operations guide](docs/operations.md) for the API sequence and recovery limits.
