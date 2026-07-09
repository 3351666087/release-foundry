import { createHash } from "node:crypto";

import { normalizeCases } from "./report_builder.mjs";
import { buildA3TenantScope } from "./a3_tenant_scope.mjs";

export const A3_SOURCE_ARTIFACTS_SCHEMA_VERSION = "a3.source_artifacts.v1";

export function buildA3SourceArtifacts(snapshot = {}, options = {}) {
  const runFixture = snapshot.runFixture || snapshot.runs || {};
  const gradeFixture = snapshot.gradeFixture || snapshot.grades || {};
  const releaseEvidence = snapshot.releaseEvidence || snapshot.release_evidence || {};
  const cases = normalizeCases(runFixture, gradeFixture);
  const grades = extractGradeResults(gradeFixture);
  const tenantScope = buildA3TenantScope(options, snapshot);
  const source = options.source || snapshot.source || "unknown";
  const artifacts = [
    sourceArtifact("a1_run_result", "A1", ["RunResult"], runFixture, {
      source,
      tenantScope,
      recordCount: extractRunRecords(runFixture).length,
      requiredBy: ["run_list", "case_detail", "release_evidence", "report_export"]
    }),
    sourceArtifact("a1_trace_event_batch", "A1", ["Trace", "Observation"], cases.flatMap((item) => item.trace_events || item.observations || []), {
      source,
      tenantScope,
      recordCount: cases.reduce((sum, item) => sum + (item.trace_events?.length || item.observations?.length || 0), 0),
      requiredBy: ["trace_timeline", "tool_call_diff", "incident_replay"]
    }),
    sourceArtifact("a1_tool_call_batch", "A1", ["ToolCall"], cases.flatMap((item) => [
      ...(item.expected?.tool_calls || []),
      ...(item.actual?.tool_calls || [])
    ]), {
      source,
      tenantScope,
      recordCount: cases.reduce((sum, item) => sum + (item.expected?.tool_calls?.length || 0) + (item.actual?.tool_calls?.length || 0), 0),
      requiredBy: ["expected_vs_actual", "tool_call_diff", "review_workflow"]
    }),
    sourceArtifact("a2_grade_result", "A2", ["GradeResult", "Judge"], gradeFixture, {
      source,
      tenantScope,
      recordCount: grades.length,
      requiredBy: ["failure_cluster", "release_gate", "review_workflow", "report_export"]
    }),
    sourceArtifact("a2_release_gate", "A2", ["ReleaseGate", "FailureTaxonomy"], releaseEvidence, {
      source,
      tenantScope,
      recordCount: releaseEvidence && Object.keys(releaseEvidence).length ? 1 : 0,
      requiredBy: ["release_war_room", "github_pr_gate", "audit_export"]
    })
  ];

  return {
    schema_version: A3_SOURCE_ARTIFACTS_SCHEMA_VERSION,
    source,
    tenant_scope: tenantScope,
    source_artifact_count: artifacts.length,
    hash_algorithm: "sha256",
    artifacts,
    safety: {
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      source_hashes_only: true
    }
  };
}

function sourceArtifact(type, lane, contracts, payload, options = {}) {
  const payloadHash = sha256(stableJson(sanitizeForHash(payload)));
  return {
    source_artifact_id: `${options.source || "unknown"}:${type}:${payloadHash.slice(0, 12)}`,
    artifact_type: type,
    source_lane: lane,
    source_contracts: contracts,
    tenant_scope: options.tenantScope,
    content_hash: payloadHash,
    hash_algorithm: "sha256",
    record_count: options.recordCount || 0,
    redaction_status: "hash_only",
    raw_payload_embedded: false,
    required_by_a3_surfaces: options.requiredBy || [],
    a3_mutates_source_semantics: false
  };
}

function extractRunRecords(runFixture = {}) {
  if (Array.isArray(runFixture)) {
    return runFixture.flatMap(extractRunRecords);
  }
  if (Array.isArray(runFixture.runs)) {
    return runFixture.runs;
  }
  if (runFixture.run_id && Array.isArray(runFixture.cases)) {
    return [runFixture];
  }
  return [];
}

function extractGradeResults(gradeFixture = {}) {
  if (Array.isArray(gradeFixture)) {
    return gradeFixture.flatMap(extractGradeResults);
  }
  if (Array.isArray(gradeFixture.grade_results)) {
    return gradeFixture.grade_results;
  }
  if (gradeFixture.grade_result && typeof gradeFixture.grade_result === "object") {
    return [gradeFixture.grade_result];
  }
  if (gradeFixture.case_id && (
    Array.isArray(gradeFixture.judge_results)
    || "passed" in gradeFixture
    || "score" in gradeFixture
    || "primary_failure_class" in gradeFixture
  )) {
    return [gradeFixture];
  }
  return [];
}

function sanitizeForHash(value = {}) {
  return JSON.parse(JSON.stringify(value || {}, (key, item) => (
    /authorization|cookie|secret|token|password|api_key|signed_url|email/i.test(key)
      && typeof item !== "boolean"
      && typeof item !== "number"
      ? "[REDACTED]"
      : item
  )));
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortForStableJson(item)]));
  }
  return value;
}
