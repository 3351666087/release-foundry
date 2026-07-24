# Ashr task ledger

Updated: 2026-07-24

This file is the repository-level crash-safe checklist. Check an item only
after its implementation or verification evidence is green. A1 records and
pushes only A1-owned work; A2/A3 paths may be exercised read-only by CL but
must not be included in A1 commits.

## A1 - current PostgreSQL OAuth first-login coordinator batch

- [x] Sync the dedicated A1 worktree with
  `origin/codex/a1-local-sdk-runner`, prove pre-commit `0/0` parity, and
  remove all accidental A2/A3 generated drift.
- [x] Implement migration 026 as the canonical PostgreSQL OAuth first-login
  authority for Google/GitHub unknown-subject registration, known-subject
  login, exact replay, verified-email conflict rollback, trusted scope,
  memberships, sessions, ACL/RLS, audit, and revocation outbox behavior.
- [x] Implement the production Go coordinator with domain-separated keyed
  digests, lookup-key rotation, serializable retry, strict result validation,
  stable non-disclosing errors, and a one-use post-commit access/refresh
  bearer receipt.
- [x] Add focused and live Docker PostgreSQL coverage for canonical account
  creation/login, replay, conflict rollback, RLS/ACL/trusted-scope failure,
  GitHub/Google parity, key rotation, session handoff, and raw-secret
  non-persistence.
- [x] Close the four-route TypeScript parity drift with explicit browser
  first-login gap contracts rather than pretending the routes are generic
  hosted JSON SDK surfaces.
- [x] Pass the complete Python, Go, TypeScript, Rust, Docker PostgreSQL, A3
  Node/webapp/E2E, evidence-gate, and release-delivery CL scope.
- [x] Pass final hygiene/commercial guards, `gofmt`, `git diff --check`,
  exact changed-path/A2/A3/generated-artifact audit, and changed-file secret
  audit.
- [x] Stage exactly the twelve A1-owned paths, review the staged diff, commit
  the complete coordinator batch, and push only
  `HEAD:codex/a1-local-sdk-runner`.
- [x] Verify implementation commit
  `0ce8252b18584d4c8f06962a8ed4facbe6c69cc5` was pushed only to
  `origin/codex/a1-local-sdk-runner` and is exactly `0/0` ahead/behind.
- [x] Commit and push A1 worklog/TASKS checkpoint
  `892553c85a16db5a265dd02a70275d6792fc7fdb`, fetch the remote, and prove
  `0/0` parity. This checked state is the final docs-only closeout.

## A1 - registration and login closure after this push

- [x] Add public Google/GitHub first-login start and callback endpoints with
  server-chosen purpose/scope, PKCE/state/nonce validation, encrypted
  HttpOnly browser intent, one-time callback consumption, secure
  access/refresh cookies, intent deletion, and empty-body `303 /console`
  handoff.
- [x] Keep first registration, ordinary login, and authenticated explicit
  credential binding as separate fail-closed operations over one canonical
  account; prove no email/provider inference can silently merge identities.
- [x] Return a browser-safe `challenge_id` for domestic-email verification
  and complete the verification-to-session/cookie/console handoff without
  exposing OTP, proof, bearer, OAuth code/state, or SMTP material.
- [x] Preserve domestic-email-first signup, optional/recommended 2FA, and
  honest non-production-ready WeChat/QQ/Alipay capability boundaries while
  keeping future domestic OAuth adapters compatible with the same canonical
  credential model.
- [x] Prove callback replay, account injection, subject collision,
  state/cookie/provider/purpose mismatch, revoked-session race,
  cross-tenant/project scope, provider/vault/database failure, and explicit
  binding authorization cannot cause takeover or partial canonical mutation.
- [ ] Wire production readiness only when provider adapters, trusted default
  scope, callback security, external opaque vault, PostgreSQL/RLS, key
  rotation, cross-language parity, and the complete CL are green.

## A1 - production registration/login runtime wiring (2026-07-24)

- [x] Re-enter the dedicated A1 worktree, confirm it is clean and exactly
  `0/0` against `origin/codex/a1-local-sdk-runner`, and verify the existing
  PostgreSQL test container name/port baseline without exposing secrets.
- [x] Audit the existing browser OAuth and domestic-email verification code;
  confirm the public handlers already implement challenge/session handoff
  contracts and isolate the current release gap to production runtime wiring
  and deployable adapter configuration rather than duplicating those flows.
- [x] Freeze fail-closed production runtime tests for Google/GitHub first-login
  capability completeness, trusted scope, exact callback, external opaque
  vault, PostgreSQL transaction storage, intent transport, and one-use
  access/refresh cookie handoff.
- [x] Implement the production external OAuth opaque-vault adapter and
  PostgreSQL first-login transaction adapter without persisting raw provider
  subject, email, OAuth code/state/nonce/verifier, provider token, or bearer.
- [x] Wire Google/GitHub public first-login services and browser intent/session
  transports into `ashr-api` only when every provider capability and trusted
  server-owned organization/project scope is valid.
- [x] Prove production email begin returns browser-safe `challenge_id` and
  verification completion produces secure access/refresh cookies, clears the
  intent, and returns an empty-body `303 /console` without A3-owned changes.
- [x] Re-prove registration/login/explicit-binding separation, callback replay
  and mismatch closure, canonical conflict rollback, RLS/ACL/key rotation,
  provider/vault/database failure atomicity, and honest domestic OAuth/2FA
  capability boundaries.
- [x] Pass focused, Go, live Docker PostgreSQL, Python/TypeScript parity, A3
  compatibility, full CL, formatting, diff, ownership/generated-path, and
  secret audits. The coherent A1 batch is ready for the commit/push gate.
- [ ] Commit the coherent A1 batch and push only A1 to
  `origin/codex/a1-local-sdk-runner`; fetch back and prove post-push `0/0`
  parity before checking this item.
