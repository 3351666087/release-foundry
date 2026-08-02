export function renderNotificationControlPlanePanel(target, controlPlane = {}) {
  if (!target) {
    return;
  }

  const summary = controlPlane.summary || {};
  const channels = Array.isArray(controlPlane.channels) ? controlPlane.channels : [];
  const triggers = Array.isArray(controlPlane.trigger_matrix) ? controlPlane.trigger_matrix : [];
  const growthPoints = Array.isArray(controlPlane.growth_points) ? controlPlane.growth_points : [];
  const alignment = controlPlane.a1_a2_alignment || {};
  const liveOps = controlPlane.live_ops_alignment || {};

  target.replaceChildren(
    intro(),
    grid([
      ["Channels", String(summary.channel_count || channels.length || 0)],
      ["Contract-ready", String(summary.contract_ready_count || 0)],
      ["Audit-backed", String(summary.audit_backed_count || 0)],
      ["Growth points", String(summary.growth_point_count || growthPoints.length || 0)],
      ["Configured", String(summary.configured_metadata_count || 0)],
      ["Live sends", String(summary.live_mutation_count || 0)]
    ]),
    section("Delivery Channels", channels.length
      ? channels.map((channel) => channelRow(channel))
      : [emptyRow("No notification control-plane channels are loaded.")]
    ),
    section("Trigger Matrix", triggers.length
      ? triggers.map((trigger) => triggerRow(trigger))
      : [emptyRow("No notification trigger matrix is loaded.")]
    ),
    section("Commercial Growth", growthPoints.length
      ? growthPoints.slice(0, 8).map((point) => growthRow(point))
      : [emptyRow("No notification growth points are loaded.")]
    ),
    section("Live Ops Alignment", [
      row("Human ops", `${liveOps.review_record_count || 0} review / ${liveOps.event_outbox_count || 0} outbox / ${liveOps.visible_human_ops ? "visible" : "waiting"}`),
      row("Billing / usage", `${liveOps.billing_readiness_status || "unknown"} / ${liveOps.usage_meter_count || 0} meter(s) / ${liveOps.billing_mutations_enabled ? "live mutation" : "read only"}`),
      row("Shareable reports", `${liveOps.shareable_report_count || 0} shareable / ${liveOps.revoked_report_count || 0} revoked / ${liveOps.expired_report_count || 0} expired / ${liveOps.total_report_views || 0} view(s)`),
      row("Why it sells", liveOps.why_it_sells || "Notifications matter when they carry reviewer, billing, and audit state.")
    ]),
    section("Hosted Gaps", [
      row("A1 hosted worker", alignment.a1_dependency || "Hosted notification worker and encrypted connector refs remain outside A3."),
      row("A2 policy", alignment.a2_dependency || "Release policy, failure taxonomy, score-pass-fail, and redaction remain A2-owned."),
      row("Safety", "No raw webhook URL, token, cookie, email, or provider secret is rendered here.")
    ])
  );
}

function intro() {
  const node = document.createElement("div");
  node.className = "caption";
  node.textContent = "Slack, Teams, email, and webhook notifications are modeled as release-governance evidence. A3 plans surfaces and audit rows; A1 owns live delivery workers and connector custody.";
  return node;
}

function grid(items) {
  const node = document.createElement("div");
  node.className = "health-grid";
  node.replaceChildren(...items.map(([label, value]) => {
    const tile = document.createElement("div");
    tile.className = "health-tile";
    tile.innerHTML = `<strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span>`;
    return tile;
  }));
  return node;
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

function channelRow(channel = {}) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(channel.label || channel.provider || "unknown")}</strong>
      <span class="badge ${badgeClass(channel.status)}">${escapeHtml(channel.status || "unknown")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(channel.provider || "unknown")}</span>
      <span>${escapeHtml(channel.current_mode || "planned")}</span>
      <span>${escapeHtml((channel.rbac_permissions || []).join(", ") || "no RBAC metadata")}</span>
    </div>
    <div class="muted">events: ${escapeHtml((channel.event_types || []).join(", ") || "none")}</div>
    <div class="muted">usage: ${escapeHtml((channel.usage_meters || []).join(", ") || "none")}</div>
    <div class="muted">next: ${escapeHtml(channel.next_action || "No next action loaded.")}</div>
  `;
  return node;
}

function triggerRow(trigger = {}) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(trigger.label || trigger.provider || "trigger")}</strong>
      <span class="badge info">${escapeHtml(trigger.dashboard_state || "planned")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml((trigger.channels || []).join(", ") || trigger.provider || "unknown")}</span>
      <span>${escapeHtml((trigger.triggers || []).join(", ") || "no triggers")}</span>
    </div>
    <div class="muted">${escapeHtml(trigger.customer_value || trigger.policy_owner || "Release-notification evidence is planned.")}</div>
  `;
  return node;
}

function growthRow(point = {}) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  const title = `${point.priority || "P2"} ${point.id || "growth"}`;
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(title)}</strong>
      <span class="badge neutral">${escapeHtml(point.surface || point.provider || "surface")}</span>
    </div>
    <div class="muted">${escapeHtml(point.title || point.sellable_claim || "Commercial notification growth point")}</div>
    <div class="muted">artifact: ${escapeHtml(point.expected_artifact || "notification evidence")}</div>
  `;
  return node;
}

function row(label, value) {
  const node = document.createElement("div");
  node.className = "mini-row";
  node.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return node;
}

function emptyRow(value) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `<div class="muted">${escapeHtml(value)}</div>`;
  return node;
}

function badgeClass(value) {
  if (["contract_ready_needs_provider_config", "contract_ready", "visible", "read_only_state_ready", "workflow_ready"].includes(value)) {
    return "pass";
  }
  if (["metadata_present_delivery_disabled", "publisher_ready_needs_live_token", "workflow_ready_no_records", "lifecycle_ready"].includes(value)) {
    return "warn";
  }
  return "neutral";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
