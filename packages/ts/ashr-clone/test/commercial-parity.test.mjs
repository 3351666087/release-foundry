import assert from "node:assert/strict";
import { test } from "node:test";
import {
  COMMERCIAL_KIT_SCHEMA_VERSION,
  SAAS_CONTROL_PLANE_PILLARS,
  buildCommercialControlPlaneKit,
  buildCommercialSurfaceReadiness,
  validateCommercialControlPlaneKit,
} from "../dist/index.js";

const capabilityMatrix = {
  schema_version: "ashr.clone.capability_matrix.v1",
  capabilities: [
    { category: "api", name: "keys" },
    { category: "quota", name: "limits" },
    { category: "trace", name: "events" },
    { category: "artifact", name: "manifests" },
    { category: "worker", name: "jobs" },
    { category: "billing", name: "ledger" },
    { category: "oauth", name: "bearer" },
  ],
  summary: {
    categories: { api: 1, quota: 1, trace: 1, artifact: 1, worker: 1, billing: 1, oauth: 1 },
    axis_counts: { real_read_verified: 3, frontend_mirrored: 120, test_covered: 88 },
  },
};

const frontendMirrorIndex = {
  schema_version: "ashr.clone.frontend_mirror_index.v1",
  usage_labels: ["Videos", "Images", "Audio", "Files", "Voice minutes"],
};

const evidenceIndex = {
  label: "real_api_evidence_index_public_fixture",
  output_policy_counts: { unsafe_real_nonprivate_override: 0 },
};

test("TS exports Python commercial control-plane evidence-kit capability names", () => {
  const kit = buildCommercialControlPlaneKit({ capabilityMatrix, frontendMirrorIndex, evidenceIndex });

  assert.equal(kit.schema_version, COMMERCIAL_KIT_SCHEMA_VERSION);
  assert.equal(kit.product_posture, "enterprise_saas_control_plane_evidence_kit");
  assert.deepEqual(kit.saas_control_plane_pillars, [...SAAS_CONTROL_PLANE_PILLARS]);
  assert.equal(kit.readiness_badge.read_only_current, true);
  assert.equal(kit.readiness_badge.paid_mutation_executed_this_round, false);
  assert.equal(kit.observability_summary.raw_trace_payloads_included, false);
  assert.equal(kit.observability_summary.metrics.frontend_mirrored_capabilities, 120);
  assert.deepEqual(validateCommercialControlPlaneKit(kit), []);
});

test("TS commercial readiness covers A1 SaaS domains without secrets or Ashr API calls", () => {
  const kit = buildCommercialControlPlaneKit({ capabilityMatrix, frontendMirrorIndex, evidenceIndex });
  const readiness = kit.commercial_surface_readiness;
  const domains = new Set(readiness.typed_client_surfaces.map((surface) => surface.domain));
  const cliWrappers = new Set(readiness.cli_wrappers);
  const fullText = JSON.stringify(kit);

  for (const domain of ["api_key", "quota", "trace", "artifact", "worker", "billing", "oauth"]) {
    assert.equal(domains.has(domain), true, `${domain} readiness domain missing`);
  }
  for (const command of ["api-key-create", "quota", "trace-ingest", "artifact-manifest-create", "job-enqueue", "billing-ledger"]) {
    assert.equal(cliWrappers.has(command), true, `${command} CLI wrapper missing`);
  }
  assert.equal(kit.usage_billing_snapshot.real_billing_called, false);
  assert.equal(kit.usage_billing_snapshot.checkout_or_portal_called, false);
  assert.equal(kit.api_key_inventory.raw_sensitive_values_included, false);
  assert.equal(readiness.raw_sensitive_values_included, false);
  assert.equal(readiness.public_safe, true);
  for (const forbidden of ["ASHR_API_KEY", "private_refs", "tp_", "sk-", "Bearer ", "ashr_live_", "secret_hash_sha256"]) {
    assert.equal(fullText.includes(forbidden), false, `${forbidden} leaked into public artifact`);
  }
});

test("TS commercial validator rejects public artifacts with leaked key material", () => {
  const kit = buildCommercialControlPlaneKit({ capabilityMatrix, frontendMirrorIndex, evidenceIndex });
  const issues = validateCommercialControlPlaneKit({ ...kit, leaked: "Bearer sk-not-real" });

  assert.equal(issues.some((issue) => issue.kind === "forbidden_public_text"), true);
});

test("TS commercial surface readiness can be consumed independently by parity tests", () => {
  const readiness = buildCommercialSurfaceReadiness();
  const apiKeySurface = readiness.typed_client_surfaces.find((surface) => surface.domain === "api_key");
  const billingSurface = readiness.typed_client_surfaces.find((surface) => surface.domain === "billing");
  const oauthSurface = readiness.typed_client_surfaces.find((surface) => surface.domain === "oauth");

  assert.deepEqual(apiKeySurface.operations.slice(0, 2), ["createApiKey", "listApiKeys"]);
  assert.equal(billingSurface.operations.includes("billingWebhookIngest"), true);
  assert.equal(oauthSurface.secret_policy, "bearer_values_rejected_from_public_artifacts");
});
