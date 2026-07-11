#!/bin/sh
set -eu

: "${ASHR_OBJECT_STORE_ENDPOINT:?ASHR_OBJECT_STORE_ENDPOINT is required}"
: "${ASHR_OBJECT_STORE_BUCKET:?ASHR_OBJECT_STORE_BUCKET is required}"
: "${ASHR_OBJECT_STORE_ACCESS_KEY_FILE:?ASHR_OBJECT_STORE_ACCESS_KEY_FILE is required}"
: "${ASHR_OBJECT_STORE_SECRET_KEY_FILE:?ASHR_OBJECT_STORE_SECRET_KEY_FILE is required}"

test -s "$ASHR_OBJECT_STORE_ACCESS_KEY_FILE"
test -s "$ASHR_OBJECT_STORE_SECRET_KEY_FILE"

alias_name=round45
object_key="${ASHR_OBJECT_EVIDENCE_PREFIX:-evidence/a1/self-host}/round45-compose-smoke.txt"
source_file=/tmp/round45-source
download_file=/tmp/round45-download
printf '%s\n' 'ashr round45 commercial compose object checksum' > "$source_file"
set -- $(sha256sum "$source_file")
expected_sha="$1"

mc alias set \
  "$alias_name" \
  "$ASHR_OBJECT_STORE_ENDPOINT" \
  "$(cat "$ASHR_OBJECT_STORE_ACCESS_KEY_FILE")" \
  "$(cat "$ASHR_OBJECT_STORE_SECRET_KEY_FILE")"
mc stat "$alias_name/$ASHR_OBJECT_STORE_BUCKET"
mc cp "$source_file" "$alias_name/$ASHR_OBJECT_STORE_BUCKET/$object_key"
mc stat "$alias_name/$ASHR_OBJECT_STORE_BUCKET/$object_key"
mc cp "$alias_name/$ASHR_OBJECT_STORE_BUCKET/$object_key" "$download_file"

set -- $(sha256sum "$download_file")
actual_sha="$1"
test "$actual_sha" = "$expected_sha"
printf '{"bucket":"%s","key":"%s","sha256":"%s","status":"ok"}\n' \
  "$ASHR_OBJECT_STORE_BUCKET" "$object_key" "$actual_sha"
