# P3 SQL Adapter Contract For A3 Store Evolution - 2026-07-07

Author: A3 SQL Adapter Worker
Scope: contract artifact only. This document defines the concrete Postgres-compatible persistence contract for evolving A3 from memory/file fixtures to a SQL-backed store. It does not require service or app code changes in this pass, and it does not include secret values.

ANCHOR: A3_SQL_ADAPTER_CONTRACT

## 1. Contract Status

Current A3 store modes are memory-backed, fixture-backed, and file-backed. The SQL adapter must preserve the same A3 read/write semantics while moving durable product state into PostgreSQL-compatible tables.

Required compatibility anchors:

- Existing API/store schema anchor: `a3.saas_db_contract.v1`.
- Dashboard DTO baseline: `a3.api_dashboard_payload.v1`.
- Run list DTO baseline: `a3.api_run_list.v1`.
- Run detail DTO baseline: `a3.api_run_detail.v1`.
- Case detail DTO baseline: `a3.api_case_detail.v1`.
- Shareable report DTO baseline: `a3.shareable_report.v1`.
- A1 import receipt baseline: `a3.a1_run_result_ingest.v1`.
- A2 import receipt baseline: `a3.a2_grade_result_ingest.v1`.

The first SQL adapter is expected to be Postgres-native. SQLite or file-backed stores may remain local developer conveniences, but production semantics are defined by this document.

## 2. Adapter Boundary

The SQL adapter must implement the same logical operations as the current A3 store:

| Operation | SQL Contract |
|---|---|
| `getDashboardSnapshot(source)` | Read project-scoped runs, cases, grades, traces, media metadata, usage summary, and latest report state without exposing raw import payloads. |
| `listRuns(options)` | Query `runs` with tenant predicates, filters, pagination, and aggregate case counts. |
| `getRun(runId, options)` | Read one run and scoped child cases by internal id or source run id. |
| `getCase(caseId, options)` | Read one case detail with grade, tool calls, trace summaries, and media metadata. |
| `importA1RunResult(payload)` | Write `import_jobs`, `idempotency_ledger`, `source_payloads`, `a1_run_imports`, normalized `runs`, `cases`, `tool_calls`, and `trace_events`. |
| `importA2GradeResult(payload)` | Write `import_jobs`, `idempotency_ledger`, `source_payloads`, `a2_grade_imports`, normalized `grade_results`, and optional `failure_clusters`. |
| `createShareableReport(options)` | Write immutable `shareable_reports`, optional `report_exports`, `report_share_links`, and `audit_events`. |
| `getReport(reportId)` | Read one authorized report snapshot or return null. |
| `listReports()` | Read report metadata only; report bodies require authorization and redaction status checks. |

Adapter rules:

- All write paths run inside a database transaction.
- Idempotency is checked before normalization writes and recorded after a successful commit.
- Replays of the same idempotency key and payload hash return the original receipt.
- Replays with the same idempotency key and a different payload hash fail closed.
- Raw source payloads are quarantined or redacted; dashboard/report reads use normalized tables.

## 3. Tenancy Rules

ANCHOR: TENANCY_RULES

A3 SQL is multi-tenant by contract even before hosted auth is fully implemented.

Required rules:

- Every customer-owned table carries `organization_id` and `project_id`.
- `organizations` rows are scoped only by `id`.
- `projects` rows carry `organization_id` and define the project boundary.
- Global catalog tables, such as `roles`, may omit `project_id` only when they contain no customer data.
- Every API read includes `organization_id = $tenantOrgId` and `project_id = $tenantProjectId` when the table has those columns.
- Cross-project joins must join on both object ids and matching tenant columns.
- Public report tokens are never database ids; only token hashes are stored.
- Deleting or archiving a project does not erase audit history. New audit events record retention actions.

Recommended Postgres row-level security policy shape:

```sql
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY a3_runs_project_scope ON runs
  USING (
    organization_id = current_setting('app.organization_id')::uuid
    AND project_id = current_setting('app.project_id')::uuid
  );
```

The adapter may start with application-enforced predicates, but migrations should keep the schema ready for row-level security.

## 4. Tables

ANCHOR: REQUIRED_TABLES

All ids are UUIDs unless explicitly described otherwise. All timestamps are `timestamptz`. JSON fields should use `jsonb`.

