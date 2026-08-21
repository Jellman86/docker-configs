# ARR and VPN Stack

Git-backed Dockhand stack for the download and media-management services on Riker. The Compose project is named `arr_stack`.

## Services

| Service | Role | Published access |
|---|---|---|
| `gluetun` | VPN gateway, DNS resolver, and HTTP proxy | LAN-bound control API `8000`; qBittorrent TCP/UDP `5041`; Web UI `8081` |
| `qbittorrent` | Download client sharing Gluetun's network namespace | Through Gluetun only |
| `prowlarr` | Indexer manager | `9696` |
| `radarr` | Movie management | `7878` |
| `sonarr` | TV management | `8989` |
| `byparr` | Browser-backed indexer challenge helper | Riker port `8191` |
| `cleanuparr` | Queue and download cleanup | `11011` |
| `seerr` | Media request interface | `5055` |
| `gluetun-guard` | Restores the containers that lose their network when Gluetun's container goes away | None |

Port variables in `docker-compose.yml` can override most published defaults.

## Topology and networking

- Compose file: `arr_vpn_stack/docker-compose.yml`
- Intended host: Riker / TrueNAS.
- External network: `${NETWORK:-arr_stack_brg}`.
- Gluetun's unauthenticated control API is bound by default to Riker's LAN
  address at `http://192.168.213.101:8000`. Override
  `GLUETUN_CONTROL_BIND_ADDRESS` or `GLUETUN_CONTROL_PORT` only when the trusted
  management network changes; never bind it to a public interface.
- qBittorrent uses `network_mode: service:gluetun`; it has no independent network path or host ports.
- Byparr reaches the public web through Gluetun's HTTP proxy at `http://gluetun:8888` by default.
- Byparr publishes port 8191 on Riker so Quark-hosted applications can reuse
  the proven service without an NPM or public route.
- Prowlarr, Radarr, Sonarr, Cleanuparr, Seerr, and Gluetun communicate over `arr_stack_brg`.
- `gluetun-guard` holds no published ports and talks only to Dockhand's API on the trusted LAN.

## Recovering from a Gluetun restart

qBittorrent shares Gluetun's network namespace, and Docker destroys that
namespace whenever Gluetun's container stops. qBittorrent comes back with no
routes at all and stays that way until it is restarted; it cannot recover on its
own. Compose's `depends_on.restart` does not cover this, because the
specification limits it to restarts Compose itself performs and explicitly
excludes "automated restart by the container runtime after the container dies" —
so it fires on `docker compose restart gluetun` and not on a crash, a host
reboot, or a restart issued from Dockhand or Auspex.

Two behaviours were measured on Riker before this was written:

- Restarting the namespace owner in place leaves the dependent with an empty
  routing table. Restarting the dependent repairs it.
- Recreating the namespace owner gives it a new container ID, and the dependent
  can then no longer be restarted at all — Docker refuses with
  `joining network namespace of container: No such container` and leaves it
  exited. Only a force-recreate repairs that, and a plain `compose up -d` is a
  no-op because the dependent's own configuration has not changed.

Prowlarr and Byparr are affected differently. Both reach the public web through
Gluetun's HTTP proxy over the bridge rather than through its namespace, so their
networking never breaks, but they hold pooled connections and cached DNS for a
proxy that has gone. That matters most when Gluetun returns on a different
bridge address, which it can after a recreate. Restarting them drops the stale
state.

Restarting Prowlarr does **not** clear a disabled indexer. Escalation level and
`DisabledTill` live in the `IndexerStatus` table on disk; rows on Riker carry
`InitialFailure` dates from before the last container start and are still at
escalation 9, so that state survives any restart and has to be cleared in
Prowlarr itself.

Byparr is deliberately excluded from the repair list. A Cloudflare challenge
solve can occupy it for two minutes, and restarting it mid-solve returns a 408
to Prowlarr, which records an indexer failure and escalates — the repair would
manufacture the failure it is supposed to help with. Byparr also resolves
`gluetun` through Docker's DNS on every request, so it holds no stale address.
Set `GLUETUN_GUARD_PROXY_DEPENDENTS` if that judgement turns out to be wrong.

## DNS ad blocking and Byparr's cookie jar

`BLOCK_ADS` is on. Byparr reaches the web through Gluetun's HTTP proxy, so the
proxy resolves every hostname the browser asks for and Gluetun's filtering
applies to the pages Byparr renders.

It is on for a specific failure. Byparr returns the browser's whole cookie jar,
third-party ad cookies included, and Prowlarr loads that into
`System.Net.CookieContainer`. A cookie value holding an unquoted comma is
rejected, and Prowlarr's `InitializeRequestCookies` abandons the entire jar
rather than the one cookie — taking `cf_clearance` with it. Measured on Riker,
twice, identically:

