import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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

function writePlanBatchGate(path, decision = "go", options = {}) {
  const targetOperation = options.targetOperation ?? "create-run";
  const createdAt = options.createdAt ?? new Date().toISOString();
  const request = options.request ?? { agent: { accepted_inputs: { text: true } }, test_config: { num_variations: 1 } };
  const targetBinding = targetOperation === "create-request" ? buildTestTargetBinding(targetOperation, request, options) : undefined;
  writeFileSync(
    path,
    JSON.stringify({
      schema_version: "ashr.clone.api_probe_batch_plan.v1",
      function: "plan_batch",
      response: {
        plan: {
          schema_version: "ashr.clone.api_probe_batch_plan.v1",
          target_operation: targetOperation,
          created_at: createdAt,
          ...(targetBinding ? { target_binding: targetBinding } : {}),
          small_batch_size: options.smallBatchSize ?? 1,
          batch_size: options.batchSize ?? inferBatchSize(request, options.smallBatchSize ?? 1),
          quota_stop_go: {
            decision,
            source: "unit-test",
            quota_or_reset_evidence_present: true,
            reset: { known: false, wait_hint_present: false, header_keys: ["x-ratelimit-remaining"] },
            can_enter_small_batch: decision === "go",
            can_enter_batch: decision === "go",
          },
          phases: [
            { phase: "dry-run", batch_size: 0, estimated_real_api_calls: 0 },
            { phase: "small-batch", batch_size: 1, estimated_real_api_calls: 2 },
          ],
        },
      },
    }),
    "utf8",
  );
}

function buildTestTargetBinding(targetOperation, request, options = {}) {
  const smallBatchSize = options.smallBatchSize ?? 1;
  const batchSize = options.batchSize ?? inferBatchSize(request, smallBatchSize);
  const modalities = modalityOrder(request);
  const components = {
    target_operation: targetOperation,
    request_fingerprint: stableSha256(request),
    request_input_schema_fingerprint: options.requestInputSchema ? stableSha256(options.requestInputSchema) : null,
    request_input_schema_source: options.requestInputSchema ? "file" : "client_default",
    allow_media_generation: options.allowMediaGeneration ?? false,
    allow_non_text_inputs: options.allowNonTextInputs ?? false,
    max_request_variations: options.maxRequestVariations ?? 1,
    small_batch_size: smallBatchSize,
    batch_size: batchSize,
    modalities,
  };
  return {
    schema_version: "ashr.clone.api_probe_target_binding.v1",
    target_operation: targetOperation,
    binding_scope: "request-payload",
    request_fingerprint: components.request_fingerprint,
    request_input_schema_fingerprint: components.request_input_schema_fingerprint,
    request_input_schema_source: components.request_input_schema_source,
    allow_media_generation: components.allow_media_generation,
    allow_non_text_inputs: components.allow_non_text_inputs,
    max_request_variations: components.max_request_variations,
    small_batch_size: smallBatchSize,
    batch_size: batchSize,
    modalities,
    fingerprint: stableSha256(components),
    fingerprint_fields: Object.keys(components).sort(),
    raw_request_not_recorded: true,
  };
}

function inferBatchSize(request, smallBatchSize) {
  const variations = request?.test_config?.num_variations ?? request?.num_variations;
  return Number.isSafeInteger(variations) ? Math.max(smallBatchSize, variations) : Math.max(smallBatchSize, 2);
}

function modalityOrder(request) {
  const accepted = request?.agent?.accepted_inputs ?? {};
  const generation = request?.generation_options ?? {};
  const enabled = new Set();
  for (const modality of ["text", "image", "audio", "file", "video", "conversation"]) {
    const value = accepted[modality];
    if (value === true || value?.enabled === true) {
      enabled.add(modality);
    }
  }
  if (generation.generate_images === true) enabled.add("image");
  if (generation.generate_audio === true) enabled.add("audio");
  if (generation.generate_files === true) enabled.add("file");
  if (generation.generate_videos === true) enabled.add("video");
  if (generation.generate_simulations === true) enabled.add("simulation");
  if (enabled.size === 0) enabled.add("text");
  return ["text", "image", "audio", "file", "video", "conversation", "simulation"].filter((modality) => enabled.has(modality));
}

function stableSha256(value) {
  return `sha256:${createHash("sha256").update(JSON.stringify(canonicalValue(value))).digest("hex")}`;
}

function canonicalValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => canonicalValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  }
  return value;
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
  const gateFile = join(temp, "quota-go.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writePlanBatchGate(gateFile, "go");

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

    const missingGate = captureStreams();
    assert.equal(
      await main(
        ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--output", join(temp, "missing-key-default.json")],
        {},
        missingGate.streams,
      ),
      2,
    );
    assert.match(missingGate.stderr, /--quota-gate-record/);
    assert.doesNotMatch(missingGate.stderr, new RegExp(ASHR_API_ENV_VAR));

    const missingKeyWithOutput = captureStreams();
    const missingKeyOutput = join(temp, "missing-key.json");
    assert.equal(
      await main(
        ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", missingKeyOutput],
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

test("probe CLI rejects read-only quota gate records before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const gateFile = join(temp, "read-only-record.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writeFileSync(
      gateFile,
      JSON.stringify({
        schema_version: "ashr.clone.api_probe_batch_plan.v1",
        function: "list_requests",
        response: { plan: { quota_stop_go: { decision: "go" } } },
      }),
      "utf8",
    );

    const capture = captureStreams();
    const code = await main(
      ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", join(temp, "blocked.json")],
      {},
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /plan-batch record/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI rejects go quota gate records without quota evidence", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const gateFile = join(temp, "go-without-evidence.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writeFileSync(
      gateFile,
      JSON.stringify({
        schema_version: "ashr.clone.api_probe_batch_plan.v1",
        function: "plan_batch",
        response: { plan: { schema_version: "ashr.clone.api_probe_batch_plan.v1", quota_stop_go: { decision: "go", source: "not-provided" } } },
      }),
      "utf8",
    );

    const capture = captureStreams();
    const code = await main(
      ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", join(temp, "blocked.json")],
      {},
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /requires reviewed quota\/reset evidence/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI blocks stop quota gate before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const gateFile = join(temp, "quota-stop.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writePlanBatchGate(gateFile, "stop");

    const capture = captureStreams();
    const code = await main(
      ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", join(temp, "blocked.json")],
      {},
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /quota gate decision=stop/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI blocks stale quota gate before key lookup unless TTL is disabled", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const gateFile = join(temp, "quota-stale.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writePlanBatchGate(gateFile, "go", { createdAt: "2000-01-01T00:00:00Z" });

    const staleCapture = captureStreams();
    const staleCode = await main(
      ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", join(temp, "stale.json")],
      {},
      staleCapture.streams,
    );

    assert.equal(staleCode, 2);
    assert.match(staleCapture.stderr, /stale/);
    assert.doesNotMatch(staleCapture.stderr, new RegExp(ASHR_API_ENV_VAR));

    const ttlDisabledCapture = captureStreams();
    const ttlDisabledCode = await main(
      [
        "create-run",
        "--execute",
        "--allow-mutate",
        "--max-retries",
        "0",
        "--dataset-id",
        "1",
        "--result-file",
        resultFile,
        "--quota-gate-record",
        gateFile,
        "--quota-gate-ttl-seconds",
        "0",
        "--output",
        join(temp, "ttl-disabled.json"),
      ],
      {},
      ttlDisabledCapture.streams,
    );

    assert.equal(ttlDisabledCode, 2);
    assert.match(ttlDisabledCapture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI blocks wrong quota gate target before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const gateFile = join(temp, "quota-wrong-target.json");
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");
    writePlanBatchGate(gateFile, "go", { targetOperation: "create-request" });

    const capture = captureStreams();
    const code = await main(
      ["create-run", "--execute", "--allow-mutate", "--max-retries", "0", "--dataset-id", "1", "--result-file", resultFile, "--quota-gate-record", gateFile, "--output", join(temp, "wrong-target.json")],
      {},
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /target_operation/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI blocks same-operation wrong request binding before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const requestFile = join(temp, "request.json");
  const gateFile = join(temp, "quota-wrong-request.json");
  try {
    const originalRequest = { agent: { name: "original", accepted_inputs: { text: true } }, test_config: { num_variations: 1 } };
    const changedRequest = { agent: { name: "changed", accepted_inputs: { text: true } }, test_config: { num_variations: 1 } };
    writeFileSync(requestFile, JSON.stringify(changedRequest), "utf8");
    writePlanBatchGate(gateFile, "go", { targetOperation: "create-request", request: originalRequest });

    const capture = captureStreams();
    const code = await main(
      [
        "create-request",
        "--execute",
        "--allow-mutate",
        "--max-retries",
        "0",
        "--request-name",
        "Wrong binding",
        "--request-file",
        requestFile,
        "--quota-gate-record",
        gateFile,
        "--output",
        join(temp, "wrong-binding.json"),
      ],
      {},
      capture.streams,
    );

    assert.equal(code, 2);
    assert.match(capture.stderr, /target_binding\.fingerprint/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI persists audited quota override reason when evidence is emitted", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const resultFile = join(temp, "result.json");
  const output = join(temp, "override-missing-key.json");
  const reason = "manual paid calibration approved after quota review";
  try {
    writeFileSync(resultFile, JSON.stringify({ status: "passed" }), "utf8");

    const capture = captureStreams();
    const code = await main(
      [
        "create-run",
        "--execute",
        "--allow-mutate",
        "--max-retries",
        "0",
        "--dataset-id",
        "1",
        "--result-file",
        resultFile,
        "--allow-quota-override",
        "--quota-override-reason",
        reason,
        "--output",
        output,
      ],
      {},
      capture.streams,
    );
    const record = readJson(output);

    assert.equal(code, 2);
    assert.match(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
    assert.equal(record.request.quota_gate.decision, "override");
    assert.equal(record.request.quota_gate.override.used, true);
    assert.equal(record.request.quota_gate.override.reason, reason);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("probe CLI create-request execute preflight blocks unsafe media before transport", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-probe-"));
  const requestFile = join(temp, "request.json");
  const gateFile = join(temp, "quota-go.json");
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
    writePlanBatchGate(gateFile, "go", {
      targetOperation: "create-request",
      request: {
        agent: { accepted_inputs: { text: true } },
        generation_options: { generate_images: true },
        test_config: { num_variations: 1 },
      },
    });
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
        "--quota-gate-record",
        gateFile,
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
