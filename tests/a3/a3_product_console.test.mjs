import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3ProductConsole } from "../../services/report/a3_product_console.mjs";
import { buildReportCenterIndex } from "../../services/report/a3_report_center.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 product console turns A1/A2 evidence into onboarding, project, and audit workflow state", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const auditEvents = [
    { event_type: "report_share_link_viewed", report_id: "a3r_demo", access_result: "allowed", viewed_at: "2026-07-07T00:00:00.000Z" }
  ];
  const reports = [{
    report_id: "a3r_demo",
    title: "Demo report",
    source: "mock",
    status: "shareable",
    share_url_path: "/r/[REDACTED_TOKEN]",
    lifecycle: { view_audit_enabled: true },
    redaction: { status: "passed" },
    sealed_evidence: { payload_hash: "hash", secret_free: true },
    view_audit: { view_count: 1 }
  }];
  const usageLedger = buildA3UsageLedger({ runFixture: runs, gradeFixture: grades }, { reports, auditEvents });
  const reportCenter = buildReportCenterIndex(reports, {
    source: "mock",
    usageLedger,
    migrationPlan: buildA3SqlMigrationPlan()
  });

  const product = buildA3ProductConsole({
    source: "mock",
    runFixture: runs,
    gradeFixture: grades
  }, {
    usageLedger,
    reportCenter,
    auditEvents,
    importReceipts: [{ schema_version: "a3.a1_run_result_ingest.v1", source: "mock", idempotency: { status: "recorded" } }],
    reviewWorkflow: {
      schema_version: "a3.review_workflow_index.v1",
      record_count: 1
    },
    notificationControlPlane: {
      schema_version: "a3.notification_control_plane.v1",
      summary: {
        channel_count: 4,
        contract_ready_count: 4
      }
    }
  });

  assert.equal(product.schema_version, "a3.product_console.v1");
  assert.equal(product.onboarding.total_steps, 10);
  assert.ok(product.onboarding.completed_steps >= 6);
  assert.ok(product.project_console.summary.case_count > 0);
  assert.ok(product.project_console.primary_actions.some((item) => item.action === "create_report" && item.enabled));
  assert.equal(product.audit_log.redacted_payload_only, true);
  assert.ok(product.audit_log.event_count >= 3);
  assert.equal(product.commercial_readiness.readiness_score, 100);
  assert.equal(product.project_console.operations_summary.review_record_count, 1);
  assert.equal(product.project_console.operations_summary.notification_channel_count, 4);

  const serialized = JSON.stringify(product);
  assert.doesNotMatch(serialized, /Bearer [A-Za-z0-9]/);
  assert.doesNotMatch(serialized, /Cookie:/);
  assert.doesNotMatch(serialized, /RELEASEFOUNDRY_API_KEY=/);
});

test("A3 product console keeps empty projects honest", () => {
  const product = buildA3ProductConsole({ runFixture: {}, gradeFixture: {} }, {});

  assert.equal(product.onboarding.status, "setup_required");
  assert.equal(product.project_console.status, "empty");
  assert.equal(product.audit_log.status, "empty");
  assert.equal(product.commercial_readiness.status, "needs_more_real_evidence");
  assert.ok(product.commercial_readiness.checks.some((item) => item.status === "missing"));
});
