# Round 47 A1 Growth-Auditor: China-First Payment Boundary

Date: 2026-07-10

Scope: A1 only. This audit reviews the uncommitted China-mainland payment work for WeChat Pay, Alipay, domestic bank-card acquiring, and retained Stripe compatibility. It does not authorize a provider call, live-money movement, merchant onboarding, or storage of payment or identity credentials.

## Executive verdict

The round has useful commercial scaffolding, especially the Postgres tenant model, CNY/fen records, reference-only configuration, reconciliation topology, and Stripe compatibility isolation. It is not yet a sellable payment-processing system.

Domestic bank cards may only be represented as an acquirer-hosted session, opaque acquirer token, or opaque provider reference. PAN, CVC/CVV, PIN, OTP, expiry, track data, cryptograms, cardholder data, raw payment credentials, and KYC documents must be rejected before serialization and must never enter an A1 API, SDK, database, queue, trace, log, evidence file, or prompt.

The current diff does not prove that invariant across every runtime and persistence boundary. Python and TypeScript now expose domestic-card plans, while Go lacks a registered domestic-card provider profile and SQL metadata filtering remains materially narrower than the runtime policy. Therefore the branch must not advertise or enable domestic-card execution until the P0 gate below is closed. A commit is acceptable only as explicitly disabled, plan-only scaffolding with no real provider calls and no public payment activation path.

## Evidence reviewed

- `services/api/china_payments.py`
- `services/api/migrations/003_a1_china_mainland_payments.sql`
- `packages/go/ashrclone/payment_domain.go`
- `packages/go/ashrclone/payment_reconciliation.go`
- `packages/ts/ashr-clone/src/china-payments.ts`
- Python, TypeScript, Go, SQL-manifest, runtime, and HTTP tests under A1 ownership
- `docs/a1/payment_provider_readiness.md`
- `docs/a1/evidence/round47_runtime_china_payment_workers.md`
- `docs/strategy/large-saas-a1-a2-a3-full-plan.md`

No secret value or private credential was read for this audit.

## P0 findings

### P0-1: Card-data non-admission is not yet a cross-layer invariant

Python rejects several sensitive names and values, and TypeScript rejects sensitive keys plus card-number-shaped values. However, the matrix is not demonstrated as complete and identical across Python, TypeScript, Go, SQL, HTTP, queues, traces, and evidence.

The SQL function `china_payment_public_metadata()` currently names `card_number` but does not explicitly reject common aliases and materials such as `pan`, `primary_account_number`, `cvc`, `cvv`, `security_code`, `otp`, `pin`, `expiry`, `expiration`, `track1`, `track2`, `cryptogram`, or magnetic-stripe data. Nested JSON text may also use semantic aliases not covered by the current expression. See `services/api/migrations/003_a1_china_mainland_payments.sql:10`.

Go normalizes generic metadata through billing redaction rather than rejecting prohibited card material at the input boundary. Redaction is not an acceptable admission control because sensitive input may already have crossed HTTP, allocation, logging, tracing, or queue boundaries before it is removed. See `packages/go/ashrclone/payment_domain.go:1288`.

Commit gate: either implement one tested forbidden-material policy across every exposed A1 layer, or keep all domestic-card capabilities and endpoints disabled and label them non-executable. A public or hosted domestic-card path cannot ship while this finding remains open.

### P0-2: Callback receipt is not callback authenticity

Python correctly requires raw bytes, required signature fields, and an injected verifier. It does not yet implement provider cryptography for WeChat Pay API v3, Alipay, or a selected card acquirer. TypeScript can model a verification result, but an untrusted caller-supplied `verified` value is never proof. Go reconciliation receives hash envelopes and provides internal state transitions; this is suitable for an internal inbox, not a provider webhook verifier.

No received or hash-only event may mutate payment state, refunds, usage ledger, quota, entitlement, billing status, or settlement state. Mutation is allowed only after provider-specific cryptographic verification, freshness and replay checks, and complete scope binding.

Public reconciliation HTTP is correctly limited to receive/list/get, with verify/apply/fail absent and tests expecting 404. Preserve that boundary. Internal verify/apply/fail methods must remain worker-only and require trusted verifier evidence. Do not add them to hosted clients or customer API routes.

Commit gate: tests must prove that unverified, stale, replayed, wrong-mode, wrong-merchant, wrong-acquirer, and cross-tenant callbacks cannot produce a money or quota mutation. If the current receive route is exposed, document and name it as a hash-only internal reconciliation inbox rather than a trusted payment webhook.

### P0-3: Domestic-card provenance is incomplete outside SQL

