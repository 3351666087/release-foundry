import { createHash } from "node:crypto";

import { A3_RBAC_ROLES } from "./a3_auth_rbac_boundary.mjs";

export const A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION = "a3.ui_action_security_preflight.v1";

const SCOPE_FIELDS = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];

export const A3_UI_ACTION_SECURITY_POLICIES = Object.freeze({
  "reviewer.approve": actionPolicy(["release:approve"], "approval.recorded", "review_approval", "review_decisions"),
  "reviewer.deny": actionPolicy(["release:review"], "denial.recorded", "review_denial", "review_decisions"),
  "reviewer.waiver": actionPolicy(["release:review"], "waiver.requested", "review_waiver", "review_decisions"),
  "hosted_report.create": actionPolicy(["reports:create", "reports:share"], "report.share_link_created", "hosted_report", "report_creations"),
  "hosted_report.revoke": actionPolicy(["reports:revoke"], "report.share_link_revoked", "hosted_report", "report_revocations"),
  "hosted_report.export": actionPolicy(["reports:create"], "report.export_requested", "hosted_report_export", "report_exports")
});

/**
 * Produces a metadata-only UI authorization decision. It never invokes an
 * executor, persistence adapter, cloud API, or report/review mutation.
 */
export function preflightA3UiAction(input = {}) {
  const action = typeof input.action === "string" ? input.action : "unknown";
  const policy = A3_UI_ACTION_SECURITY_POLICIES[action];
  const requiredPermissions = policy?.required_permissions || [];
  const blockers = [];
  const requestScope = normalizeExplicitScope(input.scope);
  const auth = objectValue(input.auth);
  const session = objectValue(input.session || auth.session);
  const actor = objectValue(input.actor);
  const evidence = objectValue(input.evidence || input.evidence_references);
  const auditEnvelope = objectValue(input.audit_envelope || input.audit);

  if (!policy) {
    addBlocker(blockers, "unknown_action", "action");
  }

  validateAuthentication(auth, session, blockers);
  validateScopes(requestScope, auth, session, actor, blockers);
  validateAuthorization(actor, requiredPermissions, blockers);
  validateEvidence(evidence, blockers);
  validateAuditEnvelope(auditEnvelope, blockers);

  const sensitiveFindings = scanSensitiveInput(input);
  for (const finding of sensitiveFindings) {
    addBlocker(blockers, `raw_${finding.category}_detected`, finding.path);
  }

  const allowed = blockers.length === 0;
  const payloadHash = sha256(stableJson({
    action,
    scope: requestScope,
    actor_hash: safeHashRef(actor.actor_hash),
    evidence: evidenceDigestShape(evidence),
    payload: sensitiveFindings.length
      ? { blocked_sensitive_categories: [...new Set(sensitiveFindings.map((item) => item.category))].sort() }
      : input.payload || {}
  }));

  return {
    schema_version: A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION,
    action,
    allowed,
    blockers,
    required_permissions: [...requiredPermissions],
    audit_event_skeleton: buildAuditSkeleton({
      action,
      policy,
      allowed,
      requestScope,
      actor,
      session,
      auditEnvelope,
      evidence,
      payloadHash
    }),
    usage_meter_intent: {
      meter: policy?.usage_meter || "api_requests",
      quantity: 1,
      disposition: allowed ? "record_after_executor_accepts" : "do_not_record_blocked_action",
      tenant_ref: safeRef(requestScope.tenant_id),
      project_ref: safeRef(requestScope.project_id),
      action_ref: `action:${action}`
    },
    redaction_summary: {
      scanned: true,
      blocked: sensitiveFindings.length > 0,
      finding_count: sensitiveFindings.length,
      categories: [...new Set(sensitiveFindings.map((item) => item.category))].sort(),
      raw_values_returned: false,
      payload_returned: false
    },
    execution_boundary: {
      decision_only: true,
      executor_invoked: false,
      persistence_write_performed: false,
      cloud_write_performed: false
    }
  };
}

export function validateA3UiActionSecurityPreflight(value = {}) {
  const errors = [];
  if (value.schema_version !== A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION) {
    errors.push(`schema_version must be ${A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION}`);
  }
  if (typeof value.allowed !== "boolean" || !Array.isArray(value.blockers)) {
    errors.push("allowed and blockers are required");
  }
  if (value.allowed === true && value.blockers?.length) {
    errors.push("allowed decisions cannot contain blockers");
  }
  if (value.execution_boundary?.cloud_write_performed !== false) {
    errors.push("preflight must not perform cloud writes");
  }
  if (JSON.stringify(value).match(/Bearer\s+\S+|X-Amz-Signature=|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)) {
    errors.push("preflight output contains sensitive-looking material");
  }
  return { valid: errors.length === 0, errors };
}

