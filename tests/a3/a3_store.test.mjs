import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";

import {
  A3_DB_CONTRACT,
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
