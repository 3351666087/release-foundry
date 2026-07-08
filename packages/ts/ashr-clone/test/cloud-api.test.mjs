import assert from "node:assert/strict";
import test from "node:test";

import {
  AGENT_INPUT_SCHEMA_VERSION,
  AGENT_TURN_SCHEMA_VERSION,
  CLOUD_API_SCHEMA_VERSION,
  RUN_RESULT_SCHEMA_VERSION,
  CloudApiService,
  QuotaLedger,
  agentInputFromParts,
  agentInputFromText,
  buildDefaultRequestInputSchema,
  coerceAgentInput,
  redactSensitive,
  redactText,
  runAgentCloudDemo,
} from "../dist/index.js";

function sampleRunResult() {
  return {
    run_id: "run_ts",
    dataset_id: "dataset_ts",
    runner_id: "ts-runner",
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
        status: "passed",
        observations: [
          { observation_id: "obs-1", type: "agent_turn", payload: { text: "Echo: hello" } },
          { observation_id: "obs-2", type: "tool_call", payload: { name: "calculator" } },
        ],
      },
    ],
    aggregate_metrics: { schema_version: "ashr.clone.run_result.v1", trace_completeness: 1.0 },
    metadata: { local_only: true, ashr_api_used: false },
    field_map_version: "a1.local.v1",
  };
}

