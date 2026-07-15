import { createHash } from "node:crypto";

export const A3_MULTIMODAL_RELEASE_READINESS_INTAKE_SCHEMA_VERSION =
  "a3.a2_multimodal_release_readiness_intake.v1";
export const A3_MULTIMODAL_RELEASE_READINESS_SCHEMA_VERSION =
  "a3.multimodal_release_readiness.v1";
export const A2_MULTIMODAL_PUBLIC_SUMMARY_ROUND52_SCHEMA_VERSION =
  "a2.multimodal_public_summary.round52.v1";

const ENVELOPE_FIELDS = [
  "schema_version",
  "source_commit_alias",
  "a1_peer_boundary",
  "public_summary",
  "shared_candidate_verification",
  "release_authority",
  "public_safe",
  "raw_provider_payload_included",
  "raw_identity_receipt_included"
];
const SUMMARY_FIELDS = [
  "binding",
  "cloud_control_run",
  "control_policy",
  "endpoint_region",
  "generated_at",
  "high_quality_local_candidate",
  "interpretation",
  "model_id",
  "multi_repeat",
  "persistence",
  "provider_id",
  "public_safe",
  "raw_provider_payload_included",
  "raw_provider_text_included",
  "raw_request_id_included",
  "release_authority",
  "review_binding",
  "schema_version",
  "secret_included"
];
const CLOUD_FIELDS = [
  "blockers",
  "eligible_count",
  "evidence_hash",
  "latency_seconds",
  "qualification_state",
  "quality"
];
const LATENCY_FIELDS = ["count", "max", "median", "min", "p95_nearest_rank"];
const QUALITY_FIELDS = ["balanced_accuracy", "sensitivity", "specificity"];
const CONTROL_FIELDS = [
  "evidence_hash",
  "quality_blockers",
  "quality_state",
  "safe_control_assessment",
  "taxonomy_assessments"
];
const SAFE_CONTROL_FIELDS = [
  "eligible_count",
  "false_positive_count",
  "maximum_false_positive_count",
  "minimum_eligible_count",
  "passed"
];
const TAXONOMY_FIELDS = [
  "detected_count",
  "eligible_count",
  "minimum_eligible_count",
  "minimum_sensitivity",
  "passed",
  "sensitivity"
];
const LOCAL_FIELDS = [
  "blockers",
  "completed_profile_count",
  "model_digest",
  "model_id",
  "probe_evidence_hash",
  "promotion_evidence_hash",
  "qualification_state",
  "runtime_promotion_state"
];
const INTERPRETATION_FIELDS = [
  "promotion_permitted",
  "provider_failure_or_invalid_output_can_pass",
  "reason"
];
const REPEAT_FIELDS = [
  "all_repeats_fresh",
  "evidence_hash",
  "promotion_eligible",
  "quality_blockers",
  "quality_state",
  "schema_version",
  "stability_blockers",
  "stability_state"
];
const PERSISTENCE_FIELDS = [
  "evidence_hash",
  "real_postgresql_proof_state",
  "same_round_real_postgresql_verified"
];
const REVIEW_FIELDS = [
  "collection_hash",
  "collection_state",
  "conservation_hash",
  "pending_queue_receipt_count",
  "verification_state"
];
const A1_BOUNDARY_FIELDS = [
  "source_commit_alias",
  "capability",
  "a3_client_route_status",
  "aggregate_readiness_available",
  "raw_identity_receipt_included",
  "production_identity_verified"
];
const CANDIDATE_FIELDS = ["blockers", "verified"];
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

export function validateA2MultimodalReleaseReadinessEnvelope(value = {}) {
  const details = [];
  if (!isRecord(value)) return invalid([{ field: "release_readiness_evidence", issue: "object_required" }]);
  exactFields(value, ENVELOPE_FIELDS, "release_readiness_evidence", details);
  if (value.schema_version !== A3_MULTIMODAL_RELEASE_READINESS_INTAKE_SCHEMA_VERSION) {
    details.push({ field: "schema_version", issue: "unsupported_schema_version" });
  }
  if (!gitAlias(value.source_commit_alias)) {
    details.push({ field: "source_commit_alias", issue: "git_commit_alias_required" });
  }
  validateA1Boundary(value.a1_peer_boundary, details);
  validatePublicSummary(value.public_summary, details);
  validateCandidate(value.shared_candidate_verification, details);
  requireSafety(value, details);
  validateCrossArtifactFacts(value, details);
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "release_readiness_evidence", issue: "sensitive_or_external_material_forbidden" });
  }
  return {
    valid: details.length === 0,
    details,
    payload_hash: `sha256:${sha256(stableJson(value))}`
  };
}

