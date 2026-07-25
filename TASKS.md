# Ashr task ledger

Updated: 2026-07-25

This file is the repository-level crash-safe checklist. Check an item only
after its implementation or verification evidence is green. A1 records and
pushes only A1-owned work; A2/A3 paths may be exercised read-only by CL but
must not be included in A1 commits.

## A1 - durable SDK event delivery / offline resume batch (2026-07-24)

- [x] Re-enter the dedicated A1 worktree, prove local/remote `0/0`, audit the
  strategy release gaps, and select the next A1-owned implementation slice
  without repeating the completed registration/OAuth runtime batch.
- [x] Freeze one Python/TypeScript event-envelope and durable-spool contract
  covering bounded batches, deterministic sampling, stable idempotency,
  retry/resume, and explicit backpressure/dead-letter behavior.
- [x] Implement the Python and TypeScript durable SDK spool with atomic local
  persistence, secret-safe metadata inspection, bounded storage, resumable
  flush, and parity helpers for the existing trace-ingestion contract.
- [x] Add Go-side hosted trace replay/idempotency evidence so an interrupted
  or repeated flush cannot double-count quota or create duplicate trace
  batches.
- [x] Carry the validated production `ASHR_GOOGLE_OAUTH_ENABLED` and
  `ASHR_GITHUB_OAUTH_ENABLED` flags into the PostgreSQL identity lifecycle
  capability response instead of hard-coding both capabilities to `false`;
  add a runtime assertion that configured providers are advertised as
  enabled only when their complete provider/vault/database graph is wired.
- [x] Add the operator-safe production Google/GitHub callback and
  secret-delivery deployment checklist; keep credentials out of the frontend,
  `NEXT_PUBLIC_*`, repository, documentation values, logs, and browser
  storage.
- [x] Pass focused Python/TypeScript/Go tests, cross-language parity, Docker
  PostgreSQL trace/quota replay coverage, full CL, formatting, ownership,
  generated-artifact, and secret audits.
- [x] Stage only A1-owned paths, commit the coherent batch, push only
  `HEAD:codex/a1-local-sdk-runner`, fetch back, and verify local/remote `0/0`;
  commit `1dd5e43f` was accepted on the A1-only remote branch.

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
- [x] Wire production readiness only when provider adapters, trusted default
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
- [x] Commit the coherent A1 batch as
  `596fde1966e1edd62e76885cd973c66338f2a383`, push only A1 to
  `origin/codex/a1-local-sdk-runner`, fetch back, and prove post-push `0/0`
  parity.

## A1 - external credential delivery and operator verification checkpoint (2026-07-24)

- [x] Re-confirm the dedicated A1 worktree is clean at the accepted remote
  baseline and preserve the A1-only push target.
- [x] Re-confirm local OAuth configuration records by presence/shape only;
  no secret values, mailbox credentials, tokens, or browser state are logged.
- [x] Add the production external Secret Manager/Vault OAuth client-credential
  resolver and fail-closed startup contract; support reference-based rotation.
- [x] Add resolver, startup, redaction, provider-isolation, and rotation tests.
- [x] Run focused, PostgreSQL, cross-language, complete CL, formatting, and
  ownership/secret audits.
- [x] Commit and push only A1 to `origin/codex/a1-local-sdk-runner`, then prove
  local/remote `0/0` parity. Implementation commit `5307d863` is the exact
  local/remote tip after the accepted A1-only push.
- [x] Verify or create the Google Web OAuth Client and GitHub OAuth App in the
  operator-owned consoles, deliver credentials through the production external
  Secret Manager/Vault, and complete real-HTTPS Google/GitHub first-login plus
  known-account E2E through the Chrome Extension. The controlled callback and
  database evidence is redacted; localhost is not used as production evidence.

## A1 - Chrome Extension real-HTTPS OAuth closure (2026-07-24)

