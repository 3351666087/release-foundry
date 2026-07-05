import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  AGENT_INPUT_SCHEMA_VERSION,
  CLOUD_API_SCHEMA_VERSION,
  RUN_RESULT_SCHEMA_VERSION,
  CloudApiService,
  CloudQueueWorker,
  NotFoundError,
  QuotaExceededError,
  QuotaLedger,
  ValidationError,
  agentInputFromParts,
  buildDefaultRequestInputSchema,
  coerceAgentInput,
  redactSensitive,
  runAgentCloudDemo,
} from "../dist/index.js";

function sampleCases(count = 2) {
  return Array.from({ length: count }, (_, index) => ({
    id: `case-${index + 1}`,
    prompt: index === 0 ? "hello" : "inspect",
    expected: { text: index === 0 ? "Echo: hello" : "Echo: inspect" },
  }));
}

function sampleRunResult(overrides = {}) {
  const cases = [
    {
      case_id: "case-1",
      status: "passed",
      observations: [
        { observation_id: "obs-1", type: "agent_turn", payload: { text: "Echo: hello" } },
        { observation_id: "obs-2", type: "tool_call", payload: { name: "search" } },
      ],
      agent_output: { text: "Echo: hello", tool_calls: [{ name: "search", arguments: { q: "hello" } }] },
    },
  ];
  return {
    schema_version: RUN_RESULT_SCHEMA_VERSION,
    run_id: "run_sample",
    dataset_id: "dataset_sample",
    runner_id: "runner_sample",
    status: "passed",
    total_cases: 1,
    passed: 1,
    failed: 0,
    errored: 0,
    timed_out: 0,
    ended_at: "2026-07-05T00:00:00.000Z",
    cases,
    aggregate_metrics: { trace_completeness: 1.0 },
    metadata: { local_only: true, ashr_api_used: false },
    ...overrides,
  };
}

function createServiceFixture(options = {}) {
  const service = new CloudApiService({ clock: () => "2026-07-05T00:00:00.000Z" });
  const tenant = service.createTenant(options.tenantName ?? "Tenant", { tenantId: options.tenantId ?? "tenant_parity" });
  const project = service.createProject(tenant.tenant_id, options.projectName ?? "Project", { projectId: options.projectId ?? "project_parity" });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId: options.datasetId ?? "dataset_parity",
    name: options.datasetName ?? "Dataset",
    cases: options.cases ?? sampleCases(),
  });
  return { service, tenant, project, dataset };
}

for (const partType of ["text", "image", "audio", "file", "video"]) {
  test(`coerceAgentInput preserves ${partType} parts at first-class modality level`, () => {
    const part = partType === "text"
      ? { type: "text", text: "hello" }
      : { type: partType, path: `fixture.${partType}`, mimeType: `${partType}/example`, description: `${partType} fixture` };
    const input = coerceAgentInput({ text: partType === "text" ? "hello" : "", parts: [part], metadata: { modality: partType } });

    assert.equal(input.schema_version, AGENT_INPUT_SCHEMA_VERSION);
    assert.equal(input.parts[0].type, partType);
    assert.equal(input.metadata.modality, partType);
    if (partType !== "text") {
      assert.equal(input.parts[0].mime_type, `${partType}/example`);
    }
  });
}

for (const mediaType of ["image", "audio", "file", "video"]) {
  test(`buildDefaultRequestInputSchema includes ${mediaType} without demoting other modalities`, () => {
    const accepted = { text: true, image: true, audio: true, file: true, video: true };
    const schema = buildDefaultRequestInputSchema({ agent: { accepted_inputs: accepted } });
    const enumValues = schema.$defs.agent_input_part.oneOf[1].properties.type.enum;

    assert.equal(schema.properties.schema_version.const, AGENT_INPUT_SCHEMA_VERSION);
    assert.equal(enumValues.includes(mediaType), true);
    assert.deepEqual(enumValues, ["image", "audio", "file", "video"]);
  });
}

