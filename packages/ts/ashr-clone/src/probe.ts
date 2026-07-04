#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ASHR_API_FIELD_MAP_VERSION,
  ASHR_API_ENV_VAR,
  ASHR_LABS_API_ENV_VAR,
  AshrApiCallRecord,
  AshrApiClient,
  AshrApiError,
  MissingAshrApiKeyError,
  redactApiSensitive,
  redactApiText,
} from "./api-client.js";

type JsonRecord = Record<string, unknown>;
type WritableStreamLike = { write(chunk: string): unknown };

const OPERATIONS = [
  "init",
  "health-check",
  "list-agents",
  "list-datasets",
  "get-dataset",
  "list-runs",
  "get-run",
  "poll-run",
  "list-requests",
  "get-request",
  "poll-request",
  "create-run",
  "create-request",
] as const;

type ProbeOperation = (typeof OPERATIONS)[number];

const MUTATING_OPERATIONS = new Set<ProbeOperation>(["create-run", "create-request"]);

export interface ProbeCliArgs {
  operation?: ProbeOperation;
  execute: boolean;
  allowMutate: boolean;
  output?: string;
  baseUrl?: string;
  timeoutSeconds: number;
  maxRetries: number;
  retryBackoffMs: number;
  printRecord: boolean;
  limit: number;
  cursor?: number;
  status?: string;
  datasetId?: number;
  runId?: number;
  requestId?: number;
  runnerId?: number;
  requestorId?: number;
  resultFile?: string;
  requestName?: string;
  requestFile?: string;
  requestSchemaFile?: string;
  allowMediaGeneration: boolean;
  allowNonTextInputs: boolean;
  maxRequestVariations: number;
  pollTimeoutSeconds: number;
  pollIntervalSeconds: number;
  help: boolean;
}

interface ProbeStreams {
  stdout: WritableStreamLike;
  stderr: WritableStreamLike;
}

class CliUsageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CliUsageError";
  }
}

export async function main(
  argv: readonly string[] = process.argv.slice(2),
  env: Record<string, string | undefined> = process.env,
  streams: ProbeStreams = { stdout: process.stdout, stderr: process.stderr },
): Promise<number> {
  let args: ProbeCliArgs | undefined;
  let outputPath: string | undefined;
  let dryRun = true;
  try {
    args = parseArgs(argv);
    if (args.help) {
      streams.stdout.write(usage());
      return 0;
    }
    dryRun = !args.execute;
    outputPath = args.output === "-" ? undefined : args.output ?? defaultOutputPath(requireOperation(args.operation), dryRun);
    validateExecuteGuards(args);
    const client = AshrApiClient.fromEnv(env, {
      required: args.execute,
      baseUrl: args.baseUrl,
      timeoutMs: args.timeoutSeconds * 1000,
      maxRetries: args.maxRetries,
      retryBackoffMs: args.retryBackoffMs,
    });
    const record = await runOperation(client, args, { dryRun, outputPath });
    await emitRecord(record, outputPath, streams.stdout, { printRecord: args.printRecord });
    return 0;
  } catch (error) {
    const message = formatErrorMessage(error);
    if (args?.operation !== undefined && outputPath !== undefined) {
      try {
        await writeErrorRecord(error, args, { dryRun, outputPath });
      } catch (writeError) {
        streams.stderr.write(`api probe evidence write error: ${formatErrorMessage(writeError)}\n`);
      }
    }
    streams.stderr.write(`api probe error: ${message}\n`);
    if (error instanceof MissingAshrApiKeyError) {
      streams.stderr.write(`hint: set ${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} in the current process\n`);
    }
    return 2;
  }
}

