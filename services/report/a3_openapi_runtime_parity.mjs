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
    dashboard.required = unique([...(dashboard.required || []), "deployment_handoff", "deployment_receipt_inbox", "deployment_acceptance_projection"]);
    dashboard.properties ||= {};
    dashboard.properties.deployment_handoff = { $ref: "#/components/schemas/DeploymentHandoff" };
    dashboard.properties.deployment_receipt_inbox = { $ref: "#/components/schemas/DeploymentReceiptInbox" };
    dashboard.properties.deployment_acceptance_projection = { $ref: "#/components/schemas/DeploymentAcceptanceProjection" };
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
