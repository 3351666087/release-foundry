export const A3_MULTIMODAL_REVIEW_QUEUE_SCHEMA_VERSION = "a3.multimodal_review_queue.v1";
export const A2_MULTIMODAL_COMPARISON_SCHEMA_VERSION = "a2.multimodal_cross_provider_comparison.v1";
export const A2_MULTIMODAL_COMPARISON_V3_SCHEMA_VERSION = "a2.multimodal_cross_provider_comparison.v3";

const SUPPORTED_SOURCE_CONTRACTS = new Set([
  A2_MULTIMODAL_COMPARISON_SCHEMA_VERSION,
  A2_MULTIMODAL_COMPARISON_V3_SCHEMA_VERSION
]);

const HASH_PATTERN = /^sha256:[a-f0-9]{64}$/;
const SCOPE_FIELDS = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];
const TOP_LEVEL_FIELDS = [
  "schema_version",
  "left_evidence_hash",
  "right_evidence_hash",
  "left_binding",
  "right_binding",
  "comparisons",
  "summary",
  "human_review_queue_receipts",
  "release_authority",
  "raw_payload_included",
  "public_safe"
];
const V3_TOP_LEVEL_FIELDS = [
  "schema_version",
  "comparison_artifact_hash",
  "left_evidence_hash",
  "right_evidence_hash",
  "left_binding",
  "right_binding",
  "comparisons",
  "summary",
  "aggregate_comparisons",
  "aggregate_summary",
  "human_review_queue_receipts",
  "release_authority",
  "raw_payload_included",
  "public_safe"
];
const V3_OPTIONAL_TOP_LEVEL_FIELDS = ["lineage"];
const BINDING_FIELDS = ["provider_id", "model_id", "model_version", "prompt_hash"];
const LINEAGE_FIELDS = [
  "left_final_matrix_hash",
  "right_final_matrix_hash",
  "left_partial_journal_hash",
  "right_partial_journal_hash"
];
const COMPARISON_FIELDS = [
  "case_id",
  "artifact_hash",
  "left_state",
  "right_state",
  "left_observed_risk",
  "right_observed_risk",
  "comparison_state",
  "human_review_required"
];
const SUMMARY_FIELDS = ["agreement", "semantic_disagreement", "unavailable"];
const V3_COMPARISON_FIELDS = [...COMPARISON_FIELDS.slice(0, 2), "repeat", ...COMPARISON_FIELDS.slice(2)];
const V3_AGGREGATE_COMPARISON_FIELDS = [
  "case_id",
  "artifact_hash",
  "left_repeat_count",
  "right_repeat_count",
  "left_valid_risks",
  "right_valid_risks",
  "comparison_state",
  "human_review_required"
];
const V3_AGGREGATE_SUMMARY_FIELDS = ["agreement", "semantic_disagreement", "unavailable", "internally_unstable"];
const RECEIPT_FIELDS = [
  "receipt_id",
  "comparison_hash",
  "artifact_hash",
  "queue_state",
  "reviewer_role",
  "release_authority"
];
const V3_RECEIPT_FIELDS = [
  "receipt_id",
  "comparison_artifact_hash",
  "comparison_hash",
  "artifact_hash",
  "case_id",
  "review_scope",
  "queue_state",
  "reviewer_role",
  "release_authority"
];
const COMPARISON_STATES = new Set(["agreement", "semantic_disagreement", "unavailable"]);
const V3_AGGREGATE_STATES = new Set([...COMPARISON_STATES, "internally_unstable"]);
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

export function validateA2MultimodalComparison(value = {}, options = {}) {
  if (!isRecord(value)) {
    return invalid([{ field: "comparison", issue: "object_required" }]);
  }
  if (value.schema_version === A2_MULTIMODAL_COMPARISON_SCHEMA_VERSION) {
    return validateV1Comparison(value, options);
  }
  if (value.schema_version === A2_MULTIMODAL_COMPARISON_V3_SCHEMA_VERSION) {
    return validateV3Comparison(value, options);
  }
  return invalid([{ field: "schema_version", issue: "unsupported_schema_version" }]);
}

