import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  TraceRecorder,
  buildCloudRunFixture,
  buildRunFixture,
  buildTraceRunFixture,
  runAgentBatch,
} from "../dist/index.js";

const packageDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(packageDir, "..", "..", "..", "..");
const schemaDir = join(repoRoot, "docs", "a1", "schemas");

const schemas = new Map();

function loadSchema(name) {
  if (!schemas.has(name)) {
    schemas.set(name, JSON.parse(readFileSync(join(schemaDir, name), "utf8")));
  }
  return schemas.get(name);
}

test("TS run result satisfies A1 RunResult JSON schema", async () => {
  const run = await sampleRunResult();
  validateSchema(run, loadSchema("run_result.schema.json"), "run_result");
});

test("TS runner fixture satisfies A1 run fixture JSON schema", async () => {
  const run = await sampleRunResult();
  const fixture = buildRunFixture(run, { name: "TS schema fixture" });

  validateSchema(fixture, loadSchema("run_fixture.schema.json"), "run_fixture");
});

test("TS trace fixture satisfies A1 run fixture JSON schema", () => {
  const recorder = new TraceRecorder({ runId: "run_trace_schema", source: "schema-test" });
  recorder.control("run.started");
  recorder.message("assistant", "ok");
  const fixture = buildTraceRunFixture({
    name: "TS trace schema fixture",
    runId: "run_trace_schema",
    datasetId: "dataset_trace_schema",
    runnerId: "runner_trace_schema",
    events: recorder.events(),
  });

  validateSchema(fixture, loadSchema("run_fixture.schema.json"), "trace_run_fixture");
});

test("Python A1 loader accepts TS-generated run fixture", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-python-fixture-"));
  try {
    const run = await sampleRunResult();
    const fixture = buildRunFixture(run, { name: "TS to Python fixture" });
    const fixturePath = join(temp, "fixture.json");
    writeFileSync(fixturePath, JSON.stringify(fixture, null, 2), "utf8");
    const child = spawnSync(
      "python",
      [
        "-B",
        "-c",
        "import json, sys; from pathlib import Path; from packages.sdk.ashr_clone.trace import load_run_fixture; fixture=load_run_fixture(Path(sys.argv[1])); print(json.dumps({'schema': fixture['schema'], 'events': len(fixture['events']), 'vm_stream': len(fixture['vm_stream'])}, sort_keys=True))",
        fixturePath,
      ],
      { cwd: repoRoot, encoding: "utf8" },
    );

    assert.equal(child.status, 0, child.stderr);
    const summary = JSON.parse(child.stdout);
    assert.equal(summary.schema, "ashr.clone.run.v1");
    assert.equal(summary.events, fixture.events.length);
    assert.equal(summary.vm_stream, fixture.vm_stream.length);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("TS cloud fixture satisfies local cloud API schema envelope", async () => {
  const run = await sampleRunResult();
  const fixture = buildCloudRunFixture(run, { tenantId: "tenant_schema", projectId: "project_schema" });

  validateSchema(fixture, loadSchema("cloud_api.schema.json"), "cloud_fixture");
  assert.equal(fixture.run_result.run_id, run.run_id);
  assert.equal(fixture.observations.length, 2);
});

async function sampleRunResult() {
  return runAgentBatch(
    (message) => ({ text: `Echo: ${message}`, tool_calls: [{ name: "echo", arguments: { message } }] }),
    [{ id: "case-1", prompt: "hello", expected: { text: "Echo: hello" } }],
    { datasetId: "dataset_schema", runnerId: "runner_schema", runId: "run_schema", maxWorkers: 4, timeoutSeconds: 5 },
  );
}

function validateSchema(value, schema, path) {
  if (schema.$ref) {
    return validateSchema(value, loadSchema(schema.$ref), path);
  }
  if (schema.const !== undefined) {
    assert.deepEqual(value, schema.const, `${path} const mismatch`);
  }
  if (schema.enum !== undefined) {
    assert.equal(schema.enum.includes(value), true, `${path} enum mismatch: ${String(value)}`);
  }
  if (schema.type !== undefined) {
    validateType(value, schema.type, path);
  }
  if (schema.minimum !== undefined && typeof value === "number") {
    assert.equal(value >= schema.minimum, true, `${path} below minimum`);
  }
  if (schema.maximum !== undefined && typeof value === "number") {
    assert.equal(value <= schema.maximum, true, `${path} above maximum`);
  }
  if (schema.type === "object" || isRecord(value)) {
    if (schema.required) {
      for (const key of schema.required) {
        assert.equal(Object.prototype.hasOwnProperty.call(value, key), true, `${path}.${key} missing`);
      }
    }
    const properties = schema.properties ?? {};
    for (const [key, childSchema] of Object.entries(properties)) {
      if (Object.prototype.hasOwnProperty.call(value, key)) {
        validateSchema(value[key], childSchema, `${path}.${key}`);
      }
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        assert.equal(Object.prototype.hasOwnProperty.call(properties, key), true, `${path}.${key} unexpected`);
      }
    }
  }
  if (schema.type === "array" || Array.isArray(value)) {
    if (schema.minItems !== undefined) {
      assert.equal(value.length >= schema.minItems, true, `${path} has too few items`);
    }
    if (schema.items) {
      value.forEach((item, index) => validateSchema(item, schema.items, `${path}[${index}]`));
    }
  }
}

function validateType(value, type, path) {
  const types = Array.isArray(type) ? type : [type];
  const ok = types.some((item) => {
    if (item === "null") return value === null;
    if (item === "array") return Array.isArray(value);
    if (item === "object") return isRecord(value);
    if (item === "integer") return Number.isInteger(value);
    if (item === "number") return typeof value === "number" && Number.isFinite(value);
    if (item === "string") return typeof value === "string";
    if (item === "boolean") return typeof value === "boolean";
    return true;
  });
  assert.equal(ok, true, `${path} type mismatch; expected ${types.join("|")}`);
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
