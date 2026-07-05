export function normalizeScore(score) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return 0;
  }
  return score <= 1 ? Math.round(score * 1000) / 10 : Math.round(score * 10) / 10;
}

export function scoreBand(score) {
  const normalized = normalizeScore(score);
  if (normalized >= 90) {
    return "90-100";
  }
  if (normalized >= 70) {
    return "70-89";
  }
  if (normalized > 0) {
    return "1-69";
  }
  return "0";
}

const CANONICAL_FAILURE_CLASSES = new Set([
  "wrong_intent",
  "missing_required_tool",
  "unnecessary_tool_call",
  "forbidden_tool_call",
  "wrong_tool",
  "wrong_arguments",
  "wrong_tool_order",
  "missing_clarification",
  "hallucinated_tool_result",
  "ignored_tool_result",
  "unsafe_or_policy_violation",
  "poor_failure_recovery"
]);

const LOCAL_FAILURE_CLASS_MAP = new Map([
  ["bad_final_response", "wrong_intent"],
  ["output_schema_invalid", "wrong_intent"],
  ["unknown_failure", "wrong_intent"]
]);

export function canonicalPrimaryFailureClass(value, passed = false) {
  const failureClass = typeof value === "string" ? value.trim() : "";
  if (failureClass === "none") {
    return passed ? "none" : "wrong_intent";
  }
  if (CANONICAL_FAILURE_CLASSES.has(failureClass)) {
    return failureClass;
  }
  if (LOCAL_FAILURE_CLASS_MAP.has(failureClass)) {
    return LOCAL_FAILURE_CLASS_MAP.get(failureClass);
  }
  return passed ? "none" : "wrong_intent";
}

export function getGradeByCase(gradeFixture = {}) {
  const grades = Array.isArray(gradeFixture.grade_results) ? gradeFixture.grade_results : [];
  return new Map(grades.map((grade) => [grade.case_id, grade]));
}

function selectFailureAnalysis(grade = {}, primaryFailureClass = "none", passed = false) {
  const judgeResults = Array.isArray(grade.judge_results) ? grade.judge_results : [];
  const analyses = judgeResults
    .map((judge) => judge.failure_analysis)
    .filter((analysis) => analysis && typeof analysis === "object");

  if (passed) {
    return analyses.find((analysis) => analysis.primary_failure_class !== "none") || null;
  }

  const matchingPrimary = analyses.find((analysis) => (
    analysis.primary_failure_class
    && analysis.primary_failure_class !== "none"
    && canonicalPrimaryFailureClass(analysis.primary_failure_class, false) === primaryFailureClass
  ));
  if (matchingPrimary) {
    return matchingPrimary;
  }

  const failedJudge = judgeResults.find((judge) => (
    judge.passed === false
    && judge.failure_analysis
    && judge.failure_analysis.primary_failure_class !== "none"
  ));
  if (failedJudge) {
    return failedJudge.failure_analysis;
  }

  return analyses.find((analysis) => analysis.primary_failure_class !== "none") || null;
}

export function normalizeCases(runFixture = {}, gradeFixture = {}) {
  const gradeByCase = getGradeByCase(gradeFixture);
  const runs = Array.isArray(runFixture.runs)
    ? runFixture.runs
    : runFixture.run_id
      ? [runFixture]
      : [];

  return runs.flatMap((run) => {
    const cases = Array.isArray(run.cases) ? run.cases : [];
    return cases.map((caseResult) => {
      const grade = gradeByCase.get(caseResult.case_id) || caseResult.grade || {};
      const passed = typeof grade.passed === "boolean"
        ? grade.passed
        : caseResult.status === "passed";
      const rawPrimaryFailureClass = grade.primary_failure_class
        || caseResult.primary_failure_class
        || "";
      const primaryFailureClass = canonicalPrimaryFailureClass(rawPrimaryFailureClass, passed);
      const failureAnalysis = selectFailureAnalysis(grade, primaryFailureClass, passed);
      const failureSummary = caseResult.failure_summary
        || failureAnalysis?.summary
        || (passed ? "Passed." : "Failure requires triage.");

      return {
        ...caseResult,
        run_id: run.run_id,
        dataset_id: run.dataset_id,
        runner_id: run.runner_id,
        run_status: run.status,
        passed,
        score: normalizeScore(grade.score ?? caseResult.score),
        primary_failure_class: primaryFailureClass,
        raw_primary_failure_class: rawPrimaryFailureClass,
        failure_summary: failureSummary,
        severity: caseResult.severity
          || failureAnalysis?.severity
          || (passed ? "none" : "major"),
        judge_results: grade.judge_results || [],
        judge_modes: (grade.judge_results || []).map((judge) => judge.judge_mode).filter(Boolean),
        score_band: scoreBand(grade.score ?? caseResult.score),
        grade
      };
    });
  });
}

