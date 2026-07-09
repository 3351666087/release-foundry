# A3 Fail-Closed RBAC Write Paths - 2026-07-09

## Purpose

This round tightens the A3 SaaS backbone after the event outbox work. The
previous Auth/RBAC module described permissions and decisions; this round makes
the local API server enforce those decisions before mutation-like writes reach
the store.

Fail-closed means: if the caller does not have the required permission, A3
returns a sanitized `403` response and does not write reports, readbacks,
review records, admin requests, idempotency receipts, or event outbox rows.

## Enforced Routes

- `POST /api/a3/import/a1-run-result`
- `POST /api/a3/import/a2-grade-result`
- `POST /api/a3/releases/:releaseId/readbacks`
- `POST /api/a3/admin/actions/plan`
- `POST /api/a3/admin/actions/submit`
- `POST /api/a3/review/waivers`
- `POST /api/a3/review/approvals`
- `POST /api/a3/reports/share`
- `POST /api/a3/reports/:reportId/revoke`
- `POST /api/a3/reports/:reportId/view`
- `GET /api/a3/events/outbox`

## Added Operation Policies

- `view_report`
- `capture_release_readback`
- `read_event_outbox`
- `plan_admin_action`

These extend the existing `a3.rbac_policy.v1` contract without changing the
A1 or A2 data contracts.

## Local Demo Roles

The dashboard and tests now pass explicit local role headers for mutation-like
requests:

- reviewer: share report, submit waiver, submit approval, capture readback
- owner: submit admin action, revoke report
- auditor: read event outbox
- developer: still allowed to import A1/A2 local evidence through the existing
  `project:ingest` permission

This is not real hosted auth. It is a local fail-closed contract until A1
provides hosted auth/session middleware and production RBAC enforcement.

## Denied Response Safety

Denied responses use `a3.api_authz_denied.v1` and include:

- operation
- decision
- required permission
- role
- tenant scope
- metadata-only authz audit event

Denied responses do not echo the raw request body and do not expose emails,
Bearer values, cookies, API keys, signed URLs, or private evidence.

## A1/A2 Compatibility

- A1 still owns auth/session middleware, hosted service accounts, RunResult,
  Trace, Observation, ToolCall, and runtime evidence.
- A2 still owns Scenario, Judge, GradeResult, score, pass/fail, release gate,
  and failure taxonomy.
- A3 only blocks or allows product-console actions before they reach A3 report,
  review, admin, readback, and event outbox state.

## Validation

Focused validation passed:

```text
node --test tests/a3/a3_auth_rbac_boundary.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_readback_capture_cli.test.mjs tests/a3/a3_sqlite_store.test.mjs
```

Result:

```text
13 tests passed, 0 failed
```

## Remaining Work

- Replace local role headers with A1 hosted auth/session middleware.
- Persist authorization decisions in production Postgres/RLS.
- Add signed reviewer identity verification before approvals can affect live
  required checks.
- Add rate limits and abuse controls around denied mutation attempts.