test("coerceAgentInput preserves text and media parts", () => {
  const input = coerceAgentInput("hello", {
    parts: [
      "hello",
      { type: "image", url: "https://example.invalid/image.png", mimeType: "image/png" },
      { type: "audio", path: "local.wav", description: "local fixture" },
      { type: "video", path: "clip.mp4", mime_type: "video/mp4" },
    ],
    metadata: { case_id: "case-1" },
  });

  assert.equal(input.schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.equal(input.text, "hello");
  assert.deepEqual(input.parts.map((part) => part.type), ["text", "image", "audio", "video"]);
  assert.equal(input.parts[1].mime_type, "image/png");
  assert.equal(input.parts[3].mime_type, "video/mp4");
  assert.equal(input.metadata.case_id, "case-1");
});

test("agent input helpers expose Python-compatible constants and defaults", () => {
  assert.equal(AGENT_TURN_SCHEMA_VERSION, "ashr.clone.agent_turn.v1");
  assert.equal(RUN_RESULT_SCHEMA_VERSION, "ashr.clone.run_result.v1");
  assert.deepEqual(agentInputFromText("hello").parts, [{ type: "text", text: "hello" }]);
  assert.deepEqual(agentInputFromParts([{ type: "file", path: "fixture.json" }], { text: "inspect" }).parts, [
    { type: "file", path: "fixture.json" },
  ]);
});

test("buildDefaultRequestInputSchema mirrors media AgentInput part schema", () => {
  const textOnly = buildDefaultRequestInputSchema({ agent: { accepted_inputs: { text: true } } });
  assert.equal(textOnly.type, "object");
  assert.equal(textOnly.additionalProperties, true);
  assert.equal("$defs" in textOnly, false);

  const media = buildDefaultRequestInputSchema({
    agent: {
      accepted_inputs: { text: true, image: true, audio: true, file: true, video: true },
      tools: [{ name: "secret_tool", api_key: "tp_secretvalue" }],
    },
  });
  assert.equal(media.properties.schema_version.const, AGENT_INPUT_SCHEMA_VERSION);
  assert.equal(media.properties.parts.items.$ref, "#/$defs/agent_input_part");
  assert.deepEqual(media.$defs.agent_input_part.oneOf[1].properties.type.enum, ["image", "audio", "file", "video"]);
  assert.equal(media.tools[0].api_key, "[redacted]");

  const imageOnly = buildDefaultRequestInputSchema({ agent: { accepted_inputs: { text: false, image: true } } });
  assert.deepEqual(imageOnly.$defs.agent_input_part.properties.type.enum, ["image"]);
});

test("redaction covers tokens, keys, emails, bearer values, and signed URL queries", () => {
  const text = "tp_secret sk-testtesttest Bearer abc.def owner@example.com https://signed.invalid/file.png?token=abc";
  const redacted = redactText(text);

  assert.equal(redacted.includes("tp_secret"), false);
  assert.equal(redacted.includes("sk-testtesttest"), false);
  assert.equal(redacted.includes("abc.def"), false);
  assert.equal(redacted.includes("owner@example.com"), false);
  assert.equal(redacted.includes("token=abc"), false);
  assert.equal(redacted.includes("[redacted]"), true);
  assert.deepEqual(redactSensitive({ api_key: "secret", nested: { url: "https://x.invalid/a?sig=1" } }), {
    api_key: "[redacted]",
    nested: { url: "https://x.invalid/a?[redacted]" },
  });
});

test("CloudApiService runs local tenant project dataset run fixture loop without fetch", () => {
  const originalFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    const service = new CloudApiService();
    const tenant = service.createTenant("Tenant", { tenantId: "tenant_ts", metadata: { local_only: true } });
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
    const fixture = service.exportRunFixture(tenant.tenant_id, project.project_id, run.run_id);
    const quota = service.quotaSnapshot(tenant.tenant_id, project.project_id);

    assert.equal(run.schema_version, CLOUD_API_SCHEMA_VERSION);
    assert.equal(run.status, "completed");
    assert.equal(run.result_status, "passed");
    assert.equal(run.observations.length, 2);
    assert.equal(poll.status, "completed");
    assert.equal(fixture.metadata.local_only, true);
    assert.equal(fixture.metadata.ashr_api_used, false);
    assert.equal(quota.used["dataset.create"], 1);
    assert.equal(quota.used["run.submit"], 1);
    assert.equal(quota.used["observation.write"], 2);
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("CloudApiService enforces tenant/project isolation", () => {
  const service = new CloudApiService();
  service.createTenant("Tenant A", { tenantId: "tenant_a" });
  service.createTenant("Tenant B", { tenantId: "tenant_b" });
  const project = service.createProject("tenant_a", "Project", { projectId: "project_a" });
  const dataset = service.createDataset("tenant_a", project.project_id, {
    datasetId: "dataset_a",
    name: "Dataset",
    cases: [{ id: "case-1" }],
  });

  assert.throws(() => service.getDataset("tenant_b", project.project_id, dataset.dataset_id), /dataset not found/);
});

test("QuotaLedger blocks run writes before consuming run quota", () => {
  const quota = new QuotaLedger();
  const service = new CloudApiService({ quota });
  service.createTenant("Tenant", { tenantId: "tenant_quota" });
  service.createProject("tenant_quota", "Project", { projectId: "project_quota" });
  quota.configure("tenant_quota", "project_quota", { "observation.write": 1 });
  service.createDataset("tenant_quota", "project_quota", {
    datasetId: "dataset_quota",
    name: "Dataset",
    cases: [{ id: "case-1" }],
  });

  assert.throws(
    () =>
      service.submitRun("tenant_quota", "project_quota", {
        datasetId: "dataset_quota",
        runResult: sampleRunResult(),
      }),
    /quota exceeded/,
  );
  const snapshot = service.quotaSnapshot("tenant_quota", "project_quota");
  assert.equal(snapshot.used["run.submit"] ?? 0, 0);
  assert.equal(service.listRuns("tenant_quota", "project_quota").length, 0);
});

test("request records preserve AgentInput-compatible media schema", () => {
  const service = new CloudApiService();
  service.createTenant("Tenant", { tenantId: "tenant_request" });
  service.createProject("tenant_request", "Project", { projectId: "project_request" });

  const request = service.createRequest("tenant_request", "project_request", {
    requestId: "request_media",
    name: "Media Request",
    acceptedInputs: { text: true, image: true, audio: true, file: true },
    requestInputSchema: {
      type: "object",
      properties: {
        schema_version: { const: AGENT_INPUT_SCHEMA_VERSION },
        parts: { type: "array" },
      },
    },
  });

  assert.equal(request.schema_version, CLOUD_API_SCHEMA_VERSION);
  assert.equal(request.accepted_inputs.image, true);
  assert.equal(request.request_input_schema.properties.schema_version.const, AGENT_INPUT_SCHEMA_VERSION);
});

test("runAgentCloudDemo adapts an external TS agent into local cloud fixture", async () => {
  const summary = await runAgentCloudDemo({
    tenantId: "tenant_demo",
    projectId: "project_demo",
    datasetId: "dataset_demo",
    runnerId: "ts-demo-runner",
    cases: [{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }],
    agent: (agentInput) => ({
      schema_version: AGENT_TURN_SCHEMA_VERSION,
      text: `Echo: ${agentInput.text}`,
      tool_calls: [],
      status: "ok",
      latency_ms: 0,
      metadata: { local_only: true },
    }),
  });

  assert.equal(summary.schema_version, CLOUD_API_SCHEMA_VERSION);
  assert.equal(summary.run.status, "completed");
  assert.equal(summary.run.result_status, "passed");
  assert.equal(summary.run.passed, 1);
  assert.equal(summary.run.observations, 2);
  assert.equal(summary.fixture.metadata.ashr_api_used, false);
  assert.equal(summary.quota.used["dataset.create"], 1);
  assert.equal(summary.quota.used["run.submit"], 1);
});
