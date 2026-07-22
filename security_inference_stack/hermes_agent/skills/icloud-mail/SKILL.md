---
name: icloud-mail
description: Use when listing, searching, or reading Scott's iCloud Mail through the isolated Himalaya sidecar on Quark. Defaults to non-mutating IMAP operations and requires explicit authorization before changing mailbox state.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [email, icloud, himalaya, imap]
    related_skills: [quark-operations]
---

# iCloud Mail

## Overview

Use the `himalaya-mail` sidecar through the configured SSH terminal backend. Himalaya is not installed in the Hermes container; invoke it on Quark with `docker exec`. The sidecar exposes no ports and receives its app-specific password as a Compose secret.

## When to Use

Use for listing folders, searching bounded envelope pages, previewing messages without marking them read, and diagnosing account connectivity. Do not use SMTP: this deployment is IMAP-only. Do not mutate flags, messages, folders, or attachments unless the user explicitly authorizes that exact operation.

## Safe Workflow

1. **Health first.** Run `docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' himalaya-mail`. Continue only when it reports `running healthy`.
2. **List before reading.** Start with a bounded envelope query and JSON output. Do not fetch entire mailboxes.
3. **Preview reads.** Always pass `--preview` to `message read`; without it Himalaya adds the `seen` flag.
4. **Minimize disclosure.** Return only fields and message content needed for the request. Never print configuration, process environments, `/run/secrets`, or app-password data.
5. **Verify mutations.** If explicitly authorized, perform one bounded mutation and read back the affected envelope state before reporting success.

## Read-Only Commands

```bash
# Account and folders
docker exec himalaya-mail himalaya account list --output json
docker exec himalaya-mail himalaya folder list --output json

# Most recent INBOX envelopes
docker exec himalaya-mail himalaya envelope list \
  --folder INBOX --page 1 --page-size 20 --output json \
  order by date desc

# Search examples
docker exec himalaya-mail himalaya envelope list \
  --folder INBOX --page 1 --page-size 20 --output json \
  from sender@example.com order by date desc
docker exec himalaya-mail himalaya envelope list \
  --folder INBOX --page 1 --page-size 20 --output json \
  subject invoice and after 2026-01-01 order by date desc

# Preview without adding the seen flag
docker exec himalaya-mail himalaya message read \
  --folder INBOX --preview --output json MESSAGE_ID
```

Treat query words as separate shell arguments. Shell-quote all user-provided patterns; never interpolate raw user text into a command string.

## Mutating Operations

Require explicit authorization immediately before: reading without `--preview`; changing flags; copying, moving, deleting, appending, or purging messages; changing folders; or downloading attachments. Sending is unavailable by design. Do not add SMTP credentials or alter the deployment as a workaround.

## Common Pitfalls

1. **A normal read is not read-only.** Use `message read --preview`.
2. **Envelope IDs are folder-scoped.** Preserve the folder from the listing.
3. **Unbounded output leaks mail.** Always set page and page-size limits.
4. **Health checks contact iCloud.** Diagnose bounded logs without exposing secrets before changing anything.
5. **Docker lifecycle is Dockhand-owned.** `docker exec`, `inspect`, and logs are permitted; never start, stop, recreate, pull, or update the sidecar directly.

## Verification Checklist

- [ ] `himalaya-mail` was running and healthy before mailbox access.
- [ ] Every list/search was page-bounded.
- [ ] Every message read used `--preview` unless marking it seen was authorized.
- [ ] No secret, configuration, or irrelevant message content was disclosed.
- [ ] Any mutation had explicit authorization and was verified with a follow-up read.
