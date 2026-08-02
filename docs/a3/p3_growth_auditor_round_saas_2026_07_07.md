# A3 Growth-Auditor Round - SaaS Commercial Push - 2026-07-07

Role: A3 Growth-Auditor / commercial SaaS auditor.

Question: what should the next A3 round build so the dashboard becomes a paid Agent Release Intelligence SaaS instead of a local evidence viewer?

Short answer: A3 already has the right commercial spine: release gate, PR gate, War Room, incident replay, reviewer workflow, official parity, report exports, audit bundle, SaaS admin shell, API-backed data, DB-ready store, and hosted report payloads. The next round should make those surfaces durable, linked, and sellable as one release-governance workflow.

Safety boundary:

- Read local repo evidence only.
- Did not read, print, edit, or commit `.env.local`.
- Did not call live ReleaseFoundry, GitHub, billing, hosted auth, or external APIs.
- Did not modify code.
- Modified only this artifact.

## Main Plan Mapping

The original A3 plan in `docs/a3/a3_integration_plan.md` names six dashboard views:

1. Summary cards.
2. Run List.
3. Case Detail.
4. Trace Timeline.
5. Failure Clusters.
6. Report Export.

The current commercial SaaS surface now extends those views into buyer-facing workflows:

| Main plan view | SaaS commercial surface | Current repo evidence |
|---|---|---|
| Summary cards | Release War Room, usage/billing snapshot, SaaS runtime health | `services/report/report_builder.mjs`, `apps/dashboard/src/app.mjs`, `apps/dashboard/src/components/saas-runtime-panel.mjs` |
| Run List | PR Gate status, release gate history, API-backed run list | `services/report/a3_gate_cli.mjs`, `services/report/a3_api_server.mjs`, `services/report/a3_store.mjs` |
| Case Detail | Incident replay UI, reviewer workflow item, official demo run `11926` | `fixtures/a3/p3/releasefoundry_dataset_884_run_11926_ui_tests_detail.redacted.json`, `tests/a3/p3_releasefoundry_mapper.test.mjs` |
| Trace Timeline | Observability replay matrix, replay readiness, trace/tool/error evidence | `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`, `tests/a3/report_builder.test.mjs` |
| Failure Clusters | Reviewer Workflow Board, regression factory, top-risk case routing | `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`, `tests/a3/dashboard_wiring.test.mjs` |
| Report Export | Report Center, audit export, hosted report, verifiable bundle | `services/report/a3_shareable_report.mjs`, `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`, `tests/a3/shareable_report.test.mjs` |

## Evidence Base

