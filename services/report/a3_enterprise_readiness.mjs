import {
  buildDashboardSummary,
  normalizeCases
} from "./report_builder.mjs";

export const A3_ENTERPRISE_READINESS_SCHEMA_VERSION = "a3.enterprise_readiness.v1";

export function buildEnterpriseReadinessReport(inputs = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const adminConsole = inputs.adminConsole || {};
  const dbContract = inputs.dbContract || {};
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const evidence = summarizeA1A2Evidence(summary, cases);
  const admin = summarizeAdminConsole(adminConsole);
  const db = summarizeDbContract(dbContract);
  const blockers = buildBlockers({ summary, evidence, admin, db });
  const readinessScore = scoreReadiness({ summary, evidence, admin, db, blockers });
  const cloudSelfHostPosture = buildCloudSelfHostPosture({ admin, db, blockers });

  return {
    schema_version: A3_ENTERPRISE_READINESS_SCHEMA_VERSION,
    readiness_score: readinessScore,
    status: readinessStatus(readinessScore, blockers),
    blockers,
    enabled_capabilities: buildEnabledCapabilities({ summary, evidence, admin, db }),
    enterprise_value_map: buildEnterpriseValueMap({ summary, evidence, admin, db, blockers, cloudSelfHostPosture }),
    cloud_self_host_posture: cloudSelfHostPosture,
    decision_packets: buildDecisionPackets({ summary, evidence, admin, blockers }),
    self_host_packet: buildSelfHostPacket({ admin, db, evidence, blockers }),
    next_actions: buildNextActions({ blockers, admin, db, evidence, cloudSelfHostPosture }),
    a1_a2_compatibility_notes: buildCompatibilityNotes({ summary, evidence })
  };
}

export function summarizeA1A2Evidence(summary = {}, cases = []) {
  const traceCases = cases.filter((item) => item.trace_ready);
  const toolCases = cases.filter((item) => (
    (item.expected?.tool_calls || []).length > 0
    || (item.actual?.tool_calls || []).length > 0
  ));
  const judgeCases = cases.filter((item) => (item.judge_results || []).length > 0 || item.grade);
  const judgeModes = new Set();
  let judgeResultCount = 0;
  let traceEventCount = 0;

  for (const item of cases) {
    traceEventCount += (item.trace_events || []).length;
    for (const judge of item.judge_results || []) {
      judgeResultCount += 1;
      if (judge.judge_mode) {
        judgeModes.add(judge.judge_mode);
      }
    }
    if ((!item.judge_results || item.judge_results.length === 0) && item.grade) {
      judgeResultCount += 1;
    }
  }

  return {
    a1_run_count: summary.totalRuns || 0,
    a1_trace_case_count: traceCases.length,
    a1_trace_event_count: traceEventCount,
    a1_tool_case_count: toolCases.length,
    a2_grade_case_count: judgeCases.length,
    a2_judge_result_count: judgeResultCount,
    a2_judge_mode_count: judgeModes.size
  };
}

function buildBlockers({ summary, evidence, admin, db }) {
  const blockers = [];
  if ((summary.totalRuns || 0) === 0) {
    blockers.push(blocker("a1_runs_missing", "blocking", "A1 run evidence is required before enterprise readiness can be claimed."));
  }
  if ((summary.totalCases || 0) === 0) {
    blockers.push(blocker("dashboard_cases_missing", "blocking", "A3 needs normalized case evidence to support audit and dashboard workflows."));
  }
  if (evidence.a1_trace_case_count === 0) {
    blockers.push(blocker("a1_trace_evidence_missing", "blocking", "A1 trace evidence is required for audit replay and self-host validation."));
  }
  if (evidence.a2_grade_case_count === 0 || evidence.a2_judge_result_count === 0) {
    blockers.push(blocker("a2_judge_evidence_missing", "blocking", "A2 judge evidence is required for release-quality grading compatibility."));
  }
  if (admin.available && admin.secret_values_allowed) {
    blockers.push(blocker("admin_secrets_enabled", "blocking", "Admin console readiness cannot allow raw secret values in local reports."));
  }
  if (admin.available && admin.real_mutations_enabled) {
    blockers.push(blocker("admin_real_mutations_enabled", "blocking", "Enterprise readiness reports must keep SaaS admin mutations plan-only until auth and audit controls exist."));
  }
  if (db.available && !db.tenant_scoping_ready) {
    blockers.push(blocker("tenant_scoping_missing", "blocking", "Self-host readiness requires tenant scoping columns for organization and project isolation."));
  }
  return blockers;
}

