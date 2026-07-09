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
  summarizeA2CrossLaneSecurityContext,
  summarizeA2ReleaseUnblockChecklist,
  summarizeA2ResultPersistence,
  summarizeA2SqlStoreReport,
  summarizeCommercialReadiness,
  summarizeArtifactRegistryExport,
  summarizeCoverage,
  summarizeCloudConsoleShell,
  summarizeEvidenceReadiness,
  summarizeGithubPublishEvidence,
  summarizeMediaReadiness,
  summarizeRegressionReadiness,
  summarizeOfficialAshrGap,
  summarizeOfficialCodeCrawlParity,
  summarizeOfficialFrontendMirror,
  summarizeOfficialParityRoadmap,
  summarizeObservabilityReplayMatrix,
  summarizeProductConsoleExport,
  summarizeReviewWorkflowExport,
  summarizeSaasAdminExport,
  summarizeBillingUsage,
  summarizeBillingMigrationReadiness,
  summarizeRegressionFactory,
  summarizeExportRedactionFirewall,
  summarizeIncidentReplayQueue,
  summarizeReviewerWorkflowBoard,
  summarizeReleaseEvidenceSummary,
  summarizeReleaseGate,
  summarizeReleaseWarRoom,
  summarizeReleaseWorkflow,
  summarizeRequestProvenance,
  summarizeUsageQuota
} from "../../services/report/report_builder.mjs";
import { buildA3UsageLedger } from "../../services/report/a3_usage_ledger.mjs";
import { buildA3ProductConsole } from "../../services/report/a3_product_console.mjs";
import { buildA3ArtifactRegistry } from "../../services/report/a3_artifact_registry.mjs";
import { buildSaasAdminConsole } from "../../services/report/a3_saas_admin.mjs";
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

test("A3 observability replay matrix packages trace, error, judge, media, and official Observability signals", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
  const frontendCodeCrawl = await loadJson("../../fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json");

  const matrix = summarizeObservabilityReplayMatrix(riskyRuns, riskyGrades, mediaSignedUrlCoverage, frontendCodeCrawl);

  assert.equal(matrix.schema_version, "a3.observability_replay_matrix.v1");
  assert.equal(matrix.available, true);
  assert.ok(matrix.replay_case_count > 0);
  assert.ok(matrix.trace_ready_count > 0);
  assert.ok(matrix.tool_error_case_count > 0);
  assert.ok(matrix.judge_linked_count > 0);
  assert.equal(matrix.official_observability_confirmed, true);
  assert.ok(matrix.official_observability_chunks.some((chunk) => /ObservabilityPage/.test(chunk)));
  assert.ok(matrix.lanes.some((lane) => lane.lane === "Trace Timeline" && lane.ready_count > 0));
  assert.ok(matrix.lanes.some((lane) => lane.lane === "A2 Judge Link" && lane.ready_count > 0));
  assert.ok(matrix.lanes.some((lane) => lane.lane === "Official Observability Parity" && lane.status === "mapped"));
  assert.ok(matrix.items.some((item) => item.production_risk === "blocker"));
  assert.ok(matrix.items.some((item) => item.trace_event_count > 0));
  assert.ok(matrix.items.some((item) => item.judge_evidence_count > 0));
  assert.ok(matrix.items.some((item) => /ObservabilityPage/.test(item.official_parity_source)));
  assert.ok(matrix.replay_steps.some((step) => /A1 trace/.test(step)));
  assert.ok(matrix.replay_steps.some((step) => /A2 judge/.test(step)));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage, {}, {}, {}, frontendCodeCrawl);
  assert.equal(json.observability_replay_matrix.schema_version, "a3.observability_replay_matrix.v1");
  assert.equal(json.observability_replay_matrix.official_observability_confirmed, true);

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage, {}, {}, {}, frontendCodeCrawl);
  assert.match(markdown, /## Observability Replay Matrix/);
  assert.match(markdown, /Official observability confirmed: yes/);
  assert.match(markdown, /Trace Timeline/);
});

test("A3 regression factory turns replay failures into A1/A2 calibrated regression candidates", async () => {
  const riskyRuns = await loadJson("../../fixtures/a3/mock_run_results.json");
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const mediaSignedUrlCoverage = await loadJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
  const frontendCodeCrawl = await loadJson("../../fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json");

  const factory = summarizeRegressionFactory(riskyRuns, riskyGrades, coverage, mediaSignedUrlCoverage, frontendCodeCrawl);

  assert.equal(factory.schema_version, "a3.regression_factory.v1");
  assert.equal(factory.available, true);
  assert.ok(factory.candidate_count > 0);
  assert.ok(factory.blocked_count > 0);
  assert.ok(factory.tool_candidate_count > 0);
  assert.equal(factory.official_results_review_confirmed, true);
  assert.ok(factory.lanes.some((lane) => lane.lane === "A1 Trace Capture" && lane.ready_count > 0));
  assert.ok(factory.lanes.some((lane) => lane.lane === "A2 Judge Contract" && lane.ready_count > 0));
  assert.ok(factory.lanes.some((lane) => lane.lane === "Official Results Parity" && lane.status === "ready"));
  assert.ok(factory.candidates.some((item) => item.required_contracts.includes("a1_trace_events")));
  assert.ok(factory.candidates.some((item) => item.required_contracts.includes("a2_judge_evidence")));
  assert.ok(factory.candidates.some((item) => item.proposed_assertions.some((assertion) => assertion.startsWith("assert_failure_class:"))));
  assert.ok(factory.promotion_steps.some((step) => /A1 trace/.test(step)));
  assert.ok(factory.promotion_steps.some((step) => /A2 judge/.test(step)));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage, {}, {}, {}, frontendCodeCrawl);
  assert.equal(json.regression_factory.schema_version, "a3.regression_factory.v1");
  assert.equal(json.regression_factory.official_results_review_confirmed, true);

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage, {}, {}, {}, {}, mediaSignedUrlCoverage, {}, {}, {}, frontendCodeCrawl);
  assert.match(markdown, /## Regression Factory/);
  assert.match(markdown, /Generated Suite Plan/);
  assert.match(markdown, /Official Results review confirmed: yes/);
});

