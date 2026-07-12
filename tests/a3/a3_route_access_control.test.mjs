import assert from "node:assert/strict";
import { test } from "node:test";

import {
  A3_AUTHZ_OPERATION_POLICIES,
  A3_RBAC_ROLES,
  buildA3RbacPolicy
} from "../../services/report/a3_auth_rbac_boundary.mjs";
import {
  A3_PUBLIC_ROUTE_PATTERNS,
  A3_REQUIRED_SCOPE_FIELDS,
  A3_ROUTE_ACCESS_MODES,
  A3_SENSITIVE_ROUTE_PATTERNS,
  buildA3RouteAccessContract,
  guardA3RouteAccess,
  matchA3RouteAccess,
  validateA3RouteAccessRegistry,
  validateA3RouteScope,
  validateTrustedA3Principal
} from "../../services/report/a3_route_access_control.mjs";

const NOW = "2026-07-12T08:00:00.000Z";
const FUTURE = "2026-07-12T09:00:00.000Z";
const SCOPE = Object.freeze({
  organization_id: "org-acme",
  tenant_id: "tenant-acme",
  workspace_id: "workspace-risk",
  project_id: "project-refunds",
  environment_id: "production"
});

test("A3 route access exposes only health and token-scoped report routes publicly", () => {
  assert.deepEqual(
    A3_PUBLIC_ROUTE_PATTERNS.map((route) => `${route.method} ${route.path_pattern}`),
    ["GET /api/a3/health", "GET /r/{share_token}"]
  );

  const health = guardA3RouteAccess({ method: "GET", url: "/api/a3/health" });
  assert.equal(health.allowed, true);
  assert.equal(health.decision, "allowed_public_route");
  assert.equal(health.route.access, "public");

  const token = "share-token-must-never-appear";
  const sharedReport = guardA3RouteAccess({
    method: "GET",
    url: `/r/${token}?role=owner`,
    headers: { authorization: "Bearer client-secret" },
    principal: { role: "owner", trusted: true }
  });
  assert.equal(sharedReport.allowed, true);
  assert.equal(sharedReport.decision, "allowed_public_token_route");
  assert.equal(sharedReport.route.token_scoped, true);
  assert.equal(sharedReport.route.resource_access_check_required, true);
  assert.doesNotMatch(JSON.stringify(sharedReport), new RegExp(token));

  const hostedById = guardA3RouteAccess({ method: "GET", url: "/reports/report-123" });
  assert.equal(hostedById.allowed, false);
  assert.equal(hostedById.http_status, 401);
  assert.equal(hostedById.route.operation_id, "read_hosted_report");
});

test("A3 route matcher resolves exact and parameterized canonical RBAC patterns", () => {
  const revoke = matchA3RouteAccess("POST", "/api/a3/reports/report-123/revoke?role=owner");
  assert.equal(revoke.matched, true);
  assert.equal(revoke.operation_id, "revoke_report");
  assert.equal(revoke.path_pattern, "/api/a3/reports/:reportId/revoke");
  assert.equal(revoke.required_permission, "reports:revoke");

  const rotate = matchA3RouteAccess({ method: "POST", url: "/v1/api-keys/key-123/rotate" });
  assert.equal(rotate.matched, true);
  assert.equal(rotate.operation_id, "rotate_api_key");
  assert.equal(rotate.path_pattern, "/v1/api-keys/{api_key_id}/rotate");

  const reportCenter = matchA3RouteAccess("GET /api/a3/reports/center");
  assert.equal(reportCenter.operation_id, "read_report_center");
  assert.equal(matchA3RouteAccess("GET", "/api/a3/reports/report-123/revoke").matched, false);
  assert.equal(matchA3RouteAccess("POST", "/api/a3/reports/a%2Fb/revoke").matched, false);
});

test("hosted enforcement ignores client role, query, header, and request principal authority", () => {
  const decision = guardA3RouteAccess({
    method: "POST",
    url: "/api/a3/reports/share?role=owner",
    role: "owner",
    headers: {
      "x-a3-role": "owner",
      authorization: "Bearer forged-client-credential"
    },
    principal: trustedPrincipal(),
    requested_scope: SCOPE
  }, {
    mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    now: NOW
  });

  assert.equal(decision.allowed, false);
  assert.equal(decision.decision, "denied_missing_principal");
  assert.equal(decision.http_status, 401);
  assert.equal(decision.response.body.error, "authentication_required");
  assert.equal(decision.safety.client_role_used_as_authority, false);
  assert.equal(decision.safety.query_role_used_as_authority, false);
  assert.equal(decision.safety.header_role_used_as_authority, false);
});

