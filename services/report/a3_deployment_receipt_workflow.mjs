import { createHash } from "node:crypto";

export const A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION = "a3.deployment_receipt.v1";
export const A3_DEPLOYMENT_RECEIPT_INBOX_SCHEMA_VERSION = "a3.deployment_receipt_inbox.v1";
export const A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION = "a3.deployment_receipt_authoritative_readback.v1";
export const A3_DEPLOYMENT_ACCEPTANCE_PROJECTION_SCHEMA_VERSION = "a3.deployment_acceptance_projection.v1";

const RECEIPT_DEFINITIONS = Object.freeze({
  a2_release_authority: definition("A2", "a2_trusted_spine", "a2_backend", "a2_trusted_service", [
    "same_candidate_bound", "integrity_verified", "decision_allow", "release_ready"
  ]),
  hosted_identity: definition("A1", "identity_verifier_receipt", "a1_backend", "a1_trusted_service", [
    "service_identity_verified", "issuer_audience_verified"
  ]),
  postgres_rls: definition("A1/A3", "postgres_rls_receipt", "deployment_probe", "a1_a3_deployment_verifier", [
    "migration_verified", "rls_allow_verified", "rls_deny_verified", "backup_marker_verified"
  ]),
  queue_worker: definition("A1", "queue_worker_receipt", "a1_backend", "a1_trusted_service", [
    "enqueue_retry_dlq_verified", "lease_recovery_verified", "worker_health_verified"
  ]),
  object_storage: definition("A1/A3", "object_storage_receipt", "deployment_probe", "a1_a3_deployment_verifier", [
    "digest_readback_verified", "retention_verified", "tenant_scope_verified"
  ]),
  deployment_health: definition("A1/A3", "deployment_health_receipt", "deployment_probe", "a1_a3_deployment_verifier", [
    "image_config_migration_verified", "health_verified", "network_policy_verified", "tenant_isolation_verified"
  ]),
  upgrade_rollback: definition("A1/A3", "upgrade_rollback_receipt", "deployment_probe", "a1_a3_deployment_verifier", [
    "upgrade_verified", "failure_injection_verified", "rollback_verified", "restore_verified"
  ]),
  github_app_installation: definition("A1/A3", "github_app_installation_receipt", "github_api_readback", "a1_github_installation_service", [
    "tenant_installation_bound", "repository_bound", "check_identity_verified"
  ]),
  required_check_enforcement: definition("Repository maintainer", "required_check_receipt", "repository_policy_readback", "github_repository_policy_service", [
    "required_context_enforced", "failing_merge_denied", "maintainer_readback_verified"
  ])
});

const REVIEW_ACTIONS = new Set(["acknowledge", "reject", "supersede"]);
const TERMINAL_STATES = new Set(["rejected", "superseded"]);
const AUTHORITATIVE_READBACK_STATUSES = new Set(["verified", "rejected"]);
const AUTHORITATIVE_REJECTION_REASONS = new Set([
  "authority_not_ready",
  "evidence_not_found",
  "hash_mismatch",
  "policy_not_satisfied",
  "stale_evidence",
  "verifier_failed",
  "wrong_candidate",
  "wrong_scope"
]);
const AUTHORITATIVE_READBACK_FIELDS = new Set([
  "schema_version",
  "external_readback_id_alias",
  "receipt_id",
  "blocker_id",
  "candidate_id",
  "run_id",
  "tenant_scope",
  "evidence_sha256",
  "verifier_class",
  "verifier_authority",
  "verification_status",
  "reason_code",
  "verified_at",
  "attestation_sha256",
  "claims"
]);
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
  return value ? { ...value, required_claims: [...value.required_claims] } : null;
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

