import {
  buildDashboardSummary,
  normalizeCases,
  summarizeCloudConsoleShell,
  summarizeReleaseGate,
  summarizeUsageQuota
} from "./report_builder.mjs";
import {
  authorizeA3Operation,
  buildA3AuthContext,
  buildA3RbacPolicy
} from "./a3_auth_rbac_boundary.mjs";

export const A3_SAAS_ADMIN_SCHEMA_VERSION = "a3.saas_admin_console.v1";
export const A3_SAAS_ADMIN_ACTION_REQUEST_SCHEMA_VERSION = "a3.saas_admin_action_request.v1";

export const A3_SAAS_ADMIN_ACTIONS = [
  "login_with_oauth",
  "configure_rbac",
  "switch_project",
  "create_project",
  "invite_teammate",
  "view_audit_log",
  "manage_usage_limit",
  "rotate_api_key",
  "revoke_api_key",
  "view_usage",
  "open_trust_center",
  "publish_trust_report",
  "download_audit_bundle"
];

export function buildSaasAdminConsole(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const usageQuota = inputs.usageQuota || {};
  const usageQuotaApiProbe = inputs.usageQuotaApiProbe || {};
  const authCheck = inputs.authCheck || {};
  const frontendSummary = inputs.frontendSummary || {};
  const requestProvenance = inputs.requestProvenance || {};
  const mediaSignedUrlCoverage = inputs.mediaSignedUrlCoverage || {};
  const coverage = inputs.coverage || {};
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const usage = summarizeUsageQuota(usageQuota, usageQuotaApiProbe);
  const cloudShell = summarizeCloudConsoleShell(authCheck, frontendSummary, requestProvenance, usageQuota, usageQuotaApiProbe);
  const releaseGate = summarizeReleaseGate(runFixture, gradeFixture, coverage, mediaSignedUrlCoverage);
  const organizationId = options.organizationId || inputs.organizationId || "org-local";
  const projectId = options.projectId || inputs.projectId || "project-local";
  const authContext = buildA3AuthContext({
    role: options.role || inputs.role || "developer",
    actorHash: options.actorHash || inputs.actorHash,
    organizationId,
    projectId
  });
  const rbacPolicy = buildA3RbacPolicy();
  const cloudPosture = buildCloudPostureSummary({ authCheck, frontendSummary, cloudShell, usage, releaseGate });

  return {
    schema_version: A3_SAAS_ADMIN_SCHEMA_VERSION,
    source: options.source || inputs.source || "mock",
    organization: {
      organization_id: organizationId,
      display_name: options.organizationName || "A3 Local Organization",
      plan: usage.available ? "calibrated" : "local_dev",
      tenancy_mode: "single_org_local",
      data_region: "local_only",
      auth_boundary: "mock_session_no_real_oauth"
    },
    project: {
      project_id: projectId,
      display_name: options.projectName || "A3 Release Intelligence",
      environment: "staging",
      linked_a1_runner: summary.totalRuns > 0,
      linked_a2_judge: cases.some((item) => (item.judge_results || []).length > 0 || item.grade),
      release_gate_decision: releaseGate.decision,
      release_gate_label: releaseGate.decision_label
    },
    login: buildLoginState(authCheck, frontendSummary, cloudShell),
    team: buildTeamState(releaseGate, usage),
    rbac: buildRbacState(),
    auth_boundary: {
      schema_version: "a3.saas_admin_auth_boundary.v1",
      auth_context: authContext,
      policy_id: rbacPolicy.policy_id,
      operation_count: rbacPolicy.operation_count,
      sample_decisions: [
        authorizeA3Operation("read_dashboard", authContext),
        authorizeA3Operation("share_report", authContext),
        authorizeA3Operation("rotate_api_key", authContext)
      ],
      enforcement_state: rbacPolicy.enforcement_state,
      next_step: "Replace local contract-only context with A1 hosted session and service-account middleware before enabling live SaaS mutations."
    },
    api_keys: buildApiKeyState(),
    usage: buildUsageState(summary, usage, usageQuotaApiProbe),
    billing_account: buildBillingAccountState(usage, usageQuotaApiProbe, summary),
    trust: buildTrustState(summary, releaseGate, cloudShell, usage),
    export_governance: buildExportGovernanceState(summary, releaseGate, usage),
    cloud_management: buildCloudManagementState(cloudShell, summary, releaseGate, usage),
    cloud_posture: cloudPosture,
    cloud_summary_strip: buildCloudSummaryStrip({ cloudPosture, releaseGate, usage, frontendSummary, authCheck }),
    tenant_control: buildTenantControlState(),
    rollout_control: buildRolloutControlState(releaseGate, usage),
    notification_destinations: buildNotificationDestinations(inputs.notificationControlPlane || inputs.notification_control_plane || {}),
    notification_summary: buildNotificationSummary(inputs.notificationControlPlane || inputs.notification_control_plane || {}),
    product_console_map: buildProductConsoleMap(),
    a1_a2_compatibility: buildCompatibilityState(summary, cases),
    actions: A3_SAAS_ADMIN_ACTIONS.map((action) => planSaasAdminAction(action, {
      releaseGate,
      usage,
      cloudShell,
      organizationId,
      projectId
    })),
    safety: {
      real_login_enabled: false,
      real_team_invites_enabled: false,
      real_api_key_secrets_enabled: false,
      real_billing_mutations_enabled: false,
      real_trust_publish_enabled: false,
      secret_values_allowed: false,
      mode: "clean_room_local_shell",
      note: "A3 mirrors SaaS workflow shape without mutating real Ashr cloud resources or storing secret values."
    }
  };
}

