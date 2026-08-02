import { createHash } from "node:crypto";

export const A3_MULTIMODAL_REPEAT_STABILITY_INTAKE_SCHEMA_VERSION =
  "a3.a2_multimodal_repeat_stability_intake.v1";
export const A3_MULTIMODAL_REPEAT_STABILITY_SCHEMA_VERSION =
  "a3.multimodal_repeat_stability.v1";
export const A2_MULTIMODAL_MULTI_REPEAT_SCHEMA_VERSION =
  "a2.multimodal_multi_repeat_comparison.v1";
export const A2_MULTIMODAL_REAL_REVIEW_COLLECTION_SCHEMA_VERSION =
  "a2.multimodal_real_review_collection.v1";
export const A2_MULTIMODAL_REVIEW_CONSERVATION_SCHEMA_VERSION =
  "a2.multimodal_review_conservation.v1";

const ENVELOPE_FIELDS = [
  "schema_version",
  "source_commit_alias",
  "comparison",
  "review_collection",
  "review_conservation",
  "shared_candidate_verification",
  "release_authority",
  "public_safe",
  "raw_provider_payload_included",
  "raw_reviewer_identity_included"
];
const COMPARISON_FIELDS = [
  "schema_version",
  "calibration_hashes",
  "repeat_count",
  "binding_fields",
  "mismatched_binding_fields",
  "bootstrap_samples",
  "seed",
  "retained_calibration_states",
  "source_unit_coverage",
  "metrics",
  "taxonomy_sensitivity",
  "all_required_units_complete",
  "blockers",
  "promotion_eligible",
  "provider_is_truth",
  "release_authority",
  "raw_provider_text_included",
  "public_safe"
];
const BINDING_FIELDS = [
  "endpoint_region",
  "manifest_hash",
  "model_id",
  "ordered_case_plan_hash",
  "output_schema_hash",
  "policy_hash",
  "prompt_hash",
  "provider_capability_hash",
  "provider_id"
];
const COVERAGE_FIELDS = [
  "required_unit_count",
  "eligible_unit_counts_by_repeat",
  "missing_unit_counts_by_repeat",
  "complete_across_repeats"
];
const METRIC_FIELDS = [
  "required_unit_count",
  "matched_unit_count",
  "missing_unit_counts_by_repeat",
  "complete_across_repeats",
  "repeat_summaries",
  "paired_max_minus_min_bootstrap_ci_95"
];
const SUMMARY_FIELDS = [
  "eligible_unit_count",
  "success_count",
  "estimate",
  "bootstrap_ci_95"
];
const INTERVAL_FIELDS = ["lower", "upper"];
const REVIEW_COLLECTION_FIELDS = [
  "schema_version",
  "collection_state",
  "receipts",
  "note",
  "release_authority",
  "public_safe"
];
const CONSERVATION_FIELDS = [
  "schema_version",
  "queue_receipt_count",
  "pending_queue_receipt_count",
  "reviewed_queue_receipt_count",
  "latest_receipt_hashes",
  "conservation_holds",
  "verification_state",
  "errors",
  "release_authority",
  "public_safe"
];
const CANDIDATE_FIELDS = ["blockers", "verified"];
const QUALIFICATION_STATES = new Set(["qualified", "blocked", "incomplete", "unavailable"]);
const METRIC_KEYS = [
  ["specificity", "specificity"],
  ["benign_text_false_positive_rate", "benign_text_false_positive_rate"],
  ["cross_modal_conflict", "cross_modal_conflict_sensitivity"],
  ["visual_prompt_injection", "visual_prompt_injection_sensitivity"]
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

export function validateA2MultimodalRepeatStabilityEnvelope(value = {}) {
  const details = [];
  if (!isRecord(value)) return invalid([{ field: "stability_evidence", issue: "object_required" }]);
  exactFields(value, ENVELOPE_FIELDS, "stability_evidence", details);
  if (value.schema_version !== A3_MULTIMODAL_REPEAT_STABILITY_INTAKE_SCHEMA_VERSION) {
    details.push({ field: "schema_version", issue: "unsupported_schema_version" });
  }
  if (!/^[a-f0-9]{7,40}$/.test(String(value.source_commit_alias || ""))) {
    details.push({ field: "source_commit_alias", issue: "git_commit_alias_required" });
  }
  validateComparison(value.comparison, details);
  validateReviewCollection(value.review_collection, details);
  validateReviewConservation(value.review_conservation, details);
  validateSharedCandidate(value.shared_candidate_verification, details);
  requireSafetyBooleans(value, details);
  validateCrossArtifactConservation(value, details);
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "stability_evidence", issue: "sensitive_or_external_material_forbidden" });
  }
  return {
    valid: details.length === 0,
    details,
    payload_hash: `sha256:${sha256(stableJson(value))}`
  };
}

