import { createHash } from "node:crypto";

import {
  A3_AUTHZ_OPERATION_POLICIES,
  A3_RBAC_ROLES,
  authorizeA3Operation,
  buildA3AuthContext
} from "./a3_auth_rbac_boundary.mjs";
import {
  tenantScopeMatches,
  validateA3TenantScope
} from "./a3_tenant_scope.mjs";

export const A3_ROUTE_ACCESS_DECISION_SCHEMA_VERSION = "a3.route_access_decision.v1";
export const A3_ROUTE_ACCESS_CONTRACT_SCHEMA_VERSION = "a3.route_access_contract.v1";
export const A3_ROUTE_ACCESS_AUDIT_SCHEMA_VERSION = "a3.route_access_audit.v1";

export const A3_ROUTE_ACCESS_MODES = Object.freeze({
  DEMO_CONTRACT: "demo_contract",
  HOSTED_ENFORCED: "hosted_enforced"
});

const A3_REQUEST_BOUNDARY_DENIALS = Object.freeze({
  malformed_json: Object.freeze({
    decision: "denied_malformed_json",
    httpStatus: 400,
    error: "invalid_json"
  }),
  body_read_timeout: Object.freeze({
    decision: "denied_body_read_timeout",
    httpStatus: 408,
    error: "request_timeout"
  }),
  payload_too_large: Object.freeze({
    decision: "denied_payload_too_large",
    httpStatus: 413,
    error: "payload_too_large"
  }),
  unsupported_media_type: Object.freeze({
    decision: "denied_unsupported_media_type",
    httpStatus: 415,
    error: "unsupported_media_type"
  }),
  invalid_json_shape: Object.freeze({
    decision: "denied_invalid_json_shape",
    httpStatus: 422,
    error: "invalid_json_shape"
  })
});

export const A3_REQUIRED_SCOPE_FIELDS = Object.freeze([
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
]);

export const A3_ROUTE_ACCESS_AUTHORITY = deepFreeze({
  identity_and_session: {
    owner: "A1",
    contract: "A1 middleware supplies the authenticated, trusted, time-bounded principal."
  },
  route_authorization: {
    owner: "A3",
    contract: "A3 maps routes to canonical RBAC operation ids and enforces tenant scope equality."
  },
  release_decisions: {
    owner: "A2",
    contract: "A3 may read A2 decisions and evidence but never recomputes release decisions."
  }
});

export const A3_PUBLIC_ROUTE_PATTERNS = Object.freeze([
  publicRoute("a3_health", "GET", "/api/a3/health", "health_probe"),
  publicRoute("shared_report_by_token", "GET", "/r/{share_token}", "report_share_token", {
    tokenScoped: true,
    resourceAccessCheckRequired: true
  })
]);

export const A3_SENSITIVE_ROUTE_PATTERNS = Object.freeze(
  A3_AUTHZ_OPERATION_POLICIES.map((policy) => Object.freeze(sensitiveRoute(policy)))
);

// Short aliases make the registry convenient for middleware and contract tooling.
export const A3_PUBLIC_ROUTES = A3_PUBLIC_ROUTE_PATTERNS;
export const A3_PROTECTED_ROUTES = A3_SENSITIVE_ROUTE_PATTERNS;

const COMPILED_PUBLIC_ROUTES = compileRegistry(A3_PUBLIC_ROUTE_PATTERNS);
const COMPILED_SENSITIVE_ROUTES = compileRegistry(A3_SENSITIVE_ROUTE_PATTERNS);

export function buildA3RouteAccessContract() {
  return {
    schema_version: A3_ROUTE_ACCESS_CONTRACT_SCHEMA_VERSION,
    default_mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    modes: [
      {
        mode: A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT,
        production_enforced: false,
        principal_source: "server_supplied_contract_principal"
      },
      {
        mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
        production_enforced: true,
        principal_source: "server_supplied_trusted_principal_only"
      }
    ],
    public_routes: A3_PUBLIC_ROUTE_PATTERNS,
    sensitive_routes: A3_SENSITIVE_ROUTE_PATTERNS,
    required_scope: A3_REQUIRED_SCOPE_FIELDS,
    authority: A3_ROUTE_ACCESS_AUTHORITY,
    safety: {
      client_role_is_authority: false,
      query_role_is_authority: false,
      header_role_is_authority: false,
      raw_identity_in_decisions: false,
      raw_credentials_in_decisions: false,
      unknown_routes_fail_closed: true
    }
  };
}

