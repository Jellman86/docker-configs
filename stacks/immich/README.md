# Immich on Quark

Photo/video library, PostgreSQL and the separate OpenVINO worker all run on Quark
(`192.168.213.102`). Riker is retired. Deploy through Git, successful CI and Dockhand.

## Deployed topology

| Git stack | Compose path | Services |
| --- | --- | --- |
| `immich` | `stacks/immich/compose.yaml` | Server, PostgreSQL, Valkey |
| `immich-ml` | `stacks/immich/compose.ml.yaml` | OpenVINO machine learning |

The server variant extends `compose.base.yaml` and sets `restart: "no"` because
Quark's storage guard owns startup and crash recovery through Dockhand. The ML
worker uses `unless-stopped` and needs only its SSD-backed model cache. The base
machine-learning profile is a fallback, not another worker to enable alongside it.

The server joins `general_brg` for NPM and `immich_backend` for database/cache.
Database/cache have no published ports. This bridge is host-local, not cross-host.
The independently deployed ML worker retains the tested LAN endpoint
`http://192.168.213.102:3003`. Its API is unauthenticated and must not be exposed
through NPM or Cloudflare. Keep it LAN-bound until both stacks deliberately move
to a shared network and the saved ML URL is updated together.

## Storage and hardware

| Location | Contents |
| --- | --- |
| `/mnt/tank/photos` -> `/data` | Originals, thumbnails, profiles, transcodes |
| `/mnt/services/docker/immich/postgres18` -> `/var/lib/postgresql` | PostgreSQL cluster `18/docker` on local SSD |
| ML `model-cache` volume | Re-downloadable weights on the added SSD's Docker storage |

Never put PostgreSQL on SMB/NFS or reuse a previous-major cluster directory.
PG18 uses the parent `/var/lib/postgresql` mount, not the old PG14 `/data` mount.
The accepted database image contains PostgreSQL 18, VectorChord 1.1.1 and pgvector.
Its digest is an explicit reviewed upgrade, not a promise to match a moving
upstream latest Compose file. Do not redeploy `tools/immich-postgres-upgrade/compose.yaml`
over the production path: it is an isolated maintenance template only.

Intel transcoding and OpenVINO receive `/dev/dri` and Quark render GID `105`.
OpenVINO also retains upstream's USB device cgroup rule. Server and ML image
versions must match; the accepted deployment uses Immich 3.3.1. Do not upgrade one
stack independently. The worker's 8 GiB memory ceiling covers measured simultaneous
CLIP/face/OCR residency; caps do not reserve that memory.

## Ingress

Private DNS `immich.pownet.uk` targets Quark. NPM forwards to
`http://immich-server:2283`, with **Websockets Support** enabled. Immich needs the
root of its domain, not a subpath. The tested advanced configuration is:

```nginx
client_max_body_size 50000M;
proxy_request_buffering off;
client_body_buffer_size 1024k;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
send_timeout 600s;
```

Store database credentials in Dockhand encrypted variables. Keep original
`IMMICH_UPLOAD_PATH`, database username/name, and saved application settings when
recreating containers. `IMMICH_TRUSTED_PROXIES` must reflect the actual proxy path;
the existing Docker-range setting is broad and assumes trusted local containers.

## Recovery and validation

Nightly bounded app recovery uses a consistent logical `pg_dump`. Photos require
the separate full USB backup. Physical cluster copying while online is not a
replacement for the dump. After a restore, replay original database properties:
`vchordrq.probes=1` and `search_path="$user", public, vectors`. Inspect them with
`pg_restore --create --schema-only --file=- immich.dump`. A restore without
`--create` does not apply the DATABASE properties automatically.

After deployment check server/ML/database health, authenticated photo original and
preview access, smart search, vector indexes, expected asset counts and a fresh
logical backup. Restore app files only while the affected service is stopped
through Dockhand. Never restart the retired PG14 cluster over PG18 files.

## Upstream references

- [Docker Compose installation](https://docs.immich.app/install/docker-compose/)
- [Hardware transcoding](https://docs.immich.app/features/hardware-transcoding/)
- [ML acceleration](https://docs.immich.app/features/ml-hardware-acceleration/)
- [Reverse proxy](https://docs.immich.app/administration/reverse-proxy/)
- [Backup and restore](https://docs.immich.app/administration/backup-and-restore/)
