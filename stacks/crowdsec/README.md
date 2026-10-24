# CrowdSec

Deployment entrypoint: [`compose.yaml`](compose.yaml), Dockhand stack `crowdsec` on Quark.
See the [deployment map](../../docs/compose-layout.md) and [ingress and DNS](../../docs/ingress-dns.md).

CrowdSec's security engine reads Nginx Proxy Manager, media-app and UniFi gateway
logs, detects scanners, brute force and exploit probes, and shares signals with the
CrowdSec community. It is **observation only**: nothing enforces its decisions.
The dashboard is the hosted [CrowdSec Console](https://app.crowdsec.net), where the
engine is enrolled as `quark` (tags `quark`, `homelab`, Community plan).

## Shape and why

| Choice | Reason |
|---|---|
| Separate stack, not inside `ingress` | A CrowdSec update never recreates NPM, the single proxy for every service. |
| Logs bind-mounted read-only | NPM's container, image and log format stay untouched. Hub parsers match the shipped formats. |
| Hosted Console, no self-hosted UI | The self-hosted TheDuffman85 Web UI (23 October) was retired on 24 October; the Console is far richer for one engine. |
| No firewall bouncer | LAN/tailnet clients are whitelisted, and internet web traffic arrives through Cloudflare Tunnel, so a host firewall would only see the tunnel. |
| No Cloudflare Worker bouncer | Upstream recommends the paid Workers plan; free-plan KV/request quotas are a poor fit for one public hostname. See [Remediation](#remediation). |
| Acquisition `transform` filters | Lines no parser can use are dropped before parsing, so routine chatter is not reported as "unparsed". |

## Service

| Service | Role | Access |
|---|---|---|
| `crowdsec` | Agent and Local API (LAPI) | Stack default network only; UniFi syslog `192.168.213.102:5514/udp` (LAN-bound) |

## Detection inputs

Every file in [`acquis.d/`](acquis.d/) has a `transform` that keeps only the lines its
parser uses (`(<condition>) ? [evt.Line.Raw] : []`; an empty list emits no event).

| Source | Acquisition | Kept lines | Hub collection / scenarios |
|---|---|---|---|
| NPM proxy/default/fallback access + error logs | `npm.yaml`, type `nginx-proxy-manager` | All except nginx "buffered to a temporary file" warnings | `crowdsecurity/nginx-proxy-manager` (base HTTP scenarios) |
| Jellyfin `log_*.log` | `jellyfin.yaml` | `has been denied` | `LePresidente/jellyfin` |
| Seerr `seerr.log` (Overseerr format) | `seerr.yaml`, type `overseerr` | Failed sign-in/login | `LePresidente/overseerr` |
| Sonarr / Radarr / Prowlarr `<app>.txt` | `sonarr.yaml` etc. | `Auth-Failure` | `schiz0phr3ne/<app>` |
| qBittorrent `qbittorrent.log` | `qbittorrent.yaml` | `WebAPI login failure` | `gilbsgilbs/qbittorrent` |
| UCG-Max remote syslog | `unifi.yaml`, syslog UDP 5514, type `unifi` | `[WAN_` firewall drops and `dropbear` | `crowdsecurity/unifi` -> `iptables-scan-multi_ports`, `ssh-bf` |

App logs are mounted read-only from their log directories only, never config or
databases. Those apps are LAN/tailnet only (Seerr is public only behind Cloudflare
Access), so their alerts fire only for sources outside the home whitelist. Plex has no
sign-in log (authentication is at plex.tv); its WAN forward is seen only at the gateway.

[`parsers/quark-private-whitelist.yaml`](parsers/quark-private-whitelist.yaml): RFC1918, Docker
bridges and the tailnet `100.64.0.0/10`, including IPv4-mapped IPv6 forms (qBittorrent logs
`::ffff:172.29.x.x`), are never alerted on.

### UniFi gateway (configured through the UniFi API, not Compose)

- **Remote syslog:** setting `rsyslogd` = SIEM server `192.168.213.102:5514`, `this_controller: false`
  (UniFi sends to the console *or* a SIEM server, not both), `log_all_contents: true`, `debug: false`.
- **Logged WAN drops:** the predefined "Block All Traffic" policies are locked and cannot log. Custom
  policy **CrowdSec: log WAN TCP probes** (External -> Gateway, TCP, connection state NEW, Block,
  Syslog logging; index 10000) logs the drops the default policy already makes. No TCP is allowed
  External -> Gateway, so behaviour is unchanged; Plex's forward (External -> Internal), WireGuard
  (UDP) and return traffic are untouched. Do **not** add a broad custom block External -> Internal:
  custom policies are evaluated before the predefined allows (port forward, return traffic).
- **Hostname repair:** CrowdSec's syslog server reads the leading digits of the gateway hostname
  `3-Bank-Street` as the RFC3164 tag, so gateway lines arrive as
  `3-Bank-Street 3: -Bank-Street [WAN_LOCAL-D-10000] ... SRC= DPT=`.
  [`parsers/quark-unifi-syslog-host.yaml`](parsers/quark-unifi-syslog-host.yaml) (mounted with an
  `a-` prefix so it runs before `crowdsecurity/unifi-logs`) re-splits them exactly as the hub parser
  would. It only matches the mangled form.
- UniFi 10.6 also emits CEF events (for example 203 "Blocked by Firewall", without ports); no hub
  scenario uses them. Upstream's rsyslog relay is needed only for CEF and is not used.
- Pre-change UniFi settings and the policy ID are saved privately under
  `/mnt/apps/developer/jellman86/recovery/unifi-*-20261024.*` for rollback.

### Real client IP for public tunnel hosts

Internet clients arrive from Cloudflare Tunnel through the Docker host gateway
(`172.18.0.1`). NPM's global real-IP header is `X-Real-IP`, which Cloudflare does not
send, so the publicly routed NPM proxy hosts (`yawamf`, `seerr`) carry this advanced config:

```nginx
# CrowdSec: Cloudflare Tunnel reaches NPM via the Docker host gateway; log the real client.
set_real_ip_from 172.18.0.1;
real_ip_header CF-Connecting-IP;
real_ip_recursive off;
```

Only connections from `172.18.0.1` may set the address; LAN/tailnet clients keep theirs.
Add the block to any proxy host that later gains a public tunnel route.

## Persistent storage

| Host path | Purpose | Recovery |
|---|---|---|
| `/mnt/services/quark/docker/crowdsec/config` | Generated config, machine and Console credentials, hub state | Included (example and live `/etc/quark-app-backup.json`) |
| `/mnt/services/quark/docker/crowdsec/data` | Alert/decision SQLite (WAL) and hub data | Excluded, rebuildable |

## Variables

| Variable | Kind | Purpose |
|---|---|---|
| `CROWDSEC_ENROLL_KEY` | Encrypted Dockhand secret, optional | Console enrollment key; the image enrolls as `quark` on start and harmlessly reports "already enrolled" afterwards. A wrong key stops CrowdSec from starting (`set -e`). |
| `TZ` | Optional | Defaults to `Europe/London` |

## Deployment and checks

Follow the [operations guide](../../docs/operations.md). After deployment:

1. `crowdsec` is healthy; `cscli console status` shows CAPI authenticated and enrolled.
2. `cscli metrics show acquisition` shows NPM, app and `syslog:192.168.213.254` sources with few or no unparsed lines.
3. `cscli metrics show parsers` shows `quark/unifi-syslog-host` and `crowdsecurity/iptables-logs` hits.
4. A public request to a tunnel hostname logs a public `[Client …]` address in NPM, not `172.18.0.1`.

To test a parser against a line without touching live config, copy `/etc/crowdsec` to
`/tmp` inside the container, point `config_dir` at the copy and run
`cscli -c /tmp/cs/config.yaml explain --type <type> --log '<line>' -v`. Use `--type unifi`
with the post-syslog form shown above for gateway lines.

## Remediation

Nothing enforces decisions. The only layer that can enforce against internet web clients
is Cloudflare, in front of the tunnel. If wanted, add the official
[Cloudflare Worker bouncer](https://docs.crowdsec.net/u/bouncers/cloudflare-workers): scope
`routes_to_protect` to the public hostnames, set `only_include_decisions_from: [crowdsec, cscli]`
to keep KV writes small, choose the route fail mode deliberately, and store its LAPI key and
Cloudflare token in Dockhand. The Plex WAN forward could be protected at the UniFi gateway,
but community UniFi bouncers are unverified on Network 10.

## Rollback

Revert the Git change and redeploy, or stop the stack through Dockhand; NPM is unaffected.
To undo the UniFi side, delete the custom policy and restore `rsyslogd` from the saved JSON.
Removing the real-IP block from an NPM proxy host only returns its logs to the gateway address.