```
|Debug|FlareSolverr|Cloudflare Detected, Applying FlareSolverr Proxy to https://kickass.ws/new/?field=time_add&sorder=desc
|Debug|HttpClient|Invalid cookie in https://kickass.ws/new/?field=time_add&sorder=desc
  System.Net.CookieException: The 'Value'='iqoption.com,iqtrading.asia' part of the cookie is invalid.
     at System.Net.CookieContainer.Add(Uri uri, Cookie cookie)
|Error|Cardigann|CloudFlareProtectionException: Unable to access kickass.ws, blocked by CloudFlare Protection
```

The solve had already succeeded — a direct Byparr call returns HTTP 200, the
real page, and a valid `cf_clearance`. The retry fails only because it carries
no clearance, and Prowlarr books that as an indexer failure. A hostname that
does not resolve sets no cookie, which is what `BLOCK_ADS` buys.

Treat it as partial cover, not a fix. Gluetun's list carries `mc.yandex.ru` but
not `mylink.cloud`, `s99i.org`, or the rotating `sh.*` host that kickass.ws also
loads, and the offending cookie appears only on some ad rotations. The durable
fix is upstream: Byparr should scope returned cookies to the target domain.

Do not reach for `DNS_BLOCK_IPS` to cover the rest. `mylink.cloud` and
`json.vpncheck.info` sit on shared Cloudflare addresses, so blocking those
resolves to blocking most of the indexers too.

None of the indexer or stack hostnames appear in Gluetun's ads or malicious
lists; that was checked against `qdm12/files` before enabling. `BLOCK_SURVEILLANCE`
is gone — current Gluetun logs `BLOCK_SURVEILLANCE is obsolete because its DNS
block lists are not longer maintained` on every start and ignores it.

A Cloudflare `error code: 1006` is a different thing entirely and no proxy fixes
it: the site has banned the exit IP. Byparr fetching 1337x through the VPN
returns `Access denied | 1337x.to used Cloudflare to restrict access`, while the
same URL from a residential IP returns an ordinary `Just a moment...` challenge.
Rotate the exit or drop the indexer.

## Why Gluetun's image is pinned to a release

`GLUETUN_IMAGE` is pinned to a specific release tag and anchored so the same
reference reaches qBittorrent's `com.jellman86.gluetun-image` label. That label
is load-bearing: it puts the image reference into qBittorrent's Compose config
hash, so changing the reference changes the hash and Compose recreates
qBittorrent in the same operation that recreates Gluetun. Since qBittorrent
shares Gluetun's namespace, that is what makes an image update atomic instead of
leaving a dead namespace behind. Measured with `docker compose config --hash`:
two different digests produce two different qBittorrent hashes.

A floating tag breaks this. `latest`, `v3` and `v3.41` are constant strings, so
the label never changes even when the underlying image does — Compose would
recreate Gluetun alone and leave qBittorrent broken until `gluetun-guard`
noticed. `latest` is also built from master rather than from a release, which is
not what should be enforcing a killswitch on an unattended overnight update.

Bump it by editing the tag, reviewing, and deploying through Dockhand. Do not
replace it with a floating tag without also removing the label and accepting
that recovery becomes reactive.

## Healthcheck timing

The checks are tuned to notice a broken container quickly without condemning a
slow start, so each service carries a short `interval` and a long
`start_period`:

| Service | Interval / retries | `start_period` | Why |
|---|---|---|---|
| `qbittorrent` | 30s / 2 | 90s | A dead namespace shows in about a minute, but it must wait for Gluetun and then load its torrent state before the WebUI answers |
| `byparr` | 1m / 3 | 60s | Answers `/health` roughly fifteen seconds after start on a warm image; a fresh pull needs longer |
| `gluetun-guard` | 1m / 3 | 60s | On a host reboot it can start before Dockhand does |

`gluetun-guard` watches Gluetun's container identity and start time through
Dockhand's read-only inspect endpoint and reacts to each case:

| Observed | Repair |
|---|---|
| Same container ID, newer `StartedAt` | Restart `qbittorrent`, then `prowlarr`, through Dockhand |
| New container ID | Recreate the stack through Dockhand (`restart?mode=recreate`, which runs `compose stop` then `up -d --force-recreate`) |

It waits for Gluetun to report healthy before repairing, so dependents are not
restarted into a killswitch, and it holds a cooldown afterwards so a flapping
tunnel cannot start a restart storm. It records Gluetun's current identity at
startup and takes no action on that first reading, which is what stops the
stack recreate — which replaces the guard too — from looping.

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
- `BYPARR_SHM_SIZE` (default `1gb`) — shared memory for Byparr's browser.
  Docker's 64MB default is too small for a browser and shows up as challenges
  that never finish rather than as a clear failure.
