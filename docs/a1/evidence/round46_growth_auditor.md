# Round 46 Growth / Money-Grade Audit

Date: 2026-07-10
Role: Growth-Auditor / Money-Grade Auditor
Workspace: `C:\Users\33516\Documents\Ashr_a1_clean_rebase`
Branch: `codex/a1-local-sdk-runner-clean`
Audited HEAD: `5dbf4ee2ab4c0ea8568623899244070dce9f9ce4`

## 1. Executive Verdict

Round 46 has materially improved the commercial payment foundation:

- focused Python Stripe/payment/OAuth tests pass `30/30`;
- the TypeScript package builds and its Stripe executor tests pass `14/14`;
- Python and TypeScript require an explicit Checkout `payment` or
  `subscription` mode and reject raw card material;
- the previously verified Go package/integration tests and `go vet` passed
  before the latest main-thread edits; the current package test gate is red
  because the new deterministic-list test uses `reflect.DeepEqual` without
  importing `reflect`;
- Postgres payment reconciliation now has composite tenant/project identity,
  digest-only evidence, Serializable transactions, row locking, replay
  recognition, and conflicting-digest rejection.

These are meaningful contract and durability gains. The reconciliation layer
is no longer a toy insert table, and TypeScript no longer trails the Python
Stripe safety boundary covered by this round.

The overall decisions remain:

- **Round 46 commit quality: NO-GO until the minimum list in section 4 is
  resolved or explicitly scoped out behind a non-production boundary.**
- **Real Stripe test-mode hosted Checkout: GATED.** It can be the next
  controlled provider test after the human/environment gates in section 5.
- **Money-grade or production authentication/payment claim: NO-GO.**
- **Human provider-account preparation: GO with the non-mutating boundary in
  section 5. Account-backed money-path execution: NO-GO.**
- **Private commercial preview: CONDITIONAL GO** for SDK integration, local
  runner, typed contracts, test-only payment development, and disposable
  self-host evaluation with explicit limitations.

The principal remaining risk is not missing field coverage. The Go
reconciliation feature is now reachable through the runtime, HTTP routes,
route manifest, and hosted client, but the reachable contract exposes
`verify`, `apply`, and `fail` as ordinary SDK mutations under the same
`billing:webhook` scope. It also parses JSON before any provider signature
proof and applies the billing event and reconciliation status in separate
transactions. A caller can therefore assert verification, and a crash can
split the money effect from the terminal reconciliation state.

## 2. Scope And Verified Integration Result

This audit reviewed the current tracked and untracked change set, including:

- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`;
- Python payment, Stripe executor, OAuth, and control-plane paths;
- TypeScript Stripe executor implementation and focused tests;
- Go/Postgres payment reconciliation implementation and integration tests;
- commercial Compose and payment-readiness evidence;
- current repository status and changed-file inventory.

No A3-owned path appeared in the current changed-file inventory. This auditor
changed only this report and did not inspect or output any secret value.

### 2.1 Focused Python verification

```powershell
python -m pytest -q `
  tests/a1/test_stripe_executor.py `
  tests/a1/test_payment_oauth_safety.py `
  tests/a1/test_round45_provider_adapters.py
```

Result: `30 passed in 0.30s`.

### 2.2 TypeScript verification

```powershell
npm run build --prefix packages/ts/ashr-clone
node --test --test-concurrency=1 `
  packages/ts/ashr-clone/test/stripe-executor.test.mjs