test("A3 export redaction firewall scrubs report exports and hardens CSV cells", async () => {
  const riskyRuns = JSON.parse(JSON.stringify(await loadJson("../../fixtures/a3/mock_run_results.json")));
  const riskyGrades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const email = ["release.owner", "example.com"].join("@");
  const apiKeyAssignment = ["ASHR_API_KEY", "secret-value"].join("=");
  const bearerValue = ["Bearer", "abc.def"].join(" ");
  const cookieValue = ["Cookie", ": session=secret"].join("");
  const signedUrl = ["https://media.example.invalid/file?", "Sign", "ature=secret"].join("");
  const formulaTitle = "=SUM(1,1)";
  const firstCase = riskyRuns.runs[0].cases[0];

  firstCase.title = formulaTitle;
  firstCase.failure_summary = `${email} ${apiKeyAssignment}`;
  firstCase.expected = {
    ...firstCase.expected,
    final_response: bearerValue
  };
  firstCase.actual = {
    ...firstCase.actual,
    final_response: signedUrl,
    tool_calls: [{
      id: "tc-redaction-smoke",
      name: "refund_order",
      arguments: {
        header: cookieValue
      }
    }]
  };

  const firewall = summarizeExportRedactionFirewall(riskyRuns, riskyGrades, coverage);
  assert.equal(firewall.schema_version, "a3.export_redaction_firewall.v1");
  assert.equal(firewall.secret_free_exports, true);
  assert.ok(firewall.replacement_count >= 5);
  assert.ok(firewall.checked_surfaces.some((surface) => surface.surface === "json_report"));
  assert.ok(firewall.checked_surfaces.some((surface) => surface.surface === "csv_report" && surface.rules_triggered.includes("csv_formula_injection")));

  const json = buildJsonReport(riskyRuns, riskyGrades, coverage);
  const jsonText = JSON.stringify(json);
  assert.equal(jsonText.includes(email), false);
  assert.equal(jsonText.includes("secret-value"), false);
  assert.equal(jsonText.includes(bearerValue), false);
  assert.equal(jsonText.includes(cookieValue), false);
  assert.equal(jsonText.includes(signedUrl), false);
  assert.equal(json.export_redaction_firewall.schema_version, "a3.export_redaction_firewall.v1");

  const markdown = buildMarkdownReport(riskyRuns, riskyGrades, coverage);
  assert.equal(markdown.includes(email), false);
  assert.equal(markdown.includes("secret-value"), false);
  assert.match(markdown, /## Export Redaction Firewall/);

  const csv = buildCsvReport(riskyRuns, riskyGrades);
  assert.equal(csv.includes(email), false);
  assert.equal(csv.includes("secret-value"), false);
  assert.equal(csv.includes(`"${formulaTitle}`), false);
  assert.ok(csv.includes(`"'${formulaTitle}`));
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

test("A3 report builder can consume raw A1 RunResult evidence directly", async () => {
  const a1Run = await loadJson("../../docs/a1/evidence/local_run_30.json");

  const summary = buildDashboardSummary(a1Run, {});
  const cases = normalizeCases(a1Run, {});
  const diffs = buildToolCallDiffs(cases[0]);

  assert.equal(summary.totalRuns, 1);
  assert.equal(summary.totalCases, 30);
  assert.equal(cases[0].run_id, a1Run.run_id);
  assert.equal(cases[0].actual.tool_calls.length, 1);
  assert.equal(cases[0].expected.tool_calls.length, 1);
  assert.ok(cases[0].trace_events.length > 0);
  assert.deepEqual(cases[0].media_evidence.media_types, []);
  assert.ok(diffs.length > 0);
});

test("A3 report builder can consume raw A2 run and single local judge result directly", async () => {
  const a2Run = await loadJson("../../fixtures/a2/runs/a2_s004_missing_tool.json");
  const a2Grade = await loadJson("../../fixtures/a2/results/a2_s004_missing_tool_grade.json");

  const summary = buildDashboardSummary(a2Run, a2Grade);
  const cases = normalizeCases(a2Run, a2Grade);
  const json = buildJsonReport(a2Run, a2Grade);

  assert.equal(summary.totalRuns, 1);
  assert.equal(summary.totalCases, 1);
  assert.equal(cases[0].case_id, a2Run.case_id);
  assert.equal(cases[0].scenario_id, a2Run.scenario_id);
  assert.equal(cases[0].passed, false);
  assert.equal(cases[0].score, 71);
  assert.equal(cases[0].primary_failure_class, "missing_required_tool");
  assert.match(cases[0].failure_summary, /Required tool missing/);
  assert.equal(cases[0].actual.final_response, a2Run.run.final_response);
  assert.equal(json.cases[0].primary_failure_class, "missing_required_tool");
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

test("A3 report exports include Product Console onboarding, project, and audit state", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const productConsole = buildA3ProductConsole({ source: "mock", runFixture: runs, gradeFixture: grades }, {
    reportCenter: {
      summary: { report_count: 1, manifest_ready_count: 1, total_view_count: 2 },
      reports: [{ report_id: "a3r_export", status: "shareable" }]
    },
    auditEvents: [{ event_type: "report_share_link_viewed", report_id: "a3r_export", access_result: "allowed" }]
  });

  const summary = summarizeProductConsoleExport(productConsole);
  assert.equal(summary.available, true);
  assert.equal(summary.onboarding.total_steps, 10);
  assert.ok(summary.project_console.case_count > 0);
  assert.ok(summary.audit_log.event_count > 0);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, productConsole);
  assert.equal(json.product_console.schema_version, "a3.product_console_export.v1");
  assert.equal(json.product_console.available, true);
  assert.equal(json.product_console.project_console.report_count, 1);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, productConsole);
  assert.match(markdown, /## Product Console \/ Onboarding \/ Audit/);
  assert.match(markdown, /Commercial readiness:/);

  const missing = summarizeProductConsoleExport({});
  assert.equal(missing.available, false);
  assert.match(missing.recommendation, /Attach Product Console/);
});

test("A3 report exports include SaaS admin login, team, API-key, usage, trust, and cloud guardrails", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const saasAdmin = buildSaasAdminConsole({
    runFixture: runs,
    gradeFixture: grades,
    source: "mock"
  });

  const summary = summarizeSaasAdminExport(saasAdmin);
  assert.equal(summary.available, true);
  assert.equal(summary.login.user_identity_redacted, true);
  assert.equal(summary.team.member_count, 4);
  assert.equal(summary.api_keys.status, "metadata_only");
  assert.equal(summary.trust.public_publish_enabled, false);
  assert.equal(summary.cloud_management.real_mutations_enabled, false);
  assert.equal(summary.a1_a2_compatibility.a1_run_result_ready, true);
  assert.equal(summary.a1_a2_compatibility.a2_grade_result_ready, true);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, saasAdmin);
  assert.equal(json.saas_admin_console.schema_version, "a3.saas_admin_export.v1");
  assert.equal(json.saas_admin_console.safety.secret_values_allowed, false);
  assert.ok(json.saas_admin_console.action_plans.every((item) => item.writes_real_ashr_cloud === false));

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, saasAdmin);
  assert.match(markdown, /## SaaS Admin \/ Login \/ Team \/ Trust/);
  assert.match(markdown, /API keys:/);
  assert.match(markdown, /real cloud write no/);

  const missing = summarizeSaasAdminExport({});
  assert.equal(missing.available, false);
  assert.match(missing.recommendation, /Attach SaaS Admin Console/);
});

test("A3 report exports include Artifact Registry evidence catalog", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const billingMigrationReadiness = await loadJson("../../fixtures/a3/p3/a3_billing_migration_readiness.redacted.json");
  const artifactRegistry = buildA3ArtifactRegistry({
    source: "mock",
    reportCenter: {
      source: "mock",
      reports: [{
        report_id: "a3r_export",
        source: "mock",
        status: "shareable",
        share_link: { scope: "private_link", token_hash_prefix: "abc123def456" },
        redaction: { status: "passed", blocked: false },
        sealed_evidence: { payload_hash_present: true, secret_free: true },
        manifest: { missing: [], redaction_status: "passed" }
      }]
    },
    usageLedger: { schema_version: "a3.usage_ledger.v1", meters: [{ meter: "runs", quantity: 1 }] },
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", status: "contract_ready", migration_count: 7 },
    productConsole: { schema_version: "a3.product_console.v1" },
    saasAdmin: { schema_version: "a3.saas_admin_console.v1" },
    billingMigrationReadiness
  });

  const summary = summarizeArtifactRegistryExport(artifactRegistry);
  assert.equal(summary.available, true);
  assert.ok(summary.artifact_count >= 8);
  assert.equal(summary.safety.raw_secret_values_allowed, false);
  assert.equal(summary.safety.raw_share_tokens_stored, false);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, artifactRegistry);
  assert.equal(json.artifact_registry.schema_version, "a3.artifact_registry_export.v1");
  assert.equal(json.artifact_registry.available, true);
  assert.ok(json.artifact_registry.top_artifacts.some((item) => item.artifact_type === "hosted_report"));
  const billingArtifact = json.artifact_registry.top_artifacts.find((item) => item.artifact_type === "billing_migration_readiness");
  assert.equal(billingArtifact.lifecycle_state, "generated");
  assert.equal(billingArtifact.missing_controls.includes("a1_authenticated_billing_ledger_read_api"), true);
  assert.match(billingArtifact.customer_value, /billing ledger migration readiness/);
  assert.match(billingArtifact.billable_value, /invoice-preview/);
  assert.match(billingArtifact.self_host_value, /Postgres billing ledger/);
  assert.match(billingArtifact.audit_value, /provider-event hash/);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, artifactRegistry);
  assert.match(markdown, /## Artifact Registry/);
  assert.match(markdown, /Artifact Packet Presets/);
  assert.match(markdown, /billing_migration_readiness/);

  const missing = summarizeArtifactRegistryExport({});
  assert.equal(missing.available, false);
  assert.match(missing.recommendation, /Attach Artifact Registry/);
});

