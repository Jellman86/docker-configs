# docker-configs
Personal Docker Compose stacks used on TrueNAS Scale. Most stacks expect external networks to exist and rely on values provided via a local `.env` file.

## Repo layout
- `arr_vpn_stack/` — Gluetun VPN stack with qBittorrent + *arr tools + FlareSolverr + deunhealth.
- `cloudflare_related/` — Cloudflare Tunnel + DDNS.
- `cold_containers/` — Cold/occasional-use stacks. Currently: `crafty` (Minecraft server manager) and `valheim`.
- `general_services/` — Watchtower + Dozzle.
- `media_related_stack/` — Plex + Unmanic.
- `security_inference_stack/` — Frigate, BirdNET-Go, Home Assistant, Matter Server, Mosquitto, and YA‑WAMF.
- `web_services/` — Nginx Proxy Manager, PrivateBin, OpenSpeedTest, Overseerr.
- `Old_configs/` — Archived configs (not actively maintained).

## Usage
Run a stack by pointing Docker Compose at the folder’s compose file:

```bash
cd <stack>
docker compose up -d
```

Notes:
- `security_inference_stack/` uses `docker_compose.yml` (underscore naming).
- Some stacks expect additional config files (e.g., `security_inference_stack/config.yaml`).

## Environment variables
Most compose files expect a `.env` alongside the compose file. Common keys include:
- `CONFIG_PATH`, `DOCKERCONFIGPATH`, `DOWNLOADSPATH`, `MEDIA_PATH` — host paths for persistent data
- `TZ` — time zone
- `PLEX_CLAIM`, `TUNNEL_TOKEN`, `NEW_DOMAIN_DNS_EDIT_CF`, VPN credentials, etc.

Docker’s environment file handling is documented here:
- https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/

## Networking assumptions
These stacks reference external networks that must already exist on the host:
- `dmz_mac_vlan`
- `service_mac_vlan`
- `general_brg`
- `vpn_stack_brg`

If the networks don’t exist, create them before starting a stack.
