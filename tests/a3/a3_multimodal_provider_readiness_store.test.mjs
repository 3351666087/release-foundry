import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { renderShareableReportHtml } from "../../services/report/a3_shareable_report.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";
import {
  A3StoreResourceNotFoundError,
  A3StoreValidationError,
  createFileBackedA3Store,
  createMemoryA3Store
} from "../../services/report/a3_store.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_provider_readiness_round51_7504680.redacted.json",
  import.meta.url
);
const scope = {
  organizationId: "org-provider",
  tenantId: "tenant-provider",
  workspaceId: "workspace-provider",
  projectId: "project-provider",
  environmentId: "staging"
};
const apiScope = {
  organization_id: scope.organizationId,
  tenant_id: scope.tenantId,
  workspace_id: scope.workspaceId,
  project_id: scope.projectId,
  environment_id: scope.environmentId
};

test("A3 store imports provider readiness with idempotency, audit, usage, and tenant isolation", async () => {
  const evidence = await loadFixture();
  const store = createMemoryA3Store({ sources: { "api-provider": snapshot() } });

  await assert.rejects(
    store.importA2MultimodalProviderReadiness(evidence, { source: "api-provider", ...scope }),
    (error) => error instanceof A3StoreValidationError && error.details[0].field === "Idempotency-Key"
  );

  const options = {
    source: "api-provider",
    ...scope,
    enforceScope: true,
    idempotencyKey: "provider-import-001",
    actorHash: "actor_hash_provider_ingest",
    importedAt: "2026-07-14T19:00:00.000Z"
  };
  const receipt = await store.importA2MultimodalProviderReadiness(evidence, options);
  const replay = await store.importA2MultimodalProviderReadiness(evidence, options);
  const projection = await store.getMultimodalProviderReadiness(options);
  const dashboard = await store.getDashboardSnapshot("api-provider", options);
  const report = await store.createShareableReport({
    ...options,
    idempotencyKey: "provider-report-001",
    createdAt: "2026-07-14T19:00:30.000Z",
    shareToken: "provider-report-test-token"
  });
  const html = renderShareableReportHtml(report);
  const state = store.exportState();

  assert.equal(receipt.schema_version, "a3.a2_multimodal_provider_readiness_ingest.v1");
  assert.equal(receipt.provider_count, 2);
  assert.equal(receipt.attempted_count, 30);
  assert.equal(receipt.completed_count, 1);
  assert.equal(receipt.failed_count, 29);
  assert.equal(receipt.timeout_case_count, 29);
  assert.equal(receipt.eligible_count, 0);
  assert.equal(receipt.completed_profile_count, 0);
  assert.equal(receipt.valid_structured_profile_count, 0);
  assert.equal(receipt.operational_health_verified, false);
  assert.equal(receipt.release_decision_changed, false);
  assert.equal(receipt.idempotency.status, "recorded");
  assert.equal(receipt.event_envelope.payload_inline, false);
  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(projection.status, "blocked_provider_readiness");
  assert.equal(projection.summary.quality_comparison_performed, false);
  assert.equal(projection.authority_boundary.routing_or_capacity_authority, "A1");
  assert.equal(projection.authority_boundary.evaluation_and_qualification_authority, "A2");
  assert.equal(dashboard.multimodal_provider_readiness.status, "blocked_provider_readiness");
  assert.equal(dashboard.multimodal_review_queue.provider_readiness.summary.eligible_count, 0);
  assert.equal(report.multimodal_provider_readiness.status, "blocked_provider_readiness");
  assert.equal(report.multimodal_provider_readiness.summary.operational_health_verified, false);
  assert.match(report.markdown_report, /## Multimodal Provider Readiness/);
  assert.match(html, /Multimodal Provider Readiness/);
  assert.match(html, /availability is insufficient/);
  assert.doesNotMatch(JSON.stringify(report.payload), /provider-report-test-token|https?:\/\//);
  assert.doesNotMatch(html, /provider-report-test-token|https?:\/\//);
  assert.ok(state.auditEvents.some((event) => event.event_type === "a2_multimodal_provider_readiness_imported"));
  assert.ok(state.eventOutbox.some((event) => event.event_type === "a2.multimodal_provider_readiness_imported"));
  assert.ok(state.eventOutbox.some((event) => event.usage_meter?.meter === "a2_multimodal_provider_readiness_imports"));

  const changed = structuredClone(evidence);
  changed.latency_probe.timeout_seconds = 91;
  await assert.rejects(
    store.importA2MultimodalProviderReadiness(changed, options),
    (error) => error instanceof A3StoreValidationError && error.statusCode === 409
  );

  await assert.rejects(
    store.getMultimodalProviderReadiness({ ...options, tenantId: "tenant-other" }),
    (error) => error instanceof A3StoreResourceNotFoundError
  );
});

test("JSON-file and SQLite stores restore diagnostic evidence without promoting health or release authority", async () => {
  const evidence = await loadFixture();
  const root = await mkdtemp(join(tmpdir(), "a3-provider-readiness-"));
  const filePath = join(root, "a3-store.json");
  const dbPath = join(root, "a3.sqlite");
  let sqliteStore;
  let reopenedSqlite;
  try {
    const seed = { sources: { "api-provider": snapshot() } };
    const fileStore = await createFileBackedA3Store({ filePath, seed });
    await fileStore.importA2MultimodalProviderReadiness(evidence, {
      source: "api-provider",
      ...scope,
      enforceScope: true,
      idempotencyKey: "provider-file-001",
      importedAt: "2026-07-14T19:01:00.000Z"
    });
    const reopenedFile = await createFileBackedA3Store({ filePath });
    const fileProjection = await reopenedFile.getMultimodalProviderReadiness({
      source: "api-provider",
      ...scope,
      enforceScope: true
    });
    assert.equal(fileProjection.status, "blocked_provider_readiness");
    assert.equal(fileProjection.summary.eligible_count, 0);
    assert.equal(fileProjection.summary.operational_health_verified, false);

    sqliteStore = await createSqliteA3Store({ dbPath, seed });
    await sqliteStore.importA2MultimodalProviderReadiness(evidence, {
      source: "api-provider",
      ...scope,
      enforceScope: true,
      idempotencyKey: "provider-sqlite-001",
      importedAt: "2026-07-14T19:02:00.000Z"
    });
    sqliteStore.close();
    sqliteStore = null;

    reopenedSqlite = await createSqliteA3Store({ dbPath });
    const sqliteProjection = await reopenedSqlite.getMultimodalProviderReadiness({
      source: "api-provider",
      ...scope,
      enforceScope: true
    });
    const state = reopenedSqlite.exportState();
    assert.equal(sqliteProjection.status, "blocked_provider_readiness");
    assert.equal(sqliteProjection.summary.failed_count, 29);
    assert.equal(sqliteProjection.release_authority, false);
    assert.equal(state.sources["api-provider"].a2MultimodalProviderReadiness.source_commit_alias, "7504680");
  } finally {
    sqliteStore?.close();
    reopenedSqlite?.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("A3 API protects provider readiness import/read and redacts unsafe or cross-tenant responses", async () => {
  const evidence = await loadFixture();
  const store = createMemoryA3Store({ sources: { "api-provider": snapshot() } });
  const { server, url } = await startA3ApiServer({
    store,
    routeAccessMode: "demo_contract",
    now: "2026-07-14T19:03:00.000Z"
  });
  try {
    const body = JSON.stringify({
      source: "api-provider",
      ...apiScope,
      provider_readiness_evidence: evidence
    });
    const denied = await fetch(`${url}/api/a3/import/a2-multimodal-provider-readiness`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "provider-api-denied",
        "x-a3-role": "viewer"
      },
      body
    });
    assert.equal(denied.status, 403);
    assert.equal((await denied.json()).required_permission, "project:ingest");

    const imported = await fetch(`${url}/api/a3/import/a2-multimodal-provider-readiness`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "provider-api-001",
        "x-a3-role": "service_account"
      },
      body
    });
    assert.equal(imported.status, 201);
    assert.equal((await imported.json()).eligible_count, 0);

    const query = new URLSearchParams({ source: "api-provider", ...apiScope });
    const viewerRead = await fetch(`${url}/api/a3/providers/multimodal-readiness?${query}`, {
      headers: { "x-a3-role": "viewer" }
    });
    assert.equal(viewerRead.status, 403);

    const reviewerRead = await fetch(`${url}/api/a3/providers/multimodal-readiness?${query}`, {
      headers: { "x-a3-role": "reviewer" }
    });
    assert.equal(reviewerRead.status, 200);
    const projection = await reviewerRead.json();
    assert.equal(projection.status, "blocked_provider_readiness");
    assert.equal(projection.summary.operational_health_verified, false);
    assert.equal(projection.authority_boundary.release_authority, false);

    query.set("tenant_id", "tenant-other");
    const foreign = await fetch(`${url}/api/a3/providers/multimodal-readiness?${query}`, {
      headers: { "x-a3-role": "reviewer" }
    });
    assert.equal(foreign.status, 404);
    assert.doesNotMatch(await foreign.text(), /qwen|llava|sha256:/i);

    const unsafe = structuredClone(evidence);
    unsafe.latency_probe.diagnosis[0] = "https://private.example/provider-diagnostic";
    const unsafeResponse = await fetch(`${url}/api/a3/import/a2-multimodal-provider-readiness`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "provider-api-unsafe",
        "x-a3-role": "service_account"
      },
      body: JSON.stringify({
        source: "api-provider",
        ...apiScope,
        provider_readiness_evidence: unsafe
      })
    });
    assert.equal(unsafeResponse.status, 400);
    assert.doesNotMatch(await unsafeResponse.text(), /private\.example|provider-diagnostic|https:/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

function snapshot() {
  return {
    source: "api-provider",
    source_label: "Provider readiness API ingest",
    organizationId: scope.organizationId,
    tenantId: scope.tenantId,
    workspaceId: scope.workspaceId,
    projectId: scope.projectId,
    environmentId: scope.environmentId,
    runFixture: {},
    gradeFixture: {}
  };
}

async function loadFixture() {
  return JSON.parse(await readFile(fixtureUrl, "utf8"));
}
