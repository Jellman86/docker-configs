# Hermes Agent on Quark

This is a standalone Git-backed Dockhand stack stored beside Quark's inference configuration. It is intentionally not part of `security_inference_stack/docker-compose.yml`, so Hermes upgrades do not pull or recreate Frigate, Home Assistant, BirdNET-Go, Mosquitto, or YA-WAMF.

## Design

- Official Hermes image pinned to a released tag and multi-architecture manifest digest.
- Persistent state under `/mnt/apps/docker/hermes`.
- Dashboard available only on Quark loopback port 9119 with Hermes basic authentication.
- Host command execution through the supported Hermes SSH backend.
- Container lifecycle through Dockhand rather than direct Docker mutations.
- Honcho selected as the external memory provider; its API key remains optional until configured.
- A read-only `quark-operations` skill and managed policy are supplied from Git.

## Host preparation

Hermes expects a private SSH key at:

```text
/mnt/apps/docker/hermes/host-control/id_ed25519
```

Create a dedicated `hermesops` account, generate the key as the host user that owns UID 1000, and add its public key to the account. On Quark, the following gives Hermes full host administration while keeping Docker lifecycle behind Dockhand:

```bash
sudo useradd --create-home --shell /bin/bash hermesops
sudo passwd hermesops
sudo usermod --append --groups wheel,systemd-journal hermesops

sudo install -d -m 0750 -o jellman86 -g jellman86 /mnt/apps/docker/hermes
sudo install -d -m 0700 -o jellman86 -g jellman86 /mnt/apps/docker/hermes/host-control
sudo -u jellman86 ssh-keygen -t ed25519 -a 100 -N '' -f /mnt/apps/docker/hermes/host-control/id_ed25519

sudo install -d -m 0700 -o hermesops -g hermesops /home/hermesops/.ssh
sudo install -m 0600 -o hermesops -g hermesops \
  /mnt/apps/docker/hermes/host-control/id_ed25519.pub \
  /home/hermesops/.ssh/authorized_keys
```

These commands assume the account and key do not already exist. Inspect rather than overwrite them if rerunning the preparation. The account must support non-interactive key authentication because Hermes connects with `BatchMode=yes`.

If full sudo is required, supply `HERMES_HOST_SUDO_PASSWORD` through Dockhand's secret variables. A restricted sudo policy is safer and should be expanded only when a real operation requires it. Do not add `hermesops` to the Docker group; Dockhand owns Docker lifecycle operations.

The host key directory and private key should be mode `0700` and `0600` respectively and readable by UID 1000. Test key access before deployment:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  -i /mnt/apps/docker/hermes/host-control/id_ed25519 \
  hermesops@127.0.0.1 true
```

Then confirm the password entered above can run `sudo`. Store that password only as the secret `HERMES_HOST_SUDO_PASSWORD` stack variable in Dockhand.

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

The dashboard is loopback-only. From another machine, tunnel it through SSH:

```bash
ssh -L 9119:127.0.0.1:9119 jellman86@quark.pownet.uk
```

Then open `http://127.0.0.1:9119`. Do not expose the dashboard publicly with basic authentication.

## Verification

1. Confirm `hermes-agent` is running and healthy in Dockhand.
2. Confirm the image contains the pinned release digest.
3. Open the dashboard through the SSH tunnel and authenticate.
4. Run `hermes doctor` and `hermes memory status` in the Dockhand terminal.
5. Ask Hermes for read-only Quark status and verify it connects through SSH.
6. Ask for a Dockhand stack listing and confirm no direct Docker mutation occurs.
7. Test Home Assistant with an entity read before allowing service calls.
