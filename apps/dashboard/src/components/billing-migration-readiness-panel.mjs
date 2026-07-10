export function renderBillingMigrationReadinessPanel(target, readiness = {}) {
  if (!target) {
    return;
  }

  const upstream = readiness.upstream_evidence || {};
  const dbTables = Array.isArray(readiness.db_contract?.tables) ? readiness.db_contract.tables : [];
  const apiRoutes = Array.isArray(readiness.api_contract) ? readiness.api_contract : [];
  target.replaceChildren(
    caption(readiness.purpose || "Billing migration readiness is not attached."),
    healthGrid([
      [readiness.summary?.upstream_commit_count || 0, "A1 commits"],
      [dbTables.length, "billing tables"],
      [readiness.summary?.consumed_evidence_count || 0, "evidence inputs"],
      [readiness.summary?.ready_for_live_customer_billing ? "yes" : "no", "live billing"]
    ]),
    table(["A1 evidence", "Source", "A3 state"], Object.entries(upstream).slice(0, 5).map(([key, item]) => [
      key,
      item.source_commit || item.summary_path || item.fixture_path || "local",
      item.a3_consumption_state || item.status || "mapped"
    ]), "No A1 billing migration evidence is loaded."),
    table(["DB table", "Purpose", "Tenant scope"], dbTables.map((item) => [
      item.name,
      item.purpose,
      `${item.tenant_column || "organization_id"} / ${item.project_column || "project_id"}`
    ]), "No billing migration DB tables are mapped."),
    table(["API route", "Owner", "Status"], apiRoutes.map((item) => [
      item.route,
      item.owner_lane,
      item.status
    ]), "No billing migration API routes are mapped."),
    caption(`A3 claim: ${readiness.summary?.a3_customer_claim || "A3 stays read-only until A1 exposes authenticated billing ledger APIs."}`)
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
  tableNode.append(tableHead(headers), tableBody(rows));
  wrapper.appendChild(tableNode);
  return wrapper;
}

function tableHead(headers) {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const value of headers) {
    const cell = document.createElement("th");
    cell.textContent = value;
    row.appendChild(cell);
  }
  head.appendChild(row);
  return head;
}

function tableBody(rows) {
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
  return body;
}
