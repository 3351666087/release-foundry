import assert from "node:assert/strict";
import test from "node:test";

import {
  MODEL_INPUT_PART_TYPES,
  MODEL_PROVIDERS,
  ModelAdapterError,
  ModelProviderAdapter,
  ModelProviderError,
  ProviderNeutralModelAdapter,
  createCapabilityCalibration,
  createCapabilityProfile,
} from "../dist/provider-adapter.js";

function response(body, options = {}) {
  return new Response(
    typeof body === "string" || body instanceof ReadableStream ? body : JSON.stringify(body),
    {
      status: options.status ?? 200,
      headers: { "content-type": "application/json", ...(options.headers ?? {}) },
    },
  );
}

function chunked(...chunks) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

test("OpenAI-compatible completion normalizes tools, usage, finish and request id", async () => {
  let sent;
  const adapter = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1/",
    apiKey: "sk-private-value",
    fetch: async (url, init) => {
      sent = { url, init, body: JSON.parse(init.body) };
      return response({
        choices: [{
          message: {
            content: "hello",
            tool_calls: [{ id: "call-1", function: { name: "lookup", arguments: "{\"q\":\"x\"}" } }],
          },
          finish_reason: "tool_calls",
        }],
        usage: { prompt_tokens: 4, completion_tokens: 3, total_tokens: 7 },
      }, { headers: { "x-request-id": "req-1" } });
    },
  });
  const result = await adapter.run({
    model: "commercial-model",
    input: "hello",
    tools: [{ name: "lookup", parameters: { type: "object" } }],
  });

  assert.equal(sent.url, "https://models.example/v1/chat/completions");
  assert.equal(sent.body.tools[0].function.name, "lookup");
  assert.equal(result.text, "hello");
  assert.equal(result.tool_calls[0].arguments, "{\"q\":\"x\"}");
  assert.equal(result.usage.total_tokens, 7);
  assert.equal(result.finish_reason, "tool_calls");
  assert.equal(result.request_id, "req-1");
});

test("five modalities remain provider-local and preserve media envelopes", async () => {
  let body;
  const adapter = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    fetch: async (_url, init) => {
      body = JSON.parse(init.body);
      return response({ choices: [{ message: { content: "ok" }, finish_reason: "stop" }] });
    },
  });
  await adapter.run({
    model: "m",
    input: [
      { type: "text", text: "inspect" },
      { type: "image", url: "https://example.test/image.png" },
      { type: "audio", data: "YQ==", mime_type: "audio/wav" },
      { type: "file", url: "https://example.test/file.pdf", name: "file.pdf" },
      { type: "video", url: "https://example.test/video.mp4" },
    ],
  });
  assert.deepEqual(body.messages[0].content.map((part) => part.type), [
    "text", "image_url", "input_audio", "input_file", "input_video",
  ]);
});

test("finish reason preserves provider truth independent of tool calls", async () => {
  const payloads = [
    {
      choices: [{
        message: {
          content: "",
          tool_calls: [{ id: "call-1", function: { name: "lookup", arguments: "{}" } }],
        },
        finish_reason: "stop",
      }],
    },
    {
      choices: [{ message: { content: "bounded" }, finish_reason: "model_length" }],
    },
  ];
  const adapter = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    fetch: async () => response(payloads.shift()),
  });
  const toolResult = await adapter.run({ model: "m", input: "x" });
  const unknownResult = await adapter.run({ model: "m", input: "x" });
  assert.equal(toolResult.finish_reason, "stop");
  assert.equal(toolResult.tool_calls.length, 1);
  assert.equal(unknownResult.finish_reason, "model_length");
});

test("OpenAI SSE consumes split frames and merges tool fragments", async () => {
  const adapter = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    fetch: async () => response(chunked(
      'data: {"choices":[{"delta":{"content":"hel"},"finish_reason":null}]}\n',
      '\ndata: {"choices":[{"delta":{"content":"lo","tool_calls":[{"index":0,"id":"c1","function":{"name":"lookup","arguments":"{\\\"q\\\":"}}]},"finish_reason":null}]}\n\n',
      'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\\"x\\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n',
      'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\ndata: [DONE]\n\n',
    )),
  });
  const result = await adapter.run({ model: "m", input: "hi", stream: true });
  assert.equal(result.text, "hello");
  assert.equal(result.tool_calls[0].id, "c1");
  assert.equal(result.tool_calls[0].name, "lookup");
  assert.equal(result.usage.total_tokens, 5);
  assert.equal(result.finish_reason, "tool_calls");
});

test("Ollama NDJSON normalizes text, tools and token usage", async () => {
  const adapter = new ModelProviderAdapter({
    provider: "ollama",
    baseUrl: "http://localhost:11434",
    fetch: async () => response(chunked(
      '{"message":{"content":"a"},"done":false}\n',
      '{"message":{"content":"b","tool_calls":[{"function":{"name":"echo","arguments":{"x":1}}}]},"done":true,"done_reason":"stop","prompt_eval_count":1,"eval_count":2}\n',
    )),
  });
  const result = await adapter.run({ model: "qwen", input: "hi", stream: true });
  assert.equal(result.text, "ab");
  assert.equal(result.tool_calls[0].name, "echo");
  assert.equal(result.usage.total_tokens, 3);
  assert.equal(result.finish_reason, "stop");
});

