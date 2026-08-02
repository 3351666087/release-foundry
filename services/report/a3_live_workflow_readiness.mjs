export const A3_LIVE_WORKFLOW_READINESS_SCHEMA_VERSION = "a3.live_workflow_readiness.v1";

export function buildA3LiveWorkflowReadiness(inputs = {}, options = {}) {
  const releaseEvidence = inputs.releaseEvidence || inputs.release_evidence || {};
  const reviewWorkflow = inputs.reviewWorkflow || inputs.review_workflow || {};
  const usageLedger = inputs.usageLedger || inputs.usage_ledger || {};
  const billingReadiness = inputs.billingReadiness || inputs.billing_readiness || {};
  const reportCenter = inputs.reportCenter || inputs.report_center || {};
  const saasAdmin = inputs.saasAdmin || inputs.saas_admin_console || {};
  const eventOutbox = inputs.eventOutbox || inputs.event_outbox || {};
  const capabilities = [
    githubCheckCapability(releaseEvidence.githubCheckPublishReceipt || releaseEvidence.github_check_publish_receipt || releaseEvidence.github_check_publish || {}),
    prCommentCapability(releaseEvidence.githubPrCommentPublishReceipt || releaseEvidence.github_pr_comment_publish_receipt || releaseEvidence.github_pr_comment_publish || {}),
    reviewerWorkflowCapability(reviewWorkflow),
    humanOperationCapability(reviewWorkflow, saasAdmin, eventOutbox),
    billingAdminCapability(usageLedger, billingReadiness),
    shareLinkLifecycleCapability(reportCenter)
  ];
  const readyCount = capabilities.filter((item) => item.status !== "missing_contract").length;
  const liveMutationCount = capabilities.filter((item) => item.live_external_mutation_observed).length;
  const needsBackendCount = capabilities.filter((item) => item.needs_backend_or_credentials).length;
  const auditBackedCount = capabilities.filter((item) => item.audit_backed).length;

  return {
    schema_version: A3_LIVE_WORKFLOW_READINESS_SCHEMA_VERSION,
    source: options.source || inputs.source || "mock",
    tenant_scope: {
      organization_id: options.organizationId || usageLedger.tenant_scope?.organization_id || saasAdmin.organization?.organization_id || "org-local",
      project_id: options.projectId || usageLedger.tenant_scope?.project_id || saasAdmin.project?.project_id || "project-local"
    },
    status: liveMutationCount > 0
      ? "live_evidence_observed"
      : readyCount === capabilities.length
        ? "contract_ready_needs_live_credentials"
        : "needs_more_contracts",
    capability_count: capabilities.length,
    ready_capability_count: readyCount,
    needs_backend_or_credentials_count: needsBackendCount,
    audit_backed_count: auditBackedCount,
    live_external_mutation_observed_count: liveMutationCount,
    human_action_count: numberOr(reviewWorkflow.human_action_count, 0) + numberOr(saasAdmin.action_request_summary?.request_count, 0),
    capabilities,
    next_actions: nextActions(capabilities),
    a1_a2_boundary: "A3 reads A1/A2 evidence, usage meters, release-gate outputs, and review records downstream only; it does not modify A1 runner/auth/billing semantics or A2 judge/release-policy semantics.",
    commercial_value: "Turns the next SaaS growth items into one dashboard/API contract: GitHub publishing, human review, usage/billing readback, and hosted report lifecycle can be checked before claiming production readiness.",
    safety: {
      secret_values_included: false,
      raw_tokens_included: false,
      raw_cookies_included: false,
      raw_emails_included: false,
      billing_mutations_performed: false,
      live_external_mutations_performed_by_a3_local_dashboard: false
    }
  };
}

function githubCheckCapability(receipt = {}) {
  const hasPublisher = Boolean(receipt.schema_version || receipt.request);
  const liveObserved = receipt.dry_run === false && receipt.posted === true;
  return capability({
    id: "github_pr_check_live_publishing",
    label: "GitHub PR check live publishing",
    status: liveObserved ? "live_posted" : hasPublisher ? "publisher_ready_needs_live_token" : "missing_contract",
    evidence: hasPublisher ? receipt.schema_version || "a3.github_check_publish_receipt.v1" : "missing",
    api_or_surface: "services/report/a3_github_integration.mjs",
    dashboard_value: "PR Gate can show machine-readable check publish status and readback evidence.",
    needs_backend_or_credentials: !liveObserved,
    audit_backed: Boolean(receipt.request || receipt.check_run),
    live_external_mutation_observed: liveObserved,
    next_action: liveObserved
      ? "Persist sanitized live GitHub check receipt and readback in release evidence."
      : "Run the existing publisher in GitHub Actions or GitHub App mode with checks:write, then capture sanitized readback."
  });
}

function prCommentCapability(receipt = {}) {
  const hasPublisher = Boolean(receipt.schema_version || receipt.plan);
  const liveObserved = receipt.dry_run === false && receipt.posted === true;
  return capability({
    id: "pr_comment_live_publishing",
    label: "PR comment live publishing",
    status: liveObserved ? "live_posted" : hasPublisher ? "publisher_ready_needs_live_token" : "missing_contract",
    evidence: hasPublisher ? receipt.schema_version || "a3.github_pr_comment_publish_receipt.v1" : "missing",
    api_or_surface: "services/report/a3_github_integration.mjs",
    dashboard_value: "PR Gate can show human-readable reviewer comment status and stale/missing readback.",
    needs_backend_or_credentials: !liveObserved,
    audit_backed: Boolean(receipt.plan || receipt.comment),
    live_external_mutation_observed: liveObserved,
    next_action: liveObserved
      ? "Persist sanitized PR comment receipt and readback in release evidence."
      : "Run the existing PR comment publisher with pull-requests:write and store sanitized receipt/readback."
  });
}