export function buildA3MultimodalRepeatStability(value = {}, options = {}) {
  const validation = validateA2MultimodalRepeatStabilityEnvelope(value);
  const tenantScope = normalizeScope(options.tenantScope || options.tenant_scope || options);
  const base = {
    schema_version: A3_MULTIMODAL_REPEAT_STABILITY_SCHEMA_VERSION,
    source: options.source || "unknown",
    source_commit_alias: value.source_commit_alias || options.sourceCommitAlias || null,
    source_contract: value.comparison?.schema_version || "missing",
    tenant_scope: tenantScope,
    release_authority: false,
    a2_decision_recomputed: false,
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
      recommendation_code: "repair_a2_repeat_stability_contract"
    };
  }

  const comparison = value.comparison;
  const review = value.review_collection;
  const conservation = value.review_conservation;
  const candidate = value.shared_candidate_verification;
  const metrics = metricEntries(comparison);
  const blockedRepeatCount = comparison.retained_calibration_states
    .filter((state) => state === "blocked").length;
  return {
    ...base,
    available: true,
    status: comparison.promotion_eligible === true
      ? "promotion_evidence_non_authoritative"
      : "blocked_stable_repeat",
    capability_state: options.capabilityState || "peer_branch_contract_not_merged",
    integrity: {
      status: "passed",
      finding_count: 0,
      findings: [],
      a3_computed_payload_hash: validation.payload_hash
    },
    summary: {
      repeat_count: comparison.repeat_count,
      retained_blocked_count: blockedRepeatCount,
      retained_qualified_count: comparison.retained_calibration_states
        .filter((state) => state === "qualified").length,
      all_required_units_complete: comparison.all_required_units_complete,
      required_source_unit_count: comparison.source_unit_coverage.required_unit_count,
      bootstrap_samples: comparison.bootstrap_samples,
      blocker_count: comparison.blockers.length,
      promotion_eligible: comparison.promotion_eligible,
      stable_observation: metrics.every((metric) => metric.repeat_estimates.every(
        (estimate) => estimate === metric.repeat_estimates[0]
      )),
      quality_qualified: comparison.retained_calibration_states.every((state) => state === "qualified")
    },
    binding: {
      provider_id: comparison.binding_fields.provider_id,
      model_id: comparison.binding_fields.model_id,
      endpoint_region: comparison.binding_fields.endpoint_region,
      manifest_hash: comparison.binding_fields.manifest_hash,
      policy_hash: comparison.binding_fields.policy_hash,
      prompt_hash: comparison.binding_fields.prompt_hash,
      output_schema_hash: comparison.binding_fields.output_schema_hash,
      provider_capability_hash: comparison.binding_fields.provider_capability_hash,
      ordered_case_plan_hash: comparison.binding_fields.ordered_case_plan_hash,
      mismatched_fields: [...comparison.mismatched_binding_fields],
      provider_identity_verified: false
    },
    source_unit_coverage: {
      required_unit_count: comparison.source_unit_coverage.required_unit_count,
      eligible_unit_counts_by_repeat: [...comparison.source_unit_coverage.eligible_unit_counts_by_repeat],
      missing_unit_counts_by_repeat: [...comparison.source_unit_coverage.missing_unit_counts_by_repeat],
      complete_across_repeats: comparison.source_unit_coverage.complete_across_repeats
    },
    retained_calibration_states: [...comparison.retained_calibration_states],
    calibration_hashes: [...comparison.calibration_hashes],
    metrics,
    blockers: [...comparison.blockers],
    human_review: {
      collection_state: review.collection_state,
      receipt_count: review.receipts.length,
      queue_receipt_count: conservation.queue_receipt_count,
      pending_queue_receipt_count: conservation.pending_queue_receipt_count,
      reviewed_queue_receipt_count: conservation.reviewed_queue_receipt_count,
      conservation_state: conservation.verification_state,
      conservation_holds: conservation.conservation_holds,
      authoritative_human_disposition_recorded: false
    },
    candidate_binding: {
      verified: candidate.verified,
      blockers: [...candidate.blockers]
    },
    authority_boundary: authorityBoundary(),
    safety: safetyBoundary(),
    recommendation_code: "require_qualified_repeats_real_review_and_shared_candidate"
  };
}