export function validateA3DeploymentReceiptAuthoritativeReadback(receipt = {}, input = {}, context = {}) {
  const errors = [];
  const definitionValue = RECEIPT_DEFINITIONS[receipt.blocker_id];
  const expectedVersion = integer(context.expected_version ?? context.expectedVersion, -1);
  const resolverIdAlias = text(context.resolver_id_alias || context.resolverIdAlias, "");
  const principalKind = text(context.principal_kind || context.principalKind, "");
  const verificationStatus = text(input.verification_status || input.verificationStatus, "").toLowerCase();
  const reasonCode = text(input.reason_code || input.reasonCode, "");
  const tenantScope = normalizeScope(input.tenant_scope || input.tenantScope);
  const receiptScope = normalizeScope(receipt.tenant_scope || receipt);
  const evidenceSha256 = normalizeSha256(input.evidence_sha256 || input.evidenceSha256);
  const attestationSha256 = normalizeSha256(input.attestation_sha256 || input.attestationSha256);
  const claims = normalizeReadbackClaims(input.claims, definitionValue, errors);
  const externalReadbackIdAlias = text(input.external_readback_id_alias || input.externalReadbackIdAlias, "");

  if (context.trusted_resolver !== true && context.trustedResolver !== true) errors.push(issue("resolver", "trusted_server_resolver_required"));
  if (principalKind !== "service_account") errors.push(issue("principal_kind", "service_account_required"));
  if (!safeOpaqueReference(resolverIdAlias)) errors.push(issue("resolver_id_alias", "opaque_metadata_reference_required"));
  if (receipt.schema_version !== A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION) errors.push(issue("receipt", "unsupported_schema"));
  if (!definitionValue) errors.push(issue("blocker_id", "unsupported_blocker"));
  if (receipt.status !== "acknowledged") errors.push(issue("receipt.status", "acknowledged_receipt_required"));
  if (expectedVersion < 1) errors.push(issue("expected_version", "required"));
  if (expectedVersion >= 1 && expectedVersion !== integer(receipt.version, 0)) errors.push(issue("expected_version", "version_conflict"));
  if (input.schema_version !== A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION) errors.push(issue("schema_version", "unsupported_schema"));
  if (!safeOpaqueReference(externalReadbackIdAlias)) errors.push(issue("external_readback_id_alias", "opaque_metadata_reference_required"));
  if (text(input.receipt_id || input.receiptId, "") !== receipt.receipt_id) errors.push(issue("receipt_id", "receipt_mismatch"));
  if (text(input.blocker_id || input.blockerId, "") !== receipt.blocker_id) errors.push(issue("blocker_id", "blocker_mismatch"));
  if (text(input.candidate_id || input.candidateId, "") !== receipt.candidate_id) errors.push(issue("candidate_id", "candidate_mismatch"));
  if (text(input.run_id || input.runId, "") !== receipt.run_id) errors.push(issue("run_id", "run_mismatch"));
  if (!scopeComplete(tenantScope) || !scopesEqual(tenantScope, receiptScope)) errors.push(issue("tenant_scope", "scope_mismatch"));
  if (!evidenceSha256 || evidenceSha256 !== receipt.evidence_sha256) errors.push(issue("evidence_sha256", "evidence_hash_mismatch"));
  if (!attestationSha256) errors.push(issue("attestation_sha256", "sha256_required"));
  if (text(input.verifier_class || input.verifierClass, "") !== receipt.verifier_class) errors.push(issue("verifier_class", "verifier_class_mismatch"));
  if (definitionValue && text(input.verifier_authority || input.verifierAuthority, "") !== definitionValue.verifier_authority) {
    errors.push(issue("verifier_authority", "authority_mismatch"));
  }
  if (!AUTHORITATIVE_READBACK_STATUSES.has(verificationStatus)) errors.push(issue("verification_status", "unsupported_status"));
  if (verificationStatus === "verified" && reasonCode !== "all_bindings_verified") errors.push(issue("reason_code", "verified_reason_required"));
  if (verificationStatus === "verified" && definitionValue) {
    for (const claim of definitionValue.required_claims) {
      if (claims[claim] !== true) errors.push(issue(`claims.${claim}`, "verified_claim_must_pass"));
    }
  }
  if (verificationStatus === "rejected" && !AUTHORITATIVE_REJECTION_REASONS.has(reasonCode)) errors.push(issue("reason_code", "rejection_reason_required"));
  if (!validTimestamp(input.verified_at || input.verifiedAt)) errors.push(issue("verified_at", "valid_iso_timestamp_required"));
  for (const field of Object.keys(input || {})) {
    if (!AUTHORITATIVE_READBACK_FIELDS.has(field)) errors.push(issue(field, "unsupported_field"));
  }
  if (containsSensitiveMaterial(input)) errors.push(issue("readback", "sensitive_material_forbidden"));

  return {
    valid: errors.length === 0,
    errors,
    normalized: errors.length ? null : {
      external_readback_id_alias: externalReadbackIdAlias,
      receipt_id: receipt.receipt_id,
      blocker_id: receipt.blocker_id,
      candidate_id: receipt.candidate_id,
      run_id: receipt.run_id,
      tenant_scope: receiptScope,
      evidence_sha256: receipt.evidence_sha256,
      verifier_class: receipt.verifier_class,
      verifier_authority: definitionValue.verifier_authority,
      verification_status: verificationStatus,
      reason_code: reasonCode,
      verified_at: new Date(input.verified_at || input.verifiedAt).toISOString(),
      attestation_sha256: attestationSha256,
      required_claims: [...definitionValue.required_claims],
      claims,
      resolver_id_alias: resolverIdAlias
    }
  };
}

