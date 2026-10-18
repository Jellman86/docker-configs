# docker-configs
Personal Docker Compose stacks consolidated on Quark, the Fedora server.
Most stacks expect external networks and overrides in Dockhand. Secrets belong
in its encrypted stack variables; never edit generated environment files.

## Structure and naming

- `stacks/<name>/compose.yaml`: normal deployment entrypoint, README and related configuration.
- `compose.base.yaml`: reusable service definitions, not a Quark deployment entrypoint.
- `compose.ml.yaml`: the explicitly separate Immich ML worker entrypoint.
- `tools/`: manual maintenance, database rehearsal and acceptance workloads.
- `host/quark/`: native storage, backup, routing and file-server configuration.
- `scripts/`: repository validation only.

Folder, Compose project and Dockhand stack names use lowercase kebab-case.
Service/container names describe the application, without host names or a `_stack`
suffix. Existing storage paths, named volumes and shared network identities are
operational state and are deliberately preserved. See [layout and rename guide](docs/compose-layout.md).

## Repo layout
- [`stacks/autofpl/`](stacks/autofpl/README.md) - private, stateless autoFPL API on Quark.
- [`stacks/arr/`](stacks/arr/README.md) - Gluetun, qBittorrent, Prowlarr, Radarr, Sonarr, Byparr, Cleanuparr, Seerr, and the Gluetun restart guard.
- [`stacks/immich/`](stacks/immich/README.md) - self-hosted photo and video library on Quark.
- [`stacks/management/`](stacks/management/README.md) - Dockhand control plane.
- [`stacks/media/`](stacks/media/README.md) - Plex, Jellyfin, and Optimisarr.
- [`stacks/monitoring/`](stacks/monitoring/README.md) - Prometheus, SNMP Exporter, Unpoller, and Grafana.
- [`stacks/stirling-pdf/`](stacks/stirling-pdf/README.md) - self-hosted PDF toolkit on Quark.
- [`stacks/home-automation/`](stacks/home-automation/README.md) - Frigate, BirdNET-Go, Mosquitto, YA-WAMF, and Home Assistant.
- [`stacks/ai-tools/`](stacks/ai-tools/README.md) - independently deployed OpenViking, mail, browser, and web-research services.
- [`stacks/ingress/`](stacks/ingress/README.md) - Nginx Proxy Manager and Cloudflare Tunnel; Tailscale is native on Quark.

Each stack README documents its services, Compose path, host placement, ports,
networks, storage, variables, security assumptions, deployment checks, and
rollback boundary. Compose source remains authoritative if documentation and
runtime state ever differ.

## Current host layout

- `quark.pownet.uk` runs management, ingress, security/inference and the
  migrated media, arr, Immich and document stacks. Riker is retired.
- Use the four guarded Quark server variants documented in
  [`host/quark/`](host/quark/README.md). The base service definitions use Quark defaults; deploy the guarded variants.
- Immich's existing Quark ML worker remains separate from its server/database.
- `monitoring` is portable; its Dockhand definition determines its host.

Existing Quark apps retain `/mnt/apps` paths through bind aliases backed by
`/mnt/services/quark` on the added apps SSD. Migrated Riker configs use
`/mnt/services/docker`. Fedora, developer workspaces and VM images stay on the
original SSD. Existing Quark stack overrides remain:

```bash
DOCKERCONFIGPATH=/mnt/apps/docker
SECURITY_EXPORT_PATH=/mnt/apps/security_inference_stack
PUID=1000
PGID=1000
RENDER_GID=105
LIBVA_DRIVER_NAME=iHD
```

Home Assistant in the security inference stack stores config under
`/mnt/apps/docker/homeassistant/config`, uses host networking for discovery,
and is available on Quark at:

```text
http://quark.pownet.uk:8123
```

Keep container config/state local to the host running the container. Use NAS
shares for long-lived exports or backups, not for SQLite-heavy `/config`
directories.

Intel GPU acceleration on the Fedora compute host is exposed through
`/dev/dri`. Services that use VA-API or Intel QSV should mount `/dev/dri`, set
`LIBVA_DRIVER_NAME=iHD`, and include the host render group with
`RENDER_GID=105`.

