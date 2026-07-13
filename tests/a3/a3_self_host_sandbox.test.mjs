import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  A3SelfHostSandboxError,
  buildSelfHostSandboxCalibration,
  findSelfHostSandboxLeaks,
  loadSelfHostSandboxCalibration,
  runA1SelfHostSandboxProbe,
  validateA1SelfHostSandboxProbe,
  validateSelfHostSandboxCalibration
} from "../../services/report/a3_self_host_sandbox.mjs";
import {
  parseSelfHostSandboxArgs,
  runSelfHostSandboxCli
} from "../../services/report/a3_self_host_sandbox_cli.mjs";

const observedAt = "2026-07-13T08:00:00.000Z";

test("A3 invokes the real A1 local sandbox probe through a constrained child process", async () => {
  const calibration = await runA1SelfHostSandboxProbe({
    repoRoot: process.cwd(),
    observedAt
  });

  assert.equal(calibration.schema_version, "a3.self_host_sandbox_calibration.v1");
  assert.equal(calibration.status, "sandbox_verified");
  assert.deepEqual(calibration.summary, {
    failed: 0,
    passed: 4,
    production_gap_count: 5,
    total_checks: 4
  });
  assert.deepEqual(calibration.checks.map((item) => item.id), [
    "a1_control_plane_health",
    "a1_worker_retry_dead_letter",
    "a1_worker_expired_lease_recovery",
    "a1_local_object_storage_integrity"
  ]);
  assert.equal(calibration.authority_boundary.production_verified, false);
  assert.equal(calibration.authority_boundary.deployment_acceptance_mutated, false);
  assert.equal(calibration.authority_boundary.a2_decision_recomputed, false);
  assert.equal(calibration.safety.child_process_environment_allowlisted, true);
  assert.match(calibration.evidence_integrity.probe_payload_sha256, /^sha256:[a-f0-9]{64}$/);
  assert.deepEqual(findSelfHostSandboxLeaks(calibration), []);
});

test("A3 sandbox validators reject production overclaims and sensitive material", async () => {
  const calibration = await runA1SelfHostSandboxProbe({ repoRoot: process.cwd(), observedAt });
  const overclaim = structuredClone(calibration);
  overclaim.authority_boundary.production_verified = true;
  assert.throws(
    () => validateSelfHostSandboxCalibration(overclaim),
    (error) => error instanceof A3SelfHostSandboxError && error.code === "calibration_contract_invalid"
  );

  const probe = calibrationToProbe(calibration);
  probe.checks[0].observed.operator_note = "Bearer should-not-leak";
  assert.throws(
    () => validateA1SelfHostSandboxProbe(probe),
    (error) => error instanceof A3SelfHostSandboxError
      && error.code === "probe_contract_invalid"
      && error.details.some((item) => item.includes("authorization"))
  );

  const pathLeak = calibrationToProbe(calibration);
  pathLeak.checks[0].observed.runtime_note = "C:\\private\\sandbox\\evidence.json";
  assert.throws(() => buildSelfHostSandboxCalibration(pathLeak), A3SelfHostSandboxError);
});

test("A3 self-host sandbox CLI writes and reloads a validated redacted fixture", async () => {
  const directory = await mkdtemp(join(tmpdir(), "a3-sandbox-calibration-"));
  const output = join(directory, "calibration.redacted.json");
  let stdout = "";
  let stderr = "";
  try {
    const exitCode = await runSelfHostSandboxCli([
      "--output", output,
      "--observed-at", observedAt
    ], {
      repoRoot: process.cwd(),
      stdout: { write: (value) => { stdout += value; } },
      stderr: { write: (value) => { stderr += value; } }
    });
    assert.equal(exitCode, 0);
    assert.equal(stdout, "");
    assert.equal(stderr, "");
    const raw = await readFile(output, "utf8");
    assert.doesNotMatch(raw, /Bearer|github_pat_|ghp_|\bsk-|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|[A-Za-z]:\\/i);
    const loaded = await loadSelfHostSandboxCalibration(output);
    assert.equal(loaded.status, "sandbox_verified");
    assert.equal(loaded.safety.production_verified, false);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("A3 self-host sandbox CLI parses bounded execution options and fails closed", async () => {
  assert.deepEqual(parseSelfHostSandboxArgs([
    "--output", "fixture.json",
    "--observed-at", observedAt,
    "--python", "python3",
    "--timeout-ms", "3000",
    "--json"
  ]), {
    output: "fixture.json",
    observedAt,
    pythonCommand: "python3",
    timeoutMs: 3000,
    json: true
  });
  await assert.rejects(
    () => runA1SelfHostSandboxProbe({
      repoRoot: process.cwd(),
      pythonCommand: "definitely-missing-python-a3",
      observedAt
    }),
    (error) => error instanceof A3SelfHostSandboxError && error.code === "probe_process_unavailable"
  );
});

function calibrationToProbe(calibration) {
  return {
    schema_version: "a3.a1_self_host_sandbox_probe.v1",
    calibration_id: calibration.calibration_id,
    observed_at: calibration.observed_at,
    status: calibration.status,
    source_lane: "A1",
    probe_owner: "A3",
    execution_mode: "local_process",
    external_api_used: false,
    tenant_scope: structuredClone(calibration.tenant_scope),
    summary: structuredClone(calibration.summary),
    checks: structuredClone(calibration.checks),
    production_gaps: structuredClone(calibration.production_gaps),
    authority_boundary: structuredClone(calibration.authority_boundary),
    safety: {
      local_only: true,
      raw_payload_included: false,
      credential_material_included: false,
      absolute_local_path_included: false,
      external_network_used: false,
      ashr_api_used: false
    }
  };
}