function actionPolicy(requiredPermissions, eventType, resourceType, usageMeter) {
  return Object.freeze({
    required_permissions: Object.freeze(requiredPermissions),
    event_type: eventType,
    resource_type: resourceType,
    usage_meter: usageMeter
  });
}

function validateAuthentication(auth, session, blockers) {
  if (auth.authenticated !== true || auth.auth_state !== "hosted_session") {
    addBlocker(blockers, "authentication_required", "auth");
  }
  if (session.state !== "active" || !isSafeReference(session.session_ref)) {
    addBlocker(blockers, "active_session_required", "session");
  }
  if (session.expires_at && !isFutureTimestamp(session.expires_at)) {
    addBlocker(blockers, "session_expired", "session.expires_at");
  }
}

function validateScopes(requestScope, auth, session, actor, blockers) {
  const missing = SCOPE_FIELDS.filter((field) => !requestScope[field]);
  if (missing.length) {
    addBlocker(blockers, "scope_incomplete", "scope", { fields: missing });
  }

  for (const [sourceName, source] of [["auth", auth], ["session", session], ["actor", actor]]) {
    const sourceScope = normalizeExplicitScope(source.scope || source.tenant_scope);
    const sourceMissing = SCOPE_FIELDS.filter((field) => !sourceScope[field]);
    if (sourceMissing.length) {
      addBlocker(blockers, "scope_binding_missing", `${sourceName}.scope`, { source: sourceName, fields: sourceMissing });
      continue;
    }
    const mismatches = SCOPE_FIELDS.filter((field) => requestScope[field] && sourceScope[field] !== requestScope[field]);
    if (mismatches.length) {
      addBlocker(blockers, "scope_mismatch", `${sourceName}.scope`, { source: sourceName, fields: mismatches });
    }
  }
}

function validateAuthorization(actor, requiredPermissions, blockers) {
  const role = typeof actor.role === "string" ? actor.role.toLowerCase() : "";
  const declared = Array.isArray(actor.permissions) ? new Set(actor.permissions.map(String)) : new Set();
  const rolePermissions = new Set(A3_RBAC_ROLES[role] || []);
  if (!rolePermissions.size) {
    addBlocker(blockers, "actor_role_invalid", "actor.role");
  }
  if (!Array.isArray(actor.permissions)) {
    addBlocker(blockers, "actor_permissions_missing", "actor.permissions");
  }
  const missing = requiredPermissions.filter((permission) => !declared.has(permission) || !rolePermissions.has(permission));
  if (missing.length) {
    addBlocker(blockers, "permission_denied", "actor.permissions", { permissions: missing });
  }
  if (!isSha256(actor.actor_hash)) {
    addBlocker(blockers, "actor_hash_required", "actor.actor_hash");
  }
}

function validateEvidence(evidence, blockers) {
  for (const lane of ["a1", "a2"]) {
    const references = evidence[lane];
    if (!Array.isArray(references) || references.length === 0) {
      addBlocker(blockers, `${lane}_evidence_references_required`, `evidence.${lane}`);
      continue;
    }
    if (references.some((item) => !validEvidenceReference(item))) {
      addBlocker(blockers, `${lane}_evidence_reference_invalid`, `evidence.${lane}`);
    }
  }
}

function validateAuditEnvelope(envelope, blockers) {
  if (envelope.schema_version !== "ashr.event_envelope.v1") {
    addBlocker(blockers, "audit_envelope_required", "audit_envelope");
    return;
  }
  const missing = ["request_ref", "trace_ref"].filter((field) => !isSafeReference(envelope[field]));
  if (missing.length || envelope.payload_inline === true) {
    addBlocker(blockers, "audit_envelope_invalid", "audit_envelope", { fields: missing });
  }
}

function buildAuditSkeleton(input) {
  const scope = input.requestScope;
  return {
    schema_version: "ashr.event_envelope.v1",
    event_type: input.policy?.event_type || "ui_action.unknown_blocked",
    event_ref: safeRef(input.auditEnvelope.event_ref) || `evt_ref:${sha256(`${input.action}:${input.payloadHash}`).slice(0, 24)}`,
    organization_ref: safeRef(scope.organization_id),
    tenant_ref: safeRef(scope.tenant_id),
    workspace_ref: safeRef(scope.workspace_id),
    project_ref: safeRef(scope.project_id),
    environment_ref: safeRef(scope.environment_id),
    actor_hash: safeHashRef(input.actor.actor_hash),
    session_ref: safeRef(input.session.session_ref),
    request_ref: safeRef(input.auditEnvelope.request_ref),
    trace_ref: safeRef(input.auditEnvelope.trace_ref),
    resource_type: input.policy?.resource_type || "unknown",
    resource_ref: safeRef(resourceReference(input.action, input.requestScope, input.auditEnvelope)),
    decision_hash: sha256(stableJson({ action: input.action, allowed: input.allowed, payload_hash: input.payloadHash })),
    payload_hash: input.payloadHash,
    evidence_refs_hash: sha256(stableJson(evidenceDigestShape(input.evidence))),
    payload_inline: false,
    redaction_status: "metadata_only"
  };
}

