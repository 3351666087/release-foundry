#!/bin/sh
set -eu

required_vars="
ASHR_GO_BACKEND
ASHR_POSTGRES_DSN
ASHR_WORKER_QUEUE
ASHR_WORKER_JOB_TYPE
ASHR_WORKER_LANE
ASHR_PAYMENT_WORKER_PROVIDER_FAMILY
ASHR_WORKER_MAX_ATTEMPTS
ASHR_WORKER_RETRY_DELAYS_SECONDS
ASHR_WORKER_DEAD_LETTER_QUEUE
ASHR_WORKER_HEARTBEAT_PATH
ASHR_WORKER_READINESS_PATH
ASHR_WORKER_SUMMARY_OUTPUT
ASHR_PAYMENT_EVIDENCE_HASH_PREFIX
"

for name in $required_vars; do
  eval "value=\${$name:-}"
  test -n "$value" || {
    echo "$name is required" >&2
    exit 64
  }
done

test "$ASHR_GO_BACKEND" = "postgres"
test "$ASHR_WORKER_QUEUE" = "$ASHR_WORKER_JOB_TYPE"
test "$ASHR_WORKER_EVIDENCE_WRITES" = "object-store-hash-only"

require_env_refs() {
  for name in "$@"; do
    eval "value=\${$name:-}"
    case "$value" in
      env:*) ;;
      *)
        echo "$name must be an env: reference" >&2
        exit 64
        ;;
    esac
  done
}

runtime_status=ready
case "$ASHR_PAYMENT_WORKER_PROVIDER_FAMILY" in
  china-wallets)
    test "${ASHR_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED:-false}" = "false"
    require_env_refs \
      ASHR_WECHAT_PAY_MERCHANT_ID_REF \
      ASHR_WECHAT_PAY_API_V3_KEY_REF \
      ASHR_WECHAT_PAY_MERCHANT_PRIVATE_KEY_REF \
      ASHR_WECHAT_PAY_PLATFORM_CERT_REF \
      ASHR_ALIPAY_APP_ID_REF \
      ASHR_ALIPAY_APP_PRIVATE_KEY_REF \
      ASHR_ALIPAY_PUBLIC_KEY_REF
    ;;
  china-bank-acquirer)
    test "${ASHR_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED:-false}" = "false"
    test "${ASHR_CHINA_ACQUIRER_MODE:-}" = "hosted-token-reference-only"
    require_env_refs \
      ASHR_CHINA_ACQUIRER_MERCHANT_ID_REF \
      ASHR_CHINA_ACQUIRER_HOSTED_ORIGIN_REF \
      ASHR_CHINA_ACQUIRER_SESSION_TOKEN_REF \
      ASHR_CHINA_ACQUIRER_SIGNING_KEY_REF
    ;;
  stripe)
    test "${ASHR_STRIPE_CHECKOUT_MODE:-}" = "hosted-checkout-reference-only"
    require_env_refs \
      ASHR_STRIPE_ACCOUNT_ID_REF \
      ASHR_STRIPE_SECRET_KEY_REF \
      ASHR_STRIPE_WEBHOOK_SECRET_REF
    if test "${ASHR_STRIPE_ENABLED:-false}" != "true"; then
      test "${ASHR_STRIPE_ENABLED:-false}" = "false"
      runtime_status=disabled
    fi
    ;;
  *)
    echo "unsupported ASHR_PAYMENT_WORKER_PROVIDER_FAMILY" >&2
    exit 64
    ;;
esac

case "$ASHR_PAYMENT_EVIDENCE_HASH_PREFIX" in
  evidence/*/sha256) ;;
  *)
    echo "ASHR_PAYMENT_EVIDENCE_HASH_PREFIX must be an evidence hash path ending in /sha256" >&2
    exit 64
    ;;
esac

worker_binary="${1:?worker binary path is required}"
test -x "$worker_binary"

runtime_dir="$(dirname "$ASHR_WORKER_HEARTBEAT_PATH")"
mkdir -p "$runtime_dir"

write_readiness() {
  readiness_tmp="${ASHR_WORKER_READINESS_PATH}.tmp"
  printf '{"status":"%s","lane":"%s","provider_family":"%s","queue":"%s","job_type":"%s","provider_network_enabled":false,"stripe_enabled":%s,"max_attempts":%s,"retry_delays_seconds":"%s","dead_letter_queue":"%s","evidence_hash_prefix":"%s"}\n' \
    "$runtime_status" \
    "$ASHR_WORKER_LANE" \
    "$ASHR_PAYMENT_WORKER_PROVIDER_FAMILY" \
    "$ASHR_WORKER_QUEUE" \
    "$ASHR_WORKER_JOB_TYPE" \
    "${ASHR_STRIPE_ENABLED:-false}" \
    "$ASHR_WORKER_MAX_ATTEMPTS" \
    "$ASHR_WORKER_RETRY_DELAYS_SECONDS" \
    "$ASHR_WORKER_DEAD_LETTER_QUEUE" \
    "$ASHR_PAYMENT_EVIDENCE_HASH_PREFIX" > "$readiness_tmp"
  mv "$readiness_tmp" "$ASHR_WORKER_READINESS_PATH"
}

write_heartbeat() {
  heartbeat_tmp="${ASHR_WORKER_HEARTBEAT_PATH}.tmp"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$ASHR_WORKER_HEARTBEAT_PATH"
}

write_readiness
if test "$runtime_status" = "disabled"; then
  while :; do
    write_heartbeat
    sleep 30
  done
fi

while :; do
  write_heartbeat
  summary_tmp="${ASHR_WORKER_SUMMARY_OUTPUT}.tmp"
  "$worker_binary" > "$summary_tmp"
  mv "$summary_tmp" "$ASHR_WORKER_SUMMARY_OUTPUT"
  write_heartbeat
  sleep "${ASHR_WORKER_RESTART_DELAY_SECONDS:-5}"
done
