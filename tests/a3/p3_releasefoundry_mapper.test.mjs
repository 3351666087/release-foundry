import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildDashboardSummary, buildJsonReport, clusterFailures, normalizeCases } from "../../services/report/report_builder.mjs";
import { buildDatasetScenarioIndex, extractReleaseFoundryRuns, mapReleaseFoundrySampleToA3Fixtures } from "../../services/report/p3_releasefoundry_mapper.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

const releasefoundryRunSample = {
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

const releasefoundryDatasetSample = {
  sample: {
    id: 202,
    dataset_source: {
      dataset_type: "multi_run_storyboard",
      runs: {
        "refund-happy-path": {
          run_id: "refund-happy-path",
          title: "Dataset Refund Happy Path",
          description: "Customer asks about unopened headphone refund.",
          intent_tags: ["refund", "policy"],
          audio_tags: { tone: "calm" },
          actions: [{ action_type: "text" }, { action_type: "text" }]
        },
        "refund-wrong-tool": {
          run_id: "refund-wrong-tool",
          title: "Dataset Refund Wrong Tool",
          description: "Customer asks for refund and agent should check policy.",
          intent_tags: ["refund", "tool_use"],
          actions: [{ action_type: "text" }, { action_type: "tool_call" }]
        }
      }
    }
  }
};

test("P3 mapper extracts ReleaseFoundry runs from list_runs style responses", () => {
  assert.equal(extractReleaseFoundryRuns(releasefoundryRunSample).length, 1);
  assert.equal(extractReleaseFoundryRuns(releasefoundryRunSample.runs[0]).length, 1);
  assert.equal(extractReleaseFoundryRuns({ calls: { list_runs: { sample: releasefoundryRunSample } } }).length, 1);
});

test("P3 mapper creates A3 run and grade fixtures", () => {
  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(releasefoundryRunSample);

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
  assert.equal(cases[0].metadata.score_source, "semantic_similarity_average");
  assert.equal(cases[0].grade.metadata.score_source, "semantic_similarity_average");
  assert.equal(cases[1].passed, false);
  assert.equal(cases[1].primary_failure_class, "wrong_arguments");
  assert.equal(cases[1].metadata.score_source, "semantic_similarity_average");
  assert.equal(cases[1].expected.tool_calls[0].tool_name, "lookup_refund_policy");
  assert.equal(cases[1].actual.tool_calls[0].tool_name, "lookup_order");
  assert.equal(cases[1].trace_events.some((event) => event.event_type === "tool.tool_call"), true);
});

test("P3 mapper joins dataset scenario titles into mapped cases", () => {
  const index = buildDatasetScenarioIndex(releasefoundryDatasetSample);
  assert.equal(index.get("refund-happy-path").title, "Dataset Refund Happy Path");

  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(releasefoundryRunSample, {
    datasetSample: releasefoundryDatasetSample
  });
  const cases = normalizeCases(runFixture, gradeFixture);

  assert.equal(runFixture.runs[0].metadata.dataset_scenario_joined, true);
  assert.equal(cases[0].title, "Dataset Refund Happy Path");
  assert.equal(cases[0].family, "multi_run_storyboard");
  assert.equal(cases[0].metadata.dataset_scenario_joined, true);
  assert.equal(cases[0].metadata.dataset_scenario_title, "Dataset Refund Happy Path");
  assert.deepEqual(cases[0].metadata.dataset_intent_tags, ["refund", "policy"]);
  assert.equal(cases[1].title, "Dataset Refund Wrong Tool");
});

test("P3 mapper output works with existing A3 report builder", () => {
  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(releasefoundryRunSample);

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
  const smoke = await loadJson("../../fixtures/a3/p3/releasefoundry_field_sample.redacted.json");
  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(smoke);

  assert.ok(runFixture.runs.length >= 1);
  assert.ok(runFixture.runs[0].cases.length >= 1);
  assert.equal(gradeFixture.grade_results.length, runFixture.runs[0].cases.length);
});

test("P3 mapper can consume read-only get-run probe response.run failed cases", async () => {
  const failedRun = await loadJson("../../fixtures/a3/p3/releasefoundry_failed_run_detail.redacted.json");
  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(failedRun);

  assert.equal(runFixture.runs.length, 1);
  assert.equal(runFixture.runs[0].status, "failed");
  assert.equal(runFixture.runs[0].cases.length, 3);
  assert.equal(gradeFixture.grade_results.length, 3);
  assert.equal(runFixture.runs[0].cases.every((item) => item.status === "failed"), true);
  assert.deepEqual(
    [...new Set(runFixture.runs[0].cases.map((item) => item.primary_failure_class))].sort(),
    ["bad_final_response", "missing_required_tool"]
  );
  assert.equal(runFixture.runs[0].cases.every((item) => item.metadata.score_source === "releasefoundry_case_grade_score"), true);
});

test("P3 mapper preserves media evidence from real ReleaseFoundry result.cases samples", async () => {
  const mediaSample = await loadJson("../../fixtures/a3/p3/releasefoundry_run_detail_sample.redacted.json");
  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(mediaSample);

  assert.equal(runFixture.runs.length, 1);
  assert.equal(runFixture.runs[0].cases.length, 3);
  assert.equal(gradeFixture.grade_results.length, 3);
  assert.equal(new Set(runFixture.runs[0].cases.map((item) => item.case_id)).size, 3);
  assert.equal(new Set(gradeFixture.grade_results.map((item) => item.case_id)).size, 3);

  const mediaCase = runFixture.runs[0].cases.find((item) => item.media_evidence?.media_types.includes("audio"));
  assert.ok(mediaCase);
  assert.equal(mediaCase.media_evidence.primary_media_type, "audio");
  assert.equal(mediaCase.media_evidence.vm_streams.length > 0, true);
  assert.equal(mediaCase.trace_events.some((event) => event.event_type === "media.vm_stream"), true);

  const toolMissingCase = runFixture.runs[0].cases.find((item) => item.expected.tool_calls.length > 0);
  assert.ok(toolMissingCase);
  assert.equal(toolMissingCase.primary_failure_class, "missing_required_tool");
  assert.equal(toolMissingCase.metadata.score_source, "releasefoundry_case_grade_score");
  assert.equal(toolMissingCase.media_evidence.evidence_items.some((item) => item.type === "vm_stream"), true);

  const summary = buildDashboardSummary(runFixture, gradeFixture);
  assert.equal(summary.mediaEvidenceCases, 3);
  assert.equal(summary.vmStreamCases, 3);

  const report = buildJsonReport(runFixture, gradeFixture);
  assert.equal(report.cases.some((item) => item.media_evidence?.primary_media_type === "audio"), true);
  assert.equal(report.cases.every((item) => item.score_source === "releasefoundry_case_grade_score"), true);
});

test("P3 mapper joins official generated dataset 884 to hosted run 11926", async () => {
  const runSample = await loadJson("../../fixtures/a3/p3/releasefoundry_dataset_884_run_11926_ui_tests_detail.redacted.json");
  const datasetSample = await loadJson("../../fixtures/a3/p3/releasefoundry_after_generate_dataset_884.redacted.json");
  const index = buildDatasetScenarioIndex(datasetSample);

  assert.equal(index.has("happy_path_text_valid_booking"), true);
  assert.equal(index.has("pdf_receipt_ocr_split_payment"), true);
  assert.equal(index.has("audio_cutoff_by_two_minutes_exception_request"), true);
  assert.equal(index.has("ui_shows_refund_but_backend_no_tool_call_image"), true);
  assert.equal(index.has("concurrent_requests_tool_timeout_then_processor_failure"), true);
  assert.deepEqual(index.get("pdf_receipt_ocr_split_payment").media_types, ["file", "audio"]);

  const { runFixture, gradeFixture } = mapReleaseFoundrySampleToA3Fixtures(runSample, {
    datasetSample,
    fixtureId: "p3_official_demo_884_11926_dashboard_sample",
    gradeFixtureId: "p3_official_demo_884_11926_dashboard_grades"
  });
  const cases = normalizeCases(runFixture, gradeFixture);
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const report = buildJsonReport(runFixture, gradeFixture);

  assert.equal(runFixture.runs[0].run_id, "11926");
  assert.equal(runFixture.runs[0].dataset_id, "884");
  assert.equal(runFixture.runs[0].metadata.dataset_scenario_joined, true);
  assert.equal(summary.totalCases, 5);
  assert.equal(summary.passed, 2);
  assert.equal(summary.failed, 3);
  assert.equal(summary.passRate, 40);
  assert.equal(summary.mediaEvidenceCases, 5);
  assert.equal(summary.vmStreamCases, 0);
  assert.equal(cases.find((item) => item.case_id === "ui_shows_refund_but_backend_no_tool_call_image").media_evidence.media_types.includes("image"), true);
  assert.equal(cases.find((item) => item.case_id === "pdf_receipt_ocr_split_payment").media_evidence.output_paths.length > 0, true);
  assert.equal(cases.find((item) => item.case_id === "concurrent_requests_tool_timeout_then_processor_failure").primary_failure_class, "wrong_intent");
  assert.equal(report.cases.every((item) => item.score_source === "semantic_similarity_average"), true);
});
