export function renderA1A2ContractRadarPanel(target, radar = {}) {
  if (!target) {
    return;
  }

  const contracts = Array.isArray(radar.contracts) ? radar.contracts : [];
  const matrix = radar.integration_matrix || {};
  const domains = Array.isArray(matrix.domains) ? matrix.domains : [];
  const bridges = Array.isArray(matrix.bridges) ? matrix.bridges : [];
  const actions = Array.isArray(matrix.top_actions) ? matrix.top_actions : [];

  target.replaceChildren(
    caption(radar.a3_action || "A1/A2 schema and artifact radar is not attached."),
    healthGrid([
      [radar.contract_count || contracts.length || 0, "schema contracts"],
      [radar.compatible_count || 0, "schema compatible"],
      [matrix.aligned_domain_count || 0, "domains aligned"],
      [matrix.attention_domain_count || 0, "need attention"]
    ]),
    sectionHeading("Schema compatibility", `${radar.compatible_count || 0}/${radar.contract_count || contracts.length || 0}`),
    reportTable(["Contract", "Lane", "Status", "Hash"], contracts.slice(0, 8).map((item) => [
      item.schema_contract_id,
      item.source_lane,
      item.status,
      item.content_hash ? `${item.content_hash.slice(0, 12)}...` : "missing"
    ]), "No A1/A2 schema contracts are loaded.", "schema-contract-table"),
    sectionHeading("Cross-Lane Integration", matrix.status || "not attached"),
    bridgeGrid(bridges),
    reportTable(["Domain", "Lane", "Status", "Public evidence", "A3 surface"], domains.map((item) => [
      item.domain,
      item.source_lane,
      item.status,
      summarizePublicEvidence(item.public_summary),
      (item.required_by_a3_surfaces || []).join(", ")
    ]), "No A1/A2 integration domains are loaded.", "integration-domain-table"),
    actionList(actions),
    caption(matrix.ownership_boundary || radar.a1_a2_boundary || "A3 consumes A1/A2 evidence downstream only."),
    caption(`Safety: raw schema payload ${radar.safety?.raw_schema_payload_embedded ? "embedded" : "not embedded"}; raw integration artifacts ${matrix.safety?.raw_artifact_payload_embedded ? "embedded" : "not embedded"}.`)
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
  grid.className = "health-grid contract-health-grid";
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

function sectionHeading(title, status) {
  const header = document.createElement("div");
  header.className = "integration-section-heading";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const badge = document.createElement("span");
  badge.className = `badge ${status === "aligned" || String(status).includes("/") ? "pass" : "warn"}`;
  badge.textContent = status;
  header.append(strong, badge);
  return header;
}

function bridgeGrid(bridges) {
  const grid = document.createElement("div");
  grid.className = "integration-bridge-grid";
  if (!bridges.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No cross-lane bridges are loaded.";
    grid.appendChild(empty);
    return grid;
  }

  for (const bridge of bridges) {
    const card = document.createElement("div");
    card.className = "integration-bridge";
    const label = document.createElement("strong");
    label.textContent = bridge.label;
    const evidence = document.createElement("span");
    evidence.textContent = `${(bridge.evidence_ids || []).length} evidence domains`;
    const surface = document.createElement("small");
    surface.textContent = `A3: ${bridge.a3_surface || "dashboard"}`;
    card.append(label, evidence, surface);
    grid.appendChild(card);
  }
  return grid;
}

function reportTable(headers, rows, emptyText, className = "") {
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = emptyText;
    return empty;
  }
  const wrapper = document.createElement("div");
  wrapper.className = `report-table contract-responsive-table ${className}`.trim();
  const table = document.createElement("table");
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
    for (const [index, value] of values.entries()) {
      const cell = document.createElement("td");
      cell.dataset.label = headers[index] || "Field";
      cell.textContent = String(value ?? "");
      row.appendChild(cell);
    }
    body.appendChild(row);
  }
  table.append(head, body);
  wrapper.appendChild(table);
  return wrapper;
}

function actionList(actions) {
  const list = document.createElement("div");
  list.className = "integration-action-list";
  const label = document.createElement("div");
  label.className = "section-kicker";
  label.textContent = "Next cross-lane actions";
  list.appendChild(label);
  for (const action of actions) {
    const row = document.createElement("div");
    row.className = "matrix-row";
    row.textContent = action;
    list.appendChild(row);
  }
  return list;
}

function summarizePublicEvidence(summary = {}) {
  const preferredKeys = [
    "route_group_count",
    "table_count",
    "providers",
    "backends",
    "route_count",
    "judge_result_rows",
    "candidate_count"
  ];
  for (const key of preferredKeys) {
    const value = summary[key];
    if (Array.isArray(value) && value.length) {
      return value.join(", ");
    }
    if (value !== undefined && value !== null) {
      return `${humanize(key)}: ${value}`;
    }
  }
  return "public-safe hash only";
}

function humanize(value) {
  return String(value).replaceAll("_", " ");
}
