import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildArgumentDiffs,
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport,
  buildToolCallDiffs,
  canonicalPrimaryFailureClass,
  clusterFailures,
  filterCases,
  getFilterOptions,
  normalizeCases,
  summarizeCoverage,
  summarizeCloudConsoleShell,
  summarizeEvidenceReadiness,
  summarizeMediaReadiness,
  summarizeOfficialAshrGap,
  summarizeOfficialCodeCrawlParity,
  summarizeOfficialFrontendMirror,
  summarizeOfficialParityRoadmap,
  summarizeIncidentReplayQueue,
  summarizeReviewerWorkflowBoard,
  summarizeReleaseGate,
  summarizeReleaseWarRoom,
  summarizeReleaseWorkflow,
  summarizeRequestProvenance,
  summarizeUsageQuota
} from "../../services/report/report_builder.mjs";
import { mapAshrSampleToA3Fixtures } from "../../services/report/p3_ashr_mapper.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 report builder summarizes run and grade fixtures", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const summary = buildDashboardSummary(runs, grades);
  assert.equal(summary.totalRuns, 1);
  assert.equal(summary.totalCases, 32);
  assert.equal(summary.passed, 2);
  assert.equal(summary.failed, 30);
  assert.equal(summary.passRate, 6.3);
  assert.equal(summary.traceCompleteness, 100);
});

test("A3 release gate blocks risky evidence and approves clean evidence", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const riskyGate = summarizeReleaseGate(riskyRuns, riskyGrades, coverage);

  assert.equal(riskyGate.decision, "block_release");
  assert.equal(riskyGate.pr_gate.blocks_merge, true);
  assert.ok(riskyGate.failed_checks.includes("pass_rate"));
  assert.ok(riskyGate.failed_checks.includes("policy_failures"));
  assert.ok(riskyGate.required_approvers.includes("Safety reviewer"));
  assert.ok(riskyGate.top_risk_cases.length > 0);

  const cleanRuns = {
    runs: [{
      run_id: "run-clean-release",
      dataset_id: "release-gate-smoke",
      runner_id: "a1-local-runner",
      status: "passed",
      trace_completeness: 1,
      cases: [
        {
          case_id: "case-clean-1",
          scenario_id: "A2-S001",
          title: "Clean direct answer",
          family: "release_gate",
          status: "passed",
          score: 0.98,
          primary_failure_class: "none",
          expected: { summary: "Answer directly." },
          actual: { final_response: "Answered directly." }
        },
        {
          case_id: "case-clean-2",
          scenario_id: "A2-S002",
          title: "Clean arithmetic",
          family: "release_gate",
          status: "passed",
          score: 0.96,
          primary_failure_class: "none",
          expected: { summary: "Return 52." },
          actual: { final_response: "52" }
        }
      ]
    }]
  };
  const cleanGrades = {
    grade_results: cleanRuns.runs[0].cases.map((item) => ({
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      passed: true,
      score: item.score,
      primary_failure_class: "none",
      judge_results: []
    }))
  };
  const cleanGate = summarizeReleaseGate(cleanRuns, cleanGrades, {
    meets_assignment_minimums: true
  });

  assert.equal(cleanGate.decision, "approve_release");
  assert.equal(cleanGate.pr_gate.blocks_merge, false);
  assert.equal(cleanGate.failed_check_count, 0);
  assert.deepEqual(cleanGate.failed_checks, []);
});

test("A3 release workflow packages PR check, waiver, audit bundle, and incident replay", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");

  const workflow = summarizeReleaseWorkflow(riskyRuns, riskyGrades, coverage, {}, {
    release_version: "refund-agent-2026.07.07",
    environment: "staging",
    owner: "A3 release owner"
  });

  assert.equal(workflow.available, true);
  assert.equal(workflow.github_check.name, "Ashr++ Release Gate");
  assert.equal(workflow.github_check.conclusion, "failure");
  assert.equal(workflow.github_check.blocks_merge, true);
  assert.match(workflow.github_check.output.summary, /Block release/);
  assert.match(workflow.pr_comment_markdown, /## Ashr\+\+ Release Gate/);
  assert.match(workflow.pr_comment_markdown, /refund-agent-2026\.07\.07/);
  assert.equal(workflow.waiver_policy.required, true);
  assert.equal(workflow.waiver_policy.exceptional_only, true);
  assert.ok(workflow.waiver_policy.required_fields.includes("expiry_date"));
  assert.ok(workflow.reviewer_workflow.review_lanes.includes("A3 triage owner"));
  assert.ok(workflow.reviewer_workflow.next_actions.some((item) => /pass rate/i.test(item)));
  assert.equal(workflow.audit_bundle.manifest_version, "a3.audit_bundle.v1");
  assert.ok(workflow.audit_bundle.artifacts.some((item) => item.id === "json_report" && item.required));
  assert.ok(workflow.audit_bundle.redaction_policy.includes("No API keys"));
  assert.equal(workflow.incident_replay.enabled, true);
  assert.ok(workflow.incident_replay.case_ids.length > 0);

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage);
  assert.equal(json.release_workflow.github_check.conclusion, "failure");
  assert.ok(json.release_workflow.audit_bundle.artifacts.some((item) => item.id === "redacted_fixtures"));

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage);
  assert.match(markdown, /## PR Gate \/ Review Workflow/);
  assert.match(markdown, /GitHub check: Ashr\+\+ Release Gate/);
  assert.match(markdown, /### PR Comment Template/);
});

