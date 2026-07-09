export type A3MobileSurfaceMode = "contract-only" | "api-backed";

export type A3MobileReleaseCard = {
  releaseId: string;
  status: "blocked" | "review_required" | "approved" | "unknown";
  evidenceSummaryId: string;
  hostedReportPath: "/reports/[REPORT_ID]" | "/r/[REDACTED_TOKEN]";
  a1Evidence: {
    runResultReady: boolean;
    traceReady: boolean;
    toolCallCount: number;
  };
  a2Evidence: {
    gradeResultReady: boolean;
    passFailReady: boolean;
    failureTaxonomyReady: boolean;
  };
  a3Evidence: {
    releaseEvidenceReady: boolean;
    reviewerWorkflowReady: boolean;
    auditExportReady: boolean;
  };
};

export const a3MobileClientSurfaceContract = {
  schema_version: "a3.mobile_client_surface.v1",
  app_surface: "React Native / Expo release approval client",
  mode: "contract-only" satisfies A3MobileSurfaceMode,
  primary_workflows: [
    "release_gate_alert",
    "incident_replay_alert",
    "reviewer_workflow_task",
    "hosted_report_review"
  ],
  allowed_api_surfaces: [
    "GET /api/a3/dashboard",
    "GET /api/a3/review/workflow",
    "GET /api/a3/reports/:reportId",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "GET /api/a3/releases/:releaseId/readbacks",
    "POST /api/a3/review/waivers",
    "POST /api/a3/review/approvals"
  ],
  disabled_mutations_until_hosted_auth: [
    "real_ashr_cloud_write",
    "billing_checkout",
    "billing_portal",
    "team_invite_send",
    "api_key_create_or_reveal",
    "trust_center_publish"
  ],
  a1_contract: {
    consumes: ["RunResult", "Trace", "Observation", "ToolCall", "agent_response"],
    never_redefines_runner_semantics: true
  },
  a2_contract: {
    consumes: ["GradeResult", "score", "pass_fail", "release_gate", "failure_taxonomy", "commercial_readiness"],
    never_redefines_judge_semantics: true
  },
  a3_contract: {
    consumes: ["ReleaseEvidence", "HostedReport", "ReviewerWorkflow", "UsageLedger", "AuditEvent", "ArtifactRegistry"],
    mobile_is_downstream_of_a1_a2: true
  },
  tenant_auth_rbac_usage_audit: {
    tenant_scope_required: true,
    hosted_auth_required_for_mutation: true,
    rbac_required_for_approval: true,
    usage_meter_visible: true,
    audit_event_required_for_review_action: true
  },
  redaction_guardrails: {
    store_raw_api_key: false,
    store_cookie: false,
    store_authorization_header: false,
    store_raw_share_token: false,
    render_signed_media_url: false,
    render_email: false,
    allowed_identifiers: ["release_id", "summary_id", "case_id", "hash_prefix", "redacted_report_path"]
  }
} as const;

export function summarizeMobileReleaseCard(card: A3MobileReleaseCard) {
  return {
    releaseId: card.releaseId,
    status: card.status,
    evidenceSummaryId: card.evidenceSummaryId,
    hostedReportPath: card.hostedReportPath,
    ready: Boolean(
      card.a1Evidence.runResultReady
      && card.a1Evidence.traceReady
      && card.a2Evidence.gradeResultReady
      && card.a2Evidence.passFailReady
      && card.a3Evidence.releaseEvidenceReady
      && card.a3Evidence.reviewerWorkflowReady
    )
  };
}
