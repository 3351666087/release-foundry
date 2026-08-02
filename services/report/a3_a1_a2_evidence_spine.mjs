import {
  buildDashboardSummary,
  normalizeCases
} from "./report_builder.mjs";

export const A3_A1_A2_EVIDENCE_SPINE_SCHEMA_VERSION = "a3.a1_a2_evidence_spine.v1";

export function buildA3A1A2EvidenceSpine(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.run_fixture || {};
  const gradeFixture = inputs.gradeFixture || inputs.grade_fixture || {};
  const cases = normalizeCases(runFixture, gradeFixture);
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const releaseGate = inputs.a2ReleaseGate || inputs.releaseGate || inputs.release_gate || {};
  const provenance = inputs.releaseDecisionProvenance || inputs.release_decision_provenance || {};
  const reviewWorkflow = inputs.reviewWorkflow || inputs.review_workflow || {};
  const reportCenter = inputs.reportCenter || inputs.report_center || {};
  const peerCalibration = inputs.peerBranchCalibration || inputs.peer_branch_calibration || {};
  const judgeResultCount = cases.reduce((total, item) => total + list(item.judge_results).length, 0);
  const traceEventCount = cases.reduce((total, item) => total + list(item.trace_events).length, 0);
  const observationCount = cases.reduce((total, item) => total + list(item.observations).length, 0);
  const toolCallCount = cases.reduce((total, item) => total + countToolCalls(item), 0);
  const failureClasses = countValues(cases
    .map((item) => item.primary_failure_class)
    .filter((value) => value && value !== "none"));
  const linkedCaseCount = cases.filter((item) => list(item.judge_results).length > 0).length;
  const releaseDecision = normalizeReleaseDecision(releaseGate.decision);
  const releaseBlockers = list(releaseGate.blockers);
  const reviewRecordCount = numberOr(
    reviewWorkflow.record_count,
    list(reviewWorkflow.records || reviewWorkflow.items).length
  );
  const reportCount = numberOr(reportCenter.report_count, list(reportCenter.reports).length);
  const peerDeltas = list(peerCalibration.top_deltas || peerCalibration.peer_deltas);
  const identityWatch = watchSignal(peerDeltas, ["identity_verification", "identity verification"]);
  const multimodalWatch = watchSignal(peerDeltas, ["multimodal_real_api_smoke", "multimodal real api smoke"]);

  const a1Status = summary.totalRuns === 0
    ? "missing"
    : summary.traceCompleteness >= 90
      ? "ready"
      : "partial";
  const a2Status = judgeResultCount > 0
    ? linkedCaseCount === summary.totalCases ? "ready" : "partial"
    : "missing";
  const gateStatus = releaseDecision === "block"
    ? "blocked"
    : releaseDecision === "pass"
      ? "ready"
      : "attention";
  const operateStatus = provenance.status === "ready"
    ? "ready"
    : releaseDecision === "block" || provenance.status === "blocked"
      ? "action_required"
      : "waiting";

  const stages = [
    stage("01", "A1", "Capture", a1Status, {
      primary: `${summary.totalRuns} run / ${summary.totalCases} cases`,
      secondary: `${summary.traceCompleteness}% trace complete`,
      metrics: {
        run_count: summary.totalRuns,
        case_count: summary.totalCases,
        trace_event_count: traceEventCount,
        observation_count: observationCount,
        tool_call_count: toolCallCount
      },
      evidence_refs: ["a1.RunResult", "a1.TraceEvent", "a1.Observation", "a1.ToolCall"]
    }),
    stage("02", "A2", "Evaluate", a2Status, {
      primary: `${judgeResultCount} judge results`,
      secondary: `${summary.passRate}% pass / ${summary.avgScore} avg`,
      metrics: {
        judge_result_count: judgeResultCount,
        linked_case_count: linkedCaseCount,
        passed_case_count: summary.passed,
        failed_case_count: summary.failed,
        failure_class_count: Object.keys(failureClasses).length
      },
      evidence_refs: ["a2.GradeResult", "a2.FailureAnalysis", "a2.RubricResult"]
    }),
    stage("03", "A2", "Gate", gateStatus, {
      primary: releaseDecision,
      secondary: `${releaseBlockers.length} release blockers`,
      metrics: {
        risk_score: numberOr(releaseGate.risk_score, 0),
        blocker_count: releaseBlockers.length,
        warning_count: list(releaseGate.warnings).length,
        evidence_ref_count: list(releaseGate.evidence_refs).length
      },
      evidence_refs: ["a2.ReleaseGate", "a2.ReleasePolicy"]
    }),
    stage("04", "A3", "Operate", operateStatus, {
      primary: provenance.release_decision || releaseDecision,
      secondary: `${reviewRecordCount} reviews / ${reportCount} reports`,
      metrics: {
        review_record_count: reviewRecordCount,
        report_count: reportCount,
        provenance_node_count: list(provenance.nodes).length,
        provenance_blocker_count: list(provenance.blockers).length
      },
      evidence_refs: ["a3.ReviewWorkflow", "a3.ReportCenter", "a3.ReleaseDecisionProvenance"]
    })
  ];

  const handoffs = [
    handoff("a1_to_a2", "A1 Capture", "A2 Evaluate", a1Status !== "missing" && a2Status !== "missing" ? "linked" : "blocked", {
      linked_case_count: linkedCaseCount,
      unresolved_case_count: Math.max(0, summary.totalCases - linkedCaseCount)
    }),
    handoff("a2_to_gate", "A2 Evaluate", "A2 Gate", a2Status !== "missing" && releaseDecision !== "unknown" ? "linked" : "blocked", {
      failed_case_count: summary.failed,
      release_blocker_count: releaseBlockers.length
    }),
    handoff("gate_to_a3", "A2 Gate", "A3 Operate", provenance.status ? "linked" : "partial", {
      provenance_node_count: list(provenance.nodes).length,
      decision_authority: provenance.decision_authority || "a2.release_gate"
    })
  ];

  const status = stages.some((item) => ["missing", "blocked"].includes(item.status))
    ? "blocked"
    : stages.some((item) => ["partial", "attention", "action_required", "waiting"].includes(item.status))
      ? "attention"
      : "ready";

  return {
    schema_version: A3_A1_A2_EVIDENCE_SPINE_SCHEMA_VERSION,
    status,
    source: options.source || inputs.source || "local",
    release_decision: provenance.release_decision || releaseDecision,
    decision_authority: provenance.decision_authority || "a2.release_gate",
    summary: {
      run_count: summary.totalRuns,
      case_count: summary.totalCases,
      trace_completeness: summary.traceCompleteness,
      judge_result_count: judgeResultCount,
      pass_rate: summary.passRate,
      failed_case_count: summary.failed,
      review_record_count: reviewRecordCount,
      report_count: reportCount
    },
    stages,
    handoffs,
    failure_classes: failureClasses,
    draft_watch: {
      a1_identity_verification: identityWatch,
      a2_multimodal_real_api_smoke: multimodalWatch,
      draft_contracts_are_authoritative: false,
      merge_required_before_production_claim: true
    },
    ownership: {
      a1: "runtime, trace, tool calls, identity, storage, usage and billing authority",
      a2: "scenario, judge, failure taxonomy, release policy and evidence verification authority",
      a3: "read-only product workflow, review, report and commercial visibility"
    },
    safety: {
      raw_run_payload_embedded: false,
      raw_grade_payload_embedded: false,
      raw_identity_embedded: false,
      secret_values_allowed: false,
      a1_or_a2_semantics_mutated: false
    }
  };
}