test("agentInputFromParts keeps explicit text separate from media-only parts", () => {
  const input = agentInputFromParts([{ type: "image", url: "https://example.invalid/a.png" }], { text: "describe", metadata: { case_id: "case-media" } });

  assert.equal(input.text, "describe");
  assert.deepEqual(input.parts, [{ type: "image", url: "https://example.invalid/a.png" }]);
  assert.equal(input.metadata.case_id, "case-media");
});

test("coerceAgentInput derives text by joining only text parts", () => {
  const input = coerceAgentInput({ parts: [{ type: "text", text: "one" }, { type: "image", path: "a.png" }, { type: "text", text: "two" }] });

  assert.equal(input.text, "one\ntwo");
});

test("coerceAgentInput rejects unknown modality types", () => {
  assert.throws(() => coerceAgentInput({ parts: [{ type: "mesh", path: "model.obj" }] }), ValidationError);
});

test("redactSensitive redacts nested secrets in cloud metadata", () => {
  const redacted = redactSensitive({ token: "tp_secret_value", nested: { Authorization: "Bearer abc.def", url: "https://x.invalid/a?token=1" } });

  assert.deepEqual(redacted, { token: "[redacted]", nested: { Authorization: "[redacted]", url: "https://x.invalid/a?[redacted]" } });
});

test("QuotaLedger consumes and snapshots per tenant/project operation", () => {
  const ledger = new QuotaLedger({ "dataset.create": 2 });
  ledger.configure("tenant", "project", {});
  ledger.consume("tenant", "project", "dataset.create");
  const snapshot = ledger.snapshot("tenant", "project");

  assert.equal(snapshot.used["dataset.create"], 1);
  assert.equal(snapshot.remaining["dataset.create"], 1);
});

test("QuotaLedger rejects negative limits", () => {
  const ledger = new QuotaLedger();
  assert.throws(() => ledger.configure("tenant", "project", { "run.submit": -1 }), ValidationError);
});

test("QuotaLedger rejects zero-unit consumption", () => {
  const ledger = new QuotaLedger();
  assert.throws(() => ledger.consume("tenant", "project", "run.submit", 0), ValidationError);
});

test("QuotaLedger throws typed quota error when exhausted", () => {
  const ledger = new QuotaLedger({ "run.submit": 1 });
  ledger.configure("tenant", "project", {});
  ledger.consume("tenant", "project", "run.submit");

  assert.throws(() => ledger.consume("tenant", "project", "run.submit"), QuotaExceededError);
});

test("QuotaLedger state roundtrips default limits and project usage", () => {
  const ledger = new QuotaLedger({ "request.create": 3 });
  ledger.configure("tenant", "project", { "request.create": 2 });
  ledger.consume("tenant", "project", "request.create");
  const restored = QuotaLedger.fromState(ledger.state());

  assert.equal(restored.snapshot("tenant", "project").used["request.create"], 1);
  assert.equal(restored.snapshot("tenant", "project").remaining["request.create"], 1);
});

test("CloudApiService creates tenant/project/dataset with stable schema fields", () => {
  const { tenant, project, dataset } = createServiceFixture();

  assert.equal(tenant.schema_version, CLOUD_API_SCHEMA_VERSION);
  assert.equal(project.tenant_id, tenant.tenant_id);
  assert.equal(dataset.case_count, 2);
  assert.equal(dataset.cases[0].id, "case-1");
});

test("CloudApiService rejects duplicate tenant/project/dataset IDs", () => {
  const { service, tenant, project } = createServiceFixture();

  assert.throws(() => service.createTenant("Again", { tenantId: tenant.tenant_id }), ValidationError);
  assert.throws(() => service.createProject(tenant.tenant_id, "Again", { projectId: project.project_id }), ValidationError);
  assert.throws(() => service.createDataset(tenant.tenant_id, project.project_id, { datasetId: "dataset_parity", name: "Again", cases: sampleCases() }), ValidationError);
});

