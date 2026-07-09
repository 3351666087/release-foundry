# A1 Self-Host Commercial Runtime Scaffold - 2026-07-09

Scope:
- `services/runner/docker-compose.a1.yml` now models the local commercial runtime shape: API, long-running worker, Postgres, object evidence storage, and billing webhook receiver.
- `infra/terraform/self-host` carries the matching provider-neutral contract for API, worker, billing webhook, Postgres, Redis, object storage, and quota ledger resources.
- This is a scaffold and static validation target. It does not include live payment-provider calls, hosted API calls, or production secret material.

Runtime services:
- `api`: Go A1 control-plane entrypoint with Postgres backend and loopback host binding.
- `worker`: long-running queue/evidence scaffold using `ASHR_WORKER_MODE=long-running`, `ASHR_WORKER_QUEUE=ashr_worker_jobs`, and object evidence writes.
- `postgres`: disposable local Postgres 16 service for smoke data.
- `object-store`: credential-free local file-backed object evidence volume for `ashr-local-artifacts/evidence/a1/self-host`.
- `billing-webhook`: loopback-only receiver surface with `ASHR_BILLING_WEBHOOK_RECEIVER=enabled`, `ASHR_BILLING_LEDGER_TABLE=ashr_billing_ledger`, and `ASHR_BILLING_QUOTA_LEDGER_TABLE=ashr_quota_ledger`.

Secret boundary:
- Secret values are not present in tracked compose, HCL, or evidence docs.
- Production-sensitive inputs are represented as reference env names only: `ASHR_POSTGRES_DSN_REF`, `ASHR_BILLING_PROVIDER_SECRET_REF`, `ASHR_BILLING_WEBHOOK_SECRET_REF`, `ASHR_OBJECT_STORE_ACCESS_KEY_REF`, and `ASHR_OBJECT_STORE_SECRET_KEY_REF`.
- Local compose uses only a container-internal Postgres DSN for disposable smoke data; it does not set `ASHR_API_KEY`, `ASHR_LABS_API_KEY`, authorization headers, bearer tokens, or provider key literals.

Evidence and quota contract:
- Worker evidence names the object bucket with `ASHR_OBJECT_STORE_BUCKET` and prefix with `ASHR_OBJECT_EVIDENCE_PREFIX`.
- Artifact manifests are routed through the `ashr_artifact_manifests` table name.
- Quota/accounting checks are routed through `ashr_quota_ledger` for run upload, trace ingestion, artifact manifest, worker job, and billing webhook ingest operations.

Validation commands:

```powershell
python -m pytest tests/a1/test_local_self_host_smoke_compose.py -q
docker compose -f services/runner/docker-compose.a1.yml config --quiet
```

Known gaps:
- The worker command is a long-running local scaffold around existing Go worker lifecycle tests, not a production queue daemon.
- The billing webhook service uses the current Go API entrypoint as the receiver surface; provider-specific signature verification remains behind the secret-ref contract.
- Object storage is file-backed for local safety. Provider adapters should map the same `*_REF` names to S3-compatible or cloud-native object storage without storing secret values in Terraform state.