export function validateA3RouteAccessRegistry() {
  const errors = [];
  const canonicalPolicies = new Map(A3_AUTHZ_OPERATION_POLICIES.map((policy) => [policy.operation, policy]));
  const routeKeys = new Set();

  for (const route of A3_PUBLIC_ROUTE_PATTERNS) {
    validateRegistryRoute(route, routeKeys, errors);
    if (route.path_pattern.startsWith("/reports/")) {
      errors.push(`${route.route_id} exposes a non-token report route publicly`);
    }
  }

  for (const route of A3_SENSITIVE_ROUTE_PATTERNS) {
    validateRegistryRoute(route, routeKeys, errors);
    const policy = canonicalPolicies.get(route.operation_id);
    if (!policy) {
      errors.push(`${route.route_id} references an unknown RBAC operation`);
      continue;
    }
    if (policy.required_permission !== route.required_permission) {
      errors.push(`${route.route_id} permission differs from the canonical RBAC policy`);
    }
    if (policy.route !== `${route.method} ${route.path_pattern}`) {
      errors.push(`${route.route_id} route differs from the canonical RBAC policy`);
    }
  }

  if (A3_SENSITIVE_ROUTE_PATTERNS.length < 20) {
    errors.push("sensitive route coverage must include at least 20 patterns");
  }

  return {
    valid: errors.length === 0,
    errors,
    public_route_count: A3_PUBLIC_ROUTE_PATTERNS.length,
    sensitive_route_count: A3_SENSITIVE_ROUTE_PATTERNS.length,
    canonical_operation_count: canonicalPolicies.size
  };
}

export function matchA3RouteAccess(methodOrRequest = {}, pathInput) {
  const normalized = normalizeRouteInput(methodOrRequest, pathInput);
  if (!normalized.valid) {
    return unmatchedRoute(normalized.method);
  }

  const publicMatch = findCompiledRoute(COMPILED_PUBLIC_ROUTES, normalized);
  if (publicMatch) {
    return matchedRoute(publicMatch);
  }

  const sensitiveMatch = findCompiledRoute(COMPILED_SENSITIVE_ROUTES, normalized);
  if (sensitiveMatch) {
    return matchedRoute(sensitiveMatch);
  }

  return unmatchedRoute(normalized.method);
}

export const matchA3Route = matchA3RouteAccess;

export function validateA3RouteScope(scopeInput = {}) {
  const explicitScope = extractExplicitScope(scopeInput);
  const missingFields = A3_REQUIRED_SCOPE_FIELDS.filter((field) => explicitScope[field] === undefined);
  const invalidTypeFields = A3_REQUIRED_SCOPE_FIELDS.filter((field) => (
    explicitScope[field] !== undefined
    && typeof explicitScope[field] !== "string"
  ));
  const emptyFields = A3_REQUIRED_SCOPE_FIELDS.filter((field) => (
    typeof explicitScope[field] === "string" && explicitScope[field].length === 0
  ));

  if (missingFields.length || invalidTypeFields.length || emptyFields.length) {
    return {
      valid: false,
      errors: [
        ...missingFields.map((field) => `${field} is required`),
        ...invalidTypeFields.map((field) => `${field} must be a string`),
        ...emptyFields.map((field) => `${field} is required`)
      ],
      missing_fields: missingFields,
      invalid_fields: [...new Set([...invalidTypeFields, ...emptyFields])],
      scope: null
    };
  }

  const validation = validateA3TenantScope(explicitScope);
  return {
    valid: validation.valid,
    errors: validation.errors,
    missing_fields: [],
    invalid_fields: validation.valid
      ? []
      : A3_REQUIRED_SCOPE_FIELDS.filter((field) => validation.errors.some((error) => error.startsWith(field))),
    scope: validation.valid ? validation.scope : null
  };
}

export function validateTrustedA3Principal(principal, options = {}) {
  return validatePrincipal(principal, {
    mode: A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    now: options.now
  });
}

export const validateA3TrustedPrincipal = validateTrustedA3Principal;

