import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadDashboardHtml() {
  return readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8");
}

test("A3 dashboard wires optional A2 coverage into JSON and Markdown exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /coverage: \{\}/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_g3_coverage_report\.json"\)/);
  assert.match(html, /buildJsonReport\(state\.runs, state\.grades, state\.coverage\)/);
  assert.match(html, /buildMarkdownReport\(state\.runs, state\.grades, state\.coverage\)/);
  assert.match(html, /buildCsvReport\(state\.runs, state\.grades\)/);
});