function buildEnabledCapabilities({ summary, evidence, admin, db }) {
  const capabilities = [];
  if ((summary.totalRuns || 0) > 0) {
    capabilities.push(capability("a1_run_ingest", "A1 run fixtures are normalized for A3 dashboards.", evidence.a1_run_count));
  }
  if (evidence.a1_trace_case_count > 0) {
    capabilities.push(capability("a1_trace_audit", "A1 trace evidence is available for replay and audit review.", evidence.a1_trace_case_count));
  }
  if (evidence.a2_grade_case_count > 0) {
    capabilities.push(capability("a2_judge_ingest", "A2 grade and judge evidence is available for compatibility checks.", evidence.a2_grade_case_count));
  }
  if ((summary.totalCases || 0) > 0) {
    capabilities.push(capability("normalized_case_dashboard", "A3 can summarize normalized release cases.", summary.totalCases));
  }
  if (admin.available && !admin.secret_values_allowed && !admin.real_mutations_enabled) {
    capabilities.push(capability("admin_console_shell", "SaaS admin console is represented as a safe read-only or plan-only shell.", admin.action_count));
  }
  if (db.available && db.tenant_scoping_ready) {
    capabilities.push(capability("self_host_db_contract", "Self-host database contract includes tenant scoping requirements.", db.table_count));
  }
  capabilities.push(capability("secret_free_aggregate_report", "Enterprise readiness output is aggregate-only and does not echo source payload values.", 1));
  return capabilities;
}

function buildNextActions({ blockers, admin, db, evidence, cloudSelfHostPosture }) {
  const actions = blockers.map((item) => ({
    id: `fix_${item.id}`,
    priority: item.severity === "blocking" ? "high" : "medium",
    action: item.message
  }));

  if (!admin.available) {
    actions.push({
      id: "attach_admin_console",
      priority: "medium",
      action: "Attach the A3 SaaS admin console summary to prove read-only admin workflow posture."
    });
  }
  if (!db.available) {
    actions.push({
      id: "attach_db_contract",
      priority: "medium",
      action: "Attach the A3 DB contract to complete self-host storage readiness evidence."
    });
  }
  if (cloudSelfHostPosture.hosted_readiness !== "read_only_hosted_shell_ready") {
    actions.push({
      id: "hosted_shell_controls",
      priority: "medium",
      action: "Strengthen hosted admin shell controls so cloud posture is visible without enabling unsafe real mutations."
    });
  }
  if (cloudSelfHostPosture.self_host_readiness !== "self_host_contract_visible") {
    actions.push({
      id: "self_host_contract_visibility",
      priority: "medium",
      action: "Expose tenant-safe DB and storage contract details so self-host readiness is clearer to enterprise buyers."
    });
  }
  if (evidence.a1_tool_case_count === 0) {
    actions.push({
      id: "add_tool_call_evidence",
      priority: "low",
      action: "Add at least one tool-call case so enterprise review can inspect tool protocol compatibility."
    });
  }
  if (actions.length === 0) {
    actions.push({
      id: "promote_to_hosted_validation",
      priority: "low",
      action: "Run the same readiness report against hosted auth, RBAC, audit-log, and storage integrations."
    });
  }
  return actions;
}

function buildEnterpriseValueMap({ summary, evidence, admin, db, blockers, cloudSelfHostPosture }) {
  return {
    schema_version: "a3.enterprise_value_map.v1",
    sellable_now: [
      "release review dashboard",
      "trace-backed failure triage",
      "hosted report and audit packet shell"
    ],
    blocked_enterprise_claims: blockers.filter((item) => item.severity === "blocking").map((item) => item.id),
    high_value_paths: [
      "enterprise audit and sign-off",
      "self-host readiness reviews",
      "release gate plus reviewer workflow"
    ],
    buyer_questions_answered: {
      release_blocking: summary.totalCases > 0,
      trace_evidence: evidence.a1_trace_case_count > 0,
      judge_evidence: evidence.a2_judge_result_count > 0,
      tenant_story: cloudSelfHostPosture.tenant_isolation_state === "visible",
      cloud_admin_story: admin.available === true,
      self_host_story: db.available === true
    }
  };
}

