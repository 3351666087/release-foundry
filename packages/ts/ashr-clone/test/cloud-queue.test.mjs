import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  CloudApiService,
  CloudQueueWorker,
  TERMINAL_RUN_STATUSES,
  ValidationError,
} from "../dist/index.js";

function cases() {
  return [
    { id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } },
    {
      id: "case-2",
      input: {
        text: "inspect",
        parts: [
          { type: "text", text: "inspect" },
          { type: "image", path: "fixtures/image.png", mime_type: "image/png" },
          { type: "audio", path: "fixtures/audio.wav", mime_type: "audio/wav" },
          { type: "file", path: "fixtures/data.json", mime_type: "application/json" },
          { type: "video", path: "fixtures/clip.mp4", mime_type: "video/mp4" },
        ],
      },
      expected: { text: "Echo: inspect" },
    },
  ];
}


function createRealtimeQueuedService() {
  const service = new CloudApiService();
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_realtime_queue" });
  const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_realtime_queue" });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId: "dataset_realtime_queue",
    name: "Dataset",
    cases: [{ id: "slow", prompt: "hello", expected: { text: "Echo: hello" } }],
  });
  return { service, tenant, project, dataset };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function createQueuedService() {
  const service = new CloudApiService({ clock: () => "2026-07-04T00:00:00.000Z" });
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_queue" });
  const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_queue" });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId: "dataset_queue",
    name: "Dataset",
    cases: cases(),
  });
  return { service, tenant, project, dataset };
}

test("CloudQueueWorker replays queued runs in deterministic batch order and restores state", async () => {
  const { service, tenant, project, dataset } = createQueuedService();
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-"));
  try {
    service.createQueuedRun(tenant.tenant_id, project.project_id, {
      datasetId: dataset.dataset_id,
      runId: "run_second",
      metadata: { batch_index: 1, replay_order: 1 },
    });
    service.createQueuedRun(tenant.tenant_id, project.project_id, {
      datasetId: dataset.dataset_id,
      runId: "run_first",
      metadata: { batch_index: 0, replay_order: 0 },
    });
    const statePath = join(temp, "state.json");
    await service.writeState(statePath);

    const restored = await CloudApiService.fromStateFile(statePath);
    const agent = { respond: (message) => ({ text: `Echo: ${message}`, tool_calls: [] }) };
    const worker = new CloudQueueWorker(restored, { queueWorkers: 2 });
    const replayed = worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
      agent,
      maxRuns: 2,
      maxWorkers: 1,
      timeoutSeconds: 5,
    });
    assert.deepEqual(replayed.map((run) => run.run_id), ["run_first", "run_second"]);

    const first = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_first", { requireTerminal: true, timeoutSeconds: 5 });
    const second = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_second", { requireTerminal: true, timeoutSeconds: 5 });
    assert.equal(first.status, "completed");
    assert.equal(second.status, "completed");
    assert.equal(TERMINAL_RUN_STATUSES.has(first.status), true);
    assert.deepEqual(first.run.status_history.map((item) => item.status), ["queued", "running", "completed"]);
    assert.equal(restored.quotaSnapshot(tenant.tenant_id, project.project_id).used["run.submit"], 2);
    assert.equal(restored.quotaSnapshot(tenant.tenant_id, project.project_id).used["observation.write"], 8);

    const fixturePath = join(temp, "run_first.fixture.json");
    await restored.writeRunFixture(tenant.tenant_id, project.project_id, "run_first", fixturePath);
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    assert.equal(fixture.metadata.ashr_api_used, false);
    assert.equal(fixture.observations.length, 4);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("CloudQueueWorker cancellation and replay validation match Python failure paths", () => {
  const { service, tenant, project, dataset } = createQueuedService();
  const worker = new CloudQueueWorker(service, { queueWorkers: 1 });
  const queued = service.createQueuedRun(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    runId: "run_cancel",
  });
  const cancelled = worker.cancelRun(tenant.tenant_id, project.project_id, queued.run_id, { reason: "operator stopped" });
  assert.equal(cancelled.status, "cancelled");
  assert.throws(() => worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, { agent: { respond: () => "ok" }, statuses: ["completed"] }), ValidationError);
});

