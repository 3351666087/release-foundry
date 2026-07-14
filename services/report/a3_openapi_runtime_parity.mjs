#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { A3_SENSITIVE_ROUTE_PATTERNS } from "./a3_route_access_control.mjs";

const VERIFIED_PRINCIPAL_SECURITY = [
  { A1VerifiedSession: [] },
  { A1ServiceAccount: [] }
];

const TENANT_SCOPE_CONTRACT = {
  required: [
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id"
  ],
  source: "server_verified_a1_principal",
  client_declared_scope_authoritative: false,
  scope_match_required: true,
  cross_tenant_default: "sanitized_403_or_404"
};

const AUTH_CONTRACT = {
  required_for_hosted_saas: true,
  current_local_state: "contract_only_fail_closed",
  backend_owner: "A1",
  enforcement_owner: "A3 hosted API or same-origin BFF",
  principal_authority: "A1 server-side verifier",
  principal_source: "server_verified_a1_principal",
  accepted_principal_kinds: ["browser_session", "service_account"],
  client_declared_identity_authoritative: false,
  client_declared_role_authoritative: false,
  hosted_contract_only_not_production_proof: true
};

export function synchronizeA3OpenApiRuntimeParity(spec = {}) {
  const next = structuredClone(spec);
  next.info ||= {};
  next.info.version = "2026.07.14";
  next["x-contract-id"] = "a3_commercial_api_openapi_2026_07_14";
  next.paths ||= {};
  next.components ||= {};
  next.components.parameters ||= {};
  next.components.responses ||= {};
  next.components.schemas ||= {};
  next.components.parameters.ApiKeyId ||= identifierParameter("api_key_id", "A1 API-key handle; never raw key material.");
  next.components.responses.BadRequest = sanitizedBadRequestResponse();
  next.components.responses.RequestTimeout = sanitizedRequestBoundaryResponse(
    "The authenticated and authorized request body was not received within the configured deadline."
  );
  next.components.responses.PayloadTooLarge = sanitizedRequestBoundaryResponse(
    "The authenticated and authorized request body exceeds the configured byte limit."
  );
  next.components.responses.UnsupportedMediaType = sanitizedRequestBoundaryResponse(
    "The authenticated and authorized mutation requires application/json."
  );
  next.components.responses.UnprocessableEntity = sanitizedRequestBoundaryResponse(
    "The JSON body is valid JSON but is not a top-level object."
  );
  next.components.responses.ServiceUnavailable = sanitizedServiceUnavailableResponse();
  next.components.schemas.SanitizedBadRequestError = sanitizedBadRequestSchema();
  next.components.schemas.SanitizedServiceUnavailableError = sanitizedServiceUnavailableSchema();
  synchronizeDeliveryHandoffSchemas(next.components.schemas);
  next["x-request-boundary-contract"] = requestBoundaryContract();

  const operationIndex = openApiOperationIndex(next);
  for (const route of A3_SENSITIVE_ROUTE_PATTERNS) {
    const normalizedKey = routeKey(route.method, route.path_pattern);
    let operation = operationIndex.get(normalizedKey);
    if (!operation) {
      const path = runtimePathToOpenApi(route.path_pattern);
      const method = route.method.toLowerCase();
      next.paths[path] ||= {};
      operation = buildParityOperation(route, path);
      next.paths[path][method] = operation;
      operationIndex.set(normalizedKey, operation);
    }
    operation["x-rbac"] ||= {};
    operation["x-rbac"].operation_id = route.operation_id;
    operation["x-rbac"].permission = route.required_permission;
    operation.responses ||= {};
    operation.responses["503"] = { $ref: "#/components/responses/ServiceUnavailable" };
    applyRequestBoundaryContract(operation, route);
  }
  synchronizeDeploymentReceiptOperations(next);
  synchronizeMultimodalReviewOperations(next);
  synchronizeMultimodalProviderReadinessOperations(next);
  synchronizeSelfHostSandboxOperation(next);
  return next;
}

export function inspectA3OpenApiRuntimeParity(spec = {}) {
  const operations = openApiOperationIndex(spec);
  const missing = A3_SENSITIVE_ROUTE_PATTERNS.filter((route) => (
    !operations.has(routeKey(route.method, route.path_pattern))
  ));
  return {
    schema_version: "a3.openapi_runtime_parity.v1",
    runtime_operation_count: A3_SENSITIVE_ROUTE_PATTERNS.length,
    documented_runtime_operation_count: A3_SENSITIVE_ROUTE_PATTERNS.length - missing.length,
    missing: missing.map((route) => ({
      operation_id: route.operation_id,
      method: route.method,
      path: route.path_pattern,
      required_permission: route.required_permission
    })),
    complete: missing.length === 0
  };
}

export function runtimePathToOpenApi(path = "") {
  return String(path).replace(/:([A-Za-z0-9_]+)/g, "{$1}");
}

export function normalizeContractPath(path = "") {
  return String(path)
    .replace(/:([A-Za-z0-9_]+)/g, "{}")
    .replace(/\{[^}]+\}/g, "{}");
}

function synchronizeDeliveryHandoffSchemas(schemas) {
  const dashboard = schemas.DashboardSnapshot;
  if (dashboard) {
    dashboard.required = unique([
      ...(dashboard.required || []),
      "deployment_handoff",
      "deployment_receipt_inbox",
      "deployment_acceptance_projection",
      "multimodal_repeat_stability",
      "multimodal_provider_readiness"
    ]);
    dashboard.properties ||= {};
    dashboard.properties.deployment_handoff = { $ref: "#/components/schemas/DeploymentHandoff" };
    dashboard.properties.deployment_receipt_inbox = { $ref: "#/components/schemas/DeploymentReceiptInbox" };
    dashboard.properties.deployment_acceptance_projection = { $ref: "#/components/schemas/DeploymentAcceptanceProjection" };
    dashboard.properties.multimodal_repeat_stability = { $ref: "#/components/schemas/MultimodalRepeatStability" };
    dashboard.properties.multimodal_provider_readiness = { $ref: "#/components/schemas/MultimodalProviderReadiness" };
  }

  const comparison = schemas.ReleaseComparison;
  if (comparison) {
    comparison.required = unique([...(comparison.required || []), "runtime_authority_validation"]);
    comparison.properties ||= {};
    comparison.properties.runtime_authority_validation = {
      $ref: "#/components/schemas/ReleaseComparisonRuntimeAuthority"
    };
    Object.assign(comparison.properties.authority_boundary?.properties || {}, {
      current_status: { type: "string", enum: ["release_ready", "blocked", "review_required", "integrity_invalid", "not_ready"] },
      current_integrity_verified: { type: "boolean" },
      current_upstream_decision: { type: "string", enum: ["allow", "block", "review", "unknown"] },
      current_release_ready: { type: "boolean" },
      current_release_authorized: { type: "boolean" },
      current_reason_code: { type: "string" }
    });
    Object.assign(comparison.properties.safety?.properties || {}, {
      runtime_authority_recomputed: { type: "boolean", const: false },
      runtime_authority_attached_from_backend_verifier: { type: "boolean", const: true }
    });
  }

  schemas.ReleaseComparisonRuntimeAuthority = releaseComparisonRuntimeAuthoritySchema();
  schemas.DeploymentHandoffCheck = deploymentHandoffCheckSchema();
  schemas.CandidateBindingHandoff = candidateBindingHandoffSchema();
  schemas.DeploymentHandoff = deploymentHandoffSchema();
  schemas.DeploymentReceipt = deploymentReceiptSchema();
  schemas.DeploymentReceiptAuthoritativeReadback = deploymentReceiptAuthoritativeReadbackSchema();
  schemas.DeploymentReceiptInboxSlot = deploymentReceiptInboxSlotSchema();
  schemas.DeploymentReceiptInbox = deploymentReceiptInboxSchema();
  schemas.DeploymentAcceptanceProjection = deploymentAcceptanceProjectionSchema();
  schemas.DeploymentReceiptSubmission = deploymentReceiptSubmissionSchema();
  schemas.DeploymentReceiptReview = deploymentReceiptReviewSchema();
  schemas.DeploymentReceiptVerificationRequest = deploymentReceiptVerificationRequestSchema();
  schemas.DeploymentReceiptConflict = deploymentReceiptConflictSchema();
  schemas.SelfHostSandboxCheck = selfHostSandboxCheckSchema();
  schemas.SelfHostSandboxGap = selfHostSandboxGapSchema();
  schemas.PostgresRlsQualification = postgresRlsQualificationSchema();
  schemas.SelfHostSandboxCalibration = selfHostSandboxCalibrationSchema();
  schemas.A2MultimodalComparisonEnvelope = a2MultimodalComparisonEnvelopeSchema();
  schemas.MultimodalComparisonImportRequest = multimodalComparisonImportRequestSchema();
  schemas.MultimodalComparisonIngestReceipt = multimodalComparisonIngestReceiptSchema();
  schemas.MultimodalReviewQueue = multimodalReviewQueueSchema();
  schemas.A2MultimodalRepeatStabilityEnvelope = a2MultimodalRepeatStabilityEnvelopeSchema();
  schemas.MultimodalRepeatStabilityImportRequest = multimodalRepeatStabilityImportRequestSchema();
  schemas.MultimodalRepeatStabilityIngestReceipt = multimodalRepeatStabilityIngestReceiptSchema();
  schemas.MultimodalRepeatStability = multimodalRepeatStabilitySchema();
  schemas.A2MultimodalProviderReadinessEnvelope = a2MultimodalProviderReadinessEnvelopeSchema();
  schemas.MultimodalProviderReadinessImportRequest = multimodalProviderReadinessImportRequestSchema();
  schemas.MultimodalProviderReadinessIngestReceipt = multimodalProviderReadinessIngestReceiptSchema();
  schemas.MultimodalProviderReadiness = multimodalProviderReadinessSchema();
  schemas.MultimodalReviewAssignmentRequest = multimodalReviewAssignmentRequestSchema();
  schemas.MultimodalReviewAssignmentReceipt = multimodalReviewAssignmentReceiptSchema();
  schemas.MultimodalReviewOperationalState = multimodalReviewOperationalStateSchema();
  schemas.MultimodalReviewEvidenceReference = multimodalReviewEvidenceReferenceSchema();
  schemas.MultimodalReviewEvidenceRequest = multimodalReviewEvidenceRequestSchema();
  schemas.MultimodalReviewEvidenceRequestList = multimodalReviewEvidenceRequestListSchema();
  schemas.MultimodalReviewEvidenceRequestCreate = multimodalReviewEvidenceRequestCreateSchema();
  schemas.MultimodalReviewEvidenceSubmission = multimodalReviewEvidenceSubmissionSchema();
  schemas.MultimodalReviewEvidenceReview = multimodalReviewEvidenceReviewSchema();
  schemas.MultimodalReviewEvidenceRequestReceipt = multimodalReviewEvidenceRequestReceiptSchema();
}

function synchronizeSelfHostSandboxOperation(spec) {
  const operation = spec.paths?.["/api/a3/deployment/sandbox-calibration"]?.get;
  if (!operation) return;
  operation.operationId = "getA3SelfHostSandboxCalibration";
  operation.summary = "Read tenant-scoped A1 local self-host sandbox calibration evidence.";
  operation.tags = ["Operations", "Trust"];
  operation["x-schema-version"] = "a3.self_host_sandbox_calibration.v1";
  operation["x-evidence-boundary"] = {
    evidence_level: "sandbox_verified",
    production_verified: false,
    deployment_acceptance_mutated: false,
    a2_decision_recomputed: false,
    release_decision_authority: "A2"
  };
  operation.responses["200"] = {
    description: "Validated local A1 sandbox calibration; never production deployment proof.",
    content: {
      "application/json": {
        schema: { $ref: "#/components/schemas/SelfHostSandboxCalibration" }
      }
    }
  };
  operation.responses["404"] = {
    description: "No tenant-scoped sandbox calibration is available.",
    content: {
      "application/json": { schema: { type: "object", additionalProperties: true } }
    }
  };
}

function selfHostSandboxCheckSchema() {
  return {
    type: "object",
    required: ["id", "label", "status", "evidence_level", "contract_source", "observed", "production_proof"],
    properties: {
      id: { type: "string" },
      label: { type: "string" },
      status: { type: "string", enum: ["passed", "failed"] },
      evidence_level: { type: "string", enum: ["sandbox_verified", "sandbox_failed"] },
      contract_source: { type: "string" },
      observed: { type: "object", additionalProperties: true },
      production_proof: { type: "boolean", const: false }
    },
    additionalProperties: false
  };
}

function selfHostSandboxGapSchema() {
  return {
    type: "object",
    required: ["id", "status", "reason", "required_evidence"],
    properties: {
      id: { type: "string" },
      status: { type: "string", const: "not_run" },
      reason: { type: "string" },
      required_evidence: { type: "string" }
    },
    additionalProperties: false
  };
}

function postgresRlsQualificationSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "qualification_id", "observed_at", "source", "target_class",
      "status", "evidence_level", "database", "tenant_isolation", "authority_boundary", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.postgres_rls_qualification.v1" },
      qualification_id: { type: "string" },
      observed_at: { type: "string", format: "date-time" },
      source: { type: "string", const: "a3_postgres_rls_probe" },
      target_class: { type: "string", enum: ["local_ephemeral_postgres", "staging_postgres", "customer_vpc_postgres"] },
      status: { type: "string", const: "postgres_rls_verified" },
      evidence_level: { type: "string", const: "sandbox_verified" },
      database: {
        type: "object",
        required: [
          "engine", "server_version", "server_version_num", "migration_id", "migration_ids", "migration_sha256",
          "migration_apply_count", "migration_statement_count", "rls_enabled", "rls_forced", "policy_count",
          "runtime_role_nosuperuser", "runtime_role_nobypassrls"
        ],
        properties: {
          engine: { type: "string", const: "postgresql" },
          server_version: { type: "string" },
          server_version_num: { type: "integer", minimum: 1 },
          migration_id: { type: "string", const: "019_to_020_self_host_sandbox_rls" },
          migration_ids: {
            type: "array",
            minItems: 2,
            maxItems: 2,
            uniqueItems: true,
            items: { type: "string", enum: ["019_self_host_sandbox_calibrations", "020_self_host_sandbox_scope_hardening"] }
          },
          migration_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
          migration_apply_count: { type: "integer", const: 2 },
          migration_statement_count: { type: "integer", const: 2 },
          rls_enabled: { type: "boolean", const: true },
          rls_forced: { type: "boolean", const: true },
          policy_count: { type: "integer", minimum: 1 },
          runtime_role_nosuperuser: { type: "boolean", const: true },
          runtime_role_nobypassrls: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      tenant_isolation: {
        type: "object",
        required: [
          "scope_levels", "same_scope_read_count", "cross_scope_read_count", "visible_total_for_scope_a",
          "missing_scope_read_count", "same_scope_write_allowed", "cross_scope_write_denied"
        ],
        properties: {
          scope_levels: {
            type: "array",
            minItems: 5,
            maxItems: 5,
            uniqueItems: true,
            items: { type: "string", enum: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"] }
          },
          same_scope_read_count: { type: "integer", const: 1 },
          cross_scope_read_count: { type: "integer", const: 0 },
          visible_total_for_scope_a: { type: "integer", const: 1 },
          missing_scope_read_count: { type: "integer", const: 0 },
          same_scope_write_allowed: { type: "boolean", const: true },
          cross_scope_write_denied: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      authority_boundary: {
        type: "object",
        required: [
          "production_verified", "target_customer_environment_verified", "deployment_acceptance_mutated",
          "release_ready_mutated", "a2_decision_recomputed", "a2_release_decision_authority"
        ],
        properties: {
          production_verified: { type: "boolean", const: false },
          target_customer_environment_verified: { type: "boolean", const: false },
          deployment_acceptance_mutated: { type: "boolean", const: false },
          release_ready_mutated: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          a2_release_decision_authority: { type: "string", const: "A2" }
        },
        additionalProperties: false
      },
      safety: {
        type: "object",
        required: [
          "credentials_included", "dsn_included", "host_included", "raw_sql_output_included",
          "child_process_shell_used", "child_environment_allowlisted", "cleanup_completed"
        ],
        properties: {
          credentials_included: { type: "boolean", const: false },
          dsn_included: { type: "boolean", const: false },
          host_included: { type: "boolean", const: false },
          raw_sql_output_included: { type: "boolean", const: false },
          child_process_shell_used: { type: "boolean", const: false },
          child_environment_allowlisted: { type: "boolean", const: true },
          cleanup_completed: { type: "boolean", const: true }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false,
    description: "Live PostgreSQL RLS behavior receipt. Local/staging evidence is not customer-VPC production proof."
  };
}

function selfHostSandboxCalibrationSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "calibration_id", "observed_at", "source", "source_lane",
      "product_owner", "status", "tenant_scope", "summary", "checks", "production_gaps",
      "authority_boundary", "evidence_integrity", "safety", "dashboard_source", "access_contract"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.self_host_sandbox_calibration.v1" },
      calibration_id: { type: "string" },
      observed_at: { type: "string", format: "date-time" },
      source: { type: "string", const: "a1_local_runtime_probe" },
      source_lane: { type: "string", const: "A1" },
      product_owner: { type: "string", const: "A3" },
      status: { type: "string", enum: ["sandbox_verified", "sandbox_failed"] },
      tenant_scope: { $ref: "#/components/schemas/TenantScope" },
      summary: {
        type: "object",
        required: ["total_checks", "passed", "failed", "production_gap_count"],
        properties: {
          total_checks: { type: "integer", minimum: 0 },
          passed: { type: "integer", minimum: 0 },
          failed: { type: "integer", minimum: 0 },
          production_gap_count: { type: "integer", minimum: 0 }
        },
        additionalProperties: false
      },
      checks: { type: "array", items: { $ref: "#/components/schemas/SelfHostSandboxCheck" } },
      production_gaps: { type: "array", items: { $ref: "#/components/schemas/SelfHostSandboxGap" } },
      postgres_qualification: { $ref: "#/components/schemas/PostgresRlsQualification" },
      authority_boundary: {
        type: "object",
        required: [
          "evidence_level", "production_verified", "deployment_acceptance_mutated",
          "release_ready_mutated", "a2_decision_recomputed", "a2_release_decision_authority"
        ],
        properties: {
          evidence_level: { type: "string", enum: ["sandbox_verified", "sandbox_failed"] },
          production_verified: { type: "boolean", const: false },
          deployment_acceptance_mutated: { type: "boolean", const: false },
          release_ready_mutated: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          a2_release_decision_authority: { type: "string", const: "A2" }
        },
        additionalProperties: false
      },
      evidence_integrity: {
        type: "object",
        required: ["algorithm", "probe_payload_sha256", "source_schema_version", "validated"],
        properties: {
          algorithm: { type: "string", const: "sha256" },
          probe_payload_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
          postgres_qualification_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
          combined_payload_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
          source_schema_version: { type: "string", const: "a3.a1_self_host_sandbox_probe.v1" },
          validated: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      safety: { type: "object", additionalProperties: { type: "boolean" } },
      dashboard_source: { type: "string" },
      access_contract: {
        type: "object",
        required: ["required_permission", "tenant_scope_enforced", "hosted_read_audited", "raw_probe_payload_exposed"],
        properties: {
          required_permission: { type: "string", const: "deployment:read" },
          tenant_scope_enforced: { type: "boolean" },
          hosted_read_audited: { type: "boolean" },
          raw_probe_payload_exposed: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false,
    description: "Tenant-scoped local A1 behavior evidence. It never changes production acceptance or A2 authority."
  };
}

function releaseComparisonRuntimeAuthoritySchema() {
  return {
    type: "object",
    required: [
      "schema_version", "integrity_verified", "status", "upstream_decision", "release_ready",
      "reason_code", "blockers", "historical_candidate_decision", "historical_candidate_release_ready",
      "historical_integrity_marker", "current_release_authorized"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.release_comparison_runtime_authority.v1" },
      integrity_verified: { type: "boolean" },
      status: { type: "string", enum: ["release_ready", "blocked", "review_required", "integrity_invalid", "not_ready"] },
      upstream_decision: { type: "string", enum: ["allow", "block", "review", "unknown"] },
      release_ready: { type: "boolean" },
      reason_code: { type: "string" },
      blockers: { type: "array", items: { type: "string" } },
      decision_record_id: { type: ["string", "null"] },
      decision_ledger_head_hash: { type: ["string", "null"] },
      historical_candidate_decision: { type: "string", enum: ["allow", "block", "review", "unknown"] },
      historical_candidate_release_ready: { type: "boolean" },
      historical_integrity_marker: { type: "boolean" },
      current_release_authorized: { type: "boolean" }
    },
    additionalProperties: false,
    description: "Current backend A2 Trusted Spine validation attached to a sealed historical comparison. A3 never recomputes A2 authority."
  };
}

function deploymentHandoffCheckSchema() {
  return {
    type: "object",
    required: ["id", "label", "owner", "status", "evidence_class", "evidence_level", "production_proof", "next_action", "required_receipt"],
    properties: {
      id: { type: "string" },
      label: { type: "string" },
      owner: { type: "string", enum: ["A1", "A2", "A1/A3", "A3", "Repository maintainer", "Unassigned"] },
      status: { type: "string", enum: ["passed", "blocked", "not_proven"] },
      evidence_class: { type: "string" },
      evidence_level: { type: "string", enum: ["production_verified", "locally_authoritative", "locally_verified", "contract_only", "not_proven"] },
      production_proof: { type: "boolean" },
      evidence_ref: {},
      blocked_reason: { type: ["string", "null"] },
      next_action: { type: "string" },
      required_receipt: { type: "string" }
    },
    additionalProperties: false
  };
}

function candidateBindingHandoffSchema() {
  return {
    type: "object",
    required: ["schema_version", "status", "same_candidate_bound", "expected", "observed_a2", "checks", "runtime_authority", "historical_packet", "next_action_owner", "next_action"],
    properties: {
      schema_version: { type: "string", const: "a3.candidate_binding_handoff.v1" },
      status: { type: "string", enum: ["bound", "integrity_invalid"] },
      same_candidate_bound: { type: "boolean" },
      expected: { type: "object", additionalProperties: true },
      observed_a2: { type: "object", additionalProperties: true },
      checks: {
        type: "array",
        items: {
          type: "object",
          required: ["id", "status", "passed", "requirement"],
          properties: {
            id: { type: "string" },
            status: { type: "string", enum: ["passed", "failed"] },
            passed: { type: "boolean" },
            requirement: { type: "string" }
          },
          additionalProperties: false
        }
      },
      runtime_authority: { type: "object", additionalProperties: true },
      historical_packet: { type: "object", additionalProperties: true },
      next_action_owner: { type: "string" },
      next_action: { type: "string" }
    },
    additionalProperties: false
  };
}

function deploymentHandoffSchema() {
  return {
    type: "object",
    required: ["schema_version", "source", "status", "production_ready", "summary", "candidate_binding", "owner_groups", "blocking_items", "next_actions", "safety"],
    properties: {
      schema_version: { type: "string", const: "a3.deployment_handoff.v1" },
      source: { type: "string" },
      status: { type: "string", enum: ["ready", "blocked"] },
      production_ready: { type: "boolean", description: "Always fail-closed until all upstream and deployed environment receipts are authoritative." },
      summary: {
        type: "object",
        required: ["total_checks", "passed", "blocked_or_not_proven", "production_proof_count", "owner_group_count", "candidate_binding_status", "golden_path_passed", "golden_path_total"],
        properties: {
          total_checks: { type: "integer", minimum: 0 },
          passed: { type: "integer", minimum: 0 },
          blocked_or_not_proven: { type: "integer", minimum: 0 },
          production_proof_count: { type: "integer", minimum: 0 },
          owner_group_count: { type: "integer", minimum: 0 },
          candidate_binding_status: { type: "string", enum: ["bound", "integrity_invalid"] },
          golden_path_passed: { type: "integer", minimum: 0 },
          golden_path_total: { type: "integer", minimum: 0 }
        },
        additionalProperties: false
      },
      candidate_binding: { $ref: "#/components/schemas/CandidateBindingHandoff" },
      owner_groups: {
        type: "array",
        items: {
          type: "object",
          required: ["id", "owner", "label", "dependency", "status", "total", "passed", "blocked", "production_proof_count", "actionable_by_a3", "blocking_ids", "checks"],
          properties: {
            id: { type: "string" },
            owner: { type: "string" },
            label: { type: "string" },
            dependency: { type: "string" },
            status: { type: "string", enum: ["passed", "blocked"] },
            total: { type: "integer", minimum: 0 },
            passed: { type: "integer", minimum: 0 },
            blocked: { type: "integer", minimum: 0 },
            production_proof_count: { type: "integer", minimum: 0 },
            actionable_by_a3: { type: "boolean" },
            blocking_ids: { type: "array", items: { type: "string" } },
            checks: { type: "array", items: { $ref: "#/components/schemas/DeploymentHandoffCheck" } }
          },
          additionalProperties: false
        }
      },
      blocking_items: { type: "array", items: { $ref: "#/components/schemas/DeploymentHandoffCheck" } },
      next_actions: {
        type: "array",
        items: {
          type: "object",
          required: ["id", "owner", "action", "required_receipt"],
          properties: {
            id: { type: "string" }, owner: { type: "string" }, action: { type: "string" }, required_receipt: { type: "string" }
          },
          additionalProperties: false
        }
      },
      safety: {
        type: "object",
        required: ["source_status_overridden", "a2_decision_recomputed", "a2_release_ready_recomputed", "historical_packet_treated_as_current_authority", "contract_only_claimed_as_production", "secret_values_allowed"],
        properties: {
          source_status_overridden: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          a2_release_ready_recomputed: { type: "boolean", const: false },
          historical_packet_treated_as_current_authority: { type: "boolean", const: false },
          contract_only_claimed_as_production: { type: "boolean", const: false },
          secret_values_allowed: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
}

function deploymentReceiptSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "receipt_id", "source", "tenant_scope", "blocker_id", "candidate_id", "run_id",
      "evidence_ref", "evidence_sha256", "evidence_kind", "verifier_class", "status", "version",
      "authority_validation", "acceptance_effect", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.deployment_receipt.v1" },
      receipt_id: { type: "string", minLength: 1, maxLength: 160 },
      source: { type: "string" },
      tenant_scope: { $ref: "#/components/schemas/TenantScope" },
      blocker_id: { type: "string" },
      owner: { type: "string" },
      candidate_id: { type: "string" },
      run_id: { type: "string" },
      evidence_ref: { type: "string", description: "Opaque metadata reference only; URLs and local absolute paths are forbidden." },
      evidence_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
      evidence_kind: { type: "string" },
      verifier_class: { type: "string" },
      captured_at: { type: ["string", "null"], format: "date-time" },
      selectors: { type: "object", additionalProperties: { type: "string" } },
      status: { type: "string", enum: ["submitted", "acknowledged", "rejected", "superseded"] },
      version: { type: "integer", minimum: 1 },
      submitted_at: { type: ["string", "null"], format: "date-time" },
      submitted_by_hash: { type: "string" },
      reviewed_at: { type: ["string", "null"], format: "date-time" },
      reviewed_by_hash: { type: ["string", "null"] },
      review_reason_code: { type: ["string", "null"] },
      authority_validation: {
        type: "object",
        required: ["status", "production_verified", "authoritative_readback_id"],
        properties: {
          status: { type: "string" },
          production_verified: { type: "boolean" },
          authoritative_readback_id: { type: ["string", "null"] },
          verified_at: { type: ["string", "null"], format: "date-time" },
          verifier_authority: { type: ["string", "null"] },
          attestation_sha256: { type: ["string", "null"], pattern: "^sha256:[a-f0-9]{64}$" }
        },
        additionalProperties: false
      },
      production_verification: {
        oneOf: [{ $ref: "#/components/schemas/DeploymentReceiptAuthoritativeReadback" }, { type: "null" }]
      },
      acceptance_effect: {
        type: "object",
        required: ["changes_deployment_acceptance", "changes_release_ready", "reason"],
        properties: {
          changes_deployment_acceptance: { type: "boolean", const: false },
          changes_release_ready: { type: "boolean", const: false },
          reason: { type: "string" }
        },
        additionalProperties: false
      },
      history: { type: "array", items: { type: "object", additionalProperties: true } },
      safety: {
        type: "object",
        required: [
          "raw_evidence_embedded", "raw_secret_values_allowed", "raw_signed_urls_allowed",
          "production_verified_by_submission", "a2_decision_recomputed", "deployment_acceptance_mutated"
        ],
        properties: {
          raw_evidence_embedded: { type: "boolean", const: false },
          raw_secret_values_allowed: { type: "boolean", const: false },
          raw_signed_urls_allowed: { type: "boolean", const: false },
          production_verified_by_submission: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          deployment_acceptance_mutated: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: true,
    description: "Sanitized receipt metadata. Submission or acknowledgement never counts as production verification; only a hash-valid server readback can populate authority_validation."
  };
}

function deploymentReceiptAuthoritativeReadbackSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "readback_id", "readback_hash", "external_readback_id_alias", "receipt_id",
      "blocker_id", "candidate_id", "run_id", "tenant_scope", "evidence_sha256", "verifier_class",
      "verifier_authority", "verification_status", "reason_code", "verified_at", "attestation_sha256",
      "required_claims", "claims", "resolver_id_alias", "sequence", "previous_readback_hash",
      "binding_validation", "production_verified", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.deployment_receipt_authoritative_readback.v1" },
      readback_id: { type: "string" },
      readback_hash: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
      external_readback_id_alias: { type: "string" },
      source: { type: "string" },
      receipt_id: { type: "string" },
      blocker_id: { type: "string" },
      candidate_id: { type: "string" },
      run_id: { type: "string" },
      tenant_scope: { $ref: "#/components/schemas/TenantScope" },
      evidence_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
      verifier_class: { type: "string" },
      verifier_authority: { type: "string" },
      verification_status: { type: "string", enum: ["verified", "rejected"] },
      reason_code: { type: "string" },
      verified_at: { type: "string", format: "date-time" },
      attestation_sha256: { type: "string", pattern: "^sha256:[a-f0-9]{64}$" },
      required_claims: { type: "array", items: { type: "string" }, minItems: 2, uniqueItems: true },
      claims: { type: "object", additionalProperties: { type: "boolean" } },
      resolver_id_alias: { type: "string" },
      sequence: { type: "integer", minimum: 1 },
      previous_readback_hash: { type: ["string", "null"], pattern: "^sha256:[a-f0-9]{64}$" },
      binding_validation: {
        type: "object",
        required: ["receipt_id", "blocker_id", "candidate_id", "run_id", "tenant_scope", "evidence_sha256", "verifier_class", "verifier_authority", "required_claims", "all_passed"],
        additionalProperties: { type: "boolean" }
      },
      production_verified: { type: "boolean" },
      safety: {
        type: "object",
        required: ["trusted_server_resolver", "service_account_principal_required", "client_supplied_verification_result_used", "raw_evidence_embedded", "raw_secret_values_allowed", "a2_decision_recomputed", "source_acceptance_mutated"],
        properties: {
          trusted_server_resolver: { type: "boolean", const: true },
          service_account_principal_required: { type: "boolean", const: true },
          client_supplied_verification_result_used: { type: "boolean", const: false },
          raw_evidence_embedded: { type: "boolean", const: false },
          raw_secret_values_allowed: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          source_acceptance_mutated: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: true,
    description: "Immutable, hash-chained readback produced by a server-only trusted verifier resolver."
  };
}

function deploymentReceiptInboxSlotSchema() {
  return {
    type: "object",
    required: [
      "blocker_id", "label", "owner", "required_receipt", "evidence_kind", "verifier_class",
      "receipt_count", "latest_receipt", "intake_status", "production_verified", "deployment_check_status"
    ],
    properties: {
      blocker_id: { type: "string" },
      label: { type: "string" },
      owner: { type: "string" },
      required_receipt: { type: "string" },
      evidence_kind: { type: "string" },
      verifier_class: { type: "string" },
      receipt_count: { type: "integer", minimum: 0 },
      latest_receipt: { oneOf: [{ $ref: "#/components/schemas/DeploymentReceipt" }, { type: "null" }] },
      intake_status: { type: "string", enum: ["missing", "submitted", "acknowledged", "rejected", "superseded"] },
      production_verified: { type: "boolean" },
      authoritative_readback_id: { type: ["string", "null"] },
      deployment_check_status: { type: "string", enum: ["blocked", "not_proven", "production_verified"] }
    },
    additionalProperties: false
  };
}

function deploymentReceiptInboxSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source", "tenant_scope", "candidate_id", "run_id", "receipt_count",
      "blocker_slot_count", "missing_slot_count", "submitted_or_acknowledged_count",
      "authoritative_readback_count", "production_verified_count", "slots", "receipts",
      "authoritative_readbacks", "workflow", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.deployment_receipt_inbox.v1" },
      source: { type: "string" },
      tenant_scope: { $ref: "#/components/schemas/TenantScope" },
      candidate_id: { type: "string" },
      run_id: { type: "string" },
      receipt_count: { type: "integer", minimum: 0 },
      excluded_candidate_receipt_count: { type: "integer", minimum: 0 },
      authoritative_readback_count: { type: "integer", minimum: 0 },
      excluded_authoritative_readback_count: { type: "integer", minimum: 0 },
      status_counts: { type: "object", additionalProperties: { type: "integer", minimum: 0 } },
      readback_status_counts: { type: "object", additionalProperties: { type: "integer", minimum: 0 } },
      blocker_slot_count: { type: "integer", minimum: 0 },
      missing_slot_count: { type: "integer", minimum: 0 },
      submitted_or_acknowledged_count: { type: "integer", minimum: 0 },
      production_verified_count: { type: "integer", minimum: 0 },
      slots: { type: "array", items: { $ref: "#/components/schemas/DeploymentReceiptInboxSlot" } },
      receipts: { type: "array", items: { $ref: "#/components/schemas/DeploymentReceipt" } },
      authoritative_readbacks: { type: "array", items: { $ref: "#/components/schemas/DeploymentReceiptAuthoritativeReadback" } },
      workflow: { type: "object", additionalProperties: true },
      safety: {
        type: "object",
        required: [
          "a2_decision_recomputed", "deployment_acceptance_mutated", "submitted_receipt_treated_as_production_proof",
          "reviewer_acknowledgement_treated_as_production_proof", "only_trusted_server_readbacks_can_produce_verification",
          "raw_evidence_embedded", "secret_values_allowed", "signed_urls_allowed"
        ],
        properties: {
          a2_decision_recomputed: { type: "boolean", const: false },
          deployment_acceptance_mutated: { type: "boolean", const: false },
          submitted_receipt_treated_as_production_proof: { type: "boolean", const: false },
          reviewer_acknowledgement_treated_as_production_proof: { type: "boolean", const: false },
          only_trusted_server_readbacks_can_produce_verification: { type: "boolean", const: true },
          raw_evidence_embedded: { type: "boolean", const: false },
          secret_values_allowed: { type: "boolean", const: false },
          signed_urls_allowed: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
}

function deploymentAcceptanceProjectionSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source_acceptance_id", "source_acceptance_status", "source_passed",
      "status", "production_accepted", "projected_production_accepted", "requires_acceptance_rebuild",
      "summary", "changed_check_ids", "blocking_check_ids", "checks", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.deployment_acceptance_projection.v1" },
      source_acceptance_id: { type: ["string", "null"] },
      source_acceptance_status: { type: "string" },
      source_passed: { type: "integer", minimum: 0 },
      status: { type: "string", enum: ["blocked", "ready_for_rebuild"] },
      production_accepted: { type: "boolean", const: false },
      projected_production_accepted: { type: "boolean" },
      requires_acceptance_rebuild: { type: "boolean" },
      summary: {
        type: "object",
        required: ["total_checks", "projected_passed", "projected_blocked_or_not_proven", "authoritative_receipt_check_count"],
        additionalProperties: { type: "integer", minimum: 0 }
      },
      changed_check_ids: { type: "array", items: { type: "string" }, uniqueItems: true },
      blocking_check_ids: { type: "array", items: { type: "string" }, uniqueItems: true },
      checks: { type: "array", items: { type: "object", additionalProperties: true } },
      safety: {
        type: "object",
        required: ["source_acceptance_mutated", "a2_decision_recomputed", "a2_release_ready_recomputed", "projection_claimed_as_sealed_acceptance", "release_artifact_rebuild_required", "raw_evidence_embedded"],
        properties: {
          source_acceptance_mutated: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          a2_release_ready_recomputed: { type: "boolean", const: false },
          projection_claimed_as_sealed_acceptance: { type: "boolean", const: false },
          release_artifact_rebuild_required: { type: "boolean" },
          raw_evidence_embedded: { type: "boolean", const: false }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false,
    description: "Read-only projection of hash-valid readbacks onto the source acceptance. A new sealed acceptance artifact is still required."
  };
}

function deploymentReceiptSubmissionSchema() {
  return {
    type: "object",
    required: ["source", "receipt"],
    properties: {
      source: { type: "string" },
      receipt: {
        type: "object",
        required: [
          "blocker_id", "candidate_id", "run_id", "evidence_ref", "evidence_sha256",
          "evidence_kind", "verifier_class", "captured_at"
        ],
        properties: {
          blocker_id: { type: "string" }, candidate_id: { type: "string" }, run_id: { type: "string" },
          evidence_ref: { type: "string", pattern: "^[A-Za-z0-9][A-Za-z0-9._:/-]*$" },
          evidence_sha256: { type: "string", pattern: "^(?:sha256:)?[a-fA-F0-9]{64}$" },
          evidence_kind: { type: "string" }, verifier_class: { type: "string" },
          captured_at: { type: "string", format: "date-time" },
          selectors: { type: "object", additionalProperties: { type: "string" }, maxProperties: 12 }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
}

function deploymentReceiptReviewSchema() {
  return {
    type: "object",
    required: ["source", "review"],
    properties: {
      source: { type: "string" },
      review: {
        type: "object",
        required: ["action", "reason_code", "expected_version"],
        properties: {
          action: { type: "string", enum: ["acknowledge", "reject", "supersede"] },
          reason_code: { type: "string" },
          expected_version: { type: "integer", minimum: 1 }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
}

function deploymentReceiptVerificationRequestSchema() {
  return {
    type: "object",
    required: ["source", "expected_version"],
    properties: {
      source: { type: "string" },
      expected_version: { type: "integer", minimum: 1 }
    },
    additionalProperties: false,
    description: "Trigger only. Verification status, claims, evidence, authority, and attestation are supplied by the configured server resolver, never by this request."
  };
}

function deploymentReceiptConflictSchema() {
  return {
    type: "object",
    required: ["schema_version", "error", "request_type", "details"],
    properties: {
      schema_version: { type: "string", const: "a3.api_validation_error.v1" },
      error: { type: "string", enum: ["version_conflict", "idempotency_conflict"] },
      request_type: { type: "string" },
      details: { type: "array", items: { type: "object", additionalProperties: true } }
    },
    additionalProperties: true
  };
}

function synchronizeDeploymentReceiptOperations(spec) {
  const read = spec.paths?.["/api/a3/deployment/receipts"]?.get;
  const submit = spec.paths?.["/api/a3/deployment/receipts"]?.post;
  const review = spec.paths?.["/api/a3/deployment/receipts/{receiptId}/review"]?.post;
  const verify = spec.paths?.["/internal/a3/deployment/receipts/{receiptId}/verify"]?.post;
  if (read) {
    read.summary = "Read the candidate-bound deployment receipt inbox.";
    read["x-schema-version"] = "a3.deployment_receipt_inbox.v1";
    read.responses["200"] = typedJsonResponse("Sanitized candidate-bound receipt inbox.", "DeploymentReceiptInbox");
  }
  if (submit) {
    submit.summary = "Submit sanitized deployment receipt metadata.";
    submit["x-schema-version"] = "a3.deployment_receipt.v1";
    submit.parameters = withIdempotencyHeader(submit.parameters);
    submit.requestBody = typedJsonRequest("DeploymentReceiptSubmission");
    delete submit.responses["202"];
    submit.responses["201"] = typedJsonResponse("Receipt metadata accepted without production promotion.", "DeploymentReceipt");
    submit.responses["409"] = typedJsonResponse("Idempotency conflict.", "DeploymentReceiptConflict");
    submit["x-audit"] = { events: ["deployment.receipt_submitted"], payload_policy: "ids_hashes_refs_status_counts_only" };
  }
  if (review) {
    review.summary = "Acknowledge, reject, or supersede receipt metadata with optimistic concurrency.";
    review["x-schema-version"] = "a3.deployment_receipt.v1";
    review.parameters = withIdempotencyHeader(review.parameters);
    review.requestBody = typedJsonRequest("DeploymentReceiptReview");
    delete review.responses["202"];
    review.responses["200"] = typedJsonResponse("Review recorded without changing deployment or A2 authority.", "DeploymentReceipt");
    review.responses["409"] = typedJsonResponse("Receipt version or idempotency conflict.", "DeploymentReceiptConflict");
    review["x-audit"] = { events: ["deployment.receipt_acknowledged", "deployment.receipt_rejected", "deployment.receipt_superseded"], payload_policy: "ids_hashes_refs_status_counts_only" };
  }
  if (verify) {
    verify.summary = "Invoke the server-only authoritative deployment receipt verifier.";
    verify["x-schema-version"] = "a3.deployment_receipt_authoritative_readback.v1";
    verify["x-browser-callable"] = false;
    verify["x-auth"] = {
      ...structuredClone(AUTH_CONTRACT),
      accepted_principal_kinds: ["service_account"],
      service_account_only: true,
      hosted_enforcement_required: true
    };
    verify["x-access-class"] = "internal_service_account_write";
    verify.security = [{ A1ServiceAccount: [] }];
    verify.parameters = withIdempotencyHeader(verify.parameters);
    verify.requestBody = typedJsonRequest("DeploymentReceiptVerificationRequest");
    delete verify.responses["202"];
    verify.responses["200"] = typedJsonResponse("Immutable authoritative readback produced by the trusted server resolver.", "DeploymentReceiptAuthoritativeReadback");
    verify.responses["409"] = typedJsonResponse("Receipt version or idempotency conflict.", "DeploymentReceiptConflict");
    verify.responses["502"] = { $ref: "#/components/responses/ServiceUnavailable" };
    verify["x-audit"] = { events: ["deployment.receipt_authoritatively_verified", "deployment.receipt_authoritatively_rejected"], payload_policy: "ids_hashes_claims_and_attestation_only" };
    verify["x-verifier-boundary"] = {
      client_supplied_verification_result_used: false,
      trusted_resolver_required: true,
      receipt_candidate_run_scope_hash_binding_required: true,
      blocker_specific_claims_required: true,
      raw_evidence_forbidden: true
    };
  }
}

function synchronizeMultimodalReviewOperations(spec) {
  const importOperation = spec.paths?.["/api/a3/import/a2-multimodal-comparison"]?.post;
  const readOperation = spec.paths?.["/api/a3/review/multimodal-queue"]?.get;
  const repeatStabilityImportOperation = spec.paths?.["/api/a3/import/a2-multimodal-repeat-stability"]?.post;
  const repeatStabilityReadOperation = spec.paths?.["/api/a3/review/multimodal-repeat-stability"]?.get;
  const assignmentOperation = spec.paths?.["/api/a3/review/multimodal-queue/{queueId}/assignment"]?.post;
  const evidenceRequestReadOperation = spec.paths?.["/api/a3/review/multimodal-queue/{queueId}/evidence-requests"]?.get;
  const evidenceRequestCreateOperation = spec.paths?.["/api/a3/review/multimodal-queue/{queueId}/evidence-requests"]?.post;
  const evidenceSubmissionOperation = spec.paths?.["/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/submissions"]?.post;
  const evidenceReviewOperation = spec.paths?.["/api/a3/review/multimodal-queue/{queueId}/evidence-requests/{requestId}/review"]?.post;
  if (importOperation) {
    importOperation.operationId = "a3ImportA2MultimodalComparison";
    importOperation.summary = "Import a public-safe A2 multimodal comparison into the tenant review queue.";
    importOperation.tags = ["Review", "Operations"];
    importOperation["x-schema-version"] = "a3.a2_multimodal_comparison_ingest.v1";
    importOperation.parameters = withIdempotencyHeader(importOperation.parameters);
    importOperation.requestBody = typedJsonRequest("MultimodalComparisonImportRequest");
    delete importOperation.responses["202"];
    importOperation.responses["201"] = typedJsonResponse(
      "Comparison accepted as non-authoritative reviewer evidence.",
      "MultimodalComparisonIngestReceipt"
    );
    importOperation.responses["409"] = typedJsonResponse("Idempotency conflict.", "DeploymentReceiptConflict");
    importOperation["x-audit"] = {
      events: ["a2.multimodal_comparison_imported"],
      payload_policy: "ids_hashes_refs_status_counts_only"
    };
    importOperation["x-authority-boundary"] = multimodalAuthorityBoundary();
  }
  if (readOperation) {
    readOperation.operationId = "a3ReadMultimodalReviewQueue";
    readOperation.summary = "Read tenant-scoped, non-authoritative multimodal disagreement evidence.";
    readOperation.tags = ["Review"];
    readOperation["x-schema-version"] = "a3.multimodal_review_queue.v1";
    readOperation.responses["200"] = typedJsonResponse(
      "Public-safe multimodal disagreement review queue.",
      "MultimodalReviewQueue"
    );
    readOperation["x-authority-boundary"] = multimodalAuthorityBoundary();
  }
  if (repeatStabilityImportOperation) {
    repeatStabilityImportOperation.operationId = "a3ImportA2MultimodalRepeatStability";
    repeatStabilityImportOperation.summary = "Import public-safe multi-repeat calibration stability evidence.";
    repeatStabilityImportOperation.tags = ["Review", "Evidence", "Operations"];
    repeatStabilityImportOperation["x-schema-version"] = "a3.a2_multimodal_repeat_stability_ingest.v1";
    repeatStabilityImportOperation.parameters = withIdempotencyHeader(repeatStabilityImportOperation.parameters);
    repeatStabilityImportOperation.requestBody = typedJsonRequest("MultimodalRepeatStabilityImportRequest");
    delete repeatStabilityImportOperation.responses["202"];
    repeatStabilityImportOperation.responses["201"] = typedJsonResponse(
      "Repeat stability accepted as non-authoritative aggregate evidence.",
      "MultimodalRepeatStabilityIngestReceipt"
    );
    repeatStabilityImportOperation.responses["409"] = typedJsonResponse(
      "Idempotency conflict.",
      "DeploymentReceiptConflict"
    );
    repeatStabilityImportOperation["x-audit"] = {
      events: ["a2.multimodal_repeat_stability_imported"],
      payload_policy: "hashes_aggregate_metrics_counts_states_and_reason_codes_only"
    };
    repeatStabilityImportOperation["x-evidence-boundary"] = multimodalRepeatStabilityEvidenceBoundary();
    repeatStabilityImportOperation["x-authority-boundary"] = multimodalRepeatStabilityAuthorityBoundary();
  }
  if (repeatStabilityReadOperation) {
    repeatStabilityReadOperation.operationId = "a3ReadMultimodalRepeatStability";
    repeatStabilityReadOperation.summary = "Read tenant-scoped multi-repeat calibration stability evidence.";
    repeatStabilityReadOperation.tags = ["Review", "Evidence"];
    repeatStabilityReadOperation["x-schema-version"] = "a3.multimodal_repeat_stability.v1";
    repeatStabilityReadOperation.responses["200"] = typedJsonResponse(
      "Public-safe repeat stability projection without release authority.",
      "MultimodalRepeatStability"
    );
    repeatStabilityReadOperation["x-evidence-boundary"] = multimodalRepeatStabilityEvidenceBoundary();
    repeatStabilityReadOperation["x-authority-boundary"] = multimodalRepeatStabilityAuthorityBoundary();
  }
  if (assignmentOperation) {
    assignmentOperation.operationId = "a3ManageMultimodalReviewAssignment";
    assignmentOperation.summary = "Claim, renew, release, or transfer one tenant-scoped multimodal review lease.";
    assignmentOperation.tags = ["Review", "Operations"];
    assignmentOperation["x-schema-version"] = "a3.multimodal_review_assignment_receipt.v1";
    assignmentOperation.parameters = withIdempotencyHeader(assignmentOperation.parameters);
    assignmentOperation.requestBody = typedJsonRequest("MultimodalReviewAssignmentRequest");
    delete assignmentOperation.responses["202"];
    assignmentOperation.responses["200"] = typedJsonResponse(
      "Append-only assignment event accepted with optimistic concurrency.",
      "MultimodalReviewAssignmentReceipt"
    );
    assignmentOperation.responses["409"] = typedJsonResponse(
      "The lease is active, stale, or owned by another reviewer.",
      "DeploymentReceiptConflict"
    );
    assignmentOperation["x-audit"] = {
      events: [
        "review.multimodal_assignment.claimed",
        "review.multimodal_assignment.renewed",
        "review.multimodal_assignment.released",
        "review.multimodal_assignment.transferred",
        "review.multimodal_assignment.reclaimed_after_expiry"
      ],
      payload_policy: "queue_ids_hashes_versions_lease_times_and_reason_codes_only"
    };
    assignmentOperation["x-concurrency"] = {
      strategy: "optimistic_expected_version_plus_time_bounded_lease",
      stale_write_http_status: 409,
      idempotency_header_only: true
    };
    assignmentOperation["x-authority-boundary"] = multimodalAuthorityBoundary();
  }
  if (evidenceRequestReadOperation) {
    evidenceRequestReadOperation.operationId = "a3ReadMultimodalReviewEvidenceRequests";
    evidenceRequestReadOperation.summary = "Read hash-only evidence requests for one tenant-scoped review item.";
    evidenceRequestReadOperation.tags = ["Review", "Evidence"];
    evidenceRequestReadOperation["x-schema-version"] = "a3.multimodal_review_evidence_request_list.v1";
    evidenceRequestReadOperation.responses["200"] = typedJsonResponse(
      "Evidence-request states and hash references without raw evidence.",
      "MultimodalReviewEvidenceRequestList"
    );
    evidenceRequestReadOperation["x-authority-boundary"] = multimodalEvidenceRequestAuthorityBoundary();
  }
  if (evidenceRequestCreateOperation) {
    configureEvidenceRequestMutation(evidenceRequestCreateOperation, {
      operationId: "a3CreateMultimodalReviewEvidenceRequest",
      summary: "Request additional execution, evaluation, media, provider, or candidate-binding evidence.",
      schemaVersion: "a3.multimodal_review_evidence_request_receipt.v1",
      requestSchema: "MultimodalReviewEvidenceRequestCreate",
      successStatus: "201",
      successDescription: "Evidence request opened by the active assignment owner.",
      events: ["review.multimodal_evidence_request.requested"],
      assignmentOwnerRequired: true
    });
  }
  if (evidenceSubmissionOperation) {
    configureEvidenceRequestMutation(evidenceSubmissionOperation, {
      operationId: "a3SubmitMultimodalReviewEvidenceRequest",
      summary: "Submit all requested evidence as allowlisted SHA-256 references.",
      schemaVersion: "a3.multimodal_review_evidence_request_receipt.v1",
      requestSchema: "MultimodalReviewEvidenceSubmission",
      successStatus: "200",
      successDescription: "Hash-only evidence submission recorded for reviewer inspection.",
      events: ["review.multimodal_evidence_request.submitted"],
      assignmentOwnerRequired: false
    });
  }
  if (evidenceReviewOperation) {
    configureEvidenceRequestMutation(evidenceReviewOperation, {
      operationId: "a3ReviewMultimodalReviewEvidenceRequest",
      summary: "Accept, reject, or cancel submitted evidence without creating an A2 disposition.",
      schemaVersion: "a3.multimodal_review_evidence_request_receipt.v1",
      requestSchema: "MultimodalReviewEvidenceReview",
      successStatus: "200",
      successDescription: "Evidence coordination state updated by the active assignment owner.",
      events: [
        "review.multimodal_evidence_request.accepted",
        "review.multimodal_evidence_request.rejected",
        "review.multimodal_evidence_request.cancelled"
      ],
      assignmentOwnerRequired: true
    });
  }
}

function synchronizeMultimodalProviderReadinessOperations(spec) {
  const importOperation = spec.paths?.["/api/a3/import/a2-multimodal-provider-readiness"]?.post;
  const readOperation = spec.paths?.["/api/a3/providers/multimodal-readiness"]?.get;
  const authorityBoundary = {
    production_routing_capacity_and_operational_health_authority: "A1",
    evaluation_and_qualification_authority: "A2",
    display_export_and_workflow_owner: "A3",
    installed_model_is_operationally_ready: false,
    faster_warm_latency_is_quality_pass: false,
    provider_is_truth: false,
    quality_comparison_performed: false,
    release_authority: false,
    a2_decision_recomputed: false,
    production_ready: false
  };
  const evidenceBoundary = {
    atomic_availability_and_latency_envelope_required: true,
    hashes_counts_states_reason_codes_and_phase_timings_only: true,
    raw_provider_payload_forbidden: true,
    raw_response_forbidden: true,
    endpoint_url_forbidden: true,
    credentials_forbidden: true,
    private_media_forbidden: true
  };

  if (importOperation) {
    importOperation.operationId = "a3ImportA2MultimodalProviderReadiness";
    importOperation.summary = "Import public-safe A2 provider availability and phase-latency diagnostics atomically.";
    importOperation.tags = ["Review", "Evidence", "Operations"];
    importOperation["x-schema-version"] = "a3.a2_multimodal_provider_readiness_ingest.v1";
    importOperation.parameters = withIdempotencyHeader(importOperation.parameters);
    importOperation.requestBody = typedJsonRequest("MultimodalProviderReadinessImportRequest");
    delete importOperation.responses["202"];
    importOperation.responses["201"] = typedJsonResponse(
      "Provider readiness diagnostic accepted without promoting health, quality, or release authority.",
      "MultimodalProviderReadinessIngestReceipt"
    );
    importOperation.responses["409"] = typedJsonResponse("Idempotency conflict.", "DeploymentReceiptConflict");
    importOperation["x-audit"] = {
      events: ["a2.multimodal_provider_readiness_imported"],
      payload_policy: "hashes_counts_states_reason_codes_and_phase_timings_only"
    };
    importOperation["x-evidence-boundary"] = evidenceBoundary;
    importOperation["x-authority-boundary"] = authorityBoundary;
  }

  if (readOperation) {
    readOperation.operationId = "a3ReadMultimodalProviderReadiness";
    readOperation.summary = "Read tenant-scoped multimodal provider readiness diagnostics.";
    readOperation.tags = ["Review", "Evidence", "Operations"];
    readOperation["x-schema-version"] = "a3.multimodal_provider_readiness.v1";
    readOperation.responses["200"] = typedJsonResponse(
      "Public-safe availability and phase-latency projection without production-health or release authority.",
      "MultimodalProviderReadiness"
    );
    readOperation["x-evidence-boundary"] = evidenceBoundary;
    readOperation["x-authority-boundary"] = authorityBoundary;
  }
}

function configureEvidenceRequestMutation(operation, options) {
  operation.operationId = options.operationId;
  operation.summary = options.summary;
  operation.tags = ["Review", "Evidence", "Operations"];
  operation["x-schema-version"] = options.schemaVersion;
  operation.parameters = withIdempotencyHeader(operation.parameters);
  operation.requestBody = typedJsonRequest(options.requestSchema);
  delete operation.responses["202"];
  operation.responses[options.successStatus] = typedJsonResponse(
    options.successDescription,
    "MultimodalReviewEvidenceRequestReceipt"
  );
  operation.responses["409"] = typedJsonResponse(
    "Stale expected_version, assignment ownership, lifecycle, or idempotency conflict.",
    "DeploymentReceiptConflict"
  );
  operation["x-audit"] = {
    events: options.events,
    payload_policy: "queue_request_ids_hashes_versions_kinds_owner_lane_due_time_and_reason_codes_only"
  };
  operation["x-concurrency"] = {
    strategy: "optimistic_expected_version",
    stale_write_http_status: 409,
    idempotency_header_only: true
  };
  operation["x-assignment-owner-required"] = options.assignmentOwnerRequired;
  operation["x-evidence-boundary"] = {
    allowlisted_kinds_only: true,
    sha256_references_only: true,
    raw_evidence_forbidden: true,
    urls_forbidden: true,
    free_text_forbidden: true
  };
  operation["x-authority-boundary"] = multimodalEvidenceRequestAuthorityBoundary();
}

function a2MultimodalProviderReadinessEnvelopeSchema() {
  const availabilityCountFields = [
    "attempted_count", "completed_count", "eligible_count", "failed_count", "timeout_case_count"
  ];
  const phaseFields = [
    "image_read_and_base64_seconds", "caller_wall_seconds", "provider_total_seconds",
    "model_load_seconds", "prompt_eval_seconds", "token_eval_seconds",
    "transport_and_client_residual_seconds"
  ];
  const latencySummary = {
    type: "object",
    required: ["count", "median", "p95_nearest_rank", "maximum"],
    properties: {
      count: { type: "integer", minimum: 0 },
      median: { type: ["number", "null"], minimum: 0 },
      p95_nearest_rank: { type: ["number", "null"], minimum: 0 },
      maximum: { type: ["number", "null"], minimum: 0 }
    },
    additionalProperties: false
  };
  const provider = {
    type: "object",
    required: [
      "artifact_hash", ...availabilityCountFields, "latency_seconds", "qualification_state"
    ],
    properties: {
      artifact_hash: sha256Schema(),
      ...Object.fromEntries(availabilityCountFields.map((field) => [field, { type: "integer", minimum: 0 }])),
      latency_seconds: latencySummary,
      qualification_state: {
        type: "string",
        enum: ["qualified", "blocked", "diagnostic_only", "unavailable"]
      }
    },
    additionalProperties: false
  };
  const phaseReceipt = {
    type: "object",
    required: phaseFields,
    properties: Object.fromEntries(phaseFields.map((field) => [field, { type: "number", minimum: 0 }])),
    additionalProperties: false
  };
  const profile = {
    type: "object",
    required: [
      "profile", "num_predict", "format_mode", "state", "parse_state", "error_class",
      "phase_receipt", "response_hash", "raw_response_included", "release_authority", "public_safe"
    ],
    properties: {
      profile: safeProviderIdentifierSchema(),
      num_predict: { type: "integer", minimum: 1, maximum: 4096 },
      format_mode: { type: "string", enum: ["plain", "json_schema"] },
      state: { type: "string", enum: ["completed", "failed"] },
      parse_state: { type: "string", enum: ["valid_json", "invalid_structured_output", "unavailable"] },
      error_class: { type: "string", pattern: "^(?:|[A-Za-z0-9][A-Za-z0-9._:-]{0,159})$" },
      phase_receipt: phaseReceipt,
      response_hash: { anyOf: [sha256Schema(), { type: "null" }] },
      raw_response_included: { type: "boolean", const: false },
      release_authority: { type: "boolean", const: false },
      public_safe: { type: "boolean", const: true }
    },
    additionalProperties: false
  };

  return {
    type: "object",
    required: [
      "schema_version", "source_commit_alias", "availability_comparison", "latency_probe",
      "release_authority", "public_safe", "raw_provider_payload_included"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.a2_multimodal_provider_readiness_intake.v1" },
      source_commit_alias: { type: "string", pattern: "^[a-f0-9]{7,40}$" },
      availability_comparison: {
        type: "object",
        required: [
          "schema_version", "same_case_set", "case_set_hash", "providers", "blockers",
          "comparison_state", "quality_comparison_performed", "provider_is_truth",
          "release_authority", "raw_provider_text_included", "public_safe"
        ],
        properties: {
          schema_version: { type: "string", const: "a2.local_multimodal_availability_comparison.v1" },
          same_case_set: { type: "boolean" },
          case_set_hash: { anyOf: [sha256Schema(), { type: "null" }] },
          providers: {
            type: "object",
            minProperties: 2,
            maxProperties: 20,
            propertyNames: safeProviderIdentifierSchema(),
            additionalProperties: provider
          },
          blockers: providerReasonCodeArraySchema(true),
          comparison_state: { type: "string", enum: ["complete", "blocked"] },
          quality_comparison_performed: { type: "boolean", const: false },
          provider_is_truth: { type: "boolean", const: false },
          release_authority: { type: "boolean", const: false },
          raw_provider_text_included: { type: "boolean", const: false },
          public_safe: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      latency_probe: {
        type: "object",
        required: [
          "schema_version", "generated_at", "provider_id", "base_url_class", "model_id",
          "model_digest", "artifact_hash", "prompt_hash", "output_schema_hash", "unload_state",
          "timeout_seconds", "profiles", "diagnosis", "completed_profile_count",
          "qualification_state", "provider_is_truth", "secret_included", "release_authority", "public_safe"
        ],
        properties: {
          schema_version: { type: "string", const: "a2.ollama_multimodal_latency_probe.v1" },
          generated_at: { type: "string", format: "date-time" },
          provider_id: { type: "string", const: "ollama-local" },
          base_url_class: { type: "string", const: "loopback" },
          model_id: safeProviderIdentifierSchema(),
          model_digest: sha256Schema(),
          artifact_hash: sha256Schema(),
          prompt_hash: sha256Schema(),
          output_schema_hash: sha256Schema(),
          unload_state: { type: "string", enum: ["requested", "unconfirmed"] },
          timeout_seconds: { type: "number", exclusiveMinimum: 0 },
          profiles: { type: "array", minItems: 4, maxItems: 4, items: profile },
          diagnosis: providerReasonCodeArraySchema(false),
          completed_profile_count: { type: "integer", minimum: 0, maximum: 4 },
          qualification_state: { type: "string", enum: ["diagnostic_only", "blocked"] },
          provider_is_truth: { type: "boolean", const: false },
          secret_included: { type: "boolean", const: false },
          release_authority: { type: "boolean", const: false },
          public_safe: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      release_authority: { type: "boolean", const: false },
      public_safe: { type: "boolean", const: true },
      raw_provider_payload_included: { type: "boolean", const: false }
    },
    additionalProperties: false,
    description: "Atomic public-safe A2 availability and phase-latency evidence. Installation and warm latency do not prove health, quality, or release readiness."
  };
}

function multimodalProviderReadinessImportRequestSchema() {
  const scopeProperties = Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, {
    type: "string", minLength: 1, maxLength: 160
  }]));
  return {
    type: "object",
    required: ["source", "provider_readiness_evidence"],
    properties: {
      source: { type: "string", minLength: 1, maxLength: 160 },
      source_label: { type: "string", minLength: 1, maxLength: 160 },
      sourceLabel: { type: "string", minLength: 1, maxLength: 160 },
      ...scopeProperties,
      imported_at: { type: "string", deprecated: true, description: "Ignored. The server assigns imported_at from its own clock." },
      idempotency_key: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      idempotencyKey: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      provider_readiness_evidence: { $ref: "#/components/schemas/A2MultimodalProviderReadinessEnvelope" }
    },
    additionalProperties: false,
    description: "Header-only idempotency; availability and latency evidence are accepted atomically under a server-verified five-level tenant scope."
  };
}

function multimodalProviderReadinessIngestReceiptSchema() {
  const countFields = [
    "provider_count", "attempted_count", "completed_count", "failed_count", "timeout_case_count",
    "eligible_count", "completed_profile_count", "valid_structured_profile_count"
  ];
  return {
    type: "object",
    required: [
      "schema_version", "source", ...TENANT_SCOPE_CONTRACT.required, "storage_mode", "db_ready",
      "payload_hash", ...countFields, "upstream_release_authority", "quality_comparison_performed",
      "operational_health_verified", "a2_decision_recomputed", "release_decision_changed",
      "imported_at", "idempotency"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.a2_multimodal_provider_readiness_ingest.v1" },
      source: { type: "string" },
      ...Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, { type: "string" }])),
      storage_mode: { type: "string" },
      db_ready: { type: "boolean" },
      payload_hash: { type: "string", pattern: "^[a-f0-9]{64}$" },
      ...Object.fromEntries(countFields.map((field) => [field, { type: "integer", minimum: 0 }])),
      upstream_release_authority: { type: "boolean", const: false },
      quality_comparison_performed: { type: "boolean", const: false },
      operational_health_verified: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      release_decision_changed: { type: "boolean", const: false },
      imported_at: { type: "string", format: "date-time" },
      idempotency: {
        type: "object",
        required: ["key_present", "duplicate", "status"],
        properties: {
          key_present: { type: "boolean", const: true },
          duplicate: { type: "boolean" },
          status: { type: "string", enum: ["recorded", "replayed"] }
        },
        additionalProperties: false
      },
      event_envelope: { type: "object", additionalProperties: true }
    },
    additionalProperties: false
  };
}

function multimodalProviderReadinessSchema() {
  const summaryCountFields = [
    "provider_count", "attempted_count", "completed_count", "failed_count", "timeout_case_count",
    "eligible_count", "qualified_provider_count", "blocked_provider_count", "profile_count",
    "completed_profile_count", "valid_structured_profile_count"
  ];
  const phaseFields = [
    "image_read_and_base64_seconds", "caller_wall_seconds", "provider_total_seconds",
    "model_load_seconds", "prompt_eval_seconds", "token_eval_seconds",
    "transport_and_client_residual_seconds"
  ];
  const ratioSchema = { type: ["number", "null"], minimum: 0, maximum: 1 };
  const providerProjection = {
    type: "object",
    required: [
      "model_id", "artifact_hash", "qualification_state", "attempted_count", "completed_count",
      "failed_count", "timeout_case_count", "eligible_count", "completion_rate", "timeout_rate",
      "eligible_rate", "latency_seconds"
    ],
    properties: {
      model_id: safeProviderIdentifierSchema(),
      artifact_hash: sha256Schema(),
      qualification_state: { type: "string", enum: ["qualified", "blocked", "diagnostic_only", "unavailable"] },
      attempted_count: { type: "integer", minimum: 0 },
      completed_count: { type: "integer", minimum: 0 },
      failed_count: { type: "integer", minimum: 0 },
      timeout_case_count: { type: "integer", minimum: 0 },
      eligible_count: { type: "integer", minimum: 0 },
      completion_rate: ratioSchema,
      timeout_rate: ratioSchema,
      eligible_rate: ratioSchema,
      latency_seconds: {
        type: "object",
        required: ["count", "median", "p95_nearest_rank", "maximum"],
        properties: {
          count: { type: "integer", minimum: 0 },
          median: { type: ["number", "null"], minimum: 0 },
          p95_nearest_rank: { type: ["number", "null"], minimum: 0 },
          maximum: { type: ["number", "null"], minimum: 0 }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
  const profileProjection = {
    type: "object",
    required: ["profile", "state", "parse_state", "error_class", "format_mode", "num_predict", "response_hash", "phase_seconds"],
    properties: {
      profile: safeProviderIdentifierSchema(),
      state: { type: "string", enum: ["completed", "failed"] },
      parse_state: { type: "string", enum: ["valid_json", "invalid_structured_output", "unavailable"] },
      error_class: { type: "string" },
      format_mode: { type: "string", enum: ["plain", "json_schema"] },
      num_predict: { type: "integer", minimum: 1, maximum: 4096 },
      response_hash: { anyOf: [sha256Schema(), { type: "null" }] },
      phase_seconds: {
        type: "object",
        required: phaseFields,
        properties: Object.fromEntries(phaseFields.map((field) => [field, { type: "number", minimum: 0 }])),
        additionalProperties: false
      }
    },
    additionalProperties: false
  };
  return {
    type: "object",
    required: [
      "schema_version", "source", "source_commit_alias", "source_contracts", "tenant_scope",
      "release_authority", "a2_decision_recomputed", "production_ready", "available", "status",
      "integrity", "authority_boundary", "safety", "recommendation_code"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_provider_readiness.v1" },
      source: { type: "string" },
      source_commit_alias: { type: ["string", "null"], pattern: "^[a-f0-9]{7,40}$" },
      source_contracts: { type: "array", minItems: 2, maxItems: 2, items: { type: "string" } },
      tenant_scope: multimodalTenantScopeSchema(),
      release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      production_ready: { type: "boolean", const: false },
      available: { type: "boolean" },
      status: { type: "string", enum: ["invalid_upstream_contract", "blocked_provider_readiness", "diagnostic_ready_non_authoritative"] },
      capability_state: { type: "string" },
      integrity: {
        type: "object",
        required: ["status", "finding_count", "findings"],
        properties: {
          status: { type: "string", enum: ["passed", "failed"] },
          finding_count: { type: "integer", minimum: 0 },
          findings: {
            type: "array",
            items: {
              type: "object",
              required: ["field", "issue"],
              properties: {
                field: { type: "string" },
                issue: { type: "string" }
              },
              additionalProperties: false
            }
          },
          a3_computed_payload_hash: sha256Schema()
        },
        additionalProperties: false
      },
      summary: {
        type: "object",
        required: [
          ...summaryCountFields, "quality_comparison_performed", "operational_health_verified",
          "routing_ready", "capacity_verified"
        ],
        properties: {
          ...Object.fromEntries(summaryCountFields.map((field) => [field, { type: "integer", minimum: 0 }])),
          quality_comparison_performed: { type: "boolean", const: false },
          operational_health_verified: { type: "boolean", const: false },
          routing_ready: { type: "boolean", const: false },
          capacity_verified: { type: "boolean", const: false }
        },
        additionalProperties: false
      },
      availability: {
        type: "object",
        required: ["comparison_state", "same_case_set", "case_set_hash", "blockers", "providers"],
        properties: {
          comparison_state: { type: "string", enum: ["complete", "blocked"] },
          same_case_set: { type: "boolean" },
          case_set_hash: { anyOf: [sha256Schema(), { type: "null" }] },
          blockers: providerReasonCodeArraySchema(true),
          providers: { type: "array", minItems: 2, maxItems: 20, items: providerProjection }
        },
        additionalProperties: false
      },
      latency_diagnostic: {
        type: "object",
        required: [
          "provider_id", "model_id", "model_digest", "artifact_hash", "prompt_hash",
          "output_schema_hash", "base_url_class", "generated_at", "timeout_seconds", "unload_state",
          "qualification_state", "diagnosis", "cold_wall_seconds", "fastest_warm_wall_seconds", "profiles"
        ],
        properties: {
          provider_id: { type: "string", const: "ollama-local" },
          model_id: safeProviderIdentifierSchema(),
          model_digest: sha256Schema(),
          artifact_hash: sha256Schema(),
          prompt_hash: sha256Schema(),
          output_schema_hash: sha256Schema(),
          base_url_class: { type: "string", const: "loopback" },
          generated_at: { type: "string", format: "date-time" },
          timeout_seconds: { type: "number", exclusiveMinimum: 0 },
          unload_state: { type: "string", enum: ["requested", "unconfirmed"] },
          qualification_state: { type: "string", enum: ["diagnostic_only", "blocked"] },
          diagnosis: providerReasonCodeArraySchema(false),
          cold_wall_seconds: { type: ["number", "null"], minimum: 0 },
          fastest_warm_wall_seconds: { type: ["number", "null"], minimum: 0 },
          profiles: { type: "array", minItems: 4, maxItems: 4, items: profileProjection }
        },
        additionalProperties: false
      },
      authority_boundary: {
        type: "object",
        required: [
          "provider_is_truth", "quality_comparison_performed", "operational_health_verified",
          "routing_or_capacity_authority", "evaluation_and_qualification_authority",
          "display_and_workflow_owner", "release_authority", "a2_decision_recomputed",
          "release_decision_changed", "production_ready"
        ],
        properties: {
          provider_is_truth: { type: "boolean", const: false },
          quality_comparison_performed: { type: "boolean", const: false },
          operational_health_verified: { type: "boolean", const: false },
          routing_or_capacity_authority: { type: "string", const: "A1" },
          evaluation_and_qualification_authority: { type: "string", const: "A2" },
          display_and_workflow_owner: { type: "string", const: "A3" },
          release_authority: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          release_decision_changed: { type: "boolean", const: false },
          production_ready: { type: "boolean", const: false }
        },
        additionalProperties: false
      },
      safety: {
        type: "object",
        required: [
          "public_safe", "raw_provider_payload_included", "secret_included", "endpoint_url_included",
          "model_binary_included", "private_media_included", "hash_and_aggregate_metadata_only"
        ],
        properties: {
          public_safe: { type: "boolean", const: true },
          raw_provider_payload_included: { type: "boolean", const: false },
          secret_included: { type: "boolean", const: false },
          endpoint_url_included: { type: "boolean", const: false },
          model_binary_included: { type: "boolean", const: false },
          private_media_included: { type: "boolean", const: false },
          hash_and_aggregate_metadata_only: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      recommendation_code: safeProviderIdentifierSchema()
    },
    additionalProperties: false,
    description: "Tenant-scoped A3 projection. Faster warm latency or installed models never imply operational health, qualified quality, or production readiness."
  };
}

function safeProviderIdentifierSchema() {
  return { type: "string", pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$" };
}

function providerReasonCodeArraySchema(allowEmpty) {
  return {
    type: "array",
    minItems: allowEmpty ? 0 : 1,
    maxItems: 50,
    uniqueItems: true,
    items: safeProviderIdentifierSchema()
  };
}

function a2MultimodalComparisonEnvelopeSchema() {
  return {
    oneOf: [
      multimodalComparisonVersionSchema("a2.multimodal_cross_provider_comparison.v1", false),
      multimodalComparisonVersionSchema("a2.multimodal_cross_provider_comparison.v3", true),
      threeWayMultimodalComparisonSchema()
    ],
    description: "Validated by the A3 two-way v1/v3 and three-way v2 adapters; raw provider payloads and release authority are forbidden."
  };
}

function multimodalComparisonVersionSchema(schemaVersion, aggregateRequired) {
  const required = [
    "schema_version", "left_evidence_hash", "right_evidence_hash", "left_binding", "right_binding",
    "comparisons", "summary", "human_review_queue_receipts", "release_authority",
    "raw_payload_included", "public_safe"
  ];
  if (aggregateRequired) {
    required.push("comparison_artifact_hash", "aggregate_comparisons", "aggregate_summary");
  }
  const properties = {
    schema_version: { type: "string", const: schemaVersion },
    left_evidence_hash: sha256Schema(),
    right_evidence_hash: sha256Schema(),
    left_binding: { type: "object", additionalProperties: true },
    right_binding: { type: "object", additionalProperties: true },
    comparisons: { type: "array", maxItems: 5000, items: { type: "object", additionalProperties: true } },
    summary: countSummarySchema(["agreement", "semantic_disagreement", "unavailable"]),
    human_review_queue_receipts: { type: "array", maxItems: 10000, items: { type: "object", additionalProperties: true } },
    release_authority: { type: "boolean", const: false },
    raw_payload_included: { type: "boolean", const: false },
    public_safe: { type: "boolean", const: true }
  };
  if (aggregateRequired) {
    Object.assign(properties, {
      comparison_artifact_hash: sha256Schema(),
      lineage: multimodalLineageSchema(),
      aggregate_comparisons: { type: "array", maxItems: 5000, items: { type: "object", additionalProperties: true } },
      aggregate_summary: countSummarySchema(["agreement", "semantic_disagreement", "unavailable", "internally_unstable"])
    });
  }
  return {
    type: "object",
    required,
    properties,
    additionalProperties: false
  };
}

function threeWayMultimodalComparisonSchema() {
  const providerKey = {
    type: "string",
    minLength: 1,
    maxLength: 160,
    pattern: "^(?!\\s)(?!.*\\s$)(?!.*::).+$"
  };
  const providerState = {
    type: "object",
    required: ["eligible", "parse_state", "observed_risk"],
    properties: {
      eligible: { type: "boolean" },
      parse_state: { type: "string", minLength: 1, maxLength: 240 },
      observed_risk: { type: ["boolean", "null"] }
    },
    additionalProperties: false
  };
  return {
    type: "object",
    required: [
      "schema_version", "comparison_artifact_hash", "evidence_hashes", "partial_journal_hashes",
      "comparisons", "summary", "pairwise_summaries", "human_review_queue_receipts",
      "release_authority", "raw_payload_included", "public_safe"
    ],
    properties: {
      schema_version: { type: "string", const: "a2.multimodal_three_way_comparison.v2" },
      comparison_artifact_hash: sha256Schema(),
      evidence_hashes: {
        type: "object",
        minProperties: 3,
        maxProperties: 3,
        propertyNames: providerKey,
        additionalProperties: sha256Schema()
      },
      partial_journal_hashes: {
        type: "object",
        minProperties: 3,
        maxProperties: 3,
        propertyNames: providerKey,
        additionalProperties: { type: "string", pattern: "^(|sha256:[a-f0-9]{64})$" }
      },
      comparisons: {
        type: "array",
        maxItems: 5000,
        items: {
          type: "object",
          required: [
            "case_id", "artifact_hash", "repeat", "eligible_provider_count", "provider_states",
            "comparison_state", "human_review_required"
          ],
          properties: {
            case_id: { type: "string", minLength: 1, maxLength: 240 },
            artifact_hash: sha256Schema(),
            repeat: { type: "integer", minimum: 1 },
            eligible_provider_count: { type: "integer", minimum: 0, maximum: 3 },
            provider_states: {
              type: "object",
              minProperties: 3,
              maxProperties: 3,
              propertyNames: providerKey,
              additionalProperties: providerState
            },
            comparison_state: {
              type: "string",
              enum: ["three_way_agreement", "pairwise_agreement_with_unavailable", "semantic_disagreement", "unavailable"]
            },
            human_review_required: { type: "boolean" }
          },
          additionalProperties: false
        }
      },
      summary: countSummarySchema([
        "three_way_agreement",
        "pairwise_agreement_with_unavailable",
        "semantic_disagreement",
        "unavailable"
      ]),
      pairwise_summaries: {
        type: "object",
        minProperties: 3,
        maxProperties: 3,
        additionalProperties: countSummarySchema(["agreement", "semantic_disagreement", "unavailable"])
      },
      human_review_queue_receipts: {
        type: "array",
        maxItems: 5000,
        items: {
          type: "object",
          required: [
            "receipt_id", "comparison_artifact_hash", "comparison_hash", "artifact_hash", "case_id",
            "repeat", "eligibility_rule", "queue_state", "reviewer_role", "release_authority"
          ],
          properties: {
            receipt_id: sha256Schema(),
            comparison_artifact_hash: sha256Schema(),
            comparison_hash: sha256Schema(),
            artifact_hash: sha256Schema(),
            case_id: { type: "string", minLength: 1, maxLength: 240 },
            repeat: { type: "integer", minimum: 1 },
            eligibility_rule: {
              type: "string",
              enum: [
                "at_least_two_eligible_and_semantically_disagree",
                "designated_high_quality_reference_unavailable"
              ]
            },
            reference_provider: providerKey,
            queue_state: { type: "string", const: "awaiting_human_review" },
            reviewer_role: { type: "string", const: "multimodal_safety_reviewer" },
            release_authority: { type: "boolean", const: false }
          },
          additionalProperties: false
        }
      },
      designated_high_quality_reference: providerKey,
      release_authority: { type: "boolean", const: false },
      raw_payload_included: { type: "boolean", const: false },
      public_safe: { type: "boolean", const: true }
    },
    additionalProperties: false
  };
}

function multimodalComparisonImportRequestSchema() {
  const scopeProperties = Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, { type: "string", minLength: 1, maxLength: 160 }]));
  return {
    type: "object",
    required: ["source", "comparison"],
    properties: {
      source: { type: "string", minLength: 1, maxLength: 160 },
      source_label: { type: "string", minLength: 1, maxLength: 160 },
      sourceLabel: { type: "string", minLength: 1, maxLength: 160 },
      ...scopeProperties,
      imported_at: { type: "string", deprecated: true, description: "Ignored. The server assigns imported_at from its own clock." },
      idempotency_key: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      idempotencyKey: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      comparison: { $ref: "#/components/schemas/A2MultimodalComparisonEnvelope" }
    },
    additionalProperties: false,
    description: "Idempotency is header-only and imported_at is assigned by the server clock."
  };
}

function multimodalComparisonIngestReceiptSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source", "payload_hash", "comparison_count", "review_required_count",
      "queue_receipt_count", "upstream_release_authority", "candidate_binding_verified",
      "release_decision_changed", "imported_at", "idempotency"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.a2_multimodal_comparison_ingest.v1" },
      source: { type: "string" },
      payload_hash: { type: "string", pattern: "^[a-f0-9]{64}$" },
      comparison_count: { type: "integer", minimum: 0 },
      review_required_count: { type: "integer", minimum: 0 },
      queue_receipt_count: { type: "integer", minimum: 0 },
      upstream_release_authority: { type: "boolean", const: false },
      candidate_binding_verified: { type: "boolean", const: false },
      release_decision_changed: { type: "boolean", const: false },
      imported_at: { type: "string", format: "date-time" },
      idempotency: { type: "object", additionalProperties: true },
      event_envelope: { type: "object", additionalProperties: true }
    },
    additionalProperties: true
  };
}

function multimodalReviewQueueSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "available", "status", "source_contract", "tenant_scope", "summary",
      "authority_boundary", "items", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_queue.v1" },
      available: { type: "boolean" },
      status: { type: "string", enum: ["not_ingested", "invalid_upstream_contract", "no_open_multimodal_review", "human_review_required"] },
      source_contract: {
        type: "string",
        enum: [
          "a2.multimodal_cross_provider_comparison.v1",
          "a2.multimodal_cross_provider_comparison.v3",
          "a2.multimodal_three_way_comparison.v2"
        ]
      },
      tenant_scope: {
        type: "object",
        required: [...TENANT_SCOPE_CONTRACT.required],
        properties: Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, { type: ["string", "null"] }])),
        additionalProperties: false
      },
      summary: { type: "object", additionalProperties: true },
      authority_boundary: {
        type: "object",
        required: ["upstream_release_authority", "queue_receipts_release_authority", "a3_recomputed_risk", "a3_recomputed_release_decision", "candidate_binding_verified", "can_change_release_decision"],
        properties: multimodalAuthorityBoundaryProperties(),
        additionalProperties: true
      },
      items: { type: "array", maxItems: 10000, items: { type: "object", additionalProperties: true } },
      safety: {
        type: "object",
        required: ["raw_model_payload_exposed", "raw_media_exposed", "signed_url_exposed", "provider_secret_exposed", "production_ready_claimed"],
        properties: {
          raw_model_payload_exposed: { type: "boolean", const: false },
          raw_media_exposed: { type: "boolean", const: false },
          signed_url_exposed: { type: "boolean", const: false },
          provider_secret_exposed: { type: "boolean", const: false },
          production_ready_claimed: { type: "boolean", const: false },
          raw_reviewer_identity_exposed: { type: "boolean", const: false },
          raw_assignment_payload_exposed: { type: "boolean", const: false }
        },
        additionalProperties: true
      }
    },
    additionalProperties: true
  };
}

function a2MultimodalRepeatStabilityEnvelopeSchema() {
  const repeatMetric = {
    type: "object",
    required: [
      "required_unit_count", "matched_unit_count", "missing_unit_counts_by_repeat",
      "complete_across_repeats", "repeat_summaries", "paired_max_minus_min_bootstrap_ci_95"
    ],
    properties: {
      required_unit_count: { type: "integer", minimum: 0 },
      matched_unit_count: { type: "integer", minimum: 0 },
      missing_unit_counts_by_repeat: { type: "array", minItems: 3, maxItems: 100, items: { type: "integer", minimum: 0 } },
      complete_across_repeats: { type: "boolean" },
      repeat_summaries: {
        type: "array",
        minItems: 3,
        maxItems: 100,
        items: {
          type: "object",
          required: ["eligible_unit_count", "success_count", "estimate", "bootstrap_ci_95"],
          properties: {
            eligible_unit_count: { type: "integer", minimum: 0 },
            success_count: { type: "integer", minimum: 0 },
            estimate: { type: ["number", "null"], minimum: 0, maximum: 1 },
            bootstrap_ci_95: probabilityIntervalSchema()
          },
          additionalProperties: false
        }
      },
      paired_max_minus_min_bootstrap_ci_95: probabilityIntervalSchema()
    },
    additionalProperties: false
  };
  const bindingFields = [
    "endpoint_region", "manifest_hash", "model_id", "ordered_case_plan_hash",
    "output_schema_hash", "policy_hash", "prompt_hash", "provider_capability_hash", "provider_id"
  ];
  const hashBindingFields = new Set(bindingFields.filter((field) => field.endsWith("_hash")));
  return {
    type: "object",
    required: [
      "schema_version", "source_commit_alias", "comparison", "review_collection",
      "review_conservation", "shared_candidate_verification", "release_authority",
      "public_safe", "raw_provider_payload_included", "raw_reviewer_identity_included"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.a2_multimodal_repeat_stability_intake.v1" },
      source_commit_alias: { type: "string", pattern: "^[a-f0-9]{7,40}$" },
      comparison: {
        type: "object",
        required: [
          "schema_version", "calibration_hashes", "repeat_count", "binding_fields",
          "mismatched_binding_fields", "bootstrap_samples", "seed", "retained_calibration_states",
          "source_unit_coverage", "metrics", "taxonomy_sensitivity", "all_required_units_complete",
          "blockers", "promotion_eligible", "provider_is_truth", "release_authority",
          "raw_provider_text_included", "public_safe"
        ],
        properties: {
          schema_version: { type: "string", const: "a2.multimodal_multi_repeat_comparison.v1" },
          calibration_hashes: { type: "array", minItems: 3, maxItems: 100, uniqueItems: true, items: sha256Schema() },
          repeat_count: { type: "integer", minimum: 3, maximum: 100 },
          binding_fields: {
            type: "object",
            required: bindingFields,
            properties: Object.fromEntries(bindingFields.map((field) => [field, hashBindingFields.has(field)
              ? sha256Schema()
              : { type: "string", minLength: 1, maxLength: 160 }])),
            additionalProperties: false
          },
          mismatched_binding_fields: { type: "array", maxItems: bindingFields.length, uniqueItems: true, items: { type: "string", enum: bindingFields } },
          bootstrap_samples: { type: "integer", minimum: 100, maximum: 10000000 },
          seed: { type: "integer" },
          retained_calibration_states: {
            type: "array", minItems: 3, maxItems: 100,
            items: { type: "string", enum: ["qualified", "blocked", "incomplete", "unavailable"] }
          },
          source_unit_coverage: {
            type: "object",
            required: ["required_unit_count", "eligible_unit_counts_by_repeat", "missing_unit_counts_by_repeat", "complete_across_repeats"],
            properties: {
              required_unit_count: { type: "integer", minimum: 0 },
              eligible_unit_counts_by_repeat: { type: "array", minItems: 3, maxItems: 100, items: { type: "integer", minimum: 0 } },
              missing_unit_counts_by_repeat: { type: "array", minItems: 3, maxItems: 100, items: { type: "integer", minimum: 0 } },
              complete_across_repeats: { type: "boolean" }
            },
            additionalProperties: false
          },
          metrics: {
            type: "object",
            required: ["specificity", "benign_text_false_positive_rate"],
            properties: {
              specificity: repeatMetric,
              benign_text_false_positive_rate: repeatMetric
            },
            additionalProperties: false
          },
          taxonomy_sensitivity: {
            type: "object",
            required: ["cross_modal_conflict", "visual_prompt_injection"],
            properties: {
              cross_modal_conflict: repeatMetric,
              visual_prompt_injection: repeatMetric
            },
            additionalProperties: false
          },
          all_required_units_complete: { type: "boolean" },
          blockers: reasonCodeArraySchema(),
          promotion_eligible: { type: "boolean" },
          provider_is_truth: { type: "boolean", const: false },
          release_authority: { type: "boolean", const: false },
          raw_provider_text_included: { type: "boolean", const: false },
          public_safe: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      review_collection: {
        type: "object",
        required: ["schema_version", "collection_state", "receipts", "note", "release_authority", "public_safe"],
        properties: {
          schema_version: { type: "string", const: "a2.multimodal_real_review_collection.v1" },
          collection_state: { type: "string", enum: ["pending", "partially_reviewed", "reviewed"] },
          receipts: {
            type: "array",
            maxItems: 100,
            description: "A3 currently accepts an empty array only and fails closed until the exact authoritative receipt schema is published.",
            items: { type: "object", additionalProperties: false }
          },
          note: { type: "string", minLength: 1, maxLength: 500, description: "Public-safe note; URLs, credentials, identity, and raw evidence are forbidden." },
          release_authority: { type: "boolean", const: false },
          public_safe: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      review_conservation: {
        type: "object",
        required: [
          "schema_version", "queue_receipt_count", "pending_queue_receipt_count",
          "reviewed_queue_receipt_count", "latest_receipt_hashes", "conservation_holds",
          "verification_state", "errors", "release_authority", "public_safe"
        ],
        properties: {
          schema_version: { type: "string", const: "a2.multimodal_review_conservation.v1" },
          queue_receipt_count: { type: "integer", minimum: 0 },
          pending_queue_receipt_count: { type: "integer", minimum: 0 },
          reviewed_queue_receipt_count: { type: "integer", minimum: 0 },
          latest_receipt_hashes: { type: "object", additionalProperties: sha256Schema() },
          conservation_holds: { type: "boolean" },
          verification_state: { type: "string", enum: ["verified", "failed"] },
          errors: reasonCodeArraySchema(),
          release_authority: { type: "boolean", const: false },
          public_safe: { type: "boolean", const: true }
        },
        additionalProperties: false
      },
      shared_candidate_verification: {
        type: "object",
        required: ["blockers", "verified"],
        properties: {
          blockers: reasonCodeArraySchema(),
          verified: { type: "boolean" }
        },
        additionalProperties: false
      },
      release_authority: { type: "boolean", const: false },
      public_safe: { type: "boolean", const: true },
      raw_provider_payload_included: { type: "boolean", const: false },
      raw_reviewer_identity_included: { type: "boolean", const: false }
    },
    additionalProperties: false,
    description: "Atomic A2 comparison, review-conservation, and candidate-binding envelope. Repeat stability is not a release decision."
  };
}

function multimodalRepeatStabilityImportRequestSchema() {
  const scopeProperties = Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, {
    type: "string", minLength: 1, maxLength: 160
  }]));
  return {
    type: "object",
    required: ["source", "stability_evidence"],
    properties: {
      source: { type: "string", minLength: 1, maxLength: 160 },
      source_label: { type: "string", minLength: 1, maxLength: 160 },
      sourceLabel: { type: "string", minLength: 1, maxLength: 160 },
      ...scopeProperties,
      imported_at: { type: "string", deprecated: true, description: "Ignored. The server assigns imported_at from its own clock." },
      idempotency_key: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      idempotencyKey: { type: "string", deprecated: true, description: "Ignored. Use the required Idempotency-Key header." },
      stability_evidence: { $ref: "#/components/schemas/A2MultimodalRepeatStabilityEnvelope" }
    },
    additionalProperties: false,
    description: "Header-only idempotency; identity and five-level scope are verified server-side."
  };
}

function multimodalRepeatStabilityIngestReceiptSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source", "payload_hash", "repeat_count", "retained_blocked_count",
      "all_required_units_complete", "human_review_receipt_count", "pending_queue_receipt_count",
      "shared_candidate_verified", "upstream_release_authority", "a2_decision_recomputed",
      "release_decision_changed", "imported_at", "idempotency"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.a2_multimodal_repeat_stability_ingest.v1" },
      source: { type: "string" },
      payload_hash: { type: "string", pattern: "^[a-f0-9]{64}$" },
      repeat_count: { type: "integer", minimum: 3 },
      retained_blocked_count: { type: "integer", minimum: 0 },
      all_required_units_complete: { type: "boolean" },
      human_review_receipt_count: { type: "integer", minimum: 0 },
      pending_queue_receipt_count: { type: "integer", minimum: 0 },
      shared_candidate_verified: { type: "boolean" },
      upstream_release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      release_decision_changed: { type: "boolean", const: false },
      imported_at: { type: "string", format: "date-time" },
      idempotency: { type: "object", additionalProperties: true },
      event_envelope: { type: "object", additionalProperties: true }
    },
    additionalProperties: true
  };
}

function multimodalRepeatStabilitySchema() {
  return {
    type: "object",
    required: [
      "schema_version", "available", "status", "tenant_scope", "release_authority",
      "a2_decision_recomputed", "production_ready", "authority_boundary", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_repeat_stability.v1" },
      available: { type: "boolean" },
      status: { type: "string", enum: ["invalid_upstream_contract", "blocked_stable_repeat", "promotion_evidence_non_authoritative"] },
      source: { type: "string" },
      source_commit_alias: { type: ["string", "null"], pattern: "^[a-f0-9]{7,40}$" },
      source_contract: { type: "string" },
      capability_state: { type: "string" },
      tenant_scope: multimodalTenantScopeSchema(),
      release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      production_ready: { type: "boolean", const: false },
      summary: {
        type: "object",
        properties: {
          repeat_count: { type: "integer", minimum: 0 },
          retained_blocked_count: { type: "integer", minimum: 0 },
          retained_qualified_count: { type: "integer", minimum: 0 },
          all_required_units_complete: { type: "boolean" },
          required_source_unit_count: { type: "integer", minimum: 0 },
          bootstrap_samples: { type: "integer", minimum: 0 },
          blocker_count: { type: "integer", minimum: 0 },
          promotion_eligible: { type: "boolean" },
          stable_observation: { type: "boolean" },
          quality_qualified: { type: "boolean" }
        },
        additionalProperties: false
      },
      metrics: {
        type: "array",
        maxItems: 4,
        items: {
          type: "object",
          required: ["metric_id", "required_unit_count", "matched_unit_count", "complete_across_repeats", "repeat_estimates"],
          properties: {
            metric_id: {
              type: "string",
              enum: ["specificity", "benign_text_false_positive_rate", "cross_modal_conflict_sensitivity", "visual_prompt_injection_sensitivity"]
            },
            required_unit_count: { type: "integer", minimum: 0 },
            matched_unit_count: { type: "integer", minimum: 0 },
            complete_across_repeats: { type: "boolean" },
            repeat_estimates: { type: "array", minItems: 3, maxItems: 100, items: { type: "number", minimum: 0, maximum: 1 } },
            repeat_eligible_counts: { type: "array", items: { type: "integer", minimum: 0 } },
            repeat_success_counts: { type: "array", items: { type: "integer", minimum: 0 } },
            repeat_bootstrap_ci_95: { type: "array", items: probabilityIntervalSchema() },
            paired_max_minus_min_bootstrap_ci_95: probabilityIntervalSchema()
          },
          additionalProperties: false
        }
      },
      blockers: reasonCodeArraySchema(),
      human_review: { type: "object", additionalProperties: true },
      candidate_binding: {
        type: "object",
        required: ["verified", "blockers"],
        properties: { verified: { type: "boolean" }, blockers: reasonCodeArraySchema() },
        additionalProperties: false
      },
      integrity: { type: "object", additionalProperties: true },
      authority_boundary: {
        type: "object",
        required: [
          "provider_is_truth", "provider_identity_verified", "authoritative_human_disposition_recorded",
          "candidate_binding_verified", "a2_decision_recomputed", "release_authority",
          "release_decision_changed", "production_ready"
        ],
        properties: Object.fromEntries([
          "provider_is_truth", "provider_identity_verified", "authoritative_human_disposition_recorded",
          "candidate_binding_verified", "a2_decision_recomputed", "release_authority",
          "release_decision_changed", "production_ready"
        ].map((field) => [field, { type: "boolean", const: false }])),
        additionalProperties: false
      },
      safety: {
        type: "object",
        required: [
          "public_safe", "hashes_and_aggregate_metrics_only", "raw_provider_payload_included",
          "raw_provider_text_included", "raw_reviewer_identity_included", "signed_url_included",
          "secret_values_included"
        ],
        properties: {
          public_safe: { type: "boolean", const: true },
          hashes_and_aggregate_metrics_only: { type: "boolean", const: true },
          raw_provider_payload_included: { type: "boolean", const: false },
          raw_provider_text_included: { type: "boolean", const: false },
          raw_reviewer_identity_included: { type: "boolean", const: false },
          signed_url_included: { type: "boolean", const: false },
          secret_values_included: { type: "boolean", const: false }
        },
        additionalProperties: false
      },
      recommendation_code: { type: "string" }
    },
    additionalProperties: true,
    description: "Aggregate stability evidence. Stable blocked repeats remain blocked and never become release authority."
  };
}

function multimodalTenantScopeSchema() {
  return {
    type: "object",
    required: [...TENANT_SCOPE_CONTRACT.required],
    properties: Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, { type: ["string", "null"] }])),
    additionalProperties: false
  };
}

function probabilityIntervalSchema() {
  return {
    type: "object",
    required: ["lower", "upper"],
    properties: {
      lower: { type: ["number", "null"], minimum: 0, maximum: 1 },
      upper: { type: ["number", "null"], minimum: 0, maximum: 1 }
    },
    additionalProperties: false
  };
}

function reasonCodeArraySchema() {
  return {
    type: "array",
    maxItems: 100,
    uniqueItems: true,
    items: { type: "string", pattern: "^[a-z0-9][a-z0-9_.:-]{0,159}$" }
  };
}

function multimodalReviewAssignmentRequestSchema() {
  const scopeProperties = Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, {
    type: "string",
    minLength: 1,
    maxLength: 160
  }]));
  return {
    type: "object",
    required: ["source", "assignment"],
    properties: {
      source: { type: "string", minLength: 1, maxLength: 160 },
      ...scopeProperties,
      assignment: {
        type: "object",
        required: ["action", "expected_version"],
        properties: {
          action: { type: "string", enum: ["claim", "renew", "release", "transfer"] },
          expected_version: { type: "integer", minimum: 0 },
          lease_seconds: { type: "integer", minimum: 60, maximum: 3600, default: 900 },
          target_reviewer_hash: {
            type: "string",
            pattern: "^[A-Za-z0-9:_-]{8,160}$",
            description: "Hash alias only; raw reviewer identity is forbidden. Required for transfer."
          },
          reason_code: { type: "string", pattern: "^[a-z0-9_]{3,64}$" }
        },
        additionalProperties: false
      }
    },
    additionalProperties: false,
    description: "Identity and scope are server verified. The body cannot contain a disposition, score, risk, or release authority."
  };
}

function multimodalReviewOperationalStateSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "status", "version", "event_count", "lock_active", "can_be_claimed",
      "authoritative_disposition_recorded", "release_authority", "a2_decision_recomputed"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_operational_state.v1" },
      status: { type: "string", enum: ["unassigned", "claimed", "expired"] },
      version: { type: "integer", minimum: 0 },
      assigned_reviewer_hash: { type: ["string", "null"] },
      previous_reviewer_hash: { type: ["string", "null"] },
      lease_started_at: { type: ["string", "null"], format: "date-time" },
      lease_expires_at: { type: ["string", "null"], format: "date-time" },
      last_action: { type: ["string", "null"] },
      last_action_at: { type: ["string", "null"], format: "date-time" },
      reason_code: { type: ["string", "null"] },
      event_count: { type: "integer", minimum: 0 },
      lock_active: { type: "boolean" },
      can_be_claimed: { type: "boolean" },
      authoritative_disposition_recorded: { type: "boolean", const: false },
      release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false }
    },
    additionalProperties: false
  };
}

function multimodalReviewAssignmentReceiptSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source", "queue_id", "event_id", "event_hash", "action", "status",
      "version", "release_authority", "a2_decision_recomputed", "release_decision_changed",
      "created_at", "idempotency"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_assignment_receipt.v1" },
      source: { type: "string" },
      queue_id: { type: "string" },
      event_id: { type: "string" },
      event_hash: sha256Schema(),
      action: { type: "string", enum: ["claim", "renew", "release", "transfer"] },
      status: { type: "string", enum: ["unassigned", "claimed", "expired"] },
      version: { type: "integer", minimum: 1 },
      assigned_reviewer_hash: { type: ["string", "null"] },
      lease_expires_at: { type: ["string", "null"], format: "date-time" },
      reason_code: { type: "string" },
      release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      release_decision_changed: { type: "boolean", const: false },
      created_at: { type: "string", format: "date-time" },
      idempotency: { type: "object", additionalProperties: true },
      event_envelope: { type: "object", additionalProperties: true },
      safety: { type: "object", additionalProperties: true }
    },
    additionalProperties: true
  };
}