The five operator deliverables requested for this closure are tracked
individually so console setup cannot be confused with an actually usable
first-login runtime:

- [x] Verify/create the Google Web OAuth Client with the exact production and
  controlled real-HTTPS callback paths through the Chrome Extension.
- [x] Verify/create the GitHub OAuth App with the exact controlled real-HTTPS
  callback path through the Chrome Extension.
- [x] Deliver both providers' Client ID/Client Secret pairs to the backend
  through the mTLS external Vault references, with no raw secret in the
  frontend, repository, documentation, browser storage, or runtime raw-secret
  environment.
- [x] Complete Google first-login on the controlled real-HTTPS domain through
  the Chrome Extension, including state/nonce/PKCE, canonical account,
  access/refresh cookie handoff, empty-body `303 /console`, replay rejection,
  and redacted database evidence. Repeat login reuses the credential/account
  and creates only a new session.
- [x] Complete GitHub first-login on the controlled real-HTTPS domain through
  the Chrome Extension with the same handoff, replay, failure-atomicity, and
  redacted database evidence. Repeat login reuses the credential/account and
  creates only a new session.

## A1 - production password and recommended optional 2FA closure (2026-07-24)

- [x] Re-enter the dedicated A1 worktree, prove exact remote `0/0` parity,
  confirm the Chrome Extension sees the operator-opened controlled HTTPS
  window, and record this checklist before implementation.
- [x] Recover the repository-external Docker runtime after the Windows restart:
  start the existing PostgreSQL/API/edge/Vault containers, unseal the
  persistent Raft Vault only from the DPAPI-protected local bootstrap,
  restore local API/edge health, and prove the new quick-tunnel `/health` and
  Extension-claimed `/console` expose both provider entries without reading
  browser storage or any OAuth/session/secret material.
- [x] Freeze the A3-safe begin/confirm contract for password
  enroll/change/recovery and TOTP enroll/confirm: raw password, TOTP secret,
  OTP, recovery codes, refs, and keyed digests must never enter the existing
  opaque mutation endpoints, logs, repository, or browser storage.
- [x] Implement a fail-closed mTLS external Vault secret processor that
  accepts secret material only on the dedicated trusted backend boundary,
  returns opaque one-use delivery plus server-keyed digests, supports
  reference-based key rotation, and cleans up partial writes.
- [x] Implement an independent restricted PostgreSQL mutation-ticket issuer
  runtime using only the `a1_security_ticket_issuer` role/DSN; bind canonical
  account, actor/session, operation, context, recent step-up receipt, TTL, and
  idempotency without granting issuer authority to `a1_runtime`.
- [x] Wire password recovery and authenticated password/TOTP begin/confirm
  handlers to the processor, receipt authority, ticket issuer, and existing
  atomic mutation executor while keeping 2FA optional and recommended.
- [x] Return TOTP enrollment material and recovery codes through one-use,
  no-store, browser-safe handoff only; prove replay, concurrency, account
  injection, CSRF, operation/context/receipt mismatch, expiry, and
  Vault/PostgreSQL failure atomicity.
- [x] Promote only the actually routable password/security/TOTP contracts
  from `proposed` to `active` and add strict Python/TypeScript DTO/client
  parity without claiming unsupported recovery-code/disable routes.
- [x] Pass focused Go/HTTP/runtime tests, live restricted-role PostgreSQL/RLS
  integration, Vault rotation/redaction/failure tests, complete
  Python/TypeScript/Rust parity, formatting, full CL, ownership, generated
  artifact, and secret audits.
- [x] Update the A1 evidence/worklog after each earned gate, commit one
  coherent A1-only batch, push only
  `HEAD:codex/a1-local-sdk-runner`, fetch, and prove final `0/0` parity.
  The 52-path implementation batch was committed as
  `ff4167e94d13d7eda7a729fee812ec32cc79704c`; the only push target was the
  A1 branch and the fetched post-push divergence was `0/0`.

