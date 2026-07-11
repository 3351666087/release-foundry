export function renderLiveOpsControlPlanePanel(target, controlPlane = {}) {
  if (!target) {
    return;
  }

  const lanes = Array.isArray(controlPlane.lanes) ? controlPlane.lanes : [];
  const counts = controlPlane.counts || {};
  const human = controlPlane.human_operation_summary || {};
  const billing = controlPlane.billing_state_summary || {};
  const share = controlPlane.report_link_summary || {};
  const signoff = controlPlane.commercial_signoff_summary || {};

  target.replaceChildren(
    caption("Six live SaaS workflows are tracked as API, DB, event, audit, and dashboard contracts. A3 keeps them safe until A1 hosted workers and A2 release policy are ready."),
    healthGrid([
      [counts.lane_count || 0, "ops lanes"],
      [counts.api_backed_count || 0, "API-backed"],
      [counts.audit_backed_count || 0, "audit-backed"],
      [counts.local_external_mutation_count || 0, "local mutations"]
    ]),
    table(["Workflow", "Surface", "Status", "Mode", "Next action"], lanes.map((item) => [
      item.label,
      item.product_surface,
      item.status,
      item.current_mode,
      item.next_action
    ]), "No live ops control-plane lanes are loaded."),
    table(["Summary", "Value"], [
      ["Human records", `${human.review_record_count || 0} review / ${human.event_outbox_count || 0} outbox`],
      ["Reviewer decisions", `${human.approval_count || 0} approve / ${human.denial_count || 0} deny / ${human.waiver_count || 0} waiver`],
      ["Billing state", `${billing.billing_readiness_status || "unknown"} / ${billing.meter_count || 0} meter(s)`],
      ["Share links", `${share.shareable_count || 0} shareable / ${share.revoked_count || 0} revoked / ${share.expired_count || 0} expired / ${share.total_view_count || 0} view(s)`]
    ]),
    table(["Commercial sign-off", "Value"], [
      ["Status", signoff.status || "unknown"],
      ["Release publish", signoff.release_publish_status || "unknown"],
      ["Required roles", (signoff.required_roles || []).join(", ") || "unknown"],
      ["Customer external", signoff.customer_external_blocked ? "blocked" : "ready"],
      ["Reviewer gate", signoff.evidence?.reviewer_gate || "unknown"],
      ["GitHub", `${signoff.evidence?.github_check || "unknown"} / ${signoff.evidence?.github_pr_comment || "unknown"}`],
      ["Hosted report", `${signoff.evidence?.hosted_report || "unknown"} / ${signoff.evidence?.shareable_report_count || 0} shareable`],
      ["Trust / billing", `${signoff.evidence?.trust_publish || "unknown"} / ${signoff.evidence?.collections_state || "unknown"}`]
    ]),
    table(["Sign-off blockers", "Reason"], (signoff.blocker_reasons || []).map((item, index) => [
      index === 0 ? signoff.status || "blocked" : "follow-up",
      item
    ]), "No commercial sign-off blockers are recorded."),
    table(["Reviewer timeline", "Status", "Reason"], (controlPlane.reviewer_timeline || []).map((item) => [
      `${item.record_type} / ${item.actor_hash}`,
      item.status,
      item.reason
    ]), "No reviewer timeline has been recorded yet."),
    table(["GitHub publish step", "Status", "Target"], (controlPlane.github_publish_timeline || []).map((item) => [
      `${item.step}${item.dry_run ? " (dry-run)" : ""}`,
      item.status,
      item.target
    ]), "No GitHub publish timeline is loaded."),
    table(["Share-link lifecycle", "Status", "Detail"], (controlPlane.share_link_timeline || []).map((item) => [
      item.timeline_id,
      item.status,
      `views ${item.view_count || 0} / expires ${item.expires_at || "n/a"} / revoked ${item.revoked_at || "n/a"}`
    ]), "No hosted report lifecycle history is loaded."),
    table(["Release publish chain", "Status", "Detail"], (controlPlane.release_publish_chain?.steps || []).map((item) => [
      item.step,
      item.status,
      item.detail
    ]), "No release publish chain is visible yet."),
    table(["Publish blockers", "Reason"], (controlPlane.release_publish_chain?.blocker_reasons || []).map((item, index) => [
      index === 0 ? controlPlane.release_publish_chain?.status || "unknown" : "follow-up",
      item
    ]), "No publish blocker reasons are recorded."),
    table(["Audit history", "Status"], (controlPlane.audit_history || []).map((item) => [
      item.event_type,
      item.status
    ]), "No audit history is visible yet."),
    caption(`A1: ${(controlPlane.a1_a2_alignment?.a1_consumed_contracts || ["usage", "GitHub worker", "billing ledger"]).join(", ")}`),
    caption(`A2: ${(controlPlane.a1_a2_alignment?.a2_consumed_contracts || ["grade", "release gate", "failure taxonomy"]).join(", ")}`)
  );
}

function caption(value) {
  const node = document.createElement("div");
  node.className = "caption";
  node.textContent = value;
  return node;
}

function healthGrid(items) {
  const grid = document.createElement("div");
  grid.className = "health-grid";
  grid.replaceChildren(...items.map(([value, label]) => {
    const tile = document.createElement("div");
    tile.className = "health-tile";
    const strong = document.createElement("strong");
    strong.textContent = String(value);
    const span = document.createElement("span");
    span.textContent = label;
    tile.append(strong, span);
    return tile;
  }));
  return grid;
}

function table(headers, rows, emptyText = "No rows.") {
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = emptyText;
    return empty;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "report-table";
  const tableNode = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const header of headers) {
    const cell = document.createElement("th");
    cell.textContent = header;
    headRow.appendChild(cell);
  }
  head.appendChild(headRow);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const rowNode = document.createElement("tr");
    for (const value of row) {
      const cell = document.createElement("td");
      cell.textContent = String(value ?? "");
      rowNode.appendChild(cell);
    }
    body.appendChild(rowNode);
  }
  tableNode.append(head, body);
  wrapper.appendChild(tableNode);
  return wrapper;
}
