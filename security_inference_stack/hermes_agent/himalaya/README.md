# Himalaya iCloud Mail client

This directory builds a pinned Himalaya v1.2.0 command-line mail client for the
`hermes_agent` Dockhand stack. The service is intentionally placed behind the
`mail` Compose profile and configures IMAP only; SMTP sending is not enabled.

## Dockhand variables

Before enabling the profile, add these variables to the Git-backed
`hermes_agent` stack in Dockhand:

| Variable | Secret | Purpose |
| --- | --- | --- |
| `COMPOSE_PROFILES=mail` | No | Enables the opt-in mail service |
| `ICLOUD_EMAIL` | Yes | Full iCloud Mail address |
| `ICLOUD_IMAP_LOGIN` | Yes | Usually the address portion before `@icloud.com`; use the full address if required |
| `ICLOUD_APP_PASSWORD` | Yes | Apple app-specific password; never commit it to Git |

Dockhand injects `ICLOUD_APP_PASSWORD` into the Compose process. Compose mounts
it into the container as `/run/secrets/icloud_app_password`, so the password is
not placed in the container environment. The container refuses to start when the
secret, email address, or IMAP login is empty.

The Git stack must have **Build images** enabled because no official Himalaya
container image is published. Dockhand builds the image from the pinned release
archive and verifies its SHA-256 checksum.

## Operations

After deployment, use the Dockhand container terminal or Docker CLI access:

```bash
docker exec himalaya-mail himalaya account list
docker exec himalaya-mail himalaya folder list
docker exec himalaya-mail himalaya envelope list --page 1 --page-size 20
```

The service exposes no ports, runs without Linux capabilities, uses a read-only
root filesystem, and has no access to the Docker socket or other application
data. Mail remains in iCloud and is accessed over TLS IMAP.

IMAP-only does **not** mean read-only: the iCloud credential can still move, delete,
copy, append, or flag messages. Treat Docker-exec access to this container as mailbox
write access, and do not perform mutating commands without explicit authorization.
