#!/usr/bin/env node
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ASHR_API_ENV_VAR,
  ASHR_API_FIELD_MAP_VERSION,
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
type CalibrateStreams = { stdout: WritableStreamLike; stderr: WritableStreamLike };
type CalibrationMode = "dry-run" | "small-batch";
type CalibrationStepKind = "read" | "mutate";
type CalibrationModality = "text" | "image" | "audio" | "file" | "video";

type CalibrationStep = {
  id: string;
  kind: CalibrationStepKind;
  modality?: CalibrationModality;
  estimated_calls: number;
  purpose: string;
  run: (client: AshrApiClient, options: { dryRun: boolean; outputPath: string; args: CalibrationArgs }) => Promise<AshrApiCallRecord>;
};

export interface CalibrationArgs {
  execute: boolean;
  smallBatch: boolean;
  includeMutating: boolean;
  allowPaidMedia: boolean;
  output?: string;
  baseUrl?: string;
  timeoutSeconds: number;
  maxRetries: number;
  retryBackoffMs: number;
  limit: number;
  modalities: CalibrationModality[];
  printRecord: boolean;
  help: boolean;
}

export interface CalibrationManifest extends JsonRecord {
  schema_version: "ashr.clone.api_calibration_manifest.v1";
  mode: CalibrationMode;
  dry_run: boolean;
  status: "planned" | "ok" | "partial" | "error";
  started_at: string;
  ended_at: string;
  duration_ms: number;
  field_map_version: typeof ASHR_API_FIELD_MAP_VERSION;
  env: JsonRecord;
  guardrails: JsonRecord;
  summary: JsonRecord;
  steps: JsonRecord[];
  errors: JsonRecord[];
}

class CalibrationUsageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CalibrationUsageError";
  }
}

export async function main(
  argv: readonly string[] = process.argv.slice(2),
  env: Record<string, string | undefined> = process.env,
  streams: CalibrateStreams = { stdout: process.stdout, stderr: process.stderr },
): Promise<number> {
  let args: CalibrationArgs | undefined;
  try {
    args = parseArgs(argv);
    if (args.help) {
      streams.stdout.write(usage());
      return 0;
    }
    validateCalibrationGuards(args);
    const outputPath = args.output ?? defaultOutputPath(args.execute);
    const manifest = await runCalibration(args, env, outputPath);
    await writeJson(outputPath, manifest);
    if (args.printRecord) {
      streams.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);
    } else {
      streams.stdout.write(summaryLine(manifest, outputPath));
    }
    return manifest.status === "error" ? 2 : 0;
  } catch (error) {
    const message = formatErrorMessage(error);
    streams.stderr.write(`api calibration error: ${message}\n`);
    if (error instanceof MissingAshrApiKeyError) {
      streams.stderr.write(`hint: set ${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} in the current process\n`);
    }
    return 2;
  }
}

