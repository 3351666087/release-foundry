import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const DOC_PATH = new URL("../../docs/a3/p3_api_calibration_import_error_shapes_2026_07_07.md", import.meta.url);

test("P3 API calibration import error evidence keeps required guarded sections", async () => {
  const doc = await readFile(DOC_PATH, "utf8");
  const requiredSections = [
    "Purpose",
    "Request Type",
    "Response Fields",
    "Error Fields",
    "Quota/Cost",
    "Private Evidence Path",
    "Redacted Summary",
    "Next API Calibration"
  ];

  for (const section of requiredSections) {
    assert.match(doc, new RegExp(`^## ${escapeRegExp(section)}$`, "m"), `missing section: ${section}`);
  }

  assert.match(doc, /a3\.a1_run_result_ingest\.v1/);
  assert.match(doc, /a3\.a2_grade_result_ingest\.v1/);
  assert.match(doc, /a3\.api_error\.v1/);
  assert.match(doc, /validation_error/);
  assert.match(doc, /Official ReleaseFoundry calibration mapping/);
  assert.match(doc, /Real ReleaseFoundry API calls \| 0/);
  assert.match(doc, /No private evidence file was read/);
  assert.match(doc, /fixtures\/a3\/p3\/\*\.redacted\.json/);

  assert.doesNotMatch(doc, /Bearer\s+[A-Za-z0-9._-]+/);
  assert.doesNotMatch(doc, /sk-[A-Za-z0-9]/);
  assert.doesNotMatch(doc, /github_pat_[A-Za-z0-9_]+/);
  assert.doesNotMatch(doc, /gho_[A-Za-z0-9_]+/);
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
