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
