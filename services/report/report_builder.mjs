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
    coverage_warnings: missing(coverageFixture.coverage_warnings),
    coverage_warning_count: missing(coverageFixture.coverage_warnings).length
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

export function buildMarkdownReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
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
    "failure_summary"
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
    item.failure_summary
  ]);
  return [header, ...rows]
    .map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(","))
    .join("\n");
}

export function buildJsonReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}) {
  return {
    schema_version: "a3.export_report.v1",
    summary: buildDashboardSummary(runFixture, gradeFixture),
    coverage: summarizeCoverage(coverageFixture),
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
      actual: item.actual
    }))
  };
}