export function guardA3RouteAccess(request = {}, options = {}) {
  const mode = normalizeMode(options.mode ?? options.enforcementMode);
  const route = matchA3RouteAccess(request);
  const now = normalizedNow(options.now);

  if (!mode) {
    return routeDecision({
      route,
      mode: "invalid",
      allowed: false,
      decision: "denied_invalid_enforcement_mode",
      httpStatus: 403,
      now,
      scopeState: emptyScopeState()
    }, options);
  }

  if (!route.matched) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: "denied_unregistered_route",
      httpStatus: 403,
      now,
      scopeState: emptyScopeState()
    }, options);
  }

  if (route.access === "public") {
    return routeDecision({
      route,
      mode,
      allowed: true,
      decision: route.token_scoped ? "allowed_public_token_route" : "allowed_public_route",
      httpStatus: 200,
      now,
      scopeState: emptyScopeState()
    }, options);
  }

  const principalInput = serverSuppliedPrincipal(options, mode);
  const principal = validatePrincipal(principalInput, { mode, now });
  if (!principal.valid) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: principal.decision,
      httpStatus: 401,
      now,
      principal,
      scopeState: {
        ...emptyScopeState(),
        principal: principal.scope_state || "not_validated"
      }
    }, options);
  }

  const requestedScope = validateA3RouteScope(requestedScopeInput(request, options));
  if (!requestedScope.valid) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: "denied_invalid_requested_scope",
      httpStatus: 403,
      now,
      principal,
      scopeState: {
        principal: "valid",
        requested: "invalid",
        matches: false
      }
    }, options);
  }

  if (!tenantScopeMatches(principal.tenant_scope, requestedScope.scope)) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: "denied_scope_mismatch",
      httpStatus: 403,
      now,
      principal,
      requestedScope: requestedScope.scope,
      scopeState: {
        principal: "valid",
        requested: "valid",
        matches: false
      }
    }, options);
  }

  const authContext = buildA3AuthContext({
    role: principal.role,
    actor_hash: principal.principal_fingerprint,
    tenant_scope: principal.tenant_scope,
    hosted_session: mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    credential_source: mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED
      ? "a1_trusted_principal"
      : "server_demo_contract"
  });
  authContext.permissions = [...principal.permissions];

  const authorization = authorizeA3Operation(route.operation_id, authContext);
  if (!authorization.allowed) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: authorization.decision === "blocked_requires_hosted_auth"
        ? "denied_requires_hosted_enforcement"
        : authorization.decision,
      httpStatus: 403,
      now,
      principal,
      requestedScope: requestedScope.scope,
      scopeState: {
        principal: "valid",
        requested: "valid",
        matches: true
      }
    }, options);
  }

  const requestBoundaryDenial = A3_REQUEST_BOUNDARY_DENIALS[options.requestBodyState];
  if (requestBoundaryDenial) {
    return routeDecision({
      route,
      mode,
      allowed: false,
      decision: requestBoundaryDenial.decision,
      httpStatus: requestBoundaryDenial.httpStatus,
      now,
      principal,
      requestedScope: requestedScope.scope,
      scopeState: {
        principal: "valid",
        requested: "valid",
        matches: true
      }
    }, options);
  }

  return routeDecision({
    route,
    mode,
    allowed: true,
    decision: mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED
      ? "allowed_trusted_principal"
      : "allowed_demo_contract",
    httpStatus: 200,
    now,
    principal,
    requestedScope: requestedScope.scope,
    scopeState: {
      principal: "valid",
      requested: "valid",
      matches: true
    }
  }, options);
}

export const guardA3RouteRequest = guardA3RouteAccess;
export const evaluateA3RouteAccess = guardA3RouteAccess;

export function createA3RouteAccessGuard(defaultOptions = {}) {
  return function configuredA3RouteAccessGuard(request, requestOptions = {}) {
    return guardA3RouteAccess(request, {
      ...defaultOptions,
      ...requestOptions
    });
  };
}

function publicRoute(routeId, method, pathPattern, mechanism, options = {}) {
  return Object.freeze({
    route_id: routeId,
    method,
    path_pattern: pathPattern,
    access: "public",
    public_mechanism: mechanism,
    token_scoped: options.tokenScoped === true,
    resource_access_check_required: options.resourceAccessCheckRequired === true,
    operation_id: null,
    required_permission: null,
    operation_mode: "public"
  });
}

function sensitiveRoute(policy) {
  const [method, ...pathParts] = String(policy.route).split(" ");
  return {
    route_id: policy.operation,
    method: method.toUpperCase(),
    path_pattern: pathParts.join(" "),
    access: "sensitive",
    public_mechanism: null,
    token_scoped: false,
    resource_access_check_required: true,
    operation_id: policy.operation,
    required_permission: policy.required_permission,
    operation_mode: policy.mode
  };
}

function compileRegistry(routes) {
  return [...routes]
    .sort((left, right) => placeholderCount(left.path_pattern) - placeholderCount(right.path_pattern))
    .map((route) => ({
      route,
      expression: routeExpression(route.path_pattern)
    }));
}

