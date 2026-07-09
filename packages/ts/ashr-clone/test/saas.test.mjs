import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { AGENT_INPUT_PART_TYPES } from "../dist/index.js";
import { SaaSControlPlaneRouter, SaaSControlPlaneService, SaaSIngestionClient, CONTROL_PLANE_SCHEMA_VERSION, buildSafeMediaEnvelope } from "../dist/saas.js";

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

test("TS SaaS ingestion client accepts Python SDK option aliases", () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_alias", projectId: "project_ts_alias" });
  service.cloud.createDataset("tenant_ts_alias", "project_ts_alias", { datasetId: "dataset_ts_alias", name: "Dataset", cases: [{ id: "case-1" }] });
  const client = new SaaSIngestionClient({ service });

  const key = client.createApiKey("tenant_ts_alias", "project_ts_alias", { name: "ingester", scopes: ["sdk:submit", "run:upload", "trace:ingest", "usage:read"], key_id: "key_ts_alias", reveal_secret: true });
  assert.equal(key.result.key_id, "key_ts_alias");
  assert.equal(key.result.secret_value_present, true);
  assert.equal(JSON.stringify(key).includes("secret_hash_sha256"), false);

  const submitted = client.sdkSubmit("tenant_ts_alias", "project_ts_alias", { dataset_id: "dataset_ts_alias", agent_ref: "mock", run_id: "run_ts_alias", api_key_id: "key_ts_alias", idempotency_key: "idem-submit" });
  assert.equal(submitted.result.run.run_id, "run_ts_alias");

  const upload = client.uploadRun("tenant_ts_alias", "project_ts_alias", "run_ts_alias", { status: "completed", api_key: "tp_should_not_leak" }, { upload_id: "upload_ts_alias", api_key_id: "key_ts_alias", request_id: "req-upload" });
  assert.equal(upload.result.upload_id, "upload_ts_alias");
  assert.equal(JSON.stringify(upload).includes("tp_should_not_leak"), false);

  const trace = client.ingestTrace("tenant_ts_alias", "project_ts_alias", "run_ts_alias", [{ observation_id: "obs_ts_alias" }], { batch_id: "trace_ts_alias", api_key_id: "key_ts_alias" });
  assert.deepEqual(trace.result.observation_ids, ["obs_ts_alias"]);

  const quota = client.quotaSnapshot("tenant_ts_alias", "project_ts_alias", { auth_key_id: "key_ts_alias" });
  assert.equal(quota.operation, "quota_snapshot");
  assert.equal(quota.result.totals["sdk.submit"], 1);
  assert.equal(quota.result.quota.used["run.upload"], 1);

  assert.throws(
    () => client.sdkSubmit("tenant_ts_alias", "project_ts_alias", { dataset_id: "dataset_ts_alias", agent_ref: "mock", api_key: "tp_raw" }),
    /raw API key values are not accepted/,
  );
});

