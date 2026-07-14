#!/usr/bin/env node
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runA3PostgresRlsQualification } from "./a3_postgres_rls_probe.mjs";

export function parsePostgresRlsProbeArgs(argv = []) {
  const options = { connection: {} };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--output") options.output = next();
    else if (item === "--observed-at") options.observedAt = next();
    else if (item === "--target-class") options.targetClass = next();
    else if (item === "--psql") options.psqlCommand = next();
    else if (item === "--host") options.connection.host = next();
    else if (item === "--port") options.connection.port = next();
    else if (item === "--user") options.connection.user = next();
    else if (item === "--database") options.connection.database = next();
    else if (item === "--sslmode") options.connection.sslmode = next();
    else if (item === "--timeout-ms") options.timeoutMs = Number(next());
    else if (item === "--json") options.json = true;
    else if (item === "--help" || item === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return options;
}

export async function runPostgresRlsProbeCli(argv = process.argv.slice(2), io = {}) {
  try {
    const options = parsePostgresRlsProbeArgs(argv);
    if (options.help) {
      (io.stdout || process.stdout).write(`${JSON.stringify(usage(), null, 2)}\n`);
      return 0;
    }
    const qualification = await runA3PostgresRlsQualification(options);
    if (options.output) {
      const output = resolve(options.output);
      await mkdir(dirname(output), { recursive: true });
      await writeFile(output, `${JSON.stringify(qualification, null, 2)}\n`, "utf8");
    }
    if (options.json || !options.output) {
      (io.stdout || process.stdout).write(`${JSON.stringify(qualification, null, 2)}\n`);
    }
    return 0;
  } catch (error) {
    const payload = {
      schema_version: "a3.postgres_rls_probe_cli_error.v1",
      error: error?.code || "postgres_rls_probe_failed",
      message: "PostgreSQL RLS qualification failed; no production acceptance changed.",
      safety: {
        exception_message_exposed: false,
        credentials_included: false,
        dsn_included: false,
        production_state_changed: false
      }
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function usage() {
  return {
    schema_version: "a3.postgres_rls_probe_cli_usage.v1",
    command: "node services/report/a3_postgres_rls_probe_cli.mjs --psql <path> --host 127.0.0.1 --port 55432 --user postgres --database postgres --output <redacted.json>",
    credential_boundary: "Password is accepted only through A3_POSTGRES_TEST_PASSWORD or PGPASSWORD and is never emitted.",
    behavior: "Applies the migration 019-to-020 upgrade chain twice and verifies five-level same-scope allow plus cross-scope RLS denial.",
    authority_boundary: "A local or staging qualification never changes Deployment Acceptance or A2 authority."
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runPostgresRlsProbeCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
