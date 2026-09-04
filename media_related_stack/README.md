# Media Stack

Git-backed Dockhand stack for Plex and Jellyfin playback plus Optimisarr media optimization on Riker.

## Services

| Service | Role | Published access |
|---|---|---|
| `plex` | Media server with Intel hardware transcoding | Host network; normally `32400` |
| `jellyfin` | Open-source media server with Intel hardware transcoding | Host network; HTTP `8096` |
| `optimisarr` | Media analysis, verification, and controlled optimization | `${OPTIMISARR_PORT:-8787}` |

## Topology and hardware

- Compose file: `media_related_stack/docker-compose.yml`
- Intended host: Riker / TrueNAS.
- Plex and Jellyfin use host networking for DLNA, discovery, and media-client
  compatibility. A reverse proxy must therefore target Riker's host address,
  not the `jellyfin` container name on `media_stack_default`.
- Optimisarr joins both its project default network and external `${ARR_NETWORK:-arr_stack_brg}` so it can resolve Radarr and Sonarr directly.
- Plex, Jellyfin, and Optimisarr receive `/dev/dri` for Intel QSV/VA-API.
  LinuxServer's Jellyfin entrypoint grants its `abc` user access to the mounted
  render device; Optimisarr separately receives `${RENDER_GID:-107}` as a
  supplementary group.

Confirm the iGPU device and host render-group ID before deployment to a new host.

## Private application access

Jellyfin is available to trusted-network clients at
`https://jellyfin.pownet.uk`. UniFi provides a private A record to Riker
(`192.168.213.101`), where Nginx Proxy Manager terminates the managed
`*.pownet.uk` certificate and proxies HTTP/WebSocket traffic to
`192.168.213.101:8096`.

This hostname is intentionally private-LAN ingress. Do not add a public DNS
record or Cloudflare Tunnel route without a separate exposure and
authentication review. Because Jellyfin uses host networking, keep the proxy
upstream on Riker's address rather than changing it to the Compose service
name.

### Jellyfin container and GPU research

Research was refreshed on 2026-08-10 against primary upstream documentation:

