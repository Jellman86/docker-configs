# autoFPL

Git-backed Dockhand stack for the private autoFPL API on Quark (`dell-compute`).

## Service

- `autofpl` runs the verified image published from autoFPL `dev` merge commit `f5b7db7921392af1b703f14c6a68e1954d23f157`.
- Compose pins the immutable manifest digest `sha256:8f72f56328256862f9161672fa52d5fb68c72cebeb13f5420e521f91d091dc70`.
- The application listens on container port `8080`, serves the responsive Gameweek decision room at `/`, returns its explicitly synthetic forecast joined to persisted snapshot state from `/api/v1/advice/demo`, publishes OpenAPI 3.1 at `/openapi/v1.json`, and exposes the private decision-snapshot write/read routes.
- One SQLite file under `/data` is authoritative for squad, selection, observation and immutable snapshot state. Startup applies three explicit migrations with foreign keys, WAL and a bounded busy timeout.

## Network exposure

The service joins the existing external `general_brg` network with alias `autofpl-api`. It declares container port `8080` for internal discovery but publishes no host port. No Nginx Proxy Manager host, Cloudflare route, Tailscale route, or public DNS record is part of this stack.

Internal callers on `general_brg` can use:

```text
http://autofpl-api:8080
```

## Hardening

The container runs explicitly as UID/GID `1654`, uses a read-only root filesystem, has only a bounded `/tmp` tmpfs, drops all Linux capabilities, enables `no-new-privileges`, and bounds PIDs, CPU, memory, shutdown time, and JSON logs. The only writable mount is the private SQLite directory at `/data`. The health check uses the image's built-in fail-closed probe.

## Persistent data

The bind source is `/mnt/apps/docker/autofpl/data`. Compose sets `create_host_path: false` so a missing path fails rather than being silently created as root. Provision it once as the Quark deployment user before the first stateful deployment:

```bash
install -d -m 0750 /mnt/apps/docker/autofpl/data
setfacl -m u:1654:rwx /mnt/apps/docker/autofpl/data
setfacl -d -m u:1654:rwx,u:1000:rwx,m::rwx /mnt/apps/docker/autofpl/data
```

Verify with `getfacl /mnt/apps/docker/autofpl/data`. The directory owner remains the deployment user; UID `1654` receives only the filesystem access needed by the non-root container. Database files, WAL files and backups stay outside Git.

Create a consistent backup from the application image's SQLite online-backup command, using a new filename under `/data/backups`, and verify the backup with the integrity command before a schema-changing deployment or rollback. Do not copy the live database/WAL pair directly.

## Dockhand deployment

Create a Git-backed Dockhand stack with:

- repository: `https://github.com/Jellman86/docker-configs.git`
- branch: `main`
- Compose path: `autofpl/docker-compose.yml`
- environment: Quark / environment ID `1`
- stack name: `autofpl`
- repull images: enabled
- force redeploy: enabled
- build on deploy: disabled

No stack variables or secrets are required for this slice. Follow the repository-level Git/Dockhand procedure in the [root README](../README.md). Do not run a parallel `docker compose up`.

## Verification

Before commit or deployment:

```bash
python3 -m unittest discover -s autofpl/tests -v
docker compose -f autofpl/docker-compose.yml config --quiet
```

After Dockhand deployment, verify:

1. Dockhand synchronized the intended `docker-configs/main` commit.
2. `autofpl` is running and healthy with the pinned manifest digest.
3. No host port is published.
4. UID/GID, read-only root, capability and network settings match Compose.
5. `/`, `/api/v1/advice/demo`, `/openapi/v1.json`, `/healthz`, `/readyz`, decision-snapshot create/read/restart behavior, the deterministic endpoints, and representative malformed/domain-invalid 400/422 handling work from a trusted internal client.
6. The advice response shows a non-null snapshot ID/revision/cutoff, `/data/autofpl.db` is owned by UID `1654`, WAL mode is active, and the built-in integrity command returns `ok`.

## Rollback

Create and verify a consistent backup before changing the image or schema. Roll back by reverting the Compose digest through Git and Dockhand only when the older image supports the current schema. Otherwise restore the matching verified backup as a separately reviewed operation; never overwrite the live database while the application is running.
