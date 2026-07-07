import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  buildSaasAdminConsole,
  planSaasAdminAction
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
  assert.equal(admin.api_keys.status, "metadata_only");
  assert.equal(admin.usage.status, "frontend_calibrated");
  assert.equal(admin.trust.publish_enabled, false);
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
