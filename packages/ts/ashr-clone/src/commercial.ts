import type { JsonRecord } from "./index.js";

export const COMMERCIAL_KIT_SCHEMA_VERSION = "ashr.clone.commercial_control_plane.v1";

export const USAGE_LABELS = [
  "Videos",
  "Images",
  "Simulations",
  "Audio",
  "Files",
  "Graded scenarios",
  "Observations",
  "Voice minutes",
] as const;

export const SAAS_CONTROL_PLANE_PILLARS = [
  "tenant_project_isolation",
  "usage_billing_governance",
  "api_key_lifecycle_governance",
  "observability_and_cost_analytics",
  "trace_artifact_worker_governance",
  "billing_oauth_readiness_governance",
  "release_gate_and_audit_evidence",
  "frontend_official_surface_parity",
] as const;

export function buildCommercialControlPlaneKit(options: {
  capabilityMatrix: JsonRecord;
  frontendMirrorIndex: JsonRecord;
  evidenceIndex: JsonRecord;
}): JsonRecord {
  return {
    schema_version: COMMERCIAL_KIT_SCHEMA_VERSION,
    product_posture: "enterprise_saas_control_plane_evidence_kit",
    saas_control_plane_pillars: [...SAAS_CONTROL_PLANE_PILLARS],
    source_labels: {
      capability_matrix: options.capabilityMatrix.schema_version,
      frontend_mirror: options.frontendMirrorIndex.schema_version,
      evidence_index: options.evidenceIndex.label,
    },
    usage_billing_snapshot: buildUsageBillingSnapshot(options.frontendMirrorIndex),
    api_key_inventory: buildApiKeyInventory(),
    observability_summary: buildObservabilitySummary(options.capabilityMatrix),
    commercial_surface_readiness: buildCommercialSurfaceReadiness(),
    readiness_badge: buildReadinessBadge(options.capabilityMatrix, options.evidenceIndex),
  };
}

export function buildUsageBillingSnapshot(frontendMirrorIndex: JsonRecord): JsonRecord {
  const mirrorLabels = strings(frontendMirrorIndex.usage_labels);
  const labels = mirrorLabels.filter((label) => (USAGE_LABELS as readonly string[]).includes(label));
  return {
    schema_version: "ashr.clone.usage_billing_snapshot.v1",
    source: "frontend_static_plus_local_synthetic",
    enterprise_saas_surface: true,
    real_billing_called: false,
    checkout_or_portal_called: false,
    plan: {
      plan_id: "local-enterprise-synthetic",
      billing_mode: "synthetic_local_no_charge",
      currency: "USD-placeholder",
      overage_mode_supported: true,
      hard_block_mode_supported: true,
    },
    usage_dimensions: (labels.length > 0 ? labels : [...USAGE_LABELS]).map((label) => ({
      label,
      resource_key: resourceKey(label),
      included_usage: null,
      used: null,
      remaining: null,
      public_safe: true,
      value_policy: "counts omitted from public artifact; private or tenant-specific usage must stay private",
    })),
  };
}

export function buildApiKeyInventory(): JsonRecord {
  return {
    schema_version: "ashr.clone.api_key_inventory.v1",
    source: "local_synthetic_governance_contract",
    enterprise_saas_surface: true,
    raw_sensitive_values_included: false,
    keys: [
      {
        key_id: "key_local_synthetic_active",
        prefix: "ashr_local_***",
        hash_presence: true,
        sensitive_value_present: false,
        status: "active",
        created_at: "2026-07-07T00:00:00Z",
        revoked_at: null,
        last_used_at: null,
        scopes: ["read:evidence", "write:runs"],
      },
      {
        key_id: "key_local_synthetic_revoked",
        prefix: "ashr_local_***",
        hash_presence: true,
        sensitive_value_present: false,
        status: "revoked",
        created_at: "2026-07-07T00:00:00Z",
        revoked_at: "2026-07-07T00:10:00Z",
        last_used_at: null,
        scopes: ["read:evidence"],
      },
    ],
    governance_rules: [
      "never store or print full API key values",
      "public artifacts may include prefix and hash-presence only",
      "revocation state is auditable without exposing the sensitive value",
    ],
  };
}

export function buildCommercialSurfaceReadiness(): JsonRecord {
  return {
    schema_version: "ashr.clone.commercial_surface_readiness.v1",
    enterprise_saas_surface: true,
    raw_sensitive_values_included: false,
    public_safe: true,
    typed_client_surfaces: [
      { domain: "api_key", operations: ["createApiKey", "listApiKeys", "verifyApiKeySecret", "configureApiKeyRateLimit", "revokeApiKey"], secret_policy: "handles_and_redacted_prefixes_only" },
      { domain: "quota", operations: ["quotaSnapshot", "usage"], secret_policy: "tenant_counts_omitted_from_public_artifacts" },
      { domain: "trace", operations: ["ingestTrace", "lifecycle"], secret_policy: "raw_trace_payloads_excluded" },
      { domain: "artifact", operations: ["createArtifactManifest", "listArtifactManifests"], secret_policy: "manifest_receipts_hash_only" },
      { domain: "worker", operations: ["enqueueWorkerJob", "leaseWorkerJob", "completeWorkerJob", "failWorkerJob", "listWorkerJobs"], secret_policy: "lease_owner_and_job_handles_only" },
      { domain: "billing", operations: ["billingCheckoutPlan", "billingPortalPlan", "billingWebhookIngest", "billingLedger"], secret_policy: "provider_payload_hashes_only_no_charge" },
      { domain: "oauth", operations: ["bearerAuthHeaders", "hostedHeaderRejection"], secret_policy: "bearer_values_rejected_from_public_artifacts" },
    ],
    cli_wrappers: [
      "api-key-create",
      "api-key-list",
      "api-key-rate-limit",
      "quota",
      "usage",
      "trace-ingest",
      "artifact-manifest-create",
      "artifact-manifest-list",
      "job-enqueue",
      "job-lease",
      "job-complete",
      "billing-checkout-plan",
      "billing-portal-plan",
      "billing-webhook-ingest",
      "billing-ledger",
    ],
  };
}