```

Result: build passed; `14 passed, 0 failed`.

The focused suite covers:

- explicit `payment` and `subscription` Checkout modes;
- rejection of ambiguous or unsupported mode;
- rejection of raw card material before provider execution;
- live-plan rejection;
- concurrent identical-request collapse;
- idempotency replay and conflict;
- digest-only webhook evidence.

### 2.3 Go verification

With Go temporary output directed to a D-drive temporary directory:

```powershell
go test ./...
go vet ./...
```

Result in `packages/go/ashrclone`: pass.

```powershell
go test ./...
go vet ./...
```

Result in `tests/integration/go`: pass.

An earlier combined command resolved the integration path relative to the Go
package directory and failed to locate it. Running from the correct repository
path passed; this was command context, not a code or assertion failure.

### 2.4 Postgres reconciliation verification

The current implementation now provides:

1. Composite identity:
   `PRIMARY KEY (tenant_id, project_id, provider, provider_event_id)`.
2. Composite project ownership rather than provider-event-only identity.
3. Digest-only payload, header, and failure evidence.
4. `sql.LevelSerializable` receive and transition transactions.
5. `FOR UPDATE` locking before mutable state transitions.
6. Idempotent replay when the same provider event and digest recur.
7. Conflict rejection when a reused provider event carries another digest.
8. Explicit reconciliation state transitions and tenant/project predicates.

This closes stale findings that the table lacked tenant-aware uniqueness,
transaction isolation, row locking, or idempotency conflict handling. It does
not by itself prove RLS, webhook-to-ledger atomicity, or exactly-once domain
effects.

### 2.5 Go HTTP, runtime, and hosted-client integration audit

The latest integration is broader than the earlier repository-only state:

1. `BackendSelection` creates a reconciliation service for memory and
   Postgres backends.
2. The Postgres backend migration runs the base migration and payment
   reconciliation migration.
3. The Go API process injects the selected reconciliation service into
   `HTTPServerOptions`.
4. The HTTP server exposes receive, list, get, verify, apply, and fail routes.
5. The route manifest and billing scope documentation include those routes.
6. The Go hosted client exposes methods for every route, including verify,
   apply, and fail.
7. The receive/list/get paths use billing webhook-ingest or billing-read
   preflight scopes and tenant/project arguments.

This is real runtime and client integration, not an orphan service. It also
makes the remaining defects release-blocking rather than theoretical:

- the public receive route accepts a caller-computed hash envelope, not exact
  provider webhook bytes plus a signature header;
- the public verify route changes `received` to `verified` without invoking a
  provider signature verifier;
- the public apply route first calls `IngestBillingWebhook` and then performs
  a separate reconciliation transition;
- verify/apply/fail are ordinary hosted-client methods and use the broad
  `billing:webhook` scope rather than an internal worker identity or a
  separately approved operator command;
- the Go Checkout and portal routes still return deterministic
  `billing.local.ashr.invalid` plans with `provider_called=false` and
  `real_charge_possible=false`; no provider execution is reachable through
  the Go runtime.

Goal alignment is therefore mixed. Wiring reconciliation through the Go
runtime advances the large-SaaS plan. Exposing internal state transitions as
customer SDK operations and calling a two-transaction sequence "apply" moves
away from the plan's auth, audit, tenant, and billing invariants. The correct
commercial boundary is public provider ingress, privileged operator reads and
replay requests, and internal worker-owned verification/application.

### 2.6 Latest main-thread fix audit

This subsection supersedes earlier green statements for the files currently
being edited by the main thread.

#### MemoryService billing webhook idempotency: not closed

`MemoryService.IngestBillingWebhook` takes `IdempotencyOptions`, holds the
service mutex, normalizes the event, appends it to `service.billingEvents`,
and appends an audit event. It does not call `idempotentReplay`, inspect
`options.Key`, or save an idempotency record. Therefore:

- same key plus same fingerprint is not marked as an idempotent replay;
- same key plus another fingerprint is not rejected;
- repeated delivery creates another ledger event and another audit event;
- the mutex prevents a data race but serializes duplicate side effects rather
  than suppressing them.

Required code fix:

1. Build the fingerprint from the normalized, public-safe event projection,
   including tenant, project, provider, provider event ID, event type, mode,
   payload digest, and all fields that can change money/entitlement behavior.
2. Under the existing mutex, check the billing-webhook idempotency record
   before appending either the billing event or audit event.
3. Return the original stored response with `IdempotentReplay=true` for the
   same key/fingerprint.
4. Return `IdempotencyConflictError` for the same key and another fingerprint.
5. Persist the idempotency record only with the ledger and audit mutation in
   the same critical section. Do not reuse the generic helper if doing so
   would require unsafe type assertions or save the record after effects.

Required tests:

- same key/same normalized event yields one ledger row and one audit row;
- same key/different payload digest or provider event ID returns conflict and
  leaves ledger/audit counts unchanged;
- 32 concurrent identical calls yield one non-replay result, 31 replay
  results, one ledger row, and one audit row;
- no-key behavior is explicitly defined and tested; a production webhook path
  should derive a stable provider-event key instead of accepting omission.

#### Reconciliation list determinism: test started, implementation not closed

The newly added
`TestMemoryPaymentReconciliationListIsDeterministicBeforeLimit` is directionally
correct but currently does not compile because `reflect` is not imported.
After that import alone, the implementation would still fail: the memory
repository iterates a Go map and stops when `limit` is reached, so it truncates
before sorting. The Postgres query orders by
`received_at DESC, provider_event_id DESC`; this is not a total order when two
providers reuse an event ID at the same timestamp, and it does not match the
new test's oldest-first expectation.

Required code fix:

1. Choose and document one public order. This audit recommends newest-first:
   `received_at DESC, provider DESC, provider_event_id DESC`.
2. In memory, collect every matching row, sort using that exact tuple, then
   apply `limit`.
3. In Postgres, add `provider DESC` to the same `ORDER BY`.
4. Add equal-timestamp, cross-provider, repeated-call, status-filter, and
   limit-boundary cases. Assert memory and Postgres fixtures return the same
   IDs in the same order.
5. Import `reflect` or compare the short ID slices without it so the package
   test compiles.

#### Go HTTP reachable-path coverage: not yet present

The current `server_test.go` contains billing-plan/webhook scaffold tests but
no test function that exercises the reconciliation HTTP routes. Repository
unit tests and a live Postgres repository test do not prove the runtime route,
auth, manifest, or hosted-client contract.

Required tests before the route family is considered integrated:

- receive/list/get happy path with the configured reconciliation capability;
- `503 payment_reconciliation_unavailable` when it is absent;
- missing auth, wrong scope, tenant mismatch, project mismatch, and revoked
  key denial;
- same digest replay and conflicting digest `409`;
- deterministic list ordering through HTTP after the limit is applied;
- manifest and hosted-client parity for the retained public surface;
- non-internal callers receive fail-closed denial or `404` for
  verify/apply/fail in every non-local profile;
- an internal worker identity can perform the reviewed transition only after
  verified evidence exists;
- crash/fault injection between domain effect and terminal state proves
  recovery with one effect.

Current command result:

```text
go test ./...
packages/go/ashrclone/payment_reconciliation_test.go:243:7:
undefined: reflect
```

The current Go package gate is therefore red. Do not retain the earlier green
claim in commit evidence without rerunning package test/vet and integration
test/vet after the fixes.

#### Public verify/apply/fail decision

**Yes: these routes must be disabled or internalized in this round.** They are
currently present in `server.go`, the route/scope manifest, billing docs
grouping, and ordinary methods in `hosted.go`. A customer key with
`billing:webhook` can call them. `verify` does not verify a provider
signature; `apply` accepts caller-provided event fields and crosses two
transactions; `fail` accepts caller-selected failure evidence.

The minimum acceptable Round 46 shape is:

- remove verify/apply/fail from the customer hosted client, public manifest,
  and public OpenAPI/SDK contract;
- make those commands unreachable in non-local profiles, preferably by
  registering them only on an internal listener;
- require workload identity with a distinct internal scope and audience;
- keep human recovery as an audited replay/request command with actor, reason,
  ticket, expected state, and approval, not as a direct target-state setter;
- treat the current caller-digest receive route as internal/test-only until a
  dedicated exact-byte provider ingress derives identity and digests after
  signature/freshness verification.

Changing the scope string while retaining the same public route and client is
not sufficient.

## 3. Remaining P0 Contract And Security Bugs

### P0-1: OAuth commercial mutation routes permit missing authentication

`auth_key_id` remains optional on OAuth provider configuration,
authorization begin/complete, direct session creation, and session revocation.
The router passes the optional value through, and service methods authenticate
only when it is present.

Impact: a route exposed as a commercial/public API can mutate OAuth
configuration or identity/session state without proving an authorized actor.
This is acceptable only inside an explicitly isolated local test harness. It
is a P0 if reachable through the commercial API.

Required closure: require authenticated server context and an appropriate
scope on every commercial OAuth mutation, or move the unauthenticated scaffold
behind a local-only route that cannot be enabled in production.

### P0-2: A mismatched OAuth callback consumes the legitimate pending flow

Wrong state, PKCE verifier, or redirect URI currently changes a pending flow
to terminal `failed`.

Impact: anyone able to submit a callback against a known or leaked flow ID can
deny the legitimate callback. State and PKCE mismatches should be rejected and
audited without consuming the flow. A provider terminal denial may use a
separate terminal transition policy.

Required closure: implement non-consuming mismatch handling, attempt limits
that do not create an easy denial primitive, atomic legitimate consumption,
and regression tests.

### P0-3: OAuth authorization flows have no enforced expiry

Flows record creation time but no effective `expires_at`, and completion does
not reject stale flows.

Impact: old authorization state remains usable beyond a defensible browser
handoff interval and enlarges replay and support-recovery risk.

Required closure: add a short configurable TTL, persisted expiry, atomic
one-time consume, expired status, cleanup, and boundary tests.

### P0-4: OAuth completion trusts caller-supplied identity and token references

The completion and direct session paths accept caller-supplied `subject_ref`,
provider-code reference, access-token reference, and refresh-token reference.
There is no demonstrated provider token exchange, issuer/audience/nonce
validation, userinfo retrieval, or binding of the provider subject to the
created session.

Impact: this is a session-construction scaffold, not proof of GitHub or Google
authentication. It must not issue a trusted production application session.

Required closure: either mark and enforce the route as non-authenticating
test-only infrastructure or complete real provider exchange and identity
validation before creating a trusted session.

### P0-5: The Stripe SDK transport is still an injected facade

The Stripe executor depends on `StripeSDKFacade`; focused tests use fake or
recording implementations. No concrete, pinned official Stripe SDK transport
and no real hosted Checkout evidence were established by this audit.

Impact: the repository proves executor policy, not provider interoperability.
It cannot claim that a Checkout Session was created, returned safely, signed
events were delivered, or provider errors were normalized correctly.

Required closure: add a concrete test-mode-only facade, strict timeouts,
bounded retries, safe error mapping, and one smallest real hosted Checkout
evidence run.

### P0-6: Stripe execution idempotency is process-local

The executor's default idempotency mapping is in memory under a process-local
lock.

Impact: restart and multi-worker execution can repeat the external side effect.
The stronger Go/Postgres reconciliation table does not protect the outbound
Checkout creation operation before the provider call.

Required closure: persist an operation fingerprint and state machine in
Postgres, use a transactional outbox or equivalent claim protocol, and prove
same-key replay plus conflicting-key behavior across restart and two workers.

### P0-7: Verification, reconciliation, and money application are not one
proven atomic path

The Go HTTP `apply` path currently:

1. reads the reconciliation row;
2. calls `IngestBillingWebhook`;
3. calls `PaymentReconciliationService.Apply`.

The billing mutation and reconciliation transition are separate repository
operations and transactions. No current evidence proves:

`raw request bytes -> signature and freshness verification -> durable receive
-> unique provider event -> tenant-scoped ledger/entitlement mutation ->
applied status`

as one atomic or explicitly compensating lifecycle.

Impact: a crash can leave an event verified but not durable, durable but not
applied, applied twice, or marked applied before all money-bearing effects
commit.

Required closure: connect the verifier to reconciliation through a durable
inbox/outbox transaction and prove duplicate delivery, conflicting digest,
crash recovery, and exactly one terminal domain effect.

### P0-8: Database-level tenant isolation for reconciliation is not proven

Composite keys and predicates are correct application-layer improvements, but
this audit did not find live evidence that the new reconciliation table is
protected by Postgres RLS under a `NOBYPASSRLS` application role.

Impact: an omitted predicate or privileged connection can bypass tenant
isolation on money-bearing data.

Required closure: add and force RLS, use tenant/project session context or
another reviewed DB policy, and run positive and cross-tenant denial tests
under the real application role.

### P0-9: Public HTTP and hosted-client contracts can assert trusted
reconciliation transitions

The Go server and hosted client expose:

- `payment.reconciliation.verify`;
- `payment.reconciliation.apply`;
- `payment.reconciliation.fail`.

All three mutations are authorized with `billing:webhook`. `verify` performs
no provider signature or freshness verification. `apply` accepts a
caller-supplied billing event body and can invoke the billing mutation before
marking reconciliation applied. `fail` accepts a caller-supplied failure
digest. The hosted SDK makes these operations appear to be supported
customer-facing commands.

Impact: a key with webhook-ingest scope can promote a caller-created digest
envelope into a trusted money lifecycle. The contract confuses provider
ingress, internal worker authority, and human operator recovery authority.

Required closure: remove verify/apply/fail from the customer hosted client and
public API contract. Keep exact-byte webhook ingress public only to the
provider-facing endpoint. Make verification and application internal
worker/service commands authenticated by workload identity. If manual replay
is required, expose a separate approval command that records actor, reason,
ticket, expected state, and audit event without directly selecting the target
state.

### P0-10: The Go webhook ingress loses the provider-signature boundary

`handleBilling` reads a JSON object before the reconciliation handler receives
the request. The reconciliation receive operation accepts
`payload_sha256`/`headers_sha256` supplied by the caller. It does not hash the
exact request bytes at the trusted edge, verify the Stripe signature and
timestamp, or bind the verified provider event ID to those bytes.

Impact: digest-only storage is safe for evidence retention, but a
caller-supplied digest is not authenticity evidence. Parsing before
verification also prevents a correct Stripe signature check over the original
bytes.

Required closure: add a dedicated bounded raw-body endpoint, preserve exact
bytes only in memory through signature verification, derive all digests
server-side, reject stale or malformed signatures, and persist only the
allowlisted event projection plus digests. The generic JSON reconciliation
receive route must remain internal/test-only or be removed.

### Security items that remain P1 unless exposed unsafely

1. `tolerance_seconds=0` disables Stripe timestamp freshness. Production
   configuration should reject zero rather than interpret it as unlimited.
2. Add a bounded webhook body size before signature decoding and persistence.
3. Prove dual-secret webhook rotation with an overlap and retirement window.
4. Keep OAuth secret/token reference topology in executor-only structures;
   public API, logs, audit, analytics, and support exports should use digests
   or presence bits only.
5. Add explicit redaction tests for provider SDK exceptions and HTTP bodies.

## 4. Minimum Must-Fix Before Round 46 Commit

This is the minimum commit-quality gate, not the complete money-grade gate.
The auditor must not implement these business-code fixes.

1. **Close or isolate unauthenticated OAuth mutations.** Require a scoped
   authenticated actor on commercial routes, or make the scaffold local-only
   and fail closed in commercial/prod profiles.
2. **Fix OAuth mismatch consumption.** Add tests proving wrong state, PKCE,
   and redirect do not permanently consume the pending legitimate flow.
3. **Add OAuth flow expiry.** Persist `expires_at`; reject and audit stale
   completion; prove one-time atomic consumption.
4. **Block trusted sessions from caller assertions.** Caller-supplied
   subject/token references must create only a marked test scaffold, never a
   trusted production session.
5. **Keep real Stripe network execution disabled until durable operation
   idempotency exists.** A clear runtime gate is acceptable for this commit;
   durable Postgres operation state is preferred.
6. **Do not publish trusted reconciliation transitions as customer
   mutations.** Remove or production-disable hosted-client and public HTTP
   verify/apply/fail. Internal worker commands require workload identity and
   least-privilege scopes.
7. **Add the exact-byte provider ingress boundary.** The trusted edge must
   bound the body, verify signature/freshness before JSON parsing, derive
   digests server-side, and bind provider event identity to verified bytes.
8. **Make money application atomic or durably compensating.** Billing ledger,
   entitlement/quota, audit/outbox, and reconciliation terminal state must
   commit together or use a proven claim/outbox protocol. The current
   `IngestBillingWebhook` then `Apply` sequence is not commit-ready for a
   production-enabled profile.
9. **Add HTTP/runtime/hosted-client integration tests.** Prove auth denial,
   tenant mismatch denial, unavailable capability behavior, same-digest
   replay, conflicting digest, internal-only transition enforcement, restart
   recovery, and route-manifest/client parity.
10. **Add an integration test for the event boundary.** Prove a verified event
   enters the correct tenant/project reconciliation row, same-digest replay is
   idempotent, and another digest conflicts.
11. **Add reconciliation RLS or record it as an explicit deployment blocker.**
   No money-grade or production-enabled profile may claim tenant isolation
   without the live `NOBYPASSRLS` denial test.
12. **Correct readiness wording.** Documentation must say Go reconciliation
   is runtime-wired but unsafe for public transition control, while Stripe
   provider
   execution is facade-tested and real test-mode Checkout is not yet proven.
13. **Review the intended commit inventory.** Round 46 contains many untracked
   implementation, test, migration, and evidence files; stage only reviewed
   A1 files and do not omit dependencies required by the green tests.
14. **Run the final gate from the staged tree:** `git diff --check`, Python
    `30/30`, TypeScript build plus `14/14`, Go package/integration tests, and
    Go package/integration vet.

If items 1-4 are intentionally deferred, the relevant OAuth routes must be
disabled in every non-local profile before the round is commit-ready.

### 4.1 Latest Go payment minimum closure

For the main thread's current reconciliation slice, the smallest defensible
P0/P1 closure before commit is:

1. **P0 - Internalize trusted transitions.** Remove public
   verify/apply/fail client methods and manifest entries, fail closed outside
   local tests, and add an internal workload-identity authorization test.
2. **P0 - Do not expose caller-digest ingress as provider authenticity.**
   Keep it internal/test-only; add a bounded raw-byte endpoint that verifies
   provider signature and freshness before JSON parsing and derives event ID
   and digests server-side.
3. **P0 - Remove the two-transaction apply window.** Move billing domain
   mutation, entitlement/quota update, audit/outbox, and terminal
   reconciliation transition into one Postgres transaction, or implement a
   durable claimed inbox/outbox state machine with crash recovery.
4. **P0 - Fix MemoryService webhook idempotency.** Same key/same fingerprint
   must replay with no duplicate ledger/audit effects; same key/different
   fingerprint must conflict; concurrent duplicates must collapse.
5. **P1 - Finish deterministic list behavior.** Sort before limit in memory,
   use the same total order in Postgres, fix the missing test import, and add
   memory/Postgres parity coverage.
6. **P1 - Add actual HTTP reachability and denial tests.** Cover configured
   and unavailable capability, auth/scope/tenant/project denial, replay,
   conflict, ordering, internal transition denial, and manifest/client parity.
7. **P1 - Restore all Go gates.** Package test/vet and integration test/vet
   must run green from the intended staged tree; the current package test is
   red.

The P0 items may be scoped out of a commit only by making the affected routes
unreachable in every commercial, self-host production, and cloud profile and
labeling the feature experimental/local-only. Documentation alone is not a
runtime boundary.

## 5. Human And Environment Gates Before Real Stripe Test Checkout

This section is only for a Stripe **test-mode hosted Checkout**. Live mode must
remain hard-disabled.

### 5.1 Human Account Operator boundary

The account boundary has four roles:

1. **Human Account Owner:** creates or selects the provider test account,
   completes provider identity/business onboarding, approves test/live mode
   and provider objects, and authorizes secret installation. The owner never
   gives raw secrets, card/wallet data, OTPs, recovery codes, or identity
   documents to code, prompts, logs, fixtures, or evidence.
2. **Human Account Operator:** creates the test Product/Price/Customer and
   webhook endpoint, approves success/cancel origins, performs the hosted
   browser Checkout, reviews the provider Dashboard result, and initiates the
   approved test refund/cancel. Card entry happens only on the
   provider-hosted page. The operator records only safe object references,
   digests, modes, statuses, timestamps, and redacted screenshots.
3. **System/automation:** resolves secret references transiently, creates the
   hosted session through the official SDK, receives bounded raw webhook
   bytes, verifies signature/freshness, persists digest-only evidence, and
   applies ledger/entitlement effects atomically. Automation must stop before
   any human credential, card/wallet, OTP, or provider recovery input.
4. **Reviewer/approver:** reviews redacted evidence, approves widening test
   volume, and separately approves any future live pilot. Live mode remains
   disabled this round.

Current launch decision:

- **Account preparation GO:** the owner/operator may select the Stripe test
  account, confirm test mode, approve one Product/Price design, currency,
  amount, payment methods, callback origins, support details, and a redacted
  evidence template. Secret references may be installed through an approved
  environment or secret manager without revealing values. Configuration may
  be validated while provider transport is disabled.
- **Money-path execution NO-GO:** do not create a Checkout Session through
  this product, trust a delivered webhook, apply an entitlement/ledger effect,
  run a refund/compensation workflow, widen volume, or perform any live-mode
  action until section 4.1 P0 items and the engineering gates below pass.
- **Operator authority limit:** the operator may create provider-side test
  objects and perform provider-hosted test actions after engineering approval,
  but may not call reconciliation verify/apply/fail, edit internal ledger
  state, install secrets into source/logs, or bypass workload identity.

Ordered human/system actions:

1. The Account Owner selects the intended Stripe test account and confirms
   test mode.
2. The Account Owner approves one test Product and Price, permitted payment
   methods, currency, amount, support details, and the HTTPS callback origins.
3. The Account Owner or authorized Operator installs the test key and webhook
   secret through a secret manager or process environment without exposing
   values to the repository, prompt, evidence, or command transcript.
4. The system validates configuration, object mode, endpoint mode, and
   callback allowlists with provider transport disabled.
5. The system creates exactly one smallest test Checkout Session through the
   official SDK.
6. The Operator opens the Stripe-hosted page and enters Stripe test data only
   there.
7. The system receives exact raw bytes, verifies the signature and timestamp,
   persists the event, and applies one atomic money/entitlement lifecycle.
8. The system proves duplicate replay, conflicting digest rejection, and
   restart recovery.
9. The Operator initiates or explicitly approves one test refund/cancel in
   the provider surface.
10. The system reconciles exactly one compensation and produces redacted
    evidence.
11. The Reviewer signs off before any volume expansion. A separate explicit
    approval and compliance review is required before any live-mode pilot.

### 5.2 Engineering/environment gates

8. Install and pin the official Stripe SDK and implement the concrete
   `StripeSDKFacade`.
9. Enforce test-key/test-object/test-endpoint mode and keep live execution
   impossible through configuration alone.
10. Configure strict provider timeouts, bounded retries, safe error mapping,
    request correlation, and response-field allowlisting.
11. Provision disposable Postgres, queue/worker, and object storage; apply the
    reviewed migrations.
12. Enable durable outbound-operation idempotency before the provider call.
13. Enable the reconciliation inbox, composite uniqueness, Serializable
    transition path, RLS, and audit linkage.
14. Configure the Stripe webhook endpoint and preserve exact raw request bytes
    before any JSON parsing.
15. Enforce a nonzero timestamp tolerance and verify system clock
    synchronization.
16. Add a bounded webhook body size and reject malformed/multi-value signature
    envelopes safely.
17. Use Stripe CLI or Dashboard test delivery to establish endpoint
    connectivity and the separate test webhook secret.
18. Run a dry-run contract validation with provider transport disabled.

### 5.3 Smallest evidence sequence

19. Create exactly one smallest test-mode Checkout Session and record only
    safe response keys, mode, status, and opaque/digested references.
20. Open the returned Stripe-hosted URL and complete payment with Stripe test
    data entered only on Stripe's page.
21. Receive and verify the signed completion event from exact raw bytes.
22. Persist the event under the correct tenant/project, apply one entitlement
    or ledger transition, and mark it applied in an atomic or explicitly
    compensating transaction.
23. Redeliver the same event and prove idempotent replay with no second domain
    effect.
24. Submit the same provider event reference with another digest in the local
    integration harness and prove conflict rejection.
25. Restart the API or worker between receipt and application and prove
    recovery without loss or duplication.
26. For subscription mode, verify the initial invoice/subscription references
    and their tenant/project binding.
27. Run a test cancellation or refund and prove the compensating ledger and
    entitlement transition.
28. Save redacted private evidence: purpose, expected scope, command, status,
    response key names, safe object references/digests, webhook event type,
    reconciliation state, and test result. Store no key, secret, raw card
    value, raw webhook body, or unrestricted provider response.

Only after this sequence is reviewed should test volume or additional payment
methods increase.

## 6. Next-Round A1 Growth Backlog

Priority is ordered by security and revenue-path dependency, then commercial
leverage. The list intentionally exceeds 20 items.

| Rank | Priority | Growth item | Exit evidence |
|---:|:---:|---|---|
| 1 | P0 | Require scoped authentication for every commercial OAuth mutation | Missing/invalid key denied; authorized path green |
| 2 | P0 | Make state/PKCE/redirect mismatches non-consuming | Legitimate callback succeeds after hostile mismatch |
| 3 | P0 | Add OAuth TTL, atomic consume, terminal states, and cleanup | Fresh/stale/replay/concurrent completion tests |
| 4 | P0 | Implement real GitHub token exchange and subject binding | Test login, userinfo, logout, revoke evidence |
| 5 | P0 | Implement Google OIDC discovery, nonce, issuer, audience, and signature checks | Test login, refresh, revoke evidence |
| 6 | P0 | Add concrete official Stripe SDK facade in test mode | One safe real Checkout Session response |
| 7 | P0 | Persist outbound Stripe operation idempotency | Restart and two-worker duplicate suppression |
| 8 | P0 | Replace caller-hash ingress with bounded exact-byte provider ingress | Server-derived digest after signature proof |
| 9 | P0 | Remove verify/apply/fail from customer hosted clients and public routes | Public contract exposes no trusted state setter |
| 10 | P0 | Add workload identity and internal scopes for verifier/applier workers | Customer API keys denied on internal commands |
| 11 | P0 | Atomically apply reconciliation to payment, entitlement, quota, audit, and outbox | Crash injection yields one terminal effect |
| 12 | P0 | Add and force Postgres RLS for reconciliation and all money tables | `NOBYPASSRLS` cross-tenant denial |
| 13 | P0 | Add transactional inbox/outbox and worker delivery claims | Restart-safe receive, publish, and apply |
| 14 | P0 | Add Go HTTP/runtime/client contract tests for auth, tenant, replay, conflict, and restart | Full reachable-path suite green |
| 15 | P0 | Run the smallest real Stripe test-mode hosted Checkout lifecycle | Checkout, webhook, replay, ledger evidence |
| 16 | P0 | Implement test refund/cancel compensation | Exactly one reversal and entitlement update |
| 17 | P0 | Enforce webhook size, timestamp, signature, and redaction bounds | Altered/stale/oversize/error-leak tests |
| 18 | P0 | Add dual-secret/key rotation windows | Old/new overlap then old-secret rejection |
| 19 | P1 | Persist Stripe customer/subscription/invoice/payment/refund/dispute projections | Provider/internal drift query |
| 20 | P1 | Implement subscription renewal, upgrade, downgrade, proration, dunning, and grace | State-machine fixtures and provider test events |
| 21 | P1 | Build entitlement projection and repair jobs | Rebuild equals online projection |
| 22 | P1 | Add dead-letter, dual-approval replay request, and operator workflow | Sanitized DLQ and audited replay |
| 23 | P1 | Reconcile metered usage, quota, invoice lines, and provider totals | Explainable per-tenant variance report |
| 24 | P1 | Add multi-currency, tax, credit-note, and rounding rules | Golden ledger fixtures |
| 25 | P1 | Add Stripe Connect/account scoping if marketplace billing is required | Wrong-account event denied |
| 26 | P1 | Persist OAuth users, identities, sessions, org membership, and account links | Restart and tenant-isolation tests |
| 27 | P1 | Encrypt provider token references and metadata with rotation | Rotation and revoked-key recovery test |
| 28 | P1 | Publish typed OpenAPI for safe Go payment read/ingress contracts | Generated contract and route suite agree |
| 29 | P1 | Generate Python and TypeScript clients from one versioned OpenAPI contract | CI rejects handwritten drift |
| 30 | P1 | Maintain Python/TypeScript parity for payment, identity, errors, and all five modalities | Shared golden fixtures pass both SDKs |
| 31 | P1 | Run two or more long-lived workers with lease/reclaim/fencing | No duplicate active or terminal effect |
| 32 | P1 | Add OpenTelemetry and SLOs for payment, OAuth, worker, quota, and reconciliation | Tenant-safe traces, metrics, alerts |
| 33 | P1 | Store signed evidence bundles in tenant-scoped object storage | Checksum, retention, and cross-tenant denial |
| 34 | P1 | Run clean-volume commercial Compose recovery and backup/restore | Fresh setup plus restored invariants |
| 35 | P1 | Implement WeChat Pay hosted executor and platform certificate verification | Valid/altered/stale/rotated notification tests |
| 36 | P1 | Implement Alipay hosted executor and canonical signature verification | Valid/altered/stale/duplicate notification tests |
| 37 | P1 | Add API-key creation, revoke, rotation, rate-limit, and usage-ledger restart tests | Revoked key denied across all services |
| 38 | P1 | Add release gate binding commit, migrations, image digests, config, and provider evidence | Unreviewed environment cannot enable release |
| 39 | P1 | Add Human Account Operator runbook with role separation and evidence allowlist | Dry run stops at every human-only boundary |
| 40 | P1 | Add provider mode/object/account consistency checks before transport | Mixed-mode and wrong-account objects denied |
| 41 | P1 | Add safe provider error taxonomy and support correlation | No provider body or secret in errors |
| 42 | P2 | Add customer billing/usage export and admin reconciliation UI contract | Export totals match internal ledgers |
| 43 | P2 | Add incident, dispute, refund, provider-outage, and credential-rotation runbooks | Tabletop evidence and owner mapping |
| 44 | P2 | Add PCI, privacy, retention, deletion, backup, and access-review evidence | Reviewed compliance control matrix |

## 7. Recommended Parallel Combination

### Lane A: OAuth trust boundary

Ranks 1-5 and 23-24. Close authentication, callback lifetime, non-consuming
mismatch, provider verification, durable identity, and token protection before
calling the feature login.

### Lane B: Stripe outbound execution

Ranks 6-7, 12-17, and 21-22. Build a test-only official SDK transport and
durable operation claims, then execute one bounded Checkout and compensation
lifecycle.

### Lane C: Webhook and money transaction

Ranks 8-14, 17-18, and 21-24. Own exact-byte verification, internal transition
authority, inbox/outbox, reconciliation, RLS, ledger/entitlement atomicity,
rotation, replay approval, and drift repair.

### Lane D: Go platform and SDK parity

Ranks 28-32 and 37-41. Stabilize the safe Go/OpenAPI surface, generate Python
and TypeScript clients, keep five-modality parity, and add long-lived worker,
observability, API-key, release, operator, provider-mode, and error gates.

### Lane E: Storage, deployment, and regional payments

Ranks 30-33 and 36-38. Prove clean deployment and evidence storage while
WeChat Pay and Alipay cryptographic integrations advance independently behind
disabled production gates.

Recommended merge order:

1. Remove public trusted-state setters and add exact-byte webhook ingress.
2. Add internal workload identity, reconciliation RLS, and one atomic
   inbox/ledger/entitlement/audit/outbox transaction.
3. Add reachable-path Go HTTP/runtime/client tests and restart/crash proofs.
4. OAuth public-route authorization, mismatch, and TTL fixes.
5. Durable Stripe outbound idempotency and concrete test facade.
6. Smallest real test-mode Checkout, replay, restart, and refund evidence.
7. Durable identity/provider exchange.
8. Safe Go/OpenAPI generated SDK parity and worker HA.
9. Storage, observability, backup/restore, wallet providers, and release gate.

## 8. Final Commit Gate

Before committing this round:

```powershell
git diff --check

