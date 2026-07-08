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
      row("Identity", admin.login?.user_identity || "[REDACTED]"),
      row("RBAC", admin.login?.rbac_boundary?.enforced_now ? "enforced" : "planned")
    ]),
    sessionBlock(admin.login || {}),
    rbacBlock(admin.rbac || {}),
    sectionBlock("Team", [
      row("Members", String(admin.team?.members?.length || 0)),
      row("Roles", (admin.team?.roles || []).join(", ") || "none"),
      row("Invite mode", admin.team?.invite_mode || "disabled"),
      row("Self approval", admin.team?.approval_policy?.self_approval_allowed ? "allowed" : "blocked")
    ]),
    rosterBlock(admin.team?.members || []),
    workflowBlock("Invite Workflow", admin.team?.invite_workflow || [], "step", "status", "reason"),
    sectionBlock("Usage", [
      row("Status", admin.usage?.status || "unknown"),
      row("Runs", String(admin.usage?.local_meter?.run_count || 0)),
      row("Cases", String(admin.usage?.local_meter?.case_count || 0)),
      row("Channels", (admin.usage?.channels || []).join(", ") || "local meter"),
      row("OAuth-only", (admin.usage?.oauth_only_functions || []).join(", ") || "none"),
      row("Plan", admin.usage?.plan_snapshot?.plan_name || "local_dev")
    ]),
    workflowBlock("Usage Controls", admin.usage?.budget_controls || [], "control", "status", "mutation_enabled"),
    sectionBlock("API Keys", [
      row("Status", admin.api_keys?.status || "unknown"),
      row("Create mode", admin.api_keys?.create_mode || "server required"),
      row("Reveal policy", admin.api_keys?.reveal_policy || "one-time only")
    ]),
    keyBlock(admin.api_keys?.keys || []),
    workflowBlock("API Key Lifecycle", admin.api_keys?.lifecycle || [], "step", "status", "safety"),
    sectionBlock("Trust", [
      row("Status", admin.trust?.status || "unknown"),
      row("Certificate", admin.trust?.public_certificate_mode || "preview"),
      row("Publish", admin.trust?.publish_enabled ? "enabled" : "disabled"),
      row("Gate", admin.trust?.release_gate_label || admin.trust?.release_gate_decision || "unknown")
    ]),
    trustBlock(admin.trust || {}),
    cloudManagementBlock(admin.cloud_management || {}),
    workflowBlock("Product Console Map", admin.product_console_map || [], "page", "a3_decision", "purpose"),
    actionPlanBlock(actions, selectedAction, selectedPlan),
    actionRequestBlock(admin.action_request_summary || {}, admin.action_requests || []),
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

function sessionBlock(login) {
  const session = login.session || {};
  const rbac = login.rbac_boundary || {};
  return sectionBlock("Auth Session", [
    row("Session status", session.status || "unknown"),
    row("Cookies", session.cookie_storage || "not read"),
    row("Tokens", session.token_storage || "not read"),
    row("Required claims", (rbac.required_claims || []).join(", ") || "none"),
    row("Policy", rbac.dashboard_policy || "read-only")
  ]);
}

function rbacBlock(rbac) {
  const block = sectionBlock("RBAC Matrix", [
    row("Status", rbac.status || "unknown"),
    row("Default role", rbac.default_role || "developer"),
    row("Enforcement", rbac.current_enforcement || "planned")
  ]);
  for (const role of rbac.permission_matrix || []) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(role.role)}</strong>
        <span class="badge info">${escapeHtml(role.permission_count || 0)} permission(s)</span>
      </div>
      <div class="muted">${escapeHtml((role.permissions || []).join(", "))}</div>
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
        <span>${escapeHtml(key.owner_role || "unassigned")}</span>
      </div>
      <div class="muted">secret value never rendered</div>
    `;
    block.appendChild(node);
  }
  return block;
}

function workflowBlock(title, items, primaryKey, badgeKey, detailKey) {
  const block = sectionBlock(title, []);
  if (!Array.isArray(items) || !items.length) {
    const empty = document.createElement("div");
    empty.className = "matrix-row";
    empty.innerHTML = `<div class="muted">No ${escapeHtml(title.toLowerCase())} loaded.</div>`;
    block.appendChild(empty);
    return block;
  }
  for (const item of items) {
    const node = document.createElement("div");
    const badge = item[badgeKey];
    const detail = detailKey === "mutation_enabled"
      ? (item[detailKey] ? "mutation enabled" : "mutation disabled")
      : item[detailKey];
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(item[primaryKey] || "item")}</strong>
        <span class="badge ${badgeClass(String(badge))}">${escapeHtml(badge ?? "unknown")}</span>
      </div>
      <div class="muted">${escapeHtml(detail || "")}</div>
    `;
    block.appendChild(node);
  }
  return block;
}

