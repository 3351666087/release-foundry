# A3 Worklog

## 2026-07-09 - Commercial Growth Round 4 API-Backed Governance E2E

### Goal

Continue A3 from latest `origin/main` and follow
`docs/strategy/large-saas-a1-a2-a3-full-plan.md` by strengthening the browser
proof around SaaS Admin, reviewer governance, and hosted report access control.

### Work completed

- Extended `tests/e2e/a3-dashboard-api-backed.spec.ts`.
- Added SaaS Admin guardrail browser coverage:
  - action selection
  - plan-only copy
  - `POST /api/a3/admin/actions/submit`
  - local request receipt
  - no real cloud mutation
  - no fixture email leakage in the rendered admin panel
- Added reviewer governance browser coverage:
  - waiver receipt through `POST /api/a3/review/waivers`
  - approval receipt through `POST /api/a3/review/approvals`
  - durable record rendering after dashboard reload
  - `hash_sealed` review custody evidence
- Added hosted report denied-state browser coverage:
  - active share link renders report body
  - revoked share link returns 410 and hides Case Evidence / Expected / Actual
  - missing share link returns 404 and hides report body evidence
- Added Round 4 evidence doc:
  - `docs/a3/p3_commercial_growth_round4_e2e_review_admin_denied_2026_07_09.md`
- Updated:
  - `docs/a3/p3_playwright_e2e_growth_2026_07_09.md`
  - `docs/a3/p3_worklog.md`
  - `docs/a3/acceptance_checklist.md`

### A1/A2 compatibility

- A1 runner, trace, observation, and tool-call contracts were not changed.
- A2 judge, score, pass/fail, release-gate, and failure taxonomy contracts were
  not changed.
- The new E2E coverage proves A3 governance around A1/A2 evidence. It does not
  replace A1 RunResult proof or A2 GradeResult proof.

### Verification

```text
node --check tests\e2e\a3-dashboard-api-backed.spec.ts
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
npm.cmd run test:e2e
node --test tests\a3\report_builder.test.mjs tests\a3\dashboard_wiring.test.mjs tests\a3\a3_commercial_growth_manifest.test.mjs tests\a3\tailwind_boundary_contract.test.mjs tests\a3\a3_wechat_mini_program_client_surface.test.mjs tests\a3\a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
python scripts\cl_guard.py hygiene
git diff --check
git check-ignore -v .env.local node_modules docs\screenshots\playwright-results
```

Result:

- API-backed E2E: 5 passed, 0 failed.
- Full E2E: 9 passed, 0 failed.
- Focused A3 contract tests: 94 passed, 0 failed.
- Commercial CL: passed, 0 blockers, 0 advisories.
- Hygiene CL: passed, no findings.
- `.env.local`, `node_modules/`, and transient Playwright output remain ignored.

### Safety boundary

- No `.env.local` was read.
- No Ashr API key, GitHub token, cookie, real email, raw signed URL, or private
  credential was read or committed.
- No live Ashr API call, live GitHub mutation, billing mutation, real auth/team
  operation, API-key creation, Trust publishing, database, object-storage, or
  cloud mutation was performed.
- SaaS Admin remains a safe local guardrail/request-recording surface.

### Current interpretation

A3 is now stronger at the "commercial product proof" layer: it can show browser
evidence for admin guardrails, reviewer exception approval records, and
fail-closed hosted report access. The next real commercial jumps are hosted
auth/RBAC, production Postgres/RLS, live GitHub readback, and object-storage
evidence custody.

## 2026-07-08 - Release Evidence Authority Guardrails

### Goal

Continue the A3 commercial-SaaS push after API-backed release evidence landed. This round makes the release evidence path more authoritative by adding health/next-action/diff helpers and tightening tenant/error safety around the API, Report Center, hosted snapshots, and SQLite persistence.

### 26 Growth Points Considered

1. Release evidence health object.
2. Deterministic next-action engine.
3. Evidence summary diff.
4. Tenant-scoped release evidence API reads.
5. Tenant-scoped hosted report snapshot listing.
6. Tenant-scoped Report Center report aggregation.
7. Tenant-scoped Artifact Registry report aggregation.
8. Tenant-scoped Product Console report evidence.
9. SQLite report tenant persistence.
10. API internal error redaction.
11. Immutable hosted snapshot proof.
12. GitHub Check readback.
13. PR comment readback.
14. Required-check enforcement proof.
15. Review identity binding.
16. Redaction fail-closed external publish policy.
17. Usage ledger summary-id linkage.
18. Offline verifier packet.
19. Webhook contract.
20. Playwright visual evidence.
21. API docs and v2 handoff.
22. Billing/usage evidence.
23. Enterprise retention/legal-hold evidence.
24. War Room health integration.
25. Backward compatibility guard.
26. Postgres migration hardening.

Implemented this round: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, and 21 as local A3-safe changes. Follow-up in the same round also added report-id scope guards for detail, manifest, view, revoke, and list routes.

### Work completed

- Added `services/report/a3_release_evidence.mjs`.
  - `buildReleaseEvidenceHealth(...)`
  - `computeReleaseEvidenceNextAction(...)`
  - `diffReleaseEvidenceSummaries(...)`
- Added `tests/a3/a3_release_evidence.test.mjs`.
- Added release evidence health and next action into `GET /api/a3/releases/:releaseId/evidence-summary`.
- Added tenant/project guard for release evidence API reads.
- Added tenant/project filtering for hosted report snapshots in the release evidence API response.
- Added scoped report filtering for Dashboard, Report Center, Artifact Registry, Product Console, and usage-ledger inputs.
- Added tenant/project scope guards for report detail, manifest, view, revoke, and report-list reads.
- Fixed SQLite report persistence to store `tenant_scope.organization_id` and `tenant_scope.project_id` instead of defaulting reports to `org-local`.
- Added API internal-error redaction so unexpected errors cannot echo Bearer tokens, Ashr key assignments, cookies, or emails.
- Added next-round authority handoff:
  - `docs/a3/p3_release_evidence_authority_round_2026_07_08.md`

### A1/A2 compatibility

- A1 runner, SDK, trace, observation, and tool-call semantics were not modified.
- A2 judge, score, pass/fail, failure taxonomy, and policy semantics were not modified.
- This round stays in A3's product/report/API/store boundary and packages downstream evidence only.

### Verification

```text
node --check services/report/a3_release_evidence.mjs
node --check services/report/a3_store.mjs
node --check services/report/a3_api_server.mjs
node --check services/report/a3_sqlite_store.mjs
node --test tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/shareable_report.test.mjs tests/a3/report_center_index.test.mjs tests/a3/artifact_registry.test.mjs
node --test tests/a3/a3_sqlite_store.test.mjs
```

Current focused result before full-suite closeout:

```text
release-evidence/API/store/report-center/SQLite focused: 20 pass, 0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, or cloud mutation APIs.
- Did not write API keys, tokens, cookies, emails, private keys, live signed URLs, or account values.
- Added API error redaction for unexpected internal exceptions.

## 2026-07-08 - API-backed release evidence summary

### Goal

Continue A3 under `docs/strategy/large-saas-a1-a2-a3-full-plan.md` and move release evidence from a static display into the A3 API/store/hosted-report path.

### Work completed

- Loaded existing redacted release evidence fixtures at the A3 store boundary.
- Added sanitized release evidence summary output to `/api/a3/dashboard`.
- Added release evidence API response support for `GET /api/a3/releases/:releaseId/evidence-summary`.
- Added immutable hosted report release evidence snapshots.
- Added Release Evidence rendering to active hosted report HTML.
- Kept denied hosted report pages body-free for revoked, expired, blocked, or missing links.
- Added release evidence readiness to Report Center summaries and manifests.
- Added `release_evidence_summary` as a first-class Artifact Registry report artifact.
- Added `release_evidence_summaries` to the SQL migration contract.
- Persisted release evidence summary rows in the SQLite-backed A3 store.
- Added docs artifact:
  - `docs/a3/p3_api_backed_release_evidence_2026_07_08.md`

### A1/A2 compatibility

- A1 runner, trace, tool-call, and SDK semantics were not modified.
- A2 judge, score, pass/fail, and failure taxonomy semantics were not modified.
- Release evidence stays downstream of A1/A2 output and only packages A3 delivery evidence.

### Verification

```text
node --check services/report/a3_store.mjs
node --check services/report/a3_shareable_report.mjs
node --check services/report/a3_api_server.mjs
node --check services/report/a3_sqlite_store.mjs
node --check services/report/a3_sql_migrations.mjs
node --test tests/a3/a3_store.test.mjs tests/a3/shareable_report.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/report_center_index.test.mjs tests/a3/report_center_manifest_contract.test.mjs tests/a3/artifact_registry.test.mjs
node --test --test-concurrency=1 (rg --files tests/a3 -g "*.test.mjs")
git diff --check
```

Result:

```text
Focused: 20 pass, 0 fail
Full A3 single-threaded: 167 pass, 0 fail
diff --check: no whitespace errors; Windows LF/CRLF warnings only
```

### Safety boundary

- Did not read or print `.env.local`.
- Confirmed `.env.local` is ignored.
- Did not call live Ashr, GitHub, billing, hosted auth, or cloud mutation APIs.
- Did not commit API keys, tokens, cookies, emails, raw share tokens, private keys, live signed URLs, or raw account values.
- Secret scan matches were limited to intentional redaction-test strings in A3 tests.
- GitHub publish evidence remains dry-run or locally redacted unless a future maintainer-approved live round is run.

## 2026-07-08 - Release Evidence Display In Dashboard And Reports

### Goal

Continue A3 against `docs/strategy/large-saas-a1-a2-a3-full-plan.md` after the group lead updated `main`. This round moves GitHub publish evidence, audit bundle verification, and signed archive verification out of hidden fixture/CLI evidence and into the customer-facing Dashboard, Report Center, JSON export, Markdown export, and print-ready report.

### Work completed

- Merged the latest `origin/main` into the A3 branch to preserve the group lead's conflict-resolution updates and refreshed SaaS strategy file.
- Added `summarizeReleaseEvidenceSummary(...)` to `services/report/report_builder.mjs`.
  - Summarizes GitHub Check publish receipt.
  - Summarizes GitHub PR comment publish receipt.
  - Summarizes required-check rollout plan.
  - Summarizes audit bundle root-hash/artifact/custody verification.
  - Summarizes signed audit archive root-hash/signature/entry verification.
  - Only exposes whitelisted status, count, hash-prefix, and safety fields.
- Added `release_evidence_summary` to JSON report exports.
- Added `## Release Evidence Summary` to Markdown report exports.
- Added Dashboard `Release Evidence` panel with:
  - publish evidence status
  - dry-run vs posted state
  - required check plan state
  - audit bundle verification state
  - audit archive signature state
  - safety summary for tokens, secrets, private keys, and real GitHub mutation.
- Added Release Evidence to Report Center and print-ready report output.
- Hardened dashboard wrapping for long release ids, check names, and verification badges so evidence rows do not force horizontal page overflow.
- Wired local static dashboard sources to load existing redacted release evidence fixtures:
  - `a3_github_check_publish_receipt_dry_run.redacted.json`
  - `a3_github_pr_comment_publish_receipt_dry_run.redacted.json`
  - `a3_github_required_check_plan.redacted.json`
  - `a3_audit_bundle_verification_passed.redacted.json`
  - `a3_audit_archive_verification_passed.redacted.json`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_round_release_evidence_display_2026_07_08.md`
- Saved screenshot evidence:
  - `docs/screenshots/a3-dashboard-release-evidence-2026-07-08.png`

### A1/A2 compatibility

- A1 runner, trace, tool-call, SDK, and artifact semantics were not modified.
- A2 judge, score, pass/fail, release policy, and failure taxonomy semantics were not modified.
- The new release evidence summary is appended as a downstream A3 report/dashboard argument, preserving existing positional call compatibility.

### Verification

```text
node --check services/report/report_builder.mjs
node --check apps/dashboard/src/app.mjs
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
node --test --test-concurrency=1 (rg --files tests/a3 -g "*.test.mjs")
```

Result:

```text
Focused: 70 pass, 0 fail
Full A3 single-threaded: 167 pass, 0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, or cloud mutation APIs.
- Did not commit API keys, tokens, cookies, emails, private keys, live signed URLs, or raw account values.
- GitHub publish receipts are still dry-run evidence, so the UI labels them as `dry-run` and `posted false`.

## 2026-07-08 - Signed Audit Archive Manifest And Verifier

### Goal

Continue A3 against `docs/strategy/large-saas-a1-a2-a3-full-plan.md`, specifically the large-SaaS requirements for reports/evidence sharing, enterprise audit, self-host retention, and release workflow evidence. This round closes the next audit gap after the bundle index: A3 can now create and verify a signed, immutable, zip-compatible audit archive manifest.

### Work completed

- Added `services/report/a3_audit_archive.mjs`.
  - Produces `a3.audit_archive_manifest.v1`.
  - Verifies `a3.audit_archive_verification.v1`.
  - Seals the audit bundle index plus bundle artifacts into an archive-level manifest.
  - Records archive entry `sha256`, byte size, content type, role, creator, and workspace-relative path.
  - Adds Ed25519 detached signature metadata with public key only.
  - Does not persist private keys.
  - Keeps binary zip/tar packaging as a follow-up item, while making the manifest zip-compatible.
- Added redacted fixtures:
  - `fixtures/a3/p3/a3_audit_archive_manifest.redacted.json`
  - `fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json`
- Added tests:
  - archive manifest creation
  - signature/root-hash verification
  - tamper detection
  - missing entry detection
  - CLI build/verify flow
  - export-firewall coverage for new archive fixtures
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md`
  - Maps the next money-grade A3 work back to the large SaaS plan.

### A1/A2 compatibility

- A1 run, trace, tool-call, and artifact semantics were not changed.
- A2 judge, score, pass/fail, failure taxonomy, and policy semantics were not changed.
- The archive layer sits downstream of A3 release evidence and verifies already-generated files.

### Verification

```text
node --check services/report/a3_audit_archive.mjs
node --test tests/a3/a3_audit_archive.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/export_firewall_generated_artifacts.test.mjs
node --test (rg --files tests/a3 -g "*.test.mjs")
```

Result:

```text
Focused: 27 pass, 0 fail
Full A3: 165 pass, 0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, or cloud mutation APIs.
- Did not commit private signing keys, API keys, tokens, cookies, emails, live signed URLs, or local absolute paths.
- This round adds signed archive manifest verification, not physical binary zip/tar packaging yet.

## 2026-07-08 - GitHub Publish Evidence Audit Bundle Sealing

### Goal

Preserve the group lead's latest `main` conflict-resolution work, then close the next A3 enterprise audit gap: GitHub Check, PR-comment, and required-check-plan evidence can now be sealed into the generated artifact manifest and audit bundle instead of living as loose dry-run receipts.

### Work completed

- Started from the refreshed `origin/main` baseline after the group lead resolved merge conflicts.
- Added optional Gate CLI inputs:
  - `--github-check-publish-receipt`
  - `--github-pr-comment-publish-receipt`
  - `--github-required-check-plan`
- The Gate CLI now reads these files as external GitHub publish evidence.
  - It does not rewrite the receipt files.
  - It records workspace-relative paths only.
  - It records SHA-256 and byte size.
  - It tags them with `origin: external_github_publish_evidence`.
- Generated artifact manifests can now include the three GitHub publish evidence artifacts alongside JSON report, Markdown report, GitHub check payload, and PR comment payload.
- Audit bundle indexes can now include and verify those GitHub publish evidence artifacts in the same custody chain.
- Refreshed committed Gate CLI and audit-bundle fixtures after `main` artifact changes left older hashes stale.

### A1/A2 compatibility

- A1 run/case/trace/tool-call evidence is still consumed through the existing `runs` fixture/input path.
- A2 grade/pass-fail/failure/coverage evidence is still consumed through the existing `grades`, `coverage`, and `thresholds` paths.
- No A1 runner logic or A2 judge semantics were changed.
- GitHub publish evidence stays downstream of A3 release/report delivery; it is not mixed into A1/A2 source inputs.

### Verification

```text
node --check services/report/a3_gate_cli.mjs
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
21 tests
21 pass
0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr APIs.
- Did not commit real GitHub tokens, API keys, cookies, emails, account data, or signed URLs.
- Did not configure live branch protection; required-check enforcement remains a plan artifact.

## 2026-07-07 - Artifact Registry Evidence Catalog

### Goal

Close today's final A3 commercial gap by turning Report Center outputs and control-plane state into a managed artifact registry. This moves A3 from "download some reports" toward "enterprise evidence catalog": every report/export/control artifact can be counted, linked to a manifest key, checked for redaction/hash readiness, attached to usage meters, and later persisted for audit/self-host workflows.

### Work completed

- Added `services/report/a3_artifact_registry.mjs`.
  - Produces `a3.artifact_registry.v1`.
  - Converts hosted reports into JSON, Markdown, hosted HTML, and report-manifest artifact entries.
  - Adds control-plane artifact entries for usage ledger, DB migration plan, Product Console state, and SaaS Admin guardrails.
  - Adds packet presets for PR review, executive sign-off, security audit, and customer-safe report sharing.
  - Keeps raw secrets and raw share tokens explicitly forbidden.
- Extended `services/report/a3_report_center.mjs`.
  - Report Center now embeds `artifact_registry`.
  - Summary includes artifact count, ready count, and billable meter count.
- Extended `services/report/a3_store.mjs` and `services/report/a3_api_server.mjs`.
  - Dashboard payload now includes `artifact_registry`.
  - Added `GET /api/a3/artifacts/registry`.
  - DB contract now names `artifact_registry_entries` and `artifact_lifecycle_events`.
- Extended `services/report/a3_sql_migrations.mjs`.
  - Added migration batch `007_artifact_registry`.
  - Added tables for artifact registry entries and lifecycle events.
  - Added indexes for project/state/type and artifact lifecycle lookup.
- Extended dashboard wiring.
  - Report Center now shows Artifact Registry summary and first artifact entries.
  - Hosted report sharing refreshes Report Center, Product Console, and Artifact Registry.
  - JSON, Markdown, and print/PDF exports now include Artifact Registry evidence.
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_artifact_registry_2026_07_07.md`
  - Contains 45 next growth points for artifact registry commercialization.