test("TS SaaS builds public-safe media envelopes for SDK submit metadata", () => {
  const envelope = buildSafeMediaEnvelope(
    { text: "inspect multimodal fixture" },
    {
      parts: [
        { type: "text", text: "inspect multimodal fixture" },
        { type: "image", url: "https://cdn.example.invalid/image.png", mimeType: "image/png", sha256: "imgsha" },
        { type: "audio", path: "fixtures/audio.wav", mime_type: "audio/wav", sha256: "audiosha" },
        { type: "file", uri: "s3://safe-bucket/report.json", filename: "report.json", mime_type: "application/json" },
        { type: "video", source: "fixtures/video.mp4", mime_type: "video/mp4", description: "short fixture" },
      ],
      metadata: { request_id: "req-media", fixture: true },
    },
  );

  assert.equal(envelope.schema_version, CONTROL_PLANE_SCHEMA_VERSION);
  assert.equal(envelope.raw_payload_included, false);
  assert.equal(envelope.secret_value_present, false);
  assert.deepEqual(envelope.parts.map((part) => part.type), AGENT_INPUT_PART_TYPES);
  assert.equal(envelope.parts[1].mime_type, "image/png");
  assert.equal(envelope.parts[3].url, "s3://safe-bucket/report.json");
  assert.equal(envelope.parts[3].name, "report.json");
  assert.equal(envelope.parts[4].path, "fixtures/video.mp4");
  assert.equal(JSON.stringify(envelope).includes("mimeType"), false);
  assert.equal(JSON.stringify(envelope).includes("filename"), false);

  assert.throws(
    () => buildSafeMediaEnvelope("bad", { parts: [{ type: "image", url: "https://cdn.example.invalid/image.png?token=abc" }] }),
    /unsafe media envelope fields are not accepted: parts\[0\]\.url/,
  );
  assert.throws(
    () => buildSafeMediaEnvelope("bad", { parts: [{ type: "audio", base64: "c2VjcmV0" }] }),
    /unsafe media envelope fields are not accepted: parts\[0\]\.base64/,
  );
  assert.throws(
    () => buildSafeMediaEnvelope("bad", { metadata: { api_key: "tp_should_not_leak" } }),
    /unsafe media envelope fields are not accepted: metadata\.api_key/,
  );
  assert.throws(
    () => buildSafeMediaEnvelope({ text: "bad", raw_payload: { api_key: "tp_should_not_leak" } }),
    /unsafe media envelope fields are not accepted: raw_payload/,
  );
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

    const key = await client.createApiKeyHttp("tenant_ts_http", "project_ts_http", { name: "ingester", scopes: ["sdk:submit", "run:upload", "trace:ingest", "usage:read"], keyId: "key_ts_http" });
    assert.equal(key.result.key_id, "key_ts_http");
    assert.equal(JSON.stringify(key).includes("secret_hash_sha256"), false);

    const submitted = await client.sdkSubmitHttp("tenant_ts_http", "project_ts_http", { dataset_id: "dataset_ts_http", agent_ref: "mock", run_id: "run_ts_http", api_key_id: "key_ts_http" });
    assert.equal(submitted.result.run.run_id, "run_ts_http");

    const upload = await client.uploadRunHttp("tenant_ts_http", "project_ts_http", "run_ts_http", { status: "completed", api_key: "tp_should_not_leak" }, { upload_id: "upload_ts_http", api_key_id: "key_ts_http" });
    assert.equal(upload.result.upload_id, "upload_ts_http");
    assert.equal(JSON.stringify(upload).includes("tp_should_not_leak"), false);

    const trace = await client.ingestTraceHttp("tenant_ts_http", "project_ts_http", "run_ts_http", [{ observation_id: "obs_ts_http" }], { batch_id: "trace_ts_http", api_key_id: "key_ts_http" });
    assert.deepEqual(trace.result.observation_ids, ["obs_ts_http"]);

    const lifecycle = await client.lifecycleHttp("tenant_ts_http", "project_ts_http", "run_ts_http");
    assert.equal(lifecycle.result.quota.used["trace.ingest"], 1);

    const quota = await client.quotaSnapshotHttp("tenant_ts_http", "project_ts_http", { auth_key_id: "key_ts_http" });
    assert.equal(quota.operation, "quota_snapshot");
    assert.equal(quota.result.totals["trace.ingest"], 1);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("TS SaaS HTTP client sends Bearer API key auth for protected ingestion routes", async () => {
  const { createServer } = await import("node:http");
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_bearer", projectId: "project_ts_bearer" });
  service.cloud.createDataset("tenant_ts_bearer", "project_ts_bearer", { datasetId: "dataset_ts_bearer", name: "Dataset", cases: [{ id: "case-1" }] });
  const created = service.createApiKey("tenant_ts_bearer", "project_ts_bearer", { name: "bearer", scopes: ["sdk:submit", "run:upload", "trace:ingest", "artifact:write", "usage:read", "evidence:read"], keyId: "key_ts_bearer", revealSecret: true });
  const secret = created.one_time_secret;
  const router = new SaaSControlPlaneRouter(service);
  const seen = [];

  const server = createServer((req, res) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      const body = raw ? JSON.parse(raw) : Object.fromEntries(url.searchParams.entries());
      seen.push({ method: req.method, path: url.pathname, authorization: req.headers.authorization, body });
      const routed = router.handle(req.method ?? "GET", url.pathname, body, { headers: req.headers });
      res.statusCode = routed.status_code;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(routed.body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    const client = SaaSIngestionClient.forBaseUrl(`http://127.0.0.1:${address.port}`);
    await client.sdkSubmitHttp("tenant_ts_bearer", "project_ts_bearer", { dataset_id: "dataset_ts_bearer", agent_ref: "mock", run_id: "run_ts_bearer", bearerApiKey: secret });
    await client.uploadRunHttp("tenant_ts_bearer", "project_ts_bearer", "run_ts_bearer", { status: "completed", api_key: "tp_should_not_leak" }, { upload_id: "upload_ts_bearer", bearerApiKey: secret });
    await client.ingestTraceHttp("tenant_ts_bearer", "project_ts_bearer", "run_ts_bearer", [{ observation_id: "obs_ts_bearer" }], { batch_id: "trace_ts_bearer", bearerApiKey: secret });
    await client.createArtifactManifestHttp("tenant_ts_bearer", "project_ts_bearer", "run_ts_bearer", { files: [{ name: "trace.json", authorization: "Bearer should-redact" }] }, { artifactId: "artifact_ts_bearer", bearerApiKey: secret });
    const listed = await client.listArtifactManifestsHttp("tenant_ts_bearer", "project_ts_bearer", "run_ts_bearer", { bearerApiKey: secret });
    const usage = await client.usageHttp("tenant_ts_bearer", "project_ts_bearer", { bearerApiKey: secret });
    const quota = await client.quotaSnapshotHttp("tenant_ts_bearer", "project_ts_bearer", { bearerApiKey: secret });

    assert.equal(listed.result.artifact_manifests.length, 1);
    assert.equal(usage.result.totals["trace.ingest"], 1);
    assert.equal(quota.result.totals["artifact.manifest"], 1);
    assert.equal(seen.every((call) => call.authorization === `Bearer ${secret}`), true);
    assert.equal(seen.every((call) => call.body.api_key_id === undefined && call.body.auth_key_id === undefined), true);
    assert.equal(JSON.stringify([listed, usage, quota]).includes(secret), false);
    assert.equal(JSON.stringify([listed, usage, quota]).includes("tp_should_not_leak"), false);
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

test("TS SaaS worker jobs lease retry dead-letter and redact payloads", () => {
  const client = new SaaSIngestionClient();
  client.bootstrapProject({ tenantName: "Worker Tenant", projectName: "Worker Project", tenantId: "tenant_ts_worker", projectId: "project_ts_worker", datasetId: "dataset_ts_worker" });
  client.sdkSubmit("tenant_ts_worker", "project_ts_worker", { dataset_id: "dataset_ts_worker", agent_ref: "mock", run_id: "run_ts_worker" });

  const enqueued = client.enqueueWorkerJob("tenant_ts_worker", "project_ts_worker", {
    job_type: "run.replay",
    target_id: "run_ts_worker",
    job_id: "job_ts_worker",
    priority: 3,
    max_attempts: 2,
    idempotency_key: "idem-ts-worker",
    payload: { run_id: "run_ts_worker", secret: "must-not-leak" },
  });
  const replay = client.enqueueWorkerJob("tenant_ts_worker", "project_ts_worker", {
    job_type: "run.replay",
    target_id: "run_ts_worker",
    job_id: "job_ts_worker",
    priority: 3,
    max_attempts: 2,
    idempotency_key: "idem-ts-worker",
    payload: { run_id: "run_ts_worker", secret: "must-not-leak" },
  });
  assert.equal(enqueued.result.raw_payload_included, false);
  assert.equal(JSON.stringify(enqueued).includes("must-not-leak"), false);
  assert.equal(replay.result.idempotent_replay, true);

  const leased = client.leaseWorkerJob("tenant_ts_worker", "project_ts_worker", { lease_owner_id: "worker-a", lease_seconds: 30, job_type: "run.replay" });
  assert.equal(leased.result.leased, true);
  assert.equal(leased.result.job.attempts, 1);
  const heartbeat = client.heartbeatWorkerJob("tenant_ts_worker", "project_ts_worker", "job_ts_worker", { lease_owner_id: "worker-a", lease_seconds: 60 });
  assert.equal(heartbeat.result.status, "leased");
  assert.equal(heartbeat.result.lease_owner_id, "worker-a");
  assert.throws(() => client.completeWorkerJob("tenant_ts_worker", "project_ts_worker", "job_ts_worker", { ok: true }, { lease_owner_id: "worker-b" }), /lease owner mismatch/);

  const failed = client.failWorkerJob("tenant_ts_worker", "project_ts_worker", "job_ts_worker", { type: "TransientError", message: "redacted", raw: "not stored" }, { lease_owner_id: "worker-a", retry_after_seconds: 0 });
  assert.equal(failed.result.status, "retrying");
  assert.equal(failed.result.last_error.raw_payload_included, false);
  const leasedAgain = client.leaseWorkerJob("tenant_ts_worker", "project_ts_worker", { lease_owner_id: "worker-b", lease_seconds: 30 });
  assert.equal(leasedAgain.result.job.attempts, 2);
  const dead = client.failWorkerJob("tenant_ts_worker", "project_ts_worker", "job_ts_worker", { type: "PermanentError" }, { lease_owner_id: "worker-b" });
  assert.equal(dead.result.status, "dead_lettered");
  assert.equal(client.leaseWorkerJob("tenant_ts_worker", "project_ts_worker", { lease_owner_id: "worker-c" }).result.status, "empty");

  const listed = client.listWorkerJobs("tenant_ts_worker", "project_ts_worker", { status: "dead_lettered" });
  assert.equal(listed.result.count, 1);
  assert.equal(listed.result.returned_count, 1);
  assert.equal(listed.result.total_count, 1);
  assert.equal(listed.result.has_more, false);
  assert.equal(listed.result.next_cursor, null);
  assert.equal(listed.result.jobs[0].job_id, "job_ts_worker");
  const used = client.service.cloud.quotaSnapshot("tenant_ts_worker", "project_ts_worker").used;
  assert.equal(used["worker.job.heartbeat"] ?? 0, 0);
  assert.equal(used["worker.job.fail"], 2);
});

test("TS SaaS router HTTP and OpenAPI expose worker job heartbeat parity", async () => {
  const service = new SaaSControlPlaneService();
  service.bootstrapProject({ tenantName: "Worker HTTP", projectName: "Worker HTTP Project", tenantId: "tenant_ts_worker_http", projectId: "project_ts_worker_http" });
  const router = new SaaSControlPlaneRouter(service);

  const spec = router.handle("GET", "/openapi.json");
  assert.equal(spec.status_code, 200);
  assert.equal(spec.body.paths["/v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat"].post.operationId, "heartbeatWorkerJob");
  assert.equal(spec.body.paths["/v1/projects/{project_id}/worker-jobs/enqueue"].post.operationId, "enqueueWorkerJob");

  const enqueued = router.handle("POST", "/v1/projects/project_ts_worker_http/worker-jobs/enqueue", { tenant_id: "tenant_ts_worker_http", job_type: "run.replay", job_id: "job_ts_worker_http", payload: { secret: "must-not-leak" } });
  assert.equal(enqueued.status_code, 202);
  assert.equal(enqueued.body.raw_payload_included, false);
  assert.equal(JSON.stringify(enqueued).includes("must-not-leak"), false);

  const leased = router.handle("POST", "/v1/projects/project_ts_worker_http/worker-jobs/lease", { tenant_id: "tenant_ts_worker_http", lease_owner_id: "worker-http", lease_seconds: 30 });
  assert.equal(leased.status_code, 200);
  assert.equal(leased.body.leased, true);

  const heartbeat = router.handle("POST", "/v1/projects/project_ts_worker_http/worker-jobs/job_ts_worker_http/heartbeat", { tenant_id: "tenant_ts_worker_http", lease_owner_id: "worker-http", lease_seconds: 60 });
  assert.equal(heartbeat.status_code, 200);
  assert.equal(heartbeat.body.status, "leased");
  assert.equal(heartbeat.body.lease_owner_id, "worker-http");

  const list = router.handle("GET", "/v1/projects/project_ts_worker_http/worker-jobs", { tenant_id: "tenant_ts_worker_http", status: "leased" });
  assert.equal(list.status_code, 200);
  assert.equal(list.body.count, 1);
  assert.equal(list.body.returned_count, 1);
  assert.equal(list.body.total_count, 1);
  assert.equal(list.body.has_more, false);
  assert.equal(list.body.next_cursor, null);

  const client = new SaaSIngestionClient({ service });
  const completed = await client.completeWorkerJobHttp("tenant_ts_worker_http", "project_ts_worker_http", "job_ts_worker_http", { ok: true, raw: "still-hashed" }, { lease_owner_id: "worker-http" });
  assert.equal(completed.result.status, "completed");
  assert.equal(JSON.stringify(completed).includes("still-hashed"), false);
});

test("TS SaaS OpenAPI keeps current Go HTTP vertical slice routes", () => {
  const router = new SaaSControlPlaneRouter(new SaaSControlPlaneService());
  const spec = router.handle("GET", "/v1/openapi.json");
  assert.equal(spec.status_code, 200);

  const goRoutes = [
    ["GET", "/healthz"],
    ["GET", "/openapi.json"],
    ["GET", "/v1/openapi.json"],
    ["POST", "/v1/bootstrap"],
    ["POST", "/v1/projects/{project_id}/sdk-submit"],
    ["POST", "/v1/projects/{project_id}/worker-jobs/enqueue"],
    ["POST", "/v1/projects/{project_id}/worker-jobs/lease"],
    ["GET", "/v1/projects/{project_id}/worker-jobs"],
    ["POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat"],
    ["POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/complete"],
    ["POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/fail"],
  ];

  for (const [method, path] of goRoutes) {
    assert.ok(spec.body.paths[path]?.[method.toLowerCase()], `${method} ${path}`);
  }
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

test("TS SaaS CLI covers worker job lifecycle and public-safe state", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "ashr-ts-saas-worker-cli-"));
  try {
    const inputState = join(tempDir, "state-input.json");
    const stateAfterEnqueue = join(tempDir, "state-enqueue.json");
    const stateAfterLease = join(tempDir, "state-lease.json");
    const stateAfterHeartbeat = join(tempDir, "state-heartbeat.json");
    const stateAfterComplete = join(tempDir, "state-complete.json");
    const service = new SaaSControlPlaneService();
    service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_cli_worker", projectId: "project_ts_cli_worker" });
    await writeFile(inputState, `${JSON.stringify(service.snapshotState(), null, 2)}\n`, "utf8");

    const enqueued = runSaasCli([
      "--state-input", inputState,
      "--state-output", stateAfterEnqueue,
      "job-enqueue",
      "--tenant-id", "tenant_ts_cli_worker",
      "--project-id", "project_ts_cli_worker",
      "--job-type", "run.replay",
      "--job-id", "job_ts_cli_worker",
      "--payload-json", "{\"secret\":\"must-not-leak\"}",
      "--max-attempts", "2",
    ]);
    assert.equal(enqueued.operation, "worker_job_enqueue");
    assert.equal(enqueued.result.raw_payload_included, false);
    assert.equal(JSON.stringify(enqueued).includes("must-not-leak"), false);

    const leased = runSaasCli([
      "--state-input", stateAfterEnqueue,
      "--state-output", stateAfterLease,
      "job-lease",
      "--tenant-id", "tenant_ts_cli_worker",
      "--project-id", "project_ts_cli_worker",
      "--lease-owner-id", "worker-cli",
      "--lease-seconds", "30",
    ]);
    assert.equal(leased.operation, "worker_job_lease");
    assert.equal(leased.result.job.job_id, "job_ts_cli_worker");

    const heartbeat = runSaasCli([
      "--state-input", stateAfterLease,
      "--state-output", stateAfterHeartbeat,
      "job-heartbeat",
      "--tenant-id", "tenant_ts_cli_worker",
      "--project-id", "project_ts_cli_worker",
      "--job-id", "job_ts_cli_worker",
      "--lease-owner-id", "worker-cli",
      "--lease-seconds", "60",
    ]);
    assert.equal(heartbeat.operation, "worker_job_heartbeat");
    assert.equal(heartbeat.result.status, "leased");

    const completed = runSaasCli([
      "--state-input", stateAfterHeartbeat,
      "--state-output", stateAfterComplete,
      "job-complete",
      "--tenant-id", "tenant_ts_cli_worker",
      "--project-id", "project_ts_cli_worker",
      "--job-id", "job_ts_cli_worker",
      "--lease-owner-id", "worker-cli",
      "--result-json", "{\"raw\":\"do-not-store\"}",
    ]);
    assert.equal(completed.operation, "worker_job_complete");
    assert.equal(completed.result.status, "completed");
    assert.equal(JSON.stringify(completed).includes("do-not-store"), false);

    const listed = runSaasCli([
      "--state-input", stateAfterComplete,
      "job-list",
      "--tenant-id", "tenant_ts_cli_worker",
      "--project-id", "project_ts_cli_worker",
      "--status", "completed",
    ]);
    assert.equal(listed.operation, "worker_jobs");
    assert.equal(listed.result.count, 1);
    assert.equal(listed.result.returned_count, 1);
    assert.equal(listed.result.total_count, 1);
    assert.equal(listed.result.has_more, false);
    assert.equal(listed.result.next_cursor, null);
    assert.equal(listed.result.jobs[0].result_sha256.length, 64);

    const persisted = JSON.parse(await readFile(stateAfterComplete, "utf8"));
    assert.equal(persisted.control_plane.worker_jobs.job_ts_cli_worker.raw_payload_included, false);
    assert.equal(JSON.stringify(persisted).includes("must-not-leak"), false);
    assert.equal(JSON.stringify(persisted).includes("do-not-store"), false);
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
