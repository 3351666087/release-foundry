import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ASHR_API_ENV_VAR, parseArgs, runCalibration } from "../dist/index.js";

const ALL_MODALITIES = ["audio", "file", "image", "text", "video"];

function tempOutput(prefix = "ashr-ts-calibration-parity-") {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  return { dir, output: join(dir, "manifest.json") };
}

async function dryRun(argv, env = {}) {
  const { dir, output } = tempOutput();
  try {
    const args = parseArgs(["--output", output, ...argv]);
    const manifest = await runCalibration(args, env, output);
    return { manifest, args };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

for (const modality of ALL_MODALITIES) {
  test(`TS calibration SDK plans ${modality} mutating request with public-safe dry-run shape`, async () => {
    const { manifest } = await dryRun(["--include-mutating", "--allow-paid-media", "--modality", modality]);
    const step = manifest.steps.find((candidate) => candidate.step_id === `create-request-${modality}`);

    assert.ok(step, `missing ${modality} create-request step`);
    assert.equal(step.modality, modality);
    assert.equal(step.kind, "mutate");
    assert.equal(step.status, "planned");
    assert.equal(step.dry_run, true);
    assert.equal(step.response_keys.includes("plan"), true);
    assert.equal(step.attempts, 0);
    assert.equal(step.estimated_calls, 2);
    assert.match(step.private_record_path, /create-request-[a-z]+_dry_run\.json$/);
    assert.deepEqual(manifest.summary.modalities, [modality]);
    assert.equal(JSON.stringify(step).includes(ASHR_API_ENV_VAR), false);
  });
}

for (const modality of ["image", "audio", "file", "video"]) {
  test(`TS calibration parser treats paid ${modality} as opt-in modality`, () => {
    const args = parseArgs(["--include-mutating", "--allow-paid-media", "--modality", modality]);

    assert.equal(args.includeMutating, true);
    assert.equal(args.allowPaidMedia, true);
    assert.deepEqual(args.modalities, [modality]);
  });
}

test("TS calibration parser preserves repeated modality order before summary sorting", () => {
  const args = parseArgs(["--include-mutating", "--allow-paid-media", "--modality", "video,audio", "--modality", "file"]);

  assert.deepEqual(args.modalities, ["video", "audio", "file"]);
});

test("TS calibration SDK dry-run exposes read-only operation parity without auth env", async () => {
  const { manifest } = await dryRun([]);

  assert.equal(manifest.mode, "dry-run");
  assert.equal(manifest.status, "planned");
  assert.equal(manifest.summary.read_steps, 5);
  assert.equal(manifest.summary.mutating_steps, 0);
  assert.equal(manifest.env.auth_env_present.length, 0);
  assert.equal(manifest.guardrails.output_policy.private_output_required, false);
});

test("TS calibration SDK redacts auth env presence to variable names only", async () => {
  const { manifest } = await dryRun([], { [ASHR_API_ENV_VAR]: "secret-value-that-must-not-appear" });
  const serialized = JSON.stringify(manifest);

  assert.deepEqual(manifest.env.auth_env_present, [ASHR_API_ENV_VAR]);
  assert.equal(serialized.includes("secret-value-that-must-not-appear"), false);
});

test("TS calibration SDK dry-run with all modalities mirrors Python five-media summary", async () => {
  const { manifest } = await dryRun(["--include-mutating", "--allow-paid-media"]);

  assert.equal(manifest.summary.total_steps, 10);
  assert.equal(manifest.summary.read_steps, 5);
  assert.equal(manifest.summary.mutating_steps, 5);
  assert.deepEqual(manifest.summary.modalities, ALL_MODALITIES);
});

test("TS calibration SDK parser keeps real execution guardrail knobs explicit", () => {
  const args = parseArgs(["--execute", "--small-batch", "--max-retries", "0", "--timeout", "7", "--retry-backoff-ms", "0", "--limit", "5"]);

  assert.equal(args.execute, true);
  assert.equal(args.smallBatch, true);
  assert.equal(args.maxRetries, 0);
  assert.equal(args.timeoutSeconds, 7);
  assert.equal(args.retryBackoffMs, 0);
  assert.equal(args.limit, 5);
});

test("TS calibration SDK parser rejects unknown flags before key lookup", () => {
  assert.throws(() => parseArgs(["--unknown-paid-thing"]), /unknown option/);
});

test("TS calibration SDK parser rejects positional raw secrets before key lookup", () => {
  assert.throws(() => parseArgs(["raw-secret-value"]), /unexpected positional argument/);
});

test("TS calibration SDK parser rejects invalid modality before any API call", () => {
  assert.throws(() => parseArgs(["--modality", "pdf"]), /unsupported modality/);
});
