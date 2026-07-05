import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport,
  buildToolCallDiffs,
  canonicalPrimaryFailureClass,
  clusterFailures,
  filterCases,
  getFilterOptions,
  normalizeCases,
  summarizeCoverage,
  summarizeEvidenceReadiness,
  summarizeRegressionReadiness
} from "../../services/report/report_builder.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 report builder summarizes run and grade fixtures", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const summary = buildDashboardSummary(runs, grades);
  assert.equal(summary.totalRuns, 1);
  assert.equal(summary.totalCases, 4);
  assert.equal(summary.passed, 2);
  assert.equal(summary.failed, 2);
  assert.equal(summary.passRate, 50);
  assert.equal(summary.traceCompleteness, 100);
});

test("A3 report builder clusters failures by primary failure class", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const clusters = clusterFailures(runs, grades);
  assert.deepEqual(clusters.map((cluster) => cluster.failureClass).sort(), [
    "missing_required_tool",
    "wrong_arguments"
  ]);
  assert.equal(clusters.reduce((sum, cluster) => sum + cluster.count, 0), 2);
});

test("A3 report builder canonicalizes local failure signals before clustering", () => {
  const runs = {
    runs: [{
      run_id: "run-local-signal",
      dataset_id: "a2-local-scenarios",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [
        {
          case_id: "case-bad-final",
          scenario_id: "A2-S013",
          title: "Bad final response",
          family: "direct_answer",
          status: "failed",
          score: 45
        },
        {
          case_id: "case-missing-primary",
          scenario_id: "A2-S999",
          title: "Missing primary",
          family: "direct_answer",
          status: "failed",
          score: 30
        }
      ]
    }]
  };
  const grades = {
    grade_results: [{
      case_id: "case-bad-final",
      passed: false,
      score: 45,
      primary_failure_class: "bad_final_response",
      judge_results: []
    }]
  };

  assert.equal(canonicalPrimaryFailureClass("output_schema_invalid", false), "wrong_intent");

  const cases = normalizeCases(runs, grades);
  assert.deepEqual(cases.map((item) => item.primary_failure_class), ["wrong_intent", "wrong_intent"]);
  assert.equal(cases[0].raw_primary_failure_class, "bad_final_response");

  const clusters = clusterFailures(runs, grades);
  assert.deepEqual(clusters.map((cluster) => [cluster.failureClass, cluster.count]), [["wrong_intent", 2]]);
});

test("A3 report builder normalizes nested A1 grade scores without A2 grade joins", () => {
  const runs = {
    runs: [{
      run_id: "run-a1-nested-grade",
      dataset_id: "a1-local",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [{
        case_id: "a1-nested-grade-case",
        scenario_id: "A2-S010",
        title: "A1 nested grade score",
        family: "retrieval_grounding",
        status: "failed",
        grade: {
          passed: false,
          score: 0.62,
          primary_failure_class: "wrong_arguments",
          judge_results: []
        }
      }]
    }]
  };

  const [item] = normalizeCases(runs, {});
  assert.equal(item.score, 62);
  assert.equal(item.primary_failure_class, "wrong_arguments");
  assert.equal(item.failure_summary, "Failure requires triage.");
});

test("A3 report builder uses the matching failed judge analysis for triage summaries", async () => {
  const run = await loadJson("../../fixtures/a2/runs/a2_s003_hallucinated_weather.json");
  const grade = await loadJson("../../fixtures/a2/results/a2_s003_hallucinated_weather_grade.json");
  const runs = {
    runs: [{
      run_id: "run-a2-s003-triage",
      dataset_id: "a2-g3-calibration",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [{
        case_id: run.case_id,
        scenario_id: run.scenario_id,
        title: "Optional Weather Check",
        family: "tool_execution",
        status: "failed",
        expected: run.expected,
        actual: run.run
      }]
    }]
  };
  const grades = { grade_results: [grade] };

  const [item] = normalizeCases(runs, grades);
  assert.equal(item.primary_failure_class, "hallucinated_tool_result");
  assert.equal(item.severity, "major");
  assert.match(item.failure_summary, /Forbidden or contradicted facts present/);
  assert.doesNotMatch(item.failure_summary, /Tool policy satisfied/);
});