| Table | Purpose | Required Columns |
|---|---|---|
| `organizations` | Tenant root | `id`, `display_name_redacted`, `plan`, `created_at`, `deleted_at` |
| `projects` | Product workspace | `id`, `organization_id`, `display_name`, `environment`, `created_at`, `archived_at` |
| `users` | Authenticated actor metadata | `id`, `organization_id`, `provider`, `provider_subject_hash`, `display_name_redacted`, `created_at`, `disabled_at` |
| `roles` | Permission catalog | `id`, `name`, `permissions_json`, `created_at` |
| `team_members` | User membership | `id`, `organization_id`, `project_id`, `user_id`, `role_id`, `status`, `created_at`, `removed_at` |
| `api_keys` | Machine credential metadata | `id`, `organization_id`, `project_id`, `name`, `prefix_redacted`, `secret_hash`, `scopes_json`, `created_by`, `last_used_at`, `revoked_at` |
| `idempotency_ledger` | Duplicate-safe writes | `id`, `organization_id`, `project_id`, `idempotency_key_hash`, `request_hash`, `operation`, `status`, `response_json`, `created_at`, `completed_at` |
| `import_jobs` | Import lifecycle | `id`, `organization_id`, `project_id`, `source_kind`, `idempotency_ledger_id`, `payload_hash`, `status`, `row_counts_json`, `error_code`, `created_by`, `created_at`, `completed_at` |
| `source_payloads` | Redacted/quarantined source envelope metadata | `id`, `organization_id`, `project_id`, `import_job_id`, `source_kind`, `schema_version`, `payload_hash`, `storage_key_hash`, `redaction_status`, `created_at` |
| `runs` | A1/A2/A3 run identity | `id`, `organization_id`, `project_id`, `import_job_id`, `source_kind`, `source_run_id`, `dataset_id`, `runner_id`, `status`, `started_at`, `ended_at`, `raw_payload_hash`, `created_at` |
| `cases` | Case summary and display | `id`, `organization_id`, `project_id`, `run_id`, `source_case_id`, `scenario_id`, `title_redacted`, `status`, `score`, `primary_failure_class`, `latency_ms`, `created_at` |
| `tool_calls` | Expected/actual tool evidence | `id`, `organization_id`, `project_id`, `case_id`, `call_id`, `name`, `arguments_redacted_json`, `output_redacted_json`, `match_status`, `seq`, `created_at` |
| `trace_events` | Replay timeline | `id`, `organization_id`, `project_id`, `run_id`, `case_id`, `seq`, `event_type`, `phase`, `source`, `event_at`, `redacted_payload_json`, `created_at` |
| `grade_results` | A2/A3 judge output | `id`, `organization_id`, `project_id`, `case_id`, `source_grade_id`, `passed`, `score`, `score_scale`, `primary_failure_class`, `severity`, `judge_modes_json`, `raw_payload_hash`, `created_at` |
| `failure_clusters` | Report grouping | `id`, `organization_id`, `project_id`, `run_id`, `primary_failure_class`, `case_count`, `severity`, `summary_redacted`, `created_at` |
| `media_evidence` | Media/file metadata | `id`, `organization_id`, `project_id`, `case_id`, `kind`, `mime_type`, `storage_key_hash`, `redaction_status`, `expires_at`, `created_at` |
| `shareable_reports` | Immutable hosted report snapshot | `id`, `organization_id`, `project_id`, `run_id`, `snapshot_version`, `builder_version`, `redaction_policy_version`, `content_hash`, `status`, `created_by`, `created_at` |
| `report_exports` | Generated JSON/Markdown/CSV/PDF/bundle outputs | `id`, `organization_id`, `project_id`, `shareable_report_id`, `format`, `storage_key_hash`, `content_hash`, `scan_status`, `created_by`, `created_at`, `expires_at` |
| `report_share_links` | External or auth-bound report links | `id`, `organization_id`, `project_id`, `shareable_report_id`, `token_hash`, `scope`, `expires_at`, `revoked_at`, `created_by`, `created_at`, `last_viewed_at` |
| `report_share_revocations` | Revocation history | `id`, `organization_id`, `project_id`, `report_share_link_id`, `revoked_by`, `reason_code`, `created_at` |
| `report_share_views` | Share-link access ledger | `id`, `organization_id`, `project_id`, `report_share_link_id`, `viewer_hash`, `result`, `viewed_at`, `metadata_redacted_json` |
| `trust_reports` | Enterprise trust/audit view | `id`, `organization_id`, `project_id`, `shareable_report_id`, `release_gate_decision`, `approval_state`, `published_at`, `revoked_at` |
| `audit_events` | Durable audit event log | `id`, `organization_id`, `project_id`, `actor_id`, `event_type`, `object_type`, `object_id`, `created_at`, `metadata_redacted_json`, `hash`, `previous_hash` |
| `usage_ledger` | Usage and quota accounting | `id`, `organization_id`, `project_id`, `event_type`, `quantity`, `unit`, `source_id`, `source_table`, `created_at` |
| `retention_policies` | Tenant/project retention configuration | `id`, `organization_id`, `project_id`, `runs_days`, `trace_days`, `media_days`, `exports_days`, `audit_days`, `legal_hold_enabled`, `created_at` |
| `redaction_scans` | Import/report/export scanner evidence | `id`, `organization_id`, `project_id`, `object_type`, `object_id`, `policy_version`, `status`, `finding_counts_json`, `created_at` |

