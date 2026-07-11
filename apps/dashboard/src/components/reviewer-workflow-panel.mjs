const REVIEW_ACTIONS = ["approval", "denial", "waiver"];

export function renderReviewerWorkflowPanel(
  target,
  workflowOrOptions = {},
  reportCenter = {},
  activeFilter = {},
  selectedReceipt = null,
  callbacks = {}
) {
  if (!target || typeof target.replaceChildren !== "function") {
    return;
  }

  const input = normalizeInput(workflowOrOptions, reportCenter, activeFilter, selectedReceipt, callbacks);
  const workflow = objectOrEmpty(input.reviewWorkflow);
  const center = objectOrEmpty(input.reportCenter);
  const filter = objectOrEmpty(input.activeFilter);
  const handlers = objectOrEmpty(input.callbacks);
  const records = arrayOfObjects(workflow.records);
  const visibleRecords = filterRecords(records, filter);

  target.replaceChildren(
    headingBlock(workflow),
    decisionSummary(workflow, records),
    scopeBlock(workflow, center),
    filterBlock(workflow, filter, handlers),
    actionBlock(handlers, filter),
    shareReadinessBlock(workflow, center),
    blockerBlock(workflow, center),
    provenanceBlock(),
    receiptBlock(input.selectedReceipt),
    recordsBlock(visibleRecords, records.length, handlers)
  );
}

export function filterReviewerWorkflowRecords(records = [], activeFilter = {}) {
  return filterRecords(arrayOfObjects(records), objectOrEmpty(activeFilter));
}

function normalizeInput(workflowOrOptions, reportCenter, activeFilter, selectedReceipt, callbacks) {
  const candidate = objectOrEmpty(workflowOrOptions);
  const isOptions = [
    "reviewWorkflow",
    "review_workflow",
    "reportCenter",
    "report_center",
    "activeFilter",
    "active_filter",
    "selectedReceipt",
    "selected_receipt",
    "callbacks"
  ].some((key) => Object.prototype.hasOwnProperty.call(candidate, key));

  if (isOptions) {
    return {
      reviewWorkflow: candidate.reviewWorkflow ?? candidate.review_workflow,
      reportCenter: candidate.reportCenter ?? candidate.report_center,
      activeFilter: candidate.activeFilter ?? candidate.active_filter,
      selectedReceipt: candidate.selectedReceipt ?? candidate.selected_receipt,
      callbacks: candidate.callbacks ?? candidate
    };
  }
  return { reviewWorkflow: candidate, reportCenter, activeFilter, selectedReceipt, callbacks };
}

function headingBlock(workflow) {
  const block = element("div", "reviewer-workflow-heading");
  appendText(block, "h3", "Reviewer Workflow");
  appendText(
    block,
    "p",
    workflow.schema_version
      ? `${numberValue(workflow.human_action_count, workflow.record_count)} human action record(s), read only in this panel.`
      : "No review workflow is loaded."
  ).className = "caption";
  return block;
}

function decisionSummary(workflow, records) {
  const block = section("Decision Status", "reviewer-workflow-decisions");
  const counts = {
    approval: numberValue(workflow.approval_count, countType(records, "approval")),
    denial: numberValue(workflow.denial_count, countType(records, "denial")),
    waiver: numberValue(workflow.waiver_count, countType(records, "waiver"))
  };
  const grid = element("div", "health-grid");
  for (const type of REVIEW_ACTIONS) {
    const tile = element("div", "health-tile");
    appendText(tile, "strong", String(counts[type]));
    appendText(tile, "span", type === "approval" ? "Approvals" : type === "denial" ? "Denials" : "Waivers");
    grid.appendChild(tile);
  }
  const accepted = numberValue(workflow.accepted_count, records.filter((record) => record.accepted === true).length);
  const tile = element("div", "health-tile");
  appendText(tile, "strong", String(accepted));
  appendText(tile, "span", "Accepted");
  grid.appendChild(tile);
  block.appendChild(grid);
  return block;
}

function scopeBlock(workflow, reportCenter) {
  const block = section("Tenant / Project / Environment Scope", "reviewer-workflow-scope");
  const tenantScope = objectOrEmpty(reportCenter.tenant_scope);
  const scopeSummary = objectOrEmpty(workflow.scope_summary);
  const latestRecord = arrayOfObjects(workflow.records).at(-1) || {};
  block.appendChild(keyValueList([
    ["Tenant", tenantScope.tenant_id ?? workflow.tenant_id ?? workflow.organization_id],
    ["Project", tenantScope.project_id ?? workflow.project_id],
    ["Environment", tenantScope.environment_id ?? latestRecord.environment ?? scopeSummary.latest_environment],
    ["Release", latestRecord.release_version ?? scopeSummary.latest_release_version]
  ]));
  return block;
}

