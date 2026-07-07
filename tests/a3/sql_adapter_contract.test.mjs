import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const DOC_PATH = new URL("../../docs/a3/p3_sql_adapter_contract_2026_07_07.md", import.meta.url);

test("A3 SQL adapter contract preserves critical section anchors", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredAnchors = [
    "ANCHOR: A3_SQL_ADAPTER_CONTRACT",
    "ANCHOR: TENANCY_RULES",
    "ANCHOR: REQUIRED_TABLES",
    "ANCHOR: A1_A2_IMPORT_TABLES",
    "ANCHOR: IDEMPOTENCY_LEDGER",
    "ANCHOR: AUDIT_EVENTS",
    "ANCHOR: REPORT_SHARE_REVOKE_VIEW",
    "ANCHOR: USAGE_LEDGER",
    "ANCHOR: REQUIRED_INDEXES",
    "ANCHOR: POSTGRES_DDL_SHAPE",
    "ANCHOR: FIXTURE_TO_SQL_MIGRATION"
  ];

  for (const anchor of requiredAnchors) {
    assert.ok(doc.includes(anchor), `missing SQL adapter anchor: ${anchor}`);
  }
});

test("A3 SQL adapter contract names required tables and import ledgers", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredTables = [
    "organizations",
    "projects",
    "users",
    "roles",
    "team_members",
    "api_keys",
    "idempotency_ledger",
    "import_jobs",
    "source_payloads",
    "runs",
    "cases",
    "tool_calls",
    "trace_events",
    "grade_results",
    "failure_clusters",
    "media_evidence",
    "shareable_reports",
    "report_exports",
    "report_share_links",
    "report_share_revocations",
    "report_share_views",
    "trust_reports",
    "audit_events",
    "usage_ledger",
    "retention_policies",
    "redaction_scans",
    "a1_run_imports",
    "a1_case_imports",
    "a1_trace_imports",
    "a2_grade_imports",
    "a2_judge_imports"
  ];

  for (const table of requiredTables) {
    assert.match(doc, new RegExp(`\`${escapeRegExp(table)}\``), `missing table: ${table}`);
  }
});

test("A3 SQL adapter contract guards tenancy, idempotency, audit, share, and usage semantics", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredTerms = [
    "a3.saas_db_contract.v1",
    "a3.api_dashboard_payload.v1",
    "a3.shareable_report.v1",
    "a3.a1_run_result_ingest.v1",
    "a3.a2_grade_result_ingest.v1",
    "Postgres",
    "organization_id = $tenantOrgId",
    "project_id = $tenantProjectId",
    "CREATE POLICY a3_runs_project_scope",
    "idempotency_key_hash",
    "same idempotency key and a different payload hash fail closed",
    "report.share_link_created",
    "report.share_link_viewed",
    "report.share_link_revoked",
    "usage_ledger is the append-only source",
    "A2 score scale is stored explicitly as `score_scale`",
    "Raw source payloads are quarantined or redacted"
  ];

  for (const term of requiredTerms) {
    assert.ok(doc.includes(term), `missing required contract term: ${term}`);
  }
});

test("A3 SQL adapter contract includes required Postgres index DDL", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredIndexes = [
    "idx_idempotency_ledger_key",
    "idx_import_jobs_payload",
    "idx_runs_source",
    "idx_runs_project_status_started",
    "idx_cases_source",
    "idx_cases_project_failure",
    "idx_trace_events_case_seq",
    "idx_tool_calls_case_seq",
    "idx_grade_results_case",
    "idx_media_evidence_case",
    "idx_shareable_reports_content",
    "idx_report_exports_report",
    "idx_report_share_links_token",
    "idx_report_share_revocations_link",
    "idx_report_share_views_link_time",
    "idx_audit_events_project_time",
    "idx_audit_events_object",
    "idx_usage_ledger_project_time",
    "idx_a1_run_imports_source",
    "idx_a1_case_imports_source",
    "idx_a2_grade_imports_source"
  ];

  for (const indexName of requiredIndexes) {
    assert.match(doc, new RegExp(`CREATE (?:UNIQUE )?INDEX ${escapeRegExp(indexName)}`), `missing index DDL: ${indexName}`);
  }
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

