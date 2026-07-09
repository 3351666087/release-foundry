import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildCsvReport,
  buildJsonReport,
  buildMarkdownReport,
  buildToolCallDiffs,
  normalizeCases
} from "../../services/report/report_builder.mjs";
import {
  buildShareableReportPayload,
  renderShareableReportHtml
} from "../../services/report/a3_shareable_report.mjs";

const runFixture = {
  runs: [{
    run_id: "run-a1-a2-compat",
    dataset_id: "dataset-a1-a2-compat",
    runner_id: "a1-local-runner",
    status: "completed",
    trace_completeness: 1,
    cases: [{
      case_id: "case-a1-a2-compat",
      scenario_id: "A2-COMPAT-001",
      title: "A1 trace and A2 grade compatibility",
      family: "release_gate",
      status: "failed",
      expected: {
        final_response: "Call refund_order before the final response.",
        tool_calls: [{
          id: "tool-expected-refund",
          name: "refund_order",
          arguments: { order_id: "order_123", amount: 42 }
        }]
      },
      actual: {
        final_response: "I refunded order_123 without using the tool.",
        tool_calls: []
      },
      trace_events: [{
        event_id: "trace-tool-missing-refund",
        seq: 2,
        event_type: "tool_call",
        phase: "tool",
        source: "agent",
        observation: {
          kind: "tool_call",
          status: "missing",
          text: "Expected refund_order tool call was not observed.",
          data: {
            id: "tool-expected-refund",
            name: "refund_order",
            tool_call_id: "tool-expected-refund"
          }
        }
      }],
      observations: [{
        event_type: "tool_call",
        role: "agent",
        status: "missing",
        content: "A1 observation links the missing tool call.",
        tool_calls: [{ id: "tool-expected-refund", name: "refund_order" }]
      }]
    }]
  }]
};

const gradeFixture = {
  grade_results: [{
    run_id: "run-a1-a2-compat",
    case_id: "case-a1-a2-compat",
    scenario_id: "A2-COMPAT-001",
    passed: false,
    score: 0.42,
    primary_failure_class: "missing_required_tool",
    judge_results: [{
      judge_mode: "a2_contract_judge",
      passed: false,
      score: 0.42,
      failure_analysis: {
        primary_failure_class: "missing_required_tool",
        severity: "blocker",
        summary: "The required refund_order tool call is missing.",
        details: ["A2 expected a refund_order tool call before the final answer."],
        remediation: ["Replay the A1 trace and require the refund_order tool call."]
      },
      evidence: {
        tool_call_ids: ["tool-expected-refund"],
        trace_event_ids: ["trace-tool-missing-refund"],
        final_response_excerpt: "without using the tool"
      }
    }],
    metadata: { score_source: "a2_grade_result" }
  }]
};

const coverageFixture = {
  schema_version: "a2.coverage_report.v1",
  pack_id: "a2-compat-pack",
  meets_assignment_minimums: true,
  scenario_count: 1,
  executable_run_case_count: 1,
  primary_failure_class_counts: { missing_required_tool: 1 },
  executable_failure_class_counts: { missing_required_tool: 1 },
  rubric_classes: ["tool_required"],
  judge_modes: ["a2_contract_judge"]
};

const evidenceReadinessFixture = {
  schema_version: "a2.evidence_readiness.v1",
  status: "ready",
  ready_for_external_collection: true,
  calibration_case_count: 1,
  readiness_checks: {
    a1_trace_ready: true,
    a1_tool_call_ready: true,
    a2_grade_ready: true
  }
};

const releaseGateFixture = {
  schema_version: "a2.release_gate.v1",
  report_id: "a2_release_gate",
  decision: "block",
  exit_code: 2,
  risk_score: 88,
  current_commercial_gate: "C2",
  ready_for_commercial_gate: false,
  blockers: [{ gate: "C3", type: "missing_required_tool", summary: "Tool evidence must be reviewed." }],
  warnings: [{ type: "readiness_review", summary: "A2 readiness must stay attached." }],
  required_evidence: [
    { source: "a1_trace", required_count: 1, current_available: 1 },
    { source: "a2_grade", required_count: 1, current_available: 1 }
  ],
  machine_contract: { ci_mode: "fail on decision=block" },
  evidence_refs: ["case-a1-a2-compat"]
};