### A1/A2 compatibility

- Registry entries are still derived from A1 run/case/trace/tool-call evidence and A2 grade/judge/pass-fail/failure evidence through the existing A3 report pipeline.
- No A1 runner logic or A2 judge semantics were changed.
- API-backed and fixture-backed sources still share the same normalized A3 boundary.

### Verification

Focused command:

```text
node --test tests/a3/artifact_registry.test.mjs tests/a3/report_center_index.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
78 tests
78 pass
0 fail
```

Full A3 suite:

```text
$tests = rg --files tests/a3 -g "*.test.mjs"; node --test $tests
```

Full result:

```text
135 tests
135 pass
0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, hosted auth, billing, database, email, or cloud mutation APIs.
- Did not commit real API keys, cookies, tokens, account emails, signed URLs, or official private frontend source.
- Artifact Registry stores metadata, schema references, lifecycle state, redaction state, and hash-readiness state only.

## 2026-07-07 - Product Console And SaaS Admin Export Evidence

### Goal

Finish the current A3 commercial-SaaS round by making Product Console and SaaS Admin state part of the actual report/export evidence, not only dashboard UI. This directly supports the team lead's direction: static -> API-backed, HTML blob -> app components, mock fixture -> DB-ready data, report export -> shareable hosted report, and SaaS-style login/team/usage/API-key/trust/cloud-management surfaces.

### Work completed

- Extended `services/report/report_builder.mjs`.
  - Added `summarizeProductConsoleExport()`.
  - Added `summarizeSaasAdminExport()`.
  - Added `product_console` to JSON report exports.
  - Added `saas_admin_console` to JSON report exports.
  - Added Product Console / Onboarding / Audit to Markdown reports.
  - Added SaaS Admin / Login / Team / Trust to Markdown reports.
- Extended `apps/dashboard/src/app.mjs`.
  - Report Center summary now mentions Product Console workflow and SaaS Admin guardrails.
  - JSON/Markdown export buttons now pass `state.productConsole` and `state.saasAdmin`.
  - Print/PDF report preview now includes Product Console and SaaS Admin sections.
- Extended tests.
  - Added report-builder coverage for Product Console exports.
  - Added report-builder coverage for SaaS Admin login/team/API-key/usage/trust/cloud export guardrails.
  - Added dashboard wiring assertions that export/report code carries both states.
- Added Growth-Auditor artifact.
  - `docs/a3/p3_growth_auditor_product_console_export_2026_07_07.md`
  - Documents artifact-entry, export/report growth, enterprise audit value, toy gaps, and 40 next Product Console growth points.

### A1/A2 compatibility

- Product Console export still derives project/case/readiness state from A1 run/case/trace/tool-call evidence and A2 grade/judge/pass-fail/failure evidence.
- SaaS Admin export includes explicit A1/A2 compatibility fields so the console cannot pretend it is ready when run or grade evidence is missing.
- No A1 runner logic or A2 judge semantics were changed.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
62 tests
62 pass
0 fail
```

Full A3 suite:

```text
$tests = rg --files tests/a3 -g "*.test.mjs"; node --test $tests
```

Full result:

```text
132 tests
132 pass
0 fail
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not commit real API keys, cookies, tokens, account emails, signed URLs, or official private frontend source.
- Did not perform real login, API-key creation, team invite, billing mutation, Trust publishing, or cloud mutation.
- Kept all admin/cloud actions as local, read-only, metadata-only, disabled, or plan-only.

## 2026-07-07 - Product Console Onboarding Audit Project Workflow

### Goal

Continue the large-SaaS plan from `origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md` by adding a real user-workflow layer for onboarding, project console state, audit log evidence, and commercial readiness. This targets A3-2 information architecture, A3-3 onboarding, A3-4 project/run UI, and A3-10 settings/audit/admin direction.

### Work completed

- Added `services/report/a3_product_console.mjs`.
  - Builds `a3.product_console.v1`.
  - Converts A1/A2/report/usage/audit evidence into onboarding state, project console state, audit log state, and commercial readiness.
  - Keeps empty projects honest with `setup_required`, `empty`, and `needs_more_real_evidence`.
- Added `GET /api/a3/product/console`.
  - Read-only API route.
  - Uses tenant/project scoped options where available.
  - Does not perform real login, invite, billing, or cloud mutations.
- Added dashboard Product Console panel.
  - Renders Onboarding Flow, Project Console, Audit Log, and Commercial Readiness.
  - Refreshes after API-backed hosted report creation.
- Added tests.
  - `tests/a3/a3_product_console.test.mjs`
  - Updated API server and dashboard wiring tests.
- Added evidence artifacts.
  - `docs/a3/p3_growth_auditor_onboarding_audit_project_console_2026_07_07.md`
  - `docs/a3/p3_onboarding_audit_a1_a2_compatibility_2026_07_07.md`

### 20+ growth points produced

The Growth-Auditor artifact lists 24 next growth points, including SQL persistence for audit events, project console route, onboarding route, project list UI, audit export, report-center event timeline, waiver/approval audit ingestion, usage/billing plan card, official onboarding parity, product console export, tenant-scope tests, Playwright screenshot evidence, reviewer SLA, and retention policy preview.

### Verification

Focused command:

```text
node --test tests/a3/a3_product_console.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
32 tests
32 pass
0 fail
```

Full A3 suite result:

```text
130 tests
130 pass
0 fail
```

Safety checks:

```text
git diff --check
=> no whitespace errors; only Windows CRLF warnings

secret/path scan
=> only intentional redaction-test strings and policy docs matched; no real key, token, cookie, signed URL, account email, or local user path was added
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr or mutate real cloud resources.
- Did not commit API keys, cookies, tokens, account emails, signed URLs, or official private source.
- Did not modify A1 runner logic or A2 judge semantics.

## 2026-07-07 - SaaS Admin Cloud Parity Growth

### Goal

Strengthen the A3 Product Console so it covers the SaaS-style areas the team asked for: login, team management, usage, API keys, trust, and cloud/project management. Keep the implementation clean-room and safe, and keep A1/A2 compatibility intact.

### Work completed

- Extended `services/report/a3_saas_admin.mjs`.
  - Added richer login/session posture without reading or saving cookies/tokens.
  - Added RBAC matrix for owner, admin, developer, reviewer, auditor, and billing admin.
  - Added invite workflow states while keeping real email invites disabled.
  - Added API key lifecycle states for create/store/rotate/revoke while keeping real secrets forbidden.
  - Added usage plan snapshot and preview-only budget controls.
  - Added Trust Center preview artifacts and redacted audit-log policy.
  - Added cloud resources, project switcher, audit controls, and product-console map.
- Extended `apps/dashboard/src/components/saas-admin-console.mjs`.
  - Dashboard now renders Auth Session, RBAC Matrix, Invite Workflow, Usage Controls, API Key Lifecycle, Trust Center, Cloud Management, and Product Console Map.
- Extended `services/report/a3_sql_migrations.mjs`.
  - Added SaaS database tables to the migration contract: `users`, `roles`, `team_members`, `api_keys`, and `trust_reports`.
- Extended `apps/dashboard/src/app.mjs`.
  - Static runtime contract now lists SaaS admin API surfaces and SaaS tables.
- Added `docs/a3/p3_saas_admin_cloud_parity_growth_2026_07_07.md`.
  - Documents what was copied as product logic, what remains plan-only, and why no official private source or secrets were committed.

### A1/A2 compatibility

- A3 still reads A1 evidence through normalized runs, cases, trace events, observations, and tool calls.
- A3 still reads A2 evidence through normalized grades, judge results, score, pass/fail, and failure class.
- No A1 runner logic or A2 judge semantics were changed.

### Verification

Focused command:

```text
node --test tests/a3/a3_saas_admin.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
35 tests
35 pass
0 fail
```

Full A3 suite result after this round:

```text
127 tests
127 pass
0 fail
```

Safety checks:

```text
git status --ignored -sb -- .env.local
=> !! .env.local

git diff --check
=> no whitespace errors; only Windows CRLF warnings

secret/path scan
=> only intentional redaction-test strings and policy docs matched; no real secret or account data was added
```

### Safety boundary

- Did not read or print `.env.local`.
- Did not write real API keys, cookies, tokens, emails, signed URLs, account identities, or official private frontend source.
- Did not call live Ashr, hosted auth, billing, database, email, or cloud mutation APIs.

## 2026-07-04 - First A3 pass

### Goal

Start A3 Dashboard & Triage work after A1/A2 opened draft PRs. Do not merge A1/A2. Read their contracts and create an independent dashboard skeleton that can consume A1/A2-style fixtures.

### Commands

```text
gh repo clone 3351666087/ashr-codex-factory ashr-codex-factory
git fetch origin
git status -sb
gh pr list --repo 3351666087/ashr-codex-factory --state open --json number,title,headRefName,baseRefName,isDraft,author,updatedAt,url
git diff --name-status origin/main...origin/codex/a1-local-sdk-runner
git diff --name-status origin/main...origin/dev/a2-scenario-judge
gh pr view 1 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
gh pr view 2 --repo 3351666087/ashr-codex-factory --json title,body,files,commits,reviews,comments
git switch -c codex/a3-dashboard-triage
node --test tests/a3/report_builder.test.mjs
python -m http.server 5173 --bind 127.0.0.1
```

### PR reconnaissance

- PR #1: `A1 local SDK runner trace loop`, draft, branch `codex/a1-local-sdk-runner`.
- PR #2: `A2: Scenario and judge foundation`, draft, branch `dev/a2-scenario-judge`.
- Main branch has only `README.md`, so A3 cannot directly import merged A1/A2 files yet.

### Implemented

- Added A3 mock run fixture based on A1/A2 field names.
- Added A3 mock grade fixture based on A2 grade output.
- Added pure report builder functions in `services/report/report_builder.mjs`.
- Added static dashboard skeleton in `apps/dashboard/index.html`.
- Added A3 tests for summary, clustering, and exports.
- Added A3 integration plan, mock fixture contract, and acceptance checklist.
- Verified the dashboard in browser at `http://127.0.0.1:5173/apps/dashboard/index.html`.
- Captured desktop, failed case, failure cluster, and mobile viewport screenshots.
- Added 6 dashboard filters: status, scenario family, failure class, run, severity, and score band.
- Added selected-case judge drilldown below Expected vs Actual.
- Added report-builder filter helpers so filtering can be tested outside the UI.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

Browser checks:

- Summary rendered `Runs=1`, `Cases=4`, `Pass Rate=50%`, `Trace Complete=100%`.
- Failure clusters rendered `missing_required_tool` and `wrong_arguments`.
- Failed case detail for `A2-S004` showed expected `web.search` and actual empty `tool_calls`.
- Mobile viewport rendered single-column layout at width 390.
- Filter logic covers failed + major + 70-89 score band.
- Captured 10 demo screenshots covering summary, failed detail, clusters, filters, wrong argument detail, judge drilldown, export actions, and mobile viewport.

### Evidence paths

- `docs/a3/a3_integration_plan.md`
- `docs/a3/mock_fixture_contract.md`
- `docs/a3/acceptance_checklist.md`
- `fixtures/a3/mock_run_results.json`
- `fixtures/a3/mock_grade_results.json`
- `apps/dashboard/index.html`
- `services/report/report_builder.mjs`
- `tests/a3/report_builder.test.mjs`
- `docs/screenshots/a3-dashboard-summary.png`
- `docs/screenshots/a3-dashboard-case-detail.png`
- `docs/screenshots/a3-dashboard-failure-clusters.png`
- `docs/screenshots/a3-dashboard-mobile-viewport.png`
- `docs/screenshots/a3-01-summary.png`
- `docs/screenshots/a3-02-failed-case-detail.png`
- `docs/screenshots/a3-03-failure-clusters.png`
- `docs/screenshots/a3-04-filter-failed.png`
- `docs/screenshots/a3-05-filter-major.png`
- `docs/screenshots/a3-06-filter-score-band.png`
- `docs/screenshots/a3-07-wrong-argument-detail.png`
- `docs/screenshots/a3-08-judge-drilldown.png`
- `docs/screenshots/a3-09-export-actions.png`
- `docs/screenshots/a3-10-mobile-viewport.png`

### Known gaps

- A1/A2 draft PR files are not merged into main, so A3 uses mock fixtures for now.
- Root package/test configuration does not exist yet; A3 tests use Node's built-in test runner directly.

### Next top 3

1. Add judge-mode filter after A2 has more varied sample judge modes.
2. Create a transform script after A1/A2 PRs merge so A3 can replace mock fixtures with real outputs.
3. Replace the static HTML shell with the team's final frontend stack if the repo standardizes on one.

## 2026-07-04 - P3 Ashr calibration

### Goal

Start P3/G3 real Ashr calibration after A1, A2, and A3 merged into main. Keep the work small and safe: verify key hygiene, inspect real Ashr field shapes, save redacted evidence, and add only a narrow mapper for A3.

### Implemented

- Added `docs/a3/p3_ashr_calibration_plan.md`.
- Added `docs/a3/p3_field_mapping.md`.
- Added `docs/a3/p3_worklog.md`.
- Saved redacted Ashr smoke fixtures under `fixtures/a3/p3`.
- Added `services/report/p3_ashr_mapper.mjs`.
- Added `tests/a3/p3_ashr_mapper.test.mjs`.
- Updated `docs/a3/acceptance_checklist.md`.

### Smoke test summary

- `.env.local` exists and is ignored by Git.
- The key was read only through environment variables and was not printed.
- `init()`, `health_check()`, `list_datasets()`, `list_runs()`, and `list_requests()` succeeded.
- `list_agents()` succeeded but returned an empty list.
- `list_observability_traces()` failed because this account has `features.observability == false`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 8
pass 8
fail 0
```

### Next top 3

1. Verify native backend failure-class fields with a real failing Ashr run.
2. Decide whether A3 should display `semantic_similarity` as the score or wait for a stronger server grade field.
3. Join `list_runs()` with `list_datasets()` so A3 cases can use real scenario titles.

## 2026-07-04 - Product console media evidence iteration

### Goal

Continue A3 after P3 calibration and move the dashboard toward a commercial-grade product console. This round chose one highest ROI enhancement: media evidence calibration and display.

### Implemented

- Added `docs/a3/p3_media_calibration.md`.
- Added `docs/a3/p3_official_frontend_notes.md`.
- Extended `services/report/p3_ashr_mapper.mjs` to support real Ashr `run.result.cases[]` samples.
- Added `media_evidence` mapping for media type, action tags, output paths, audio tags, intent tags, VM stream summaries, and known gaps.
- Added media timeline events such as `media.vm_stream`.
- Extended `services/report/report_builder.mjs` so summary/export includes media evidence.
- Added P3 media sample coverage in `tests/a3/p3_ashr_mapper.test.mjs`.
- Updated `apps/dashboard/index.html` from a demo dashboard toward a product console:
  - data source switcher
  - workflow overview
  - Usage / Quota known-gap panel
  - Requests / datasets / runs object summary
  - case-level Media Evidence panel
  - P3 media sample mode

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 9
pass 9
fail 0
```

Browser checks:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`.
- Confirmed title, P3 data source, 3 case rows, 3 media-evidence cases, and Media Evidence panel.
- Confirmed no browser console warnings/errors.
- Confirmed mobile viewport width 390 has no horizontal overflow.

### Evidence paths

- `fixtures/a3/p3/ashr_media_field_sample.redacted.json`
- `fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_run_detail_sample.redacted.json`
- `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`
- `docs/a3/p3_media_calibration.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/screenshots/a3-p3-product-console-media-overview.png`
- `docs/screenshots/a3-p3-product-console-media-mobile.png`

### Known gaps

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` failed with a network reset, so local remote refs may lag GitHub API state.
- Authenticated `lab.ashr.io` dashboard observation is blocked until a logged-in session is available.
- Real signed media URLs for audio/image/video are not confirmed in the sanitized sample.
- Native Ashr backend failure-class fields remain unconfirmed; A3 still derives failure class for the media sample.

### Next top 3

1. Add trace/tool-call expected-vs-actual diff.
2. Add report center / PDF-ready report layout.
3. Observe authenticated Ashr Lab after manual login and update A3 navigation assumptions.

## 2026-07-04 - Tool-call diff follow-up

### Goal

Continue the next A3 backlog item: make tool-call failures directly readable in the dashboard and exported JSON.

### Implemented

- Added `buildToolCallDiffs(caseResult)` to `services/report/report_builder.mjs`.
- Added `tool_call_diffs` to JSON export.
- Added test coverage in `tests/a3/report_builder.test.mjs`.
- Added dashboard `Tool Call Diff` panel under Case Detail.
- Added `docs/a3/p3_tool_call_diff.md`.
- Captured `docs/screenshots/a3-p3-tool-call-diff.png`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 10
pass 10
fail 0
```

Browser checks:

- Missing required tool case showed `missing_required_tool`.
- Wrong argument case showed `wrong_arguments`.
- Tool name and argument JSON rendered in expected/actual columns.
- Desktop check showed no horizontal overflow.

### Next top 3

1. Add field-level argument highlighting.
2. Add report center / PDF-ready report layout.
3. Observe authenticated Ashr Lab after manual login.

## 2026-07-04 - Dashboard product-console polish

### Goal

Continue optimizing A3's third part by making the dashboard feel more like a commercial product console while preserving the existing local fixture workflow.

### Implemented

- Added `docs/a3/a3_dashboard_polish.md`.
- Refined dashboard visual styling with clearer panel spacing, shadows, and health color accents.
- Added `Coverage Health` to surface A2 coverage summary, assignment health, and coverage warnings.
- Added `Triage Queue` to rank current failed cases by severity and score.
- Added `Report Center` to explain JSON/CSV/Markdown report contents and mirror export actions.
- Shared one export handler across topbar export buttons and Report Center buttons.
- Added dashboard wiring test coverage for the new product-console panels.
- Escaped rendered judge, trace, and cluster text for safer fixture rendering.
- Added P3 mapper de-duplication for repeated redacted case IDs so dashboard selection is deterministic.
- Captured desktop, P3 media, and mobile screenshots for this polish pass.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 19
pass 19
fail 0
```

Browser checks:

