# Ashr Clone TypeScript SDK

Local-only TypeScript parity package for A1. It mirrors the Python `AgentInput`, `CloudApiService`, `QuotaLedger`, run polling, and fixture export shapes without reading API keys or making network calls.

```powershell
npm install --prefix packages/ts/ashr-clone
npm test --prefix packages/ts/ashr-clone
```

Minimal quickstart:

```js
import { CloudApiService } from "./dist/index.js";

const service = new CloudApiService();
const tenant = service.createTenant("Local Tenant", { tenantId: "tenant_demo" });
const project = service.createProject(tenant.tenant_id, "Local Project", { projectId: "project_demo" });
const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
  datasetId: "dataset_demo",
  name: "Local Dataset",
  cases: [{ id: "case-1", prompt: "hello" }],
});
const run = service.submitRun(tenant.tenant_id, project.project_id, {
  datasetId: dataset.dataset_id,
  runResult: {
    run_id: "run_demo",
    dataset_id: dataset.dataset_id,
    runner_id: "ts-local-runner",
    status: "passed",
    total_cases: 1,
    ended_at: new Date().toISOString(),
    cases: [{ case_id: "case-1", observations: [{ observation_id: "obs-1" }] }],
  },
});

console.log(service.pollRun(tenant.tenant_id, project.project_id, run.run_id).status);
console.log(service.exportRunFixture(tenant.tenant_id, project.project_id, run.run_id).metadata);
```

This package intentionally does not expose a hosted Ashr API client yet. Real API calibration remains in the Python probe until the dry-run/small-batch discipline is mirrored in TypeScript.