function filterBlock(workflow, activeFilter, callbacks) {
  const block = section("Review Filters", "reviewer-workflow-filters");
  const options = objectOrEmpty(workflow.filter_options);
  const definitions = [
    ["releaseVersion", "Release", arrayOfScalars(options.release_versions)],
    ["environment", "Environment", arrayOfScalars(options.environments)],
    ["actorHash", "Actor", arrayOfScalars(options.actor_hashes)]
  ];
  const grid = element("div", "inline-select-grid");
  for (const [field, label, values] of definitions) {
    const wrapper = element("label", "review-filter-control");
    appendText(wrapper, "span", label);
    const select = element("select");
    select.dataset.reviewFilter = field;
    select.appendChild(option("", `All ${label.toLowerCase()}s`, !scalar(activeFilter[field])));
    for (const value of values) {
      const display = field === "actorHash" ? shortHash(value) : value;
      select.appendChild(option(value, display, scalar(activeFilter[field]) === value));
    }
    select.addEventListener("change", (event) => {
      const nextFilter = { ...activeFilter, [field]: scalar(select.value) };
      callback(handlersFor(callbacks, ["onFilterChange", "onFilter"]), nextFilter, {
        field,
        value: scalar(select.value),
        event
      });
    });
    wrapper.appendChild(select);
    grid.appendChild(wrapper);
  }
  block.appendChild(grid);
  return block;
}

function actionBlock(callbacks, activeFilter) {
  const block = section("Reviewer Actions", "reviewer-workflow-actions");
  const row = element("div", "action-row review-action-row");
  for (const action of REVIEW_ACTIONS) {
    const button = element("button", "button subtle");
    button.type = "button";
    button.dataset.reviewAction = action;
    button.textContent = action === "approval" ? "Approve" : action === "denial" ? "Deny" : "Request Waiver";
    button.addEventListener("click", (event) => {
      callback(handlersFor(callbacks, ["onAction", "onReviewAction"]), action, {
        activeFilter: { ...activeFilter },
        event
      });
    });
    row.appendChild(button);
  }
  block.appendChild(row);
  appendText(block, "p", "Actions emit reviewer intent only; this panel performs no cloud write.").className = "muted";
  return block;
}

function shareReadinessBlock(workflow, reportCenter) {
  const block = section("Report Share Readiness", "reviewer-workflow-share-readiness");
  const summary = objectOrEmpty(reportCenter.summary);
  const shareable = numberValue(summary.shareable_count, 0);
  const blocked = numberValue(summary.blocked_count, 0);
  const revoked = numberValue(summary.revoked_count, 0);
  const accepted = numberValue(workflow.accepted_count, 0);
  const status = shareable > 0 && accepted > 0 && blocked === 0 ? "ready" : "blocked or waiting";
  block.appendChild(keyValueList([
    ["Status", status],
    ["Shareable reports", shareable],
    ["Manifest-ready reports", numberValue(summary.manifest_ready_count, 0)],
    ["Blocked / revoked", `${blocked} / ${revoked}`],
    ["Accepted human records", accepted]
  ]));
  return block;
}

function blockerBlock(workflow, reportCenter) {
  const block = section("Review Blockers", "reviewer-workflow-blockers");
  const reasons = [];
  const external = objectOrEmpty(reportCenter.external_publish_blockers);
  reasons.push(...arrayOfScalars(external.reasons));
  for (const record of arrayOfObjects(workflow.records)) {
    const findings = arrayOfObjects(objectOrEmpty(record.review).findings);
    for (const finding of findings) {
      if (finding.severity === "blocking") {
        reasons.push(scalar(finding.message || finding.summary || finding.id));
      }
    }
  }
  for (const report of arrayOfObjects(reportCenter.reports)) {
    const redaction = objectOrEmpty(report.redaction);
    if (report.status === "blocked" || redaction.blocked === true) {
      reasons.push(scalar(redaction.reason || redaction.status || `${scalar(report.report_id) || "Report"} is blocked.`));
    }
  }
  block.appendChild(textList(uniqueNonEmpty(reasons), "No review or sharing blockers are reported."));
  return block;
}

function provenanceBlock() {
  const block = section("Evidence Provenance", "reviewer-workflow-provenance");
  block.appendChild(textList([
    "A1 trace provenance: trace events and tool-call evidence are read-only inputs; this panel does not change runner, billing, or storage semantics.",
    "A2 judge provenance: scores, pass/fail, failure classes, release gates, and waiver policy remain A2-owned; reviewer actions do not rewrite judge or release semantics."
  ]));
  return block;
}

function receiptBlock(receiptInput) {
  const block = section("Selected Receipt", "reviewer-workflow-receipt");
  const receipt = objectOrEmpty(receiptInput);
  if (!Object.keys(receipt).length) {
    appendText(block, "p", "No review receipt is selected.").className = "muted";
    return block;
  }
  block.appendChild(keyValueList([
    ["Type", receipt.record_type],
    ["Status", receipt.status],
    ["Record", receipt.record_id],
    ["Event", objectOrEmpty(receipt.event_envelope).event_type],
    ["Payload hash", shortHash(receipt.payload_hash)],
    ["Review hash", shortHash(receipt.review_hash)],
    ["Cloud mutation", receipt.real_cloud_mutation_performed === true ? "reported" : "none"]
  ]));
  return block;
}

