import { createHash } from "node:crypto";

export const A3_MULTIMODAL_RELEASE_CASE_EVIDENCE_INTAKE_SCHEMA_VERSION =
  "a3.a2_multimodal_release_case_evidence_intake.v1";
export const A3_MULTIMODAL_RELEASE_CASE_EVIDENCE_SCHEMA_VERSION =
  "a3.multimodal_release_case_evidence.v1";

const ENVELOPE_FIELDS = [
  "schema_version",
  "source_commit_alias",
  "source_artifact_id",
  "source_calibration_hash",
  "release_summary_evidence_hash",
  "control_policy_evidence_hash",
  "generated_at",
  "taxonomy",
  "summary",
  "cases",
  "authority_boundary",
  "safety"
];
const SUMMARY_FIELDS = [
  "eligible_count",
  "detected_count",
  "missed_count",
  "sensitivity",
  "minimum_sensitivity",
  "quality_state"
];
const CASE_FIELDS = [
  "case_id",
  "expected_risk",
  "observed_risk",
  "outcome",
  "artifact_hash",
  "response_hash",
  "media_type",
  "latency_seconds",
  "repeat"
];
const AUTHORITY_FIELDS = ["release_authority", "provider_is_truth", "a3_recomputed_a2_decision"];
const SAFETY_FIELDS = [
  "public_safe",
  "raw_media_included",
  "raw_provider_payload_included",
  "signed_url_included",
  "secret_included"
];
const SECRET_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b/,
  /\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{12,}\b/,
  /\bBearer\s+[A-Za-z0-9._~-]{12,}\b/i,
  /\bCookie\s*:\s*[^\s]{12,}/i,
  /\b(?:postgres(?:ql)?|mysql):\/\/[^\s"']+/i,
  /https?:\/\/[^\s"']+/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /C:\\Users\\/i
];

export function validateA2MultimodalReleaseCaseEvidence(value = {}) {
  const details = [];
  if (!isRecord(value)) return invalid([{ field: "case_evidence", issue: "object_required" }]);
  exactFields(value, ENVELOPE_FIELDS, "case_evidence", details);
  if (value.schema_version !== A3_MULTIMODAL_RELEASE_CASE_EVIDENCE_INTAKE_SCHEMA_VERSION) {
    details.push({ field: "schema_version", issue: "unsupported_schema_version" });
  }
  if (!gitAlias(value.source_commit_alias)) details.push({ field: "source_commit_alias", issue: "git_commit_alias_required" });
  if (!safeIdentifier(value.source_artifact_id)) details.push({ field: "source_artifact_id", issue: "safe_identifier_required" });
  for (const field of ["source_calibration_hash", "release_summary_evidence_hash", "control_policy_evidence_hash"]) {
    if (!isHash(value[field])) details.push({ field, issue: "sha256_required" });
  }
  if (!validIsoDate(value.generated_at)) details.push({ field: "generated_at", issue: "iso_datetime_required" });
  if (value.taxonomy !== "cross_modal_conflict") details.push({ field: "taxonomy", issue: "unsupported_taxonomy" });
  validateSummary(value.summary, details);
  validateCases(value.cases, value.summary, value.taxonomy, details);
  validateAuthority(value.authority_boundary, details);
  validateSafety(value.safety, details);
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "case_evidence", issue: "sensitive_or_external_material_forbidden" });
  }
  return {
    valid: details.length === 0,
    details,
    payload_hash: `sha256:${sha256(stableJson(value))}`
  };
}

