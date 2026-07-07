import {
  buildDashboardSummary,
  normalizeCases,
  summarizeCloudConsoleShell,
  summarizeReleaseGate,
  summarizeUsageQuota
} from "./report_builder.mjs";

export const A3_SAAS_ADMIN_SCHEMA_VERSION = "a3.saas_admin_console.v1";

export const A3_SAAS_ADMIN_ACTIONS = [
  "login_with_oauth",
  "switch_project",
  "invite_teammate",
  "rotate_api_key",
  "revoke_api_key",
  "view_usage",
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
    team: buildTeamState(releaseGate),
    api_keys: buildApiKeyState(),
    usage: buildUsageState(summary, usage, usageQuotaApiProbe),
    trust: buildTrustState(summary, releaseGate, cloudShell),
    cloud_management: buildCloudManagementState(cloudShell),
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
    switch_project: {
      area: "cloud_management",
      mode: "read_only",
      enabled: true,
      risk: "low",
      reason: "Project switching can read scoped dashboard payloads without mutating cloud state.",
      next_step: "Bind project selector to tenant-scoped API once A1 provides real org/project auth."
    },
    invite_teammate: {
      area: "team",
      mode: "plan_only",
      enabled: false,
      risk: "high",
      reason: "Invites send external emails and must require real auth, RBAC, and audit events.",
      next_step: "Create invite request preview and audit event first."
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
    supported_modes: ["manual_oauth_observation", "api_key_env_probe", "local_mock"],
    required_before_real_saas: ["hosted auth callback", "session cookie policy", "RBAC middleware", "audit login events"]
  };
}

function buildTeamState(releaseGate = {}) {
  const blocked = releaseGate.decision === "block_release";
  return {
    status: "mock_roster",
    invite_mode: "disabled_until_auth",
    roles: ["owner", "admin", "developer", "reviewer", "auditor", "billing_admin"],
    members: [
      { member_id: "mem_owner", display_name: "Owner", role: "owner", status: "active", redacted: true },
      { member_id: "mem_reviewer", display_name: "Release reviewer", role: "reviewer", status: blocked ? "required" : "active", redacted: true },
      { member_id: "mem_developer", display_name: "Developer", role: "developer", status: "active", redacted: true },
      { member_id: "mem_auditor", display_name: "Auditor", role: "auditor", status: "available", redacted: true }
    ],
    approval_policy: {
      required_for_blocked_release: blocked,
      required_roles: blocked ? ["reviewer", "owner"] : ["reviewer"],
      self_approval_allowed: false
    }
  };
}

function buildApiKeyState() {
  return {
    status: "metadata_only",
    create_mode: "server_required",
    reveal_policy: "one_time_secret_only_never_in_dashboard_fixture",
    keys: [
      {
        key_id: "key_ci_ingest",
        name: "CI ingest key",
        prefix: "ashr_ci_[REDACTED]",
        scopes: ["runs:write", "traces:write", "reports:read"],
        last_used_at: "redacted",
        status: "planned"
      },
      {
        key_id: "key_report_read",
        name: "Report read key",
        prefix: "ashr_rpt_[REDACTED]",
        scopes: ["reports:read", "release_gates:read"],
        last_used_at: "redacted",
        status: "planned"
      }
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
    api_probe_status: Object.fromEntries(Object.entries(apiProbeCalls).map(([name, value]) => [
      name,
      value?.status || value?.error?.status || "unknown"
    ])),
    billing_mutations_enabled: false
  };
}

function buildTrustState(summary, releaseGate = {}, cloudShell = {}) {
  const publishable = releaseGate.decision === "approve_release" && summary.totalCases > 0;
  return {
    status: publishable ? "ready_for_review" : "not_publishable",
    public_certificate_mode: "preview_only",
    publish_enabled: false,
    release_gate_decision: releaseGate.decision,
    release_gate_label: releaseGate.decision_label,
    frontend_trust_observed: cloudShell.observed_pages?.includes("Trust") || false,
    evidence_required: [
      "passing release gate",
      "redacted hosted report",
      "reviewer approval",
      "audit bundle hash",
      "A1 trace evidence",
      "A2 judge evidence"
    ],
    blocked_reason: publishable ? "Requires real hosted trust publishing service." : "Release gate is not approved."
  };
}

function buildCloudManagementState(cloudShell = {}) {
  return {
    status: cloudShell.available ? "frontend_confirmed_shell" : "local_mock_shell",
    observed_pages: cloudShell.observed_pages || [],
    sections: cloudShell.sections || [],
    real_mutations_enabled: false,
    supported_readonly_surfaces: ["projects", "runs", "cases", "reports", "usage", "trust"],
    disabled_mutations: ["create_api_key", "revoke_api_key", "invite_teammate", "change_billing", "publish_trust_certificate"]
  };
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