test("retry policy retries transient responses but not ordinary 4xx", async () => {
  let calls = 0;
  const delays = [];
  const adapter = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    maxRetries: 2,
    retryBackoffMs: 10,
    sleep: async (delay) => delays.push(delay),
    fetch: async () => {
      calls += 1;
      if (calls < 3) return response("limited", { status: 429 });
      return response({ choices: [{ message: { content: "ok" }, finish_reason: "stop" }] });
    },
  });
  assert.equal((await adapter.run({ model: "m", input: "x" })).text, "ok");
  assert.equal(calls, 3);
  assert.deepEqual(delays, [10, 20]);

  let badCalls = 0;
  const bad = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    maxRetries: 4,
    fetch: async () => {
      badCalls += 1;
      return response("bad", { status: 400 });
    },
  });
  await assert.rejects(() => bad.run({ model: "m", input: "x" }), (error) => {
    assert.equal(error.code, "invalid_request");
    return true;
  });
  assert.equal(badCalls, 1);
});

test("timeout errors are safe and stream failures do not replay", async () => {
  const timed = new ModelProviderAdapter({
    provider: "ollama",
    baseUrl: "http://localhost:11434",
    maxRetries: 0,
    fetch: async () => {
      const error = new Error("Authorization: Bearer sk-super-secret");
      error.name = "AbortError";
      throw error;
    },
  });
  await assert.rejects(() => timed.run({ model: "m", input: "x" }), (error) => {
    assert.equal(error.code, "timeout");
    assert.equal(String(error).includes("super-secret"), false);
    return true;
  });

  let calls = 0;
  const streaming = new ModelProviderAdapter({
    provider: "openai-compatible",
    baseUrl: "https://models.example/v1",
    maxRetries: 3,
    fetch: async () => {
      calls += 1;
      return response(chunked(
        'data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}\n\n',
        "data: not-json\n\n",
      ));
    },
  });
  await assert.rejects(
    () => streaming.run({ model: "m", input: "x", stream: true }),
    ModelProviderError,
  );
  assert.equal(calls, 1);
});

test("Python-compatible provider symbols retain meaningful runtime behavior", () => {
  assert.deepEqual([...MODEL_INPUT_PART_TYPES], ["text", "image", "audio", "file", "video"]);
  assert.deepEqual([...MODEL_PROVIDERS], ["openai_compatible", "ollama"]);
  assert.equal(ProviderNeutralModelAdapter, ModelProviderAdapter);

  const error = new ModelAdapterError("rate_limit", "retry later", {
    retryable: true,
    status_code: 429,
  });
  assert.equal(error.kind, "rate_limit");
  assert.equal(error.status_code, 429);
  assert.deepEqual(error.toJSON(), {
    kind: "rate_limit",
    message: "retry later",
    status_code: 429,
    retryable: true,
  });
});

test("capability calibration is endpoint model and evidence scoped", async () => {
  const record = await createCapabilityCalibration({
    provider: "ollama",
    model: "qwen2.5:1.5b",
    baseUrl: "http://localhost:11434/",
    calibratedAt: "2026-07-12T00:00:00Z",
    evidence: "redacted calibration facts",
    capabilities: { text: "callable", stream: "callable", tools: "callable", usage: "callable" },
  });
  assert.equal(record.provider, "ollama");
  assert.equal(record.model, "qwen2.5:1.5b");
  assert.equal(record.endpoint_sha256.length, 64);
  assert.equal(record.evidence_sha256.length, 64);
  assert.equal(record.capabilities.tools, "callable");
  assert.equal("image" in record.capabilities, false);
});

test("capability calibration rejects non-terminal states and weak evidence metadata at runtime", async () => {
  const base = {
    provider: "ollama",
    model: "qwen2.5:1.5b",
    baseUrl: "http://localhost:11434",
    calibratedAt: "2026-07-12T00:00:00Z",
    evidence: "facts",
    capabilities: { text: "callable" },
  };
  for (const overrides of [
    { capabilities: { text: "discovered" } },
    { capabilities: { text: "arbitrary" } },
    { evidence: "" },
    { evidence: new Uint8Array() },
    { calibratedAt: "2026-07-12T00:00:00" },
    { calibratedAt: "not-a-timestamp" },
  ]) {
    await assert.rejects(createCapabilityCalibration({ ...base, ...overrides }));
  }
});

test("capability profiles distinguish discovered from callable modalities", () => {
  const initial = createCapabilityProfile("ollama", "qwen");
  assert.equal(initial.modalities.text.state, "callable");
  assert.equal(initial.modalities.image.state, "discovered");
  assert.equal(initial.tools.state, "discovered");

  const calibrated = createCapabilityProfile("openai-compatible", "vision-model", {
    image: { state: "callable", checked_at: "2026-07-12T00:00:00Z" },
    audio: { state: "failed", detail: "provider rejected audio envelope" },
  });
  assert.equal(calibrated.modalities.image.state, "callable");
  assert.equal(calibrated.modalities.audio.state, "failed");
});