export function getFilterOptions(cases = []) {
  const uniqueSorted = (values) => [...new Set(values.filter(Boolean))].sort();
  return {
    statuses: ["passed", "failed"],
    families: uniqueSorted(cases.map((item) => item.family)),
    failureClasses: uniqueSorted(cases.map((item) => item.primary_failure_class)),
    runIds: uniqueSorted(cases.map((item) => item.run_id)),
    severities: uniqueSorted(cases.map((item) => item.severity)),
    scoreBands: ["90-100", "70-89", "1-69", "0"],
    judgeModes: uniqueSorted(cases.flatMap((item) => item.judge_modes || []))
  };
}

export function filterCases(cases = [], filters = {}) {
  const {
    status = "all",
    family = "all",
    failureClass = "all",
    runId = "all",
    severity = "all",
    scoreBand: selectedScoreBand = "all",
    judgeMode = "all"
  } = filters;

  return cases.filter((item) => {
    const caseStatus = item.passed ? "passed" : "failed";
    return (status === "all" || caseStatus === status)
      && (family === "all" || item.family === family)
      && (failureClass === "all" || item.primary_failure_class === failureClass)
      && (runId === "all" || item.run_id === runId)
      && (severity === "all" || item.severity === severity)
      && (selectedScoreBand === "all" || item.score_band === selectedScoreBand)
      && (judgeMode === "all" || (item.judge_modes || []).includes(judgeMode));
  });
}

export function buildDashboardSummary(runFixture = {}, gradeFixture = {}) {
  const runs = Array.isArray(runFixture.runs)
    ? runFixture.runs
    : runFixture.run_id
      ? [runFixture]
      : [];
  const cases = normalizeCases(runFixture, gradeFixture);
  const totalCases = cases.length;
  const passed = cases.filter((item) => item.passed).length;
  const failed = totalCases - passed;
  const mediaEvidenceCases = cases.filter(hasMediaEvidence).length;
  const vmStreamCases = cases.filter((item) => (item.media_evidence?.vm_streams || []).length > 0).length;
  const avgScore = totalCases
    ? Math.round((cases.reduce((sum, item) => sum + normalizeScore(item.score), 0) / totalCases) * 10) / 10
    : 0;

  return {
    totalRuns: runs.length,
    totalCases,
    passed,
    failed,
    passRate: totalCases ? Math.round((passed / totalCases) * 1000) / 10 : 0,
    avgScore,
    traceCompleteness: runs.length
      ? Math.round((runs.reduce((sum, run) => sum + (run.trace_completeness || 0), 0) / runs.length) * 1000) / 10
      : 0,
    mediaEvidenceCases,
    vmStreamCases,
    lastRunId: runs[0]?.run_id || "none"
  };
}

