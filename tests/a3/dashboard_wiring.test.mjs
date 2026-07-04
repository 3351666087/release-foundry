import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadDashboardHtml() {
  return readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8");
}

test("A3 dashboard wires optional A2 coverage into JSON and Markdown exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /coverage: \{\}/);
  assert.match(html, /evidenceReadiness: \{\}/);
  assert.match(html, /caseBook: \{\}/);
  assert.match(html, /regressionReplay: \{\}/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_g3_coverage_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_evidence_readiness_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_case_book\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_regression_replay_report\.json"\)/);
  assert.match(html, /buildJsonReport\(\s*state\.runs,\s*state\.grades,\s*state\.coverage,\s*state\.evidenceReadiness,\s*state\.caseBook,\s*state\.regressionReplay\s*\)/);
  assert.match(html, /buildMarkdownReport\(\s*state\.runs,\s*state\.grades,\s*state\.coverage,\s*state\.evidenceReadiness,\s*state\.caseBook,\s*state\.regressionReplay\s*\)/);
  assert.match(html, /buildCsvReport\(state\.runs, state\.grades\)/);
});