export function buildA3MultimodalReleaseReadiness(value = {}, options = {}) {
  const validation = validateA2MultimodalReleaseReadinessEnvelope(value);
  const summary = value.public_summary || {};
  const tenantScope = normalizeScope(options.tenantScope || options.tenant_scope || options);
  const base = {
    schema_version: A3_MULTIMODAL_RELEASE_READINESS_SCHEMA_VERSION,
    source: options.source || "unknown",
    source_commit_alias: value.source_commit_alias || options.sourceCommitAlias || null,
    a1_peer_commit_alias: value.a1_peer_boundary?.source_commit_alias || null,
    source_contract: summary.schema_version || "missing",
    tenant_scope: tenantScope,
    release_authority: false,
    a2_decision_recomputed: false,
    release_decision_changed: false,
    production_ready: false
  };
  if (!validation.valid) {
    return {
      ...base,
      available: false,
      status: "invalid_upstream_contract",
      integrity: {
        status: "failed",
        finding_count: validation.details.length,
        findings: validation.details
      },
      authority_boundary: authorityBoundary(),
      safety: safetyBoundary(),
      recommendation_code: "repair_a2_round52_public_summary_contract"
    };
  }

  const cloud = summary.cloud_control_run;
  const controls = summary.control_policy;
  const safeControls = controls.safe_control_assessment;
  const taxonomy = Object.entries(controls.taxonomy_assessments)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([taxonomyId, assessment]) => ({ taxonomy_id: taxonomyId, ...assessment }));
  const local = summary.high_quality_local_candidate;
  const repeat = summary.multi_repeat;
  const review = summary.review_binding;
  const persistence = summary.persistence;
  const candidate = value.shared_candidate_verification;
  const blocked = cloud.qualification_state !== "qualified"
    || controls.quality_state !== "qualified"
    || local.runtime_promotion_state !== "qualified"
    || repeat.quality_state !== "qualified"
    || repeat.promotion_eligible !== true
    || review.collection_state !== "reviewed"
    || persistence.same_round_real_postgresql_verified !== true
    || candidate.verified !== true;

  return {
    ...base,
    available: true,
    status: blocked ? "blocked_multimodal_release_readiness" : "qualified_evidence_non_authoritative",
    capability_state: options.capabilityState || "peer_branch_public_summary_not_merged",
    integrity: {
      status: "passed",
      finding_count: 0,
      findings: [],
      a3_computed_payload_hash: validation.payload_hash
    },
    summary: {
      cloud_eligible_count: cloud.eligible_count,
      specificity: cloud.quality.specificity,
      sensitivity: cloud.quality.sensitivity,
      balanced_accuracy: cloud.quality.balanced_accuracy,
      safe_control_count: safeControls.eligible_count,
      safe_control_false_positive_count: safeControls.false_positive_count,
      taxonomy_count: taxonomy.length,
      taxonomy_eligible_count: sum(taxonomy, "eligible_count"),
      taxonomy_detected_count: sum(taxonomy, "detected_count"),
      local_completed_profile_count: local.completed_profile_count,
      repeat_quality_state: repeat.quality_state,
      repeat_stability_state: repeat.stability_state,
      human_review_state: review.collection_state,
      real_postgresql_verified: persistence.same_round_real_postgresql_verified,
      candidate_verified: candidate.verified,
      promotion_permitted: false
    },
    cloud_control: {
      provider_id: summary.provider_id,
      model_id: summary.model_id,
      endpoint_region: summary.endpoint_region,
      qualification_state: cloud.qualification_state,
      evidence_hash: cloud.evidence_hash,
      blockers: [...cloud.blockers],
      quality: { ...cloud.quality },
      latency_seconds: { ...cloud.latency_seconds }
    },
    control_policy: {
      quality_state: controls.quality_state,
      evidence_hash: controls.evidence_hash,
      blockers: [...controls.quality_blockers],
      safe_controls: { ...safeControls },
      taxonomy_assessments: taxonomy
    },
    local_runtime: {
      model_id: local.model_id,
      model_digest: local.model_digest,
      qualification_state: local.qualification_state,
      runtime_promotion_state: local.runtime_promotion_state,
      completed_profile_count: local.completed_profile_count,
      probe_evidence_hash: local.probe_evidence_hash,
      promotion_evidence_hash: local.promotion_evidence_hash,
      blockers: [...local.blockers]
    },
    repeat_evidence: {
      schema_version: repeat.schema_version,
      quality_state: repeat.quality_state,
      stability_state: repeat.stability_state,
      all_repeats_fresh: repeat.all_repeats_fresh,
      promotion_eligible: repeat.promotion_eligible,
      quality_blockers: [...repeat.quality_blockers],
      stability_blockers: [...repeat.stability_blockers],
      evidence_hash: repeat.evidence_hash
    },
    human_review: {
      collection_state: review.collection_state,
      verification_state: review.verification_state,
      pending_queue_receipt_count: review.pending_queue_receipt_count,
      collection_hash: review.collection_hash,
      conservation_hash: review.conservation_hash,
      authoritative_human_disposition_recorded: false
    },
    persistence: {
      proof_state: persistence.real_postgresql_proof_state,
      same_round_real_postgresql_verified: persistence.same_round_real_postgresql_verified,
      evidence_hash: persistence.evidence_hash
    },
    candidate_binding: {
      verified: candidate.verified,
      blockers: [...candidate.blockers]
    },
    identity_boundary: { ...value.a1_peer_boundary },
    interpretation: {
      promotion_permitted: false,
      provider_failure_or_invalid_output_can_pass: false,
      reason_code: "quality_runtime_review_persistence_and_candidate_controls_blocked"
    },
    authority_boundary: authorityBoundary(),
    safety: safetyBoundary(),
    recommendation_code: "repair_attack_sensitivity_structured_output_review_persistence_and_candidate_binding"
  };
}