The SQL model has a strong `china_payment_acquirer_account_bindings` table and composite organization/project/application/provider/mode foreign keys. Python and TypeScript expose account/acquirer references. Go defines `PaymentProviderDomesticBankCard`, but `paymentProviderProfiles()` does not register it and order validation does not require an acquirer account, hosted-session reference, token reference, merchant application, or environment provenance. See `packages/go/ashrclone/payment_domain.go:1252`.

An opaque token or reference is safe only when its provenance is known. Every domestic-card order, refund, callback, bill row, and reconciliation event must bind:

- organization/tenant;
- project;
- merchant application;
- provider and selected acquirer;
- acquirer account;
- test or live mode;
- hosted/token/reference contract;
- reference issuer, creation time, expiry, and revocation state.

Commit gate: no domestic-card capability may be advertised or selected through Go, OpenAPI, hosted clients, or workers until this provenance is enforced. Disabled schema and plan scaffolding may commit.

### P0-4: Capability claims exceed implemented acquiring and verification

Python and TypeScript mark hosted/token domestic-card planning as supported, but there is no selected acquirer integration, merchant contract, KYC approval, cryptographic callback verifier, production key resolver, or live acquiring evidence. SQL constraints do not make the system a card acquirer.

Commit gate: readiness documents and capability payloads must say `plan_only`, `provider_calls=false`, `real_card_acceptance=false`, and `merchant_activation_required=true`. Any user-facing claim of real card acceptance, trusted webhook readiness, or live acquiring is blocked.

## P1 findings

1. **Go provider parity:** register domestic bank cards or explicitly mark them disabled; add hosted/token/reference-only channels and provider status maps.
2. **CNY/fen enforcement:** Go accepts any three-letter currency. WeChat Pay, Alipay, and domestic-card paths must require `CNY`, integer minor units, and explicitly label the unit as `fen`. Stripe compatibility may retain its separate currency matrix.
3. **Reference validation:** references need bounded length, strict prefixes, issuer/type information, and rejection of credential-like or card-like content.
4. **Freshness and replay:** callback verification needs provider-specific timestamp windows, nonce/event uniqueness, certificate serial validation, and durable replay records.
5. **Mode binding:** test and live accounts, keys, callback endpoints, queues, data, and evidence must be hard-separated. A test object can never satisfy a live transition.
6. **Merchant binding:** provider merchant/application identity returned by a verified callback must equal the configured tenant/project binding before state changes.
7. **Atomic money path:** verified event, order/refund transition, append-only ledger entry, quota/entitlement decision, audit record, and outbox enqueue require one serializable transaction or an equivalent idempotent state machine.
8. **Refund controls:** partial, repeated, and concurrent refunds need cumulative amount checks, provider idempotency, approval policy, and verified refund callbacks.
9. **RLS proof:** migration structure is promising, but a live Postgres test must use a `NOBYPASSRLS` application role and prove cross-tenant denial for every China-payment table and function.
10. **Readiness documentation:** `docs/a1/payment_provider_readiness.md` remains Stripe/wallet-oriented and does not yet describe domestic-card acquirer/KYC boundaries as a first-class rail.
11. **Operator packet:** the existing human checklist is Stripe-first and must be replaced or extended with mainland merchant/acquirer onboarding and production activation steps.
12. **PCI and privacy classification:** obtain a documented PCI scope decision for hosted/token/reference-only integration and a China privacy/data-retention review before real merchant traffic.

## Tenant, merchant, and callback rules

A verified event is actionable only when all bindings agree:

`tenant + project + merchant_application + provider + provider_account/acquirer_account + mode + provider_event + provider_object`

Provider event IDs are idempotency keys only inside that complete scope. A globally reused provider event ID must neither collide across tenants nor permit cross-scope lookup.

Callback processing must follow this order:

1. Select tenant/project and expected merchant binding from trusted routing or a non-secret provider account reference.
2. Read the exact raw bytes transiently without logging or persisting them.
3. Resolve verification keys and certificates through a vault/KMS reference.
4. Verify provider signature, certificate chain/serial, timestamp freshness, nonce, and expected mode.
5. Parse the verified payload and compare merchant/application/acquirer identity with the selected binding.
6. Insert a durable callback inbox record using digests and public-safe references only.
7. Detect replay or same-key/different-content conflict.
8. In an internal worker transaction, apply normalized order/refund state, ledger, audit, and outbox effects.
9. Acknowledge according to the provider protocol.

Failure at any step must fail closed. A digest proves content stability, not authenticity.

## CNY and fen contract

