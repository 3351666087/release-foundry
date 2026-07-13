import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildA3ReleaseComparison } from "../../services/report/a3_release_comparison.mjs";
import { createFixtureBackedA3Store, loadA3SourceSnapshot } from "../../services/report/a3_store.mjs";

test("rc.2 comparison preserves A1 execution, A2 grades, and A2 release authority as separate facts", async () => {
  const snapshot = await loadA3SourceSnapshot("a3-golden-path-rc2");
  const comparison = snapshot.releaseComparison;

  assert.equal(comparison.schema_version, "a3.release_comparison.v1");
  assert.equal(comparison.baseline.version, "0.2.0-rc.1");
  assert.equal(comparison.candidate.version, "0.2.0-rc.2");
  assert.equal(comparison.baseline.run_id, "a3-golden-20260712-001");
  assert.equal(comparison.candidate.run_id, "a3-golden-20260712-002");

  assert.deepEqual(comparison.baseline.a1_execution, {
    total_cases: 3,
    passed: 3,
    failed: 0,
    trace_completeness_percent: 100,
    tool_call_count: 0
  });
  assert.deepEqual(comparison.candidate.a1_execution, {
    total_cases: 3,
    passed: 3,
    failed: 0,
    trace_completeness_percent: 100,
    tool_call_count: 4
  });

  assert.equal(comparison.baseline.a2_evaluation.passed, 1);
  assert.equal(comparison.baseline.a2_evaluation.failed, 2);
  assert.equal(comparison.baseline.a2_evaluation.pass_rate, 33.3);
  assert.deepEqual(comparison.baseline.a2_evaluation.primary_failure_class_counts, {
    missing_required_tool: 2,
    none: 1
  });
  assert.equal(comparison.candidate.a2_evaluation.passed, 3);
  assert.equal(comparison.candidate.a2_evaluation.failed, 0);
  assert.equal(comparison.candidate.a2_evaluation.pass_rate, 100);
  assert.deepEqual(comparison.candidate.a2_evaluation.primary_failure_class_counts, { none: 3 });

  assert.deepEqual(comparison.resolved_failure_classes, [{
    failure_class: "missing_required_tool",
    before: 2,
    after: 0,
    resolved: 2
  }]);
  assert.equal(comparison.quality.improved, true);
  assert.equal(comparison.quality.a2_passed_case_delta, 2);
  assert.equal(comparison.quality.a2_pass_rate_point_delta, 66.7);
  assert.equal(comparison.quality.tool_call_delta, 4);

  assert.equal(comparison.baseline.delivery.authoritative_decision, "block");
  assert.equal(comparison.candidate.delivery.authoritative_decision, "block");
  assert.equal(comparison.authority_boundary.decision_changed, false);
  assert.equal(comparison.authority_boundary.candidate_release_ready, false);
  assert.equal(comparison.authority_boundary.production_ready, false);
  assert.equal(comparison.baseline.delivery.golden_path_passed, 7);
  assert.equal(comparison.candidate.delivery.golden_path_passed, 7);
  assert.equal(comparison.baseline.delivery.deployment_checks_passed, 8);
  assert.equal(comparison.candidate.delivery.deployment_checks_passed, 8);
  assert.equal(comparison.authority_boundary.delivery_progress_changed, false);

  assert.equal(comparison.baseline.artifact_count, 12);
  assert.equal(comparison.candidate.artifact_count, 16);
  assert.equal(comparison.safety.a2_scores_recomputed, false);
  assert.equal(comparison.safety.a2_pass_fail_recomputed, false);
  assert.equal(comparison.safety.a2_failure_class_recomputed, false);
  assert.equal(comparison.safety.a2_release_decision_recomputed, false);
});

test("dashboard API and OpenAPI expose the same release-comparison contract", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["a3-golden-path-rc2"] });
  const dashboard = await store.getDashboardSnapshot("a3-golden-path-rc2");
  const openapi = JSON.parse(await readFile("docs/a3/openapi/a3_commercial_api.openapi.json", "utf8"));

  assert.equal(dashboard.release_comparison.schema_version, "a3.release_comparison.v1");
  assert.equal(dashboard.release_comparison.candidate.a2_evaluation.passed, 3);
  assert.equal(dashboard.release_comparison.authority_boundary.candidate_decision, "block");
  assert.equal(dashboard.release_comparison.authority_boundary.current_status, "integrity_invalid");
  assert.equal(dashboard.release_comparison.authority_boundary.current_integrity_verified, false);
  assert.equal(dashboard.release_comparison.authority_boundary.current_upstream_decision, "unknown");
  assert.equal(dashboard.release_comparison.runtime_authority_validation.historical_candidate_decision, "block");
  assert.equal(dashboard.release_comparison.runtime_authority_validation.current_release_authorized, false);
  assert.equal(dashboard.release_comparison.safety.runtime_authority_recomputed, false);
  assert.equal(
    openapi.components.schemas.DashboardSnapshot.properties.release_comparison.$ref,
    "#/components/schemas/ReleaseComparison"
  );
  assert.equal(
    openapi.components.schemas.DashboardSnapshot.properties.deployment_handoff.$ref,
    "#/components/schemas/DeploymentHandoff"
  );
  assert.equal(
    openapi.components.schemas.ReleaseComparison.properties.schema_version.const,
    "a3.release_comparison.v1"
  );
  assert.equal(
    openapi.components.schemas.ReleaseComparison.properties.safety.properties.a2_release_decision_recomputed.const,
    false
  );
  assert.equal(
    openapi.components.schemas.ReleaseComparison.properties.runtime_authority_validation.$ref,
    "#/components/schemas/ReleaseComparisonRuntimeAuthority"
  );
});

test("comparison builder fails closed instead of inventing passing or release-ready evidence", () => {
  const comparison = buildA3ReleaseComparison({}, {});

  assert.equal(comparison.baseline.a2_evaluation.passed, 0);
  assert.equal(comparison.candidate.a2_evaluation.passed, 0);
  assert.equal(comparison.quality.improved, false);
  assert.equal(comparison.authority_boundary.baseline_decision, "unknown");
  assert.equal(comparison.authority_boundary.candidate_decision, "unknown");
  assert.equal(comparison.authority_boundary.candidate_release_ready, false);
  assert.equal(comparison.authority_boundary.production_ready, false);
});
