import { guardA3SecuritySurface } from "./a3_security_redaction_guard.mjs";

export const A3_RELEASE_DECISION_PROVENANCE_SCHEMA_VERSION = "a3.release_decision_provenance.v1";

const REQUIRED_ROLES = ["owner", "admin", "reviewer", "auditor"];
const SCOPE_FIELDS = ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"];

export function buildA3ReleaseDecisionProvenance(inputs = {}, options = {}) {
  const a1Run = inputs.a1RunResult || inputs.runResult || inputs.a1?.run_result || null;
  const a2Grades = inputs.a2GradeResults || inputs.gradeResults || inputs.a2?.grade_results || null;
  const a2Gate = inputs.a2ReleaseGate || inputs.releaseGate || inputs.a2?.release_gate || null;
  const requestedScope = explicitScope(options.tenantScope || inputs.tenant_scope || {});
  const auth = options.auth || inputs.auth || {};
  const missingContracts = validateRequiredContracts(a1Run, a2Grades, a2Gate);
  const blockers = missingContracts.map((contract) => blocker(
    "missing_contract",
    `Required upstream contract is missing or invalid: ${contract}.`,
    [contract]
  ));

  if (Object.keys(requestedScope).length !== SCOPE_FIELDS.length) {
    blockers.push(blocker("scope_incomplete", "All tenant scope fields are required for a release decision provenance read.", SCOPE_FIELDS));
  }
  if (auth.trusted !== true || !["hosted_session", "service_account"].includes(auth.auth_state)) {
    blockers.push(blocker("auth_untrusted", "Release provenance requires a trusted hosted identity or service-account backend.", ["a1.identity_backend"]));
  }

  const artifacts = [
    ["a1.run_result", a1Run],
    ["a2.grade_results", a2Grades],
    ["a2.release_gate", a2Gate],
    ["a3.review_workflow", inputs.reviewWorkflow],
    ["a3.shareable_report", inputs.shareableReport],
    ["a3.usage_ledger", inputs.usageLedger],
    ["a3.billing_visibility", inputs.billingVisibility],
    ["a3.audit", inputs.audit]
  ];
  for (const [label, artifact] of artifacts) {
    if (!artifact) continue;
    for (const mismatch of scopeMismatches(artifact, requestedScope)) {
      blockers.push(blocker("scope_mismatch", `${label} ${mismatch.field} does not match the requested scope.`, [label, mismatch.field]));
    }
  }

  const graph = buildGraph(a1Run, a2Grades, a2Gate, inputs, blockers);
  const guarded = guardA3SecuritySurface(graph, {
    surface: "json_report",
    tenantScope: requestedScope,
    actor: options.actor || inputs.actor || {},
    requiredRoles: options.requiredRoles || REQUIRED_ROLES,
    requireActorTenant: true,
    requireTenantMatch: true
  });
  if (!guarded.allowed) {
    for (const reason of [...guarded.tenant.reasons, ...guarded.rbac.reasons]) {
      blockers.push(blocker(reason.includes("mismatch") ? "scope_mismatch" : "auth_rbac_denied", `Security guard denied provenance visibility: ${reason}.`, [reason]));
    }
    if (guarded.redaction.residual_finding_count > 0) {
      blockers.push(blocker("redaction_failed", "Sensitive material remained after redaction.", []));
    }
  }

  const uniqueBlockers = dedupe(blockers);
  const ready = uniqueBlockers.length === 0;
  return {
    schema_version: A3_RELEASE_DECISION_PROVENANCE_SCHEMA_VERSION,
    status: ready ? "ready" : "blocked",
    fail_closed: true,
    read_only: true,
    source_of_truth: {
      a1: "RunResult, Observation/TraceEvent, ToolCall, usage/billing/storage references",
      a2: "GradeResult, FailureAnalysis, ReleaseGate, release/security/SQL verification",
      a3: "additive read-only provenance and visibility only"
    },
    tenant_scope: requestedScope,
    release_decision: ready ? a2Gate.decision : "block",
    upstream_release_decision: validGate(a2Gate) ? a2Gate.decision : null,
    decision_authority: ready ? "a2.release_gate.v1" : "fail_closed_by_a3_provenance",
    missing_contracts: [...new Set(missingContracts)].sort(),
    blockers: uniqueBlockers,
    nodes: guarded.value.nodes || [],
    edges: guarded.value.edges || [],
    governance: {
      tenant: { required: true, matched: !uniqueBlockers.some((item) => item.type.startsWith("scope_")) },
      auth: {
        required: true,
        allowed: auth.trusted === true
          && ["hosted_session", "service_account"].includes(auth.auth_state)
          && guarded.tenant.allowed === true,
        auth_state: auth.auth_state || "untrusted_local_context",
        trusted_identity_backend: auth.trusted === true
      },
      rbac: { required_roles: REQUIRED_ROLES, allowed: guarded.rbac.allowed === true },
      usage: visibility(inputs.usageLedger, "usage:read"),
      billing: visibility(inputs.billingVisibility, "billing:read"),
      audit: visibility(inputs.audit, "audit:read"),
      redaction: {
        status: guarded.redaction.status,
        replacement_count: guarded.redaction.replacement_count,
        residual_finding_count: guarded.redaction.residual_finding_count,
        raw_secret_values_allowed: false
      }
    },
    semantics: {
      a1_mutated: false,
      a2_mutated: false,
      release_decision_recomputed: false,
      missing_evidence_may_be_inferred: false,
      visibility_does_not_grant_authority: true
    }
  };
}

