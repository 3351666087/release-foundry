import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { findCommercialApiContractLeaks } from "../../services/report/a3_commercial_api_contract.mjs";
import {
  inspectA3OpenApiRuntimeParity,
  normalizeContractPath,
  synchronizeA3OpenApiRuntimeParity
} from "../../services/report/a3_openapi_runtime_parity.mjs";
import { A3_SENSITIVE_ROUTE_PATTERNS } from "../../services/report/a3_route_access_control.mjs";

const OPENAPI_PATH = new URL("../../docs/a3/openapi/a3_commercial_api.openapi.json", import.meta.url);
const COMMERCIAL_FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_api_contract.redacted.json", import.meta.url);

const FIVE_LEVEL_SCOPE = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];

const VERIFIED_PRINCIPAL_SECURITY = [
  { A1VerifiedSession: [] },
  { A1ServiceAccount: [] }
];

const PUBLIC_READ_PATHS = new Set([
  "/api/a3/health",
  "/r/{shareToken}"
]);

const REQUIRED_FOCUS_TAGS = [
  "Dashboard",
  "Reports",
  "Release Gate",
  "Admin",
  "Billing",
  "Trust",
  "Review",
  "Operations",
  "Notifications"
];

const REQUIRED_SENSITIVE_READ_SURFACES = {
  dashboard: ["/api/a3/dashboard"],
  runs_and_case: ["/api/a3/runs", "/api/a3/runs/{runId}", "/api/a3/cases/{caseId}"],
  evidence: [
    "/api/a3/releases/{releaseId}/evidence-summary",
    "/api/a3/releases/{releaseId}/evidence-health",
    "/api/a3/a1-a2/evidence-spine"
  ],
  reports: [
    "/api/a3/reports",
    "/api/a3/reports/center",
    "/api/a3/reports/{reportId}",
    "/api/a3/reports/{reportId}/manifest"
  ],
  review: ["/api/a3/review/workflow"],
  admin: ["/api/a3/admin/console", "/api/a3/auth/context", "/api/a3/auth/rbac-policy"],
  usage_and_billing: [
    "/api/a3/usage/ledger",
    "/api/a3/billing/readiness",
    "/api/a3/billing/migration-readiness"
  ],
  live_ops: ["/api/a3/live-workflow/readiness", "/api/a3/live-ops/control-plane"],
  notifications: ["/api/a3/notifications/control-plane"],
  artifacts: ["/api/a3/artifacts/registry"],
  product_console: ["/api/a3/product/console"],
  schema_drift: ["/api/a3/a1-a2/schema-drift"],
  peer_calibration: ["/api/a3/peer-branches/calibration"],
  outbox: ["/api/a3/events/outbox"]
};

const REQUIRED_OPERATION_NOTES = [
  "x-tenant-scope",
  "x-auth",
  "x-rbac",
  "x-usage",
  "x-audit",
  "x-a1-a2-contract"
];

test("A3 commercial OpenAPI v2 covers the required tenant-sensitive read surfaces", async () => {
  const spec = await readOpenApi();

  assert.equal(spec.openapi, "3.1.0");
  assert.equal(spec["x-schema-version"], "a3.openapi.commercial_api.v2");
  assert.equal(spec.info.title, "Ashr++ A3 Commercial Product Console API");
  assert.equal(spec.info.version, "2026.07.12");
  assert.ok(spec["x-contract-source"].includes("services/report/a3_commercial_api_contract.mjs"));
  assert.ok(spec["x-contract-source"].includes("docs/a3/a3_trusted_read_access_contract_2026_07_12.md"));

  const declaredTags = new Set(spec.tags.map((tag) => tag.name));
  for (const tag of REQUIRED_FOCUS_TAGS) {
    assert.equal(declaredTags.has(tag), true, `missing declared tag ${tag}`);
  }

  const requiredRoutes = new Set(Object.values(REQUIRED_SENSITIVE_READ_SURFACES).flat());
  assert.equal(requiredRoutes.size >= 20, true, "security contract must cover at least 20 sensitive reads");

  for (const [surface, routes] of Object.entries(REQUIRED_SENSITIVE_READ_SURFACES)) {
    assert.equal(routes.length > 0, true, `surface ${surface} must name at least one route`);
    for (const path of routes) {
      assert.ok(spec.paths[path]?.get, `missing ${surface} read route GET ${path}`);
    }
  }
});

