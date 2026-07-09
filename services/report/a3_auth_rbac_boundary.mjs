import { buildA3TenantScope } from "./a3_tenant_scope.mjs";

export const A3_AUTH_CONTEXT_SCHEMA_VERSION = "a3.auth_context.v1";
export const A3_RBAC_POLICY_SCHEMA_VERSION = "a3.rbac_policy.v1";
export const A3_AUTHZ_DECISION_SCHEMA_VERSION = "a3.authz_decision.v1";

export const A3_RBAC_ROLES = {
  owner: [
    "project:read",
    "project:ingest",
    "reports:create",
    "reports:share",
    "reports:revoke",
    "release:review",
    "release:approve",
    "admin:plan",
    "team:manage",
    "api_keys:manage",
    "usage:read",
    "billing:read",
    "trust:read",
    "trust:publish",
    "audit:read"
  ],
  admin: [
    "project:read",
    "project:ingest",
    "reports:create",
    "reports:share",
    "reports:revoke",
    "release:review",
    "admin:plan",
    "team:manage",
    "api_keys:manage",
    "usage:read",
    "trust:read",
    "audit:read"
  ],
  developer: [
    "project:read",
    "project:ingest",
    "reports:create",
    "usage:read"
  ],
  reviewer: [
    "project:read",
    "reports:create",
    "reports:share",
    "release:review",
    "release:approve",
    "trust:read",
    "audit:read"
  ],
  auditor: [
    "project:read",
    "reports:create",
    "trust:read",
    "audit:read",
    "usage:read"
  ],
  billing_admin: [
    "project:read",
    "usage:read",
    "billing:read",
    "admin:plan"
  ],
  service_account: [
    "project:read",
    "project:ingest",
    "reports:create"
  ],
  viewer: [
    "project:read"
  ]
};

export const A3_AUTHZ_OPERATION_POLICIES = [
  operation("read_auth_context", "GET /api/a3/auth/context", "project:read", "read_only", {
    event: "auth.context_read",
    resourceType: "auth_context",
    surface: "admin_console"
  }),
  operation("read_rbac_policy", "GET /api/a3/auth/rbac-policy", "audit:read", "read_only", {
    event: "rbac.policy_read",
    resourceType: "rbac_policy",
    surface: "admin_console"
  }),
  operation("authorize_operation", "POST /api/a3/auth/authorize", "project:read", "read_only", {
    event: "authz.operation_checked",
    resourceType: "authz_decision",
    surface: "admin_console"
  }),
  operation("read_dashboard", "GET /api/a3/dashboard", "project:read", "read_only", {
    event: "project.dashboard_read",
    resourceType: "dashboard"
  }),
  operation("import_a1_run_result", "POST /api/a3/import/a1-run-result", "project:ingest", "local_write", {
    event: "a1.run_result_imported",
    resourceType: "a1_run_result",
    a1: ["RunResult", "TraceEvent", "Observation", "ToolCall"],
    a2: ["GradeResult join boundary"]
  }),
  operation("import_a2_grade_result", "POST /api/a3/import/a2-grade-result", "project:ingest", "local_write", {
    event: "a2.grade_result_imported",
    resourceType: "a2_grade_result",
    a1: ["RunResult join boundary"],
    a2: ["GradeResult", "Judge", "FailureTaxonomy"]
  }),
  operation("share_report", "POST /api/a3/reports/share", "reports:share", "local_write", {
    event: "report.share_link_created",
    resourceType: "shareable_report",
    a1: ["RunResult", "artifact refs"],
    a2: ["GradeResult", "ReleaseGate"]
  }),
  operation("revoke_report", "POST /api/a3/reports/:reportId/revoke", "reports:revoke", "local_write", {
    event: "report.share_link_revoked",
    resourceType: "shareable_report"
  }),
  operation("submit_review_waiver", "POST /api/a3/review/waivers", "release:review", "local_write", {
    event: "waiver.requested",
    resourceType: "review_waiver",
    a2: ["ReleaseGate", "policy evaluation"]
  }),
  operation("submit_review_approval", "POST /api/a3/review/approvals", "release:approve", "local_write", {
    event: "approval.recorded",
    resourceType: "review_approval",
    a2: ["ReleaseGate", "policy evaluation"]
  }),
  operation("submit_admin_action", "POST /api/a3/admin/actions/submit", "admin:plan", "plan_only", {
    event: "admin.action_requested",
    resourceType: "saas_admin_action"
  }),
  operation("read_usage", "GET /api/a3/usage/ledger", "usage:read", "read_only", {
    event: "usage.read",
    resourceType: "usage_ledger",
    a1: ["usage ledger"],
    a2: ["model cost policy"]
  }),
  operation("read_billing_readiness", "GET /api/a3/billing/readiness", "billing:read", "read_only", {
    event: "billing.readiness_read",
    resourceType: "billing_readiness",
    a1: ["billing ledger"]
  }),
  operation("rotate_api_key", "POST /v1/api-keys/{api_key_id}/rotate", "api_keys:manage", "hosted_mutation", {
    event: "api_key.rotate_requested",
    resourceType: "api_key",
    requiresHostedAuth: true
  }),
  operation("invite_teammate", "POST /v1/team/invites", "team:manage", "hosted_mutation", {
    event: "team.invite_requested",
    resourceType: "team_invite",
    requiresHostedAuth: true
  }),
  operation("publish_trust_report", "POST /v1/trust/reports/publish", "trust:publish", "hosted_mutation", {
    event: "trust.publish_requested",
    resourceType: "trust_report",
    requiresHostedAuth: true
  })
];

