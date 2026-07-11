# Round 52: Live PostgreSQL Identity Verification Evidence

Date: 2026-07-11

## Scope

This reviewer slice owns only:

- `tests/a1/test_identity_verification_postgres_migration.py`
- `docs/a1/evidence/round52_identity_verification_postgres_20260710.md`

It does not modify migration or implementation code, A2/A3 files, or shared
judge semantics.

## Environment

The live proof ran against:

```text
container: ashr-oauth-pg-test
image: postgres:16-alpine
database: PostgreSQL 16.14
server compiler: GCC 15.2.0
runtime role: a1_runtime
connection model: two independent docker exec + psql client processes
```

Each test run creates a fresh database, applies every migration in filename
order, executes with `ON_ERROR_STOP=1`, and drops the database afterward.

## Exact Transaction Outcomes

The live test proved:

1. Challenge issue through the restricted runtime role created exactly one
   delivery-outbox row and one five-dimensional abuse-budget row.
2. Verification produced a durable receipt in `verified` state.
3. An injected credential-insert failure propagated to the client and rolled
   back the whole bind transaction. The receipt remained `verified` with
   `consumed_at IS NULL`, so the proof stayed retryable.
4. Two independent `psql` connections then competed to bind that same receipt
   with different idempotency and request digests.
5. Exactly one connection committed and returned a valid credential UUID.
   Exactly one connection failed with a consumed-proof or
   `idempotency_conflict` outcome.
6. PostgreSQL contained exactly one active, verified email credential matching
   the returned UUID, principal, provider environment, and subject digest.
7. The receipt ended in `consumed` state with `mutation_kind = 'bind'`;
   `mutation_result_id`, `idempotency_digest`, and `request_digest` matched the
   winning transaction.
8. Replaying the winning idempotency and request digests returned the same
   credential UUID without creating a second credential.
9. Reusing the winning idempotency digest with a different request digest
   failed with `idempotency_conflict`.

## Exact Isolation Outcomes

The live restricted-role proof established both layers of the boundary:

- A call presenting a different session organization while requesting the
  original organization/project scope was rejected by the narrow
  `SECURITY DEFINER` entrypoint.
- Direct `UPDATE` of `identity_verification_receipts` by `a1_runtime` was
  rejected by table privileges/RLS.
- Static contract checks also confirmed forced RLS on all six verification
  tables and no direct runtime table grants.

## Validation

```text
python -m pytest tests/a1/test_identity_verification_postgres_migration.py -q -p no:cacheprovider
```

Final result:

```text
13 passed
```

The live race test was then repeated five times. All five fresh-database
iterations passed, covering ten independent competing `psql` connections with
exactly one committed bind per receipt:

```text
race iterations: 5/5 passed
independent competing connections: 10
committed winners: 5
rejected losers: 5
duplicate credentials: 0
```

The original live test first exposed a reviewer-test defect after the
one-winner race had already succeeded: it queried nonexistent tenant/project
columns on `identity_credentials`. The assertion was corrected to follow the
actual schema and strengthened with receipt terminal-state, exact replay,
same-key/different-request conflict, and cross-scope rejection checks. The
conflict request is selected relative to the actual concurrent winner so the
assertion remains valid regardless of scheduler order. No production semantics
were weakened.

## Secret Handling

No environment values, SMTP addresses, authorization codes, OTP values,
message bodies, or raw contact identifiers were read or recorded. The test
uses generated UUIDs and SHA-256 test digests only.

## Remaining Limits

This proof covers credential binding. It does not yet provide the same
independent-connection live race for login/session creation or account
recovery/session rotation, nor a process-restart persistence test. Those are
separate follow-up integration proofs rather than reasons to weaken this
credential-binding contract.
