import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json",
  import.meta.url
);
const scope = {
  organization_id: "org-api-mm",
  tenant_id: "tenant-api-mm",
  workspace_id: "workspace-api-mm",
  project_id: "project-api-mm",
  environment_id: "environment-api-mm"
};

test("A3 API exposes the peer calibration queue and a protected tenant-scoped multimodal import", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["p3-media"] });
  const serverNow = "2026-07-14T09:30:00.000Z";
  const { server, url } = await startA3ApiServer({ store, routeAccessMode: "demo_contract", now: serverNow });
  try {
    const peerQueueResponse = await fetch(`${url}/api/a3/review/multimodal-queue?source=p3-media`, {
      headers: { "x-a3-role": "reviewer" }
    });
    assert.equal(peerQueueResponse.status, 200);
    const peerQueue = await peerQueueResponse.json();
    assert.equal(peerQueue.status, "human_review_required");
    assert.equal(peerQueue.source_commit_alias, "564d4b0");
    assert.equal(peerQueue.source_contract, "a2.multimodal_cross_provider_comparison.v3");
    assert.equal(peerQueue.summary.internally_unstable, 2);
    assert.equal(peerQueue.capability_state, "peer_branch_contract_not_merged");
    assert.equal(peerQueue.authority_boundary.can_change_release_decision, false);

    const comparison = JSON.parse(await readFile(fixtureUrl, "utf8"));
    const body = JSON.stringify({
      source: "api-ingest",
      ...scope,
      comparison,
      imported_at: "2000-01-01T00:00:00.000Z",
      idempotency_key: "body-only-key-must-not-authorize"
    });
    const denied = await fetch(`${url}/api/a3/import/a2-multimodal-comparison`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "mm-api-denied-001",
        "x-a3-role": "viewer"
      },
      body
    });
    assert.equal(denied.status, 403);
    const deniedPayload = await denied.json();
    assert.equal(deniedPayload.required_permission, "project:ingest");
    assert.equal(deniedPayload.safety.raw_request_body_echoed, false);

    const missingHeader = await fetch(`${url}/api/a3/import/a2-multimodal-comparison`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-a3-role": "service_account"
      },
      body
    });
    assert.equal(missingHeader.status, 400);
    assert.doesNotMatch(await missingHeader.text(), /body-only-key|2000-01-01/);

    const imported = await fetch(`${url}/api/a3/import/a2-multimodal-comparison`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "mm-api-import-001",
        "x-a3-role": "service_account"
      },
      body
    });
    assert.equal(imported.status, 201);
    const receipt = await imported.json();
    assert.equal(receipt.review_required_count, 4);
    assert.equal(receipt.imported_at, serverNow);
    assert.equal(receipt.event_envelope.payload_inline, false);
    assert.equal(receipt.release_decision_changed, false);

    const query = new URLSearchParams({ source: "api-ingest", ...scope, role: "reviewer" });
    const queueResponse = await fetch(`${url}/api/a3/review/multimodal-queue?${query}`);
    assert.equal(queueResponse.status, 200);
    const queue = await queueResponse.json();
    assert.equal(queue.ingest_mode, "tenant_scoped_api");
    assert.equal(queue.summary.review_required_count, 4);
    assert.deepEqual(queue.tenant_scope, scope);
    assert.equal(queue.authority_boundary.candidate_binding_verified, false);

    const queueId = queue.items[0].queue_id;
    const assignmentUrl = `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/assignment?${query}`;
    const assignmentBody = JSON.stringify({
      source: "api-ingest",
      ...scope,
      assignment: {
        action: "claim",
        expected_version: 0,
        lease_seconds: 300
      }
    });
    const missingAssignmentKey = await fetch(assignmentUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-a3-role": "reviewer",
        "x-a3-actor-hash": "reviewer_hash_api"
      },
      body: assignmentBody
    });
    assert.equal(missingAssignmentKey.status, 400);

    const claimed = await fetch(assignmentUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "mm-api-assignment-001",
        "x-a3-role": "reviewer",
        "x-a3-actor-hash": "reviewer_hash_api"
      },
      body: assignmentBody
    });
    assert.equal(claimed.status, 200);
    const claimReceipt = await claimed.json();
    assert.equal(claimReceipt.schema_version, "a3.multimodal_review_assignment_receipt.v1");
    assert.equal(claimReceipt.status, "claimed");
    assert.equal(claimReceipt.version, 1);
    assert.equal(claimReceipt.release_authority, false);
    assert.equal(claimReceipt.a2_decision_recomputed, false);

    const replayed = await fetch(assignmentUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "mm-api-assignment-001",
        "x-a3-role": "reviewer",
        "x-a3-actor-hash": "reviewer_hash_api"
      },
      body: assignmentBody
    });
    assert.equal(replayed.status, 200);
    assert.equal((await replayed.json()).idempotency.status, "duplicate_replay");

    const competing = await fetch(assignmentUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "idempotency-key": "mm-api-assignment-002",
        "x-a3-role": "reviewer",
        "x-a3-actor-hash": "reviewer_hash_other"
      },
      body: JSON.stringify({
        source: "api-ingest",
        ...scope,
        assignment: { action: "claim", expected_version: 1 }
      })
    });
    assert.equal(competing.status, 409);
    assert.equal((await competing.json()).error, "assignment_already_claimed");

    const assignedQueueResponse = await fetch(`${url}/api/a3/review/multimodal-queue?${query}`);
    const assignedQueue = await assignedQueueResponse.json();
    assert.equal(assignedQueue.summary.assignment_active_count, 1);
    assert.equal(assignedQueue.items[0].operational_state.status, "claimed");
    assert.equal(assignedQueue.items[0].assignment_history.length, 1);
    assert.equal(assignedQueue.items[0].assignment_history[0].event_hash, claimReceipt.event_hash);
    assert.equal(assignedQueue.authority_boundary.assignment_events_change_a2_decision, false);

    const dashboardResponse = await fetch(`${url}/api/a3/dashboard?${query}`);
    assert.equal(dashboardResponse.status, 200);
    const dashboard = await dashboardResponse.json();
    assert.equal(dashboard.multimodal_review_queue.items.length, 4);
    assert.equal(dashboard.multimodal_review_assignment_packet.event_count, 1);
    assert.equal(dashboard.multimodal_review_assignment_packet.integrity.status, "passed");
    assert.match(dashboard.multimodal_review_assignment_packet.packet_root_hash, /^sha256:[a-f0-9]{64}$/);
    assert.equal(dashboard.multimodal_review_assignment_packet.archive_binding.audit_archive_signature_verified, false);
    assert.ok(dashboard.artifact_registry.entries.some((entry) => (
      entry.artifact_type === "multimodal_review_assignment_packet"
      && entry.hash_status === "content_hash_present"
    )));
    assert.equal(dashboard.event_outbox.event_type_counts["a2.multimodal_comparison_imported"], 1);

    query.set("tenant_id", "tenant-other");
    const foreign = await fetch(`${url}/api/a3/review/multimodal-queue?${query}`);
    assert.equal(foreign.status, 404);
    assert.doesNotMatch(await foreign.text(), /round40|qwen-vl|sha256:/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
