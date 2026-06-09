# docker-configs
Personal Docker Compose stacks used on TrueNAS Scale. Most stacks expect external networks to exist and rely on values provided via a local `.env` file.

## Repo layout
- `arr_vpn_stack/` - Gluetun VPN stack with qBittorrent, Prowlarr, Radarr, Sonarr, and FlareSolverr.
- `media_related_stack/` - Plex and Unmanic.
- `monitoring_management/` - Prometheus, Grafana, SNMP exporter, and SNMP trap receiver.
- `security_inference_stack/` - Frigate, BirdNET-Go, Matter Server, Mosquitto, and YA-WAMF.
- `web_services/` - Nginx Proxy Manager, Cloudflare Tunnel, and Overseerr.

## Usage
Run a stack by pointing Docker Compose at the folder's compose file:

```bash
cd <stack>
docker compose up -d
```

## Windows/WSL boot startup
Docker Desktop can restart containers before WSL bind mounts are fully ready. That can make
containers briefly fail on boot even when their restart policy is correct.

Use `scripts/start-stacks-on-boot.ps1` from Windows Task Scheduler to start the stacks in a
controlled order:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\ServerAdmin\Documents\GitHub\docker-configs\scripts\start-stacks-on-boot.ps1"
```

To register the task from an elevated PowerShell session:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\ServerAdmin\Documents\GitHub\docker-configs\scripts\register-startup-task.ps1"
```

The wrapper waits 30 seconds after launching Docker Desktop. The WSL script then waits for
Docker, waits another 120 seconds, logs the currently running containers, ensures the
existing `dockhand` container is running, and uses the Dockhand API for the rest of the
orchestration. Before starting any network-dependent stacks it **waits for real outbound
internet/DNS** (probed from inside the `dockhand` container), because Docker Desktop can
restart containers before the WSL VM's networking is ready — in that window `gluetun`,
`cloudflare-tunnel` and `tailscale` fail their startup checks and exhaust their restart
retries, taking the Arr stack down with `gluetun`. It then stops the Arr stack containers,
starts `gluetun`, waits 60 seconds, and starts the rest of the Arr stack plus any other
configured stacks with containers that are not already running.

After the stacks are up it runs a **port-mapping remediation pass**: the same boot race can
leave a container "running" (and healthy, since health checks run inside the container) yet
with no host port mapping, so it is unreachable from the host/LAN. Any such container is
restarted through the Dockhand API to re-establish its published ports, without recreating
it or touching its Dockhand-managed env. Finally, **Nginx Proxy Manager (`npm`) is brought
up last** so it resolves upstream container IPs against the final running set rather than
stale/missing ones. Logs are written to `%USERPROFILE%\docker-startup-logs`.

The task is registered as `\Server Automation\Start Docker Compose Stacks`.

Notes:
- The startup script expects the `dockhand` container to already exist. It does not run
  `docker compose up` for application stacks during boot orchestration.
- Most stacks expect a `.env` file in the same directory as the compose file.

## Environment variables
Common keys used across stacks include:
- `CONFIG_PATH`, `DOCKERCONFIGPATH`, `DOWNLOADSPATH`, `MEDIA_PATH` - host paths for persistent data
- `TZ` - time zone
- `PLEX_CLAIM`, `TUNNEL_TOKEN`, `NEW_DOMAIN_DNS_EDIT_CF`, VPN credentials, and service-specific secrets

Docker's environment file handling is documented here:
- https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/

## Networking assumptions
These stacks reference external networks that must already exist on the host:
- `general_brg`
- `vpn_stack_brg`

Some deployments may also use additional external networks such as `dmz_mac_vlan` or `service_mac_vlan`, but they are not required by the active compose files in this repo.

## Configuration Notes

### Web Services
When chaining Cloudflare Tunnel (`cloudflared`) with Nginx Proxy Manager (`nginx-pm`), avoid redirect loops:
- If Nginx Proxy Manager has Force SSL enabled, point Cloudflare Tunnel at `https://nginx-rp:443` and disable TLS verification in Cloudflare.
- If Cloudflare Tunnel targets `http://nginx-rp:80`, disable Force SSL in Nginx Proxy Manager for that host and let Cloudflare handle edge redirects.
