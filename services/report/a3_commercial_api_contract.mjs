import { createHash } from "node:crypto";

export const A3_COMMERCIAL_API_CONTRACT_SCHEMA_VERSION = "a3.commercial_api_contract.v1";
export const A3_COMMERCIAL_API_CONTRACT_ID = "a3_commercial_api_contract_2026_07_09";
export const A3_COMMERCIAL_API_CONTRACT_GENERATED_AT = "2026-07-09T00:00:00.000Z";

const REQUIRED_A3_SURFACES = [
  "product_console",
  "release_gate",
  "review_workflow",
  "report_center",
  "artifact_registry",
  "usage_billing",
  "admin_console",
  "notification_control_plane",
  "audit_export"
];

const SECRET_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
  /\bghp_[A-Za-z0-9]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
  /Cookie:\s*(?!\[REDACTED\])/i,
  /ASHR_API_KEY\s*=\s*(?!\[REDACTED\])/i,
  /https:\/\/[^"\s]+X-Amz-Signature=/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /C:\\Users\\/i
];

export function buildA3CommercialApiContract(options = {}) {
  const endpoints = COMMERCIAL_ENDPOINTS.map((endpoint, index) => ({
    ...endpoint,
    order: index + 1,
    a3_status: classifyEndpoint(endpoint),
    contract_risk: classifyRisk(endpoint),
    secret_values_allowed: false
  }));
  const body = {
    schema_version: A3_COMMERCIAL_API_CONTRACT_SCHEMA_VERSION,
    contract_id: options.contractId || A3_COMMERCIAL_API_CONTRACT_ID,
    generated_at: options.generatedAt || A3_COMMERCIAL_API_CONTRACT_GENERATED_AT,
    source: options.source || "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      tenant_id: options.tenantId || "tenant-local",
      workspace_id: options.workspaceId || "workspace-local",
      project_id: options.projectId || "project-local",
      environment_id: options.environmentId || "staging"
    },
    purpose: "Map commercial /v1 SaaS endpoints to current A3 product surfaces without claiming A1/A2 backend ownership.",
    summary: summarizeEndpoints(endpoints),
    required_a3_surfaces: REQUIRED_A3_SURFACES,
    endpoint_matrix: endpoints,
    event_envelope_contract: {
      schema_version: "ashr.event_envelope.v1",
      required_fields: [
        "event_id",
        "event_type",
        "schema_version",
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "actor_id",
        "request_id",
        "trace_id",
        "resource_type",
        "resource_id",
        "created_at",
        "payload_ref",
        "payload_hash",
        "redaction_status"
      ],
      a3_current_state: "modeled_as_contract; persisted audit_events exist only in local A3 store",
      local_contract_module: "services/report/a3_event_envelope.mjs",
      durable_outbox_table: "event_outbox",
      a1_dependency: "A1 owns durable API gateway, auth middleware, usage source, and worker event publication.",
      a2_dependency: "A2 owns judge/policy events and verifier correctness for grade/release evidence."
    },
    source_authority: {
      a1: {
        owns: ["runs", "trace_events", "observations", "tool_calls", "artifacts", "usage_source", "auth_backend"],
        consumed_by_a3_as: ["RunResult", "TraceEvent", "ToolCall", "Observation", "artifact refs", "usage preview"],
        must_not_change: "A3 does not mutate A1 runner, SDK, auth, quota, or artifact semantics."
      },
      a2: {
        owns: ["scenarios", "judge_results", "release_gate", "failure_taxonomy", "commercial_readiness"],
        consumed_by_a3_as: ["GradeResult", "ReleaseGate", "CommercialReadiness", "RegressionReplay", "ResultPersistence"],
        must_not_change: "A3 does not change judge scores, pass/fail, thresholds, or failure-class semantics."
      },
      a3: {
        owns: ["console UX", "review workflow", "report center", "shareable report", "commercial API mapping"],
        downstream_only: true
      }
    },
    tenant_auth_rbac_usage_audit: {
      tenant: {
        required_scope: ["organization_id", "project_id", "environment_id"],
        cross_tenant_default: "404_or_empty",
        durable_backend_owner: "A1"
      },
      auth: {
        current_a3_state: "read-only or plan-only shell",
        required_before_live_write: ["hosted session", "safe actor id", "service account id", "idempotency key"],
        raw_credentials_in_contract: false
      },
      rbac: {
        roles: ["owner", "admin", "developer", "reviewer", "auditor", "billing_admin", "service_account"],
        enforcement_state: "contract_only_until_A1_auth_middleware",
        denied_state_required: true
      },
      usage: {
        meters: [...new Set(endpoints.flatMap((endpoint) => endpoint.usage_meters))].sort(),
        billing_mutations_enabled: false,
        source_of_truth: "A1 billing ledger; A3 remains read-only preview"
      },
      audit: {
        append_only_required: true,
        event_types: [...new Set(endpoints.flatMap((endpoint) => endpoint.events))].sort(),
        payload_policy: "ids, hashes, refs, statuses, and counts only"
      }
    },
    safety: {
      contains_secret_values: false,
      raw_tokens_allowed: false,
      raw_cookies_allowed: false,
      raw_emails_allowed: false,
      raw_signed_urls_allowed: false,
      live_cloud_mutations_performed: false,
      fixture_output_path: "fixtures/a3/p3/a3_commercial_api_contract.redacted.json"
    },
    acceptance: {
      node_test: "node --test tests/a3/a3_commercial_api_contract.test.mjs",
      fixture: "fixtures/a3/p3/a3_commercial_api_contract.redacted.json",
      documentation: "docs/a3/p3_commercial_api_contract_2026_07_09.md",
      api_route: "GET /api/a3/commercial-api/contract"
    }
  };

  return {
    ...body,
    contract_hash: sha256(stableJson(body))
  };
}

