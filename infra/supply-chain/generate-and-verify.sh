#!/bin/sh
set -eu

: "${ASHR_RELEASE_API_IMAGE:?ASHR_RELEASE_API_IMAGE must be repository@sha256:digest}"
: "${ASHR_RELEASE_WORKER_IMAGE:?ASHR_RELEASE_WORKER_IMAGE must be repository@sha256:digest}"
: "${ASHR_RELEASE_IDENTITY_DELIVERY_IMAGE:?ASHR_RELEASE_IDENTITY_DELIVERY_IMAGE must be repository@sha256:digest}"
: "${ASHR_RELEASE_MIGRATION_IMAGE:?ASHR_RELEASE_MIGRATION_IMAGE must be repository@sha256:digest}"
: "${ASHR_RELEASE_VERIFIER_IMAGE:?ASHR_RELEASE_VERIFIER_IMAGE must be repository@sha256:digest}"

repo_root="${ASHR_RELEASE_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
revision="${ASHR_RELEASE_REVISION:-HEAD}"
output_dir="${ASHR_RELEASE_EVIDENCE_DIR:-}"
cleanup=false
if test -z "$output_dir"; then
  output_dir="$(mktemp -d)"
  cleanup=true
fi
if test "$cleanup" = true; then
  trap 'rm -rf -- "$output_dir"' EXIT INT TERM
fi

python "$repo_root/infra/supply-chain/generate_release_evidence.py" \
  --repo-root "$repo_root" \
  --revision "$revision" \
  --output-dir "$output_dir" \
  --image "api=$ASHR_RELEASE_API_IMAGE" \
  --image "worker=$ASHR_RELEASE_WORKER_IMAGE" \
  --image "identity-delivery=$ASHR_RELEASE_IDENTITY_DELIVERY_IMAGE" \
  --image "migration=$ASHR_RELEASE_MIGRATION_IMAGE" \
  --image "verifier=$ASHR_RELEASE_VERIFIER_IMAGE"

python "$repo_root/infra/supply-chain/verify_release_evidence.py" \
  --repo-root "$repo_root" \
  --evidence-dir "$output_dir" \
  --check-git

printf 'A1 release evidence verified at %s\n' "$output_dir"
