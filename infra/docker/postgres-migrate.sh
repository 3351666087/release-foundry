#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_POSTGRES_HOST:?RELEASEFOUNDRY_POSTGRES_HOST is required}"
: "${RELEASEFOUNDRY_POSTGRES_DB:?RELEASEFOUNDRY_POSTGRES_DB is required}"
: "${RELEASEFOUNDRY_POSTGRES_USER:?RELEASEFOUNDRY_POSTGRES_USER is required}"
: "${RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE:?RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE is required}"
: "${RELEASEFOUNDRY_POSTGRES_MIGRATION:?RELEASEFOUNDRY_POSTGRES_MIGRATION is required}"
: "${RELEASEFOUNDRY_POSTGRES_MIGRATION_DIR:=/migrations/ordered}"

test -s "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE"
test -s "$RELEASEFOUNDRY_POSTGRES_MIGRATION"
test -d "$RELEASEFOUNDRY_POSTGRES_MIGRATION_DIR"
export PGPASSWORD="$(cat "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE")"

apply_migration() {
  migration_path="$1"
  test -s "$migration_path"
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --file "$migration_path"
}

apply_migration "$RELEASEFOUNDRY_POSTGRES_MIGRATION"

find "$RELEASEFOUNDRY_POSTGRES_MIGRATION_DIR" -maxdepth 1 -type f -name '*.sql' |
  sort |
  while IFS= read -r migration_path; do
    apply_migration "$migration_path"
  done

tables="$(
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.releasefoundry_tenants'), to_regclass('public.releasefoundry_projects'), to_regclass('public.releasefoundry_worker_jobs'), to_regclass('public.releasefoundry_artifact_manifests'));"
)"
test "$tables" = "releasefoundry_tenants,releasefoundry_projects,releasefoundry_worker_jobs,releasefoundry_artifact_manifests"

billing_objects="$(
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.billing_provider_events'), to_regclass('public.billing_ledger_events'), to_regclass('public.china_payment_orders'));"
)"
test "$billing_objects" = "billing_provider_events,billing_ledger_events,china_payment_orders"

verified_trigger="$(
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'billing_provider_events_require_verified_signature' AND NOT tgisinternal;"
)"
test "$verified_trigger" = "1"

payment_security_objects="$(
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.china_payment_verification_artifacts'), to_regprocedure('public.a1_current_project_id()'), to_regprocedure('public.a1_assert_role_nobypassrls(name)'));"
)"
test "$payment_security_objects" = "china_payment_verification_artifacts,a1_current_project_id(),a1_assert_role_nobypassrls(name)"

payment_security_triggers="$(
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM pg_trigger WHERE tgname IN ('china_payment_notifications_require_artifact', 'china_payment_orders_require_verified_transition', 'china_payment_refunds_require_verified_transition', 'china_payment_verification_artifacts_append_only') AND NOT tgisinternal;"
)"
test "$payment_security_triggers" = "4"
