import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  A3StoreResourceNotFoundError,
  A3StoreValidationError,
  createMemoryA3Store
} from "../../services/report/a3_store.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_6673310_sample.redacted.json",
  import.meta.url
);
const threeWayFixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_three_way_v2_bb3bcfe_sample.redacted.json",
  import.meta.url
);
const scope = {
  organizationId: "org-mm",
  tenantId: "tenant-mm",
  workspaceId: "workspace-mm",
  projectId: "project-mm",
  environmentId: "environment-mm"
};

test("A3 store imports one tenant-scoped A2 multimodal comparison with idempotency, audit, and outbox evidence", async () => {
  const comparison = await loadFixture();
  const store = createMemoryA3Store({
    sources: { "api-ingest": snapshot() },
    storageMode: "memory",
    dbReady: false
  });

  await assert.rejects(
    store.importA2MultimodalComparison(comparison, { source: "api-ingest", ...scope }),
    (error) => error instanceof A3StoreValidationError && error.details[0].field === "Idempotency-Key"
  );

  const options = {
    source: "api-ingest",
    ...scope,
    enforceScope: true,
    idempotencyKey: "mm-import-001",
    actorHash: "actor_hash_review_service",
    importedAt: "2026-07-13T14:00:00.000Z"
  };
  const receipt = await store.importA2MultimodalComparison(comparison, options);
  const replay = await store.importA2MultimodalComparison(comparison, options);
  const queue = await store.getMultimodalReviewQueue(options);
  const queueId = queue.items[0].queue_id;
  const assignment = await store.mutateMultimodalReviewAssignment(queueId, {
    action: "claim",
    expected_version: 0,
    lease_seconds: 300
  }, {
    ...options,
    idempotencyKey: "mm-assignment-001",
    actorHash: "reviewer_hash_store",
    actorRole: "reviewer",
    now: "2026-07-13T14:01:00.000Z"
  });
  const assignedQueue = await store.getMultimodalReviewQueue({
    ...options,
    now: "2026-07-13T14:01:01.000Z"
  });
  const dashboard = await store.getDashboardSnapshot("api-ingest", options);
  const report = await store.createShareableReport({
    source: "api-ingest",
    ...scope,
    enforceScope: true,
    idempotencyKey: "mm-report-001",
    title: "Multimodal review evidence",
    createdAt: "2026-07-13T14:02:00.000Z",
    expiresAt: "2026-07-14T14:02:00.000Z",
    shareToken: "local-test-share-token-mm-001"
  });
  const state = store.exportState();

  assert.equal(receipt.schema_version, "a3.a2_multimodal_comparison_ingest.v1");
  assert.equal(receipt.comparison_count, 2);
  assert.equal(receipt.review_required_count, 1);
  assert.equal(receipt.upstream_release_authority, false);
  assert.equal(receipt.release_decision_changed, false);
  assert.equal(receipt.idempotency.status, "recorded");
  assert.equal(receipt.event_envelope.payload_inline, false);
  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(queue.status, "human_review_required");
  assert.equal(queue.items[0].release_authority, false);
  assert.equal(assignment.schema_version, "a3.multimodal_review_assignment_receipt.v1");
  assert.equal(assignment.status, "claimed");
  assert.equal(assignment.version, 1);
  assert.equal(assignment.release_decision_changed, false);
  assert.equal(assignedQueue.items[0].operational_state.status, "claimed");
  assert.equal(assignedQueue.summary.assignment_active_count, 1);
  assert.equal(dashboard.multimodal_review_queue.summary.review_required_count, 1);
  assert.equal(report.multimodal_review_queue.available, true);
  assert.equal(report.multimodal_review_queue.summary.semantic_disagreement, 1);
  assert.equal(report.multimodal_review_queue.summary.assignment_active_count, 1);
  assert.equal(report.multimodal_review_queue.items[0].assignment_status, "claimed");
  assert.equal(report.multimodal_review_queue.items[0].assignment_version, 1);
  assert.equal(report.multimodal_review_queue.authority_boundary.can_change_release_decision, false);
  assert.match(report.markdown_report, /## Multimodal Disagreement Review/);
  assert.match(report.markdown_report, /Actively assigned: 1/);
  assert.match(report.markdown_report, /assignment claimed v1/);
  assert.match(report.markdown_report, /Can change release decision: no/);
  assert.doesNotMatch(JSON.stringify(report.multimodal_review_queue), /local-test-share-token|https?:\/\//);
  assert.ok(state.auditEvents.some((item) => item.event_type === "a2_multimodal_comparison_imported"));
  assert.equal(state.auditEvents.at(-1).event_type, "multimodal_review_assignment_claimed");
  const importEvent = state.eventOutbox.find((item) => item.event_type === "a2.multimodal_comparison_imported");
  assert.ok(importEvent);
  assert.equal(importEvent.safety.metadata_only, true);
  assert.equal(state.multimodalReviewAssignmentEvents.length, 1);
  assert.equal(state.multimodalReviewAssignmentEvents[0].a2_decision_recomputed, false);
  assert.ok(state.eventOutbox.some((item) => item.event_type === "review.multimodal_assignment.claimed"));

  const changed = structuredClone(comparison);
  changed.left_evidence_hash = hash("a");
  await assert.rejects(
    store.importA2MultimodalComparison(changed, options),
    (error) => error instanceof A3StoreValidationError && error.statusCode === 409
  );

  await assert.rejects(
    store.getMultimodalReviewQueue({
      source: "api-ingest",
      ...scope,
      tenantId: "tenant-other",
      enforceScope: true
    }),
    (error) => error instanceof A3StoreResourceNotFoundError
  );
});

test("SQLite restores the imported A2 three-way review queue without promoting release authority", async () => {
  const root = await mkdtemp(join(tmpdir(), "a3-mm-review-"));
  const dbPath = join(root, "a3.sqlite");
  const comparison = await loadThreeWayFixture();
  let store;
  let reopened;
  try {
    store = await createSqliteA3Store({
      dbPath,
      seed: { sources: { "api-ingest": snapshot() } }
    });
    await store.importA2MultimodalComparison(comparison, {
      source: "api-ingest",
      ...scope,
      enforceScope: true,
      idempotencyKey: "mm-sqlite-001",
      importedAt: "2026-07-13T14:05:00.000Z"
    });
    const importedQueue = await store.getMultimodalReviewQueue({
      source: "api-ingest",
      ...scope,
      enforceScope: true,
      now: "2026-07-13T14:05:01.000Z"
    });
    await store.mutateMultimodalReviewAssignment(importedQueue.items[0].queue_id, {
      action: "claim",
      expected_version: 0,
      lease_seconds: 300
    }, {
      source: "api-ingest",
      ...scope,
      enforceScope: true,
      idempotencyKey: "mm-sqlite-assignment-001",
      actorHash: "reviewer_hash_sqlite",
      actorRole: "reviewer",
      now: "2026-07-13T14:05:02.000Z"
    });
    store.close();
    store = null;

    reopened = await createSqliteA3Store({ dbPath });
    const queue = await reopened.getMultimodalReviewQueue({
      source: "api-ingest",
      ...scope,
      enforceScope: true,
      now: "2026-07-13T14:05:03.000Z"
    });
    const state = reopened.exportState();
    const inspection = reopened.inspectSqliteState();

    assert.equal(queue.available, true);
    assert.equal(queue.summary.review_required_count, 1);
    assert.equal(queue.provider_set.provider_count, 3);
    assert.equal(queue.items[0].providers.length, 3);
    assert.equal(queue.authority_boundary.can_change_release_decision, false);
    assert.equal(queue.items[0].operational_state.status, "claimed");
    assert.equal(queue.summary.assignment_active_count, 1);
    assert.equal(inspection.operational_tables.multimodal_review_assignment_events, 1);
    assert.equal(state.sources["api-ingest"].a2MultimodalComparison.schema_version, "a2.multimodal_three_way_comparison.v2");
  } finally {
    store?.close();
    reopened?.close();
    await rm(root, { recursive: true, force: true });
  }
});

function snapshot() {
  return {
    source: "api-ingest",
    source_label: "API Ingest",
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

async function loadThreeWayFixture() {
  return JSON.parse(await readFile(threeWayFixtureUrl, "utf8"));
}

function hash(character) {
  return `sha256:${character.repeat(64)}`;
}
