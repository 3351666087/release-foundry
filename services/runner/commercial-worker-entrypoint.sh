#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_GO_BACKEND:?RELEASEFOUNDRY_GO_BACKEND is required}"
: "${RELEASEFOUNDRY_POSTGRES_DSN:?RELEASEFOUNDRY_POSTGRES_DSN is required}"
: "${RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT:?RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT is required}"
: "${RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH:?RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH is required}"

worker_binary="${1:?worker binary path is required}"
test "$RELEASEFOUNDRY_GO_BACKEND" = "postgres"
test "$worker_binary" = "/usr/local/bin/releasefoundry-worker"
test -x "$worker_binary"
case "$RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT" in
  http://*|https://*) ;;
  *) echo "commercial worker requires an S3-compatible HTTP(S) endpoint" >&2; exit 64 ;;
esac

heartbeat_dir="$(dirname "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH")"
mkdir -p "$heartbeat_dir"

while :; do
  heartbeat_tmp="${RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH}.tmp"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH"

  summary_tmp="${RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT}.tmp"
  "$worker_binary" > "$summary_tmp"
  mv "$summary_tmp" "$RELEASEFOUNDRY_WORKER_SUMMARY_OUTPUT"

  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH"
  sleep "${RELEASEFOUNDRY_WORKER_RESTART_DELAY_SECONDS:-5}"
done
