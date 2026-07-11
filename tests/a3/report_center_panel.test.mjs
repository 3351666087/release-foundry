import assert from "node:assert/strict";
import { test } from "node:test";

import { renderReportCenterPanel } from "../../apps/dashboard/src/components/report-center-panel.mjs";

test("Report Center renders hosted lifecycle, tenant scope, artifacts, usage posture, and A2 release sign-off read-only", () => {
  const { target } = fixtureDom();
  renderReportCenterPanel(target, fullModel());

  const output = target.textContent;
  assert.match(output, /Release packet/);
  assert.match(output, /workspace-a \/ project-a \/ prod/);
  assert.match(output, /reviewer_signoff/);
  assert.match(output, /customer external blocked/);
  assert.match(output, /Manifest 92%/);
  assert.match(output, /release evidence ready/);
  assert.match(output, /Artifact Registry/);
  assert.match(output, /hosted_report: shared, hash_ready, passed redaction, report_snapshots/);
  assert.match(output, /signoff_packet_ready_for_review/);
  assert.match(output, /usage ready, migration ready/);
});

test("Report Center empty state keeps audience filters, tenant scope groups, and external publish blockers visible", () => {
  const { target } = fixtureDom();
  const model = fullModel();
  model.reports = [];
  model.summary = {};
  model.workspace_groups.groups = [];
  model.environment_groups.groups = [];

  renderReportCenterPanel(target, model);

  assert.match(target.textContent, /No hosted reports yet/);
  assert.match(target.textContent, /Audience Filters/);
  assert.match(target.textContent, /customer_external: blocked/);
  assert.match(target.textContent, /No workspace grouping yet/);
  assert.match(target.textContent, /No environment grouping yet/);
  assert.match(target.textContent, /External Publish Blockers/);
  assert.match(target.textContent, /public export trust workflow/);
});

test("Report Center delegates create, revoke, and export API intents without owning DB, auth, RBAC, usage, or audit mutations", () => {
  const { target } = fixtureDom();
  const calls = [];
  const model = fullModel();
  renderReportCenterPanel(target, model, {
    create: (intent) => calls.push(["create", intent]),
    revoke: (report) => calls.push(["revoke", report.report_id]),
    export: (format) => calls.push(["export", format])
  });

  findButton(target, "Create hosted report").click();
  findButton(target, "Revoke").click();
  findButton(target, "JSON").click();
  findButton(target, "Print/PDF").click();

  assert.deepEqual(calls, [
    ["create", { type: "create" }],
    ["revoke", "a3r-release"],
    ["export", "json"],
    ["export", "print"]
  ]);
});

test("Report Center embedded mode avoids duplicate header commands while retaining row lifecycle actions", () => {
  const { target } = fixtureDom();
  renderReportCenterPanel(target, fullModel(), { revoke: () => {} }, { showHeaderActions: false });

  assert.equal(target.descendants().some((node) => node.tagName === "button" && node.textContent === "Create hosted report"), false);
  assert.equal(target.descendants().some((node) => node.tagName === "button" && node.textContent === "JSON"), false);
  assert.ok(findButton(target, "Revoke"));
});

test("Report Center renders untrusted report, audience, blocker, scope, and artifact text XSS-safe via textContent", () => {
  const { target, documentNode } = fixtureDom();
  const attack = '<img src=x onerror="steal()"><script>steal()</script>';
  const model = fullModel();
  model.reports[0].title = attack;
  model.reports[0].tenant_scope.workspace_id = attack;
  model.export_audience_governance.audiences[0].basis = attack;
  model.external_publish_blockers.reasons = [attack];
  model.artifact_registry.entries[0].customer_value = attack;

  renderReportCenterPanel(target, model);

  assert.ok(target.textContent.includes(attack));
  assert.equal(documentNode.createdTags.includes("img"), false);
  assert.equal(documentNode.createdTags.includes("script"), false);
  assert.equal(target.descendants().some((node) => node.innerHTMLAssigned), false);
});

