import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3FixturesFromA2Paths } from "../../services/report/a3_fixture_builder.mjs";
import { buildToolCallDiffs, normalizeCases } from "../../services/report/report_builder.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 fixture builder regenerates current mock fixtures from merged A2 outputs", async () => {
  const generated = await buildA3FixturesFromA2Paths();
  const currentRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const currentGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  assert.deepEqual(currentRuns, generated.runFixture);
  assert.deepEqual(currentGrades, generated.gradeFixture);
  assert.equal(currentRuns.runs[0].cases.length, 32);
  assert.equal(currentGrades.grade_results.length, 32);
  assert.equal(currentRuns.runs[0].metadata.source, "merged_a2_outputs");
});

test("A3 fixture builder preserves A2 scenario labels, judge evidence, and tool diffs", async () => {
  const { runFixture, gradeFixture } = await buildA3FixturesFromA2Paths();
  const cases = normalizeCases(runFixture, gradeFixture);

  const missingToolCase = cases.find((item) => item.case_id === "sample-a2-s004-missing-tool");
  assert.equal(missingToolCase.title, "Required Current Price");
  assert.equal(missingToolCase.family, "tool_execution");
  assert.equal(missingToolCase.judge_results.length, 5);
  assert.deepEqual(buildToolCallDiffs(missingToolCase).map((diff) => diff.status), [
    "missing_required_tool"
  ]);

  const wrongArgumentsCase = cases.find((item) => item.case_id === "sample-a2-s010-wrong-arguments");
  const [argumentDiff] = buildToolCallDiffs(wrongArgumentsCase);
  assert.equal(argumentDiff.status, "wrong_arguments");
  assert.deepEqual(argumentDiff.argument_diffs, [{
    path: "path",
    status: "changed_argument",
    expected: "fixtures/a2/contracts/vendor-alpha.txt",
    actual: "fixtures/a2/contracts/vendor-alfa.txt"
  }]);
  assert.deepEqual(argumentDiff.judge_evidence[0].evidence.trace_event_ids, [
    "sample-a2-s010-wrong-arguments:trace:1"
  ]);

  const wrongOrderCase = cases.find((item) => item.case_id === "sample-a2-s009-wrong-order");
  assert.deepEqual(buildToolCallDiffs(wrongOrderCase).map((diff) => diff.status), [
    "wrong_tool_order",
    "wrong_tool_order"
  ]);
});