- Mock dashboard rendered Coverage Health, Triage Queue, and Report Center.
- P3 media dashboard rendered 3 cases, 3 media-evidence cases, and exactly one active triage row after P3 case ID de-duplication.
- Mobile viewport width 390 had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/a3/a3_dashboard_polish.md`
- `docs/screenshots/a3-dashboard-polish-overview.png`
- `docs/screenshots/a3-dashboard-polish-p3-media.png`
- `docs/screenshots/a3-dashboard-polish-mobile.png`

### Next top 3

1. Add field-level tool argument diff highlighting.
2. Link each tool diff row back to A2 judge evidence.
3. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.

## 2026-07-04 - Field-level argument diff follow-up

### Goal

Make `wrong_arguments` failures easier to understand by showing exactly which tool argument field changed, went missing, or appeared unexpectedly.

### Implemented

- Added `buildArgumentDiffs()` in `services/report/report_builder.mjs`.
- Extended `buildToolCallDiffs()` so each diff row can include `argument_diffs`.
- Preserved `argument_diffs` in JSON report export through the existing `tool_call_diffs` field.
- Updated the dashboard `Tool Call Diff` panel to show argument path, status, expected value, and actual value.
- Added test coverage for changed, missing, and unexpected argument fields.
- Updated `docs/a3/p3_tool_call_diff.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 21
pass 21
fail 0
```

Browser checks:

- Selected the `Wrong Argument Trap` case in the dashboard.
- Confirmed `argument_diffs` rendered one field row for `path`.
- Confirmed status `changed_argument`.
- Confirmed expected value `fixtures/a2/contracts/vendor-alpha.txt`.
- Confirmed actual value `fixtures/a2/contracts/vendor-alfa.txt`.
- Desktop viewport had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/screenshots/a3-dashboard-argument-diff.png`

### Next top 3

1. Link each diff row back to A2 judge evidence.
2. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.
3. Add semantic matching for reordered tool calls instead of index-only matching.

## 2026-07-04 - Tool diff judge evidence linkage

### Goal

Connect each A3 `Tool Call Diff` row back to the A2 judge evidence that explains why the row failed.

### Implemented

- Added `judge_evidence` to each `buildToolCallDiffs()` row when a failed A2 judge result matches the diff failure class or tool call ID.
- Preserved judge evidence in JSON export through the existing `tool_call_diffs` field.
- Dashboard now renders judge mode, score, failure class, severity, summary, tool evidence IDs, details, and remediation under the relevant tool diff row.
- Added report-builder test coverage for missing-tool and wrong-argument judge evidence linkage.
- Added dashboard wiring test coverage for the judge evidence UI.
- Updated `docs/a3/p3_tool_call_diff.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs
node --test tests/a3/p3_ashr_mapper.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 22
pass 22
fail 0
```

Browser checks:

- Selected the `Wrong Argument Trap` case in the dashboard.
- Confirmed the matching diff row renders `g1_trace_contract_judge`.
- Confirmed tool evidence ID `file.read#1`.
- Confirmed judge details and remediation render under the tool diff.
- Desktop viewport had no horizontal overflow.
- Browser console warnings/errors: none.

### Evidence paths

- `docs/screenshots/a3-dashboard-judge-evidence.png`

### Next top 3

1. Add a print/PDF-ready report layout if the team wants handoff docs directly from A3.
2. Add semantic matching for reordered tool calls instead of index-only matching.
3. Deep-link judge evidence to exact trace event IDs when shared trace IDs are available.

## 2026-07-04 - Print-ready report preview

### Goal

Add a PDF-ready report view so A3 can produce a handoff report directly from the dashboard, not only through JSON/CSV/Markdown downloads.

### Implemented

- Added dashboard `Report Preview` section.
- Added `Print Report` topbar action and `Print/PDF` Report Center action.
- Added print CSS that hides sidebar, filters, operational controls, run list, and case detail during browser print.
- Added `renderPrintReport()` to summarize metrics, coverage health, failure clusters, triage queue, selected case evidence, tool diffs, and linked judge evidence.
- Updated Report Center to describe the Print/PDF workflow.
- Added dashboard wiring test coverage for the report preview and print path.
- Updated `docs/a3/a3_dashboard_polish.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 23
pass 23
fail 0
```

Browser checks:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html#report-preview`.
- Confirmed Report Preview renders summary metrics, coverage health, failure clusters, triage queue, selected case evidence, tool diff, and linked judge evidence.
- Selected the `Wrong Argument Trap` failed case and confirmed the report preview refreshed to show `wrong_arguments` evidence.
- Confirmed no horizontal overflow at desktop viewport width.
- Browser console warnings/errors: none.

Evidence path:

- `docs/screenshots/a3-dashboard-print-report.png`

### Next top 3

1. Add semantic matching for reordered tool calls instead of index-only matching.
2. Deep-link judge evidence to exact trace event IDs when shared trace IDs are available.
3. Add judge-mode filtering after A2 exposes more varied judge-mode samples.

## 2026-07-04 - Semantic tool-call matching closeout

### Goal

Stop expanding A3 and close one remaining high-value Tool Call Diff gap: reordered tool calls should be shown as `wrong_tool_order`, not as unrelated `wrong_tool` rows.

### Implemented

- Updated `buildToolCallDiffs()` to pair expected and actual tool calls by semantic similarity before falling back to index matching.
- Added diff metadata: `match_strategy`, `expected_index`, `actual_index`, and `order_changed`.
- Added `wrong_tool_order` diff status when the same tool and arguments appear in a different position.
- Updated judge evidence matching so reordered rows can still link back to A2 `tool_call_ids`.
- Added dashboard display for matching strategy and original expected/actual positions.
- Added one A3 mock `wrong_tool_order` case so the dashboard can demonstrate the behavior.
- Added report-builder and dashboard wiring tests.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 25
pass 25
fail 0
```

Spot check:

- `sample-a2-s009-wrong-order` now produces two `wrong_tool_order` rows.
- Both rows use `semantic_exact_reordered`.
- Expected `web.search` matches actual `web.search` even when actual position is #2.
- Expected `web.open` matches actual `web.open` even when actual position is #1.
- Both rows keep linked A2 judge evidence.

### Stop point

This is a reasonable A3 polish stopping point. Remaining items are optional refinements, not required for the current dashboard/report handoff.

## 2026-07-05 - Judge-mode filter closeout

### Goal

Continue yesterday's unfinished A3 acceptance work without expanding scope. The clear remaining UI gap was that `services/report/report_builder.mjs` already exposed `judgeModes` and `filterCases(..., { judgeMode })`, but the dashboard did not yet have a Judge Mode filter control.

### Implemented

- Added a `Judge Mode` select to the dashboard filter row.
- Populated the select from normalized A2 judge modes through `getFilterOptions(state.cases).judgeModes`.
- Wired the selected judge mode into `filterCases()`.
- Added dashboard wiring test coverage.
- Extended report-builder filter tests to verify `g1_trace_contract_judge` and `g2_output_contract_judge` options and judge-mode filtering behavior.
- Updated `docs/a3/acceptance_checklist.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 26
pass 26
fail 0
```

Spot check:

- Judge mode options include `g1_trace_contract_judge` and `g2_output_contract_judge`.
- Filtering by `g2_output_contract_judge` returns `sample-a2-s001-pass` and `sample-a2-s004-missing-tool`.

### Scope safety

- No real Ashr API calls.
- No secret/key reads or writes.
- No A1 runner logic changes.
- No A2 judge semantic changes.

## 2026-07-05 - Dataset scenario title join closeout

### Goal

Continue the remaining P3 A3 mapper acceptance item without using real credentials or expanding scope: mapped A3 cases should be able to use scenario titles from Ashr dataset samples instead of falling back only to test/case IDs.

### Implemented

- Added `buildDatasetScenarioIndex()` in `services/report/p3_ashr_mapper.mjs`.
- Added optional `datasetSample` support to `mapAshrSampleToA3Fixtures()`.
- Joined dataset scenario title, dataset type, scenario key, and intent tags into mapped A3 cases when a dataset sample is provided.
- Kept fallback behavior unchanged when no dataset sample is available.
- Updated P3 media dashboard loading so it passes `ashr_dataset_detail_sample.redacted.json` into the mapper.
- Added mapper test coverage for dataset title joins.
- Added dashboard wiring test coverage to ensure the P3 dataset sample is passed into the mapper.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_field_mapping.md`.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- P3 media sample mapping reports `metadata.dataset_scenario_joined=true`.
- Mapped cases preserve joined dataset scenario titles in `metadata.dataset_scenario_title`.
- No real Ashr API calls were made; only committed redacted fixtures were used.

### Remaining P3 unknowns

- Native Ashr backend failure-class evidence was checked later with a real failed run; current sample has no named backend `failure_class`.
- Signed media URL fields still need confirmation from an unsanitized or richer sample.
- Authenticated Ashr Lab UI observation still requires a manual logged-in browser session.

## 2026-07-05 - Judge evidence trace-link closeout

### Goal

Close the remaining A3 Tool Call Diff evidence item without using live Ashr data: judge evidence should point back to matching trace event IDs when A3 has trace events with matching tool names or tool call IDs.

### Implemented

- Added `trace_event_links` to each A3 tool-call diff row.
- Added linked `evidence.trace_event_ids` inside each matching `judge_evidence` block.
- Matched trace events by tool name and tool call ID.
- Preserved fallback trace IDs when the source event lacks a stable `event_id`.
- Updated dashboard Judge Evidence rendering to show `Trace events`.
- Updated print/report preview judge evidence text to include trace event IDs.
- Added report-builder and dashboard wiring tests.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_tool_call_diff.md`.

### Verification

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- `sample-a2-s010-wrong-argument` now links `file.read` judge evidence to `sample-a2-s010-wrong-argument:trace:1`.
- Reordered tool-call tests link `web.search` and `web.open` to their exact synthetic trace event IDs.

### Stop point

This is the chosen stop point for this run. Remaining unchecked items need live/less-sanitized Ashr evidence or manual authenticated UI access, so they should not be forced in this local-only A3 pass.

## 2026-07-05 - Score source policy closeout

### Goal

Close the P3 score-source decision without live API calls. A3 needed a clear rule for whether dashboard/report scores come from `semantic_similarity` or from stronger Ashr grade fields.

### Decision

A3 now uses this priority:

1. `case.grade.score` when present, recorded as `ashr_case_grade_score`.
2. `case.score` when present, recorded as `ashr_case_score`.
3. Average `action_results[].semantic_similarity` for action-results samples without a stronger grade, recorded as `semantic_similarity_average`.
4. Pass/fail fallback only when no score-like field exists, recorded as `pass_fail_default`.

### Implemented

- Added `score_source` and `score_source_detail` metadata in P3 mapped cases.
- Added grade-result metadata with the same score source.
- Added `score_source` to A3 JSON report export.
- Added mapper and report-builder tests for score-source behavior.
- Updated `docs/a3/acceptance_checklist.md` and `docs/a3/p3_field_mapping.md`.

### Verification

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 28
pass 28
fail 0
```

Spot check:

- Action-results sample uses `semantic_similarity_average`.
- P3 media case-result sample uses `ashr_case_grade_score`.
- Mock A3 cases export `score_source=unknown`, because they predate P3 score provenance.

### Stop point

This is a reasonable local-only stop point. Remaining P3 evidence items require live failing Ashr runs, signed media URL confirmation, or authenticated Ashr Lab access.

## 2026-07-05 - Generated A3 fixture closeout

### Goal

Close the remaining local-only A3 acceptance item: replace hand-maintained A3 mock fixtures with reproducible fixtures generated from merged A2 outputs.

### Implemented

- Added `services/report/a3_fixture_builder.mjs`.
- The builder reads:
  - `packages/scenarios/a2_g3_full_pack.json`
  - `fixtures/a2/results/a2_g3_grade_results.json`
  - `fixtures/a2/runs/*.json`
- Regenerated:
  - `fixtures/a3/mock_run_results.json`
  - `fixtures/a3/mock_grade_results.json`
- The default A3 mock dashboard now uses 32 merged A2 executable cases instead of 5 hand-maintained demo cases.
- Preserved A2 judge results, scenario titles, scenario families, expected tool calls, actual tool calls, final responses, observations, and trace events.
- Added special handling for `wrong_tool_order` cases where A2 declares tool names but omits expected args, so A3 shows order diffs instead of false argument diffs.
- Added `tests/a3/a3_fixture_builder.test.mjs` to prove the checked-in A3 fixtures match the generated output.
- Updated `tests/a3/report_builder.test.mjs` for the 32-case generated fixture.
- Updated `docs/a3/mock_fixture_contract.md` and `docs/a3/acceptance_checklist.md`.

### Verification

```text
node services/report/a3_fixture_builder.mjs --write
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 30
pass 30
fail 0
```

### Stop point

This is a clean local stop point. The remaining unchecked items require external/manual evidence: a real failing Ashr run, authenticated Ashr Lab UI observation, or richer signed media URL samples.

## 2026-07-05 - Frontend/API product logic calibration

### Goal

Continue P3 by using the now-local `ASHR_API_KEY` safely, collecting real Ashr API field evidence, and documenting how real Ashr frontend/product logic maps into the A3 Dashboard / Triage / Report MVP.

### Implemented

- Confirmed `.env.local` remains ignored and contains one `ASHR_API_KEY` entry without printing the key.
- Ran a read-only real Ashr API calibration using the key from environment only.
- Saved new sanitized fixtures:
  - `fixtures/a3/p3/ashr_frontend_api_objects.redacted.json`
  - `fixtures/a3/p3/ashr_run_trace_sample.redacted.json`
  - `fixtures/a3/p3/ashr_media_url_sample.redacted.json`
- Confirmed successful read-only calls for:
  - `init`
  - `health_check`
  - `list_agents`
  - `list_datasets`
  - `get_dataset`
  - `list_runs`
  - `get_run`
  - `list_requests`
  - `get_request`
  - signed-url dataset probes
- `list_observability_traces` still failed because the account does not have observability enabled.
- Confirmed `get_run` can return a direct run object with `result.cases[]`.
- Confirmed the redacted run sample contains expected/actual, score, pass/fail, failure-like fields, and tool-call evidence.
- Confirmed a signed media/file URL field name: `actions[].signed_url`; the value is redacted.
- Added frontend/product docs:
  - `docs/a3/p3_frontend_page_map.md`
  - `docs/a3/p3_frontend_workflow_notes.md`
  - `docs/a3/p3_frontend_field_mapping.md`
  - `docs/a3/p3_frontend_to_a3_mvp_gap.md`
  - `docs/a3/p3_a3_mvp_recommendations.md`
- Updated `docs/a3/p3_field_mapping.md`, `docs/a3/p3_official_frontend_notes.md`, and `docs/a3/acceptance_checklist.md`.

### Frontend observation result

- A Windows Edge window titled `Ashr Labs ... Microsoft Edge` was present.
- Direct content extraction from that logged-in Edge window was stopped by the browser-control safety layer because it could not verify the current browser URL.
- Codex in-app browser was available but did not share the Edge login state.
- No logged-in screenshots were saved and no UI state was changed.

### Verification target

Run the A3 test suite and secret scan after this documentation pass.

### Next top 3

1. Log into Ashr Lab inside the Codex in-app browser or provide sanitized screenshots so A3 can directly confirm page labels and navigation.
2. Add a small request provenance panel in A3 using the confirmed `request_status`, duration, accepted-input, and generation-option fields.
3. Get one UI-visible populated hosted run to verify frontend run/case detail pages and frontend failure labels.

## 2026-07-06 - Authenticated Ashr Lab UI calibration

### Goal

Finish the direct authenticated frontend observation that was blocked in the prior round.

### What happened

- The user could not log into Ashr through the Codex in-app browser because Google OAuth returned `400 Bad Request`.
- Normal Edge/Chrome windows still could not be inspected safely because browser URL verification failed.
- Opened a separate Chrome profile with local CDP debugging on port `9222`.
- The user manually logged into Ashr in that isolated Chrome profile.
- Used read-only CDP/Playwright observation after login.

### Confirmed UI pages

- Datasets: `?tab=analysis`
- Agents: `?tab=agents`
- Folders: `?tab=folders`
- Analytics: `?tab=analytics`
- Usage: `?tab=usage`
- Trust: `?tab=trust`
- API Keys: `?tab=api-keys`
- Team: `?tab=team`

### Confirmed product logic

- Datasets page has search, filters, sort, group, pinned-only, and `New dataset`.
- New Dataset is an 8-step wizard: Basic Info, Agent, Inputs, Tools, Context, Test Config, Behaviors, Review.
- Analytics exposes run volume, pass rate over time, runs by agent, and pass rate by agent.
- Usage tracks Images, Audio, and Files quota.
- Trust is a public certificate/trust-page concept with frozen metrics.
- API Keys and Team are real admin pages but outside A3 MVP scope.

### Updated docs

- `docs/a3/p3_frontend_page_map.md`
- `docs/a3/p3_frontend_workflow_notes.md`
- `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- `docs/a3/p3_frontend_field_mapping.md`
- `docs/a3/p3_a3_mvp_recommendations.md`
- `docs/a3/p3_official_frontend_notes.md`
- `docs/a3/p3_worklog.md`
- `docs/a3/acceptance_checklist.md`

### Safety

- No screenshots saved from the authenticated account.
- No cookies, tokens, key values, or account-specific values saved.
- No create/delete/submit actions performed.
- `.env.local` was not touched.

### Verification

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
tests 30
pass 30
fail 0
```

Additional checks:

- `git diff --check`: only LF-to-CRLF warnings.
- `.env.local`: ignored by `.gitignore`.
- Targeted secret scans: no account email, username, real API-key assignment, bearer token, cookie assignment, or token assignment found in the new authenticated-frontend docs.
- Broader A3 scan still matches an intentional fake fixture string shaped like `ashr_live_...`; this is synthetic test content and not a real secret.

### Remaining gaps

- Need a populated Ashr hosted run to observe run detail, case detail, trace/timeline, expected-vs-actual, and frontend failure labels.
- Need a UI-visible populated hosted run to verify frontend failure labels; backend failed-run fields were checked later through the API.

## 2026-07-06 - Request Provenance panel

### Goal

Use the already-confirmed Ashr request API fields to improve A3's product-console workflow without making live API calls.

