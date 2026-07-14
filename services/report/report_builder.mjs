import {
  redactExport,
  sanitizeCsvCellValue,
  summarizeRedactionResults
} from "./export_redaction_firewall.mjs";
import { summarizeA3PeerBranchCalibration } from "./a3_peer_branch_calibration.mjs";

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

const MEDIA_CHANNEL_ORDER = ["audio", "files", "images", "video", "vm_stream"];

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
  const grades = normalizeGradeResults(gradeFixture);
  return new Map(grades.map((grade) => [grade.case_id, grade]));
}

function normalizeGradeResults(gradeFixture = {}) {
  if (Array.isArray(gradeFixture)) {
    return gradeFixture.flatMap((item) => normalizeGradeResults(item));
  }
  if (Array.isArray(gradeFixture.grade_results)) {
    return gradeFixture.grade_results;
  }
  if (isObject(gradeFixture.grade_result)) {
    return [gradeFixture.grade_result];
  }
  if (gradeFixture.case_id && (
    Array.isArray(gradeFixture.judge_results)
    || "passed" in gradeFixture
    || "score" in gradeFixture
    || "primary_failure_class" in gradeFixture
  )) {
    return [gradeFixture];
  }
  return [];
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
  const runs = normalizeRunInputs(runFixture);

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
      const expected = normalizeExpected(caseResult, grade);
      const actual = normalizeActual(caseResult, grade);
      const traceEvents = normalizeTraceEvents(caseResult);
      const observations = Array.isArray(caseResult.observations) ? caseResult.observations : [];
      const mediaEvidence = normalizeMediaEvidence(caseResult, actual);

      return {
        ...caseResult,
        run_id: run.run_id || caseResult.run_id || grade.run_id || "run-local",
        dataset_id: run.dataset_id || caseResult.dataset_id || grade.dataset_id || "local-dataset",
        runner_id: run.runner_id || caseResult.runner_id || "a1-local-runner",
        run_status: run.status,
        expected,
        actual,
        trace_events: traceEvents,
        observations,
        trace_ready: traceEvents.length > 0 || observations.length > 0,
        media_evidence: mediaEvidence,
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

function normalizeRunInputs(runFixture = {}) {
  if (Array.isArray(runFixture)) {
    return runFixture.flatMap((item) => normalizeRunInputs(item));
  }
  if (Array.isArray(runFixture.runs)) {
    return runFixture.runs;
  }
  if (runFixture.run_id && Array.isArray(runFixture.cases)) {
    return [runFixture];
  }
  if (Array.isArray(runFixture.cases)) {
    return [{
      run_id: runFixture.run_id || runFixture.id || "run-local-cases",
      dataset_id: runFixture.dataset_id || "local-cases",
      runner_id: runFixture.runner_id || "a1-local-runner",
      status: runFixture.status || "completed",
      cases: runFixture.cases.map((item, index) => normalizeLooseCase(item, index))
    }];
  }
  if (runFixture.schema === "ashr.clone.run.v1" && isObject(runFixture.run)) {
    return [{
      run_id: runFixture.run.run_id || runFixture.run.id || `run-${runFixture.name || "a1-fixture"}`,
      dataset_id: runFixture.dataset_id || runFixture.name || "a1-run-fixture",
      runner_id: runFixture.run.agent || "a1-local-runner",
      status: runFixture.run.status || "completed",
      started_at: runFixture.run.started_at,
      ended_at: runFixture.run.finished_at,
      cases: [normalizeA1RunFixtureCase(runFixture)]
    }];
  }
  if (runFixture.case_id && (isObject(runFixture.run) || isObject(runFixture.expected))) {
    return [{
      run_id: runFixture.run_id || `run-${runFixture.case_id}`,
      dataset_id: runFixture.dataset_id || "a2-single-case",
      runner_id: runFixture.runner_id || "a2-local-runner",
      status: "completed",
      cases: [normalizeA2RunFixtureCase(runFixture)]
    }];
  }
  return [];
}

function normalizeLooseCase(caseResult = {}, index = 0) {
  return {
    ...caseResult,
    case_id: caseResult.case_id || caseResult.id || `case-${index + 1}`,
    title: caseResult.title || caseResult.name || caseResult.prompt || `Case ${index + 1}`,
    expected: caseResult.expected || {},
    actual: caseResult.actual || caseResult.agent_output || {}
  };
}

function normalizeA1RunFixtureCase(fixture = {}) {
  const run = fixture.run || {};
  return {
    case_id: fixture.case_id || fixture.name || run.run_id || "a1-run-fixture-case",
    scenario_id: fixture.scenario_id || fixture.name || "a1-run-fixture",
    title: fixture.name || run.task || "A1 run fixture",
    status: run.status || "completed",
    started_at: run.started_at,
    ended_at: run.finished_at,
    expected: fixture.expected || {},
    actual: fixture.replay?.actual || fixture.replay || {},
    observations: Array.isArray(fixture.events) ? fixture.events : [],
    trace_events: Array.isArray(fixture.events) ? fixture.events : [],
    media_evidence: {
      media_types: Array.isArray(fixture.vm_stream) && fixture.vm_stream.length > 0 ? ["vm_stream"] : [],
      evidence_items: [],
      vm_streams: Array.isArray(fixture.vm_stream) ? fixture.vm_stream : []
    },
    metadata: {
      labels: fixture.labels || [],
      source_schema: fixture.schema
    }
  };
}

function normalizeA2RunFixtureCase(fixture = {}) {
  const run = fixture.run || {};
  return {
    case_id: fixture.case_id,
    scenario_id: fixture.scenario_id,
    title: fixture.title || fixture.userTask || fixture.case_id,
    status: fixture.expected?.passed === false ? "failed" : "passed",
    expected: {
      ...objectOr(fixture.expected),
      tool_calls: fixture.expected?.tool_calls || fixture.expected?.expectedToolCalls || []
    },
    actual: {
      final_response: run.final_response || run.text || run.response || "",
      text: run.final_response || run.text || run.response || "",
      tool_calls: Array.isArray(run.tool_calls) ? run.tool_calls : []
    },
    trace_events: Array.isArray(run.trace_events) ? run.trace_events : [],
    observations: Array.isArray(run.observations) ? run.observations : [],
    metadata: {
      source_schema: "a2.single_run_fixture"
    }
  };
}

function normalizeExpected(caseResult = {}, grade = {}) {
  const expected = caseResult.expected || grade.expected || {};
  return {
    ...objectOr(expected),
    text: firstText(expected.text, expected.expected_response, expected.expectedResponse, ""),
    final_response: firstText(expected.final_response, expected.text, expected.expected_response, expected.expectedResponse, ""),
    tool_calls: normalizeToolCallObjects(expected.tool_calls || expected.expectedToolCalls || expected.tools)
  };
}

function normalizeActual(caseResult = {}, grade = {}) {
  const actual = caseResult.actual || grade.actual || {};
  const agentOutput = caseResult.agent_output || {};
  const run = caseResult.run || {};
  const text = firstText(actual.final_response, actual.text, actual.response, agentOutput.text, run.final_response, run.text, "");
  const toolCalls = actual.tool_calls
    || agentOutput.tool_calls
    || run.tool_calls
    || [];
  return {
    ...objectOr(actual),
    text,
    final_response: text,
    tool_calls: normalizeToolCallObjects(toolCalls)
  };
}

function normalizeTraceEvents(caseResult = {}) {
  const direct = caseResult.trace_events || caseResult.events || [];
  const observations = caseResult.observations || [];
  const agentVmLogs = caseResult.agent_output?.vm_stream?.logs || [];
  return [
    ...(Array.isArray(direct) ? direct : []),
    ...(Array.isArray(observations) && direct !== observations ? observations : []),
    ...(Array.isArray(agentVmLogs) ? agentVmLogs : [])
  ];
}

function normalizeMediaEvidence(caseResult = {}, actual = {}) {
  const existing = caseResult.media_evidence || {};
  const vmStreams = [
    ...(Array.isArray(existing.vm_streams) ? existing.vm_streams : []),
    ...(caseResult.agent_output?.vm_stream ? [caseResult.agent_output.vm_stream] : []),
    ...(Array.isArray(caseResult.vm_stream) ? caseResult.vm_stream : [])
  ];
  const mediaTypes = [
    ...(Array.isArray(existing.media_types) ? existing.media_types : []),
    ...(vmStreams.length > 0 ? ["vm_stream"] : [])
  ];
  return {
    ...existing,
    media_types: uniqueValues(mediaTypes),
    evidence_items: Array.isArray(existing.evidence_items) ? existing.evidence_items : [],
    vm_streams: vmStreams
  };
}

function normalizeToolCallObjects(toolCalls) {
  if (!Array.isArray(toolCalls)) {
    return [];
  }
  return toolCalls.map((call) => ({
    ...objectOr(call),
    id: call.id || call.tool_call_id || null,
    name: call.name || call.tool_name || call.tool || "unknown_tool",
    arguments: call.arguments || call.args || call.parameters || {}
  }));
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
  const runs = normalizeRunInputs(runFixture);
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
    capability_axis_targets: mapping(coverageFixture.capability_axis_targets),
    capability_axis_checks: mapping(coverageFixture.capability_axis_checks),
    capability_axis_counts: mapping(coverageFixture.capability_axis_counts),
    capability_axis_scenarios: mapping(coverageFixture.capability_axis_scenarios),
    capability_axis_exemplars: mapping(coverageFixture.capability_axis_exemplars),
    missing_capability_axes: missing(coverageFixture.missing_capability_axes),
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
  const realApi = mapping(evidenceFixture.a1_real_api_evidence);
  const realQuotaGate = mapping(realApi.real_quota_gate);
  const officialReadonly = mapping(evidenceFixture.a1_official_api_readonly_manifest);
  const officialMutating = mapping(evidenceFixture.a1_official_api_mutating_index);
  const officialPaidMedia = mapping(evidenceFixture.a1_official_api_paid_media_summary);
  const officialPaidMediaGuardrails = mapping(officialPaidMedia.guardrails);
  const officialSdkSmoke = mapping(evidenceFixture.official_sdk_smoke);
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
    ashr_reviewed_public_observation_count: ashrMergeGate.reviewed_public_observation_count || 0,
    ashr_missing_public_observation_count: ashrMergeGate.missing_public_observation_count || 0,
    ashr_missing_reviewed_observation_count: ashrMergeGate.missing_reviewed_observation_count || 0,
    ashr_public_merge_blocking_reason: ashrMergeGate.blocking_reason || "",
    real_api_evidence_available: realApi.available === true,
    real_api_total_records: realApi.total_records || 0,
    real_api_record_count: realApi.real_record_count || 0,
    real_api_read_ok_count: mapping(realApi.real_read_status_counts).ok || 0,
    real_api_quota_block_count: realApi.quota_block_count || 0,
    real_api_create_request_blocked: realQuotaGate.create_request_blocked === true,
    real_api_quota_blocked_functions: missing(realQuotaGate.blocked_functions),
    real_api_quota_public_action: realQuotaGate.public_action || "",
    official_api_readonly_available: officialReadonly.available === true,
    official_api_readonly_status: officialReadonly.status || "unknown",
    official_api_readonly_read_step_count: officialReadonly.read_step_count || 0,
    official_api_readonly_ok_or_planned_step_count: officialReadonly.ok_or_planned_step_count || 0,
    official_api_readonly_error_step_count: officialReadonly.error_step_count || 0,
    official_api_readonly_quota_block_count: officialReadonly.quota_block_count || 0,
    official_api_readonly_public_safe: officialReadonly.public_safe === true,
    official_api_readonly_redacted_summary_fields_only: officialReadonly.redacted_summary_fields_only === true,
    official_api_readonly_raw_payload_values_included: officialReadonly.raw_payload_values_included === true,
    official_api_readonly_ready_for_a2_evidence_context: officialReadonly.ready_for_a2_evidence_context === true,
    official_api_readonly_modalities: missing(officialReadonly.modalities),
    official_api_readonly_step_ids: missing(officialReadonly.step_ids),
    official_api_mutating_available: officialMutating.available === true,
    official_api_mutating_public_safe: officialMutating.public_safe === true,
    official_api_mutating_raw_payloads_included: officialMutating.raw_payloads_included === true,
    official_api_mutating_secret_values_included: officialMutating.secret_values_included === true,
    official_api_mutating_record_count: officialMutating.record_count || 0,
    official_api_mutating_status_counts: mapping(officialMutating.status_counts),
    official_api_mutating_modalities: missing(officialMutating.modalities),
    official_api_mutating_step_ids: missing(officialMutating.mutating_step_ids),
    official_api_mutating_observed_error_kinds: missing(officialMutating.observed_error_kinds),
    official_api_mutating_total_steps: officialMutating.total_steps || 0,
    official_api_mutating_read_step_count: officialMutating.read_step_count || 0,
    official_api_mutating_step_count: officialMutating.mutating_step_count || 0,
    official_api_mutating_quota_block_count: officialMutating.quota_block_count || 0,
    official_api_mutating_private_manifest_count: officialMutating.private_manifest_count || 0,
    official_api_mutating_ready_for_a2_evidence_context: officialMutating.ready_for_a2_evidence_context === true,
    official_api_mutating_c3_grading_ready: officialMutating.c3_grading_ready === true,
    official_api_paid_media_available: officialPaidMedia.available === true,
    official_api_paid_media_status: officialPaidMedia.status || "unknown",
    official_api_paid_media_mode: officialPaidMedia.mode || "unknown",
    official_api_paid_media_public_safe: officialPaidMedia.public_safe === true,
    official_api_paid_media_redacted_summary_fields_only: officialPaidMedia.redacted_summary_fields_only === true,
    official_api_paid_media_raw_payload_values_included: officialPaidMedia.raw_payload_values_included === true,
    official_api_paid_media_guardrails: officialPaidMediaGuardrails,
    official_api_paid_media_total_step_count: officialPaidMedia.total_step_count || 0,
    official_api_paid_media_read_step_count: officialPaidMedia.read_step_count || 0,
    official_api_paid_media_mutating_step_count: officialPaidMedia.mutating_step_count || 0,
    official_api_paid_media_ok_or_planned_step_count: officialPaidMedia.ok_or_planned_step_count || 0,
    official_api_paid_media_error_step_count: officialPaidMedia.error_step_count || 0,
    official_api_paid_media_quota_block_count: officialPaidMedia.quota_block_count || 0,
    official_api_paid_media_estimated_call_count: officialPaidMedia.estimated_call_count || 0,
    official_api_paid_media_modalities: missing(officialPaidMedia.modalities),
    official_api_paid_media_step_ids: missing(officialPaidMedia.step_ids),
    official_api_paid_media_mutating_functions: missing(officialPaidMedia.mutating_functions),
    official_api_paid_media_mutating_modalities: missing(officialPaidMedia.mutating_modalities),
    official_api_paid_media_quota_blocked_step_ids: missing(officialPaidMedia.quota_blocked_step_ids),
    official_api_paid_media_quota_remaining_observed: officialPaidMedia.quota_remaining_observed === true,
    official_api_paid_media_status_code_counts: mapping(officialPaidMedia.status_code_counts),
    official_api_paid_media_ready_for_a2_evidence_context: officialPaidMedia.ready_for_a2_evidence_context === true,
    official_api_paid_media_safe_for_paid_media_claims: officialPaidMedia.safe_for_paid_media_claims === true,
    official_api_paid_media_c3_grading_ready: officialPaidMedia.c3_grading_ready === true,
    official_sdk_smoke_available: officialSdkSmoke.available === true,
    official_sdk_smoke_read_only_reachable: officialSdkSmoke.read_only_reachable === true,
    official_sdk_smoke_ok_call_count: officialSdkSmoke.ok_call_count || 0,
    official_sdk_smoke_error_call_count: officialSdkSmoke.error_call_count || 0,
    official_sdk_smoke_call_names: missing(officialSdkSmoke.call_names),
    semantic_offline_reference_only: semantic.offline_reference_only === true,
    semantic_expected_reviewed_observation_count: semantic.expected_reviewed_observation_count || 0,
    semantic_reviewed_live_observation_count: semantic.reviewed_live_observation_count || 0,
    semantic_missing_reviewed_live_observation_count: semantic.missing_reviewed_live_observation_count || 0,
    semantic_reviewed_live_sdk_languages: missing(semantic.reviewed_live_sdk_languages),
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
    semantic_live_reviewed_observation_count: semanticMergeGate.reviewed_live_observation_count || 0,
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
    reviewed_evidence_target_count: caseBookGate.reviewed_evidence_target_count || replayGate.reviewed_evidence_target_count || 0,
    reviewed_external_evidence_count: caseBookGate.reviewed_external_evidence_count || candidatePool.reviewed_external_evidence_count || 0,
    review_evidence_ready: caseBookGate.review_evidence_ready === true,
    case_book_maturity_ready: replayGate.case_book_maturity_ready === true,
    local_llm_mismatch_count: candidatePool.local_llm_mismatch_count || 0,
    ashr_grading_missing_count: candidatePool.ashr_grading_missing_count || 0,
    gaps: [...missing(caseBookGate.gaps), ...missing(replayGate.gaps)]
  };
}

export function summarizeCommercialReadiness(commercialFixture = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const available = isObject(commercialFixture) && Object.keys(commercialFixture).length > 0;
  const snapshot = mapping(commercialFixture.evidence_snapshot);
  const gateStatus = missing(commercialFixture.gate_status);
  const statusCounts = gateStatus.reduce((counts, gate) => {
    const status = gate && typeof gate.status === "string" ? gate.status : "unknown";
    return { ...counts, [status]: (counts[status] || 0) + 1 };
  }, {});

  return {
    available,
    schema_version: available ? commercialFixture.schema_version || "unknown" : "none",
    report_id: available ? commercialFixture.report_id || "unknown" : "none",
    current_gate: commercialFixture.current_gate || "none",
    ready_for_commercial_gate: commercialFixture.ready_for_commercial_gate === true,
    gate_count: gateStatus.length,
    gate_status_counts: statusCounts,
    partial_gate_ids: gateStatus.filter((gate) => gate.status === "partial").map((gate) => gate.gate).filter(Boolean),
    blocked_gate_ids: gateStatus.filter((gate) => gate.status === "blocked").map((gate) => gate.gate).filter(Boolean),
    next_top_3_ids: missing(commercialFixture.next_top_3).map((item) => item.id).filter(Boolean),
    scope_boundary_status: mapping(commercialFixture.scope_boundary).status || "unknown",
    assignment_minimums_green: snapshot.assignment_minimums_green === true,
    scenario_count: snapshot.scenario_count || 0,
    golden_case_count: snapshot.golden_case_count || 0,
    failure_class_count: snapshot.failure_class_count || 0,
    real_api_total_records: snapshot.real_api_total_records || 0,
    real_api_record_count: snapshot.real_api_record_count || 0,
    real_api_quota_block_count: snapshot.real_api_quota_block_count || 0,
    real_api_create_request_blocked: snapshot.real_api_create_request_blocked === true,
    official_sdk_smoke_read_only_reachable: snapshot.official_sdk_smoke_read_only_reachable === true,
    official_sdk_smoke_ok_call_count: snapshot.official_sdk_smoke_ok_call_count || 0,
    official_sdk_smoke_error_call_count: snapshot.official_sdk_smoke_error_call_count || 0,
    ashr_public_merge_status: snapshot.ashr_public_merge_status || "unknown",
    semantic_live_merge_status: snapshot.semantic_live_merge_status || "unknown",
    regression_replay_maturity: snapshot.regression_replay_maturity || "unknown"
  };
}

export function summarizeA2ResultPersistence(resultPersistenceFixture = {}) {
  const available = isObject(resultPersistenceFixture) && Object.keys(resultPersistenceFixture).length > 0;
  const metadata = objectOr(resultPersistenceFixture.metadata);
  const records = Array.isArray(resultPersistenceFixture.records) ? resultPersistenceFixture.records : [];
  const releaseGateRecords = records.filter((record) => record.record_type === "release_gate");
  const scenarioSelectionRecords = records.filter((record) => record.record_type === "scenario_selection");
  const releaseUnblockChecklistRecords = records.filter((record) => record.record_type === "release_unblock_checklist");
  const a1IngestionDigestRecords = records.filter((record) => record.record_type === "a1_ingestion_digest");
  const judgeRecords = records.filter((record) => record.record_type === "judge_result");
  const safetyBlockingRecords = judgeRecords.filter((record) => record.safety_blocking === true);
  const failedJudgeRecords = judgeRecords.filter((record) => record.passed === false);
  const recordTypeCounts = Object.keys(objectOr(resultPersistenceFixture.record_type_counts)).length
    ? objectOr(resultPersistenceFixture.record_type_counts)
    : records.reduce((counts, record) => ({
      ...counts,
      [record.record_type || "unknown"]: (counts[record.record_type || "unknown"] || 0) + 1
    }), {});

  return {
    available,
    schema_version: available ? resultPersistenceFixture.schema_version || "unknown" : "none",
    manifest_id: resultPersistenceFixture.manifest_id || "none",
    tenant_id: resultPersistenceFixture.tenant_id || resultPersistenceFixture.org || "unknown",
    project: resultPersistenceFixture.project || "unknown",
    run: resultPersistenceFixture.run || "unknown",
    dataset_id: resultPersistenceFixture.dataset_id || null,
    record_count: resultPersistenceFixture.record_count || records.length,
    record_type_counts: recordTypeCounts,
    judge_result_count: judgeRecords.length,
    failed_judge_result_count: failedJudgeRecords.length,
    safety_blocking_result_count: safetyBlockingRecords.length,
    release_gate_record_count: releaseGateRecords.length,
    scenario_selection_record_count: scenarioSelectionRecords.length,
    release_unblock_checklist_record_count: releaseUnblockChecklistRecords.length,
    a1_ingestion_digest_record_count: a1IngestionDigestRecords.length,
    source_refs: objectOr(resultPersistenceFixture.source_refs),
    public_safe: metadata.public_safe === true,
    canonical_json_hashing: metadata.canonical_json_hashing === true,
    raw_private_evidence_not_recorded: metadata.raw_private_evidence_not_recorded === true,
    secrets_not_recorded: metadata.secrets_not_recorded === true,
    intended_consumers: Array.isArray(metadata.intended_consumers) ? metadata.intended_consumers : [],
    latest_records: records.slice(-5).map((record) => ({
      record_type: record.record_type,
      case_id: record.case_id,
      scenario_id: record.scenario_id,
      judge_id: record.judge_id,
      judge_version: record.judge_version,
      passed: record.passed,
      score: record.score,
      primary_failure_class: record.primary_failure_class,
      safety_blocking: record.safety_blocking === true,
      decision: record.decision || null,
      exit_code: record.exit_code ?? null,
      risk_score: record.risk_score ?? null,
      overall_status: record.overall_status || null,
      blocked_gate_count: record.blocked_gate_count ?? record.blocking_gate_count ?? null,
      release_gate_decision: record.release_gate_decision || null,
      release_gate_risk_score: record.release_gate_risk_score ?? null,
      gate_count: record.gate_count ?? null,
      private_evidence_required: record.private_evidence_required === true,
      selected_count: record.selected_count ?? null,
      selection_id: record.selection_id || null,
      upload_id: record.upload_id || null,
      trace_batch_id: record.trace_batch_id || null,
      output_hash: record.output_hash
    })),
    recommendation: available
      ? "Use the A2 result persistence manifest as the audit bridge between judge outputs, release gate decisions, and A3 report exports."
      : "Attach A2 result persistence manifest before claiming judge and release-gate evidence is durable."
  };
}

export function summarizeA2ReleaseUnblockChecklist(unblockFixture = {}) {
  const available = isObject(unblockFixture) && Object.keys(unblockFixture).length > 0;
  const gateItems = Array.isArray(unblockFixture.gate_items) ? unblockFixture.gate_items : [];
  const a3Summary = objectOr(unblockFixture.a3_consumption_summary);
  const reviewWorkflow = objectOr(unblockFixture.review_workflow);
  const blockingItems = gateItems.filter((item) => item.blocks_release === true);
  const requiredActions = gateItems.flatMap((item) => (
    Array.isArray(item.required_actions)
      ? item.required_actions.map((action) => ({ ...action, gate: item.gate, owner_role: item.owner_role }))
      : []
  ));
  const privateEvidenceActions = requiredActions.filter((action) => action.private_evidence_required === true);

  return {
    available,
    schema_version: available ? unblockFixture.schema_version || "unknown" : "none",
    checklist_id: unblockFixture.checklist_id || "none",
    source_release_gate: unblockFixture.source_release_gate || "unknown",
    overall_status: unblockFixture.overall_status || "unknown",
    release_gate_decision: unblockFixture.release_gate_decision || "unknown",
    release_gate_exit_code: unblockFixture.release_gate_exit_code ?? null,
    release_gate_risk_score: unblockFixture.release_gate_risk_score ?? null,
    blocked_gate_count: unblockFixture.blocked_gate_count || blockingItems.length,
    blocking_gate_ids: blockingItems.map((item) => item.gate).filter(Boolean),
    dashboard_sections: Array.isArray(a3Summary.dashboard_sections) ? a3Summary.dashboard_sections : [],
    primary_action: a3Summary.primary_action || requiredActions[0]?.action || "",
    required_reviewer_roles: Array.isArray(reviewWorkflow.required_reviewers) ? reviewWorkflow.required_reviewers : [],
    required_action_count: requiredActions.length,
    private_evidence_required_count: privateEvidenceActions.length,
    evidence_refs: Array.isArray(unblockFixture.evidence_refs) ? unblockFixture.evidence_refs : [],
    gate_items: gateItems.map((item) => ({
      gate: item.gate,
      title: item.title,
      status: item.status,
      blocks_release: item.blocks_release === true,
      owner_role: item.owner_role,
      missing_count: item.missing_count || 0,
      required_action_count: Array.isArray(item.required_actions) ? item.required_actions.length : 0,
      evidence_refs: Array.isArray(item.evidence_refs) ? item.evidence_refs : []
    })),
    next_unblock_actions: requiredActions.slice(0, 5).map((action) => ({
      gate: action.gate,
      action_id: action.action_id,
      action: action.action,
      owner_role: action.owner_role,
      private_evidence_required: action.private_evidence_required === true,
      missing_count: action.missing_count || 0
    })),
    safety: {
      public_safe: unblockFixture.metadata?.public_safe === true,
      deterministic: unblockFixture.metadata?.deterministic === true,
      does_not_execute_live_calls: unblockFixture.metadata?.does_not_execute_live_calls === true,
      does_not_read_private_evidence: unblockFixture.metadata?.does_not_read_private_evidence === true
    },
    recommendation: available
      ? "Show this checklist beside A3 release gate and reviewer workflow so owners know exactly what evidence must be reviewed before unblocking."
      : "Attach A2 release unblock checklist before claiming blocked releases have an auditable unblock path."
  };
}

export function summarizeA2CrossLaneSecurityContext(securityFixture = {}) {
  const available = isObject(securityFixture) && Object.keys(securityFixture).length > 0;
  const a1RouteScope = objectOr(securityFixture.a1_route_scope);
  const a3AuthRbac = objectOr(securityFixture.a3_auth_rbac_boundary);
  const policy = objectOr(securityFixture.a2_policy_implications);
  const followups = Array.isArray(securityFixture.a2_security_followups) ? securityFixture.a2_security_followups : [];
  const metadata = objectOr(securityFixture.metadata);

  return {
    available,
    schema_version: available ? securityFixture.schema_version || "unknown" : "none",
    report_id: securityFixture.report_id || "none",
    source_refs: objectOr(securityFixture.source_refs),
    a1_route_scope_available: a1RouteScope.available === true,
    a1_route_scope_ready_for_a2_security_context: a1RouteScope.ready_for_a2_security_context === true,
    a1_route_scope_schema_version: a1RouteScope.schema_version || "unknown",
    a3_auth_rbac_available: a3AuthRbac.available === true,
    a3_auth_rbac_ready_for_a2_security_context: a3AuthRbac.ready_for_a2_security_context === true,
    a3_auth_rbac_schema_version: a3AuthRbac.schema_version || "unknown",
    should_block_hosted_mutations_without_a1_auth: policy.should_block_hosted_mutations_without_a1_auth === true,
    should_require_metadata_only_audit_events: policy.should_require_metadata_only_audit_events === true,
    should_keep_raw_actor_identity_forbidden: policy.should_keep_raw_actor_identity_forbidden === true,
    should_add_route_scope_security_cases: policy.should_add_route_scope_security_cases === true,
    should_add_auth_rbac_abuse_cases: policy.should_add_auth_rbac_abuse_cases === true,
    release_policy_refs: Array.isArray(policy.release_policy_refs) ? policy.release_policy_refs : [],
    followup_count: followups.length,
    blocking_followup_count: followups.filter((item) => item.requires_user_decision === true).length,
    followups: followups.slice(0, 5).map((item) => ({
      followup_id: item.followup_id,
      action: item.action,
      owner: item.owner,
      tags: Array.isArray(item.tags) ? item.tags : [],
      writes_private_evidence: item.writes_private_evidence === true,
      requires_user_decision: item.requires_user_decision === true
    })),
    safety: {
      public_safe: metadata.public_safe === true,
      deterministic: metadata.deterministic === true,
      requires_network: metadata.requires_network === true,
      requires_ashr_api_key: metadata.requires_ashr_api_key === true,
      does_not_execute_live_calls: metadata.does_not_execute_live_calls === true,
      does_not_read_private_evidence: metadata.does_not_read_private_evidence === true,
      raw_private_evidence_not_recorded: metadata.raw_private_evidence_not_recorded === true,
      secrets_not_recorded: metadata.secrets_not_recorded === true
    },
    recommendation: available
      ? "Use this A2 cross-lane security context to keep A3 hosted mutations, audit events, actor redaction, and RBAC abuse cases aligned with A1/A2 security evidence."
      : "Attach A2 cross-lane security context before claiming A3 SaaS write paths are security-reviewed across lanes."
  };
}

export function summarizeA2SqlStoreReport(sqlFixture = {}) {
  const available = isObject(sqlFixture) && Object.keys(sqlFixture).length > 0;
  const database = objectOr(sqlFixture.database);
  const queryChecks = objectOr(sqlFixture.query_checks);
  const metadata = objectOr(sqlFixture.metadata);

  return {
    available,
    schema_version: available ? sqlFixture.schema_version || "unknown" : "none",
    report_id: sqlFixture.report_id || "none",
    database_engine: database.engine || "unknown",
    reference_dialect: database.reference_dialect || "unknown",
    production_target: database.production_target || "unknown",
    ddl_version: database.ddl_version || "unknown",
    ddl_ref: database.ddl_ref || "",
    table_counts: objectOr(sqlFixture.table_counts),
    write_counts: objectOr(sqlFixture.write_counts),
    source_refs: objectOr(sqlFixture.source_refs),
    failure_class_counts: objectOr(queryChecks.failure_class_counts),
    golden_failure_class_counts: objectOr(queryChecks.golden_failure_class_counts),
    calibration_missing_ashr_count: queryChecks.calibration_missing_ashr_count || 0,
    calibration_disagreement_count: queryChecks.calibration_disagreement_count || 0,
    regression_replay_status_counts: objectOr(queryChecks.regression_replay_status_counts),
    can_join_case_level_history: queryChecks.can_join_case_level_history === true,
    table_count_total: Object.values(objectOr(sqlFixture.table_counts)).reduce((sum, value) => sum + (Number(value) || 0), 0),
    write_count_total: Object.values(objectOr(sqlFixture.write_counts)).reduce((sum, value) => sum + (Number(value) || 0), 0),
    safety: {
      public_safe: metadata.public_safe === true,
      uses_python_stdlib_sqlite: metadata.uses_python_stdlib_sqlite === true,
      does_not_require_external_database: metadata.does_not_require_external_database === true,
      does_not_execute_live_calls: metadata.does_not_execute_live_calls === true,
      raw_private_evidence_not_recorded: metadata.raw_private_evidence_not_recorded === true,
      secrets_not_recorded: metadata.secrets_not_recorded === true,
      intended_consumers: Array.isArray(metadata.intended_consumers) ? metadata.intended_consumers : []
    },
    recommendation: available
      ? "Use this A2 SQL store report as the bridge from mock fixture evidence toward DB-backed judge history, failure analytics, and SaaS audit export."
      : "Attach A2 SQL store report before claiming A2 judge evidence is queryable as durable DB data."
  };
}

function normalizeA2ReadinessArgs(requestFixture = {}, usageFixture = {}, usageApiProbe = {}, bundle = {}, releaseGateCandidate = {}) {
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const schema = (value) => isObject(value) ? String(value.schema_version || "") : "";
  const explicit = isObject(bundle) ? bundle : {};
  const legacyA2Args = schema(requestFixture).includes("case_book")
    || schema(usageFixture).includes("regression")
    || schema(usageApiProbe).includes("commercial_readiness")
    || schema(releaseGateCandidate).includes("release_gate");

  return {
    legacyA2Args,
    caseBookFixture: explicit.caseBook || explicit.case_book || (legacyA2Args ? requestFixture : {}),
    regressionReplayFixture: explicit.regressionReplay || explicit.regression_replay || (legacyA2Args ? usageFixture : {}),
    commercialReadinessFixture: explicit.commercialReadiness || explicit.commercial_readiness || (legacyA2Args ? usageApiProbe : {}),
    releaseGateFixture: explicit.releaseGate || explicit.release_gate || (legacyA2Args ? releaseGateCandidate : {}),
    resultPersistenceFixture: explicit.resultPersistence || explicit.result_persistence || explicit.resultPersistenceManifest || explicit.result_persistence_manifest || {},
    releaseUnblockChecklistFixture: explicit.releaseUnblockChecklist || explicit.release_unblock_checklist || {},
    crossLaneSecurityContextFixture: explicit.crossLaneSecurityContext || explicit.cross_lane_security_context || {},
    sqlStoreReportFixture: explicit.sqlStoreReport || explicit.sql_store_report || {}
  };
}

function isA2ReadinessBundle(value = {}) {
  const schema = isObject(value) ? String(value.schema_version || "") : "";
  if (schema.startsWith("a3.")) {
    return false;
  }
  return isObject(value) && (
    isObject(value.caseBook)
    || isObject(value.case_book)
    || isObject(value.regressionReplay)
    || isObject(value.regression_replay)
    || isObject(value.commercialReadiness)
    || isObject(value.commercial_readiness)
    || isObject(value.releaseGate)
    || isObject(value.release_gate)
    || isObject(value.resultPersistence)
    || isObject(value.result_persistence)
    || isObject(value.resultPersistenceManifest)
    || isObject(value.result_persistence_manifest)
    || isObject(value.releaseUnblockChecklist)
    || isObject(value.release_unblock_checklist)
    || isObject(value.crossLaneSecurityContext)
    || isObject(value.cross_lane_security_context)
    || isObject(value.sqlStoreReport)
    || isObject(value.sql_store_report)
  );
}

export function summarizeRequestProvenance(requestFixture = {}) {
  const requests = extractRequestObjects(requestFixture);
  const statusCounts = requests.reduce((counts, request) => {
    const status = request.request_status || request.status || "unknown";
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
  const latestRequest = [...requests].sort((left, right) => (
    Date.parse(right.created_at || right.completed_at || "") - Date.parse(left.created_at || left.completed_at || "")
  ))[0] || null;

  if (!latestRequest) {
    return {
      available: false,
      total_requests: 0,
      status_counts: {},
      latest_request: null
    };
  }

  const requestBody = latestRequest.request || {};
  const acceptedInputs = objectOr(requestBody.agent?.accepted_inputs);
  const generationOptions = objectOr(requestBody.generation_options);
  const testConfig = objectOr(requestBody.test_config);
  const tools = Array.isArray(requestBody.agent?.tools)
    ? requestBody.agent.tools
    : Array.isArray(latestRequest.request_input_schema?.tools)
      ? latestRequest.request_input_schema.tools
      : [];

  return {
    available: true,
    total_requests: requests.length,
    status_counts: statusCounts,
    latest_request: {
      request_id: firstText(latestRequest.id, latestRequest.request_id, "unknown_request"),
      request_name: firstText(latestRequest.request_name, requestBody.metadata?.dataset_name, "unnamed request"),
      request_status: firstText(latestRequest.request_status, latestRequest.status, "unknown"),
      created_at: latestRequest.created_at || "",
      completed_at: latestRequest.completed_at || "",
      actual_duration_s: numberOrNull(latestRequest.actual_duration_s),
      estimated_duration_s: numberOrNull(latestRequest.estimated_duration_s),
      has_failure: Boolean(requestBody._failure) || latestRequest.request_status === "failed",
      accepted_input_types: truthyKeys(acceptedInputs),
      generation_outputs: truthyKeys(generationOptions),
      test_strategy: firstText(testConfig.strategy, "unknown"),
      num_variations: numberOrNull(testConfig.num_variations),
      coverage: objectOr(testConfig.coverage),
      tool_count: tools.length,
      output_format: firstText(requestBody.agent?.output_format?.type, "unknown"),
      context_keys: Object.keys(objectOr(requestBody.context)).sort()
    }
  };
}

export function summarizeUsageQuota(usageFixture = {}, usageApiProbe = {}) {
  const frontendModules = Array.isArray(usageFixture.frontend_known_modules)
    ? usageFixture.frontend_known_modules
    : [];
  const apiPaths = objectOr(usageFixture.api_paths);
  const apiProbeCalls = objectOr(usageApiProbe.calls);
  const apiProbeFieldPaths = objectOr(usageApiProbe.field_paths);
  const apiFunctions = Array.isArray(usageApiProbe.frontend_source_functions)
    ? usageApiProbe.frontend_source_functions
    : [];
  const channels = uniqueSorted([
    ...frontendModules,
    ...Object.keys(apiPaths),
    ...Object.keys(apiProbeFieldPaths)
  ].flatMap((value) => usageQuotaChannelsFromText(value)));
  const apiCallStatuses = Object.fromEntries(Object.entries(apiProbeCalls).map(([name, call]) => [
    name,
    {
      ok: call?.ok === true,
      status_code: numberOrNull(call?.status_code),
      error: firstText(call?.error?.message, "")
    }
  ]));
  const directApiAccessible = Object.values(apiCallStatuses).some((call) => call.ok);
  const oauthOnlyFunctions = Object.entries(apiCallStatuses)
    .filter(([, call]) => call.status_code === 403 && /oauth/i.test(call.error))
    .map(([name]) => name)
    .sort();

  return {
    available: frontendModules.length > 0 || Object.keys(apiPaths).length > 0 || Object.keys(apiProbeCalls).length > 0,
    frontend_modules: frontendModules,
    channels,
    api_confirmed: usageFixture.api_confirmed === true || Object.keys(apiPaths).length > 0,
    api_path_count: Object.keys(apiPaths).length + Object.keys(apiProbeFieldPaths).length,
    frontend_source_functions: uniqueSorted([...apiFunctions, ...Object.keys(apiProbeCalls)]),
    direct_api_accessible: directApiAccessible,
    oauth_only_functions: oauthOnlyFunctions,
    api_call_statuses: apiCallStatuses,
    guidance: directApiAccessible
      ? "Usage/quota fields can be mapped from the API probe."
      : oauthOnlyFunctions.length
        ? "Usage/quota counters are visible in the official frontend, but direct API-key access is OAuth-gated."
        : "Usage/quota remains a frontend-confirmed product concept without a direct API-key sample."
  };
}

export function summarizeBillingUsage(runFixture = {}, gradeFixture = {}, usageFixture = {}, usageApiProbe = {}, options = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const evidenceCounts = buildBillingEvidenceCounts(summary, cases);
  const defaultMeters = buildBillingUsageMeters(summary, cases);
  const optionMeters = Array.isArray(options.meters) ? options.meters : [];
  const meters = mergeBillingMeters(defaultMeters, optionMeters);
  const billableMeters = meters.filter((item) => item.billable);
  const billableUnitCount = billableMeters.reduce((sum, item) => sum + item.billable_units, 0);
  const plan = resolveBillingPlan(usageFixture, usageQuota, options);
  const quota = resolveBillingQuota(usageFixture, options, billableUnitCount, plan);
  const overageRisk = classifyOverageRisk(quota, plan);
  const primaryBillableMeter = billableMeters.find((item) => item.meter === "cases")
    || billableMeters.find((item) => item.quantity > 0)
    || null;

  return {
    schema_version: "a3.billing_usage_summary.v1",
    available: summary.totalRuns > 0 || summary.totalCases > 0 || usageQuota.available || optionMeters.length > 0,
    status: "read_only_commercial_summary",
    billing_mutations_enabled: false,
    plan,
    quota,
    billable_meter: primaryBillableMeter,
    billable_meters: billableMeters,
    billable_unit_count: billableUnitCount,
    meter_count: meters.length,
    meters,
    overage_risk: overageRisk,
    usage_quota_observed: usageQuota.available,
    usage_quota_direct_api_accessible: usageQuota.direct_api_accessible,
    oauth_only_functions: usageQuota.oauth_only_functions,
    evidence_counts: evidenceCounts,
    commercial_guidance: overageRisk.status === "over_quota"
      ? "Usage is over the included quota; keep A3 in read-only display mode until A1 billing enforcement and customer plan controls are live."
      : "Show plan, quota, and billable usage as customer-visible read-only evidence; do not mutate billing state from A3."
  };
}

export function summarizeBillingMigrationReadiness(billingMigrationFixture = {}) {
  const available = billingMigrationFixture?.schema_version === "a3.billing_migration_readiness.v1"
    || Boolean(billingMigrationFixture?.summary || billingMigrationFixture?.db_contract || billingMigrationFixture?.upstream_evidence);
  if (!available) {
    return {
      schema_version: "a3.billing_migration_readiness_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach a3.billing_migration_readiness.v1 before claiming billing ledger migration readiness in customer reports."
    };
  }

  const summary = objectOr(billingMigrationFixture.summary);
  const upstreamEvidence = objectOr(billingMigrationFixture.upstream_evidence);
  const durableMigration = objectOr(upstreamEvidence.durable_billing_ledger_migration);
  const replayEvidence = objectOr(upstreamEvidence.replay_evidence);
  const liveSmoke = objectOr(upstreamEvidence.live_smoke);
  const officialReadonly = objectOr(upstreamEvidence.official_api_readonly_summary);
  const dbContract = objectOr(billingMigrationFixture.db_contract);
  const eventContract = objectOr(billingMigrationFixture.event_contract);
  const artifactContract = objectOr(billingMigrationFixture.artifact_contract);
  const boundary = objectOr(billingMigrationFixture.tenant_auth_rbac_usage_audit);
  const tenantBoundary = objectOr(boundary.tenant);
  const authBoundary = objectOr(boundary.auth);
  const rbacBoundary = objectOr(boundary.rbac);
  const usageBoundary = objectOr(boundary.usage);
  const auditBoundary = objectOr(boundary.audit);
  const safety = objectOr(billingMigrationFixture.safety);
  const consumerState = objectOr(billingMigrationFixture.a3_consumer_state);
  const blockedForLiveBilling = Array.isArray(consumerState.blocked_for_live_customer_billing)
    ? consumerState.blocked_for_live_customer_billing
    : [];
  const notClaimedByA3 = Array.isArray(consumerState.not_claimed_by_a3)
    ? consumerState.not_claimed_by_a3
    : [];
  const tables = Array.isArray(dbContract.tables) ? dbContract.tables : [];
  const apiContracts = Array.isArray(billingMigrationFixture.api_contract) ? billingMigrationFixture.api_contract : [];
  const upstreamCommits = Array.isArray(billingMigrationFixture.upstream_commits) ? billingMigrationFixture.upstream_commits : [];
  const missingControls = summary.ready_for_live_customer_billing === true
    ? []
    : [
      "a1_authenticated_billing_ledger_read_api",
      "hosted_auth_rbac_enforcement",
      "a1_provider_webhook_executor",
      "live_billing_readback_receipts"
    ];

  const exportSummary = {
    schema_version: "a3.billing_migration_readiness_export.v1",
    source_schema_version: billingMigrationFixture.schema_version || "unknown",
    available: true,
    contract_id: billingMigrationFixture.contract_id || "unknown",
    contract_hash_prefix: hashPrefix(billingMigrationFixture.contract_hash || ""),
    source_branch: billingMigrationFixture.source_branch || "unknown",
    status: summary.status || "unknown",
    ready_for_live_customer_billing: summary.ready_for_live_customer_billing === true,
    consumed_evidence_count: summary.consumed_evidence_count || 0,
    upstream_commit_count: summary.upstream_commit_count || upstreamCommits.length,
    upstream_commits: upstreamCommits.map((commit) => ({
      sha: commit.sha || "unknown",
      evidence_kind: commit.evidence_kind || "unknown",
      a3_consumption_status: commit.a3_consumption_status || "unknown"
    })),
    consumed_states: objectOr(summary.consumed_states),
    customer_claim: summary.a3_customer_claim || "Billing migration readiness is available as read-only A3 evidence only.",
    db_contract: {
      durable_backend_owner: dbContract.durable_backend_owner || "unknown",
      a3_db_mutation_required: dbContract.a3_db_mutation_required === true,
      migration_manifest_schema: dbContract.migration_manifest_schema || durableMigration.source_schema_version || "unknown",
      table_names: tables.map((table) => table.name).filter(Boolean),
      table_count: tables.length,
      function_names: (Array.isArray(dbContract.functions) ? dbContract.functions : [])
        .map((item) => item.name)
        .filter(Boolean),
      rls_enabled_and_forced: dbContract.required_safety?.rls_enabled_and_forced === true,
      raw_payload_column_allowed: dbContract.required_safety?.raw_payload_column_allowed === true,
      raw_provider_secret_allowed: dbContract.required_safety?.raw_provider_secret_allowed === true
    },
    replay_evidence: {
      provider_event_count: replayEvidence.provider_event_count || 0,
      ledger_event_count: replayEvidence.ledger_event_count || 0,
      usage_units: replayEvidence.usage_units || 0,
      replay_statuses_observed: Array.isArray(replayEvidence.replay_statuses_observed) ? replayEvidence.replay_statuses_observed : [],
      ledger_event_types_observed: Array.isArray(replayEvidence.ledger_event_types_observed) ? replayEvidence.ledger_event_types_observed : [],
      raw_payload_included: replayEvidence.raw_payload_included === true,
      secret_value_present: replayEvidence.secret_value_present === true
    },
    live_smoke: {
      execution_model: liveSmoke.execution_model || "unknown",
      executed_by_a3: liveSmoke.executed_by_a3 === true,
      replay_statuses_expected: Array.isArray(liveSmoke.replay_statuses_expected) ? liveSmoke.replay_statuses_expected : []
    },
    official_api_readonly: {
      status: officialReadonly.status || "unknown",
      read_steps: officialReadonly.read_steps || 0,
      mutating_steps: officialReadonly.mutating_steps || 0,
      public_summary_fields_only: officialReadonly.public_summary_fields_only === true
    },
    api_contracts: apiContracts.map((route) => ({
      route: route.route || "unknown",
      owner_lane: route.owner_lane || "unknown",
      status: route.status || "unknown",
      a3_side_effect: route.a3_side_effect || "unknown"
    })),
    event_contract: {
      event_envelope_schema: eventContract.event_envelope_schema || "unknown",
      provider_event_type_count: Array.isArray(eventContract.provider_event_types) ? eventContract.provider_event_types.length : 0,
      ledger_event_types: Array.isArray(eventContract.ledger_event_types) ? eventContract.ledger_event_types : [],
      replay_statuses: Array.isArray(eventContract.replay_statuses) ? eventContract.replay_statuses : [],
      payload_policy: eventContract.payload_policy || "hashes, refs, statuses, counts, and normalized totals only"
    },
    artifact_contract: {
      upstream_input_count: Array.isArray(artifactContract.upstream_inputs) ? artifactContract.upstream_inputs.length : 0,
      a3_output_count: Array.isArray(artifactContract.a3_outputs) ? artifactContract.a3_outputs.length : 0,
      retention_policy: artifactContract.retention_policy || "public-safe contract artifacts only"
    },
    boundary: {
      tenant_scope_keys: Array.isArray(tenantBoundary.required_scope) ? tenantBoundary.required_scope : [],
      auth_raw_credentials_allowed: authBoundary.raw_credentials_allowed === true,
      read_roles: Array.isArray(rbacBoundary.read_roles) ? rbacBoundary.read_roles : [],
      a3_mutation_roles_enabled: Array.isArray(rbacBoundary.a3_mutation_roles_enabled) ? rbacBoundary.a3_mutation_roles_enabled : [],
      usage_source_of_truth: usageBoundary.source_of_truth || "A1 billing ledger and usage rollups",
      billable_meters: Array.isArray(usageBoundary.billable_meters) ? usageBoundary.billable_meters : [],
      billing_mutations_enabled: usageBoundary.billing_mutations_enabled === true,
      audit_append_only_required: auditBoundary.append_only_required === true,
      audit_raw_payload_logged: auditBoundary.raw_payload_logged === true
    },
    safety: {
      env_local_read: safety.env_local_read === true,
      real_api_called_by_a3: safety.real_api_called_by_a3 === true,
      live_database_migration_run_by_a3: safety.live_database_migration_run_by_a3 === true,
      real_payment_provider_called: safety.real_payment_provider_called === true,
      billing_mutation_performed_by_a3: safety.billing_mutation_performed_by_a3 === true,
      provider_secret_values_included: safety.provider_secret_values_included === true,
      raw_provider_payload_included: safety.raw_provider_payload_included === true,
      raw_card_data_included: safety.raw_card_data_included === true,
      raw_customer_email_included: safety.raw_customer_email_included === true,
      raw_signed_urls_included: safety.raw_signed_urls_included === true
    },
    missing_controls: missingControls,
    blocked_for_live_customer_billing: blockedForLiveBilling,
    not_claimed_by_a3: notClaimedByA3,
    customer_value: "Shows buyers billing-ledger migration readiness without exposing provider secrets or claiming live payment mutations.",
    billable_value: "Maps future invoice-preview and usage-unit meters while keeping A3 billing mutations disabled.",
    self_host_value: "Preserves A1-owned Postgres migration, RLS, and table/function contract as self-host deployment evidence.",
    audit_value: "Records hash-only provider-event, replay-status, tenant-scope, RBAC, and no-raw-payload controls for audit packets.",
    recommendation: "Use this report section as customer-safe migration evidence until A1 exposes authenticated billing ledger read APIs and live receipts."
  };
  return redactExport(exportSummary, { surface: "billing_migration_readiness_summary" }).value;
}

export function summarizeMediaReadiness(runFixture = {}, gradeFixture = {}, usageFixture = {}, mediaSignedUrlFixture = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const mediaCases = cases.filter(hasMediaEvidence);
  const evidenceItems = mediaCases.flatMap((item) => item.media_evidence?.evidence_items || []);
  const vmStreams = mediaCases.flatMap((item) => item.media_evidence?.vm_streams || []);
  const usageChannels = summarizeUsageQuota(usageFixture, {}).channels;
  const signedUrlByType = objectOr(mediaSignedUrlFixture.signed_url_by_nearest_type);
  const outputPathByType = objectOr(mediaSignedUrlFixture.output_path_by_nearest_type);
  const acceptedInputFlags = objectOr(mediaSignedUrlFixture.accepted_input_flags);
  const generationOutputFlags = objectOr(mediaSignedUrlFixture.generation_output_flags);
  const conclusion = objectOr(mediaSignedUrlFixture.conclusion);
  const rawMediaTypes = [
    ...usageChannels,
    ...mediaCases.flatMap((item) => item.media_evidence?.media_types || []),
    ...mediaCases.map((item) => item.media_evidence?.primary_media_type),
    ...evidenceItems.map((item) => item.type),
    ...Object.keys(signedUrlByType),
    ...Object.keys(outputPathByType),
    ...Object.keys(acceptedInputFlags),
    ...Object.keys(generationOutputFlags).map((key) => key.replace(/^generate_/, "").replace(/s$/, ""))
  ].filter(Boolean);
  const channels = sortMediaChannels(rawMediaTypes.map(canonicalMediaChannel).filter(Boolean));
  const confirmedSignedUrlTypes = sortMediaChannels(Object.entries(signedUrlByType)
    .filter(([, count]) => Number(count) > 0)
    .map(([type]) => canonicalMediaChannel(type))
    .filter(Boolean));
  const outputPathTypes = sortMediaChannels(Object.entries(outputPathByType)
    .filter(([, count]) => Number(count) > 0)
    .map(([type]) => canonicalMediaChannel(type))
    .filter(Boolean));
  const signedUrlKeyCount = numberOrNull(mediaSignedUrlFixture.signed_url_key_count) ?? countObjectValues(signedUrlByType);
  const outputPathKeyCount = numberOrNull(mediaSignedUrlFixture.output_path_key_count) ?? countObjectValues(outputPathByType);
  const renderLiveLinks = conclusion.render_live_signed_links_in_a3 === true;
  const unconfirmedSignedUrlTypes = ["audio", "images", "video"].filter((type) => (
    channels.includes(type) && !confirmedSignedUrlTypes.includes(type)
  ));
  const channelMatrix = buildMediaChannelMatrix({
    channels,
    usageChannels,
    mediaCases,
    outputPathTypes,
    confirmedSignedUrlTypes,
    unconfirmedSignedUrlTypes,
    renderLiveLinks
  });
  const evidenceQueue = buildMediaEvidenceQueue(mediaCases, {
    confirmedSignedUrlTypes,
    unconfirmedSignedUrlTypes,
    renderLiveLinks
  });

  return {
    available: mediaCases.length > 0 || channels.length > 0 || signedUrlKeyCount > 0 || outputPathKeyCount > 0,
    media_case_count: mediaCases.length,
    evidence_item_count: evidenceItems.length,
    vm_stream_count: vmStreams.length,
    channels,
    output_path_key_count: outputPathKeyCount,
    output_path_types: outputPathTypes,
    signed_url_key_count: signedUrlKeyCount,
    signed_url_confirmed_types: confirmedSignedUrlTypes,
    signed_url_unconfirmed_types: unconfirmedSignedUrlTypes,
    live_rendering_allowed: renderLiveLinks,
    values_redacted: mediaSignedUrlFixture.signed_url_values_saved === false || mediaSignedUrlFixture.safety?.signed_url_values_saved === false,
    safety: objectOr(mediaSignedUrlFixture.safety),
    channel_matrix: channelMatrix,
    evidence_queue: evidenceQueue,
    evidence_queue_count: evidenceQueue.length,
    guidance: renderLiveLinks
      ? "Live signed media links can be rendered from the current evidence."
      : "Render media metadata only. Do not render live signed URLs until audio/image/video signed URL and expiry behavior are confirmed.",
    known_gaps: uniqueSorted([
      ...mediaCases.flatMap((item) => item.media_evidence?.known_gaps || []),
      ...unconfirmedSignedUrlTypes.map((type) => `${type} signed URL behavior is unconfirmed.`),
      confirmedSignedUrlTypes.length === 1 && confirmedSignedUrlTypes[0] === "files"
        ? "Only file-like signed_url fields are confirmed in the redacted sample."
        : "",
      conclusion.reason || ""
    ])
  };
}

export function summarizeCloudConsoleShell(authFixture = {}, frontendFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}) {
  const authOk = authFixture.auth_ok === true || authFixture.calls?.init?.ok === true || authFixture.calls?.health_check?.ok === true;
  const frontendAuth = objectOr(frontendFixture.auth_state);
  const frontendSessionValid = frontendAuth.frontend_session_valid === true;
  const pages = Array.isArray(frontendFixture.pages) ? frontendFixture.pages : [];
  const pageNames = pages.map((page) => page.page).filter(Boolean);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const observedPageCount = pageNames.length;

  const sections = [
    {
      area: "Auth session",
      status: authOk || frontendSessionValid ? "observed" : "mock-only",
      detail: authOk && frontendSessionValid
        ? "API-key auth and manual frontend session were both observed with redacted evidence."
        : authOk
          ? "API-key auth was observed; frontend session state is not loaded for this source."
          : "No auth fixture is loaded; keep this as a local mock shell."
    },
    {
      area: "Workspace / tenant",
      status: authOk ? "redacted" : "mock-only",
      detail: authOk
        ? "Tenant/user existence was confirmed, but names, ids, plan, and email stay redacted."
        : "Show workspace shape only; do not store account values."
    },
    {
      area: "Datasets / runs",
      status: requestProvenance.available ? "read-only samples" : "local fixtures",
      detail: requestProvenance.available
        ? "Request and dataset provenance can be shown from redacted samples."
        : "Mock fixtures cover the evaluation flow without cloud access."
    },
    {
      area: "Usage / billing",
      status: usageQuota.oauth_only_functions.length ? "OAuth-gated" : usageQuota.available ? "frontend-confirmed" : "known gap",
      detail: usageQuota.available
        ? usageQuota.guidance
        : "Keep billing/usage as a product shell until a safe source is available."
    },
    {
      area: "API keys",
      status: "disabled",
      detail: "Do not copy create/revoke/show-secret flows. Only show setup status and safety policy."
    },
    {
      area: "Team",
      status: "disabled",
      detail: "Do not copy invites or member administration in the A3 MVP."
    },
    {
      area: "Trust / report",
      status: "report-only",
      detail: "A3 uses local export/print reports instead of public certificate publishing."
    },
    {
      area: "Cloud mutations",
      status: "disabled",
      detail: "No create, delete, publish, invite, billing, or key-management actions are wired."
    }
  ];
  const actions = buildCloudActionGuardrails({
    authOk,
    frontendSessionValid,
    requestProvenance,
    usageQuota,
    observedPageCount
  });

  return {
    available: authOk || frontendSessionValid || observedPageCount > 0 || requestProvenance.available || usageQuota.available,
    auth_observed: authOk,
    frontend_session_observed: frontendSessionValid,
    observed_page_count: observedPageCount,
    observed_pages: pageNames,
    real_mutations_enabled: false,
    secret_values_allowed: false,
    sections,
    actions,
    recommendation: "Mimic the official cloud console as a read-only shell: show workspace, auth, usage, API-key, team, and trust status, but do not implement real account or cloud mutations."
  };
}

export function summarizeOfficialAshrGap(runFixture = {}, gradeFixture = {}, coverageFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const hasFailures = summary.failed > 0;
  const hasExpectedActual = cases.some((item) => isObject(item.expected) || isObject(item.actual));
  const hasToolDiffs = cases.some((item) => buildToolCallDiffs(item).length > 0);
  const hasMediaEvidence = summary.mediaEvidenceCases > 0;

  const copied = [
    gapItem("Runs", summary.totalRuns > 0, "Run list and execution-batch summary are available."),
    gapItem("Case detail", summary.totalCases > 0, "Selected case view shows status, score, judge evidence, and trace."),
    gapItem("Expected vs actual", hasExpectedActual, "Expected response/tool calls can be compared against actual output."),
    gapItem("Tool-call inspection", hasToolDiffs, "Tool-call diff shows wrong, missing, extra, reordered, and argument-level mismatches."),
    gapItem("Failure triage", hasFailures, "Failure clusters and triage queue turn raw failures into debugging work."),
    gapItem("Report export", true, "JSON, CSV, Markdown, and print/PDF flows are wired."),
    gapItem("Media evidence", hasMediaEvidence, "A3 preserves media metadata when redacted Ashr samples provide it.")
  ].filter((item) => item.confirmed);

  const partial = [
    gapItem("Datasets", summary.totalRuns > 0, "A3 shows dataset identity and joined titles, but not the full official dataset generator."),
    gapItem("Analytics", summary.totalCases > 0, "A3 has pass-rate, score, coverage, and failure analytics, but not official charts by account."),
    gapItem("Requests", requestProvenance.available, "A3 can show generation provenance from redacted request samples."),
    gapItem("Usage / quota", usageQuota.available, usageQuota.guidance),
    gapItem("Coverage health", coverage.available, "A3 shows A2 scenario and failure-class coverage instead of official hosted analytics."),
    gapItem("Frontend run detail", false, "Hosted run 11926 is API-retrievable and list_runs(summary_only) visible, but visual Results-page confirmation still needs a logged-in browser pass.")
  ];

  const blocked = [
    {
      area: "Populated official run detail",
      reason: "The official demo run 11926 exists through the API with result.tests[] and appears in the same summary_only list_runs shape used by the frontend, but the in-app browser was not logged in for visual Results-page verification.",
      next_step: "Refresh the logged-in Ashr Lab dataset 884 Results page and confirm whether run 11926 is visible in the official UI."
    },
    {
      area: "Native failure class",
      reason: "The real failed-run sample exposed score, passed, reason, and metrics, but no named backend failure_class field.",
      next_step: "Keep A3 failure classes derived until a future sample proves a native field."
    },
    {
      area: "Live signed media rendering",
      reason: "Only redacted file-like signed_url coverage is confirmed; audio/image/video signed URL behavior is not complete.",
      next_step: "Keep live media URLs out of the dashboard until access/redaction rules are clear."
    }
  ];

  const outOfScope = [
    "OAuth/login implementation",
    "API key creation or revocation",
    "Team invites and account administration",
    "Billing, upgrades, and usage enforcement",
    "Full 8-step dataset generation wizard",
    "Public Trust/certificate publishing",
    "Destructive hosted cloud operations"
  ];

  const officialPages = [
    officialPage("Datasets", "?tab=analysis", "partial", "Copy list/filter mental model; keep A3 focused on runs and cases."),
    officialPage("Dataset / Results Detail", "?tab=analysis&dataset=884", "api-summary confirmed, visual pending", "A3 can show run 11926 locally; official API summary lists it, while visual Results confirmation still needs a logged-in frontend pass."),
    officialPage("Agents", "?tab=agents", "metadata only", "Use agent as a label/filter, not a full agent registry."),
    officialPage("Folders", "?tab=folders", "not needed", "Skip folder management for the student MVP."),
    officialPage("Analytics", "?tab=analytics", "partial", "Use summary metrics, pass rate, failures, and coverage; skip account-level charts."),
    officialPage("Usage", "?tab=usage", usageQuota.available ? "partial" : "known gap", "Show quota/media state as read-only calibration evidence."),
    officialPage("Trust", "?tab=trust", "report-only", "Keep printable reports; skip public certificate publishing."),
    officialPage("API Keys", "?tab=api-keys", "out of scope", "Do not copy secret/key management."),
    officialPage("Team", "?tab=team", "out of scope", "Do not copy member invites or account administration.")
  ];

  return {
    available: true,
    copied_count: copied.length,
    partial_count: partial.filter((item) => item.confirmed).length,
    blocked_count: blocked.length,
    out_of_scope_count: outOfScope.length,
    official_pages: officialPages,
    copied,
    partial,
    blocked,
    out_of_scope: outOfScope,
    recommendation: "Keep A3 as a local read-only triage console. Copy official Ashr's navigation and evidence-review logic, but do not copy account, billing, key, team, or hosted mutation flows."
  };
}

export function summarizeOfficialFrontendMirror(mirrorFixture = {}) {
  const navigation = Array.isArray(mirrorFixture.navigation) ? mirrorFixture.navigation : [];
  const apiMethodGroups = Array.isArray(mirrorFixture.api_method_groups) ? mirrorFixture.api_method_groups : [];
  const labChunks = Array.isArray(mirrorFixture.lab_chunks) ? mirrorFixture.lab_chunks : [];
  const confirmedLabels = Array.isArray(mirrorFixture.confirmed_labels) ? mirrorFixture.confirmed_labels : [];
  const mvpRecommendations = Array.isArray(mirrorFixture.mvp_recommendations) ? mirrorFixture.mvp_recommendations : [];
  const safety = objectOr(mirrorFixture.safety);
  const available = navigation.length > 0 || apiMethodGroups.length > 0 || labChunks.length > 0;

  const pages = navigation.map((item) => {
    const decision = String(item.a3_decision || "");
    return {
      tab_id: item.tab_id || "unknown",
      label: item.label || item.tab_id || "Unknown",
      chunk: item.chunk || "unknown",
      a3_status: classifyOfficialMirrorDecision(decision),
      a3_decision: decision || "No A3 decision recorded."
    };
  });

  const groups = apiMethodGroups.map((item) => {
    const methods = Array.isArray(item.methods) ? item.methods : [];
    const decision = String(item.a3_decision || "");
    return {
      group: item.group || "unknown",
      method_count: methods.length,
      methods,
      a3_status: classifyOfficialMirrorDecision(decision),
      a3_decision: decision || "No A3 decision recorded."
    };
  });

  const statusCounts = countOfficialMirrorStatuses([...pages, ...groups]);

  return {
    available,
    source_archive: mirrorFixture.source_archive || "unknown",
    clean_room_boundary: mirrorFixture.copyright_boundary || "Clean-room summary only. Do not copy official source, styles, assets, cookies, or secrets.",
    total_files: numberOrNull(mirrorFixture.file_counts?.total_files) ?? 0,
    html_file_count: numberOrNull(mirrorFixture.file_counts?.html) ?? 0,
    javascript_file_count: numberOrNull(mirrorFixture.file_counts?.javascript) ?? 0,
    lab_chunk_count: labChunks.length,
    page_count: pages.length,
    api_group_count: groups.length,
    api_method_count: groups.reduce((sum, group) => sum + group.method_count, 0),
    confirmed_label_count: confirmedLabels.length,
    confirmed_labels: confirmedLabels,
    pages,
    api_method_groups: groups,
    copied_count: statusCounts.copy,
    partial_count: statusCounts.partial,
    future_count: statusCounts.future,
    out_of_scope_count: statusCounts.out_of_scope,
    unknown_count: statusCounts.unknown,
    safety: {
      official_source_committed: safety.official_source_committed === true,
      secret_values_allowed: safety.secret_values_allowed === true,
      raw_cookies_allowed: safety.raw_cookies_allowed === true,
      raw_tokens_allowed: safety.raw_tokens_allowed === true,
      raw_signed_urls_allowed: safety.raw_signed_urls_allowed === true
    },
    recommendation: mvpRecommendations[0] || "Use official frontend structure as product reference only, then implement A3-owned dashboard views with redacted fixtures."
  };
}

export function summarizeOfficialCodeCrawlParity(codeCrawlFixture = {}) {
  const chunkSignals = Array.isArray(codeCrawlFixture.chunk_signals) ? codeCrawlFixture.chunk_signals : [];
  const parityTargets = Array.isArray(codeCrawlFixture.a3_parity_targets) ? codeCrawlFixture.a3_parity_targets : [];
  const safety = objectOr(codeCrawlFixture.safety);
  const scope = objectOr(codeCrawlFixture.crawl_scope);
  const chunks = chunkSignals.map((item) => {
    const signals = objectOr(item.signals);
    const signalEntries = Object.entries(signals)
      .filter(([, value]) => Number(value) > 0)
      .sort((left, right) => Number(right[1]) - Number(left[1]));
    return {
      chunk: item.chunk || "unknown",
      role: item.role || "unknown",
      size_bytes: numberOrNull(item.size_bytes) ?? 0,
      top_signals: signalEntries.slice(0, 5).map(([signal, count]) => ({ signal, count })),
      signal_count: signalEntries.reduce((sum, [, count]) => sum + Number(count || 0), 0),
      a3_status: classifyOfficialCodeCrawlDecision(item.a3_decision || ""),
      a3_decision: item.a3_decision || "No A3 decision recorded."
    };
  });
  const targets = parityTargets.map((item) => {
    const status = classifyOfficialCodeCrawlDecision(item.a3_status || item.a3_decision || "");
    return {
      target: item.target || "unknown",
      official_evidence: Array.isArray(item.official_evidence) ? item.official_evidence : [],
      a3_status: status,
      a3_dependency: item.a1_a2_dependency || "A1/A2 dependency not recorded."
    };
  });
  const statusCounts = countOfficialMirrorStatuses([
    ...chunks,
    ...targets.map((item) => ({ a3_status: item.a3_status }))
  ]);

  return {
    schema_version: "a3.official_code_crawl_parity.v1",
    available: chunks.length > 0 || targets.length > 0,
    source_archive: codeCrawlFixture.source_archive || "unknown",
    clean_room_boundary: codeCrawlFixture.clean_room_boundary || "Clean-room summary only. Do not copy official source, styles, assets, cookies, tokens, or secrets.",
    zip_file_count: numberOrNull(scope.zip_file_count) ?? 0,
    lab_javascript_chunk_count: numberOrNull(scope.lab_javascript_chunk_count) ?? chunks.length,
    lab_css_chunk_count: numberOrNull(scope.lab_css_chunk_count) ?? 0,
    chunk_count: chunks.length,
    parity_target_count: targets.length,
    copy_now_count: statusCounts.copy,
    partial_count: statusCounts.partial,
    future_count: statusCounts.future,
    out_of_scope_count: statusCounts.out_of_scope,
    chunks,
    parity_targets: targets,
    next_build_order: Array.isArray(codeCrawlFixture.next_build_order) ? codeCrawlFixture.next_build_order : [],
    safety: {
      secret_values_saved: safety.secret_values_saved === true,
      raw_cookies_saved: safety.raw_cookies_saved === true,
      raw_tokens_saved: safety.raw_tokens_saved === true,
      raw_signed_urls_saved: safety.raw_signed_urls_saved === true,
      official_source_committed: safety.official_source_committed === true,
      raw_source_excerpt_committed: objectOr(codeCrawlFixture.crawl_scope).raw_source_excerpt_committed === true
    },
    recommendation: "Use official code crawl signals to prioritize A3-owned release intelligence: results review, trace observability, media metadata, trust/audit, and read-only usage. Keep admin, keys, billing mutations, and source copying out of scope."
  };
}

export function summarizeOfficialParityRoadmap(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  requestFixture = {},
  usageFixture = {},
  usageApiProbe = {},
  mediaSignedUrlFixture = {},
  frontendMirrorFixture = {}
) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const officialGap = summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe);
  const mirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const media = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const copiedPages = mirror.pages.filter((page) => page.a3_status === "copy");
  const partialPages = mirror.pages.filter((page) => page.a3_status === "partial");
  const futurePages = mirror.pages.filter((page) => page.a3_status === "future");
  const outOfScopePages = mirror.pages.filter((page) => page.a3_status === "out_of_scope");
  const priorities = [
    parityAction("Results review", "copy_now", summary.totalRuns > 0, "Keep run list, case detail, expected vs actual, score, pass/fail, and failed-case triage as the A3 core."),
    parityAction("Trace / observability", media.vm_stream_count > 0 ? "copy_now" : "next", summary.traceCompleteness >= 90, "Use official Observability as inspiration for trace timeline, replay, latency, and tool-error review."),
    parityAction("Media evidence", media.available ? "copy_now" : "next", media.available, media.guidance),
    parityAction("Usage / quota", usageQuota.available ? "read_only" : "next", usageQuota.available, "Show quota and billing-adjacent signals as read-only evidence; do not copy checkout or enforcement."),
    parityAction("Trust / audit", "copy_as_report", true, "Use official Trust ideas through local audit bundle, verifier, print/PDF, and release sign-off reports."),
    parityAction("API keys / team / billing", "do_not_copy", false, "Keep OAuth, key creation, team invites, billing portal, and destructive cloud mutations out of the student MVP.")
  ];
  const mediaActions = [
    ...media.signed_url_unconfirmed_types.map((channel) => parityAction(`${channel} signed URL`, "calibrate_next", false, `Collect a redacted ${channel} sample before rendering live previews.`)),
    media.evidence_queue_count > 0
      ? parityAction("Media evidence queue", "copy_now", true, `${media.evidence_queue_count} media case(s) can be reviewed with metadata-only previews.`)
      : parityAction("Media evidence queue", "next", false, "Add redacted audio/image/video/file examples before claiming official media parity.")
  ];

  return {
    schema_version: "a3.official_parity_roadmap.v1",
    available: officialGap.available || mirror.available || media.available,
    official_gap_blocked_count: officialGap.blocked_count,
    official_gap_blocked_areas: officialGap.blocked.map((item) => item.area),
    official_pages_observed: mirror.page_count,
    copied_page_count: copiedPages.length,
    partial_page_count: partialPages.length,
    future_page_count: futurePages.length,
    out_of_scope_page_count: outOfScopePages.length,
    copied_pages: copiedPages.map((page) => page.label),
    partial_pages: partialPages.map((page) => page.label),
    future_pages: futurePages.map((page) => page.label),
    out_of_scope_pages: outOfScopePages.map((page) => page.label),
    priorities,
    media_actions: mediaActions,
    cloud_admin_boundaries: [
      "Do not implement OAuth/login for A3 MVP.",
      "Do not implement API-key creation, reveal, revoke, or storage.",
      "Do not implement billing checkout, portal, upgrade, or quota enforcement.",
      "Do not implement team invites or account administration.",
      "Keep cloud/admin concepts as read-only product shell evidence."
    ],
    next_build_order: [
      "Official Results-page visual confirmation for run 11926.",
      "Trace/Observability replay lane for top-risk cases.",
      "Redacted audio/image/video media samples and metadata-only previews.",
      "Trust/audit report improvements tied to bundle verifier.",
      "Self-host/enterprise shell that proves no secrets or cloud mutations are required."
    ],
    recommendation: "Use official Ashr for product workflow parity, but keep A3 focused on local release intelligence: results, case detail, trace, failure analysis, media evidence, reports, and audit."
  };
}

