#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { CloudApiService, TERMINAL_RUN_STATUSES, ValidationError } from "./index.js";
import type { JsonRecord, RunRecord } from "./index.js";
import { CloudQueueWorker } from "./cloud-queue.js";
import { loadAgentTarget, runAgentBatch } from "./runner.js";

type CliOptions = Record<string, string | boolean | string[]>;

async function main(): Promise<number> {
  const argv = process.argv.slice(2);
  const command = argv[0] && !argv[0].startsWith("--") ? argv[0] : "queue-run";
  const options = parseArgs(command === argv[0] ? argv.slice(1) : argv);
  if (options.help || options.h) {
    printHelp();
    return 0;
  }
  if (command === "run-agent") {
    const summary = await runAgent(options);
    process.stdout.write(`${JSON.stringify(summary)}\n`);
    const run = isRecord(summary.run) ? summary.run : {};
    const hasFailure = Boolean(run.failed || run.errored || run.timed_out);
    return options["fail-on-case-failure"] && hasFailure ? 1 : 0;
  }
  if (command === "run-agent-queued") {
    const summary = await runAgentQueued(options);
    process.stdout.write(`${JSON.stringify(summaryLine(command, summary))}
`);
    const run = Array.isArray(summary.runs) && isRecord(summary.runs[0]) ? summary.runs[0] : {};
    const hasFailure = Boolean(run.failed || run.errored || run.timed_out);
    return options["fail-on-case-failure"] && hasFailure ? 1 : 0;
  }
  if (command === "queue-run") {
    const summary = await queueRun(options);
    process.stdout.write(`${JSON.stringify(summaryLine(command, summary))}\n`);
    return 0;
  }
  if (command === "replay-queued") {
    const summary = await replayQueued(options);
    process.stdout.write(`${JSON.stringify(summaryLine(command, summary))}\n`);
    return 0;
  }
  if (command === "export-fixture") {
    const summary = await exportFixture(options);
    process.stdout.write(`${JSON.stringify(summaryLine(command, summary))}\n`);
    return 0;
  }
  throw new Error(`unknown command: ${command}`);
}

async function runAgent(options: CliOptions): Promise<JsonRecord> {
  const inputPath = stringOption(options, "input", true);
  const agentTarget = stringOption(options, "agent", true);
  const fixtureOutput = stringOption(options, "fixture-output", true);
  const summaryOutput = stringOption(options, "summary-output", false);
  const runOutput = stringOption(options, "run-output", false);
  const stateOutput = stringOption(options, "state-output", false);
  const tenantId = stringOption(options, "tenant-id", false) ?? "tenant_ts_demo";
  const projectId = stringOption(options, "project-id", false) ?? "project_ts_demo";
  const datasetId = stringOption(options, "dataset-id", false) ?? "dataset_ts_demo";
  const tenantName = stringOption(options, "tenant-name", false) ?? "TS Demo Tenant";
  const projectName = stringOption(options, "project-name", false) ?? "TS Demo Project";
  const datasetName = stringOption(options, "dataset-name", false) ?? "TS Demo Dataset";
  const runnerId = stringOption(options, "runner-id", false) ?? "a1-ts-cloud-demo-runner";
  const cases = await loadCases(inputPath);
  const service = new CloudApiService();
  const tenant = service.createTenant(tenantName, { tenantId, metadata: { local_only: true } });
  const project = service.createProject(tenant.tenant_id, projectName, { projectId, metadata: { local_only: true } });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId,
    name: datasetName,
    cases,
    metadata: { source: "packages/ts/releasefoundry/cloud-cli.run-agent", input_path: inputPath },
  });
  const agent = await loadAgentTarget(agentTarget);
  const runResult = await runAgentBatch(agent, cases, {
    datasetId: dataset.dataset_id,
    runnerId,
    runId: stringOption(options, "run-id", false),
    maxWorkers: numberOption(options, "max-workers", 4),
    timeoutSeconds: options["no-timeout"] ? null : timeoutOption(options, "timeout", 30),
    metadata: { local_only: true, releasefoundry_api_used: false },
  });
  const run = service.submitRun(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    runResult,
    runId: runResult.run_id,
    metadata: { source: "packages/ts/releasefoundry/cloud-cli.run-agent" },
  });
  const poll = service.pollRun(tenant.tenant_id, project.project_id, run.run_id);
  await service.writeRunFixture(tenant.tenant_id, project.project_id, run.run_id, fixtureOutput);
  if (runOutput) {
    await writeJson(runOutput, runResult);
  }
  if (stateOutput) {
    await service.writeState(stateOutput);
  }
  const summary = demoSummary({
    tenant,
    project,
    dataset,
    run,
    poll,
    quota: service.quotaSnapshot(tenant.tenant_id, project.project_id),
    fixtureOutput,
    runOutput: runOutput ?? null,
    stateOutput: stateOutput ?? null,
  });
  if (summaryOutput) {
    await writeJson(summaryOutput, summary);
  }
  return summary;
}

