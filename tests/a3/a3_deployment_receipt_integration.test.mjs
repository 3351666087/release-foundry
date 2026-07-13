import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";

import { A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION } from "../../services/report/a3_deployment_receipt_workflow.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { A3_RBAC_ROLES } from "../../services/report/a3_auth_rbac_boundary.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";
import {
  A3StoreValidationError,
  createFixtureBackedA3Store,
  loadA3SourceSnapshot
} from "../../services/report/a3_store.mjs";

const source = "a3-golden-path-rc2";
const scope = {
  organization_id: "org-local",
  tenant_id: "tenant-local",
  workspace_id: "workspace-local",
  project_id: "project-local",
  environment_id: "staging"
};

test("A3 store persists receipt metadata and reviews without promoting deployment acceptance", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  const before = await store.getDashboardSnapshot(source);
  const input = receiptInput(before);

  assert.equal(before.deployment_receipt_inbox.schema_version, "a3.deployment_receipt_inbox.v1");
  assert.equal(before.deployment_receipt_inbox.blocker_slot_count, 9);
  assert.equal(before.deployment_receipt_inbox.receipt_count, 0);
  assert.equal(before.deployment_acceptance.summary.passed, 8);

  await assert.rejects(
    () => store.submitDeploymentReceipt(input, { source }),
    (error) => error instanceof A3StoreValidationError
      && error.requestType === "deployment_receipt_submit"
      && error.details.some((item) => item.field === "Idempotency-Key")
  );

  const submitted = await store.submitDeploymentReceipt(input, {
    source,
    actorHash: "actor_deployment_submitter_hash",
    submittedAt: "2026-07-13T06:01:00.000Z",
    idempotencyKey: "deployment-submit-001"
  });
  assert.equal(submitted.status, "submitted");
  assert.equal(submitted.version, 1);
  assert.equal(submitted.authority_validation.production_verified, false);
  assert.equal(submitted.acceptance_effect.changes_deployment_acceptance, false);
  assert.equal(submitted.idempotency.status, "recorded");
  assert.equal(submitted.event_outbox_delivery_status, "pending");

  const replay = await store.submitDeploymentReceipt(input, {
    source,
    submittedAt: "2026-07-13T06:01:00.000Z",
    idempotencyKey: "deployment-submit-001"
  });
  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(replay.idempotency.duplicate, true);

  const reviewed = await store.reviewDeploymentReceipt(submitted.receipt_id, {
    action: "acknowledge",
    reason_code: "metadata_complete",
    expected_version: 1
  }, {
    source,
    actorHash: "actor_deployment_reviewer_hash",
    reviewedAt: "2026-07-13T06:02:00.000Z",
    idempotencyKey: "deployment-review-001"
  });
  assert.equal(reviewed.status, "acknowledged");
  assert.equal(reviewed.version, 2);
  assert.equal(reviewed.authority_validation.status, "awaiting_authoritative_readback");
  assert.equal(reviewed.authority_validation.production_verified, false);

  await assert.rejects(
    () => store.reviewDeploymentReceipt(submitted.receipt_id, {
      action: "reject",
      reason_code: "stale_evidence",
      expected_version: 1
    }, {
      source,
      idempotencyKey: "deployment-review-stale"
    }),
    (error) => error instanceof A3StoreValidationError
      && error.statusCode === 409
      && error.error === "version_conflict"
  );

  const after = await store.getDashboardSnapshot(source);
  const slot = after.deployment_receipt_inbox.slots.find((item) => item.blocker_id === input.blocker_id);
  assert.equal(after.deployment_receipt_inbox.receipt_count, 1);
  assert.equal(after.deployment_receipt_inbox.production_verified_count, 0);
  assert.equal(slot.intake_status, "acknowledged");
  assert.equal(slot.production_verified, false);
  assert.equal(slot.deployment_check_status, "not_proven");
  assert.equal(after.deployment_acceptance.summary.passed, 8);
  assert.equal(after.deployment_handoff.blocking_items.length, 9);
  assert.equal(after.trusted_release_authority.status, "integrity_invalid");
  assert.equal(after.trusted_release_authority.upstream_decision, "unknown");
  assert.equal(after.event_outbox.event_type_counts["deployment.receipt_submitted"], 1);
  assert.equal(after.event_outbox.event_type_counts["deployment.receipt_acknowledged"], 1);
  assert.doesNotMatch(JSON.stringify(after.deployment_receipt_inbox), /Bearer|Cookie|ASHR_API_KEY|X-Amz-Signature|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
  assert.equal(store.exportState().deploymentReceipts.length, 1);
});