test("CloudQueueWorker limits active replay work to normalized queueWorkers", async () => {
  const { service, tenant, project, dataset } = createQueuedService();
  for (let index = 1; index <= 5; index += 1) {
    service.createQueuedRun(tenant.tenant_id, project.project_id, {
      datasetId: dataset.dataset_id,
      runId: `run_${index}`,
      metadata: { replay_order: index },
    });
  }

  let releaseFirstInvocation;
  const firstInvocationReleased = new Promise((resolve) => {
    releaseFirstInvocation = resolve;
  });
  let blockedFirstInvocation = false;
  const agent = {
    respond(input) {
      const message = typeof input === "string" ? input : input.text;
      if (!blockedFirstInvocation) {
        blockedFirstInvocation = true;
        return new Promise((resolve) => {
          firstInvocationReleased.then(() => resolve({ text: `Echo: ${message}`, tool_calls: [] }));
        });
      }
      return { text: `Echo: ${message}`, tool_calls: [] };
    },
  };
  const worker = new CloudQueueWorker(service, { queueWorkers: 1 });
  worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent,
    maxRuns: 5,
    maxWorkers: 1,
    timeoutSeconds: 5,
  });
  assert.equal(worker.queueWorkers, 4);

  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_1").status, "running");
  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_2").status, "running");
  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_3").status, "running");
  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_4").status, "running");
  assert.equal(service.getRun(tenant.tenant_id, project.project_id, "run_5").status, "queued");

  releaseFirstInvocation();
  const completed = await Promise.all(
    [1, 2, 3, 4, 5].map((index) => worker.waitForRun(tenant.tenant_id, project.project_id, `run_${index}`, { requireTerminal: true, timeoutSeconds: 5 })),
  );
  assert.deepEqual(completed.map((poll) => poll.status), ["completed", "completed", "completed", "completed", "completed"]);
  assert.deepEqual(completed[4].run.status_history.map((item) => item.status), ["queued", "running", "completed"]);
});


test("CloudApiService leases, heartbeats, reclaims, and rejects permanent leases", () => {
  const { service, tenant, project, dataset } = createQueuedService();
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_lease" });
  const running = service.markRunRunning(tenant.tenant_id, project.project_id, "run_lease", {
    leaseOwnerId: "worker-a",
    leaseSeconds: 60,
  });
  const heartbeat = service.heartbeatRun(tenant.tenant_id, project.project_id, "run_lease", {
    leaseOwnerId: "worker-a",
    leaseSeconds: 120,
  });

  assert.equal(running.lease_owner_id, "worker-a");
  assert.equal(typeof running.lease_expires_at, "string");
  assert.equal(typeof heartbeat.lease_heartbeat_at, "string");
  assert.throws(() => service.heartbeatRun(tenant.tenant_id, project.project_id, "run_lease", { leaseOwnerId: "worker-b" }), ValidationError);
  assert.throws(() => service.heartbeatRun(tenant.tenant_id, project.project_id, "run_lease", { leaseOwnerId: "worker-a", leaseSeconds: null }), ValidationError);
  assert.throws(() => service.completeRun(tenant.tenant_id, project.project_id, "run_lease", { run_id: "run_lease", status: "passed", ended_at: "2026-07-04T00:00:00.000Z", cases: [] }), ValidationError);
  assert.throws(() => service.completeRun(tenant.tenant_id, project.project_id, "run_lease", { run_id: "run_lease", status: "passed", ended_at: "2026-07-04T00:00:00.000Z", cases: [] }, { leaseOwnerId: "worker-b" }), ValidationError);
  assert.throws(() => service.completeRun(tenant.tenant_id, project.project_id, "run_lease", { run_id: "run_lease", status: "running", cases: [] }, { leaseOwnerId: "worker-a" }), ValidationError);

  const completed = service.completeRun(tenant.tenant_id, project.project_id, "run_lease", { run_id: "run_lease", status: "passed", ended_at: "2026-07-04T00:00:00.000Z", cases: [] }, { leaseOwnerId: "worker-a" });
  assert.equal(completed.status, "completed");
  assert.equal(completed.lease_owner_id, null);
  assert.equal(completed.lease_expires_at, null);

  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_permanent_guard" });
  assert.throws(() => service.markRunRunning(tenant.tenant_id, project.project_id, "run_permanent_guard", { leaseOwnerId: "worker-a", leaseSeconds: null }), ValidationError);
});

