export function renderA1A2EvidenceSpine(target, spine = {}) {
  if (!target) return;
  const stages = Array.isArray(spine.stages) ? spine.stages : [];
  const handoffs = Array.isArray(spine.handoffs) ? spine.handoffs : [];

  const header = element("div", "evidence-spine-header");
  const heading = element("div", "evidence-spine-heading");
  heading.append(
    element("span", "section-index", "001"),
    element("h2", "", "Evidence spine")
  );
  const state = element("span", `badge ${badgeTone(spine.status)}`, spine.status || "not attached");
  header.append(heading, state);

  const stageGrid = element("div", "evidence-spine-grid");
  if (!stages.length) {
    stageGrid.append(element("div", "muted", "Waiting for A1 and A2 evidence contracts."));
  } else {
    stageGrid.append(...stages.map(stageCard));
  }

  const handoffList = element("div", "evidence-handoff-list");
  handoffList.append(...handoffs.map((item) => {
    const row = element("div", "evidence-handoff");
    row.append(
      element("strong", "", `${item.from} -> ${item.to}`),
      element("span", `badge ${item.status === "linked" ? "pass" : "warn"}`, item.status),
      element("small", "", handoffSummary(item))
    );
    return row;
  }));

  const watch = element("div", "evidence-draft-watch");
  watch.append(
    watchRow("A1 identity", spine.draft_watch?.a1_identity_verification),
    watchRow("A2 multimodal", spine.draft_watch?.a2_multimodal_real_api_smoke)
  );

  const boundary = element("p", "caption evidence-spine-boundary");
  boundary.textContent = "A1 captures execution. A2 owns evaluation and release policy. A3 presents the evidence and workflow without changing either upstream meaning.";
  target.replaceChildren(header, stageGrid, handoffList, watch, boundary);
}

function stageCard(stage) {
  const card = element("article", `evidence-stage evidence-stage-${String(stage.lane || "a3").toLowerCase()}`);
  const top = element("div", "evidence-stage-top");
  top.append(
    element("span", "evidence-stage-index", stage.stage_index || "--"),
    element("span", "evidence-stage-lane", stage.lane || "A3"),
    element("span", `badge ${badgeTone(stage.status)}`, stage.status || "unknown")
  );
  card.append(
    top,
    element("h3", "", stage.label || "Stage"),
    element("strong", "evidence-stage-primary", stage.primary || "No evidence"),
    element("p", "caption", stage.secondary || "No secondary signal"),
    metricStrip(stage.metrics)
  );
  return card;
}

function metricStrip(metrics = {}) {
  const strip = element("div", "evidence-stage-metrics");
  const entries = Object.entries(metrics).slice(0, 3);
  strip.append(...entries.map(([key, value]) => {
    const item = element("span", "");
    item.append(element("strong", "", String(value)), element("small", "", humanize(key)));
    return item;
  }));
  return strip;
}

function watchRow(label, signal = {}) {
  const row = element("div", "evidence-watch-row");
  row.append(
    element("span", "", label),
    element("strong", "", signal.observed ? signal.contract || "observed" : "not observed"),
    element("small", "", signal.observed ? "draft watch / not main authority" : "no current peer signal")
  );
  return row;
}

function handoffSummary(item = {}) {
  const metrics = item.metrics || {};
  if (item.handoff_id === "a1_to_a2") {
    return `${metrics.linked_case_count || 0} linked / ${metrics.unresolved_case_count || 0} unresolved`;
  }
  if (item.handoff_id === "a2_to_gate") {
    return `${metrics.failed_case_count || 0} failed / ${metrics.release_blocker_count || 0} blockers`;
  }
  return `${metrics.provenance_node_count || 0} provenance nodes`;
}

function badgeTone(status) {
  if (["ready", "linked"].includes(status)) return "pass";
  if (["blocked", "missing", "action_required"].includes(status)) return "fail";
  return "warn";
}

function humanize(value) {
  return String(value).replaceAll("_", " ");
}

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}
