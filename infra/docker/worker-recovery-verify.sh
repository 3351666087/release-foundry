#!/bin/sh
set -eu

: "${ASHR_POSTGRES_HOST:?ASHR_POSTGRES_HOST is required}"
: "${ASHR_POSTGRES_DB:?ASHR_POSTGRES_DB is required}"
: "${ASHR_POSTGRES_USER:?ASHR_POSTGRES_USER is required}"
: "${ASHR_POSTGRES_PASSWORD_FILE:?ASHR_POSTGRES_PASSWORD_FILE is required}"
: "${ASHR_WORKER_HEARTBEAT_PATH:?ASHR_WORKER_HEARTBEAT_PATH is required}"

test -s "$ASHR_POSTGRES_PASSWORD_FILE"
test -s "$ASHR_WORKER_HEARTBEAT_PATH"
export PGPASSWORD="$(cat "$ASHR_POSTGRES_PASSWORD_FILE")"

deadline=$(( $(date +%s) + 90 ))
while :; do
  row="$(
    psql \
      --host "$ASHR_POSTGRES_HOST" \
      --username "$ASHR_POSTGRES_USER" \
      --dbname "$ASHR_POSTGRES_DB" \
      --tuples-only \
      --no-align \
      --set ON_ERROR_STOP=1 \
      --command "SELECT concat_ws('|', status, attempts, lease_owner_id, result_sha256 <> '') FROM ashr_worker_jobs WHERE tenant_id = 'tenant_self_host' AND project_id = 'project_self_host' AND job_id = 'job_round45_restart_recovery';"
  )"
  case "$row" in
    completed\|2\|*\|t)
      printf '{"job_id":"job_round45_restart_recovery","row":"%s","status":"ok"}\n' "$row"
      exit 0
      ;;
  esac
  test "$(date +%s)" -lt "$deadline"
  sleep 2
done
