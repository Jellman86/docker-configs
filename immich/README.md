# Immich

Self-hosted photo and video library for phone backup, browsing, search, and
sharing. Runs on Riker because the library lives next to pool storage and the
Alder Lake-N iGPU handles transcoding without borrowing Quark's compute.

## Services

| Service | Role | Network exposure |
|---|---|---|
| `immich-server` | API, web UI, and all background workers | `general_brg` + `immich_backend`; no host port |
| `immich-machine-learning` | CLIP search, face recognition, OCR | `immich_backend` only; **off by default** |
| `immich-redis` | Valkey job queue and cache | `immich_backend` only |
| `immich-database` | Postgres 14 + VectorChord | `immich_backend` only |

Upstream merged the old `immich-microservices` container into `immich-server`
in v1.118.0. Any compose file still carrying it is stale.

## Topology

Riker (`riker.pownet.uk`, TrueNAS) runs the stack. Only `immich-server` joins
the external `general_brg` bridge, with alias `immich-server`, so Nginx Proxy
Manager can reach it by name. The database, cache, and ML worker stay on the
stack's own `immich_backend` bridge and are unreachable from the proxy network.

`immich_backend` is a normal bridge rather than `internal: true` because the ML
worker downloads model weights and the server fetches reverse geocoding data on
first run.

Compose path for the Dockhand Git stack:

```text
immich/docker-compose.yml
```

## Private application access

The stack publishes no host port. Expose it with a UniFi private A record for
`immich.pownet.uk` pointing at Riker (`192.168.213.101`), then an Nginx Proxy
Manager proxy host targeting:

```text
http://immich-server:2283
```

Immich **cannot be served on a sub-path** - it must own the root of a
(sub)domain.

Three proxy settings are mandatory, and each fails silently if missed:

1. **Websockets Support** must be enabled, or the web UI reports
   `Server Status Offline | Version Unknown`.
2. **`client_max_body_size`** must be raised well above nginx's default, or
   large video uploads fail. Upstream's reference config uses `50000M`.
3. **Timeouts** must be raised from the default 60s, or uploads die mid-transfer.

Put the following in the proxy host's **Advanced** tab:

```nginx
client_max_body_size 50000M;
proxy_request_buffering off;
client_body_buffer_size 1024k;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
send_timeout 600s;
```

`proxy_request_buffering off` keeps the proxy from spooling entire videos to
disk before forwarding them, which both avoids filling the proxy and roughly
doubles upload speed.

This hostname is private-LAN ingress. Do not add a public DNS record or a
Cloudflare Tunnel route without a separate exposure and authentication review.

## Persistent storage

| Path | Contents | Pool |
|---|---|---|
| `${IMMICH_UPLOAD_PATH:-/mnt/tank/photos}` | Originals, thumbnails, transcodes, profile images, Immich's own DB dumps | `tank` (spinning, bulk) |
| `${IMMICH_DB_PATH:-/mnt/apps/docker/immich/postgres}` | Postgres data directory | `apps` (NVMe) |
| `model-cache` volume | ML model weights; re-downloadable | Docker volume |

Two rules that matter more here than in most stacks:

- **The database must not sit on a network share or the media pool.** Upstream
  states network shares are unsupported for the database, and this repository
  keeps database-heavy state local to its host. It is deliberately on the NVMe
  `apps` pool.
- **The upload tree must stay on one mount.** Thumbnails and transcodes add
  roughly 10-20% on top of the originals; splitting them breaks Immich's own
  backup assumptions.

The filesystem must be Unix-compatible with real ownership. ZFS qualifies.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `IMMICH_VERSION` | `v3` | Major-version metatag. Upstream now recommends pinning the major rather than tracking `release`, so a v4 never lands unattended |
| `IMMICH_DB_PASSWORD` | **none - required** | Postgres password. **Dockhand secret only.** Must be `A-Za-z0-9` with no symbols or spaces, because Immich builds a connection URL from it |
| `IMMICH_DB_USERNAME` | `postgres` | Upstream advises leaving this alone |
| `IMMICH_DB_NAME` | `immich` | Upstream advises leaving this alone |
| `IMMICH_UPLOAD_PATH` | `/mnt/tank/photos` | Media root |
| `IMMICH_DB_PATH` | `/mnt/apps/docker/immich/postgres` | Database directory |
| `IMMICH_TRUSTED_PROXIES` | `172.16.0.0/12` | Keeps real client IPs in the audit log instead of the proxy's address |
| `IMMICH_ML_URL` | `http://immich-machine-learning:3003` | Point at another host to run inference remotely |
| `RENDER_GID` | `107` | Riker's `render` group, owner of `/dev/dri/renderD128` |
| `TZ` | `Europe/London` | Container timezone |
| `IMMICH_SERVER_MEMORY_LIMIT` | `3g` | Server bound |
| `IMMICH_ML_MEMORY_LIMIT` | `4g` | ML bound; the worker is the memory-hungry component |
| `IMMICH_DB_MEMORY_LIMIT` | `2g` | Database bound |
| `IMMICH_REDIS_MEMORY_LIMIT` | `512m` | Cache bound |

`IMMICH_DB_PASSWORD` is the only secret and has **no default on purpose** -
this repository is public, so a default would publish a working credential.

## Hardware acceleration