### Implemented

- Added `summarizeRequestProvenance()` to `services/report/report_builder.mjs`.
- Added request provenance to JSON and Markdown exports.
- Added dashboard `Request Provenance` panel.
- Dashboard P3 media source now loads `fixtures/a3/p3/ashr_request_detail_sample.redacted.json`.
- Added tests for report-builder request summary and dashboard wiring.
- Updated A3/P3 docs and acceptance checklist.

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

- Local preview: `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`
- Request Provenance rendered status, accepted inputs, generation outputs, tool count, strategy, and failure flag.
- Browser console warnings/errors: none.
- Screenshot: `docs/screenshots/a3-dashboard-request-provenance.png`

### Scope safety

- No live Ashr API calls.
- No `.env.local` access.
- No A1 runner logic changes.
- No A2 judge semantic changes.
- Only A3-owned code/docs were changed.

### Remaining gaps

- Native backend failure-class evidence has now been checked with a real failed run; frontend failure labels still need a UI-visible populated run.
- Populated Ashr run/case/trace frontend pages still need a non-empty Lab account or generated sample.
- Full signed media URL rendering is still blocked until per-modality redaction/access behavior is confirmed.

## 2026-07-06 - Real failed-run API probe

### Goal

Continue P3 calibration with the user's logged-in Chrome session and local `.env.local` key, while keeping the work read-only and secret-safe.

### API evidence

- Ran read-only `list-runs` and `list-requests` probes.
- Found a real failed run in the Ashr API response.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_failed_run_probe.redacted.json`
  - `fixtures/a3/p3/ashr_failed_run_detail.redacted.json`
  - `fixtures/a3/p3/ashr_request_probe.redacted.json`
  - `fixtures/a3/p3/ashr_failed_request_detail.redacted.json`
- Confirmed failed-run fields:
  - `run.result.status`
  - aggregate passed/failed counts
  - `run.result.cases[]`
  - per-case `status`
  - `grade.label`
  - `grade.passed`
  - `grade.score`
  - `grade.reason`
  - `grade.metrics`
- Confirmed no named native backend `failure_class` field in this failed-run sample.
- A3 therefore still derives failure clusters from grade metrics and expected/actual evidence.

### Frontend evidence

- Connected read-only to the user's logged-in Chrome through local CDP.
- Confirmed the Lab Datasets page loaded but showed 0 UI-visible datasets.
- Confirmed Analytics loaded but showed 0 agents, 0 datasets, 0 graded runs, and not enough data.
- Confirmed Trust, Agents, and Folders empty states.
- Did not save authenticated screenshots or account-specific values.

### Implemented

- Updated `services/report/p3_ashr_mapper.mjs` so `extractAshrRuns()` accepts API probe wrapper shapes such as `response.run` and `response.runs`.
- Added mapper test coverage for the real redacted failed-run fixture.
- Updated P3 field mapping, frontend gap docs, MVP recommendations, and acceptance checklist.

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

### Remaining gaps

- Need one UI-visible populated Lab run to observe real frontend run detail, case detail, expected-vs-actual, tool calls, trace/timeline, and frontend failure labels.
- Need per-modality signed media URL behavior before rendering live signed links.
- Keep failure class derived unless a future Ashr sample exposes a named backend `failure_class`.

## 2026-07-06 - API/frontend visibility gap documented

### Goal

Explain why the authenticated Lab frontend can show empty states while the API still returns populated calibration objects.

### Evidence

- Ran read-only API probes for datasets, runs, requests, and failed-run dataset detail.
- Saved sanitized fixtures:
  - `fixtures/a3/p3/ashr_dataset_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_run_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_request_probe_after_frontend_empty.redacted.json`
  - `fixtures/a3/p3/ashr_failed_run_dataset_detail.redacted.json`
- API returned populated objects:
  - 3 datasets
  - 2 runs
  - 5 requests
- Authenticated frontend still showed:
  - 0 UI-visible datasets on Datasets
  - 0 graded runs on Analytics
  - run-tests-first empty state on Trust

### Output

- Added `docs/a3/p3_api_frontend_visibility_gap.md`.
- Linked it from `docs/a3/p3_frontend_page_map.md`.
- Added checklist evidence in `docs/a3/acceptance_checklist.md`.

### Conclusion

The current gap is frontend visibility, not API availability. A3 should keep using sanitized API fixtures for populated run/case evidence until a UI-visible hosted run is available.

## 2026-07-06 - Frontend session expired

### Goal

Check whether the connected Chrome Lab session can still be used for frontend product calibration.

### Evidence

- Observed the current Lab frontend through read-only Chrome/CDP.
- The page showed sign-in UI and `Your session has expired. Please sign in again.`
- Frontend POST requests to `api.ashr.io/testing-platform-api` returned `401`.
- Saved sanitized fixture: `fixtures/a3/p3/ashr_frontend_session_expired_network.redacted.json`.

### Safety

- No headers, cookies, tokens, response bodies, or screenshots were saved.
- No sign-in or form-submit action was performed.

### Conclusion

Further frontend observation now requires fresh manual login. Local read-only API calibration through `.env.local` remains separate and continues to be the source of populated run/case evidence.

## 2026-07-06 - Signed media URL coverage audit

### Goal

Clarify whether A3 can safely render real Ashr signed media links.

### Evidence

- Scanned 18 redacted P3 fixtures under `fixtures/a3/p3`.
- Saved coverage fixture: `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`.
- Added documentation: `docs/a3/p3_signed_media_url_coverage.md`.
- Found 2 `signed_url` keys, both nearest to file-like actions.
- Found no audio/image/video `signed_url` sample.
- Confirmed `output_path` evidence exists for audio and file actions.

### Conclusion

A3 should preserve signed URL metadata in redacted form, but should not render live signed media links. Current evidence confirms file-like signed URL fields only; audio/image/video signed URL behavior remains unconfirmed.

## 2026-07-06 - Chinese P3/A3 handoff summary

### Goal

Give the student team a plain-language explanation of current A3/P3 status and remaining evidence gaps.

### Added

- `docs/a3/p3_status_handoff_cn.md`

### Summary

The handoff explains what A3 has completed, what the real Ashr API proved, what the real frontend observation proved, why frontend detail pages still need a fresh login and UI-visible populated run, why failure class remains derived, and why live signed media rendering is still out of scope.

## 2026-07-06 - Frontend relogin observation checklist

### Goal

Prepare a safe next-step checklist for frontend calibration after the user manually logs into Ashr Lab again.

### Added

- `docs/a3/p3_frontend_relogin_observation_checklist.md`

### Summary

The checklist covers observation order, required evidence, safety rules, stop conditions, and the minimum successful frontend pass: login valid, one UI-visible populated run, one run detail, one case detail, and confirmation of expected-vs-actual / trace / tool call / failure label presence.

## 2026-07-06 - Frontend relogin checked

### Goal

Continue frontend calibration after the user manually logged into Ashr Lab again.

### Evidence

- Connected read-only to Chrome through the local CDP port.
- Confirmed Lab top-level pages loaded with authenticated frontend API calls returning `200`.
- Saved sanitized summary: `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`.
- No headers, cookies, tokens, response bodies, screenshots, email, or account-specific values were saved.

### Findings

- Login is valid again; the earlier `401`/session-expired blocker is no longer the current issue.
- Datasets still shows 0 UI-visible datasets and `No datasets match your filters.`
- Analytics still shows 0 agents, 0 datasets, and 0 graded runs.
- Trust still shows the run-tests-first empty state.

### Conclusion

The remaining blocker is data visibility, not login. A3 can cite the real frontend for navigation, filters, analytics modules, usage/quota modules, empty states, and trust/report inspiration, but still needs one UI-visible populated hosted run before confirming real frontend run detail, case detail, expected-vs-actual, trace/timeline, and native frontend failure labels.

## 2026-07-06 - Usage / Quota media calibration panel

### Goal

Run the next A3 Commercial Growth iteration with media coverage included, using real Ashr API and official frontend evidence without creating or mutating real objects.

### Chosen ROI item

Selected Usage / Quota + Media calibration panel/report enhancement.

This was the best single step because it combines:

- media direction from the group lead
- real API calibration
- official frontend workflow calibration
- small A3-owned implementation scope
- clear demo value for non-developers

### Evidence

Saved redacted evidence:

- `fixtures/a3/p3/ashr_media_api_calibration.redacted.json`
- `fixtures/a3/p3/ashr_media_run_case_sample.redacted.json`
- `fixtures/a3/p3/ashr_media_signed_url_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`
- `fixtures/a3/p3/ashr_frontend_usage_workflow.redacted.json`
- `docs/a3/p3_media_frontend_notes.md`

API findings:

- Read-only media/API calibration saw 3 datasets, 5 requests, and 2 runs.
- Signed URL paths remain confirmed only for file-like action shape.
- Direct API-key calls to `get_usage` and `billing_get_status` returned 403 OAuth-only messages.

Frontend findings:

- Usage page shows Images, Audio, and Files quota modules.
- Usage page calls `get_usage` and `billing_get_status`.
- Datasets page calls `list_datasets`, `list_requests`, and `list_folder_memberships`.
- Trust page calls `get_trust_certificate_status` and `preview_trust_certificate`.

### Implemented

- Added `summarizeUsageQuota()` to report builder.
- Added `usage_quota` to JSON export.
- Added Usage / Quota section to Markdown export.
- Added Usage / Quota evidence to dashboard console and print/PDF preview.
- Added tests for dashboard wiring and report builder summary.

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

- `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-media`

## 2026-07-06 - Official demo source 884/11925

- Added a dashboard data source for the official A3 refund demo: `P3 Official Demo 884/11925`.
- The source maps hosted Ashr run `11925` from dataset `884` into the existing A3 Run List, Case Detail, Expected vs Actual, Tool Call Diff, Failure Clusters, Media Readiness, and Report export flow.
- Updated P3 mapper support for official dataset wrappers under `response.dataset`.
- Preserved generated dataset media action types in `media_evidence`, so the official demo now exposes audio, file, and image channels in A3.
- Added tests for the official demo source and generated-dataset request provenance.
- Verification passed:

```text
node --test tests/a3/p3_ashr_mapper.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_fixture_builder.test.mjs
tests 41
pass 41
fail 0
```

- Browser smoke passed at `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11925.png`.

## 2026-07-06 - Official frontend dataset 884 observation

- Connected to the user's authenticated normal Chrome session through local CDP.
- Opened official Ashr dataset `884`.
- Confirmed official frontend shows `A3 Refund Demo Dataset`, Overview, `Test cases (5)`, and `Results (0)`.
- Confirmed official Test cases page shows the five generated refund cases with title, key, description, action count, and tag count.
- Opened `happy_path_text_valid_booking` in the official frontend.
- Confirmed official case detail shows TEST DETAILS, tags, ACTIONS, User/Agent actors, TEXT/AUDIO labels, and Tool Calls.
- Clicked `Open Most Recent Run`; official frontend still showed `Runs History / No runs found`.
- Tried direct `run=11925`; official frontend returned to dataset overview and did not show run `11925`.
- Added redacted evidence: `fixtures/a3/p3/ashr_dataset_884_official_frontend_observation.redacted.json`.
- Updated docs to clarify the current gap: A3 can display API run `11925` locally, but official Results does not list that API-created run.
- Confirmed Usage / Quota renders Images/Audio/Files evidence and OAuth-gated API status.
- Saved screenshot: `docs/screenshots/a3-dashboard-usage-quota-media.png`.

## 2026-07-06 - Official Ashr dashboard gap panel

### Goal

Compare the current A3 dashboard with the official Ashr Lab product structure and improve the safest, highest-value gap without copying account/security/cloud administration features.

### Evidence used

- Existing authenticated frontend page map: `docs/a3/p3_frontend_page_map.md`
- Existing frontend-to-MVP gap doc: `docs/a3/p3_frontend_to_a3_mvp_gap.md`
- Existing MVP recommendations: `docs/a3/p3_a3_mvp_recommendations.md`
- Existing redacted P3 API/frontend fixtures

No new real Ashr API calls were required for this round.

### Finding

A3 already covers the core evaluation workflow: run list, case detail, expected vs actual, trace timeline, tool-call diff, failure clusters, media evidence, and report export.

The largest remaining product difference is the official cloud-console shell: Datasets, Agents, Folders, Analytics, Usage, Trust, API Keys, and Team. For the student MVP, only the evaluation-review and reporting ideas should be copied. Account, key, team, billing, OAuth, public trust publishing, and hosted mutation flows remain out of scope.

### Implemented

- Added `docs/a3/p3_official_dashboard_gap_analysis.md`.
- Added `summarizeOfficialAshrGap()` in `services/report/report_builder.mjs`.
- Added `official_ashr_gap` to JSON reports.
- Added `Official Ashr Gap` to Markdown reports.
- Added an `Official Ashr Gap` dashboard panel.
- Added the same gap map to the print/PDF report preview.
- Added dashboard and report-builder test coverage.

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
- Confirmed `Official Ashr Gap` dashboard panel renders.
- Confirmed print/PDF report preview includes `Official Ashr Gap`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-gap.png`.

### Safety

- No real key, token, cookie, email, or signed URL was printed or saved.
- No `.env.local` change.
- No real Ashr create/delete/publish/invite/key-management action.
- Changes stayed inside A3-owned dashboard/report/test/doc paths.

## 2026-07-06 - Media readiness and cloud console polish

### Goal

Improve the A3 dashboard in the areas requested by the team: more media direction, a more polished product console, and a safe imitation of official login/cloud/admin product logic.

### Scope decision

Implemented:

- media readiness display
- signed URL safety posture
- official-style read-only cloud console shell
- UI polish for product-console feel
- JSON/Markdown/print report support

Not implemented:

- real login/OAuth
- real API-key create/revoke/show-secret UI
- real team invites
- billing or upgrade mutations
- real cloud create/delete/publish operations
- live signed media URL rendering

### Implemented

- Added `summarizeMediaReadiness()` in `services/report/report_builder.mjs`.
- Added `summarizeCloudConsoleShell()` in `services/report/report_builder.mjs`.
- Added JSON export fields:
  - `media_readiness`
  - `cloud_console_shell`
- Added Markdown/print sections:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added dashboard panels:
  - `Media Readiness`
  - `Cloud Console Shell`
- Added dashboard polish:
  - sidebar brand mark
  - topbar safety/status chips
  - Media and Cloud Shell nav entries
  - clearer badges and product-console panel styling
- Added documentation: `docs/a3/p3_media_cloud_console_polish.md`.
- Added dashboard/report-builder test coverage.

### Evidence

Used existing redacted fixtures only:

- `fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json`
- `fixtures/a3/p3/ashr_auth_check.redacted.json`
- `fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_sample.redacted.json`
- `fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json`

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
- Confirmed `Media Readiness` renders with 6 rows.
- Confirmed `Cloud Console Shell` renders with 8 rows.
- Confirmed print/PDF report preview includes `Media Readiness`.
- Confirmed print/PDF report preview includes `Cloud Console Shell`.
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-cloud-polish.png`
  - `docs/screenshots/a3-dashboard-cloud-shell.png`

### Safety

- No real Ashr API calls were required for this round.
- No key, token, cookie, email, browser header, account value, or raw signed URL was saved.
- `.env.local` was not modified.
- All cloud/admin behavior remains local read-only status display.

## 2026-07-06 - Media matrix and cloud action guardrails

### Goal

Continue polishing the media/cloud dashboard so it explains exact readiness and action boundaries, not just high-level status.

### Implemented

- Added a Media Channel Matrix inside `summarizeMediaReadiness()`.
- The matrix covers:
  - audio
  - files
  - images
  - video
  - VM stream
- Each media channel now reports:
  - usage/frontend observation
  - case evidence count
  - output path confirmation
  - signed URL confirmation
  - live preview policy
  - A3 decision
- Added Cloud Action Guardrails inside `summarizeCloudConsoleShell()`.
- The guardrails separate safe local actions from disabled official cloud/admin actions:
  - local fixture switching
  - local export
  - local print/PDF
  - auth/workspace/request/usage read-only viewing
  - disabled OAuth login
  - disabled hosted dataset creation
  - disabled API-key mutation
  - disabled team invite
  - disabled billing upgrade
  - disabled Trust publishing
  - disabled cloud deletion
- Dashboard now renders:
  - `media-channel-matrix`
  - `cloud-action-list`
- Print/PDF report now includes both tables.
- JSON/Markdown report already include both through `media_readiness` and `cloud_console_shell`.

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
- Confirmed no horizontal overflow at the tested viewport.
- Saved screenshots:
  - `docs/screenshots/a3-dashboard-media-matrix.png`
  - `docs/screenshots/a3-dashboard-cloud-guardrails.png`

### Safety

- Still no real Ashr API calls.
- Still no `.env.local` changes.
- Still no live signed URL rendering.
- Still no real login, key, team, billing, trust, create, delete, or publish action.

## 2026-07-07 - Official UI-compatible run 11926

### Why this was needed

The earlier hosted run `11925` existed through the API, but it used the local clone's `result.cases[]` structure. Official Ashr frontend evidence points to the Results UI reading `result.tests[].action_results[]`, so A3 needed a closer official-shape run before saying the result path was properly tested.

### Work completed

- Built `fixtures/a3/p3/ashr_dataset_884_demo_run_result.official_ui_tests.synthetic.json`.
- Created exactly one real Ashr run for dataset `884` using the official-style `tests[]` result shape.
- New run id: `11926`.
- Confirmed `get_run(11926)` returns 5 tests.
- Confirmed `list_runs(dataset_id=884)` returns `11926`.
- Confirmed frontend-style `list_runs(dataset_id=884, summary_only=true)` returns `11926`.
- Updated dashboard source `p3-official-demo` from run `11925` to run `11926`.
- Saved screenshot: `docs/screenshots/a3-dashboard-official-demo-884-11926.png`.

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
- Confirmed run `11926`, 5 cases, 40% pass rate, 56.4 average score, 5 media-evidence cases.

### Remaining gap

The in-app browser was not logged in to Ashr Lab, so this round did not visually confirm the official Results tab. The next manual/browser step is to refresh `https://lab.ashr.io/?tab=analysis&dataset=884` in a logged-in Ashr browser and check whether Results lists run `11926`.

