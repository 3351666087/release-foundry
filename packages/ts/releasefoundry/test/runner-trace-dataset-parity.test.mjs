import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  AGENT_INPUT_SCHEMA_VERSION,
  AgentAdapter,
  AgentAdapterError,
  AgentResult,
  TraceRecorder,
  apiRecordToCases,
  buildRunFixture,
  buildTraceRunFixture,
  buildVmStream,
  caseFromSourceRun,
  datasetSourceToCases,
  extractDatasetSource,
  loadRunFixture,
  replayFixtureFromSourceRun,
  runAgentBatch,
  toA2JudgeRun,
  traceEventsFromVmStream,
  validateRunFixture,
  validateVmStreamFrame,
  writeRunFixture,
} from "../dist/index.js";

function sourceFixture() {
  return {
    dataset_type: "voice",
    total_runs: 3,
    runs: {
      alpha: {
        run_id: "alpha-run",
        title: "Alpha",
        intent: "book",
        actions: [
          { actor: "user", content: "hello" },
          { actor: "agent", name: "ask_time", content: "what time?", expected_response: { text: "what time?" } },
          { actor: "user", content: "7pm" },
          { actor: "agent", name: "reserve", tool_calls: [{ name: "calendar", arguments: { hour: 19 } }], expected_response: { tool_calls: [{ name: "calendar", arguments: { hour: 19 } }] } },
        ],
      },
      beta: { run_id: "beta-run", title: "Beta", actions: [{ actor: "user", content: "agentless" }] },
    },
  };
}