test("CloudApiService enforces tenant/project isolation on dataset reads", () => {
  const { service, dataset } = createServiceFixture();

  assert.throws(() => service.getDataset("other", "project_parity", dataset.dataset_id), NotFoundError);
  assert.throws(() => service.getDataset("tenant_parity", "other", dataset.dataset_id), NotFoundError);
});

test("CloudApiService lists only project-local datasets", () => {
  const { service, tenant, project } = createServiceFixture();
  const projectTwo = service.createProject(tenant.tenant_id, "Project Two", { projectId: "project_two" });
  service.createDataset(tenant.tenant_id, projectTwo.project_id, { datasetId: "dataset_two", name: "Dataset Two", cases: sampleCases(1) });

  assert.deepEqual(service.listDatasets(tenant.tenant_id, project.project_id).map((item) => item.dataset_id), ["dataset_parity"]);
});

test("CloudApiService creates request records with five-modality accepted inputs", () => {
  const { service, tenant, project } = createServiceFixture();
  const request = service.createRequest(tenant.tenant_id, project.project_id, {
    requestId: "request_media",
    name: "Media request",
    acceptedInputs: { text: true, image: true, audio: true, file: true, video: true },
    requestInputSchema: buildDefaultRequestInputSchema({ agent: { accepted_inputs: { text: true, image: true, audio: true, file: true, video: true } } }),
  });

  assert.equal(request.status, "created");
  assert.equal(request.accepted_inputs.video, true);
  assert.equal(request.request_input_schema.$defs.agent_input_part.oneOf[1].properties.type.enum.includes("video"), true);
});

test("CloudApiService request quota increments create calls", () => {
  const { service, tenant, project } = createServiceFixture();
  service.createRequest(tenant.tenant_id, project.project_id, { requestId: "request_one", name: "Request One" });

  assert.equal(service.quotaSnapshot(tenant.tenant_id, project.project_id).used["request.create"], 1);
});

test("CloudApiService lists project-local requests", () => {
  const { service, tenant, project } = createServiceFixture();
  service.createRequest(tenant.tenant_id, project.project_id, { requestId: "request_one", name: "Request One" });

  assert.deepEqual(service.listRequests(tenant.tenant_id, project.project_id).map((item) => item.request_id), ["request_one"]);
});

test("CloudApiService submitRun extracts nested observations and updates quota", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  const run = service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() });
  const quota = service.quotaSnapshot(tenant.tenant_id, project.project_id);

  assert.equal(run.status, "completed");
  assert.equal(run.observations.length, 2);
  assert.equal(quota.used["run.submit"], 1);
  assert.equal(quota.used["observation.write"], 2);
});

test("CloudApiService submitRun honors explicit run id", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  const run = service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_explicit", runResult: sampleRunResult() });

  assert.equal(run.run_id, "run_explicit");
});

test("CloudApiService rejects duplicate run ids", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_dup", runResult: sampleRunResult() });

  assert.throws(() => service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_dup", runResult: sampleRunResult() }), ValidationError);
});

test("CloudApiService pollRun returns run envelope and terminal status", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() });
  const poll = service.pollRun(tenant.tenant_id, project.project_id, "run_sample");

  assert.equal(poll.status, "completed");
  assert.equal(poll.run.result_status, "passed");
});

test("CloudApiService exportRunFixture keeps A3-consumable run result and observations", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() });
  const fixture = service.exportRunFixture(tenant.tenant_id, project.project_id, "run_sample");

  assert.equal(fixture.run_id, "run_sample");
  assert.equal(fixture.run_result.status, "passed");
  assert.equal(fixture.observations.length, 2);
  assert.equal(fixture.metadata.ashr_api_used, false);
});