test("every runtime RBAC route has an OpenAPI operation with the same permission", async () => {
  const spec = await readOpenApi();
  const parity = inspectA3OpenApiRuntimeParity(spec);
  const operations = new Map(collectOperations(spec).map((operation) => [
    `${operation.method.toUpperCase()} ${normalizeContractPath(operation.path)}`,
    operation
  ]));

  assert.equal(parity.complete, true);
  assert.equal(parity.runtime_operation_count, 53);
  assert.equal(parity.documented_runtime_operation_count, 53);
  assert.deepEqual(parity.missing, []);
  for (const route of A3_SENSITIVE_ROUTE_PATTERNS) {
    const key = `${route.method} ${normalizeContractPath(route.path_pattern)}`;
    const operation = operations.get(key);
    assert.ok(operation, `missing OpenAPI operation ${key}`);
    assert.equal(operation["x-rbac"].permission, route.required_permission, `${key} permission drift`);
  }
  assert.deepEqual(synchronizeA3OpenApiRuntimeParity(spec), spec, "committed OpenAPI must be synchronizer-clean");
});

test("every non-public A3 read explicitly requires a verified A1 principal, RBAC, scope, and sanitized denials", async () => {
  const spec = await readOpenApi();
  const protectedReads = collectOperations(spec)
    .filter(({ method }) => method === "get")
    .filter(({ path }) => !PUBLIC_READ_PATHS.has(path));

  assert.equal(protectedReads.length >= 20, true, "expected broad protected read coverage");

  for (const operation of protectedReads) {
    assert.deepEqual(operation.security, VERIFIED_PRINCIPAL_SECURITY, `${operation.operationId} must declare verified-principal security`);
    assert.equal(operation["x-access-class"], "tenant_sensitive_read");

    for (const note of REQUIRED_OPERATION_NOTES) {
      assert.ok(operation[note], `${operation.operationId} missing ${note}`);
    }

    const scope = operation["x-tenant-scope"];
    assert.ok(Array.isArray(scope.required));
    for (const field of FIVE_LEVEL_SCOPE) {
      assert.equal(scope.required.includes(field), true, `${operation.operationId} missing scope field ${field}`);
    }
    assert.equal(scope.source, "server_verified_a1_principal");
    assert.equal(scope.client_declared_scope_authoritative, false);
    assert.equal(scope.scope_match_required, true);
    assert.equal(scope.cross_tenant_default, "sanitized_403_or_404");

    const auth = operation["x-auth"];
    assert.equal(auth.required_for_hosted_saas, true);
    assert.equal(auth.backend_owner, "A1");
    assert.equal(auth.principal_authority, "A1 server-side verifier");
    assert.equal(auth.principal_source, "server_verified_a1_principal");
    assert.deepEqual(auth.accepted_principal_kinds, ["browser_session", "service_account"]);
    assert.equal(auth.client_declared_identity_authoritative, false);
    assert.equal(auth.client_declared_role_authoritative, false);
    assert.equal(auth.hosted_contract_only_not_production_proof, true);

    const rbac = operation["x-rbac"];
    assert.match(rbac.permission, /^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$/);
    assert.equal(rbac.evaluation, "server_side_against_verified_principal");
    assert.equal(rbac.client_declared_role_authoritative, false);
    assert.equal(rbac.denied_state_required, true);

    assert.equal(operation.responses["401"].$ref, "#/components/responses/Unauthorized");
    assert.equal(operation.responses["403"].$ref, "#/components/responses/Forbidden");
    assert.ok(Array.isArray(operation["x-usage"].meters));
    assert.ok(operation["x-usage"].source_of_truth.includes("A1 usage ledger"));
    assert.ok(Array.isArray(operation["x-audit"].events));
    assert.equal(operation["x-audit"].payload_policy, "ids_hashes_refs_status_counts_only");
  }
});

test("health and share-token reads are the only public reads and use distinct access contracts", async () => {
  const spec = await readOpenApi();
  const publicReads = collectOperations(spec)
    .filter(({ method, security }) => method === "get" && Array.isArray(security) && security.length === 0)
    .map(({ path }) => path)
    .sort();

  assert.deepEqual(publicReads, [...PUBLIC_READ_PATHS].sort());

  const health = spec.paths["/api/a3/health"].get;
  assert.deepEqual(health.security, []);
  assert.equal(health["x-access-class"], "public_health");
  assert.equal(health["x-public-access"].kind, "health_probe");
  assert.equal(health["x-public-access"].tenant_data_allowed, false);
  assert.equal(health["x-public-access"].customer_payload_allowed, false);
  assert.equal(health["x-rbac"], undefined);
  assert.equal(health.responses["401"], undefined);
  assert.equal(health.responses["403"], undefined);

  const share = spec.paths["/r/{shareToken}"].get;
  assert.deepEqual(share.security, []);
  assert.equal(share["x-access-class"], "public_share_capability");
  assert.equal(share["x-public-access"].kind, "share_token");
  assert.equal(share["x-public-access"].access_model, "opaque_path_capability");
  assert.equal(share["x-public-access"].token_lookup, "server_side_digest_only");
  assert.equal(share["x-public-access"].token_logging_allowed, false);
  assert.equal(share["x-public-access"].tenant_scope_resolution, "server_side_from_valid_token");
  assert.deepEqual(share["x-public-access"].lifecycle_enforcement, ["expiry", "revocation", "download_control", "view_audit"]);
  assert.equal(share["x-rbac"], undefined);
  assert.ok(share.responses["404"]);
  assert.ok(share.responses["410"]);

  const shareToken = spec.components.parameters.ShareToken;
  assert.equal(shareToken.in, "path");
  assert.equal(shareToken.required, true);
  assert.equal(shareToken["x-sensitive"], true);
  assert.equal(shareToken["x-log-policy"], "redact");
  assert.equal(shareToken.schema.writeOnly, true);
});