function reviewerWorkflowCapability(reviewWorkflow = {}) {
  const hasWorkflow = reviewWorkflow.schema_version === "a3.review_workflow_index.v1"
    || numberOr(reviewWorkflow.waiver_count, 0) > 0
    || numberOr(reviewWorkflow.approval_count, 0) > 0
    || numberOr(reviewWorkflow.denial_count, 0) > 0;
  return capability({
    id: "reviewer_approve_deny_waiver_workflow",
    label: "Reviewer approve / deny / waiver workflow",
    status: hasWorkflow ? "workflow_ready" : "missing_contract",
    evidence: hasWorkflow ? "a3.review_workflow_index.v1" : "missing",
    api_or_surface: "GET /api/a3/review/workflow",
    dashboard_value: `${numberOr(reviewWorkflow.approval_count, 0)} approval(s), ${numberOr(reviewWorkflow.denial_count, 0)} denial(s), ${numberOr(reviewWorkflow.waiver_count, 0)} waiver(s).`,
    needs_backend_or_credentials: !reviewWorkflow.durable_storage_ready,
    audit_backed: numberOr(reviewWorkflow.record_count, 0) > 0,
    next_action: hasWorkflow
      ? "Keep every approval, denial, and waiver tenant-scoped and event-backed."
      : "Submit one approval/denial/waiver record through the A3 API to prove human review."
  });
}

function humanOperationCapability(reviewWorkflow = {}, saasAdmin = {}, eventOutbox = {}) {
  const reviewActions = numberOr(reviewWorkflow.human_action_count, 0);
  const adminActions = numberOr(saasAdmin.action_request_summary?.request_count, 0);
  const outboxEvents = numberOr(eventOutbox.event_count, 0) || numberOr(eventOutbox.outbox_count, 0);
  const count = reviewActions + adminActions;
  return capability({
    id: "dashboard_human_operation_records",
    label: "Dashboard human operation records",
    status: count > 0 ? "visible" : "workflow_ready_no_records",
    evidence: count > 0 ? "review_workflow_records + saas_admin_action_requests" : "no human action rows yet",
    api_or_surface: "Reviewer Workflow + SaaS Admin Console",
    dashboard_value: `${count} human operation record(s), ${outboxEvents} outbox/audit event(s).`,
    needs_backend_or_credentials: false,
    audit_backed: outboxEvents > 0 || count > 0,
    next_action: count > 0
      ? "Show latest actor-hash, action type, status, and audit event id in dashboard."
      : "Use the dashboard buttons to record one denial/waiver/admin guardrail request."
  });
}

function billingAdminCapability(usageLedger = {}, billingReadiness = {}) {
  const meterCount = Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0;
  const hasReadState = usageLedger.schema_version === "a3.usage_ledger.v1"
    && billingReadiness.schema_version === "a3.billing_readiness.v1";
  return capability({
    id: "billing_admin_real_usage_billing_state",
    label: "Billing/admin read real usage/billing state",
    status: hasReadState ? "read_only_state_ready" : "missing_contract",
    evidence: hasReadState ? "usage_ledger + billing_readiness" : "missing",
    api_or_surface: "GET /api/a3/usage/ledger + GET /api/a3/billing/readiness",
    dashboard_value: `${meterCount} usage meter(s), billing status ${billingReadiness.status || "unknown"}.`,
    needs_backend_or_credentials: billingReadiness.billing_mutations_enabled !== true,
    audit_backed: hasReadState,
    next_action: hasReadState
      ? "Keep billing mutations disabled until A1 owns authoritative usage ledger, hosted auth, and provider webhooks."
      : "Attach usage ledger and billing readiness endpoints to the admin panel."
  });
}

function shareLinkLifecycleCapability(reportCenter = {}) {
  const summary = reportCenter.summary || {};
  const shareable = numberOr(summary.shareable_count, 0);
  const revoked = numberOr(summary.revoked_count, 0);
  const expired = numberOr(summary.expired_count, 0);
  const views = numberOr(summary.total_view_count, 0);
  const lifecycleReady = reportCenter.schema_version === "a3.report_center_index.v1"
    || shareable + revoked + expired + views > 0;
  return capability({
    id: "report_share_link_revocable_expiring_audited",
    label: "Report share link revocable, expiring, audited",
    status: lifecycleReady ? "lifecycle_ready" : "missing_contract",
    evidence: lifecycleReady ? "shareable_reports + report_share_links + report_view_events" : "missing",
    api_or_surface: "POST /api/a3/reports/share + POST /api/a3/reports/:reportId/revoke + GET /r/:shareToken",
    dashboard_value: `${shareable} shareable, ${revoked} revoked, ${expired} expired, ${views} view event(s).`,
    needs_backend_or_credentials: false,
    audit_backed: lifecycleReady,
    next_action: lifecycleReady
      ? "Add hosted auth mode and persistent audit rows before exposing customer links publicly."
      : "Create one hosted report from the dashboard and verify revoke/expiry/audit display."
  });
}

function capability(value = {}) {
  return {
    id: value.id,
    label: value.label,
    status: value.status,
    evidence: value.evidence,
    api_or_surface: value.api_or_surface,
    dashboard_value: value.dashboard_value,
    needs_backend_or_credentials: value.needs_backend_or_credentials === true,
    audit_backed: value.audit_backed === true,
    live_external_mutation_observed: value.live_external_mutation_observed === true,
    next_action: value.next_action
  };
}

function nextActions(capabilities = []) {
  return capabilities
    .filter((item) => item.status !== "live_posted" && item.status !== "lifecycle_ready")
    .map((item) => item.next_action)
    .filter(Boolean)
    .slice(0, 3);
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
