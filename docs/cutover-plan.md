# Compose cutover and acceptance

**18 October: the user authorized staged execution once checks pass.** Source
preparation is complete; record actual rollout acceptance before claiming the
new runtime identities are active. The independent USB backup has a recurrent
transport fault and is not retried by this cutover.

Three existing automatic Git schedules (`ai_tools`, `security_inference_stack`,
`web_services`) are paused to prevent an unattended deployment during preparation.
Their prior schedules are saved privately on the host. Restore them only after
successful cutover, not merely after merging documentation.

## Project mapping

| Current Dockhand/Compose name | Prepared name |
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
All 11 source paths were staged/synced to layout commit `b61318a` without
deploying. Container IDs/start times and encrypted variables were verified
unchanged. This does not change container ownership. Explicit `name` values describe the prepared target;
Dockhand's project argument still takes precedence until its stack is renamed.

The only proposed container-name correction is `yawamf-monalithic` -> `yawamf`.
Its service name remains `yawamf`, the old DNS alias is retained, and its upstream
image repository name does not change. All other service/container identities,
host bindings and persistent bind paths remain unchanged.

## Checks already completed

- All 20 manifests and 61 resolved service definitions rendered successfully.
- All 84 existing stack/host policy tests passed; CI passed on the layout change.
- Eleven live stack configurations were compared with the prepared definitions
  using current non-secret overrides and synthetic secret values.
- Differences are project/private-network identity, relocated repository-local
  files/build context, explicit existing named volumes, the external shared arr
  bridge and YA-WAMF naming. The optional repair job now looks up `arr`.
- NPM, UniFi records and Quark's fixed-IP reservation were inspected read-only.
  Proposed cleanups are in [ingress and DNS](ingress-dns.md).

These are source/configuration checks, not post-deployment application acceptance.
The target layout has not been exercised by recreating production containers.

## Execution

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
   needs no change. Review `devenv` and the retired reservation before editing.
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