Riker is an Intel N100 (Alder Lake-N, UHD Graphics, `i915`), with
`/dev/dri/renderD128` owned by group `render` (GID 107).

Upstream ships acceleration as separate `hwaccel.transcoding.yml` and
`hwaccel.ml.yml` overlay files combined with `-f`. Dockhand deploys a single
compose path and would never load a second file, so the relevant fragments are
**inlined**:

- `immich-server` gets `/dev/dri` and `group_add`, equivalent to upstream's
  `quicksync` transcoding profile.
- `immich-machine-learning` gets `/dev/dri`, the `c 189:* rmw` cgroup rule, and
  the `-openvino` image tag, equivalent to upstream's `openvino` profile.

Transcoding acceleration is low-risk and always on. OpenVINO inference is the
more fragile of the two on Alder Lake-N; if it misbehaves, drop the `-openvino`
suffix to fall back to CPU inference, which only slows the initial library scan.

## Machine learning is opt-in

`immich-machine-learning` sits behind the `machine-learning` Compose profile and
**does not start by default**.

Immich's documented minimum is 6 GB RAM, 8 GB recommended, and the ML worker
alone holds 2-4 GB resident. Riker has 15 GB total with roughly 3 GB available
and **no swap**, already serving Plex, Jellyfin, and the ARR stack. Starting the
worker there would either force ZFS ARC down to its floor or trip the OOM
killer against services that matter more.

Three ways forward, in preference order:

1. **Leave it off.** Everything except smart search, face recognition, and OCR
   works. This is the deployed default.
2. **Run inference on Quark** (22.9 GB RAM, 14 cores, its own `/dev/dri`).
   Deploy the worker there and set `IMMICH_ML_URL` on Riker to point at it.
   This is the best option if smart search matters.
3. **Enable it locally** once Riker has headroom, by deploying with the
   `machine-learning` profile active.

Search and Explore are noticeably poorer without it; nothing else is affected.

## Companion tools

None are required, and none belong in this stack.

- **`immich-go`** - a bulk importer for Google Photos Takeout, iCloud exports,
  and local folders. It is a **standalone Go binary with no official container
  image**, run ad hoc from a workstation against the API. It is not a service
  and must not be added here.
- **`immich-cli`** - the official CLI. Run with `docker run --rm` when needed.
- **immich-public-proxy**, **immich-kiosk** - genuine long-running services, but
  separate concerns that would deploy as their own stacks. Both talk only to the
  API.
- **immich-power-tools**, **immich-deduper** - reach directly into the Immich
  database rather than the API, which couples them to Immich's schema across
  upgrades. Avoid.

## Deployment and updates

Deploy only through Riker's Dockhand after the Compose change has reached
`main`. Riker runs Dockhand `1.0.37`; confirm the live version before any
mutation and follow
[`dockhand-git-deployments.md`](../../.agents/nevercommit/dockhand-git-deployments.md).

`IMMICH_DB_PASSWORD` must exist in Dockhand's secret store **before** the first
deploy. Postgres initialises its data directory on first start and the password
is fixed at that moment; changing it afterwards means editing the database, not
the variable.

The Git stack has `repullImages` enabled, so a Dockhand deploy pulls the current
`v3` images and recreates the containers.

## Rollback

Immich **does not support downgrades**, not even patch-level, because migrations
run forward-only on start. Rolling back the image after a successful start
requires restoring the database from backup as well.

Revert the Compose commit, push `main`, then repeat the Dockhand sync and deploy.
Restore `${IMMICH_DB_PATH}` from a verified backup only after stopping the stack
through Dockhand.

## Security and operational notes

- Every service runs with `no-new-privileges` and no published host port.
- The database and cache are unreachable from `general_brg`.
- `IMMICH_DB_PASSWORD` lives only in Dockhand's secret store. This repository is
  public; never give it a default.
- Immich has its own user accounts and admin registration. The first account
  created becomes the administrator, so register it immediately after the first
  deploy rather than leaving registration open on the LAN.
- Upgrade the mobile app before the server. The app supports the current and
  previous major; the server only supports a matching major.
- Docker CLI may be used for read-only diagnosis only; all lifecycle changes go
  through Dockhand.

## Research record

Verified on 2026-08-27 against upstream primary sources, at release `v3.1.0`:

- [Official release compose file](https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml)
  defines the four services, the digest-pinned Valkey 9 and
  `ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0` images,
  `shm_size: 128mb`, and `healthcheck: disable: false`.
- [Environment variables](https://docs.immich.app/install/environment-variables)
  documents `DB_*`, `REDIS_HOSTNAME`, `IMMICH_TRUSTED_PROXIES`, and
  `IMMICH_MACHINE_LEARNING_URL`.
- [Reverse proxy](https://docs.immich.app/administration/reverse-proxy/) gives
  the `client_max_body_size 50000M`, `proxy_request_buffering off`, and 600s
  timeout values reproduced above, and states sub-path hosting is unsupported.
- [ML hardware acceleration](https://docs.immich.app/features/ml-hardware-acceleration)
  documents the `-openvino` image tag and the `c 189:* rmw` cgroup rule.
- [Requirements](https://docs.immich.app/install/requirements) states the 6 GB
  minimum, 8 GB recommendation, and that 4 GB systems must disable machine
  learning.
- v3.0.0 dropped pgvecto.rs support; VectorChord has been the default since
  v1.133.0. Migrate before upgrading from anything older.
