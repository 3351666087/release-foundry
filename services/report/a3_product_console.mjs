import {
  buildDashboardSummary,
  normalizeCases
} from "./report_builder.mjs";

export const A3_PRODUCT_CONSOLE_SCHEMA_VERSION = "a3.product_console.v1";

export function buildA3ProductConsole(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const cases = normalizeCases(runFixture, gradeFixture);
  const usageLedger = options.usageLedger || inputs.usageLedger || {};
  const reportCenter = options.reportCenter || inputs.reportCenter || {};
  const reviewWorkflow = options.reviewWorkflow || inputs.reviewWorkflow || {};
  const notificationControlPlane = options.notificationControlPlane || inputs.notificationControlPlane || {};
  const auditEvents = Array.isArray(options.auditEvents) ? options.auditEvents : [];
  const importReceipts = Array.isArray(options.importReceipts) ? options.importReceipts : [];
  const source = options.source || inputs.source || "mock";
  const organizationId = options.organizationId || inputs.organizationId || "org-local";
  const projectId = options.projectId || inputs.projectId || "project-local";

  return {
    schema_version: A3_PRODUCT_CONSOLE_SCHEMA_VERSION,
    source,
    tenant_scope: {
      organization_id: organizationId,
      project_id: projectId
    },
    onboarding: buildOnboarding(summary, cases, usageLedger, reportCenter, importReceipts),
    project_console: buildProjectConsole(summary, cases, usageLedger, reportCenter, reviewWorkflow, notificationControlPlane, source, projectId),
    go_to_market: buildGoToMarketSummary(summary, reportCenter, reviewWorkflow, notificationControlPlane, usageLedger),
    audit_log: buildAuditLog(auditEvents, importReceipts, reportCenter),
    commercial_readiness: buildCommercialReadiness(summary, cases, usageLedger, reportCenter, reviewWorkflow, notificationControlPlane, auditEvents)
  };
}

function buildOnboarding(summary, cases, usageLedger, reportCenter, importReceipts) {
  const steps = [
    onboardingStep("create_project", "Create project", true, "Local tenant/project contract is available."),
    onboardingStep("choose_ingestion", "Choose ingestion path", true, "A3 supports fixture, raw A1/A2, and API-backed sources."),
    onboardingStep("submit_first_run", "Submit first run", summary.totalRuns > 0, `${summary.totalRuns || 0} run(s) loaded.`),
    onboardingStep("attach_judge_results", "Attach A2 judge results", cases.some((item) => (item.judge_results || []).length > 0 || item.grade), "A2 grade evidence joins by case id."),
    onboardingStep("review_failures", "Review failures", summary.totalCases > 0, `${summary.failed || 0} failed case(s) need triage.`),
    onboardingStep("create_hosted_report", "Create hosted report", (reportCenter.summary?.report_count || 0) > 0, `${reportCenter.summary?.report_count || 0} hosted report(s).`),
    onboardingStep("connect_release_gate", "Connect release gate", summary.totalCases > 0 && summary.traceCompleteness >= 0, "Release gate can evaluate normalized A1/A2 evidence."),
    onboardingStep("invite_reviewer", "Invite reviewer", false, "Plan-only until hosted auth and email invite service exist."),
    onboardingStep("set_usage_budget", "Set usage budget", false, "Read-only usage ledger exists; billing mutation is disabled."),
    onboardingStep("download_audit_bundle", "Download audit bundle", importReceipts.length > 0 || (reportCenter.summary?.manifest_ready_count || 0) > 0, "Audit bundle readiness depends on imports or hosted report manifests.")
  ];
  const completed = steps.filter((item) => item.status === "complete").length;

  return {
    status: completed >= 7 ? "ready_for_team_trial" : completed >= 4 ? "partially_onboarded" : "setup_required",
    completed_steps: completed,
    total_steps: steps.length,
    completion_rate: Math.round((completed / steps.length) * 100),
    paths: [
      onboardingPath("upload_json", "Upload JSON", ["choose_ingestion", "submit_first_run", "attach_judge_results"]),
      onboardingPath("python_sdk", "Python SDK", ["choose_ingestion", "submit_first_run", "connect_release_gate"]),
      onboardingPath("github_action", "GitHub Action", ["choose_ingestion", "connect_release_gate", "download_audit_bundle"])
    ],
    steps,
    next_actions: steps.filter((item) => item.status !== "complete").slice(0, 4).map((item) => item.next_action)
  };
}