test("A3 store invokes a trusted resolver once and projects a hash-valid readback", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  const dashboard = await store.getDashboardSnapshot(source);
  const submitted = await store.submitDeploymentReceipt(receiptInput(dashboard), {
    source,
    idempotencyKey: "authoritative-store-submit"
  });
  const acknowledged = await store.reviewDeploymentReceipt(submitted.receipt_id, {
    action: "acknowledge",
    reason_code: "metadata_complete",
    expected_version: 1
  }, {
    source,
    idempotencyKey: "authoritative-store-review"
  });
  let resolverCalls = 0;
  const resolver = async ({ receipt }) => {
    resolverCalls += 1;
    return authoritativeReadback(receipt);
  };
  const options = {
    source,
    trustedResolver: true,
    principalKind: "service_account",
    resolverIdAlias: "svc-deployment-verifier-store",
    actorHash: "svc_deployment_verifier_hash",
    expectedVersion: acknowledged.version,
    idempotencyKey: "authoritative-store-verify"
  };
  const verified = await store.verifyDeploymentReceiptAuthoritatively(acknowledged.receipt_id, resolver, options);
  assert.equal(verified.production_verified, true);
  assert.equal(verified.verification_status, "verified");
  assert.equal(verified.idempotency.status, "recorded");
  assert.equal(resolverCalls, 1);

  const replay = await store.verifyDeploymentReceiptAuthoritatively(acknowledged.receipt_id, resolver, options);
  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(resolverCalls, 1);

  const after = await store.getDashboardSnapshot(source);
  assert.equal(after.deployment_receipt_inbox.production_verified_count, 1);
  assert.equal(after.deployment_receipt_inbox.authoritative_readback_count, 1);
  assert.equal(after.deployment_acceptance.summary.passed, 8);
  assert.equal(after.deployment_acceptance_projection.summary.projected_passed, 9);
  assert.equal(after.deployment_acceptance_projection.production_accepted, false);
  assert.deepEqual(after.deployment_acceptance_projection.changed_check_ids, ["deployment_health"]);
  assert.equal(store.exportState().deploymentReceipts[0].version, 2);
  assert.equal(store.exportState().deploymentReceiptReadbacks.length, 1);
  assert.equal(after.event_outbox.event_type_counts["deployment.receipt_authoritatively_verified"], 1);

  await assert.rejects(
    () => store.verifyDeploymentReceiptAuthoritatively(acknowledged.receipt_id, async ({ receipt }) => ({
      ...authoritativeReadback(receipt),
      candidate_id: "wrong-candidate"
    }), {
      ...options,
      idempotencyKey: "authoritative-store-invalid"
    }),
    (error) => error instanceof A3StoreValidationError
      && error.statusCode === 502
      && error.error === "authoritative_verifier_invalid"
  );
  assert.equal(store.exportState().deploymentReceiptReadbacks.length, 1);

  await assert.rejects(
    () => store.verifyDeploymentReceiptAuthoritatively(acknowledged.receipt_id, resolver, {
      ...options,
      trustedResolver: false,
      principalKind: "user",
      idempotencyKey: "authoritative-store-untrusted"
    }),
    (error) => error instanceof A3StoreValidationError
      && error.statusCode === 403
      && error.error === "trusted_deployment_verifier_required"
  );
  assert.equal(resolverCalls, 1);
});

