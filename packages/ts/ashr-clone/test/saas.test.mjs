import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { SaaSControlPlaneRouter, SaaSControlPlaneService, SaaSIngestionClient, CONTROL_PLANE_SCHEMA_VERSION } from "../dist/saas.js";

test("TS SaaS control plane covers key submit upload trace lifecycle idempotency", async () => {
  const service = new SaaSControlPlaneService();
  const boot = service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_saas", projectId: "project_ts_saas" });
  service.cloud.createDataset("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", name: "Dataset", cases: [{ id: "case-1", prompt: "hello" }] });
  assert.equal(boot.schema_version, CONTROL_PLANE_SCHEMA_VERSION);

  const key = service.createApiKey("tenant_ts_saas", "project_ts_saas", { name: "ingester", scopes: ["sdk:submit", "run:upload", "trace:ingest"], keyId: "key_ts_saas" });
  assert.equal(key.secret_value_present, false);
  assert.equal(JSON.stringify(key).includes("secret_hash_sha256"), false);

  const submitted = service.sdkSubmitRun("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", agentRef: "mock", runId: "run_ts_saas", apiKeyId: "key_ts_saas", idempotencyKey: "idem-submit" });
  const replay = service.sdkSubmitRun("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", agentRef: "mock", runId: "run_ts_saas", apiKeyId: "key_ts_saas", idempotencyKey: "idem-submit", requestId: "retry-request" });
  assert.equal(submitted.run.run_id, "run_ts_saas");
  assert.equal(replay.idempotent_replay, true);
  assert.equal(replay.run.run_id, "run_ts_saas");

  const upload = service.uploadRunResult("tenant_ts_saas", "project_ts_saas", "run_ts_saas", { run_id: "run_ts_saas", status: "completed", api_key: "tp_should_not_leak" }, { uploadId: "upload_ts_saas", apiKeyId: "key_ts_saas", idempotencyKey: "idem-upload" });
  assert.deepEqual(upload.payload_keys, ["api_key", "run_id", "status"]);
  assert.equal(upload.raw_payload_included, false);
  assert.equal(JSON.stringify(upload).includes("tp_should_not_leak"), false);

  const trace = service.ingestTrace("tenant_ts_saas", "project_ts_saas", "run_ts_saas", [{ observation_id: "obs_ts_saas", type: "agent_message" }], { batchId: "trace_ts_saas", apiKeyId: "key_ts_saas", idempotencyKey: "idem-trace" });
  assert.deepEqual(trace.observation_ids, ["obs_ts_saas"]);

  const lifecycle = service.lifecycleSnapshot("tenant_ts_saas", "project_ts_saas", "run_ts_saas");
  assert.equal(lifecycle.quota.used["sdk.submit"], 1);
  assert.equal(lifecycle.quota.used["run.submit"], 1);
  assert.equal(lifecycle.quota.used["run.upload"], 1);
  assert.equal(lifecycle.quota.used["trace.ingest"], 1);
  assert.equal(lifecycle.usage_ledger.length, 3);
  assert.equal(lifecycle.audit_log.length >= 3, true);

  const restored = SaaSControlPlaneService.fromState(service.snapshotState());
  assert.equal(restored.lifecycleSnapshot("tenant_ts_saas", "project_ts_saas", "run_ts_saas").trace_batches[0].batch_id, "trace_ts_saas");
});