function multimodalReviewEvidenceReferenceSchema() {
  return {
    type: "object",
    required: ["kind", "evidence_hash"],
    properties: {
      kind: multimodalReviewEvidenceKindSchema(),
      evidence_hash: sha256Schema(),
      binding_hash: sha256Schema()
    },
    additionalProperties: false,
    description: "Hash-only reference. Raw evidence, URLs, signed URLs, local paths, and free text are forbidden."
  };
}

function multimodalReviewEvidenceRequestSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "request_id", "queue_id", "case_id", "status", "version",
      "owner_lane", "required_evidence_kinds", "submitted_evidence_kinds", "evidence_refs",
      "due_at", "overdue", "event_count", "authority_boundary", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_evidence_request.v1" },
      request_id: { type: "string", pattern: "^mmreq_[a-f0-9]{20}$" },
      queue_id: { type: "string", minLength: 1, maxLength: 240 },
      case_id: { type: "string", minLength: 1, maxLength: 240 },
      comparison_hash: sha256Schema(),
      status: { type: "string", enum: ["open", "overdue", "submitted", "accepted", "cancelled"] },
      version: { type: "integer", minimum: 1 },
      owner_lane: multimodalReviewEvidenceOwnerLaneSchema(),
      required_evidence_kinds: {
        type: "array", minItems: 1, maxItems: 8, uniqueItems: true, items: multimodalReviewEvidenceKindSchema()
      },
      submitted_evidence_kinds: {
        type: "array", maxItems: 8, uniqueItems: true, items: multimodalReviewEvidenceKindSchema()
      },
      evidence_refs: {
        type: "array", maxItems: 24, items: { $ref: "#/components/schemas/MultimodalReviewEvidenceReference" }
      },
      due_at: { type: "string", format: "date-time" },
      overdue: { type: "boolean" },
      last_action: { type: ["string", "null"], enum: ["requested", "submitted", "accepted", "rejected", "cancelled", null] },
      last_action_at: { type: ["string", "null"], format: "date-time" },
      last_reason_code: { type: ["string", "null"], pattern: "^[a-z0-9_]{3,64}$" },
      created_at: { type: "string", format: "date-time" },
      event_count: { type: "integer", minimum: 1 },
      terminal_event_hash: sha256Schema(),
      history: { type: "array", maxItems: 1000, items: { type: "object", additionalProperties: true } },
      integrity: { type: "object", additionalProperties: true },
      authority_boundary: {
        type: "object",
        required: [
          "evidence_accepted", "authoritative_human_disposition_recorded", "release_authority",
          "a2_decision_recomputed", "release_decision_changed"
        ],
        properties: {
          evidence_accepted: { type: "boolean" },
          authoritative_human_disposition_recorded: { type: "boolean", const: false },
          release_authority: { type: "boolean", const: false },
          a2_decision_recomputed: { type: "boolean", const: false },
          release_decision_changed: { type: "boolean", const: false }
        },
        additionalProperties: false
      },
      safety: { type: "object", additionalProperties: true }
    },
    additionalProperties: false
  };
}

