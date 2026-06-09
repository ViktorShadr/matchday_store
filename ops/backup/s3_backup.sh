#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_ENV_FILE="$SCRIPT_DIR/s3_backup.env"

TMP_DIR=""
UPLOADED_POSTGRES=false
UPLOADED_MEDIA=false
BACKUP_TIER=""

usage() {
    cat <<'USAGE'
Usage: ops/backup/s3_backup.sh <daily|weekly|monthly>

Required configuration can be provided through environment variables or an env file.
By default the script reads ops/backup/s3_backup.env when it exists.
Set BACKUP_ENV_FILE=/path/to/backup_s3.env to use another file.
USAGE
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

die() {
    trap - ERR
    log "ERROR: $*"
    exit 1
}

report_error() {
    local status=$?
    local line=${BASH_LINENO[0]:-unknown}
    log "ERROR: command failed near line $line with exit code $status"
}
trap report_error ERR

cleanup() {
    local status=$?

    if [[ -z "$TMP_DIR" || ! -d "$TMP_DIR" ]]; then
        return
    fi

    if (( status == 0 )) || [[ "$UPLOADED_POSTGRES" == true && "$UPLOADED_MEDIA" == true ]]; then
        rm -rf -- "$TMP_DIR"
        log "Temporary files removed"
        return
    fi

    log "Backup failed; temporary files kept for inspection: $TMP_DIR"
}
trap cleanup EXIT

load_env_file() {
    local env_file=$1
    local line key value first_char last_char mode go_bits

    [[ -f "$env_file" ]] || die "Env file not found: $env_file"
    [[ -r "$env_file" ]] || die "Env file is not readable: $env_file"

    mode="$(stat -c '%a' "$env_file" 2>/dev/null || true)"
    if [[ -n "$mode" && ${#mode} -ge 3 ]]; then
        go_bits="${mode: -2}"
        if [[ "$go_bits" != "00" ]]; then
            log "WARNING: env file is readable by group/others ($mode). Recommended: chmod 600 $env_file"
        fi
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

        if [[ "$line" =~ ^export[[:space:]]+(.+)$ ]]; then
            line="${BASH_REMATCH[1]}"
        fi

        [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || die "Invalid env line in $env_file: $line"

        key="${line%%=*}"
        value="${line#*=}"

        if (( ${#value} >= 2 )); then
            first_char="${value:0:1}"
            last_char="${value: -1}"
            if [[ "$first_char" == "$last_char" && ( "$first_char" == '"' || "$first_char" == "'" ) ]]; then
                value="${value:1:${#value}-2}"
            fi
        fi

        export "$key=$value"
    done < "$env_file"
}

load_configuration() {
    if [[ -n "${BACKUP_ENV_FILE:-}" ]]; then
        load_env_file "$BACKUP_ENV_FILE"
    elif [[ -f "$DEFAULT_ENV_FILE" ]]; then
        load_env_file "$DEFAULT_ENV_FILE"
    fi

    if [[ -z "${COMPOSE_FILE:-}" ]]; then
        if [[ -f "$PROJECT_ROOT/docker-compose.prod.yml" ]]; then
            COMPOSE_FILE="$PROJECT_ROOT/docker-compose.prod.yml"
        else
            COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yaml"
        fi
        export COMPOSE_FILE
    fi

    APP_NAME="${APP_NAME:-matchday_store}"
    POSTGRES_SERVICE="${POSTGRES_SERVICE:-${POSTGRES_CONTAINER:-db}}"
    MEDIA_SOURCE="${MEDIA_SOURCE:-container}"
    MEDIA_SERVICE="${MEDIA_SERVICE:-web}"
    MEDIA_PATH="${MEDIA_PATH:-/app/media}"
    RETENTION_DAILY_DAYS="${RETENTION_DAILY_DAYS:-14}"
    RETENTION_WEEKLY_WEEKS="${RETENTION_WEEKLY_WEEKS:-8}"
    RETENTION_MONTHLY_MONTHS="${RETENTION_MONTHLY_MONTHS:-6}"
    AWS_EC2_METADATA_DISABLED=true
    AWS_PAGER=""

    export APP_NAME POSTGRES_SERVICE MEDIA_SOURCE MEDIA_SERVICE MEDIA_PATH
    export RETENTION_DAILY_DAYS RETENTION_WEEKLY_WEEKS RETENTION_MONTHLY_MONTHS
    export AWS_EC2_METADATA_DISABLED AWS_PAGER
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_var() {
    local name=$1
    [[ -n "${!name:-}" ]] || die "Required environment variable is not set: $name"
}

validate_configuration() {
    local required_vars=(
        S3_ENDPOINT_URL
        S3_BUCKET_NAME
        S3_REGION
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
        POSTGRES_SERVICE
        DB_NAME
        DB_USER
        DB_PASSWORD
        MEDIA_PATH
    )
    local var

    case "$BACKUP_TIER" in
        daily|weekly|monthly)
            ;;
        *)
            die "Backup tier must be daily, weekly, or monthly; got: $BACKUP_TIER"
            ;;
    esac

    for var in "${required_vars[@]}"; do
        require_var "$var"
    done

    case "$MEDIA_SOURCE" in
        container)
            require_var MEDIA_SERVICE
            ;;
        host)
            ;;
        *)
            die "MEDIA_SOURCE must be 'container' or 'host', got: $MEDIA_SOURCE"
            ;;
    esac

    require_command aws
    require_command basename
    require_command cut
    require_command date
    require_command docker
    require_command du
    require_command gzip
    require_command mktemp
    require_command sed
    require_command tar
    require_command tr

    docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is not available"
    date -u -d '1 day ago' '+%Y-%m-%dT%H:%M:%SZ' >/dev/null 2>&1 || die "GNU date with -d support is required"
}

COMPOSE_ARGS=()

build_compose_args() {
    local compose_file
    local old_ifs=$IFS

    IFS=':'
    local -a compose_args_raw
    read -r -a compose_args_raw <<< "$COMPOSE_FILE"
    IFS=$old_ifs

    COMPOSE_ARGS=()
    for compose_file in "${compose_args_raw[@]}"; do
        [[ -n "$compose_file" ]] || continue
        [[ -f "$compose_file" ]] || die "Compose file not found: $compose_file"
        COMPOSE_ARGS+=("-f" "$compose_file")
    done

    (( ${#COMPOSE_ARGS[@]} > 0 )) || die "No compose files configured"
}

compose() {
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

aws_cli() {
    AWS_DEFAULT_REGION="$S3_REGION" aws \
        --endpoint-url "$S3_ENDPOINT_URL" \
        --region "$S3_REGION" \
        "$@"
}

file_size() {
    du -h "$1" | cut -f1
}

assert_non_empty_file() {
    local file=$1
    [[ -s "$file" ]] || die "Backup archive was not created or is empty: $file"
}

create_postgres_backup() {
    local output=$1

    log "Creating PostgreSQL backup from service '$POSTGRES_SERVICE', database '$DB_NAME'"

    printf '%s\n' "$DB_PASSWORD" |
        compose exec -T "$POSTGRES_SERVICE" sh -c '
            set -eu
            IFS= read -r PGPASSWORD
            export PGPASSWORD
            db_user=$1
            db_name=$2
            pg_dump --format=plain --no-owner --no-acl --encoding=UTF8 --username="$db_user" --dbname="$db_name"
        ' sh "$DB_USER" "$DB_NAME" |
        gzip -9 > "$output"

    assert_non_empty_file "$output"
    log "PostgreSQL archive created: $output ($(file_size "$output"))"
}

create_media_backup_from_container() {
    local output=$1

    log "Creating media backup from service '$MEDIA_SERVICE', path '$MEDIA_PATH'"

    compose exec -T "$MEDIA_SERVICE" sh -c '
        set -eu
        media_path=$1
        if [ ! -d "$media_path" ]; then
            printf "Media path not found in container: %s\n" "$media_path" >&2
            exit 1
        fi
        parent=$(dirname "$media_path")
        base=$(basename "$media_path")
        tar -C "$parent" -czf - "$base"
    ' sh "$MEDIA_PATH" > "$output"

    assert_non_empty_file "$output"
    log "Media archive created: $output ($(file_size "$output"))"
}

create_media_backup_from_host() {
    local output=$1
    local parent base

    [[ -d "$MEDIA_PATH" ]] || die "Media path not found on host: $MEDIA_PATH"

    parent="$(cd -- "$(dirname -- "$MEDIA_PATH")" && pwd -P)"
    base="$(basename -- "$MEDIA_PATH")"

    log "Creating media backup from host path '$MEDIA_PATH'"
    tar -C "$parent" -czf "$output" "$base"

    assert_non_empty_file "$output"
    log "Media archive created: $output ($(file_size "$output"))"
}

create_media_backup() {
    local output=$1

    case "$MEDIA_SOURCE" in
        container)
            create_media_backup_from_container "$output"
            ;;
        host)
            create_media_backup_from_host "$output"
            ;;
    esac
}

check_s3_access() {
    log "Checking S3 bucket access: s3://$S3_BUCKET_NAME"
    aws_cli s3api head-bucket --bucket "$S3_BUCKET_NAME" >/dev/null
}

upload_archive() {
    local file=$1
    local key=$2
    local uri="s3://$S3_BUCKET_NAME/$key"

    log "Uploading $(basename -- "$file") to $uri"
    aws_cli s3 cp "$file" "$uri" --only-show-errors
    aws_cli s3api head-object --bucket "$S3_BUCKET_NAME" --key "$key" >/dev/null
    rm -f -- "$file"
    log "Uploaded and removed local archive: $uri"
}

retention_cutoff() {
    local cutoff

    case "$BACKUP_TIER" in
        daily)
            cutoff="$(date -u -d "$RETENTION_DAILY_DAYS days ago" '+%Y-%m-%dT%H:%M:%SZ')"
            ;;
        weekly)
            cutoff="$(date -u -d "$((RETENTION_WEEKLY_WEEKS * 7)) days ago" '+%Y-%m-%dT%H:%M:%SZ')"
            ;;
        monthly)
            cutoff="$(date -u -d "$RETENTION_MONTHLY_MONTHS months ago" '+%Y-%m-%dT%H:%M:%SZ')"
            ;;
    esac

    printf '%s\n' "$cutoff"
}

delete_expired_objects() {
    local prefix=$1
    local cutoff=$2
    local list_output key
    local keys=()

    log "Applying retention to s3://$S3_BUCKET_NAME/$prefix/; deleting objects older than $cutoff"

    list_output="$(aws_cli s3api list-objects-v2 \
        --bucket "$S3_BUCKET_NAME" \
        --prefix "$prefix/" \
        --query "Contents[?LastModified<='$cutoff'].Key" \
        --output text)"

    mapfile -t keys < <(printf '%s\n' "$list_output" | tr '\t' '\n' | sed '/^$/d;/^None$/d')

    if (( ${#keys[@]} == 0 )); then
        log "No expired objects found under $prefix/"
        return
    fi

    for key in "${keys[@]}"; do
        [[ "$key" == "$prefix/"* ]] || die "Refusing to delete unexpected S3 key outside prefix '$prefix/': $key"
        log "Deleting expired S3 object: s3://$S3_BUCKET_NAME/$key"
        aws_cli s3 rm "s3://$S3_BUCKET_NAME/$key" --only-show-errors
    done
}

apply_retention() {
    local cutoff
    cutoff="$(retention_cutoff)"

    delete_expired_objects "backups/postgres/$BACKUP_TIER" "$cutoff"
    delete_expired_objects "backups/media/$BACKUP_TIER" "$cutoff"
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        usage
        exit 0
    fi

    if (( $# > 1 )); then
        usage
        exit 2
    fi

    BACKUP_TIER="${1:-${BACKUP_TIER:-daily}}"

    load_configuration
    validate_configuration
    build_compose_args

    umask 077
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/matchday-s3-backup.XXXXXX")"

    local timestamp postgres_file media_file postgres_key media_key
    timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    postgres_file="$TMP_DIR/${APP_NAME}_postgres_${BACKUP_TIER}_${timestamp}.sql.gz"
    media_file="$TMP_DIR/${APP_NAME}_media_${BACKUP_TIER}_${timestamp}.tar.gz"
    postgres_key="backups/postgres/$BACKUP_TIER/$(basename -- "$postgres_file")"
    media_key="backups/media/$BACKUP_TIER/$(basename -- "$media_file")"

    log "Starting $BACKUP_TIER S3 backup"
    log "Using compose file(s): $COMPOSE_FILE"
    log "Using temporary directory: $TMP_DIR"

    check_s3_access

    create_postgres_backup "$postgres_file"
    upload_archive "$postgres_file" "$postgres_key"
    UPLOADED_POSTGRES=true

    create_media_backup "$media_file"
    upload_archive "$media_file" "$media_key"
    UPLOADED_MEDIA=true

    apply_retention

    log "Backup completed successfully"
}

main "$@"