function buildGraph(run, gradeReport, gate, inputs, blockers) {
  const nodes = [];
  const edges = [];
  if (validRun(run)) {
    const runId = run.run_id;
    nodes.push(node(`run:${runId}`, "run", "a1", {
      run_id: runId,
      dataset_id: run.dataset_id,
      status: run.status,
      trace_completeness: run.trace_completeness,
      storage_refs: publicRefs(run.metadata?.artifact_refs || run.artifact_refs)
    }));
    for (const caseItem of run.cases) {
      const caseId = caseItem.case_id;
      const caseNodeId = `case:${caseId}`;
      nodes.push(node(caseNodeId, "case", "a1", {
        run_id: runId,
        case_id: caseId,
        scenario_id: caseItem.scenario_id,
        status: caseItem.status
      }));
      edges.push(edge(`run:${runId}`, caseNodeId, "contains"));
      const traces = traceRecords(caseItem);
      if (traces.length === 0) {
        blockers.push(blocker("missing_evidence", `A1 case ${caseId} has no trace or observation evidence.`, [caseId]));
      }
      for (const [index, trace] of traces.entries()) {
        const traceId = trace.event_id || trace.observation_id || `${caseId}:${index}`;
        const traceNodeId = `trace:${traceId}`;
        nodes.push(node(traceNodeId, "trace", "a1", {
          trace_id: traceId,
          run_id: trace.run_id || runId,
          case_id: trace.case_id || caseId,
          event_type: trace.event_type,
          status: trace.status || trace.observation?.status,
          text: trace.observation?.text || trace.content || null
        }));
        edges.push(edge(caseNodeId, traceNodeId, "emits"));
        for (const [toolIndex, tool] of toolCalls(trace).entries()) {
          const toolId = tool.tool_call_id || tool.id || `${traceId}:${toolIndex}`;
          const toolNodeId = `tool_call:${toolId}`;
          nodes.push(node(toolNodeId, "tool_call", "a1", {
            tool_call_id: toolId,
            name: tool.name || tool.tool || null,
            arguments: tool.arguments || tool.args || null,
            status: tool.status || trace.status || trace.observation?.status || null
          }));
          edges.push(edge(traceNodeId, toolNodeId, "records"));
        }
      }
    }
  }

  if (validGrades(gradeReport)) {
    for (const grade of gradeReport.grade_results) {
      const gradeId = `grade:${grade.case_id}`;
      nodes.push(node(gradeId, "grade", "a2", {
        case_id: grade.case_id,
        scenario_id: grade.scenario_id,
        passed: grade.passed,
        score: grade.score,
        primary_failure_class: grade.primary_failure_class
      }));
      const caseNodeId = `case:${grade.case_id}`;
      if (nodes.some((item) => item.id === caseNodeId)) edges.push(edge(caseNodeId, gradeId, "graded_by"));
      else blockers.push(blocker("broken_reference", `A2 grade references unknown A1 case ${grade.case_id}.`, [grade.case_id]));
      linkJudgeEvidence(grade, gradeId, nodes, edges, blockers);

      if (grade.passed === false || grade.primary_failure_class !== "none") {
        const failureId = `failure:${grade.case_id}`;
        const analysis = grade.judge_results?.[0]?.failure_analysis || {};
        nodes.push(node(failureId, "failure", "a2", {
          case_id: grade.case_id,
          failure_class: grade.primary_failure_class,
          severity: analysis.severity || null,
          safety_blocking: analysis.safety_blocking === true,
          summary: analysis.summary || null
        }));
        edges.push(edge(gradeId, failureId, "explains"));
      }
    }
  }

  if (validGate(gate)) {
    const gateId = `release_gate:${gate.report_id}`;
    nodes.push(node(gateId, "release_decision", "a2", {
      report_id: gate.report_id,
      decision: gate.decision,
      exit_code: gate.exit_code,
      risk_score: gate.risk_score,
      blocker_count: Array.isArray(gate.blockers) ? gate.blockers.length : null,
      evidence_refs: publicRefs(gate.evidence_refs)
    }));
    for (const grade of gradeReport?.grade_results || []) edges.push(edge(`grade:${grade.case_id}`, gateId, "informs"));
    for (const grade of gradeReport?.grade_results || []) {
      if (grade.passed === false || grade.primary_failure_class !== "none") edges.push(edge(`failure:${grade.case_id}`, gateId, "supports"));
    }
    addVisibilityNode(nodes, edges, gateId, "review", inputs.reviewWorkflow, "reviews");
    addVisibilityNode(nodes, edges, gateId, "share", inputs.shareableReport, "exposes");
    addVisibilityNode(nodes, edges, gateId, "audit", inputs.audit, "records");
  }

  const runNode = nodes.find((item) => item.type === "run");
  const usageId = addVisibilityNode(nodes, edges, runNode?.id, "usage", inputs.usageLedger, "meters");
  if (usageId) addVisibilityNode(nodes, edges, usageId, "billing", inputs.billingVisibility, "bills_from");
  return { nodes: dedupeById(nodes), edges: dedupeEdges(edges) };
}

