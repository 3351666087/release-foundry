/**
 * Presentation contract for normalized `a3.report_center_index.v1` data.
 * API/DB mutation, auth/RBAC decisions, usage metering, and audit recording stay
 * with the caller; this component only emits create/revoke/export intent. A1
 * runtime/billing/storage fields and A2 release decisions are read-only here.
 */
export function renderReportCenterPanel(target, model = {}, callbacks = {}, options = {}) {
  if (!target || typeof target.replaceChildren !== "function") {
    throw new TypeError("Report Center target must be a DOM element.");
  }

  const documentNode = target.ownerDocument || globalThis.document;
  if (!documentNode || typeof documentNode.createElement !== "function") {
    throw new TypeError("Report Center requires a DOM document.");
  }

  const reports = array(model.reports);
  const registry = model.artifact_registry || {};
  const shell = element(documentNode, "section", "report-center-panel");
  shell.setAttribute("data-component", "report-center-panel");
  shell.replaceChildren(
    renderHeader(documentNode, reports, model.summary || {}, callbacks, options),
    renderAudienceGovernance(documentNode, model.export_audience_governance || {}, model.audience_filters || {}),
    renderScopeGroups(documentNode, model.workspace_groups || {}, model.environment_groups || {}, model.tenant_scope || {}),
    renderExternalBlockers(documentNode, model.external_publish_blockers || {}),
    renderSignoff(documentNode, model.release_signoff_summary || {}, model.release_signoff_detail || {}),
    renderReports(documentNode, reports, callbacks),
    renderArtifactRegistry(documentNode, registry)
  );
  target.replaceChildren(shell);
  return shell;
}

function renderHeader(documentNode, reports, summary, callbacks, options) {
  const block = element(documentNode, "header", "report-center-header");
  const title = textElement(documentNode, "h3", "Report Center");
  const status = textElement(
    documentNode,
    "span",
    reports.length ? `${reports.length} hosted` : "No hosted reports",
    "badge info"
  );
  const metrics = textElement(
    documentNode,
    "div",
    `${number(summary.shareable_count)} shareable, ${number(summary.revoked_count)} revoked, ${number(summary.expired_count)} expired, ${number(summary.total_view_count)} total view(s).`,
    "muted"
  );
  block.replaceChildren(title, status, metrics);
  if (options.showHeaderActions !== false) {
    const actions = element(documentNode, "div", "report-actions");
    actions.replaceChildren(
      actionButton(documentNode, "Create hosted report", callbacks.create, modelEvent("create"), "button primary"),
      ...["json", "csv", "markdown", "print"].map((format) =>
        actionButton(documentNode, exportLabel(format), callbacks.export, format, "button secondary")
      )
    );
    block.append(actions);
  }
  return block;
}

function renderAudienceGovernance(documentNode, governance, filters) {
  const audiences = array(governance.audiences);
  const filterRows = array(filters.filters);
  const block = section(documentNode, "Audience Governance", "audience-governance");
  block.append(
    textElement(
      documentNode,
      "div",
      `${string(governance.status)}; default ${string(filters.default_filter, "internal_ops")}.`,
      "muted"
    ),
    rowList(documentNode, audiences, "No audience governance loaded.", (item) => {
      const state = item.allowed === true ? "allowed" : "blocked";
      return `${string(item.audience)}: ${state}. ${string(item.basis, "No basis loaded.")}`;
    }),
    textElement(documentNode, "strong", "Audience Filters"),
    rowList(documentNode, filterRows, "No audience filter counts loaded.", (item) =>
      `${string(item.audience)}: ${string(item.state)}, ${number(item.allowed_count)} allowed, ${number(item.blocked_count)} blocked.`
    )
  );
  return block;
}

function renderScopeGroups(documentNode, workspaceGroups, environmentGroups, tenantScope) {
  const block = section(documentNode, "Tenant Scope", "tenant-scope");
  block.append(
    textElement(
      documentNode,
      "div",
      ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"]
        .map((key) => string(tenantScope[key], "unknown"))
        .join(" / "),
      "muted"
    ),
    textElement(documentNode, "strong", "Workspace Groups"),
    rowList(documentNode, array(workspaceGroups.groups), "No workspace grouping yet.", (item) =>
      `${string(item.workspace_id)}: ${number(item.report_count)} report(s), ${number(item.shareable_count)} shareable, ${number(item.release_evidence_ready_count)} release-evidence-ready.`
    ),
    textElement(documentNode, "strong", "Environment Groups"),
    rowList(documentNode, array(environmentGroups.groups), "No environment grouping yet.", (item) =>
      `${string(item.environment_id)}: ${number(item.report_count)} report(s), ${number(item.shareable_count)} shareable, ${number(item.release_evidence_ready_count)} release-evidence-ready.`
    )
  );
  return block;
}

function renderExternalBlockers(documentNode, blockers) {
  const block = section(documentNode, "External Publish Blockers", "external-publish-blockers");
  block.append(
    textElement(
      documentNode,
      "div",
      `${string(blockers.status)}: ${number(blockers.blocker_count)} blocked report(s).`,
      "muted"
    ),
    rowList(documentNode, array(blockers.reasons), "No blocker reason loaded.", (reason) => string(reason)),
    rowList(documentNode, array(blockers.prerequisites), "No publish prerequisite loaded.", (item) => `Requires: ${string(item)}`)
  );
  return block;
}

