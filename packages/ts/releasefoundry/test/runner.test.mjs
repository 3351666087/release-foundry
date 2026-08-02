import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  AGENT_INPUT_SCHEMA_VERSION,
  AgentAdapter,
  AgentResult,
  BatchRunner,
  LocalEvalRunner,
  buildRunFixture,
  coerceRunnerAgentInput,
  runBatch,
  runCase,
  runAgentBatch,
  toA2JudgeRun,
} from "../dist/index.js";

test("AgentAdapter wraps callable and object agents with normalized tool calls", async () => {
  const callable = new AgentAdapter((message) => ({
    text: `Echo: ${message}`,
    tool_calls: [{ function: { name: "math", arguments: "{\"x\":1}" }, id: "call-1" }],
  }));
  const callableTurn = await callable.respond("hello");

  assert.equal(callableTurn.text, "Echo: hello");
  assert.equal(callableTurn.tool_calls[0].name, "math");
  assert.deepEqual(callableTurn.tool_calls[0].arguments, { x: 1 });
  assert.equal(callable.history.length, 1);

  const objectAgent = {
    resetCount: 0,
    reset() {
      this.resetCount += 1;
    },
    respond(input) {
      return new AgentResult({ text: `Object: ${input.text}`, metadata: { from: "object" } });
    },
  };
  const objectAdapter = new AgentAdapter(objectAgent, { inputStyle: "request" });
  assert.equal(await objectAdapter.reset(), true);
  const objectTurn = await objectAdapter.respondInput(coerceRunnerAgentInput("world"));

  assert.equal(objectAgent.resetCount, 1);
  assert.equal(objectTurn.text, "Object: world");
  assert.equal(objectTurn.metadata.from, "object");
});

test("runAgentBatch normalizes maxWorkers, records trace, and builds replay fixture", async () => {
  const cases = Array.from({ length: 6 }, (_, index) => ({
    id: `case-${index + 1}`,
    prompt: `hello ${index + 1}`,
    expected: { text: `Echo: hello ${index + 1}` },
  }));

  const result = await runAgentBatch(
    (message) => ({ text: `Echo: ${message}`, tool_calls: [{ name: "echo", arguments: { message } }] }),
    cases,
    { datasetId: "dataset_ts_runner", runnerId: "runner_ts", maxWorkers: 1, timeoutSeconds: 5, runId: "run_ts_runner" },
  );
  const fixture = buildRunFixture(result, { name: "TS Runner Fixture" });

  assert.equal(result.schema_version, "releasefoundry.run_result.v1");
  assert.equal(result.status, "passed");
  assert.equal(result.total_cases, 6);
  assert.equal(result.max_workers, 4);
  assert.equal(result.trace_completeness, 1);
  assert.equal(result.aggregate_metrics.total_tool_calls, 6);
  assert.equal(result.cases[0].observations.length, 2);
  assert.equal(fixture.schema, "releasefoundry.run.v1");
  assert.equal(fixture.events.length, 12);
  assert.ok(fixture.vm_stream.length >= 12);
  assert.equal(fixture.replay.metadata.releasefoundry_api_used, false);
});

test("runAgentBatch emits replayable timeout and redacted error cases", async () => {
  const timeoutResult = await runAgentBatch(
    () => new Promise((resolve) => setTimeout(() => resolve("too late"), 40)),
    [{ id: "slow", prompt: "wait" }],
    { runId: "run_timeout", timeoutSeconds: 0.001 },
  );
  assert.equal(timeoutResult.status, "completed_with_errors");
  assert.equal(timeoutResult.timed_out, 1);
  assert.equal(timeoutResult.trace_completeness, 1);
  assert.equal(timeoutResult.cases[0].observations[1].vm_stream.metadata.failure, "timeout");

  const errorResult = await runAgentBatch(
    () => {
      throw new Error("bad token Bearer should-not-leak");
    },
    [{ id: "error", prompt: "explode" }],
    { runId: "run_error", timeoutSeconds: 5 },
  );
  assert.equal(errorResult.errored, 1);
  assert.equal(errorResult.trace_completeness, 1);
  assert.equal(errorResult.cases[0].agent_output.error.message.includes("should-not-leak"), false);
});