function validateRequiredContracts(run, grades, gate) {
  const missing = [];
  if (!validRun(run)) missing.push("a1.RunResult/releasefoundry.run_result.v1");
  if (!validGrades(grades)) missing.push("a2.grade_results.v1");
  if (!validGate(gate)) missing.push("a2.release_gate.v1");
  return missing;
}

function validRun(value) {
  return Boolean(value && value.aggregate_metrics?.schema_version === "releasefoundry.run_result.v1"
    && nonBlank(value.run_id) && nonBlank(value.dataset_id) && Array.isArray(value.cases));
}

function validGrades(value) {
  return Boolean(value && value.schema_version === "a2.grade_results.v1" && Array.isArray(value.grade_results)
    && value.grade_results.every((item) => item?.schema_version === "a2.local_judge_run.v1"
      && nonBlank(item.case_id) && typeof item.passed === "boolean" && Number.isFinite(item.score)));
}

function validGate(value) {
  return Boolean(value && value.schema_version === "a2.release_gate.v1" && nonBlank(value.report_id)
    && ["pass", "warn", "block"].includes(value.decision) && Number.isInteger(value.exit_code));
}

function traceRecords(caseItem) {
  const traceEvents = Array.isArray(caseItem.trace_events) ? caseItem.trace_events : [];
  const observations = Array.isArray(caseItem.observations) ? caseItem.observations : [];
  return [...traceEvents, ...observations];
}