function validatePublicSummary(value, details) {
  const prefix = "public_summary";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, SUMMARY_FIELDS, prefix, details);
  if (value.schema_version !== A2_MULTIMODAL_PUBLIC_SUMMARY_ROUND52_SCHEMA_VERSION) {
    details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  }
  if (!validIsoDate(value.generated_at)) details.push({ field: `${prefix}.generated_at`, issue: "iso_datetime_required" });
  if (!safeIdentifier(value.provider_id) || !safeIdentifier(value.model_id) || !safeIdentifier(value.endpoint_region)) {
    details.push({ field: prefix, issue: "safe_provider_model_region_required" });
  }
  validateBinding(value.binding, details);
  validateCloud(value.cloud_control_run, details);
  validateControlPolicy(value.control_policy, details);
  validateLocalRuntime(value.high_quality_local_candidate, details);
  validateInterpretation(value.interpretation, details);
  validateRepeat(value.multi_repeat, details);
  validatePersistence(value.persistence, details);
  validateReview(value.review_binding, details);
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
  for (const field of ["raw_provider_payload_included", "raw_provider_text_included", "raw_request_id_included", "release_authority", "secret_included"]) {
    if (value[field] !== false) details.push({ field: `${prefix}.${field}`, issue: "must_be_false" });
  }
}

function validateBinding(value, details) {
  const prefix = "public_summary.binding";
  if (!isRecord(value) || !Object.keys(value).length) {
    details.push({ field: prefix, issue: "non_empty_hash_map_required" });
    return;
  }
  for (const [key, hash] of Object.entries(value)) {
    if (!safeIdentifier(key) || !isHash(hash)) details.push({ field: `${prefix}.${key}`, issue: "safe_sha256_binding_required" });
  }
}