export function planSaasAdminAction(action, context = {}) {
  const releaseGate = context.releaseGate || {};
  const usage = context.usage || {};
  const cloudShell = context.cloudShell || {};
  const base = {
    schema_version: "a3.saas_admin_action_plan.v1",
    action,
    organization_id: context.organizationId || "org-local",
    project_id: context.projectId || "project-local",
    secret_values_included: false,
    writes_real_ashr_cloud: false
  };

  const plans = {
    login_with_oauth: {
      area: "login",
      mode: "mock_only",
      enabled: false,
      risk: "high",
      reason: "Real OAuth/session handling belongs outside the static A3 dashboard.",
      next_step: "Add hosted auth middleware before enabling real login."
    },
    configure_rbac: {
      area: "team",
      mode: "contract_ready",
      enabled: true,
      risk: "medium",
      reason: "RBAC roles can be modeled safely as metadata before real login is wired.",
      next_step: "Attach server-side session roles to every A3 API route before enforcing writes."
    },
    switch_project: {
      area: "cloud_management",
      mode: "read_only",
      enabled: true,
      risk: "low",
      reason: "Project switching can read scoped dashboard payloads without mutating cloud state.",
      next_step: "Bind project selector to tenant-scoped API once A1 provides real org/project auth."
    },
    create_project: {
      area: "cloud_management",
      mode: "plan_only",
      enabled: false,
      risk: "medium",
      reason: "Creating cloud projects changes tenant state and must require hosted auth, RBAC, and audit events.",
      next_step: "Keep project creation as a preview card until the organizations/projects tables are backed by real auth."
    },
    invite_teammate: {
      area: "team",
      mode: "plan_only",
      enabled: false,
      risk: "high",
      reason: "Invites send external emails and must require real auth, RBAC, and audit events.",
      next_step: "Create invite request preview and audit event first."
    },
    view_audit_log: {
      area: "trust",
      mode: "read_only",
      enabled: true,
      risk: "low",
      reason: "Audit logs can be shown as redacted metadata and are useful for reviewer confidence.",
      next_step: "Back the audit log with database rows once hosted report events are persistent."
    },
    manage_usage_limit: {
      area: "usage",
      mode: "plan_only",
      enabled: false,
      risk: "high",
      reason: "Changing quota or billing limits can affect cost and needs real tenant admin permissions.",
      next_step: "Show quota and usage read-only until billing and plan controls are implemented."
    },
    rotate_api_key: {
      area: "api_keys",
      mode: "plan_only",
      enabled: false,
      risk: "high",
      reason: "A3 can show key metadata and rotation workflow, but must never mint or reveal real secrets locally.",
      next_step: "Add server-side hashed key storage and one-time secret reveal."
    },
    revoke_api_key: {
      area: "api_keys",
      mode: "plan_only",
      enabled: false,
      risk: "medium",
      reason: "Revocation changes machine access and must be backed by A1 API-key service.",
      next_step: "Wire to A1 API-key backend after RBAC is available."
    },
    view_usage: {
      area: "usage",
      mode: usage.available ? "read_only_calibrated" : "read_only_local",
      enabled: true,
      risk: "low",
      reason: usage.available ? usage.guidance : "Usage can be estimated from local run/case counts.",
      next_step: usage.direct_api_accessible ? "Use direct API usage feed." : "Keep OAuth-gated fields as frontend-confirmed evidence."
    },
    open_trust_center: {
      area: "trust",
      mode: "preview",
      enabled: true,
      risk: "medium",
      reason: "A trust center preview can reuse redacted release-gate, report, and audit evidence without public publishing.",
      next_step: "Require signed approval before exposing any public trust page."
    },
    publish_trust_report: {
      area: "trust",
      mode: "plan_only",
      enabled: releaseGate.decision === "approve_release",
      risk: "high",
      reason: "Trust publishing needs immutable hosted reports, approval chain, and access policy.",
      next_step: releaseGate.decision === "approve_release"
        ? "Require reviewer sign-off before publishing trust page."
        : "Fix blocking release-gate evidence before trust publication."
    },
    download_audit_bundle: {
      area: "trust",
      mode: "local_export",
      enabled: true,
      risk: "medium",
      reason: "A3 can safely export redacted local audit evidence.",
      next_step: "Move bundle generation behind hosted report snapshot and audit log."
    }
  };

  return {
    ...base,
    ...(plans[action] || {
      area: "unknown",
      mode: "disabled",
      enabled: false,
      risk: "unknown",
      reason: "Unknown SaaS admin action.",
      next_step: "Add action contract before wiring UI."
    }),
    frontend_session_observed: Boolean(cloudShell.frontend_session_observed),
    created_at: context.createdAt || "runtime"
  };
}