Implementation and release gates discovered by the real runtime exercise:

- [x] Start the production identity runtime with the restricted
  `a1_runtime` PostgreSQL role (`NOSUPERUSER`, `NOBYPASSRLS`, `NOINHERIT`) and
  pass production schema/readiness without using the `postgres` superuser DSN.
- [x] Preserve the already-registered quick-tunnel hostname while restoring
  the exact external Host through a controlled local reverse proxy; the
  real-HTTPS health check is green and no secret crosses that edge.
- [x] Replace the first-login store's forbidden direct sensitive-table insert
  with a scoped, security-definer PostgreSQL entrypoint; make readiness prove
  its ACL/owner/search-path/RLS boundary and add a restricted-role integration
  test.
- [x] Permit a standard same-origin browser top-level navigation to the public
  OAuth start route without weakening the strict Origin contract used by
  mutation requests; reject cross-site, malformed, non-navigation, and
  forwarded-host spoofing cases.
- [x] Apply migration 027, rebuild/restart the restricted-role runtime, and
  prove local/real-HTTPS health plus explicit-Origin and standard same-origin
  top-level navigation preflights for Google and GitHub.
- [x] Re-run all four main Go packages and the Go integration module after the
  readiness change; extend the disposable restricted-role PostgreSQL harness
  for migration 027 and pass the complete identity/OAuth lifecycle integration
  matrix against migrations 001-027.
- [x] Diagnose the Chrome Extension handoff without switching browser
  surfaces: Chrome is running, the Extension is installed/enabled in the
  selected `Default` profile, and the registered Native Messaging Host,
  expected Extension origin, and manifest path are correct. Open a fresh
  `Default`-profile Chrome window for the operator to enter the controlled
  `/console` URL without exposing an OAuth-bearing URL.
- [x] Restrict the repository-external nginx E2E edge to a safe access-log
  shape containing only status, method, and path; exclude query arguments,
  Referer, Cookie, client address, and the complete request. Confirm the
  blocked automated Google attempt produced no canonical principal,
  credential, session, first-login operation, or opaque token mutation; only
  one additional pending Google runtime transaction exists.
- [x] Have the operator open the controlled `/console` URL in that exact
  Extension-selected window; then retain that tab for both provider flows
  without standalone Playwright, another browser, raw CDP, or an indirect
  navigation bridge.
- [x] Reproduce the real Google callback shape and harden the callback parser
  to accept only Google's documented single-valued `iss`, `scope`, `authuser`,
  and `prompt` additions while preserving strict `code`/`state` bounds,
  malformed-query rejection, provider-specific allowlists, and GitHub's
  `code`/`state`-only contract. Re-run all Go packages plus the restricted-role
  PostgreSQL identity/OAuth lifecycle integrations.
- [x] Correct the second incompatibility exposed by the real Google callback:
  canonicalize first-login transaction `created_at`/`expires_at` to UTC
  microsecond precision before deriving the Vault envelope/binding or issuing
  SQL, so strict Vault/PostgreSQL binding validation survives a real
  `TIMESTAMPTZ` round trip.
- [x] Add non-microsecond-aligned unit and live PostgreSQL regressions proving
  the canonical Vault envelope and SQL arguments agree, the restricted
  runtime role consumes the transaction, and the external opaque reference is
  deleted exactly once. Re-run all four Go packages and both complete
  restricted-role PostgreSQL integration suites.
- [x] Rebuild/restart the restricted-role runtime, complete both provider
  first-login and known-account Extension E2E flows, and update only redacted
  aggregate/provider-set release evidence.
- [x] Run the final focused/full cross-language, PostgreSQL, CL plan, hygiene,
  commercial, formatting, secret, ownership, and generated-artifact audits.