test("A3 release war room joins gate, replay, audit, and official parity signals", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const requestSample = await loadJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
  const usageSample = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
  const frontendMirror = await loadJson("../../fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json");

  const warRoom = summarizeReleaseWarRoom(
    riskyRuns,
    riskyGrades,
    coverage,
    mediaSignedUrlCoverage,
    requestSample,
    usageSample,
    usageApiProbe,
    frontendMirror
  );

  assert.equal(warRoom.available, true);
  assert.equal(warRoom.schema_version, "a3.release_war_room.v1");
  assert.equal(warRoom.decision, "no_go");
  assert.equal(warRoom.decision_label, "No-go");
  assert.equal(warRoom.blocks_merge, true);
  assert.equal(warRoom.waiver_required, true);
  assert.ok(warRoom.revenue_risk_score >= 70);
  assert.ok(warRoom.incident_replay_case_count > 0);
  assert.ok(warRoom.required_artifact_count >= 4);
  assert.ok(warRoom.lanes.some((lane) => lane.lane === "Incident Replay" && lane.status === "active"));
  assert.ok(warRoom.lanes.some((lane) => lane.lane === "Evidence & Audit" && lane.status === "required"));
  assert.ok(warRoom.lanes.some((lane) => lane.lane === "Official Product Parity" && lane.status === "mapped"));
  assert.equal(warRoom.enterprise_readiness.secret_free_exports, true);
  assert.equal(warRoom.enterprise_readiness.external_mutations_enabled, false);
  assert.ok(warRoom.executive_brief.some((line) => /Revenue risk score/.test(line)));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, {}, {}, frontendMirror);
  assert.equal(json.release_war_room.schema_version, "a3.release_war_room.v1");
  assert.equal(json.release_war_room.decision, "no_go");
  assert.ok(json.release_war_room.lanes.length >= 6);

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, {}, {}, frontendMirror);
  assert.match(markdown, /## Release War Room/);
  assert.match(markdown, /Decision: No-go/);
  assert.match(markdown, /Release Control: blocked/);
  assert.match(markdown, /Official Product Parity: mapped/);

  const committedWarRoom = await loadJson("../../fixtures/a3/p3/a3_release_war_room_11926.redacted.json");
  assert.equal(committedWarRoom.schema_version, "a3.release_war_room.v1");
  assert.equal(committedWarRoom.decision, "no_go");
  assert.equal(committedWarRoom.safety.secret_values_saved, false);
  assert.equal(committedWarRoom.safety.raw_signed_urls_saved, false);
});

test("A3 incident replay queue packages failed cases with A1 and A2 evidence", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");

  const replay = summarizeIncidentReplayQueue(riskyRuns, riskyGrades, mediaSignedUrlCoverage);

  assert.equal(replay.schema_version, "a3.incident_replay_queue.v1");
  assert.equal(replay.available, true);
  assert.ok(replay.queue_count > 0);
  assert.ok(replay.blocker_count > 0);
  assert.ok(replay.trace_ready_count > 0);
  assert.ok(replay.tool_diff_ready_count > 0);
  assert.ok(replay.judge_evidence_ready_count > 0);
  assert.ok(replay.replay_steps.some((step) => /A1 trace/.test(step)));
  assert.ok(replay.replay_steps.some((step) => /A2 judge/.test(step)));
  assert.ok(replay.queue.some((item) => item.reviewer_packet.artifacts.includes("tool_call_diff")));
  assert.ok(replay.queue.some((item) => item.reviewer_packet.artifacts.includes("a2_judge_evidence")));
  assert.ok(replay.queue.every((item) => item.reviewer_packet.required));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage);
  assert.equal(json.incident_replay_queue.schema_version, "a3.incident_replay_queue.v1");
  assert.ok(json.incident_replay_queue.queue_count > 0);

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage);
  assert.match(markdown, /## Incident Replay Queue/);
  assert.match(markdown, /Replay A1 trace events and tool-call diffs/);
  assert.match(markdown, /Read linked A2 judge evidence/);
});

test("A3 reviewer workflow board turns A1 and A2 evidence into owner review state", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");

  const board = summarizeReviewerWorkflowBoard(riskyRuns, riskyGrades, coverage, mediaSignedUrlCoverage);

  assert.equal(board.schema_version, "a3.reviewer_workflow_board.v1");
  assert.equal(board.available, true);
  assert.equal(board.board_state, "blocked");
  assert.ok(board.required_reviewer_count > 0);
  assert.ok(board.open_item_count > 0);
  assert.ok(board.blocked_item_count > 0);
  assert.ok(board.waiver_blocked_count > 0);
  assert.ok(board.a1_a2_calibration.a1_trace_ready_count > 0);
  assert.ok(board.a1_a2_calibration.a1_tool_diff_ready_count > 0);
  assert.ok(board.a1_a2_calibration.a2_judge_evidence_ready_count > 0);
  assert.ok(board.lanes.some((lane) => lane.status === "blocked"));
  assert.ok(board.items.some((item) => item.required_artifacts.includes("trace_timeline")));
  assert.ok(board.items.some((item) => item.required_artifacts.includes("a2_judge_evidence")));
  assert.ok(board.items.some((item) => item.evidence_counts.tool_diffs > 0));
  assert.ok(board.review_steps.some((step) => /A1 trace/.test(step)));
  assert.ok(board.review_steps.some((step) => /A2 judge/.test(step)));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage);
  assert.equal(json.reviewer_workflow_board.schema_version, "a3.reviewer_workflow_board.v1");
  assert.equal(json.reviewer_workflow_board.board_state, "blocked");

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage);
  assert.match(markdown, /## Reviewer Workflow Board/);
  assert.match(markdown, /A1 trace ready/);
  assert.match(markdown, /A2 judge evidence ready/);
});

