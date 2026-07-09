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
    releaseEvidenceReadbacks: [{
      readback_id: "rerb_registry",
      resource_kind: "github_check",
      readback_status: "readback_confirmed",
      payload_hash: "sha256_registry_readback"
    }],
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", status: "contract_ready", migration_count: 7 },
    productConsole: { schema_version: "a3.product_console.v1" },
    saasAdmin: { schema_version: "a3.saas_admin_console.v1" }
  });

  assert.equal(registry.schema_version, "a3.artifact_registry.v1");
  assert.equal(registry.registry_status, "evidence_available");
  assert.equal(registry.summary.report_artifact_count, 5);
  assert.equal(registry.summary.control_artifact_count, 11);
  assert.equal(registry.summary.billable_meter_count >= 4, true);
  assert.ok(registry.entries.some((item) => item.artifact_type === "hosted_report" && item.lifecycle_state === "shared"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "release_evidence_summary"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "release_evidence_readback" && item.resource_id === "rerb_registry"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "usage_ledger"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_check_publish_receipt"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_pr_comment_publish_receipt"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "github_required_check_plan"));
  assert.ok(registry.entries.some((item) => item.artifact_type === "notification_control_plane"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "github_pr_gate_packet"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "source_evidence_packet"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "security_audit_packet"));
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "notification_readiness_packet"));
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
  assert.equal(registry.summary.control_artifact_count, 10);
  assert.ok(registry.next_actions.some((item) => item.includes("Create a hosted report")));
  assert.ok(registry.entries.every((item) => item.raw_secret_values_allowed === false));
});

test("A3 artifact registry includes billing migration readiness as control and audit evidence", async () => {
  const billingMigrationReadiness = await loadJson("../../fixtures/a3/p3/a3_billing_migration_readiness.redacted.json");
  const registry = buildA3ArtifactRegistry({
    source: "unit",
    usageLedger: { schema_version: "a3.usage_ledger.v1", meters: [{ meter: "usage_units", quantity: 14 }] },
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", status: "contract_ready", migration_count: 7 },
    billingMigrationReadiness: {
      ...billingMigrationReadiness,
      ignored_secret: "sk_live_registry_should_not_escape_1234567890",
      ignored_bearer: "Authorization: Bearer registry-secret"
    }
  });

  const entry = registry.entries.find((item) => item.artifact_type === "billing_migration_readiness");
  assert.equal(entry.lifecycle_state, "generated");
  assert.equal(entry.redaction_status, "metadata_only");
  assert.equal(entry.billable_meter, "billing_readiness_artifacts");
  assert.match(entry.customer_value, /customer-safe billing ledger migration readiness/);
  assert.match(entry.billable_value, /invoice-preview/);
  assert.match(entry.self_host_value, /Postgres billing ledger/);
  assert.match(entry.audit_value, /provider-event hash/);
  assert.equal(entry.missing_controls.includes("a1_authenticated_billing_ledger_read_api"), true);
  assert.equal(entry.raw_secret_values_allowed, false);
  assert.equal(entry.raw_share_token_stored, false);

  const securityPacket = registry.packet_presets.find((item) => item.preset_id === "security_audit_packet");
  const billingPacket = registry.packet_presets.find((item) => item.preset_id === "billing_migration_packet");
  assert.equal(securityPacket.required_artifact_types.includes("billing_migration_readiness"), true);
  assert.equal(billingPacket.required_artifact_types.includes("billing_migration_readiness"), true);
  assert.equal(billingPacket.missing_artifact_types.includes("billing_migration_readiness"), false);

  assert.doesNotMatch(JSON.stringify(registry), /sk_live_registry_should_not_escape|Authorization: Bearer|whsec_|C:\\Users/);
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

test("A3 artifact registry can register A1/A2 source artifact hashes", () => {
  const registry = buildA3ArtifactRegistry({
    source: "unit",
    sourceArtifacts: {
      schema_version: "a3.source_artifacts.v1",
      artifacts: [
        {
          source_artifact_id: "unit:a1_run_result:abc",
          artifact_type: "a1_run_result",
          source_lane: "A1",
          source_contracts: ["RunResult"],
          content_hash: "a".repeat(64),
          record_count: 1,
          redaction_status: "hash_only"
        },
        {
          source_artifact_id: "unit:a2_grade_result:def",
          artifact_type: "a2_grade_result",
          source_lane: "A2",
          source_contracts: ["GradeResult"],
          content_hash: "b".repeat(64),
          record_count: 2,
          redaction_status: "hash_only"
        }
      ]
    }
  });

  const sourceEntries = registry.entries.filter((item) => item.retention_class === "source_evidence");
  assert.equal(sourceEntries.length, 2);
  assert.equal(sourceEntries.every((item) => item.hash_status === "content_hash_present"), true);
  assert.equal(sourceEntries.every((item) => item.raw_payload_embedded === false), true);
  assert.ok(registry.packet_presets.some((item) => item.preset_id === "source_evidence_packet"));
});
