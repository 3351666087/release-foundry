export const A3_LIVE_OPS_CONTROL_PLANE_SCHEMA_VERSION = "a3.live_ops_control_plane.v1";

export function buildA3LiveOpsControlPlane(inputs = {}, options = {}) {
  const releaseEvidence = inputs.releaseEvidence || inputs.release_evidence || {};
  const reviewWorkflow = inputs.reviewWorkflow || inputs.review_workflow || {};
  const usageLedger = inputs.usageLedger || inputs.usage_ledger || {};
  const billingReadiness = inputs.billingReadiness || inputs.billing_readiness || {};
  const reportCenter = inputs.reportCenter || inputs.report_center || {};
  const eventOutbox = inputs.eventOutbox || inputs.event_outbox || {};
  const liveWorkflowReadiness = inputs.liveWorkflowReadiness || inputs.live_workflow_readiness || {};
  const source = options.source || inputs.source || liveWorkflowReadiness.source || usageLedger.source || "mock";

  const lanes = [
    githubCheckLane(releaseEvidence),
    prCommentLane(releaseEvidence),
    reviewerDecisionLane(reviewWorkflow),
    humanOperationLane(reviewWorkflow, eventOutbox),
    billingAdminLane(usageLedger, billingReadiness),
    reportShareLane(reportCenter)
  ];
  const counts = {
    lane_count: lanes.length,
    api_backed_count: lanes.filter((item) => item.api_backed).length,
    audit_backed_count: lanes.filter((item) => item.audit_backed).length,
    live_worker_ready_count: lanes.filter((item) => item.live_worker_ready).length,
    read_only_state_count: lanes.filter((item) => item.current_mode === "read_only_state").length,
    local_external_mutation_count: lanes.filter((item) => item.real_external_mutation_performed_locally).length,
    missing_contract_count: lanes.filter((item) => item.status === "missing_contract").length
  };

  return {
    schema_version: A3_LIVE_OPS_CONTROL_PLANE_SCHEMA_VERSION,
    source,
    tenant_scope: {
      organization_id: options.organizationId
        || liveWorkflowReadiness.tenant_scope?.organization_id
        || usageLedger.tenant_scope?.organization_id
        || billingReadiness.tenant_scope?.organization_id
        || "org-local",
      project_id: options.projectId
        || liveWorkflowReadiness.tenant_scope?.project_id
        || usageLedger.tenant_scope?.project_id
        || billingReadiness.tenant_scope?.project_id
        || "project-local"
    },
    status: counts.missing_contract_count > 0
      ? "needs_contracts"
      : counts.local_external_mutation_count > 0
        ? "live_mutation_observed"
        : "control_plane_ready_needs_live_workers",
    counts,
    requested_growth_items: lanes.map((item) => ({
      id: item.id,
      label: item.label,
      status: item.status,
      current_mode: item.current_mode,
      live_worker_ready: item.live_worker_ready,
      audit_backed: item.audit_backed,
      next_action: item.next_action
    })),
    lanes,
    human_operation_summary: {
      review_record_count: numberOr(reviewWorkflow.record_count, 0),
      approval_count: numberOr(reviewWorkflow.approval_count, 0),
      denial_count: numberOr(reviewWorkflow.denial_count, 0),
      waiver_count: numberOr(reviewWorkflow.waiver_count, 0),
      event_outbox_count: numberOr(eventOutbox.event_count, 0),
      latest_human_action: reviewWorkflow.latest_human_action || null,
      dashboard_visible: numberOr(reviewWorkflow.record_count, 0) > 0 || numberOr(eventOutbox.event_count, 0) > 0
    },
    billing_state_summary: {
      usage_ledger_status: usageLedger.status || "unknown",
      meter_count: Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0,
      billing_readiness_status: billingReadiness.status || "unknown",
      billing_mutations_enabled: billingReadiness.billing_mutations_enabled === true,
      invoice_preview_ready: billingReadiness.invoice_preview?.ready_for_customer_invoice === true
    },
    report_link_summary: {
      report_count: numberOr(reportCenter.summary?.report_count, 0),
      shareable_count: numberOr(reportCenter.summary?.shareable_count, 0),
      revoked_count: numberOr(reportCenter.summary?.revoked_count, 0),
      expired_count: numberOr(reportCenter.summary?.expired_count, 0),
      total_view_count: numberOr(reportCenter.summary?.total_view_count, 0)
    },
    a1_a2_alignment: {
      a1_consumed_contracts: ["RunResult", "Trace", "ToolCall", "usage ledger / billing migration evidence"],
      a2_consumed_contracts: ["GradeResult", "ReleaseGate", "failure taxonomy", "cross-lane security context"],
      a3_mutates_a1_a2_semantics: false,
      note: "A3 turns A1/A2 evidence into product workflow state; it does not rewrite runner results, judge scores, pass/fail, or failure classes."
    },
    safety: {
      secret_values_included: false,
      raw_tokens_included: false,
      raw_cookies_included: false,
      raw_emails_included: false,
      raw_signed_urls_included: false,
      real_github_mutation_performed_locally: false,
      real_billing_mutation_performed_locally: false,
      real_report_publication_performed_locally: false
    },
    next_actions: nextActions(lanes)
  };
}