- [x] Commit the exact 13-path A1 batch as
  `086622c7b13f5cfb6fdf63f217e78b03694c0291`, push only
  `HEAD:codex/a1-local-sdk-runner`, fetch the remote, and prove post-push
  local/remote parity `0/0`.

## A1 - TOTP disable and recovery-code lifecycle closure (2026-07-25)

- [x] Restore the existing password/TOTP enrollment baseline after introducing
  the private processor-state store: legacy begin/confirm flows no longer
  require that optional store, while the three new lifecycle mutations still
  fail closed without it. All Go packages pass.
- [x] Reconnect only through the operator-authorized Chrome Extension in the
  newly opened window and re-run both live Google and GitHub HTTPS OAuth
  round-trips. Each provider returned to the controlled `/console` landing
  page; no browser cookie/storage, callback parameter, provider token, account
  identity, or secret was inspected or retained. A repeat-only aggregate
  PostgreSQL check held Google and GitHub canonical credential counts at `2`
  each while total/active sessions advanced from `16` to `18`.
- [x] Re-check the five operator OAuth deliverables after the latest Chrome
  window handoff. The Google Web client, GitHub OAuth App, four external-Vault
  credential references, and exact HTTPS callback registrations remained in
  place. The controlled bridge token had expired and both start routes failed
  closed; rotate it from the DPAPI-protected bootstrap without exposing any
  token or client secret, restore both starts to `302`, and complete fresh
  Google/GitHub Extension round-trips. Canonical credential counts stayed at
  `2` per provider while total/active sessions advanced from `18` to `20`.
- [x] Freeze the A3-safe production contract for recent-authenticated TOTP
  disable, one-time recovery-code authentication/consumption, and recovery-code
  rotation. Raw TOTP secrets/codes and recovery codes must remain confined to
  the trusted processor boundary and must never enter public mutation tickets,
  PostgreSQL, logs, repository artifacts, frontend state, or result DTOs. The
  exact operation split, request shapes, idempotency binding, response
  invariants, and nested-secret rejection pass the focused Python/round54
  group (`77 passed`) and TypeScript build/identity group (`71 passed`).
- [x] Extend the external mTLS Vault processor with account-bound,
  constant-time recovery-code verification, atomic single-code consumption,
  deterministic replay handling, recovery-batch rotation, and TOTP-disable
  cleanup/compensation across active and previous processor keys. The focused
  lifecycle/concurrency suite passed 25 repeated runs, and the live external
  Vault harness passed TLS 1.3 mutual authentication, one-winner CAS,
  consume/rotate/disable replay rules, rollback/finalize behavior, key
  rotation/retirement, read-only/timeout/outage failure, and redacted logs
  across `165` Vault TLS requests.
- [x] Add the scoped PostgreSQL/RLS mutation lifecycle for `mfa_disable`,
  `mfa_recovery_consume`, and `mfa_recovery_rotate`, including restricted
  issuer/runtime ACLs, recent-auth/CSRF/session binding, idempotency,
  concurrency, security-version advancement, session revocation, audit, and
  outbox guarantees. Migration 029 now has a dedicated clean-apply/live-Docker
  PostgreSQL suite covering consume/rotate/disable, exact replay and payload
  conflict, wrong-account and stale-state rejection, concurrent exactly-once
  consume, private processor/replay projections, five forced-RLS policies,
  restricted login-member ACLs, and public-result redaction; the focused
  migration/scoped-runtime/verification group passes `24` tests.
- [x] Wire the Go runtime, issuer, store, service, HTTP routes, startup
  readiness, and processor client/server so all three operations are callable
  only through their intended trusted/public boundaries and 2FA remains
  optional but recommended. Go formatting is clean; every main-module package
  passes, the focused recovery lifecycle passes 25 repeated runs, and the live
  PostgreSQL lifecycle integration passes against migrations 001-029.