function trustBlock(trust) {
  const center = trust.trust_center || {};
  const artifacts = Array.isArray(center.artifacts) ? center.artifacts : [];
  const block = sectionBlock("Trust Center", [
    row("Preview", center.preview_enabled ? "enabled" : "disabled"),
    row("Public publish", center.public_publish_enabled ? "enabled" : "blocked"),
    row("Audit payload", trust.audit_log_policy?.redacted_payload_only ? "redacted" : "unknown")
  ]);
  for (const artifact of artifacts) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(artifact.artifact)}</strong>
        <span class="badge ${badgeClass(artifact.status)}">${escapeHtml(artifact.status)}</span>
      </div>
    `;
    block.appendChild(node);
  }
  return block;
}

function cloudManagementBlock(cloud) {
  const block = sectionBlock("Cloud Management", [
    row("Status", cloud.status || "unknown"),
    row("Project switcher", cloud.project_switcher?.enabled ? "read-only" : "disabled"),
    row("Real mutations", cloud.real_mutations_enabled ? "enabled" : "disabled"),
    row("Audit storage", cloud.audit_controls?.storage_target || "audit_events")
  ]);
  for (const resource of cloud.resources || []) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(resource.type)} / ${escapeHtml(resource.id)}</strong>
        <span class="badge neutral">${escapeHtml(resource.mode)}</span>
      </div>
      <div class="muted">${escapeHtml(resource.label)}</div>
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

  const button = document.createElement("button");
  button.type = "button";
  button.className = "button subtle";
  button.dataset.adminActionSubmit = "true";
  button.textContent = selectedPlan.enabled ? "Record Request" : "Record Guardrail";
  block.appendChild(button);
  return block;
}

function actionRequestBlock(summary, requests) {
  const block = sectionBlock("Admin Action Requests", [
    row("Recorded", String(summary.request_count || requests.length || 0)),
    row("Pending", String(summary.pending_count || 0)),
    row("Blocked", String(summary.blocked_count || 0)),
    row("Real writes", summary.real_cloud_mutations_performed ? "yes" : "no")
  ]);
  const latest = Array.isArray(requests) ? requests.slice(-4).reverse() : [];
  if (!latest.length) {
    const empty = document.createElement("div");
    empty.className = "matrix-row";
    empty.innerHTML = `<div class="muted">No admin requests recorded yet. Use Record Request to create a safe audit event.</div>`;
    block.appendChild(empty);
    return block;
  }
  for (const request of latest) {
    const node = document.createElement("div");
    node.className = "matrix-row";
    node.innerHTML = `
      <div class="matrix-head">
        <strong>${escapeHtml(request.action)}</strong>
        <span class="badge ${badgeClass(request.status)}">${escapeHtml(request.status)}</span>
      </div>
      <div class="case-meta">
        <span>${escapeHtml(request.request_id)}</span>
        <span>${escapeHtml(request.area)}</span>
        <span>${request.real_cloud_mutation_performed ? "real write" : "no real cloud write"}</span>
      </div>
      <div class="muted">${escapeHtml(request.next_step || "")}</div>
    `;
    block.appendChild(node);
  }
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

function badgeClass(value) {
  if (["available", "enabled", "copy_now", "read_only", "contract_ready", "approve_release"].includes(value)) {
    return "pass";
  }
  if (["blocked", "disabled", "plan_only", "missing", "block_release", "recorded_plan_only", "blocked_requires_backend", "blocked_real_cloud_mutation"].includes(value)) {
    return "warn";
  }
  if (["preview", "preview_only", "planned", "recorded_read_only"].includes(value)) {
    return "info";
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