test("CloudQueueWorker reclaims expired running leases", async () => {
  const { service, tenant, project, dataset } = createQueuedService();
  service.createQueuedRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runId: "run_expired" });
  service.markRunRunning(tenant.tenant_id, project.project_id, "run_expired", { leaseOwnerId: "dead-worker", leaseSeconds: 1 });
  service.reclaimExpiredRunLeases(tenant.tenant_id, project.project_id, { now: "2999-01-01T00:00:00.000Z" });

  const worker = new CloudQueueWorker(service, { queueWorkers: 1 });
  const replayed = worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent: { respond: (message) => ({ text: `Echo: ${message}`, tool_calls: [] }) },
    maxRuns: 1,
    maxWorkers: 1,
    timeoutSeconds: 5,
  });
  assert.deepEqual(replayed.map((run) => run.run_id), ["run_expired"]);

  const completed = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_expired", { requireTerminal: true, timeoutSeconds: 5 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.run.lease_reclaim_count, 1);
  assert.equal(completed.run.lease_owner_id, null);
  assert.deepEqual(completed.run.status_history.map((item) => item.status), ["queued", "running", "queued", "running", "completed"]);
});

test("CloudQueueWorker renews active leases and blocks double replay", async () => {
  const { service, tenant, project, dataset } = createRealtimeQueuedService();
  let calls = 0;
  const slowAgent = {
    async respond(message) {
      calls += 1;
      await delay(300);
      return { text: `Echo: ${message}`, tool_calls: [] };
    },
  };

  const firstWorker = new CloudQueueWorker(service, { queueWorkers: 1 });
  firstWorker.enqueueAgentRun({
    tenantId: tenant.tenant_id,
    projectId: project.project_id,
    datasetId: dataset.dataset_id,
    agent: slowAgent,
    runId: "run_active_lease",
    maxWorkers: 1,
    timeoutSeconds: 5,
    leaseSeconds: 0.15,
  });
  await delay(220);

  const secondWorker = new CloudQueueWorker(service, { queueWorkers: 1 });
  const replayed = secondWorker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent: slowAgent,
    maxRuns: 1,
    maxWorkers: 1,
    timeoutSeconds: 5,
    leaseSeconds: 0.15,
  });
  const completed = await firstWorker.waitForRun(tenant.tenant_id, project.project_id, "run_active_lease", { requireTerminal: true, timeoutSeconds: 5 });

  assert.deepEqual(replayed, []);
  assert.equal(completed.status, "completed");
  assert.equal(completed.run.lease_reclaim_count, 0);
  assert.equal(completed.run.lease_owner_id, null);
  assert.equal(calls, 1);
});

test("CloudQueueWorker rejects stale owner completion after reclaim by another worker", async () => {
  const { service, tenant, project, dataset } = createRealtimeQueuedService();
  service.createQueuedRun(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    runId: "run_stale_owner",
  });
  const staleOwner = "worker-4-run_stale_owner";
  service.markRunRunning(tenant.tenant_id, project.project_id, "run_stale_owner", {
    leaseOwnerId: staleOwner,
    leaseSeconds: 0.01,
  });
  service.reclaimExpiredRunLeases(tenant.tenant_id, project.project_id, {
    now: "2999-01-01T00:00:00.000Z",
  });

  let releaseAgent;
  const agentReleased = new Promise((resolve) => {
    releaseAgent = resolve;
  });
  const worker = new CloudQueueWorker(service, { queueWorkers: 4 });
  const replayed = worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent: {
      async respond(message) {
        await agentReleased;
        return { text: `Echo: ${message}`, tool_calls: [] };
      },
    },
    maxRuns: 1,
    maxWorkers: 1,
    timeoutSeconds: 5,
    leaseSeconds: 2,
  });

  assert.deepEqual(replayed.map((run) => run.run_id), ["run_stale_owner"]);
  await delay(50);
  const running = service.getRun(tenant.tenant_id, project.project_id, "run_stale_owner");
  assert.equal(running.status, "running");
  assert.notEqual(running.lease_owner_id, staleOwner);
  assert.throws(() => service.completeRun(tenant.tenant_id, project.project_id, "run_stale_owner", { run_id: "run_stale_owner", status: "passed", ended_at: "2026-07-04T00:00:00.000Z", cases: [] }, { leaseOwnerId: staleOwner }), ValidationError);

  releaseAgent();
  const completed = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_stale_owner", { requireTerminal: true, timeoutSeconds: 5 });
  assert.equal(completed.status, "completed");
  assert.equal(completed.run.lease_owner_id, null);
});