- [x] Add strict Python/TypeScript DTO, route, parsing, and client parity;
  promote only implemented routes and keep every secret/ref/digest/ticket
  absent from A3/browser-visible responses. The round54 schema and evidence
  now expose active consume/rotate/disable routes while retaining only
  existing-account credential linking as proposed.
- [x] Export the recovery lifecycle result DTO and all three exact route
  helpers from the public Python package barrel, and prove top-level imports
  resolve to the strict unified-identity implementations (`62 passed`).
- [x] Update the production deployment contract with all six strict
  API-to-processor mTLS URLs, migration 029/RLS rollout requirements, exact
  consume/rotate/disable operations and routes, recent-auth/CSRF/session
  binding, atomic security-version/session/audit/outbox effects, prepare →
  PostgreSQL mutation → finalize ordering, cleanup compensation, one-use
  no-store rotation handoff, and private/public secret-material boundaries.
- [x] Regenerate and validate the public TS/Python symbol/contract matrix and
  Go/Python/TypeScript route snapshot. Add the three snake-case TypeScript
  parity aliases plus explicit generic-SaaS gap records for routes owned by
  the dedicated unified identity client. The generated contracts report
  unified-identity parity, Go `100`, Python `35`, TypeScript `38`, and the
  complete focused evidence group passes `27` tests.
- [x] Pass the uncached Go main-module test suite for all five packages,
  `go vet ./...`, and the standalone `tests/integration/go` test/vet module.
- [x] Re-run the complete live Docker PostgreSQL identity lifecycle against
  migrations 001-029 (`39.15s`, all subtests passed) and the migration
  029/scoped-runtime/verification RLS group (`24 passed in 32.55s`).
- [x] Fix the one full-suite-discovered round54 drift by keeping the three
  active TypeScript recovery/disable route declarations statically
  inspectable by the shared HTTP boundary test. Round54 passes `26` tests,
  TypeScript builds cleanly, and its unified-identity suite passes `71`.
- [x] Pass Python compileall and the complete A1 Python suite after the
  manifest correction: `1450 passed, 5 skipped` in `338.25s`.
- [x] Pass the complete release Python gate: `33 passed` with only the known
  upstream `jsonschema.RefResolver` deprecation warning.
- [x] Run the broad repository pytest gate: `2178 passed, 14 skipped` in
  `407.03s`. The only two failures are peer-owned A2 generated-fixture drift
  where `a2_cross_lane_security_context.json` still records A1 route count
  `102` while the current builder observes `111`; do not regenerate, modify,
  restore, stage, or commit any `fixtures/a2/**` artifact from the A1 lane.
- [x] Pass the complete TypeScript package matrix: the first run exposed that
  the generic hosted Go-route gap registry had not delegated the three new
  recovery/disable routes to `UnifiedIdentityHttpClient`; after adding those
  explicit public-safe records and coverage, build plus all `667` tests pass.
- [x] Pass the complete Rust runtime verifier gate: `cargo fmt --check`,
  all-target/all-feature Clippy with warnings denied, and every unit plus
  integration test (`31` total) are clean.
- [x] Re-run the repository-external live Vault processor closeout: TLS 1.3
  mTLS on both hops, projected-token isolation, active/previous key rotation
  and retirement, concurrent one-use handoff, cleanup compensation, recovery
  consume/rotate/disable, read-only/timeout/unavailable failure paths, and
  redacted logs all pass across `162` Vault TLS requests.
- [x] Pass focused replay/concurrency/wrong-account/stale-ticket/CSRF/
  recent-auth/session-revocation/Vault-failure/PostgreSQL-failure/key-rotation
  tests plus live Docker PostgreSQL/RLS and external-Vault validation.
- [x] Complete the final generated/format integrity pass: all `19` changed Go
  files are `gofmt` clean from the repository root, generated TS/Python parity
  check is current, its focused evidence group passes `27` tests, all `21`
  changed JSON files parse, `git diff --check` is clean, and Python compileall
  succeeds.
