import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  TraceRecorder,
  TraceValidationError,
  buildTraceRunFixture,
  buildVmStream,
  loadRunFixture,
  traceEventsFromVmStream,
  validateRunFixture,
  validateTraceEvent,
  validateVmStreamFrame,
  writeRunFixture,
} from "../dist/index.js";

test("TraceRecorder builds strict events and VM stream frames", () => {
  const recorder = new TraceRecorder({ runId: "run_trace", source: "test" });
  recorder.message("user", "hello");
  recorder.toolCall("calculator", { expression: "19 + 23" }, { callId: "call-1", output: { value: 42 } });
  recorder.metric("score", 1);

  const events = recorder.events();
  const frames = buildVmStream(events, { provider: "test-provider" });

  assert.equal(events.length, 3);
  assert.equal(validateTraceEvent(events[0]).schema, "ashr.clone.trace.v1");
  assert.equal(validateVmStreamFrame(frames[0]).schema, "ashr.clone.vm_stream.v1");
  assert.equal(frames[0].stream, "stdin");
  assert.equal(traceEventsFromVmStream("run_trace", frames).length, 3);
});

test("validateRunFixture rejects malformed traces and accepts generated fixture", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-trace-"));
  try {
    const recorder = new TraceRecorder({ runId: "run_fixture" });
    recorder.control("run.started");
    recorder.message("assistant", "ok");
    const fixture = buildTraceRunFixture({
      name: "TS trace fixture",
      runId: "run_fixture",
      datasetId: "dataset_trace",
      runnerId: "runner_trace",
      events: recorder.events(),
      expected: { status: "ok" },
    });
    const path = join(temp, "fixture.json");
    await writeRunFixture(path, fixture);
    const loaded = await loadRunFixture(path);

    assert.equal(validateRunFixture(fixture).schema, "ashr.clone.run.v1");
    assert.equal(loaded.run.run_id, "run_fixture");
    assert.throws(() => validateRunFixture({ ...fixture, vm_stream: [{ bad: true }] }), TraceValidationError);
    assert.throws(() => validateTraceEvent({ ...fixture.events[0], observation: "bad" }), TraceValidationError);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