test("security schemes reject client-declared roles and denial schemas are closed and sanitized", async () => {
  const spec = await readOpenApi();
  const schemes = spec.components.securitySchemes;

  assert.deepEqual(Object.keys(schemes).sort(), ["A1ServiceAccount", "A1VerifiedSession"]);
  assert.equal(schemes.A1VerifiedSession.type, "apiKey");
  assert.equal(schemes.A1VerifiedSession.in, "cookie");
  assert.equal(schemes.A1VerifiedSession.name, "__Host-ashr_session");
  assert.equal(schemes.A1VerifiedSession["x-verification"], "server_side_a1");
  assert.equal(schemes.A1VerifiedSession["x-client-readable"], false);
  assert.equal(schemes.A1ServiceAccount.type, "http");
  assert.equal(schemes.A1ServiceAccount.scheme, "bearer");
  assert.equal(schemes.A1ServiceAccount["x-verification"], "server_side_a1");

  for (const [name, scheme] of Object.entries(schemes)) {
    assert.notEqual(scheme.in, "header", `${name} must not accept a client identity or role header`);
    assert.doesNotMatch(`${name}:${scheme.name || ""}`, /role/i);
  }

  const serialized = JSON.stringify(spec).toLowerCase();
  assert.equal(serialized.includes("x-a3-role"), false);

  const hostedContract = spec["x-hosted-security-contract"];
  assert.equal(hostedContract.status, "contract_only_not_production_proof");
  assert.equal(hostedContract.server_verified_principal_required, true);
  assert.equal(hostedContract.client_declared_role_headers_authoritative, false);
  assert.equal(hostedContract.client_declared_tenant_scope_authoritative, false);
  assert.equal(hostedContract.a1_hosted_login_production_complete_claimed, false);
  assert.equal(hostedContract.a2_decision_semantics_unchanged, true);

  for (const [responseName, schemaName] of [
    ["Unauthorized", "SanitizedUnauthorizedError"],
    ["Forbidden", "SanitizedForbiddenError"]
  ]) {
    const response = spec.components.responses[responseName];
    const schema = spec.components.schemas[schemaName];
    assert.equal(response["x-sanitized"], true);
    assert.equal(response.headers["Cache-Control"].schema.const, "no-store");
    assert.equal(response.content["application/json"].schema.$ref, `#/components/schemas/${schemaName}`);
    assert.equal(schema["x-sanitized"], true);
    assert.equal(schema.additionalProperties, false);
    assert.deepEqual(Object.keys(schema.properties).sort(), ["error", "request_id", "schema_version"]);
    for (const forbiddenField of ["tenant_id", "resource_id", "role", "permission", "detail", "message"]) {
      assert.equal(schema.properties[forbiddenField], undefined, `${schemaName} must not expose ${forbiddenField}`);
    }
  }
});

