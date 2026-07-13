import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { A3_RBAC_ROLES } from "../../services/report/a3_auth_rbac_boundary.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

const source = "a3-golden-path-rc2";
const scope = Object.freeze({
  organization_id: "org-local",
  tenant_id: "tenant-local",
  workspace_id: "workspace-local",
  project_id: "project-local",
  environment_id: "staging"
});

test("A3 store exposes tenant-scoped A1 sandbox evidence without changing deployment acceptance", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  const before = await store.getDashboardSnapshot(source);
  const calibration = await store.getSelfHostSandboxCalibration({ source });
  const after = await store.getDashboardSnapshot(source);

  assert.equal(calibration.schema_version, "a3.self_host_sandbox_calibration.v1");
  assert.equal(calibration.status, "sandbox_verified");
  assert.equal(calibration.summary.passed, 4);
  assert.equal(calibration.summary.production_gap_count, 5);
  assert.equal(calibration.authority_boundary.production_verified, false);
  assert.equal(calibration.authority_boundary.deployment_acceptance_mutated, false);
  assert.equal(calibration.authority_boundary.a2_decision_recomputed, false);
  assert.equal(before.deployment_acceptance.summary.passed, 8);
  assert.equal(after.deployment_acceptance.summary.passed, 8);
  assert.equal(after.trusted_release_authority.status, "integrity_invalid");
  assert.equal(after.trusted_release_authority.upstream_decision, "unknown");

  await assert.rejects(
    () => store.getSelfHostSandboxCalibration({ source, ...scope, projectId: "project-other", enforceScope: true }),
    /scope/i
  );
});

test("hosted A3 sandbox API requires deployment:read, audits access, and rejects cross scope", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal("auditor")
  }, async (url) => {
    const response = await fetch(`${url}/api/a3/deployment/sandbox-calibration?source=${source}`);
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.status, "sandbox_verified");
    assert.equal(payload.access_contract.required_permission, "deployment:read");
    assert.equal(payload.access_contract.tenant_scope_enforced, true);
    assert.equal(payload.access_contract.hosted_read_audited, true);
    assert.equal(payload.safety.production_verified, false);
    assert.doesNotMatch(JSON.stringify(payload), /Bearer|github_pat_|ghp_|\bsk-|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|[A-Za-z]:\\/i);

    const crossScope = await fetch(`${url}/api/a3/deployment/sandbox-calibration?source=${source}&project_id=project-other`);
    assert.equal(crossScope.status, 403);
    assert.deepEqual(await crossScope.json(), {
      schema_version: "a3.sanitized_forbidden.v1",
      error: "access_denied"
    });
  });

  const state = store.exportState();
  assert.equal(state.auditEvents.some((event) => event.event_type === "route_access.allowed"), true);
  assert.equal(state.auditEvents.some((event) => event.event_type === "route_access.denied"), true);
  assert.equal(state.eventOutbox.some((event) => event.event_type === "route_access.allowed"), true);

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal("viewer")
  }, async (url) => {
    const denied = await fetch(`${url}/api/a3/deployment/sandbox-calibration?source=${source}`);
    assert.equal(denied.status, 403);
    assert.deepEqual(await denied.json(), {
      schema_version: "a3.sanitized_forbidden.v1",
      error: "access_denied"
    });
  });
});

test("SQLite persists the validated sandbox calibration as a distinct non-production record", async () => {
  const directory = await mkdtemp(join(tmpdir(), "a3-self-host-sandbox-db-"));
  const dbPath = join(directory, "a3.db");
  const fixtureStore = await createFixtureBackedA3Store({ sources: [source] });
  let store;
  try {
    store = await createSqliteA3Store({ dbPath, seed: fixtureStore.exportState() });
    let inspection = store.inspectSqliteState();
    assert.equal(inspection.operational_tables.self_host_sandbox_calibrations, 1);
    assert.equal((await store.getSelfHostSandboxCalibration({ source })).status, "sandbox_verified");
    store.close();
    store = null;

    store = await createSqliteA3Store({ dbPath });
    const restored = await store.getSelfHostSandboxCalibration({ source });
    inspection = store.inspectSqliteState();
    assert.equal(restored.status, "sandbox_verified");
    assert.equal(restored.authority_boundary.production_verified, false);
    assert.equal(inspection.operational_tables.self_host_sandbox_calibrations, 1);
  } finally {
    store?.close();
    await rm(directory, { recursive: true, force: true });
  }
});

function trustedPrincipal(role) {
  return {
    trusted: true,
    authenticated: true,
    role,
    actor_hash: "actor_0123456789abcdef01234567",
    session: { state: "active" },
    permissions: [...A3_RBAC_ROLES[role]],
    expires_at: "2099-01-01T00:00:00.000Z",
    tenant_scope: scope
  };
}

async function withServer(options, operation) {
  const { server, url } = await startA3ApiServer(options);
  try {
    return await operation(url);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}