test("A3 report builder clusters failures by primary failure class", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const clusters = clusterFailures(runs, grades);
  assert.deepEqual(clusters.map((cluster) => cluster.failureClass).sort(), [
    "forbidden_tool_call",
    "hallucinated_tool_result",
    "ignored_tool_result",
    "missing_clarification",
    "missing_required_tool",
    "poor_failure_recovery",
    "unnecessary_tool_call",
    "unsafe_or_policy_violation",
    "wrong_arguments",
    "wrong_intent",
    "wrong_tool",
    "wrong_tool_order"
  ]);
  assert.equal(clusters.reduce((sum, cluster) => sum + cluster.count, 0), 30);
});

test("A3 report builder canonicalizes local failure signals before clustering", () => {
  const runs = {
    runs: [{
      run_id: "run-local-signal",
      dataset_id: "a2-local-scenarios",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [
        {
          case_id: "case-bad-final",
          scenario_id: "A2-S013",
          title: "Bad final response",
          family: "direct_answer",
          status: "failed",
          score: 45
        },
        {
          case_id: "case-missing-primary",
          scenario_id: "A2-S999",
          title: "Missing primary",
          family: "direct_answer",
          status: "failed",
          score: 30
        }
      ]
    }]
  };
  const grades = {
    grade_results: [{
      case_id: "case-bad-final",
      passed: false,
      score: 45,
      primary_failure_class: "bad_final_response",
      judge_results: []
    }]
  };

  assert.equal(canonicalPrimaryFailureClass("output_schema_invalid", false), "wrong_intent");

  const cases = normalizeCases(runs, grades);
  assert.deepEqual(cases.map((item) => item.primary_failure_class), ["wrong_intent", "wrong_intent"]);
  assert.equal(cases[0].raw_primary_failure_class, "bad_final_response");

  const clusters = clusterFailures(runs, grades);
  assert.deepEqual(clusters.map((cluster) => [cluster.failureClass, cluster.count]), [["wrong_intent", 2]]);
});

test("A3 report builder normalizes nested A1 grade scores without A2 grade joins", () => {
  const runs = {
    runs: [{
      run_id: "run-a1-nested-grade",
      dataset_id: "a1-local",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [{
        case_id: "a1-nested-grade-case",
        scenario_id: "A2-S010",
        title: "A1 nested grade score",
        family: "retrieval_grounding",
        status: "failed",
        grade: {
          passed: false,
          score: 0.62,
          primary_failure_class: "wrong_arguments",
          judge_results: []
        }
      }]
    }]
  };

  const [item] = normalizeCases(runs, {});
  assert.equal(item.score, 62);
  assert.equal(item.primary_failure_class, "wrong_arguments");
  assert.equal(item.failure_summary, "Failure requires triage.");
});

test("A3 report builder uses the matching failed judge analysis for triage summaries", async () => {
  const run = await loadJson("../../fixtures/a2/runs/a2_s003_hallucinated_weather.json");
  const grade = await loadJson("../../fixtures/a2/results/a2_s003_hallucinated_weather_grade.json");
  const runs = {
    runs: [{
      run_id: "run-a2-s003-triage",
      dataset_id: "a2-g3-calibration",
      runner_id: "a1-local-runner",
      status: "failed",
      cases: [{
        case_id: run.case_id,
        scenario_id: run.scenario_id,
        title: "Optional Weather Check",
        family: "tool_execution",
        status: "failed",
        expected: run.expected,
        actual: run.run
      }]
    }]
  };
  const grades = { grade_results: [grade] };

  const [item] = normalizeCases(runs, grades);
  assert.equal(item.primary_failure_class, "hallucinated_tool_result");
  assert.equal(item.severity, "major");
  assert.match(item.failure_summary, /Forbidden or contradicted facts present/);
  assert.doesNotMatch(item.failure_summary, /Tool policy satisfied/);
});

test("A3 report builder exposes and applies dashboard filters", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const cases = normalizeCases(runs, grades);
  const options = getFilterOptions(cases);

  assert.ok(options.statuses.includes("passed"));
  assert.ok(options.families.includes("tool_execution"));
  assert.ok(options.failureClasses.includes("missing_required_tool"));
  assert.ok(options.runIds.includes("run_a3_generated_from_a2_g3"));
  assert.ok(options.severities.includes("major"));
  assert.ok(options.scoreBands.includes("70-89"));
  assert.ok(options.judgeModes.includes("g1_trace_contract_judge"));
  assert.ok(options.judgeModes.includes("g2_output_contract_judge"));

  const filtered = filterCases(cases, {
    status: "failed",
    failureClass: "missing_required_tool",
    severity: "major",
    scoreBand: "70-89"
  });
  assert.deepEqual(filtered.map((item) => item.case_id).sort(), [
    "sample-a2-s004-missing-tool",
    "sample-a2-s029-missing-required-search"
  ]);

  const outputJudgeCases = filterCases(cases, {
    judgeMode: "g2_output_contract_judge"
  });
  assert.equal(outputJudgeCases.length, cases.length);
  assert.ok(outputJudgeCases.some((item) => item.case_id === "sample-a2-s001-pass"));
  assert.ok(outputJudgeCases.some((item) => item.case_id === "sample-a2-s004-missing-tool"));
});

