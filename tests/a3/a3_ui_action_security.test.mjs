import assert from "node:assert/strict";
import test from "node:test";

import {
  A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION,
  preflightA3UiAction,
  validateA3UiActionSecurityPreflight
} from "../../services/report/a3_ui_action_security.mjs";

const HASH = "a".repeat(64);
const SCOPE = {
  organization_id: "org-acme",
  tenant_id: "tenant-acme",
  workspace_id: "workspace-main",
  project_id: "project-releasefoundry",
  environment_id: "production"
};

const ACTION_CASES = [
  ["reviewer.approve", "reviewer", ["release:approve"]],
  ["reviewer.deny", "reviewer", ["release:review"]],
  ["reviewer.waiver", "reviewer", ["release:review"]],
  ["hosted_report.create", "owner", ["reports:create", "reports:share"]],
  ["hosted_report.revoke", "owner", ["reports:revoke"]],
  ["hosted_report.export", "developer", ["reports:create"]]
];

for (const [action, role, permissions] of ACTION_CASES) {
  test(`allows metadata-only preflight for ${action}`, () => {
    const decision = preflightA3UiAction(validInput(action, role, permissions));

    assert.equal(decision.schema_version, A3_UI_ACTION_SECURITY_PREFLIGHT_SCHEMA_VERSION);
    assert.equal(decision.allowed, true);
    assert.deepEqual(decision.blockers, []);
    assert.deepEqual(decision.required_permissions, permissions);
    assert.equal(decision.audit_event_skeleton.payload_inline, false);
    assert.match(decision.audit_event_skeleton.payload_hash, /^[a-f0-9]{64}$/);
    assert.equal(decision.usage_meter_intent.disposition, "record_after_executor_accepts");
    assert.equal(decision.execution_boundary.cloud_write_performed, false);
    assert.equal(validateA3UiActionSecurityPreflight(decision).valid, true);
  });
}

test("fails closed without hosted authentication or an active session reference", () => {
  const input = validInput("reviewer.approve", "reviewer", ["release:approve"]);
  input.auth = { authenticated: false, auth_state: "anonymous", scope: SCOPE };
  input.session = { state: "missing", scope: SCOPE };
  assertBlockers(input, ["authentication_required", "active_session_required"]);
});

test("fails closed when any bound scope differs", () => {
  const input = validInput("reviewer.deny", "reviewer", ["release:review"]);
  input.actor.scope = { ...SCOPE, tenant_id: "tenant-other" };
  assertBlockers(input, ["scope_mismatch"]);
});

test("fails closed when the role or declared permissions are insufficient", () => {
  const input = validInput("reviewer.approve", "admin", ["release:approve"]);
  assertBlockers(input, ["permission_denied"]);
});

for (const [category, mutation] of [
  ["token", (input) => { input.payload.authorization = "Bearer abcdefghijklmnop"; }],
  ["email", (input) => { input.payload.reviewer_email = "reviewer@example.test"; }],
  ["signed_url", (input) => { input.payload.download = "https://storage.test/a?X-Amz-Signature=abcdef"; }],
  ["secret", (input) => { input.payload.api_key = "not-returned"; }]
]) {
  test(`fails closed when a raw ${category} is supplied and never echoes it`, () => {
    const input = validInput("hosted_report.export", "developer", ["reports:create"]);
    mutation(input);
    const decision = preflightA3UiAction(input);

    assert.equal(decision.allowed, false);
    assert.ok(decision.blockers.some((item) => item.code === `raw_${category}_detected`));
    assert.ok(decision.redaction_summary.categories.includes(category));
    assert.equal(JSON.stringify(decision).includes("reviewer@example.test"), false);
    assert.equal(JSON.stringify(decision).includes("abcdefghijklmnop"), false);
    assert.equal(JSON.stringify(decision).includes("X-Amz-Signature"), false);
    assert.equal(JSON.stringify(decision).includes("not-returned"), false);

    const sameCategoryInput = validInput("hosted_report.export", "developer", ["reports:create"]);
    if (category === "secret") sameCategoryInput.payload.api_key = "different-secret-value";
    if (category === "token") sameCategoryInput.payload.authorization = "Bearer differenttokenvalue";
    if (category === "email") sameCategoryInput.payload.reviewer_email = "different@example.test";
    if (category === "signed_url") sameCategoryInput.payload.download = "https://other.test/b?X-Amz-Signature=different";
    const sameCategoryDecision = preflightA3UiAction(sameCategoryInput);
    assert.equal(decision.audit_event_skeleton.payload_hash, sameCategoryDecision.audit_event_skeleton.payload_hash);
  });
}

test("fails closed without a metadata-only audit envelope", () => {
  const input = validInput("hosted_report.revoke", "owner", ["reports:revoke"]);
  delete input.audit_envelope;
  assertBlockers(input, ["audit_envelope_required"]);
});

test("accepts explicit secret indirection but rejects a raw value disguised as a ref", () => {
  const allowedInput = validInput("hosted_report.export", "developer", ["reports:create"]);
  allowedInput.payload.secret_ref = "vault:reports/export-key";
  assert.equal(preflightA3UiAction(allowedInput).allowed, true);

  const blockedInput = validInput("hosted_report.export", "developer", ["reports:create"]);
  blockedInput.payload.secret_ref = "plaintext-secret-value";
  assertBlockers(blockedInput, ["raw_secret_detected"]);
});

test("rejects raw session identifiers as token material", () => {
  const input = validInput("reviewer.waiver", "reviewer", ["release:review"]);
  input.session.session_id = "opaque-session-credential";
  assertBlockers(input, ["raw_token_detected"]);
});

test("fails closed without valid A1 and A2 evidence references", () => {
  const input = validInput("hosted_report.create", "owner", ["reports:create", "reports:share"]);
  input.evidence = { a1: [], a2: [{ ref: "grade:1", sha256: "bad" }] };
  assertBlockers(input, ["a1_evidence_references_required", "a2_evidence_reference_invalid"]);
});

test("unknown actions fail closed and still cannot execute", () => {
  const decision = preflightA3UiAction(validInput("reviewer.publish_everything", "owner", []));
  assert.equal(decision.allowed, false);
  assert.ok(decision.blockers.some((item) => item.code === "unknown_action"));
  assert.equal(decision.execution_boundary.executor_invoked, false);
});

function validInput(action, role, permissions) {
  return {
    action,
    auth: { authenticated: true, auth_state: "hosted_session", scope: { ...SCOPE } },
    session: { state: "active", session_ref: "session:hashed-reference", scope: { ...SCOPE } },
    scope: { ...SCOPE },
    actor: { role, permissions, actor_hash: HASH, scope: { ...SCOPE } },
    payload: { release_ref: "release:2026-07", reason_ref: "reason:review-note" },
    evidence: {
      a1: [{ ref: "artifact:a1-run-result", sha256: "b".repeat(64) }],
      a2: [{ ref: "artifact:a2-release-gate", sha256: "c".repeat(64) }]
    },
    audit_envelope: {
      schema_version: "releasefoundry.event_envelope.v1",
      event_ref: "event:preflight-request",
      request_ref: "request:ui-action",
      trace_ref: "trace:ui-action",
      resource_ref: "release:2026-07",
      payload_inline: false
    }
  };
}

function assertBlockers(input, expectedCodes) {
  const decision = preflightA3UiAction(input);
  assert.equal(decision.allowed, false);
  for (const code of expectedCodes) {
    assert.ok(decision.blockers.some((item) => item.code === code), `missing blocker ${code}`);
  }
  assert.equal(decision.execution_boundary.cloud_write_performed, false);
}
