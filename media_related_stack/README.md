# Media Stack

Git-backed Dockhand stack for Plex playback and Optimisarr media optimization on Riker.

## Services

| Service | Role | Published access |
|---|---|---|
| `plex` | Media server with Intel hardware transcoding | Host network; normally `32400` |
| `optimisarr` | Media analysis, verification, and controlled optimization | `${OPTIMISARR_PORT:-8787}` |

## Topology and hardware

- Compose file: `media_related_stack/docker-compose.yml`
- Intended host: Riker / TrueNAS.
- Plex uses host networking for discovery and media-client compatibility.
- Optimisarr joins both its project default network and external `${ARR_NETWORK:-arr_stack_brg}` so it can resolve Radarr and Sonarr directly.
- Both services receive `/dev/dri` for Intel QSV/VA-API. Optimisarr also receives `${RENDER_GID:-107}` as a supplementary group.

Confirm the iGPU device and host render-group ID before deployment to a new host.

## Persistent storage

| Host path | Container use |
|---|---|
| `${CONFIG_PATH:-/mnt/apps/docker/pms}` | Plex configuration, metadata, and identity |
| `${MEDIA_PATH:-/mnt/tank/media}` | Plex library at `/library` |
| `${MEDIA_PATH}/transcode` | Plex transcode workspace |
| `${DOCKERCONFIGPATH:-/mnt/apps/docker}/optimisarr` | Optimisarr configuration and database |
| `${DATAPATH:-/mnt/tank}` | Optimisarr `/data` tree |
| `${OPTIMISARR_WORKPATH:-/mnt/tank/.optimisarr/work}` | Optimisarr work area |
| `${OPTIMISARR_TRASHPATH:-/mnt/tank/.optimisarr/trash}` | Optimisarr quarantine/trash area |

Optimisarr's `/data`, `/work`, and `/trash` paths must remain on the same filesystem so replacement uses atomic moves rather than copy-and-delete. Preserve the Plex config directory to retain the server identity and libraries.

## Environment

Common settings:

- `PUID`, `PGID`, `TZ`, `UMASK`
- `CONFIG_PATH`, `MEDIA_PATH`, `DOCKERCONFIGPATH`, `DATAPATH`
- `ARR_NETWORK`, `RENDER_GID`, `LIBVA_DRIVER_NAME`
- Optimisarr image, port, logging, work, and trash overrides

`PLEX_CLAIM` is sensitive and normally needed only when claiming a new Plex server. Store it as a Dockhand secret and remove or rotate it after use according to Plex guidance.

## Deployment and updates

Use the repository-level Git/Dockhand procedure in the [root README](../README.md). Optimisarr may drain active work for up to two hours; its `stop_grace_period` is intentionally long. Do not retry or bypass a Dockhand deployment while graceful shutdown is in progress.

After deployment, verify:

1. Plex responds at `/identity`, retains its libraries, and can access `/dev/dri`.
2. Optimisarr responds at `/api/health` and retains its database.
3. Optimisarr resolves Radarr/Sonarr on `arr_stack_brg`.
4. `/data`, `/work`, and `/trash` resolve to the intended same filesystem.
5. A representative hardware-transcode check uses the expected Intel device before enabling automated work.

## Rollback

Revert the Git/image change, push, and redeploy through Dockhand. Do not interrupt an active Optimisarr replacement operation. Restore Plex or Optimisarr bind-mounted state only from a verified backup and only after services have been stopped through Dockhand.

## Security and operational notes

- Plex host networking exposes its normal service ports directly on Riker; control exposure with trusted-network firewalling and Plex authentication.
- Optimisarr can modify media. Keep quality gates, free-space checks, and backup/recovery procedures enabled.
- Do not move Optimisarr work/trash to a different filesystem without reviewing replacement safety.
- Further migration details are in [`ARR_STACK_MIGRATION.md`](../ARR_STACK_MIGRATION.md).