test("A3 report exports include billing migration readiness without leaking provider secrets", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const billingMigrationReadiness = await loadJson("../../fixtures/a3/p3/a3_billing_migration_readiness.redacted.json");
  const unsafeProbe = {
    ...billingMigrationReadiness,
    ignored_provider_secret: "sk_live_should_not_escape_1234567890",
    ignored_webhook_secret: "whsec_should_not_escape_1234567890",
    ignored_email: "billing-owner@example.com",
    ignored_path: "C:\\Users\\private\\billing.env",
    ignored_header: "Authorization: Bearer should-not-escape"
  };

  const summary = summarizeBillingMigrationReadiness(unsafeProbe);
  assert.equal(summary.schema_version, "a3.billing_migration_readiness_export.v1");
  assert.equal(summary.source_schema_version, "a3.billing_migration_readiness.v1");
  assert.equal(summary.available, true);
  assert.equal(summary.status, "read_only_migration_contract_ready");
  assert.equal(summary.ready_for_live_customer_billing, false);
  assert.equal(summary.db_contract.table_names.includes("billing_provider_events"), true);
  assert.equal(summary.db_contract.a3_db_mutation_required, false);
  assert.equal(summary.replay_evidence.raw_payload_included, false);
  assert.equal(summary.boundary.billing_mutations_enabled, false);
  assert.equal(summary.safety.env_local_read, false);
  assert.equal(summary.missing_controls.includes("hosted_auth_rbac_enforcement"), true);
  assert.match(summary.customer_value, /billing-ledger migration readiness/);
  assert.match(summary.self_host_value, /Postgres migration/);
  assert.match(summary.audit_value, /tenant-scope/);

  const json = buildJsonReport(...[
    runs,
    grades,
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
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    unsafeProbe
  ]);
  assert.equal(json.billing_migration_readiness.available, true);
  assert.equal(json.billing_migration_readiness.ready_for_live_customer_billing, false);
  assert.equal(json.billing_migration_readiness.db_contract.raw_provider_secret_allowed, false);
  assert.equal(json.billing_migration_readiness.live_smoke.executed_by_a3, false);
  assert.equal(json.billing_migration_readiness.official_api_readonly.mutating_steps, 0);

  const markdown = buildMarkdownReport(...[
    runs,
    grades,
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
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    unsafeProbe
  ]);
  assert.match(markdown, /## Billing Migration Readiness/);
  assert.match(markdown, /Live customer billing ready: no/);
  assert.match(markdown, /billing_accounts, billing_provider_events, billing_ledger_events/);
  assert.match(markdown, /Billing mutations enabled: no/);

  const serialized = JSON.stringify(json) + markdown + JSON.stringify(summary);
  assert.doesNotMatch(serialized, /sk_live_should_not_escape|whsec_should_not_escape|billing-owner@example\.com|C:\\Users|Authorization: Bearer/);
});

test("A3 report exports include durable review workflow records", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const reviewWorkflow = {
    schema_version: "a3.review_workflow_index.v1",
    source: "mock",
    record_count: 3,
    waiver_count: 1,
    approval_count: 1,
    denial_count: 1,
    human_action_count: 3,
    accepted_count: 3,
    durable_storage_ready: true,
    real_cloud_mutations_performed: false,
    records: [{
      record_id: "rwr_waiver_unit",
      record_type: "waiver",
      status: "valid_exceptional_waiver",
      accepted: true,
      run_id: "run_a3_generated_from_a2_g3",
      payload_hash: "a".repeat(64),
      review_hash: "b".repeat(64),
      signature: { status: "hash_sealed_unsigned_record" }
    }, {
      record_id: "rwr_approval_unit",
      record_type: "approval",
      status: "valid_exception_approval",
      accepted: true,
      run_id: "run_a3_generated_from_a2_g3",
      payload_hash: "c".repeat(64),
      review_hash: "d".repeat(64),
      signature: { status: "hash_sealed_signer_record" }
    }, {
      record_id: "rwr_denial_unit",
      record_type: "denial",
      status: "valid_denial",
      accepted: true,
      run_id: "run_a3_generated_from_a2_g3",
      payload_hash: "e".repeat(64),
      review_hash: "f".repeat(64),
      subject: { decision: "deny_release" },
      signature: { status: "hash_sealed_signer_record" }
    }]
  };

  const summary = summarizeReviewWorkflowExport(reviewWorkflow);
  assert.equal(summary.available, true);
  assert.equal(summary.record_count, 3);
  assert.equal(summary.denial_count, 1);
  assert.equal(summary.human_action_count, 3);
  assert.equal(summary.durable_storage_ready, true);
  assert.equal(summary.real_cloud_mutations_performed, false);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, reviewWorkflow);
  assert.equal(json.review_workflow.schema_version, "a3.review_workflow_export.v1");
  assert.equal(json.review_workflow.accepted_count, 3);
  assert.equal(json.review_workflow.denial_count, 1);
  assert.equal(json.review_workflow.latest_records[2].subject_decision, "deny_release");

  const missing = summarizeReviewWorkflowExport({});
  assert.equal(missing.available, false);
  assert.match(missing.recommendation, /Review Workflow API/);
});

