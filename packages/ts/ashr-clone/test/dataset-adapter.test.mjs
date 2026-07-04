import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  DATASET_SOURCE_ADAPTER_VERSION,
  apiRecordToCases,
  caseFromSourceRun,
  datasetSourceToCases,
  extractDatasetSource,
  loadCasesFromApiRecord,
  replayFixtureFromSourceRun,
  writeCases,
} from "../dist/index.js";

function sampleDatasetSource() {
  return {
    dataset_type: "voice",
    total_runs: 2,
    runs: {
      run_one: {
        run_id: "hosted-run-1",
        title: "Book a table",
        intent: "Reserve dinner",
        intent_tags: ["booking"],
        audio_tags: ["clear"],
        actions: [
          { actor: "user", name: "start", content: "Need a table tonight" },
          {
            actor: "agent",
            name: "respond",
            action_type: "message",
            content: "What time should I book?",
            expected_response: {
              text: "What time should I book?",
              tool_calls: [{ name: "calendar", arguments_json: "{\"day\":\"today\"}" }],
            },
          },
        ],
      },
      run_two: {
        run_id: "hosted-run-2",
        title: "Agentless",
        actions: [{ actor: "user", content: "hello" }],
      },
    },
  };
}

test("datasetSourceToCases maps hosted agent actions into runner cases", () => {
  const cases = datasetSourceToCases(sampleDatasetSource(), { includeAgentlessRuns: true });

  assert.equal(cases.length, 2);
  assert.equal(cases[0].case_id, "hosted-run-1-a001");
  assert.equal(cases[0].scenario_id, "hosted-run-1");
  assert.equal(cases[0].expected.text, "What time should I book?");
  assert.deepEqual(cases[0].expected.tool_calls, [{ name: "calendar", arguments: { day: "today" } }]);
  assert.equal(cases[0].metadata.adapter_version, DATASET_SOURCE_ADAPTER_VERSION);
  assert.equal(cases[0].metadata.requires_external_judge, false);
  assert.equal(cases[1].metadata.requires_external_judge, true);
});

test("caseFromSourceRun selects requested agent action and validates indexes", () => {
  const run = sampleDatasetSource().runs.run_one;
  const caseRecord = caseFromSourceRun(run, { agentActionOrdinal: 0 });

  assert.equal(caseRecord.title, "Book a table / respond");
  assert.match(caseRecord.prompt, /Conversation so far/);
  assert.throws(() => caseFromSourceRun(run, { actionIndex: 0 }), /not an agent action/);
});

test("api records extract dataset_source and load/write public-safe case files", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-dataset-"));
  try {
    const input = join(temp, "record.json");
    const output = join(temp, "cases.json");
    const record = { response: { dataset: { dataset_source: sampleDatasetSource() } } };
    await import("node:fs/promises").then((fs) => fs.writeFile(input, `${JSON.stringify(record)}\n`, "utf8"));

    assert.equal(extractDatasetSource(record).total_runs, 2);
    assert.equal(apiRecordToCases(record, { maxCases: 1 }).length, 1);
    const loaded = await loadCasesFromApiRecord(input);
    await writeCases(output, loaded);
    const written = JSON.parse(readFileSync(output, "utf8"));

    assert.equal(loaded.length, 1);
    assert.equal(written.adapter_version, DATASET_SOURCE_ADAPTER_VERSION);
    assert.equal(written.cases[0].metadata.source, "ashr_dataset_source");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("replayFixtureFromSourceRun produces A3 replay-style trace and VM frames", () => {
  const fixture = replayFixtureFromSourceRun(sampleDatasetSource().runs.run_one, { name: "source replay" });

  assert.equal(fixture.schema, "ashr.clone.run_fixture.v1");
  assert.equal(fixture.name, "source replay");
  assert.equal(fixture.labels.includes("ashr-dataset-source"), true);
  assert.ok(fixture.events.length >= 2);
  assert.ok(fixture.vm_stream.length >= 2);
  assert.equal(fixture.replay.metadata.adapter_version, DATASET_SOURCE_ADAPTER_VERSION);
  assert.equal(fixture.replay.metadata.ashr_api_used, false);
});

test("dataset adapter CLI writes cases and replay fixtures", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-dataset-cli-"));
  try {
    const input = join(temp, "record.json");
    const casesOutput = join(temp, "cases.json");
    const fixtureOutput = join(temp, "fixture.json");
    const record = { response: { dataset: { dataset_source: sampleDatasetSource() } } };
    await import("node:fs/promises").then((fs) => fs.writeFile(input, `${JSON.stringify(record)}\n`, "utf8"));

    const casesChild = spawnSync(
      process.execPath,
      ["dist/dataset-adapter-cli.js", "cases", "--input", input, "--output", casesOutput, "--max-cases", "1"],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );
    const fixtureChild = spawnSync(
      process.execPath,
      ["dist/dataset-adapter-cli.js", "replay-fixture", "--input", input, "--output", fixtureOutput, "--run-key", "run_one"],
      { cwd: new URL("../", import.meta.url), encoding: "utf8" },
    );

    assert.equal(casesChild.status, 0, casesChild.stderr);
    assert.equal(fixtureChild.status, 0, fixtureChild.stderr);
    assert.equal(JSON.parse(readFileSync(casesOutput, "utf8")).cases.length, 1);
    assert.equal(JSON.parse(readFileSync(fixtureOutput, "utf8")).schema, "ashr.clone.run_fixture.v1");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