async function queueRun(options: CliOptions): Promise<JsonRecord> {
  const inputPath = stringOption(options, "input", true);
  const stateOutput = stringOption(options, "state-output", true);
  const summaryOutput = stringOption(options, "summary-output", false);
  const tenantId = stringOption(options, "tenant-id", false) ?? "tenant_ts_queue_state";
  const projectId = stringOption(options, "project-id", false) ?? "project_ts_queue_state";
  const datasetId = stringOption(options, "dataset-id", false) ?? "dataset_ts_queue_state";
  const tenantName = stringOption(options, "tenant-name", false) ?? "TS Queue State Tenant";
  const projectName = stringOption(options, "project-name", false) ?? "TS Queue State Project";
  const datasetName = stringOption(options, "dataset-name", false) ?? "TS Queue State Dataset";
  const runnerId = stringOption(options, "runner-id", false) ?? "a1-ts-cloud-queue-runner";
  const cases = await loadCases(inputPath);
  const service = new CloudApiService();
  const tenant = service.createTenant(tenantName, { tenantId, metadata: { local_only: true } });
  const project = service.createProject(tenant.tenant_id, projectName, { projectId, metadata: { local_only: true } });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId,
    name: datasetName,
    cases,
    metadata: { source: "packages/ts/releasefoundry/cloud-cli", input_path: inputPath },
  });
  const runIds = queueRunIds(dataset.dataset_id, stringListOption(options, "run-id"), numberOption(options, "run-count", 1));
  const queuedRuns = runIds.map((runId, index) =>
    service.createQueuedRun(tenant.tenant_id, project.project_id, {
      datasetId: dataset.dataset_id,
      runnerId,
      runId,
      metadata: {
        source: "packages/ts/releasefoundry/cloud-cli.queue-run",
        batch_index: index,
        batch_size: runIds.length,
        replay_order: index,
      },
    }),
  );
  await service.writeState(stateOutput);
  const summary = stateSummary({
    tenant,
    project,
    dataset,
    runs: queuedRuns,
    quota: service.quotaSnapshot(tenant.tenant_id, project.project_id),
    stateInput: null,
    stateOutput,
  });
  summary.queue = {
    run_ids: queuedRuns.map((run) => run.run_id),
    queued_statuses: queuedRuns.map((run) => ({ run_id: run.run_id, status: run.status })),
    status_histories: Object.fromEntries(queuedRuns.map((run) => [run.run_id, run.status_history ?? []])),
    batch_size: queuedRuns.length,
  };
  if (summaryOutput) {
    await writeJson(summaryOutput, summary);
  }
  return summary;
}

