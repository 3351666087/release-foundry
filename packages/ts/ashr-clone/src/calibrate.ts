#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
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
type QuotaGateSummary = JsonRecord & { decision: string };
type QuotaGateIssue = JsonRecord & { code: string; message: string };
type QuotaGateValidation = JsonRecord & { valid: boolean; gate: QuotaGateSummary; issues: QuotaGateIssue[] };

const API_PROBE_BATCH_PLAN_SCHEMA_VERSION = "ashr.clone.api_probe_batch_plan.v1";
const API_PROBE_GATE_VALIDATION_SCHEMA_VERSION = "ashr.clone.api_probe_gate_validation.v1";
const DEFAULT_QUOTA_GATE_TTL_SECONDS = 24 * 60 * 60;
const CALIBRATION_QUOTA_GATE_TARGET_OPERATION = "create-request";
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const PRIVATE_EVIDENCE_DIR = resolve(REPO_ROOT, "docs/evidence/private_refs");

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
  allowNonprivateOutput: boolean;
  baseUrl?: string;
  timeoutSeconds: number;
  maxRetries: number;
  retryBackoffMs: number;
  quotaGateRecord?: string;
  quotaGateTtlSeconds: number;
  allowQuotaOverride: boolean;
  quotaOverrideReason?: string;
  quotaGateSummary?: QuotaGateSummary;
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
    const outputPath = args.output ?? defaultOutputPath(args.execute);
    enforcePrivateStdoutPolicy(args);
    enforcePrivateOutputPath(args, outputPath);
    await validateCalibrationGuards(args);
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
  enforcePrivateOutputPath(args, outputPath);
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
      const record = errorStepRecord(step, error, dryRun, stepOutput, args.quotaGateSummary);
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
      mutating_execute_requires_quota_gate: true,
      quota_gate_ttl_seconds: args.quotaGateTtlSeconds,
      quota_gate: args.quotaGateSummary ?? null,
      paid_media_requires_allow_paid_media: true,
      max_retries_for_execute: args.execute ? args.maxRetries : null,
      raw_records_private: true,
      output_policy: outputPolicy(args, outputPath),
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
    allowNonprivateOutput: false,
    timeoutSeconds: 30,
    maxRetries: 2,
    retryBackoffMs: 500,
    quotaGateTtlSeconds: DEFAULT_QUOTA_GATE_TTL_SECONDS,
    allowQuotaOverride: false,
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
      case "--allow-quota-override":
        args.allowQuotaOverride = true;
        break;
      case "--allow-nonprivate-output":
        args.allowNonprivateOutput = true;
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
      case "--quota-gate-record":
        args.quotaGateRecord = requireOptionValue(readValue(), name);
        break;
      case "--quota-gate-ttl-seconds":
        args.quotaGateTtlSeconds = nonNegativeInteger(readValue(), name);
        break;
      case "--quota-override-reason":
        args.quotaOverrideReason = requireOptionValue(readValue(), name);
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

async function validateCalibrationGuards(args: CalibrationArgs): Promise<void> {
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
  if (args.execute && args.includeMutating) {
    args.quotaGateSummary = await enforceMutatingQuotaGate(args);
  }
}

