# Compose layout and naming

Use `stacks/<name>/compose.yaml` for a normal deployment and put its README,
example variables, provisioning and tests beside it. Keep native host setup in
`host/`, repository checks in `scripts/` and manual one-shot work in `tools/`.
Never store live application data, generated Dockhand files or secrets here.

A stack represents an application or a small integrated system with a useful
update/rollback boundary. It is not a collection of everything using the GPU or
everything on one host. Avoid splitting every supporting container into a stack:
its database/cache belongs with its application. Shared ingress and the management
plane remain separate so an application update does not recreate either.

**Status:** normalized source and runtime identities accepted on 18 October 2026.
See the [cutover sequence and acceptance](cutover-plan.md).

## Deployment map

| Dockhand / Compose project | Git Compose path | Contents |
|---|---|---|
| `management` | `stacks/management/compose.yaml` | Dockhand |
| `ingress` | `stacks/ingress/compose.yaml` | NPM, Cloudflare connector |
| `home-automation` | `stacks/home-automation/compose.yaml` | Frigate, BirdNET-Go, MQTT, YA-WAMF, Home Assistant |
| `ai-tools` | `stacks/ai-tools/compose.yaml` | OpenKnowledge, Playwright browser MCP and SearXNG (Hermes/OpenViking retired 2026-10-18) |
| `arr` | `stacks/arr/compose.yaml` | VPN, downloads, indexers, requests and library management |
| `media` | `stacks/media/compose.yaml` | Playback servers and Optimisarr |
| `immich` | `stacks/immich/compose.yaml` | Photo server, private PostgreSQL and Valkey |
| `immich-ml` | `stacks/immich/compose.ml.yaml` | Independently operated Intel inference worker |
| `optimisarr-sidecar` | `stacks/optimisarr-sidecar/compose.yaml` | Separate development worker and pairing identity |
| `stirling-pdf` | `stacks/stirling-pdf/compose.yaml` | PDF application |
| `twenty` | `stacks/twenty/compose.yaml` | Research workbench |
| `autofpl` (optional) | `stacks/autofpl/compose.yaml` | API and optional analytics job |
| `monitoring` (optional) | `stacks/monitoring/compose.yaml` | Metrics, exporters and dashboards |

The photo worker remains explicit because it has its own hardware/resource and
restart boundary; it must still use a compatible Immich version. Home automation
is one integrated camera/bird/MQTT system: YA-WAMF consumes Frigate and BirdNET,
and Home Assistant uses its broker. AI tools have their own independent lifecycle.
This preserves the existing operational boundaries without multiplying stacks.

`compose.base.yaml` provides reusable definitions for guarded Quark entrypoints.
Compose `extends` loads these automatically. Do not deploy a base file or combine
base and entrypoint as overlays: that can restore unsafe restart policies.
Manual tools are not enabled by normal deployments. Bootstrap jobs have profiles
or successful one-shot exits; they are not unhealthy long-running applications.

## Stable state and connectivity

- Explicit top-level `name` matches Dockhand, which also supplies the project name.
- Existing service names remain DNS contracts. Keep short application names such
  as `radarr`, `frigate` and `immich-database`. A descriptive exception is
  service `cloudflared`, container `cloudflare-tunnel`.
- The typo-shaped YA-WAMF container name becomes `yawamf`; the old
  `yawamf-monalithic` network alias remains for existing proxy targets. Its
  upstream image repository name is unchanged.
- Shared `general_brg`, `npm_proxy_backends`, `arr_stack_brg` and
  `immich_backend` names remain stable. The arr bridge is external because media
  also uses it. Old underscores in these identities do not justify network churn.
- The existing sidecar configuration volume `optimisarr_sidecar_sidecar-config`
  and worker cache `immich_ml_model-cache` are explicit external volumes. A
  project rename must never silently substitute empty state. On a fresh host,
  restore/provision these through the managed deployment before using the stack.
- Other bind paths, UID/GID settings, API URLs, secrets and backup selection remain
  unchanged. In particular, do not rename `/mnt/apps/security_inference_stack`
  or a Docker volume directory as part of reorganizing this repository.

## Applying the rename on an existing host

First validate all resolved Compose models with the current non-secret overrides
and placeholder secret values; check persistent mounts, device access and ports.
Push to Git and require passing CI before changing Dockhand references.

Renaming only a Dockhand record is insufficient: running containers retain their
old Compose project labels. For a changed project name, record the current
configuration, stop/remove its old containers through Dockhand with
`removeVolumes: false`, rename the same Git-stack record through the API, update
its Compose path, sync and deploy through Dockhand. Its encrypted variables move
with that record. Never create a parallel stack over the same data. Inspect old
container absence, new project labels, mounts, named volumes and application health
before moving to the next stack. Keep the existing shared arr network external.

Stacks whose project names remain unchanged need only a path update and sync
when the resolved model is unchanged. They do not require a cosmetic recreation.
The management plane must remain available throughout the rollout. A rollback
uses the prior Git commit and reverse mapping through Dockhand, retaining all data.

## Upstream contracts

Docker documents [project-name precedence](https://docs.docker.com/compose/how-tos/project-name/),
[service DNS and external networks](https://docs.docker.com/compose/how-tos/networking/),
and [explicit volume names](https://docs.docker.com/reference/compose-file/volumes/).
Changing a project name changes default network/volume identity; it does not
rename or adopt existing containers automatically. The structure here keeps those
runtime contracts explicit rather than treating a directory move as a deployment.
