# Optimisarr Linux sidecar — Quark dev

A dedicated Git-backed Dockhand stack for testing the development worker on
Quark's Intel GPU. The image reuses Optimisarr's Linux media runtime and shared
worker engine. Its dashboard is at `https://optimisarr-sidecar.pownet.uk` once
the private UniFi DNS and NPM proxy route are configured.

## Dockhand configuration

- Repository: `Jellman86/docker-configs`, branch `main`.
- Compose path: `optimisarr_sidecar/docker-compose.yml`.
- Stack name: `optimisarr_sidecar`; environment: Quark.
- Enable **Repull images**. Keep scheduled updates disabled during testing.
- First deployment: generate a code in the main Optimisarr server's Workers
  settings. Store `OPTIMISARR_PAIRING_CODE` as an encrypted stack variable, sync
  the Git stack, then deploy it through Dockhand. Remove the consumed code from
  the variable store after pairing. The named config volume retains identity.
- For later updates, wait for the Optimisarr dev CI/image publication, then sync
  and deploy through Dockhand. Never deploy a failed or still-building image.

The dashboard is read-only. Manage scheduling, draining and pairing on the main
server. Port 8788 binds only to Quark's private address. NPM should forward the
private hostname to `192.168.213.102:8788` using the existing wildcard TLS cert.

`/work` is a bounded 4 GiB tmpfs, not a media-library mount. The container has a
6 GiB memory limit and no swap allowance, leaving host RAM for other services.
There is one job slot. Jobs require space for both source and candidate; larger
jobs are declined safely. Working files disappear on recreation; the worker
hands leases back during its 45-second shutdown window. Pairing persists.

No library directories or Docker socket are mounted into this worker.