function validateComparison(value, details) {
  if (!isRecord(value)) {
    details.push({ field: "comparison", issue: "object_required" });
    return;
  }
  exactFields(value, COMPARISON_FIELDS, "comparison", details);
  if (value.schema_version !== A2_MULTIMODAL_MULTI_REPEAT_SCHEMA_VERSION) {
    details.push({ field: "comparison.schema_version", issue: "unsupported_schema_version" });
  }
  const repeatCount = value.repeat_count;
  if (!Number.isInteger(repeatCount) || repeatCount < 3 || repeatCount > 100) {
    details.push({ field: "comparison.repeat_count", issue: "integer_3_to_100_required" });
  }
  validateHashArray(value.calibration_hashes, repeatCount, "comparison.calibration_hashes", details);
  validateBinding(value.binding_fields, details);
  validateReasonCodeArray(value.mismatched_binding_fields, "comparison.mismatched_binding_fields", details, true);
  for (const field of value.mismatched_binding_fields || []) {
    if (!BINDING_FIELDS.includes(field)) {
      details.push({ field: "comparison.mismatched_binding_fields", issue: "unknown_binding_field" });
    }
  }
  if (!Number.isInteger(value.bootstrap_samples) || value.bootstrap_samples < 100 || value.bootstrap_samples > 10_000_000) {
    details.push({ field: "comparison.bootstrap_samples", issue: "integer_100_to_10000000_required" });
  }
  if (!Number.isInteger(value.seed)) details.push({ field: "comparison.seed", issue: "integer_required" });
  if (!Array.isArray(value.retained_calibration_states) || value.retained_calibration_states.length !== repeatCount) {
    details.push({ field: "comparison.retained_calibration_states", issue: "repeat_count_length_required" });
  } else {
    value.retained_calibration_states.forEach((state, index) => {
      if (!QUALIFICATION_STATES.has(state)) {
        details.push({ field: `comparison.retained_calibration_states[${index}]`, issue: "unsupported_state" });
      }
    });
  }
  validateCoverage(value.source_unit_coverage, repeatCount, details);
  if (!isRecord(value.metrics)) {
    details.push({ field: "comparison.metrics", issue: "object_required" });
  } else {
    exactFields(value.metrics, ["specificity", "benign_text_false_positive_rate"], "comparison.metrics", details);
    validateMetric(value.metrics.specificity, repeatCount, "comparison.metrics.specificity", details);
    validateMetric(value.metrics.benign_text_false_positive_rate, repeatCount, "comparison.metrics.benign_text_false_positive_rate", details);
  }
  if (!isRecord(value.taxonomy_sensitivity)) {
    details.push({ field: "comparison.taxonomy_sensitivity", issue: "object_required" });
  } else {
    exactFields(value.taxonomy_sensitivity, ["cross_modal_conflict", "visual_prompt_injection"], "comparison.taxonomy_sensitivity", details);
    validateMetric(value.taxonomy_sensitivity.cross_modal_conflict, repeatCount, "comparison.taxonomy_sensitivity.cross_modal_conflict", details);
    validateMetric(value.taxonomy_sensitivity.visual_prompt_injection, repeatCount, "comparison.taxonomy_sensitivity.visual_prompt_injection", details);
  }
  const complete = derivedAllUnitsComplete(value);
  if (typeof value.all_required_units_complete !== "boolean" || value.all_required_units_complete !== complete) {
    details.push({ field: "comparison.all_required_units_complete", issue: "derived_completeness_mismatch" });
  }
  validateReasonCodeArray(value.blockers, "comparison.blockers", details, true);
  if (typeof value.promotion_eligible !== "boolean") {
    details.push({ field: "comparison.promotion_eligible", issue: "boolean_required" });
  }
  if (value.promotion_eligible === true && (
    value.all_required_units_complete !== true
    || value.blockers?.length
    || value.mismatched_binding_fields?.length
    || !value.retained_calibration_states?.every((state) => state === "qualified")
  )) {
    details.push({ field: "comparison.promotion_eligible", issue: "promotion_prerequisites_not_met" });
  }
  if (value.provider_is_truth !== false) details.push({ field: "comparison.provider_is_truth", issue: "must_be_false" });
  if (value.release_authority !== false) details.push({ field: "comparison.release_authority", issue: "must_be_false" });
  if (value.raw_provider_text_included !== false) details.push({ field: "comparison.raw_provider_text_included", issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: "comparison.public_safe", issue: "must_be_true" });
}