function validateV1Comparison(value = {}, options = {}) {
  const details = [];
  exactFields(value, TOP_LEVEL_FIELDS, "comparison", details);
  if (value.schema_version !== A2_MULTIMODAL_COMPARISON_SCHEMA_VERSION) {
    details.push({ field: "schema_version", issue: "unsupported_schema_version" });
  }
  for (const field of ["left_evidence_hash", "right_evidence_hash"]) {
    if (!isHash(value[field])) details.push({ field, issue: "sha256_required" });
  }
  validateBinding(value.left_binding, "left_binding", details);
  validateBinding(value.right_binding, "right_binding", details);

  if (!Array.isArray(value.comparisons) || value.comparisons.length > 5000) {
    details.push({ field: "comparisons", issue: "bounded_array_required" });
  }
  if (!Array.isArray(value.human_review_queue_receipts) || value.human_review_queue_receipts.length > 5000) {
    details.push({ field: "human_review_queue_receipts", issue: "bounded_array_required" });
  }
  validateSummary(value.summary, details);
  if (value.release_authority !== false) {
    details.push({ field: "release_authority", issue: "must_be_false" });
  }
  if (value.raw_payload_included !== false) {
    details.push({ field: "raw_payload_included", issue: "must_be_false" });
  }
  if (value.public_safe !== true) {
    details.push({ field: "public_safe", issue: "must_be_true" });
  }

  const scope = normalizeScope(options.tenantScope || options.tenant_scope || options);
  for (const field of SCOPE_FIELDS) {
    if (!scope[field]) details.push({ field: `tenant_scope.${field}`, issue: "required" });
  }

  const comparisons = Array.isArray(value.comparisons) ? value.comparisons : [];
  const receipts = Array.isArray(value.human_review_queue_receipts)
    ? value.human_review_queue_receipts
    : [];
  const caseIds = new Set();
  const artifactHashes = new Set();
  const requiredArtifacts = new Set();

  comparisons.forEach((item, index) => {
    const prefix = `comparisons[${index}]`;
    if (!isRecord(item)) {
      details.push({ field: prefix, issue: "object_required" });
      return;
    }
    exactFields(item, COMPARISON_FIELDS, prefix, details);
    validateText(item.case_id, `${prefix}.case_id`, details);
    validateText(item.left_state, `${prefix}.left_state`, details);
    validateText(item.right_state, `${prefix}.right_state`, details);
    if (!isHash(item.artifact_hash)) details.push({ field: `${prefix}.artifact_hash`, issue: "sha256_required" });
    if (![true, false, null].includes(item.left_observed_risk)) {
      details.push({ field: `${prefix}.left_observed_risk`, issue: "boolean_or_null_required" });
    }
    if (![true, false, null].includes(item.right_observed_risk)) {
      details.push({ field: `${prefix}.right_observed_risk`, issue: "boolean_or_null_required" });
    }
    if (!COMPARISON_STATES.has(item.comparison_state)) {
      details.push({ field: `${prefix}.comparison_state`, issue: "unsupported_state" });
    }
    if (typeof item.human_review_required !== "boolean") {
      details.push({ field: `${prefix}.human_review_required`, issue: "boolean_required" });
    }
    if (item.comparison_state === "agreement" && item.human_review_required !== false) {
      details.push({ field: `${prefix}.human_review_required`, issue: "agreement_cannot_require_review" });
    }
    if (["semantic_disagreement", "unavailable"].includes(item.comparison_state) && item.human_review_required !== true) {
      details.push({ field: `${prefix}.human_review_required`, issue: "non_agreement_requires_review" });
    }
    if (caseIds.has(item.case_id)) details.push({ field: `${prefix}.case_id`, issue: "duplicate" });
    if (artifactHashes.has(item.artifact_hash)) details.push({ field: `${prefix}.artifact_hash`, issue: "duplicate" });
    caseIds.add(item.case_id);
    artifactHashes.add(item.artifact_hash);
    if (item.human_review_required === true && isHash(item.artifact_hash)) requiredArtifacts.add(item.artifact_hash);
  });

  const receiptArtifacts = new Set();
  const receiptIds = new Set();
  receipts.forEach((item, index) => {
    const prefix = `human_review_queue_receipts[${index}]`;
    if (!isRecord(item)) {
      details.push({ field: prefix, issue: "object_required" });
      return;
    }
    exactFields(item, RECEIPT_FIELDS, prefix, details);
    for (const field of ["receipt_id", "comparison_hash", "artifact_hash"]) {
      if (!isHash(item[field])) details.push({ field: `${prefix}.${field}`, issue: "sha256_required" });
    }
    if (item.queue_state !== "awaiting_human_review") {
      details.push({ field: `${prefix}.queue_state`, issue: "unsupported_queue_state" });
    }
    if (item.reviewer_role !== "multimodal_safety_reviewer") {
      details.push({ field: `${prefix}.reviewer_role`, issue: "unsupported_reviewer_role" });
    }
    if (item.release_authority !== false) {
      details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
    }
    if (!requiredArtifacts.has(item.artifact_hash)) {
      details.push({ field: `${prefix}.artifact_hash`, issue: "orphan_queue_receipt" });
    }
    if (receiptArtifacts.has(item.artifact_hash)) {
      details.push({ field: `${prefix}.artifact_hash`, issue: "duplicate_queue_receipt" });
    }
    if (receiptIds.has(item.receipt_id)) details.push({ field: `${prefix}.receipt_id`, issue: "duplicate" });
    receiptArtifacts.add(item.artifact_hash);
    receiptIds.add(item.receipt_id);
  });
  for (const artifactHash of requiredArtifacts) {
    if (!receiptArtifacts.has(artifactHash)) {
      details.push({ field: "human_review_queue_receipts", issue: "missing_required_queue_receipt" });
    }
  }

  if (isRecord(value.summary)) {
    const counted = countStates(comparisons);
    for (const field of SUMMARY_FIELDS) {
      if (value.summary[field] !== counted[field]) {
        details.push({ field: `summary.${field}`, issue: "count_mismatch" });
      }
    }
  }
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "comparison", issue: "sensitive_or_external_material_forbidden" });
  }

  return {
    valid: details.length === 0,
    details,
    tenant_scope: scope,
    counted_summary: countStates(comparisons),
    review_required_count: requiredArtifacts.size
  };
}

