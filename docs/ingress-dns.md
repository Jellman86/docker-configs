# Ingress and private DNS

**Reviewed and accepted: 18 October 2026.** Runtime acceptance is recorded in the
[cutover guide](cutover-plan.md).
NPM and UniFi remain authoritative for their live configuration. This document
records intent; Compose does not create DNS records, proxy hosts or access policies.

## Naming and traffic

Use service URLs such as `sonarr.pownet.uk`, independent of the host/project name.
Keep `quark.pownet.uk` for SSH, SMB and host administration. Avoid new
`<service>-quark` or `<service>-riker` URLs and preserve working client aliases
until they can be deliberately retired.

```text
Private client -> UniFi DNS -> Quark 192.168.213.102:443 -> NPM -> application
Public client  -> Cloudflare Access/Tunnel -> existing NPM origin -> application
Tailscale      -> native host/subnet routing -> the same private service endpoints
```

A Docker service name is useful only on a shared Docker network. It is not a
UniFi DNS name. Renaming a Compose project should not change a service URL or
require a new public tunnel. Host-networked applications need a host endpoint.
Keep TLS verification, original HTTP Host/TLS server-name handling, WebSockets
and application-specific proxy settings when changing a backend.

## UniFi findings and intended records

After retiring the stale development entry, 24 enabled static A records point
to `192.168.213.102`. Quark has an active fixed-IP reservation for that address.
Existing A records are adequate for this home lab; converting them all to CNAMEs
would add cutover work without fixing the naming issue.

| Item | Accepted state | Maintenance note |
|---|---|---|
| Canonical services | Service names point to Quark `.102` | Preserve; no broad DNS rewrite |
| `devenv.pownet.uk` | Stale record removed | Reintroduce only with a real, intended backend |
| Riker reservation/local DNS | Disabled for the inactive retired host | Client history is retained; no stale A answer remains |
| Quark client | Friendly/local DNS identity and `.102` reservation preserved | Cached DHCP hostname `dell-compute` is informational; no forced lease renewal |
| `overseerr.pownet.uk` | Alias for the Seerr route | Preserve until clients use `seerr.pownet.uk` |
| Long YA-WAMF URL | Still listed on its NPM proxy host | Check actual client/DNS use before removing the alias |

Do not move a record to Quark merely because its old target is Riker. The
application must exist on Quark first. Preserve unrelated DNS records, existing
TTLs and public DNS/Access policy unless their change is separately intended.

## NPM backend map

These targets describe the canonical service route. Preserve existing access
lists, certificate assignments, advanced configuration and application settings.

| Private URL prefix (`.pownet.uk`) | Backend | Cutover note |
|---|---|---|
| `dockhand` | `http://dockhand:3000` | Stable container/service name |
| `npm` | `http://npm:81` | Administrative endpoint |
| `frigate` | `http://frigate:5000` | Current trusted-network, unauthenticated origin policy |
| `birdnet` | `http://birdnet-go:8080` | Stable service name |
| `yawamf` | `http://yawamf:8080` | Canonical target accepted; old bridge alias retained for clients |
| `homeassistant` | `http://192.168.213.102:8123` | Host endpoint accepted; no bridge IP dependency |
| `openviking` | `http://openviking:1933` | Preserve application authentication |
| `openknowledge` | `http://openknowledge:8080` | NPM access list (Basic auth) is the only auth; preserve Host/`X-Forwarded-Proto`, WebSockets, unbuffered `/mcp` |
| `hermes` | `http://hermes-dashboard:9119` | Intentional trusted-proxy network alias |
| `playwright-mcp` | `http://playwright-mcp:8931` | Preserve NPM access list and application allow-list |
| `optimisarr-sidecar` | `http://192.168.213.102:8788` | Existing host-bound endpoint |
| `cockpit` | `https://192.168.213.102:9090` | Native host service; preserve TLS/origin settings |
| `sonarr` | `http://sonarr:8989` | Preserve allowed hosts and app authentication |
| `radarr` | `http://radarr:7878` | Preserve allowed hosts and app authentication |
| `prowlarr` | `http://prowlarr:9696` | Preserve allowed hosts and app authentication |
| `seerr` | `http://seerr:5055` | Includes existing public and Overseerr aliases |
| `torrents` | `http://gluetun:8081` | qBittorrent shares the VPN namespace |
| `plex` | `http://192.168.213.102:32400` | Host networking |
| `jellyfin` | `http://192.168.213.102:8096` | Host networking |
| `cleanuparr` | `http://cleanuparr:11011` | Stable service name |
| `optimisarr` | `http://optimisarr:8787` | Stable service name |
| `stirling` | `http://stirling-pdf:8080` | Stable service name |
| `immich` | `http://immich-server:2283` | Preserve upload limits, timeouts and WebSockets |
| `twenty` | `http://twenty-api:8080` | Intentional network alias |

NPM uses the shared `general_brg` and `npm_proxy_backends` networks. Keep both
external during a project rename. Do not point a bridge service at a container IP
or rely on a project-generated default network from a different stack.

The `yawamf` container keeps its old DNS alias for compatibility. NPM now uses
the canonical target, and the service URL passed acceptance.
That avoids a simultaneous proxy/DNS/container rename. The upstream image name
`yawamf-monalithic` is a registry contract and remains unchanged.

## Exposure boundaries

Gluetun's control port 8000 is bound to Quark's **LAN** address, not its Tailscale
address. This is separate from private HTTPS routing; do not expose it through
NPM or Cloudflare merely to make an application discover it. qBittorrent's UI is
served through Gluetun. Immich's unauthenticated ML port stays LAN-bound and has
no NPM/public route. Database, cache and internal tool ports stay private.

Most NPM routes currently have no NPM access list and rely on trusted-network
placement plus application authentication. Dockhand login and Frigate browser
auth remain separate audit decisions. Do not silently alter those policies or
claim TLS provides application authentication as part of the rename.

## Validation after future changes

After explicit cutover authorization, resolve each canonical private name through
UniFi and through the intended Tailscale client path. Check valid TLS, the actual
application, authentication and WebSockets where used. Test dependencies from
inside their networks. Confirm that old compatibility names have no required
clients before removing them. Signed-in public services and actual external Plex
playback still require their own checks; a login page or unauthenticated 403 is
not proof of signed-in functionality.
