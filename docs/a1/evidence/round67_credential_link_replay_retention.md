# Round 67 - Credential-Link Replay Retention and Audited Purge

Date: 2026-07-14

## Scope

This A1 slice gives completed credential-link exact-replay rows a bounded,
auditable retention lifecycle. It allows an old lifecycle receipt lookup key
to become retirement-ready after its replay window expires, without exposing
receipt identifiers, keyed fingerprints, proof material, link payloads, or
database mutation authority through the A3-facing API.

## PostgreSQL contract

Migration `024_a1_credential_link_replay_retention.sql`:

- adds `identity_lifecycle_receipts.replay_retain_until`;
- derives the deadline as exactly `consumed_at + interval '30 days'`;
- backfills existing completed replay rows and makes the deadline immutable;
- adds a bounded lookup index and consistency checks;
- creates the durable aggregate-only
  `identity_credential_link_replay_purge_audit` table;
- enables and forces RLS on the audit table;
- revokes direct receipt/audit access from `PUBLIC` and `a1_runtime`;
- exposes only the pinned-search-path `SECURITY DEFINER` authority
  `a1_purge_identity_credential_link_replays(...)`.

The purge authority:

- accepts a bound from 1 through 1000;
- serializes requests with an advisory lock;
- locks eligible rows with `FOR UPDATE SKIP LOCKED`;
- deletes only consumed credential-link replay rows whose immutable retention
  deadline is at or before the requested cutoff;
- excludes `legacy-unversioned` rows;
- supports exact idempotent replay and rejects reuse of an idempotency key with
  changed request fingerprints;
- persists and returns aggregate counts by safe lookup-key version only.

No raw receipt digest, proof ciphertext, nonce, proof-key version, subject
fingerprint, email fingerprint, credential link result, or key material is
returned by the function or retained in the purge audit.

## Go production API

`PostgresProductionIdentityStore.PurgeExpiredCredentialLinkReplays` adds a
typed A3-safe entry point around the PostgreSQL authority.

The request requires:

- an explicit cutoff;
- a bounded limit;
- actor and reason text;
- an idempotency key.

Actor and reason accept Unicode, including Chinese operational metadata. The
store HMAC-keys idempotency and request fingerprints before calling
PostgreSQL, validates the aggregate receipt strictly, rejects malformed
schemas, impossible counts, overflow, and legacy lookup-version output, and
never performs direct table deletion.

Production readiness now requires migration 024, the purge function, forced
RLS, revoked direct runtime table access, and a pinned `SECURITY DEFINER`
owner.

## Lookup-key retirement semantics

A completed lookup-v1 credential-link replay continues to block lookup-v1
retirement during its 30-day exact-replay window. Purging before the immutable
deadline deletes zero rows. Purging after the deadline deletes the eligible
row and makes lookup-v1 retirement ready when no other live, replay-capable,
legacy, or out-of-keyring rows remain.

This preserves the previous exact-replay contract for the full retention
window while providing an explicit and durable operational path to old-key
retirement.

## Verification

All commands ran in the isolated A1 worktree
`C:\Users\33516\Documents\Ashr-a1-sync`.

```text
python -m pytest \
  tests/a1/test_identity_lifecycle_receipt_postgres_migration.py \
  tests/a1/test_atomic_identity_credential_link_migration.py \
  tests/a1/test_lifecycle_receipt_lookup_readiness_migration.py \
  tests/a1/test_credential_link_replay_retention_migration.py -q
18 passed in 0.10s

go test . -run 'IdentityLifecycle|Lookup|ProductionIdentity|CredentialLink' -count=1
ok github.com/ashr-labs/ashr/packages/go/ashrclone 1.747s

ASHR_RUN_IDENTITY_LIFECYCLE_POSTGRES_INTEGRATION=1 \
ASHR_IDENTITY_LIFECYCLE_TEST_DSN=postgres://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable \
go test . -run '^TestIdentityLifecyclePostgresIntegration$' -count=1 -v
PASS
ok github.com/ashr-labs/ashr/packages/go/ashrclone 52.751s

go test ./... -count=1
PASS across ashrclone and all command packages

go vet ./...
PASS
```

The authoritative PostgreSQL integration used Docker container
`ashr-oauth-pg-test` and
`postgres://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable`.

The complete Python A1 suite result was:

```text
1393 passed, 2 skipped, 1 failed in 401.83s
```

The single failure was isolated and reproduced independently:

```text
python -m pytest \
  tests/a1/test_identity_verification_postgres_migration.py::test_live_retryable_proof_outbox_budget_and_runtime_boundary -q
1 failed in 9.61s
```

It expects migration 017's old
`a1_bind_verified_identity_credential` authority to reach an injected table
trigger, but migration 020 intentionally revoked that unsafe runtime function.
The observed error is therefore the pre-existing obsolete-authority mismatch:
`permission denied for function a1_bind_verified_identity_credential`. The
Round 67 retention migration does not grant or alter that function, and this
focused slice does not weaken the newer authority boundary to satisfy the
obsolete test.

## Next A1 item

Continue cross-language identity-security/client parity and production
lookup-key rotation drills after publishing bounded replay retention.
