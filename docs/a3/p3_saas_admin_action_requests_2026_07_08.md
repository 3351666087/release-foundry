# P3 SaaS Admin Action Requests

Date: 2026-07-08

## Goal

Move the A3 SaaS Admin Console one step beyond static plan cards. The dashboard can now record safe, local admin action requests for login/team/usage/API-key/trust/cloud-management workflows without performing any real ReleaseFoundry cloud mutation.

## What changed

- Added `a3.saas_admin_action_request.v1`.
- Added `a3.saas_admin_action_receipt.v1`.
- Added `POST /api/a3/admin/actions/submit`.
- Added `GET /api/a3/admin/actions`.
- Added `saas_admin_action_requests` to the SQL migration contract.
- Added SQLite persistence for admin action request rows.
- Added dashboard `Record Request` / `Record Guardrail` control in the SaaS Admin Console.
- Added SaaS Admin action request summary and latest requests to report exports.

## Safety model

The request workflow is intentionally safe:

- No real OAuth login is performed.
- No real team invite email is sent.
- No real API key is created, rotated, revealed, or revoked.
- No billing or quota mutation is performed.
- No Trust page is publicly published.
- No live ReleaseFoundry cloud object is created, deleted, or modified.
- Actor identity is stored as a hash or redacted placeholder only.
- Email, token, cookie, password, and secret-like target fields are dropped or redacted.

## Why this matters commercially

This makes A3 feel more like a SaaS control plane:

- A reviewer can see that dangerous admin actions are governed.
- A customer can see that admin actions become audit events.
- A future hosted version has a clear DB table for approvals and admin workflow.
- The product can support enterprise controls without leaking secrets or mutating real ReleaseFoundry state during the student MVP.

## A1/A2 compatibility

This does not change A1 runner output or A2 judge semantics.

A3 still reads normalized A1 run/case/trace/tool-call evidence and A2 score/pass/fail/failure-class evidence. The SaaS Admin Console only adds product workflow state around those results.

## Verification

Focused tests passed:

```text
node --test tests/a3/a3_saas_admin.test.mjs tests/a3/a3_store.test.mjs
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

Result:

```text
79 tests
79 pass
0 fail
```

Syntax checks passed:

```text
node --check services/report/a3_store.mjs
node --check services/report/a3_saas_admin.mjs
node --check services/report/a3_api_server.mjs
node --check apps/dashboard/src/app.mjs
```

## Remaining gaps

- Real hosted auth and RBAC enforcement are not implemented.
- Real API key hashing and one-time reveal service are still future work.
- Real team invite email delivery is still future work.
- Real Trust publishing needs signed approvals and immutable hosted reports first.
- Production Postgres/MySQL deployment is still future work; this pass verifies local SQLite plus SQL contract.
