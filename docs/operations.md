# Operations

Use the [cutover sequence](cutover-plan.md) for project renames. Routine updates
use the procedure below; preparing or merging source alone does not authorize them.

## Configuration ownership

| Configuration | Authoritative location |
|---|---|
| Compose, resource/device settings and provisioning | This Git repository |
| Overrides, credentials and API tokens | Dockhand encrypted stack variables |
| Application settings/databases | Persistent application directories |
| Reverse-proxy routes/certificates/access lists | NPM UI/API; documented intent in [ingress and DNS](ingress-dns.md) |
| Private service DNS and host reservation | UniFi; documented intent in [ingress and DNS](ingress-dns.md) |
| Public tunnel ingress and access policy | Cloudflare administration |
| Native storage, backup and routing settings | Root-owned host configuration; [host guide](../host/quark/README.md) |

Do not write NPM or Dockhand databases directly. A Compose environment variable
may initialize an application only once; do not assume editing it rewrites an
existing saved setting. Keep secret examples empty and validate with placeholders.

## Routine update

1. Inspect the intended stack, active jobs and current recovery backup. Review the
   resolved Compose model with its existing non-secret overrides. Preserve data
   mount paths, owners, device access, network aliases and published bindings.
2. Push the reviewed source. Require successful CI and image publication before
   using a new image. YA-WAMF follows the user's rolling `dev-intel` policy.
3. Discover the environment and Git-stack record through `GET /api/environments`
   and `GET /api/git/stacks`. Verify repository, branch, Compose path and
   `repullImages: true`; do not guess stack IDs.
4. Send `POST /api/git/stacks/{id}/sync`, then read the record again. Require the
   intended commit, `syncStatus: synced` and no sync error.
5. Send `POST /api/git/stacks/{id}/deploy` with `Accept: application/json`, no
   body. Wait for an explicit `success: true`. A draining Optimisarr job can keep
   the request open for up to two hours. Do not start another deployment or retry
   an ambiguous response before checking actual state.
6. Verify running/healthy containers, expected image references, persistent mounts
   and authenticated application behavior. For a network change, test the app
   through NPM and its dependent services as well as its local health endpoint.

Dockhand applies its configured fresh pull and recreation. Read-only Docker
inspection, logs and health requests are allowed; Docker CLI deployment commands
are not. The management stack controls the rest of the estate, so a manager
upgrade needs its separate documented maintenance procedure and working SSH.

## Acceptance and rollback

Check the application rather than only container health: a request through the
canonical URL, an authenticated read, a representative operation, dependency
connectivity and recent errors. Database/photo upgrades also need restore and
integrity evidence. Keep public signed-in and actual WAN playback checks separate
from an unauthenticated HTTP response.

For an ordinary image/config regression, revert the Git change, require passing
checks, then sync/deploy through Dockhand. For a major database upgrade, an old
image cannot read new cluster files: use the documented logical restore procedure
and a verified recovery archive. Never copy an old physical PostgreSQL cluster
over the current one. A stack/project rename requires the reverse identity mapping
in the [cutover plan](cutover-plan.md), not simply a Git revert.

## Backups and maintenance

Nightly online app recovery retains three successful archives, at most 4 GiB per
generation and 20 GiB including working data. They contain consistent SQLite and
PostgreSQL recovery data, selected configuration and private host identity. These
archives share the media host and are not an independent copy of photos or VMs.

The on-demand external copy is a separate installed tool. Its current receipt
must show actual completion before the backup is accepted. Live file copying is
best effort; its consistent database archive is the database recovery source.
Do not restart the first copy, reformat the disk or add a full-media checksum pass
as part of this Compose reorganization. See the [host guide](../host/quark/README.md).

Keep ordinary storage guards, health timers, log limits and monthly scrub.
A scrub checks Btrfs checksums and mirror readability; it does not prove that an
independent USB copy matches the source. Preserve the other agent's development
work and the original SSD's VM space.
