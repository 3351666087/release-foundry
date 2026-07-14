import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildA3MultimodalRepeatStability,
  validateA2MultimodalRepeatStabilityEnvelope
} from "../../services/report/a3_multimodal_repeat_stability.mjs";

const fixture = JSON.parse(await readFile(new URL(
  "../../fixtures/a3/p3/a2_multimodal_repeat_stability_round51_7504680.redacted.json",
  import.meta.url
), "utf8"));

test("A2 Round 51 repeat stability projects complete but blocked evidence without release authority", () => {
  const validation = validateA2MultimodalRepeatStabilityEnvelope(fixture);
  assert.equal(validation.valid, true, JSON.stringify(validation.details));
  assert.match(validation.payload_hash, /^sha256:[a-f0-9]{64}$/);

  const projection = buildA3MultimodalRepeatStability(fixture, {
    source: "p3-a2-round51",
    tenantScope: {
      organization_id: "org-local",
      tenant_id: "tenant-local",
      workspace_id: "workspace-local",
      project_id: "project-local",
      environment_id: "staging"
    }
  });

  assert.equal(projection.available, true);
  assert.equal(projection.status, "blocked_stable_repeat");
  assert.equal(projection.summary.repeat_count, 3);
  assert.equal(projection.summary.retained_blocked_count, 3);
  assert.equal(projection.summary.all_required_units_complete, true);
  assert.equal(projection.summary.required_source_unit_count, 45);
  assert.equal(projection.summary.stable_observation, true);
  assert.equal(projection.summary.quality_qualified, false);
  assert.equal(projection.summary.promotion_eligible, false);
  assert.deepEqual(projection.metrics.map((item) => item.repeat_estimates), [
    [0.95, 0.95, 0.95],
    [0.2, 0.2, 0.2],
    [0.3, 0.3, 0.3],
    [0.6, 0.6, 0.6]
  ]);
  assert.equal(projection.human_review.collection_state, "pending");
  assert.equal(projection.human_review.receipt_count, 0);
  assert.equal(projection.human_review.pending_queue_receipt_count, 1);
  assert.equal(projection.candidate_binding.verified, false);
  assert.equal(projection.authority_boundary.authoritative_human_disposition_recorded, false);
  assert.equal(projection.authority_boundary.release_authority, false);
  assert.equal(projection.authority_boundary.release_decision_changed, false);
  assert.equal(projection.production_ready, false);
  assert.doesNotMatch(JSON.stringify(projection), /independently verified human reviewer/i);
});

test("repeat stability rejects count drift, false promotion, and unbounded upstream fields", () => {
  const tampered = structuredClone(fixture);
  tampered.comparison.source_unit_coverage.eligible_unit_counts_by_repeat[1] = 44;
  tampered.comparison.promotion_eligible = true;
  tampered.comparison.unexpected_payload = "unsafe";

  const validation = validateA2MultimodalRepeatStabilityEnvelope(tampered);
  assert.equal(validation.valid, false);
  assert.equal(validation.details.some((item) => item.issue === "derived_completeness_mismatch"), true);
  assert.equal(validation.details.some((item) => item.issue === "promotion_prerequisites_not_met"), true);
  assert.equal(validation.details.some((item) => item.field === "comparison.unexpected_payload"), true);

  const projection = buildA3MultimodalRepeatStability(tampered, { source: "tampered" });
  assert.equal(projection.available, false);
  assert.equal(projection.status, "invalid_upstream_contract");
  assert.equal(projection.authority_boundary.release_authority, false);
});

test("repeat stability fails closed until A2 publishes an exact real-review receipt schema", () => {
  const withUnspecifiedReceipt = structuredClone(fixture);
  withUnspecifiedReceipt.review_collection.collection_state = "reviewed";
  withUnspecifiedReceipt.review_collection.receipts = [{ disposition: "allow" }];
  withUnspecifiedReceipt.review_conservation.pending_queue_receipt_count = 0;
  withUnspecifiedReceipt.review_conservation.reviewed_queue_receipt_count = 1;
  withUnspecifiedReceipt.review_conservation.latest_receipt_hashes = {
    queue_receipt_1: `sha256:${"a".repeat(64)}`
  };

  const validation = validateA2MultimodalRepeatStabilityEnvelope(withUnspecifiedReceipt);
  assert.equal(validation.valid, false);
  assert.equal(validation.details.some((item) => item.issue === "authoritative_receipt_schema_not_supported"), true);
});

test("repeat stability rejects secrets, external URLs, and raw provider promotion material", () => {
  for (const mutate of [
    (value) => { value.review_collection.note = "See https://private.example/evidence"; },
    (value) => { value.review_collection.note = "Bearer abcdefghijklmnopqrstuvwxyz"; },
    (value) => { value.raw_provider_payload_included = true; },
    (value) => { value.comparison.release_authority = true; }
  ]) {
    const unsafe = structuredClone(fixture);
    mutate(unsafe);
    const validation = validateA2MultimodalRepeatStabilityEnvelope(unsafe);
    assert.equal(validation.valid, false);
  }
});
