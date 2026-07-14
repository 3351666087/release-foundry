import { buildA3TenantScope } from "./a3_tenant_scope.mjs";

export const A3_AUTH_CONTEXT_SCHEMA_VERSION = "a3.auth_context.v1";
export const A3_RBAC_POLICY_SCHEMA_VERSION = "a3.rbac_policy.v1";
export const A3_AUTHZ_DECISION_SCHEMA_VERSION = "a3.authz_decision.v1";

export const A3_RBAC_ROLES = {
  owner: [
    "project:read",
    "project:ingest",
    "reports:create",
    "reports:share",
    "reports:revoke",
    "release:review",
    "release:approve",
    "deployment:read",
    "deployment:submit",
    "deployment:review",
    "admin:plan",
    "team:manage",
    "api_keys:manage",
    "usage:read",
    "billing:read",
    "trust:read",
    "trust:publish",
    "audit:read",
    "notifications:read",
    "notifications:configure",
    "notifications:test"
  ],
  admin: [
    "project:read",
    "project:ingest",
    "reports:create",
    "reports:share",
    "reports:revoke",
    "release:review",
    "deployment:read",
    "deployment:submit",
    "deployment:review",
    "admin:plan",
    "team:manage",
    "api_keys:manage",
    "usage:read",
    "trust:read",
    "audit:read",
    "notifications:read",
    "notifications:configure",
    "notifications:test"
  ],
  developer: [
    "project:read",
    "project:ingest",
    "reports:create",
    "usage:read",
    "deployment:read",
    "deployment:submit"
  ],
  reviewer: [
    "project:read",
    "reports:create",
    "reports:share",
    "release:review",
    "release:approve",
    "deployment:read",
    "deployment:review",
    "trust:read",
    "audit:read",
    "notifications:read"
  ],
  auditor: [
    "project:read",
    "reports:create",
    "trust:read",
    "audit:read",
    "usage:read",
    "deployment:read",
    "notifications:read"
  ],
  billing_admin: [
    "project:read",
    "usage:read",
    "billing:read",
    "admin:plan"
  ],
  service_account: [
    "project:read",
    "project:ingest",
    "reports:create",
    "release:review",
    "deployment:read",
    "deployment:submit",
    "deployment:verify",
    "notifications:deliver"
  ],
  viewer: [
    "project:read",
    "notifications:read"
  ]
};