function fullModel() {
  return {
    tenant_scope: {
      organization_id: "org-a",
      tenant_id: "tenant-a",
      workspace_id: "workspace-a",
      project_id: "project-a",
      environment_id: "prod"
    },
    summary: {
      shareable_count: 1,
      revoked_count: 0,
      expired_count: 0,
      total_view_count: 7
    },
    export_audience_governance: {
      status: "audience_gates_visible",
      audiences: [
        { audience: "reviewer_signoff", allowed: true, basis: "release evidence ready" },
        { audience: "customer_external", allowed: false, basis: "trust workflow missing" }
      ]
    },
    audience_filters: {
      status: "filters_ready",
      default_filter: "internal_ops",
      filters: [
        { audience: "internal_ops", state: "visible", allowed_count: 1, blocked_count: 0 },
        { audience: "customer_external", state: "blocked", allowed_count: 0, blocked_count: 1 }
      ]
    },
    workspace_groups: {
      groups: [{ workspace_id: "workspace-a", report_count: 1, shareable_count: 1, release_evidence_ready_count: 1 }]
    },
    environment_groups: {
      groups: [{ environment_id: "prod", report_count: 1, shareable_count: 1, release_evidence_ready_count: 1 }]
    },
    external_publish_blockers: {
      status: "customer_external_blocked",
      blocker_count: 1,
      reasons: ["Customer-visible exports require explicit trust and audit workflows."],
      prerequisites: ["public export trust workflow", "tenant-approved share policy"]
    },
    release_signoff_summary: {
      status: "signoff_packet_ready_for_review",
      shareable_count: 1,
      release_evidence_ready_count: 1,
      manifest_ready_count: 1,
      usage_ready: true,
      migration_ready: true
    },
    release_signoff_detail: {
      checklist: [{ id: "release_evidence", passed: true }, { id: "reviewer_approval", passed: false }],
      recommendations: ["Collect reviewer approval before external sign-off."]
    },
    reports: [{
      report_id: "a3r-release",
      title: "Release packet",
      status: "shareable",
      share_url_path: "/reports/a3r-release",
      view_count: 7,
      tenant_scope: { workspace_id: "workspace-a", project_id: "project-a", environment_id: "prod" },
      share_link: { scope: "private_link" },
      export_audience: {
        allowed: ["internal_ops", "reviewer_signoff"],
        blocked: ["customer_external"],
        customer_external_blocked: true
      },
      manifest: { completeness_score: 92, missing: [] },
      redaction: { status: "passed" },
      release_evidence: { available: true },
      lifecycle: { revocable: true, view_audit_enabled: true }
    }],
    artifact_registry: {
      registry_status: "registry_ready",
      summary: { artifact_count: 1, ready_count: 1, hash_ready_count: 1, billable_meter_count: 1 },
      entries: [{
        artifact_id: "artifact-hosted",
        artifact_type: "hosted_report",
        lifecycle_state: "shared",
        hash_status: "hash_ready",
        redaction_status: "passed",
        billable_meter: "report_snapshots",
        customer_value: "Auditable hosted evidence"
      }]
    }
  };
}

function fixtureDom() {
  const documentNode = new FakeDocument();
  return { documentNode, target: documentNode.createElement("div") };
}

function findButton(root, label) {
  const button = root.descendants().find((node) => node.tagName === "button" && node.textContent === label);
  assert.ok(button, `missing button: ${label}`);
  return button;
}

class FakeDocument {
  constructor() {
    this.createdTags = [];
  }

  createElement(tagName) {
    const normalized = String(tagName).toLowerCase();
    this.createdTags.push(normalized);
    return new FakeElement(normalized, this);
  }
}

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.className = "";
    this.disabled = false;
    this.innerHTMLAssigned = false;
    this.textValue = "";
  }

  set textContent(value) {
    this.textValue = String(value ?? "");
    this.children = [];
  }

  get textContent() {
    return this.textValue + this.children.map((child) => child.textContent).join("");
  }

  set innerHTML(_value) {
    this.innerHTMLAssigned = true;
    throw new Error("innerHTML is forbidden in Report Center component tests");
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.textValue = "";
    this.children = [...nodes];
  }

  addEventListener(type, callback) {
    this.listeners.set(type, callback);
  }

  click() {
    if (!this.disabled) this.listeners.get("click")?.();
  }

  descendants() {
    return [this, ...this.children.flatMap((child) => child.descendants())];
  }
}