test("A3 export builders produce markdown, CSV, and JSON report shapes", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");

  const cases = normalizeCases(runs, grades);
  assert.equal(cases.length, 32);

  const markdown = buildMarkdownReport(runs, grades);
  assert.match(markdown, /A3 Dashboard Triage Report/);
  assert.match(markdown, /## Release Gate/);
  assert.match(markdown, /missing_required_tool/);
  assert.doesNotMatch(markdown, /## Coverage/);

  const csv = buildCsvReport(runs, grades);
  assert.match(csv, /"case_id"/);
  assert.match(csv, /"sample-a2-s004-missing-tool"/);
  assert.match(csv, /"media_types"/);

  const json = buildJsonReport(runs, grades);
  assert.equal(json.schema_version, "a3.export_report.v1");
  assert.equal(json.coverage.available, false);
  assert.equal(json.release_gate.decision, "block_release");
  assert.equal(json.failure_clusters.length, 12);
  assert.ok(Array.isArray(json.cases[0].tool_call_diffs));
  assert.equal(json.cases[0].score_source, "unknown");
});

test("A3 report builder creates tool-call expected-vs-actual diffs", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const cases = normalizeCases(runs, grades);

  const missingToolCase = cases.find((item) => item.case_id === "sample-a2-s004-missing-tool");
  const missingDiffs = buildToolCallDiffs(missingToolCase);
  assert.equal(missingDiffs.length, 1);
  assert.equal(missingDiffs[0].status, "missing_required_tool");
  assert.equal(missingDiffs[0].expected.name, "web.search");
  assert.equal(missingDiffs[0].judge_evidence.length, 1);
  assert.equal(missingDiffs[0].judge_evidence[0].primary_failure_class, "missing_required_tool");
  assert.match(missingDiffs[0].judge_evidence[0].summary, /Required tool missing/);

  const wrongArgumentCase = cases.find((item) => item.case_id === "sample-a2-s010-wrong-arguments");
  const wrongArgumentDiffs = buildToolCallDiffs(wrongArgumentCase);
  assert.equal(wrongArgumentDiffs.length, 1);
  assert.equal(wrongArgumentDiffs[0].status, "wrong_arguments");
  assert.equal(wrongArgumentDiffs[0].expected.name, "file.read");
  assert.equal(wrongArgumentDiffs[0].actual.name, "file.read");
  assert.deepEqual(wrongArgumentDiffs[0].argument_diffs, [{
    path: "path",
    status: "changed_argument",
    expected: "fixtures/a2/contracts/vendor-alpha.txt",
    actual: "fixtures/a2/contracts/vendor-alfa.txt"
  }]);
  assert.equal(wrongArgumentDiffs[0].judge_evidence.length, 1);
  assert.equal(wrongArgumentDiffs[0].judge_evidence[0].judge_mode, "g1_trace_contract_judge");
  assert.deepEqual(wrongArgumentDiffs[0].judge_evidence[0].evidence.tool_call_ids, ["file.read#1"]);
  assert.equal(wrongArgumentDiffs[0].trace_event_links.length, 1);
  assert.deepEqual(wrongArgumentDiffs[0].judge_evidence[0].evidence.trace_event_ids, [
    "sample-a2-s010-wrong-arguments:trace:1"
  ]);
  assert.deepEqual(wrongArgumentDiffs[0].judge_evidence[0].remediation, [
    "Align trace with scenario toolPolicy."
  ]);

  const json = buildJsonReport(runs, grades);
  const exportedCase = json.cases.find((item) => item.case_id === "sample-a2-s010-wrong-arguments");
  assert.equal(exportedCase.tool_call_diffs[0].argument_diffs[0].path, "path");
  assert.equal(exportedCase.tool_call_diffs[0].judge_evidence[0].primary_failure_class, "wrong_arguments");
});

test("A3 report builder semantically pairs reordered tool calls", () => {
  const caseResult = {
    case_id: "case-reordered-tools",
    primary_failure_class: "wrong_tool_order",
    expected: {
      tool_calls: [
        {
          tool: "web.search",
          args: {
            query: "Project Zephyr official changelog latest release"
          }
        },
        {
          tool: "web.open",
          args: {
            url: "https://example.test/project-zephyr/changelog"
          }
        }
      ]
    },
    actual: {
      tool_calls: [
        {
          id: "web.open#1",
          name: "web.open",
          arguments: {
            url: "https://example.test/project-zephyr/changelog"
          }
        },
        {
          id: "web.search#1",
          name: "web.search",
          arguments: {
            query: "Project Zephyr official changelog latest release"
          }
        }
      ]
    },
    trace_events: [
      {
        event_id: "trace-web-open",
        seq: 10,
        phase: "tool",
        event_type: "tool.tool_call",
        observation: {
          kind: "tool_call",
          data: {
            id: "web.open#1",
            name: "web.open"
          }
        }
      },
      {
        event_id: "trace-web-search",
        seq: 11,
        phase: "tool",
        event_type: "tool.tool_call",
        observation: {
          kind: "tool_call",
          data: {
            id: "web.search#1",
            name: "web.search"
          }
        }
      }
    ],
    judge_results: [
      {
        judge_mode: "g1_trace_contract_judge",
        passed: false,
        score: 71,
        failure_analysis: {
          primary_failure_class: "wrong_tool_order",
          failure_classes: ["wrong_tool_order"],
          severity: "major",
          summary: "Tool order violated: web.search before web.open",
          details: ["Tool order violated: web.search before web.open"],
          remediation: ["Align trace with scenario toolPolicy."]
        },
        evidence: {
          tool_call_ids: ["web.open#1", "web.search#1"]
        }
      }
    ]
  };

  const diffs = buildToolCallDiffs(caseResult);

  assert.equal(diffs.length, 2);
  assert.deepEqual(diffs.map((diff) => diff.status), ["wrong_tool_order", "wrong_tool_order"]);
  assert.deepEqual(diffs.map((diff) => diff.expected.name), ["web.search", "web.open"]);
  assert.deepEqual(diffs.map((diff) => diff.actual.name), ["web.search", "web.open"]);
  assert.deepEqual(diffs.map((diff) => diff.match_strategy), ["semantic_exact_reordered", "semantic_exact_reordered"]);
  assert.deepEqual(diffs.map((diff) => [diff.expected_index, diff.actual_index]), [[0, 1], [1, 0]]);
  assert.deepEqual(diffs.map((diff) => diff.trace_event_links.map((event) => event.event_id)), [
    ["trace-web-search"],
    ["trace-web-open"]
  ]);
  assert.deepEqual(diffs.map((diff) => diff.judge_evidence[0].evidence.trace_event_ids), [
    ["trace-web-search"],
    ["trace-web-open"]
  ]);
  assert.equal(diffs.some((diff) => diff.status === "wrong_tool"), false);
  assert.equal(diffs[0].judge_evidence[0].primary_failure_class, "wrong_tool_order");
});

