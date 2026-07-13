import { createHash } from "node:crypto";

export const A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION = "a3.deployment_receipt.v1";
export const A3_DEPLOYMENT_RECEIPT_INBOX_SCHEMA_VERSION = "a3.deployment_receipt_inbox.v1";

const RECEIPT_DEFINITIONS = Object.freeze({
  a2_release_authority: definition("A2", "a2_trusted_spine", "a2_backend"),
  hosted_identity: definition("A1", "identity_verifier_receipt", "a1_backend"),
  postgres_rls: definition("A1/A3", "postgres_rls_receipt", "deployment_probe"),
  queue_worker: definition("A1", "queue_worker_receipt", "a1_backend"),
  object_storage: definition("A1/A3", "object_storage_receipt", "deployment_probe"),
  deployment_health: definition("A1/A3", "deployment_health_receipt", "deployment_probe"),
  upgrade_rollback: definition("A1/A3", "upgrade_rollback_receipt", "deployment_probe"),
  github_app_installation: definition("A1/A3", "github_app_installation_receipt", "github_api_readback"),
  required_check_enforcement: definition("Repository maintainer", "required_check_receipt", "repository_policy_readback")
});

const REVIEW_ACTIONS = new Set(["acknowledge", "reject", "supersede"]);
const TERMINAL_STATES = new Set(["rejected", "superseded"]);
const SAFE_SELECTOR_KEYS = new Set([
  "deployment_id_alias",
  "image_digest",
  "config_digest",
  "migration_id_alias",
  "health_status",
  "verifier_version",
  "worker_version",
  "object_version_alias",
  "retention_policy_alias",
  "backup_id_alias",
  "restore_id_alias",
  "installation_alias",
  "app_slug",
  "required_check_context",
  "policy_receipt_alias",
  "decision_record_id",
  "decision_ledger_head_hash"
]);
const REASON_CODES = new Set([
  "metadata_complete",
  "wrong_candidate",
  "wrong_scope",
  "hash_mismatch",
  "stale_evidence",
  "insufficient_authority",
  "superseded_by_newer_receipt",
  "invalid_evidence_reference"
]);

export function deploymentReceiptDefinition(blockerId) {
  const value = RECEIPT_DEFINITIONS[String(blockerId || "")];
  return value ? { ...value } : null;
}

export function deploymentReceiptBlockerIds() {
  return Object.keys(RECEIPT_DEFINITIONS);
}

export function validateA3DeploymentReceiptSubmission(input = {}, context = {}) {
  const errors = [];
  const blockerId = text(input.blocker_id || input.blockerId, "");
  const definitionValue = RECEIPT_DEFINITIONS[blockerId];
  const candidateId = text(input.candidate_id || input.candidateId, "");
  const runId = text(input.run_id || input.runId, "");
  const evidenceRef = text(input.evidence_ref || input.evidenceRef, "");
  const evidenceSha256 = normalizeSha256(input.evidence_sha256 || input.evidenceSha256);
  const evidenceKind = text(input.evidence_kind || input.evidenceKind, definitionValue?.evidence_kind || "");
  const verifierClass = text(input.verifier_class || input.verifierClass, definitionValue?.verifier_class || "");
  const expectedCandidateId = text(context.expected_candidate_id || context.expectedCandidateId, "");
  const expectedRunId = text(context.expected_run_id || context.expectedRunId, "");
  const selectors = normalizeSelectors(input.selectors, errors);

  if (!definitionValue) errors.push(issue("blocker_id", "unsupported_blocker"));
  if (!candidateId) errors.push(issue("candidate_id", "required"));
  if (expectedCandidateId && candidateId !== expectedCandidateId) errors.push(issue("candidate_id", "candidate_mismatch"));
  if (!runId) errors.push(issue("run_id", "required"));
  if (expectedRunId && runId !== expectedRunId) errors.push(issue("run_id", "run_mismatch"));
  if (!safeOpaqueReference(evidenceRef)) errors.push(issue("evidence_ref", "opaque_metadata_reference_required"));
  if (!evidenceSha256) errors.push(issue("evidence_sha256", "sha256_required"));
  if (definitionValue && evidenceKind !== definitionValue.evidence_kind) errors.push(issue("evidence_kind", "does_not_match_blocker"));
  if (definitionValue && verifierClass !== definitionValue.verifier_class) errors.push(issue("verifier_class", "does_not_match_blocker"));
  if (!validTimestamp(input.captured_at || input.capturedAt)) errors.push(issue("captured_at", "valid_iso_timestamp_required"));
  if (containsSensitiveMaterial(input)) errors.push(issue("submission", "sensitive_material_forbidden"));

  return {
    valid: errors.length === 0,
    errors,
    normalized: errors.length ? null : {
      blocker_id: blockerId,
      owner: definitionValue.owner,
      candidate_id: candidateId,
      run_id: runId,
      evidence_ref: evidenceRef,
      evidence_sha256: evidenceSha256,
      evidence_kind: evidenceKind,
      verifier_class: verifierClass,
      captured_at: new Date(input.captured_at || input.capturedAt).toISOString(),
      selectors
    }
  };
}

