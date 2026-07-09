const contract = Object.freeze({
  schema_version: "a3.wechat_mini_program_client_surface.v1",
  surface_id: "wechat-mini-program-client-surface",
  commercial_entry: "China commercial client surface for release approval and incident alert review",
  purpose: [
    "Give release owners a mobile approval shell for A3 release evidence.",
    "Give incident responders a mobile alert shell for A3 incident replay status.",
    "Keep WeChat Mini Program state downstream of A1, A2, and A3 evidence without storing secrets."
  ],
  pages: [
    {
      route: "pages/release-approval/index",
      title: "Release Approval",
      page_role: "release_approval_shell",
      consumes: [
        "A3 hosted report snapshot",
        "A3 release evidence summary v2",
        "A3 reviewer workflow board",
        "A1 RunResult status",
        "A2 GradeResult and ReleaseGate decision"
      ],
      api_reads: [
        "GET /api/a3/releases/:releaseId/evidence-summary?version=2",
        "GET /api/a3/releases/:releaseId/readbacks",
        "GET /api/a3/reports/:reportId/manifest"
      ],
      guarded_actions: [
        {
          action_id: "request_release_approval",
          mode: "planned_contract_only",
          required_rbac: ["release_owner", "reviewer", "auditor"],
          payload_fields: ["tenant_id", "project_id", "release_id", "summary_id", "review_item_id", "artifact_hash"],
          forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]
        }
      ]
    },
    {
      route: "pages/incident-alert/index",
      title: "Incident Alert",
      page_role: "incident_alert_shell",
      consumes: [
        "A3 incident replay queue",
        "A3 observability replay matrix",
        "A3 reviewer workflow board",
        "A1 Trace and ToolCall evidence",
        "A2 failure taxonomy and judge evidence"
      ],
      api_reads: [
        "GET /api/a3/releases/:releaseId/evidence-health",
        "GET /api/a3/releases/:releaseId/evidence-diff",
        "GET /api/a3/review/workflow?releaseId=:releaseId"
      ],
      guarded_actions: [
        {
          action_id: "acknowledge_incident_alert",
          mode: "planned_contract_only",
          required_rbac: ["release_owner", "incident_reviewer", "auditor"],
          payload_fields: ["tenant_id", "project_id", "release_id", "incident_id", "replay_item_id", "evidence_hash"],
          forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]
        }
      ]
    }
  ],
  api_contract: {
    reads: [
      {
        method: "GET",
        path: "/api/a3/releases/:releaseId/evidence-summary",
        query: ["version=2"],
        consumes: ["release_evidence_summary", "hosted_report_snapshot", "usage_ledger"],
        redaction: "server redacted; no raw customer payload"
      },
      {
        method: "GET",
        path: "/api/a3/releases/:releaseId/readbacks",
        consumes: ["release_evidence_readback"],
        redaction: "nested token/cookie/header fields removed before client render"
      },
      {
        method: "GET",
        path: "/api/a3/review/workflow",
        consumes: ["reviewer_workflow_board", "waiver_review", "approval_review"],
        redaction: "actor ids are aliases; no private account values"
      },
      {
        method: "GET",
        path: "/api/a3/reports/:reportId/manifest",
        consumes: ["hosted_report_manifest", "artifact_registry", "audit_bundle_index"],
        redaction: "hashes and status only for restricted artifacts"
      }
    ],
    write_requests: [
      {
        method: "POST",
        path: "/api/a3/review/actions/submit",
        status: "planned_contract_only",
        payload: "tenant_id, project_id, release_id, actor_role, action_id, evidence_hashes",
        forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]
      }
    ]
  },
  db_contract: {
    read_models: [
      "release_evidence_snapshots",
      "release_evidence_readbacks",
      "hosted_reports",
      "review_workflow_records",
      "audit_events",
      "usage_ledger",
      "artifact_registry_entries"
    ],
    write_models: [
      "review_action_requests",
      "incident_alert_acknowledgements"
    ],
    tenant_columns_required: ["tenant_id", "project_id", "release_id"]
  },
  event_contract: {
    emits: [
      "wechat.release_approval_viewed",
      "wechat.release_approval_requested",
      "wechat.incident_alert_viewed",
      "wechat.incident_alert_acknowledged"
    ],
    payload_policy: "ids, statuses, hashes, actor aliases, and counts only"
  },
  artifact_contract: {
    reads: [
      "release_evidence_summary",
      "hosted_report_snapshot",
      "reviewer_workflow_board",
      "incident_replay_packet",
      "audit_bundle_index",
      "artifact_registry_entry"
    ],
    never_reads: [
      "raw token",
      "cookie",
      "raw API key",
      "raw signed URL",
      "private prompt body"
    ]
  },
  a1_a2_a3_integration: {
    a1: ["A1 RunResult", "A1 Trace", "A1 ToolCall", "A1 Observation"],
    a2: ["A2 GradeResult", "A2 ReleaseGate", "A2 FailureTaxonomy", "A2 CommercialReadiness"],
    a3: ["A3 hosted report", "A3 release evidence", "A3 reviewer workflow", "A3 usage ledger", "A3 audit bundle"]
  },
  tenant_auth_rbac_usage_audit_redaction_guardrails: {
    tenant: "Every API call and event must include tenant_id, project_id, and release_id from authenticated server context.",
    auth: "The mini program receives server-issued session state only; it does not store tokens, cookies, raw keys, or Authorization headers.",
    rbac: "Release approval and incident acknowledgement require release_owner, reviewer, incident_reviewer, or auditor role checks server-side.",
    usage: "Meter page views, approval requests, incident acknowledgements, readbacks viewed, and hosted report opens as usage events.",
    audit: "Append audit events for page viewed, approval requested, alert acknowledged, report opened, and denied access.",
    redaction: "Render only redacted summaries, aliases, hashes, counts, statuses, and hosted report links; never render raw signed URLs or secret-bearing payloads."
  },
  storage_policy: {
    noPersistentToken: true,
    noCookie: true,
    noRawKey: true,
    noWxStorageToken: true,
    allowed_local_state: ["last_opened_release_id", "last_opened_incident_id"],
    forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url", "password", "secret"]
  }
});

module.exports = contract;
