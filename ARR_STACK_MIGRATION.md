# Arr Stack — Migration & Configuration Reference

Snapshot of the running media/download stack so it can be rebuilt on a new
machine. Captured 2026-06-14 from the live containers.

Two compose stacks make up the "arr stack":

- `arr_vpn_stack/` — gluetun (VPN) + qbittorrent, prowlarr, radarr, sonarr,
  byparr, cleanuparr, seerr, optimisarr.
- `media_related_stack/` — plex (and was unmanic; only plex in the compose now).

> **Secrets are intentionally redacted below.** VPN keys live in
> `arr_vpn_stack/.env` (git-ignored) and app API keys live inside each app's
> `config.xml` (inside its named volume). Carry these across with the files,
> don't retype them.

---

## 1. Host environment / prerequisites

| Item | Value |
|------|-------|
| Host OS | Windows + Docker Desktop, WSL2 in **mirrored** networking mode (`.wslconfig`: `networkingMode=mirrored`, `firewall=false`) |
| Bind IP | `DOCKER_BIND_IP=192.168.213.101` — all ports publish to this explicit host IP, **not** localhost. Per-machine; set in each `.env`. Change to the new host's LAN IP. |
| Timezone | `Europe/London` |
| PUID/PGID | arr apps: `1000`/`1000`; plex: `568`/`568` |
| Data root | `/mnt/s` (a Windows drive mounted into WSL). Bound into containers as `/data`. |
| GPU | NVIDIA NVENC via WSL driver. optimisarr needs `/usr/lib/wsl/lib` bind-mounted (supplies `libnvidia-encode.so.1`) and `NVIDIA_DRIVER_CAPABILITIES=compute,video,utility`. |

### External Docker networks (must exist before `compose up`)

```bash
docker network create vpn_stack_brg   # currently subnet 172.19.0.0/16
docker network create general_brg     # currently subnet 172.18.0.0/16
```

### External named volumes (must exist; hold all app config/state)

```bash
for v in gluetun_config qbittorrent_config qbittorrent_logs prowlarr_config \
         radarr_config sonarr_config seerr_config cleanuparr_config optimisarr_config; do
  docker volume create "$v"
done
```

On the current host these live at `/var/lib/docker/volumes/<name>/_data`.
**To migrate state, copy each volume's `_data` directory** (stop containers
first) — that carries every quality profile, indexer, API key and history below.
A clean rebuild from this doc is possible but loses watch history/queues.

### Host data directory layout (`/mnt/s` → `/data`)

```
/mnt/s
├── media
│   ├── film            (radarr roots: /data/media/film/{adults,kids})
│   ├── tv              (sonarr roots: /data/media/tv/{adult,kids})
│   └── training
├── downloads
│   ├── torrents/complete    (qbittorrent default save)
│   ├── torrents/incomplete  (qbittorrent temp)
│   ├── complete
│   ├── incomplete
│   └── source               (torrent .torrent export dir)
└── transcode               (plex transcode)
```

`copyUsingHardlinks=true` in radarr/sonarr — downloads and media **must stay on
the same filesystem** (`/data`) so imports hardlink instead of copy. Same for
optimisarr `/work` and `/trash` (atomic moves).

---

## 2. Services, images & published ports

Only qbittorrent runs inside the VPN netns (`network_mode: service:gluetun`);
everything else sits on `vpn_stack_brg` directly. qbittorrent's WebUI/torrent
ports are therefore published *on the gluetun container*, not on qbittorrent.

| Service | Image | Host port (`192.168.213.101:`) | Notes |
|---------|-------|------|-------|
| gluetun | `qmcgaw/gluetun:latest` | 5041 tcp/udp, 8081 | NordVPN, WireGuard. Publishes qbit ports. |
| qbittorrent | `lscr.io/linuxserver/qbittorrent:latest` | (via gluetun: 8081 WebUI, 5041 torrent) | VueTorrent mod. `network_mode: service:gluetun` |
| prowlarr | `lscr.io/linuxserver/prowlarr:latest` | 9696 | indexer manager |
| radarr | `lscr.io/linuxserver/radarr:latest` | 7878 | movies |
| sonarr | `lscr.io/linuxserver/sonarr:latest` | 8989 | tv |
| byparr | `ghcr.io/thephaseless/byparr:latest` | (internal 8191) | FlareSolverr replacement; proxies via `http://gluetun:8888` |
| cleanuparr | `ghcr.io/cleanuparr/cleanuparr:latest` | 11011 | stalled/orphan cleanup |
| seerr | `ghcr.io/seerr-team/seerr:latest` | 5055 | requests (Overseerr fork) |
| optimisarr | `ghcr.io/jellman86/optimisarr:dev` | 8787 | transcode/optimise (own repo) |
| plex | `lscr.io/linuxserver/plex:latest` | host network (32400) | `/dev/dri` for HW transcode |

