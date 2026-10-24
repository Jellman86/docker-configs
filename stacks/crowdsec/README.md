# CrowdSec

Deployment entrypoint: [`compose.yaml`](compose.yaml), Dockhand stack `crowdsec` on Quark.
See the [deployment map](../../docs/compose-layout.md) and [ingress and DNS](../../docs/ingress-dns.md).

CrowdSec's security engine reads Nginx Proxy Manager's logs, detects scanners,
brute force and exploit probes, and shares signals with the CrowdSec community.
[CrowdSec Web UI](https://github.com/TheDuffman85/crowdsec-web-ui) is the
self-hosted dashboard for alerts, decisions, metrics and notifications.

## Shape and why

| Choice | Reason |
|---|---|
| Separate stack, not inside `ingress` | A CrowdSec or dashboard update never recreates NPM, the single proxy for every service. |
| Logs bind-mounted read-only | NPM's container, image and log format stay untouched. The hub parser matches NPM's shipped format. |
| No firewall bouncer | Every LAN/tailnet client is whitelisted, and internet traffic arrives through Cloudflare Tunnel, so a host firewall would only ever see the tunnel itself. |
| No Cloudflare Worker bouncer by default | Upstream recommends the paid Workers plan; on the free plan its KV/request quotas are a poor fit for one public hostname. See [Remediation](#remediation). |
| Dashboard machine registered by a one-shot job | No manual `cscli` exec; the Dockhand secret is the only source of the password and re-registration is idempotent. |

## Services

| Service | Role | Access |
|---|---|---|
| `crowdsec` | Agent and Local API (LAPI) | `lapi` network only (`172.24.24.10:8080`, metrics `:6060`); UniFi syslog `192.168.213.102:5514/udp` |
| `web-ui-machine` | One-shot `cscli machines add --force`; exits 0 | No network |
| `crowdsec-web-ui` | Dashboard | `https://crowdsec.pownet.uk` through NPM (`crowdsec-web-ui:3000` on `npm_proxy_backends`) |

The only host port is the LAN-bound UniFi syslog listener. The `lapi` subnet is fixed (`172.24.24.0/24`) so
`config.yaml.local` can grant LAPI `trusted_ips` (alert deletion) to the dashboard alone.

## Detection inputs

- [`acquis.d/npm.yaml`](acquis.d/npm.yaml): NPM proxy-host, default-host and fallback access/error logs, type `nginx-proxy-manager`.
- Collections: `crowdsecurity/nginx-proxy-manager` (parser plus base HTTP scenarios) and `crowdsecurity/whitelist-good-actors`.
- Observation of private apps' sign-in failures (read-only log directories, never config or databases):

  | App | Log mounted at `/var/log/apps/…` | Hub collection |
  |---|---|---|
  | Jellyfin | `jellyfin/log_*.log` | `LePresidente/jellyfin` |
  | Seerr | `seerr/seerr.log` (Overseerr format) | `LePresidente/overseerr` |
  | Sonarr / Radarr / Prowlarr | `<app>/<app>.txt` | `schiz0phr3ne/<app>` |
  | qBittorrent | `qbittorrent/qbittorrent.log` | `gilbsgilbs/qbittorrent` |

  These apps are reachable only from the LAN/tailnet (Seerr publicly only behind
  Cloudflare Access), so their alerts fire only for sources outside the home whitelist.
  Plex has no sign-in log to parse (authentication happens at plex.tv); its direct
  WAN port forward (6001 -> 32400) is visible only to a firewall-level source.
- UniFi gateway syslog ([`acquis.d/unifi.yaml`](acquis.d/unifi.yaml), `crowdsecurity/unifi`): the
  UCG-Max sends remote syslog (UniFi "SIEM server" mode) to `192.168.213.102:5514/udp`, LAN-bound.
  UniFi Network 10.6 sends firewall and IPS events only as CEF, and the predefined "Block All
  Traffic" policies cannot log. A custom UniFi policy, **CrowdSec: log WAN TCP probes**
  (External -> Gateway, TCP, new connections, Block, Syslog logging), therefore logs the drops
  the default policy already makes; no TCP is allowed External -> Gateway, so behaviour is unchanged.
  - [`parsers/quark-unifi-cef-syslog.yaml`](parsers/quark-unifi-cef-syslog.yaml) routes CEF lines
    from the syslog stream to the hub `crowdsecurity/unifi-cef` parser (upstream instead suggests
    an rsyslog relay that splits CEF into a `type: cef` file).
  - [`parsers/quark-unifi-cef-source.yaml`](parsers/quark-unifi-cef-source.yaml) fills the source
    for CEF 203 "Blocked by Firewall", which carries `UNIFIsrcIp`/`UNIFIsrcClientIp`, not `src`.
  - [`scenarios/quark-unifi-wan-blocked.yaml`](scenarios/quark-unifi-wan-blocked.yaml): 10+ blocks
    from one internet source within about 10 minutes. UniFi 10.6 omits ports, so the hub's
    port-scan scenario cannot fire from UniFi data.
  - [`scenarios/quark-unifi-ips.yaml`](scenarios/quark-unifi-ips.yaml): any CyberSecure IPS detection.
  Both are observation-only (`remediation: false`).
- [`parsers/quark-private-whitelist.yaml`](parsers/quark-private-whitelist.yaml): RFC1918, Docker bridges and the tailnet `100.64.0.0/10` (including IPv4-mapped IPv6 forms) are never alerted on or banned.

Internet clients arrive from Cloudflare Tunnel through the Docker host gateway
(`172.18.0.1`). NPM's global real-IP header is `X-Real-IP`, which Cloudflare does
not send, so the publicly routed proxy hosts carry this advanced config to log the
real client:

```nginx
# Cloudflare Tunnel reaches NPM via the Docker host gateway; log the real client.
set_real_ip_from 172.18.0.1;
real_ip_header CF-Connecting-IP;
real_ip_recursive off;
```

Only connections from `172.18.0.1` may set the address, and LAN/tailnet clients
keep their real address. Add the block to any proxy host that later gains a public
tunnel route. Without it CrowdSec sees only the whitelisted gateway.

## Persistent storage

| Host path | Purpose | Recovery |
|---|---|---|
| `/mnt/services/quark/docker/crowdsec/config` | Generated config, machine credentials, Console enrollment, hub state | Included |
| `/mnt/services/quark/docker/crowdsec/data` | Alert/decision SQLite (WAL) and hub data | Excluded, rebuildable |
| `/mnt/services/quark/docker/crowdsec/web-ui` | Dashboard accounts, sessions, notification settings (SQLite + WAL) | Included |

Create `web-ui` as `1000:1000` before first deployment (the dashboard runs as the
upstream `node` user with all capabilities dropped). Docker creates the others.
Add the two included paths to the live `/etc/quark-app-backup.json` as well as the example.

## Variables

| Variable | Kind | Purpose |
|---|---|---|
| `CROWDSEC_WEB_UI_LAPI_PASSWORD` | Encrypted Dockhand secret | Dashboard's LAPI machine password (`openssl rand -hex 32`) |
| `TZ` | Optional | Defaults to `Europe/London` |

Rotating the secret and redeploying re-registers the machine with the new value.

## Deployment and checks

Follow the [operations guide](../../docs/operations.md). After deployment:

1. `crowdsec` is healthy; `web-ui-machine` exited 0; `crowdsec-web-ui` is healthy.
2. `cscli metrics show acquisition` lists `/var/log/npm/*` with parsed lines, and `cscli machines list` shows `crowdsec-web-ui`.
3. `https://crowdsec.pownet.uk` shows the login page and, once signed in, LAPI status and alerts.
4. A public request to a tunnel hostname logs a public `[Client …]` address, not `172.18.0.1`.

The first visitor creates the dashboard administrator. Complete that immediately after
first deployment and keep the credential in the private credential store.

## Remediation

CrowdSec here detects and records decisions, and the dashboard can add manual bans,
but nothing yet enforces them. The only layer that can enforce against internet
clients is Cloudflare, in front of the tunnel. When that is wanted, add the official
[Cloudflare Worker bouncer](https://docs.crowdsec.net/u/bouncers/cloudflare-workers)
as a service in this stack. Scope `routes_to_protect` to the public hostnames, set
`only_include_decisions_from: [crowdsec, cscli]` to keep KV writes small, choose the
route fail mode deliberately, and store its LAPI key and Cloudflare token in Dockhand.
Optional: enroll in the CrowdSec Console (`cscli console enroll`) for its hosted view.

## Rollback

Revert the Git change and redeploy, or stop the stack through Dockhand. NPM is
unaffected either way. Removing the real-IP block from a proxy host only returns
its logs to showing the gateway address.