test("TS SaaS API key one-time secret verify and public redaction parity", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_secret", projectId: "project_ts_secret" });
  service.cloud.createDataset("tenant_ts_secret", "project_ts_secret", { datasetId: "dataset_ts_secret", name: "Dataset", cases: [{ id: "case-1" }] });

  const created = service.createApiKey("tenant_ts_secret", "project_ts_secret", {
    name: "CI writer",
    scopes: ["sdk:submit", "run:upload"],
    keyId: "key_ts_secret",
    revealSecret: true,
  });
  const secret = created.one_time_secret;
  assert.equal(typeof secret, "string");
  assert.equal(secret.startsWith("ashr_local_key_ts_secret_"), true);
  assert.equal(created.secret_value_present, true);
  assert.equal(created.one_time_secret_displayed, true);
  assert.equal(created.verify_mode, "sha256");
  assert.equal(JSON.stringify(created).includes("secret_hash_sha256"), false);

  const listed = service.listApiKeys("tenant_ts_secret", "project_ts_secret");
  const listedText = JSON.stringify(listed);
  assert.equal(listed[0].secret_value_present, false);
  assert.equal(listed[0].secret_hash_present, true);
  assert.equal(listed[0].one_time_secret_displayed, true);
  assert.equal(listed[0].verify_mode, "sha256");
  assert.equal(listedText.includes(secret), false);
  assert.equal(listedText.includes("secret_hash_sha256"), false);

  const verified = service.verifyApiKeySecret("tenant_ts_secret", "project_ts_secret", { keyId: "key_ts_secret", secret, scope: "sdk:submit" });
  assert.equal(verified.authenticated, true);
  assert.equal(verified.api_key.key_id, "key_ts_secret");
  assert.equal(verified.secret_value_present, false);
  assert.throws(
    () => service.verifyApiKeySecret("tenant_ts_secret", "project_ts_secret", { keyId: "key_ts_secret", secret: "wrong" }),
    /secret verification failed/,
  );
});

test("TS SaaS API key rate limit blocks before mutation and records snapshot", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_rate", projectId: "project_ts_rate" });
  service.cloud.createDataset("tenant_ts_rate", "project_ts_rate", { datasetId: "dataset_ts_rate", name: "Dataset", cases: [{ id: "case-1" }] });
  service.createApiKey("tenant_ts_rate", "project_ts_rate", { name: "Limited submitter", scopes: ["sdk:submit"], keyId: "key_ts_rate", revealSecret: true });

  const configured = service.configureApiKeyRateLimit("tenant_ts_rate", "project_ts_rate", { keyId: "key_ts_rate", operation: "sdk:submit", limit: 1 });
  assert.equal(configured.limit, 1);
  assert.equal(configured.remaining, 1);

  const first = service.sdkSubmitRun("tenant_ts_rate", "project_ts_rate", { datasetId: "dataset_ts_rate", agentRef: "mock", runId: "run_ts_rate_1", apiKeyId: "key_ts_rate" });
  assert.equal(first.run.run_id, "run_ts_rate_1");
  assert.throws(
    () => service.sdkSubmitRun("tenant_ts_rate", "project_ts_rate", { datasetId: "dataset_ts_rate", agentRef: "mock", runId: "run_ts_rate_2", apiKeyId: "key_ts_rate" }),
    /rate limit exceeded/,
  );
  assert.throws(() => service.cloud.getRun("tenant_ts_rate", "project_ts_rate", "run_ts_rate_2"));

  const snapshot = service.apiKeyRateLimitSnapshot("tenant_ts_rate", "project_ts_rate", { keyId: "key_ts_rate" });
  assert.equal(snapshot.schema_version, CONTROL_PLANE_SCHEMA_VERSION);
  assert.equal(snapshot.rate_limits[0].used, 1);
  assert.equal(snapshot.rate_limits[0].remaining, 0);
});

