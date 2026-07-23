# Hermes Agent on Quark

This is a standalone Git-backed Dockhand stack stored beside Quark's inference configuration. It is intentionally not part of `security_inference_stack/docker-compose.yml`, so Hermes upgrades do not pull or recreate Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

## Design

- Official Hermes image pinned to a released tag and multi-architecture manifest digest.
- Persistent state under `/mnt/apps/docker/hermes`.
- Dashboard available through Nginx Proxy Manager at `https://hermes.pownet.uk`, with a loopback-only port 9119 fallback and Hermes basic authentication.
- Host command execution through the supported Hermes SSH backend.
- Container lifecycle through Dockhand rather than direct Docker mutations.
- Hermes built-in `MEMORY.md`, `USER.md`, SQLite session history, and skills remain persistent; OpenViking adds automatic hierarchical recall, session extraction, and resource ingestion.
- OpenViking v0.4.11 runs as a non-root sidecar with no published host port, hashed API keys, encrypted persistent data, and isolated Codex OAuth credentials.
- Its authenticated MCP endpoint is routed through Quark's LAN-only Nginx Proxy Manager; internal storage and Ollama remain private.
- A non-root one-shot provisioner creates least-privileged `hermes/hermes` and
  recovery `hermes/codex` USER keys. Approved agents share the `hermes/hermes`
  identity and `hermes` agent scope so they read and write the same user and
  agent memories; the root credential remains confined to OpenViking and the
  bootstrap job.
- A private Ollama v0.32.1 sidecar supplies `nomic-embed-text` embeddings without a separately billed embedding API.
- The official Microsoft Playwright MCP v0.0.78 image supplies shared headless Chromium automation over private Docker HTTP transport.
- The read-only `quark-operations` skill and managed policy are supplied from Git.
- A read-only Rusty IMAP MCP sidecar is isolated on a private Compose network and exposes no host ports.

## Host preparation

Hermes expects a private SSH key at:

```text
/mnt/apps/docker/hermes/host-control/id_ed25519
```

Hermes runs host commands as the existing `jellman86` account. Use a dedicated agent key rather than reusing a personal workstation key:

```bash
install -d -m 0750 /mnt/apps/docker/hermes
install -d -m 0700 /mnt/apps/docker/hermes/host-control ~/.ssh
test -f /mnt/apps/docker/hermes/host-control/id_ed25519 || \
  ssh-keygen -t ed25519 -a 100 -N '' -C 'hermes-agent@quark' \
    -f /mnt/apps/docker/hermes/host-control/id_ed25519
touch ~/.ssh/authorized_keys
grep -qxFf /mnt/apps/docker/hermes/host-control/id_ed25519.pub ~/.ssh/authorized_keys || \
  cat /mnt/apps/docker/hermes/host-control/id_ed25519.pub >> ~/.ssh/authorized_keys
chmod 0600 /mnt/apps/docker/hermes/host-control/id_ed25519 ~/.ssh/authorized_keys
```

The commands preserve an existing key and avoid adding the same public key twice. The account must support non-interactive key authentication because Hermes connects with `BatchMode=yes`.

Create the non-root persistent directories before the first OpenViking deployment:

```bash
install -d -m 0700 /mnt/apps/docker/openviking
install -d -m 0700 /mnt/apps/docker/openviking-ollama
```

Both directories are owned by UID/GID 1000. OpenViking keeps its configuration,
encrypted context database, and dedicated `codex_auth.json` under the first path;
Ollama keeps the embedding model under the second. Do not copy or bind-mount
Hermes's own Codex token store into OpenViking.

Supply `HERMES_HOST_SUDO_PASSWORD` through Dockhand's secret variables when Hermes needs sudo. The account already has host and Docker permissions, so the managed deny rules and `quark-operations` skill require all Docker lifecycle changes to go through Dockhand.

The host key directory and private key should be mode `0700` and `0600` respectively and readable by UID 1000. Test key access before deployment:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  -i /mnt/apps/docker/hermes/host-control/id_ed25519 \
  jellman86@127.0.0.1 true
