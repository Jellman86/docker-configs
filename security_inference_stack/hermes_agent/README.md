# Hermes Agent on Quark

This is a standalone Git-backed Dockhand stack stored beside Quark's inference configuration. It is intentionally not part of `security_inference_stack/docker-compose.yml`, so Hermes upgrades do not pull or recreate Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

## Design

- Official Hermes image pinned to a released tag and multi-architecture manifest digest.
- Persistent state under `/mnt/apps/docker/hermes`.
- Dashboard available through Nginx Proxy Manager at `https://hermes.pownet.uk`, with a loopback-only port 9119 fallback and Hermes basic authentication.
- Host command execution through the supported Hermes SSH backend.
- Container lifecycle through Dockhand rather than direct Docker mutations.
- Honcho selected as the external memory provider; its API key remains optional until configured.
- A read-only `quark-operations` skill and managed policy are supplied from Git.

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
- Build images: disabled
- Force recreation: enabled for deliberate upgrades

Copy every required value from the ignored `.env` into the stack-variable panel. Mark dashboard credentials, provider keys, messaging tokens, Home Assistant token, Honcho key, and the sudo password as secrets.

Deploy only through Dockhand. After deployment, use Dockhand's container terminal for initial setup:

```bash
hermes doctor
hermes model
hermes memory setup honcho
hermes memory status
```

Honcho can use cloud OAuth/API-key mode or a self-hosted base URL. The managed configuration pins Honcho as the selected provider but leaves credentials and identity setup to the wizard.

## Access

Nginx Proxy Manager routes `https://hermes.pownet.uk` to `hermes-agent:9119` over the external `general_brg` network. The proxy host uses the existing `*.pownet.uk` certificate, Force SSL, HTTP/2, WebSocket support, and Block Common Exploits.

The trusted-network DNS server must resolve `hermes.pownet.uk` to Quark/NPM at `192.168.213.102`. This record is separate from NPM and was not present when the proxy host was created.

The published host port remains loopback-only as a recovery path. To use it from another machine:

```bash
ssh -L 9119:127.0.0.1:9119 jellman86@quark.pownet.uk
```

Then open `http://127.0.0.1:9119`. Keep the NPM route and DNS record private to the trusted network when using basic authentication.

## Verification

1. Confirm `hermes-agent` is running and healthy in Dockhand.
2. Confirm the image contains the pinned release digest.
3. Open `https://hermes.pownet.uk` and authenticate; use the SSH tunnel only as a recovery path.
4. Run `hermes doctor` and `hermes memory status` in the Dockhand terminal.
5. Ask Hermes for read-only Quark status and verify it connects through SSH.
6. Ask for a Dockhand stack listing and confirm no direct Docker mutation occurs.
7. Test Home Assistant with an entity read before allowing service calls.
