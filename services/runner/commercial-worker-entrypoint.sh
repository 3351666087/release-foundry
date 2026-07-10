#!/bin/sh
set -eu

: "${ASHR_GO_BACKEND:?ASHR_GO_BACKEND is required}"
: "${ASHR_POSTGRES_DSN:?ASHR_POSTGRES_DSN is required}"
: "${ASHR_OBJECT_STORE_ENDPOINT:?ASHR_OBJECT_STORE_ENDPOINT is required}"
: "${ASHR_WORKER_HEARTBEAT_PATH:?ASHR_WORKER_HEARTBEAT_PATH is required}"

worker_binary="${1:?worker binary path is required}"
test "$ASHR_GO_BACKEND" = "postgres"
test "$worker_binary" = "/usr/local/bin/ashr-worker"
test -x "$worker_binary"
case "$ASHR_OBJECT_STORE_ENDPOINT" in
  http://*|https://*) ;;
  *) echo "commercial worker requires an S3-compatible HTTP(S) endpoint" >&2; exit 64 ;;
esac

heartbeat_dir="$(dirname "$ASHR_WORKER_HEARTBEAT_PATH")"
mkdir -p "$heartbeat_dir"

while :; do
  heartbeat_tmp="${ASHR_WORKER_HEARTBEAT_PATH}.tmp"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$ASHR_WORKER_HEARTBEAT_PATH"

  summary_tmp="${ASHR_WORKER_SUMMARY_OUTPUT}.tmp"
  "$worker_binary" > "$summary_tmp"
  mv "$summary_tmp" "$ASHR_WORKER_SUMMARY_OUTPUT"

  date -u +%Y-%m-%dT%H:%M:%SZ > "$heartbeat_tmp"
  mv "$heartbeat_tmp" "$ASHR_WORKER_HEARTBEAT_PATH"
  sleep "${ASHR_WORKER_RESTART_DELAY_SECONDS:-5}"
done
