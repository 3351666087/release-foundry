export function renderEnterpriseReadinessPanel(target, readiness = {}) {
  if (!target) {
    return;
  }

  const blockers = Array.isArray(readiness.blockers) ? readiness.blockers : [];
  const capabilities = Array.isArray(readiness.enabled_capabilities) ? readiness.enabled_capabilities : [];
  const actions = Array.isArray(readiness.next_actions) ? readiness.next_actions : [];
  const a1 = readiness.a1_a2_compatibility_notes?.a1 || {};
  const a2 = readiness.a1_a2_compatibility_notes?.a2 || {};

  target.replaceChildren(
    summary(readiness),
    grid([
      ["Score", String(readiness.readiness_score ?? 0)],
      ["Status", readiness.status || "unknown"],
      ["A1 traces", String(a1.trace_case_count || 0)],
      ["A2 judges", String(a2.judge_result_count || 0)]
    ]),
    section("Enterprise Blockers", blockers.length
      ? blockers.map((item) => row(item.id, `${item.severity}: ${item.message}`, item.severity === "blocking" ? "fail" : "warn"))
      : [row("none", "No blocking enterprise readiness issue in the current evidence.", "pass")]
    ),
    section("Sellable Capabilities", capabilities.length
      ? capabilities.slice(0, 8).map((item) => row(item.id, `${item.label} (${item.evidence_count})`, "info"))
      : [row("none", "No enterprise capability evidence is loaded.", "neutral")]
    ),
    section("Next Actions", actions.length
      ? actions.slice(0, 6).map((item) => row(item.id, `${item.priority}: ${item.action}`, item.priority === "high" ? "warn" : "neutral"))
      : [row("none", "No next action generated.", "neutral")]
    ),
    section("A1/A2 Compatibility", [
      row("A1", `${a1.compatible ? "compatible" : "missing"} / ${a1.run_count || 0} run(s), ${a1.trace_event_count || 0} trace event(s), ${a1.tool_case_count || 0} tool case(s)`, a1.compatible ? "pass" : "warn"),
      row("A2", `${a2.compatible ? "compatible" : "missing"} / ${a2.grade_case_count || 0} grade case(s), ${a2.judge_result_count || 0} judge result(s)`, a2.compatible ? "pass" : "warn")
    ])
  );
}

function summary(readiness) {
  const node = document.createElement("div");
  node.className = "caption";
  node.textContent = `Enterprise readiness ${readiness.status || "unknown"} / score ${readiness.readiness_score ?? 0}. This panel is aggregate-only and should not echo source payload secrets.`;
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

function row(label, value, badgeClass) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(label)}</strong>
      <span class="badge ${escapeHtml(badgeClass)}">${escapeHtml(badgeClass)}</span>
    </div>
    <div class="muted">${escapeHtml(value)}</div>
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
