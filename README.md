# docker-configs
Personal Docker Compose stacks used on TrueNAS Scale. Most stacks expect external networks to exist and rely on values provided via a local `.env` file.

## Repo layout
- `arr_vpn_stack/` - Gluetun VPN stack with qBittorrent, Prowlarr, Radarr, Sonarr, and FlareSolverr.
- `media_related_stack/` - Plex and Unmanic.
- `security_inference_stack/` - Frigate, BirdNET-Go, Matter Server, Mosquitto, and YA-WAMF.
- `web_services/` - Nginx Proxy Manager, Cloudflare Tunnel, and Overseerr.

## Usage
Run a stack by pointing Docker Compose at the folder's compose file:

```bash
cd <stack>
docker compose up -d
```

Notes:
- `security_inference_stack/` uses `docker_compose.yml` (underscore naming).
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