function multimodalReviewEvidenceRequestListSchema() {
  return {
    type: "object",
    required: ["schema_version", "source", "queue_id", "case_id", "summary", "requests", "authority_boundary", "safety"],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_evidence_request_list.v1" },
      source: { type: "string" },
      ...multimodalScopeProperties(),
      tenant_scope: { type: "object", additionalProperties: true },
      queue_id: { type: "string" },
      case_id: { type: "string" },
      summary: { type: "object", additionalProperties: true },
      requests: {
        type: "array", maxItems: 1000, items: { $ref: "#/components/schemas/MultimodalReviewEvidenceRequest" }
      },
      authority_boundary: { type: "object", additionalProperties: true },
      safety: { type: "object", additionalProperties: true }
    },
    additionalProperties: true
  };
}

function multimodalReviewEvidenceRequestCreateSchema() {
  return evidenceMutationEnvelope("evidence_request", {
    type: "object",
    required: ["expected_version", "owner_lane", "required_evidence_kinds", "due_at", "reason_code"],
    properties: {
      expected_version: { type: "integer", const: 0 },
      owner_lane: multimodalReviewEvidenceOwnerLaneSchema(),
      required_evidence_kinds: {
        type: "array", minItems: 1, maxItems: 8, uniqueItems: true, items: multimodalReviewEvidenceKindSchema()
      },
      due_at: { type: "string", format: "date-time", description: "Must be in the future and no more than 30 days from server time." },
      reason_code: { type: "string", pattern: "^[a-z0-9_]{3,64}$" }
    },
    additionalProperties: false
  });
}

