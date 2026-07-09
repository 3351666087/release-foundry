export const A3_SQL_MIGRATION_SCHEMA_VERSION = "a3.sql_migration_plan.v1";

export function buildA3SqlMigrationPlan(options = {}) {
  const dialect = normalizeDialect(options.dialect || "postgres");
  const statements = migrationStatements(dialect);
  return {
    schema_version: A3_SQL_MIGRATION_SCHEMA_VERSION,
    dialect,
    status: "contract_ready",
    migration_count: statements.length,
    tenancy_columns: ["organization_id", "project_id"],
    guardrails: [
      "Every tenant-owned row must include organization_id and project_id.",
      "Team, RBAC, API key, and trust-center tables store metadata only until hosted auth is available.",
      "Import endpoints must write idempotency_keys and api_import_receipts before exposing dashboard state.",
      "Hosted report views and revocations must write audit_events.",
      "Artifact registry rows must link report exports, control-plane evidence, lifecycle events, redaction status, and retention class.",
      "SaaS admin actions are request/audit records first; real cloud mutations stay disabled until hosted auth and RBAC are enforced.",
      "Reviewer waiver and approval records must be hash-sealed, tenant-scoped, and durable before they can influence release governance.",
      "Release evidence summaries must be tenant-scoped, hash-sealed, and safe to expose through API-backed dashboard and hosted report snapshots.",
      "Release evidence v2 authority rows must separate immutable snapshots, safe diffs, and external readback states before claiming enterprise enforcement.",
      "Release evidence readback capture must be idempotent, tenant-scoped, audit-linked, and hash-only before it can influence PR gates.",
      "Secret values are never stored; API keys and idempotency keys are hashed.",
      "Postgres is the recommended production target; MySQL and SQLite dialects are contract targets for student/self-host deployments."
    ],
    statements
  };
}

