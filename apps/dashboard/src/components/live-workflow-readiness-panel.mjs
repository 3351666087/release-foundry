export function renderLiveWorkflowReadinessPanel(target, readiness = {}) {
  if (!target) {
    return;
  }

  const capabilities = Array.isArray(readiness.capabilities) ? readiness.capabilities : [];
  target.replaceChildren(
    caption(readiness.commercial_value || "Live workflow readiness is not attached."),
    healthGrid([
      [readiness.ready_capability_count || 0, "ready capabilities"],
      [readiness.needs_backend_or_credentials_count || 0, "need live backend"],
      [readiness.human_action_count || 0, "human records"],
      [readiness.audit_backed_count || 0, "audit backed"]
    ]),
    table(["Next capability", "Status", "Dashboard value"], capabilities.map((item) => [
      item.label,
      item.status,
      item.dashboard_value
    ]), "No live workflow readiness capabilities are loaded."),
    table(["Next action"], (readiness.next_actions || []).map((item) => [item]), "No live workflow next actions are pending."),
    caption(`Boundary: ${readiness.a1_a2_boundary || "A3 keeps live workflow evidence downstream of A1/A2 contracts."}`)
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

function table(headers, rows, emptyText) {
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
  for (const value of headers) {
    const cell = document.createElement("th");
    cell.textContent = value;
    headRow.appendChild(cell);
  }
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  for (const values of rows) {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = String(value ?? "");
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
  tableNode.append(head, body);
  wrapper.appendChild(tableNode);
  return wrapper;
}
