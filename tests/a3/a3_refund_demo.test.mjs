import assert from "node:assert/strict";
import { test } from "node:test";

import { loadA3SourceSnapshot } from "../../services/report/a3_store.mjs";
import { buildToolCallDiffs, normalizeCases } from "../../services/report/report_builder.mjs";

test("refund teaching demo preserves the A1 trace and A2 grade contract", async () => {
  const snapshot = await loadA3SourceSnapshot("refund-demo");
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);

  assert.equal(snapshot.source, "refund-demo");
  assert.equal(snapshot.summary.totalRuns, 1);
  assert.equal(snapshot.summary.totalCases, 1);
  assert.equal(snapshot.summary.failed, 1);
  assert.equal(snapshot.summary.avgScore, 42);
  assert.equal(snapshot.summary.traceCompleteness, 100);

  assert.equal(cases.length, 1);
  const [item] = cases;
  assert.equal(item.case_id, "case-refund-demo-001");
  assert.equal(item.passed, false);
  assert.equal(item.score, 42);
  assert.equal(item.primary_failure_class, "missing_required_tool");
  assert.equal(item.expected.tool_calls[0].name, "refund_order");
  assert.equal(item.actual.tool_calls.length, 0);
  assert.equal(item.trace_events[1].event_id, "trace-refund-tool-missing");
  assert.equal(item.judge_results[0].judge_mode, "a2_contract_judge");

  const diffs = buildToolCallDiffs(item);
  assert.equal(diffs.length, 1);
  assert.equal(diffs[0].status, "missing_required_tool");
  assert.equal(diffs[0].expected.name, "refund_order");
  assert.equal(diffs[0].trace_event_links[0].event_id, "trace-refund-tool-missing");
  assert.equal(diffs[0].judge_evidence[0].score, 42);
});