test("A3 deployment receipt API enforces submit/review permissions and optimistic concurrency", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  const dashboard = await store.getDashboardSnapshot(source);
  const input = receiptInput(dashboard);
  const { server, url } = await startA3ApiServer({ store, routeAccessMode: "demo_contract" });

  try {
    const initial = await getJson(`${url}/api/a3/deployment/receipts?source=${source}`);
    assert.equal(initial.receipt_count, 0);

    const missingIdempotency = await fetch(`${url}/api/a3/deployment/receipts?source=${source}`, {
      method: "POST",
      headers: demoHeaders("developer"),
      body: JSON.stringify({ source, ...scope, receipt: input })
    });
    assert.equal(missingIdempotency.status, 400);
    assert.equal((await missingIdempotency.json()).request_type, "deployment_receipt_submit");

    const submitResponse = await fetch(`${url}/api/a3/deployment/receipts?source=${source}`, {
      method: "POST",
      headers: { ...demoHeaders("developer"), "idempotency-key": "api-deployment-submit-001" },
      body: JSON.stringify({ source, ...scope, receipt: input })
    });
    assert.equal(submitResponse.status, 201);
    const submitted = await submitResponse.json();
    assert.equal(submitted.status, "submitted");
    assert.equal(submitted.safety.production_verified_by_submission, false);

    const deniedReview = await fetch(`${url}/api/a3/deployment/receipts/${submitted.receipt_id}/review?source=${source}`, {
      method: "POST",
      headers: { ...demoHeaders("developer"), "idempotency-key": "api-deployment-review-denied" },
      body: JSON.stringify({
        source,
        ...scope,
        review: { action: "acknowledge", reason_code: "metadata_complete", expected_version: 1 }
      })
    });
    assert.equal(deniedReview.status, 403);

    const reviewResponse = await fetch(`${url}/api/a3/deployment/receipts/${submitted.receipt_id}/review?source=${source}`, {
      method: "POST",
      headers: { ...demoHeaders("reviewer"), "idempotency-key": "api-deployment-review-001" },
      body: JSON.stringify({
        source,
        ...scope,
        review: { action: "acknowledge", reason_code: "metadata_complete", expected_version: 1 }
      })
    });
    assert.equal(reviewResponse.status, 200);
    const reviewed = await reviewResponse.json();
    assert.equal(reviewed.status, "acknowledged");
    assert.equal(reviewed.version, 2);

    const staleResponse = await fetch(`${url}/api/a3/deployment/receipts/${submitted.receipt_id}/review?source=${source}`, {
      method: "POST",
      headers: { ...demoHeaders("reviewer"), "idempotency-key": "api-deployment-review-stale" },
      body: JSON.stringify({
        source,
        ...scope,
        review: { action: "reject", reason_code: "stale_evidence", expected_version: 1 }
      })
    });
    assert.equal(staleResponse.status, 409);
    assert.equal((await staleResponse.json()).error, "version_conflict");

    const inbox = await getJson(`${url}/api/a3/deployment/receipts?source=${source}`);
    assert.equal(inbox.receipt_count, 1);
    assert.equal(inbox.receipts[0].status, "acknowledged");
    assert.equal(inbox.production_verified_count, 0);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("authoritative verification API is service-account-only and never consumes client verification output", async () => {
  const store = await createFixtureBackedA3Store({ sources: [source] });
  const dashboard = await store.getDashboardSnapshot(source);
  const submitted = await store.submitDeploymentReceipt(receiptInput(dashboard), {
    source,
    idempotencyKey: "internal-api-submit"
  });
  const acknowledged = await store.reviewDeploymentReceipt(submitted.receipt_id, {
    action: "acknowledge",
    reason_code: "metadata_complete",
    expected_version: 1
  }, {
    source,
    idempotencyKey: "internal-api-review"
  });
  let resolverCalls = 0;
  const resolver = async ({ receipt }) => {
    resolverCalls += 1;
    return authoritativeReadback(receipt, { external_readback_id_alias: "internal-api-readback" });
  };

  const { server, url } = await startA3ApiServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal("service_account"),
    resolveAuthoritativeDeploymentReceipt: resolver
  });
  try {
    const response = await fetch(`${url}/internal/a3/deployment/receipts/${submitted.receipt_id}/verify?source=${source}`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "internal-api-verify" },
      body: JSON.stringify({ source, expected_version: acknowledged.version })
    });
    assert.equal(response.status, 200);
    const verified = await response.json();
    assert.equal(verified.production_verified, true);
    assert.equal(verified.safety.client_supplied_verification_result_used, false);
    assert.equal(resolverCalls, 1);

    const injected = await fetch(`${url}/internal/a3/deployment/receipts/${submitted.receipt_id}/verify?source=${source}`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "internal-api-injected" },
      body: JSON.stringify({
        source,
        expected_version: acknowledged.version,
        production_verified: true,
        readback: { verification_status: "verified" }
      })
    });
    assert.equal(injected.status, 400);
    const injectedPayload = await injected.json();
    assert.equal(injectedPayload.error, "client_verification_result_forbidden");
    assert.equal(injectedPayload.safety.client_verification_result_used, false);
    assert.equal(resolverCalls, 1);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  const deniedServer = await startA3ApiServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => trustedPrincipal("owner"),
    resolveAuthoritativeDeploymentReceipt: resolver
  });
  try {
    const denied = await fetch(`${deniedServer.url}/internal/a3/deployment/receipts/${submitted.receipt_id}/verify?source=${source}`, {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": "internal-api-owner-denied" },
      body: JSON.stringify({ source, expected_version: acknowledged.version })
    });
    assert.equal(denied.status, 403);
    assert.equal(resolverCalls, 1);
  } finally {
    await new Promise((resolve) => deniedServer.server.close(resolve));
  }

  const demoServer = await startA3ApiServer({
    store,
    routeAccessMode: "demo_contract",
    resolveAuthoritativeDeploymentReceipt: resolver
  });
  try {
    const forged = await fetch(`${demoServer.url}/internal/a3/deployment/receipts/${submitted.receipt_id}/verify?source=${source}`, {
      method: "POST",
      headers: {
        ...demoHeaders("service_account"),
        "x-a3-service-account": "true",
        "idempotency-key": "internal-api-demo-forged"
      },
      body: JSON.stringify({ source, ...scope, expected_version: acknowledged.version })
    });
    assert.equal(forged.status, 403);
    assert.equal((await forged.json()).error, "trusted_deployment_verifier_required");
    assert.equal(resolverCalls, 1);
  } finally {
    await new Promise((resolve) => demoServer.server.close(resolve));
  }
});