const resultPersistenceFixture = {
  schema_version: "a2.result_persistence_manifest.v1",
  manifest_id: "persist-a1-a2-compat",
  metadata: {
    public_safe: true,
    canonical_json_hashing: true,
    raw_private_evidence_not_recorded: true,
    secrets_not_recorded: true
  },
  records: [
    {
      record_type: "judge_result",
      case_id: "case-a1-a2-compat",
      scenario_id: "A2-COMPAT-001",
      judge_id: "a2_contract_judge",
      judge_version: "compat",
      passed: false,
      score: 0.42,
      primary_failure_class: "missing_required_tool",
      output_hash: "hash-judge"
    },
    {
      record_type: "release_gate",
      decision: "block",
      output_hash: "hash-release-gate"
    }
  ]
};

const releaseUnblockChecklistFixture = {
  schema_version: "a2.release_unblock_checklist.v1",
  checklist_id: "unblock-a1-a2-compat",
  source_release_gate: "a2_release_gate",
  overall_status: "blocked",
  release_gate_decision: "block",
  release_gate_exit_code: 2,
  release_gate_risk_score: 88,
  gate_items: [{
    gate: "C3",
    title: "A1 trace and A2 score evidence",
    status: "blocked",
    blocks_release: true,
    owner_role: "A2 evidence reviewer",
    missing_count: 1,
    required_actions: [{
      action: "Review A1 trace, tool_call, A2 score, pass/fail, and failure_class.",
      private_evidence_required: false
    }]
  }],
  a3_consumption_summary: {
    dashboard_sections: ["case_detail", "release_gate", "readiness"],
    primary_action: "Keep compatibility fields visible in A3 reports."
  },
  review_workflow: { required_reviewers: ["A2 evidence reviewer"] },
  evidence_refs: ["case-a1-a2-compat"]
};

const a2ReadinessBundle = {
  releaseGate: releaseGateFixture,
  resultPersistence: resultPersistenceFixture,
  releaseUnblockChecklist: releaseUnblockChecklistFixture
};