function validateCloud(value, details) {
  const prefix = "public_summary.cloud_control_run";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, CLOUD_FIELDS, prefix, details);
  validateReasonCodes(value.blockers, `${prefix}.blockers`, details, true);
  if (!nonNegativeInteger(value.eligible_count)) details.push({ field: `${prefix}.eligible_count`, issue: "non_negative_integer_required" });
  if (!isHash(value.evidence_hash)) details.push({ field: `${prefix}.evidence_hash`, issue: "sha256_required" });
  if (!["qualified", "blocked", "incomplete"].includes(value.qualification_state)) details.push({ field: `${prefix}.qualification_state`, issue: "unsupported_state" });
  if (value.qualification_state === "qualified" ? value.blockers?.length : !value.blockers?.length) details.push({ field: prefix, issue: "qualification_blocker_mismatch" });
  validateLatency(value.latency_seconds, value.eligible_count, details);
  const quality = value.quality;
  if (!isRecord(quality)) return details.push({ field: `${prefix}.quality`, issue: "object_required" });
  exactFields(quality, QUALITY_FIELDS, `${prefix}.quality`, details);
  for (const field of QUALITY_FIELDS) if (!probability(quality[field])) details.push({ field: `${prefix}.quality.${field}`, issue: "probability_required" });
  if (QUALITY_FIELDS.every((field) => probability(quality[field]))
    && !closeNumber(quality.balanced_accuracy, (quality.specificity + quality.sensitivity) / 2)) {
    details.push({ field: `${prefix}.quality.balanced_accuracy`, issue: "derived_balanced_accuracy_mismatch" });
  }
}

function validateLatency(value, eligibleCount, details) {
  const prefix = "public_summary.cloud_control_run.latency_seconds";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, LATENCY_FIELDS, prefix, details);
  if (!nonNegativeInteger(value.count) || value.count !== eligibleCount) details.push({ field: `${prefix}.count`, issue: "eligible_count_mismatch" });
  for (const field of ["min", "median", "p95_nearest_rank", "max"]) if (!nonNegativeNumber(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_number_required" });
  if ([value.min, value.median, value.p95_nearest_rank, value.max].every(nonNegativeNumber)
    && !(value.min <= value.median && value.median <= value.p95_nearest_rank && value.p95_nearest_rank <= value.max)) {
    details.push({ field: prefix, issue: "latency_order_invalid" });
  }
}

function validateControlPolicy(value, details) {
  const prefix = "public_summary.control_policy";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, CONTROL_FIELDS, prefix, details);
  if (!isHash(value.evidence_hash)) details.push({ field: `${prefix}.evidence_hash`, issue: "sha256_required" });
  validateReasonCodes(value.quality_blockers, `${prefix}.quality_blockers`, details, true);
  if (!["qualified", "blocked", "incomplete"].includes(value.quality_state)) details.push({ field: `${prefix}.quality_state`, issue: "unsupported_state" });
  if (value.quality_state === "qualified" ? value.quality_blockers?.length : !value.quality_blockers?.length) details.push({ field: prefix, issue: "quality_blocker_mismatch" });
  const safe = value.safe_control_assessment;
  if (!isRecord(safe)) {
    details.push({ field: `${prefix}.safe_control_assessment`, issue: "object_required" });
  } else {
    exactFields(safe, SAFE_CONTROL_FIELDS, `${prefix}.safe_control_assessment`, details);
    for (const field of ["eligible_count", "false_positive_count", "maximum_false_positive_count", "minimum_eligible_count"]) {
      if (!nonNegativeInteger(safe[field])) details.push({ field: `${prefix}.safe_control_assessment.${field}`, issue: "non_negative_integer_required" });
    }
    const passed = safe.eligible_count >= safe.minimum_eligible_count
      && safe.false_positive_count <= safe.maximum_false_positive_count;
    if (safe.passed !== passed) details.push({ field: `${prefix}.safe_control_assessment.passed`, issue: "derived_pass_mismatch" });
  }
  if (!isRecord(value.taxonomy_assessments) || !Object.keys(value.taxonomy_assessments).length) {
    details.push({ field: `${prefix}.taxonomy_assessments`, issue: "non_empty_object_required" });
  } else {
    for (const [taxonomy, assessment] of Object.entries(value.taxonomy_assessments)) {
      validateTaxonomyAssessment(taxonomy, assessment, details);
    }
  }
}

