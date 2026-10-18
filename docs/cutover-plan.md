# Compose cutover and acceptance

**Accepted on 18 October 2026.** All 11 Git-stack names/paths and running Compose
project labels match the normalized layout. Thirty-one containers are running,
and every configured health check passes. The two OpenViking bootstrap jobs
exited successfully. No containers remain under the old project names.

The previously enabled daily 03:00 Git schedules for `ai-tools`, `home-automation`
and `ingress` are restored. Other stack scheduling policies are unchanged.
The independent USB backup is a separate unresolved transport fault; it is not
claimed verified and will not be retried automatically.

## Acceptance

- All 20 manifests / 61 resolved service definitions and 85 policy tests pass.
- All 11 Dockhand records have canonical Git paths and successful syncs. Source-only
  synchronization was verified to preserve container IDs/start times.
- The original sidecar pairing volume and Immich ML cache are retained, and all
  five application aliases resolve to the added SSD. No application data was removed.
- NPM targets `yawamf:8080` and Quark `.102:8123` for Home Assistant. Nginx validation
  passes. All 24 private service records resolve to Quark and return valid TLS/HTTP
  responses, including expected authentication responses.
- The stale `devenv` record is removed. Riker's inactive reservation/local DNS are
  disabled; Quark's reservation and all other static records are preserved.
- Four empty obsolete AI networks and eleven unused generated deployment-source
  folders are removed. A fixed 405 KB private source archive excludes generated
  environment files. Shared networks and the optional research network remain.
- YA-WAMF's published rolling `dev-intel` image was verified against successful
  upstream CI and deployed through Dockhand. Its Intel GPU/NPU devices remain
  present. Frigate has six active feeds, zero skipped frames and approximately
  5.6 ms detector latency at acceptance.
- PostgreSQL 18.4 and original database properties are healthy. A fresh bounded
  1.27 GB app recovery archive passed 32 SQLite checks and a complete gzip CRC read.
  Three archives and the existing size limits are retained.
- The queue is unpaused and can dispatch; qBittorrent uses the current Gluetun
  namespace. Source mirror health, mount guards and the monthly scrub timer pass.

These checks do not establish signed-in public service access, actual WAN Plex
playback or completion of the independent USB backup. Private evidence is kept
on the Mac and under `/mnt/services/host/external-backup`.

## Project mapping

| Former Dockhand/Compose name | Current name |
|---|---|
| `ai_tools` | `ai-tools` |
| `arr_stack` | `arr` |
| `media_stack` | `media` |
| `web_services` | `ingress` |
| `security_inference_stack` | `home-automation` |
| `stirling_pdf` | `stirling-pdf` |
| `immich_ml` | `immich-ml` |
| `optimisarr_sidecar` | `optimisarr-sidecar` |
| `immich`, `management`, `twenty` | Unchanged |

The complete Git-path mapping is in [layout and naming](compose-layout.md).
All 11 source paths were first staged/synced without deploying, then the
normalized runtime identities were checked against Dockhand and container labels.
Explicit Compose `name` values now match the active Dockhand names.

The container-name correction is `yawamf-monalithic` -> `yawamf`.
Its service name remains `yawamf`, the old DNS alias is retained, and its upstream
image repository name does not change. All other service/container identities,
host bindings and persistent bind paths remain unchanged.

## Procedure for a future move

1. Confirm source health, adequate space and current consistent app recovery.
   Check the independent USB job before interrupting any application. Preserve
   the developer/test trees and all normal storage/backup safeguards.
2. Confirm the reviewed Git commit and successful CI/image publication. Snapshot
   the current stack metadata, masked variable inventory and container/mount
   identities privately. Check for other agents' changes before proceeding.
3. For unchanged project names, update the Git path and sync. If the effective
   model is identical, avoid a cosmetic deployment, particularly of Dockhand.
4. For each changed name, use Dockhand to remove the old project's containers
   with **`removeVolumes: false`**. Keep the old source available for rollback.
   Wait for actual graceful shutdown; do not retry a draining media operation.
5. Rename the same Git-stack record, update its path, preserve encrypted variables,
   sync and deploy through Dockhand. Never create a parallel copy over live data.
   Verify container project labels, data/device mounts, named-volume identity,
   health and representative application behavior before the next stack.
6. Preserve the external arr bridge while media uses it. Check qBittorrent's
   namespace after VPN recreation. Do not change mount guards or restart policies
   to simplify the rollout.
7. Handle ingress last. Update NPM's YA-WAMF target after its new name resolves;
   normalize Home Assistant's host endpoint separately. Canonical DNS mostly
   needs no change. Review any newly retired DNS records/reservations before editing.
8. Test private DNS/TLS/authentication and application integrations. Record any
   public signed-in/WAN checks separately. Restore only the previous automatic
   update schedules once the rollout is accepted. Record the actual completed
   mapping and update this document's status.

The sidecar configuration volume and ML model cache are explicit existing volumes.
Do not rename their directories, create empty replacements or remove them during
`down`. The repo move is not a data migration and requires no additional full copy.

## Rollback boundary

A Git revert alone does not rename running containers or their project labels.
Use Dockhand to remove the new containers with volumes retained, restore the old
record name/path and known-good Git revision, then sync/deploy and verify the
original mounts. Reapply previous NPM targets if they were changed. Keep the
management plane and LAN SSH available throughout. Never restore an old database
cluster over a newer major-version cluster as a naming rollback.
