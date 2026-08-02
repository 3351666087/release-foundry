import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import {
  filterReviewerWorkflowRecords,
  renderReviewerWorkflowPanel
} from "../../apps/dashboard/src/components/reviewer-workflow-panel.mjs";

let originalDocument;

beforeEach(() => {
  originalDocument = globalThis.document;
  globalThis.document = new FakeDocument();
});

afterEach(() => {
  globalThis.document = originalDocument;
});

test("renders decisions, human actions, scope, share readiness, blockers, and provenance", () => {
  const target = document.createElement("div");
  renderReviewerWorkflowPanel(target, fixture());

  assert.match(target.textContent, /Reviewer Workflow/);
  assert.match(target.textContent, /1\s*Approvals/);
  assert.match(target.textContent, /1\s*Denials/);
  assert.match(target.textContent, /1\s*Waivers/);
  assert.match(target.textContent, /tenant-acme/);
  assert.match(target.textContent, /project-checkout/);
  assert.match(target.textContent, /production/);
  assert.match(target.textContent, /Shareable reports2/);
  assert.match(target.textContent, /Customer sharing requires redaction approval/);
  assert.match(target.textContent, /A1 trace provenance/);
  assert.match(target.textContent, /A2 judge provenance/);
  assert.match(target.textContent, /does not change runner, billing, or storage semantics/);
  assert.match(target.textContent, /do not rewrite judge or release semantics/);
});

test("filters records and reports filter changes through callbacks", () => {
  const data = fixture();
  const calls = [];
  data.activeFilter = { environment: "production" };
  data.callbacks.onFilterChange = (...args) => calls.push(args);
  const target = document.createElement("div");

  renderReviewerWorkflowPanel(target, data);

  assert.match(target.textContent, /2 of 3 record\(s\) visible/);
  assert.doesNotMatch(target.textContent, /rwr-waiver-stage/);
  const releaseSelect = target.find((node) => node.dataset.reviewFilter === "releaseVersion");
  releaseSelect.value = "v2";
  releaseSelect.dispatchEvent({ type: "change" });
  assert.deepEqual(calls[0][0], { environment: "production", releaseVersion: "v2" });
  assert.deepEqual(calls[0][1].field, "releaseVersion");

  assert.deepEqual(
    filterReviewerWorkflowRecords(data.reviewWorkflow.records, { actorHash: "actor-approve" }).map((item) => item.record_id),
    ["rwr-approve-prod"]
  );
});

test("approve, deny, waiver, and receipt selection emit callbacks without cloud writes", () => {
  const data = fixture();
  const actions = [];
  const receipts = [];
  data.callbacks = {
    onAction: (action, context) => actions.push([action, context.activeFilter]),
    onReceiptSelect: (receipt) => receipts.push(receipt.record_id)
  };
  data.activeFilter = { releaseVersion: "v2" };
  const target = document.createElement("div");
  renderReviewerWorkflowPanel(target, data);

  for (const action of ["approval", "denial", "waiver"]) {
    target.find((node) => node.dataset.reviewAction === action).click();
  }
  target.find((node) => node.dataset.reviewReceipt === "rwr-deny-prod").click();

  assert.deepEqual(actions.map(([action]) => action), ["approval", "denial", "waiver"]);
  assert.deepEqual(actions[0][1], { releaseVersion: "v2" });
  assert.deepEqual(receipts, ["rwr-deny-prod"]);
  assert.match(target.textContent, /performs no cloud write/);
});

test("renders a selected receipt using only curated receipt fields", () => {
  const data = fixture();
  data.selectedReceipt = {
    schema_version: "a3.review_workflow_record.v1",
    record_type: "approval",
    status: "valid_approval",
    record_id: "receipt-42",
    payload_hash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    review_hash: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    event_envelope: { event_type: "review.approved" },
    real_cloud_mutation_performed: false,
    raw_payload: "must-not-render"
  };
  const target = document.createElement("div");
  renderReviewerWorkflowPanel(target, data);

  assert.match(target.textContent, /receipt-42/);
  assert.match(target.textContent, /review\.approved/);
  assert.match(target.textContent, /aaaaaaaaaaaa\.\.\./);
  assert.match(target.textContent, /Cloud mutationnone/);
  assert.doesNotMatch(target.textContent, /must-not-render/);
});

