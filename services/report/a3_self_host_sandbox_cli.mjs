#!/usr/bin/env node
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  attachPostgresRlsQualificationFromFile,
  runA1SelfHostSandboxProbe
} from "./a3_self_host_sandbox.mjs";

export function parseSelfHostSandboxArgs(argv = []) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--output") options.output = next();
    else if (item === "--postgres-qualification") options.postgresQualification = next();
    else if (item === "--observed-at") options.observedAt = next();
    else if (item === "--python") options.pythonCommand = next();
    else if (item === "--timeout-ms") options.timeoutMs = Number(next());
    else if (item === "--json") options.json = true;
    else if (item === "--help" || item === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return options;
}

export async function runSelfHostSandboxCli(argv = process.argv.slice(2), io = {}) {
  try {
    const options = parseSelfHostSandboxArgs(argv);
    if (options.help) {
      (io.stdout || process.stdout).write(`${JSON.stringify(usage(), null, 2)}\n`);
      return 0;
    }
    let calibration = await runA1SelfHostSandboxProbe({
      ...options,
      repoRoot: io.repoRoot || process.cwd()
    });
    if (options.postgresQualification) {
      calibration = await attachPostgresRlsQualificationFromFile(calibration, options.postgresQualification);
    }
    if (options.output) {
      const output = resolve(options.output);
      await mkdir(dirname(output), { recursive: true });
      await writeFile(output, `${JSON.stringify(calibration, null, 2)}\n`, "utf8");
    }
    if (options.json || !options.output) {
      (io.stdout || process.stdout).write(`${JSON.stringify(calibration, null, 2)}\n`);
    }
    return calibration.status === "sandbox_verified" ? 0 : 1;
  } catch (error) {
    const payload = {
      schema_version: "a3.self_host_sandbox_cli_error.v1",
      error: error?.code || "self_host_sandbox_cli_error",
      message: "Self-host sandbox calibration failed; no production state changed.",
      safety: {
        exception_message_exposed: false,
        credential_material_included: false,
        production_state_changed: false
      }
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function usage() {
  return {
    schema_version: "a3.self_host_sandbox_cli_usage.v1",
    command: "node services/report/a3_self_host_sandbox_cli.mjs --postgres-qualification fixtures/a3/p3/a3_postgres_rls_qualification_20260713.redacted.json --output fixtures/a3/p3/a3_self_host_sandbox_calibration_20260713.redacted.json --observed-at 2026-07-13T08:00:00.000Z",
    behavior: "Runs local A1 health, worker, lease-recovery, and object-integrity checks.",
    boundary: "sandbox_verified never means production_verified and never changes A2 or deployment acceptance."
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runSelfHostSandboxCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
