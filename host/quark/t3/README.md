# Native T3 Code

T3 runs as the existing `jellman86` host user because coding agents need native toolchains, hardware and authorized system administration. It is separate from the Forgejo Compose stack. Upstream supports `t3 service install` and a systemd user service with lingering on Linux.

The installed versions on 18 October match the Mac: T3 0.1.0, Codex 0.163.0, Claude Code 2.1.302, Muse 1.4.10 and OpenCode 1.19.3. T3's default is Muse Wonder Full; provider sign-ins are deferred at the user's request. OpenCode free-model inference was checked separately from paid-provider authentication. (OpenViking was retired on 2026-10-18; agents now use OpenKnowledge MCP.)

## State and startup

`~/.t3`, `~/.codex`, `~/.claude`, provider data and native package storage point into `/mnt/apps/developer/jellman86/agent-state` or `agent-tools` on the original SSD. Preserve existing developer symlinks and work. The small OS root is not a build/cache destination.

Install the official CLI as the normal user, enable lingering, then use `t3 service install`. Apply [quark.conf](quark.conf) at `~/.config/systemd/user/t3code.service.d/quark.conf`, with a private `~/.t3/provider.env` for any provider credentials. Never copy real credentials into this public deployment repository.

The private agent-information checkout is `/mnt/apps/developer/jellman86/.agents`, exposed as `~/.agents`. It comes from the separate private Forgejo repository and intentionally contains owner-authorized secrets. Ordinary provider configurations use the unauthenticated private OpenKnowledge MCP at `https://openknowledge.pownet.uk/mcp`. No Mac conversations, environment identity or provider OAuth sessions were copied.

## Routing and permissions

- `https://t3.pownet.uk`: UniFi A record `.102`; NPM proxies to `172.18.0.1:3773` with WebSockets.
- `https://quark.dinosaur-algieba.ts.net/`: private Tailscale Serve HTTPS, forwarding to loopback port 3773. No public Funnel.
- Desktop SSH environment: `jellman86@quark.pownet.uk`.
- Generate a fresh pairing link with `t3 pair --tailscale`; never commit the token.

GPU/NPU access uses existing video/render memberships. The host user retains its existing wheel/sudo and Docker memberships. Sudo requires the user's password; no passwordless rule or root T3 server was added. Existing Git/CI/Dockhand rules still govern Compose deployments.

## Maintenance

Use `t3 service status`, `systemctl --user status t3code.service` and `journalctl --user -u t3code.service`. The service starts at boot and survives logout. Trace rotation and the normal system journal bound logs.

Use `t3 update`; it asks before restarting active work. Claude's native installer and Muse's stable launcher manage their updates. Codex/OpenCode use the existing SSD npm prefix. No extra recurring updater or OpenCode 2 migration was installed.

Developer/T3 conversation state is excluded from the normal application backup. Important source belongs in Git; preserving conversations needs a separate deliberate backup choice.

[Installation](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md), [background service](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md), [remote access](https://github.com/pingdotgg/t3code/blob/main/docs/user/remote-access.md).
