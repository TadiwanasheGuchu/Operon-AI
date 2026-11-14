#!/usr/bin/env bash
# Logical backup of the Operon database (schema, data, RLS policies, functions, grants).
#
#   DATABASE_URL=postgresql://operon_owner:...@host:5432/operon ./backup.sh /backups
#
# Writes operon-<UTC timestamp>.dump (pg_dump custom format) plus a .sha256 and a manifest with
# the migration revision and per-table row counts, which restore.sh and restore_drill.sh check.
# Run as the schema owner. Encrypt and ship the files off-host (object storage with versioning
# and a retention lock); see docs/operations/backup-and-recovery.md.
set -euo pipefail

OUT_DIR="${1:?usage: backup.sh OUTPUT_DIR}"
: "${DATABASE_URL:?set DATABASE_URL (schema owner)}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="$OUT_DIR/operon-$STAMP"

pg_dump --format=custom --compress=6 --no-password --dbname="$DATABASE_URL" --file="$BASE.dump"
sha256sum "$BASE.dump" | awk '{print $1}' > "$BASE.dump.sha256"

psql --no-password --dbname="$DATABASE_URL" -tA -v ON_ERROR_STOP=1 <<'SQL' > "$BASE.manifest"
SELECT 'revision=' || version_num FROM alembic_version;
SELECT 'rows.' || c.relname || '=' || (xpath('/row/n/text()',
       query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname), false, true, '')))[1]::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;
SQL
echo "Backup written: $BASE.dump ($(du -h "$BASE.dump" | cut -f1))"