test("A3 report builder creates field-level argument diffs", () => {
  const argumentDiffs = buildArgumentDiffs(
    {
      order_id: "R-100",
      refund: {
        reason: "damaged",
        items: ["sku-1", "sku-2"]
      }
    },
    {
      order_id: "R-100",
      refund: {
        reason: "changed_mind",
        items: ["sku-1"]
      },
      dry_run: true
    }
  );

  assert.deepEqual(argumentDiffs, [
    {
      path: "dry_run",
      status: "unexpected_argument",
      expected: null,
      actual: true
    },
    {
      path: "refund.items[1]",
      status: "missing_argument",
      expected: "sku-2",
      actual: null
    },
    {
      path: "refund.reason",
      status: "changed_argument",
      expected: "damaged",
      actual: "changed_mind"
    }
  ]);
});

test("A3 report builder can consume A2 G3 aggregate grade fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const cases = normalizeCases(runs, grades);
  const clusters = clusterFailures(runs, grades);
  const judgeModes = new Set(cases.flatMap((item) => item.judge_modes || []));

  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s042-wrong-read-order"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-pass"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-wrong-order"));
  assert.ok(grades.grade_results.some((grade) => grade.case_id === "sample-a2-s031-media-pipeline-unsupported-output"));
  assert.ok(cases.length >= 3);
  assert.ok(clusters.some((cluster) => cluster.failureClass === "wrong_arguments"));
  assert.equal(judgeModes.size, 5);
  assert.ok(judgeModes.has("g3_semantic_reference_judge"));
});

test("A3 report builder can join every A2 G3 aggregate grade by case id", async () => {
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const runs = {
    runs: [{
      run_id: "run-a2-g3-aggregate-join",
      dataset_id: grades.dataset_id,
      runner_id: "a1-local-runner",
      status: "failed",
      cases: grades.grade_results.map((grade) => ({
        case_id: grade.case_id,
        scenario_id: grade.scenario_id,
        title: grade.case_id,
        family: "a2_g3_calibration",
        status: grade.passed ? "passed" : "failed"
      }))
    }]
  };

  const cases = normalizeCases(runs, grades);
  assert.equal(cases.length, grades.grade_results.length);
  assert.equal(cases.filter((item) => item.judge_results.length === 5).length, grades.grade_results.length);
  assert.deepEqual(
    cases.map((item) => item.primary_failure_class).sort(),
    grades.grade_results.map((grade) => grade.primary_failure_class).sort()
  );
});