export const A3_AUTHZ_OPERATION_POLICIES = [
  operation("read_auth_context", "GET /api/a3/auth/context", "project:read", "read_only", {
    event: "auth.context_read",
    resourceType: "auth_context",
    surface: "admin_console"
  }),
  operation("read_rbac_policy", "GET /api/a3/auth/rbac-policy", "audit:read", "read_only", {
    event: "rbac.policy_read",
    resourceType: "rbac_policy",
    surface: "admin_console"
  }),
  operation("authorize_operation", "POST /api/a3/auth/authorize", "project:read", "read_only", {
    event: "authz.operation_checked",
    resourceType: "authz_decision",
    surface: "admin_console"
  }),
  operation("read_dashboard", "GET /api/a3/dashboard", "project:read", "read_only", {
    event: "project.dashboard_read",
    resourceType: "dashboard"
  }),
  operation("preflight_ui_action", "POST /api/a3/ui-actions/preflight", "project:read", "read_only", {
    event: "ui_action.preflight_checked",
    resourceType: "ui_action_preflight"
  }),
  operation("read_db_contract", "GET /api/a3/db-contract", "audit:read", "read_only", {
    event: "database.contract_read",
    resourceType: "database_contract",
    surface: "admin_console"
  }),
  operation("read_db_migrations", "GET /api/a3/db-migrations", "audit:read", "read_only", {
    event: "database.migrations_read",
    resourceType: "database_migration_plan",
    surface: "admin_console"
  }),
  operation("read_live_workflow_readiness", "GET /api/a3/live-workflow/readiness", "audit:read", "read_only", {
    event: "live_workflow.readiness_read",
    resourceType: "live_workflow_readiness"
  }),
  operation("read_live_ops_control_plane", "GET /api/a3/live-ops/control-plane", "audit:read", "read_only", {
    event: "live_ops.control_plane_read",
    resourceType: "live_ops_control_plane"
  }),
  operation("read_commercial_api_contract", "GET /api/a3/commercial-api/contract", "audit:read", "read_only", {
    event: "commercial_api.contract_read",
    resourceType: "commercial_api_contract",
    surface: "admin_console"
  }),
  operation("read_evidence_spine", "GET /api/a3/a1-a2/evidence-spine", "audit:read", "read_only", {
    event: "a1_a2.evidence_spine_read",
    resourceType: "a1_a2_evidence_spine",
    a1: ["RunResult, TraceEvent, Observation, ToolCall evidence references"],
    a2: ["GradeResult, Judge, and Decision Ledger evidence references"]
  }),
  operation("read_release_decision_provenance", "GET /api/a3/release-decision/provenance", "project:read", "read_only", {
    event: "release_decision.provenance_read",
    resourceType: "release_decision_provenance",
    a2: ["A2 owns Release Decision and Decision Ledger semantics; A3 reads without recomputation"]
  }),
  operation("read_release_evidence_summary", "GET /api/a3/releases/:releaseId/evidence-summary", "project:read", "read_only", {
    event: "release_evidence.summary_read",
    resourceType: "release_evidence_summary",
    a2: ["A2 owns release policy and decision semantics; A3 presents supplied evidence"]
  }),
  operation("read_release_evidence_health", "GET /api/a3/releases/:releaseId/evidence-health", "project:read", "read_only", {
    event: "release_evidence.health_read",
    resourceType: "release_evidence_health",
    a2: ["A2 owns release policy and decision semantics; A3 presents supplied evidence"]
  }),
  operation("read_release_evidence_diff", "GET /api/a3/releases/:releaseId/evidence-diff", "project:read", "read_only", {
    event: "release_evidence.diff_read",
    resourceType: "release_evidence_diff",
    a2: ["A2 owns release policy and decision semantics; A3 compares supplied evidence metadata"]
  }),
  operation("read_release_readbacks", "GET /api/a3/releases/:releaseId/readbacks", "audit:read", "read_only", {
    event: "release_evidence.readbacks_read",
    resourceType: "release_evidence_readback",
    a1: ["GitHub readback worker boundary"],
    a2: ["ReleaseGate evidence state"]
  }),
  operation("read_admin_console", "GET /api/a3/admin/console", "admin:plan", "read_only", {
    event: "admin.console_read",
    resourceType: "saas_admin_console",
    surface: "admin_console"
  }),
  operation("read_enterprise_readiness", "GET /api/a3/enterprise/readiness", "audit:read", "read_only", {
    event: "enterprise.readiness_read",
    resourceType: "enterprise_readiness",
    surface: "admin_console"
  }),
  operation("read_admin_actions", "GET /api/a3/admin/actions", "admin:plan", "read_only", {
    event: "admin.actions_read",
    resourceType: "saas_admin_action",
    surface: "admin_console"
  }),
  operation("read_review_workflow", "GET /api/a3/review/workflow", "release:review", "read_only", {
    event: "review.workflow_read",
    resourceType: "review_workflow",
    a2: ["A2 ReleaseGate and policy evaluation are authoritative"]
  }),
  operation("read_self_host_sandbox_calibration", "GET /api/a3/deployment/sandbox-calibration", "deployment:read", "read_only", {
    event: "deployment.sandbox_calibration_read",
    resourceType: "self_host_sandbox_calibration",
    a1: ["local control-plane health, worker retry/dead-letter, lease recovery, and object-integrity behavior"],
    a2: ["A2 remains the sole release-decision authority; sandbox evidence never changes its decision"]
  }),
  operation("read_deployment_receipts", "GET /api/a3/deployment/receipts", "deployment:read", "read_only", {
    event: "deployment.receipts_read",
    resourceType: "deployment_receipt_inbox",
    a1: ["deployment, identity, queue, storage, and GitHub worker receipts"],
    a2: ["same-candidate Trusted Spine and immutable Decision Ledger selectors"]
  }),
  operation("list_runs", "GET /api/a3/runs", "project:read", "read_only", {
    event: "run.listed",
    resourceType: "run"
  }),
  operation("read_run", "GET /api/a3/runs/:runId", "project:read", "read_only", {
    event: "run.read",
    resourceType: "run"
  }),
  operation("read_case", "GET /api/a3/cases/:caseId", "project:read", "read_only", {
    event: "case.read",
    resourceType: "case"
  }),
  operation("read_report_center", "GET /api/a3/reports/center", "project:read", "read_only", {
    event: "report.center_read",
    resourceType: "report_center"
  }),
  operation("read_artifact_registry", "GET /api/a3/artifacts/registry", "audit:read", "read_only", {
    event: "artifact.registry_read",
    resourceType: "artifact_registry"
  }),
  operation("read_product_console", "GET /api/a3/product/console", "project:read", "read_only", {
    event: "product.console_read",
    resourceType: "product_console"
  }),
  operation("list_reports", "GET /api/a3/reports", "project:read", "read_only", {
    event: "report.listed",
    resourceType: "shareable_report"
  }),
  operation("read_report", "GET /api/a3/reports/:reportId", "project:read", "read_only", {
    event: "report.read",
    resourceType: "shareable_report"
  }),
  operation("read_report_manifest", "GET /api/a3/reports/:reportId/manifest", "project:read", "read_only", {
    event: "report.manifest_read",
    resourceType: "report_manifest"
  }),
  operation("read_hosted_report", "GET /reports/:reportId", "project:read", "read_only", {
    event: "hosted_report.read",
    resourceType: "shareable_report"
  }),
  operation("import_a1_run_result", "POST /api/a3/import/a1-run-result", "project:ingest", "local_write", {
    event: "a1.run_result_imported",
    resourceType: "a1_run_result",
    a1: ["RunResult", "TraceEvent", "Observation", "ToolCall"],
    a2: ["GradeResult join boundary"]
  }),
  operation("import_a2_grade_result", "POST /api/a3/import/a2-grade-result", "project:ingest", "local_write", {
    event: "a2.grade_result_imported",
    resourceType: "a2_grade_result",
    a1: ["RunResult join boundary"],
    a2: ["GradeResult", "Judge", "FailureTaxonomy"]
  }),
  operation("import_a2_multimodal_comparison", "POST /api/a3/import/a2-multimodal-comparison", "project:ingest", "local_write", {
    event: "a2.multimodal_comparison_imported",
    resourceType: "multimodal_review_snapshot",
    a1: ["verified principal", "five-level tenant scope", "audit and usage execution"],
    a2: ["MultimodalCrossProviderComparison", "non-authoritative human-review queue receipt"]
  }),
  operation("import_a2_multimodal_repeat_stability", "POST /api/a3/import/a2-multimodal-repeat-stability", "project:ingest", "local_write", {
    event: "a2.multimodal_repeat_stability_imported",
    resourceType: "multimodal_repeat_stability",
    a1: ["verified ingest principal", "five-level tenant scope", "audit and usage execution"],
    a2: ["MultiRepeatComparison", "real-review collection", "review conservation", "shared-candidate verification"]
  }),
  operation("read_multimodal_review_queue", "GET /api/a3/review/multimodal-queue", "release:review", "read_only", {
    event: "review.multimodal_queue_read",
    resourceType: "multimodal_review_queue",
    a2: ["semantic disagreement and queue receipt facts remain non-release-authoritative"]
  }),
  operation("read_multimodal_repeat_stability", "GET /api/a3/review/multimodal-repeat-stability", "release:review", "read_only", {
    event: "review.multimodal_repeat_stability_read",
    resourceType: "multimodal_repeat_stability",
    a2: ["repeat stability is read-only evidence and never becomes a release decision"]
  }),
  operation("manage_multimodal_review_assignment", "POST /api/a3/review/multimodal-queue/:queueId/assignment", "release:review", "local_write", {
    event: "review.multimodal_assignment_changed",
    resourceType: "multimodal_review_assignment",
    a1: ["server-verified reviewer identity, five-level scope, durable audit and outbox"],
    a2: ["queue receipt remains non-authoritative; assignment never rewrites risk or release decisions"]
  }),
  operation("read_multimodal_review_evidence_requests", "GET /api/a3/review/multimodal-queue/:queueId/evidence-requests", "release:review", "read_only", {
    event: "review.multimodal_evidence_requests_read",
    resourceType: "multimodal_review_evidence_request",
    a1: ["server-verified reviewer identity and exact five-level tenant scope"],
    a2: ["evidence requests remain coordination metadata and never become human dispositions"]
  }),
  operation("create_multimodal_review_evidence_request", "POST /api/a3/review/multimodal-queue/:queueId/evidence-requests", "release:review", "local_write", {
    event: "review.multimodal_evidence_request.requested",
    resourceType: "multimodal_review_evidence_request",
    a1: ["active reviewer assignment lease, audit, outbox, and hash-only evidence contract"],
    a2: ["requested evidence kinds cannot alter score, risk, or release authority"]
  }),
  operation("submit_multimodal_review_evidence_request", "POST /api/a3/review/multimodal-queue/:queueId/evidence-requests/:requestId/submissions", "project:ingest", "local_write", {
    event: "review.multimodal_evidence_request.submitted",
    resourceType: "multimodal_review_evidence_request",
    a1: ["server-verified ingest principal, hash-only evidence refs, audit, and outbox"],
    a2: ["A2 judge or review receipt hashes may be referenced but never rewritten"]
  }),
  operation("review_multimodal_review_evidence_request", "POST /api/a3/review/multimodal-queue/:queueId/evidence-requests/:requestId/review", "release:review", "local_write", {
    event: "review.multimodal_evidence_request.reviewed",
    resourceType: "multimodal_review_evidence_request",
    a1: ["active reviewer assignment lease, optimistic version, durable audit and outbox"],
    a2: ["accepting evidence is not an A2 human disposition and cannot change release readiness"]
  }),
  operation("share_report", "POST /api/a3/reports/share", "reports:share", "local_write", {
    event: "report.share_link_created",
    resourceType: "shareable_report",
    a1: ["RunResult", "artifact refs"],
    a2: ["GradeResult", "ReleaseGate"]
  }),
  operation("revoke_report", "POST /api/a3/reports/:reportId/revoke", "reports:revoke", "local_write", {
    event: "report.share_link_revoked",
    resourceType: "shareable_report"
  }),
  operation("view_report", "POST /api/a3/reports/:reportId/view", "project:read", "local_write", {
    event: "report.viewed",
    resourceType: "shareable_report"
  }),
  operation("submit_review_waiver", "POST /api/a3/review/waivers", "release:review", "local_write", {
    event: "waiver.requested",
    resourceType: "review_waiver",
    a2: ["ReleaseGate", "policy evaluation"]
  }),
  operation("submit_review_approval", "POST /api/a3/review/approvals", "release:approve", "local_write", {
    event: "approval.recorded",
    resourceType: "review_approval",
    a2: ["ReleaseGate", "policy evaluation"]
  }),
  operation("submit_review_denial", "POST /api/a3/review/denials", "release:review", "local_write", {
    event: "denial.recorded",
    resourceType: "review_denial",
    a2: ["ReleaseGate", "policy evaluation"]
  }),
  operation("submit_deployment_receipt", "POST /api/a3/deployment/receipts", "deployment:submit", "local_write", {
    event: "deployment.receipt_submitted",
    resourceType: "deployment_receipt",
    a1: ["sanitized deployment receipt metadata and evidence hashes"],
    a2: ["same-candidate authority selectors; A3 never recomputes A2"]
  }),
  operation("review_deployment_receipt", "POST /api/a3/deployment/receipts/:receiptId/review", "deployment:review", "local_write", {
    event: "deployment.receipt_reviewed",
    resourceType: "deployment_receipt",
    a1: ["external verifier readback remains authoritative"],
    a2: ["acknowledgement never changes A2 Release Ready"]
  }),
  operation("verify_deployment_receipt", "POST /internal/a3/deployment/receipts/:receiptId/verify", "deployment:verify", "local_write", {
    event: "deployment.receipt_authoritatively_verified",
    resourceType: "deployment_receipt_readback",
    a1: ["trusted service-account identity and authoritative deployment verifier resolver"],
    a2: ["A2 same-candidate authority claims are consumed without recomputation"],
    serviceAccountOnly: true,
    requiresHostedAuth: true
  }),
  operation("submit_admin_action", "POST /api/a3/admin/actions/submit", "admin:plan", "plan_only", {
    event: "admin.action_requested",
    resourceType: "saas_admin_action"
  }),
  operation("plan_admin_action", "POST /api/a3/admin/actions/plan", "admin:plan", "plan_only", {
    event: "admin.action_planned",
    resourceType: "saas_admin_action_plan"
  }),
  operation("capture_release_readback", "POST /api/a3/releases/:releaseId/readbacks", "release:review", "local_write", {
    event: "release_evidence.readback_captured",
    resourceType: "release_evidence_readback",
    a1: ["GitHub readback worker boundary"],
    a2: ["ReleaseGate evidence state"]
  }),
  operation("publish_github_check", "POST /api/a3/github/check-run/publish", "release:review", "local_write", {
    event: "github.check_publish_requested",
    resourceType: "github_publish_receipt",
    a1: ["GitHub App or Actions worker boundary", "hosted secret storage"],
    a2: ["ReleaseGate evidence state"]
  }),
  operation("publish_github_pr_comment", "POST /api/a3/github/pr-comment/publish", "release:review", "local_write", {
    event: "github.pr_comment_publish_requested",
    resourceType: "github_publish_receipt",
    a1: ["GitHub App or Actions worker boundary", "hosted secret storage"],
    a2: ["ReleaseGate evidence state"]
  }),
  operation("read_event_outbox", "GET /api/a3/events/outbox", "audit:read", "read_only", {
    event: "event_outbox.read",
    resourceType: "event_outbox"
  }),
  operation("read_schema_drift", "GET /api/a3/a1-a2/schema-drift", "audit:read", "read_only", {
    event: "schema_drift.read",
    resourceType: "a1_a2_schema_drift_radar",
    a1: ["RunResult", "TraceEvent", "Observation", "ToolCall schemas"],
    a2: ["GradeResult", "ReleaseGate", "result persistence schemas"]
  }),
  operation("read_peer_branch_calibration", "GET /api/a3/peer-branches/calibration", "audit:read", "read_only", {
    event: "peer_branch_calibration.read",
    resourceType: "a1_a2_peer_branch_calibration",
    a1: ["billing ledger", "route parity", "quota", "API key metadata", "evidence bundles"],
    a2: ["cross-lane security context", "release unblock checklist", "SQL store report", "scenario backlog"]
  }),
  operation("read_usage", "GET /api/a3/usage/ledger", "usage:read", "read_only", {
    event: "usage.read",
    resourceType: "usage_ledger",
    a1: ["usage ledger"],
    a2: ["model cost policy"]
  }),
  operation("read_billing_readiness", "GET /api/a3/billing/readiness", "billing:read", "read_only", {
    event: "billing.readiness_read",
    resourceType: "billing_readiness",
    a1: ["billing ledger"]
  }),
  operation("read_billing_migration_readiness", "GET /api/a3/billing/migration-readiness", "billing:read", "read_only", {
    event: "billing.migration_readiness_read",
    resourceType: "billing_migration_readiness",
    surface: "usage_billing",
    a1: ["read-only billing ledger summary", "durable billing migration manifest", "provider event replay evidence"],
    a2: ["security verification", "model cost policy"]
  }),
  operation("read_notification_control_plane", "GET /api/a3/notifications/control-plane", "notifications:read", "read_only", {
    event: "notification.control_plane_read",
    resourceType: "notification_control_plane",
    surface: "release_notifications",
    a1: ["hosted notification workers", "encrypted connector refs", "event outbox", "usage ledger"],
    a2: ["release policy", "failure taxonomy", "redaction verification"]
  }),
  operation("rotate_api_key", "POST /v1/api-keys/{api_key_id}/rotate", "api_keys:manage", "hosted_mutation", {
    event: "api_key.rotate_requested",
    resourceType: "api_key",
    requiresHostedAuth: true
  }),
  operation("invite_teammate", "POST /v1/team/invites", "team:manage", "hosted_mutation", {
    event: "team.invite_requested",
    resourceType: "team_invite",
    requiresHostedAuth: true
  }),
  operation("publish_trust_report", "POST /v1/trust/reports/publish", "trust:publish", "hosted_mutation", {
    event: "trust.publish_requested",
    resourceType: "trust_report",
    requiresHostedAuth: true
  })
];

