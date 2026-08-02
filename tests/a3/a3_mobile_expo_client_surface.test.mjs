import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const packageJson = JSON.parse(readFileSync("apps/mobile/package.json", "utf8"));
const appJson = JSON.parse(readFileSync("apps/mobile/app.json", "utf8"));
const readme = readFileSync("apps/mobile/README.md", "utf8");
const contractSource = readFileSync("apps/mobile/src/release-intelligence-contract.ts", "utf8");
const screenSource = readFileSync("apps/mobile/src/screens/ReleaseApprovalScreen.contract.tsx", "utf8");
const doc = readFileSync("docs/a3/p3_mobile_expo_client_surface_2026_07_09.md", "utf8");

test("A3 mobile package declares a React Native / Expo client surface", () => {
  assert.equal(packageJson.name, "@releasefoundry/a3-mobile");
  assert.equal(packageJson.private, true);
  assert.match(packageJson.description, /React Native \/ Expo/i);
  assert.ok(packageJson.dependencies.expo);
  assert.ok(packageJson.dependencies["react-native"]);
  assert.equal(appJson.expo.extra.surface, "a3-mobile-release-intelligence");
  assert.equal(appJson.expo.extra.realCloudMutationsEnabled, false);
});

test("A3 mobile contract binds release evidence, hosted reports, and reviewer workflow", () => {
  for (const expected of [
    "GET /api/a3/dashboard",
    "GET /api/a3/review/workflow",
    "GET /api/a3/reports/:reportId",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "ReleaseEvidence",
    "HostedReport",
    "ReviewerWorkflow"
  ]) {
    assert.match(contractSource, new RegExp(escapeRegExp(expected)));
  }
  assert.match(screenSource, /Release Approval/);
  assert.match(screenSource, /approval_requires_hosted_auth_rbac_and_audit/);
});

test("A3 mobile contract stays downstream of A1 and A2 evidence", () => {
  for (const expected of [
    "RunResult",
    "Trace",
    "Observation",
    "ToolCall",
    "GradeResult",
    "score",
    "pass_fail",
    "release_gate",
    "failure_taxonomy"
  ]) {
    assert.match(contractSource, new RegExp(escapeRegExp(expected)));
  }
  assert.match(contractSource, /never_redefines_runner_semantics: true/);
  assert.match(contractSource, /never_redefines_judge_semantics: true/);
});

test("A3 mobile surface declares tenant auth RBAC usage audit and redaction guardrails", () => {
  for (const expected of [
    "tenant_scope_required",
    "hosted_auth_required_for_mutation",
    "rbac_required_for_approval",
    "usage_meter_visible",
    "audit_event_required_for_review_action",
    "store_raw_api_key: false",
    "store_cookie: false",
    "store_authorization_header: false",
    "store_raw_share_token: false",
    "render_signed_media_url: false"
  ]) {
    assert.match(contractSource, new RegExp(escapeRegExp(expected)));
  }
});

test("A3 mobile docs preserve API DB event artifact and A1/A2/A3 integration boundaries", () => {
  for (const expected of [
    "API / DB / Event / Artifact Contract",
    "Tenant / Auth / RBAC / Usage / Audit",
    "A1",
    "A2",
    "A3",
    "RunResult",
    "GradeResult",
    "Release Evidence"
  ]) {
    assert.match(doc, new RegExp(escapeRegExp(expected)));
  }
});

test("A3 mobile surface does not include high-confidence secret patterns or local persistence APIs", () => {
  const combined = [readme, contractSource, screenSource, doc].join("\n");
  assert.doesNotMatch(combined, /RELEASEFOUNDRY_API_KEY\s*=/);
  assert.doesNotMatch(combined, /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i);
  assert.doesNotMatch(combined, /(^|\n)Cookie:\s*(?!\[REDACTED\])/i);
  assert.doesNotMatch(combined, /github_pat_|ghp_|AKIA[0-9A-Z]{16}/);
  assert.doesNotMatch(combined, /AsyncStorage|SecureStore|localStorage|document\.cookie/);
});

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
