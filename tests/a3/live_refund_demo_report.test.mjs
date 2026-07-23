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

test("live refund case page presents a Chinese five-step evidence story", async () => {
  const casePage = await readFile(new URL("../../apps/webapp/components/pages/case-page.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../apps/webapp/app/globals.css", import.meta.url), "utf8");

  assert.match(casePage, /model\.source === "live-refund-demo"/);
  assert.match(casePage, /真实运行证据 \/ 不是预先写好的截图/);
  assert.match(casePage, /大模型作出决定/);
  assert.match(casePage, /工具真实执行/);
  assert.match(casePage, /收到沙盒回执/);
  assert.match(casePage, /评测系统验收/);
  assert.match(casePage, /真实的是模型推理、工具调用和评测记录；模拟的是订单和退款资金/);
  assert.match(casePage, /它到底是怎么运行起来的/);
  assert.match(casePage, /ProviderNeutralModelAdapter\.for_ollama/);
  assert.match(casePage, /self\.adapter\.complete/);
  assert.match(casePage, /run_agent_batch/);
  assert.match(casePage, /grade_run/);
  assert.match(casePage, /POST http:\/\/ollama:11434\/api\/chat/);
  assert.match(casePage, /不伪造也不展示模型不可验证的隐藏思维链/);
  assert.match(styles, /\.live-proof-flow/);
  assert.match(styles, /\.live-code-grid/);
  assert.match(styles, /\.live-runtime-receipt/);
  assert.match(styles, /@media \(max-width: 820px\)/);
});