function isA2ReleaseGateFixture(value = {}) {
  return isObject(value) && (
    value.schema_version === "a2.release_gate.v1"
    || value.report_id === "a2_release_gate"
    || Array.isArray(value.required_evidence)
    || Array.isArray(value.blockers)
  );
}

function summarizeA2ReleaseGate(releaseGateFixture = {}) {
  const missing = (value) => Array.isArray(value) ? value : [];
  const mapping = (value) => isObject(value) ? value : {};
  const available = isObject(releaseGateFixture) && Object.keys(releaseGateFixture).length > 0;
  const requiredEvidence = missing(releaseGateFixture.required_evidence);
  const blockers = missing(releaseGateFixture.blockers);
  const warnings = missing(releaseGateFixture.warnings);

  return {
    available,
    schema_version: available ? releaseGateFixture.schema_version || "unknown" : "none",
    report_id: available ? releaseGateFixture.report_id || "unknown" : "none",
    decision: releaseGateFixture.decision || "none",
    exit_code: releaseGateFixture.exit_code || 0,
    risk_score: releaseGateFixture.risk_score || 0,
    current_commercial_gate: releaseGateFixture.current_commercial_gate || "none",
    ready_for_commercial_gate: releaseGateFixture.ready_for_commercial_gate === true,
    blocks_release: releaseGateFixture.decision === "block",
    blocking_gate_count: releaseGateFixture.blocking_gate_count || blockers.length,
    evidence_blocker_count: releaseGateFixture.evidence_blocker_count || 0,
    warning_count: releaseGateFixture.warning_count || warnings.length,
    blocker_gates: [...new Set(blockers.map((item) => item.gate).filter(Boolean))].sort(),
    blocker_types: [...new Set(blockers.map((item) => item.type).filter(Boolean))].sort(),
    warning_types: [...new Set(warnings.map((item) => item.type).filter(Boolean))].sort(),
    required_sources: requiredEvidence.map((item) => item.source).filter(Boolean).sort(),
    required_source_counts: Object.fromEntries(requiredEvidence
      .filter((item) => item && item.source)
      .map((item) => [item.source, {
        required_count: item.required_count || 0,
        current_available: item.current_available || 0,
        collection_packet_ref: item.collection_packet_ref || ""
      }])),
    pr_annotation_count: missing(releaseGateFixture.pr_annotations).length,
    ci_mode: mapping(releaseGateFixture.machine_contract).ci_mode || "unknown",
    evidence_refs: missing(releaseGateFixture.evidence_refs)
  };
}

