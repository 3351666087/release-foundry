import assert from "node:assert/strict";
import { test } from "node:test";

import { buildReportCenterManifest } from "../../services/report/a3_report_center_manifest.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";

test("A3 SQL migration plan covers tenant-scoped import, report, audit, and usage tables", () => {
  const plan = buildA3SqlMigrationPlan();

  assert.equal(plan.schema_version, "a3.sql_migration_plan.v1");
  assert.equal(plan.dialect, "postgres");
  assert.ok(plan.migration_count >= 7);
  assert.ok(plan.guardrails.some((item) => item.includes("organization_id")));

  const sql = plan.statements.map((item) => item.sql).join("\n");
  for (const table of [
    "users",
    "roles",
    "team_members",
    "api_keys",
    "trust_reports",
    "idempotency_keys",
    "api_import_receipts",
    "shareable_reports",
    "report_share_links",
    "report_view_events",
    "report_revocations",
    "audit_events",
    "usage_ledger",
    "artifact_registry_entries",
    "artifact_lifecycle_events",
    "release_evidence_summaries",
    "release_evidence_snapshots",
    "release_evidence_diffs",
    "release_evidence_readbacks"
  ]) {
    assert.match(sql, new RegExp(`CREATE TABLE IF NOT EXISTS ${table}`));
  }
  assert.match(sql, /identity_hash TEXT NOT NULL/);
  assert.match(sql, /key_hash TEXT NOT NULL/);
  assert.match(sql, /release_gate_decision TEXT/);
  assert.match(sql, /token_hash TEXT PRIMARY KEY/);
  assert.match(sql, /access_result TEXT NOT NULL DEFAULT 'allowed'/);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS idx_usage_meter/);
  assert.match(sql, /manifest_join_key TEXT NOT NULL/);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS idx_artifact_registry_project_state/);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS idx_artifact_lifecycle_events_artifact/);
  assert.match(sql, /source_snapshot_id TEXT/);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS idx_release_evidence_snapshots_release/);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS idx_release_evidence_readbacks_summary/);
  assert.ok(plan.guardrails.some((item) => item.includes("v2 authority rows")));
});

test("A3 SQL migration plan documents Postgres, MySQL, and SQLite dialect targets", () => {
  const postgres = buildA3SqlMigrationPlan({ dialect: "postgres" });
  const mysql = buildA3SqlMigrationPlan({ dialect: "mysql" });
  const sqlite = buildA3SqlMigrationPlan({ dialect: "sqlite" });
  const fallback = buildA3SqlMigrationPlan({ dialect: "unknown" });

  assert.equal(postgres.dialect, "postgres");
  assert.match(postgres.statements.map((item) => item.sql).join("\n"), /JSONB/);
  assert.match(postgres.statements.map((item) => item.sql).join("\n"), /TIMESTAMPTZ/);

  assert.equal(mysql.dialect, "mysql");
  assert.match(mysql.statements.map((item) => item.sql).join("\n"), /BIGINT AUTO_INCREMENT PRIMARY KEY/);
  assert.match(mysql.statements.map((item) => item.sql).join("\n"), /payload JSON NOT NULL/);
  assert.match(mysql.guardrails.join(" "), /MySQL/);

  assert.equal(sqlite.dialect, "sqlite");
  assert.match(sqlite.statements.map((item) => item.sql).join("\n"), /INTEGER PRIMARY KEY AUTOINCREMENT/);

  assert.equal(fallback.dialect, "postgres");
});

test("A3 usage ledger turns A1/A2 evidence and hosted reports into read-only meters", () => {
  const ledger = buildA3UsageLedger({
    runFixture: {
      runs: [{
        run_id: "run-ledger",
        cases: [{
          case_id: "case-ledger",
          status: "failed",
          trace_events: [{ event_type: "tool_call" }],
          actual: { tool_calls: [{ name: "refund_order" }] }
        }]
      }]
    },
    gradeFixture: {
      grade_results: [{
        case_id: "case-ledger",
        passed: false,
        score: 0.2,
        judge_results: [{ judge_mode: "deterministic", passed: false }]
      }]
    }
  }, {
    reports: [{ report_id: "a3r_1" }],
    auditEvents: [{ event_type: "report_view" }, { event_type: "report_revoke" }],
    importReceipts: [{ schema_version: "a3.a1_run_result_ingest.v1" }]
  });

  assert.equal(ledger.schema_version, "a3.usage_ledger.v1");
  assert.equal(ledger.billing_mutations_enabled, false);
  assert.equal(meter(ledger, "runs"), 1);
  assert.equal(meter(ledger, "cases"), 1);
  assert.equal(meter(ledger, "judge_results"), 1);
  assert.equal(meter(ledger, "shareable_reports"), 1);
  assert.equal(meter(ledger, "report_views"), 1);
  assert.equal(meter(ledger, "api_imports"), 1);
});

test("A3 report center manifest links hosted report, usage ledger, and DB migration evidence", () => {
  const manifest = buildReportCenterManifest({
    report_id: "a3r_manifest",
    status: "shareable",
    source: "mock",
    share_url_path: "/reports/a3r_manifest",
    lifecycle: { revocable: true },
    view_audit: { view_count: 2 },
    redaction: { status: "passed" },
    sealed_evidence: { payload_hash: "abc123" },
    artifacts: [
      { id: "json_report", sha256: "jsonhash" },
      { id: "markdown_report", sha256: "mdhash" },
      { id: "hosted_report", sha256: "htmlhash" }
    ]
  }, {
    usageLedger: { schema_version: "a3.usage_ledger.v1", meters: [{ meter: "runs" }] },
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", migration_count: 6 }
  });

  assert.equal(manifest.schema_version, "a3.report_center_manifest.v1");
  assert.equal(manifest.release_packet.hosted_report_ready, true);
  assert.equal(manifest.release_packet.usage_meter_count, 1);
  assert.equal(manifest.release_packet.migration_count, 6);
  assert.ok(manifest.artifacts.some((item) => item.id === "usage_ledger"));
  assert.ok(manifest.artifacts.some((item) => item.id === "db_migration_plan"));
});

function meter(ledger, name) {
  return ledger.meters.find((item) => item.meter === name)?.quantity;
}
