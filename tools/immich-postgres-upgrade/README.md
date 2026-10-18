# Isolated Immich database rehearsal

Manual restore-rehearsal template, **not a normal application stack**. Quark's
PostgreSQL 18 upgrade is complete. Do not rerun that migration or attach this
second database process to its production cluster.

Before any separately authorized future rehearsal, require current logical dump
acceptance, compatible image versions and an empty isolated test directory. The
manifest deliberately has no default data/dump directory:

| Dockhand variable | Required value |
|---|---|
| `IMMICH_PG18_PATH` | Pre-created isolated local directory; never the live PG18 path |
| `IMMICH_PG_UPGRADE_DIR` | Directory containing the reviewed `immich.dump`; mounted read-only |
| `IMMICH_DB_PASSWORD` | Encrypted secret |
| `IMMICH_DB_USERNAME`, `IMMICH_DB_NAME` | Matching dump/application identities |

`database` and the one-shot `restore` job share an internal network and publish
no ports. The restore uses `--exit-on-error`; no successful receipt is implied by
starting the database. A custom-format restore without `--create` does not replay
all original per-database properties. Verify table counts, extensions, database
properties and representative application queries before calling a rehearsal valid.

Follow [Git/CI/Dockhand operations](../../docs/operations.md). This tool is excluded from the normal application rollout. Remove a future temporary stack through Dockhand only after recording
results; keep production data, ordinary recovery archives and useful small evidence.