function buildCloudSelfHostPosture({ admin, db, blockers }) {
  const blockingCount = blockers.filter((item) => item.severity === "blocking").length;
  return {
    hosted_readiness: admin.available && !admin.real_mutations_enabled
      ? "read_only_hosted_shell_ready"
      : "hosted_shell_missing_controls",
    self_host_readiness: db.available && db.tenant_scoping_ready
      ? "self_host_contract_visible"
      : "self_host_contract_incomplete",
    tenant_isolation_state: db.tenant_scoping_ready ? "visible" : "missing",
    cloud_admin_surface_state: admin.available ? "visible" : "missing",
    blocking_count: blockingCount,
    why_it_matters: "Commercial buyers want to know whether the product is heading toward hosted control, self-host compatibility, and tenant-safe isolation."
  };
}

function buildDecisionPackets({ summary, evidence, admin, blockers }) {
  const releaseEvidenceReady = evidence.a1_trace_case_count > 0 && evidence.a2_judge_result_count > 0;
  const blockingCount = blockers.filter((item) => item.severity === "blocking").length;
  return {
    schema_version: "a3.decision_packets.v1",
    reviewer_packet: {
      status: releaseEvidenceReady ? "ready_for_review" : "missing_evidence",
      includes: ["trace timeline", "tool-call diffs", "judge evidence", "audit-visible hosted report"],
      buyer_value: "Lets reviewers sign or block releases with concrete evidence instead of screenshots."
    },
    executive_packet: {
      status: releaseEvidenceReady && blockingCount === 0 ? "ready_for_signoff" : "blocked_by_evidence_or_controls",
      includes: ["release status", "failure cluster summary", "sign-off readiness", "risk posture"],
      buyer_value: "Lets leadership sign deployment posture without reading raw traces or secrets."
    },
    customer_external_packet: {
      status: "blocked",
      includes: ["public trust summary", "sanitized hosted report", "revocable audit trail"],
      buyer_value: "Future customer-safe packet for post-approval external sharing.",
      blocked_reason: "Trust workflow, redaction proof, and customer-safe publish controls are not complete yet."
    },
    admin_surface_ready: admin.available === true,
    dashboard_case_count: summary.totalCases || 0
  };
}

function buildSelfHostPacket({ admin, db, evidence, blockers }) {
  return {
    schema_version: "a3.self_host_packet.v1",
    status: db.available && db.tenant_scoping_ready ? "packet_contract_ready" : "packet_incomplete",
    install_surfaces: ["postgres schema", "tenant scoping", "audit events", "usage rollups"],
    buyer_promises: [
      "Self-host buyers can inspect tenant boundaries before rollout.",
      "Audit and usage expectations are visible before deployment.",
      "A1/A2 evidence requirements stay explicit in the self-host story."
    ],
    hosted_vs_self_host: [
      {
        surface: "identity",
        hosted: "A1 hosted auth and session boundary later",
        self_host: "customer-owned IdP and RBAC bridge",
        buyer_value: "Supports enterprise review of login and approval authority."
      },
      {
        surface: "artifact storage",
        hosted: "managed object storage contract",
        self_host: "customer bucket / MinIO-compatible target",
        buyer_value: "Keeps evidence packets inside customer-controlled infrastructure."
      },
      {
        surface: "usage and billing",
        hosted: "metered hosted packaging",
        self_host: "contract-visible local usage ledger",
        buyer_value: "Lets procurement understand hosted price vs internal deployment cost."
      }
    ],
    blocker_count: blockers.filter((item) => item.severity === "blocking").length,
    a1_trace_ready: evidence.a1_trace_case_count > 0,
    a2_judge_ready: evidence.a2_judge_result_count > 0,
    admin_surface_ready: admin.available === true
  };
}

