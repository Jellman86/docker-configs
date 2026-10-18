# Isolated NVIDIA worker acceptance

This Git-backed Dockhand stack tests the released Linux worker image on an NVIDIA
Docker host independently of any installed Windows service or production queue.
It requests GPU access and uses disposable RAM storage for configuration and media.
Recreation deliberately removes its pairing and scratch files.

Before deployment, pass image publication checks and set these stack variables in
Dockhand:

- `OPTIMISARR_IMAGE`: the published image pinned by digest.
- `OPTIMISARR_SERVER`: the isolated acceptance server, reachable from the worker.
- `OPTIMISARR_PAIRING_CODE`: that server's one-use code, stored as a secret.
- `OPTIMISARR_ACCEPTANCE_BIND`: a private host address reachable by the test observer.

The defaults leave it unpaired and expose its monitor only on localhost. Never use
a production pairing code. Restrict any remote monitor access to the test host.

Sync and deploy through Dockhand after Compose validation passes. Record the
image revision, GPU/driver and proved encoder capabilities. Run the application's
fleet acceptance harness with strict sidecar verification and independent VMAF,
including frame cadence, stream retention, size, replacement and rollback checks.
Observe source/candidate files on tmpfs and confirm cleanup. Remove the owned test
stack through Dockhand and revoke its temporary management connection afterward.
Docker CLI lifecycle operations are not the deployment path.
