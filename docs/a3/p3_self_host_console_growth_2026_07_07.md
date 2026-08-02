# P3 Self-Host And Enterprise Console Contract - 2026-07-07

Author: A3 Self-Host Contract Worker
Scope: contract artifact only. This document inspects the existing A3 store, API, admin console, report builder, and A1/A2 handoff docs. It does not change shared app or service files, does not read `.env.local`, and does not include secret values.

## 1. Contract Status

A3 already has a local API/store/admin/report slice that can become a self-host or enterprise console without changing the A1 runner or A2 judge contracts.

Current implemented anchors:

- Store contract: `A3_DB_CONTRACT` with `schema_version=a3.saas_db_contract.v1`.
- API health: `GET /api/a3/health` returns `a3.api_health.v1`, `ok`, `service`, `storage_mode`, and `db_ready`.
- API DB contract: `GET /api/a3/db-contract` returns the DB-ready table and guardrail contract.
- Dashboard payload: `GET /api/a3/dashboard` returns `a3.api_dashboard_payload.v1`.
- Admin console: `GET /api/a3/admin/console` returns `a3.saas_admin_console.v1`.
- Admin actions: `POST /api/a3/admin/actions/plan` returns plan-only/read-only action contracts.
- Shareable reports: `POST /api/a3/reports/share` returns `a3.shareable_report.v1` after the export redaction firewall runs.

Target self-host posture:

- Production DB: PostgreSQL.
- Local/dev store: memory/file today, SQLite-compatible migration path later.
- MySQL: compatible by contract, only supported if a customer or platform decision justifies the migration burden.
- Tenancy: every persisted customer object is scoped by `organization_id` and `project_id`.
- Secrets: never persist or return API keys, cookies, bearer tokens, raw signed URLs, `.env.local` values, local home paths, or unredacted account identifiers.

## 2. Enterprise Console Pages

The self-host console must expose these pages as first-class routes or route-level views. Each page reads from the A3 API contract rather than raw fixture files.

| Page | Primary Users | Required Data | Required Controls |
|---|---|---|---|
| Login / Session | all users | provider, session status, redacted user identity, org/project scope | logout, session refresh, auth error state |
| Organization / Project Switcher | owner, admin, developer | organizations, projects, role grants, active project | project switch, scoped reload, no cross-project leakage |
| Runs | developer, reviewer | run list, source kind, status, pass rate, failure class, timestamps | filters, pagination, import status, empty/error states |
| Run Detail | developer, reviewer | run summary, cases, aggregate score, trace completeness, A1/A2 source hashes | case drilldown, report build action |
| Case Detail | developer, reviewer, auditor | expected/actual, tool-call diffs, observations, trace events, A2 judge evidence, media metadata | redacted evidence view, trace pagination, copy-safe IDs |
| Report Center | reviewer, auditor | report snapshots, shareable reports, redaction status, artifact hashes | create snapshot, view hosted report, revoke share link |
| Export Queue | reviewer, auditor | JSON, Markdown, CSV, PDF, audit bundle jobs | retry failed job, download only after scan passes |
| Release Gate / War Room | reviewer, owner | gate decision, blocked checks, waivers, approvals, incident replay, audit bundle readiness | approve, block, request exception, attach evidence |
| Team | owner, admin | members, roles, invite state, approval policy | invite preview, role change plan, no email send until auth/RBAC is live |
| API Keys | owner, admin | key metadata, prefix, scopes, last used, status | create/rotate/revoke plan, one-time reveal only from server |
| Usage | billing admin, owner | run/case counts, usage channels, quota status, local meter | read-only usage view, no billing mutation in A3 local shell |
| Trust / Audit | owner, auditor | trust report preview, release evidence, redaction policy, audit bundle hash | publish plan, download bundle, retention/legal hold view |
| System Health | admin, operator | API, DB, object store, export worker, redaction, audit log, A1/A2 compatibility checks | health refresh, readiness details, safe diagnostics |
| Retention And Audit Policy | owner, auditor | retention windows, legal holds, deletion queue, audit coverage | policy preview, hold plan, export policy evidence |

Disabled until hosted auth/RBAC exists:

- Real OAuth callback mutation.
- Real team invites.
- Real API-key creation, reveal, rotation, or revocation.
- Real billing mutation.
- Public Trust publishing.
- Cross-project data access.