function validateV3Comparison(value = {}, options = {}) {
  const details = [];
  exactFields(
    value,
    V3_TOP_LEVEL_FIELDS,
    "comparison",
    details,
    V3_OPTIONAL_TOP_LEVEL_FIELDS
  );
  for (const field of ["comparison_artifact_hash", "left_evidence_hash", "right_evidence_hash"]) {
    if (!isHash(value[field])) details.push({ field, issue: "sha256_required" });
  }
  validateBinding(value.left_binding, "left_binding", details);
  validateBinding(value.right_binding, "right_binding", details);
  validateV3Lineage(value.lineage, details);

  if (!Array.isArray(value.comparisons) || value.comparisons.length > 5000) {
    details.push({ field: "comparisons", issue: "bounded_array_required" });
  }
  if (!Array.isArray(value.aggregate_comparisons) || value.aggregate_comparisons.length > 5000) {
    details.push({ field: "aggregate_comparisons", issue: "bounded_array_required" });
  }
  if (!Array.isArray(value.human_review_queue_receipts) || value.human_review_queue_receipts.length > 10000) {
    details.push({ field: "human_review_queue_receipts", issue: "bounded_array_required" });
  }
  validateSummary(value.summary, details);
  validateCountSummary(value.aggregate_summary, V3_AGGREGATE_SUMMARY_FIELDS, "aggregate_summary", details);
  if (value.release_authority !== false) details.push({ field: "release_authority", issue: "must_be_false" });
  if (value.raw_payload_included !== false) details.push({ field: "raw_payload_included", issue: "must_be_false" });
  if (value.public_safe !== true) details.push({ field: "public_safe", issue: "must_be_true" });

  const scope = normalizeScope(options.tenantScope || options.tenant_scope || options);
  for (const field of SCOPE_FIELDS) {
    if (!scope[field]) details.push({ field: `tenant_scope.${field}`, issue: "required" });
  }

  const comparisons = Array.isArray(value.comparisons) ? value.comparisons : [];
  const aggregates = Array.isArray(value.aggregate_comparisons) ? value.aggregate_comparisons : [];
  const receipts = Array.isArray(value.human_review_queue_receipts)
    ? value.human_review_queue_receipts
    : [];
  const comparisonKeys = new Set();
  const aggregateKeys = new Set();
  const requiredCounts = new Map();

  comparisons.forEach((item, index) => {
    const prefix = `comparisons[${index}]`;
    if (!isRecord(item)) {
      details.push({ field: prefix, issue: "object_required" });
      return;
    }
    exactFields(item, V3_COMPARISON_FIELDS, prefix, details);
    validateText(item.case_id, `${prefix}.case_id`, details);
    validateText(item.left_state, `${prefix}.left_state`, details);
    validateText(item.right_state, `${prefix}.right_state`, details);
    if (!isHash(item.artifact_hash)) details.push({ field: `${prefix}.artifact_hash`, issue: "sha256_required" });
    if (!Number.isInteger(item.repeat) || item.repeat < 1) {
      details.push({ field: `${prefix}.repeat`, issue: "positive_integer_required" });
    }
    validateObservedRisk(item.left_observed_risk, `${prefix}.left_observed_risk`, details);
    validateObservedRisk(item.right_observed_risk, `${prefix}.right_observed_risk`, details);
    validateReviewState(item, prefix, COMPARISON_STATES, details, ["semantic_disagreement"]);
    const key = comparisonIdentity(item);
    if (comparisonKeys.has(key)) details.push({ field: prefix, issue: "duplicate_repeat_comparison" });
    comparisonKeys.add(key);
    if (item.human_review_required === true) {
      incrementCount(requiredCounts, receiptIdentity("repeat", item.case_id, item.artifact_hash));
    }
  });

  aggregates.forEach((item, index) => {
    const prefix = `aggregate_comparisons[${index}]`;
    if (!isRecord(item)) {
      details.push({ field: prefix, issue: "object_required" });
      return;
    }
    exactFields(item, V3_AGGREGATE_COMPARISON_FIELDS, prefix, details);
    validateText(item.case_id, `${prefix}.case_id`, details);
    if (!isHash(item.artifact_hash)) details.push({ field: `${prefix}.artifact_hash`, issue: "sha256_required" });
    for (const field of ["left_repeat_count", "right_repeat_count"]) {
      if (!Number.isInteger(item[field]) || item[field] < 0) {
        details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
      }
    }
    validateRiskSet(item.left_valid_risks, `${prefix}.left_valid_risks`, details);
    validateRiskSet(item.right_valid_risks, `${prefix}.right_valid_risks`, details);
    validateReviewState(
      item,
      prefix,
      V3_AGGREGATE_STATES,
      details,
      ["semantic_disagreement", "internally_unstable"]
    );
    if (
      item.comparison_state === "internally_unstable"
      && uniqueBooleanCount(item.left_valid_risks) < 2
      && uniqueBooleanCount(item.right_valid_risks) < 2
    ) {
      details.push({ field: `${prefix}.comparison_state`, issue: "instability_evidence_required" });
    }
    const key = aggregateIdentity(item);
    if (aggregateKeys.has(key)) details.push({ field: prefix, issue: "duplicate_aggregate_comparison" });
    aggregateKeys.add(key);
    if (item.human_review_required === true) {
      incrementCount(requiredCounts, receiptIdentity("aggregate", item.case_id, item.artifact_hash));
    }
  });

  const receiptCounts = new Map();
  const receiptIds = new Set();
  const comparisonHashes = new Set();
  receipts.forEach((item, index) => {
    const prefix = `human_review_queue_receipts[${index}]`;
    if (!isRecord(item)) {
      details.push({ field: prefix, issue: "object_required" });
      return;
    }
    exactFields(item, V3_RECEIPT_FIELDS, prefix, details);
    for (const field of ["receipt_id", "comparison_artifact_hash", "comparison_hash", "artifact_hash"]) {
      if (!isHash(item[field])) details.push({ field: `${prefix}.${field}`, issue: "sha256_required" });
    }
    validateText(item.case_id, `${prefix}.case_id`, details);
    if (item.comparison_artifact_hash !== value.comparison_artifact_hash) {
      details.push({ field: `${prefix}.comparison_artifact_hash`, issue: "artifact_binding_mismatch" });
    }
    if (!["repeat", "aggregate"].includes(item.review_scope)) {
      details.push({ field: `${prefix}.review_scope`, issue: "unsupported_review_scope" });
    }
    if (item.queue_state !== "awaiting_human_review") {
      details.push({ field: `${prefix}.queue_state`, issue: "unsupported_queue_state" });
    }
    if (item.reviewer_role !== "multimodal_safety_reviewer") {
      details.push({ field: `${prefix}.reviewer_role`, issue: "unsupported_reviewer_role" });
    }
    if (item.release_authority !== false) {
      details.push({ field: `${prefix}.release_authority`, issue: "must_be_false" });
    }
    const key = receiptIdentity(item.review_scope, item.case_id, item.artifact_hash);
    if (!requiredCounts.has(key)) {
      details.push({ field: prefix, issue: "orphan_queue_receipt" });
    }
    incrementCount(receiptCounts, key);
    if (receiptIds.has(item.receipt_id)) details.push({ field: `${prefix}.receipt_id`, issue: "duplicate" });
    if (comparisonHashes.has(item.comparison_hash)) details.push({ field: `${prefix}.comparison_hash`, issue: "duplicate" });
    receiptIds.add(item.receipt_id);
    comparisonHashes.add(item.comparison_hash);
  });

  for (const [key, count] of requiredCounts) {
    if ((receiptCounts.get(key) || 0) !== count) {
      details.push({ field: "human_review_queue_receipts", issue: "review_receipt_conservation_failed" });
    }
  }
  for (const [key, count] of receiptCounts) {
    if (count !== (requiredCounts.get(key) || 0)) {
      details.push({ field: "human_review_queue_receipts", issue: "unexpected_queue_receipt_count" });
    }
  }

  const countedSummary = countStates(comparisons);
  const countedAggregateSummary = countAggregateStates(aggregates);
  compareCountSummary(value.summary, countedSummary, SUMMARY_FIELDS, "summary", details);
  compareCountSummary(
    value.aggregate_summary,
    countedAggregateSummary,
    V3_AGGREGATE_SUMMARY_FIELDS,
    "aggregate_summary",
    details
  );
  if (SECRET_PATTERNS.some((pattern) => pattern.test(JSON.stringify(value)))) {
    details.push({ field: "comparison", issue: "sensitive_or_external_material_forbidden" });
  }

  return {
    valid: details.length === 0,
    details,
    tenant_scope: scope,
    counted_summary: countedSummary,
    counted_aggregate_summary: countedAggregateSummary,
    review_required_count: [...requiredCounts.values()].reduce((sum, count) => sum + count, 0)
  };
}

