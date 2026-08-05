#!/usr/bin/env bash
set -euo pipefail

backup_kind="${1:?usage: create-database-backup.sh <backup-kind> <backup-dir>}"
backup_dir="${2:?usage: create-database-backup.sh <backup-kind> <backup-dir>}"

: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD is required}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required}"

timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
dump_file="$backup_dir/chorba-public-$backup_kind-$timestamp.sql"
gzip_file="$dump_file.gz"
encrypted_file="$gzip_file.age"

mkdir -p "$backup_dir"

supabase db dump \
  --linked \
  --password "$SUPABASE_DB_PASSWORD" \
  --data-only \
  --use-copy \
  --schema public \
  --file "$dump_file"
gzip -9 "$dump_file"
age --recipient "$BACKUP_AGE_RECIPIENT" --output "$encrypted_file" "$gzip_file"
sha256sum "$encrypted_file" > "$encrypted_file.sha256"

rm "$gzip_file"
