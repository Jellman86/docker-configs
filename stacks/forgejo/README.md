# Forgejo

Private Git hosting for Pownet, using the upstream LTS rootless container and SQLite. The stack is named `forgejo`, with one container also named `forgejo`. NPM routes `https://git.pownet.uk` to `forgejo:3000`; only SSH is published at `192.168.213.102:2222`.

Private UniFi DNS and Quark's approved Tailscale subnet route provide access at home and over the tailnet. No public Tunnel, WAN forward or new Tailscale identity is required. T3 Code is a separate native service and is not part of this stack.

## Deployment

Use Git, successful Compose/host CI and Dockhand Git sync/deploy. Select `stacks/forgejo/compose.yaml`, environment Quark, stack name `forgejo`. Set `FORGEJO_SECRET_KEY` and `FORGEJO_INTERNAL_TOKEN` to independent random values in Dockhand's encrypted variable store. Keep repull enabled; the image follows the LTS patch train, with major upgrades reviewed separately.

Pre-create `/mnt/services/quark/docker/forgejo/{data,config}` on the mounted apps SSD, owned by `1000:1000`, mode `0700`. Bind mounts refuse automatic creation. The existing host mount dependency protects Docker startup. No Docker socket, devices or host privilege are granted to Forgejo.

Installation is locked from first startup. Create the initial administrator using Forgejo's CLI through Dockhand exec; the password belongs in a private credential store, never this repository. Registration is disabled. Sign-in is required and all repositories are forced private. Reverse-proxy login is disabled and the v15 wildcard trusted-proxy default is explicitly restricted.

## Use

Add your SSH public key in Forgejo's account settings. Clone URLs use:

```text
ssh://git@git.pownet.uk:2222/jellman86/agent-config.git
https://git.pownet.uk/jellman86/agent-config.git
```

An `agent-config` repository is appropriate for instructions, skills, templates and sanitized helper scripts shared between machines. Exclude `.agents/nevercommit`, account credentials, `.env` secrets, tokens, recovery archives and machine-local session databases. A private repository still keeps committed secrets in its history.

Actions runners, packages, LFS and email are disabled initially. Use the administrator account to add other users rather than enabling registration. Without a mail destination, password recovery is an administrator operation.

## Recovery

- `/var/lib/gitea` maps to `/mnt/services/quark/docker/forgejo/data`, including repositories, SQLite and SSH identity.
- `/etc/gitea` maps to `/mnt/services/quark/docker/forgejo/config`.
- SQLite: `/var/lib/gitea/data/forgejo.db`.

The whole Forgejo directory is included in the bounded nightly application backup. The existing online SQLite backup replaces live database files with checked recovery copies; Git repository/config files are copied live. Avoid pushes during a manual recovery capture if a strict repository/database point in time is required. This is not an atomic whole-service snapshot.

Keep three successful app archives, 4 GiB maximum per generation and 20 GiB working allowance. Repository growth must fit those existing limits; do not silently increase retention or include large rebuildable artifacts. Media-like attachment extensions are excluded by that compact archive policy. The external rolling services copy includes the full directory on a future successful run, but the current USB backup is incomplete after transport errors and is not claimed verified.

Restore config, repositories and checked SQLite together while the stack is stopped through Dockhand. Preserve UID/GID, SSH keys and the original secrets. Recreate through Git/CI/Dockhand, then check `/api/healthz`, sign-in, private clone/push and repository visibility.

## Upstream

- [LTS container and rootless storage contract](https://forgejo.org/docs/v15.0/admin/installation/docker/)
- [Configuration reference](https://forgejo.org/docs/latest/admin/config-cheat-sheet/)
- [SQLite recommendation for modest activity](https://forgejo.org/docs/latest/admin/setup/recommendations/)