function validateTaxonomyAssessment(taxonomy, value, details) {
  const prefix = `public_summary.control_policy.taxonomy_assessments.${taxonomy}`;
  if (!safeIdentifier(taxonomy) || !isRecord(value)) return details.push({ field: prefix, issue: "safe_taxonomy_object_required" });
  exactFields(value, TAXONOMY_FIELDS, prefix, details);
  for (const field of ["detected_count", "eligible_count", "minimum_eligible_count"]) {
    if (!nonNegativeInteger(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
  }
  if (value.detected_count > value.eligible_count) details.push({ field: `${prefix}.detected_count`, issue: "detected_exceeds_eligible" });
  if (!probability(value.minimum_sensitivity) || !probability(value.sensitivity)) details.push({ field: prefix, issue: "probability_required" });
  const expected = value.eligible_count > 0 ? value.detected_count / value.eligible_count : 0;
  if (!closeNumber(value.sensitivity, expected)) details.push({ field: `${prefix}.sensitivity`, issue: "count_ratio_mismatch" });
  const passed = value.eligible_count >= value.minimum_eligible_count && value.sensitivity >= value.minimum_sensitivity;
  if (value.passed !== passed) details.push({ field: `${prefix}.passed`, issue: "derived_pass_mismatch" });
}

function validateLocalRuntime(value, details) {
  const prefix = "public_summary.high_quality_local_candidate";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, LOCAL_FIELDS, prefix, details);
  validateReasonCodes(value.blockers, `${prefix}.blockers`, details, true);
  if (!nonNegativeInteger(value.completed_profile_count)) details.push({ field: `${prefix}.completed_profile_count`, issue: "non_negative_integer_required" });
  if (!safeIdentifier(value.model_id)) details.push({ field: `${prefix}.model_id`, issue: "safe_identifier_required" });
  for (const field of ["model_digest", "probe_evidence_hash", "promotion_evidence_hash"]) if (!isHash(value[field])) details.push({ field: `${prefix}.${field}`, issue: "sha256_required" });
  for (const field of ["qualification_state", "runtime_promotion_state"]) if (!["qualified", "blocked", "incomplete"].includes(value[field])) details.push({ field: `${prefix}.${field}`, issue: "unsupported_state" });
  if (value.runtime_promotion_state === "qualified" ? value.blockers?.length : !value.blockers?.length) details.push({ field: prefix, issue: "runtime_blocker_mismatch" });
}

function validateInterpretation(value, details) {
  const prefix = "public_summary.interpretation";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, INTERPRETATION_FIELDS, prefix, details);
  if (value.promotion_permitted !== false) details.push({ field: `${prefix}.promotion_permitted`, issue: "must_be_false" });
  if (value.provider_failure_or_invalid_output_can_pass !== false) details.push({ field: `${prefix}.provider_failure_or_invalid_output_can_pass`, issue: "must_be_false" });
  if (!safeText(value.reason, 1, 1000)) details.push({ field: `${prefix}.reason`, issue: "safe_text_required" });
}

function validateRepeat(value, details) {
  const prefix = "public_summary.multi_repeat";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, REPEAT_FIELDS, prefix, details);
  if (value.schema_version !== "a2.multimodal_multi_repeat_comparison.v2") details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  if (!isHash(value.evidence_hash)) details.push({ field: `${prefix}.evidence_hash`, issue: "sha256_required" });
  for (const field of ["quality_state", "stability_state"]) if (!["qualified", "blocked", "incomplete"].includes(value[field])) details.push({ field: `${prefix}.${field}`, issue: "unsupported_state" });
  validateReasonCodes(value.quality_blockers, `${prefix}.quality_blockers`, details, true);
  validateReasonCodes(value.stability_blockers, `${prefix}.stability_blockers`, details, true);
  if (value.quality_state === "qualified" ? value.quality_blockers?.length : !value.quality_blockers?.length) details.push({ field: prefix, issue: "quality_blocker_mismatch" });
  if (value.stability_state === "qualified" ? value.stability_blockers?.length : !value.stability_blockers?.length) details.push({ field: prefix, issue: "stability_blocker_mismatch" });
  if (typeof value.all_repeats_fresh !== "boolean" || typeof value.promotion_eligible !== "boolean") details.push({ field: prefix, issue: "boolean_state_required" });
  if (value.promotion_eligible && (value.quality_state !== "qualified" || value.stability_state !== "qualified" || !value.all_repeats_fresh)) details.push({ field: `${prefix}.promotion_eligible`, issue: "promotion_prerequisites_not_met" });
}

