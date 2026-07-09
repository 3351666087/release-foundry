# A1 Evidence

This directory holds public-safe A1 evidence notes and smoke-run pointers. It must not include raw hosted Ashr API payloads, API keys, bearer tokens, or private evidence references.

## Local Go API + Postgres self-host smoke

`services/runner/docker-compose.a1.yml` is a local Docker Compose artifact for the A1 Go API + Postgres direction. It starts:

- `postgres`: Postgres 16 on loopback port `15432` with local trust auth for disposable smoke data.
- `api`: the Go control-plane entrypoint from `packages/go/ashrclone/cmd/ashr-api`, listening on loopback port `18787` and configured with `ASHR_GO_BACKEND=postgres` plus a container-internal `ASHR_POSTGRES_DSN`.

Run from the repository root:

```powershell
docker compose -f services/runner/docker-compose.a1.yml up --build
```

Optional local cleanup:

```powershell
docker compose -f services/runner/docker-compose.a1.yml down -v
```

Static validation:

```powershell
python -m pytest tests/a1/test_local_self_host_smoke_compose.py
```

Boundary notes:

- The compose file is local-only and binds API/Postgres ports to `127.0.0.1`.
- The API service uses the local Go backend environment only: `ASHR_GO_API_ADDR`, `ASHR_GO_BACKEND`, `ASHR_POSTGRES_DSN`, and `ASHR_A1_SMOKE_MODE`.
- The artifact intentionally does not set hosted API key variables such as `ASHR_API_KEY`, `ASHR_LABS_API_KEY`, or bearer-token headers.
- The Postgres DSN is a local service URL for the compose network and is not a production secret.

## 2026-07-09 - A1 Postgres / SQL / Compose backend slice