export function buildA3DeploymentReceiptSubmission(input = {}, context = {}) {
  const validation = validateA3DeploymentReceiptSubmission(input, context);
  if (!validation.valid) return validation;
  const normalized = validation.normalized;
  const submittedAt = normalizedTimestamp(context.submitted_at || context.submittedAt);
  const tenantScope = normalizeScope(context.tenant_scope || context.tenantScope);
  const fingerprint = deploymentReceiptSubmissionFingerprint(normalized, { tenant_scope: tenantScope });
  const receiptId = text(context.receipt_id || context.receiptId, `dpr_${fingerprint.slice(0, 20)}`);
  const actorHash = safeActorHash(context.actor_hash || context.actorHash);
  const record = {
    schema_version: A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION,
    receipt_id: receiptId,
    source: text(context.source, "unknown"),
    tenant_scope: tenantScope,
    ...tenantScope,
    ...normalized,
    status: "submitted",
    version: 1,
    submitted_at: submittedAt,
    submitted_by_hash: actorHash,
    metadata_validation: {
      status: "passed",
      schema_version: A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION,
      payload_hash: fingerprint
    },
    authority_validation: {
      status: "pending_external_verifier",
      production_verified: false,
      authoritative_readback_id: null
    },
    acceptance_effect: {
      changes_deployment_acceptance: false,
      changes_release_ready: false,
      reason: "submission_is_not_authoritative_readback"
    },
    history: [{
      sequence: 1,
      action: "submitted",
      status: "submitted",
      actor_hash: actorHash,
      reason_code: "metadata_complete",
      created_at: submittedAt
    }],
    safety: receiptSafety()
  };
  return { valid: true, errors: [], normalized, fingerprint, record };
}

export function reviewA3DeploymentReceipt(record = {}, review = {}, context = {}) {
  const errors = [];
  const action = text(review.action, "").toLowerCase();
  const expectedVersion = integer(review.expected_version ?? review.expectedVersion, -1);
  const reasonCode = text(review.reason_code || review.reasonCode, "");
  const currentVersion = integer(record.version, 0);

  if (record.schema_version !== A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION) errors.push(issue("receipt", "unsupported_schema"));
  if (!REVIEW_ACTIONS.has(action)) errors.push(issue("action", "unsupported_action"));
  if (TERMINAL_STATES.has(record.status)) errors.push(issue("status", "terminal_state"));
  if (expectedVersion < 1) errors.push(issue("expected_version", "required"));
  if (expectedVersion >= 1 && expectedVersion !== currentVersion) errors.push(issue("expected_version", "version_conflict"));
  if (!REASON_CODES.has(reasonCode)) errors.push(issue("reason_code", "unsupported_reason"));
  if (action === "acknowledge" && reasonCode !== "metadata_complete") errors.push(issue("reason_code", "acknowledgement_requires_metadata_complete"));
  if (action === "supersede" && reasonCode !== "superseded_by_newer_receipt") errors.push(issue("reason_code", "supersede_reason_required"));
  if (containsSensitiveMaterial(review)) errors.push(issue("review", "sensitive_material_forbidden"));
  if (errors.length) return { valid: false, errors };

  const reviewedAt = normalizedTimestamp(context.reviewed_at || context.reviewedAt);
  const reviewerHash = safeActorHash(context.actor_hash || context.actorHash);
  const status = action === "acknowledge" ? "acknowledged" : action === "reject" ? "rejected" : "superseded";
  return {
    valid: true,
    errors: [],
    record: {
      ...record,
      status,
      version: currentVersion + 1,
      reviewed_at: reviewedAt,
      reviewed_by_hash: reviewerHash,
      review_reason_code: reasonCode,
      authority_validation: {
        ...record.authority_validation,
        status: status === "acknowledged" ? "awaiting_authoritative_readback" : "not_applicable",
        production_verified: false,
        authoritative_readback_id: null
      },
      acceptance_effect: {
        changes_deployment_acceptance: false,
        changes_release_ready: false,
        reason: status === "acknowledged"
          ? "metadata_acknowledgement_is_not_production_verification"
          : `receipt_${status}`
      },
      history: [
        ...(Array.isArray(record.history) ? record.history : []),
        {
          sequence: (Array.isArray(record.history) ? record.history.length : 0) + 1,
          action,
          status,
          actor_hash: reviewerHash,
          reason_code: reasonCode,
          created_at: reviewedAt
        }
      ],
      safety: receiptSafety()
    }
  };
}