function findCompiledRoute(compiledRoutes, request) {
  return compiledRoutes.find(({ route, expression }) => (
    route.method === request.method && expression.test(request.pathname)
  ))?.route;
}

function routeExpression(pathPattern) {
  const segments = pathPattern.split("/").map((segment) => {
    if (/^:[A-Za-z][A-Za-z0-9_]*$/.test(segment) || /^\{[A-Za-z][A-Za-z0-9_]*\}$/.test(segment)) {
      return "[^/]+";
    }
    return escapeRegExp(segment);
  });
  return new RegExp(`^${segments.join("/")}$`);
}

function placeholderCount(pathPattern) {
  return pathPattern.split("/").filter((segment) => (
    /^:[A-Za-z][A-Za-z0-9_]*$/.test(segment) || /^\{[A-Za-z][A-Za-z0-9_]*\}$/.test(segment)
  )).length;
}

function normalizeRouteInput(methodOrRequest, pathInput) {
  let method;
  let rawPath;

  if (typeof methodOrRequest === "string" && pathInput !== undefined) {
    method = methodOrRequest;
    rawPath = pathInput;
  } else if (typeof methodOrRequest === "string") {
    const routeParts = methodOrRequest.match(/^([A-Za-z]+)\s+(\/.*)$/);
    method = routeParts?.[1] || "GET";
    rawPath = routeParts?.[2] || methodOrRequest;
  } else {
    method = methodOrRequest?.method || "GET";
    rawPath = methodOrRequest?.pathname ?? methodOrRequest?.path ?? methodOrRequest?.url;
  }

  const normalizedMethod = String(method || "").trim().toUpperCase();
  const pathname = normalizePathname(rawPath);
  return {
    valid: /^[A-Z]+$/.test(normalizedMethod) && pathname !== null,
    method: /^[A-Z]+$/.test(normalizedMethod) ? normalizedMethod : "INVALID",
    pathname
  };
}

function normalizePathname(rawPath) {
  if (typeof rawPath !== "string" || !rawPath || /[\0\r\n\\]/.test(rawPath)) {
    return null;
  }
  if (/%(?:2f|5c)/i.test(rawPath)) {
    return null;
  }
  try {
    const absolute = /^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(rawPath);
    if (!absolute && (!rawPath.startsWith("/") || rawPath.startsWith("//"))) {
      return null;
    }
    return new URL(rawPath, "http://a3.invalid").pathname;
  } catch {
    return null;
  }
}

function matchedRoute(route) {
  return {
    matched: true,
    access: route.access,
    method: route.method,
    path_pattern: route.path_pattern,
    route_id: route.route_id,
    operation_id: route.operation_id,
    required_permission: route.required_permission,
    operation_mode: route.operation_mode,
    public_mechanism: route.public_mechanism,
    token_scoped: route.token_scoped,
    resource_access_check_required: route.resource_access_check_required
  };
}

function unmatchedRoute(method) {
  return {
    matched: false,
    access: "unregistered",
    method: method || "INVALID",
    path_pattern: null,
    route_id: null,
    operation_id: null,
    required_permission: null,
    operation_mode: null,
    public_mechanism: null,
    token_scoped: false,
    resource_access_check_required: true
  };
}

function validateRegistryRoute(route, routeKeys, errors) {
  const routeKey = `${route.method} ${route.path_pattern}`;
  if (!route.method || !route.path_pattern || !route.path_pattern.startsWith("/")) {
    errors.push(`${route.route_id || "unknown"} has an invalid method/path pattern`);
  }
  if (routeKeys.has(routeKey)) {
    errors.push(`${routeKey} is registered more than once`);
  }
  routeKeys.add(routeKey);
}

function extractExplicitScope(input = {}) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return {};
  }
  const nested = firstObject(input.tenant_scope, input.tenantScope, input.scope, input);
  return Object.fromEntries(A3_REQUIRED_SCOPE_FIELDS.flatMap((field) => {
    const camel = snakeToCamel(field);
    const value = firstDefined(ownValue(nested, field), ownValue(nested, camel), ownValue(input, field), ownValue(input, camel));
    return value === undefined ? [] : [[field, value]];
  }));
}

