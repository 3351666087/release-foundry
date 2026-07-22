#!/bin/sh
set -eu

: "${ASHR_POSTGRES_HOST:?ASHR_POSTGRES_HOST is required}"
: "${ASHR_POSTGRES_DB:?ASHR_POSTGRES_DB is required}"
: "${ASHR_POSTGRES_USER:?ASHR_POSTGRES_USER is required}"
: "${ASHR_POSTGRES_PASSWORD_FILE:?ASHR_POSTGRES_PASSWORD_FILE is required}"
: "${ASHR_POSTGRES_RUNTIME_PASSWORD_FILE:?ASHR_POSTGRES_RUNTIME_PASSWORD_FILE is required}"
: "${ASHR_POSTGRES_MIGRATION:?ASHR_POSTGRES_MIGRATION is required}"
: "${ASHR_POSTGRES_MIGRATION_DIR:=/migrations/ordered}"

test -s "$ASHR_POSTGRES_PASSWORD_FILE"
test -s "$ASHR_POSTGRES_RUNTIME_PASSWORD_FILE"
test -s "$ASHR_POSTGRES_MIGRATION"
test -d "$ASHR_POSTGRES_MIGRATION_DIR"
export PGPASSWORD="$(cat "$ASHR_POSTGRES_PASSWORD_FILE")"

ensure_runtime_roles() {
  # Identity migrations grant narrowly-scoped functions to these roles. Create
  # them before the first migration so a clean cluster has the same security
  # posture as the live integration fixtures.
  ASHR_POSTGRES_RUNTIME_SECRET="$(cat "$ASHR_POSTGRES_RUNTIME_PASSWORD_FILE")"
  export ASHR_POSTGRES_RUNTIME_SECRET
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 <<'SQL'
\getenv runtime_password ASHR_POSTGRES_RUNTIME_SECRET

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    CREATE ROLE a1_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_security_ticket_issuer') THEN
    CREATE ROLE a1_security_ticket_issuer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ashr_identity_runtime') THEN
    CREATE ROLE ashr_identity_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
END
$$;

ALTER ROLE a1_runtime
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE a1_security_ticket_issuer
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE ashr_identity_runtime
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS
  PASSWORD :'runtime_password';
GRANT a1_runtime TO ashr_identity_runtime;
GRANT USAGE ON SCHEMA public TO ashr_identity_runtime;
REVOKE CREATE ON SCHEMA public FROM ashr_identity_runtime;
SQL
  unset ASHR_POSTGRES_RUNTIME_SECRET
}

ensure_runtime_roles

ensure_migration_ledger() {
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS ashr_schema_migrations (
  migration_name TEXT PRIMARY KEY,
  migration_sha256 TEXT NOT NULL CHECK (migration_sha256 ~ '^[0-9a-f]{64}$'),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON TABLE ashr_schema_migrations FROM PUBLIC;
SQL
}

ensure_migration_ledger

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

apply_ordered_migration() {
  migration_path="$1"
  migration_name="$(basename "$migration_path")"
  migration_sha256="$(sha256sum "$migration_path" | awk '{print $1}')"
  case "$migration_name" in
    *[!A-Za-z0-9._-]*)
      printf '%s\n' "Refusing unsafe migration filename" >&2
      exit 6
      ;;
  esac
  recorded_sha256="$(
    psql \
      --host "$ASHR_POSTGRES_HOST" \
      --username "$ASHR_POSTGRES_USER" \
      --dbname "$ASHR_POSTGRES_DB" \
      --tuples-only \
      --no-align \
      --set ON_ERROR_STOP=1 \
      --command "SELECT migration_sha256 FROM ashr_schema_migrations WHERE migration_name = '$migration_name';"
  )"
  if [ -n "$recorded_sha256" ]; then
    if [ "$recorded_sha256" != "$migration_sha256" ]; then
      printf '%s\n' "Refusing changed applied migration: $migration_name" >&2
      exit 6
    fi
    return
  fi

  apply_migration "$migration_path"
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --command "INSERT INTO ashr_schema_migrations (migration_name, migration_sha256) VALUES ('$migration_name', '$migration_sha256');"
}

apply_migration "$ASHR_POSTGRES_MIGRATION"

find "$ASHR_POSTGRES_MIGRATION_DIR" -maxdepth 1 -type f -name '*.sql' |
  sort |
  while IFS= read -r migration_path; do
    apply_ordered_migration "$migration_path"
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

payment_security_objects="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT concat_ws(',', to_regclass('public.china_payment_verification_artifacts'), to_regprocedure('public.a1_current_project_id()'), to_regprocedure('public.a1_assert_role_nobypassrls(name)'));"
)"
test "$payment_security_objects" = "china_payment_verification_artifacts,a1_current_project_id(),a1_assert_role_nobypassrls(name)"

payment_security_triggers="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM pg_trigger WHERE tgname IN ('china_payment_notifications_require_artifact', 'china_payment_orders_require_verified_transition', 'china_payment_refunds_require_verified_transition', 'china_payment_verification_artifacts_append_only') AND NOT tgisinternal;"
)"
test "$payment_security_triggers" = "4"

runtime_roles="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM pg_roles WHERE rolname IN ('a1_runtime', 'a1_security_ticket_issuer') AND rolcanlogin = false AND rolsuper = false AND rolcreatedb = false AND rolcreaterole = false AND rolbypassrls = false;"
)"
test "$runtime_roles" = "2"

identity_runtime_role="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT CASE WHEN rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND rolinherit AND NOT rolbypassrls AND pg_has_role(rolname, 'a1_runtime', 'MEMBER') AND has_schema_privilege(rolname, 'public', 'USAGE') AND NOT has_schema_privilege(rolname, 'public', 'CREATE') THEN 'ready' ELSE 'not_ready' END FROM pg_roles WHERE rolname = 'ashr_identity_runtime';"
)"
test "$identity_runtime_role" = "ready"

ordered_migrations="$(
  find "$ASHR_POSTGRES_MIGRATION_DIR" -maxdepth 1 -type f -name '*.sql' | wc -l | tr -d ' '
)"
recorded_migrations="$(
  psql \
    --host "$ASHR_POSTGRES_HOST" \
    --username "$ASHR_POSTGRES_USER" \
    --dbname "$ASHR_POSTGRES_DB" \
    --tuples-only \
    --no-align \
    --set ON_ERROR_STOP=1 \
    --command "SELECT COUNT(*) FROM ashr_schema_migrations;"
)"
test "$recorded_migrations" = "$ordered_migrations"