export function buildA3AuthContext(input = {}, options = {}) {
  const tenantScope = buildA3TenantScope(input.tenant_scope || input.tenantScope || input, options);
  const role = normalizeRole(firstPresent(
    input.role,
    input.actor_role,
    input.actorRole,
    options.role,
    "developer"
  ));
  const rawActor = firstPresent(input.actor_id, input.actorId, options.actorId, "actor-local");
  const actorHash = input.actor_hash || input.actorHash || stableHash(rawActor);
  const authState = input.hosted_session === true || input.hostedSession === true
    ? "hosted_session"
    : input.service_account === true || input.serviceAccount === true
      ? "service_account"
      : "local_dev_context";

  return {
    schema_version: A3_AUTH_CONTEXT_SCHEMA_VERSION,
    auth_state: authState,
    actor_id: safeActorAlias(rawActor),
    actor_hash: actorHash,
    role,
    permissions: [...A3_RBAC_ROLES[role]].sort(),
    tenant_scope: tenantScope,
    credential_source: input.credential_source || input.credentialSource || options.credentialSource || "local_header_or_query",
    hosted_auth_required_before_live_saas: true,
    current_enforcement: authState === "hosted_session" ? "hosted_session_observed" : "local_contract_only",
    a1_dependency: "A1 must provide hosted auth middleware, session validation, service-account validation, and durable RBAC enforcement.",
    a2_dependency: "A2 must verify security, release-policy, redaction, and abuse cases that depend on role or approval state.",
    safety: {
      raw_actor_identity_exposed: false,
      raw_email_allowed: false,
      raw_token_allowed: false,
      raw_cookie_allowed: false,
      raw_api_key_allowed: false,
      stores_secret_values: false
    }
  };
}