function buildProjectConsole(summary, cases, usageLedger, reportCenter, reviewWorkflow, notificationControlPlane, source, projectId) {
  const failures = cases.filter((item) => !item.passed);
  const failureClasses = countBy(failures, (item) => item.primary_failure_class || "unknown");
  const runs = countBy(cases, (item) => item.run_id || "unknown");
  const meters = Array.isArray(usageLedger.meters) ? usageLedger.meters : [];
  const workflowRecords = Number(reviewWorkflow.record_count || 0);
  const notificationSummary = notificationControlPlane.summary || {};

  return {
    project_id: projectId,
    display_name: source === "mock" ? "A3 Release Intelligence" : `A3 ${source}`,
    environment: "staging",
    status: summary.failed > 0 ? "needs_triage" : summary.totalCases > 0 ? "release_candidate" : "empty",
    summary: {
      run_count: summary.totalRuns,
      case_count: summary.totalCases,
      failed_case_count: summary.failed,
      pass_rate: summary.passRate,
      average_score: summary.avgScore,
      trace_completeness: summary.traceCompleteness,
      media_evidence_cases: summary.mediaEvidenceCases
    },
    recent_runs: Object.entries(runs).slice(0, 6).map(([runId, count]) => ({
      run_id: runId,
      case_count: count,
      failed_case_count: cases.filter((item) => item.run_id === runId && !item.passed).length
    })),
    failure_classes: Object.entries(failureClasses).map(([failureClass, count]) => ({
      failure_class: failureClass,
      count
    })),
    usage_snapshot: {
      meter_count: meters.length,
      billable_unit_count: usageLedger.billable_unit_count || 0,
      high_value_meters: usageLedger.high_value_meters || []
    },
    report_snapshot: {
      report_count: reportCenter.summary?.report_count || 0,
      manifest_ready_count: reportCenter.summary?.manifest_ready_count || 0,
      total_view_count: reportCenter.summary?.total_view_count || 0
    },
    operations_summary: {
      review_record_count: workflowRecords,
      shareable_report_count: reportCenter.summary?.shareable_count || 0,
      manifest_ready_count: reportCenter.summary?.manifest_ready_count || 0,
      notification_channel_count: notificationSummary.channel_count || 0,
      notification_contract_ready_count: notificationSummary.contract_ready_count || 0,
      why_it_matters: "Product console value increases when failed runs, reviewer actions, hosted reports, and notification lanes are visible together."
    },
    primary_actions: [
      projectAction("open_triage", failures.length > 0, `${failures.length} failed case(s) need owner review.`),
      projectAction("create_report", summary.totalCases > 0, "Package current release evidence into a hosted report."),
      projectAction("request_reviewer", failures.length > 0, "Route blocking failures to reviewer workflow."),
      projectAction("promote_regression", failures.length > 0, "Turn high-risk failures into regression replay candidates.")
    ]
  };
}

function buildGoToMarketSummary(summary, reportCenter, reviewWorkflow, notificationControlPlane, usageLedger) {
  const reportSummary = reportCenter.summary || {};
  const notificationSummary = notificationControlPlane.summary || {};
  const meters = Array.isArray(usageLedger.meters) ? usageLedger.meters : [];
  const reviewCount = Number(reviewWorkflow.record_count || 0);
  return {
    status: reportSummary.shareable_count > 0 && reviewCount > 0 ? "field_sellable" : "internal_trial_only",
    strongest_motion: reportSummary.shareable_count > 0 ? "audit_report_center" : "release_gate_console",
    buyer_value: [
      "Block risky releases before production.",
      "Package replay, judge, and audit evidence into one customer-facing report.",
      "Give reviewers and operators one shared sign-off surface."
    ],
    revenue_signals: {
      hosted_reports: reportSummary.shareable_count || 0,
      review_records: reviewCount,
      notification_lanes: notificationSummary.channel_count || 0,
      billable_meters: meters.length
    },
    next_sales_moves: [
      "Show one hosted report with release evidence during product demo.",
      "Connect review workflow output to release sign-off language.",
      "Attach usage meter language to plan and quota packaging."
    ]
  };
}

