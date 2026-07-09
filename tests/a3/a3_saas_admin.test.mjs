import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildSaasAdminActionRequest,
  buildSaasAdminConsole,
  planSaasAdminAction,
  summarizeSaasAdminActionRequests
} from "../../services/report/a3_saas_admin.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 SaaS admin console models login, team, usage, API keys, and trust without secrets", async () => {
  const runs = await loadJson("../../fixtures/a3/mock_run_results.json");
  const grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
  const usage = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
  const usageApiProbe = await loadJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
  const authCheck = await loadJson("../../fixtures/a3/p3/ashr_auth_check.redacted.json");
  const frontendSummary = await loadJson("../../fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json");

  const admin = buildSaasAdminConsole({
    runFixture: runs,
    gradeFixture: grades,
    usageQuota: usage,
    usageQuotaApiProbe: usageApiProbe,
    authCheck,
    frontendSummary
  });

  assert.equal(admin.schema_version, "a3.saas_admin_console.v1");
  assert.equal(admin.login.status, "observed_read_only");
  assert.equal(admin.team.invite_mode, "disabled_until_auth");
  assert.equal(admin.rbac.status, "contract_ready");
  assert.equal(admin.api_keys.status, "metadata_only");
  assert.ok(admin.api_keys.lifecycle.some((item) => item.step === "rotate"));
  assert.equal(admin.usage.status, "frontend_calibrated");
  assert.equal(admin.usage.plan_snapshot.quota_mutations_enabled, false);
  assert.equal(admin.trust.publish_enabled, false);
  assert.equal(admin.trust.trust_center.public_publish_enabled, false);
  assert.ok(admin.cloud_management.resources.some((item) => item.type === "project"));
  assert.ok(admin.product_console_map.some((item) => item.page === "Team"));
  assert.equal(admin.safety.real_api_key_secrets_enabled, false);
  assert.equal(admin.a1_a2_compatibility.a1_run_result_ready, true);
  assert.equal(admin.a1_a2_compatibility.a2_grade_result_ready, true);

  const serialized = JSON.stringify(admin);
  assert.doesNotMatch(serialized, /gho_|sk-|github_pat_|Bearer [A-Za-z0-9]/);
  assert.match(serialized, /\[REDACTED\]/);
});

test("A3 SaaS admin actions are explicit read-only or plan-only guardrails", () => {
  const invite = planSaasAdminAction("invite_teammate", {});
  assert.equal(invite.mode, "plan_only");
  assert.equal(invite.enabled, false);
  assert.equal(invite.writes_real_ashr_cloud, false);
  assert.equal(invite.secret_values_included, false);

  const rbac = planSaasAdminAction("configure_rbac", {});
  assert.equal(rbac.mode, "contract_ready");
  assert.equal(rbac.enabled, true);
  assert.equal(rbac.writes_real_ashr_cloud, false);

  const usageLimit = planSaasAdminAction("manage_usage_limit", {});
  assert.equal(usageLimit.mode, "plan_only");
  assert.equal(usageLimit.enabled, false);

  const usage = planSaasAdminAction("view_usage", {
    usage: { available: true, direct_api_accessible: false, guidance: "OAuth-gated functions confirmed." }
  });
  assert.equal(usage.enabled, true);
  assert.match(usage.reason, /OAuth-gated/);

  const trust = planSaasAdminAction("publish_trust_report", {
    releaseGate: { decision: "block_release" }
  });
  assert.equal(trust.enabled, false);
  assert.match(trust.next_step, /Fix blocking release-gate/);
});

test("A3 SaaS admin action requests record guardrails without cloud writes or secrets", () => {
  const plan = planSaasAdminAction("rotate_api_key", {
    organizationId: "org-unit",
    projectId: "project-unit",
    createdAt: "2026-07-08T00:00:00.000Z"
  });
  const request = buildSaasAdminActionRequest("rotate_api_key", {
    plan,
    requestId: "aar_unit_rotate",
    actorHash: "actor_hash_only",
    requestedAt: "2026-07-08T00:00:00.000Z"
  });

  assert.equal(request.schema_version, "a3.saas_admin_action_request.v1");
  assert.equal(request.status, "recorded_plan_only");
  assert.equal(request.real_cloud_mutation_performed, false);
  assert.equal(request.secret_values_included, false);
  assert.equal(request.safety.raw_api_key_values_allowed, false);

  const summary = summarizeSaasAdminActionRequests([request]);
  assert.equal(summary.request_count, 1);
  assert.equal(summary.pending_count, 1);
  assert.equal(summary.real_cloud_mutations_performed, false);
});
