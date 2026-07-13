# P3 Worklog

## 2026-07-12 - Provider-Neutral Goal Reconfirmation And Security Closure

- Reconfirmed current GitHub `main` `ccf6ce5` and strategy blob `575b31b8`.
- The new A3 Goal preserves prior P3 official-product calibration as optional
  reference evidence; it does not restore Ashr as a required runtime or CI
  dependency.
- No Ashr API call, mutation, quota spend, browser-account action, or key read
  was needed for this security round.
- `.env.local` remained ignored and was not printed, edited, staged, or
  included in evidence.
- Closed hosted resource-selection, five-level scope, share-token server-time,
  trusted-principal, denial-schema, unknown-route-audit, and demo live-GitHub
  escape defects.
- Added identical-ID cross-tenant tests while preserving A1 RunResult and A2
  GradeResult/Decision Ledger semantics.
- Added an A2 Decision Ledger authorization barrier before any live GitHub
  transport and kept the merged-main `release_ready=false` sample blocked.
- Closed the follow-up independent-audit bypasses: direct startup is hosted by
  default, the standalone GitHub CLI is dry-run only, hosted live writes need
  server-side A2 and tenant GitHub resolvers, and foreign-only waivers fail.
- Added exact-scope aggregate filtering, fully scoped new records, a typed
  Partial state, and desktop/mobile visual evidence. No Ashr API was needed:
  Ashr remains an optional calibration provider, not a runtime dependency.
- Read-only peer calibration records A2 draft `a1cdc00` provider provenance and
  independent high-risk review as unmerged watch signals only.
- Added source-plus-five-level snapshot identity, dedicated SQLite GitHub
  receipt/event-outbox persistence, honest fixture `db_ready=false`,
  Partial-before-empty rendering, and runtime/OpenAPI parity `53/53`.
- Current verification: A3 `387/387`, Playwright `33/33`, Webapp check passed,
  A1 session lifecycle `35/35`, A2 trusted spine `7/7`, both CL guards passed,
  real-format long token/key scan 0 matches, and diff check passed.
- Current status remains local implementation plus contract support, not
  production hosted identity, Postgres/RLS, or customer deployment proof.
- Production PostgreSQL/RLS, complete production-table scope policies,
  deployed A1/A2/GitHub resolvers, and malformed/OPTIONS audit coverage remain
  open. The local SQLite proof must not be described as production custody.

## 2026-07-09 - Commercial Growth Round 6 Reviewer Denial / Human Action / Runtime Reads

Continued A3 from the commercial SaaS strategy bus and focused on the next
review/governance/runtime requirements.

Implemented this round:

- Added denial as the third reviewer action beside waiver and approval.
- Added `POST /api/a3/review/denials` in the local A3 API server.
- Added memory/file/SQLite store support for denial records.
- Added `denial.submitted` metadata-only event-outbox evidence.
- Added dashboard controls to record waiver, approval, and denial in API-backed
  mode.
- Added dashboard display of review receipts and human action counts.
- Added API-backed usage ledger and billing readiness reads into dashboard
  runtime refresh.
- Added billing readiness rows to the SaaS Runtime panel.
- Added denial to `a3.commercial_api_contract.v1`, OpenAPI, and the redacted
  commercial API contract fixture.

A1/A2 calibration:

- A1 RunResult, TraceEvent, ToolCall, usage, auth, billing, and GitHub
  publisher semantics were not modified.
- A2 ReleaseGate and judge semantics remain authoritative. A3 denial records
  describe human governance only and do not rewrite score/pass/fail/failure
  classes.
- GitHub publishing remains live-capable through the existing publisher module
  but default-safe in this round: no live token was read and no live mutation was
  performed.
- Billing remains read-only in A3. No checkout, invoice, provider, quota, or
  customer payment mutation was enabled.

Verification:

```text
node --check apps\dashboard\src\app.mjs apps\dashboard\src\api-client.mjs apps\dashboard\src\components\saas-runtime-panel.mjs services\report\a3_review_workflow.mjs services\report\a3_store.mjs services\report\a3_sqlite_store.mjs services\report\a3_api_server.mjs services\report\a3_auth_rbac_boundary.mjs services\report\a3_commercial_api_contract.mjs services\report\report_builder.mjs
node --test tests\a3\*.mjs
npm.cmd run test:e2e
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git diff --check
```

Results:

- Syntax checks passed.
- Focused A3 tests: 96 passed, 0 failed.
- Full A3 Node suite: 243 passed, 0 failed.
- Playwright E2E: 9 passed, 0 failed.
- Commercial CL: passed, 0 blockers, 0 advisories.
- Hygiene CL: passed, no findings.
- `git diff --check` passed.
- `.env.local`, `node_modules/`, and Playwright transient output remain ignored.

## 2026-07-09 - Commercial Growth Round 5 Billing/Usage Readiness Contract

Continued from PR #25 / `codex/a3-commercial-growth-round4` after syncing
`origin/main` and checking open PR state. This round followed
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` and moved A3 one step closer
to a commercial SaaS billing surface without enabling real payment or cloud
mutations.

Twenty growth points considered:

1. Billing readiness API.
2. Usage ledger plan fields.
3. Usage ledger quota fields.
4. Billable meter classification.
5. Overage risk classification.
6. JSON report billing summary.
7. Markdown report billing summary.
8. A1 run/trace evidence counts in billing output.
9. A2 judge/failure evidence counts in billing output.
10. Invoice preview without real amounts.
11. Provider boundary for Stripe/WeChat Pay/Alipay/manual invoice.
12. Paid-action blocker summary from SaaS Admin.
13. Tenant-scoped billing readiness.
14. Future DB contract names for billing customers/subscriptions/invoices.
15. Event names for usage/quota/billing changes.
16. Secret-free billing report assertions.
17. Growth-Auditor Money-Grade Round 5.
18. A1 Postgres/auth/usage branch calibration.
19. A2 commercial readiness calibration.
20. PR #25 CI/readiness check continuation.

Implemented this round:

- Added `services/report/a3_billing_readiness.mjs`.
- Added `GET /api/a3/billing/readiness`.
- Added `a3.billing_readiness.v1`.
- Extended `a3.usage_ledger.v1` with:
  - `plan`
  - `quota`
  - `billable_meter`
  - `billable_meters`
  - `billable_unit_count`
  - `overage_risk`
  - `evidence_counts`
  - `billing_usage_summary`
- Added `a3.billing_usage_summary.v1` to JSON report exports.
- Added `Billing / Usage Summary` to Markdown report exports.
- Added billing readiness tests:
  - `tests/a3/a3_billing_readiness.test.mjs`
- Updated API tests:
  - `tests/a3/a3_api_server.test.mjs`
- Added implementation docs:
  - `docs/a3/p3_billing_readiness_contract_2026_07_09.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_money_grade_round5_2026_07_09.md`

Verification:

```text
node --check services\report\a3_billing_readiness.mjs
node --check services\report\a3_store.mjs
node --check services\report\a3_api_server.mjs
node --check services\report\report_builder.mjs
node --test tests\a3\a3_billing_readiness.test.mjs tests\a3\a3_api_server.test.mjs tests\a3\a3_sql_usage_report_center.test.mjs tests\a3\report_builder.test.mjs
```

Results:

- Focused billing/API/report/usage tests passed: 51 pass, 0 fail.
- Syntax checks passed for new and touched report/API modules.

A1/A2 calibration:

- A1: billing readiness treats A3 usage meters as read-only derived evidence.
  It does not claim to replace A1's future Postgres `usage_events`,
  `usage_rollups`, quota ledger, auth handles, or billing webhooks.
- A2: `judge_results`, failed cases, and failure classes are counted for billing
  visibility without changing A2 judge, score, pass/fail, release-gate, or
  failure taxonomy semantics.
- A3: owns the product/billing surface and readiness explanation, not payment
  provider mutations.

API / DB / event / artifact contract:

- API added: `GET /api/a3/billing/readiness`.
- DB contracts named for future A1/A3 handoff:
  - `usage_ledger`
  - `usage_events`
  - `usage_rollups`
  - `quota_policies`
  - `billing_customers`
  - `billing_subscriptions`
  - `billing_invoices`
  - `audit_events`
- Events named:
  - `usage.recorded`
  - `quota.exceeded`
  - `billing.subscription_changed`
  - `audit_event.created`
- Artifact impact:
  - Billing readiness is a control-plane report artifact candidate.
  - No customer invoice or payment provider artifact is generated yet.

Tenant/auth/RBAC/usage/audit:

- Tenant scope is included in billing readiness output.
- Auth/RBAC remains read-only/plan-only until hosted auth exists.
- Usage is derived from A1/A2-backed A3 meters.
- Audit states no raw private payload, customer email, token, API key, or payment
  secret is required in UI/report output.

Safety boundary:

- No `.env.local` was read.
- No Ashr API key, GitHub token, cookie, raw account value, signed URL, customer
  email, or payment secret was read or committed.
- No live Ashr API call was made.
- No live GitHub mutation beyond the already-open PR branch was made.
- No real payment provider, billing, team, API-key, Trust, object-storage, or
  cloud mutation was performed.

Remaining gaps:

- Production billing still requires A1-owned usage events, usage rollups,
  provider webhooks, hosted auth/RBAC, billing-admin approval, and invoice
  export.
- A3 billing readiness is a contract and customer-facing explanation layer; it
  is not a production billing ledger.
- A1 open branch `origin/codex/a1-local-sdk-runner` shows active Postgres/auth
  direction, but it was not merged into this A3 branch.

## 2026-07-09 - Commercial Growth Round 4 Review/Admin/Denied-State E2E

Continued from latest `origin/main` after PR #24 was merged. This round follows
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` and adds browser-level proof for
the API-backed commercial workflow edges that were still mostly API-unit-tested:
SaaS Admin request guardrails, reviewer waiver/approval receipts, and hosted
report denied-state safety.

Implemented:

- Extended `tests/e2e/a3-dashboard-api-backed.spec.ts`.
- Added SaaS Admin guardrail E2E:
  - loads `apps/dashboard/index.html?source=api-mock`
  - selects an admin action
  - confirms plan-only / no-real-cloud-write language
  - submits to `POST /api/a3/admin/actions/submit`
  - confirms the dashboard records `recorded_plan_only`
  - confirms fixture email-like values are not rendered
- Added reviewer waiver/approval E2E:
  - posts redacted waiver fixture to `POST /api/a3/review/waivers`
  - posts redacted approval fixture to `POST /api/a3/review/approvals`
  - reloads dashboard and confirms Durable Review Records, waiver/approval
    counts, valid statuses, and `hash_sealed` custody language
  - calls `GET /api/a3/review/workflow` and confirms durable storage readiness
- Added hosted report denied-state E2E:
  - creates an API-backed hosted report
  - confirms active share page renders report body and Case Evidence
  - revokes the report through `POST /api/a3/reports/:reportId/revoke`
  - confirms revoked `/r/:shareToken` returns 410 without Case Evidence,
    Expected, or Actual text
  - confirms missing share token returns 404 without report body leakage
- Added documentation:
  - `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md`
- Updated:
  - `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`
  - `docs/a3/acceptance_checklist.md`

Verification:

```text
node --check tests\e2e\a3-dashboard-api-backed.spec.ts
git diff --check
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
npm.cmd run test:e2e
node --test tests\a3\report_builder.test.mjs tests\a3\dashboard_wiring.test.mjs tests\a3\a3_commercial_growth_manifest.test.mjs tests\a3\tailwind_boundary_contract.test.mjs tests\a3\a3_wechat_mini_program_client_surface.test.mjs tests\a3\a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git check-ignore -v .env.local node_modules docs\screenshots\playwright-results
```

Results:

- API-backed Playwright E2E passed: 5 pass, 0 fail.
- Full Playwright E2E passed: 9 pass, 0 fail.
- Focused A3 Node/Tailwind/mobile/WeChat/commercial tests passed: 94 pass, 0 fail.
- Commercial CL passed with 20/20 blocker anchors, 0 blockers, and 0 advisories.
- Hygiene CL passed with no findings.
- `git diff --check` passed.
- `.env.local`, `node_modules/`, and transient Playwright results are ignored.

A1/A2 calibration:

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, grade, score, pass/fail, release-gate, and failure-taxonomy semantics
  were not changed.
- A3 review/admin/report evidence remains downstream of A1 RunResult and A2
  GradeResult evidence.

Safety boundary:

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub mutation was made.
- No real login, billing, team invite, API-key creation, Trust publishing,
  database, object-storage, or cloud mutation was made.
- No API key, token, cookie, account email, raw signed URL, or private credential
  was committed.

Current interpretation:

This round closes three important "commercial proof" holes in A3's local MVP:
admin actions are visibly guarded, reviewer exception workflows are durable
enough for audit language, and denied hosted report links fail closed without
leaking report body evidence. It still does not equal production SaaS auth/RBAC,
Postgres/RLS, billing, object storage, or live GitHub branch-protection proof.

## 2026-07-08 - API-backed release evidence summary

- Continued A3 using `docs/strategy/large-saas-a1-a2-a3-full-plan.md` as the commercial SaaS roadmap.
- Followed the team direction:
  - static -> API-backed
  - mock fixture -> DB-ready data
  - report export -> shareable hosted report
- Added A3 store loading for existing redacted release evidence fixtures.
- Added sanitized `release_evidence_summary` to API-backed dashboard payloads.
- Added release evidence API response support:
  - `GET /api/a3/releases/:releaseId/evidence-summary`
- Added immutable release evidence snapshots to shareable hosted reports.
- Added hosted report HTML rendering for Release Evidence.
- Added Report Center readiness fields for release evidence.
- Added manifest artifact id `release_evidence_summary`.
- Added Artifact Registry artifact type `release_evidence_summary`.
- Added SQL migration table contract `release_evidence_summaries`.
- Added SQLite persistence for release evidence summary rows.
- Added documentation:
  - `docs/a3/p3_api_backed_release_evidence_2026_07_08.md`
  - `docs/a3/p3_growth_auditor_round_api_backed_release_evidence_2026_07_08.md`
- Verification:
  - `node --check services/report/a3_store.mjs`
  - `node --check services/report/a3_shareable_report.mjs`
  - `node --check services/report/a3_api_server.mjs`
  - `node --check services/report/a3_sqlite_store.mjs`
  - `node --check services/report/a3_sql_migrations.mjs`
  - `node --test tests/a3/a3_store.test.mjs tests/a3/shareable_report.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/report_center_index.test.mjs tests/a3/report_center_manifest_contract.test.mjs tests/a3/artifact_registry.test.mjs`
  - `node --test --test-concurrency=1 (rg --files tests/a3 -g "*.test.mjs")`
  - `git diff --check`
  - Result: focused 20 pass / 0 fail; full A3 single-threaded 167 pass / 0 fail; `git diff --check` had no whitespace errors beyond Windows LF/CRLF warnings.
- Safety:
  - Did not read or print `.env.local`.
  - Confirmed `.env.local` is ignored.
  - Did not call live Ashr APIs.
  - Did not call live GitHub mutation APIs.
  - Did not store API keys, tokens, cookies, account emails, raw share tokens, private keys, or live signed URLs.
  - Secret scan matches were limited to intentional redaction-test strings in A3 tests.
- Remaining follow-up:
  - GitHub Check and PR comment readback are still not live-confirmed.
  - Branch protection is still not configured.
  - Release evidence summary is SQLite-backed locally, but not production Postgres-backed yet.
  - Real tenant auth/RBAC enforcement is still future A1/A3 integration work.

## 2026-07-08 - Release evidence display for publish and verification records

- Continued A3 using `docs/strategy/large-saas-a1-a2-a3-full-plan.md` as the large-SaaS roadmap.
- Merged the latest `origin/main` so the branch includes the group lead's refreshed strategy/conflict-resolution updates.
- Added release evidence summary support in `services/report/report_builder.mjs`.
- The summary converts existing redacted P3 evidence into customer-facing report fields:
  - GitHub Check publish receipt.
  - GitHub PR comment publish receipt.
  - GitHub required-check plan.
  - Audit bundle verification.
  - Signed audit archive verification.
- Added release evidence to:
  - JSON report export as `release_evidence_summary`.
  - Markdown report export as `## Release Evidence Summary`.
  - Dashboard `Release Evidence` panel.
  - Report Center summary/tile.
  - Print-ready report preview.
- Hardened dashboard wrapping for long release ids, check names, and verification badges.
- Saved screenshot evidence:
  - `docs/screenshots/a3-dashboard-release-evidence-2026-07-08.png`
- Added tests:
  - report builder summarizes release evidence and does not leak raw GitHub request details.
  - dashboard wiring includes panel ids, fixture paths, renderer, state, and export wiring.
- Verification:
  - `node --check services/report/report_builder.mjs`
  - `node --check apps/dashboard/src/app.mjs`
  - `node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs`
  - `node --test --test-concurrency=1 (rg --files tests/a3 -g "*.test.mjs")`
  - Result: focused 70 pass / 0 fail; full A3 single-threaded 167 pass / 0 fail.
- Safety:
  - Did not read or print `.env.local`.
  - Did not call live Ashr APIs.
  - Did not call live GitHub mutation APIs.
  - Did not store secrets, tokens, cookies, emails, private keys, live signed URLs, or raw account values.
- Remaining follow-up:
  - API-backed dashboard snapshots do not yet serve release evidence from durable DB/API state.
  - Hosted report pages should surface this same release evidence summary server-side.
  - Real GitHub Check/PR comment publishing still requires explicit maintainer-approved live integration, not dry-run receipts.

