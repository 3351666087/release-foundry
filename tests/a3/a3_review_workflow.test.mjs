import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildReviewWorkflowIndex,
  buildReviewWorkflowRecord,
  validateDenialRecord
} from "../../services/report/a3_review_workflow.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 review workflow records reuse waiver and approval validation semantics", async () => {
  const runFixture = await loadJson("../../fixtures/a3/mock_run_results.json");
  const gradeFixture = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const waiver = await loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
  const approval = await loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");
  const snapshot = {
    source: "mock",
    organizationId: "org-local",
    projectId: "project-local",
    runFixture,
    gradeFixture,
    coverage
  };

  const waiverRecord = buildReviewWorkflowRecord("waiver", waiver, snapshot, {
    generatedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(waiverRecord.schema_version, "a3.review_workflow_record.v1");
  assert.equal(waiverRecord.status, "valid_exceptional_waiver");
  assert.equal(waiverRecord.accepted, true);
  assert.equal(waiverRecord.signature.raw_signature_stored, false);
  assert.match(waiverRecord.payload_hash, /^[a-f0-9]{64}$/);
  assert.match(waiverRecord.review_hash, /^[a-f0-9]{64}$/);

  const approvalRecord = buildReviewWorkflowRecord("approval", approval, snapshot, {
    waiver,
    generatedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(approvalRecord.status, "valid_exception_approval");
  assert.equal(approvalRecord.accepted, true);
  assert.equal(approvalRecord.subject.decision, "approve_exception");
  assert.equal(approvalRecord.safety.real_cloud_mutation_performed, false);

  const denial = buildDenialFixture();
  const denialReview = validateDenialRecord(denial, {}, {}, { lastRunId: "run_a3_generated_from_a2_g3" }, {
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha"
  });
  assert.equal(denialReview.schema_version, "a3.denial_review.v1");
  assert.equal(denialReview.status, "valid_denial");
  assert.equal(denialReview.accepted, true);

  const denialRecord = buildReviewWorkflowRecord("denial", denial, snapshot, {
    generatedAt: "2026-07-07T12:00:00.000Z",
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha"
  });
  assert.equal(denialRecord.status, "valid_denial");
  assert.equal(denialRecord.accepted, true);
  assert.equal(denialRecord.subject.decision, "deny_release");
  assert.equal(denialRecord.safety.real_cloud_mutation_performed, false);

  const index = buildReviewWorkflowIndex([waiverRecord, approvalRecord, denialRecord]);
  assert.equal(index.schema_version, "a3.review_workflow_index.v1");
  assert.equal(index.record_count, 3);
  assert.equal(index.waiver_count, 1);
  assert.equal(index.approval_count, 1);
  assert.equal(index.denial_count, 1);
  assert.equal(index.accepted_count, 3);
  assert.equal(index.latest_human_action, "denial");
});

function buildDenialFixture() {
  return {
    schema_version: "a3.denial.v1",
    denial_id: "denial-local-blocked-001",
    decision: "deny_release",
    reason: "Release remains blocked until failed A1 traces and A2 judge evidence are remediated.",
    release_version: "local-mock-commercial-gate",
    environment: "staging",
    run_id: "run_a3_generated_from_a2_g3",
    head_sha: "local-demo-head-sha",
    reviewer: {
      role: "Safety reviewer",
      name: "Safety reviewer",
      identity_source: "unit-test",
      reviewed_at: "2026-07-07T12:50:00.000Z"
    },
    reviewed_artifacts: [
      {
        id: "a3_gate_cli_report",
        path: "fixtures/a3/p3/a3_gate_cli_report.redacted.md",
        sha256: "3333333333333333333333333333333333333333333333333333333333333333"
      }
    ]
  };
}
