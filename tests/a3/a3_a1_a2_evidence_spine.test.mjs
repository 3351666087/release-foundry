import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  A3_A1_A2_EVIDENCE_SPINE_SCHEMA_VERSION,
  buildA3A1A2EvidenceSpine
} from "../../services/report/a3_a1_a2_evidence_spine.mjs";

test("A3 evidence spine joins A1 capture, A2 evaluation/gate, and A3 workflow", async () => {
  const [runFixture, gradeFixture, releaseGate, peerBranchCalibration] = await Promise.all([
    loadJson("../../fixtures/a3/mock_run_results.json"),
    loadJson("../../fixtures/a3/mock_grade_results.json"),
    loadJson("../../fixtures/a2/results/a2_release_gate_report.json"),
    loadJson("../../fixtures/a3/p3/a3_peer_branch_calibration.redacted.json")
  ]);
  const spine = buildA3A1A2EvidenceSpine({
    runFixture,
    gradeFixture,
    a2ReleaseGate: releaseGate,
    peerBranchCalibration,
    releaseDecisionProvenance: {
      status: "blocked",
      release_decision: "block",
      decision_authority: "fail_closed_by_a3_provenance",
      nodes: [{ id: "run" }, { id: "grade" }],
      blockers: [{ type: "auth_untrusted" }]
    },
    reviewWorkflow: { record_count: 2 },
    reportCenter: { report_count: 1 }
  }, { source: "mock" });

  assert.equal(spine.schema_version, A3_A1_A2_EVIDENCE_SPINE_SCHEMA_VERSION);
  assert.equal(spine.stages.length, 4);
  assert.deepEqual(spine.stages.map((item) => item.lane), ["A1", "A2", "A2", "A3"]);
  assert.equal(spine.stages[0].metrics.case_count, 32);
  assert.equal(spine.stages[0].metrics.trace_event_count > 0, true);
  assert.equal(spine.stages[1].metrics.judge_result_count > 32, true);
  assert.equal(spine.stages[2].status, "blocked");
  assert.equal(spine.stages[3].metrics.review_record_count, 2);
  assert.equal(spine.handoffs.every((item) => item.status === "linked"), true);
  assert.equal(spine.draft_watch.a1_identity_verification.observed, true);
  assert.equal(spine.draft_watch.a2_multimodal_real_api_smoke.observed, true);
  assert.equal(spine.draft_watch.draft_contracts_are_authoritative, false);
  assert.equal(spine.safety.a1_or_a2_semantics_mutated, false);
  assert.equal(JSON.stringify(spine).includes("Your request was denied"), false);
});

test("A3 evidence spine fails visibly when upstream evidence is absent", () => {
  const spine = buildA3A1A2EvidenceSpine();
  assert.equal(spine.status, "blocked");
  assert.equal(spine.stages[0].status, "missing");
  assert.equal(spine.stages[1].status, "missing");
  assert.equal(spine.release_decision, "unknown");
  assert.equal(spine.safety.raw_run_payload_embedded, false);
  assert.equal(spine.safety.raw_grade_payload_embedded, false);
});

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}