async function runAgentQueued(options: CliOptions): Promise<JsonRecord> {
  const inputPath = stringOption(options, "input", true);
  const agentTarget = stringOption(options, "agent", true);
  const fixtureOutput = stringOption(options, "fixture-output", true);
  const summaryOutput = stringOption(options, "summary-output", false);
  const runOutput = stringOption(options, "run-output", false);
  const stateOutput = stringOption(options, "state-output", false);
  const tenantId = stringOption(options, "tenant-id", false) ?? "tenant_ts_queue_demo";
  const projectId = stringOption(options, "project-id", false) ?? "project_ts_queue_demo";
  const datasetId = stringOption(options, "dataset-id", false) ?? "dataset_ts_queue_demo";
  const tenantName = stringOption(options, "tenant-name", false) ?? "TS Queue Demo Tenant";
  const projectName = stringOption(options, "project-name", false) ?? "TS Queue Demo Project";
  const datasetName = stringOption(options, "dataset-name", false) ?? "TS Queue Demo Dataset";
  const runnerId = stringOption(options, "runner-id", false) ?? "a1-ts-cloud-queue-runner";
  const cases = await loadCases(inputPath);
  const service = new CloudApiService();
  const tenant = service.createTenant(tenantName, { tenantId, metadata: { local_only: true } });
  const project = service.createProject(tenant.tenant_id, projectName, { projectId, metadata: { local_only: true } });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId,
    name: datasetName,
    cases,
    metadata: { source: "packages/ts/releasefoundry/cloud-cli.run-agent-queued", input_path: inputPath },
  });
  const agent = await loadAgentTarget(agentTarget);
  const worker = new CloudQueueWorker(service, { queueWorkers: numberOption(options, "queue-workers", 4) });
  const queued = worker.enqueueAgentRun({
    tenantId: tenant.tenant_id,
    projectId: project.project_id,
    datasetId: dataset.dataset_id,
    agent,
    runnerId,
    runId: stringOption(options, "run-id", false),
    maxWorkers: numberOption(options, "max-workers", 4),
    timeoutSeconds: timeoutOption(options, "timeout", 30),
    metadata: { source: "packages/ts/releasefoundry/cloud-cli.run-agent-queued" },
  });
  const poll = await worker.waitForRun(tenant.tenant_id, project.project_id, queued.run_id, {
    timeoutSeconds: timeoutOption(options, "wait-timeout", 30),
    requireTerminal: true,
  });
  await service.writeRunFixture(tenant.tenant_id, project.project_id, poll.run.run_id, fixtureOutput);
  if (runOutput) {
    await writeJson(runOutput, poll.run.result);
  }
  if (stateOutput) {
    await service.writeState(stateOutput);
  }
  const summary = stateSummary({
    tenant,
    project,
    dataset,
    runs: [poll.run],
    quota: service.quotaSnapshot(tenant.tenant_id, project.project_id),
    stateInput: null,
    stateOutput: stateOutput ?? null,
  });
  summary.queue = {
    run_id: poll.run.run_id,
    queued_status: queued.status,
    status_history: poll.run.status_history ?? [],
    queue_workers: numberOption(options, "queue-workers", 4),
    runner_max_workers: numberOption(options, "max-workers", 4),
  };
  summary.outputs = { ...(summary.outputs as JsonRecord), fixture: resolve(fixtureOutput), run_result: runOutput ? resolve(runOutput) : null };
  if (summaryOutput) {
    await writeJson(summaryOutput, summary);
  }
  return summary;
}

async function replayQueued(options: CliOptions): Promise<JsonRecord> {
  const stateInput = stringOption(options, "state-input", true);
  const agentTarget = stringOption(options, "agent", true);
  const tenantId = stringOption(options, "tenant-id", true);
  const projectId = stringOption(options, "project-id", true);
  const datasetId = stringOption(options, "dataset-id", false);
  const service = await CloudApiService.fromStateFile(stateInput);
  const agent = await loadAgentTarget(agentTarget);
  const worker = new CloudQueueWorker(service, { queueWorkers: numberOption(options, "queue-workers", 4) });
  const replayed = worker.replayIncompleteRuns(tenantId, projectId, {
    agent,
    datasetId,
    statuses: stringListOption(options, "status", ["queued", "running"]),
    maxRuns: numberOption(options, "max-runs", 100),
    maxWorkers: numberOption(options, "max-workers", 4),
    timeoutSeconds: timeoutOption(options, "timeout", 30),
    metadata: { state_input_path: stateInput },
  });
  const completed: RunRecord[] = [];
  for (const run of replayed) {
    const poll = await worker.waitForRun(tenantId, projectId, run.run_id, {
      timeoutSeconds: timeoutOption(options, "wait-timeout", 30),
      requireTerminal: true,
    });
    completed.push(poll.run);
  }
  const outputs = await writeReplayOutputs(service, tenantId, projectId, completed, {
    fixtureOutput: stringOption(options, "fixture-output", false),
    fixtureOutputDir: stringOption(options, "fixture-output-dir", false),
    runOutput: stringOption(options, "run-output", false),
    runOutputDir: stringOption(options, "run-output-dir", false),
  });
  const stateOutput = stringOption(options, "state-output", false);
  if (stateOutput) {
    await service.writeState(stateOutput);
  }
  const dataset = datasetId || completed[0]?.dataset_id || replayed[0]?.dataset_id;
  const summary = stateSummary({
    tenant: service.getTenant(tenantId),
    project: service.getProject(tenantId, projectId),
    dataset: dataset ? service.getDataset(tenantId, projectId, dataset) : null,
    runs: completed,
    quota: service.quotaSnapshot(tenantId, projectId),
    stateInput,
    stateOutput: stateOutput ?? null,
  });
  summary.replay = {
    replayed: replayed.map((run) => run.run_id),
    completed: completed.map((run) => ({ run_id: run.run_id, status: run.status })),
    status_histories: Object.fromEntries(completed.map((run) => [run.run_id, run.status_history ?? []])),
  };
  summary.outputs = { ...(summary.outputs as JsonRecord), ...outputs };
  const summaryOutput = stringOption(options, "summary-output", false);
  if (summaryOutput) {
    await writeJson(summaryOutput, summary);
  }
  return summary;
}

