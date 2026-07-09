# A3 Billing Migration Readiness - 2026-07-09

ANCHOR: A3_BILLING_MIGRATION_READINESS

## Lane

A3 / Product Console / Usage Billing / Migration Bridge.

## Contract

- Schema: `a3.billing_migration_readiness.v1`
- Module: `services/report/a3_billing_migration_readiness.mjs`
- Fixture: `fixtures/a3/p3/a3_billing_migration_readiness.redacted.json`
- Test: `node --test tests/a3/a3_billing_migration_readiness.test.mjs`
- Upstream branch: `origin/codex/a1-local-sdk-runner`

## Upstream A1 Evidence Consumed

- `f8ee956`: A1 billing ledger replay parity.
  - A3 consumes the public replay fixture shape, accepted/duplicate replay states,
    `invoice_paid` and `usage_reconciled` ledger event vocabulary, USD minor-unit
    total, usage-unit count, and public-safety flags.
- `91213fc`: A1 durable billing ledger migration.
  - A3 consumes the migration manifest and SQL contract for
    `billing_accounts`, `billing_provider_events`, and
    `billing_ledger_events`.
  - A3 records the required functions:
    `normalize_billing_event_type`, `ingest_billing_provider_event`, and
    `summarize_billing_ledger`.
- `11ac03e`: A1 billing ledger live migration smoke.
  - A3 records the opt-in live smoke expectation that the migration is
    replayable and provider events report `accepted`, `duplicate`, and
    `conflict` safely.
  - A3 did not run the live smoke or apply the migration.

## A3 Consumer State

A3 is ready to consume a read-only A1 billing ledger summary when A1 exposes an
authenticated API for it. This contract does not claim live customer billing,
provider webhook execution, invoice mutation, or checkout readiness.

A3 can consume now:

- Migration manifest fields.
- Provider and ledger event type vocabulary.
- Public replay fixture counts, statuses, hashes, and totals.
- Live smoke expectations from the A1 diff.

Blocked for live billing:

- A1 authenticated read API is not wired into A3 in this change.
- A1 provider webhook executor is not callable by A3.
- A1 hosted auth and RBAC are required before any billing write path.
- A3 checkout, billing portal, and provider mutation paths remain disabled.

## API / DB / Event / Artifact Contract

API:

- Existing A3 surface: `GET /api/a3/billing/readiness`.
- Future A1 read API: `GET /v1/projects/{project_id}/billing/ledger-summary`.
- Future A1 audit readback API:
  `GET /v1/projects/{project_id}/billing/provider-events`.
- Future A1-only mutation:
  `POST /v1/billing/webhooks/{provider}`.
- Every A3-side entry is read-only and has no side effect.

DB:

- A1 owns `billing_accounts`, `billing_provider_events`, and
  `billing_ledger_events`.
- Required scope: `organization_id` plus `project_id`.
- Required safety: forced RLS, no raw provider payload column, no raw provider
  secret, no raw card data, and metadata secret checks.

Events:

- Provider event vocabulary includes `invoice.paid`,
  `wechat_pay.transaction.success`, `alipay.trade.success`, and
  `ashr.usage.reconciled`.
- Ledger event vocabulary includes `checkout_created`, `invoice_paid`,
  `refund_created`, `subscription_canceled`, and `usage_reconciled`.
- Replay states include `accepted`, `duplicate`, `conflict`, and `rejected`.
- A3 event payloads must contain ids, refs, hashes, statuses, counts, and
  normalized totals only.

Artifacts:

- A1 inputs are the migration manifest, SQL migration, replay fixture, live smoke
  test, and official API read-only public summary.
- A3 outputs are this module, this redacted fixture, and this documentation.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: preserve `organization_id`, `project_id`, and `environment_id`; never
  merge ledger summaries across tenants.
- Auth: A3 remains read-only until A1 hosted session, actor identity, service
  account identity, idempotency, and auth middleware exist.
- RBAC: read roles are `billing_admin`, `auditor`, and `owner`; mutation is
  reserved for A1 provider-webhook verifier service.
- Usage: A1 billing ledger and usage rollups are the source of truth; A3 shows
  read-only usage and invoice-preview state only.
- Audit: append-only audit is required; raw payload logging is not allowed.

## Safety Boundary

- No .env.local was read.
- No real API was called by A3.
- No live database migration was run by A3.
- No real payment provider was called.
- No billing mutation was performed by A3.
- No provider secret, raw provider payload, card data, customer email, signed URL,
  or private manifest content is stored in the A3 fixture.

## Evidence And Next Step

The redacted fixture is the evidence object for this bridge:
`fixtures/a3/p3/a3_billing_migration_readiness.redacted.json`.

Next A3 work should wait for an A1-owned read-only billing ledger API, then wire
that API into the billing UI with tenant, auth, RBAC, usage, and audit checks
kept fail-closed.
