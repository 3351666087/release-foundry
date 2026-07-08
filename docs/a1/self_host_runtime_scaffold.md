# A1 Self-Host Runtime Scaffold

This note captures the current deploy/runtime scaffold for the A1 Ashr large-SaaS path. It is intentionally local-first and credential-free.

## Docker Compose

`infra/docker/docker-compose.self-host.yml` defines five services:

- `api`: runs the stdlib WSGI control plane from `services.api.control_plane` on port `8080`.
- `worker`: uses the same Python image and exposes the `services.api.cli replay-queued` worker path behind the `worker` profile.
- `postgres`: local Postgres 16 metadata store with development-only credentials.
- `redis`: local Redis queue/cache placeholder.
- `object-store`: filesystem-backed artifact volume placeholder at `file:///object-store`.

The compose file has no production secrets. Replace the local Postgres password, object-store placeholder, and runtime URLs through environment-specific secret management before production use.

## Terraform

`infra/terraform/self-host/` is a provider-neutral HCL skeleton. It uses `null_resource` contract records to name the API, worker, Postgres, Redis, and object-store components without requiring cloud credentials. Provider-specific adapters should consume its variables and preserve the non-secret output contract.

## Rust Utility

`packages/rust/ashr-runtime-verify` is a dependency-free Rust crate for runtime fixture checks. It supports:

- `verify <path>`: bounded JSON text, runtime marker, delimiter, and secret-marker checks.
- `replay-plan <path>`: deterministic replay candidate summary for queued/running statuses.

Rust is optional for static validation in this workspace; install `cargo` to compile or run the crate directly.

## Static Validation

Run:

```bash
node --test tests/integration/deploy_runtime_scaffold.test.mjs
```

The test validates compose, Terraform, Rust metadata, and secret hygiene without Docker, Terraform, Rust, or external cloud credentials.
