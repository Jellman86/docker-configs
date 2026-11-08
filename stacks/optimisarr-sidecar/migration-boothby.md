# Quark to Boothby sidecar migration

Prepared 8 November 2026. Owner authorized moving the existing worker with configuration intact. Optimisarr's active agent reviewed the code and confirmed the identity is credential-based, not bound to host/IP. It has no test requiring Quark's worker. This runbook does not claim cutover has completed.

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
6. Sync/deploy through Dockhand. Verify worker 5 is online while still drained, heartbeat problem is empty, and fresh Intel encoder probes succeeded. Confirm no Quark sidecar process is running. Update the existing NPM proxy upstream; preserve private UniFi DNS and TLS.
7. `DELETE /api/workers/5/drain` to resume only after checks pass. Verify readiness/claims and the outcome of normally scheduled work. Record runtime image, config integrity, capacities, actual encoder list and current backup coverage.

## Rollback

Drain Boothby and wait for zero jobs, then set its replicas to zero and sync/deploy through Dockhand. Verify it is stopped before restoring Quark's active replicas to 1 and deploying the original pinned image and volume on Quark. Point NPM upstream back to `.102:8788`, verify worker 5 online/healthy and only then resume. Do not revoke/re-pair the worker or run both hosts simultaneously.
