import assert from "node:assert/strict";
import test from "node:test";

import {
  RELEASEFOUNDRY_API_ENV_VAR,
  RELEASEFOUNDRY_DEFAULT_BASE_URL,
  RELEASEFOUNDRY_LEGACY_API_ENV_VAR,
  AGENT_INPUT_SCHEMA_VERSION,
  ReleaseFoundryApiClient,
  ReleaseFoundryApiError,
  MissingReleaseFoundryApiKeyError,
  enforceCreateRequestPreflight,
  redactApiSensitive,
  redactApiText,
  summarizeGenerationRequest,
} from "../dist/index.js";

function transportFrom(responses, seen = []) {
  return async (url, headers, body, timeoutMs) => {
    seen.push({ url, headers, body: JSON.parse(body), timeoutMs });
    const next = responses.shift();
    if (!next) {
      throw new Error("unexpected transport call");
    }
    return next;
  };
}

test("ReleaseFoundryApiClient dry-run defaults do not require keys or fetch", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    const client = new ReleaseFoundryApiClient();
    const record = await client.init();

    assert.equal(record.status, "planned");
    assert.equal(record.dry_run, true);
    assert.equal(record.attempts, 0);
    assert.equal(record.request.function, "init");
    assert.equal(record.response.plan.base_url, RELEASEFOUNDRY_DEFAULT_BASE_URL);
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fromEnv accepts explicit env records and never logs key values", () => {
  const client = ReleaseFoundryApiClient.fromEnv(
    {
      [RELEASEFOUNDRY_API_ENV_VAR]: "tp_syntheticsecret",
      [RELEASEFOUNDRY_LEGACY_API_ENV_VAR]: "tp_ignored",
    },
    { required: true },
  );

  assert.match(client.toString(), /apiKey=set/);
  assert.equal(client.toString().includes("tp_syntheticsecret"), false);
  assert.throws(() => ReleaseFoundryApiClient.fromEnv({}, { required: true }), MissingReleaseFoundryApiKeyError);
  assert.doesNotThrow(() => ReleaseFoundryApiClient.fromEnv({}, { required: false }));

  const previous = process.env[RELEASEFOUNDRY_API_ENV_VAR];
  try {
    process.env[RELEASEFOUNDRY_API_ENV_VAR] = "tp_processsynthetic";
    assert.match(ReleaseFoundryApiClient.fromEnv().toString(), /apiKey=set/);
    assert.equal(ReleaseFoundryApiClient.fromEnv().toString().includes("tp_processsynthetic"), false);
  } finally {
    if (previous === undefined) {
      delete process.env[RELEASEFOUNDRY_API_ENV_VAR];
    } else {
      process.env[RELEASEFOUNDRY_API_ENV_VAR] = previous;
    }
  }
});

test("read-only real execution uses injected transport and session context", async () => {
  const seen = [];
  const client = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 0,
    transport: transportFrom(
      [
        { statusCode: 200, body: { status: "ok", tenant: { id: 11 }, user: { id: 22 } } },
        { statusCode: 200, body: { status: "ok", datasets: [], next_cursor: null }, headers: { "x-ratelimit-remaining": "7" } },
      ],
      seen,
    ),
  });

  const record = await client.listDatasets({ dryRun: false, limit: 1 });

  assert.equal(seen.length, 2);
  assert.equal(seen[0].body.function, "init");
  assert.equal(seen[1].body.function, "list_datasets");
  assert.equal(seen[1].body.tenant_id, 11);
  assert.equal(seen[1].body.include_signed_urls, false);
  assert.equal(seen[1].headers.Authorization, "Bearer tp_syntheticsecret");
  assert.equal(record.status, "ok");
  assert.equal(record.request.params.tenant_id, 11);
  assert.equal(record.response_headers["x-ratelimit-remaining"], "7");
});

