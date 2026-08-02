import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildA3MultimodalReleaseCaseEvidence,
  validateA2MultimodalReleaseCaseEvidence
} from "../../services/report/a3_multimodal_release_case_evidence.mjs";
import { renderShareableReportHtml } from "../../services/report/a3_shareable_report.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

const fixture = JSON.parse(await readFile(new URL(
  "../../fixtures/a3/p3/a2_multimodal_release_case_evidence_round52_850b39a.redacted.json",
  import.meta.url
), "utf8"));

test("A3 validates and projects five hash-bound Round 52 attack cases", () => {
  const validation = validateA2MultimodalReleaseCaseEvidence(fixture);
  const projection = buildA3MultimodalReleaseCaseEvidence(fixture, {
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
  assert.equal(projection.status, "attention_required");
  assert.equal(projection.summary.eligible_count, 5);
  assert.equal(projection.summary.detected_count, 3);
  assert.equal(projection.summary.missed_count, 2);
  assert.equal(projection.summary.sensitivity, 0.6);
  assert.equal(projection.affected_cases.length, 5);
  assert.deepEqual(projection.missed_case_ids, [
    "round51-attack-safety-guidance-conflict-01",
    "round51-attack-safety-guidance-conflict-05"
  ]);
  assert.equal(projection.affected_cases[0].media_evidence.raw_media_available, false);
  assert.equal(projection.affected_cases[0].media_evidence.signed_url_available, false);
  assert.equal(projection.authority_boundary.release_authority, false);
  assert.equal(projection.production_ready, false);
});

test("A3 rejects count drift, outcome drift, duplicate media, URLs, raw media, and promotion", () => {
  const mutations = [
    (value) => { value.summary.detected_count = 4; },
    (value) => { value.summary.sensitivity = 0.8; },
    (value) => { value.cases[0].outcome = "detected"; },
    (value) => { value.cases[1].artifact_hash = value.cases[0].artifact_hash; },
    (value) => { value.cases[0].media_url = "https://private.example.test/media.png"; },
    (value) => { value.safety.raw_media_included = true; },
    (value) => { value.authority_boundary.release_authority = true; }
  ];

  for (const mutate of mutations) {
    const changed = structuredClone(fixture);
    mutate(changed);
    const validation = validateA2MultimodalReleaseCaseEvidence(changed);
    assert.equal(validation.valid, false);
    assert.ok(validation.details.length > 0);
    assert.equal(buildA3MultimodalReleaseCaseEvidence(changed).status, "invalid_upstream_case_evidence");
  }
});

test("public case projection contains hashes but no raw media, URL, identity, or provider payload", () => {
  const projection = buildA3MultimodalReleaseCaseEvidence(fixture);
  const serialized = JSON.stringify(projection);
  assert.match(serialized, /sha256:[a-f0-9]{64}/);
  assert.doesNotMatch(serialized, /https?:\/\/|Bearer\s|Cookie\s*:|C:\\Users\\|api[_-]?key/i);
  assert.equal(projection.safety.hash_only_case_evidence, true);
  assert.equal(projection.safety.raw_media_included, false);
  assert.equal(projection.safety.raw_provider_payload_included, false);
  assert.equal(projection.safety.signed_url_included, false);
  assert.equal(projection.authority_boundary.a2_decision_recomputed, false);
});

test("Round 52 Dashboard and hosted report expose the same five hash-only media cases", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["p3-a2-round52"] });
  const dashboard = await store.getDashboardSnapshot("p3-a2-round52");
  const report = await store.createShareableReport({
    source: "p3-a2-round52",
    idempotencyKey: "round52-case-evidence-report-001",
    createdAt: "2026-07-15T00:00:00.000Z",
    shareToken: "round52-case-evidence-test-token"
  });
  const html = renderShareableReportHtml(report);

  assert.equal(dashboard.multimodal_release_case_evidence.summary.missed_count, 2);
  assert.equal(dashboard.multimodal_review_queue.release_case_evidence.affected_cases.length, 5);
  assert.equal(report.multimodal_release_case_evidence.summary.detected_count, 3);
  assert.match(report.markdown_report, /## Multimodal Case and Media Evidence/);
  assert.match(report.markdown_report, /round51-attack-safety-guidance-conflict-01/);
  assert.match(html, /Multimodal Case and Media Evidence/);
  assert.match(html, /2 of 5 attack cases were missed/);
  assert.doesNotMatch(JSON.stringify(report.payload), /round52-case-evidence-test-token|https?:\/\//);
  assert.doesNotMatch(html, /round52-case-evidence-test-token|https?:\/\//);
});

test("OpenAPI exposes a closed hash-only case-evidence projection with resolved hash refs", async () => {
  const openapi = JSON.parse(await readFile(new URL(
    "../../docs/a3/openapi/a3_commercial_api.openapi.json",
    import.meta.url
  ), "utf8"));
  const dashboard = openapi.components.schemas.DashboardSnapshot;
  const schema = openapi.components.schemas.MultimodalReleaseCaseEvidence;
  const hash = openapi.components.schemas.Sha256Hash;

  assert.equal(
    dashboard.properties.multimodal_release_case_evidence.$ref,
    "#/components/schemas/MultimodalReleaseCaseEvidence"
  );
  assert.equal(schema.additionalProperties, false);
  assert.equal(schema.properties.schema_version.const, "a3.multimodal_release_case_evidence.v1");
  assert.equal(schema.properties.release_authority.const, false);
  assert.equal(schema.properties.a2_decision_recomputed.const, false);
  assert.equal(schema.properties.production_ready.const, false);
  assert.equal(schema.properties.safety.properties.raw_media_included.const, false);
  assert.equal(schema.properties.safety.properties.signed_url_included.const, false);
  assert.equal(hash.pattern, "^sha256:[a-f0-9]{64}$");
});