## 5. A1/A2 Import Tables

ANCHOR: A1_A2_IMPORT_TABLES

The SQL adapter must keep normalized A3 tables readable while preserving import provenance for A1 and A2.

| Table | Purpose | Required Columns |
|---|---|---|
| `a1_run_imports` | A1 RunResult root mapping | `id`, `organization_id`, `project_id`, `import_job_id`, `run_id`, `source_run_id`, `a1_schema_version`, `payload_hash`, `trace_completeness`, `created_at` |
| `a1_case_imports` | A1 case mapping | `id`, `organization_id`, `project_id`, `a1_run_import_id`, `case_id`, `source_case_id`, `scenario_id`, `payload_hash`, `created_at` |
| `a1_trace_imports` | A1 trace/observation mapping | `id`, `organization_id`, `project_id`, `a1_case_import_id`, `trace_event_id`, `source_event_id`, `seq`, `payload_hash`, `created_at` |
| `a2_grade_imports` | A2 grade result mapping | `id`, `organization_id`, `project_id`, `import_job_id`, `grade_result_id`, `source_grade_id`, `a2_schema_version`, `score_scale`, `payload_hash`, `created_at` |
| `a2_judge_imports` | A2 judge detail mapping | `id`, `organization_id`, `project_id`, `a2_grade_import_id`, `judge_mode`, `passed`, `score`, `payload_hash`, `created_at` |

Import invariants:

- A1 `RunResult` imports create or update normalized `runs`, `cases`, `tool_calls`, and `trace_events`.
- A2 grade imports attach to existing cases by tenant plus `source_case_id` or create grade-only placeholders marked `evidence_pending`.
- A2 score scale is stored explicitly as `score_scale` and never guessed during report rendering.
- `source_payloads.payload_hash` and import table payload hashes are SHA-256 hex strings.
- Unknown source fields can be retained only through redacted metadata or private quarantined payload references.

## 6. Idempotency Ledger

ANCHOR: IDEMPOTENCY_LEDGER

Every mutating adapter operation accepts or derives an idempotency key.

Required operation names:

- `import.a1_run_result`
- `import.a2_grade_result`
- `report.snapshot_create`
- `report.export_create`
- `report.share_link_create`
- `report.share_link_revoke`

Postgres-compatible uniqueness:

```sql
CREATE UNIQUE INDEX idx_idempotency_ledger_key
  ON idempotency_ledger (organization_id, project_id, operation, idempotency_key_hash);
```

Replay behavior:

| Existing Ledger State | Incoming Request | Result |
|---|---|---|
| no row | any valid request | Insert `processing`, perform write, then store receipt as `completed`. |
| `completed` with same request hash | same operation/key/hash | Return stored `response_json` without duplicate writes. |
| `processing` and not expired | same operation/key | Return retryable conflict. |
| `failed` with same request hash | same operation/key/hash | Allow retry only if operation is marked retryable. |
| any state with different request hash | same operation/key, different hash | Fail closed with idempotency conflict. |

## 7. Audit Events

ANCHOR: AUDIT_EVENTS

Audit events are append-only in normal operation. Corrections are represented as new events.

Required event types:

