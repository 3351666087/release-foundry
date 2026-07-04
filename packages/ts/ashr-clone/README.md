# Ashr Clone TypeScript SDK

TypeScript parity package for A1. It mirrors the Python `AgentInput`, `CloudApiService`, `QuotaLedger`, run polling, fixture export, and dry-run-first Ashr API client surfaces.

```powershell
npm install --prefix packages/ts/ashr-clone
npm test --prefix packages/ts/ashr-clone
npm run probe --prefix packages/ts/ashr-clone -- init --output docs/evidence/private_refs/a1_ts_api_init_dry_run.json
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

Dry-run API client quickstart:

```js
import { AshrApiClient } from "./dist/index.js";

const client = new AshrApiClient();
const plan = await client.createRequest({
  requestName: "A1 Media Dry Run",
  request: {
    agent: { accepted_inputs: { text: true, image: true, audio: true, file: true } },
    generation_options: { generate_images: true, generate_audio: true, generate_files: true },
    test_config: { num_variations: 1 },
  },
});

console.log(plan.status); // planned
console.log(plan.attempts); // 0
```

`AshrApiClient` defaults to dry-run mode, does not require an API key for plans, and does not call `fetch` or an injected transport unless `dryRun: false` is passed. Real execution must use an explicit key source and should follow the dry-run -> small batch -> batch discipline recorded in A1 evidence.

Probe CLI:

```powershell
npm run build --prefix packages/ts/ashr-clone
node packages/ts/ashr-clone/dist/probe.js health-check --output docs/evidence/private_refs/a1_ts_api_health_check_dry_run.json
node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json
```

The CLI is dry-run-first and writes JSON records to `docs/evidence/private_refs` by default. Stdout prints only a one-line summary unless `--print-record` is explicitly passed. Real calls require `--execute` and an environment-only `ASHR_API_KEY` or `ASHR_LABS_API_KEY`; mutating calls also require `--allow-mutate --max-retries 0`.