- [x] Pass `python scripts/cl_guard.py plan --full`; the selective CI planner
  resolves the full Python/A3/TypeScript/Go/Rust/integration/evidence matrix.
- [x] Pass `python scripts/cl_guard.py hygiene` with zero findings, including
  the repository high-confidence secret and hygiene blockers.
- [x] Pass `python scripts/cl_guard.py commercial`: all `20` blocker anchors
  and `4` advisory anchors are present, with zero blockers or advisories.
- [x] Build and validate the closeout ownership manifest: exactly `41`
  changed/untracked A1 paths fall under the documented A1 platform/runtime/
  identity/SDK/migration/test boundaries, with zero invalid or
  `fixtures/a2/**` paths.
- [x] Secret-scan the exact staged A1 diff. CL hygiene has zero findings;
  redacted Gitleaks triage classified its five generic candidates as
  test-only `idem-` replay keys, and a narrowly scoped default-rule rerun
  reports no leaks without adding an allowlist to the repository.
- [x] Update A3-safe evidence, parity snapshots, deployment/runtime docs, and
  this worklog only after each gate is earned; pass full Go/Python/TypeScript/
  Rust/CL/ownership/generated-artifact/secret checks.
- [x] Precisely stage only the `41` A1-owned paths, commit the coherent batch
  as `cbd465b7`, push only `HEAD:codex/a1-local-sdk-runner`, fetch, and prove
  local/remote `0/0` parity with zero staged `fixtures/a2/**` peer artifacts.

## A1 authoritative tenancy lifecycle batch (2026-07-25)

- [x] Freeze the PostgreSQL-authoritative organization/project/environment
  lifecycle contract, A3-safe public DTOs, trusted-session boundary, strategic
  organization/project roles, idempotency rules, and actor/request/trace/audit
  invariants before implementation.
- [x] Add migration `030_a1_tenancy_lifecycle.sql` with lifecycle state,
  strategic role constraints, mutation idempotency, audit/outbox emission,
  restricted runtime grants, and FORCE RLS for every new tenant-owned table.
  A fresh disposable PostgreSQL database applied migrations `001-030`; the
  focused live suite passes `5` tests covering exact replay, payload conflict,
  cross-tenant isolation, last-owner rejection, concurrent exactly-once
  effects, append-only receipts, FORCE RLS, and the two-function runtime ACL.
- [x] Implement the scoped PostgreSQL tenancy store and runtime initialization
  without accepting caller-supplied account ownership or introducing a second
  authoritative in-memory tenancy path. PostgreSQL runtime readiness now
  requires migration 030 and constructs a store limited to
  `a1_tenancy_query` / `a1_tenancy_mutate`; memory mode does not advertise the
  authoritative routes.
- [x] Add authenticated Go HTTP routes for organization/project/environment
  create/list/update/archive/restore/enable/disable plus project membership
  set/revoke/list, reusing the trusted identity Session resolver. All 14
  routes derive the caller only from canonical `Session.AccountID`, reject
  identity overrides, and emit strict no-store public envelopes.
- [x] Enforce active membership, role authorization, cross-tenant/project
  isolation, last-owner protection, idempotent replay, payload-conflict
  rejection, and concurrent exactly-once lifecycle effects. The fresh Docker
  migration suite passes `5` tests and the permanent Go live integration
  passes against migrations `001-030` with restricted runtime credentials,
  including readiness, exact replay/conflict, cross-tenant opacity,
  last-owner rejection, 12-way exactly-once mutation, and real HTTP routing.
- [x] Add strict Python SDK DTOs, parsers, route helpers, and client methods for
  the implemented tenancy surface while rejecting private refs, digests,
  tickets, raw policy internals, and arbitrary account/actor overrides. Added
  `packages/sdk/ashr_clone/tenancy.py`, root exports, and
  `tests/a1/test_tenancy_sdk.py`: all 14 exact route/client operations use the
  origin-bound browser cookie jar, mutation idempotency is header-only,
  response DTO/envelopes reject unknown/private/cross-scope content, public
  errors accept only the four frozen keys, HTTPS is mandatory outside an
  explicitly controlled localhost, and no API accepts a caller principal or
  session override. The tenancy, browser-session, and SDK-distribution focused
  group passes `31` tests.
