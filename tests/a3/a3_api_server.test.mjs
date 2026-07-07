import assert from "node:assert/strict";
import { test } from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

test("A3 API server exposes dashboard, run, case, and shareable report routes", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store });
  try {
    const health = await getJson(`${url}/api/a3/health`);
    assert.equal(health.ok, true);
    assert.equal(health.db_ready, true);

    const dashboard = await getJson(`${url}/api/a3/dashboard?source=mock`);
    assert.equal(dashboard.schema_version, "a3.api_dashboard_payload.v1");
    assert.equal(dashboard.summary.totalCases, 32);
    assert.equal(dashboard.storage.db_contract.mysql_compatible, true);
    assert.equal(dashboard.saas_admin_console.schema_version, "a3.saas_admin_console.v1");
    assert.equal(dashboard.enterprise_readiness.schema_version, "a3.enterprise_readiness.v1");
    assert.equal(dashboard.storage.db_migrations.schema_version, "a3.sql_migration_plan.v1");
    assert.equal(dashboard.usage_ledger.schema_version, "a3.usage_ledger.v1");

    const migrations = await getJson(`${url}/api/a3/db-migrations`);
    assert.equal(migrations.schema_version, "a3.sql_migration_plan.v1");
    assert.ok(migrations.statements.some((item) => item.tables.includes("idempotency_keys")));

    const mysqlMigrations = await getJson(`${url}/api/a3/db-migrations?dialect=mysql`);
    assert.equal(mysqlMigrations.dialect, "mysql");
    assert.match(mysqlMigrations.statements.map((item) => item.sql).join("\n"), /BIGINT AUTO_INCREMENT PRIMARY KEY/);

    const usageLedger = await getJson(`${url}/api/a3/usage/ledger?source=mock`);
    assert.equal(usageLedger.schema_version, "a3.usage_ledger.v1");
    assert.equal(usageLedger.billing_mutations_enabled, false);

    const admin = await getJson(`${url}/api/a3/admin/console?source=mock`);
    assert.equal(admin.login.user_identity, "[REDACTED]");
    assert.equal(admin.login.session.cookie_storage, "not_read_or_saved");
    assert.equal(admin.rbac.status, "contract_ready");
    assert.equal(admin.api_keys.status, "metadata_only");
    assert.equal(admin.usage.plan_snapshot.quota_mutations_enabled, false);
    assert.equal(admin.trust.trust_center.public_publish_enabled, false);
    assert.equal(admin.cloud_management.real_mutations_enabled, false);
    assert.ok(admin.cloud_management.resources.some((item) => item.type === "report_center"));

    const actionResponse = await fetch(`${url}/api/a3/admin/actions/plan?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "invite_teammate" })
    });
    assert.equal(actionResponse.ok, true);
    const actionPlan = await actionResponse.json();
    assert.equal(actionPlan.mode, "plan_only");
    assert.equal(actionPlan.writes_real_ashr_cloud, false);

    const readiness = await getJson(`${url}/api/a3/enterprise/readiness?source=mock`);
    assert.equal(readiness.schema_version, "a3.enterprise_readiness.v1");
    assert.equal(readiness.a1_a2_compatibility_notes.dashboard_case_count, 32);

    const ingestRunResponse = await fetch(`${url}/api/a3/import/a1-run-result`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "idem-api-run-1" },
      body: JSON.stringify({
        source: "api-ingest",
        run_result: {
          runs: [{
            run_id: "run-ingested-api",
            dataset_id: "dataset-ingested-api",
            runner_id: "a1-api-runner",
            status: "completed",
            cases: [{
              case_id: "case-ingested-api",
              scenario_id: "scenario-ingested-api",
              status: "failed",
              expected: { final_response: "Deny refund." },
              actual: { final_response: "Refund approved." },
              trace_events: [{ event_type: "agent_response" }]
            }]
          }]
        }
      })
    });
    assert.equal(ingestRunResponse.status, 201);
    const ingestRun = await ingestRunResponse.json();
    assert.equal(ingestRun.schema_version, "a3.a1_run_result_ingest.v1");
    assert.equal(ingestRun.imported_run_count, 1);
    assert.equal(ingestRun.idempotency.status, "recorded");

    const duplicateRunResponse = await fetch(`${url}/api/a3/import/a1-run-result`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "idem-api-run-1" },
      body: JSON.stringify({
        source: "api-ingest",
        run_result: {
          runs: [{
            run_id: "run-ingested-api",
            dataset_id: "dataset-ingested-api",
            runner_id: "a1-api-runner",
            status: "completed",
            cases: [{
              case_id: "case-ingested-api",
              scenario_id: "scenario-ingested-api",
              status: "failed",
              expected: { final_response: "Deny refund." },
              actual: { final_response: "Refund approved." },
              trace_events: [{ event_type: "agent_response" }]
            }]
          }]
        }
      })
    });
    assert.equal(duplicateRunResponse.status, 201);
    const duplicateRun = await duplicateRunResponse.json();
    assert.equal(duplicateRun.idempotency.status, "duplicate_replay");

    const conflictRunResponse = await fetch(`${url}/api/a3/import/a1-run-result`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "idem-api-run-1" },
      body: JSON.stringify({
        source: "api-ingest",
        run_result: {
          runs: [{
            run_id: "run-conflict",
            cases: [{ case_id: "case-conflict", status: "passed" }]
          }]
        }
      })
    });
    assert.equal(conflictRunResponse.status, 409);
    const conflictRun = await conflictRunResponse.json();
    assert.equal(conflictRun.schema_version, "a3.api_validation_error.v1");
    assert.equal(conflictRun.error, "idempotency_conflict");

    const ingestGradeResponse = await fetch(`${url}/api/a3/import/a2-grade-result`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source: "api-ingest",
        grade_result: {
          case_id: "case-ingested-api",
          scenario_id: "scenario-ingested-api",
          passed: false,
          score: 0.31,
          primary_failure_class: "wrong_intent",
          judge_results: [{ judge_mode: "deterministic", passed: false }]
        }
      })
    });
    assert.equal(ingestGradeResponse.status, 201);
    const ingestGrade = await ingestGradeResponse.json();
    assert.equal(ingestGrade.imported_grade_count, 1);
    assert.equal(ingestGrade.a1_a2_join_ready, true);

    const invalidGradeResponse = await fetch(`${url}/api/a3/import/a2-grade-result`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "api-ingest", grade_result: { score: 0.1 } })
    });
    assert.equal(invalidGradeResponse.status, 400);
    const invalidGrade = await invalidGradeResponse.json();
    assert.equal(invalidGrade.error, "validation_error");
    assert.equal(invalidGrade.quota_or_cost, "local_validation_only");

    const ingestedDashboard = await getJson(`${url}/api/a3/dashboard?source=api-ingest`);
    assert.equal(ingestedDashboard.summary.failed, 1);
    assert.equal(ingestedDashboard.cases[0].primary_failure_class, "wrong_intent");
    assert.equal(ingestedDashboard.enterprise_readiness.a1_a2_compatibility_notes.a2.compatible, true);

    const runs = await getJson(`${url}/api/a3/runs?source=mock`);
    assert.equal(runs.schema_version, "a3.api_run_list.v1");
    assert.equal(runs.runs.length, 1);

    const run = await getJson(`${url}/api/a3/runs/${encodeURIComponent(runs.runs[0].run_id)}?source=mock`);
    assert.equal(run.schema_version, "a3.api_run_detail.v1");
    assert.equal(run.summary.total_cases, 32);

    const firstCaseId = dashboard.cases[0].case_id;
    const detail = await getJson(`${url}/api/a3/cases/${encodeURIComponent(firstCaseId)}?source=mock`);
    assert.equal(detail.schema_version, "a3.api_case_detail.v1");
    assert.equal(detail.case.case_id, firstCaseId);

    const shareResponse = await fetch(`${url}/api/a3/reports/share?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "A3 API smoke report" })
    });
    assert.equal(shareResponse.status, 201);
    const report = await shareResponse.json();
    assert.equal(report.schema_version, "a3.shareable_report.v1");
    assert.equal(report.status, "shareable");
    assert.equal(report.lifecycle.revocable, true);
    assert.ok(report.expires_at);
    assert.match(report.share_url_path, /^\/r\/a3s_/);
    assert.match(report.internal_url_path, /^\/reports\/a3r_/);

    const savedReport = await getJson(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}`);
    assert.equal(savedReport.report_id, report.report_id);
    assert.equal(savedReport.share_url_path, "/r/[REDACTED_TOKEN]");
    assert.equal(savedReport.share_link.token_hash, undefined);
    assert.match(savedReport.share_link.token_hash_prefix, /^[a-f0-9]{12}$/);

    const manifest = await getJson(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}/manifest?source=mock`);
    assert.equal(manifest.schema_version, "a3.report_center_manifest.v1");
    assert.equal(manifest.release_packet.hosted_report_ready, true);
    assert.ok(manifest.artifacts.some((item) => item.id === "db_migration_plan"));

    const reportCenter = await getJson(`${url}/api/a3/reports/center?source=mock`);
    assert.equal(reportCenter.schema_version, "a3.report_center_index.v1");
    assert.equal(reportCenter.summary.report_count, 1);
    assert.equal(reportCenter.summary.shareable_count, 1);
    assert.equal(reportCenter.reports[0].report_id, report.report_id);
    assert.equal(reportCenter.control_plane.sql_contract_ready, true);
    assert.equal(reportCenter.control_plane.billing_mutations_enabled, false);

    const viewResponse = await fetch(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}/view`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ viewer: "test-viewer" })
    });
    assert.equal(viewResponse.status, 200);
    const viewReceipt = await viewResponse.json();
    assert.equal(viewReceipt.schema_version, "a3.report_view_receipt.v1");
    assert.equal(viewReceipt.view_audit.view_count, 1);

    const internalReport = await fetch(`${url}${report.internal_url_path}`);
    assert.equal(internalReport.status, 200);
    assert.match(internalReport.headers.get("content-type"), /text\/html/);
    const internalHtml = await internalReport.text();
    assert.match(internalHtml, /A3 API smoke report/);
    assert.match(internalHtml, /Sealed Evidence/);

    const hostedReport = await fetch(`${url}${report.share_url_path}`);
    assert.equal(hostedReport.status, 200);
    assert.match(hostedReport.headers.get("content-type"), /text\/html/);
    const hostedHtml = await hostedReport.text();
    assert.match(hostedHtml, /A3 API smoke report/);
    assert.match(hostedHtml, /Sealed Evidence/);

    const revokeResponse = await fetch(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}/revoke`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: "unit-test" })
    });
    assert.equal(revokeResponse.status, 200);
    const revokeReceipt = await revokeResponse.json();
    assert.equal(revokeReceipt.status, "revoked");

    const revokedHostedReport = await fetch(`${url}${report.share_url_path}`);
    assert.equal(revokedHostedReport.status, 410);
    const revokedHostedHtml = await revokedHostedReport.text();
    assert.match(revokedHostedHtml, /A3 report is not available/);
    assert.doesNotMatch(revokedHostedHtml, /Case Evidence/);

    const missingShareToken = await fetch(`${url}/r/missing-share-token`);
    assert.equal(missingShareToken.status, 404);

    const missing = await fetch(`${url}/api/a3/cases/missing-case?source=mock`);
    assert.equal(missing.status, 404);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
