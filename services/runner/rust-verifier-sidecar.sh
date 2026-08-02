#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_VERIFIER_KEY_ENV:?RELEASEFOUNDRY_VERIFIER_KEY_ENV is required}"
: "${RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT:?RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT is required}"
: "${RELEASEFOUNDRY_VERIFIER_OBJECT_ROOT:?RELEASEFOUNDRY_VERIFIER_OBJECT_ROOT is required}"
: "${RELEASEFOUNDRY_VERIFIER_EXECUTABLE:=/usr/local/bin/releasefoundry-runtime-verify}"
: "${RELEASEFOUNDRY_VERIFIER_TIMEOUT_SECONDS:=30}"
: "${RELEASEFOUNDRY_VERIFIER_POLL_SECONDS:=2}"
: "${RELEASEFOUNDRY_VERIFIER_STALE_CLAIM_SECONDS:=300}"
: "${RELEASEFOUNDRY_VERIFIER_MAX_OBJECT_BYTES:=1073741824}"
: "${RELEASEFOUNDRY_VERIFIER_MAX_TOTAL_BYTES:=4294967296}"
: "${RELEASEFOUNDRY_VERIFIER_ONCE:=0}"

case "$RELEASEFOUNDRY_VERIFIER_KEY_ENV" in
  ''|*[!A-Z0-9_]*) echo "invalid verifier key environment name" >&2; exit 64 ;;
esac
for value in "$RELEASEFOUNDRY_VERIFIER_TIMEOUT_SECONDS" "$RELEASEFOUNDRY_VERIFIER_POLL_SECONDS" \
  "$RELEASEFOUNDRY_VERIFIER_STALE_CLAIM_SECONDS" "$RELEASEFOUNDRY_VERIFIER_MAX_OBJECT_BYTES" \
  "$RELEASEFOUNDRY_VERIFIER_MAX_TOTAL_BYTES" "$RELEASEFOUNDRY_VERIFIER_ONCE"; do
  case "$value" in
    ''|*[!0-9]*) echo "verifier numeric configuration is invalid" >&2; exit 64 ;;
  esac
done
test "$RELEASEFOUNDRY_VERIFIER_TIMEOUT_SECONDS" -gt 0
test "$RELEASEFOUNDRY_VERIFIER_POLL_SECONDS" -gt 0
test "$RELEASEFOUNDRY_VERIFIER_STALE_CLAIM_SECONDS" -ge 60
test "$RELEASEFOUNDRY_VERIFIER_MAX_OBJECT_BYTES" -gt 0
test "$RELEASEFOUNDRY_VERIFIER_MAX_TOTAL_BYTES" -ge "$RELEASEFOUNDRY_VERIFIER_MAX_OBJECT_BYTES"
test "$RELEASEFOUNDRY_VERIFIER_ONCE" = 0 || test "$RELEASEFOUNDRY_VERIFIER_ONCE" = 1
test -x "$RELEASEFOUNDRY_VERIFIER_EXECUTABLE"
command -v jq >/dev/null
command -v sha256sum >/dev/null
command -v timeout >/dev/null

inbox="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/inbox"
processing="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/processing"
accepted="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/accepted"
rejected="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/rejected"
status="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/status"
bundles="$RELEASEFOUNDRY_VERIFIER_QUEUE_ROOT/bundles"
mkdir -p "$inbox" "$processing" "$accepted" "$rejected" "$status" "$bundles" "$RELEASEFOUNDRY_VERIFIER_OBJECT_ROOT"
umask 077

atomic_status() {
  destination="$1"
  value="$2"
  temporary="${destination}.tmp.$$"
  printf '%s\n' "$value" > "$temporary"
  mv "$temporary" "$destination"
}

reject_claim() {
  claim="$1"
  basename="$2"
  code="$3"
  rm -f "$status/${basename%.json}.result.tmp.$$"
  temporary="$rejected/${basename%.json}.verification.json.tmp.$$"
  printf '{"status":"rejected","code":"%s"}\n' "$code" > "$temporary"
  mv "$temporary" "$rejected/${basename%.json}.verification.json"
  mv "$claim" "$rejected/$basename"
}

recover_stale_claims() {
  now="$(date +%s)"
  for claim in "$processing"/*.json; do
    test -f "$claim" || break
    modified="$(stat -c %Y "$claim")"
    age=$((now - modified))
    if test "$age" -ge "$RELEASEFOUNDRY_VERIFIER_STALE_CLAIM_SECONDS"; then
      basename="${claim##*/}"
      recovered="$inbox/${basename%%.processing.*}.json"
      if test -e "$recovered"; then
        mv "$claim" "$rejected/$basename.stale-duplicate"
      else
        mv "$claim" "$recovered"
      fi
    fi
  done
}

