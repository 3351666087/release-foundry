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

test("A3 Report Center report items preserve row-level tenant workspace environment scope", () => {
  const center = buildReportCenterIndex([
    {
      report_id: "a3r_scoped",
      title: "Scoped report",
      source: "mock",
      status: "shareable",
      tenant_scope: {
        organization_id: "org-row",
        tenant_id: "tenant-row",
        workspace_id: "workspace-row",
        project_id: "project-row",
        environment_id: "prod"
      },
      share_link: { token_hash: "hash-row", token_hash_prefix: "hash-row", scope: "private_link" },
      redaction: { status: "passed", blocked: false },
      sealed_evidence: { payload_hash: "abc", hash_algorithm: "sha256", secret_free: true },
      lifecycle: { revocable: true, view_audit_enabled: true },
      view_audit: { view_count: 1 }
    }
  ], { now: "2026-07-10T00:00:00.000Z" });

  assert.equal(center.reports[0].tenant_scope.workspace_id, "workspace-row");
  assert.equal(center.reports[0].tenant_scope.environment_id, "prod");
  assert.equal(center.reports[0].tenant_scope.project_id, "project-row");
});

test("A3 Report Center index exposes export audience governance", () => {
  const center = buildReportCenterIndex([
    {
      report_id: "a3r_audience",
      title: "Audience-governed report",
      source: "mock",
      status: "shareable",
      share_link: { token_hash: "hash-audience", token_hash_prefix: "hash-audience", scope: "private_link" },
      redaction: { status: "passed", blocked: false },
      sealed_evidence: { payload_hash: "abc", hash_algorithm: "sha256", secret_free: true },
      lifecycle: { revocable: true, view_audit_enabled: true },
      view_audit: { view_count: 1 },
      release_evidence_summary: { available: true }
    }
  ], { now: "2026-07-10T00:00:00.000Z" });

  assert.equal(center.export_audience_governance.status, "audience_gates_visible");
  assert.equal(center.export_audience_governance.audiences.some((item) => item.audience === "customer_external" && item.allowed === false), true);
  assert.equal(center.export_audience_governance.audiences.some((item) => item.audience === "reviewer_signoff" && item.allowed === true), true);
});

test("A3 Report Center rows surface allowed audiences from report contract", () => {
  const center = buildReportCenterIndex([
    {
      report_id: "a3r_row_audience",
      title: "Row audience report",
      source: "mock",
      status: "shareable",
      share_link: { token_hash: "hash-ra", token_hash_prefix: "hash-ra", scope: "private_link" },
      redaction: { status: "passed", blocked: false },
      sealed_evidence: { payload_hash: "abc", hash_algorithm: "sha256", secret_free: true },
      lifecycle: { revocable: true, view_audit_enabled: true },
      release_evidence_summary: { available: true }
    }
  ], { now: "2026-07-10T00:00:00.000Z" });

  assert.deepEqual(center.reports[0].export_audience.allowed, ["internal_ops", "reviewer_signoff", "executive_summary"]);
  assert.equal(center.reports[0].export_audience.customer_external_blocked, true);
});

test("A3 Report Center index exposes audience filters, grouped scopes, and external publish blockers", () => {
  const center = buildReportCenterIndex([
    {
      report_id: "a3r_grouped_1",
      title: "Workspace A report",
      source: "mock",
      status: "shareable",
      tenant_scope: {
        organization_id: "org-local",
        tenant_id: "tenant-local",
        workspace_id: "workspace-a",
        project_id: "project-a",
        environment_id: "prod"
      },
      share_link: { token_hash: "hash-ga", token_hash_prefix: "hash-ga", scope: "private_link" },
      redaction: { status: "passed", blocked: false },
      sealed_evidence: { payload_hash: "abc", hash_algorithm: "sha256", secret_free: true },
      lifecycle: { revocable: true, view_audit_enabled: true },
      release_evidence_summary: { available: true }
    },
    {
      report_id: "a3r_grouped_2",
      title: "Workspace B report",
      source: "mock",
      status: "blocked",
      tenant_scope: {
        organization_id: "org-local",
        tenant_id: "tenant-local",
        workspace_id: "workspace-b",
        project_id: "project-b",
        environment_id: "staging"
      },
      share_link: { token_hash: "hash-gb", token_hash_prefix: "hash-gb", scope: "private_link" },
      redaction: { status: "blocked", blocked: true },
      sealed_evidence: { payload_hash: "def", hash_algorithm: "sha256", secret_free: true },
      lifecycle: { revocable: false, view_audit_enabled: true }
    }
  ], { now: "2026-07-10T00:00:00.000Z" });

  assert.equal(center.audience_filters.schema_version, "a3.report_center_audience_filters.v1");
  assert.equal(center.audience_filters.default_filter, "internal_ops");
  assert.equal(center.audience_filters.filters.some((item) => item.audience === "customer_external" && item.state === "blocked"), true);
  assert.equal(center.workspace_groups.groups.some((item) => item.workspace_id === "workspace-a"), true);
  assert.equal(center.environment_groups.groups.some((item) => item.environment_id === "prod"), true);
  assert.equal(center.external_publish_blockers.status, "customer_external_blocked");
  assert.ok(center.external_publish_blockers.prerequisites.includes("public export trust workflow"));
});