export function summarizeCoverage(coverageFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const available = isObject(coverageFixture) && Object.keys(coverageFixture).length > 0;
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const countKeys = (value) => Object.keys(mapping(value)).length;

  return {
    available,
    schema_version: available ? coverageFixture.schema_version || "unknown" : "none",
    pack_id: available ? coverageFixture.pack_id || "unknown" : "none",
    meets_assignment_minimums: coverageFixture.meets_assignment_minimums === true,
    assignment_checks: mapping(coverageFixture.assignment_checks),
    scenario_count: coverageFixture.scenario_count || 0,
    scenario_dimension_minimums: mapping(coverageFixture.scenario_dimension_minimums),
    scenario_dimension_checks: mapping(coverageFixture.scenario_dimension_checks),
    scenario_dimension_counts: mapping(coverageFixture.scenario_dimension_counts),
    scenario_dimension_scenarios: mapping(coverageFixture.scenario_dimension_scenarios),
    thin_scenario_dimensions: mapping(coverageFixture.thin_scenario_dimensions),
    scenario_quality_targets: mapping(coverageFixture.scenario_quality_targets),
    scenario_quality_warnings: missing(coverageFixture.scenario_quality_warnings),
    scenario_quality_warning_count: missing(coverageFixture.scenario_quality_warnings).length,
    difficulty_counts: mapping(coverageFixture.difficulty_counts),
    action_count_counts: mapping(coverageFixture.action_count_counts),
    multi_turn_scenario_count: coverageFixture.multi_turn_scenario_count || 0,
    environment_counts: mapping(coverageFixture.environment_counts),
    tag_counts: mapping(coverageFixture.tag_counts),
    tool_policy_shape_counts: mapping(coverageFixture.tool_policy_shape_counts),
    required_tool_counts: mapping(coverageFixture.required_tool_counts),
    optional_tool_counts: mapping(coverageFixture.optional_tool_counts),
    forbidden_tool_counts: mapping(coverageFixture.forbidden_tool_counts),
    ordered_tool_count: coverageFixture.ordered_tool_count || 0,
    ordered_tool_pairs: mapping(coverageFixture.ordered_tool_pairs),
    fixture_scenario_count: coverageFixture.fixture_scenario_count || 0,
    fixture_type_counts: mapping(coverageFixture.fixture_type_counts),
    fixture_ref_counts_by_scenario: mapping(coverageFixture.fixture_ref_counts_by_scenario),
    rubric_class_count: Array.isArray(coverageFixture.rubric_classes) ? coverageFixture.rubric_classes.length : 0,
    judge_mode_count: Array.isArray(coverageFixture.judge_modes) ? coverageFixture.judge_modes.length : 0,
    primary_failure_class_count: countKeys(coverageFixture.primary_failure_class_counts),
    golden_case_count: coverageFixture.golden_case_count || 0,
    golden_failure_class_count: countKeys(coverageFixture.golden_failure_class_counts),
    golden_failure_class_cases: mapping(coverageFixture.golden_failure_class_cases),
    golden_failure_classes_missing: missing(coverageFixture.golden_failure_classes_missing),
    thin_golden_failure_classes: mapping(coverageFixture.thin_golden_failure_classes),
    executable_run_case_count: coverageFixture.executable_run_case_count || 0,
    executable_failure_class_count: countKeys(coverageFixture.executable_failure_class_counts),
    executable_failure_class_cases: mapping(coverageFixture.executable_failure_class_cases),
    executable_failure_classes_missing: missing(coverageFixture.executable_failure_classes_missing),
    thin_executable_failure_classes: mapping(coverageFixture.thin_executable_failure_classes),
    executable_media_case_count: coverageFixture.executable_media_case_count || 0,
    executable_tool_output_grounding_case_count: coverageFixture.executable_tool_output_grounding_case_count || 0,
    executable_media_expected_class_counts: mapping(coverageFixture.executable_media_expected_class_counts),
    executable_media_case_refs: missing(coverageFixture.executable_media_case_refs),
    executable_tool_output_grounding_case_refs: missing(coverageFixture.executable_tool_output_grounding_case_refs),
    coverage_warnings: missing(coverageFixture.coverage_warnings),
    coverage_warning_count: missing(coverageFixture.coverage_warnings).length
  };
}