function toolCalls(trace) {
  if (Array.isArray(trace.tool_calls)) return trace.tool_calls;
  if (Array.isArray(trace.observation?.data?.tool_calls)) return trace.observation.data.tool_calls;
  if (trace.observation?.data && (trace.observation.data.tool_call_id || trace.observation.data.name)) return [trace.observation.data];
  return [];
}

function addVisibilityNode(nodes, edges, parentId, type, value, relation) {
  const id = `${type}:${value?.record_id || value?.report_id || value?.ledger_id || value?.manifest_id || "visibility"}`;
  nodes.push(node(id, `${type}_visibility`, "a3", {
    available: Boolean(value),
    schema_version: value?.schema_version || null,
    status: value?.status || null,
    visibility: value?.visibility || "restricted",
    public_safe: value?.metadata?.public_safe === true || value?.safety?.secret_values_included === false || false
  }));
  if (parentId) edges.push(edge(parentId, id, relation));
  return id;
}

function scopeMismatches(artifact, expected) {
  const candidates = [
    artifact,
    artifact.tenant_scope,
    artifact.scope,
    artifact.metadata,
    artifact.release_candidate,
    artifact.scenario_selection_gate,
    artifact.payload
  ].filter(Boolean).map(explicitScope);
  const mismatches = [];
  for (const actual of candidates) {
    for (const field of SCOPE_FIELDS) {
      if (actual[field] !== undefined && expected[field] !== undefined && String(actual[field]) !== String(expected[field])) {
        mismatches.push({ field, expected: expected[field], actual: actual[field] });
      }
    }
  }
  return [...new Map(mismatches.map((item) => [`${item.field}:${item.actual}`, item])).values()];
}

function linkJudgeEvidence(grade, gradeId, nodes, edges, blockers) {
  for (const judge of grade.judge_results || []) {
    const evidence = judge?.evidence || {};
    for (const traceId of publicRefs(evidence.trace_event_ids)) {
      const sourceId = `trace:${traceId}`;
      if (nodes.some((item) => item.id === sourceId)) edges.push(edge(sourceId, gradeId, "supports_grade"));
      else blockers.push(blocker("broken_reference", `A2 grade references unknown A1 trace ${traceId}.`, [traceId, grade.case_id]));
    }
    for (const toolId of publicRefs(evidence.tool_call_ids)) {
      const sourceId = `tool_call:${toolId}`;
      if (nodes.some((item) => item.id === sourceId)) edges.push(edge(sourceId, gradeId, "supports_grade"));
      else blockers.push(blocker("broken_reference", `A2 grade references unknown A1 tool call ${toolId}.`, [toolId, grade.case_id]));
    }
  }
}

function explicitScope(value = {}) {
  const source = value.tenant_scope || value.tenantScope || value;
  const result = {};
  for (const field of SCOPE_FIELDS) {
    const camel = field.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
    const found = source[field] ?? source[camel];
    if (found !== undefined && found !== null && found !== "") result[field] = String(found);
  }
  return result;
}

function visibility(value, permission) {
  return { available: Boolean(value), required_permission: permission, visibility: value?.visibility || "restricted", read_only: true };
}

function node(id, type, lane, attributes) {
  return { id, type, lane, attributes };
}

function edge(from, to, relation) {
  return { from, to, relation };
}

function blocker(type, message, evidenceRefs) {
  return { type, severity: "blocking", message, evidence_refs: evidenceRefs };
}

function publicRefs(value) {
  return (Array.isArray(value) ? value : []).filter((item) => typeof item === "string").slice(0, 32);
}

function nonBlank(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function dedupe(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.type}:${item.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dedupeById(items) {
  return [...new Map(items.map((item) => [item.id, item])).values()];
}

function dedupeEdges(items) {
  return [...new Map(items.map((item) => [`${item.from}:${item.relation}:${item.to}`, item])).values()];
}
