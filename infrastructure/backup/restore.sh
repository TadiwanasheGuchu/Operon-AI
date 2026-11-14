#!/usr/bin/env bash
# Restore a backup made by backup.sh into an EMPTY database, then verify it.
#
#   TARGET_URL=postgresql://operon_owner:...@host:5432/operon_restored ./restore.sh operon-....dump
#
# Checks the checksum before restoring, and afterwards the migration revision, per-table row
# counts (against the manifest), and that row-level security is still enabled on tenant tables.
# Exits non-zero on any mismatch. Never point TARGET_URL at a database holding live data.
set -euo pipefail

DUMP="${1:?usage: restore.sh BACKUP.dump}"
: "${TARGET_URL:?set TARGET_URL (an empty database, schema owner)}"
MANIFEST="${DUMP%.dump}.manifest"

expected_sum="$(cat "$DUMP.sha256")"
actual_sum="$(sha256sum "$DUMP" | awk '{print $1}')"
[[ "$expected_sum" == "$actual_sum" ]] || { echo "Checksum mismatch: refusing to restore." >&2; exit 2; }

existing="$(psql --no-password --dbname="$TARGET_URL" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
[[ "$existing" == "0" ]] || { echo "Target database isn't empty: refusing to restore." >&2; exit 2; }

# Extensions (pgcrypto, citext) are created when the database is provisioned, by a superuser
# (infrastructure/database/init); the schema owner can't recreate or comment on them.
LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT
pg_restore --list "$DUMP" | grep -v -E ' EXTENSION | COMMENT - EXTENSION ' > "$LIST"
pg_restore --no-password --no-owner --exit-on-error --single-transaction \
  --use-list="$LIST" --dbname="$TARGET_URL" "$DUMP"

fail=0
while IFS='=' read -r key value; do
  case "$key" in
    revision)
      got="$(psql --no-password --dbname="$TARGET_URL" -tAc 'SELECT version_num FROM alembic_version')"
      [[ "$got" == "$value" ]] || { echo "Revision: expected $value, got $got"; fail=1; } ;;
    rows.*)
      table="${key#rows.}"
      got="$(psql --no-password --dbname="$TARGET_URL" -tAc "SELECT count(*) FROM public.\"$table\"")"
      [[ "$got" == "$value" ]] || { echo "Rows in $table: expected $value, got $got"; fail=1; } ;;
  esac
done < "$MANIFEST"

unprotected="$(psql --no-password --dbname="$TARGET_URL" -tAc "
  SELECT string_agg(c.relname, ', ') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'organisation_id' AND NOT a.attisdropped
  WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity
    AND c.relname NOT IN ('audit_logs')")"
[[ -z "$unprotected" ]] || { echo "Row-level security missing on: $unprotected"; fail=1; }

[[ "$fail" == "0" ]] || { echo "Restore verification FAILED." >&2; exit 1; }
echo "Restore verified: revision, row counts and row-level security match the backup."