test("TS AgentAdapter keyword style passes request envelope under custom key", async () => {
  const seen = [];
  const adapter = new AgentAdapter((payload) => {
    seen.push(payload);
    return { text: payload.request.text };
  }, { inputStyle: "keyword", inputKeyword: "request" });
  const turn = await adapter.respond("hello");
  assert.equal(turn.text, "hello");
  assert.equal(seen[0].request.schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.equal(turn.metadata.style, "callable:keyword");
});

test("TS AgentAdapter reset failure is recorded without raiseErrors", async () => {
  const adapter = new AgentAdapter({ reset() { throw new Error("reset Bearer should-not-leak"); }, respond() { return "ok"; } });
  assert.equal(await adapter.reset(), false);
  assert.equal(adapter.lastResetError.message.includes("should-not-leak"), false);
});

test("TS AgentAdapter reset failure raises redacted adapter error", async () => {
  const adapter = new AgentAdapter({ reset() { throw new Error("reset Bearer should-not-leak"); }, respond() { return "ok"; } }, { raiseErrors: true });
  await assert.rejects(() => adapter.reset(), (error) => error instanceof AgentAdapterError && !String(error.message).includes("should-not-leak"));
});

test("TS AgentAdapter response failure becomes error turn with redacted context", async () => {
  const adapter = new AgentAdapter(() => { throw new Error("boom Bearer should-not-leak"); });
  const turn = await adapter.respond("hello", { api_key: "tp_should_not_leak" });
  assert.equal(turn.status, "error");
  assert.equal(JSON.stringify(turn).includes("should-not-leak"), false);
  assert.equal(JSON.stringify(turn).includes("tp_should_not_leak"), false);
});

test("TS AgentAdapter raiseErrors propagates response failures", async () => {
  const adapter = new AgentAdapter(() => { throw new Error("boom"); }, { raiseErrors: true });
  await assert.rejects(() => adapter.respond("hello"), /boom/);
});

test("TS AgentAdapter copies AgentResult before adding adapter metadata", async () => {
  const original = new AgentResult({ text: "ok", metadata: { source: "agent" } });
  const adapter = new AgentAdapter(() => original, { name: "adapter-copy" });
  const turn = await adapter.respond("hello");
  assert.notEqual(turn, original);
  assert.equal(turn.metadata.source, "agent");
  assert.equal(turn.metadata.adapter_name, "adapter-copy");
  assert.equal(original.metadata.adapter_name, undefined);
});

test("TS AgentAdapter falls back to callable when respond attribute is not callable", async () => {
  function callable(input) { return { text: `call:${input}` }; }
  callable.respond = "not a function";
  const turn = await new AgentAdapter(callable).respond("ping");
  assert.equal(turn.text, "call:ping");
  assert.equal(turn.metadata.style, "callable");
});

test("TS toA2JudgeRun extracts text from OpenAI style content parts", async () => {
  const result = await runAgentBatch(() => ({ message: { content: "hello" } }), [{ id: "case", prompt: "hi", expected: { text: "hello" } }]);
  const judge = toA2JudgeRun(result.cases[0].agent_output);
  assert.equal(judge.final_response, "hello");
  assert.equal(result.cases[0].grade.passed, true);
});

test("TS runAgentBatch handles plain mapping output without tool calls", async () => {
  const result = await runAgentBatch(() => ({ response: "plain map" }), [{ id: "case", prompt: "hi", expected: { text: "plain map" } }]);
  assert.equal(result.status, "passed");
  assert.equal(result.cases[0].agent_output.text, "plain map");
});

test("TS run fixture preserves local-only metadata after build", async () => {
  const result = await runAgentBatch(() => "ok", [{ id: "case", prompt: "hi", expected: { text: "ok" } }], { runId: "run_fixture_meta" });
  const fixture = buildRunFixture(result, { name: "meta" });
  assert.equal(fixture.replay.metadata.releasefoundry_api_used, false);
  assert.equal(fixture.replay.metadata.local_only, true);
});

test("TS validateVmStreamFrame rejects unsupported streams", () => {
  assert.throws(() => validateVmStreamFrame({ schema: "releasefoundry.vm_stream.v1", seq: 0, timestamp: "2026-01-01T00:00:00.000Z", event_id: "evt", stream: "bad", status: "ok", text: "x", data: {} }), /unsupported VM stream/);
});

test("TS validateVmStreamFrame rejects negative seq", () => {
  assert.throws(() => validateVmStreamFrame({ schema: "releasefoundry.vm_stream.v1", seq: -1, timestamp: "2026-01-01T00:00:00.000Z", event_id: "evt", stream: "stdout", status: "ok", text: "x", data: {} }), /seq/);
});

test("TS traceEventsFromVmStream sorts frames by seq", () => {
  const recorder = new TraceRecorder({ runId: "run_trace_sort" });
  recorder.message("assistant", "second");
  recorder.message("assistant", "first");
  const frames = buildVmStream(recorder.events()).reverse();
  const events = traceEventsFromVmStream("run_trace_sort", frames);
  assert.deepEqual(events.map((event) => event.seq), [0, 1]);
});

test("TS TraceRecorder metric and control events roundtrip through VM stream", () => {
  const recorder = new TraceRecorder({ runId: "run_metric" });
  recorder.metric("latency", 12);
  recorder.control("lease.acquired", { worker: "w1" });
  const events = traceEventsFromVmStream("run_metric", buildVmStream(recorder.events()));
  assert.equal(events.length, 2);
  assert.deepEqual(events.map((event) => event.observation.kind), ["metric", "lifecycle"]);
});

test("TS buildTraceRunFixture rejects empty event lists", () => {
  assert.throws(() => buildTraceRunFixture({ name: "bad", runId: "run_bad", events: [] }), /at least one event/);
});

test("TS writeRunFixture writes trailing newline and loadRunFixture validates", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "releasefoundry-ts-trace-newline-"));
  try {
    const recorder = new TraceRecorder({ runId: "run_file" });
    recorder.message("assistant", "ok");
    const fixture = buildTraceRunFixture({ name: "file", runId: "run_file", events: recorder.events() });
    const path = join(tempDir, "fixture.json");
    await writeRunFixture(path, fixture);
    assert.equal((await readFile(path, "utf8")).endsWith("\n"), true);
    assert.equal((await loadRunFixture(path)).schema, "releasefoundry.run.v1");
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("TS validateRunFixture rejects missing replay object", () => {
  const recorder = new TraceRecorder({ runId: "run_missing_replay" });
  recorder.message("assistant", "ok");
  const fixture = buildTraceRunFixture({ name: "missing", runId: "run_missing_replay", events: recorder.events() });
  delete fixture.replay;
  assert.throws(() => validateRunFixture(fixture), /replay/);
});

test("TS datasetSourceToCases honors maxCases zero", () => {
  assert.deepEqual(datasetSourceToCases(sourceFixture(), { maxCases: 0, includeAgentlessRuns: true }), []);
});

test("TS datasetSourceToCases emits multiple agent actions deterministically", () => {
  const cases = datasetSourceToCases(sourceFixture());
  assert.deepEqual(cases.map((item) => item.case_id), ["alpha-run-a001", "alpha-run-a003"]);
});

test("TS datasetSourceToCases includes agentless run only when requested", () => {
  assert.equal(datasetSourceToCases(sourceFixture()).length, 2);
  assert.equal(datasetSourceToCases(sourceFixture(), { includeAgentlessRuns: true }).length, 3);
});

test("TS apiRecordToCases accepts response.dataset_source shape", () => {
  const cases = apiRecordToCases({ response: { dataset_source: sourceFixture() } }, { maxCases: 1 });
  assert.equal(cases.length, 1);
  assert.equal(cases[0].scenario_id, "alpha-run");
});

test("TS apiRecordToCases accepts response.dataset.dataset_source shape", () => {
  const cases = apiRecordToCases({ response: { dataset: { dataset_source: sourceFixture() } } }, { maxCases: 1 });
  assert.equal(cases.length, 1);
  assert.equal(cases[0].metadata.source, "releasefoundry_dataset_source");
});

test("TS extractDatasetSource rejects missing runs", () => {
  assert.throws(() => extractDatasetSource({ dataset_source: { total_runs: 1 } }), /runs/);
});

test("TS caseFromSourceRun selects second agent action by ordinal", () => {
  const item = caseFromSourceRun(sourceFixture().runs.alpha, { agentActionOrdinal: 1 });
  assert.equal(item.case_id, "alpha-run-a003");
  assert.equal(item.expected.tool_calls[0].name, "calendar");
});

test("TS caseFromSourceRun rejects out-of-range agent ordinal", () => {
  assert.throws(() => caseFromSourceRun(sourceFixture().runs.alpha, { agentActionOrdinal: 5 }), /requested agent action/);
});

test("TS replayFixtureFromSourceRun includes every source action as VM frame", () => {
  const fixture = replayFixtureFromSourceRun(sourceFixture().runs.alpha, { name: "alpha replay" });
  assert.equal(fixture.vm_stream.length, 4);
  assert.equal(fixture.events.length, 4);
  assert.equal(fixture.replay.metadata.releasefoundry_api_used, false);
});

test("TS writeRunFixture rejects malformed fixtures before write", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "releasefoundry-ts-bad-fixture-"));
  try {
    await assert.rejects(() => writeRunFixture(join(tempDir, "bad.json"), { schema: "wrong" }), /schema/);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});
