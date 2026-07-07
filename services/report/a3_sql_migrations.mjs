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
      "Import endpoints must write idempotency_keys and api_import_receipts before exposing dashboard state.",
      "Hosted report views and revocations must write audit_events.",
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
    statement("006_reports_audit_usage", ["shareable_reports", "report_view_events", "report_revocations", "audit_events", "usage_ledger"], `
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
CREATE TABLE IF NOT EXISTS report_view_events (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT NOT NULL REFERENCES shareable_reports(id),
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
CREATE INDEX IF NOT EXISTS idx_usage_meter ON usage_ledger(organization_id, project_id, meter, period_start);`)
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