test("request input style preserves Text/Audio/File/Image/Video parts for agent adapters", async () => {
  const seenInputs = [];
  const mediaAgent = {
    respond(input) {
      seenInputs.push(input);
      return { text: `parts:${input.parts.map((part) => part.type).join(",")}` };
    },
  };
  const result = await runAgentBatch(
    mediaAgent,
    [
      {
        id: "media",
        input: {
          schema_version: AGENT_INPUT_SCHEMA_VERSION,
          text: "inspect media",
          parts: [
            { type: "text", text: "inspect media" },
            { type: "image", path: "fixtures/image.png", mimeType: "image/png" },
            { type: "audio", path: "fixtures/audio.wav", mime_type: "audio/wav" },
            { type: "file", path: "fixtures/data.json", mime_type: "application/json" },
            { type: "video", path: "fixtures/clip.mp4", mime_type: "video/mp4" },
          ],
        },
        expected: { text: "parts:text,image,audio,file,video" },
      },
    ],
    { inputStyle: "request", runId: "run_media" },
  );

  assert.equal(result.passed, 1);
  assert.equal(seenInputs[0].schema_version, AGENT_INPUT_SCHEMA_VERSION);
  assert.equal(seenInputs[0].parts[1].mime_type, "image/png");
  assert.deepEqual(seenInputs[0].parts.map((part) => part.type), ["text", "image", "audio", "file", "video"]);
});

test("LocalEvalRunner convenience class returns A3-consumable run results", async () => {
  const runner = new LocalEvalRunner({
    agent: { respond: (message) => `Echo: ${message}` },
    datasetId: "dataset_local_eval",
    runnerId: "runner_local_eval",
    runId: "run_local_eval",
    maxWorkers: 2,
  });
  const result = await runner.run([{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }]);

  assert.equal(result.run_id, "run_local_eval");
  assert.equal(result.max_workers, 4);
  assert.equal(result.passed, 1);
  assert.equal(result.metadata.local_only, true);
});

test("releasefoundry-runner CLI writes run result and fixture", () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-ts-runner-"));
  try {
    const agentPath = join(temp, "agent.mjs");
    const inputPath = join(temp, "cases.json");
    const outputPath = join(temp, "run.json");
    const fixturePath = join(temp, "fixture.json");
    writeFileSync(
      agentPath,
      "export default { respond(message) { return { text: `Echo: ${message}`, tool_calls: [{ name: 'cli_tool', arguments: { ok: true } }] }; } };\n",
      "utf8",
    );
    writeFileSync(inputPath, JSON.stringify({ cases: [{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }] }), "utf8");

    const child = spawnSync(
      process.execPath,
      [
        "dist/runner-cli.js",
        "--input",
        inputPath,
        "--output",
        outputPath,
        "--agent",
        `${agentPath}:default`,
        "--dataset-id",
        "dataset_cli",
        "--runner-id",
        "runner_cli",
        "--run-id",
        "run_cli",
        "--max-workers",
        "1",
        "--timeout",
        "5",
        "--fixture-output",
        fixturePath,
        "--fail-on-case-failure",
      ],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(child.status, 0, child.stderr);
    const stdout = JSON.parse(child.stdout);
    const result = JSON.parse(readFileSync(outputPath, "utf8"));
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    assert.equal(stdout.status, "passed");
    assert.equal(result.run_id, "run_cli");
    assert.equal(result.max_workers, 4);
    assert.equal(fixture.run.run_id, "run_cli");
    assert.equal(existsSync(fixturePath), true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("runCase, runBatch, BatchRunner, and toA2JudgeRun mirror Python helper surface", async () => {
  const single = await runCase({ id: "literal", input: 42, expected: 42 });
  const batch = await runBatch([
    { id: "pass", input: "ok", expected: "ok" },
    { id: "fail", input: "no", expected: "yes" },
  ], { maxWorkers: 1 });
  const classRunner = new BatchRunner({ maxWorkers: 2 });
  const classResult = await classRunner.run([{ id: "class-pass", output: "done", expected: "done" }]);
  const judgeRun = toA2JudgeRun({
    text: "final",
    tool_calls: [{ name: "search", arguments: { q: "releasefoundry" }, id: "tool-1" }],
  }, { expectedKeywords: ["final"] });

  assert.equal(single.status, "passed");
  assert.equal(batch.max_workers, 4);
  assert.equal(batch.summary.passed, 1);
  assert.equal(batch.summary.failed, 1);
  assert.equal(classResult.summary.passed, 1);
  assert.equal(judgeRun.final_response, "final");
  assert.equal(judgeRun.tool_calls[0].tool, "search");
  assert.deepEqual(judgeRun.tool_calls[0].args, { q: "releasefoundry" });
  assert.deepEqual(judgeRun.expected_keywords, ["final"]);
});
