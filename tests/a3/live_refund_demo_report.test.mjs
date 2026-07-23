import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { exportDemoReports } from "../../services/report/a3_demo_report_cli.mjs";


test("live refund demo exports A3 reports from A1 and A2 fixtures", async () => {
  const outputDir = await mkdtemp(join(tmpdir(), "ashr-live-refund-report-"));
  const receipt = await exportDemoReports({
    runs: new URL("../../fixtures/a3/demo/refund_demo_run_results.json", import.meta.url),
    grades: new URL("../../fixtures/a3/demo/refund_demo_grade_results.json", import.meta.url),
    outputDir
  });

  assert.equal(receipt.schema_version, "a3.live_refund_report_export.v1");
  assert.equal(receipt.summary.totalCases, 1);
  assert.equal(receipt.exports.length, 3);
  assert.equal(receipt.redaction_boundary.secret_values_allowed, false);
  assert.match(await readFile(join(outputDir, "a3_report.md"), "utf8"), /missing_required_tool/);
  assert.match(await readFile(join(outputDir, "a3_report.csv"), "utf8"), /case-refund-demo-001/);
});