## 3. Required API Surface

Current local API routes that must remain compatible:

| Route | Current Schema | Self-Host Requirement |
|---|---|---|
| `GET /api/a3/health` | `a3.api_health.v1` | Liveness plus shallow storage readiness; no secrets in diagnostics |
| `GET /api/a3/db-contract` | `a3.saas_db_contract.v1` | Returns current table/guardrail contract for operators and tests |
| `GET /api/a3/dashboard` | `a3.api_dashboard_payload.v1` | Project-scoped dashboard payload with admin console summary |
| `GET /api/a3/runs` | `a3.api_run_list.v1` | Paginated and filterable by project, status, dataset, date, failure class, source |
| `GET /api/a3/runs/:runId` | `a3.api_run_detail.v1` | Project-scoped run detail; never leak raw import payload |
| `GET /api/a3/cases/:caseId` | `a3.api_case_detail.v1` | Case evidence with redacted expected/actual, traces, tool calls, media metadata |
| `POST /api/a3/reports/share` | `a3.shareable_report.v1` | Builds immutable redacted hosted-report payload; must pass redaction firewall |
| `GET /api/a3/reports/:reportId` | `a3.shareable_report.v1` | Reads hosted report by internal report id only for authorized users |
| `GET /api/a3/reports` | `a3.api_report_list.v1` | Lists report metadata, not raw report bodies |
| `GET /api/a3/admin/console` | `a3.saas_admin_console.v1` | Read-only enterprise console model with redacted identities |
| `POST /api/a3/admin/actions/plan` | `a3.saas_admin_action_plan.v1` | Produces read-only/plan-only action plans until real services exist |

Required next self-host routes:

| Route | Purpose | Guardrail |
|---|---|---|
| `POST /api/a3/runs/import` | Import A1 RunResult, A2 grade, A3 normalized, or official API-shaped evidence | idempotency key, source hash, redaction pre-scan |
| `GET /api/a3/runs/:runId/cases` | Paginated case list for one run | project scoped, no raw payload dump |
| `GET /api/a3/cases/:caseId/trace` | Trace timeline pagination | redacted payloads, max page size |
| `POST /api/a3/reports/:reportId/exports` | Queue export artifacts | snapshot hash, redaction scan, audit event |
| `GET /api/a3/exports/:exportId` | Read export metadata or short-lived download pointer | no raw storage key or signed URL in durable response |
| `POST /api/a3/reports/:reportId/share-links` | Create expiring/revocable share link | separate token from DB ids |
| `POST /api/a3/share-links/:shareId/revoke` | Revoke hosted report link | audit event required |
| `GET /api/a3/audit/events` | Audit log search | auditor role, pagination, redacted metadata |
| `GET /api/a3/retention/policy` | Current retention settings | no mutation through local shell |
| `POST /api/a3/retention/actions/plan` | Preview purge/legal-hold action | plan-only until policy service exists |

## 4. Required DB Tables

The current `A3_DB_CONTRACT` names these required tables. Self-host migrations must create them or an explicitly compatible view/model.