export function buildSaasAdminActionRequest(action, context = {}) {
  const plan = context.plan || planSaasAdminAction(action, context);
  const status = classifyActionRequestStatus(plan);
  return {
    schema_version: A3_SAAS_ADMIN_ACTION_REQUEST_SCHEMA_VERSION,
    request_id: context.requestId || `aar_${String(plan.action || action || "unknown").replaceAll(/[^a-z0-9_]+/gi, "_")}`,
    action: plan.action || action,
    area: plan.area || "unknown",
    mode: plan.mode || "unknown",
    status,
    organization_id: plan.organization_id || context.organizationId || "org-local",
    project_id: plan.project_id || context.projectId || "project-local",
    actor_hash: context.actorHash || "actor_[REDACTED_HASH]",
    requested_at: context.requestedAt || plan.created_at || "runtime",
    real_cloud_mutation_performed: false,
    writes_real_ashr_cloud: plan.writes_real_ashr_cloud === true,
    secret_values_included: false,
    requires_hosted_auth: actionRequiresHostedAuth(plan),
    requires_reviewer_approval: actionRequiresReviewerApproval(plan),
    reason: plan.reason || "No action reason supplied.",
    next_step: plan.next_step || "Review the action plan before enabling this workflow.",
    plan,
    safety: {
      no_real_ashr_write: true,
      raw_api_key_values_allowed: false,
      raw_email_values_allowed: false,
      raw_token_values_allowed: false,
      redacted_identity_only: true
    }
  };
}

export function summarizeSaasAdminActionRequests(requests = []) {
  const items = Array.isArray(requests) ? requests : [];
  const pending = items.filter((item) => item.status === "recorded_plan_only" || item.status === "blocked_requires_backend").length;
  const readOnly = items.filter((item) => item.status === "recorded_read_only").length;
  const blocked = items.filter((item) => item.status === "blocked_real_cloud_mutation" || item.status === "blocked_requires_backend").length;
  return {
    schema_version: "a3.saas_admin_action_request_summary.v1",
    request_count: items.length,
    pending_count: pending,
    read_only_count: readOnly,
    blocked_count: blocked,
    latest_request_id: items[items.length - 1]?.request_id || null,
    real_cloud_mutations_performed: false,
    secret_values_included: false
  };
}

function classifyActionRequestStatus(plan = {}) {
  if (plan.writes_real_ashr_cloud) {
    return "blocked_real_cloud_mutation";
  }
  if (plan.mode === "plan_only" || plan.enabled === false) {
    return "recorded_plan_only";
  }
  if (plan.mode === "mock_only") {
    return "blocked_requires_backend";
  }
  return "recorded_read_only";
}

function actionRequiresHostedAuth(plan = {}) {
  return ["login", "team", "api_keys", "usage", "trust", "cloud_management"].includes(plan.area)
    && !["read_only", "read_only_calibrated", "read_only_local", "local_export", "contract_ready"].includes(plan.mode);
}

function actionRequiresReviewerApproval(plan = {}) {
  return plan.area === "trust"
    || plan.action === "publish_trust_report"
    || plan.action === "download_audit_bundle"
    || plan.risk === "high";
}

function buildCloudSummaryStrip({ cloudPosture = {}, releaseGate = {}, usage = {}, frontendSummary = {}, authCheck = {} } = {}) {
  const observedFrontend = Boolean(Object.keys(frontendSummary || {}).length);
  const observedAuth = Boolean(Object.keys(authCheck || {}).length);
  return {
    schema_version: "a3.cloud_summary_strip.v1",
    headline: releaseGate.decision === "approve_release" ? "ready_for_governed_publish" : "review_before_publish",
    tiles: [
      {
        label: "Auth",
        value: cloudPosture.hosted_auth_state || "unknown",
        tone: observedAuth ? "pass" : "warn"
      },
      {
        label: "Tenant",
        value: cloudPosture.tenant_scope_state || "unknown",
        tone: cloudPosture.tenant_scope_state === "organization_project_visible" ? "pass" : "warn"
      },
      {
        label: "Usage",
        value: usage.available ? (usage.overage_risk || "calibrated") : "local_projection_only",
        tone: usage.overage_risk === "over_quota" ? "fail" : usage.overage_risk === "near_quota" ? "warn" : "pass"
      },
      {
        label: "Frontend",
        value: observedFrontend ? "observed" : "fixture_only",
        tone: observedFrontend ? "pass" : "neutral"
      },
      {
        label: "Trust",
        value: cloudPosture.trust_publish_state || "unknown",
        tone: releaseGate.decision === "approve_release" ? "pass" : "warn"
      }
    ],
    next_operator_moves: [
      "Keep hosted auth and tenant scope visible before enabling mutation-backed admin actions.",
      "Treat trust publish as gated by reviewer evidence and report governance, not a standalone button.",
      "Escalate usage overage or quota warning inside the same cloud summary strip buyers and operators see first."
    ]
  };
}

