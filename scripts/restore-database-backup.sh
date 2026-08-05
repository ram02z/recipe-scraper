#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: restore-database-backup.sh [--local | --prod] [--db-url URL] <backup.sql.gz.age> <age-identity-file>

Default behavior decrypts and gunzips the backup to a temporary SQL file only.

Options:
  --local       Restore into local Supabase after running db reset.
  --prod        Restore into the hosted database. Requires --db-url or SUPABASE_DB_URL.
  --db-url URL  Database URL used with --prod. Optional for --local.
EOF
}

mode="extract"
db_url=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)
      mode="local"
      shift
      ;;
    --prod)
      mode="prod"
      shift
      ;;
    --db-url)
      db_url="${2:?--db-url requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

backup_file="${1:?missing encrypted backup file}"
identity_file="${2:?missing age identity file}"

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

if [[ ! -f "$backup_file" ]]; then
  printf 'backup file not found: %s\n' "$backup_file" >&2
  exit 1
fi

if [[ ! -f "$identity_file" ]]; then
  printf 'age identity file not found: %s\n' "$identity_file" >&2
  exit 1
fi

if [[ -f "$backup_file.sha256" ]]; then
  sha256sum --check "$backup_file.sha256"
fi

tmp_dir="$(mktemp -d)"
gzip_file="$tmp_dir/restore.sql.gz"
sql_file="$tmp_dir/restore.sql"

age --decrypt --identity "$identity_file" --output "$gzip_file" "$backup_file"
gunzip --keep "$gzip_file"

printf 'Restored SQL file: %s\n' "$sql_file"

case "$mode" in
  extract)
    ;;
  local)
    db_url="${db_url:-postgresql://postgres:postgres@127.0.0.1:54322/postgres}"
    supabase db reset --local --no-seed
    psql "$db_url" --file "$sql_file"
    ;;
  prod)
    db_url="${db_url:-${SUPABASE_DB_URL:-}}"
    if [[ -z "$db_url" ]]; then
      printf 'SUPABASE_DB_URL is required when using --prod\n' >&2
      exit 1
    fi
    printf 'Restoring into hosted database. Press Ctrl-C within 10 seconds to abort.\n' >&2
    sleep 10
    psql "$db_url" --file "$sql_file"
    ;;
esac