test("A3 report builder can summarize A2 G3 coverage fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");

  const summary = summarizeCoverage(coverage);
  assert.equal(summary.available, true);
  assert.equal(summary.meets_assignment_minimums, true);
  assert.equal(summary.scenario_count, 60);
  assert.equal(summary.scenario_dimension_counts.required_tool_use, 24);
  assert.equal(summary.scenario_dimension_counts.fixture_grounding, 30);
  assert.equal(summary.scenario_dimension_counts.ordered_tool_sequence, 5);
  assert.equal(summary.scenario_dimension_counts.tool_output_grounding, 1);
  assert.deepEqual(summary.scenario_dimension_scenarios.tool_output_grounding, ["A2-S031"]);
  assert.equal(summary.scenario_quality_warning_count, 0);
  assert.equal(summary.difficulty_counts.D4, 2);
  assert.equal(summary.multi_turn_scenario_count, 4);
  assert.equal(summary.ordered_tool_pairs["web.search -> web.open"], 3);
  assert.equal(summary.ordered_tool_pairs["file.read -> file.read"], 1);
  assert.equal(summary.ordered_tool_pairs["media.fetch -> image.view"], 1);
  assert.equal(summary.ordered_tool_pairs["image.view -> media.classify"], 1);
  assert.equal(summary.rubric_class_count, 5);
  assert.equal(summary.judge_mode_count, 5);
  assert.equal(summary.executable_run_case_count, 32);
  assert.equal(summary.executable_media_case_count, 4);
  assert.equal(summary.executable_tool_output_grounding_case_count, 4);
  assert.equal(summary.executable_media_expected_class_counts.wrong_arguments, 1);
  assert.equal(summary.primary_failure_class_count, 12);
  assert.equal(summary.golden_failure_classes_missing.length, 0);
  assert.equal(summary.executable_failure_classes_missing.length, 0);
  assert.equal(summary.coverage_warning_count, 0);
  assert.equal(Object.keys(summary.thin_golden_failure_classes).length, 0);
  assert.equal(Object.keys(summary.thin_executable_failure_classes).length, 0);
  assert.ok(summary.golden_failure_class_cases.wrong_arguments.some((item) => (
    item.case_id === "GC-A2-S033-fail-wrong-calculator-arguments"
  )));
  assert.ok(summary.executable_failure_class_cases.missing_required_tool.some((item) => (
    item.case_id === "sample-a2-s029-missing-required-search"
  )));
  assert.ok(summary.executable_failure_class_cases.hallucinated_tool_result.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-unsupported-output"
  )));
  assert.ok(summary.executable_failure_class_cases.wrong_tool_order.some((item) => (
    item.case_id === "sample-a2-s042-wrong-read-order"
  )));
  assert.ok(summary.executable_failure_class_cases.wrong_tool_order.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-wrong-order"
  )));
  assert.ok(summary.executable_media_case_refs.some((item) => (
    item.case_id === "sample-a2-s031-media-pipeline-wrong-classifier-args"
  )));

  const json = buildJsonReport(runs, grades, coverage);
  assert.equal(json.coverage.executable_failure_class_count, 12);
  assert.equal(json.coverage.executable_media_case_count, 4);
  assert.equal(json.coverage.coverage_warning_count, 0);
  assert.equal(json.coverage.scenario_quality_warnings.length, 0);
  assert.equal(json.coverage.golden_failure_class_cases.wrong_arguments.length, 2);

  const markdown = buildMarkdownReport(runs, grades, coverage);
  assert.match(markdown, /## Coverage/);
  assert.match(markdown, /Assignment minimums met: yes/);
  assert.match(markdown, /Scenarios: 60/);
  assert.match(markdown, /Scenario dimensions met: 16\/16/);
  assert.match(markdown, /Scenario quality warnings: 0/);
  assert.doesNotMatch(markdown, /### Scenario Quality Warnings/);
  assert.match(markdown, /Coverage warnings: 0/);
  assert.match(markdown, /Media executable cases: 4/);
  assert.match(markdown, /Tool-output grounding executable cases: 4/);
  assert.match(markdown, /### Failure Class Evidence/);
  assert.match(markdown, /wrong_arguments: golden GC-A2-S010-fail\/A2-S010/);
  assert.match(markdown, /missing_required_tool: golden GC-A2-S004-fail\/A2-S004/);
  assert.match(markdown, /sample-a2-s029-missing-required-search\/A2-S029/);
});

test("A3 report builder can summarize A2 evidence readiness fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");

  const summary = summarizeEvidenceReadiness(readiness);
  assert.equal(summary.available, true);
  assert.equal(summary.schema_version, "a2.evidence_readiness.v1");
  assert.equal(summary.status, "awaiting_private_evidence");
  assert.equal(summary.ready_for_external_collection, true);
  assert.equal(summary.calibration_case_count, 6);
  assert.equal(summary.ashr_current_missing, 6);
  assert.equal(summary.ashr_expected_observation_count, 6);
  assert.equal(summary.ashr_case_map_covers_all_calibration_cases, true);
  assert.equal(summary.semantic_offline_reference_only, true);
  assert.equal(summary.semantic_expected_reviewed_observation_count, 6);
  assert.ok(summary.semantic_required_fields.includes("prompt_hash"));
  assert.deepEqual(summary.covered_sdk_languages, ["python", "typescript"]);
  assert.ok(summary.batch_plan_refs.includes("semantic_llm_judge_audit"));
  assert.ok(summary.never_commit.includes("raw prompts"));

  const json = buildJsonReport(runs, grades, coverage, readiness);
  assert.equal(json.evidence_readiness.available, true);
  assert.equal(json.evidence_readiness.ashr_current_missing, 6);
  assert.equal(json.evidence_readiness.semantic_offline_reference_only, true);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness);
  assert.match(markdown, /## Evidence Readiness/);
  assert.match(markdown, /Status: awaiting_private_evidence/);
  assert.match(markdown, /Ashr grading missing: 6\/6/);
  assert.match(markdown, /SDK languages covered: python, typescript/);
});

test("A3 report builder summarizes P3 Ashr request provenance", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const requestSample = await loadJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
  const generatedDatasetSummary = await loadJson("../../fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json");

  const summary = summarizeRequestProvenance(requestSample);
  assert.equal(summary.available, true);
  assert.equal(summary.total_requests, 1);
  assert.equal(summary.latest_request.request_status, "failed");
  assert.equal(summary.latest_request.actual_duration_s, 3);
  assert.equal(summary.latest_request.estimated_duration_s, 75);
  assert.deepEqual(summary.latest_request.accepted_input_types, ["audio", "file", "image", "text"]);
  assert.deepEqual(summary.latest_request.generation_outputs, ["generate_audio", "generate_files", "generate_images"]);
  assert.match(summary.latest_request.test_strategy, /^\[REDACTED/);
  assert.equal(summary.latest_request.tool_count, 1);
  assert.equal(summary.latest_request.has_failure, true);

  const json = buildJsonReport(runs, grades, {}, {}, requestSample);
  assert.equal(json.request_provenance.available, true);
  assert.equal(json.request_provenance.latest_request.request_status, "failed");

  const markdown = buildMarkdownReport(runs, grades, {}, {}, requestSample);
  assert.match(markdown, /## Request Provenance/);
  assert.match(markdown, /Accepted inputs: audio, file, image, text/);
  assert.match(markdown, /Generation outputs: generate_audio, generate_files, generate_images/);

  const generated = summarizeRequestProvenance(generatedDatasetSummary);
  assert.equal(generated.available, true);
  assert.equal(generated.total_requests, 1);
  assert.equal(generated.latest_request.request_name, "A3 Refund Demo Dataset");
  assert.equal(generated.latest_request.request_status, "dataset_generated");
  assert.deepEqual(generated.latest_request.accepted_input_types, ["audio", "file", "image", "text"]);
  assert.equal(generated.latest_request.test_strategy, "official_generate_test_suite");
  assert.equal(generated.latest_request.num_variations, 5);
});

test("A3 report builder summarizes P3 Ashr usage and quota calibration", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const usageSample = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");

  const summary = summarizeUsageQuota(usageSample, usageApiProbe);
  assert.equal(summary.available, true);
  assert.deepEqual(summary.channels, ["audio", "files", "images"]);
  assert.equal(summary.direct_api_accessible, false);
  assert.deepEqual(summary.oauth_only_functions, ["billing_get_status", "get_usage"]);
  assert.ok(summary.frontend_source_functions.includes("get_usage"));
  assert.match(summary.guidance, /OAuth-gated/);

  const json = buildJsonReport(runs, grades, {}, {}, {}, usageSample, usageApiProbe);
  assert.equal(json.usage_quota.available, true);
  assert.equal(json.usage_quota.direct_api_accessible, false);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, usageSample, usageApiProbe);
  assert.match(markdown, /## Usage \/ Quota/);
  assert.match(markdown, /OAuth-gated functions: billing_get_status, get_usage/);
});

