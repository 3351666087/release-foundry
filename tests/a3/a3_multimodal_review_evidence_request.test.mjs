import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildA3MultimodalReviewAssignmentProjection,
  planA3MultimodalReviewAssignmentTransition
} from "../../services/report/a3_multimodal_review_assignment.mjs";
import {
  buildA3MultimodalReviewEvidenceRequestProjection,
  planA3MultimodalReviewEvidenceRequestTransition
} from "../../services/report/a3_multimodal_review_evidence_request.mjs";
import { buildA3MultimodalReviewQueue } from "../../services/report/a3_multimodal_review_queue.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_three_way_v2_bb3bcfe_sample.redacted.json",
  import.meta.url
);
const scope = {
  organization_id: "org-evidence-request",
  tenant_id: "tenant-evidence-request",
  workspace_id: "workspace-evidence-request",
  project_id: "project-evidence-request",
  environment_id: "staging"
};
const reviewer = "reviewer_hash_evidence_owner";
const submitter = "service_account_hash_execution";

test("multimodal review evidence request completes a hash-only request, submission, and acceptance flow", async () => {
  const { queue, queueId } = await claimedQueue("2026-07-14T16:00:00.000Z");
  const events = [];

  const requested = plan(queue, events, queueId, null, "create", {
    expected_version: 0,
    owner_lane: "execution",
    required_evidence_kinds: ["a1_run_trace", "a1_tool_call"],
    due_at: "2026-07-15T16:00:00.000Z",
    reason_code: "trace_and_tool_call_required"
  }, reviewer, "reviewer", "2026-07-14T16:01:00.000Z");
  assert.equal(requested.valid, true);
  assert.equal(requested.statusCode, 201);
  assert.equal(requested.event.event_type, "requested");
  assert.equal(requested.evidence_request.status, "open");
  assert.equal(requested.event.release_authority, false);
  assert.equal(requested.event.authoritative_human_disposition_recorded, false);
  events.push(requested.event);

  const incomplete = plan(queue, events, queueId, requested.event.request_id, "submit", {
    expected_version: 1,
    owner_lane: "execution",
    evidence_refs: [{ kind: "a1_run_trace", evidence_hash: hash("a") }],
    reason_code: "partial_execution_evidence"
  }, submitter, "service_account", "2026-07-14T16:02:00.000Z");
  assert.equal(incomplete.valid, false);
  assert.equal(incomplete.error, "evidence_request_incomplete_submission");
  assert.equal(incomplete.statusCode, 409);

  const submitted = plan(queue, events, queueId, requested.event.request_id, "submit", {
    expected_version: 1,
    owner_lane: "execution",
    evidence_refs: [
      { kind: "a1_tool_call", evidence_hash: hash("b"), binding_hash: hash("c") },
      { kind: "a1_run_trace", evidence_hash: hash("a") }
    ],
    reason_code: "execution_evidence_submitted"
  }, submitter, "service_account", "2026-07-14T16:03:00.000Z");
  assert.equal(submitted.valid, true);
  assert.equal(submitted.evidence_request.status, "submitted");
  assert.equal(submitted.evidence_request.version, 2);
  assert.deepEqual(submitted.evidence_request.submitted_evidence_kinds, ["a1_run_trace", "a1_tool_call"]);
  events.push(submitted.event);

  const wrongReviewer = plan(queue, events, queueId, requested.event.request_id, "review", {
    expected_version: 2,
    action: "accept",
    reason_code: "evidence_complete"
  }, "reviewer_hash_not_assignment_owner", "reviewer", "2026-07-14T16:04:00.000Z");
  assert.equal(wrongReviewer.valid, false);
  assert.equal(wrongReviewer.error, "evidence_request_assignment_not_owned");
  assert.equal(wrongReviewer.statusCode, 403);

  const accepted = plan(queue, events, queueId, requested.event.request_id, "review", {
    expected_version: 2,
    action: "accept",
    reason_code: "evidence_complete"
  }, reviewer, "reviewer", "2026-07-14T16:04:00.000Z");
  assert.equal(accepted.valid, true);
  assert.equal(accepted.evidence_request.status, "accepted");
  assert.equal(accepted.evidence_request.authority_boundary.evidence_accepted, true);
  assert.equal(accepted.evidence_request.authority_boundary.authoritative_human_disposition_recorded, false);
  assert.equal(accepted.evidence_request.authority_boundary.release_decision_changed, false);
  events.push(accepted.event);

  const projected = buildA3MultimodalReviewEvidenceRequestProjection(queue, events, {
    now: "2026-07-14T16:05:00.000Z"
  });
  assert.equal(projected.summary.evidence_request_count, 1);
  assert.equal(projected.summary.evidence_request_accepted_count, 1);
  assert.equal(projected.items[0].evidence_requests[0].history.length, 3);
  assert.equal(projected.items[0].evidence_requests[0].integrity.status, "passed");
  assert.equal(projected.authority_boundary.evidence_requests_change_a2_decision, false);
  assert.equal(projected.safety.raw_evidence_exposed, false);
  assert.doesNotMatch(JSON.stringify(projected), /https?:\/\/|Bearer\s|Cookie:|ASHR_API_KEY|@example\./i);

  const missingSubmission = buildA3MultimodalReviewEvidenceRequestProjection(
    queue,
    [requested.event, accepted.event],
    { now: "2026-07-14T16:05:00.000Z" }
  );
  assert.equal(missingSubmission.items[0].evidence_requests[0].integrity.status, "failed");
  assert.ok(missingSubmission.items[0].evidence_requests[0].integrity.findings.some((finding) => (
    finding.id === "previous_event_hash_mismatch" || finding.id === "invalid_lifecycle_transition"
  )));
  const blockedMutation = plan(queue, [requested.event, accepted.event], queueId, requested.event.request_id, "review", {
    expected_version: 3,
    action: "cancel",
    reason_code: "invalid_chain_cancel"
  }, reviewer, "reviewer", "2026-07-14T16:06:00.000Z");
  assert.equal(blockedMutation.valid, false);
  assert.equal(blockedMutation.error, "evidence_request_integrity_invalid");

  const tampered = structuredClone(submitted.event);
  tampered.evidence_refs[0].evidence_hash = hash("f");
  const tamperedProjection = buildA3MultimodalReviewEvidenceRequestProjection(queue, [requested.event, tampered], {
    now: "2026-07-14T16:05:00.000Z"
  });
  assert.equal(tamperedProjection.summary.evidence_request_invalid_event_count, 1);
});