## 2026-07-07 - Commercial Release Gate

### Goal

Move A3 closer to a paid release-intelligence workflow by adding a release gate that can tell a team whether an agent release should be approved, reviewed, or blocked.

### Work completed

- Added `summarizeReleaseGate()` in `services/report/report_builder.mjs`.
- Added `release_gate` to JSON report export.
- Added `## Release Gate` to Markdown report export.
- Added Release Gate section to print/PDF report preview.
- Added Release Gate dashboard panel.
- Added dashboard wiring tests for the panel and render loop.
- Added report-builder tests for blocked risky evidence and approved clean evidence.
- Added Growth-Auditor handoff:
  - `docs/a3/p3_release_gate_growth_round_2026_07_07.md`
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-release-gate-11926.png`

### Current official demo gate result

For dataset `884` / run `11926`:

- Decision: `Block release`
- Risk score: `70`
- Failed checks: `2`
- Blocks merge: `yes`
- Required approvers: `4`

Why blocked:

- 40% pass rate is below the 95% commercial release threshold.
- One case has `missing_required_tool`.

### Verification

Command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs tests/a3/a3_fixture_builder.test.mjs
```

Result:

```text
tests 43
pass 43
fail 0
```

Browser smoke:

- Opened `http://127.0.0.1:5173/apps/dashboard/index.html?source=p3-official-demo`.
- Confirmed Release Gate renders `Block release`, risk score, failed checks, blockers, and approver count.

### Commercial value

This is the first A3 feature that directly maps to a paid enterprise workflow: block risky agent releases, generate reviewer evidence, and give managers a sign-off artifact.

## 2026-07-07 - PR Gate workflow and audit bundle

### Goal

Turn the local Release Gate into a PR-facing and audit-facing workflow that looks closer to a commercial release-intelligence product.

### Work completed

- Added `summarizeReleaseWorkflow()` in `services/report/report_builder.mjs`.
- Added a GitHub Check payload shape:
  - check name: `Ashr++ Release Gate`
  - conclusion: `success`, `neutral`, or `failure`
  - blocks-merge signal
  - output title, summary, and evidence text
- Added a PR comment Markdown template.
- Added waiver policy:
  - required fields
  - exceptional-only waiver for blocked releases
  - 1-day maximum expiry for blocked releases
- Added reviewer workflow:
  - review state
  - release/safety/runner/judge/evidence/A3 review lanes
  - next actions
- Added audit bundle manifest:
  - JSON report
  - Markdown report
  - print/PDF report
  - case evidence
  - redacted fixtures
  - screenshot evidence
- Added incident replay pack from top-risk failed cases.
- Added `release_workflow` to JSON report export.
- Added `## PR Gate / Review Workflow` to Markdown report export.
- Added `PR Gate & Audit` dashboard panel.
- Added `PR Gate & Audit Workflow` to print-ready report preview.

### Evidence

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

### Commercial value

A3 now emits the artifacts a buyer expects around release control: a PR check payload, a PR comment body, waiver guidance, reviewer lanes, audit manifest, and incident replay case list. It is still not a live GitHub required check, but the contract shape is now present and tested.

## 2026-07-07 - Gate CLI contract and hashed audit manifest

### Goal

Turn the release gate workflow into a command-shaped artifact that future CI and GitHub PR checks can consume.

### Work completed

- Added `services/report/a3_gate_cli.mjs`.
- Added `buildGateCliPayload()` for programmatic gate packaging.
- Added `renderGateCliMarkdown()` for human-readable gate output.
- Added command arguments:
  - `--runs`
  - `--grades`
  - `--coverage`
  - `--thresholds`
  - `--release-version`
  - `--environment`
  - `--owner`
  - `--source`
  - `--json`
  - `--markdown`
  - `--strict-exit`
  - `--no-fail`
- Added `fixtures/a3/release_gate_thresholds.json`.
- Added configurable release thresholds to `summarizeReleaseGate()`.
- Added threshold values to `release_gate`.
- Added hashed audit manifest for CLI input files.
- Added workspace-relative artifact paths to avoid writing local user directories into CLI output.
- Added separate exit behavior:
  - `--strict-exit` for CI merge blocking
  - `--no-fail` for local report generation
- Added redacted CLI evidence fixture:
  - `fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json`
- Added tests:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

Focused command:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 4
pass 4
fail 0
```

### Commercial value

This gives A3 the first real CI-shaped contract: `ashr gate --json`. A future GitHub Action can run this command, read `release_workflow.github_check`, attach the PR comment, and block merge when `release_gate.pr_gate.blocks_merge` is true.

### Follow-up hardening

- Added output file options:
  - `--output-json`
  - `--output-md`
  - `--output-check`
  - `--output-pr-comment`
- Added GitHub Check Run payload output with annotations for top-risk cases.
- Added PR comment Markdown file output.
- Added lightweight output redaction scrubber.
- Added committed redacted PR artifacts:
  - `fixtures/a3/p3/a3_gate_cli_github_check.redacted.json`
  - `fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md`
  - `fixtures/a3/p3/a3_gate_cli_report.redacted.md`
- Expanded CLI tests to cover output files, annotations, redaction, and committed artifacts.

Updated verification:

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Result:

```text
tests 7
pass 7
fail 0
```

## 2026-07-07 - GitHub dry-run request adapter

### Goal

Turn the existing A3 gate CLI payload into GitHub-shaped dry-run requests before any live GitHub token or required check is introduced.

### Work completed

- Added `services/report/a3_github_integration.mjs`.
- Added `buildGitHubCheckRunRequest()` for create/update Check Run request shapes.
- Added `buildPrCommentUpsertPlan()` for marker-based PR comment create/update plans.
- Added `buildGitHubActionWorkflowExample()` for a future GitHub Actions workflow.
- Required callers to pass a current `headSha` so stale fixture SHAs are not reused.
- Let caller-provided `detailsUrl` override fixture/demo URLs.
- Generated redacted dry-run fixtures:
  - `fixtures/a3/p3/a3_github_check_create_request.redacted.json`
  - `fixtures/a3/p3/a3_github_pr_comment_upsert_plan.redacted.json`
- Generated workflow example:
  - `docs/a3/p3_github_action_workflow_example.yml`
- Added focused test coverage:
  - `tests/a3/a3_github_integration.test.mjs`
- Documented the round:
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

### Current interpretation

A3 can now produce safe GitHub-shaped release gate artifacts without calling GitHub. This is still dry-run only: no GitHub API call, no token, no real PR comment, and no required check has been created.

## 2026-07-07 - Generated artifact manifest for enterprise audit

### Goal

Hash the files generated by the A3 Gate CLI so an enterprise reviewer can verify that exported release evidence was not changed after generation.

### Work completed

- Added `buildGeneratedArtifactManifest()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--output-manifest`
- The manifest now records hashes for:
  - JSON gate report
  - Markdown gate report
  - GitHub Check Run payload
  - PR comment Markdown
- The manifest records:
  - schema version `a3.generated_artifact_manifest.v1`
  - run id
  - release decision
  - risk score
  - merge-blocking status
  - GitHub check conclusion
  - content type
  - byte size
  - SHA-256
  - workspace-relative path
- Added committed redacted manifest fixture:
  - `fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json`
- Added tests for generated artifact hash correctness and redacted paths.
- Added documentation:
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

### Current interpretation

A3 now hashes both sides of the gate evidence chain: input fixtures in `audit_manifest.artifacts` and generated output files in `a3.generated_artifact_manifest.v1`. This is still not a signed immutable audit bundle, but it is a stronger foundation for enterprise sign-off.

## 2026-07-07 - File-backed waiver validation

### Goal

Move waiver handling from policy text into a local validation contract that can support enterprise review.

### Work completed

- Added `validateWaiverRequest()` in `services/report/a3_gate_cli.mjs`.
- Added CLI arguments:
  - `--waiver`
  - `--generated-at`
- Added `waiver_review` to Gate CLI JSON output.
- Added waiver file hashing to `audit_manifest.artifacts`.
- Added Waiver Review section to the Markdown report.
- Added redacted waiver fixtures:
  - `fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json`
- Added tests for:
  - valid exceptional waiver
  - expired/incomplete waiver rejection
  - committed waiver review fixture
  - Markdown Waiver Review output
- Added documentation:
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

### Current interpretation

A3 can now validate waiver evidence locally. A valid waiver is evidence for reviewer sign-off, not an automatic unblock: blocked releases still remain blocked until a future live policy explicitly changes CI behavior.

## 2026-07-07 - File-backed signed approval validation

### Goal

Move exception approval from informal sign-off into a structured local approval validation contract.

### Work completed

- Added `validateApprovalRecord()` in `services/report/a3_gate_cli.mjs`.
- Added CLI argument:
  - `--approval`
- Added `approval_review` to Gate CLI JSON output.
- Added approval file hashing to `audit_manifest.artifacts`.
- Added Approval Review section to the Markdown report.
- Added redacted approval fixtures:
  - `fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json`
  - `fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json`
- Added tests for:
  - valid exception approval
  - invalid too-permissive approval
  - missing required signer roles
  - self-approval separation-of-duties failure
  - committed approval review fixture
  - Markdown Approval Review output
- Added documentation:
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

### Current interpretation

A3 can now validate file-backed approval evidence for a blocked-release exception. This is not cryptographic signing and not durable backend persistence yet; it is the local contract needed before approval records can be bound to GitHub/OIDC/SSO identities and immutable audit bundles.

## 2026-07-07 - Audit bundle index and root hash

### Goal

Turn the scattered A3 gate artifacts into one audit bundle index with a stable root hash and a local chain-of-custody trail.

### Work completed

- Added `buildAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--output-bundle`
- Added schema:
  - `a3.audit_bundle_index.v1`
- Added bundle root hash generation over canonical JSON.
- Added self-hash exclusion so the bundle index does not hash its own file bytes.
- Added artifact grouping:
  - source inputs
  - generated outputs
  - governance records
  - custody records
- Added chain-of-custody events:
  - `gate_built`
  - `input_artifacts_hashed`
  - `generated_artifacts_hashed`
  - `waiver_reviewed`
  - `approval_reviewed`
  - `bundle_index_written`
- Added byte size and content type metadata for input audit artifacts.
- Added redacted bundle fixture:
  - `fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json`
- Added Growth-Auditor report:
  - `docs/a3/p3_growth_auditor_audit_bundle_index_2026_07_07.md`
- Added implementation doc:
  - `docs/a3/p3_audit_bundle_index_growth_2026_07_07.md`
- Added tests in:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Focused result after this pass: all A3 Gate CLI tests pass.

### Current interpretation

A3 now has the local evidence package layer that sits above gate JSON, Markdown report, GitHub check payload, waiver, and approval. This is not immutable enterprise storage yet, but it is the root-hash contract future storage, verifier, and GitHub artifact upload can rely on.

## 2026-07-07 - Audit bundle verifier

### Goal

Add the verification command that proves an A3 audit bundle index still matches its artifact hashes and custody event hashes.

### Work completed

- Added `verifyAuditBundleIndex()` in `services/report/a3_gate_cli.mjs`.
- Added `renderBundleVerificationMarkdown()` in `services/report/a3_gate_cli.mjs`.
- Added CLI option:
  - `--verify-index`
- Added verification schema:
  - `a3.audit_bundle_verification.v1`
- Verification now checks:
  - bundle root hash
  - artifact SHA-256 hashes
  - artifact byte sizes
  - missing artifact files
  - unsafe local paths
  - custody event hashes
  - `previous_event_hash` chain links
- Added redacted verification fixture:
  - `fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json`
- Added implementation doc:
  - `docs/a3/p3_audit_bundle_verifier_growth_2026_07_07.md`
- Added tests in:
  - `tests/a3/a3_gate_cli.test.mjs`

### Verification

```text
node --test tests/a3/a3_gate_cli.test.mjs
```

Focused result after this pass:

```text
tests 20
pass 20
fail 0
```

### Current interpretation

A3 can now generate a local audit bundle index and verify it later. This closes the first verifier gap and makes the bundle/root-hash work actually usable by reviewers and auditors.

## 2026-07-07 - Official frontend mirror clean-room integration

### Goal

Use the offline Ashr frontend mirror as product-reference evidence without copying official source code or sensitive browser/session data.

### Work completed

- Added report-builder summary support for the clean-room frontend mirror fixture.
- Added JSON export field:
  - `official_frontend_mirror`
- Added Markdown report section:
  - `Official Frontend Mirror`
- Added dashboard panel:
  - `Official Frontend Mirror`
- Added print/PDF report section for the frontend mirror summary.
- Wired the dashboard to load:
  - `fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json`
- Added tests in:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`
- Added implementation note:
  - `docs/a3/p3_frontend_mirror_analysis_2026_07_07.md`
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-official-frontend-mirror.png`

### Current interpretation

The mirror is now represented as a clean-room product map: official navigation, API method groups, visible labels, copy/partial/future/out-of-scope decisions, and safety boundaries. A3 still does not copy official code, assets, OAuth, key management, billing, team administration, cookies, tokens, or raw signed URLs.

## 2026-07-07 - Release War Room

### Goal

Turn the existing Release Gate, PR Gate, incident replay, audit evidence, and official frontend parity signals into one reviewer-facing release decision packet.

### Work completed

- Added `summarizeReleaseWarRoom()` in `services/report/report_builder.mjs`.
- Added schema:
  - `a3.release_war_room.v1`
- Added JSON export field:
  - `release_war_room`
- Added Markdown report section:
  - `Release War Room`
- Added dashboard panel:
  - `Release War Room`
- Added print/PDF report section:
  - `Release War Room`
- Added redacted fixture:
  - `fixtures/a3/p3/a3_release_war_room_11926.redacted.json`
- Added implementation doc:
  - `docs/a3/p3_release_war_room_growth_2026_07_07.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_release_war_room_2026_07_07.md`
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-release-war-room.png`
- Added tests in:
  - `tests/a3/report_builder.test.mjs`
  - `tests/a3/dashboard_wiring.test.mjs`

### Current interpretation

The Release War Room is the first A3 operational cockpit over release evidence. It gives a no-go/review/ship-ready decision, revenue risk score, merge-block status, waiver requirement, incident replay count, required audit artifact count, reviewer lanes, and official-product parity context. It does not call live APIs and does not store secrets, cookies, tokens, or live signed URLs.

## 2026-07-07 - Official Parity Roadmap and Media Evidence Queue

### Goal

Move the official frontend mirror summary from background evidence into an actionable dashboard/report roadmap, and make media evidence review more concrete.

### Work completed

- Re-checked A1/A2 handoff assumptions through A3 tests:
  - A1-style run/trace/tool-call fixtures still feed A3 normalization and tool-call diff logic.
  - A2 G3 grade/coverage fixtures still join into A3 reports and filters.
- Added dashboard panel:
  - `Official Parity Roadmap`
- Added Media Readiness sub-panel:
  - `Media Evidence Queue`
- Added print/PDF report section:
  - `Official Parity Roadmap`
- Updated Report Center copy to include official parity roadmap evidence.
- Added report-builder tests for:
  - `summarizeOfficialParityRoadmap()`
  - `media_readiness.evidence_queue`
  - JSON export `official_parity_roadmap`
  - Markdown `Official Parity Roadmap`
- Added dashboard wiring tests for:
  - roadmap panel IDs/functions
  - media evidence queue IDs/functions
- Added implementation note:
  - `docs/a3/p3_official_parity_media_queue_2026_07_07.md`
- Saved browser verification screenshots:
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

### Current interpretation

A3 now explains not only what it already copied from official Ashr, but also the next build order and the cloud/admin boundaries that should remain disabled. Media evidence is still metadata-only, but reviewers can now see which cases are queued for media review and what evidence is missing.

## 2026-07-07 - Incident Replay Queue

### Goal

Upgrade A3 from a release dashboard into a replay-first incident review workflow.

### Work completed

- Added `summarizeIncidentReplayQueue()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `incident_replay_queue`
- Added Markdown report section:
  - `Incident Replay Queue`
- Added dashboard panel:
  - `Incident Replay`
- Added print/PDF report section:
  - `Incident Replay Queue`
- Updated Report Center copy to include incident replay evidence.
- Added report-builder tests that prove the replay queue packages:
  - A1 trace / observation readiness
  - A1 tool-call diff evidence
  - A2 judge evidence
  - media metadata evidence
  - reviewer packet artifacts
- Added dashboard wiring tests for the Incident Replay panel.
- Added implementation note:
  - `docs/a3/p3_incident_replay_queue_growth_2026_07_07.md`
- Saved browser verification screenshot:
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

### Current interpretation

Incident Replay Queue is a commercial workflow, not a cosmetic list. It turns failed cases into ranked replay packets with owner lanes, trace readiness, tool-call divergence, A2 judge evidence, media metadata, and release-blocker state. This moves A3 closer to a platform that can stop risky releases and help reviewers reproduce failures before sign-off.

## 2026-07-07 - Reviewer Workflow Board

### Goal

Convert incident replay evidence into an owned reviewer workflow board.

### Work completed

- Added `summarizeReviewerWorkflowBoard()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `reviewer_workflow_board`
- Added Markdown report section:
  - `Reviewer Workflow Board`
- Added dashboard panel:
  - `Reviewer Workflow`
- Added print/PDF report section:
  - `Reviewer Workflow Board`
- Added reviewer lanes, review states, missing-artifact checks, waiver state, approval readiness, and next actions.
- Kept the board calibrated to:
  - A1 trace and observation readiness
  - A1 tool-call diffs
  - A2 judge evidence
  - A2 coverage availability
  - metadata-only media evidence
- Added report-builder tests for the reviewer workflow board.
- Added dashboard wiring tests for the Reviewer Workflow panel and print report.
- Added implementation note:
  - `docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md`
- Included Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_reviewer_workflow_2026_07_07.md`
- Browser-smoke verified Reviewer Workflow with `Blocked`, 3 open official-demo items, 6 reviewer lanes, and A1/A2 calibration counts.
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-reviewer-workflow-board.png`

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
44 tests
44 pass
0 fail
```

Final A3 suite result:

```text
127 tests
127 pass
0 fail
```

Export firewall result:

```text
1 generated-artifact secret/path scan
1 pass
0 fail
```

Full command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
80 tests
80 pass
0 fail
```