function buildCloudPostureSummary({ authCheck = {}, frontendSummary = {}, cloudShell = {}, usage = {}, releaseGate = {} } = {}) {
  return {
    schema_version: "a3.cloud_posture_summary.v1",
    hosted_auth_state: cloudShell.frontend_session_observed || cloudShell.auth_observed ? "observed_read_only" : "local_mock_only",
    tenant_scope_state: "organization_project_visible",
    usage_state: usage.available ? "calibrated_read_only" : "local_projection_only",
    trust_publish_state: releaseGate.decision === "approve_release" ? "approval_required_before_publish" : "blocked_by_release_gate",
    api_key_state: "metadata_only_no_secret_reveal",
    cloud_admin_state: "read_only_control_surface",
    why_it_matters: "Commercial customers expect cloud posture to describe auth, tenant scope, usage, trust, and API-key safety in one place."
  };
}

function buildLoginState(authCheck = {}, frontendSummary = {}, cloudShell = {}) {
  const observed = Boolean(
    cloudShell.auth_observed
    || cloudShell.frontend_session_observed
    || Object.keys(authCheck || {}).length
    || Object.keys(frontendSummary || {}).length
  );
  return {
    status: observed ? "observed_read_only" : "local_mock",
    provider: "google_oauth_observed",
    session_storage: "not_persisted",
    user_identity: "[REDACTED]",
    session: {
      status: observed ? "manual_login_observed" : "mock_session",
      cookie_storage: "not_read_or_saved",
      token_storage: "not_read_or_saved",
      expires_at: "unknown",
      account_email: "[REDACTED]"
    },
    rbac_boundary: {
      enforced_now: false,
      required_claims: ["organization_id", "project_id", "role"],
      dashboard_policy: "read_only_or_plan_only_until_hosted_auth"
    },
    supported_modes: ["manual_oauth_observation", "api_key_env_probe", "local_mock"],
    required_before_real_saas: ["hosted auth callback", "session cookie policy", "RBAC middleware", "audit login events"]
  };
}

function buildTeamState(releaseGate = {}, usage = {}) {
  const blocked = releaseGate.decision === "block_release";
  const seatsPurchased = usage.available ? 12 : 5;
  const members = [
    { member_id: "mem_owner", display_name: "Owner", role: "owner", status: "active", redacted: true, seat_state: "billable" },
    { member_id: "mem_reviewer", display_name: "Release reviewer", role: "reviewer", status: blocked ? "required" : "active", redacted: true, seat_state: "billable" },
    { member_id: "mem_developer", display_name: "Developer", role: "developer", status: "active", redacted: true, seat_state: "billable" },
    { member_id: "mem_auditor", display_name: "Auditor", role: "auditor", status: "available", redacted: true, seat_state: "free_audit" }
  ];
  const billableSeats = members.filter((item) => item.seat_state === "billable").length;
  return {
    status: "mock_roster",
    invite_mode: "disabled_until_auth",
    roles: ["owner", "admin", "developer", "reviewer", "auditor", "billing_admin"],
    members,
    seat_management: {
      purchased_seats: seatsPurchased,
      assigned_billable_seats: billableSeats,
      free_audit_seats: members.filter((item) => item.seat_state === "free_audit").length,
      pending_invites: blocked ? 1 : 0,
      overage_risk: billableSeats >= seatsPurchased ? "seat_limit_reached" : billableSeats >= Math.max(seatsPurchased - 1, 1) ? "seat_limit_near" : "healthy",
      why_it_matters: "Commercial buyers expect team invites, reviewer routing, and billing seats to agree before they trust release approvals."
    },
    approval_policy: {
      required_for_blocked_release: blocked,
      required_roles: blocked ? ["reviewer", "owner"] : ["reviewer"],
      self_approval_allowed: false
    },
    invite_workflow: [
      { step: "enter_email", status: "blocked", reason: "Email is private user data and is not stored in A3 fixtures." },
      { step: "choose_role", status: "preview", reason: "Role metadata is safe to model locally." },
      { step: "assign_seat", status: "preview", reason: "Every invited operator should consume an approved billable or audit seat." },
      { step: "send_invite", status: "disabled", reason: "Sending email is a real cloud mutation." },
      { step: "audit_event", status: "required", reason: "Every invite must write a tenant-scoped audit event." }
    ]
  };
}