## 2026-07-08 - Signed audit archive manifest and verifier

- Continued A3 using `docs/strategy/large-saas-a1-a2-a3-full-plan.md` as the large-SaaS roadmap.
- Added signed audit archive manifest support in `services/report/a3_audit_archive.mjs`.
- Added archive-level verification for:
  - archive root hash
  - Ed25519 signature
  - bundle index entry hash
  - generated artifact entry hashes
  - missing-entry detection
  - safe workspace-relative paths
- Saved redacted archive fixtures:
  - `fixtures/a3/p3/a3_audit_archive_manifest.redacted.json`
  - `fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json`
- Added archive tests in `tests/a3/a3_audit_archive.test.mjs`.
- Updated export-firewall scan coverage so the new archive manifest and verification fixture are checked for secrets and local account paths.
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md`
- Verification:
  - `node --check services/report/a3_audit_archive.mjs`
  - `node --test tests/a3/a3_audit_archive.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/export_firewall_generated_artifacts.test.mjs`
  - `node --test (rg --files tests/a3 -g "*.test.mjs")`
  - Result: focused 27 pass / 0 fail; full A3 165 pass / 0 fail.
- Safety:
  - Did not read or print `.env.local`.
  - Did not call live Ashr APIs.
  - Did not store private signing keys.
  - Did not commit secrets, tokens, cookies, emails, local absolute paths, or live signed URLs.
- Remaining follow-up:
  - Binary zip/tar packaging around the signed archive manifest is still future work.
  - Dashboard/report display of GitHub publish evidence and archive/bundle verification remains the next high-value A3 UI round.

## 2026-07-08 - GitHub publish evidence audit bundle sealing

- Synced remote state and confirmed the group lead had refreshed `origin/main` after merge-conflict resolution.
- Created the new work from the latest `origin/main` baseline instead of forcing the older A3 branch over main.
- Added optional Gate CLI evidence inputs for:
  - GitHub Check publish receipt.
  - GitHub PR comment publish receipt.
  - GitHub required-check plan.
- Kept these artifacts downstream of A3 delivery evidence:
  - They are not A1 run inputs.
  - They are not A2 judge inputs.
  - They are external GitHub publish evidence read by A3 for audit/report custody.
- Updated the generated artifact manifest and audit bundle flow so the three GitHub evidence files can be hash-sealed and verified.
- Refreshed stale committed Gate CLI/audit-bundle fixtures after main's conflict-resolution artifact refresh changed underlying file hashes.
- Verification:
  - `node --check services/report/a3_gate_cli.mjs`
  - `node --test tests/a3/a3_gate_cli.test.mjs`
  - Result: 21 pass, 0 fail.
- Safety:
  - Did not read or print `.env.local`.
  - Did not call live Ashr APIs.
  - Did not commit secrets, tokens, cookies, account data, emails, or live signed URLs.

## 2026-07-04

### Safety and Git state

- Ran `git fetch origin`; GitHub connection reset during the first check.
- Confirmed current branch: `codex/a3-p3-ashr-calibration`.
- Confirmed local HEAD equals the current local `origin/main`.
- Confirmed merged main includes A1, A2, and A3 merge commits.
- Confirmed `.env.local` exists.
- Confirmed `.env.local` is ignored by `.git/info/exclude`.
- Did not print or read the key value.

### Local contract reconnaissance

- Read A3 integration and fixture contracts:
  - `docs/a3/a3_integration_plan.md`
  - `docs/a3/mock_fixture_contract.md`
  - `services/report/report_builder.mjs`
- Read A1/A2 handoff:
  - `docs/a2/a1_a3_handoff.md`
- Read A1 schemas:
  - `docs/a1/schemas/run_result.schema.json`
  - `docs/a1/schemas/case_result.schema.json`
  - `docs/a1/schemas/agent_turn.schema.json`
  - `docs/a1/schemas/trace_event.schema.json`
  - `docs/a1/schemas/observation.schema.json`
- Read A2 grading schema:
  - `services/judge/schemas.py`
- Read A3 fixtures:
  - `fixtures/a3/mock_run_results.json`
  - `fixtures/a3/mock_grade_results.json`

### Real Ashr SDK reconnaissance

- Inspected local A1 PyPI artifact `ashr_labs-0.3.1`.
- Found `AshrLabsClient`, `RunBuilder`, `TestBuilder`, `Trace`, and typed models.
- Found production base URL in SDK artifact: `https://api.ashr.io/testing-platform-api`.
- Found SDK environment variable name: `ASHR_LABS_API_KEY`.
- Found user-provided project convention also mentions `ASHR_API_KEY`; P3 smoke code should support both without printing values.

### Current interpretation

- Real Ashr likely stores testing data as `Dataset` plus `Run`.
- A real `Run` has a nested `result`.
- A run result built by the SDK contains `tests[]`, `action_results[]`, and `aggregate_metrics`.
- Expected vs actual is represented by action results:
  - `expected` / `actual` for tool calls
  - `expected_response` / `actual_response` for text responses
- Trace-like production observability is a separate API concept with `Trace` and `observations[]`.

### Ashr smoke test results

- Safely loaded `.env.local` without printing the key.
- Used `ASHR_LABS_API_KEY` in the current process for the SDK.
- Imported the SDK from `docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl`.
- Ran read-only calls:
  - `init()`: success.
  - `health_check()`: success.
  - `list_agents()`: success, empty list.
  - `list_datasets(limit=5, include_signed_urls=False)`: success.
  - `list_runs(limit=5)`: success.
  - `list_requests(limit=5)`: success.
  - `list_observability_traces(limit=5)`: failed; account feature flag `observability` is false.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_auth_check.redacted.json`
  - `fixtures/a3/p3/ashr_field_sample.redacted.json`

### Mapper implementation

- Added `services/report/p3_ashr_mapper.mjs`.
- Added `tests/a3/p3_ashr_mapper.test.mjs`.
- The mapper converts `runs[].result.tests[].action_results[]` into:
  - A3 `runFixture.runs[].cases[]`
  - A3 `gradeFixture.grade_results[]`
  - expected vs actual panels
  - A1-like observations and trace events
  - derived failure classes for dashboard clustering

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 4 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 4 tests passed.
- Confirmed `.env.local` remains ignored and untracked.

### Current blockers and assumptions

- GitHub `fetch` hit a network reset earlier, but local HEAD matches local `origin/main`.
- Observability API is not available for this account because `features.observability` is false.
- Native backend failure-class fields were not visible in the current successful run sample.
- P3 mapper currently derives `primary_failure_class` from `match_status`, tool-call comparison, and response divergence.

### Next top 3

1. Get or create one minimal failing run so P3 can verify native failure fields, if any.
2. Decide whether A3 should display `semantic_similarity` as score or wait for a stronger server grade.
3. Join `list_runs()` data with `list_datasets()` data so case titles can come from `dataset_source.runs.*.title`.

### Completed commands

- `git fetch origin`
- `git status -sb`
- `git branch --show-current`
- `git rev-list --left-right --count HEAD...origin/main`
- `git check-ignore -v .env.local`
- `rg --files docs/a1 docs/a2 docs/a3 packages/sdk packages/scenarios services/runner services/judge services/report fixtures`
- `tar -tf docs/a1/_pypi_artifacts/ashr_labs-0.3.1.tar.gz`
- `python -m zipfile -l docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl`
- Read-only Ashr SDK smoke test via `AshrLabsClient`.
- `node --test tests/a3/report_builder.test.mjs`
- `node --test tests/a3/p3_ashr_mapper.test.mjs`

## 2026-07-04 - Product Console / Media Evidence iteration

### Baseline and peer state

- Current branch: `codex/a3-p3-ashr-calibration`.
- `.env.local` is ignored by `.git/info/exclude`.
- `gh pr list --state all --limit 20` showed:
  - PR #5 `P3 Ashr calibration for A3 dashboard`: merged.
  - PR #6 `A1 local SDK runner, cloud API, and TS quickstart`: merged.
  - PR #7 `A1 queue worker and TS API client parity`: open draft.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` failed with a network reset. This is recorded as merge risk because local `origin/main` may be stale even though GitHub API was reachable.

### ROI decision

Selected `Media Evidence` for this round.

Reason:

- Real Ashr samples already exposed media fields that A3 could not display.
- Media evidence has high demo value because non-developers can understand audio/file/VM evidence faster than raw JSON.
- Supporting media fields reduces integration risk for future real Ashr data.

Backlog:

- Trace tree + tool-call diff + judge drilldown.
- Report center with more formal export workflow.
- Authenticated official Ashr dashboard observation after manual login.

### Real Ashr media calibration

Read-only Ashr API/SDK evidence from this round is saved in sanitized files:

- `fixtures/a3/p3/ashr_media_field_sample.redacted.json`
- `fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`

Confirmed fields:

- `dataset_source.runs.*.actions[]`
- `action_type`: `text`, `file`, `audio`
- `action_tags`
- `output_path`
- `expected_response.tool_calls`
- `run.result.cases[]`
- `case.metadata.action_type`
- `case.metadata.audio_tags`
- `case.metadata.intent_tags`
- `case.observations[].vm_stream`
- `grade.expected`
- `grade.actual`
- `grade.metrics`
- `grade.passed`
- `grade.score`

### Official frontend observation

- Public site observed at `https://ashr.io/`.
- Public product concepts seen: datasets, test details, explore, prompts, SDK, full test timelines, expected vs actual, usage scaling.
- Lab frontend opened at `https://lab.ashr.io/` and landed on sign-in/onboarding.
- No login, form submission, workspace creation, or plan selection was performed.
- Notes saved in `docs/a3/p3_official_frontend_notes.md`.

### Implemented

- Extended `services/report/p3_ashr_mapper.mjs` to support:
  - `run.result.tests[].action_results[]`
  - `run.result.cases[]`
  - media evidence summary
  - audio/file/image/video action types
  - action tags and output paths
  - VM stream summaries
  - media timeline events such as `media.vm_stream`
- Extended `services/report/report_builder.mjs` to include media evidence counts in summaries and media fields in JSON/CSV exports.
- Extended `tests/a3/p3_ashr_mapper.test.mjs` with a real redacted `result.cases[]` media sample test.
- Updated `apps/dashboard/index.html` into a product-console style UI:
  - data source switcher
  - product console overview
  - Usage / Quota known-gap panel
  - Requests / datasets / runs object summary
  - Media Evidence panel in Case Detail
  - P3 media sample view powered by the mapper

### Screenshots

- `docs/screenshots/a3-p3-product-console-media-overview.png`
- `docs/screenshots/a3-p3-product-console-media-mobile.png`

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 4 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 5 tests passed.
- Browser smoke: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Browser checks:
  - Page title rendered `A3 Product Console`.
  - Data source rendered `P3 redacted Ashr media sample`.
  - Case rows: 3.
  - Media Evidence metric: 3.
  - Media panel showed `audio` and `vm_stream`.
  - Console logs: no warnings/errors.
  - Mobile viewport width 390 had no horizontal overflow.

### Next top 3

1. Add a trace/tool-call diff panel for expected vs actual tool-call comparison.
2. Add a report-center page with saved report history and PDF-ready layout.
3. After a teammate logs into Ashr Lab, observe authenticated requests/datasets/runs/detail pages and update `p3_official_frontend_notes.md`.

## 2026-07-04 - Tool-call diff follow-up

### Goal

Continue the next A3 backlog item after media evidence: make expected vs actual tool-call failures readable without manual JSON comparison.

### Implemented

- Added `buildToolCallDiffs(caseResult)` in `services/report/report_builder.mjs`.
- Added normalized tool-call comparison statuses:
  - `match`
  - `missing_required_tool`
  - `unexpected_tool_call`
  - `wrong_tool`
  - `wrong_arguments`
- Added `tool_call_diffs` to JSON export output.
- Added dashboard `Tool Call Diff` panel in Case Detail.
- Added `docs/a3/p3_tool_call_diff.md`.
- Added screenshot `docs/screenshots/a3-p3-tool-call-diff.png`.

### Verification

- `node --test tests/a3/report_builder.test.mjs`: 5 tests passed.
- `node --test tests/a3/p3_ashr_mapper.test.mjs`: 5 tests passed.
- Browser smoke at `http://127.0.0.1:5173/apps/dashboard/index.html`.
- Confirmed missing tool case renders `missing_required_tool`.
- Confirmed wrong argument case renders `wrong_arguments`.
- Confirmed no horizontal overflow in the desktop browser check.

### Next top 3

1. Add field-level argument highlighting inside the tool-call diff.
2. Add report-center page with saved report history and PDF-ready layout.
3. Observe authenticated Ashr Lab after manual login and update official frontend notes.

## 2026-07-06 - Authenticated Lab frontend observation

### Goal

Continue P3 frontend/product-logic calibration after the user successfully logged into a browser session. Confirm real Lab navigation and UI workflow without saving secrets, cookies, screenshots, or account-specific values.

### Browser/login path

- Normal Edge and normal Chrome were visible but could not be inspected because the automation safety layer could not verify the current browser URL.
- Codex in-app browser could open Ashr, but Google login returned `400 Bad Request`.
- Launched an isolated Chrome profile with local CDP debugging on port `9222`.
- The user manually logged into Ashr in that isolated Chrome profile.
- Codex connected read-only through local CDP after login.

### Confirmed authenticated Lab pages

- `?tab=analysis`: Datasets page with search, Type/Agent/Creator/Status/Runs/time filters, pinned-only, sort, group, and `New dataset`.
- `?tab=agents`: Agents page; current account showed `No agents yet`.
- `?tab=folders`: Folders page with search and `New folder`; current account showed no folders.
- `?tab=analytics`: Analytics page with agents, datasets, graded runs, overall pass rate, run volume, pass-rate trend, runs by agent, and pass rate by agent.
- `?tab=usage`: Usage page with Images, Audio, and Files quota counters.
- `?tab=trust`: Trust page with public trust/certificate preview and frozen-metrics language.
- `?tab=api-keys`: API Keys page with create/setup instructions; no secret values were saved.
- `?tab=team`: Team management page; account-specific values were not saved.
- Settings menu: Theme and Low Power.
- New Dataset modal: 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.

### Documentation updated

- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_a3_mvp_recommendations.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/a3/acceptance_checklist.md`

### Safety

- Did not print, document, or commit the Ashr key.
- Did not read browser cookies or tokens.
- Did not save authenticated screenshots.
- Did not submit forms, create datasets, create keys, invite users, delete data, or change settings.
- Account email and user-specific values were redacted or omitted from docs.

### Verification

- Ran `node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs`.
- Result: 30 tests passed, 0 failed.
- Ran `git diff --check`; only existing LF-to-CRLF warnings were reported.
- Confirmed `.env.local` is ignored by `.gitignore`.
- Ran targeted scans for emails, user handles, real API-key assignments, bearer tokens, and cookie/token assignments in A3-owned files.
- New authenticated-frontend docs did not contain the account email, username, key, cookie, or token values.
- A broader scan still matches an old intentional fake fixture string shaped like `ashr_live_...`; it is synthetic test content, not a real Ashr secret.

### Remaining unknowns

- Populated dataset detail, run detail, case detail, expected-vs-actual, and trace timeline were not visible because the observed account had no UI-visible datasets/runs.
- Native backend failure-class evidence was checked later with a real failed run; frontend failure labels still require a UI-visible populated run.
- Signed media URL behavior is still confirmed for one dataset action field name only, not full audio/image/video UI rendering.

### Next top 3

1. Get one UI-visible populated run and observe the populated run/case detail frontend.
2. Add a request provenance panel to A3 using confirmed request API fields.
3. Decide whether to keep Trust/Usage as documentation-only product inspiration or add a minimal local mock panel later.

## 2026-07-06 - Request Provenance dashboard closeout

### Goal

Continue the P3/A3 product-logic goal by turning confirmed real Ashr request fields into a visible dashboard/report feature.

### Implemented

- Added `summarizeRequestProvenance()` in `services/report/report_builder.mjs`.
- The summary supports direct request samples, `sample`, `get_request`, `list_requests`, and `calls.*.sample` shapes.
- Preserves only safe request metadata:
  - request status
  - actual/estimated duration
  - accepted input types
  - generation output flags
  - test strategy if not redacted
  - tool count
  - failure-present flag
- Added `request_provenance` to JSON report export.
- Added `Request Provenance` section to Markdown export.
- Added dashboard Request Provenance panel for the P3 media source.
- Dashboard now loads `fixtures/a3/p3/ashr_request_detail_sample.redacted.json` when `source=p3-media`.
- Added report-builder and dashboard wiring tests.
- Updated:
  - `docs/a3/acceptance_checklist.md`
  - `docs/a3/a3_dashboard_polish.md`
  - `docs/a3/p3_a3_mvp_recommendations.md`

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 32
pass 32
fail 0
```

Browser smoke:

- Started local static server at `http://127.0.0.1:5173`.
- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Request Provenance rendered:
  - status `failed`
  - accepted inputs `audio, file, image, text`
  - generation outputs `generate_audio, generate_files, generate_images`
  - tool count `1`
  - redacted strategy
  - failure noted `yes`
- Browser console warnings/errors: none.
- Screenshot saved: `docs/screenshots/a3-dashboard-request-provenance.png`.

### Safety

- No live Ashr API calls.
- No `.env.local` reads or writes.
- No key, cookie, token, or account information added.
- Uses only committed redacted P3 request fixture data.

### Next top 3