export function summarizeReleaseGate(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  if (isA2ReleaseGateFixture(runFixture)) {
    return summarizeA2ReleaseGate(runFixture);
  }

  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const media = summarizeMediaReadiness(runFixture, gradeFixture, {}, mediaSignedUrlFixture);
  const clusters = clusterFailures(runFixture, gradeFixture);
  const thresholds = normalizeReleaseGateThresholds(options.thresholds || options);
  const failedCases = cases.filter((item) => !item.passed);
  const criticalCases = failedCases.filter((item) => ["critical", "blocker"].includes(item.severity));
  const policyCases = failedCases.filter((item) => [
    "unsafe_or_policy_violation",
    "forbidden_tool_call"
  ].includes(item.primary_failure_class));
  const missingToolCases = failedCases.filter((item) => item.primary_failure_class === "missing_required_tool");
  const traceOk = summary.traceCompleteness >= thresholds.trace_completeness_min;
  const passRateOk = summary.passRate >= thresholds.pass_rate_min;
  const coverageOk = !coverage.available || coverage.meets_assignment_minimums;
  const mediaSafe = !media.live_rendering_allowed;
  const checks = [
    gateCheck("pass_rate", passRateOk, `${summary.passRate}% pass rate`, `Minimum commercial gate is ${thresholds.pass_rate_min}% before release sign-off.`),
    gateCheck("critical_failures", criticalCases.length === 0, `${criticalCases.length} critical/blocker case(s)`, "Critical or blocker failures stop release."),
    gateCheck("policy_failures", policyCases.length === 0, `${policyCases.length} safety/policy case(s)`, "Unsafe or forbidden-tool failures require safety review."),
    gateCheck("required_tool_coverage", missingToolCases.length === 0, `${missingToolCases.length} missing required tool case(s)`, "Missing required tools can hide production incident risk."),
    gateCheck("trace_evidence", traceOk, `${summary.traceCompleteness}% trace completeness`, `Release evidence needs at least ${thresholds.trace_completeness_min}% trace coverage for replay and audit.`),
    gateCheck("coverage_minimums", coverageOk, coverage.available ? `A2 coverage minimums ${coverage.meets_assignment_minimums ? "met" : "not met"}` : "coverage fixture absent", "A2 scenario coverage must be healthy when available."),
    gateCheck("media_safety", mediaSafe, media.available ? `${media.signed_url_key_count} signed URL key(s), live rendering blocked` : "no media evidence", "A3 must not render live signed media until URL safety is confirmed.")
  ];
  const failedChecks = checks.filter((check) => !check.passed);
  const hardBlock = criticalCases.length > 0
    || policyCases.length > 0
    || summary.passRate < thresholds.hard_block_pass_rate_min
    || summary.traceCompleteness < thresholds.hard_block_trace_completeness_min;
  const decision = hardBlock
    ? "block_release"
    : failedChecks.length > 0
      ? "needs_review"
      : "approve_release";
  const riskScore = Math.min(100, Math.round(
    (100 - summary.passRate)
    + criticalCases.length * 25
    + policyCases.length * 20
    + missingToolCases.length * 10
    + Math.max(0, 90 - summary.traceCompleteness)
    + (coverage.available && !coverage.meets_assignment_minimums ? 10 : 0)
  ));
  const topRiskCases = failedCases
    .sort((left, right) => releaseGateCaseWeight(right) - releaseGateCaseWeight(left) || left.score - right.score)
    .slice(0, 5)
    .map((item) => ({
      case_id: item.case_id,
      title: item.title,
      primary_failure_class: item.primary_failure_class,
      severity: item.severity,
      score: item.score,
      summary: item.failure_summary
    }));
  const requiredApprovers = unique([
    "Release owner",
    failedChecks.length ? "A3 triage owner" : null,
    policyCases.length ? "Safety reviewer" : null,
    missingToolCases.length ? "A1 runner/tooling owner" : null,
    coverage.available && !coverage.meets_assignment_minimums ? "A2 judge owner" : null,
    !traceOk ? "Evidence owner" : null,
    media.available ? "Media/security reviewer" : null
  ]);

  return {
    available: summary.totalCases > 0,
    decision,
    decision_label: decision === "approve_release" ? "Approve release" : decision === "needs_review" ? "Needs review" : "Block release",
    risk_score: riskScore,
    summary: decision === "approve_release"
      ? "Release gate passed for the loaded evidence package."
      : decision === "needs_review"
        ? "Release needs human review before sign-off."
        : "Release is blocked by high-risk evidence.",
    checks,
    failed_check_count: failedChecks.length,
    failed_checks: failedChecks.map((check) => check.id),
    thresholds,
    required_approvers: requiredApprovers,
    top_risk_cases: topRiskCases,
    pr_gate: {
      status: decision,
      github_check_name: "Ashr++ Release Gate",
      blocks_merge: decision === "block_release",
      warning_only: decision === "needs_review",
      audit_artifacts: ["json_report", "markdown_report", "print_pdf", "case_evidence"]
    },
    commercial_value: "Blocks risky agent releases, creates reviewer sign-off evidence, and gives enterprise buyers a concrete release-control artifact."
  };
}

export function summarizeReleaseWorkflow(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const gate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options.thresholds ? { thresholds: options.thresholds } : {});
  const runId = summary.lastRunId || "unknown-run";
  const releaseVersion = options.release_version || `candidate-${runId}`;
  const environment = options.environment || "staging";
  const owner = options.owner || "Release owner";
  const conclusion = gate.decision === "approve_release"
    ? "success"
    : gate.decision === "needs_review"
      ? "neutral"
      : "failure";
  const topRiskLines = gate.top_risk_cases.map((item) => (
    `- ${item.case_id}: ${item.primary_failure_class} / ${item.severity} / ${item.score}`
  ));
  const checkTextLines = [
    `Run: ${runId}`,
    `Release: ${releaseVersion}`,
    `Environment: ${environment}`,
    `Pass rate: ${summary.passRate}%`,
    `Average score: ${summary.avgScore}`,
    `Trace completeness: ${summary.traceCompleteness}%`,
    `Failed checks: ${gate.failed_checks.join(", ") || "none"}`,
    "",
    "Top risk cases:",
    ...(topRiskLines.length ? topRiskLines : ["- none"])
  ];
  const waiverAllowed = gate.decision === "needs_review";
  const blockWaiverExceptional = gate.decision === "block_release";
  const requiredApprovers = gate.required_approvers.length ? gate.required_approvers : [owner];
  const reviewerGate = buildPrGateReviewerProjection(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, gate, options);
  const nextActions = unique([
    ...buildReleaseNextActions(gate),
    reviewerGate.pr_gate_next_action
  ]);
  checkTextLines.splice(7, 0,
    `PR gate next action: ${reviewerGate.pr_gate_next_action}`,
    `Sign-off risk: ${reviewerGate.sign_off_risk.level}`
  );

  return {
    available: gate.available,
    release_version: releaseVersion,
    environment,
    owner,
    github_check: {
      name: "Ashr++ Release Gate",
      status: "completed",
      conclusion,
      blocks_merge: gate.pr_gate.blocks_merge,
      output: {
        title: `${gate.decision_label}: ${runId}`,
        summary: `${gate.decision_label} with risk score ${gate.risk_score} and ${gate.failed_check_count} failed check(s).`,
        text: checkTextLines.join("\n")
      }
    },
    pr_comment_markdown: buildReleasePrCommentMarkdown(gate, summary, {
      release_version: releaseVersion,
      environment,
      owner,
      reviewerGate
    }),
    waiver_policy: {
      required: gate.decision !== "approve_release",
      allowed: waiverAllowed,
      exceptional_only: blockWaiverExceptional,
      expiry_max_days: blockWaiverExceptional ? 1 : waiverAllowed ? 7 : 0,
      required_fields: [
        "waiver_owner",
        "business_reason",
        "risk_acceptance",
        "expiry_date",
        "follow_up_issue"
      ],
      blocked_checks: gate.failed_checks,
      guidance: blockWaiverExceptional
        ? "Blocked releases require an explicit executive exception and a one-day expiry."
        : waiverAllowed
          ? "Review releases can be waived with owner, reason, expiry, and follow-up evidence."
          : "No waiver is required for an approved release."
    },
    reviewer_workflow: {
      state: gate.decision === "approve_release" ? "ready_to_merge" : "waiting_for_review",
      required_approvers: requiredApprovers,
      review_lanes: unique([
        "Release owner",
        gate.failed_checks.includes("policy_failures") ? "Safety reviewer" : null,
        gate.failed_checks.includes("required_tool_coverage") ? "Runner/tooling owner" : null,
        gate.failed_checks.includes("coverage_minimums") ? "Judge owner" : null,
        gate.failed_checks.includes("trace_evidence") ? "Evidence owner" : null,
        "A3 triage owner",
        ...reviewerGate.reviewer_lanes.map((lane) => lane.lane)
      ]),
      next_actions: nextActions,
      pr_gate_next_action: reviewerGate.pr_gate_next_action,
      sign_off_risk: reviewerGate.sign_off_risk,
      a1_evidence: reviewerGate.a1_evidence,
      a2_release_gate: reviewerGate.a2_release_gate
    },
    reviewer_gate: reviewerGate,
    audit_bundle: {
      manifest_version: "a3.audit_bundle.v1",
      redaction_policy: "No API keys, cookies, tokens, emails, or live signed media URLs are allowed in exported artifacts.",
      artifacts: [
        auditArtifact("json_report", "a3-dashboard-report.json", true, "Machine-readable release gate, cases, tool diffs, media readiness, and cloud safety evidence."),
        auditArtifact("markdown_report", "a3-dashboard-report.md", true, "Human PR/release note summary with failed checks and top risks."),
        auditArtifact("print_pdf", "browser-print-report.pdf", true, "Executive sign-off packet generated from the local print view."),
        auditArtifact("case_evidence", "normalized_cases[].tool_call_diffs", true, "Case-level expected vs actual, tool-call comparison, and judge evidence."),
        auditArtifact("redacted_fixtures", "fixtures/a3/p3/*.redacted.json", true, "Sanitized Ashr API/frontend calibration evidence."),
        auditArtifact("screenshots", "docs/screenshots/a3-dashboard-*.png", false, "Visual QA evidence with sensitive account details avoided.")
      ]
    },
    incident_replay: {
      enabled: gate.top_risk_cases.length > 0,
      case_ids: gate.top_risk_cases.map((item) => item.case_id),
      replay_mode: "failed_cases_first",
      purpose: "Let reviewers reproduce the highest-risk failures before approving a release."
    },
    commercial_value: "Turns A3 output into a PR gate, reviewer workflow, waiver policy, and audit bundle that can sit in an enterprise release process."
  };
}

function buildPrGateReviewerProjection(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, gate = {}, options = {}) {
  const a2ReleaseGateFixture = selectA2ReleaseGateFixture(options);
  const a2ReleaseGate = isA2ReleaseGateFixture(a2ReleaseGateFixture)
    ? summarizeA2ReleaseGate(a2ReleaseGateFixture)
    : emptyA2ReleaseGateSummary();
  const a2Blockers = summarizeA2BlockersForReview(a2ReleaseGateFixture);
  const a2Warnings = summarizeA2WarningsForReview(a2ReleaseGateFixture);
  const requiredEvidence = summarizeA2RequiredEvidenceForReview(a2ReleaseGateFixture);
  const incidentReplay = summarizeIncidentReplayQueue(runFixture, gradeFixture, mediaSignedUrlFixture, { limit: options.limit || 8 });
  const a1Evidence = summarizeA1EvidenceForPrGate(incidentReplay);
  const reviewerLanes = buildPrGateReviewerLanes({
    gate,
    a2ReleaseGate,
    a2Blockers,
    a2Warnings,
    requiredEvidence,
    a1Evidence
  });
  const signOffRisk = buildSignOffRisk({
    gate,
    a2ReleaseGate,
    a2Blockers,
    a2Warnings,
    a1Evidence,
    requiredBeforeUnblock: readA2RequiredBeforeUnblock(a2ReleaseGateFixture)
  });
  const prGateNextAction = buildPrGateNextAction({
    gate,
    a2ReleaseGate,
    a2Blockers,
    a1Evidence,
    signOffRisk
  });

  return {
    schema_version: "a3.pr_gate_reviewer_projection.v1",
    available: gate.available === true || a2ReleaseGate.available === true || a1Evidence.top_risk_case_count > 0,
    source_semantics_preserved: true,
    source_mutation_performed: false,
    pr_gate_next_action: prGateNextAction,
    sign_off_risk: signOffRisk,
    reviewer_lanes: reviewerLanes,
    a2_release_gate: {
      available: a2ReleaseGate.available,
      schema_version: a2ReleaseGate.schema_version,
      decision: a2ReleaseGate.decision,
      blocks_release: a2ReleaseGate.blocks_release === true,
      risk_score: a2ReleaseGate.risk_score,
      current_commercial_gate: a2ReleaseGate.current_commercial_gate,
      blocker_count: a2Blockers.length,
      warning_count: a2Warnings.length,
      blocker_gates: a2ReleaseGate.blocker_gates || [],
      blocker_types: a2ReleaseGate.blocker_types || [],
      required_sources: a2ReleaseGate.required_sources || [],
      required_evidence: requiredEvidence,
      blockers: a2Blockers.slice(0, 10),
      warnings: a2Warnings.slice(0, 5),
      ci_mode: a2ReleaseGate.ci_mode,
      evidence_refs: a2ReleaseGate.evidence_refs || []
    },
    a1_evidence: a1Evidence,
    safety: {
      secret_values_included: false,
      private_evidence_values_included: false,
      private_input_refs_exposed: false,
      raw_a1_trace_payloads_mutated: false,
      raw_a2_gate_semantics_mutated: false,
      real_cloud_mutation_performed: false
    },
    commercial_value: "Turns A2 release blockers and A1 trace/tool-call evidence into owned reviewer lanes, PR gate next action, and explicit sign-off risk."
  };
}

function selectA2ReleaseGateFixture(options = {}) {
  const candidate = options.a2ReleaseGate
    || options.a2_release_gate
    || options.releaseGateFixture
    || options.release_gate_fixture
    || {};
  return isA2ReleaseGateFixture(candidate) ? candidate : {};
}

function emptyA2ReleaseGateSummary() {
  return {
    available: false,
    schema_version: "none",
    decision: "none",
    blocks_release: false,
    risk_score: 0,
    current_commercial_gate: "none",
    blocker_gates: [],
    blocker_types: [],
    required_sources: [],
    ci_mode: "none",
    evidence_refs: []
  };
}

function summarizeA2BlockersForReview(releaseGateFixture = {}) {
  const blockers = Array.isArray(releaseGateFixture.blockers) ? releaseGateFixture.blockers : [];
  return blockers.map((blocker, index) => {
    const gate = blocker.gate || "unknown_gate";
    const type = blocker.type || "unknown";
    return {
      blocker_id: `${gate}:${type}:${index + 1}`,
      source: "a2.release_gate.blockers",
      gate,
      type,
      status: blocker.status || "unknown",
      severity: blocker.severity || "unknown",
      summary: blocker.summary || "",
      required_action: blocker.required_action || "Resolve the A2 release gate blocker before sign-off.",
      missing_count: Number.isFinite(Number(blocker.missing_count)) ? Number(blocker.missing_count) : 0,
      evidence_refs: Array.isArray(blocker.evidence_refs) ? blocker.evidence_refs : []
    };
  });
}

function summarizeA2WarningsForReview(releaseGateFixture = {}) {
  const warnings = Array.isArray(releaseGateFixture.warnings) ? releaseGateFixture.warnings : [];
  return warnings.map((warning, index) => ({
    warning_id: `warning:${warning.type || "unknown"}:${index + 1}`,
    source: "a2.release_gate.warnings",
    type: warning.type || "unknown",
    severity: warning.severity || "unknown",
    summary: warning.summary || "",
    count: warning.count || 0,
    evidence_refs: Array.isArray(warning.evidence_refs) ? warning.evidence_refs : []
  }));
}

function summarizeA2RequiredEvidenceForReview(releaseGateFixture = {}) {
  const requiredEvidence = Array.isArray(releaseGateFixture.required_evidence) ? releaseGateFixture.required_evidence : [];
  return requiredEvidence.map((item) => ({
    source: item.source || "unknown",
    required_count: item.required_count || 0,
    current_available: item.current_available || 0,
    missing_count: Math.max(0, Number(item.required_count || 0) - Number(item.current_available || 0)),
    collection_packet_ref: item.collection_packet_ref || "",
    command_count: Array.isArray(item.commands) ? item.commands.length : 0,
    private_input_ref_present: Boolean(item.private_input_ref),
    private_input_ref_exposed: false
  }));
}

function readA2RequiredBeforeUnblock(releaseGateFixture = {}) {
  const workflow = objectOr(releaseGateFixture.review_workflow);
  return Array.isArray(workflow.required_before_unblock) ? workflow.required_before_unblock : [];
}

function summarizeA1EvidenceForPrGate(incidentReplay = {}) {
  const queue = Array.isArray(incidentReplay.queue) ? incidentReplay.queue : [];
  const missingTraceCases = queue.filter((item) => !item.trace_ready);
  const toolDiffCases = queue.filter((item) => item.tool_diff_count > 0);
  return {
    source: "a1.normalized_trace_and_tool_call_evidence",
    top_risk_case_count: queue.length,
    trace_ready_count: incidentReplay.trace_ready_count || queue.filter((item) => item.trace_ready).length,
    missing_trace_count: missingTraceCases.length,
    tool_diff_ready_count: incidentReplay.tool_diff_ready_count || toolDiffCases.length,
    judge_evidence_ready_count: incidentReplay.judge_evidence_ready_count || 0,
    media_evidence_ready_count: incidentReplay.media_evidence_ready_count || 0,
    release_blocker_case_count: incidentReplay.blocker_count || queue.filter((item) => item.release_blocker).length,
    evidence_cases: queue.slice(0, 5).map((item) => ({
      case_id: item.case_id,
      owner_lane: item.owner_lane,
      trace_ready: item.trace_ready === true,
      tool_diff_count: item.tool_diff_count || 0,
      judge_evidence_count: item.judge_evidence_count || 0,
      release_blocker: item.release_blocker === true,
      next_action: item.trace_ready
        ? "Replay A1 trace and inspect expected-vs-actual tool-call evidence before sign-off."
        : "Collect A1 trace evidence before sign-off."
    }))
  };
}

function buildPrGateReviewerLanes({
  gate = {},
  a2ReleaseGate = {},
  a2Blockers = [],
  a2Warnings = [],
  requiredEvidence = [],
  a1Evidence = {}
} = {}) {
  const a2BlockerLanes = groupA2BlockersByGate(a2Blockers).map(([gateId, blockers]) => ({
    lane: `${gateId} A2 release blocker`,
    owner: a2ReviewerOwnerForGate(gateId, blockers),
    source: "a2.release_gate",
    status: "blocked",
    item_count: blockers.length,
    blocker_count: blockers.length,
    warning_count: a2Warnings.filter((warning) => blockers.some((blocker) => blocker.type === warning.type)).length,
    required_sources: requiredEvidence.map((item) => item.source).filter(Boolean),
    evidence_refs: uniqueSorted(blockers.flatMap((blocker) => blocker.evidence_refs)),
    next_action: blockers[0]?.required_action || `Resolve ${gateId} A2 release blocker before sign-off.`,
    required_actions: uniqueSorted(blockers.map((blocker) => blocker.required_action))
  }));

  const a1Lane = {
    lane: "A1 trace/tool-call evidence",
    owner: "A1 API/runtime owner",
    source: "a1.trace_tool_call_evidence",
    status: a1Evidence.missing_trace_count > 0 ? "needs_evidence" : a1Evidence.top_risk_case_count > 0 ? "ready" : "standby",
    item_count: a1Evidence.top_risk_case_count || 0,
    blocker_count: a1Evidence.release_blocker_case_count || 0,
    trace_ready_count: a1Evidence.trace_ready_count || 0,
    tool_diff_ready_count: a1Evidence.tool_diff_ready_count || 0,
    next_action: a1Evidence.top_risk_case_count > 0
      ? `Replay ${a1Evidence.trace_ready_count || 0} A1 trace-ready case(s) and inspect ${a1Evidence.tool_diff_ready_count || 0} tool-call diff packet(s).`
      : "Stand by for A1 trace/tool-call evidence when the PR gate has failed cases."
  };

  const a3Lane = {
    lane: "A3 PR gate action",
    owner: "A3 dashboard/report owner",
    source: "a3.release_workflow",
    status: a2ReleaseGate.blocks_release || gate.pr_gate?.blocks_merge
      ? "blocked"
      : gate.pr_gate?.warning_only
        ? "review"
        : "ready",
    item_count: 1,
    blocker_count: a2ReleaseGate.blocks_release || gate.pr_gate?.blocks_merge ? 1 : 0,
    next_action: "Publish the PR gate next action with the report, then require reviewer disposition before merge."
  };

  return [...a2BlockerLanes, a1Lane, a3Lane];
}

function groupA2BlockersByGate(blockers = []) {
  const groups = new Map();
  for (const blocker of blockers) {
    const gate = blocker.gate || "unknown_gate";
    if (!groups.has(gate)) {
      groups.set(gate, []);
    }
    groups.get(gate).push(blocker);
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
}

function a2ReviewerOwnerForGate(gateId = "", blockers = []) {
  if (gateId === "C3") {
    return "A2 calibration owner";
  }
  if (gateId === "C4") {
    return "A2 semantic judge owner";
  }
  if (gateId === "C5") {
    return "A2 regression owner";
  }
  if (blockers.some((blocker) => blocker.type === "evidence_gate")) {
    return "A2 evidence reviewer";
  }
  return "A2 owner";
}

function buildSignOffRisk({
  gate = {},
  a2ReleaseGate = {},
  a2Blockers = [],
  a2Warnings = [],
  a1Evidence = {},
  requiredBeforeUnblock = []
} = {}) {
  const reasons = unique([
    a2ReleaseGate.blocks_release ? `A2 release gate decision=${a2ReleaseGate.decision} blocks release.` : "",
    gate.pr_gate?.blocks_merge ? `A3 PR gate decision=${gate.decision} blocks merge.` : "",
    gate.pr_gate?.warning_only ? `A3 PR gate decision=${gate.decision} requires review.` : "",
    a1Evidence.release_blocker_case_count > 0 ? `${a1Evidence.release_blocker_case_count} A1 replay case(s) are release blockers.` : "",
    a1Evidence.missing_trace_count > 0 ? `${a1Evidence.missing_trace_count} replay case(s) lack A1 trace evidence.` : "",
    a2Warnings.length > 0 ? `${a2Warnings.length} A2 warning(s) remain open.` : ""
  ]);
  const level = a2ReleaseGate.blocks_release || gate.pr_gate?.blocks_merge
    ? "blocked"
    : gate.pr_gate?.warning_only || a1Evidence.missing_trace_count > 0
      ? "high"
      : a2Warnings.length > 0
        ? "medium"
        : "low";
  const baseScore = Math.max(Number(gate.risk_score || 0), Number(a2ReleaseGate.risk_score || 0));
  const score = Math.min(100, Math.round(
    baseScore
    + (a2Blockers.length > 0 ? Math.min(20, a2Blockers.length * 3) : 0)
    + (a1Evidence.missing_trace_count > 0 ? 10 : 0)
    + Math.min(10, a2Warnings.length * 2)
  ));
  const requiredBeforeSignOff = unique([
    ...requiredBeforeUnblock,
    ...a2Blockers.slice(0, 5).map((blocker) => blocker.required_action),
    a1Evidence.top_risk_case_count > 0 ? "Replay A1 trace/tool-call evidence for top-risk cases and record reviewer disposition." : ""
  ]);

  return {
    level,
    score,
    can_sign_off: level === "low" && gate.decision === "approve_release" && a2ReleaseGate.blocks_release !== true,
    risk_acceptance_required: level !== "low",
    executive_exception_required: level === "blocked",
    reasons,
    required_before_sign_off: requiredBeforeSignOff
  };
}

function buildPrGateNextAction({
  gate = {},
  a2ReleaseGate = {},
  a2Blockers = [],
  a1Evidence = {},
  signOffRisk = {}
} = {}) {
  const blockerGates = uniqueSorted(a2Blockers.map((blocker) => blocker.gate));
  if (a2ReleaseGate.blocks_release) {
    const a1Clause = a1Evidence.top_risk_case_count > 0
      ? `; replay ${a1Evidence.trace_ready_count || 0} A1 trace-ready case(s) and ${a1Evidence.tool_diff_ready_count || 0} tool-call diff packet(s)`
      : "";
    return `Block merge: resolve A2 release gate blocker(s) ${blockerGates.join(", ") || "unknown"} before sign-off${a1Clause}.`;
  }
  if (gate.pr_gate?.blocks_merge) {
    return `Block merge: resolve A3 failed check(s) ${(gate.failed_checks || []).join(", ") || "unknown"} before sign-off.`;
  }
  if (gate.pr_gate?.warning_only || signOffRisk.level === "high") {
    return "Require reviewer disposition: attach A1 replay evidence and A3 audit artifacts before merge.";
  }
  return "Merge may proceed after JSON, Markdown, and audit artifacts are attached to the release record.";
}

export function summarizeReleaseWarRoom(
  runFixture = {},
  gradeFixture = {},
  coverageFixture = {},
  mediaSignedUrlFixture = {},
  requestFixture = {},
  usageFixture = {},
  usageApiProbe = {},
  frontendMirrorFixture = {},
  options = {}
) {
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const gate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options.thresholds ? { thresholds: options.thresholds } : {});
  const workflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const mediaReadiness = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, mediaSignedUrlFixture);
  const officialMirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const incidentCaseCount = workflow.incident_replay.case_ids.length;
  const revenueRiskScore = Math.min(100, Math.round(
    gate.risk_score
    + (workflow.waiver_policy.required ? 8 : 0)
    + (incidentCaseCount > 0 ? Math.min(12, incidentCaseCount * 3) : 0)
    + (mediaReadiness.signed_url_unconfirmed_types.length > 0 ? 4 : 0)
    + (officialMirror.future_count > 0 ? 2 : 0)
  ));
  const decision = gate.decision === "approve_release"
    ? "ship_ready"
    : gate.decision === "needs_review"
      ? "review_required"
      : "no_go";
  const urgency = decision === "no_go"
    ? "stop_the_line"
    : decision === "review_required"
      ? "same_day_review"
      : "monitor_after_merge";
  const lanes = [
    warRoomLane(
      "Release Control",
      "Release owner",
      gate.pr_gate.blocks_merge ? "blocked" : gate.pr_gate.warning_only ? "review" : "ready",
      `${gate.decision_label}; risk score ${gate.risk_score}; ${gate.failed_check_count} failed gate check(s).`,
      gate.pr_gate.blocks_merge ? "Do not merge until exception approval and audit evidence are attached." : "Attach gate report to release record."
    ),
    warRoomLane(
      "Failure Triage",
      "A3 triage owner",
      gate.top_risk_cases.length ? "active" : "ready",
      `${gate.top_risk_cases.length} top-risk case(s) queued.`,
      gate.top_risk_cases.length ? "Assign owners for every top-risk case before sign-off." : "No high-risk failure queue for this run."
    ),
    warRoomLane(
      "Incident Replay",
      "Evidence owner",
      workflow.incident_replay.enabled ? "active" : "ready",
      `${incidentCaseCount} failed case(s) packaged for replay-first review.`,
      workflow.incident_replay.enabled ? "Replay highest-risk cases before approving release." : "Keep replay pack attached for audit continuity."
    ),
    warRoomLane(
      "Reviewer Workflow",
      workflow.reviewer_workflow.review_lanes.join(", ") || "Release owner",
      workflow.reviewer_workflow.state,
      `${workflow.reviewer_workflow.required_approvers.length} required approver(s); waiver required ${workflow.waiver_policy.required ? "yes" : "no"}.`,
      workflow.reviewer_workflow.next_actions[0] || "No reviewer action required."
    ),
    warRoomLane(
      "Evidence & Audit",
      "Audit owner",
      workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length ? "required" : "optional",
      `${workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length} required artifact(s); redaction policy active.`,
      "Export JSON, Markdown, print/PDF, and bundle evidence before external review."
    ),
    warRoomLane(
      "Official Product Parity",
      "Product owner",
      officialMirror.available ? "mapped" : "missing",
      officialMirror.available
        ? `${officialMirror.page_count} official page(s), ${officialMirror.api_method_count} API method(s) mapped.`
        : "No official frontend mirror summary loaded.",
      officialMirror.available ? "Keep copying review/evidence logic, not secret, billing, or team mutation flows." : "Load clean-room official frontend summary."
    )
  ];

  return {
    schema_version: "a3.release_war_room.v1",
    available: summary.totalCases > 0,
    decision,
    decision_label: decision === "ship_ready" ? "Ship ready" : decision === "review_required" ? "Review required" : "No-go",
    urgency,
    run_id: summary.lastRunId || "unknown-run",
    release_version: workflow.release_version,
    environment: workflow.environment,
    revenue_risk_score: revenueRiskScore,
    blocks_merge: gate.pr_gate.blocks_merge,
    waiver_required: workflow.waiver_policy.required,
    incident_replay_case_count: incidentCaseCount,
    required_artifact_count: workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length,
    required_approvers: workflow.reviewer_workflow.required_approvers,
    top_risk_cases: gate.top_risk_cases,
    lanes,
    executive_brief: buildWarRoomExecutiveBrief({ summary, gate, workflow, revenueRiskScore, requestProvenance, usageQuota, mediaReadiness, officialMirror }),
    customer_value: "Gives release owners one screen for no-go decisions, incident replay, reviewer sign-off, and audit evidence before an agent reaches customers.",
    enterprise_readiness: {
      local_read_only: true,
      secret_free_exports: true,
      external_mutations_enabled: false,
      self_host_ready_contract: true,
      audit_bundle_required: true
    }
  };
}

export function summarizeIncidentReplayQueue(runFixture = {}, gradeFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const mediaReadiness = summarizeMediaReadiness(runFixture, gradeFixture, {}, mediaSignedUrlFixture);
  const failedCases = cases
    .filter((item) => !item.passed)
    .sort((left, right) => incidentReplayWeight(right) - incidentReplayWeight(left) || left.score - right.score)
    .slice(0, options.limit || 8);
  const queue = failedCases.map((item, index) => buildIncidentReplayItem(item, index, mediaReadiness));
  const ownerCounts = queue.reduce((counts, item) => {
    counts[item.owner_lane] = (counts[item.owner_lane] || 0) + 1;
    return counts;
  }, {});

  return {
    schema_version: "a3.incident_replay_queue.v1",
    available: queue.length > 0,
    replay_mode: "failed_cases_first",
    queue_count: queue.length,
    run_ids: uniqueSorted(queue.map((item) => item.run_id)),
    owner_counts: ownerCounts,
    blocker_count: queue.filter((item) => item.release_blocker).length,
    trace_ready_count: queue.filter((item) => item.trace_ready).length,
    tool_diff_ready_count: queue.filter((item) => item.tool_diff_count > 0).length,
    judge_evidence_ready_count: queue.filter((item) => item.judge_evidence_count > 0).length,
    media_evidence_ready_count: queue.filter((item) => item.media_evidence_count > 0 || item.vm_stream_count > 0).length,
    queue,
    replay_steps: [
      "Open the failed case detail before approving the release.",
      "Replay A1 trace events and tool-call diffs.",
      "Read linked A2 judge evidence and remediation.",
      "Compare expected vs actual response and required tools.",
      "Attach media evidence metadata when present.",
      "Record reviewer owner, disposition, and follow-up issue before waiver or merge."
    ],
    commercial_value: "Packages failed agent behavior into replay-first incident evidence so reviewers can reproduce risk before signing off."
  };
}

export function summarizeReviewerWorkflowBoard(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, options = {}) {
  const releaseWorkflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options);
  const releaseGate = summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, options.thresholds ? { thresholds: options.thresholds } : {});
  const incidentReplay = summarizeIncidentReplayQueue(runFixture, gradeFixture, mediaSignedUrlFixture, { limit: options.limit || 8 });
  const requiredApprovers = releaseWorkflow.reviewer_workflow?.required_approvers || [];
  const items = incidentReplay.queue.map((item) => buildReviewerWorkflowItem(item, releaseWorkflow));
  const reviewerGate = releaseWorkflow.reviewer_gate || {};
  const lanes = buildReviewerWorkflowLanes(items, requiredApprovers, reviewerGate.reviewer_lanes || []);
  const blockerCount = items.filter((item) => item.review_state === "blocked").length;
  const needsEvidenceCount = items.filter((item) => item.review_state === "needs_evidence").length;
  const waiverBlockedCount = items.filter((item) => item.waiver_state === "executive_exception_required").length;
  const approvalReadyCount = items.filter((item) => item.approval_ready).length;
  const boardState = releaseWorkflow.available
    ? blockerCount > 0 || releaseGate.pr_gate.blocks_merge
      ? "blocked"
      : needsEvidenceCount > 0 || items.length > 0 || releaseWorkflow.waiver_policy.required
        ? "needs_review"
        : "ready"
    : "no_evidence";

  return {
    schema_version: "a3.reviewer_workflow_board.v1",
    available: releaseWorkflow.available,
    board_state: boardState,
    board_label: boardState === "ready" ? "Ready" : boardState === "needs_review" ? "Needs review" : boardState === "blocked" ? "Blocked" : "No evidence",
    release_version: releaseWorkflow.release_version,
    environment: releaseWorkflow.environment,
    github_check: {
      name: releaseWorkflow.github_check.name,
      conclusion: releaseWorkflow.github_check.conclusion,
      blocks_merge: releaseWorkflow.github_check.blocks_merge
    },
    waiver_policy: {
      required: releaseWorkflow.waiver_policy.required,
      allowed: releaseWorkflow.waiver_policy.allowed,
      exceptional_only: releaseWorkflow.waiver_policy.exceptional_only,
      guidance: releaseWorkflow.waiver_policy.guidance
    },
    required_reviewer_count: requiredApprovers.length,
    required_approvers: requiredApprovers,
    open_item_count: items.filter((item) => item.review_state !== "closed").length,
    blocked_item_count: blockerCount,
    needs_evidence_count: needsEvidenceCount,
    waiver_blocked_count: waiverBlockedCount,
    approval_ready_count: approvalReadyCount,
    pr_gate_next_action: reviewerGate.pr_gate_next_action || releaseWorkflow.reviewer_workflow?.pr_gate_next_action || "",
    sign_off_risk: reviewerGate.sign_off_risk || releaseWorkflow.reviewer_workflow?.sign_off_risk || {},
    reviewer_gate: reviewerGate,
    lanes,
    items,
    a1_a2_calibration: {
      a1_trace_ready_count: incidentReplay.trace_ready_count,
      a1_tool_diff_ready_count: incidentReplay.tool_diff_ready_count,
      a2_judge_evidence_ready_count: incidentReplay.judge_evidence_ready_count,
      media_evidence_ready_count: incidentReplay.media_evidence_ready_count,
      coverage_available: summarizeCoverage(coverageFixture).available
    },
    review_steps: [
      "Start from A1 trace and observation evidence before changing release state.",
      "Compare A1 expected vs actual tool calls for every tool-related failure.",
      "Read A2 judge score, pass/fail, failure class, and remediation before assigning disposition.",
      "Keep media evidence metadata-only until signed URL safety is proven.",
      "Record owner lane and next action before waiver, approval, or merge."
    ],
    commercial_value: "Turns replay evidence into an owned reviewer board: who must review, what evidence is missing, and whether waiver or approval can proceed."
  };
}

function buildReviewerWorkflowItem(item = {}, releaseWorkflow = {}) {
  const requiredArtifacts = uniqueSorted([
    "case_detail",
    "expected_vs_actual",
    "release_gate",
    "a2_judge_evidence",
    "trace_timeline",
    item.tool_diff_count > 0 ? "tool_call_diff" : "",
    item.media_evidence_count > 0 || item.vm_stream_count > 0 ? "media_metadata" : ""
  ]);
  const readyArtifacts = uniqueSorted([
    "case_detail",
    "expected_vs_actual",
    "release_gate",
    item.judge_evidence_count > 0 ? "a2_judge_evidence" : "",
    item.trace_ready ? "trace_timeline" : "",
    item.tool_diff_count > 0 ? "tool_call_diff" : "",
    item.media_evidence_count > 0 || item.vm_stream_count > 0 ? "media_metadata" : ""
  ]);
  const missingArtifacts = requiredArtifacts.filter((artifact) => !readyArtifacts.includes(artifact));
  const waiverState = releaseWorkflow.waiver_policy?.exceptional_only
    ? "executive_exception_required"
    : releaseWorkflow.waiver_policy?.allowed
      ? "waiver_allowed"
      : releaseWorkflow.waiver_policy?.required
        ? "waiver_blocked"
        : "not_required";
  const reviewState = item.release_blocker || releaseWorkflow.github_check?.blocks_merge
    ? "blocked"
    : missingArtifacts.length > 0
      ? "needs_evidence"
      : releaseWorkflow.waiver_policy?.required
        ? "needs_owner_review"
        : "approval_ready";
  const approvalReady = reviewState === "approval_ready" && missingArtifacts.length === 0;

  return {
    case_id: item.case_id,
    run_id: item.run_id,
    scenario_id: item.scenario_id,
    owner_lane: item.owner_lane,
    review_state: reviewState,
    release_blocker: item.release_blocker,
    score: item.score,
    severity: item.severity,
    primary_failure_class: item.primary_failure_class,
    failure_summary: item.failure_summary,
    required_artifacts: requiredArtifacts,
    ready_artifacts: readyArtifacts,
    missing_artifacts: missingArtifacts,
    waiver_state: waiverState,
    waiver_allowed: waiverState === "waiver_allowed",
    approval_required: item.release_blocker || releaseWorkflow.waiver_policy?.required || releaseWorkflow.github_check?.blocks_merge,
    approval_ready: approvalReady,
    evidence_counts: {
      trace_events: item.trace_event_count,
      observations: item.observation_count,
      tool_diffs: item.tool_diff_count,
      judge_evidence: item.judge_evidence_count,
      media_evidence: item.media_evidence_count + item.vm_stream_count
    },
    next_action: reviewerWorkflowNextAction(item, reviewState, missingArtifacts, waiverState)
  };
}