export async function runOperation(
  client: AshrApiClient,
  args: ProbeCliArgs,
  options: { dryRun: boolean; outputPath?: string },
): Promise<AshrApiCallRecord> {
  const operation = requireOperation(args.operation);
  const callOptions = { dryRun: options.dryRun, outputPath: options.outputPath };

  switch (operation) {
    case "init":
      return client.init(callOptions);
    case "health-check":
      return client.healthCheck(callOptions);
    case "list-agents":
      return client.listAgents(callOptions);
    case "list-datasets":
      return client.listDatasets({ ...callOptions, limit: args.limit, cursor: args.cursor });
    case "get-dataset":
      return client.getDataset(requireNumber(args.datasetId, "--dataset-id is required for get-dataset"), callOptions);
    case "list-runs":
      return client.listRuns({ ...callOptions, datasetId: args.datasetId, limit: args.limit });
    case "get-run":
      return client.getRun(requireNumber(args.runId, "--run-id is required for get-run"), callOptions);
    case "poll-run":
      return client.pollRun({
        ...callOptions,
        runId: requireNumber(args.runId, "--run-id is required for poll-run"),
        timeoutSeconds: args.pollTimeoutSeconds,
        pollIntervalSeconds: args.pollIntervalSeconds,
      });
    case "list-requests":
      return client.listRequests({ ...callOptions, limit: args.limit, status: args.status, cursor: args.cursor });
    case "get-request":
      return client.getRequest(requireNumber(args.requestId, "--request-id is required for get-request"), callOptions);
    case "poll-request":
      return client.pollRequest({
        ...callOptions,
        requestId: requireNumber(args.requestId, "--request-id is required for poll-request"),
        timeoutSeconds: args.pollTimeoutSeconds,
        pollIntervalSeconds: args.pollIntervalSeconds,
      });
    case "create-run": {
      const result = await readJsonObject(requireText(args.resultFile, "--result-file is required for create-run"), "--result-file");
      return client.createRun({
        ...callOptions,
        datasetId: requireNumber(args.datasetId, "--dataset-id is required for create-run"),
        result,
        runnerId: args.runnerId,
      });
    }
    case "create-request": {
      const request = await readJsonObject(requireText(args.requestFile, "--request-file is required for create-request"), "--request-file");
      const requestInputSchema = args.requestSchemaFile
        ? await readJsonObject(args.requestSchemaFile, "--request-schema-file")
        : undefined;
      return client.createRequest({
        ...callOptions,
        requestName: requireText(args.requestName, "--request-name is required for create-request"),
        request,
        requestInputSchema,
        requestorId: args.requestorId,
        allowMediaGeneration: args.allowMediaGeneration,
        allowNonTextInputs: args.allowNonTextInputs,
        maxRequestVariations: args.maxRequestVariations,
      });
    }
  }
}

export function parseArgs(argv: readonly string[]): ProbeCliArgs {
  const args: ProbeCliArgs = {
    execute: false,
    allowMutate: false,
    timeoutSeconds: 30,
    maxRetries: 2,
    retryBackoffMs: 500,
    printRecord: false,
    limit: 5,
    allowMediaGeneration: false,
    allowNonTextInputs: false,
    maxRequestVariations: 1,
    pollTimeoutSeconds: 300,
    pollIntervalSeconds: 20,
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const raw = argv[index];
    if (raw === "-h" || raw === "--help") {
      args.help = true;
      continue;
    }
    if (!raw.startsWith("--")) {
      if (args.operation !== undefined) {
        throw new CliUsageError(`unexpected positional argument: ${raw}`);
      }
      if (!isOperation(raw)) {
        throw new CliUsageError(`unsupported operation: ${raw}`);
      }
      args.operation = raw;
      continue;
    }

    const [name, inlineValue] = splitOption(raw);
    switch (name) {
      case "--execute":
        rejectInlineValue(name, inlineValue);
        args.execute = true;
        break;
      case "--allow-mutate":
        rejectInlineValue(name, inlineValue);
        args.allowMutate = true;
        break;
      case "--allow-media-generation":
        rejectInlineValue(name, inlineValue);
        args.allowMediaGeneration = true;
        break;
      case "--allow-non-text-inputs":
        rejectInlineValue(name, inlineValue);
        args.allowNonTextInputs = true;
        break;
      case "--print-record":
        rejectInlineValue(name, inlineValue);
        args.printRecord = true;
        break;
      case "--output": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.output = value;
        index = nextIndex;
        break;
      }
      case "--base-url": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.baseUrl = value;
        index = nextIndex;
        break;
      }
      case "--timeout": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.timeoutSeconds = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--max-retries": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.maxRetries = parseInteger(value, name, { min: 0 });
        index = nextIndex;
        break;
      }
      case "--retry-backoff-ms": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.retryBackoffMs = parseInteger(value, name, { min: 0 });
        index = nextIndex;
        break;
      }
      case "--limit": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.limit = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--cursor": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.cursor = parseInteger(value, name, { min: 0 });
        index = nextIndex;
        break;
      }
      case "--status": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.status = value;
        index = nextIndex;
        break;
      }
      case "--dataset-id": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.datasetId = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--run-id": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.runId = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--request-id": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.requestId = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--runner-id": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.runnerId = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--requestor-id": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.requestorId = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--result-file": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.resultFile = value;
        index = nextIndex;
        break;
      }
      case "--request-name": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.requestName = value;
        index = nextIndex;
        break;
      }
      case "--request-file": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.requestFile = value;
        index = nextIndex;
        break;
      }
      case "--request-schema-file": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.requestSchemaFile = value;
        index = nextIndex;
        break;
      }
      case "--max-request-variations": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.maxRequestVariations = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--poll-timeout": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.pollTimeoutSeconds = parseInteger(value, name, { min: 1 });
        index = nextIndex;
        break;
      }
      case "--poll-interval": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.pollIntervalSeconds = parseInteger(value, name, { min: 0 });
        index = nextIndex;
        break;
      }
      default:
        throw new CliUsageError(`unknown option: ${name}`);
    }
  }

  if (!args.help && args.operation === undefined) {
    throw new CliUsageError("operation is required");
  }
  return args;
}