Goal:
- Continue A1 after CL Gate unblock, keeping A3 out of the commit and expanding beyond Go-only into Go + SQL/PLpgSQL + Docker/YAML self-host evidence per `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

CL Gate unblock:
- Merged `origin/main` into `codex/a1-local-sdk-runner` to align the PR merge-ref with the current CL workflow and A3 pinned evidence baseline.
- GitHub run `28959405199`: Plan, Go, Python, TypeScript, and CL summary passed; A3-only jobs were correctly skipped by selective CL plan for the A1-only push.
- A3 local dirty files were not committed. Remaining A3 status entries are EOL-only workspace noise and are excluded from A1 staging.

Implemented:
- `packages/go/ashrclone/postgres.go`: first durable Postgres repository slice with schema SQL, migration hook, tenant/project/dataset upserts, run submit, and idempotency ledger replay/conflict handling.
- `packages/go/ashrclone/backend.go`, `cmd/ashr-api/main.go`, `server.go`: backend selection now exposes readiness and migration; Go API startup runs Postgres migration before advertising readiness; health reports `backend_mode=postgres` separately from `backend_ready`.
- `docs/a1/schemas/a1_control_plane_postgres_migration.sql`: SQL/PLpgSQL migration artifact with tenant/project/dataset/run/idempotency tables, RLS policies, current-tenant helper, and updated_at triggers.
- `services/runner/docker-compose.a1.yml`: local-only Go API + Postgres compose smoke with loopback ports and no hosted Ashr API keys.
- `tests/a1/test_a1_control_plane_postgres_migration.py` and `tests/a1/test_local_self_host_smoke_compose.py`: static validation for SQL/PLpgSQL and Docker/YAML artifacts.
- `docs/a1/evidence/README.md`: public-safe self-host smoke instructions and boundaries.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `python -B -m pytest tests/a1/test_a1_control_plane_postgres_migration.py tests/a1/test_local_self_host_smoke_compose.py -q -p no:cacheprovider` -> 5 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 306 passed.
- `npm test --prefix packages/ts/ashr-clone` -> 282 passed.
- Repo-root `go test ./...` still fails because the repository root is not a Go module; Go tests must run from `packages/go/ashrclone` and `tests/integration/go`.

Real API / private evidence:
- No Ashr API calls in this CL-fix/backend-slice subround. No secret files read. No private evidence staged.

Peer changes / impact:
- `origin/main` brought CL workflow, A2/A3 contracts, `.gitattributes`, and strategy updates into this branch. Impact: A1 branch now tests against current CL baseline; A3 evidence failures are resolved by branch alignment, not by modifying A3 artifacts.

Known gaps / next 20 A1 growth points:
1. Implement Postgres worker job enqueue/lease/heartbeat/complete/fail/list.
2. Implement Postgres run upload persistence.
3. Implement Postgres trace event ingestion persistence.
4. Implement Postgres artifact manifest persistence.
5. Add PLpgSQL quota ledger consume/refund functions.
6. Add tenant/project API key lifecycle tables and Go routes.
7. Add auth middleware with API-key scopes for mutating routes.
8. Add usage ledger writes before submit/upload/trace/artifact/worker mutation.
9. Add audit hash-chain append and verifier in Go.
10. Add Docker Compose live smoke once Docker daemon availability is confirmed.
11. Add TS/Python SDK smoke against the compose Go+Postgres server.
12. Add OpenAPI generation from Go route manifest and validate Python/TS parity.
13. Add SQL migration checksum/version ledger for Postgres artifact.
14. Add Rust verifier over A1 public evidence packets if security/audit path needs it.
15. Add Terraform/HCL self-host skeleton for enterprise deploy review.
16. Add official API read-only calibration for newly named backend concepts.
17. Add paid small-batch official API calibration only after dry-run plan and quota evidence.
18. Expand media envelope tests across text/audio/file/image/video equally.
19. Add old-vs-new run diff API and fixture.
20. Keep A3 files out of A1 commits except explicit CL unblock emergencies.

## 2026-07-09 - A1 worker_jobs SQL contract expansion

Goal:
- Apply the language/platform decision that Go owns worker runtime while SQL/PLpgSQL owns durable tenant-isolated backend state. This subround strengthens the Postgres schema before implementing the full Go worker queue persistence path.

Implemented:
- Added `ashr_worker_jobs` to `PostgresSchemaSQL` with tenant/project scoped primary key, job type, target id, payload hash, status, priority, attempts, lease owner/expires, available_at, last_error JSONB, result hash, idempotency key, request id, and lifecycle timestamps.
- Added worker lease/status indexes: `ashr_worker_jobs_lease_idx` and `ashr_worker_jobs_status_idx`.
- Extended `docs/a1/schemas/a1_control_plane_postgres_migration.sql` with the same table/index contract plus updated_at trigger, RLS enablement, and `ashr_worker_jobs_tenant_isolation` policy.
- Extended `tests/a1/test_a1_control_plane_postgres_migration.py` to verify worker_jobs table, indexes, trigger, RLS, and policy remain aligned with Go schema.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `python -B -m pytest tests/a1/test_a1_control_plane_postgres_migration.py tests/a1/test_local_self_host_smoke_compose.py -q -p no:cacheprovider` -> 5 passed.

Next:
- Implement Go Postgres `EnqueueWorkerJob`, `LeaseWorkerJob`, heartbeat, complete, fail, and list using this table.
- Add PLpgSQL quota ledger consume/refund before worker mutations.

## 2026-07-09 - A1 durable Postgres worker lifecycle

Goal:
- Move the Go self-host backend from worker-job schema-only support to a durable queue lifecycle that can back API gateway worker routes, self-host workers, release-gate jobs, and future quota/audit enforcement without using Ashr-hosted APIs.

Implemented:
- `packages/go/ashrclone/postgres.go`: implemented Postgres `EnqueueWorkerJob`, `LeaseWorkerJob`, `HeartbeatWorkerJob`, `CompleteWorkerJob`, `FailWorkerJob`, and `ListWorkerJobs`.
- Added worker-specific idempotency replay/insert helpers for `Envelope[WorkerJob]` while preserving existing run submit idempotency behavior.
- Added project existence checks, expired lease normalization, `FOR UPDATE SKIP LOCKED` lease selection, row scanning with nullable lifecycle timestamps, redacted `last_error` JSONB decode/encode, result/failure hash persistence, and lease-owner validation.
- `packages/go/ashrclone/postgres_test.go`: updated Postgres boundary tests so worker lifecycle methods are treated as implemented DB-backed operations; remaining not-implemented coverage now targets upload, trace, and artifact persistence.
- `tests/a1/test_a1_control_plane_postgres_migration.py`: added static lifecycle assertions for atomic worker queue behavior, hash-only payload/result/error handling, idempotency helpers, and list filters.

Validation:
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `python -B -m pytest tests/a1/test_a1_control_plane_postgres_migration.py tests/a1/test_local_self_host_smoke_compose.py -q -p no:cacheprovider` -> 7 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 308 passed.
- `npm test --prefix packages/ts/ashr-clone` -> 282 passed.
- `git diff --check` -> only pre-existing A3 CRLF warnings for `docs/a3/acceptance_checklist.md` and `docs/a3/worklog.md`; no A1 whitespace errors.

Real API / private evidence:
- No official Ashr API call in this backend durability subround. No API key or desktop key file was read, printed, logged, or staged.

Peer changes / impact:
- `origin/main` and PR list were fetched before implementation. PR #21 is merged, but branch still contains later A1 commit `9c721d3`; next PR must include `9c721d3` plus this worker lifecycle implementation.
- Existing dirty A3 EOL-only files and untracked `recon/`, `tools/` remain out of scope and must not be staged.

Next 20 A1 growth points:
1. Add live Postgres worker lifecycle tests gated by `A1_POSTGRES_TEST_DSN`.
2. Implement durable Postgres run upload persistence.
3. Implement durable Postgres trace ingestion persistence.
4. Implement durable Postgres artifact manifest persistence.
5. Add PLpgSQL quota ledger consume/refund functions and static tests.
6. Add API-key lifecycle tables and Go routes.
7. Enforce API-key scopes in Go middleware before worker/upload/trace/artifact mutations.
8. Add usage ledger writes before durable mutations.
9. Add audit hash-chain append and verify routes in Go.
10. Add worker daemon loop that heartbeats, completes, retries, and dead-letters against Postgres.
11. Add Docker Compose live smoke for Go API + Postgres + worker when Docker daemon is available.
12. Add TS SDK smoke against Go Postgres backend, not only memory backend.
13. Add Python SDK smoke against Go Postgres backend.
14. Generate OpenAPI from Go route manifest and validate TS/Python route parity from it.
15. Add SQL migration checksum/version ledger.
16. Add Terraform/HCL self-host skeleton for enterprise review.
17. Add Rust evidence bundle verifier for tamper-proof audit packets.
18. Run official API dry-run/small-batch calibration for run lifecycle fields with public-safe summaries.
19. Expand five-modality official API evidence packet for text/audio/file/image/video equally after quota gate review.
20. Keep A2/A3 artifacts out of A1 commits unless a CL emergency explicitly requires otherwise.
