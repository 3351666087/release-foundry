import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  A3StoreResourceNotFoundError,
  createFileBackedA3Store,
  createMemoryA3Store
} from "../../services/report/a3_store.mjs";
import { createSqliteA3Store } from "../../services/report/a3_sqlite_store.mjs";
import { renderShareableReportHtml } from "../../services/report/a3_shareable_report.mjs";
import { buildA3SqlMigrationPlan } from "../../services/report/a3_sql_migrations.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_three_way_v2_bb3bcfe_sample.redacted.json",
  import.meta.url
);
const scope = {
  organizationId: "org-evidence-store",
  tenantId: "tenant-evidence-store",
  workspaceId: "workspace-evidence-store",
  projectId: "project-evidence-store",
  environmentId: "staging"
};
const reviewer = "reviewer_hash_store_owner";

test("A3 store records evidence requests with idempotency, audit, outbox, dashboard, and report projections", async () => {
  const store = createMemoryA3Store({
    sources: { "api-ingest": snapshot() },
    storageMode: "memory"
  });
  const result = await completeEvidenceRequest(store, "memory");
  const replay = await store.createMultimodalReviewEvidenceRequest(result.queueId, requestInput(), {
    ...baseOptions("2026-07-14T20:01:00.000Z"),
    idempotencyKey: "memory-request-create"
  });
  const dashboard = await store.getDashboardSnapshot("api-ingest", baseOptions("2026-07-14T20:05:00.000Z"));
  const report = await store.createShareableReport({
    ...baseOptions("2026-07-14T20:06:00.000Z"),
    createdAt: "2026-07-14T20:06:00.000Z",
    expiresAt: "2026-07-15T20:06:00.000Z",
    idempotencyKey: "memory-evidence-report",
    shareToken: "local-evidence-report-token",
    title: "Evidence request audit"
  });
  const state = store.exportState();
  const hostedHtml = renderShareableReportHtml(report);

  assert.equal(replay.idempotency.status, "duplicate_replay");
  assert.equal(dashboard.multimodal_review_queue.summary.evidence_request_accepted_count, 1);
  assert.equal(dashboard.multimodal_review_queue.items[0].evidence_requests[0].status, "accepted");
  assert.equal(dashboard.multimodal_review_queue.items[0].evidence_requests[0].authority_boundary.release_authority, false);
  assert.equal(dashboard.usage_ledger.meters.find((meter) => meter.meter === "multimodal_review_evidence_request_actions").quantity, 3);
  assert.equal(report.multimodal_review_queue.summary.evidence_request_accepted_count, 1);
  assert.match(report.markdown_report, /Evidence requests accepted: 1/);
  assert.match(hostedHtml, /Multimodal Review Evidence Requests/);
  assert.match(hostedHtml, /a1_run_trace:sha256:aaaaaaaaaa/);
  assert.match(hostedHtml, /Evidence acceptance is not a human disposition/);
  assert.equal(state.multimodalReviewEvidenceRequestEvents.length, 3);
  assert.equal(state.multimodalReviewEvidenceRequestEvents[1].evidence_refs.length, 1);
  assert.equal(state.multimodalReviewEvidenceRequestEvents[1].evidence_refs[0].evidence_hash, hash("a"));
  assert.ok(state.auditEvents.some((event) => event.event_type === "multimodal_review_evidence_request_accepted"));
  assert.ok(state.eventOutbox.some((event) => event.event_type === "review.multimodal_evidence_request.accepted"));
  assert.doesNotMatch(JSON.stringify(state.multimodalReviewEvidenceRequestEvents), /local-evidence-report-token|https?:\/\/|Bearer\s|Cookie:/i);
  assert.doesNotMatch(hostedHtml, /local-evidence-report-token|https?:\/\/|Bearer\s|Cookie:/i);

  await assert.rejects(
    store.listMultimodalReviewEvidenceRequests(result.queueId, {
      ...baseOptions("2026-07-14T20:05:00.000Z"),
      tenantId: "tenant-foreign"
    }),
    (error) => error instanceof A3StoreResourceNotFoundError
  );
});

