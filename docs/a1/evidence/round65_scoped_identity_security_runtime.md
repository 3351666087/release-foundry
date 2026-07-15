# Round 65: Canonical-Account Scoped Identity-Security Runtime

Date: 2026-07-14

## Scope

A1 now binds every production PostgreSQL password/MFA posture lookup, mutation
ticket resolution, and mutation execution to the canonical account selected by
the authenticated HTTP session.

The A3-facing resolver contract now requires the canonical account ID
explicitly. The Go PostgreSQL adapter validates that ID as a UUID, installs it
as transaction-local `app.a1_principal_id`, and invokes only principal-scoped
database functions. A returned ticket must identify exactly the requested
canonical account.

## Database authority

Migration `022_a1_scoped_identity_security_runtime.sql` adds scoped overloads:

```text
a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamptz)
a1_execute_identity_security_mutation(text,text,text,uuid)
```

Both require `a1_current_principal_id()` to equal the explicit principal ID.
They also verify that the persisted ticket belongs to that principal before
delegating to migration 018's private implementation authority.

The runtime role loses `EXECUTE` on the old unscoped resolver and executor and
receives only the scoped overloads. `PUBLIC` has no execution privilege, and
the runtime retains no direct table privileges over account-security,
receipts, tickets, or idempotency state.

`a1_project_account_security(uuid)` is also principal-scoped. Its public-safe
projection retains password availability, optional/recommended 2FA posture,
recovery-code count, security version, and active-session count without
projecting secret references, digests, recovery batches, or session digests.

## Fail-closed proof

The Docker/PostgreSQL test creates two canonical principals and issues a valid
password-enrollment receipt and ticket for principal B.

With transaction context set to principal A:

- B's security posture is rejected;
- B's scoped ticket resolution is rejected;
- B's scoped mutation execution is rejected;
- B's ticket and step-up receipt remain unconsumed.

With context set to principal B:

- the public posture succeeds and reports 2FA as optional and recommended;
- the public ticket envelope succeeds without trusted secret material;
- password enrollment succeeds;
- an exact replay with the same idempotency key and request fingerprint returns
  the stable original result.

## Verification

Executed verification:

```text
go test ./... -count=1
TestIdentityLifecyclePostgresIntegration: PASS
python -m pytest \
  tests/a1/test_scoped_identity_security_runtime.py \
  tests/a1/test_password_mfa_lifecycle_migration.py \
  tests/a1/test_verified_credential_mutation_authority.py \
  tests/a1/test_atomic_identity_credential_link_migration.py -q
31 passed
git diff --check
```

The live integration harness now applies migrations 001 through 022 and grants
its disposable constrained runtime role only the new scoped resolver and
executor signatures.