### Current interpretation

Reviewer Workflow Board is the next layer after Incident Replay Queue. Incident Replay says which failed cases must be replayed; Reviewer Workflow says who owns them, what evidence is missing, and whether waiver or approval can proceed. This makes A3 closer to a release-governance product while still staying local-only and safe.

## 2026-07-07 - Official Code Crawl Parity

### Goal

Use the official Ashr frontend mirror as clean-room product evidence and convert code-level page/module signals into A3 parity reporting.

### Work completed

- Added redacted code-crawl fixture:
  - `fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json`
- Added `summarizeOfficialCodeCrawlParity()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `official_code_crawl_parity`
- Added Markdown report section:
  - `Official Code Crawl Parity`
- Added dashboard panel:
  - `Official Code Crawl`
- Added print/PDF report section:
  - `Official Code Crawl Parity`
- Added report-builder tests proving the crawl summary does not commit official source and maps A3 copy/out-of-scope decisions.
- Added dashboard-wiring tests for fixture loading, panel IDs, renderers, exports, and print report.
- Added implementation note:
  - `docs/a3/p3_official_code_crawl_parity_growth_2026_07_07.md`
- Added clean-room explorer note:
  - `docs/a3/p3_official_frontend_code_crawl_cleanroom_2026_07_07.md`
- Added Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_code_crawl_parity_2026_07_07.md`
- Browser-smoke verified Official Code Crawl with 9 chunk rows, 6 parity target rows, and `source committed no`.
- Saved browser verification screenshot:
  - `docs/screenshots/a3-dashboard-official-code-crawl-parity.png`

### A1/A2 calibration

- Results review maps back to A1 run/case/trace plus A2 score/pass/fail/failure class.
- Trace observability maps back to A1 trace/tool-call evidence plus A2 judge remediation.
- Media evidence maps back to A1 media metadata and A2 media failure taxonomy.
- Trust/audit maps back to A1/A2 evidence packaged by A3 report, audit bundle, and verifier.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
46 tests
46 pass
0 fail
```

Full command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
82 tests
82 pass
0 fail
```

### Current interpretation

Official Code Crawl Parity gives A3 a stronger product reference without copying official source. It shows which official frontend chunks imply results review, trace observability, media evidence, trust/audit, usage, API keys, and team admin. A3 should copy the release-intelligence workflow and keep admin, billing, and secret flows out of scope.

## 2026-07-07 - Observability Replay Matrix

### Goal

Turn failed-case replay into production-style observability replay evidence.

### Work completed

- Added `summarizeObservabilityReplayMatrix()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `observability_replay_matrix`
- Added Markdown report section:
  - `Observability Replay Matrix`
- Added dashboard panel:
  - `Observability Replay`
- Added print/PDF report section:
  - `Observability Replay Matrix`
- Added replay lanes for:
  - trace timeline
  - tool errors
  - latency / duration
  - A2 judge link
  - media metadata
  - official Observability parity
- Added per-case production replay items with production risk, observability state, trace counts, tool/error counts, judge counts, media counts, and next action.
- Added implementation note:
  - `docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md`
- Added clean-room explorer note:
  - `docs/a3/p3_observability_replay_cleanroom_2026_07_07.md`
- Added Growth-Auditor note:
  - `docs/a3/p3_growth_auditor_observability_replay_2026_07_07.md`

### A1/A2/Official calibration

- A1 supplies trace events, observations, tool-call diffs, latency/duration fields, and tool-error text.
- A2 supplies score, pass/fail, primary failure class, judge evidence, and remediation.
- Official code crawl supplies ObservabilityPage / trace / latency / error product signals without copying official source.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
48 tests
48 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
84 tests
84 pass
0 fail
```

Browser smoke:

- Opened the local dashboard with the official demo source.
- Confirmed `Observability Replay`, `Trace Timeline`, and `Official Observability Parity` render.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-observability-replay-matrix.png`

### Current interpretation

Observability Replay Matrix is the production replay layer A3 was missing. It connects incident replay to trace evidence, tool/error evidence, A2 judge findings, media metadata, and official Observability parity. This moves A3 closer to a sellable release-intelligence platform that can block risky agent releases and support incident review.

## 2026-07-07 - Regression Factory

### Goal

Turn failed incident replay cases into regression-test candidates for the next release gate.

### Work completed

- Added `summarizeRegressionFactory()` in `services/report/report_builder.mjs`.
- Added JSON export field:
  - `regression_factory`
- Added Markdown report section:
  - `Regression Factory`
- Added dashboard panel:
  - `Regression Factory`
- Added print/PDF report section:
  - `Regression Factory`
- Added per-candidate fields:
  - regression id
  - generator state
  - owner lane
  - coverage status
  - required contracts
  - proposed assertions
  - generated artifact plan
  - next action
- Added implementation note:
  - `docs/a3/p3_regression_factory_growth_2026_07_07.md`
- Added contract delta note from integration explorer:
  - `docs/a3/p3_a1_a2_a3_contract_delta_2026_07_07.md`
- Added official frontend parity backlog:
  - `docs/a3/p3_official_frontend_parity_backlog_2026_07_07.md`
- Added Growth-Auditor round note:
  - `docs/a3/p3_growth_auditor_round_2026_07_07_enterprise_push.md`

### A1/A2/Official calibration

- A1 supplies trace, observation, expected vs actual, tool-call, media metadata, and replay evidence.
- A2 supplies pass/fail, score, primary failure class, judge evidence, severity, remediation, and coverage.
- Official code crawl supplies Results review parity signals without copying official source.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
50 tests
50 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
86 tests
86 pass
0 fail
```

Browser smoke:

- Opened the local dashboard with the official demo source.
- Confirmed `Regression Factory`, candidate count, coverage information, A1 Trace Capture, and A2 Judge Contract render.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-regression-factory.png`

### Current interpretation

Regression Factory is the next commercial layer after Incident Replay and Observability Replay. Incident Replay says what failed, Observability Replay says whether the evidence is replayable, and Regression Factory says whether the failure can become a repeatable regression candidate before the next release. This moves A3 closer to a paid release-intelligence workflow instead of a one-time demo dashboard.

## 2026-07-07 - Export Redaction Firewall And Dashboard Webapp Split

### Goal

Improve A3 enterprise export safety, strengthen A1/A2 data compatibility, and migrate the dashboard away from a single oversized HTML file.

### Work completed

- Added shared export firewall module:
  - `services/report/export_redaction_firewall.mjs`
- Added `summarizeExportRedactionFirewall()` to `services/report/report_builder.mjs`.
- Added `export_redaction_firewall` to JSON report exports.
- Added `Export Redaction Firewall` to Markdown and print/PDF report output.
- Added CSV cell scrubbing and formula-injection hardening.
- Reused the shared firewall from the A3 Gate CLI.
- Added dashboard `Export Safety` panel.
- Split dashboard webapp files:
  - `apps/dashboard/index.html`
  - `apps/dashboard/src/app.mjs`
  - `apps/dashboard/src/styles.css`
- Reduced `index.html` from more than 3,000 lines to about 400 lines.
- Strengthened A1/A2 input normalization in `report_builder.mjs`.
- Added direct compatibility for:
  - A1 RunResult root fixtures
  - A1 loose case lists
  - A1 `ashr.clone.run.v1` run fixture shape
  - A2 single run fixtures
  - A2 single local judge result fixtures
  - Existing A3 aggregate run fixtures
  - Existing A2 aggregate grade reports
- Added implementation note:
  - `docs/a3/p3_dashboard_webapp_migration_2026_07_07.md`
- Added Export Redaction Firewall docs:
  - `docs/a3/p3_growth_auditor_redaction_firewall_2026_07_07.md`
  - `docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md`

### A1/A2 calibration

- A1 compatibility now maps agent output, expected output, tool calls, observations, trace events, and optional media evidence into A3 case fields.
- A2 compatibility now maps single judge results and aggregate grade reports into pass/fail, score, failure class, severity, judge modes, and remediation evidence.

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
55 tests
55 pass
0 fail
```

Full A3 command:

```text
node --test tests/a3/a3_fixture_builder.test.mjs tests/a3/a3_gate_cli.test.mjs tests/a3/a3_github_integration.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/p3_ashr_mapper.test.mjs
```

Full result:

```text
91 tests
91 pass
0 fail
```

Browser smoke:

- Served local dashboard at `http://127.0.0.1:4173/apps/dashboard/index.html`.
- Confirmed split webapp loads `src/app.mjs` and `src/styles.css`.
- Confirmed dashboard renders 32 cases, 6.3% pass rate, and Export Safety status `passed`.
- Browser console error log was empty.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-webapp-export-safety.png`

### Current interpretation

A3 is now less brittle. It no longer depends only on hand-shaped mock fixtures, and the dashboard is easier for the team to maintain because HTML, JS, and CSS have separate ownership boundaries.

## 2026-07-07 - Raw A1/A2 Dashboard Sources

### Goal

Close the remaining UI gap from the A1/A2 compatibility work: the report builder could consume raw A1/A2 data, but the dashboard Data selector did not expose those raw sources.

### Work completed

- Added `Raw A1 RunResult` to the dashboard Data selector.
- Added `Raw A2 Single Case` to the dashboard Data selector.
- Wired `raw-a1` to `docs/a1/evidence/local_run_30.json`.
- Wired `raw-a2` to:
  - `fixtures/a2/runs/a2_s004_missing_tool.json`
  - `fixtures/a2/results/a2_s004_missing_tool_grade.json`
- Added source labels for raw A1 and raw A2.
- Added `resetCalibrationState()` so switching from P3 samples to raw A1/A2 does not leave stale request/quota/auth data in state.
- Added dashboard wiring tests for raw A1/A2 sources.
- Added implementation note:
  - `docs/a3/p3_raw_a1_a2_dashboard_sources_2026_07_07.md`

### Verification

Focused command:

```text
node --test tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
56 tests
56 pass
0 fail
```

Browser smoke:

- `?source=raw-a1`: 1 run, 30 cases, 100% pass rate, Export Safety `passed`.
- `?source=raw-a2`: 1 run, 1 case, 0% pass rate, Export Safety `passed`.
- Browser error log was empty.
- Saved screenshot:
  - `docs/screenshots/a3-dashboard-raw-a2-source.png`

### Current interpretation

The A1/A2 compatibility work is now visible from the dashboard, not only proven in unit tests. This makes the A3 handoff easier to demo and easier for A1/A2 teammates to validate.

## 2026-07-07 - SaaS API Store And Hosted Report Slice

### Goal

Move A3 from a static fixture dashboard toward a SaaS-shaped product path without breaking the current mock/raw A1/raw A2/P3 demo sources.

### Work completed

- Added a DB-ready A3 store abstraction:
  - `services/report/a3_store.mjs`
  - Supports memory store, JSON-file-backed store, fixture-backed source loading, run list, run detail, case detail, and shareable report persistence.
- Added a minimal A3 API server:
  - `services/report/a3_api_server.mjs`
  - Supports `GET /api/a3/health`, `GET /api/a3/db-contract`, `GET /api/a3/dashboard`, `GET /api/a3/runs`, `GET /api/a3/runs/:runId`, `GET /api/a3/cases/:caseId`, `POST /api/a3/reports/share`, and `GET /api/a3/reports/:reportId`.
- Added shareable hosted report payload builder:
  - `services/report/a3_shareable_report.mjs`
  - Wraps existing JSON/Markdown report outputs into `a3.shareable_report.v1`.
  - Reuses the export redaction firewall before a report is considered shareable.
- Added dashboard API client and component boundary:
  - `apps/dashboard/src/api-client.mjs`
  - `apps/dashboard/src/components/saas-runtime-panel.mjs`
- Added dashboard UI wiring:
  - New `API-backed Mock` Data source.
  - New `SaaS Runtime` panel showing API and DB-ready contract.
  - New `Share Hosted Report` action in Report Center.
- Added SaaS migration plan:
  - `docs/a3/p3_saas_api_db_migration_2026_07_07.md`
  - Covers 30 growth points across API, DB, app components, hosted reports, A1/A2 compatibility, secret safety, and verification evidence.

### Current interpretation

This is not yet a full SaaS app, but it changes the architecture direction in the right way:

- Static -> API-backed: dashboard can load the same A3 data shape through `/api/a3/dashboard`.
- Mock fixture -> DB data: store interface now hides whether data came from memory, JSON file, fixtures, or a future SQL adapter.
- HTML blob -> app components: the SaaS Runtime panel is now a real component module.
- Report export -> shareable hosted report: report output can be sealed, redacted, hashed, and stored behind a share URL path.

### Next highest-value targets

- Add a real SQL adapter behind `a3_store.mjs` after A1 chooses Postgres/MySQL/SQLite migration tooling.
- Add hosted report route rendering, not only hosted report payload creation.
- Add import endpoints for A1 RunResult and A2 GradeResult so API data can be created without hand-loaded fixtures.

## 2026-07-07 - SaaS Admin Console Shell

### Goal

Add the missing SaaS product-console areas the team lead called out: login, cloud/team management, usage, API keys, team, and trust. Keep it clean-room and safe: no real API-key creation, no real team invite, no real billing mutation, no real Trust publish, and no copied private frontend source.

### Work completed

- Added `services/report/a3_saas_admin.mjs`.
  - Produces `a3.saas_admin_console.v1`.
  - Covers Login, Organization/Project, Team, API Keys, Usage, Trust, Cloud Management, A1/A2 compatibility, and action plans.
  - Every sensitive cloud action is explicitly marked `read_only`, `plan_only`, `mock_only`, or `disabled`.
- Extended `services/report/a3_store.mjs`.
  - Adds `getSaasAdminConsole(...)`.
  - Adds `planSaasAdminAction(...)`.
  - Adds `saas_admin_console` to `/api/a3/dashboard` payload.
  - Extends DB contract with `users`, `team_members`, `roles`, `api_keys`, and `trust_reports`.
- Extended `services/report/a3_api_server.mjs`.
  - Adds `GET /api/a3/admin/console`.
  - Adds `POST /api/a3/admin/actions/plan`.
- Extended dashboard.
  - New `SaaS Admin Console` panel.
  - Shows Login, Team roster, Usage, API key metadata, Trust status, Cloud Action Plan, and A1/A2 compatibility counts.
  - Uses API action planning in API-backed mode and local plan state in static mode.
- Added `apps/dashboard/src/components/saas-admin-console.mjs`.
- Added tests:
  - `tests/a3/a3_saas_admin.test.mjs`
  - Store/API/dashboard wiring coverage for admin console and action planning.

### Safety boundary

- No real Ashr API key was read, created, printed, saved, or revoked.
- No real team invite, billing change, Trust publish, or OAuth login flow was executed.
- API key rows are metadata-only with redacted prefixes.
- The implementation uses clean-room product behavior already captured in redacted A3/P3 notes and fixtures.

### Current interpretation

A3 now looks more like a SaaS console instead of only a run/report dashboard. It still does not provide real auth/RBAC/API-key mutation, but it shows the exact product surfaces and guardrails needed before those become real hosted features.

## 2026-07-07 - API Ingest, Hosted Report Page, And Enterprise Readiness

### Goal

Continue the large SaaS plan by moving A3 from fixture-only reporting toward API-ingested evidence, hosted report viewing, self-host readiness, and enterprise audit posture. Keep A1 runner semantics and A2 judge semantics unchanged.

### Work completed

- Extended `services/report/a3_store.mjs`.
  - Added `importA1RunResult(...)`.
  - Added `importA2GradeResult(...)`.
  - Added `getEnterpriseReadiness(...)`.
  - Added API contract entries for A1/A2 import routes, hosted report HTML, and enterprise readiness.
- Extended `services/report/a3_api_server.mjs`.
  - Added `POST /api/a3/import/a1-run-result`.
  - Added `POST /api/a3/import/a2-grade-result`.
  - Added `GET /api/a3/enterprise/readiness`.
  - Added `GET /reports/:reportId` as a real HTML hosted-report route.
- Extended `services/report/a3_shareable_report.mjs`.
  - Added `renderShareableReportHtml(...)`.
  - Hosted reports render only redacted/shareable report payload fields and sealed evidence metadata.
- Added Enterprise Readiness.
  - `services/report/a3_enterprise_readiness.mjs` produces `a3.enterprise_readiness.v1`.
  - Dashboard now includes an Enterprise Readiness panel for self-host/audit review.
  - The readiness report summarizes A1 run/trace/tool-call evidence, A2 grade/judge evidence, DB contract readiness, admin-console guardrails, blockers, capabilities, and next actions.
- Added self-host contract artifact:
  - `docs/a3/p3_self_host_console_growth_2026_07_07.md`
  - `tests/a3/self_host_console_contract.test.mjs`
- Added Growth-Auditor round artifact:
  - `docs/a3/p3_growth_auditor_round_saas_2026_07_07.md`
  - Contains 30 commercial growth points mapped to the A3 plan and current repo evidence.

### Verification

Focused command:

```text
node --test tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/shareable_report.test.mjs tests/a3/a3_enterprise_readiness.test.mjs tests/a3/self_host_console_contract.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
39 tests
39 pass
0 fail
```

### Current interpretation

This round directly advances the team lead's SaaS migration points:

- `static -> API-backed`: A3 can now accept A1 RunResult and A2 GradeResult through API routes.
- `mock fixture -> real DB data`: the store contract now has ingest receipts and source isolation for `api-ingest`.
- `HTML blob -> app components`: Enterprise Readiness is rendered through a component boundary.
- `report export -> shareable hosted report`: shared reports now have an actual `/reports/:reportId` HTML route, not only JSON payloads.

### Safety boundary

- No real Ashr API key, token, cookie, account data, or signed media URL was printed or committed.
- No real cloud mutation, API-key rotation, team invite, billing mutation, or Trust publish was executed.
- Hosted report HTML uses redacted shareable payload data and sealed evidence metadata only.

## 2026-07-07 - Growth auditor import and hosted report commercialization artifact

### Goal

Create a docs-only Growth-Auditor artifact for the current A3 commercial SaaS round focused on A1/A2 API ingest idempotency and validation, hosted report expiry/revocation/view audit, enterprise readiness, SQL/self-host next steps, and PR Gate / Report Center commercialization.

### Work completed

- Added `docs/a3/p3_growth_auditor_round_import_hosted_report_2026_07_07.md`.
- Captured 32 concrete growth points, each tagged across code/test/API/UI/docs/evidence and mapped to money value.
- Kept the round documentation-only; no code, tests, fixtures, schemas, secrets, or runtime files were changed.

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, database, or external APIs.
- Stayed within the requested write scope: the new growth-auditor artifact and append-only worklog update.

## 2026-07-07 - SQL Usage Ledger Report Center Implementation

### Goal

Turn the SaaS growth plan into concrete A3-owned contracts so the dashboard can move from static fixture review toward API-backed, DB-ready, shareable-report workflows while staying compatible with A1 and A2.

### Work completed

- Added SQL migration planning in `services/report/a3_sql_migrations.mjs`.
  - Covers organizations, projects, runs, cases, trace events, tool calls, grade results, idempotency keys, API import receipts, shareable reports, report view events, revocations, audit events, and usage ledger.
  - Supports Postgres as the recommended production target.
  - Adds MySQL and SQLite dialect targets for student/self-host deployment planning.
- Added read-only usage metering in `services/report/a3_usage_ledger.mjs`.
  - Counts A1/A2-derived runs, cases, failed cases, trace events, tool-call cases, judge results, media evidence cases, hosted reports, report views, report revocations, and API imports.
  - Keeps billing mutations disabled.
- Added report center manifest generation in `services/report/a3_report_center_manifest.mjs`.
  - Links hosted report artifacts, usage ledger evidence, and DB migration evidence.
  - Gives PR gate / audit bundle a single report packet shape.
- Extended `services/report/a3_store.mjs` and `services/report/a3_api_server.mjs`.
  - Adds `GET /api/a3/db-migrations`.
  - Adds `GET /api/a3/usage/ledger`.
  - Adds `GET /api/a3/reports/:reportId/manifest`.
  - Includes DB migrations and usage ledger in dashboard payloads.
- Extended `apps/dashboard/src/components/saas-runtime-panel.mjs` and `apps/dashboard/src/app.mjs`.
  - Shows migration batches and usage meters in the SaaS Runtime panel.
  - Keeps mock/raw A1/raw A2/P3 source compatibility.
- Added CI-style export firewall scan.
  - `tests/a3/export_firewall_generated_artifacts.test.mjs` scans generated A3 docs and fixtures for key/token/cookie/account-path leaks.
  - `docs/a3/p3_export_firewall_ci_scan_2026_07_07.md` documents the scan policy.
- Updated `docs/a3/acceptance_checklist.md`.
  - Marks export-firewall scan, SQL migration contract, usage ledger, and report center manifest work complete.
  - Keeps the real SQL adapter unchecked because no live database server has been selected or wired yet.

### Verification

Focused commands run:

```text
node --test tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/report_center_manifest_contract.test.mjs
node --test tests/a3/export_firewall_generated_artifacts.test.mjs
```

Focused result before final full-suite rerun:

```text
43 focused tests passed
1 export-firewall scan passed
```

Final A3 suite result:

```text
124 tests
124 pass
0 fail
```

Secret/path scan result:

```text
Only intentional redaction-test strings and existing redaction policy examples were matched.
No real key, cookie, token, account email, signed media URL, or local user artifact was added.
```

### Current interpretation

A3 now has the shape of a SaaS product, not just a local HTML demo:

- static -> API-backed: the same dashboard shape can be served by A3 API routes.
- mock fixture -> real DB data: not fully implemented yet, but SQL migration contracts define the future tables.
- HTML blob -> app components: dashboard logic is split across modules/components.
- report export -> shareable hosted report: report links have lifecycle, revoke/view audit, and manifest contracts.

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, billing, hosted auth, database, or external APIs in this implementation pass.
- Did not copy official private frontend source; the UI remains a clean-room local implementation.
- No real login, API-key creation, team invite, billing mutation, Trust publish, cloud delete, key reveal, token, cookie, account email, or signed URL was added.

## 2026-07-07 - Report Center Control Plane Index

### Goal

Move A3 Report Center beyond local export buttons by adding an API-backed report inventory that can summarize hosted report lifecycle, manifest readiness, usage evidence, migration evidence, and redaction status.

### Work completed

- Added `services/report/a3_report_center.mjs`.
  - New schema: `a3.report_center_index.v1`.
  - Summarizes hosted report count, shareable/expired/revoked/blocked status, total views, manifest readiness, firewall pass count, usage meter count, SQL migration count, and next actions.
  - Keeps cloud mutations and billing mutations disabled.
- Extended `services/report/a3_store.mjs`.
  - Adds `getReportCenter(...)`.
  - Adds `report_center` to `/api/a3/dashboard` payloads.
  - Keeps A1/A2 evidence joins intact through the existing normalized snapshot.
- Extended `services/report/a3_api_server.mjs`.
  - Adds `GET /api/a3/reports/center`.
- Extended dashboard API client and UI.
  - Adds `fetchA3ReportCenter(...)`.
  - API-backed dashboard state now includes `state.reportCenter`.
  - Sharing a hosted report refreshes Report Center.
  - Report Center now shows hosted reports with status, share path, view count, manifest completeness, artifact count, and redaction state.
- Added `docs/a3/p3_report_center_control_plane_growth_2026_07_07.md`.
  - Documents commercial meaning, incomplete parts, and next 20 growth points.
- Updated `docs/a3/acceptance_checklist.md`.
  - Marks Report Center index/API/dashboard wiring complete.

### Verification

Focused command:

```text
node --test tests/a3/report_center_index.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
37 tests
37 pass
0 fail
```

Final A3 suite result:

```text
126 tests
126 pass
0 fail
```

Secret/path scan result:

```text
Only intentional redaction-test strings and existing redaction policy examples were matched.
No real key, cookie, token, account email, signed media URL, or local user artifact was added.
```

### Current interpretation

This is a useful SaaS step because Report Center is now becoming a control plane:

- It can list hosted reports instead of only creating one link.
- It can tell whether each report is shareable, revoked, expired, or blocked.
- It links reports to manifest completeness, redaction status, usage ledger, and SQL migration evidence.
- It gives PR Gate, audit bundle, and self-host readiness a common future anchor.

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, billing, hosted auth, database, or external APIs in this implementation pass.
- Did not add real cloud mutation, real login, real API-key management, team invite, billing mutation, Trust publish, or destructive retention behavior.
- No real key, token, cookie, account email, signed URL, or official private source was committed.

## 2026-07-07 - Share Token Lifecycle For Hosted Reports

### Goal

Move hosted report sharing from internal report-id URLs toward external share-token URLs so customer-facing evidence links can be expired, revoked, audited, and summarized without exposing internal report ids as the primary sharing mechanism.

### Work completed

- Extended `services/report/a3_shareable_report.mjs`.
  - Adds external `share_url_path` in the `/r/:shareToken` shape.
  - Keeps internal admin path as `internal_url_path` in the `/reports/:reportId` shape.
  - Adds `share_link` metadata with token hash, token hash prefix, scope, expiry, and revocation fields.
  - Renders controlled denied pages for revoked, expired, blocked, or missing share access without rendering report body/case evidence.
- Extended `services/report/a3_store.mjs`.
  - Registers share links by token hash.
  - Stores redacted `/r/[REDACTED_TOKEN]` paths instead of raw share tokens.
  - Adds `getReportForShareToken(...)`.
  - Records allowed and denied share-link access events as redacted audit events.
  - Revoking a report also revokes its share link.
- Extended `services/report/a3_api_server.mjs`.
  - Adds `GET /r/:shareToken`.
  - Returns hosted report HTML for active share tokens.
  - Returns controlled denied HTML and no report body for revoked/expired/missing tokens.
- Extended SQL/usage/report-center contracts.
  - Adds `report_share_links` migration contract.
  - Adds `access_result` and `token_hash_prefix` fields to report view event planning.
  - Counts share-link access events in the usage ledger report-view meter.
  - Shows token hash prefix in Report Center dashboard rows.
- Added Growth-Auditor artifact:
  - `docs/a3/p3_share_token_lifecycle_growth_2026_07_07.md`
  - Covers sellable capability, remaining toy-like gaps, enterprise/self-host/audit value, and 30 next growth points.

### Verification

Focused command:

```text
node --test tests/a3/shareable_report.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/report_center_index.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Focused result:

