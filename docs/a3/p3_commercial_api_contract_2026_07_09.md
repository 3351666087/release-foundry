# A3 Commercial API Contract - 2026-07-09

ANCHOR: A3_COMMERCIAL_API_CONTRACT

## Goal

Move A3 from dashboard-only proof toward the commercial SaaS API surface defined
in `docs/strategy/large-saas-a1-a2-a3-full-plan.md`.

This round adds `a3.commercial_api_contract.v1`, a machine-readable map from
commercial `/v1` SaaS endpoints to current A3 product surfaces. It does not
claim that A1/A2 backend services are complete. It tells the team what is
implemented locally, what is read-only, what is plan-only, and what is blocked
until A1 hosted auth/RBAC/payment backends exist.

## Files

- `services/report/a3_commercial_api_contract.mjs`
- `fixtures/a3/p3/a3_commercial_api_contract.redacted.json`
- `tests/a3/a3_commercial_api_contract.test.mjs`
- `GET /api/a3/commercial-api/contract`

## Endpoint Coverage

ANCHOR: ENDPOINT_COVERAGE

The contract currently maps 30 commercial endpoints, including:

- `GET /v1/me`
- `GET /v1/organizations`
- `POST /v1/projects`
- `POST /v1/api-keys`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/trace-events`
- `POST /v1/artifacts/upload-url`
- `POST /v1/release-gates/evaluate`
- `POST /v1/release-gates/{release_gate_id}/waivers`
- `POST /v1/release-gates/{release_gate_id}/approvals`
- `POST /v1/release-gates/{release_gate_id}/denials`
- `GET /v1/evidence-bundles/{bundle_id}`
- `GET /v1/reports`
- `POST /v1/reports/{report_id}/share`
- `GET /v1/usage`
- `GET /v1/billing/subscription`
- `POST /v1/billing/checkout`
- `POST /v1/billing/portal`

Each endpoint records:

- owner lane
- A3 product surface
- local A3 route
- RBAC requirement
- DB tables
- event names
- artifact types
- usage meters
- A1/A2 dependencies
- implementation status

## API Contract

ANCHOR: API_CONTRACT

New local A3 API route:

```text
GET /api/a3/commercial-api/contract
```

Response schema:

```text
a3.commercial_api_contract.v1
```

This is a read-only A3 route. It does not create organizations, projects, API
keys, billing checkout sessions, payment portal sessions, hosted reports, or
live Ashr resources.

## DB Contract

ANCHOR: DB_CONTRACT

The A3 DB contract now includes:

```text
commercial_api_contracts
source_artifacts
event_outbox
```

The SQL migration contract includes a tenant-scoped table with:

- `organization_id`
- `tenant_id`
- `workspace_id`
- `project_id`
- `environment_id`
- `contract_schema_version`
- endpoint counts
- `contract_hash`
- redacted JSON payload

This keeps the contract ready for Postgres/MySQL/SQLite without making A3 the
source of truth for A1 backend state.

## Event Contract

ANCHOR: EVENT_CONTRACT

The contract declares `ashr.event_envelope.v1` with:

- `event_id`
- `event_type`
- `schema_version`
- `organization_id`
- `tenant_id`
- `workspace_id`
- `project_id`
- `environment_id`
- `actor_id`
- `request_id`
- `trace_id`
- `resource_type`
- `resource_id`
- `created_at`
- `payload_ref`
- `payload_hash`
- `redaction_status`

A3 only models this envelope in this round. Durable event publication remains
A1-owned, and judge/policy event correctness remains A2-owned. The local
contract module is `services/report/a3_event_envelope.mjs`; the future durable
outbox table is `event_outbox`.

## Artifact Contract

ANCHOR: ARTIFACT_CONTRACT

The redacted fixture is:

```text
fixtures/a3/p3/a3_commercial_api_contract.redacted.json
```

Commercial artifact types referenced by the endpoint map include:

- `run_result`
- `trace_event_batch`
- `tool_call_batch`
- `judge_result`
- `release_gate_report`
- `waiver_request`
- `approval_record`
- `denial_record`
- `hosted_report`
- `redaction_report`
- `usage_ledger`
- `billing_readiness_snapshot`
- `audit_bundle_index`

This round also introduces source-artifact hash summaries for A1/A2 inputs:

- `a1_run_result`
- `a1_trace_event_batch`
- `a1_tool_call_batch`
- `a2_grade_result`
- `a2_release_gate`

These entries store ids, counts, source contracts, redaction status, and
SHA-256 content hashes only. They do not embed raw A1 traces, raw A2 judge
payloads, secrets, cookies, tokens, emails, or signed URLs.

## Tenant/Auth/RBAC/Usage/Audit

ANCHOR: TENANT_AUTH_RBAC_USAGE_AUDIT

- Tenant: every endpoint is scoped by organization/tenant/workspace/project/environment.
- Auth: A3 stays read-only or plan-only until A1 hosted auth exists.
- RBAC: roles are declared, but live enforcement belongs to A1 middleware.
- Usage: A3 records read-only meters; A1 billing ledger is the future source of truth.
- Audit: event payloads must use ids, refs, hashes, statuses, and counts only.
- Billing: checkout and portal routes are blocked until payment backend and RBAC exist.

## A1/A2 Integration

ANCHOR: A1_A2_INTEGRATION

A3 consumes:

- A1 RunResult
- A1 TraceEvent
- A1 ToolCall
- A1 artifact refs
- A1 usage preview
- A2 GradeResult
- A2 ReleaseGate
- A2 CommercialReadiness
- A2 ResultPersistence
- A2 ReleaseUnblockChecklist

A3 does not mutate A1 runner, SDK, auth, quota, or artifact semantics. A3 does
not alter A2 outputs, and A3 does not change judge scores, pass/fail,
thresholds, release policies, or failure classes.

## Acceptance

ANCHOR: ACCEPTANCE

Run:

```text
node --test tests/a3/a3_commercial_api_contract.test.mjs
```

Expected result:

- contract validates
- fixture matches current builder
- API route returns the contract
- DB migration includes `commercial_api_contracts`
- no API key, token, email, cookie, local user path, or raw signed URL appears
