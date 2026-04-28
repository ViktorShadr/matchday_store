#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$PROJECT_ROOT/docker-compose.yaml}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_PATH="$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose -f "$COMPOSE_FILE" exec -T db sh -c 'pg_dump -U "$DB_USER" "$DB_NAME"' | gzip -9 > "$BACKUP_PATH"

find "$BACKUP_DIR" -type f -name "postgres_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete

echo "Backup created: $BACKUP_PATH"
