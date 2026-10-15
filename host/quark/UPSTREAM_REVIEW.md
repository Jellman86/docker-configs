# Quark configuration contracts

Reviewed 15 October 2026 against upstream documentation and the live Dockhand
inventory. Ten Git stacks are deployed. All 30 long-running containers were
running and configured health checks passed. Maintenance/bootstrap containers
can exit successfully; that is not an application outage. Optional repository
stacks were reviewed/rendered, not silently deployed.

## Stack contracts and intentional differences

| Stack | Upstream contract and local choice |
| --- | --- |
| `management` | [Dockhand](https://dockhand.pro/manual/) uses `/app/data`, PUID/PGID and the Docker socket. Socket access controls the host. Its state is backed up; generated files/database are not hand-edited. |
| `web_services` | [NPM](https://nginxproxymanager.com/setup/) persists `/data` and certificates, listens on 80/81/443. [Cloudflared](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/) uses a remotely managed tunnel token and loopback metrics readiness. Tailscale is native, not a Compose service. |
| `arr_stack` | [LinuxServer qBittorrent](https://docs.linuxserver.io/images/docker-qbittorrent/) needs matching WEBUI_PORT and shared data paths. qBittorrent alone shares [Gluetun's namespace](https://github.com/qdm12/gluetun-wiki/blob/main/setup/connect-a-container-to-gluetun.md). Other Arr apps use internal service URLs and a common `/data` mount. [Seerr](https://docs.seerr.dev/getting-started/docker) uses native `user:` and `init: true`; [Cleanuparr](https://cleanuparr.github.io/docs/installation/detailed/) accepts PUID/PGID. |
| `media_stack` | [Plex](https://docs.linuxserver.io/images/docker-plex/) and [Jellyfin](https://docs.linuxserver.io/images/docker-jellyfin/) use host networking for discovery, persistent identity and `/dev/dri`. LSIO entrypoints manage device groups; Optimisarr receives render GID 105 explicitly. Jellyfin's source library is read-only. Plex scratch is on the SSD. |
| `immich`, `immich_ml` | [Immich](https://docs.immich.app/install/docker-compose/) server/ML versions match, OpenVINO is image-specific, database/cache stay private and PostgreSQL stays on local SSD. PG18 uses `/var/lib/postgresql`, logical recovery and preserved database properties. The retained ML LAN endpoint is deliberate; see the stack README. |
| `security_inference_stack` | [Frigate](https://docs.frigate.video/frigate/installation/) uses sized shared memory, cache tmpfs, iGPU/NPU and retained media. [BirdNET-Go](https://github.com/tphakala/birdnet-go/wiki/installation) uses BIRDNET_UID/GID, not generic PUID. [Mosquitto](https://github.com/eclipse-mosquitto/mosquitto/blob/master/docker/generic/README.md) persists authenticated config/data; host MQTT is loopback-only. [Home Assistant](https://www.home-assistant.io/installation/linux#install-home-assistant-container) deliberately uses host networking, D-Bus and privilege. YA-WAMF remains rolling `dev-intel` by user instruction. |
| `ai_tools` | [Playwright MCP](https://github.com/microsoft/playwright-mcp) has an explicit host allowlist, isolated browser state and bounded tmpfs. [Ollama](https://docs.ollama.com/docker) embeddings intentionally use CPU. [OpenViking](https://docs.openviking.ai/en/configuration/01-server) uses its selected config file and private authenticated backend. Hermes runs with its upstream bootstrap and authenticated dashboard. No MCP action or external message was sent as an audit test. |
| `optimisarr_sidecar` | Persistent pairing/config volume, bounded concurrency, scratch tmpfs and Intel device exposure. The config volume is explicitly included in nightly app recovery; engine images/other volume caches are not. |
| `stirling_pdf` | [Stirling security](https://docs.stirlingpdf.com/Configuration/Security/System%20and%20Security/) supports explicit login policy. This trusted-LAN instance has login disabled and no host port. `/tmp` is ephemeral; neither tmpfs nor analytics settings guarantee all user files are deleted. |
| `monitoring_management` (optional) | [Prometheus](https://prometheus.io/docs/prometheus/latest/storage/) uses local TSDB, time/size retention with room for WAL/compaction. [Grafana](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/) persists state and requires an explicit initial admin password. Defaults 9091/3002 avoid Cockpit/Dockhand. Not deployed. |
| `autofpl` (optional) | Own application image contract and policy tests: unprivileged/read-only API, networkless analytics, local state, private ingress and Quark Byparr endpoint. Not deployed in the reviewed Dockhand inventory. |
| Acceptance/maintenance templates | NVIDIA acceptance belongs on Picard, never Quark. PostgreSQL restore rehearsal and temporary Dockhand maintenance are on-demand only; do not deploy them over live production paths. |

## Consistent Quark conventions

- Deploy only through Git, passing CI and Dockhand. Comments/source-only changes
  do not require image pulls or forced recreation of healthy applications.
- Use the four guarded server variants for media, Arr, Immich and Stirling.
  `restart: "no"` is deliberate: the native storage guard verifies both UUIDs
  and mirror serials before starting/recovering them through Dockhand. SSD-only
  infrastructure uses `unless-stopped` and engine mount dependencies.
- Migrated state uses `/mnt/services/docker`, UID/GID 568. Existing Quark state
  uses `/mnt/apps` compatibility aliases to `/mnt/services/quark`, UID/GID 1000.
  Different identities preserve ownership; do not recursively chown the estate
  to make the numbers look uniform. Native-image `user:` and LSIO PUID/PGID are
  different contracts.
- Docker bridges are host-local. `general_brg` and `npm_proxy_backends` provide
  proxy access; database/cache networks remain separate. Host-network services
  need host-IP proxy backends, not Docker service DNS.
- `AllowedHosts` is persisted in the Arr apps; qBittorrent has an explicit domain
  list and CSRF enabled. Valid routes and internal client tests passed, while
  unknown/Riker hosts were rejected. These are app settings, not Compose secrets.
- Bound Docker stdout/stderr logs separately from application file logs. Do not
  impose uniform health commands on images lacking curl/wget or on one-shot jobs.
- Keep the current device permissions/provider choices unless a tested need
  justifies changing them. Render group is 105. Passing a device does not alone
  select QSV/OpenVINO inside an application's saved configuration.
- Preserve native Tailscale identity/auto-update, forwarding, SMB permissions,
  UUID mount dependencies, bounded online recovery and monthly Btrfs scrubs.
  Do not reboot, unmount sources, restart the storage guard or disturb the active
  full USB copy simply to audit consistency.

## Validation and limits

CI renders every Compose file with synthetic values and checks bounded logging
and one-shot behavior. Stack-specific checks validate GPU mappings, storage paths,
Arr VPN dependencies, database safety and application policies. Optional services
are not claimed to have passed live application acceptance.

The live review checked Git paths, container mounts/networks/devices/restart/log
policies, health, canonical proxy origins, Arr connections, storage guards and
backup coverage. It is not an exhaustive proof of every feature or external
account. Existing signed-in public/WAN Plex checks and independent VM backup
remain separate. EZTV currently fails its indexer test.

Current homelab tradeoffs: Dockhand login is disabled on trusted ingress; Frigate's
private NPM route uses internal unauthenticated port 5000; Stirling is LAN-only
without login. Changing identities/passwords or access policy needs a considered
rollout, not a blanket replacement during a storage copy. Fedora SELinux is
Enforcing, but Docker currently does not enable SELinux container labelling;
claiming container SELinux confinement would be wrong. Enabling it requires
reviewed volume labels and lifecycle testing. These limits are recorded, not
silently marked fixed or treated as grounds for production-scale machinery.

## Applied review results

The reviewed candidate and prior repository models were rendered with each of
the ten active stacks' existing non-secret Dockhand overrides and identical
synthetic secret placeholders. All ten effective models were equal. Therefore
this source/default/comment correction needs a Git sync, not a forced pull or
restart of healthy services. Optional monitoring changes are not deployed.

Nightly recovery now also includes the sidecar's small config volume, Cockpit
origins, monthly scrub/health units and external-backup script/settings. Existing
three-archive / 4 GiB-generation / 20 GiB-working limits remain unchanged. The
current external copy continues and will take a fresh recovery archive at its end.

Fourteen failed historical migration transient units were recorded privately and
had their failed state cleared only after confirming they were inactive. No job
was rerun and no application/backup service was stopped.
