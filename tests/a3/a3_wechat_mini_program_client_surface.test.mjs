import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const PROJECT_CONFIG_PATH = new URL("../../apps/wechat-miniprogram/project.config.json", import.meta.url);
const APP_JSON_PATH = new URL("../../apps/wechat-miniprogram/app.json", import.meta.url);
const CONTRACT_PATH = new URL("../../apps/wechat-miniprogram/contracts/a3-client-surface.contract.js", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md", import.meta.url);

const contract = require("../../apps/wechat-miniprogram/contracts/a3-client-surface.contract.js");

async function loadJson(url) {
  return JSON.parse(await readFile(url, "utf8"));
}

async function assertExists(url, label) {
  await access(url);
  assert.ok(true, `${label} exists`);
}

test("WeChat mini program project config and page declarations exist", async () => {
  const project = await loadJson(PROJECT_CONFIG_PATH);
  const app = await loadJson(APP_JSON_PATH);

  assert.equal(project.appid, "touristappid");
  assert.equal(project.miniprogramRoot, "./");
  assert.equal(project.compileType, "miniprogram");
  assert.ok(Array.isArray(app.pages));
  assert.deepEqual(app.pages, [
    "pages/release-approval/index",
    "pages/incident-alert/index"
  ]);

  for (const page of app.pages) {
    for (const ext of ["js", "json", "wxml", "wxss"]) {
      await assertExists(new URL(`../../apps/wechat-miniprogram/${page}.${ext}`, import.meta.url), `${page}.${ext}`);
    }
  }
});

test("WeChat client-surface contract binds hosted report, release evidence, and reviewer workflow", () => {
  assert.equal(contract.schema_version, "a3.wechat_mini_program_client_surface.v1");
  assert.equal(contract.surface_id, "wechat-mini-program-client-surface");

  const serialized = JSON.stringify(contract);
  const requiredTerms = [
    "A3 hosted report",
    "A3 release evidence",
    "A3 reviewer workflow",
    "hosted_report_snapshot",
    "release_evidence_summary",
    "reviewer_workflow_board",
    "A1 RunResult",
    "A1 Trace",
    "A1 ToolCall",
    "A2 GradeResult",
    "A2 ReleaseGate",
    "A2 CommercialReadiness"
  ];

  for (const term of requiredTerms) {
    assert.ok(serialized.includes(term), `missing contract term: ${term}`);
  }

  const routes = contract.pages.map((page) => page.route);
  assert.ok(routes.includes("pages/release-approval/index"));
  assert.ok(routes.includes("pages/incident-alert/index"));
  assert.ok(contract.api_contract.reads.some((api) => api.path === "/api/a3/releases/:releaseId/evidence-summary"));
  assert.ok(contract.api_contract.reads.some((api) => api.path === "/api/a3/review/workflow"));
});

test("WeChat contract declares tenant, RBAC, usage, audit, and redaction guardrails", () => {
  const guardrails = contract.tenant_auth_rbac_usage_audit_redaction_guardrails;

  for (const key of ["tenant", "auth", "rbac", "usage", "audit", "redaction"]) {
    assert.equal(typeof guardrails[key], "string", `missing guardrail: ${key}`);
    assert.equal(guardrails[key].length > 20, true, `guardrail too short: ${key}`);
  }

  assert.equal(contract.storage_policy.noPersistentToken, true);
  assert.equal(contract.storage_policy.noCookie, true);
  assert.equal(contract.storage_policy.noRawKey, true);
  assert.equal(contract.storage_policy.noWxStorageToken, true);

  for (const forbidden of ["token", "cookie", "Authorization", "api_key", "raw_key", "raw_signed_url"]) {
    assert.ok(contract.storage_policy.forbidden_fields.includes(forbidden), `missing forbidden field: ${forbidden}`);
  }
});

test("WeChat mini program source avoids local secret persistence APIs", async () => {
  const sourcePaths = [
    CONTRACT_PATH,
    new URL("../../apps/wechat-miniprogram/app.js", import.meta.url),
    new URL("../../apps/wechat-miniprogram/pages/release-approval/index.js", import.meta.url),
    new URL("../../apps/wechat-miniprogram/pages/incident-alert/index.js", import.meta.url)
  ];

  for (const sourcePath of sourcePaths) {
    const source = await readFile(sourcePath, "utf8");
    assert.doesNotMatch(source, /wx\.setStorage(?:Sync)?\s*\(/, `${sourcePath.pathname} uses wx storage`);
    assert.doesNotMatch(source, /localStorage|sessionStorage/, `${sourcePath.pathname} uses browser storage`);
    assert.doesNotMatch(source, /Bearer\s+[A-Za-z0-9._-]+/);
    assert.doesNotMatch(source, /gh[pousr]_[A-Za-z0-9_]+/);
    assert.doesNotMatch(source, /AKIA[0-9A-Z]{16}/);
  }
});

test("WeChat mini program documentation preserves API DB event artifact and A1/A2 integration terms", async () => {
  const doc = await readFile(DOC_PATH, "utf8");
  const requiredTerms = [
    "API Contract",
    "DB Contract",
    "Event Contract",
    "Artifact Contract",
    "Tenant / Auth / RBAC / Usage / Audit / Redaction",
    "A1 RunResult",
    "A1 Trace",
    "A2 GradeResult",
    "A2 ReleaseGate",
    "A3 hosted report",
    "A3 release evidence",
    "does not alter A1 runner semantics or A2 judge semantics"
  ];

  for (const term of requiredTerms) {
    assert.ok(doc.includes(term), `missing doc term: ${term}`);
  }
});
