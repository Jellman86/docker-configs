# autoFPL

Git-backed Dockhand stack for the private autoFPL API on Quark (`dell-compute`).

## Service

- `autofpl` runs the verified image published from autoFPL `dev` merge commit `41affc4d5d5e0fd5031c3a52082cc2c282ffc91f`.
- Compose pins the immutable manifest digest `sha256:7cc4b0cc5a25cf1f7b03f76c15e63fe007a2924fced02b5c8995fac656be4d72`.
- The application listens on container port `8080` and serves the responsive Gameweek decision room at `/`. When a qualifying official capture exists, the advice route returns an explicitly unvalidated Baseline v0 squad, XI, bench and captaincy with official portraits, cutoff-aware player dossiers, wide intervals and transparent market/fixture evidence. Schema 13 persists one immutable forecast artifact and content hash per official capture; schema 14 retains the official provider's optional next-Gameweek expected-points value as a separately labelled, not-promoted dossier challenger. Schema 15 adds immutable, forecast-linked selection revisions with an explicit one-time user lock and deadline-derived draft, locked, expired and frozen states. Schemas 16–19 add bounded third-party research-source observations, a verified 2025/26 historical FPL archive, cutoff-safe cross-season player state, and a read-only identical-fold cross-season feature ablation. Users can edit XI/bench membership, bench priority and captaincy against the same forecast squad; valid changes create a new unlocked superseding revision and never rewrite or submit the prior choice. Refreshing prediction only reloads Baseline v0 and does not start collection or change a user's saved selection.
- The API publishes OpenAPI 3.1 at `/openapi/v1.json`, exposes private decision-snapshot write/read routes, and serves read-only provenance, replay and deterministic FPL Form player/fixture identity-coverage views.
- One SQLite file under `/data` is authoritative for squad, immutable selection revisions and locks, observation, immutable snapshot state, official FPL captures, Baseline v0 forecast artifacts, public forecast captures, research observations, the verified historical archive and collection checks. Startup applies nineteen explicit migrations with foreign keys, WAL and a bounded busy timeout. Official final outcomes retain bounded xG/xA/xGC, ICT/BPS and defensive evidence; legacy rows remain null.
- FPL Form collection reuses Quark's existing Playwright MCP service. One fixed code operation fetches the canonical provider page through Playwright's request context without rendering or executing the roughly 105 MB document. It short-circuits the off-season sentinel and, for an active Gameweek, scans one encoded player object at a time rather than constructing the complete decoded history. The bounded MCP client accepts either direct JSON or SSE Streamable HTTP responses and selects the matching JSON-RPC result. The browser returns compact, versioned evidence to autoFPL with transport, extraction-version and full provider-payload hash provenance. The application does not run a second browser stack or download the page into the API process.
- The instance checks FPL Form at most every six hours. Its persisted last-check time survives restarts, so a deployment waits the remaining interval rather than creating an extra provider request.
- The instance also checks the fixed official bootstrap/fixture pair every six hours and persists the attempt time independently of immutable content deduplication.
- The read-only FPL Form evaluator reuses the same authoritative identity resolution, pairs only deadline-eligible captures with later final outcomes, and emits deterministic exploratory metrics for published conditional points and a separately labelled appearance-adjusted challenger.
- The read-only official expected-points evaluator scores retained `ep_next` values unchanged against later final outcomes, requires complete capture/player chronology, keeps zero-minute players in the population, and emits deterministic overall, position and zero-minute metrics without promoting the source.
- The player dossier exposes retained official underlying evidence, while the analytics boundary produces cutoff-safe temporal summaries and identical-fold, unpromoted underlying-feature and cross-season ablations. The prior-season archive preserves the latest pre-cutoff player performance and availability state while excluding archived source expected-points and final-health leakage.
- An explicit deterministic FFScout adapter reads one retained pre-deadline snapshot, resolves predicted-XI entries through their embedded official Premier League photo code and the snapshot's exact official identity capture, and writes only idempotent quarantined categorical start claims. Unmatched codes are reported and no extracted claim influences a forecast or selection.

## Network exposure

The service joins the existing external `general_brg` network with alias `autofpl-api` and the existing internal `hermes_agent_research_private` network. The research network lets autoFPL call Quark's bounded `spider-mcp` research collector without deploying another browser or scraper. It declares container port `8080` for internal discovery but publishes no host port. The separately managed private-LAN DNS and Nginx Proxy Manager route exposes `https://autofpl.pownet.uk` to trusted clients and proxies to `autofpl-api:8080`; this Compose stack does not create or modify that ingress. There is no public or tunnel route.

Internal callers on `general_brg` can use:

```text
http://autofpl-api:8080
```

## Hardening

The container runs explicitly as UID/GID `1654`, uses a read-only root filesystem, has only a bounded `/tmp` tmpfs, drops all Linux capabilities, enables `no-new-privileges`, and bounds PIDs, CPU, memory, shutdown time, and JSON logs. The only writable mount is the private SQLite directory at `/data`. The health check uses the image's built-in fail-closed probe.

The 256 MiB limit covers the API and its bounded MCP response handling. The large dynamic-page parse runs in the separately managed Playwright service, so the operator importer no longer needs the temporary 768 MiB application allowance.

## Persistent data

The bind source is `/mnt/apps/docker/autofpl/data`. Compose sets `create_host_path: false` so a missing path fails rather than being silently created as root. Provision it once as the Quark deployment user before the first stateful deployment:

```bash
install -d -m 0750 /mnt/apps/docker/autofpl/data
setfacl -m u:1654:rwx /mnt/apps/docker/autofpl/data
setfacl -d -m u:1654:rwx,u:1000:rwx,m::rwx /mnt/apps/docker/autofpl/data
```

