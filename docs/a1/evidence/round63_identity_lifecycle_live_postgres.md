# Round 63 Live PostgreSQL Identity Security Lifecycle

Date: 2026-07-14

## Scope

This round strengthens the disposable live-PostgreSQL identity lifecycle
integration test. It proves that the canonical account, exact credential
binding, password enrollment, two-phase TOTP enrollment, session revocation,
security-receipt rotation/tamper handling, and row-level isolation operate
together against migrations 001 through 018.

No SQL validation was weakened and no process-memory security fallback was
introduced.

## Failure Diagnosis

The first live run rejected identity session and verified-email synchronization
inputs:

```text
pq: identity session input rejected (22023)
pq: verified email sync rejected (42501)
```

The test harness had pinned its application clock to July 12, 2026 while the
PostgreSQL server was running on July 14, 2026. That made the fixture session
already expired and placed OAuth step-up authentication outside the migration's
ten-minute recent-auth window.

The fix reads `clock_timestamp()` from each disposable target database and uses
that value as the harness application clock. Production constraints and
fail-closed behavior remain unchanged.

## Fresh-Cluster Corrections

- Ensure migration-owned role `a1_runtime` exists idempotently before applying
  migrations on a fresh disposable database.
- Apply migrations `001` through `018`, including the authoritative
  password/MFA lifecycle.
- Keep the disposable runtime role `NOSUPERUSER NOBYPASSRLS`.
- When the admin DSN uses a Unix-domain socket, replace only the disposable
  password-authenticated runtime DSN host with `127.0.0.1`. This avoids peer
  authentication incorrectly comparing the operating-system user with the
  generated PostgreSQL runtime role.

## Authoritative Password And TOTP Lifecycle

The previous fixture directly set `two_factor_status='enabled'` without TOTP
secret material. Migration 018 correctly rejected that invalid posture through
`identity_totp_posture_check`.

The test now uses the authoritative lifecycle:

1. Issue a scoped `password_enroll` security receipt.
2. Call `a1_mutate_account_password` with an opaque vault reference and keyed
   digest.
3. Issue a scoped `mfa_enroll` receipt.
4. Call `a1_begin_totp_enrollment`.
5. Issue a scoped `mfa_confirm` receipt.
6. Call `a1_confirm_totp_enrollment`.
7. Assert that all three receipts are consumed and at least one existing
   identity session is revoked.

No raw password, TOTP secret, recovery code, provider token, or private proof is
persisted in the test or emitted as public evidence.

## Real RLS Isolation

The integration test creates a second principal and security row, grants the
disposable runtime role only `SELECT` on `identity_account_security`, and sets
transaction-local `app.a1_principal_id` to the canonical account under test.

The `NOSUPERUSER NOBYPASSRLS` role sees:

```text
own rows: 1
foreign rows: 0
```

This exercises PostgreSQL policy enforcement rather than reproducing the
expected filter in application memory.

## Live Verification

Environment:

- WSL distribution: `Ubuntu-24.04-ReleaseFoundry`
- PostgreSQL: 16.14
- Admin connection: local Unix socket
- Migrations: 001 through 018

Authoritative command:

```powershell
wsl.exe -d Ubuntu-24.04-ReleaseFoundry -- bash /mnt/c/Users/33516/Documents/ReleaseFoundry-a1-live-test.sh
```

Result:

```text
PASS
ok github.com/3351666087/release-foundry/packages/go/releasefoundry 6.954s
```

Passing live coverage includes:

- Atomic registration, replay, registration/login separation, and rollback.
- OAuth-first canonical account and exact email credential projection.
- Public-safe account serialization.
- Authoritative password enrollment.
- Two-phase TOTP enrollment and confirmation.
- Single-use security-receipt consumption and session revocation.
- Receipt signing-key rotation and fail-closed tamper handling.
- Tamper rejection for `proof_ciphertext`, `proof_nonce`, `tenant_scope`, and
  `proof_key_version`.
- Real PostgreSQL RLS isolation using a non-bypass runtime role.

## Security Decision

Stale fixture time, invalid direct posture mutation, missing fresh-cluster role
prerequisites, and peer-auth DSN behavior were corrected in the harness. The
database's strict session, recent-auth, TOTP posture, receipt, and RLS
constraints remain authoritative.

The next production slice is a typed PostgreSQL-backed
`IdentitySecurityHTTPStore` that invokes migration 018 SECURITY DEFINER
functions atomically. Unsafe split-memory password/MFA stores remain fail
closed.