test("deadline projection marks open requests overdue without fabricating a persisted event", async () => {
  const { queue, queueId } = await claimedQueue("2026-07-14T17:00:00.000Z");
  const requested = plan(queue, [], queueId, null, "create", {
    expected_version: 0,
    owner_lane: "evaluation",
    required_evidence_kinds: ["a2_judge_receipt"],
    due_at: "2026-07-14T17:10:00.000Z",
    reason_code: "judge_receipt_required"
  }, reviewer, "reviewer", "2026-07-14T17:01:00.000Z");
  assert.equal(requested.valid, true);

  const overdue = buildA3MultimodalReviewEvidenceRequestProjection(queue, [requested.event], {
    now: "2026-07-14T17:10:01.000Z"
  });
  const request = overdue.items[0].evidence_requests[0];
  assert.equal(request.status, "overdue");
  assert.equal(request.version, 1);
  assert.equal(request.event_count, 1);
  assert.equal(overdue.summary.evidence_request_overdue_count, 1);
  assert.equal(overdue.summary.evidence_request_event_count, 1);
});

test("rejected evidence reopens the request and unsafe evidence payload fields fail closed", async () => {
  const { queue, queueId } = await claimedQueue("2026-07-14T18:00:00.000Z");
  const requested = plan(queue, [], queueId, null, "create", {
    expected_version: 0,
    owner_lane: "customer_operator",
    required_evidence_kinds: ["media_evidence"],
    due_at: "2026-07-15T18:00:00.000Z",
    reason_code: "media_hash_required"
  }, reviewer, "reviewer", "2026-07-14T18:01:00.000Z");

  const unsafe = plan(queue, [requested.event], queueId, requested.event.request_id, "submit", {
    expected_version: 1,
    owner_lane: "customer_operator",
    evidence_refs: [{
      kind: "media_evidence",
      evidence_hash: hash("d"),
      url: "https://private.invalid/signed-media"
    }],
    reason_code: "media_submitted"
  }, "developer_hash_customer_ops", "developer", "2026-07-14T18:02:00.000Z");
  assert.equal(unsafe.valid, false);
  assert.ok(unsafe.details.some((item) => item.field.endsWith(".url") && item.issue === "unexpected_field"));

  const submitted = plan(queue, [requested.event], queueId, requested.event.request_id, "submit", {
    expected_version: 1,
    owner_lane: "customer_operator",
    evidence_refs: [{ kind: "media_evidence", evidence_hash: hash("d") }],
    reason_code: "media_submitted"
  }, "developer_hash_customer_ops", "developer", "2026-07-14T18:03:00.000Z");
  assert.equal(submitted.valid, true);

  const rejected = plan(queue, [requested.event, submitted.event], queueId, requested.event.request_id, "review", {
    expected_version: 2,
    action: "reject",
    reason_code: "binding_hash_missing"
  }, reviewer, "reviewer", "2026-07-14T18:04:00.000Z");
  assert.equal(rejected.valid, true);
  assert.equal(rejected.event.event_type, "rejected");
  assert.equal(rejected.evidence_request.status, "open");
  assert.equal(rejected.evidence_request.version, 3);
  assert.equal(rejected.evidence_request.authority_boundary.release_authority, false);
});