1. Get one UI-visible populated run to verify frontend run/case detail and failure labels.
2. Observe populated run detail, case detail, trace/timeline, and expected-vs-actual pages.
3. Confirm signed media URL behavior across audio, image, file, and video before rendering live links.

## 2026-07-06 - Failed run probe and Chrome frontend recheck

### Goal

Continue real Ashr API + frontend product calibration after the user confirmed Chrome login worked. Close the highest-value remaining evidence gap: use a real failed run, if present, to verify failure fields without mutating Ashr data.

### Safety

- Confirmed `.env.local` exists and is ignored by `.gitignore`.
- Loaded `ASHR_API_KEY` into the process only for read-only probe commands.
- Did not print the key.
- Did not read or save cookies, browser storage, tokens, or raw account details.
- Did not submit forms, create datasets, create keys, invite users, or change settings.
- Did not save authenticated frontend screenshots.

### Read-only Ashr API calls

Saved new sanitized fixtures:

- `fixtures/a3/p3/ashr_failed_run_probe.redacted.json`
- `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`
- `fixtures/a3/p3/ashr_request_probe.redacted.json`
- `fixtures/a3/p3/ashr_failed_request_detail.redacted.json`

Confirmed fields from the failed run:

- `run.result.status == "failed"`
- aggregate passed/failed counts
- `run.result.cases[]`
- `cases[].status == "failed"`
- `cases[].grade.label == "failed"`
- `cases[].grade.passed == false`
- `cases[].grade.score`
- `cases[].grade.reason`
- `cases[].grade.metrics.text_match`
- `cases[].grade.metrics.tool_match`
- `cases[].observations[]`

Important conclusion:

- The real failed run did not expose a named backend `failure_class` field.
- A3 should continue deriving failure clusters from confirmed fields such as `grade.metrics`, expected/actual, and tool-call evidence.
- In this sample, A3 mapped the failed cases into `bad_final_response` and `missing_required_tool`.

Confirmed fields from the failed request:

- `request.request_status == "failed"`
- `request.request._failure` exists
- `request.request._failure.error` exists after redaction

A3 should treat failed requests as request-provenance evidence, not as case-level judge results.

### Authenticated frontend recheck

Connected to the user's logged-in Chrome through local CDP and observed Lab pages read-only:

- `?tab=analysis`: Datasets page loaded successfully, but showed 0 UI-visible datasets and `No datasets match your filters.`
- `?tab=analytics`: loaded successfully, but showed 0 agents, 0 datasets, 0 graded runs, and not enough data.
- `?tab=trust`: loaded successfully and showed the run-tests-first empty state.
- `?tab=agents`: loaded successfully and showed no agents.
- `?tab=folders`: loaded successfully and showed no folders.
- `?tab=usage`, `?tab=api-keys`, and `?tab=team` were observed earlier in the same authenticated session; no key values or account-specific values were saved.

Frontend conclusion:

- The API has usable run/request evidence, including a failed run.
- The Lab frontend account still has no UI-visible populated dataset/run to open.
- Populated run detail, case detail, expected-vs-actual, and trace/timeline frontend pages remain unobserved.

### Mapper update

- Updated `services/report/p3_ashr_mapper.mjs` so `extractAshrRuns()` can consume API probe wrapper shapes such as `response.run` and `response.runs`.
- Added a mapper test using `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`.
- Confirmed the failed-run fixture maps to one A3 run and three failed A3 cases.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 33
pass 33
fail 0
```

### Next top 3

1. Find a UI-visible populated Lab run or dataset so A3 can observe real frontend run/case detail pages.
2. Confirm signed media URL behavior across audio, image, file, and video before rendering live signed links.
3. Keep native failure class as derived in A3 unless a future Ashr sample exposes a named backend `failure_class`.

## 2026-07-06 - API/frontend visibility comparison

### Goal

Clarify why the Lab frontend still shows empty states even though real API probes can return datasets, runs, and requests.

### Read-only API probes

Saved sanitized fixtures:

- `fixtures/a3/p3/ashr_dataset_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_run_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_request_probe_after_frontend_empty.redacted.json`
- `fixtures/a3/p3/ashr_failed_run_dataset_detail.redacted.json`

Confirmed API object counts:

- datasets: 3
- runs: 2
- requests: 5

Confirmed API fields:

- dataset fields: `id`, `name`, `dataset_type`, `dataset_source`, `request_id`, `run_count`, `created_at`
- run fields: `id`, `dataset`, `result.status`, `result.aggregate_metrics`, `result.cases[]` or `result.tests[]`
- request fields: `id`, `request_name`, `request_status`, `request`, `actual_duration_s`, `estimated_duration_s`
- dataset detail fields: `dataset.dataset_source.dataset_type`, `dataset.dataset_source.runs`, `dataset.dataset_source.total_runs`

### Frontend comparison

Authenticated Chrome/CDP observation still showed:

- Datasets page: 0 UI-visible datasets / no matching datasets.
- Analytics page: 0 agents, 0 datasets, 0 graded runs.
- Trust page: run-tests-first empty state.

### Interpretation

- API data exists and remains usable for A3 calibration.
- The frontend is reachable and authenticated, but does not show those API objects in the current visible pages.
- The cause is not confirmed; possible explanations include filters, workspace visibility, repo scoping, or product separation between API calibration objects and visible Lab artifacts.
- A3 should not guess hidden frontend routes. It should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run is available.

### Documentation

- Added `docs/a3/p3_api_frontend_visibility_gap.md`.
- Linked the visibility gap from `docs/a3/p3_frontend_page_map.md` and `docs/a3/acceptance_checklist.md`.

### Next top 3

1. Ask for or create, with explicit approval only, one UI-visible populated Lab run if frontend detail pages must be verified.
2. Keep A3 populated run/case behavior backed by sanitized API fixtures.
3. Confirm signed media URL behavior per media type before rendering live media links.

## 2026-07-06 - Frontend session-expired network probe

### Goal

Check whether the currently connected Chrome session can still fetch Lab data from the frontend.

### Observation

Read-only Chrome/CDP observation found:

- The Lab page now shows sign-in UI.
- Visible text includes `Your session has expired. Please sign in again.`
- Frontend POST requests to `api.ashr.io/testing-platform-api` returned `401`.

Saved sanitized fixture:

- `fixtures/a3/p3/ashr_frontend_session_expired_network.redacted.json`

### Safety

- Did not save request headers.
- Did not save cookies.
- Did not save tokens.
- Did not save response bodies.
- Did not save screenshots.
- Did not submit sign-in forms.

### Interpretation

- The browser frontend session has expired and needs fresh manual login before further frontend detail observation.
- This does not invalidate local API probes through `.env.local`; those are a separate credential path.
- A3 should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run can be observed in a fresh logged-in frontend session.

### Next top 3

1. Ask the user to sign in again only when we are ready to observe frontend run/case detail pages.
2. Continue treating redacted API fixtures as authoritative for populated A3 mapping.
3. Avoid guessing hidden frontend routes while the frontend session is expired.

## 2026-07-06 - Signed media URL coverage audit

### Goal

Turn the remaining signed-media uncertainty into a precise evidence statement: which media types have confirmed `signed_url` fields, and whether A3 can safely render live media links.

### Method

Scanned the redacted local P3 fixtures under `fixtures/a3/p3` for:

- `signed_url`
- `output_path`
- `action_type`
- media request flags such as `generate_audio`, `generate_files`, `generate_images`, and `generate_videos`

No raw URL values were printed or saved.

### Evidence saved

- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`
- `docs/a3/p3_signed_media_url_coverage.md`

### Findings

- 18 redacted P3 fixture files scanned.
- 2 `signed_url` keys found.
- Both `signed_url` keys were nearest to file-like actions.
- 0 audio `signed_url` samples found.
- 0 image `signed_url` samples found.
- 0 video `signed_url` samples found.
- `output_path` evidence exists for file and audio.
- image/video appear in accepted-input and generation flags, but not as concrete signed URL samples.

### A3 decision

- Preserve `signed_url` metadata only in redacted form.
- Do not render live signed links yet.
- Do not infer audio/image/video signed URL behavior from file-only evidence.
- Keep Media Evidence focused on media type, action tags, output path presence, audio tags, VM stream evidence, and known gaps.

### Next top 3

1. Get sanitized audio signed URL evidence.
2. Get sanitized image/video signed URL evidence if those features are in scope.
3. Confirm signed URL expiry/access behavior before any live link rendering.

## 2026-07-06 - Chinese P3/A3 handoff summary

### Goal

Create a beginner-friendly handoff note that explains current A3/P3 status, evidence, remaining external gaps, and what to say if the group lead asks.

### Added

- `docs/a3/p3_status_handoff_cn.md`

### Content

The handoff explains:

- what the Ashr clone project is doing
- what A3 owns
- which dashboard/report pieces are already done
- which real Ashr API fields were confirmed
- what the failed-run probe proved
- why A3 derives failure class
- what was observed in the real Ashr frontend
- why the frontend still needs fresh login and a UI-visible populated run
- why live signed media links should not be rendered yet
- what remains externally blocked

### Decision

Use this as the short human-facing handoff for student/team communication. Keep the more detailed technical evidence in the existing P3 mapping, visibility-gap, signed-media, and worklog docs.

## 2026-07-06 - Frontend relogin observation checklist

### Goal

Prepare the next frontend calibration pass so it can start safely after the user manually logs into Ashr Lab again.

### Added

- `docs/a3/p3_frontend_relogin_observation_checklist.md`

### Checklist scope

The checklist defines:

- preconditions before starting observation
- secret-safety rules
- priority order for Datasets, Dataset detail, Run detail, Case detail, Trace, Expected vs Actual, Media Evidence, Report/Trust
- evidence files to update
- stop conditions such as `401`, captcha, password prompt, or visible secrets
- minimum success standard for the next frontend pass

### Decision

Do not attempt more frontend observation while the browser session is expired. Use this checklist after fresh manual login and only proceed read-only.

## 2026-07-06 - Frontend relogin top-level confirmation

### Goal

Re-check the real Ashr Lab frontend after the user manually logged in again, and confirm whether deeper run/case UI calibration can continue.

### Method

- Connected read-only to the user's Chrome through the local CDP debugging port.
- Did not save cookies, headers, tokens, response bodies, screenshots, email, or account-specific values.
- Opened only safe top-level Lab tabs: Usage, Datasets, Analytics, Agents, Folders, and Trust.
- Did not open API key values, invite/team actions, create flows, or submit forms.

### Evidence saved

- `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`

### Findings

- Fresh frontend login is valid.
- Frontend Lab requests returned `200`, not the earlier `401`.
- `?tab=usage` shows quota modules for Images, Audio, and Files.
- `?tab=analysis` loads the Datasets console with filters for Type, Agent, Creator, Status, Runs, time, Sort, and Group.
- After a longer wait, Datasets showed `0` and `No datasets match your filters.`
- `?tab=analytics` shows the real product analytics modules: Agents, Datasets, Graded runs, Overall pass rate, Run volume, Pass rate over time, Runs by agent, and Pass rate by agent.
- Analytics still showed 0 agents, 0 datasets, and 0 graded runs.
- Agents and Folders also showed empty states.
- Trust showed the public trust/certificate concept, but still said tests must be run before anything can be certified.

### Conclusion

This pass removes the stale blocker of "frontend session expired." The current blocker is now narrower: the authenticated frontend account has no UI-visible populated dataset/run, so run detail, case detail, expected-vs-actual, trace/timeline, and native frontend failure labels still cannot be observed directly.

### A3 decision

- Keep using sanitized real API fixtures as the evidence source for populated run/case/trace behavior.
- Use the real frontend only for confirmed product-console navigation, empty states, analytics concepts, usage/quota concepts, and trust/report inspiration.
- Do not invent hidden frontend detail routes or native failure labels.

## 2026-07-06 - Media usage/quota calibration and A3 panel

### Goal

Continue A3 Product Console / UI Workflow Commercial Growth with the highest-ROI media-focused enhancement: connect real Ashr media/usage evidence to the dashboard and report workflow.

### ROI decision

Selected: Usage / Quota + Media calibration panel/report enhancement.

Why:

- It directly addresses the media direction requested for the next iteration.
- The official frontend has visible Images, Audio, and Files quota modules.
- The frontend revealed concrete usage functions: `get_usage` and `billing_get_status`.
- Direct API-key calls to those functions returned OAuth-only 403 responses, which is important product evidence for A3.
- The implementation is small and stays inside A3-owned dirs.

Backlog candidates:

- Full media preview/link rendering: still blocked because audio/image/video signed URL behavior is not confirmed.
- Full frontend run/case detail replication: still blocked by missing UI-visible populated run.
- Trust publishing flow: product inspiration only, not student MVP scope.

### Read-only Ashr API calls

L0 read-only calls completed:

- `init`
- `list_datasets`
- signed-url `list_datasets` probe with `include_signed_urls=true`
- `list_requests`
- `list_runs`
- 3 `get_dataset`
- 5 `get_request`
- 2 `get_run`
- `get_usage`
- `billing_get_status`

Results:

- Datasets observed: 3
- Requests observed: 5
- Runs observed: 2
- `signed_url` paths observed: 2
- `get_usage`: 403, OAuth-only for API key
- `billing_get_status`: 403, OAuth-only for API key

Saved redacted evidence:

- `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`
- `fixtures/a3/p3/ashr_media_run_case_sample.redacted.json`
- `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`

### Official frontend observation

Authenticated Chrome/CDP observation confirmed:

- Usage page path: `/?tab=usage`
- Visible media quota channels: Images, Audio, Files
- Frontend Usage functions: `get_usage`, `billing_get_status`
- Datasets functions: `list_datasets`, `list_requests`, `list_folder_memberships`
- Analytics functions: `list_agents`, `list_datasets`
- Trust functions: `get_trust_certificate_status`, `preview_trust_certificate`

Saved redacted frontend evidence:

- `fixtures/a3/p3/ashr_frontend_usage_workflow.redacted.json`
- `docs/a3/p3_media_frontend_notes.md`

### Implemented

- Added `summarizeUsageQuota()` in `services/report/report_builder.mjs`.
- JSON export now includes `usage_quota`.
- Markdown export now includes a `Usage / Quota` section.
- Dashboard Usage / Quota panel now shows:
  - media channels: audio, files, images
  - frontend functions: `billing_get_status`, `get_usage`
  - API-key access: no
  - OAuth-gated functions
  - A3 decision to show frontend-confirmed quota state
- Print/PDF report preview now includes Usage / Quota.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 35
pass 35
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Usage / Quota text renders.
- Confirmed no horizontal overflow.
- Saved screenshot: `docs/screenshots/a3-dashboard-usage-quota-media.png`.

### Safety

- Did not print or save the real API key.
- Did not save browser token values, headers, cookies, response bodies, emails, or account values.
- Did not create, mutate, delete, publish, invite, or generate real Ashr objects.
- Signed URL values are represented only as `[REDACTED_SIGNED_URL]`.

### Next top 3

1. Get one UI-visible populated hosted run to observe real run/case/trace/media preview pages.
2. Get sanitized audio/image/video signed URL samples before any live link rendering.
3. If approved, design a minimal L1 dry-run plan for one tiny frontend-visible demo request/run.

## 2026-07-06 - Official dashboard gap comparison

### Goal

Use already collected official Ashr frontend/API calibration evidence to compare A3 with the real product and improve the local A3 MVP in the safest area.

### Product comparison

A3 already matches the core evaluation-review loop:

- runs
- case detail
- expected vs actual
- trace timeline
- tool-call diff
- failure clusters
- media evidence
- report export

The official product has broader cloud-console areas:

- Datasets
- Agents
- Folders
- Analytics
- Usage
- Trust
- API Keys
- Team

The student MVP should copy the navigation and evidence-review ideas, but should not copy account administration, API-key management, billing, OAuth login, team invites, hosted mutation flows, or public trust publishing.

### Implemented

- Added `docs/a3/p3_official_dashboard_gap_analysis.md`.
- Added `summarizeOfficialAshrGap()` in `services/report/report_builder.mjs`.
- Added dashboard panel `Official Ashr Gap`.
- Added report JSON field `official_ashr_gap`.
- Added Markdown/print report section `Official Ashr Gap`.
- Added tests for dashboard wiring and report-builder output.

### Safety

- No new real Ashr API calls were required.
- No browser cookies, tokens, headers, emails, account values, keys, or signed URLs were saved.
- No real Ashr objects were created, deleted, published, invited, or mutated.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 37
pass 37
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed the `Official Ashr Gap` dashboard panel renders.
- Confirmed the print/PDF report preview includes `Official Ashr Gap`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-gap.png`.

## 2026-07-06 - Media readiness and cloud console polish

### Goal

Continue the P3/A3 product-console iteration by improving media handling and safely mimicking official Ashr cloud/admin surfaces.

### Implemented

- Added product-level `Media Readiness`.
- Added signed URL safety summary using redacted coverage evidence.
- Added `Cloud Console Shell` as a read-only status map for:
  - auth session
  - workspace / tenant
  - datasets / runs
  - usage / billing
  - API keys
  - team
  - trust / report
  - cloud mutations
- Added UI polish:
  - sidebar brand mark
  - status chips
  - Media and Cloud Shell nav links
  - clearer badges and panel states
- Added report fields:
  - `media_readiness`
  - `cloud_console_shell`
- Added Markdown/print report sections:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added documentation: `docs/a3/p3_media_cloud_console_polish.md`.

### Safety boundary

The dashboard mimics the product shape only. It does not implement:

- real login/OAuth
- API-key management
- team invites
- billing changes
- public trust publishing
- create/delete/publish cloud mutations
- live signed URL rendering

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 39
pass 39
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed `Media Readiness` renders with media channel and signed URL safety state.
- Confirmed `Cloud Console Shell` renders with auth/workspace/API-key/team/billing/trust/cloud-mutation boundaries.
- Confirmed print/PDF report preview includes both new sections.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-cloud-polish.png`
  - `docs/screenshots/a3-dashboard-cloud-shell.png`