test("CloudApiService writeRunFixture creates parent directories", async () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-parity-fixture-"));
  try {
    service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() });
    const output = join(temp, "nested", "fixture.json");
    await service.writeRunFixture(tenant.tenant_id, project.project_id, "run_sample", output);

    assert.equal(existsSync(output), true);
    assert.equal(JSON.parse(readFileSync(output, "utf8")).run_id, "run_sample");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("CloudApiService appendObservation consumes observation quota", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  const run = service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_obs" });
  service.appendObservation(tenant.tenant_id, project.project_id, run.run_id, { type: "heartbeat", payload: { ok: true } });

  assert.equal(service.getRun(tenant.tenant_id, project.project_id, run.run_id).observations.length, 1);
  assert.equal(service.quotaSnapshot(tenant.tenant_id, project.project_id).used["observation.write"], 1);
});

test("CloudApiService queued run starts with queued result shape", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  const run = service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue" });

  assert.equal(run.status, "queued");
  assert.equal(run.result.schema_version, RUN_RESULT_SCHEMA_VERSION);
  assert.deepEqual(run.status_history.map((item) => item.status), ["queued"]);
});

test("CloudApiService markRunRunning is idempotent for running status", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue" });
  service.markRunRunning(tenant.tenant_id, project.project_id, "run_queue");
  const run = service.markRunRunning(tenant.tenant_id, project.project_id, "run_queue");

  assert.equal(run.status, "running");
});

test("CloudApiService completeRun writes completion history", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue" });
  service.markRunRunning(tenant.tenant_id, project.project_id, "run_queue");
  const run = service.completeRun(tenant.tenant_id, project.project_id, "run_queue", sampleRunResult({ run_id: "run_queue" }));

  assert.equal(run.status, "completed");
  assert.deepEqual(run.status_history.map((item) => item.status), ["queued", "running", "completed"]);
});

test("CloudApiService failRun redacts secret values", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_fail" });
  const run = service.failRun(tenant.tenant_id, project.project_id, "run_fail", { error: { message: "token tp_secret_value failed", api_key: "secret" } });

  assert.equal(run.status, "failed");
  assert.equal(JSON.stringify(run.error).includes("tp_secret_value"), false);
  assert.equal(run.error.api_key, "[redacted]");
});

test("CloudApiService cancelRun blocks completed runs", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_done", runResult: sampleRunResult({ run_id: "run_done" }) });

  assert.throws(() => service.cancelRun(tenant.tenant_id, project.project_id, "run_done"), ValidationError);
});

test("CloudApiService cancelRun marks queued run cancelled with redacted reason", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_cancel" });
  const run = service.cancelRun(tenant.tenant_id, project.project_id, "run_cancel", { reason: "Bearer abc.def" });

  assert.equal(run.status, "cancelled");
  assert.equal(JSON.stringify(run.error).includes("abc.def"), false);
});

test("CloudApiService listRuns can filter by dataset", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  const datasetTwo = service.createDataset(tenant.tenant_id, project.project_id, { datasetId: "dataset_two", name: "Dataset Two", cases: sampleCases(1) });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_one", runResult: sampleRunResult({ run_id: "run_one" }) });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: datasetTwo.dataset_id, runId: "run_two", runResult: sampleRunResult({ run_id: "run_two", dataset_id: datasetTwo.dataset_id }) });

  assert.deepEqual(service.listRuns(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id }).map((item) => item.run_id), ["run_one"]);
});

test("CloudApiService snapshotState carries store and quota metadata", () => {
  const { service } = createServiceFixture();
  const state = service.snapshotState();

  assert.equal(state.kind, "local_cloud_state");
  assert.equal(state.metadata.local_only, true);
  assert.equal(Object.keys(state.store.tenants).length, 1);
});

test("CloudApiService fromState rejects non-object payloads", () => {
  assert.throws(() => CloudApiService.fromState(null), ValidationError);
});