test("A3 SQLite store restores deployment receipt review state after restart", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-deployment-receipts-"));
  const dbPath = join(dir, "a3.sqlite");
  let store;
  try {
    store = await createSqliteA3Store({
      dbPath,
      seed: { snapshot: await loadA3SourceSnapshot(source) }
    });
    const dashboard = await store.getDashboardSnapshot(source);
    const submitted = await store.submitDeploymentReceipt(receiptInput(dashboard), {
      source,
      idempotencyKey: "sqlite-deployment-submit"
    });
    await store.reviewDeploymentReceipt(submitted.receipt_id, {
      action: "acknowledge",
      reason_code: "metadata_complete",
      expected_version: 1
    }, {
      source,
      idempotencyKey: "sqlite-deployment-review"
    });
    await store.verifyDeploymentReceiptAuthoritatively(submitted.receipt_id, async ({ receipt }) => authoritativeReadback(receipt), {
      source,
      trustedResolver: true,
      principalKind: "service_account",
      resolverIdAlias: "svc-deployment-verifier-sqlite",
      expectedVersion: 2,
      idempotencyKey: "sqlite-deployment-authoritative-verify"
    });

    const inspection = store.inspectSqliteState();
    assert.equal(inspection.operational_tables.deployment_receipts, 1);
    assert.equal(inspection.operational_tables.deployment_receipt_readbacks, 1);
    const db = new DatabaseSync(dbPath, { readOnly: true });
    try {
      const row = db.prepare("SELECT status, version, production_verified, evidence_sha256 FROM deployment_receipts LIMIT 1").get();
      assert.equal(row.status, "acknowledged");
      assert.equal(row.version, 2);
      assert.equal(row.production_verified, 0);
      assert.match(row.evidence_sha256, /^sha256:[a-f0-9]{64}$/);
    } finally {
      db.close();
    }

    store.close();
    store = await createSqliteA3Store({ dbPath });
    const restored = await store.listDeploymentReceipts({ source });
    assert.equal(restored.receipt_count, 1);
    assert.equal(restored.receipts[0].status, "acknowledged");
    assert.equal(restored.receipts[0].version, 2);
    assert.equal(restored.production_verified_count, 1);
    assert.equal(restored.authoritative_readback_count, 1);
    assert.equal((await store.getDashboardSnapshot(source)).deployment_acceptance.summary.passed, 8);
    assert.equal((await store.getDashboardSnapshot(source)).deployment_acceptance_projection.summary.projected_passed, 9);
  } finally {
    store?.close?.();
    await rm(dir, { recursive: true, force: true });
  }
});

