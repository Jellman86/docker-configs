# Quark to Boothby sidecar migration

Completed 8 November 2026. Owner authorized moving the existing worker with configuration intact. Optimisarr's active agent reviewed the code and confirmed the identity is credential-based, not bound to host/IP. It has no test requiring Quark's worker. The verified cutover is recorded below; preserve the same safeguards for future moves.

## Safety contract

Worker 5 (`Quark Linux dev`) must remain the same worker. Preserve the entire private `/config` directory, especially mode-0600 `pairing.json`; do not print or commit credentials. `/work` is disposable and must not be migrated. The process lock is local to a config directory and cannot prevent duplicate identities on two hosts.

Keep the exact running image for the move:
`ghcr.io/jellman86/optimisarr-sidecar@sha256:c80b334e964b056fe94784934be13595b894a2033c7ed955a8af398db8171e60`, revision `01c8f6888be2e5bf2b05c7e60aec7c3c1aeef702`.

Preserve the main server's verification/replacement gates. Do not retry production media or change encoding policies just to test the move. Observe the first normally scheduled work and record its actual outcome separately from connectivity/capability acceptance.

## Sequence

1. Confirm the saved server address exactly matches `OPTIMISARR_SERVER` and its HTTPS health endpoint is reachable from Boothby. Preflight confirmed `https://optimisarr.pownet.uk`.
2. `POST /api/workers/5/drain`; wait until `heldLeases=0` and `activeJobs=[]`. Let the current job finish. The durable drain remains effective after moving.
3. Require green infrastructure CI and known-good source image publication. Set Quark's Git-stack variables to `OPTIMISARR_REPLICAS=0`, its original private bind, and the fixed source image. Sync/deploy through Dockhand and confirm the old process is stopped/removed before copying state or starting Boothby. Retain the external source volume.
4. Capture the old volume/config into a private, permission-restricted archive on Quark. Check inventory/hashes without logging values. Transfer privately to Boothby and restore to `/mnt/services/docker/optimisarr-sidecar/config`, retaining safe paths and UID/GID 1000. Apply/verify SELinux labels. Keep the source/rollback archive unchanged.
5. Create Boothby's external volume through Dockhand's volume API, with the explicit local bind options in the README. Register a separate Git-stack record for the same source path on Boothby. Use fixed image, exact server address, concurrency 1, private bind `.103` and replicas 1. Do not set a pairing code.
6. Sync/deploy through Dockhand. Verify worker 5 is online while still drained, no new heartbeat/authentication problem has appeared, and fresh Intel encoder probes succeeded. Confirm no Quark sidecar process is running. Route private UniFi DNS to the active host and verify its NPMplus upstream/TLS. Retain the old route for rollback.
7. `DELETE /api/workers/5/drain` to resume only after checks pass. Verify readiness/claims and the outcome of normally scheduled work. Record runtime image, config integrity, capacities, actual encoder list and current backup coverage.

## Rollback

Drain Boothby and wait for zero jobs, then set its replicas to zero and sync/deploy through Dockhand. Verify it is stopped before restoring Quark's active replicas to 1 and deploying the original pinned image and volume on Quark. Point NPM upstream back to `.102:8788`, verify worker 5 online/healthy and only then resume. Do not revoke/re-pair the worker or run both hosts simultaneously.

## Completed cutover evidence

Job 6212 finished before stopping Quark. Zero leases/jobs were verified; both hosts were stopped through Dockhand before copying pairing. The protected configuration copy matched its original checksum, mode 0600, UID/GID 1000, and was restored with SELinux labels. Worker ID 5 remains named `Quark Linux dev`; this version has no supported rename control. No new pairing/revocation occurred.

Boothby uses Dockhand environment 3, Git stack 20, replicas 1. Quark environment 1/stack 6 has replicas 0, no worker container, and the retained original volume for rollback. The exact image above remains pinned. Discover IDs before operational use. Both stack records use explicit variables and automatic updates are disabled.

Fresh Boothby capabilities are software `libsvtav1`, `libx264`, `libx265` and hardware `h264_qsv`, `h264_vaapi`, `hevc_qsv`, `hevc_vaapi`. UHD 770 does not offer AV1 hardware encode. All four hardware paths passed small synthetic encodes as the worker's UID with SELinux enforcing. The historical `lastProblemAt` was `2026-11-08T06:24:18.8413726Z`, predating migration; check-in does not clear this field. A new fault must be distinguished from that retained history.

After resuming, normal work was claimed and reached Measuring without manually retrying jobs or altering server verification policy. This connectivity/capability evidence alone does not certify output quality or every job's success.

Private dashboard: https://optimisarr-sidecar.pownet.uk → UniFi `.103` → Boothby NPMplus proxy 2 → `.103:8788`, verified with normal DNS and trusted HTTPS 200. The main Optimisarr server remains on Quark. Its agent has been told the new worker deployment target. Quark's previous proxy host 11 also points to Boothby and remains fallback; moving the identity back additionally requires reversing the private DNS/edge route.

A protected one-off pairing snapshot exists on Quark's original developer SSD. Automated Boothby capture/off-site backup is not implemented and Quark's existing application archive job does not cover Boothby. Never treat the retained old volume as a current backup after later config changes.
