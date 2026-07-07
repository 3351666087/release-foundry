import {
  buildDashboardSummary,
  normalizeCases
} from "./report_builder.mjs";

export const A3_USAGE_LEDGER_SCHEMA_VERSION = "a3.usage_ledger.v1";

export function buildA3UsageLedger(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const reports = Array.isArray(options.reports) ? options.reports : [];
  const auditEvents = Array.isArray(options.auditEvents) ? options.auditEvents : [];
  const importReceipts = Array.isArray(options.importReceipts) ? options.importReceipts : [];
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
    meter("report_views", auditEvents.filter((item) => item.event_type === "report_view").length, "Hosted report view events"),
    meter("report_revocations", auditEvents.filter((item) => item.event_type === "report_revoke").length, "Hosted report revocation events"),
    meter("api_imports", importReceipts.length, "A1/A2 API import receipts")
  ];

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
    meters,
    billable_unit_count: meters.reduce((sum, item) => sum + item.quantity, 0),
    high_value_meters: meters
      .filter((item) => ["failed_cases", "judge_results", "shareable_reports", "report_views", "api_imports"].includes(item.meter))
      .map((item) => item.meter),
    commercial_note: "Usage ledger is read-only until hosted billing, RBAC, and customer plan controls exist."
  };
}

function meter(name, quantity, description) {
  return {
    meter: name,
    quantity: Number(quantity || 0),
    description,
    billable: !["failed_cases"].includes(name)
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
