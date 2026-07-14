import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildA3MultimodalReviewQueue,
  validateA2MultimodalComparison
} from "../../services/report/a3_multimodal_review_queue.mjs";
import {
  buildJsonReport,
  buildMarkdownReport
} from "../../services/report/report_builder.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_6673310_sample.redacted.json",
  import.meta.url
);
const v3FixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json",
  import.meta.url
);
const tenantScope = {
  organization_id: "org-review",
  tenant_id: "tenant-review",
  workspace_id: "workspace-review",
  project_id: "project-review",
  environment_id: "environment-review"
};

test("A3 maps the current A2 multimodal disagreement sample into a non-authoritative review queue", async () => {
  const fixture = await loadFixture();
  const queue = buildA3MultimodalReviewQueue(fixture, {
    tenantScope,
    source: "p3-media",
    sourceCommitAlias: "6673310",
    ingestMode: "peer_branch_redacted_sample",
    capabilityState: "peer_branch_contract_not_merged"
  });

  assert.equal(queue.available, true);
  assert.equal(queue.status, "human_review_required");
  assert.equal(queue.source_commit_alias, "6673310");
  assert.equal(queue.summary.comparison_count, 2);
  assert.equal(queue.summary.semantic_disagreement, 1);
  assert.equal(queue.summary.review_required_count, 1);
  assert.equal(queue.items[0].case_id, "round37-hallucination-2");
  assert.equal(queue.items[0].risk_disagreement, true);
  assert.equal(queue.items[0].left.model_id, "qwen-vl-plus");
  assert.equal(queue.items[0].right.model_id, "qwen-vl-max");
  assert.equal(queue.items[0].release_authority, false);
  assert.equal(queue.authority_boundary.a3_recomputed_risk, false);
  assert.equal(queue.authority_boundary.a3_recomputed_release_decision, false);
  assert.equal(queue.authority_boundary.can_change_release_decision, false);
  assert.equal(queue.safety.raw_model_payload_exposed, false);
  assert.deepEqual(queue.tenant_scope, tenantScope);

  const jsonReport = buildJsonReport(...emptyInputs(22), queue);
  const markdownReport = buildMarkdownReport(...emptyInputs(21), queue);
  assert.equal(jsonReport.multimodal_review_queue.available, true);
  assert.equal(jsonReport.multimodal_review_queue.summary.semantic_disagreement, 1);
  assert.equal(jsonReport.multimodal_review_queue.authority_boundary.can_change_release_decision, false);
  assert.match(markdownReport, /## Multimodal Disagreement Review/);
  assert.match(markdownReport, /Can change release decision: no/);
});

test("A3 rejects unsafe, inconsistent, orphaned, or unscoped multimodal comparison input", async () => {
  const fixture = await loadFixture();
  const mutations = [
    (value) => { value.release_authority = true; },
    (value) => { value.raw_payload_included = true; },
    (value) => { value.summary.semantic_disagreement = 0; },
    (value) => { value.human_review_queue_receipts[0].artifact_hash = hash("f"); },
    (value) => { value.left_binding.model_version = "https://private.invalid/model"; }
  ];

  for (const mutate of mutations) {
    const candidate = structuredClone(fixture);
    mutate(candidate);
    const validation = validateA2MultimodalComparison(candidate, { tenantScope });
    assert.equal(validation.valid, false);
    assert.ok(validation.details.length > 0);
  }

  const unscoped = validateA2MultimodalComparison(fixture, {});
  assert.equal(unscoped.valid, false);
  assert.equal(unscoped.details.filter((item) => item.field.startsWith("tenant_scope.")).length, 5);
});

test("A3 maps A2 v3 repeated and aggregate disagreement evidence without promoting it to release authority", async () => {
  const fixture = JSON.parse(await readFile(v3FixtureUrl, "utf8"));
  const validation = validateA2MultimodalComparison(fixture, { tenantScope });
  const queue = buildA3MultimodalReviewQueue(fixture, {
    tenantScope,
    source: "p3-media",
    sourceCommitAlias: "564d4b0",
    ingestMode: "peer_branch_redacted_sample",
    capabilityState: "peer_branch_contract_not_merged"
  });

  assert.equal(validation.valid, true);
  assert.equal(queue.source_contract, "a2.multimodal_cross_provider_comparison.v3");
  assert.equal(queue.source_commit_alias, "564d4b0");
  assert.equal(queue.summary.comparison_count, 8);
  assert.equal(queue.summary.repeat_comparison_count, 6);
  assert.equal(queue.summary.aggregate_comparison_count, 2);
  assert.equal(queue.summary.semantic_disagreement, 2);
  assert.equal(queue.summary.internally_unstable, 2);
  assert.equal(queue.summary.review_required_count, 4);
  assert.equal(queue.items.filter((item) => item.comparison_scope === "repeat").length, 2);
  assert.equal(queue.items.filter((item) => item.comparison_scope === "aggregate").length, 2);
  assert.deepEqual(queue.items.find((item) => item.comparison_scope === "aggregate").left.valid_risks, [false, true]);
  assert.equal(queue.validation.receipt_conservation_verified, true);
  assert.equal(queue.authority_boundary.can_change_release_decision, false);
  assert.equal(queue.safety.production_ready_claimed, false);

  const missingReceipt = structuredClone(fixture);
  missingReceipt.human_review_queue_receipts.pop();
  const invalid = validateA2MultimodalComparison(missingReceipt, { tenantScope });
  const invalidQueue = buildA3MultimodalReviewQueue(missingReceipt, { tenantScope });
  assert.equal(invalid.valid, false);
  assert.ok(invalid.details.some((item) => item.issue === "review_receipt_conservation_failed"));
  assert.equal(invalidQueue.status, "invalid_upstream_contract");
  assert.equal(invalidQueue.source_contract, "a2.multimodal_cross_provider_comparison.v3");
});

test("A3 exposes a bounded invalid state without echoing unsafe upstream content", async () => {
  const fixture = await loadFixture();
  fixture.left_binding.model_id = "Bearer secret-material-that-must-not-surface";
  const queue = buildA3MultimodalReviewQueue(fixture, { tenantScope, source: "api-ingest" });
  const serialized = JSON.stringify(queue);

  assert.equal(queue.available, false);
  assert.equal(queue.status, "invalid_upstream_contract");
  assert.ok(queue.validation.error_count > 0);
  assert.doesNotMatch(serialized, /secret-material/);
  assert.equal(queue.safety.production_ready_claimed, false);
});

async function loadFixture() {
  return JSON.parse(await readFile(fixtureUrl, "utf8"));
}

function hash(character) {
  return `sha256:${character.repeat(64)}`;
}

function emptyInputs(count) {
  return Array.from({ length: count }, () => ({}));
}