async function enforceMutatingQuotaGate(args: CalibrationArgs): Promise<QuotaGateSummary> {
  const override = args.allowQuotaOverride;
  const reason = (args.quotaOverrideReason ?? "").trim();
  if (args.quotaGateRecord === undefined) {
    if (override) {
      requireQuotaOverrideReason(reason);
      return overrideQuotaGate(reason);
    }
    throw new CalibrationUsageError("mutating calibration execution requires --quota-gate-record from plan-batch or --allow-quota-override with an audit reason");
  }

  const quotaGateRecord = await readJsonObject(args.quotaGateRecord, "--quota-gate-record");
  const validation = validateQuotaGateRecord(quotaGateRecord, {
    targetOperation: CALIBRATION_QUOTA_GATE_TARGET_OPERATION,
    ttlSeconds: args.quotaGateTtlSeconds,
    expectedModalities: expectedCalibrationGateModalities(args),
    expectedRequestFingerprints: requestFingerprintsForModalities(selectedCalibrationModalities(args)),
  });
  const quotaGate = validation.gate;
  if (quotaGate.decision === "go") {
    if (!validation.valid) {
      throw new CalibrationUsageError(quotaGateValidationErrorMessage(validation));
    }
    return withQuotaOverride(withQuotaValidation(quotaGate, validation), false, null);
  }
  if (quotaGate.decision === "stop" || quotaGate.decision === "wait") {
    if (override) {
      requireQuotaOverrideReason(reason);
      return withQuotaOverride(withQuotaValidation(quotaGate, validation), true, reason);
    }
    if (!validation.valid) {
      throw new CalibrationUsageError(quotaGateValidationErrorMessage(validation));
    }
    throw new CalibrationUsageError(`mutating calibration execution blocked by quota gate decision=${quotaGate.decision}; rerun after reset evidence or pass --allow-quota-override with --quota-override-reason`);
  }
  throw new CalibrationUsageError(`--quota-gate-record has unsupported quota_stop_go.decision=${quotaGate.decision}`);
}

function extractPlanBatchQuotaGate(record: JsonRecord): { plan: JsonRecord; gate: QuotaGateSummary } {
  const response = isRecord(record.response) ? record.response : undefined;
  const plan = response && isRecord(response.plan) ? response.plan : undefined;
  const hasPlanSchema = plan?.schema_version === API_PROBE_BATCH_PLAN_SCHEMA_VERSION;
  if (!plan || (record.schema_version !== API_PROBE_BATCH_PLAN_SCHEMA_VERSION && !hasPlanSchema) || record.function !== "plan_batch") {
    throw new CalibrationUsageError(`--quota-gate-record must be a plan-batch record with schema_version=${API_PROBE_BATCH_PLAN_SCHEMA_VERSION} and function=plan_batch`);
  }
  const gate = plan && isRecord(plan.quota_stop_go) ? plan.quota_stop_go : undefined;
  if (!gate || typeof gate.decision !== "string" || !["go", "stop", "wait"].includes(gate.decision)) {
    throw new CalibrationUsageError("--quota-gate-record must contain response.plan.quota_stop_go.decision of go, stop, or wait");
  }
  return { plan, gate: redactApiSensitive({ ...gate }) as QuotaGateSummary };
}