```

Confirm the account password can run `sudo`. Store that password only as the secret `HERMES_HOST_SUDO_PASSWORD` stack variable in Dockhand.

## Dockhand stack

Create a Git stack with:

- Stack name: `hermes_agent`
- Compose path: `security_inference_stack/hermes_agent/docker-compose.yml`
- Context directory: the Compose file's directory/default
- Re-pull images: enabled
- Build images: enabled (required for the pinned Rusty IMAP MCP sidecar)
- Force recreation: enabled for deliberate upgrades

Copy every required value from the ignored `.env` into the stack-variable panel. Mark dashboard credentials, provider keys, messaging tokens, Home Assistant token, sudo password, `RUSTY_IMAP_MCP_IMAP_PASSWORD`, `OPENVIKING_ROOT_API_KEY`, `OPENVIKING_HERMES_KEY_SEED`, `OPENVIKING_API_KEY`, `OPENVIKING_CODEX_KEY_SEED`, and `OPENVIKING_CODEX_API_KEY` as secrets. The OpenViking root key and both tenant-key seeds must each be independent 64-character random hexadecimal values and must never be committed.

Derive each tenant key locally from its dedicated seed using the same documented v0.4.11 key codec. Do not print keys into shell history; write them directly to the ignored `.env` or Dockhand secret input. The one-shot `openviking-bootstrap` service independently creates or repairs both USER identities and fails closed unless OpenViking returns exactly the derived values:

```python
import base64, hashlib
b64 = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
def user_key(user, seed):
    secret = hashlib.sha256(f"{user}\0{seed}".encode()).hexdigest()
    return f"{b64('hermes')}.{b64(user)}.{b64(secret)}"

hermes_key = user_key("hermes", "<OPENVIKING_HERMES_KEY_SEED>")
codex_key = user_key("codex", "<OPENVIKING_CODEX_KEY_SEED>")
```

The root key is available only to OpenViking and the short-lived bootstrap
container. The bootstrap verifies that both configured USER keys match their
seed-derived and server-returned values before Hermes may start. Hermes uses
the `hermes/hermes` USER key. Approved Codex clients may receive that same USER
key from their operating system's secret store when shared memory is required;
the `hermes/codex` key remains an isolated recovery identity. OpenViking stores
tenant keys as Argon2id hashes.

OpenViking uses a separate ChatGPT/Codex device login. Place the resulting OpenViking-owned token store at:

```text
/mnt/apps/docker/openviking/codex_auth.json
```

The local embedding model is pulled automatically by the one-shot `openviking-ollama-model` service before OpenViking starts. Neither port 1933 nor 11434 is published to the host.
OpenViking uses the ChatGPT-backed Codex model selected by
`OPENVIKING_VLM_MODEL` for memory extraction. The default is
`gpt-5.6-luna` with `OPENVIKING_VLM_REASONING_EFFORT=low`. Luna is the
extraction-oriented, token-efficient GPT-5.6 tier; the model must remain
present in the authenticated Codex model catalogue. Use Terra only when
representative memory-extraction checks show that Luna misses important facts
or relationships.

Deploy only through Dockhand. After deployment, use Dockhand's container terminal for initial setup:

```bash
hermes doctor
hermes model
hermes memory status
```

The managed configuration selects the native `openviking` provider. Existing
Hermes profile memory and session history remain on `/opt/data`; OpenViking is
additive and does not migrate or delete them.

## Playwright MCP

The stack runs Microsoft's official `mcr.microsoft.com/playwright/mcp` image,
pinned to release v0.0.78 and its immutable multi-architecture digest. Hermes
connects through its native Streamable HTTP MCP client at:

```text
http://playwright-mcp:8931/mcp
```

The endpoint is available to containers attached to the external
`general_brg` network. Port 8931 is exposed only as Docker metadata and is not
published on the host. Other MCP clients on that network can use the same URL.

Codex on the trusted LAN connects through the authenticated TLS proxy at:

```text
https://quark.pownet.uk/mcp
```

Nginx Proxy Manager authenticates this dedicated proxy host before forwarding
to `playwright-mcp:8931`; the backend remains unpublished and explicitly allows
only its internal service names plus `quark.pownet.uk`. Codex reads the Basic
authorization header from `PLAYWRIGHT_MCP_AUTHORIZATION` through
`env_http_headers`; the value must come from the client operating system's
secret store rather than `~/.codex/config.toml`.

Each HTTP client receives an isolated, ephemeral headless Chromium context.
The service runs as the image's unprivileged `node` user with a read-only root
filesystem, dropped capabilities, no-new-privileges, and bounded tmpfs storage.
Service workers are disabled and no host workspace, browser profile, or Docker
socket is mounted.

Playwright MCP is not an authentication or network security boundary. Treat
membership of `general_brg` and access to the dedicated NPM credential as
permission to control a browser. Do not publish port 8931.

## Access

Nginx Proxy Manager routes `https://hermes.pownet.uk` to `hermes-agent:9119` over the external `general_brg` network. The proxy host uses the existing `*.pownet.uk` certificate, Force SSL, HTTP/2, WebSocket support, and Block Common Exploits.

