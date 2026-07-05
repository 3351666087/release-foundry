import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  AGENT_INPUT_SCHEMA_VERSION,
  CLOUD_API_SCHEMA_VERSION,
  CloudApiService,
  QuotaExceededError,
  agentInputFromText,
  coerceAgentInput,
  redactSensitive,
  redactText,
} from "../dist/index.js";

function sampleRunResult() {
  return {
    run_id: "run_ts_demo",
    dataset_id: "dataset_ts",
    runner_id: "ts-local-runner",
    status: "passed",
    total_cases: 1,
    passed: 1,
    failed: 0,
    errored: 0,
    timed_out: 0,
    ended_at: "2026-07-04T00:00:00.000Z",
    cases: [
      {
        case_id: "case-1",
        observations: [
          { observation_id: "obs-user", role: "user", content: "hello" },
          { observation_id: "obs-assistant", role: "assistant", content: "Echo: hello" },
        ],
      },
    ],
  };
}

test("AgentInput helpers keep text and media parts typed", () => {
  const text = agentInputFromText("hello", { source: "test" });
  assert.equal(text.schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.deepEqual(text.parts, [{ type: "text", text: "hello" }]);

  const media = coerceAgentInput({
    text: "inspect",
    parts: [
      { type: "text", text: "inspect" },
      { type: "image", path: "fixtures/image.png", mime_type: "image/png" },
      { type: "video", path: "fixtures/clip.mp4", mime_type: "video/mp4" },
    ],
  });
  assert.equal(media.parts[1].type, "image");
  assert.equal(media.parts[1].path, "fixtures/image.png");
  assert.equal(media.parts[2].type, "video");
});

test("CloudApiService submits a run, polls it, and writes a fixture without fetch", () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = () => {
    throw new Error("fetch must not be called");
  };
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-"));
  try {
    const service = new CloudApiService({ clock: () => "2026-07-04T00:00:00.000Z" });
    const tenant = service.createTenant("Tenant", { tenantId: "tenant_ts" });
    const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_ts" });
    const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
      datasetId: "dataset_ts",
      name: "Dataset",
      cases: [{ id: "case-1", prompt: "hello" }],
    });
    const run = service.submitRun(tenant.tenant_id, project.project_id, {
      datasetId: dataset.dataset_id,
      runResult: sampleRunResult(),
    });
    const poll = service.pollRun(tenant.tenant_id, project.project_id, run.run_id);
    const outputPath = join(temp, "fixture.json");
    writeFileSync(outputPath, `${JSON.stringify(service.exportRunFixture(tenant.tenant_id, project.project_id, run.run_id), null, 2)}\n`, "utf8");
    const fixture = JSON.parse(readFileSync(outputPath, "utf8"));

    assert.equal(poll.status, "completed");
    assert.equal(fixture.schema_version, CLOUD_API_SCHEMA_VERSION);
    assert.equal(fixture.metadata.ashr_api_used, false);
    assert.equal(fixture.observations.length, 2);
    assert.equal(service.quotaSnapshot(tenant.tenant_id, project.project_id).used["run.submit"], 1);
  } finally {
    globalThis.fetch = previousFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

test("quota checks block before run writes", () => {
  const service = new CloudApiService();
  const tenant = service.createTenant("Tenant", { tenantId: "tenant_quota" });
  const project = service.createProject(tenant.tenant_id, "Project", { projectId: "project_quota" });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId: "dataset_quota",
    name: "Dataset",
    cases: [{ id: "case-1" }],
  });
  service.quota.configure(tenant.tenant_id, project.project_id, { "observation.write": 1 });

  assert.throws(
    () => service.submitRun(tenant.tenant_id, project.project_id, { datasetId: dataset.dataset_id, runResult: sampleRunResult() }),
    QuotaExceededError,
  );
  assert.equal(service.listRuns(tenant.tenant_id, project.project_id).length, 0);
});

test("redaction helper handles keys, bearer tokens, emails, and query signatures", () => {
  const redacted = redactSensitive({
    Authorization: "Bearer abc.def-123",
    api_key: "sk-testtesttest",
    nested: "owner@example.com?sig=secret",
  });
  assert.deepEqual(redacted, {
    Authorization: "[redacted]",
    api_key: "[redacted]",
    nested: "[redacted]?sig=[redacted]",
  });
  assert.equal(redactText("token tp_secretvalue owner@example.com"), "token [redacted] [redacted]");
});
