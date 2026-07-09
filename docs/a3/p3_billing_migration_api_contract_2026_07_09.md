# A3 Billing Migration API Contract - 2026-07-09

ANCHOR: A3_BILLING_MIGRATION_API_CONTRACT

## Contract

- Schema: `a3.billing_migration_readiness.v1`
- Local A3 route: `GET /api/a3/billing/migration-readiness`
- Commercial mapping: future read-only A1 billing ledger and migration summary API
- Required permission: `billing:read`
- SQL evidence table: `billing_migration_readiness`

## Boundary

This route is a read-only A3 product surface. It can display readiness for the
A1 durable billing ledger migration, replay evidence, provider event summary,
ledger event summary, and migration manifest hash.

No A3 billing mutation is allowed here. A3 must not create checkout sessions,
open billing portals, ingest provider webhooks, alter subscriptions, reconcile
ledger rows, or call payment providers.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: every response must preserve `organization_id`, `tenant_id`,
  `workspace_id`, `project_id`, and `environment_id`.
- Auth: hosted SaaS must use A1-owned session or service-account auth before
  customer data is exposed.
- RBAC: `billing:read` is required. `viewer` must not read sensitive billing
  migration or provider status by default.
- Usage: A1 usage ledger remains the source of truth; A3 records only read
  meters such as `api_requests` and `billing_readiness_reads`.
- Audit: append-only audit events should use
  `billing.migration_readiness_read` and `billing.ledger_summary_read` with ids,
  refs, hashes, statuses, and counts only.

## OpenAPI Anchors

- Path: `#/paths/~1api~1a3~1billing~1migration-readiness`
- Response schema: `#/components/schemas/BillingMigrationReadiness`
- Schema version: `a3.billing_migration_readiness.v1`
- Safety fields: `billing_mutations_enabled=false`,
  `raw_provider_secret_allowed=false`,
  `raw_provider_payload_embedded=false`, and `raw_card_data_allowed=false`.

## SQL Contract

The `billing_migration_readiness` table is an A3 projection of read-only A1
billing ledger evidence. It is tenant-scoped and stores:

- source owner lane `A1`
- source ledger summary ref
- migration manifest hash
- provider and ledger event counts
- replay status summary
- redacted payload hash and JSON payload
- explicit false flags for billing mutations, raw provider payload, provider
  secrets, and card data

## Safety

- No `.env.local` is read.
- No real API is called.
- No key, token, cookie, customer email, provider secret, card data, raw provider
  payload, or signed URL is stored.
- A3 consumes read-only A1 billing ledger evidence; it does not become the
  billing system of record.