function buildReviewerWorkflowLanes(items = [], requiredApprovers = [], gateLanes = []) {
  const laneNames = uniqueSorted([
    ...requiredApprovers,
    ...items.map((item) => item.owner_lane),
    ...gateLanes.map((lane) => lane.lane)
  ]);
  return laneNames.map((lane) => {
    const laneItems = items.filter((item) => item.owner_lane === lane);
    const gateLane = gateLanes.find((item) => item.lane === lane) || {};
    const blockedItems = laneItems.filter((item) => item.review_state === "blocked");
    const missingItems = laneItems.filter((item) => item.review_state === "needs_evidence");
    const approvalReadyItems = laneItems.filter((item) => item.approval_ready);
    const status = gateLane.status === "blocked"
      ? "blocked"
      : blockedItems.length
      ? "blocked"
      : gateLane.status === "needs_evidence" || missingItems.length
        ? "needs_evidence"
        : laneItems.length
          ? "needs_review"
          : gateLane.status || "standby";
    const itemCount = laneItems.length || gateLane.item_count || 0;
    const blockedCount = blockedItems.length || gateLane.blocker_count || 0;
    const missingEvidenceCount = missingItems.length || (gateLane.status === "needs_evidence" ? gateLane.item_count || 1 : 0);
    const approvalReadyCount = approvalReadyItems.length || gateLane.approval_ready_count || 0;
    const nextAction = gateLane.next_action
      || laneItems[0]?.next_action
      || (lane === "Release owner"
        ? "Confirm release gate outcome and collect reviewer sign-off."
        : "Stand by for assigned incident replay or approval request.");

    return {
      lane,
      owner: gateLane.owner || lane,
      item_count: itemCount,
      blocked_count: blockedCount,
      missing_evidence_count: missingEvidenceCount,
      approval_ready_count: approvalReadyCount,
      status,
      next_action: nextAction,
      source: gateLane.source || "a3.reviewer_workflow_board",
      evidence_refs: gateLane.evidence_refs || [],
      required_actions: gateLane.required_actions || []
    };
  });
}

function reviewerWorkflowNextAction(item = {}, reviewState = "", missingArtifacts = [], waiverState = "") {
  if (missingArtifacts.length > 0) {
    return `Collect missing evidence: ${missingArtifacts.join(", ")}.`;
  }
  if (reviewState === "blocked") {
    if (waiverState === "executive_exception_required") {
      return "Replay the case and request executive exception only if the release cannot wait.";
    }
    return "Replay the case and fix the blocker before approval.";
  }
  if (reviewState === "needs_owner_review") {
    return "Assign owner disposition and attach waiver follow-up evidence if risk is accepted.";
  }
  if (reviewState === "approval_ready") {
    return "Ready for reviewer approval after release owner sign-off.";
  }
  return item.failure_summary || "Review case evidence and record disposition.";
}

export function summarizeObservabilityReplayMatrix(runFixture = {}, gradeFixture = {}, mediaSignedUrlFixture = {}, frontendCodeCrawlFixture = {}, options = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const replayQueue = summarizeIncidentReplayQueue(runFixture, gradeFixture, mediaSignedUrlFixture, { limit: options.limit || 8 });
  const codeCrawl = summarizeOfficialCodeCrawlParity(frontendCodeCrawlFixture);
  const officialObservabilityMapped = officialObservabilityConfirmed(codeCrawl);
  const officialObservabilityChunkNames = officialObservabilityChunks(codeCrawl);
  const caseById = new Map(cases.map((item) => [item.case_id, item]));
  const items = replayQueue.queue.map((replayItem, index) => buildObservabilityReplayItem(
    replayItem,
    caseById.get(replayItem.case_id) || {},
    index,
    codeCrawl
  ));
  const lanes = buildObservabilityReplayLanes(items, codeCrawl);
  const traceReadyCount = items.filter((item) => item.trace_ready).length;
  const toolErrorCaseCount = items.filter((item) => item.tool_error_count > 0 || item.error_signal_count > 0).length;
  const latencyCaseCount = items.filter((item) => item.latency_ms > 0 || item.duration_ms > 0).length;
  const mediaCaseCount = items.filter((item) => item.media_evidence_count > 0).length;
  const judgeLinkedCount = items.filter((item) => item.judge_evidence_count > 0).length;
  const blockedReplayCount = items.filter((item) => item.production_risk === "blocker").length;

  return {
    schema_version: "a3.observability_replay_matrix.v1",
    available: items.length > 0,
    replay_case_count: items.length,
    trace_ready_count: traceReadyCount,
    tool_error_case_count: toolErrorCaseCount,
    latency_case_count: latencyCaseCount,
    media_case_count: mediaCaseCount,
    judge_linked_count: judgeLinkedCount,
    blocked_replay_count: blockedReplayCount,
    official_observability_confirmed: officialObservabilityMapped,
    official_observability_chunks: officialObservabilityChunkNames,
    lanes,
    items,
    a1_a2_calibration: {
      normalized_case_count: cases.length,
      a1_trace_ready_count: traceReadyCount,
      a1_tool_diff_ready_count: replayQueue.tool_diff_ready_count,
      a2_judge_evidence_ready_count: judgeLinkedCount,
      media_evidence_ready_count: mediaCaseCount
    },
    replay_steps: [
      "Open the failed case in A3 and confirm run id, case id, score, and failure class.",
      "Replay A1 trace events and observations before assigning a production disposition.",
      "Inspect tool-call diffs, tool errors, timeout/error text, and latency signals.",
      "Read A2 judge evidence and remediation to explain why the incident matters.",
      "Attach media metadata only; do not render live signed media URLs.",
      "Record whether the incident is reproducible, fixed, waived, or blocked before release."
    ],
    commercial_value: "Turns trace, tool errors, latency, judge findings, and media metadata into a production replay matrix that can block risky agent releases and support incident review."
  };
}

function buildObservabilityReplayItem(replayItem = {}, caseItem = {}, index = 0, codeCrawl = {}) {
  const traceEvents = Array.isArray(caseItem.trace_events) ? caseItem.trace_events : [];
  const observations = Array.isArray(caseItem.observations) ? caseItem.observations : [];
  const traceReady = replayItem.trace_ready || traceEvents.length > 0 || observations.length > 0;
  const toolErrorCount = countToolErrorSignals(caseItem);
  const errorSignalCount = countErrorSignals(caseItem);
  const latencyMs = numberOrDefault(caseItem.latency_ms, 0);
  const durationMs = numberOrDefault(caseItem.duration_ms, 0);
  const mediaEvidenceCount = Number(replayItem.media_evidence_count || 0) + Number(replayItem.vm_stream_count || 0);
  const productionRisk = replayItem.release_blocker || toolErrorCount > 0 || errorSignalCount > 0
    ? "blocker"
    : replayItem.tool_diff_count > 0 || replayItem.judge_evidence_count > 0
      ? "needs_replay"
      : "watch";
  const observabilityState = traceReady && replayItem.judge_evidence_count > 0
    ? productionRisk === "blocker" ? "blocked_with_evidence" : "replay_ready"
    : "needs_evidence";

  return {
    rank: index + 1,
    run_id: replayItem.run_id,
    case_id: replayItem.case_id,
    scenario_id: replayItem.scenario_id,
    owner_lane: replayItem.owner_lane,
    production_risk: productionRisk,
    observability_state: observabilityState,
    score: replayItem.score,
    severity: replayItem.severity,
    primary_failure_class: replayItem.primary_failure_class,
    trace_ready: traceReady,
    trace_event_count: traceEvents.length || replayItem.trace_event_count,
    observation_count: observations.length || replayItem.observation_count,
    latency_ms: latencyMs,
    duration_ms: durationMs,
    tool_diff_count: replayItem.tool_diff_count,
    tool_error_count: toolErrorCount,
    error_signal_count: errorSignalCount,
    judge_evidence_count: replayItem.judge_evidence_count,
    media_evidence_count: mediaEvidenceCount,
    official_parity_source: observabilityParitySource(codeCrawl),
    next_action: observabilityReplayNextAction({
      traceReady,
      productionRisk,
      toolErrorCount,
      errorSignalCount,
      judgeEvidenceCount: replayItem.judge_evidence_count,
      mediaEvidenceCount
    })
  };
}

function buildObservabilityReplayLanes(items = [], codeCrawl = {}) {
  const traceReadyCount = items.filter((item) => item.trace_ready).length;
  const toolErrorCount = items.filter((item) => item.tool_error_count > 0 || item.error_signal_count > 0).length;
  const latencyCount = items.filter((item) => item.latency_ms > 0 || item.duration_ms > 0).length;
  const judgeCount = items.filter((item) => item.judge_evidence_count > 0).length;
  const mediaCount = items.filter((item) => item.media_evidence_count > 0).length;
  const officialMapped = officialObservabilityConfirmed(codeCrawl);

  return [
    observabilityLane("Trace Timeline", traceReadyCount, items.length, traceReadyCount === items.length ? "ready" : "needs_evidence", "Replay A1 trace events and observations for every queued incident."),
    observabilityLane("Tool Errors", toolErrorCount, items.length, toolErrorCount > 0 ? "active" : "watch", "Inspect tool errors, timeouts, wrong tools, wrong arguments, and tool-order drift."),
    observabilityLane("Latency / Duration", latencyCount, items.length, latencyCount > 0 ? "active" : "watch", "Use latency or duration fields when available; request A1 timing evidence when missing."),
    observabilityLane("A2 Judge Link", judgeCount, items.length, judgeCount === items.length ? "ready" : "needs_evidence", "Read A2 failure class, score, summary, details, and remediation before disposition."),
    observabilityLane("Media Metadata", mediaCount, items.length, mediaCount > 0 ? "metadata_only" : "watch", "Attach media metadata only and keep live signed URLs blocked."),
    observabilityLane("Official Observability Parity", officialMapped ? 1 : 0, 1, officialMapped ? "mapped" : "unconfirmed", "Use official Observability code-crawl signals as product reference, not copied source.")
  ];
}

function observabilityLane(lane, readyCount, totalCount, status, nextAction) {
  return {
    lane,
    ready_count: readyCount,
    total_count: totalCount,
    status,
    next_action: nextAction
  };
}

function observabilityReplayNextAction({
  traceReady = false,
  productionRisk = "watch",
  toolErrorCount = 0,
  errorSignalCount = 0,
  judgeEvidenceCount = 0,
  mediaEvidenceCount = 0
} = {}) {
  if (!traceReady) {
    return "Request A1 trace/observation evidence before production replay sign-off.";
  }
  if (judgeEvidenceCount === 0) {
    return "Request A2 judge evidence before assigning incident disposition.";
  }
  if (productionRisk === "blocker") {
    return toolErrorCount > 0 || errorSignalCount > 0
      ? "Replay tool/error path and block release until owner records fix or exception."
      : "Replay high-risk trace and block release until reviewer disposition is recorded.";
  }
  if (mediaEvidenceCount > 0) {
    return "Review media metadata and attach it to the replay packet without rendering signed URLs.";
  }
  return "Replay trace, confirm expected vs actual, and record reviewer disposition.";
}

function observabilityParitySource(codeCrawl = {}) {
  const chunks = officialObservabilityChunks(codeCrawl);
  return chunks[0] || "ObservabilityPage clean-room signal";
}

function officialObservabilityConfirmed(codeCrawl = {}) {
  return Array.isArray(codeCrawl.parity_targets) && codeCrawl.parity_targets.some((target) => target.target === "Trace observability");
}

function officialObservabilityChunks(codeCrawl = {}) {
  return (Array.isArray(codeCrawl.chunks) ? codeCrawl.chunks : [])
    .filter((chunk) => /observability|trace|latency|error/i.test(`${chunk.role} ${chunk.chunk} ${chunk.a3_decision}`))
    .map((chunk) => chunk.chunk);
}

function countToolErrorSignals(item = {}) {
  const values = [
    ...(Array.isArray(item.trace_events) ? item.trace_events : []),
    ...(Array.isArray(item.observations) ? item.observations : [])
  ];
  return values.filter((entry) => /tool-error|timeout|error|failed|failure/i.test(JSON.stringify(entry))).length;
}

function countErrorSignals(item = {}) {
  return /timeout|error|failed|failure|exception/i.test(JSON.stringify({
    failure_summary: item.failure_summary,
    trace_events: item.trace_events,
    observations: item.observations,
    actual: item.actual
  })) ? 1 : 0;
}

export function summarizeRegressionFactory(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, frontendCodeCrawlFixture = {}, options = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const incidentReplay = summarizeIncidentReplayQueue(runFixture, gradeFixture, mediaSignedUrlFixture, { limit: options.limit || 10 });
  const observability = summarizeObservabilityReplayMatrix(runFixture, gradeFixture, mediaSignedUrlFixture, frontendCodeCrawlFixture, { limit: options.limit || 10 });
  const codeCrawl = summarizeOfficialCodeCrawlParity(frontendCodeCrawlFixture);
  const caseById = new Map(cases.map((item) => [item.case_id, item]));
  const observabilityByCase = new Map(observability.items.map((item) => [item.case_id, item]));
  const candidates = incidentReplay.queue.map((item, index) => buildRegressionCandidate(
    item,
    caseById.get(item.case_id) || {},
    observabilityByCase.get(item.case_id) || {},
    coverage,
    index
  ));
  const readyCount = candidates.filter((item) => item.generator_state === "ready_to_promote").length;
  const blockedCount = candidates.filter((item) => item.generator_state === "blocked").length;
  const needsEvidenceCount = candidates.filter((item) => item.generator_state === "needs_evidence").length;
  const coverageGapCount = candidates.filter((item) => item.coverage_status === "coverage_gap").length;
  const toolCandidateCount = candidates.filter((item) => item.tool_diff_count > 0).length;
  const mediaCandidateCount = candidates.filter((item) => item.media_evidence_count > 0).length;
  const officialResultsMapped = officialResultsReviewConfirmed(codeCrawl);

  return {
    schema_version: "a3.regression_factory.v1",
    available: candidates.length > 0,
    factory_state: blockedCount > 0 ? "blocked" : needsEvidenceCount > 0 ? "needs_evidence" : readyCount > 0 ? "ready" : "empty",
    candidate_count: candidates.length,
    ready_count: readyCount,
    needs_evidence_count: needsEvidenceCount,
    blocked_count: blockedCount,
    coverage_gap_count: coverageGapCount,
    tool_candidate_count: toolCandidateCount,
    media_candidate_count: mediaCandidateCount,
    official_results_review_confirmed: officialResultsMapped,
    generated_suite_plan: {
      suite_id: `a3-regression-${incidentReplay.run_ids.join("-") || "local"}`,
      source_mode: incidentReplay.replay_mode,
      target_paths: [
        "packages/scenarios/a2_g3_full_pack.json",
        "fixtures/a2/runs/*.json",
        "fixtures/a2/results/*_grade.json",
        "fixtures/a3/p3/*.redacted.json"
      ],
      redaction_required: true,
      live_cloud_mutation_required: false
    },
    lanes: buildRegressionFactoryLanes(candidates, coverage, officialResultsMapped),
    candidates,
    a1_a2_calibration: {
      normalized_case_count: cases.length,
      a1_trace_ready_count: candidates.filter((item) => item.trace_ready).length,
      a1_tool_diff_ready_count: toolCandidateCount,
      a2_judge_evidence_ready_count: candidates.filter((item) => item.judge_evidence_count > 0).length,
      coverage_available: coverage.available,
      official_results_review_confirmed: officialResultsMapped
    },
    promotion_steps: [
      "Start from failed incident replay cases, not hand-written demo scenarios.",
      "Require A1 trace, expected vs actual, and tool-call diff evidence before promotion.",
      "Require A2 judge score, failure class, and remediation before marking the regression ready.",
      "Map the case to A2 coverage and failure taxonomy so the suite improves release coverage.",
      "Keep media evidence metadata-only and do not embed live signed URLs in generated regressions.",
      "Attach the generated regression suite to PR gate and audit bundle outputs before merge."
    ],
    commercial_value: "Converts production failures into repeatable regression candidates so teams can prove a risky agent fix will not regress before the next release."
  };
}

export function summarizeExportRedactionFirewall(runFixture = {}, gradeFixture = {}, coverageFixture = {}, mediaSignedUrlFixture = {}, frontendCodeCrawlFixture = {}, options = {}) {
  const cases = normalizeCases(runFixture, gradeFixture);
  const scanCases = cases.map((item) => ({
    run_id: item.run_id,
    case_id: item.case_id,
    scenario_id: item.scenario_id,
    title: item.title,
    failure_summary: item.failure_summary,
    expected: item.expected,
    actual: item.actual,
    tool_call_diffs: buildToolCallDiffs(item),
    media_evidence: item.media_evidence || null,
    judge_modes: item.judge_modes,
    score: item.score,
    passed: item.passed,
    primary_failure_class: item.primary_failure_class
  }));
  const jsonResult = options.jsonResult || redactExport({
    cases: scanCases,
    coverage: coverageFixture,
    media_signed_url_coverage: mediaSignedUrlFixture,
    official_code_crawl: frontendCodeCrawlFixture
  }, { surface: "json_report" });
  const markdownResult = redactExport(scanCases.map((item) => [
    item.case_id,
    item.title,
    item.failure_summary,
    stableJson(item.expected),
    stableJson(item.actual),
    stableJson(item.media_evidence)
  ].join(" | ")).join("\n"), { surface: "markdown_report" });
  const printResult = redactExport({
    summary: buildDashboardSummary(runFixture, gradeFixture),
    cases: scanCases.map((item) => ({
      case_id: item.case_id,
      title: item.title,
      failure_summary: item.failure_summary,
      primary_failure_class: item.primary_failure_class,
      score: item.score
    }))
  }, { surface: "print_report" });
  const csvResult = scanCsvExportSurface(cases);
  const summary = summarizeRedactionResults([
    jsonResult,
    markdownResult,
    csvResult,
    printResult
  ]);

  return {
    schema_version: "a3.export_redaction_firewall.v1",
    available: true,
    policy_version: summary.policy.policy_version,
    status: summary.status,
    secret_free_exports: summary.secret_free_exports,
    fail_closed_ready: summary.fail_closed_ready,
    replacement_count: summary.replacement_count,
    residual_finding_count: summary.residual_finding_count,
    blocking_finding_count: summary.blocking_finding_count,
    surface_count: summary.surfaces.length,
    checked_surfaces: summary.surfaces,
    categories: summary.categories,
    patterns: summary.patterns,
    export_surfaces: [
      "json_report",
      "csv_report",
      "markdown_report",
      "print_report",
      "gate_cli_payload",
      "github_check_payload",
      "audit_bundle_index"
    ],
    a1_a2_calibration: {
      a1_case_count: cases.length,
      a1_trace_ready_count: cases.filter((item) => item.trace_ready || (item.trace_events || []).length > 0).length,
      a1_tool_diff_case_count: cases.filter((item) => buildToolCallDiffs(item).length > 0).length,
      a2_grade_count: Array.isArray(gradeFixture.grade_results) ? gradeFixture.grade_results.length : 0,
      a2_failure_class_count: new Set(cases.map((item) => item.primary_failure_class).filter(Boolean)).size
    },
    guardrails: [
      "Scrub API keys, bearer tokens, cookies, emails, prefixed tokens, signed media URLs, and local user-home paths before export.",
      "Run CSV formula hardening on every cell before spreadsheet download.",
      "Keep live signed media URLs out of JSON, Markdown, CSV, print, GitHub, and audit bundle outputs.",
      "Treat residual blocking findings after redaction as export-blocking.",
      "Use A1 trace/tool evidence and A2 judge/failure evidence only after the same export firewall pass."
    ],
    commercial_value: "Makes A3 reports safer to share in PRs, audits, and enterprise review packets by proving exports are scrubbed before they leave the dashboard or CLI."
  };
}

function buildRegressionCandidate(replayItem = {}, caseItem = {}, observabilityItem = {}, coverage = {}, index = 0) {
  const traceReady = replayItem.trace_ready || observabilityItem.trace_ready === true;
  const judgeReady = replayItem.judge_evidence_count > 0 || observabilityItem.judge_evidence_count > 0;
  const toolDiffCount = numberOrDefault(replayItem.tool_diff_count, 0);
  const mediaEvidenceCount = Number(replayItem.media_evidence_count || 0) + Number(replayItem.vm_stream_count || 0);
  const coverageStatus = regressionCoverageStatus(replayItem.primary_failure_class, coverage);
  const blocked = replayItem.release_blocker || replayItem.severity === "critical";
  const generatorState = !traceReady || !judgeReady
    ? "needs_evidence"
    : blocked
      ? "blocked"
      : "ready_to_promote";
  const requiredContracts = regressionRequiredContracts({ traceReady, judgeReady, toolDiffCount, mediaEvidenceCount, coverageStatus });
  const expectedToolCount = normalizeToolCalls(caseItem.expected?.tool_calls).length;
  const actualToolCount = normalizeToolCalls(caseItem.actual?.tool_calls).length;

  return {
    rank: index + 1,
    regression_id: `regression-${replayItem.case_id || index + 1}`,
    case_id: replayItem.case_id,
    run_id: replayItem.run_id,
    scenario_id: replayItem.scenario_id,
    owner_lane: regressionOwnerLane(replayItem),
    generator_state: generatorState,
    release_blocker: Boolean(replayItem.release_blocker),
    coverage_status: coverageStatus,
    primary_failure_class: replayItem.primary_failure_class,
    severity: replayItem.severity,
    score: replayItem.score,
    trace_ready: traceReady,
    trace_event_count: replayItem.trace_event_count,
    observation_count: replayItem.observation_count,
    tool_diff_count: toolDiffCount,
    expected_tool_count: expectedToolCount,
    actual_tool_count: actualToolCount,
    judge_evidence_count: Math.max(numberOrDefault(replayItem.judge_evidence_count, 0), numberOrDefault(observabilityItem.judge_evidence_count, 0)),
    media_evidence_count: mediaEvidenceCount,
    required_contracts: requiredContracts,
    proposed_assertions: regressionAssertions(replayItem.primary_failure_class, caseItem),
    generated_artifacts: [
      `scenario:${replayItem.scenario_id || "unknown"}`,
      `run_fixture:${replayItem.case_id || "unknown"}`,
      `grade_fixture:${replayItem.case_id || "unknown"}`,
      "pr_gate_regression_note"
    ],
    next_action: regressionNextAction({ generatorState, coverageStatus, toolDiffCount, mediaEvidenceCount, releaseBlocker: replayItem.release_blocker })
  };
}

function buildRegressionFactoryLanes(candidates = [], coverage = {}, officialResultsMapped = false) {
  const total = candidates.length;
  return [
    regressionFactoryLane("A1 Trace Capture", candidates.filter((item) => item.trace_ready).length, total, "Trace, observations, expected vs actual, and tool-call diffs must be replayable."),
    regressionFactoryLane("A2 Judge Contract", candidates.filter((item) => item.judge_evidence_count > 0).length, total, "Judge score, failure class, severity, and remediation must be attached."),
    regressionFactoryLane("Coverage Promotion", candidates.filter((item) => item.coverage_status === "covered").length, total, coverage.available ? "Promote gaps into A2 coverage instead of adding isolated one-off tests." : "Load A2 coverage report before suite promotion."),
    regressionFactoryLane("Tool Regression", candidates.filter((item) => item.tool_diff_count > 0).length, total, "Tool failures need expected/actual call and argument assertions."),
    regressionFactoryLane("Media Regression", candidates.filter((item) => item.media_evidence_count > 0).length, total, "Media cases stay metadata-only until signed URL safety is proven."),
    regressionFactoryLane("Official Results Parity", officialResultsMapped ? 1 : 0, 1, "Match official Results review concepts without copying official frontend source.")
  ];
}

function regressionFactoryLane(lane, readyCount, totalCount, nextAction) {
  const status = totalCount === 0
    ? "empty"
    : readyCount === totalCount
      ? "ready"
      : readyCount > 0
        ? "partial"
        : "needs_evidence";
  return {
    lane,
    ready_count: readyCount,
    total_count: totalCount,
    status,
    next_action: nextAction
  };
}

function regressionCoverageStatus(failureClass = "none", coverage = {}) {
  if (!coverage.available) {
    return "unknown";
  }
  const executable = objectOr(coverage.executable_failure_class_cases);
  const golden = objectOr(coverage.golden_failure_class_cases);
  const hasExecutable = Array.isArray(executable[failureClass]) && executable[failureClass].length > 0;
  const hasGolden = Array.isArray(golden[failureClass]) && golden[failureClass].length > 0;
  return hasExecutable && hasGolden ? "covered" : "coverage_gap";
}

function regressionRequiredContracts({ traceReady = false, judgeReady = false, toolDiffCount = 0, mediaEvidenceCount = 0, coverageStatus = "unknown" } = {}) {
  return uniqueSorted([
    "case_id",
    "scenario_id",
    "expected_vs_actual",
    traceReady ? "a1_trace_events" : "missing_a1_trace_events",
    judgeReady ? "a2_judge_evidence" : "missing_a2_judge_evidence",
    toolDiffCount > 0 ? "tool_call_diff" : "response_assertion",
    mediaEvidenceCount > 0 ? "media_metadata" : "",
    coverageStatus === "coverage_gap" ? "coverage_update" : "coverage_link"
  ]);
}

function regressionOwnerLane(item = {}) {
  if (item.primary_failure_class === "unsafe_or_policy_violation") {
    return "Safety regression owner";
  }
  if (/tool|argument|order/.test(item.primary_failure_class || "")) {
    return "Runner/tool regression owner";
  }
  if (item.media_evidence_count > 0 || item.vm_stream_count > 0) {
    return "Media regression owner";
  }
  return "Judge regression owner";
}

function regressionAssertions(failureClass = "", caseItem = {}) {
  const base = ["preserve_case_prompt", "compare_expected_vs_actual_response", `assert_failure_class:${failureClass || "unknown"}`];
  const expectedTools = normalizeToolCalls(caseItem.expected?.tool_calls);
  if (expectedTools.length > 0 || /tool|argument|order/.test(failureClass)) {
    base.push("assert_expected_tool_sequence");
    base.push("assert_tool_arguments");
  }
  if (failureClass === "unsafe_or_policy_violation") {
    base.push("assert_no_secret_or_policy_leak");
  }
  if (failureClass === "missing_clarification") {
    base.push("assert_clarification_question");
  }
  if ((caseItem.media_evidence?.media_types || []).length > 0) {
    base.push("assert_media_metadata_only");
  }
  return uniqueSorted(base);
}

function regressionNextAction({ generatorState = "needs_evidence", coverageStatus = "unknown", toolDiffCount = 0, mediaEvidenceCount = 0, releaseBlocker = false } = {}) {
  if (generatorState === "needs_evidence") {
    return "Collect A1 trace and A2 judge evidence before generating a regression.";
  }
  if (releaseBlocker) {
    return "Keep release blocked; promote this case only after owner fix and reviewer disposition.";
  }
  if (coverageStatus === "coverage_gap") {
    return "Add this failure class to A2 coverage and then generate run/grade fixtures.";
  }
  if (toolDiffCount > 0) {
    return "Generate tool-call regression assertions from expected vs actual diff rows.";
  }
  if (mediaEvidenceCount > 0) {
    return "Generate metadata-only media regression and keep live media URLs out of fixtures.";
  }
  return "Promote to regression suite and bind it to PR gate before next release.";
}

function officialResultsReviewConfirmed(codeCrawl = {}) {
  return Array.isArray(codeCrawl.parity_targets) && codeCrawl.parity_targets.some((target) => target.target === "Results review");
}

function gateCheck(id, passed, observed, detail) {
  return { id, passed, observed, detail };
}

function normalizeReleaseGateThresholds(value = {}) {
  return {
    pass_rate_min: numberOrDefault(value.pass_rate_min, 95),
    trace_completeness_min: numberOrDefault(value.trace_completeness_min, 90),
    hard_block_pass_rate_min: numberOrDefault(value.hard_block_pass_rate_min, 80),
    hard_block_trace_completeness_min: numberOrDefault(value.hard_block_trace_completeness_min, 70)
  };
}

