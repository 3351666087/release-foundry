import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ASHR_API_ENV_VAR, ASHR_LABS_API_ENV_VAR } from "../dist/index.js";
import { main } from "../dist/probe.js";

function captureStreams() {
  let stdout = "";
  let stderr = "";
  return {
    streams: {
      stdout: {
        write(chunk) {
          stdout += String(chunk);
          return true;
        },
      },
      stderr: {
        write(chunk) {
          stderr += String(chunk);
          return true;
        },
      },
    },
    get stdout() {
      return stdout;
    },
    get stderr() {
      return stderr;
    },
  };
}

function parseStdoutJson(capture) {
  assert.equal(capture.stderr, "");
  return JSON.parse(capture.stdout);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("probe CLI dry-run init writes JSON and does not call fetch", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const output = join(temp, "init.json");
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    const capture = captureStreams();
    const code = await main(["init", "--output", output], {}, capture.streams);
    const record = readJson(output);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.match(capture.stdout, /function=init/);
    assert.doesNotMatch(capture.stdout, /"response"/);
    assert.equal(record.status, "planned");
    assert.equal(record.dry_run, true);
    assert.equal(record.attempts, 0);
    assert.equal(record.request.function, "init");
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI writes JSON to output file and prints summary by default", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  try {
    const output = join(temp, "nested", "probe.json");
    const capture = captureStreams();
    const code = await main(["list-agents", "--output", output], {}, capture.streams);
    const fileRecord = readJson(output);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.match(capture.stdout, /function=list_agents status=planned dry_run=true/);
    assert.doesNotMatch(capture.stdout, /"request"/);
    assert.equal(fileRecord.request.function, "list_agents");
    assert.equal(fileRecord.output_path, output);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI prints full JSON only with --print-record", async () => {
  const capture = captureStreams();
  const code = await main(["health-check", "--output", "-", "--print-record"], {}, capture.streams);
  const record = parseStdoutJson(capture);

  assert.equal(code, 0);
  assert.equal(record.request.function, "keep_alive");
  assert.equal(record.output_path, undefined);
});

test("probe CLI dry-run supports read-only parity operations without a key", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  const cases = [
    ["health-check", "keep_alive", []],
    ["list-agents", "list_agents", []],
    ["list-datasets", "list_datasets", []],
    ["list-runs", "list_runs", []],
    ["list-requests", "list_requests", []],
    ["get-run", "get_run", ["--run-id", "12"]],
    ["poll-run", "poll_run", ["--run-id", "12", "--poll-timeout", "3", "--poll-interval", "1"]],
    ["get-request", "get_request", ["--request-id", "34"]],
    ["poll-request", "poll_request", ["--request-id", "34", "--poll-timeout", "3", "--poll-interval", "1"]],
  ];
  try {
    for (const [operation, functionName, extraArgs] of cases) {
      const capture = captureStreams();
      const code = await main([operation, ...extraArgs, "--output", "-", "--print-record"], {}, capture.streams);
      const record = parseStdoutJson(capture);

      assert.equal(code, 0);
      assert.equal(record.status, "planned");
      assert.equal(record.dry_run, true);
      assert.equal(record.request.function, functionName);
    }
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("probe CLI create-request dry-run records safe preflight and shape summaries", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const requestFile = join(temp, "request.json");
  try {
    writeFileSync(
      requestFile,
      JSON.stringify({
        agent: { name: "media-agent", accepted_inputs: { text: true, image: true } },
        generation_options: { generate_images: true },
        test_config: { num_variations: 1 },
      }),
      "utf8",
    );
    const capture = captureStreams();
    const code = await main(["create-request", "--request-name", "Tiny calibration", "--request-file", requestFile, "--output", "-", "--print-record"], {}, capture.streams);
    const record = parseStdoutJson(capture);

    assert.equal(code, 0);
    assert.equal(record.status, "planned");
    assert.equal(record.request.function, "create_request");
    assert.equal(record.request.mutates, true);
    assert.equal(record.request.preflight.media_generation_enabled, true);
    assert.equal(record.request.preflight.request_input_schema_source, "client_default");
    assert.equal(record.request.params.request.agent_name_present, true);
    assert.equal(record.request.params.request.accepted_input_flags.image, true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI create-run dry-run records a mutating plan without a key", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed", total_cases: 1 }), "utf8");
    const capture = captureStreams();
    const code = await main(["create-run", "--dataset-id", "7", "--result-file", resultFile, "--output", "-", "--print-record"], {}, capture.streams);
    const record = parseStdoutJson(capture);

    assert.equal(code, 0);
    assert.equal(record.status, "planned");
    assert.equal(record.request.function, "create_run");
    assert.equal(record.request.mutates, true);
    assert.equal(record.request.params.dataset_id, 7);
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI non-dry-run requires a key before read-only transport", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const output = join(temp, "missing-key.json");
  const capture = captureStreams();
  try {
    const code = await main(["health-check", "--execute", "--output", output], {}, capture.streams);

    assert.equal(code, 2);
    assert.equal(capture.stdout, "");
    assert.match(capture.stderr, new RegExp(`${ASHR_API_ENV_VAR}.*${ASHR_LABS_API_ENV_VAR}`));
    const record = readJson(output);
    assert.equal(record.status, "error");
    assert.equal(record.error.error_kind, "auth");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI mutating execute guardrails run before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");

    const missingAllow = captureStreams();
    assert.equal(await main(["create-run", "--execute", "--dataset-id", "1", "--result-file", resultFile, "--output", join(temp, "missing-allow.json")], {}, missingAllow.streams), 2);
    assert.match(missingAllow.stderr, /--allow-mutate/);
    assert.doesNotMatch(missingAllow.stderr, new RegExp(ASHR_API_ENV_VAR));

    const retryGuard = captureStreams();
    assert.equal(
      await main(["create-run", "--execute", "--allow-mutate", "--dataset-id", "1", "--result-file", resultFile, "--output", join(temp, "retry-guard.json")], {}, retryGuard.streams),
      2,
    );
    assert.match(retryGuard.stderr, /--max-retries 0/);
    assert.doesNotMatch(retryGuard.stderr, new RegExp(ASHR_API_ENV_VAR));

    const missingKey = captureStreams();
    assert.equal(
      await main(
        ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--output", join(temp, "missing-key-default.json")],
        {},
        missingKey.streams,
      ),
      2,
    );
    assert.match(missingKey.stderr, new RegExp(ASHR_API_ENV_VAR));

    const missingKeyWithOutput = captureStreams();
    const missingKeyOutput = join(temp, "missing-key.json");
    assert.equal(
      await main(
        ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--output", missingKeyOutput],
        {},
        missingKeyWithOutput.streams,
      ),
      2,
    );
    assert.equal(readJson(missingKeyOutput).status, "error");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI create-request execute preflight blocks unsafe media before transport", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const requestFile = join(temp, "request.json");
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    writeFileSync(
      requestFile,
      JSON.stringify({
        agent: { accepted_inputs: { text: true } },
        generation_options: { generate_images: true },
        test_config: { num_variations: 1 },
      }),
      "utf8",
    );
    const capture = captureStreams();
    const output = join(temp, "media-blocked.json");
    const code = await main(
      [
        "create-request",
        "--execute",
        "--allow-mutate",
        "--max-retries",
        "0",
        "--request-name",
        "Media blocked",
        "--request-file",
        requestFile,
        "--output",
        output,
      ],
      { [ASHR_API_ENV_VAR]: "tp_syntheticsecret" },
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /enables media generation/);
    assert.equal(fetchCalled, false);
    assert.equal(readJson(output).status, "error");
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});