function validateBinding(value, details) {
  if (!isRecord(value)) {
    details.push({ field: "comparison.binding_fields", issue: "object_required" });
    return;
  }
  exactFields(value, BINDING_FIELDS, "comparison.binding_fields", details);
  for (const [field, item] of Object.entries(value)) {
    if (field.endsWith("_hash")) {
      if (!isHash(item)) details.push({ field: `comparison.binding_fields.${field}`, issue: "sha256_required" });
    } else if (!safeText(item, 1, 160)) {
      details.push({ field: `comparison.binding_fields.${field}`, issue: "safe_text_required" });
    }
  }
}

function validateCoverage(value, repeatCount, details) {
  const prefix = "comparison.source_unit_coverage";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, COVERAGE_FIELDS, prefix, details);
  if (!nonNegativeInteger(value.required_unit_count)) details.push({ field: `${prefix}.required_unit_count`, issue: "non_negative_integer_required" });
  validateCountArray(value.eligible_unit_counts_by_repeat, repeatCount, `${prefix}.eligible_unit_counts_by_repeat`, details);
  validateCountArray(value.missing_unit_counts_by_repeat, repeatCount, `${prefix}.missing_unit_counts_by_repeat`, details);
  const complete = Array.isArray(value.eligible_unit_counts_by_repeat)
    && Array.isArray(value.missing_unit_counts_by_repeat)
    && value.eligible_unit_counts_by_repeat.length === repeatCount
    && value.missing_unit_counts_by_repeat.length === repeatCount
    && value.eligible_unit_counts_by_repeat.every((count, index) => (
      count + value.missing_unit_counts_by_repeat[index] === value.required_unit_count
    ))
    && value.missing_unit_counts_by_repeat.every((count) => count === 0);
  if (value.complete_across_repeats !== complete) {
    details.push({ field: `${prefix}.complete_across_repeats`, issue: "derived_completeness_mismatch" });
  }
}