export function buildA3RbacPolicy(options = {}) {
  const operations = A3_AUTHZ_OPERATION_POLICIES.map((policy) => ({
    ...policy,
    roles_allowed: rolesForPermission(policy.required_permission),
    live_saas_requires_a1_auth: policy.mode === "hosted_mutation" || options.hostedAuthRequired === true,
    denied_state_required: true
  }));
  return {
    schema_version: A3_RBAC_POLICY_SCHEMA_VERSION,
    policy_id: options.policyId || "a3_rbac_policy_2026_07_09",
    generated_at: options.generatedAt || "2026-07-09T00:00:00.000Z",
    enforcement_state: "contract_ready_not_hosted_enforced",
    role_count: Object.keys(A3_RBAC_ROLES).length,
    operation_count: operations.length,
    roles: Object.entries(A3_RBAC_ROLES).map(([role, permissions]) => ({
      role,
      permissions: [...permissions].sort(),
      permission_count: permissions.length
    })),
    operations,
    tenant_scope_required: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"],
    usage_meter: "api_requests",
    audit_event_contract: "ashr.event_envelope.v1",
    safety: {
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      real_cloud_mutations_enabled: false,
      denied_responses_must_be_sanitized: true
    }
  };
}

export function authorizeA3Operation(operationId, contextInput = {}, options = {}) {
  const authContext = contextInput.schema_version === A3_AUTH_CONTEXT_SCHEMA_VERSION
    ? contextInput
    : buildA3AuthContext(contextInput, options);
  const policy = findOperationPolicy(operationId);
  if (!policy) {
    return authzDecision({
      operationId,
      authContext,
      policy: unknownPolicy(operationId),
      allowed: false,
      decision: "denied_unknown_operation",
      reason: "Operation is not in the A3 RBAC boundary contract."
    }, options);
  }

  const hasPermission = authContext.permissions.includes(policy.required_permission);
  const hostedMutationBlocked = policy.mode === "hosted_mutation" && authContext.auth_state !== "hosted_session";
  const allowed = hasPermission && !hostedMutationBlocked;
  const decision = !hasPermission
    ? "denied_missing_permission"
    : hostedMutationBlocked
      ? "blocked_requires_hosted_auth"
      : policy.mode === "plan_only"
        ? "allowed_plan_only"
        : policy.mode === "local_write"
          ? "allowed_local_write"
          : "allowed_read_only";
  const reason = !hasPermission
    ? `${authContext.role} lacks ${policy.required_permission}.`
    : hostedMutationBlocked
      ? "Live cloud mutation requires A1 hosted auth, server-side RBAC, and audit persistence."
      : "A3 local boundary allows this operation within the documented mode.";

  return authzDecision({
    operationId: policy.operation,
    authContext,
    policy,
    allowed,
    decision,
    reason
  }, options);
}