test("A3 report builder exposes and applies dashboard filters", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const cases = normalizeCases(runs, grades);
  const options = getFilterOptions(cases);

  assert.ok(options.statuses.includes("passed"));
  assert.ok(options.families.includes("tool_execution"));
  assert.ok(options.failureClasses.includes("missing_required_tool"));
  assert.ok(options.runIds.includes("run_a3_g2_demo_001"));
  assert.ok(options.severities.includes("major"));
  assert.ok(options.scoreBands.includes("70-89"));

  const filtered = filterCases(cases, {
    status: "failed",
    severity: "major",
    scoreBand: "70-89"
  });
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].case_id, "sample-a2-s004-missing-tool");
});

test("A3 export builders produce markdown, CSV, and JSON report shapes", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const cases = normalizeCases(runs, grades);
  assert.equal(cases.length, 4);

  const markdown = buildMarkdownReport(runs, grades);
  assert.match(markdown, /A3 Dashboard Triage Report/);
  assert.match(markdown, /missing_required_tool/);
  assert.doesNotMatch(markdown, /## Coverage/);

  const csv = buildCsvReport(runs, grades);
  assert.match(csv, /"case_id"/);
  assert.match(csv, /"sample-a2-s004-missing-tool"/);
  assert.match(csv, /"media_types"/);

  const json = buildJsonReport(runs, grades);
  assert.equal(json.schema_version, "a3.export_report.v1");
  assert.equal(json.coverage.available, false);
  assert.equal(json.failure_clusters.length, 2);
  assert.ok(Array.isArray(json.cases[0].tool_call_diffs));
});

test("A3 report builder creates tool-call expected-vs-actual diffs", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const cases = normalizeCases(runs, grades);

  const missingToolCase = cases.find((item) => item.case_id === "sample-a2-s004-missing-tool");
  const missingDiffs = buildToolCallDiffs(missingToolCase);
  assert.equal(missingDiffs.length, 1);
  assert.equal(missingDiffs[0].status, "missing_required_tool");
  assert.equal(missingDiffs[0].expected.name, "web.search");

  const wrongArgumentCase = cases.find((item) => item.case_id === "sample-a2-s010-wrong-argument");
  const wrongArgumentDiffs = buildToolCallDiffs(wrongArgumentCase);
  assert.equal(wrongArgumentDiffs.length, 1);
  assert.equal(wrongArgumentDiffs[0].status, "wrong_arguments");
  assert.equal(wrongArgumentDiffs[0].expected.name, "file.read");
  assert.equal(wrongArgumentDiffs[0].actual.name, "file.read");
});

test("A3 report builder can consume A2 G3 aggregate grade fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const cases = normalizeCases(runs, grades);
  const clusters = clusterFailures(runs, grades);
  const judgeModes = new Set(cases.flatMap((item) => item.judge_modes || []));

  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s042-wrong-read-order"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-pass"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-wrong-order"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-unsupported-output"));
  assert.ok(cases.length >= 3);
  assert.ok(clusters.some((cluster) => cluster.failureClass === "wrong_arguments"));
  assert.equal(judgeModes.size, 5);
  assert.ok(judgeModes.has("g3_semantic_reference_judge"));
});

test("A3 report builder can join every A2 G3 aggregate grade by case id", async () => {
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const runs = {
    runs: [{
      run_id: "run-a2-g3-aggregate-join",
      dataset_id: grades.dataset_id,
      runner_id: "a1-local-runner",
      status: "failed",
      cases: grades.grade_results.map((grade) => ({
        case_id: grade.case_id,
        scenario_id: grade.scenario_id,
        title: grade.case_id,
        family: "a2_g3_calibration",
        status: grade.passed ? "passed" : "failed"
      }))
    }]
  };

  const cases = normalizeCases(runs, grades);
  assert.equal(cases.length, grades.grade_results.length);
  assert.equal(cases.filter((item) => item.judge_results.length === 5).length, grades.grade_results.length);
  assert.deepEqual(
    cases.map((item) => item.primary_failure_class).sort(),
    grades.grade_results.map((grade) => grade.primary_failure_class).sort()
  );
});