export function buildA3MultimodalReviewQueue(value = {}, options = {}) {
  if (!isRecord(value) || Object.keys(value).length === 0) {
    return emptyQueue(options);
  }
  const validation = validateA2MultimodalComparison(value, options);
  if (!validation.valid) {
    return {
      ...emptyQueue({ ...options, sourceContract: value.schema_version }),
      available: false,
      status: "invalid_upstream_contract",
      validation: {
        valid: false,
        error_count: validation.details.length,
        errors: validation.details.slice(0, 24)
      }
    };
  }
  if (value.schema_version === A2_MULTIMODAL_COMPARISON_V3_SCHEMA_VERSION) {
    return buildV3Queue(value, validation, options);
  }

  const receiptByArtifact = new Map(
    value.human_review_queue_receipts.map((receipt) => [receipt.artifact_hash, receipt])
  );
  const items = value.comparisons
    .filter((item) => item.human_review_required === true)
    .map((item) => {
      const receipt = receiptByArtifact.get(item.artifact_hash);
      return {
        queue_id: receipt.receipt_id,
        case_id: item.case_id,
        artifact_hash: item.artifact_hash,
        comparison_hash: receipt.comparison_hash,
        queue_state: receipt.queue_state,
        reviewer_role: receipt.reviewer_role,
        comparison_scope: "case",
        repeat: null,
        comparison_state: item.comparison_state,
        left: providerProjection(value.left_binding, item.left_state, item.left_observed_risk),
        right: providerProjection(value.right_binding, item.right_state, item.right_observed_risk),
        risk_disagreement: item.left_observed_risk !== item.right_observed_risk,
        release_authority: false,
        permitted_action: "handoff_to_authoritative_review_service"
      };
    });

  return {
    schema_version: A3_MULTIMODAL_REVIEW_QUEUE_SCHEMA_VERSION,
    available: true,
    status: items.length ? "human_review_required" : "no_open_multimodal_review",
    source: safeLabel(options.source || "unknown"),
    source_contract: value.schema_version,
    source_commit_alias: safeCommitAlias(options.sourceCommitAlias),
    ingest_mode: safeLabel(options.ingestMode || "tenant_scoped_api"),
    capability_state: safeLabel(options.capabilityState || "contract_supported_not_production_verified"),
    tenant_scope: validation.tenant_scope,
    provider_pair: {
      left: bindingProjection(value.left_binding),
      right: bindingProjection(value.right_binding)
    },
    evidence: {
      left_evidence_hash: value.left_evidence_hash,
      right_evidence_hash: value.right_evidence_hash,
      raw_payload_included: false,
      public_safe: true
    },
    summary: {
      ...validation.counted_summary,
      comparison_count: value.comparisons.length,
      review_required_count: items.length,
      queue_receipt_count: value.human_review_queue_receipts.length
    },
    authority_boundary: {
      upstream_release_authority: false,
      queue_receipts_release_authority: false,
      a3_recomputed_risk: false,
      a3_recomputed_release_decision: false,
      candidate_binding_verified: false,
      can_change_release_decision: false,
      authoritative_resolution_required: "a2.human_review_resolution.v1 plus same-candidate Decision Ledger"
    },
    validation: {
      valid: true,
      error_count: 0,
      summary_recomputed_for_integrity_only: true
    },
    items,
    safety: {
      raw_model_payload_exposed: false,
      raw_media_exposed: false,
      signed_url_exposed: false,
      provider_secret_exposed: false,
      production_ready_claimed: false
    }
  };
}