function requestedScopeInput(request, options) {
  const explicit = firstDefined(
    options.requestedScope,
    options.requested_scope,
    request?.requested_scope,
    request?.requestedScope,
    request?.tenant_scope,
    request?.tenantScope,
    request?.scope,
    request?.body?.requested_scope,
    request?.body?.requestedScope,
    request?.body?.tenant_scope,
    request?.body?.tenantScope,
    request?.body?.scope
  );
  if (explicit !== undefined) {
    return explicit;
  }
  if (hasExplicitScopeField(request?.body)) {
    return request.body;
  }

  const rawUrl = request?.url ?? request?.path ?? request?.pathname;
  if (typeof rawUrl !== "string") {
    return {};
  }
  try {
    const url = new URL(rawUrl, "http://a3.invalid");
    const queryScope = {};
    for (const field of A3_REQUIRED_SCOPE_FIELDS) {
      const camel = snakeToCamel(field);
      if (url.searchParams.has(field)) {
        queryScope[field] = url.searchParams.get(field);
      } else if (url.searchParams.has(camel)) {
        queryScope[field] = url.searchParams.get(camel);
      }
    }
    return queryScope;
  } catch {
    return {};
  }
}

function serverSuppliedPrincipal(options, mode) {
  if (mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED) {
    return firstDefined(options.trustedPrincipal, options.trusted_principal, options.principal);
  }
  return firstDefined(
    options.contractPrincipal,
    options.contract_principal,
    options.demoPrincipal,
    options.demo_principal,
    options.principal,
    options.trustedPrincipal,
    options.trusted_principal
  );
}

function validatePrincipal(principal, options) {
  const hosted = options.mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED;
  if (!principal || typeof principal !== "object" || Array.isArray(principal)) {
    return invalidPrincipal("denied_missing_principal");
  }

  const role = typeof principal.role === "string" ? principal.role.trim().toLowerCase() : "";
  if (!Object.hasOwn(A3_RBAC_ROLES, role)) {
    return invalidPrincipal("denied_invalid_principal");
  }
  const principalType = canonicalPrincipalType(principal, role);
  const sessionState = String(
    principal.session?.state
    || principal.session?.status
    || principal.session_state
    || principal.session_status
    || (principalType === "service_account" ? principal.service_account?.state : "")
    || (principalType === "service_account" ? principal.service_account?.status : "")
    || (principalType === "service_account" ? principal.service_account_state : "")
    || (principalType === "service_account" ? principal.service_account_status : "")
    || ""
  ).toLowerCase();
  if (hosted && principal.trusted !== true) {
    return invalidPrincipal("denied_untrusted_principal");
  }
  if (hosted && principal.authenticated !== true) {
    return invalidPrincipal("denied_unauthenticated_principal");
  }
  const activeStates = principalType === "service_account"
    ? ["active", "enabled"]
    : ["active", "authenticated"];
  if (hosted && !activeStates.includes(sessionState)) {
    return invalidPrincipal(sessionState === "expired" ? "denied_expired_principal" : "denied_untrusted_principal");
  }
  if (["expired", "revoked", "disabled", "invalid"].includes(sessionState)) {
    return invalidPrincipal(sessionState === "expired" ? "denied_expired_principal" : "denied_untrusted_principal");
  }

  const expiresAtInput = firstDefined(
    principal.expires_at,
    principal.expiresAt,
    principal.session_expires_at,
    principal.sessionExpiresAt,
    principal.session?.expires_at,
    principal.session?.expiresAt,
    principal.exp
  );
  const expiresAt = parseTimestamp(expiresAtInput);
  if (hosted && expiresAt === null) {
    return invalidPrincipal("denied_invalid_principal");
  }
  const now = parseTimestamp(options.now) ?? Date.now();
  if (expiresAt !== null && expiresAt <= now) {
    return invalidPrincipal("denied_expired_principal");
  }

  const scopeValidation = validateA3RouteScope(
    firstDefined(principal.tenant_scope, principal.tenantScope, principal.scope, principal)
  );
  if (!scopeValidation.valid) {
    return {
      ...invalidPrincipal("denied_invalid_principal"),
      scope_state: "invalid"
    };
  }

  if (hosted && !Array.isArray(principal.permissions)) {
    return invalidPrincipal("denied_invalid_principal");
  }
  if (principal.permissions !== undefined && !Array.isArray(principal.permissions)) {
    return invalidPrincipal("denied_invalid_principal");
  }
  const rolePermissions = A3_RBAC_ROLES[role];
  const permissions = principal.permissions === undefined
    ? [...rolePermissions]
    : rolePermissions.filter((permission) => principal.permissions.includes(permission));
  const identityReference = firstDefined(
    principal.actor_hash,
    principal.actorHash,
    principal.subject_hash,
    principal.subjectHash,
    principal.subject_id,
    principal.subjectId,
    principal.actor_id,
    principal.actorId,
    principal.id
  );
  if (hosted && (identityReference === undefined || String(identityReference).trim() === "")) {
    return invalidPrincipal("denied_invalid_principal");
  }

  return {
    valid: true,
    decision: null,
    role,
    permissions,
    tenant_scope: scopeValidation.scope,
    scope_state: "valid",
    principal_type: principalType,
    principal_fingerprint: digest(`a3-principal:${String(identityReference || `${role}:${scopeFingerprint(scopeValidation.scope)}`)}`),
    expires_at: expiresAt === null ? null : new Date(expiresAt).toISOString(),
    trusted: hosted,
    raw_identity_exposed: false
  };
}

