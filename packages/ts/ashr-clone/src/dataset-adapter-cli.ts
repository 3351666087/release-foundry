#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { apiRecordToCases, extractDatasetSource, replayFixtureFromSourceRun } from "./dataset-adapter.js";

type CliOptions = Record<string, string | boolean>;

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  const command = args[0] && !args[0].startsWith("--") ? args[0] : "cases";
  const options = parseArgs(command === args[0] ? args.slice(1) : args);
  if (options.help || options.h) {
    printHelp();
    return 0;
  }
  const inputPath = stringOption(options, "input", true);
  const outputPath = stringOption(options, "output", true);
  const payload = JSON.parse(await readFile(resolve(inputPath), "utf8")) as unknown;
  if (!isRecord(payload)) {
    throw new Error("input must be a JSON object");
  }
  if (command === "cases") {
    const cases = apiRecordToCases(payload, {
      maxCases: numberOption(options, "max-cases", null),
      includeAgentlessRuns: Boolean(options["include-agentless-runs"]),
    });
    await writeJson(outputPath, { adapter_version: "ashr.clone.dataset_adapter.v1", cases });
    process.stdout.write(`${JSON.stringify({ status: "ok", command, cases: cases.length, output: resolve(outputPath) })}\n`);
    return 0;
  }
  if (command === "replay-fixture") {
    const source = extractDatasetSource(payload);
    const runKey = stringOption(options, "run-key", false);
    const runs = source.runs;
    const rawRun = runKey && isRecord(runs) ? runs[runKey] : Array.isArray(runs) ? runs[0] : isRecord(runs) ? Object.values(runs)[0] : undefined;
    if (!isRecord(rawRun)) {
      throw new Error("no source run found for replay fixture");
    }
    const fixture = replayFixtureFromSourceRun(rawRun, { runKey });
    await writeJson(outputPath, fixture);
    process.stdout.write(`${JSON.stringify({ status: "ok", command, output: resolve(outputPath), events: Array.isArray(fixture.events) ? fixture.events.length : 0 })}\n`);
    return 0;
  }
  throw new Error(`unknown command: ${command}`);
}

function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      throw new Error(`unexpected argument: ${arg}`);
    }
    const name = arg.slice(2);
    const next = args[index + 1];
    if (next === undefined || next.startsWith("--")) {
      options[name] = true;
      continue;
    }
    options[name] = next;
    index += 1;
  }
  return options;
}

function stringOption(options: CliOptions, name: string, required: true): string;
function stringOption(options: CliOptions, name: string, required: false): string | undefined;
function stringOption(options: CliOptions, name: string, required: boolean): string | undefined {
  const value = options[name];
  if (typeof value === "string") {
    return value;
  }
  if (required) {
    throw new Error(`missing required --${name}`);
  }
  return undefined;
}

function numberOption(options: CliOptions, name: string, fallback: number | null): number | null {
  const value = options[name];
  if (value === undefined || value === true) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`--${name} must be numeric`);
  }
  return parsed;
}

async function writeJson(path: string, value: unknown): Promise<void> {
  const output = resolve(path);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function printHelp(): void {
  process.stdout.write(`ashr-clone-dataset-adapter

Commands:
  cases            Convert API dataset_source records to local runner cases.
  replay-fixture   Convert one source run to an A3 replay fixture.

Required:
  --input <api-record.json>
  --output <output.json>

Options:
  --max-cases <n>
  --include-agentless-runs
  --run-key <key>       replay-fixture only
`);
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    process.stderr.write(`ashr-clone-dataset-adapter error: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