test("A3 report exports include release evidence publish and verification summary", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const releaseEvidence = {
    githubCheckPublishReceipt: await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
    githubPrCommentPublishReceipt: await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
    githubRequiredCheckPlan: await loadJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json"),
    githubCheckReadback: await loadJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json"),
    githubPrCommentReadback: await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json"),
    githubRequiredCheckProof: await loadJson("../../fixtures/a3/p3/a3_github_required_check_proof_plan_only.redacted.json"),
    auditBundleVerification: await loadJson("../../fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json"),
    auditArchiveVerification: await loadJson("../../fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json")
  };
  releaseEvidence.readback_records = [
    releaseEvidence.githubCheckReadback,
    releaseEvidence.githubPrCommentReadback,
    releaseEvidence.githubRequiredCheckProof
  ];

  const summary = summarizeReleaseEvidenceSummary(releaseEvidence);
  assert.equal(summary.schema_version, "a3.release_evidence_summary.v1");
  assert.equal(summary.available, true);
  assert.equal(summary.overall_status, "verified");
  assert.equal(summary.github_check_publish.dry_run, true);
  assert.equal(summary.github_check_publish.posted, false);
  assert.equal(summary.github_pr_comment_publish.dry_run, true);
  assert.equal(summary.github_pr_comment_publish.posted, false);
  assert.equal(summary.github_required_check_plan.maintainer_approval_required, true);
  assert.equal(summary.github_check_readback.readback_status, "readback_confirmed");
  assert.equal(summary.pr_comment_readback.body_hash_match, true);
  assert.equal(summary.required_check_proof.plan_only_must_not_claim_enforcement, true);
  assert.equal(summary.readback_record_count, 3);
  assert.equal(summary.readback_status_counts.readback_confirmed, 2);
  assert.equal(summary.readback_status_counts.plan_only, 1);
  assert.equal(summary.readback_resource_counts.github_check, 1);
  assert.equal(summary.audit_bundle_verification.status, "passed");
  assert.equal(summary.audit_bundle_verification.root_hash_passed, true);
  assert.equal(summary.audit_archive_verification.status, "passed");
  assert.equal(summary.audit_archive_verification.signature_passed, true);
  assert.equal(summary.safety.token_included, false);
  assert.equal(summary.safety.real_github_mutation_performed, false);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, releaseEvidence);
  assert.equal(json.release_evidence_summary.available, true);
  assert.equal(json.release_evidence_summary.audit_archive_verification.signature_passed, true);
  assert.equal(json.release_evidence_summary.readback_record_count, 3);
  assert.equal(json.release_evidence_summary.readback_records[0].resource_kind, "github_check");
  assert.match(json.release_evidence_summary.readback_history.a1_a2_boundary, /A1 RunResult/);
  assert.doesNotMatch(JSON.stringify(json.release_evidence_summary), /scrape saved browser passwords/);
  assert.doesNotMatch(JSON.stringify(json.release_evidence_summary), /raw_details/);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, releaseEvidence);
  assert.match(markdown, /## Release Evidence Summary/);
  assert.match(markdown, /GitHub check readback: readback_confirmed/);
  assert.match(markdown, /PR comment readback: readback_confirmed/);
  assert.match(markdown, /Required check readback: plan_only/);
  assert.match(markdown, /Readback records: 3, confirmed 2/);
  assert.match(markdown, /Audit bundle verification: passed/);
  assert.match(markdown, /Audit archive verification: passed/);
  assert.match(markdown, /real GitHub mutation no/);

  const missing = summarizeReleaseEvidenceSummary({});
  assert.equal(missing.available, false);
  assert.match(missing.recommendation, /GitHub publish receipts/);
});

