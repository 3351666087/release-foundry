export function renderEnterpriseReadinessPanel(target, readiness = {}) {
  if (!target) {
    return;
  }

  const blockers = Array.isArray(readiness.blockers) ? readiness.blockers : [];
  const capabilities = Array.isArray(readiness.enabled_capabilities) ? readiness.enabled_capabilities : [];
  const actions = Array.isArray(readiness.next_actions) ? readiness.next_actions : [];
  const posture = readiness.cloud_self_host_posture || {};
  const a1 = readiness.a1_a2_compatibility_notes?.a1 || {};
  const a2 = readiness.a1_a2_compatibility_notes?.a2 || {};
  const missing = Array.isArray(readiness.missing_capabilities) ? readiness.missing_capabilities : [];

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
    enterpriseValueBlock(readiness.enterprise_value_map || {}),
    section("Hosted / Self-Host Gaps", missing.length
      ? missing.slice(0, 8).map((item) => row(item.id || "gap", `${item.label || item.message || item}`, "warn"))
      : [row("none", "No explicit hosted or self-host gap was published in the current evidence.", "neutral")]
    ),
    section("Cloud / Self-Host Posture", [
      row("Hosted", posture.hosted_readiness || "unknown", posture.hosted_readiness === "read_only_hosted_shell_ready" ? "pass" : "warn"),
      row("Self-host", posture.self_host_readiness || "unknown", posture.self_host_readiness === "self_host_contract_visible" ? "pass" : "warn"),
      row("Tenant isolation", posture.tenant_isolation_state || "unknown", posture.tenant_isolation_state === "visible" ? "pass" : "warn"),
      row("Why it matters", posture.why_it_matters || "Commercial buyers need clear hosted and self-host posture.", "info")
    ]),
    selfHostPacketBlock(readiness.self_host_packet || {}),
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

function enterpriseValueBlock(valueMap) {
  const block = section("Enterprise Value", [
    row("Sellable now", (valueMap.sellable_now || []).join(", ") || "none", "info"),
    row("High-value paths", (valueMap.high_value_paths || []).join(", ") || "none", "pass")
  ]);
  const buyer = valueMap.buyer_questions_answered || {};
  for (const [label, ok] of Object.entries(buyer)) {
    block.appendChild(row(label, ok ? "answered" : "missing", ok ? "pass" : "warn"));
  }
  if ((valueMap.blocked_enterprise_claims || []).length) {
    block.appendChild(row("Blocked claims", valueMap.blocked_enterprise_claims.join(", "), "warn"));
  }
  return block;
}

function selfHostPacketBlock(packet) {
  const block = section("Self-Host Packet", [
    row("Status", packet.status || "unknown", packet.status === "packet_contract_ready" ? "pass" : "warn"),
    row("Install surfaces", (packet.install_surfaces || []).join(", ") || "none", "info"),
    row("Blockers", String(packet.blocker_count || 0), (packet.blocker_count || 0) === 0 ? "pass" : "warn")
  ]);
  for (const item of packet.buyer_promises || []) {
    block.appendChild(row("Buyer promise", item, "neutral"));
  }
  for (const item of packet.hosted_vs_self_host || []) {
    block.appendChild(row(item.surface || "surface", `hosted: ${item.hosted || "unknown"} / self-host: ${item.self_host || "unknown"} / value: ${item.buyer_value || "unknown"}`, "info"));
  }
  return block;
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