test("A3 report builder can summarize A2 G3 coverage fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");

  const summary = summarizeCoverage(coverage);
  assert.equal(summary.available, true);
  assert.equal(summary.meets_assignment_minimums, true);
  assert.equal(summary.scenario_count, 60);
  assert.equal(summary.scenario_dimension_counts.required_tool_use, 24);
  assert.equal(summary.scenario_dimension_counts.fixture_grounding, 30);
  assert.equal(summary.scenario_dimension_counts.ordered_tool_sequence, 5);
  assert.equal(summary.scenario_dimension_counts.tool_output_grounding, 1);
  assert.deepEqual(summary.scenario_dimension_scenarios.tool_output_grounding, ["A2-S031"]);
  assert.equal(summary.capability_axis_counts.tool_choice_and_policy, 60);
  assert.equal(summary.capability_axis_counts.multi_step_workflow, 15);
  assert.equal(summary.capability_axis_counts.trace_contract, 32);
  assert.equal(summary.capability_axis_counts.media_and_multimodal, 2);
  assert.equal(summary.capability_axis_checks.media_and_multimodal, true);
  assert.equal(Object.keys(summary.capability_axis_exemplars).length, 10);
  assert.ok(summary.capability_axis_exemplars.media_and_multimodal.some((item) => (
    item.scenario_id === "A2-S031"
  )));
  assert.match(
    summary.capability_axis_exemplars.media_and_multimodal[0].why_it_matters,
    /Evidence signals:/
  );
  assert.deepEqual(summary.missing_capability_axes, []);
  assert.equal(summary.scenario_quality_warning_count, 0);
  assert.equal(summary.difficulty_counts.D4, 2);
  assert.equal(summary.multi_turn_scenario_count, 4);
  assert.equal(summary.ordered_tool_pairs["web.search -> web.open"], 3);
  assert.equal(summary.ordered_tool_pairs["file.read -> file.read"], 1);
  assert.equal(summary.ordered_tool_pairs["media.fetch -> image.view"], 1);
  assert.equal(summary.ordered_tool_pairs["image.view -> media.classify"], 1);
  assert.equal(summary.rubric_class_count, 5);
  assert.equal(summary.judge_mode_count, 5);
  assert.equal(summary.executable_run_case_count, 32);
  assert.equal(summary.executable_media_case_count, 4);
  assert.equal(summary.executable_tool_output_grounding_case_count, 4);
  assert.equal(summary.executable_media_expected_class_counts.wrong_arguments, 1);
  assert.equal(summary.primary_failure_class_count, 12);
  assert.equal(summary.golden_failure_classes_missing.length, 0);
  assert.equal(summary.executable_failure_classes_missing.length, 0);
  assert.equal(summary.coverage_warning_count, 0);
  assert.equal(Object.keys(summary.thin_golden_failure_classes).length, 0);
  assert.equal(Object.keys(summary.thin_executable_failure_classes).length, 0);
  assert.ok(summary.golden_failure_class_cases.wrong_arguments.some((item) => (
    item.case_id === "GC-A2-S033-fail-wrong-calculator-arguments"
  )));
  assert.ok(summary.executable_failure_class_cases.missing_required_tool.some((item) => (
    item.case_id === "sample-a2-s029-missing-required-search"
  )));
  assert.ok(summary.executable_failure_class_cases.hallucinated_tool_result.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-unsupported-output"
  )));
  assert.ok(summary.executable_failure_class_cases.wrong_tool_order.some((item) => (
    item.case_id === "sample-a2-s042-wrong-read-order"
  )));
  assert.ok(summary.executable_failure_class_cases.wrong_tool_order.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-wrong-order"
  )));
  assert.ok(summary.executable_media_case_refs.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-wrong-classifier-args"
  )));

  const json = buildJsonReport(runs, grades, coverage);
  assert.equal(json.coverage.executable_failure_class_count, 12);
  assert.equal(json.coverage.executable_media_case_count, 4);
  assert.equal(json.coverage.coverage_warning_count, 0);
  assert.equal(json.coverage.scenario_quality_warnings.length, 0);
  assert.equal(json.coverage.missing_capability_axes.length, 0);
  assert.equal(json.coverage.capability_axis_exemplars.media_and_multimodal.length, 2);
  assert.equal(json.coverage.golden_failure_class_cases.wrong_arguments.length, 2);

  const markdown = buildMarkdownReport(runs, grades, coverage);
  assert.match(markdown, /## Coverage/);
  assert.match(markdown, /Assignment minimums met: yes/);
  assert.match(markdown, /Scenarios: 60/);
  assert.match(markdown, /Scenario dimensions met: 16\/16/);
  assert.match(markdown, /Capability axes met: 10\/10/);
  assert.match(markdown, /### Capability Axis Exemplars/);
  assert.match(markdown, /media_and_multimodal: A2-S031/);
  assert.match(markdown, /Scenario quality warnings: 0/);
  assert.doesNotMatch(markdown, /### Scenario Quality Warnings/);
  assert.match(markdown, /Coverage warnings: 0/);
  assert.match(markdown, /Media executable cases: 4/);
  assert.match(markdown, /Tool-output grounding executable cases: 4/);
  assert.match(markdown, /### Failure Class Evidence/);
  assert.match(markdown, /wrong_arguments: golden GC-A2-S010-fail\/A2-S010/);
  assert.match(markdown, /missing_required_tool: golden GC-A2-S004-fail\/A2-S004/);
  assert.match(markdown, /sample-a2-s029-missing-required-search\/A2-S029/);
});

test("A3 report builder can summarize A2 evidence readiness fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");

  const summary = summarizeEvidenceReadiness(readiness);
  assert.equal(summary.available, true);
  assert.equal(summary.schema_version, "a2.evidence_readiness.v1");
  assert.equal(summary.status, "awaiting_private_evidence");
  assert.equal(summary.ready_for_external_collection, true);
  assert.equal(summary.calibration_case_count, 6);
  assert.equal(summary.ashr_current_missing, 6);
  assert.equal(summary.ashr_expected_observation_count, 6);
  assert.equal(summary.ashr_case_map_covers_all_calibration_cases, true);
  assert.equal(summary.ashr_public_merge_status, "not_merged");
  assert.equal(summary.ashr_public_matrix_merged, false);
  assert.equal(summary.ashr_safe_to_mark_c3_met, false);
  assert.equal(summary.ashr_merged_public_observation_count, 0);
  assert.equal(summary.ashr_reviewed_public_observation_count, 0);
  assert.equal(summary.ashr_missing_public_observation_count, 6);
  assert.equal(summary.ashr_missing_reviewed_observation_count, 6);
  assert.match(summary.ashr_public_merge_blocking_reason, /before C3 is met/);
  assert.equal(summary.semantic_offline_reference_only, true);
  assert.equal(summary.semantic_expected_reviewed_observation_count, 6);
  assert.equal(summary.semantic_reviewed_live_observation_count, 0);
  assert.equal(summary.semantic_missing_reviewed_live_observation_count, 6);
  assert.deepEqual(summary.semantic_reviewed_live_sdk_languages, []);
  assert.equal(summary.semantic_risk_assessment_status, "offline_reference_risk_register");
  assert.equal(summary.semantic_false_positive_tracking_ready, true);
  assert.equal(summary.semantic_false_positive_candidate_count, 0);
  assert.equal(summary.semantic_false_negative_candidate_count, 0);
  assert.equal(summary.semantic_failure_class_drift_candidate_count, 1);
  assert.equal(summary.semantic_score_delta_review_count, 4);
  assert.equal(summary.semantic_risk_case_count, 4);
  assert.equal(summary.semantic_live_merge_status, "offline_reference_only");
  assert.equal(summary.semantic_audited_live_evidence_merged, false);
  assert.equal(summary.semantic_safe_to_mark_c4_met, false);
  assert.equal(summary.semantic_live_reviewed_observation_count, 0);
  assert.equal(summary.semantic_missing_audited_observation_count, 6);
  assert.match(summary.semantic_live_merge_blocking_reason, /before C4 is met/);
  assert.ok(summary.semantic_required_fields.includes("prompt_hash"));
  assert.deepEqual(summary.covered_sdk_languages, ["python", "typescript"]);
  assert.ok(summary.batch_plan_refs.includes("semantic_llm_judge_audit"));
  assert.ok(summary.never_commit.includes("raw prompts"));

  const json = buildJsonReport(runs, grades, coverage, readiness);
  assert.equal(json.evidence_readiness.available, true);
  assert.equal(json.evidence_readiness.ashr_current_missing, 6);
  assert.equal(json.evidence_readiness.ashr_public_merge_status, "not_merged");
  assert.equal(json.evidence_readiness.ashr_safe_to_mark_c3_met, false);
  assert.equal(json.evidence_readiness.ashr_merged_public_observation_count, 0);
  assert.equal(json.evidence_readiness.ashr_reviewed_public_observation_count, 0);
  assert.equal(json.evidence_readiness.semantic_risk_assessment_status, "offline_reference_risk_register");
  assert.equal(json.evidence_readiness.semantic_false_positive_candidate_count, 0);
  assert.equal(json.evidence_readiness.semantic_failure_class_drift_candidate_count, 1);
  assert.equal(json.evidence_readiness.semantic_score_delta_review_count, 4);
  assert.equal(json.evidence_readiness.semantic_live_merge_status, "offline_reference_only");
  assert.equal(json.evidence_readiness.semantic_safe_to_mark_c4_met, false);
  assert.equal(json.evidence_readiness.semantic_offline_reference_only, true);
  assert.equal(json.evidence_readiness.semantic_reviewed_live_observation_count, 0);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness);
  assert.match(markdown, /## Evidence Readiness/);
  assert.match(markdown, /Status: awaiting_private_evidence/);
  assert.match(markdown, /Ashr grading missing: 6\/6/);
  assert.match(markdown, /Ashr public merge: not_merged/);
  assert.match(markdown, /Ashr safely merged observations: 0\/6/);
  assert.match(markdown, /Ashr reviewed public observations: 0\/6/);
  assert.match(markdown, /C3 safe to mark met: no/);
  assert.match(markdown, /Semantic reviewed live observations: 0\/6/);
  assert.match(markdown, /Semantic risk register: offline_reference_risk_register/);
  assert.match(markdown, /Semantic false-positive candidates: 0/);
  assert.match(markdown, /Semantic failure-class drift candidates: 1/);
  assert.match(markdown, /Semantic score-delta reviews: 4/);
  assert.match(markdown, /Semantic live merge: offline_reference_only/);
  assert.match(markdown, /C4 safe to mark met: no/);
  assert.match(markdown, /SDK languages covered: python, typescript/);
});