### gluetun / VPN (values in `.env`, secrets redacted)

```
VPN_SERVICE_PROVIDER = nordvpn
VPN_TYPE             = wireguard
WIREGUARD_PRIVATE_KEY = <REDACTED — arr_vpn_stack/.env WGPRIVKEY>
SERVER_COUNTRIES    = Netherlands,Switzerland,Sweden,Denmark,Germany,Belgium,France,Ireland,Norway,Spain
DNS over TLS via Cloudflare; HTTP proxy ON at :8888 (used by byparr)
FIREWALL_INPUT_PORTS    = 5041,8081,9696,7878,8989,8191
FIREWALL_OUTBOUND_SUBNETS = 192.168.211.0/24 … 192.168.215.0/24  (LAN access)
```

---

## 3. Indexers, download client & app links (Prowlarr)

Prowlarr full-syncs indexers to Radarr & Sonarr. Indexers themselves are
configured in the Prowlarr UI and stored in the `prowlarr_config` volume — they
carry across with that volume, so there's nothing to re-enter by hand. (Add/curate
your own indexer set on the new host as needed; none require API keys/credentials.)

**Applications (full sync):** Radarr `http://radarr:7878`, Sonarr
`http://sonarr:8989`, both pointing back at `http://prowlarr:9696`.

**Download client (shared):** qBittorrent at host `gluetun` port `8081`
(reachable as `gluetun` because qbit shares its netns).
- Radarr category: `radarr`
- Sonarr category: `tv-sonarr`
- Prowlarr default category: `prowlarr`

> App API keys (carry across in each `config.xml`): radarr/sonarr/prowlarr each
> have a 32-char key in `<volume>/config.xml`. Auth = Forms, disabled for local
> addresses.

---

## 4. qBittorrent settings

```
DefaultSavePath        = /data/downloads/torrents/complete
TempPath (incomplete)  = /data/downloads/torrents/incomplete   (enabled)
TorrentExportDirectory = /downloads/source
WebUI Address/Port     = * / 8081
Torrent port           = 5041
Encryption             = 1 (prefer)
QueueingSystemEnabled  = true (ignore slow torrents)
MaxActiveDownloads/Torrents/Uploads = 10 / 15 / 5
GlobalMaxRatio         = 1
GlobalMaxSeedingMinutes= 1440 (24h)
```

Categories: `radarr`, `tv-sonarr`, `prowlarr` (all default save path / share
limits). VueTorrent WebUI via `DOCKER_MODS`.

---

## 5. Media quality settings — Radarr (movies)

**Quality profiles** (custom format `HEVC/x265` scored **+100** in every profile
to prefer x265):

| # | Profile | Upgrades | Allowed qualities |
|---|---------|----------|-------------------|
| 6 | **Movies: 4K→1080p HEVC** (the active custom one) | yes, cutoff WEB 1080p | 720p/1080p/2160p HDTV+Bluray+WEB, Remux-1080p |
| 1 | Any | no | everything |
| 2 | SD | no | SD sources |
| 3 | HD-720p | no | 720p |
| 4 | HD-1080p | no | 1080p |
| 5 | Ultra-HD | no | 2160p |

**Custom format:** `HEVC/x265` — matches release titles containing x265/HEVC.

**Root folders:** `/data/media/film/adults`, `/data/media/film/kids`

**Naming:** rename on, `{Movie Title} ({Release Year}) {Quality Full}`, folder
`{Movie Title} ({Release Year})`, smart colon replacement.

**Media management:** hardlinks on, propers/repacks = preferAndUpgrade,
auto-unmonitor previously downloaded, min free space 100 MB, extra files `srt`,
mediainfo on, recycle bin cleanup 7 days.

**Quality definition size caps (MB/min):** 720p+ capped pref 35 / max 80;
SD pref 95 / max 100. (Tuned down to favour smaller HEVC releases.)

**Connections:** Plex Media Server (library update notification).

---

## 6. Media quality settings — Sonarr (TV)

**Quality profiles** (also `HEVC/x265` +100 everywhere):

| # | Profile | Upgrades | Allowed qualities |
|---|---------|----------|-------------------|
| 6 | **TV: 1080p/720p HEVC** (active custom one) | yes, cutoff WEB 1080p | 720p/1080p HDTV+Bluray+WEB |
| 1 | Any | no | up to 1080p |
| 2–5 | SD / HD-720p / HD-1080p / Ultra-HD | no | per name |