test("A3 report exports include GitHub publish evidence receipts", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const githubPublishEvidence = {
    schema_version: "a3.github_publish_evidence.v1",
    check_publish: await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
    pr_comment_publish: await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
    required_check_plan: await loadJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json")
  };

  const summary = summarizeGithubPublishEvidence(githubPublishEvidence);
  assert.equal(summary.available, true);
  assert.equal(summary.status, "planned");
  assert.equal(summary.dry_run_only, true);
  assert.equal(summary.posted_count, 0);
  assert.equal(summary.planned_count, 3);
  assert.equal(summary.required_check_planned, true);
  assert.equal(summary.check_name, "Ashr++ Release Gate");
  assert.equal(summary.safety.token_included, false);
  assert.equal(summary.safety.secret_values_allowed, false);

  const json = buildJsonReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, githubPublishEvidence);
  assert.equal(json.github_publish_evidence.schema_version, "a3.github_publish_evidence_export.v1");
  assert.equal(json.github_publish_evidence.required_check_planned, true);
  assert.equal(json.github_publish_evidence.pr_comment_publish.status, "planned");

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, githubPublishEvidence);
  assert.match(markdown, /## GitHub Publish Evidence/);
  assert.match(markdown, /Required check planned: yes/);
  assert.doesNotMatch(JSON.stringify(json.github_publish_evidence), /Authorization|Bearer|gh[pousr]_/);
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
  assert.equal(summary.capability_axis_counts.tool_choice_and_policy, 60);
  assert.equal(summary.capability_axis_counts.multi_step_workflow, 15);
  assert.equal(summary.capability_axis_counts.trace_contract, 32);
  assert.equal(summary.capability_axis_counts.media_and_multimodal, 2);
  assert.ok(summary.capability_axis_counts.enterprise_saas_operations >= 8);
  assert.equal(summary.capability_axis_checks.media_and_multimodal, true);
  assert.equal(summary.capability_axis_checks.enterprise_saas_operations, true);
  assert.equal(Object.keys(summary.capability_axis_exemplars).length, 11);
  assert.ok(summary.capability_axis_exemplars.media_and_multimodal.some((item) => (
    item.scenario_id === "A2-S031"
  )));
  assert.ok(summary.capability_axis_exemplars.enterprise_saas_operations.some((item) => (
    item.why_it_matters.includes("enterprise SaaS workflow")
  )));
  assert.match(
    summary.capability_axis_exemplars.media_and_multimodal[0].why_it_matters,
    /Evidence signals:/
  );
  assert.deepEqual(summary.missing_capability_axes, []);
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
  assert.match(markdown, /Scenario dimensions met: 17\/17/);
  assert.match(markdown, /Capability axes met: 11\/11/);
  assert.match(markdown, /### Capability Axis Exemplars/);
  assert.match(markdown, /media_and_multimodal: A2-S031/);
  assert.match(markdown, /enterprise_saas_operations:/);
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

  const readinessWithOfficialApi = {
    ...readiness,
    a1_official_api_readonly_manifest: {
      available: true,
      status: "ready",
      read_step_count: 7,
      ok_or_planned_step_count: 6,
      error_step_count: 1,
      quota_block_count: 0,
      modalities: ["text", "image"],
      step_ids: ["list_runs", "get_run"],
      public_safe: true,
      redacted_summary_fields_only: true,
      raw_payload_values_included: false,
      ready_for_a2_evidence_context: true
    },
    a1_official_api_mutating_index: {
      available: true,
      public_safe: true,
      raw_payloads_included: false,
      secret_values_included: false,
      record_count: 4,
      status_counts: { ok: 2, blocked: 2 },
      modalities: ["text", "audio"],
      mutating_step_ids: ["create_request", "create_run"],
      observed_error_kinds: ["quota"],
      total_steps: 8,
      read_step_count: 4,
      mutating_step_count: 4,
      quota_block_count: 2,
      private_manifest_count: 2,
      ready_for_a2_evidence_context: true,
      c3_grading_ready: false
    },
    a1_official_api_paid_media_summary: {
      available: true,
      status: "quota_blocked",
      mode: "small_batch",
      public_safe: true,
      redacted_summary_fields_only: true,
      raw_payload_values_included: false,
      guardrails: {
        quota_gate_present: true,
        raw_records_private: true
      },
      total_step_count: 5,
      read_step_count: 2,
      mutating_step_count: 3,
      ok_or_planned_step_count: 3,
      error_step_count: 2,
      quota_block_count: 2,
      estimated_call_count: 5,
      modalities: ["image", "audio"],
      step_ids: ["media-image-smoke", "media-audio-smoke"],
      mutating_functions: ["create_request"],
      mutating_modalities: ["image"],
      quota_blocked_step_ids: ["media-image-smoke"],
      quota_remaining_observed: true,
      status_code_counts: { 200: 2, 429: 2 },
      ready_for_a2_evidence_context: true,
      safe_for_paid_media_claims: false,
      c3_grading_ready: false
    }
  };
  const officialSummary = summarizeEvidenceReadiness(readinessWithOfficialApi);
  assert.equal(officialSummary.official_api_readonly_available, true);
  assert.equal(officialSummary.official_api_readonly_ready_for_a2_evidence_context, true);
  assert.deepEqual(officialSummary.official_api_readonly_modalities, ["text", "image"]);
  assert.equal(officialSummary.official_api_mutating_record_count, 4);
  assert.equal(officialSummary.official_api_mutating_secret_values_included, false);
  assert.equal(officialSummary.official_api_mutating_quota_block_count, 2);
  assert.equal(officialSummary.official_api_paid_media_status, "quota_blocked");
  assert.equal(officialSummary.official_api_paid_media_estimated_call_count, 5);
  assert.equal(officialSummary.official_api_paid_media_safe_for_paid_media_claims, false);
  assert.equal(officialSummary.official_api_paid_media_guardrails.raw_records_private, true);

  const json = buildJsonReport(runs, grades, coverage, readiness);
  assert.equal(json.evidence_readiness.available, true);
  assert.equal(json.evidence_readiness.ashr_current_missing, 6);
  assert.equal(json.evidence_readiness.semantic_offline_reference_only, true);
  const officialJson = buildJsonReport(runs, grades, coverage, readinessWithOfficialApi);
  assert.equal(officialJson.evidence_readiness.official_api_mutating_record_count, 4);
  assert.equal(officialJson.evidence_readiness.official_api_paid_media_quota_block_count, 2);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness);
  assert.match(markdown, /## Evidence Readiness/);
  assert.match(markdown, /Status: awaiting_private_evidence/);
  assert.match(markdown, /Ashr grading missing: 6\/6/);
  assert.match(markdown, /SDK languages covered: python, typescript/);
  const officialMarkdown = buildMarkdownReport(runs, grades, coverage, readinessWithOfficialApi);
  assert.match(officialMarkdown, /Official API readonly: ready \/ A2 context ready/);
  assert.match(officialMarkdown, /Official API mutating: records 4, quota blocks 2, raw payloads not included/);
  assert.match(officialMarkdown, /Official paid media: quota_blocked \/ safe claims no \/ estimated calls 5/);
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

  const billing = summarizeBillingUsage(runs, grades, usageSample, usageApiProbe, {
    plan: {
      plan_id: "plan-growth",
      plan_name: "Growth",
      included_unit_count: 10,
      overage_enabled: true
    }
  });
  assert.equal(billing.schema_version, "a3.billing_usage_summary.v1");
  assert.equal(billing.plan.plan_name, "Growth");
  assert.equal(billing.quota.included_units, 10);
  assert.ok(billing.billable_meters.some((item) => item.meter === "cases" && item.billable));
  assert.equal(billing.overage_risk.status, "over_quota");
  assert.equal(billing.evidence_counts.a1.runs, 1);
  assert.equal(billing.evidence_counts.a1.cases, 32);
  assert.ok(billing.evidence_counts.a2.judge_results > 0);

  const json = buildJsonReport(runs, grades, {}, {}, {}, usageSample, usageApiProbe);
  assert.equal(json.usage_quota.available, true);
  assert.equal(json.usage_quota.direct_api_accessible, false);
  assert.equal(json.billing_usage_summary.available, true);
  assert.equal(json.billing_usage_summary.plan.plan_name, "frontend-observed-plan");
  assert.equal(json.billing_usage_summary.billing_mutations_enabled, false);
  assert.equal(json.billing_usage_summary.evidence_counts.a1.cases, 32);

  const markdown = buildMarkdownReport(runs, grades, {}, {}, {}, usageSample, usageApiProbe);
  assert.match(markdown, /## Usage \/ Quota/);
  assert.match(markdown, /OAuth-gated functions: billing_get_status, get_usage/);
  assert.match(markdown, /## Billing \/ Usage Summary/);
  assert.match(markdown, /A1 evidence: runs 1, cases 32/);
});

test("A3 usage ledger exposes read-only plan, quota, billable meters, overage risk, and A1/A2 evidence counts", () => {
  const ledger = buildA3UsageLedger({
    runFixture: {
      runs: [{
        run_id: "run-billing-ledger",
        cases: [{
          case_id: "case-billing-ledger",
          status: "failed",
          trace_events: [{ event_type: "tool_call" }, { event_type: "observation" }],
          observations: [{ event_type: "artifact.write" }],
          actual: { tool_calls: [{ name: "refund_order" }] }
        }]
      }]
    },
    gradeFixture: {
      grade_results: [{
        case_id: "case-billing-ledger",
        passed: false,
        score: 0.2,
        primary_failure_class: "wrong_tool",
        judge_results: [
          { judge_mode: "deterministic", passed: false },
          { judge_mode: "semantic", passed: false }
        ]
      }]
    }
  }, {
    plan: {
      plan_id: "plan-starter",
      plan_name: "Starter",
      included_unit_count: 4,
      overage_enabled: true
    },
    reports: [{ report_id: "a3r_billing" }],
    auditEvents: [{ event_type: "report_view" }, { event_type: "report_revoke" }],
    releaseEvidenceReadbacks: [{ readback_id: "rerb_billing", readback_status: "readback_confirmed" }],
    importReceipts: [
      { schema_version: "a3.a1_run_result_ingest.v1" },
      { schema_version: "a3.a2_grade_result_ingest.v1" }
    ]
  });

  assert.equal(ledger.schema_version, "a3.usage_ledger.v1");
  assert.equal(ledger.billing_mutations_enabled, false);
  assert.equal(ledger.plan.plan_name, "Starter");
  assert.equal(ledger.quota.included_units, 4);
  assert.ok(ledger.billable_unit_count > ledger.quota.included_units);
  assert.equal(ledger.overage_risk.status, "over_quota");
  assert.ok(ledger.billable_meters.some((item) => item.meter === "judge_results" && item.billable_units === 2));
  assert.equal(ledger.evidence_counts.a1.runs, 1);
  assert.equal(ledger.evidence_counts.a1.trace_events, 3);
  assert.equal(ledger.evidence_counts.a2.judge_results, 2);
  assert.deepEqual(ledger.evidence_counts.a2.failure_classes, ["wrong_tool"]);
  assert.equal(ledger.billing_usage_summary.schema_version, "a3.billing_usage_summary.v1");
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

test("A3 report builder preserves A2 regression and commercial readiness exports", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");
  const commercial = await loadJson("../../fixtures/a2/results/a2_commercial_readiness_report.json");

  const regression = summarizeRegressionReadiness(caseBook, regressionReplay);
  assert.equal(regression.available, true);
  assert.equal(regression.maturity_status, "seed");
  assert.equal(regression.target_replay_case_count, 3);

  const commercialSummary = summarizeCommercialReadiness(commercial);
  assert.equal(commercialSummary.available, true);
  assert.equal(commercialSummary.current_gate, "C2");
  assert.equal(commercialSummary.real_api_create_request_blocked, true);

  const legacyJson = buildJsonReport(runs, grades, coverage, readiness, caseBook, regressionReplay, commercial);
  assert.equal(legacyJson.regression_readiness.available, true);
  assert.equal(legacyJson.commercial_readiness.current_gate, "C2");

  const json = buildJsonReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, {
    caseBook,
    regressionReplay,
    commercialReadiness: commercial
  });
  assert.equal(json.regression_readiness.maturity_status, "seed");
  assert.equal(json.commercial_readiness.real_api_create_request_blocked, true);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, {
    caseBook,
    regressionReplay,
    commercialReadiness: commercial
  });
  assert.match(markdown, /## Regression Readiness/);
  assert.match(markdown, /Case book regressions: 1\/3/);
  assert.match(markdown, /Replay cases: 1\/3/);
  assert.match(markdown, /## Commercial Readiness/);
  assert.match(markdown, /Current gate: C2/);
  assert.match(markdown, /Commercial create-request quota blocked: yes/);
});

test("A3 report builder can summarize A2 C5 regression readiness fixtures", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");

  const summary = summarizeRegressionReadiness(caseBook, regressionReplay);
  assert.equal(summary.available, true);
  assert.equal(summary.case_book_schema_version, "a2.case_book.v1");
  assert.equal(summary.replay_schema_version, "a2.regression_replay.v1");
  assert.equal(summary.regression_case_count, 1);
  assert.equal(summary.replay_case_count, 1);
  assert.equal(summary.replay_ready, true);
  assert.equal(summary.maturity_status, "seed");
  assert.equal(summary.case_book_ready, false);
  assert.equal(summary.replay_gate_ready, false);
  assert.equal(summary.target_regression_case_count, 3);
  assert.equal(summary.current_regression_case_count, 1);
  assert.equal(summary.target_replay_case_count, 3);
  assert.equal(summary.current_replay_case_count, 1);
  assert.equal(summary.failed_replay_case_count, 0);
  assert.equal(summary.reviewed_evidence_target_count, 3);
  assert.equal(summary.reviewed_external_evidence_count, 0);
  assert.equal(summary.review_evidence_ready, false);
  assert.equal(summary.case_book_maturity_ready, false);
  assert.equal(summary.local_llm_mismatch_count, 1);
  assert.equal(summary.ashr_grading_missing_count, 6);
  assert.ok(summary.gaps.some((gap) => gap.includes("Promote 2 more")));
  assert.ok(summary.gaps.some((gap) => gap.includes("reviewed Ashr grading or audited semantic evidence")));
  assert.ok(summary.gaps.some((gap) => gap.includes("Replay 2 more")));

  const json = buildJsonReport(runs, grades, coverage, readiness, caseBook, regressionReplay);
  assert.equal(json.regression_readiness.available, true);
  assert.equal(json.regression_readiness.maturity_status, "seed");
  assert.equal(json.regression_readiness.target_replay_case_count, 3);
  assert.equal(json.regression_readiness.reviewed_external_evidence_count, 0);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, caseBook, regressionReplay);
  assert.match(markdown, /## Regression Readiness/);
  assert.match(markdown, /Maturity status: seed/);
  assert.match(markdown, /Case book regressions: 1\/3/);
  assert.match(markdown, /Replay cases: 1\/3/);
  assert.match(markdown, /Reviewed external evidence: 0\/3/);
  assert.match(markdown, /Ashr grading missing: 6/);
});



test("A3 report builder can summarize A2 commercial readiness fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");
  const commercial = await loadJson("../../fixtures/a2/results/a2_commercial_readiness_report.json");

  const summary = summarizeCommercialReadiness(commercial);
  assert.equal(summary.available, true);
  assert.equal(summary.schema_version, "a2.commercial_readiness.v1");
  assert.equal(summary.current_gate, "C2");
  assert.equal(summary.ready_for_commercial_gate, false);
  assert.equal(summary.gate_count, 7);
  assert.equal(summary.gate_status_counts.met, 3);
  assert.equal(summary.gate_status_counts.partial, 4);
  assert.deepEqual(summary.partial_gate_ids, ["C3", "C4", "C5", "C6"]);
  assert.deepEqual(summary.blocked_gate_ids, []);
  assert.equal(summary.scope_boundary_status, "controlled");
  assert.equal(summary.assignment_minimums_green, true);
  assert.equal(summary.scenario_count, 60);
  assert.equal(summary.golden_case_count, 32);
  assert.equal(summary.failure_class_count, 12);
  assert.equal(summary.real_api_total_records, commercial.evidence_snapshot.real_api_total_records);
  assert.equal(summary.real_api_record_count, commercial.evidence_snapshot.real_api_record_count);
  assert.equal(summary.real_api_quota_block_count, commercial.evidence_snapshot.real_api_quota_block_count);
  assert.ok(summary.real_api_total_records >= 140);
  assert.ok(summary.real_api_record_count >= 110);
  assert.ok(summary.real_api_quota_block_count >= 5);
  assert.equal(summary.real_api_create_request_blocked, true);
  assert.equal(summary.official_sdk_smoke_read_only_reachable, true);
  assert.equal(summary.official_sdk_smoke_ok_call_count, 6);
  assert.equal(summary.ashr_public_merge_status, "not_merged");
  assert.equal(summary.semantic_live_merge_status, "offline_reference_only");
  assert.equal(summary.regression_replay_maturity, "seed");
  assert.deepEqual(summary.next_top_3_ids, [
    "fill_ashr_grading_column",
    "audited_llm_judge_harness",
    "promote_disagreement_regressions"
  ]);

  const json = buildJsonReport(runs, grades, coverage, readiness, caseBook, regressionReplay, commercial);
  assert.equal(json.commercial_readiness.available, true);
  assert.equal(json.commercial_readiness.current_gate, "C2");
  assert.equal(json.commercial_readiness.real_api_create_request_blocked, true);
  assert.equal(json.commercial_readiness.official_sdk_smoke_read_only_reachable, true);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, caseBook, regressionReplay, commercial);
  assert.match(markdown, /## Commercial Readiness/);
  assert.match(markdown, /Current gate: C2/);
  assert.match(markdown, /Gate status counts: met 3, partial 4, blocked 0/);
  assert.match(markdown, /Partial gates: C3, C4, C5, C6/);
  assert.match(markdown, new RegExp(`Commercial real API records: ${summary.real_api_record_count}\\/${summary.real_api_total_records}`));
  assert.match(markdown, /Commercial create-request quota blocked: yes/);
  assert.match(markdown, /Commercial official SDK smoke: ok \(6 ok, 0 error\)/);
});



