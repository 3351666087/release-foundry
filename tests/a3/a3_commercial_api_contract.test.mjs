import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  A3_COMMERCIAL_API_CONTRACT_SCHEMA_VERSION,
  buildA3CommercialApiContract,
  findCommercialApiContractLeaks,
  validateA3CommercialApiContract
} from "../../services/report/a3_commercial_api_contract.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import {
  A3_DB_CONTRACT,
  createFixtureBackedA3Store
} from "../../services/report/a3_store.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";

const FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_api_contract.redacted.json", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_commercial_api_contract_2026_07_09.md", import.meta.url);

test("A3 commercial API contract maps SaaS /v1 routes to product surfaces", async () => {
  const contract = buildA3CommercialApiContract();
  const validation = validateA3CommercialApiContract(contract);

  assert.equal(contract.schema_version, A3_COMMERCIAL_API_CONTRACT_SCHEMA_VERSION);
  assert.equal(validation.valid, true, validation.errors.join("\n"));
  assert.equal(contract.endpoint_matrix.length >= 20, true);
  assert.equal(contract.summary.endpoint_count, contract.endpoint_matrix.length);
  assert.equal(contract.summary.implemented_or_read_only_count >= 10, true);
  assert.equal(contract.summary.plan_only_count > 0, true);
  assert.equal(contract.summary.blocked_by_auth_count > 0, true);
  assert.match(contract.contract_hash, /^[a-f0-9]{64}$/);

  const surfaces = new Set(contract.endpoint_matrix.map((endpoint) => endpoint.a3_surface));
  for (const surface of contract.required_a3_surfaces) {
    assert.equal(surfaces.has(surface), true, `missing surface ${surface}`);
  }

  const routes = new Set(contract.endpoint_matrix.map((endpoint) => endpoint.route));
  for (const route of [
    "POST /v1/runs",
    "GET /v1/runs/{run_id}",
    "POST /v1/release-gates/evaluate",
    "POST /v1/release-gates/{release_gate_id}/approvals",
    "POST /v1/reports/{report_id}/share",
    "GET /v1/usage",
    "POST /v1/billing/checkout"
  ]) {
    assert.equal(routes.has(route), true, `missing route ${route}`);
  }

  assert.equal(contract.source_authority.a1.must_not_change.includes("does not mutate A1"), true);
  assert.equal(contract.source_authority.a2.must_not_change.includes("does not change judge"), true);
  assert.equal(contract.tenant_auth_rbac_usage_audit.usage.billing_mutations_enabled, false);
  assert.equal(contract.safety.contains_secret_values, false);
  assert.deepEqual(findCommercialApiContractLeaks(contract), []);
});

test("A3 commercial API contract fixture and docs are generated and secret-free", async () => {
  const fixture = JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
  const expected = buildA3CommercialApiContract();
  assert.deepEqual(fixture, expected);
  assert.equal(validateA3CommercialApiContract(fixture).valid, true);
  assert.deepEqual(findCommercialApiContractLeaks(fixture), []);

  const doc = await readFile(DOC_PATH, "utf8");
  for (const term of [
    "ANCHOR: A3_COMMERCIAL_API_CONTRACT",
    "a3.commercial_api_contract.v1",
    "GET /api/a3/commercial-api/contract",
    "POST /v1/release-gates/evaluate",
    "commercial_api_contracts",
    "ashr.event_envelope.v1",
    "tenant",
    "auth",
    "RBAC",
    "usage",
    "audit",
    "A1 RunResult",
    "A2 GradeResult",
    "does not mutate A1",
    "does not change judge"
  ]) {
    assert.ok(doc.includes(term), `missing doc term ${term}`);
  }
  assert.equal(findCommercialApiContractLeaks(doc).length, 0);
});

test("A3 API exposes commercial API contract and DB migration coverage", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store });
  try {
    const response = await fetch(`${url}/api/a3/commercial-api/contract?source=mock&environment_id=staging`);
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.schema_version, "a3.commercial_api_contract.v1");
    assert.equal(payload.tenant_scope.organization_id, "org-local");
    assert.equal(payload.tenant_scope.project_id, "project-local");
    assert.equal(payload.tenant_scope.environment_id, "staging");
    assert.equal(payload.endpoint_matrix.some((endpoint) => endpoint.route === "GET /v1/usage"), true);
    assert.equal(payload.endpoint_matrix.some((endpoint) => endpoint.local_a3_route === "GET /api/a3/billing/readiness"), true);
    assert.equal(payload.event_envelope_contract.required_fields.includes("payload_hash"), true);
    assert.deepEqual(findCommercialApiContractLeaks(payload), []);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  assert.equal(A3_DB_CONTRACT.tables.includes("commercial_api_contracts"), true);
  assert.equal(A3_DB_CONTRACT.api_surfaces.includes("GET /api/a3/commercial-api/contract"), true);
  const migrations = buildA3SqlMigrationPlan();
  assert.equal(migrations.statements.some((statement) => statement.tables.includes("commercial_api_contracts")), true);
});