Verify with `getfacl /mnt/apps/docker/autofpl/data`. The directory owner remains the deployment user; UID `1654` receives only the filesystem access needed by the non-root container. Database files, WAL files and backups stay outside Git.

Create a consistent backup from the application image's SQLite online-backup command, using a new filename under `/data/backups`, and verify the backup with the integrity command before a schema-changing deployment or rollback. Do not copy the live database/WAL pair directly.

Before this migration, the live schema-3 database was backed up to `/data/backups/autofpl-before-be32299-20260725T2205Z.db` and the backup returned `ok` from the prior image's integrity command.

Before the schema-8 Playwright collector deployment, the live database was backed up to `/data/backups/autofpl-before-f2c0270-20260726T0922Z.db`; the SQLite integrity check returned `ok`.

Before the schema-9 canonical-source hotfix, the live database was backed up to `/data/backups/autofpl-before-2bec8d0-20260726T0941Z.db`; the SQLite integrity check returned `ok`.

Before this schema-10 deployment, the live database was backed up online to `/data/backups/autofpl-before-d091825-20260726T1216Z.db`; both the live database and backup returned `ok`, and the backup SHA-256 is `1504ba13387aebeb79c158814fc0402b226b63556a0af8d48034aef075a81fee`.

Before the schema-13 forecast-artifact deployment, the live database was backed up online to `/data/backups/autofpl-before-60ae796-20260726T1434Z.db`; both the live database and backup returned `ok`, and the backup SHA-256 is `968e3112afec48555ab4cee062bebaf699eb105d8f4043bedaccad792ea095e9`.

Before the schema-14 official expected-points challenger deployment, the live database was backed up online to `/data/backups/autofpl-before-e21fc26-20260726T1500Z.db`; both the live database and backup returned `ok`, and the backup SHA-256 is `3e89de48378db065ac6f54e83927d964c0117eef038cd51b0c0905a9527d835f`.

Before the schema-15 selection-lifecycle deployment, the live database was backed up online to `/data/backups/autofpl-before-da3bb1e-20260726T1559Z.db`; both the live database and backup returned `ok`, and the backup SHA-256 is `8a06c42d13f5aa733b71aa49aa6173a33c819f990bcf24fe81450c0e4bd2ffea`.

Before the schema-19 historical-data and research-evidence deployment, the live database was backed up online to `/data/backups/autofpl-before-54152f0-20260726T1813Z.db`; both the live database and backup returned `ok`, the backup is 7,925,760 bytes, and its SHA-256 is `dd95949eb7993ec9416d8a52e4f6334d5b59e2d56b08dd549da2dd0980d9c235`.

## Dockhand deployment

Create a Git-backed Dockhand stack with:

- repository: `https://github.com/Jellman86/docker-configs.git`
- branch: `main`
- Compose path: `autofpl/docker-compose.yml`
- environment: Quark / environment ID `1`
- stack name: `autofpl`
- repull images: enabled
- force redeploy: enabled
- build on deploy: disabled

No stack variables or secrets are required for this slice. Follow the repository-level Git/Dockhand procedure in the [root README](../README.md). Do not run a parallel `docker compose up`.

## Verification

Before commit or deployment:

```bash
python3 -m unittest discover -s autofpl/tests -v
docker compose -f autofpl/docker-compose.yml config --quiet
```

After Dockhand deployment, verify:

1. Dockhand synchronized the intended `docker-configs/main` commit.
2. `autofpl` is running and healthy with the pinned manifest digest.
3. No host port is published.
4. UID/GID, read-only root, capability and network settings match Compose.
5. `/`, `/api/v1/advice/demo`, the selected-player dossier route, `/openapi/v1.json`, `/healthz`, `/readyz`, decision-snapshot create/read/restart behavior, the deterministic endpoints, and representative malformed/domain-invalid 400/422 handling work from a trusted internal client.
6. When a qualifying official replay exists, advice reports `official-market-baseline-v0`, returns a legal official 15-player squad with 11 starters, one captain and one vice-captain, links every player to a cutoff-aware dossier and labels the prediction as unvalidated.
7. `/data/autofpl.db` is owned by UID `1654`, WAL mode is active, and the built-in integrity command returns `ok`.
8. Before the first operator import, `/api/v1/data/official-fpl/latest` returns 404. After `--import-official-fpl`, it reports the fixed URLs, null publication time, equal retrieval/availability time, hashes and non-zero source counts without returning raw provider JSON.
9. `--import-fpl-form-forecast` uses `playwright-mcp:8931`, fails cleanly without a partial capture when the provider has no active next-Gameweek forecast, and records `playwright-mcp`, extraction version and provider payload hash provenance when an active forecast is available.
10. The capture-specific FPL Form identity route returns 404 for an unknown capture and fails closed on unavailable, ambiguous or post-deadline evidence. `--evaluate-fpl-form-forecast` and `--evaluate-official-fpl-expected-points` return exit `2` with deterministic `insufficient-data` reports until their complete forecast/outcome pairs exist.
11. `/api/v1/selections/current` returns 404 before a user creates a draft. The UI offers explicit forecast-to-draft, edit and confirmation-gated lock actions only for persisted pre-deadline forecasts; synthetic previews remain read-only. Edits reject infeasible formations and create immutable superseding drafts, including after an earlier revision was locked. Neither editing nor locking writes to an FPL account.

## Rollback

Create and verify a consistent backup before changing the image or schema. Roll back by reverting the Compose digest through Git and Dockhand only when the older image supports the current schema. Otherwise restore the matching verified backup as a separately reviewed operation; never overwrite the live database while the application is running.