test("hosted enforcement rejects expired, untrusted, and malformed principals with sanitized 401", () => {
  const expired = guardProtected({
    principal: trustedPrincipal({ expires_at: "2026-07-12T07:59:59.000Z" })
  });
  assert.equal(expired.allowed, false);
  assert.equal(expired.decision, "denied_expired_principal");
  assert.equal(expired.http_status, 401);

  const untrusted = guardProtected({
    principal: trustedPrincipal({ trusted: false })
  });
  assert.equal(untrusted.decision, "denied_untrusted_principal");
  assert.equal(untrusted.http_status, 401);

  const incompleteScope = { ...SCOPE };
  delete incompleteScope.environment_id;
  const malformed = guardProtected({
    principal: trustedPrincipal({ tenant_scope: incompleteScope })
  });
  assert.equal(malformed.decision, "denied_invalid_principal");
  assert.equal(malformed.http_status, 401);

  const unauthenticated = guardProtected({
    principal: trustedPrincipal({ authenticated: false })
  });
  assert.equal(unauthenticated.decision, "denied_unauthenticated_principal");

  const inactive = guardProtected({
    principal: trustedPrincipal({ session: { state: "revoked" } })
  });
  assert.equal(inactive.decision, "denied_untrusted_principal");

  const missingPermissions = trustedPrincipal();
  delete missingPermissions.permissions;
  const implicitPermissions = guardProtected({ principal: missingPermissions });
  assert.equal(implicitPermissions.decision, "denied_invalid_principal");

  const missingIdentity = trustedPrincipal();
  delete missingIdentity.actor_id;
  const anonymousPrincipal = guardProtected({ principal: missingIdentity });
  assert.equal(anonymousPrincipal.decision, "denied_invalid_principal");

  for (const decision of [expired, untrusted, malformed, unauthenticated, inactive, implicitPermissions, anonymousPrincipal]) {
    assert.deepEqual(decision.response.body, {
      schema_version: "a3.sanitized_unauthorized.v1",
      error: "authentication_required"
    });
  }
});

test("hosted enforcement returns 403 for role or effective-permission denial", () => {
  const viewer = guardProtected({
    principal: trustedPrincipal({ role: "viewer" })
  });
  assert.equal(viewer.allowed, false);
  assert.equal(viewer.decision, "denied_missing_permission");
  assert.equal(viewer.http_status, 403);
  assert.equal(viewer.route.required_permission, "reports:share");
  assert.deepEqual(viewer.response.body, {
    schema_version: "a3.sanitized_forbidden.v1",
    error: "access_denied"
  });

  const narrowedOwner = guardProtected({
    principal: trustedPrincipal({ permissions: ["project:read"] })
  });
  assert.equal(narrowedOwner.decision, "denied_missing_permission");
  assert.equal(narrowedOwner.http_status, 403);
});

test("hosted enforcement requires an explicit matching five-level requested scope", () => {
  const mismatch = guardProtected({
    requestedScope: {
      ...SCOPE,
      project_id: "project-other"
    }
  });
  assert.equal(mismatch.allowed, false);
  assert.equal(mismatch.decision, "denied_scope_mismatch");
  assert.equal(mismatch.http_status, 403);
  assert.equal(mismatch.scope_validation.matches, false);

  const incompleteScope = { ...SCOPE };
  delete incompleteScope.workspace_id;
  const missing = guardProtected({ requestedScope: incompleteScope });
  assert.equal(missing.decision, "denied_invalid_requested_scope");
  assert.equal(missing.http_status, 403);
  assert.equal(missing.scope_validation.requested, "invalid");

  const explicitValidation = validateA3RouteScope(incompleteScope);
  assert.equal(explicitValidation.valid, false);
  assert.deepEqual(explicitValidation.missing_fields, ["workspace_id"]);
});

test("trusted hosted principal with matching scope and permission is allowed", () => {
  const decision = guardProtected();
  assert.equal(decision.allowed, true);
  assert.equal(decision.decision, "allowed_trusted_principal");
  assert.equal(decision.http_status, 200);
  assert.equal(decision.production_enforced, true);
  assert.equal(decision.principal.trusted, true);
  assert.equal(decision.principal.role, "owner");
  assert.equal(decision.scope_validation.matches, true);
  assert.equal(decision.response, null);
  assert.equal(decision.audit_evidence.redaction_status, "metadata_only");
  assert.equal(decision.audit_evidence.payload_inline, false);
  assert.equal(decision.audit_event.schema_version, "ashr.event_envelope.v1");
  assert.equal(decision.audit_event.organization_id, SCOPE.organization_id);
  assert.equal(decision.audit_event.environment_id, SCOPE.environment_id);
  assert.equal(decision.audit_event.payload_inline, false);
  assert.equal(decision.audit_event.safety.raw_secret_values_allowed, false);

  const principalValidation = validateTrustedA3Principal(trustedPrincipal(), { now: NOW });
  assert.equal(principalValidation.valid, true);
  assert.deepEqual(principalValidation.tenant_scope.organization_id, SCOPE.organization_id);
});

