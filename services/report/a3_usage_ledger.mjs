import {
  buildDashboardSummary,
  normalizeCases,
  summarizeBillingUsage
} from "./report_builder.mjs";

export const A3_USAGE_LEDGER_SCHEMA_VERSION = "a3.usage_ledger.v1";

export function buildA3UsageLedger(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const reports = Array.isArray(options.reports) ? options.reports : [];
  const auditEvents = Array.isArray(options.auditEvents) ? options.auditEvents : [];
  const releaseEvidenceReadbacks = Array.isArray(options.releaseEvidenceReadbacks) ? options.releaseEvidenceReadbacks : [];
  const importReceipts = Array.isArray(options.importReceipts) ? options.importReceipts : [];
  const usageFixture = inputs.usageFixture || inputs.usage || {};
  const usageApiProbe = inputs.usageApiProbe || inputs.usageProbe || {};
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const periodStart = options.periodStart || "local";
  const periodEnd = options.periodEnd || "runtime";

  const meters = [
    meter("runs", summary.totalRuns, "A1 submitted run batches"),
    meter("cases", summary.totalCases, "Normalized A3 cases"),
    meter("failed_cases", summary.failed, "Cases requiring triage"),
    meter("trace_events", countTraceEvents(cases), "A1 trace and observation events"),
    meter("tool_call_cases", cases.filter((item) => hasToolCalls(item)).length, "Cases containing expected or actual tool calls"),
    meter("judge_results", countJudgeResults(cases), "A2 judge result entries"),
    meter("media_evidence_cases", summary.mediaEvidenceCases || 0, "Cases with media evidence metadata"),
    meter("shareable_reports", reports.length, "Hosted report payloads"),
    meter("report_views", auditEvents.filter((item) => item.event_type === "report_view" || item.event_type === "report_share_link_viewed").length, "Hosted report view and share-link access events"),
    meter("report_revocations", auditEvents.filter((item) => item.event_type === "report_revoke").length, "Hosted report revocation events"),
    meter("release_evidence_readbacks", releaseEvidenceReadbacks.length || auditEvents.filter((item) => item.event_type === "release_evidence.readback_captured").length, "GitHub Check, PR comment, and required-check readback receipts"),
    meter("api_imports", importReceipts.length, "A1/A2 API import receipts")
  ];
  const billingUsageSummary = summarizeBillingUsage(runFixture, gradeFixture, usageFixture, usageApiProbe, {
    meters,
    plan: options.plan || inputs.plan || inputs.billingPlan,
    quota: options.quota || inputs.quota,
    billingPeriod: options.billingPeriod,
    currency: options.currency,
    overageEnabled: options.overageEnabled
  });

  return {
    schema_version: A3_USAGE_LEDGER_SCHEMA_VERSION,
    tenant_scope: {
      organization_id: options.organizationId || inputs.organizationId || "org-local",
      project_id: options.projectId || inputs.projectId || "project-local"
    },
    period: {
      start: periodStart,
      end: periodEnd
    },
    status: "read_only_meter",
    billing_mutations_enabled: false,
    plan: billingUsageSummary.plan,
    quota: billingUsageSummary.quota,
    meters,
    billable_meter: billingUsageSummary.billable_meter,
    billable_meters: billingUsageSummary.billable_meters,
    billable_unit_count: billingUsageSummary.billable_unit_count,
    overage_risk: billingUsageSummary.overage_risk,
    evidence_counts: billingUsageSummary.evidence_counts,
    billing_usage_summary: billingUsageSummary,
    high_value_meters: meters
      .filter((item) => ["failed_cases", "judge_results", "shareable_reports", "report_views", "release_evidence_readbacks", "api_imports"].includes(item.meter))
      .map((item) => item.meter),
    commercial_note: "Usage ledger is read-only until hosted billing, RBAC, customer plan controls, and quota enforcement exist."
  };
}

function meter(name, quantity, description) {
  const normalizedQuantity = Number(quantity || 0);
  const billable = !["failed_cases", "trace_events", "tool_call_cases"].includes(name);
  return {
    meter: name,
    quantity: normalizedQuantity,
    unit: "unit",
    description,
    billable,
    billable_units: billable ? normalizedQuantity : 0,
    billable_weight: 1
  };
}

function countTraceEvents(cases) {
  return cases.reduce((sum, item) => (
    sum
    + (Array.isArray(item.trace_events) ? item.trace_events.length : 0)
    + (Array.isArray(item.observations) ? item.observations.length : 0)
  ), 0);
}

function countJudgeResults(cases) {
  return cases.reduce((sum, item) => {
    if (Array.isArray(item.judge_results) && item.judge_results.length) {
      return sum + item.judge_results.length;
    }
    return item.grade ? sum + 1 : sum;
  }, 0);
}

function hasToolCalls(item) {
  return (item.expected?.tool_calls || []).length > 0
    || (item.actual?.tool_calls || []).length > 0;
}