YA-WAMF uses its `dev-intel` runtime image on Quark. The security stack passes
both `/dev/dri` and `/dev/accel/accel0` through to the container so OpenVINO can
validate Intel GPU and NPU providers while keeping the same persistent
`/config` and `/data` mounts when runtime image families are switched. Quark
defaults `YAWAMF_INFERENCE_PROVIDER` to `intel_npu` for validation; set that
Dockhand stack variable to another supported provider when comparing runtimes.

## Deployment

Every Compose project is a Git-backed Dockhand stack. Git is the source of truth, and all image
pulls and container recreations must be performed through the Dockhand API on the server that owns
the stack. Do not run `docker pull`, `docker compose pull`, or `docker compose up` on a host.

The synchronous Git deployment API was verified against the installed Dockhand
`1.0.49` on 13 October 2026. Verify the installed version and route contract again
if the control plane is upgraded.

1. Push changes and wait for CI and any image publication to succeed.
2. Discover the stack through `GET /api/git/stacks`; verify repository, branch,
   Compose path, environment and `repullImages: true`.
3. `POST /api/git/stacks/{id}/sync` with `Accept: application/json`. Verify
   `lastCommit`, `syncStatus: "synced"` and no sync error with a fresh GET.
4. `POST /api/git/stacks/{id}/deploy` with `Accept: application/json`, no body.
   Keep the request open until it returns `success: true`. This performs the
   configured fresh pull and recreation. Never issue a second deployment while
   the first is running, or retry an ambiguous response without inspecting state.
5. Verify image references, running state, health and application behavior.

Container start, stop and restart operations also go through Dockhand. Native
Docker/containerd shutdown for cold storage maintenance follows the documented
host-maintenance sequence, retaining Dockhand and transport until engine stop.

Notes:
- Most stacks expect environment overrides in Dockhand's stack configuration.
- Store secrets in Dockhand's encrypted secret variables. Never edit generated `.env.dockhand`
  files or the generated stack copy on a host.
- Docker CLI logs and inspection may be used for read-only diagnosis, but all lifecycle and image
  mutations go through Dockhand.
- On the Fedora compute host (`quark.pownet.uk`), use
  `DOCKERCONFIGPATH=/mnt/apps/docker`. The host's Docker engine data lives
  separately at `/mnt/apps/docker-engine`; do not use that path for app config
  bind mounts.

### Validation and rollback

Before committing, parse every changed YAML file, render the affected Compose
model with non-secret validation placeholders, run stack-specific tests, and
review `git diff --check` plus the staged diff. Never retrieve a production
secret merely to make a local render pass.

For rollback, revert the relevant Git commit or restore a reviewed prior image
reference, push `main`, and redeploy through Dockhand. Persistent bind mounts
are not rolled back with container images; restore them only from a verified
backup and only after stopping the affected services through Dockhand.

## Environment variables
Common keys used across stacks include:
- `CONFIG_PATH`, `DOCKERCONFIGPATH`, `DATAPATH`, `DOWNLOADS_PATH`, `MEDIA_PATH` - host paths for persistent data
- `TZ` - time zone
- `PLEX_CLAIM`, `TUNNEL_TOKEN`, `NEW_DOMAIN_DNS_EDIT_CF`, VPN credentials, and service-specific secrets

Docker's environment file handling is documented here:
- https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/

## Networking assumptions

The common external bridge is `general_brg`. Quark's web stack also joins
`npm_proxy_backends` so NPM can reach the migrated application containers.
Tailscale runs on the host with its own interface and approved subnet/exit
routes; it has no Docker bridge or Compose service.

Dockhand deploys one complete Compose file per Git stack. For Quark ingress use
`stacks/ingress/compose.yaml`. Retired Riker ingress manifests are available in Git history.

## Configuration Notes

### Web Services
When chaining Cloudflare Tunnel (`cloudflared`) with Nginx Proxy Manager (`nginx-pm`), avoid redirect loops:
- When NPM forces HTTPS, use `https://quark.pownet.uk:443` as the tunnel origin, with the public hostname as HTTP Host and TLS server name. Keep TLS verification enabled.
- If using an HTTP origin instead, avoid an origin redirect back to the same public URL.

See [Quark configuration review](host/quark/UPSTREAM_REVIEW.md) for upstream contracts, intentional deviations, current deployment scope and remaining limitations.

## Twenty research workbench

[`stacks/twenty/`](stacks/twenty/) serves the research-only .NET/Svelte investing workbench on Quark through Git-backed Dockhand and private NPM ingress.