export function summarizeEvidenceReadiness(evidenceFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const available = isObject(evidenceFixture) && Object.keys(evidenceFixture).length > 0;
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const ashr = mapping(evidenceFixture.ashr_grading_preflight);
  const ashrMergeGate = mapping(evidenceFixture.ashr_public_merge_gate);
  const semantic = mapping(evidenceFixture.semantic_judge_preflight);
  const semanticMergeGate = mapping(evidenceFixture.semantic_live_merge_gate);
  const redaction = mapping(evidenceFixture.redaction_policy);

  return {
    available,
    schema_version: available ? evidenceFixture.schema_version || "unknown" : "none",
    status: available ? evidenceFixture.status || "unknown" : "none",
    ready_for_external_collection: evidenceFixture.ready_for_external_collection === true,
    calibration_case_count: evidenceFixture.calibration_case_count || 0,
    readiness_checks: mapping(evidenceFixture.readiness_checks),
    ashr_current_missing: ashr.current_missing || 0,
    ashr_expected_observation_count: ashr.expected_observation_count || 0,
    ashr_case_map_covers_all_calibration_cases: ashr.case_map_covers_all_calibration_cases === true,
    ashr_public_merge_status: ashrMergeGate.status || "unknown",
    ashr_public_matrix_merged: ashrMergeGate.public_matrix_merged === true,
    ashr_safe_to_mark_c3_met: ashrMergeGate.safe_to_mark_c3_met === true,
    ashr_merged_public_observation_count: ashrMergeGate.merged_public_observation_count || 0,
    ashr_missing_public_observation_count: ashrMergeGate.missing_public_observation_count || 0,
    ashr_public_merge_blocking_reason: ashrMergeGate.blocking_reason || "",
    semantic_offline_reference_only: semantic.offline_reference_only === true,
    semantic_expected_reviewed_observation_count: semantic.expected_reviewed_observation_count || 0,
    semantic_risk_assessment_status: semantic.risk_assessment_status || "unknown",
    semantic_false_positive_tracking_ready: semantic.false_positive_tracking_ready === true,
    semantic_false_positive_candidate_count: semantic.false_positive_candidate_count || 0,
    semantic_false_negative_candidate_count: semantic.false_negative_candidate_count || 0,
    semantic_failure_class_drift_candidate_count: semantic.failure_class_drift_candidate_count || 0,
    semantic_score_delta_review_count: semantic.score_delta_review_count || 0,
    semantic_risk_case_count: semantic.risk_case_count || 0,
    semantic_live_merge_status: semanticMergeGate.status || "unknown",
    semantic_audited_live_evidence_merged: semanticMergeGate.audited_live_evidence_merged === true,
    semantic_safe_to_mark_c4_met: semanticMergeGate.safe_to_mark_c4_met === true,
    semantic_missing_audited_observation_count: semanticMergeGate.missing_audited_observation_count || 0,
    semantic_live_merge_blocking_reason: semanticMergeGate.blocking_reason || "",
    semantic_required_fields: missing(semantic.required_fields),
    required_sdk_languages: missing(semantic.required_sdk_languages),
    covered_sdk_languages: missing(semantic.covered_sdk_languages),
    batch_plan_refs: missing(evidenceFixture.batch_plan_refs),
    private_raw_path: redaction.raw_private_path || "",
    never_commit: missing(redaction.never_commit)
  };
}

export function summarizeRegressionReadiness(caseBookFixture = {}, regressionReplayFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const caseBookAvailable = isObject(caseBookFixture) && Object.keys(caseBookFixture).length > 0;
  const replayAvailable = isObject(regressionReplayFixture) && Object.keys(regressionReplayFixture).length > 0;
  const candidatePool = mapping(caseBookFixture.candidate_pool);
  const caseBookGate = mapping(caseBookFixture.maturity_gate);
  const replayGate = mapping(regressionReplayFixture.maturity_gate);

  return {
    available: caseBookAvailable || replayAvailable,
    case_book_schema_version: caseBookAvailable ? caseBookFixture.schema_version || "unknown" : "none",
    replay_schema_version: replayAvailable ? regressionReplayFixture.schema_version || "unknown" : "none",
    regression_case_count: caseBookFixture.regression_case_count || 0,
    replay_case_count: regressionReplayFixture.replay_case_count || 0,
    replay_ready: regressionReplayFixture.replay_ready === true,
    maturity_status: regressionReplayFixture.maturity_status || caseBookGate.status || "none",
    case_book_ready: caseBookGate.ready === true,
    replay_gate_ready: replayGate.ready === true,
    target_regression_case_count: caseBookGate.target_regression_case_count || 0,
    current_regression_case_count: caseBookGate.current_regression_case_count || caseBookFixture.regression_case_count || 0,
    target_replay_case_count: replayGate.target_replay_case_count || 0,
    current_replay_case_count: replayGate.current_replay_case_count || regressionReplayFixture.replay_case_count || 0,
    failed_replay_case_count: replayGate.failed_replay_case_count || regressionReplayFixture.failed_count || 0,
    local_llm_mismatch_count: candidatePool.local_llm_mismatch_count || 0,
    ashr_grading_missing_count: candidatePool.ashr_grading_missing_count || 0,
    gaps: [...missing(caseBookGate.gaps), ...missing(replayGate.gaps)]
  };
}

