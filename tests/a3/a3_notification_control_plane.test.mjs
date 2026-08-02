import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3LiveOpsControlPlane } from "../../services/report/a3_live_ops_control_plane.mjs";
import { buildA3LiveWorkflowReadiness } from "../../services/report/a3_live_workflow_readiness.mjs";
import {
  buildA3NotificationControlPlane,
  findA3NotificationSecretLeaks
} from "../../services/report/a3_notification_control_plane.mjs";
import { buildReviewWorkflowIndex } from "../../services/report/a3_review_workflow.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";
import { buildA3BillingReadiness } from "../../services/report/a3_billing_readiness.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 notification control plane maps Slack Teams email and webhook lanes", async () => {
  const checkPublish = await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json");
  const prCommentPublish = await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json");
  const runFixture = {
    runs: [{
      run_id: "run-notify",
      status: "failed",
      cases: [{
        case_id: "case-notify",
        status: "failed",
        expected: { tool_calls: [{ name: "refund_order" }] },
        actual: { tool_calls: [] },
        trace_events: [{ event_type: "agent_response" }]
      }]
    }]
  };
  const gradeFixture = {
    grade_results: [{
      case_id: "case-notify",
      passed: false,
      score: 0.31,
      primary_failure_class: "missing_required_tool"
    }]
  };
  const reviewWorkflow = buildReviewWorkflowIndex([
    { record_type: "approval", accepted: true },
    { record_type: "denial", accepted: true }
  ]);
  const usageLedger = buildA3UsageLedger({ runFixture, gradeFixture }, {
    reports: [{ report_id: "a3r_notify" }],
    auditEvents: [{ event_type: "report.share_link_created" }]
  });
  const billingReadiness = buildA3BillingReadiness({ usageLedger });
  const reportCenter = {
    schema_version: "a3.report_center_index.v1",
    summary: {
      report_count: 1,
      shareable_count: 1,
      revoked_count: 0
    }
  };
  const eventOutbox = {
    schema_version: "a3.event_outbox_dashboard.v1",
    event_count: 3
  };
  const releaseEvidence = {
    schema_version: "a3.release_evidence_summary.v1",
    githubCheckPublishReceipt: checkPublish,
    githubPrCommentPublishReceipt: prCommentPublish,
    overall_status: "blocked"
  };
  const liveWorkflowReadiness = buildA3LiveWorkflowReadiness({
    releaseEvidence,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    eventOutbox
  });
  const liveOpsControlPlane = buildA3LiveOpsControlPlane({
    releaseEvidence,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    eventOutbox,
    liveWorkflowReadiness
  });

  const controlPlane = buildA3NotificationControlPlane({
    releaseEvidence,
    liveOpsControlPlane,
    reviewWorkflow,
    eventOutbox,
    reportCenter,
    usageLedger
  });

  assert.equal(controlPlane.schema_version, "a3.notification_control_plane.v1");
  assert.equal(controlPlane.summary.channel_count, 4);
  assert.equal(controlPlane.summary.api_backed_count, 4);
  assert.equal(controlPlane.summary.live_mutation_count, 0);
  assert.deepEqual(controlPlane.channels.map((item) => item.provider), ["slack", "teams", "email", "webhook"]);
  assert.ok(controlPlane.channels.every((item) => item.db_tables.includes("notification_deliveries")));
  assert.ok(controlPlane.channels.every((item) => item.audit_events.length >= 2));
  assert.ok(controlPlane.channels.every((item) => item.payload_fields.includes("primary_failure_class")));
  assert.equal(controlPlane.trigger_matrix.length, 4);
  assert.equal(controlPlane.growth_points.length >= 20, true);
  assert.equal(controlPlane.summary.strongest_money_path, "PR gate + incident replay + enterprise audit notifications");
  assert.equal(controlPlane.a1_a2_alignment.a3_mutates_a1_a2_semantics, false);
  assert.equal(controlPlane.safety.raw_webhook_urls_included, false);
  assert.equal(controlPlane.safety.real_slack_mutation_performed_locally, false);
  assert.doesNotMatch(JSON.stringify(controlPlane), /Bearer|xoxb-|sk-|ghp_|github_pat_|@|https:\/\/hooks\.slack/);
});

test("A3 notification control plane does not echo provider secrets from inputs", () => {
  const slackWebhook = ["https://hooks.slack.com/services", "T00000000", "B00000000", "secret-token"].join("/");
  const teamsWebhook = ["https://outlook.office.com", "webhook", "tenant-secret"].join("/");
  const ownerAddress = ["release.owner", "example.com"].join("@");
  const customerEndpoint = [
    "https://customer.example.test/webhook?token=",
    ["github", "pat", "secretSECRET000000"].join("_")
  ].join("");
  const controlPlane = buildA3NotificationControlPlane({
    slack: {
      webhook_url: slackWebhook,
      bot_token: ["xoxb", "123456789012", "abcdefSECRET"].join("-")
    },
    teams: {
      incoming_webhook_url: teamsWebhook,
      authorization_header: ["Authorization:", "Bearer", "teams-secret-token-1234567890"].join(" ")
    },
    email: {
      recipients: [ownerAddress],
      provider_key: ["sk", "proj", "emailSECRET000000000000"].join("-")
    },
    webhook: {
      endpoint_url: customerEndpoint,
      signing_secret: ["whsec", "customerSECRET000000"].join("_")
    }
  });
  const serialized = JSON.stringify(controlPlane);

  assert.deepEqual(findA3NotificationSecretLeaks(controlPlane), []);
  assert.equal(controlPlane.summary.channel_count, 4);
  assert.equal(controlPlane.safety.secret_values_included, false);
  assert.equal(controlPlane.safety.provider_credentials_echoed, false);
  assert.equal(controlPlane.safety.raw_webhook_urls_included, false);
  assert.doesNotMatch(serialized, /hooks\.slack\.com|outlook\.office\.com|customer\.example/i);
  assert.doesNotMatch(serialized, /release\.owner|@example/i);
  assert.doesNotMatch(serialized, /Bearer|xoxb-|whsec_|sk-proj-|github_pat_|ghp_/);
});