- `run.import_requested`
- `run.import_completed`
- `run.import_failed`
- `case.viewed`
- `report.snapshot_created`
- `report.redaction_blocked`
- `report.export_queued`
- `report.export_completed`
- `report.export_failed`
- `report.share_link_created`
- `report.share_link_viewed`
- `report.share_link_revoked`
- `usage.recorded`
- `retention.purge_planned`
- `retention.legal_hold_enabled`
- `system.health_checked`

Audit rules:

- `audit_events.metadata_redacted_json` contains ids, hashes, counts, policy versions, and safe error classes only.
- `audit_events.hash` chains high-value events with `previous_hash` for bundle verification.
- Report share create/revoke/view writes always create audit events in the same transaction as the share table write.
- Import completion writes row counts but not raw prompt, response, trace, token, cookie, DB URL, or signed URL values.

## 8. Report Share/Revoke/View Contract

ANCHOR: REPORT_SHARE_REVOKE_VIEW

Share-link tables separate hosted report state from external access state.

Required behavior:

- `shareable_reports` are immutable report snapshots.
- `report_share_links.token_hash` is a hash of the external token, never the raw token.
- Creating a link writes `report_share_links` and `audit_events(event_type='report.share_link_created')`.
- Revoking a link sets `report_share_links.revoked_at`, inserts `report_share_revocations`, and writes `audit_events(event_type='report.share_link_revoked')`.
- Viewing a link inserts `report_share_views`, updates `report_share_links.last_viewed_at`, and writes `audit_events(event_type='report.share_link_viewed')`.
- Expired or revoked links return controlled errors and do not return report bodies.

Recommended status values for `report_share_views.result`:

- `allowed`
- `expired`
- `revoked`
- `not_found`
- `auth_required`
- `redaction_blocked`

## 9. Usage Ledger

ANCHOR: USAGE_LEDGER

`usage_ledger` is the append-only source for usage and quota calculations.
The usage_ledger is the append-only source for product usage, quota, and billing-adjacent evidence.

Required usage events:

- `run.imported`
- `case.imported`
- `trace_event.imported`
- `grade.imported`
- `report.snapshot_created`
- `report.export_created`
- `report.share_viewed`
- `media.reference_created`

Usage rules:

- Quantities are positive integers.
- Corrections are represented as compensating negative entries only when billing policy allows them; otherwise use a distinct `usage.adjustment_planned` event.
- `source_table` and `source_id` point to the normalized object that caused usage.
- Usage rows are tenant scoped and never contain raw payload data.

## 10. Indexes

ANCHOR: REQUIRED_INDEXES

Postgres migrations must create these indexes or strictly stronger equivalents.

```sql
CREATE UNIQUE INDEX idx_projects_org_display
  ON projects (organization_id, lower(display_name))
  WHERE archived_at IS NULL;

CREATE UNIQUE INDEX idx_api_keys_secret_hash
  ON api_keys (organization_id, project_id, secret_hash)
  WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX idx_idempotency_ledger_key
  ON idempotency_ledger (organization_id, project_id, operation, idempotency_key_hash);

CREATE UNIQUE INDEX idx_import_jobs_payload
  ON import_jobs (organization_id, project_id, source_kind, payload_hash);

CREATE UNIQUE INDEX idx_runs_source
  ON runs (organization_id, project_id, source_kind, source_run_id);

CREATE INDEX idx_runs_project_status_started
  ON runs (organization_id, project_id, status, started_at DESC);

CREATE UNIQUE INDEX idx_cases_source
  ON cases (organization_id, project_id, run_id, source_case_id);

CREATE INDEX idx_cases_project_failure
  ON cases (organization_id, project_id, primary_failure_class, status);

CREATE INDEX idx_trace_events_case_seq
  ON trace_events (organization_id, project_id, case_id, seq);

CREATE INDEX idx_tool_calls_case_seq
  ON tool_calls (organization_id, project_id, case_id, seq);

CREATE INDEX idx_grade_results_case
  ON grade_results (organization_id, project_id, case_id, created_at DESC);

CREATE INDEX idx_media_evidence_case
  ON media_evidence (organization_id, project_id, case_id, redaction_status);

CREATE UNIQUE INDEX idx_shareable_reports_content
  ON shareable_reports (organization_id, project_id, content_hash);

CREATE INDEX idx_report_exports_report
  ON report_exports (organization_id, project_id, shareable_report_id, format);

CREATE UNIQUE INDEX idx_report_share_links_token
  ON report_share_links (token_hash);

CREATE INDEX idx_report_share_revocations_link
  ON report_share_revocations (organization_id, project_id, report_share_link_id);

CREATE INDEX idx_report_share_views_link_time
  ON report_share_views (organization_id, project_id, report_share_link_id, viewed_at DESC);

CREATE INDEX idx_audit_events_project_time
  ON audit_events (organization_id, project_id, created_at DESC);

CREATE INDEX idx_audit_events_object
  ON audit_events (organization_id, project_id, object_type, object_id);

CREATE INDEX idx_usage_ledger_project_time
  ON usage_ledger (organization_id, project_id, created_at DESC);

CREATE INDEX idx_a1_run_imports_source
  ON a1_run_imports (organization_id, project_id, source_run_id);

CREATE INDEX idx_a1_case_imports_source
  ON a1_case_imports (organization_id, project_id, source_case_id);

CREATE INDEX idx_a2_grade_imports_source
  ON a2_grade_imports (organization_id, project_id, source_grade_id);
```

