import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
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

test("A3 store loads fixture sources through a DB-ready dashboard snapshot", async () => {
  const snapshot = await loadA3SourceSnapshot("mock");

  assert.equal(snapshot.schema_version, "a3.dashboard_snapshot.v1");
  assert.equal(snapshot.source, "mock");
  assert.equal(snapshot.summary.totalRuns, 1);
  assert.equal(snapshot.summary.totalCases, 32);
  assert.equal(snapshot.storage.db_ready, true);
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

  const runs = await store.listRuns({ source: "mock" });
  assert.equal(runs.length, 1);
  assert.equal(runs[0].total_cases, 32);

  const detail = await store.getCase(dashboard.cases[0].case_id, { source: "mock" });
  assert.equal(detail.schema_version, "a3.api_case_detail.v1");
  assert.equal(detail.case.case_id, dashboard.cases[0].case_id);

  const missing = await store.getCase("missing-case", { source: "mock" });
  assert.equal(missing, null);

  const report = await store.createShareableReport({ source: "mock", createdAt: "2026-07-07T00:00:00.000Z" });
  assert.equal(report.schema_version, "a3.shareable_report.v1");
  assert.equal(report.status, "shareable");
  assert.match(report.share_url_path, /^\/reports\/a3r_/);
  assert.equal(report.sealed_evidence.secret_free, true);

  const admin = await store.getSaasAdminConsole({ source: "mock" });
  assert.equal(admin.team.members.length, 4);
  assert.equal(admin.safety.real_team_invites_enabled, false);

  const action = await store.planSaasAdminAction("rotate_api_key", { source: "mock" });
  assert.equal(action.mode, "plan_only");
  assert.equal(action.writes_real_ashr_cloud, false);

  const readiness = await store.getEnterpriseReadiness({ source: "mock" });
  assert.equal(readiness.schema_version, "a3.enterprise_readiness.v1");
  assert.equal(readiness.a1_a2_compatibility_notes.dashboard_case_count, 32);
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

test("A3 store tracks hosted report expiry, revoke, and view audit state", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const report = await store.createShareableReport({
    source: "mock",
    createdAt: "2026-07-07T00:00:00.000Z",
    expiresAt: "2026-07-08T00:00:00.000Z"
  });
  assert.equal(report.status, "shareable");
  assert.equal(report.expires_at, "2026-07-08T00:00:00.000Z");

  const viewed = await store.getReportForView(report.report_id, {
    viewer: "unit-test",
    viewedAt: "2026-07-07T12:00:00.000Z"
  });
  assert.equal(viewed.status, "shareable");
  assert.equal(viewed.view_audit.view_count, 1);

  const expired = await store.getReportForView(report.report_id, {
    viewer: "unit-test",
    viewedAt: "2026-07-09T00:00:00.000Z"
  });
  assert.equal(expired.status, "expired");

  const revoke = await store.revokeReport(report.report_id, {
    revokedBy: "unit-test",
    reason: "rotated_report"
  });
  assert.equal(revoke.schema_version, "a3.report_revoke_receipt.v1");
  assert.equal(revoke.status, "revoked");

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
