#!/bin/sh
set -eu

: "${RELEASEFOUNDRY_RELEASE_API_IMAGE:?RELEASEFOUNDRY_RELEASE_API_IMAGE must be repository@sha256:digest}"
: "${RELEASEFOUNDRY_RELEASE_WORKER_IMAGE:?RELEASEFOUNDRY_RELEASE_WORKER_IMAGE must be repository@sha256:digest}"
: "${RELEASEFOUNDRY_RELEASE_IDENTITY_DELIVERY_IMAGE:?RELEASEFOUNDRY_RELEASE_IDENTITY_DELIVERY_IMAGE must be repository@sha256:digest}"
: "${RELEASEFOUNDRY_RELEASE_MIGRATION_IMAGE:?RELEASEFOUNDRY_RELEASE_MIGRATION_IMAGE must be repository@sha256:digest}"
: "${RELEASEFOUNDRY_RELEASE_VERIFIER_IMAGE:?RELEASEFOUNDRY_RELEASE_VERIFIER_IMAGE must be repository@sha256:digest}"

repo_root="${RELEASEFOUNDRY_RELEASE_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
revision="${RELEASEFOUNDRY_RELEASE_REVISION:-HEAD}"
output_dir="${RELEASEFOUNDRY_RELEASE_EVIDENCE_DIR:-}"
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
  --image "api=$RELEASEFOUNDRY_RELEASE_API_IMAGE" \
  --image "worker=$RELEASEFOUNDRY_RELEASE_WORKER_IMAGE" \
  --image "identity-delivery=$RELEASEFOUNDRY_RELEASE_IDENTITY_DELIVERY_IMAGE" \
  --image "migration=$RELEASEFOUNDRY_RELEASE_MIGRATION_IMAGE" \
  --image "verifier=$RELEASEFOUNDRY_RELEASE_VERIFIER_IMAGE"

python "$repo_root/infra/supply-chain/verify_release_evidence.py" \
  --repo-root "$repo_root" \
  --evidence-dir "$output_dir" \
  --check-git

printf 'A1 release evidence verified at %s\n' "$output_dir"