test("CloudApiService state file roundtrip preserves runs and quota", async () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-state-roundtrip-"));
  try {
    service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() });
    const statePath = join(temp, "state.json");
    await service.writeState(statePath);
    const restored = await CloudApiService.fromStateFile(statePath);

    assert.equal(restored.getRun(tenant.tenant_id, project.project_id, "run_sample").status, "completed");
    assert.equal(restored.quotaSnapshot(tenant.tenant_id, project.project_id).used["run.submit"], 1);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("CloudQueueWorker exposes pollRun passthrough", () => {
  const { service, tenant, project, dataset } = createServiceFixture();
  const queued = service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue" });
  const worker = new CloudQueueWorker(service, { queueWorkers: 4 });

  assert.equal(worker.pollRun(tenant.tenant_id, project.project_id, queued.run_id).status, "queued");
});

test("CloudQueueWorker validates replay max run limit", () => {
  const worker = new CloudQueueWorker(new CloudApiService());
  assert.throws(() => worker.replayIncompleteRuns("tenant", "project", { agent: () => "ok", maxRuns: 0 }), ValidationError);
});

test("CloudQueueWorker does not replay completed runs", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_done", runResult: sampleRunResult({ run_id: "run_done" }) });
  const worker = new CloudQueueWorker(service, { queueWorkers: 4 });

  assert.deepEqual(worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, { agent: () => "ok" }), []);
});

test("runAgentCloudDemo returns complete local cloud summary without network", async () => {
  const summary = await runAgentCloudDemo({
    cases: sampleCases(1),
    agent: (agentInput) => ({ text: `Echo: ${agentInput.text}`, tool_calls: [] }),
    tenantId: "tenant_demo",
    projectId: "project_demo",
    datasetId: "dataset_demo",
  });

  assert.equal(summary.run.status, "completed");
  assert.equal(summary.fixture.run_result.status, "passed");
  assert.equal(summary.metadata.ashr_api_used, false);
});

test("runAgentCloudDemo rejects empty case lists", async () => {
  await assert.rejects(() => runAgentCloudDemo({ cases: [], agent: () => "ok" }), ValidationError);
});

test("ashr-clone-cloud help documents direct and queued Python-parity commands", () => {
  const child = spawnSync(process.execPath, ["dist/cloud-cli.js", "--help"], { cwd: new URL("../", import.meta.url), encoding: "utf8" });

  assert.equal(child.status, 0, child.stderr);
  assert.equal(child.stdout.includes("run-agent"), true);
  assert.equal(child.stdout.includes("run-agent-queued"), true);
  assert.equal(child.stdout.includes("text/audio/file/image/video"), false);
});

