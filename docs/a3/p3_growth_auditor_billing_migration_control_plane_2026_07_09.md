# A3 Growth-Auditor Billing Migration Control Plane - 2026-07-09

ANCHOR: A3_GROWTH_AUDITOR_BILLING_MIGRATION_CONTROL_PLANE

Role: Growth-Auditor / Money-Grade Auditor.

Scope: audit this A3 round from live ops to billing migration API/dashboard/report
as a commercial product surface. This artifact is docs-only and public-safe. It
does not read `.env.local`, does not call live Ashr/GitHub/billing APIs, does not
write secrets, and does not change A1/A2/other-worker code.

## Executive Verdict

This A3 round materially improved commercial readiness. It moved A3 from
"dashboard/report demo" toward a control-plane layer that can explain live ops,
billing migration readiness, usage/billing state, review workflow, PR gate
evidence, API platform coverage, and enterprise audit posture.

Sellable now:

- Design-partner pilot for release governance, PR gate evidence, reviewer
  workflow, report sharing, usage/billing preview, and billing migration planning.
- Sales-engineering packet for enterprise/self-host buyers who need to see API,
  DB, event, artifact, tenant, auth, RBAC, usage, audit, and A1/A2 boundaries.
- Internal implementation control plane for deciding which work can become live
  next without pretending mocked/read-only paths are production billing.

Not sellable yet:

- Production billing, checkout, customer subscription management, entitlement
  enforcement, or provider webhook execution.
- Hosted enterprise SaaS with real auth/RBAC, Postgres/RLS, immutable storage,
  live branch protection, and durable event replay.
- Self-host package with one-command install, backup/restore, upgrade test,
  object custody, and offline audit verification.

Money-grade call:

```text
This round can help increase ACV if sold honestly as governed release evidence
plus billing migration control-plane readiness. It should not be sold as live
billing or production enterprise enforcement until A1-owned auth/RBAC, durable
DB, billing ledger, provider webhook, and hosted worker paths are wired.
```

## Evidence Anchors

ANCHOR: EXISTING_EVIDENCE_ANCHORS