export function buildA3AuthContext(input = {}, options = {}) {
  const tenantScope = buildA3TenantScope(input.tenant_scope || input.tenantScope || input, options);
  const role = normalizeRole(firstPresent(
    input.role,
    input.actor_role,
    input.actorRole,
    options.role,
    "developer"
  ));
  const rawActor = firstPresent(input.actor_id, input.actorId, options.actorId, "actor-local");
  const actorHash = input.actor_hash || input.actorHash || stableHash(rawActor);
  const authState = input.hosted_session === true || input.hostedSession === true
    ? "hosted_session"
    : input.service_account === true || input.serviceAccount === true
      ? "service_account"
      : "local_dev_context";

  return {
    schema_version: A3_AUTH_CONTEXT_SCHEMA_VERSION,
    auth_state: authState,
    actor_id: safeActorAlias(rawActor),
    actor_hash: actorHash,
    role,
    permissions: [...A3_RBAC_ROLES[role]].sort(),
    tenant_scope: tenantScope,
    credential_source: input.credential_source || input.credentialSource || options.credentialSource || "local_header_or_query",
    hosted_auth_required_before_live_saas: true,
    current_enforcement: authState === "hosted_session" ? "hosted_session_observed" : "local_contract_only",
    a1_dependency: "A1 must provide hosted auth middleware, session validation, service-account validation, and durable RBAC enforcement.",
    a2_dependency: "A2 must verify security, release-policy, redaction, and abuse cases that depend on role or approval state.",
    safety: {
      raw_actor_identity_exposed: false,
      raw_email_allowed: false,
      raw_token_allowed: false,
      raw_cookie_allowed: false,
      raw_api_key_allowed: false,
      stores_secret_values: false
    }
  };
}

export function buildA3RbacPolicy(options = {}) {
  const operations = A3_AUTHZ_OPERATION_POLICIES.map((policy) => ({
    ...policy,
    roles_allowed: rolesForPermission(policy.required_permission),
    live_saas_requires_a1_auth: policy.mode === "hosted_mutation" || options.hostedAuthRequired === true,
    denied_state_required: true
  }));
  return {
    schema_version: A3_RBAC_POLICY_SCHEMA_VERSION,
    policy_id: options.policyId || "a3_rbac_policy_2026_07_09",
    generated_at: options.generatedAt || "2026-07-09T00:00:00.000Z",
    enforcement_state: "contract_ready_not_hosted_enforced",
    role_count: Object.keys(A3_RBAC_ROLES).length,
    operation_count: operations.length,
    roles: Object.entries(A3_RBAC_ROLES).map(([role, permissions]) => ({
      role,
      permissions: [...permissions].sort(),
      permission_count: permissions.length
    })),
    operations,
    tenant_scope_required: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"],
    usage_meter: "api_requests",
    audit_event_contract: "ashr.event_envelope.v1",
    safety: {
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      real_cloud_mutations_enabled: false,
      denied_responses_must_be_sanitized: true
    }
  };
}

