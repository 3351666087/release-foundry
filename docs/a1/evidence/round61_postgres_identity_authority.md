# Round 61 PostgreSQL Identity Authority

Date: 2026-07-12

## Scope

This round removes process-memory fallback from canonical identity-account HTTP
reads in the production Go runtime. PostgreSQL is the sole production authority.
The shared A1/A2/A3 contract and judge/dashboard semantics are unchanged.

## Commercial ROI Selection

| Candidate | Demo value | Risk reduction | Contract impact | Effort | API evidence value |
|---|---:|---:|---:|---:|---:|
| PostgreSQL-only canonical identity reads | 4 | 5 | 2 | 3 | 2 |
| Go browser-session bootstrap/logout/revoke-all parity | 4 | 4 | 3 | 4 | 2 |
| Hash-bound provider execution receipts | 5 | 5 | 3 | 4 | 5 |

The PostgreSQL authority slice was completed first because allowing production
reads to fall back to process memory could return a different account after a
restart or from another replica.

## Implementation

- Added an explicit `UnifiedIdentityStore` dependency to the Go HTTP server.
- Production runtime injects `ProductionIdentityStore` and no longer constructs
  the in-memory `UnifiedIdentityService`.
- Added `ProductionIdentityStore.GetIdentityAccount`.
- Account projection uses migration 017 in a read-only `READ COMMITTED`
  transaction with transaction-local timeouts.
- Invalid account UUIDs fail before database access.
- SQL NULL and malformed projection JSON fail closed.
- Query, timeout configuration, and commit failures are covered; rollback is
  asserted where applicable.
- The account is decoded strictly and the transaction commits before the value
  is returned.
- Missing production authority returns the stable public-safe
  `503 identity_store_unavailable`.
- Lifecycle construction accepts a nil memory service only when the atomic
  production coordinator is present.
- Production readiness requires migration 017 account-projection capability.
- Store selection is explicit. Backend and verification internals are not
  searched for an implicit fallback implementation.
- Added the `openIdentityDatabase` runtime seam solely to inject `sqlmock` into
  the actual production constructor path.

The production constructor test proves:

```text
runtime.mode == postgres
runtime.unifiedIdentity == nil
runtime.postgres != nil
runtime.identityLifecycle != nil
runtime.identitySessions != nil
```

## Verification

Completed successfully:

```text
go test -count=1 ./...
go vet ./...
npm run build
npm test
npm pack --dry-run
python tests/a1/ts_python_parity_matrix.py --check
python scripts/cl_guard.py hygiene
python scripts/cl_guard.py commercial
git diff --check
```

TypeScript result:

```text
634 passed, 0 failed
114 package files
1.7 MB unpacked
```

The first full Python attempt collected 1366 tests and progressed to
approximately 39% without a failure, then blocked on repeated `docker inspect`
calls. Docker Desktop was restarted. The daemon itself became ready, but the
earlier `docker` command resolved to a hanging CLI shim. Prepending the Docker
Desktop distribution path made the server probe return version `29.6.1`:

```text
C:\Program Files\Docker\Docker\resources\bin
```

The authoritative full gate was then rerun with that CLI first on `PATH`:

```text
python -m pytest tests/a1 tests/integration
1326 passed, 40 skipped in 107.51s
```

This completed the real Go-server Python SDK vertical path as part of the full
suite. The initial hang is retained here as an environment diagnosis, not a
product failure or a passing result.

## Boundary And Deferred Security Work

- Split password/MFA stores are not wired into production because they cannot
  atomically guarantee ticket consumption, credential mutation, session
  revocation, idempotency, and audit. Those routes remain fail closed until one
  opaque transactional operation and SQL wrapper exist.
- A future explicit production HTTP constructor should prevent generic nil
  backends from becoming memory stores.
- PostgreSQL startup errors still need a stable public-safe wrapper.
- Identity-security success maps should become typed DTOs.
- Typed service outages should be distinguishable from authorization failures.

## Peer State

`origin/dev/g3-a2-calibration` advanced to `6b62f978`. No peer file was merged
or modified by this A1 round.

## Next-Round Required Top Three

1. Persist hash-bound, public-safe provider execution evidence for XJTLU
   `gpt-5.6-sol`, Qwen official `qwen-plus`, and local Ollama, including
   `endpoint_sha256`, `evidence_sha256`, invocation timestamp, and response
   binding for the already verified Python/TypeScript, streaming, tool-call,
   and usage paths.
2. Complete successful target-endpoint calibration for image, audio, file, and
   video. Protocol support or an accepted request ending in
   `request_status=failed` remains `discovered`, never `callable`.
3. Produce one authoritative A1 release-candidate evidence package binding the
   latest A1 Git SHA, provider execution receipts, PostgreSQL/RLS proof,
   concurrent claim/lease/fencing proof, and restart-persistence proof.

Provider keys remain environment-only. Public evidence must not contain keys,
credential-bearing endpoints, private prompts, or raw private responses.