export function buildA3DeploymentReceiptAuthoritativeReadback(receipt = {}, input = {}, context = {}) {
  const validation = validateA3DeploymentReceiptAuthoritativeReadback(receipt, input, context);
  if (!validation.valid) return validation;
  const normalized = validation.normalized;
  const previous = isTrustedA3DeploymentReceiptAuthoritativeReadback(context.previous_readback || context.previousReadback)
    ? context.previous_readback || context.previousReadback
    : null;
  const sequence = previous ? integer(previous.sequence, 0) + 1 : 1;
  const core = {
    schema_version: A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
    source: text(receipt.source, "unknown"),
    ...normalized,
    ...normalized.tenant_scope,
    sequence,
    previous_readback_hash: previous?.readback_hash || null,
    binding_validation: {
      receipt_id: true,
      blocker_id: true,
      candidate_id: true,
      run_id: true,
      tenant_scope: true,
      evidence_sha256: true,
      verifier_class: true,
      verifier_authority: true,
      required_claims: normalized.required_claims.every((claim) => normalized.claims[claim] === true),
      all_passed: normalized.verification_status === "verified"
        ? normalized.required_claims.every((claim) => normalized.claims[claim] === true)
        : true
    },
    production_verified: normalized.verification_status === "verified",
    safety: {
      trusted_server_resolver: true,
      service_account_principal_required: true,
      client_supplied_verification_result_used: false,
      raw_evidence_embedded: false,
      raw_secret_values_allowed: false,
      a2_decision_recomputed: false,
      source_acceptance_mutated: false
    }
  };
  const readbackHash = `sha256:${sha256(stableJson(core))}`;
  const record = {
    ...core,
    readback_id: `dprv_${readbackHash.slice(7, 27)}`,
    readback_hash: readbackHash
  };
  return { valid: true, errors: [], normalized, record };
}

export function isTrustedA3DeploymentReceiptAuthoritativeReadback(value = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  if (value.schema_version !== A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION) return false;
  const { readback_id: readbackId, readback_hash: readbackHash, ...core } = value;
  const expectedHash = `sha256:${sha256(stableJson(core))}`;
  return readbackHash === expectedHash
    && readbackId === `dprv_${expectedHash.slice(7, 27)}`
    && value.safety?.trusted_server_resolver === true
    && value.safety?.client_supplied_verification_result_used === false
    && value.binding_validation?.all_passed === true
    && value.production_verified === (value.verification_status === "verified");
}