function buildCompatibilityNotes({ summary, evidence }) {
  return {
    a1: {
      compatible: evidence.a1_run_count > 0 && evidence.a1_trace_case_count > 0,
      run_count: evidence.a1_run_count,
      trace_case_count: evidence.a1_trace_case_count,
      trace_event_count: evidence.a1_trace_event_count,
      tool_case_count: evidence.a1_tool_case_count,
      note: "A3 reads normalized A1 run and trace evidence without changing runner semantics."
    },
    a2: {
      compatible: evidence.a2_grade_case_count > 0 && evidence.a2_judge_result_count > 0,
      grade_case_count: evidence.a2_grade_case_count,
      judge_result_count: evidence.a2_judge_result_count,
      judge_mode_count: evidence.a2_judge_mode_count,
      note: "A3 preserves A2 grade and judge evidence as compatibility inputs for release review."
    },
    dashboard_case_count: summary.totalCases || 0
  };
}

function scoreReadiness({ summary, evidence, admin, db, blockers }) {
  const totalCases = summary.totalCases || 0;
  const traceCoverage = totalCases ? evidence.a1_trace_case_count / totalCases : 0;
  const gradeCoverage = totalCases ? evidence.a2_grade_case_count / totalCases : 0;
  let score = 0;

  score += evidence.a1_run_count > 0 ? 15 : 0;
  score += Math.round(traceCoverage * 20);
  score += Math.round(gradeCoverage * 20);
  score += evidence.a2_judge_result_count > 0 ? 10 : 0;
  score += admin.available ? 10 : 0;
  score += admin.available && !admin.secret_values_allowed && !admin.real_mutations_enabled ? 10 : 0;
  score += db.available ? 5 : 0;
  score += db.available && db.tenant_scoping_ready ? 10 : 0;

  const blockingPenalty = blockers.filter((item) => item.severity === "blocking").length * 10;
  return clamp(score - blockingPenalty, 0, 100);
}

function readinessStatus(score, blockers = []) {
  if (blockers.some((item) => item.severity === "blocking")) {
    return "blocked";
  }
  if (score >= 85) {
    return "enterprise_ready_local_evidence";
  }
  if (score >= 60) {
    return "needs_hosted_validation";
  }
  return "not_ready";
}

function summarizeAdminConsole(adminConsole = {}) {
  const available = isObject(adminConsole) && Object.keys(adminConsole).length > 0;
  const safety = isObject(adminConsole.safety) ? adminConsole.safety : {};
  const cloud = isObject(adminConsole.cloud_management) ? adminConsole.cloud_management : {};
  return {
    available,
    schema_version: available ? adminConsole.schema_version || "unknown" : "none",
    action_count: Array.isArray(adminConsole.actions) ? adminConsole.actions.length : 0,
    secret_values_allowed: safety.secret_values_allowed === true || safety.real_api_key_secrets_enabled === true,
    real_mutations_enabled: cloud.real_mutations_enabled === true
      || safety.real_team_invites_enabled === true
      || safety.real_billing_mutations_enabled === true
      || safety.real_trust_publish_enabled === true
  };
}

function summarizeDbContract(dbContract = {}) {
  const available = isObject(dbContract) && Object.keys(dbContract).length > 0;
  const tenantColumns = Array.isArray(dbContract.tenant_columns_required)
    ? dbContract.tenant_columns_required
    : [];
  return {
    available,
    schema_version: available ? dbContract.schema_version || "unknown" : "none",
    recommended_primary_db: dbContract.recommended_primary_db || "unknown",
    table_count: Array.isArray(dbContract.tables) ? dbContract.tables.length : 0,
    api_surface_count: Array.isArray(dbContract.api_surfaces) ? dbContract.api_surfaces.length : 0,
    tenant_scoping_ready: tenantColumns.includes("organization_id") && tenantColumns.includes("project_id")
  };
}

function blocker(id, severity, message) {
  return { id, severity, message };
}

function capability(id, label, evidenceCount) {
  return { id, label, evidence_count: evidenceCount };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

