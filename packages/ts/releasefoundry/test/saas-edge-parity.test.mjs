import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ADMIN_ALL_SCOPE,
  SaaSControlPlaneRouter,
  SaaSControlPlaneService,
  SaaSHttpJsonTransport,
  SaaSIngestionClient,
  SecretInputError,
  exportSaaSOpenApiSpec,
  runSaaSCli,
  saasHealthz,
} from "../dist/saas.js";

function service() {
  const item = new SaaSControlPlaneService();
  item.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_edge", projectId: "project_edge" });
  item.cloud.createDataset("tenant_edge", "project_edge", { datasetId: "dataset_edge", name: "Dataset", cases: [{ id: "case-1", prompt: "hi" }] });
  return item;
}

function withRun() {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "all", scopes: [ADMIN_ALL_SCOPE], keyId: "key_all" });
  item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_edge", apiKeyId: "key_all" });
  return item;
}

test("TS SaaS admin all scope can submit runs", () => {
  const item = withRun();
  assert.equal(item.lifecycleSnapshot("tenant_edge", "project_edge", "run_edge").run_id, "run_edge");
});

test("TS SaaS write:runs alias can submit and upload", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "writer", scopes: ["write:runs"], keyId: "key_write" });
  item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_write", apiKeyId: "key_write" });
  const upload = item.uploadRunResult("tenant_edge", "project_edge", "run_write", { status: "completed" }, { apiKeyId: "key_write" });
  assert.equal(upload.status, "uploaded");
});

test("TS SaaS traces:write alias can ingest trace", () => {
  const item = withRun();
  item.createApiKey("tenant_edge", "project_edge", { name: "trace", scopes: ["traces:write"], keyId: "key_trace" });
  const trace = item.ingestTrace("tenant_edge", "project_edge", "run_edge", [{ observation_id: "obs" }], { apiKeyId: "key_trace" });
  assert.equal(trace.observation_count, 1);
});

test("TS SaaS artifact:write alias can create manifests", () => {
  const item = withRun();
  item.createApiKey("tenant_edge", "project_edge", { name: "artifact", scopes: ["artifact:write"], keyId: "key_artifact" });
  const artifact = item.createArtifactManifest("tenant_edge", "project_edge", "run_edge", { schema_version: "x" }, { apiKeyId: "key_artifact" });
  assert.equal(artifact.raw_manifest_included, false);
});

test("TS SaaS key admin alias can create another key", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "admin", scopes: ["key:admin"], keyId: "key_admin" });
  const created = item.createApiKey("tenant_edge", "project_edge", { name: "child", scopes: ["sdk:submit"], keyId: "key_child", authKeyId: "key_admin" });
  assert.equal(created.key_id, "key_child");
});

test("TS SaaS key read alias can list keys", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "reader", scopes: ["key:read"], keyId: "key_reader" });
  assert.equal(item.listApiKeys("tenant_edge", "project_edge", { authKeyId: "key_reader" }).length, 1);
});

test("TS SaaS denied scope blocks upload", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "submit", scopes: ["sdk:submit"], keyId: "key_submit" });
  item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_submit", apiKeyId: "key_submit" });
  assert.throws(() => item.uploadRunResult("tenant_edge", "project_edge", "run_submit", { status: "completed" }, { apiKeyId: "key_submit" }), /missing required scope/);
});

test("TS SaaS revoked key cannot authenticate", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "revoked", scopes: ["sdk:submit"], keyId: "key_revoked" });
  item.revokeApiKey("tenant_edge", "project_edge", "key_revoked");
  assert.throws(() => item.authenticateApiKey("tenant_edge", "project_edge", { keyId: "key_revoked", scope: "sdk:submit" }), /not active/);
});

test("TS SaaS revoked key cannot verify secret", () => {
  const item = service();
  const key = item.createApiKey("tenant_edge", "project_edge", { name: "revoked", scopes: ["sdk:submit"], keyId: "key_revoked_secret", revealSecret: true });
  item.revokeApiKey("tenant_edge", "project_edge", "key_revoked_secret");
  assert.throws(() => item.verifyApiKeySecret("tenant_edge", "project_edge", { keyId: "key_revoked_secret", secret: String(key.one_time_secret) }), /not active/);
});