test("creating or reviewing evidence requests requires ownership of an active assignment lease", async () => {
  const comparison = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const queue = buildA3MultimodalReviewQueue(comparison, {
    source: "p3-a2-round50",
    tenantScope: scope,
    sourceCommitAlias: "bb3bcfe"
  });
  const queueId = queue.items[0].queue_id;
  const denied = plan(queue, [], queueId, null, "create", {
    expected_version: 0,
    owner_lane: "execution",
    required_evidence_kinds: ["a1_run_trace"],
    due_at: "2026-07-15T19:00:00.000Z",
    reason_code: "trace_required"
  }, reviewer, "reviewer", "2026-07-14T19:00:00.000Z");
  assert.equal(denied.valid, false);
  assert.equal(denied.error, "evidence_request_active_assignment_required");
  assert.equal(denied.statusCode, 409);
});

async function claimedQueue(now) {
  const comparison = JSON.parse(await readFile(fixtureUrl, "utf8"));
  const base = buildA3MultimodalReviewQueue(comparison, {
    source: "p3-a2-round50",
    tenantScope: scope,
    sourceCommitAlias: "bb3bcfe"
  });
  const queueId = base.items[0].queue_id;
  const claim = planA3MultimodalReviewAssignmentTransition(base, [], {
    action: "claim",
    expected_version: 0,
    lease_seconds: 3600
  }, {
    queueId,
    source: "p3-a2-round50",
    tenantScope: scope,
    actorHash: reviewer,
    actorRole: "reviewer",
    now
  });
  assert.equal(claim.valid, true);
  return {
    queue: buildA3MultimodalReviewAssignmentProjection(base, [claim.event], { now }),
    queueId
  };
}

function plan(queue, events, queueId, requestId, operation, input, actorHash, actorRole, now) {
  return planA3MultimodalReviewEvidenceRequestTransition(queue, events, input, {
    operation,
    queueId,
    requestId,
    source: "p3-a2-round50",
    tenantScope: scope,
    actorHash,
    actorRole,
    now
  });
}

function hash(character) {
  return `sha256:${character.repeat(64)}`;
}
