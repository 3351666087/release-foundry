#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT:?RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT is required}"
: "${RELEASEFOUNDRY_OBJECT_STORE_BUCKET:?RELEASEFOUNDRY_OBJECT_STORE_BUCKET is required}"
: "${RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_FILE:?RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_FILE is required}"
: "${RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_FILE:?RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_FILE is required}"

test -s "$RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_FILE"
test -s "$RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_FILE"

alias_name=round45
object_key="${RELEASEFOUNDRY_OBJECT_EVIDENCE_PREFIX:-evidence/a1/self-host}/round45-compose-smoke.txt"
source_file=/tmp/round45-source
download_file=/tmp/round45-download
printf '%s\n' 'releasefoundry round45 commercial compose object checksum' > "$source_file"
set -- $(sha256sum "$source_file")
expected_sha="$1"

mc alias set \
  "$alias_name" \
  "$RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT" \
  "$(cat "$RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_FILE")" \
  "$(cat "$RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_FILE")"
mc stat "$alias_name/$RELEASEFOUNDRY_OBJECT_STORE_BUCKET"
mc cp "$source_file" "$alias_name/$RELEASEFOUNDRY_OBJECT_STORE_BUCKET/$object_key"
mc stat "$alias_name/$RELEASEFOUNDRY_OBJECT_STORE_BUCKET/$object_key"
mc cp "$alias_name/$RELEASEFOUNDRY_OBJECT_STORE_BUCKET/$object_key" "$download_file"

set -- $(sha256sum "$download_file")
actual_sha="$1"
test "$actual_sha" = "$expected_sha"
printf '{"bucket":"%s","key":"%s","sha256":"%s","status":"ok"}\n' \
  "$RELEASEFOUNDRY_OBJECT_STORE_BUCKET" "$object_key" "$actual_sha"
