# Ashr Clone TypeScript SDK

TypeScript parity package for A1. It mirrors the Python `AgentInput`, `AgentAdapter`, local runner, dataset-source adapter, trace/replay helpers, `CloudApiService`, `QuotaLedger`, run polling, fixture export, and dry-run-first Ashr API client surfaces.

```powershell
npm install --prefix packages/ts/ashr-clone
npm test --prefix packages/ts/ashr-clone
npm run probe --prefix packages/ts/ashr-clone -- init --output docs/evidence/private_refs/a1_ts_api_init_dry_run.json
```

Cloud runtime quickstart:

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

Local runner quickstart:

```js
import { LocalEvalRunner, buildRunFixture } from "./dist/index.js";

const runner = new LocalEvalRunner({
  agent: { respond: (message) => ({ text: `Echo: ${message}`, tool_calls: [] }) },
  datasetId: "dataset_ts_demo",
  runnerId: "a1-ts-local-runner",
  maxWorkers: 4,
});

const result = await runner.run([{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }]);
console.log(result.passed);
console.log(buildRunFixture(result).schema);
```

Runner CLI:

```powershell
npm run build --prefix packages/ts/ashr-clone
node packages/ts/ashr-clone/dist/runner-cli.js --input docs/a1/evidence/local_agent_cases_30.json --output docs/evidence/private_refs/a1_ts_runner_run_30_smoke.json --agent examples/agents/mock_agent_ts.mjs:default --dataset-id a2-local-scenarios-ts --runner-id a1-ts-local-runner --run-id run_a1_ts_runner_30_smoke --max-workers 4 --timeout 5 --fixture-output docs/evidence/private_refs/a1_ts_runner_fixture_30_smoke.json --fail-on-case-failure
```

Dataset-source adapter CLI:

```powershell
node packages/ts/ashr-clone/dist/dataset-adapter-cli.js cases --input docs/evidence/private_refs/a1_api_get_dataset_first_real.json --output docs/evidence/private_refs/a1_ts_dataset_cases.json --max-cases 10
node packages/ts/ashr-clone/dist/dataset-adapter-cli.js replay-fixture --input docs/evidence/private_refs/a1_api_get_dataset_first_real.json --output docs/evidence/private_refs/a1_ts_dataset_replay_fixture.json
```

The dataset adapter accepts API probe records or dataset objects containing `dataset_source.runs`, converts agent actions into local runner cases, and can emit A3-style replay fixtures without reading media files or calling hosted Ashr APIs.

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

The probe CLI is dry-run-first and writes JSON records to `docs/evidence/private_refs` by default. Stdout prints only a one-line summary unless `--print-record` is explicitly passed. Real calls require `--execute` and an environment-only `ASHR_API_KEY` or `ASHR_LABS_API_KEY`; mutating calls also require `--allow-mutate --max-retries 0`.

Trace/replay helpers:

- `TraceRecorder`, `buildVmStream`, `traceEventsFromVmStream`, `buildTraceRunFixture`.
- `validateTraceEvent`, `validateVmStreamFrame`, `validateRunFixture`, `loadRunFixture`, `writeRunFixture`.
- `runCase`, `runBatch`, `BatchRunner`, `runFile`, and `toA2JudgeRun` mirror Python helper ergonomics for local-only tests and A2 projection.
