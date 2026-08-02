#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_POSTGRES_HOST:?RELEASEFOUNDRY_POSTGRES_HOST is required}"
: "${RELEASEFOUNDRY_POSTGRES_DB:?RELEASEFOUNDRY_POSTGRES_DB is required}"
: "${RELEASEFOUNDRY_POSTGRES_USER:?RELEASEFOUNDRY_POSTGRES_USER is required}"
: "${RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE:?RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE is required}"
: "${RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH:?RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH is required}"

test -s "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE"
test -s "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH"
export PGPASSWORD="$(cat "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE")"

deadline=$(( $(date +%s) + 90 ))
while :; do
  row="$(
    psql \
      --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
      --username "$RELEASEFOUNDRY_POSTGRES_USER" \
      --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
      --tuples-only \
      --no-align \
      --set ON_ERROR_STOP=1 \
      --command "SELECT concat_ws('|', status, attempts, lease_owner_id, result_sha256 <> '') FROM releasefoundry_worker_jobs WHERE tenant_id = 'tenant_self_host' AND project_id = 'project_self_host' AND job_id = 'job_round45_restart_recovery';"
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