function validateExecuteGuards(args: ProbeCliArgs): void {
  const operation = requireOperation(args.operation);
  if (!args.execute || !MUTATING_OPERATIONS.has(operation)) {
    return;
  }
  if (!args.allowMutate) {
    throw new CliUsageError(`${operation} is mutating; rerun with --allow-mutate after reviewing the dry-run plan`);
  }
  if (args.maxRetries !== 0) {
    throw new CliUsageError(`${operation} execution requires --max-retries 0 to avoid duplicate mutation on retry`);
  }
}

function defaultOutputPath(operation: ProbeOperation, dryRun: boolean): string {
  return `docs/evidence/private_refs/a1_ts_api_${operation.replaceAll("-", "_")}_${dryRun ? "dry_run" : "real"}.json`;
}

async function readJsonObject(path: string, optionName: string): Promise<JsonRecord> {
  const text = await readFile(path, "utf8");
  const parsed = JSON.parse(text) as unknown;
  if (!isRecord(parsed)) {
    throw new CliUsageError(`${optionName} must contain a JSON object`);
  }
  return parsed;
}

async function emitRecord(
  record: AshrApiCallRecord,
  outputPath: string | undefined,
  stdout: WritableStreamLike,
  options: { printRecord: boolean },
): Promise<void> {
  const json = `${JSON.stringify(record, null, 2)}\n`;
  if (outputPath !== undefined) {
    const absoluteOutput = resolve(outputPath);
    await mkdir(dirname(absoluteOutput), { recursive: true });
    await writeFile(absoluteOutput, json, "utf8");
  }
  if (options.printRecord) {
    stdout.write(json);
    return;
  }
  stdout.write(`${summaryLine(record, outputPath)}\n`);
}

async function writeErrorRecord(
  error: unknown,
  args: ProbeCliArgs,
  options: { dryRun: boolean; outputPath: string },
): Promise<void> {
  const record = errorRecord(error, args, options.dryRun, options.outputPath);
  const absoluteOutput = resolve(options.outputPath);
  await mkdir(dirname(absoluteOutput), { recursive: true });
  await writeFile(absoluteOutput, `${JSON.stringify(record, null, 2)}\n`, "utf8");
}

function errorRecord(error: unknown, args: ProbeCliArgs, dryRun: boolean, outputPath: string): AshrApiCallRecord {
  if (error instanceof AshrApiError && isCallRecord(error.response)) {
    const record = redactApiSensitive(error.response) as unknown as AshrApiCallRecord;
    record.output_path = outputPath;
    return record;
  }
  const operation = requireOperation(args.operation);
  const now = new Date().toISOString();
  const statusCode = error instanceof AshrApiError ? error.statusCode : null;
  const errorPayload = error instanceof AshrApiError
    ? error.toJSON()
    : { message: formatErrorMessage(error), status_code: statusCode, error_kind: error instanceof MissingAshrApiKeyError ? "auth" : "client" };
  return redactApiSensitive({
    function: operation,
    dry_run: dryRun,
    purpose: "",
    started_at: now,
    ended_at: now,
    duration_ms: 0,
    attempts: 0,
    status: "error",
    status_code: statusCode,
    request: {
      function: operation,
      params: {},
      estimated_calls: 1,
      mutates: MUTATING_OPERATIONS.has(operation),
    },
    response_headers: error instanceof AshrApiError ? error.responseHeaders : {},
    error: errorPayload,
    output_path: outputPath,
    field_map_version: ASHR_API_FIELD_MAP_VERSION,
  }) as AshrApiCallRecord;
}