function invalidPrincipal(decision) {
  return {
    valid: false,
    decision,
    role: null,
    permissions: [],
    tenant_scope: null,
    scope_state: "not_validated",
    principal_type: null,
    principal_fingerprint: null,
    expires_at: null,
    trusted: false,
    raw_identity_exposed: false
  };
}

function canonicalPrincipalType(principal, role) {
  if (role === "service_account" || principal.service_account === true) {
    return "service_account";
  }
  return principal.principal_type === "workload" ? "workload" : "user";
}

function routeDecision(input, options) {
  const denied = !input.allowed;
  const sanitizedError = sanitizedRouteError(input.httpStatus, input.decision);
  const requestTransport = buildRequestTransport(input.route, options);
  const scopeFingerprintValue = input.requestedScope
    ? scopeFingerprint(input.requestedScope)
    : null;
  const auditEvidence = buildAuditEvidence({
    ...input,
    requestTransport,
    requestId: firstDefined(options.requestId, options.request_id),
    scopeFingerprint: scopeFingerprintValue
  });
  const accessAuditEvent = buildAccessAuditEvent({
    ...input,
    requestTransport,
    requestFingerprint: auditEvidence.request_fingerprint,
    traceId: firstDefined(options.traceId, options.trace_id),
    scopeFingerprint: scopeFingerprintValue
  });

  return {
    schema_version: A3_ROUTE_ACCESS_DECISION_SCHEMA_VERSION,
    allowed: input.allowed,
    decision: input.decision,
    http_status: input.httpStatus,
    status_code: input.httpStatus,
    enforcement_mode: input.mode,
    production_enforced: input.mode === A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED,
    operation: input.route.operation_id,
    required_permission: input.route.required_permission,
    role: input.principal?.role || null,
    route: {
      matched: input.route.matched,
      access: input.route.access,
      method: input.route.method,
      path_pattern: input.route.path_pattern,
      operation_id: input.route.operation_id,
      required_permission: input.route.required_permission,
      operation_mode: input.route.operation_mode,
      public_mechanism: input.route.public_mechanism,
      token_scoped: input.route.token_scoped,
      resource_access_check_required: input.route.resource_access_check_required
    },
    request_transport: requestTransport,
    principal: input.principal?.valid
      ? {
          trusted: input.principal.trusted,
          role: input.principal.role,
          principal_type: input.principal.principal_type,
          principal_fingerprint: input.principal.principal_fingerprint,
          raw_identity_exposed: false
        }
      : null,
    scope_validation: {
      required_fields: A3_REQUIRED_SCOPE_FIELDS,
      principal: input.scopeState.principal,
      requested: input.scopeState.requested,
      matches: input.scopeState.matches,
      scope_fingerprint: scopeFingerprintValue
    },
    response: denied
      ? {
          status: input.httpStatus,
          body: sanitizedError
        }
      : null,
    denied_state: denied
      ? {
          http_status: input.httpStatus,
          body_policy: "sanitized_error_without_private_evidence",
          customer_message: sanitizedCustomerMessage(input.httpStatus)
        }
      : null,
    audit_evidence: auditEvidence,
    audit_event: accessAuditEvent,
    access_audit_event: accessAuditEvent,
    authority: A3_ROUTE_ACCESS_AUTHORITY,
    safety: {
      client_role_used_as_authority: false,
      query_role_used_as_authority: false,
      header_role_used_as_authority: false,
      raw_identity_exposed: false,
      raw_token_exposed: false,
      raw_cookie_exposed: false,
      raw_api_key_exposed: false,
      raw_origin_exposed: false,
      raw_path_parameters_exposed: false,
      a2_release_decision_recomputed: false
    }
  };
}

