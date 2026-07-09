import { redactText } from "./export_redaction_firewall.mjs";

export const A3_SECURITY_REDACTION_GUARD_SCHEMA_VERSION = "a3.security_redaction_guard.v1";

export const A3_SECURITY_GUARD_SURFACES = [
  "admin_console",
  "admin_action",
  "review_workflow",
  "report_center",
  "shareable_report",
  "api_error",
  "json_report",
  "markdown_report"
];

const SENSITIVE_KEY_PATTERNS = [
  {
    pattern_id: "authorization_field",
    category: "token",
    severity: "blocking",
    regex: /^(authorization|x-api-key|api[-_]?key|access[-_]?key)$/i,
    replacement: "[REDACTED_SECRET]"
  },
  {
    pattern_id: "token_field",
    category: "token",
    severity: "blocking",
    regex: /(access|refresh|id|session|csrf|xsrf|jwt|bearer)[-_]?token|token$|session[_-]?id/i,
    replacement: "[REDACTED_TOKEN]"
  },
  {
    pattern_id: "secret_field",
    category: "secret",
    severity: "blocking",
    regex: /secret|password|private[_-]?key|client[_-]?secret/i,
    replacement: "[REDACTED_SECRET]"
  },
  {
    pattern_id: "email_field",
    category: "pii",
    severity: "blocking",
    regex: /(^|[_-])email($|[_-])|email_address|account_email|user_identity/i,
    replacement: "[REDACTED_EMAIL]"
  },
  {
    pattern_id: "signed_url_field",
    category: "signed_url",
    severity: "blocking",
    regex: /signed[_-]?url|presigned[_-]?url|media[_-]?url/i,
    replacement: "[REDACTED_SIGNED_URL]"
  }
];

const DEFAULT_REQUIRED_ROLES = {
  admin_console: ["owner", "admin", "auditor"],
  admin_action: ["owner", "admin"],
  review_workflow: ["owner", "admin", "reviewer", "auditor"],
  report_center: ["owner", "admin", "reviewer", "auditor"],
  shareable_report: ["owner", "admin", "reviewer", "auditor"],
  api_error: ["owner", "admin", "developer", "reviewer", "auditor"],
  json_report: ["owner", "admin", "reviewer", "auditor"],
  markdown_report: ["owner", "admin", "reviewer", "auditor"]
};

export function guardA3SecuritySurface(payload, options = {}) {
  const surface = normalizeSurface(options.surface);
  const tenantScope = normalizeTenantScope(options.tenantScope || options);
  const actor = normalizeActor(options.actor || options.viewer || {});
  const requiredRoles = normalizeRequiredRoles(options.requiredRoles || DEFAULT_REQUIRED_ROLES[surface] || []);
  const tenantDecision = evaluateTenantAccess(actor, tenantScope, options);
  const rbacDecision = evaluateRbacAccess(actor, requiredRoles, options);
  const redacted = redactSecurityValue(payload, { path: "$" });
  const postScan = scanResidualLeaks(redacted.value, { surface });
  const blocked = tenantDecision.allowed !== true
    || rbacDecision.allowed !== true
    || postScan.residual_findings.length > 0;

  return {
    schema_version: A3_SECURITY_REDACTION_GUARD_SCHEMA_VERSION,
    surface,
    status: blocked ? "blocked" : redacted.findings.length > 0 ? "cleaned" : "passed",
    allowed: !blocked,
    tenant_scope: tenantScope,
    tenant: tenantDecision,
    rbac: rbacDecision,
    redaction: {
      status: postScan.residual_findings.length > 0 ? "blocked" : redacted.findings.length > 0 ? "cleaned" : "passed",
      replacement_count: redacted.findings.length,
      residual_finding_count: postScan.residual_findings.length,
      findings: redacted.findings.map((finding) => normalizeFinding(finding, surface)),
      residual_findings: postScan.residual_findings
    },
    value: redacted.value,
    safety: {
      raw_authorization_allowed: false,
      raw_api_key_allowed: false,
      raw_email_allowed: false,
      raw_signed_url_allowed: false,
      fail_closed_on_residual: true
    }
  };
}

export function assertA3SecurityGuardPassed(payload, options = {}) {
  const guarded = guardA3SecuritySurface(payload, options);
  if (!guarded.allowed) {
    const reasons = [
      ...guarded.tenant.reasons,
      ...guarded.rbac.reasons,
      ...guarded.redaction.residual_findings.map((finding) => `residual_${finding.pattern_id}`)
    ];
    throw new Error(`A3 security redaction guard blocked ${guarded.surface}: ${reasons.join(", ") || "unknown"}`);
  }
  return guarded.value;
}

