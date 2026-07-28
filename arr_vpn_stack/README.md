# ARR and VPN Stack

Git-backed Dockhand stack for the download and media-management services on Riker. The Compose project is named `arr_stack`.

## Services

| Service | Role | Published access |
|---|---|---|
| `gluetun` | VPN gateway, DNS resolver, and HTTP proxy | qBittorrent TCP/UDP `5041`; Web UI `8081` |
| `qbittorrent` | Download client sharing Gluetun's network namespace | Through Gluetun only |
| `prowlarr` | Indexer manager | `9696` |
| `radarr` | Movie management | `7878` |
| `sonarr` | TV management | `8989` |
| `byparr` | Browser-backed indexer challenge helper | Riker port `8191` |
| `cleanuparr` | Queue and download cleanup | `11011` |
| `seerr` | Media request interface | `5055` |

Port variables in `docker-compose.yml` can override most published defaults.

## Topology and networking

- Compose file: `arr_vpn_stack/docker-compose.yml`
- Intended host: Riker / TrueNAS.
- External network: `${NETWORK:-arr_stack_brg}`.
- qBittorrent uses `network_mode: service:gluetun`; it has no independent network path or host ports.
- Byparr reaches the public web through Gluetun's HTTP proxy at `http://gluetun:8888` by default.
- Byparr publishes port 8191 on Riker so Quark-hosted applications can reuse
  the proven service without an NPM or public route.
- Prowlarr, Radarr, Sonarr, Cleanuparr, Seerr, and Gluetun communicate over `arr_stack_brg`.

Gluetun requires `/dev/net/tun` and `NET_ADMIN`. Confirm the external network and TUN device exist before first deployment.

## Persistent storage

| Host path | Container use |
|---|---|
| `${DOCKERCONFIGPATH}/gluetun` | VPN state and configuration |
| `${DOCKERCONFIGPATH}/qbittorrent` | qBittorrent configuration |
| `${DOCKERCONFIGPATH}/qbittorrent/logs` | qBittorrent `/logs`; retain only when needed for diagnostics or audit |
| `${DOCKERCONFIGPATH}/prowlarr` | Prowlarr state |
| `${DOCKERCONFIGPATH}/radarr` | Radarr state |
| `${DOCKERCONFIGPATH}/sonarr` | Sonarr state |
| `${DOCKERCONFIGPATH}/cleanuparr` | Cleanuparr state |
| `${DOCKERCONFIGPATH}/seerr` | Seerr state |
| `${DATAPATH}` | Shared `/data` tree for downloads and media imports |

Defaults are `/mnt/apps/docker` and `/mnt/tank`. Keep downloads and media on the same filesystem so Radarr and Sonarr can use hardlinks. Back up application configuration before migration or destructive recovery.

## Environment

Common settings:

- `PUID`, `PGID`, `TZ`
- `DOCKERCONFIGPATH`, `DATAPATH`, `NETWORK`
- Optional image and published-port overrides

Secrets that belong in Dockhand's encrypted variables:

- `WGPRIVKEY` for WireGuard, or `OPENVPNUSER` and `OPENVPNPASSWORD` for OpenVPN

VPN selection and policy variables include `VPNHOST`, `VPNPROTOCOL`, `VPNCOUNTRY`, `FIREWALL_INPUT_PORTS`, and `FIREWALL_OUTBOUND_SUBNETS`. Never commit a populated `.env` file.

## Deployment and updates

This stack is managed through its Git-backed Dockhand entry. Follow the repository-level deployment procedure in the [root README](../README.md): validate the Compose source, push the reviewed change, then deploy through Dockhand. Do not run lifecycle-changing `docker compose up`, `pull`, or `down` commands directly on Riker.

After deployment, verify:

1. Gluetun is healthy and reports the intended VPN exit before trusting qBittorrent.
2. qBittorrent is healthy and still shares Gluetun's network namespace.
3. Radarr, Sonarr, Prowlarr, Cleanuparr, and Seerr are healthy and retain their state.
4. Byparr is reachable from Quark at `http://192.168.213.101:8191` and uses
   Gluetun's proxy.
5. The `/data` mount points at the expected storage tree.

## Rollback

Revert the relevant Git commit or restore a previously reviewed image reference, push `main`, and redeploy through Dockhand. Application databases and configuration live outside the container images; restore those bind-mounted directories from backup only when state is damaged, and stop/recreate services through Dockhand before filesystem restoration.

## Security notes

- VPN credentials are secrets; do not place them in Git, logs, or documentation.
- Gluetun is deliberately privileged only with the network capability and TUN device needed for VPN routing.
- Do not expose Gluetun's proxy beyond trusted container/LAN boundaries.
- Byparr accepts arbitrary destination URLs and proxy overrides. Keep port 8191
  on the trusted LAN only; callers must use typed, allowlisted source adapters
  and must not forward user-controlled URLs or `X-Proxy-*` headers.
- qBittorrent must not be changed to a separate network without an explicit leak-prevention review.
- The detailed migration and application reference is in [`ARR_STACK_MIGRATION.md`](../ARR_STACK_MIGRATION.md).
