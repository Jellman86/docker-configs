# Quark storage workloads

The migrated media services use the two independent USB disks as a native Btrfs
RAID1 at `/mnt/tank`, and the incoming AirDisk SSD as XFS at `/mnt/services`.
Quark's `/mnt/apps` volume remains on its boot SSD for VMs and workspaces;
existing app paths become bind aliases to the added SSD during consolidation. The enclosure stays in
Single mode. The bridge's `RANDOM__` identity changes on reconnection, so mounts
use filesystem UUIDs and the guard also verifies the actual ATA member serials.

The Quark variants extend the existing service definitions:

- `arr_vpn_stack/docker-compose.quark.yml` owns `arr_stack_brg` and joins the
  proxied services to Quark's existing `npm_proxy_backends`. The arr network
  retains default-gateway priority, including for Gluetun.
- `media_related_stack/docker-compose.quark.yml` joins that network and Quark's
  existing NPM `general_brg`. Plex transcode temporary files use the SSD.
- `immich/docker-compose.quark-server.yml` reuses the existing Quark ML worker.
- `stirling_pdf/docker-compose.quark.yml` preserves the document toolkit's
  configs, custom files and OCR data on the incoming apps SSD.

Set all application config paths to `/mnt/services/docker`, including Plex's
`CONFIG_PATH` and Immich's `IMMICH_DB_PATH`. Set `RENDER_GID` from the actual host
render device, `GLUETUN_CONTROL_BIND_ADDRESS` to Quark's LAN address, and
`IMMICH_ML_URL` to the existing worker's reachable endpoint. Store credentials
only in Dockhand's encrypted stack variables. Never copy Riker's generated env
file or database over Quark's running Dockhand instance.

## Storage verification and restoration

Keep the independent ZFS migration backup intact. Import it read-only through
a compatible recovery system, verify the final snapshot GUIDs and recorded file
hashes, and verify disk serials before formatting either original media disk.
Stage and fully checksum-compare all apps datasets on Quark's existing SSD
before reformatting the AirDisk. Formatting is a one-time migration operation;
none of the startup services here formats, partitions, repairs or deploys disks.

Restore former tank datasets into ordinary directories in ONE Btrfs subvolume.
Media, downloads, Optimisarr work and trash must share that subvolume for atomic
moves and hardlinks. Preserve numeric owners, modes, timestamps, hardlinks and
supported xattrs. TrueNAS NFSv4 ACLs require deliberate POSIX permission mapping;
do not blindly copy them using rsync `-A` or recursively change every UID.
Preserve PostgreSQL's own user and private directory modes. Compare all restored
files using checksums before enabling application writers, then scrub the mirror
and validate databases, representative media and Intel acceleration.

Use explicit RAID1 for data, metadata and system, retain CoW/data checksums, and
avoid automatic defragmentation or periodic whole-volume balance on these SMR
drives. Keep the unmounted fallback mount directories empty and immutable, and
use `nofail` UUID mounts so a missing enclosure cannot stop Quark's networking,
Cockpit, NPM or existing apps. Activate the separately prepared health/scrub
configuration only with the actual media UUID after restoration.

## Startup guard

Docker restart policies do not enforce Compose health dependencies at host boot.
All migrated variants therefore use `restart: "no"`. Install
`storage_workloads.py` as `/usr/local/sbin/quark-storage-workloads`, the service
unit under `/etc/systemd/system`, and a root-owned mode-0600 config at
`/etc/quark-storage-workloads.json`. Replace both example UUIDs with the actual
ones. If Dockhand authentication is enabled, add a root-only `token_file` path.

The guard checks exact mount path, filesystem type, UUID, member serials and
read-write state. For Btrfs it also checks RAID1 profiles, missing devices and
error counters. It resolves existing container IDs from Dockhand, respects
configured health dependencies, rechecks storage before each start and starts or
stops containers only through Dockhand. It never creates or deploys containers.
A failed individual stop does not skip the remaining services. Before starting
a stopped VPN container, the guard stops qBittorrent and Prowlarr so their next
start uses the new network namespace/proxy connection. Optimisarr stops
last because its encode drain can take two hours.

Keep `/etc/quark-storage-workloads.enabled` ABSENT during restore. Create it only
after the restored storage and application acceptance checks pass. Enable the
systemd service after installing and checking its config. To pause migrated
workloads for maintenance, remove the enabled file; the guard will stop them.
Stopping a container in Dockhand without disabling the guard allows the guard to
start it again. Do not manually deploy storage workloads while their mounts are
unavailable. Dockhand's explicit deployment endpoint starts containers itself,
so the guard is not an authorization boundary around operator deployments.

The old gluetun watchdog can redeploy an entire stack and bypass this gate. It
is retained behind the `manual-network-repair` profile for compatibility but is
not started by normal deployment or by the guard.
Use the storage guard for existing-container crash recovery. Namespace repair
that requires recreation must use the normal Git/CI/Dockhand deployment path
while verified storage is available. Quark's existing independent services keep
their restart policies and are not stopped by this guard.

The guard stops affected workloads if storage checks fail; it cannot make an
unreliable USB bridge safe or undo writes during the detection interval. It will
not automatically mount a degraded mirror, reset counters, repair filesystems,
or force a hung container to exit. Resolve storage failures before re-enabling
workloads. Preserve the readonly recovery route and independent backup until
ongoing backup and restore testing is established.

