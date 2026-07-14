import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { renderShareableReportHtml } from "../../services/report/a3_shareable_report.mjs";
import {
  buildA3MultimodalReleaseReadiness,
  validateA2MultimodalReleaseReadinessEnvelope
} from "../../services/report/a3_multimodal_release_readiness.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_release_readiness_round52_850b39a.redacted.json",
  import.meta.url
);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));

test("A3 validates and projects the real public-safe A2 Round 52 release-readiness summary", () => {
  const validation = validateA2MultimodalReleaseReadinessEnvelope(fixture);
  const projection = buildA3MultimodalReleaseReadiness(fixture, {
    source: "p3-a2-round52",
    tenantScope: {
      organization_id: "org-round52",
      tenant_id: "tenant-round52",
      workspace_id: "workspace-round52",
      project_id: "project-round52",
      environment_id: "staging"
    }
  });

  assert.equal(validation.valid, true);
  assert.match(validation.payload_hash, /^sha256:[a-f0-9]{64}$/);
  assert.equal(projection.status, "blocked_multimodal_release_readiness");
  assert.equal(projection.source_commit_alias, "850b39a");
  assert.equal(projection.a1_peer_commit_alias, "566a13d");
  assert.equal(projection.summary.cloud_eligible_count, 15);
  assert.equal(projection.summary.safe_control_count, 10);
  assert.equal(projection.summary.safe_control_false_positive_count, 0);
  assert.equal(projection.summary.taxonomy_detected_count, 3);
  assert.equal(projection.summary.taxonomy_eligible_count, 5);
  assert.equal(projection.summary.specificity, 1);
  assert.equal(projection.summary.sensitivity, 0.6);
  assert.equal(projection.summary.balanced_accuracy, 0.8);
  assert.equal(projection.local_runtime.model_id, "qwen3-vl:8b");
  assert.equal(projection.local_runtime.completed_profile_count, 0);
  assert.equal(projection.repeat_evidence.quality_state, "blocked");
  assert.equal(projection.repeat_evidence.stability_state, "qualified");
  assert.equal(projection.repeat_evidence.promotion_eligible, false);
  assert.equal(projection.human_review.collection_state, "pending");
  assert.equal(projection.persistence.same_round_real_postgresql_verified, false);
  assert.equal(projection.candidate_binding.verified, false);
  assert.equal(projection.identity_boundary.a3_client_route_status, "not_exposed_in_peer_evidence");
  assert.equal(projection.release_authority, false);
  assert.equal(projection.production_ready, false);
});

test("A3 fails closed on count drift, false promotion, unsafe identity material, or unknown fields", () => {
  const mutations = [
    (value) => { value.public_summary.cloud_control_run.eligible_count = 14; },
    (value) => { value.public_summary.control_policy.taxonomy_assessments.cross_modal_conflict.sensitivity = 0.8; },
    (value) => { value.public_summary.control_policy.safe_control_assessment.passed = false; },
    (value) => { value.public_summary.multi_repeat.promotion_eligible = true; },
    (value) => { value.public_summary.release_authority = true; },
    (value) => { value.a1_peer_boundary.raw_identity_receipt_included = true; },
    (value) => { value.public_summary.provider_endpoint = "https://private.example.test"; }
  ];

  for (const mutate of mutations) {
    const changed = structuredClone(fixture);
    mutate(changed);
    const validation = validateA2MultimodalReleaseReadinessEnvelope(changed);
    assert.equal(validation.valid, false);
    assert.ok(validation.details.length > 0);
    assert.equal(buildA3MultimodalReleaseReadiness(changed).status, "invalid_upstream_contract");
  }
});

test("Round 52 fixture source reaches Dashboard and hosted reports without changing release authority", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["p3-a2-round52"] });
  const dashboard = await store.getDashboardSnapshot("p3-a2-round52");
  const report = await store.createShareableReport({
    source: "p3-a2-round52",
    idempotencyKey: "round52-report-001",
    createdAt: "2026-07-15T00:00:00.000Z",
    shareToken: "round52-test-share-token"
  });
  const html = renderShareableReportHtml(report);

  assert.equal(dashboard.multimodal_release_readiness.schema_version, "a3.multimodal_release_readiness.v1");
  assert.equal(dashboard.multimodal_release_readiness.summary.taxonomy_detected_count, 3);
  assert.equal(dashboard.multimodal_review_queue.release_readiness.summary.repeat_stability_state, "qualified");
  assert.equal(dashboard.multimodal_review_queue.release_readiness.summary.repeat_quality_state, "blocked");
  assert.equal(dashboard.trusted_release_authority.release_ready, false);
  assert.equal(report.multimodal_release_readiness.status, "blocked_multimodal_release_readiness");
  assert.match(report.markdown_report, /## Multimodal Release Readiness/);
  assert.match(html, /Multimodal Release Readiness/);
  assert.match(html, /3\/5/);
  assert.doesNotMatch(JSON.stringify(report.payload), /round52-test-share-token|https?:\/\//);
  assert.doesNotMatch(html, /round52-test-share-token|https?:\/\//);
});

test("public projection contains no provider endpoint, identity receipt, secret, or production claim", () => {
  const projection = buildA3MultimodalReleaseReadiness(fixture);
  const serialized = JSON.stringify(projection);
  assert.doesNotMatch(serialized, /https?:\/\/|Bearer\s|Cookie\s*:|C:\\Users\\|api[_-]?key/i);
  assert.equal(projection.safety.raw_provider_payload_included, false);
  assert.equal(projection.safety.raw_identity_receipt_included, false);
  assert.equal(projection.authority_boundary.a2_decision_recomputed, false);
  assert.equal(projection.authority_boundary.release_authority, false);
  assert.equal(projection.authority_boundary.production_ready, false);
});

test("OpenAPI declares the Round 52 dashboard projection without adding release authority", async () => {
  const openapi = JSON.parse(await readFile(
    new URL("../../docs/a3/openapi/a3_commercial_api.openapi.json", import.meta.url),
    "utf8"
  ));
  const dashboard = openapi.components.schemas.DashboardSnapshot;
  const schema = openapi.components.schemas.MultimodalReleaseReadiness;
  assert.equal(
    dashboard.properties.multimodal_release_readiness.$ref,
    "#/components/schemas/MultimodalReleaseReadiness"
  );
  assert.equal(schema.properties.schema_version.const, "a3.multimodal_release_readiness.v1");
  assert.equal(schema.properties.release_authority.const, false);
  assert.equal(schema.properties.a2_decision_recomputed.const, false);
  assert.equal(schema.properties.production_ready.const, false);
});
