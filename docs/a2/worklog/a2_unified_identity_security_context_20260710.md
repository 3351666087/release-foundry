# A2 unified identity security context

Date: 2026-07-10
Lane: A2 Evaluation / Policy / Security

## Upstream signal

A1 branch `origin/agent/a1-local-sdk-runner` advanced to `3367dc7` with:

- `services/api/migrations/007_a1_oauth_runtime_store.sql`
- `services/api/migrations/008_a1_unified_identity_account.sql`
- `services/api/migrations/009_a1_oauth_identity_coordinator.sql`
- `services/api/migrations/010_a1_identity_revocation_outbox.sql`
- `services/api/migrations/011_a1_identity_session_authentication.sql`
- `docs/a1/evidence/unified_identity_contract_20260710.json`
- `docs/a1/evidence/unified_identity_same_account_localhost_20260710.json`
- `docs/a1/evidence/google_oauth_localhost_evidence_20260710.json`

## A2 change

A2 now emits `a1_unified_identity_security` in the evidence readiness report.
The block is forward-compatible: it remains a stable missing object while the
A1 files are absent from `main`, and becomes a public-safe policy context when
the A1 SQL and evidence files are present.

The parser checks:

- canonical account and multi-provider credential model
- GitHub plus Google same-account localhost calibration
- same-email implicit merge rejection
- cross-account credential takeover rejection
- caller-supplied account mismatch rejection
- credential and membership decoupling
- digest-only identity storage
- opaque-reference-only OAuth secret storage
- tenant, project, and principal RLS
- public DTO allowlist and forbidden material exclusion
- identity audit/outbox, recovery, merge, append-only, and hard-delete guards
- provider revocation outbox lease fencing, external side-effect checkpoints,
  retry/backoff, dead-letter, and reconnect cleanup guards
- digest-only session authentication with active principal, credential, and
  tenant/project membership revalidation under restricted runtime role

## Boundary

This context does not unlock C3. It is policy/security context for A2 identity,
OAuth linking, membership-decoupling, and account-takeover regression cases.
The A1 evidence is localhost and public-safe; production readiness and pending
providers remain explicitly incomplete.
