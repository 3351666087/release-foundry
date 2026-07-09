import { createHash } from "node:crypto";

import { normalizeCases } from "./report_builder.mjs";
import { buildA3TenantScope } from "./a3_tenant_scope.mjs";

export const A3_SOURCE_ARTIFACTS_SCHEMA_VERSION = "a3.source_artifacts.v1";

export function buildA3SourceArtifacts(snapshot = {}, options = {}) {
  const runFixture = snapshot.runFixture || snapshot.runs || {};
  const gradeFixture = snapshot.gradeFixture || snapshot.grades || {};
  const releaseEvidence = snapshot.releaseEvidence || snapshot.release_evidence || {};
  const evidenceReadiness = snapshot.evidenceReadiness || snapshot.evidence_readiness || {};
  const resultPersistence = snapshot.resultPersistence || snapshot.result_persistence || snapshot.resultPersistenceManifest || snapshot.result_persistence_manifest || {};
  const releaseUnblockChecklist = snapshot.releaseUnblockChecklist || snapshot.release_unblock_checklist || {};
  const crossLaneSecurityContext = snapshot.crossLaneSecurityContext || snapshot.cross_lane_security_context || {};
  const sqlStoreReport = snapshot.sqlStoreReport || snapshot.sql_store_report || {};
  const officialReadonlyManifest = snapshot.a1OfficialApiReadonlyManifest
    || snapshot.a1_official_api_readonly_manifest
    || evidenceReadiness.a1_official_api_readonly_manifest
    || {};
  const officialMutatingIndex = snapshot.a1OfficialApiMutatingIndex
    || snapshot.a1_official_api_mutating_index
    || evidenceReadiness.a1_official_api_mutating_index
    || {};
  const officialPaidMediaSummary = snapshot.a1OfficialApiPaidMediaSummary
    || snapshot.a1_official_api_paid_media_summary
    || evidenceReadiness.a1_official_api_paid_media_summary
    || {};
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
  if (hasPayload(officialReadonlyManifest)) {
    artifacts.push(sourceArtifact("a1_official_api_readonly_manifest", "A1", ["OfficialApiReadonlyManifest"], officialReadonlyManifest, {
      source,
      tenantScope,
      recordCount: officialReadonlyManifest.read_step_count || 1,
      requiredBy: ["official_api_calibration", "evidence_readiness", "audit_export"]
    }));
  }
  if (hasPayload(officialMutatingIndex)) {
    artifacts.push(sourceArtifact("a1_official_api_mutating_index", "A1", ["OfficialApiMutatingIndex"], officialMutatingIndex, {
      source,
      tenantScope,
      recordCount: officialMutatingIndex.record_count || officialMutatingIndex.total_steps || 1,
      requiredBy: ["official_api_calibration", "quota_triage", "audit_export"]
    }));
  }
  if (hasPayload(officialPaidMediaSummary)) {
    artifacts.push(sourceArtifact("a1_official_api_paid_media_summary", "A1", ["OfficialApiPaidMediaSummary"], officialPaidMediaSummary, {
      source,
      tenantScope,
      recordCount: officialPaidMediaSummary.total_step_count || officialPaidMediaSummary.estimated_call_count || 1,
      requiredBy: ["media_evidence", "paid_media_claims", "audit_export"]
    }));
  }
  if (hasPayload(resultPersistence)) {
    artifacts.push(sourceArtifact("a2_result_persistence_manifest", "A2", ["ResultPersistenceManifest"], resultPersistence, {
      source,
      tenantScope,
      recordCount: resultPersistence.record_count || (Array.isArray(resultPersistence.records) ? resultPersistence.records.length : 1),
      requiredBy: ["report_export", "artifact_registry", "audit_export"]
    }));
  }
  if (hasPayload(releaseUnblockChecklist)) {
    artifacts.push(sourceArtifact("a2_release_unblock_checklist", "A2", ["ReleaseUnblockChecklist"], releaseUnblockChecklist, {
      source,
      tenantScope,
      recordCount: Array.isArray(releaseUnblockChecklist.gate_items) ? releaseUnblockChecklist.gate_items.length : 1,
      requiredBy: ["review_workflow", "release_war_room", "report_export"]
    }));
  }
  if (hasPayload(crossLaneSecurityContext)) {
    artifacts.push(sourceArtifact("a2_cross_lane_security_context", "A2", ["CrossLaneSecurityContext"], crossLaneSecurityContext, {
      source,
      tenantScope,
      recordCount: Array.isArray(crossLaneSecurityContext.a2_security_followups) ? crossLaneSecurityContext.a2_security_followups.length : 1,
      requiredBy: ["auth_rbac_boundary", "security_audit", "release_policy"]
    }));
  }
  if (hasPayload(sqlStoreReport)) {
    artifacts.push(sourceArtifact("a2_sql_store_report", "A2", ["SqlStoreReport"], sqlStoreReport, {
      source,
      tenantScope,
      recordCount: Object.values(sqlStoreReport.table_counts || {}).reduce((sum, value) => sum + (Number(value) || 0), 0) || 1,
      requiredBy: ["db_backed_reports", "failure_analytics", "audit_export"]
    }));
  }

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

function hasPayload(value = {}) {
  return value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length > 0;
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
