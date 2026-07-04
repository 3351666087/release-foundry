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
      const failureSummary = caseResult.failure_summary
        || grade.judge_results?.find((judge) => judge.failure_analysis)?.failure_analysis?.summary
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
          || grade.judge_results?.find((judge) => judge.failure_analysis)?.failure_analysis?.severity
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
  const missing = (value) => Array.isArray(value) ? value : [];
  const countKeys = (value) => value && typeof value === "object" && !Array.isArray(value)
    ? Object.keys(value).length
    : 0;

  return {
    schema_version: coverageFixture.schema_version || "unknown",
    pack_id: coverageFixture.pack_id || "unknown",
    scenario_count: coverageFixture.scenario_count || 0,
    rubric_class_count: Array.isArray(coverageFixture.rubric_classes) ? coverageFixture.rubric_classes.length : 0,
    judge_mode_count: Array.isArray(coverageFixture.judge_modes) ? coverageFixture.judge_modes.length : 0,
    primary_failure_class_count: countKeys(coverageFixture.primary_failure_class_counts),
    golden_case_count: coverageFixture.golden_case_count || 0,
    golden_failure_class_count: countKeys(coverageFixture.golden_failure_class_counts),
    golden_failure_classes_missing: missing(coverageFixture.golden_failure_classes_missing),
    executable_run_case_count: coverageFixture.executable_run_case_count || 0,
    executable_failure_class_count: countKeys(coverageFixture.executable_failure_class_counts),
    executable_failure_classes_missing: missing(coverageFixture.executable_failure_classes_missing)
  };
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
    "",
    "## Coverage",
    "",
    `- Scenarios: ${coverage.scenario_count}`,
    `- Rubric classes: ${coverage.rubric_class_count}`,
    `- Judge modes: ${coverage.judge_mode_count}`,
    `- Golden cases: ${coverage.golden_case_count}`,
    `- Executable run cases: ${coverage.executable_run_case_count}`,
    `- Missing executable failure classes: ${coverage.executable_failure_classes_missing.join(", ") || "none"}`,
    "",
    "## Failure Clusters",
    ""
  ];

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