export async function runCalibration(args: CalibrationArgs, env: Record<string, string | undefined>, outputPath: string): Promise<CalibrationManifest> {
  const startedAt = utcNow();
  const started = Date.now();
  const dryRun = !args.execute;
  const steps = calibrationSteps(args).filter((step) => args.includeMutating || step.kind === "read");
  const client = AshrApiClient.fromEnv(env, {
    required: args.execute,
    baseUrl: args.baseUrl,
    timeoutMs: args.timeoutSeconds * 1000,
    maxRetries: args.maxRetries,
    retryBackoffMs: args.retryBackoffMs,
  });
  const stepResults: JsonRecord[] = [];
  const errors: JsonRecord[] = [];
  for (const step of steps) {
    const stepOutput = stepOutputPath(outputPath, step.id, dryRun);
    try {
      const record = await step.run(client, { dryRun, outputPath: stepOutput, args });
      await writeJson(stepOutput, record);
      stepResults.push(summarizeStep(step, record, stepOutput));
    } catch (error) {
      const record = errorStepRecord(step, error, dryRun, stepOutput);
      await writeJson(stepOutput, record);
      const summary = summarizeStep(step, record, stepOutput);
      stepResults.push(summary);
      errors.push({ step_id: step.id, error_kind: summary.error_kind ?? "unknown", error_keys: summary.error_keys ?? [], status_code: summary.status_code ?? null });
      if (step.kind === "mutate") {
        break;
      }
    }
  }
  const okCount = stepResults.filter((step) => step.status === "ok" || step.status === "planned").length;
  const status = errors.length === 0 ? (dryRun ? "planned" : "ok") : okCount > 0 ? "partial" : "error";
  const endedAt = utcNow();
  return redactApiSensitive({
    schema_version: "ashr.clone.api_calibration_manifest.v1",
    mode: dryRun ? "dry-run" : "small-batch",
    dry_run: dryRun,
    status,
    started_at: startedAt,
    ended_at: endedAt,
    duration_ms: Math.max(0, Date.now() - started),
    field_map_version: ASHR_API_FIELD_MAP_VERSION,
    env: {
      auth_env_present: [
        ...(env[ASHR_API_ENV_VAR] ? [ASHR_API_ENV_VAR] : []),
        ...(env[ASHR_LABS_API_ENV_VAR] ? [ASHR_LABS_API_ENV_VAR] : []),
      ],
      base_url: client.baseUrl,
    },
    guardrails: {
      execute_requires_small_batch: true,
      mutating_requires_include_mutating: true,
      paid_media_requires_allow_paid_media: true,
      max_retries_for_execute: args.execute ? args.maxRetries : null,
      raw_records_private: true,
    },
    summary: {
      total_steps: stepResults.length,
      read_steps: stepResults.filter((step) => step.kind === "read").length,
      mutating_steps: stepResults.filter((step) => step.kind === "mutate").length,
      ok_or_planned_steps: okCount,
      error_steps: errors.length,
      estimated_calls: steps.reduce((sum, step) => sum + step.estimated_calls, 0),
      modalities: Array.from(new Set(stepResults.map((step) => step.modality).filter(Boolean))).sort(),
    },
    steps: stepResults,
    errors,
  }) as CalibrationManifest;
}

export function parseArgs(argv: readonly string[]): CalibrationArgs {
  const args: CalibrationArgs = {
    execute: false,
    smallBatch: false,
    includeMutating: false,
    allowPaidMedia: false,
    timeoutSeconds: 30,
    maxRetries: 2,
    retryBackoffMs: 500,
    limit: 2,
    modalities: [],
    printRecord: false,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const raw = argv[index];
    if (raw === "-h" || raw === "--help") {
      args.help = true;
      continue;
    }
    if (!raw.startsWith("--")) {
      throw new CalibrationUsageError(`unexpected positional argument: ${raw}`);
    }
    const [name, inlineValue] = splitOption(raw);
    const readValue = () => inlineValue ?? argv[++index];
    switch (name) {
      case "--execute":
        args.execute = true;
        break;
      case "--small-batch":
        args.smallBatch = true;
        break;
      case "--include-mutating":
        args.includeMutating = true;
        break;
      case "--allow-paid-media":
        args.allowPaidMedia = true;
        break;
      case "--output":
        args.output = requireOptionValue(readValue(), name);
        break;
      case "--base-url":
        args.baseUrl = requireOptionValue(readValue(), name);
        break;
      case "--timeout":
        args.timeoutSeconds = positiveNumber(readValue(), name);
        break;
      case "--max-retries":
        args.maxRetries = nonNegativeInteger(readValue(), name);
        break;
      case "--retry-backoff-ms":
        args.retryBackoffMs = nonNegativeInteger(readValue(), name);
        break;
      case "--limit":
        args.limit = positiveInteger(readValue(), name);
        break;
      case "--modality":
        args.modalities.push(...parseModalities(requireOptionValue(readValue(), name)));
        break;
      case "--print-record":
        args.printRecord = true;
        break;
      default:
        throw new CalibrationUsageError(`unknown option: ${name}`);
    }
  }
  return args;
}

