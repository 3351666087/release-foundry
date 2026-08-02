import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { findCommercialApiContractLeaks } from "../../services/report/a3_commercial_api_contract.mjs";
import {
  inspectA3OpenApiRuntimeParity,
  normalizeContractPath,
  synchronizeA3OpenApiRuntimeParity
} from "../../services/report/a3_openapi_runtime_parity.mjs";
import { A3_SENSITIVE_ROUTE_PATTERNS } from "../../services/report/a3_route_access_control.mjs";

const OPENAPI_PATH = new URL("../../docs/a3/openapi/a3_commercial_api.openapi.json", import.meta.url);
const COMMERCIAL_FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_api_contract.redacted.json", import.meta.url);

const FIVE_LEVEL_SCOPE = [
  "organization_id",
  "tenant_id",
  "workspace_id",
  "project_id",
  "environment_id"
];

const VERIFIED_PRINCIPAL_SECURITY = [
  { A1VerifiedSession: [] },
  { A1ServiceAccount: [] }
];

const PUBLIC_READ_PATHS = new Set([
  "/api/a3/health",
  "/r/{shareToken}"
]);

const REQUIRED_FOCUS_TAGS = [
  "Dashboard",
  "Reports",
  "Release Gate",
  "Admin",
  "Billing",
  "Trust",
  "Review",
  "Operations",
  "Notifications"
];

const REQUIRED_SENSITIVE_READ_SURFACES = {
  dashboard: ["/api/a3/dashboard"],
  runs_and_case: ["/api/a3/runs", "/api/a3/runs/{runId}", "/api/a3/cases/{caseId}"],
  evidence: [
    "/api/a3/releases/{releaseId}/evidence-summary",
    "/api/a3/releases/{releaseId}/evidence-health",
    "/api/a3/a1-a2/evidence-spine"
  ],
  reports: [
    "/api/a3/reports",
    "/api/a3/reports/center",
    "/api/a3/reports/{reportId}",
    "/api/a3/reports/{reportId}/manifest"
  ],
  review: ["/api/a3/review/workflow"],
  deployment_operations: ["/api/a3/deployment/sandbox-calibration", "/api/a3/deployment/receipts"],
  admin: ["/api/a3/admin/console", "/api/a3/auth/context", "/api/a3/auth/rbac-policy"],
  usage_and_billing: [
    "/api/a3/usage/ledger",
    "/api/a3/billing/readiness",
    "/api/a3/billing/migration-readiness"
  ],
  live_ops: ["/api/a3/live-workflow/readiness", "/api/a3/live-ops/control-plane"],
  notifications: ["/api/a3/notifications/control-plane"],
  artifacts: ["/api/a3/artifacts/registry"],
  product_console: ["/api/a3/product/console"],
  schema_drift: ["/api/a3/a1-a2/schema-drift"],
  peer_calibration: ["/api/a3/peer-branches/calibration"],
  outbox: ["/api/a3/events/outbox"]
};

const REQUIRED_OPERATION_NOTES = [
  "x-tenant-scope",
  "x-auth",
  "x-rbac",
  "x-usage",
  "x-audit",
  "x-a1-a2-contract"
];

test("A3 commercial OpenAPI v2 covers the required tenant-sensitive read surfaces", async () => {
  const spec = await readOpenApi();

  assert.equal(spec.openapi, "3.1.0");
  assert.equal(spec["x-schema-version"], "a3.openapi.commercial_api.v2");
  assert.equal(spec.info.title, "ReleaseFoundry A3 Commercial Product Console API");
  assert.equal(spec.info.version, "2026.07.14");
  assert.ok(spec["x-contract-source"].includes("services/report/a3_commercial_api_contract.mjs"));
  assert.ok(spec["x-contract-source"].includes("docs/a3/a3_trusted_read_access_contract_2026_07_12.md"));

  const declaredTags = new Set(spec.tags.map((tag) => tag.name));
  for (const tag of REQUIRED_FOCUS_TAGS) {
    assert.equal(declaredTags.has(tag), true, `missing declared tag ${tag}`);
  }

  const requiredRoutes = new Set(Object.values(REQUIRED_SENSITIVE_READ_SURFACES).flat());
  assert.equal(requiredRoutes.size >= 20, true, "security contract must cover at least 20 sensitive reads");

  for (const [surface, routes] of Object.entries(REQUIRED_SENSITIVE_READ_SURFACES)) {
    assert.equal(routes.length > 0, true, `surface ${surface} must name at least one route`);
    for (const path of routes) {
      assert.ok(spec.paths[path]?.get, `missing ${surface} read route GET ${path}`);
    }
  }
});

test("every runtime RBAC route has an OpenAPI operation with the same permission", async () => {
  const spec = await readOpenApi();
  const parity = inspectA3OpenApiRuntimeParity(spec);
  const operations = new Map(collectOperations(spec).map((operation) => [
    `${operation.method.toUpperCase()} ${normalizeContractPath(operation.path)}`,
    operation
  ]));

  assert.equal(parity.complete, true);
  assert.equal(parity.runtime_operation_count, 69);
  assert.equal(parity.documented_runtime_operation_count, 69);
  assert.deepEqual(parity.missing, []);
  for (const route of A3_SENSITIVE_ROUTE_PATTERNS) {
    const key = `${route.method} ${normalizeContractPath(route.path_pattern)}`;
    const operation = operations.get(key);
    assert.ok(operation, `missing OpenAPI operation ${key}`);
    assert.equal(operation["x-rbac"].permission, route.required_permission, `${key} permission drift`);
  }
  assert.deepEqual(synchronizeA3OpenApiRuntimeParity(spec), spec, "committed OpenAPI must be synchronizer-clean");
});

