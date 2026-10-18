# Web Services Stack

Deployment entrypoint: [`compose.yaml`](compose.yaml). See the [deployment map](../../docs/compose-layout.md) and [cutover sequence](../../docs/cutover-plan.md) before changing a live project.

Git-backed Dockhand stack for ingress and Cloudflare Tunnel. Tailscale runs natively on Quark. This directory contains complete host-specific Compose manifests rather than an override chain.

## Compose manifest

Deploy `compose.yaml` as Dockhand stack `ingress` on Quark. It joins
`general_brg` and `npm_proxy_backends`. Retired Riker manifests have been
removed; Git history retains them. This is a complete manifest, not an overlay.

## Services

| Service | Role | Published access |
|---|---|---|
| `npm` | Nginx Proxy Manager reverse proxy and certificate management | `80`, `81`, `443` |
| `cloudflared` | Outbound Cloudflare Tunnel connector | No host port |

## Networking

The stack attaches services to the external `general_brg` network.

- Quark attaches NPM to `npm_proxy_backends`, which is the explicit network for private proxy targets such as OpenViking.
- NPM has the `nginx-rp` alias on `general_brg`.

Create the selected manifest's external networks before first deployment.

## Persistent storage

| Host path | Purpose |
|---|---|
| `${DOCKERCONFIGPATH}/nginx-proxy-manager/data` | NPM database and configuration |
| `${DOCKERCONFIGPATH}/nginx-proxy-manager/letsencrypt` | Certificates and ACME state |

These directories contain security-sensitive state. Back them up with restrictive permissions and do not copy them into Git.

## Environment

Common settings:

- `PUID`, `PGID`, `TZ`, `DOCKERCONFIGPATH`

Secrets:

- `TUNNEL_TOKEN`

Store the tunnel token in Dockhand. Native Tailscale keeps its node identity privately in `/var/lib/tailscale`, independent of Docker and the apps SSD.

## Deployment and updates

Use `stacks/ingress/compose.yaml` in Dockhand and follow the [root deployment procedure](../../README.md).

After deployment, verify:

1. NPM's health check succeeds and ports 80/81/443 are bound only on the intended host.
2. Existing NPM proxy hosts, certificates, and access lists remain present.
3. Cloudflared reports ready and the expected tunnel routes resolve without redirect loops.
4. Tailscale is connected, advertises only the approved routes/exit-node capability, and preserves its identity.
5. NPM can resolve each intended backend over the selected host-specific networks.

When Cloudflare Tunnel targets NPM, avoid redirect loops:

- If NPM forces HTTPS, target `https://nginx-rp:443` and configure the tunnel's origin TLS policy appropriately.
- If the tunnel targets `http://nginx-rp:80`, let Cloudflare handle edge HTTPS and do not force a conflicting NPM redirect.

## Rollback

Revert the relevant Git or image change, push, and redeploy the same host-specific manifest through Dockhand. Preserve NPM bind-mounted state. Native Tailscale is managed separately from this stack. An ingress rollback can affect all hosted services, so verify local/LAN recovery access before updating and avoid changing DNS, tunnel routing, certificates, and container images in one release.

## Security notes

- NPM and Cloudflare/Tailscale credentials are administrative secrets.
- Keep NPM's admin UI on trusted networks or behind a separate access control.
- Review every proxy host and Cloudflare route for intended public versus LAN-only exposure.
- Tailscale is a privileged network boundary; advertise only explicitly approved routes.
- Never publish private backend MCP/CDP ports merely to make them easier to proxy.

## Why NPM's access-log format is not overridden (2026-09-08)

NPM's shipped `proxy` and `standard` formats log `"$request_uri"`, so any credential an
application carries in a query string lands in `/data/logs/proxy-host-*_access.log`. An
attempt to fix that by bind-mounting a redacted copy of `/etc/nginx/conf.d/include/log-proxy.conf`
(`read_only: true`) took the proxy down for about three minutes: NPM's s6 `prepare` step runs
`chown -R $PUID:$PGID /etc/nginx/conf.d` on every fresh container under `set -e`, and `chown`
fails with EROFS on a read-only bind, so the container came up half-initialised (`s6-rc: warning:
unable to start service prepare`). Reverted in `1d2959e`.

A read-write bind of a file already owned by `$PUID:$PGID` would most likely pass that `chown`,
but proving it means another live deploy of the only proxy in front of every service here. The
application that put credentials in query strings (YA-WAMF) has stopped doing so, which is the
real fix, so this is deliberately left alone. If it is ever revisited: test the bind on a
throwaway NPM container first, never on this one.

## Native Tailscale on Quark

Install the stable signed Fedora package from Tailscale. During the one-time
handover, stop the old container through Dockhand before copying its private
state to root-owned `/var/lib/tailscale`; never run the same identity twice.
Enable `tailscaled.service` after copying state and verify the same node ID,
addresses, hostname, subnet routes and exit-node capability before deploying
this stack to remove the orphaned container. Keep a LAN SSH connection available.

Install `host/quark/99-quark-tailscale.conf` under `/etc/sysctl.d` for forwarding
and `host/quark/tailscaled-gro.conf` as `tailscaled.service.d/10-quark-gro.conf`.
Preserve route approvals and do not enable Tailscale SSH or change host DNS
acceptance during migration. The app backup includes the native state file.
Remove old Dockhand auth-key variables and container-state copy after acceptance.