export function validateA3CommercialApiContract(contract = {}) {
  const errors = [];
  if (contract.schema_version !== A3_COMMERCIAL_API_CONTRACT_SCHEMA_VERSION) {
    errors.push("schema_version must be a3.commercial_api_contract.v1");
  }
  const endpoints = Array.isArray(contract.endpoint_matrix) ? contract.endpoint_matrix : [];
  if (endpoints.length < 20) {
    errors.push("commercial API contract must contain at least 20 endpoints");
  }
  for (const surface of REQUIRED_A3_SURFACES) {
    if (!endpoints.some((endpoint) => endpoint.a3_surface === surface)) {
      errors.push(`missing A3 surface coverage: ${surface}`);
    }
  }
  for (const endpoint of endpoints) {
    for (const field of ["route", "owner_lane", "a3_surface", "rbac", "local_a3_route"]) {
      if (!endpoint[field]) {
        errors.push(`${endpoint.route || "endpoint"} missing ${field}`);
      }
    }
    if (!Array.isArray(endpoint.db_tables) || endpoint.db_tables.length === 0) {
      errors.push(`${endpoint.route} missing db_tables`);
    }
    if (!Array.isArray(endpoint.events) || endpoint.events.length === 0) {
      errors.push(`${endpoint.route} missing events`);
    }
    if (!Array.isArray(endpoint.artifacts) || endpoint.artifacts.length === 0) {
      errors.push(`${endpoint.route} missing artifacts`);
    }
    if (!Array.isArray(endpoint.a1_a2_dependencies) || endpoint.a1_a2_dependencies.length === 0) {
      errors.push(`${endpoint.route} missing A1/A2 dependencies`);
    }
  }
  for (const leak of findCommercialApiContractLeaks(contract)) {
    errors.push(`potential secret leak: ${leak.pattern}`);
  }
  return { valid: errors.length === 0, errors };
}

export function findCommercialApiContractLeaks(value) {
  const serialized = JSON.stringify(value);
  return SECRET_PATTERNS
    .filter((pattern) => pattern.test(serialized))
    .map((pattern) => ({ pattern: pattern.source }));
}

function endpoint(route, ownerLane, a3Surface, localA3Route, options = {}) {
  return {
    route,
    owner_lane: ownerLane,
    a3_surface: a3Surface,
    local_a3_route: localA3Route,
    method: route.split(" ")[0],
    status_hint: options.status || "planned",
    rbac: options.rbac || "tenant_reader",
    db_tables: options.db || [],
    events: options.events || [],
    artifacts: options.artifacts || [],
    usage_meters: options.usage || [],
    a1_a2_dependencies: options.dependencies || [],
    notes: options.notes || "Mapped from commercial SaaS strategy into A3 downstream product workflow."
  };
}