async function exportFixture(options: CliOptions): Promise<JsonRecord> {
  const stateInput = stringOption(options, "state-input", true);
  const tenantId = stringOption(options, "tenant-id", true);
  const projectId = stringOption(options, "project-id", true);
  const runId = stringOption(options, "run-id", true);
  const fixtureOutput = stringOption(options, "fixture-output", true);
  const service = await CloudApiService.fromStateFile(stateInput);
  const poll = service.pollRun(tenantId, projectId, runId);
  if (!options["allow-incomplete"] && !TERMINAL_RUN_STATUSES.has(poll.status)) {
    throw new ValidationError(`run ${runId} must be terminal before fixture export; current status=${poll.status}`);
  }
  await service.writeRunFixture(tenantId, projectId, runId, fixtureOutput);
  const summary = stateSummary({
    tenant: service.getTenant(tenantId),
    project: service.getProject(tenantId, projectId),
    dataset: service.getDataset(tenantId, projectId, poll.run.dataset_id),
    runs: [poll.run],
    quota: service.quotaSnapshot(tenantId, projectId),
    stateInput,
    stateOutput: null,
  });
  summary.outputs = { ...(summary.outputs as JsonRecord), fixture: resolve(fixtureOutput) };
  summary.export = { run_id: runId, status: poll.status, allow_incomplete: Boolean(options["allow-incomplete"]) };
  const summaryOutput = stringOption(options, "summary-output", false);
  if (summaryOutput) {
    await writeJson(summaryOutput, summary);
  }
  return summary;
}

async function writeReplayOutputs(
  service: CloudApiService,
  tenantId: string,
  projectId: string,
  runs: RunRecord[],
  options: { fixtureOutput?: string; fixtureOutputDir?: string; runOutput?: string; runOutputDir?: string },
): Promise<JsonRecord> {
  if (options.fixtureOutput && options.fixtureOutputDir) {
    throw new ValidationError("use either --fixture-output or --fixture-output-dir");
  }
  if (options.runOutput && options.runOutputDir) {
    throw new ValidationError("use either --run-output or --run-output-dir");
  }
  if (options.fixtureOutput && runs.length !== 1) {
    throw new ValidationError("--fixture-output requires exactly one replayed run; use --fixture-output-dir for batches");
  }
  if (options.runOutput && runs.length !== 1) {
    throw new ValidationError("--run-output requires exactly one replayed run; use --run-output-dir for batches");
  }
  const outputs: JsonRecord = { fixture: null, fixtures: {}, run_result: null, run_results: {} };
  if (options.fixtureOutput && runs[0]) {
    await service.writeRunFixture(tenantId, projectId, runs[0].run_id, options.fixtureOutput);
    outputs.fixture = resolve(options.fixtureOutput);
  }
  if (options.runOutput && runs[0]) {
    await writeJson(options.runOutput, runs[0].result);
    outputs.run_result = resolve(options.runOutput);
  }
  if (options.fixtureOutputDir) {
    const fixtures: Record<string, string> = {};
    for (const run of runs) {
      const path = resolve(options.fixtureOutputDir, `${safeFileName(run.run_id)}.fixture.json`);
      await service.writeRunFixture(tenantId, projectId, run.run_id, path);
      fixtures[run.run_id] = path;
    }
    outputs.fixtures = fixtures;
  }
  if (options.runOutputDir) {
    const runResults: Record<string, string> = {};
    for (const run of runs) {
      const path = resolve(options.runOutputDir, `${safeFileName(run.run_id)}.run.json`);
      await writeJson(path, run.result);
      runResults[run.run_id] = path;
    }
    outputs.run_results = runResults;
  }
  return outputs;
}

