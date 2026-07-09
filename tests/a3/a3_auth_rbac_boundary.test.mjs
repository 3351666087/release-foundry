import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  authorizeA3Operation,
  buildA3AuthContext,
  buildA3RbacPolicy,
  validateA3AuthBoundary
} from "../../services/report/a3_auth_rbac_boundary.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { buildA3ArtifactRegistry } from "../../services/report/a3_artifact_registry.mjs";
import { buildSaasAdminConsole } from "../../services/report/a3_saas_admin.mjs";
import {
  A3_DB_CONTRACT,
  createFixtureBackedA3Store
} from "../../services/report/a3_store.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";
import { summarizeSaasAdminExport } from "../../services/report/report_builder.mjs";

test("A3 auth context redacts actor identity while preserving tenant and role metadata", () => {
  const context = buildA3AuthContext({
    actor_id: ["release-owner", "example.com"].join("@"),
    role: "reviewer",
    organization_id: "org-auth",
    tenant_id: "tenant-auth",
    workspace_id: "workspace-auth",
    project_id: "project-auth"
  });

  assert.equal(context.schema_version, "a3.auth_context.v1");
  assert.equal(context.actor_id, "actor_[REDACTED]");
  assert.match(context.actor_hash, /^actor_[a-f0-9]{24}$/);
  assert.equal(context.role, "reviewer");
  assert.equal(context.permissions.includes("release:approve"), true);
  assert.equal(context.tenant_scope.tenant_id, "tenant-auth");
  assert.equal(context.safety.raw_actor_identity_exposed, false);
  assert.equal(validateA3AuthBoundary(context).valid, true);
  assert.doesNotMatch(JSON.stringify(context), /release-owner|example\.com|Bearer|Cookie|ASHR_API_KEY/);
});

test("A3 RBAC policy allows local read/review operations and blocks hosted mutations", () => {
  const policy = buildA3RbacPolicy();
  assert.equal(policy.schema_version, "a3.rbac_policy.v1");
  assert.equal(policy.operations.some((item) => item.operation === "rotate_api_key"), true);
  assert.equal(policy.operations.every((item) => item.denied_state_required === true), true);
  assert.equal(validateA3AuthBoundary(policy).valid, true);

  const reviewer = buildA3AuthContext({ role: "reviewer", actor_id: "reviewer-local" });
  const share = authorizeA3Operation("share_report", reviewer);
  assert.equal(share.schema_version, "a3.authz_decision.v1");
  assert.equal(share.allowed, true);
  assert.equal(share.decision, "allowed_local_write");
  assert.equal(share.audit_event.schema_version, "ashr.event_envelope.v1");
  assert.equal(validateA3AuthBoundary(share).valid, true);

  const rotate = authorizeA3Operation("rotate_api_key", reviewer);
  assert.equal(rotate.allowed, false);
  assert.equal(rotate.decision, "denied_missing_permission");
  assert.equal(rotate.denied_state.body_policy, "sanitized_error_without_private_evidence");
  assert.equal(rotate.safety.real_cloud_mutation_performed, false);

  const ownerLocal = buildA3AuthContext({ role: "owner", actor_id: "owner-local" });
  const hostedBlocked = authorizeA3Operation("rotate_api_key", ownerLocal);
  assert.equal(hostedBlocked.allowed, false);
  assert.equal(hostedBlocked.decision, "blocked_requires_hosted_auth");
  assert.match(hostedBlocked.reason, /hosted auth/);
});

test("A3 RBAC policy covers local write and audit operations with expected roles", () => {
  const policy = buildA3RbacPolicy();
  const operations = Object.fromEntries(policy.operations.map((item) => [item.operation, item]));

  for (const operation of [
    "import_a1_run_result",
    "import_a2_grade_result",
    "share_report",
    "revoke_report",
    "view_report",
    "submit_review_waiver",
    "submit_review_approval",
    "plan_admin_action",
    "submit_admin_action",
    "capture_release_readback",
    "read_event_outbox",
    "read_schema_drift",
    "read_peer_branch_calibration",
    "read_billing_migration_readiness"
  ]) {
    assert.ok(operations[operation], `${operation} should be covered by RBAC policy`);
    assert.equal(operations[operation].denied_state_required, true);
  }

  assert.deepEqual(operations.share_report.roles_allowed, ["admin", "owner", "reviewer"]);
  assert.deepEqual(operations.revoke_report.roles_allowed, ["admin", "owner"]);
  assert.deepEqual(operations.submit_review_approval.roles_allowed, ["owner", "reviewer"]);
  assert.deepEqual(operations.read_event_outbox.roles_allowed, ["admin", "auditor", "owner", "reviewer"]);
  assert.deepEqual(operations.read_schema_drift.roles_allowed, ["admin", "auditor", "owner", "reviewer"]);
  assert.deepEqual(operations.read_peer_branch_calibration.roles_allowed, ["admin", "auditor", "owner", "reviewer"]);
  assert.equal(operations.read_billing_migration_readiness.route, "GET /api/a3/billing/migration-readiness");
  assert.equal(operations.read_billing_migration_readiness.required_permission, "billing:read");
  assert.equal(operations.read_billing_migration_readiness.mode, "read_only");
  assert.deepEqual(operations.read_billing_migration_readiness.roles_allowed, ["billing_admin", "owner"]);
  assert.equal(authorizeA3Operation("submit_review_approval", { role: "admin" }).allowed, false);
  assert.equal(authorizeA3Operation("submit_review_approval", { role: "admin" }).decision, "denied_missing_permission");
  assert.equal(authorizeA3Operation("plan_admin_action", { role: "viewer" }).allowed, false);
  assert.equal(authorizeA3Operation("plan_admin_action", { role: "billing_admin" }).decision, "allowed_plan_only");
  assert.equal(authorizeA3Operation("read_billing_migration_readiness", { role: "billing_admin" }).decision, "allowed_read_only");
  assert.equal(authorizeA3Operation("read_billing_migration_readiness", { role: "viewer" }).decision, "denied_missing_permission");
  assert.equal(authorizeA3Operation("read_billing_migration_readiness", { role: "auditor" }).decision, "denied_missing_permission");
  assert.equal(authorizeA3Operation("unknown_mutation", { role: "owner" }).decision, "denied_unknown_operation");
});