- WeChat Pay, Alipay, and domestic bank-card A1 contracts use `currency="CNY"`.
- Amounts are positive integers in fen. Refund totals and signed settlement adjustments must use explicitly named integer fields.
- Never infer yuan versus fen from decimal shape or provider name.
- Reject floating-point amounts, scientific notation, negative order amounts, overflow, and ambiguous generic `amount` fields at public boundaries.
- Reconciliation must retain gross, fee, refund, and net amounts separately and verify arithmetic before ledger application.
- Stripe remains a compatibility rail and must use its own provider/currency capability checks rather than weakening mainland-rail constraints.

## Human merchant and KYC boundary

The following work requires a human account operator and must occur directly in the provider or acquirer interface:

1. Select and confirm the contracting legal entity.
2. Apply for WeChat Pay, Alipay, and one selected domestic-card acquirer account.
3. Choose the correct merchant category and product/channel permissions.
4. Upload business licenses, legal-representative identity documents, and other KYC materials directly to the provider.
5. Bind and verify the settlement bank account directly with the provider.
6. Complete provider login, CAPTCHA, OTP/2FA, legal attestations, and agreements.
7. Register and approve callback domains and application identifiers.
8. Create or install production certificates and keys through an approved vault/KMS process; the repository receives references only.
9. Enable sandbox/test products and provide non-secret merchant/application/account reference IDs.
10. After engineering gates pass, explicitly approve production activation.
11. Execute the smallest approved live payment, immediate refund/void, and settlement reconciliation under a written runbook.
12. Store only redacted references, timestamps, statuses, and digests in private evidence.

KYC documents, bank-account credentials, card data, OTPs, private keys, API secrets, raw callback bodies, and unredacted dashboard screenshots must never be copied into source control, Codex prompts, public evidence, traces, or test fixtures.

## Sellable capability assessment

Potentially sellable now as disabled integration infrastructure:

- tenant/project-scoped China-payment persistence;
- merchant application and acquirer account reference model;
- CNY/fen order, refund, bill, and reconciliation records;
- hosted/token/reference-only SQL shape;
- hash-only callback and bill evidence;
- worker, retry, scheduler, and dead-letter topology;
- public reconciliation receive/list/get boundary with internal transitions absent;
- Stripe compatibility contracts isolated from mainland-first rails.

Still a prototype:

- real WeChat Pay or Alipay payment execution;
- domestic bank-card acceptance or acquiring;
- trusted provider callback processing;
- payment-driven quota or entitlement activation;
- automated refunds and settlement;
- merchant/KYC onboarding;
- production certificate rotation;
- chargebacks, disputes, frozen funds, and reserve handling;
- operational finance reconciliation and regulatory reporting.

## Round 47 commit gate

All items below are required before this diff is described as payment-ready:

1. Keep all provider execution disabled and preserve `real_provider_calls=false`.
2. State clearly that domestic cards are plan-only and require merchant/acquirer activation.
3. Keep public reconciliation routes receive/list/get only; verify/apply/fail remain internal and absent from hosted clients.
4. Prove no unverified reconciliation event can mutate order, refund, ledger, quota, entitlement, or settlement state.
5. Close the card-data rejection matrix across exposed runtime and persistence boundaries, or disable domestic-card capability in all public manifests.
6. Align provider capability claims across Python, TypeScript, Go, SQL, docs, tests, and any OpenAPI schema.
7. Enforce CNY/fen on every mainland rail; do not share Go's generic three-letter currency validator with mainland execution.
8. Require complete tenant/project/merchant/acquirer/mode provenance for every domestic-card reference.
9. Add adversarial tests for sensitive aliases, nested metadata, card-number-shaped values, wrong merchant, wrong acquirer, wrong mode, stale timestamps, replay, and cross-tenant access.
10. Run focused Python, TypeScript, Go, migration, manifest, compose, secret-scan, and diff checks without staging peer changes.

No live provider call or real-money test is part of this commit gate.

## Main-agent drive instructions

For this round, implement the minimum security closure rather than adding another payment feature:

1. Create one normative forbidden payment-data matrix and enforce it in Python, TypeScript, Go, SQL, HTTP decoding, queue payload validation, traces, logs, and evidence serializers.
2. Add domestic-card Go parity only behind a disabled capability flag until hosted/token/reference provenance and CNY/fen validation are complete.
3. Make callback state transitions consume a trusted internal verification artifact, never a public boolean or hash-only receipt.
4. Update readiness and operator evidence to identify WeChat Pay, Alipay, and domestic-card acquirers as the primary rails while preserving Stripe compatibility.
5. Test the full negative matrix and cross-tenant/mode/merchant/acquirer isolation before enabling any execution worker.