function recordsBlock(records, totalCount, callbacks) {
  const block = section("Durable Review Records", "reviewer-workflow-records");
  appendText(block, "p", "Human Action Log").className = "section-kicker";
  appendText(block, "p", `${records.length} of ${totalCount} record(s) visible.`).className = "caption";
  if (!records.length) {
    appendText(block, "p", totalCount ? "No records match the active filters." : "No human review actions are recorded.").className = "muted";
    return block;
  }

  const list = element("div", "matrix-list");
  for (const record of [...records].reverse()) {
    const row = element("button", "matrix-row reviewer-workflow-record");
    row.type = "button";
    row.dataset.reviewReceipt = scalar(record.record_id);
    const review = objectOrEmpty(record.review);
    const subject = objectOrEmpty(record.subject);
    const signature = objectOrEmpty(record.signature);
    const actor = objectOrEmpty(review.approval).reviewer_role
      || objectOrEmpty(review.denial).reviewer_role
      || objectOrEmpty(review.waiver).latest_approver_role
      || signature.signer_role
      || "unknown actor";
    appendText(row, "strong", `${scalar(record.record_type) || "review"}: ${scalar(record.status) || "unknown"}`);
    appendText(row, "span", `${scalar(record.record_id) || "no record id"} / ${record.accepted === true ? "accepted" : "not accepted"}`);
    appendText(row, "span", `${scalar(record.organization_id) || "unknown tenant"} / ${scalar(record.project_id) || "unknown project"} / ${scalar(record.environment) || "unknown environment"}`);
    appendText(row, "span", `${scalar(actor)} / ${scalar(record.created_at) || "unknown time"}`);
    appendText(row, "span", scalar(subject.decision || subject.follow_up_issue || record.release_version) || "No disposition detail.");
    row.addEventListener("click", (event) => {
      callback(handlersFor(callbacks, ["onReceiptSelect", "onSelectReceipt"]), record, { event });
    });
    list.appendChild(row);
  }
  block.appendChild(list);
  return block;
}

function filterRecords(records, filter) {
  const releaseVersion = scalar(filter.releaseVersion ?? filter.release_version);
  const environment = scalar(filter.environment);
  const actorHash = scalar(filter.actorHash ?? filter.actor_hash);
  return records.filter((record) => {
    if (releaseVersion && scalar(record.release_version) !== releaseVersion) return false;
    if (environment && scalar(record.environment) !== environment) return false;
    if (actorHash && ![record.payload_hash, record.review_hash, record.subject?.approved_by_actor_hash].map(scalar).includes(actorHash)) return false;
    return true;
  });
}

function section(title, className) {
  const block = element("section", className);
  appendText(block, "h4", title);
  return block;
}

function keyValueList(rows) {
  const list = element("div", "matrix-list");
  for (const [label, rawValue] of rows) {
    const row = element("div", "mini-row");
    appendText(row, "span", label);
    appendText(row, "strong", scalar(rawValue) || "unknown");
    list.appendChild(row);
  }
  return list;
}

function textList(values, emptyText = "No items.") {
  const list = element("ul", "reviewer-workflow-list");
  const items = values.length ? values : [emptyText];
  for (const value of items) appendText(list, "li", value);
  return list;
}

function option(value, label, selected) {
  const node = element("option");
  node.value = value;
  node.selected = selected;
  node.textContent = label;
  return node;
}

function appendText(parent, tagName, value) {
  const node = element(tagName);
  node.textContent = scalar(value);
  parent.appendChild(node);
  return node;
}

function element(tagName, className = "") {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  return node;
}

function handlersFor(callbacks, names) {
  const source = objectOrEmpty(callbacks);
  for (const name of names) if (typeof source[name] === "function") return source[name];
  return null;
}

function callback(handler, ...args) {
  if (typeof handler === "function") handler(...args);
}

function objectOrEmpty(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function arrayOfObjects(value) {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object" && !Array.isArray(item)) : [];
}

function arrayOfScalars(value) {
  return Array.isArray(value) ? uniqueNonEmpty(value.map(scalar)) : [];
}

function scalar(value) {
  if (value === undefined || value === null) return "";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return "";
}

function shortHash(value) {
  const text = scalar(value);
  return text.length > 14 ? `${text.slice(0, 12)}...` : text;
}

function numberValue(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : Number(fallback) || 0;
}

function countType(records, type) {
  return records.filter((record) => record.record_type === type).length;
}

function uniqueNonEmpty(values) {
  return [...new Set(values.map(scalar).filter(Boolean))];
}