function migrationStatements(dialect) {
  const types = dialectTypes(dialect);

  return [
    statement("001_organizations", ["organizations"], `
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'local_dev',
  created_at ${types.timestamp} NOT NULL
);`),
    statement("002_projects", ["projects"], `
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  display_name TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'staging',
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(organization_id);`),
    statement("003_identity_team_keys_trust", ["users", "roles", "team_members", "api_keys", "trust_reports"], `
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  identity_hash TEXT NOT NULL,
  display_name TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at ${types.timestamp} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_identity_hash ON users(organization_id, identity_hash);
CREATE TABLE IF NOT EXISTS roles (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL,
  permissions ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_roles_org_name ON roles(organization_id, name);
CREATE TABLE IF NOT EXISTS team_members (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  role_id TEXT NOT NULL REFERENCES roles(id),
  status TEXT NOT NULL DEFAULT 'active',
  invited_by_user_id TEXT,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_members_project ON team_members(project_id, status);
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  key_hash TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  name TEXT NOT NULL,
  scopes ${types.json} NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_by_user_id TEXT,
  last_used_at ${types.timestamp},
  revoked_at ${types.timestamp},
  created_at ${types.timestamp} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE TABLE IF NOT EXISTS trust_reports (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  report_id TEXT,
  status TEXT NOT NULL,
  release_gate_decision TEXT,
  evidence_hash TEXT,
  published_at ${types.timestamp},
  created_at ${types.timestamp} NOT NULL
);`),
    statement("003_runs_cases", ["runs", "cases"], `
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL REFERENCES projects(id),
  dataset_id TEXT,
  runner_id TEXT,
  status TEXT NOT NULL,
  trace_completeness REAL,
  raw_payload_hash TEXT NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES runs(id),
  scenario_id TEXT,
  status TEXT NOT NULL,
  score REAL,
  primary_failure_class TEXT,
  payload ${types.json} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_project_run ON cases(project_id, run_id);
CREATE INDEX IF NOT EXISTS idx_cases_failure ON cases(project_id, primary_failure_class, status);`),
    statement("004_trace_tool_grade", ["trace_events", "tool_calls", "grade_results"], `
CREATE TABLE IF NOT EXISTS trace_events (
  id ${types.serial},
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  event_type TEXT,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_calls (
  id ${types.serial},
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  tool_name TEXT,
  arguments_hash TEXT,
  payload ${types.json} NOT NULL
);
CREATE TABLE IF NOT EXISTS grade_results (
  id ${types.serial},
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  passed BOOLEAN,
  score REAL,
  primary_failure_class TEXT,
  judge_results ${types.json} NOT NULL,
  payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grade_case ON grade_results(project_id, case_id);`),
    statement("005_import_idempotency", ["idempotency_keys", "api_import_receipts"], `
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key_hash TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  request_type TEXT NOT NULL,
  source TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  response_payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_scope ON idempotency_keys(request_type, source, key_hash);
CREATE TABLE IF NOT EXISTS api_import_receipts (
  id ${types.serial},
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  source TEXT NOT NULL,
  request_type TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  imported_run_count INTEGER NOT NULL,
  imported_grade_count INTEGER NOT NULL,
  dashboard_case_count INTEGER NOT NULL,
  created_at ${types.timestamp} NOT NULL
);`),
    statement("006_reports_audit_usage", ["shareable_reports", "report_share_links", "report_view_events", "report_revocations", "audit_events", "usage_ledger"], `
CREATE TABLE IF NOT EXISTS shareable_reports (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  expires_at ${types.timestamp},
  revoked_at ${types.timestamp},
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS report_share_links (
  token_hash TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT NOT NULL REFERENCES shareable_reports(id),
  scope TEXT NOT NULL,
  expires_at ${types.timestamp},
  revoked_at ${types.timestamp},
  created_by TEXT,
  created_at ${types.timestamp} NOT NULL,
  last_viewed_at ${types.timestamp}
);
CREATE INDEX IF NOT EXISTS idx_report_share_links_report ON report_share_links(project_id, report_id);
CREATE TABLE IF NOT EXISTS report_view_events (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT NOT NULL REFERENCES shareable_reports(id),
  token_hash_prefix TEXT,
  access_result TEXT NOT NULL DEFAULT 'allowed',
  viewer_hash TEXT,
  viewed_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS report_revocations (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT NOT NULL REFERENCES shareable_reports(id),
  reason TEXT NOT NULL,
  revoked_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  subject_id TEXT,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_ledger (
  id ${types.serial},
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  meter TEXT NOT NULL,
  quantity REAL NOT NULL,
  source TEXT NOT NULL,
  period_start ${types.timestamp} NOT NULL,
  period_end ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_meter ON usage_ledger(organization_id, project_id, meter, period_start);`),
    statement("007_artifact_registry", ["artifact_registry_entries", "artifact_lifecycle_events"], `
CREATE TABLE IF NOT EXISTS artifact_registry_entries (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT,
  artifact_type TEXT NOT NULL,
  content_type TEXT NOT NULL,
  manifest_join_key TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL,
  hash_status TEXT NOT NULL,
  redaction_status TEXT NOT NULL,
  retention_class TEXT NOT NULL,
  share_scope TEXT NOT NULL,
  billable_meter TEXT,
  customer_value TEXT NOT NULL,
  missing_controls ${types.json} NOT NULL,
  raw_secret_values_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_share_token_stored BOOLEAN NOT NULL DEFAULT FALSE,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_registry_project_state ON artifact_registry_entries(project_id, lifecycle_state, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_registry_report ON artifact_registry_entries(project_id, report_id);
CREATE TABLE IF NOT EXISTS artifact_lifecycle_events (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL REFERENCES artifact_registry_entries(id),
  event_type TEXT NOT NULL,
  actor_hash TEXT,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_lifecycle_events_artifact ON artifact_lifecycle_events(project_id, artifact_id, created_at);`),
    statement("008_saas_admin_action_requests", ["saas_admin_action_requests"], `
CREATE TABLE IF NOT EXISTS saas_admin_action_requests (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  action TEXT NOT NULL,
  area TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  actor_hash TEXT,
  request_hash TEXT NOT NULL,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saas_admin_action_requests_project ON saas_admin_action_requests(project_id, area, status, created_at);`),
    statement("009_review_workflow_records", ["review_workflow_records"], `
CREATE TABLE IF NOT EXISTS review_workflow_records (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  record_type TEXT NOT NULL,
  run_id TEXT,
  release_version TEXT,
  environment TEXT,
  status TEXT NOT NULL,
  accepted BOOLEAN NOT NULL DEFAULT FALSE,
  payload_hash TEXT NOT NULL,
  review_hash TEXT NOT NULL,
  signature_status TEXT NOT NULL,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_workflow_records_release ON review_workflow_records(project_id, run_id, release_version, record_type, status);`),
    statement("010_release_evidence_summaries", ["release_evidence_summaries"], `
CREATE TABLE IF NOT EXISTS release_evidence_summaries (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  release_id TEXT NOT NULL,
  source TEXT NOT NULL,
  summary_schema_version TEXT NOT NULL,
  overall_status TEXT NOT NULL,
  summary_hash TEXT NOT NULL,
  payload ${types.json} NOT NULL,
  hosted_report_snapshot_id TEXT,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_evidence_project_release ON release_evidence_summaries(project_id, release_id, overall_status);
CREATE INDEX IF NOT EXISTS idx_release_evidence_summary_hash ON release_evidence_summaries(summary_hash);`),
    statement("011_release_evidence_authority_v2", ["release_evidence_snapshots", "release_evidence_diffs", "release_evidence_readbacks"], `
CREATE TABLE IF NOT EXISTS release_evidence_snapshots (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  release_id TEXT NOT NULL,
  summary_id TEXT NOT NULL,
  source_snapshot_id TEXT,
  summary_schema_version TEXT NOT NULL,
  summary_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  health_status TEXT NOT NULL,
  next_action TEXT,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_evidence_snapshots_release ON release_evidence_snapshots(project_id, release_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_release_evidence_snapshots_hash ON release_evidence_snapshots(project_id, summary_hash);
CREATE TABLE IF NOT EXISTS release_evidence_diffs (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  release_id TEXT NOT NULL,
  from_summary_id TEXT NOT NULL,
  to_summary_id TEXT NOT NULL,
  diff_hash TEXT NOT NULL,
  changed_field_count INTEGER NOT NULL,
  regression_count INTEGER NOT NULL,
  improvement_count INTEGER NOT NULL,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_evidence_diffs_release ON release_evidence_diffs(project_id, release_id, created_at);
CREATE TABLE IF NOT EXISTS release_evidence_readbacks (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  release_id TEXT NOT NULL,
  summary_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  readback_status TEXT NOT NULL,
  head_sha_alias TEXT,
  external_id_alias TEXT,
  payload_hash TEXT NOT NULL,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_evidence_readbacks_summary ON release_evidence_readbacks(project_id, summary_id, provider, readback_status);
CREATE INDEX IF NOT EXISTS idx_release_evidence_readbacks_release ON release_evidence_readbacks(project_id, release_id, provider, created_at);`)
    ,
    statement("012_commercial_api_contracts", ["commercial_api_contracts"], `
CREATE TABLE IF NOT EXISTS commercial_api_contracts (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'tenant-local',
  workspace_id TEXT NOT NULL DEFAULT 'workspace-local',
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  contract_schema_version TEXT NOT NULL,
  endpoint_count INTEGER NOT NULL,
  implemented_or_read_only_count INTEGER NOT NULL,
  plan_only_count INTEGER NOT NULL,
  blocked_by_auth_count INTEGER NOT NULL,
  contract_hash TEXT NOT NULL,
  payload ${types.json} NOT NULL,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commercial_api_contracts_project ON commercial_api_contracts(project_id, environment_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_commercial_api_contracts_hash ON commercial_api_contracts(project_id, contract_hash);`)
    ,
    statement("013_source_artifacts_and_event_outbox", ["source_artifacts", "event_outbox"], `
CREATE TABLE IF NOT EXISTS source_artifacts (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  source_lane TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  source_contracts ${types.json} NOT NULL,
  content_hash TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  redaction_status TEXT NOT NULL DEFAULT 'hash_only',
  raw_payload_embedded BOOLEAN NOT NULL DEFAULT FALSE,
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_artifacts_project ON source_artifacts(project_id, source_lane, artifact_type, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_artifacts_hash ON source_artifacts(project_id, artifact_type, content_hash);
CREATE TABLE IF NOT EXISTS event_outbox (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  payload_ref TEXT,
  payload_hash TEXT NOT NULL,
  redaction_status TEXT NOT NULL,
  delivery_status TEXT NOT NULL DEFAULT 'pending',
  created_at ${types.timestamp} NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_outbox_project ON event_outbox(project_id, event_type, delivery_status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_outbox_resource_hash ON event_outbox(project_id, resource_type, resource_id, payload_hash);`)
  ];
}

function dialectTypes(dialect) {
  if (dialect === "mysql") {
    return {
      serial: "BIGINT AUTO_INCREMENT PRIMARY KEY",
      json: "JSON",
      timestamp: "DATETIME"
    };
  }
  if (dialect === "sqlite") {
    return {
      serial: "INTEGER PRIMARY KEY AUTOINCREMENT",
      json: "TEXT",
      timestamp: "TEXT"
    };
  }
  return {
    serial: "GENERATED BY DEFAULT AS IDENTITY",
    json: "JSONB",
    timestamp: "TIMESTAMPTZ"
  };
}

function normalizeDialect(dialect) {
  if (["postgres", "mysql", "sqlite"].includes(dialect)) {
    return dialect;
  }
  return "postgres";
}

function statement(id, tables, sql) {
  return {
    id,
    tables,
    sql: sql.trim()
  };
}