function validateQuotaGateRecord(
  record: JsonRecord,
  options: { targetOperation: string; ttlSeconds: number; expectedModalities: CalibrationModality[]; expectedRequestFingerprints: JsonRecord },
): QuotaGateValidation {
  if (!Number.isSafeInteger(options.ttlSeconds) || options.ttlSeconds < 0) {
    throw new CalibrationUsageError("--quota-gate-ttl-seconds must be an integer >= 0");
  }

  const { plan, gate } = extractPlanBatchQuotaGate(record);
  const issues: QuotaGateIssue[] = [];
  const targetOperation = typeof plan.target_operation === "string" ? plan.target_operation : null;
  if (targetOperation !== options.targetOperation) {
    issues.push({
      code: "target_operation_mismatch",
      message: `quota gate target_operation=${JSON.stringify(targetOperation)} does not match requested operation=${JSON.stringify(options.targetOperation)}`,
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

  const binding = quotaGatePlanBinding(plan, issues, options.expectedModalities, options.expectedRequestFingerprints);
  return redactApiSensitive({
    valid: issues.length === 0,
    schema_version: API_PROBE_GATE_VALIDATION_SCHEMA_VERSION,
    gate: { ...gate },
    target_operation: targetOperation,
    expected_target_operation: options.targetOperation,
    created_at: createdAt,
    age_seconds: ageSeconds,
    ttl_seconds: options.ttlSeconds,
    ...binding,
    issues,
  }) as QuotaGateValidation;
}

function validateQuotaGoGate(quotaGate: QuotaGateSummary): void {
  const reset = isRecord(quotaGate.reset) ? quotaGate.reset : {};
  const headerKeys = Array.isArray(reset.header_keys) ? reset.header_keys : [];
  const hasEvidence = quotaGate.quota_or_reset_evidence_present === true || isRecord(quotaGate.quota) || headerKeys.length > 0;
  if (quotaGate.source === "not-provided" || !hasEvidence) {
    throw new CalibrationUsageError("--quota-gate-record decision=go requires reviewed quota/reset evidence; rerun plan-batch with --quota-record or use an audited override");
  }
}

function requireQuotaOverrideReason(reason: string): void {
  if (reason.length < 12) {
    throw new CalibrationUsageError("--allow-quota-override requires --quota-override-reason with at least 12 characters");
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

function quotaGatePlanBinding(plan: JsonRecord, issues: QuotaGateIssue[], expectedModalities: CalibrationModality[], expectedRequestFingerprints: JsonRecord): JsonRecord {
  const binding: JsonRecord = {};
  const planModalities = planModalitiesBinding(plan, issues);
  if (planModalities !== undefined) {
    binding.modalities = planModalities;
    binding.expected_modalities = expectedModalities;
    if (!sameStringArray(planModalities, expectedModalities)) {
      issues.push({
        code: "modalities_mismatch",
        message: `quota gate modalities=${JSON.stringify(planModalities)} do not match requested calibration modalities=${JSON.stringify(expectedModalities)}`,
      });
    }
  }
  if (plan.request_fingerprint !== undefined) {
    Object.assign(binding, validateRequestFingerprintBinding(plan.request_fingerprint, expectedRequestFingerprints, issues));
  }
  return binding;
}

function validateRequestFingerprintBinding(value: unknown, expected: JsonRecord, issues: QuotaGateIssue[]): JsonRecord {
  const expectedValues = new Set(Object.values(expected).filter((item): item is string => typeof item === "string"));
  const binding: JsonRecord = {
    request_fingerprint: value,
    expected_request_fingerprints: expected,
  };
  if (typeof value === "string") {
    if (expectedValues.size !== 1) {
      issues.push({ code: "request_fingerprint_mismatch", message: "quota gate request_fingerprint must bind every selected calibrator modality when more than one request shape is selected" });
    } else if (!expectedValues.has(value)) {
      issues.push({ code: "request_fingerprint_mismatch", message: "quota gate request_fingerprint does not match the selected calibrator request shape" });
    }
    return binding;
  }
  if (Array.isArray(value)) {
    if (!value.every((item) => typeof item === "string")) {
      issues.push({ code: "invalid_request_fingerprint", message: "quota gate request_fingerprint array must contain only strings" });
    } else if (!sameStringSet(value, [...expectedValues])) {
      issues.push({ code: "request_fingerprint_mismatch", message: "quota gate request_fingerprint array does not match selected calibrator request shapes" });
    }
    return binding;
  }
  if (isRecord(value)) {
    const normalized = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, item]));
    if (!Object.values(normalized).every((item) => typeof item === "string")) {
      issues.push({ code: "invalid_request_fingerprint", message: "quota gate request_fingerprint map values must be strings" });
    } else if (!sameStringRecord(normalized as Record<string, string>, expected as Record<string, string>)) {
      issues.push({ code: "request_fingerprint_mismatch", message: "quota gate request_fingerprint map does not match selected calibrator request shapes" });
    }
    return binding;
  }
  issues.push({ code: "invalid_request_fingerprint", message: "quota gate request_fingerprint must be a string, array, or modality map when present" });
  return binding;
}

function planModalitiesBinding(plan: JsonRecord, issues: QuotaGateIssue[]): CalibrationModality[] | undefined {
  if (plan.modalities === undefined) {
    return undefined;
  }
  if (!Array.isArray(plan.modalities)) {
    issues.push({ code: "invalid_modalities", message: "quota gate response.plan.modalities must be an array when present" });
    return undefined;
  }
  const modalities: CalibrationModality[] = [];
  for (const [index, value] of plan.modalities.entries()) {
    if (typeof value !== "string" || !isCalibrationModality(value)) {
      issues.push({ code: "invalid_modalities", message: `quota gate response.plan.modalities[${index}] must be one of text,image,audio,file,video` });
      continue;
    }
    modalities.push(value);
  }
  return Array.from(new Set(modalities)).sort((left, right) => modalityOrder(left) - modalityOrder(right));
}

function sameStringArray(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  return leftSet.size === rightSet.size && [...leftSet].every((value) => rightSet.has(value));
}

function sameStringRecord(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return sameStringArray(leftKeys, rightKeys) && leftKeys.every((key) => left[key] === right[key]);
}

function expectedCalibrationGateModalities(args: CalibrationArgs): CalibrationModality[] {
  const selected = new Set(selectedCalibrationModalities(args));
  selected.add("text");
  return (["text", "image", "audio", "file", "video"] as CalibrationModality[]).filter((modality) => selected.has(modality));
}

function requestFingerprintsForModalities(modalities: CalibrationModality[]): JsonRecord {
  return Object.fromEntries(modalities.map((modality) => [modality, calibrationRequestFingerprint(modality)]));
}

function calibrationRequestFingerprint(modality: CalibrationModality): string {
  return createHash("sha256").update(JSON.stringify(canonicalValue(requestForModality(modality)))).digest("hex");
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

function selectedCalibrationModalities(args: CalibrationArgs): CalibrationModality[] {
  const defaults: CalibrationModality[] = ["text", "image", "audio", "file", "video"];
  const selected: CalibrationModality[] = args.modalities.length > 0 ? args.modalities : defaults;
  return Array.from(new Set(selected)).sort((left, right) => modalityOrder(left) - modalityOrder(right));
}

function parseModalities(value: string): CalibrationModality[] {
  return value.split(",").map((item) => {
    const modality = item.trim();
    if (!isCalibrationModality(modality)) {
      throw new CalibrationUsageError(`unsupported modality: ${modality}`);
    }
    return modality;
  });
}

function isCalibrationModality(value: string): value is CalibrationModality {
  return ["text", "image", "audio", "file", "video"].includes(value);
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
    run: async (client, options) => {
      const record = await client.createRequest({
        dryRun: options.dryRun,
        outputPath: options.outputPath,
        requestName: `A1 ${modality} API calibration ${options.dryRun ? "dry run" : "small batch"}`,
        request: requestForModality(modality),
        allowMediaGeneration: options.args.allowPaidMedia,
        allowNonTextInputs: true,
        maxRequestVariations: 1,
        purpose: `Create a tiny ${modality} calibration request with first-class AgentInput envelope`,
      });
      return attachQuotaGate(record, options.args.quotaGateSummary);
    },
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

function errorStepRecord(step: CalibrationStep, error: unknown, dryRun: boolean, outputPath: string, quotaGate: QuotaGateSummary | undefined): AshrApiCallRecord {
  if (error instanceof AshrApiError && isRecord(error.response) && isCallRecord(error.response)) {
    const record = redactApiSensitive(error.response) as unknown as AshrApiCallRecord;
    record.output_path = outputPath;
    return step.kind === "mutate" ? attachQuotaGate(record, quotaGate) : record;
  }
  const now = utcNow();
  const statusCode = error instanceof AshrApiError ? error.statusCode : null;
  const errorPayload = error instanceof AshrApiError
    ? error.toJSON()
    : { message: formatErrorMessage(error), status_code: statusCode, error_kind: error instanceof MissingAshrApiKeyError ? "auth" : "client" };
  const record = redactApiSensitive({
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
  return step.kind === "mutate" ? attachQuotaGate(record, quotaGate) : record;
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

function stepOutputPath(manifestPath: string, stepId: string, dryRun: boolean): string {
  const suffix = dryRun ? "dry_run" : "real";
  return resolve(dirname(manifestPath), `a1_ts_api_calibration_${stepId}_${suffix}.json`);
}

function defaultOutputPath(execute: boolean): string {
  return resolve(PRIVATE_EVIDENCE_DIR, `a1_ts_api_calibration_manifest_${execute ? "real" : "dry_run"}.json`);
}

function enforcePrivateStdoutPolicy(args: CalibrationArgs): void {
  if (args.printRecord && requiresPrivateOutput(args) && !args.allowNonprivateOutput) {
    throw new CalibrationUsageError("--print-record is disabled for real API and gate evidence; use the JSON file under docs/evidence/private_refs or pass --allow-nonprivate-output only for synthetic tests");
  }
}

function enforcePrivateOutputPath(args: CalibrationArgs, outputPath: string): void {
  if (args.allowNonprivateOutput || !requiresPrivateOutput(args)) {
    return;
  }
  if (isPrivateOutputPath(outputPath)) {
    return;
  }
  throw new CalibrationUsageError("--output for real API and gate evidence must stay under docs/evidence/private_refs; pass --allow-nonprivate-output only for synthetic tests");
}

function outputPolicy(args: CalibrationArgs, outputPath: string): JsonRecord {
  const required = requiresPrivateOutput(args);
  const isPrivate = isPrivateOutputPath(outputPath);
  return {
    schema_version: "ashr.clone.output_policy.v1",
    private_output_required: required,
    allow_nonprivate_output: Boolean(args.allowNonprivateOutput),
    nonprivate_output_override_used: Boolean(required && args.allowNonprivateOutput && !isPrivate),
    output_is_private: isPrivate,
    sink: isPrivate ? "private_file" : "nonprivate_file",
    private_root: "docs/evidence/private_refs",
    resolved_under_repo: repoRelativeOutputPath(outputPath),
    full_record_stdout_blocked: Boolean(required && !args.allowNonprivateOutput),
  };
}

function repoRelativeOutputPath(outputPath: string): string {
  const target = resolveOutputPath(outputPath);
  const pathFromRepo = relative(REPO_ROOT, target);
  return pathFromRepo.startsWith("..") || isAbsolute(pathFromRepo) ? "<outside-repo>" : pathFromRepo.replaceAll("\\", "/");
}

function requiresPrivateOutput(args: CalibrationArgs): boolean {
  return Boolean(args.execute || args.quotaGateRecord || args.allowQuotaOverride);
}

function isPrivateOutputPath(outputPath: string): boolean {
  const root = resolve(PRIVATE_EVIDENCE_DIR);
  const target = resolveOutputPath(outputPath);
  const pathFromRoot = relative(root, target);
  return pathFromRoot !== "" && !pathFromRoot.startsWith("..") && !isAbsolute(pathFromRoot);
}

function resolveOutputPath(outputPath: string): string {
  return isAbsolute(outputPath) ? resolve(outputPath) : resolve(REPO_ROOT, outputPath);
}

async function writeJson(path: string, value: unknown): Promise<void> {
  const absolutePath = resolve(path);
  await mkdir(dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function readJsonObject(path: string, optionName: string): Promise<JsonRecord> {
  const text = await readFile(path, "utf8");
  const parsed = JSON.parse(text) as unknown;
  if (!isRecord(parsed)) {
    throw new CalibrationUsageError(`${optionName} must contain a JSON object`);
  }
  return parsed;
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

function parseUtcTimestamp(value: string): number | null {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
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
  --allow-nonprivate-output Allow protected real API/gate evidence outside docs/evidence/private_refs for synthetic tests only.
  --base-url <url>          Override Ashr API URL.
  --timeout <seconds>       Request timeout. Default 30.
  --max-retries <count>     Retry count. Real execution requires 0.
  --retry-backoff-ms <ms>   Retry backoff. Default 500.
  --quota-gate-record <path> Plan-batch record required for mutating real execution.
  --quota-gate-ttl-seconds <count> Maximum age for plan-batch gate evidence. Default ${DEFAULT_QUOTA_GATE_TTL_SECONDS}; 0 disables.
  --allow-quota-override    Allow mutating real execution without a go gate.
  --quota-override-reason <text>
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
