import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import packageJson from "../package.json" with { type: "json" };
import {
  SaaSControlPlaneRouter,
  SaaSControlPlaneService,
  SaaSIngestionClient,
  exportSaaSOpenApiSpec,
  runSaaSCli,
} from "../dist/saas.js";

function seededService() {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_release", projectId: "project_ts_release" });
  service.cloud.createDataset("tenant_ts_release", "project_ts_release", { datasetId: "dataset_ts_release", name: "Dataset", cases: [{ id: "case-1", prompt: "ship?" }] });
  service.createApiKey("tenant_ts_release", "project_ts_release", { name: "release key", scopes: ["sdk:submit", "run:upload", "trace:ingest", "artifact:write", "audit:read"], keyId: "key_ts_release" });
  service.sdkSubmitRun("tenant_ts_release", "project_ts_release", { datasetId: "dataset_ts_release", agentRef: "mock", runId: "run_ts_release", apiKeyId: "key_ts_release" });
  service.uploadRunResult("tenant_ts_release", "project_ts_release", "run_ts_release", { status: "completed", api_key: "tp_should_not_leak", score: 0.98 }, { uploadId: "upload_ts_release", apiKeyId: "key_ts_release" });
  service.ingestTrace("tenant_ts_release", "project_ts_release", "run_ts_release", [{ observation_id: "obs-1", type: "agent_message", content: "ok" }], { batchId: "trace_ts_release", apiKeyId: "key_ts_release" });
  service.createArtifactManifest("tenant_ts_release", "project_ts_release", "run_ts_release", { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json", api_key: "tp_should_not_leak" }] }, { artifactId: "artifact_ts_release", apiKeyId: "key_ts_release" });
  return service;
}

function assertPublicSafe(value) {
  const text = JSON.stringify(value);
  assert.equal(text.includes("tp_should_not_leak"), false);
  assert.equal(text.includes("secret_hash_sha256"), false);
  assert.equal(text.includes("ASHR_API_KEY"), false);
}

test("TS release gate passes complete local lifecycle", () => {
  const gate = seededService().evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release");
  assert.equal(gate.decision, "pass");
  assert.equal(gate.trace_completeness, 1);
  assert.equal(gate.upload_count, 1);
  assert.equal(gate.trace_batch_count, 1);
  assert.equal(gate.observation_count, 1);
  assert.deepEqual(gate.blockers, []);
  assert.equal(gate.local_only, true);
});

test("TS release gate blocks missing evidence with named blockers", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_block", projectId: "project_ts_block" });
  service.cloud.createDataset("tenant_ts_block", "project_ts_block", { datasetId: "dataset_ts_block", name: "Dataset", cases: [{ id: "case-1" }] });
  service.sdkSubmitRun("tenant_ts_block", "project_ts_block", { datasetId: "dataset_ts_block", agentRef: "mock", runId: "run_ts_block" });
  const gate = service.evaluateReleaseGate("tenant_ts_block", "project_ts_block", "run_ts_block", { minScore: 0.99 });
  assert.equal(gate.decision, "block");
  assert.equal(gate.blockers.includes("score_below_threshold"), true);
  assert.equal(gate.blockers.includes("trace_completeness_below_threshold"), true);
  assert.equal(gate.blockers.includes("missing_run_upload"), true);
});

test("TS audit snapshot filters release gate events by run and action", () => {
  const service = seededService();
  service.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release", { requestId: "req-release" });
  const snapshot = service.auditSnapshot("tenant_ts_release", "project_ts_release", { runId: "run_ts_release", actionPrefix: "release_gate", limit: 5 });
  assert.equal(snapshot.event_count, 1);
  assert.equal(snapshot.events[0].action, "release_gate.evaluate");
  assert.equal(snapshot.events[0].request_id, "req-release");
  assertPublicSafe(snapshot);
});

test("TS release evidence packet summarizes counts hashes usage and redaction", () => {
  const service = seededService();
  const packet = service.buildReleaseEvidencePacket("tenant_ts_release", "project_ts_release", "run_ts_release");
  assert.equal(packet.packet_schema_version, "ashr.clone.release_evidence_packet.v1");
  assert.equal(packet.counts.uploads, 1);
  assert.equal(packet.counts.trace_batches, 1);
  assert.equal(packet.counts.observations, 1);
  assert.equal(packet.counts.artifacts, 1);
  assert.equal(packet.usage_totals["trace.ingest"], 1);
  assert.match(packet.hashes.uploads_sha256, /^[a-f0-9]{64}$/);
  assert.match(packet.integrity.packet_sha256, /^[a-f0-9]{64}$/);
  assert.equal(packet.redaction.raw_payload_included, false);
  assertPublicSafe(packet);
});

test("TS release evidence packet integrity changes when evidence changes", () => {
  const service = seededService();
  const before = service.buildReleaseEvidencePacket("tenant_ts_release", "project_ts_release", "run_ts_release");
  service.ingestTrace("tenant_ts_release", "project_ts_release", "run_ts_release", [{ observation_id: "obs-2", type: "tool_call" }], { batchId: "trace_ts_release_2", apiKeyId: "key_ts_release" });
  const after = service.buildReleaseEvidencePacket("tenant_ts_release", "project_ts_release", "run_ts_release");
  assert.notEqual(after.integrity.packet_sha256, before.integrity.packet_sha256);
  assert.equal(after.counts.trace_batches, 2);
  assert.equal(after.counts.observations, 2);
});

test("TS router exposes release gate audit log and release evidence routes", () => {
  const router = new SaaSControlPlaneRouter(seededService());
  const tenant = { tenant_id: "tenant_ts_release", api_key_id: "key_ts_release" };
  const gate = router.handle("POST", "/v1/projects/project_ts_release/runs/run_ts_release/release-gate", { ...tenant, request_id: "req-router" });
  assert.equal(gate.status_code, 200);
  assert.equal(gate.body.decision, "pass");
  const audit = router.handle("GET", "/v1/projects/project_ts_release/audit-log", { ...tenant, run_id: "run_ts_release", action_prefix: "release_gate" });
  assert.equal(audit.status_code, 200);
  assert.equal(audit.body.events.some((event) => event.request_id === "req-router"), true);
  const evidence = router.handle("GET", "/v1/projects/project_ts_release/runs/run_ts_release/release-evidence", tenant);
  assert.equal(evidence.status_code, 200);
  assert.equal(evidence.body.counts.artifacts, 1);
  assertPublicSafe(evidence);
});

test("TS router release gate validates tenant and run boundaries", () => {
  const router = new SaaSControlPlaneRouter(seededService());
  const missingTenant = router.handle("POST", "/v1/projects/project_ts_release/runs/run_ts_release/release-gate", {});
  assert.equal(missingTenant.status_code, 400);
  assert.equal(missingTenant.body.error.message, "tenant_id is required");
  const wrongRun = router.handle("POST", "/v1/projects/project_ts_release/runs/run_missing/release-gate", { tenant_id: "tenant_ts_release" });
  assert.equal(wrongRun.status_code, 404);
});

test("TS OpenAPI advertises release and audit parity routes", () => {
  const spec = exportSaaSOpenApiSpec({ serverUrl: "http://127.0.0.1" });
  assert.equal(spec.paths["/v1/projects/{project_id}/runs/{run_id}/release-gate"].post.operationId, "evaluateReleaseGate");
  assert.equal(spec.paths["/v1/projects/{project_id}/runs/{run_id}/release-evidence"].get.operationId, "buildReleaseEvidencePacket");
  assert.equal(spec.paths["/v1/projects/{project_id}/audit-log"].get.operationId, "auditSnapshot");
  assertPublicSafe(spec);
});

test("TS client local wrappers envelope release gate audit and evidence operations", () => {
  const client = new SaaSIngestionClient({ service: seededService() });
  const gate = client.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release");
  const audit = client.auditLog("tenant_ts_release", "project_ts_release", { actionPrefix: "release_gate" });
  const evidence = client.buildReleaseEvidencePacket("tenant_ts_release", "project_ts_release", "run_ts_release");
  assert.equal(gate.operation, "release_gate");
  assert.equal(audit.operation, "audit_log");
  assert.equal(evidence.operation, "release_evidence");
  assert.equal(evidence.result.counts.artifacts, 1);
});

test("TS client HTTP wrappers call hosted release endpoints", async () => {
  const router = new SaaSControlPlaneRouter(seededService());
  const server = createServer((req, res) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      const queryBody = Object.fromEntries(url.searchParams.entries());
      const body = { ...queryBody, ...(raw ? JSON.parse(raw) : {}) };
      const routed = router.handle(req.method ?? "GET", url.pathname, body);
      res.statusCode = routed.status_code;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(routed.body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    const client = SaaSIngestionClient.forBaseUrl(`http://127.0.0.1:${address.port}`);
    const gate = await client.evaluateReleaseGateHttp("tenant_ts_release", "project_ts_release", "run_ts_release", { authKeyId: "key_ts_release" });
    const audit = await client.auditLogHttp("tenant_ts_release", "project_ts_release", { runId: "run_ts_release", actionPrefix: "release_gate", authKeyId: "key_ts_release" });
    const evidence = await client.buildReleaseEvidencePacketHttp("tenant_ts_release", "project_ts_release", "run_ts_release", { authKeyId: "key_ts_release" });
    assert.equal(gate.result.decision, "pass");
    assert.equal(audit.result.event_count >= 1, true);
    assert.equal(evidence.result.release_gate.decision, "pass");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("TS SaaS CLI package exposes bin and help mentions release commands", async () => {
  assert.equal(packageJson.bin["ashr-clone-saas"], "./dist/saas.js");
  const help = await runSaaSCli(["--help"]);
  assert.equal(help.operation, "help");
  assert.equal(help.usage.includes("release-gate"), true);
  assert.equal(help.usage.includes("release-evidence"), true);
  assert.equal(help.usage.includes("audit-log"), true);
});

test("TS SaaS CLI evaluates release gate from persisted state", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "ashr-ts-release-cli-"));
  try {
    const statePath = join(tempDir, "state.json");
    await writeFile(statePath, `${JSON.stringify(seededService().snapshotState(), null, 2)}\n`, "utf8");
    const gate = runSaasCli(["--state-input", statePath, "release-gate", "--tenant-id", "tenant_ts_release", "--project-id", "project_ts_release", "--run-id", "run_ts_release"]);
    assert.equal(gate.operation, "release_gate");
    assert.equal(gate.result.decision, "pass");
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("TS SaaS CLI writes state after release gate audit append", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "ashr-ts-release-state-"));
  try {
    const inputPath = join(tempDir, "input.json");
    const outputPath = join(tempDir, "output.json");
    await writeFile(inputPath, `${JSON.stringify(seededService().snapshotState(), null, 2)}\n`, "utf8");
    const gate = runSaasCli(["--state-input", inputPath, "--state-output", outputPath, "release-gate", "--tenant-id", "tenant_ts_release", "--project-id", "project_ts_release", "--run-id", "run_ts_release", "--request-id", "req-cli"]);
    assert.equal(gate.state_output, outputPath);
    const persisted = JSON.parse(await readFile(outputPath, "utf8"));
    assert.equal(Object.values(persisted.control_plane.audit_log).some((event) => event.request_id === "req-cli"), true);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("TS SaaS CLI emits audit log and release evidence from state", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "ashr-ts-release-audit-"));
  try {
    const statePath = join(tempDir, "state.json");
    const service = seededService();
    service.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release", { requestId: "req-audit" });
    await writeFile(statePath, `${JSON.stringify(service.snapshotState(), null, 2)}\n`, "utf8");
    const audit = runSaasCli(["--state-input", statePath, "audit-log", "--tenant-id", "tenant_ts_release", "--project-id", "project_ts_release", "--run-id", "run_ts_release", "--action-prefix", "release_gate"]);
    const evidence = runSaasCli(["--state-input", statePath, "release-evidence", "--tenant-id", "tenant_ts_release", "--project-id", "project_ts_release", "--run-id", "run_ts_release"]);
    assert.equal(audit.operation, "audit_log");
    assert.equal(audit.result.events.some((event) => event.request_id === "req-audit"), true);
    assert.equal(evidence.operation, "release_evidence");
    assert.match(evidence.result.integrity.packet_sha256, /^[a-f0-9]{64}$/);
    assertPublicSafe(evidence);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("TS SaaS CLI hosted mode rejects state mixing for release commands", async () => {
  await assert.rejects(
    () => runSaaSCli(["--base-url", "http://127.0.0.1:1", "--state-input", "state.json", "release-gate", "--tenant-id", "t", "--project-id", "p", "--run-id", "r"]),
    /--base-url cannot be combined/,
  );
});

test("TS release evidence packet survives snapshot restore", () => {
  const restored = SaaSControlPlaneService.fromState(seededService().snapshotState());
  const packet = restored.buildReleaseEvidencePacket("tenant_ts_release", "project_ts_release", "run_ts_release");
  assert.equal(packet.counts.uploads, 1);
  assert.equal(packet.counts.trace_batches, 1);
  assert.equal(packet.counts.artifacts, 1);
});

test("TS release gate honors custom thresholds", () => {
  const service = seededService();
  const high = service.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release", { minScore: 1.01 });
  const low = service.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release", { minScore: 0.1, requiredTraceCompleteness: 0.1 });
  assert.equal(high.decision, "block");
  assert.equal(high.blockers.includes("score_below_threshold"), true);
  assert.equal(low.decision, "pass");
});

test("TS audit snapshot enforces bounded limit", () => {
  const service = seededService();
  for (let index = 0; index < 6; index += 1) service.evaluateReleaseGate("tenant_ts_release", "project_ts_release", "run_ts_release", { requestId: `req-${index}` });
  const snapshot = service.auditSnapshot("tenant_ts_release", "project_ts_release", { actionPrefix: "release_gate", limit: 3 });
  assert.equal(snapshot.event_count, 3);
  assert.deepEqual(snapshot.events.map((event) => event.request_id), ["req-3", "req-4", "req-5"]);
});

function runSaasCli(args) {
  const child = spawnSync(process.execPath, ["dist/saas.js", ...args], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });
  assert.equal(child.status, 0, child.stderr || child.stdout);
  return JSON.parse(child.stdout);
}