test("A3 SaaS admin export and artifact registry include auth/RBAC boundary evidence", async () => {
  const runFixture = await loadJson("../../fixtures/a3/mock_run_results.json");
  const gradeFixture = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const admin = buildSaasAdminConsole({
    runFixture,
    gradeFixture,
    role: "developer"
  });
  const exportSummary = summarizeSaasAdminExport(admin);

  assert.equal(admin.auth_boundary.schema_version, "a3.saas_admin_auth_boundary.v1");
  assert.equal(exportSummary.auth_boundary.actor_identity_redacted, true);
  assert.equal(exportSummary.auth_boundary.role, "developer");
  assert.equal(exportSummary.auth_boundary.real_cloud_mutations_performed, false);

  const registry = buildA3ArtifactRegistry({
    source: "mock",
    saasAdmin: admin
  });
  assert.ok(registry.entries.some((item) => item.artifact_type === "auth_rbac_boundary"));
  assert.ok(registry.packet_presets.some((item) => (
    item.preset_id === "security_audit_packet"
    && item.required_artifact_types.includes("auth_rbac_boundary")
  )));
  assert.equal(registry.safety.raw_secret_values_allowed, false);
  assert.doesNotMatch(JSON.stringify(registry), /Bearer|Cookie|ASHR_API_KEY|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
});

test("A3 API exposes auth/RBAC boundary routes without leaking actor secrets", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store });
  try {
    const actor = ["owner", "example.com"].join("@");
    const context = await getJson(`${url}/api/a3/auth/context?role=reviewer&actor_id=${encodeURIComponent(actor)}&organization_id=org-api&tenant_id=tenant-api&workspace_id=workspace-api&project_id=project-api`);
    assert.equal(context.schema_version, "a3.auth_context_api_response.v1");
    assert.equal(context.auth_context.actor_id, "actor_[REDACTED]");
    assert.equal(context.auth_context.tenant_scope.tenant_id, "tenant-api");
    assert.equal(context.sample_decisions.some((item) => item.operation === "rotate_api_key" && item.allowed === false), true);
    assert.doesNotMatch(JSON.stringify(context), /owner@example\.com|Bearer|Cookie|ASHR_API_KEY/);

    const policy = await getJson(`${url}/api/a3/auth/rbac-policy`);
    assert.equal(policy.schema_version, "a3.rbac_policy.v1");
    assert.equal(policy.operations.some((item) => item.operation === "share_report"), true);

    const authorizeResponse = await fetch(`${url}/api/a3/auth/authorize`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-a3-role": "billing_admin",
        "x-a3-actor-id": actor
      },
      body: JSON.stringify({
        operation: "share_report",
        authorization: "Bearer should-not-leak"
      })
    });
    assert.equal(authorizeResponse.status, 200);
    const decision = await authorizeResponse.json();
    assert.equal(decision.schema_version, "a3.authz_decision.v1");
    assert.equal(decision.allowed, false);
    assert.equal(decision.decision, "denied_missing_permission");
    assert.equal(decision.audit_event.redaction_status, "metadata_only");
    assert.doesNotMatch(JSON.stringify(decision), /should-not-leak|owner@example\.com|Bearer [A-Za-z0-9]/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("A3 auth/RBAC boundary is represented in API, DB, and OpenAPI contracts", async () => {
  assert.equal(A3_DB_CONTRACT.tables.includes("auth_contexts"), true);
  assert.equal(A3_DB_CONTRACT.tables.includes("rbac_policy_snapshots"), true);
  assert.equal(A3_DB_CONTRACT.tables.includes("authz_decisions"), true);
  assert.equal(A3_DB_CONTRACT.api_surfaces.includes("GET /api/a3/auth/context"), true);
  assert.equal(A3_DB_CONTRACT.api_surfaces.includes("POST /api/a3/auth/authorize"), true);

  const migration = buildA3SqlMigrationPlan();
  assert.equal(migration.tenancy_columns.includes("tenant_id"), true);
  assert.equal(migration.statements.some((item) => item.tables.includes("auth_contexts")), true);
  assert.match(migration.statements.map((item) => item.sql).join("\n"), /CREATE TABLE IF NOT EXISTS authz_decisions/);
  assert.match(migration.statements.map((item) => item.sql).join("\n"), /CREATE TABLE IF NOT EXISTS billing_migration_readiness/);

  const openapi = await loadJson("../../docs/a3/openapi/a3_commercial_api.openapi.json");
  assert.ok(openapi.paths["/api/a3/auth/context"]);
  assert.ok(openapi.paths["/api/a3/auth/rbac-policy"]);
  assert.ok(openapi.paths["/api/a3/auth/authorize"]);
  assert.equal(openapi.paths["/api/a3/billing/migration-readiness"].get["x-rbac"].permission, "billing:read");
  assert.ok(openapi.components.schemas.AuthzDecision);
  assert.ok(openapi.components.schemas.BillingMigrationReadiness);
});

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