test("ashr-clone-cloud run-agent writes direct fixture, summary, run, and state outputs", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-direct-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    const summaryPath = join(temp, "summary.json");
    const runPath = join(temp, "run.json");
    const statePath = join(temp, "state.json");
    writeFileSync(inputPath, JSON.stringify({ cases: sampleCases(3) }), "utf8");
    writeFileSync(agentPath, "export default { respond(message) { return { text: `Echo: ${message}`, tool_calls: [] }; } };\n", "utf8");

    const child = spawnSync(
      process.execPath,
      [
        "dist/cloud-cli.js",
        "run-agent",
        "--input",
        inputPath,
        "--agent",
        `${agentPath}:default`,
        "--fixture-output",
        fixturePath,
        "--summary-output",
        summaryPath,
        "--run-output",
        runPath,
        "--state-output",
        statePath,
        "--tenant-id",
        "tenant_direct",
        "--project-id",
        "project_direct",
        "--dataset-id",
        "dataset_direct",
        "--run-id",
        "run_direct",
        "--max-workers",
        "1",
        "--timeout",
        "5",
        "--fail-on-case-failure",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 0, child.stderr);
    assert.equal(JSON.parse(child.stdout).run.run_id, "run_direct");
    assert.equal(JSON.parse(readFileSync(summaryPath, "utf8")).run.status, "completed");
    assert.equal(JSON.parse(readFileSync(fixturePath, "utf8")).run_id, "run_direct");
    assert.equal(JSON.parse(readFileSync(runPath, "utf8")).run_id, "run_direct");
    assert.equal(JSON.parse(readFileSync(statePath, "utf8")).kind, "local_cloud_state");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("ashr-clone-cloud run-agent fails on case failure when requested", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-direct-fail-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    writeFileSync(inputPath, JSON.stringify({ cases: [{ id: "case-1", prompt: "hello", expected: { text: "expected" } }] }), "utf8");
    writeFileSync(agentPath, "export default { respond() { return { text: 'actual', tool_calls: [] }; } };\n", "utf8");

    const child = spawnSync(
      process.execPath,
      ["dist/cloud-cli.js", "run-agent", "--input", inputPath, "--agent", `${agentPath}:default`, "--fixture-output", fixturePath, "--fail-on-case-failure"],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 1);
    assert.equal(JSON.parse(readFileSync(fixturePath, "utf8")).status, "failed");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("ashr-clone-cloud run-agent supports no-timeout direct execution", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-direct-notimeout-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    writeFileSync(inputPath, JSON.stringify({ cases: sampleCases(1) }), "utf8");
    writeFileSync(agentPath, "export default { respond(message) { return { text: `Echo: ${message}`, tool_calls: [] }; } };\n", "utf8");

    const child = spawnSync(
      process.execPath,
      ["dist/cloud-cli.js", "run-agent", "--input", inputPath, "--agent", `${agentPath}:default`, "--fixture-output", fixturePath, "--no-timeout"],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 0, child.stderr);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("ashr-clone-cloud rejects missing required direct run arguments", () => {
  const child = spawnSync(process.execPath, ["dist/cloud-cli.js", "run-agent", "--input", "missing.json"], { cwd: new URL("../", import.meta.url), encoding: "utf8" });

  assert.equal(child.status, 2);
  assert.equal(child.stderr.includes("missing required --agent"), true);
});

test("ashr-clone-cloud rejects unknown commands with redacted error channel", () => {
  const child = spawnSync(process.execPath, ["dist/cloud-cli.js", "unknown"], { cwd: new URL("../", import.meta.url), encoding: "utf8" });

  assert.equal(child.status, 2);
  assert.equal(child.stderr.includes("cloud api error"), true);
});



test("buildDefaultRequestInputSchema keeps text-only request compact", () => {
  const schema = buildDefaultRequestInputSchema({ agent: { accepted_inputs: { text: true, image: false, audio: false, file: false, video: false } } });

  assert.equal(schema.type, "object");
  assert.equal(schema.additionalProperties, true);
  assert.equal(schema.$defs, undefined);
});

test("buildDefaultRequestInputSchema accepts enabled object flags", () => {
  const schema = buildDefaultRequestInputSchema({ agent: { accepted_inputs: { image: { enabled: true }, audio: { enabled: false }, file: { enabled: true }, video: { enabled: true } } } });
  const partSchema = schema.$defs.agent_input_part;
  const enumValues = partSchema.oneOf ? partSchema.oneOf[partSchema.oneOf.length - 1].properties.type.enum : partSchema.properties.type.enum;

  assert.deepEqual(enumValues, ["image", "file", "video"]);
});

test("CloudApiService rejects blank tenant names", () => {
  const service = new CloudApiService();
  assert.throws(() => service.createTenant(""), ValidationError);
});

test("CloudApiService rejects blank tenant ids", () => {
  const service = new CloudApiService();
  assert.throws(() => service.createTenant("Tenant", { tenantId: "" }), ValidationError);
});

test("CloudApiService rejects projects for missing tenants", () => {
  const service = new CloudApiService();
  assert.throws(() => service.createProject("missing", "Project"), NotFoundError);
});

test("CloudApiService rejects blank project names", () => {
  const service = new CloudApiService();
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_blank_project" });
  assert.throws(() => service.createProject(tenant.tenant_id, ""), ValidationError);
});

test("CloudApiService rejects empty datasets", () => {
  const service = new CloudApiService();
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_empty_dataset" });
  const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_empty_dataset" });
  assert.throws(() => service.createDataset(tenant.tenant_id, project.project_id, { name: "Empty", cases: [] }), ValidationError);
});

test("CloudApiService clones dataset cases on create", () => {
  const cases = sampleCases(1);
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_clone_cases", projectId: "project_clone_cases", datasetId: "dataset_clone_cases", cases });
  cases[0].prompt = "mutated";

  assert.equal(service.getDataset(tenant.tenant_id, project.project_id, "dataset_clone_cases").cases[0].prompt, "hello");
});

test("CloudApiService getTenant returns defensive copies", () => {
  const { service, tenant } = createServiceFixture({ tenantId: "tenant_copy", projectId: "project_copy", datasetId: "dataset_copy" });
  const copy = service.getTenant(tenant.tenant_id);
  copy.name = "Mutated";

  assert.equal(service.getTenant(tenant.tenant_id).name, "Tenant");
});

test("CloudApiService getProject returns defensive copies", () => {
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_project_copy", projectId: "project_project_copy", datasetId: "dataset_project_copy" });
  const copy = service.getProject(tenant.tenant_id, project.project_id);
  copy.name = "Mutated";

  assert.equal(service.getProject(tenant.tenant_id, project.project_id).name, "Project");
});

test("CloudApiService getDataset returns defensive copies", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_dataset_copy", projectId: "project_dataset_copy", datasetId: "dataset_dataset_copy" });
  const copy = service.getDataset(tenant.tenant_id, project.project_id, dataset.dataset_id);
  copy.cases[0].prompt = "Mutated";

  assert.equal(service.getDataset(tenant.tenant_id, project.project_id, dataset.dataset_id).cases[0].prompt, "hello");
});

test("CloudApiService getRequest enforces project isolation", () => {
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_request_iso", projectId: "project_request_iso", datasetId: "dataset_request_iso" });
  service.createRequest(tenant.tenant_id, project.project_id, { requestId: "request_iso", name: "Request" });

  assert.throws(() => service.getRequest(tenant.tenant_id, "other", "request_iso"), NotFoundError);
});

test("CloudApiService listRuns is empty before submissions", () => {
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_no_runs", projectId: "project_no_runs", datasetId: "dataset_no_runs" });

  assert.deepEqual(service.listRuns(tenant.tenant_id, project.project_id), []);
});

test("CloudApiService createQueuedRun preserves runner id and metadata", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_queue_meta", projectId: "project_queue_meta", datasetId: "dataset_queue_meta" });
  const run = service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue_meta", runnerId: "runner_meta", metadata: { replay_order: 7 } });

  assert.equal(run.runner_id, "runner_meta");
  assert.equal(run.metadata.replay_order, 7);
});

test("CloudApiService createQueuedRun rejects duplicate ids", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_queue_dup", projectId: "project_queue_dup", datasetId: "dataset_queue_dup" });
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue_dup" });

  assert.throws(() => service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_queue_dup" }), ValidationError);
});

test("CloudApiService markRunRunning rejects completed runs", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_running_done", projectId: "project_running_done", datasetId: "dataset_sample" });
  service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_done", runResult: sampleRunResult({ run_id: "run_done" }) });

  assert.throws(() => service.markRunRunning(tenant.tenant_id, project.project_id, "run_done"), ValidationError);
});

test("CloudApiService completeRun leaves cancelled runs unchanged", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_complete_cancel", projectId: "project_complete_cancel", datasetId: "dataset_complete_cancel" });
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_cancelled_complete" });
  service.cancelRun(tenant.tenant_id, project.project_id, "run_cancelled_complete");
  const run = service.completeRun(tenant.tenant_id, project.project_id, "run_cancelled_complete", sampleRunResult({ run_id: "run_cancelled_complete" }));

  assert.equal(run.status, "cancelled");
});

