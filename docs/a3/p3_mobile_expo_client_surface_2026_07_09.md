# A3 Mobile Expo Client Surface - 2026-07-09

## Purpose

This round adds the first React Native / Expo contract surface for A3. The goal is not a full mobile app yet. The goal is to define and test the mobile release approval and incident alert shape so A3 can grow toward PWA, Expo, and mobile review workflows without drifting away from A1/A2 evidence.

## API / DB / Event / Artifact Contract

- API: mobile reads A3 dashboard, review workflow, hosted report, release evidence, and readback routes. Review waiver/approval mutation routes are declared but require hosted auth, RBAC, and audit before real use.
- DB: no DB migration is added. The mobile surface expects tenant-scoped A3 records from the existing A3 store/API contract.
- Event: mobile review actions must create audit events before they can affect a release decision.
- Artifact: mobile renders hosted report paths and artifact hash prefixes only. Raw share tokens, signed URLs, cookies, and API keys are not rendered.

## Tenant / Auth / RBAC / Usage / Audit

- Tenant: every mobile card must be scoped to an organization/project by the API layer.
- Auth: hosted auth is required before mobile can perform approval or waiver actions.
- RBAC: approvals require reviewer or admin permission.
- Usage: the mobile surface may display usage meter summaries but does not create billing events directly.
- Audit: waiver and approval actions require audit event receipts.
- Redaction: only redacted IDs, hash prefixes, and status labels are allowed on-device.

## A1 / A2 / A3 Integration

- A1: mobile consumes RunResult, Trace, Observation, ToolCall, and agent response readiness from A3 summaries.
- A2: mobile consumes GradeResult, score, pass/fail, release gate, failure taxonomy, and commercial readiness from A3 summaries.
- A3: mobile consumes Release Evidence, Hosted Report, Reviewer Workflow, Usage Ledger, Audit Event, and Artifact Registry status.

## Verification

```text
node --test tests/a3/a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
```

## Boundaries

- No `.env.local` read.
- No live ReleaseFoundry API call.
- No live billing/auth/team/API-key/Trust/cloud mutation.
- No A1 runner change.
- No A2 judge semantic change.