test("A3 commercial OpenAPI preserves A1/A2 authority and commercial fixture references", async () => {
  const spec = await readOpenApi();
  const fixture = JSON.parse(await readFile(COMMERCIAL_FIXTURE_PATH, "utf8"));

  assert.equal(fixture.schema_version, "a3.commercial_api_contract.v1");
  assert.ok(spec["x-a1-a2-references"].a1.includes("RunResult"));
  assert.ok(spec["x-a1-a2-references"].a1.includes("TraceEvent"));
  assert.ok(spec["x-a1-a2-references"].a1.includes("ToolCall"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("GradeResult"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("ReleaseGate"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("failure taxonomy"));
  assert.ok(spec["x-a1-a2-references"].a3_integration_rule.includes("must not reinterpret A2 judge semantics"));

  const operations = collectOperations(spec);
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a1?.includes("RunResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a1?.includes("usage ledger")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("GradeResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("ReleaseGate")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("redaction verifier")));

  const commercialRoutes = new Set(fixture.endpoint_matrix.map((endpoint) => endpoint.local_a3_route));
  for (const localRoute of [
    "GET /api/a3/dashboard",
    "GET /api/a3/runs/:runId",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "POST /api/a3/review/denials",
    "POST /api/a3/reports/share",
    "GET /api/a3/admin/console",
    "GET /api/a3/billing/readiness",
    "GET /api/a3/billing/migration-readiness",
    "GET /api/a3/usage/ledger"
  ]) {
    assert.equal(commercialRoutes.has(localRoute), true, `existing commercial contract missing ${localRoute}`);
  }

  const migrationReadiness = spec.paths["/api/a3/billing/migration-readiness"].get;
  assert.equal(migrationReadiness["x-schema-version"], "a3.billing_migration_readiness.v1");
  assert.equal(migrationReadiness["x-rbac"].permission, "billing:read");
  assert.deepEqual(migrationReadiness["x-a1-a2-contract"].a1, [
    "read-only billing ledger summary",
    "durable billing migration manifest",
    "provider event replay evidence"
  ]);
  assert.equal(
    migrationReadiness.responses["200"].content["application/json"].schema.$ref,
    "#/components/schemas/BillingMigrationReadiness"
  );
});

test("dashboard contract exposes a fail-closed partial aggregate state", async () => {
  const spec = await readOpenApi();
  const dashboard = spec.components.schemas.DashboardSnapshot;
  const aggregate = spec.components.schemas.AggregateScopeStatus;
  const authority = spec.components.schemas.TrustedReleaseAuthority;

  assert.equal(dashboard.properties.aggregate_scope_status.$ref, "#/components/schemas/AggregateScopeStatus");
  assert.equal(dashboard.properties.trusted_release_authority.$ref, "#/components/schemas/TrustedReleaseAuthority");
  assert.equal(aggregate.additionalProperties, false);
  assert.deepEqual(aggregate.properties.status.enum, ["complete", "partial"]);
  assert.equal(aggregate.properties.excluded_record_count.minimum, 0);
  assert.equal(aggregate.properties.safety.properties.unscoped_records_included.const, false);
  assert.equal(aggregate.properties.safety.properties.cross_tenant_fallback_allowed.const, false);
  assert.equal(aggregate.properties.safety.properties.foreign_record_counts_exposed.const, false);
  assert.deepEqual(authority.properties.upstream_decision.enum, ["allow", "block", "review", "unknown"]);
  assert.equal(authority.properties.release_ready.description.includes("must not recompute"), true);
  assert.equal(authority.properties.safety.properties.a3_score_recomputed.const, false);
  assert.equal(authority.properties.safety.properties.a3_release_ready_recomputed.const, false);
  assert.equal(authority.properties.safety.properties.client_chain_verified_flag_trusted_without_recalculation.const, false);
});

test("A3 commercial OpenAPI artifact is redacted and safe to publish", async () => {
  const text = await readFile(OPENAPI_PATH, "utf8");
  const spec = JSON.parse(text);
  const serialized = JSON.stringify(spec);

  assert.deepEqual(findCommercialApiContractLeaks(spec), []);
  assert.equal(spec["x-secret-policy"].raw_secrets_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_tokens_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_cookies_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_emails_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_signed_urls_allowed, false);
  assert.equal(spec.components.schemas.SafetyEnvelope.properties.contains_secret_values.const, false);
  assert.equal(spec.components.schemas.BillingReadiness.properties.billing_mutations_enabled.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.billing_mutations_enabled.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.raw_provider_secret_allowed.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.raw_provider_payload_embedded.const, false);

  for (const forbidden of [
    /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
    /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
    /\bghp_[A-Za-z0-9]{20,}\b/,
    /\bAKIA[0-9A-Z]{16}\b/,
    /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
    /Cookie:\s*(?!\[REDACTED\])/i,
    /ASHR_API_KEY\s*=\s*(?!\[REDACTED\])/i,
    /X-Amz-Signature=/i,
    /C:\\Users\\/i
  ]) {
    assert.equal(forbidden.test(serialized), false, `forbidden pattern leaked: ${forbidden.source}`);
  }
});

function collectOperations(spec) {
  const operations = [];
  for (const [path, pathItem] of Object.entries(spec.paths || {})) {
    for (const method of ["get", "post", "put", "patch", "delete"]) {
      if (pathItem[method]) {
        operations.push({ path, method, ...pathItem[method] });
      }
    }
  }
  return operations;
}

async function readOpenApi() {
  return JSON.parse(await readFile(OPENAPI_PATH, "utf8"));
}
