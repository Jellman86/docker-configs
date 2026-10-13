# docker-configs
Personal Docker Compose stacks consolidated on Quark, the Fedora server.
Most stacks expect external networks and overrides in Dockhand. Secrets belong
in its encrypted stack variables; never edit generated environment files.

## Repo layout
- [`autofpl/`](autofpl/README.md) - private, stateless autoFPL API on Quark.
- [`arr_vpn_stack/`](arr_vpn_stack/README.md) - Gluetun, qBittorrent, Prowlarr, Radarr, Sonarr, Byparr, Cleanuparr, Seerr, and the Gluetun restart guard.
- [`immich/`](immich/README.md) - self-hosted photo and video library on Quark.
- [`management/`](management/README.md) - Dockhand control plane.
- [`media_related_stack/`](media_related_stack/README.md) - Plex, Jellyfin, and Optimisarr.
- [`monitoring_management/`](monitoring_management/README.md) - Prometheus, SNMP Exporter, Unpoller, and Grafana.
- [`stirling_pdf/`](stirling_pdf/README.md) - self-hosted PDF toolkit on Quark.
- [`security_inference_stack/`](security_inference_stack/README.md) - Frigate, BirdNET-Go, Mosquitto, YA-WAMF, and Home Assistant.
- [`security_inference_stack/ai_tools/`](security_inference_stack/ai_tools/README.md) - independently deployed OpenViking, mail, browser, and web-research services.
- [`web_services/`](web_services/README.md) - host-specific Nginx Proxy Manager, Cloudflare Tunnel, and Tailscale stacks.

Each stack README documents its services, Compose path, host placement, ports,
networks, storage, variables, security assumptions, deployment checks, and
rollback boundary. Compose source remains authoritative if documentation and
runtime state ever differ.

## Current host layout

- `quark.pownet.uk` runs management, ingress, security/inference and the
  migrated media, arr, Immich and document stacks. Riker is retired.
- Use the four guarded Quark server variants documented in
  [`host/quark/`](host/quark/README.md). The base files retain legacy defaults.
- Immich's existing Quark ML worker remains separate from its server/database.
- `monitoring_management` is portable; its Dockhand definition determines its host.

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

The default cross-host network is:

- `general_brg`

Stacks should only require host-specific networks when the host actually runs
the related services. The security inference stack and the Quark web services
file run on `general_brg` only, which keeps Quark independent from the NAS
media/ARR networks.

Dockhand deploys one compose file per Git stack. Use the host-specific complete
compose file, not a multi-file override chain.

On Quark, set the web services Git stack compose path to:

```text
web_services/docker-compose.quark.yml
```

On Riker, where Nginx Proxy Manager and Tailscale need to reach ARR/media
containers directly, use the base web services Compose file (the explicit
`docker-compose.riker.yml` file is currently equivalent):

```text
web_services/docker-compose.yml
```

The Riker file attaches services to:

- `arr_stack_brg` through the internal compose key `vpn_stack_brg`
- `media_stack_default`

Override `NETWORK` only if the host uses a different ARR external network name.

## Configuration Notes

### Web Services
When chaining Cloudflare Tunnel (`cloudflared`) with Nginx Proxy Manager (`nginx-pm`), avoid redirect loops:
- If Nginx Proxy Manager has Force SSL enabled, point Cloudflare Tunnel at `https://nginx-rp:443` and disable TLS verification in Cloudflare.
- If Cloudflare Tunnel targets `http://nginx-rp:80`, disable Force SSL in Nginx Proxy Manager for that host and let Cloudflare handle edge redirects.
