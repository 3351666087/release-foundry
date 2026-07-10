#!/bin/sh
set -eu

: "${ASHR_POSTGRES_HOST:?ASHR_POSTGRES_HOST is required}"
: "${ASHR_POSTGRES_DB:?ASHR_POSTGRES_DB is required}"
: "${ASHR_POSTGRES_USER:?ASHR_POSTGRES_USER is required}"
: "${ASHR_POSTGRES_PASSWORD_FILE:?ASHR_POSTGRES_PASSWORD_FILE is required}"
: "${ASHR_POSTGRES_MIGRATION:?ASHR_POSTGRES_MIGRATION is required}"
: "${ASHR_POSTGRES_MIGRATION_DIR:=/migrations/ordered}"

test -s "$ASHR_POSTGRES_PASSWORD_FILE"
test -s "$ASHR_POSTGRES_MIGRATION"
test -d "$ASHR_POSTGRES_MIGRATION_DIR"
export PGPASSWORD="$(cat "$ASHR_POSTGRES_PASSWORD_FILE")"

apply_migration() {
  migration_path="$1"
  test -s "$migration_path"
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --file "$migration_path"
}

apply_migration "$ASHR_POSTGRES_MIGRATION"

find "$ASHR_POSTGRES_MIGRATION_DIR" -maxdepth 1 -type f -name '*.sql' |
  sort |
  while IFS= read -r migration_path; do
    apply_migration "$migration_path"
  done

tables="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.ashr_tenants'), to_regclass('public.ashr_projects'), to_regclass('public.ashr_worker_jobs'), to_regclass('public.ashr_artifact_manifests'));"
)"
test "$tables" = "ashr_tenants,ashr_projects,ashr_worker_jobs,ashr_artifact_manifests"

billing_objects="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.billing_provider_events'), to_regclass('public.billing_ledger_events'), to_regclass('public.china_payment_orders'));"
)"
test "$billing_objects" = "billing_provider_events,billing_ledger_events,china_payment_orders"

verified_trigger="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'billing_provider_events_require_verified_signature' AND NOT tgisinternal;"
)"
test "$verified_trigger" = "1"
