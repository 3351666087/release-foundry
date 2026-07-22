export const visualNavigationSelector = [
  ".nav a[href^='#']",
  ".product-surface-strip a[href^='#']",
  ".section-rail a[href^='#']"
].join(", ");

export const primaryAreas = [
  {
    href: "#summary",
    label: "Overview",
    meta: "health",
    children: [
      { href: "#summary", label: "Source & exports" },
      { href: "#product-surfaces", label: "Product surfaces" },
      { href: "#workspace-shortcuts", label: "Workspace shortcuts" },
      { href: "#metrics", label: "Run metrics" },
      { href: "#integration-spine", label: "A1/A2 evidence spine" }
    ]
  },
  {
    href: "#console",
    label: "Evaluate",
    meta: "runs",
    children: [
      { href: "#console", label: "Console" },
      { href: "#product-console", label: "Product console" },
      { href: "#media-readiness", label: "Media readiness" },
      { href: "#official-gap", label: "Official gap" },
      { href: "#official-mirror", label: "Frontend mirror" },
      { href: "#official-code-crawl", label: "Code crawl parity" },
      { href: "#official-roadmap", label: "Parity roadmap" }
    ]
  },
  {
    href: "#runs",
    label: "Review",
    meta: "cases",
    children: [
      { href: "#runs", label: "Run list" },
      { href: "#detail", label: "Case detail" },
      { href: "#timeline", label: "Trace timeline" },
      { href: "#clusters", label: "Failure clusters" },
      { href: "#reviewer-workflow", label: "Reviewer workflow" }
    ]
  },
  {
    href: "#report-preview",
    label: "Reports",
    meta: "export",
    children: [
      { href: "#report-preview", label: "Report preview" },
      { href: "#operations", label: "Report center" },
      { href: "#export-redaction", label: "Export safety" },
      { href: "#release-evidence", label: "Release evidence" }
    ]
  },
  {
    href: "#saas-admin",
    label: "Admin",
    meta: "access",
    children: [
      { href: "#saas-admin", label: "Login / team" },
      { href: "#live-workflow-readiness", label: "Live workflow" },
      { href: "#live-ops-control-plane", label: "Live ops" },
      { href: "#notification-control-plane", label: "Notifications" },
      { href: "#cloud-shell", label: "API keys" },
      { href: "#saas-runtime", label: "Usage / quota" },
      { href: "#billing-migration-readiness", label: "Billing migration" },
      { href: "#reviewer-workflow", label: "Reviewer workflow" }
    ]
  },
  {
    href: "#enterprise-readiness",
    label: "Trust",
    meta: "audit",
    children: [
      { href: "#enterprise-readiness", label: "Enterprise posture" },
      { href: "#schema-drift-radar", label: "Contract radar" },
      { href: "#peer-branch-calibration", label: "Peer Branches" },
      { href: "#release-gate", label: "Release gate" },
      { href: "#pr-gate", label: "PR gate" },
      { href: "#war-room", label: "War room" },
      { href: "#incident-replay", label: "Incident replay" },
      { href: "#observability-replay", label: "Observability replay" },
      { href: "#regression-factory", label: "Regression factory" }
    ]
  }
];

export const productSurfaces = [
  {
    href: "#summary",
    label: "Workspace",
    detail: "source and release health"
  },
  {
    href: "#runs",
    label: "Evaluation",
    detail: "runs, cases and traces"
  },
  {
    href: "#reviewer-workflow",
    label: "Review",
    detail: "human release decisions"
  },
  {
    href: "#operations",
    label: "Reports",
    detail: "evidence and export lifecycle"
  },
  {
    href: "#saas-admin",
    label: "Administration",
    detail: "identity, team and billing"
  },
  {
    href: "#schema-drift-radar",
    label: "Trust",
    detail: "contracts, audit and policy"
  }
];

export const workspaceRailGroups = [
  {
    label: "Live",
    links: [
      { href: "#runs", label: "Runs" },
      { href: "#reviewer-workflow", label: "Review" },
      { href: "#operations", label: "Reports" }
    ]
  },
  {
    label: "Control",
    links: [
      { href: "#saas-admin", label: "Admin" },
      { href: "#billing-migration-readiness", label: "Billing" },
      { href: "#enterprise-readiness", label: "Enterprise" }
    ]
  },
  {
    label: "Evidence",
    links: [
      { href: "#media-readiness", label: "Media" },
      { href: "#schema-drift-radar", label: "Contracts" },
      { href: "#official-gap", label: "Official parity" }
    ]
  }
];

export function setupVisualShell(root = document) {
  renderPrimaryNav(root.querySelector("[data-visual-shell='primary-nav']"));
  renderProductSurfaces(root.querySelector("[data-visual-shell='surface-strip']"));
  renderWorkspaceRail(root.querySelector("[data-visual-shell='section-rail']"));
}

function renderPrimaryNav(container) {
  if (!container) return;
  container.replaceChildren(...primaryAreas.map((item, index) => {
    const group = document.createElement("div");
    group.className = "nav-group";
    group.dataset.navGroup = item.label.toLowerCase();
    group.classList.toggle("expanded", index === 0);

    const link = anchor(item.href, "nav-link nav-parent");
    link.dataset.navParent = item.label.toLowerCase();
    link.dataset.navLabel = item.label;
    link.classList.toggle("active", index === 0);

    const label = document.createElement("span");
    label.textContent = item.label;
    const meta = document.createElement("small");
    meta.textContent = item.meta;
    const number = document.createElement("span");
    number.className = "nav-number";
    number.textContent = String(index + 1).padStart(3, "0");
    const arrow = document.createElement("span");
    arrow.className = "nav-arrow";
    arrow.setAttribute("aria-hidden", "true");

    link.append(label, meta, number, arrow);

    const sublist = document.createElement("div");
    sublist.className = "nav-sublist";
    sublist.setAttribute("aria-label", `${item.label} subsections`);
    sublist.replaceChildren(...item.children.map((child) => {
      const childLink = anchor(child.href, "nav-subitem");
      childLink.dataset.navLabel = child.label;
      childLink.dataset.navGroupLabel = item.label;
      childLink.textContent = child.label;
      return childLink;
    }));

    group.append(link, sublist);
    return group;
  }));
}

function renderProductSurfaces(container) {
  if (!container) return;
  container.replaceChildren(...productSurfaces.map((item, index) => {
    const link = anchor(item.href, "product-surface");
    link.dataset.navLabel = item.label;
    link.dataset.navDetail = item.detail;
    link.classList.toggle("active", index === 0);

    const label = document.createElement("strong");
    label.textContent = item.label;
    const detail = document.createElement("span");
    detail.textContent = item.detail;

    link.append(label, detail);
    return link;
  }));
}

function renderWorkspaceRail(container) {
  if (!container) return;
  container.replaceChildren(...workspaceRailGroups.map((group) => {
    const groupNode = document.createElement("div");
    groupNode.className = "rail-group";

    const label = document.createElement("span");
    label.className = "rail-label";
    label.textContent = group.label;

    groupNode.append(label, ...group.links.map((item) => {
      const link = anchor(item.href, "rail-chip");
      link.dataset.navLabel = item.label;
      link.dataset.navGroupLabel = group.label;
      link.textContent = item.label;
      return link;
    }));
    return groupNode;
  }));
}

function anchor(href, className) {
  const link = document.createElement("a");
  link.href = href;
  link.className = className;
  return link;
}