function buildV3Queue(value, validation, options) {
  const receiptQueues = new Map();
  for (const receipt of value.human_review_queue_receipts) {
    const key = receiptIdentity(receipt.review_scope, receipt.case_id, receipt.artifact_hash);
    const queue = receiptQueues.get(key) || [];
    queue.push(receipt);
    receiptQueues.set(key, queue);
  }

  const takeReceipt = (scope, item) => {
    const queue = receiptQueues.get(receiptIdentity(scope, item.case_id, item.artifact_hash)) || [];
    return queue.shift();
  };
  const repeatItems = value.comparisons
    .filter((item) => item.human_review_required === true)
    .map((item) => {
      const receipt = takeReceipt("repeat", item);
      return {
        queue_id: receipt.receipt_id,
        case_id: item.case_id,
        artifact_hash: item.artifact_hash,
        comparison_artifact_hash: value.comparison_artifact_hash,
        comparison_hash: receipt.comparison_hash,
        queue_state: receipt.queue_state,
        reviewer_role: receipt.reviewer_role,
        comparison_scope: "repeat",
        repeat: item.repeat,
        comparison_state: item.comparison_state,
        left: providerProjection(value.left_binding, item.left_state, item.left_observed_risk),
        right: providerProjection(value.right_binding, item.right_state, item.right_observed_risk),
        risk_disagreement: item.left_observed_risk !== item.right_observed_risk,
        release_authority: false,
        permitted_action: "handoff_to_authoritative_review_service"
      };
    });
  const aggregateItems = value.aggregate_comparisons
    .filter((item) => item.human_review_required === true)
    .map((item) => {
      const receipt = takeReceipt("aggregate", item);
      return {
        queue_id: receipt.receipt_id,
        case_id: item.case_id,
        artifact_hash: item.artifact_hash,
        comparison_artifact_hash: value.comparison_artifact_hash,
        comparison_hash: receipt.comparison_hash,
        queue_state: receipt.queue_state,
        reviewer_role: receipt.reviewer_role,
        comparison_scope: "aggregate",
        repeat: null,
        comparison_state: item.comparison_state,
        left: {
          ...providerProjection(value.left_binding, "aggregate", singleObservedRisk(item.left_valid_risks)),
          valid_risks: [...item.left_valid_risks],
          repeat_count: item.left_repeat_count
        },
        right: {
          ...providerProjection(value.right_binding, "aggregate", singleObservedRisk(item.right_valid_risks)),
          valid_risks: [...item.right_valid_risks],
          repeat_count: item.right_repeat_count
        },
        risk_disagreement: !sameBooleanSet(item.left_valid_risks, item.right_valid_risks),
        release_authority: false,
        permitted_action: "handoff_to_authoritative_review_service"
      };
    });
  const items = [...repeatItems, ...aggregateItems];
  const repeatSummary = validation.counted_summary;
  const aggregateSummary = validation.counted_aggregate_summary;

  return {
    schema_version: A3_MULTIMODAL_REVIEW_QUEUE_SCHEMA_VERSION,
    available: true,
    status: items.length ? "human_review_required" : "no_open_multimodal_review",
    source: safeLabel(options.source || "unknown"),
    source_contract: value.schema_version,
    source_commit_alias: safeCommitAlias(options.sourceCommitAlias),
    ingest_mode: safeLabel(options.ingestMode || "tenant_scoped_api"),
    capability_state: safeLabel(options.capabilityState || "contract_supported_not_production_verified"),
    tenant_scope: validation.tenant_scope,
    provider_pair: {
      left: bindingProjection(value.left_binding),
      right: bindingProjection(value.right_binding)
    },
    evidence: {
      comparison_artifact_hash: value.comparison_artifact_hash,
      left_evidence_hash: value.left_evidence_hash,
      right_evidence_hash: value.right_evidence_hash,
      lineage: isRecord(value.lineage) ? { ...value.lineage } : null,
      raw_payload_included: false,
      public_safe: true
    },
    summary: {
      agreement: repeatSummary.agreement + aggregateSummary.agreement,
      semantic_disagreement: repeatSummary.semantic_disagreement + aggregateSummary.semantic_disagreement,
      unavailable: repeatSummary.unavailable + aggregateSummary.unavailable,
      internally_unstable: aggregateSummary.internally_unstable,
      comparison_count: value.comparisons.length + value.aggregate_comparisons.length,
      repeat_comparison_count: value.comparisons.length,
      aggregate_comparison_count: value.aggregate_comparisons.length,
      review_required_count: items.length,
      queue_receipt_count: value.human_review_queue_receipts.length,
      repeat_summary: { ...repeatSummary },
      aggregate_summary: { ...aggregateSummary }
    },
    authority_boundary: {
      upstream_release_authority: false,
      queue_receipts_release_authority: false,
      a3_recomputed_risk: false,
      a3_recomputed_release_decision: false,
      candidate_binding_verified: false,
      can_change_release_decision: false,
      authoritative_resolution_required: "A2 real human-review receipt, authoritative resolution, and same-candidate Decision Ledger"
    },
    validation: {
      valid: true,
      error_count: 0,
      summary_recomputed_for_integrity_only: true,
      receipt_conservation_verified: true
    },
    items,
    safety: {
      raw_model_payload_exposed: false,
      raw_media_exposed: false,
      signed_url_exposed: false,
      provider_secret_exposed: false,
      production_ready_claimed: false
    }
  };
}