```text
44 tests
44 pass
0 fail
```

### Current interpretation

This is a commercial hardening step:

- `/reports/:reportId` can stay as an internal/admin report path.
- `/r/:shareToken` becomes the safer external sharing boundary.
- Raw share tokens are returned once to the creator but not stored in durable report payloads.
- Report Center can show token hash prefixes, lifecycle state, view counts, manifest readiness, and redaction status.
- Expired/revoked/missing token access now produces audit evidence instead of silently failing.

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, billing, hosted auth, database, or external APIs in this implementation pass.
- Did not add real auth/RBAC, real billing, real email sharing, real API-key management, or destructive retention behavior.
- No real key, token, cookie, account email, signed URL, or official private source was committed.

## 2026-07-07 - Import Idempotency And Hosted Report Lifecycle

### Goal

Turn the new A1/A2 import routes and hosted report route into SaaS-grade contracts instead of one-off demo endpoints.

### Work completed

- Extended `services/report/a3_store.mjs`.
  - Added `A3StoreValidationError`.
  - Added validation for A1 RunResult imports and A2 GradeResult imports.
  - Added idempotency receipt tracking keyed by request type, source, idempotency key hash, and payload hash.
  - Added duplicate replay behavior for matching idempotency keys.
  - Added 409 conflict behavior when the same idempotency key is reused with a different payload.
  - Added hosted report view audit, expiry status, revoke receipt, and report lifecycle status.
- Extended `services/report/a3_api_server.mjs`.
  - Reads `Idempotency-Key` / `X-Idempotency-Key` for import routes.
  - Returns `a3.api_validation_error.v1` with redacted summary and quota/cost note for bad imports.
  - Adds `POST /api/a3/reports/:reportId/view`.
  - Adds `POST /api/a3/reports/:reportId/revoke`.
  - Hosted report HTML returns `410` for expired or revoked reports.
- Extended `services/report/a3_shareable_report.mjs`.
  - Adds default 30-day `expires_at`.
  - Adds lifecycle metadata and initial view audit metadata.
- Added SQL adapter contract artifact:
  - `docs/a3/p3_sql_adapter_contract_2026_07_07.md`
  - `tests/a3/sql_adapter_contract.test.mjs`
- Added API calibration/error-shape evidence artifact:
  - `docs/a3/p3_api_calibration_import_error_shapes_2026_07_07.md`
  - `tests/a3/api_calibration_contract.test.mjs`

### Verification

Focused command:

```text
node --test tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/shareable_report.test.mjs tests/a3/sql_adapter_contract.test.mjs tests/a3/api_calibration_contract.test.mjs
```

Focused result:

```text
14 tests
14 pass
0 fail
```

### Current interpretation

This is an important SaaS hardening step:

- Import routes now behave like production APIs: repeat-safe, conflict-aware, and validation-shaped.
- Hosted reports now behave like customer-facing share links: expirable, revocable, and view-audited.
- SQL/self-host planning now has explicit table/index/ledger anchors for the next DB-backed implementation round.

### Safety boundary

- No real Ashr API key, token, cookie, account data, or signed URL was printed or committed.
- Validation errors do not echo request payloads.
- Idempotency ledger stores a hashed key prefix and payload hash, not raw API keys or secrets.

## 2026-07-07 - Growth auditor SQL usage and report center artifact

### Goal

Create a docs-only Growth-Auditor artifact for the next A3 commercial SaaS round focused on SQL migrations, usage ledger, billing/read-only quotas, report center manifest, CI export firewall, PR gate integration, hosted report lifecycle, and self-host deployment.

### Work completed

- Added `docs/a3/p3_growth_auditor_round_sql_usage_report_center_2026_07_07.md`.
- Captured 32 concrete growth points tagged across code/test/API/UI/docs/evidence.
- Mapped each growth point to money value, enterprise value, and risk reduction.
- Kept the round documentation-only; no code, tests, fixtures, schemas, secrets, or runtime files were changed.

### Safety boundary

- Did not read or print `.env.local`.
- Did not call live Ashr, GitHub, billing, hosted auth, database, or external APIs.
- Stayed within the requested write scope: the new growth-auditor artifact and append-only worklog update.

## 2026-07-08 - SQLite-backed A3 store and hosted report revoke UI

### Goal

Move A3 from "SQL contract exists" toward "local SQL-backed SaaS store can actually run."

### Work completed

- Added `services/report/a3_sqlite_store.mjs`.
  - Uses Node's built-in SQLite runtime.
  - Applies the existing SQLite migration contract.
  - Persists A3 state into real SQL tables for dashboard snapshots, runs, cases, reports, share links, import receipts, idempotency rows, audit events, view events, revocations, and usage ledger rows.
  - Keeps raw share tokens out of stored report reads and inspection evidence.
  - Handles missing share-token audit as an audit event without creating fake report rows.
- Added `tests/a3/a3_sqlite_store.test.mjs`.
  - Verifies A1 RunResult and A2 GradeResult import persistence.
  - Verifies idempotency duplicate replay and conflict behavior.
  - Verifies hosted report share/view/revoke lifecycle rows.
  - Verifies API server compatibility when injected with the SQLite store.
  - Verifies reopen-after-close persistence for revoked report state.
- Extended dashboard Report Center lifecycle controls.
  - Added `revokeShareableA3Report()` to the dashboard API client.
  - Added a Revoke button for active API-backed hosted reports.
  - Refreshes Report Center, Artifact Registry, Product Console, and print report evidence after share/revoke actions.
- Added `docs/a3/p3_sqlite_store_growth_2026_07_08.md`.
  - Captures commercial value, safety boundary, verification, and 22 next growth points.

### Verification

```text
node --test tests/a3/a3_sqlite_store.test.mjs tests/a3/dashboard_wiring.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs
```

Result:

```text
38 tests
38 pass
0 fail
```

Syntax check:

```text
node --check apps/dashboard/src/app.mjs
node --check apps/dashboard/src/api-client.mjs
node --check services/report/a3_sqlite_store.mjs
```

Result: passed.

### Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub, billing, auth, team, Trust, or cloud mutation API was called.
- No API key, token, cookie, account email, raw share token, or live signed URL was committed.

### Current interpretation

A3 now has a concrete local SQL-backed store target. This is still not production Postgres or a hosted multi-tenant SaaS, but it turns the previous SQL contract into executable storage evidence and makes the hosted report lifecycle feel more like a real SaaS control plane.

## 2026-07-08 - SaaS admin action request workflow

### Goal

Respond to the SaaS growth request for login, cloud/project management, usage, API keys, team, and trust workflows without introducing unsafe real Ashr mutations.

The group lead also changed `main` and several files while resolving merge conflicts. This round first fetched `origin/main` and confirmed the A3 branch is already based on the current main, then kept changes additive inside A3-owned areas.

### Work completed

- Added `a3.saas_admin_action_request.v1` and `a3.saas_admin_action_receipt.v1`.
- Added safe admin action request recording for login/team/usage/API-key/trust/cloud-management operations.
- Added API routes:
  - `POST /api/a3/admin/actions/submit`
  - `GET /api/a3/admin/actions`
- Added `saas_admin_action_requests` to the SQL migration contract.
- Persisted SaaS admin action requests in the SQLite-backed A3 store.
- Added dashboard `Record Request` / `Record Guardrail` control in the SaaS Admin Console.
- Added request summary and latest requests to SaaS Admin report exports.
- Preserved A1/A2 compatibility: A3 still only consumes A1 run/trace/tool-call evidence and A2 score/pass/fail/failure-class evidence.

### Verification

```text
node --check services/report/a3_store.mjs
node --check services/report/a3_saas_admin.mjs
node --check services/report/a3_api_server.mjs
node --check apps/dashboard/src/app.mjs
```

Result: passed.

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

### Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub, billing, auth, team invite, API-key, Trust publish, or cloud mutation API was called.
- No API key, token, cookie, account email, raw share token, or live signed URL was committed.

### Current interpretation

A3 now has a safer SaaS admin workflow: dangerous console actions can be represented as request records and audit events instead of fake-working buttons. This keeps the student MVP honest while moving it closer to enterprise product behavior.

## 2026-07-08 - Durable review workflow records

### Goal

Move reviewer waiver/approval from file-backed validation only toward API-backed and DB-backed enterprise sign-off evidence.

### Work completed

- Added `services/report/a3_review_workflow.mjs`.
- Reused existing Gate CLI validators:
  - `validateWaiverRequest(...)`
  - `validateApprovalRecord(...)`
- Added schemas:
  - `a3.review_workflow_record.v1`
  - `a3.review_workflow_index.v1`
  - `a3.review_workflow_receipt.v1`
- Added API routes:
  - `POST /api/a3/review/waivers`
  - `POST /api/a3/review/approvals`
  - `GET /api/a3/review/workflow`
- Added SQL migration table `review_workflow_records`.
- Added SQLite persistence and inspection count for review workflow rows.
- Added dashboard durable review records under Reviewer Workflow.
- Added JSON export field `review_workflow`.
- Added tests for service, store, API, SQLite, dashboard wiring, and report export.

### Verification

Focused tests:

```text
node --test tests/a3/a3_review_workflow.test.mjs tests/a3/a3_store.test.mjs
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_sqlite_store.test.mjs
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/report_builder.test.mjs
```

Result: passed after aligning waiver validation context with the original release version fixture.

### Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub, billing, auth, team, API-key, Trust, or cloud mutation API was called.
- No API key, token, cookie, account email, raw share token, live signed URL, or raw cryptographic signature was committed.

### Current interpretation

A3 now has durable review workflow records, but not final production-grade signature verification. The next true enterprise step is real reviewer identity binding through SSO/OIDC/GitHub plus cryptographic signature verification before approvals can affect a live required check.

## 2026-07-08 - Live-capable GitHub Check publisher

### Goal

Move the A3 PR Gate closer to a real customer merge workflow by turning the existing GitHub Check payload into a live-capable Check Run publisher.

### Work completed