test("CloudApiService failRun leaves cancelled runs unchanged", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_fail_cancel", projectId: "project_fail_cancel", datasetId: "dataset_fail_cancel" });
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_cancelled_fail" });
  service.cancelRun(tenant.tenant_id, project.project_id, "run_cancelled_fail");
  const run = service.failRun(tenant.tenant_id, project.project_id, "run_cancelled_fail", { error: "late failure" });

  assert.equal(run.status, "cancelled");
});

test("CloudApiService appendObservation stores defensive copies", () => {
  const { service, tenant, project, dataset } = createServiceFixture({ tenantId: "tenant_obs_copy", projectId: "project_obs_copy", datasetId: "dataset_obs_copy" });
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_obs_copy" });
  const observation = { type: "metric", payload: { score: 1 } };
  service.appendObservation(tenant.tenant_id, project.project_id, "run_obs_copy", observation);
  observation.payload.score = 0;

  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_obs_copy").observations[0].payload.score, 1);
});

test("CloudApiService custom quota can block dataset creation before mutation", () => {
  const service = new CloudApiService({ quota: new QuotaLedger({ "dataset.create": 0 }) });
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_quota_dataset" });
  const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_quota_dataset" });

  assert.throws(() => service.createDataset(tenant.tenant_id, project.project_id, { name: "Dataset", cases: sampleCases(1) }), QuotaExceededError);
  assert.deepEqual(service.listDatasets(tenant.tenant_id, project.project_id), []);
});

