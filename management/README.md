# Management Stack

Git-backed Dockhand control-plane stack for the Fedora compute host.

## Services

| Service | Role | Published access |
|---|---|---|
| `dockhand` | Docker and Git-backed Compose management UI/API | `${DOCKHAND_PORT:-3000}` |

## Topology and storage

- Compose file: `management/docker-compose.yml`
- Intended host: Quark / `dell-compute`.
- External network: `general_brg`.
- Persistent data: `${DOCKERCONFIGPATH:-/mnt/apps/docker}/dockhand` mounted at `/app/data`.
- Docker control: host `/var/run/docker.sock` mounted into Dockhand.

The Docker socket gives Dockhand effective control over the host Docker daemon. Treat access to the UI/API and its persistent data as administrative access.

## Environment

A non-secret template is provided in [`.env.example`](.env.example). Settings are:

- `PUID`, `PGID`
- `TZ`
- `DOCKERCONFIGPATH`
- `DOCKHAND_PORT`

Authentication and repository credentials configured inside Dockhand must remain in its protected persistent data or secret store and must not be committed.

## Deployment and updates

The normal Git-backed deployment workflow is described in the [root README](../README.md). Because Dockhand owns the lifecycle of other stacks, update this stack cautiously and verify that an out-of-band Docker/SSH recovery path exists before recreating it.

After an update, verify:

1. `GET /api/auth/session` succeeds through the health check.
2. Existing environments, repositories, stack variables, and Git stack definitions remain present.
3. Dockhand can read container state and Git stack metadata.
4. No stack is deployed merely as part of validating the Dockhand upgrade.

## Rollback

Prefer reverting the repository/image change and redeploying through Dockhand while the control plane is healthy. If Dockhand itself cannot start, use the pre-authorized host recovery path only to restore the last known-good Dockhand container and `/app/data`; do not mutate unrelated stacks during recovery.

## Security notes

- Do not expose port 3000 publicly without a separate authenticated TLS boundary.
- Protect the Docker socket and Dockhand data directory from untrusted users.
- Store secrets in Dockhand's encrypted variables and never edit generated `.env.dockhand` files.
- Use Docker CLI inspection only for diagnosis; stack lifecycle changes belong to Dockhand.
