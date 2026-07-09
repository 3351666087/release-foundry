# A3 Billing Readiness Contract - 2026-07-09

## Lane

A3 / Product Console / Billing UI / Usage Workflow.

## Why This Matters

The strategy bus says Ashr++ must eventually bill by usage. A3 owns the customer
surface for plan, checkout, invoice, quota, and usage UI, but A1 owns the real
usage ledger, billing backend, provider webhooks, and tenant enforcement.

This round adds a read-only billing readiness contract so A3 can expose what is
already billable, what is blocked, and what A1/A2 evidence must exist before
real billing mutations are safe.

## Added Contract

- Module: `services/report/a3_billing_readiness.mjs`
- API: `GET /api/a3/billing/readiness`
- Schema: `a3.billing_readiness.v1`
- Tests:
  - `tests/a3/a3_billing_readiness.test.mjs`
  - `tests/a3/a3_api_server.test.mjs`

## API / DB / Event / Artifact Contract

- API:
  - Reads from existing `GET /api/a3/usage/ledger` semantics.
  - Adds `GET /api/a3/billing/readiness`.
  - Does not add checkout, portal, subscription, or invoice mutation APIs.
- DB:
  - Names future source-of-truth tables:
    - `usage_ledger`
    - `usage_events`
    - `usage_rollups`
    - `quota_policies`
    - `billing_customers`
    - `billing_subscriptions`
    - `billing_invoices`
    - `audit_events`
- Events:
  - `usage.recorded`
  - `quota.exceeded`
  - `billing.subscription_changed`
  - `audit_event.created`
- Artifact:
  - Billing readiness is a report/control-plane evidence object.
  - It does not create customer invoices or payment-provider artifacts yet.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: output includes `organization_id` and `project_id`.
- Auth/RBAC: real billing mutations remain disabled until hosted auth and RBAC
  are enforced by A1.
- Usage: billable meters are derived from A3 usage ledger rows, which are in turn
  derived from A1 run/trace evidence and A2 judge evidence.
- Audit: invoice preview is public-safe and contains no raw private payload.
- Redaction: no API key, token, cookie, customer email, or payment secret is
  required in the UI contract.

## A1 / A2 Calibration

- A1 alignment:
  - A3 expects A1 to provide authoritative usage events, rollups, tenant scope,
    auth, and billing webhook backend later.
  - Current A3 readiness only reads local usage meters.
- A2 alignment:
  - A3 treats `judge_results` as a billable meter but does not change A2 judge
    score, pass/fail, or failure taxonomy semantics.
  - A2 cost policy and semantic judge cost metadata remain future inputs.
- A3 boundary:
  - A3 owns the billing surface and readiness summary, not real payment mutation.

## Safety Boundary

- No live payment provider was called.
- No real billing mutation was performed.
- No `.env.local` was read.
- No Ashr API key, GitHub token, cookie, signed URL, customer email, or payment
  secret was stored.

## Remaining Gaps

1. A1 needs production usage events and usage rollups in Postgres.
2. A1 needs billing provider webhook verification.
3. A3 needs real billing UI only after hosted auth/RBAC exists.
4. A2 needs stable cost-policy fields for semantic judge/model usage.
5. Report Center should later include billing readiness as a customer-facing
   control-plane artifact.
