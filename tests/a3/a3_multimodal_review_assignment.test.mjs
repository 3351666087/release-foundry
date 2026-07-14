import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildA3MultimodalReviewAssignmentProjection,
  planA3MultimodalReviewAssignmentTransition
} from "../../services/report/a3_multimodal_review_assignment.mjs";
import { buildA3MultimodalReviewQueue } from "../../services/report/a3_multimodal_review_queue.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json",
  import.meta.url
);
const scope = {
  organization_id: "org-assignment",
  tenant_id: "tenant-assignment",
  workspace_id: "workspace-assignment",
  project_id: "project-assignment",
  environment_id: "staging"
};
const reviewerAlpha = "reviewer_hash_alpha";
const reviewerBeta = "reviewer_hash_beta";

test("multimodal review assignment supports claim, renew, transfer, release, and optimistic conflict checks", async () => {
  const queue = await reviewQueue();
  const queueId = queue.items[0].queue_id;
  const events = [];

  const claim = plan(queue, events, queueId, {
    action: "claim",
    expected_version: 0,
    lease_seconds: 300
  }, reviewerAlpha, "reviewer", "2026-07-14T10:00:00.000Z");
  assert.equal(claim.valid, true);
  assert.equal(claim.event.event_type, "claimed");
  assert.equal(claim.operational_state.status, "claimed");
  assert.equal(claim.operational_state.version, 1);
  assert.equal(claim.event.release_authority, false);
  events.push(claim.event);

  const stale = plan(queue, events, queueId, {
    action: "renew",
    expected_version: 0
  }, reviewerAlpha, "reviewer", "2026-07-14T10:01:00.000Z");
  assert.equal(stale.valid, false);
  assert.equal(stale.error, "assignment_version_conflict");
  assert.equal(stale.statusCode, 409);

  const competingClaim = plan(queue, events, queueId, {
    action: "claim",
    expected_version: 1
  }, reviewerBeta, "reviewer", "2026-07-14T10:01:00.000Z");
  assert.equal(competingClaim.valid, false);
  assert.equal(competingClaim.error, "assignment_already_claimed");

  const renew = plan(queue, events, queueId, {
    action: "renew",
    expected_version: 1,
    lease_seconds: 600
  }, reviewerAlpha, "reviewer", "2026-07-14T10:02:00.000Z");
  assert.equal(renew.valid, true);
  assert.equal(renew.event.event_type, "renewed");
  events.push(renew.event);

  const transfer = plan(queue, events, queueId, {
    action: "transfer",
    expected_version: 2,
    target_reviewer_hash: reviewerBeta,
    reason_code: "specialist_handoff"
  }, reviewerAlpha, "reviewer", "2026-07-14T10:03:00.000Z");
  assert.equal(transfer.valid, true);
  assert.equal(transfer.event.event_type, "transferred");
  assert.equal(transfer.operational_state.assigned_reviewer_hash, reviewerBeta);
  events.push(transfer.event);

  const release = plan(queue, events, queueId, {
    action: "release",
    expected_version: 3,
    reason_code: "review_complete_handoff"
  }, reviewerBeta, "reviewer", "2026-07-14T10:04:00.000Z");
  assert.equal(release.valid, true);
  assert.equal(release.operational_state.status, "unassigned");
  assert.equal(release.operational_state.version, 4);
  events.push(release.event);

  const projected = buildA3MultimodalReviewAssignmentProjection(queue, events, {
    now: "2026-07-14T10:04:01.000Z"
  });
  assert.equal(projected.summary.assignment_active_count, 0);
  assert.equal(projected.summary.assignment_unassigned_count, queue.items.length);
  assert.equal(projected.summary.assignment_event_count, 4);
  assert.equal(projected.items[0].operational_state.event_count, 4);
  assert.equal(projected.authority_boundary.assignment_events_release_authority, false);
  assert.equal(projected.authority_boundary.assignment_events_change_a2_decision, false);
  assert.equal(projected.safety.raw_reviewer_identity_exposed, false);
});

test("expired leases can be reclaimed and assignment inputs cannot smuggle dispositions or release authority", async () => {
  const queue = await reviewQueue();
  const queueId = queue.items[0].queue_id;
  const claim = plan(queue, [], queueId, {
    action: "claim",
    expected_version: 0,
    lease_seconds: 60
  }, reviewerAlpha, "reviewer", "2026-07-14T11:00:00.000Z");
  const expiredProjection = buildA3MultimodalReviewAssignmentProjection(queue, [claim.event], {
    now: "2026-07-14T11:01:01.000Z"
  });
  assert.equal(expiredProjection.items[0].operational_state.status, "expired");
  assert.equal(expiredProjection.items[0].operational_state.can_be_claimed, true);

  const reclaimed = plan(queue, [claim.event], queueId, {
    action: "claim",
    expected_version: 1,
    lease_seconds: 120
  }, reviewerBeta, "reviewer", "2026-07-14T11:01:01.000Z");
  assert.equal(reclaimed.valid, true);
  assert.equal(reclaimed.event.event_type, "reclaimed_after_expiry");
  assert.equal(reclaimed.operational_state.assigned_reviewer_hash, reviewerBeta);

  const forbidden = plan(queue, [], queueId, {
    action: "claim",
    expected_version: 0,
    disposition: "confirm_safe",
    release_authority: true
  }, reviewerAlpha, "reviewer", "2026-07-14T11:00:00.000Z");
  assert.equal(forbidden.valid, false);
  assert.equal(forbidden.error, "invalid_assignment_action");
  assert.deepEqual(
    forbidden.details.filter((item) => item.issue === "unexpected_field").map((item) => item.field).sort(),
    ["disposition", "release_authority"]
  );
});

test("latest A2 peer calibration records real provider measurements without inventing a human review receipt", async () => {
  const calibration = JSON.parse(await readFile(new URL(
    "../../fixtures/a3/p3/a2_multimodal_round49_calibration_1553562.redacted.json",
    import.meta.url
  ), "utf8"));
  assert.equal(calibration.source_commit_alias, "1553562");
  assert.equal(calibration.real_provider_calibration.counts.requested, 50);
  assert.equal(calibration.real_provider_calibration.counts.completed, 49);
  assert.equal(calibration.real_provider_calibration.quality.sensitivity, 0.6363636363636364);
  assert.equal(calibration.real_provider_calibration.latency_seconds.p95_nearest_rank, 10.373);
  assert.equal(calibration.real_provider_calibration.qualification_state, "blocked");
  assert.equal(calibration.human_review_calibration.real_public_safe_review_receipt_found, false);
  assert.equal(calibration.human_review_calibration.fixture_reviewer_identity_class, "test_review_fixture");
  assert.equal(calibration.candidate_binding.trusted_spine_generated, false);
  assert.equal(calibration.safety.release_authority, false);
  assert.equal(calibration.safety.a2_decision_recomputed, false);
  assert.doesNotMatch(JSON.stringify(calibration), /Bearer\s|ASHR_API_KEY|Cookie:|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?:\/\//i);
});

async function reviewQueue() {
  const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));
  return buildA3MultimodalReviewQueue(fixture, {
    source: "p3-media",
    tenantScope: scope,
    sourceCommitAlias: "1553562"
  });
}

function plan(queue, events, queueId, input, actorHash, actorRole, now) {
  return planA3MultimodalReviewAssignmentTransition(queue, events, input, {
    queueId,
    source: "p3-media",
    tenantScope: scope,
    actorHash,
    actorRole,
    now
  });
}
