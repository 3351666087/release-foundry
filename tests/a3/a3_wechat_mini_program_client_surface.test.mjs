import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const project = require("../../apps/wechat-miniprogram/project.config.json");
const app = require("../../apps/wechat-miniprogram/app.json");
const contract = require("../../apps/wechat-miniprogram/contracts/a3-client-surface.contract.js");
const apiClient = require("../../apps/wechat-miniprogram/utils/api-client.js");
const releaseCenter = require("../../apps/wechat-miniprogram/services/release-center.js");

const ROOT = new URL("../../apps/wechat-miniprogram/", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_wechat_mini_program_client_surface_2026_07_09.md", import.meta.url);
const PAGE_ROUTES = [
  "pages/workbench/index",
  "pages/release-approval/index",
  "pages/incident-alert/index",
  "pages/account/index"
];

test("WeChat release center declares a four-tab enterprise information architecture", async () => {
  assert.equal(project.appid, "touristappid");
  assert.equal(project.projectname, "ashr-release-center-wechat");
  assert.equal(project.miniprogramRoot, "./");
  assert.equal(project.compileType, "miniprogram");
  assert.deepEqual(app.pages, PAGE_ROUTES);
  assert.deepEqual(app.tabBar.list.map((item) => item.text), ["工作台", "审批", "告警", "账户"]);

  for (const page of PAGE_ROUTES) {
    for (const ext of ["js", "json", "wxml", "wxss"]) {
      await access(new URL(`${page}.${ext}`, ROOT));
    }
  }
});

test("WeChat contract keeps source provenance internal and customer terminology product-facing", () => {
  assert.equal(contract.schema_version, "a3.wechat_mini_program_client_surface.v2");
  assert.equal(contract.customer_brand, "Ashr 发布中心");
  assert.deepEqual(contract.pages.map((page) => page.route), PAGE_ROUTES);
  assert.deepEqual(contract.customer_facing_terminology.slice(0, 4), ["执行证据", "评测结论", "发布决策", "人工审批"]);
  assert.equal(contract.internal_source_provenance.visibility, "contract_metadata_only_not_customer_ui");

  const provenance = JSON.stringify(contract.internal_source_provenance);
  for (const term of ["A1 RunResult", "A1 Trace", "A1 ToolCall", "A2 GradeResult", "A2 ReleaseGate", "A2 DecisionLedger"]) {
    assert.ok(provenance.includes(term), `missing internal provenance term: ${term}`);
  }

  const preflight = contract.api_contract.guarded_requests.find((item) => item.path === "/api/a3/ui-actions/preflight");
  assert.equal(preflight.status, "implemented_preflight_only");
  assert.equal(preflight.writes_release_state, false);
  assert.equal(contract.capability_status.review_mutation, "not_implemented_preflight_only");
  assert.match(contract.capability_status.wechat_identity, /not_implemented/);
});

test("customer-facing mini program templates expose no internal lane labels", async () => {
  for (const route of PAGE_ROUTES) {
    const wxml = await readFile(new URL(`${route}.wxml`, ROOT), "utf8");
    assert.doesNotMatch(wxml, /\bA[123]\b|WeChat Mini Program|Release Approval|Incident Alert/);
  }

  const appText = JSON.stringify(app);
  assert.doesNotMatch(appText, /\bA[123]\b|Release Approval|Incident Alert/);
  assert.match(await readFile(new URL("pages/workbench/index.wxml", ROOT), "utf8"), /执行证据/);
  assert.match(await readFile(new URL("pages/release-approval/index.wxml", ROOT), "utf8"), /发布决策/);
  assert.match(await readFile(new URL("pages/incident-alert/index.wxml", ROOT), "utf8"), /事件时间线/);
  assert.match(await readFile(new URL("pages/account/index.wxml", ROOT), "utf8"), /生产能力状态/);

  for (const file of ["preview/index.html", "preview/preview.css", "preview/preview.js"]) {
    await access(new URL(file, ROOT));
  }
  const preview = await readFile(new URL("preview/index.html", ROOT), "utf8");
  assert.doesNotMatch(preview, /\bA[123]\b/);
  assert.match(preview, /data-page="workbench"/);
  assert.match(preview, /data-page="approval"/);
  assert.match(preview, /data-page="incidents"/);
  assert.match(preview, /data-page="account"/);
});

test("mini program source does not persist credentials or embed authorization material", async () => {
  const sourcePaths = [
    "app.js",
    "utils/api-client.js",
    "services/release-center.js",
    ...PAGE_ROUTES.map((route) => `${route}.js`)
  ];

  for (const relativePath of sourcePaths) {
    const source = await readFile(new URL(relativePath, ROOT), "utf8");
    assert.doesNotMatch(source, /wx\.setStorage(?:Sync)?\s*\(/, `${relativePath} uses wx storage`);
    assert.doesNotMatch(source, /localStorage|sessionStorage/, `${relativePath} uses browser storage`);
    assert.doesNotMatch(source, /gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|AKIA[0-9A-Z]{16}/);
  }

  assert.equal(contract.storage_policy.noPersistentToken, true);
  assert.equal(contract.storage_policy.noCookie, true);
  assert.equal(contract.storage_policy.noRawKey, true);
  assert.deepEqual(contract.storage_policy.allowed_local_state, []);
});

test("HTTPS API client allowlists routes and rejects sensitive request or response material", async () => {
  assert.equal(apiClient.normalizeApiBaseUrl("https://release.example.test"), "https://release.example.test");
  assert.equal(apiClient.normalizeApiBaseUrl("http://release.example.test"), "");
  assert.equal(apiClient.normalizeApiBaseUrl("https://user:pass@release.example.test"), "");
  assert.equal(apiClient.isAllowedPath("/api/a3/health", "GET"), true);
  assert.equal(apiClient.isAllowedPath("/api/a3/dashboard?source=api-ingest", "GET"), true);
  assert.equal(apiClient.isAllowedPath("/api/a3/admin/keys", "GET"), false);
  assert.equal(apiClient.isAllowedPath("/api/a3/ui-actions/preflight", "POST"), true);
  assert.equal(apiClient.isAllowedPath("/api/a3/ui-actions/preflight", "GET"), false);

  const descriptor = apiClient.buildRequestDescriptor(
    "https://release.example.test",
    "/api/a3/health"
  );
  assert.equal(descriptor.url, "https://release.example.test/api/a3/health");
  assert.equal(Object.hasOwn(descriptor.header, "Authorization"), false);
  assert.equal(descriptor.header["X-Client-Surface"], "release-center-miniprogram");

  assert.equal(apiClient.containsSensitiveMaterial({ api_key: "raw-secret" }), true);
  assert.equal(apiClient.containsSensitiveMaterial({ nested: { password: "raw-secret" } }), true);
  assert.equal(apiClient.containsSensitiveMaterial({ api_key: "[REDACTED]" }), false);
  assert.throws(
    () => apiClient.buildRequestDescriptor("https://release.example.test", "/api/a3/ui-actions/preflight", { method: "POST", data: { token: "raw-token" } }),
    (error) => error.code === "request_contains_sensitive_material"
  );

  await assert.rejects(
    apiClient.requestJson("/api/a3/health", {
      config: { apiBaseUrl: "https://release.example.test" },
      wxRuntime: {
        request(options) {
          options.success({ statusCode: 200, data: { password: "must-not-render" } });
        }
      }
    }),
    (error) => error.code === "response_contains_sensitive_material"
  );
});

test("release center recognizes the real health payload and only requests review preflight", async () => {
  const config = { dataMode: "connected", apiBaseUrl: "https://release.example.test" };
  const connection = await releaseCenter.checkConnection({
    config,
    request: async () => ({ ok: true, service: "a3-api" })
  });
  assert.equal(connection.status, "connected");

  let captured;
  const release = {
    id: "release-2026-07",
    version: "rc.3",
    tenantScope: {
      organization_id: "org-acme",
      tenant_id: "tenant-acme",
      workspace_id: "workspace-main",
      project_id: "project-refund",
      environment_id: "staging"
    },
    evidenceRefs: {
      a1: [{ ref: "artifact:run", sha256: "1".repeat(64) }],
      a2: [{ ref: "artifact:grade", sha256: "2".repeat(64) }]
    }
  };
  const result = await releaseCenter.requestReviewPreflight("approve", release, {
    config,
    request: async (path, options) => {
      captured = { path, options };
      return { allowed: false, blockers: [{ code: "authentication_required" }] };
    }
  });
  assert.equal(result.allowed, false);
  assert.equal(captured.path, "/api/a3/ui-actions/preflight");
  assert.equal(captured.options.method, "POST");
  assert.equal(captured.options.data.action, "reviewer.approve");
  assert.deepEqual(captured.options.data.scope, release.tenantScope);
  assert.deepEqual(captured.options.data.evidence, release.evidenceRefs);
  assert.equal(captured.options.data.audit_envelope.payload_inline, false);
  assert.equal(Object.hasOwn(captured.options.data, "Authorization"), false);

  const preview = await releaseCenter.requestReviewPreflight("approve", release, {
    config: { dataMode: "preview", apiBaseUrl: "" },
    request: async () => assert.fail("preview must not call an API")
  });
  assert.deepEqual(preview, { status: "preview_only", allowed: false });
});

test("A1/A2 dashboard projections become customer-facing release evidence without recomputing the decision", () => {
  const snapshot = releaseCenter.normalizeDashboardPayload({
    summary: { totalCases: 3, passed: 3, failed: 0, traceCompleteness: 100 },
    release_evidence_summary: { release_id: "release-refund-01", release_version: "rc.3" },
    delivery_golden_path: { progress: { passed: 7, total: 11 } },
    deployment_handoff: { summary: { passed: 8, total_checks: 17 } },
    release_decision_provenance: {
      status: "blocked",
      release_decision: "block",
      tenant_scope: {
        organization_id: "org-acme",
        tenant_id: "tenant-acme",
        workspace_id: "workspace-main",
        project_id: "project-refund",
        environment_id: "staging"
      },
      blockers: [{ type: "auth_untrusted" }]
    },
    a1_a2_evidence_spine: {
      summary: { case_count: 3, failed_case_count: 0, trace_completeness: 100 },
      stages: [
        { status: "ready", metrics: { run_count: 1, case_count: 3 } },
        { status: "ready", metrics: { judge_result_count: 3, passed_case_count: 3 } },
        { status: "blocked", metrics: { blocker_count: 1, warning_count: 0 } },
        { status: "action_required", metrics: { review_record_count: 0, report_count: 1 } }
      ]
    },
    incident_replay_queue: { queue: [] }
  });

  assert.equal(snapshot.release.status, "blocked");
  assert.equal(snapshot.release.decisionLabel, "暂不可发布");
  assert.equal(snapshot.release.passRateLabel, "3 / 3");
  assert.equal(snapshot.release.progressLabel, "7 / 11");
  assert.equal(snapshot.release.acceptanceLabel, "8 / 17");
  assert.deepEqual(snapshot.release.evidenceStages.map((item) => item.title), ["执行证据", "评测结论", "发布决策", "人工审批"]);
  assert.equal(snapshot.release.blockers[0].title, "企业身份尚未受信");
  assert.equal(snapshot.tasks[0].type, "release");
  assert.doesNotMatch(JSON.stringify(snapshot.release.evidenceStages), /\bA[123]\b/);
});

test("v2 release evidence maps source artifact hashes into preflight references", () => {
  const snapshot = releaseCenter.normalizeReleasePayload({
    release_id: "release-refund-01",
    tenant_scope: {
      organization_id: "org-acme",
      tenant_id: "tenant-acme",
      workspace_id: "workspace-main",
      project_id: "project-refund"
    },
    release_evidence_summary: {
      release_identity: { release_id: "release-refund-01", environment: "staging" },
      health: { overall_status: "blocked", next_action: { action: "publish_github_check", reason: "github_check_missing_or_not_posted", label: "Publish check." } },
      a1_evidence: { run_count: 1, case_count: 3, trace_event_count: 12, missing_required_fields: [] },
      a2_evidence: { grade_count: 3, failed_case_count: 0, missing_required_fields: [] },
      required_check_proof: { enforced: false },
      source_artifacts: {
        artifacts: [
          { source_artifact_id: "run-result", source_lane: "A1", content_hash: "a".repeat(64) },
          { source_artifact_id: "grade-result", source_lane: "A2", content_hash: "b".repeat(64) }
        ]
      }
    },
    next_action: { action: "publish_github_check", reason: "github_check_missing_or_not_posted", label: "需要补齐代码检查回执。" }
  }, { readbacks: [] }, "release-refund-01");

  assert.equal(snapshot.release.status, "blocked");
  assert.equal(snapshot.release.evidenceStages[0].status, "complete");
  assert.equal(snapshot.release.evidenceStages[1].status, "complete");
  assert.equal(snapshot.release.evidenceStages[2].status, "blocked");
  assert.deepEqual(snapshot.release.evidenceRefs.a1, [{ ref: "artifact:run-result", sha256: "a".repeat(64) }]);
  assert.deepEqual(snapshot.release.evidenceRefs.a2, [{ ref: "artifact:grade-result", sha256: "b".repeat(64) }]);
});

test("connected evidence never falls back to preview tenant scope or preview metrics", () => {
  const dashboard = releaseCenter.normalizeDashboardPayload({
    release_decision_provenance: { status: "blocked", blockers: [] }
  });
  assert.equal(dashboard.release.tenantScope.organization_id, "");
  assert.equal(dashboard.release.tenantScope.tenant_id, "");
  assert.equal(dashboard.release.progressLabel, "待校验");
  assert.equal(dashboard.release.acceptanceLabel, "待校验");
  assert.equal(dashboard.release.passRateLabel, "待同步");
  assert.equal(dashboard.release.title, "当前候选版本");

  const release = releaseCenter.normalizeReleasePayload({
    release_id: "release-no-scope",
    release_evidence_summary: {
      health: { overall_status: "blocked" },
      a1_evidence: {},
      a2_evidence: {},
      source_artifacts: { artifacts: [] }
    }
  }, {}, "release-no-scope");
  assert.equal(release.release.tenantScope.organization_id, "");
  assert.equal(release.release.tenantScope.tenant_id, "");
  assert.notEqual(release.release.tenantScope.organization_id, "org-local");
});

test("WeChat documentation records runtime modes, four pages, truth boundaries, and source integration", async () => {
  const doc = await readFile(DOC_PATH, "utf8");
  for (const term of [
    "发布工作台",
    "发布审批",
    "风险告警",
    "账户与连接",
    "preview",
    "connected",
    "preflight",
    "A1 RunResult",
    "A2 GradeResult",
    "does not alter A1 runner semantics or A2 judge semantics"
  ]) {
    assert.ok(doc.includes(term), `missing doc term: ${term}`);
  }
});