function githubCheckLane(releaseEvidence = {}) {
  const receipt = releaseEvidence.githubCheckPublishReceipt || releaseEvidence.github_check_publish_receipt || {};
  const readback = releaseEvidence.githubCheckReadback || releaseEvidence.github_check_readback || findReadback(releaseEvidence, "check_run");
  const publishReady = Boolean(receipt.schema_version || receipt.request);
  const readbackConfirmed = readback.readback_confirmed === true || readback.readback_status === "readback_confirmed";
  const livePostedByReceipt = receipt.dry_run === false && receipt.posted === true;
  return lane({
    id: "github_pr_check_live_publishing",
    label: "GitHub PR check live publishing",
    product_surface: "PR Gate",
    status: readbackConfirmed
      ? "readback_confirmed"
      : publishReady
        ? "publish_contract_ready"
        : "missing_contract",
    current_mode: livePostedByReceipt ? "live_mutation_receipt" : publishReady ? "dry_run_publish_plan" : "missing",
    live_worker_ready: publishReady && Boolean(receipt.request?.requires_token_scope || receipt.requires_token_scope || "checks:write"),
    api_backed: publishReady,
    audit_backed: publishReady || readbackConfirmed,
    real_external_mutation_performed_locally: livePostedByReceipt,
    evidence_sources: compact([
      receipt.schema_version,
      readback.schema_version,
      readback.readback_id
    ]),
    api_routes: ["POST /internal/github/check-run", "POST /api/a3/releases/:releaseId/readbacks"],
    db_tables: ["release_evidence_readbacks", "event_outbox", "audit_events"],
    audit_events: ["github.check_publish_requested", "release_evidence.readback_captured"],
    dashboard_fields: ["check name", "conclusion", "readback status", "stale/missing/deleted state", "head SHA alias"],
    a1_dependency: "A1 provides hosted API/GitHub worker boundary and durable readback persistence.",
    a2_dependency: "A2 release gate decision supplies the pass/fail reason that the check publishes.",
    next_action: readbackConfirmed
      ? "Bind confirmed check readback into hosted PR gate and branch-protection evidence."
      : "Run the check publisher from CI/GitHub App with checks:write, then post sanitized readback to A3."
  });
}

function prCommentLane(releaseEvidence = {}) {
  const receipt = releaseEvidence.githubPrCommentPublishReceipt || releaseEvidence.github_pr_comment_publish_receipt || {};
  const readback = releaseEvidence.githubPrCommentReadback || releaseEvidence.github_pr_comment_readback || findReadback(releaseEvidence, "pr_comment");
  const publishReady = Boolean(receipt.schema_version || receipt.plan);
  const readbackConfirmed = readback.readback_confirmed === true || readback.readback_status === "readback_confirmed";
  const livePostedByReceipt = receipt.dry_run === false && receipt.posted === true;
  return lane({
    id: "pr_comment_live_publishing",
    label: "PR comment live publishing",
    product_surface: "PR Gate",
    status: readbackConfirmed
      ? "readback_confirmed"
      : publishReady
        ? "publish_contract_ready"
        : "missing_contract",
    current_mode: livePostedByReceipt ? "live_mutation_receipt" : publishReady ? "dry_run_publish_plan" : "missing",
    live_worker_ready: publishReady && Boolean(receipt.plan?.requires_token_scope || receipt.requires_token_scope || "pull-requests:write"),
    api_backed: publishReady,
    audit_backed: publishReady || readbackConfirmed,
    real_external_mutation_performed_locally: livePostedByReceipt,
    evidence_sources: compact([
      receipt.schema_version,
      readback.schema_version,
      readback.readback_id
    ]),
    api_routes: ["POST /internal/github/pr-comment", "POST /api/a3/releases/:releaseId/readbacks"],
    db_tables: ["release_evidence_readbacks", "event_outbox", "audit_events"],
    audit_events: ["github.pr_comment_publish_requested", "release_evidence.readback_captured"],
    dashboard_fields: ["pull number alias", "comment marker", "body hash", "readback status", "stale/missing/deleted state"],
    a1_dependency: "A1 provides the hosted worker/API route that owns GitHub credentials.",
    a2_dependency: "A2 release gate/failure taxonomy gives the reviewer-readable content.",
    next_action: readbackConfirmed
      ? "Keep comment readback freshness visible beside reviewer workflow."
      : "Run PR comment upsert through a GitHub App/Action and capture sanitized readback."
  });
}