| Table | Purpose | Minimum Required Fields |
|---|---|---|
| `organizations` | tenant boundary | `id`, `display_name_redacted`, `plan`, `created_at`, `deleted_at` |
| `users` | authenticated actor identity | `id`, `provider`, `provider_subject_hash`, `display_name_redacted`, `created_at`, `disabled_at` |
| `roles` | role catalog | `id`, `name`, `permissions_json`, `created_at` |
| `team_members` | org/project membership | `id`, `organization_id`, `project_id`, `user_id`, `role_id`, `status`, `created_at`, `removed_at` |
| `projects` | scoped product workspace | `id`, `organization_id`, `display_name`, `environment`, `created_at`, `archived_at` |
| `api_keys` | machine access metadata | `id`, `organization_id`, `project_id`, `name`, `prefix_redacted`, `secret_hash`, `scopes_json`, `created_by`, `last_used_at`, `revoked_at` |
| `runs` | A1/A2/A3 run identity | `id`, `organization_id`, `project_id`, `source_kind`, `source_run_id`, `dataset_id`, `runner_id`, `status`, `started_at`, `ended_at`, `raw_payload_hash` |
| `cases` | case summary and display | `id`, `organization_id`, `project_id`, `run_id`, `case_id`, `scenario_id`, `title`, `status`, `score`, `primary_failure_class`, `latency_ms` |
| `tool_calls` | expected/actual tool evidence | `id`, `organization_id`, `project_id`, `case_id`, `call_id`, `name`, `arguments_redacted_json`, `output_redacted_json`, `match_status`, `seq` |
| `trace_events` | replay timeline | `id`, `organization_id`, `project_id`, `run_id`, `case_id`, `seq`, `event_type`, `phase`, `source`, `timestamp`, `redacted_payload_json` |
| `grade_results` | A2/A3 judge output | `id`, `organization_id`, `project_id`, `case_id`, `passed`, `score`, `score_scale`, `primary_failure_class`, `severity`, `judge_modes_json`, `raw_payload_hash` |
| `failure_clusters` | report grouping | `id`, `organization_id`, `project_id`, `run_id`, `primary_failure_class`, `case_count`, `severity`, `summary` |
| `media_evidence` | file/audio/image/video metadata | `id`, `organization_id`, `project_id`, `case_id`, `kind`, `mime_type`, `storage_key_hash`, `redaction_status`, `expires_at` |
| `shareable_reports` | immutable hosted report snapshot | `id`, `organization_id`, `project_id`, `run_id`, `snapshot_version`, `builder_version`, `redaction_policy_version`, `content_hash`, `status`, `created_by`, `created_at` |
| `trust_reports` | enterprise trust/audit view | `id`, `organization_id`, `project_id`, `shareable_report_id`, `release_gate_decision`, `approval_state`, `published_at`, `revoked_at` |
| `audit_events` | durable event log | `id`, `organization_id`, `project_id`, `actor_id`, `event_type`, `object_type`, `object_id`, `created_at`, `metadata_redacted_json`, `hash` |
| `usage_ledger` | usage and quota accounting | `id`, `organization_id`, `project_id`, `event_type`, `quantity`, `unit`, `source_id`, `created_at` |

Required supporting tables for production hardening:

| Table | Purpose | Minimum Required Fields |
|---|---|---|
| `report_exports` | generated JSON/Markdown/CSV/PDF/bundle outputs | `id`, `organization_id`, `project_id`, `shareable_report_id`, `format`, `storage_key_hash`, `content_hash`, `scan_status`, `created_by`, `created_at`, `expires_at` |
| `share_links` | external or auth-bound report links | `id`, `organization_id`, `project_id`, `shareable_report_id`, `token_hash`, `scope`, `expires_at`, `revoked_at`, `created_by`, `last_viewed_at` |
| `retention_policies` | tenant/project retention config | `id`, `organization_id`, `project_id`, `runs_days`, `trace_days`, `media_days`, `exports_days`, `audit_days`, `legal_hold_enabled`, `created_at` |
| `redaction_scans` | export/import scanner evidence | `id`, `organization_id`, `project_id`, `object_type`, `object_id`, `policy_version`, `status`, `finding_counts_json`, `created_at` |
| `import_jobs` | async/idempotent ingest | `id`, `organization_id`, `project_id`, `source_kind`, `idempotency_key_hash`, `payload_hash`, `status`, `row_counts_json`, `created_at`, `completed_at` |

DB invariants:

- Every customer-owned row carries `organization_id` and `project_id`, except global role catalog rows.
- Public/share tokens are stored as hashes and are never database ids.
- Secret-bearing values are stored only as hashes, encrypted server-side blobs, or short-lived minted access, never in report snapshots.
- Raw imported payloads may be stored only in private quarantine/object storage with hashes; normalized DB rows and hosted reports expose redacted summaries.
- `audit_events` are append-only in normal operation. Corrections are new events, not destructive rewrites.

## 5. Environment Variables And Redaction Contract

Self-host deployments must document these variables. Operators may provide values through their secret manager, container runtime, or local `.env` equivalent, but A3 docs, tests, logs, API responses, reports, and screenshots must never print secret values.