export function buildA3DeploymentReceiptInbox(records = [], handoff = {}, context = {}, readbacks = []) {
  const expectedCandidateId = text(context.expected_candidate_id || context.expectedCandidateId, "unknown");
  const expectedRunId = text(context.expected_run_id || context.expectedRunId, "unknown");
  const expectedScope = normalizeScope(context.tenant_scope || context.tenantScope);
  const allRecords = (Array.isArray(records) ? records : [])
    .filter((record) => record.schema_version === A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION);
  const scopedRecords = (Array.isArray(records) ? records : [])
    .filter((record) => record.schema_version === A3_DEPLOYMENT_RECEIPT_SCHEMA_VERSION)
    .filter((record) => expectedCandidateId === "unknown" || record.candidate_id === expectedCandidateId)
    .filter((record) => expectedRunId === "unknown" || record.run_id === expectedRunId)
    .sort((left, right) => String(right.submitted_at || "").localeCompare(String(left.submitted_at || "")));
  const allReadbacks = (Array.isArray(readbacks) ? readbacks : [])
    .filter(isTrustedA3DeploymentReceiptAuthoritativeReadback);
  const scopedReadbacks = allReadbacks
    .filter((readback) => expectedCandidateId === "unknown" || readback.candidate_id === expectedCandidateId)
    .filter((readback) => expectedRunId === "unknown" || readback.run_id === expectedRunId)
    .filter((readback) => !scopeComplete(expectedScope) || scopesEqual(normalizeScope(readback.tenant_scope || readback), expectedScope))
    .sort(compareReadbacksNewestFirst);
  const scoped = scopedRecords.map((record) => materializeReceiptAuthority(
    record,
    scopedReadbacks.filter((readback) => readback.receipt_id === record.receipt_id)[0] || null
  ));
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
      production_verified: matching[0]?.authority_validation?.production_verified === true,
      authoritative_readback_id: matching[0]?.authority_validation?.authoritative_readback_id || null,
      deployment_check_status: matching[0]?.authority_validation?.production_verified === true
        ? "production_verified"
        : blocker.status
    };
  });
  return {
    schema_version: A3_DEPLOYMENT_RECEIPT_INBOX_SCHEMA_VERSION,
    source: text(context.source, "unknown"),
    tenant_scope: expectedScope,
    candidate_id: expectedCandidateId,
    run_id: expectedRunId,
    receipt_count: scoped.length,
    excluded_candidate_receipt_count: allRecords.length - scoped.length,
    authoritative_readback_count: scopedReadbacks.length,
    excluded_authoritative_readback_count: allReadbacks.length - scopedReadbacks.length,
    status_counts: countBy(scoped, "status"),
    readback_status_counts: countBy(scopedReadbacks, "verification_status"),
    blocker_slot_count: slots.length,
    missing_slot_count: slots.filter((slot) => slot.receipt_count === 0).length,
    submitted_or_acknowledged_count: slots.filter((slot) => ["submitted", "acknowledged"].includes(slot.intake_status)).length,
    production_verified_count: slots.filter((slot) => slot.production_verified).length,
    slots,
    receipts: scoped,
    authoritative_readbacks: scopedReadbacks,
    workflow: {
      submission_status: "metadata_only",
      authoritative_promotion_api_exposed_to_browser: false,
      authoritative_verification_route: "POST /internal/a3/deployment/receipts/:receiptId/verify",
      authoritative_verification_principal: "service_account",
      authoritative_verification_source: "trusted_server_resolver",
      optimistic_concurrency_required_for_review: true,
      idempotency_required_for_submission: true,
      idempotency_required_for_authoritative_verification: true
    },
    safety: {
      a2_decision_recomputed: false,
      deployment_acceptance_mutated: false,
      submitted_receipt_treated_as_production_proof: false,
      reviewer_acknowledgement_treated_as_production_proof: false,
      only_trusted_server_readbacks_can_produce_verification: true,
      raw_evidence_embedded: false,
      secret_values_allowed: false,
      signed_urls_allowed: false
    }
  };
}

