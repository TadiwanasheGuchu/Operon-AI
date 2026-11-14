#!/usr/bin/env bash
# Recovery drill: back up SOURCE_URL, restore into a fresh scratch database, verify, time it.
#
#   SOURCE_URL=postgresql://operon_owner:...@host/operon \
#   ADMIN_URL=postgresql://postgres:...@host/postgres \
#   ./restore_drill.sh
#
# ADMIN_URL must be able to CREATE/DROP DATABASE. The scratch database is dropped afterwards.
# Prints the measured restore time (the database part of RTO) for the drill log.
set -euo pipefail
: "${SOURCE_URL:?}" "${ADMIN_URL:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
SCRATCH="operon_restore_drill_$(date -u +%s)"
OWNER="$(psql --no-password --dbname="$SOURCE_URL" -tAc 'SELECT current_user')"
cleanup() { psql --no-password --dbname="$ADMIN_URL" -qc "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

t0=$(date +%s)
DATABASE_URL="$SOURCE_URL" "$HERE/backup.sh" "$WORK"
t1=$(date +%s)
psql --no-password --dbname="$ADMIN_URL" -qc "CREATE DATABASE $SCRATCH OWNER $OWNER"
psql --no-password --dbname="${ADMIN_URL%/*}/$SCRATCH" -qc \
  "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS citext;" >/dev/null
TARGET_URL="${SOURCE_URL%/*}/$SCRATCH" "$HERE/restore.sh" "$(ls "$WORK"/*.dump)"
t2=$(date +%s)
echo "Drill passed. Backup took $((t1 - t0))s; restore and verification took $((t2 - t1))s."
