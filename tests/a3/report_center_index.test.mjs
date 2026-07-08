import assert from "node:assert/strict";
import { test } from "node:test";

import { buildReportCenterIndex } from "../../services/report/a3_report_center.mjs";

test("A3 Report Center index summarizes hosted report lifecycle and manifest readiness", () => {
  const center = buildReportCenterIndex([
    {
      report_id: "a3r_shareable",
      title: "Shareable release report",
      source: "mock",
      status: "shareable",
      share_url_path: "/reports/a3r_shareable",
      share_link: {
        token_hash: "hash-shareable",
        token_hash_prefix: "hash-shareabl",
        scope: "private_link"
      },
      created_at: "2026-07-07T00:00:00.000Z",
      expires_at: "2026-07-08T00:00:00.000Z",
      lifecycle: { revocable: true, view_audit_enabled: true },
      view_audit: { view_count: 3 },
      redaction: { status: "passed", blocked: false, residual_finding_count: 0 },
      sealed_evidence: {
        payload_hash: "abc123",
        hash_algorithm: "sha256",
        secret_free: true
      },
      artifacts: [
        { id: "json_report", sha256: "jsonhash" },
        { id: "markdown_report", sha256: "mdhash" },
        { id: "hosted_report", sha256: "htmlhash" }
      ]
    },
    {
      report_id: "a3r_revoked",
      title: "Revoked report",
      source: "mock",
      status: "revoked",
      revoked_at: "2026-07-07T01:00:00.000Z",
      redaction: { status: "passed", blocked: false },
      sealed_evidence: { payload_hash: "def456", hash_algorithm: "sha256", secret_free: true }
    }
  ], {
    source: "mock",
    now: "2026-07-07T12:00:00.000Z",
    usageLedger: { schema_version: "a3.usage_ledger.v1", meters: [{ meter: "runs", quantity: 1 }] },
    migrationPlan: { schema_version: "a3.sql_migration_plan.v1", migration_count: 6, status: "contract_ready" }
  });

  assert.equal(center.schema_version, "a3.report_center_index.v1");
  assert.equal(center.summary.report_count, 2);
  assert.equal(center.summary.shareable_count, 1);
  assert.equal(center.summary.revoked_count, 1);
  assert.equal(center.summary.total_view_count, 3);
  assert.ok(center.summary.artifact_registry_count >= 8);
  assert.ok(center.summary.artifact_billable_meter_count >= 4);
  assert.equal(center.control_plane.usage_meter_count, 1);
  assert.equal(center.control_plane.migration_count, 6);
  assert.equal(center.control_plane.live_cloud_mutations_enabled, false);
  assert.ok(center.reports[0].manifest.completeness_score >= 80);
  assert.equal(center.reports[0].redaction.status, "passed");
  assert.equal(center.reports[0].share_link.raw_token_stored, false);
  assert.equal(center.reports[0].share_link.token_hash_prefix, "hash-shareabl");
  assert.equal(center.reports[1].status, "revoked");
  assert.equal(center.artifact_registry.schema_version, "a3.artifact_registry.v1");
  assert.ok(center.artifact_registry.entries.some((item) => item.artifact_type === "hosted_report"));
});

test("A3 Report Center index keeps empty state actionable without pretending reports exist", () => {
  const center = buildReportCenterIndex([], {
    usageLedger: {},
    migrationPlan: {}
  });

  assert.equal(center.summary.report_count, 0);
  assert.equal(center.summary.manifest_ready_count, 0);
  assert.equal(center.artifact_registry.summary.report_artifact_count, 0);
  assert.ok(center.next_actions.some((item) => item.includes("Create the first hosted report")));
  assert.equal(center.control_plane.billing_mutations_enabled, false);
});
