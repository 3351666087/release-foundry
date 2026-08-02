import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3BillingReadiness } from "../../services/report/a3_billing_readiness.mjs";
import { buildA3LiveWorkflowReadiness } from "../../services/report/a3_live_workflow_readiness.mjs";
import { buildReviewWorkflowIndex } from "../../services/report/a3_review_workflow.mjs";
import { buildSaasAdminConsole } from "../../services/report/a3_saas_admin.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 live workflow readiness summarizes the six next SaaS growth items", async () => {
  const checkPublish = await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json");
  const prCommentPublish = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json");
  const runFixture = {
    runs: [{
      run_id: "run-live",
      cases: [{
        case_id: "case-live",
        status: "failed",
        trace_events: [{ event_type: "agent_response" }],
        expected: { tool_calls: [{ name: "refund_order" }] },
        actual: { tool_calls: [] }
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-live",
      passed: false,
      score: 0.42,
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
    reports: [{ report_id: "a3r_live" }],
    auditEvents: [{ event_type: "report_share_link_viewed" }],
    releaseEvidenceReadbacks: [{ readback_id: "rb-live" }]
  });
  const saasAdmin = buildSaasAdminConsole({ runFixture, gradeFixture });
  const billingReadiness = buildA3BillingReadiness({ usageLedger, adminConsole: saasAdmin });
  const readiness = buildA3LiveWorkflowReadiness({
    releaseEvidence: {
      githubCheckPublishReceipt: checkPublish,
      githubPrCommentPublishReceipt: prCommentPublish
    },
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter: {
      schema_version: "a3.report_center_index.v1",
      summary: {
        shareable_count: 1,
        revoked_count: 1,
        expired_count: 1,
        total_view_count: 2
      }
    },
    saasAdmin,
    eventOutbox: {
      event_count: 3
    }
  });

  assert.equal(readiness.schema_version, "a3.live_workflow_readiness.v1");
  assert.equal(readiness.capability_count, 6);
  assert.equal(readiness.ready_capability_count, 6);
  assert.equal(readiness.needs_backend_or_credentials_count >= 2, true);
  assert.equal(readiness.human_action_count, 3);
  assert.deepEqual(readiness.capabilities.map((item) => item.id), [
    "github_pr_check_live_publishing",
    "pr_comment_live_publishing",
    "reviewer_approve_deny_waiver_workflow",
    "dashboard_human_operation_records",
    "billing_admin_real_usage_billing_state",
    "report_share_link_revocable_expiring_audited"
  ]);
  assert.match(readiness.a1_a2_boundary, /does not modify A1/);
  assert.equal(readiness.safety.secret_values_included, false);
  assert.equal(readiness.safety.billing_mutations_performed, false);
  assert.doesNotMatch(JSON.stringify(readiness), /Bearer|github_pat_|ghp_|sk-|@/);
});
