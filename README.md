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

## Configuration Notes

### Web Services (Cloudflare Tunnel + Nginx Proxy Manager)
When chaining Cloudflare Tunnel (`cloudflared`) with Nginx Proxy Manager (`nginx-pm`), beware of **Infinite Redirect Loops** (ERR_TOO_MANY_REDIRECTS).

- **The Issue:** If NPM has "Force SSL" enabled, it redirects all HTTP traffic to HTTPS. If Cloudflare Tunnel connects to NPM via HTTP (e.g., `http://nginx-rp:80`), NPM returns a 301 Redirect. Cloudflare sees this and retries, creating a loop.
- **The Fix:**
    1.  **Option A (Recommended):** Configure Cloudflare Tunnel to connect to NPM via HTTPS (`https://nginx-rp:443`) with "No TLS Verify" enabled in the Cloudflare dashboard.
    2.  **Option B:** Disable "Force SSL" in Nginx Proxy Manager for the specific proxy host and let Cloudflare handle the HTTP->HTTPS redirection at the edge.

## Networking assumptions
These stacks reference external networks that must already exist on the host:
- `dmz_mac_vlan`
- `service_mac_vlan`
- `general_brg`
- `vpn_stack_brg`

If the networks don’t exist, create them before starting a stack.
