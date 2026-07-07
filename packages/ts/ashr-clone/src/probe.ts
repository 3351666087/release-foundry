#!/usr/bin/env node
import { createHash } from "node:crypto";
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
  summarizeGenerationRequest,
} from "./api-client.js";

type JsonRecord = Record<string, unknown>;
type WritableStreamLike = { write(chunk: string): unknown };
type QuotaGateSummary = JsonRecord & { decision: string };
type QuotaGateIssue = JsonRecord & { code: string; message: string };
type QuotaGateValidation = JsonRecord & { valid: boolean; gate: QuotaGateSummary; issues: QuotaGateIssue[] };

const API_PROBE_BATCH_PLAN_SCHEMA_VERSION = "ashr.clone.api_probe_batch_plan.v1";
const API_PROBE_GATE_VALIDATION_SCHEMA_VERSION = "ashr.clone.api_probe_gate_validation.v1";
const API_PROBE_TARGET_BINDING_SCHEMA_VERSION = "ashr.clone.api_probe_target_binding.v1";
const DEFAULT_QUOTA_GATE_TTL_SECONDS = 24 * 60 * 60;

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
  quotaGateRecord?: string;
  quotaGateTtlSeconds: number;
  allowQuotaOverride: boolean;
  quotaOverrideReason?: string;
  quotaGateSummary?: QuotaGateSummary;
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
    await validateExecuteGuards(args);
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
      const record = await client.createRun({
        ...callOptions,
        datasetId: requireNumber(args.datasetId, "--dataset-id is required for create-run"),
        result,
        runnerId: args.runnerId,
      });
      return attachQuotaGate(record, args.quotaGateSummary);
    }
    case "create-request": {
      const request = await readJsonObject(requireText(args.requestFile, "--request-file is required for create-request"), "--request-file");
      const requestInputSchema = args.requestSchemaFile
        ? await readJsonObject(args.requestSchemaFile, "--request-schema-file")
        : undefined;
      const record = await client.createRequest({
        ...callOptions,
        requestName: requireText(args.requestName, "--request-name is required for create-request"),
        request,
        requestInputSchema,
        requestorId: args.requestorId,
        allowMediaGeneration: args.allowMediaGeneration,
        allowNonTextInputs: args.allowNonTextInputs,
        maxRequestVariations: args.maxRequestVariations,
      });
      return attachQuotaGate(record, args.quotaGateSummary);
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
    quotaGateTtlSeconds: DEFAULT_QUOTA_GATE_TTL_SECONDS,
    allowQuotaOverride: false,
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
      case "--allow-quota-override":
        rejectInlineValue(name, inlineValue);
        args.allowQuotaOverride = true;
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
      case "--quota-gate-record": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.quotaGateRecord = value;
        index = nextIndex;
        break;
      }
      case "--quota-gate-ttl-seconds": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.quotaGateTtlSeconds = parseInteger(value, name, { min: 0 });
        index = nextIndex;
        break;
      }
      case "--quota-override-reason": {
        const [value, nextIndex] = readOptionValue(argv, index, name, inlineValue);
        args.quotaOverrideReason = value;
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

async function validateExecuteGuards(args: ProbeCliArgs): Promise<void> {
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
  args.quotaGateSummary = await enforceMutatingQuotaGate(args, operation);
}

async function enforceMutatingQuotaGate(args: ProbeCliArgs, operation: ProbeOperation): Promise<QuotaGateSummary> {
  const override = args.allowQuotaOverride;
  const reason = (args.quotaOverrideReason ?? "").trim();
  if (args.quotaGateRecord === undefined) {
    if (override) {
      requireQuotaOverrideReason(reason);
      return overrideQuotaGate(reason);
    }
    throw new CliUsageError(`${operation} execution requires --quota-gate-record from plan-batch or --allow-quota-override with an audit reason`);
  }

  const quotaGateRecord = await readJsonObject(args.quotaGateRecord, "--quota-gate-record");
  const validation = validateQuotaGateRecord(quotaGateRecord, {
    operation,
    ttlSeconds: args.quotaGateTtlSeconds,
    expectedBinding: await expectedQuotaGateBinding(args, operation),
  });
  const quotaGate = validation.gate;
  if (quotaGate.decision === "go") {
    if (!validation.valid) {
      throw new CliUsageError(quotaGateValidationErrorMessage(validation));
    }
    return withQuotaOverride(withQuotaValidation(quotaGate, validation), false, null);
  }
  if (quotaGate.decision === "stop" || quotaGate.decision === "wait") {
    if (override) {
      requireQuotaOverrideReason(reason);
      return withQuotaOverride(withQuotaValidation(quotaGate, validation), true, reason);
    }
    if (!validation.valid) {
      throw new CliUsageError(quotaGateValidationErrorMessage(validation));
    }
    throw new CliUsageError(`${operation} execution blocked by quota gate decision=${quotaGate.decision}; rerun after reset evidence or pass --allow-quota-override with --quota-override-reason`);
  }
  throw new CliUsageError(`--quota-gate-record has unsupported quota_stop_go.decision=${quotaGate.decision}`);
}

function extractPlanBatchQuotaGate(record: JsonRecord): { plan: JsonRecord; gate: QuotaGateSummary } {
  const response = isRecord(record.response) ? record.response : undefined;
  const plan = response && isRecord(response.plan) ? response.plan : undefined;
  const hasPlanSchema = plan?.schema_version === API_PROBE_BATCH_PLAN_SCHEMA_VERSION;
  if (!plan || (record.schema_version !== API_PROBE_BATCH_PLAN_SCHEMA_VERSION && !hasPlanSchema) || record.function !== "plan_batch") {
    throw new CliUsageError(`--quota-gate-record must be a plan-batch record with schema_version=${API_PROBE_BATCH_PLAN_SCHEMA_VERSION} and function=plan_batch`);
  }
  const gate = plan && isRecord(plan.quota_stop_go) ? plan.quota_stop_go : undefined;
  if (!gate || typeof gate.decision !== "string" || !["go", "stop", "wait"].includes(gate.decision)) {
    throw new CliUsageError("--quota-gate-record must contain response.plan.quota_stop_go.decision of go, stop, or wait");
  }
  return { plan, gate: redactApiSensitive({ ...gate }) as QuotaGateSummary };
}

function validateQuotaGateRecord(
  record: JsonRecord,
  options: { operation: ProbeOperation; ttlSeconds: number; expectedBinding?: JsonRecord },
): QuotaGateValidation {
  if (!Number.isSafeInteger(options.ttlSeconds) || options.ttlSeconds < 0) {
    throw new CliUsageError("--quota-gate-ttl-seconds must be an integer >= 0");
  }

  const { plan, gate } = extractPlanBatchQuotaGate(record);
  const issues: QuotaGateIssue[] = [];
  const targetOperation = typeof plan.target_operation === "string" ? plan.target_operation : null;
  if (targetOperation !== options.operation) {
    issues.push({
      code: "target_operation_mismatch",
      message: `quota gate target_operation=${JSON.stringify(targetOperation)} does not match requested operation=${JSON.stringify(options.operation)}`,
    });
  }

  const createdAt = typeof plan.created_at === "string" ? plan.created_at : null;
  const createdAtMs = createdAt ? parseUtcTimestamp(createdAt) : null;
  let ageSeconds: number | null = null;
  if (createdAt !== null && createdAtMs === null) {
    issues.push({ code: "invalid_created_at", message: "quota gate plan.created_at is not a valid ISO timestamp" });
  } else if (createdAt === null && options.ttlSeconds > 0) {
    issues.push({ code: "missing_created_at", message: "quota gate plan.created_at is required when TTL validation is enabled" });
  }
  if (createdAtMs !== null) {
    ageSeconds = Math.max(0, Math.trunc((Date.now() - createdAtMs) / 1000));
    if (options.ttlSeconds > 0 && ageSeconds > options.ttlSeconds) {
      issues.push({
        code: "stale_gate",
        message: `quota gate is stale: age_seconds=${ageSeconds} exceeds ttl_seconds=${options.ttlSeconds}`,
      });
    }
  }

  if (gate.decision === "go") {
    try {
      validateQuotaGoGate(gate);
    } catch (error) {
      issues.push({
        code: "go_without_quota_evidence",
        message: formatErrorMessage(error),
      });
    }
  }

  const targetBinding = targetBindingSummary(plan.target_binding);
  if (options.expectedBinding !== undefined) {
    validateTargetBinding(plan.target_binding, options.expectedBinding, issues);
  }
  const binding = quotaGatePlanBinding(plan, issues);
  return redactApiSensitive({
    valid: issues.length === 0,
    schema_version: API_PROBE_GATE_VALIDATION_SCHEMA_VERSION,
    gate: { ...gate },
    target_operation: targetOperation,
    expected_target_operation: options.operation,
    created_at: createdAt,
    age_seconds: ageSeconds,
    ttl_seconds: options.ttlSeconds,
    target_binding: targetBinding,
    expected_target_binding: targetBindingSummary(options.expectedBinding),
    ...binding,
    issues,
  }) as QuotaGateValidation;
}

async function expectedQuotaGateBinding(args: ProbeCliArgs, operation: ProbeOperation): Promise<JsonRecord | undefined> {
  if (operation !== "create-request") {
    return undefined;
  }
  const request = await readJsonObject(requireText(args.requestFile, "--request-file is required to validate a create-request quota gate target binding"), "--request-file");
  const requestInputSchema = args.requestSchemaFile
    ? await readJsonObject(args.requestSchemaFile, "--request-schema-file")
    : undefined;
  const requestInputSchemaSource = requestInputSchema === undefined ? "client_default" : "file";
  return buildTargetBinding({
    targetOperation: operation,
    request,
    requestInputSchema,
    requestInputSchemaSource,
    allowMediaGeneration: args.allowMediaGeneration,
    allowNonTextInputs: args.allowNonTextInputs,
    maxRequestVariations: args.maxRequestVariations,
  });
}

function buildTargetBinding(options: {
  targetOperation: ProbeOperation;
  request: JsonRecord;
  requestInputSchema?: JsonRecord;
  requestInputSchemaSource: string;
  allowMediaGeneration: boolean;
  allowNonTextInputs: boolean;
  maxRequestVariations: number;
}): JsonRecord {
  const preflight = summarizeGenerationRequest(options.request);
  const modalities = buildModalityOrder(preflight);
  const smallBatchSize = 1;
  const batchSize = inferredBatchSize(preflight, smallBatchSize);
  const components: JsonRecord = {
    target_operation: options.targetOperation,
    request_fingerprint: stableSha256(options.request),
    request_input_schema_fingerprint: options.requestInputSchema === undefined ? null : stableSha256(options.requestInputSchema),
    request_input_schema_source: options.requestInputSchemaSource,
    allow_media_generation: options.allowMediaGeneration,
    allow_non_text_inputs: options.allowNonTextInputs,
    max_request_variations: options.maxRequestVariations,
    small_batch_size: smallBatchSize,
    batch_size: batchSize,
    modalities,
  };
  return redactApiSensitive({
    schema_version: API_PROBE_TARGET_BINDING_SCHEMA_VERSION,
    target_operation: options.targetOperation,
    binding_scope: "request-payload",
    request_fingerprint: components.request_fingerprint,
    request_input_schema_fingerprint: components.request_input_schema_fingerprint,
    request_input_schema_source: options.requestInputSchemaSource,
    allow_media_generation: options.allowMediaGeneration,
    allow_non_text_inputs: options.allowNonTextInputs,
    max_request_variations: options.maxRequestVariations,
    small_batch_size: smallBatchSize,
    batch_size: batchSize,
    modalities,
    fingerprint: stableSha256(components),
    fingerprint_fields: Object.keys(components).sort(),
    raw_request_not_recorded: true,
  }) as JsonRecord;
}

function validateQuotaGoGate(quotaGate: QuotaGateSummary): void {
  const reset = isRecord(quotaGate.reset) ? quotaGate.reset : {};
  const headerKeys = Array.isArray(reset.header_keys) ? reset.header_keys : [];
  const hasEvidence = quotaGate.quota_or_reset_evidence_present === true || isRecord(quotaGate.quota) || headerKeys.length > 0;
  if (quotaGate.source === "not-provided" || !hasEvidence) {
    throw new CliUsageError("--quota-gate-record decision=go requires reviewed quota/reset evidence; rerun plan-batch with --quota-record or use an audited override");
  }
}

function requireQuotaOverrideReason(reason: string): void {
  if (reason.length < 12) {
    throw new CliUsageError("--allow-quota-override requires --quota-override-reason with at least 12 characters");
  }
}

function overrideQuotaGate(reason: string): QuotaGateSummary {
  return redactApiSensitive({
    decision: "override",
    source: "not-provided",
    override: { used: true, reason },
  }) as QuotaGateSummary;
}

function withQuotaOverride(quotaGate: QuotaGateSummary, used: boolean, reason: string | null): QuotaGateSummary {
  return redactApiSensitive({
    ...quotaGate,
    override: { used, reason },
  }) as QuotaGateSummary;
}

function withQuotaValidation(quotaGate: QuotaGateSummary, validation: QuotaGateValidation): QuotaGateSummary {
  return redactApiSensitive({
    ...quotaGate,
    validation: { ...validation, gate: { ...validation.gate } },
  }) as QuotaGateSummary;
}

function quotaGateValidationErrorMessage(validation: QuotaGateValidation): string {
  const messages = validation.issues
    .map((issue) => (typeof issue.message === "string" ? issue.message : "unknown quota gate validation issue"))
    .filter((message) => message.length > 0);
  return `quota gate validation failed: ${messages.length > 0 ? messages.join("; ") : "unknown quota gate validation issue"}`;
}

function quotaGatePlanBinding(plan: JsonRecord, issues: QuotaGateIssue[]): JsonRecord {
  const binding: JsonRecord = {};
  assignOptionalIntegerBinding(binding, issues, plan, "small_batch_size", "response.plan.small_batch_size", { min: 1 });
  assignOptionalIntegerBinding(binding, issues, plan, "batch_size", "response.plan.batch_size", { min: 1 });
  assignOptionalIntegerBinding(binding, issues, plan, "estimated_calls", "response.plan.estimated_calls", { min: 0 });
  assignOptionalIntegerBinding(binding, issues, plan, "estimated_real_api_calls", "response.plan.estimated_real_api_calls", { min: 0 });

  if (plan.phases !== undefined) {
    if (!Array.isArray(plan.phases)) {
      issues.push({ code: "invalid_phases", message: "quota gate response.plan.phases must be an array when present" });
    } else {
      const phases: JsonRecord[] = [];
      for (const [index, phaseValue] of plan.phases.entries()) {
        if (!isRecord(phaseValue)) {
          issues.push({ code: "invalid_phase", message: `quota gate response.plan.phases[${index}] must be an object` });
          continue;
        }
        const phase: JsonRecord = {};
        if (typeof phaseValue.phase === "string") {
          phase.phase = phaseValue.phase;
        }
        assignOptionalIntegerBinding(phase, issues, phaseValue, "batch_size", `response.plan.phases[${index}].batch_size`, { min: 0 });
        assignOptionalIntegerBinding(phase, issues, phaseValue, "estimated_real_api_calls", `response.plan.phases[${index}].estimated_real_api_calls`, { min: 0 });
        if (Object.keys(phase).length > 0) {
          phases.push(phase);
        }
      }
      if (phases.length > 0) {
        binding.phases = phases;
      }
    }
  }

  return binding;
}

function validateTargetBinding(actual: unknown, expected: JsonRecord, issues: QuotaGateIssue[]): void {
  if (!isRecord(actual)) {
    issues.push({ code: "missing_target_binding", message: "quota gate response.plan.target_binding is required for this mutating request" });
    return;
  }
  if (actual.schema_version !== API_PROBE_TARGET_BINDING_SCHEMA_VERSION) {
    issues.push({ code: "invalid_target_binding_schema", message: `quota gate target_binding.schema_version must be ${API_PROBE_TARGET_BINDING_SCHEMA_VERSION}` });
  }
  if (typeof actual.fingerprint !== "string" || typeof expected.fingerprint !== "string" || actual.fingerprint !== expected.fingerprint) {
    issues.push({ code: "target_binding_mismatch", message: "quota gate target_binding.fingerprint does not match the current request payload and execution guardrails" });
    return;
  }
  for (const field of [
    "target_operation",
    "request_fingerprint",
    "request_input_schema_fingerprint",
    "request_input_schema_source",
    "allow_media_generation",
    "allow_non_text_inputs",
    "max_request_variations",
    "small_batch_size",
    "batch_size",
    "modalities",
  ]) {
    if (JSON.stringify(actual[field]) !== JSON.stringify(expected[field])) {
      issues.push({ code: "target_binding_field_mismatch", message: `quota gate target_binding.${field} does not match the current request` });
      return;
    }
  }
}

function targetBindingSummary(value: unknown): JsonRecord | null {
  if (!isRecord(value)) {
    return null;
  }
  const fields = [
    "schema_version",
    "target_operation",
    "binding_scope",
    "fingerprint",
    "request_fingerprint",
    "request_input_schema_fingerprint",
    "request_input_schema_source",
    "allow_media_generation",
    "allow_non_text_inputs",
    "max_request_variations",
    "small_batch_size",
    "batch_size",
    "modalities",
    "raw_request_not_recorded",
  ];
  const summary: JsonRecord = {};
  for (const field of fields) {
    if (field in value) {
      summary[field] = value[field];
    }
  }
  return redactApiSensitive(summary) as JsonRecord;
}

function buildModalityOrder(preflight: JsonRecord): string[] {
  const enabled = new Map<string, Set<string>>();
  const acceptedFlags = isRecord(preflight.accepted_input_flags) ? preflight.accepted_input_flags : {};
  for (const modality of ["text", "image", "audio", "file", "video", "conversation"]) {
    if (acceptedFlags[modality] === true) {
      addEnabledModality(enabled, modality, "accepted_inputs");
    }
  }
  const mediaGeneration = isRecord(preflight.media_generation) ? preflight.media_generation : {};
  const mediaMap: Record<string, string> = { audio: "audio", files: "file", images: "image", videos: "video", simulations: "simulation" };
  for (const [field, modality] of Object.entries(mediaMap)) {
    if (mediaGeneration[field] === true) {
      addEnabledModality(enabled, modality, "media_generation");
    }
  }
  if (enabled.size === 0) {
    addEnabledModality(enabled, "text", "default");
  }
  return ["text", "image", "audio", "file", "video", "conversation", "simulation"].filter((modality) => enabled.has(modality));
}

function addEnabledModality(enabled: Map<string, Set<string>>, modality: string, source: string): void {
  const existing = enabled.get(modality) ?? new Set<string>();
  existing.add(source);
  enabled.set(modality, existing);
}

function inferredBatchSize(preflight: JsonRecord, smallBatchSize: number): number {
  return typeof preflight.num_variations === "number" && Number.isSafeInteger(preflight.num_variations)
    ? Math.max(smallBatchSize, preflight.num_variations)
    : Math.max(smallBatchSize, 2);
}

function assignOptionalIntegerBinding(
  target: JsonRecord,
  issues: QuotaGateIssue[],
  source: JsonRecord,
  field: string,
  path: string,
  options: { min: number },
): void {
  const value = source[field];
  if (value === undefined) {
    return;
  }
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < options.min) {
    issues.push({ code: "invalid_numeric_binding", message: `quota gate ${path} must be an integer >= ${options.min} when present` });
    return;
  }
  target[field] = value;
}

