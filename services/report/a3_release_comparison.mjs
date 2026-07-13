export const A3_RELEASE_COMPARISON_SCHEMA_VERSION = "a3.release_comparison.v1";

export function buildA3ReleaseComparison(baselineInput = {}, candidateInput = {}) {
  const baseline = summarizeCandidate(baselineInput);
  const candidate = summarizeCandidate(candidateInput);
  const resolvedFailureClasses = resolvedFailures(
    baseline.a2_evaluation.primary_failure_class_counts,
    candidate.a2_evaluation.primary_failure_class_counts
  );
  const authorityChanged = baseline.delivery.authoritative_decision !== candidate.delivery.authoritative_decision
    || baseline.delivery.release_ready !== candidate.delivery.release_ready;
  const deliveryProgressChanged = baseline.delivery.golden_path_passed !== candidate.delivery.golden_path_passed
    || baseline.delivery.deployment_checks_passed !== candidate.delivery.deployment_checks_passed;

  return {
    schema_version: A3_RELEASE_COMPARISON_SCHEMA_VERSION,
    comparison_id: `${baseline.version || "baseline"}__${candidate.version || "candidate"}`,
    baseline,
    candidate,
    changes: [
      change("a2_passed_cases", baseline.a2_evaluation.passed, candidate.a2_evaluation.passed, "cases", "A2", "higher_is_better"),
      change("a2_pass_rate", baseline.a2_evaluation.pass_rate, candidate.a2_evaluation.pass_rate, "percentage_points", "A2", "higher_is_better"),
      change(
        "missing_required_tool_cases",
        failureCount(baseline, "missing_required_tool"),
        failureCount(candidate, "missing_required_tool"),
        "cases",
        "A2",
        "lower_is_better"
      ),
      change("a1_tool_calls", baseline.a1_execution.tool_call_count, candidate.a1_execution.tool_call_count, "calls", "A1", "evidence_added"),
      change("trace_completeness", baseline.a1_execution.trace_completeness_percent, candidate.a1_execution.trace_completeness_percent, "percent", "A1", "higher_is_better"),
      change("release_artifacts", baseline.artifact_count, candidate.artifact_count, "artifacts", "A3", "evidence_added"),
      change("golden_path_stages", baseline.delivery.golden_path_passed, candidate.delivery.golden_path_passed, "stages", "A3", "higher_is_better"),
      change("deployment_checks", baseline.delivery.deployment_checks_passed, candidate.delivery.deployment_checks_passed, "checks", "A1/A3", "higher_is_better")
    ],
    resolved_failure_classes: resolvedFailureClasses,
    quality: {
      improved: candidate.a2_evaluation.passed > baseline.a2_evaluation.passed
        && candidate.a2_evaluation.failed < baseline.a2_evaluation.failed,
      a2_passed_case_delta: candidate.a2_evaluation.passed - baseline.a2_evaluation.passed,
      a2_pass_rate_point_delta: rounded(candidate.a2_evaluation.pass_rate - baseline.a2_evaluation.pass_rate),
      tool_call_delta: candidate.a1_execution.tool_call_count - baseline.a1_execution.tool_call_count,
      summary_code: "tool_chain_repaired_and_a2_case_grades_improved"
    },
    authority_boundary: {
      owner: "A2 Decision Ledger",
      decision_changed: authorityChanged,
      baseline_decision: baseline.delivery.authoritative_decision,
      candidate_decision: candidate.delivery.authoritative_decision,
      baseline_release_ready: baseline.delivery.release_ready,
      candidate_release_ready: candidate.delivery.release_ready,
      production_ready: candidate.delivery.production_ready,
      delivery_progress_changed: deliveryProgressChanged,
      explanation_code: authorityChanged
        ? "authoritative_release_state_changed"
        : "quality_improved_but_authoritative_release_state_unchanged"
    },
    provenance: {
      baseline: candidateProvenance(baselineInput, baseline),
      candidate: candidateProvenance(candidateInput, candidate),
      copied_authority_fields: [
        "a1_execution",
        "a2_evaluation",
        "delivery.authoritative_decision",
        "delivery.release_ready",
        "delivery.production_ready"
      ],
      display_only_derived_fields: ["changes", "resolved_failure_classes", "quality"]
    },
    safety: {
      a1_execution_recomputed: false,
      a2_scores_recomputed: false,
      a2_pass_fail_recomputed: false,
      a2_failure_class_recomputed: false,
      a2_release_decision_recomputed: false,
      production_readiness_overstated: false,
      secret_values_allowed: false
    }
  };
}