test("A3 report builder summarizes official Ashr product gap", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const requestSample = await loadJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
  const usageSample = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");

  const gap = summarizeOfficialAshrGap(runs, grades, coverage, requestSample, usageSample, usageApiProbe);
  assert.equal(gap.available, true);
  assert.ok(gap.copied.some((item) => item.area === "Expected vs actual"));
  assert.ok(gap.partial.some((item) => item.area === "Usage / quota" && item.confirmed));
  assert.ok(gap.blocked.some((item) => item.area === "Native failure class"));
  assert.ok(gap.out_of_scope.includes("API key creation or revocation"));
  assert.deepEqual(gap.official_pages.map((page) => page.page), [
    "Datasets",
    "Dataset / Results Detail",
    "Agents",
    "Folders",
    "Analytics",
    "Usage",
    "Trust",
    "API Keys",
    "Team"
  ]);

  const json = buildJsonReport(runs, grades, coverage, {}, requestSample, usageSample, usageApiProbe);
  assert.equal(json.official_ashr_gap.available, true);
  assert.ok(json.official_ashr_gap.official_pages.some((page) => page.page === "Team"));

  const markdown = buildMarkdownReport(runs, grades, coverage, {}, requestSample, usageSample, usageApiProbe);
  assert.match(markdown, /## Official Ashr Gap/);
  assert.match(markdown, /Dataset \/ Results Detail \(\?tab=analysis&dataset=884\): api-summary confirmed, visual pending/);
  assert.match(markdown, /API Keys \(\?tab=api-keys\): out of scope/);
  assert.match(markdown, /Keep A3 as a local read-only triage console/);
});

test("A3 report builder summarizes official frontend mirror clean-room parity", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const frontendMirror = await loadJson("../../fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json");

  const mirror = summarizeOfficialFrontendMirror(frontendMirror);
  assert.equal(mirror.available, true);
  assert.equal(mirror.page_count, 11);
  assert.equal(mirror.api_group_count, 7);
  assert.equal(mirror.api_method_count, 53);
  assert.equal(mirror.safety.official_source_committed, false);
  assert.equal(mirror.safety.secret_values_allowed, false);
  assert.ok(mirror.pages.some((page) => page.label === "Datasets" && page.a3_status === "copy"));
  assert.ok(mirror.pages.some((page) => page.label === "API Keys" && page.a3_status === "out_of_scope"));
  assert.ok(mirror.api_method_groups.some((group) => (
    group.group === "evaluation_core"
    && group.method_count === 10
    && group.a3_status === "copy"
  )));
  assert.ok(mirror.api_method_groups.some((group) => (
    group.group === "observability_voice"
    && group.a3_status === "future"
  )));

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, frontendMirror);
  assert.equal(json.official_frontend_mirror.available, true);
  assert.equal(json.official_frontend_mirror.page_count, 11);
  assert.equal(json.official_frontend_mirror.safety.raw_tokens_allowed, false);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, frontendMirror);
  assert.match(markdown, /## Official Frontend Mirror/);
  assert.match(markdown, /Pages observed: 11/);
  assert.match(markdown, /API evaluation_core: copy, 10 method\(s\)/);
  assert.match(markdown, /Official source committed: no/);
});

test("A3 report builder summarizes official code crawl parity without source leakage", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const frontendCodeCrawl = await loadJson("../../fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json");

  const crawl = summarizeOfficialCodeCrawlParity(frontendCodeCrawl);

  assert.equal(crawl.schema_version, "a3.official_code_crawl_parity.v1");
  assert.equal(crawl.available, true);
  assert.equal(crawl.chunk_count, 9);
  assert.equal(crawl.parity_target_count, 6);
  assert.equal(crawl.safety.official_source_committed, false);
  assert.equal(crawl.safety.raw_source_excerpt_committed, false);
  assert.ok(crawl.chunks.some((chunk) => (
    chunk.chunk === "CreateRequestModal-LwtjGDgm.js"
    && chunk.a3_status === "copy"
    && chunk.top_signals.some((signal) => signal.signal === "expected")
  )));
  assert.ok(crawl.chunks.some((chunk) => (
    chunk.chunk === "ObservabilityPage-BmNyibq8.js"
    && chunk.a3_status === "partial"
    && chunk.top_signals.some((signal) => signal.signal === "trace")
  )));
  assert.ok(crawl.parity_targets.some((target) => (
    target.target === "API keys and team admin"
    && target.a3_status === "out_of_scope"
  )));
  assert.ok(crawl.parity_targets.some((target) => /A1 run/.test(target.a3_dependency)));

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, frontendCodeCrawl);
  assert.equal(json.official_code_crawl_parity.schema_version, "a3.official_code_crawl_parity.v1");
  assert.equal(json.official_code_crawl_parity.safety.official_source_committed, false);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, frontendCodeCrawl);
  assert.match(markdown, /## Official Code Crawl Parity/);
  assert.match(markdown, /CreateRequestModal-LwtjGDgm\.js: copy/);
  assert.match(markdown, /API keys and team admin: out_of_scope/);
  assert.match(markdown, /Official source committed: no/);
});