## 2026-07-06 - Media matrix and cloud action guardrails

### Goal

Make the media/cloud polish more explicit for reviewers by showing exact per-channel media decisions and exact cloud/admin action boundaries.

### Implemented

- Media Readiness now includes `channel_matrix`.
- Each media channel has:
  - usage observation
  - case evidence count
  - output path status
  - signed URL status
  - preview policy
  - decision text
- Cloud Console Shell now includes `actions`.
- Actions mark safe local flows as enabled and sensitive official-cloud flows as disabled.
- Dashboard renders:
  - `media-channel-matrix`
  - `cloud-action-list`
- Print/PDF report includes both tables.
- Markdown report includes `Cloud Action Guardrails`.

### Safety

This still does not add real login, API-key management, team invites, billing mutations, Trust publishing, hosted dataset creation, cloud deletion, or live signed URL rendering.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 39
pass 39
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed Media Channel Matrix renders 5 rows.
- Confirmed Cloud Action Guardrails renders 15 rows.
- Confirmed print/PDF report includes cloud guardrail actions.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-matrix.png`
  - `docs/screenshots/a3-dashboard-cloud-guardrails.png`

## 2026-07-06 - Chrome/CDP official agent wizard crawl

### Goal

Recover from the in-app-browser Google login stall, use an authenticated normal Chrome session to crawl the real Ashr Lab UI, and prepare a minimal official demo agent/dataset draft for A3 calibration.

### What happened

- The Codex in-app browser repeatedly stalled on Google's `gis_transform` page during login.
- A normal Chrome profile was launched with local CDP debugging and the user manually logged into Ashr Lab.
- The authenticated page was confirmed at `https://lab.ashr.io/?tab=analysis`.
- Top-level Lab pages were crawled through Chrome/CDP:
  - Datasets
  - Agents
  - Folders
  - Analytics
  - Usage
  - Trust
  - API Keys
  - Team
- Account-specific values were redacted; no cookies, tokens, API keys, or raw emails were saved.

### Official wizard findings

- The official `New dataset` flow has 8 steps:
  - Basic Info
  - Agent
  - Inputs
  - Tools
  - Context
  - Test Config
  - Behaviors
  - Review
- The wizard supports media input types:
  - text
  - audio
  - conversation
  - file
  - image
  - video
  - website simulation
  - custom schema
- The wizard supports tool definitions with:
  - tool name
  - tool description
  - parameter name
  - parameter type
  - parameter description
  - optional marker
- The wizard supports behavior/rubric-style constraints:
  - tool order
  - response requirements
  - success criteria

### Prepared draft

Filled an official wizard draft to the Review step:

- Dataset: `A3 Refund Demo Dataset`
- Agent: `A3 Refund Demo Agent`
- Domain: `e-commerce`
- Accepted inputs: `text`, `audio`, `file`, `image`
- Tool: `confirm_cancel`
- Parameter: `booking_id`
- Coverage: 5 diverse variations, including multi-input scenarios
- Behavior rule: refund completion must be confirmed through the correct tool call

The final `Generate Test Suite` button was not clicked because it creates real hosted Ashr data. This remains pending explicit user confirmation.

### Evidence

- Added `fixtures/a3/p3/ashr_chrome_agent_wizard_review.redacted.json`.
- Updated `docs/a3/p3_frontend_page_map.md`.
- Updated `docs/a3/p3_frontend_workflow_notes.md`.
- Updated `docs/a3/acceptance_checklist.md`.

### Next

1. If approved, click `Generate Test Suite` in the official Review step.
2. Revisit Agents/Datasets to see whether the generated hosted objects become UI-visible.
3. If a run/case can be generated, observe official expected-vs-actual, tool-call, pass/fail, and media evidence pages.

## 2026-07-06 - Official Generate Test Suite execution

### Goal

Create one real official frontend-visible Ashr dataset/test-suite example after explicit user confirmation, then observe what appears in the official UI.

### User confirmation

The user explicitly confirmed:

```text
确认生成 A3 Refund Demo Dataset / A3 Refund Demo Agent
```

### Action

- Clicked the official `Generate Test Suite` button in the Review step.
- Observed the button enter `Generating...`.
- Observed three Ashr API/network responses with HTTP `200`.
- Waited for generation to settle and reloaded the Datasets page.

### Result

The official frontend showed a new dataset:

- Name: `A3 Refund Demo Dataset`
- Display id: `#00000374`
- Dataset id: `884`
- Frontend path: `?tab=analysis&dataset=884`
- Test cases: 5
- Results: 0
- Runs history: no runs found
- Analytics: dataset count moved to 1, graded runs remained 0
- Agents page: still `No agents yet`

Generated test cases:

- `happy_path_text_valid_booking`
- `pdf_receipt_ocr_split_payment`
- `audio_cutoff_by_two_minutes_exception_request`
- `ui_shows_refund_but_backend_no_tool_call_image`
- `concurrent_requests_tool_timeout_then_processor_failure`

The generated cases cover text, audio, file, and image inputs. They are strong evidence for official dataset/case browsing and media-oriented case metadata, but they are not completed run results yet.

### Read-only API follow-up

Saved redacted evidence:

- `fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_requests.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_datasets.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_agents.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_requests_wait.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_datasets_wait.redacted.json`
- `fixtures/a3/p3/ashr_after_generate_list_agents_wait.redacted.json`

`get-dataset 884` succeeded and confirmed `dataset_source.total_runs == 5`.

### Safety

- The mutation was limited to the explicitly confirmed `Generate Test Suite` action.
- No API key values were printed or saved.
- No cookies, browser tokens, request headers, emails, or screenshots were saved.
- No API key management, team invite, billing, Trust publishing, or delete action was performed.

### Interpretation

This solves the previous "no real official frontend example" gap for dataset/case definitions. The remaining gap is narrower:

- Still missing: official run execution result.
- Still missing: official frontend pass/fail, score, actual tool calls, trace timeline, and failure reason for this new dataset.

### Next

1. Find the official way to run dataset `884` against an agent.
2. If a run can be produced safely, observe official Results / run detail / case result pages.
3. Map generated dataset case metadata into A3 dashboard/report provenance.

## 2026-07-06 - Official demo run 11925 mapped into A3 dashboard

### Goal

Turn the real frontend-visible `A3 Refund Demo Dataset` into a complete A3 triage example by adding one hosted run result and wiring it into the dashboard as a selectable source.

### Result

- Created a local synthetic run-result payload for dataset `884` with the same five generated refund test cases.
- The synthetic run has 2 passing cases and 3 failing cases.
- Created a hosted Ashr run through the safe A1 API probe path.
- Created run id: `11925`.
- Run status: `failed`.
- Dataset id: `884`.
- Saved redacted evidence:
  - `fixtures/a3/p3/ashr_dataset_884_demo_run_result.synthetic.json`
  - `fixtures/a3/p3/ashr_dataset_884_create_run_plan.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_create_run_real.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_run_11925_detail.redacted.json`
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_after_create.redacted.json`

### Dashboard wiring

- Added a dashboard data source: `P3 Official Demo 884/11925`.
- The source loads:
  - `fixtures/a3/p3/ashr_dataset_884_run_11925_detail.redacted.json`
  - `fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json`
  - `fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json`
- A3 now maps the official demo to:
  - 1 run
  - 5 cases
  - 2 passed
  - 3 failed
  - 40% pass rate
  - 56.4 average score
  - 100% trace completeness
  - 5 media-evidence cases
  - 5 VM-stream cases
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-official-demo-884-11925.png`

### Mapper updates

- `services/report/p3_ashr_mapper.mjs` now reads official dataset wrappers shaped like `response.dataset`.
- Dataset scenario metadata is joined into run cases for the official `884` sample.
- Dataset media action types are preserved in A3 `media_evidence`, including audio, file, and image channels.
- Output paths stay metadata-only; live signed URL rendering remains blocked by safety policy.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 41
pass 41
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed data source label: `P3 official Ashr demo dataset 884 / run 11925`.
- Confirmed visible counts: 1 run, 5 cases, 40% pass rate, 56.4 average score, 100% trace completeness.

### Remaining limitation

The frontend session expired before the populated official Results/run-detail page could be visually inspected. API evidence confirms the hosted run exists and is retrievable, but the official frontend result page still needs a fresh manual login pass.

## 2026-07-06 - Official frontend relogin check after run 11925

### Goal

Try to directly open the official Ashr frontend for dataset `884` after run `11925` exists, so A3 can compare its local dashboard against the real Results/run-detail UI.

### Action

- Opened `https://lab.ashr.io/?tab=analysis&dataset=884` in the Codex in-app browser.
- Read the page state without entering credentials and without saving cookies/tokens/headers.

### Result

- The page landed on the Ashr sign-in screen.
- Visible copy included:
  - `Sign in to your account`
  - `Continue with Google`
  - `Continue with Microsoft`
- Dataset `884` and run `11925` were not visible in the frontend in this unauthenticated state.
- Saved redacted evidence:
  - `fixtures/a3/p3/ashr_dataset_884_frontend_relogin_needed.redacted.json`

### Updated interpretation

This is no longer a "no real run exists" blocker. The real hosted run exists through API evidence and is already mapped into A3. The remaining work is specifically a frontend visual comparison after manual login.

Next manual step:

1. User signs into Ashr Lab in the browser.
2. Reopen `https://lab.ashr.io/?tab=analysis&dataset=884`.
3. Inspect Results / run detail / case detail / trace UI for run `11925`.

## 2026-07-06 - Authenticated official frontend dataset/case observation

### Goal

After the user restored the logged-in normal Chrome session, directly observe the real Ashr frontend for dataset `884` and compare it against A3's local `p3-official-demo` source.

### Observation

- Connected to the user's authenticated normal Chrome session through local CDP.
- Opened `https://lab.ashr.io/?tab=analysis&dataset=884`.
- Confirmed the official frontend shows:
  - dataset `A3 Refund Demo Dataset`
  - display id `#00000374`
  - `Overview`
  - `Test cases (5)`
  - `Results (0)`
  - generated request status `Completed`
- Opened `Test cases (5)`.
- Confirmed all five generated refund cases are visible with:
  - ordinal
  - title
  - case key
  - description
  - action count
  - tag count
- Opened sample case `happy_path_text_valid_booking`.
- Confirmed official case detail shows:
  - `TEST DETAILS`
  - tags
  - `ACTIONS (4)`
  - actor labels (`User`, `Agent`)
  - content text
  - input/media labels (`TEXT`, `AUDIO`)
  - `Tool Calls (1)`
  - `Back to Tests`
  - `Open Most Recent Run`

### Results / run visibility finding

- Clicking `Open Most Recent Run` still showed:
  - `Runs History`
  - `No runs found`
  - `This dataset hasn't been run yet`
- Direct URL attempt `?tab=analysis&dataset=884&run=11925` returned to dataset overview and did not show run `11925`.
- Official frontend did not show score, pass/fail, expected-vs-actual result, trace result, or failure class for API-created run `11925`.

### Evidence

- Added `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`.
- No screenshots were saved because the page includes account-adjacent UI such as user initials and internal creator id.
- No raw payload/config modal was opened.
- No API key, cookie, token, header, or email was saved.

### Interpretation

A3 now has a clearer product gap:

- Official frontend confirms dataset and generated test-case browsing.
- A3 mirrors this with dataset/case metadata, media evidence, and case detail.
- API-created run `11925` is retrievable and A3 can display it locally.
- Official frontend Results does not list that API-created run, so populated official Results UI parity is blocked by product/API visibility mismatch, not by missing A3 code.

## 2026-07-07 - Official UI-compatible tests run 11926

### Goal

Try another safe path to make a real result object that is closer to what the official Ashr frontend expects. The previous run `11925` used an A1-like `result.cases[]` shape. Frontend bundle and fixture evidence point to the official Results flow reading `run.result.tests[].action_results[]`.

### What changed

- Created a synthetic, redacted, official-UI-shaped result fixture:
  - `fixtures/a3/p3/ashr_dataset_884_demo_run_result.official_ui_tests.synthetic.json`
- The fixture converts the same five refund demo cases into:
  - `result.tests[]`
  - `tests[].test_id`
  - `tests[].action_results[]`
  - user text actions
  - tool-call comparison actions
  - expected vs actual response actions
  - `aggregate_metrics.total_tests`
  - `aggregate_metrics.tests_passed`
  - `aggregate_metrics.tests_failed`
- Ran a dry-run mutation plan:
  - `fixtures/a3/p3/ashr_dataset_884_create_run_ui_tests_plan.redacted.json`
- Created one real Ashr hosted run:
  - run id `11926`
  - dataset id `884`
  - 5 tests
  - 2 pass / 3 fail
  - result status `completed_with_failures`
  - evidence: `fixtures/a3/p3/ashr_dataset_884_create_run_ui_tests_real.redacted.json`

### Read-only verification

- `get_run(11926)` succeeded and confirmed `result.tests[]` exists:
  - `fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json`
- `list_runs(dataset_id=884)` now returns both `11926` and `11925`:
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_ui_tests_after_create.redacted.json`
- `list_runs(dataset_id=884, summary_only=true)` also returns both `11926` and `11925`:
  - `fixtures/a3/p3/ashr_dataset_884_list_runs_summary_ui_tests_after_create.redacted.json`
- This is important because the official frontend appears to call `list_runs` with `summary_only: true`.

### Dashboard update

- Updated A3 `p3-official-demo` to read run `11926` instead of `11925`.
- The local dashboard now shows:
  - 1 run
  - 5 cases
  - 2 pass / 3 fail
  - 40% pass rate
  - 56.4 average score
  - 5 media-evidence cases
  - 0 VM stream cases, because the official `tests[]` result does not include the old A1-like `vm_stream` field.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-official-demo-884-11926.png`

### Frontend observation

- The in-app browser was not logged in to Ashr Lab and showed the sign-in page.
- Therefore this round could not visually confirm whether the official Results tab now shows run `11926`.
- The API evidence is stronger than before: run `11926` is not only retrievable by `get_run`, it is also present in the frontend-style `summary_only` run list.

### Verification

Command:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 41
pass 41
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed data source label references `run 11926`.
- Confirmed metrics: 5 cases, 40% pass rate, 56.4 average score, 5 media cases.

### Current interpretation

The old blocker has changed. It is no longer true that A3 lacks a real run result. A3 now has:

- a real generated dataset `884`
- an old A1-like API run `11925`
- a new official-UI-like API run `11926`
- local dashboard support for `11926`

The remaining proof is visual: refresh the logged-in official Ashr Lab frontend for dataset `884` and check whether Results now lists run `11926`.

## 2026-07-07 - Release Gate commercial growth pass

### Goal

Push A3 toward a commercial release-intelligence workflow, not just a triage dashboard.

### Added capability

A3 now computes a release decision:

- `approve_release`
- `needs_review`
- `block_release`

The release gate considers:

- pass rate
- critical/blocker failures
- unsafe or forbidden-tool failures
- missing required tool failures
- trace completeness
- A2 coverage minimums
- media signed URL safety

### Official demo result

For run `11926`, A3 now says:

- Decision: `Block release`
- Risk score: `70`
- Failed checks: `2`
- Blocks merge: `yes`

This is correct for the demo data because the run only has a 40% pass rate and includes a missing-required-tool failure.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-release-gate-11926.png`

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 43
pass 43
fail 0
```

## 2026-07-07 - PR Gate workflow and audit bundle commercial pass

### Goal

Extend the Release Gate into a workflow that can be attached to a PR or release review: GitHub check payload, PR comment, waiver policy, reviewer lanes, audit bundle, and incident replay case list.

### Added capability

A3 now builds a `release_workflow` object with:

- GitHub check shape:
  - `Ashr++ Release Gate`
  - `success` / `neutral` / `failure`
  - merge-blocking flag
  - check output title, summary, and text
- PR comment Markdown template.
- Waiver policy:
  - required fields
  - blocked-release exceptional waiver rule
  - expiry maximums
- Reviewer workflow:
  - review state
  - review lanes
  - next actions
- Audit bundle:
  - manifest version
  - redaction policy
  - required and optional artifacts
- Incident replay pack:
  - top-risk failed case ids
  - `failed_cases_first` mode

### API calibration note