The trusted-network DNS server must resolve `hermes.pownet.uk` to Quark/NPM at `192.168.213.102`.

Nginx Proxy Manager routes the exact `/mcp` location on the existing
LAN-only Hermes host to `openviking:1933` over `npm_proxy_backends`:

```text
https://hermes.pownet.uk/mcp
```

The main Hermes dashboard route remains `hermes-agent:9119`; only `/mcp` is
sent to OpenViking. Approved agents that require identical memories use the
same `hermes/hermes` USER key and the `hermes` agent scope. Never configure a
client with `OPENVIKING_ROOT_API_KEY`. OpenViking and Ollama retain no
host-published ports.

Register the endpoint with Codex using an environment-backed bearer token:

```bash
codex mcp add openviking \
  --url https://hermes.pownet.uk/mcp \
  --bearer-token-env-var OPENVIKING_SHARED_API_KEY
```

Supply `OPENVIKING_SHARED_API_KEY` with the same value as the Dockhand secret
`OPENVIKING_API_KEY` from the client operating system's secret store; do not
put the key directly in `~/.codex/config.toml`. Add the non-secret agent header
to the server entry so Codex shares Hermes's agent memory as well as its user
memory:

```toml
[mcp_servers.openviking]
url = "https://hermes.pownet.uk/mcp"
bearer_token_env_var = "OPENVIKING_SHARED_API_KEY"
http_headers = { "X-OpenViking-Agent" = "hermes" }
```

Restart Codex after adding the server or changing its credential. This native
MCP connection exposes OpenViking's tools on demand. Automatic prompt recall
and turn capture require the separate official OpenViking Codex memory plugin
and its reviewed lifecycle hooks.

The published host port remains loopback-only as a recovery path. To use it from another machine:

```bash
ssh -L 9119:127.0.0.1:9119 jellman86@quark.pownet.uk
```

Then open `http://127.0.0.1:9119`. Keep the NPM route and DNS record private to the trusted network when using basic authentication.

## Verification

1. Confirm `hermes-agent` is running and healthy in Dockhand.
2. Confirm all runtime images match their pinned release digests.
3. Open `https://hermes.pownet.uk` and authenticate; use the SSH tunnel only as a recovery path.
4. Confirm `openviking` and `openviking-ollama` are healthy, and both `openviking-ollama-model` and `openviking-bootstrap` exited successfully.
5. From the trusted LAN, confirm `https://hermes.pownet.uk/mcp` rejects an unauthenticated request.
6. Connect Codex with the shared `hermes/hermes` USER key and `hermes` agent
   scope. Verify that both clients list the same user and peer memory URIs
   without exposing the key or OpenViking root credential.
7. Run `hermes doctor` and `hermes memory status` in the Dockhand terminal; confirm the `openviking` provider is active.
8. From Hermes, store a unique test fact with `viking_remember`, retrieve it with `viking_search`, recreate the OpenViking service through Dockhand, and retrieve it again.
   Treat an accepted store request as incomplete until OpenViking logs confirm
   extraction succeeded and the other client retrieves the resulting memory.
9. Confirm `openviking` runs as UID 1000, has a read-only root filesystem, and publishes no host port.
10. Ask Hermes for read-only Quark status and verify it connects through SSH.
11. Ask for a Dockhand stack listing and confirm no direct Docker mutation occurs.
12. Test Home Assistant with an entity read before allowing service calls.
13. Confirm `rusty-imap-mcp` is healthy and Hermes registers only `mcp_rusty_imap_{list_folders,search,fetch_message,list_attachments,list_labels}`.
14. Confirm `playwright-mcp` is healthy, has no published port, and Hermes discovers `mcp_playwright_*` browser tools from `http://playwright-mcp:8931/mcp`.
15. Use Playwright MCP to navigate to a harmless public page, inspect its title, and close the browser context.
16. Confirm a body fetch leaves the message's `\\Seen` flag unchanged. Rusty uses read-only `EXAMINE` plus `BODY.PEEK[]`; the runtime check verifies the provider preserves that behavior.
