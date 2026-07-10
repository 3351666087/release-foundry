#!/bin/sh
set -eu

: "${ASHR_POSTGRES_HOST:?ASHR_POSTGRES_HOST is required}"
: "${ASHR_POSTGRES_DB:?ASHR_POSTGRES_DB is required}"
: "${ASHR_POSTGRES_USER:?ASHR_POSTGRES_USER is required}"
: "${ASHR_POSTGRES_PASSWORD_FILE:?ASHR_POSTGRES_PASSWORD_FILE is required}"

test -s "$ASHR_POSTGRES_PASSWORD_FILE"
export PGPASSWORD="$(cat "$ASHR_POSTGRES_PASSWORD_FILE")"

psql \
  --host "$ASHR_POSTGRES_HOST" \
  --username "$ASHR_POSTGRES_USER" \
  --dbname "$ASHR_POSTGRES_DB" \
  --set ON_ERROR_STOP=1 <<'SQL'
INSERT INTO ashr_tenants (tenant_id, name)
VALUES ('tenant_self_host', 'Round45 tenant')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO ashr_projects (tenant_id, project_id, name)
VALUES ('tenant_self_host', 'project_self_host', 'Round45 project')
ON CONFLICT (tenant_id, project_id) DO NOTHING;

INSERT INTO ashr_worker_jobs (
    tenant_id,
    project_id,
    job_id,
    job_type,
    target_id,
    payload_sha256,
    status,
    attempts,
    max_attempts,
    lease_owner_id,
    lease_expires_at,
    available_at,
    request_id
)
VALUES (
    'tenant_self_host',
    'project_self_host',
    'job_round45_restart_recovery',
    'release_gate',
    'round45-compose',
    repeat('4', 64),
    'leased',
    1,
    3,
    'worker_before_restart',
    now() - interval '1 minute',
    now() - interval '1 minute',
    'round45-compose-smoke'
)
ON CONFLICT (tenant_id, project_id, job_id) DO UPDATE SET
    status = EXCLUDED.status,
    attempts = EXCLUDED.attempts,
    lease_owner_id = EXCLUDED.lease_owner_id,
    lease_expires_at = EXCLUDED.lease_expires_at,
    available_at = EXCLUDED.available_at,
    result_sha256 = '',
    completed_at = NULL,
    dead_lettered_at = NULL,
    updated_at = now();
SQL