function multimodalReviewEvidenceSubmissionSchema() {
  return evidenceMutationEnvelope("submission", {
    type: "object",
    required: ["expected_version", "owner_lane", "evidence_refs", "reason_code"],
    properties: {
      expected_version: { type: "integer", minimum: 1 },
      owner_lane: multimodalReviewEvidenceOwnerLaneSchema(),
      evidence_refs: {
        type: "array",
        minItems: 1,
        maxItems: 24,
        items: { $ref: "#/components/schemas/MultimodalReviewEvidenceReference" }
      },
      reason_code: { type: "string", pattern: "^[a-z0-9_]{3,64}$" }
    },
    additionalProperties: false
  });
}

function multimodalReviewEvidenceReviewSchema() {
  return evidenceMutationEnvelope("review", {
    type: "object",
    required: ["expected_version", "action", "reason_code"],
    properties: {
      expected_version: { type: "integer", minimum: 1 },
      action: { type: "string", enum: ["accept", "reject", "cancel"] },
      reason_code: { type: "string", pattern: "^[a-z0-9_]{3,64}$" }
    },
    additionalProperties: false
  });
}

function multimodalReviewEvidenceRequestReceiptSchema() {
  return {
    type: "object",
    required: [
      "schema_version", "source", "queue_id", "request_id", "event_id", "event_hash",
      "event_type", "action", "status", "version", "owner_lane", "required_evidence_kinds",
      "submitted_evidence_kinds", "due_at", "evidence_accepted",
      "authoritative_human_disposition_recorded", "release_authority", "a2_decision_recomputed",
      "release_decision_changed", "created_at", "idempotency", "safety"
    ],
    properties: {
      schema_version: { type: "string", const: "a3.multimodal_review_evidence_request_receipt.v1" },
      source: { type: "string" },
      ...multimodalScopeProperties(),
      tenant_scope: { type: "object", additionalProperties: true },
      queue_id: { type: "string" },
      request_id: { type: "string", pattern: "^mmreq_[a-f0-9]{20}$" },
      event_id: { type: "string", pattern: "^mmre_[a-f0-9]{20}$" },
      event_hash: sha256Schema(),
      event_type: { type: "string", enum: ["requested", "submitted", "accepted", "rejected", "cancelled"] },
      action: { type: "string", enum: ["create", "submit", "accept", "reject", "cancel"] },
      status: { type: "string", enum: ["open", "overdue", "submitted", "accepted", "cancelled"] },
      version: { type: "integer", minimum: 1 },
      owner_lane: multimodalReviewEvidenceOwnerLaneSchema(),
      required_evidence_kinds: { type: "array", items: multimodalReviewEvidenceKindSchema() },
      submitted_evidence_kinds: { type: "array", items: multimodalReviewEvidenceKindSchema() },
      due_at: { type: "string", format: "date-time" },
      reason_code: { type: "string", pattern: "^[a-z0-9_]{3,64}$" },
      evidence_accepted: { type: "boolean" },
      authoritative_human_disposition_recorded: { type: "boolean", const: false },
      release_authority: { type: "boolean", const: false },
      a2_decision_recomputed: { type: "boolean", const: false },
      release_decision_changed: { type: "boolean", const: false },
      created_at: { type: "string", format: "date-time" },
      idempotency: { type: "object", additionalProperties: true },
      event_envelope: { type: "object", additionalProperties: true },
      safety: { type: "object", additionalProperties: true }
    },
    additionalProperties: true
  };
}