export function redactSecurityValue(value, options = {}) {
  const path = options.path || "$";
  const keyPolicy = options.keyPolicy || null;

  if (value === null || value === undefined || typeof value === "boolean" || typeof value === "number") {
    return redactionResult(value, []);
  }

  if (typeof value === "string") {
    if (keyPolicy) {
      return redactionResult(keyPolicy.replacement, [keyFinding(keyPolicy, path)]);
    }
    const redacted = redactText(value, { path });
    return redactionResult(redacted.value, redacted.findings.map((finding) => normalizeFinding(finding)));
  }

  if (Array.isArray(value)) {
    const mapped = [];
    const findings = [];
    value.forEach((item, index) => {
      const redacted = redactSecurityValue(item, { path: `${path}[${index}]`, keyPolicy });
      mapped.push(redacted.value);
      findings.push(...redacted.findings);
    });
    return redactionResult(mapped, findings);
  }

  if (typeof value === "object") {
    if (keyPolicy) {
      return redactionResult(keyPolicy.replacement, [keyFinding(keyPolicy, path)]);
    }

    const mapped = {};
    const findings = [];
    let collision = 0;
    for (const [key, item] of Object.entries(value)) {
      const redactedKey = redactText(key, { path: `${path}.[key]` });
      const keyFindings = redactedKey.findings.map((finding) => normalizeFinding(finding));
      const childPolicy = sensitivePolicyForKey(redactedKey.value);
      let safeKey = String(redactedKey.value);
      if (Object.hasOwn(mapped, safeKey)) {
        collision += 1;
        safeKey = `${safeKey}_${collision}`;
      }
      const childPath = `${path}.${pathSegment(safeKey)}`;
      const redacted = redactSecurityValue(item, { path: childPath, keyPolicy: childPolicy });
      mapped[safeKey] = redacted.value;
      findings.push(...keyFindings, ...redacted.findings);
    }
    return redactionResult(mapped, findings);
  }

  return redactionResult(String(value), []);
}

export function scanA3SecurityLeaks(value, options = {}) {
  return scanResidualLeaks(value, options).residual_findings;
}

function scanResidualLeaks(value, options = {}) {
  const surface = options.surface || "a3_security_guard";
  const serialized = stableJson(value);
  const scanned = redactText(serialized, { path: "$" });
  return {
    residual_findings: scanned.findings.map((finding) => ({
      ...normalizeFinding(finding, surface),
      post_redaction: true
    }))
  };
}

function normalizeSurface(surface = "json_report") {
  return A3_SECURITY_GUARD_SURFACES.includes(surface) ? surface : "json_report";
}

function normalizeTenantScope(scope = {}) {
  return {
    organization_id: scope.organization_id || scope.organizationId || "org-local",
    project_id: scope.project_id || scope.projectId || "project-local"
  };
}

function normalizeActor(actor = {}) {
  const roles = Array.isArray(actor.roles)
    ? actor.roles
    : actor.role
      ? [actor.role]
      : [];
  return {
    actor_hash: actor.actor_hash || actor.actorHash || "actor_[REDACTED_HASH]",
    organization_id: actor.organization_id || actor.organizationId || null,
    project_id: actor.project_id || actor.projectId || null,
    roles: [...new Set(roles.map((role) => String(role).toLowerCase()))]
  };
}

function normalizeRequiredRoles(roles = []) {
  return [...new Set((Array.isArray(roles) ? roles : [roles])
    .filter(Boolean)
    .map((role) => String(role).toLowerCase()))];
}

function evaluateTenantAccess(actor, tenantScope, options = {}) {
  const strict = options.requireTenantMatch !== false;
  const reasons = [];
  if (strict && actor.organization_id && actor.organization_id !== tenantScope.organization_id) {
    reasons.push("organization_mismatch");
  }
  if (strict && actor.project_id && actor.project_id !== tenantScope.project_id) {
    reasons.push("project_mismatch");
  }
  if (strict && options.requireActorTenant === true && (!actor.organization_id || !actor.project_id)) {
    reasons.push("actor_tenant_missing");
  }
  return {
    allowed: reasons.length === 0,
    required: strict,
    actor_scope: {
      organization_id: actor.organization_id,
      project_id: actor.project_id
    },
    reasons
  };
}

function evaluateRbacAccess(actor, requiredRoles, options = {}) {
  if (options.requireRbac === false || requiredRoles.length === 0) {
    return {
      allowed: true,
      required_roles: requiredRoles,
      actor_roles: actor.roles,
      reasons: []
    };
  }
  const allowed = actor.roles.some((role) => requiredRoles.includes(role));
  return {
    allowed,
    required_roles: requiredRoles,
    actor_roles: actor.roles,
    reasons: allowed ? [] : ["missing_required_role"]
  };
}

function sensitivePolicyForKey(key = "") {
  return SENSITIVE_KEY_PATTERNS.find((policy) => policy.regex.test(String(key))) || null;
}

function normalizeFinding(finding = {}, surface) {
  return {
    surface: surface || finding.surface || "a3_security_guard",
    path: finding.path || "$",
    pattern_id: finding.pattern_id || "unknown",
    category: finding.category || "unknown",
    severity: finding.severity === "warning" ? "blocking" : finding.severity || "blocking",
    replacement: finding.replacement || "[REDACTED]",
    sample: "[REDACTED_SAMPLE]"
  };
}

function keyFinding(policy, path) {
  return {
    surface: "a3_security_guard",
    path,
    pattern_id: policy.pattern_id,
    category: policy.category,
    severity: policy.severity,
    replacement: policy.replacement,
    sample: "[REDACTED_SAMPLE]"
  };
}

function redactionResult(value, findings) {
  return {
    value,
    findings,
    replacement_count: findings.length
  };
}

function pathSegment(key = "") {
  const safe = String(key).replaceAll(/[^A-Za-z0-9_$-]+/g, "_").slice(0, 64);
  return safe || "field";
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}
