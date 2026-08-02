# A3 Event Outbox SaaS Backbone - 2026-07-09

## Purpose

This round advances A3 from a dashboard/report MVP toward the commercial SaaS
plan in `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

The key change is executable `event_outbox` behavior. Every important A3
control-plane write now creates a metadata-only `releasefoundry.event_envelope.v1` row
that can later feed audit logs, usage metering, billing, trust center evidence,
worker delivery, and production database persistence.

## Covered Write Paths

- `POST /api/a3/reports/share`
- `POST /api/a3/reports/:reportId/view`
- `POST /api/a3/reports/:reportId/revoke`
- `POST /api/a3/admin/actions/submit`
- `POST /api/a3/review/waivers`
- `POST /api/a3/review/approvals`
- `POST /api/a3/releases/:releaseId/readbacks`

## New Read Surface

- `GET /api/a3/events/outbox`

The API returns `a3.event_outbox_list.v1` with event counts, event type counts,
delivery status counts, tenant scope, and sanitized event rows.

## Dashboard Payload

`GET /api/a3/dashboard` now includes:

- `event_outbox.schema_version = a3.event_outbox_dashboard.v1`
- `event_outbox.event_count`
- `event_outbox.event_type_counts`
- latest metadata-only events
- an explicit A1/A2 boundary note

This gives the dashboard a SaaS-control-plane summary without changing A1 or
A2 source data.

## Idempotency

The same write paths now accept idempotency keys at the A3 boundary. Repeated
requests with the same key and same payload return a duplicate replay receipt;
reusing the same key with a different payload raises the existing A3
idempotency conflict error.

This is especially important for:

- report share creation
- report view counting
- report revocation
- admin action request recording
- waiver/approval submit
- release readback capture

## Safety

The outbox is metadata-only:

- no raw payload body is embedded
- no raw share token is stored
- no API key is stored
- no cookie is stored
- no signed media URL is stored
- no raw email is stored
- actors are represented as safe IDs or hashes

Event payloads are hashed with SHA-256 through the existing
`releasefoundry.event_envelope.v1` builder.

## A1/A2 Compatibility

This round does not change A1 or A2 semantics.

- A1 still owns RunResult, Trace, Observation, ToolCall, runner evidence, and
  runtime artifacts.
- A2 still owns Scenario, Judge, GradeResult, score, pass/fail, release gate,
  and failure taxonomy.
- A3 only records downstream product-console actions around reports, review,
  admin, and release evidence visibility.

## Validation

Focused validation passed:

```text
node --test tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_tenant_event_source_artifact_contract.test.mjs
```

Result:

```text
12 tests passed, 0 failed
```

## Remaining Work

- Add fail-closed RBAC checks directly around mutation-like write routes.
- Add A1/A2 schema drift tests against the latest shared schemas.
- Persist event outbox rows in the production DB adapter when a real hosted DB
  replaces local memory/file state.
- Add worker delivery states beyond local `pending` rows.
- Surface event outbox details in the React/Next dashboard once the HTML shell
  migration starts.