function scanSensitiveInput(input) {
  const findings = [];
  walk(input, "$", (key, value, path) => {
    const normalizedKey = String(key || "").toLowerCase();
    const referenceKey = /(?:_ref|_hash|sha256)$/.test(normalizedKey);
    const sensitiveCategory = sensitiveCategoryForKey(normalizedKey);
    if (sensitiveCategory && !referenceKey) {
      findings.push({ category: sensitiveCategory, path });
      return;
    }
    if (sensitiveCategory && referenceKey) {
      const hashKey = /(?:_hash|sha256)$/.test(normalizedKey);
      const validIndirection = hashKey ? isSha256(value) : isSafeIndirectionReference(value);
      if (!validIndirection) findings.push({ category: sensitiveCategory, path });
      return;
    }
    if (typeof value !== "string") return;
    if (/\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/i.test(value)
      || /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/.test(value)) {
      findings.push({ category: "token", path });
    } else if (/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(value)) {
      findings.push({ category: "email", path });
    } else if (/https?:\/\/\S+(?:X-Amz-(?:Signature|Credential)|Signature=|sig=|token=)\S*/i.test(value)) {
      findings.push({ category: "signed_url", path });
    } else if (/\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[0-9A-Z]{16})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/i.test(value)) {
      findings.push({ category: "secret", path });
    }
  });
  return uniqueFindings(findings);
}

function walk(value, path, visit, key = "") {
  visit(key, value, path);
  if (Array.isArray(value)) {
    value.forEach((item, index) => walk(item, `${path}[${index}]`, visit, String(index)));
  } else if (value && typeof value === "object") {
    for (const [childKey, child] of Object.entries(value)) {
      walk(child, `${path}.${childKey}`, visit, childKey);
    }
  }
}

function normalizeExplicitScope(value) {
  const source = value && typeof value === "object" ? value : {};
  return Object.fromEntries(SCOPE_FIELDS.map((field) => [field, safeScopeValue(source[field]) || null]));
}

function validEvidenceReference(value) {
  return value && typeof value === "object"
    && isSafeReference(value.ref || value.artifact_ref || value.evidence_ref)
    && isSha256(value.sha256 || value.hash);
}

function evidenceDigestShape(evidence) {
  return Object.fromEntries(["a1", "a2"].map((lane) => [lane, Array.isArray(evidence?.[lane])
    ? evidence[lane].map((item) => ({ ref: safeRef(item?.ref || item?.artifact_ref || item?.evidence_ref), sha256: safeHashRef(item?.sha256 || item?.hash) }))
    : []]));
}

function resourceReference(action, scope, auditEnvelope) {
  return auditEnvelope.resource_ref
    || (action.startsWith("reviewer.") ? `release:${scope.project_id}:${scope.environment_id}` : `report:${scope.project_id}`);
}

function addBlocker(blockers, code, field, details = {}) {
  const key = `${code}:${field}`;
  if (blockers.some((item) => `${item.code}:${item.field}` === key)) return;
  blockers.push({ code, field, ...details });
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function isSafeReference(value) {
  return typeof value === "string"
    && value.length >= 3
    && value.length <= 256
    && /^[A-Za-z0-9][A-Za-z0-9:._/-]*$/.test(value);
}

function isSafeIndirectionReference(value) {
  return isSafeReference(value) && /^[A-Za-z][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9:._/-]*$/.test(value);
}

function sensitiveCategoryForKey(key) {
  if (/(?:^|_)email(?:$|_)|email_address|user_identity/i.test(key)) return "email";
  if (/signed[_-]?url|presigned[_-]?url|media[_-]?url/i.test(key)) return "signed_url";
  if (/authorization|cookie|(?:^|_)(?:access|refresh|id|csrf|xsrf|bearer)?_?token(?:$|_)|session[_-]?id/i.test(key)) return "token";
  if (/password|passphrase|private[_-]?key|api[_-]?key|(?:^|_)secret(?:$|_)/i.test(key)) return "secret";
  return null;
}

function safeRef(value) {
  return isSafeReference(value) ? value : null;
}

function isSha256(value) {
  return /^[a-f0-9]{64}$/i.test(String(value || ""));
}

function safeHashRef(value) {
  return isSha256(value) ? String(value).toLowerCase() : null;
}

function safeScopeValue(value) {
  return isSafeReference(value) ? value : null;
}

function isFutureTimestamp(value) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && timestamp > Date.now();
}

function uniqueFindings(findings) {
  return [...new Map(findings.map((item) => [`${item.category}:${item.path}`, item])).values()];
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) return value.map(sortForStableJson);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortForStableJson(item)]));
  }
  return value;
}