| Variable | Required | Redaction Class | Purpose |
|---|---:|---|---|
| `PORT` | yes | public | HTTP listen port |
| `RELEASEFOUNDRY_A3_DEPLOYMENT_MODE` | yes | public | `local`, `self_host`, or `enterprise` |
| `RELEASEFOUNDRY_A3_BASE_URL` | yes | public_internal | canonical console URL |
| `RELEASEFOUNDRY_A3_DB_URL` | yes in self-host | secret | PostgreSQL/MySQL/SQLite connection string; print only `[REDACTED_DB_URL]` |
| `RELEASEFOUNDRY_A3_DB_SSL_MODE` | no | public | DB TLS policy |
| `RELEASEFOUNDRY_A3_SECRET_KEY_BASE` | yes | secret | session/signing key material |
| `RELEASEFOUNDRY_A3_SESSION_COOKIE_NAME` | yes | public_internal | cookie name only, not cookie value |
| `RELEASEFOUNDRY_A3_AUTH_PROVIDER` | yes | public | `local_mock`, `oidc`, or platform auth |
| `RELEASEFOUNDRY_A3_OIDC_ISSUER` | yes for OIDC | public_internal | issuer URL |
| `RELEASEFOUNDRY_A3_OIDC_CLIENT_ID` | yes for OIDC | confidential_identifier | client id; may show last 4 chars only |
| `RELEASEFOUNDRY_A3_OIDC_CLIENT_SECRET` | yes for OIDC | secret | client secret |
| `RELEASEFOUNDRY_A3_API_KEY_PEPPER` | yes for API keys | secret | server-side API-key hash pepper |
| `RELEASEFOUNDRY_A3_OBJECT_STORE_URL` | yes for exports/media | public_internal | object store endpoint |
| `RELEASEFOUNDRY_A3_OBJECT_STORE_BUCKET` | yes for exports/media | public_internal | bucket/container name |
| `RELEASEFOUNDRY_A3_OBJECT_STORE_ACCESS_KEY_ID` | yes for exports/media | secret | storage access key id |
| `RELEASEFOUNDRY_A3_OBJECT_STORE_SECRET_ACCESS_KEY` | yes for exports/media | secret | storage secret |
| `RELEASEFOUNDRY_A3_SIGNED_URL_TTL_SECONDS` | yes for media/downloads | public | max short-lived URL TTL |
| `RELEASEFOUNDRY_A3_REDACTION_POLICY_VERSION` | yes | public | active export/import redaction policy |
| `RELEASEFOUNDRY_A3_ENABLE_PUBLIC_SHARE_LINKS` | yes | public | must be `false` unless share-link policy is implemented |
| `RELEASEFOUNDRY_A3_IMPORT_MAX_BYTES` | yes | public | max import request size |
| `RELEASEFOUNDRY_A3_RUN_RETENTION_DAYS` | yes | public | normalized run retention |
| `RELEASEFOUNDRY_A3_TRACE_RETENTION_DAYS` | yes | public | trace/observation retention |
| `RELEASEFOUNDRY_A3_MEDIA_RETENTION_DAYS` | yes | public | media metadata/private object retention |
| `RELEASEFOUNDRY_A3_EXPORT_RETENTION_DAYS` | yes | public | export artifact retention |
| `RELEASEFOUNDRY_A3_AUDIT_RETENTION_DAYS` | yes | public | audit log retention; enterprise default should be at least 365 |
| `RELEASEFOUNDRY_A3_A1_COMPAT_VERSION` | yes | public | expected A1 contract version, currently `releasefoundry.run.v1` compatible |
| `RELEASEFOUNDRY_A3_A2_COMPAT_VERSION` | yes | public | expected A2 grade version, currently `a2.grade_results.v1` compatible |
| `RELEASEFOUNDRY_A3_LOG_LEVEL` | no | public | runtime log verbosity |

Redaction rules:

- Secret values render as `[REDACTED]`, `[REDACTED_DB_URL]`, `[REDACTED_SECRET]`, or a typed hash reference.
- API key values are never returned after creation. The console may show `prefix_redacted`, `scopes`, `created_at`, `last_used_at`, and `revoked_at`.
- OIDC client ids, object store bucket names, and base URLs are treated as `public_internal`; they may appear in operator-only diagnostics but not public hosted reports.
- Signed URLs are never durable report content. Store `storage_key_hash` and mint short-lived URLs only after authorization.
- `.env.local` and equivalent local secret files are outside committed evidence and must not be read for documentation.

## 6. Health Checks And Readiness

Minimum endpoints:

| Check | Endpoint Or Probe | Pass Condition | Failure Response |
|---|---|---|---|
| API liveness | `GET /api/a3/health` | `ok=true`, `service=a3-api` | `503` or `ok=false` with redacted reason |
| DB contract | `GET /api/a3/db-contract` | `schema_version=a3.saas_db_contract.v1`; required tables present in migration state | missing table list, no DB URL |
| Dashboard read | `GET /api/a3/dashboard?source=mock` or seeded source | `a3.api_dashboard_payload.v1`; storage contract present | source unavailable with safe error |
| Admin console read | `GET /api/a3/admin/console` | `a3.saas_admin_console.v1`; safety flags false for real mutations until enabled | safe degraded state |
| Report build/redaction | `POST /api/a3/reports/share` on seeded run | `a3.shareable_report.v1`; `sealed_evidence.secret_free=true` | blocked redaction status and audit event |
| DB connectivity | internal migration/query probe | migrations applied, read/write transaction succeeds | redacted driver error class |
| Object storage | internal signed write/read/delete probe | private bucket reachable; no public URL leakage | redacted storage error class |
| Export worker | queue heartbeat | worker processes no-op job and records audit event | degraded export queue |
| Audit log | append/read probe | can append `system.health_checked` and read by id | fail closed for mutating admin actions |
| A1 compatibility | seeded A1 RunResult import/normalize | run/cases/traces/tool calls normalize without schema drift | compatibility warning, import blocked if required fields missing |
| A2 compatibility | seeded A2 grade import/normalize | pass/fail, score, primary failure class, judge evidence preserved | compatibility warning, import blocked if score scale unknown |

Safe diagnostics may include:

- schema versions,
- table names,
- migration version,
- row counts,
- source labels,
- content hashes,
- redaction policy version,
- pass/fail status.

Safe diagnostics must not include:

- DB URLs,
- credentials,
- auth headers,
- cookies,
- session ids,
- raw signed URLs,
- raw customer prompts/traces/media,
- local user home paths,
- email addresses or account identifiers.

## 7. Retention And Audit Controls

Default retention policy for enterprise self-host:

| Data Class | Default Retention | Deletion Behavior | Legal Hold |
|---|---:|---|---|
| normalized runs and cases | 180 days | soft delete then purge after grace period | yes |
| trace events and observations | 90 days | purge or aggregate to hashes/counts | yes |
| media metadata | 90 days | purge metadata and private object pointers | yes |
| private raw import quarantine | 30 days | purge after successful normalization unless hold exists | yes |
| report snapshots | 365 days | retain immutable content hash; purge body after retention if policy allows | yes |
| export artifacts | 90 days | expire download and remove object | yes |
| share links | 30 days max by default | expire automatically; revocation immediate | no, link token remains hashed only |
| audit events | 365 days minimum | append-only; archive before purge | yes |
| usage ledger | 365 days | aggregate before purge if billing needs it | yes |

Required audit events:

- `auth.login_succeeded`
- `auth.login_failed`
- `project.switched`
- `run.import_requested`
- `run.import_completed`
- `run.import_failed`
- `case.viewed`
- `report.snapshot_created`
- `report.redaction_blocked`
- `report.share_link_created`
- `report.share_link_viewed`
- `report.share_link_revoked`
- `export.queued`
- `export.completed`
- `export.failed`
- `team.invite_planned`
- `team.role_change_planned`
- `api_key.create_planned`
- `api_key.rotate_planned`
- `api_key.revoke_planned`
- `trust.publish_planned`
- `retention.purge_planned`
- `retention.legal_hold_enabled`
- `retention.legal_hold_released`
- `system.health_checked`

Audit event payload rules:

- Include actor id, organization id, project id, object type, object id, timestamp, policy version, and hash references.
- Store `metadata_redacted_json`, never raw credentials or raw customer payloads.
- Chain high-value events with a stable event hash so audit bundles can prove continuity.
- Retention deletes must create audit events before data is purged.
- Self-approval remains disabled for release exceptions and trust publication.

## 8. Redaction And Export Controls

The existing A3 report path already uses an export redaction firewall. The self-host contract makes that firewall a release gate.

Required redaction gates:

- Import pre-scan for raw A1/A2/A3/official payloads.
- Report snapshot scan before `shareable_reports` insert is marked publishable.
- Export scan before JSON, Markdown, CSV, PDF, or audit bundle is downloadable.
- Share-link scan before a public or restricted link is enabled.
- Audit bundle scan before bundle hash is sealed.

