# autoFPL

Git-backed Dockhand stack for the private autoFPL API on Quark (`dell-compute`).

## Service

- `autofpl` runs the verified image published from autoFPL `dev` merge commit `f7d96e97a1ac5a25a39e376ec31d763fe52825d0`.
- Compose pins the immutable manifest digest `sha256:7e9c8cf82a3b910af74affd17fb3c77a2bcaf92cf02b67c72f4b58d7714a727f`.
- The application listens on container port `8080` and exposes `/healthz`, `/readyz`, decision-snapshot metadata validation, manual squad validation, and starting-XI validation.
- The current slice is stateless and has no bind mounts or named volumes.

## Network exposure

The service joins the existing external `general_brg` network with alias `autofpl-api`. It declares container port `8080` for internal discovery but publishes no host port. No Nginx Proxy Manager host, Cloudflare route, Tailscale route, or public DNS record is part of this stack.

Internal callers on `general_brg` can use:

```text
http://autofpl-api:8080
```

## Hardening

The container runs explicitly as UID/GID `1654`, uses a read-only root filesystem, has only a bounded `/tmp` tmpfs, drops all Linux capabilities, enables `no-new-privileges`, and bounds PIDs, CPU, memory, shutdown time, and JSON logs. The health check uses the image's built-in fail-closed probe.

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
5. `/healthz`, `/readyz`, a valid validation request, and malformed/unsupported request handling work from a temporary client attached to `general_brg` or from an existing trusted internal consumer.

## Rollback

Revert the Compose commit or restore a previously reviewed image digest, push `main`, and redeploy through Dockhand. This slice has no persistent application state to restore.