test("uses textContent for XSS-safe text and tolerates invalid or empty inputs", () => {
  const source = '<img src=x onerror="globalThis.pwned=true">';
  const data = fixture();
  data.reviewWorkflow.records[0].status = source;
  data.reportCenter.external_publish_blockers.reasons = [`blocked ${source}`];
  const target = document.createElement("div");
  renderReviewerWorkflowPanel(target, data);

  assert.match(target.textContent, /<img src=x/);
  assert.equal(target.findAll((node) => node.tagName === "IMG").length, 0);

  const empty = document.createElement("div");
  assert.doesNotThrow(() => renderReviewerWorkflowPanel(empty, null, "bad", [], "bad", null));
  assert.match(empty.textContent, /No review workflow is loaded/);
  assert.match(empty.textContent, /No human review actions are recorded/);
  assert.doesNotThrow(() => renderReviewerWorkflowPanel(null, {}));
});

function fixture() {
  return {
    reviewWorkflow: {
      schema_version: "a3.review_workflow_index.v1",
      record_count: 3,
      human_action_count: 3,
      approval_count: 1,
      denial_count: 1,
      waiver_count: 1,
      accepted_count: 2,
      scope_summary: { latest_release_version: "v2", latest_environment: "production" },
      filter_options: {
        release_versions: ["v1", "v2"],
        environments: ["staging", "production"],
        actor_hashes: ["actor-waiver", "actor-approve", "actor-deny"]
      },
      records: [
        record("waiver", "rwr-waiver-stage", "staging", "v1", "actor-waiver", true),
        record("approval", "rwr-approve-prod", "production", "v2", "actor-approve", true),
        {
          ...record("denial", "rwr-deny-prod", "production", "v2", "actor-deny", false),
          review: {
            denial: { reviewer_role: "Safety reviewer" },
            findings: [{ severity: "blocking", message: "Critical judge failure remains open." }]
          }
        }
      ]
    },
    reportCenter: {
      tenant_scope: {
        tenant_id: "tenant-acme",
        project_id: "project-checkout",
        environment_id: "production"
      },
      summary: { shareable_count: 2, manifest_ready_count: 1, blocked_count: 1, revoked_count: 0 },
      external_publish_blockers: {
        reasons: ["Customer sharing requires redaction approval."]
      }
    },
    activeFilter: {},
    selectedReceipt: null,
    callbacks: {}
  };
}

function record(type, id, environment, release, hash, accepted) {
  return {
    record_type: type,
    record_id: id,
    status: `valid_${type}`,
    accepted,
    organization_id: "tenant-acme",
    project_id: "project-checkout",
    environment,
    release_version: release,
    payload_hash: hash,
    created_at: "2026-07-11T08:00:00.000Z",
    signature: { signer_role: "Release reviewer" },
    subject: { decision: type === "denial" ? "deny_release" : `accept_${type}` },
    review: {}
  };
}

class FakeDocument {
  createElement(tagName) {
    return new FakeElement(tagName);
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.value = "";
    this.selected = false;
    this.listeners = new Map();
    this._textContent = "";
  }

  set textContent(value) {
    this._textContent = String(value ?? "");
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent).join("");
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this._textContent = "";
    this.children = children;
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatchEvent(event) {
    event.target = this;
    for (const listener of this.listeners.get(event.type) || []) listener(event);
  }

  click() {
    this.dispatchEvent({ type: "click" });
  }

  find(predicate) {
    if (predicate(this)) return this;
    for (const child of this.children) {
      const match = child.find(predicate);
      if (match) return match;
    }
    return null;
  }

  findAll(predicate, matches = []) {
    if (predicate(this)) matches.push(this);
    for (const child of this.children) child.findAll(predicate, matches);
    return matches;
  }
}