No new Ashr hosted mutation was performed in this pass. The workflow is built on the existing redacted official-demo evidence for dataset `884` / run `11926`. This keeps the round focused on release workflow packaging without creating duplicate hosted runs.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-pr-gate-audit-11926.png`

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 44
pass 44
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed `PR Gate & Audit` renders check conclusion `failure`, blocks merge `yes`, waiver required `yes`, waiver max `1d`, and audit bundle artifacts.

### Current interpretation

A3 is now closer to an enterprise release-control surface. It still does not call the GitHub Checks API or persist approvals, but it has the data contract and UI/report surfaces needed for the next implementation step.

## 2026-07-07 - Gate CLI contract and hashed audit manifest

### Goal

Create the local command contract for a future CI/PR release gate.

### Added capability

A3 now has a command-shaped gate entrypoint:

```text
node services/report/a3_gate_cli.mjs --runs fixtures/a3/mock_run_results.json --grades fixtures/a3/mock_grade_results.json --coverage fixtures/a2/results/a2_g3_coverage_report.json --thresholds fixtures/a3/release_gate_thresholds.json --release-version local-mock-commercial-gate --source a3-local-mock --json
```

The output includes:

- `schema_version: a3.gate_cli.v1`
- dashboard summary
- release gate
- release workflow
- GitHub check payload
- waiver policy
- reviewer workflow
- incident replay cases
- audit manifest
- SHA-256 hashes for input files
- exit-code hint for merge blocking
- workspace-relative artifact paths
- `--strict-exit` for CI
- `--no-fail` for local report generation

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
  - `services/report/report_builder.mjs`
- Fixture:
  - `fixtures/a3/release_gate_thresholds.json`
  - `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Docs:
  - `docs/a3/p3_gate_cli_growth_2026_07_07.md`

### API calibration note

This pass did not create new live Ashr API data. It packages existing A3/A2/P3 evidence into a CI-consumable local artifact. No API key, token, cookie, email, header, or live signed media URL was printed or saved.

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

### Current interpretation

A3 now has the contract needed for a GitHub Action or PR check. It is not yet a live GitHub required check, but the payload, evidence hashes, and tests are in place.

### Follow-up hardening

- Added CLI output file support:
  - JSON report
  - Markdown report
  - GitHub Check Run payload
  - PR comment Markdown
- Added GitHub Check annotations for the top-risk cases.
- Added lightweight redaction scrubber for CLI output.
- Added committed redacted PR artifacts:
  - `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
  - `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
  - `fixtures/a3/p3/a3_gate_cli_report.redacted.md`
- Expanded focused CLI test coverage to 7 tests.

Updated focused verification:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 7
pass 7
fail 0
```

## 2026-07-07 - GitHub dry-run integration adapter

### Goal

Convert the existing A3 PR gate / gate CLI output into GitHub-shaped dry-run artifacts. This prepares A3 for a future required check without using a live token yet.

### Added capability

A3 now includes:

- `buildGitHubCheckRunRequest()`
  - create-check mode
  - update-check mode
  - explicit `headSha` requirement
  - caller-controlled `detailsUrl`
  - normalized annotations
- `buildPrCommentUpsertPlan()`
  - stable HTML marker
  - create-new-comment mode
  - update-existing-comment mode
  - PR comment body from A3 gate evidence
- `buildGitHubActionWorkflowExample()`
  - workflow showing how a future CI job can call `a3_gate_cli.mjs`
  - artifact upload step
  - local gate enforcement step

### Artifacts

- Code:
  - `services/report/a3_github_integration.mjs`
- Tests:
  - `tests/a3/a3_github_integration.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
  - `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- Docs:
  - `docs/a3/p3_github_action_workflow_example.yml`
  - `docs/a3/p3_github_dry_run_integration_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
tests 6
pass 6
fail 0
```

### API calibration note

No live GitHub API call was made. No GitHub token, Ashr key, cookie, or signed URL was read or written. This pass uses existing redacted A3 gate evidence only.

### Current interpretation

A3 now has the dry-run bridge from local release gate to GitHub PR workflow. The remaining work is to add an explicitly approved live writer and required-check deployment path.

## 2026-07-07 - Generated artifact manifest for audit-grade exports

### Goal

Extend the Gate CLI audit trail from input evidence hashes to generated output artifact hashes.

### Added capability

A3 now supports:

- `--output-manifest`
- `a3.generated_artifact_manifest.v1`
- output hash records for:
  - `json_report`
  - `markdown_report`
  - `github_check_run`
  - `pr_comment_markdown`
- content type and byte size per generated artifact
- workspace-relative output paths
- release summary embedded in the manifest
- safety metadata showing the manifest is dry-run compatible and should not contain secret values

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- Docs:
  - `docs/a3/p3_generated_artifact_manifest_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_artifact_manifest_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 9
pass 9
fail 0
```

### API calibration note

No new Ashr or GitHub API call was made. This pass only uses local redacted A3/A2 fixture evidence and generated local output files. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes one enterprise audit gap: reviewers can now verify that generated report artifacts match the files produced by the Gate CLI. The remaining enterprise gaps are signed manifests, immutable storage, persisted approvals, waiver expiry, and live required-check enforcement.

## 2026-07-07 - File-backed waiver validation

### Goal

Turn the release workflow waiver policy into a local file-backed validation contract.

### Added capability

A3 now supports:

- `--waiver`
- `--generated-at`
- `a3.waiver.v1` waiver request fixture
- `a3.waiver_review.v1` validation output
- waiver file hashing in the audit manifest
- Markdown Waiver Review section

The validator checks:

- schema version
- required waiver fields
- run id
- release version
- environment
- head SHA
- expiry date
- max expiry policy
- required approver roles
- approval record fields
- failed-check coverage
- reviewed artifact hash shape

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`
- Docs:
  - `docs/a3/p3_waiver_validation_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_waiver_workflow_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 12
pass 12
fail 0
```

### API calibration note

No live Ashr or GitHub API call was made. This pass uses local redacted A3/A2 evidence and local waiver fixtures only. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes part of the waiver governance gap: A3 can now say whether a local exception file satisfies policy. It still does not persist approvals in a backend, verify reviewer identity against GitHub/SSO, or let a waiver automatically unblock a release.

## 2026-07-07 - File-backed signed approval validation

### Goal

Add a structured approval/sign-off validation layer on top of waiver validation.

### Added capability

A3 now supports:

- `--approval`
- `a3.approval.v1` approval record fixture
- `a3.approval_review.v1` validation output
- approval file hashing in the audit manifest
- Markdown Approval Review section

The validator checks:

- schema version
- approval id
- decision enum
- blocked-release exception decision
- run id
- release version
- environment
- head SHA
- waiver id binding
- signer role/name/timestamp
- co-signer role/name/timestamp
- required signer roles
- reviewed artifact SHA-256 hashes
- separation-of-duties self-approval guardrail

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixtures:
  - `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`
- Docs:
  - `docs/a3/p3_signed_approval_validation_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_signed_approval_2026_07_07.md`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 15
pass 15
fail 0
```

### API calibration note

No live Ashr or GitHub API call was made. This pass uses local redacted A3/A2 evidence and local approval fixtures only. No API key, token, cookie, header, email, or signed media URL was read or saved.

### Current interpretation

This closes part of the sign-off evidence gap: A3 can now verify that a file-backed approval is scoped to the exact run/release/environment/head SHA and references the waiver/artifacts under review. It still needs cryptographic signatures, durable persistence, and real identity binding before it becomes enterprise-grade approval infrastructure.

## 2026-07-07 - Audit bundle index / root hash / chain-of-custody

### Goal

Close the next enterprise audit gap after generated manifests, waiver validation, and approval validation: bind the release evidence into one verifiable bundle index.

### Added capability

A3 now supports:

- `--output-bundle`
- `a3.audit_bundle_index.v1`
- `bundle_root_hash`
- workspace-safe bundle artifact paths
- source/generated/governance/custody artifact grouping
- custody event hashes with `previous_event_hash`
- local retention metadata and verification command hint

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- Docs:
  - `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_audit_bundle_index_2026_07_07.md`

### API calibration note

No live Ashr or GitHub API call was made in this pass. The work uses existing local A3/A2 fixtures plus redacted waiver/approval records. No API key, token, cookie, header, email, or live signed media URL was read or saved.

### Current interpretation

This turns A3 evidence from "several related files" into "one bundle index with a root hash." It is still local and unsigned, but it gives future enterprise work a clear handle for audit, retention, GitHub artifacts, and management sign-off.

## 2026-07-07 - Audit bundle verifier

### Goal

Turn the bundle root hash into something a reviewer can actually verify from the CLI.

### Added capability

A3 now supports:

- `--verify-index`
- `a3.audit_bundle_verification.v1`
- root hash verification
- artifact hash verification
- artifact byte-size verification
- missing artifact detection
- custody event hash verification
- previous-event hash chain verification
- JSON and Markdown verification reports

### Artifacts

- Code:
  - `services/report/a3_gate_cli.mjs`
- Tests:
  - `tests/a3/a3_gate_cli.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- Docs:
  - `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`

### API calibration note

No live Ashr or GitHub API call was made in this pass. The work verifies local redacted bundle evidence only. No API key, token, cookie, header, email, or live signed media URL was read or saved.

### Current interpretation

This makes A3's audit bundle useful after export. A customer or reviewer can run verification and get a pass/fail answer instead of manually checking every JSON file.

## 2026-07-07 - Official frontend mirror clean-room integration

### Goal

Fold the offline Ashr frontend mirror into P3 calibration as a clean-room product map.

### Added capability

A3 now summarizes the mirror into:

- official navigation parity
- official API method group parity
- visible UI label confirmation
- copy / partial / future / out-of-scope decisions
- safety flags for official source, secrets, cookies, tokens, and signed URLs

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Fixture:
  - `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json`
- Docs:
  - `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-official-frontend-mirror.png`

### API calibration note

No live Ashr API call was made in this pass. The work uses the offline redacted mirror summary only. No API key, token, cookie, header, email, raw signed media URL, or official source file was committed.

### Current interpretation

This turns the frontend mirror from "we have a zip" into a dashboard/report-visible product reference. A3 can now explain which official Ashr pages and API groups it is copying, partially copying, deferring, or intentionally excluding.

## 2026-07-07 - Release War Room

### Goal

Create the first money-grade Release War Room layer on top of Release Gate, PR Gate, audit bundle, incident replay, media readiness, usage/quota, and official frontend parity.

### Added capability

A3 now supports:

- `a3.release_war_room.v1`
- `summarizeReleaseWarRoom()`
- dashboard `Release War Room` panel
- JSON export field `release_war_room`
- Markdown section `Release War Room`
- print/PDF `Release War Room` section
- redacted official-demo War Room fixture for dataset `884` / run `11926`

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Fixture:
  - `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Docs:
  - `docs/a3/p3_release_war_room_growth_2026_07_07.md`
  - `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-release-war-room.png`

### API calibration note

No live Ashr API call was made in this pass. The fixture was generated from existing redacted official demo evidence. No key, token, cookie, email, raw signed media URL, or official source file was saved.

### Current interpretation

This makes A3 feel less like an eval viewer and more like an agent release command center. The current official demo War Room says `no_go`, revenue risk score `93`, merge blocked, waiver required, and audit evidence required.

## 2026-07-07 - Official parity roadmap and media queue

### Goal

Convert official frontend mirror evidence and media calibration evidence into dashboard-visible reviewer workflow.

### Added capability

A3 now supports:

- dashboard `Official Parity Roadmap` panel
- `official_parity_roadmap` JSON export field
- Markdown `Official Parity Roadmap` section
- print/PDF `Official Parity Roadmap` section
- Media Readiness `Media Evidence Queue`
- report-center copy that names parity roadmap as part of the release evidence packet

### A1/A2 calibration note

This pass re-ran A3 tests over:

- A1-style generated run/tool-call/trace fixture paths
- A2 G3 grade results
- A2 G3 coverage report
- P3 Ashr mapper output for real redacted run shapes

The goal is to keep A3 attached to A1 runner output and A2 judge output instead of becoming a standalone dashboard mock.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_official_parity_media_queue_2026_07_07.md`
- Screenshots:
  - `docs/screenshots/a3-dashboard-official-parity-media-queue.png`
  - `docs/screenshots/a3-dashboard-media-evidence-queue.png`
  - `docs/screenshots/a3-dashboard-media-evidence-queue-detail.png`

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
76 tests
76 pass
0 fail
```

### API calibration note

No live Ashr API call was made in this pass. The work uses existing redacted P3 Ashr fixtures, the official frontend clean-room summary, and local A1/A2-derived fixtures. No API key, token, cookie, email, raw signed media URL, or official source file was saved.

## 2026-07-07 - Incident replay queue

### Goal

Build a replay-first failed-case queue that can support release review, incident review, waiver review, and audit export.

### Added capability

A3 now supports:

- `a3.incident_replay_queue.v1`
- `summarizeIncidentReplayQueue()`
- dashboard `Incident Replay` panel
- JSON export field `incident_replay_queue`
- Markdown section `Incident Replay Queue`
- print/PDF section `Incident Replay Queue`
- reviewer packet artifact list per replay case

### A1/A2 calibration note

The replay queue is intentionally joined from upstream evidence:

- A1-style trace/observation readiness
- A1 expected-vs-actual tool-call diff evidence
- A2 judge evidence count and judge modes
- A2 failure class and severity
- A3 release blocker status
- P3 metadata-only media evidence

This means A3 replay is still connected to runner and judge output instead of becoming a dashboard-only mock.

### Artifacts

- Code:
  - `services/report/report_builder.mjs`
  - `apps/dashboard/index.html`
- Tests:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Docs:
  - `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`
- Screenshot:
  - `docs/screenshots/a3-dashboard-incident-replay-queue.png`

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
78 tests
78 pass
0 fail
```

### API calibration note

No live Ashr API call was made in this pass. The work uses existing redacted P3 Ashr fixtures and local A1/A2-derived fixtures. No API key, token, cookie, email, raw signed media URL, or official source file was saved.
## 2026-07-08 - SaaS Admin action request workflow

Continued A3 Product Console / SaaS growth after the group lead updated `main` during merge-conflict cleanup. Fetched `origin/main`, confirmed the current A3 branch is already based on the latest main, and kept this pass additive inside A3-owned files.

Added a safe request/audit layer for SaaS Admin actions:

- `POST /api/a3/admin/actions/submit`
- `GET /api/a3/admin/actions`
- `a3.saas_admin_action_request.v1`
- `a3.saas_admin_action_receipt.v1`
- SQL table contract: `saas_admin_action_requests`
- SQLite persistence for admin action request rows
- Dashboard `Record Request` / `Record Guardrail` control
- Report export summary for recorded admin requests

No real Ashr login, team invite, billing, API-key, Trust publish, or cloud mutation was performed. No `.env.local`, API key, token, cookie, account email, raw share token, or live signed URL was read or committed.

Verification passed:

```text
node --test tests/a3/a3_saas_admin.test.mjs tests/a3/a3_store.test.mjs
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

Result: 79 pass, 0 fail.

## 2026-07-08 - Durable reviewer waiver and approval records

Continued A3 enterprise release sign-off work by adding a durable review workflow layer above the existing file-backed waiver/approval validation.

Added:

- `services/report/a3_review_workflow.mjs`
- `a3.review_workflow_record.v1`
- `a3.review_workflow_index.v1`
- `a3.review_workflow_receipt.v1`
- `POST /api/a3/review/waivers`
- `POST /api/a3/review/approvals`
- `GET /api/a3/review/workflow`
- SQL table contract: `review_workflow_records`
- SQLite persistence for waiver/approval workflow records
- Dashboard durable review records under Reviewer Workflow
- JSON export field: `review_workflow`
- Documentation: `docs/a3/p3_review_workflow_durable_storage_2026_07_08.md`

The new durable records reuse the existing Gate CLI validators rather than changing release-gate semantics.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live cloud mutation.
- No raw cryptographic signatures stored.
- No API key, token, cookie, account email, raw share token, or live signed URL committed.

Remaining production gap:

Real cryptographic signature verification and SSO/OIDC/GitHub reviewer identity binding are still not implemented.

## 2026-07-08 - Live-capable GitHub Check publisher

Continued A3 commercial PR Gate work by adding a live-capable GitHub Check Run publisher while keeping existing dry-run contracts intact.

Added:

- `publishGitHubCheckRun(...)` in `services/report/a3_github_integration.mjs`
- `services/report/a3_github_publish_cli.mjs`
- default dry-run receipt generation
- explicit `--live` mode for CI
- runtime-token support through environment variables
- updated GitHub Actions workflow example
- redacted dry-run publish receipt fixture
- documentation in `docs/a3/p3_live_github_check_publisher_2026_07_08.md`

Verification:

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result: 13 pass, 0 fail.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No token, cookie, email, Authorization header, or raw signed URL committed.

Remaining production gap:

The publisher can create/update a GitHub Check Run when CI explicitly opts in, but repository branch protection still needs maintainer-approved configuration before `Ashr++ Release Gate` is truly a required check.

## 2026-07-08 - PR comment publisher and required-check plan

Continued A3 PR Gate work by adding human-readable PR comment publishing and a branch-protection required-check plan.

Added:

- `publishPrCommentUpsert(...)`
- `buildBranchProtectionRequiredCheckPlan(...)`
- CLI flags `--pr-comment` and `--pull-number`
- GitHub Actions `Publish Ashr++ PR Comment` example step
- redacted dry-run PR comment receipt fixture
- redacted required-check plan fixture
- documentation in `docs/a3/p3_pr_comment_required_check_plan_2026_07_08.md`

Verification:

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result: 21 pass, 0 fail.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No branch-protection mutation.
- No token, cookie, email, Authorization header, or raw signed URL committed.

Remaining production gap:

Branch protection still needs maintainer approval before `Ashr++ Release Gate` is truly required.

## 2026-07-08 - Release evidence authority guardrails

Continued the A3 commercial SaaS path defined in `docs/strategy/large-saas-a1-a2-a3-full-plan.md` by making release evidence less like a static report field and more like a tenant-scoped authority object.

Added:

- `services/report/a3_release_evidence.mjs`
- release evidence health, deterministic next action, and sanitized diff helpers
- `release_evidence_health` and `next_action` in `GET /api/a3/releases/:releaseId/evidence-summary`
- tenant/project guards for release evidence API reads
- source/organization/project filtering for release evidence hosted-report snapshots
- tenant/project filtering for Dashboard, Report Center, Artifact Registry, Product Console, and usage-ledger report inputs
- report-id scope guards for report detail, manifest, view, revoke, and report-list routes
- SQLite report tenant persistence using `tenant_scope.organization_id` and `tenant_scope.project_id`
- API internal-error redaction for Bearer tokens, Ashr key assignments, cookies, and emails
- tests for release evidence health/diff, cross-tenant denial, SQLite tenant persistence, and error redaction
- authority handoff in `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`

## 2026-07-08 - GitHub publish evidence in reports and artifact registry

Continued A3 PR Gate evidence work by binding GitHub publish receipts into report exports and Artifact Registry.

Added:

- `summarizeGithubPublishEvidence(...)`
- JSON report field `github_publish_evidence`
- Markdown section `GitHub Publish Evidence`
- Artifact Registry entries for GitHub check receipt, PR comment receipt, and required-check plan
- Artifact Registry preset `github_pr_gate_packet`
- dashboard static fixture loading for GitHub publish evidence
- dashboard export wiring for `state.githubPublishEvidence`
- documentation in `docs/a3/p3_github_publish_evidence_registry_2026_07_08.md`

Verification:

```text
node --check services/report/a3_release_evidence.mjs
node --check services/report/a3_store.mjs
node --check services/report/a3_api_server.mjs
node --check services/report/a3_sqlite_store.mjs
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/shareable_report.test.mjs tests/a3/report_center_index.test.mjs tests/a3/artifact_registry.test.mjs tests/a3/a3_sqlite_store.test.mjs
```

Result: 20 pass, 0 fail.

A1/A2 calibration:

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, score, pass/fail, failure taxonomy, and policy semantics were not changed.
- A3 still consumes A1/A2 outputs downstream through existing dashboard/report/store contracts.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub, billing, auth, team, API-key, Trust, or cloud mutation API call.
- No API key, token, cookie, account email, raw share token, live signed URL, or private key committed.

Current interpretation:

A3 now has a stronger SaaS-style evidence boundary. Release evidence and hosted reports are no longer only visible UI/report data; they also carry health, next-action, tenant scope, and denial behavior that future auth/RBAC/database work can attach to.

## 2026-07-08 - Release evidence v2 authority API

Continued A3 under `docs/strategy/large-saas-a1-a2-a3-full-plan.md` by moving release evidence from v1 report summary toward an explicit authority object that can anchor PR gates, hosted reports, usage, audit, and enterprise review.

20 growth points considered this round:

1. v2 authority summary.
2. v1/v2 API version negotiation.
3. compact evidence health endpoint.
4. evidence diff endpoint.
5. A1 RunResult evidence counts.
6. A1 trace/observation/tool-call evidence counts.
7. A2 GradeResult/Judge/failure-class evidence counts.
8. required-check proof state.
9. GitHub Check readback state placeholders.
10. PR comment readback state placeholders.
11. hosted report snapshot linkage.
12. usage-ledger linkage.
13. redaction fail-closed surfaces.
14. compliance/retention placeholders.
15. source snapshot id.
16. tenant/project scope propagation.
17. A1/A2 contract mapping artifact.
18. Growth-Auditor money-grade audit artifact.
19. cross-tenant diff denial.
20. v1 backward compatibility.

Implemented this round:

- Added `a3.release_evidence_summary.v2` builder in `services/report/a3_release_evidence.mjs`.
- Kept v1 stable by requiring explicit `version=2` or v2 schema request for the v2 response.
- Added `GET /api/a3/releases/:releaseId/evidence-health`.
- Added `GET /api/a3/releases/:releaseId/evidence-diff`.
- Added v2 A1 evidence fields for RunResult, Trace, ToolCall, and Observation counts.
- Added v2 A2 evidence fields for Scenario, Judge, GradeResult, and FailureTaxonomy counts.
- Added required-check proof fields that keep plan-only separate from enforced.
- Added readback placeholders that do not claim live GitHub Check or PR comment confirmation.
- Added usage-ledger linkage through `summary_id`.
- Added safety/redaction/compliance fields that fail closed by default.
- Added A1/A2 contract mapping artifact:
  - `docs/a3/p3_a1_a2_release_evidence_v2_contract_map_2026_07_08.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_release_evidence_v2_2026_07_08.md`

Verification:

```text
node --check services/report/a3_release_evidence.mjs
node --check services/report/a3_store.mjs
node --check services/report/a3_api_server.mjs
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs
```

Result: 14 pass, 0 fail.

A1/A2 calibration:

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, score, pass/fail, failure taxonomy, and release policy semantics were not changed.
- A3 v2 authority maps A1/A2 outputs downstream and records where source snapshot/hash/readback contracts are still missing.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub readback, branch-protection mutation, billing mutation, auth/team/API-key/Trust mutation, or cloud mutation.
- No API key, token, cookie, account email, raw share token, live signed URL, or private key committed.

Current interpretation:

A3 now has a concrete v2 authority API surface, but not yet full enterprise production proof. The next money-grade step is live-shaped GitHub readback plus immutable source snapshots and Postgres/RLS-backed persistence.

## 2026-07-08 - Release evidence v2 SQL authority rows

Continued the same release evidence v2 authority round by adding DB-shaped storage contracts for the v2 summary instead of leaving it as an API-only computed object.

Added:

- SQL migration contract table `release_evidence_snapshots`
- SQL migration contract table `release_evidence_diffs`
- SQL migration contract table `release_evidence_readbacks`
- Postgres/MySQL/SQLite-compatible DDL for v2 authority rows
- SQLite inspection counts for v2 snapshots, diffs, and readbacks
- SQLite persistence of one v2 authority snapshot per release evidence summary
- SQLite persistence of safe v1-to-v2 diff evidence
- SQLite persistence of readback placeholder rows for:
  - GitHub Check
  - PR comment
  - required-check proof

Verification:

```text
node --check services/report/a3_sql_migrations.mjs
node --check services/report/a3_sqlite_store.mjs
node --test tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs
```

Result: 18 pass, 0 fail.

Safety boundary:

- No live Ashr, GitHub, auth, billing, object storage, or cloud API calls.
- No `.env.local` read.
- No real readback claims; readback rows remain explicit placeholder/plan-only states until live readback exists.

Current interpretation:

A3 now has a local SQL-backed place for release evidence v2 snapshots, diffs, and readbacks. This still is not production Postgres/RLS, but it gives A1/A3 a concrete DB contract to implement against.

## 2026-07-08 - GitHub readback and required-check proof contracts

Continued A3 under `docs/strategy/large-saas-a1-a2-a3-full-plan.md` by turning GitHub publish evidence into live-shaped readback evidence.

Implemented:

- Added `buildGitHubCheckReadbackReceipt(...)`.
- Added `buildPrCommentReadbackReceipt(...)`.
- Added `buildRequiredCheckProof(...)`.
- Added live-capable readback helpers:
  - `readGitHubCheckRun(...)`
  - `readPrCommentReadback(...)`
  - `readRequiredCheckProof(...)`
- Added readback states:
  - `generated`
  - `posted`
  - `readback_confirmed`
  - `stale`
  - `missing`
  - `deleted`
  - `permission_denied`
  - `failed`
- Wired readback receipts into `release_evidence_summary.v1` aggregation and `a3.release_evidence_summary.v2`.
- Added redacted readback fixtures:
  - `fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json`
  - `fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json`
  - `fixtures/a3/p3/a3_github_required_check_proof_plan_only.redacted.json`
- Added documentation:
  - `docs/a3/p3_github_readback_contract_2026_07_08.md`

Verification:

```text
node --check services/report/a3_github_integration.mjs
node --check services/report/a3_release_evidence.mjs
node --check services/report/report_builder.mjs
node --test tests/a3/a3_github_integration.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs
```

Result: 40 pass, 0 fail.

A1/A2 calibration:

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, score, pass/fail, failure taxonomy, and policy semantics were not changed.
- A3 readback evidence stays downstream of A1/A2 and only proves PR/release publication state.

node --test tests/a3/artifact_registry.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result: 73 pass, 0 fail.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No branch-protection mutation.
- No token, cookie, email, raw signed URL, Authorization header, or secret value stored.
- Required-check proof remains `plan_only` unless branch-protection readback confirms enforcement.

Current interpretation:

A3 can now represent the commercial distinction between a generated artifact, a posted artifact, and a readback-confirmed external control. The remaining production step is maintainer-approved live CI/GitHub App integration that actually performs the readback against GitHub.

## 2026-07-08 - Release evidence readback capture API

Continued A3 under `docs/strategy/large-saas-a1-a2-a3-full-plan.md` by moving release evidence readback from static fixture state into an API-backed, idempotent, tenant-scoped capture path.

Implemented:

- Added `POST /api/a3/releases/:releaseId/readbacks`.
- Added `GET /api/a3/releases/:releaseId/readbacks`.
- Added `submitReleaseEvidenceReadback(...)` and `listReleaseEvidenceReadbacks(...)` to the A3 store.
- Added readback capture idempotency.
- Added audit event `release_evidence.readback_captured`.
- Added nested redaction for Authorization, token, email, cookie, password, API-key, and secret-like values.
- Wired captured readbacks into `a3.release_evidence_summary.v2` so latest captured readback can override static fixture readback state.
- Kept A1/A2 import receipts separate from readback capture receipts.
- Persisted current authority readback rows through the SQLite-backed store.
- Added `release_evidence_readbacks` usage meter evidence.
- Added `release_evidence_readback` artifact registry entries.
- Added documentation:
  - `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`

Verification:

```text
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/artifact_registry.test.mjs
```

Result: 21 pass, 0 fail.

A1/A2 calibration:

- A1 runner, SDK, trace, observation, and tool-call semantics were not changed.
- A2 judge, score, pass/fail, failure taxonomy, and policy semantics were not changed.
- A3 readback capture remains downstream of A1/A2 evidence.
- GitHub readback confirmed is still not the same as A1 release evidence verifier passed.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No branch-protection mutation.
- No token, cookie, email, Authorization header, raw account value, or secret value committed.

Current interpretation:

A3 now has a concrete API and DB path for external CI/GitHub readback evidence. This is a useful SaaS step from static mock evidence toward release control-plane evidence, but production still needs a live GitHub App/CI worker, A1 verifier packet adapter, hosted auth/RBAC, and Postgres/RLS.

## 2026-07-08 - Readback worker CLI and UI/report visibility

Continued A3 under `docs/strategy/large-saas-a1-a2-a3-full-plan.md` by connecting the readback capture path to a worker-style CLI and customer-visible dashboard/report surfaces.

Implemented:

- Added safe CLI:
  - `services/report/a3_readback_capture_cli.mjs`
- Added CLI tests:
  - `tests/a3/a3_readback_capture_cli.test.mjs`
- Added dry-run default and explicit `--submit`.
- Added `--output-receipt` for CI artifacts.
- Sanitized nested Authorization, token, cookie, email, password, API-key, and secret-like fields.
- Normalized readback resource kinds across GitHub/API/fixture naming.
- Added dashboard payload field:
  - `release_evidence_readbacks`
- Added readback records and counts to:
  - `release_evidence_summary`
  - JSON report export
  - Markdown report export
  - dashboard Release Evidence panel
  - Report Center summary/tile
  - print-ready report
- Added A1/A2 contract-alignment documentation:
  - `docs/a3/p3_readback_a1_a2_contract_alignment_2026_07_08.md`
- Added Growth-Auditor documentation:
  - `docs/a3/p3_growth_auditor_readback_worker_round_2026_07_08.md`
- Added implementation documentation:
  - `docs/a3/p3_readback_worker_and_visibility_2026_07_08.md`

Verification:

```text
node --check services/report/a3_readback_capture_cli.mjs
node --check services/report/report_builder.mjs
node --check services/report/a3_store.mjs
node --check apps/dashboard/src/app.mjs
node --test tests/a3/a3_readback_capture_cli.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
git diff --check
```

Result: 81 pass, 0 fail.

A1/A2 calibration:

- A1 RunResult, trace, observation, and tool-call semantics were not changed.
- A2 GradeResult, score, pass/fail, judge, rubric, and failure taxonomy semantics were not changed.
- Readback evidence is still downstream of A1/A2 and only proves external release-control state.

Safety boundary:

- No `.env.local` read.
- No Ashr API call.
- No live GitHub API call.
- No branch-protection mutation.
- No billing, hosted auth, team, API-key, Trust, or cloud mutation.
- No token, cookie, email, Authorization header, raw key, raw account value, or secret value committed.

Current interpretation:

This closes the gap between "A3 can store readback" and "A3 can be fed by a worker and show readback to users." Production still needs a live GitHub App/GitHub Actions worker, hosted auth/RBAC, and production Postgres/RLS before readback can enforce a real customer release gate.

## 2026-07-09 - Commercial CL gate anchors

Continued from latest `main` after A3 readback work was merged. This round upgrades the CL gate so A3 cannot quietly drift away from the commercial SaaS endgame.

Implemented:

- Added `commercial` subcommand to `scripts/cl_guard.py`.
- Added commercial anchor gate to `.github/workflows/cl-gate.yml`.
- Added 20 blocker anchors covering strategy, CL workflow, A3 dashboard/API/report/store/release evidence/readback, A1 schemas, A2 schemas, and A3 tests.
- Added 4 advisory-only gaps for future A3 toolchains:
  - Playwright TS E2E
  - Tailwind/CSS product system
  - React Native / Expo mobile surface
  - WeChat mini program surface
- Added tests:
  - `tests/a1/test_cl_guard.py`
- Added Contract-Agent artifact:
  - `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md`
- Added UI/TS/Playwright artifact:
  - `docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_cl_gate_2026_07_09.md`

Verification:

```text
python -m py_compile scripts/cl_guard.py tests/a1/test_cl_guard.py
python scripts/cl_guard.py commercial
python scripts/cl_guard.py hygiene
python -B -m pytest tests/a1/test_cl_guard.py -q -p no:cacheprovider
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_saas_admin.test.mjs tests/a3/a3_review_workflow.test.mjs
npm ci  # in packages/ts/ashr-clone
```

Results:

- CL guard pytest passed: 3 pass, 0 fail.
- A3 Node contracts passed: 37 pass, 0 fail.
- TypeScript package dependency install passed with 0 vulnerabilities.
- Local full TypeScript SDK test is blocked by missing Go on this Windows workstation because the TS suite intentionally builds and drives the Go API server.
- Added Go setup to the `typescript-sdk` CI job so the cross-stack TypeScript-to-Go vertical slice can run in GitHub Actions.

A1/A2 calibration:

- A1 evidence and worker schema anchors now participate in the CL gate.
- A2 grade and commercial-readiness schema anchors now participate in the CL gate.
- A3 still consumes A1/A2 evidence downstream through API/dashboard/report tests; it does not redefine A1/A2 semantics.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub mutation.
- No billing/auth/team/API-key/Trust/cloud mutation.
- Missing Playwright/Tailwind/mobile/WeChat surfaces are advisories, not false blockers.

Current interpretation:

This round makes A3 more durable rather than more flashy. It gives the repo a low-noise commercial regression gate: if future work removes the release evidence path, A1/A2 contract anchors, TypeScript mainline, dashboard webapp split, or A3 API/report/store evidence spine, CL can stop it.

- No token, cookie, email, Authorization header, or raw signed URL committed.

Remaining production gap:

Publish receipts still need audit-bundle hashing, dedicated dashboard cards, and real branch-protection verification.

## 2026-07-09 - Commercial Growth Round 2

Continued from PR #23 / `codex/a3-commercial-growth-round2` with latest `origin/main` and `docs/strategy/large-saas-a1-a2-a3-full-plan.md` as the commercial bus. This round pushed A3 in three parallel directions: Playwright E2E proof, A2 persistence/unblock export consumption, and a machine-readable commercial growth manifest.

Implemented:

- Added Playwright TS E2E infrastructure:
  - `package.json`
  - `package-lock.json`
  - `playwright.config.ts`
  - `tests/e2e/static-dashboard-server.mjs`
  - `tests/e2e/a3-dashboard-commercial.spec.ts`
- Verified the real dashboard page `apps/dashboard/index.html?source=p3-official-demo`.
- Captured screenshot evidence:
  - `docs/screenshots/a3-playwright-dashboard-commercial-2026-07-09.png`
- Added A2 persistence/unblock export bridge:
  - `summarizeA2ResultPersistence`
  - `summarizeA2ReleaseUnblockChecklist`
  - JSON report fields `a2_result_persistence` and `a2_release_unblock_checklist`
  - Markdown report sections `A2 Result Persistence` and `A2 Release Unblock Checklist`
- Wired dashboard report export to load:
  - `fixtures/a2/results/a2_result_persistence_manifest.json`
  - `fixtures/a2/results/a2_release_unblock_checklist.json`
- Added commercial growth manifest:
  - `services/report/a3_commercial_growth_manifest.mjs`
  - `tests/a3/a3_commercial_growth_manifest.test.mjs`
  - `fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json`
  - `docs/a3/p3_commercial_growth_manifest_2026_07_09.md`
- Added Money-Grade Auditor report:
  - `docs/a3/p3_growth_auditor_money_grade_round2_2026_07_09.md`
- Added implementation notes:
  - `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md`
  - `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`
- Updated `.gitignore` for Node dependencies and transient Playwright output.

Verification:

```text
node --check services/report/report_builder.mjs
node --check apps/dashboard/src/app.mjs
node --check services/report/a3_commercial_growth_manifest.mjs
node --check tests/e2e/static-dashboard-server.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
node --test tests/a3/a3_commercial_growth_manifest.test.mjs
npm.cmd run test:e2e
```

Results so far:

- Report/dashboard contract tests passed: 73 pass, 0 fail.
- Commercial growth manifest tests passed: 5 pass, 0 fail.
- Playwright E2E passed: 4 pass, 0 fail.
- Playwright screenshot rendered and was visually inspected.
- Final pre-commit CL commercial gate passed with 0 blockers.
- Final pre-commit CL hygiene gate passed with no findings.
- Final combined A3 Node tests passed: 78 pass, 0 fail.
- Final `git diff --check` passed.
- Final ignored-file check confirmed `.env.local`, `node_modules/`, and transient Playwright results are ignored.

A1/A2 calibration:

- A1 runner/trace/tool-call semantics were not changed.
- A2 judge/release-gate semantics were not changed.
- A3 now consumes newer A2 result persistence and release unblock checklist artifacts downstream in reports.
- Commercial growth manifest binds growth points to A1/A2/A3 evidence or explicit gaps.

Safety boundary:

- No `.env.local` read.
- No Ashr API key, GitHub token, cookie, email, raw signed URL, or account value committed.
- No live Ashr API call in this round.
- No hosted auth, billing, team, API-key, Trust, database, object storage, or cloud mutation.
- Playwright used local redacted/static fixtures only.

Current interpretation:

This round turns A3 from "dashboard with many panels" toward "testable commercial product surface." The important movement is executable browser proof plus stronger A2 release evidence in exports plus a growth manifest that forces future work to name evidence, contracts, tenant/RBAC/usage/audit impact, and commercial value.

## 2026-07-09 - Commercial Growth Round 3 API-Backed E2E Start

Continued from PR #24 / `codex/a3-commercial-growth-round2`. Opening checks confirmed the local worktree was clean and PR #24 remained clean on GitHub. A retry `git fetch origin` hit a transient GitHub HTTPS reset, so this round avoided rebasing or overwriting remote state and continued from the already pushed A3 branch.

Implemented:

- Mounted the existing A3 API handler inside the Playwright E2E static server:
  - `tests/e2e/static-dashboard-server.mjs`
- Added API-backed browser coverage:
  - `tests/e2e/a3-dashboard-api-backed.spec.ts`
- Added Tailwind product-system contract surface:
  - `tailwind.config.ts`
  - `postcss.config.mjs`
  - `tests/a3/tailwind_boundary_contract.test.mjs`
  - `docs/a3/p3_tailwind_product_system_contract_2026_07_09.md`
- Added Expo mobile client-surface contract:
  - `apps/mobile/package.json`
  - `apps/mobile/app.json`
  - `apps/mobile/src/release-intelligence-contract.ts`
  - `tests/a3/a3_mobile_expo_client_surface.test.mjs`
  - `docs/a3/p3_mobile_expo_client_surface_2026_07_09.md`
- Added WeChat mini program client-surface contract:
  - `apps/wechat-miniprogram/project.config.json`
  - `apps/wechat-miniprogram/pages/release-approval/index.*`
  - `apps/wechat-miniprogram/pages/incident-alert/index.*`
  - `tests/a3/a3_wechat_mini_program_client_surface.test.mjs`
  - `docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md`
- Added Round 3 execution evidence:
  - `docs/a3/p3_commercial_growth_round3_execution_2026_07_09.md`
- Updated Playwright growth notes:
  - `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`

Verification:

```text
node --check tests/e2e/static-dashboard-server.mjs
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
node --test tests/a3/tailwind_boundary_contract.test.mjs tests/a3/a3_wechat_mini_program_client_surface.test.mjs tests/a3/a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
```

Results:

- Static/API E2E server syntax check passed.
- API-backed Playwright E2E passed: 2 pass, 0 fail.
- Client/design-surface contract tests passed: 16 pass, 0 fail.
- Commercial CL passed with 0 blockers and 0 advisories.
- Windows backslash path invocation did not match the Playwright spec; the forward-slash invocation succeeded.

A1/A2 calibration:

- A1 runner, trace, and tool-call semantics were not changed.
- A2 judge, grade, release-gate, and failure taxonomy semantics were not changed.
- API-backed dashboard E2E still requires visible A1 import surfaces, A1 trace references, A2 import surfaces, and A2 judge evidence.

Safety boundary:

- No `.env.local` read.
- No Ashr API key, GitHub token, cookie, email, raw signed URL, or account value read or written.
- No live Ashr API call.
- No live GitHub mutation.
- No real billing, auth, team, API-key, Trust, database, object storage, or cloud mutation.
- Hosted report share/revoke runs only against the local fixture-backed A3 API store.
- One subagent accidentally wrote mobile draft files outside the repository root. Those exact accidental outer-workspace files and empty folders were removed after verifying their absolute paths were outside `ashr-codex-factory`; the correct in-repo mobile contract was kept.

## 2026-07-09 - PR #25 Export Firewall CI Redaction Fix

Fixed the GitHub Actions `A3 dashboard/report/evidence contracts` failure by
removing email-shaped fixture placeholders from the Round 4 evidence document.
The failure was caused by the repository export firewall treating fixture
identity text as an unsafe account value. No runtime code, A1 runner behavior, or
A2 judge semantics changed.

Verification:

```text
node --test tests/a3/export_firewall_generated_artifacts.test.mjs
python scripts\cl_guard.py hygiene
git diff --check
```

Results:

- Export firewall passed.
- Hygiene CL passed with no findings.
- Diff whitespace check passed.

Safety:

- No `.env.local`, Ashr API key, GitHub token, cookie, real account value, raw
  signed URL, or payment secret was read or committed.

## 2026-07-09 - Commercial API Contract and Evidence Coverage Round

Continued A3 toward the large SaaS strategy bus with a new commercial API
contract round. This round adds `a3.commercial_api_contract.v1`, exposes it from
`GET /api/a3/commercial-api/contract`, records the future DB table
`commercial_api_contracts`, and generates
`fixtures/a3/p3/a3_commercial_api_contract.redacted.json`.

The contract maps 29 commercial `/v1` endpoints into A3-owned product surfaces:
product console, release gate, review workflow, report center, artifact
registry, usage/billing, admin console, and audit export. Every endpoint names
owner lane, local A3 route, RBAC requirement, DB tables, events, artifacts, usage
meters, and A1/A2 dependencies.

Parallel agent outputs integrated into this round:

- `fixtures/a3/p3/a3_commercial_evidence_coverage.redacted.json`
- `docs/a3/p3_commercial_evidence_coverage_2026_07_09.md`
- `tests/a3/a3_commercial_evidence_coverage.test.mjs`
- `tests/a3/a1_a2_compatibility_contract.test.mjs`
- `services/report/a3_security_redaction_guard.mjs`
- `tests/a3/a3_security_redaction_guard.test.mjs`
- `docs/a3/p3_growth_auditor_money_grade_round6_2026_07_09.md`

A1/A2 boundary:

- A3 does not mutate A1 runner, SDK, auth, usage, billing, artifact, or API
  gateway semantics.
- A3 does not change A2 judge scores, pass/fail, release policies, thresholds,
  failure classes, or verifier semantics.
- A3 remains downstream: it turns A1/A2 evidence into product workflow, report,
  review, audit, usage/billing preview, and commercial readiness evidence.

Safety:

- No `.env.local` read.
- No API key, token, cookie, real account value, raw signed URL, or payment
  secret written.
- No live Ashr, GitHub, billing, auth, or cloud mutation performed.

Publish note:

- Local git HTTPS push was unavailable during this round, so the already-tested
  A3 commit was published through the GitHub Git Data API with a fast-forward
  parent and redacted file set only. No secret-bearing files were included.

## 2026-07-09 - Commercial SaaS Contract Round 7: OpenAPI, Tenant Scope, Event Envelope, Source Artifacts

Continued from latest `origin/main` after the group lead refreshed main with
latest A1/README sync work. This round followed
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` and focused on making A3 less
like a dashboard-only demo and more like a commercial SaaS contract consumer.