export function buildA3DeploymentReceiptInbox(records = [], handoff = {}, context = {}) {
  const expectedCandidateId = text(context.expected_candidate_id || context.expectedCandidateId, "unknown");
  const expectedRunId = text(context.expected_run_id || context.expectedRunId, "unknown");
  const allRecords = (Array.isArray(records) ? records : [])
    .filter((record) => record.schema_version === A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION);
  const scoped = (Array.isArray(records) ? records : [])
    .filter((record) => record.schema_version === A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION)
    .filter((record) => expectedCandidateId === "unknown" || record.candidate_id === expectedCandidateId)
    .filter((record) => expectedRunId === "unknown" || record.run_id === expectedRunId)
    .sort((left, right) => String(right.submitted_at || "").localeCompare(String(left.submitted_at || "")));
  const blockers = Array.isArray(handoff.blocking_items) ? handoff.blocking_items : [];
  const slots = blockers.map((blocker) => {
    const matching = scoped.filter((record) => record.blocker_id === blocker.id);
    const definitionValue = RECEIPT_DEFINITIONS[blocker.id] || {};
    return {
      blocker_id: blocker.id,
      label: blocker.label,
      owner: blocker.owner,
      required_receipt: blocker.required_receipt,
      evidence_kind: definitionValue.evidence_kind || "unknown",
      verifier_class: definitionValue.verifier_class || "unknown",
      receipt_count: matching.length,
      latest_receipt: matching[0] || null,
      intake_status: matching[0]?.status || "missing",
      production_verified: false,
      deployment_check_status: blocker.status
    };
  });
  return {
    schema_version: A3_DEPLOYMENT_RECEIPT_INBOX_SCHEMA_VERSION,
    source: text(context.source, "unknown"),
    tenant_scope: normalizeScope(context.tenant_scope || context.tenantScope),
    candidate_id: expectedCandidateId,
    run_id: expectedRunId,
    receipt_count: scoped.length,
    excluded_candidate_receipt_count: allRecords.length - scoped.length,
    status_counts: countBy(scoped, "status"),
    blocker_slot_count: slots.length,
    missing_slot_count: slots.filter((slot) => slot.receipt_count === 0).length,
    submitted_or_acknowledged_count: slots.filter((slot) => ["submitted", "acknowledged"].includes(slot.intake_status)).length,
    production_verified_count: 0,
    slots,
    receipts: scoped,
    workflow: {
      submission_status: "metadata_only",
      authoritative_promotion_api_exposed_to_browser: false,
      optimistic_concurrency_required_for_review: true,
      idempotency_required_for_submission: true
    },
    safety: {
      a2_decision_recomputed: false,
      deployment_acceptance_mutated: false,
      submitted_receipt_treated_as_production_proof: false,
      raw_evidence_embedded: false,
      secret_values_allowed: false,
      signed_urls_allowed: false
    }
  };
}

