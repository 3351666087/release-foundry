export const visualNavigationSelector = [
  ".nav a[href^='#']",
  ".product-surface-strip a[href^='#']",
  ".section-rail a[href^='#']"
].join(", ");

export const primaryAreas = [
  { href: "#summary", label: "Overview", meta: "health" },
  { href: "#console", label: "Evaluate", meta: "runs" },
  { href: "#runs", label: "Review", meta: "cases" },
  { href: "#report-preview", label: "Reports", meta: "export" },
  { href: "#saas-admin", label: "Admin", meta: "access" },
  { href: "#enterprise-readiness", label: "Trust", meta: "audit" }
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
      { href: "#product-console", label: "Product Console" },
      { href: "#saas-admin", label: "SaaS Admin" },
      { href: "#enterprise-readiness", label: "Enterprise" },
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
    const link = anchor(item.href, "nav-link");
    link.classList.toggle("active", index === 0);

    const label = document.createElement("span");
    label.textContent = item.label;
    const meta = document.createElement("small");
    meta.textContent = item.meta;

    link.append(label, meta);
    return link;
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
