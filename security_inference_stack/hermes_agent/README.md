# Hermes Agent on Quark

This is a standalone Git-backed Dockhand stack stored beside Quark's inference configuration. It is intentionally not part of `security_inference_stack/docker-compose.yml`, so Hermes upgrades do not pull or recreate Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

## Design

- Official Hermes image pinned to a released tag and multi-architecture manifest digest.
- Persistent state under `/mnt/apps/docker/hermes`.
- Dashboard available through Nginx Proxy Manager at `https://hermes.pownet.uk`, with a loopback-only port 9119 fallback and Hermes basic authentication.
- Host command execution through the supported Hermes SSH backend.
- Container lifecycle through Dockhand rather than direct Docker mutations.
- Hermes built-in `MEMORY.md`, `USER.md`, SQLite session history, and skills remain persistent; OpenViking adds automatic hierarchical recall, session extraction, and resource ingestion.
- OpenViking v0.4.11 runs as a non-root private sidecar with no published port, an API key, encrypted persistent data, and isolated Codex OAuth credentials.
- A private Ollama v0.32.1 sidecar supplies `nomic-embed-text` embeddings without a separately billed embedding API.
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

Copy every required value from the ignored `.env` into the stack-variable panel. Mark dashboard credentials, provider keys, messaging tokens, Home Assistant token, sudo password, `RUSTY_IMAP_MCP_IMAP_PASSWORD`, and `OPENVIKING_ROOT_API_KEY` as secrets. The OpenViking key should be 64 random hexadecimal characters and must never be committed.

OpenViking uses a separate ChatGPT/Codex device login. Place the resulting OpenViking-owned token store at:

```text
/mnt/apps/docker/openviking/codex_auth.json
```

The local embedding model is pulled automatically by the one-shot `openviking-ollama-model` service before OpenViking starts. Neither port 1933 nor 11434 is published to the host.

Deploy only through Dockhand. After deployment, use Dockhand's container terminal for initial setup:

```bash
hermes doctor
hermes model
hermes memory status
```

The managed configuration selects the native `openviking` provider. Existing
Hermes profile memory and session history remain on `/opt/data`; OpenViking is
additive and does not migrate or delete them.

## Access

Nginx Proxy Manager routes `https://hermes.pownet.uk` to `hermes-agent:9119` over the external `general_brg` network. The proxy host uses the existing `*.pownet.uk` certificate, Force SSL, HTTP/2, WebSocket support, and Block Common Exploits.

The trusted-network DNS server must resolve `hermes.pownet.uk` to Quark/NPM at `192.168.213.102`.

The published host port remains loopback-only as a recovery path. To use it from another machine:

```bash
ssh -L 9119:127.0.0.1:9119 jellman86@quark.pownet.uk
```

Then open `http://127.0.0.1:9119`. Keep the NPM route and DNS record private to the trusted network when using basic authentication.

## Verification

1. Confirm `hermes-agent` is running and healthy in Dockhand.
2. Confirm all runtime images match their pinned release digests.
3. Open `https://hermes.pownet.uk` and authenticate; use the SSH tunnel only as a recovery path.
4. Confirm `openviking` and `openviking-ollama` are healthy and `openviking-ollama-model` exited successfully after pulling `nomic-embed-text`.
5. Run `hermes doctor` and `hermes memory status` in the Dockhand terminal; confirm the `openviking` provider is active.
6. From Hermes, store a unique test fact with `viking_remember`, retrieve it with `viking_search`, recreate the OpenViking service through Dockhand, and retrieve it again.
7. Confirm `openviking` runs as UID 1000, has a read-only root filesystem, and exposes no host port.
8. Ask Hermes for read-only Quark status and verify it connects through SSH.
9. Ask for a Dockhand stack listing and confirm no direct Docker mutation occurs.
10. Test Home Assistant with an entity read before allowing service calls.
11. Confirm `rusty-imap-mcp` is healthy and Hermes registers only `mcp_rusty_imap_{list_folders,search,fetch_message,list_attachments,list_labels}`.
12. Confirm a body fetch leaves the message's `\\Seen` flag unchanged. Rusty uses read-only `EXAMINE` plus `BODY.PEEK[]`; the runtime check verifies the provider preserves that behavior.