export function buildObservabilitySummary(capabilityMatrix: JsonRecord): JsonRecord {
  const capabilities = Array.isArray(capabilityMatrix.capabilities) ? capabilityMatrix.capabilities : [];
  const summary = isRecord(capabilityMatrix.summary) ? capabilityMatrix.summary : {};
  const categories = isRecord(summary.categories) ? summary.categories : {};
  const axisCounts = isRecord(summary.axis_counts) ? summary.axis_counts : {};
  return {
    schema_version: "ashr.clone.observability_summary.v1",
    source: "capability_matrix_local_summary",
    enterprise_saas_surface: true,
    raw_trace_payloads_included: false,
    metrics: {
      capability_domains: Object.keys(categories).length,
      total_capabilities: capabilities.length,
      median_capabilities_per_domain: medianDomainCount(categories),
      real_read_verified_capabilities: numberValue(axisCounts.real_read_verified),
      frontend_mirrored_capabilities: numberValue(axisCounts.frontend_mirrored),
      test_covered_capabilities: numberValue(axisCounts.test_covered),
      error_patterns: [],
      tool_reliability: [],
      latency_distribution: { source: "not_computed_in_public_artifact" },
      cost_analytics: { source: "placeholder_public_safe_no_amounts" },
    },
    a3_handoff_fields: ["capability_domains", "total_capabilities", "error_patterns", "tool_reliability", "cost_analytics"],
  };
}

export function buildReadinessBadge(capabilityMatrix: JsonRecord, evidenceIndex: JsonRecord): JsonRecord {
  const summary = isRecord(capabilityMatrix.summary) ? capabilityMatrix.summary : {};
  const axisCounts = isRecord(summary.axis_counts) ? summary.axis_counts : {};
  const policyCounts = isRecord(evidenceIndex.output_policy_counts) ? evidenceIndex.output_policy_counts : {};
  const unsafe = numberValue(policyCounts.unsafe_real_nonprivate_override);
  return {
    schema_version: "ashr.clone.commercial_readiness_badge.v1",
    enterprise_saas_surface: true,
    read_only_current: numberValue(axisCounts.real_read_verified) > 0,
    gate_current: unsafe === 0,
    mutation_blocked_or_quota_guarded: true,
    paid_mutation_executed_this_round: false,
    private_output_policy_current: unsafe === 0,
    status: "enterprise_saas_read_only_verified_mutation_guarded",
    buyer_safe_claims: [
      "live read-only API shapes were sampled into private evidence",
      "mutating and billing surfaces are classified before execution",
      "public artifacts omit raw keys, private refs, tenant payloads, and exact usage amounts",
      "enterprise SaaS control-plane surfaces are mapped across usage, billing, API keys, observability, release gates, trace ingestion, artifact manifests, worker queues, and OAuth-style bearer governance",
    ],
  };
}

export function validateCommercialControlPlaneKit(kit: JsonRecord): JsonRecord[] {
  const issues: JsonRecord[] = [];
  if (kit.schema_version !== COMMERCIAL_KIT_SCHEMA_VERSION) issues.push({ severity: "error", kind: "bad_schema_version" });
  const text = JSON.stringify(kit);
  for (const forbidden of ["ASHR_API_KEY", "private_refs", "tp_", "sk-", "Bearer ", "ashr_live_", "secret_hash_sha256"]) {
    if (text.includes(forbidden)) issues.push({ severity: "error", kind: "forbidden_public_text", value: forbidden });
  }
  if (kit.product_posture !== "enterprise_saas_control_plane_evidence_kit") issues.push({ severity: "error", kind: "missing_enterprise_saas_posture" });
  const inventory = isRecord(kit.api_key_inventory) ? kit.api_key_inventory : {};
  if (inventory.raw_sensitive_values_included !== false) issues.push({ severity: "error", kind: "api_key_sensitive_values_not_blocked" });
  const readiness = isRecord(kit.commercial_surface_readiness) ? kit.commercial_surface_readiness : {};
  if (readiness.raw_sensitive_values_included !== false) issues.push({ severity: "error", kind: "commercial_surface_sensitive_values_not_blocked" });
  return issues;
}

function resourceKey(label: string): string {
  return label.toLowerCase().replaceAll(" ", "_");
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function medianDomainCount(categories: JsonRecord): number {
  const counts = Object.values(categories).map(numberValue).filter((value) => value > 0).sort((left, right) => left - right);
  if (counts.length === 0) return 0;
  const middle = Math.floor(counts.length / 2);
  return counts.length % 2 === 1 ? counts[middle] : (counts[middle - 1] + counts[middle]) / 2;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
