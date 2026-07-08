import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { buildA3ArtifactRegistry } from "../../services/report/a3_artifact_registry.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 artifact registry turns reports and control-plane state into audit entries", () => {
  const registry = buildA3ArtifactRegistry({
    source: "mock",
    reportCenter: {
      source: "mock",
      tenant_scope: { organization_id: "org-test", project_id: "project-test" },
      reports: [{
        report_id: "a3r_test",
        source: "mock",
        status: "shareable",
        share_link: { scope: "private_link", token_hash_prefix: "abc123def456" },
        redaction: { status: "passed", blocked: false },
        sealed_evidence: { payload_hash_present: true, secret_free: true },
        manifest: { missing: [], redaction_status: "passed" }
      }]
    },
    usageLedger: { schema_version: "a3.usage_ledger.v1", meters: [{ meter: "runs", quantity: 1 }] },
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", status: "contract_ready", migration_count: 7 },
    productConsole: { schema_version: "a3.product_console.v1" },
    saasAdmin: { schema_version: "a3.saas_admin_console.v1" }
  });

  assert.equal(registry.schema_version, "a3.artifact_registry.v1");
  assert.equal(registry.registry_status, "evidence_available");
  assert.equal(registry.summary.report_artifact_count, 4);
  assert.equal(registry.summary.control_artifact_count, 7);
  assert.equal(registry.summary.billable_meter_count >= 4, true);
  assert.ok(registry.entries.some((item) => item.artifact_type === "hosted_report" && item.lifecycle_state === "shared"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "usage_ledger"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_check_publish_receipt"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_pr_comment_publish_receipt"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_required_check_plan"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "github_pr_gate_packet"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "security_audit_packet"));
  assert.equal(registry.safety.raw_secret_values_allowed, false);
  assert.equal(registry.safety.raw_share_tokens_stored, false);

  const serialized = JSON.stringify(registry);
  assert.doesNotMatch(serialized, /Bearer [A-Za-z0-9]/);
  assert.doesNotMatch(serialized, /Cookie:/);
  assert.doesNotMatch(serialized, /ASHR_API_KEY=/);
});

test("A3 artifact registry keeps empty projects honest", () => {
  const registry = buildA3ArtifactRegistry();

  assert.equal(registry.registry_status, "evidence_available");
  assert.equal(registry.summary.report_artifact_count, 0);
  assert.equal(registry.summary.control_artifact_count, 7);
  assert.ok(registry.next_actions.some((item) => item.includes("Create a hosted report")));
  assert.ok(registry.entries.every((item) => item.raw_secret_values_allowed === false));
});

test("A3 artifact registry includes GitHub publish evidence controls", async () => {
  const registry = buildA3ArtifactRegistry({
    source: "mock",
    githubPublishEvidence: {
      schema_version: "a3.github_publish_evidence.v1",
      check_publish: await loadJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
      pr_comment_publish: await loadJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
      required_check_plan: await loadJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json")
    }
  });

  const check = registry.entries.find((item) => item.artifact_type === "github_check_publish_receipt");
  const comment = registry.entries.find((item) => item.artifact_type === "github_pr_comment_publish_receipt");
  const required = registry.entries.find((item) => item.artifact_type === "github_required_check_plan");

  assert.equal(check.lifecycle_state, "generated");
  assert.equal(comment.lifecycle_state, "generated");
  assert.equal(required.lifecycle_state, "generated");
  assert.equal(check.raw_secret_values_allowed, false);
  assert.equal(comment.raw_secret_values_allowed, false);
  assert.equal(required.raw_secret_values_allowed, false);
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "github_pr_gate_packet"));
  assert.doesNotMatch(JSON.stringify(registry), /Authorization|Bearer|gh[pousr]_|C:\\Users/);
});