process_claim() {
  claim="$1"
  basename="$2"
  if ! jq -e '
    type == "object" and
    (keys | sort == ["bundle_file","project_id","run_id","tenant_id"]) and
    ([.tenant_id,.project_id,.run_id,.bundle_file] | all(type == "string" and length > 0))
  ' "$claim" >/dev/null 2>&1; then
    reject_claim "$claim" "$basename" "malformed_job"
    return
  fi
  tenant_id="$(jq -r .tenant_id "$claim")"
  project_id="$(jq -r .project_id "$claim")"
  run_id="$(jq -r .run_id "$claim")"
  bundle_file="$(jq -r .bundle_file "$claim")"
  case "$bundle_file" in
    ''|/*|*\\*|*/*|.*|*..*) reject_claim "$claim" "$basename" "invalid_bundle_path"; return ;;
  esac
  bundle="$bundles/$bundle_file"
  if ! test -f "$bundle" || test -L "$bundle"; then
    reject_claim "$claim" "$basename" "invalid_bundle_path"
    return
  fi
  tenant_digest="$(printf %s "$tenant_id" | sha256sum | cut -d' ' -f1)"
  project_digest="$(printf %s "$project_id" | sha256sum | cut -d' ' -f1)"
  run_digest="$(printf %s "$run_id" | sha256sum | cut -d' ' -f1)"
  result_tmp="$status/${basename%.json}.result.tmp.$$"
  if ! timeout --signal=KILL "$RELEASEFOUNDRY_VERIFIER_TIMEOUT_SECONDS" \
    "$RELEASEFOUNDRY_VERIFIER_EXECUTABLE" verify-signed-bundle-objects "$bundle" \
      --key-env "$RELEASEFOUNDRY_VERIFIER_KEY_ENV" \
      --object-root "$RELEASEFOUNDRY_VERIFIER_OBJECT_ROOT" \
      --max-object-bytes "$RELEASEFOUNDRY_VERIFIER_MAX_OBJECT_BYTES" \
      --max-total-bytes "$RELEASEFOUNDRY_VERIFIER_MAX_TOTAL_BYTES" \
      --expected-tenant-digest "$tenant_digest" \
      --expected-project-digest "$project_digest" \
      --expected-bundle-id-digest "$run_digest" > "$result_tmp" 2>/dev/null; then
    reject_claim "$claim" "$basename" "verification_failed"
    return
  fi
  if ! jq -e '
    type == "object" and
    .status == "ok" and
    .verification_level == "objects_verified" and
    .manifest_authenticated == true and
    .object_verification_performed == true and
    (.evidence_items | type == "number" and . > 0) and
    (.objects_verified == .evidence_items) and
    (.authenticated_bundle_digest | type == "string" and test("^[0-9a-f]{64}$")) and
    (.evidence_digest | type == "string" and test("^[0-9a-f]{64}$"))
  ' "$result_tmp" >/dev/null 2>&1; then
    reject_claim "$claim" "$basename" "malformed_verifier_output"
    return
  fi
  mv "$result_tmp" "$accepted/${basename%.json}.verification.json"
  mv "$claim" "$accepted/$basename"
}

drain() {
  rm -f "$status/ready"
  atomic_status "$status/draining" "draining"
  exit 0
}
trap drain INT TERM

recover_stale_claims
atomic_status "$status/ready" "ready"
while :; do
  atomic_status "$status/heartbeat" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  recover_stale_claims
  for candidate in "$inbox"/*.json; do
    test -f "$candidate" || break
    basename="${candidate##*/}"
    case "$basename" in
      ''|*[!A-Za-z0-9._-]*|.*|*..*) mv "$candidate" "$rejected/invalid-name.$$.json"; continue ;;
    esac
    claim="$processing/${basename%.json}.processing.$$.json"
    mv "$candidate" "$claim"
    process_claim "$claim" "$basename"
    atomic_status "$status/heartbeat" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  done
  if test "$RELEASEFOUNDRY_VERIFIER_ONCE" = 1; then
    exit 0
  fi
  sleep "$RELEASEFOUNDRY_VERIFIER_POLL_SECONDS" &
  wait $!
done
