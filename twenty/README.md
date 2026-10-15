# Twenty research workbench (Quark)

Application: [Jellman86/twenty](https://github.com/Jellman86/twenty), `dev` branch. Roadmap: [Twenty project](https://github.com/users/Jellman86/projects/1).

This is a stateless ASP.NET Core/Svelte research dashboard. It has no broker credentials, live execution or training worker. No persistent volume is needed for this first slice. It runs as UID 1654, read-only, with 512 MiB/1 CPU and rotated logs. There is no published host port; NPM reaches `twenty-api:8080` on the existing `general_brg`.

Deploy as a Git-backed Dockhand stack named `twenty`, repository `docker-configs`, branch `main`, Compose path `twenty/docker-compose.yml`, environment Quark. Enable repull images and force recreation. Verify application CI (including full-history secret scan and image smoke), image publication and Compose CI before syncing and deploying through Dockhand's API. No Docker CLI lifecycle operations.

Private ingress: UniFi `twenty.pownet.uk` → Quark; NPM HTTPS → `http://twenty-api:8080`, using the existing wildcard certificate and LAN/Tailscale-only allow rules. No public tunnel or public DNS entry. Verify `/health/ready`, `/api/meta`, `/api/roadmap`, and a POST to `/api/projections` after deployment. The app itself has no authentication; preserve private ingress restrictions.

Rollback by reverting the app/Compose Git change, awaiting CI/image publication, then Dockhand sync/deploy. Secrets belong in Dockhand's encrypted store; none are required for this slice.