function isCallRecord(value: JsonRecord): boolean {
  return typeof value.function === "string" && typeof value.dry_run === "boolean" && value.field_map_version === ASHR_API_FIELD_MAP_VERSION;
}

function summaryLine(record: AshrApiCallRecord, outputPath: string | undefined): string {
  return [
    `function=${record.function}`,
    `status=${record.status}`,
    `dry_run=${record.dry_run}`,
    `attempts=${record.attempts}`,
    `status_code=${record.status_code ?? "null"}`,
    `output=${outputPath ?? "-"}`,
  ].join(" ");
}

function formatErrorMessage(error: unknown): string {
  if (error instanceof AshrApiError || error instanceof MissingAshrApiKeyError || error instanceof Error) {
    return redactApiText(error.message);
  }
  return redactApiText(String(error));
}

function usage(): string {
  return `Usage: ashr-clone-probe <operation> [options]

Operations:
  ${OPERATIONS.join(", ")}

Defaults:
  Commands are dry-run plans unless --execute is provided.
  Successful commands write a JSON probe record to docs/evidence/private_refs by default.
  Stdout prints a one-line summary unless --print-record is provided.
  Use --output - to skip writing a file.

Options:
  --execute
  --allow-mutate
  --output <path>
  --base-url <url>
  --timeout <seconds>
  --max-retries <count>
  --retry-backoff-ms <ms>
  --print-record
  --limit <count>
  --cursor <cursor>
  --status <status>
  --dataset-id <id>
  --run-id <id>
  --request-id <id>
  --runner-id <id>
  --requestor-id <id>
  --result-file <path>
  --request-name <name>
  --request-file <path>
  --request-schema-file <path>
  --allow-media-generation
  --allow-non-text-inputs
  --max-request-variations <count>
  --poll-timeout <seconds>
  --poll-interval <seconds>
`;
}

function splitOption(raw: string): [string, string | undefined] {
  const separator = raw.indexOf("=");
  if (separator === -1) {
    return [raw, undefined];
  }
  return [raw.slice(0, separator), raw.slice(separator + 1)];
}

function readOptionValue(argv: readonly string[], index: number, name: string, inlineValue: string | undefined): [string, number] {
  if (inlineValue !== undefined) {
    if (inlineValue.length === 0) {
      throw new CliUsageError(`${name} requires a value`);
    }
    return [inlineValue, index];
  }
  const nextIndex = index + 1;
  const value = argv[nextIndex];
  if (value === undefined || value.startsWith("--")) {
    throw new CliUsageError(`${name} requires a value`);
  }
  return [value, nextIndex];
}

function rejectInlineValue(name: string, inlineValue: string | undefined): void {
  if (inlineValue !== undefined) {
    throw new CliUsageError(`${name} does not accept a value`);
  }
}

function parseInteger(value: string, name: string, options: { min: number }): number {
  if (!/^-?\d+$/.test(value)) {
    throw new CliUsageError(`${name} must be an integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < options.min) {
    throw new CliUsageError(`${name} must be an integer >= ${options.min}`);
  }
  return parsed;
}

function requireOperation(operation: ProbeOperation | undefined): ProbeOperation {
  if (operation === undefined) {
    throw new CliUsageError("operation is required");
  }
  return operation;
}

function requireNumber(value: number | undefined, message: string): number {
  if (value === undefined) {
    throw new CliUsageError(message);
  }
  return value;
}

function requireText(value: string | undefined, message: string): string {
  if (value === undefined || value.length === 0) {
    throw new CliUsageError(message);
  }
  return value;
}

function isOperation(value: string): value is ProbeOperation {
  return (OPERATIONS as readonly string[]).includes(value);
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  main().then((code) => {
    process.exitCode = code;
  });
}