Primary references:
[mkfs.btrfs](https://btrfs.readthedocs.io/en/latest/mkfs.btrfs.html),
[Btrfs hardware considerations](https://btrfs.readthedocs.io/en/latest/Hardware.html),
[Docker startup order](https://docs.docker.com/compose/how-tos/startup-order/).

## Consolidated application storage and ingress

Migrated Riker configs live at `/mnt/services/docker`. Existing Quark app trees
live at `/mnt/services/quark/{docker,docker-engine,containerd,security_inference_stack,compose}`.
Bind mounts preserve their original `/mnt/apps/{name}` paths, including the
`/var/lib/containerd` symlink target. Do not merge the two config trees: Quark's
NPM and Dockhand remain authoritative. Keep `/mnt/apps/libvirt` and
`/mnt/apps/dev` on the original SSD.

A cold move requires stopping ordinary workloads through Dockhand, then stopping
native Docker/containerd so management databases, named volumes and image stores
are consistent. Verify full checksums before activation and retain original
copies for rollback. Bind mounts require `mnt-services.mount`; native Docker and
containerd need `RequiresMountsFor` dependencies on their aliases. Keep empty
fallback directories immutable. The media guard remains responsible for the
USB-backed workloads and their health ordering.

Use plain service names for private ingress: `dockhand.pownet.uk`,
`npm.pownet.uk` and `playwright-mcp.pownet.uk`. Preserve Playwright's explicit
host allow-list and NPM authentication. Physical `quark.pownet.uk` remains an
administration/SSH name. Migrated services keep their existing canonical names,
with NPM and private DNS pointing at Quark. Retarget the existing public Seerr
Cloudflare tunnel origin separately through an authorized management credential;
its connector token cannot edit tunnel ingress. Do not expose new services.

## Native SMB shares

`smb.conf` preserves the three enabled source shares: `media`, `downloads` and
`home`. There were no NFS exports. Only authenticated `media-apps` group members
can connect, and existing POSIX ACLs still control each directory. Private home
data retains its user-specific ACL; group membership alone does not grant access.
SMB1, guest access, printing and NetBIOS ports are not enabled. Allow TCP 445 only
from the existing trusted LAN and Tailscale ranges in the host firewall.

Install Fedora's native Samba packages, import the existing SMB password hash
through `pdbedit` from a root-only migration file, and verify the imported hash
without printing it. Map the source username to its actual Quark Unix UID. Keep
the original TrueNAS export and secret seed private; neither belongs in Git.

Samba's persistent state belongs on the apps SSD at `/mnt/services/host/samba`,
bind-mounted onto `/var/lib/samba`, with an SELinux equivalence to the canonical
directory. Install `smb-storage.conf` as a drop-in under `smb.service.d` so it
requires the actual storage mounts and verifies UUIDs, member identities and
mirror health before startup. Retain the original state before activating a bind.

Use the standard `samba_share_t` label for the mirror root and the three exported
trees. Photos, Optimisarr work, backups and other unshared trees keep their
existing labels. Quark's current Docker workloads run as `spc_t`; verify their
access again after relabeling. Enabling Docker SELinux confinement later requires
qualifying a shared-label policy before changing that setting. Do not enable
global Samba export booleans or disable enforcing mode to resolve a denial.

Validate `testparm`, authenticated share listing and a disposable write/read/
delete round trip in each share before declaring acceptance. Use `smb://quark.pownet.uk`
on macOS or `\\quark.pownet.uk\media` on Windows. Preserve the existing login;
clients need to reconnect to the new hostname. Retain the independent ZFS backup.

## Application recovery backups

Quark is a home lab. `app_backup.py` makes a small online backup of settings and
application databases without stopping containers or SMB. Install it as
`/usr/local/sbin/quark-app-backup`, fill the example mount UUIDs, and install the
service/timer. Keep `/etc/quark-app-backup.json` root-only. The timer runs nightly
at 03:10. There is no dependency on migration jobs or a recovery VM.

SQLite uses its online backup API and checks the resulting copy. Plex uses its
bundled SQLite tool for its custom tokenizer. Immich uses a
consistent logical `pg_dump`; Samba account hashes use `pdbedit`. Other live
configuration files are best-effort copies, suitable for a home lab rather than
a synchronized snapshot of every application. Dockhand's encryption key, stack
settings, NPM certificates and selected host configuration are included privately.
Files retain ownership and permissions for restoration.

Archives live at `/mnt/tank/backups/apps`. Keep three successful archives, each
limited to 4 GiB. Including one temporary staging tree and one candidate archive,
maximum routine data is 20 GiB, below the user's 200 GiB allowance. Only a valid
new candidate permits rotation; a failed backup keeps existing recovery points.
This does not include the fixed one-off recovery copy. Container images, models,
recordings, artwork, caches and historical backups are excluded from the routine.
The job performs no recurring whole-media checksum comparisons.

These are apps SSD recovery copies on the same host mirror, not an independent
backup of media, photo originals, personal files or VMs. Keep the independent
backup disk and a documented recovery path. For restoration, extract an archive
privately, stop only the affected writer through Dockhand, restore its matching
`apps/files` config path with numeric ownership and apply `restorecon`. Restore
`apps/immich.dump` with `pg_restore` into a compatible Immich database; never copy
it over PostgreSQL's physical files. `apps/smbpasswd-private.txt` can be imported
with `pdbedit`. Treat archives as credentials: keep the backup directory private.

Primary references: [SQLite online backup](https://sqlite.org/backup.html) and
[PostgreSQL logical backup](https://www.postgresql.org/docs/current/app-pgdump.html).