function numberOrDefault(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildReleasePrCommentMarkdown(gate, summary, options = {}) {
  const reviewerGate = options.reviewerGate || {};
  const lines = [
    "## Ashr++ Release Gate",
    "",
    `Decision: **${gate.decision_label}**`,
    `Risk score: **${gate.risk_score}**`,
    `Release: \`${options.release_version || "candidate"}\``,
    `Environment: \`${options.environment || "staging"}\``,
    `Owner: ${options.owner || "Release owner"}`,
    "",
    "| Signal | Value |",
    "|---|---|",
    `| Run | \`${summary.lastRunId || "unknown-run"}\` |`,
    `| Pass rate | ${summary.passRate}% |`,
    `| Average score | ${summary.avgScore} |`,
    `| Trace completeness | ${summary.traceCompleteness}% |`,
    `| Failed checks | ${gate.failed_checks.join(", ") || "none"} |`,
    `| PR gate next action | ${reviewerGate.pr_gate_next_action || "Follow release gate decision."} |`,
    `| Sign-off risk | ${reviewerGate.sign_off_risk?.level || "unknown"} |`,
    "",
    "### Required Reviewers",
    "",
    ...(gate.required_approvers.length ? gate.required_approvers.map((item) => `- ${item}`) : ["- none"]),
    "",
    "### Top Risk Cases",
    "",
    ...(gate.top_risk_cases.length
      ? gate.top_risk_cases.map((item) => `- \`${item.case_id}\`: ${item.primary_failure_class} / ${item.severity} / ${item.score} - ${item.summary}`)
      : ["- none"])
  ];
  if (reviewerGate.available) {
    lines.push(
      "",
      "### Reviewer Gate",
      "",
      `- Next action: ${reviewerGate.pr_gate_next_action}`,
      `- Sign-off risk: ${reviewerGate.sign_off_risk.level} (${reviewerGate.sign_off_risk.score})`,
      `- A2 blockers: ${reviewerGate.a2_release_gate?.blocker_gates?.join(", ") || "none"}`,
      `- A1 trace/tool-call evidence: trace ${reviewerGate.a1_evidence?.trace_ready_count || 0}, tool diffs ${reviewerGate.a1_evidence?.tool_diff_ready_count || 0}`,
      "",
      "### Reviewer Lanes",
      "",
      ...reviewerGate.reviewer_lanes.map((lane) => `- ${lane.lane}: ${lane.status} / ${lane.owner} - ${lane.next_action}`)
    );
  }
  return `${lines.join("\n")}\n`;
}

function buildReleaseNextActions(gate) {
  if (gate.decision === "approve_release") {
    return [
      "Attach JSON and Markdown audit artifacts to the release record.",
      "Keep the print/PDF report for sign-off evidence.",
      "Monitor the next production replay batch."
    ];
  }
  const actions = [
    "Review failed gate checks before merge.",
    "Replay the top risk cases from the incident replay pack.",
    "Attach waiver evidence only if the required approvers accept the risk."
  ];
  if (gate.failed_checks.includes("pass_rate")) {
    actions.push("Raise pass rate above the commercial threshold or narrow the release scope.");
  }
  if (gate.failed_checks.includes("required_tool_coverage")) {
    actions.push("Fix missing required tool coverage before customer-facing release.");
  }
  if (gate.failed_checks.includes("policy_failures")) {
    actions.push("Route unsafe or forbidden-tool cases to safety review.");
  }
  return actions;
}

function warRoomLane(lane, owner, status, evidence, nextAction) {
  return {
    lane,
    owner,
    status,
    evidence,
    next_action: nextAction
  };
}

function buildIncidentReplayItem(item, index, mediaReadiness = {}) {
  const toolDiffs = buildToolCallDiffs(item);
  const nonMatchingDiffs = toolDiffs.filter((diff) => diff.status !== "match");
  const traceEvents = Array.isArray(item.trace_events) ? item.trace_events : [];
  const observations = Array.isArray(item.observations) ? item.observations : [];
  const judgeEvidence = toolDiffs.flatMap((diff) => diff.judge_evidence || []);
  const media = item.media_evidence || {};
  const mediaEvidenceItems = Array.isArray(media.evidence_items) ? media.evidence_items : [];
  const vmStreams = Array.isArray(media.vm_streams) ? media.vm_streams : [];
  const traceReady = traceEvents.length > 0 || observations.length > 0;
  const releaseBlocker = ["critical", "blocker", "major", "high"].includes(item.severity)
    || [
      "unsafe_or_policy_violation",
      "forbidden_tool_call",
      "missing_required_tool"
    ].includes(item.primary_failure_class);
  const ownerLane = incidentReplayOwnerLane(item.primary_failure_class, {
    hasToolDiffs: nonMatchingDiffs.length > 0,
    hasMedia: mediaEvidenceItems.length > 0 || vmStreams.length > 0
  });

  return {
    rank: index + 1,
    run_id: item.run_id || "unknown-run",
    case_id: item.case_id,
    scenario_id: item.scenario_id,
    title: item.title,
    status: item.passed ? "passed" : "failed",
    score: normalizeScore(item.score),
    severity: item.severity || "major",
    primary_failure_class: item.primary_failure_class || "wrong_intent",
    failure_summary: item.failure_summary,
    release_blocker: releaseBlocker,
    owner_lane: ownerLane,
    trace_ready: traceReady,
    trace_event_count: traceEvents.length,
    observation_count: observations.length,
    tool_diff_count: nonMatchingDiffs.length,
    tool_diff_statuses: uniqueSorted(nonMatchingDiffs.map((diff) => diff.status)),
    judge_evidence_count: judgeEvidence.length,
    judge_modes: uniqueSorted(item.judge_modes || []),
    media_evidence_count: mediaEvidenceItems.length,
    vm_stream_count: vmStreams.length,
    media_types: sortMediaChannels([
      media.primary_media_type,
      ...(Array.isArray(media.media_types) ? media.media_types : []),
      ...mediaEvidenceItems.map((entry) => entry.type)
    ].map(canonicalMediaChannel).filter(Boolean)),
    signed_url_policy: mediaReadiness.live_rendering_allowed
      ? "live_preview_allowed"
      : "metadata_only",
    replay_actions: buildIncidentReplayActions(item, {
      traceReady,
      nonMatchingDiffs,
      judgeEvidence,
      mediaEvidenceItems,
      vmStreams
    }),
    reviewer_packet: {
      required: true,
      owner_lane: ownerLane,
      artifacts: uniqueSorted([
        "case_detail",
        traceReady ? "trace_timeline" : "",
        nonMatchingDiffs.length ? "tool_call_diff" : "",
        judgeEvidence.length ? "a2_judge_evidence" : "",
        mediaEvidenceItems.length || vmStreams.length ? "media_metadata" : "",
        "expected_vs_actual",
        "release_gate"
      ])
    }
  };
}

function incidentReplayOwnerLane(failureClass = "", { hasToolDiffs = false, hasMedia = false } = {}) {
  if (["unsafe_or_policy_violation", "forbidden_tool_call"].includes(failureClass)) {
    return "Safety reviewer";
  }
  if ([
    "missing_required_tool",
    "wrong_tool",
    "wrong_arguments",
    "wrong_tool_order",
    "hallucinated_tool_result",
    "ignored_tool_result"
  ].includes(failureClass) || hasToolDiffs) {
    return "Runner/tooling owner";
  }
  if (hasMedia) {
    return "Media evidence owner";
  }
  if (failureClass === "missing_clarification") {
    return "Conversation design owner";
  }
  return "A3 triage owner";
}

function buildIncidentReplayActions(item, {
  traceReady = false,
  nonMatchingDiffs = [],
  judgeEvidence = [],
  mediaEvidenceItems = [],
  vmStreams = []
} = {}) {
  return [
    replayAction("case_detail", true, "Open case detail and confirm expected vs actual behavior."),
    replayAction("trace_timeline", traceReady, traceReady ? "Replay A1 trace/observation timeline." : "Trace is missing; request A1 trace evidence."),
    replayAction("tool_call_diff", nonMatchingDiffs.length > 0, nonMatchingDiffs.length ? `Inspect ${nonMatchingDiffs.length} non-matching tool-call diff(s).` : "No tool-call diff evidence is attached."),
    replayAction("a2_judge_evidence", judgeEvidence.length > 0 || (item.judge_results || []).length > 0, "Read A2 judge summary, severity, remediation, and evidence ids."),
    replayAction("media_metadata", mediaEvidenceItems.length > 0 || vmStreams.length > 0, "Review media evidence metadata only; do not render live signed URLs."),
    replayAction("release_decision", true, "Record reviewer disposition before waiver, approval, or merge.")
  ];
}

function replayAction(action, ready, detail) {
  return {
    action,
    ready: Boolean(ready),
    detail
  };
}

function incidentReplayWeight(item = {}) {
  return releaseGateCaseWeight(item)
    + (item.media_evidence ? 15 : 0)
    + buildToolCallDiffs(item).filter((diff) => diff.status !== "match").length * 10
    + ((item.judge_results || []).length ? 5 : 0);
}

function buildWarRoomExecutiveBrief({
  summary,
  gate,
  workflow,
  revenueRiskScore,
  requestProvenance,
  usageQuota,
  mediaReadiness,
  officialMirror
} = {}) {
  return [
    `${gate.decision_label} for run ${summary.lastRunId || "unknown-run"} with ${summary.passRate}% pass rate and ${summary.failed} failed case(s).`,
    `Revenue risk score is ${revenueRiskScore}; PR gate ${workflow.github_check.blocks_merge ? "blocks merge" : workflow.github_check.conclusion}.`,
    workflow.incident_replay.enabled
      ? `${workflow.incident_replay.case_ids.length} case(s) are packaged for replay-first incident review.`
      : "No failed case replay pack is required for the current evidence package.",
    `${workflow.audit_bundle.artifacts.filter((artifact) => artifact.required).length} required audit artifact(s) must travel with the release record.`,
    requestProvenance.available
      ? `Request provenance is available for ${requestProvenance.total_requests} request sample(s).`
      : "Request provenance is not available for this source.",
    usageQuota.available
      ? `Usage/quota calibration is present; direct API-key access ${usageQuota.direct_api_accessible ? "works" : "is limited or OAuth-gated"}.`
      : "Usage/quota calibration is not loaded.",
    mediaReadiness.available
      ? `Media evidence is present with live rendering ${mediaReadiness.live_rendering_allowed ? "allowed" : "blocked by safety"}.`
      : "No media evidence is loaded.",
    officialMirror.available
      ? `Official frontend mirror maps ${officialMirror.page_count} page(s) and ${officialMirror.api_method_count} API method name(s).`
      : "Official frontend mirror map is not loaded."
  ];
}

function auditArtifact(id, path, required, purpose) {
  return { id, path, required, purpose };
}

function releaseGateCaseWeight(item) {
  const severityWeight = {
    critical: 5,
    blocker: 5,
    high: 4,
    major: 3,
    medium: 2,
    minor: 1,
    low: 1,
    none: 0
  };
  const failureWeight = {
    unsafe_or_policy_violation: 5,
    forbidden_tool_call: 4,
    missing_required_tool: 3,
    wrong_tool: 3,
    wrong_arguments: 2
  };
  return (severityWeight[item.severity] || 0) * 1000
    + (failureWeight[item.primary_failure_class] || 0) * 100
    + (100 - Number(item.score || 0));
}

function unique(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function gapItem(area, confirmed, note) {
  return {
    area,
    confirmed: Boolean(confirmed),
    note
  };
}

function officialPage(page, path, a3Status, mvpDecision) {
  return {
    page,
    path,
    a3_status: a3Status,
    mvp_decision: mvpDecision
  };
}

function classifyOfficialMirrorDecision(decision = "") {
  const text = String(decision).toLowerCase();
  if (!text.trim()) {
    return "unknown";
  }
  if (text.includes("future")) {
    return "future";
  }
  if (text.includes("highest priority") || text.includes("copy dataset/run/case")) {
    return "copy";
  }
  if (text.includes("copy audit") || text.includes("copy report") || text.includes("copy pass-rate")) {
    return "partial";
  }
  if (
    text.includes("do not copy")
    || text.includes("skip")
    || text.includes("out of scope")
    || text.includes("low priority")
  ) {
    return "out_of_scope";
  }
  if (
    text.includes("copy")
    || text.includes("show")
    || text.includes("read-only")
    || text.includes("use ")
  ) {
    return "partial";
  }
  return "unknown";
}

function classifyOfficialCodeCrawlDecision(decision = "") {
  const text = String(decision).toLowerCase();
  if (!text.trim()) {
    return "unknown";
  }
  if (text.includes("copy_now") || text.includes("copy_results") || text.includes("copy_dataset")) {
    return "copy";
  }
  if (
    text.includes("partial")
    || text.includes("metadata_only")
    || text.includes("read_only")
    || text.includes("copy_trace")
    || text.includes("copy_trust")
    || text.includes("copy_pass_rate")
    || text.includes("local_report")
  ) {
    return "partial";
  }
  if (text.includes("future") || text.includes("next")) {
    return "future";
  }
  if (text.includes("do_not_copy") || text.includes("out_of_scope") || text.includes("disabled")) {
    return "out_of_scope";
  }
  if (text.includes("copy") || text.includes("use ")) {
    return "partial";
  }
  return "unknown";
}

function countOfficialMirrorStatuses(items = []) {
  const counts = {
    copy: 0,
    partial: 0,
    future: 0,
    out_of_scope: 0,
    unknown: 0
  };
  for (const item of items) {
    const status = item.a3_status;
    if (status in counts) {
      counts[status] += 1;
    } else {
      counts.unknown += 1;
    }
  }
  return counts;
}

function usageQuotaChannelsFromText(value = "") {
  const text = String(value).toLowerCase();
  return [
    text.includes("image") ? "images" : "",
    text.includes("audio") ? "audio" : "",
    text.includes("file") ? "files" : "",
    text.includes("video") ? "video" : ""
  ].filter(Boolean);
}

function buildMediaChannelMatrix({
  channels = [],
  usageChannels = [],
  mediaCases = [],
  outputPathTypes = [],
  confirmedSignedUrlTypes = [],
  unconfirmedSignedUrlTypes = [],
  renderLiveLinks = false
} = {}) {
  return channels.map((channel) => {
    const caseEvidenceCount = mediaCases.filter((item) => caseHasMediaChannel(item, channel)).length;
    const signedUrlConfirmed = confirmedSignedUrlTypes.includes(channel);
    const signedUrlUnconfirmed = unconfirmedSignedUrlTypes.includes(channel);
    const outputPathConfirmed = outputPathTypes.includes(channel);
    const usageObserved = usageChannels.includes(channel);
    const livePreviewAllowed = renderLiveLinks && signedUrlConfirmed && !signedUrlUnconfirmed;
    const previewPolicy = livePreviewAllowed
      ? "live_preview_allowed"
      : signedUrlConfirmed
        ? "redacted_signed_url_metadata_only"
        : channel === "vm_stream"
          ? "vm_stream_summary_only"
          : "metadata_only";

    return {
      channel,
      usage_observed: usageObserved,
      case_evidence_count: caseEvidenceCount,
      output_path_confirmed: outputPathConfirmed,
      signed_url_confirmed: signedUrlConfirmed,
      signed_url_unconfirmed: signedUrlUnconfirmed,
      live_preview_allowed: livePreviewAllowed,
      preview_policy: previewPolicy,
      decision: mediaChannelDecision(channel, {
        caseEvidenceCount,
        outputPathConfirmed,
        signedUrlConfirmed,
        signedUrlUnconfirmed,
        livePreviewAllowed
      })
    };
  });
}

function buildMediaEvidenceQueue(mediaCases = [], {
  confirmedSignedUrlTypes = [],
  unconfirmedSignedUrlTypes = [],
  renderLiveLinks = false
} = {}) {
  return mediaCases
    .map((item) => {
      const evidence = item.media_evidence || {};
      const evidenceItems = Array.isArray(evidence.evidence_items) ? evidence.evidence_items : [];
      const vmStreams = Array.isArray(evidence.vm_streams) ? evidence.vm_streams : [];
      const mediaTypes = sortMediaChannels([
        evidence.primary_media_type,
        ...(Array.isArray(evidence.media_types) ? evidence.media_types : []),
        ...evidenceItems.map((entry) => entry.type),
        ...vmStreams.map((entry) => entry.type || "vm_stream")
      ].map(canonicalMediaChannel).filter(Boolean));
      const primaryMediaType = canonicalMediaChannel(evidence.primary_media_type)
        || mediaTypes[0]
        || (vmStreams.length ? "vm_stream" : "files");
      const hasConfirmedSignedUrl = mediaTypes.some((type) => confirmedSignedUrlTypes.includes(type));
      const hasUnconfirmedSignedUrl = mediaTypes.some((type) => unconfirmedSignedUrlTypes.includes(type));
      const safeToRender = renderLiveLinks && hasConfirmedSignedUrl && !hasUnconfirmedSignedUrl;
      const signedUrlStatus = hasConfirmedSignedUrl
        ? "confirmed_redacted_metadata"
        : hasUnconfirmedSignedUrl
          ? "unconfirmed"
          : "not_observed";
      const previewPolicy = safeToRender
        ? "live_preview_allowed"
        : hasConfirmedSignedUrl
          ? "redacted_signed_url_metadata_only"
          : primaryMediaType === "vm_stream"
            ? "vm_stream_summary_only"
            : "metadata_only";
      const knownGaps = uniqueSorted([
        ...(Array.isArray(evidence.known_gaps) ? evidence.known_gaps : []),
        hasUnconfirmedSignedUrl ? `${primaryMediaType} signed URL behavior is unconfirmed.` : "",
        safeToRender ? "" : "Live preview is disabled until signed URL safety is confirmed."
      ]);

      return {
        case_id: item.case_id || "unknown_case",
        scenario_id: item.scenario_id || "unknown_scenario",
        title: item.title || "Untitled media case",
        status: item.passed ? "passed" : "failed",
        score: normalizeScore(item.score),
        severity: item.severity || "none",
        primary_failure_class: item.primary_failure_class || "none",
        primary_media_type: primaryMediaType,
        media_types: mediaTypes,
        evidence_count: evidenceItems.length,
        vm_stream_count: vmStreams.length,
        signed_url_status: signedUrlStatus,
        preview_policy: previewPolicy,
        safe_to_render: safeToRender,
        next_action: safeToRender
          ? "Render live preview only from fresh runtime URLs."
          : hasUnconfirmedSignedUrl
            ? "Collect a redacted signed URL shape for this channel before live rendering."
            : "Review metadata, output paths, VM stream summaries, and expected vs actual evidence.",
        known_gaps: knownGaps
      };
    })
    .sort((left, right) => (
      Number(left.status === "passed") - Number(right.status === "passed")
      || right.evidence_count - left.evidence_count
      || right.vm_stream_count - left.vm_stream_count
      || left.case_id.localeCompare(right.case_id)
    ))
    .slice(0, 8);
}

function parityAction(area, action, confirmed, note) {
  return {
    area,
    action,
    confirmed: Boolean(confirmed),
    note
  };
}

function caseHasMediaChannel(item = {}, channel = "") {
  const evidence = item.media_evidence || {};
  if (channel === "vm_stream") {
    return (evidence.vm_streams || []).length > 0
      || (evidence.evidence_items || []).some((entry) => canonicalMediaChannel(entry.type) === "vm_stream");
  }
  const evidenceChannels = [
    evidence.primary_media_type,
    ...(evidence.media_types || []),
    ...(evidence.evidence_items || []).map((entry) => entry.type)
  ].map(canonicalMediaChannel);
  return evidenceChannels.includes(channel);
}

function mediaChannelDecision(channel, signals = {}) {
  if (signals.livePreviewAllowed) {
    return "Safe to render live preview from current evidence.";
  }
  if (signals.signedUrlConfirmed) {
    return "Signed URL shape is confirmed, but A3 keeps values redacted and does not render live links.";
  }
  if (signals.signedUrlUnconfirmed) {
    return "Observed as a product channel, but signed URL behavior is still unconfirmed.";
  }
  if (channel === "vm_stream" && signals.caseEvidenceCount > 0) {
    return "Show VM stream summary only.";
  }
  if (signals.outputPathConfirmed || signals.caseEvidenceCount > 0) {
    return "Show output path and evidence metadata only.";
  }
  return "Keep as observed product capability until concrete case evidence exists.";
}

function buildCloudActionGuardrails({
  authOk = false,
  frontendSessionValid = false,
  requestProvenance = {},
  usageQuota = {},
  observedPageCount = 0
} = {}) {
  return [
    cloudAction("Switch local fixture", "Local dashboard", true, "Safe local UI action; no external request is made."),
    cloudAction("Export JSON / CSV / Markdown", "Local report", true, "Safe local export from redacted fixtures."),
    cloudAction("Print / PDF report", "Local report", true, "Safe browser print flow; no upload or public publishing."),
    cloudAction("Observe auth status", "Auth session", authOk || frontendSessionValid, "Read-only status from redacted auth/frontend evidence."),
    cloudAction("View workspace shell", "Workspace / tenant", authOk, "Only redacted workspace existence is shown; account values stay hidden."),
    cloudAction("View request provenance", "Datasets / runs", requestProvenance.available === true, "Read-only request/dataset/run provenance from redacted samples."),
    cloudAction("View usage quota", "Usage / billing", usageQuota.available === true, usageQuota.guidance || "Read-only usage shell."),
    cloudAction("Sign in with OAuth", "Auth session", false, "Do not implement real OAuth/login in A3; manual browser login remains external."),
    cloudAction("Create hosted dataset", "Datasets", false, "Would create or mutate real Ashr cloud data; disabled for MVP."),
    cloudAction("Generate / revoke API key", "API keys", false, "Would expose or mutate secrets; disabled."),
    cloudAction("Invite teammate", "Team", false, "Would change account access; disabled."),
    cloudAction("Upgrade billing plan", "Usage / billing", false, "Would affect payment/plan state; disabled."),
    cloudAction("Publish Trust certificate", "Trust", false, "Would create public-facing hosted output; replaced by local report export."),
    cloudAction("Delete cloud object", "Cloud mutations", false, "Destructive hosted operation; disabled."),
    cloudAction("Deep-link official run detail", "Official frontend", false, "Requires one UI-visible populated hosted run before A3 should copy the detail workflow.")
  ];
}

function cloudAction(action, surface, enabled, reason) {
  return {
    action,
    surface,
    enabled: Boolean(enabled),
    mode: enabled ? "local/read-only" : "disabled",
    reason
  };
}

function canonicalMediaChannel(value = "") {
  const text = String(value).toLowerCase();
  if (text.includes("audio")) {
    return "audio";
  }
  if (text.includes("image")) {
    return "images";
  }
  if (text.includes("video")) {
    return "video";
  }
  if (text.includes("file")) {
    return "files";
  }
  if (text.includes("vm")) {
    return "vm_stream";
  }
  return "";
}

function sortMediaChannels(values = []) {
  const unique = [...new Set(values.filter(Boolean))];
  return unique.sort((left, right) => {
    const leftIndex = MEDIA_CHANNEL_ORDER.indexOf(left);
    const rightIndex = MEDIA_CHANNEL_ORDER.indexOf(right);
    if (leftIndex === -1 && rightIndex === -1) {
      return left.localeCompare(right);
    }
    if (leftIndex === -1) {
      return 1;
    }
    if (rightIndex === -1) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

function countObjectValues(value = {}) {
  return Object.values(objectOr(value)).reduce((sum, item) => sum + (Number(item) || 0), 0);
}

function uniqueSorted(values = []) {
  return [...new Set(values.filter(Boolean))].sort();
}

function buildBillingEvidenceCounts(summary = {}, cases = []) {
  const traceEventCount = cases.reduce((sum, item) => sum + (Array.isArray(item.trace_events) ? item.trace_events.length : 0), 0);
  const observationCount = cases.reduce((sum, item) => sum + (Array.isArray(item.observations) ? item.observations.length : 0), 0);
  const judgeResultCount = cases.reduce((sum, item) => sum + countCaseJudgeResults(item), 0);
  const failureClasses = uniqueSorted(cases
    .map((item) => item.primary_failure_class)
    .filter((item) => item && item !== "none"));
  const scoreBandCounts = cases.reduce((counts, item) => ({
    ...counts,
    [item.score_band]: (counts[item.score_band] || 0) + 1
  }), {});

  return {
    a1: {
      runs: summary.totalRuns || 0,
      cases: summary.totalCases || 0,
      trace_events: traceEventCount,
      observations: observationCount,
      trace_ready_cases: cases.filter((item) => item.trace_ready).length,
      tool_call_cases: cases.filter(hasCaseToolCalls).length,
      media_evidence_cases: summary.mediaEvidenceCases || 0
    },
    a2: {
      graded_cases: cases.filter((item) => isObject(item.grade) && Object.keys(item.grade).length > 0).length,
      judge_results: judgeResultCount,
      failed_cases: summary.failed || 0,
      failure_class_count: failureClasses.length,
      failure_classes: failureClasses,
      score_band_counts: scoreBandCounts
    }
  };
}

function buildBillingUsageMeters(summary = {}, cases = []) {
  const evidenceCounts = buildBillingEvidenceCounts(summary, cases);
  return [
    billingMeter("runs", summary.totalRuns, "run", "A1 submitted run batches", { billable: true }),
    billingMeter("cases", summary.totalCases, "case", "Normalized A3 evaluation cases", { billable: true }),
    billingMeter("failed_cases", summary.failed, "case", "Failed cases requiring reviewer triage", { billable: false }),
    billingMeter("trace_events", evidenceCounts.a1.trace_events + evidenceCounts.a1.observations, "event", "A1 trace and observation evidence events", { billable: false }),
    billingMeter("tool_call_cases", evidenceCounts.a1.tool_call_cases, "case", "Cases containing expected or actual tool calls", { billable: false }),
    billingMeter("judge_results", evidenceCounts.a2.judge_results, "judge_result", "A2 judge result entries", { billable: true }),
    billingMeter("media_evidence_cases", evidenceCounts.a1.media_evidence_cases, "case", "Cases with media evidence metadata", { billable: true })
  ];
}

function billingMeter(name, quantity, unit, description, options = {}) {
  const normalizedQuantity = Number(quantity || 0);
  const weight = typeof options.weight === "number" && !Number.isNaN(options.weight) ? options.weight : 1;
  const billable = options.billable !== false;
  return {
    meter: name,
    quantity: normalizedQuantity,
    unit,
    description,
    billable,
    billable_units: billable ? Math.round(normalizedQuantity * weight * 1000) / 1000 : 0,
    billable_weight: weight
  };
}

function mergeBillingMeters(defaultMeters = [], optionMeters = []) {
  const byName = new Map(defaultMeters.map((item) => [item.meter, item]));
  for (const meter of optionMeters) {
    if (!meter || !meter.meter) {
      continue;
    }
    const previous = byName.get(meter.meter) || {};
    byName.set(meter.meter, normalizeBillingMeter({
      ...previous,
      ...meter,
      description: meter.description || previous.description
    }));
  }
  return [...byName.values()].map(normalizeBillingMeter);
}

function normalizeBillingMeter(meter = {}) {
  const quantity = Number(meter.quantity || 0);
  const weight = typeof meter.billable_weight === "number" && !Number.isNaN(meter.billable_weight)
    ? meter.billable_weight
    : typeof meter.weight === "number" && !Number.isNaN(meter.weight)
      ? meter.weight
      : 1;
  const billable = meter.billable !== false;
  return {
    meter: meter.meter || "unknown_meter",
    quantity,
    unit: meter.unit || "unit",
    description: meter.description || "Usage meter",
    billable,
    billable_units: billable ? Math.round(quantity * weight * 1000) / 1000 : 0,
    billable_weight: weight
  };
}

function resolveBillingPlan(usageFixture = {}, usageQuota = {}, options = {}) {
  const optionPlan = options.plan || options.billingPlan || {};
  const planFixture = usageFixture.billing_plan || usageFixture.current_plan || usageFixture.plan || {};
  const hasOptionPlan = isObject(optionPlan) && Object.keys(optionPlan).length > 0;
  const planObject = typeof optionPlan === "string"
    ? { plan_name: optionPlan }
    : hasOptionPlan
      ? optionPlan
      : typeof planFixture === "string"
        ? { plan_name: planFixture }
        : objectOr(planFixture);
  const apiPaths = objectOr(usageFixture.api_paths);
  const observedPlanPath = Boolean(apiPaths["init.tenant.plan"]);
  const planName = firstText(
    planObject.plan_name,
    planObject.name,
    planObject.plan,
    planObject.id,
    observedPlanPath ? "frontend-observed-plan" : "local-readonly"
  );
  const includedUnits = firstNumber(
    planObject.included_unit_count,
    planObject.included_units,
    planObject.quota_units,
    planObject.quota?.included_units,
    options.quota?.included_units,
    options.quota?.included_unit_count
  );

  return {
    plan_id: firstText(planObject.plan_id, planObject.id, planName.toLowerCase().replaceAll(" ", "-")),
    plan_name: planName,
    source: planObject.source || (observedPlanPath || usageQuota.available ? "usage_quota_observation" : "a3_local_default"),
    billing_period: firstText(planObject.billing_period, options.billingPeriod, "monthly"),
    currency: firstText(planObject.currency, options.currency, "USD"),
    included_unit_count: includedUnits,
    overage_enabled: planObject.overage_enabled === true || options.overageEnabled === true,
    mutation_allowed: false
  };
}

function resolveBillingQuota(usageFixture = {}, options = {}, billableUnitCount = 0, plan = {}) {
  const optionQuota = options.quota || {};
  const fixtureQuota = usageFixture.quota || usageFixture.usage_quota || {};
  const quotaObject = isObject(optionQuota) && Object.keys(optionQuota).length > 0
    ? optionQuota
    : isObject(fixtureQuota)
      ? fixtureQuota
      : {};
  const includedUnits = firstNumber(
    quotaObject.included_units,
    quotaObject.included_unit_count,
    quotaObject.limit,
    quotaObject.monthly_limit,
    plan.included_unit_count
  );
  const usedUnits = firstNumber(
    quotaObject.used_units,
    quotaObject.used,
    quotaObject.quantity,
    billableUnitCount
  );
  const remainingUnits = typeof includedUnits === "number"
    ? Math.max(0, includedUnits - usedUnits)
    : null;

  return {
    unit: firstText(quotaObject.unit, quotaObject.meter_unit, "billable_unit"),
    included_units: includedUnits,
    used_units: usedUnits,
    remaining_units: remainingUnits,
    overage_units: typeof includedUnits === "number" ? Math.max(0, usedUnits - includedUnits) : 0,
    enforcement: "read_only",
    source: quotaObject.source || (typeof includedUnits === "number" ? "plan_quota" : "a3_metered_without_limit")
  };
}

function classifyOverageRisk(quota = {}, plan = {}) {
  if (typeof quota.included_units !== "number" || quota.included_units <= 0) {
    return {
      status: "unknown_limit",
      risk_level: "unknown",
      usage_ratio: null,
      remaining_units: quota.remaining_units,
      overage_units: quota.overage_units || 0,
      reason: "No included quota limit was available in the read-only inputs."
    };
  }

  const ratio = quota.used_units / quota.included_units;
  const usageRatio = Math.round(ratio * 1000) / 1000;
  if (quota.used_units > quota.included_units) {
    return {
      status: "over_quota",
      risk_level: plan.overage_enabled ? "high" : "blocked",
      usage_ratio: usageRatio,
      remaining_units: 0,
      overage_units: quota.used_units - quota.included_units,
      reason: plan.overage_enabled
        ? "Usage exceeds included quota and would enter overage billing on a live plan."
        : "Usage exceeds included quota and should block plan-limited actions until upgraded."
    };
  }
  if (ratio >= 0.9) {
    return {
      status: "near_quota",
      risk_level: "high",
      usage_ratio: usageRatio,
      remaining_units: quota.remaining_units,
      overage_units: 0,
      reason: "Usage is at least 90% of included quota."
    };
  }
  if (ratio >= 0.75) {
    return {
      status: "watch",
      risk_level: "medium",
      usage_ratio: usageRatio,
      remaining_units: quota.remaining_units,
      overage_units: 0,
      reason: "Usage is at least 75% of included quota."
    };
  }
  return {
    status: "within_quota",
    risk_level: "low",
    usage_ratio: usageRatio,
    remaining_units: quota.remaining_units,
    overage_units: 0,
    reason: "Usage is below the configured quota watch threshold."
  };
}

function firstNumber(...values) {
  for (const value of values) {
    if (typeof value === "number" && !Number.isNaN(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

function countCaseJudgeResults(item = {}) {
  if (Array.isArray(item.judge_results) && item.judge_results.length) {
    return item.judge_results.length;
  }
  return item.grade && Object.keys(objectOr(item.grade)).length > 0 ? 1 : 0;
}

function hasCaseToolCalls(item = {}) {
  return (item.expected?.tool_calls || []).length > 0
    || (item.actual?.tool_calls || []).length > 0;
}

function extractRequestObjects(input = {}) {
  if (Array.isArray(input)) {
    return input.filter(isObject);
  }
  if (input.response && input.response !== input) {
    const responseRequests = extractRequestObjects(input.response);
    if (responseRequests.length) {
      return responseRequests;
    }
  }
  if (Array.isArray(input.requests)) {
    return input.requests.filter(isObject);
  }
  if (Array.isArray(input.list_requests?.requests)) {
    return input.list_requests.requests.filter(isObject);
  }
  if (Array.isArray(input.calls?.list_requests?.sample?.requests)) {
    return input.calls.list_requests.sample.requests.filter(isObject);
  }
  if (isObject(input.sample) && looksLikeRequest(input.sample)) {
    return [input.sample];
  }
  if (isObject(input.calls?.get_request?.sample)) {
    return [input.calls.get_request.sample];
  }
  if (isObject(input.get_request?.sample)) {
    return [input.get_request.sample];
  }
  const generatedDatasetSummary = generatedDatasetSummaryAsRequest(input);
  if (generatedDatasetSummary) {
    return [generatedDatasetSummary];
  }
  return looksLikeRequest(input) ? [input] : [];
}

function generatedDatasetSummaryAsRequest(input = {}) {
  const frontend = objectOr(input.frontend_result);
  if (!frontend.dataset_id_decimal && !frontend.dataset_name) {
    return null;
  }

  const generatedCases = Array.isArray(input.generated_test_cases) ? input.generated_test_cases : [];
  const acceptedInputs = uniqueSorted(generatedCases.flatMap((item) => (
    Array.isArray(item.media_or_input_types) ? item.media_or_input_types : []
  )));

  return {
    id: `dataset-${firstText(frontend.dataset_id_decimal, "unknown")}-generate-test-suite`,
    request_name: firstText(frontend.dataset_name, "Generated dataset"),
    request_status: frontend.dataset_visible ? "dataset_generated" : "unknown",
    created_at: firstText(input.captured_at, frontend.created_date_visible, ""),
    completed_at: firstText(input.captured_at, ""),
    actual_duration_s: null,
    estimated_duration_s: null,
    request: {
      metadata: {
        dataset_name: firstText(frontend.dataset_name, "Generated dataset"),
        source: "frontend_generate_test_suite_summary"
      },
      agent: {
        accepted_inputs: Object.fromEntries(acceptedInputs.map((inputType) => [inputType, true])),
        tools: []
      },
      generation_options: {
        generated_dataset: frontend.dataset_visible === true
      },
      test_config: {
        strategy: "official_generate_test_suite",
        num_variations: generatedCases.length || numberOrNull(frontend.total_tests_visible),
        coverage: {
          media_channels: acceptedInputs
        }
      },
      context: {
        domain: "e-commerce"
      }
    }
  };
}

function looksLikeRequest(value = {}) {
  return isObject(value) && (
    "request_status" in value
    || "request_name" in value
    || "estimated_duration_s" in value
    || "actual_duration_s" in value
    || isObject(value.request)
  );
}

function objectOr(value) {
  return isObject(value) ? value : {};
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function truthyKeys(value = {}) {
  return Object.entries(objectOr(value))
    .filter(([, flag]) => flag === true || isRedactedPlaceholder(flag))
    .map(([key]) => key)
    .sort();
}

function numberOrNull(value) {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function isRedactedPlaceholder(value) {
  return typeof value === "string" && value.startsWith("[REDACTED");
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

function coverageExemplarLines(exemplars = {}) {
  return Object.entries(exemplars)
    .sort(([left], [right]) => left.localeCompare(right))
    .flatMap(([axis, items]) => (
      Array.isArray(items) ? items : []
    ).map((item) => (
      `- ${axis}: ${item.scenario_id || "unknown"} (${item.title || "untitled"}) - ${item.why_it_matters || "No reviewer note."}`
    )));
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
  const pairs = pairToolCalls(expected, actual);

  return pairs.map((pair, index) => {
    const { expectedCall, actualCall, expectedIndex, actualIndex, matchStrategy } = pair;
    const status = toolDiffStatus(expectedCall, actualCall, pair);
    const traceEventLinks = buildTraceEventLinks(caseResult, {
      index,
      expectedIndex,
      actualIndex,
      expectedCall,
      actualCall
    });
    return {
      index,
      expected_index: expectedIndex,
      actual_index: actualIndex,
      match_strategy: matchStrategy,
      order_changed: Number.isInteger(expectedIndex)
        && Number.isInteger(actualIndex)
        && expectedIndex !== actualIndex,
      status,
      expected: expectedCall,
      actual: actualCall,
      summary: toolDiffSummary(status, expectedCall, actualCall),
      argument_diffs: expectedCall && actualCall
        ? buildArgumentDiffs(expectedCall.arguments, actualCall.arguments)
        : [],
      trace_event_links: traceEventLinks,
      judge_evidence: buildToolDiffJudgeEvidence(caseResult, {
        index,
        expectedIndex,
        actualIndex,
        status,
        expectedCall,
        actualCall,
        traceEventLinks
      })
    };
  });
}

function buildTraceEventLinks(caseResult = {}, diff = {}) {
  const events = Array.isArray(caseResult.trace_events) ? caseResult.trace_events : [];
  const toolNames = new Set([diff.expectedCall?.name, diff.actualCall?.name].filter(Boolean));
  const toolIds = new Set([diff.expectedCall?.id, diff.actualCall?.id].filter(Boolean));
  const seen = new Set();

  return events.flatMap((event, eventIndex) => {
    if (!isToolTraceEvent(event)) {
      return [];
    }
    const data = event.observation?.data || event.data || {};
    const names = traceToolNames(event);
    const ids = traceToolIds(event);
    const nameMatches = names.some((name) => toolNames.has(name));
    const idMatches = ids.some((id) => toolIds.has(id));
    if (!nameMatches && !idMatches) {
      return [];
    }

    const eventId = firstText(event.event_id, event.id, `${caseResult.case_id || "case"}:trace:${event.seq ?? eventIndex}`);
    if (seen.has(eventId)) {
      return [];
    }
    seen.add(eventId);
    return [{
      event_id: eventId,
      seq: event.seq ?? eventIndex,
      event_type: event.event_type || event.type || "tool.tool_call",
      phase: event.phase || "tool",
      tool_name: names[0] || data.name || "tool"
    }];
  });
}

function isToolTraceEvent(event = {}) {
  const eventType = String(event.event_type || event.type || "");
  const phase = String(event.phase || "");
  const kind = String(event.observation?.kind || "");
  return eventType.includes("tool")
    || phase === "tool"
    || kind.includes("tool");
}

function traceToolNames(event = {}) {
  const data = event.observation?.data || event.data || {};
  return uniqueValues([
    data.name,
    data.tool_name,
    data.tool,
    data.actual?.tool_name,
    data.actual?.name,
    data.actual?.tool,
    data.expected?.tool_name,
    data.expected?.name,
    data.expected?.tool
  ].filter(Boolean).map(String));
}

function traceToolIds(event = {}) {
  const data = event.observation?.data || event.data || {};
  return uniqueValues([
    data.id,
    data.tool_call_id,
    data.actual?.id,
    data.actual?.tool_call_id,
    data.expected?.id,
    data.expected?.tool_call_id
  ].filter(Boolean).map(String));
}

function uniqueValues(values) {
  return [...new Set(values)];
}

function firstText(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return String(value);
    }
  }
  return "";
}

function buildToolDiffJudgeEvidence(caseResult = {}, diff = {}) {
  const judgeResults = Array.isArray(caseResult.judge_results) ? caseResult.judge_results : [];
  const toolNames = new Set([diff.expectedCall?.name, diff.actualCall?.name].filter(Boolean));
  const toolIds = new Set([diff.expectedCall?.id, diff.actualCall?.id].filter(Boolean));
  const positions = [diff.index, diff.expectedIndex, diff.actualIndex]
    .filter((position) => Number.isInteger(position))
    .map((position) => `#${position + 1}`);

  return judgeResults.flatMap((judge) => {
    const analysis = judge.failure_analysis || {};
    const evidence = judge.evidence || {};
    const failureClasses = Array.isArray(analysis.failure_classes) ? analysis.failure_classes : [];
    const toolCallIds = Array.isArray(evidence.tool_call_ids) ? evidence.tool_call_ids : [];
    const relevantFailure = judge.passed === false && (
      failureMatchesDiff(analysis.primary_failure_class, diff.status)
      || failureClasses.some((failureClass) => failureMatchesDiff(failureClass, diff.status))
      || failureMatchesDiff(analysis.primary_failure_class, caseResult.primary_failure_class)
    );
    const relevantTool = toolCallIds.some((toolCallId) => (
      positions.some((position) => toolCallId === position || toolCallId.endsWith(position))
      || [...toolIds].some((toolId) => toolCallId === toolId)
      || [...toolNames].some((toolName) => toolCallId.includes(toolName))
    ));

    if (!relevantFailure && !relevantTool) {
      return [];
    }

    return [{
      judge_mode: judge.judge_mode || "judge",
      score: judge.score ?? null,
      primary_failure_class: analysis.primary_failure_class || "none",
      severity: analysis.severity || "none",
      summary: analysis.summary || "No judge summary.",
      details: Array.isArray(analysis.details) ? analysis.details : [],
      remediation: Array.isArray(analysis.remediation) ? analysis.remediation : [],
      evidence: {
        tool_call_ids: toolCallIds,
        trace_event_ids: (diff.traceEventLinks || []).map((event) => event.event_id),
        final_response_excerpt: evidence.final_response_excerpt || null
      }
    }];
  });
}

function failureMatchesDiff(failureClass, status) {
  if (!failureClass || !status) {
    return false;
  }
  if (failureClass === status) {
    return true;
  }
  return canonicalPrimaryFailureClass(failureClass, false) === canonicalPrimaryFailureClass(status, false);
}

export function buildArgumentDiffs(expectedArgs = {}, actualArgs = {}) {
  const expectedLeaves = flattenArgumentLeaves(expectedArgs);
  const actualLeaves = flattenArgumentLeaves(actualArgs);
  const paths = [...new Set([...expectedLeaves.keys(), ...actualLeaves.keys()])].sort();

  return paths.flatMap((path) => {
    const hasExpected = expectedLeaves.has(path);
    const hasActual = actualLeaves.has(path);
    const expected = hasExpected ? expectedLeaves.get(path) : null;
    const actual = hasActual ? actualLeaves.get(path) : null;

    if (!hasExpected && hasActual) {
      return [{ path, status: "unexpected_argument", expected, actual }];
    }
    if (hasExpected && !hasActual) {
      return [{ path, status: "missing_argument", expected, actual }];
    }
    if (stableJson(expected) !== stableJson(actual)) {
      return [{ path, status: "changed_argument", expected, actual }];
    }
    return [];
  });
}

export function summarizeProductConsoleExport(productConsoleFixture = {}) {
  const available = productConsoleFixture?.schema_version === "a3.product_console.v1"
    || Boolean(productConsoleFixture?.onboarding || productConsoleFixture?.project_console || productConsoleFixture?.audit_log);
  if (!available) {
    return {
      schema_version: "a3.product_console_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach Product Console workflow state before claiming onboarding, project, or audit readiness."
    };
  }

  const onboarding = productConsoleFixture.onboarding || {};
  const project = productConsoleFixture.project_console || {};
  const audit = productConsoleFixture.audit_log || {};
  const readiness = productConsoleFixture.commercial_readiness || {};
  return {
    schema_version: "a3.product_console_export.v1",
    available: true,
    source: productConsoleFixture.source || "unknown",
    tenant_scope: productConsoleFixture.tenant_scope || {},
    onboarding: {
      status: onboarding.status || "unknown",
      completed_steps: onboarding.completed_steps || 0,
      total_steps: onboarding.total_steps || 0,
      completion_rate: onboarding.completion_rate || 0,
      next_actions: (onboarding.next_actions || []).slice(0, 6)
    },
    project_console: {
      project_id: project.project_id || "project-local",
      status: project.status || "unknown",
      run_count: project.summary?.run_count || 0,
      case_count: project.summary?.case_count || 0,
      failed_case_count: project.summary?.failed_case_count || 0,
      report_count: project.report_snapshot?.report_count || 0,
      primary_actions: (project.primary_actions || []).map((item) => ({
        action: item.action,
        enabled: item.enabled === true,
        mode: item.mode || "unknown"
      }))
    },
    audit_log: {
      status: audit.status || "empty",
      event_count: audit.event_count || 0,
      redacted_payload_only: audit.redacted_payload_only === true,
      missing_required_events: audit.missing_required_events || []
    },
    commercial_readiness: {
      status: readiness.status || "unknown",
      readiness_score: readiness.readiness_score || 0,
      strongest_money_path: readiness.strongest_money_path || "unknown",
      checks: (readiness.checks || []).map((item) => ({
        id: item.id,
        status: item.status,
        passed: item.passed === true
      })),
      next_commercial_moves: readiness.next_commercial_moves || []
    },
    recommendation: "Use Product Console export as the onboarding/project/audit section of customer-facing release evidence."
  };
}

export function summarizeSaasAdminExport(saasAdminFixture = {}) {
  const available = saasAdminFixture?.schema_version === "a3.saas_admin_console.v1"
    || Boolean(saasAdminFixture?.login || saasAdminFixture?.team || saasAdminFixture?.api_keys || saasAdminFixture?.trust || saasAdminFixture?.cloud_management);
  if (!available) {
    return {
      schema_version: "a3.saas_admin_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach SaaS Admin Console state before claiming login, team, API-key, usage, trust, or cloud-management readiness."
    };
  }

  const login = saasAdminFixture.login || {};
  const team = saasAdminFixture.team || {};
  const apiKeys = saasAdminFixture.api_keys || {};
  const usage = saasAdminFixture.usage || {};
  const billing = saasAdminFixture.billing_account || {};
  const trust = saasAdminFixture.trust || {};
  const cloud = saasAdminFixture.cloud_management || {};
  const compatibility = saasAdminFixture.a1_a2_compatibility || {};
  const safety = saasAdminFixture.safety || {};
  const actions = Array.isArray(saasAdminFixture.actions) ? saasAdminFixture.actions : [];
  const actionRequests = Array.isArray(saasAdminFixture.action_requests) ? saasAdminFixture.action_requests : [];
  const actionRequestSummary = saasAdminFixture.action_request_summary || {};
  const authBoundary = saasAdminFixture.auth_boundary || {};

  return {
    schema_version: "a3.saas_admin_export.v1",
    available: true,
    source: saasAdminFixture.source || "unknown",
    organization: {
      plan: saasAdminFixture.organization?.plan || "unknown",
      tenancy_mode: saasAdminFixture.organization?.tenancy_mode || "unknown",
      data_region: saasAdminFixture.organization?.data_region || "unknown",
      auth_boundary: saasAdminFixture.organization?.auth_boundary || "unknown"
    },
    login: {
      status: login.status || "unknown",
      provider: login.provider || "unknown",
      session_storage: login.session_storage || "not_persisted",
      user_identity_redacted: login.user_identity === "[REDACTED]" || login.session?.account_email === "[REDACTED]",
      rbac_enforced_now: login.rbac_boundary?.enforced_now === true
    },
    auth_boundary: {
      schema_version: authBoundary.schema_version || "unknown",
      actor_identity_redacted: authBoundary.auth_context?.safety?.raw_actor_identity_exposed === false,
      role: authBoundary.auth_context?.role || "unknown",
      auth_state: authBoundary.auth_context?.auth_state || "unknown",
      enforcement_state: authBoundary.enforcement_state || "unknown",
      operation_count: authBoundary.operation_count || 0,
      denied_state_count: (authBoundary.sample_decisions || []).filter((item) => item.allowed !== true).length,
      real_cloud_mutations_performed: (authBoundary.sample_decisions || []).some((item) => item.safety?.real_cloud_mutation_performed === true)
    },
    team: {
      status: team.status || "unknown",
      invite_mode: team.invite_mode || "unknown",
      member_count: Array.isArray(team.members) ? team.members.length : 0,
      roles: Array.isArray(team.roles) ? team.roles : [],
      self_approval_allowed: team.approval_policy?.self_approval_allowed === true,
      approval_escalation_summary: team.approval_policy?.escalation_summary || "unknown",
      seat_management: {
        purchased_seats: team.seat_management?.purchased_seats || 0,
        assigned_billable_seats: team.seat_management?.assigned_billable_seats || 0,
        free_audit_seats: team.seat_management?.free_audit_seats || 0,
        pending_invites: team.seat_management?.pending_invites || 0,
        overage_risk: team.seat_management?.overage_risk || "unknown"
      },
      procurement_posture: team.procurement_posture || {}
    },
    api_keys: {
      status: apiKeys.status || "unknown",
      create_mode: apiKeys.create_mode || "unknown",
      reveal_policy: apiKeys.reveal_policy || "unknown",
      hygiene_status: apiKeys.hygiene_status || "unknown",
      rotation_slo_days: apiKeys.rotation_slo_days || 0,
      leaked_key_detection: apiKeys.leaked_key_detection || "unknown",
      key_count: Array.isArray(apiKeys.keys) ? apiKeys.keys.length : 0,
      audit_requirements: Array.isArray(apiKeys.audit_requirements) ? apiKeys.audit_requirements : [],
      lifecycle_steps: (apiKeys.lifecycle || []).map((item) => ({
        step: item.step,
        status: item.status
      }))
    },
    usage: {
      status: usage.status || "unknown",
      plan_name: usage.plan_snapshot?.plan_name || "unknown",
      quota_mutations_enabled: usage.plan_snapshot?.quota_mutations_enabled === true,
      overage_posture: usage.plan_snapshot?.overage_posture || "unknown",
      channels: Array.isArray(usage.channels) ? usage.channels : [],
      oauth_only_functions: Array.isArray(usage.oauth_only_functions) ? usage.oauth_only_functions : [],
      escalation_posture: usage.escalation_posture || {}
    },
    billing_account: {
      schema_version: billing.schema_version || "unknown",
      status: billing.status || "unknown",
      plan_name: billing.plan_name || "unknown",
      quota_window: billing.quota_window || "unknown",
      invoice_preview_state: billing.invoice_preview_state || "unknown",
      overage_risk: billing.overage_risk || "unknown",
      collections_posture: billing.collections_posture || {},
      provider_priority: (billing.provider_priority || []).slice(0, 4).map((item) => ({
        provider: item.provider,
        priority: item.priority,
        market: item.market,
        readiness: item.readiness
      }))
    },
    commercial_ops: saasAdminFixture.commercial_ops || {},
    self_host_console: saasAdminFixture.self_host_console || {},
    developer_platform: saasAdminFixture.developer_platform || {},
    trust: {
      status: trust.status || "unknown",
      public_certificate_mode: trust.public_certificate_mode || "unknown",
      publish_enabled: trust.publish_enabled === true,
      public_publish_enabled: trust.trust_center?.public_publish_enabled === true,
      release_gate_label: trust.release_gate_label || trust.release_gate_decision || "unknown",
      compliance_posture: {
        audit_export_ready: trust.compliance_posture?.audit_export_ready === true,
        customer_visible_publish_blocked: trust.compliance_posture?.customer_visible_publish_blocked === true,
        soc2_surface: trust.compliance_posture?.soc2_surface || "unknown",
        retention_policy: trust.compliance_posture?.retention_policy || "unknown"
      }
    },
    cloud_management: {
      status: cloud.status || "unknown",
      resource_count: Array.isArray(cloud.resources) ? cloud.resources.length : 0,
      real_mutations_enabled: cloud.real_mutations_enabled === true,
      supported_readonly_surfaces: Array.isArray(cloud.supported_readonly_surfaces) ? cloud.supported_readonly_surfaces : [],
      disabled_mutations: Array.isArray(cloud.disabled_mutations) ? cloud.disabled_mutations : [],
      workspace_action_readiness: cloud.workspace_action_readiness || {},
      workspace_posture: {
        schema_version: cloud.workspace_posture?.schema_version || "unknown",
        status: cloud.workspace_posture?.status || "unknown",
        tenant_scope_state: cloud.workspace_posture?.tenant_scope_state || "unknown",
        project_state: cloud.workspace_posture?.project_state || "unknown",
        environment_state: cloud.workspace_posture?.environment_state || cloud.workspace_posture?.active_environment || "unknown",
        usage_state: cloud.workspace_posture?.usage_state || "unknown",
        operator_story: Array.isArray(cloud.workspace_posture?.operator_story) ? cloud.workspace_posture.operator_story : [],
        next_capabilities: Array.isArray(cloud.workspace_posture?.next_capabilities) ? cloud.workspace_posture.next_capabilities : []
      }
    },
    a1_a2_compatibility: {
      a1_run_result_ready: compatibility.a1_run_result_ready === true,
      a2_grade_result_ready: compatibility.a2_grade_result_ready === true,
      case_count: compatibility.case_count || 0,
      trace_ready_count: compatibility.trace_ready_count || 0,
      judge_ready_count: compatibility.judge_ready_count || 0
    },
    safety: {
      real_login_enabled: safety.real_login_enabled === true,
      real_team_invites_enabled: safety.real_team_invites_enabled === true,
      real_api_key_secrets_enabled: safety.real_api_key_secrets_enabled === true,
      real_billing_mutations_enabled: safety.real_billing_mutations_enabled === true,
      real_trust_publish_enabled: safety.real_trust_publish_enabled === true,
      secret_values_allowed: safety.secret_values_allowed === true,
      mode: safety.mode || "unknown"
    },
    action_plans: actions.slice(0, 8).map((item) => ({
      action: item.action,
      area: item.area,
      mode: item.mode,
      enabled: item.enabled === true,
      writes_real_ashr_cloud: item.writes_real_ashr_cloud === true
    })),
    action_requests: {
      request_count: actionRequestSummary.request_count || actionRequests.length,
      pending_count: actionRequestSummary.pending_count || 0,
      blocked_count: actionRequestSummary.blocked_count || 0,
      real_cloud_mutations_performed: actionRequestSummary.real_cloud_mutations_performed === true,
      secret_values_included: actionRequestSummary.secret_values_included === true,
      latest: actionRequests.slice(-3).map((item) => ({
        request_id: item.request_id,
        action: item.action,
        area: item.area,
        mode: item.mode,
        status: item.status,
        real_cloud_mutation_performed: item.real_cloud_mutation_performed === true,
        secret_values_included: item.secret_values_included === true
      }))
    },
    recommendation: "Keep SaaS admin, key, team, billing, trust, and cloud workflows read-only or plan-only until hosted auth, RBAC, SQL persistence, and audit events are real."
  };
}

function isArtifactRegistryFixture(value = {}) {
  const schema = isObject(value) ? String(value.schema_version || "") : "";
  if (schema.includes("artifact_registry")) {
    return true;
  }
  return isObject(value)
    && Array.isArray(value.entries)
    && (Array.isArray(value.packet_presets) || isObject(value.summary));
}

export function summarizeArtifactRegistryExport(artifactRegistryFixture = {}) {
  const available = artifactRegistryFixture?.schema_version === "a3.artifact_registry.v1"
    || Boolean(artifactRegistryFixture?.entries || artifactRegistryFixture?.summary);
  if (!available) {
    return {
      schema_version: "a3.artifact_registry_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach Artifact Registry state before claiming managed report/export evidence."
    };
  }

  const entries = Array.isArray(artifactRegistryFixture.entries) ? artifactRegistryFixture.entries : [];
  const summary = artifactRegistryFixture.summary || {};
  const topArtifactEntries = entries.slice(0, 8);
  const billingMigrationEntry = entries.find((item) => item.artifact_type === "billing_migration_readiness");
  if (billingMigrationEntry && !topArtifactEntries.includes(billingMigrationEntry)) {
    topArtifactEntries.push(billingMigrationEntry);
  }
  return {
    schema_version: "a3.artifact_registry_export.v1",
    available: true,
    status: artifactRegistryFixture.registry_status || "unknown",
    source: artifactRegistryFixture.source || "unknown",
    artifact_count: summary.artifact_count || entries.length,
    report_artifact_count: summary.report_artifact_count || entries.filter((item) => item.report_id).length,
    control_artifact_count: summary.control_artifact_count || entries.filter((item) => !item.report_id).length,
    ready_count: summary.ready_count || 0,
    blocked_count: summary.blocked_count || 0,
    hash_ready_count: summary.hash_ready_count || 0,
    billable_meter_count: summary.billable_meter_count || 0,
    packet_presets: (artifactRegistryFixture.packet_presets || []).map((item) => ({
      preset_id: item.preset_id,
      status: item.status,
      missing_artifact_types: item.missing_artifact_types || []
    })),
    top_artifacts: topArtifactEntries.map((item) => ({
      artifact_id: item.artifact_id,
      artifact_type: item.artifact_type,
      lifecycle_state: item.lifecycle_state,
      hash_status: item.hash_status,
      redaction_status: item.redaction_status,
      billable_meter: item.billable_meter,
      customer_value: item.customer_value,
      billable_value: item.billable_value || null,
      self_host_value: item.self_host_value || null,
      audit_value: item.audit_value || null,
      missing_controls: Array.isArray(item.missing_controls) ? item.missing_controls : []
    })),
    safety: {
      raw_secret_values_allowed: artifactRegistryFixture.safety?.raw_secret_values_allowed === true,
      raw_share_tokens_stored: artifactRegistryFixture.safety?.raw_share_tokens_stored === true,
      real_cloud_mutations_enabled: artifactRegistryFixture.safety?.real_cloud_mutations_enabled === true
    },
    recommendation: "Use Artifact Registry as the enterprise evidence catalog behind report exports, PR gates, billing meters, and audit bundles."
  };
}

export function summarizeGithubPublishEvidence(githubPublishFixture = {}) {
  const checkPublish = objectOr(githubPublishFixture.check_publish);
  const prCommentPublish = objectOr(githubPublishFixture.pr_comment_publish);
  const requiredCheckPlan = objectOr(githubPublishFixture.required_check_plan);
  const records = [checkPublish, prCommentPublish, requiredCheckPlan].filter((item) => item.schema_version);
  if (!records.length) {
    return {
      schema_version: "a3.github_publish_evidence_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach GitHub check publish, PR comment publish, and required-check plan receipts before claiming PR Gate publish evidence."
    };
  }
  const postedCount = records.filter((item) => item.posted === true || item.status === "posted").length;
  const plannedCount = records.filter((item) => item.dry_run === true || item.status === "planned" || String(item.mode || "").startsWith("plan_")).length;
  const dryRunOnly = records.every((item) => item.dry_run === true || item.safety?.dry_run_only === true || String(item.mode || "").startsWith("plan_"));
  const tokenIncluded = records.some((item) => item.safety?.token_included === true);
  const secretValuesAllowed = records.some((item) => item.safety?.secret_values_allowed === true);
  const requiredTokenScopes = [...new Set(records
    .map((item) => item.requires_token_scope || item.request?.requires_token_scope || item.plan?.requires_token_scope)
    .filter(Boolean))];
  const summaryStatus = postedCount === 2 && requiredCheckPlan.schema_version
    ? "posted_with_required_check_plan"
    : postedCount > 0
      ? "partial"
      : plannedCount > 0
        ? "planned"
        : "missing";
  return {
    schema_version: "a3.github_publish_evidence_export.v1",
    available: true,
    status: summaryStatus,
    dry_run_only: dryRunOnly,
    posted_count: postedCount,
    planned_count: plannedCount,
    mutation_count: postedCount,
    check_publish: summarizeGithubPublishRecord(checkPublish, "github_check"),
    pr_comment_publish: summarizeGithubPublishRecord(prCommentPublish, "pr_comment"),
    required_check_plan: summarizeGithubPublishRecord(requiredCheckPlan, "required_check_plan"),
    required_check_planned: requiredCheckPlan.schema_version === "a3.github_required_check_plan.v1",
    repo: checkPublish.request?.repo || prCommentPublish.plan?.repo || requiredCheckPlan.repo || {},
    branch: requiredCheckPlan.branch || null,
    pull_number: prCommentPublish.plan?.pull_number || null,
    check_name: requiredCheckPlan.check_name || checkPublish.request?.body?.name || "Ashr++ Release Gate",
    required_token_scopes: requiredTokenScopes,
    maintainer_approval_required: requiredCheckPlan.safety?.maintainer_approval_required === true,
    safety: {
      token_included: tokenIncluded,
      secret_values_allowed: secretValuesAllowed,
      response_body_sanitized: records.every((item) => item.safety?.response_body_sanitized !== false),
      raw_secret_values_allowed: false
    },
    recommendation: "Use GitHub publish evidence as the PR Gate delivery receipt, then bind it into Artifact Registry, audit bundle, and branch-protection verification."
  };
}


export function summarizeLiveOpsControlPlaneExport(controlPlaneFixture = {}) {
  const available = controlPlaneFixture?.schema_version === "a3.live_ops_control_plane.v1"
    || Boolean(controlPlaneFixture?.lanes || controlPlaneFixture?.human_operation_summary || controlPlaneFixture?.report_link_summary);
  if (!available) {
    return {
      schema_version: "a3.live_ops_control_plane_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach live ops control-plane evidence before claiming publish, reviewer, billing, and report-governance readiness."
    };
  }

  return {
    schema_version: "a3.live_ops_control_plane_export.v1",
    available: true,
    source: controlPlaneFixture.source || "unknown",
    status: controlPlaneFixture.status || "unknown",
    lane_count: controlPlaneFixture.counts?.lane_count || 0,
    api_backed_count: controlPlaneFixture.counts?.api_backed_count || 0,
    audit_backed_count: controlPlaneFixture.counts?.audit_backed_count || 0,
    local_external_mutation_count: controlPlaneFixture.counts?.local_external_mutation_count || 0,
    human_operation_summary: controlPlaneFixture.human_operation_summary || {},
    billing_state_summary: controlPlaneFixture.billing_state_summary || {},
    report_link_summary: controlPlaneFixture.report_link_summary || {},
    release_publish_chain: controlPlaneFixture.release_publish_chain || {},
    commercial_signoff_summary: controlPlaneFixture.commercial_signoff_summary || {},
    reviewer_timeline: Array.isArray(controlPlaneFixture.reviewer_timeline) ? controlPlaneFixture.reviewer_timeline : [],
    github_publish_timeline: Array.isArray(controlPlaneFixture.github_publish_timeline) ? controlPlaneFixture.github_publish_timeline : [],
    share_link_timeline: Array.isArray(controlPlaneFixture.share_link_timeline) ? controlPlaneFixture.share_link_timeline : [],
    audit_history: Array.isArray(controlPlaneFixture.audit_history) ? controlPlaneFixture.audit_history : [],
    lanes: Array.isArray(controlPlaneFixture.lanes) ? controlPlaneFixture.lanes.map((item) => ({
      id: item.id,
      status: item.status,
      current_mode: item.current_mode,
      product_surface: item.product_surface,
      next_action: item.next_action
    })) : [],
    safety: controlPlaneFixture.safety || {},
    recommendation: "Keep live ops export aligned with A1 hosted workers and A2 release semantics while exposing operator-facing governance evidence."
  };
}
export function summarizeNotificationControlPlane(notificationFixture = {}) {
  const available = notificationFixture?.schema_version === "a3.notification_control_plane.v1";
  if (!available) {
    return {
      schema_version: "a3.notification_control_plane_export.v1",
      available: false,
      status: "missing",
      recommendation: "Attach Notification Control Plane evidence before claiming Slack, Teams, email, or webhook release notifications."
    };
  }
  const summary = notificationFixture.summary || {};
  const channels = Array.isArray(notificationFixture.channels)
    ? notificationFixture.channels
    : Array.isArray(notificationFixture.lanes)
      ? notificationFixture.lanes
      : [];
  const growthPoints = Array.isArray(notificationFixture.growth_points) ? notificationFixture.growth_points : [];
  return {
    schema_version: "a3.notification_control_plane_export.v1",
    available: true,
    source: notificationFixture.source || "unknown",
    status: notificationFixture.status || "unknown",
    channel_count: summary.channel_count || channels.length,
    api_backed_count: summary.api_backed_count || channels.filter((item) => (item.api_routes || item.api?.routes || []).length > 0).length,
    audit_backed_count: summary.audit_backed_count || channels.filter((item) => (item.audit_events || item.audit?.events || []).length > 0).length,
    live_mutation_count: summary.live_mutation_count || 0,
    growth_point_count: summary.growth_point_count || growthPoints.length,
    strongest_money_path: summary.strongest_money_path || "PR gate + incident replay + enterprise audit notifications",
    channels: channels.map((item) => ({
      id: item.id,
      provider: item.provider,
      label: item.label,
      status: item.status,
      current_mode: item.current_mode,
      api_routes: item.api_routes || item.api?.routes || [],
      db_tables: item.db_tables || item.db?.tables || [],
      event_types: item.event_types || item.event?.types || [],
      artifact_types: item.artifact_types || item.artifact?.types || [],
      usage_meters: item.usage_meters || item.usage?.meters || [],
      audit_events: item.audit_events || item.audit?.events || [],
      a1_dependency: item.a1_dependency || item.dependencies?.A1,
      a2_dependency: item.a2_dependency || item.dependencies?.A2,
      next_action: item.next_action
    })),
    trigger_count: Array.isArray(notificationFixture.trigger_matrix) ? notificationFixture.trigger_matrix.length : 0,
    top_growth_points: growthPoints.slice(0, 8).map((item) => ({
      id: item.id,
      title: item.title || item.action,
      surface: item.surface || item.provider,
      priority: item.priority || "P2",
      expected_artifact: item.expected_artifact || item.contract_surface?.artifacts?.join(", ") || "notification evidence"
    })),
    safety: {
      secret_values_included: notificationFixture.safety?.secret_values_included === true,
      raw_webhook_urls_included: notificationFixture.safety?.raw_webhook_urls_included === true,
      raw_tokens_included: notificationFixture.safety?.raw_tokens_included === true,
      raw_emails_included: notificationFixture.safety?.raw_emails_included === true,
      real_external_mutation_performed_locally: notificationFixture.safety?.real_external_mutation_performed_locally === true
    },
    recommendation: "Use Notification Control Plane as the collaboration layer for PR gates, incident replay, reviewer workflow, and enterprise audit packets while A1 owns live delivery workers and connector secrets."
  };
}

function summarizeGithubPublishRecord(record = {}, type = "unknown") {
  if (!record.schema_version) {
    return {
      type,
      available: false,
      status: "missing",
      posted: false,
      dry_run: null
    };
  }
  return {
    type,
    available: true,
    schema_version: record.schema_version,
    mode: record.mode || "unknown",
    status: record.status || (String(record.mode || "").startsWith("plan_") ? "planned" : "unknown"),
    posted: record.posted === true,
    dry_run: record.dry_run === true || record.safety?.dry_run_only === true,
    http_status: record.http_status ?? null,
    github_request_id: record.github_request_id || null,
    redacted_summary: record.redacted_summary || null,
    token_included: record.safety?.token_included === true,
    secret_values_allowed: record.safety?.secret_values_allowed === true
  };
}


function hashPrefix(value, length = 16) {
  return typeof value === "string" && value.length ? value.slice(0, length) : null;
}

function hasReleaseEvidenceObject(value = {}) {
  return isObject(value) && Boolean(value.schema_version || value.status || value.mode || value.request || value.plan || value.root_hash || value.signature || value.entries || value.artifacts);
}

function summarizeGithubCheckPublishReceipt(receipt = {}) {
  const request = objectOr(receipt.request);
  const body = objectOr(request.body);
  const repo = objectOr(request.repo);
  return {
    available: hasReleaseEvidenceObject(receipt),
    mode: receipt.mode || request.mode || "unknown",
    status: receipt.status || "missing",
    dry_run: receipt.dry_run === true || request.safety?.dry_run_only === true,
    posted: receipt.posted === true,
    http_status: numberOrNull(receipt.http_status),
    check_name: body.name || "unknown",
    conclusion: body.conclusion || receipt.check_run?.conclusion || "unknown",
    repo: repo.owner && repo.repo ? `${repo.owner}/${repo.repo}` : "unknown",
    requires_token_scope: request.requires_token_scope || "unknown",
    token_included: receipt.safety?.token_included === true || request.safety?.token_included === true,
    secret_values_allowed: receipt.safety?.secret_values_allowed === true || request.safety?.secret_values_allowed === true,
    redacted_summary: receipt.redacted_summary || "No redacted publish summary available."
  };
}

function summarizeGithubPrCommentPublishReceipt(receipt = {}) {
  const plan = objectOr(receipt.plan);
  const repo = objectOr(plan.repo);
  return {
    available: hasReleaseEvidenceObject(receipt),
    mode: receipt.mode || plan.mode || "unknown",
    status: receipt.status || "missing",
    dry_run: receipt.dry_run === true || plan.safety?.dry_run_only === true,
    posted: receipt.posted === true,
    http_status: numberOrNull(receipt.http_status),
    repo: repo.owner && repo.repo ? `${repo.owner}/${repo.repo}` : "unknown",
    pull_number: numberOrNull(plan.pull_number),
    requires_token_scope: plan.requires_token_scope || "unknown",
    token_included: receipt.safety?.token_included === true || plan.safety?.token_included === true,
    secret_values_allowed: receipt.safety?.secret_values_allowed === true || plan.safety?.secret_values_allowed === true,
    redacted_summary: receipt.redacted_summary || "No redacted PR comment summary available."
  };
}

function summarizeGithubRequiredCheckPlan(plan = {}) {
  const repo = objectOr(plan.repo);
  return {
    available: hasReleaseEvidenceObject(plan),
    mode: plan.mode || "unknown",
    status: plan.required_for_commercial_gate === true ? "planned" : "missing",
    repo: repo.owner && repo.repo ? `${repo.owner}/${repo.repo}` : "unknown",
    branch: plan.branch || "unknown",
    check_name: plan.check_name || "unknown",
    required_for_commercial_gate: plan.required_for_commercial_gate === true,
    maintainer_approval_required: plan.safety?.maintainer_approval_required === true,
    dry_run: plan.safety?.dry_run_only === true,
    requires_token_scope: plan.requires_token_scope || "unknown",
    token_included: plan.safety?.token_included === true,
    secret_values_allowed: plan.safety?.secret_values_allowed === true,
    redacted_summary: plan.redacted_summary || "No required-check plan summary available."
  };
}

function summarizeGithubCheckReadbackReceipt(receipt = {}) {
  return {
    available: hasReleaseEvidenceObject(receipt),
    schema_version: receipt.schema_version || "unknown",
    readback_id: receipt.readback_id || null,
    readback_status: receipt.readback_status || receipt.status || "missing",
    readback_confirmed: receipt.readback_confirmed === true || receipt.readback_status === "readback_confirmed",
    posted: receipt.posted === true,
    stale: receipt.stale === true || receipt.readback_status === "stale",
    missing: receipt.missing === true || receipt.readback_status === "missing",
    deleted: receipt.deleted === true || receipt.readback_status === "deleted",
    permission_denied: receipt.readback_status === "permission_denied",
    check_name: receipt.expected?.check_name || receipt.observed?.check_name || "unknown",
    head_sha_match: receipt.matches?.head_sha ?? null,
    output_hash_match: receipt.matches?.output_hash ?? null,
    payload_hash: receipt.payload_hash || null,
    sanitized_error_class: receipt.sanitized_error_class || null,
    token_included: receipt.safety?.token_included === true,
    secret_values_allowed: receipt.safety?.secret_values_allowed === true
  };
}

function summarizeGithubPrCommentReadbackReceipt(receipt = {}) {
  return {
    available: hasReleaseEvidenceObject(receipt),
    schema_version: receipt.schema_version || "unknown",
    readback_id: receipt.readback_id || null,
    readback_status: receipt.readback_status || receipt.status || "missing",
    readback_confirmed: receipt.readback_confirmed === true || receipt.readback_status === "readback_confirmed",
    posted: receipt.posted === true,
    stale: receipt.stale === true || receipt.readback_status === "stale",
    missing: receipt.missing === true || receipt.readback_status === "missing",
    deleted: receipt.deleted === true || receipt.readback_status === "deleted",
    permission_denied: receipt.readback_status === "permission_denied",
    pull_number: numberOrNull(receipt.expected?.pull_number),
    marker_match: receipt.matches?.marker ?? receipt.marker_match ?? null,
    body_hash_match: receipt.matches?.body_hash ?? receipt.body_hash_match ?? null,
    payload_hash: receipt.payload_hash || null,
    sanitized_error_class: receipt.sanitized_error_class || null,
    token_included: receipt.safety?.token_included === true,
    secret_values_allowed: receipt.safety?.secret_values_allowed === true
  };
}

function summarizeGithubRequiredCheckProof(proof = {}) {
  return {
    available: hasReleaseEvidenceObject(proof),
    schema_version: proof.schema_version || "unknown",
    proof_id: proof.proof_id || null,
    readback_status: proof.readback_status || proof.enforcement_readback_status || "plan_only",
    enforcement_readback_status: proof.enforcement_readback_status || proof.readback_status || "plan_only",
    enforced: proof.enforced === true,
    plan_only_must_not_claim_enforcement: proof.plan_only_must_not_claim_enforcement !== false,
    check_name: proof.check_name || "unknown",
    branch: proof.branch || "unknown",
    checked_count: proof.checked_count || 0,
    payload_hash: proof.payload_hash || null,
    sanitized_error_class: proof.sanitized_error_class || null,
    token_included: proof.safety?.token_included === true,
    secret_values_allowed: proof.safety?.secret_values_allowed === true
  };
}

function normalizeReleaseEvidenceReadbackResourceKind(value, schemaVersion = "") {
  const kind = String(value || "").toLowerCase();
  if (["check_run", "github_check"].includes(kind) || String(schemaVersion).includes("github_check")) {
    return "github_check";
  }
  if (["pr_comment", "pull_request_comment"].includes(kind) || String(schemaVersion).includes("pr_comment")) {
    return "pr_comment";
  }
  if (["required_check", "branch_protection"].includes(kind) || String(schemaVersion).includes("required_check")) {
    return "required_check";
  }
  return kind || "unknown";
}

function summarizeReleaseEvidenceReadbackRecord(record = {}, index = 0) {
  const schemaVersion = record.schema_version || "unknown";
  const resourceKind = normalizeReleaseEvidenceReadbackResourceKind(record.resource_kind || record.resourceKind, schemaVersion);
  const status = record.readback_status || record.enforcement_readback_status || record.status || "missing";
  return {
    readback_id: record.readback_id || record.proof_id || `readback_${index + 1}`,
    provider: record.provider || "github",
    resource_kind: resourceKind,
    readback_status: status,
    readback_confirmed: record.readback_confirmed === true || status === "readback_confirmed",
    stale: record.stale === true || status === "stale",
    missing: record.missing === true || status === "missing",
    deleted: record.deleted === true || status === "deleted",
    enforced: record.enforced === true,
    check_name: record.check_name || record.expected?.check_name || record.matched_check?.context || "unknown",
    external_id_alias: record.external_id_alias
      || record.expected?.check_run_id_alias
      || record.expected?.comment_id_alias
      || record.matched_check?.context
      || null,
    payload_hash_prefix: hashPrefix(record.payload_hash),
    captured_at: record.captured_at || record.checked_at || null,
    sanitized_error_class: record.sanitized_error_class || null
  };
}

function countReleaseEvidenceReadbackRecords(records = [], field) {
  return records.reduce((counts, record) => {
    const key = record[field] || "unknown";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function collectReleaseEvidenceReadbackRecords(fixture = {}, fallbacks = []) {
  const containers = [
    fixture.readback_records,
    fixture.releaseEvidenceReadbacks,
    fixture.release_evidence_readbacks,
    fixture.readbacks
  ];
  for (const container of containers) {
    if (Array.isArray(container)) {
      return container;
    }
    if (isObject(container)) {
      for (const key of ["records", "latest_records", "readbacks", "readback_records"]) {
        if (Array.isArray(container[key])) {
          return container[key];
        }
      }
    }
  }
  return fallbacks.filter((item) => item && item.available !== false && item.readback_status !== "missing");
}

function summarizeReleaseEvidenceReadbackHistory(fixture = {}, fallbacks = []) {
  const records = collectReleaseEvidenceReadbackRecords(fixture, fallbacks)
    .map((record, index) => summarizeReleaseEvidenceReadbackRecord(record, index));
  return {
    schema_version: "a3.release_evidence_readback_history.v1",
    available: records.length > 0,
    readback_count: records.length,
    status_counts: countReleaseEvidenceReadbackRecords(records, "readback_status"),
    resource_counts: countReleaseEvidenceReadbackRecords(records, "resource_kind"),
    latest_records: records.slice(-8),
    a1_a2_boundary: "Readback confirms external publication state; it does not replace A1 RunResult execution evidence or A2 GradeResult judge semantics."
  };
}

function summarizeAuditBundleVerification(verification = {}) {
  const artifacts = objectOr(verification.artifacts);
  const custody = objectOr(verification.chain_of_custody);
  const safety = objectOr(verification.safety);
  return {
    available: hasReleaseEvidenceObject(verification),
    status: verification.status || "missing",
    bundle_id: verification.bundle_id || "unknown",
    root_hash_passed: verification.root_hash?.passed === true,
    root_hash_prefix: hashPrefix(verification.root_hash?.actual || verification.root_hash?.expected),
    artifact_total: artifacts.total || 0,
    artifact_checked: artifacts.checked || 0,
    artifact_passed: artifacts.passed || 0,
    artifact_failed: artifacts.failed || 0,
    custody_total: custody.total || 0,
    custody_passed: custody.passed || 0,
    custody_failed: custody.failed || 0,
    finding_count: Array.isArray(verification.findings) ? verification.findings.length : 0,
    contains_secret_values: safety.contains_secret_values === true,
    unsafe_path_count: safety.unsafe_path_count || 0,
    self_hash_excluded: safety.self_hash_excluded === true,
    process_exit_code: numberOrNull(verification.process_exit_code)
  };
}

function summarizeAuditArchiveVerification(verification = {}) {
  const entries = objectOr(verification.entries);
  const signature = objectOr(verification.signature);
  const safety = objectOr(verification.safety);
  return {
    available: hasReleaseEvidenceObject(verification),
    status: verification.status || "missing",
    archive_id: verification.archive_id || "unknown",
    root_hash_passed: verification.root_hash?.passed === true,
    root_hash_prefix: hashPrefix(verification.root_hash?.actual || verification.root_hash?.expected),
    signature_passed: signature.passed === true,
    signature_algorithm: signature.algorithm || "unknown",
    signer_type: signature.signer_type || "unknown",
    identity_binding: signature.identity_binding || "unknown",
    entry_total: entries.total || 0,
    entry_checked: entries.checked || 0,
    entry_passed: entries.passed || 0,
    entry_failed: entries.failed || 0,
    finding_count: Array.isArray(verification.findings) ? verification.findings.length : 0,
    contains_secret_values: safety.contains_secret_values === true,
    unsafe_path_count: safety.unsafe_path_count || 0,
    raw_private_key_stored: safety.raw_private_key_stored === true,
    process_exit_code: numberOrNull(verification.process_exit_code)
  };
}

export function summarizeReleaseEvidenceSummary(releaseEvidenceFixture = {}) {
  const fixture = isObject(releaseEvidenceFixture) ? releaseEvidenceFixture : {};
  if (fixture.schema_version === "a3.release_evidence_summary.v1") {
    const githubCheckReadback = summarizeGithubCheckReadbackReceipt(fixture.github_check_readback || {});
    const prCommentReadback = summarizeGithubPrCommentReadbackReceipt(fixture.pr_comment_readback || {});
    const requiredCheckProof = summarizeGithubRequiredCheckProof(fixture.required_check_proof || {});
    const history = summarizeReleaseEvidenceReadbackHistory(fixture, [
      githubCheckReadback,
      prCommentReadback,
      requiredCheckProof
    ]);
    return {
      ...fixture,
      schema_version: "a3.release_evidence_summary.v1",
      available: fixture.available === true,
      github_check_readback: fixture.github_check_readback || githubCheckReadback,
      pr_comment_readback: fixture.pr_comment_readback || prCommentReadback,
      required_check_proof: fixture.required_check_proof || requiredCheckProof,
      readback_history: fixture.readback_history || history,
      readback_records: fixture.readback_records || history.latest_records,
      readback_record_count: fixture.readback_record_count ?? history.readback_count,
      readback_status_counts: fixture.readback_status_counts || history.status_counts,
      readback_resource_counts: fixture.readback_resource_counts || history.resource_counts
    };
  }

  const githubCheck = summarizeGithubCheckPublishReceipt(fixture.githubCheckPublishReceipt || fixture.github_check_publish_receipt || fixture.github_check || {});
  const prComment = summarizeGithubPrCommentPublishReceipt(fixture.githubPrCommentPublishReceipt || fixture.github_pr_comment_publish_receipt || fixture.pr_comment || {});
  const requiredCheck = summarizeGithubRequiredCheckPlan(fixture.githubRequiredCheckPlan || fixture.github_required_check_plan || fixture.required_check_plan || {});
  const githubCheckReadback = summarizeGithubCheckReadbackReceipt(fixture.githubCheckReadback || fixture.github_check_readback || {});
  const prCommentReadback = summarizeGithubPrCommentReadbackReceipt(fixture.githubPrCommentReadback || fixture.pr_comment_readback || {});
  const requiredCheckProof = summarizeGithubRequiredCheckProof(fixture.githubRequiredCheckProof || fixture.required_check_proof || {});
  const readbackHistory = summarizeReleaseEvidenceReadbackHistory(fixture, [
    fixture.githubCheckReadback || fixture.github_check_readback || githubCheckReadback,
    fixture.githubPrCommentReadback || fixture.pr_comment_readback || prCommentReadback,
    fixture.githubRequiredCheckProof || fixture.required_check_proof || requiredCheckProof
  ]);
  const auditBundle = summarizeAuditBundleVerification(fixture.auditBundleVerification || fixture.audit_bundle_verification || {});
  const auditArchive = summarizeAuditArchiveVerification(fixture.auditArchiveVerification || fixture.audit_archive_verification || {});
  const surfaces = [githubCheck, prComment, requiredCheck, auditBundle, auditArchive];
  const availableCount = surfaces.filter((item) => item.available).length;
  const verificationPassed = auditBundle.available
    && auditArchive.available
    && auditBundle.status === "passed"
    && auditArchive.status === "passed"
    && auditBundle.root_hash_passed
    && auditArchive.root_hash_passed
    && auditArchive.signature_passed;
  const publishPlanned = githubCheck.available && prComment.available && requiredCheck.available;
  const safety = {
    token_included: githubCheck.token_included || prComment.token_included || requiredCheck.token_included,
    secret_values_allowed: githubCheck.secret_values_allowed || prComment.secret_values_allowed || requiredCheck.secret_values_allowed,
    contains_secret_values: auditBundle.contains_secret_values || auditArchive.contains_secret_values,
    raw_private_key_stored: auditArchive.raw_private_key_stored,
    real_github_mutation_performed: githubCheck.posted || prComment.posted,
    dry_run_only: (githubCheck.available ? githubCheck.dry_run && !githubCheck.posted : true)
      && (prComment.available ? prComment.dry_run && !prComment.posted : true)
      && (requiredCheck.available ? requiredCheck.dry_run : true)
  };

  return {
    schema_version: "a3.release_evidence_summary.v1",
    available: availableCount > 0,
    overall_status: verificationPassed ? "verified" : publishPlanned ? "planned" : availableCount ? "partial" : "missing",
    available_surface_count: availableCount,
    github_check_publish: githubCheck,
    github_pr_comment_publish: prComment,
    github_required_check_plan: requiredCheck,
    github_check_readback: githubCheckReadback,
    pr_comment_readback: prCommentReadback,
    required_check_proof: requiredCheckProof,
    readback_history: readbackHistory,
    readback_records: readbackHistory.latest_records,
    readback_record_count: readbackHistory.readback_count,
    readback_status_counts: readbackHistory.status_counts,
    readback_resource_counts: readbackHistory.resource_counts,
    audit_bundle_verification: auditBundle,
    audit_archive_verification: auditArchive,
    safety,
    commercial_value: "Turns release evidence into a customer-visible control: PR gate publication, required-check rollout, bundle verification, and signed archive verification can be reviewed before an agent ships.",
    recommendation: verificationPassed
      ? "Expose this release evidence in hosted reports and PR gates so reviewers can sign off on verified artifacts instead of trusting local files."
      : "Attach GitHub publish receipts plus audit bundle/archive verification before claiming enterprise release evidence is complete."
  };
}

export function buildMarkdownReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}, evidenceReadinessFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}, mediaSignedUrlFixture = {}, authFixture = {}, frontendFixture = {}, frontendMirrorFixture = {}, frontendCodeCrawlFixture = {}, productConsoleFixture = {}, saasAdminFixture = {}, a2ReadinessBundle = {}, artifactRegistryFixture = {}, releaseEvidenceFixture = {}, githubPublishEvidenceFixture = {}, peerBranchCalibrationFixture = {}, billingMigrationReadinessFixture = {}, notificationControlPlaneFixture = {}, multimodalReviewQueueFixture = {}) {
  if (isArtifactRegistryFixture(a2ReadinessBundle) && !isArtifactRegistryFixture(artifactRegistryFixture)) {
    artifactRegistryFixture = a2ReadinessBundle;
    a2ReadinessBundle = {};
  }
  const productConsoleAsA2Bundle = isA2ReadinessBundle(productConsoleFixture);
  const effectiveA2ReadinessBundle = isA2ReadinessBundle(a2ReadinessBundle)
    ? a2ReadinessBundle
    : productConsoleAsA2Bundle
      ? productConsoleFixture
      : {};
  if (productConsoleAsA2Bundle) {
    productConsoleFixture = {};
  }
  const a2Readiness = normalizeA2ReadinessArgs(requestFixture, usageFixture, usageApiProbe, effectiveA2ReadinessBundle, mediaSignedUrlFixture);
  if (a2Readiness.legacyA2Args) {
    requestFixture = {};
    usageFixture = {};
    usageApiProbe = {};
  }
  const reportMediaSignedUrlFixture = a2Readiness.legacyA2Args ? {} : mediaSignedUrlFixture;
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const coverage = summarizeCoverage(coverageFixture);
  const evidenceReadiness = summarizeEvidenceReadiness(evidenceReadinessFixture);
  const regressionReadiness = summarizeRegressionReadiness(a2Readiness.caseBookFixture, a2Readiness.regressionReplayFixture);
  const commercialReadiness = summarizeCommercialReadiness(a2Readiness.commercialReadinessFixture);
  const resultPersistence = summarizeA2ResultPersistence(a2Readiness.resultPersistenceFixture);
  const releaseUnblockChecklist = summarizeA2ReleaseUnblockChecklist(a2Readiness.releaseUnblockChecklistFixture);
  const a2CrossLaneSecurityContext = summarizeA2CrossLaneSecurityContext(a2Readiness.crossLaneSecurityContextFixture);
  const a2SqlStoreReport = summarizeA2SqlStoreReport(a2Readiness.sqlStoreReportFixture);
  const requestProvenance = summarizeRequestProvenance(requestFixture);
  const usageQuota = summarizeUsageQuota(usageFixture, usageApiProbe);
  const billingUsage = summarizeBillingUsage(runFixture, gradeFixture, usageFixture, usageApiProbe);
  const billingMigrationReadiness = summarizeBillingMigrationReadiness(billingMigrationReadinessFixture);
  const mediaReadiness = summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, reportMediaSignedUrlFixture);
  const cloudConsoleShell = summarizeCloudConsoleShell(authFixture, frontendFixture, requestFixture, usageFixture, usageApiProbe);
  const officialGap = summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe);
  const officialFrontendMirror = summarizeOfficialFrontendMirror(frontendMirrorFixture);
  const officialCodeCrawlParity = summarizeOfficialCodeCrawlParity(frontendCodeCrawlFixture);
  const officialParityRoadmap = summarizeOfficialParityRoadmap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe, reportMediaSignedUrlFixture, frontendMirrorFixture);
  const releaseWorkflowOptions = isA2ReleaseGateFixture(a2Readiness.releaseGateFixture)
    ? { a2ReleaseGate: a2Readiness.releaseGateFixture }
    : {};
  const releaseGate = isA2ReleaseGateFixture(a2Readiness.releaseGateFixture)
    ? summarizeReleaseGate(a2Readiness.releaseGateFixture)
    : summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture);
  const releaseWorkflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, releaseWorkflowOptions);
  const releaseWarRoom = summarizeReleaseWarRoom(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, requestFixture, usageFixture, usageApiProbe, frontendMirrorFixture, releaseWorkflowOptions);
  const incidentReplayQueue = summarizeIncidentReplayQueue(runFixture, gradeFixture, reportMediaSignedUrlFixture);
  const reviewerWorkflowBoard = summarizeReviewerWorkflowBoard(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, releaseWorkflowOptions);
  const observabilityReplayMatrix = summarizeObservabilityReplayMatrix(runFixture, gradeFixture, reportMediaSignedUrlFixture, frontendCodeCrawlFixture);
  const regressionFactory = summarizeRegressionFactory(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, frontendCodeCrawlFixture);
  const exportRedactionFirewall = summarizeExportRedactionFirewall(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, frontendCodeCrawlFixture);
  const productConsole = summarizeProductConsoleExport(productConsoleFixture);
  const saasAdmin = summarizeSaasAdminExport(saasAdminFixture);
  const artifactRegistry = summarizeArtifactRegistryExport(artifactRegistryFixture);
  const releaseEvidence = summarizeReleaseEvidenceSummary(releaseEvidenceFixture);
  const githubPublishEvidence = summarizeGithubPublishEvidence(githubPublishEvidenceFixture);
  const notificationControlPlane = summarizeNotificationControlPlane(notificationControlPlaneFixture);
  const liveOpsControlPlane = summarizeLiveOpsControlPlaneExport(notificationControlPlaneFixture.live_ops_control_plane || {});
  const peerBranchCalibration = summarizeA3PeerBranchCalibration(peerBranchCalibrationFixture);
  const multimodalReviewQueue = summarizeMultimodalReviewQueueExport(multimodalReviewQueueFixture);
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

  if (releaseGate.available && releaseGate.schema_version === "a2.release_gate.v1") {
    lines.push(
      "## Release Gate",
      "",
      `- Decision: ${releaseGate.decision}`,
      `- Blocks release: ${releaseGate.blocks_release ? "yes" : "no"}`,
      `- Exit code: ${releaseGate.exit_code}`,
      `- Risk score: ${releaseGate.risk_score}`,
      `- Current commercial gate: ${releaseGate.current_commercial_gate}`,
      `- Blocking gates: ${releaseGate.blocker_gates.join(", ") || "none"}`,
      `- Blocker types: ${releaseGate.blocker_types.join(", ") || "none"}`,
      `- Evidence blockers: ${releaseGate.evidence_blocker_count}`,
      `- Warnings: ${releaseGate.warning_count}`,
      `- Required sources: ${releaseGate.required_sources.join(", ") || "none"}`,
      `- CI mode: ${releaseGate.ci_mode}`,
      ""
    );
  } else if (releaseGate.available) {
    lines.push(
      "## Release Gate",
      "",
      `- Decision: ${releaseGate.decision_label}`,
      `- Risk score: ${releaseGate.risk_score}`,
      `- Failed checks: ${releaseGate.failed_check_count}`,
      `- Required approvers: ${releaseGate.required_approvers.join(", ") || "none"}`,
      `- PR gate: ${releaseGate.pr_gate.blocks_merge ? "blocks merge" : releaseGate.pr_gate.warning_only ? "warning only" : "pass"}`,
      `- Commercial value: ${releaseGate.commercial_value}`,
      ""
    );
    for (const check of releaseGate.checks) {
      lines.push(`- ${check.id}: ${check.passed ? "pass" : "fail"} - ${check.observed}. ${check.detail}`);
    }
    lines.push("");
  }

  if (releaseWorkflow.available) {
    lines.push(
      "## PR Gate / Review Workflow",
      "",
      `- GitHub check: ${releaseWorkflow.github_check.name}`,
      `- Check conclusion: ${releaseWorkflow.github_check.conclusion}`,
      `- Waiver required: ${releaseWorkflow.waiver_policy.required ? "yes" : "no"}`,
      `- Waiver allowed: ${releaseWorkflow.waiver_policy.allowed ? "yes" : "no"}`,
      `- Review state: ${releaseWorkflow.reviewer_workflow.state}`,
      `- Review lanes: ${releaseWorkflow.reviewer_workflow.review_lanes.join(", ") || "none"}`,
      `- Audit bundle artifacts: ${releaseWorkflow.audit_bundle.artifacts.map((item) => item.id).join(", ")}`,
      `- Incident replay cases: ${releaseWorkflow.incident_replay.case_ids.join(", ") || "none"}`,
      `- Commercial value: ${releaseWorkflow.commercial_value}`,
      ""
    );
    lines.push("### PR Comment Template", "", releaseWorkflow.pr_comment_markdown.trim(), "");
  }


  if (githubPublishEvidence.available) {
    lines.push(
      "## GitHub Publish Evidence",
      "",
      `- Status: ${githubPublishEvidence.status}`,
      `- Dry-run only: ${githubPublishEvidence.dry_run_only ? "yes" : "no"}`,
      `- Posted receipts: ${githubPublishEvidence.posted_count}`,
      `- Planned receipts: ${githubPublishEvidence.planned_count}`,
      `- Check: ${githubPublishEvidence.check_publish.status}`,
      `- PR comment: ${githubPublishEvidence.pr_comment_publish.status}`,
      `- Required check planned: ${githubPublishEvidence.required_check_planned ? "yes" : "no"}`,
      `- Required scopes: ${githubPublishEvidence.required_token_scopes.join(", ") || "none"}`,
      `- Maintainer approval required: ${githubPublishEvidence.maintainer_approval_required ? "yes" : "no"}`,
      ""
    );
  }

  if (liveOpsControlPlane.available) {
    lines.push(
      `## Live Ops Control Plane`,
      ``,
      `- Status: ${liveOpsControlPlane.status}`,
      `- Lanes: ${liveOpsControlPlane.lane_count}`,
      `- API-backed: ${liveOpsControlPlane.api_backed_count}`,
      `- Audit-backed: ${liveOpsControlPlane.audit_backed_count}`,
      `- Local external mutations: ${liveOpsControlPlane.local_external_mutation_count}`,
      `- Reviewer actions: ${liveOpsControlPlane.human_operation_summary.review_record_count || 0}`,
      `- Shareable reports: ${liveOpsControlPlane.report_link_summary.shareable_count || 0}`,
      `- Commercial sign-off: ${liveOpsControlPlane.commercial_signoff_summary.status || "unknown"}`,
      `- Required roles: ${(liveOpsControlPlane.commercial_signoff_summary.required_roles || []).join(", ") || "unknown"}`,
      `- Customer external blocked: ${liveOpsControlPlane.commercial_signoff_summary.customer_external_blocked ? "yes" : "no"}`,
      ``
    );
    for (const item of liveOpsControlPlane.reviewer_timeline.slice(0, 4)) {
      lines.push(`- reviewer ${item.record_type}: ${item.status} / ${item.reason}`);
    }
    for (const item of liveOpsControlPlane.github_publish_timeline.slice(0, 3)) {
      lines.push(`- github ${item.step}: ${item.status} / ${item.target}`);
    }
    lines.push(``);
  }

  if (notificationControlPlane.available) {
    lines.push(
      "## Notification Control Plane",
      "",
      `- Status: ${notificationControlPlane.status}`,
      `- Channels: ${notificationControlPlane.channel_count}`,
      `- API-backed: ${notificationControlPlane.api_backed_count}`,
      `- Audit-backed: ${notificationControlPlane.audit_backed_count}`,
      `- Live external mutations: ${notificationControlPlane.live_mutation_count}`,
      `- Growth points: ${notificationControlPlane.growth_point_count}`,
      `- Strongest money path: ${notificationControlPlane.strongest_money_path}`,
      `- Safety: secrets ${notificationControlPlane.safety.secret_values_included ? "present" : "blocked"}, webhook URLs ${notificationControlPlane.safety.raw_webhook_urls_included ? "present" : "blocked"}, live send ${notificationControlPlane.safety.real_external_mutation_performed_locally ? "performed" : "not performed"}`,
      ""
    );
    for (const channel of notificationControlPlane.channels) {
      lines.push(`- ${channel.provider}: ${channel.status}, events ${channel.event_types.join(", ") || "none"}, meter ${channel.usage_meters.join(", ") || "none"}`);
    }
    lines.push("");
  }

  if (peerBranchCalibration.available) {
    lines.push(
      "## Peer Branch Calibration",
      "",
      `- Status: ${peerBranchCalibration.status}`,
      `- Peer branches: ${peerBranchCalibration.peer_branch_count}`,
      `- Peer deltas: ${peerBranchCalibration.peer_delta_count}`,
      `- A1/A2 peer delta evidence: ${peerBranchCalibration.peer_delta_count} downstream contract change(s) observed before merge.`,
      `- Blocking deltas: ${peerBranchCalibration.blocking_delta_count}`,
      `- Ready deltas: ${peerBranchCalibration.ready_delta_count}`,
      `- Growth points: ${peerBranchCalibration.growth_point_count}`,
      `- Boundary: ${peerBranchCalibration.a1_a2_boundary}`,
      `- Commercial value: ${peerBranchCalibration.commercial_value}`,
      ""
    );
    for (const item of peerBranchCalibration.action_items.slice(0, 5)) {
      lines.push(`- ${item.priority} ${item.surface}: ${item.action} (${item.evidence_ref})`);
    }
    lines.push("");
  }

  if (productConsole.available) {
    lines.push(
      "## Product Console / Onboarding / Audit",
      "",
      `- Source: ${productConsole.source}`,
      `- Onboarding: ${productConsole.onboarding.status} (${productConsole.onboarding.completed_steps}/${productConsole.onboarding.total_steps}, ${productConsole.onboarding.completion_rate}%)`,
      `- Project status: ${productConsole.project_console.status}`,
      `- Project evidence: ${productConsole.project_console.run_count} run(s), ${productConsole.project_console.case_count} case(s), ${productConsole.project_console.failed_case_count} failed case(s), ${productConsole.project_console.report_count} report(s)`,
      `- Audit log: ${productConsole.audit_log.status}, ${productConsole.audit_log.event_count} event(s), redacted-only ${productConsole.audit_log.redacted_payload_only ? "yes" : "no"}`,
      `- Commercial readiness: ${productConsole.commercial_readiness.status} / ${productConsole.commercial_readiness.readiness_score}`,
      `- Strongest money path: ${productConsole.commercial_readiness.strongest_money_path}`,
      ""
    );
    if (productConsole.onboarding.next_actions.length) {
      lines.push("### Product Console Next Actions", "", ...productConsole.onboarding.next_actions.map((item) => `- ${item}`), "");
    }
    if (productConsole.commercial_readiness.checks.length) {
      lines.push("### Product Console Readiness Checks", "");
      for (const check of productConsole.commercial_readiness.checks) {
        lines.push(`- ${check.id}: ${check.status}`);
      }
      lines.push("");
    }
  }

  if (saasAdmin.available) {
    lines.push(
      "## SaaS Admin / Login / Team / Trust",
      "",
      `- Source: ${saasAdmin.source}`,
      `- Login: ${saasAdmin.login.status}, ${saasAdmin.login.provider}, identity redacted ${saasAdmin.login.user_identity_redacted ? "yes" : "no"}`,
      `- Team: ${saasAdmin.team.status}, ${saasAdmin.team.member_count} member(s), invite mode ${saasAdmin.team.invite_mode}`,
      `- Usage: ${saasAdmin.usage.status}, plan ${saasAdmin.usage.plan_name}, quota mutation ${saasAdmin.usage.quota_mutations_enabled ? "enabled" : "disabled"}`,
      `- API keys: ${saasAdmin.api_keys.status}, ${saasAdmin.api_keys.key_count} metadata row(s), reveal policy ${saasAdmin.api_keys.reveal_policy}`,
      `- Trust: ${saasAdmin.trust.status}, publish ${saasAdmin.trust.publish_enabled ? "enabled" : "disabled"}, public publish ${saasAdmin.trust.public_publish_enabled ? "enabled" : "disabled"}`,
      `- Cloud management: ${saasAdmin.cloud_management.status}, ${saasAdmin.cloud_management.resource_count} resource(s), real mutations ${saasAdmin.cloud_management.real_mutations_enabled ? "enabled" : "disabled"}`,
      `- A1/A2 compatibility: A1 ${saasAdmin.a1_a2_compatibility.a1_run_result_ready ? "ready" : "missing"}, A2 ${saasAdmin.a1_a2_compatibility.a2_grade_result_ready ? "ready" : "missing"}`,
      `- Safety mode: ${saasAdmin.safety.mode}, secret values allowed ${saasAdmin.safety.secret_values_allowed ? "yes" : "no"}`,
      ""
    );
    if (saasAdmin.action_plans.length) {
      lines.push("### SaaS Admin Action Guardrails", "");
      for (const action of saasAdmin.action_plans) {
        lines.push(`- ${action.action}: ${action.mode}, real cloud write ${action.writes_real_ashr_cloud ? "yes" : "no"}`);
      }
      lines.push("");
    }
  }

  if (artifactRegistry.available) {
    lines.push(
      "## Artifact Registry",
      "",
      `- Source: ${artifactRegistry.source}`,
      `- Status: ${artifactRegistry.status}`,
      `- Artifacts: ${artifactRegistry.artifact_count} total, ${artifactRegistry.report_artifact_count} report, ${artifactRegistry.control_artifact_count} control`,
      `- Ready: ${artifactRegistry.ready_count}, hash-ready ${artifactRegistry.hash_ready_count}, blocked ${artifactRegistry.blocked_count}`,
      `- Billable meters: ${artifactRegistry.billable_meter_count}`,
      `- Safety: raw secrets ${artifactRegistry.safety.raw_secret_values_allowed ? "allowed" : "blocked"}, raw share tokens ${artifactRegistry.safety.raw_share_tokens_stored ? "stored" : "not stored"}, real cloud mutations ${artifactRegistry.safety.real_cloud_mutations_enabled ? "enabled" : "disabled"}`,
      ""
    );
    if (artifactRegistry.packet_presets.length) {
      lines.push("### Artifact Packet Presets", "");
      for (const preset of artifactRegistry.packet_presets) {
        lines.push(`- ${preset.preset_id}: ${preset.status}${preset.missing_artifact_types.length ? `, missing ${preset.missing_artifact_types.join(", ")}` : ""}`);
      }
      lines.push("");
    }
    if (artifactRegistry.top_artifacts.length) {
      lines.push("### Registry Entries", "");
      for (const artifact of artifactRegistry.top_artifacts) {
        lines.push(`- ${artifact.artifact_type}: ${artifact.lifecycle_state}, ${artifact.hash_status}, ${artifact.redaction_status}, meter ${artifact.billable_meter}`);
        if (artifact.artifact_type === "billing_migration_readiness") {
          lines.push(`  - Missing controls: ${artifact.missing_controls.join(", ") || "none"}`);
          lines.push(`  - Billable value: ${artifact.billable_value || artifact.customer_value}`);
          lines.push(`  - Self-host value: ${artifact.self_host_value || "n/a"}`);
          lines.push(`  - Audit value: ${artifact.audit_value || "n/a"}`);
        }
      }
      lines.push("");
    }
  }

  if (releaseEvidence.available) {
    lines.push(
      "## Release Evidence Summary",
      "",
      `- Overall status: ${releaseEvidence.overall_status}`,
      `- GitHub check publish: ${releaseEvidence.github_check_publish.status}, dry-run ${releaseEvidence.github_check_publish.dry_run ? "yes" : "no"}, posted ${releaseEvidence.github_check_publish.posted ? "yes" : "no"}`,
      `- PR comment publish: ${releaseEvidence.github_pr_comment_publish.status}, dry-run ${releaseEvidence.github_pr_comment_publish.dry_run ? "yes" : "no"}, posted ${releaseEvidence.github_pr_comment_publish.posted ? "yes" : "no"}`,
      `- Required check plan: ${releaseEvidence.github_required_check_plan.check_name}, maintainer approval ${releaseEvidence.github_required_check_plan.maintainer_approval_required ? "required" : "not required"}`,
      `- GitHub check readback: ${releaseEvidence.github_check_readback.readback_status}, hash ${releaseEvidence.github_check_readback.payload_hash ? hashPrefix(releaseEvidence.github_check_readback.payload_hash) : "missing"}, head SHA match ${releaseEvidence.github_check_readback.head_sha_match === null ? "unknown" : releaseEvidence.github_check_readback.head_sha_match ? "yes" : "no"}`,
      `- PR comment readback: ${releaseEvidence.pr_comment_readback.readback_status}, body hash match ${releaseEvidence.pr_comment_readback.body_hash_match === null ? "unknown" : releaseEvidence.pr_comment_readback.body_hash_match ? "yes" : "no"}`,
      `- Required check readback: ${releaseEvidence.required_check_proof.readback_status}, enforced ${releaseEvidence.required_check_proof.enforced ? "yes" : "no"}, plan-only guard ${releaseEvidence.required_check_proof.plan_only_must_not_claim_enforcement ? "on" : "off"}`,
      `- Readback records: ${releaseEvidence.readback_record_count || 0}, confirmed ${releaseEvidence.readback_status_counts?.readback_confirmed || 0}, stale ${releaseEvidence.readback_status_counts?.stale || 0}, missing ${releaseEvidence.readback_status_counts?.missing || 0}`,
      `- A1/A2 boundary: ${releaseEvidence.readback_history?.a1_a2_boundary || "Readback is external publication proof, not runner or judge proof."}`,
      `- Audit bundle verification: ${releaseEvidence.audit_bundle_verification.status}, root hash passed ${releaseEvidence.audit_bundle_verification.root_hash_passed ? "yes" : "no"}, artifacts ${releaseEvidence.audit_bundle_verification.artifact_passed}/${releaseEvidence.audit_bundle_verification.artifact_total}`,
      `- Audit archive verification: ${releaseEvidence.audit_archive_verification.status}, root hash passed ${releaseEvidence.audit_archive_verification.root_hash_passed ? "yes" : "no"}, signature passed ${releaseEvidence.audit_archive_verification.signature_passed ? "yes" : "no"}, entries ${releaseEvidence.audit_archive_verification.entry_passed}/${releaseEvidence.audit_archive_verification.entry_total}`,
      `- Safety: tokens included ${releaseEvidence.safety.token_included ? "yes" : "no"}, secret values ${releaseEvidence.safety.contains_secret_values || releaseEvidence.safety.secret_values_allowed ? "present/allowed" : "blocked"}, raw private key stored ${releaseEvidence.safety.raw_private_key_stored ? "yes" : "no"}, real GitHub mutation ${releaseEvidence.safety.real_github_mutation_performed ? "yes" : "no"}`,
      `- Recommendation: ${releaseEvidence.recommendation}`,
      ""
    );
  }

  if (releaseWarRoom.available) {
    lines.push(
      "## Release War Room",
      "",
      `- Decision: ${releaseWarRoom.decision_label}`,
      `- Urgency: ${releaseWarRoom.urgency}`,
      `- Revenue risk score: ${releaseWarRoom.revenue_risk_score}`,
      `- Blocks merge: ${releaseWarRoom.blocks_merge ? "yes" : "no"}`,
      `- Waiver required: ${releaseWarRoom.waiver_required ? "yes" : "no"}`,
      `- Incident replay cases: ${releaseWarRoom.incident_replay_case_count}`,
      `- Required audit artifacts: ${releaseWarRoom.required_artifact_count}`,
      `- Customer value: ${releaseWarRoom.customer_value}`,
      ""
    );
    lines.push("### Executive Brief", "", ...releaseWarRoom.executive_brief.map((item) => `- ${item}`), "");
    lines.push("### War Room Lanes", "");
    for (const lane of releaseWarRoom.lanes) {
      lines.push(`- ${lane.lane}: ${lane.status} / ${lane.owner} - ${lane.next_action}`);
    }
    lines.push("");
  }

  if (incidentReplayQueue.available) {
    lines.push(
      "## Incident Replay Queue",
      "",
      `- Replay mode: ${incidentReplayQueue.replay_mode}`,
      `- Queue count: ${incidentReplayQueue.queue_count}`,
      `- Blocker cases: ${incidentReplayQueue.blocker_count}`,
      `- Trace-ready cases: ${incidentReplayQueue.trace_ready_count}`,
      `- Tool-diff-ready cases: ${incidentReplayQueue.tool_diff_ready_count}`,
      `- Judge-evidence-ready cases: ${incidentReplayQueue.judge_evidence_ready_count}`,
      `- Media-evidence-ready cases: ${incidentReplayQueue.media_evidence_ready_count}`,
      `- Commercial value: ${incidentReplayQueue.commercial_value}`,
      ""
    );
    lines.push("### Replay Steps", "", ...incidentReplayQueue.replay_steps.map((step) => `- ${step}`), "");
    lines.push("### Replay Cases", "");
    for (const item of incidentReplayQueue.queue) {
      lines.push(`- ${item.rank}. ${item.case_id}: ${item.primary_failure_class} / ${item.severity} / ${item.score} / ${item.owner_lane} - ${item.failure_summary}`);
    }
    lines.push("");
  }

  if (reviewerWorkflowBoard.available) {
    lines.push(
      "## Reviewer Workflow Board",
      "",
      `- Board state: ${reviewerWorkflowBoard.board_label}`,
      `- Required reviewers: ${reviewerWorkflowBoard.required_reviewer_count}`,
      `- Open items: ${reviewerWorkflowBoard.open_item_count}`,
      `- Blocked items: ${reviewerWorkflowBoard.blocked_item_count}`,
      `- Needs evidence: ${reviewerWorkflowBoard.needs_evidence_count}`,
      `- Waiver blocked: ${reviewerWorkflowBoard.waiver_blocked_count}`,
      `- Approval ready: ${reviewerWorkflowBoard.approval_ready_count}`,
      `- A1 trace ready: ${reviewerWorkflowBoard.a1_a2_calibration.a1_trace_ready_count}`,
      `- A1 tool-diff ready: ${reviewerWorkflowBoard.a1_a2_calibration.a1_tool_diff_ready_count}`,
      `- A2 judge evidence ready: ${reviewerWorkflowBoard.a1_a2_calibration.a2_judge_evidence_ready_count}`,
      `- Commercial value: ${reviewerWorkflowBoard.commercial_value}`,
      ""
    );
    lines.push("### Reviewer Lanes", "");
    for (const lane of reviewerWorkflowBoard.lanes) {
      lines.push(`- ${lane.lane}: ${lane.status} / ${lane.item_count} item(s) - ${lane.next_action}`);
    }
    lines.push("", "### Reviewer Items", "");
    for (const item of reviewerWorkflowBoard.items) {
      lines.push(`- ${item.case_id}: ${item.review_state} / ${item.owner_lane} / missing ${item.missing_artifacts.join(", ") || "none"} - ${item.next_action}`);
    }
    lines.push("");
  }

  if (multimodalReviewQueue.available) {
    lines.push(
      "## Multimodal Disagreement Review",
      "",
      `- Status: ${multimodalReviewQueue.status}`,
      `- Capability state: ${multimodalReviewQueue.capability_state}`,
      `- Compared cases: ${multimodalReviewQueue.summary.comparison_count}`,
      `- Repeat comparisons: ${multimodalReviewQueue.summary.repeat_comparison_count}`,
      `- Aggregate comparisons: ${multimodalReviewQueue.summary.aggregate_comparison_count}`,
      `- Semantic disagreements: ${multimodalReviewQueue.summary.semantic_disagreement}`,
      `- Internally unstable aggregates: ${multimodalReviewQueue.summary.internally_unstable}`,
      `- Awaiting human review: ${multimodalReviewQueue.summary.review_required_count}`,
      `- Actively assigned: ${multimodalReviewQueue.summary.assignment_active_count}`,
      `- Unassigned: ${multimodalReviewQueue.summary.assignment_unassigned_count}`,
      `- Expired leases: ${multimodalReviewQueue.summary.assignment_expired_count}`,
      `- Assignment events: ${multimodalReviewQueue.summary.assignment_event_count}`,
      `- Can change release decision: ${multimodalReviewQueue.authority_boundary.can_change_release_decision ? "yes" : "no"}`,
      `- Candidate binding verified: ${multimodalReviewQueue.authority_boundary.candidate_binding_verified ? "yes" : "no"}`,
      ""
    );
    lines.push("### Disagreement Queue", "");
    for (const item of multimodalReviewQueue.items) {
      lines.push(`- ${item.case_id}: ${item.comparison_scope}${item.repeat ? ` #${item.repeat}` : ""} / ${item.left_model}=${item.left_observed_risk} vs ${item.right_model}=${item.right_observed_risk} / ${item.queue_state} / assignment ${item.assignment_status} v${item.assignment_version} / release authority no`);
    }
    lines.push("");
  }

  if (observabilityReplayMatrix.available) {
    lines.push(
      "## Observability Replay Matrix",
      "",
      `- Replay cases: ${observabilityReplayMatrix.replay_case_count}`,
      `- Trace-ready cases: ${observabilityReplayMatrix.trace_ready_count}`,
      `- Tool/error cases: ${observabilityReplayMatrix.tool_error_case_count}`,
      `- Latency/duration cases: ${observabilityReplayMatrix.latency_case_count}`,
      `- Judge-linked cases: ${observabilityReplayMatrix.judge_linked_count}`,
      `- Media cases: ${observabilityReplayMatrix.media_case_count}`,
      `- Blocked replay cases: ${observabilityReplayMatrix.blocked_replay_count}`,
      `- Official observability confirmed: ${observabilityReplayMatrix.official_observability_confirmed ? "yes" : "no"}`,
      `- Commercial value: ${observabilityReplayMatrix.commercial_value}`,
      ""
    );
    lines.push("### Observability Lanes", "");
    for (const lane of observabilityReplayMatrix.lanes) {
      lines.push(`- ${lane.lane}: ${lane.status} / ${lane.ready_count}/${lane.total_count} - ${lane.next_action}`);
    }
    lines.push("", "### Replay Items", "");
    for (const item of observabilityReplayMatrix.items) {
      lines.push(`- ${item.case_id}: ${item.production_risk} / ${item.observability_state} / trace ${item.trace_event_count} / errors ${item.error_signal_count} / judge ${item.judge_evidence_count} - ${item.next_action}`);
    }
    lines.push("");
  }

  if (regressionFactory.available) {
    lines.push(
      "## Regression Factory",
      "",
      `- Factory state: ${regressionFactory.factory_state}`,
      `- Candidate count: ${regressionFactory.candidate_count}`,
      `- Ready candidates: ${regressionFactory.ready_count}`,
      `- Needs evidence: ${regressionFactory.needs_evidence_count}`,
      `- Blocked candidates: ${regressionFactory.blocked_count}`,
      `- Coverage gaps: ${regressionFactory.coverage_gap_count}`,
      `- Tool candidates: ${regressionFactory.tool_candidate_count}`,
      `- Media candidates: ${regressionFactory.media_candidate_count}`,
      `- Official Results review confirmed: ${regressionFactory.official_results_review_confirmed ? "yes" : "no"}`,
      `- Commercial value: ${regressionFactory.commercial_value}`,
      ""
    );
    lines.push("### Generated Suite Plan", "");
    lines.push(
      `- Suite id: ${regressionFactory.generated_suite_plan.suite_id}`,
      `- Source mode: ${regressionFactory.generated_suite_plan.source_mode}`,
      `- Redaction required: ${regressionFactory.generated_suite_plan.redaction_required ? "yes" : "no"}`,
      `- Live cloud mutation required: ${regressionFactory.generated_suite_plan.live_cloud_mutation_required ? "yes" : "no"}`,
      ""
    );
    lines.push("### Factory Lanes", "");
    for (const lane of regressionFactory.lanes) {
      lines.push(`- ${lane.lane}: ${lane.status} / ${lane.ready_count}/${lane.total_count} - ${lane.next_action}`);
    }
    lines.push("", "### Regression Candidates", "");
    for (const item of regressionFactory.candidates) {
      lines.push(`- ${item.regression_id}: ${item.generator_state} / ${item.primary_failure_class} / ${item.coverage_status} / contracts ${item.required_contracts.join(", ")} - ${item.next_action}`);
    }
    lines.push("");
  }

  if (exportRedactionFirewall.available) {
    lines.push(
      "## Export Redaction Firewall",
      "",
      `- Status: ${exportRedactionFirewall.status}`,
      `- Secret-free exports: ${exportRedactionFirewall.secret_free_exports ? "yes" : "no"}`,
      `- Replacement count: ${exportRedactionFirewall.replacement_count}`,
      `- Residual findings: ${exportRedactionFirewall.residual_finding_count}`,
      `- Checked surfaces: ${exportRedactionFirewall.checked_surfaces.map((surface) => surface.surface).join(", ")}`,
      `- Commercial value: ${exportRedactionFirewall.commercial_value}`,
      ""
    );
    for (const surface of exportRedactionFirewall.checked_surfaces) {
      lines.push(`- ${surface.surface}: ${surface.status}, ${surface.replacement_count} replacement(s), ${surface.residual_finding_count} residual finding(s)`);
    }
    lines.push("");
  }

  if (coverage.available) {
    const evidenceLines = coverageEvidenceLines(coverage);
    const exemplarLines = coverageExemplarLines(coverage.capability_axis_exemplars);
    lines.push(
      "## Coverage",
      "",
      `- Assignment minimums met: ${coverage.meets_assignment_minimums ? "yes" : "no"}`,
      `- Scenarios: ${coverage.scenario_count}`,
      `- Scenario dimensions met: ${Object.values(coverage.scenario_dimension_checks).filter(Boolean).length}/${Object.keys(coverage.scenario_dimension_checks).length}`,
      `- Capability axes met: ${Object.values(coverage.capability_axis_checks).filter(Boolean).length}/${Object.keys(coverage.capability_axis_checks).length}`,
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
    if (exemplarLines.length > 0) {
      lines.push(
        "### Capability Axis Exemplars",
        "",
        ...exemplarLines,
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
      `- Ashr public merge: ${evidenceReadiness.ashr_public_merge_status || "unknown"}`,
      `- Ashr safely merged observations: ${evidenceReadiness.ashr_merged_public_observation_count || 0}/${evidenceReadiness.ashr_expected_observation_count}`,
      `- Ashr reviewed public observations: ${evidenceReadiness.ashr_reviewed_public_observation_count || 0}/${evidenceReadiness.ashr_expected_observation_count}`,
      `- C3 safe to mark met: ${evidenceReadiness.ashr_safe_to_mark_c3_met ? "yes" : "no"}`,
      `- Real API evidence: ${evidenceReadiness.real_api_evidence_available ? "yes" : "no"} / records ${evidenceReadiness.real_api_total_records || 0}`,
      `- Real API quota gate: ${evidenceReadiness.real_api_create_request_blocked ? "blocked" : "not blocked"} / ${evidenceReadiness.real_api_quota_block_count || 0}`,
      `- Official API readonly: ${evidenceReadiness.official_api_readonly_available ? evidenceReadiness.official_api_readonly_status : "not attached"} / A2 context ${evidenceReadiness.official_api_readonly_ready_for_a2_evidence_context ? "ready" : "not ready"}`,
      `- Official API mutating: records ${evidenceReadiness.official_api_mutating_record_count || 0}, quota blocks ${evidenceReadiness.official_api_mutating_quota_block_count || 0}, raw payloads ${evidenceReadiness.official_api_mutating_raw_payloads_included ? "included" : "not included"}`,
      `- Official paid media: ${evidenceReadiness.official_api_paid_media_status || "unknown"} / safe claims ${evidenceReadiness.official_api_paid_media_safe_for_paid_media_claims ? "yes" : "no"} / estimated calls ${evidenceReadiness.official_api_paid_media_estimated_call_count || 0}`,
      `- Official SDK smoke: ${evidenceReadiness.official_sdk_smoke_read_only_reachable ? "read-only reachable" : "not confirmed"}`,
      `- Semantic judge offline-only: ${evidenceReadiness.semantic_offline_reference_only ? "yes" : "no"}`,
      `- Semantic live reviewed: ${evidenceReadiness.semantic_reviewed_live_observation_count || 0}/${evidenceReadiness.semantic_expected_reviewed_observation_count || 0}`,
      `- Semantic live merge: ${evidenceReadiness.semantic_live_merge_status || "unknown"}`,
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
      `- Case book regressions: ${regressionReadiness.current_regression_case_count}/${regressionReadiness.target_regression_case_count}`,
      `- Replay cases: ${regressionReadiness.current_replay_case_count}/${regressionReadiness.target_replay_case_count}`,
      `- Reviewed external evidence: ${regressionReadiness.reviewed_external_evidence_count}/${regressionReadiness.reviewed_evidence_target_count}`,
      `- Ashr grading missing: ${regressionReadiness.ashr_grading_missing_count}`,
      ""
    );
    if (regressionReadiness.gaps.length > 0) {
      lines.push(...regressionReadiness.gaps.map((gap) => `- Gap: ${gap}`), "");
    }
  }

  if (commercialReadiness.available) {
    lines.push(
      "## Commercial Readiness",
      "",
      `- Current gate: ${commercialReadiness.current_gate}`,
      `- Ready for commercial gate: ${commercialReadiness.ready_for_commercial_gate ? "yes" : "no"}`,
      `- Gate status counts: met ${commercialReadiness.gate_status_counts.met || 0}, partial ${commercialReadiness.gate_status_counts.partial || 0}, blocked ${commercialReadiness.gate_status_counts.blocked || 0}`,
      `- Partial gates: ${commercialReadiness.partial_gate_ids.join(", ") || "none"}`,
      `- Scenario count: ${commercialReadiness.scenario_count}`,
      `- Golden cases: ${commercialReadiness.golden_case_count}`,
      `- Failure classes: ${commercialReadiness.failure_class_count}`,
      `- Commercial real API records: ${commercialReadiness.real_api_record_count}/${commercialReadiness.real_api_total_records}`,
      `- Commercial create-request quota blocked: ${commercialReadiness.real_api_create_request_blocked ? "yes" : "no"}`,
      `- Commercial official SDK smoke: ${commercialReadiness.official_sdk_smoke_read_only_reachable ? "ok" : "not confirmed"} (${commercialReadiness.official_sdk_smoke_ok_call_count || 0} ok, ${commercialReadiness.official_sdk_smoke_error_call_count || 0} error)`,
      `- Ashr merge status: ${commercialReadiness.ashr_public_merge_status}`,
      `- Semantic live merge status: ${commercialReadiness.semantic_live_merge_status}`,
      `- Regression replay maturity: ${commercialReadiness.regression_replay_maturity}`,
      ""
    );
  }

  if (resultPersistence.available) {
    lines.push(
      "## A2 Result Persistence",
      "",
      `- Manifest: ${resultPersistence.manifest_id}`,
      `- Tenant: ${resultPersistence.tenant_id}`,
      `- Project/run: ${resultPersistence.project} / ${resultPersistence.run}`,
      `- Records: ${resultPersistence.record_count}`,
      `- Judge results: ${resultPersistence.judge_result_count}`,
      `- Failed judge results: ${resultPersistence.failed_judge_result_count}`,
      `- Safety blocking results: ${resultPersistence.safety_blocking_result_count}`,
      `- Release gate records: ${resultPersistence.release_gate_record_count}`,
      `- Scenario selection records: ${resultPersistence.scenario_selection_record_count}`,
      `- Release unblock checklist records: ${resultPersistence.release_unblock_checklist_record_count}`,
      `- A1 ingestion digest records: ${resultPersistence.a1_ingestion_digest_record_count}`,
      `- Public safe: ${resultPersistence.public_safe ? "yes" : "no"}`,
      `- Secrets recorded: ${resultPersistence.secrets_not_recorded ? "no" : "unknown"}`,
      `- Recommendation: ${resultPersistence.recommendation}`,
      ""
    );
  }

  if (releaseUnblockChecklist.available) {
    lines.push(
      "## A2 Release Unblock Checklist",
      "",
      `- Status: ${releaseUnblockChecklist.overall_status}`,
      `- Release decision: ${releaseUnblockChecklist.release_gate_decision}`,
      `- Risk score: ${releaseUnblockChecklist.release_gate_risk_score}`,
      `- Blocking gates: ${releaseUnblockChecklist.blocking_gate_ids.join(", ") || "none"}`,
      `- Required actions: ${releaseUnblockChecklist.required_action_count}`,
      `- Private evidence required: ${releaseUnblockChecklist.private_evidence_required_count}`,
      `- Required reviewers: ${releaseUnblockChecklist.required_reviewer_roles.join(", ") || "none"}`,
      `- Dashboard sections: ${releaseUnblockChecklist.dashboard_sections.join(", ") || "none"}`,
      `- Primary action: ${releaseUnblockChecklist.primary_action || "none"}`,
      `- Safety: public ${releaseUnblockChecklist.safety.public_safe ? "yes" : "no"}, no live calls ${releaseUnblockChecklist.safety.does_not_execute_live_calls ? "yes" : "no"}`,
      ""
    );
    for (const item of releaseUnblockChecklist.gate_items) {
      lines.push(`- ${item.gate}: ${item.status}, missing ${item.missing_count}, owner ${item.owner_role}`);
    }
    lines.push("");
  }

  if (a2CrossLaneSecurityContext.available) {
    lines.push(
      "## A2 Cross-Lane Security Context",
      "",
      `- Report: ${a2CrossLaneSecurityContext.report_id}`,
      `- A1 route scope ready: ${a2CrossLaneSecurityContext.a1_route_scope_ready_for_a2_security_context ? "yes" : "no"}`,
      `- A3 auth/RBAC ready: ${a2CrossLaneSecurityContext.a3_auth_rbac_ready_for_a2_security_context ? "yes" : "no"}`,
      `- Block hosted mutations without A1 auth: ${a2CrossLaneSecurityContext.should_block_hosted_mutations_without_a1_auth ? "yes" : "no"}`,
      `- Metadata-only audit events required: ${a2CrossLaneSecurityContext.should_require_metadata_only_audit_events ? "yes" : "no"}`,
      `- Raw actor identity forbidden: ${a2CrossLaneSecurityContext.should_keep_raw_actor_identity_forbidden ? "yes" : "no"}`,
      `- Security followups: ${a2CrossLaneSecurityContext.followup_count}`,
      `- Safety: public ${a2CrossLaneSecurityContext.safety.public_safe ? "yes" : "no"}, no live calls ${a2CrossLaneSecurityContext.safety.does_not_execute_live_calls ? "yes" : "no"}`,
      ""
    );
  }

  if (a2SqlStoreReport.available) {
    lines.push(
      "## A2 SQL Store Report",
      "",
      `- Report: ${a2SqlStoreReport.report_id}`,
      `- DB: ${a2SqlStoreReport.database_engine} / target ${a2SqlStoreReport.production_target}`,
      `- DDL: ${a2SqlStoreReport.ddl_version}`,
      `- Table rows: ${a2SqlStoreReport.table_count_total}`,
      `- Writes: ${a2SqlStoreReport.write_count_total}`,
      `- Calibration missing Ashr: ${a2SqlStoreReport.calibration_missing_ashr_count}`,
      `- Calibration disagreements: ${a2SqlStoreReport.calibration_disagreement_count}`,
      `- Case-level history join: ${a2SqlStoreReport.can_join_case_level_history ? "ready" : "not ready"}`,
      `- Safety: public ${a2SqlStoreReport.safety.public_safe ? "yes" : "no"}, external DB required ${a2SqlStoreReport.safety.does_not_require_external_database ? "no" : "unknown"}`,
      ""
    );
  }

  if (requestProvenance.available) {
    const latest = requestProvenance.latest_request;
    lines.push(
      "## Request Provenance",
      "",
      `- Requests observed: ${requestProvenance.total_requests}`,
      `- Latest request: ${latest.request_name}`,
      `- Status: ${latest.request_status}`,
      `- Duration: ${latest.actual_duration_s ?? "unknown"}s actual / ${latest.estimated_duration_s ?? "unknown"}s estimated`,
      `- Accepted inputs: ${latest.accepted_input_types.join(", ") || "none"}`,
      `- Generation outputs: ${latest.generation_outputs.join(", ") || "none"}`,
      `- Tools declared: ${latest.tool_count}`,
      ""
    );
  }

  if (usageQuota.available) {
    lines.push(
      "## Usage / Quota",
      "",
      `- Frontend modules: ${usageQuota.frontend_modules.join(", ") || "none"}`,
      `- Media channels: ${usageQuota.channels.join(", ") || "unknown"}`,
      `- Frontend source functions: ${usageQuota.frontend_source_functions.join(", ") || "unknown"}`,
      `- Direct API-key access: ${usageQuota.direct_api_accessible ? "yes" : "no"}`,
      `- OAuth-gated functions: ${usageQuota.oauth_only_functions.join(", ") || "none"}`,
      `- Guidance: ${usageQuota.guidance}`,
      ""
    );
  }

  if (billingUsage.available) {
    lines.push(
      "## Billing / Usage Summary",
      "",
      `- Plan: ${billingUsage.plan.plan_name} (${billingUsage.plan.billing_period})`,
      `- Billable units: ${billingUsage.billable_unit_count}`,
      `- Primary billable meter: ${billingUsage.billable_meter?.meter || "none"}`,
      `- Quota: ${billingUsage.quota.used_units}/${billingUsage.quota.included_units ?? "unknown"} ${billingUsage.quota.unit}`,
      `- Overage risk: ${billingUsage.overage_risk.status} (${billingUsage.overage_risk.risk_level})`,
      `- A1 evidence: runs ${billingUsage.evidence_counts.a1.runs}, cases ${billingUsage.evidence_counts.a1.cases}, trace events ${billingUsage.evidence_counts.a1.trace_events}`,
      `- A2 evidence: graded cases ${billingUsage.evidence_counts.a2.graded_cases}, judge results ${billingUsage.evidence_counts.a2.judge_results}, failed cases ${billingUsage.evidence_counts.a2.failed_cases}`,
      `- Billing mutations enabled: ${billingUsage.billing_mutations_enabled ? "yes" : "no"}`,
      ""
    );
  }

  if (billingMigrationReadiness.available) {
    lines.push(
      "## Billing Migration Readiness",
      "",
      `- Status: ${billingMigrationReadiness.status}`,
      `- Live customer billing ready: ${billingMigrationReadiness.ready_for_live_customer_billing ? "yes" : "no"}`,
      `- Consumed evidence: ${billingMigrationReadiness.consumed_evidence_count}`,
      `- Upstream commits: ${billingMigrationReadiness.upstream_commit_count}`,
      `- A1 DB tables: ${billingMigrationReadiness.db_contract.table_names.join(", ") || "none"}`,
      `- DB mutations required in A3: ${billingMigrationReadiness.db_contract.a3_db_mutation_required ? "yes" : "no"}`,
      `- Replay evidence: provider events ${billingMigrationReadiness.replay_evidence.provider_event_count}, ledger events ${billingMigrationReadiness.replay_evidence.ledger_event_count}, usage units ${billingMigrationReadiness.replay_evidence.usage_units}`,
      `- Live smoke executed by A3: ${billingMigrationReadiness.live_smoke.executed_by_a3 ? "yes" : "no"}`,
      `- Official API readonly: ${billingMigrationReadiness.official_api_readonly.status}, mutating steps ${billingMigrationReadiness.official_api_readonly.mutating_steps}`,
      `- Billing mutations enabled: ${billingMigrationReadiness.boundary.billing_mutations_enabled ? "yes" : "no"}`,
      `- Missing controls: ${billingMigrationReadiness.missing_controls.join(", ") || "none"}`,
      `- Customer value: ${billingMigrationReadiness.customer_value}`,
      `- Self-host value: ${billingMigrationReadiness.self_host_value}`,
      `- Audit value: ${billingMigrationReadiness.audit_value}`,
      ""
    );
    if (billingMigrationReadiness.blocked_for_live_customer_billing.length) {
      lines.push("### Billing Migration Blockers", "");
      for (const blocker of billingMigrationReadiness.blocked_for_live_customer_billing) {
        lines.push(`- ${blocker}`);
      }
      lines.push("");
    }
  }

  if (mediaReadiness.available) {
    lines.push(
      "## Media Readiness",
      "",
      `- Media cases: ${mediaReadiness.media_case_count}`,
      `- Evidence items: ${mediaReadiness.evidence_item_count}`,
      `- VM streams: ${mediaReadiness.vm_stream_count}`,
      `- Channels: ${mediaReadiness.channels.join(", ") || "unknown"}`,
      `- Signed URL keys: ${mediaReadiness.signed_url_key_count}`,
      `- Signed URL confirmed types: ${mediaReadiness.signed_url_confirmed_types.join(", ") || "none"}`,
      `- Live rendering allowed: ${mediaReadiness.live_rendering_allowed ? "yes" : "no"}`,
      `- Guidance: ${mediaReadiness.guidance}`,
      ""
    );
    for (const channel of mediaReadiness.channel_matrix) {
      lines.push(`- ${channel.channel}: ${channel.preview_policy} - ${channel.decision}`);
    }
    lines.push("");
  }

  if (cloudConsoleShell.available) {
    lines.push(
      "## Cloud Console Shell",
      "",
      `- Auth observed: ${cloudConsoleShell.auth_observed ? "yes" : "no"}`,
      `- Frontend session observed: ${cloudConsoleShell.frontend_session_observed ? "yes" : "no"}`,
      `- Observed pages: ${cloudConsoleShell.observed_pages.join(", ") || "none"}`,
      `- Real mutations enabled: ${cloudConsoleShell.real_mutations_enabled ? "yes" : "no"}`,
      `- Secret values allowed: ${cloudConsoleShell.secret_values_allowed ? "yes" : "no"}`,
      `- Recommendation: ${cloudConsoleShell.recommendation}`,
      ""
    );
    for (const section of cloudConsoleShell.sections) {
      lines.push(`- ${section.area}: ${section.status} - ${section.detail}`);
    }
    lines.push("", "### Cloud Action Guardrails", "");
    for (const action of cloudConsoleShell.actions) {
      lines.push(`- ${action.action}: ${action.mode} - ${action.reason}`);
    }
    lines.push("");
  }

  lines.push(
    "## Official Ashr Gap",
    "",
    `- Copied areas: ${officialGap.copied_count}`,
    `- Partial areas: ${officialGap.partial_count}`,
    `- Blocked areas: ${officialGap.blocked_count}`,
    `- Out-of-scope areas: ${officialGap.out_of_scope_count}`,
    `- Recommendation: ${officialGap.recommendation}`,
    ""
  );
  for (const page of officialGap.official_pages) {
    lines.push(`- ${page.page} (${page.path}): ${page.a3_status} - ${page.mvp_decision}`);
  }
  lines.push("");

  if (officialFrontendMirror.available) {
    lines.push(
      "## Official Frontend Mirror",
      "",
      `- Source archive: ${officialFrontendMirror.source_archive}`,
      `- Clean-room boundary: ${officialFrontendMirror.clean_room_boundary}`,
      `- Pages observed: ${officialFrontendMirror.page_count}`,
      `- Lab chunks observed: ${officialFrontendMirror.lab_chunk_count}`,
      `- API method groups observed: ${officialFrontendMirror.api_group_count}`,
      `- API methods observed: ${officialFrontendMirror.api_method_count}`,
      `- Labels confirmed: ${officialFrontendMirror.confirmed_labels.join(", ") || "none"}`,
      `- Official source committed: ${officialFrontendMirror.safety.official_source_committed ? "yes" : "no"}`,
      `- Secrets/tokens/cookies allowed: ${officialFrontendMirror.safety.secret_values_allowed || officialFrontendMirror.safety.raw_tokens_allowed || officialFrontendMirror.safety.raw_cookies_allowed ? "yes" : "no"}`,
      `- Recommendation: ${officialFrontendMirror.recommendation}`,
      ""
    );
    for (const page of officialFrontendMirror.pages) {
      lines.push(`- Page ${page.label} (${page.tab_id}): ${page.a3_status} - ${page.a3_decision}`);
    }
    lines.push("");
    for (const group of officialFrontendMirror.api_method_groups) {
      lines.push(`- API ${group.group}: ${group.a3_status}, ${group.method_count} method(s) - ${group.a3_decision}`);
    }
    lines.push("");
  }

  if (officialCodeCrawlParity.available) {
    lines.push(
      "## Official Code Crawl Parity",
      "",
      `- Source archive: ${officialCodeCrawlParity.source_archive}`,
      `- Clean-room boundary: ${officialCodeCrawlParity.clean_room_boundary}`,
      `- Lab JS chunks observed: ${officialCodeCrawlParity.lab_javascript_chunk_count}`,
      `- Parity targets: ${officialCodeCrawlParity.parity_target_count}`,
      `- Copy-now targets: ${officialCodeCrawlParity.copy_now_count}`,
      `- Partial targets: ${officialCodeCrawlParity.partial_count}`,
      `- Out-of-scope targets: ${officialCodeCrawlParity.out_of_scope_count}`,
      `- Official source committed: ${officialCodeCrawlParity.safety.official_source_committed ? "yes" : "no"}`,
      `- Raw source excerpts committed: ${officialCodeCrawlParity.safety.raw_source_excerpt_committed ? "yes" : "no"}`,
      `- Recommendation: ${officialCodeCrawlParity.recommendation}`,
      ""
    );
    lines.push("### Code Crawl Chunks", "");
    for (const chunk of officialCodeCrawlParity.chunks) {
      const signals = chunk.top_signals.map((item) => `${item.signal}:${item.count}`).join(", ") || "none";
      lines.push(`- ${chunk.chunk}: ${chunk.a3_status} / ${chunk.role} / signals ${signals} - ${chunk.a3_decision}`);
    }
    lines.push("", "### A3 Parity Targets", "");
    for (const target of officialCodeCrawlParity.parity_targets) {
      lines.push(`- ${target.target}: ${target.a3_status} / evidence ${target.official_evidence.join(", ") || "none"} / ${target.a3_dependency}`);
    }
    lines.push("");
  }

  if (officialParityRoadmap.available) {
    lines.push(
      "## Official Parity Roadmap",
      "",
      `- Official pages observed: ${officialParityRoadmap.official_pages_observed}`,
      `- Copied pages: ${officialParityRoadmap.copied_page_count}`,
      `- Partial pages: ${officialParityRoadmap.partial_page_count}`,
      `- Future pages: ${officialParityRoadmap.future_page_count}`,
      `- Out-of-scope pages: ${officialParityRoadmap.out_of_scope_page_count}`,
      `- Official blocked gaps: ${officialParityRoadmap.official_gap_blocked_count}`,
      `- Recommendation: ${officialParityRoadmap.recommendation}`,
      ""
    );
    lines.push("### Build Priorities", "");
    for (const item of officialParityRoadmap.priorities) {
      lines.push(`- ${item.area}: ${item.action} / ${item.confirmed ? "confirmed" : "unconfirmed"} - ${item.note}`);
    }
    lines.push("", "### Media Actions", "");
    for (const item of officialParityRoadmap.media_actions) {
      lines.push(`- ${item.area}: ${item.action} - ${item.note}`);
    }
    lines.push("", "### Cloud/Admin Boundaries", "");
    for (const boundary of officialParityRoadmap.cloud_admin_boundaries) {
      lines.push(`- ${boundary}`);
    }
    lines.push("", "### Next Build Order", "");
    for (const step of officialParityRoadmap.next_build_order) {
      lines.push(`- ${step}`);
    }
    lines.push("");
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

  return redactExport(`${lines.join("\n")}\n`, { surface: "markdown_report" }).value;
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
    .map((row, rowIndex) => row.map((value, columnIndex) => csvCell(value, `rows[${rowIndex}][${columnIndex}]`)).join(","))
    .join("\n");
}

function csvCell(value, path) {
  const redacted = sanitizeCsvCellValue(value, { path, surface: "csv_report" });
  return `"${String(redacted.value ?? "").replaceAll('"', '""')}"`;
}

function scanCsvExportSurface(cases = []) {
  const fields = [
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
  const findings = [];
  cases.forEach((item, rowIndex) => {
    const row = [
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
    ];
    row.forEach((value, columnIndex) => {
      const redacted = sanitizeCsvCellValue(value, {
        surface: "csv_report",
        path: `rows[${rowIndex}].${fields[columnIndex]}`
      });
      findings.push(...redacted.findings.map((finding) => ({
        ...finding,
        surface: "csv_report"
      })));
    });
  });
  const residualFindings = [];
  return {
    surface: "csv_report",
    value: "[csv cells]",
    findings,
    residual_findings: residualFindings,
    replacement_count: findings.length,
    replacements: findings.length,
    blocked: false,
    status: findings.length > 0 ? "cleaned" : "passed"
  };
}

export function summarizeExportAudienceGovernance(governance = {}) {
  const packetReadiness = Array.isArray(governance.packet_readiness) ? governance.packet_readiness : [];
  if (!governance.schema_version && !packetReadiness.length) {
    return {
      schema_version: "a3.export_audience_summary.v1",
      available: false,
      status: "missing",
      recommendation: "Attach export audience governance before claiming reviewer, executive, or customer-safe report posture."
    };
  }
  return {
    schema_version: "a3.export_audience_summary.v1",
    available: true,
    status: governance.status || "unknown",
    allowed_audiences: governance.allowed_audiences || [],
    blocked_audiences: governance.blocked_audiences || [],
    customer_external_blocked: governance.customer_external_blocked === true,
    packet_status: packetReadiness.map((item) => ({
      packet: item.packet,
      status: item.status,
      why: item.why
    })),
    required_controls: governance.required_controls || [],
    commercial_value: governance.commercial_value || []
  };
}

export function summarizeReviewWorkflowExport(reviewWorkflowFixture = {}) {
  const available = reviewWorkflowFixture?.schema_version === "a3.review_workflow_index.v1"
    || Boolean(reviewWorkflowFixture?.records || reviewWorkflowFixture?.record_count);
  if (!available) {
    return {
      schema_version: "a3.review_workflow_export.v1",
      available: false,
      status: "missing",
      recommendation: "Submit waiver and approval records through the A3 Review Workflow API before claiming durable sign-off storage."
    };
  }
  const records = Array.isArray(reviewWorkflowFixture.records) ? reviewWorkflowFixture.records : [];
  return {
    schema_version: "a3.review_workflow_export.v1",
    available: true,
    source: reviewWorkflowFixture.source || "unknown",
    record_count: reviewWorkflowFixture.record_count || records.length,
    waiver_count: reviewWorkflowFixture.waiver_count || records.filter((item) => item.record_type === "waiver").length,
    approval_count: reviewWorkflowFixture.approval_count || records.filter((item) => item.record_type === "approval").length,
    denial_count: reviewWorkflowFixture.denial_count || records.filter((item) => item.record_type === "denial").length,
    human_action_count: reviewWorkflowFixture.human_action_count || records.length,
    accepted_count: reviewWorkflowFixture.accepted_count || records.filter((item) => item.accepted === true).length,
    durable_storage_ready: reviewWorkflowFixture.durable_storage_ready === true,
    real_cloud_mutations_performed: reviewWorkflowFixture.real_cloud_mutations_performed === true,
    latest_records: records.slice(-5).map((item) => ({
      record_id: item.record_id,
      record_type: item.record_type,
      status: item.status,
      accepted: item.accepted === true,
      run_id: item.run_id,
      payload_hash: item.payload_hash,
      review_hash: item.review_hash,
      subject_decision: item.subject?.decision || null,
      signature_status: item.signature?.status || "unknown"
    })),
    recommendation: "Use durable Review Workflow records as the enterprise sign-off layer above the local reviewer board and PR gate."
  };
}

export function summarizeMultimodalReviewQueueExport(queue = {}) {
  const available = queue?.schema_version === "a3.multimodal_review_queue.v1"
    && queue.available === true;
  if (!available) {
    return {
      schema_version: "a3.multimodal_review_queue_export.v1",
      available: false,
      status: queue?.status || "missing",
      recommendation: "Ingest a public-safe, tenant-scoped multimodal comparison before exporting reviewer evidence."
    };
  }
  const summary = objectOr(queue.summary);
  const authority = objectOr(queue.authority_boundary);
  const items = Array.isArray(queue.items) ? queue.items : [];
  return {
    schema_version: "a3.multimodal_review_queue_export.v1",
    available: true,
    status: queue.status || "unknown",
    capability_state: queue.capability_state || "unknown",
    source_contract: queue.source_contract || "unknown",
    source_commit_alias: queue.source_commit_alias || null,
    tenant_scope: objectOr(queue.tenant_scope),
    provider_pair: objectOr(queue.provider_pair),
    summary: {
      comparison_count: numberOrDefault(summary.comparison_count, 0),
      repeat_comparison_count: numberOrDefault(summary.repeat_comparison_count, 0),
      aggregate_comparison_count: numberOrDefault(summary.aggregate_comparison_count, 0),
      agreement: numberOrDefault(summary.agreement, 0),
      semantic_disagreement: numberOrDefault(summary.semantic_disagreement, 0),
      unavailable: numberOrDefault(summary.unavailable, 0),
      internally_unstable: numberOrDefault(summary.internally_unstable, 0),
      review_required_count: numberOrDefault(summary.review_required_count, 0),
      queue_receipt_count: numberOrDefault(summary.queue_receipt_count, 0),
      assignment_active_count: numberOrDefault(summary.assignment_active_count, 0),
      assignment_expired_count: numberOrDefault(summary.assignment_expired_count, 0),
      assignment_unassigned_count: numberOrDefault(summary.assignment_unassigned_count, 0),
      assignment_event_count: numberOrDefault(summary.assignment_event_count, 0),
      assignment_invalid_event_count: numberOrDefault(summary.assignment_invalid_event_count, 0)
    },
    authority_boundary: {
      upstream_release_authority: authority.upstream_release_authority === true,
      queue_receipts_release_authority: authority.queue_receipts_release_authority === true,
      a3_recomputed_risk: authority.a3_recomputed_risk === true,
      a3_recomputed_release_decision: authority.a3_recomputed_release_decision === true,
      candidate_binding_verified: authority.candidate_binding_verified === true,
      can_change_release_decision: authority.can_change_release_decision === true,
      assignment_events_release_authority: authority.assignment_events_release_authority === true,
      assignment_events_change_a2_decision: authority.assignment_events_change_a2_decision === true
    },
    items: items.slice(0, 100).map((item) => {
      const operational = objectOr(item.operational_state);
      return ({
      queue_id: item.queue_id,
      case_id: item.case_id,
      artifact_hash: item.artifact_hash,
      comparison_hash: item.comparison_hash,
      comparison_state: item.comparison_state,
      comparison_scope: item.comparison_scope || "case",
      repeat: Number.isInteger(item.repeat) ? item.repeat : null,
      queue_state: item.queue_state,
      reviewer_role: item.reviewer_role,
      left_provider: item.left?.provider_id,
      left_model: item.left?.model_id,
      left_model_version: item.left?.model_version,
      left_observed_risk: item.left?.observed_risk,
      left_valid_risks: Array.isArray(item.left?.valid_risks)
        ? item.left.valid_risks.filter((value) => typeof value === "boolean")
        : [],
      right_provider: item.right?.provider_id,
      right_model: item.right?.model_id,
      right_model_version: item.right?.model_version,
      right_observed_risk: item.right?.observed_risk,
      right_valid_risks: Array.isArray(item.right?.valid_risks)
        ? item.right.valid_risks.filter((value) => typeof value === "boolean")
        : [],
      assignment_status: operational.status || "unassigned",
      assignment_version: numberOrDefault(operational.version, 0),
      assigned_reviewer_hash: operational.assigned_reviewer_hash || null,
      lease_expires_at: operational.lease_expires_at || null,
      assignment_last_action: operational.last_action || null,
      assignment_event_count: numberOrDefault(operational.event_count, 0),
      authoritative_disposition_recorded: false,
      release_authority: false
    });
    }),
    safety: {
      raw_model_payload_included: false,
      raw_media_included: false,
      signed_url_included: false,
      raw_reviewer_identity_included: false,
      release_decision_recomputed: false
    },
    recommendation: "Require an authoritative human-review resolution and same-candidate Decision Ledger before any release-state change."
  };
}

export function buildJsonReport(runFixture = {}, gradeFixture = {}, coverageFixture = {}, evidenceReadinessFixture = {}, requestFixture = {}, usageFixture = {}, usageApiProbe = {}, mediaSignedUrlFixture = {}, authFixture = {}, frontendFixture = {}, frontendMirrorFixture = {}, frontendCodeCrawlFixture = {}, productConsoleFixture = {}, saasAdminFixture = {}, a2ReadinessBundle = {}, artifactRegistryFixture = {}, reviewWorkflowFixture = {}, releaseEvidenceFixture = {}, githubPublishEvidenceFixture = {}, peerBranchCalibrationFixture = {}, billingMigrationReadinessFixture = {}, notificationControlPlaneFixture = {}, multimodalReviewQueueFixture = {}) {
  if (isArtifactRegistryFixture(a2ReadinessBundle) && !isArtifactRegistryFixture(artifactRegistryFixture)) {
    artifactRegistryFixture = a2ReadinessBundle;
    a2ReadinessBundle = {};
  }
  const productConsoleAsA2Bundle = isA2ReadinessBundle(productConsoleFixture);
  const effectiveA2ReadinessBundle = isA2ReadinessBundle(a2ReadinessBundle)
    ? a2ReadinessBundle
    : productConsoleAsA2Bundle
      ? productConsoleFixture
      : {};
  if (productConsoleAsA2Bundle) {
    productConsoleFixture = {};
  }
  const a2Readiness = normalizeA2ReadinessArgs(requestFixture, usageFixture, usageApiProbe, effectiveA2ReadinessBundle, mediaSignedUrlFixture);
  if (a2Readiness.legacyA2Args) {
    requestFixture = {};
    usageFixture = {};
    usageApiProbe = {};
  }
  const reportMediaSignedUrlFixture = a2Readiness.legacyA2Args ? {} : mediaSignedUrlFixture;
  const releaseGate = isA2ReleaseGateFixture(a2Readiness.releaseGateFixture)
    ? summarizeReleaseGate(a2Readiness.releaseGateFixture)
    : summarizeReleaseGate(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture);
  const rawReport = {
    schema_version: "a3.export_report.v1",
    summary: buildDashboardSummary(runFixture, gradeFixture),
    coverage: summarizeCoverage(coverageFixture),
    evidence_readiness: summarizeEvidenceReadiness(evidenceReadinessFixture),
    regression_readiness: summarizeRegressionReadiness(a2Readiness.caseBookFixture, a2Readiness.regressionReplayFixture),
    commercial_readiness: summarizeCommercialReadiness(a2Readiness.commercialReadinessFixture),
    a2_result_persistence: summarizeA2ResultPersistence(a2Readiness.resultPersistenceFixture),
    a2_release_unblock_checklist: summarizeA2ReleaseUnblockChecklist(a2Readiness.releaseUnblockChecklistFixture),
    a2_cross_lane_security_context: summarizeA2CrossLaneSecurityContext(a2Readiness.crossLaneSecurityContextFixture),
    a2_sql_store_report: summarizeA2SqlStoreReport(a2Readiness.sqlStoreReportFixture),
    request_provenance: summarizeRequestProvenance(requestFixture),
    usage_quota: summarizeUsageQuota(usageFixture, usageApiProbe),
    billing_usage_summary: summarizeBillingUsage(runFixture, gradeFixture, usageFixture, usageApiProbe),
    billing_migration_readiness: summarizeBillingMigrationReadiness(billingMigrationReadinessFixture),
    media_readiness: summarizeMediaReadiness(runFixture, gradeFixture, usageFixture, reportMediaSignedUrlFixture),
    cloud_console_shell: summarizeCloudConsoleShell(authFixture, frontendFixture, requestFixture, usageFixture, usageApiProbe),
    official_ashr_gap: summarizeOfficialAshrGap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe),
    official_frontend_mirror: summarizeOfficialFrontendMirror(frontendMirrorFixture),
    official_code_crawl_parity: summarizeOfficialCodeCrawlParity(frontendCodeCrawlFixture),
    official_parity_roadmap: summarizeOfficialParityRoadmap(runFixture, gradeFixture, coverageFixture, requestFixture, usageFixture, usageApiProbe, reportMediaSignedUrlFixture, frontendMirrorFixture),
    product_console: summarizeProductConsoleExport(productConsoleFixture),
    saas_admin_console: summarizeSaasAdminExport(saasAdminFixture),
    export_audience_governance: summarizeExportAudienceGovernance(saasAdminFixture.export_governance || {}),
    artifact_registry: summarizeArtifactRegistryExport(artifactRegistryFixture),
    review_workflow: summarizeReviewWorkflowExport(reviewWorkflowFixture),
    multimodal_review_queue: summarizeMultimodalReviewQueueExport(multimodalReviewQueueFixture),
    release_evidence_summary: summarizeReleaseEvidenceSummary(releaseEvidenceFixture),
    github_publish_evidence: summarizeGithubPublishEvidence(githubPublishEvidenceFixture),
    notification_control_plane: summarizeNotificationControlPlane(notificationControlPlaneFixture),
    peer_branch_calibration: summarizeA3PeerBranchCalibration(peerBranchCalibrationFixture),
    live_ops_control_plane: summarizeLiveOpsControlPlaneExport(notificationControlPlaneFixture.live_ops_control_plane || {}),
    release_gate: releaseGate,
    release_workflow: summarizeReleaseWorkflow(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture),
    release_war_room: summarizeReleaseWarRoom(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, requestFixture, usageFixture, usageApiProbe, frontendMirrorFixture),
    incident_replay_queue: summarizeIncidentReplayQueue(runFixture, gradeFixture, reportMediaSignedUrlFixture),
    reviewer_workflow_board: summarizeReviewerWorkflowBoard(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture),
    observability_replay_matrix: summarizeObservabilityReplayMatrix(runFixture, gradeFixture, reportMediaSignedUrlFixture, frontendCodeCrawlFixture),
    regression_factory: summarizeRegressionFactory(runFixture, gradeFixture, coverageFixture, reportMediaSignedUrlFixture, frontendCodeCrawlFixture),
    failure_clusters: clusterFailures(runFixture, gradeFixture),
    cases: normalizeCases(runFixture, gradeFixture).map((item) => ({
      run_id: item.run_id,
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      title: item.title,
      status: item.passed ? "passed" : "failed",
      score: item.score,
      score_source: item.metadata?.score_source || item.grade?.metadata?.score_source || "unknown",
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
  const redacted = redactExport(rawReport, { surface: "json_report" });
  return {
    ...redacted.value,
    export_redaction_firewall: summarizeExportRedactionFirewall(runFixture, gradeFixture, coverageFixture, mediaSignedUrlFixture, frontendCodeCrawlFixture, {
      jsonResult: redacted
    })
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

  return toolCalls.map((call, index) => ({
    id: call.id || call.tool_call_id || null,
    name: call.tool_name || call.name || call.tool || "unknown_tool",
    arguments: call.arguments || call.args || call.parameters || {},
    original_index: index,
    raw: call
  }));
}

function pairToolCalls(expected = [], actual = []) {
  const usedActual = new Set();
  const pairs = expected.map((expectedCall, expectedIndex) => {
    const match = selectBestActualMatch(expectedCall, expectedIndex, actual, usedActual);
    if (!match) {
      return {
        expectedCall,
        actualCall: null,
        expectedIndex,
        actualIndex: null,
        matchStrategy: "unmatched_expected"
      };
    }

    usedActual.add(match.actualIndex);
    return {
      expectedCall,
      actualCall: actual[match.actualIndex],
      expectedIndex,
      actualIndex: match.actualIndex,
      matchStrategy: match.matchStrategy
    };
  });

  for (let actualIndex = 0; actualIndex < actual.length; actualIndex += 1) {
    if (!usedActual.has(actualIndex)) {
      pairs.push({
        expectedCall: null,
        actualCall: actual[actualIndex],
        expectedIndex: null,
        actualIndex,
        matchStrategy: "unmatched_actual"
      });
    }
  }

  return pairs;
}

function selectBestActualMatch(expectedCall, expectedIndex, actual = [], usedActual = new Set()) {
  const candidates = actual.flatMap((actualCall, actualIndex) => {
    if (usedActual.has(actualIndex)) {
      return [];
    }
    const score = toolMatchScore(expectedCall, actualCall, expectedIndex, actualIndex);
    if (score <= 0) {
      return [];
    }
    return [{
      actualIndex,
      score,
      matchStrategy: toolMatchStrategy(expectedCall, actualCall, expectedIndex, actualIndex),
      distance: Math.abs(expectedIndex - actualIndex)
    }];
  });

  candidates.sort((left, right) => (
    right.score - left.score
    || left.distance - right.distance
    || left.actualIndex - right.actualIndex
  ));
  return candidates[0] || null;
}

function toolMatchScore(expectedCall, actualCall, expectedIndex, actualIndex) {
  const sameName = expectedCall.name === actualCall.name;
  const sameArguments = stableJson(expectedCall.arguments) === stableJson(actualCall.arguments);
  if (sameName && sameArguments) {
    return 100;
  }
  if (sameName) {
    return 80 - Math.min(buildArgumentDiffs(expectedCall.arguments, actualCall.arguments).length, 20);
  }
  if (expectedIndex === actualIndex) {
    return 40;
  }
  return 0;
}

function toolMatchStrategy(expectedCall, actualCall, expectedIndex, actualIndex) {
  const sameName = expectedCall.name === actualCall.name;
  const sameArguments = stableJson(expectedCall.arguments) === stableJson(actualCall.arguments);
  if (sameName && sameArguments && expectedIndex === actualIndex) {
    return "index_exact";
  }
  if (sameName && sameArguments) {
    return "semantic_exact_reordered";
  }
  if (sameName && expectedIndex === actualIndex) {
    return "index_name";
  }
  if (sameName) {
    return "semantic_name";
  }
  return "index";
}

function toolDiffStatus(expectedCall, actualCall, pair = {}) {
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
  if (Number.isInteger(pair.expectedIndex) && Number.isInteger(pair.actualIndex) && pair.expectedIndex !== pair.actualIndex) {
    return "wrong_tool_order";
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
  if (status === "wrong_tool_order") {
    return `Tool ${expectedCall.name} matched, but appeared in a different order.`;
  }
  return "No tool call expected or observed.";
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function flattenArgumentLeaves(value, prefix = "") {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return new Map();
    }
    return value.reduce((leaves, item, index) => (
      mergeMaps(leaves, flattenArgumentLeaves(item, `${prefix}[${index}]`))
    ), new Map());
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return new Map();
    }
    return entries.reduce((leaves, [key, item]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return mergeMaps(leaves, flattenArgumentLeaves(item, path));
    }, new Map());
  }

  return new Map([[prefix || "(root)", value]]);
}

function mergeMaps(left, right) {
  for (const [key, value] of right) {
    left.set(key, value);
  }
  return left;
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
