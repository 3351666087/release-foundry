export const A3_BILLING_READINESS_SCHEMA_VERSION = "a3.billing_readiness.v1";

const DEFAULT_BILLING_THRESHOLDS = {
  runs: 1000,
  cases: 10000,
  trace_events: 100000,
  judge_results: 10000,
  media_evidence_cases: 1000,
  shareable_reports: 500,
  report_views: 5000,
  release_evidence_readbacks: 1000,
  api_imports: 5000
};

export function buildA3BillingReadiness(inputs = {}, options = {}) {
  const usageLedger = inputs.usageLedger || inputs.usage_ledger || {};
  const adminConsole = inputs.adminConsole || inputs.saasAdminConsole || inputs.saas_admin_console || {};
  const thresholds = { ...DEFAULT_BILLING_THRESHOLDS, ...(options.thresholds || {}) };
  const meters = Array.isArray(usageLedger.meters) ? usageLedger.meters : [];
  const billableMeters = meters.filter((item) => item.billable !== false);
  const blockedPaidActions = collectBlockedPaidActions(adminConsole);
  const tenantScope = {
    organization_id: options.organizationId
      || usageLedger.tenant_scope?.organization_id
      || adminConsole.organization?.organization_id
      || "org-local",
    project_id: options.projectId
      || usageLedger.tenant_scope?.project_id
      || adminConsole.project?.project_id
      || "project-local"
  };
  const a1Ready = meterQuantity(meters, "runs") > 0
    && meterQuantity(meters, "trace_events") > 0;
  const a2Ready = meterQuantity(meters, "judge_results") > 0;
  const hostedReportReady = meterQuantity(meters, "shareable_reports") > 0;
  const reviewEvidenceReady = meterQuantity(meters, "release_evidence_readbacks") > 0
    || hasActionArea(adminConsole, "trust");
  const blockedForRealBilling = [
    !adminConsole.login?.rbac_boundary?.enforced_now,
    adminConsole.usage?.billing_mutations_enabled !== false ? false : true,
    !usageLedger.meters,
    blockedPaidActions.length > 0
  ].filter(Boolean).length;

  return {
    schema_version: A3_BILLING_READINESS_SCHEMA_VERSION,
    source: options.source || usageLedger.source || adminConsole.source || "mock",
    tenant_scope: tenantScope,
    status: blockedForRealBilling > 0 ? "read_only_contract_ready" : "billing_mutation_ready",
    billing_mutations_enabled: false,
    provider_boundary: {
      provider_mode: "not_configured",
      supported_future_providers: ["wechat_pay", "alipay", "manual_invoice", "stripe"],
      checkout_enabled: false,
      billing_portal_enabled: false,
      invoice_export_enabled: true,
      secret_values_required_in_ui: false
    },
    plan_readiness: {
      current_plan: adminConsole.organization?.plan || "local_dev",
      recommended_next_plan: recommendedPlan(meters, hostedReportReady, reviewEvidenceReady),
      quota_policy_ready: true,
      overage_policy_ready: true,
      customer_invoice_ready: false,
      reason: "A3 can compute read-only meters and invoice lines, but real billing needs hosted auth, A1 ledger enforcement, provider webhooks, and a China-first payment path with WeChat Pay and Alipay before secondary international providers."
    },
    billable_meter_count: billableMeters.length,
    billable_unit_count: billableMeters.reduce((sum, item) => sum + Number(item.quantity || 0), 0),
    meters: meters.map((item) => billingMeter(item, thresholds)),
    quota_exposure: meters
      .map((item) => billingMeter(item, thresholds))
      .filter((item) => item.quota_state !== "untracked"),
    invoice_preview: buildInvoicePreview(billableMeters),
    blocked_paid_actions: blockedPaidActions,
    a1_a2_alignment: {
      a1_usage_source_ready: a1Ready,
      a1_run_meter_quantity: meterQuantity(meters, "runs"),
      a1_trace_meter_quantity: meterQuantity(meters, "trace_events"),
      a2_judge_meter_ready: a2Ready,
      a2_judge_meter_quantity: meterQuantity(meters, "judge_results"),
      hosted_report_meter_ready: hostedReportReady,
      review_evidence_meter_ready: reviewEvidenceReady,
      contract_note: "Billing readiness consumes A1/A2-derived A3 usage meters without changing A1 runner or A2 judge semantics."
    },
    required_api_contracts: [
      "GET /api/a3/usage/ledger",
      "GET /api/a3/billing/readiness",
      "GET /api/a3/admin/console",
      "future GET /v1/usage",
      "future GET /v1/billing/subscription",
      "future POST /v1/billing/checkout",
      "future POST /v1/billing/portal"
    ],
    required_db_contracts: [
      "usage_ledger",
      "usage_events",
      "usage_rollups",
      "quota_policies",
      "billing_customers",
      "billing_subscriptions",
      "billing_invoices",
      "audit_events"
    ],
    required_events: [
      "usage.recorded",
      "quota.exceeded",
      "billing.subscription_changed",
      "audit_event.created"
    ],
    audit: {
      tenant_scoped: true,
      raw_private_payload_logged: false,
      invoice_line_items_public_safe: true,
      usage_source: usageLedger.schema_version || "unknown",
      admin_guardrails_source: adminConsole.schema_version || "unknown"
    },
    next_actions: nextBillingActions({ a1Ready, a2Ready, hostedReportReady, reviewEvidenceReady, blockedPaidActions }),
    safety: {
      real_payment_provider_called: false,
      real_billing_mutation_performed: false,
      raw_customer_email_required: false,
      raw_api_key_required: false,
      secret_values_included: false
    }
  };
}