function summarizeCandidate(input = {}) {
  const runFixture = object(input.runFixture || input.run_fixture);
  const run = firstRun(runFixture);
  const gradeFixture = object(input.gradeFixture || input.grade_fixture);
  const grades = list(gradeFixture.grade_results).map(object);
  const path = object(input.deliveryGoldenPath || input.delivery_golden_path);
  const progress = object(path.progress);
  const authority = object(path.authoritative_release);
  const acceptance = object(input.deploymentAcceptance || input.deployment_acceptance);
  const acceptanceSummary = object(acceptance.summary);
  const manifest = object(input.releaseArtifactManifest || input.release_artifact_manifest);
  const release = object(manifest.release);
  const artifactSet = object(manifest.artifact_set);
  const aggregate = object(run.aggregate_metrics);
  const totalCases = integer(gradeFixture.total_cases, grades.length);
  const passed = integer(gradeFixture.passed, grades.filter((grade) => grade.passed === true).length);
  const failed = integer(gradeFixture.failed, Math.max(0, totalCases - passed));

  return {
    source: text(input.source, "unknown"),
    version: text(release.version, text(path.release_version, "unknown")),
    run_id: text(run.run_id, text(gradeFixture.report_id, "unknown")),
    a1_execution: {
      total_cases: integer(run.total_cases),
      passed: integer(run.passed),
      failed: integer(run.failed),
      trace_completeness_percent: percentage(aggregate.trace_completeness ?? run.trace_completeness),
      tool_call_count: integer(aggregate.total_tool_calls)
    },
    a2_evaluation: {
      total_cases: totalCases,
      passed,
      failed,
      pass_rate: totalCases ? rounded((passed / totalCases) * 100) : 0,
      primary_failure_class_counts: failureClassCounts(grades)
    },
    delivery: {
      authoritative_decision: text(authority.upstream_decision, "unknown"),
      release_ready: authority.release_ready === true,
      production_ready: path.production_ready === true,
      golden_path_passed: integer(progress.passed),
      golden_path_total: integer(progress.total),
      deployment_checks_passed: integer(acceptanceSummary.passed),
      deployment_checks_total: integer(acceptanceSummary.total_checks)
    },
    artifact_count: integer(artifactSet.artifact_count)
  };
}

function candidateProvenance(input, summary) {
  const runFixture = object(input.runFixture || input.run_fixture);
  const gradeFixture = object(input.gradeFixture || input.grade_fixture);
  const path = object(input.deliveryGoldenPath || input.delivery_golden_path);
  const acceptance = object(input.deploymentAcceptance || input.deployment_acceptance);
  const manifest = object(input.releaseArtifactManifest || input.release_artifact_manifest);
  return {
    source: summary.source,
    run_id: summary.run_id,
    release_version: summary.version,
    a1_schema_version: text(firstRun(runFixture).schema_version, text(runFixture.schema_version, "unknown")),
    a2_schema_version: text(gradeFixture.schema_version, "unknown"),
    golden_path_schema_version: text(path.schema_version, "unknown"),
    deployment_schema_version: text(acceptance.schema_version, "unknown"),
    release_artifact_schema_version: text(manifest.schema_version, "unknown")
  };
}

function firstRun(runFixture) {
  const runs = list(runFixture.runs).map(object);
  return runs[0] || runFixture;
}

function failureClassCounts(grades) {
  const counts = new Map();
  for (const grade of grades) {
    const failureClass = text(grade.primary_failure_class, "none");
    counts.set(failureClass, (counts.get(failureClass) || 0) + 1);
  }
  return Object.fromEntries([...counts.entries()].sort(([left], [right]) => left.localeCompare(right)));
}

function failureCount(candidate, failureClass) {
  return integer(candidate.a2_evaluation.primary_failure_class_counts[failureClass]);
}

function resolvedFailures(before = {}, after = {}) {
  return Object.entries(before)
    .filter(([failureClass, count]) => failureClass !== "none" && integer(count) > integer(after[failureClass]))
    .map(([failureClass, count]) => ({
      failure_class: failureClass,
      before: integer(count),
      after: integer(after[failureClass]),
      resolved: integer(count) - integer(after[failureClass])
    }));
}

function change(id, before, after, unit, authority, policy) {
  const delta = rounded(after - before);
  return {
    id,
    before,
    after,
    delta,
    unit,
    authority,
    direction: delta === 0
      ? "unchanged"
      : policy === "lower_is_better"
        ? (delta < 0 ? "improved" : "regressed")
        : policy === "evidence_added"
          ? (delta > 0 ? "evidence_added" : "unchanged")
          : (delta > 0 ? "improved" : "regressed")
  };
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function text(value, fallback = "unknown") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function integer(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : fallback;
}

function percentage(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return rounded(parsed >= 0 && parsed <= 1 ? parsed * 100 : parsed);
}

function rounded(value) {
  return Math.round(Number(value) * 10) / 10;
}