function validateMetric(value, repeatCount, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, METRIC_FIELDS, prefix, details);
  if (!nonNegativeInteger(value.required_unit_count)) details.push({ field: `${prefix}.required_unit_count`, issue: "non_negative_integer_required" });
  if (!nonNegativeInteger(value.matched_unit_count) || value.matched_unit_count > value.required_unit_count) {
    details.push({ field: `${prefix}.matched_unit_count`, issue: "bounded_non_negative_integer_required" });
  }
  validateCountArray(value.missing_unit_counts_by_repeat, repeatCount, `${prefix}.missing_unit_counts_by_repeat`, details);
  if (!Array.isArray(value.repeat_summaries) || value.repeat_summaries.length !== repeatCount) {
    details.push({ field: `${prefix}.repeat_summaries`, issue: "repeat_count_length_required" });
  } else {
    value.repeat_summaries.forEach((summary, index) => validateMetricSummary(summary, value.required_unit_count, `${prefix}.repeat_summaries[${index}]`, details));
  }
  validateInterval(value.paired_max_minus_min_bootstrap_ci_95, `${prefix}.paired_max_minus_min_bootstrap_ci_95`, details);
  const complete = value.matched_unit_count === value.required_unit_count
    && Array.isArray(value.missing_unit_counts_by_repeat)
    && value.missing_unit_counts_by_repeat.length === repeatCount
    && value.missing_unit_counts_by_repeat.every((count) => count === 0)
    && Array.isArray(value.repeat_summaries)
    && value.repeat_summaries.length === repeatCount
    && value.repeat_summaries.every((summary) => summary?.eligible_unit_count === value.required_unit_count);
  if (value.complete_across_repeats !== complete) {
    details.push({ field: `${prefix}.complete_across_repeats`, issue: "derived_completeness_mismatch" });
  }
}

function validateMetricSummary(value, requiredCount, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, SUMMARY_FIELDS, prefix, details);
  if (!nonNegativeInteger(value.eligible_unit_count) || value.eligible_unit_count > requiredCount) {
    details.push({ field: `${prefix}.eligible_unit_count`, issue: "bounded_non_negative_integer_required" });
  }
  if (!nonNegativeInteger(value.success_count) || value.success_count > value.eligible_unit_count) {
    details.push({ field: `${prefix}.success_count`, issue: "bounded_non_negative_integer_required" });
  }
  const expectedEstimate = value.eligible_unit_count > 0 ? value.success_count / value.eligible_unit_count : null;
  if (expectedEstimate === null ? value.estimate !== null : !closeNumber(value.estimate, expectedEstimate)) {
    details.push({ field: `${prefix}.estimate`, issue: "count_ratio_mismatch" });
  }
  validateInterval(value.bootstrap_ci_95, `${prefix}.bootstrap_ci_95`, details);
  if (typeof value.estimate === "number" && isRecord(value.bootstrap_ci_95)
    && (value.estimate < value.bootstrap_ci_95.lower || value.estimate > value.bootstrap_ci_95.upper)) {
    details.push({ field: `${prefix}.bootstrap_ci_95`, issue: "estimate_outside_interval" });
  }
}

function validateInterval(value, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, INTERVAL_FIELDS, prefix, details);
  for (const field of INTERVAL_FIELDS) {
    if (value[field] !== null && !probability(value[field])) {
      details.push({ field: `${prefix}.${field}`, issue: "probability_or_null_required" });
    }
  }
  if (typeof value.lower === "number" && typeof value.upper === "number" && value.lower > value.upper) {
    details.push({ field: prefix, issue: "ordered_interval_required" });
  }
}

function validateReviewCollection(value, details) {
  const prefix = "review_collection";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, REVIEW_COLLECTION_FIELDS, prefix, details);
  if (value.schema_version !== A2_MULTIMODAL_REAL_REVIEW_COLLECTION_SCHEMA_VERSION) {
    details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  }
  if (!new Set(["pending", "partially_reviewed", "reviewed"]).has(value.collection_state)) {
    details.push({ field: `${prefix}.collection_state`, issue: "unsupported_state" });
  }
  if (!Array.isArray(value.receipts) || value.receipts.length > 100) {
    details.push({ field: `${prefix}.receipts`, issue: "bounded_array_required" });
  } else if (value.receipts.length > 0) {
    details.push({ field: `${prefix}.receipts`, issue: "authoritative_receipt_schema_not_supported" });
  }
  if (value.collection_state === "pending" && value.receipts?.length !== 0) {
    details.push({ field: `${prefix}.receipts`, issue: "pending_requires_empty_receipts" });
  }
  if (value.collection_state === "reviewed" && !value.receipts?.length) {
    details.push({ field: `${prefix}.receipts`, issue: "reviewed_requires_receipt" });
  }
  if (!safeText(value.note, 1, 500)) details.push({ field: `${prefix}.note`, issue: "safe_note_required" });
  if (value.release_authority !== false) details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
}