test("healthCheck maps to keep_alive and listAgents maps to list_agents", async () => {
  const health = await new ReleaseFoundryApiClient().healthCheck();
  const agents = await new ReleaseFoundryApiClient().listAgents();

  assert.equal(health.request.function, "keep_alive");
  assert.equal(health.response.plan.function, "keep_alive");
  assert.equal(agents.request.function, "list_agents");
});

test("missing keys block non-dry-run execution before transport", async () => {
  let transportCalled = false;
  const client = new ReleaseFoundryApiClient({
    transport: () => {
      transportCalled = true;
      throw new Error("transport must not be called");
    },
  });

  await assert.rejects(() => client.init({ dryRun: false }), MissingReleaseFoundryApiKeyError);
  await assert.rejects(() => client.pollRun({ dryRun: false, runId: 1, timeoutSeconds: 1, pollIntervalSeconds: 0 }), MissingReleaseFoundryApiKeyError);
  await assert.rejects(() => client.pollRequest({ dryRun: false, requestId: 1, timeoutSeconds: 1, pollIntervalSeconds: 0 }), MissingReleaseFoundryApiKeyError);
  assert.equal(transportCalled, false);
});

test("createRequest dry-run records media AgentInput schema and safe shape summaries", async () => {
  const request = {
    agent: {
      name: "media-agent",
      accepted_inputs: { text: true, image: true, audio: true, file: true, video: true },
      tools: [{ name: "tool", api_key: "tp_syntheticsecret" }],
    },
    generation_options: { generate_images: true, generate_audio: true, generate_files: true, generate_videos: true },
    test_config: { num_variations: 1 },
  };

  const record = await new ReleaseFoundryApiClient().createRequest({ requestName: "A1 Media Dry Run", request });

  assert.equal(record.status, "planned");
  assert.equal(record.request.mutates, true);
  assert.equal(record.request.params.request_input_schema.agent_input_schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.deepEqual(record.request.params.request_input_schema.agent_input_part_types, ["audio", "file", "image", "text", "video"]);
  assert.equal(record.request.params.request.generation_options.generate_videos, true);
  assert.equal(record.request.params.request.tools_count, 1);
  assert.equal(record.request.preflight.media_generation_enabled, true);
  assert.equal(record.request.preflight.non_text_inputs_enabled, true);
  assert.equal(JSON.stringify(record).includes("tp_syntheticsecret"), false);
});

test("createRequest real guardrails block unsafe mutations before transport", async () => {
  const client = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 0,
    transport: () => {
      throw new Error("transport must not be called");
    },
  });

  await assert.rejects(
    async () => client.createRequest({ dryRun: false, requestName: "unknown variations", request: { agent: { accepted_inputs: { text: true } } } }),
    /num_variations is unknown/,
  );
  await assert.rejects(
    async () =>
      client.createRequest({
        dryRun: false,
        requestName: "media blocked",
        request: {
          agent: { accepted_inputs: { text: true, image: true } },
          generation_options: { generate_images: true },
          test_config: { num_variations: 1 },
        },
      }),
    /enables media generation/,
  );
});


test("createRequest quota errors preserve safe quota shape", async () => {
  const client = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 0,
    transport: transportFrom([
      { statusCode: 200, body: { status: "ok", user: { id: 1, tenant_id: 2 }, tenant: { id: 2 } } },
      {
        statusCode: 200,
        body: {
          status: "error",
          message: "Usage limit exceeded for requests: 5/5 used, requested 1, 0 remaining",
          quota: { resource: "requests", limit: 5, used: 5, requested: 1, remaining: 0 },
        },
      },
    ]),
  });

  await assert.rejects(
    () =>
      client.createRequest({
        dryRun: false,
        requestName: "quota blocked",
        request: { agent: { accepted_inputs: { text: { enabled: true } } }, test_config: { num_variations: 1 } },
      }),
    (error) => {
      assert.equal(error instanceof ReleaseFoundryApiError, true);
      assert.match(error.message, /Usage limit exceeded/);
      const payload = JSON.stringify(error.response);
      assert.equal(payload.includes("tp_syntheticsecret"), false);
      assert.match(payload, /Usage limit exceeded/);
      assert.match(payload, /"quota"/);
      assert.match(payload, /"remaining":0/);
      return true;
    },
  );
});
test("mutating real calls require maxRetries zero", async () => {
  const client = new ReleaseFoundryApiClient({ apiKey: "tp_syntheticsecret" });

  await assert.rejects(
    async () => client.createRun({ dryRun: false, datasetId: 1, result: { status: "passed" } }),
    /requires maxRetries=0/,
  );
});

