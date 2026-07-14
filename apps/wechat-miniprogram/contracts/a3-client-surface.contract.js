const contract = Object.freeze({
  schema_version: "a3.wechat_mini_program_client_surface.v2",
  surface_id: "wechat-mini-program-client-surface",
  customer_brand: "Ashr 发布中心",
  customer_facing_terminology: ["执行证据", "评测结论", "发布决策", "人工审批", "风险告警"],
  data_modes: {
    preview: "Explicit local demonstration data; no production action is performed.",
    connected: "HTTPS enterprise API projections with server-side identity and tenant authority."
  },
  pages: [
    {
      route: "pages/workbench/index",
      title: "发布工作台",
      page_role: "release_workbench",
      customer_purpose: "Show the current release decision, evidence stages, quality metrics, and pending work.",
      consumes: ["release dashboard projection", "release evidence summary", "incident replay queue"],
      api_reads: ["GET /api/a3/dashboard?source=api-ingest"],
      mutations: []
    },
    {
      route: "pages/release-approval/index",
      title: "发布审批",
      page_role: "release_approval",
      customer_purpose: "Explain why a candidate is ready or blocked before a human decision.",
      consumes: ["release evidence summary v2", "deployment readbacks", "release decision provenance"],
      api_reads: [
        "GET /api/a3/releases/:releaseId/evidence-summary?version=2",
        "GET /api/a3/releases/:releaseId/readbacks"
      ],
      guarded_actions: [
        {
          action_id: "review_permission_preflight",
          mode: "preflight_only",
          endpoint: "POST /api/a3/ui-actions/preflight",
          result_effect: "No release decision is written by this client version.",
          server_authority: ["authenticated actor", "tenant scope", "RBAC", "release evidence version"],
          forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]
        }
      ]
    },
    {
      route: "pages/incident-alert/index",
      title: "风险告警",
      page_role: "incident_triage",
      customer_purpose: "Filter risk cases and inspect the redacted evidence timeline and response checklist.",
      consumes: ["incident replay queue", "trace summary", "tool-call summary", "failure classification"],
      api_reads: ["GET /api/a3/dashboard?source=api-ingest"],
      mutations: []
    },
    {
      route: "pages/account/index",
      title: "账户与连接",
      page_role: "connection_diagnostics",
      customer_purpose: "Show enterprise connection, client security, and production capability status without exposing credentials.",
      consumes: ["service health", "tenant display scope", "client capability status"],
      api_reads: ["GET /api/a3/health", "GET /api/a3/dashboard?source=api-ingest"],
      mutations: []
    }
  ],
  api_contract: {
    reads: [
      {
        method: "GET",
        path: "/api/a3/health",
        authority: "public health projection",
        redaction: "status only"
      },
      {
        method: "GET",
        path: "/api/a3/dashboard",
        authority: "authenticated server context",
        consumes: ["release decision provenance", "release evidence summary", "incident replay queue"],
        redaction: "server-redacted projection; no raw customer payload"
      },
      {
        method: "GET",
        path: "/api/a3/releases/:releaseId/evidence-summary",
        authority: "authenticated server context",
        consumes: ["release evidence summary", "decision ledger projection"],
        redaction: "statuses, counts, aliases, and evidence references only"
      },
      {
        method: "GET",
        path: "/api/a3/releases/:releaseId/readbacks",
        authority: "authenticated server context",
        consumes: ["deployment and repository readbacks"],
        redaction: "nested secret-bearing fields removed before client render"
      }
    ],
    guarded_requests: [
      {
        method: "POST",
        path: "/api/a3/ui-actions/preflight",
        status: "implemented_preflight_only",
        writes_release_state: false,
        payload: "tenant/project/environment/release ids and evidence references only",
        forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]
      }
    ]
  },
  internal_source_provenance: {
    visibility: "contract_metadata_only_not_customer_ui",
    execution: ["A1 RunResult", "A1 Trace", "A1 ToolCall", "A1 Observation"],
    evaluation: ["A2 GradeResult", "A2 ReleaseGate", "A2 FailureTaxonomy", "A2 DecisionLedger"],
    product: ["A3 hosted report", "A3 release evidence", "A3 reviewer workflow", "A3 audit bundle"]
  },
  tenant_auth_rbac_usage_audit_redaction_guardrails: {
    tenant: "Navigation ids are hints only; authenticated server context remains authoritative for tenant, project, environment, and release scope.",
    auth: "The client sends no embedded Authorization header and persists no token, cookie, API key, or raw credential.",
    rbac: "Only the server may decide whether an actor can review a release; this version performs preflight and never writes a decision.",
    usage: "Future telemetry must use redacted ids, statuses, counts, and action outcomes without customer evidence bodies.",
    audit: "Any future decision mutation must append an immutable server-side audit event before the UI may claim success.",
    redaction: "Reject responses containing secret-bearing keys or values and render only approved summary projections."
  },
  capability_status: {
    wechat_identity: "not_implemented_requires_qualified_appid_and_backend",
    review_mutation: "not_implemented_preflight_only",
    subscription_message: "not_implemented",
    wechat_payment: "not_in_scope_for_release_center",
    production_appid: "not_configured_touristappid_for_preview"
  },
  storage_policy: {
    noPersistentToken: true,
    noCookie: true,
    noRawKey: true,
    noWxStorageToken: true,
    allowed_local_state: [],
    forbidden_fields: ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url", "password", "secret"]
  }
});

module.exports = contract;