function formatCoverageCaseRefs(refs = []) {
  if (!Array.isArray(refs) || refs.length === 0) {
    return "none";
  }
  return refs
    .map((item) => `${item.case_id || "unknown_case"}/${item.scenario_id || "unknown_scenario"}`)
    .join(", ");
}

function coverageEvidenceLines(coverage = {}) {
  const goldenClasses = Object.keys(coverage.golden_failure_class_cases || {});
  const executableClasses = Object.keys(coverage.executable_failure_class_cases || {});
  return [...new Set([...goldenClasses, ...executableClasses])]
    .sort()
    .map((failureClass) => (
      `- ${failureClass}: golden ${formatCoverageCaseRefs(coverage.golden_failure_class_cases[failureClass])}; `
      + `executable ${formatCoverageCaseRefs(coverage.executable_failure_class_cases[failureClass])}`
    ));
}

export function clusterFailures(runFixture = {}, gradeFixture = {}) {
  const failedCases = normalizeCases(runFixture, gradeFixture)
    .filter((item) => !item.passed && item.primary_failure_class !== "none");
  const clusters = new Map();

  for (const item of failedCases) {
    const key = item.primary_failure_class || "wrong_intent";
    if (!clusters.has(key)) {
      clusters.set(key, {
        failureClass: key,
        count: 0,
        severity: item.severity || "major",
        cases: [],
        summaries: new Set()
      });
    }

    const cluster = clusters.get(key);
    cluster.count += 1;
    cluster.cases.push({
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      title: item.title,
      score: item.score,
      summary: item.failure_summary
    });
    if (item.failure_summary) {
      cluster.summaries.add(item.failure_summary);
    }
  }

  return [...clusters.values()].map((cluster) => ({
    ...cluster,
    summaries: [...cluster.summaries]
  })).sort((left, right) => right.count - left.count || left.failureClass.localeCompare(right.failureClass));
}

export function buildToolCallDiffs(caseResult = {}) {
  const expected = normalizeToolCalls(caseResult.expected?.tool_calls);
  const actual = normalizeToolCalls(caseResult.actual?.tool_calls);
  const total = Math.max(expected.length, actual.length);
  const diffs = [];

  for (let index = 0; index < total; index += 1) {
    const expectedCall = expected[index] || null;
    const actualCall = actual[index] || null;
    const status = toolDiffStatus(expectedCall, actualCall);
    diffs.push({
      index,
      status,
      expected: expectedCall,
      actual: actualCall,
      summary: toolDiffSummary(status, expectedCall, actualCall)
    });
  }

  return diffs;
}

