# Quark encrypted OneDrive backups

Duplicati's free open-source client provides a web UI, scheduler, encrypted version history and native personal OneDrive support. No paid hosted console is required. The image is pinned by registry digest; update through Git/CI/Dockhand, not the in-app updater.

## Scope and access

The only backup source mounted is `/mnt/tank/backups/apps`, read-only at `/source/quark-apps`. These are Quark's existing nightly application recovery archives. They exclude media, original photos, VM disks and developer state. This does not mean the whole host is backed up. No Docker socket or live application databases are mounted.

The container runs as root to read the root-only archives, without privileged mode. It only writes its own `/data` directory. Mount creation fails if the source is absent; never create an empty replacement. Check the tank mount and current archive before accepting an upload; a mounted path alone does not prove filesystem health or freshness.

The web UI has no published host port. UniFi private DNS maps `backup.pownet.uk` to `192.168.213.102`; NPM terminates HTTPS and proxies to `duplicati:8200` on `npm_proxy_backends`. No public Cloudflare route is created. Access requires the UI password, stored as secret `DUPLICATI_UI_PASSWORD` in Dockhand. The independent `DUPLICATI_SETTINGS_KEY` encrypts stored credential fields. Neither is the backup decryption passphrase.

## Deployment

1. Require CI success for the exact Git commit. Create a Dockhand Git stack named `backup`, Compose path `stacks/backup/compose.yaml`, environment Quark. Keep repullImages and forceRedeploy enabled and automatic updates disabled.
2. Generate and save independent settings/UI secrets in Dockhand's variable store. No database or generated env edits. Confirm `/mnt/tank` is mounted and the source directory exists before deployment.
3. Sync through `/api/git/stacks/{id}/sync`, verify the exact lastCommit and no syncError, then deploy through `/api/git/stacks/{id}/deploy`. Verify running image digest, mounts and private HTTPS access through NPM. Add the UniFi static A record and an NPM proxy host with the existing pownet.uk wildcard certificate, SSL forced, HTTP/2 and websocket forwarding. Do not edit unrelated routes. Do not use Docker CLI lifecycle commands.
4. Sign into the UI and connect personal Microsoft OneDrive via its AuthID authorization flow. This requires the owner's Microsoft sign-in. Do not paste OAuth tokens into Git, logs or chat.

## Initial job (requires Microsoft authorization)

- Name: `Quark application recovery offsite`.
- Destination: Microsoft OneDrive v2, unique folder `QuarkBackups/app-recovery`. Never reuse a folder belonging to another backup job.
- Encryption: AES-256 with a new strong passphrase. Retain it and an encrypted job export in an owner-accessible location independent of Quark and OneDrive. Do not start real uploads before this recovery copy exists.
- Source: `/source/quark-apps/`, include only completed files matching `apps-????????T??????Z.tar.gz`. Exclude dotfiles, `.candidate-*` and `.working-*` explicitly. Check the UI's source preview shows only the dated archives.
- Schedule: daily 05:00 Europe/London, after the local 03:10 job (30 minute timeout). Check the latest local archive is under 30 hours old. Do not count re-uploading an old archive as a successful fresh backup.
- Retention proposal: daily for 14 days, weekly for 8 weeks, monthly for 12 months. Confirm OneDrive free capacity before enabling retention cleanup. Backing up gzip archives limits deduplication; measure actual storage/bandwidth. Local three-generation rotation must remain unchanged.
- Configure verification and failure reporting. No email destination is assumed or configured. A green upload result does not prove freshness of the upstream archive; independent monitoring must check both stages.

A deployed empty Duplicati instance is NOT an active off-site backup. Accept only after OneDrive connection, saved encryption/recovery material, scheduled job and a remote restore are verified. Record evidence without credentials.

## Disaster recovery and drills

On another machine install the same Duplicati release, use Restore > Direct restore from backup files, reconnect OneDrive, enter the destination folder and backup passphrase, and restore into a NEW empty directory. Duplicati can rebuild its local index from remote volumes; restoration must be tested without its original `/data` database. Do not restore over live application data.

Compare a restored archive's SHA-256 against the original and inspect its manifest. A complete application recovery drill must then restore the databases/settings following the application-specific procedure. Repeat quarterly and after significant changes.

Export the job configuration with credentials only as an encrypted recovery artifact outside Git. Preserve the settings key and UI password separately if retaining a copy of `/data`; an online filesystem copy of its SQLite files is not a consistent database backup. The remote backup and passphrase must permit a direct restore without `/data`.

Croftview backup capture is a later separate job/repository scope, after ERPNext runs and complete database/files/config sets reach Quark. Do not add a missing/empty placeholder directory now.

## References

- https://docs.duplicati.com/platform-specific-guides/using-duplicati-from-docker
- https://docs.duplicati.com/backup-destinations/file-synchronization-providers/onedrive-destination
- https://github.com/duplicati/duplicati/blob/master/ReleaseBuilder/Resources/Docker/README.md