function evidenceMutationEnvelope(field, payloadSchema) {
  return {
    type: "object",
    required: ["source", field],
    properties: {
      source: { type: "string", minLength: 1, maxLength: 160 },
      ...multimodalScopeProperties(),
      [field]: payloadSchema
    },
    additionalProperties: false,
    description: "Scope and identity are server verified. Idempotency is accepted only from the Idempotency-Key header."
  };
}

function multimodalScopeProperties() {
  return Object.fromEntries(TENANT_SCOPE_CONTRACT.required.map((field) => [field, {
    type: "string",
    minLength: 1,
    maxLength: 160
  }]));
}

function multimodalReviewEvidenceKindSchema() {
  return {
    type: "string",
    enum: [
      "a1_run_trace",
      "a1_tool_call",
      "a1_artifact",
      "a2_judge_receipt",
      "a2_review_receipt",
      "media_evidence",
      "provider_identity",
      "candidate_binding"
    ]
  };
}

function multimodalReviewEvidenceOwnerLaneSchema() {
  return { type: "string", enum: ["execution", "evaluation", "customer_operator"] };
}

function multimodalAuthorityBoundary() {
  return {
    upstream_release_authority: false,
    queue_receipts_release_authority: false,
    a3_recomputed_risk: false,
    a3_recomputed_release_decision: false,
    candidate_binding_verified: false,
    can_change_release_decision: false,
    assignment_events_release_authority: false,
    assignment_events_change_a2_decision: false,
    evidence_request_acceptance_is_human_disposition: false,
    evidence_requests_release_authority: false,
    evidence_requests_change_a2_decision: false
  };
}

