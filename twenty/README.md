# Twenty research workbench (Quark)

Application: [Jellman86/twenty](https://github.com/Jellman86/twenty), `dev` branch. Roadmap: [Twenty project](https://github.com/users/Jellman86/projects/1).

ASP.NET Core/Svelte research workbench with a single-operator sign-in, a paper ledger, an optional Trading 212 connection and a local free-data collector. State lives in the private `twenty_data` volume (`/data`): research runs, ledgers, the operator account and session keys, and raw data captures. It runs as UID 1654, read-only, with 512 MiB/1 CPU and rotated logs. There is no published host port; NPM reaches `twenty-api:8080` on the existing `general_brg`.

Deploy as a Git-backed Dockhand stack named `twenty`, repository `docker-configs`, branch `main`, Compose path `twenty/docker-compose.yml`, environment Quark. Enable repull images and force recreation. Verify application CI (including full-history secret scan and image smoke), image publication and Compose CI before syncing and deploying through Dockhand's API. No Docker CLI lifecycle operations.

Private ingress: UniFi `twenty.pownet.uk` → Quark; NPM HTTPS → `http://twenty-api:8080`, using the existing wildcard certificate and LAN/Tailscale-only allow rules. No public tunnel or public DNS entry. Verify `/health/ready`, `/api/meta`, `/api/roadmap`, and a POST to `/api/projections` after deployment. The app requires sign-in for everything except health checks; keep the private ingress restrictions anyway.

Stack variables (Dockhand, stack `twenty`, environment Quark; mark the credentials as secrets):

| Variable | Value |
|---|---|
| `TWENTY_T212_ENVIRONMENT` | `live` or `demo`; leave unset for no broker |
| `TWENTY_T212_KEY`, `TWENTY_T212_SECRET` | Trading 212 API key and secret (secret) |
| `TWENTY_AUTH` | `on` (default) or `off`; `off` is refused with a live broker key |
| `TWENTY_COLLECTOR_ROLE` | defaults to `local`; `off` disables collection |
| `TWENTY_INGEST_TOKEN` | only when a remote collector ships here (secret, 32+ characters) |

Check a broker credential without signing in: `docker exec twenty dotnet Twenty.Api.dll --broker-check` (read-only, prints a masked account). First sign-in needs the one-time setup code from the container log.

Rollback by reverting the app/Compose Git change, awaiting CI/image publication, then Dockhand sync/deploy. Secrets belong in Dockhand's encrypted store, never in this repository.
