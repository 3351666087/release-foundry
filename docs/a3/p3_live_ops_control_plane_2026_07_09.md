# A3 Live Ops Control Plane - 2026-07-09

## Goal

Turn the team lead's next six SaaS workflow asks into one A3 product-console
contract:

1. GitHub PR check live publishing
2. PR comment live publishing
3. reviewer approve / deny / waiver workflow
4. dashboard human operation records
5. billing/admin reads usage and billing state
6. report share links can be revoked, expire, and leave audit evidence

## What changed

- Added `a3.live_ops_control_plane.v1`.
- Added `GET /api/a3/live-ops/control-plane`.
- Added dashboard panel `Live Ops Control Plane`.
- Added static/API-backed dashboard wiring.
- Added fixture `fixtures/a3/p3/a3_live_ops_control_plane.redacted.json`.
- Added Node coverage in `tests/a3/a3_live_ops_control_plane.test.mjs`,
  `tests/a3/a3_api_server.test.mjs`, and `tests/a3/dashboard_wiring.test.mjs`.

## Why this exists

`a3.live_workflow_readiness.v1` answers "are these capabilities ready at a
high level?" The new control plane answers the next product question:

```text
For each live workflow, which API, DB table, audit event, dashboard field,
A1 dependency, A2 dependency, and next action are required?
```

That makes the dashboard easier to use as a SaaS implementation checklist
instead of only a demo screen.

## A1 / A2 boundary

- A1 owns hosted workers, GitHub credentials, durable usage events, billing
  ledger migrations, quota enforcement, provider webhooks, auth/RBAC, and DB
  persistence.
- A2 owns judge semantics, pass/fail, score, release policy, failure taxonomy,
  and security verification.
- A3 consumes those outputs downstream and presents them as workflow state. A3
  does not rewrite A1 runner results or A2 judge decisions.

## Safety

- No `.env.local` read.
- No live GitHub API call.
- No billing provider call.
- No team invite, API-key mutation, Trust publish, branch-protection mutation,
  or cloud write.
- No raw key, token, cookie, email, signed URL, local path, or payment secret is
  stored in the fixture, docs, dashboard, or tests.

## Remaining production work

1. Run the existing GitHub check/comment publisher from a maintainer-approved
   GitHub App or CI job and submit sanitized readback receipts to A3.
2. Swap fixture usage meters to A1 durable billing ledger rows after A1 exposes
   a read-only authenticated summary API.
3. Persist report share-link lifecycle and human operation rows in production
   Postgres with hosted auth/RBAC and audit retention.