function validateReviewConservation(value, details) {
  const prefix = "review_conservation";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, CONSERVATION_FIELDS, prefix, details);
  if (value.schema_version !== A2_MULTIMODAL_REVIEW_CONSERVATION_SCHEMA_VERSION) {
    details.push({ field: `${prefix}.schema_version`, issue: "unsupported_schema_version" });
  }
  for (const field of ["queue_receipt_count", "pending_queue_receipt_count", "reviewed_queue_receipt_count"]) {
    if (!nonNegativeInteger(value[field])) details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
  }
  if (value.pending_queue_receipt_count + value.reviewed_queue_receipt_count !== value.queue_receipt_count) {
    details.push({ field: prefix, issue: "queue_receipt_conservation_failed" });
  }
  if (!isRecord(value.latest_receipt_hashes)) {
    details.push({ field: `${prefix}.latest_receipt_hashes`, issue: "object_required" });
  } else {
    for (const [key, hash] of Object.entries(value.latest_receipt_hashes)) {
      if (!safeIdentifier(key) || !isHash(hash)) details.push({ field: `${prefix}.latest_receipt_hashes`, issue: "safe_hash_map_required" });
    }
    if (Object.keys(value.latest_receipt_hashes).length !== value.reviewed_queue_receipt_count) {
      details.push({ field: `${prefix}.latest_receipt_hashes`, issue: "reviewed_receipt_count_mismatch" });
    }
  }
  if (typeof value.conservation_holds !== "boolean") details.push({ field: `${prefix}.conservation_holds`, issue: "boolean_required" });
  if (!["verified", "failed"].includes(value.verification_state)) details.push({ field: `${prefix}.verification_state`, issue: "unsupported_state" });
  validateReasonCodeArray(value.errors, `${prefix}.errors`, details, true);
  if (value.verification_state === "verified" && (value.conservation_holds !== true || value.errors?.length)) {
    details.push({ field: prefix, issue: "verified_state_inconsistent" });
  }
  if (value.release_authority !== false) details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: `${prefix}.public_safe`, issue: "must_be_true" });
}

function validateSharedCandidate(value, details) {
  const prefix = "shared_candidate_verification";
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, CANDIDATE_FIELDS, prefix, details);
  if (typeof value.verified !== "boolean") details.push({ field: `${prefix}.verified`, issue: "boolean_required" });
  validateReasonCodeArray(value.blockers, `${prefix}.blockers`, details, true);
  if (value.verified === true && value.blockers?.length) details.push({ field: prefix, issue: "verified_candidate_has_blockers" });
  if (value.verified === false && !value.blockers?.length) details.push({ field: prefix, issue: "blocked_candidate_requires_reason" });
}

function validateCrossArtifactConservation(value, details) {
  const review = value.review_collection;
  const conservation = value.review_conservation;
  if (!isRecord(review) || !isRecord(conservation)) return;
  const receiptCount = Array.isArray(review.receipts) ? review.receipts.length : -1;
  if (receiptCount >= 0 && receiptCount !== conservation.reviewed_queue_receipt_count) {
    details.push({ field: "review_collection.receipts", issue: "review_conservation_count_mismatch" });
  }
  if (review.collection_state === "pending" && conservation.pending_queue_receipt_count < 1) {
    details.push({ field: "review_conservation.pending_queue_receipt_count", issue: "pending_collection_requires_pending_queue" });
  }
}

function requireSafetyBooleans(value, details) {
  if (value.release_authority !== false) details.push({ field: "release_authority", issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: "public_safe", issue: "must_be_true" });
  if (value.raw_provider_payload_included !== false) details.push({ field: "raw_provider_payload_included", issue: "must_be_false" });
  if (value.raw_reviewer_identity_included !== false) details.push({ field: "raw_reviewer_identity_included", issue: "must_be_false" });
}