function validatePersistence(value, details) {
  const prefix = "public_summary.persistence";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, PERSISTENCE_FIELDS, prefix, details);
  if (!isHash(value.evidence_hash)) details.push({ field: `${prefix}.evidence_hash`, issue: "sha256_required" });
  if (!["qualified", "blocked", "incomplete"].includes(value.real_postgresql_proof_state)) details.push({ field: `${prefix}.real_postgresql_proof_state`, issue: "unsupported_state" });
  if (typeof value.same_round_real_postgresql_verified !== "boolean") details.push({ field: `${prefix}.same_round_real_postgresql_verified`, issue: "boolean_required" });
  if ((value.real_postgresql_proof_state === "qualified") !== value.same_round_real_postgresql_verified) details.push({ field: prefix, issue: "postgresql_proof_state_mismatch" });
}

function validateReview(value, details) {
  const prefix = "public_summary.review_binding";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, REVIEW_FIELDS, prefix, details);
  for (const field of ["collection_hash", "conservation_hash"]) if (!isHash(value[field])) details.push({ field: `${prefix}.${field}`, issue: "sha256_required" });
  if (!["pending", "partially_reviewed", "reviewed"].includes(value.collection_state)) details.push({ field: `${prefix}.collection_state`, issue: "unsupported_state" });
  if (!["verified", "failed"].includes(value.verification_state)) details.push({ field: `${prefix}.verification_state`, issue: "unsupported_state" });
  if (!nonNegativeInteger(value.pending_queue_receipt_count)) details.push({ field: `${prefix}.pending_queue_receipt_count`, issue: "non_negative_integer_required" });
  if (value.collection_state === "pending" && value.pending_queue_receipt_count < 1) details.push({ field: prefix, issue: "pending_review_requires_queue_receipt" });
}

function validateA1Boundary(value, details) {
  const prefix = "a1_peer_boundary";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, A1_BOUNDARY_FIELDS, prefix, details);
  if (!gitAlias(value.source_commit_alias)) details.push({ field: `${prefix}.source_commit_alias`, issue: "git_commit_alias_required" });
  if (!safeIdentifier(value.capability) || !safeIdentifier(value.a3_client_route_status)) details.push({ field: prefix, issue: "safe_identifier_required" });
  for (const field of ["aggregate_readiness_available", "raw_identity_receipt_included", "production_identity_verified"]) if (typeof value[field] !== "boolean") details.push({ field: `${prefix}.${field}`, issue: "boolean_required" });
  if (value.raw_identity_receipt_included !== false) details.push({ field: `${prefix}.raw_identity_receipt_included`, issue: "must_be_false" });
}

function validateCandidate(value, details) {
  const prefix = "shared_candidate_verification";
  if (!isRecord(value)) return details.push({ field: prefix, issue: "object_required" });
  exactFields(value, CANDIDATE_FIELDS, prefix, details);
  if (typeof value.verified !== "boolean") details.push({ field: `${prefix}.verified`, issue: "boolean_required" });
  validateReasonCodes(value.blockers, `${prefix}.blockers`, details, true);
  if (value.verified ? value.blockers?.length : !value.blockers?.length) details.push({ field: prefix, issue: "candidate_blocker_mismatch" });
}