function validateCalibrationGuards(args: CalibrationArgs): void {
  if (args.execute && !args.smallBatch) {
    throw new CalibrationUsageError("real API calibration requires --small-batch before --execute");
  }
  if (args.execute && args.maxRetries !== 0) {
    throw new CalibrationUsageError("real API calibration requires --max-retries 0 to avoid duplicate paid calls");
  }
  const selectedModalities = selectedCalibrationModalities(args);
  const paidModalities = selectedModalities.filter((modality) => modality !== "text");
  if (args.includeMutating && paidModalities.length > 0 && !args.allowPaidMedia) {
    throw new CalibrationUsageError("non-text media calibration requires --allow-paid-media after reviewing cost risk");
  }
}


function selectedCalibrationModalities(args: CalibrationArgs): CalibrationModality[] {
  const defaults: CalibrationModality[] = ["text", "image", "audio", "file", "video"];
  const selected: CalibrationModality[] = args.modalities.length > 0 ? args.modalities : defaults;
  return Array.from(new Set(selected)).sort((left, right) => modalityOrder(left) - modalityOrder(right));
}

function parseModalities(value: string): CalibrationModality[] {
  return value.split(",").map((item) => {
    const modality = item.trim();
    if (!["text", "image", "audio", "file", "video"].includes(modality)) {
      throw new CalibrationUsageError(`unsupported modality: ${modality}`);
    }
    return modality as CalibrationModality;
  });
}

function modalityOrder(modality: CalibrationModality): number {
  return ["text", "image", "audio", "file", "video"].indexOf(modality);
}
function calibrationSteps(args: CalibrationArgs): CalibrationStep[] {
  const limit = Math.min(Math.max(1, Math.trunc(args.limit)), 5);
  return [
    {
      id: "init",
      kind: "read",
      estimated_calls: 1,
      purpose: "Resolve Ashr session context and tenant/user/features shape",
      run: (client, options) => client.init({ dryRun: options.dryRun, outputPath: options.outputPath, purpose: "Resolve Ashr session context and tenant/user/features shape" }),
    },
    {
      id: "health-check",
      kind: "read",
      estimated_calls: 1,
      purpose: "Check Ashr API reachability and keep_alive shape",
      run: (client, options) => client.healthCheck({ dryRun: options.dryRun, outputPath: options.outputPath, purpose: "Check Ashr API reachability and keep_alive shape" }),
    },
    {
      id: "list-agents",
      kind: "read",
      estimated_calls: 1,
      purpose: "List tenant agent fields for SDK adapter parity",
      run: (client, options) => client.listAgents({ dryRun: options.dryRun, outputPath: options.outputPath, purpose: "List tenant agent fields for SDK adapter parity" }),
    },
    {
      id: "list-datasets",
      kind: "read",
      estimated_calls: 2,
      purpose: "List dataset fields, pagination, and dataset_source envelopes",
      run: (client, options) => client.listDatasets({ dryRun: options.dryRun, outputPath: options.outputPath, purpose: "List dataset fields, pagination, and dataset_source envelopes", limit }),
    },
    {
      id: "list-requests",
      kind: "read",
      estimated_calls: 2,
      purpose: "List request fields, failure envelopes, and pagination",
      run: (client, options) => client.listRequests({ dryRun: options.dryRun, outputPath: options.outputPath, purpose: "List request fields, failure envelopes, and pagination", limit }),
    },
    ...selectedCalibrationModalities(args).map((modality) => createRequestStep(modality)),
  ];
}

function createRequestStep(modality: CalibrationModality): CalibrationStep {
  return {
    id: `create-request-${modality}`,
    kind: "mutate",
    modality,
    estimated_calls: 2,
    purpose: `Create a tiny ${modality} calibration request with first-class AgentInput envelope`,
    run: (client, options) => client.createRequest({
      dryRun: options.dryRun,
      outputPath: options.outputPath,
      requestName: `A1 ${modality} API calibration ${options.dryRun ? "dry run" : "small batch"}`,
      request: requestForModality(modality),
      allowMediaGeneration: options.args.allowPaidMedia,
      allowNonTextInputs: true,
      maxRequestVariations: 1,
      purpose: `Create a tiny ${modality} calibration request with first-class AgentInput envelope`,
    }),
  };
}