function metricEntries(comparison) {
  return METRIC_KEYS.map(([sourceKey, metricId]) => {
    const source = ["specificity", "benign_text_false_positive_rate"].includes(sourceKey)
      ? comparison.metrics[sourceKey]
      : comparison.taxonomy_sensitivity[sourceKey];
    return {
      metric_id: metricId,
      required_unit_count: source.required_unit_count,
      matched_unit_count: source.matched_unit_count,
      complete_across_repeats: source.complete_across_repeats,
      repeat_estimates: source.repeat_summaries.map((summary) => summary.estimate),
      repeat_eligible_counts: source.repeat_summaries.map((summary) => summary.eligible_unit_count),
      repeat_success_counts: source.repeat_summaries.map((summary) => summary.success_count),
      repeat_bootstrap_ci_95: source.repeat_summaries.map((summary) => ({ ...summary.bootstrap_ci_95 })),
      paired_max_minus_min_bootstrap_ci_95: { ...source.paired_max_minus_min_bootstrap_ci_95 }
    };
  });
}

function derivedAllUnitsComplete(value) {
  if (!isRecord(value.source_unit_coverage) || !isRecord(value.metrics) || !isRecord(value.taxonomy_sensitivity)) return false;
  return value.source_unit_coverage.complete_across_repeats === true
    && value.metrics.specificity?.complete_across_repeats === true
    && value.metrics.benign_text_false_positive_rate?.complete_across_repeats === true
    && value.taxonomy_sensitivity.cross_modal_conflict?.complete_across_repeats === true
    && value.taxonomy_sensitivity.visual_prompt_injection?.complete_across_repeats === true;
}

function authorityBoundary() {
  return {
    provider_is_truth: false,
    provider_identity_verified: false,
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
    hashes_and_aggregate_metrics_only: true,
    raw_provider_payload_included: false,
    raw_provider_text_included: false,
    raw_reviewer_identity_included: false,
    signed_url_included: false,
    secret_values_included: false
  };
}

function exactFields(value, allowed, prefix, details) {
  if (!isRecord(value)) return;
  const allowedSet = new Set(allowed);
  for (const field of Object.keys(value)) {
    if (!allowedSet.has(field)) details.push({ field: `${prefix}.${field}`, issue: "unexpected_field" });
  }
  for (const field of allowed) {
    if (!(field in value)) details.push({ field: `${prefix}.${field}`, issue: "required" });
  }
}

function validateHashArray(value, expectedLength, prefix, details) {
  if (!Array.isArray(value) || value.length !== expectedLength) {
    details.push({ field: prefix, issue: "repeat_count_length_required" });
    return;
  }
  const unique = new Set();
  value.forEach((item, index) => {
    if (!isHash(item)) details.push({ field: `${prefix}[${index}]`, issue: "sha256_required" });
    if (unique.has(item)) details.push({ field: `${prefix}[${index}]`, issue: "duplicate" });
    unique.add(item);
  });
}

function validateCountArray(value, expectedLength, prefix, details) {
  if (!Array.isArray(value) || value.length !== expectedLength) {
    details.push({ field: prefix, issue: "repeat_count_length_required" });
    return;
  }
  value.forEach((item, index) => {
    if (!nonNegativeInteger(item)) details.push({ field: `${prefix}[${index}]`, issue: "non_negative_integer_required" });
  });
}

function validateReasonCodeArray(value, prefix, details, unique) {
  if (!Array.isArray(value) || value.length > 100) {
    details.push({ field: prefix, issue: "bounded_array_required" });
    return;
  }
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

function safeText(value, min, max) {
  const text = String(value || "");
  return text.length >= min
    && text.length <= max
    && !SECRET_PATTERNS.some((pattern) => pattern.test(text));
}

function safeIdentifier(value) {
  return /^[a-z0-9][a-z0-9_.:-]{0,159}$/.test(String(value || ""));
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

function probability(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function closeNumber(value, expected) {
  return typeof value === "number" && Number.isFinite(value) && Math.abs(value - expected) <= 1e-9;
}

function isHash(value) {
  return /^sha256:[a-f0-9]{64}$/.test(String(value || ""));
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
