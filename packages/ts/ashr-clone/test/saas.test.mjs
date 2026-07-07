import assert from "node:assert/strict";
import { test } from "node:test";
import { SaaSControlPlaneRouter, SaaSControlPlaneService, CONTROL_PLANE_SCHEMA_VERSION } from "../dist/saas.js";

test("TS SaaS control plane covers key submit upload trace lifecycle idempotency", async () => {
  const service = new SaaSControlPlaneService();
  const boot = service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_saas", projectId: "project_ts_saas" });
  service.cloud.createDataset("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", name: "Dataset", cases: [{ id: "case-1", prompt: "hello" }] });
  assert.equal(boot.schema_version, CONTROL_PLANE_SCHEMA_VERSION);

  const key = service.createApiKey("tenant_ts_saas", "project_ts_saas", { name: "ingester", scopes: ["sdk:submit", "run:upload", "trace:ingest"], keyId: "key_ts_saas" });
  assert.equal(key.secret_value_present, false);
  assert.equal(JSON.stringify(key).includes("secret_hash_sha256"), false);

  const submitted = service.sdkSubmitRun("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", agentRef: "mock", runId: "run_ts_saas", apiKeyId: "key_ts_saas", idempotencyKey: "idem-submit" });
  const replay = service.sdkSubmitRun("tenant_ts_saas", "project_ts_saas", { datasetId: "dataset_ts_saas", agentRef: "mock", runId: "run_ts_saas_2", apiKeyId: "key_ts_saas", idempotencyKey: "idem-submit" });
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