| Direction | Existing anchor | Commercial signal |
|---|---|---|
| PR gate | `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`; `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md`; `tests/a3/a3_gate_cli.test.mjs` | A3 can frame release governance as required-check/readback evidence, but live branch protection is still future integration work. |
| production replay | `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_observability_replay_2026_07_07.md`; `tests/a3/a3_release_evidence.test.mjs` | Replay and release evidence are moving toward production incident/regression confidence. |
| enterprise audit | `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md`; `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`; `tests/a3/a3_audit_archive.test.mjs` | Audit bundle/archive language supports compliance sales, pending immutable custody. |
| self-host | `docs/a3/p3_self_host_console_growth_2026_07_07.md`; `tests/a3/self_host_console_contract.test.mjs`; `tests/a1/test_local_self_host_smoke_compose.py` | Self-host story exists as console/contract evidence, not yet turnkey install. |
| trace ingestion | `docs/a1/schemas/trace_event.schema.json`; `docs/a1/saas_ingestion_quickstart.md`; `tests/a3/a1_a2_compatibility_contract.test.mjs` | A3 can preserve A1 trace evidence downstream, but A1 remains source of ingestion truth. |
| judge calibration | `docs/a3/p3_api_calibration_import_error_shapes_2026_07_07.md`; `docs/a3/p3_growth_auditor_peer_branch_calibration_2026_07_09.md`; `tests/a3/api_calibration_contract.test.mjs` | A3 can expose calibration/readiness evidence while A2 owns judge semantics. |
| incident report | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`; `docs/a3/p3_growth_auditor_incident_replay_2026_07_07.md`; `docs/screenshots/a3-dashboard-incident-replay-queue.png` | Incident replay/reporting is a buyer-relevant risk reduction surface. |
| review workflow | `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`; `docs/a3/p3_growth_auditor_reviewer_workflow_2026_07_07.md`; `tests/a3/a3_review_workflow.test.mjs` | Approval/denial/waiver workflow is a direct enterprise governance feature. |
| billing/usage | `docs/a3/p3_billing_readiness_contract_2026_07_09.md`; `docs/a3/p3_billing_migration_readiness_2026_07_09.md`; `docs/a3/a3_billing_usage_summary_2026_07_09.md`; `tests/a3/a3_billing_readiness.test.mjs`; `tests/a3/a3_billing_migration_readiness.test.mjs` | Read-only usage/billing preview and A1 billing migration bridge are strong sales-engineering artifacts, not live charging. |
| API platform | `docs/a3/p3_commercial_api_contract_2026_07_09.md`; `docs/a3/openapi/a3_commercial_api.openapi.json`; `tests/a3/a3_commercial_api_contract.test.mjs`; `tests/a3/a3_commercial_openapi_contract.test.mjs` | A3 now has an endpoint map/OpenAPI artifact that can become the product-console API contract. |
| live ops control plane | `docs/a3/p3_live_ops_control_plane_2026_07_09.md`; `tests/a3/a3_live_ops_control_plane.test.mjs`; `tests/a3/dashboard_wiring.test.mjs` | Six requested SaaS workflow lanes are mapped into API/DB/audit/dashboard dependencies. |
| live workflow readiness | `docs/a3/p3_live_workflow_readiness_2026_07_09.md`; `tests/a3/a3_live_workflow_readiness.test.mjs` | A3 can state what is local, read-only, or blocked before external mutation. |

## New Sellable Capabilities This Round

ANCHOR: NEW_SELLABLE_CAPABILITIES

1. Live ops control plane: A3 now maps GitHub publishing, reviewer workflow,
   human operation records, billing/admin read state, and hosted report link
   governance into one inspectable product-console contract.
2. Live workflow readiness: A3 can answer whether each commercial workflow is
   local, API-backed, audit-backed, read-only, or blocked by A1/A2 work.
3. Billing migration bridge: A3 consumes A1 durable billing migration and replay
   evidence as a read-only readiness contract, including ledger/provider tables,
   replay statuses, totals, and safety boundaries.
4. Billing/usage summary: A3 can show plan/quota/meter/overage-style evidence in
   reports without enabling payment mutation.
5. API platform contract: A3 maps commercial `/v1` endpoints, local routes,
   owner lanes, RBAC requirements, DB tables, event names, artifact types, usage
   meters, and implementation status.
6. Enterprise audit posture: A3 can package release, report, readback, review,
   usage, billing readiness, and audit archive evidence into buyer-readable
   artifacts.
7. PR gate and review workflow story: A3 can show how a release decision becomes
   a check/comment/readback/reviewer approval artifact, even before live branch
   protection is enabled.
8. Self-host sales story: A3 has enough docs/tests to describe the self-host
   console contract and what remains for install/runtime hardening.
9. A1/A2 compatibility guardrail: A3 repeatedly states that it consumes A1
   runner/trace/billing facts and A2 judge/release semantics downstream only.
10. Dashboard/report proof: API-backed dashboard and report builder tests turn
   these control-plane claims into locally executable evidence.

## Toy / Mocked / Read-Only Surfaces That Must Upgrade

ANCHOR: TOY_MOCKED_READ_ONLY_UPGRADE_LIST

| Surface | Current state | Required upgrade |
|---|---|---|
| Billing provider | Read-only migration readiness; no provider call. | A1-owned webhook verifier, idempotency, reconciliation, provider event storage, and A3 read-only UI over authenticated summaries. |
| Checkout / portal | Blocked or plan-only. | Enable only after hosted auth/RBAC, entitlement policy, provider backend, and audit events exist. |
| Usage ledger | A3 summary/preview from fixtures/local evidence. | A1 durable usage events, rollups, quota enforcement, chargeback grouping, and replay-safe billing export. |
| Live GitHub PR gate | Dry-run/readback evidence and workflow contracts. | Maintainer-approved GitHub App/Action, branch protection proof, required-check receipt, and sanitized readback capture. |
| Production replay | Replay matrix/incident queue evidence. | Durable trace ingestion, replay runner, replay result storage, incident report export, and regression promotion policy. |
| Enterprise audit | Archive/index/verifier docs and tests. | Immutable object storage, retention policy, WORM/object-lock proof, verifier CLI, and customer audit packet. |
| Self-host | Console contract and smoke hints. | Compose/Kubernetes install, migrations, seed data, backup/restore, upgrade test, offline license/audit mode. |
| Trace ingestion | A1 schema and A3 compatibility consumer. | Hosted ingestion endpoint, batching/idempotency, validation failures, tenant isolation, and trace replay linkage. |
| Judge calibration | Import/calibration docs and A2-owned semantics. | Versioned calibration matrix in dashboard/report, drift alerts, human calibration review, and cost policy display. |
| Review workflow | Local approval/denial/waiver shape. | Durable identity, separation-of-duties, signed approval, expiry/revocation, and audit export. |
| API platform | Commercial endpoint map/OpenAPI artifact. | Generated client, route-level schema validation, auth/RBAC examples, error catalog, and compatibility versioning. |

## ACV, Risk, Enterprise, Self-Host, Audit, Compliance Impact

ANCHOR: ACV_RISK_ENTERPRISE_IMPACT

ACV expansion:

- PR gate plus review workflow can sell to engineering leaders as release risk
  governance instead of a generic dashboard.
- Billing/usage visibility creates a path to usage-based pricing, chargeback,
  enterprise invoice review, and finance stakeholder demos.
- API platform mapping supports sales engineering, customer integrations, and
  partner/platform conversations.
- Enterprise audit and self-host artifacts create higher-tier packaging for
  regulated buyers.

Lower launch risk:

- Live workflow readiness and live ops control plane prevent false readiness
  claims by labeling blocked, read-only, local, mocked, and external-mutation
  paths.
- Production replay, incident report, and judge calibration evidence give teams
  a way to catch regressions before release.
- A1/A2 boundary language prevents A3 from rewriting runner, billing, or judge
  truth.

Enterprise/self-host/audit/compliance support:

- Tenant/auth/RBAC/usage/audit implications are now stated across billing,
  commercial API, live ops, report, review, and audit docs.
- Self-host has a visible console contract, but still needs install/runtime
  hardening.
- Compliance story is viable only after source artifact hashes, immutable
  storage, durable events, and verifier workflows become mandatory.

## Next-Round Growth Points

ANCHOR: NEXT_ROUND_20_PLUS_GROWTH_POINTS

| ID | Growth point | Parallel lane | Output required |
|---|---|---|---|
| G01 | Turn PR gate dry-run/readback into a required-check evidence packet. | PR gate / GitHub | Redacted required-check receipt with commit SHA, check name, status, payload hash, and branch-protection state. |
| G02 | Add production replay readiness matrix to release evidence. | production replay | Report section linking source trace hash, replay run id, regression result, and promotion decision. |
| G03 | Create incident report export from incident replay queue. | incident report | Customer-safe Markdown/JSON incident report with timeline, failed cases, replay state, owner, and remediation. |
| G04 | Promote enterprise audit bundle verifier into a documented customer workflow. | enterprise audit | Verifier command, expected outputs, hash checks, and failure examples. |
| G05 | Build self-host readiness packet. | self-host | Compose smoke, migration check, seed fixture, backup/restore placeholder, and offline audit checklist. |
| G06 | Add trace ingestion contract test for A3 imports. | trace ingestion | Test proving trace events retain ids, order, tool refs, redaction status, and source hash. |
| G07 | Add trace ingestion failure catalog. | trace ingestion | Public-safe error shapes for invalid schema, wrong tenant, duplicate batch, and oversized payload. |
| G08 | Surface judge calibration status in dashboard top-level readiness. | judge calibration | Calibration panel with judge version, sample count, drift state, blocker count, and A2 authority. |
| G09 | Add calibration-to-release-gate linkage. | judge calibration | Release evidence must name calibration matrix/version used by A2 outputs. |
| G10 | Make review workflow durable-storage receipts mandatory. | review workflow | Approval/denial/waiver rows with actor id, role, tenant, reason hash, expiry, and event id. |
| G11 | Add separation-of-duties rules to review workflow. | review workflow | Test that author cannot approve own release without explicit waiver policy. |
| G12 | Wire billing migration readiness into the API platform contract. | billing/usage / API platform | Endpoint map entries for ledger summary, provider events readback, and billing audit export. |
| G13 | Add usage chargeback preview by org/project/release/report. | billing/usage | Read-only usage rollup table and report section; no payment mutation. |
| G14 | Add billing export approval workflow. | billing/usage / review workflow | Billing admin approval receipt for exporting invoice-preview or ledger-summary data. |
| G15 | Add provider replay conflict dashboard state. | billing/usage | UI/report state for accepted, duplicate, conflict, rejected billing replay events. |
| G16 | Generate a typed client from A3 OpenAPI. | API platform | Generated or checked TypeScript client used by dashboard API calls. |
| G17 | Add route-level schema validation for A3 API-backed dashboard payloads. | API platform | Tests that server response matches OpenAPI/JSON schema before render. |
| G18 | Add A3 API error catalog. | API platform | Standard errors for auth denied, RBAC denied, tenant mismatch, validation failed, unavailable upstream. |
| G19 | Add two-tenant negative tests across report/review/billing/live-ops routes. | enterprise audit / API platform | Same tenant allowed, wrong tenant denied, missing auth denied where applicable. |
| G20 | Add source artifact hash registry for A1 traces and A2 judge outputs. | enterprise audit / trace ingestion / judge calibration | Registry rows for A1 RunResult, TraceEvent batch, ToolCall batch, A2 GradeResult, ReleaseGate. |
| G21 | Add immutable hosted report snapshot hash. | enterprise audit / review workflow | Hosted report includes source hashes, generated hash, expiry/revocation events, and view receipts. |
| G22 | Add object-storage custody contract. | enterprise audit / self-host | Storage ref, content hash, retention class, no signed URL leakage, and deletion/hold policy. |
| G23 | Add API platform customer quickstart. | API platform | Public-safe example: fetch release evidence, fetch usage summary, fetch billing readiness, export report. |
| G24 | Add enterprise audit dashboard filter set. | enterprise audit | Auditor view for release, report, billing, PR gate, incident report, and review workflow evidence. |
| G25 | Add self-host upgrade simulation. | self-host | Test/doc proving migration from prior fixture version to current contract version. |
| G26 | Add production replay cost/usage meter. | billing/usage / production replay | Meter replay runs and judge evaluations without charging real customers yet. |
| G27 | Add PR comment live-publish approval gate. | PR gate / review workflow | Reviewer-approved PR comment payload with redaction scan and readback hash. |
| G28 | Add incident-to-billing impact view. | incident report / billing/usage | Show whether failed/replayed cases are billable, credited, or excluded. |
| G29 | Add compliance control mapping. | enterprise audit | Map audit evidence to SOC2-style controls: access, change management, incident response, logging. |
| G30 | Add commercial launch checklist gate. | API platform / enterprise audit | One doc/test that fails unless PR gate, replay, audit, self-host, trace, judge, incident, review, billing, and API anchors exist. |

Parallelization plan:

- PR gate lane: G01, G27 can run together.
- Replay/incident lane: G02, G03, G26, G28 can run together.
- Enterprise audit/self-host lane: G04, G05, G19, G21, G22, G24, G25, G29 can
  run together.
- Trace/judge lane: G06, G07, G08, G09, G20 can run together.
- Review/billing lane: G10, G11, G12, G13, G14, G15 can run together.
- API platform lane: G16, G17, G18, G23, G30 can run together.

## Commercial Upgrade Priority

ANCHOR: COMMERCIAL_UPGRADE_PRIORITY

1. Close API platform foundations first: OpenAPI coverage, generated client,
   route validation, and error catalog.
2. Then close audit foundations: source artifact hashes, event envelope,
   immutable report snapshot, and audit verifier workflow.
3. Then close enterprise trust: two-tenant negative tests, RBAC denied states,
   review workflow durability, and compliance mapping.
4. Then close revenue readiness: A1-backed usage ledger read API, billing export
   approval, replay conflict visibility, and invoice-preview controls.
5. Then close deployment packaging: self-host install, upgrade simulation,
   backup/restore, and offline audit packet.

## Safety And Non-Claims

ANCHOR: SAFETY_AND_NON_CLAIMS

- No `.env.local` was read.
- No live Ashr API was called.
- No live GitHub API was called.
- No billing provider was called.
- No checkout, portal, subscription, invoice, team invite, API-key rotation,
  Trust publish, branch-protection mutation, or cloud mutation was performed.
- No secret, token, cookie, email, signed URL, payment data, raw provider
  payload, or private evidence body is required by this artifact.
- A3 remains a downstream product-console/report/review/audit surface for A1
  runner/billing/auth facts and A2 judge/release-policy facts.

## Acceptance

ANCHOR: ACCEPTANCE

This artifact is intentionally testable. The companion test must prove:

- the document contains the required directions: PR gate, production replay,
  enterprise audit, self-host, trace ingestion, judge calibration, incident
  report, review workflow, billing/usage, and API platform;
- at least 20 next-round growth points exist;
- existing evidence anchors point at committed docs/tests/artifacts;
- safety boundaries and non-claims are explicit.
