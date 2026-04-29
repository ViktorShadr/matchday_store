#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <backup.sql.gz|backup.sql>"
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_ROOT/docker-compose.yaml}"
VERIFY_DB="restore_verify_$(date -u +%Y%m%d%H%M%S)"

cleanup() {
    docker compose -f "$COMPOSE_FILE" exec -T db sh -c "dropdb -U \"\$DB_USER\" --if-exists \"$VERIFY_DB\"" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "$COMPOSE_FILE" exec -T db sh -c "createdb -U \"\$DB_USER\" \"$VERIFY_DB\""

if [ "${BACKUP_FILE##*.}" = "gz" ]; then
    gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -U \"\$DB_USER\" \"$VERIFY_DB\""
else
    cat "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -U \"\$DB_USER\" \"$VERIFY_DB\""
fi

docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -U \"\$DB_USER\" \"$VERIFY_DB\" -c 'SELECT COUNT(*) AS applied_migrations FROM django_migrations;'"

echo "Restore verification completed for $BACKUP_FILE"