test("TS SaaS idempotency keys reject request fingerprint conflicts before usage audit and mutation", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_idem_conflict", projectId: "project_ts_idem_conflict" });
  service.cloud.createDataset("tenant_ts_idem_conflict", "project_ts_idem_conflict", { datasetId: "dataset_ts_idem_conflict", name: "Dataset", cases: [{ id: "case-1" }] });
  service.createApiKey("tenant_ts_idem_conflict", "project_ts_idem_conflict", { name: "writer", scopes: ["sdk:submit", "run:upload", "trace:ingest", "artifact:write", "usage:read", "audit:read", "evidence:read"], keyId: "key_ts_idem_conflict" });
  for (const operation of ["sdk:submit", "run:upload", "trace:ingest", "artifact:upload"]) {
    service.configureApiKeyRateLimit("tenant_ts_idem_conflict", "project_ts_idem_conflict", { keyId: "key_ts_idem_conflict", operation, limit: 20 });
  }

  service.sdkSubmitRun("tenant_ts_idem_conflict", "project_ts_idem_conflict", { datasetId: "dataset_ts_idem_conflict", agentRef: "mock", runId: "run_ts_idem_conflict", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-submit" });
  const submitReplay = service.sdkSubmitRun("tenant_ts_idem_conflict", "project_ts_idem_conflict", { datasetId: "dataset_ts_idem_conflict", agentRef: "mock", runId: "run_ts_idem_conflict", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-submit", requestId: "retry-request" });
  assert.equal(submitReplay.idempotent_replay, true);

  service.uploadRunResult("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", { status: "completed" }, { uploadId: "upload_ts_idem_conflict", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-upload" });
  service.ingestTrace("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", [{ observation_id: "obs_ts_idem_conflict", type: "agent_message" }], { batchId: "trace_ts_idem_conflict", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-trace" });
  service.createArtifactManifest("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json" }] }, { artifactId: "artifact_ts_idem_conflict", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-artifact" });

  const before = service.lifecycleSnapshot("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict");
  const beforeUsage = { ...before.quota.used };
  const beforeAuditCount = before.audit_log.length;
  const beforeUploads = before.uploads.length;
  const beforeTraceBatches = before.trace_batches.length;
  const beforeArtifacts = service.listArtifactManifests("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", { authKeyId: "key_ts_idem_conflict" }).length;
  const beforeRateLimits = service.apiKeyRateLimitSnapshot("tenant_ts_idem_conflict", "project_ts_idem_conflict", { keyId: "key_ts_idem_conflict" }).rate_limits;
  assert.deepEqual(Object.fromEntries(beforeRateLimits.map((bucket) => [bucket.operation, bucket.used])), { "sdk:submit": 1, "run:upload": 1, "trace:ingest": 1, "artifact:upload": 1 });

  assert.throws(
    () => service.sdkSubmitRun("tenant_ts_idem_conflict", "project_ts_idem_conflict", { datasetId: "dataset_ts_idem_conflict", agentRef: "mock", runId: "run_ts_idem_conflict_different", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-submit" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );
  assert.throws(
    () => service.uploadRunResult("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", { status: "failed" }, { uploadId: "upload_ts_idem_conflict_2", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-upload" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );
  assert.throws(
    () => service.ingestTrace("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", [{ observation_id: "obs_ts_idem_conflict_2", type: "tool_call" }], { batchId: "trace_ts_idem_conflict_2", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-trace" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );
  assert.throws(
    () => service.createArtifactManifest("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict_missing", { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "different.json" }] }, { artifactId: "artifact_ts_idem_conflict_2", apiKeyId: "key_ts_idem_conflict", idempotencyKey: "idem-artifact" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );

  const after = service.lifecycleSnapshot("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict");
  assert.deepEqual(after.quota.used, beforeUsage);
  assert.equal(after.audit_log.length, beforeAuditCount);
  assert.equal(after.uploads.length, beforeUploads);
  assert.equal(after.trace_batches.length, beforeTraceBatches);
  assert.equal(service.listArtifactManifests("tenant_ts_idem_conflict", "project_ts_idem_conflict", "run_ts_idem_conflict", { authKeyId: "key_ts_idem_conflict" }).length, beforeArtifacts);
  assert.deepEqual(service.apiKeyRateLimitSnapshot("tenant_ts_idem_conflict", "project_ts_idem_conflict", { keyId: "key_ts_idem_conflict" }).rate_limits, beforeRateLimits);
});

test("TS SaaS router maps local REST-ish ingestion and redacts errors", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_router", projectId: "project_ts_router" });
  service.cloud.createDataset("tenant_ts_router", "project_ts_router", { datasetId: "dataset_ts_router", name: "Dataset", cases: [{ id: "case-1" }] });
  const router = new SaaSControlPlaneRouter(service);
  const body = { tenant_id: "tenant_ts_router" };

  const key = router.handle("POST", "/v1/projects/project_ts_router/api-keys", { ...body, name: "key", scopes: ["sdk:submit", "run:upload", "trace:ingest"], key_id: "key_ts_router" });
  assert.equal(key.status_code, 201);
  const submit = router.handle("POST", "/v1/projects/project_ts_router/sdk-submit", { ...body, api_key_id: "key_ts_router", dataset_id: "dataset_ts_router", agent_ref: "mock", run_id: "run_ts_router", idempotency_key: "idem-router-submit" });
  assert.equal(submit.status_code, 202);
  const upload = router.handle("POST", "/v1/projects/project_ts_router/runs/run_ts_router/upload", { ...body, api_key_id: "key_ts_router", upload_id: "upload_ts_router", result: { status: "completed" } });
  assert.equal(upload.status_code, 202);
  const trace = router.handle("POST", "/v1/projects/project_ts_router/runs/run_ts_router/trace-events", { ...body, api_key_id: "key_ts_router", batch_id: "trace_ts_router", observations: [{ observation_id: "obs_ts_router" }] });
  assert.equal(trace.status_code, 202);
  const lifecycle = router.handle("GET", "/v1/projects/project_ts_router/runs/run_ts_router/lifecycle", body);
  assert.equal(lifecycle.status_code, 200);
  assert.equal(lifecycle.body.quota.used["trace.ingest"], 1);
  assert.equal(JSON.stringify(lifecycle).includes("secret_hash_sha256"), false);

  service.revokeApiKey("tenant_ts_router", "project_ts_router", "key_ts_router");
  const blocked = router.handle("POST", "/v1/projects/project_ts_router/sdk-submit", { ...body, api_key_id: "key_ts_router", dataset_id: "dataset_ts_router", agent_ref: "mock", run_id: "blocked" });
  assert.equal(blocked.status_code, 400);
});

test("TS SaaS router exposes healthz and OpenAPI helper", async () => {
  const router = new SaaSControlPlaneRouter();
  const health = router.handle("GET", "/healthz");
  assert.equal(health.status_code, 200);
  assert.equal(health.body.status, "ok");
  assert.equal(health.body.ashr_api_used, false);
  assert.equal(health.body.openapi_path, "/openapi.json");
  assert.equal(health.body.legacy_openapi_path, "/healthz/openapi");

  const openapi = router.handle("GET", "/healthz/openapi");
  assert.equal(openapi.status_code, 200);
  assert.equal(openapi.body.openapi, "3.0.3");
  assert.ok(openapi.body.paths["/v1/projects/{project_id}/sdk-submit"]);
  assert.ok(openapi.body.paths["/healthz/openapi"]);

  const localClient = new SaaSIngestionClient();
  const localSpec = await localClient.openApi({ serverUrl: "http://unit.test" });
  assert.equal(localSpec.servers[0].url, "http://unit.test");
});

test("TS SaaS ingestion client can call baseUrl JSON transport", async () => {
  const { createServer } = await import("node:http");
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_http", projectId: "project_ts_http" });
  service.cloud.createDataset("tenant_ts_http", "project_ts_http", { datasetId: "dataset_ts_http", name: "Dataset", cases: [{ id: "case-1" }] });
  const router = new SaaSControlPlaneRouter(service);

  const server = createServer((req, res) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      const body = raw ? JSON.parse(raw) : Object.fromEntries(url.searchParams.entries());
      const routed = router.handle(req.method ?? "GET", url.pathname, body);
      res.statusCode = routed.status_code;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(routed.body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    const baseUrl = `http://127.0.0.1:${address.port}`;
    const client = SaaSIngestionClient.forBaseUrl(baseUrl);

    const health = await client.healthz();
    assert.equal(health.status, "ok");

    const spec = await client.openApi();
    assert.equal(spec.openapi, "3.0.3");

    const key = await client.createApiKeyHttp("tenant_ts_http", "project_ts_http", { name: "ingester", scopes: ["sdk:submit", "run:upload", "trace:ingest"], keyId: "key_ts_http" });
    assert.equal(key.result.key_id, "key_ts_http");
    assert.equal(JSON.stringify(key).includes("secret_hash_sha256"), false);

    const submitted = await client.sdkSubmitHttp("tenant_ts_http", "project_ts_http", { datasetId: "dataset_ts_http", agentRef: "mock", runId: "run_ts_http", apiKeyId: "key_ts_http" });
    assert.equal(submitted.result.run.run_id, "run_ts_http");

    const upload = await client.uploadRunHttp("tenant_ts_http", "project_ts_http", "run_ts_http", { status: "completed", api_key: "tp_should_not_leak" }, { uploadId: "upload_ts_http", apiKeyId: "key_ts_http" });
    assert.equal(upload.result.upload_id, "upload_ts_http");
    assert.equal(JSON.stringify(upload).includes("tp_should_not_leak"), false);

    const trace = await client.ingestTraceHttp("tenant_ts_http", "project_ts_http", "run_ts_http", [{ observation_id: "obs_ts_http" }], { batchId: "trace_ts_http", apiKeyId: "key_ts_http" });
    assert.deepEqual(trace.result.observation_ids, ["obs_ts_http"]);

    const lifecycle = await client.lifecycleHttp("tenant_ts_http", "project_ts_http", "run_ts_http");
    assert.equal(lifecycle.result.quota.used["trace.ingest"], 1);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});


test("TS SaaS artifact manifests and usage parity are redacted and idempotent", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_artifact", projectId: "project_ts_artifact" });
  service.cloud.createDataset("tenant_ts_artifact", "project_ts_artifact", { datasetId: "dataset_ts_artifact", name: "Dataset", cases: [{ id: "case-1" }] });
  service.createApiKey("tenant_ts_artifact", "project_ts_artifact", { name: "artifact-writer", scopes: ["sdk:submit", "artifact:write", "evidence:read", "usage:read"], keyId: "key_ts_artifact" });
  service.sdkSubmitRun("tenant_ts_artifact", "project_ts_artifact", { datasetId: "dataset_ts_artifact", agentRef: "mock", runId: "run_ts_artifact", apiKeyId: "key_ts_artifact" });

  const manifest = service.createArtifactManifest(
    "tenant_ts_artifact",
    "project_ts_artifact",
    "run_ts_artifact",
    { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json", api_key: "tp_should_not_leak" }] },
    { artifactId: "artifact_ts", apiKeyId: "key_ts_artifact", idempotencyKey: "artifact-idem" },
  );
  const replay = service.createArtifactManifest(
    "tenant_ts_artifact",
    "project_ts_artifact",
    "run_ts_artifact",
    { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json", api_key: "tp_should_not_leak" }] },
    { artifactId: "artifact_ts", apiKeyId: "key_ts_artifact", idempotencyKey: "artifact-idem", requestId: "artifact-retry" },
  );
  assert.throws(
    () => service.createArtifactManifest(
      "tenant_ts_artifact",
      "project_ts_artifact",
      "run_ts_artifact",
      { schema_version: "ashr.clone.artifact_manifest.v1", files: [{ name: "trace.json", api_key: "different" }] },
      { artifactId: "artifact_ts_again", apiKeyId: "key_ts_artifact", idempotencyKey: "artifact-idem" },
    ),
    /idempotency key conflict.*request fingerprint mismatch/,
  );

  assert.equal(manifest.artifact_id, "artifact_ts");
  assert.equal(manifest.raw_manifest_included, false);
  assert.equal(replay.idempotent_replay, true);
  assert.equal(replay.artifact_id, "artifact_ts");
  assert.equal(JSON.stringify(manifest).includes("tp_should_not_leak"), false);

  const listed = service.listArtifactManifests("tenant_ts_artifact", "project_ts_artifact", "run_ts_artifact", { authKeyId: "key_ts_artifact" });
  assert.equal(listed.length, 1);
  const usage = service.usageSnapshot("tenant_ts_artifact", "project_ts_artifact", { authKeyId: "key_ts_artifact" });
  assert.equal(usage.totals["artifact.manifest"], 1);
});

test("TS SaaS CLI covers API key reveal verify and rate-limit parity", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "ashr-ts-saas-cli-"));
  try {
    const inputState = join(tempDir, "state-input.json");
    const stateAfterCreate = join(tempDir, "state-create.json");
    const stateAfterRate = join(tempDir, "state-rate.json");
    const service = new SaaSControlPlaneService();
    service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_cli", projectId: "project_ts_cli" });
    await writeFile(inputState, `${JSON.stringify(service.snapshotState(), null, 2)}\n`, "utf8");

    const created = runSaasCli([
      "--state-input", inputState,
      "--state-output", stateAfterCreate,
      "api-key-create",
      "--tenant-id", "tenant_ts_cli",
      "--project-id", "project_ts_cli",
      "--name", "cli key",
      "--scope", "sdk:submit",
      "--scope", "run:upload",
      "--key-id", "key_ts_cli",
      "--reveal-secret",
    ]);
    assert.equal(created.operation, "create_api_key");
    assert.equal(created.result.key_id, "key_ts_cli");
    assert.equal(created.result.secret_value_present, true);
    assert.equal(created.result.one_time_secret_displayed, true);
    assert.equal(JSON.stringify(created).includes("secret_hash_sha256"), false);
    const secret = created.result.one_time_secret;
    assert.equal(typeof secret, "string");
    assert.equal(secret.startsWith("ashr_local_key_ts_cli_"), true);

    const listed = runSaasCli([
      "--state-input", stateAfterCreate,
      "api-key-list",
      "--tenant-id", "tenant_ts_cli",
      "--project-id", "project_ts_cli",
    ]);
    assert.equal(listed.operation, "list_api_keys");
    assert.equal(listed.result.api_keys[0].secret_value_present, false);
    assert.equal(JSON.stringify(listed).includes(secret), false);
    assert.equal(JSON.stringify(listed).includes("secret_hash_sha256"), false);

    const verified = runSaasCli([
      "--state-input", stateAfterCreate,
      "api-key-verify",
      "--tenant-id", "tenant_ts_cli",
      "--project-id", "project_ts_cli",
      "--key-id", "key_ts_cli",
      "--secret", secret,
      "--scope", "sdk:submit",
    ]);
    assert.equal(verified.operation, "verify_api_key_secret");
    assert.equal(verified.result.authenticated, true);
    assert.equal(verified.result.secret_value_present, false);

    const bucket = runSaasCli([
      "--state-input", stateAfterCreate,
      "--state-output", stateAfterRate,
      "api-key-rate-limit",
      "--tenant-id", "tenant_ts_cli",
      "--project-id", "project_ts_cli",
      "--key-id", "key_ts_cli",
      "--operation", "sdk:submit",
      "--limit", "3",
      "--period", "minute",
    ]);
    assert.equal(bucket.operation, "configure_api_key_rate_limit");
    assert.equal(bucket.result.operation, "sdk:submit");
    assert.equal(bucket.result.limit, 3);
    assert.equal(bucket.result.period, "minute");

    const snapshot = runSaasCli([
      "--state-input", stateAfterRate,
      "api-key-rate-limits",
      "--tenant-id", "tenant_ts_cli",
      "--project-id", "project_ts_cli",
    ]);
    assert.equal(snapshot.operation, "api_key_rate_limit_snapshot");
    assert.equal(snapshot.result.rate_limits.length, 1);
    assert.equal(snapshot.result.rate_limits[0].key_id, "key_ts_cli");
    assert.equal(snapshot.result.rate_limits[0].remaining, 3);

    const persisted = JSON.parse(await readFile(stateAfterRate, "utf8"));
    assert.equal(Object.keys(persisted.control_plane.api_key_rate_limits).length, 1);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

function runSaasCli(args) {
  const child = spawnSync(process.execPath, ["dist/saas.js", ...args], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });
  assert.equal(child.status, 0, child.stderr || child.stdout);
  return JSON.parse(child.stdout);
}