function stateSummary(options: {
  tenant: JsonRecord;
  project: JsonRecord;
  dataset: JsonRecord | null;
  runs: RunRecord[];
  quota: JsonRecord;
  stateInput: string | null;
  stateOutput: string | null;
}): JsonRecord {
  return {
    schema_version: "releasefoundry.cloud_api.v1",
    tenant: { tenant_id: options.tenant.tenant_id, name: options.tenant.name },
    project: { project_id: options.project.project_id, tenant_id: options.project.tenant_id, name: options.project.name },
    dataset: options.dataset
      ? { dataset_id: options.dataset.dataset_id, case_count: options.dataset.case_count, name: options.dataset.name }
      : null,
    run_ids: options.runs.map((run) => run.run_id),
    runs: options.runs.map((run) => ({
      run_id: run.run_id,
      dataset_id: run.dataset_id,
      status: run.status,
      result_status: run.result_status,
      runner_id: run.runner_id,
      total_cases: run.total_cases,
      passed: run.result.passed ?? null,
      failed: run.result.failed ?? null,
      errored: run.result.errored ?? null,
      timed_out: run.result.timed_out ?? null,
      observations: run.observations.length,
      status_history: run.status_history ?? [],
    })),
    quota: { used: options.quota.used ?? {}, remaining: options.quota.remaining ?? {} },
    outputs: {
      state_input: options.stateInput ? resolve(options.stateInput) : null,
      state: options.stateOutput ? resolve(options.stateOutput) : null,
    },
    metadata: { local_only: true, releasefoundry_api_used: false },
  };
}

function demoSummary(options: {
  tenant: JsonRecord;
  project: JsonRecord;
  dataset: JsonRecord;
  run: RunRecord;
  poll: ReturnType<CloudApiService["pollRun"]>;
  quota: JsonRecord;
  fixtureOutput: string;
  runOutput: string | null;
  stateOutput: string | null;
}): JsonRecord {
  const result = options.run.result ?? {};
  return {
    schema_version: "releasefoundry.cloud_api.v1",
    tenant: { tenant_id: options.tenant.tenant_id, name: options.tenant.name },
    project: { project_id: options.project.project_id, tenant_id: options.project.tenant_id, name: options.project.name },
    dataset: { dataset_id: options.dataset.dataset_id, case_count: options.dataset.case_count, name: options.dataset.name },
    run: {
      run_id: options.run.run_id,
      dataset_id: options.run.dataset_id,
      status: options.run.status,
      result_status: options.run.result_status,
      runner_id: options.run.runner_id,
      total_cases: options.run.total_cases,
      passed: result.passed ?? null,
      failed: result.failed ?? null,
      errored: result.errored ?? null,
      timed_out: result.timed_out ?? null,
      trace_completeness: result.trace_completeness ?? null,
      observations: options.run.observations.length,
    },
    poll: { status: options.poll.status, run_id: options.poll.run_id },
    quota: { used: options.quota.used ?? {}, remaining: options.quota.remaining ?? {} },
    outputs: {
      fixture: resolve(options.fixtureOutput),
      run_result: options.runOutput ? resolve(options.runOutput) : null,
      state: options.stateOutput ? resolve(options.stateOutput) : null,
    },
    metadata: { local_only: true, releasefoundry_api_used: false },
  };
}

async function loadCases(inputPath: string): Promise<JsonRecord[]> {
  const payload = JSON.parse(await readFile(resolve(inputPath), "utf8")) as unknown;
  const cases = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.cases) ? payload.cases : undefined;
  if (!cases) {
    throw new Error("input JSON must be a case list or object with cases");
  }
  return cases.map((item, index) => (isRecord(item) ? item : { id: `case-${index + 1}`, input: item }));
}

function queueRunIds(datasetId: string, explicitIds: string[], runCount: number): Array<string | undefined> {
  const count = Math.trunc(Number(runCount));
  if (!Number.isFinite(count) || count < 1) {
    throw new ValidationError("run-count must be positive");
  }
  if (explicitIds.length) {
    if (count !== 1 && count !== explicitIds.length) {
      throw new ValidationError("run-count must match the number of explicit run IDs");
    }
    if (new Set(explicitIds).size !== explicitIds.length) {
      throw new ValidationError("run IDs must be unique");
    }
    return explicitIds;
  }
  if (count === 1) {
    return [undefined];
  }
  const prefix = safeFileName(datasetId) || "dataset";
  return Array.from({ length: count }, (_, index) => `run_${prefix}_${String(index + 1).padStart(3, "0")}`);
}

