# A3 Commercial Growth Manifest - 2026-07-09

ANCHOR: A3_COMMERCIAL_GROWTH_MANIFEST

This round adds `a3.commercial_growth_manifest.v1`, a machine-readable commercial growth manifest for A3. The goal is not to describe vague roadmap ideas. The manifest records 20+ growth points with evidence bindings, explicit gaps, and API/DB/event/artifact contract surfaces so A3 can keep moving toward a sellable Agent Release Intelligence Platform.

The generated fixture is:

- `fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json`

The implementation and test are:

- `services/report/a3_commercial_growth_manifest.mjs`
- `tests/a3/a3_commercial_growth_manifest.test.mjs`

ANCHOR: GROWTH_POINT_CLASSIFICATION

The manifest classifies growth points across:

- revenue
- risk
- audit
- self-host
- usage
- billing
- e2e

Every growth point must bind to A1 evidence, A2 evidence, A3 evidence, or an explicit commercial gap. The purpose is to avoid empty product claims and force every growth idea to name what proves it today or what blocks it from enterprise readiness.

ANCHOR: API_CONTRACT

Planned API surfaces:

- `GET /api/a3/commercial-growth/manifest`
- `GET /api/a3/releases/:releaseId/commercial-growth`
- `POST /api/a3/commercial-growth/refresh`

No live route was added in this round. The manifest records the contract shape first so a later API-backed implementation can be added without inventing new semantics.

ANCHOR: DB_CONTRACT

Planned DB tables:

- `commercial_growth_manifests`
- `commercial_growth_points`
- `commercial_growth_evidence_links`
- `commercial_growth_gap_events`

These should become tenant-scoped SaaS tables before A3 claims durable hosted commercial growth tracking.

ANCHOR: EVENT_CONTRACT

Planned events:

- `commercial_growth.manifest_generated`
- `commercial_growth.point_recorded`
- `commercial_growth.gap_recorded`
- `commercial_growth.point_promoted`
- `commercial_growth.manifest_exported`

Events should contain ids, hashes, statuses, and counts only. They must not contain raw customer payloads, secrets, tokens, cookies, or private evidence bodies.

ANCHOR: ARTIFACT_CONTRACT

Artifact surfaces:

- `a3_commercial_growth_manifest.redacted.json`
- `p3_commercial_growth_manifest_2026_07_09.md`
- `release_evidence_summary`
- `report_center_manifest`
- `audit_bundle_index`

The manifest is redacted and public-safe. It is intended to be hashed into a future audit bundle and linked from Report Center.

ANCHOR: TENANT_AUTH_RBAC_USAGE_AUDIT

Tenant/auth/RBAC/usage/audit implications:

- Tenant: the manifest includes `organization_id`, `project_id`, and `release_id` scope.
- Auth: current state is local metadata only; hosted auth is required before live refresh.
- RBAC: planned roles include owner, admin, developer, reviewer, auditor, and billing admin.
- Usage: meter candidates include `growth_manifest_exports`, `growth_point_promotions`, `readback_checks`, and `audit_packet_exports`.
- Billing: billing mutation is disabled; this is read-only commercial evidence.
- Audit: append-only audit events are required before this becomes a hosted SaaS feature.

ANCHOR: A1_A2_INTEGRATION

A1 integration:

- A1 RunResult
- Trace
- ToolCall
- Observation
- WorkerDataModel
- SaaSControlPlane

A2 integration:

- A2 GradeResult
- ReleaseGate
- ScenarioSelection
- JudgeVersions
- CommercialReadiness
- CalibrationMatrix

A3 consumes these outputs downstream. This manifest does not alter A1 runner or A2 judge semantics.

ANCHOR: ACCEPTANCE

Acceptance evidence:

```text
node --test tests/a3/a3_commercial_growth_manifest.test.mjs
```

The test verifies:

- schema version
- at least 20 growth points
- required growth dimensions
- A1/A2/A3 evidence binding or explicit gaps
- API/DB/event/artifact contract surface
- generated fixture parity
- secret-free fixture content
- documentation anchors
- acceptance checklist entries

Safety boundary:

- No `.env.local` read.
- No API key printed.
- No live Ashr API call.
- No live GitHub mutation.
- No hosted billing/auth/team/API-key/Trust/cloud mutation.
- No raw official source, browser cookies, tokens, emails, local absolute user paths, or signed URLs written.