function buildAuditEvidence(input) {
  const eventSeed = JSON.stringify({
    decision: input.decision,
    mode: input.mode,
    method: input.route.method,
    path_pattern: input.route.path_pattern,
    operation_id: input.route.operation_id,
    principal_fingerprint: input.principal?.principal_fingerprint || null,
    scope_fingerprint: input.scopeFingerprint,
    transport_method: input.requestTransport.transport_method,
    preflight_for_method: input.requestTransport.preflight_for_method,
    request_body_state: input.requestTransport.request_body_state,
    occurred_at: input.now
  });
  return {
    schema_version: A3_ROUTE_ACCESS_AUDIT_SCHEMA_VERSION,
    event_id: `rae_${digest(eventSeed).slice(0, 24)}`,
    event_type: input.allowed ? "route_access.allowed" : "route_access.denied",
    occurred_at: input.now,
    enforcement_mode: input.mode,
    decision: input.decision,
    http_status: input.httpStatus,
    route_method: input.route.method,
    route_pattern: input.route.path_pattern,
    operation_id: input.route.operation_id,
    required_permission: input.route.required_permission,
    transport_method: input.requestTransport.transport_method,
    preflight_for_method: input.requestTransport.preflight_for_method,
    request_body_state: input.requestTransport.request_body_state,
    principal_role: input.principal?.role || null,
    principal_type: input.principal?.principal_type || null,
    principal_fingerprint: input.principal?.principal_fingerprint || null,
    scope_fingerprint: input.scopeFingerprint,
    request_fingerprint: input.requestId === undefined
      ? null
      : digest(`a3-request:${String(input.requestId)}`),
    redaction_status: "metadata_only",
    payload_inline: false,
    safety: {
      raw_request_path_included: false,
      raw_path_parameters_included: false,
      raw_identity_included: false,
      raw_credentials_included: false,
      raw_cookies_included: false,
      raw_origin_included: false
    }
  };
}

function buildAccessAuditEvent(input) {
  const tenantScope = input.principal?.tenant_scope
    || input.requestedScope
    || auditSentinelScope(input.route.access);
  const actorId = input.principal?.principal_fingerprint
    ? `actor_${input.principal.principal_fingerprint.slice(0, 24)}`
    : input.route.access === "public"
      ? "actor_public"
      : "actor_unavailable";
  const requestId = input.requestFingerprint
    ? `req_${input.requestFingerprint.slice(0, 24)}`
    : "req_unavailable";
  const traceFingerprint = input.traceId === undefined
    ? null
    : digest(`a3-trace:${String(input.traceId)}`);
  const traceId = traceFingerprint ? `trace_${traceFingerprint.slice(0, 24)}` : "trace_unavailable";
  const payloadHash = digest(JSON.stringify({
    schema_version: A3_ROUTE_ACCESS_DECISION_SCHEMA_VERSION,
    decision: input.decision,
    allowed: input.allowed,
    http_status: input.httpStatus,
    enforcement_mode: input.mode,
    operation: input.route.operation_id,
    required_permission: input.route.required_permission,
    principal_role: input.principal?.role || null,
    scope_fingerprint: input.scopeFingerprint,
    transport_method: input.requestTransport.transport_method,
    preflight_for_method: input.requestTransport.preflight_for_method,
    request_body_state: input.requestTransport.request_body_state
  }));
  const eventId = digest(JSON.stringify({
    event_type: input.allowed ? "route_access.allowed" : "route_access.denied",
    operation: input.route.operation_id,
    decision: input.decision,
    transport_method: input.requestTransport.transport_method,
    preflight_for_method: input.requestTransport.preflight_for_method,
    request_body_state: input.requestTransport.request_body_state,
    actor_id: actorId,
    request_id: requestId,
    created_at: input.now,
    payload_hash: payloadHash
  }));

  return {
    schema_version: "ashr.event_envelope.v1",
    event_id: `evt_${eventId.slice(0, 24)}`,
    event_type: input.allowed ? "route_access.allowed" : "route_access.denied",
    decision: input.decision,
    http_status: input.httpStatus,
    operation_id: input.route.operation_id,
    required_permission: input.route.required_permission,
    organization_id: tenantScope.organization_id,
    tenant_id: tenantScope.tenant_id,
    workspace_id: tenantScope.workspace_id,
    project_id: tenantScope.project_id,
    environment_id: tenantScope.environment_id,
    actor_id: actorId,
    request_id: requestId,
    trace_id: traceId,
    resource_type: "route_access_decision",
    resource_id: input.route.operation_id || input.route.route_id || "unregistered_route",
    created_at: input.now,
    payload_ref: null,
    payload_hash: payloadHash,
    payload_schema_version: A3_ROUTE_ACCESS_DECISION_SCHEMA_VERSION,
    payload_inline: false,
    redaction_status: "metadata_only",
    audit_visibility: "metadata_only",
    transport_method: input.requestTransport.transport_method,
    preflight_for_method: input.requestTransport.preflight_for_method,
    request_body_state: input.requestTransport.request_body_state,
    usage_meter: "api_requests",
    safety: {
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_identity_values_allowed: false,
      raw_origin_values_allowed: false,
      raw_path_parameters_allowed: false
    }
  };
}