test("A3 report/export/dashboard contracts preserve A1 trace/tool_call and A2 grading fields", async () => {
  const cases = normalizeCases(runFixture, gradeFixture);
  assert.equal(cases.length, 1);
  const [caseItem] = cases;

  assert.equal(caseItem.trace_ready, true);
  assert.equal(caseItem.trace_events[0].event_id, "trace-tool-missing-refund");
  assert.equal(caseItem.expected.tool_calls[0].name, "refund_order");
  assert.equal(caseItem.actual.tool_calls.length, 0);
  assert.equal(caseItem.passed, false);
  assert.equal(caseItem.score, 42);
  assert.equal(caseItem.primary_failure_class, "missing_required_tool");
  assert.equal(caseItem.severity, "blocker");

  const diffs = buildToolCallDiffs(caseItem);
  assert.equal(diffs[0].status, "missing_required_tool");
  assert.equal(diffs[0].expected.name, "refund_order");
  assert.equal(diffs[0].trace_event_links[0].event_id, "trace-tool-missing-refund");
  assert.equal(diffs[0].judge_evidence[0].score, 0.42);
  assert.equal(diffs[0].judge_evidence[0].primary_failure_class, "missing_required_tool");

  const jsonReport = buildJsonReport(
    runFixture,
    gradeFixture,
    coverageFixture,
    evidenceReadinessFixture,
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    a2ReadinessBundle
  );
  assert.equal(jsonReport.summary.passed, 0);
  assert.equal(jsonReport.summary.failed, 1);
  assert.equal(jsonReport.evidence_readiness.schema_version, "a2.evidence_readiness.v1");
  assert.equal(jsonReport.evidence_readiness.status, "ready");
  assert.equal(jsonReport.evidence_readiness.ready_for_external_collection, true);
  assert.equal(jsonReport.release_gate.schema_version, "a2.release_gate.v1");
  assert.equal(jsonReport.release_gate.decision, "block");
  assert.equal(jsonReport.release_gate.blocks_release, true);
  assert.deepEqual(jsonReport.release_gate.required_sources, ["a1_trace", "a2_grade"]);
  assert.equal(jsonReport.a2_result_persistence.latest_records[0].passed, false);
  assert.equal(jsonReport.a2_result_persistence.latest_records[0].score, 0.42);
  assert.equal(jsonReport.a2_result_persistence.latest_records[0].primary_failure_class, "missing_required_tool");
  assert.equal(jsonReport.a2_result_persistence.release_gate_record_count, 1);
  assert.equal(jsonReport.a2_release_unblock_checklist.release_gate_decision, "block");
  assert.deepEqual(jsonReport.a2_release_unblock_checklist.dashboard_sections, ["case_detail", "release_gate", "readiness"]);
  assert.equal(jsonReport.cases[0].status, "failed");
  assert.equal(jsonReport.cases[0].score, 42);
  assert.equal(jsonReport.cases[0].score_source, "a2_grade_result");
  assert.equal(jsonReport.cases[0].primary_failure_class, "missing_required_tool");
  assert.equal(jsonReport.cases[0].expected.tool_calls[0].name, "refund_order");
  assert.equal(jsonReport.cases[0].tool_call_diffs[0].trace_event_links[0].event_id, "trace-tool-missing-refund");
  assert.equal(jsonReport.export_redaction_firewall.a1_a2_calibration.a1_trace_ready_count, 1);
  assert.equal(jsonReport.export_redaction_firewall.a1_a2_calibration.a1_tool_diff_case_count, 1);
  assert.equal(jsonReport.export_redaction_firewall.a1_a2_calibration.a2_grade_count, 1);
  assert.equal(jsonReport.export_redaction_firewall.a1_a2_calibration.a2_failure_class_count, 1);

  const csvReport = buildCsvReport(runFixture, gradeFixture);
  assert.match(csvReport, /"status","score","severity","primary_failure_class"/);
  assert.match(csvReport, /"failed","42","blocker","missing_required_tool"/);

  const markdownReport = buildMarkdownReport(
    runFixture,
    gradeFixture,
    coverageFixture,
    evidenceReadinessFixture,
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    a2ReadinessBundle
  );
  assert.match(markdownReport, /## Release Gate/);
  assert.match(markdownReport, /Decision: block/);
  assert.match(markdownReport, /## A2 Result Persistence/);
  assert.match(markdownReport, /Failed judge results: 1/);
  assert.match(markdownReport, /## A2 Release Unblock Checklist/);
  assert.match(markdownReport, /Release decision: block/);
  assert.match(markdownReport, /case-a1-a2-compat \/ A2-COMPAT-001: FAIL \(42\)/);

  const shareable = buildShareableReportPayload({
    runFixture,
    gradeFixture,
    coverage: coverageFixture,
    evidenceReadiness: evidenceReadinessFixture,
    a2ReadinessBundle
  }, {
    reportId: "a3r_a1_a2_compat",
    shareToken: "a3s_a1_a2_compat",
    createdAt: "2026-07-09T00:00:00.000Z"
  });
  assert.equal(shareable.release_gate.decision, "block");
  assert.equal(shareable.payload.cases[0].status, "failed");
  assert.equal(shareable.payload.cases[0].score, 42);
  assert.equal(shareable.payload.cases[0].primary_failure_class, "missing_required_tool");
  assert.equal(shareable.payload.cases[0].tool_call_diffs[0].trace_event_links[0].event_id, "trace-tool-missing-refund");
  const shareableHtml = renderShareableReportHtml(shareable);
  assert.match(shareableHtml, /Release Gate/);
  assert.match(shareableHtml, /case-a1-a2-compat/);
  assert.match(shareableHtml, /missing_required_tool/);

  const dashboardSource = await readFile(new URL("../../apps/dashboard/src/app.mjs", import.meta.url), "utf8");
  assert.match(dashboardSource, /state\.cases = normalizeCases\(state\.runs, state\.grades\)/);
  assert.match(dashboardSource, /item\.trace_events/);
  assert.match(dashboardSource, /data: \{ tool_calls: obs\.tool_calls \}/);
  assert.match(dashboardSource, /item\.passed \? "PASS" : "FAIL"/);
  assert.match(dashboardSource, /item\.score/);
  assert.match(dashboardSource, /item\.primary_failure_class/);
  assert.match(dashboardSource, /state\.evidenceReadiness/);
  assert.match(dashboardSource, /releaseGate: state\.releaseGate/);
  assert.match(dashboardSource, /buildCsvReport\(state\.runs, state\.grades\)/);
});
