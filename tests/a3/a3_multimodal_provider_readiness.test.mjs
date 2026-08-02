import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildA3MultimodalProviderReadiness,
  validateA2MultimodalProviderReadinessEnvelope
} from "../../services/report/a3_multimodal_provider_readiness.mjs";

const fixtureUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_provider_readiness_round51_7504680.redacted.json",
  import.meta.url
);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));

test("A3 validates and projects the real Round 51 local provider diagnostics", () => {
  const validation = validateA2MultimodalProviderReadinessEnvelope(fixture);
  const projection = buildA3MultimodalProviderReadiness(fixture, {
    source: "p3-a2-round51",
    tenantScope: {
      organization_id: "org-provider",
      tenant_id: "tenant-provider",
      workspace_id: "workspace-provider",
      project_id: "project-provider",
      environment_id: "staging"
    }
  });

  assert.equal(validation.valid, true);
  assert.match(validation.payload_hash, /^sha256:[a-f0-9]{64}$/);
  assert.equal(projection.status, "blocked_provider_readiness");
  assert.equal(projection.summary.provider_count, 2);
  assert.equal(projection.summary.attempted_count, 30);
  assert.equal(projection.summary.completed_count, 1);
  assert.equal(projection.summary.failed_count, 29);
  assert.equal(projection.summary.timeout_case_count, 29);
  assert.equal(projection.summary.eligible_count, 0);
  assert.equal(projection.summary.qualified_provider_count, 0);
  assert.equal(projection.summary.profile_count, 4);
  assert.equal(projection.summary.completed_profile_count, 0);
  assert.equal(projection.summary.valid_structured_profile_count, 0);
  assert.equal(projection.summary.quality_comparison_performed, false);
  assert.equal(projection.summary.operational_health_verified, false);
  assert.equal(projection.availability.providers[0].model_id, "llava:7b");
  assert.equal(projection.availability.providers[1].model_id, "qwen3-vl:4b");
  assert.equal(projection.latency_diagnostic.cold_wall_seconds, 74.299641);
  assert.equal(projection.latency_diagnostic.fastest_warm_wall_seconds, 1.64026);
  assert.equal(projection.latency_diagnostic.profiles.every((item) => item.state === "failed"), true);
  assert.equal(projection.authority_boundary.routing_or_capacity_authority, "A1");
  assert.equal(projection.authority_boundary.evaluation_and_qualification_authority, "A2");
  assert.equal(projection.release_authority, false);
  assert.equal(projection.production_ready, false);
});

test("A3 rejects count drift, unsafe material, unknown fields, and release promotion", () => {
  const cases = [
    (value) => { value.availability_comparison.providers["llava:7b"].failed_count = 13; },
    (value) => { value.availability_comparison.providers["qwen3-vl:4b"].latency_seconds.count = 14; },
    (value) => { value.latency_probe.profiles[0].phase_receipt.transport_and_client_residual_seconds = 10; },
    (value) => { value.latency_probe.completed_profile_count = 1; },
    (value) => { value.latency_probe.profiles[0].raw_response_included = true; },
    (value) => { value.latency_probe.endpoint_url = "https://private.example.test"; },
    (value) => { value.availability_comparison.release_authority = true; },
    (value) => { value.raw_provider_payload_included = true; }
  ];

  for (const mutate of cases) {
    const changed = structuredClone(fixture);
    mutate(changed);
    const validation = validateA2MultimodalProviderReadinessEnvelope(changed);
    assert.equal(validation.valid, false);
    assert.ok(validation.details.length > 0);
    assert.equal(buildA3MultimodalProviderReadiness(changed).status, "invalid_upstream_contract");
  }
});

test("A3 rejects a phase probe that is not bound to an availability model", () => {
  const changed = structuredClone(fixture);
  changed.latency_probe.model_id = "other-model:1b";
  const validation = validateA2MultimodalProviderReadinessEnvelope(changed);
  assert.equal(validation.valid, false);
  assert.ok(validation.details.some((item) => item.issue === "model_missing_from_availability_comparison"));
});

test("public projection contains no endpoint, secret, raw response, or release authority", () => {
  const projection = buildA3MultimodalProviderReadiness(fixture);
  const serialized = JSON.stringify(projection);
  assert.doesNotMatch(serialized, /https?:\/\/|Bearer\s|Cookie\s*:|C:\\Users\\|raw-secret|api[_-]?key/i);
  assert.equal(projection.safety.raw_provider_payload_included, false);
  assert.equal(projection.safety.endpoint_url_included, false);
  assert.equal(projection.authority_boundary.release_authority, false);
  assert.equal(projection.authority_boundary.release_decision_changed, false);
});
