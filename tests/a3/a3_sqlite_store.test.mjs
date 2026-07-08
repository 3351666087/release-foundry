import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { DatabaseSync } from "node:sqlite";

import {
  createSqliteA3Store
} from "../../services/report/a3_sqlite_store.mjs";
import {
  A3StoreValidationError,
  loadA3SourceSnapshot
} from "../../services/report/a3_store.mjs";
import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";

async function loadJson(path) {
  return JSON.parse(await readFile(new URL(path, import.meta.url), "utf8"));
}

test("A3 SQLite store persists A1/A2 imports, reports, audit events, and usage rows", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-sqlite-store-"));
  const dbPath = join(dir, "a3.sqlite");
  let store;
  try {
    store = await createSqliteA3Store({
      dbPath,
      seed: {
        snapshot: await loadA3SourceSnapshot("mock")
      }
    });

    let inspection = store.inspectSqliteState();
    assert.equal(inspection.schema_version, "a3.sqlite_store_inspection.v1");
    assert.equal(inspection.storage_mode, "sqlite");
    assert.equal(inspection.migration_contract, "a3.sql_migration_plan.v1");
    assert.equal(inspection.operational_tables.dashboard_snapshots, 1);
    assert.equal(inspection.operational_tables.runs, 1);
    assert.equal(inspection.operational_tables.cases, 32);
    assert.equal(inspection.operational_tables.release_evidence_summaries, 1);
    assert.equal(inspection.operational_tables.release_evidence_snapshots, 1);
    assert.equal(inspection.operational_tables.release_evidence_diffs, 1);
    assert.equal(inspection.operational_tables.release_evidence_readbacks, 3);
    assert.equal(inspection.safety.raw_share_tokens_stored, false);
    assert.equal(inspection.safety.state_payload_secret_scan.api_key_assignment_found, false);

    const runResult = {
      runs: [{
        run_id: "run-sqlite-ingest",
        dataset_id: "dataset-sqlite",
        runner_id: "a1-sqlite-runner",
        status: "completed",
        cases: [{
          case_id: "case-sqlite-ingest",
          scenario_id: "scenario-sqlite",
          status: "failed",
          expected: { final_response: "Deny refund." },
          actual: { final_response: "Refund approved." },
          trace_events: [{ event_type: "agent_response" }]
        }]
      }]
    };
    const firstImport = await store.importA1RunResult(runResult, {
      source: "api-ingest",
      idempotencyKey: "sqlite-idempotency-key"
    });
    const duplicateImport = await store.importA1RunResult(runResult, {
      source: "api-ingest",
      idempotencyKey: "sqlite-idempotency-key"
    });
    assert.equal(firstImport.idempotency.status, "recorded");
    assert.equal(duplicateImport.idempotency.status, "duplicate_replay");

    await assert.rejects(
      () => store.importA1RunResult({
        runs: [{ run_id: "run-sqlite-conflict", cases: [{ case_id: "case-sqlite-conflict" }] }]
      }, {
        source: "api-ingest",
        idempotencyKey: "sqlite-idempotency-key"
      }),
      (error) => error instanceof A3StoreValidationError && error.statusCode === 409
    );

    await store.importA2GradeResult({
      case_id: "case-sqlite-ingest",
      scenario_id: "scenario-sqlite",
      passed: false,
      score: 0.21,
      primary_failure_class: "wrong_intent",
      judge_results: [{ judge_mode: "deterministic", passed: false }]
    }, {
      source: "api-ingest"
    });

    const report = await store.createShareableReport({
      source: "api-ingest",
      title: "SQLite-backed A3 report",
      shareToken: "sqlite-share-token",
      organizationId: "org-enterprise",
      projectId: "project-enterprise"
    });
    assert.equal(report.status, "shareable");
    assert.equal(report.share_url_path, "/r/sqlite-share-token");

    const viewed = await store.getReportForShareToken("sqlite-share-token", {
      viewer: "sqlite-test",
      viewedAt: "2026-07-07T12:00:00.000Z"
    });
    assert.equal(viewed.access_result, "allowed");

    const revoke = await store.revokeReport(report.report_id, {
      reason: "sqlite-test",
      revokedAt: "2026-07-07T13:00:00.000Z"
    });
    assert.equal(revoke.status, "revoked");

    const adminAction = await store.submitSaasAdminAction("publish_trust_report", {
      source: "api-ingest",
      actor: ["trust-admin", "example.com"].join("@"),
      reason: "Request trust preview without public publishing."
    });
    assert.equal(adminAction.schema_version, "a3.saas_admin_action_receipt.v1");
    assert.equal(adminAction.real_cloud_mutation_performed, false);

    const waiver = await loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
    const approval = await loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json");
    const waiverReceipt = await store.submitReviewWaiver(waiver, {
      source: "mock",
      generatedAt: "2026-07-07T12:00:00.000Z"
    });
    const approvalReceipt = await store.submitReviewApproval(approval, {
      source: "mock",
      waiver,
      generatedAt: "2026-07-07T12:00:00.000Z"
    });
    assert.equal(waiverReceipt.status, "valid_exceptional_waiver");
    assert.equal(approvalReceipt.status, "valid_exception_approval");

    inspection = store.inspectSqliteState();
    assert.equal(inspection.operational_tables.dashboard_snapshots, 2);
    assert.equal(inspection.operational_tables.idempotency_keys, 1);
    assert.equal(inspection.operational_tables.api_import_receipts, 1);
    assert.equal(inspection.operational_tables.shareable_reports, 1);
    assert.equal(inspection.operational_tables.report_share_links, 1);
    assert.equal(inspection.operational_tables.report_view_events, 1);
    assert.equal(inspection.operational_tables.report_revocations, 1);
    assert.equal(inspection.operational_tables.saas_admin_action_requests, 1);
    assert.equal(inspection.operational_tables.review_workflow_records, 2);
    assert.equal(inspection.operational_tables.release_evidence_summaries, 1);
    assert.equal(inspection.operational_tables.release_evidence_snapshots, 1);
    assert.equal(inspection.operational_tables.release_evidence_diffs, 1);
    assert.equal(inspection.operational_tables.release_evidence_readbacks, 3);
    assert.ok(inspection.operational_tables.audit_events >= 2);
    assert.ok(inspection.operational_tables.usage_ledger > 0);
    assert.equal(inspection.safety.state_payload_secret_scan.raw_share_token_hint_found, false);

    const sqlCheck = new DatabaseSync(dbPath, { readOnly: true });
    try {
      const row = sqlCheck.prepare("SELECT organization_id, project_id FROM shareable_reports WHERE id = ?").get(report.report_id);
      assert.equal(row.organization_id, "org-enterprise");
      assert.equal(row.project_id, "project-enterprise");
      const snapshotRow = sqlCheck.prepare("SELECT summary_schema_version, health_status FROM release_evidence_snapshots LIMIT 1").get();
      assert.equal(snapshotRow.summary_schema_version, "a3.release_evidence_summary.v2");
      assert.ok(snapshotRow.health_status);
    } finally {
      sqlCheck.close();
    }

    store.close();
    store = await createSqliteA3Store({ dbPath });
    const savedReport = await store.getReport(report.report_id);
    assert.equal(savedReport.status, "revoked");
    assert.equal(savedReport.share_url_path, "/r/[REDACTED_TOKEN]");
    assert.equal(savedReport.share_link.token_hash, undefined);
    assert.match(savedReport.share_link.token_hash_prefix, /^[a-f0-9]{12}$/);
    const savedAdminActions = await store.listSaasAdminActionRequests({ source: "api-ingest" });
    assert.equal(savedAdminActions.summary.request_count, 1);
    assert.doesNotMatch(JSON.stringify(savedAdminActions), new RegExp(["trust-admin", "example.com"].join("@")));
    const savedReviewWorkflow = await store.getReviewWorkflow({ source: "mock" });
    assert.equal(savedReviewWorkflow.record_count, 2);
    assert.equal(savedReviewWorkflow.accepted_count, 2);
  } finally {
    if (store?.close) {
      store.close();
    }
    await rm(dir, { recursive: true, force: true });
  }
});