function buildRbacState() {
  return {
    status: "contract_ready",
    default_role: "developer",
    permission_matrix: [
      role("owner", ["read_all", "manage_team", "manage_billing", "rotate_keys", "publish_trust", "approve_release"]),
      role("admin", ["read_all", "manage_team", "rotate_keys", "approve_release"]),
      role("developer", ["read_runs", "import_a1", "import_a2", "create_reports"]),
      role("reviewer", ["read_runs", "review_failures", "approve_release", "request_waiver"]),
      role("auditor", ["read_reports", "download_audit_bundle", "view_audit_log"]),
      role("billing_admin", ["read_usage", "manage_usage_limit"])
    ],
    enforcement_points: [
      "POST /api/a3/import/a1-run-result",
      "POST /api/a3/import/a2-grade-result",
      "POST /api/a3/reports/share",
      "POST /api/a3/reports/:reportId/revoke",
      "POST /api/a3/admin/actions/plan"
    ],
    current_enforcement: "documented_not_enforced_without_hosted_auth",
    high_risk_permissions: [
      "release:approve",
      "api_keys:manage",
      "team:manage",
      "billing:read",
      "trust:publish"
    ],
    separation_of_duties: [
      {
        lane: "release_governance",
        requirement: "Blocked release should involve reviewer plus owner or delegate before sign-off.",
        buyer_value: "Reduces one-person risky release approval."
      },
      {
        lane: "api_key_hygiene",
        requirement: "Key rotation and scope changes must emit audit events and avoid self-approval.",
        buyer_value: "Supports enterprise secret hygiene review."
      },
      {
        lane: "billing_and_procurement",
        requirement: "Billing viewers should read invoices without gaining release approval or key rotation rights.",
        buyer_value: "Matches finance and engineering separation in real companies."
      }
    ]
  };
}

function buildTenantControlState() {
  return {
    status: "contract_visible",
    tenancy_model: "organization -> workspace -> project -> environment",
    default_environment: "staging",
    environment_switcher: {
      enabled: true,
      mode: "read_only_shell",
      guardrail: "A3 reads tenant scope and environment labels without mutating hosted deployment targets."
    },
    workspace_inventory: [
      {
        workspace_id: "workspace-local",
        label: "Release Intelligence Workspace",
        environment_count: 3,
        status: "active",
        posture: "single_workspace_demo_with_multi_env_contract"
      },
      {
        workspace_id: "workspace-audit",
        label: "Audit Replica Workspace",
        environment_count: 2,
        status: "planned",
        posture: "customer_visible_shell_for_multi_workspace_story"
      }
    ],
    environment_policies: [
      {
        environment: "dev",
        release_policy: "developer experimentation",
        approval_rule: "no external sharing without reviewer evidence"
      },
      {
        environment: "staging",
        release_policy: "candidate release validation",
        approval_rule: "review workflow and report share governance required"
      },
      {
        environment: "production",
        release_policy: "sign-off only",
        approval_rule: "approval plus audit packet and readback evidence required"
      }
    ],
    tenant_boundaries: [
      "Every report, approval, and admin action is tenant-scoped.",
      "Workspace and project labels must remain visible in export and audit surfaces.",
      "Environment selection should change readback and publish context before any future live mutation."
    ]
  };
}

function buildWorkspacePosture(summary = {}, releaseGate = {}, usage = {}) {
  return {
    schema_version: "a3.workspace_posture.v1",
    status: "cloud_shell_visible",
    tenant_scope_state: "visible",
    project_state: summary.totalRuns > 0 ? "instrumented_demo_project" : "empty_project",
    environment_state: releaseGate.decision === "block_release" ? "staging_requires_signoff" : "staging_reviewable",
    usage_state: usage.available ? "usage_surface_visible" : "local_projection_only",
    operator_story: [
      "Ops can see which workspace and environment a report belongs to.",
      "Reviewers can see whether a release is blocked before hosted sharing.",
      "Finance and audit viewers can inspect usage and report lifecycle without key or trace secret exposure."
    ],
    next_capabilities: [
      "Persist tenant-scoped workspace selection in hosted session state.",
      "Expose environment-specific publish readiness and rollback packet links.",
      "Join workspace posture with billable seat usage and audit export presets."
    ]
  };
}

function buildApiKeyState() {
  return {
    status: "metadata_only",
    create_mode: "server_required",
    reveal_policy: "one_time_secret_only_never_in_dashboard_fixture",
    hygiene_status: "rotation_and_scope_review_required_before_live_cloud_mutations",
    rotation_slo_days: 30,
    leaked_key_detection: "prefix_and_audit_only",
    lifecycle: [
      { step: "create", status: "planned", safety: "server generates secret and returns it once" },
      { step: "store", status: "planned", safety: "store hash and prefix only" },
      { step: "rotate", status: "plan_only", safety: "requires admin role and audit event" },
      { step: "revoke", status: "plan_only", safety: "requires admin role and audit event" },
      { step: "verify_scope", status: "preview", safety: "keys should be least-privilege before PR publish or hosted sharing" }
    ],
    keys: [
      {
        key_id: "key_ci_ingest",
        name: "CI ingest key",
        prefix: "ashr_ci_[REDACTED]",
        scopes: ["runs:write", "traces:write", "reports:read"],
        last_used_at: "redacted",
        status: "planned",
        owner_role: "developer",
        rotation_state: "due_soon"
      },
      {
        key_id: "key_report_read",
        name: "Report read key",
        prefix: "ashr_rpt_[REDACTED]",
        scopes: ["reports:read", "release_gates:read"],
        last_used_at: "redacted",
        status: "planned",
        owner_role: "reviewer",
        rotation_state: "healthy"
      }
    ],
    audit_requirements: [
      "api_key_created",
      "api_key_rotated",
      "api_key_revoked",
      "api_key_scope_verified"
    ],
    guardrails: [
      "Only prefixes and hashes may be stored.",
      "Secret value is shown once by server-side API only.",
      "A3 fixtures and reports must never contain real API key values."
    ]
  };
}