test("A3 report builder summarizes official parity roadmap and media evidence queue", async () => {
  const runSample = await loadJson("../../fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json");
  const datasetSample = await loadJson("../../fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const requestSample = await loadJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
  const usageSample = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
  const frontendMirror = await loadJson("../../fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json");
  const mapped = mapAshrSampleToA3Fixtures(runSample, {
    datasetSample,
    fixtureId: "p3_official_demo_884_11926_dashboard_sample",
    gradeFixtureId: "p3_official_demo_884_11926_dashboard_grades"
  });

  const runs = mapped.runFixture;
  const grades = mapped.gradeFixture;
  const roadmap = summarizeOfficialParityRoadmap(
    runs,
    grades,
    coverage,
    requestSample,
    usageSample,
    usageApiProbe,
    mediaSignedUrlCoverage,
    frontendMirror
  );
  const media = summarizeMediaReadiness(runs, grades, usageSample, mediaSignedUrlCoverage);

  assert.equal(roadmap.schema_version, "a3.official_parity_roadmap.v1");
  assert.equal(roadmap.available, true);
  assert.ok(roadmap.priorities.some((item) => item.area === "Results review" && item.action === "copy_now"));
  assert.ok(roadmap.priorities.some((item) => item.area === "API keys / team / billing" && item.action === "do_not_copy"));
  assert.ok(roadmap.media_actions.some((item) => item.area === "Media evidence queue" && item.action === "copy_now"));
  assert.ok(roadmap.cloud_admin_boundaries.some((item) => /API-key creation/.test(item)));
  assert.ok(roadmap.next_build_order.some((item) => /Trace\/Observability/.test(item)));
  assert.ok(media.evidence_queue_count > 0);
  assert.ok(media.evidence_queue.some((item) => item.safe_to_render === false && item.preview_policy.includes("metadata")));

  const json = buildJsonReport(runs, grades, coverage, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, {}, {}, frontendMirror);
  assert.equal(json.official_parity_roadmap.schema_version, "a3.official_parity_roadmap.v1");
  assert.ok(json.media_readiness.evidence_queue_count > 0);

  const markdown = buildMarkdownReport(runs, grades, coverage, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, {}, {}, frontendMirror);
  assert.match(markdown, /## Official Parity Roadmap/);
  assert.match(markdown, /### Build Priorities/);
  assert.match(markdown, /API keys \/ team \/ billing: do_not_copy/);
  assert.match(markdown, /Media evidence queue: copy_now/);
});

test("A3 report builder summarizes media readiness and cloud console shell", async () => {
  const rawSample = await loadJson("../../fixtures/a3/p3/ashr_run_detail_sample.redacted.json");
  const usageSample = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
  const requestSample = await loadJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
  const authSample = await loadJson("../../fixtures/a3/p3/ashr_auth_check.redacted.json");
  const frontendSummary = await loadJson("../../fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json");
  const mapped = mapAshrSampleToA3Fixtures(rawSample);

  const runs = mapped.runFixture;
  const grades = mapped.gradeFixture;

  const media = summarizeMediaReadiness(runs, grades, usageSample, mediaSignedUrlCoverage);
  assert.equal(media.available, true);
  assert.equal(media.live_rendering_allowed, false);
  assert.ok(media.channels.includes("audio"));
  assert.ok(media.channels.includes("files"));
  assert.deepEqual(media.signed_url_confirmed_types, ["files"]);
  assert.ok(media.signed_url_unconfirmed_types.includes("audio"));
  assert.ok(media.channel_matrix.some((channel) => (
    channel.channel === "files"
    && channel.signed_url_confirmed === true
    && channel.live_preview_allowed === false
  )));
  assert.ok(media.channel_matrix.some((channel) => (
    channel.channel === "audio"
    && channel.signed_url_unconfirmed === true
  )));
  assert.match(media.guidance, /metadata only/);

  const cloud = summarizeCloudConsoleShell(authSample, frontendSummary, requestSample, usageSample, usageApiProbe);
  assert.equal(cloud.available, true);
  assert.equal(cloud.auth_observed, true);
  assert.equal(cloud.frontend_session_observed, true);
  assert.equal(cloud.real_mutations_enabled, false);
  assert.equal(cloud.secret_values_allowed, false);
  assert.ok(cloud.sections.some((section) => section.area === "API keys" && section.status === "disabled"));
  assert.ok(cloud.actions.some((action) => action.action === "Export JSON / CSV / Markdown" && action.enabled));
  assert.ok(cloud.actions.some((action) => action.action === "Generate / revoke API key" && !action.enabled));
  assert.ok(cloud.actions.some((action) => action.action === "Invite teammate" && action.mode === "disabled"));
  assert.ok(cloud.observed_pages.includes("Usage"));

  const json = buildJsonReport(runs, grades, {}, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, authSample, frontendSummary);
  assert.equal(json.media_readiness.live_rendering_allowed, false);
  assert.ok(json.media_readiness.channel_matrix.length >= 4);
  assert.ok(json.media_readiness.evidence_queue_count > 0);
  assert.equal(json.cloud_console_shell.real_mutations_enabled, false);
  assert.ok(json.cloud_console_shell.actions.length >= 10);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, requestSample, usageSample, usageApiProbe, mediaSignedUrlCoverage, authSample, frontendSummary);
  assert.match(markdown, /## Media Readiness/);
  assert.match(markdown, /Live rendering allowed: no/);
  assert.match(markdown, /## Cloud Console Shell/);
  assert.match(markdown, /API keys: disabled/);
  assert.match(markdown, /### Cloud Action Guardrails/);
  assert.match(markdown, /Generate \/ revoke API key: disabled/);
});