test("API errors and retryable statuses are redacted", async () => {
  const errorClient = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 0,
    transport: transportFrom([{ statusCode: 200, body: { status: "error", message: "bad tp_leaked owner@example.com" } }]),
  });
  await assert.rejects(
    () => errorClient.listAgents({ dryRun: false }),
    (error) => {
      assert.equal(error instanceof ReleaseFoundryApiError, true);
      assert.equal(error.message.includes("tp_leaked"), false);
      assert.equal(error.message.includes("owner@example.com"), false);
      assert.equal(error.response.error.response.message.includes("tp_leaked"), false);
      return true;
    },
  );

  const seen = [];
  const retryClient = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 1,
    retryBackoffMs: 0,
    transport: transportFrom(
      [
        { statusCode: 429, body: { message: "slow down" }, headers: { "retry-after": "1" } },
        { statusCode: 200, body: { status: "ok", db: "ok", message: "alive" } },
      ],
      seen,
    ),
  });
  const record = await retryClient.healthCheck({ dryRun: false });

  assert.equal(record.status, "ok");
  assert.equal(record.attempts, 2);
  assert.equal(seen.length, 2);
});

test("pollRequest failure summary keeps nested failure values private", async () => {
  const client = new ReleaseFoundryApiClient({
    apiKey: "tp_syntheticsecret",
    maxRetries: 0,
    transport: transportFrom([
      {
        statusCode: 200,
        body: {
          status: "ok",
          request: {
            request_status: "failed",
            request: { _failure: { at: "stage-1", error: "raw hosted failure detail" } },
          },
        },
      },
    ]),
  });

  await assert.rejects(
    () => client.pollRequest({ dryRun: false, requestId: 9, timeoutSeconds: 1, pollIntervalSeconds: 0 }),
    (error) => {
      assert.equal(error instanceof ReleaseFoundryApiError, true);
      const failure = error.response.error.failure_summary.failure_sources["request._failure"];
      assert.deepEqual(failure.keys, ["at", "error"]);
      assert.equal(failure.fields.error.type, "string");
      assert.equal(failure.fields.error.length, "raw hosted failure detail".length);
      assert.equal(JSON.stringify(error.response.error.failure_summary).includes("raw hosted failure detail"), false);
      return true;
    },
  );
});

test("preflight helpers mirror Python guardrail semantics", () => {
  const summary = summarizeGenerationRequest({
    agent: { accepted_inputs: { text: true, audio: { enabled: true } } },
    generation_options: { generate_audio: true },
    test_config: { num_variations: "2" },
  });

  assert.equal(summary.num_variations, 2);
  assert.equal(summary.agent_input_schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.equal(summary.media_generation_enabled, true);
  assert.equal(summary.cost_risk.level, "paid_media_generation");
  assert.equal(summary.cost_risk.estimated_generated_asset_units, 2);
  assert.deepEqual(summary.cost_risk.generated_media_modalities, ["audio"]);
  assert.throws(() => enforceCreateRequestPreflight(summary, { allowMediaGeneration: true, allowNonTextInputs: true, maxRequestVariations: 1 }), /exceeds/);
  assert.deepEqual(redactApiSensitive({ api_key: "tp_syntheticsecret", url: "https://x.invalid/a?sig=1" }), {
    api_key: "[redacted]",
    url: "https://x.invalid/a?[redacted]",
  });
  assert.equal(redactApiText("Bearer abc.def sk-testtest owner@example.com").includes("abc.def"), false);
});
