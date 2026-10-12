# Quark storage workloads

The migrated media services use the two independent USB disks as a native Btrfs
RAID1 at `/mnt/tank`, and the incoming AirDisk SSD as XFS at `/mnt/services`.
Quark's existing `/mnt/apps` remains on its boot SSD. The enclosure stays in
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