- [Jellyfin's container guide](https://jellyfin.org/docs/general/installation/container/)
  documents port `8096`, optional host networking for discovery/DLNA, bind
  mounts, and `/dev/dri` device access.
- [Jellyfin's Intel GPU guide](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/intel/)
  recommends Intel Quick Sync (QSV) on modern Intel Linux systems, the `iHD`
  driver, and `/dev/dri/renderD128` unless another render node is selected.
- [Jellyfin monitoring](https://jellyfin.org/docs/general/post-install/networking/advanced/monitoring/)
  defines `GET /health` as the HTTP/database readiness check and warns that it
  is unhealthy during startup migrations.
- [LinuxServer's Jellyfin image contract](https://docs.linuxserver.io/images/docker-jellyfin/)
  defines `lscr.io/linuxserver/jellyfin:latest`, `PUID`/`PGID`, `/config`,
  arbitrary media mounts, and automatic permissions for a mounted `/dev/dri`.

The LinuxServer image is intentional because it matches this stack's Plex
identity and permission conventions. The optional LinuxServer Intel OpenCL mod
is not enabled: ordinary QSV/VA-API transcoding does not require it. Introduce
that extra runtime dependency only after a separate HDR/Dolby Vision
tone-mapping test on this host.

## Persistent storage

| Host path | Container use |
|---|---|
| `${CONFIG_PATH:-/mnt/apps/docker/pms}` | Plex configuration, metadata, and identity |
| `${MEDIA_PATH:-/mnt/tank/media}` | Plex library at `/library` |
| `${IMMICH_PHOTOS_PATH:-/mnt/tank/photos}/library` | Immich storage-template originals, read-only in Plex at `/immich/library` |
| `${IMMICH_PHOTOS_PATH:-/mnt/tank/photos}/upload` | Immich non-template originals, read-only in Plex at `/immich/upload` |
| `${MEDIA_PATH}/transcode` | Plex transcode workspace |
| `${DOCKERCONFIGPATH:-/mnt/apps/docker}/jellyfin` | Jellyfin configuration, database, metadata, cache, and identity at `/config` |
| `${MEDIA_PATH:-/mnt/tank/media}` | The same media tree mounted read-only in Jellyfin at `/library` |
| `${DOCKERCONFIGPATH:-/mnt/apps/docker}/optimisarr` | Optimisarr configuration and database |
| `${DATAPATH:-/mnt/tank}` | Optimisarr `/data` tree |
| `${OPTIMISARR_WORKPATH:-/mnt/tank/.optimisarr/work}` | Optimisarr work area |
| `${OPTIMISARR_TRASHPATH:-/mnt/tank/.optimisarr/trash}` | Optimisarr quarantine/trash area |

Optimisarr's `/data`, `/work`, and `/trash` paths must remain on the same filesystem so replacement uses atomic moves rather than copy-and-delete. Preserve the Plex and Jellyfin config directories to retain their server identities and libraries.

Plex receives only Immich's two original-asset trees, both read-only. Its
`Photos` library should include both `/immich/library` and `/immich/upload`.
Do not expose Immich's `thumbs`, `encoded-video`, `backups`, or `profile`
directories: those are generated or application-internal data, not photo
library sources. Plex may display Immich's UUID/hash folders in its folder
view; Immich remains the system of record and files must not be changed through
Plex.

Jellyfin deliberately receives the shared media tree read-only. Playback,
scanning, metadata stored under `/config`, and transcoding still work, while a
Jellyfin account or plugin cannot delete Plex's source media. Saving NFO files,
downloaded subtitles, or artwork beside media will not work; granting write
access requires a separate review and explicit removal of `read_only: true`.

## Environment

Common settings:

- `PUID`, `PGID`, `TZ`, `UMASK`
- `CONFIG_PATH`, `MEDIA_PATH`, `IMMICH_PHOTOS_PATH`, `DOCKERCONFIGPATH`, `DATAPATH`
- `ARR_NETWORK`, `RENDER_GID`, `LIBVA_DRIVER_NAME`
- Optimisarr image, port, logging, work, and trash overrides

`PLEX_CLAIM` is sensitive and normally needed only when claiming a new Plex server. Store it as a Dockhand secret and remove or rotate it after use according to Plex guidance.

## Deployment and updates

Use the repository-level Git/Dockhand procedure in the [root README](../README.md). Optimisarr may drain active work for up to two hours; its `stop_grace_period` is intentionally long. Do not retry or bypass a Dockhand deployment while graceful shutdown is in progress.

After deployment, verify:

1. Plex responds at `/identity`, retains its libraries, and can access `/dev/dri`.
   Confirm `/immich/library` and `/immich/upload` are present as read-only
   mounts, then create or retain one `Photos` library named `Immich Photos`
   with both paths and scan it.
2. Jellyfin reaches `http://localhost:8096/health`, completes its setup wizard,
   and adds the existing folders below `/library` without changing them.
3. `https://jellyfin.pownet.uk/health` returns `Healthy`, the certificate is
   valid for the hostname, and the web UI loads after its root redirect.
4. In Jellyfin's Dashboard, open Playback > Transcoding, select **Intel Quick
   Sync (QSV)**, use `/dev/dri/renderD128`, and enable only codecs reported by
   the host. Compose exposes the GPU but cannot safely preconfigure this
   installation-specific setting.
5. Use the permitted read-only diagnostic `docker exec jellyfin
   /usr/lib/jellyfin-ffmpeg/vainfo` and then force one lower-bitrate playback.
   Confirm the Jellyfin FFmpeg log selects QSV rather than a software encoder.
6. Optimisarr responds at `/api/health` and retains its database.
7. Optimisarr resolves Radarr/Sonarr on `arr_stack_brg`.
8. `/data`, `/work`, and `/trash` resolve to the intended same filesystem.
9. A representative Optimisarr hardware-transcode check uses the expected Intel device before enabling automated work.

## Rollback

Revert the Git/image change, push, and redeploy through Dockhand. Do not interrupt an active Optimisarr replacement operation. Removing Jellyfin from Compose leaves its bind-mounted `/config` intact. Restore Plex, Jellyfin, or Optimisarr state only from a verified backup and only after services have been stopped through Dockhand.

## Security and operational notes

- Plex host networking exposes its normal service ports directly on Riker; control exposure with trusted-network firewalling and Plex authentication.
- Jellyfin host networking exposes `8096` and its discovery/DLNA listeners
  directly on Riker. Complete the setup wizard immediately, create a strong
  administrator credential, disable remote access until the reverse proxy and
  authentication policy are ready, and do not expose `/metrics` publicly.
- Back up Jellyfin's `/config`; LinuxServer notes that metadata for a large
  collection can grow beyond 50 GB.
- Optimisarr can modify media. Keep quality gates, free-space checks, and backup/recovery procedures enabled.
- Do not move Optimisarr work/trash to a different filesystem without reviewing replacement safety.
- Further migration details are in [`ARR_STACK_MIGRATION.md`](../ARR_STACK_MIGRATION.md).