test("TS SaaS wrong secret is rejected", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "secret", scopes: ["sdk:submit"], keyId: "key_secret", revealSecret: true });
  assert.throws(() => item.verifyApiKeySecret("tenant_edge", "project_edge", { keyId: "key_secret", secret: "wrong" }), /verification failed/);
});

test("TS SaaS idempotent submit does not double consume usage", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "all", scopes: [ADMIN_ALL_SCOPE], keyId: "key_all" });
  item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_idem", idempotencyKey: "idem" });
  const replay = item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_idem", idempotencyKey: "idem", requestId: "retry" });
  assert.equal(replay.idempotent_replay, true);
  assert.throws(
    () => item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_other", idempotencyKey: "idem" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );
  assert.equal(item.usageSnapshot("tenant_edge", "project_edge", { authKeyId: "key_all" }).totals["sdk.submit"], 1);
});

test("TS SaaS idempotent upload replays original upload id", () => {
  const item = withRun();
  const first = item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "completed" }, { uploadId: "u1", idempotencyKey: "u-idem" });
  const second = item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "completed" }, { uploadId: "u1", idempotencyKey: "u-idem", requestId: "retry" });
  assert.equal(second.idempotent_replay, true);
  assert.equal(second.upload_id, first.upload_id);
  assert.throws(
    () => item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "failed" }, { uploadId: "u2", idempotencyKey: "u-idem" }),
    /idempotency key conflict.*request fingerprint mismatch/,
  );
});

test("TS SaaS trace ingestion rejects empty observations", () => {
  const item = withRun();
  assert.throws(() => item.ingestTrace("tenant_edge", "project_edge", "run_edge", []), /at least one observation/);
});

test("TS SaaS rate limit rejects non-positive limits", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "key", scopes: ["sdk:submit"], keyId: "key_rate" });
  assert.throws(() => item.configureApiKeyRateLimit("tenant_edge", "project_edge", { keyId: "key_rate", operation: "sdk:submit", limit: 0 }), /positive/);
});

test("TS SaaS rate limit usage persists after snapshot restore", () => {
  const item = service();
  item.createApiKey("tenant_edge", "project_edge", { name: "key", scopes: ["sdk:submit"], keyId: "key_rate_state" });
  item.configureApiKeyRateLimit("tenant_edge", "project_edge", { keyId: "key_rate_state", operation: "sdk:submit", limit: 2 });
  item.sdkSubmitRun("tenant_edge", "project_edge", { datasetId: "dataset_edge", agentRef: "mock", runId: "run_rate_state", apiKeyId: "key_rate_state" });
  const restored = SaaSControlPlaneService.fromState(item.snapshotState());
  assert.equal(restored.apiKeyRateLimitSnapshot("tenant_edge", "project_edge", { keyId: "key_rate_state" }).rate_limits[0].remaining, 1);
});

test("TS SaaS snapshot integrity is a sha256 digest", () => {
  assert.match(service().snapshotState().integrity.payload_sha256, /^[a-f0-9]{64}$/);
});

test("TS SaaS state rejects unsupported schema version", () => {
  const state = service().snapshotState();
  state.state_schema_version = 99;
  assert.throws(() => SaaSControlPlaneService.fromState(state), /unsupported/);
});

test("TS SaaS state rejects malformed bucket records", () => {
  const state = service().snapshotState();
  state.control_plane.api_keys.bad = "not-object";
  assert.throws(() => SaaSControlPlaneService.fromState(state), /records must be objects/);
});

test("TS SaaS client rejects raw apiKey option", () => {
  assert.throws(() => new SaaSIngestionClient({ service: service() }).createApiKey("tenant_edge", "project_edge", { name: "bad", scopes: [], apiKey: "tp_should_not_accept" }), SecretInputError);
});

test("TS SaaS CLI rejects raw positional arguments", async () => {
  await assert.rejects(() => runSaaSCli(["bad-positional"]), /unexpected argument/);
});

test("TS SaaS CLI rejects missing numeric option", async () => {
  await assert.rejects(() => runSaaSCli(["api-key-rate-limit", "--tenant-id", "t", "--project-id", "p", "--key-id", "k", "--operation", "x"]), /missing required --limit/);
});

