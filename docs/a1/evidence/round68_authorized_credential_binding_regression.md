# Round 68 - Authorized Credential-Binding Regression

Date: 2026-07-14

## Scope

This A1 slice closes the only known failure from the complete Python A1 suite
without restoring migration 017's obsolete direct credential-binding runtime
authority.

The live PostgreSQL verification test now exercises migration 020's
request-bound authorized wrapper:

`a1_bind_verified_identity_credential_authorized(...)`.

## Security contract

The regression provisions the same production prerequisites required by the
current binding path:

- an active canonical principal with tenant and project memberships;
- a verified login credential and recent scoped `aal1` session;
- a verified credential-binding proof receipt;
- a `credential_bind` step-up receipt bound to the request digest;
- a secret-free mutation ticket issued through
  `a1_issue_identity_security_mutation_ticket(...)`.

The test explicitly proves that `a1_runtime`:

- can execute only the authorized wrapper;
- cannot execute the old direct binding function;
- cannot mutate verification receipts directly.

## Transaction and concurrency proof

An injected `identity_credentials` insert failure occurs after the wrapper has
validated the session, locked the ticket, and attempted to consume the
step-up receipt. PostgreSQL transaction rollback preserves all three retry
inputs:

- the verification receipt remains verified and unconsumed;
- the step-up receipt remains unconsumed;
- the mutation ticket remains unconsumed.

Two independently authorized requests then race for the same verified proof.
Exactly one creates the credential and consumes its authorization pair. The
losing transaction leaves its own step-up receipt and mutation ticket
unconsumed. Exact replay returns the original credential, changed request
binding is rejected, cross-scope execution fails, and direct table mutation
remains denied.

No runtime grant was restored on
`a1_bind_verified_identity_credential(...)`.

## Verification

All commands ran in the isolated A1 worktree
`C:\Users\33516\Documents\Ashr-a1-sync` against Docker PostgreSQL container
`ashr-oauth-pg-test`.

```text
python -m pytest \
  tests/a1/test_identity_verification_postgres_migration.py::test_live_retryable_proof_outbox_budget_and_runtime_boundary \
  -q
1 passed in 9.07s

python -m pytest \
  tests/a1/test_identity_verification_postgres_migration.py \
  tests/a1/test_verified_credential_mutation_authority.py \
  tests/a1/test_scoped_identity_security_runtime.py -q
20 passed in 23.56s

python -m pytest tests/a1 -q
1394 passed, 2 skipped in 341.59s

python -m py_compile \
  tests/a1/test_identity_verification_postgres_migration.py
PASS

git diff --check
PASS
```

The complete A1 Python suite is now green. Round 67's sole known failure was
the obsolete direct-authority test path corrected by this round.

## Next A1 item

Continue production lookup-key rotation drills and cross-language
identity-security/client parity while preserving the canonical-account,
recent-session, step-up, and explicit-ticket binding boundary.