export function buildA3DeploymentAcceptanceProjection(acceptance = {}, inbox = {}) {
  const verifiedSlots = new Map((Array.isArray(inbox.slots) ? inbox.slots : [])
    .filter((slot) => slot.production_verified === true && slot.authoritative_readback_id)
    .map((slot) => [slot.blocker_id, slot]));
  const sourceChecks = Array.isArray(acceptance.checks) ? acceptance.checks : [];
  const changedCheckIds = [];
  const checks = sourceChecks.map((check) => {
    const slot = verifiedSlots.get(check.id);
    if (!slot || check.status === "passed") return { ...check };
    changedCheckIds.push(check.id);
    return {
      ...check,
      status: "passed",
      evidence_class: "authoritative_readback",
      evidence_ref: slot.authoritative_readback_id,
      blocked_reason: null,
      production_proof: true,
      details: {
        ...(check.details || {}),
        authoritative_readback_id: slot.authoritative_readback_id,
        source_receipt_id: slot.latest_receipt?.receipt_id || null,
        projection_only: true
      }
    };
  });
  const blocking = checks.filter((check) => check.required !== false && check.status !== "passed");
  const projectedPassed = checks.filter((check) => check.status === "passed").length;
  return {
    schema_version: A3_DEPLOYMENT_ACCEPTANCE_PROJECTION_SCHEMA_VERSION,
    source_acceptance_id: acceptance.acceptance_id || null,
    source_acceptance_status: text(acceptance.status, "unknown"),
    source_passed: integer(acceptance.summary?.passed, 0),
    status: blocking.length ? "blocked" : "ready_for_rebuild",
    production_accepted: false,
    projected_production_accepted: checks.length > 0 && blocking.length === 0,
    requires_acceptance_rebuild: changedCheckIds.length > 0,
    summary: {
      total_checks: checks.length,
      projected_passed: projectedPassed,
      projected_blocked_or_not_proven: blocking.length,
      authoritative_receipt_check_count: changedCheckIds.length
    },
    changed_check_ids: changedCheckIds,
    blocking_check_ids: blocking.map((check) => check.id),
    checks,
    safety: {
      source_acceptance_mutated: false,
      a2_decision_recomputed: false,
      a2_release_ready_recomputed: false,
      projection_claimed_as_sealed_acceptance: false,
      release_artifact_rebuild_required: changedCheckIds.length > 0,
      raw_evidence_embedded: false
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

function definition(owner, evidenceKind, verifierClass, verifierAuthority, requiredClaims) {
  return Object.freeze({
    owner,
    evidence_kind: evidenceKind,
    verifier_class: verifierClass,
    verifier_authority: verifierAuthority,
    required_claims: Object.freeze([...requiredClaims])
  });
}

function normalizeReadbackClaims(value, definitionValue, errors) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    errors.push(issue("claims", "object_required"));
    return {};
  }
  const allowed = new Set(definitionValue?.required_claims || []);
  const claims = {};
  for (const [key, raw] of Object.entries(value)) {
    if (!allowed.has(key)) {
      errors.push(issue(`claims.${key}`, "unsupported_claim"));
      continue;
    }
    if (typeof raw !== "boolean") {
      errors.push(issue(`claims.${key}`, "boolean_required"));
      continue;
    }
    claims[key] = raw;
  }
  for (const claim of allowed) {
    if (!Object.hasOwn(claims, claim)) errors.push(issue(`claims.${claim}`, "required"));
  }
  return claims;
}

function materializeReceiptAuthority(receipt, readback) {
  const trusted = isTrustedA3DeploymentReceiptAuthoritativeReadback(readback)
    && readback.receipt_id === receipt.receipt_id
    && readback.blocker_id === receipt.blocker_id
    && readback.candidate_id === receipt.candidate_id
    && readback.run_id === receipt.run_id
    && readback.evidence_sha256 === receipt.evidence_sha256
    && readback.verifier_class === receipt.verifier_class
    && scopesEqual(normalizeScope(readback.tenant_scope || readback), normalizeScope(receipt.tenant_scope || receipt));
  const productionVerified = trusted && readback.verification_status === "verified";
  return {
    ...receipt,
    authority_validation: {
      status: !trusted
        ? receipt.authority_validation?.status || "awaiting_authoritative_readback"
        : productionVerified
          ? "production_verified"
          : "authoritative_rejected",
      production_verified: productionVerified,
      authoritative_readback_id: trusted ? readback.readback_id : null,
      verified_at: trusted ? readback.verified_at : null,
      verifier_authority: trusted ? readback.verifier_authority : null,
      attestation_sha256: trusted ? readback.attestation_sha256 : null
    },
    acceptance_effect: {
      changes_deployment_acceptance: false,
      changes_release_ready: false,
      reason: productionVerified
        ? "authoritative_readback_available_for_acceptance_rebuild"
        : trusted
          ? "authoritative_readback_rejected"
          : receipt.acceptance_effect?.reason || "authoritative_readback_missing"
    },
    production_verification: trusted ? readback : null
  };
}

function compareReadbacksNewestFirst(left, right) {
  const sequenceDelta = integer(right.sequence, 0) - integer(left.sequence, 0);
  if (sequenceDelta) return sequenceDelta;
  return String(right.verified_at || "").localeCompare(String(left.verified_at || ""));
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
  return /(?:\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{12,}|Cookie\s*:|RELEASEFOUNDRY(?:_LABS)?_API_KEY\s*[:=]|X-Amz-Signature=|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|C:\\Users\\|\/Users\/)/i.test(serialized);
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

function scopeComplete(value) {
  return Object.values(value || {}).every((item) => typeof item === "string" && item.length > 0);
}

function scopesEqual(left, right) {
  return ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"]
    .every((field) => left?.[field] === right?.[field]);
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