test("TS SaaS CLI rejects nonnumeric release gate threshold", async () => {
  await assert.rejects(() => runSaaSCli(["release-gate", "--tenant-id", "t", "--project-id", "p", "--run-id", "r", "--min-score", "nope"]), /numeric/);
});

test("TS SaaS health advertises local-only no ReleaseFoundry API", () => {
  const health = saasHealthz();
  assert.equal(health.local_only, true);
  assert.equal(health.releasefoundry_api_used, false);
});

test("TS SaaS OpenAPI has no secret hash field", () => {
  assert.equal(JSON.stringify(exportSaaSOpenApiSpec()).includes("secret_hash_sha256"), false);
});

test("TS SaaS router unsupported route returns validation error", () => {
  const result = new SaaSControlPlaneRouter(service()).handle("GET", "/v1/projects/project_edge/unknown", { tenant_id: "tenant_edge" });
  assert.equal(result.status_code, 400);
  assert.equal(result.body.error.code, "validation_error");
});

test("TS SaaS router not-found run returns 404", () => {
  const result = new SaaSControlPlaneRouter(service()).handle("GET", "/v1/projects/project_edge/runs/missing/lifecycle", { tenant_id: "tenant_edge" });
  assert.equal(result.status_code, 404);
});

test("TS SaaS router create key reveal is redacted by default", () => {
  const result = new SaaSControlPlaneRouter(service()).handle("POST", "/v1/projects/project_edge/api-keys", { tenant_id: "tenant_edge", name: "key", scopes: ["sdk:submit"], key_id: "key_router" });
  assert.equal(result.body.secret_value_present, false);
  assert.equal(JSON.stringify(result).includes("secret_hash_sha256"), false);
});

test("TS SaaS router create key can reveal one-time secret", () => {
  const result = new SaaSControlPlaneRouter(service()).handle("POST", "/v1/projects/project_edge/api-keys", { tenant_id: "tenant_edge", name: "key", scopes: ["sdk:submit"], key_id: "key_router_reveal", reveal_secret: true });
  assert.equal(result.body.secret_value_present, true);
  assert.equal(String(result.body.one_time_secret).startsWith("releasefoundry_local_key_router_reveal_"), true);
});

test("TS SaaS audit log can filter by action prefix", () => {
  const item = withRun();
  item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "completed" });
  const audit = item.auditSnapshot("tenant_edge", "project_edge", { actionPrefix: "run." });
  assert.equal(audit.events.every((event) => String(event.action).startsWith("run.")), true);
});

test("TS SaaS release evidence packet includes audit hash", () => {
  const item = withRun();
  item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "completed" });
  item.ingestTrace("tenant_edge", "project_edge", "run_edge", [{ observation_id: "obs" }]);
  const packet = item.buildReleaseEvidencePacket("tenant_edge", "project_edge", "run_edge", { authKeyId: "key_all" });
  assert.match(packet.hashes.audit_sha256, /^[a-f0-9]{64}$/);
});

test("TS SaaS release evidence packet redacts raw payloads", () => {
  const item = withRun();
  item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { api_key: "tp_should_not_leak" });
  const packet = item.buildReleaseEvidencePacket("tenant_edge", "project_edge", "run_edge", { authKeyId: "key_all" });
  assert.equal(JSON.stringify(packet).includes("tp_should_not_leak"), false);
});

test("TS SaaS release gate custom evaluator is preserved", () => {
  const item = withRun();
  const gate = item.evaluateReleaseGate("tenant_edge", "project_edge", "run_edge", { evaluator: "enterprise-policy" });
  assert.equal(gate.evaluator, "enterprise-policy");
});

test("TS SaaS list artifact manifests can filter by run", () => {
  const item = withRun();
  item.createArtifactManifest("tenant_edge", "project_edge", "run_edge", { schema_version: "x" }, { artifactId: "a1", apiKeyId: "key_all" });
  assert.equal(item.listArtifactManifests("tenant_edge", "project_edge", "run_edge", { authKeyId: "key_all" }).length, 1);
  assert.equal(item.listArtifactManifests("tenant_edge", "project_edge", "other", { authKeyId: "key_all" }).length, 0);
});