function validateCrossArtifactFacts(value, details) {
  const summary = value.public_summary;
  if (!isRecord(summary)) return;
  const cloud = summary.cloud_control_run;
  const controls = summary.control_policy;
  const local = summary.high_quality_local_candidate;
  if (isRecord(cloud) && isRecord(controls) && isRecord(controls.safe_control_assessment) && isRecord(controls.taxonomy_assessments)) {
    const expected = controls.safe_control_assessment.eligible_count
      + Object.values(controls.taxonomy_assessments).reduce((total, item) => total + (item?.eligible_count || 0), 0);
    if (cloud.eligible_count !== expected) details.push({ field: "public_summary.cloud_control_run.eligible_count", issue: "control_case_conservation_failed" });
  }
  if (isRecord(local) && local.model_id !== summary.high_quality_local_candidate?.model_id) {
    details.push({ field: "public_summary.high_quality_local_candidate.model_id", issue: "local_candidate_binding_failed" });
  }
  if (summary.interpretation?.promotion_permitted === false && summary.multi_repeat?.promotion_eligible === true) {
    details.push({ field: "public_summary.multi_repeat.promotion_eligible", issue: "interpretation_promotion_mismatch" });
  }
}

function requireSafety(value, details) {
  if (value.release_authority !== false) details.push({ field: "release_authority", issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: "public_safe", issue: "must_be_true" });
  if (value.raw_provider_payload_included !== false) details.push({ field: "raw_provider_payload_included", issue: "must_be_false" });
  if (value.raw_identity_receipt_included !== false) details.push({ field: "raw_identity_receipt_included", issue: "must_be_false" });
}

function authorityBoundary() {
  return {
    a1_runtime_identity_authority: "A1",
    a2_evaluation_qualification_authority: "A2",
    a3_product_projection_authority: "A3",
    a1_operational_health_verified: false,
    a2_quality_qualified: false,
    authoritative_human_disposition_recorded: false,
    candidate_binding_verified: false,
    a2_decision_recomputed: false,
    release_authority: false,
    release_decision_changed: false,
    production_ready: false
  };
}

function safetyBoundary() {
  return {
    public_safe: true,
    aggregate_metrics_and_hashes_only: true,
    raw_provider_payload_included: false,
    raw_provider_text_included: false,
    raw_request_id_included: false,
    raw_identity_receipt_included: false,
    endpoint_url_included: false,
    secret_values_included: false
  };
}

function exactFields(value, allowed, prefix, details) {
  if (!isRecord(value)) return;
  const allowedSet = new Set(allowed);
  for (const field of Object.keys(value)) if (!allowedSet.has(field)) details.push({ field: `${prefix}.${field}`, issue: "unexpected_field" });
  for (const field of allowed) if (!(field in value)) details.push({ field: `${prefix}.${field}`, issue: "required" });
}

function validateReasonCodes(value, prefix, details, unique) {
  if (!Array.isArray(value) || value.length > 100) return details.push({ field: prefix, issue: "bounded_array_required" });
  const seen = new Set();
  value.forEach((item, index) => {
    if (!safeIdentifier(item)) details.push({ field: `${prefix}[${index}]`, issue: "reason_code_required" });
    if (unique && seen.has(item)) details.push({ field: `${prefix}[${index}]`, issue: "duplicate" });
    seen.add(item);
  });
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

function safeIdentifier(value) {
  return /^[a-z0-9][a-z0-9_.:-]{0,239}$/.test(String(value || ""));
}

function safeText(value, min, max) {
  const text = String(value || "");
  return text.length >= min && text.length <= max && !SECRET_PATTERNS.some((pattern) => pattern.test(text));
}

function gitAlias(value) {
  return /^[a-f0-9]{7,40}$/.test(String(value || ""));
}

function isHash(value) {
  return /^sha256:[a-f0-9]{64}$/.test(String(value || ""));
}

function validIsoDate(value) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) && value.includes("T");
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function nonNegativeNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function probability(value) {
  return nonNegativeNumber(value) && value <= 1;
}

function closeNumber(value, expected) {
  return typeof value === "number" && Number.isFinite(value) && Math.abs(value - expected) <= 1e-9;
}

function sum(items, field) {
  return items.reduce((total, item) => total + Number(item?.[field] || 0), 0);
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function invalid(details) {
  return { valid: false, details, payload_hash: null };
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortValue(value));
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (isRecord(value)) {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortValue(item)]));
  }
  return value;
}
