# Stirling PDF

Self-hosted PDF toolkit for merging, splitting, converting, compressing, signing
and OCR. Runs on Riker because the work it does is document handling next to
storage, and it needs no GPU or NPU time on the compute host.

## Services

| Service | Role | Network exposure |
|---|---|---|
| `stirling-pdf` | PDF manipulation and OCR web application | `general_brg` only; no host port |

## Topology

Riker (`riker.pownet.uk`, TrueNAS) runs the stack. The container joins the
existing external `general_brg` bridge with alias `stirling-pdf`, which is the
same network Riker's Nginx Proxy Manager sits on, so NPM can reach it by name
without a published host port.

Compose path for the Dockhand Git stack:

```text
stirling_pdf/docker-compose.yml
```

## Private application access

The stack publishes no host port and creates no ingress of its own. Expose it by
adding a proxy host in Riker's Nginx Proxy Manager pointing at:

```text
http://stirling-pdf:8080
```

Then add the matching private-LAN DNS record. There is no public or tunnel
route, and none should be added: uploaded documents are processed in the
container and the application has no authentication enabled.

## Persistent storage

Three bind mounts under `${DOCKERCONFIGPATH:-/mnt/apps/docker}/stirling-pdf`:

| Path | Contents |
|---|---|
| `trainingData` | Tesseract OCR language data |
| `configs` | Per-installation application settings |
| `customFiles` | Custom templates and static overrides |

Working copies during conversion go to a 1 GB `tmpfs` at `/tmp`, so scratch
churn stays off the pool and is cleared on every restart. Nothing a user
uploads is retained after processing.

## Environment

All values have defaults; none are secret, so no Dockhand secret variables are
required for this stack.

| Variable | Default | Purpose |
|---|---|---|
| `PUID` / `PGID` | `568` | TrueNAS apps user, matching the other Riker stacks |
| `TZ` | `Europe/London` | Container timezone |
| `DOCKERCONFIGPATH` | `/mnt/apps/docker` | Persistent config root on Riker |
| `NETWORK` | `general_brg` | External bridge shared with Nginx Proxy Manager |
| `STIRLING_LANGS` | `en_GB` | OCR language packs to install |
| `STIRLING_LOCALE` | `en-GB` | Application default locale |
| `STIRLING_MEMORY_LIMIT` | `2g` | Memory bound; OCR is the heaviest operation |
| `STIRLING_CPUS` | `2.0` | CPU bound |

## Deployment and updates

Deploy only through Riker's Dockhand after the Compose change has reached
`main`. Riker runs Dockhand `1.0.37`; confirm the live version before any
mutation and follow
[`dockhand-git-deployments.md`](../../.agents/nevercommit/dockhand-git-deployments.md).

The image tracks `latest`. The Git stack has `repullImages` enabled, so a
Dockhand deploy pulls the current image and recreates the container.

## Rollback

Revert the relevant Git commit or pin a known-good image digest, push `main`,
then repeat the Dockhand sync and deploy. The bind mounts are not rolled back
with the image; restore them from a verified backup only after stopping the
service through Dockhand.

## Security and operational notes

- The container runs with `no-new-privileges` and publishes no host port.
- Authentication is not enabled, so the only access boundary is the private LAN
  and Nginx Proxy Manager. Do not route this through Cloudflare Tunnel.
- Analytics reporting is disabled explicitly.
- Memory and CPU are bounded because OCR and large-document conversion can
  otherwise consume the host.
- Docker CLI may be used for read-only diagnosis only; all lifecycle changes go
  through Dockhand.
