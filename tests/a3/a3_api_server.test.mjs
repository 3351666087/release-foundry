import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

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
    assert.equal(dashboard.product_console.schema_version, "a3.product_console.v1");
    assert.equal(dashboard.storage.db_migrations.schema_version, "a3.sql_migration_plan.v1");
    assert.equal(dashboard.usage_ledger.schema_version, "a3.usage_ledger.v1");
    assert.equal(dashboard.release_evidence_summary.schema_version, "a3.release_evidence_summary.v1");
    assert.equal(dashboard.release_evidence_summary.available, true);

    const releaseEvidence = await getJson(`${url}${dashboard.release_evidence_api.path}`);
    assert.equal(releaseEvidence.schema_version, "a3.release_evidence_api_response.v1");
    assert.equal(releaseEvidence.release_evidence_summary.available, true);
    assert.equal(releaseEvidence.release_evidence_health.schema_version, "a3.release_evidence_health.v1");
    assert.equal(releaseEvidence.next_action.action, "publish_github_check");
    assert.equal(releaseEvidence.safety.raw_request_body_exposed, false);

    const releaseEvidenceV2 = await getJson(`${url}${dashboard.release_evidence_api.path}&version=2`);
    assert.equal(releaseEvidenceV2.schema_version, "a3.release_evidence_api_response.v2");
    assert.equal(releaseEvidenceV2.release_evidence_summary.schema_version, "a3.release_evidence_summary.v2");
    assert.equal(releaseEvidenceV2.release_evidence_summary.a1_evidence.contracts.includes("Trace"), true);
    assert.equal(releaseEvidenceV2.release_evidence_summary.a2_evidence.contracts.includes("Judge"), true);
    assert.equal(releaseEvidenceV2.release_evidence_summary.required_check_proof.enforced, false);
    assert.equal(releaseEvidenceV2.release_evidence_summary.safety.raw_secret_values_allowed, false);

    const releaseEvidenceHealth = await getJson(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/evidence-health?source=mock`);
    assert.equal(releaseEvidenceHealth.schema_version, "a3.release_evidence_health_api_response.v1");
    assert.equal(releaseEvidenceHealth.summary_id, releaseEvidenceV2.summary_id);
    assert.equal(releaseEvidenceHealth.release_evidence_health.schema_version, "a3.release_evidence_health.v1");

    const releaseEvidenceDiff = await getJson(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/evidence-diff?source=mock`);
    assert.equal(releaseEvidenceDiff.schema_version, "a3.release_evidence_diff_api_response.v1");
    assert.equal(releaseEvidenceDiff.diff.schema_version, "a3.release_evidence_diff.v1");
    assert.ok(releaseEvidenceDiff.diff.changed_fields.some((item) => item.field === "schema_version"));
    assert.equal(releaseEvidenceDiff.safety.raw_secret_values_allowed, false);

    const checkReadback = await loadJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
    const readbackCaptureBody = {
      readback: {
        ...checkReadback,
        expected: {
          ...checkReadback.expected,
          authorization: "Bearer should-not-leak"
        }
      },
      actor: ["release-owner", "example.com"].join("@")
    };
    const readbackCapture = await fetch(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/readbacks?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "idem-readback-1" },
      body: JSON.stringify(readbackCaptureBody)
    });
    assert.equal(readbackCapture.status, 202);
    const readbackReceipt = await readbackCapture.json();
    assert.equal(readbackReceipt.schema_version, "a3.release_evidence_readback_capture_receipt.v1");
    assert.equal(readbackReceipt.readback_status, "readback_confirmed");
    assert.equal(readbackReceipt.idempotency.status, "recorded");
    assert.equal(readbackReceipt.secret_values_included, false);
    assert.doesNotMatch(JSON.stringify(readbackReceipt), /should-not-leak|release-owner@example.com|Bearer/);

    const duplicateReadback = await fetch(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/readbacks?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "idem-readback-1" },
      body: JSON.stringify(readbackCaptureBody)
    });
    assert.equal(duplicateReadback.status, 202);
    const duplicateReadbackReceipt = await duplicateReadback.json();
    assert.equal(duplicateReadbackReceipt.idempotency.duplicate, true);

    const readbacks = await getJson(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/readbacks?source=mock`);
    assert.equal(readbacks.schema_version, "a3.release_evidence_readback_list.v1");
    assert.equal(readbacks.readback_count, 1);
    assert.equal(readbacks.status_counts.readback_confirmed, 1);
    assert.equal(readbacks.readbacks[0].resource_kind, "github_check");
    assert.doesNotMatch(JSON.stringify(readbacks), /should-not-leak|release-owner@example.com|Bearer/);

    const releaseEvidenceAfterCapture = await getJson(`${url}${dashboard.release_evidence_api.path}&version=2`);
    assert.equal(releaseEvidenceAfterCapture.release_evidence_summary.github_check_readback.readback_status, "readback_confirmed");
    assert.equal(releaseEvidenceAfterCapture.release_evidence_summary.github_check_readback.readback_confirmed, true);
    assert.equal(releaseEvidenceAfterCapture.release_evidence_summary.github_check_readback.payload_hash, readbackReceipt.payload_hash);

    const usageAfterReadback = await getJson(`${url}/api/a3/usage/ledger?source=mock`);
    assert.equal(usageAfterReadback.meters.some((item) => item.meter === "release_evidence_readbacks" && item.quantity === 1), true);

    const crossTenantReleaseEvidence = await fetch(`${url}${dashboard.release_evidence_api.path}&organization_id=org-other`);
    assert.equal(crossTenantReleaseEvidence.status, 404);
    const crossTenantPayload = await crossTenantReleaseEvidence.json();
    assert.equal(crossTenantPayload.error, "not_found");
    assert.equal(crossTenantPayload.kind, "release_evidence");
    assert.doesNotMatch(JSON.stringify(crossTenantPayload), /Release Evidence|github_check_publish|audit_bundle_verification/);
    const crossTenantDiff = await fetch(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/evidence-diff?source=mock&organization_id=org-other`);
    assert.equal(crossTenantDiff.status, 404);
    const crossTenantReadback = await fetch(`${url}/api/a3/releases/${encodeURIComponent(releaseEvidence.release_id)}/readbacks?source=mock&organization_id=org-other`);
    assert.equal(crossTenantReadback.status, 404);

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

    const ownerEmail = ["owner", "example.com"].join("@");
    const teammateEmail = ["teammate", "example.com"].join("@");
    const actionSubmitResponse = await fetch(`${url}/api/a3/admin/actions/submit?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "invite_teammate",
        actor: ownerEmail,
        target: {
          email: teammateEmail,
          role: "reviewer"
        }
      })
    });
    assert.equal(actionSubmitResponse.status, 202);
    const actionReceipt = await actionSubmitResponse.json();
    assert.equal(actionReceipt.schema_version, "a3.saas_admin_action_receipt.v1");
    assert.equal(actionReceipt.status, "recorded_plan_only");
    assert.equal(actionReceipt.real_cloud_mutation_performed, false);
    assert.equal(actionReceipt.secret_values_included, false);

    const actionRequests = await getJson(`${url}/api/a3/admin/actions?source=mock`);
    assert.equal(actionRequests.schema_version, "a3.saas_admin_action_request_list.v1");
    assert.equal(actionRequests.summary.request_count, 1);
    assert.equal(actionRequests.requests[0].action, "invite_teammate");
    assert.doesNotMatch(JSON.stringify(actionRequests), new RegExp(`${ownerEmail}|${teammateEmail}`));

    const readiness = await getJson(`${url}/api/a3/enterprise/readiness?source=mock`);
    assert.equal(readiness.schema_version, "a3.enterprise_readiness.v1");
    assert.equal(readiness.a1_a2_compatibility_notes.dashboard_case_count, 32);

    const waiver = await loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
    const approval = await loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");
    const waiverResponse = await fetch(`${url}/api/a3/review/waivers?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        waiver,
        generated_at: "2026-07-07T12:00:00.000Z"
      })
    });
    assert.equal(waiverResponse.status, 202);
    const waiverReceipt = await waiverResponse.json();
    assert.equal(waiverReceipt.status, "valid_exceptional_waiver");
    assert.equal(waiverReceipt.accepted, true);

    const approvalResponse = await fetch(`${url}/api/a3/review/approvals?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        approval,
        waiver,
        generated_at: "2026-07-07T12:00:00.000Z"
      })
    });
    assert.equal(approvalResponse.status, 202);
    const approvalReceipt = await approvalResponse.json();
    assert.equal(approvalReceipt.status, "valid_exception_approval");
    assert.equal(approvalReceipt.accepted, true);

    const reviewWorkflow = await getJson(`${url}/api/a3/review/workflow?source=mock`);
    assert.equal(reviewWorkflow.schema_version, "a3.review_workflow_index.v1");
    assert.equal(reviewWorkflow.record_count, 2);
    assert.equal(reviewWorkflow.durable_storage_ready, true);

    const productConsole = await getJson(`${url}/api/a3/product/console?source=mock`);
    assert.equal(productConsole.schema_version, "a3.product_console.v1");
    assert.equal(productConsole.project_console.summary.case_count, 32);
    assert.equal(productConsole.audit_log.redacted_payload_only, true);
    assert.ok(productConsole.onboarding.steps.some((item) => item.id === "submit_first_run"));

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

    const otherTenantShareResponse = await fetch(`${url}/api/a3/reports/share?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        title: "A3 other tenant report",
        organization_id: "org-other",
        project_id: "project-other"
      })
    });
    assert.equal(otherTenantShareResponse.status, 201);
    const otherTenantReport = await otherTenantShareResponse.json();

    const savedReport = await getJson(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}`);
    assert.equal(savedReport.report_id, report.report_id);
    assert.equal(savedReport.share_url_path, "/r/[REDACTED_TOKEN]");
    assert.equal(savedReport.share_link.token_hash, undefined);
    assert.match(savedReport.share_link.token_hash_prefix, /^[a-f0-9]{12}$/);

    const crossTenantReport = await fetch(`${url}/api/a3/reports/${encodeURIComponent(otherTenantReport.report_id)}?source=mock`);
    assert.equal(crossTenantReport.status, 404);
    const crossTenantManifest = await fetch(`${url}/api/a3/reports/${encodeURIComponent(otherTenantReport.report_id)}/manifest?source=mock`);
    assert.equal(crossTenantManifest.status, 404);
    const crossTenantView = await fetch(`${url}/api/a3/reports/${encodeURIComponent(otherTenantReport.report_id)}/view?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ viewer: "wrong-tenant" })
    });
    assert.equal(crossTenantView.status, 404);
    const crossTenantRevoke = await fetch(`${url}/api/a3/reports/${encodeURIComponent(otherTenantReport.report_id)}/revoke?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: "wrong-tenant" })
    });
    assert.equal(crossTenantRevoke.status, 404);
    const scopedOtherTenantReport = await getJson(`${url}/api/a3/reports/${encodeURIComponent(otherTenantReport.report_id)}?source=mock&organization_id=org-other&project_id=project-other`);
    assert.equal(scopedOtherTenantReport.report_id, otherTenantReport.report_id);

    const manifest = await getJson(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}/manifest?source=mock`);
    assert.equal(manifest.schema_version, "a3.report_center_manifest.v1");
    assert.equal(manifest.release_packet.hosted_report_ready, true);
    assert.equal(manifest.release_packet.release_evidence_summary_ready, true);
    assert.ok(manifest.artifacts.some((item) => item.id === "db_migration_plan"));
    assert.ok(manifest.artifacts.some((item) => item.id === "release_evidence_summary"));

    const reportCenter = await getJson(`${url}/api/a3/reports/center?source=mock`);
    assert.equal(reportCenter.schema_version, "a3.report_center_index.v1");
    assert.equal(reportCenter.summary.report_count, 1);
    assert.equal(reportCenter.summary.shareable_count, 1);
    assert.equal(reportCenter.reports[0].report_id, report.report_id);
    assert.equal(reportCenter.control_plane.sql_contract_ready, true);
    assert.equal(reportCenter.control_plane.billing_mutations_enabled, false);
    assert.equal(reportCenter.summary.release_evidence_ready_count, 1);
    assert.equal(reportCenter.artifact_registry.schema_version, "a3.artifact_registry.v1");
    assert.ok(reportCenter.artifact_registry.entries.some((item) => item.report_id === report.report_id));

    const reportList = await getJson(`${url}/api/a3/reports?source=mock`);
    assert.deepEqual(reportList.reports.map((item) => item.report_id), [report.report_id]);

    const artifactRegistry = await getJson(`${url}/api/a3/artifacts/registry?source=mock`);
    assert.equal(artifactRegistry.schema_version, "a3.artifact_registry.v1");
    assert.equal(artifactRegistry.summary.report_artifact_count, 5);
    assert.ok(artifactRegistry.entries.some((item) => item.artifact_type === "release_evidence_summary"));
    assert.ok(artifactRegistry.packet_presets.some((item) => item.preset_id === "pr_review_packet"));
    assert.equal(artifactRegistry.safety.raw_share_tokens_stored, false);

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
    assert.match(internalHtml, /Release Evidence/);
    assert.match(internalHtml, /Sealed Evidence/);

    const hostedReport = await fetch(`${url}${report.share_url_path}`);
    assert.equal(hostedReport.status, 200);
    assert.match(hostedReport.headers.get("content-type"), /text\/html/);
    const hostedHtml = await hostedReport.text();
    assert.match(hostedHtml, /A3 API smoke report/);
    assert.match(hostedHtml, /Release Evidence/);
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

test("A3 API server redacts unexpected internal error messages", async () => {
  const store = {
    storage_mode: "memory",
    async getDashboardSnapshot() {
      throw new Error(`Authorization: Bearer ${"x".repeat(24)} ASHR_API_KEY=secret_live_value owner@example.com`);
    }
  };
  const { server, url } = await startA3ApiServer({ store });
  try {
    const response = await fetch(`${url}/api/a3/dashboard`);
    assert.equal(response.status, 500);
    const payload = await response.json();
    assert.equal(payload.error, "internal_error");
    assert.match(payload.message, /Bearer \[REDACTED\]/);
    assert.match(payload.message, /ASHR_API_KEY=\[REDACTED\]/);
    assert.doesNotMatch(JSON.stringify(payload), /secret_live_value|owner@example.com|x{24}/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
