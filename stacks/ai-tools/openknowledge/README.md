# OpenKnowledge sidecar

This image packages the upstream `@inkeep/open-knowledge` server for the
`ai-tools` stack. Upstream publishes no registry image, so the Dockerfile
follows the [upstream Docker recipe](https://openknowledge.ai/docs/remote-control/methods/docker)
with supply-chain pins, matching the other built images in this stack.

## Supply-chain pins

- npm package: `@inkeep/open-knowledge@0.86.22` (`OPENKNOWLEDGE_VERSION` build arg)
- Base image: `node:24-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5`
- To upgrade, bump both pins together, rebuild through Dockhand, and back up
  `/mnt/apps/docker/openknowledge` first. The entrypoint finds the existing
  project on the volume and starts the server; content and history remain.

## Security boundary

- OpenKnowledge has no authentication of its own. The container is only
  reachable on `npm_proxy_backends`; NPM is the authenticating edge (access
  list with Basic auth for browser and MCP clients). Never publish a host
  port or route it publicly without that access list.
- `OK_ALLOW_EXTERNAL=1` is only safe behind that edge. It is supplied by
  Compose together with `OK_EXTERNAL_URL=https://openknowledge.pownet.uk`;
  without the pair the server refuses proxied requests.
- The container runs as UID/GID 1000 with a read-only root filesystem, all
  capabilities dropped, `no-new-privileges`, bounded resources/logs, and a
  tmpfs `/tmp`. Its only writable state is the `/data` bind mount, which is a
  live git repository: run exactly one replica against it.
- NPM must preserve the client `Host`, set `X-Forwarded-Proto: https`, allow
  WebSockets (live editing) and never buffer `/mcp` (SSE streaming).

## Endpoints

The server only allows its external Host (`openknowledge.pownet.uk`), so
even Hermes connects through NPM with the access-list credential — a direct
`http://openknowledge:8080/mcp` request is rejected with
`403 Host header not allowed`. Hermes receives the full
`Basic <base64>` header as the Dockhand secret
`OPENKNOWLEDGE_MCP_AUTHORIZATION`. Direct service-name access is only used
for the `/readyz` healthcheck, which has no Host restriction.

Trusted LAN/Tailscale clients use the authenticated TLS proxy:

```text
https://openknowledge.pownet.uk/mcp
https://openknowledge.pownet.uk/        (editor)
```

Health: `GET /healthz` (liveness), `GET /readyz` (readiness, used by the
Compose healthcheck).

## Host preparation

Create the persistent directory before the first deployment (owned by
UID/GID 1000, as for OpenViking):

```bash
install -d -m 0700 -o 1000 -g 1000 /mnt/apps/docker/openknowledge
```
