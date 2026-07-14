import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_three_way_v2_bb3bcfe_sample.redacted.json",
  import.meta.url
);
const scope = {
  organization_id: "org-evidence-api",
  tenant_id: "tenant-evidence-api",
  workspace_id: "workspace-evidence-api",
  project_id: "project-evidence-api",
  environment_id: "staging"
};
const reviewer = "reviewer_hash_api_evidence_owner";

test("A3 API enforces the complete tenant-scoped multimodal evidence-request workflow", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["p3-a2-round50"] });
  const serverNow = "2026-07-14T21:00:00.000Z";
  const { server, url } = await startA3ApiServer({
    store,
    routeAccessMode: "demo_contract",
    now: serverNow
  });
  try {
    const comparison = JSON.parse(await readFile(fixtureUrl, "utf8"));
    const importResponse = await fetch(`${url}/api/a3/import/a2-multimodal-comparison`, {
      method: "POST",
      headers: jsonHeaders("service_account", "evidence-api-import", "service_account_hash_import"),
      body: JSON.stringify({ source: "api-evidence", ...scope, comparison })
    });
    assert.equal(importResponse.status, 201);

    const query = new URLSearchParams({ source: "api-evidence", ...scope, role: "reviewer" });
    const queueResponse = await fetch(`${url}/api/a3/review/multimodal-queue?${query}`);
    assert.equal(queueResponse.status, 200);
    const queue = await queueResponse.json();
    const queueId = queue.items[0].queue_id;
    const assignmentUrl = `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/assignment?${query}`;
    const claimResponse = await fetch(assignmentUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-claim", reviewer),
      body: JSON.stringify({
        source: "api-evidence",
        ...scope,
        assignment: { action: "claim", expected_version: 0, lease_seconds: 3600 }
      })
    });
    assert.equal(claimResponse.status, 200);

    const collectionUrl = `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests?${query}`;
    const evidenceRequest = {
      expected_version: 0,
      owner_lane: "execution",
      required_evidence_kinds: ["a1_run_trace", "a1_tool_call"],
      due_at: "2026-07-15T21:00:00.000Z",
      reason_code: "execution_evidence_required"
    };
    const body = JSON.stringify({ source: "api-evidence", ...scope, evidence_request: evidenceRequest });
    const deniedUrl = new URL(collectionUrl);
    deniedUrl.searchParams.set("role", "viewer");

    const denied = await fetch(deniedUrl, {
      method: "POST",
      headers: jsonHeaders("viewer", "evidence-api-denied", "viewer_hash_evidence"),
      body
    });
    assert.equal(denied.status, 403);
    assert.match(JSON.stringify(await denied.json()), /release:review/);

    const missingKey = await fetch(collectionUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-a3-role": "reviewer",
        "x-a3-actor-hash": reviewer
      },
      body: JSON.stringify({ ...JSON.parse(body), idempotency_key: "body-key-is-not-authority" })
    });
    assert.equal(missingKey.status, 400);
    assert.doesNotMatch(await missingKey.text(), /body-key-is-not-authority/);

    const createdResponse = await fetch(collectionUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-create", reviewer),
      body
    });
    assert.equal(createdResponse.status, 201);
    const created = await createdResponse.json();
    assert.equal(created.schema_version, "a3.multimodal_review_evidence_request_receipt.v1");
    assert.equal(created.status, "open");
    assert.equal(created.version, 1);
    assert.equal(created.authoritative_human_disposition_recorded, false);
    assert.equal(created.release_decision_changed, false);

    const replayResponse = await fetch(collectionUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-create", reviewer),
      body
    });
    assert.equal(replayResponse.status, 201);
    assert.equal((await replayResponse.json()).idempotency.status, "duplicate_replay");

    const submissionQuery = new URLSearchParams(query);
    submissionQuery.set("role", "service_account");
    const submissionUrl = `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests/${encodeURIComponent(created.request_id)}/submissions?${submissionQuery}`;
    const unsafeSubmission = await fetch(submissionUrl, {
      method: "POST",
      headers: jsonHeaders("service_account", "evidence-api-unsafe-submit", "service_account_hash_submit"),
      body: JSON.stringify({
        source: "api-evidence",
        ...scope,
        submission: {
          expected_version: 1,
          owner_lane: "execution",
          evidence_refs: [
            { kind: "a1_run_trace", evidence_hash: hash("a") },
            { kind: "a1_tool_call", evidence_hash: hash("b"), url: "https://private.invalid/evidence" }
          ],
          reason_code: "execution_evidence_submitted"
        }
      })
    });
    assert.equal(unsafeSubmission.status, 400);
    assert.doesNotMatch(await unsafeSubmission.text(), /private\.invalid/);

    const submissionBody = JSON.stringify({
      source: "api-evidence",
      ...scope,
      submission: {
        expected_version: 1,
        owner_lane: "execution",
        evidence_refs: [
          { kind: "a1_run_trace", evidence_hash: hash("a"), binding_hash: hash("c") },
          { kind: "a1_tool_call", evidence_hash: hash("b"), binding_hash: hash("c") }
        ],
        reason_code: "execution_evidence_submitted"
      }
    });
    const submittedResponse = await fetch(submissionUrl, {
      method: "POST",
      headers: jsonHeaders("service_account", "evidence-api-submit", "service_account_hash_submit"),
      body: submissionBody
    });
    assert.equal(submittedResponse.status, 200);
    const submitted = await submittedResponse.json();
    assert.equal(submitted.status, "submitted");
    assert.equal(submitted.version, 2);
    assert.deepEqual(submitted.submitted_evidence_kinds, ["a1_run_trace", "a1_tool_call"]);

    const reviewUrl = `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests/${encodeURIComponent(created.request_id)}/review?${query}`;
    const reviewBody = JSON.stringify({
      source: "api-evidence",
      ...scope,
      review: { expected_version: 2, action: "accept", reason_code: "evidence_hashes_verified" }
    });
    const wrongOwner = await fetch(reviewUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-wrong-owner", "reviewer_hash_api_other"),
      body: reviewBody
    });
    assert.equal(wrongOwner.status, 403);
    assert.equal((await wrongOwner.json()).error, "evidence_request_assignment_not_owned");

    const acceptedResponse = await fetch(reviewUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-accept", reviewer),
      body: reviewBody
    });
    assert.equal(acceptedResponse.status, 200);
    const accepted = await acceptedResponse.json();
    assert.equal(accepted.status, "accepted");
    assert.equal(accepted.version, 3);
    assert.equal(accepted.evidence_accepted, true);
    assert.equal(accepted.authoritative_human_disposition_recorded, false);
    assert.equal(accepted.release_authority, false);

    const staleResponse = await fetch(reviewUrl, {
      method: "POST",
      headers: jsonHeaders("reviewer", "evidence-api-stale", reviewer),
      body: reviewBody
    });
    assert.equal(staleResponse.status, 409);
    assert.equal((await staleResponse.json()).error, "evidence_request_version_conflict");

    const listingResponse = await fetch(collectionUrl, {
      headers: { "x-a3-role": "reviewer", "x-a3-actor-hash": reviewer }
    });
    assert.equal(listingResponse.status, 200);
    const listing = await listingResponse.json();
    assert.equal(listing.summary.accepted_count, 1);
    assert.equal(listing.requests[0].event_count, 3);
    assert.equal(listing.requests[0].evidence_refs.length, 2);
    assert.equal(listing.authority_boundary.release_decision_changed, false);

    const dashboardResponse = await fetch(`${url}/api/a3/dashboard?${query}`);
    assert.equal(dashboardResponse.status, 200);
    const dashboard = await dashboardResponse.json();
    assert.equal(dashboard.multimodal_review_queue.summary.evidence_request_accepted_count, 1);
    assert.equal(dashboard.event_outbox.event_type_counts["review.multimodal_evidence_request.accepted"], 1);

    const foreignQuery = new URLSearchParams({ ...Object.fromEntries(query), tenant_id: "tenant-foreign" });
    const foreign = await fetch(
      `${url}/api/a3/review/multimodal-queue/${encodeURIComponent(queueId)}/evidence-requests?${foreignQuery}`,
      { headers: { "x-a3-role": "reviewer", "x-a3-actor-hash": reviewer } }
    );
    assert.equal(foreign.status, 404);
    assert.doesNotMatch(await foreign.text(), /mmreq_|sha256:|a1_run_trace/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

function jsonHeaders(role, idempotencyKey, actorHash) {
  return {
    "content-type": "application/json",
    "idempotency-key": idempotencyKey,
    "x-a3-role": role,
    "x-a3-actor-hash": actorHash
  };
}

function hash(character) {
  return `sha256:${character.repeat(64)}`;
}