export function validateA3AuthBoundary(value = {}) {
  const serialized = JSON.stringify(value);
  const errors = [];
  if (serialized.match(/Bearer\s+[A-Za-z0-9._-]+|Cookie:|ASHR_API_KEY\s*=|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i)) {
    errors.push("auth boundary contains sensitive-looking material");
  }
  if (value.schema_version === A3_AUTH_CONTEXT_SCHEMA_VERSION) {
    if (!value.actor_hash || value.safety?.raw_actor_identity_exposed !== false) {
      errors.push("auth context must use actor_hash and hide raw identity");
    }
  }
  if (value.schema_version === A3_RBAC_POLICY_SCHEMA_VERSION) {
    if (!Array.isArray(value.operations) || !value.operations.length) {
      errors.push("rbac policy must contain operations");
    }
  }
  if (value.schema_version === A3_AUTHZ_DECISION_SCHEMA_VERSION) {
    if (!value.audit_event || !validateMetadataOnlyEventEnvelope(value.audit_event).valid) {
      errors.push("authz decision must include a valid metadata-only audit event");
    }
  }
  return { valid: errors.length === 0, errors };
}

function operation(operationName, route, requiredPermission, mode, options = {}) {
  return {
    operation: operationName,
    route,
    required_permission: requiredPermission,
    mode,
    surface: options.surface || "product_console",
    audit_event_type: options.event,
    resource_type: options.resourceType,
    requires_hosted_auth: options.requiresHostedAuth === true,
    usage_meters: ["api_requests"],
    a1_dependencies: options.a1 || ["tenant/auth/API gateway", "audit events", "usage ledger"],
    a2_dependencies: options.a2 || ["security verification", "redaction policy"]
  };
}

