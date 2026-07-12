# A1 Self-Host Runtime Scaffold

This note captures the current deploy/runtime scaffold for the A1 Ashr large-SaaS path. It is intentionally local-first and credential-free.

## Docker Compose

`infra/docker/docker-compose.self-host.yml` defines a compiled Go runtime plus
the backing and migration services needed by the commercial self-host path:

- `api`: runs `/usr/local/bin/ashr-api` from the multi-stage Go runtime image.
- `worker`: runs the long-lived `/usr/local/bin/ashr-worker` daemon.
- `postgres` and `postgres-migrate`: durable metadata plus ordered migrations.
- `redis`: queue/cache coordination.
- `minio` and `minio-init`: S3-compatible object storage and private bucket bootstrap.

The compose file has no embedded production secrets. Credentials are supplied
through Compose secret references and must be resolved by environment-specific
secret management. `services/runner/docker-compose.a1.yml` remains the smaller
quickstart: its `object-store` service is only a local filesystem placeholder,
not MinIO or production object storage.

## Terraform

`infra/terraform/self-host/` is a provider-neutral HCL skeleton. It uses
`null_resource` contract records to name the API, worker, Postgres, Redis, and
object-store components without requiring cloud credentials. The current
static contract is `ashr.a1.self_host.commercial_runtime.v2`.
Provider-specific adapters should consume its variables and preserve the
non-secret output contract.

## Rust Utility

`packages/rust/ashr-runtime-verify` is a security-focused Rust crate for
runtime fixture and signed-bundle checks. Its locked dependency set deliberately
includes `hmac`, `sha2`, `subtle`, and `zeroize`, plus bounded JSON parsing,
rather than maintaining the obsolete dependency-free constraint. It supports:

- `verify <path>`: bounded JSON text, runtime marker, delimiter, and secret-marker checks.
- `replay-plan <path>`: deterministic replay candidate summary for queued/running statuses.

Rust is optional for static validation in this workspace; install `cargo` to compile or run the crate directly.

## Static Validation

Run:

```bash
node --test tests/integration/deploy_runtime_scaffold.test.mjs
```

The test validates compose, Terraform, Rust metadata, and secret hygiene without Docker, Terraform, Rust, or external cloud credentials.