function receiptInput(dashboard) {
  const expected = dashboard.deployment_handoff.candidate_binding.expected;
  return {
    blocker_id: "deployment_health",
    candidate_id: expected.candidate_sha_alias,
    run_id: expected.run_id,
    evidence_ref: "receipt:deployment-health:20260713-001",
    evidence_sha256: "a".repeat(64),
    evidence_kind: "deployment_health_receipt",
    verifier_class: "deployment_probe",
    captured_at: "2026-07-13T06:00:00.000Z",
    selectors: {
      deployment_id_alias: "deploy-staging-001",
      image_digest: `sha256:${"b".repeat(64)}`,
      health_status: "healthy"
    }
  };
}

function authoritativeReadback(receipt, overrides = {}) {
  return {
    schema_version: A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
    external_readback_id_alias: "deploy-readback-integration-001",
    receipt_id: receipt.receipt_id,
    blocker_id: receipt.blocker_id,
    candidate_id: receipt.candidate_id,
    run_id: receipt.run_id,
    tenant_scope: receipt.tenant_scope,
    evidence_sha256: receipt.evidence_sha256,
    verifier_class: receipt.verifier_class,
    verifier_authority: "a1_a3_deployment_verifier",
    verification_status: "verified",
    reason_code: "all_bindings_verified",
    verified_at: "2026-07-13T07:00:00.000Z",
    attestation_sha256: `sha256:${"d".repeat(64)}`,
    claims: {
      image_config_migration_verified: true,
      health_verified: true,
      network_policy_verified: true,
      tenant_isolation_verified: true
    },
    ...overrides
  };
}

function demoHeaders(role) {
  return {
    "content-type": "application/json",
    "x-a3-role": role,
    "x-a3-organization-id": scope.organization_id,
    "x-a3-tenant-id": scope.tenant_id,
    "x-a3-workspace-id": scope.workspace_id,
    "x-a3-project-id": scope.project_id,
    "x-a3-environment-id": scope.environment_id
  };
}

function trustedPrincipal(role) {
  return {
    trusted: true,
    authenticated: true,
    role,
    actor_hash: `actor_${role}_0123456789abcdef`,
    session: { state: "active" },
    permissions: [...A3_RBAC_ROLES[role]],
    expires_at: "2099-01-01T00:00:00.000Z",
    tenant_scope: scope
  };
}

async function getJson(url) {
  const response = await fetch(url, { headers: demoHeaders("auditor") });
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