export function buildA3MultimodalReleaseCaseEvidence(value = {}, options = {}) {
  const validation = validateA2MultimodalReleaseCaseEvidence(value);
  const base = {
    schema_version: A3_MULTIMODAL_RELEASE_CASE_EVIDENCE_SCHEMA_VERSION,
    source: options.source || "unknown",
    source_commit_alias: value.source_commit_alias || null,
    source_artifact_id: value.source_artifact_id || null,
    tenant_scope: normalizeScope(options.tenantScope || options.tenant_scope || options),
    release_authority: false,
    a2_decision_recomputed: false,
    release_decision_changed: false,
    production_ready: false
  };
  if (!validation.valid) {
    return {
      ...base,
      available: false,
      status: "invalid_upstream_case_evidence",
      integrity: { status: "failed", finding_count: validation.details.length, findings: validation.details },
      safety: publicSafety(),
      recommendation_code: "repair_round52_case_evidence_contract"
    };
  }

  const cases = value.cases.map((item) => ({
    case_id: item.case_id,
    taxonomy: value.taxonomy,
    outcome: item.outcome,
    expected_risk: true,
    observed_risk: item.observed_risk,
    latency_seconds: item.latency_seconds,
    repeat: item.repeat,
    media_evidence: {
      media_type: item.media_type,
      artifact_hash: item.artifact_hash,
      raw_media_available: false,
      signed_url_available: false,
      access_audit_required: true
    },
    response_evidence: {
      response_hash: item.response_hash,
      raw_response_available: false
    }
  }));
  const missedCases = cases.filter((item) => item.outcome === "missed");
  return {
    ...base,
    available: true,
    status: missedCases.length ? "attention_required" : "case_evidence_complete_non_authoritative",
    capability_state: options.capabilityState || "peer_branch_public_safe_case_evidence_not_merged",
    integrity: {
      status: "passed",
      finding_count: 0,
      findings: [],
      a3_computed_payload_hash: validation.payload_hash,
      source_calibration_hash: value.source_calibration_hash,
      release_summary_evidence_hash: value.release_summary_evidence_hash,
      control_policy_evidence_hash: value.control_policy_evidence_hash
    },
    summary: {
      taxonomy: value.taxonomy,
      eligible_count: value.summary.eligible_count,
      detected_count: value.summary.detected_count,
      missed_count: value.summary.missed_count,
      sensitivity: value.summary.sensitivity,
      minimum_sensitivity: value.summary.minimum_sensitivity,
      quality_state: value.summary.quality_state,
      hash_bound_case_count: cases.length,
      raw_media_count: 0,
      signed_url_count: 0
    },
    affected_cases: cases,
    missed_case_ids: missedCases.map((item) => item.case_id),
    evidence_boundary: {
      projection_mode: "hash_only",
      media_access_state: "metadata_only_no_signed_url",
      raw_media_included: false,
      raw_provider_payload_included: false,
      access_audit_required: true
    },
    authority_boundary: {
      a1_media_delivery_authority: "A1",
      a2_case_quality_authority: "A2",
      a3_triage_projection_authority: "A3",
      provider_is_truth: false,
      a2_decision_recomputed: false,
      release_authority: false,
      production_ready: false
    },
    safety: publicSafety(),
    recommendation_code: missedCases.length
      ? "review_missed_cross_modal_cases_and_recalibrate_a2"
      : "retain_hash_bound_cases_for_release_audit"
  };
}

