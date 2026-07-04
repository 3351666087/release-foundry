import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport,
  canonicalPrimaryFailureClass,
  clusterFailures,
  filterCases,
  getFilterOptions,
  normalizeCases,
  summarizeCoverage
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

  const json = buildJsonReport(runs, grades);
  assert.equal(json.schema_version, "a3.export_report.v1");
  assert.equal(json.coverage.available, false);
  assert.equal(json.failure_clusters.length, 2);
});

test("A3 report builder can consume A2 G3 aggregate grade fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const cases = normalizeCases(runs, grades);
  const clusters = clusterFailures(runs, grades);
  const judgeModes = new Set(cases.flatMap((item) => item.judge_modes || []));

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
  assert.equal(summary.rubric_class_count, 5);
  assert.equal(summary.judge_mode_count, 5);
  assert.equal(summary.primary_failure_class_count, 12);
  assert.equal(summary.golden_failure_classes_missing.length, 0);
  assert.equal(summary.executable_failure_classes_missing.length, 0);
  assert.equal(summary.coverage_warning_count, 1);
  assert.equal(Object.keys(summary.thin_golden_failure_classes).length, 0);
  assert.equal(Object.keys(summary.thin_executable_failure_classes).length, 9);
  assert.equal(summary.thin_executable_failure_classes.hallucinated_tool_result, undefined);
  assert.equal(summary.thin_executable_failure_classes.wrong_arguments, undefined);
  assert.equal(summary.thin_executable_failure_classes.poor_failure_recovery, undefined);

  const json = buildJsonReport(runs, grades, coverage);
  assert.equal(json.coverage.executable_failure_class_count, 12);
  assert.equal(json.coverage.coverage_warning_count, 1);

  const markdown = buildMarkdownReport(runs, grades, coverage);
  assert.match(markdown, /## Coverage/);
  assert.match(markdown, /Assignment minimums met: yes/);
  assert.match(markdown, /Scenarios: 60/);
  assert.match(markdown, /Coverage warnings: 1/);
});
