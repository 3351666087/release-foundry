import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport,
  clusterFailures,
  filterCases,
  getFilterOptions,
  normalizeCases
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

  const csv = buildCsvReport(runs, grades);
  assert.match(csv, /"case_id"/);
  assert.match(csv, /"sample-a2-s004-missing-tool"/);

  const json = buildJsonReport(runs, grades);
  assert.equal(json.schema_version, "a3.export_report.v1");
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
