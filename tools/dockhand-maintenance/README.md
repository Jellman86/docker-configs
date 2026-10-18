# Temporary Dockhand maintenance process

This manual template allows a second Dockhand process to manage an authorized
update of the normal manager. It is not a second permanent control plane and is
not currently deployed. The previous migration's maintenance state is retired.

The endpoint is loopback-only at `127.0.0.1:3001`. The bind directory
`/mnt/services/host/dockhand-maintenance` must already exist and contain a verified
private online database copy plus its matching encryption identity. Never bind
both manager processes to the same live database directory or create an empty
replacement over the running manager's state.

Keep working LAN SSH, verify the seeded manager's health and environment, then
use its API for the normal manager's Git sync/deploy after CI succeeds. Verify
that the original manager again owns the correct stacks and secrets. Remove the
temporary stack through the original manager and retire its copied private state
once no process uses it. Preserve a compact verified recovery archive.

See [operations](../../docs/operations.md) and the normal
[management stack](../../stacks/management/README.md). The current naming rollout preserves the `management` identity and does not
require deploying this maintenance process.