- Main plan: `docs/a3/a3_integration_plan.md`
- Enterprise push: `docs/a3/p3_growth_auditor_round_2026_07_07_enterprise_push.md`
- SaaS admin console: `docs/a3/p3_growth_auditor_saas_admin_console_2026_07_07.md`
- SaaS API/DB slice: `docs/a3/p3_growth_auditor_saas_api_db_2026_07_07.md`
- Release War Room: `docs/a3/p3_release_war_room_growth_2026_07_07.md`, `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- PR Gate: `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`, `services/report/a3_gate_cli.mjs`, `services/report/a3_github_integration.mjs`
- Incident replay: `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`
- Reviewer workflow: `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`
- Official parity: `docs/a3/p3_official_code_crawl_parity_growth_2026_07_07.md`, `fixtures/a3/p3/releasefoundry_frontend_code_crawl_summary.redacted.json`
- API/DB/store: `services/report/a3_api_server.mjs`, `services/report/a3_store.mjs`, `tests/a3/a3_api_server.test.mjs`, `tests/a3/a3_store.test.mjs`
- Hosted report: `services/report/a3_shareable_report.mjs`, `tests/a3/shareable_report.test.mjs`
- UI wiring: `apps/dashboard/src/app.mjs`, `apps/dashboard/src/components/saas-admin-console.mjs`, `apps/dashboard/src/components/saas-runtime-panel.mjs`, `tests/a3/dashboard_wiring.test.mjs`

## Commercial Growth Points For Next Round

| ID | Growth point | Main plan mapping | Type | Evidence already present | Concrete next build |
|---|---|---|---|---|---|
| SaaS-01 | Release War Room should become the first screen for release owners. | Summary cards, Failure Clusters, Report Export | code, test, UI, docs | `services/report/report_builder.mjs`; `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`; `docs/a3/p3_release_war_room_growth_2026_07_07.md`; `tests/a3/dashboard_wiring.test.mjs` | Add a War Room snapshot id, release owner field, last-updated timestamp, and deep links to PR Gate, incident replay, reviewer board, and hosted report. |
| SaaS-02 | PR Gate should link every blocked check to a hosted War Room packet. | Run List, Report Export | code, test, API, docs | `services/report/a3_gate_cli.mjs`; `services/report/a3_github_integration.mjs`; `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`; `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json` | Add `war_room_url`, `hosted_report_url`, `bundle_root_hash`, and `reviewer_board_url` fields to GitHub check and PR comment payloads. |
| SaaS-03 | Live PR gate enforcement needs a safe GitHub App lane, not only dry-run payloads. | Run List, Report Export | code, API, docs | `services/report/a3_github_integration.mjs`; `tests/a3/a3_github_integration.test.mjs`; `docs/a3/p3_github_dry_run_integration_2026_07_07.md` | Add a plan-only GitHub App contract with installation id, permissions, check-run id persistence, and explicit dry-run/live policy gates. |
| SaaS-04 | Incident Replay Queue should become an actionable UI board. | Case Detail, Trace Timeline, Failure Clusters | code, test, UI, docs | `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`; `apps/dashboard/src/app.mjs`; `tests/a3/dashboard_wiring.test.mjs` | Add replay item states: queued, assigned, reproducing, reproduced, fixed, flaky, waived, and blocked-by-evidence. |
| SaaS-05 | Incident replay should emit a portable replay pack. | Trace Timeline, Report Export | code, API, docs | `services/report/report_builder.mjs`; `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`; `fixtures/a3/mock_run_results.json`; `fixtures/a3/mock_grade_results.json` | Define `a3.replay_pack.v1` with input hashes, case ids, trace ids, judge evidence ids, expected tool calls, media metadata, and replay command hints. |
| SaaS-06 | Reviewer Workflow Board needs durable workflow state. | Failure Clusters, Case Detail, Report Export | code, test, UI, API, docs | `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`; `services/report/report_builder.mjs`; `tests/a3/report_builder.test.mjs` | Add board item ids, assignee, lane, status, SLA, disposition, comments, and audit event references. |
| SaaS-07 | Reviewer workflow should be visible inside PR comments. | Run List, Failure Clusters, Report Export | code, test, API | `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`; `services/report/a3_gate_cli.mjs`; `tests/a3/a3_gate_cli.test.mjs` | Add a compact reviewer table to PR comments: owner, blocker count, missing evidence, waiver requirement, approval readiness, and next action. |
| SaaS-08 | Official parity should become a product acceptance gate. | Summary cards, Case Detail, Report Export | code, test, UI, docs | `docs/a3/p3_official_code_crawl_parity_growth_2026_07_07.md`; `docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md`; `fixtures/a3/p3/releasefoundry_frontend_code_crawl_summary.redacted.json`; `tests/a3/report_builder.test.mjs` | Add parity statuses to release gate: results-review mapped, observability mapped, usage read-only, admin/billing/key flows excluded, visual Results confirmation pending. |
| SaaS-10 | Report Center should become a release packet builder. | Report Export | code, test, UI, API, docs | `apps/dashboard/src/app.mjs`; `services/report/a3_shareable_report.mjs`; `tests/a3/shareable_report.test.mjs` | Add a Report Center manifest with JSON, Markdown, PR comment, GitHub check, audit bundle, hosted report, War Room, replay pack, and reviewer board artifacts. |
| SaaS-11 | Audit export should seal all commercial workflow artifacts, not only gate outputs. | Report Export | code, test, API, docs | `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`; `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`; `tests/a3/a3_gate_cli.test.mjs`; `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md` | Add War Room, incident replay, reviewer board, hosted report, SaaS admin action plan, and usage ledger artifacts to the bundle index. |
| SaaS-12 | Audit export needs archive-level verification. | Report Export | code, test, API, docs | `services/report/a3_gate_cli.mjs`; `tests/a3/a3_gate_cli.test.mjs`; `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md` | Add `verify --bundle <dir-or-zip>` and detached root-hash signature metadata. |
| SaaS-13 | Enterprise shell should move from "clean-room local shell" to tenant-aware admin surface. | Summary cards, Report Export | code, test, UI, API, docs | `services/report/a3_saas_admin.mjs`; `apps/dashboard/src/components/saas-admin-console.mjs`; `tests/a3/a3_saas_admin.test.mjs`; `docs/a3/p3_growth_auditor_saas_admin_console_2026_07_07.md` | Add tenant/project/repo selectors, role matrix, session status, audit log preview, and guarded action plans for each disabled mutation. |
| SaaS-14 | Usage/billing should graduate from read-only calibration to a usage ledger. | Summary cards, Report Export | code, test, UI, API, docs | `fixtures/a3/p3/releasefoundry_usage_quota_sample.redacted.json`; `fixtures/a3/p3/releasefoundry_usage_quota_api_probe.redacted.json`; `services/report/a3_saas_admin.mjs`; `tests/a3/report_builder.test.mjs` | Add `usage_ledger` records for runs, cases, judge calls, tool calls, replay packs, hosted reports, verifier runs, bundle bytes, retained days, and seats. |
| SaaS-15 | Usage/billing should influence release policy without performing billing mutations. | Summary cards, Run List | code, test, UI, API | `apps/dashboard/src/app.mjs`; `services/report/a3_saas_admin.mjs`; `tests/a3/a3_saas_admin.test.mjs` | Add warn-only and block-capable quota policy states while keeping checkout, plan upgrade, and billing mutation actions disabled. |
| SaaS-16 | Self-host console needs an installable product story. | Summary cards, Report Export | docs, API, UI | `docs/a3/p3_growth_auditor_round_2026_07_07_enterprise_push.md`; `docs/a3/p3_saas_api_db_migration_2026_07_07.md`; `apps/dashboard/src/components/saas-runtime-panel.mjs` | Add a self-host admin page concept covering Docker Compose, API server, DB, storage path, backup, restore, retention, offline verifier, and upgrade checks. |
| SaaS-17 | Self-host console should expose health checks through API. | Summary cards, Run List | code, test, API, UI | `services/report/a3_api_server.mjs`; `tests/a3/a3_api_server.test.mjs`; `apps/dashboard/src/components/saas-runtime-panel.mjs` | Extend `/api/a3/health` with store mode, migration status, artifact storage status, retention job status, verifier version, and redaction status. |
| SaaS-18 | API-backed data should become the default integration boundary. | Run List, Case Detail, Report Export | code, test, UI, API, docs | `services/report/a3_api_server.mjs`; `apps/dashboard/src/api-client.mjs`; `tests/a3/a3_api_server.test.mjs`; `docs/a3/p3_growth_auditor_saas_api_db_2026_07_07.md` | Add import endpoints for A1 RunResult and A2 GradeResult plus idempotency keys and validation errors. |
| SaaS-19 | API-backed dashboard needs loading, empty, error, and stale-data states. | Summary cards, Run List, Case Detail | code, test, UI | `apps/dashboard/src/api-client.mjs`; `apps/dashboard/src/app.mjs`; `tests/a3/dashboard_wiring.test.mjs` | Add visible API state badges and retry paths for `/api/a3/dashboard`, `/api/a3/runs`, `/api/a3/cases/:caseId`, and admin action plans. |
| SaaS-20 | DB-backed data should move from contract to first migration. | Run List, Case Detail, Trace Timeline, Report Export | code, test, API, docs | `services/report/a3_store.mjs`; `tests/a3/a3_store.test.mjs`; `docs/a3/p3_saas_api_db_migration_2026_07_07.md` | Add migrations for `tenants`, `projects`, `repos`, `runs`, `cases`, `grade_results`, `trace_events`, `reports`, `audit_events`, `usage_ledger`, and `review_items`. |
| SaaS-21 | DB-backed store should support Postgres first and keep fixture/file stores for demos. | Run List, Case Detail, Report Export | code, test, API | `services/report/a3_store.mjs`; `tests/a3/a3_store.test.mjs` | Add a SQL adapter behind the existing store interface and run contract tests against fixture, file, and SQL modes. |
| SaaS-22 | Hosted report should become an access-controlled page, not only a payload. | Report Export | code, test, UI, API, docs | `services/report/a3_shareable_report.mjs`; `services/report/a3_api_server.mjs`; `tests/a3/shareable_report.test.mjs`; `tests/a3/a3_api_server.test.mjs` | Add `GET /reports/:reportId` HTML route, access policy, expiry, revocation, view audit event, and redaction status banner. |
| SaaS-23 | Hosted report should become the Trust/report center handoff. | Report Export, Summary cards | code, test, UI, API | `services/report/a3_saas_admin.mjs`; `services/report/a3_shareable_report.mjs`; `apps/dashboard/src/components/saas-admin-console.mjs` | Connect Trust preview to hosted report id, audit bundle root hash, release gate status, reviewer approval status, and publish readiness. |
| SaaS-24 | Report Center should create a one-click "customer evidence packet." | Report Export | code, test, UI, docs | `apps/dashboard/src/app.mjs`; `fixtures/a3/p3/a3_gate_cli_report.redacted.md`; `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json` | Add packet presets: engineering PR review, executive sign-off, security audit, incident replay, and self-host retention export. |
| SaaS-25 | Redaction firewall should gate every hosted and exported artifact. | Report Export | code, test, API, docs | `services/report/export_redaction_firewall.mjs`; `services/report/a3_shareable_report.mjs`; `tests/a3/shareable_report.test.mjs`; `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md` | Add fail-closed findings with field path, artifact id, reason, severity, and remediation; block hosted report publication when findings are unresolved. |
| SaaS-26 | Enterprise identity should bind approvals to real actors. | Report Export, Failure Clusters | code, test, API, docs | `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`; `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`; `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md` | Add actor binding fields for GitHub actor, OIDC subject, SSO subject, local RBAC user, signer role, and separation-of-duties proof. |
| SaaS-27 | Waiver workflow should connect to remediation tracking. | Failure Clusters, Report Export | code, test, API, docs | `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`; `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`; `docs/a3/p3_waiver_validation_growth_2026_07_07.md` | Add follow-up issue id, due date, owner, risk class, revalidation gate, and automatic stale-waiver blocker. |
| SaaS-28 | Observability replay should connect A1/A2 evidence to production-style traces. | Trace Timeline, Case Detail | code, test, UI, API, docs | `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`; `services/report/report_builder.mjs`; `tests/a3/report_builder.test.mjs` | Add `trace_ingestion.v1`, trace pagination endpoint, latency/error rollups, tool-call diff anchors, and OpenTelemetry/ReleaseFoundry/A1 adapter placeholders. |
| SaaS-29 | Regression factory should turn replay outcomes into new test cases. | Failure Clusters, Trace Timeline | code, test, UI, docs | `docs/a3/p3_regression_factory_growth_2026_07_07.md`; `services/report/report_builder.mjs`; `tests/a3/report_builder.test.mjs` | Add "promote to regression" action plan with required A1 trace, A2 judge evidence, official parity status, and generated fixture path. |
| SaaS-30 | Commercial pricing proof should be visible in the product. | Summary cards, Report Export | docs, UI, API | `services/report/a3_saas_admin.mjs`; `docs/a3/p3_growth_auditor_saas_admin_console_2026_07_07.md`; `docs/a3/p3_growth_auditor_round_2026_07_07_enterprise_push.md` | Add ROI fields: risky releases blocked, reviewer hours saved, audit hours saved, replay packs produced, retained evidence bytes, and active reviewer seats. |

## Required Coverage Check

| Required topic | Covered by growth points |
|---|---|
| Release war room | SaaS-01, SaaS-02 |
| PR gate | SaaS-02, SaaS-03, SaaS-07 |
| Incident replay UI | SaaS-04, SaaS-05, SaaS-28 |
| Reviewer workflow | SaaS-06, SaaS-07, SaaS-26, SaaS-27 |
| Official parity | SaaS-08, SaaS-09, SaaS-28 |
| Report center | SaaS-10, SaaS-23, SaaS-24 |
| Audit export | SaaS-11, SaaS-12, SaaS-25 |
| Enterprise shell | SaaS-13, SaaS-26 |
| Usage/billing | SaaS-14, SaaS-15, SaaS-30 |
| Self-host console | SaaS-16, SaaS-17 |
| API-backed data | SaaS-18, SaaS-19 |
| DB-backed data | SaaS-20, SaaS-21 |
| Hosted report | SaaS-22, SaaS-23 |

## Highest-Value Next Round

The next round should not be another dashboard-only polish pass. The highest-value package is:

1. Hosted Report Center with access policy, redaction status, and audit bundle root hash.
2. PR Gate payloads that link to War Room, hosted report, reviewer board, and bundle verification.
3. Durable reviewer workflow schema with item lifecycle and audit events.
4. API import endpoints for A1/A2 evidence.
5. First DB migration and SQL store adapter contract.
6. Usage ledger and quota policy states.
7. Self-host console health page and deployment checklist.

Commercial one-liner:

> A3 should sell as the release-control, reviewer-workflow, and audit-evidence SaaS for agent changes: every risky PR gets a gate decision, War Room, replay queue, reviewer board, hosted report, and verifiable bundle.

## Auditor Call

A3 is close to a commercial SaaS story because the repo now contains real code/test/UI/API/docs evidence for the workflow buyers care about. The gap is no longer "what should the product be?" The gap is durability: identity, persistence, API import, DB storage, access-controlled hosted reports, audit retention, self-host health, and usage metering.

Do the next round as a product-system pass: link the existing surfaces together, persist their state, and make every exported report trace back to the same release id, PR head SHA, run id, reviewer item ids, bundle root hash, and hosted report id.
