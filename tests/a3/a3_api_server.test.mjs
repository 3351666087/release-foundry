import assert from "node:assert/strict";
import { test } from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { createFixtureBackedA3Store } from "../../services/report/a3_store.mjs";

test("A3 API server exposes dashboard, run, case, and shareable report routes", async () => {
  const store = await createFixtureBackedA3Store({ sources: ["mock"] });
  const { server, url } = await startA3ApiServer({ store });
  try {
    const health = await getJson(`${url}/api/a3/health`);
    assert.equal(health.ok, true);
    assert.equal(health.db_ready, true);

    const dashboard = await getJson(`${url}/api/a3/dashboard?source=mock`);
    assert.equal(dashboard.schema_version, "a3.api_dashboard_payload.v1");
    assert.equal(dashboard.summary.totalCases, 32);
    assert.equal(dashboard.storage.db_contract.mysql_compatible, true);

    const runs = await getJson(`${url}/api/a3/runs?source=mock`);
    assert.equal(runs.schema_version, "a3.api_run_list.v1");
    assert.equal(runs.runs.length, 1);

    const run = await getJson(`${url}/api/a3/runs/${encodeURIComponent(runs.runs[0].run_id)}?source=mock`);
    assert.equal(run.schema_version, "a3.api_run_detail.v1");
    assert.equal(run.summary.total_cases, 32);

    const firstCaseId = dashboard.cases[0].case_id;
    const detail = await getJson(`${url}/api/a3/cases/${encodeURIComponent(firstCaseId)}?source=mock`);
    assert.equal(detail.schema_version, "a3.api_case_detail.v1");
    assert.equal(detail.case.case_id, firstCaseId);

    const shareResponse = await fetch(`${url}/api/a3/reports/share?source=mock`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "A3 API smoke report" })
    });
    assert.equal(shareResponse.status, 201);
    const report = await shareResponse.json();
    assert.equal(report.schema_version, "a3.shareable_report.v1");
    assert.equal(report.status, "shareable");

    const savedReport = await getJson(`${url}/api/a3/reports/${encodeURIComponent(report.report_id)}`);
    assert.equal(savedReport.report_id, report.report_id);

    const missing = await fetch(`${url}/api/a3/cases/missing-case?source=mock`);
    assert.equal(missing.status, 404);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

async function getJson(url) {
  const response = await fetch(url);
  assert.equal(response.ok, true, `${url} returned ${response.status}`);
  return response.json();
}
