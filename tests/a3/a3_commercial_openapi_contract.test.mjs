import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { findCommercialApiContractLeaks } from "../../services/report/a3_commercial_api_contract.mjs";

const OPENAPI_PATH = new URL("../../docs/a3/openapi/a3_commercial_api.openapi.json", import.meta.url);
const COMMERCIAL_FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_api_contract.redacted.json", import.meta.url);

const REQUIRED_FOCUS_TAGS = [
  "Dashboard",
  "Reports",
  "Release Gate",
  "Admin",
  "Billing",
  "Trust"
];

const REQUIRED_OPERATION_NOTES = [
  "x-tenant-scope",
  "x-auth",
  "x-rbac",
  "x-usage",
  "x-audit",
  "x-a1-a2-contract"
];

test("A3 commercial OpenAPI artifact has the expected schema version and focus surfaces", async () => {
  const spec = await readOpenApi();

  assert.equal(spec.openapi, "3.1.0");
  assert.equal(spec["x-schema-version"], "a3.openapi.commercial_api.v1");
  assert.equal(spec.info.title, "Ashr++ A3 Commercial Product Console API");
  assert.ok(spec["x-contract-source"].includes("services/report/a3_commercial_api_contract.mjs"));

  const declaredTags = new Set(spec.tags.map((tag) => tag.name));
  for (const tag of REQUIRED_FOCUS_TAGS) {
    assert.equal(declaredTags.has(tag), true, `missing declared tag ${tag}`);
  }

  const operationsByTag = new Map(REQUIRED_FOCUS_TAGS.map((tag) => [tag, 0]));
  for (const operation of collectOperations(spec)) {
    for (const tag of operation.tags || []) {
      if (operationsByTag.has(tag)) {
        operationsByTag.set(tag, operationsByTag.get(tag) + 1);
      }
    }
  }

  for (const [tag, count] of operationsByTag) {
    assert.equal(count > 0, true, `tag ${tag} must have at least one operation`);
  }

  for (const requiredPath of [
    "/api/a3/dashboard",
    "/api/a3/runs/{runId}",
    "/api/a3/releases/{releaseId}/evidence-summary",
    "/api/a3/reports",
    "/api/a3/reports/share",
    "/api/a3/admin/console",
    "/api/a3/review/denials",
    "/api/a3/billing/readiness",
    "/api/a3/usage/ledger",
    "/api/a3/enterprise/readiness"
  ]) {
    assert.ok(spec.paths[requiredPath], `missing OpenAPI path ${requiredPath}`);
  }
});

test("A3 commercial OpenAPI artifact carries tenant/auth/RBAC/usage/audit notes on every operation", async () => {
  const spec = await readOpenApi();
  const operations = collectOperations(spec);
  assert.equal(operations.length >= 12, true, "expected commercial API surface coverage");

  for (const operation of operations) {
    for (const note of REQUIRED_OPERATION_NOTES) {
      assert.ok(operation[note], `${operation.operationId} missing ${note}`);
    }

    assert.ok(Array.isArray(operation["x-tenant-scope"].required));
    assert.ok(operation["x-tenant-scope"].required.includes("organization_id"));
    assert.ok(operation["x-auth"].backend_owner.includes("A1"));
    assert.equal(operation["x-rbac"].denied_state_required, true);
    assert.ok(Array.isArray(operation["x-usage"].meters));
    assert.ok(operation["x-usage"].source_of_truth.includes("A1 usage ledger"));
    assert.ok(Array.isArray(operation["x-audit"].events));
    assert.equal(operation["x-audit"].payload_policy, "ids_hashes_refs_status_counts_only");
  }

  for (const note of ["tenant", "auth", "rbac", "usage", "audit"]) {
    assert.ok(spec["x-required-commercial-notes"][note], `missing top-level ${note} note`);
  }
});

test("A3 commercial OpenAPI artifact preserves A1/A2 source authority references", async () => {
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
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"].a1.includes("RunResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"].a1.includes("usage ledger")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"].a2.includes("GradeResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"].a2.includes("ReleaseGate")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"].a2.includes("redaction verifier")));

  const commercialRoutes = new Set(fixture.endpoint_matrix.map((endpoint) => endpoint.local_a3_route));
  for (const localRoute of [
    "GET /api/a3/dashboard",
    "GET /api/a3/runs/:runId",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "POST /api/a3/review/denials",
    "POST /api/a3/reports/share",
    "GET /api/a3/admin/console",
    "GET /api/a3/billing/readiness",
    "GET /api/a3/usage/ledger"
  ]) {
    assert.equal(commercialRoutes.has(localRoute), true, `existing commercial contract missing ${localRoute}`);
  }
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
