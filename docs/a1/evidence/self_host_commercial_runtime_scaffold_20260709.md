# A1 Self-Host Commercial Runtime Scaffold - 2026-07-09

Scope:
- `services/runner/docker-compose.a1.yml` now models the local commercial runtime shape: API, long-running worker, Postgres, object evidence storage, and billing webhook receiver.
- `infra/docker/docker-compose.self-host.yml` now models the commercial daemon deployment profile with API, worker daemon, Postgres, Redis, MinIO, and bucket bootstrap wiring.
- `infra/docker/self-host.env.example` documents reference-only secret names and local non-secret service endpoints for compose validation.
- `infra/terraform/self-host` carries the matching provider-neutral contract for API, worker, billing webhook, Postgres, Redis, object storage, and quota ledger resources.
- This is a scaffold and static validation target. It does not include live payment-provider calls, hosted API calls, or production secret material.

Runtime services:
- `api`: Go A1 control-plane entrypoint with Postgres backend and loopback host binding.
- `worker`: long-running queue/evidence scaffold using `RELEASEFOUNDRY_WORKER_MODE=long-running`, `RELEASEFOUNDRY_WORKER_QUEUE=releasefoundry_worker_jobs`, and object evidence writes.
- `postgres`: disposable local Postgres 16 service for smoke data.
- `object-store`: credential-free local file-backed object evidence volume for `releasefoundry-local-artifacts/evidence/a1/self-host`.
- `billing-webhook`: loopback-only receiver surface with `RELEASEFOUNDRY_BILLING_WEBHOOK_RECEIVER=enabled`, `RELEASEFOUNDRY_BILLING_LEDGER_TABLE=releasefoundry_billing_ledger`, and `RELEASEFOUNDRY_BILLING_QUOTA_LEDGER_TABLE=releasefoundry_quota_ledger`.

Commercial daemon profile:
- `infra/docker/docker-compose.self-host.yml` exposes `api`, `worker`, `daemon`, and `commercial` profiles so the API and worker daemon can be validated together or separately.
- `worker` uses `RELEASEFOUNDRY_WORKER_MODE=daemon`, `RELEASEFOUNDRY_WORKER_QUEUE=releasefoundry_worker_jobs`, `RELEASEFOUNDRY_WORKER_LEASE_SECONDS`, `RELEASEFOUNDRY_WORKER_POLL_INTERVAL_SECONDS`, `RELEASEFOUNDRY_WORKER_MAX_ATTEMPTS`, and `RELEASEFOUNDRY_WORKER_EVIDENCE_WRITES=object-store`.
- `postgres`, `redis`, and `minio` all have health checks; the worker waits on healthy API, Postgres, Redis, and MinIO services.
- `minio-init` creates the `releasefoundry-local-artifacts` bucket and keeps access private. MinIO root material is passed through Compose secrets backed by environment names only.

Secret boundary:
- Secret values are not present in tracked compose, HCL, or evidence docs.
- Production-sensitive inputs are represented as reference env names only: `RELEASEFOUNDRY_POSTGRES_DSN_REF`, `RELEASEFOUNDRY_BILLING_PROVIDER_SECRET_REF`, `RELEASEFOUNDRY_BILLING_WEBHOOK_SECRET_REF`, `RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_REF`, and `RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_REF`.
- The infra/docker env example uses `RELEASEFOUNDRY_DATABASE_URL_REF`, `RELEASEFOUNDRY_REDIS_URL_REF`, `RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT_REF`, `RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY_REF`, `RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY_REF`, `RELEASEFOUNDRY_BILLING_PROVIDER_SECRET_REF`, and `RELEASEFOUNDRY_BILLING_WEBHOOK_SECRET_REF` instead of secret values.
- Local compose uses only a container-internal Postgres DSN for disposable smoke data; it does not set `RELEASEFOUNDRY_API_KEY`, `RELEASEFOUNDRY_API_KEY`, authorization headers, bearer tokens, or provider key literals.

Evidence and quota contract:
- Worker evidence names the object bucket with `RELEASEFOUNDRY_OBJECT_STORE_BUCKET` and prefix with `RELEASEFOUNDRY_OBJECT_EVIDENCE_PREFIX`.
- Artifact manifests are routed through the `releasefoundry_artifact_manifests` table name.
- Quota/accounting checks are routed through `releasefoundry_quota_ledger` for run upload, trace ingestion, artifact manifest, worker job, and billing webhook ingest operations.

Validation commands:

```powershell
python -m pytest tests/a1/test_local_self_host_smoke_compose.py -q
docker compose -f services/runner/docker-compose.a1.yml config --quiet
docker compose --env-file infra/docker/self-host.env.example -f infra/docker/docker-compose.self-host.yml --profile commercial config --quiet
```

Known gaps:
- The worker command is a long-running local scaffold around existing Go worker lifecycle tests, not a production queue daemon.
- The billing webhook service uses the current Go API entrypoint as the receiver surface; provider-specific signature verification remains behind the secret-ref contract.
- `services/runner/docker-compose.a1.yml` keeps file-backed storage for the Go smoke surface. The commercial `infra/docker` profile uses MinIO/S3-compatible wiring, but the current worker command still exercises the replay scaffold rather than a production queue daemon binary.