test("TS SaaS usage snapshot totals multiple operations", () => {
  const item = withRun();
  item.uploadRunResult("tenant_edge", "project_edge", "run_edge", { status: "completed" });
  item.ingestTrace("tenant_edge", "project_edge", "run_edge", [{ observation_id: "obs" }]);
  const totals = item.usageSnapshot("tenant_edge", "project_edge", { authKeyId: "key_all" }).totals;
  assert.equal(totals["sdk.submit"], 1);
  assert.equal(totals["run.upload"], 1);
  assert.equal(totals["trace.ingest"], 1);
});

test("TS SaaS HTTP transport rejects non-object JSON", async () => {
  const transport = new SaaSHttpJsonTransport({ baseUrl: "http://example.test", fetch: async () => ({ ok: true, status: 200, async json() { return []; }, async text() { return "[]"; } }) });
  await assert.rejects(() => transport.requestJson("GET", "/healthz"), /must be a JSON object/);
});

test("TS SaaS HTTP transport maps error body message", async () => {
  const transport = new SaaSHttpJsonTransport({ baseUrl: "http://example.test", fetch: async () => ({ ok: false, status: 400, async json() { return { error: { message: "blocked" } }; }, async text() { return "blocked"; } }) });
  await assert.rejects(() => transport.requestJson("GET", "/healthz"), /blocked/);
});

test("TS SaaS HTTP transport sends GET params through query", async () => {
  const seen = [];
  const transport = new SaaSHttpJsonTransport({ baseUrl: "http://example.test", fetch: async (url) => { seen.push(String(url)); return { ok: true, status: 200, async json() { return { ok: true }; }, async text() { return "{}"; } }; } });
  await transport.requestJson("GET", "/audit-log", { tenant_id: "tenant_edge", limit: 3 });
  assert.equal(seen[0].includes("tenant_id=tenant_edge"), true);
  assert.equal(seen[0].includes("limit=3"), true);
});

test("TS SaaS HTTP transport sends POST JSON body", async () => {
  const seen = [];
  const transport = new SaaSHttpJsonTransport({ baseUrl: "http://example.test", fetch: async (_url, init) => { seen.push(init); return { ok: true, status: 200, async json() { return { ok: true }; }, async text() { return "{}"; } }; } });
  await transport.requestJson("POST", "/bootstrap", { tenant_id: "tenant_edge" });
  assert.equal(seen[0].headers["content-type"], "application/json");
  assert.equal(JSON.parse(seen[0].body).tenant_id, "tenant_edge");
});

test("TS SaaS client baseUrl constructor stores HTTP transport", () => {
  const client = SaaSIngestionClient.forBaseUrl("http://127.0.0.1:9", { fetch: async () => ({ ok: true, status: 200, async json() { return {}; }, async text() { return "{}"; } }) });
  assert.notEqual(client.transport, undefined);
});

test("TS SaaS hosted billing wrappers keep Python operation and route parity", async () => {
  const calls = [];
  const client = new SaaSIngestionClient({
    transport: {
      async requestJson(method, path, body, options = {}) {
        calls.push({ method, path, body, headers: options.headers ?? {} });
        return { ok: true, method, path };
      },
    },
  });

  const usage = await client.usageSnapshotHttp("tenant_bill", "project_bill", { auth_key_id: "key_usage", bearerApiKey: "Bearer hosted_test_key" });
  const quota = await client.quotaSnapshotHttp("tenant_bill", "project_bill", { auth_key_id: "key_usage" });
  const lifecycle = await client.lifecycleHttp("tenant_bill", "project_bill", "run_bill");

  assert.equal(usage.operation, "usage_snapshot");
  assert.equal(quota.operation, "quota_snapshot");
  assert.equal(lifecycle.operation, "lifecycle_snapshot");
  assert.deepEqual(calls.map((call) => `${call.method} ${call.path}`), [
    "GET /v1/projects/project_bill/usage",
    "GET /v1/projects/project_bill/quota",
    "GET /v1/projects/project_bill/runs/run_bill/lifecycle",
  ]);
  assert.equal(calls[0].body.auth_key_id, "key_usage");
  assert.equal(calls[0].headers.Authorization, "Bearer hosted_test_key");
});
