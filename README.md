# docker-configs
Personal Docker Compose stacks used on TrueNAS Scale. Most stacks expect external networks to exist and rely on values provided via a local `.env` file.

## Repo layout
- `arr_vpn_stack/` - Gluetun VPN stack with qBittorrent, Prowlarr, Radarr, Sonarr, and FlareSolverr.
- `media_related_stack/` - Plex and Optimisarr.
- `monitoring_management/` - Prometheus, Grafana, SNMP exporter, and SNMP trap receiver.
- `security_inference_stack/` - Frigate, BirdNET-Go, Matter Server, Mosquitto, and YA-WAMF.
- `web_services/` - Nginx Proxy Manager, Cloudflare Tunnel, and Tailscale.

## Usage
Run a stack by pointing Docker Compose at the folder's compose file:

```bash
cd <stack>
docker compose up -d
```

Notes:
- Most stacks expect a `.env` file in the same directory as the compose file.

## Environment variables
Common keys used across stacks include:
- `CONFIG_PATH`, `DOCKERCONFIGPATH`, `DATAPATH`, `DOWNLOADS_PATH`, `MEDIA_PATH` - host paths for persistent data
- `TZ` - time zone
- `PLEX_CLAIM`, `TUNNEL_TOKEN`, `NEW_DOMAIN_DNS_EDIT_CF`, VPN credentials, and service-specific secrets

Docker's environment file handling is documented here:
- https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/

## Networking assumptions
These stacks reference external networks that must already exist on the host:
- `general_brg`
- `arr_stack_brg`

The compose files may use the internal service network key `vpn_stack_brg`, but
it resolves to the external Docker network `arr_stack_brg` by default. Override
with `NETWORK` only if the host uses a different external network name.

Some deployments may also use additional external networks such as `dmz_mac_vlan` or `service_mac_vlan`, but they are not required by the active compose files in this repo.

## Configuration Notes

### Web Services
When chaining Cloudflare Tunnel (`cloudflared`) with Nginx Proxy Manager (`nginx-pm`), avoid redirect loops:
- If Nginx Proxy Manager has Force SSL enabled, point Cloudflare Tunnel at `https://nginx-rp:443` and disable TLS verification in Cloudflare.
- If Cloudflare Tunnel targets `http://nginx-rp:80`, disable Force SSL in Nginx Proxy Manager for that host and let Cloudflare handle edge redirects.