export function authorizeA3Operation(operationId, contextInput = {}, options = {}) {
  const authContext = contextInput.schema_version === A3_AUTH_CONTEXT_SCHEMA_VERSION
    ? contextInput
    : buildA3AuthContext(contextInput, options);
  const policy = findOperationPolicy(operationId);
  if (!policy) {
    return authzDecision({
      operationId,
      authContext,
      policy: unknownPolicy(operationId),
      allowed: false,
      decision: "denied_unknown_operation",
      reason: "Operation is not in the A3 RBAC boundary contract."
    }, options);
  }

  const hasPermission = authContext.permissions.includes(policy.required_permission);
  const hostedMutationBlocked = policy.mode === "hosted_mutation" && authContext.auth_state !== "hosted_session";
  const allowed = hasPermission && !hostedMutationBlocked;
  const decision = !hasPermission
    ? "denied_missing_permission"
    : hostedMutationBlocked
      ? "blocked_requires_hosted_auth"
      : policy.mode === "plan_only"
        ? "allowed_plan_only"
        : policy.mode === "local_write"
          ? "allowed_local_write"
          : "allowed_read_only";
  const reason = !hasPermission
    ? `${authContext.role} lacks ${policy.required_permission}.`
    : hostedMutationBlocked
      ? "Live cloud mutation requires A1 hosted auth, server-side RBAC, and audit persistence."
      : "A3 local boundary allows this operation within the documented mode.";

  return authzDecision({
    operationId: policy.operation,
    authContext,
    policy,
    allowed,
    decision,
    reason
  }, options);
}

export function validateA3AuthBoundary(value = {}) {
  const serialized = JSON.stringify(value);
  const errors = [];
  if (serialized.match(/Bearer\s+[A-Za-z0-9._-]+|Cookie:|ASHR_API_KEY\s*=|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i)) {
    errors.push("auth boundary contains sensitive-looking material");
  }
  if (value.schema_version === A3_AUTH_CONTEXT_SCHEMA_VERSION) {
    if (!value.actor_hash || value.safety?.raw_actor_identity_exposed !== false) {
      errors.push("auth context must use actor_hash and hide raw identity");
    }
  }
  if (value.schema_version === A3_RBAC_POLICY_SCHEMA_VERSION) {
    if (!Array.isArray(value.operations) || !value.operations.length) {
      errors.push("rbac policy must contain operations");
    }
  }
  if (value.schema_version === A3_AUTHZ_DECISION_SCHEMA_VERSION) {
    if (!value.audit_event || !validateMetadataOnlyEventEnvelope(value.audit_event).valid) {
      errors.push("authz decision must include a valid metadata-only audit event");
    }
  }
  return { valid: errors.length === 0, errors };
}

function operation(operationName, route, requiredPermission, mode, options = {}) {
  return {
    operation: operationName,
    route,
    required_permission: requiredPermission,
    mode,
    surface: options.surface || "product_console",
    audit_event_type: options.event,
    resource_type: options.resourceType,
    requires_hosted_auth: options.requiresHostedAuth === true,
    usage_meters: ["api_requests"],
    a1_dependencies: options.a1 || ["tenant/auth/API gateway", "audit events", "usage ledger"],
    a2_dependencies: options.a2 || ["security verification", "redaction policy"]
  };
}

function authzDecision(input, options = {}) {
  const tenantScope = input.authContext.tenant_scope || buildA3TenantScope({}, options);
  const auditEvent = buildMetadataOnlyEventEnvelope({
    eventType: input.policy.audit_event_type || "authz.checked",
    resourceType: input.policy.resource_type || "authz_decision",
    resourceId: input.operationId,
    tenantScope,
    actorId: input.authContext.actor_hash,
    requestId: options.requestId || "req-a3-authz",
    traceId: options.traceId || "trace-a3-authz",
    payload: {
      schema_version: A3_AUTHZ_DECISION_SCHEMA_VERSION,
      operation: input.operationId,
      role: input.authContext.role,
      decision: input.decision,
      allowed: input.allowed,
      required_permission: input.policy.required_permission
    }
  });

  return {
    schema_version: A3_AUTHZ_DECISION_SCHEMA_VERSION,
    operation: input.operationId,
    allowed: input.allowed,
    decision: input.decision,
    reason: input.reason,
    mode: input.policy.mode,
    required_permission: input.policy.required_permission,
    role: input.authContext.role,
    tenant_scope: tenantScope,
    actor_hash: input.authContext.actor_hash,
    audit_event: auditEvent,
    denied_state: input.allowed
      ? null
      : {
          http_status: input.decision === "blocked_requires_hosted_auth" ? 403 : 403,
          body_policy: "sanitized_error_without_private_evidence",
          customer_message: input.decision === "blocked_requires_hosted_auth"
            ? "This action requires hosted auth and server-side RBAC."
            : "This role is not allowed to perform the requested action."
        },
    safety: {
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_api_key_values_allowed: false,
      real_cloud_mutation_performed: false
    }
  };
}

function rolesForPermission(permission) {
  return Object.entries(A3_RBAC_ROLES)
    .filter(([, permissions]) => permissions.includes(permission))
    .map(([role]) => role)
    .sort();
}