## Ranked next-round growth points

1. P0: normative PAN/CVC/CVV/PIN/OTP/expiry/track/cryptogram/KYC non-admission policy.
2. P0: identical sensitive-material rejection in Python, TypeScript, Go, SQL, HTTP, queue, trace, log, and evidence paths.
3. P0: trusted internal verification artifact required by all money-state transitions.
4. P0: domestic-card hosted/token/reference provenance bound to tenant/project/merchant/acquirer/mode.
5. P0: unverified-event non-mutation tests for ledger, quota, entitlement, refunds, and settlement.
6. P1: Go domestic-card capability, channel, status, and refund parity behind a disabled flag.
7. P1: CNY/fen validators shared by every mainland order, refund, bill, and reconciliation path.
8. P1: Python/TypeScript/Go/SQL/OpenAPI capability conformance suite.
9. P1: WeChat Pay API v3 signature, platform-certificate, serial, timestamp, and nonce verifier.
10. P1: Alipay RSA2 signature, app/seller identity, charset, timestamp, and replay verifier.
11. P1: selected domestic-card acquirer callback verifier and certification suite.
12. P1: durable callback inbox with content conflict detection and bounded retention.
13. P1: serializable order/refund/ledger/quota/audit/outbox transaction.
14. P1: live Postgres `NOBYPASSRLS` isolation proof for all payment tables and functions.
15. P1: sandbox/live account, key, callback, queue, database, and evidence separation.
16. P1: vault/KMS reference resolver with rotation, revocation, and certificate overlap.
17. P1: hosted payment URL allowlist, signed return context, and anti-open-redirect checks.
18. P1: opaque token/reference TTL, single-use, issuer, revocation, and replay rules.
19. P1: merchant application and acquirer account lifecycle state machine.
20. P1: mainland merchant/KYC human-operator packet and separation-of-duties approvals.
21. P1: partial and multiple refund cumulative amount enforcement.
22. P1: verified refund callback and refund idempotency workflow.
23. P1: daily WeChat Pay, Alipay, and acquirer settlement-bill ingestion.
24. P1: gross/fee/refund/net arithmetic and exception reconciliation.
25. P1: chargeback, dispute, frozen-funds, reserve, and manual-review lifecycle.
26. P1: finance operator exception queue with dual approval and immutable audit.
27. P1: payment SLOs, callback lag, replay, signature-failure, reconciliation-gap, and DLQ alerts.
28. P1: PCI scope/SAQ assessment for hosted/token/reference-only card integration.
29. P1: China privacy, retention, data-residency, and incident-response review.
30. P2: acquirer portability interface and contract tests for a second processor.
31. P2: Stripe compatibility isolation tests proving it cannot weaken mainland CNY or card-data rules.
32. P2: controlled smallest-value sandbox-to-live certification runbook with private evidence.

Recommended parallel bundle after the Round 47 gate:

- Security lane: items 1-5, 14, and 28.
- Runtime lane: items 6-8, 12, 13, and 15.
- Provider lane: items 9-11, 16-18, and 23.
- Money operations lane: items 19-27.
- Compatibility and release lane: items 29-32.

## Final main-agent disposition

The direct generated-fixture blocker was resolved by regenerating the A2
cross-lane consumer snapshot after the A1 route artifact expanded from 43 to
67 routes. No A2 judge source or semantics changed. The generated fixture
check and focused A2 contract suite passed.

The remaining P0 findings are correctly retained as payment-readiness blockers,
not source-commit blockers. This round commits only fail-closed, disabled,
plan-only infrastructure:

- `real_provider_calls=false`
- `real_card_acceptance=false`
- `merchant_application_started=false`
- `kyc_started=false`
- `live_money_activation=false`
- `plan_only=true`

Public billing callback ingestion rejects caller-supplied verification before
opening a database transaction. Database triggers independently reject
unverified direct writes. Provider-specific cryptographic verification,
entitlements, project-level RLS proof, and atomic money-state transitions remain
next-round work and must be completed before any payment-ready claim.

Final validation:

- Python A1: `534 passed, 2 skipped`
- TypeScript: `376 passed`
- Go package tests and vet: passed
- Go integration tests and vet: passed
- A2 generated fixture check: passed
- Focused A2 cross-lane contracts: `67 passed`
- CL hygiene and commercial guards: passed
- Diff check: passed with line-ending warnings only
- Bounded secret scan: only intentional negative-test/guardrail hits; no real
  credential or private-key artifact found