test("A3 report builder can summarize A2 release gate fixture", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");
  const commercial = await loadJson("../../fixtures/a2/results/a2_commercial_readiness_report.json");
  const releaseGate = await loadJson("../../fixtures/a2/results/a2_release_gate_report.json");

  const summary = summarizeReleaseGate(releaseGate);
  assert.equal(summary.available, true);
  assert.equal(summary.schema_version, "a2.release_gate.v1");
  assert.equal(summary.decision, "block");
  assert.equal(summary.blocks_release, true);
  assert.equal(summary.exit_code, 2);
  assert.equal(summary.risk_score, 100);
  assert.equal(summary.current_commercial_gate, "C2");
  assert.equal(summary.ready_for_commercial_gate, false);
  assert.equal(summary.blocking_gate_count, 3);
  assert.equal(summary.evidence_blocker_count, 4);
  assert.equal(summary.warning_count, 3);
  assert.deepEqual(summary.blocker_gates, ["C3", "C4", "C5"]);
  assert.deepEqual(summary.required_sources, ["ashr_grading", "llm_judge"]);
  assert.equal(summary.required_source_counts.ashr_grading.required_count, 6);
  assert.equal(summary.required_source_counts.ashr_grading.current_available, 0);
  assert.equal(summary.required_source_counts.llm_judge.required_count, 6);
  assert.equal(summary.required_source_counts.llm_judge.current_available, 0);
  assert.equal(summary.ci_mode, "fail on decision=block");
  assert.ok(summary.evidence_refs.includes("fixtures/a2/results/a2_g3_calibration_matrix.json"));

  const json = buildJsonReport(
    runs,
    grades,
    coverage,
    readiness,
    caseBook,
    regressionReplay,
    commercial,
    releaseGate
  );
  assert.equal(json.release_gate.available, true);
  assert.equal(json.release_gate.decision, "block");
  assert.equal(json.release_gate.blocks_release, true);
  assert.deepEqual(json.release_gate.required_sources, ["ashr_grading", "llm_judge"]);

  const markdown = buildMarkdownReport(
    runs,
    grades,
    coverage,
    readiness,
    caseBook,
    regressionReplay,
    commercial,
    releaseGate
  );
  assert.match(markdown, /## Release Gate/);
  assert.match(markdown, /Decision: block/);
  assert.match(markdown, /Blocks release: yes/);
  assert.match(markdown, /Blocking gates: C3, C4, C5/);
  assert.match(markdown, /Required sources: ashr_grading, llm_judge/);
});

