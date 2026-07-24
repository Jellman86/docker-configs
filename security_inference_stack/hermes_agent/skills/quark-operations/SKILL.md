---
name: quark-operations
description: Operate and diagnose the Quark Fedora host and its Git-backed Dockhand Compose stacks. Use for host health, logs, services, containers, stack syncs, deployments, rollbacks, Home Assistant connectivity, or incidents on quark.pownet.uk.
---

# Quark Operations

Treat Quark as a production host. Inspect first, minimize scope, preserve persistent data, and report the exact result of every mutation.

## Host contract

- Execute host commands through the configured SSH backend.
- Use `http://127.0.0.1:3000` for Dockhand. Terminal commands run on Quark through SSH, so this URL is intentionally host-loopback rather than a container-only hostname.
- Keep application state under `/mnt/apps/docker`; Docker engine data is `/mnt/apps/docker-engine` and is never an application bind-mount target.
- Keep secrets in Dockhand stack secrets or Hermes credential storage. Never print, copy, or commit `.env`, tokens, passwords, private keys, or generated `.env.dockhand` files.
- Never mount or expose the host Docker socket from an agent-created container.

## Diagnose before changing

1. Establish the requested outcome and affected service or stack.
2. Gather read-only evidence with the smallest relevant commands: `systemctl status`, `journalctl`, `ss`, `df`, `free`, `curl` health requests, and Dockhand GET endpoints.
3. Check current state again immediately before a mutation.
4. Make one bounded change, then verify service state, health, logs, and absence of duplicate containers.

Do not claim success from a command exit alone. Verify the application-facing outcome.

## Docker and Compose lifecycle

Git and Dockhand are the only deployment path. Never run `docker run`, `docker pull`, `docker compose pull`, `docker compose up`, direct container start/stop/restart/remove commands, or an equivalent Docker Engine mutation.

Read-only Docker diagnostics such as `docker ps`, `docker logs`, `docker inspect`, `docker stats`, and `docker network inspect` are allowed when the SSH user has permission. Prefer Dockhand GET endpoints when they provide the same evidence.

For a Git-backed stack using the Dockhand `1.0.27` API contract verified on
2026-07-24:

1. Ensure the intended Compose change is committed and pushed and any required image manifest exists.
2. `GET /api/health` and require an OK response.
3. Read the live Dockhand version with
   `docker exec dockhand node -p "require('/app/package.json').version"`. If it
   is not `1.0.27`, stop and verify the current UI/API deploy route, request
   payload, job schema, and terminal states before changing this skill.
4. `GET /api/git/stacks`; select by stack name, repository, branch, and compose path. Never guess an id.
5. Verify the stack's `repullImages`, `buildOnDeploy`, and `forceRedeploy` settings are appropriate for the change.
6. `POST /api/git/stacks/{id}/deploy-stream` with content type `application/json` and body `{}`. Record the returned `jobId`.
7. Poll `GET /api/jobs/{jobId}` while `status` is `running`. Require `done`, inspect `result` for an error/failure, and treat `error` or an unknown status as failure.
8. `GET /api/git/stacks/{id}` and verify `lastCommit` equals the intended remote revision.
9. Verify the expected image, running state, health, private-port posture, application endpoint, and logs.

Do not retry a deployment while the first request is running. A long request can be a normal graceful drain.

If Dockhand authentication is later enabled, stop and require a dedicated
host-side credential mechanism before proceeding. Do not treat the managed SSH
backend as a secret transport or assume that container environment variables
are forwarded into SSH commands. Never place a token in a URL, command history,
skill, or repository file.

## Rollback

Revert or pin a known-good Compose/image version in Git, push it, then repeat the same deploy-stream and job-verification sequence. Never repair a Git stack by editing Dockhand's generated checkout, `.env.dockhand`, database, or a running container.

## Host mutations

- Use `sudo` only when the requested operation truly requires it.
- Explain service interruption, data risk, and rollback before high-impact changes.
- Never disable SSH, networking, Docker, Dockhand, the firewall, or authentication without explicit confirmation and a recovery path.
- Never recursively delete broad directories. Resolve and inspect an exact target first.
- Prefer reversible changes and preserve backups of modified host configuration.

## Home Assistant

Use the native Home Assistant tools for entity and service operations. Use host SSH only for host-level Home Assistant diagnosis. Start with reads; require explicit user intent before changing locks, alarms, cameras, or safety-related devices.
