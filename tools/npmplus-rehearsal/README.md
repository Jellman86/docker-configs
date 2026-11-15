# Offline NPMplus migration rehearsal

One-time compatibility test of a consistent copy of Quark's original NPM state.
The source NPM is 2.17.0. Stable NPMplus 2026-10-22-r1 was tested and rejects
its `20260906220000_user_permission_meta.js` migration. The next candidate is the
official upstream `develop` image pinned by digest, whose source includes that
migration. This is a development build, not a newly released stable version.
Migration and application tests must succeed without editing migration history
or touching the original database.

Prepare an independent, private copy of both NPM data and letsencrypt under the
owner's developer SSD. Use SQLite's backup API for the live database, preserve
file identities, and verify certificate files do not change during capture. Do
not bind the original state directories. Do not commit state or credentials.

First deploy `compose.migrate.yaml` to import the copied legacy certificate tree.
When upstream reports that import complete, switch the same Dockhand Git record
to `compose.yaml` and sync/deploy again; the old letsencrypt mount must be absent
before upstream continues its database migration. Never deploy both entrypoints
as separate workloads against the same copy.

Deploy only through Git, passing CI and Dockhand in Quark environment 1, with
automatic sync/deploy disabled. Set `NPMPLUS_REHEARSAL_ROOT` to that isolated copy
and `NPMPLUS_REHEARSAL_COOKIE_SECRET` as an encrypted Dockhand variable. Host port
bindings and network egress are deliberately absent; copied DNS credentials must
never reach the real provider. Read the loopback API through Dockhand's approved
container execution endpoint. Do not use Docker CLI lifecycle or exec commands.

Verify readiness, administrator authentication, migrated host/certificate/access
list counts and the selected version's API schema. Offline backend DNS and ACME
failures are expected and are separate from database compatibility. A successful
API/database test does not prove proxying, TLS renewal, WebSockets or enforcement;
those need a subsequent isolated connected rehearsal before production cutover.

Stop/remove only this owned test workload and Git-stack record through Dockhand
when finished, and securely remove copied private state after rollback/recovery
requirements are met. Preserve all other agents' containers and work.
