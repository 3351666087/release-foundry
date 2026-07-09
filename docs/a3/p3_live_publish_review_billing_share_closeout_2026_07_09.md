# A3 Live Publish, Review, Billing, and Share Closeout - 2026-07-09

## Scope

This closeout covers the six A3 SaaS workflow asks from the team lead:

1. GitHub PR check live publishing
2. PR comment live publishing
3. reviewer approve / deny / waiver workflow
4. dashboard-visible human operation records
5. billing/admin reads usage and billing state
6. report share links can be revoked, expire, and leave audit evidence

## What is now wired

GitHub publishing is exposed through local A3 API routes:

- `POST /api/a3/github/check-run/publish`
- `POST /api/a3/github/pr-comment/publish`

Both routes default to dry-run. Live mode is gated behind hosted session or
service-account context, runtime token environment variables, RBAC checks, and
sanitized receipts. A3 does not accept raw GitHub tokens in request bodies.

Reviewer workflow now has three durable local actions:

- waiver
- approval
- denial

Each action records a sanitized review receipt, RBAC decision, audit event, and
event-outbox row. A2 remains the owner of judge semantics and release policy;
A3 only records the human decision workflow around those policy outputs.

Human operation records are visible through:

- `saas_admin_action_requests`
- `review_workflow_records`
- `audit_events`
- `event_outbox`
- `github_publish_receipts`

Billing/admin now reads read-only usage and billing readiness projections:

- `GET /api/a3/usage/ledger`
- `GET /api/a3/billing/readiness`
- `GET /api/a3/billing/migration-readiness`

A3 still does not perform checkout, invoice, subscription, provider webhook, or
payment mutation work. Those remain A1-owned backend and billing-ledger work.

Shareable reports already support lifecycle controls:

- `POST /api/a3/reports/share`
- `GET /api/a3/reports/:reportId`
- `GET /reports/:reportId`
- `GET /r/:shareToken`
- `POST /api/a3/reports/:reportId/view`
- `POST /api/a3/reports/:reportId/revoke`

The store tracks expiry, revoke, view audit, denied access, and sanitized share
link summaries without exposing raw share tokens.

## A1 / A2 calibration

A1 remains the source of truth for:

- runner outputs
- hosted auth/session/service accounts
- GitHub credentials and workers
- durable usage events
- billing ledger and provider integrations
- production database persistence

A2 remains the source of truth for:

- score
- pass/fail
- failure taxonomy
- release policy
- security verification
- judge semantics

A3 consumes these outputs and presents product workflow, review, report,
billing-readiness, and audit surfaces without changing A1 or A2 semantics.

## Safety

- No `.env.local` was read.
- No real Ashr API call was made.
- No live GitHub API call was made.
- No billing provider call was made.
- No hosted auth, team invite, API-key rotation, Trust publish, branch
  protection mutation, or cloud write was performed.
- No raw key, token, cookie, email, signed URL, local path, payment secret, or
  raw share token was written.

## Verification

Commands run in this closeout:

```text
node --check services/report/a3_store.mjs
node --check services/report/a3_api_server.mjs
node --check services/report/a3_auth_rbac_boundary.mjs
node --check apps/dashboard/src/app.mjs
node --test tests/a3/*.mjs
npm.cmd run test:e2e
```

Results:

- Full A3 Node suite: 260 pass, 0 fail.
- Playwright E2E: 10 pass, 0 fail.

## Remaining production work

1. Run GitHub check/comment live mode only from a maintainer-approved GitHub App
   or CI worker, then capture sanitized readback evidence.
2. Replace local fixture/file/memory persistence with A1-owned Postgres/RLS and
   hosted auth once available.
3. Replace read-only billing projections with A1 durable billing ledger and
   provider webhook evidence before claiming production billing.
