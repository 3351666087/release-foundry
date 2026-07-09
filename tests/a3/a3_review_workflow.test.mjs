import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildReviewWorkflowIndex,
  buildReviewWorkflowRecord
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

  const index = buildReviewWorkflowIndex([waiverRecord, approvalRecord]);
  assert.equal(index.schema_version, "a3.review_workflow_index.v1");
  assert.equal(index.record_count, 2);
  assert.equal(index.waiver_count, 1);
  assert.equal(index.approval_count, 1);
  assert.equal(index.accepted_count, 2);
});