function buildUsageState(summary, usage, usageApiProbe = {}) {
  const apiProbeCalls = usageApiProbe.calls || usageApiProbe.probes || {};
  return {
    status: usage.available ? "frontend_calibrated" : "local_estimate",
    channels: usage.channels,
    frontend_modules: usage.frontend_modules,
    direct_api_accessible: usage.direct_api_accessible,
    oauth_only_functions: usage.oauth_only_functions,
    local_meter: {
      run_count: summary.totalRuns,
      case_count: summary.totalCases,
      failed_case_count: summary.failed,
      media_case_count: summary.mediaEvidenceCases
    },
    plan_snapshot: {
      plan_name: usage.available ? "ashr_calibrated_unknown_plan" : "local_dev",
      billing_status: "read_only",
      quota_mutations_enabled: false,
      recommended_meters: ["runs", "cases", "trace_events", "judge_results", "media_evidence_cases", "shareable_reports"],
      overage_posture: summary.failed > 0 ? "watch_failed_case_spike" : "healthy_usage_mix"
    },
    budget_controls: [
      { control: "daily_run_limit", status: "preview_only", mutation_enabled: false },
      { control: "media_storage_limit", status: "preview_only", mutation_enabled: false },
      { control: "report_view_limit", status: "preview_only", mutation_enabled: false }
    ],
    api_probe_status: Object.fromEntries(Object.entries(apiProbeCalls).map(([name, value]) => [
      name,
      value?.status || value?.error?.status || "unknown"
    ])),
    billing_mutations_enabled: false
  };
}

function buildBillingAccountState(usage = {}, usageApiProbe = {}, summary = {}) {
  const billableMeters = Array.isArray(usage.billable_meters) ? usage.billable_meters : [];
  return {
    schema_version: "a3.billing_account_state.v1",
    status: usage.available ? "read_only_calibrated" : "local_projection_only",
    plan_name: usage.plan_name || usage.plan?.name || "local_dev",
    quota_window: usage.quota_window || "monthly",
    billable_meter_count: billableMeters.length,
    invoice_preview_state: usage.direct_api_accessible ? "api_read_visible" : "fixture_projection_only",
    overage_risk: usage.overage_risk || "unknown",
    plan_comparison: [
      { tier: "Starter", positioning: "local evidence and export-only reports", fit: "solo / internal evaluation" },
      { tier: "Team", positioning: "reviewer workflow, hosted report lifecycle, and domestic payment onboarding", fit: "shared release review" },
      { tier: "Enterprise", positioning: "tenant controls, self-host packet, audit exports, sign-off evidence, and China-first billing readiness", fit: "regulated orgs" }
    ],
    provider_priority: [
      {
        provider: "wechat_pay",
        priority: "primary",
        market: "CN",
        readiness: "contract_first",
        settlement: "wallet and QR native",
        why_now: "Best fit for China-first buyer onboarding and familiar enterprise reimbursement flows."
      },
      {
        provider: "alipay",
        priority: "primary",
        market: "CN",
        readiness: "contract_first",
        settlement: "consumer and enterprise balance payments",
        why_now: "Strong domestic procurement path and common acceptance for software payments."
      },
      {
        provider: "manual_invoice",
        priority: "fallback",
        market: "CN + global enterprise",
        readiness: "workflow_shell",
        settlement: "bank transfer after invoice approval",
        why_now: "Needed for enterprise buyers who cannot pay by card or wallet at purchase time."
      },
      {
        provider: "stripe",
        priority: "secondary",
        market: "global",
        readiness: "public_reference_only",
        settlement: "card and international billing",
        why_now: "Useful later for international customers, but not the primary student-team commercial path."
      }
    ],
    invoice_workflow: [
      {
        step: "billing_contact_submit",
        owner: "buyer",
        status: "shell_ready",
        detail: "Billing contact, tax title, invoice header, and procurement notes captured before enabling real payment mutation."
      },
      {
        step: "finance_review",
        owner: "vendor_ops",
        status: "shell_ready",
        detail: "A3 can show pending, approved, or blocked invoice state without mutating any real provider."
      },
      {
        step: "provider_or_transfer",
        owner: "billing_system",
        status: "planned",
        detail: "Future path chooses WeChat Pay, Alipay, or manual transfer based on procurement policy and customer region."
      },
      {
        step: "receipt_and_audit",
        owner: "a3_console",
        status: "copy_now",
        detail: "Hosted reports, audit exports, and release evidence can reference invoice state without exposing secrets."
      }
    ],
    invoice_preview: buildInvoicePreview(billableMeters),
    packaging: [
      "Starter: local evidence and export-only reports.",
      "Team: reviewer workflow, hosted report lifecycle, and WeChat Pay / Alipay-ready billing shell.",
      "Enterprise: tenant controls, self-host packet, audit exports, sign-off evidence, and China-first billing posture."
    ],
    next_actions: [
      "Attach durable billing account rows when A1 exposes them.",
      "Keep invoice preview read-only until hosted auth and provider webhooks exist.",
      "Prioritize WeChat Pay and Alipay provider contracts before secondary international payment providers."
    ],
    source_fields: Object.keys(usageApiProbe || {}).slice(0, 8)
  };
}

