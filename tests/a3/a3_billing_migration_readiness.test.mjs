import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  A3_BILLING_MIGRATION_READINESS_SCHEMA_VERSION,
  buildA3BillingMigrationReadiness,
  findA3BillingMigrationReadinessLeaks,
  validateA3BillingMigrationReadiness
} from "../../services/report/a3_billing_migration_readiness.mjs";

const FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_billing_migration_readiness.redacted.json", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_billing_migration_readiness_2026_07_09.md", import.meta.url);
const MODULE_PATH = new URL("../../services/report/a3_billing_migration_readiness.mjs", import.meta.url);

test("A3 billing migration readiness maps A1 durable migration and replay evidence", () => {
  const contract = buildA3BillingMigrationReadiness();
  const validation = validateA3BillingMigrationReadiness(contract);

  assert.equal(contract.schema_version, A3_BILLING_MIGRATION_READINESS_SCHEMA_VERSION);
  assert.equal(validation.valid, true, validation.errors.join("\n"));
  assert.equal(contract.summary.status, "read_only_migration_contract_ready");
  assert.equal(contract.summary.ready_for_live_customer_billing, false);
  assert.match(contract.contract_hash, /^[a-f0-9]{64}$/);

  const commits = new Set(contract.upstream_commits.map((commit) => commit.sha));
  for (const sha of ["f8ee956", "91213fc", "11ac03e"]) {
    assert.equal(commits.has(sha), true, `missing upstream commit ${sha}`);
  }

  const durable = contract.upstream_evidence.durable_billing_ledger_migration;
  assert.equal(durable.source_commit, "91213fc");
  assert.equal(durable.source_schema_version, "releasefoundry.a1_billing_ledger_migration_manifest.v1");
  assert.deepEqual(durable.providers, ["stripe", "wechat_pay", "alipay"]);
  assert.equal(durable.tables.some((table) => table.name === "billing_provider_events"), true);
  assert.equal(durable.functions.includes("ingest_billing_provider_event"), true);
  assert.equal(durable.public_safety.provider_calls_executed, false);

  const replay = contract.upstream_evidence.replay_evidence;
  assert.equal(replay.source_commit, "f8ee956");
  assert.deepEqual(replay.replay_statuses_observed, ["accepted", "duplicate"]);
  assert.deepEqual(replay.ledger_event_types_observed, ["invoice_paid", "usage_reconciled"]);
  assert.deepEqual(replay.totals_by_currency_minor, { usd: 12345 });
  assert.equal(replay.usage_units, 14);

  const smoke = contract.upstream_evidence.live_smoke;
  assert.equal(smoke.source_commit, "11ac03e");
  assert.equal(smoke.executed_by_a3, false);
  assert.deepEqual(smoke.replay_statuses_expected, ["accepted", "duplicate", "conflict"]);
});

test("A3 readiness contract exposes API DB event artifact and security boundaries", () => {
  const contract = buildA3BillingMigrationReadiness();

  assert.equal(contract.api_contract.some((route) => route.route === "GET /api/a3/billing/readiness"), true);
  assert.equal(contract.api_contract.every((route) => route.a3_side_effect === "none_read_only_contract"), true);
  assert.equal(contract.db_contract.durable_backend_owner, "A1");
  assert.equal(contract.db_contract.a3_db_mutation_required, false);
  assert.equal(contract.db_contract.required_safety.rls_enabled_and_forced, true);
  assert.equal(contract.db_contract.required_safety.raw_provider_secret_allowed, false);

  const dbTables = new Set(contract.db_contract.tables.map((table) => table.name));
  for (const table of ["billing_accounts", "billing_provider_events", "billing_ledger_events"]) {
    assert.equal(dbTables.has(table), true, `missing DB contract table ${table}`);
  }

  assert.equal(contract.event_contract.provider_event_types.includes("invoice.paid"), true);
  assert.equal(contract.event_contract.ledger_event_types.includes("usage_reconciled"), true);
  assert.equal(contract.event_contract.replay_statuses.includes("conflict"), true);
  assert.equal(contract.artifact_contract.upstream_inputs.some((artifact) => artifact.path.endsWith("002_a1_billing_ledger.sql")), true);
  assert.equal(contract.artifact_contract.a3_outputs.some((artifact) => artifact.path === "fixtures/a3/p3/a3_billing_migration_readiness.redacted.json"), true);

  const boundary = contract.tenant_auth_rbac_usage_audit;
  assert.deepEqual(boundary.tenant.required_scope, ["organization_id", "project_id", "environment_id"]);
  assert.equal(boundary.auth.raw_credentials_allowed, false);
  assert.deepEqual(boundary.rbac.a3_mutation_roles_enabled, []);
  assert.equal(boundary.usage.billing_mutations_enabled, false);
  assert.equal(boundary.audit.raw_payload_logged, false);
  assert.equal(contract.safety.env_local_read, false);
  assert.equal(contract.safety.real_api_called_by_a3, false);
  assert.equal(contract.safety.real_payment_provider_called, false);
});

test("A3 billing migration fixture docs and source are deterministic and secret-free", async () => {
  const fixture = JSON.parse(await readFile(FIXTURE_PATH, "utf8"));
  const expected = buildA3BillingMigrationReadiness();
  assert.deepEqual(fixture, expected);
  assert.equal(validateA3BillingMigrationReadiness(fixture).valid, true);
  assert.deepEqual(findA3BillingMigrationReadinessLeaks(fixture), []);

  const doc = await readFile(DOC_PATH, "utf8");
  for (const term of [
    "ANCHOR: A3_BILLING_MIGRATION_READINESS",
    "a3.billing_migration_readiness.v1",
    "origin/agent/a1-local-sdk-runner",
    "11ac03e",
    "91213fc",
    "f8ee956",
    "billing_accounts",
    "billing_provider_events",
    "billing_ledger_events",
    "tenant",
    "auth",
    "RBAC",
    "usage",
    "audit",
    "No .env.local",
    "No real API"
  ]) {
    assert.ok(doc.includes(term), `missing doc term ${term}`);
  }
  assert.deepEqual(findA3BillingMigrationReadinessLeaks(doc), []);

  const source = await readFile(MODULE_PATH, "utf8");
  assert.doesNotMatch(source, /readFile|fetch\(|process\.env|\.env\.local/);
});
