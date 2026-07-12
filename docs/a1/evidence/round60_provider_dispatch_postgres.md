# Round 60: PostgreSQL Provider Dispatch Coordination

Date: 2026-07-12

## Scope

This round adds A1-owned provider dispatch coordination without changing A2
judge semantics or A3 dashboard/report behavior:

- Go dispatch lifecycle and PostgreSQL repository
- Go HTTP publication plus Python and TypeScript public contract parity
- migration 019 with fail-closed tenant/project RLS
- fencing, leases, stream observation, terminal proof, and reconciliation
- deterministic concurrency, cancellation, retry, and safe-error tests

No Ashr API or paid provider call was needed for this database correctness
slice. No DSN, password, API key, OAuth secret, prompt, media, or raw provider
response was written to evidence.

## Verification

Commands were run from the canonical A1 staging worktree.

```text
go test ./...
PASS

python -m pytest \
  tests/a1/test_provider_dispatch_postgres_migration.py \
  tests/a1/test_provider_dispatch_postgres_adversarial.py \
  tests/a1/test_provider_dispatch_sdk.py -q
22 passed

npm run build
PASS

npm test
634 passed

npm pack --dry-run
114 package files; 1.7 MB unpacked

python tests/a1/ts_python_parity_matrix.py --check
PASS

python -m pytest tests/a1 tests/integration -q -p no:cacheprovider
1329 passed, 37 skipped

go test -count=1 ./...
go vet ./...
PASS in packages/go/ashrclone and tests/integration/go

node --test tests/integration/deploy_runtime_scaffold.test.mjs
5 passed
```

The Go tests include explicit proof for:

- pre-cancelled contexts
- deadline expiry during retry backoff
- bounded retry after PostgreSQL `40001`
- bounded exhaustion after PostgreSQL `40P01`
- `READ COMMITTED` claim transactions
- failed commit mapped to an indeterminate stable error
- no SQL, table, host, or driver detail in public operational errors

## Live PostgreSQL Proof

Container: `ashr-a1-provider-dispatch-pg` on local port `55439`.

The live 16-client claim proof was repeated ten times:

```text
go test . \
  -run TestProviderDispatchConcurrentClaimAndRestartLiveOptIn \
  -count=10 -v
PASS (10/10)
```

Every repetition produced exactly one claimant with fencing token `1`; the
remaining clients returned an empty claim without error.

The database container was then actually restarted with `docker restart`.
After `pg_isready`, the latest completed dispatch was read again and its
durable identity, state, fencing token, attempts, terminal proof digest, and
terminal response digest were compared. The records were byte-identical.

Public-safe record digest:

```text
2c3dba970899697ad2197b0c9ff3d0841c8a85e3d919aab8203456a3114d0b38
```

## RLS Proof

Migration 019 and the embedded Go schema both:

- enable and force RLS
- use `app.a1_organization_id` and `app.a1_project_id`
- fail closed when either transaction-local setting is absent
- apply identical `USING` and `WITH CHECK` scope predicates

The migration suite executes with a real `NOSUPERUSER NOBYPASSRLS` role and
proves missing-scope invisibility, correct-scope read/write, sibling-project
isolation, cross-tenant isolation, rejected cross-scope writes, idempotent
re-execution, and legacy-policy upgrade without data loss.

## HTTP And Quickstart Proof

The dispatch lifecycle is published by the Go control plane and consumed by
both Python and TypeScript SDK surfaces. Public errors use stable codes and do
not expose SQL, DSN, driver, table, credential, or host detail.

The quickstart Compose path was rebuilt without cache:

```text
docker compose -f services/runner/docker-compose.a1.yml down
docker compose -f services/runner/docker-compose.a1.yml build --no-cache api
docker compose -f services/runner/docker-compose.a1.yml up -d --force-recreate postgres object-store api
```

The API image is built from `infra/docker/Dockerfile.go-runtime` and executes
the compiled `/usr/local/bin/ashr-api`; it no longer depends on `go run` or a
Go toolchain in the final image. PostgreSQL became healthy, the object-store
placeholder remained running, and the API returned:

```json
{
  "ashr_api_used": false,
  "backend": "postgres_repository_v0",
  "backend_mode": "postgres",
  "backend_ready": true,
  "local_only": false,
  "ready": true,
  "schema_version": "ashr.clone.saas_control_plane.v1",
  "service": "ashr-go-control-plane",
  "status": "ok"
}
```

The standard Python SDK to real Go server test passed:

```text
python -m pytest tests/integration/test_a1_go_server_python_sdk.py -q -p no:cacheprovider
1 passed
```

The deployment scaffold acceptance contract was formally upgraded to the
compiled Go commercial runtime, MinIO service names, Terraform marker
`ashr.a1.self_host.commercial_runtime.v2`, and the approved Rust verifier
security dependencies. It passed `5/5`.

## Known Boundary

This round proves PostgreSQL coordination, persistence, Go HTTP publication,
and Python/TypeScript contract parity. The quickstart Compose `object-store`
service is intentionally a BusyBox-backed local filesystem placeholder; it is
not MinIO, S3, or production object storage. The commercial self-host Compose
has the separate MinIO path.

The first earlier Docker dependency download encountered a transient
`proxy.golang.org` EOF. A later retry and the final no-cache build succeeded.
One combined local command also mixed a Node `.mjs` test into pytest and a
fresh PowerShell process reported Docker pipe/config permissions; authoritative
commands were rerun independently and passed. These were command/environment
hygiene issues, not product failures.

The publishing worktree has unusual write ACLs. Python source syntax was
verified without bytecode output by parsing all 174 Python files with
`ast.parse`. The Rust verifier passed all suites with an external writable
`CARGO_TARGET_DIR`; A3 passed `334/334` with writable `TEMP` and `TMP`, and the
pinned audit bundle verifier passed. Publication remains gated on committing
this snapshot, pushing it, and obtaining a green CL Gate for the new SHA.