function buildInvoicePreview(billableMeters = []) {
  return {
    currency: "CNY",
    interval: "monthly",
    line_items: billableMeters.slice(0, 6).map((meter) => ({
      meter: meter.meter,
      quantity: meter.quantity || 0,
      unit_price_label: meter.meter === "shareable_reports" ? "CNY 14 / report" : meter.meter === "report_views" ? "CNY 0.15 / view" : "CNY 7 / unit",
      subtotal_label: meter.meter === "shareable_reports"
        ? "CNY " + (Number(meter.quantity || 0) * 14).toFixed(2)
        : meter.meter === "report_views"
          ? "CNY " + (Number(meter.quantity || 0) * 0.15).toFixed(2)
          : "CNY " + (Number(meter.quantity || 0) * 7).toFixed(2)
    }))
  };
}

function buildExportGovernanceState(summary = {}, releaseGate = {}, usage = {}) {
  const releaseApproved = releaseGate.decision === "approve_release";
  return {
    schema_version: "a3.export_governance_state.v1",
    status: releaseApproved ? "reviewer_and_exec_packets_ready_for_review" : "waiting_for_release_gate",
    shareable_reports_ready: summary.totalCases > 0,
    allowed_audiences: ["internal_ops", "reviewer_signoff", ...(releaseApproved ? ["executive_summary"] : [])],
    blocked_audiences: ["customer_external"],
    customer_external_blocked: true,
    packet_readiness: [
      { packet: "reviewer_signoff", status: summary.totalCases > 0 ? "copy_now" : "missing_cases", why: "Reviewer packet can carry trace, tool-call, failure, and audit evidence." },
      { packet: "executive_summary", status: releaseApproved ? "copy_now" : "blocked_by_release_gate", why: "Executive packet should only appear after release evidence is coherent enough for sign-off." },
      { packet: "customer_external", status: "blocked", why: "Customer-safe export needs explicit trust workflow, redaction proof, and revocable hosted audit path." }
    ],
    required_controls: [
      "tenant-scoped hosted reports",
      "reviewer approval or waiver receipt",
      "release evidence summary",
      "audit-visible share-link lifecycle",
      "redaction firewall proof"
    ],
    commercial_value: [
      "Gives operators a safe reviewer packet without leaking raw trace or secrets.",
      "Lets leadership read executive status without granting tool-level evidence access.",
      "Prevents premature customer-facing export claims before trust controls exist."
    ],
    billing_alignment: {
      primary_region: "CN-first",
      invoice_mode: usage.available ? "metered_preview" : "local_preview",
      ties_to_usage: true
    }
  };
}

function buildTrustState(summary, releaseGate = {}, cloudShell = {}, usage = {}) {
  const publishable = releaseGate.decision === "approve_release" && summary.totalCases > 0;
  return {
    status: publishable ? "ready_for_review" : "not_publishable",
    public_certificate_mode: "preview_only",
    publish_enabled: false,
    release_gate_decision: releaseGate.decision,
    release_gate_label: releaseGate.decision_label,
    frontend_trust_observed: cloudShell.observed_pages?.includes("Trust") || false,
    trust_center: {
      preview_enabled: true,
      public_publish_enabled: false,
      artifacts: [
        { artifact: "release_gate_summary", status: releaseGate.decision || "unknown" },
        { artifact: "redacted_shareable_report", status: "available_after_export_firewall" },
        { artifact: "audit_bundle", status: "local_export" },
        { artifact: "a1_trace_evidence", status: summary.traceCompleteness > 0 ? "available" : "missing" },
        { artifact: "a2_judge_evidence", status: summary.totalCases > 0 ? "available" : "missing" }
      ]
    },
    audit_log_policy: {
      tenant_scoped: true,
      redacted_payload_only: true,
      required_events: ["login", "import", "share_report", "view_report", "revoke_report", "approval", "api_key_rotation"]
    },
    evidence_required: [
      "passing release gate",
      "redacted hosted report",
      "reviewer approval",
      "audit bundle hash",
      "A1 trace evidence",
      "A2 judge evidence"
    ],
    compliance_posture: {
      audit_export_ready: true,
      customer_visible_publish_blocked: true,
      soc2_surface: "evidence_only_preview",
      retention_policy: usage.available ? "metered_retention_preview" : "local_retention_preview"
    },
    publish_blockers: [
      "reviewer approval receipt",
      "customer-safe redaction proof",
      "revocable hosted public audit trail",
      "hosted trust publishing service"
    ],
    customer_safe_artifacts: [
      "release_gate_summary",
      "executive_summary_packet",
      "redacted_shareable_report",
      "audit_bundle_hash"
    ],
    blocked_reason: publishable ? "Requires real hosted trust publishing service." : "Release gate is not approved."
  };
}