## 11. Minimal DDL Shape

ANCHOR: POSTGRES_DDL_SHAPE

The exact migration files may add constraints and metadata, but they must remain compatible with the following shape.

```sql
CREATE TABLE idempotency_ledger (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  idempotency_key_hash text NOT NULL,
  request_hash text NOT NULL,
  operation text NOT NULL,
  status text NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
  response_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE runs (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  import_job_id uuid,
  source_kind text NOT NULL,
  source_run_id text NOT NULL,
  dataset_id text,
  runner_id text,
  status text NOT NULL,
  started_at timestamptz,
  ended_at timestamptz,
  raw_payload_hash text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cases (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES runs(id),
  source_case_id text NOT NULL,
  scenario_id text,
  title_redacted text,
  status text NOT NULL,
  score numeric,
  primary_failure_class text,
  latency_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE shareable_reports (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid REFERENCES runs(id),
  snapshot_version integer NOT NULL,
  builder_version text NOT NULL,
  redaction_policy_version text NOT NULL,
  content_hash text NOT NULL,
  status text NOT NULL,
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  actor_id uuid,
  event_type text NOT NULL,
  object_type text NOT NULL,
  object_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata_redacted_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  hash text NOT NULL,
  previous_hash text
);
```

## 12. Fixture-To-SQL Migration

ANCHOR: FIXTURE_TO_SQL_MIGRATION

Migration from memory/file fixtures to SQL is additive:

1. Read the same sanitized fixture sources currently accepted by the A3 store.
2. Derive a deterministic `idempotency_key_hash` from source kind, source id, tenant, and payload hash when a caller does not provide one.
3. Insert one `import_jobs` row.
4. Insert one `source_payloads` metadata row with payload hash and redaction status.
5. Normalize A1 run data into `runs`, `cases`, `tool_calls`, and `trace_events`.
6. Normalize A2 judge data into `grade_results` and `failure_clusters`.
7. Insert `a1_*_imports` and `a2_*_imports` provenance rows.
8. Insert `usage_ledger` rows for imported runs, cases, traces, grades, media references, and reports.
9. Insert `audit_events` for requested/completed/failed import states.
10. Return the existing A3 ingest receipt shape.

Success evidence may print schema versions, row counts, ids, hashes, and pass/fail status. It must not print secrets, raw prompts, raw traces, auth headers, cookies, signed URLs, DB URLs, or `.env.local` values.

## 13. Redaction And Secret Safety

The SQL adapter never persists secret-bearing values in report-readable columns.

Forbidden durable report content:

- API keys, bearer tokens, cookies, auth headers, OAuth client secrets.
- Database URLs and storage credentials.
- Raw signed URLs or durable media access URLs.
- Local absolute home paths.
- Email addresses or account identifiers unless tokenized by policy.
- Spreadsheet formulas in CSV/tabular exports.

Allowed evidence:

- Schema versions.
- Status values.
- Canonical failure classes.
- Scores with explicit scale.
- Redacted summaries.
- Hashes.
- Row counts.
- Audit ids.
- Redaction finding counts.

## 14. Verification Command

Recommended guard for this artifact:

```text
node --test tests/a3/sql_adapter_contract.test.mjs
```