function authzDecision(input, options = {}) {
  const tenantScope = input.authContext.tenant_scope || buildA3TenantScope({}, options);
  const auditEvent = buildMetadataOnlyEventEnvelope({
    eventType: input.policy.audit_event_type || "authz.checked",
    resourceType: input.policy.resource_type || "authz_decision",
    resourceId: input.operationId,
    tenantScope,
    actorId: input.authContext.actor_hash,
    requestId: options.requestId || "req-a3-authz",
    traceId: options.traceId || "trace-a3-authz",
    payload: {
      schema_version: A3_AUTHZ_DECISION_SCHEMA_VERSION,
      operation: input.operationId,
      role: input.authContext.role,
      decision: input.decision,
      allowed: input.allowed,
      required_permission: input.policy.required_permission
    }
  });

  return {
    schema_version: A3_AUTHZ_DECISION_SCHEMA_VERSION,
    operation: input.operationId,
    allowed: input.allowed,
    decision: input.decision,
    reason: input.reason,
    mode: input.policy.mode,
    required_permission: input.policy.required_permission,
    role: input.authContext.role,
    tenant_scope: tenantScope,
    actor_hash: input.authContext.actor_hash,
    audit_event: auditEvent,
    denied_state: input.allowed
      ? null
      : {
          http_status: input.decision === "blocked_requires_hosted_auth" ? 403 : 403,
          body_policy: "sanitized_error_without_private_evidence",
          customer_message: input.decision === "blocked_requires_hosted_auth"
            ? "This action requires hosted auth and server-side RBAC."
            : "This role is not allowed to perform the requested action."
        },
    safety: {
      raw_actor_identity_exposed: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_api_key_values_allowed: false,
      real_cloud_mutation_performed: false
    }
  };
}

