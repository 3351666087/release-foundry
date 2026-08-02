# Round 69: Dedicated Identity Runtime and Migration Replay Evidence

Date: 2026-07-22

## Scope

This evidence covers the A1 acceptance remediation on the disposable
self-host Compose stack. It does not claim hosted PostgreSQL, VPC, KMS,
production deployment, or A2 release approval.

## Changes under test

- The API identity store accepts `RELEASEFOUNDRY_IDENTITY_POSTGRES_DSN` before the
  shared control-plane DSN.
- `postgres-migrate` creates `releasefoundry_identity_runtime` as a login role with no
  superuser, database-creation, role-creation, or RLS-bypass authority.
- The identity login inherits the scoped security-definer entrypoints from the
  non-login `a1_runtime` role and has no `public` schema CREATE privilege.
- Ordered migrations are recorded in `releasefoundry_schema_migrations` with SHA-256
  digests. A changed recorded file fails closed.

## Verification

All credentials used below were disposable process-local test values. No
credential value is stored in this document or in tracked Compose files.

- `go test ./cmd/releasefoundry-api`: passed.
- `python -m pytest tests/a1/test_round45_commercial_compose.py tests/a1/test_local_self_host_smoke_compose.py -q`:
  `16 passed, 1 skipped`.
- Compose model validation with commercial profiles: passed.
- Fresh PostgreSQL migration: passed; ordered ledger count was `24`.
- Migration replay on the same database: passed; previously recorded ordered
  files were skipped.
- Full disposable commercial smoke:
  `python -m pytest tests/a1/test_round45_commercial_compose.py::test_round45_live_commercial_compose_smoke -q`:
  `1 passed` in approximately 71 seconds.

The full smoke covered the Go PostgreSQL API health gate, MinIO private-bucket
PUT/HEAD/GET checksum evidence, worker heartbeat, expired-lease recovery, and
durable completion verification. The test's unique Compose project was removed
with `down --volumes --remove-orphans` after completion.

## Security boundary

The identity connection is now independently authenticated from the ordinary
control-plane connection. The ordinary A1 repository still uses its existing
control-plane DSN in this round; converting every repository query to an
explicit tenant-context runtime role is a separate follow-up and is not claimed
here.

## Remaining gates

- Real hosted identity, target PostgreSQL, object storage, KMS, and VPC
  deployment receipts are still absent.
- GitHub tenant-bound App installation and enforced required-check readback are
  still external acceptance gates.
- A2 judge authority remains unchanged; this evidence does not change any
  score, Decision Ledger result, or production-readiness decision.
