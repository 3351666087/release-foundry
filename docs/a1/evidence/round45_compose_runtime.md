# Round45 Commercial Compose Runtime

Date: 2026-07-10

## Scope

This round makes the disposable commercial Compose smoke explicit and fail closed.
It does not edit `services/api/**` and does not allow the commercial
profile to silently select the Go memory backend or a local file object store.

## Runtime gates

- `postgres-migrate` waits for real Postgres readiness, applies
  `docs/a1/schemas/a1_control_plane_postgres_migration.sql` with
  `ON_ERROR_STOP=1`, then verifies the tenant, project, worker-job, and artifact
  manifest tables.
- `api` is the Go control plane with `RELEASEFOUNDRY_GO_BACKEND=postgres`. Its healthcheck
  requires `backend=postgres_repository_v0`, `backend_ready=true`, and
  `local_only=false`.
- `minio-init` creates a private bucket. The opt-in `minio-smoke` then performs
  S3-compatible PUT / HEAD / GET and compares the downloaded SHA-256 checksum.
- `worker-recovery-seed` inserts `job_round45_restart_recovery` as an expired
  lease. The real worker must reclaim it, increment attempts from 1 to 2, and
  complete it.
- `commercial-worker-entrypoint.sh` writes heartbeat and summary files
  atomically. A worker process failure exits the container instead of being
  swallowed by the restart loop.
- `worker-recovery-verify` requires a fresh heartbeat file and a completed
  durable Postgres row with a non-empty result checksum.

## Commands

Static contract:

```powershell
python -m pytest tests/a1/test_round45_commercial_compose.py -q
docker compose -f infra/docker/docker-compose.self-host.yml --profile commercial --profile commercial-smoke config --quiet
```

Disposable live smoke:

```powershell
$env:RELEASEFOUNDRY_RUN_COMMERCIAL_COMPOSE_SMOKE = "1"
$env:RELEASEFOUNDRY_POSTGRES_AUTH_SECRET = "round45-postgres-local-only"
$env:RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY = "round45minio"
$env:RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY = "round45-minio-local-only-secret"
python -m pytest tests/a1/test_round45_commercial_compose.py -q
```

The live test uses a unique Compose project name and always runs
`down --volumes --remove-orphans` in cleanup. The values above are disposable
test inputs only; tracked files contain reference names, not secret values.

## Evidence status

- Docker Desktop 4.81.0 and Docker Engine 29.6.1 were reachable.
- Docker Compose v5.2.0 was reachable.
- WSL2 was enabled; `docker-desktop` was running and
  `Ubuntu-24.04-ReleaseFoundry` was installed.
- Command results and any runtime failure discovered during implementation are
  recorded in the final task report.