function validateSummary(value, details) {
  const prefix = "summary";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, SUMMARY_FIELDS, prefix, details);
  for (const field of ["eligible_count", "detected_count", "missed_count"]) {
    if (!nonNegativeInteger(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
  }
  if (nonNegativeInteger(value.detected_count) && nonNegativeInteger(value.missed_count)
    && value.eligible_count !== value.detected_count + value.missed_count) {
    details.push({ field: `${prefix}.eligible_count`, issue: "detected_missed_conservation_failed" });
  }
  if (!probability(value.sensitivity) || !probability(value.minimum_sensitivity)) {
    details.push({ field: prefix, issue: "probability_required" });
  } else if (value.eligible_count > 0 && !closeNumber(value.sensitivity, value.detected_count / value.eligible_count)) {
    details.push({ field: `${prefix}.sensitivity`, issue: "count_ratio_mismatch" });
  }
  const expectedState = value.sensitivity >= value.minimum_sensitivity ? "qualified" : "blocked";
  if (value.quality_state !== expectedState) details.push({ field: `${prefix}.quality_state`, issue: "derived_quality_state_mismatch" });
}

function validateCases(value, summary, taxonomy, details) {
  const prefix = "cases";
  if (!Array.isArray(value) || !value.length || value.length > 100) {
    details.push({ field: prefix, issue: "bounded_non_empty_array_required" });
    return;
  }
  const caseIds = new Set();
  const artifactHashes = new Set();
  let detected = 0;
  let missed = 0;
  value.forEach((item, index) => {
    const itemPrefix = `${prefix}[${index}]`;
    if (!isRecord(item)) return details.push({ field: itemPrefix, issue: "object_required" });
    exactFields(item, CASE_FIELDS, itemPrefix, details);
    if (!safeIdentifier(item.case_id)) details.push({ field: `${itemPrefix}.case_id`, issue: "safe_identifier_required" });
    if (caseIds.has(item.case_id)) details.push({ field: `${itemPrefix}.case_id`, issue: "duplicate" });
    caseIds.add(item.case_id);
    if (item.expected_risk !== true) details.push({ field: `${itemPrefix}.expected_risk`, issue: "must_be_true" });
    if (typeof item.observed_risk !== "boolean") details.push({ field: `${itemPrefix}.observed_risk`, issue: "boolean_required" });
    const expectedOutcome = item.observed_risk === true ? "detected" : "missed";
    if (item.outcome !== expectedOutcome) details.push({ field: `${itemPrefix}.outcome`, issue: "derived_outcome_mismatch" });
    if (expectedOutcome === "detected") detected += 1;
    else missed += 1;
    for (const field of ["artifact_hash", "response_hash"]) {
      if (!isHash(item[field])) details.push({ field: `${itemPrefix}.${field}`, issue: "sha256_required" });
    }
    if (artifactHashes.has(item.artifact_hash)) details.push({ field: `${itemPrefix}.artifact_hash`, issue: "duplicate" });
    artifactHashes.add(item.artifact_hash);
    if (!/^image\/(?:png|jpeg|webp)$/.test(String(item.media_type || ""))) details.push({ field: `${itemPrefix}.media_type`, issue: "supported_image_type_required" });
    if (!nonNegativeNumber(item.latency_seconds) || item.latency_seconds > 900) details.push({ field: `${itemPrefix}.latency_seconds`, issue: "bounded_non_negative_number_required" });
    if (!Number.isInteger(item.repeat) || item.repeat < 1 || item.repeat > 100) details.push({ field: `${itemPrefix}.repeat`, issue: "bounded_positive_integer_required" });
    if (taxonomy !== "cross_modal_conflict") details.push({ field: itemPrefix, issue: "taxonomy_binding_failed" });
  });
  if (summary?.eligible_count !== value.length) details.push({ field: "summary.eligible_count", issue: "case_count_mismatch" });
  if (summary?.detected_count !== detected) details.push({ field: "summary.detected_count", issue: "case_outcome_mismatch" });
  if (summary?.missed_count !== missed) details.push({ field: "summary.missed_count", issue: "case_outcome_mismatch" });
}

function validateAuthority(value, details) {
  if (!isRecord(value)) return details.push({ field: "authority_boundary", issue: "object_required" });
  exactFields(value, AUTHORITY_FIELDS, "authority_boundary", details);
  for (const field of AUTHORITY_FIELDS) if (value[field] !== false) details.push({ field: `authority_boundary.${field}`, issue: "must_be_false" });
}

function validateSafety(value, details) {
  if (!isRecord(value)) return details.push({ field: "safety", issue: "object_required" });
  exactFields(value, SAFETY_FIELDS, "safety", details);
  if (value.public_safe !== true) details.push({ field: "safety.public_safe", issue: "must_be_true" });
  for (const field of SAFETY_FIELDS.filter((item) => item !== "public_safe")) {
    if (value[field] !== false) details.push({ field: `safety.${field}`, issue: "must_be_false" });
  }
}

function publicSafety() {
  return {
    public_safe: true,
    hash_only_case_evidence: true,
    raw_media_included: false,
    raw_provider_payload_included: false,
    raw_response_included: false,
    signed_url_included: false,
    secret_included: false
  };
}

function exactFields(value, allowed, prefix, details) {
  if (!isRecord(value)) return;
  const allowedSet = new Set(allowed);
  for (const field of Object.keys(value)) if (!allowedSet.has(field)) details.push({ field: `${prefix}.${field}`, issue: "unexpected_field" });
  for (const field of allowed) if (!(field in value)) details.push({ field: `${prefix}.${field}`, issue: "required" });
}

function normalizeScope(value = {}) {
  const nested = value.tenant_scope || value.tenantScope || {};
  return {
    organization_id: value.organization_id || value.organizationId || nested.organization_id || "org-local",
    tenant_id: value.tenant_id || value.tenantId || nested.tenant_id || "tenant-local",
    workspace_id: value.workspace_id || value.workspaceId || nested.workspace_id || "workspace-local",
    project_id: value.project_id || value.projectId || nested.project_id || "project-local",
    environment_id: value.environment_id || value.environmentId || nested.environment_id || "staging"
  };
}

function safeIdentifier(value) { return /^[a-z0-9][a-z0-9_.:-]{0,239}$/.test(String(value || "")); }
function gitAlias(value) { return /^[a-f0-9]{7,40}$/.test(String(value || "")); }
function isHash(value) { return /^sha256:[a-f0-9]{64}$/.test(String(value || "")); }
function validIsoDate(value) { return typeof value === "string" && value.includes("T") && !Number.isNaN(Date.parse(value)); }
function nonNegativeInteger(value) { return Number.isInteger(value) && value >= 0; }
function nonNegativeNumber(value) { return typeof value === "number" && Number.isFinite(value) && value >= 0; }
function probability(value) { return nonNegativeNumber(value) && value <= 1; }
function closeNumber(value, expected) { return typeof value === "number" && Math.abs(value - expected) <= 1e-9; }
function isRecord(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function invalid(details) { return { valid: false, details, payload_hash: null }; }
function sha256(value) { return createHash("sha256").update(String(value)).digest("hex"); }
function stableJson(value) { return JSON.stringify(sortValue(value)); }
function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (isRecord(value)) return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, sortValue(item)]));
  return value;
}
