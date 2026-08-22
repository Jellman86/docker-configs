# Web Services Stack

Git-backed Dockhand stack for ingress, Cloudflare Tunnel, and Tailscale. This directory contains complete host-specific Compose manifests rather than an override chain.

## Compose manifests

| File | Intended host | Backend networks |
|---|---|---|
| `docker-compose.quark.yml` | Quark / Fedora | `general_brg`, `npm_proxy_backends` |
| `docker-compose.yml` | Riker / TrueNAS canonical stack | `general_brg`, `${NETWORK:-arr_stack_brg}`, `media_stack_default` |
| `docker-compose.riker.yml` | Explicit Riker equivalent | Same Riker networks as the base file |

Dockhand deploys one complete file. Do not combine these manifests with `-f` overlays. The base and Riker-specific files are equivalent today; keep them synchronized if both are retained.

## Services

| Service | Role | Published access |
|---|---|---|
| `npm` | Nginx Proxy Manager reverse proxy and certificate management | `80`, `81`, `443` |
| `cloudflared` | Outbound Cloudflare Tunnel connector | No host port |
| `tailscale` | Subnet router and exit node | No application port; `/dev/net/tun` |

## Networking

All variants attach services to the external `general_brg` network.

- Riker attaches NPM to ARR and media networks so it can proxy those services directly. Tailscale also joins the ARR network.
- Quark attaches NPM to `npm_proxy_backends`, which is the explicit network for private proxy targets such as OpenViking. Quark's Tailscale service remains on `general_brg` only.
- NPM has the `nginx-rp` alias on `general_brg`.
- Tailscale requires `NET_ADMIN`, `NET_RAW`, `/dev/net/tun`, and IPv4/IPv6 forwarding. The Quark manifest selects nftables-compatible binaries for Fedora.

Create the selected manifest's external networks before first deployment.

## Remote access and tailnet DNS

Both hosts run a Tailscale container that advertises the LAN as subnet routes, so tailnet
clients reach services by their normal `*.pownet.uk` names over the existing Nginx Proxy
Manager ingress and its `*.pownet.uk` wildcard certificate. No exit node is required; subnet
routes apply passively to any client with accept-routes enabled.

| Host | Advertised routes | Role |
|---|---|---|
| `quark` | `192.168.213.0/24`, `192.168.214.0/24`, `0.0.0.0/0`, `::/0` | subnet router (primary) + exit node |
| `riker` | `192.168.213.0/24`, `192.168.214.0/24`, `0.0.0.0/0`, `::/0` | subnet router (standby) + exit node |

Both hosts' routes are approved, so route failover between them is automatic.

### Split DNS (required for off-LAN access)

`*.pownet.uk` records exist only in local DNS; public resolvers return nothing. Without a
split-DNS route, remote clients can reach `192.168.213.0/24` but cannot resolve any service
name. The tailnet therefore maps the zone to the LAN resolver, which is itself inside an
advertised route:

```text
pownet.uk -> 192.168.213.254
```

This is control-plane state, not Compose state. Manage it through the Tailscale API:

```sh
# inspect
curl -H "Authorization: Bearer $TS_API_KEY" \
  https://api.tailscale.com/api/v2/tailnet/-/dns/split-dns

# set (PATCH is a partial update; it leaves other domains untouched)
curl -X PATCH -H "Authorization: Bearer $TS_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"pownet.uk":["192.168.213.254"]}' \
  https://api.tailscale.com/api/v2/tailnet/-/dns/split-dns

# remove
curl -X PATCH -H "Authorization: Bearer $TS_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"pownet.uk":null}' \
  https://api.tailscale.com/api/v2/tailnet/-/dns/split-dns
```

Global nameservers stay empty and MagicDNS stays enabled, so only `pownet.uk` queries are
redirected and general internet DNS is unaffected.

### Route auto-approval

The tailnet ACL auto-approves both subnet routes and exit-node advertisements. Without this,
recreating a Tailscale container without its `${DOCKERCONFIGPATH}/tailscale` state directory
produces a node whose routes sit unapproved, which breaks remote access silently and presents
as a DNS failure:

```json
"autoApprovers": {
  "routes": {
    "192.168.213.0/24": ["Jellman86@github"],
    "192.168.214.0/24": ["Jellman86@github"]
  },
  "exitNode": ["Jellman86@github"]
}
```

Tailscale cannot issue wildcard certificates for `*.ts.net`, so MagicDNS node names are not a
substitute for the NPM ingress and its `*.pownet.uk` wildcard.

## Persistent storage

| Host path | Purpose |
|---|---|
| `${DOCKERCONFIGPATH}/nginx-proxy-manager/data` | NPM database and configuration |
| `${DOCKERCONFIGPATH}/nginx-proxy-manager/letsencrypt` | Certificates and ACME state |
| `${DOCKERCONFIGPATH}/tailscale` | Tailscale node identity and state |

These directories contain security-sensitive state. Back them up with restrictive permissions and do not copy them into Git.

## Environment

Common settings:

- `PUID`, `PGID`, `TZ`, `DOCKERCONFIGPATH`
- `TAILSCALE_HOSTNAME`, `TAILSCALE_ADVERTISE_ROUTES`
- Riker network override: `NETWORK`

Secrets:

- `TUNNEL_TOKEN`
- `TS_AUTHKEY`

Store both secrets in Dockhand. Tailscale auth keys should be scoped and short-lived where practical.

## Deployment and updates

Choose the correct complete manifest in the Dockhand Git stack definition and follow the [root deployment procedure](../README.md). Never deploy the Quark manifest on Riker or vice versa without reviewing network and nftables differences.

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

Revert the relevant Git or image change, push, and redeploy the same host-specific manifest through Dockhand. Preserve NPM and Tailscale bind-mounted state. An ingress rollback can affect all hosted services, so verify local/LAN recovery access before updating and avoid changing DNS, tunnel routing, certificates, and container images in one release.

## Security notes

- NPM and Cloudflare/Tailscale credentials are administrative secrets.
- Keep NPM's admin UI on trusted networks or behind a separate access control.
- Review every proxy host and Cloudflare route for intended public versus LAN-only exposure.
- Tailscale is a privileged network boundary; advertise only explicitly approved routes.
- Never publish private backend MCP/CDP ports merely to make them easier to proxy.
