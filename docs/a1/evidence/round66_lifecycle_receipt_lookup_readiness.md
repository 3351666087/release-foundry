# Round 66 — Lifecycle Receipt Lookup-Key Retirement Readiness

Date: 2026-07-14

## Scope

This A1 slice makes lifecycle receipt lookup-key rotation observable and
fail-closed without persisting or returning raw opaque receipt IDs. It also
preserves completed credential-link exact replay when the active lookup key
changes.

## PostgreSQL contract

Migration `023_a1_lifecycle_receipt_lookup_readiness.sql`:

- adds a required `lookup_key_version` to every lifecycle receipt;
- labels pre-existing rows `legacy-unversioned`, because they cannot be safely
  re-keyed after the raw opaque receipt ID has intentionally been discarded;
- requires every new receipt to carry an explicit configured lookup-key
  version and rejects the legacy sentinel for new writes;
- revokes the old nine-argument receipt-issue authority from `a1_runtime` and
  grants only the new ten-argument authority;
- exposes
  `a1_identity_lifecycle_lookup_retirement_readiness(TEXT,TEXT[],TIMESTAMPTZ)`
  as a pinned-search-path `SECURITY DEFINER` aggregate preflight.

The preflight returns only:

- safe lookup-key version labels;
- live/replay aggregate counts;
- the latest expiration deadline for an unreachable live receipt;
- readiness and replay-retention booleans.

It never returns receipt digests, proof ciphertext, nonces, proof-key versions,
raw link results, or key bytes.

## Retirement semantics

The Go production store refuses to preflight retirement of:

- the active lookup key;
- an invalid version;
- a version not present in the configured keyring.

PostgreSQL reports retirement as unsafe while removing a key would strand:

- an unconsumed and unexpired lifecycle receipt;
- a completed credential-link exact-replay row;
- any live or replay-capable `legacy-unversioned` row;
- any row whose version is outside the post-retirement retained version set.

Completed credential-link replay currently has no bounded purge authority, so
its lookup key remains required until a later audited replay-retention and
purge policy is implemented.

## Exact replay across lookup-key rotation

The live PostgreSQL test exposed and closed an additional rotation gap:
although the old receipt digest could be found through the previous lookup
key, credential-link idempotency, request, event, subject, and email digests
were initially recomputed with the new active key. That changed the persisted
fingerprints and could turn an exact replay into a duplicate-link conflict.

The coordinator now identifies which configured lookup key actually matched
the locked receipt and derives all transaction fingerprints with that same key.
This preserves the original exact-replay contract while the previous lookup
key is retained. Digest matching uses constant-time byte comparison.

## Verification

All commands ran in the isolated A1 worktree
`C:\Users\33516\Documents\ReleaseFoundry-a1-sync`.

```text
go test . -run 'IdentityLifecycle|Lookup|ProductionIdentity|CredentialLink' -count=1
ok github.com/3351666087/release-foundry/packages/go/releasefoundry

python -m pytest \
  tests/a1/test_identity_lifecycle_receipt_postgres_migration.py \
  tests/a1/test_atomic_identity_credential_link_migration.py \
  tests/a1/test_lifecycle_receipt_lookup_readiness_migration.py -q
14 passed in 0.12s

RELEASEFOUNDRY_RUN_IDENTITY_LIFECYCLE_POSTGRES_INTEGRATION=1 \
RELEASEFOUNDRY_IDENTITY_LIFECYCLE_TEST_DSN=postgres://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable \
go test . -run '^TestIdentityLifecyclePostgresIntegration$' -count=1 -v
PASS
ok github.com/3351666087/release-foundry/packages/go/releasefoundry 42.666s

go test ./cmd/releasefoundry-api -run 'Identity|Lookup|Production' -count=1
ok github.com/3351666087/release-foundry/packages/go/releasefoundry/cmd/releasefoundry-api

go test ./... -count=1
ok github.com/3351666087/release-foundry/packages/go/releasefoundry
ok github.com/3351666087/release-foundry/packages/go/releasefoundry/cmd/releasefoundry-api
ok github.com/3351666087/release-foundry/packages/go/releasefoundry/cmd/releasefoundry-identity-delivery
ok github.com/3351666087/release-foundry/packages/go/releasefoundry/cmd/releasefoundry-worker

go vet ./...
PASS
```

The Docker PostgreSQL container used for the authoritative integration was
`releasefoundry-oauth-pg-test` on `127.0.0.1:55432`.

## Next A1 item

Define a bounded credential-link replay-retention and purge authority with an
audited purge receipt, so previous lookup keys can eventually be retired
without weakening exact replay or silently deleting security evidence.
