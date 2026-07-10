# Round 51 Identity, OTP, and SMTP Evidence

Date: 2026-07-10

## Scope

This A1 slice hardens the canonical identity runtime, adds email and phone
verification contracts across Go, Python, and TypeScript, and calibrates a
development-only SMTP delivery path. It does not claim production OTP,
production SMS, or production account recovery readiness.

## Safe environment evidence

The following user-level environment variables were confirmed present without
printing their values:

- `ASHR_SMTP_HOST`
- `ASHR_SMTP_PORT`
- `ASHR_SMTP_FROM`
- `ASHR_SMTP_AUTH_CODE`

No sender address, recipient address, authorization code, OTP, provider
response, or message body is retained in this evidence file.

QQ Connect was evaluated as an account-login channel and rejected for the
current low-barrier path because the user-observed enrollment flow requires a
business license. Its disposition is `enterprise-only`. QQ Mail SMTP was
enabled by the human operator and is treated separately as an email delivery
calibration channel.

## Implemented

- PostgreSQL digest-only session authentication under a restricted runtime
  role, including principal, credential, organization membership, and project
  membership revalidation.
- Revocation outbox malformed-task dead lettering, lease fencing, dependency
  deadlines, renewal, event-specific metadata allowlists, and value-level
  secret rejection.
- Go email and phone verification lifecycle with HMAC digests, TTL, attempt
  caps, resend cooldown, and atomic single-use consumption.
- Python and TypeScript public verification contracts with canonical route and
  stable-error parity.
- Development-only implicit TLS SMTP sender with TLS 1.2 minimum, bounded
  context and connection deadlines, email-only delivery, header-injection
  prevention, and provider-error redaction.
- Runtime SMTP wiring that is opt-in and fail-closed. Production verification
  still requires an injected durable store and sender.

## Validation

```text
Go package tests: passed
Go vet: passed
Go integration tests: passed
Python focused identity/parity/migration tests: 60 passed
TypeScript build: passed
TypeScript full suite: 512 passed
Canonical identity parity: 12 routes, 28 stable errors, no differing fields
```

The opt-in real SMTP calibration sent exactly one self-addressed verification
message with a 15-second hard timeout. The command completed successfully in
approximately 2.3 seconds. Only the safe outcome class and duration are
recorded; the destination, code, authorization material, headers, and body
were not printed or persisted.

## Commercial disposition

This slice is suitable as a development calibration and contract baseline.
It is not production-ready because the production path still needs a durable
PostgreSQL challenge/receipt/cooldown store, transactionally consistent
receipt consumption and identity mutation, anti-enumeration behavior,
distributed abuse budgets, durable audit, production sender injection, and
an SMS provider.

The Growth-Auditor initially reported a Go compile blocker while the runtime
wiring existed before the SMTP sender landed. That blocker is now resolved
and the full Go module plus integration suite pass. Its remaining production
findings continue to apply.

## Next commercial priorities

1. PostgreSQL OTP challenge, receipt, cooldown, and append-only audit schema.
2. Atomic receipt consumption plus account or credential mutation.
3. Store interfaces that remove production HTTP dependence on memory identity.
4. Anti-enumeration response and timing controls.
5. Identifier, account, IP, tenant, and device abuse budgets.
6. Domestic SMS provider interface and one sandbox adapter.
7. STARTTLS 587 support where a provider requires it.
8. Production worker supervision for revocation and verification outboxes.
9. Vault-backed production GitHub and Google OAuth.
10. Session rotation families, reuse detection, inventory, and revoke-all.