**Root folders:** `/data/media/tv/adult`, `/data/media/tv/kids`

**Naming:** rename on,
`{Series Title} - S{season:00}E{episode:00} - {Episode Title} {Quality Full}`,
season folders `Season {season}`, multi-episode style 5, episode title required.

**Media management:** hardlinks on, propers/repacks = preferAndUpgrade,
auto-unmonitor previously downloaded, extra files `srt`, mediainfo on.

**Quality definition size caps (MB/min):** SD ~min 2 / max 100; 720p min 3 /
max ~125–130; 1080p min 4 / max 130–155; 2160p min 35.

**Connections:** Plex Media Server.

---

## 7. optimisarr (transcode/optimisation) — own repo

Config DB: `optimisarr_config` volume → `/config/optimisarr.db` (SQLite).
See the `optimisarr/` repo. Reachable at `:8787`. Mounts `/data`, `/work`
(`/mnt/s/.optimisarr/work`), `/trash` (`/mnt/s/.optimisarr/trash`) — all on the
same fs as `/data` for atomic replacement.

**Global settings (live):**

```
maxConcurrentJobs = 1        encoderMode = Auto       cpuThreadLimit = 0 (all)
schedule = disabled (window 00:00–00:00)
minFreeDiskBytes = 10 GiB
replacementAllowCrossFilesystem = false   quarantineRetentionDays = 0
Verification quality gates:
  VMAF harmonic mean ≥ 93, VMAF min ≥ 80, quality gate ON
  require audio retained = true, require subtitles retained = false
  require size reduction = true
  audio loudness gate ON (max drift 1 LUFS), clipping gate ON (max true peak 0 dBTP)
  image SSIM ≥ 0.95, image quality + metadata gates ON
  duration tolerance 1%
```

**Libraries** (currently all `TEST_*`, profile `ConservativeHevc`, move-on-complete):

| Library | Type | Notable rules |
|---------|------|---------------|
| TEST_Films | Film | audio aac@128k, video-audio opus@160k, downmix→stereo; → `/data/media/testing/complete/film` |
| TEST_TV | Tv | maxHeight 2160, HDR `TonemapToSdr`; → `…/complete/tv` |
| TEST_Music | Music | audio aac; → `…/complete/muisic` *(note existing typo in target)* |
| TEST_Images | Photo | image library; → `…/complete/images` |

These are test libraries — recreate real Film/TV libraries pointing at
`/data/media/film` and `/data/media/tv` on the new host.

---

## 8. Plex (media_related_stack)

```
Image:    lscr.io/linuxserver/plex:latest    network_mode: host (port 32400)
PUID/PGID: 568/568
/config    -> ${CONFIG_PATH}/pms   (default /home/jellman86/docker/media_related_stack/pms)
/library   -> ${MEDIA_PATH}        (/mnt/s/media)
/transcode -> ${MEDIA_PATH}/transcode
/dev/dri               -> hardware (QSV/VAAPI) transcoding
PLEX_CLAIM -> get a fresh token from https://plex.tv/claim if re-claiming the server
```

> Plex config is a **bind mount**, not a named volume — copy
> `…/media_related_stack/pms` to keep libraries, metadata and the server identity.

---

## 9. Rebuild checklist (new machine)

1. Install Docker Desktop + WSL2 (mirrored networking, firewall off).
2. Set the new host LAN IP in both `.env` files (`DOCKER_BIND_IP`).
3. Mount the data drive at `/mnt/s` (or update `DATAPATH`/`MEDIA_PATH`).
4. Create the two external networks and the named volumes (§1).
5. **Restore state:** copy each volume's `_data` and the Plex `pms` bind dir from
   the old host. (Or rebuild config from §3–§8.)
6. Copy `arr_vpn_stack/.env` (VPN keys) and `media_related_stack/.env`.
7. Confirm NVIDIA GPU works in WSL (`nvidia-smi`) for optimisarr/Plex.
8. `cd arr_vpn_stack && docker compose up -d` (gluetun first — others depend on
   its healthcheck), then `cd ../media_related_stack && docker compose up -d`.
9. Verify gluetun has a tunnel + correct exit IP before trusting qbittorrent.
10. Re-point seerr/Plex at the new addresses if the IP changed.

### Boot-race caveat (see repo README / memory)

Docker Desktop restarts containers at boot before WSL networking is ready;
containers come up "healthy" but with no host port mapping, and gluetun can
exhaust retries. The repo's `scripts/start-stacks-on-boot.*` handles ordering,
waits for real internet, then runs a port-mapping remediation pass and brings
NPM up last. Reuse it on the new host.
