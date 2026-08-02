#!/bin/sh
set -eu

required_vars="
RELEASEFOUNDRY_GO_BACKEND
RELEASEFOUNDRY_POSTGRES_DSN
RELEASEFOUNDRY_WORKER_QUEUE
RELEASEFOUNDRY_WORKER_JOB_TYPE
RELEASEFOUNDRY_WORKER_LANE
RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY
RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS
RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS
RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE
RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH
RELEASEFOUNDRY_WORKER_READINESS_PATH
RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT
RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX
"

for name in $required_vars; do
  eval "value=\${$name:-}"
  test -n "$value" || {
    echo "$name is required" >&2
    exit 64
  }
done

test "$RELEASEFOUNDRY_GO_BACKEND" = "postgres"
test "$RELEASEFOUNDRY_WORKER_QUEUE" = "$RELEASEFOUNDRY_WORKER_JOB_TYPE"
test "$RELEASEFOUNDRY_WORKER_EVIDENCE_WRITES" = "object-store-hash-only"

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
case "$RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY" in
  china-wallets)
    test "${RELEASEFOUNDRY_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED:-false}" = "false"
    require_env_refs \
      RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_ID_REF \
      RELEASEFOUNDRY_WECHAT_PAY_API_V3_KEY_REF \
      RELEASEFOUNDRY_WECHAT_PAY_MERCHANT_PRIVATE_KEY_REF \
      RELEASEFOUNDRY_WECHAT_PAY_PLATFORM_CERT_REF \
      RELEASEFOUNDRY_ALIPAY_APP_ID_REF \
      RELEASEFOUNDRY_ALIPAY_APP_PRIVATE_KEY_REF \
      RELEASEFOUNDRY_ALIPAY_PUBLIC_KEY_REF
    ;;
  china-bank-acquirer)
    test "${RELEASEFOUNDRY_CHINA_PAYMENT_PROVIDER_NETWORK_ENABLED:-false}" = "false"
    test "${RELEASEFOUNDRY_CHINA_ACQUIRER_MODE:-}" = "hosted-token-reference-only"
    require_env_refs \
      RELEASEFOUNDRY_CHINA_ACQUIRER_MERCHANT_ID_REF \
      RELEASEFOUNDRY_CHINA_ACQUIRER_HOSTED_ORIGIN_REF \
      RELEASEFOUNDRY_CHINA_ACQUIRER_SESSION_TOKEN_REF \
      RELEASEFOUNDRY_CHINA_ACQUIRER_SIGNING_KEY_REF
    ;;
  stripe)
    test "${RELEASEFOUNDRY_STRIPE_CHECKOUT_MODE:-}" = "hosted-checkout-reference-only"
    require_env_refs \
      RELEASEFOUNDRY_STRIPE_ACCOUNT_ID_REF \
      RELEASEFOUNDRY_STRIPE_SECRET_KEY_REF \
      RELEASEFOUNDRY_STRIPE_WEBHOOK_SECRET_REF
    if test "${RELEASEFOUNDRY_STRIPE_ENABLED:-false}" != "true"; then
      test "${RELEASEFOUNDRY_STRIPE_ENABLED:-false}" = "false"
      runtime_status=disabled
    fi
    ;;
  *)
    echo "unsupported RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY" >&2
    exit 64
    ;;
esac

case "$RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX" in
  evidence/*/sha256) ;;
  *)
    echo "RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX must be an evidence hash path ending in /sha256" >&2
    exit 64
    ;;
esac

worker_binary="${1:?worker binary path is required}"
test -x "$worker_binary"

runtime_dir="$(dirname "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH")"
mkdir -p "$runtime_dir"

write_readiness() {
  readiness_tmp="${RELEASEFOUNDRY_WORKER_READINESS_PATH}.tmp"
  printf '{"status":"%s","lane":"%s","provider_family":"%s","queue":"%s","job_type":"%s","provider_network_enabled":false,"stripe_enabled":%s,"max_attempts":%s,"retry_delays_seconds":"%s","dead_letter_queue":"%s","evidence_hash_prefix":"%s"}\n' \
    "$runtime_status" \
    "$RELEASEFOUNDRY_WORKER_LANE" \
    "$RELEASEFOUNDRY_PAYMENT_WORKER_PROVIDER_FAMILY" \
    "$RELEASEFOUNDRY_WORKER_QUEUE" \
    "$RELEASEFOUNDRY_WORKER_JOB_TYPE" \
    "${RELEASEFOUNDRY_STRIPE_ENABLED:-false}" \
    "$RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS" \
    "$RELEASEFOUNDRY_WORKER_RETRY_DELAYS_SECONDS" \
    "$RELEASEFOUNDRY_WORKER_DEAD_LETTER_QUEUE" \
    "$RELEASEFOUNDRY_PAYMENT_EVIDENCE_HASH_PREFIX" > "$readiness_tmp"
  mv "$readiness_tmp" "$RELEASEFOUNDRY_WORKER_READINESS_PATH"
}

write_heartbeat() {
  heartbeat_tmp="${RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH}.tmp"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH"
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
  summary_tmp="${RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT}.tmp"
  "$worker_binary" > "$summary_tmp"
  mv "$summary_tmp" "$RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT"
  write_heartbeat
  sleep "${RELEASEFOUNDRY_WORKER_RESTART_DELAY_SECONDS:-5}"
done
