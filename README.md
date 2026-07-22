# docker-configs
Personal Docker Compose stacks used across the TrueNAS storage host and the
Fedora compute host. Most stacks expect external networks to exist and rely on
values provided via a local `.env` file.

## Repo layout
- `arr_vpn_stack/` - Gluetun VPN stack with qBittorrent, Prowlarr, Radarr, Sonarr, and FlareSolverr.
- `media_related_stack/` - Plex and Optimisarr.
- `monitoring_management/` - Prometheus, Grafana, SNMP exporter, and SNMP trap receiver.
- `security_inference_stack/` - Frigate, BirdNET-Go, Mosquitto, YA-WAMF, Home Assistant, and the opt-in Himalaya iCloud Mail client.
- `web_services/` - Nginx Proxy Manager, Cloudflare Tunnel, and Tailscale.

## Current host layout

- `riker.pownet.uk` / TrueNAS N100 NAS keeps the storage-local media stack:
  `arr_vpn_stack`, `media_related_stack`, and `web_services`.
- `dell-compute` / Fedora Core Ultra box runs compute-heavy and management
  stacks: `security_inference_stack` and `management` / Dockhand.

The Fedora host uses `/mnt/apps` for persistent Docker data:

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

The deployment sequence is:

1. Push the application and Compose commits and wait for CI, image smoke tests, and registry
   publication to succeed.
2. Discover the target through `GET /api/git/stacks`; verify its repository, branch, compose path,
   and `repullImages: true` setting.
3. `POST /api/git/stacks/{id}/sync`, then verify `lastCommit`, `syncStatus`, and `syncError` through
   `GET /api/git/stacks/{id}`.
4. `POST /api/git/stacks/{id}/deploy` with `Accept: application/json` and wait for `success: true`.
5. Verify the expected image and health through `GET /api/containers?env={environmentId}` and the
   application's health endpoint.

On Dockhand 1.0.35, the Git deploy endpoint performs a second safety sync. With `repullImages`
enabled it applies pull policy `always`, producing the API-owned equivalent of an
`up -d --remove-orphans --pull always`. A long request is expected when a service is draining under
`stop_grace_period`; do not retry or bypass it.

Notes:
- Most stacks expect environment overrides in Dockhand's stack configuration.
- Store secrets in Dockhand's encrypted secret variables. Never edit generated `.env.dockhand`
  files or the generated stack copy on a host.
- Docker CLI logs and inspection may be used for read-only diagnosis, but all lifecycle and image
  mutations go through Dockhand.
- On the Fedora compute host (`quark.pownet.uk` / `dell-compute`), use
  `DOCKERCONFIGPATH=/mnt/apps/docker`. The host's Docker engine data lives
  separately at `/mnt/apps/docker-engine`; do not use that path for app config
  bind mounts.

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
containers directly, use the base web services compose file:

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