- `BLOCK_ADS` (default `on`) — Gluetun DNS ad filtering. Keep it on unless an
  indexer is shown to be on the block list; see the section above for why it
  matters to Byparr.

Secrets that belong in Dockhand's encrypted variables:

- `WGPRIVKEY` for WireGuard, or `OPENVPNUSER` and `OPENVPNPASSWORD` for OpenVPN

`gluetun-guard` settings, all optional and defaulted in Compose:

- `DOCKHAND_URL` (default `http://192.168.213.101:30328`), `DOCKHAND_ENV_ID`,
  and `DOCKHAND_TOKEN` — the token is only needed if Dockhand authentication is
  enabled; keep it in Dockhand's encrypted variables if it is set.
- `GLUETUN_GUARD_ANCHOR`, `GLUETUN_GUARD_NAMESPACE_DEPENDENTS`, and
  `GLUETUN_GUARD_PROXY_DEPENDENTS` — space-separated container names. Anything
  moved onto `network_mode: service:gluetun` must be added to the namespace
  list, and anything pointed at Gluetun's proxy to the proxy list.
- `GLUETUN_GUARD_POLL_SECONDS`, `GLUETUN_GUARD_READY_TIMEOUT_SECONDS`,
  `GLUETUN_GUARD_COOLDOWN_SECONDS`, `GLUETUN_GUARD_STACK`.

VPN selection and policy variables include `VPNHOST`, `VPNPROTOCOL`, `VPNCOUNTRY`,
`GLUETUN_CONTROL_BIND_ADDRESS`, `GLUETUN_CONTROL_PORT`, `FIREWALL_INPUT_PORTS`,
and `FIREWALL_OUTBOUND_SUBNETS`. If Dockhand overrides `FIREWALL_INPUT_PORTS`,
that value must include `8000` for the control API. Never commit a populated
`.env` file.

## Deployment and updates

This stack is managed through its Git-backed Dockhand entry. Follow the repository-level deployment procedure in the [root README](../README.md): validate the Compose source, push the reviewed change, then deploy through Dockhand. Do not run lifecycle-changing `docker compose up`, `pull`, or `down` commands directly on Riker.

After deployment, verify:

1. Gluetun is healthy and reports the intended VPN exit before trusting qBittorrent.
2. qBittorrent is healthy and still shares Gluetun's network namespace.
3. Radarr, Sonarr, Prowlarr, Cleanuparr, and Seerr are healthy and retain their state.
4. Byparr is reachable from Quark at `http://192.168.213.101:8191` and uses
   Gluetun's proxy.
5. Gluetun's control API responds from the trusted LAN at
   `http://192.168.213.101:8000/v1/version` and is unreachable from untrusted
   networks.
6. The `/data` mount points at the expected storage tree.
7. `gluetun-guard` is healthy and its log reports `watching gluetun id=...`. An
   unhealthy guard means it cannot reach Dockhand, and the recovery above is not
   in place.

## Rollback

Revert the relevant Git commit or restore a previously reviewed image reference, push `main`, and redeploy through Dockhand. Application databases and configuration live outside the container images; restore those bind-mounted directories from backup only when state is damaged, and stop/recreate services through Dockhand before filesystem restoration.

## Security notes

- VPN credentials are secrets; do not place them in Git, logs, or documentation.
- Gluetun is deliberately privileged only with the network capability and TUN device needed for VPN routing.
- Gluetun's control API is intentionally unauthenticated for Auspex on the
  trusted `192.168.213.0/24` management network. It can stop the VPN, DNS, or
  updater, so port `8000` must never be forwarded by the router, published by a
  reverse proxy, or bound to a public interface.
- Do not expose Gluetun's proxy beyond trusted container/LAN boundaries.
- Byparr accepts arbitrary destination URLs and proxy overrides. Keep port 8191
  on the trusted LAN only; callers must use typed, allowlisted source adapters
  and must not forward user-controlled URLs or `X-Proxy-*` headers.
- qBittorrent must not be changed to a separate network without an explicit leak-prevention review.
- `gluetun-guard` deliberately has no access to the Docker socket. Every action
  it takes is a Dockhand API call, so container lifecycle stays owned by
  Dockhand and the guard cannot be used to escalate to the host. The widely
  used alternatives — `autoheal` and `deunhealth` — were rejected for this
  reason and because both only issue a plain restart, which cannot repair a
  dependent whose namespace owner was recreated.
- The detailed migration and application reference is in [`ARR_STACK_MIGRATION.md`](../ARR_STACK_MIGRATION.md).