Twenty growth points considered and advanced:

1. OpenAPI artifact for A3 commercial API surfaces.
2. Tenant scope helper with organization/tenant/workspace/project/environment.
3. Metadata-only event envelope builder.
4. Future `event_outbox` SQL contract.
5. A1 RunResult source artifact hash.
6. A1 trace event batch source artifact hash.
7. A1 tool-call batch source artifact hash.
8. A2 GradeResult source artifact hash.
9. A2 ReleaseGate source artifact hash.
10. Source artifacts in release evidence v2.
11. Source artifacts in artifact registry.
12. Source artifacts in API-backed dashboard payload.
13. Commercial API fixture refresh after tenant/workspace fields.
14. Commercial API docs update for event outbox and source artifacts.
15. OpenAPI test for tenant/auth/RBAC/usage/audit notes.
16. Tenant/event/source-artifact unit tests.
17. A1/A2 live alignment documentation.
18. Growth-Auditor Money-Grade Round 7.
19. Full A3 Node contract test run.
20. Commercial and hygiene CL guard run.

Implemented:

- Added `services/report/a3_tenant_scope.mjs`.
- Added `services/report/a3_event_envelope.mjs`.
- Added `services/report/a3_source_artifacts.mjs`.
- Added `docs/a3/openapi/a3_commercial_api.openapi.json`.
- Added `tests/a3/a3_commercial_openapi_contract.test.mjs`.
- Added `tests/a3/a3_tenant_event_source_artifact_contract.test.mjs`.
- Updated `a3.commercial_api_contract.v1` with `tenant_id`, `workspace_id`,
  `environment_id`, event outbox notes, and refreshed redacted fixture.
- Updated `a3.release_evidence_summary.v2` so source artifact hashes travel with
  release evidence without embedding raw A1/A2 payloads.
- Updated Artifact Registry so it can include A1/A2 source evidence entries.
- Updated SQL migration contract with `source_artifacts` and `event_outbox`.
- Added Integration-Agent output:
  - `docs/a3/p3_a1_a2_live_alignment_2026_07_09.md`
- Added Growth-Auditor output:
  - `docs/a3/p3_growth_auditor_money_grade_round7_2026_07_09.md`

A1/A2 calibration:

- A1 remains source of truth for RunResult, TraceEvent, Observation, ToolCall,
  tenant/auth/API gateway, durable usage, artifact storage, and event
  publication.
- A2 remains source of truth for Scenario, GradeResult, Judge, ReleaseGate,
  failure taxonomy, policy, and verifier semantics.
- A3 now records source artifact ids, counts, source contracts, and SHA-256
  hashes so dashboard/report/release evidence can prove which A1/A2 evidence it
  consumed without changing that evidence.

API / DB / Event / Artifact contract:

- API docs: `docs/a3/openapi/a3_commercial_api.openapi.json`.
- DB: `commercial_api_contracts`, `source_artifacts`, `event_outbox`.
- Event: `services/report/a3_event_envelope.mjs` models
  `ashr.event_envelope.v1`; durable event outbox remains future backend work.
- Artifact: source artifact hash summaries for A1/A2 evidence are now carried by
  release evidence v2 and artifact registry.

Tenant/auth/RBAC/usage/audit:

- Tenant fields now preserve `organization_id`, `tenant_id`, `workspace_id`,
  `project_id`, and `environment_id`.
- Auth/RBAC live enforcement remains blocked until A1 hosted auth/RBAC exists.
- Usage remains read-only and downstream of the A1 usage ledger.
- Audit events and source artifacts are metadata/hash only; no raw payloads are
  embedded.

Verification:

```text
node --check services\report\a3_tenant_scope.mjs
node --check services\report\a3_event_envelope.mjs
node --check services\report\a3_source_artifacts.mjs
node --check services\report\a3_store.mjs
node --check services\report\a3_release_evidence.mjs
node --check services\report\a3_artifact_registry.mjs
node --test tests\a3\a3_tenant_event_source_artifact_contract.test.mjs tests\a3\a3_release_evidence.test.mjs tests\a3\artifact_registry.test.mjs tests\a3\a3_commercial_api_contract.test.mjs tests\a3\a3_commercial_openapi_contract.test.mjs
node --test tests\a3\*.mjs
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git diff --check -- services/report tests/a3 docs/a3/openapi docs/a3/p3_commercial_api_contract_2026_07_09.md fixtures/a3/p3/a3_commercial_api_contract.redacted.json
```

Results:

- Focused tenant/event/source-artifact/OpenAPI tests passed: 19 pass, 0 fail.
- Full A3 Node tests passed: 229 pass, 0 fail.
- Commercial CL passed: 0 blockers, 0 advisories.
- Hygiene CL passed with no findings.
- Diff whitespace check passed for touched A3 files.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No real auth, billing, team, API-key, Trust, object-storage, branch
  protection, or cloud mutation.
- No API key, token, cookie, real account value, email, raw signed URL, or
  payment secret was written.

## 2026-07-09 - Auth/RBAC Boundary Spine Round

Goal: answer Contract-Agent and Bus-Auditor feedback that A3 had auth/RBAC
claims in OpenAPI/docs but needed a concrete local actor context and
authorization decision contract.

Implemented:

- `services/report/a3_auth_rbac_boundary.mjs`
- `a3.auth_context.v1`
- `a3.rbac_policy.v1`
- `a3.authz_decision.v1`
- API routes:
  - `GET /api/a3/auth/context`
  - `GET /api/a3/auth/rbac-policy`
  - `POST /api/a3/auth/authorize`
- SaaS Admin Console `auth_boundary` state.
- Dashboard Auth/RBAC Boundary panel inside SaaS Admin.
- SaaS Admin export `auth_boundary` summary.
- Artifact Registry `auth_rbac_boundary` evidence.
- SQL contract tables:
  - `auth_contexts`
  - `rbac_policy_snapshots`
  - `authz_decisions`
- OpenAPI paths and schemas for Auth/RBAC boundary.
- Documentation:
  - `docs/a3/p3_auth_rbac_boundary_2026_07_09.md`
- Tests:
  - `tests/a3/a3_auth_rbac_boundary.test.mjs`

A1/A2 calibration:

- A1 remains owner of hosted auth, sessions, API keys, RBAC enforcement, tenant
  isolation, audit, usage, and API gateway.
- A2 remains owner of security verification, abuse cases, release policy,
  redaction, and verifier correctness.
- A3 only models local product-workflow authorization and denied states.

Verification:

```text
node --test tests/a3/a3_auth_rbac_boundary.test.mjs tests/a3/a3_saas_admin.test.mjs tests/a3/artifact_registry.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_commercial_openapi_contract.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs
```

Final verification result:

- Focused Auth/RBAC round: 22 pass, 0 fail.
- Full A3 Node suite: 234 pass, 0 fail.
- Playwright E2E: 9 pass, 0 fail.
- Commercial CL: passed, 0 blockers, 0 advisories.
- Hygiene CL: passed, no findings.
- `git diff --check`: passed.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No real hosted auth, team invite, API-key rotation, billing, Trust publish, or
  cloud mutation.
- Actor identity is represented as `actor_hash`; raw email/token/cookie/key
  values are not returned.

## 2026-07-09 - Peer Branch and Live Workflow Readiness Round

Goal: consume A1/A2 peer-branch contract changes before merge and turn the team
lead's next six commercial workflow items into a visible A3 readiness contract.

Implemented:

- `a3.peer_branch_calibration.v1`
- `GET /api/a3/peer-branches/calibration`
- dashboard `Peer Branch Calibration`
- source-artifact hash row `a3_peer_branch_calibration`
- `a3.live_workflow_readiness.v1`
- `GET /api/a3/live-workflow/readiness`
- dashboard `Live Workflow Readiness`
- static and API-backed dashboard wiring
- docs:
  - `docs/a3/p3_growth_auditor_peer_branch_calibration_2026_07_09.md`
  - `docs/a3/p3_live_workflow_readiness_2026_07_09.md`

The live readiness contract covers:

- GitHub PR check live publishing
- PR comment live publishing
- reviewer approve / deny / waiver workflow
- dashboard human operation records
- billing/admin read-only usage and billing state
- hosted report share-link revoke, expiry, and audit lifecycle

A1/A2 calibration:

- A1 remains owner of runner, auth, API gateway, usage ledger, billing provider,
  quota enforcement, and live GitHub/CI credentials.
- A2 remains owner of judge semantics, score/pass/fail, release policy, failure
  taxonomy, and security verification.
- A3 consumes A1/A2 outputs and peer deltas as downstream dashboard/report/API
  evidence only.

Verification:

```text
node --test tests\a3\a3_live_workflow_readiness.test.mjs tests\a3\a3_api_server.test.mjs tests\a3\dashboard_wiring.test.mjs tests\a3\a3_peer_branch_calibration.test.mjs tests\a3\a3_tenant_event_source_artifact_contract.test.mjs
```

Result:

- Focused round: 45 pass, 0 fail.
- Full A3 Node suite: 249 pass, 0 fail.
- Playwright E2E: 9 pass, 0 fail.
- Commercial CL: passed, 0 blockers, 0 advisories.
- Hygiene CL: passed, no findings.
- `git diff --check`: passed.
- `.env.local`, `node_modules`, and Playwright result artifacts remain ignored.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No billing provider call.
- No hosted auth, team invite, API-key mutation, Trust publish, branch
  protection mutation, or cloud write.
