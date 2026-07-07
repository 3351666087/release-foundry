export function renderSaasRuntimePanel(target, runtime = {}) {
  if (!target) {
    return;
  }

  const dbContract = runtime.db_contract || {};
  const apiSurfaces = Array.isArray(dbContract.api_surfaces) ? dbContract.api_surfaces : [];
  const tables = Array.isArray(dbContract.tables) ? dbContract.tables : [];
  const guardrails = Array.isArray(dbContract.guardrails) ? dbContract.guardrails : [];

  target.replaceChildren(
    runtimeSummary(runtime),
    runtimeGrid([
      ["Mode", runtime.mode || "static_fixture"],
      ["DB ready", runtime.db_ready ? "yes" : "planned"],
      ["Primary DB", dbContract.recommended_primary_db || "postgres"],
      ["MySQL", dbContract.mysql_compatible ? "compatible" : "not planned"]
    ]),
    runtimeList("API surfaces", apiSurfaces),
    runtimeList("DB tables", tables.slice(0, 8)),
    runtimeList("Guardrails", guardrails)
  );
}

function runtimeSummary(runtime) {
  const node = document.createElement("div");
  node.className = "caption";
  node.textContent = runtime.mode && runtime.mode !== "static_fixture"
    ? "Dashboard data is API-backed and follows the A3 DB-ready contract."
    : "Dashboard is using local fixtures, but the same data shape can be served by the A3 API store.";
  return node;
}

function runtimeGrid(rows) {
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

function runtimeList(label, items) {
  const list = document.createElement("div");
  list.className = "matrix-list";
  const header = document.createElement("div");
  header.className = "section-kicker";
  header.textContent = label;
  list.appendChild(header);

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "matrix-row";
    empty.innerHTML = `<div class="muted">No ${escapeHtml(label.toLowerCase())} loaded.</div>`;
    list.appendChild(empty);
    return list;
  }

  for (const item of items) {
    const row = document.createElement("div");
    row.className = "matrix-row";
    row.innerHTML = `<div class="muted">${escapeHtml(item)}</div>`;
    list.appendChild(row);
  }
  return list;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