function emptyQueue(options = {}) {
  return {
    schema_version: A3_MULTIMODAL_REVIEW_QUEUE_SCHEMA_VERSION,
    available: false,
    status: "not_ingested",
    source: safeLabel(options.source || "unknown"),
    source_contract: supportedSourceContract(options.sourceContract),
    source_commit_alias: safeCommitAlias(options.sourceCommitAlias),
    ingest_mode: safeLabel(options.ingestMode || "none"),
    capability_state: "not_available",
    tenant_scope: normalizeScope(options.tenantScope || options.tenant_scope || options),
    summary: {
      agreement: 0,
      semantic_disagreement: 0,
      unavailable: 0,
      comparison_count: 0,
      review_required_count: 0,
      queue_receipt_count: 0
    },
    authority_boundary: {
      upstream_release_authority: false,
      queue_receipts_release_authority: false,
      a3_recomputed_risk: false,
      a3_recomputed_release_decision: false,
      candidate_binding_verified: false,
      can_change_release_decision: false
    },
    items: [],
    safety: {
      raw_model_payload_exposed: false,
      raw_media_exposed: false,
      signed_url_exposed: false,
      provider_secret_exposed: false,
      production_ready_claimed: false
    }
  };
}

function validateBinding(value, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, BINDING_FIELDS, prefix, details);
  for (const field of ["provider_id", "model_id", "model_version"]) {
    validateText(value[field], `${prefix}.${field}`, details);
  }
  if (!isHash(value.prompt_hash)) details.push({ field: `${prefix}.prompt_hash`, issue: "sha256_required" });
}

