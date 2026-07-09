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
      { href: "#metrics", label: "Run metrics" }
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
      { href: "#official-gap", label: "Official gap" }
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
      { href: "#clusters", label: "Failure clusters" }
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
      { href: "#peer-branch-calibration", label: "Peer branches" },
      { href: "#release-gate", label: "Release gate" },
      { href: "#pr-gate", label: "PR gate" },
      { href: "#war-room", label: "War room" }
    ]
  }
];

export const productSurfaces = [
  {
    href: "#summary",
    label: "Workspace",
    detail: "Evaluation health and source status"
  },
  {
    href: "#product-console",
    label: "Product Console / Onboarding / Audit",
    detail: "product console workflow, projects, audit log"
  },
  {
    href: "#saas-admin",
    label: "SaaS Admin / Login / Team / Trust",
    detail: "SaaS admin guardrails, RBAC, team, API keys"
  },
  {
    href: "#saas-runtime",
    label: "Usage",
    detail: "quota, meters, reportable activity"
  },
  {
    href: "#cloud-shell",
    label: "API Keys",
    detail: "read-only cloud action shell"
  },
  {
    href: "#enterprise-readiness",
    label: "Trust",
    detail: "audit, export safety, self-host posture"
  }
];

export const workspaceRailGroups = [
  {
    label: "Workflow",
    links: [
      { href: "#console", label: "Console" },
      { href: "#runs", label: "Run List" },
      { href: "#detail", label: "Case Detail" },
      { href: "#timeline", label: "Trace Timeline" },
      { href: "#clusters", label: "Failure Clusters" }
    ]
  },
  {
    label: "Platform",
    links: [
      { href: "#saas-runtime", label: "SaaS Runtime" },
      { href: "#billing-migration-readiness", label: "Billing Migration" },
      { href: "#live-workflow-readiness", label: "Live Workflow" },
      { href: "#live-ops-control-plane", label: "Live Ops" },
      { href: "#product-console", label: "Product Console" },
      { href: "#saas-admin", label: "SaaS Admin" },
      { href: "#enterprise-readiness", label: "Enterprise" },
      { href: "#schema-drift-radar", label: "Contracts" },
      { href: "#peer-branch-calibration", label: "Peer Branches" },
      { href: "#cloud-shell", label: "Cloud Shell" }
    ]
  },
  {
    label: "Calibration",
    links: [
      { href: "#media-readiness", label: "Media" },
      { href: "#official-gap", label: "Official Gap" },
      { href: "#official-mirror", label: "Frontend Mirror" },
      { href: "#official-code-crawl", label: "Code Crawl" },
      { href: "#official-roadmap", label: "Parity Roadmap" }
    ]
  },
  {
    label: "Release",
    links: [
      { href: "#release-gate", label: "Release Gate" },
      { href: "#war-room", label: "War Room" },
      { href: "#incident-replay", label: "Incident Replay" },
      { href: "#observability-replay", label: "Observability" },
      { href: "#regression-factory", label: "Regression" },
      { href: "#reviewer-workflow", label: "Review" },
      { href: "#pr-gate", label: "PR Gate" },
      { href: "#release-evidence", label: "Evidence" }
    ]
  },
  {
    label: "Output",
    links: [
      { href: "#operations", label: "Operations" },
      { href: "#report-preview", label: "Report" },
      { href: "#export-redaction", label: "Export Safety" }
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
    link.classList.toggle("active", index === 0);

    const label = document.createElement("span");
    label.textContent = item.label;
    const meta = document.createElement("small");
    meta.textContent = item.meta;
    const arrow = document.createElement("span");
    arrow.className = "nav-arrow";
    arrow.setAttribute("aria-hidden", "true");

    link.append(label, meta, arrow);

    const sublist = document.createElement("div");
    sublist.className = "nav-sublist";
    sublist.setAttribute("aria-label", `${item.label} subsections`);
    sublist.replaceChildren(...item.children.map((child) => {
      const childLink = anchor(child.href, "nav-subitem");
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
