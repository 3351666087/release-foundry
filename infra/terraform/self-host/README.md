# Ashr A1 Self-Host Terraform Skeleton

This directory is a provider-neutral deployment contract for the A1 runtime. It names the components that a cloud-specific adapter should provision without requiring cloud credentials during static validation.

Components:

- `api`: stdlib WSGI control-plane/API runtime on port `8080`.
- `worker`: replay-oriented queue worker runtime using `python -m services.api.cli replay-queued`.
- `postgres`: durable control-plane and run metadata store.
- `redis`: queue/cache coordination layer.
- `object_store`: artifact and replay evidence storage bucket/container.

Secret handling:

- No secrets are stored in this module.
- Connection strings are represented as `*_REF` placeholders in outputs.
- Provider adapters should resolve those references from their secret manager at deploy time.

Static validation only needs Terraform syntax/metadata checks. Applying this module creates only `null_resource` contract records unless a provider-specific adapter is added later.