function findOperationPolicy(operationId) {
  return A3_AUTHZ_OPERATION_POLICIES.find((policy) => (
    policy.operation === operationId
    || policy.route === operationId
    || policy.route.replace(/:[A-Za-z]+/g, "{id}") === operationId
  ));
}

function unknownPolicy(operationId) {
  return {
    operation: operationId,
    route: "unknown",
    required_permission: "unknown",
    mode: "unknown",
    audit_event_type: "authz.unknown_operation",
    resource_type: "authz_decision"
  };
}

function normalizeRole(role) {
  const value = String(role || "developer").toLowerCase().replaceAll(/[^a-z0-9_]+/g, "_");
  return A3_RBAC_ROLES[value] ? value : "developer";
}

function safeActorAlias(rawActor) {
  const value = String(rawActor || "");
  if (!value || value.match(/@|Bearer|Cookie|token|key/i)) {
    return "actor_[REDACTED]";
  }
  return value.replaceAll(/[^a-zA-Z0-9_.:-]/g, "_").slice(0, 80) || "actor_[REDACTED]";
}

function stableHash(value) {
  return `actor_${stableHexDigest(value || "actor-local").slice(0, 24)}`;
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function buildMetadataOnlyEventEnvelope(input = {}) {
  const tenantScope = buildA3TenantScope(input.tenantScope || input.tenant_scope || {});
  const payload = sanitizeForHash(input.payload || {});
  const payloadHash = stableHexDigest(stableJson(payload));
  const eventSeed = stableJson({
    event_type: input.eventType,
    resource_type: input.resourceType,
    resource_id: input.resourceId,
    actor_id: input.actorId,
    request_id: input.requestId,
    trace_id: input.traceId,
    payload_hash: payloadHash,
    tenant_scope: tenantScope
  });

  return {
    schema_version: "ashr.event_envelope.v1",
    event_id: `evt_${stableHexDigest(eventSeed).slice(0, 16)}`,
    event_type: input.eventType || "authz.checked",
    organization_id: tenantScope.organization_id,
    tenant_id: tenantScope.tenant_id,
    workspace_id: tenantScope.workspace_id,
    project_id: tenantScope.project_id,
    environment_id: tenantScope.environment_id,
    actor_id: input.actorId || "actor_[REDACTED_HASH]",
    request_id: input.requestId || "req-a3-authz",
    trace_id: input.traceId || "trace-a3-authz",
    resource_type: input.resourceType || "authz_decision",
    resource_id: input.resourceId || "unknown",
    created_at: input.createdAt || "2026-07-09T00:00:00.000Z",
    payload_ref: null,
    payload_hash: payloadHash,
    redaction_status: "metadata_only",
    payload_inline: false,
    payload_schema_version: payload.schema_version || null,
    usage_meter: "api_requests",
    audit_visibility: "metadata_only",
    safety: {
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_signed_urls_allowed: false
    }
  };
}

function validateMetadataOnlyEventEnvelope(event = {}) {
  const errors = [];
  for (const field of [
    "event_id",
    "event_type",
    "schema_version",
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "actor_id",
    "request_id",
    "trace_id",
    "resource_type",
    "resource_id",
    "created_at",
    "payload_hash",
    "redaction_status"
  ]) {
    if (!event[field]) {
      errors.push(`${field} is required`);
    }
  }
  if (event.schema_version !== "ashr.event_envelope.v1") {
    errors.push("schema_version must be ashr.event_envelope.v1");
  }
  if (!/^[a-f0-9]{64}$/.test(String(event.payload_hash || ""))) {
    errors.push("payload_hash must be a 64-character hex digest");
  }
  return { valid: errors.length === 0, errors };
}

function sanitizeForHash(payload = {}) {
  return JSON.parse(JSON.stringify(payload, (key, value) => {
    if (/authorization|cookie|secret|token|password|api_key|signed_url|email/i.test(key)) {
      return "[REDACTED]";
    }
    if (typeof value === "string") {
      return value
        .replace(/\bBearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer [REDACTED]")
        .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]")
        .replace(/https:\/\/[^"\s]+X-Amz-Signature=[^"\s]+/gi, "[REDACTED_SIGNED_URL]");
    }
    return value;
  }));
}

function stableHexDigest(value) {
  const text = String(value ?? "");
  let hashA = 0x811c9dc5;
  let hashB = 0x01000193;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    hashA ^= code;
    hashA = Math.imul(hashA, 0x01000193) >>> 0;
    hashB ^= code + index;
    hashB = Math.imul(hashB, 0x85ebca6b) >>> 0;
  }
  const seed = `${hashA.toString(16).padStart(8, "0")}${hashB.toString(16).padStart(8, "0")}`;
  return seed.repeat(4).slice(0, 64);
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