function reviewerDecisionLane(reviewWorkflow = {}) {
  const recordCount = numberOr(reviewWorkflow.record_count, 0);
  const hasWorkflow = reviewWorkflow.schema_version === "a3.review_workflow_index.v1" || recordCount > 0;
  return lane({
    id: "reviewer_approve_deny_waiver_workflow",
    label: "Reviewer approve / deny / waiver workflow",
    product_surface: "Reviewer Workflow",
    status: hasWorkflow ? "api_backed" : "missing_contract",
    current_mode: recordCount > 0 ? "human_records_present" : hasWorkflow ? "api_backed_no_records" : "missing",
    live_worker_ready: hasWorkflow,
    api_backed: hasWorkflow,
    audit_backed: recordCount > 0,
    real_external_mutation_performed_locally: false,
    evidence_sources: compact([reviewWorkflow.schema_version, reviewWorkflow.latest_record_id]),
    api_routes: ["POST /api/a3/review/approvals", "POST /api/a3/review/denials", "POST /api/a3/review/waivers", "GET /api/a3/review/workflow"],
    db_tables: ["review_workflow_records", "audit_events", "event_outbox"],
    audit_events: ["approval.submitted", "denial.submitted", "waiver.submitted"],
    dashboard_fields: ["record id", "record type", "accepted", "actor hash", "release version", "audit event id"],
    a1_dependency: "A1 owns hosted auth/RBAC identity binding before approvals affect live checks.",
    a2_dependency: "A2 owns release policy, failure taxonomy, and unblock semantics.",
    next_action: recordCount > 0
      ? "Add reviewer filters by actor hash, status, release version, and unblock gate."
      : "Submit one local approval/denial/waiver through the API to prove visible human records."
  });
}

function humanOperationLane(reviewWorkflow = {}, eventOutbox = {}) {
  const reviewRecords = numberOr(reviewWorkflow.record_count, 0);
  const outboxEvents = numberOr(eventOutbox.event_count, 0);
  const visibleCount = reviewRecords + outboxEvents;
  return lane({
    id: "dashboard_human_operation_records",
    label: "Dashboard shows human operation records",
    product_surface: "Audit Log",
    status: visibleCount > 0 ? "visible" : "api_backed_no_records",
    current_mode: visibleCount > 0 ? "audit_metadata_visible" : "waiting_for_human_actions",
    live_worker_ready: true,
    api_backed: true,
    audit_backed: visibleCount > 0,
    real_external_mutation_performed_locally: false,
    evidence_sources: compact([reviewWorkflow.schema_version, eventOutbox.schema_version]),
    api_routes: ["GET /api/a3/events/outbox", "GET /api/a3/review/workflow", "GET /api/a3/admin/actions"],
    db_tables: ["event_outbox", "audit_events", "review_workflow_records", "saas_admin_action_requests"],
    audit_events: ["review.*", "admin_action.*", "report.*", "release_evidence.readback_captured"],
    dashboard_fields: ["event id", "event type", "resource id", "delivery status", "payload hash prefix", "actor hash"],
    a1_dependency: "A1 durable audit/outbox backend will replace local memory/file persistence.",
    a2_dependency: "A2 can consume cross-lane security context from these records.",
    next_action: visibleCount > 0
      ? "Promote the latest human events into dashboard timeline and report manifests."
      : "Create one review/admin/report action so dashboard has real operation rows to show."
  });
}