test("A3 API server can run on the SQLite store without changing API contracts", async () => {
  const dir = await mkdtemp(join(tmpdir(), "a3-sqlite-api-"));
  const dbPath = join(dir, "a3.sqlite");
  let store;
  let server;
  try {
    store = await createSqliteA3Store({
      dbPath,
      seed: {
        snapshot: await loadA3SourceSnapshot("mock")
      }
    });
    const started = await startA3ApiServer({ store });
    server = started.server;
    const url = started.url;

    const health = await getJson(`${url}/api/a3/health`);
    assert.equal(health.storage_mode, "sqlite");

    const shareResponse = await fetch(`${url}/api/a3/reports/share?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "SQLite API report" })
    });
    assert.equal(shareResponse.status, 201);
    const report = await shareResponse.json();
    assert.equal(report.schema_version, "a3.shareable_report.v1");

    const center = await getJson(`${url}/api/a3/reports/center?source=mock`);
    assert.equal(center.summary.report_count, 1);

    const revokeResponse = await fetch(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}/revoke`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason: "sqlite-api-test" })
    });
    assert.equal(revokeResponse.status, 200);
    const revoked = await revokeResponse.json();
    assert.equal(revoked.status, "revoked");

    const inspection = store.inspectSqliteState();
    assert.equal(inspection.operational_tables.shareable_reports, 1);
    assert.equal(inspection.operational_tables.report_revocations, 1);
  } finally {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
    if (store?.close) {
      store.close();
    }
    await rm(dir, { recursive: true, force: true });
  }
});

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
