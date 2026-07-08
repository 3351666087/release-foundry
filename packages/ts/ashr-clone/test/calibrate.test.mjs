import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ASHR_API_ENV_VAR } from "../dist/index.js";
import { main } from "../dist/calibrate.js";

function captureStreams() {
  let stdout = "";
  let stderr = "";
  return {
    streams: {
      stdout: { write(chunk) { stdout += String(chunk); return true; } },
      stderr: { write(chunk) { stderr += String(chunk); return true; } },
    },
    get stdout() { return stdout; },
    get stderr() { return stderr; },
  };
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writePlanBatchGate(path, decision = "go", options = {}) {
  const plan = {
    schema_version: "ashr.clone.api_probe_batch_plan.v1",
    target_operation: options.targetOperation ?? "create-request",
    created_at: options.createdAt ?? new Date().toISOString(),
    quota_stop_go: {
      decision,
      source: "unit-test",
      quota_or_reset_evidence_present: true,
      reset: { known: false, wait_hint_present: false, header_keys: ["x-ratelimit-remaining"] },
      can_enter_small_batch: decision === "go",
      can_enter_batch: decision === "go",
    },
  };
  if (options.modalities !== undefined) {
    plan.modalities = options.modalities;
  }
  if (options.requestFingerprint !== undefined) {
    plan.request_fingerprint = options.requestFingerprint;
  }
  writeFileSync(
    path,
    JSON.stringify({
      schema_version: "ashr.clone.api_probe_batch_plan.v1",
      function: "plan_batch",
      response: {
        plan,
      },
    }),
    "utf8",
  );
}

test("calibrate CLI dry-run writes a five-modality manifest without fetch", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  let fetchCalled = false;
  globalThis.fetch = () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    const capture = captureStreams();
    const code = await main(["--output", output], {}, capture.streams);
    const manifest = readJson(output);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.match(capture.stdout, /mode=dry-run status=planned/);
    assert.equal(fetchCalled, false);
    assert.equal(manifest.schema_version, "ashr.clone.api_calibration_manifest.v1");
    assert.equal(manifest.summary.read_steps, 5);
    assert.equal(manifest.summary.mutating_steps, 0);
    assert.equal(manifest.guardrails.output_policy.private_output_required, false);
    assert.equal(manifest.guardrails.output_policy.sink, "nonprivate_file");
    assert.deepEqual(manifest.summary.modalities, []);
    assert.equal(manifest.env.auth_env_present.includes(ASHR_API_ENV_VAR), false);
    assert.equal(manifest.steps.every((step) => step.status === "planned"), true);
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI includes five mutating modality plans only with explicit opt-in", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  try {
    const capture = captureStreams();
    const code = await main(["--include-mutating", "--allow-paid-media", "--output", output, "--print-record"], {}, capture.streams);
    const manifest = JSON.parse(capture.stdout);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.equal(readJson(output).steps.length, 10);
    assert.equal(manifest.summary.mutating_steps, 5);
    assert.deepEqual(manifest.summary.modalities, ["audio", "file", "image", "text", "video"]);
    for (const modality of ["text", "image", "audio", "file", "video"]) {
      assert.ok(manifest.steps.some((step) => step.step_id === `create-request-${modality}` && step.modality === modality));
    }
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI real execution requires small-batch and zero retries before key lookup", async () => {
  const capture = captureStreams();
  const code = await main(["--execute"], {}, capture.streams);

  assert.equal(code, 2);
  assert.match(capture.stderr, /--small-batch/);
  assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
});

