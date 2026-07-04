import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { CloudApiService, redactSensitive } from "../dist/index.js";

const runResultPath = process.argv[2]
  ? resolve(process.argv[2])
  : resolve("../../../docs/a1/evidence/local_run_30.json");
const fixturePath = process.argv[3] ? resolve(process.argv[3]) : resolve("./tmp/cloud_fixture.json");

const runResult = JSON.parse(readFileSync(runResultPath, "utf8"));
const cases = Array.isArray(runResult.cases) ? runResult.cases : [];

const service = new CloudApiService();
const tenant = service.createTenant("TS Local Tenant", { tenantId: "tenant_ts_quickstart" });
const project = service.createProject(tenant.tenant_id, "TS Local Project", { projectId: "project_ts_quickstart" });
const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
  datasetId: String(runResult.dataset_id || "dataset_ts_quickstart"),
  name: "TS Local Dataset",
  cases,
});
const run = service.submitRun(tenant.tenant_id, project.project_id, {
  datasetId: dataset.dataset_id,
  runResult,
});

mkdirSync(dirname(fixturePath), { recursive: true });
writeFileSync(fixturePath, `${JSON.stringify(service.exportRunFixture(tenant.tenant_id, project.project_id, run.run_id), null, 2)}\n`, "utf8");

console.log(JSON.stringify(redactSensitive({
  status: "ok",
  fixture: fixturePath,
  run_id: run.run_id,
  total_cases: run.total_cases,
  metadata: { local_only: true, ashr_api_used: false },
}), null, 2));