- Added `publishGitHubCheckRun(...)` in `services/report/a3_github_integration.mjs`.
- Added `services/report/a3_github_publish_cli.mjs`.
- Kept publisher dry-run by default.
- Added explicit live mode through CLI `--live` or `dryRun: false`.
- Added runtime-token handling through `GITHUB_TOKEN`, `GH_TOKEN`, or `--token-env`.
- Updated `docs/a3/p3_github_action_workflow_example.yml` with a `Publish Ashr++ GitHub Check` step.
- Saved redacted dry-run receipt:
  - `fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json`
- Added documentation:
  - `docs/a3/p3_live_github_check_publisher_2026_07_08.md`

### Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
13 tests
13 pass
0 fail
```

### Safety boundary

- No `.env.local` was read.
- No Ashr API call was made.
- No live GitHub API call was made in this pass.
- No GitHub token, API key, cookie, email, raw signed URL, or Authorization header was committed.
- Branch protection was not changed; making `Ashr++ Release Gate` a required check still requires maintainer approval in GitHub settings.

### Current interpretation

A3 can now publish a GitHub Check Run when CI explicitly opts in, which is much closer to a commercial PR gate. It is still not the full "required check" story until branch protection is configured and evidenced.

## 2026-07-08 - PR comment publisher and required-check plan

### Goal

Continue the PR Gate commercial workflow by adding human-readable PR comment publishing and a branch-protection required-check plan.

### Work completed

- Added `publishPrCommentUpsert(...)` in `services/report/a3_github_integration.mjs`.
- Added `buildBranchProtectionRequiredCheckPlan(...)` in `services/report/a3_github_integration.mjs`.
- Extended `services/report/a3_github_publish_cli.mjs` with explicit PR comment mode:
  - `--pr-comment`
  - `--pull-number`
- Updated `docs/a3/p3_github_action_workflow_example.yml` with `Publish Ashr++ PR Comment`.
- Saved redacted evidence fixtures:
  - `fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json`
  - `fixtures/a3/p3/a3_github_required_check_plan.redacted.json`
- Added documentation:
  - `docs/a3/p3_pr_comment_required_check_plan_2026_07_08.md`

### Verification

```text
node --test tests/a3/a3_github_integration.test.mjs
```

Result:

```text
21 tests
21 pass
0 fail
```

### Safety boundary

- Existing PR comment plan builder remains dry-run and plan-only.
- PR comment publishing requires explicit `--pr-comment --pull-number`.
- Branch protection is still plan-only; no repository settings were changed.
- No `.env.local`, Ashr key, GitHub token, cookie, email, Authorization header, or raw signed URL was committed.

### Current interpretation

A3 now has both machine-readable Check Run publishing and human-readable PR comment publishing. The remaining commercial gap is enforcing the check through branch protection and proving that setting with maintainer-approved evidence.

## 2026-07-08 - GitHub readback and required-check proof contracts

### Goal

Continue the A3 PR Gate / Release Evidence authority work by adding readback contracts. This lets A3 distinguish "we generated a GitHub artifact" from "GitHub currently has the expected check/comment/required-check state."

### Work completed

- Added GitHub Check readback receipt contract:
  - generated
  - posted
  - readback-confirmed
  - stale SHA/body
  - missing
  - deleted
  - permission denied
  - failed
- Added PR comment readback receipt contract:
  - marker match
  - body-hash match
  - comment id match
  - stale/missing/deleted/permission-denied states
- Added required-check proof contract:
  - branch-protection readback
  - enforced only when readback confirms the configured check
  - plan-only cannot claim enforcement
- Wired readback summaries into:
  - `services/report/report_builder.mjs`
  - `services/report/a3_release_evidence.mjs`
  - `services/report/a3_store.mjs`
- Added redacted fixture examples under `fixtures/a3/p3`.
- Added documentation:
  - `docs/a3/p3_github_readback_contract_2026_07_08.md`

## 2026-07-08 - GitHub publish evidence in reports and artifact registry

### Goal

Bind GitHub publish receipts into A3's customer-facing evidence chain so PR Gate delivery evidence appears in reports, Artifact Registry, and dashboard Report Center wiring.

### Work completed

- Added `summarizeGithubPublishEvidence(...)` in `services/report/report_builder.mjs`.
- Added `github_publish_evidence` to JSON report export.
- Added `GitHub Publish Evidence` to Markdown report export.
- Added Artifact Registry control artifacts:
  - `github_check_publish_receipt`
  - `github_pr_comment_publish_receipt`
  - `github_required_check_plan`
- Added `github_pr_gate_packet` Artifact Registry preset.
- Dashboard static sources now load redacted GitHub publish evidence fixtures.
- Dashboard export calls pass `state.githubPublishEvidence` to JSON and Markdown reports.
- Added documentation:
  - `docs/a3/p3_github_publish_evidence_registry_2026_07_08.md`

### Verification

```text
node --check services/report/a3_github_integration.mjs
node --check services/report/a3_release_evidence.mjs
node --check services/report/report_builder.mjs
node --test tests/a3/a3_github_integration.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_store.test.mjs

node --test tests/a3/artifact_registry.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
```

Result:

```text
40 tests
40 pass
0 fail
```

### A1/A2 calibration

- A1 source data contracts were not changed.
- A2 judge/policy semantics were not changed.
- A3 readback evidence wraps the release workflow only, after A1/A2 have produced run and grade evidence.

### Safety boundary

- No `.env.local` was read.
- No Ashr API call was made.
- No live GitHub API call was made.
- No real branch protection was changed.
- No GitHub token, API key, cookie, email, Authorization header, raw signed URL, or secret value was committed.

### Current interpretation

This closes a major commercial evidence gap in local code: A3 can now model external GitHub proof instead of only local publish receipts. The next step is maintainer-approved CI or GitHub App integration that performs real readback and persists the receipt.

## 2026-07-08 - Release evidence readback capture API

### Goal

Continue the A3 release evidence authority work by making readback receipts capturable through API and durable store paths, instead of only relying on static redacted fixtures.

### Work completed

- Added `POST /api/a3/releases/:releaseId/readbacks`.
- Added `GET /api/a3/releases/:releaseId/readbacks`.
- Added store methods for readback submit/list.
- Added idempotency, tenant-scope checks, audit event linkage, and payload hash receipts.
- Added deeper redaction for nested Authorization/token/email/secret-like fields.
- Wired latest captured readbacks into release evidence v2 summary.
- Persisted current readback authority rows through SQLite.
- Added readback usage meter and artifact registry entries.
- Kept readback idempotency separate from A1/A2 API import receipts.
- Added documentation:
  - `docs/a3/p3_release_evidence_readback_capture_api_2026_07_08.md`

### Verification

```text
node --test tests/a3/a3_api_server.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_sqlite_store.test.mjs tests/a3/a3_release_evidence.test.mjs tests/a3/a3_sql_usage_report_center.test.mjs tests/a3/artifact_registry.test.mjs
```

Result:

```text
21 tests
21 pass
0 fail
```

### A1/A2 calibration

- A1 runner and trace/tool-call contracts were not changed.
- A2 judge and grade semantics were not changed.
- A3 readback capture consumes downstream release evidence only.
- A3 does not claim that GitHub readback equals A1 verifier success.

73 tests
73 pass
0 fail
```

### Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub API call was made.
- No branch protection was changed.
- No API key, token, cookie, email, Authorization header, or raw account value was committed.

### Current interpretation

A3 now has an API/DB path for runtime readback evidence. The next production step is a maintainer-approved CI or GitHub App worker that performs live readback and submits sanitized receipts to this API.

## 2026-07-08 - Readback Worker CLI And Dashboard Visibility

### Goal

Continue A3 along the commercial SaaS plan by making release evidence readback usable from a worker/CI command and visible in the dashboard, Report Center, JSON export, Markdown export, and print-ready report.

### Work completed

- Added `services/report/a3_readback_capture_cli.mjs`.
- Added `tests/a3/a3_readback_capture_cli.test.mjs`.
- CLI defaults to dry-run and only submits when `--submit` is provided.
- CLI posts sanitized readback evidence to `POST /api/a3/releases/:releaseId/readbacks`.
- CLI supports `--output-receipt` so CI can save a redacted artifact.
- Normalized readback resource kinds:
  - `check_run` / `github_check` -> `github_check`
  - `pr_comment` / `pull_request_comment` -> `pr_comment`
  - `required_check` / `branch_protection` -> `required_check`
- Added `release_evidence_readbacks` to API-backed dashboard payloads.
- Added readback history to `release_evidence_summary`.
- Added Release Evidence readback rows to the dashboard panel.
- Added readback summary to Report Center text.
- Added readback fields to JSON, Markdown, and print/PDF-ready report exports.
- Added A1/A2 contract-alignment doc:
  - `docs/a3/p3_readback_a1_a2_contract_alignment_2026_07_08.md`
- Added Growth-Auditor doc:
  - `docs/a3/p3_growth_auditor_readback_worker_round_2026_07_08.md`
- Added implementation summary:
  - `docs/a3/p3_readback_worker_and_visibility_2026_07_08.md`

### Verification

```text
node --check services/report/a3_readback_capture_cli.mjs
node --check services/report/report_builder.mjs
node --check services/report/a3_store.mjs
node --check apps/dashboard/src/app.mjs
node --test tests/a3/a3_readback_capture_cli.test.mjs tests/a3/a3_store.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/report_builder.test.mjs tests/a3/dashboard_wiring.test.mjs
git diff --check
```

Result:

```text
81 tests
81 pass
0 fail
```

### A1/A2 calibration

- A1 runner, trace, observation, and tool-call contracts were not changed.
- A2 judge, score, pass/fail, rubric, and failure taxonomy semantics were not changed.
- A3 readback is explicitly documented as external release-control proof, not as A1 or A2 proof.
- Dashboard/report copy now keeps "GitHub readback confirmed" separate from "A1 RunResult valid" and "A2 GradeResult passed".

### Safety boundary

- No `.env.local` was read.
- No Ashr API call was made.
- No live GitHub API call was made.
- No branch protection, billing, auth, API-key, team, Trust, or cloud mutation was made.
- No token, cookie, email, Authorization header, raw key, account data, or secret value was committed.

### Current interpretation

A3 now has the local path needed for a future CI worker: collect a redacted GitHub readback receipt, submit it through the A3 API, persist it, and show it in customer-facing dashboard/report surfaces. The remaining commercial step is a maintainer-approved live GitHub App or GitHub Actions worker plus hosted auth/RBAC and production Postgres/RLS.

## 2026-07-09 - Commercial CL Gate Anchors

### Goal

Continue A3 from latest `main` and make every future PR harder to regress away from the commercial SaaS endgame. This round follows `docs/strategy/large-saas-a1-a2-a3-full-plan.md`: A3 owns Product Console, Review Workflow, Report Center, GitHub Gate, Commercial UI, and client workflows, while staying calibrated to A1 runtime evidence and A2 judge evidence.

### Work completed

- Added `python scripts/cl_guard.py commercial`.
- Wired the new commercial gate into `.github/workflows/cl-gate.yml`.
- Added 20 blocker anchors across:
  - main strategy file
  - CL workflow and guard
  - dashboard webapp split
  - dashboard API client
  - TypeScript SDK package
  - A3 API routes
  - A3 store DB/API contract
  - report builder exports
  - release evidence v2 authority
  - readback worker CLI
  - A1 evidence/worker schemas
  - A2 grade/commercial readiness schemas
  - A3 API/dashboard/report/SQLite tests
  - A3 acceptance ledger
- Added advisory-only checks for missing future surfaces:
  - Playwright TS E2E
  - Tailwind product styling pipeline
  - React Native / Expo mobile client
  - WeChat mini program client surface
- Added `tests/a1/test_cl_guard.py`.
- Added Contract-Agent artifact:
  - `docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md`
- Added UI/TS/Playwright artifact:
  - `docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md`
- Added Growth-Auditor artifact:
  - `docs/a3/p3_growth_auditor_cl_gate_2026_07_09.md`

### Verification

```text
python -m py_compile scripts/cl_guard.py tests/a1/test_cl_guard.py
python scripts/cl_guard.py commercial
python scripts/cl_guard.py hygiene
python -B -m pytest tests/a1/test_cl_guard.py -q -p no:cacheprovider
```

Additional validation before commit:

```text
node --test tests/a3/dashboard_wiring.test.mjs tests/a3/a3_api_server.test.mjs tests/a3/a3_saas_admin.test.mjs tests/a3/a3_review_workflow.test.mjs
npm test --prefix packages/ts/ashr-clone
git diff --check
```

Result:

- CL commercial anchor gate passed with 20/20 blocker anchors and 0 blockers.
- Hygiene gate passed with no secret findings.
- CL guard pytest passed: 3 pass, 0 fail.
- A3 Node contracts passed: 37 pass, 0 fail.
- `packages/ts/ashr-clone` dependency install passed with 0 vulnerabilities.
- Local full `npm test` is blocked by the Windows workstation missing `go`; the TypeScript test suite includes a real Go HTTP server vertical slice.
- `.github/workflows/cl-gate.yml` now installs Go in the `typescript-sdk` job so CI can run that vertical slice intentionally.
- Attempted local portable Go install under the user local tools directory, but `go.dev` download failed from this machine with a remote connection error.

### A1/A2 calibration

- A1 runtime/worker/evidence schema anchors are now part of the commercial CL gate.
- A2 grade/commercial readiness schema anchors are now part of the commercial CL gate.
- A3 API/dashboard/report tests remain the consumer-side proof that A1/A2 evidence is not replaced by A3 UI claims.

### Safety boundary

- No `.env.local` was read.
- No live Ashr API call was made.
- No live GitHub mutation was made.
- No billing, auth, team, API-key, Trust, object-storage, database, or cloud mutation was made.
- Playwright/Tailwind/mobile/WeChat are advisory-only until their actual toolchains exist.

### Current interpretation

This is not a new product screen; it is a durability upgrade for the whole project. Future CLs now have a low-noise commercial anchor gate, so A3 is less likely to drift back into isolated demo work. The strongest next build remains a real Playwright TS E2E lane for dashboard/admin/review/report flows, followed by typed dashboard DTOs and a Tailwind/design-system migration.

- No branch-protection mutation was made.
- No token, cookie, email, Authorization header, raw signed URL, or local absolute user path was committed.

### Current interpretation

A3 PR Gate now has a stronger audit story: generated check/comment/required-check evidence can travel through report export and Artifact Registry. The next enterprise step is hashing those receipts into the audit bundle and verifying real branch protection.

## 2026-07-09 - A2 Persistence and Unblock Export Bridge

### Goal

Continue A3 commercial growth after PR #23 by consuming newer A2 release evidence without changing A2 semantics. This follows `docs/strategy/large-saas-a1-a2-a3-full-plan.md`: A3 should turn A1/A2 evidence into product console, report center, review workflow, audit export, and release-gate buyer value.

### Work completed

- Added A3 summary support for `a2.result_persistence_manifest.v1`.
- Added A3 summary support for `a2.release_unblock_checklist.v1`.
- Extended the A2 readiness bundle accepted by report exports with:
  - `resultPersistence`
  - `resultPersistenceManifest`
  - `releaseUnblockChecklist`
- Added `a2_result_persistence` and `a2_release_unblock_checklist` to JSON report export.
- Added Markdown report sections:
  - `A2 Result Persistence`
  - `A2 Release Unblock Checklist`
- Wired dashboard export loading for:
  - `fixtures/a2/results/a2_result_persistence_manifest.json`
  - `fixtures/a2/results/a2_release_unblock_checklist.json`
- Added tests proving dashboard export wiring and report-builder summaries.
- Added implementation note:
  - `docs/a3/p3_a2_persistence_unblock_export_2026_07_09.md`

### A1/A2 calibration

- A1 runner, trace, observation, tool-call, and ingestion semantics were not changed.
- A2 judge, grade, failure taxonomy, release-gate, and unblock semantics were not changed.
- A3 only summarizes A2-owned fixtures and schemas for product/report/review consumption.

### Safety boundary

- No `.env.local` read.
- No Ashr API key read, printed, or written.
- No live Ashr API call.
- No hosted auth, billing, team, API-key, Trust, database, object storage, or cloud mutation.
- A2 private evidence refs remain named anchors only; raw private payloads were not read.

## 2026-07-09 - API-Backed Playwright E2E Bridge

### Goal

Advance A3 from static dashboard browser proof toward the strategy bus requirement: `static -> API-backed`, `report export -> shareable hosted report`, and A1/A2-visible commercial workflow evidence.

### Work completed

- Mounted `services/report/a3_api_server.mjs` into the local Playwright dashboard server.
- Added API-backed Playwright E2E for `apps/dashboard/index.html?source=api-mock`.
- Verified browser-visible API/DB surfaces, SaaS Admin shell, A1 trace references, A2 judge evidence, Report Center, and hosted report lifecycle.
- Exercised hosted report create/revoke through local A3 API routes.
- Added Tailwind product-system config, PostCSS readiness, docs, and tests.
- Added React Native / Expo mobile release approval client-surface contract, docs, and tests.
- Added WeChat mini program release approval / incident alert client-surface contract, docs, and tests.
- Added `docs/a3/p3_commercial_growth_round3_execution_2026_07_09.md` with 20 growth points.
- Updated Playwright evidence notes and acceptance checklist.

### Verification

```text
node --check tests/e2e/static-dashboard-server.mjs
npx.cmd playwright test tests/e2e/a3-dashboard-api-backed.spec.ts
node --test tests/a3/tailwind_boundary_contract.test.mjs tests/a3/a3_wechat_mini_program_client_surface.test.mjs tests/a3/a3_mobile_expo_client_surface.test.mjs
python scripts\cl_guard.py commercial
```

Result:

- API-backed Playwright E2E passed: 2 pass, 0 fail.
- Client/design-surface contract tests passed: 16 pass, 0 fail.
- Commercial CL passed with 0 blockers and 0 advisories.

### A1/A2 calibration

- A1 runner logic was not changed.
- A2 judge semantics were not changed.
- A3 now proves in a browser that API-backed mode still exposes A1 import/trace and A2 import/judge evidence.

### Safety boundary

- No `.env.local`, API key, token, cookie, email, raw signed URL, account value, or private credential was read or committed.
- No live Ashr/GitHub/cloud/billing/auth mutation was performed.