function rolesForPermission(permission) {
  return Object.entries(A3_RBAC_ROLES)
    .filter(([, permissions]) => permissions.includes(permission))
    .map(([role]) => role)
    .sort();
}

function findOperationPolicy(operationId) {
  return A3_AUTHZ_OPERATION_POLICIES.find((policy) => (
    policy.operation === operationId
    || policy.route === operationId
    || policy.route.replace(/:[A-Za-z]+/g, "{id}") === operationId
  ));
}

function unknownPolicy(operationId) {
  return {
    operation: operationId,
    route: "unknown",
    required_permission: "unknown",
    mode: "unknown",
    audit_event_type: "authz.unknown_operation",
    resource_type: "authz_decision"
  };
}

function normalizeRole(role) {
  const value = String(role || "developer").toLowerCase().replaceAll(/[^a-z0-9_]+/g, "_");
  return A3_RBAC_ROLES[value] ? value : "developer";
}

function safeActorAlias(rawActor) {
  const value = String(rawActor || "");
  if (!value || value.match(/@|Bearer|Cookie|token|key/i)) {
    return "actor_[REDACTED]";
  }
  return value.replaceAll(/[^a-zA-Z0-9_.:-]/g, "_").slice(0, 80) || "actor_[REDACTED]";
}

function stableHash(value) {
  return `actor_${stableHexDigest(value || "actor-local").slice(0, 24)}`;
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function buildMetadataOnlyEventEnvelope(input = {}) {
  const tenantScope = buildA3TenantScope(input.tenantScope || input.tenant_scope || {});
  const payload = sanitizeForHash(input.payload || {});
  const payloadHash = stableHexDigest(stableJson(payload));
  const eventSeed = stableJson({
    event_type: input.eventType,
    resource_type: input.resourceType,
    resource_id: input.resourceId,
    actor_id: input.actorId,
    request_id: input.requestId,
    trace_id: input.traceId,
    payload_hash: payloadHash,
    tenant_scope: tenantScope
  });

  return {
    schema_version: "ashr.event_envelope.v1",
    event_id: `evt_${stableHexDigest(eventSeed).slice(0, 16)}`,
    event_type: input.eventType || "authz.checked",
    organization_id: tenantScope.organization_id,
    tenant_id: tenantScope.tenant_id,
    workspace_id: tenantScope.workspace_id,
    project_id: tenantScope.project_id,
    environment_id: tenantScope.environment_id,
    actor_id: input.actorId || "actor_[REDACTED_HASH]",
    request_id: input.requestId || "req-a3-authz",
    trace_id: input.traceId || "trace-a3-authz",
    resource_type: input.resourceType || "authz_decision",
    resource_id: input.resourceId || "unknown",
    created_at: input.createdAt || "2026-07-09T00:00:00.000Z",
    payload_ref: null,
    payload_hash: payloadHash,
    redaction_status: "metadata_only",
    payload_inline: false,
    payload_schema_version: payload.schema_version || null,
    usage_meter: "api_requests",
    audit_visibility: "metadata_only",
    safety: {
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_signed_urls_allowed: false
    }
  };
}

function validateMetadataOnlyEventEnvelope(event = {}) {
  const errors = [];
  for (const field of [
    "event_id",
    "event_type",
    "schema_version",
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "actor_id",
    "request_id",
    "trace_id",
    "resource_type",
    "resource_id",
    "created_at",
    "payload_hash",
    "redaction_status"
  ]) {
    if (!event[field]) {
      errors.push(`${field} is required`);
    }
  }
  if (event.schema_version !== "ashr.event_envelope.v1") {
    errors.push("schema_version must be ashr.event_envelope.v1");
  }
  if (!/^[a-f0-9]{64}$/.test(String(event.payload_hash || ""))) {
    errors.push("payload_hash must be a 64-character hex digest");
  }
  return { valid: errors.length === 0, errors };
}

function sanitizeForHash(payload = {}) {
  return JSON.parse(JSON.stringify(payload, (key, value) => {
    if (/authorization|cookie|secret|token|password|api_key|signed_url|email/i.test(key)) {
      return "[REDACTED]";
    }
    if (typeof value === "string") {
      return value
        .replace(/\bBearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer [REDACTED]")
        .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]")
        .replace(/https:\/\/[^"\s]+X-Amz-Signature=[^"\s]+/gi, "[REDACTED_SIGNED_URL]");
    }
    return value;
  }));
}

function stableHexDigest(value) {
  const text = String(value ?? "");
  let hashA = 0x811c9dc5;
  let hashB = 0x01000193;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    hashA ^= code;
    hashA = Math.imul(hashA, 0x01000193) >>> 0;
    hashB ^= code + index;
    hashB = Math.imul(hashB, 0x85ebca6b) >>> 0;
  }
  const seed = `${hashA.toString(16).padStart(8, "0")}${hashB.toString(16).padStart(8, "0")}`;
  return seed.repeat(4).slice(0, 64);
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
