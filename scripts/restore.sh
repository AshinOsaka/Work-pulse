#!/usr/bin/env bash
# Restore a WorkPulse backup made by scripts/backup.sh. REPLACES the current database and object storage.
#
#   scripts/restore.sh backups/20261006T020000Z
#   COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml scripts/restore.sh backups/...
#
# The API and worker are stopped during the restore and started again afterwards. The restored screenshots are
# readable only with the STORAGE_ENCRYPTION_KEY that was in use when they were taken.
set -euo pipefail
# Git Bash on Windows would rewrite container paths such as /data into Windows paths.
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

dir="${1:?usage: scripts/restore.sh <backup directory>}"
(cd "$dir" && sha256sum -c --quiet SHA256SUMS) || { echo "Checksums don't match; not restoring." >&2; exit 1; }

if [ "${FORCE:-}" != "1" ]; then
  read -r -p "This replaces ALL current WorkPulse data with $dir. Type 'restore' to continue: " answer
  [ "$answer" = "restore" ] || { echo "Cancelled."; exit 1; }
fi

echo "Stopping the API and worker..."
docker compose stop backend worker

echo "Restoring the database..."
docker compose exec -T mongo sh -c 'exec mongorestore --quiet --drop \
  --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin \
  --nsInclude "$MONGO_APP_DB.*" --archive --gzip' < "$dir/mongo.archive.gz"

echo "Restoring object storage..."
# A one-off container with the same volume (the API stays stopped); old objects are replaced, not merged.
docker compose run --rm --no-deps -T --entrypoint sh backend -c \
  'find /data/objects -mindepth 1 -delete && tar -C /data -xzf -' < "$dir/objects.tar.gz"

echo "Starting the API and worker..."
docker compose up -d backend worker
echo "Restore complete."
