import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";

import {
  A3_DB_CONTRACT,
  A3StoreValidationError,
  createFileBackedA3Store,
  createFixtureBackedA3Store,
  createMemoryA3Store,
  loadA3SourceSnapshot
} from "../../services/report/a3_store.mjs";

async function importJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 store loads fixture sources without claiming database readiness", async () => {
  const snapshot = await loadA3SourceSnapshot("mock");

  assert.equal(snapshot.schema_version, "a3.dashboard_snapshot.v1");
  assert.equal(snapshot.source, "mock");
  assert.equal(snapshot.summary.totalRuns, 1);
  assert.equal(snapshot.summary.totalCases, 32);
  assert.equal(snapshot.storage.db_ready, false);
  assert.equal(snapshot.a2GradeResults.schema_version, "a2.grade_results.v1");
  assert.equal(snapshot.a2ReleaseGate.schema_version, "a2.release_gate.v1");
});

test("A3 fixture-backed store exposes runs, cases, and hosted report payloads", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock", "raw-a2"] });
  const dashboard = await store.getDashboardSnapshot("mock");

  assert.equal(dashboard.schema_version, "a3.api_dashboard_payload.v1");
  assert.equal(dashboard.storage.db_contract.schema_version, A3_DB_CONTRACT.schema_version);
  assert.equal(dashboard.summary.totalCases, 32);
  assert.equal(dashboard.cases.length, 32);
  assert.equal(dashboard.saas_admin_console.schema_version, "a3.saas_admin_console.v1");
  assert.equal(dashboard.saas_admin_console.api_keys.status, "metadata_only");
  assert.equal(dashboard.enterprise_readiness.schema_version, "a3.enterprise_readiness.v1");
  assert.ok(dashboard.enterprise_readiness.enabled_capabilities.length > 0);
  assert.equal(dashboard.storage.db_migrations.schema_version, "a3.sql_migration_plan.v1");
  assert.equal(dashboard.usage_ledger.schema_version, "a3.usage_ledger.v1");
  assert.equal(dashboard.release_evidence_summary.schema_version, "a3.release_evidence_summary.v1");
  assert.equal(dashboard.release_evidence_summary.available, true);
  assert.equal(dashboard.release_evidence_api.raw_fixture_exposed, false);
  assert.equal(dashboard.release_decision_provenance.schema_version, "a3.release_decision_provenance.v1");
  assert.equal(dashboard.release_decision_provenance.status, "blocked");
  assert.equal(dashboard.release_decision_provenance.governance.auth.trusted_identity_backend, false);
  assert.ok(dashboard.release_decision_provenance.blockers.some((item) => item.type === "auth_untrusted"));

  const runs = await store.listRuns({ source: "mock" });
  assert.equal(runs.length, 1);
  assert.equal(runs[0].total_cases, 32);

  const detail = await store.getCase(dashboard.cases[0].case_id, { source: "mock" });
  assert.equal(detail.schema_version, "a3.api_case_detail.v1");
  assert.equal(detail.case.case_id, dashboard.cases[0].case_id);

  const missing = await store.getCase("missing-case", { source: "mock" });
  assert.equal(missing, null);

  const report = await store.createShareableReport({
    source: "mock",
    createdAt: "2026-07-07T00:00:00.000Z",
    shareToken: "unit_store_share_token"
  });
  assert.equal(report.schema_version, "a3.shareable_report.v1");
  assert.equal(report.status, "shareable");
  assert.equal(report.share_url_path, "/r/unit_store_share_token");
  assert.match(report.internal_url_path, /^\/reports\/a3r_/);
  assert.equal(report.sealed_evidence.secret_free, true);
  assert.equal(report.release_evidence_summary.available, true);
  assert.equal(report.release_evidence_snapshot.immutable_in_hosted_report, true);
  const otherTenantReport = await store.createShareableReport({
    source: "mock",
    organizationId: "org-other",
    projectId: "project-other",
    createdAt: "2026-07-07T00:01:00.000Z",
    shareToken: "unit_other_tenant_share_token"
  });

  const releaseEvidence = await store.getReleaseEvidenceSummary("current", { source: "mock" });
  assert.equal(releaseEvidence.schema_version, "a3.release_evidence_api_response.v1");
  assert.equal(releaseEvidence.release_evidence_summary.available, true);
  assert.equal(releaseEvidence.release_evidence_health.schema_version, "a3.release_evidence_health.v1");
  assert.equal(releaseEvidence.next_action.action, "publish_github_check");
  assert.equal(releaseEvidence.safety.raw_fixture_exposed, false);
  assert.ok(releaseEvidence.hosted_report_snapshots.some((item) => item.report_id === report.report_id));
  assert.equal(releaseEvidence.hosted_report_snapshots.some((item) => item.report_id === otherTenantReport.report_id), false);

  const scopedReleaseEvidence = await store.getReleaseEvidenceSummary("current", {
    source: "mock",
    organizationId: "org-local",
    projectId: "project-local"
  });
  assert.equal(scopedReleaseEvidence.schema_version, "a3.release_evidence_api_response.v1");

  const releaseEvidenceV2 = await store.getReleaseEvidenceSummary("current", {
    source: "mock",
    organizationId: "org-local",
    projectId: "project-local",
    version: "2"
  });
  assert.equal(releaseEvidenceV2.schema_version, "a3.release_evidence_api_response.v2");
  assert.equal(releaseEvidenceV2.release_evidence_summary.schema_version, "a3.release_evidence_summary.v2");
  assert.equal(releaseEvidenceV2.release_evidence_summary.a1_evidence.contracts.includes("RunResult"), true);
  assert.equal(releaseEvidenceV2.release_evidence_summary.a2_evidence.contracts.includes("GradeResult"), true);
  assert.equal(releaseEvidenceV2.release_evidence_summary.github_check_readback.readback_status, "readback_confirmed");
  assert.equal(releaseEvidenceV2.release_evidence_summary.pr_comment_readback.readback_status, "readback_confirmed");
  assert.equal(releaseEvidenceV2.release_evidence_summary.required_check_proof.enforced, false);
  assert.equal(releaseEvidenceV2.release_evidence_summary.required_check_proof.plan_only_must_not_claim_enforcement, true);
  assert.equal(releaseEvidenceV2.release_evidence_summary.usage_ledger.linked_summary_id, releaseEvidenceV2.summary_id);
  assert.equal(releaseEvidenceV2.compatibility.v1_stable, true);

  const releaseEvidenceDiff = await store.getReleaseEvidenceDiff("current", {
    source: "mock",
    organizationId: "org-local",
    projectId: "project-local"
  });
  assert.equal(releaseEvidenceDiff.schema_version, "a3.release_evidence_diff_api_response.v1");
  assert.equal(releaseEvidenceDiff.diff.schema_version, "a3.release_evidence_diff.v1");
  assert.ok(releaseEvidenceDiff.diff.changed_fields.some((item) => item.field === "schema_version"));
  assert.equal(releaseEvidenceDiff.safety.raw_secret_values_allowed, false);

  const stalePrReadback = {
    schema_version: "a3.github_pr_comment_readback_receipt.v1",
    provider: "github",
    resource_kind: "pr_comment",
    readback_id: "ghprb_store_stale",
    readback_status: "stale",
    stale: true,
    expected: {
      comment_id_alias: 2001,
      body_hash: "expected_hash",
      marker: "<!-- releasefoundry-plus-plus:release-gate:unit -->"
    },
    observed: {
      comment_id_alias: 2001,
      body_hash: "old_hash",
      body_marker_present: true
    },
    matches: {
      marker: true,
      body_hash: false
    },
    safety: {
      token_included: false,
      secret_values_allowed: false,
      raw_body_stored: false
    }
  };
  const readbackReceipt = await store.submitReleaseEvidenceReadback("current", stalePrReadback, {
    source: "mock",
    actor: ["reviewer", "example.com"].join("@"),
    idempotencyKey: "store-readback-1"
  });
  assert.equal(readbackReceipt.schema_version, "a3.release_evidence_readback_capture_receipt.v1");
  assert.equal(readbackReceipt.readback_status, "stale");
  assert.equal(readbackReceipt.idempotency.status, "recorded");
  assert.equal(readbackReceipt.secret_values_included, false);

  const duplicateReadback = await store.submitReleaseEvidenceReadback("current", stalePrReadback, {
    source: "mock",
    actor: ["reviewer", "example.com"].join("@"),
    idempotencyKey: "store-readback-1"
  });
  assert.equal(duplicateReadback.idempotency.duplicate, true);

  const readbackList = await store.listReleaseEvidenceReadbacks("current", { source: "mock" });
  assert.equal(readbackList.schema_version, "a3.release_evidence_readback_list.v1");
  assert.equal(readbackList.readback_count, 1);
  assert.equal(readbackList.status_counts.stale, 1);
  assert.doesNotMatch(JSON.stringify(readbackList), /reviewer@example.com|Bearer|Authorization/);

  const releaseEvidenceAfterReadback = await store.getReleaseEvidenceSummary("current", {
    source: "mock",
    version: "2"
  });
  assert.equal(releaseEvidenceAfterReadback.release_evidence_summary.pr_comment_readback.readback_status, "stale");
  assert.equal(releaseEvidenceAfterReadback.release_evidence_summary.pr_comment_readback.body_hash_match, false);
  assert.equal(releaseEvidenceAfterReadback.readback_records.length, 1);
  assert.equal(releaseEvidenceAfterReadback.readback_records[0].resource_kind, "pr_comment");

  const dashboardAfterReadback = await store.getDashboardSnapshot("mock");
  assert.equal(dashboardAfterReadback.release_evidence_readbacks.schema_version, "a3.release_evidence_readback_dashboard.v1");
  assert.equal(dashboardAfterReadback.release_evidence_readbacks.readback_count, 1);
  assert.equal(dashboardAfterReadback.release_evidence_readbacks.status_counts.stale, 1);
  assert.equal(dashboardAfterReadback.release_evidence_summary.readback_record_count, 1);
  assert.equal(dashboardAfterReadback.release_evidence_summary.readback_records[0].resource_kind, "pr_comment");
  assert.match(dashboardAfterReadback.release_evidence_summary.readback_history.a1_a2_boundary, /A1 RunResult/);
  assert.doesNotMatch(JSON.stringify(dashboardAfterReadback.release_evidence_readbacks), /reviewer@example.com|Bearer|Authorization/);

  const crossTenantReleaseEvidence = await store.getReleaseEvidenceSummary("current", {
    source: "mock",
    organizationId: "org-other"
  });
  assert.equal(crossTenantReleaseEvidence, null);
  assert.equal(await store.getReleaseEvidenceDiff("current", {
    source: "mock",
    organizationId: "org-other"
  }), null);

  const savedReport = await store.getReport(report.report_id);
  assert.equal(savedReport.share_url_path, "/r/[REDACTED_TOKEN]");
  assert.equal(savedReport.share_link.token_hash, undefined);
  assert.match(savedReport.share_link.token_hash_prefix, /^[a-f0-9]{12}$/);
  assert.doesNotMatch(JSON.stringify(savedReport), /unit_store_share_token/);

  const admin = await store.getSaasAdminConsole({ source: "mock" });
  assert.equal(admin.team.members.length, 4);
  assert.equal(admin.safety.real_team_invites_enabled, false);

  const action = await store.planSaasAdminAction("rotate_api_key", { source: "mock" });
  assert.equal(action.mode, "plan_only");
  assert.equal(action.writes_real_releasefoundry_cloud, false);

  const adminRequest = await store.submitSaasAdminAction("rotate_api_key", {
    source: "mock",
    actor: ["reviewer", "example.com"].join("@"),
    reason: "Rotate old key without exposing secret value.",
    target: {
      key_prefix: "releasefoundry_ci_[REDACTED]",
      email: ["reviewer", "example.com"].join("@"),
      token: ["Bearer", "should-not-persist"].join(" ")
    }
  });
  assert.equal(adminRequest.schema_version, "a3.saas_admin_action_receipt.v1");
  assert.equal(adminRequest.status, "recorded_plan_only");
  assert.equal(adminRequest.real_cloud_mutation_performed, false);
  assert.equal(adminRequest.secret_values_included, false);

  const adminRequests = await store.listSaasAdminActionRequests({ source: "mock" });
  assert.equal(adminRequests.schema_version, "a3.saas_admin_action_request_list.v1");
  assert.equal(adminRequests.summary.request_count, 1);
  assert.equal(adminRequests.requests[0].action, "rotate_api_key");
  assert.equal(adminRequests.requests[0].target.email, undefined);
  assert.equal(adminRequests.requests[0].target.token, undefined);
  assert.doesNotMatch(JSON.stringify(adminRequests), new RegExp(`${["reviewer", "example.com"].join("@")}|should-not-persist`));

  const waiver = await importJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
  const approval = await importJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");
  const waiverReceipt = await store.submitReviewWaiver(waiver, {
    source: "mock",
    generatedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(waiverReceipt.schema_version, "a3.review_workflow_receipt.v1");
  assert.equal(waiverReceipt.status, "valid_exceptional_waiver");
  assert.equal(waiverReceipt.accepted, true);

  const approvalReceipt = await store.submitReviewApproval(approval, {
    source: "mock",
    waiver,
    generatedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(approvalReceipt.status, "valid_exception_approval");
  assert.equal(approvalReceipt.accepted, true);

  const denialReceipt = await store.submitReviewDenial(buildDenialFixture(), {
    source: "mock",
    generatedAt: "2026-07-07T12:00:00.000Z",
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha"
  });
  assert.equal(denialReceipt.status, "valid_denial");
  assert.equal(denialReceipt.accepted, true);

  const reviewWorkflow = await store.getReviewWorkflow({ source: "mock" });
  assert.equal(reviewWorkflow.schema_version, "a3.review_workflow_index.v1");
  assert.equal(reviewWorkflow.record_count, 3);
  assert.equal(reviewWorkflow.waiver_count, 1);
  assert.equal(reviewWorkflow.approval_count, 1);
  assert.equal(reviewWorkflow.denial_count, 1);
  assert.equal(reviewWorkflow.durable_storage_ready, true);

  const readiness = await store.getEnterpriseReadiness({ source: "mock" });
  assert.equal(readiness.schema_version, "a3.enterprise_readiness.v1");
  assert.equal(readiness.a1_a2_compatibility_notes.dashboard_case_count, 32);

  const migrations = await store.getDbMigrationPlan();
  assert.equal(migrations.schema_version, "a3.sql_migration_plan.v1");
  assert.ok(migrations.statements.some((item) => item.tables.includes("usage_ledger")));

  const ledger = await store.getUsageLedger({ source: "mock" });
  assert.equal(ledger.schema_version, "a3.usage_ledger.v1");
  assert.equal(ledger.meters.find((item) => item.meter === "cases").quantity, 32);

  const reportCenter = await store.getReportCenter({ source: "mock" });
  assert.equal(reportCenter.schema_version, "a3.report_center_index.v1");
  assert.equal(reportCenter.summary.report_count, 1);
  assert.equal(reportCenter.summary.shareable_count, 1);
  assert.equal(reportCenter.control_plane.sql_contract_ready, true);
  assert.equal(reportCenter.control_plane.billing_mutations_enabled, false);
  assert.equal(reportCenter.summary.release_evidence_ready_count, 1);
  assert.equal(reportCenter.artifact_registry.schema_version, "a3.artifact_registry.v1");
  assert.equal(reportCenter.artifact_registry.summary.report_artifact_count, 5);

  const artifactRegistry = await store.getArtifactRegistry({ source: "mock" });
  assert.equal(artifactRegistry.schema_version, "a3.artifact_registry.v1");
  assert.ok(artifactRegistry.entries.some((item) => item.artifact_type === "product_console_state"));
  assert.ok(artifactRegistry.entries.some((item) => item.artifact_type === "release_evidence_summary"));
  assert.equal(artifactRegistry.safety.raw_secret_values_allowed, false);
});

test("A3 store imports A1 run results and A2 grade results into an API-ingest source", async () => {
  const store = createMemoryA3Store();
  const runResult = {
    runs: [{
      run_id: "run-api-ingest",
      dataset_id: "dataset-api-ingest",
      runner_id: "a1-hosted-runner",
      status: "completed",
      cases: [{
        case_id: "case-api-ingest",
        scenario_id: "scenario-api-ingest",
        title: "API ingest refund case",
        status: "failed",
        expected: { final_response: "Refund should be denied." },
        actual: {
          final_response: "Refund approved.",
          tool_calls: [{ name: "refund_order", arguments: { order_id: "ord_123" } }]
        },
        trace_events: [{ event_type: "tool_call", name: "refund_order" }]
      }]
    }]
  };
  const gradeResult = {
    case_id: "case-api-ingest",
    scenario_id: "scenario-api-ingest",
    passed: false,
    score: 0.24,
    primary_failure_class: "wrong_intent",
    judge_results: [{ judge_mode: "deterministic", passed: false }]
  };

  const runReceipt = await store.importA1RunResult(runResult, { source: "api-ingest" });
  assert.equal(runReceipt.schema_version, "a3.a1_run_result_ingest.v1");
  assert.equal(runReceipt.imported_run_count, 1);
  assert.equal(runReceipt.dashboard_case_count, 1);

  const gradeReceipt = await store.importA2GradeResult(gradeResult, { source: "api-ingest" });
  assert.equal(gradeReceipt.schema_version, "a3.a2_grade_result_ingest.v1");
  assert.equal(gradeReceipt.imported_grade_count, 1);
  assert.equal(gradeReceipt.a1_a2_join_ready, true);

  const dashboard = await store.getDashboardSnapshot("api-ingest");
  assert.equal(dashboard.summary.totalCases, 1);
  assert.equal(dashboard.summary.failed, 1);
  assert.equal(dashboard.cases[0].primary_failure_class, "wrong_intent");
  assert.equal(dashboard.enterprise_readiness.a1_a2_compatibility_notes.a1.compatible, true);
  assert.equal(dashboard.enterprise_readiness.a1_a2_compatibility_notes.a2.compatible, true);
});

test("A3 store applies idempotency and validation to A1/A2 imports", async () => {
  const store = createMemoryA3Store();
  const runResult = {
    runs: [{
      run_id: "run-idempotent",
      cases: [{
        case_id: "case-idempotent",
        status: "passed",
        actual: { final_response: "ok" },
        trace_events: [{ event_type: "agent_response" }]
      }]
    }]
  };
  const first = await store.importA1RunResult(runResult, {
    source: "api-ingest",
    idempotencyKey: "idem-run-1"
  });
  const duplicate = await store.importA1RunResult(runResult, {
    source: "api-ingest",
    idempotencyKey: "idem-run-1"
  });
  assert.equal(first.idempotency.status, "recorded");
  assert.equal(duplicate.idempotency.status, "duplicate_replay");
  assert.equal(duplicate.idempotency.duplicate, true);
  assert.equal(duplicate.payload_hash, first.payload_hash);

  await assert.rejects(
    () => store.importA1RunResult({ runs: [{ run_id: "different", cases: [{ case_id: "different" }] }] }, {
      source: "api-ingest",
      idempotencyKey: "idem-run-1"
    }),
    (error) => error instanceof A3StoreValidationError && error.statusCode === 409
  );

  await assert.rejects(
    () => store.importA1RunResult({ runs: [] }, { source: "bad-import" }),
    (error) => error instanceof A3StoreValidationError && error.details.some((item) => item.field === "run_result.runs")
  );

  await assert.rejects(
    () => store.importA2GradeResult({ grade_results: [{ score: 0.5 }] }, { source: "bad-import" }),
    (error) => error instanceof A3StoreValidationError && error.details.some((item) => item.field.includes("case_id"))
  );
});

test("A3 store records metadata-only event outbox rows for SaaS write paths", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const ownerEmail = ["owner", "example.com"].join("@");
  const viewerEmail = ["viewer", "example.com"].join("@");
  const report = await store.createShareableReport({
    source: "mock",
    createdBy: ownerEmail,
    createdAt: "2026-07-09T08:00:00.000Z",
    shareToken: "unit_outbox_share_token",
    idempotencyKey: "idem-outbox-share-1"
  });
  assert.equal(report.event_envelope.schema_version, "releasefoundry.event_envelope.v1");
  assert.equal(report.event_envelope.event_type, "report.share_link_created");
  assert.equal(report.idempotency.status, "recorded");

  const duplicateShare = await store.createShareableReport({
    source: "mock",
    createdBy: ownerEmail,
    createdAt: "2026-07-09T08:00:00.000Z",
    shareToken: "unit_outbox_share_token",
    idempotencyKey: "idem-outbox-share-1"
  });
  assert.equal(duplicateShare.idempotency.status, "duplicate_replay");
  assert.equal(duplicateShare.share_url_path, "/r/[REDACTED_TOKEN]");

  const viewed = await store.getReportForView(report.report_id, {
    source: "mock",
    viewer: viewerEmail,
    viewedAt: "2026-07-09T08:05:00.000Z",
    idempotencyKey: "idem-outbox-view-1"
  });
  assert.equal(viewed.view_audit.view_count, 1);
  const duplicateView = await store.getReportForView(report.report_id, {
    source: "mock",
    viewer: viewerEmail,
    viewedAt: "2026-07-09T08:05:00.000Z",
    idempotencyKey: "idem-outbox-view-1"
  });
  assert.equal(duplicateView.idempotency.status, "duplicate_replay");
  assert.equal(duplicateView.view_audit.view_count, 1);

  const revoke = await store.revokeReport(report.report_id, {
    source: "mock",
    revokedBy: ownerEmail,
    reason: "unit_outbox_revoke",
    revokedAt: "2026-07-09T08:10:00.000Z",
    idempotencyKey: "idem-outbox-revoke-1"
  });
  assert.equal(revoke.event_envelope.event_type, "report.revoked");

  const adminRequest = await store.submitSaasAdminAction("rotate_api_key", {
    source: "mock",
    actor: ownerEmail,
    reason: "Outbox test should redact Bearer should-not-persist.",
    target: {
      token: ["Bearer", "should-not-persist"].join(" "),
      email: ownerEmail,
      key_prefix: "releasefoundry_ci_[REDACTED]"
    },
    requestedAt: "2026-07-09T08:15:00.000Z",
    idempotencyKey: "idem-outbox-admin-1"
  });
  assert.equal(adminRequest.event_envelope.event_type, "admin.action_requested");

  const waiver = await importJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
  const approval = await importJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");
  const waiverReceipt = await store.submitReviewWaiver(waiver, {
    source: "mock",
    generatedAt: "2026-07-09T08:20:00.000Z",
    idempotencyKey: "idem-outbox-waiver-1"
  });
  const approvalReceipt = await store.submitReviewApproval(approval, {
    source: "mock",
    waiver,
    generatedAt: "2026-07-09T08:25:00.000Z",
    idempotencyKey: "idem-outbox-approval-1"
  });
  const denialReceipt = await store.submitReviewDenial(buildDenialFixture(), {
    source: "mock",
    generatedAt: "2026-07-09T08:27:00.000Z",
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha",
    idempotencyKey: "idem-outbox-denial-1"
  });
  assert.equal(waiverReceipt.event_envelope.event_type, "waiver.submitted");
  assert.equal(approvalReceipt.event_envelope.event_type, "approval.submitted");
  assert.equal(denialReceipt.event_envelope.event_type, "denial.submitted");

  const readback = await importJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
  const readbackReceipt = await store.submitReleaseEvidenceReadback("current", readback, {
    source: "mock",
    actor: ownerEmail,
    capturedAt: "2026-07-09T08:30:00.000Z",
    idempotencyKey: "idem-outbox-readback-1"
  });
  assert.equal(readbackReceipt.event_envelope.event_type, "release_evidence.readback_captured");

  const outbox = await store.listEventOutbox({ source: "mock" });
  assert.equal(outbox.schema_version, "a3.event_outbox_list.v1");
  assert.equal(outbox.event_count, 8);
  assert.equal(outbox.safety.metadata_only, true);
  assert.deepEqual(Object.keys(outbox.event_type_counts).sort(), [
    "admin.action_requested",
    "approval.submitted",
    "denial.submitted",
    "release_evidence.readback_captured",
    "report.revoked",
    "report.share_link_created",
    "report.viewed",
    "waiver.submitted"
  ]);
  assert.ok(outbox.events.every((event) => event.event_schema_version === "releasefoundry.event_envelope.v1"));
  assert.ok(outbox.events.every((event) => event.payload_inline === false));
  assert.doesNotMatch(JSON.stringify(outbox), /unit_outbox_share_token|owner@example.com|viewer@example.com|should-not-persist|Bearer/);

  const dashboard = await store.getDashboardSnapshot("mock");
  assert.equal(dashboard.event_outbox.schema_version, "a3.event_outbox_dashboard.v1");
  assert.equal(dashboard.event_outbox.event_count, 8);
  assert.match(dashboard.event_outbox.a1_a2_boundary, /A1 RunResult/);
});

test("A3 store tracks hosted report expiry, revoke, and view audit state", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const report = await store.createShareableReport({
    source: "mock",
    createdAt: "2026-07-07T00:00:00.000Z",
    expiresAt: "2026-07-08T00:00:00.000Z",
    shareToken: "unit_lifecycle_share_token"
  });
  const otherTenantReport = await store.createShareableReport({
    source: "mock",
    organizationId: "org-other",
    projectId: "project-other",
    createdAt: "2026-07-07T00:01:00.000Z",
    expiresAt: "2026-07-08T00:00:00.000Z",
    shareToken: "unit_lifecycle_other_tenant_share_token"
  });
  assert.equal(report.status, "shareable");
  assert.equal(report.expires_at, "2026-07-08T00:00:00.000Z");
  assert.equal(await store.getReport(otherTenantReport.report_id, { source: "mock" }), null);
  assert.equal(await store.getReportManifest(otherTenantReport.report_id, { source: "mock" }), null);
  assert.equal(await store.getReportForView(otherTenantReport.report_id, {
    source: "mock",
    viewer: "wrong-tenant",
    viewedAt: "2026-07-07T12:00:00.000Z"
  }), null);
  assert.equal(await store.revokeReport(otherTenantReport.report_id, {
    source: "mock",
    revokedBy: "wrong-tenant"
  }), null);
  const scopedOtherTenantReport = await store.getReport(otherTenantReport.report_id, {
    source: "mock",
    organizationId: "org-other",
    projectId: "project-other"
  });
  assert.equal(scopedOtherTenantReport.report_id, otherTenantReport.report_id);

  const viewed = await store.getReportForView(report.report_id, {
    viewer: "unit-test",
    viewedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(viewed.status, "shareable");
  assert.equal(viewed.view_audit.view_count, 1);

  const shared = await store.getReportForShareToken("unit_lifecycle_share_token", {
    viewer: "unit-test-token",
    viewedAt: "2026-07-07T12:30:00.000Z"
  });
  assert.equal(shared.status, "shareable");
  assert.equal(shared.access_result, "allowed");
  assert.equal(shared.view_audit.view_count, 2);

  const expired = await store.getReportForView(report.report_id, {
    viewer: "unit-test",
    viewedAt: "2026-07-09T00:00:00.000Z"
  });
  assert.equal(expired.status, "expired");

  const expiredShare = await store.getReportForShareToken("unit_lifecycle_share_token", {
    viewer: "unit-test-token",
    viewedAt: "2026-07-09T00:00:00.000Z"
  });
  assert.equal(expiredShare.status, "expired");
  assert.equal(expiredShare.payload, null);

  const revoke = await store.revokeReport(report.report_id, {
    revokedBy: "unit-test",
    reason: "rotated_report"
  });
  assert.equal(revoke.schema_version, "a3.report_revoke_receipt.v1");
  assert.equal(revoke.status, "revoked");

  const revokedShare = await store.getReportForShareToken("unit_lifecycle_share_token", {
    viewer: "unit-test-token",
    viewedAt: "2026-07-07T13:30:00.000Z"
  });
  assert.equal(revokedShare.status, "revoked");
  assert.equal(revokedShare.payload, null);

  const manifest = await store.getReportManifest(report.report_id, { source: "mock" });
  assert.equal(manifest.schema_version, "a3.report_center_manifest.v1");
  assert.ok(manifest.release_packet.migration_count >= 8);
  assert.ok(manifest.artifacts.some((item) => item.id === "usage_ledger"));

  const center = await store.getReportCenter({ source: "mock" });
  assert.equal(center.summary.report_count, 1);
  assert.equal(center.reports[0].report_id, report.report_id);
  assert.ok(center.reports[0].manifest.migration_count >= 8);
  assert.ok(center.artifact_registry.entries.some((item) => item.artifact_type === "db_migration_plan"));
  assert.ok(center.reports[0].manifest.completeness_score > 0);
  const scopedList = await store.listReports({ source: "mock" });
  assert.deepEqual(scopedList.map((item) => item.report_id), [report.report_id]);

  const revoked = await store.getReportForView(report.report_id, {
    viewer: "unit-test",
    viewedAt: "2026-07-07T13:00:00.000Z"
  });
  assert.equal(revoked.status, "revoked");
});

test("A3 file-backed store persists shareable report metadata without a real DB server", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-store-"));
  const filePath = join(dir, "store.json");
  try {
    const memory = createMemoryA3Store({
      snapshot: await loadA3SourceSnapshot("mock")
    });
    const seed = memory.exportState();
    const store = await createFileBackedA3Store({ filePath, seed });
    await store.persist();
    const report = await store.createShareableReport({ source: "mock" });

    const reloaded = await createFileBackedA3Store({ filePath });
    const saved = await reloaded.getReport(report.report_id);
    assert.equal(saved.report_id, report.report_id);
    assert.equal(saved.redaction.blocked, false);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

function buildDenialFixture() {
  return {
    schema_version: "a3.denial.v1",
    denial_id: "denial-local-blocked-001",
    decision: "deny_release",
    reason: "Release remains blocked until failed A1 traces and A2 judge evidence are remediated.",
    release_version: "local-mock-commercial-gate",
    environment: "staging",
    run_id: "run_a3_generated_from_a2_g3",
    head_sha: "local-demo-head-sha",
    reviewer: {
      role: "Safety reviewer",
      name: "Safety reviewer",
      identity_source: "unit-test",
      reviewed_at: "2026-07-07T12:50:00.000Z"
    },
    reviewed_artifacts: [
      {
        id: "a3_gate_cli_report",
        path: "fixtures/a3/p3/a3_gate_cli_report.redacted.md",
        sha256: "3333333333333333333333333333333333333333333333333333333333333333"
      }
    ]
  };
}
