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
  "../../fixtures/a3/p3/a2_multimodal_repeat_stability_round51_7504680.redacted.json",
  import.meta.url
);
const scope = {
  organizationId: "org-repeat",
  tenantId: "tenant-repeat",
  workspaceId: "workspace-repeat",
  projectId: "project-repeat",
  environmentId: "staging"
};
const apiScope = {
  organization_id: scope.organizationId,
  tenant_id: scope.tenantId,
  workspace_id: scope.workspaceId,
  project_id: scope.projectId,
  environment_id: scope.environmentId
};

test("A3 store imports repeat stability with scope, idempotency, audit, dashboard, and report evidence", async () => {
  const evidence = await loadFixture();
  const store = createMemoryA3Store({
    sources: { "api-repeat": snapshot() },
    storageMode: "memory",
    dbReady: false
  });

  await assert.rejects(
    store.importA2MultimodalRepeatStability(evidence, { source: "api-repeat", ...scope }),
    (error) => error instanceof A3StoreValidationError
      && error.details[0].field === "Idempotency-Key"
  );

  const options = {
    source: "api-repeat",
    ...scope,
    enforceScope: true,
    idempotencyKey: "repeat-import-001",
    actorHash: "actor_hash_repeat_ingest",
    importedAt: "2026-07-14T18:30:00.000Z"
  };
  const receipt = await store.importA2MultimodalRepeatStability(evidence, options);
  const replay = await store.importA2MultimodalRepeatStability(evidence, options);
  const projection = await store.getMultimodalRepeatStability(options);
  const dashboard = await store.getDashboardSnapshot("api-repeat", options);
  const report = await store.createShareableReport({
    ...options,
    idempotencyKey: "repeat-report-001",
    createdAt: "2026-07-14T18:31:00.000Z",
    shareToken: "repeat-report-test-token"
  });
  const html = renderShareableReportHtml(report);
  const state = store.exportState();

  assert.equal(receipt.schema_version, "a3.a2_multimodal_repeat_stability_ingest.v1");
  assert.equal(receipt.repeat_count, 3);
  assert.equal(receipt.retained_blocked_count, 3);
  assert.equal(receipt.all_required_units_complete, true);
  assert.equal(receipt.human_review_receipt_count, 0);
  assert.equal(receipt.pending_queue_receipt_count, 1);
  assert.equal(receipt.shared_candidate_verified, false);
  assert.equal(receipt.release_decision_changed, false);
  assert.equal(receipt.idempotency.status, "recorded");
  assert.equal(receipt.event_envelope.payload_inline, false);
  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(projection.status, "blocked_stable_repeat");
  assert.equal(projection.summary.stable_observation, true);
  assert.equal(projection.summary.quality_qualified, false);
  assert.equal(projection.production_ready, false);
  assert.equal(dashboard.multimodal_repeat_stability.status, "blocked_stable_repeat");
  assert.equal(dashboard.multimodal_review_queue.repeat_stability.summary.repeat_count, 3);
  assert.equal(report.multimodal_repeat_stability.status, "blocked_stable_repeat");
  assert.equal(report.multimodal_repeat_stability.summary.quality_qualified, false);
  assert.match(report.markdown_report, /## Multimodal Repeat Stability/);
  assert.match(html, /Multimodal Repeat Stability/);
  assert.match(html, /Complete and stable, but quality is not qualified/);
  assert.doesNotMatch(JSON.stringify(report.payload), /repeat-report-test-token|https?:\/\//);
  assert.doesNotMatch(html, /repeat-report-test-token|https?:\/\//);
  assert.ok(state.auditEvents.some((event) => event.event_type === "a2_multimodal_repeat_stability_imported"));
  assert.ok(state.eventOutbox.some((event) => event.event_type === "a2.multimodal_repeat_stability_imported"));

  const changed = structuredClone(evidence);
  changed.review_collection.note = "Round 51 remains pending after a second metadata-only observation.";
  await assert.rejects(
    store.importA2MultimodalRepeatStability(changed, options),
    (error) => error instanceof A3StoreValidationError && error.statusCode === 409
  );

  await assert.rejects(
    store.getMultimodalRepeatStability({
      ...options,
      tenantId: "tenant-other"
    }),
    (error) => error instanceof A3StoreResourceNotFoundError
  );

  const unsafe = structuredClone(evidence);
  unsafe.review_collection.note = "Inspect https://private.example/reviewer-evidence";
  await assert.rejects(
    store.importA2MultimodalRepeatStability(unsafe, {
      ...options,
      idempotencyKey: "repeat-import-unsafe"
    }),
    (error) => error instanceof A3StoreValidationError
      && error.details.some((detail) => detail.issue === "sensitive_or_external_material_forbidden")
  );
});

test("JSON-file and SQLite stores restore repeat stability without promoting authority", async () => {
  const evidence = await loadFixture();
  const root = await mkdtemp(join(tmpdir(), "a3-repeat-stability-"));
  const filePath = join(root, "a3-store.json");
  const dbPath = join(root, "a3.sqlite");
  let sqliteStore;
  let reopenedSqlite;
  try {
    const seed = { sources: { "api-repeat": snapshot() } };
    const fileStore = await createFileBackedA3Store({ filePath, seed });
    await fileStore.importA2MultimodalRepeatStability(evidence, {
      source: "api-repeat",
      ...scope,
      enforceScope: true,
      idempotencyKey: "repeat-file-001",
      importedAt: "2026-07-14T18:32:00.000Z"
    });
    const reopenedFile = await createFileBackedA3Store({ filePath });
    const fileProjection = await reopenedFile.getMultimodalRepeatStability({
      source: "api-repeat",
      ...scope,
      enforceScope: true
    });
    assert.equal(fileProjection.status, "blocked_stable_repeat");
    assert.equal(fileProjection.summary.repeat_count, 3);
    assert.equal(fileProjection.authority_boundary.release_authority, false);

    sqliteStore = await createSqliteA3Store({ dbPath, seed });
    await sqliteStore.importA2MultimodalRepeatStability(evidence, {
      source: "api-repeat",
      ...scope,
      enforceScope: true,
      idempotencyKey: "repeat-sqlite-001",
      importedAt: "2026-07-14T18:33:00.000Z"
    });
    sqliteStore.close();
    sqliteStore = null;

    reopenedSqlite = await createSqliteA3Store({ dbPath });
    const sqliteProjection = await reopenedSqlite.getMultimodalRepeatStability({
      source: "api-repeat",
      ...scope,
      enforceScope: true
    });
    const state = reopenedSqlite.exportState();
    assert.equal(sqliteProjection.status, "blocked_stable_repeat");
    assert.equal(sqliteProjection.summary.all_required_units_complete, true);
    assert.equal(sqliteProjection.summary.quality_qualified, false);
    assert.equal(state.sources["api-repeat"].a2MultimodalRepeatStability.source_commit_alias, "7504680");
  } finally {
    sqliteStore?.close();
    reopenedSqlite?.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("A3 API protects repeat stability import/read and hides unsafe or foreign-tenant evidence", async () => {
  const evidence = await loadFixture();
  const store = createMemoryA3Store({ sources: { "api-repeat": snapshot() } });
  const { server, url } = await startA3ApiServer({
    store,
    routeAccessMode: "demo_contract",
    now: "2026-07-14T18:34:00.000Z"
  });
  try {
    const body = JSON.stringify({
      source: "api-repeat",
      ...apiScope,
      stability_evidence: evidence
    });
    const denied = await fetch(`${url}/api/a3/import/a2-multimodal-repeat-stability`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "repeat-api-denied",
        "x-a3-role": "viewer"
      },
      body
    });
    assert.equal(denied.status, 403);
    assert.equal((await denied.json()).required_permission, "project:ingest");

    const imported = await fetch(`${url}/api/a3/import/a2-multimodal-repeat-stability`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "repeat-api-001",
        "x-a3-role": "service_account"
      },
      body
    });
    assert.equal(imported.status, 201);
    const receipt = await imported.json();
    assert.equal(receipt.repeat_count, 3);
    assert.equal(receipt.idempotency.status, "recorded");
    assert.equal(receipt.release_decision_changed, false);

    const query = new URLSearchParams({ source: "api-repeat", ...apiScope });
    const viewerRead = await fetch(`${url}/api/a3/review/multimodal-repeat-stability?${query}`, {
      headers: { "x-a3-role": "viewer" }
    });
    assert.equal(viewerRead.status, 403);

    const reviewerRead = await fetch(`${url}/api/a3/review/multimodal-repeat-stability?${query}`, {
      headers: { "x-a3-role": "reviewer" }
    });
    assert.equal(reviewerRead.status, 200);
    const projection = await reviewerRead.json();
    assert.equal(projection.status, "blocked_stable_repeat");
    assert.equal(projection.human_review.authoritative_human_disposition_recorded, false);
    assert.equal(projection.candidate_binding.verified, false);

    query.set("tenant_id", "tenant-other");
    const foreign = await fetch(`${url}/api/a3/review/multimodal-repeat-stability?${query}`, {
      headers: { "x-a3-role": "reviewer" }
    });
    assert.equal(foreign.status, 404);
    assert.doesNotMatch(await foreign.text(), /qwen-vl|dashscope|sha256:/);

    const unsafe = structuredClone(evidence);
    unsafe.review_collection.note = "Bearer abcdefghijklmnopqrstuvwxyz";
    const unsafeResponse = await fetch(`${url}/api/a3/import/a2-multimodal-repeat-stability`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "repeat-api-unsafe",
        "x-a3-role": "service_account"
      },
      body: JSON.stringify({
        source: "api-repeat",
        ...apiScope,
        stability_evidence: unsafe
      })
    });
    assert.equal(unsafeResponse.status, 400);
    assert.doesNotMatch(await unsafeResponse.text(), /abcdefghijklmnopqrstuvwxyz|Bearer/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

function snapshot() {
  return {
    source: "api-repeat",
    source_label: "Repeat stability API ingest",
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