export function buildMarkdownReport(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  evidenceReadinessFixture = {},
  caseBookFixture = {},
  regressionReplayFixture = {}
) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const evidenceReadiness = summarizeEvidenceReadiness(evidenceReadinessFixture);
  const regressionReadiness = summarizeRegressionReadiness(caseBookFixture, regressionReplayFixture);
  const clusters = clusterFailures(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const lines = [
    "# A3 Dashboard Triage Report",
    "",
    `- Runs: ${summary.totalRuns}`,
    `- Cases: ${summary.totalCases}`,
    `- Pass rate: ${summary.passRate}%`,
    `- Average score: ${summary.avgScore}`,
    `- Trace completeness: ${summary.traceCompleteness}%`,
    ""
  ];

  if (coverage.available) {
    const evidenceLines = coverageEvidenceLines(coverage);
    lines.push(
      "## Coverage",
      "",
      `- Assignment minimums met: ${coverage.meets_assignment_minimums ? "yes" : "no"}`,
      `- Scenarios: ${coverage.scenario_count}`,
      `- Scenario dimensions met: ${Object.values(coverage.scenario_dimension_checks).filter(Boolean).length}/${Object.keys(coverage.scenario_dimension_checks).length}`,
      `- Scenario quality warnings: ${coverage.scenario_quality_warning_count}`,
      `- Rubric classes: ${coverage.rubric_class_count}`,
      `- Judge modes: ${coverage.judge_mode_count}`,
      `- Golden cases: ${coverage.golden_case_count}`,
      `- Executable run cases: ${coverage.executable_run_case_count}`,
      `- Media executable cases: ${coverage.executable_media_case_count}`,
      `- Tool-output grounding executable cases: ${coverage.executable_tool_output_grounding_case_count}`,
      `- Missing executable failure classes: ${coverage.executable_failure_classes_missing.join(", ") || "none"}`,
      `- Coverage warnings: ${coverage.coverage_warning_count}`,
      ""
    );
    if (coverage.scenario_quality_warnings.length > 0) {
      lines.push(
        "### Scenario Quality Warnings",
        "",
        ...coverage.scenario_quality_warnings.map((warning) => `- ${warning}`),
        ""
      );
    }
    if (evidenceLines.length > 0) {
      lines.push(
        "### Failure Class Evidence",
        "",
        ...evidenceLines,
        ""
      );
    }
  }

  if (evidenceReadiness.available) {
    lines.push(
      "## Evidence Readiness",
      "",
      `- Status: ${evidenceReadiness.status}`,
      `- Ready for external collection: ${evidenceReadiness.ready_for_external_collection ? "yes" : "no"}`,
      `- Calibration cases: ${evidenceReadiness.calibration_case_count}`,
      `- Ashr grading missing: ${evidenceReadiness.ashr_current_missing}/${evidenceReadiness.ashr_expected_observation_count}`,
      `- Ashr public merge: ${evidenceReadiness.ashr_public_merge_status}`,
      `- Ashr safely merged observations: ${evidenceReadiness.ashr_merged_public_observation_count}/${evidenceReadiness.ashr_expected_observation_count}`,
      `- C3 safe to mark met: ${evidenceReadiness.ashr_safe_to_mark_c3_met ? "yes" : "no"}`,
      `- Semantic judge offline-only: ${evidenceReadiness.semantic_offline_reference_only ? "yes" : "no"}`,
      `- Semantic risk register: ${evidenceReadiness.semantic_risk_assessment_status}`,
      `- Semantic false-positive candidates: ${evidenceReadiness.semantic_false_positive_candidate_count}`,
      `- Semantic failure-class drift candidates: ${evidenceReadiness.semantic_failure_class_drift_candidate_count}`,
      `- Semantic score-delta reviews: ${evidenceReadiness.semantic_score_delta_review_count}`,
      `- Semantic live merge: ${evidenceReadiness.semantic_live_merge_status}`,
      `- C4 safe to mark met: ${evidenceReadiness.semantic_safe_to_mark_c4_met ? "yes" : "no"}`,
      `- SDK languages covered: ${evidenceReadiness.covered_sdk_languages.join(", ") || "none"}`,
      `- Private evidence path: ${evidenceReadiness.private_raw_path || "none"}`,
      ""
    );
  }

  if (regressionReadiness.available) {
    lines.push(
      "## Regression Readiness",
      "",
      `- Maturity status: ${regressionReadiness.maturity_status}`,
      `- Case book regressions: ${regressionReadiness.current_regression_case_count}/${regressionReadiness.target_regression_case_count || "unknown"}`,
      `- Replay cases: ${regressionReadiness.current_replay_case_count}/${regressionReadiness.target_replay_case_count || "unknown"}`,
      `- Replay ready: ${regressionReadiness.replay_ready ? "yes" : "no"}`,
      `- Local-vs-LLM mismatches: ${regressionReadiness.local_llm_mismatch_count}`,
      `- Ashr grading missing: ${regressionReadiness.ashr_grading_missing_count}`,
      `- Maturity gaps: ${regressionReadiness.gaps.join(" | ") || "none"}`,
      ""
    );
  }

  lines.push(
    "## Failure Clusters",
    ""
  );

  if (clusters.length === 0) {
    lines.push("- No failures.");
  } else {
    for (const cluster of clusters) {
      lines.push(`- ${cluster.failureClass}: ${cluster.count} case(s), severity ${cluster.severity}`);
    }
  }

  lines.push("", "## Cases", "");
  for (const item of cases) {
    lines.push(`- ${item.case_id} / ${item.scenario_id}: ${item.passed ? "PASS" : "FAIL"} (${item.score}) - ${item.failure_summary}`);
  }

  return `${lines.join("\n")}\n`;
}