function sanitizedRouteError(httpStatus, decision) {
  const boundaryDenial = Object.values(A3_REQUEST_BOUNDARY_DENIALS)
    .find((item) => item.decision === decision);
  if (boundaryDenial) {
    return {
      schema_version: "a3.sanitized_bad_request.v1",
      error: boundaryDenial.error
    };
  }
  if (httpStatus === 401) {
    return {
      schema_version: "a3.sanitized_unauthorized.v1",
      error: "authentication_required"
    };
  }
  return {
    schema_version: "a3.sanitized_forbidden.v1",
    error: "access_denied"
  };
}

function sanitizedCustomerMessage(httpStatus) {
  if (httpStatus === 400) return "The request body is not valid JSON.";
  if (httpStatus === 408) return "The request body was not received in time.";
  if (httpStatus === 413) return "The request body is too large.";
  if (httpStatus === 415) return "The request media type is not supported.";
  if (httpStatus === 422) return "The JSON request body must be an object.";
  if (httpStatus === 401) return "Authentication is required.";
  return "The request is not allowed.";
}

function buildRequestTransport(route, options = {}) {
  const transportMethod = normalizedAuditMethod(options.transportMethod || route.method);
  const preflightForMethod = transportMethod === "OPTIONS"
    ? normalizedAuditMethod(options.preflightMethod, null)
    : null;
  return {
    transport_method: transportMethod,
    route_method: normalizedAuditMethod(route.method),
    preflight: transportMethod === "OPTIONS",
    preflight_for_method: preflightForMethod,
    request_body_state: normalizedRequestBodyState(options.requestBodyState)
  };
}

function normalizedRequestBodyState(value) {
  const state = String(value || "not_read").trim().toLowerCase();
  return ["not_read", "valid_json", ...Object.keys(A3_REQUEST_BOUNDARY_DENIALS)].includes(state)
    ? state
    : "not_read";
}

function normalizedAuditMethod(value, fallback = "UNKNOWN") {
  const method = String(value || "").trim().toUpperCase();
  return ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"].includes(method)
    ? method
    : fallback;
}

function auditSentinelScope(access) {
  const sentinel = access === "public" ? "public" : "unavailable";
  return Object.fromEntries(A3_REQUIRED_SCOPE_FIELDS.map((field) => [field, sentinel]));
}

function emptyScopeState() {
  return {
    principal: "not_required",
    requested: "not_required",
    matches: null
  };
}

function normalizeMode(mode) {
  if (mode === undefined || mode === null || mode === "") {
    return A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED;
  }
  const normalized = String(mode).trim().toLowerCase();
  if (["hosted", "hosted_enforced"].includes(normalized)) {
    return A3_ROUTE_ACCESS_MODES.HOSTED_ENFORCED;
  }
  if (["demo", "contract", "demo_contract", "contract_demo"].includes(normalized)) {
    return A3_ROUTE_ACCESS_MODES.DEMO_CONTRACT;
  }
  return null;
}

function normalizedNow(value) {
  const parsed = parseTimestamp(value);
  return new Date(parsed === null ? Date.now() : parsed).toISOString();
}

function parseTimestamp(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? value.getTime() : null;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return null;
    return value < 10_000_000_000 ? value * 1000 : value;
  }
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function scopeFingerprint(scope) {
  return digest(A3_REQUIRED_SCOPE_FIELDS.map((field) => String(scope?.[field] || "")).join("\u001f"));
}

function digest(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function snakeToCamel(field) {
  return field.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
}

function hasExplicitScopeField(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  return A3_REQUIRED_SCOPE_FIELDS.some((field) => (
    ownValue(value, field) !== undefined || ownValue(value, snakeToCamel(field)) !== undefined
  ));
}

function ownValue(object, key) {
  return object && typeof object === "object" && Object.prototype.hasOwnProperty.call(object, key)
    ? object[key]
    : undefined;
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function firstObject(...values) {
  return values.find((value) => value && typeof value === "object" && !Array.isArray(value)) || {};
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) {
    return value;
  }
  Object.freeze(value);
  for (const nested of Object.values(value)) {
    deepFreeze(nested);
  }
  return value;
}