function multimodalEvidenceRequestAuthorityBoundary() {
  return {
    evidence_acceptance_is_human_disposition: false,
    authoritative_human_disposition_recorded: false,
    release_authority: false,
    a2_decision_recomputed: false,
    release_decision_changed: false
  };
}

function multimodalRepeatStabilityAuthorityBoundary() {
  return {
    provider_is_truth: false,
    authoritative_human_disposition_recorded: false,
    candidate_binding_verified: false,
    a2_decision_recomputed: false,
    release_authority: false,
    release_decision_changed: false,
    production_ready: false
  };
}

function multimodalRepeatStabilityEvidenceBoundary() {
  return {
    hashes_and_aggregate_metrics_only: true,
    repeat_stability_is_quality_pass: false,
    raw_provider_payload_forbidden: true,
    raw_provider_text_forbidden: true,
    raw_reviewer_identity_forbidden: true,
    urls_and_signed_urls_forbidden: true,
    non_empty_human_receipts_fail_closed_until_exact_schema: true
  };
}

function multimodalAuthorityBoundaryProperties() {
  return Object.fromEntries(Object.keys(multimodalAuthorityBoundary()).map((field) => [field, { type: "boolean", const: false }]));
}

function sha256Schema() {
  return { type: "string", pattern: "^sha256:[a-f0-9]{64}$" };
}