function stage(index, lane, label, status, details) {
  return {
    stage_index: index,
    lane,
    label,
    status,
    ...details
  };
}

function handoff(id, from, to, status, metrics) {
  return {
    handoff_id: id,
    from,
    to,
    status,
    metrics
  };
}

function normalizeReleaseDecision(value) {
  if (["pass", "approve", "approve_release"].includes(value)) return "pass";
  if (["block", "blocked", "block_release", "deny"].includes(value)) return "block";
  if (["warn", "warning"].includes(value)) return "warn";
  return "unknown";
}

function countToolCalls(item = {}) {
  const expected = list(item.expected?.tool_calls);
  const actual = list(item.actual?.tool_calls);
  const observed = list(item.observations).reduce((total, observation) => total + list(observation.tool_calls).length, 0);
  return Math.max(expected.length, actual.length, observed);
}

function countValues(values) {
  const counts = {};
  for (const value of values) {
    counts[value] = (counts[value] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function watchSignal(deltas, needles) {
  const match = deltas.find((item) => {
    const haystack = `${item.delta_id || ""} ${item.contract || ""} ${item.source_file || ""}`.toLowerCase();
    return needles.some((needle) => haystack.includes(needle));
  });
  return match
    ? {
        observed: true,
        status: match.a3_status || "watch",
        source_lane: match.owner_lane || "A1/A2",
        contract: match.contract || match.delta_id,
        source_branch: match.source_branch || "peer branch",
        merged_to_main: false
      }
    : {
        observed: false,
        status: "not_observed",
        source_lane: "A1/A2",
        contract: null,
        source_branch: null,
        merged_to_main: false
      };
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