test("demo contract mode simulates RBAC without claiming hosted enforcement", () => {
  const contractPrincipal = {
    role: "reviewer",
    actor_id: "demo-reviewer",
    tenant_scope: SCOPE
  };
  const demo = guardA3RouteAccess({
    method: "POST",
    url: "/api/a3/reports/share",
    requested_scope: SCOPE
  }, {
    mode: A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT,
    contractPrincipal,
    now: NOW
  });
  assert.equal(demo.allowed, true);
  assert.equal(demo.decision, "allowed_demo_contract");
  assert.equal(demo.production_enforced, false);
  assert.equal(demo.principal.trusted, false);

  const hosted = guardA3RouteAccess({
    method: "POST",
    url: "/api/a3/reports/share",
    requested_scope: SCOPE
  }, {
    mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    contractPrincipal,
    now: NOW
  });
  assert.equal(hosted.allowed, false);
  assert.equal(hosted.decision, "denied_missing_principal");
});

test("route decisions and metadata-only audit evidence never expose credentials or raw identity", () => {
  const token = "secret-token-7c16d9";
  const cookie = "session-cookie-21f9a8";
  const email = "route-owner@example.com";
  const requestId = `Bearer ${token}`;
  const principal = trustedPrincipal({
    actor_id: email,
    authorization: `Bearer ${token}`,
    cookie,
    api_key: "sk-live-private-value"
  });
  const decision = guardA3RouteAccess({
    method: "POST",
    url: `/api/a3/reports/share?role=owner&token=${token}`,
    headers: {
      authorization: `Bearer ${token}`,
      cookie
    },
    body: {
      requested_scope: SCOPE,
      authorization: `Bearer ${token}`
    }
  }, {
    mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    trustedPrincipal: principal,
    requestedScope: SCOPE,
    requestId,
    now: NOW
  });

  assert.equal(decision.allowed, true);
  assert.match(decision.principal.principal_fingerprint, /^[a-f0-9]{64}$/);
  assert.match(decision.audit_evidence.request_fingerprint, /^[a-f0-9]{64}$/);
  assert.equal(decision.audit_evidence.safety.raw_identity_included, false);
  assert.equal(decision.audit_evidence.safety.raw_credentials_included, false);

  const serialized = JSON.stringify(decision);
  for (const secret of [token, cookie, email, requestId, "sk-live-private-value"]) {
    assert.equal(serialized.includes(secret), false, `${secret} must not appear in the decision`);
  }
  assert.doesNotMatch(serialized, /Bearer\s+[A-Za-z0-9._-]+|Cookie:/i);
});

test("route registry has canonical RBAC mappings and broad sensitive coverage", () => {
  const validation = validateA3RouteAccessRegistry();
  assert.equal(validation.valid, true, validation.errors.join("; "));
  assert.equal(validation.sensitive_route_count >= 20, true);
  assert.equal(validation.sensitive_route_count, A3_SENSITIVE_ROUTE_PATTERNS.length);

  const canonicalOperations = new Set(A3_AUTHZ_OPERATION_POLICIES.map((policy) => policy.operation));
  assert.equal(A3_SENSITIVE_ROUTE_PATTERNS.every((route) => canonicalOperations.has(route.operation_id)), true);
  assert.equal(A3_SENSITIVE_ROUTE_PATTERNS.every((route) => route.required_permission), true);
  assert.equal(new Set(A3_SENSITIVE_ROUTE_PATTERNS.map((route) => (
    `${route.method} ${route.path_pattern}`
  ))).size, A3_SENSITIVE_ROUTE_PATTERNS.length);

  for (const operation of [
    "read_run",
    "read_case",
    "read_report",
    "read_report_manifest",
    "read_release_decision_provenance",
    "read_release_evidence_summary",
    "read_hosted_report"
  ]) {
    assert.equal(canonicalOperations.has(operation), true, `${operation} must remain canonical`);
  }

  const policy = buildA3RbacPolicy();
  assert.equal(policy.operation_count, A3_SENSITIVE_ROUTE_PATTERNS.length);
  assert.deepEqual(policy.tenant_scope_required, A3_REQUIRED_SCOPE_FIELDS);

  const contract = buildA3RouteAccessContract();
  assert.equal(contract.default_mode, "hosted_enforced");
  assert.equal(contract.authority.identity_and_session.owner, "A1");
  assert.equal(contract.authority.release_decisions.owner, "A2");
  assert.equal(contract.safety.unknown_routes_fail_closed, true);
});

function guardProtected(options = {}) {
  return guardA3RouteAccess({
    method: "POST",
    url: "/api/a3/reports/share",
    requested_scope: options.requestedScope || SCOPE
  }, {
    mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    trustedPrincipal: options.principal || trustedPrincipal(),
    now: NOW
  });
}

function trustedPrincipal(overrides = {}) {
  const role = overrides.role || "owner";
  return {
    trusted: true,
    authenticated: true,
    role,
    actor_id: "actor-route-owner",
    session: { state: "active" },
    permissions: [...A3_RBAC_ROLES[role]],
    expires_at: FUTURE,
    tenant_scope: SCOPE,
    ...overrides
  };
}