function validateSummary(value, details) {
  if (!isRecord(value)) {
    details.push({ field: "summary", issue: "object_required" });
    return;
  }
  exactFields(value, SUMMARY_FIELDS, "summary", details);
  for (const field of SUMMARY_FIELDS) {
    if (!Number.isInteger(value[field]) || value[field] < 0) {
      details.push({ field: `summary.${field}`, issue: "non_negative_integer_required" });
    }
  }
}

function validateV3Lineage(value, details) {
  if (value === undefined) return;
  if (!isRecord(value)) {
    details.push({ field: "lineage", issue: "object_required" });
    return;
  }
  exactFields(value, LINEAGE_FIELDS, "lineage", details);
  for (const field of ["left_final_matrix_hash", "right_final_matrix_hash"]) {
    if (!isHash(value[field])) details.push({ field: `lineage.${field}`, issue: "sha256_required" });
  }
  for (const field of ["left_partial_journal_hash", "right_partial_journal_hash"]) {
    if (!isOptionalHash(value[field])) details.push({ field: `lineage.${field}`, issue: "optional_sha256_required" });
  }
}

function validateCountSummary(value, fields, prefix, details) {
  if (!isRecord(value)) {
    details.push({ field: prefix, issue: "object_required" });
    return;
  }
  exactFields(value, fields, prefix, details);
  for (const field of fields) {
    if (!Number.isInteger(value[field]) || value[field] < 0) {
      details.push({ field: `${prefix}.${field}`, issue: "non_negative_integer_required" });
    }
  }
}

function compareCountSummary(source, counted, fields, prefix, details) {
  if (!isRecord(source)) return;
  for (const field of fields) {
    if (source[field] !== counted[field]) {
      details.push({ field: `${prefix}.${field}`, issue: "count_mismatch" });
    }
  }
}

function validateObservedRisk(value, field, details) {
  if (![true, false, null].includes(value)) {
    details.push({ field, issue: "boolean_or_null_required" });
  }
}

