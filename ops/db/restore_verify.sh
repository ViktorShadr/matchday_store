#!/usr/bin/env sh
set -eu

# ---------------------------------------------------------------------------
# CI mode: DATABASE_URL is set and the DB has already been restored by the
# caller. Run verification checks directly via psql against that URL.
# ---------------------------------------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
    echo "Running in CI mode with DATABASE_URL"

    MIGRATIONS=$(psql "$DATABASE_URL" -t -c 'SELECT COUNT(*) FROM django_migrations;' 2>/dev/null | tr -d ' ')
    echo "Applied migrations: ${MIGRATIONS}"
    if [ "${MIGRATIONS:-0}" -eq 0 ]; then
        echo "ERROR: No migrations found — restore may have failed"
        exit 1
    fi

    ORDERS=$(psql "$DATABASE_URL" -t -c 'SELECT COUNT(*) FROM orders_order;' | tr -d ' ')
    echo "Orders count: ${ORDERS}"
    if [ -z "${ORDERS}" ]; then
        echo "ERROR: Could not query orders_order — table missing or restore failed"
        exit 1
    fi

    PRODUCTS=$(psql "$DATABASE_URL" -t -c 'SELECT COUNT(*) FROM store_product;' | tr -d ' ')
    echo "Products count: ${PRODUCTS}"
    if [ -z "${PRODUCTS}" ]; then
        echo "ERROR: Could not query store_product — table missing or restore failed"
        exit 1
    fi

    echo "Restore verification completed successfully"
    exit 0
fi

# ---------------------------------------------------------------------------
# Local mode: docker compose is available, a backup file path is required.
# ---------------------------------------------------------------------------
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <backup.sql.gz|backup.sql>"
    echo "  or set DATABASE_URL for CI mode (no args needed)"
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
docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -U \"\$DB_USER\" \"$VERIFY_DB\" -c 'SELECT COUNT(*) AS orders FROM orders_order;'"
docker compose -f "$COMPOSE_FILE" exec -T db sh -c "psql -U \"\$DB_USER\" \"$VERIFY_DB\" -c 'SELECT COUNT(*) AS products FROM store_product;'"

echo "Restore verification completed for $BACKUP_FILE"
