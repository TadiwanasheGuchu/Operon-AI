# Backup and recovery

## Targets

| | Target | How |
|---|---|---|
| **RPO** (data you can lose) | **≤ 5 minutes** | Managed Postgres point-in-time recovery: continuous WAL archiving |
| **RTO** (time to service) | **≤ 1 hour** | Restore to a point in time, point the API at it, run the health gate |
| Logical backup | Daily, 35 days retained; monthly for 12 months | `infrastructure/backup/backup.sh` → encrypted object storage with versioning and a retention lock |
| Drill | Monthly, and after any schema-heavy release | `infrastructure/backup/restore_drill.sh` |

Postgres is the system of record. Redis holds only short-lived state: rate-limit counters, SSO
sign-in state, discovery caches. Losing Redis signs nobody out and loses no business data.
Temporal keeps its own history, but workflow state is rebuilt from `workflow_executions`
(ADR 0012), so the Temporal database can be restored separately or recreated empty. The sweep
re-drives anything in flight.

## Layer 1: point-in-time recovery (primary)

Use the provider's PITR on the managed database (RDS, Cloud SQL, Azure Flexible Server, Crunchy
Bridge, Neon) with at least 7 days of WAL. For self-hosted Postgres, use pgBackRest or WAL-G:
take a full backup weekly, a differential daily, and archive WAL continuously to object storage.

To recover from a bad deploy or an accidental deletion:

1. Find the target time: the audit log (`occurred_at`) or the deploy time.
2. Restore to a **new** instance at that time. Never restore over the live one.
3. Verify it with the checks in `restore.sh`: migration revision, row counts sensible, RLS
   enabled.
4. Switch `OPERON_DATABASE_URL` and `OPERON_MIGRATIONS_DATABASE_URL`, then run
   `deploy.sh <env> <current version>`. Health checks gate the switch.
5. Keep the old instance read-only for investigation, then retire it.

## Layer 2: verified logical backups (portable)

```bash
DATABASE_URL=postgresql://operon_owner:…@db/operon infrastructure/backup/backup.sh /backups
```

This writes three files:

- `operon-<timestamp>.dump`: `pg_dump` custom format, containing schema, data, RLS policies,
  functions and grants;
- `.sha256`;
- `.manifest`: the migration revision and per-table row counts.

Encrypt the files and copy them off the host.

Restore into an **empty** database. Extensions are created when the database is provisioned
(`infrastructure/database/init`).

```bash
TARGET_URL=postgresql://operon_owner:…@db/operon_restored infrastructure/backup/restore.sh operon-….dump
```

`restore.sh` refuses to run if the checksum doesn't match or the target isn't empty. It restores
in a single transaction. Afterwards it checks:

- the migration revision;
- every table's row count against the manifest;
- that RLS is still enabled on the tenant tables.

## Drill results

`restore_drill.sh` backs up a source, restores it into a scratch database, verifies it, times it,
and drops the scratch database.

| Date | Data | Dump | Backup | Restore + verify | Result |
|---|---|---|---|---|---|
| 2026-11-13 | Development database | small | 0 s | 4 s | Pass |
| 2026-11-13 | Load-test database: 397 MB, 3 orgs × 10k SKUs, 824k sales rows | 21 MB | 3 s | 10 s | Pass |

Extrapolating linearly, 50 organisations at that size (about 6.5 GB) would take about 3 minutes to
restore logically, well inside the RTO. PITR restore time depends on the provider and is
measured in the first staging drill.

Record each drill: date, data size, times, result, and any problem found.

## Single-tenant recovery

To recover one organisation's data without rolling back everyone:

1. Restore to a scratch database (PITR or logical).
2. Export the organisation from it: the `POST /organisations/current/export` format, or SQL.
3. Re-apply the rows you need in a reviewed migration script.

Never hand-edit production (CLAUDE.md §10).
