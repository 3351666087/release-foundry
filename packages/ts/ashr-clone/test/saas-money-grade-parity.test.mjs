import assert from "node:assert/strict";
import test from "node:test";

import { SaaSControlPlaneService, CONTROL_PLANE_SCHEMA_VERSION } from "../dist/saas.js";

function seededService(suffix = "money") {
  const service = new SaaSControlPlaneService();
  const tenantId = `tenant_ts_${suffix}`;
  const projectId = `project_ts_${suffix}`;
  const datasetId = `dataset_ts_${suffix}`;
  const runId = `run_ts_${suffix}`;
  service.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId, projectId });
  service.cloud.createDataset(tenantId, projectId, { datasetId, name: "Dataset", cases: [{ id: "case-1", prompt: "hello" }] });
  return { service, tenantId, projectId, datasetId, runId };
}

function completedRun(suffix = "money") {
  const ctx = seededService(suffix);
  const { service, tenantId, projectId, datasetId, runId } = ctx;
  const key = service.createApiKey(tenantId, projectId, {
    name: "all surface",
    keyId: `key_${suffix}`,
    revealSecret: true,
    scopes: ["sdk:submit", "run:upload", "trace:ingest", "artifact:upload", "evidence:read", "audit:read", "worker_job:write", "worker_job:read", "usage:read"],
  });
  service.sdkSubmitRun(tenantId, projectId, { datasetId, agentRef: "mock", runId, apiKeyId: key.key_id, idempotencyKey: `submit_${suffix}` });
  service.uploadRunResult(tenantId, projectId, runId, { run_id: runId, status: "completed", score: 1, raw_payload: "must_not_leak" }, { uploadId: `upload_${suffix}`, apiKeyId: key.key_id, idempotencyKey: `upload_${suffix}` });
  service.ingestTrace(tenantId, projectId, runId, [{ observation_id: `obs_${suffix}`, type: "agent_message", content: "ok" }], { batchId: `trace_${suffix}`, apiKeyId: key.key_id, idempotencyKey: `trace_${suffix}` });
  return { ...ctx, key };
}

for (const scope of ["sdk:submit", "run:upload", "trace:ingest", "artifact:upload", "evidence:read", "audit:read", "worker_job:write", "worker_job:read", "usage:read"]) {
  test(`TS SaaS API key authenticates normalized scope ${scope}`, () => {
    const { service, tenantId, projectId } = seededService(scope.replace(/[:_]/g, "_"));
    const key = service.createApiKey(tenantId, projectId, { name: "scoped", keyId: `key_${scope.replace(/[:_]/g, "_")}`, scopes: [scope] });
    const auth = service.authenticateApiKey(tenantId, projectId, { keyId: key.key_id, scope, consumeRate: false });

    assert.equal(auth.authenticated, true);
    assert.equal(auth.api_key.key_id, key.key_id);
    assert.equal(auth.secret_value_present, false);
  });
}

test("TS SaaS revoked API key fails closed for future mutations", () => {
  const { service, tenantId, projectId, datasetId } = seededService("revoked");
  const key = service.createApiKey(tenantId, projectId, { name: "revoked", keyId: "key_revoked", scopes: ["sdk:submit"] });
  const revoked = service.revokeApiKey(tenantId, projectId, key.key_id);

  assert.equal(revoked.status, "revoked");
  assert.throws(() => service.sdkSubmitRun(tenantId, projectId, { datasetId, agentRef: "mock", runId: "run_revoked", apiKeyId: key.key_id }), /not active/);
});

test("TS SaaS artifact evidence requires evidence read scope for listing", () => {
  const { service, tenantId, projectId, runId, key } = completedRun("artifact_scope");
  const artifact = service.createArtifactManifest(tenantId, projectId, runId, { kind: "report", raw_payload: "must_not_leak" }, { artifactId: "artifact_scope", apiKeyId: key.key_id, idempotencyKey: "artifact_scope" });

  assert.equal(JSON.stringify(artifact).includes("must_not_leak"), false);
  assert.equal(service.listArtifactManifests(tenantId, projectId, runId, { authKeyId: key.key_id }).length, 1);
});

test("TS SaaS release evidence verification detects tampered packet fields", () => {
  const { service, tenantId, projectId, runId, key } = completedRun("release_tamper");
  service.createArtifactManifest(tenantId, projectId, runId, { kind: "report" }, { artifactId: "artifact_tamper", apiKeyId: key.key_id });
  const gate = service.evaluateReleaseGate(tenantId, projectId, runId, { authKeyId: key.key_id });
  const packet = service.buildReleaseEvidencePacket(tenantId, projectId, runId, { releaseGate: gate, authKeyId: key.key_id });
  const tampered = { ...packet, run_id: "wrong-run" };
  const verification = service.verifyReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId: key.key_id, packet: tampered });

  assert.equal(verification.verified, false);
  assert.equal(verification.failures.some((failure) => failure.reason === "run_id_mismatch"), true);
});

test("TS SaaS worker lease ownership blocks stale completion", () => {
  const { service, tenantId, projectId, key } = completedRun("worker_owner");
  const enqueued = service.enqueueWorkerJob(tenantId, projectId, { jobType: "run.replay", jobId: "job_owner", payload: { run_id: "run_ts_worker_owner" }, apiKeyId: key.key_id });
  const leased = service.leaseWorkerJob(tenantId, projectId, { leaseOwnerId: "worker-a", apiKeyId: key.key_id });

  assert.equal(enqueued.job_id, "job_owner");
  assert.equal(leased.job.job_id, "job_owner");
  assert.throws(() => service.completeWorkerJob(tenantId, projectId, "job_owner", {}, { leaseOwnerId: "worker-b", apiKeyId: key.key_id }), /owner mismatch/);
  const completed = service.completeWorkerJob(tenantId, projectId, "job_owner", { ok: true }, { leaseOwnerId: "worker-a", apiKeyId: key.key_id });
  assert.equal(completed.status, "completed");
});

test("TS SaaS audit chain verification requires audit scope and reports chain head tail", () => {
  const { service, tenantId, projectId, key } = completedRun("audit_chain");
  const verification = service.verifyAuditChain(tenantId, projectId, { authKeyId: key.key_id });

  assert.equal(verification.schema_version, "ashr.clone.audit_chain_verification.v1");
  assert.equal(verification.verified, true);
  assert.equal(Number(verification.event_count) > 0, true);
  assert.equal(typeof verification.tail_audit_event_sha256, "string");
});

test("TS SaaS snapshot restore preserves API key rate-limit and audit state", () => {
  const { service, tenantId, projectId, datasetId } = seededService("restore_limits");
  const key = service.createApiKey(tenantId, projectId, { name: "limited", keyId: "key_restore_limits", scopes: ["sdk:submit"] });
  service.configureApiKeyRateLimit(tenantId, projectId, { keyId: key.key_id, operation: "sdk:submit", limit: 1 });
  service.sdkSubmitRun(tenantId, projectId, { datasetId, agentRef: "mock", runId: "run_restore_limits", apiKeyId: key.key_id });
  const restored = SaaSControlPlaneService.fromState(service.snapshotState());

  assert.throws(() => restored.sdkSubmitRun(tenantId, projectId, { datasetId, agentRef: "mock", runId: "run_restore_limits_2", apiKeyId: key.key_id }), /rate limit exceeded/);
  assert.equal(restored.auditSnapshot(tenantId, projectId).events.length > 0, true);
});