function buildCloudManagementState(cloudShell = {}, summary = {}, releaseGate = {}, usage = {}) {
  return {
    status: cloudShell.available ? "frontend_confirmed_shell" : "local_mock_shell",
    observed_pages: cloudShell.observed_pages || [],
    sections: cloudShell.sections || [],
    real_mutations_enabled: false,
    supported_readonly_surfaces: ["projects", "runs", "cases", "reports", "usage", "trust"],
    disabled_mutations: ["create_project", "create_api_key", "revoke_api_key", "invite_teammate", "change_billing", "publish_trust_certificate"],
    resources: [
      cloudResource("organization", "org-local", "local tenant shell", "read_only"),
      cloudResource("project", "project-local", `${summary.totalRuns || 0} run(s), ${summary.totalCases || 0} case(s)`, "read_only"),
      cloudResource("release_gate", releaseGate.decision || "unknown", releaseGate.decision_label || "not evaluated", "read_only"),
      cloudResource("report_center", "local", "shareable report metadata and manifests", "read_only")
    ],
    project_switcher: {
      enabled: true,
      current_project_id: "project-local",
      tenant_isolation_required: true,
      mutation_mode: "read_only"
    },
    workspace_posture: buildWorkspacePosture(summary, releaseGate, usage),
    audit_controls: {
      enabled: true,
      storage_target: "audit_events table",
      redaction_required: true,
      sampled_events: ["report_share_link_viewed", "report_view", "report_revoke", "api_import"]
    }
  };
}

function buildNotificationDestinations(controlPlane = {}) {
  const channels = Array.isArray(controlPlane.channels) ? controlPlane.channels : [];
  return channels.slice(0, 6).map((channel) => ({
    label: channel.label || channel.provider || "notification",
    provider: channel.provider || "unknown",
    status: channel.status || "unknown",
    current_mode: channel.current_mode || "planned",
    secret_ref_present: channel.secret_ref_present === true,
    next_action: channel.next_action || "No next action loaded."
  }));
}

function buildNotificationSummary(controlPlane = {}) {
  const summary = controlPlane.summary || {};
  const channels = Array.isArray(controlPlane.channels) ? controlPlane.channels : [];
  return {
    channel_count: summary.channel_count || channels.length || 0,
    configured_count: summary.configured_metadata_count || 0,
    secret_ref_count: channels.filter((channel) => channel.secret_ref_present === true).length,
    live_send_enabled: summary.live_mutation_count > 0
  };
}


function buildRolloutControlState(releaseGate = {}, usage = {}) {
  return {
    schema_version: "a3.rollout_control_state.v1",
    signoff_state: releaseGate.decision || "unknown",
    rollout_mode: releaseGate.decision === "approve_release" ? "ready_for_controlled_rollout" : "blocked_until_evidence_complete",
    quota_state: usage.available ? "metered_read_only" : "local_projection_only",
    rollback_surface: "incident_replay_and_report_center",
    required_before_live: [
      "reviewer approval or waiver record",
      "hosted report manifest",
      "release evidence readback",
      "usage and quota visibility"
    ]
  };
}

function buildProductConsoleMap() {
  return [
    consolePage("Login", "Manual OAuth observation and future hosted session state.", "copy_as_shell"),
    consolePage("Team", "Role roster, invite plan, approval ownership.", "copy_as_shell"),
    consolePage("Usage", "Read-only quota and meter summary.", "copy_now"),
    consolePage("API Keys", "Prefix-only key metadata and rotation plan.", "copy_as_shell"),
    consolePage("Trust", "Release-gate evidence, audit bundle, hosted report preview.", "copy_now"),
    consolePage("Cloud Management", "Project switching, tenant-scoped resources, audit controls.", "copy_as_shell")
  ];
}

function buildCompatibilityState(summary, cases = []) {
  const traceReady = cases.filter((item) => item.trace_ready).length;
  const judgeReady = cases.filter((item) => (item.judge_results || []).length > 0 || item.grade).length;
  const toolCases = cases.filter((item) => (
    (item.expected?.tool_calls || []).length > 0
    || (item.actual?.tool_calls || []).length > 0
  )).length;
  return {
    a1_run_result_ready: summary.totalRuns > 0,
    a1_trace_case_count: traceReady,
    a1_tool_case_count: toolCases,
    a2_grade_result_ready: judgeReady > 0,
    a2_judge_case_count: judgeReady,
    dashboard_case_count: summary.totalCases,
    compatibility_note: "SaaS admin shell reads A3 normalized cases and does not alter A1 runner or A2 judge semantics."
  };
}

function role(roleName, permissions) {
  return {
    role: roleName,
    permissions,
    permission_count: permissions.length
  };
}

function cloudResource(type, id, label, mode) {
  return {
    type,
    id,
    label,
    mode
  };
}

function consolePage(page, purpose, a3Decision) {
  return {
    page,
    purpose,
    a3_decision: a3Decision
  };
}