function billingMeter(item = {}, thresholds = {}) {
  const quantity = Number(item.quantity || 0);
  const threshold = thresholds[item.meter] || 0;
  return {
    meter: item.meter || "unknown",
    quantity,
    billable: item.billable !== false,
    description: item.description || "",
    quota_threshold: threshold || null,
    quota_state: threshold
      ? quantity >= threshold
        ? "over_quota"
        : quantity >= threshold * 0.8
          ? "near_quota"
          : "within_quota"
      : "untracked",
    invoice_category: invoiceCategory(item.meter)
  };
}

function buildInvoicePreview(meters = []) {
  return {
    schema_version: "a3.invoice_preview.v1",
    status: "preview_only",
    currency: "USD",
    line_items: meters.map((item) => ({
      meter: item.meter,
      quantity: Number(item.quantity || 0),
      unit_label: invoiceCategory(item.meter),
      amount_usd: null,
      pricing_source: "not_configured"
    })),
    total_amount_usd: null,
    ready_for_customer_invoice: false
  };
}

function collectBlockedPaidActions(adminConsole = {}) {
  const actions = Array.isArray(adminConsole.actions) ? adminConsole.actions : [];
  return actions
    .filter((item) => ["usage", "api_keys", "team", "trust", "cloud_management"].includes(item.area))
    .filter((item) => item.enabled === false || item.mode === "plan_only" || item.mode === "mock_only")
    .map((item) => ({
      action: item.action,
      area: item.area,
      mode: item.mode,
      risk: item.risk,
      next_step: item.next_step
    }));
}

function hasActionArea(adminConsole = {}, area) {
  return Array.isArray(adminConsole.actions)
    && adminConsole.actions.some((item) => item.area === area);
}

function meterQuantity(meters, name) {
  return Number(meters.find((item) => item.meter === name)?.quantity || 0);
}

function recommendedPlan(meters, hostedReportReady, reviewEvidenceReady) {
  const cases = meterQuantity(meters, "cases");
  const judgeResults = meterQuantity(meters, "judge_results");
  if (hostedReportReady && reviewEvidenceReady && judgeResults > 0) {
    return "team";
  }
  if (cases > 0 || judgeResults > 0) {
    return "student";
  }
  return "free";
}

function nextBillingActions(context = {}) {
  const actions = [];
  if (!context.a1Ready) {
    actions.push("Ask A1 for authoritative usage_events and usage_rollups persisted in Postgres.");
  }
  if (!context.a2Ready) {
    actions.push("Ask A2 to keep judge_results and cost policy fields stable for billing display.");
  }
  if (!context.hostedReportReady) {
    actions.push("Create or import at least one hosted report before invoice preview is useful.");
  }
  if (!context.reviewEvidenceReady) {
    actions.push("Connect review evidence or readback receipts so paid audit value is visible.");
  }
  if (context.blockedPaidActions?.length) {
    actions.push("Keep paid mutations disabled until hosted auth, RBAC, audit events, and provider webhooks exist.");
  }
  actions.push("Prioritize WeChat Pay and Alipay before secondary international checkout providers.");
  actions.push("Add provider-backed checkout only after A1 owns billing ledger and webhook verification.");
  return actions;
}

function invoiceCategory(meter) {
  const categories = {
    runs: "run",
    cases: "case",
    trace_events: "trace event",
    tool_call_cases: "tool-call case",
    judge_results: "judge result",
    media_evidence_cases: "media evidence case",
    shareable_reports: "hosted report",
    report_views: "report view",
    report_revocations: "report revocation",
    release_evidence_readbacks: "release evidence readback",
    api_imports: "API import"
  };
  return categories[meter] || "usage unit";
}