test("A3 report builder exports A2 result persistence and release unblock checklist evidence", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const caseBook = await loadJson("../../fixtures/a2/results/a2_case_book.json");
  const regressionReplay = await loadJson("../../fixtures/a2/results/a2_regression_replay_report.json");
  const commercial = await loadJson("../../fixtures/a2/results/a2_commercial_readiness_report.json");
  const releaseGate = await loadJson("../../fixtures/a2/results/a2_release_gate_report.json");
  const resultPersistence = await loadJson("../../fixtures/a2/results/a2_result_persistence_manifest.json");
  const releaseUnblockChecklist = await loadJson("../../fixtures/a2/results/a2_release_unblock_checklist.json");

  const persistenceSummary = summarizeA2ResultPersistence(resultPersistence);
  assert.equal(persistenceSummary.available, true);
  assert.equal(persistenceSummary.schema_version, "a2.result_persistence_manifest.v1");
  assert.equal(persistenceSummary.record_count, 163);
  assert.equal(persistenceSummary.judge_result_count, 160);
  assert.equal(persistenceSummary.release_gate_record_count, 1);
  assert.equal(persistenceSummary.scenario_selection_record_count, 1);
  assert.equal(persistenceSummary.release_unblock_checklist_record_count, 1);
  assert.equal(persistenceSummary.safety_blocking_result_count, 4);
  assert.equal(persistenceSummary.public_safe, true);
  assert.equal(persistenceSummary.secrets_not_recorded, true);
  assert.ok(persistenceSummary.latest_records.some((record) => record.record_type === "release_unblock_checklist"));

  const extendedPersistence = {
    ...resultPersistence,
    record_count: resultPersistence.records.length + 1,
    record_type_counts: {
      ...resultPersistence.record_type_counts,
      release_unblock_checklist: (resultPersistence.record_type_counts.release_unblock_checklist || 0) + 1
    },
    source_refs: {
      ...resultPersistence.source_refs,
      release_unblock_checklist: "fixtures/a2/results/a2_release_unblock_checklist.json"
    },
    records: [
      ...resultPersistence.records,
      {
        schema_version: "a2.result_persistence_record.v1",
        record_type: "release_unblock_checklist",
        tenant_id: "org_local_demo",
        org: "org_local_demo",
        project: "a2_g3_calibration",
        run: "a2_g3_grade_results",
        case: "release-unblock-checklist",
        case_id: "release-unblock-checklist",
        scenario_id: null,
        judge_id: "release_unblock_checklist_builder",
        judge_version: "a2.release_unblock_checklist.v1",
        policy_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000001",
        input_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000002",
        output_hash: "sha256:0000000000000000000000000000000000000000000000000000000000000003",
        created_at: "2026-07-09T00:00:00Z",
        overall_status: "blocked",
        blocked_gate_count: 3,
        release_gate_decision: "block",
        release_gate_risk_score: 100,
        gate_count: 3,
        private_evidence_required: true,
        result_schema_version: "a2.release_unblock_checklist.v1"
      }
    ]
  };
  const extendedPersistenceSummary = summarizeA2ResultPersistence(extendedPersistence);
  const latestUnblockRecord = extendedPersistenceSummary.latest_records.at(-1);
  assert.equal(extendedPersistenceSummary.release_unblock_checklist_record_count, 2);
  assert.equal(latestUnblockRecord.record_type, "release_unblock_checklist");
  assert.equal(latestUnblockRecord.overall_status, "blocked");
  assert.equal(latestUnblockRecord.release_gate_decision, "block");
  assert.equal(latestUnblockRecord.release_gate_risk_score, 100);
  assert.equal(latestUnblockRecord.private_evidence_required, true);

  const unblockSummary = summarizeA2ReleaseUnblockChecklist(releaseUnblockChecklist);
  assert.equal(unblockSummary.available, true);
  assert.equal(unblockSummary.schema_version, "a2.release_unblock_checklist.v1");
  assert.equal(unblockSummary.overall_status, "blocked");
  assert.deepEqual(unblockSummary.blocking_gate_ids, ["C3", "C4", "C5"]);
  assert.equal(unblockSummary.required_action_count, 3);
  assert.equal(unblockSummary.private_evidence_required_count, 2);
  assert.ok(unblockSummary.required_reviewer_roles.includes("A2 evidence reviewer"));
  assert.ok(unblockSummary.dashboard_sections.includes("C3 official grading"));

  const bundle = {
    caseBook,
    regressionReplay,
    commercialReadiness: commercial,
    releaseGate,
    resultPersistence,
    releaseUnblockChecklist
  };
  const json = buildJsonReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, bundle);
  assert.equal(json.a2_result_persistence.available, true);
  assert.equal(json.a2_result_persistence.record_count, 163);
  assert.equal(json.a2_release_unblock_checklist.overall_status, "blocked");
  assert.deepEqual(json.a2_release_unblock_checklist.blocking_gate_ids, ["C3", "C4", "C5"]);
  const extendedJson = buildJsonReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, {
    ...bundle,
    resultPersistence: extendedPersistence
  });
  assert.equal(extendedJson.a2_result_persistence.release_unblock_checklist_record_count, 2);
  assert.equal(extendedJson.a2_result_persistence.latest_records.at(-1).overall_status, "blocked");

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, bundle);
  assert.match(markdown, /## A2 Result Persistence/);
  assert.match(markdown, /Records: 163/);
  assert.match(markdown, /Safety blocking results: 4/);
  assert.match(markdown, /Release unblock checklist records: 1/);
  const extendedMarkdown = buildMarkdownReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, {
    ...bundle,
    resultPersistence: extendedPersistence
  });
  assert.match(extendedMarkdown, /Release unblock checklist records: 2/);
  assert.match(markdown, /## A2 Release Unblock Checklist/);
  assert.match(markdown, /Blocking gates: C3, C4, C5/);
  assert.match(markdown, /Required reviewers: A2 evidence reviewer, A2 case-book owner/);
});