function buildAuditLog(auditEvents, importReceipts, reportCenter) {
  const importEvents = importReceipts.map((receipt, index) => ({
    event_id: `import_${index + 1}`,
    event_type: receipt.schema_version || "api_import",
    subject_id: receipt.source || "api-ingest",
    result: receipt.idempotency?.status || "recorded",
    created_at: "runtime",
    redacted: true
  }));
  const reportEvents = (reportCenter.reports || []).map((report, index) => ({
    event_id: `report_center_${index + 1}`,
    event_type: "report_center_indexed",
    subject_id: report.report_id,
    result: report.status,
    created_at: report.created_at || "runtime",
    redacted: true
  }));
  const rawEvents = auditEvents.map((event, index) => ({
    event_id: event.event_id || `audit_${index + 1}`,
    event_type: event.event_type || "audit_event",
    subject_id: event.report_id || event.subject_id || "redacted",
    result: event.access_result || event.status || "recorded",
    created_at: event.viewed_at || event.revoked_at || event.created_at || "runtime",
    redacted: true
  }));
  const events = [...rawEvents, ...importEvents, ...reportEvents];
  const eventCounts = countBy(events, (item) => item.event_type);

  return {
    status: events.length ? "evidence_available" : "empty",
    event_count: events.length,
    redacted_payload_only: true,
    event_types: Object.entries(eventCounts).map(([eventType, count]) => ({ event_type: eventType, count })),
    events: events.slice(-20),
    required_events: [
      "api_import",
      "report_share_link_viewed",
      "report_view",
      "report_revoke",
      "review_approval",
      "waiver_decision",
      "api_key_rotation"
    ],
    missing_required_events: [
      "review_approval",
      "waiver_decision",
      "api_key_rotation"
    ].filter((eventType) => !eventCounts[eventType])
  };
}

function buildCommercialReadiness(summary, cases, usageLedger, reportCenter, reviewWorkflow, notificationControlPlane, auditEvents) {
  const hasA1 = summary.totalRuns > 0 && cases.some((item) => item.trace_ready || (item.trace_events || []).length > 0);
  const hasA2 = cases.some((item) => (item.judge_results || []).length > 0 || item.grade);
  const hasReports = (reportCenter.summary?.report_count || 0) > 0;
  const hasUsage = Array.isArray(usageLedger.meters) && usageLedger.meters.length > 0;
  const hasAudit = auditEvents.length > 0 || hasReports;
  const hasReviewWorkflow = Number(reviewWorkflow.record_count || 0) > 0;
  const hasNotifications = Number(notificationControlPlane.summary?.channel_count || 0) > 0;
  const checks = [
    readinessCheck("a1_trace_ingestion", hasA1),
    readinessCheck("a2_judge_join", hasA2),
    readinessCheck("project_console", summary.totalCases > 0),
    readinessCheck("hosted_report", hasReports),
    readinessCheck("usage_meter", hasUsage),
    readinessCheck("audit_log", hasAudit),
    readinessCheck("review_workflow", hasReviewWorkflow),
    readinessCheck("notification_control_plane", hasNotifications)
  ];
  const passed = checks.filter((item) => item.passed).length;

  return {
    status: passed >= 5 ? "commercial_demo_ready" : "needs_more_real_evidence",
    readiness_score: Math.round((passed / checks.length) * 100),
    checks,
    strongest_money_path: hasReports && hasAudit ? "enterprise_audit_report_center" : "api_backed_release_gate",
    next_commercial_moves: [
      "Back this product console with real tenant auth.",
      "Persist audit events in SQL instead of memory/file state.",
      "Attach GitHub PR checks to release gate decisions.",
      "Add billing plan and quota enforcement behind the usage ledger."
    ]
  };
}

function onboardingStep(id, label, complete, evidence) {
  return {
    id,
    label,
    status: complete ? "complete" : "pending",
    evidence,
    next_action: complete ? "No action needed." : `Complete onboarding step: ${label}.`
  };
}

function onboardingPath(id, label, stepIds) {
  return {
    id,
    label,
    step_ids: stepIds
  };
}

function projectAction(action, enabled, reason) {
  return {
    action,
    enabled,
    mode: enabled ? "available" : "blocked",
    reason
  };
}

function readinessCheck(id, passed) {
  return {
    id,
    passed,
    status: passed ? "passed" : "missing"
  };
}

function countBy(items, keyFn) {
  return items.reduce((counts, item) => {
    const key = keyFn(item);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}