function validateReviewState(item, prefix, supportedStates, details, reviewRequiredStates = []) {
  if (!supportedStates.has(item.comparison_state)) {
    details.push({ field: `${prefix}.comparison_state`, issue: "unsupported_state" });
  }
  if (typeof item.human_review_required !== "boolean") {
    details.push({ field: `${prefix}.human_review_required`, issue: "boolean_required" });
  }
  if (item.comparison_state === "agreement" && item.human_review_required !== false) {
    details.push({ field: `${prefix}.human_review_required`, issue: "agreement_cannot_require_review" });
  }
  if (reviewRequiredStates.includes(item.comparison_state) && item.human_review_required !== true) {
    details.push({ field: `${prefix}.human_review_required`, issue: "comparison_state_requires_review" });
  }
}

function validateRiskSet(value, field, details) {
  if (
    !Array.isArray(value)
    || value.length > 2
    || value.some((item) => typeof item !== "boolean")
    || new Set(value).size !== value.length
  ) {
    details.push({ field, issue: "unique_boolean_array_required" });
  }
}

function validateText(value, field, details) {
  if (typeof value !== "string" || !value.trim() || value.length > 240 || /[\u0000-\u001f]/.test(value)) {
    details.push({ field, issue: "bounded_text_required" });
  }
}

function exactFields(value, required, prefix, details, optional = []) {
  const allowedSet = new Set([...required, ...optional]);
  for (const field of required) {
    if (!(field in value)) details.push({ field: `${prefix}.${field}`, issue: "required" });
  }
  for (const field of Object.keys(value)) {
    if (!allowedSet.has(field)) details.push({ field: `${prefix}.${field}`, issue: "unknown_field" });
  }
}

function normalizeScope(value = {}) {
  const nested = isRecord(value.tenant_scope) ? value.tenant_scope : value;
  return Object.fromEntries(SCOPE_FIELDS.map((field) => {
    const camel = field.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
    const raw = nested[field] ?? nested[camel];
    return [field, typeof raw === "string" && raw.trim() ? raw.trim().slice(0, 160) : null];
  }));
}

function providerProjection(binding, state, observedRisk) {
  return {
    provider_id: binding.provider_id,
    model_id: binding.model_id,
    model_version: binding.model_version,
    observation_state: state,
    observed_risk: observedRisk
  };
}

function bindingProjection(binding) {
  return {
    provider_id: binding.provider_id,
    model_id: binding.model_id,
    model_version: binding.model_version,
    prompt_hash: binding.prompt_hash
  };
}

function countStates(items = []) {
  const counts = { agreement: 0, semantic_disagreement: 0, unavailable: 0 };
  for (const item of items) {
    if (COMPARISON_STATES.has(item?.comparison_state)) counts[item.comparison_state] += 1;
  }
  return counts;
}

function countAggregateStates(items = []) {
  const counts = { agreement: 0, semantic_disagreement: 0, unavailable: 0, internally_unstable: 0 };
  for (const item of items) {
    if (V3_AGGREGATE_STATES.has(item?.comparison_state)) counts[item.comparison_state] += 1;
  }
  return counts;
}

function comparisonIdentity(item = {}) {
  return JSON.stringify([item.case_id, item.artifact_hash, item.repeat]);
}

function aggregateIdentity(item = {}) {
  return JSON.stringify([item.case_id, item.artifact_hash]);
}

function receiptIdentity(scope, caseId, artifactHash) {
  return JSON.stringify([scope, caseId, artifactHash]);
}

function incrementCount(counts, key) {
  counts.set(key, (counts.get(key) || 0) + 1);
}

function uniqueBooleanCount(value) {
  return Array.isArray(value) ? new Set(value.filter((item) => typeof item === "boolean")).size : 0;
}

function singleObservedRisk(value) {
  return uniqueBooleanCount(value) === 1 ? value[0] : null;
}

function sameBooleanSet(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right)) return false;
  return [...left].sort().join(",") === [...right].sort().join(",");
}

function safeLabel(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return text && /^[A-Za-z0-9_.:/ -]{1,160}$/.test(text) ? text : "unknown";
}

function safeCommitAlias(value) {
  const text = typeof value === "string" ? value.trim() : "";
  return /^[a-f0-9]{7,40}$/.test(text) ? text : null;
}

function supportedSourceContract(value) {
  return SUPPORTED_SOURCE_CONTRACTS.has(value)
    ? value
    : A2_MULTIMODAL_COMPARISON_SCHEMA_VERSION;
}

function isHash(value) {
  return typeof value === "string" && HASH_PATTERN.test(value);
}

function isOptionalHash(value) {
  return value === "" || isHash(value);
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function invalid(details) {
  return {
    valid: false,
    details,
    tenant_scope: normalizeScope({}),
    counted_summary: { agreement: 0, semantic_disagreement: 0, unavailable: 0 },
    review_required_count: 0
  };
}