test("A3 report builder can summarize A2 C5 regression readiness fixtures", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");

  const summary = summarizeRegressionReadiness(caseBook, regressionReplay);
  assert.equal(summary.available, true);
  assert.equal(summary.case_book_schema_version, "a2.case_book.v1");
  assert.equal(summary.replay_schema_version, "a2.regression_replay.v1");
  assert.equal(summary.regression_case_count, 1);
  assert.equal(summary.replay_case_count, 1);
  assert.equal(summary.replay_ready, true);
  assert.equal(summary.maturity_status, "seed");
  assert.equal(summary.case_book_ready, false);
  assert.equal(summary.replay_gate_ready, false);
  assert.equal(summary.target_regression_case_count, 3);
  assert.equal(summary.current_regression_case_count, 1);
  assert.equal(summary.target_replay_case_count, 3);
  assert.equal(summary.current_replay_case_count, 1);
  assert.equal(summary.failed_replay_case_count, 0);
  assert.equal(summary.reviewed_evidence_target_count, 3);
  assert.equal(summary.reviewed_external_evidence_count, 0);
  assert.equal(summary.review_evidence_ready, false);
  assert.equal(summary.case_book_maturity_ready, false);
  assert.equal(summary.local_llm_mismatch_count, 1);
  assert.equal(summary.ashr_grading_missing_count, 6);
  assert.ok(summary.gaps.some((gap) => gap.includes("Promote 2 more")));
  assert.ok(summary.gaps.some((gap) => gap.includes("reviewed Ashr grading or audited semantic evidence")));
  assert.ok(summary.gaps.some((gap) => gap.includes("Replay 2 more")));

  const json = buildJsonReport(runs, grades, coverage, readiness, caseBook, regressionReplay);
  assert.equal(json.regression_readiness.available, true);
  assert.equal(json.regression_readiness.maturity_status, "seed");
  assert.equal(json.regression_readiness.target_replay_case_count, 3);
  assert.equal(json.regression_readiness.reviewed_external_evidence_count, 0);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, caseBook, regressionReplay);
  assert.match(markdown, /## Regression Readiness/);
  assert.match(markdown, /Maturity status: seed/);
  assert.match(markdown, /Case book regressions: 1\/3/);
  assert.match(markdown, /Replay cases: 1\/3/);
  assert.match(markdown, /Reviewed external evidence: 0\/3/);
  assert.match(markdown, /Ashr grading missing: 6/);
});
