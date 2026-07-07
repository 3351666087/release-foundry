export function renderSaasAdminConsole(target, admin = {}, options = {}) {
  if (!target) {
    return;
  }

  const actions = Array.isArray(admin.actions) ? admin.actions : [];
  const selectedAction = options.selectedAction || actions[0]?.action || "view_usage";
  const selectedPlan = options.selectedPlan || actions.find((item) => item.action === selectedAction) || actions[0] || {};

  target.replaceChildren(
    sectionIntro(admin),
    summaryGrid(admin),
    sectionBlock("Login", [
      row("Status", admin.login?.status || "unknown"),
      row("Provider", admin.login?.provider || "unknown"),
      row("Session", admin.login?.session_storage || "not persisted"),
      row("Identity", admin.login?.user_identity || "[REDACTED]")
    ]),
    sectionBlock("Team", [
      row("Members", String(admin.team?.members?.length || 0)),
      row("Roles", (admin.team?.roles || []).join(", ") || "none"),
      row("Invite mode", admin.team?.invite_mode || "disabled")
    ]),
    rosterBlock(admin.team?.members || []),
    sectionBlock("Usage", [
      row("Status", admin.usage?.status || "unknown"),
      row("Runs", String(admin.usage?.local_meter?.run_count || 0)),
      row("Cases", String(admin.usage?.local_meter?.case_count || 0)),
      row("Channels", (admin.usage?.channels || []).join(", ") || "local meter"),
      row("OAuth-only", (admin.usage?.oauth_only_functions || []).join(", ") || "none")
    ]),
    sectionBlock("API Keys", [
      row("Status", admin.api_keys?.status || "unknown"),
      row("Create mode", admin.api_keys?.create_mode || "server required"),
      row("Reveal policy", admin.api_keys?.reveal_policy || "one-time only")
    ]),
    keyBlock(admin.api_keys?.keys || []),
    sectionBlock("Trust", [
      row("Status", admin.trust?.status || "unknown"),
      row("Certificate", admin.trust?.public_certificate_mode || "preview"),
      row("Publish", admin.trust?.publish_enabled ? "enabled" : "disabled"),
      row("Gate", admin.trust?.release_gate_label || admin.trust?.release_gate_decision || "unknown")
    ]),
    actionPlanBlock(actions, selectedAction, selectedPlan),
    compatibilityBlock(admin.a1_a2_compatibility || {})
  );
}

function sectionIntro(admin) {
  const node = document.createElement("div");
  node.className = "caption";
  node.textContent = `${admin.organization?.display_name || "A3 Local Organization"} / ${admin.project?.display_name || "A3 Release Intelligence"} / ${admin.safety?.mode || "clean-room shell"}`;
  return node;
}

function summaryGrid(admin) {
  const rows = [
    ["Org", admin.organization?.plan || "local"],
    ["Project", admin.project?.environment || "staging"],
    ["A1", admin.a1_a2_compatibility?.a1_run_result_ready ? "ready" : "missing"],
    ["A2", admin.a1_a2_compatibility?.a2_grade_result_ready ? "ready" : "missing"]
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

function sectionBlock(title, rows) {
  const block = document.createElement("div");
  block.className = "matrix-list";
  const header = document.createElement("div");
  header.className = "section-kicker";
  header.textContent = title;
  block.appendChild(header);
  for (const item of rows) {
    block.appendChild(item);
  }
  return block;
}

function row(label, value) {
  const node = document.createElement("div");
  node.className = "mini-row";
  node.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return node;
}

function rosterBlock(members) {
  const block = sectionBlock("Team Roster", []);
  for (const member of members) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(member.display_name)}</strong>
        <span class="badge neutral">${escapeHtml(member.role)}</span>
      </div>
      <div class="muted">${escapeHtml(member.status)} / ${member.redacted ? "redacted identity" : "visible identity"}</div>
    `;
    block.appendChild(node);
  }
  return block;
}

function keyBlock(keys) {
  const block = sectionBlock("API Key Metadata", []);
  for (const key of keys) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(key.name)}</strong>
        <span class="badge warn">${escapeHtml(key.status)}</span>
      </div>
      <div class="case-meta">
        <span>${escapeHtml(key.prefix)}</span>
        <span>${escapeHtml((key.scopes || []).join(", "))}</span>
      </div>
      <div class="muted">secret value never rendered</div>
    `;
    block.appendChild(node);
  }
  return block;
}

function actionPlanBlock(actions, selectedAction, selectedPlan) {
  const block = sectionBlock("Cloud Action Plan", []);
  const selector = document.createElement("select");
  selector.className = "admin-action-select";
  selector.dataset.adminActionSelect = "true";
  for (const action of actions) {
    const option = document.createElement("option");
    option.value = action.action;
    option.textContent = action.action;
    option.selected = action.action === selectedAction;
    selector.appendChild(option);
  }
  block.appendChild(selector);

  const plan = document.createElement("div");
  plan.className = "matrix-row";
  plan.dataset.adminActionPlan = "true";
  plan.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(selectedPlan.action || selectedAction)}</strong>
      <span class="badge ${selectedPlan.enabled ? "pass" : selectedPlan.mode === "plan_only" ? "warn" : "neutral"}">${escapeHtml(selectedPlan.mode || "unknown")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(selectedPlan.area || "unknown")}</span>
      <span>${escapeHtml(selectedPlan.risk || "unknown")} risk</span>
      <span>${selectedPlan.writes_real_ashr_cloud ? "real write" : "no real cloud write"}</span>
    </div>
    <div class="muted">${escapeHtml(selectedPlan.reason || "No action plan loaded.")}</div>
    <div class="muted">${escapeHtml(selectedPlan.next_step || "")}</div>
  `;
  block.appendChild(plan);
  return block;
}

function compatibilityBlock(compatibility) {
  return sectionBlock("A1/A2 Compatibility", [
    row("A1 trace cases", String(compatibility.a1_trace_case_count || 0)),
    row("A1 tool cases", String(compatibility.a1_tool_case_count || 0)),
    row("A2 judge cases", String(compatibility.a2_judge_case_count || 0)),
    row("Dashboard cases", String(compatibility.dashboard_case_count || 0))
  ]);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