export function buildCsvReport(runFixture = {}, gradeFixture = {}) {
  const header = [
    "run_id",
    "case_id",
    "scenario_id",
    "title",
    "status",
    "score",
    "severity",
    "primary_failure_class",
    "failure_summary",
    "media_types",
    "media_evidence_count",
    "vm_stream_count"
  ];
  const rows = normalizeCases(runFixture, gradeFixture).map((item) => [
    item.run_id,
    item.case_id,
    item.scenario_id,
    item.title,
    item.passed ? "passed" : "failed",
    item.score,
    item.severity,
    item.primary_failure_class,
    item.failure_summary,
    (item.media_evidence?.media_types || []).join("|"),
    item.media_evidence?.evidence_items?.length || 0,
    item.media_evidence?.vm_streams?.length || 0
  ]);
  return [header, ...rows]
    .map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
    .join("\n");
}

export function buildJsonReport(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  evidenceReadinessFixture = {},
  caseBookFixture = {},
  regressionReplayFixture = {}
) {
  return {
    schema_version: "a3.export_report.v1",
    summary: buildDashboardSummary(runFixture, gradeFixture),
    coverage: summarizeCoverage(coverageFixture),
    evidence_readiness: summarizeEvidenceReadiness(evidenceReadinessFixture),
    regression_readiness: summarizeRegressionReadiness(caseBookFixture, regressionReplayFixture),
    failure_clusters: clusterFailures(runFixture, gradeFixture),
    cases: normalizeCases(runFixture, gradeFixture).map((item) => ({
      run_id: item.run_id,
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      title: item.title,
      status: item.passed ? "passed" : "failed",
      score: item.score,
      severity: item.severity,
      score_band: item.score_band,
      judge_modes: item.judge_modes,
      primary_failure_class: item.primary_failure_class,
      failure_summary: item.failure_summary,
      expected: item.expected,
      actual: item.actual,
      tool_call_diffs: buildToolCallDiffs(item),
      media_evidence: item.media_evidence || null
    }))
  };
}

function hasMediaEvidence(item = {}) {
  const mediaEvidence = item.media_evidence || {};
  return (mediaEvidence.media_types || []).length > 0
    || (mediaEvidence.evidence_items || []).length > 0
    || (mediaEvidence.vm_streams || []).length > 0;
}

function normalizeToolCalls(toolCalls) {
  if (!Array.isArray(toolCalls)) {
    return [];
  }

  return toolCalls.map((call) => ({
    name: call.tool_name || call.name || call.tool || "unknown_tool",
    arguments: call.arguments || call.args || call.parameters || {},
    raw: call
  }));
}

function toolDiffStatus(expectedCall, actualCall) {
  if (expectedCall && !actualCall) {
    return "missing_required_tool";
  }
  if (!expectedCall && actualCall) {
    return "unexpected_tool_call";
  }
  if (!expectedCall && !actualCall) {
    return "none";
  }
  if (expectedCall.name !== actualCall.name) {
    return "wrong_tool";
  }
  if (stableJson(expectedCall.arguments) !== stableJson(actualCall.arguments)) {
    return "wrong_arguments";
  }
  return "match";
}

function toolDiffSummary(status, expectedCall, actualCall) {
  if (status === "match") {
    return `Matched ${expectedCall.name}.`;
  }
  if (status === "missing_required_tool") {
    return `Expected ${expectedCall.name}, but no actual tool call was present at this position.`;
  }
  if (status === "unexpected_tool_call") {
    return `Unexpected actual tool call ${actualCall.name}.`;
  }
  if (status === "wrong_tool") {
    return `Expected ${expectedCall.name}, but actual tool was ${actualCall.name}.`;
  }
  if (status === "wrong_arguments") {
    return `Tool ${expectedCall.name} was called with different arguments.`;
  }
  return "No tool call expected or observed.";
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}