function requestForModality(modality: CalibrationModality): JsonRecord {
  const acceptedInputs: JsonRecord = Object.fromEntries(
    (["text", "image", "audio", "file", "video", "conversation"] as const).map((part) => [part, { enabled: part === modality || part === "text" }]),
  );
  const generationOptions: JsonRecord = {
    generate_images: modality === "image",
    generate_audio: modality === "audio",
    generate_files: modality === "file",
    generate_videos: modality === "video",
    generate_simulations: false,
  };
  return {
    agent: {
      name: `A1 ${modality} calibration agent`,
      description: `Synthetic non-sensitive ${modality} API calibration agent.`,
      accepted_inputs: acceptedInputs,
      output_format: { type: "text" },
      tools: [
        {
          name: "inspect_input",
          description: `Inspect synthetic ${modality} input without external side effects.`,
          parameters: {
            type: "object",
            required: ["summary"],
            properties: { summary: { type: "string" } },
          },
        },
      ],
    },
    context: {
      domain: "api calibration",
      use_case: `Validate ${modality} request shape and paid generation guardrails.`,
      scenario_context: "Use tiny synthetic non-sensitive data only.",
    },
    metadata: {
      dataset_name: `A1 ${modality} API calibration`,
      description: "Generated by A1 env-gated calibration harness.",
      local_secret_policy: "ASHR_API_KEY read from environment only; no key is logged or stored.",
    },
    test_config: {
      strategy: "focused",
      num_variations: 1,
      coverage: { happy_path: true, edge_cases: false, error_handling: false },
    },
    generation_options: generationOptions,
  };
}

function summarizeStep(step: CalibrationStep, record: AshrApiCallRecord, outputPath: string): JsonRecord {
  const response = isRecord(record.response) ? record.response : {};
  const error = isRecord(record.error) ? record.error : {};
  return {
    step_id: step.id,
    kind: step.kind,
    modality: step.modality,
    function: record.function,
    purpose: step.purpose,
    dry_run: record.dry_run,
    status: record.status,
    status_code: record.status_code,
    attempts: record.attempts,
    estimated_calls: step.estimated_calls,
    response_keys: sortedKeys(response),
    response_status: typeof response.status === "string" ? response.status : null,
    response_headers_keys: sortedKeys(record.response_headers),
    response_summary_keys: sortedKeys(record.response_summary),
    top_counts: {
      agents: Array.isArray(response.agents) ? response.agents.length : undefined,
      datasets: Array.isArray(response.datasets) ? response.datasets.length : undefined,
      requests: Array.isArray(response.requests) ? response.requests.length : undefined,
      runs: Array.isArray(response.runs) ? response.runs.length : undefined,
    },
    next_cursor: response.next_cursor ?? null,
    error_keys: sortedKeys(error),
    error_kind: typeof error.error_kind === "string" ? error.error_kind : null,
    private_record_path: outputPath,
  };
}

function errorStepRecord(step: CalibrationStep, error: unknown, dryRun: boolean, outputPath: string): AshrApiCallRecord {
  if (error instanceof AshrApiError && isRecord(error.response) && isCallRecord(error.response)) {
    const record = redactApiSensitive(error.response) as unknown as AshrApiCallRecord;
    record.output_path = outputPath;
    return record;
  }
  const now = utcNow();
  const statusCode = error instanceof AshrApiError ? error.statusCode : null;
  const errorPayload = error instanceof AshrApiError
    ? error.toJSON()
    : { message: formatErrorMessage(error), status_code: statusCode, error_kind: error instanceof MissingAshrApiKeyError ? "auth" : "client" };
  return redactApiSensitive({
    function: step.id,
    dry_run: dryRun,
    purpose: step.purpose,
    started_at: now,
    ended_at: now,
    duration_ms: 0,
    attempts: 0,
    status: "error",
    status_code: statusCode,
    request: { function: step.id, params: {}, estimated_calls: step.estimated_calls, mutates: step.kind === "mutate" },
    response_headers: error instanceof AshrApiError ? error.responseHeaders : {},
    error: errorPayload,
    output_path: outputPath,
    field_map_version: ASHR_API_FIELD_MAP_VERSION,
  }) as AshrApiCallRecord;
}