test("CloudApiService fromState preserves request records", () => {
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_state_request", projectId: "project_state_request", datasetId: "dataset_state_request" });
  service.createRequest(tenant.tenant_id, project.project_id, { requestId: "request_state", name: "Request State" });
  const restored = CloudApiService.fromState(service.snapshotState());

  assert.equal(restored.getRequest(tenant.tenant_id, project.project_id, "request_state").name, "Request State");
});

test("CloudApiService fromState rejects malformed quota project entries", () => {
  assert.throws(() => CloudApiService.fromState({ kind: "local_cloud_state", store: {}, quota: { projects: ["bad"] } }), ValidationError);
});

test("CloudApiService writeState creates parent directories", async () => {
  const { service } = createServiceFixture({ tenantId: "tenant_write_state", projectId: "project_write_state", datasetId: "dataset_write_state" });
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-write-state-"));
  try {
    const statePath = join(temp, "nested", "state.json");
    await service.writeState(statePath);

    assert.equal(JSON.parse(readFileSync(statePath, "utf8")).kind, "local_cloud_state");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("CloudApiService exportRunFixture rejects unknown run ids", () => {
  const { service, tenant, project } = createServiceFixture({ tenantId: "tenant_missing_fixture", projectId: "project_missing_fixture", datasetId: "dataset_missing_fixture" });

  assert.throws(() => service.exportRunFixture(tenant.tenant_id, project.project_id, "missing"), NotFoundError);
});

test("runAgentCloudDemo records failed case summaries", async () => {
  const summary = await runAgentCloudDemo({
    cases: [{ id: "case-1", prompt: "hello", expected: { text: "expected" } }],
    agent: () => ({ text: "actual", tool_calls: [] }),
    tenantId: "tenant_demo_failed",
    projectId: "project_demo_failed",
    datasetId: "dataset_demo_failed",
  });

  assert.equal(summary.run.status, "failed");
  assert.equal(summary.run.failed, 1);
});

test("ashr-clone-cloud queue-run rejects duplicate explicit run ids", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-queue-dup-cli-"));
  try {
    const inputPath = join(temp, "cases.json");
    const statePath = join(temp, "state.json");
    writeFileSync(inputPath, JSON.stringify({ cases: sampleCases(1) }), "utf8");
    const child = spawnSync(
      process.execPath,
      ["dist/cloud-cli.js", "queue-run", "--input", inputPath, "--state-output", statePath, "--run-id", "run_dup", "--run-id", "run_dup"],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 2);
    assert.equal(child.stderr.includes("run IDs must be unique"), true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

