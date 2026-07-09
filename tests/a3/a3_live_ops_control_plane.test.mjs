import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3BillingReadiness } from "../../services/report/a3_billing_readiness.mjs";
import { buildA3LiveOpsControlPlane } from "../../services/report/a3_live_ops_control_plane.mjs";
import { buildA3LiveWorkflowReadiness } from "../../services/report/a3_live_workflow_readiness.mjs";
import { buildReviewWorkflowIndex } from "../../services/report/a3_review_workflow.mjs";
import { buildSaasAdminConsole } from "../../services/report/a3_saas_admin.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 live ops control plane tracks the six requested SaaS workflow lanes", async () => {
  const checkPublish = await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json");
  const prCommentPublish = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json");
  const checkReadback = await loadJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
  const prCommentReadback = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json");
  const runFixture = {
    runs: [{
      run_id: "run-live-ops",
      cases: [{
        case_id: "case-live-ops",
        status: "failed",
        trace_events: [{ event_type: "agent_response" }],
        expected: { tool_calls: [{ name: "refund_order" }] },
        actual: { tool_calls: [] }
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-live-ops",
      passed: false,
      score: 0.44,
      primary_failure_class: "missing_required_tool",
      judge_results: [{ judge_mode: "deterministic", passed: false }]
    }]
  };
  const reviewWorkflow = buildReviewWorkflowIndex([
    { record_type: "approval", accepted: true },
    { record_type: "denial", accepted: true },
    { record_type: "waiver", accepted: true }
  ]);
  const usageLedger = buildA3UsageLedger({ runFixture, gradeFixture }, {
    reports: [{ report_id: "a3r_live_ops" }],
    auditEvents: [{ event_type: "report_share_link_viewed" }],
    releaseEvidenceReadbacks: [checkReadback, prCommentReadback]
  });
  const saasAdmin = buildSaasAdminConsole({ runFixture, gradeFixture });
  const billingReadiness = buildA3BillingReadiness({ usageLedger, adminConsole: saasAdmin });
  const reportCenter = {
    schema_version: "a3.report_center_index.v1",
    summary: {
      report_count: 2,
      shareable_count: 1,
      revoked_count: 1,
      expired_count: 1,
      total_view_count: 2
    }
  };
  const eventOutbox = {
    schema_version: "a3.event_outbox_dashboard.v1",
    event_count: 4
  };
  const releaseEvidence = {
    githubCheckPublishReceipt: checkPublish,
    githubPrCommentPublishReceipt: prCommentPublish,
    githubCheckReadback: checkReadback,
    githubPrCommentReadback: prCommentReadback,
    readback_records: [checkReadback, prCommentReadback]
  };
  const liveWorkflowReadiness = buildA3LiveWorkflowReadiness({
    releaseEvidence,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    eventOutbox
  });

  const controlPlane = buildA3LiveOpsControlPlane({
    releaseEvidence,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    eventOutbox,
    liveWorkflowReadiness
  });

  assert.equal(controlPlane.schema_version, "a3.live_ops_control_plane.v1");
  assert.equal(controlPlane.counts.lane_count, 6);
  assert.equal(controlPlane.counts.api_backed_count, 6);
  assert.equal(controlPlane.counts.audit_backed_count, 6);
  assert.equal(controlPlane.counts.local_external_mutation_count, 0);
  assert.deepEqual(controlPlane.lanes.map((item) => item.id), [
    "github_pr_check_live_publishing",
    "pr_comment_live_publishing",
    "reviewer_approve_deny_waiver_workflow",
    "dashboard_human_operation_records",
    "billing_admin_real_usage_billing_state",
    "report_share_link_revocable_expiring_audited"
  ]);
  assert.ok(controlPlane.lanes.every((item) => item.db_tables.length > 0));
  assert.ok(controlPlane.lanes.every((item) => item.audit_events.length > 0));
  assert.equal(controlPlane.human_operation_summary.approval_count, 1);
  assert.equal(controlPlane.billing_state_summary.billing_mutations_enabled, false);
  assert.equal(controlPlane.report_link_summary.revoked_count, 1);
  assert.equal(controlPlane.a1_a2_alignment.a3_mutates_a1_a2_semantics, false);
  assert.equal(controlPlane.safety.secret_values_included, false);
  assert.doesNotMatch(JSON.stringify(controlPlane), /Bearer|sk-|ghp_|github_pat_|@/);
});