test("A3 report builder preserves A2 cross-lane security and SQL store summaries", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a2/results/a2_g3_grade_results.json");
  const coverage = await loadJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
  const readiness = await loadJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
  const crossLaneSecurityContext = {
    schema_version: "a2.cross_lane_security_context.v1",
    report_id: "a2_cross_lane_security_context_unit",
    source_refs: {
      a1_route_scope: "docs/a1/route_scope.md",
      a3_auth_rbac_boundary: "docs/a3/auth_rbac.md",
      a3_openapi: "docs/a3/openapi/a3_commercial_api.openapi.json"
    },
    a1_route_scope: {
      available: true,
      schema_version: "a1.route_scope.v1",
      ready_for_a2_security_context: true
    },
    a3_auth_rbac_boundary: {
      available: true,
      schema_version: "a3.rbac_policy.v1",
      ready_for_a2_security_context: true
    },
    a2_policy_implications: {
      should_block_hosted_mutations_without_a1_auth: true,
      should_require_metadata_only_audit_events: true,
      should_keep_raw_actor_identity_forbidden: true,
      should_add_route_scope_security_cases: true,
      should_add_auth_rbac_abuse_cases: true,
      release_policy_refs: ["release_gate.auth_boundary"]
    },
    a2_security_followups: [{
      followup_id: "security-followup-1",
      action: "Add hosted mutation abuse case.",
      owner: "A2 security reviewer",
      tags: ["auth", "rbac"],
      writes_private_evidence: false,
      requires_user_decision: false
    }],
    metadata: {
      public_safe: true,
      deterministic: true,
      requires_network: false,
      requires_ashr_api_key: false,
      does_not_execute_live_calls: true,
      does_not_read_private_evidence: true,
      raw_private_evidence_not_recorded: true,
      secrets_not_recorded: true
    }
  };
  const sqlStoreReport = {
    schema_version: "a2.sql_store_report.v1",
    report_id: "a2_sql_store_unit",
    database: {
      engine: "sqlite",
      reference_dialect: "sqlite",
      production_target: "postgres",
      ddl_version: "a2.sql_store.sqlite.v1",
      ddl_ref: "services/judge/sql/a2.sql"
    },
    table_counts: {
      a2_eval_runs: 1,
      a2_judge_results: 160,
      a2_calibration_cases: 6
    },
    write_counts: {
      a2_judge_results: 160,
      a2_calibration_cases: 6
    },
    query_checks: {
      failure_class_counts: { missing_required_tool: 3 },
      golden_failure_class_counts: { wrong_arguments: 1 },
      calibration_missing_ashr_count: 6,
      calibration_disagreement_count: 1,
      regression_replay_status_counts: { blocked: 3 },
      can_join_case_level_history: true
    },
    source_refs: {
      grade_report: "fixtures/a2/results/a2_g3_grade_results.json",
      ddl: "services/judge/sql/a2.sql"
    },
    metadata: {
      public_safe: true,
      uses_python_stdlib_sqlite: true,
      does_not_require_external_database: true,
      does_not_execute_live_calls: true,
      raw_private_evidence_not_recorded: true,
      secrets_not_recorded: true,
      intended_consumers: ["A3 reporting", "SaaS audit export"]
    }
  };

  const securitySummary = summarizeA2CrossLaneSecurityContext(crossLaneSecurityContext);
  assert.equal(securitySummary.available, true);
  assert.equal(securitySummary.should_block_hosted_mutations_without_a1_auth, true);
  assert.equal(securitySummary.followup_count, 1);
  assert.equal(securitySummary.safety.secrets_not_recorded, true);

  const sqlSummary = summarizeA2SqlStoreReport(sqlStoreReport);
  assert.equal(sqlSummary.available, true);
  assert.equal(sqlSummary.production_target, "postgres");
  assert.equal(sqlSummary.table_count_total, 167);
  assert.equal(sqlSummary.write_count_total, 166);
  assert.equal(sqlSummary.can_join_case_level_history, true);

  const bundle = {
    crossLaneSecurityContext,
    sqlStoreReport
  };
  const json = buildJsonReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, bundle);
  assert.equal(json.a2_cross_lane_security_context.report_id, "a2_cross_lane_security_context_unit");
  assert.equal(json.a2_sql_store_report.database_engine, "sqlite");
  assert.equal(json.a2_sql_store_report.table_count_total, 167);

  const markdown = buildMarkdownReport(runs, grades, coverage, readiness, {}, {}, {}, {}, {}, {}, {}, {}, bundle);
  assert.match(markdown, /## A2 Cross-Lane Security Context/);
  assert.match(markdown, /Block hosted mutations without A1 auth: yes/);
  assert.match(markdown, /## A2 SQL Store Report/);
  assert.match(markdown, /DB: sqlite \/ target postgres/);
});
