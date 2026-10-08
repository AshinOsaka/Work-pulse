#!/usr/bin/env bash
# Back up WorkPulse: the MongoDB database and the encrypted object store (screenshots, report files).
#
#   scripts/backup.sh                         # development stack
#   COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml scripts/backup.sh
#
# Writes backups/<UTC timestamp>/{mongo.archive.gz,objects.tar.gz,SHA256SUMS} and deletes backups older than
# BACKUP_KEEP_DAYS (default 14). Copy the directory off the server (object storage, another region) afterwards.
#
# Screenshots stay encrypted in the backup: restoring them needs the same STORAGE_ENCRYPTION_KEY, which is NOT in the
# backup. Keep it (and JWT_SECRET) in your secret store.
set -euo pipefail
# Git Bash on Windows would rewrite container paths such as /data into Windows paths.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

out="${BACKUP_DIR:-./backups}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dir="$out/$stamp"
umask 077
mkdir -p "$dir"

echo "Backing up the database..."
# Runs inside the mongo container with its own root credentials; nothing secret is passed on this command line.
docker compose exec -T mongo sh -c 'exec mongodump --quiet \
  --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin \
  --db "$MONGO_APP_DB" --archive --gzip' > "$dir/mongo.archive.gz"

echo "Backing up object storage..."
docker compose exec -T backend tar -C /data -czf - objects > "$dir/objects.tar.gz"

# Both archives must be readable before the backup counts.
gzip -t "$dir/mongo.archive.gz"
tar -tzf - < "$dir/objects.tar.gz" > /dev/null  # stdin: GNU tar reads "C:..." as host:file
(cd "$dir" && sha256sum mongo.archive.gz objects.tar.gz > SHA256SUMS)

echo "Backup written to $dir ($(du -sh "$dir" | cut -f1))"
find "$out" -mindepth 1 -maxdepth 1 -type d -mtime "+$keep_days" -print -exec rm -rf {} +