test("calibrate CLI rejects read-only quota gate records before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "read-only-record.json");
  try {
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
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /plan-batch record/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI rejects go quota gate records without quota evidence", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "go-without-evidence.json");
  try {
    writeFileSync(
      gateFile,
      JSON.stringify({
        schema_version: "ashr.clone.api_probe_batch_plan.v1",
        function: "plan_batch",
        response: {
          plan: {
            schema_version: "ashr.clone.api_probe_batch_plan.v1",
            target_operation: "create-request",
            created_at: new Date().toISOString(),
            quota_stop_go: { decision: "go", source: "not-provided" },
          },
        },
      }),
      "utf8",
    );

    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /requires reviewed quota\/reset evidence/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI rejects wrong target quota gate before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "wrong-target.json");
  try {
    writePlanBatchGate(gateFile, "go", { targetOperation: "create-run" });

    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /target_operation/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI rejects stale quota gate before key lookup unless TTL is disabled", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "stale-gate.json");
  try {
    writePlanBatchGate(gateFile, "go", { createdAt: "2000-01-01T00:00:00Z" });

    const staleCapture = captureStreams();
    const staleCode = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, staleCapture.streams);

    assert.equal(staleCode, 2);
    assert.match(staleCapture.stderr, /stale/);
    assert.doesNotMatch(staleCapture.stderr, new RegExp(ASHR_API_ENV_VAR));

    const ttlDisabledCapture = captureStreams();
    const ttlDisabledCode = await main(
      ["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile, "--quota-gate-ttl-seconds", "0"],
      {},
      ttlDisabledCapture.streams,
    );

    assert.equal(ttlDisabledCode, 2);
    assert.doesNotMatch(ttlDisabledCapture.stderr, /stale/);
    assert.match(ttlDisabledCapture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI rejects modality-bound quota gate mismatch before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "wrong-modality.json");
  try {
    writePlanBatchGate(gateFile, "go", { modalities: ["image"] });

    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /modalities/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI rejects request-fingerprint-bound quota gate mismatch before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "wrong-fingerprint.json");
  try {
    writePlanBatchGate(gateFile, "go", { requestFingerprint: "not-the-text-calibrator-fingerprint" });

    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /request_fingerprint/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI blocks stop quota gate before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const gateFile = join(temp, "quota-stop.json");
  try {
    writePlanBatchGate(gateFile, "stop");

    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--include-mutating", "--modality", "text", "--quota-gate-record", gateFile], {}, capture.streams);

    assert.equal(code, 2);
    assert.match(capture.stderr, /quota gate decision=stop/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI protected output blocks before key lookup", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  try {
    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--output", output], {}, capture.streams);

    assert.equal(code, 2);
    assert.equal(capture.stdout, "");
    assert.match(capture.stderr, /docs\/evidence\/private_refs/);
    assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI quota-gate protected output blocks before gate read", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  const missingGate = join(temp, "missing-gate.json");
  try {
    const capture = captureStreams();
    const code = await main(["--execute", "--small-batch", "--include-mutating", "--modality", "text", "--max-retries", "0", "--quota-gate-record", missingGate, "--output", output], {}, capture.streams);

    assert.equal(code, 2);
    assert.equal(capture.stdout, "");
    assert.match(capture.stderr, /docs\/evidence\/private_refs/);
    assert.doesNotMatch(capture.stderr, /quota-gate-record/);
    assert.equal(existsSync(output), false);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI protected print-record is blocked before key lookup", async () => {
  const output = join(process.cwd(), "..", "..", "..", "docs", "evidence", "private_refs", "ts_calibrate_print_record_block.json");
  const capture = captureStreams();
  const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--output", output, "--print-record"], {}, capture.streams);

  assert.equal(code, 2);
  assert.equal(capture.stdout, "");
  assert.match(capture.stderr, /--print-record/);
  assert.doesNotMatch(capture.stderr, new RegExp(ASHR_API_ENV_VAR));
  assert.equal(existsSync(output), false);
});

test("calibrate CLI read-only small-batch records response keys without leaking key", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  const seen = [];
  globalThis.fetch = async (_url, init) => {
    const body = JSON.parse(String(init.body));
    seen.push({ body, authorization: init.headers.Authorization });
    if (body.function === "init") {
      return response({ status: "ok", user: { id: 1, tenant_id: 2, email: "owner@example.com" }, tenant: { id: 2 }, features: {}, notes: [] });
    }
    if (body.function === "keep_alive") {
      return response({ status: "ok", message: "keep alive", db: "ok" });
    }
    if (body.function === "list_agents") {
      return response({ status: "ok", agents: [] });
    }
    if (body.function === "list_datasets") {
      return response({ status: "ok", datasets: [{ id: 7, name: "dataset" }], next_cursor: null });
    }
    if (body.function === "list_requests") {
      return response({ status: "ok", requests: [{ id: 8, request_status: "completed" }], next_cursor: null });
    }
    throw new Error(`unexpected function ${body.function}`);
  };
  try {
    const capture = captureStreams();
    const syntheticApiKey = "test_synthetic_secret";
    const code = await main(["--execute", "--small-batch", "--max-retries", "0", "--output", output, "--allow-nonprivate-output"], { [ASHR_API_ENV_VAR]: syntheticApiKey }, capture.streams);
    const manifest = readJson(output);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.equal(manifest.mode, "small-batch");
    assert.equal(manifest.status, "ok");
    assert.equal(manifest.summary.read_steps, 5);
    assert.equal(manifest.summary.mutating_steps, 0);
    assert.equal(manifest.env.auth_env_present.includes(ASHR_API_ENV_VAR), true);
    assert.equal(manifest.guardrails.output_policy.private_output_required, true);
    assert.equal(manifest.guardrails.output_policy.nonprivate_output_override_used, true);
    assert.equal(JSON.stringify(manifest).includes(syntheticApiKey), false);
    assert.equal(seen.length, 6);
    assert.equal(seen.every((item) => item.authorization === ["Bearer", syntheticApiKey].join(" ")), true);
    assert.ok(manifest.steps.some((step) => step.step_id === "list-datasets" && step.response_keys.includes("datasets")));
    assert.ok(manifest.steps.some((step) => step.step_id === "list-requests" && step.response_keys.includes("requests")));
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI persists audited quota override reason in emitted evidence", async () => {
  const originalFetch = globalThis.fetch;
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  const reason = "manual paid calibration approved after quota review";
  globalThis.fetch = async (_url, init) => {
    const body = JSON.parse(String(init.body));
    if (body.function === "init") {
      return response({ status: "ok", user: { id: 1, tenant_id: 2, email: "owner@example.com" }, tenant: { id: 2 }, features: {}, notes: [] });
    }
    if (body.function === "keep_alive") {
      return response({ status: "ok", message: "keep alive", db: "ok" });
    }
    if (body.function === "list_agents") {
      return response({ status: "ok", agents: [] });
    }
    if (body.function === "list_datasets") {
      return response({ status: "ok", datasets: [{ id: 7, name: "dataset" }], next_cursor: null });
    }
    if (body.function === "list_requests") {
      return response({ status: "ok", requests: [{ id: 8, request_status: "completed" }], next_cursor: null });
    }
    if (body.function === "create_request") {
      return response({ status: "ok", request: { id: 9, request_status: "queued" } });
    }
    throw new Error(`unexpected function ${body.function}`);
  };
  try {
    const capture = captureStreams();
    const code = await main(
      [
        "--execute",
        "--small-batch",
        "--max-retries",
        "0",
        "--include-mutating",
        "--modality",
        "text",
        "--allow-quota-override",
        "--quota-override-reason",
        reason,
        "--output",
        output,
        "--allow-nonprivate-output",
      ],
      { [ASHR_API_ENV_VAR]: "test_synthetic_secret" },
      capture.streams,
    );
    const manifest = readJson(output);
    const mutateStep = manifest.steps.find((step) => step.step_id === "create-request-text");
    const stepRecord = readJson(mutateStep.private_record_path);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.equal(manifest.summary.mutating_steps, 1);
    assert.equal(manifest.guardrails.quota_gate.decision, "override");
    assert.equal(manifest.guardrails.quota_gate.override.reason, reason);
    assert.equal(stepRecord.request.preflight.quota_gate.override.used, true);
    assert.equal(stepRecord.request.preflight.quota_gate.override.reason, reason);
    assert.equal(JSON.stringify(manifest).includes("test_synthetic_secret"), false);
  } finally {
    globalThis.fetch = originalFetch;
    rmSync(temp, { recursive: true, force: true });
  }
});

function response(body) {
  return {
    status: 200,
    headers: { forEach() {} },
    async text() {
      return JSON.stringify(body);
    },
  };
}
test("calibrate CLI can narrow mutating calibration to text without paid media flag", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-calibrate-"));
  const output = join(temp, "manifest.json");
  try {
    const capture = captureStreams();
    const code = await main(["--include-mutating", "--modality", "text", "--output", output], {}, capture.streams);
    const manifest = readJson(output);

    assert.equal(code, 0);
    assert.equal(capture.stderr, "");
    assert.equal(manifest.summary.mutating_steps, 1);
    assert.deepEqual(manifest.summary.modalities, ["text"]);
    assert.equal(manifest.steps.some((step) => step.step_id === "create-request-text"), true);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("calibrate CLI blocks non-text mutating calibration without paid media flag", async () => {
  const capture = captureStreams();
  const code = await main(["--include-mutating", "--modality", "image"], {}, capture.streams);

  assert.equal(code, 2);
  assert.match(capture.stderr, /--allow-paid-media/);
});
