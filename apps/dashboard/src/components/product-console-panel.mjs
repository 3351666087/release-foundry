export function renderProductConsolePanel(target, productConsole = {}) {
  if (!target) {
    return;
  }

  target.replaceChildren(
    summaryBlock(productConsole),
    metricGrid(productConsole),
    onboardingBlock(productConsole.onboarding || {}),
    projectBlock(productConsole.project_console || {}),
    operationsLoopBlock(productConsole.project_console?.operations_summary || {}),
    goToMarketBlock(productConsole.go_to_market || {}),
    auditBlock(productConsole.audit_log || {}),
    readinessBlock(productConsole.commercial_readiness || {})
  );
}

function summaryBlock(productConsole) {
  const node = document.createElement("div");
  node.className = "caption";
  const tenant = productConsole.tenant_scope || {};
  node.textContent = `${tenant.organization_id || "org-local"} / ${tenant.project_id || "project-local"} / ${productConsole.source || "mock"} product workflow. Read-only SaaS shell; no real cloud mutation.`;
  return node;
}

function metricGrid(productConsole) {
  const onboarding = productConsole.onboarding || {};
  const project = productConsole.project_console || {};
  const audit = productConsole.audit_log || {};
  const readiness = productConsole.commercial_readiness || {};
  const rows = [
    ["Onboarding", `${onboarding.completion_rate ?? 0}%`],
    ["Project", project.status || "unknown"],
    ["Audit events", String(audit.event_count || 0)],
    ["Readiness", `${readiness.readiness_score ?? 0}`]
  ];
  const grid = document.createElement("div");
  grid.className = "health-grid";
  grid.replaceChildren(...rows.map(([label, value]) => {
    const tile = document.createElement("div");
    tile.className = "health-tile";
    tile.innerHTML = `<strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span>`;
    return tile;
  }));
  return grid;
}

function onboardingBlock(onboarding) {
  const block = section("Onboarding Flow", [
    miniRow("Status", onboarding.status || "unknown"),
    miniRow("Completed", `${onboarding.completed_steps || 0}/${onboarding.total_steps || 0}`),
    miniRow("Paths", (onboarding.paths || []).map((item) => item.label).join(", ") || "none")
  ]);
  for (const step of onboarding.steps || []) {
    block.appendChild(row(step.label, step.status, step.evidence, step.status === "complete" ? "pass" : "warn"));
  }
  return block;
}

function projectBlock(project) {
  const summary = project.summary || {};
  const block = section("Project Console", [
    miniRow("Status", project.status || "unknown"),
    miniRow("Runs", String(summary.run_count || 0)),
    miniRow("Cases", String(summary.case_count || 0)),
    miniRow("Failed", String(summary.failed_case_count || 0)),
    miniRow("Reports", String(project.report_snapshot?.report_count || 0))
  ]);
  for (const action of project.primary_actions || []) {
    block.appendChild(row(action.action, action.mode, action.reason, action.enabled ? "pass" : "neutral"));
  }
  for (const failure of project.failure_classes || []) {
    block.appendChild(row(failure.failure_class, `${failure.count} case(s)`, "Failure class requiring triage.", "warn"));
  }
  return block;
}

function operationsLoopBlock(summary) {
  return section("Operations Loop", [
    miniRow("Review records", String(summary.review_record_count || 0)),
    miniRow("Shareable reports", String(summary.shareable_report_count || 0)),
    miniRow("Manifest-ready", String(summary.manifest_ready_count || 0)),
    miniRow("Notification lanes", `${summary.notification_channel_count || 0} / ${summary.notification_contract_ready_count || 0} ready`),
    row("Why it matters", "loop", summary.why_it_matters || "Failed runs, reviewer actions, hosted reports, and notifications should stay visible together.", "info")
  ]);
}

function goToMarketBlock(summary) {
  const block = section("Go-To-Market", [
    miniRow("Status", summary.status || "unknown"),
    miniRow("Motion", summary.strongest_motion || "unknown"),
    miniRow("Hosted reports", String(summary.revenue_signals?.hosted_reports || 0)),
    miniRow("Review records", String(summary.revenue_signals?.review_records || 0)),
    miniRow("Notification lanes", String(summary.revenue_signals?.notification_lanes || 0)),
    miniRow("Billable meters", String(summary.revenue_signals?.billable_meters || 0))
  ]);
  for (const item of summary.buyer_value || []) {
    block.appendChild(row("Buyer value", "sellable", item, "info"));
  }
  for (const item of summary.next_sales_moves || []) {
    block.appendChild(row("Next", "sales", item, "neutral"));
  }
  return block;
}

function auditBlock(audit) {
  const block = section("Audit Log", [
    miniRow("Status", audit.status || "empty"),
    miniRow("Events", String(audit.event_count || 0)),
    miniRow("Payload policy", audit.redacted_payload_only ? "redacted only" : "unknown"),
    miniRow("Missing", (audit.missing_required_events || []).join(", ") || "none")
  ]);
  for (const event of audit.events || []) {
    block.appendChild(row(event.event_type, event.result, `${event.subject_id} / ${event.created_at}`, event.result === "allowed" || event.result === "recorded" ? "pass" : "neutral"));
  }
  return block;
}

function readinessBlock(readiness) {
  const block = section("Commercial Readiness", [
    miniRow("Status", readiness.status || "unknown"),
    miniRow("Score", String(readiness.readiness_score ?? 0)),
    miniRow("Money path", readiness.strongest_money_path || "unknown")
  ]);
  for (const check of readiness.checks || []) {
    block.appendChild(row(check.id, check.status, check.passed ? "Evidence available." : "Evidence missing.", check.passed ? "pass" : "warn"));
  }
  for (const action of readiness.next_commercial_moves || []) {
    block.appendChild(row("Next", "growth", action, "info"));
  }
  return block;
}

function section(title, children) {
  const block = document.createElement("div");
  block.className = "matrix-list";
  const header = document.createElement("div");
  header.className = "section-kicker";
  header.textContent = title;
  block.appendChild(header);
  block.append(...children);
  return block;
}

function miniRow(label, value) {
  const node = document.createElement("div");
  node.className = "mini-row";
  node.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return node;
}

function row(label, badge, detail, badgeClass) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(label)}</strong>
      <span class="badge ${escapeHtml(badgeClass)}">${escapeHtml(badge)}</span>
    </div>
    <div class="muted">${escapeHtml(detail || "")}</div>
  `;
  return node;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function governanceLoopBlock(summary, audit, readiness) {
  return section("Commercial Governance Loop", [
    miniRow("Review records", String(summary.review_record_count || 0)),
    miniRow("Shareable reports", String(summary.shareable_report_count || 0)),
    miniRow("Manifest-ready", String(summary.manifest_ready_count || 0)),
    miniRow("Audit events", String(audit.event_count || 0)),
    miniRow("Readiness", String(readiness.readiness_score || 0)),
    row("Why it matters", "governance", "GitHub publish, reviewer sign-off, hosted evidence, and audit retention need to read like one operator workflow.", "info")
  ]);
}