function classifyEndpoint(endpoint) {
  if (endpoint.status_hint === "implemented") return "implemented_local_a3";
  if (endpoint.status_hint === "read_only") return "read_only_local_a3";
  if (endpoint.status_hint === "plan_only") return "plan_only_until_backend";
  if (endpoint.status_hint === "blocked_by_auth") return "blocked_until_A1_auth_RBAC";
  return "contract_mapped_not_live";
}

function classifyRisk(endpoint) {
  if (endpoint.route.includes("/billing/checkout") || endpoint.route.includes("/billing/portal")) {
    return "high_payment_mutation";
  }
  if (endpoint.route.includes("/api-keys") || endpoint.route.includes("/organizations") || endpoint.route.includes("/projects")) {
    return "high_tenant_or_secret_mutation";
  }
  if (endpoint.route.includes("/release-gates") || endpoint.route.includes("/approvals") || endpoint.route.includes("/waivers")) {
    return "medium_release_governance";
  }
  return "low_read_or_ingest_contract";
}

function summarizeEndpoints(endpoints) {
  const byStatus = countBy(endpoints, "a3_status");
  const byOwner = countBy(endpoints, "owner_lane");
  const bySurface = countBy(endpoints, "a3_surface");
  return {
    endpoint_count: endpoints.length,
    implemented_or_read_only_count: endpoints.filter((endpoint) => (
      endpoint.a3_status === "implemented_local_a3"
      || endpoint.a3_status === "read_only_local_a3"
    )).length,
    plan_only_count: endpoints.filter((endpoint) => endpoint.a3_status === "plan_only_until_backend").length,
    blocked_by_auth_count: endpoints.filter((endpoint) => endpoint.a3_status === "blocked_until_A1_auth_RBAC").length,
    by_status: byStatus,
    by_owner_lane: byOwner,
    by_a3_surface: bySurface,
    sellable_claim: "A3 can show customers which release-intelligence workflow is product-ready, which API is only planned, and which backend owner must close the gap before live SaaS launch."
  };
}

function countBy(items, field) {
  return Object.fromEntries([...new Set(items.map((item) => item[field]))]
    .sort()
    .map((value) => [value, items.filter((item) => item[field] === value).length]));
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortForStableJson(item)]));
  }
  return value;
}

const COMMON_A1 = ["A1 tenant/auth/API gateway", "A1 Postgres/object storage", "A1 audit and usage source"];
const COMMON_A2 = ["A2 judge/release policy", "A2 failure taxonomy", "A2 evidence readiness"];