python -m pytest -q `
  tests/a1/test_stripe_executor.py `
  tests/a1/test_payment_oauth_safety.py `
  tests/a1/test_round45_provider_adapters.py

npm run build --prefix packages/ts/ashr-clone
node --test --test-concurrency=1 `
  packages/ts/ashr-clone/test/stripe-executor.test.mjs

# From packages/go/ashrclone
go test ./...
go vet ./...

# From tests/integration/go
go test ./...
go vet ./...
```

Previously verified results before the latest reconciliation edits:

- Python: `30/30`.
- TypeScript focused Stripe executor: `14/14`, build green.
- Go package: test and vet were green before the latest reconciliation test
  was added. They are not green in the current worktree.
- Go integration: test and vet green.

Current-worktree recheck on 2026-07-10:

- `packages/go/ashrclone: go test ./...` fails at compile time because
  `payment_reconciliation_test.go` calls `reflect.DeepEqual` without importing
  `reflect`.
- `packages/go/ashrclone: go vet ./...` fails on the same compile error.
- `tests/integration/go: go test ./...` passes.
- `tests/integration/go: go vet ./...` passes.

Also run a bounded secret scan over the staged files and print only file names,
rule IDs, and counts. Do not print matching values.

Additional Round 46 Go payment gate:

1. No customer API key can call verify/apply/fail.
2. No public SDK presents trusted reconciliation state setters.
3. Provider ingress verifies exact raw bytes before parsing.
4. Digests and provider identity are derived by the trusted edge.
5. One transaction or reviewed durable workflow owns ledger, entitlement,
   quota, audit/outbox, and terminal reconciliation state.
6. The application role proves RLS denial across tenant and project.
7. Route manifest, OpenAPI, Go hosted client, Python client, and TypeScript
   client agree on the safe public surface.
8. Live mode remains disabled and Go Checkout remains accurately labeled
   plan-only until official provider transport evidence exists.

### 8.1 Minimal implementable public/internal boundary

This is the smallest acceptable Round 46 boundary. It deliberately preserves
repository/service state-machine tests and worker implementation options while
removing customer authority over trusted money state.

**Public/customer surface**

1. The public API mux may expose reconciliation `receive`, `list`, and `get`
   only. `receive` remains experimental/internal-ingress quality until exact
   provider bytes are verified before parsing; it must not be described as a
   provider webhook endpoint.
2. The public mux must not register paths ending in `/verify`, `/apply`, or
   `/fail`. A customer request to those paths must receive `404` in every
   production, commercial, self-host, and default profile. Returning `403`
   behind the same public handler is weaker because it preserves a published
   mutation contract and risks later scope expansion.
3. Remove the three state-setter entries from `GoRouteManifest`, route-scope
   docs, OpenAPI output, generated clients, and examples. The public manifest
   must contain no `payment.reconciliation.verify`,
   `payment.reconciliation.apply`, or `payment.reconciliation.fail`
   operation.
4. Remove `VerifyPaymentReconciliationHTTP`,
   `ApplyPaymentReconciliationHTTP`, `FailPaymentReconciliationHTTP`, and the
   generic customer action helper from `hosted.go`. Customer SDKs may retain
   receive/list/get only.
5. Do not solve this by renaming `billing:webhook` to an "internal" scope.
   Customer API-key authentication and the public listener are the wrong trust
   boundary regardless of scope spelling.

**Internal worker/test surface**

1. Keep `PaymentReconciliationService.Verify`, `.Apply`, and `.Fail` as
   unexported-to-network domain operations for repository tests and worker
   orchestration. Direct service calls in Go tests are acceptable.
2. If HTTP is required for worker integration, create a separate internal
   handler/mux and listener. It must not be mounted under the public
   `/v1/projects/.../billing` router and must not appear in public
   route/OpenAPI manifests.
3. The internal listener requires workload identity with a dedicated audience,
   for example `ashr-payment-worker`, plus a distinct transition permission.
   A customer API key, even one holding `billing:webhook`, must always fail.
4. Bind the authenticated workload to the tenant/project/job claim. The worker
   may transition only the event claimed by its durable job; request-body
   tenant, project, provider, event ID, target state, and failure evidence are
   not independent authority.
5. `verify` is an output of provider signature/freshness verification, not a
   callable assertion. `apply` is an output of the reviewed transactional
   money workflow, not a second mutation after ledger effects. `fail` records
   a classified worker failure with server-derived evidence and audit context.
6. Local tests may construct the internal handler explicitly. Production
   constructors must default it off and require explicit internal-listener
   configuration plus workload-identity verifier injection.

**Recommended code shape**

- `NewHTTPHandler` / the public server constructor registers only the safe
  customer surface.
- An explicit `NewInternalPaymentWorkerHandler` owns transition commands and
  accepts a workload-auth verifier and transactional payment application
  service.
- The worker calls the internal application service directly when co-located;
  the internal HTTP handler is only for a separately deployed worker.
- A compile-time/public-surface test prevents the removed customer client
  methods and manifest operations from returning unnoticed.

This boundary is a containment measure, not a claim that payment processing is
money-grade. Exact-byte signature verification, atomic application, durable
inbox/outbox, and RLS remain required.

### 8.2 Required HTTP and contract test matrix

The current worktree has repository/service reconciliation tests but no
dedicated reconciliation reachable-path test in `server_test.go`. The
following tests are required for the Round 46 gate.

**Public retained routes**

1. `POST events` succeeds only with the intended ingress authorization and
   writes the authenticated tenant/project, ignoring conflicting body scope.
2. Same provider/event/digest replay returns success without a second row.
3. Same provider/event with a different digest returns
   `409 payment_reconciliation_conflict`.
4. `GET events` and `GET event` require billing-read authority and remain
   tenant/project isolated.
5. Missing reconciliation capability returns
   `503 payment_reconciliation_unavailable`.
6. Missing auth, wrong scope, tenant mismatch, project mismatch, API-key
   mismatch, and revoked key fail closed.
7. Invalid status and invalid limit produce stable client errors.
8. List order is identical in memory and Postgres. Use one total order in both
   implementations, then apply limit. Include equal timestamps, two providers,
   multiple event IDs, status filtering, and repeated calls.

**Removed public transitions**

9. Public POSTs to `/verify`, `/apply`, and `/fail` return `404` for an
   unauthenticated request, a normal customer key, and a key carrying every
   customer billing scope.
10. Public route manifest, scope docs, and OpenAPI contain none of the three
    transition operations or paths.
11. The customer hosted client has no transition methods. Retained
    receive/list/get methods match the public manifest.
12. Default, commercial, self-host, and production constructors all prove the
    same absence; a configuration flag must not accidentally mount them on the
    public listener.

**Internal worker capability**

13. A valid workload identity with the correct audience, tenant/project, job,
    provider, and event claim can invoke the internal transition workflow.
14. Missing identity, customer API key, wrong audience, wrong job, expired
    identity, tenant/project mismatch, and event mismatch are denied.
15. Internal verify cannot succeed without recorded provider verification
    evidence derived from exact raw bytes and freshness checks.
16. Internal apply replay is idempotent and produces one domain effect, one
    audit/outbox effect, and one terminal reconciliation state.
17. Fault injection between domain-effect preparation and terminal state
    either rolls the transaction back or leaves a durable recoverable
    inbox/outbox state; it must never produce an applied ledger with a
    nonterminal reconciliation event.
18. Internal fail uses server-derived failure classification/evidence and
    cannot overwrite applied state or change evidence on replay.

**Current implementation defects exposed by this matrix**

- `handlePaymentReconciliation` still registers public verify/apply/fail and
  authorizes them with `billing:webhook`.
- `GoRouteManifest` and `GoRouteScopeDocs` still publish all three operations.
- `hosted.go` still exposes all three customer methods.
- Memory webhook idempotency now supports sequential replay, but its separate
  check and later store allow concurrent same-key requests to pass together.
  A 32-way concurrency test must prove one original side effect and 31
  replays.
- Memory reconciliation sorts ascending by received time/provider/event ID;
  Postgres sorts descending by received time/event ID and omits provider.
  Their contract is still divergent.
- The new deterministic memory-list test does not currently compile because
  `reflect` is not imported.

### 8.3 Round 46 P0/P1 and commit gate

**P0 required before enabling any account-backed money path**

1. Remove public/customer verify/apply/fail routes, manifest entries, docs, and
   hosted-client methods.
2. Preserve transition capability only behind direct worker service calls or a
   separate workload-identity-protected internal listener.
3. Verify bounded exact provider bytes, signature, freshness, and event
   identity before parsing and before recording a trusted verified state.
4. Derive provider event identity, payload digest, header digest, and failure
   evidence at the trusted edge; do not accept them as caller authority.
5. Replace the current ingest-then-apply two-transaction sequence with one
   reviewed transaction or a durable inbox/outbox workflow that proves one
   ledger/entitlement/quota/audit/outbox/reconciliation effect.
6. Make webhook idempotency atomic under concurrency, including conflict
   detection for a reused key with a different normalized request.

**P1 required before this Round 46 code commit is represented as integrated**

1. Restore `go test ./...` and `go vet ./...` green in
   `packages/go/ashrclone`.
2. Define one total reconciliation list order and implement it identically in
   memory and Postgres before applying limit.
3. Add the public absence, retained-route, auth/isolation, internal-identity,
   replay/conflict, and fault-injection tests listed above.
4. Prove reconciliation RLS using a `NOBYPASSRLS` application role, or keep an
   explicit production blocker.
5. Keep readiness wording accurate: the Go Checkout remains plan-only and the
   generic reconciliation receive route is not a verified provider webhook.

**Commit decision**

- **NO-GO** if verify/apply/fail remain reachable on the public listener or
  visible in any customer SDK/public contract.
- **NO-GO** while Go package test/vet do not compile.
- **NO-GO for money-grade or real Checkout execution** until all P0 items are
  closed.
- A code-only Round 46 commit may proceed with exact-byte ingress, atomic
  application, or RLS still deferred only when every affected money mutation
  is demonstrably runtime-disabled outside local tests and documentation names
  each blocker. Public trusted-state setters cannot be deferred behind a
  warning; they must be removed or internalized in this round.

## 9. Final Decision

Round 46 now contains a credible cross-language Stripe safety contract and a
substantially stronger tenant-aware Postgres reconciliation primitive. Those
gains should be retained and documented accurately.

The remaining P0s are concentrated and actionable:

1. OAuth routes can mutate trusted state without mandatory authentication.
2. Hostile mismatch can consume an OAuth flow.
3. OAuth flow lifetime is unbounded.
4. Caller-supplied OAuth identity references can construct a session without
   provider authentication.
5. Stripe provider transport and outbound idempotency are not durable or
   provider-proven.
6. Public Go and hosted-client contracts permit caller-driven
   verify/apply/fail transitions.
7. Go ingress accepts caller hashes after JSON parsing rather than verifying
   exact provider bytes.
8. Signed-event verification, reconciliation, and money-bearing application
   are not yet one proven atomic path.
9. Reconciliation RLS is not proven under the application role.

**Money-grade: NO-GO.**

**Real Stripe test-mode hosted Checkout: proceed only after section 5 gates,
starting with one smallest test operation.**

**Round 46 commit: proceed only after section 4 is closed or the affected
OAuth and provider-network paths are explicitly disabled outside local test
profiles.**

## 10. Final Payment-Boundary Re-audit (2026-07-10)

This section supersedes the payment-reconciliation findings in sections 2.5,
2.6, 8.2, 8.3, and 9 where they describe public `verify`/`apply`/`fail`
routes, customer hosted-client transition methods, a missing `reflect` import,
non-atomic memory webhook idempotency, or divergent memory/Postgres list
ordering. Those observations were accurate for the earlier worktree and are
closed in the current worktree.

### 10.1 Verified closures

1. The public reconciliation HTTP surface is now limited to authenticated
   `receive`, `list`, and `get`.
2. Public POST requests to `verify`, `apply`, and `fail` return `404`.
3. The Go route manifest and scope documentation publish only
   `payment.reconciliation.receive`, `payment.reconciliation.list`, and
   `payment.reconciliation.get`.
4. The customer hosted client contains only receive/list/get reconciliation
   methods. Repository production-code scans found no hosted transition method
   or transition operation marker.
5. HTTP tests cover configured-capability failure, authentication, scope
   denial, tenant/project isolation, digest conflict, filtering, limit,
   deterministic ordering, public-output redaction, transition-path absence,
   manifest safety, and hosted-client method absence.
6. `MemoryService.IngestBillingWebhook` now holds its mutex across replay
   lookup, ledger/audit mutation, and idempotency storage. The 32-caller test
   proves one original result, 31 replays, and one billing event. Reuse of the
   same key for a different normalized event returns
   `IdempotencyConflictError`.
7. Memory and Postgres reconciliation lists use the same total order:
   `received_at ASC, provider ASC, provider_event_id ASC`, with limit applied
   after ordering.
8. Postgres reconciliation receive/transition uses composite
   tenant/project/provider/event identity, digest-only storage, Serializable
   transactions, row locking, and conflict checks.

### 10.2 Final P0 decision

**There is no remaining P0 public trusted-state-setter blocker for a contained
Round 46 code commit.** The previously exposed customer transition surface is
closed and protected by executable absence tests.

The following remain **P0 blockers before enabling or claiming any
account-backed money execution**:

1. The public reconciliation receive route accepts caller-supplied provider,
   provider event ID, payload digest, and header digest after JSON decoding.
   It is an untrusted digest inbox, not evidence that Stripe sent or signed an
   event.
2. The separate public billing webhook-ingest path also consumes decoded JSON
   and derives `Verified` from caller-supplied metadata such as signature
   presence and secret reference. It does not prove a Stripe signature over
   the exact original request bytes.
3. There is no bounded exact-raw-byte Stripe webhook edge that verifies
   signature and timestamp freshness before JSON parsing, derives provider
   identity/digests server-side, and rejects stale, malformed, wrong-mode, or
   wrong-account events.
4. Direct reconciliation transition methods remain an in-process
   test/orchestration capability. There is no production internal listener or
   worker command protected by workload identity, audience, tenant/project,
   job, provider, and event claims.
5. Provider verification, reconciliation transition, ledger/entitlement/quota
   application, audit/outbox emission, and terminal event state are not one
   proven atomic transaction or recoverable inbox/outbox workflow.
6. Postgres RLS and tenant isolation have not been demonstrated with the real
   `NOBYPASSRLS` application role across reconciliation and every money table.
7. Go Checkout remains a deterministic plan only: the local invalid billing
   URL, `provider_called=false`, and `real_charge_possible=false` do not
   constitute hosted Checkout evidence.

These P0s do not block a code-only commit when the affected paths remain
non-money-bearing and documentation states their trust level accurately. They
do block Stripe test-mode product execution, entitlement mutation, and every
live-mode claim.

### 10.3 P1 findings

1. Strengthen the 32-way webhook idempotency test to assert exactly one audit
   event and one stored idempotency record, not only one billing event.
2. Add transition absence tests for unauthenticated requests and for each
   customer billing scope independently. The current all-scope-key `404`
   assertion is strong, but the expanded matrix makes regressions easier to
   diagnose.
3. Add constructor/profile tests proving that default, commercial, self-host,
   and production wiring cannot remount transition routes.
4. Add equal-timestamp ordering fixtures covering multiple providers and event
   IDs in both memory and Postgres implementations.
5. Add restart and multi-process idempotency evidence for the durable webhook
   path. The current concurrency proof is intentionally memory-process local.
6. Add request-body size limits and safe error tests before accepting any
   provider-shaped webhook traffic.
7. Keep the direct transition service explicitly documented as internal and
   non-money-bearing until workload identity and atomic application exist.
8. Add a staged-file secret scan and verify that generated manifests/OpenAPI,
   if included in the commit, contain no stale transition routes.

### 10.4 Exact commit gate

The Round 46 payment reconciliation slice is **GO for commit as containment and
read-model infrastructure only** when all of the following are true at staging
time:

1. Package `go test ./...` and `go vet ./...` remain green.
2. Go integration `go test ./...` and `go vet ./...` remain green.
3. `git diff --check` is clean for the intended staged files.
4. Public HTTP, manifest, scope docs, generated public contract, and customer
   hosted clients expose receive/list/get only.
5. Transition-path tests continue to assert `404`, and no profile or
   constructor mounts an alternative public transition listener.
6. Readiness documentation calls reconciliation receive an untrusted
   caller-hash inbox, not a verified provider webhook.
7. Documentation states that no reconciliation transition currently causes a
   payment, entitlement, quota, subscription, refund, or invoice mutation.
8. Documentation states that Go Checkout is plan-only and Stripe live mode is
   disabled.
9. The staged-file secret scan is clean and no raw provider payload, signature,
   credential, card data, or unrestricted provider response is committed.
10. The commit message and PR description do not claim money-grade processing,
    production webhook readiness, real hosted Checkout, or live-mode readiness.

The commit is **NO-GO** if a customer-facing transition route or client method
reappears, any public path treats caller-supplied hashes as provider
authenticity, any money effect is enabled, or readiness language overstates the
implemented boundary.

### 10.5 Human Account Operator boundary

The human operator has confirmed Stripe Dashboard access in test/sandbox mode.
That safely permits account inventory and configuration planning, but it does
not authorize a live application or a product-originated charge.

Safe next human sequence:

1. Confirm the intended Stripe test account and record only non-secret account
   and mode identifiers in private evidence.
2. Inventory test-mode products, prices, webhook endpoints, redirect origins,
   tax settings, and restricted-key policy without copying secret values into
   source, prompts, logs, or evidence.
3. Engineering implements the exact-byte webhook edge, official Stripe
   transport, durable outbound idempotency, workload identity, atomic
   application, and RLS proof.
4. Security review confirms bounded bodies, signature freshness, mode/account
   consistency, redaction, replay handling, and provider error hygiene.
5. The operator installs test credentials through the approved secret store
   and configures one test webhook endpoint after the receiver is ready.
6. Run one smallest hosted Checkout test-mode lifecycle, then replay the same
   webhook and verify exactly one durable domain effect.
7. Expand only after refund/cancel, restart, multi-worker, tenant-isolation,
   audit/outbox, and recovery evidence pass.
8. Live-mode application, business verification, bank settlement, tax,
   pricing, refund/dispute policy, and any real payment remain separate
   explicit human and compliance gates.

### 10.6 Validation evidence

Executed from the current Round 46 worktree:

- `packages/go/ashrclone`: `go test ./...` passed.
- `packages/go/ashrclone`: `go vet ./...` passed.
- `tests/integration/go`: `go test ./...` passed.
- `tests/integration/go`: `go vet ./...` passed.
- Production-code marker scan found zero public reconciliation transition
  operation markers and zero hosted transition methods.
- Bounded report scan found zero common Stripe/API/private-key secret markers.

**Final payment-boundary decision**

- Public reconciliation containment: **GO**.
- Round 46 code-only commit under section 10.4: **GO**.
- Stripe test-account inventory and configuration planning: **GO**.
- Product-originated Stripe hosted Checkout or trusted webhook processing:
  **NO-GO until section 10.2 P0 items are closed**.
- Stripe live mode or real-money execution: **NO-GO; live application has not
  started and requires separate human, security, compliance, and operational
  approval**.

## 11. Mainland-China Payment Priority Re-audit (2026-07-10)

This section supersedes every Stripe-priority assumption in sections 1-10.
For A1 commercial planning, WeChat Pay and Alipay are now the primary payment
rails for mainland China. Stripe remains a compatibility adapter and must not
be the implicit default in a provider-neutral API.

### 11.1 Executive verdict

The current Round 45/46 payment diff is **NO-GO for commit as a trusted
mainland-China payment path**. The reconciliation read surface remains
acceptably contained, but the domestic webhook verification contract has a P0
semantic flaw: WeChat Pay and Alipay events can be labeled `verified` without
provider cryptographic verification.

The slice may become **GO for a non-money-bearing scaffold commit** only after
the P0 containment in section 11.4 is implemented and tested. No domestic
callback may activate quota, entitlement, subscription, invoice, refund, or
ledger effects in this round.

### 11.2 P0 boundary findings

1. **Domestic callbacks can receive a false trusted state.** In
   `services/api/billing.py`, raw-body verification is implemented only for
   Stripe, while non-Stripe raw-body verification is unsupported. The generic
   result still derives `verified` from an empty failure list, so the presence
   of expected header names and secret references can be mistaken for
   authenticity. `BillingLedger.ingest_provider_webhook` then trusts that
   value.
2. **The same false-trust shape exists in Go.** The Go service assigns
   `event.Verified = len(event.Failures) == 0`, while its failure builder checks
   configuration and header presence rather than WeChat Pay API v3 or Alipay
   cryptographic authenticity. The event is then accepted into billing event
   storage.
3. **Tenant/project labels do not prove merchant ownership.** A request can
   carry tenant and project identifiers, but there is no durable binding from
   tenant/project to WeChat merchant ID, app ID, certificate serial, Alipay
   app ID, seller ID, gateway environment, or receiving account. A valid
   callback from merchant A must never be reusable against merchant B's
   project.
4. **There is no trusted domestic callback edge.** Exact request bytes,
   provider timestamp, nonce, certificate serial, signature, account identity,
   freshness decision, replay decision, and verifier version are not captured
   as a durable provider attestation before domain processing.
5. **Money and quota application are not proven atomic.** Provider
   verification, order transition, payment/refund ledger entry, entitlement or
   quota mutation, audit event, outbox event, and terminal inbox state are not
   one atomic transaction or a proven recoverable inbox/outbox workflow.

Minimum safe interpretation: every current WeChat Pay or Alipay callback is an
untrusted `received` event, regardless of header presence. Until a real
provider-specific verifier succeeds, `verified` must remain false and no
money, quota, entitlement, subscription, invoice, refund, or reconciliation
application is permitted.

### 11.3 P1 boundary and commercial gaps

1. Provider-neutral checkout still silently defaults to Stripe/test in Python.
   A China-first API must require an explicit provider or an explicit,
   versioned China-primary routing policy.
2. Payment readiness and the human operator checklist are Stripe-first and do
   not define WeChat Pay or Alipay merchant onboarding, account ownership,
   certificate/key custody, callback domain, settlement, refund, or bill
   permissions.
3. Billing price and ledger defaults remain USD-oriented. The domestic ledger
   needs integer fen semantics, explicit `CNY`, immutable currency per order,
   and rejection of floating-point amounts and implicit conversion.
4. Generic `test/live` is not an adequate environment model. WeChat Pay and
   Alipay need provider-specific account, gateway, app, merchant, certificate,
   and production/sandbox capability profiles.
5. WeChat Pay API v3 exact-byte signature verification, timestamp freshness,
   nonce replay control, platform certificate serial resolution, certificate
   rotation/revocation, and AES-GCM notification resource decryption are
   absent.
6. Alipay canonical parameter reconstruction, RSA2/certificate verification,
   charset/sign-type enforcement, `app_id`/`seller_id` binding, and gateway
   environment binding are absent.
7. The callback idempotency identity is not yet based on durable
   provider-derived event/order/trade/refund identity plus tenant, project,
   provider, merchant, and environment. Caller-supplied hashes may be useful
   inbox dedupe hints but are not authenticity or money idempotency keys.
8. Refunds lack a durable state machine for requested, provider-accepted,
   pending, partial, succeeded, failed, reversed, and reconciled states.
   Multiple partial refunds and refund callback idempotency are not proven.
9. Daily transaction and refund bill download, signature/integrity checks,
   discrepancy classification, operator review, and corrective journal
   workflow are absent.
10. Complaint, frozen-funds, chargeback-equivalent, settlement delay, and
    merchant-risk event handling are absent.
11. Postgres isolation is not proven under the actual `NOBYPASSRLS`
    application role across payment order, callback inbox, refund, ledger,
    quota, audit, outbox, reconciliation, and secret-reference tables.
12. Secret configuration is reference-shaped but lacks a production
    KMS/Vault resolver, least-privilege workload identity, access audit,
    rotation, revocation, and separation among merchant private keys, API v3
    keys, platform certificates, Alipay keys, and webhook verification
    material.
13. Callback body limits, content-type enforcement, redacted diagnostics,
    dead-letter handling, bounded replay, clock-skew monitoring, and
    provider-specific error hygiene are incomplete.
14. The current WeChat NATIVE and Alipay trade-page adapters are deterministic
    plan contracts only. They do not establish network execution, provider
    acceptance, hosted/QR completion, callback authenticity, settlement, or
    refund readiness.
15. Mainland callback domain, HTTPS certificate operations, ICP/network
    readiness, privacy notice, retention policy, invoice/fapiao workflow, and
    merchant support runbooks are not established.

### 11.4 Must land in Round 46

The minimum commit-safe closure is:

1. Fail closed for WeChat Pay and Alipay: header presence, configured secret
   references, or a caller digest must never produce `verified=true`.
2. Keep domestic events in `received/unverified` state until a
   provider-specific verifier returns a structured attestation.
3. Prove by tests in Python and Go that plausible fake domestic headers,
   configured references, replayed nonces, wrong merchant/app identity, and
   altered bodies cannot produce a verified event or any domain effect.
4. Block every unverified event from billing ledger, entitlement, quota,
   subscription, invoice, refund, and reconciliation application.
5. Remove the silent Stripe default from provider-neutral checkout. Require
   explicit `provider`, or a documented and tested routing policy whose
   mainland default is WeChat Pay/Alipay and whose Stripe path is explicitly
   compatibility-only.
6. Add a provider account identity contract containing tenant, project,
   provider, environment, merchant/account ID, app ID, and key/certificate
   reference identities. Do not store secret values in that contract.
7. Define the durable callback inbox key and conflict rules using
   tenant/project/provider/environment/merchant plus provider event, order,
   trade, or refund identity. Same key with different body digest must
   conflict.
8. Keep reconciliation verify/apply/fail operations internal and
   non-money-bearing. The public receive/list/get-only containment and `404`
   tests must remain.
9. Update strategy, payment readiness, and the human operator checklist to
   identify WeChat Pay and Alipay as primary, Stripe as compatibility-only,
   and all domestic live/KYC/settlement/payment actions as separate human
   gates.
10. Run staged-file secret scanning and ensure evidence records only reference
    names, modes, IDs safe for documentation, status, and response-field
    shapes. No credential, signature, raw callback, private key, certificate
    private material, or payment personal data may enter source or evidence.

Items 1-5 are P0 commit blockers. Items 6-10 are P1 commit gates for claiming
the slice is an intentional China-first scaffold rather than an accidental
Stripe-first compatibility layer.

### 11.5 Human Account Operator boundary

No WeChat Pay or Alipay live account action should start from the current code.
The safe human sequence is:

1. Engineering first lands the fail-closed callback semantics and explicit
   provider routing contract.
2. Product/legal identifies the intended mainland entity, merchant ownership,
   settlement bank account, business category, refund policy, privacy terms,
   invoice/fapiao owner, and authorized operators.
3. The operator inventories WeChat Pay and Alipay onboarding requirements and
   records only non-secret account/application identifiers in private
   evidence.
4. Security defines the approved secret manager, workload identities,
   certificate/key ownership, rotation cadence, revocation path, access audit,
   and incident owner.
5. Engineering implements provider verification, durable inbox/outbox,
   tenant/project/merchant binding, atomic application, refunds, and bill
   reconciliation.
6. The operator configures sandbox or non-money test capability only after the
   matching receiver and verifier are ready.
7. Run the smallest test lifecycle, including duplicate callback, altered
   body, stale timestamp, wrong merchant/app, restart, multi-worker,
   refund/cancel, and reconciliation discrepancy cases.
8. Production merchant application, KYC, settlement binding, production key
   installation, real QR/payment, refund, and bill access remain explicit
   human, legal, security, and finance approvals.

Stripe test-account inventory may continue as compatibility research, but it
must not drive the mainland product contract or delay domestic trust-boundary
work.

### 11.6 Ranked A1 growth backlog

1. P0 fail-closed domestic callback verification semantics.
2. WeChat Pay API v3 exact-byte signature verification.
3. WeChat platform certificate serial store, refresh, rotation, and
   revocation.
4. WeChat timestamp freshness and durable nonce replay protection.
5. WeChat AES-GCM notification resource decryption with redacted failures.
6. Alipay canonical parameter reconstruction and strict field filtering.
7. Alipay RSA2 and certificate-chain verification.
8. Alipay `app_id`, `seller_id`, gateway, charset, and sign-type binding.
9. Tenant/project/provider/merchant/app/environment binding schema.
10. Durable provider callback inbox with body digest and conflict semantics.
11. Workload identity for verifier, callback worker, refund worker, and
    reconciliation worker.
12. Atomic order/ledger/entitlement/quota/audit/outbox application.
13. CNY integer-fen ledger and immutable order currency.
14. Domestic payment-order state machine with provider transition guards.
15. Refund state machine with provider request idempotency.
16. Partial and multiple-refund accounting invariants.
17. Refund callback verification and replay safety.
18. WeChat transaction/refund bill download and integrity validation.
19. Alipay transaction/refund bill download and integrity validation.
20. Daily reconciliation, discrepancy classification, and operator workflow.
21. Quota activation, reservation, release, reversal, and refund coupling.
22. Real `NOBYPASSRLS` tenant-isolation integration proof for every money
    table.
23. KMS/Vault secret-reference resolver with least privilege and access audit.
24. Merchant key, API v3 key, platform certificate, and Alipay key rotation
    drills.
25. Provider-specific sandbox/production capability profiles and hard mode
    separation.
26. Dead-letter queue, bounded replay, poison-event quarantine, and operator
    controls.
27. Payment observability: verification failures, replay rate, callback lag,
    ledger lag, refund lag, and reconciliation SLOs.
28. Complaint, frozen-funds, risk-control, and settlement-delay workflows.
29. Go, Python, TypeScript, CLI, and OpenAPI parity for domestic payment
    contracts.
30. Merchant onboarding, callback-domain, ICP/network, support, and incident
    runbooks.
31. Invoice/fapiao, tax ownership, retention, deletion, and audit-export
    readiness.
32. Stripe compatibility conformance tests that cannot influence the default
    mainland routing policy.

The highest-ROI implementation bundle for this round is items 1, 9, 10, 13,
and 32's routing-isolation portion. Real provider verification begins
immediately after that containment; it must not be represented by header-shape
checks or mocked success flags.

### 11.7 Main-agent driving instructions

1. Stop all feature expansion that depends on domestic callbacks being
   trusted. Patch Python and Go verification semantics first.
2. Add negative trust tests before implementation, then make the smallest
   fail-closed change that keeps current plan-contract tests useful.
3. Remove provider-neutral Stripe defaults and update every SDK/CLI/OpenAPI
   example to choose a provider explicitly.
4. Introduce the non-secret provider-account binding contract and enforce it
   at callback ingestion, order lookup, refund lookup, and reconciliation
   lookup.
5. Preserve the receive/list/get-only public reconciliation boundary. Do not
   add public verify/apply/fail routes or hosted-client methods.
6. Keep current callback and reconciliation paths non-money-bearing until an
   atomic Postgres application path and real provider verifier attestation are
   proven under concurrency, restart, and RLS tests.
7. Update strategy/readiness/operator evidence in the same commit so no
   Stripe-first or money-grade claim survives.
8. Re-run Python focused payment/OAuth tests, TypeScript build/payment tests,
   Go package and integration tests, `go vet`, diff checks, public-route
   absence scans, and staged-file secret scans.
9. Ask Growth-Auditor to re-audit the exact staged diff. Do not commit on the
   basis of the unstaged worktree report alone.

### 11.8 Updated Round 46 commit gate

**P0 decision: NO-GO now.**

The commit becomes **GO only as a non-money-bearing China-first scaffold** when
all section 11.4 items are closed, the full focused test suite is green, and
the exact staged diff passes secret and public-transition scans.

It remains **NO-GO** for sandbox payment execution, production merchant
onboarding, real payment, refund, entitlement/quota activation, settlement, or
money-grade claims until provider cryptographic verification, account binding,
durable idempotency, atomic application, RLS proof, refund handling, and bill
reconciliation are implemented and evidenced.
