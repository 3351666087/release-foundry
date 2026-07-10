import assert from "node:assert/strict";
import { once } from "node:events";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { SaaSIngestionClient } from "../dist/saas.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const goServerCwd = resolve(__dirname, "../../../go/ashrclone");

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  const port = typeof address === "object" && address !== null ? address.port : 0;
  server.close();
  await once(server, "close");
  return port;
}

async function buildGoServerBinary() {
  const dir = await mkdtemp(join(tmpdir(), "ashr-ts-go-server-"));
  const binary = join(dir, process.platform === "win32" ? "ashr-api.exe" : "ashr-api");
  const command = process.platform === "win32" ? (process.env.ComSpec ?? "C:\\Windows\\System32\\cmd.exe") : (process.env.GO_EXE ?? "go");
  const args = process.platform === "win32" ? ["/c", "go", "build", "-o", binary, "./cmd/ashr-api"] : ["build", "-o", binary, "./cmd/ashr-api"];
  const build = spawnSync(command, args, { cwd: goServerCwd, encoding: "utf8" });
  if (build.status !== 0) throw new Error(`failed to build Go server: ${build.stderr || build.stdout}`);
  return { binary, dir };
}

async function waitForHealth(client, child) {
  let lastError;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) break;
    try {
      const health = await client.healthz();
      if (health.status === "ok") return health;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Go server did not become healthy: ${lastError?.message ?? "unknown"}`);
}

test("TS SaaS client drives the real Go HTTP server vertical slice", async () => {
  const port = await freePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const built = await buildGoServerBinary();
  const child = spawn(built.binary, [], {
    cwd: goServerCwd,
    env: {
      ...process.env,
      ASHR_GO_API_ADDR: `127.0.0.1:${port}`,
      ASHR_GO_BACKEND: "memory",
      ASHR_ENVIRONMENT: "development",
      ASHR_IDENTITY_RUNTIME: "memory",
      ASHR_IDENTITY_MEMORY_ENABLED: "true",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stderr = [];
  child.stderr.on("data", (chunk) => stderr.push(String(chunk)));
  try {
    const client = SaaSIngestionClient.forBaseUrl(baseUrl);
    const apiKeyId = "key_ts_go";
    const health = await waitForHealth(client, child);
    assert.equal(health.backend, "memory_service_v0");

    const boot = await client.requestJson("POST", "/v1/bootstrap", {
      tenant_name: "Tenant",
      project_name: "Project",
      tenant_id: "tenant_ts_go",
      project_id: "project_ts_go",
      dataset_id: "dataset_ts_go",
      dataset_name: "Dataset",
    });
    assert.equal(boot.project.project_id, "project_ts_go");

    const submit = await client.sdkSubmitHttp("tenant_ts_go", "project_ts_go", {
      dataset_id: "dataset_ts_go",
      agent_ref: "agent:ts-go",
      run_id: "run_ts_go",
      api_key_id: apiKeyId,
      idempotency_key: "idem-submit-ts-go",
    });
    assert.equal(submit.result.run_id, "run_ts_go");

    const upload = await client.uploadRunHttp("tenant_ts_go", "project_ts_go", "run_ts_go", { status: "completed", media: [{ modality: "text", text: "ok" }] }, { upload_id: "upload_ts_go", apiKeyId, idempotency_key: "idem-upload-ts-go" });
    assert.equal(upload.result.upload_id, "upload_ts_go");
    assert.equal(upload.result.raw_payload_included, false);

    const trace = await client.ingestTraceHttp("tenant_ts_go", "project_ts_go", "run_ts_go", [{ observation_id: "obs_ts_go", modality: "text", type: "agent_message" }], { batch_id: "trace_ts_go", apiKeyId, idempotency_key: "idem-trace-ts-go" });
    assert.equal(trace.result.batch_id, "trace_ts_go");
    assert.equal(trace.result.observation_count, 1);

    const artifact = await client.createArtifactManifestHttp("tenant_ts_go", "project_ts_go", "run_ts_go", { artifact_type: "run_fixture", modalities: ["text", "audio", "file", "image", "video"] }, { artifactId: "artifact_ts_go", apiKeyId, idempotencyKey: "idem-artifact-ts-go" });
    assert.equal(artifact.result.artifact_id, "artifact_ts_go");
    const artifacts = await client.listArtifactManifestsHttp("tenant_ts_go", "project_ts_go", "run_ts_go", { authKeyId: apiKeyId });
    assert.equal(artifacts.result.count, 1);

    const usage = await client.usageHttp("tenant_ts_go", "project_ts_go", { authKeyId: apiKeyId });
    assert.equal(usage.operation, "usage_snapshot");
    assert.equal(usage.result.tenant_id, "tenant_ts_go");
    assert.equal(usage.result.project_id, "project_ts_go");
    assert.equal(usage.result.operation_totals === null || Array.isArray(usage.result.operation_totals), true);
    assert.equal(typeof usage.result.total_units, "number");
    assert.equal(typeof usage.result.total_events, "number");

    const audit = await client.verifyAuditChainHttp("tenant_ts_go", "project_ts_go", { authKeyId: apiKeyId, requestId: "audit-ts-go" });
    assert.equal(audit.operation, "audit_chain_verify");
    assert.equal(audit.result.tenant_id, "tenant_ts_go");
    assert.equal(audit.result.project_id, "project_ts_go");
    assert.equal(audit.result.verified, true);
    assert.equal(typeof audit.result.event_count, "number");

    const enqueued = await client.enqueueWorkerJobHttp("tenant_ts_go", "project_ts_go", { job_type: "release_gate", target_id: "run_ts_go", job_id: "job_ts_go", payload: { run_id: "run_ts_go" }, apiKeyId, idempotency_key: "idem-job-ts-go" });
    assert.equal(enqueued.result.job_id, "job_ts_go");
    const leased = await client.leaseWorkerJobHttp("tenant_ts_go", "project_ts_go", { lease_owner_id: "worker_ts_go", job_type: "release_gate", apiKeyId });
    assert.equal(leased.result.leased, true);
    const completed = await client.completeWorkerJobHttp("tenant_ts_go", "project_ts_go", "job_ts_go", { status: "ok" }, { lease_owner_id: "worker_ts_go", apiKeyId });
    assert.equal(completed.result.status, "completed");
    const jobs = await client.listWorkerJobsHttp("tenant_ts_go", "project_ts_go", { status: "completed", authKeyId: apiKeyId });
    assert.equal(jobs.result.count, 1);
  } finally {
    child.kill();
    await Promise.race([once(child, "exit"), new Promise((resolve) => setTimeout(resolve, 2000))]);
    await rm(built.dir, { recursive: true, force: true });
    assert.equal(child.exitCode === 0 || child.exitCode === null || child.signalCode !== null, true, stderr.join(""));
  }
});