const COMMERCIAL_ENDPOINTS = [
  endpoint("GET /v1/me", "A1", "admin_console", "GET /api/a3/admin/console", {
    status: "blocked_by_auth",
    rbac: "authenticated_user",
    db: ["users", "identities", "sessions", "organization_members"],
    events: ["auth.session_read", "audit.actor_bound"],
    artifacts: ["auth_boundary_receipt"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("GET /v1/organizations", "A1", "admin_console", "GET /api/a3/admin/console", {
    status: "read_only",
    rbac: "organization_member",
    db: ["organizations", "organization_members", "roles"],
    events: ["organization.listed"],
    artifacts: ["saas_admin_guardrails"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("POST /v1/organizations", "A1", "admin_console", "POST /api/a3/admin/actions/submit", {
    status: "plan_only",
    rbac: "authenticated_user",
    db: ["organizations", "organization_members", "audit_events"],
    events: ["organization.create_requested", "audit.mutation_planned"],
    artifacts: ["saas_admin_action_request"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("GET /v1/projects", "A1", "product_console", "GET /api/a3/product/console", {
    status: "read_only",
    rbac: "project_reader",
    db: ["projects", "environments", "runs"],
    events: ["project.listed"],
    artifacts: ["product_console_snapshot"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("POST /v1/projects", "A1", "product_console", "POST /api/a3/admin/actions/submit", {
    status: "plan_only",
    rbac: "organization_admin",
    db: ["projects", "environments", "audit_events"],
    events: ["project.create_requested", "audit.mutation_planned"],
    artifacts: ["saas_admin_action_request"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("GET /v1/projects/{project_id}", "A1", "product_console", "GET /api/a3/dashboard", {
    status: "implemented",
    rbac: "project_reader",
    db: ["projects", "runs", "run_cases", "grade_results"],
    events: ["project.dashboard_read"],
    artifacts: ["dashboard_snapshot"],
    usage: ["api_requests"],
    dependencies: ["A1 RunResult", "A2 GradeResult"]
  }),
  endpoint("POST /v1/api-keys", "A1", "admin_console", "POST /api/a3/admin/actions/submit", {
    status: "plan_only",
    rbac: "organization_admin",
    db: ["api_keys", "audit_events"],
    events: ["api_key.create_requested"],
    artifacts: ["api_key_metadata_only_plan"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("GET /v1/api-keys", "A1", "admin_console", "GET /api/a3/admin/console", {
    status: "read_only",
    rbac: "organization_admin",
    db: ["api_keys", "audit_events"],
    events: ["api_key.listed"],
    artifacts: ["api_key_prefix_metadata"],
    usage: ["api_requests"],
    dependencies: COMMON_A1
  }),
  endpoint("POST /v1/datasets", "A1/A2", "product_console", "POST /api/a3/import/a2-grade-result", {
    status: "plan_only",
    rbac: "project_developer",
    db: ["datasets", "scenarios", "scenario_packs", "audit_events"],
    events: ["dataset.create_requested"],
    artifacts: ["scenario_selection_manifest"],
    usage: ["api_requests", "case_count"],
    dependencies: ["A1 dataset persistence", "A2 scenario schema"]
  }),
  endpoint("GET /v1/datasets/{dataset_id}", "A1/A2", "product_console", "GET /api/a3/dashboard", {
    status: "read_only",
    rbac: "project_reader",
    db: ["datasets", "scenarios", "run_cases"],
    events: ["dataset.read"],
    artifacts: ["dataset_summary"],
    usage: ["api_requests"],
    dependencies: ["A1 dataset record", "A2 scenario metadata"]
  }),
  endpoint("POST /v1/runs", "A1", "product_console", "POST /api/a3/import/a1-run-result", {
    status: "implemented",
    rbac: "project_developer_or_service_account",
    db: ["runs", "run_cases", "api_import_receipts", "idempotency_keys"],
    events: ["run.created", "a1.imported"],
    artifacts: ["run_result", "api_import_receipt"],
    usage: ["api_requests", "run_count"],
    dependencies: ["A1 RunResult"]
  }),
  endpoint("GET /v1/runs", "A1", "product_console", "GET /api/a3/runs", {
    status: "implemented",
    rbac: "project_reader",
    db: ["runs", "run_cases"],
    events: ["run.listed"],
    artifacts: ["run_list"],
    usage: ["api_requests"],
    dependencies: ["A1 RunResult"]
  }),
  endpoint("GET /v1/runs/{run_id}", "A1", "product_console", "GET /api/a3/runs/:runId", {
    status: "implemented",
    rbac: "project_reader",
    db: ["runs", "run_cases", "trace_events", "tool_calls"],
    events: ["run.read"],
    artifacts: ["run_detail", "trace_timeline"],
    usage: ["api_requests"],
    dependencies: ["A1 RunResult", "A1 TraceEvent", "A1 ToolCall"]
  }),
  endpoint("POST /v1/runs/{run_id}/trace-events", "A1", "product_console", "POST /api/a3/import/a1-run-result", {
    status: "plan_only",
    rbac: "project_developer_or_service_account",
    db: ["trace_events", "observations", "tool_calls", "api_import_receipts"],
    events: ["trace.ingested", "trace.validation_failed"],
    artifacts: ["trace_event_batch", "tool_call_batch"],
    usage: ["api_requests", "trace_event_count"],
    dependencies: ["A1 TraceEvent", "A1 Observation", "A1 ToolCall"]
  }),
  endpoint("POST /v1/runs/{run_id}/complete", "A1/A2", "release_gate", "GET /api/a3/releases/:releaseId/evidence-summary", {
    status: "plan_only",
    rbac: "project_developer_or_service_account",
    db: ["runs", "judge_results", "release_gates", "usage_ledger"],
    events: ["run.completed", "judge.completed", "release_gate.blocked"],
    artifacts: ["run_result", "judge_result", "release_gate_report"],
    usage: ["api_requests", "run_count", "judge_invocations"],
    dependencies: ["A1 RunResult", ...COMMON_A2]
  }),
  endpoint("POST /v1/artifacts/upload-url", "A1", "artifact_registry", "GET /api/a3/artifacts/registry", {
    status: "plan_only",
    rbac: "project_developer_or_service_account",
    db: ["artifacts", "artifact_manifests", "artifact_lifecycle_events"],
    events: ["artifact.upload_url_requested"],
    artifacts: ["artifact_upload_plan"],
    usage: ["api_requests", "artifact_bytes_uploaded"],
    dependencies: ["A1 artifact service", "A2 redaction policy"]
  }),
  endpoint("POST /v1/artifacts/complete", "A1/A2", "artifact_registry", "GET /api/a3/artifacts/registry", {
    status: "plan_only",
    rbac: "project_developer_or_service_account",
    db: ["artifacts", "artifact_manifests", "artifact_lifecycle_events"],
    events: ["artifact.uploaded", "artifact.redaction_scanned"],
    artifacts: ["artifact_manifest", "redaction_report"],
    usage: ["api_requests", "artifact_bytes_uploaded"],
    dependencies: ["A1 artifact service", "A2 redaction verifier"]
  }),
  endpoint("POST /v1/release-gates/evaluate", "A2/A3", "release_gate", "GET /api/a3/releases/:releaseId/evidence-health", {
    status: "implemented",
    rbac: "project_reviewer",
    db: ["release_gates", "judge_results", "release_evidence_summaries"],
    events: ["policy.evaluated", "release_gate.blocked", "release_gate.approved"],
    artifacts: ["release_gate_report", "release_evidence_summary"],
    usage: ["api_requests", "judge_invocations"],
    dependencies: COMMON_A2
  }),
  endpoint("POST /v1/release-gates/{release_gate_id}/waivers", "A2/A3", "review_workflow", "POST /api/a3/review/waivers", {
    status: "implemented",
    rbac: "reviewer_or_security_admin",
    db: ["waivers", "review_workflow_records", "audit_events"],
    events: ["waiver.requested", "waiver.accepted", "audit.mutation_recorded"],
    artifacts: ["waiver_request", "waiver_review"],
    usage: ["api_requests"],
    dependencies: ["A2 release policy", "A3 reviewer workflow"]
  }),
  endpoint("POST /v1/release-gates/{release_gate_id}/approvals", "A2/A3", "review_workflow", "POST /api/a3/review/approvals", {
    status: "implemented",
    rbac: "reviewer_or_owner",
    db: ["approvals", "review_workflow_records", "audit_events"],
    events: ["approval.recorded", "release_gate.approved"],
    artifacts: ["approval_record", "approval_review"],
    usage: ["api_requests"],
    dependencies: ["A2 release policy", "A3 reviewer workflow"]
  }),
  endpoint("POST /v1/release-gates/{release_gate_id}/denials", "A2/A3", "review_workflow", "POST /api/a3/review/denials", {
    status: "implemented",
    rbac: "reviewer_or_owner",
    db: ["denials", "review_workflow_records", "audit_events"],
    events: ["denial.recorded", "release_gate.denied"],
    artifacts: ["denial_record", "denial_review"],
    usage: ["api_requests"],
    dependencies: ["A2 release policy", "A3 reviewer workflow"]
  }),
  endpoint("GET /v1/releases/{release_id}/deployment-receipts", "A1/A2/A3", "release_gate", "GET /api/a3/deployment/receipts", {
    status: "read_only",
    rbac: "deployment:read",
    db: ["deployment_receipts", "audit_events", "event_outbox"],
    events: ["deployment.receipts_read"],
    artifacts: ["deployment_receipt_inbox"],
    usage: ["api_requests"],
    dependencies: ["A1 deployment receipts", "A2 same-candidate Trusted Spine", "A3 deployment handoff"]
  }),
  endpoint("POST /v1/releases/{release_id}/deployment-receipts", "A1/A3", "release_gate", "POST /api/a3/deployment/receipts", {
    status: "implemented",
    rbac: "deployment:submit",
    db: ["deployment_receipts", "idempotency_keys", "audit_events", "event_outbox"],
    events: ["deployment.receipt_submitted"],
    artifacts: ["deployment_receipt_metadata"],
    usage: ["api_requests", "deployment_receipt_submissions"],
    dependencies: ["A1 external verifier receipt", "A2 candidate and run selectors", "A3 metadata redaction boundary"]
  }),
  endpoint("POST /v1/releases/{release_id}/deployment-receipts/{receipt_id}/reviews", "A3", "review_workflow", "POST /api/a3/deployment/receipts/:receiptId/review", {
    status: "implemented",
    rbac: "deployment:review",
    db: ["deployment_receipts", "idempotency_keys", "audit_events", "event_outbox"],
    events: ["deployment.receipt_acknowledged", "deployment.receipt_rejected", "deployment.receipt_superseded"],
    artifacts: ["deployment_receipt_review"],
    usage: ["api_requests", "deployment_receipt_reviews"],
    dependencies: ["A1 authoritative verifier readback", "A2 Release Ready remains immutable", "A3 optimistic concurrency"]
  }),
  endpoint("GET /v1/evidence-bundles/{bundle_id}", "A1/A3", "audit_export", "GET /api/a3/artifacts/registry", {
    status: "read_only",
    rbac: "auditor",
    db: ["evidence_bundles", "bundle_signatures", "artifact_registry_entries"],
    events: ["bundle.read"],
    artifacts: ["audit_bundle_index", "audit_archive_manifest"],
    usage: ["api_requests", "report_exports"],
    dependencies: ["A1 bundle service", "A2 verifier correctness", "A3 audit export UI"]
  }),
  endpoint("POST /v1/evidence-bundles/{bundle_id}/verify", "A1/A2/A3", "audit_export", "GET /api/a3/artifacts/registry", {
    status: "read_only",
    rbac: "auditor",
    db: ["evidence_bundles", "bundle_signatures", "audit_events"],
    events: ["bundle.verified", "bundle.verification_failed"],
    artifacts: ["bundle_verification", "audit_archive_verification"],
    usage: ["api_requests", "report_exports"],
    dependencies: ["A1 bundle service", "A2 verifier correctness", "A3 audit export UI"]
  }),
  endpoint("GET /v1/reports", "A3", "report_center", "GET /api/a3/reports", {
    status: "implemented",
    rbac: "project_reader",
    db: ["shareable_reports", "report_share_links", "report_view_events"],
    events: ["report.listed"],
    artifacts: ["report_center_manifest"],
    usage: ["api_requests", "report_exports"],
    dependencies: ["A1/A2 source evidence"]
  }),
  endpoint("GET /v1/reports/{report_id}", "A3", "report_center", "GET /api/a3/reports/:reportId", {
    status: "implemented",
    rbac: "project_reader",
    db: ["shareable_reports", "report_view_events", "artifact_registry_entries"],
    events: ["report.read", "report.viewed"],
    artifacts: ["hosted_report", "markdown_report", "json_export"],
    usage: ["api_requests", "report_exports"],
    dependencies: ["A1/A2 source evidence"]
  }),
  endpoint("POST /v1/reports/{report_id}/share", "A3", "report_center", "POST /api/a3/reports/share", {
    status: "implemented",
    rbac: "project_reviewer_or_owner",
    db: ["shareable_reports", "report_share_links", "audit_events"],
    events: ["report.share_link_created", "artifact.redaction_scanned"],
    artifacts: ["hosted_report", "redaction_report"],
    usage: ["api_requests", "report_exports"],
    dependencies: ["A3 export redaction firewall", "A1/A2 source evidence"]
  }),
  endpoint("GET /v1/usage", "A1/A3", "usage_billing", "GET /api/a3/usage/ledger", {
    status: "read_only",
    rbac: "billing_admin_or_auditor",
    db: ["usage_events", "usage_rollups", "usage_ledger"],
    events: ["usage.read", "usage.recorded"],
    artifacts: ["usage_rollup", "usage_ledger"],
    usage: ["api_requests"],
    dependencies: ["A1 usage ledger", "A2 model cost policy", "A3 usage UI"]
  }),
  endpoint("GET /v1/billing/migration-readiness", "A1/A3", "usage_billing", "GET /api/a3/billing/migration-readiness", {
    status: "read_only",
    rbac: "billing:read",
    db: ["billing_migration_readiness", "billing_ledger_events", "billing_provider_events", "audit_events"],
    events: ["billing.migration_readiness_read", "billing.ledger_summary_read"],
    artifacts: ["billing_migration_readiness_snapshot"],
    usage: ["api_requests", "billing_readiness_reads"],
    dependencies: ["A1 read-only billing ledger summary", "A1 durable billing migration manifest", "A3 billing UI"],
    notes: "Maps future commercial billing migration readiness to A1 ledger/migration summaries; A3 remains read-only and cannot mutate billing provider state."
  }),
  endpoint("GET /v1/billing/subscription", "A1/A3", "usage_billing", "GET /api/a3/billing/readiness", {
    status: "read_only",
    rbac: "billing_admin",
    db: ["billing_customers", "billing_subscriptions", "billing_invoices", "usage_rollups"],
    events: ["billing.subscription_read"],
    artifacts: ["billing_readiness_snapshot"],
    usage: ["api_requests"],
    dependencies: ["A1 billing ledger", "A3 billing UI"]
  }),
  endpoint("POST /v1/billing/checkout", "A1/A3", "usage_billing", "GET /api/a3/billing/readiness", {
    status: "blocked_by_auth",
    rbac: "billing_admin",
    db: ["billing_customers", "billing_subscriptions", "audit_events"],
    events: ["billing.checkout_requested", "billing.mutation_blocked"],
    artifacts: ["billing_checkout_plan"],
    usage: ["api_requests"],
    dependencies: ["A1 payment backend", "A3 billing UI"]
  }),
  endpoint("POST /v1/billing/portal", "A1/A3", "usage_billing", "GET /api/a3/billing/readiness", {
    status: "blocked_by_auth",
    rbac: "billing_admin",
    db: ["billing_customers", "billing_subscriptions", "audit_events"],
    events: ["billing.portal_requested", "billing.mutation_blocked"],
    artifacts: ["billing_portal_plan"],
    usage: ["api_requests"],
    dependencies: ["A1 payment backend", "A3 billing UI"]
  }),
  endpoint("GET /v1/notification-channels", "A1/A3", "notification_control_plane", "GET /api/a3/notifications/control-plane", {
    status: "read_only",
    rbac: "project_reviewer_or_admin",
    db: ["notification_channels", "notification_subscriptions", "notification_templates"],
    events: ["notification.channels_read"],
    artifacts: ["notification_control_plane"],
    usage: ["api_requests"],
    dependencies: ["A1 hosted notification worker", "A2 release policy", "A3 notification UI"]
  }),
  endpoint("POST /v1/notifications/test", "A1/A3", "notification_control_plane", "GET /api/a3/notifications/control-plane", {
    status: "plan_only",
    rbac: "notifications:publish",
    db: ["notification_deliveries", "event_outbox", "audit_events", "usage_events"],
    events: ["notification.test_requested", "notification.delivery_audited"],
    artifacts: ["notification_test_plan"],
    usage: ["api_requests", "notification_plans"],
    dependencies: ["A1 encrypted connector reference", "A1 delivery worker", "A3 notification control plane"]
  }),
  endpoint("POST /v1/release-gates/{release_gate_id}/notifications", "A1/A2/A3", "notification_control_plane", "GET /api/a3/notifications/control-plane", {
    status: "plan_only",
    rbac: "notifications:publish",
    db: ["notification_deliveries", "webhook_deliveries", "event_outbox", "audit_events", "usage_events"],
    events: ["notification.slack_release_requested", "notification.teams_incident_requested", "notification.webhook_delivery_requested"],
    artifacts: ["slack_release_notification_plan", "teams_incident_notification_plan", "webhook_delivery_plan"],
    usage: ["api_requests", "notification_plans", "webhook_deliveries"],
    dependencies: ["A2 ReleaseGate", "A1 hosted notification worker", "A3 report/review workflow"]
  })
];
