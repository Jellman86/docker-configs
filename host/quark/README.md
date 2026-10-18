# Quark host

Fedora Server on Quark (`192.168.213.102`, `quark.pownet.uk`). Riker is retired.
Application storage has been consolidated on the added SSD. The initial media
mirror scrub passed; the independent USB backup failed again during catch-up after successful
filesystem recovery. The spare is normally unmounted pending investigation of
repeated USB resets/write errors. No successful full-backup receipt exists.

The repository's normalized Compose layout is **live and accepted**. Follow
the [cutover sequence and mapping](../../docs/cutover-plan.md). Do not rerun migration,
filesystem preparation, old PostgreSQL upgrades or native Tailscale handover jobs.

## Storage

| Mount | Purpose |
|---|---|
| `/` | Small Fedora root volume; keep build trees and large caches off it |
| `/mnt/apps` | Original SSD: VMs and `/mnt/apps/developer/jellman86` |
| `/mnt/services` | Added SSD: applications, Docker/containerd and native app state |
| `/mnt/tank` | Two 8 TB drives in Btrfs RAID1: media, photos, downloads and personal data |
| `/mnt/external-backup` | Independent ext4 USB copy, mounted on demand |

Migrated application configs use `/mnt/services/docker`. Existing Quark app and
engine data use `/mnt/services/quark`. Five legacy `/mnt/apps` bind aliases
resolve to the added SSD; they are not duplicate copies. Preserve the home-directory
symlinks for development/test work and the `/var/lib/containerd` compatibility link.
Do not merge the two application config trees or rename live volume directories.

Use UUID mounts and verify actual member serials, filesystem type and read-write
state. The ICY BOX stays in SINGLE mode with native Btrfs RAID1 for data, metadata
and system. Retain CoW/checksums, empty protected fallback directories and mount
dependencies. Avoid automatic defragmentation and periodic full-volume balance.
Private UUID/serial inventories and recovery evidence remain on the Mac.

## Guarded startup

`storage_workloads.py` is installed as `/usr/local/sbin/quark-storage-workloads`,
with `/etc/quark-storage-workloads.json` and its systemd unit. Guarded Compose
entrypoints use `restart: "no"`; the guard verifies mounts, RAID profiles, members
and error counters before starting existing containers through Dockhand. It also
orders healthy dependencies and handles a lost VPN namespace.

Keep `/etc/quark-storage-workloads.enabled` present during normal operation.
**Stopping the guard or removing that marker stops the guarded applications.**
Do not use either merely to inspect health. A manual stop in Dockhand can be
undone by the enabled guard. The guard does not deploy containers, repair disks,
reset errors or make a failing USB adapter safe. Operator deployments must also
check storage before they start applications.

The old Gluetun repair job is profile-gated manual tooling, not a running watchdog.
Only normal Git/CI/Dockhand deployment may perform a required recreation.

## Routine checks

```sh
sudo /usr/local/sbin/quark-media-maintain health
sudo btrfs scrub status -d /mnt/tank
sudo systemctl list-timers 'quark-*'
df -h / /mnt/apps /mnt/services /mnt/tank
```

Hourly mirror health and a monthly scrub are installed. The scrub explicitly
limits each member to 40 MiB/s. Read its actual status and next timer time; do not
launch another scrub as a verification shortcut. Container stdout/stderr has
bounded Docker rotation. Applications must separately retain/rotate files they
write inside their own directories.

## Recovery backups

`app_backup.py` is installed as `/usr/local/sbin/quark-app-backup` and runs nightly
through `quark-app-backup.timer`. Root-only `/etc/quark-app-backup.json` selects
state. Archives are under `/mnt/tank/backups/apps`; current evidence is
`/mnt/services/host/app-backup/status.json`. Limits are three successful archives,
4 GiB per generation and 20 GiB including working data. Applications remain online.

SQLite uses consistent online recovery copies. Immich uses a logical PostgreSQL
dump; its restored database properties, including `vchordrq.probes`, also matter.
Keep PostgreSQL 18 at `/mnt/services/docker/immich/postgres18`, mounted at
`/var/lib/postgresql`. The stopped old PG14 cluster has already been removed.
Never recreate it or run the upgrade rehearsal against production storage.

The independent USB tool is `/usr/local/sbin/quark-external-backup`, configured by
`/etc/quark-external-backup.json`. Its installed guide is
`/usr/local/share/quark-external-backup/README.md`; the practical Mac handover is
`~/Desktop/Quark Backup/README.md`. It keeps one rolling file copy plus a fresh
consistent application archive. Read the actual status and completed receipt:

```sh
sudo systemctl status quark-external-backup-run.service
sudo cat /mnt/external-backup/quark-backup/status.json
sudo cat /mnt/external-backup/quark-backup/last-success.json
```

An absent receipt means the first full backup has not been accepted. Do not
reformat the already prepared ext4 disk. The old ZFS backup and offline reader are
retired. VM/developer trees, rebuildable engine data and backups of backups are
excluded. Independent VM backup remains a separate decision.

## Access, security and networking

Tailscale is native (`tailscaled.service`), using the official stable Fedora DNF
repository and automatic client updates. Preserve `/var/lib/tailscale`, the node
identity, forwarding settings, GRO tuning and approved subnet/exit routes.
`99-quark-tailscale.conf` and `tailscaled-gro.conf` document the host settings.
No Docker Tailscale service or replacement identity is needed.

Native Samba shares are `media`, `downloads` and `home`, using existing authenticated
credentials, POSIX permissions and `/mnt/services/host/samba` state. Access with
`smb://quark.pownet.uk` or `\\quark.pownet.uk\media`. Validate with `testparm` and
an authenticated disposable read/write test. Keep `smb-storage.conf` mount
requirements and normal SELinux labels. SMB1 and guest access remain disabled.

The host is SELinux Enforcing, but current Docker container labelling is disabled.
Do not claim those workloads are confined. Enabling container labelling requires
a separate shared-volume/device qualification, not a naming cleanup.

Docker receives the Intel iGPU at `/dev/dri`; Quark's render group is GID `105`.
Only workloads that need the NPU receive `/dev/accel/accel0`. Preserve those
permissions, application provider choices and measured memory limits at cutover.

## References

- [Btrfs hardware considerations](https://btrfs.readthedocs.io/en/latest/Hardware.html)
- [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)
- [SQLite online backup](https://sqlite.org/backup.html)
- [PostgreSQL logical backup](https://www.postgresql.org/docs/current/app-pgdump.html)
- [Tailscale subnet routers](https://tailscale.com/docs/features/subnet-routers)