test("CloudQueueWorker does not let settled futures block later replays", async () => {
  const { service, tenant, project, dataset } = createQueuedService();
  service.createQueuedRun(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    runId: "run_requeued_after_settled",
  });
  const worker = new CloudQueueWorker(service, { queueWorkers: 1 });
  worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent: { respond: (message) => ({ text: `Echo: ${message}`, tool_calls: [] }) },
    maxRuns: 1,
    maxWorkers: 1,
    timeoutSeconds: 5,
  });
  const first = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_requeued_after_settled", { requireTerminal: true, timeoutSeconds: 5 });
  assert.equal(first.status, "completed");

  const rawRun = service.store.runs.run_requeued_after_settled;
  rawRun.status = "queued";
  rawRun.result_status = "queued";
  rawRun.result.status = "queued";
  rawRun.observations = [];

  const replayed = worker.replayIncompleteRuns(tenant.tenant_id, project.project_id, {
    agent: { respond: (message) => ({ text: `Echo: ${message}`, tool_calls: [] }) },
    maxRuns: 1,
    maxWorkers: 1,
    timeoutSeconds: 5,
  });
  assert.deepEqual(replayed.map((run) => run.run_id), ["run_requeued_after_settled"]);
  const second = await worker.waitForRun(tenant.tenant_id, project.project_id, "run_requeued_after_settled", { requireTerminal: true, timeoutSeconds: 5 });
  assert.equal(second.status, "completed");
});
test("ashr-clone-cloud CLI queues, replays, and exports TS fixtures", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-cli-"));
  try {
    const inputPath = join(temp, "cases.json");
    const statePath = join(temp, "state.json");
    const replayedStatePath = join(temp, "replayed-state.json");
    const summaryPath = join(temp, "summary.json");
    const fixtureDir = join(temp, "fixtures");
    const runDir = join(temp, "runs");
    const exportPath = join(temp, "exported.fixture.json");
    const agentPath = join(temp, "agent.mjs");
    writeFileSync(inputPath, JSON.stringify({ cases: cases() }), "utf8");
    writeFileSync(agentPath, "export default { respond(message) { return { text: `Echo: ${message}`, tool_calls: [] }; } };\n", "utf8");

    const queue = spawnSync(
      process.execPath,
      [
        "dist/cloud-cli.js",
        "queue-run",
        "--input",
        inputPath,
        "--state-output",
        statePath,
        "--summary-output",
        join(temp, "queued-summary.json"),
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--dataset-id",
        "dataset_cli",
        "--run-id",
        "run_cli_b",
        "--run-id",
        "run_cli_a",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );
    assert.equal(queue.status, 0, queue.stderr);
    assert.equal(JSON.parse(queue.stdout).run_ids.length, 2);

    const replay = spawnSync(
      process.execPath,
      [
        "dist/cloud-cli.js",
        "replay-queued",
        "--state-input",
        statePath,
        "--agent",
        `${agentPath}:default`,
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--fixture-output-dir",
        fixtureDir,
        "--run-output-dir",
        runDir,
        "--summary-output",
        summaryPath,
        "--state-output",
        replayedStatePath,
        "--queue-workers",
        "4",
        "--max-workers",
        "4",
        "--timeout",
        "5",
        "--wait-timeout",
        "5",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );
    assert.equal(replay.status, 0, replay.stderr);
    const replaySummary = JSON.parse(readFileSync(summaryPath, "utf8"));
    assert.deepEqual(replaySummary.replay.completed.map((item) => item.status), ["completed", "completed"]);
    assert.equal(Object.keys(replaySummary.outputs.fixtures).length, 2);
    assert.equal(Object.keys(replaySummary.outputs.run_results).length, 2);

    const exportRun = spawnSync(
      process.execPath,
      [
        "dist/cloud-cli.js",
        "export-fixture",
        "--state-input",
        replayedStatePath,
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--run-id",
        "run_cli_a",
        "--fixture-output",
        exportPath,
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );
    assert.equal(exportRun.status, 0, exportRun.stderr);
    assert.equal(existsSync(exportPath), true);
    assert.equal(JSON.parse(readFileSync(exportPath, "utf8")).status, "completed");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});


test("ashr-clone-cloud CLI run-agent mirrors Python direct cloud demo", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-direct-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    const runPath = join(temp, "run.json");
    const summaryPath = join(temp, "summary.json");
    const statePath = join(temp, "state.json");
    writeFileSync(inputPath, JSON.stringify({ cases: cases() }), "utf8");
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
        "--run-output",
        runPath,
        "--summary-output",
        summaryPath,
        "--state-output",
        statePath,
        "--tenant-id",
        "tenant_direct",
        "--project-id",
        "project_direct",
        "--tenant-name",
        "Tenant Direct",
        "--project-name",
        "Project Direct",
        "--dataset-id",
        "dataset_direct",
        "--dataset-name",
        "Dataset Direct",
        "--runner-id",
        "runner_direct",
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
    const stdout = JSON.parse(child.stdout);
    const summary = JSON.parse(readFileSync(summaryPath, "utf8"));
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    const run = JSON.parse(readFileSync(runPath, "utf8"));
    const state = JSON.parse(readFileSync(statePath, "utf8"));
    assert.equal(stdout.run.run_id, "run_direct");
    assert.equal(stdout.run.status, "completed");
    assert.equal(stdout.poll.status, "completed");
    assert.equal(summary.tenant.name, "Tenant Direct");
    assert.equal(summary.project.name, "Project Direct");
    assert.equal(summary.dataset.name, "Dataset Direct");
    assert.equal(summary.run.passed, 2);
    assert.equal(summary.run.trace_completeness, 1);
    assert.equal(summary.outputs.fixture, fixturePath);
    assert.equal(summary.outputs.run_result, runPath);
    assert.equal(summary.outputs.state, statePath);
    assert.equal(fixture.run_id, "run_direct");
    assert.equal(run.run_id, "run_direct");
    assert.equal(state.kind, "local_cloud_state");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});


test("ashr-clone-cloud CLI run-agent returns nonzero on case failure when requested", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-direct-fail-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    writeFileSync(inputPath, JSON.stringify({ cases: [{ id: "case-1", prompt: "hello", expected: { text: "not hello" } }] }), "utf8");
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
        "--fail-on-case-failure",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 1, child.stderr);
    const stdout = JSON.parse(child.stdout);
    assert.equal(stdout.run.failed, 1);
    assert.equal(existsSync(fixturePath), true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});


test("ashr-clone-cloud CLI run-agent-queued mirrors Python one-shot queue demo", () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-cloud-one-shot-"));
  try {
    const inputPath = join(temp, "cases.json");
    const agentPath = join(temp, "agent.mjs");
    const fixturePath = join(temp, "fixture.json");
    const runPath = join(temp, "run.json");
    const summaryPath = join(temp, "summary.json");
    const statePath = join(temp, "state.json");
    writeFileSync(inputPath, JSON.stringify({ cases: cases() }), "utf8");
    writeFileSync(agentPath, "export default { respond(message) { return { text: `Echo: ${message}`, tool_calls: [] }; } };\n", "utf8");

    const child = spawnSync(
      process.execPath,
      [
        "dist/cloud-cli.js",
        "run-agent-queued",
        "--input",
        inputPath,
        "--agent",
        `${agentPath}:default`,
        "--fixture-output",
        fixturePath,
        "--run-output",
        runPath,
        "--summary-output",
        summaryPath,
        "--state-output",
        statePath,
        "--tenant-id",
        "tenant_one_shot",
        "--project-id",
        "project_one_shot",
        "--tenant-name",
        "Tenant One Shot",
        "--project-name",
        "Project One Shot",
        "--dataset-id",
        "dataset_one_shot",
        "--dataset-name",
        "Dataset One Shot",
        "--runner-id",
        "runner_one_shot",
        "--run-id",
        "run_one_shot",
        "--queue-workers",
        "1",
        "--max-workers",
        "1",
        "--timeout",
        "5",
        "--wait-timeout",
        "5",
        "--fail-on-case-failure",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 0, child.stderr);
    const stdout = JSON.parse(child.stdout);
    const summary = JSON.parse(readFileSync(summaryPath, "utf8"));
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    const run = JSON.parse(readFileSync(runPath, "utf8"));
    const state = JSON.parse(readFileSync(statePath, "utf8"));
    assert.deepEqual(stdout.run_ids, ["run_one_shot"]);
    assert.equal(summary.tenant.name, "Tenant One Shot");
    assert.equal(summary.project.name, "Project One Shot");
    assert.equal(summary.dataset.name, "Dataset One Shot");
    assert.equal(summary.runs[0].status, "completed");
    assert.deepEqual(summary.runs[0].status_history.map((item) => item.status), ["queued", "running", "completed"]);
    assert.equal(fixture.run_id, "run_one_shot");
    assert.equal(run.run_id, "run_one_shot");
    assert.equal(state.kind, "local_cloud_state");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