export function deploymentReceiptSubmissionFingerprint(input = {}, context = {}) {
  return sha256(stableJson({
    blocker_id: input.blocker_id,
    owner: input.owner,
    candidate_id: input.candidate_id,
    run_id: input.run_id,
    evidence_ref: input.evidence_ref,
    evidence_sha256: input.evidence_sha256,
    evidence_kind: input.evidence_kind,
    verifier_class: input.verifier_class,
    captured_at: input.captured_at,
    selectors: input.selectors || {},
    tenant_scope: normalizeScope(context.tenant_scope || context.tenantScope)
  }));
}

function definition(owner, evidenceKind, verifierClass) {
  return Object.freeze({ owner, evidence_kind: evidenceKind, verifier_class: verifierClass });
}

function normalizeSelectors(value, errors) {
  if (value === undefined || value === null) return {};
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    errors.push(issue("selectors", "object_required"));
    return {};
  }
  const entries = Object.entries(value);
  if (entries.length > 12) errors.push(issue("selectors", "too_many_fields"));
  const selectors = {};
  for (const [key, raw] of entries) {
    if (!SAFE_SELECTOR_KEYS.has(key)) {
      errors.push(issue(`selectors.${key}`, "unsupported_field"));
      continue;
    }
    const normalized = text(raw, "");
    if (!normalized || normalized.length > 240 || containsSensitiveMaterial(normalized)) {
      errors.push(issue(`selectors.${key}`, "unsafe_or_invalid_value"));
      continue;
    }
    selectors[key] = normalized;
  }
  return selectors;
}

function safeOpaqueReference(value) {
  return Boolean(value)
    && value.length <= 240
    && /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(value)
    && !/[?#@\\]/.test(value)
    && !/(?:^|\/)\.\.(?:\/|$)/.test(value)
    && !/^(?:https?|file):/i.test(value)
    && !/^[A-Za-z]:/.test(value)
    && !containsSensitiveMaterial(value);
}

function normalizeSha256(value) {
  const normalized = text(value, "").toLowerCase().replace(/^sha256:/, "");
  return /^[a-f0-9]{64}$/.test(normalized) ? `sha256:${normalized}` : null;
}

function containsSensitiveMaterial(value) {
  const serialized = typeof value === "string" ? value : stableJson(value);
  return /(?:\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{12,}|Cookie\s*:|ASHR(?:_LABS)?_API_KEY\s*[:=]|X-Amz-Signature=|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|C:\\Users\\|\/Users\/)/i.test(serialized);
}

function normalizeScope(value = {}) {
  const nested = value.tenant_scope || value.tenantScope || {};
  return {
    organization_id: text(value.organization_id ?? value.organizationId ?? nested.organization_id, ""),
    tenant_id: text(value.tenant_id ?? value.tenantId ?? nested.tenant_id, ""),
    workspace_id: text(value.workspace_id ?? value.workspaceId ?? nested.workspace_id, ""),
    project_id: text(value.project_id ?? value.projectId ?? nested.project_id, ""),
    environment_id: text(value.environment_id ?? value.environmentId ?? nested.environment_id, "")
  };
}

function receiptSafety() {
  return {
    raw_evidence_embedded: false,
    raw_secret_values_allowed: false,
    raw_signed_urls_allowed: false,
    production_verified_by_submission: false,
    a2_decision_recomputed: false,
    deployment_acceptance_mutated: false
  };
}

function safeActorHash(value) {
  const normalized = text(value, "actor_[REDACTED_HASH]");
  return normalized.length <= 128 && !containsSensitiveMaterial(normalized)
    ? normalized
    : `actor_${sha256(normalized).slice(0, 16)}`;
}

function validTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) return false;
  return Number.isFinite(Date.parse(value));
}

function normalizedTimestamp(value) {
  return validTimestamp(value) ? new Date(value).toISOString() : new Date().toISOString();
}

function countBy(items, field) {
  return items.reduce((counts, item) => {
    const key = text(item[field], "unknown");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function issue(field, issueValue) {
  return { field, issue: issueValue };
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function text(value, fallback = "unknown") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function integer(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : fallback;
}