function parseUtcTimestamp(value: string): number | null {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function stableSha256(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonicalJson(value)).digest("hex")}`;
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalValue(value));
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => canonicalValue(item));
  }
  if (isRecord(value)) {
    const sorted: JsonRecord = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = canonicalValue(value[key]);
    }
    return sorted;
  }
  return value;
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
    return attachQuotaGate(record, args.quotaGateSummary);
  }
  const operation = requireOperation(args.operation);
  const now = new Date().toISOString();
  const statusCode = error instanceof AshrApiError ? error.statusCode : null;
  const errorPayload = error instanceof AshrApiError
    ? error.toJSON()
    : { message: formatErrorMessage(error), status_code: statusCode, error_kind: error instanceof MissingAshrApiKeyError ? "auth" : "client" };
  const record = redactApiSensitive({
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
  return attachQuotaGate(record, args.quotaGateSummary);
}

function attachQuotaGate(record: AshrApiCallRecord, quotaGate: QuotaGateSummary | undefined): AshrApiCallRecord {
  if (quotaGate === undefined) {
    return record;
  }
  const safeGate = redactApiSensitive(quotaGate) as JsonRecord;
  if (isRecord(record.request)) {
    if (isRecord(record.request.preflight)) {
      record.request.preflight.quota_gate = safeGate;
    } else {
      record.request.quota_gate = safeGate;
    }
  }
  return record;
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
  --quota-gate-record <path>       Required for mutating --execute; must be plan-batch evidence.
  --quota-gate-ttl-seconds <count> Maximum age for plan-batch gate evidence. Default ${DEFAULT_QUOTA_GATE_TTL_SECONDS}; 0 disables.
  --allow-quota-override
  --quota-override-reason <text>
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
