import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildDashboardSummary, clusterFailures, normalizeCases } from "../../services/report/report_builder.mjs";
import { extractAshrRuns, mapAshrSampleToA3Fixtures } from "../../services/report/p3_ashr_mapper.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

const ashrRunSample = {
  runs: [
    {
      id: 101,
      created_at: "2026-07-04T08:00:03Z",
      dataset: 202,
      runner: 303,
      result: {
        status: "completed",
        started_at: "2026-07-04T08:00:00Z",
        completed_at: "2026-07-04T08:00:02Z",
        aggregate_metrics: {
          total_tests: 2,
          tests_passed: 1,
          tests_failed: 1,
          average_similarity_score: 0.7,
          total_tool_call_divergence: 1,
          total_response_divergence: 1
        },
        tests: [
          {
            test_id: "refund-happy-path",
            status: "completed",
            started_at: "2026-07-04T08:00:00Z",
            completed_at: "2026-07-04T08:00:01Z",
            action_results: [
              {
                actor: "user",
                action_type: "text",
                action_index: 0,
                text: "I want to return my unopened headphones.",
                input_provided: true
              },
              {
                actor: "agent",
                action_type: "text",
                action_index: 1,
                expected_response: { text: "Explain the return window." },
                actual_response: { text: "You can return unopened headphones within 30 days." },
                match_status: "exact",
                semantic_similarity: 0.96
              }
            ]
          },
          {
            test_id: "refund-wrong-tool",
            status: "completed",
            started_at: "2026-07-04T08:00:01Z",
            completed_at: "2026-07-04T08:00:02Z",
            action_results: [
              {
                actor: "user",
                action_type: "text",
                action_index: 0,
                text: "Refund order R-100.",
                input_provided: true
              },
              {
                actor: "agent",
                action_type: "tool_call",
                action_index: 1,
                tool_calls: [
                  {
                    expected: {
                      tool_name: "lookup_refund_policy",
                      arguments: { order_id: "R-100" }
                    },
                    actual: {
                      tool_name: "lookup_order",
                      arguments: { order_id: "R-999" }
                    },
                    match_status: "mismatch",
                    argument_comparison: {
                      status: "mismatch",
                      exact_match: false
                    },
                    divergence_notes: "Wrong tool and wrong order id."
                  }
                ]
              },
              {
                actor: "agent",
                action_type: "text",
                action_index: 2,
                expected_response: { text: "Ground answer in refund policy." },
                actual_response: { text: "Refund already issued." },
                match_status: "divergent",
                semantic_similarity: 0.42,
                divergence_notes: "Claims a refund without policy lookup."
              }
            ]
          }
        ]
      }
    }
  ]
};

test("P3 mapper extracts Ashr runs from list_runs style responses", () => {
  assert.equal(extractAshrRuns(ashrRunSample).length, 1);
  assert.equal(extractAshrRuns(ashrRunSample.runs[0]).length, 1);
  assert.equal(extractAshrRuns({ calls: { list_runs: { sample: ashrRunSample } } }).length, 1);
});

test("P3 mapper creates A3 run and grade fixtures", () => {
  const { runFixture, gradeFixture } = mapAshrSampleToA3Fixtures(ashrRunSample);

  assert.equal(runFixture.schema_version, "a3.dashboard_fixture.v1");
  assert.equal(gradeFixture.schema_version, "a3.grade_fixture.v1");
  assert.equal(runFixture.runs[0].run_id, "101");
  assert.equal(runFixture.runs[0].total_cases, 2);
  assert.equal(runFixture.runs[0].passed, 1);
  assert.equal(runFixture.runs[0].failed, 1);
  assert.equal(runFixture.runs[0].trace_completeness, 1);
  assert.equal(gradeFixture.grade_results.length, 2);

  const cases = normalizeCases(runFixture, gradeFixture);
  assert.equal(cases[0].case_id, "refund-happy-path");
  assert.equal(cases[0].passed, true);
  assert.equal(cases[0].score, 96);
  assert.equal(cases[1].passed, false);
  assert.equal(cases[1].primary_failure_class, "wrong_arguments");
  assert.equal(cases[1].expected.tool_calls[0].tool_name, "lookup_refund_policy");
  assert.equal(cases[1].actual.tool_calls[0].tool_name, "lookup_order");
  assert.equal(cases[1].trace_events.some((event) => event.event_type === "tool.tool_call"), true);
});

test("P3 mapper output works with existing A3 report builder", () => {
  const { runFixture, gradeFixture } = mapAshrSampleToA3Fixtures(ashrRunSample);

  const summary = buildDashboardSummary(runFixture, gradeFixture);
  assert.equal(summary.totalRuns, 1);
  assert.equal(summary.totalCases, 2);
  assert.equal(summary.passRate, 50);
  assert.equal(summary.traceCompleteness, 100);

  const clusters = clusterFailures(runFixture, gradeFixture);
  assert.equal(clusters.length, 1);
  assert.equal(clusters[0].failureClass, "wrong_arguments");
});

test("P3 mapper can read the committed redacted smoke fixture shape", async () => {
  const smoke = await loadJson("../../fixtures/a3/p3/ashr_field_sample.redacted.json");
  const { runFixture, gradeFixture } = mapAshrSampleToA3Fixtures(smoke);

  assert.ok(runFixture.runs.length >= 1);
  assert.ok(runFixture.runs[0].cases.length >= 1);
  assert.equal(gradeFixture.grade_results.length, runFixture.runs[0].cases.length);
});
