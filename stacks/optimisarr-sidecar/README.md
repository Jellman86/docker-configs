# Optimisarr Linux development worker

Git-backed Dockhand entrypoint: [compose.yaml](compose.yaml). The worker moved from Quark to Boothby on 8 November 2026, preserving worker 5's existing pairing. [Migration runbook](migration-boothby.md) records the sequence, rollback and verification. Do not run both hosts with the copied identity.

## Explicit host settings

- Repository `Jellman86/docker-configs`, branch `main`, stack `optimisarr-sidecar`, Compose path `stacks/optimisarr-sidecar/compose.yaml`.
- Set `OPTIMISARR_REPLICAS=1` only on the active host; the default is zero. Retired Quark keeps `0` so a sync/deploy cannot start its copied identity.
- Boothby: `OPTIMISARR_BIND_IP=192.168.213.103`. Quark rollback requires `.102`. The default binds loopback.
- For migration, pin `OPTIMISARR_SIDECAR_IMAGE` to the exact source image digest. Upgrade separately after successful cutover and successful image CI/publication.
- `OPTIMISARR_SERVER` must exactly match the saved pairing server address; the current address is `https://optimisarr.pownet.uk` and is reachable from Boothby.
- Leave `OPTIMISARR_PAIRING_CODE` unset for migration. First-time pairing is a different operation and must not replace the existing identity.
- `OPTIMISARR_WORKER_NAME` describes a new pairing only; the existing server worker may retain its original name until renamed through a supported app control.
- Enable repull images and forced recreation; leave automatic updates disabled during migration/testing. Resolve environment and stack IDs from the Dockhand API before deployment.

The external volume is deliberately named `optimisarr_sidecar_sidecar-config`. On Boothby, provision it through Dockhand's volume API using the local driver and bind device `/mnt/services/docker/optimisarr-sidecar/config`, type `none`, option `bind`. This keeps state on the data SSD. Create that directory with UID/GID 1000 and `container_file_t` SELinux context before starting the worker; restore the protected config while the Quark instance is stopped. Never mount the same identity on two running hosts.

The read-only dashboard remains `https://optimisarr-sidecar.pownet.uk`; UniFi resolves it to `.103`; Boothby's own NPMplus forwards HTTPS to `.103:8788`. Quark's old proxy remains a fallback. Manage pairing, scheduling and drain/resume through the main server.

## Resource and recovery limits

There is one job slot, a bounded 4 GiB RAM `/work`, a 256 MiB `/tmp`, and a 6 GiB container memory limit with no swap allowance. RAM scratch counts against that limit. Jobs need room for source plus candidate; overlarge jobs are declined rather than spilling into business storage. No media library or Docker socket is mounted. Pass `/dev/dri` for Intel capability probing and verify actual encoder availability before resuming claims.

The worker retains its 45-second shutdown grace, but drain and wait for zero leases/jobs before stopping it. The old volume remains a protected rollback copy; it does not protect future changes on Boothby. Until Boothby backup automation includes this directory, take and retain a separate protected recovery copy of the pairing/config and document that coverage gap.
