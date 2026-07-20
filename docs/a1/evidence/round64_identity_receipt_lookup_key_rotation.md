# Round 64: Independent Identity Receipt Lookup-Key Rotation

Date: 2026-07-14

## Scope

A1 now separates two lifecycle-receipt key responsibilities:

- proof-encryption keys protect the trusted identity proof ciphertext and are
  required only while an unconsumed proof may still need decryption;
- receipt-lookup keys produce keyed digests used to locate persisted lifecycle
  receipts and completed credential-link replay records.

This separation lets an operator retire an old proof-encryption key without
breaking an exact replay that has already completed. An unconsumed proof
encrypted with the retired key still fails closed and its internal key version
is not exposed through the A3-safe credential-link error.

## Production configuration

The existing encryption keyring remains:

```text
ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION
ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY
ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON
```

The optional independent lookup keyring is:

```text
ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_ACTIVE_VERSION
ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_KEY
ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON
```

The active lookup version and key must be configured together. Previous lookup
keys are rejected unless an active lookup key is also configured. Every key
must contain at least 32 bytes, versions must be valid and unique, malformed or
unknown JSON fields are rejected, and errors do not echo secret material.

When the optional lookup keyring is absent, A1 retains the legacy behavior and
derives lookup digests from the proof-encryption keyring. This compatibility
mode does not make legacy receipts independent of old encryption-key
retention.

## Safe rollout and rotation sequence

1. Introduce an independent lookup key while the current proof-encryption key
   is still available.
2. Keep the lookup key stable while rotating the active proof-encryption key.
3. Retain the previous proof-encryption key until no unconsumed proof created
   with that key may remain valid.
4. Retire the old proof-encryption key. Completed exact replay remains
   locatable through the stable lookup key; unconsumed old proofs fail closed.
5. Retain lookup keys for the full persisted receipt and idempotency replay
   window. Rotate or retire a lookup key only after rows using its digest
   namespace are migrated or no longer need replay.

Rows created before independent lookup-key rollout cannot automatically survive
retirement of the encryption key that produced their legacy lookup digest.
They require an explicit migration strategy or continued retention of the
corresponding legacy key during their replay window.

## Verification

The real PostgreSQL integration test proves:

- an OAuth credential-link command completed under `enc-old` replays exactly
  under `enc-new` with no old encryption key configured;
- replay returns the same credential ID and `linked_at`, with
  `credential_added=false`;
- an unconsumed proof issued under `enc-old` is located through the stable
  lookup key but rejected through the public-safe
  `identity_credential_link_unavailable` code;
- the failed attempt does not consume the proof, mutation ticket, or step-up
  authorization, because the old-key instance can still complete it;
- the database contains exactly three credentials and two completed-link audit
  events after the two legitimate mutations, with no duplicate replay
  mutation.

Executed verification:

```text
go test ./... -count=1
go vet ./...
TestIdentityLifecyclePostgresIntegration: PASS
python -m pytest tests/a1/test_atomic_identity_credential_link_migration.py -q
6 passed
git diff --check
```

Published A1 commit:

```text
6d4ba9c9c1c463267fa734c0589b509d46c96b0f
fix(a1): separate lifecycle receipt lookup keys
```