- No raw key, token, cookie, email, account value, signed URL, local path, or
  payment secret was written.

## 2026-07-09 - Live Ops Control Plane Round

Goal: turn the six next SaaS workflow asks into one A3 product-console contract
with API, DB, event, audit, dashboard, and A1/A2 dependency visibility.

Implemented:

- `a3.live_ops_control_plane.v1`
- `GET /api/a3/live-ops/control-plane`
- dashboard `Live Ops Control Plane`
- static and API-backed dashboard wiring
- redacted fixture:
  - `fixtures/a3/p3/a3_live_ops_control_plane.redacted.json`
- docs:
  - `docs/a3/p3_live_ops_control_plane_2026_07_09.md`

The control plane covers:

- GitHub PR check live publishing
- PR comment live publishing
- reviewer approve / deny / waiver workflow
- dashboard human operation records
- billing/admin read-only usage and billing state
- report share-link revoke, expiry, and audit lifecycle

A1/A2 calibration:

- A1 remains owner of hosted workers, GitHub credentials, usage events,
  billing ledger migrations, provider webhooks, auth/RBAC, and production DB
  persistence.
- A2 remains owner of judge semantics, score/pass/fail, release policy, failure
  taxonomy, and security verification.
- A3 maps those outputs to product workflow state and does not mutate A1/A2
  source semantics.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No billing provider call.
- No hosted auth, team invite, API-key mutation, Trust publish, branch
  protection mutation, or cloud write.
- No raw key, token, cookie, email, account value, signed URL, local path, or
  payment secret was written.

Verification:

- Focused Node: 43 pass, 0 fail.
- Full A3 Node suite: 254 pass, 0 fail.
- Playwright E2E: 9 pass, 0 fail.
- Commercial CL: passed, 0 blockers, 0 advisories.
- Hygiene CL: passed.
- `git diff --check`: passed.
- `.env.local`, `node_modules`, and Playwright result artifacts remain ignored.

## 2026-07-09 - Live Publish / Review / Billing / Share Closeout

Goal: verify and document the latest A3 implementation pass for the six SaaS
workflow asks:

1. GitHub PR check live publishing.
2. PR comment live publishing.
3. Reviewer approve / deny / waiver workflow.
4. Dashboard-visible human operation records.
5. Billing/admin reads usage and billing state.
6. Report share link revoke, expiry, and audit lifecycle.

Completed:

- Confirmed local A3 API routes for GitHub check and PR comment publishing.
- Confirmed GitHub publish defaults to dry-run and live mode is gated by hosted
  session or service-account context.
- Confirmed reviewer waiver, approval, and denial routes write sanitized local
  receipts, audit events, and event-outbox rows.
- Confirmed dashboard/report payloads expose `github_publish_receipts`,
  `review_workflow_records`, `saas_admin_action_requests`, `audit_events`, and
  event-outbox summaries as human operation evidence.
- Confirmed usage/billing/admin read routes stay read-only and downstream of
  A1 billing/usage ownership.
- Confirmed hosted report links support create, view, revoke, expiry, denied
  access, and audit records without exposing raw share tokens.
- Added closeout doc:
  - `docs/a3/p3_live_publish_review_billing_share_closeout_2026_07_09.md`

A1/A2 calibration:

- A1 owns hosted auth, service accounts, GitHub credentials/workers, production
  DB persistence, durable usage events, billing ledger, provider webhooks, and
  runner outputs.
- A2 owns score, pass/fail, release policy, failure taxonomy, security
  verification, and judge semantics.
- A3 only presents workflow, review, report, billing-readiness, and audit
  state derived from those sources.

Verification:

- `node --check services/report/a3_store.mjs`
- `node --check services/report/a3_api_server.mjs`
- `node --check services/report/a3_auth_rbac_boundary.mjs`
- `node --check apps/dashboard/src/app.mjs`
- `node --test tests/a3/*.mjs`
- `npm.cmd run test:e2e`

Results:

- Full A3 Node suite: 260 pass, 0 fail.
- Playwright E2E: 10 pass, 0 fail.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub API call.
- No billing provider call.
- No hosted auth, team invite, API-key mutation, Trust publish, branch
  protection mutation, or cloud write.
- No raw key, token, cookie, email, account value, signed URL, local path,
  payment secret, or raw share token was written.

## 2026-07-09 - Notification Control Plane Implementation

Goal: implement the next A3 commercial workflow layer for Slack, Teams, email,
and customer webhook notification readiness without performing real external
sends.

Completed:

- Implemented `a3.notification_control_plane.v1` with four lanes:
  - Slack release/reviewer notifications.
  - Microsoft Teams release/reviewer notifications.
  - Email digest/escalation notifications.
  - Customer webhook notifications.
- Exposed `GET /api/a3/notifications/control-plane` from the A3 API store and
  server.
- Added dashboard rendering and navigation for `Notification Control Plane`.
- Added notification summary to report exports and report-center tiles.
- Added artifact registry coverage:
  - `notification_control_plane`
  - `notification_readiness_packet`
  - security audit packet inclusion.
- Added SQL migration contract for notification channel, subscription,
  template, delivery, and webhook delivery metadata tables.
- Added commercial API contract endpoints and regenerated
  `fixtures/a3/p3/a3_commercial_api_contract.redacted.json`.
- Added RBAC boundary coverage for `notifications:read`.
- Added notification secret-leak detection and tests proving that raw Slack,
  Teams, email, webhook, token, cookie, key, and account-like values are not
  echoed.

A1/A2 calibration:

- A1 remains owner of hosted notification workers, encrypted connector
  references, delivery retry/dead-letter behavior, event outbox durability, and
  usage ledger writes.
- A2 remains owner of which release-policy/failure-taxonomy/security events are
  notify-worthy and whether notification payloads are safely redacted.
- A3 remains downstream-only and does not mutate A1 runner outputs, A1 billing
  facts, A2 score/pass-fail/failure-class, or A2 release policy semantics.

Verification:

- `node --check services/report/a3_notification_control_plane.mjs`
- `node --check services/report/a3_auth_rbac_boundary.mjs`
- `node --check services/report/a3_store.mjs`
- `node --check services/report/a3_api_server.mjs`
- `node --check services/report/report_builder.mjs`
- `node --check apps/dashboard/src/app.mjs`
- `node --test tests/a3/a3_notification_control_plane.test.mjs tests/a3/a3_live_ops_control_plane.test.mjs tests/a3/a3_live_workflow_readiness.test.mjs tests/a3/a3_auth_rbac_boundary.test.mjs`
- `node --test tests/a3/artifact_registry.test.mjs tests/a3/a3_commercial_api_contract.test.mjs tests/a3/a3_commercial_openapi_contract.test.mjs`
- `node --test tests/a3/*.mjs`
- `npm.cmd run test:e2e`
- `python scripts/cl_guard.py commercial`
- `python scripts/cl_guard.py hygiene`
- `git diff --check`

Results:

- Focused notification/live workflow/RBAC tests: 10 pass, 0 fail.
- Focused artifact/commercial contract tests: 12 pass, 0 fail.
- Full A3 Node suite: 262 pass, 0 fail.
- Playwright E2E: 10 pass, 0 fail.
- Commercial CL: passed.
- Hygiene CL: passed.
- Diff check: passed.

Safety boundary:

- No `.env.local` read.
- No live Ashr API call.
- No live GitHub, Slack, Teams, email, webhook, billing provider, or cloud
  mutation.
- No raw key, token, cookie, email, account value, signed URL, local path,
  payment secret, raw webhook URL, connector secret, or raw share token was
  written.

## 2026-07-11 - API Reference And Identity Contract Calibration

- Fetched current main and read latest A1/A2 remote branches without merging
  either peer branch.
- Calibrated A1 Google/GitHub OAuth, unified identity, email verification,
  anti-enumeration response, SMTP, and callback contracts at `ac960bd`.
- Calibrated A2 identity/security context at `58fe876` while preserving A2
  score, pass/fail, failure-class, and release-policy authority.
- Added route-level API Reference, OAuth start adapters, email challenge
  request, fail-closed verification UX, and transactional email templates.
- Recorded the challenge-context and callback-session blockers instead of
  claiming production registration/login.
- Passed 334 A3 Node tests, 31 Playwright tests, 562 current-main A1/A2 Python
  tests plus 1013 subtests, both CL guards, build, audit, and secret scan.
- No live provider, SMTP, OAuth, email, account, or secret-bearing operation was
  executed.

## 2026-07-11 - A1/A2 Draft Identity And Trusted-Spine Alignment

- Re-fetched `origin/main`, A1, and A2; current main remains `5dbf4ee`, while
  A1 advanced to `c784163` and A2 advanced to `47c05e5`.
- Corrected the A3 product claim: Google/GitHub currently support authenticated
  account linking, not initial OAuth sign-in.
- Added the A1 browser-session refresh contract and A2 trusted evidence and
  append-only decision schemas to the product API Reference.
- Kept the A3 login controls fail-closed and preserved A1 identity/session and
  A2 grade/release authority.
- Verified A3 (`334` Node, `31` Playwright), current-main A1/A2 (`562` Python
  plus `1013` subtests), latest A1 draft Go/TypeScript (`574` TypeScript tests),
  and latest A2 trusted spine (`11` tests plus `29` subtests).
- The draft-only A1 Rust verifier was not run because Cargo is unavailable; it
  is not consumed by this A3 change.
- No key, token, cookie, OTP, email, account payload, provider request, or cloud
  mutation entered this calibration.

## 2026-07-12 - Merged-main Identity And Trusted-Spine Recalibration

- Confirmed current `main` `ccf6ce5` contains A1 `c784163` and A2 `8cd1d4f`
  through integration commit `7dd14d7`.
- Used an official temporary latest-main archive for compatibility testing
  while standard Git HTTPS remained unavailable; no third-party proxy was
  used.
- Replaced stale open-draft labels with merged-main implementation state for
  A1 account linking, email challenge start, callback, and session refresh.
- Re-read the unified strategy merged at `ccf6ce5`: Ashr is now an optional
  calibration provider, while the internal A1/A2/A3 enterprise Release path
  must remain provider-neutral and runnable without Ashr.
- Inspected A2 peer ref `2a87e16` as a non-authoritative watch signal for
  durable provider reconciliation; it was not consumed before entering main.
- Preserved honest product blockers: initial Google/GitHub login is still
  unavailable, browser email completion still lacks mailbox-bound challenge
  context, and A2 still reports `release_ready=false` with decision `block`.
- Upgraded the redacted A3 auth snapshot to v3 and recorded A2's five required
  scope fields, `scope_complete`, `validation_errors`, and direct A1 RunResult
  validation.
- Current-main checks passed: A3 Node `334/334`, A2 `186/186` plus `1050`
  subtests, focused auth/Webapp `9/9`, trusted spine `7/7`, Next.js production
  build, and full Playwright `31/31` including Webapp routes `6/6`.
- A broad Python run additionally reached `1230` passes before environment-only
  Docker/Postgres, Go, Cargo, and archive-without-`.git` gaps; none are claimed
  as green.
- No Ashr key, OAuth token, cookie, OTP, email, account data, provider payload,
  or cloud mutation was used in this recalibration.

## 2026-07-12 - Request Boundary Recalibration

- Re-fetched current `main` `ccf6ce5` and re-read current A1 identity plus A2
  Evidence Snapshot / Decision Ledger contracts before changing A3.
- Added a provider-neutral protected request boundary; no Ashr API call or key
  was needed for this security pass.
- Preserved A1 as principal/session authority and A2 as Release Decision
  authority while adding sanitized `400/408/413/415/422`, protected OPTIONS
  authorization, and metadata-only request-body-state audit in A3.
- Current verification passed: A3 Node `397/397`, Playwright `35/35`, A1
  TypeScript session lifecycle `35/35`, A2 trusted spine `7/7`, Next.js build,
  commercial CL, and hygiene CL.
- No API key, token, cookie, email, signed URL, raw body, or account identity
  was persisted in docs, fixtures, events, screenshots, or Git state.
- Detailed evidence:
  `docs/a3/a3_request_boundary_audit_2026_07_12.md` and
  `docs/a3/growth_auditor_money_grade_round12_2026_07_12.md`.

## 2026-07-12 - Real GitHub and Release Delivery Preparation

- Added one read-only GitHub observation path and kept direct live token publishing disabled.
- Created a fresh A1 run and A2 judge result for release-delivery calibration; no Ashr API key or real customer data was used.
- Built a run-specific Audit Bundle, signed archive, Release Artifact, Deployment Acceptance, and Golden Path packet.
- Current GitHub facts are explicit: PR #35 CI is green for the previous head, `main` branch protection is absent, and no tenant custom GitHub App installation is proven.
- The first packet intentionally treats the old confirmed fixtures as contract evidence. A later readback pass will replace them with real `github.com` receipts tied to the candidate commit.
- Pre-publish local gates passed for all A3/A2 checks that this environment can execute: A3 Node `405/405`, A2 `186/186` plus `1050` subtests, Next.js 15-page production build, Playwright `11/11`, both CL guards, both npm audits, YAML/JSON parsing, redacted evidence scanning, and diff hygiene.
- A1 compatibility was also exercised broadly (`1232` Python passes and `573` TypeScript SDK passes). Docker/PostgreSQL, Go, and Cargo-dependent tests remain explicitly environment-blocked rather than being weakened, skipped by code changes, or reported as passed.
- First live GitHub publish succeeded for candidate `01f8707`: workflow `29190601539`, release-artifact Check `86644503081`, and Actions artifact `8259384802` all completed successfully. The artifact was downloaded and its embedded Release Artifact verification remained `passed` while the Golden Path correctly remained `blocked_by_a2`.
- A pull-request SHA calibration issue was found from that real evidence and fixed: the release packet now distinguishes candidate head from the CI-tested synthetic merge commit.
- Corrected run `29190953806` produced artifact `8259493055`; the downloaded packet independently records candidate `ad6113e`, tested merge `e07c5f6`, a passing embedded manifest verification, and `production_release=false`.
- Real Check and operator PR-comment readbacks now confirm ID/name/conclusion/head plus marker/body-hash/head respectively. The live branch-policy readback remains missing (HTTP 404), and custom tenant GitHub App proof remains false.
- Resealed output now reports Golden Path `7/11`, Deployment Acceptance `8/17`, Audit Bundle `14/14`, custody `7/7`, and archive `15/15` while preserving the A2 `block` decision.
- Final post-readback gates passed: A3 Node `406/406`, A2 `186/186` plus `1050` subtests, Next.js 15-page build, Playwright `11/11`, CL, audits, YAML/JSON, secret/path, and diff checks.
- CI now verifies and uploads the immutable `ad6113e` candidate packet instead of regenerating it from a later evidence commit; standalone Release Artifact verification is available through `--verify-manifest`.
- The first Linux sealed-packet verification correctly caught a Windows CRLF versus Git LF byte mismatch in the generated A2 grade fixture. The fixture was normalized to the existing repository LF policy and the full hash/signature chain was resealed; no verifier rule was weakened.
- No key, token, cookie, email, installation token, private signing key, or raw GitHub response was persisted.

## 2026-07-13 - Live GitHub Deployment Resolver Calibration

- Extended the read-only GitHub observer with repository installation identity readback.
- Added server-fixed GitHub resolver implementations for `github_app_installation` and `required_check_enforcement`.
- Required A1 tenant-installation binding for GitHub App proof and separate hash-valid failing-merge plus maintainer receipts for required-check proof.
- Read PR #35 head Check `86746616300`: HTTP 200, exact head/name/conclusion, App slug `github-actions`.
- Read repository installation: HTTP 401 permission denied. This does not prove absence; it proves the current OAuth identity cannot establish repository binding.
- Read main required status checks: HTTP 404 and `enforced=false`.
- Saved three sanitized provider fixtures and one post-seal calibration summary under `fixtures/a3/p3`.
- Proved through the internal HTTP verify route that provider mismatch becomes a persisted trusted rejection while Deployment Acceptance remains `8/17` and production verified receipts remain `0`.
- No GitHub mutation, merge attempt, branch-protection update, token output, A2 recomputation, or sealed rc.2 rewrite occurred.
- Final verification passed A3 Node `449/449`, merged-main A2 `186/186` plus `1050` subtests, Next.js typecheck/build with 15 static pages, the full Playwright command plus an isolated `1/1` visual retry, both CL guards, both production npm audits, pinned evidence, and all sealed rc.2 verifiers.
- Post-verification fetch kept main at `ccf6ce5` and A1 Draft at `2307231`; A2 development moved to `d31aaab`. Its new multimodal/provider/persistence schemas remain non-authoritative calibration and explicitly do not supply the same-candidate Trusted Spine A3 needs.

## 2026-07-13 - A1 Self-host Sandbox Calibration

- Executed four real local A1 behaviors and generated a sanitized `sandbox_verified` fixture.
- Added Store/SQLite/API/RBAC/OpenAPI/API Reference and Delivery UI integration.
- Kept production proof, Deployment Acceptance mutation, and A2 recomputation false.
- Focused Python, Node, TypeScript, production build, and Playwright checks passed.
- Final local regression passed A3 Node `458/458`, current-main A2 `186/186` plus `1050` subtests, Next.js typecheck/build with 15 static pages, and Playwright `40/40`.
- Both CL guards passed, both production npm audits found 0 vulnerabilities, and the sealed rc.2 bundle/archive/Release Artifact reverified without mutation.
- Remote CI status is tracked in `docs/a3/worklog.md` after publish.
