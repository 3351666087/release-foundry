export function renderSaasRuntimePanel(target, runtime = {}) {
  if (!target) {
    return;
  }

  const dbContract = runtime.db_contract || {};
  const apiSurfaces = Array.isArray(dbContract.api_surfaces) ? dbContract.api_surfaces : [];
  const tables = Array.isArray(dbContract.tables) ? dbContract.tables : [];
  const guardrails = Array.isArray(dbContract.guardrails) ? dbContract.guardrails : [];
  const migrations = runtime.db_migrations || {};
  const usageLedger = runtime.usage_ledger || {};
  const billingReadiness = runtime.billing_readiness || {};
  const eventOutbox = runtime.event_outbox || {};
  const burnSummary = usageLedger.burn_summary || {};

  target.replaceChildren(
    runtimeSummary(runtime),
    runtimeGrid([
      ["Mode", humanize(runtime.mode || "static_fixture")],
      ["DB ready", runtime.db_ready ? "yes" : "planned"],
      ["Primary DB", dbContract.recommended_primary_db || "postgres"],
      ["MySQL", dbContract.mysql_compatible ? "compatible" : "not planned"],
      ["Migrations", String(migrations.migration_count || 0)],
      ["Usage meters", String((usageLedger.meters || []).length)],
      ["Billing", humanize(billingReadiness.status || "not loaded")],
      ["Runway", humanize(burnSummary.status || "unknown")],
      ["Event outbox", String(eventOutbox.event_count || 0)]
    ]),
    runtimeSpine([
      ["API routes", apiSurfaces.length],
      ["DB tables", tables.length],
      ["A1 usage", billingReadiness.a1_a2_alignment?.a1_usage_source_ready ? "ready" : "waiting"],
      ["A2 judge meter", billingReadiness.a1_a2_alignment?.a2_judge_meter_ready ? "ready" : "waiting"]
    ]),
    runtimeDisclosureGrid([
      runtimeDisclosure("API surfaces", apiSurfaces),
      runtimeDisclosure("DB tables", tables),
      runtimeDisclosure("Migration batches", (migrations.statements || []).map((item) => `${item.id}: ${item.tables.join(", ")}`)),
      runtimeDisclosure("Usage meters", (usageLedger.meters || []).map((item) => `${item.meter}: ${item.quantity}`)),
      runtimeDisclosure("Burn / Runway", burnRows(burnSummary)),
      runtimeDisclosure("Billing readiness", billingReadiness.schema_version ? billingRows(billingReadiness) : []),
      runtimeDisclosure("Event outbox", eventOutboxRows(eventOutbox)),
      runtimeDisclosure("Guardrails", guardrails)
    ])
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
  grid.className = "health-grid runtime-health-grid";
  grid.replaceChildren(...rows.map(([label, value]) => {
    const tile = document.createElement("div");
    tile.className = "health-tile";
    const strong = document.createElement("strong");
    strong.textContent = value;
    const span = document.createElement("span");
    span.textContent = label;
    tile.append(strong, span);
    return tile;
  }));
  return grid;
}

function runtimeSpine(rows) {
  const grid = document.createElement("div");
  grid.className = "runtime-spine-grid";
  for (const [label, value] of rows) {
    const item = document.createElement("div");
    item.className = "runtime-spine-item";
    const strong = document.createElement("strong");
    strong.textContent = String(value);
    const span = document.createElement("span");
    span.textContent = label;
    item.append(strong, span);
    grid.appendChild(item);
  }
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
    const text = document.createElement("div");
    text.className = "muted";
    text.textContent = `No ${label.toLowerCase()} loaded.`;
    empty.appendChild(text);
    list.appendChild(empty);
    return list;
  }

  for (const item of items) {
    const row = document.createElement("div");
    row.className = "matrix-row";
    const text = document.createElement("div");
    text.className = "muted";
    text.textContent = item;
    row.appendChild(text);
    list.appendChild(row);
  }
  return list;
}

function runtimeDisclosure(label, items) {
  const details = document.createElement("details");
  details.className = "runtime-disclosure";
  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.textContent = label;
  const count = document.createElement("span");
  count.className = "runtime-disclosure-count";
  count.textContent = String(items.length);
  summary.append(title, count);
  details.append(summary, runtimeList(label, items));
  return details;
}

function runtimeDisclosureGrid(items) {
  const grid = document.createElement("div");
  grid.className = "runtime-disclosure-grid";
  grid.replaceChildren(...items);
  return grid;
}

function burnRows(burn = {}) {
  if (!burn.status) {
    return [];
  }
  return [
    `status: ${burn.status || "unknown"}`,
    `billable units: ${burn.billable_units || 0}`,
    `quota included: ${burn.quota_included_units || 0}`,
    `remaining units: ${burn.estimated_remaining_units || 0}`,
    `active meters: ${(burn.active_billable_meters || []).join(", ") || "none"}`
  ];
}

function billingRows(billing = {}) {
  return [
    `status: ${billing.status || "unknown"}`,
    `mutations: ${billing.billing_mutations_enabled ? "enabled" : "disabled"}`,
    `provider: ${billing.provider_boundary?.provider_mode || "not configured"}`,
    `checkout: ${billing.provider_boundary?.checkout_enabled ? "enabled" : "disabled"}`,
    `invoice export: ${billing.provider_boundary?.invoice_export_enabled ? "ready" : "not ready"}`,
    `billable units: ${billing.billable_unit_count || 0}`,
    `A1 usage ready: ${billing.a1_a2_alignment?.a1_usage_source_ready ? "yes" : "no"}`,
    `A2 judge meter ready: ${billing.a1_a2_alignment?.a2_judge_meter_ready ? "yes" : "no"}`,
    ...((billing.quota_exposure || []).slice(0, 4).map((item) => `${item.meter}: ${item.quantity} / ${item.quota_state}`)),
    ...((billing.next_actions || []).slice(0, 3).map((item) => `next: ${item}`))
  ];
}

function eventOutboxRows(eventOutbox = {}) {
  const rows = [];
  rows.push(`events: ${eventOutbox.event_count || 0}`);
  rows.push(`pending: ${eventOutbox.pending_count || 0}`);
  rows.push(`delivered: ${eventOutbox.delivered_count || 0}`);
  rows.push(`audit only: ${eventOutbox.audit_only_count || 0}`);
  return rows;
}

function humanize(value) {
  const text = String(value ?? "").replaceAll("_", " ");
  return text ? text[0].toUpperCase() + text.slice(1) : "";
}