function renderSignoff(documentNode, signoff, detail) {
  const checklist = array(detail.checklist);
  const passed = checklist.filter((item) => item.passed === true).length;
  const block = section(documentNode, "Release Sign-Off", "release-signoff");
  block.append(
    textElement(documentNode, "div", string(signoff.status), "badge neutral"),
    textElement(
      documentNode,
      "div",
      `${number(signoff.shareable_count)} shareable, ${number(signoff.release_evidence_ready_count)} release-evidence-ready, ${number(signoff.manifest_ready_count)} manifest-ready, usage ${signoff.usage_ready ? "ready" : "missing"}, migration ${signoff.migration_ready ? "ready" : "missing"}.`,
      "muted"
    ),
    textElement(documentNode, "div", `${passed}/${checklist.length} checklist item(s) passed.`, "muted"),
    rowList(documentNode, array(detail.recommendations), "No recommendation loaded.", (item) => string(item))
  );
  return block;
}

function renderReports(documentNode, reports, callbacks) {
  const block = section(documentNode, "Hosted Reports", "hosted-reports");
  if (!reports.length) {
    block.append(textElement(documentNode, "div", "No hosted reports yet.", "empty-state"));
    return block;
  }

  const list = element(documentNode, "div", "report-list");
  list.replaceChildren(...reports.map((report) => renderReport(documentNode, report, callbacks)));
  block.append(list);
  return block;
}

function renderReport(documentNode, report, callbacks) {
  const node = element(documentNode, "article", "matrix-row hosted-report-row");
  const audience = report.export_audience || {};
  const scope = report.tenant_scope || {};
  const manifest = report.manifest || {};
  const header = element(documentNode, "div", "matrix-head");
  header.replaceChildren(
    textElement(documentNode, "strong", string(report.title, string(report.report_id))),
    textElement(documentNode, "span", string(report.status), `badge ${reportStatusClass(report.status)}`)
  );
  node.append(
    header,
    textElement(documentNode, "div", `${string(report.report_id)} / ${string(report.share_url_path, "no share path")} / ${number(report.view_count)} view(s)`, "case-meta"),
    textElement(documentNode, "div", `${string(scope.workspace_id)} / ${string(scope.project_id)} / ${string(scope.environment_id)} / ${string(report.share_link?.scope, "private_link")}`, "case-meta"),
    textElement(documentNode, "div", `Audience ${join(audience.allowed)}; blocked ${join(audience.blocked)}; ${audience.customer_external_blocked ? "customer external blocked" : "external publish open"}.`, "case-meta"),
    textElement(documentNode, "div", `Manifest ${number(manifest.completeness_score)}%; ${string(report.redaction?.status)} redaction; ${report.release_evidence?.available ? "release evidence ready" : "release evidence missing"}; ${report.lifecycle?.view_audit_enabled ? "audit visible" : "audit missing"}.`, "case-meta"),
    textElement(documentNode, "div", array(manifest.missing).length ? `Missing: ${array(manifest.missing).map((item) => string(item)).join(", ")}` : "Manifest evidence is ready for release and audit linkage.", "muted")
  );

  const canRevoke = report.lifecycle?.revocable !== false && !["revoked", "expired"].includes(report.status);
  if (canRevoke) {
    const actions = element(documentNode, "div", "report-actions compact");
    actions.append(actionButton(documentNode, "Revoke", callbacks.revoke, report, "button danger"));
    node.append(actions);
  }
  return node;
}

function renderArtifactRegistry(documentNode, registry) {
  const summary = registry.summary || {};
  const block = section(documentNode, "Artifact Registry", "artifact-registry");
  block.append(
    textElement(documentNode, "div", string(registry.registry_status), "badge neutral"),
    textElement(documentNode, "div", `${number(summary.artifact_count)} artifact(s), ${number(summary.ready_count)} ready, ${number(summary.hash_ready_count)} hash-ready, ${number(summary.billable_meter_count)} billable meter(s).`, "muted"),
    rowList(documentNode, array(registry.entries).slice(0, 8), "No registered artifacts.", (entry) =>
      `${string(entry.artifact_type, string(entry.artifact_id))}: ${string(entry.lifecycle_state)}, ${string(entry.hash_status)}, ${string(entry.redaction_status)} redaction, ${string(entry.billable_meter, "no meter")}. ${string(entry.customer_value, "")}`
    )
  );
  return block;
}

function section(documentNode, title, name) {
  const node = element(documentNode, "section", "report-center-section");
  node.setAttribute("data-section", name);
  node.append(textElement(documentNode, "h4", title));
  return node;
}

function rowList(documentNode, items, emptyText, describe) {
  const list = element(documentNode, "div", "report-center-list");
  const rows = items.length
    ? items.map((item) => textElement(documentNode, "div", describe(item), "mini-row"))
    : [textElement(documentNode, "div", emptyText, "empty-state")];
  list.replaceChildren(...rows);
  return list;
}

function actionButton(documentNode, label, callback, payload, className) {
  const button = textElement(documentNode, "button", label, className);
  button.type = "button";
  button.disabled = typeof callback !== "function";
  if (typeof callback === "function") {
    button.addEventListener("click", () => callback(payload));
  }
  return button;
}

function element(documentNode, tagName, className = "") {
  const node = documentNode.createElement(tagName);
  node.className = className;
  return node;
}

function textElement(documentNode, tagName, value, className = "") {
  const node = element(documentNode, tagName, className);
  node.textContent = string(value, "");
  return node;
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function string(value, fallback = "unknown") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function join(value) {
  return array(value).length ? array(value).map((item) => string(item)).join(", ") : "none";
}

function exportLabel(format) {
  return format === "print" ? "Print/PDF" : format.toUpperCase();
}

function modelEvent(type) {
  return { type };
}

function reportStatusClass(status) {
  if (status === "shareable") return "pass";
  if (status === "blocked") return "fail";
  if (status === "expired" || status === "revoked") return "warn";
  return "neutral";
}