- [x] Add matching TypeScript SDK DTOs, validators, route helpers, and client
  methods. Added frozen `ashr.clone.tenancy.v1` DTO/envelope/error types,
  all 14 exact route helpers and browser-safe client operations, root/subpath
  exports, Python-style aliases, strict response/scope/private-field
  validation, header-only idempotency, browser-managed same-origin
  credentials with no Cookie input/header, HTTPS-by-default, and controlled
  localhost opt-in. TypeScript builds cleanly and `tenancy.test.mjs` passes
  all `9` tests.
- [x] Regenerate Go/Python/TypeScript route and public-symbol parity artifacts
  with the new tenancy module and exact 14-route surface. The generated
  contract reports Go `114`, Python hosted `35` plus tenancy `14`, TypeScript
  hosted `38` plus tenancy `14`, and exact three-language tenancy parity with
  zero provider-only routes; writer/check and the focused evidence/SDK group
  pass `38` tests.
- [x] Add focused migration/RLS/ACL, Go runtime/HTTP/store, Python, TypeScript,
  A3-safe schema, cross-tenant, replay, conflict, concurrency, and last-owner
  regression tests. The focused PostgreSQL/Python/A3/parity group passes `69`,
  the uncached Go main and integration modules plus vet pass, and the complete
  TypeScript package passes all `676` tests after adding tenancy to the strict
  reusable-module and package-export inventories.
- [x] Update production deployment/runtime documentation and A1 evidence for
  migration 030, restricted PostgreSQL roles, trusted Session authorization,
  lifecycle routes, audit/outbox, and rollback requirements. Corrected the
  canonical caller boundary to trusted `Session.AccountID`, added the
  route-first/data-preserving rollout and rollback runbook, and published the
  A3-safe round 69 evidence without tenant identities or secret material.
- [x] Run focused and full Go/Python/TypeScript/PostgreSQL/generated checks,
  `gofmt`, `go vet`, `git diff --check`, and the complete CL plan/hygiene/
  commercial gates; fix every A1-owned failure. Python compileall and the
  complete A1 suite pass `1473` tests with `5` intentional skips; migration
  030 live PostgreSQL passes `5`, Go main/integration test and vet gates pass,
  the explicit Go PostgreSQL tenancy integration passes, TypeScript builds and
  passes `676`, release passes `33`, Rust fmt/clippy and all `31` tests pass,
  generated parity and JSON checks are current, `git diff --check` is clean,
  and CL full-plan/hygiene/commercial report zero findings or blockers.
- [x] Build the exact A1 ownership manifest, secret-scan the exact staged diff,
  and prove no `fixtures/a2/**`, secret, browser credential, or peer-owned path
  is staged. The repository-external manifest contains exactly `35` A1 paths,
  matches the index exactly, leaves all `253` peer-owned A2 working-tree paths
  unstaged, and has zero staged `fixtures/a2/**`. Replaced static live-test key
  material with runtime `crypto/rand` data and constructed long test
  idempotency keys from bounded parts; the final redacted staged gitleaks scan
  reports zero findings without a committed allowlist.
- [x] Precisely stage, commit, and push only this A1 batch to
  `origin/codex/a1-local-sdk-runner`; fetch and prove local/remote `0/0`
  parity. Committed the exact 35-path manifest as `6f80469f` with `10,288`
  insertions and `26` deletions, pushed only
  `HEAD:codex/a1-local-sdk-runner`, fetched the target, and proved `0/0`
  parity while all peer-owned `fixtures/a2/**` changes remained unstaged.