test("JSON file store restores accepted evidence-request history after restart", async () => {
  const root = await mkdtemp(join(tmpdir(), "a3-evidence-json-"));
  const filePath = join(root, "a3-store.json");
  try {
    const first = await createFileBackedA3Store({
      filePath,
      seed: { sources: { "api-ingest": snapshot() } }
    });
    const completed = await completeEvidenceRequest(first, "json");
    const reopened = await createFileBackedA3Store({ filePath });
    const listing = await reopened.listMultimodalReviewEvidenceRequests(
      completed.queueId,
      baseOptions("2026-07-14T20:05:00.000Z")
    );
    assert.equal(listing.summary.accepted_count, 1);
    assert.equal(listing.requests[0].event_count, 3);
    assert.equal(listing.requests[0].integrity.status, "passed");
    assert.equal(reopened.exportState().multimodalReviewEvidenceRequestEvents.length, 3);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("SQLite persists evidence-request event rows and restores them across restart", async () => {
  const root = await mkdtemp(join(tmpdir(), "a3-evidence-sqlite-"));
  const dbPath = join(root, "a3.sqlite");
  let first;
  let reopened;
  try {
    first = await createSqliteA3Store({
      dbPath,
      seed: { sources: { "api-ingest": snapshot() } }
    });
    const completed = await completeEvidenceRequest(first, "sqlite");
    const firstInspection = first.inspectSqliteState();
    assert.equal(firstInspection.operational_tables.multimodal_review_evidence_request_events, 3);
    first.close();
    first = null;

    reopened = await createSqliteA3Store({ dbPath });
    const listing = await reopened.listMultimodalReviewEvidenceRequests(
      completed.queueId,
      baseOptions("2026-07-14T20:05:00.000Z")
    );
    const inspection = reopened.inspectSqliteState();
    assert.equal(listing.requests[0].status, "accepted");
    assert.equal(listing.requests[0].version, 3);
    assert.equal(listing.requests[0].authority_boundary.authoritative_human_disposition_recorded, false);
    assert.equal(inspection.operational_tables.multimodal_review_evidence_request_events, 3);
    assert.equal(inspection.safety.state_payload_secret_scan.api_key_assignment_found, false);
    assert.equal(inspection.safety.state_payload_secret_scan.raw_share_token_hint_found, false);
  } finally {
    first?.close();
    reopened?.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("PostgreSQL contract forces five-level RLS for evidence-request events", () => {
  const postgres = buildA3SqlMigrationPlan({ dialect: "postgres" });
  const create = postgres.statements.find((item) => item.id === "023_multimodal_review_evidence_request_events");
  const hardening = postgres.statements.find((item) => item.id === "024_multimodal_review_evidence_request_scope_hardening");
  assert.ok(create.tables.includes("multimodal_review_evidence_request_events"));
  assert.match(create.sql, /required_evidence_kinds JSONB NOT NULL/);
  assert.match(create.sql, /evidence_refs JSONB NOT NULL/);
  assert.match(create.sql, /request_id, version/);
  assert.match(hardening.sql, /ENABLE ROW LEVEL SECURITY/);
  assert.match(hardening.sql, /FORCE ROW LEVEL SECURITY/);
  for (const setting of [
    "app.a3_organization_id",
    "app.a3_tenant_id",
    "app.a3_workspace_id",
    "app.a3_project_id",
    "app.a3_environment_id"
  ]) assert.match(hardening.sql, new RegExp(setting.replaceAll(".", "\\.")));
});

async function completeEvidenceRequest(store, prefix) {
  const comparison = JSON.parse(await readFile(fixtureUrl, "utf8"));
  await store.importA2MultimodalComparison(comparison, {
    ...baseOptions("2026-07-14T20:00:00.000Z"),
    idempotencyKey: `${prefix}-comparison-import`
  });
  const queue = await store.getMultimodalReviewQueue(baseOptions("2026-07-14T20:00:30.000Z"));
  const queueId = queue.items[0].queue_id;
  await store.mutateMultimodalReviewAssignment(queueId, {
    action: "claim",
    expected_version: 0,
    lease_seconds: 3600
  }, {
    ...baseOptions("2026-07-14T20:00:30.000Z"),
    idempotencyKey: `${prefix}-assignment-claim`,
    actorHash: reviewer,
    actorRole: "reviewer"
  });
  const created = await store.createMultimodalReviewEvidenceRequest(queueId, requestInput(), {
    ...baseOptions("2026-07-14T20:01:00.000Z"),
    idempotencyKey: `${prefix}-request-create`,
    actorHash: reviewer,
    actorRole: "reviewer"
  });
  await store.submitMultimodalReviewEvidenceRequest(queueId, created.request_id, {
    expected_version: 1,
    owner_lane: "execution",
    evidence_refs: [{
      kind: "a1_run_trace",
      evidence_hash: hash("a"),
      binding_hash: hash("b")
    }],
    reason_code: "trace_hash_submitted"
  }, {
    ...baseOptions("2026-07-14T20:02:00.000Z"),
    idempotencyKey: `${prefix}-request-submit`,
    actorHash: "service_account_hash_store",
    actorRole: "service_account"
  });
  const accepted = await store.reviewMultimodalReviewEvidenceRequest(queueId, created.request_id, {
    expected_version: 2,
    action: "accept",
    reason_code: "trace_hash_verified"
  }, {
    ...baseOptions("2026-07-14T20:03:00.000Z"),
    idempotencyKey: `${prefix}-request-accept`,
    actorHash: reviewer,
    actorRole: "reviewer"
  });
  assert.equal(accepted.status, "accepted");
  assert.equal(accepted.release_decision_changed, false);
  return { queueId, requestId: created.request_id };
}

function requestInput() {
  return {
    expected_version: 0,
    owner_lane: "execution",
    required_evidence_kinds: ["a1_run_trace"],
    due_at: "2026-07-15T20:00:00.000Z",
    reason_code: "trace_hash_required"
  };
}

function baseOptions(now) {
  return {
    source: "api-ingest",
    ...scope,
    enforceScope: true,
    now,
    importedAt: now
  };
}

function snapshot() {
  return {
    source: "api-ingest",
    source_label: "API ingest",
    ...scope,
    runFixture: {},
    gradeFixture: {}
  };
}

function hash(character) {
  return `sha256:${character.repeat(64)}`;
}