test("multimodal OpenAPI matches the header-only import and non-authoritative review queue runtime", async () => {
  const spec = await readOpenApi();
  const importOperation = spec.paths["/api/a3/import/a2-multimodal-comparison"].post;
  const readOperation = spec.paths["/api/a3/review/multimodal-queue"].get;
  const repeatImportOperation = spec.paths["/api/a3/import/a2-multimodal-repeat-stability"].post;
  const repeatReadOperation = spec.paths["/api/a3/review/multimodal-repeat-stability"].get;
  const assignmentOperation = spec.paths["/api/a3/review/multimodal-queue/{queueId}/assignment"].post;
  const evidenceCollection = spec.paths["/api/a3/review/multimodal-queue/{queueId}/evidence-requests"];
  const evidenceSubmission = spec.paths["/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/submissions"].post;
  const evidenceReview = spec.paths["/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/review"].post;
  const idempotency = importOperation.parameters.find((item) => item.name === "Idempotency-Key");
  const assignmentIdempotency = assignmentOperation.parameters.find((item) => item.name === "Idempotency-Key");
  const repeatIdempotency = repeatImportOperation.parameters.find((item) => item.name === "Idempotency-Key");

  assert.equal(importOperation["x-rbac"].permission, "project:ingest");
  assert.equal(idempotency.in, "header");
  assert.equal(idempotency.required, true);
  assert.equal(importOperation.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalComparisonImportRequest");
  assert.equal(importOperation.responses["201"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalComparisonIngestReceipt");
  assert.equal(importOperation.responses["202"], undefined);
  assert.equal(importOperation["x-authority-boundary"].can_change_release_decision, false);
  assert.equal(readOperation["x-rbac"].permission, "release:review");
  assert.equal(readOperation.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewQueue");
  assert.equal(repeatImportOperation["x-rbac"].permission, "project:ingest");
  assert.equal(repeatIdempotency.in, "header");
  assert.equal(repeatIdempotency.required, true);
  assert.equal(repeatImportOperation.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalRepeatStabilityImportRequest");
  assert.equal(repeatImportOperation.responses["201"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalRepeatStabilityIngestReceipt");
  assert.equal(repeatImportOperation.responses["202"], undefined);
  assert.equal(repeatImportOperation["x-evidence-boundary"].repeat_stability_is_quality_pass, false);
  assert.equal(repeatImportOperation["x-evidence-boundary"].non_empty_human_receipts_fail_closed_until_exact_schema, true);
  assert.equal(repeatImportOperation["x-authority-boundary"].release_authority, false);
  assert.equal(repeatReadOperation["x-rbac"].permission, "release:review");
  assert.equal(repeatReadOperation.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalRepeatStability");
  assert.equal(repeatReadOperation["x-authority-boundary"].production_ready, false);
  assert.equal(assignmentOperation["x-rbac"].permission, "release:review");
  assert.equal(assignmentIdempotency.in, "header");
  assert.equal(assignmentIdempotency.required, true);
  assert.equal(assignmentOperation.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewAssignmentRequest");
  assert.equal(assignmentOperation.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewAssignmentReceipt");
  assert.equal(assignmentOperation["x-concurrency"].strategy, "optimistic_expected_version_plus_time_bounded_lease");
  assert.equal(evidenceCollection.get["x-rbac"].permission, "release:review");
  assert.equal(evidenceCollection.get.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewEvidenceRequestList");
  assert.equal(evidenceCollection.post["x-rbac"].permission, "release:review");
  assert.equal(evidenceCollection.post["x-assignment-owner-required"], true);
  assert.equal(evidenceCollection.post.parameters.find((item) => item.name === "Idempotency-Key").required, true);
  assert.equal(evidenceCollection.post.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewEvidenceRequestCreate");
  assert.equal(evidenceSubmission["x-rbac"].permission, "project:ingest");
  assert.equal(evidenceSubmission["x-assignment-owner-required"], false);
  assert.equal(evidenceSubmission.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewEvidenceSubmission");
  assert.equal(evidenceReview["x-rbac"].permission, "release:review");
  assert.equal(evidenceReview["x-assignment-owner-required"], true);
  assert.equal(evidenceReview.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalReviewEvidenceReview");
  assert.equal(evidenceReview["x-authority-boundary"].evidence_acceptance_is_human_disposition, false);
  assert.equal(evidenceReview["x-authority-boundary"].release_decision_changed, false);
  assert.equal(evidenceReview["x-evidence-boundary"].sha256_references_only, true);
  assert.equal(evidenceReview["x-evidence-boundary"].raw_evidence_forbidden, true);

  const request = spec.components.schemas.MultimodalComparisonImportRequest;
  const envelope = spec.components.schemas.A2MultimodalComparisonEnvelope;
  const receipt = spec.components.schemas.MultimodalComparisonIngestReceipt;
  const queue = spec.components.schemas.MultimodalReviewQueue;
  const assignmentRequest = spec.components.schemas.MultimodalReviewAssignmentRequest;
  const assignmentReceipt = spec.components.schemas.MultimodalReviewAssignmentReceipt;
  const evidenceReference = spec.components.schemas.MultimodalReviewEvidenceReference;
  const evidenceRequest = spec.components.schemas.MultimodalReviewEvidenceRequest;
  const evidenceRequestReceipt = spec.components.schemas.MultimodalReviewEvidenceRequestReceipt;
  const repeatRequest = spec.components.schemas.MultimodalRepeatStabilityImportRequest;
  const repeatEnvelope = spec.components.schemas.A2MultimodalRepeatStabilityEnvelope;
  const repeatReceipt = spec.components.schemas.MultimodalRepeatStabilityIngestReceipt;
  const repeatProjection = spec.components.schemas.MultimodalRepeatStability;
  assert.match(request.description, /header-only/);
  assert.match(request.properties.imported_at.description, /server assigns/);
  assert.deepEqual(envelope.oneOf.map((item) => item.properties.schema_version.const), [
    "a2.multimodal_cross_provider_comparison.v1",
    "a2.multimodal_cross_provider_comparison.v3",
    "a2.multimodal_three_way_comparison.v2"
  ]);
  assert.equal(envelope.oneOf[1].properties.release_authority.const, false);
  assert.equal(envelope.oneOf[2].properties.release_authority.const, false);
  assert.equal(envelope.oneOf[2].properties.evidence_hashes.minProperties, 3);
  assert.equal(envelope.oneOf[2].properties.evidence_hashes.maxProperties, 3);
  assert.deepEqual(envelope.oneOf[2].properties.comparisons.items.properties.comparison_state.enum, [
    "three_way_agreement",
    "pairwise_agreement_with_unavailable",
    "semantic_disagreement",
    "unavailable"
  ]);
  assert.equal(receipt.properties.upstream_release_authority.const, false);
  assert.equal(receipt.properties.candidate_binding_verified.const, false);
  assert.equal(receipt.properties.release_decision_changed.const, false);
  assert.equal(queue.properties.authority_boundary.properties.a3_recomputed_risk.const, false);
  assert.equal(queue.properties.authority_boundary.properties.a3_recomputed_release_decision.const, false);
  assert.equal(queue.properties.authority_boundary.properties.can_change_release_decision.const, false);
  assert.equal(queue.properties.authority_boundary.properties.assignment_events_change_a2_decision.const, false);
  assert.equal(queue.properties.safety.properties.production_ready_claimed.const, false);
  assert.deepEqual(assignmentRequest.properties.assignment.properties.action.enum, ["claim", "renew", "release", "transfer"]);
  assert.equal(assignmentRequest.properties.assignment.properties.expected_version.minimum, 0);
  assert.match(assignmentRequest.description, /cannot contain a disposition/);
  assert.equal(assignmentReceipt.properties.release_authority.const, false);
  assert.equal(assignmentReceipt.properties.a2_decision_recomputed.const, false);
  assert.match(evidenceReference.properties.evidence_hash.pattern, /sha256/);
  assert.equal(evidenceReference.additionalProperties, false);
  assert.equal(evidenceRequest.properties.authority_boundary.properties.authoritative_human_disposition_recorded.const, false);
  assert.equal(evidenceRequest.properties.authority_boundary.properties.release_authority.const, false);
  assert.equal(evidenceRequestReceipt.properties.release_decision_changed.const, false);
  assert.match(repeatRequest.description, /Header-only idempotency/);
  assert.equal(repeatRequest.properties.stability_evidence.$ref, "#/components/schemas/A2MultimodalRepeatStabilityEnvelope");
  assert.equal(repeatEnvelope.properties.schema_version.const, "a3.a2_multimodal_repeat_stability_intake.v1");
  assert.equal(repeatEnvelope.properties.comparison.properties.schema_version.const, "a2.multimodal_multi_repeat_comparison.v1");
  assert.equal(repeatEnvelope.properties.comparison.properties.repeat_count.minimum, 3);
  assert.equal(repeatEnvelope.properties.comparison.properties.provider_is_truth.const, false);
  assert.equal(repeatEnvelope.properties.comparison.properties.release_authority.const, false);
  assert.equal(repeatEnvelope.properties.review_collection.properties.release_authority.const, false);
  assert.equal(repeatEnvelope.properties.raw_provider_payload_included.const, false);
  assert.equal(repeatEnvelope.properties.raw_reviewer_identity_included.const, false);
  assert.equal(repeatReceipt.properties.upstream_release_authority.const, false);
  assert.equal(repeatReceipt.properties.a2_decision_recomputed.const, false);
  assert.equal(repeatReceipt.properties.release_decision_changed.const, false);
  assert.equal(repeatProjection.properties.status.enum.includes("blocked_stable_repeat"), true);
  assert.equal(repeatProjection.properties.authority_boundary.properties.release_authority.const, false);
  assert.equal(repeatProjection.properties.authority_boundary.properties.production_ready.const, false);
  assert.equal(repeatProjection.properties.safety.properties.hashes_and_aggregate_metrics_only.const, true);
  assert.equal(repeatProjection.properties.safety.properties.signed_url_included.const, false);
});

test("provider readiness OpenAPI is strict, atomic, and non-authoritative", async () => {
  const spec = await readOpenApi();
  const importOperation = spec.paths["/api/a3/import/a2-multimodal-provider-readiness"].post;
  const readOperation = spec.paths["/api/a3/providers/multimodal-readiness"].get;
  const envelope = spec.components.schemas.A2MultimodalProviderReadinessEnvelope;
  const request = spec.components.schemas.MultimodalProviderReadinessImportRequest;
  const receipt = spec.components.schemas.MultimodalProviderReadinessIngestReceipt;
  const projection = spec.components.schemas.MultimodalProviderReadiness;

  assert.equal(importOperation["x-rbac"].permission, "project:ingest");
  assert.equal(importOperation.parameters.find((item) => item.name === "Idempotency-Key").required, true);
  assert.equal(importOperation.requestBody.content["application/json"].schema.$ref, "#/components/schemas/MultimodalProviderReadinessImportRequest");
  assert.equal(importOperation.responses["201"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalProviderReadinessIngestReceipt");
  assert.equal(importOperation.responses["202"], undefined);
  assert.equal(importOperation["x-evidence-boundary"].atomic_availability_and_latency_envelope_required, true);
  assert.equal(importOperation["x-authority-boundary"].faster_warm_latency_is_quality_pass, false);
  assert.equal(importOperation["x-authority-boundary"].production_routing_capacity_and_operational_health_authority, "A1");
  assert.equal(importOperation["x-authority-boundary"].evaluation_and_qualification_authority, "A2");
  assert.equal(readOperation["x-rbac"].permission, "release:review");
  assert.equal(readOperation.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/MultimodalProviderReadiness");
  assert.equal(readOperation["x-authority-boundary"].release_authority, false);

  assert.equal(envelope.additionalProperties, false);
  assert.equal(envelope.properties.schema_version.const, "a3.a2_multimodal_provider_readiness_intake.v1");
  assert.equal(envelope.properties.availability_comparison.additionalProperties, false);
  assert.equal(envelope.properties.availability_comparison.properties.providers.additionalProperties.additionalProperties, false);
  assert.equal(envelope.properties.availability_comparison.properties.quality_comparison_performed.const, false);
  assert.equal(envelope.properties.latency_probe.additionalProperties, false);
  assert.equal(envelope.properties.latency_probe.properties.profiles.minItems, 4);
  assert.equal(envelope.properties.latency_probe.properties.profiles.maxItems, 4);
  assert.equal(envelope.properties.latency_probe.properties.secret_included.const, false);
  assert.equal(request.properties.provider_readiness_evidence.$ref, "#/components/schemas/A2MultimodalProviderReadinessEnvelope");
  assert.match(request.description, /Header-only idempotency/);
  assert.equal(receipt.additionalProperties, false);
  assert.equal(receipt.properties.upstream_release_authority.const, false);
  assert.equal(receipt.properties.operational_health_verified.const, false);
  assert.equal(projection.properties.status.enum.includes("blocked_provider_readiness"), true);
  assert.deepEqual(projection.properties.integrity.properties.findings.items.required, ["field", "issue"]);
  assert.equal(projection.properties.integrity.properties.findings.items.additionalProperties, false);
  assert.equal(projection.properties.summary.properties.routing_ready.const, false);
  assert.equal(projection.properties.authority_boundary.properties.release_authority.const, false);
  assert.equal(projection.properties.safety.properties.endpoint_url_included.const, false);
  assert.equal(spec.components.schemas.DashboardSnapshot.properties.multimodal_provider_readiness.$ref, "#/components/schemas/MultimodalProviderReadiness");
});

test("self-host sandbox OpenAPI keeps local evidence separate from production acceptance", async () => {
  const spec = await readOpenApi();
  const operation = spec.paths["/api/a3/deployment/sandbox-calibration"].get;
  const schema = spec.components.schemas.SelfHostSandboxCalibration;

  assert.equal(operation.operationId, "getA3SelfHostSandboxCalibration");
  assert.equal(operation["x-rbac"].permission, "deployment:read");
  assert.deepEqual(operation["x-evidence-boundary"], {
    evidence_level: "sandbox_verified",
    production_verified: false,
    deployment_acceptance_mutated: false,
    a2_decision_recomputed: false,
    release_decision_authority: "A2"
  });
  assert.equal(operation.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/SelfHostSandboxCalibration");
  assert.equal(schema.properties.authority_boundary.properties.production_verified.const, false);
  assert.equal(schema.properties.authority_boundary.properties.deployment_acceptance_mutated.const, false);
  assert.equal(schema.properties.authority_boundary.properties.a2_decision_recomputed.const, false);
  assert.equal(schema.properties.access_contract.properties.required_permission.const, "deployment:read");
  assert.equal(schema.properties.evidence_integrity.properties.postgres_qualification_sha256.pattern, "^sha256:[a-f0-9]{64}$");
  assert.equal(schema.properties.evidence_integrity.properties.combined_payload_sha256.pattern, "^sha256:[a-f0-9]{64}$");
  assert.equal(schema.properties.postgres_qualification.$ref, "#/components/schemas/PostgresRlsQualification");
  const postgres = spec.components.schemas.PostgresRlsQualification;
  assert.equal(postgres.properties.database.properties.migration_id.const, "019_to_020_self_host_sandbox_rls");
  assert.equal(postgres.properties.database.properties.migration_statement_count.const, 2);
  assert.equal(postgres.properties.database.properties.rls_enabled.const, true);
  assert.equal(postgres.properties.database.properties.rls_forced.const, true);
  assert.equal(postgres.properties.tenant_isolation.properties.cross_scope_read_count.const, 0);
  assert.equal(postgres.properties.tenant_isolation.properties.cross_scope_write_denied.const, true);
  assert.equal(postgres.properties.authority_boundary.properties.production_verified.const, false);
  assert.equal(postgres.properties.authority_boundary.properties.target_customer_environment_verified.const, false);
});

test("every non-public A3 read explicitly requires a verified A1 principal, RBAC, scope, and sanitized denials", async () => {
  const spec = await readOpenApi();
  const protectedReads = collectOperations(spec)
    .filter(({ method }) => method === "get")
    .filter(({ path }) => !PUBLIC_READ_PATHS.has(path));

  assert.equal(protectedReads.length >= 20, true, "expected broad protected read coverage");

  for (const operation of protectedReads) {
    assert.deepEqual(operation.security, VERIFIED_PRINCIPAL_SECURITY, `${operation.operationId} must declare verified-principal security`);
    assert.equal(operation["x-access-class"], "tenant_sensitive_read");

    for (const note of REQUIRED_OPERATION_NOTES) {
      assert.ok(operation[note], `${operation.operationId} missing ${note}`);
    }

    const scope = operation["x-tenant-scope"];
    assert.ok(Array.isArray(scope.required));
    for (const field of FIVE_LEVEL_SCOPE) {
      assert.equal(scope.required.includes(field), true, `${operation.operationId} missing scope field ${field}`);
    }
    assert.equal(scope.source, "server_verified_a1_principal");
    assert.equal(scope.client_declared_scope_authoritative, false);
    assert.equal(scope.scope_match_required, true);
    assert.equal(scope.cross_tenant_default, "sanitized_403_or_404");

    const auth = operation["x-auth"];
    assert.equal(auth.required_for_hosted_saas, true);
    assert.equal(auth.backend_owner, "A1");
    assert.equal(auth.principal_authority, "A1 server-side verifier");
    assert.equal(auth.principal_source, "server_verified_a1_principal");
    assert.deepEqual(auth.accepted_principal_kinds, ["browser_session", "service_account"]);
    assert.equal(auth.client_declared_identity_authoritative, false);
    assert.equal(auth.client_declared_role_authoritative, false);
    assert.equal(auth.hosted_contract_only_not_production_proof, true);

    const rbac = operation["x-rbac"];
    assert.match(rbac.permission, /^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$/);
    assert.equal(rbac.evaluation, "server_side_against_verified_principal");
    assert.equal(rbac.client_declared_role_authoritative, false);
    assert.equal(rbac.denied_state_required, true);

    assert.equal(operation.responses["401"].$ref, "#/components/responses/Unauthorized");
    assert.equal(operation.responses["403"].$ref, "#/components/responses/Forbidden");
    assert.ok(Array.isArray(operation["x-usage"].meters));
    assert.ok(operation["x-usage"].source_of_truth.includes("A1 usage ledger"));
    assert.ok(Array.isArray(operation["x-audit"].events));
    assert.equal(operation["x-audit"].payload_policy, "ids_hashes_refs_status_counts_only");
  }
});

test("health and share-token reads are the only public reads and use distinct access contracts", async () => {
  const spec = await readOpenApi();
  const publicReads = collectOperations(spec)
    .filter(({ method, security }) => method === "get" && Array.isArray(security) && security.length === 0)
    .map(({ path }) => path)
    .sort();

  assert.deepEqual(publicReads, [...PUBLIC_READ_PATHS].sort());

  const health = spec.paths["/api/a3/health"].get;
  assert.deepEqual(health.security, []);
  assert.equal(health["x-access-class"], "public_health");
  assert.equal(health["x-public-access"].kind, "health_probe");
  assert.equal(health["x-public-access"].tenant_data_allowed, false);
  assert.equal(health["x-public-access"].customer_payload_allowed, false);
  assert.equal(health["x-rbac"], undefined);
  assert.equal(health.responses["401"], undefined);
  assert.equal(health.responses["403"], undefined);

  const share = spec.paths["/r/{shareToken}"].get;
  assert.deepEqual(share.security, []);
  assert.equal(share["x-access-class"], "public_share_capability");
  assert.equal(share["x-public-access"].kind, "share_token");
  assert.equal(share["x-public-access"].access_model, "opaque_path_capability");
  assert.equal(share["x-public-access"].token_lookup, "server_side_digest_only");
  assert.equal(share["x-public-access"].token_logging_allowed, false);
  assert.equal(share["x-public-access"].tenant_scope_resolution, "server_side_from_valid_token");
  assert.deepEqual(share["x-public-access"].lifecycle_enforcement, ["expiry", "revocation", "download_control", "view_audit"]);
  assert.equal(share["x-rbac"], undefined);
  assert.ok(share.responses["404"]);
  assert.ok(share.responses["410"]);

  const shareToken = spec.components.parameters.ShareToken;
  assert.equal(shareToken.in, "path");
  assert.equal(shareToken.required, true);
  assert.equal(shareToken["x-sensitive"], true);
  assert.equal(shareToken["x-log-policy"], "redact");
  assert.equal(shareToken.schema.writeOnly, true);
});

test("security schemes reject client-declared roles and denial schemas are closed and sanitized", async () => {
  const spec = await readOpenApi();
  const schemes = spec.components.securitySchemes;

  assert.deepEqual(Object.keys(schemes).sort(), ["A1ServiceAccount", "A1VerifiedSession"]);
  assert.equal(schemes.A1VerifiedSession.type, "apiKey");
  assert.equal(schemes.A1VerifiedSession.in, "cookie");
  assert.equal(schemes.A1VerifiedSession.name, "__Host-releasefoundry_session");
  assert.equal(schemes.A1VerifiedSession["x-verification"], "server_side_a1");
  assert.equal(schemes.A1VerifiedSession["x-client-readable"], false);
  assert.equal(schemes.A1ServiceAccount.type, "http");
  assert.equal(schemes.A1ServiceAccount.scheme, "bearer");
  assert.equal(schemes.A1ServiceAccount["x-verification"], "server_side_a1");

  for (const [name, scheme] of Object.entries(schemes)) {
    assert.notEqual(scheme.in, "header", `${name} must not accept a client identity or role header`);
    assert.doesNotMatch(`${name}:${scheme.name || ""}`, /role/i);
  }

  const serialized = JSON.stringify(spec).toLowerCase();
  assert.equal(serialized.includes("x-a3-role"), false);

  const hostedContract = spec["x-hosted-security-contract"];
  assert.equal(hostedContract.status, "contract_only_not_production_proof");
  assert.equal(hostedContract.server_verified_principal_required, true);
  assert.equal(hostedContract.client_declared_role_headers_authoritative, false);
  assert.equal(hostedContract.client_declared_tenant_scope_authoritative, false);
  assert.equal(hostedContract.a1_hosted_login_production_complete_claimed, false);
  assert.equal(hostedContract.a2_decision_semantics_unchanged, true);

  for (const [responseName, schemaName] of [
    ["Unauthorized", "SanitizedUnauthorizedError"],
    ["Forbidden", "SanitizedForbiddenError"]
  ]) {
    const response = spec.components.responses[responseName];
    const schema = spec.components.schemas[schemaName];
    assert.equal(response["x-sanitized"], true);
    assert.equal(response.headers["Cache-Control"].schema.const, "no-store");
    assert.equal(response.content["application/json"].schema.$ref, `#/components/schemas/${schemaName}`);
    assert.equal(schema["x-sanitized"], true);
    assert.equal(schema.additionalProperties, false);
    assert.deepEqual(Object.keys(schema.properties).sort(), ["error", "request_id", "schema_version"]);
    for (const forbiddenField of ["tenant_id", "resource_id", "role", "permission", "detail", "message"]) {
      assert.equal(schema.properties[forbiddenField], undefined, `${schemaName} must not expose ${forbiddenField}`);
    }
  }
});

test("OpenAPI documents sanitized malformed JSON and protected OPTIONS behavior", async () => {
  const spec = await readOpenApi();
  const boundary = spec["x-request-boundary-contract"];
  assert.equal(boundary.schema_version, "a3.request_boundary_contract.v1");
  assert.equal(boundary.malformed_json.authorized_status, 400);
  assert.equal(boundary.malformed_json.body_read_timeout_status, 408);
  assert.equal(boundary.malformed_json.payload_too_large_status, 413);
  assert.equal(boundary.malformed_json.unsupported_media_type_status, 415);
  assert.equal(boundary.malformed_json.invalid_json_shape_status, 422);
  assert.equal(boundary.malformed_json.unauthenticated_status, 401);
  assert.equal(boundary.malformed_json.unauthorized_status, 403);
  assert.equal(boundary.malformed_json.default_maximum_body_bytes, 1048576);
  assert.equal(boundary.malformed_json.default_body_read_timeout_ms, 10000);
  assert.equal(boundary.malformed_json.required_media_type, "application/json");
  assert.equal(boundary.malformed_json.required_top_level_shape, "object");
  assert.equal(boundary.malformed_json.raw_body_logging_allowed, false);
  assert.equal(boundary.malformed_json.metadata_only_denial_audit_required, true);
  assert.equal(boundary.malformed_json.authorization_audit_unavailable_status, 503);
  assert.equal(boundary.protected_options.target_route_authorization_required, true);
  assert.equal(boundary.protected_options.protected_preflight_audited, true);
  assert.equal(boundary.protected_options.raw_origin_logging_allowed, false);
  assert.equal(boundary.protected_options.cors_enablement_claimed, false);
  assert.equal(boundary.authority.identity_and_session, "A1");
  assert.equal(boundary.authority.release_decision, "A2");

  const operations = collectOperations(spec).filter((operation) => operation["x-rbac"]);
  const mutations = operations.filter((operation) => !["get", "head"].includes(operation.method));
  assert.equal(operations.length, 69);
  assert.ok(mutations.length > 0);
  for (const operation of operations) {
    const optionsPolicy = operation["x-protected-options"];
    assert.equal(optionsPolicy.target_method_header, "Access-Control-Request-Method");
    assert.equal(optionsPolicy.target_route_authorization_required, true);
    assert.equal(optionsPolicy.a1_verified_principal_required_for_protected_route, true);
    assert.equal(optionsPolicy.metadata_only_access_audit_required, true);
    assert.equal(optionsPolicy.unregistered_or_unsupported_target_fails_closed, true);
    assert.equal(optionsPolicy.cors_enablement_claimed, false);
    assert.equal(operation.responses["503"].$ref, "#/components/responses/ServiceUnavailable");
  }
  for (const operation of mutations) {
    assert.equal(operation.responses["400"].$ref, "#/components/responses/BadRequest");
    assert.equal(operation.responses["408"].$ref, "#/components/responses/RequestTimeout");
    assert.equal(operation.responses["413"].$ref, "#/components/responses/PayloadTooLarge");
    assert.equal(operation.responses["415"].$ref, "#/components/responses/UnsupportedMediaType");
    assert.equal(operation.responses["422"].$ref, "#/components/responses/UnprocessableEntity");
    assert.equal(operation["x-request-validation"].malformed_json, "sanitized_400_after_authentication_and_authorization");
    assert.equal(operation["x-request-validation"].body_read_timeout, "sanitized_408_after_authentication_and_authorization");
    assert.equal(operation["x-request-validation"].maximum_body_bytes_default, 1048576);
    assert.equal(operation["x-request-validation"].required_media_type, "application/json");
    assert.equal(operation["x-request-validation"].required_top_level_shape, "object");
    assert.equal(operation["x-request-validation"].unauthorized_precedence, "401");
    assert.equal(operation["x-request-validation"].forbidden_precedence, "403");
    assert.equal(operation["x-request-validation"].raw_body_echoed, false);
    assert.equal(operation["x-request-validation"].metadata_only_denial_audit_required, true);
  }

  const badRequestResponse = spec.components.responses.BadRequest;
  const badRequestSchema = spec.components.schemas.SanitizedBadRequestError;
  assert.equal(badRequestResponse["x-sanitized"], true);
  assert.equal(badRequestResponse.headers["Cache-Control"].schema.const, "no-store");
  assert.equal(
    badRequestResponse.content["application/json"].schema.$ref,
    "#/components/schemas/SanitizedBadRequestError"
  );
  assert.equal(badRequestSchema.additionalProperties, false);
  assert.equal(badRequestSchema.properties.schema_version.const, "a3.sanitized_bad_request.v1");
  assert.deepEqual(badRequestSchema.properties.error.enum, [
    "invalid_json",
    "request_timeout",
    "payload_too_large",
    "unsupported_media_type",
    "invalid_json_shape"
  ]);
  assert.deepEqual(Object.keys(badRequestSchema.properties).sort(), ["error", "request_id", "schema_version"]);

  const unavailableResponse = spec.components.responses.ServiceUnavailable;
  const unavailableSchema = spec.components.schemas.SanitizedServiceUnavailableError;
  assert.equal(unavailableResponse["x-sanitized"], true);
  assert.equal(unavailableResponse.headers["Cache-Control"].schema.const, "no-store");
  assert.equal(
    unavailableResponse.content["application/json"].schema.$ref,
    "#/components/schemas/SanitizedServiceUnavailableError"
  );
  assert.equal(unavailableSchema.additionalProperties, false);
  assert.deepEqual(unavailableSchema.properties.error.enum, [
    "authorization_audit_unavailable",
    "authorization_configuration_invalid"
  ]);
});

test("A3 commercial OpenAPI preserves A1/A2 authority and commercial fixture references", async () => {
  const spec = await readOpenApi();
  const fixture = JSON.parse(await readFile(COMMERCIAL_FIXTURE_PATH, "utf8"));

  assert.equal(fixture.schema_version, "a3.commercial_api_contract.v1");
  assert.ok(spec["x-a1-a2-references"].a1.includes("RunResult"));
  assert.ok(spec["x-a1-a2-references"].a1.includes("TraceEvent"));
  assert.ok(spec["x-a1-a2-references"].a1.includes("ToolCall"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("GradeResult"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("ReleaseGate"));
  assert.ok(spec["x-a1-a2-references"].a2.includes("failure taxonomy"));
  assert.ok(spec["x-a1-a2-references"].a3_integration_rule.includes("must not reinterpret A2 judge semantics"));

  const operations = collectOperations(spec);
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a1?.includes("RunResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a1?.includes("usage ledger")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("GradeResult")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("ReleaseGate")));
  assert.ok(operations.some((operation) => operation["x-a1-a2-contract"]?.a2?.includes("redaction verifier")));

  const commercialRoutes = new Set(fixture.endpoint_matrix.map((endpoint) => endpoint.local_a3_route));
  for (const localRoute of [
    "GET /api/a3/dashboard",
    "GET /api/a3/runs/:runId",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "POST /api/a3/review/denials",
    "POST /api/a3/reports/share",
    "GET /api/a3/admin/console",
    "GET /api/a3/billing/readiness",
    "GET /api/a3/billing/migration-readiness",
    "GET /api/a3/usage/ledger"
  ]) {
    assert.equal(commercialRoutes.has(localRoute), true, `existing commercial contract missing ${localRoute}`);
  }

  const migrationReadiness = spec.paths["/api/a3/billing/migration-readiness"].get;
  assert.equal(migrationReadiness["x-schema-version"], "a3.billing_migration_readiness.v1");
  assert.equal(migrationReadiness["x-rbac"].permission, "billing:read");
  assert.deepEqual(migrationReadiness["x-a1-a2-contract"].a1, [
    "read-only billing ledger summary",
    "durable billing migration manifest",
    "provider event replay evidence"
  ]);
  assert.equal(
    migrationReadiness.responses["200"].content["application/json"].schema.$ref,
    "#/components/schemas/BillingMigrationReadiness"
  );
});

test("dashboard contract exposes a fail-closed partial aggregate state", async () => {
  const spec = await readOpenApi();
  const dashboard = spec.components.schemas.DashboardSnapshot;
  const aggregate = spec.components.schemas.AggregateScopeStatus;
  const authority = spec.components.schemas.TrustedReleaseAuthority;

  assert.equal(dashboard.properties.aggregate_scope_status.$ref, "#/components/schemas/AggregateScopeStatus");
  assert.equal(dashboard.properties.trusted_release_authority.$ref, "#/components/schemas/TrustedReleaseAuthority");
  assert.equal(dashboard.properties.deployment_handoff.$ref, "#/components/schemas/DeploymentHandoff");
  assert.equal(dashboard.properties.deployment_receipt_inbox.$ref, "#/components/schemas/DeploymentReceiptInbox");
  assert.equal(dashboard.properties.deployment_acceptance_projection.$ref, "#/components/schemas/DeploymentAcceptanceProjection");
  assert.equal(dashboard.properties.multimodal_repeat_stability.$ref, "#/components/schemas/MultimodalRepeatStability");
  assert.equal(spec.components.schemas.DeploymentHandoff.properties.schema_version.const, "a3.deployment_handoff.v1");
  assert.equal(spec.components.schemas.DeploymentHandoff.properties.safety.properties.a2_decision_recomputed.const, false);
  assert.equal(spec.components.schemas.CandidateBindingHandoff.properties.schema_version.const, "a3.candidate_binding_handoff.v1");
  assert.equal(spec.components.schemas.DeploymentReceipt.properties.schema_version.const, "a3.deployment_receipt.v1");
  assert.equal(spec.components.schemas.DeploymentReceipt.properties.authority_validation.properties.production_verified.type, "boolean");
  assert.equal(spec.components.schemas.DeploymentReceipt.properties.acceptance_effect.properties.changes_release_ready.const, false);
  assert.equal(spec.components.schemas.DeploymentReceiptAuthoritativeReadback.properties.schema_version.const, "a3.deployment_receipt_authoritative_readback.v1");
  assert.equal(spec.components.schemas.DeploymentReceiptAuthoritativeReadback.properties.safety.properties.client_supplied_verification_result_used.const, false);
  assert.equal(spec.components.schemas.DeploymentReceiptInbox.properties.schema_version.const, "a3.deployment_receipt_inbox.v1");
  assert.equal(spec.components.schemas.DeploymentReceiptInbox.properties.production_verified_count.minimum, 0);
  assert.equal(spec.components.schemas.DeploymentAcceptanceProjection.properties.schema_version.const, "a3.deployment_acceptance_projection.v1");
  assert.equal(spec.components.schemas.DeploymentAcceptanceProjection.properties.production_accepted.const, false);
  assert.equal(spec.components.schemas.ReleaseComparisonRuntimeAuthority.properties.schema_version.const, "a3.release_comparison_runtime_authority.v1");
  assert.equal(aggregate.additionalProperties, false);
  assert.deepEqual(aggregate.properties.status.enum, ["complete", "partial"]);
  assert.equal(aggregate.properties.excluded_record_count.minimum, 0);
  assert.equal(aggregate.properties.safety.properties.unscoped_records_included.const, false);
  assert.equal(aggregate.properties.safety.properties.cross_tenant_fallback_allowed.const, false);
  assert.equal(aggregate.properties.safety.properties.foreign_record_counts_exposed.const, false);
  assert.deepEqual(authority.properties.upstream_decision.enum, ["allow", "block", "review", "unknown"]);
  assert.equal(authority.properties.release_ready.description.includes("must not recompute"), true);
  assert.equal(authority.properties.safety.properties.a3_score_recomputed.const, false);
  assert.equal(authority.properties.safety.properties.a3_release_ready_recomputed.const, false);
  assert.equal(authority.properties.safety.properties.client_chain_verified_flag_trusted_without_recalculation.const, false);
});

test("deployment receipt OpenAPI requires idempotency and documents non-authoritative review", async () => {
  const spec = await readOpenApi();
  const collection = spec.paths["/api/a3/deployment/receipts"];
  const review = spec.paths["/api/a3/deployment/receipts/{receiptId}/review"].post;
  const verify = spec.paths["/internal/a3/deployment/receipts/{receiptId}/verify"].post;

  assert.equal(collection.get["x-rbac"].permission, "deployment:read");
  assert.equal(collection.get.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptInbox");
  assert.equal(collection.post["x-rbac"].permission, "deployment:submit");
  assert.equal(collection.post.requestBody.content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptSubmission");
  assert.equal(collection.post.responses["201"].content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceipt");
  assert.equal(collection.post.parameters.some((item) => item.name === "Idempotency-Key" && item.required === true), true);
  assert.equal(review["x-rbac"].permission, "deployment:review");
  assert.equal(review.requestBody.content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptReview");
  assert.equal(review.responses["409"].content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptConflict");
  assert.equal(review.responses["200"].description.includes("without changing deployment or A2 authority"), true);
  assert.equal(verify["x-rbac"].permission, "deployment:verify");
  assert.equal(verify["x-browser-callable"], false);
  assert.equal(verify["x-auth"].service_account_only, true);
  assert.deepEqual(verify.security, [{ A1ServiceAccount: [] }]);
  assert.equal(verify.requestBody.content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptVerificationRequest");
  assert.equal(verify.responses["200"].content["application/json"].schema.$ref, "#/components/schemas/DeploymentReceiptAuthoritativeReadback");
  assert.equal(verify.parameters.some((item) => item.name === "Idempotency-Key" && item.required === true), true);
  assert.equal(verify["x-verifier-boundary"].client_supplied_verification_result_used, false);
});

test("A3 commercial OpenAPI artifact is redacted and safe to publish", async () => {
  const text = await readFile(OPENAPI_PATH, "utf8");
  const spec = JSON.parse(text);
  const serialized = JSON.stringify(spec);

  assert.deepEqual(findCommercialApiContractLeaks(spec), []);
  assert.equal(spec["x-secret-policy"].raw_secrets_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_tokens_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_cookies_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_emails_allowed, false);
  assert.equal(spec["x-secret-policy"].raw_signed_urls_allowed, false);
  assert.equal(spec.components.schemas.SafetyEnvelope.properties.contains_secret_values.const, false);
  assert.equal(spec.components.schemas.BillingReadiness.properties.billing_mutations_enabled.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.billing_mutations_enabled.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.raw_provider_secret_allowed.const, false);
  assert.equal(spec.components.schemas.BillingMigrationReadiness.properties.raw_provider_payload_embedded.const, false);

  for (const forbidden of [
    /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
    /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
    /\bghp_[A-Za-z0-9]{20,}\b/,
    /\bAKIA[0-9A-Z]{16}\b/,
    /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
    /Cookie:\s*(?!\[REDACTED\])/i,
    /RELEASEFOUNDRY_API_KEY\s*=\s*(?!\[REDACTED\])/i,
    /X-Amz-Signature=/i,
    /C:\\Users\\/i
  ]) {
    assert.equal(forbidden.test(serialized), false, `forbidden pattern leaked: ${forbidden.source}`);
  }
});

function collectOperations(spec) {
  const operations = [];
  for (const [path, pathItem] of Object.entries(spec.paths || {})) {
    for (const method of ["get", "post", "put", "patch", "delete"]) {
      if (pathItem[method]) {
        operations.push({ path, method, ...pathItem[method] });
      }
    }
  }
  return operations;
}

async function readOpenApi() {
  return JSON.parse(await readFile(OPENAPI_PATH, "utf8"));
}
