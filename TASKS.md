# Ashr task ledger

Updated: 2026-07-24

This file is the repository-level crash-safe checklist. Check an item only
after its implementation or verification evidence is green. A1 records and
pushes only A1-owned work; A2/A3 paths may be exercised read-only by CL but
must not be included in A1 commits.

## A1 — current PostgreSQL OAuth first-login coordinator batch

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
- [ ] Stage exactly the twelve A1-owned paths, review the staged diff, commit
  the complete coordinator batch, and push only
  `HEAD:codex/a1-local-sdk-runner`.
- [ ] Verify the pushed implementation commit is `0/0`, record its SHA in
  this ledger and `docs/a1/worklog.md`, then push the A1 worklog/TASKS
  completion checkpoint and prove final `0/0` parity.

## A1 — registration and login closure after this push

- [ ] Add public Google/GitHub first-login start and callback endpoints with
  server-chosen purpose/scope, PKCE/state/nonce validation, encrypted
  HttpOnly browser intent, one-time callback consumption, secure
  access/refresh cookies, intent deletion, and empty-body `303 /console`
  handoff.
- [ ] Keep first registration, ordinary login, and authenticated explicit
  credential binding as separate fail-closed operations over one canonical
  account; prove no email/provider inference can silently merge identities.
- [ ] Return a browser-safe `challenge_id` for domestic-email verification
  and complete the verification-to-session/cookie/console handoff without
  exposing OTP, proof, bearer, OAuth code/state, or SMTP material.
- [ ] Preserve domestic-email-first signup, optional/recommended 2FA, and
  honest non-production-ready WeChat/QQ/Alipay capability boundaries while
  keeping future domestic OAuth adapters compatible with the same canonical
  credential model.
- [ ] Prove callback replay, account injection, subject collision,
  state/cookie/provider/purpose mismatch, revoked-session race,
  cross-tenant/project scope, provider/vault/database failure, and explicit
  binding authorization cannot cause takeover or partial canonical mutation.
- [ ] Wire production readiness only when provider adapters, trusted default
  scope, callback security, external opaque vault, PostgreSQL/RLS, key
  rotation, cross-language parity, and the complete CL are green.