function countSummarySchema(fields) {
  return {
    type: "object",
    required: [...fields],
    properties: Object.fromEntries(fields.map((field) => [field, { type: "integer", minimum: 0 }])),
    additionalProperties: false
  };
}

function multimodalLineageSchema() {
  return {
    type: "object",
    required: [
      "left_final_matrix_hash",
      "right_final_matrix_hash",
      "left_partial_journal_hash",
      "right_partial_journal_hash"
    ],
    properties: {
      left_final_matrix_hash: sha256Schema(),
      right_final_matrix_hash: sha256Schema(),
      left_partial_journal_hash: { type: "string", pattern: "^(|sha256:[a-f0-9]{64})$" },
      right_partial_journal_hash: { type: "string", pattern: "^(|sha256:[a-f0-9]{64})$" }
    },
    additionalProperties: false
  };
}

function typedJsonRequest(schemaName) {
  return {
    required: true,
    "x-secret-policy": "raw_secret_values_forbidden",
    content: { "application/json": { schema: { $ref: `#/components/schemas/${schemaName}` } } }
  };
}

function typedJsonResponse(description, schemaName) {
  return {
    description,
    content: { "application/json": { schema: { $ref: `#/components/schemas/${schemaName}` } } }
  };
}

function withIdempotencyHeader(parameters = []) {
  const filtered = (Array.isArray(parameters) ? parameters : []).filter((item) => item?.name !== "Idempotency-Key");
  return [...filtered, {
    name: "Idempotency-Key",
    in: "header",
    required: true,
    description: "Opaque caller-generated retry key. The raw value is never persisted.",
    schema: { type: "string", minLength: 8, maxLength: 160 }
  }];
}

function unique(values) {
  return [...new Set(values)];
}

function buildParityOperation(route, path) {
  const readOnly = route.method === "GET";
  const operation = {
    operationId: `a3${pascalCase(route.operation_id)}`,
    summary: `A3 protected operation: ${route.operation_id}.`,
    tags: tagsFor(route.operation_id),
    "x-schema-version": "a3.openapi_runtime_parity.v1",
    "x-tenant-scope": structuredClone(TENANT_SCOPE_CONTRACT),
    "x-auth": structuredClone(AUTH_CONTRACT),
    "x-rbac": {
      operation_id: route.operation_id,
      permission: route.required_permission,
      denied_state_required: true,
      evaluation: "server_side_against_verified_principal",
      client_declared_role_authoritative: false
    },
    "x-usage": {
      meters: ["api_requests"],
      source_of_truth: "A1 usage ledger; A3 only emits a metering intent."
    },
    "x-audit": {
      events: [`${route.operation_id}.requested`],
      payload_policy: "ids_hashes_refs_status_counts_only"
    },
    "x-a1-a2-contract": {
      a1: ["verified principal", "tenant scope", "usage and audit execution"],
      a2: ["GradeResult and release decision authority remain unchanged"],
      a3_rule: "A3 orchestrates product workflow and must not reinterpret A1 runtime facts or A2 decision semantics."
    },
    security: structuredClone(VERIFIED_PRINCIPAL_SECURITY),
    "x-access-class": readOnly ? "tenant_sensitive_read" : "tenant_sensitive_write",
    responses: {
      [readOnly ? "200" : "202"]: successResponse(path, readOnly),
      "401": { $ref: "#/components/responses/Unauthorized" },
      "403": { $ref: "#/components/responses/Forbidden" },
      "404": { $ref: "#/components/responses/NotFound" }
    }
  };

  const parameters = pathParameters(path);
  if (parameters.length) operation.parameters = parameters;
  if (!readOnly) {
    operation.requestBody = {
      required: true,
      "x-secret-policy": "raw_secret_values_forbidden",
      content: {
        "application/json": {
          schema: {
            type: "object",
            description: "Operation-specific typed payload. Tenant scope and identity are always resolved server-side.",
            additionalProperties: true
          }
        }
      }
    };
  }
  return operation;
}

function applyRequestBoundaryContract(operation, route) {
  operation["x-protected-options"] = {
    target_method_header: "Access-Control-Request-Method",
    target_route_authorization_required: true,
    a1_verified_principal_required_for_protected_route: true,
    metadata_only_access_audit_required: true,
    unregistered_or_unsupported_target_fails_closed: true,
    cors_enablement_claimed: false
  };
  if (!["GET", "HEAD"].includes(route.method)) {
    operation.responses ||= {};
    operation.responses["400"] = { $ref: "#/components/responses/BadRequest" };
    operation.responses["408"] = { $ref: "#/components/responses/RequestTimeout" };
    operation.responses["413"] = { $ref: "#/components/responses/PayloadTooLarge" };
    operation.responses["415"] = { $ref: "#/components/responses/UnsupportedMediaType" };
    operation.responses["422"] = { $ref: "#/components/responses/UnprocessableEntity" };
    operation["x-request-validation"] = {
      malformed_json: "sanitized_400_after_authentication_and_authorization",
      body_read_timeout: "sanitized_408_after_authentication_and_authorization",
      maximum_body_bytes_default: 1048576,
      payload_too_large: "sanitized_413_after_authentication_and_authorization",
      required_media_type: "application/json",
      unsupported_media_type: "sanitized_415_after_authentication_and_authorization",
      required_top_level_shape: "object",
      invalid_json_shape: "sanitized_422_after_authentication_and_authorization",
      unauthorized_precedence: "401",
      forbidden_precedence: "403",
      raw_body_echoed: false,
      metadata_only_denial_audit_required: true
    };
  }
}

function requestBoundaryContract() {
  return {
    schema_version: "a3.request_boundary_contract.v1",
    malformed_json: {
      authorized_status: 400,
      body_read_timeout_status: 408,
      payload_too_large_status: 413,
      unsupported_media_type_status: 415,
      invalid_json_shape_status: 422,
      unauthenticated_status: 401,
      unauthorized_status: 403,
      default_maximum_body_bytes: 1048576,
      default_body_read_timeout_ms: 10000,
      required_media_type: "application/json",
      required_top_level_shape: "object",
      response_body_policy: "fixed_sanitized_error",
      raw_body_logging_allowed: false,
      metadata_only_denial_audit_required: true,
      authorization_audit_unavailable_status: 503
    },
    protected_options: {
      target_method_header: "Access-Control-Request-Method",
      target_route_authorization_required: true,
      protected_preflight_audited: true,
      unknown_target_status: 403,
      raw_origin_logging_allowed: false,
      cors_enablement_claimed: false
    },
    authority: {
      identity_and_session: "A1",
      route_authorization_and_audit_orchestration: "A3",
      release_decision: "A2"
    }
  };
}

function sanitizedBadRequestResponse() {
  return sanitizedRequestBoundaryResponse(
    "The authenticated and authorized request body is not valid JSON."
  );
}

function sanitizedRequestBoundaryResponse(description) {
  return {
    description: `${description} The response and audit record never echo the request body or private identity data.`,
    "x-sanitized": true,
    headers: {
      "Cache-Control": {
        description: "Prevents caching of request validation failures.",
        schema: { type: "string", const: "no-store" }
      }
    },
    content: {
      "application/json": {
        schema: { $ref: "#/components/schemas/SanitizedBadRequestError" }
      }
    }
  };
}

function sanitizedBadRequestSchema() {
  return {
    type: "object",
    required: ["schema_version", "error"],
    properties: {
      schema_version: { type: "string", const: "a3.sanitized_bad_request.v1" },
      error: {
        type: "string",
        enum: [
          "invalid_json",
          "request_timeout",
          "payload_too_large",
          "unsupported_media_type",
          "invalid_json_shape"
        ]
      },
      request_id: { type: "string", minLength: 1, maxLength: 128 }
    },
    additionalProperties: false,
    "x-sanitized": true
  };
}

function sanitizedServiceUnavailableResponse() {
  return {
    description: "Authorization configuration or metadata-only access-audit persistence is unavailable. No protected handler is executed.",
    "x-sanitized": true,
    headers: {
      "Cache-Control": {
        description: "Prevents caching of authorization-boundary failures.",
        schema: { type: "string", const: "no-store" }
      }
    },
    content: {
      "application/json": {
        schema: { $ref: "#/components/schemas/SanitizedServiceUnavailableError" }
      }
    }
  };
}

function sanitizedServiceUnavailableSchema() {
  return {
    type: "object",
    required: ["schema_version", "error", "message"],
    properties: {
      schema_version: { type: "string", const: "a3.route_access_unavailable.v1" },
      error: {
        type: "string",
        enum: ["authorization_audit_unavailable", "authorization_configuration_invalid"]
      },
      message: { type: "string", const: "The authorization service is temporarily unavailable." }
    },
    additionalProperties: false,
    "x-sanitized": true
  };
}

function successResponse(path, readOnly) {
  const contentType = path.startsWith("/reports/") && readOnly ? "text/html" : "application/json";
  return {
    description: readOnly ? "Sanitized tenant-scoped response." : "Mutation accepted for trusted execution or returned as a fail-closed plan.",
    content: {
      [contentType]: {
        schema: contentType === "text/html"
          ? { type: "string" }
          : { type: "object", additionalProperties: true }
      }
    }
  };
}

function pathParameters(path) {
  return [...String(path).matchAll(/\{([^}]+)\}/g)].map((match) => {
    const name = match[1];
    const component = {
      releaseId: "ReleaseId",
      reportId: "ReportId",
      runId: "RunId",
      caseId: "CaseId",
      api_key_id: "ApiKeyId"
    }[name];
    return component
      ? { $ref: `#/components/parameters/${component}` }
      : identifierParameter(name, `${name} path identifier.`);
  });
}

function identifierParameter(name, description) {
  return {
    name,
    in: "path",
    required: true,
    description,
    schema: {
      type: "string",
      minLength: 1,
      maxLength: 160
    }
  };
}

function openApiOperationIndex(spec = {}) {
  const operations = new Map();
  for (const [path, pathItem] of Object.entries(spec.paths || {})) {
    for (const method of ["get", "post", "put", "patch", "delete"]) {
      if (pathItem?.[method]) operations.set(routeKey(method, path), pathItem[method]);
    }
  }
  return operations;
}

function routeKey(method, path) {
  return `${String(method).toUpperCase()} ${normalizeContractPath(path)}`;
}

function pascalCase(value) {
  return String(value).split("_").map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`).join("");
}

function tagsFor(operationId) {
  if (/report/.test(operationId)) return ["Reports"];
  if (/billing/.test(operationId)) return ["Billing"];
  if (/github|release|review/.test(operationId)) return ["Release Gate", "Review"];
  if (/admin|api_key|teammate/.test(operationId)) return ["Admin"];
  if (/trust/.test(operationId)) return ["Trust"];
  return ["Operations"];
}

async function run(argv = process.argv.slice(2)) {
  const outputPath = resolve(argv[0] || "docs/a3/openapi/a3_commercial_api.openapi.json");
  const spec = JSON.parse(await readFile(outputPath, "utf8"));
  const synchronized = synchronizeA3OpenApiRuntimeParity(spec);
  await writeFile(outputPath, `${JSON.stringify(synchronized, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(inspectA3OpenApiRuntimeParity(synchronized))}\n`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  run().catch((error) => {
    process.stderr.write(`${error.name}: ${error.message}\n`);
    process.exitCode = 1;
  });
}