function isCallRecord(value: JsonRecord): boolean {
  return typeof value.function === "string" && typeof value.dry_run === "boolean" && value.field_map_version === ASHR_API_FIELD_MAP_VERSION;
}

function stepOutputPath(manifestPath: string, stepId: string, dryRun: boolean): string {
  const suffix = dryRun ? "dry_run" : "real";
  return resolve(dirname(manifestPath), `a1_ts_api_calibration_${stepId}_${suffix}.json`);
}

function defaultOutputPath(execute: boolean): string {
  return `docs/evidence/private_refs/a1_ts_api_calibration_manifest_${execute ? "real" : "dry_run"}.json`;
}

async function writeJson(path: string, value: unknown): Promise<void> {
  const absolutePath = resolve(path);
  await mkdir(dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function sortedKeys(value: unknown): string[] {
  return isRecord(value) ? Object.keys(value).sort() : [];
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function splitOption(raw: string): [string, string | undefined] {
  const index = raw.indexOf("=");
  return index === -1 ? [raw, undefined] : [raw.slice(0, index), raw.slice(index + 1)];
}

function requireOptionValue(value: string | undefined, optionName: string): string {
  if (value === undefined || value === "") {
    throw new CalibrationUsageError(`${optionName} requires a value`);
  }
  return value;
}

function positiveNumber(value: string | undefined, optionName: string): number {
  const parsed = Number(requireOptionValue(value, optionName));
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new CalibrationUsageError(`${optionName} must be positive`);
  }
  return parsed;
}

function positiveInteger(value: string | undefined, optionName: string): number {
  const parsed = Math.trunc(positiveNumber(value, optionName));
  if (parsed <= 0) {
    throw new CalibrationUsageError(`${optionName} must be a positive integer`);
  }
  return parsed;
}

function nonNegativeInteger(value: string | undefined, optionName: string): number {
  const parsed = Number(requireOptionValue(value, optionName));
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new CalibrationUsageError(`${optionName} must be a non-negative integer`);
  }
  return parsed;
}

function summaryLine(manifest: CalibrationManifest, outputPath: string): string {
  return [
    `mode=${manifest.mode}`,
    `status=${manifest.status}`,
    `steps=${String(manifest.summary.total_steps ?? 0)}`,
    `errors=${String(manifest.summary.error_steps ?? 0)}`,
    `output=${outputPath}`,
  ].join(" ") + "\n";
}

function formatErrorMessage(error: unknown): string {
  if (error instanceof AshrApiError || error instanceof MissingAshrApiKeyError || error instanceof Error) {
    return redactApiText(error.message);
  }
  return redactApiText(String(error));
}

function usage(): string {
  return `Usage: ashr-clone-calibrate [options]

Runs an env-gated Ashr API calibration batch. Defaults to dry-run plans and writes a
safe manifest plus per-step private records under docs/evidence/private_refs.

Options:
  --execute                 Run real API calls. Requires --small-batch and --max-retries 0.
  --small-batch             Acknowledge bounded first real batch.
  --include-mutating        Include create-request calibration steps.
  --allow-paid-media        Allow paid media generation request steps after cost review.
  --output <path>           Manifest output path.
  --base-url <url>          Override Ashr API URL.
  --timeout <seconds>       Request timeout. Default 30.
  --max-retries <count>     Retry count. Real execution requires 0.
  --retry-backoff-ms <ms>   Retry backoff. Default 500.
  --limit <count>           List limit for read probes. Default 2, capped at 5.
  --modality <type[,type]>  Limit mutating probes to text,image,audio,file,video. Repeatable.
  --print-record            Print full manifest to stdout.
  -h, --help                Show this help.
`;
}

function utcNow(): string {
  return new Date().toISOString();
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  main().then((code) => {
    process.exitCode = code;
  });
}