Blocked categories:

- API keys, bearer tokens, cookies, auth headers, OAuth client secrets.
- DB URLs and storage credentials.
- Raw signed URLs or durable media access URLs.
- Spreadsheet formulas in CSV/tabular exports.
- Email addresses and account identifiers unless tokenized by policy.
- Local absolute paths under user home directories.
- Unknown high-entropy strings when fail-closed export mode is enabled.

Allowed exported evidence:

- schema versions,
- redacted titles and summaries,
- pass/fail and score data,
- canonical A2 failure classes,
- judge modes and redacted failure summaries,
- tool names and redacted argument hashes,
- content hashes,
- row counts,
- redaction finding counts,
- audit event ids and hashes.

## 9. A1/A2 Compatibility Expectations

Compatibility is additive. The self-host console must not force A1 or A2 to change existing output shapes before A3 can import and display evidence.

A1 expectations:

- Accept A1 `RunResult` root objects with `run_id`, `dataset_id`, `runner_id`, `status`, `cases[]`, aggregate metrics, and trace completeness.
- Accept A1 case objects with `case_id`, `scenario_id`, `title`, `status`, `latency_ms`, `expected`, `actual`, `agent_output`, `observations[]`, optional `trace_events[]`, optional `grade`, and metadata.
- Accept A1 `AgentTurn` tool calls with `name`, `arguments`, `call_id`, `output`, `latency_ms`, and `error`.
- Preserve A1 trace and observation evidence as redacted `trace_events`/`observations`, not as lossy report-only text.
- Normalize A1 score values on the 0-1 scale into A3 display scores only when score provenance is recorded.

A2 expectations:

- Accept A2 aggregate `a2.grade_results.v1` with `grade_results[]`, `total_cases`, `passed`, `failed`, `dataset_id`, and `scenario_pack`.
- Accept A2 single local judge outputs with pass/fail, 0-100 score, `primary_failure_class`, `judge_results[]`, `failure_analysis`, and evidence.
- Preserve canonical A2 failure classes or `none` as the primary clustering key.
- Preserve judge modes, max score, severity, remediation, safety-blocking status, and compact evidence references.
- Treat A2 coverage, calibration, readiness, semantic harness, case book, regression replay, SDK parity, and commercial readiness as optional feeds. Missing optional feeds produce explicit unavailable states, not crashes.

A3 compatibility envelope:

- Current normalized dashboard/report fields remain backward-compatible unless the schema version changes.
- `a3.api_dashboard_payload.v1`, `a3.api_run_list.v1`, `a3.api_run_detail.v1`, `a3.api_case_detail.v1`, `a3.shareable_report.v1`, and `a3.saas_admin_console.v1` are the self-host API DTO baseline.
- Unknown source fields may be hashed and quarantined, but are not blindly exposed to the browser.
- Missing optional evidence is shown as `unavailable`, `not_loaded`, or `not_applicable`.
- Official API-shaped run payloads using `result.tests[]` and `action_results[]` remain import-compatible through the existing P3 mapper boundary.

Compatibility health must fail closed when:

- score scale cannot be determined,
- required case ids are missing,
- A2 primary failure class is unknown and cannot be mapped,
- redaction pre-scan blocks import,
- source payload schema version is unsupported,
- a cross-project source id collision is detected.

## 10. Acceptance Criteria

Self-host/enterprise console is contract-complete when:

- All pages listed in this contract have a route-level owner and API DTO.
- Required DB tables exist in migrations with `organization_id` and `project_id` scoping.
- Required env vars are documented with redaction classes and never printed in tests/logs.
- Health checks cover API, DB contract, dashboard read, admin read, report redaction, object storage, export worker, audit log, and A1/A2 compatibility.
- Retention policy, legal hold, and audit events are persisted and included in release evidence.
- Shareable reports are immutable, redacted, hash-sealed snapshots.
- Export artifacts are generated from the same report snapshot shown in the hosted report.
- A1 RunResult and A2 grade imports preserve existing semantics and score scales.
- Admin mutations remain plan-only until hosted auth, RBAC, audit events, and server-side services exist.

Recommended verification command for this document:

```text
node --test tests/a3/self_host_console_contract.test.mjs
```
