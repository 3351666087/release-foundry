#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_POSTGRES_HOST:?RELEASEFOUNDRY_POSTGRES_HOST is required}"
: "${RELEASEFOUNDRY_POSTGRES_DB:?RELEASEFOUNDRY_POSTGRES_DB is required}"
: "${RELEASEFOUNDRY_POSTGRES_USER:?RELEASEFOUNDRY_POSTGRES_USER is required}"
: "${RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE:?RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_TENANT_ID:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_TENANT_ID is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_PROJECT_ID:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_PROJECT_ID is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_JOB_TYPE:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_JOB_TYPE is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_HEARTBEAT_PATH:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_HEARTBEAT_PATH is required}"
: "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_READINESS_PATH:?RELEASEFOUNDRY_PAYMENT_RECONCILIATION_READINESS_PATH is required}"

test -s "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE"
case "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC" in
  [0-2][0-9]:[0-5][0-9]) ;;
  *)
    echo "RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC must be HH:MM" >&2
    exit 64
    ;;
esac

export PGPASSWORD="$(cat "$RELEASEFOUNDRY_POSTGRES_PASSWORD_FILE")"
runtime_dir="$(dirname "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_HEARTBEAT_PATH")"
mkdir -p "$runtime_dir"

enqueue_bill_date() {
  bill_date="$1"
  job_id="china-payment-reconciliation-$bill_date"
  payload_sha="$(printf '%s' "china-payment-bill:$bill_date" | sha256sum | cut -d ' ' -f 1)"
  psql \
    --host "$RELEASEFOUNDRY_POSTGRES_HOST" \
    --username "$RELEASEFOUNDRY_POSTGRES_USER" \
    --dbname "$RELEASEFOUNDRY_POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --set tenant_id="$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_TENANT_ID" \
    --set project_id="$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_PROJECT_ID" \
    --set job_id="$job_id" \
    --set job_type="$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_JOB_TYPE" \
    --set bill_date="$bill_date" \
    --set payload_sha="$payload_sha" \
    --set max_attempts="${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_MAX_ATTEMPTS:-4}" <<'SQL'
INSERT INTO releasefoundry_worker_jobs (
    tenant_id,
    project_id,
    job_id,
    job_type,
    target_id,
    payload_sha256,
    status,
    priority,
    max_attempts,
    available_at,
    idempotency_key,
    request_id
)
VALUES (
    :'tenant_id',
    :'project_id',
    :'job_id',
    :'job_type',
    :'bill_date',
    :'payload_sha',
    'queued',
    50,
    :'max_attempts',
    now(),
    :'job_id',
    'china-payment-daily-scheduler'
)
ON CONFLICT (tenant_id, project_id, job_id) DO NOTHING;
SQL
}

printf 'ready\n' > "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_READINESS_PATH"
last_enqueued_date=""

if test "${RELEASEFOUNDRY_PAYMENT_RECONCILIATION_RUN_ON_START:-false}" = "true"; then
  last_enqueued_date="$(date -u -d 'yesterday' +%F)"
  enqueue_bill_date "$last_enqueued_date"
fi

while :; do
  now_hhmm="$(date -u +%H:%M)"
  today="$(date -u +%F)"
  if test "$now_hhmm" \> "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC" || test "$now_hhmm" = "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC"; then
    bill_date="$(date -u -d 'yesterday' +%F)"
    if test "$last_enqueued_date" != "$bill_date"; then
      enqueue_bill_date "$bill_date"
      last_enqueued_date="$bill_date"
    fi
  fi
  printf '%s schedule_utc=%s date=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_SCHEDULE_UTC" "$today" > "$RELEASEFOUNDRY_PAYMENT_RECONCILIATION_HEARTBEAT_PATH"
  sleep 30
done