function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      throw new Error(`unexpected argument: ${arg}`);
    }
    const name = arg.slice(2);
    const next = args[index + 1];
    if (next === undefined || next.startsWith("--")) {
      options[name] = true;
      continue;
    }
    if (options[name] === undefined) {
      options[name] = next;
    } else if (Array.isArray(options[name])) {
      (options[name] as string[]).push(next);
    } else {
      options[name] = [String(options[name]), next];
    }
    index += 1;
  }
  return options;
}

function stringOption(options: CliOptions, name: string, required: true): string;
function stringOption(options: CliOptions, name: string, required: false): string | undefined;
function stringOption(options: CliOptions, name: string, required: boolean): string | undefined {
  const value = options[name];
  if (typeof value === "string") {
    return value;
  }
  if (required) {
    throw new Error(`missing required --${name}`);
  }
  return undefined;
}

function stringListOption(options: CliOptions, name: string, fallback: string[] = []): string[] {
  const value = options[name];
  if (Array.isArray(value)) {
    return value.map(String);
  }
  if (typeof value === "string") {
    return [value];
  }
  return fallback;
}

function timeoutOption(options: CliOptions, name: string, fallback: number): number | null {
  if (name === "timeout" && options["no-timeout"]) {
    return null;
  }
  return numberOption(options, name, fallback);
}

function numberOption(options: CliOptions, name: string, fallback: number): number {
  const value = options[name];
  if (value === undefined || value === true) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`--${name} must be numeric`);
  }
  return parsed;
}

async function writeJson(path: string, value: unknown): Promise<void> {
  const output = resolve(path);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function summaryLine(command: string, summary: JsonRecord): JsonRecord {
  return {
    status: "ok",
    command,
    run_ids: summary.run_ids ?? [],
    outputs: summary.outputs ?? {},
    quota: summary.quota ?? {},
  };
}

function safeFileName(value: string): string {
  return value.replace(/[^A-Za-z0-9_.-]/g, "_").replace(/^[._]+|[._]+$/g, "") || "run";
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function printHelp(): void {
  process.stdout.write(`releasefoundry-cloud

Commands:
  run-agent       Run an agent directly, submit the local run, and write outputs.
  run-agent-queued Queue an agent run, wait for completion, and write outputs.
  queue-run        Create a local cloud state with one or more queued TS runs.
  replay-queued    Replay queued/running runs from a saved state through an agent.
  export-fixture   Export a run fixture from a saved state.

run-agent:
  --input <cases.json>
  --agent <module:export>
  --fixture-output <file>
  --summary-output <file>
  --run-output <file>
  --state-output <state.json>
  --tenant-id <id> --project-id <id> --dataset-id <id>
  --tenant-name <name> --project-name <name> --dataset-name <name>
  --run-id <id>
  --max-workers <n> --timeout <seconds> --no-timeout
  --fail-on-case-failure

run-agent-queued:
  --input <cases.json>
  --agent <module:export>
  --fixture-output <file>
  --summary-output <file>
  --run-output <file>
  --state-output <state.json>
  --tenant-id <id> --project-id <id> --dataset-id <id>
  --tenant-name <name> --project-name <name> --dataset-name <name>
  --run-id <id>
  --queue-workers <n> --max-workers <n> --timeout <seconds> --no-timeout --wait-timeout <seconds>
  --fail-on-case-failure

queue-run:
  --input <cases.json>
  --state-output <state.json>
  --tenant-id <id> --project-id <id> --dataset-id <id>
  --tenant-name <name> --project-name <name> --dataset-name <name>
  --run-id <id>        repeatable
  --run-count <n>

replay-queued:
  --state-input <state.json>
  --agent <module:export>
  --tenant-id <id> --project-id <id>
  --fixture-output <file> | --fixture-output-dir <dir>
  --run-output <file> | --run-output-dir <dir>
  --state-output <state.json>
  --queue-workers <n> --max-workers <n> --timeout <seconds> --no-timeout --wait-timeout <seconds>

export-fixture:
  --state-input <state.json>
  --tenant-id <id> --project-id <id> --run-id <id>
  --fixture-output <file>
  --allow-incomplete
`);
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    process.stderr.write(`cloud api error: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
  });