function billingAdminLane(usageLedger = {}, billingReadiness = {}) {
  const meterCount = Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0;
  const hasReadState = usageLedger.schema_version === "a3.usage_ledger.v1"
    && billingReadiness.schema_version === "a3.billing_readiness.v1";
  return lane({
    id: "billing_admin_real_usage_billing_state",
    label: "Billing/admin reads usage and billing state",
    product_surface: "Billing / Admin",
    status: hasReadState ? "read_only_state_ready" : "missing_contract",
    current_mode: "read_only_state",
    live_worker_ready: hasReadState,
    api_backed: hasReadState,
    audit_backed: hasReadState,
    real_external_mutation_performed_locally: false,
    evidence_sources: compact([usageLedger.schema_version, billingReadiness.schema_version]),
    api_routes: ["GET /api/a3/usage/ledger", "GET /api/a3/billing/readiness"],
    db_tables: ["usage_ledger", "usage_rollups", "billing_customers", "billing_subscriptions", "billing_invoices", "audit_events"],
    audit_events: ["usage.recorded", "billing.subscription_changed", "audit_event.created"],
    dashboard_fields: ["plan", "quota", "meter quantity", "billable unit count", "invoice preview", "billing mutation disabled"],
    a1_dependency: "A1 owns authoritative usage events, billing ledger migrations, provider webhooks, and quota enforcement.",
    a2_dependency: "A2 judge meters and risk policy must stay stable for cost and failure analytics.",
    next_action: hasReadState && meterCount > 0
      ? "Swap read-only fixture meters to A1 durable billing ledger rows when available."
      : "Ask A1 for usage ledger/billing migration sample rows before claiming live billing."
  });
}

function reportShareLane(reportCenter = {}) {
  const summary = reportCenter.summary || {};
  const lifecycleReady = reportCenter.schema_version === "a3.report_center_index.v1";
  return lane({
    id: "report_share_link_revocable_expiring_audited",
    label: "Report share link revocable, expiring, audited",
    product_surface: "Report Center",
    status: lifecycleReady ? "lifecycle_ready" : "missing_contract",
    current_mode: lifecycleReady ? "api_backed_lifecycle" : "missing",
    live_worker_ready: lifecycleReady,
    api_backed: lifecycleReady,
    audit_backed: lifecycleReady,
    real_external_mutation_performed_locally: false,
    evidence_sources: compact([reportCenter.schema_version]),
    api_routes: ["POST /api/a3/reports/share", "GET /r/:shareToken", "POST /api/a3/reports/:reportId/revoke", "GET /api/a3/reports/center"],
    db_tables: ["shareable_reports", "report_share_links", "report_view_events", "report_revocations", "audit_events"],
    audit_events: ["report.shared", "report_share_link.viewed", "report.revoked", "report.expired"],
    dashboard_fields: ["report id", "token hash prefix", "expires at", "revoked at", "view count", "manifest completeness"],
    a1_dependency: "A1 hosted auth/object storage will later own public access enforcement and artifact storage.",
    a2_dependency: "A2 release evidence and judge summaries are included in safe report payloads.",
    next_action: numberOr(summary.shareable_count, 0) > 0
      ? "Persist share-link events in Postgres and expose revocation/audit history in hosted mode."
      : "Create one shareable report so link lifecycle can be verified end to end."
  });
}

function lane(value = {}) {
  return {
    id: value.id,
    label: value.label,
    product_surface: value.product_surface,
    status: value.status,
    current_mode: value.current_mode,
    live_worker_ready: value.live_worker_ready === true,
    api_backed: value.api_backed === true,
    audit_backed: value.audit_backed === true,
    real_external_mutation_performed_locally: value.real_external_mutation_performed_locally === true,
    evidence_sources: value.evidence_sources || [],
    api_routes: value.api_routes || [],
    db_tables: value.db_tables || [],
    audit_events: value.audit_events || [],
    dashboard_fields: value.dashboard_fields || [],
    a1_dependency: value.a1_dependency,
    a2_dependency: value.a2_dependency,
    next_action: value.next_action
  };
}

function findReadback(releaseEvidence = {}, resourceKind) {
  const records = releaseEvidence.readback_records || releaseEvidence.readbacks || [];
  return Array.isArray(records)
    ? records.find((item) => item.resource_kind === resourceKind) || {}
    : {};
}

function nextActions(lanes = []) {
  return lanes
    .filter((item) => item.status !== "readback_confirmed" && item.status !== "lifecycle_ready")
    .map((item) => item.next_action)
    .filter(Boolean)
    .slice(0, 4);
}

function compact(items = []) {
  return items.filter((item) => item !== undefined && item !== null && String(item).trim() !== "");
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
