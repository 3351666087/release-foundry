import { createHash } from "node:crypto";
import { isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import type { AgentInput, AgentTurn, CaseResult, JsonRecord, RunResult } from "./index.js";

export const MIN_MAX_WORKERS = 4;
export const DEFAULT_MAX_WORKERS = 4;
export const DEFAULT_TIMEOUT_SECONDS = 30;
export const LOCAL_RUNNER_ID = "a1-local-runner";
export const LOCAL_DATASET_ID = "local-dataset";
export const LOCAL_RUN_FIELD_MAP_VERSION = "a1.ts.local.v1";

const AGENT_INPUT_SCHEMA_VERSION_VALUE = "releasefoundry.agent_input.v1";
const AGENT_TURN_SCHEMA_VERSION_VALUE = "releasefoundry.agent_turn.v1";
const RUN_RESULT_SCHEMA_VERSION_VALUE = "releasefoundry.run_result.v1";
const PASSED = "passed";
const FAILED = "failed";
const ERROR = "error";
const TIMEOUT = "timeout";
const INPUT_STYLES = ["text", "request", "keyword"] as const;
const AGENT_INPUT_PART_TYPES = ["text", "image", "audio", "file", "video"] as const;

export type AgentInputStyle = (typeof INPUT_STYLES)[number];
export type AgentLike = AgentFunction | AgentObject | AgentConstructor;
export type AgentFunction = (input: unknown, context?: JsonRecord) => unknown | Promise<unknown>;
export type AgentConstructor = new () => AgentObject | AgentFunction;

export interface AgentObject {
  respond?: (input?: unknown, context?: JsonRecord) => unknown | Promise<unknown>;
  reset?: () => unknown | Promise<unknown>;
  clone?: () => AgentObject | AgentFunction;
}

export interface AgentAdapterOptions {
  name?: string;
  raiseErrors?: boolean;
  inputStyle?: AgentInputStyle;
  inputKeyword?: string;
}

export interface RunAgentBatchOptions {
  datasetId?: string;
  runnerId?: string;
  runId?: string;
  maxWorkers?: number | null;
  timeoutSeconds?: number | null;
  inputStyle?: AgentInputStyle;
  inputKeyword?: string;
  metadata?: JsonRecord;
}

export interface RunBatchOptions {
  maxWorkers?: number | null;
  timeoutSeconds?: number | null;
}

export interface LocalEvalRunnerOptions extends RunAgentBatchOptions {
  agent?: AgentLike;
}

export interface LocalObservation extends JsonRecord {
  observation_id: string;
  run_id: string;
  case_id: string;
  turn_index: number;
  event_type: string;
  role: string;
  content?: unknown;
  tool_calls?: JsonRecord[];
  started_at: string;
  ended_at: string;
  latency_ms?: number;
  status: string;
  error?: string;
  metadata: JsonRecord;
  vm_stream?: JsonRecord;
}

export interface LocalGradeResult extends JsonRecord {
  scenario_id: string;
  passed: boolean;
  score: number;
  label: string;
  reason: string;
  expected: JsonRecord;
  actual: JsonRecord;
  metrics: JsonRecord;
}

export interface LocalCaseResult extends CaseResult {
  scenario_id: string;
  title: string;
  started_at: string;
  ended_at: string;
  latency_ms: number;
  observations: LocalObservation[];
  grade: LocalGradeResult;
  expected: JsonRecord;
  error?: string;
  metadata: JsonRecord;
}

export interface LocalRunResult extends RunResult {
  schema_version: typeof RUN_RESULT_SCHEMA_VERSION_VALUE;
  run_id: string;
  dataset_id: string;
  runner_id: string;
  status: string;
  total_cases: number;
  passed: number;
  failed: number;
  errored: number;
  timed_out: number;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  max_workers: number;
  trace_completeness: number;
  cases: LocalCaseResult[];
  aggregate_metrics: JsonRecord;
  metadata: JsonRecord;
  field_map_version: string;
}

export interface LocalRunFixture extends JsonRecord {
  schema: "releasefoundry.run.v1";
  schema_version: "releasefoundry.run.v1";
  name?: string;
  run: JsonRecord;
  events: JsonRecord[];
  vm_stream: JsonRecord[];
  replay: JsonRecord;
  metadata: JsonRecord & { local_only: true; releasefoundry_api_used: false };
}

export class AgentAdapterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgentAdapterError";
  }
}

export class AgentResult implements AgentTurn {
  schema_version: typeof AGENT_TURN_SCHEMA_VERSION_VALUE = AGENT_TURN_SCHEMA_VERSION_VALUE;
  text: string;
  tool_calls: JsonRecord[];
  status: string;
  latency_ms: number;
  metadata: JsonRecord;
  error?: JsonRecord;
  raw?: unknown;

  constructor(options: {
    text?: unknown;
    toolCalls?: unknown;
    tool_calls?: unknown;
    raw?: unknown;
    status?: string;
    latencyMs?: number;
    latency_ms?: number;
    metadata?: JsonRecord;
    error?: unknown;
  } = {}) {
    this.text = textValue(options.text ?? "");
    this.tool_calls = normalizeToolCalls(options.tool_calls ?? options.toolCalls ?? []);
    this.raw = options.raw;
    this.status = options.status ?? "ok";
    this.latency_ms = Math.max(0, Math.trunc(Number(options.latency_ms ?? options.latencyMs ?? 0)));
    this.metadata = jsonRecord(options.metadata ?? {});
    if (options.error !== undefined && options.error !== null) {
      this.error = coerceError(options.error);
    }
  }

  get ok(): boolean {
    return this.status === "ok" && this.error === undefined;
  }

  copy(): AgentResult {
    return new AgentResult({
      text: this.text,
      tool_calls: this.tool_calls,
      raw: this.raw,
      status: this.status,
      latency_ms: this.latency_ms,
      metadata: this.metadata,
      error: this.error,
    });
  }

  toJSON(): AgentTurn {
    return this.toDict();
  }

  toDict(): AgentTurn {
    const data: AgentTurn = {
      schema_version: AGENT_TURN_SCHEMA_VERSION_VALUE,
      text: jsonValue(this.text) as string,
      tool_calls: jsonValue(this.tool_calls) as JsonRecord[],
      status: jsonValue(this.status) as string,
      latency_ms: this.latency_ms,
      metadata: jsonRecord(this.metadata),
    };
    if (this.error !== undefined) {
      data.error = jsonRecord(this.error);
    }
    return data;
  }
}

export class AgentAdapter {
  readonly agent: AgentLike;
  readonly name: string;
  readonly raiseErrors: boolean;
  readonly inputStyle: AgentInputStyle;
  readonly inputKeyword: string;
  readonly history: AgentResult[] = [];
  lastResult?: AgentResult;
  lastResetError?: JsonRecord;
  lastResetLatencyMs?: number;

  constructor(agent: AgentLike, options: AgentAdapterOptions = {}) {
    if (!isAgentUsable(agent)) {
      throw new AgentAdapterError("agent must expose respond(input) or be callable");
    }
    this.agent = agent;
    this.name = options.name ?? agentName(agent);
    this.raiseErrors = Boolean(options.raiseErrors);
    this.inputStyle = normalizeInputStyle(options.inputStyle ?? "text");
    this.inputKeyword = options.inputKeyword ?? "agent_input";
  }

  async reset(): Promise<boolean> {
    const started = Date.now();
    const reset = typeof this.agent === "object" && this.agent !== null ? this.agent.reset : undefined;
    if (typeof reset !== "function") {
      this.lastResetError = undefined;
      this.lastResetLatencyMs = elapsedMs(started);
      return true;
    }
    try {
      await reset.call(this.agent);
      this.lastResetError = undefined;
      this.lastResetLatencyMs = elapsedMs(started);
      return true;
    } catch (error) {
      this.lastResetError = errorPayload(error);
      this.lastResetLatencyMs = elapsedMs(started);
      if (this.raiseErrors) {
        throw new AgentAdapterError(`agent reset failed: ${redactText(String(error instanceof Error ? error.message : error))}`);
      }
      return false;
    }
  }

  areset(): Promise<boolean> {
    return this.reset();
  }

  async respond(message: unknown, context: JsonRecord = {}): Promise<AgentResult> {
    const result = await this.respondWithStyle(message, context, this.inputStyle);
    this.lastResult = result;
    this.history.push(result);
    return result;
  }

  arespond(message: unknown, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respond(message, context);
  }

  async respondInput(agentInput: AgentInput | JsonRecord, context: JsonRecord = {}): Promise<AgentResult> {
    const result = await this.respondWithStyle(agentInput, context, "request");
    this.lastResult = result;
    this.history.push(result);
    return result;
  }

  arespondInput(agentInput: AgentInput | JsonRecord, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respondInput(agentInput, context);
  }

  runTurn(message: unknown, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respond(message, context);
  }

  arunTurn(message: unknown, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respond(message, context);
  }

  runInputTurn(agentInput: AgentInput | JsonRecord, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respondInput(agentInput, context);
  }

  arunInputTurn(agentInput: AgentInput | JsonRecord, context: JsonRecord = {}): Promise<AgentResult> {
    return this.respondInput(agentInput, context);
  }

  private async respondWithStyle(message: unknown, context: JsonRecord, inputStyle: AgentInputStyle): Promise<AgentResult> {
    const started = Date.now();
    try {
      const [agentInput, callContext] = prepareAgentInput(message, context);
      const [value, style] = await this.invoke(agentInput, callContext, inputStyle);
      return this.normalize(value, started, style);
    } catch (error) {
      if (this.raiseErrors) {
        throw error;
      }
      return new AgentResult({
        text: "",
        status: ERROR,
        latency_ms: elapsedMs(started),
        error: errorPayload(error),
        metadata: {
          adapter_name: this.name,
          style: ERROR,
          context: redactSensitive(context) as JsonRecord,
        },
      });
    }
  }

  private async invoke(agentInput: AgentInput, context: JsonRecord, inputStyle: AgentInputStyle): Promise<[unknown, string]> {
    const responder = typeof this.agent === "object" && this.agent !== null && typeof this.agent.respond === "function"
      ? this.agent.respond.bind(this.agent)
      : undefined;
    const callable = typeof this.agent === "function" && !isClassLike(this.agent) ? this.agent : undefined;
    const target = responder ?? callable;
    if (target === undefined) {
      throw new AgentAdapterError("agent must expose respond(input) or be callable");
    }
    const stylePrefix = responder ? "respond" : "callable";
    if (inputStyle === "keyword") {
      return [await target({ ...context, [this.inputKeyword]: agentInput }), `${stylePrefix}:keyword`];
    }
    if (inputStyle === "request") {
      return [await target(agentInput, context), `${stylePrefix}:request`];
    }
    return [await target(agentInput.text, context), stylePrefix];
  }

  private normalize(value: unknown, started: number, style: string): AgentResult {
    if (value instanceof AgentResult) {
      const result = value.copy();
      result.latency_ms = result.latency_ms || elapsedMs(started);
      result.metadata.adapter_name ??= this.name;
      result.metadata.style ??= style;
      return result;
    }
    if (typeof value === "string") {
      return new AgentResult({
        text: value,
        raw: value,
        latency_ms: elapsedMs(started),
        metadata: { adapter_name: this.name, style },
      });
    }
    if (isRecord(value)) {
      const metadata = isRecord(value.metadata) ? jsonRecord(value.metadata) : {};
      metadata.adapter_name ??= this.name;
      metadata.style ??= style;
      return new AgentResult({
        text: extractText(value),
        tool_calls: extractToolCalls(value),
        raw: value,
        status: String(value.status ?? "ok"),
        latency_ms: elapsedMs(started),
        error: value.error,
        metadata,
      });
    }
    return new AgentResult({
      text: objectText(value),
      tool_calls: normalizeToolCalls(getObjectProperty(value, "tool_calls") ?? getObjectProperty(value, "toolCalls") ?? []),
      raw: value,
      latency_ms: elapsedMs(started),
      metadata: { adapter_name: this.name, style },
    });
  }
}

export class LocalEvalRunner {
  readonly agent: AgentLike;
  readonly datasetId: string;
  readonly runnerId: string;
  readonly runId?: string;
  readonly maxWorkers: number;
  readonly timeoutSeconds: number | null;
  readonly inputStyle: AgentInputStyle;
  readonly inputKeyword: string;

  constructor(agent: AgentLike | LocalEvalRunnerOptions, options: LocalEvalRunnerOptions = {}) {
    const runnerOptions = isAgentUsable(agent as AgentLike) ? options : (agent as LocalEvalRunnerOptions);
    const runnerAgent = runnerOptions.agent ?? (agent as AgentLike);
    if (!isAgentUsable(runnerAgent)) {
      throw new AgentAdapterError("LocalEvalRunner requires an agent");
    }
    this.agent = runnerAgent;
    this.datasetId = runnerOptions.datasetId ?? LOCAL_DATASET_ID;
    this.runnerId = runnerOptions.runnerId ?? LOCAL_RUNNER_ID;
    this.runId = runnerOptions.runId;
    this.maxWorkers = normalizeMaxWorkers(runnerOptions.maxWorkers ?? DEFAULT_MAX_WORKERS);
    this.timeoutSeconds = normalizeTimeoutSeconds(runnerOptions.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS);
    this.inputStyle = normalizeInputStyle(runnerOptions.inputStyle ?? "text");
    this.inputKeyword = runnerOptions.inputKeyword ?? "agent_input";
  }

  run(cases: Iterable<unknown>): Promise<LocalRunResult> {
    return runAgentBatch(this.agent, cases, {
      datasetId: this.datasetId,
      runnerId: this.runnerId,
      runId: this.runId,
      maxWorkers: this.maxWorkers,
      timeoutSeconds: this.timeoutSeconds,
      inputStyle: this.inputStyle,
      inputKeyword: this.inputKeyword,
    });
  }
}

export class BatchRunner {
  readonly maxWorkers: number;
  readonly timeoutSeconds: number | null;

  constructor(options: RunBatchOptions = {}) {
    this.maxWorkers = normalizeMaxWorkers(options.maxWorkers ?? DEFAULT_MAX_WORKERS);
    this.timeoutSeconds = normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS);
  }

  run(cases: Iterable<unknown>): Promise<JsonRecord> {
    return runBatch(cases, { maxWorkers: this.maxWorkers, timeoutSeconds: this.timeoutSeconds });
  }
}

export function coerceRunnerAgentInput(value: unknown, options: { parts?: unknown; metadata?: JsonRecord } = {}): AgentInput {
  return coerceLocalAgentInput(value, options);
}

export function normalizeMaxWorkers(maxWorkers: number | null | undefined): number {
  const requested = maxWorkers === null || maxWorkers === undefined ? DEFAULT_MAX_WORKERS : Math.trunc(Number(maxWorkers));
  if (!Number.isFinite(requested) || requested < 1) {
    throw new Error("maxWorkers must be positive");
  }
  return Math.max(MIN_MAX_WORKERS, requested);
}

export function normalizeTimeoutSeconds(timeoutSeconds: number | null | undefined, fieldName = "timeoutSeconds"): number | null {
  if (timeoutSeconds === null || timeoutSeconds === undefined) {
    return null;
  }
  const value = Number(timeoutSeconds);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${fieldName} must be non-negative`);
  }
  return value;
}

export async function runCase(caseValue: unknown, options: { index?: number; timeoutSeconds?: number | null } = {}): Promise<JsonRecord> {
  const index = options.index ?? 0;
  const [caseRecord, caseId] = normalizeCase(caseValue, index);
  const timeoutSeconds = effectiveTimeoutSeconds(caseRecord, normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS));
  const execute = async (): Promise<JsonRecord> => executeLiteralCase(caseRecord, index, caseId);
  if (timeoutSeconds === null) {
    return execute();
  }
  return withTimeout(execute(), timeoutSeconds, () => literalTimeoutCase(caseRecord, index, caseId, timeoutSeconds));
}

export async function runBatch(cases: Iterable<unknown>, options: RunBatchOptions = {}): Promise<JsonRecord> {
  const caseList = Array.from(cases);
  const workerCount = normalizeMaxWorkers(options.maxWorkers ?? DEFAULT_MAX_WORKERS);
  const timeoutSeconds = normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS);
  const ordered: JsonRecord[] = new Array(caseList.length);
  let nextIndex = 0;

  async function worker(): Promise<void> {
    while (nextIndex < caseList.length) {
      const index = nextIndex;
      nextIndex += 1;
      ordered[index] = await runCase(caseList[index], { index, timeoutSeconds });
    }
  }

  await Promise.all(Array.from({ length: Math.min(workerCount, Math.max(1, caseList.length)) }, worker));
  const summary = {
    total: ordered.length,
    passed: ordered.filter((item) => item.status === PASSED).length,
    failed: ordered.filter((item) => item.status === FAILED).length,
    errors: ordered.filter((item) => item.status === ERROR).length,
    timeouts: ordered.filter((item) => item.status === TIMEOUT).length,
  };
  return {
    schema_version: "releasefoundry.runner.v1",
    max_workers: workerCount,
    summary: { ...summary, completed: summary.passed + summary.failed + summary.errors },
    results: ordered,
  };
}

export async function runFile(inputPath: string, outputPath: string, options: RunBatchOptions = {}): Promise<JsonRecord> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  const payload = JSON.parse(await fs.readFile(inputPath, "utf8")) as unknown;
  const cases = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.cases) ? payload.cases : undefined;
  if (!cases) {
    throw new AgentAdapterError("input JSON must be a case list or object with cases");
  }
  const result = await runBatch(cases, options);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  return result;
}

export function toA2JudgeRun(agentOutput: AgentResult | JsonRecord, options: { expectedKeywords?: string[]; forbiddenKeywords?: string[] } = {}): JsonRecord {
  const output = agentOutput instanceof AgentResult ? agentOutput.toDict() : jsonRecord(agentOutput);
  const toolCalls = normalizeToolCalls(output.tool_calls ?? []).map((call, index) => {
    const name = String(call.tool ?? call.name ?? `tool_${index}`);
    const args = isRecord(call.args) ? call.args : toolArguments(call);
    return { ...call, tool: name, name, args: jsonValue(args), arguments: jsonValue(args) };
  });
  const run: JsonRecord = {
    tool_calls: toolCalls,
    final_response: textValue(output.text ?? ""),
  };
  if (options.expectedKeywords) {
    run.expected_keywords = [...options.expectedKeywords];
  }
  if (options.forbiddenKeywords) {
    run.forbidden_keywords = [...options.forbiddenKeywords];
  }
  return run;
}

export const to_a2_judge_run = toA2JudgeRun;

export async function runAgentBatch(
  agent: AgentLike,
  cases: Iterable<unknown>,
  options: RunAgentBatchOptions = {},
): Promise<LocalRunResult> {
  const caseList = Array.from(cases);
  const workerCount = normalizeMaxWorkers(options.maxWorkers ?? DEFAULT_MAX_WORKERS);
  const defaultTimeout = normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS);
  const datasetId = options.datasetId ?? LOCAL_DATASET_ID;
  const runnerId = options.runnerId ?? LOCAL_RUNNER_ID;
  const startedAt = utcNow();
  const runId = options.runId ?? stableRunId(datasetId, runnerId, caseList, startedAt);
  const factory = agentFactory(agent);
  const ordered: Array<LocalCaseResult | undefined> = new Array(caseList.length);
  let nextIndex = 0;

  async function worker(): Promise<void> {
    while (nextIndex < caseList.length) {
      const index = nextIndex;
      nextIndex += 1;
      const caseRecord = caseList[index];
      try {
        ordered[index] = await runAgentCase(factory, caseRecord, index, runId, defaultTimeout, {
          inputStyle: options.inputStyle,
          inputKeyword: options.inputKeyword,
        });
      } catch (error) {
        ordered[index] = agentErrorCase(caseRecord, index, runId, errorName(error), errorMessage(error));
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(workerCount, Math.max(1, caseList.length)) }, worker));

  const endedAt = utcNow();
  const caseResults = ordered.filter((item): item is LocalCaseResult => item !== undefined);
  const passed = caseResults.filter((item) => item.status === PASSED).length;
  const failed = caseResults.filter((item) => item.status === FAILED).length;
  const errored = caseResults.filter((item) => item.status === ERROR).length;
  const timedOut = caseResults.filter((item) => item.status === TIMEOUT).length;
  const trace = traceCompleteness(caseResults);
  return {
    schema_version: RUN_RESULT_SCHEMA_VERSION_VALUE,
    run_id: runId,
    dataset_id: datasetId,
    runner_id: runnerId,
    status: passed === caseResults.length ? PASSED : errored || timedOut ? "completed_with_errors" : FAILED,
    total_cases: caseResults.length,
    passed,
    failed,
    errored,
    timed_out: timedOut,
    started_at: startedAt,
    ended_at: endedAt,
    duration_ms: durationMs(startedAt, endedAt),
    max_workers: workerCount,
    trace_completeness: trace,
    cases: caseResults,
    aggregate_metrics: {
      schema_version: RUN_RESULT_SCHEMA_VERSION_VALUE,
      trace_completeness: trace,
      passed,
      failed,
      errored,
      timed_out: timedOut,
      total_tool_calls: caseResults.reduce((total, item) => total + item.agent_output.tool_calls.length, 0),
    },
    metadata: { ...jsonRecord(options.metadata ?? {}), local_only: true, releasefoundry_api_used: false },
    field_map_version: LOCAL_RUN_FIELD_MAP_VERSION,
  };
}

export async function loadAgentTarget(target: string): Promise<AgentLike> {
  const [moduleName, exportPath] = splitTarget(target);
  const imported = await import(moduleSpecifier(moduleName));
  let resolvedTarget: unknown = imported;
  for (const part of exportPath.split(".")) {
    if (!part) {
      continue;
    }
    resolvedTarget = isRecord(resolvedTarget) ? resolvedTarget[part] : getObjectProperty(resolvedTarget, part);
  }
  if (!isAgentUsable(resolvedTarget as AgentLike)) {
    throw new AgentAdapterError(`target ${target} resolved to a non-agent value`);
  }
  return resolvedTarget as AgentLike;
}

export async function runAgentFile(
  inputPath: string,
  outputPath: string,
  agent: AgentLike,
  options: RunAgentBatchOptions = {},
): Promise<LocalRunResult> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  const payload = JSON.parse(await fs.readFile(inputPath, "utf8")) as unknown;
  const cases = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.cases) ? payload.cases : undefined;
  if (!cases) {
    throw new AgentAdapterError("input JSON must be a case list or object with cases");
  }
  const result = await runAgentBatch(agent, cases, options);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  return result;
}

export function buildCloudRunFixture(
  runResult: LocalRunResult | RunResult | JsonRecord,
  options: { tenantId?: string; projectId?: string; metadata?: JsonRecord } = {},
): LocalRunFixture {
  const result = jsonRecord(runResult);
  const observations = extractRunObservations(result);
  return dropUndefined({
    schema_version: "releasefoundry.cloud_api.v1",
    tenant_id: options.tenantId,
    project_id: options.projectId,
    dataset_id: String(result.dataset_id ?? LOCAL_DATASET_ID),
    run_id: String(result.run_id ?? "local-run"),
    status: String(result.status ?? ""),
    run_result: result,
    observations,
    metadata: { ...jsonRecord(options.metadata ?? {}), local_only: true, releasefoundry_api_used: false },
  }) as LocalRunFixture;
}

export function buildRunFixture(
  runResult: LocalRunResult | RunResult | JsonRecord,
  options: { name?: string; labels?: string[]; metadata?: JsonRecord } = {},
): JsonRecord {
  const result = jsonRecord(runResult);
  const observations = extractRunObservations(result);
  const events = observations.map((item, index) => traceEventFromObservation(item, index));
  return {
    schema: "releasefoundry.run.v1",
    name: options.name ?? `${String(result.run_id ?? "ts-run")} fixture`,
    labels: options.labels ?? ["a1", "typescript", "local-runner"],
    run: {
      run_id: String(result.run_id ?? "local-run"),
      agent: String(result.runner_id ?? LOCAL_RUNNER_ID),
      task: String(result.dataset_id ?? LOCAL_DATASET_ID),
      status: String(result.status ?? "unknown"),
      started_at: String(result.started_at ?? utcNow()),
      finished_at: String(result.ended_at ?? result.finished_at ?? utcNow()),
      dataset_id: result.dataset_id,
      runner_id: result.runner_id,
      total_cases: result.total_cases,
      trace_completeness: result.trace_completeness,
      field_map_version: result.field_map_version,
    },
    events,
    vm_stream: events.map((event) => vmFrameFromTraceEvent(event)),
    expected: { run_result: result },
    replay: {
      source: "packages/ts/releasefoundry",
      deterministic: false,
      metadata: { ...jsonRecord(options.metadata ?? {}), local_only: true, releasefoundry_api_used: false },
    },
  };
}

type AgentFactory = () => { agent: AgentLike; lock?: AsyncMutex };

async function runAgentCase(
  factory: AgentFactory,
  caseValue: unknown,
  index: number,
  runId: string,
  defaultTimeout: number | null,
  options: Pick<RunAgentBatchOptions, "inputStyle" | "inputKeyword">,
): Promise<LocalCaseResult> {
  const [caseRecord] = normalizeCase(caseValue, index);
  let timeoutSeconds: number | null;
  try {
    timeoutSeconds = effectiveTimeoutSeconds(caseRecord, defaultTimeout);
  } catch (error) {
    return agentErrorCase(caseRecord, index, runId, errorName(error), errorMessage(error));
  }
  if (timeoutSeconds !== null && timeoutSeconds <= 0) {
    return agentTimeoutCase(caseRecord, index, runId, timeoutSeconds);
  }
  const execution = async (): Promise<LocalCaseResult> => {
    const { agent: caseAgent, lock } = factory();
    const execute = () => executeAgentCase(caseAgent, caseRecord, index, runId, options);
    return lock ? lock.runExclusive(execute) : execute();
  };
  if (timeoutSeconds === null) {
    return execution();
  }
  return withTimeout(execution(), timeoutSeconds, () => agentTimeoutCase(caseRecord, index, runId, timeoutSeconds));
}

async function executeLiteralCase(caseRecord: JsonRecord, index: number, caseId: string): Promise<JsonRecord> {
  try {
    const output = await literalCaseOutput(caseRecord);
    const expected = "expected" in caseRecord ? jsonValue(caseRecord.expected) : undefined;
    const passed = expected === undefined || JSON.stringify(jsonValue(output)) === JSON.stringify(expected);
    return dropUndefined({
      id: caseId,
      case_id: caseId,
      index,
      expected,
      output: jsonValue(output),
      passed,
      status: passed ? PASSED : FAILED,
    });
  } catch (error) {
    return {
      id: caseId,
      case_id: caseId,
      index,
      passed: false,
      status: ERROR,
      error: errorPayload(error),
    };
  }
}

async function literalCaseOutput(caseRecord: JsonRecord): Promise<unknown> {
  if (caseRecord.target !== undefined || caseRecord.callable !== undefined) {
    const target = await loadAgentTarget(String(caseRecord.target ?? caseRecord.callable));
    if (typeof target !== "function" || isClassLike(target)) {
      throw new AgentAdapterError("literal case target must resolve to a callable function");
    }
    const targetFunction = target as AgentFunction;
    const kwargs = isRecord(caseRecord.kwargs) ? caseRecord.kwargs : {};
    if (Array.isArray(caseRecord.args)) {
      return (targetFunction as (...args: unknown[]) => unknown | Promise<unknown>)(...caseRecord.args, kwargs);
    }
    if (caseRecord.call_with === "kwargs") {
      return targetFunction({ ...(isRecord(caseRecord.input) ? caseRecord.input : {}), ...kwargs });
    }
    if ("input" in caseRecord) {
      return targetFunction(caseRecord.input, kwargs);
    }
    if ("prompt" in caseRecord) {
      return targetFunction(caseRecord.prompt, kwargs);
    }
    return targetFunction(kwargs);
  }
  for (const key of ["actual", "output", "result", "input"]) {
    if (key in caseRecord) {
      return caseRecord[key];
    }
  }
  return null;
}

function literalTimeoutCase(caseRecord: JsonRecord, index: number, caseId: string, timeoutSeconds: number): JsonRecord {
  return {
    id: caseId,
    case_id: caseId,
    index,
    passed: false,
    status: TIMEOUT,
    timeout_seconds: timeoutSeconds,
    error: { type: "TimeoutError", message: `case timed out after ${formatSeconds(timeoutSeconds)} seconds` },
  };
}

async function executeAgentCase(
  agent: AgentLike,
  caseRecord: JsonRecord,
  index: number,
  runId: string,
  options: Pick<RunAgentBatchOptions, "inputStyle" | "inputKeyword">,
): Promise<LocalCaseResult> {
  const startedAt = utcNow();
  const caseId = caseIdFor(caseRecord, index);
  const scenarioId = String(caseRecord.scenario_id ?? caseRecord.scenario ?? caseId);
  const title = String(caseRecord.title ?? caseRecord.name ?? scenarioId);
  const expected = expectedPayload(caseRecord);
  const agentInput = caseAgentInput(caseRecord, caseId);
  const inputStyle = normalizeInputStyle(String(caseRecord.input_style ?? caseRecord.agent_input_style ?? options.inputStyle ?? "text"));
  const adapter = new AgentAdapter(agent, { inputStyle, inputKeyword: options.inputKeyword });
  const resetOk = await adapter.reset();
  const userObservation = observation(runId, caseId, 0, "message", "user", agentInput.text, startedAt, startedAt, {
    metadata: { scenario_id: scenarioId, agent_input: agentInput },
  });
  let turn = inputStyle === "request"
    ? await adapter.respondInput(agentInput, caseRecord)
    : await adapter.respond(agentInput, caseRecord);
  if (!resetOk && turn.error === undefined) {
    turn = turn.copy();
    turn.status = ERROR;
    turn.error = adapter.lastResetError ?? { type: "AgentResetError", message: "agent reset failed" };
    turn.metadata.reset_ok = false;
  }
  const endedAt = utcNow();
  const status = caseStatus(turn, expected, resetOk);
  const grade = gradeResult(scenarioId, turn, expected, status, resetOk);
  const assistantObservation = observation(runId, caseId, 1, "agent_response", "assistant", turn.text, startedAt, endedAt, {
    toolCalls: turn.tool_calls,
    latencyMs: turn.latency_ms,
    status: turn.error ? ERROR : "ok",
    error: typeof turn.error?.message === "string" ? turn.error.message : undefined,
    metadata: { reset_ok: resetOk },
    vmStream: caseVmStream(caseRecord, agentInput, turn, startedAt, endedAt),
  });
  const latencyMs = durationMs(startedAt, endedAt);
  return dropUndefined({
    case_id: caseId,
    scenario_id: scenarioId,
    title,
    prompt: agentInput.text,
    actual: turn.text,
    status,
    started_at: startedAt,
    ended_at: endedAt,
    latency_ms: latencyMs,
    observations: [userObservation, assistantObservation],
    grade,
    agent_output: turn.toDict(),
    expected,
    error: turn.error && typeof turn.error.message === "string" ? turn.error.message : undefined,
    metadata: jsonRecord(caseRecord.metadata ?? {}),
  }) as LocalCaseResult;
}

function agentTimeoutCase(caseValue: unknown, index: number, runId: string, timeoutSeconds: number | null): LocalCaseResult {
  const duration = Math.max(0, Math.trunc(Number(timeoutSeconds ?? 0) * 1000));
  return agentErrorCase(caseValue, index, runId, "TimeoutError", `case timed out after ${formatSeconds(timeoutSeconds ?? 0)} seconds`, TIMEOUT, duration);
}

function agentErrorCase(
  caseValue: unknown,
  index: number,
  runId: string,
  errorType: string,
  message: string,
  status = ERROR,
  latencyMs = 0,
): LocalCaseResult {
  const [caseRecord] = normalizeCase(caseValue, index);
  const startedAt = utcNow();
  const endedAt = addMs(startedAt, latencyMs);
  const caseId = caseIdFor(caseRecord, index);
  const scenarioId = String(caseRecord.scenario_id ?? caseRecord.scenario ?? caseId);
  const expected = expectedPayload(caseRecord);
  const safeMessage = redactText(message);
  const agentInput = caseAgentInput(caseRecord, caseId);
  const grade: LocalGradeResult = {
    scenario_id: scenarioId,
    passed: false,
    score: 0,
    label: status,
    reason: safeMessage,
    expected,
    actual: { error: { type: errorType, message: safeMessage } },
    metrics: { reset_ok: false, latency_ms: latencyMs },
  };
  const userObservation = observation(runId, caseId, 0, "message", "user", agentInput.text, startedAt, startedAt, {
    metadata: { scenario_id: scenarioId, agent_input: agentInput },
  });
  const errorObservation = observation(runId, caseId, 1, status, "system", safeMessage, startedAt, endedAt, {
    latencyMs,
    status: ERROR,
    error: safeMessage,
    metadata: { error_type: errorType },
    vmStream: errorVmStream(caseRecord, agentInput, errorType, safeMessage, status, latencyMs),
  });
  const agentOutput = new AgentResult({
    text: "",
    tool_calls: [],
    status,
    latency_ms: latencyMs,
    error: { type: errorType, message: safeMessage },
    metadata: { synthetic: true },
  });
  return dropUndefined({
    case_id: caseId,
    scenario_id: scenarioId,
    title: String(caseRecord.title ?? caseRecord.name ?? scenarioId),
    prompt: agentInput.text,
    actual: "",
    status,
    started_at: startedAt,
    ended_at: endedAt,
    latency_ms: latencyMs,
    observations: [userObservation, errorObservation],
    grade,
    agent_output: agentOutput.toDict(),
    expected,
    error: safeMessage,
    metadata: jsonRecord(caseRecord.metadata ?? {}),
  }) as LocalCaseResult;
}

function caseAgentInput(caseRecord: JsonRecord, caseId: string): AgentInput {
  const rawInput = caseRecord.agent_input ?? caseRecord.agentInput ?? casePrompt(caseRecord);
  const parts = caseRecord.input_parts ?? caseRecord.inputParts ?? caseRecord.parts;
  const metadata = {
    case_id: caseId,
    ...(isRecord(caseRecord.metadata) ? caseRecord.metadata : {}),
  };
  return coerceLocalAgentInput(rawInput, { parts, metadata });
}

function coerceLocalAgentInput(value: unknown, options: { parts?: unknown; metadata?: JsonRecord } = {}): AgentInput {
  let input: AgentInput;
  if (isRecord(value) && (value.schema_version === AGENT_INPUT_SCHEMA_VERSION_VALUE || "text" in value || "parts" in value || "metadata" in value)) {
    input = {
      schema_version: AGENT_INPUT_SCHEMA_VERSION_VALUE,
      text: textValue(value.text ?? ""),
      parts: normalizeInputParts(value.parts ?? []),
      metadata: isRecord(value.metadata) ? jsonRecord(value.metadata) : {},
    } as AgentInput;
  } else {
    input = {
      schema_version: AGENT_INPUT_SCHEMA_VERSION_VALUE,
      text: textValue(value),
      parts: [],
      metadata: {},
    } as AgentInput;
  }
  if (options.parts !== undefined) {
    input.parts = normalizeInputParts(options.parts);
  }
  if (options.metadata) {
    input.metadata = { ...input.metadata, ...jsonRecord(options.metadata) };
  }
  if (input.parts.length === 0 && input.text) {
    input.parts = [{ type: "text", text: input.text }];
  }
  if (!input.text) {
    input.text = textFromInputParts(input.parts);
  }
  return input;
}

function prepareAgentInput(message: unknown, context: JsonRecord): [AgentInput, JsonRecord] {
  const callContext = { ...context };
  const parts = callContext.input_parts ?? callContext.inputParts;
  const metadata = callContext.input_metadata ?? callContext.inputMetadata;
  delete callContext.input_parts;
  delete callContext.inputParts;
  delete callContext.input_metadata;
  delete callContext.inputMetadata;
  return [coerceLocalAgentInput(message, { parts, metadata: isRecord(metadata) ? metadata : undefined }), callContext];
}

function normalizeInputParts(parts: unknown): AgentInput["parts"] {
  if (parts === undefined || parts === null) {
    return [];
  }
  const partList = Array.isArray(parts) ? parts : [parts];
  return partList.map((part, index) => normalizeInputPart(part, index));
}

function normalizeInputPart(part: unknown, index: number): AgentInput["parts"][number] {
  if (typeof part === "string") {
    return { type: "text", text: part };
  }
  if (!isRecord(part)) {
    throw new AgentAdapterError(`agent input part ${index} must be a mapping`);
  }
  const normalized = jsonRecord(part) as AgentInput["parts"][number] & JsonRecord;
  const partType = String(normalized.type ?? "text").toLowerCase();
  if (!(AGENT_INPUT_PART_TYPES as readonly string[]).includes(partType)) {
    throw new AgentAdapterError(`agent input part ${index} has unsupported type: ${partType}`);
  }
  normalized.type = partType as AgentInput["parts"][number]["type"];
  if (normalized.mimeType !== undefined && normalized.mime_type === undefined) {
    normalized.mime_type = String(normalized.mimeType);
    delete normalized.mimeType;
  }
  if (normalized.type === "text") {
    normalized.text = textValue(normalized.text ?? normalized.content ?? "");
    delete normalized.content;
  }
  return normalized;
}

function textFromInputParts(parts: AgentInput["parts"]): string {
  return parts
    .filter((part) => part.type === "text" && part.text)
    .map((part) => String(part.text))
    .join("\n");
}

function agentFactory(agent: AgentLike): AgentFactory {
  if (isClassLike(agent)) {
    return () => ({ agent: new (agent as AgentConstructor)() as AgentLike });
  }
  if (typeof agent === "object" && agent !== null && typeof agent.clone === "function") {
    return () => ({ agent: agent.clone?.() as AgentLike });
  }
  if (typeof agent === "function") {
    return () => ({ agent });
  }
  const lock = new AsyncMutex();
  return () => ({ agent, lock });
}

function splitTarget(target: string): [string, string] {
  const trimmed = target.trim();
  if (!trimmed) {
    throw new AgentAdapterError("agent target must be a non-empty string");
  }
  const colonIndex = trimmed.lastIndexOf(":");
  if (colonIndex > 1) {
    return [trimmed.slice(0, colonIndex), trimmed.slice(colonIndex + 1) || "default"];
  }
  if (/\.(?:mjs|cjs|js)$/i.test(trimmed)) {
    return [trimmed, "default"];
  }
  const dotIndex = trimmed.lastIndexOf(".");
  if (dotIndex > 0) {
    return [trimmed.slice(0, dotIndex), trimmed.slice(dotIndex + 1)];
  }
  return [trimmed, "default"];
}

function moduleSpecifier(moduleName: string): string {
  if (moduleName.startsWith("file://")) {
    return moduleName;
  }
  if (moduleName.startsWith(".") || moduleName.startsWith("/") || isAbsolute(moduleName) || /\.(?:mjs|cjs|js)$/i.test(moduleName)) {
    return pathToFileURL(resolve(moduleName)).href;
  }
  return moduleName;
}

function extractRunObservations(runResult: JsonRecord): JsonRecord[] {
  const cases = Array.isArray(runResult.cases) ? runResult.cases : [];
  const observations: JsonRecord[] = [];
  for (const item of cases) {
    if (!isRecord(item) || !Array.isArray(item.observations)) {
      continue;
    }
    for (const observationRecord of item.observations) {
      if (isRecord(observationRecord)) {
        observations.push(jsonRecord(observationRecord));
      }
    }
  }
  return observations;
}

function traceEventFromObservation(observationRecord: JsonRecord, index: number): JsonRecord {
  const phase = tracePhaseForObservation(observationRecord);
  const kind = traceKindForObservation(observationRecord);
  const channel = traceChannelForObservation(observationRecord);
  const timestamp = String(observationRecord.started_at ?? observationRecord.ended_at ?? utcNow());
  const data = jsonRecord({
    content: observationRecord.content,
    tool_calls: observationRecord.tool_calls ?? [],
    error: observationRecord.error,
    metadata: observationRecord.metadata ?? {},
  });
  const metadata = jsonRecord({
    observation_id: observationRecord.observation_id,
    case_id: observationRecord.case_id,
    turn_index: observationRecord.turn_index,
  });
  return {
    schema: "releasefoundry.trace.v1",
    type: "trace_event",
    event_type: `${phase}.${kind}`,
    run_id: String(observationRecord.run_id ?? "local-run"),
    event_id: `evt_${index + 1}`,
    seq: index,
    timestamp,
    phase,
    source: "packages/ts/releasefoundry.local-runner",
    parent_id: null,
    tags: ["runner", String(observationRecord.role ?? channel)],
    observation: {
      kind,
      channel,
      status: String(observationRecord.status ?? "ok"),
      text: textValue(observationRecord.content ?? observationRecord.error ?? ""),
      data,
    },
    metadata,
  };
}

function vmFrameFromTraceEvent(event: JsonRecord): JsonRecord {
  const observation = isRecord(event.observation) ? event.observation : {};
  const kind = String(observation.kind ?? "message");
  const channel = String(observation.channel ?? "agent");
  return {
    schema: "releasefoundry.vm_stream.v1",
    seq: Number(event.seq ?? 0),
    timestamp: String(event.timestamp ?? utcNow()),
    event_id: String(event.event_id ?? "evt_0"),
    stream: vmStreamForTraceObservation(kind, channel),
    status: String(observation.status ?? "ok"),
    text: String(observation.text ?? ""),
    data: isRecord(observation.data) ? jsonRecord(observation.data) : {},
  };
}

function vmStreamForTraceObservation(kind: string, channel: string): string {
  if (kind === "message") {
    if (channel === "user") {
      return "stdin";
    }
    if (channel === "assistant") {
      return "stdout";
    }
    return "lifecycle";
  }
  if (kind === "tool_call") {
    return "tool_call";
  }
  if (kind === "tool_result") {
    return "tool_result";
  }
  if (kind === "metric") {
    return "metric";
  }
  if (kind === "control") {
    return "lifecycle";
  }
  if (kind === "error") {
    return "stderr";
  }
  return "state";
}
function tracePhaseForObservation(observationRecord: JsonRecord): string {
  const role = String(observationRecord.role ?? "");
  if (role === "user") {
    return "input";
  }
  if (Array.isArray(observationRecord.tool_calls) && observationRecord.tool_calls.length > 0) {
    return "tool";
  }
  if (observationRecord.error !== undefined) {
    return "error";
  }
  return "output";
}

function traceKindForObservation(observationRecord: JsonRecord): string {
  if (Array.isArray(observationRecord.tool_calls) && observationRecord.tool_calls.length > 0) {
    return "tool_call";
  }
  if (observationRecord.error !== undefined) {
    return "error";
  }
  return "message";
}

function traceChannelForObservation(observationRecord: JsonRecord): string {
  const role = String(observationRecord.role ?? "");
  if (role) {
    return role;
  }
  if (Array.isArray(observationRecord.tool_calls) && observationRecord.tool_calls.length > 0) {
    return "tool";
  }
  if (observationRecord.error !== undefined) {
    return "vm";
  }
  return "assistant";
}

function traceStreamForObservation(observationRecord: JsonRecord): string {
  const role = String(observationRecord.role ?? "");
  if (role === "user") {
    return "stdin";
  }
  if (observationRecord.error !== undefined) {
    return "stderr";
  }
  if (Array.isArray(observationRecord.tool_calls) && observationRecord.tool_calls.length > 0) {
    return "tool_call";
  }
  return "stdout";
}

function normalizeVmStreamType(value: string): string {
  if (["stdin", "stdout", "tool_call", "tool_result", "lifecycle", "metric", "stderr", "state"].includes(value)) {
    return value;
  }
  if (value === "request") {
    return "stdin";
  }
  if (value === "response" || value === "log") {
    return "stdout";
  }
  return "state";
}
class AsyncMutex {
  private tail: Promise<void> = Promise.resolve();

  async runExclusive<T>(fn: () => Promise<T> | T): Promise<T> {
    const previous = this.tail;
    let release: () => void = () => undefined;
    this.tail = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await fn();
    } finally {
      release();
    }
  }
}

function normalizeInputStyle(inputStyle: string): AgentInputStyle {
  if ((INPUT_STYLES as readonly string[]).includes(inputStyle)) {
    return inputStyle as AgentInputStyle;
  }
  throw new AgentAdapterError(`inputStyle must be one of ${INPUT_STYLES.join(", ")}`);
}

function isAgentUsable(agent: AgentLike): boolean {
  if (isClassLike(agent)) {
    return true;
  }
  if (typeof agent === "function") {
    return true;
  }
  return typeof agent === "object" && agent !== null && typeof agent.respond === "function";
}

function isClassLike(value: unknown): value is AgentConstructor {
  return typeof value === "function" && /^class\s/.test(Function.prototype.toString.call(value));
}

function agentName(agent: AgentLike): string {
  if (typeof agent === "function") {
    return agent.name || "anonymous-agent";
  }
  if (typeof agent === "object" && agent !== null) {
    return agent.constructor?.name || "object-agent";
  }
  return "local-agent";
}

function normalizeToolCalls(toolCalls: unknown): JsonRecord[] {
  if (toolCalls === undefined || toolCalls === null) {
    return [];
  }
  const calls = Array.isArray(toolCalls) ? toolCalls : [toolCalls];
  return calls.map((call, index) => normalizeToolCall(call, index));
}

function normalizeToolCall(call: unknown, index: number): JsonRecord {
  if (!isRecord(call)) {
    return { name: String(call), arguments: {}, call_id: `tool_${index}` };
  }
  const functionRecord = isRecord(call.function) ? call.function : {};
  const name = String(call.name ?? call.tool ?? functionRecord.name ?? call.type ?? `tool_${index}`);
  let args: unknown = call.arguments ?? call.args ?? call.input ?? {};
  if (isEmptyRecord(args) && functionRecord.arguments !== undefined) {
    args = functionRecord.arguments;
  }
  let argumentsJson = call.arguments_json;
  if (typeof args === "string") {
    argumentsJson ??= args;
    try {
      args = JSON.parse(args) as unknown;
    } catch {
      args = { value: args };
    }
  }
  if (args === undefined || args === null) {
    args = {};
  }
  if (!isRecord(args)) {
    args = { value: args };
  }
  const normalized: JsonRecord = {
    name,
    arguments: jsonValue(args),
  };
  if (argumentsJson !== undefined && argumentsJson !== null) {
    normalized.arguments_json = String(argumentsJson);
  }
  if (call.id !== undefined || call.call_id !== undefined) {
    normalized.call_id = String(call.id ?? call.call_id);
  }
  if (call.output !== undefined || call.result !== undefined) {
    normalized.output = jsonValue(call.output ?? call.result);
  }
  if (call.latency_ms !== undefined) {
    normalized.latency_ms = Math.max(0, Math.trunc(Number(call.latency_ms)));
  }
  if (call.error !== undefined) {
    normalized.error = typeof call.error === "string" ? redactText(call.error) : redactSensitive(call.error);
  }
  return normalized;
}

function extractText(data: JsonRecord): string {
  const choices = data.choices;
  if (Array.isArray(choices) && choices.length > 0 && isRecord(choices[0])) {
    const message = choices[0].message;
    if (isRecord(message)) {
      return firstText(message, ["content", "text", "message", "response", "output"]);
    }
  }
  if (isRecord(data.message)) {
    return firstText(data.message, ["content", "text", "message", "response", "output"]);
  }
  return firstText(data, ["text", "message", "content", "response", "output"]);
}

function extractToolCalls(data: JsonRecord): unknown {
  for (const key of ["tool_calls", "tools", "toolCalls", "actions"]) {
    if (data[key] !== undefined && data[key] !== null) {
      return data[key];
    }
  }
  const choices = data.choices;
  if (Array.isArray(choices) && choices.length > 0 && isRecord(choices[0]) && isRecord(choices[0].message)) {
    return choices[0].message.tool_calls ?? choices[0].message.toolCalls ?? [];
  }
  if (isRecord(data.message)) {
    return data.message.tool_calls ?? data.message.toolCalls ?? [];
  }
  return [];
}

function firstText(data: JsonRecord, keys: string[]): string {
  for (const key of keys) {
    if (data[key] !== undefined && data[key] !== null) {
      return textValue(data[key]);
    }
  }
  return "";
}

function objectText(value: unknown): string {
  for (const attr of ["text", "message", "content", "response", "output"]) {
    const item = getObjectProperty(value, attr);
    if (item !== undefined) {
      return textValue(item);
    }
  }
  return textValue(value);
}

function getObjectProperty(value: unknown, property: string): unknown {
  return typeof value === "object" && value !== null && property in value ? (value as Record<string, unknown>)[property] : undefined;
}

function textValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  const contentPartText = textFromContentParts(value);
  if (contentPartText !== null) {
    return contentPartText;
  }
  return JSON.stringify(jsonValue(value));
}

function textFromContentParts(value: unknown): string | null {
  if (isRecord(value)) {
    return textFromContentPart(value);
  }
  if (!Array.isArray(value)) {
    return null;
  }
  let sawPart = false;
  const texts: string[] = [];
  for (const item of value) {
    if (typeof item === "string") {
      texts.push(item);
      continue;
    }
    if (!isRecord(item) || !("type" in item)) {
      return sawPart ? texts.join("\n") : null;
    }
    sawPart = true;
    const text = textFromContentPart(item);
    if (text) {
      texts.push(text);
    }
  }
  return sawPart || texts.length > 0 ? texts.join("\n") : null;
}

function textFromContentPart(part: JsonRecord): string | null {
  const partType = String(part.type ?? "").toLowerCase();
  if (!["text", "input_text", "output_text"].includes(partType)) {
    return null;
  }
  for (const key of ["text", "content", "value"]) {
    if (part[key] !== undefined) {
      return typeof part[key] === "string" ? part[key] : JSON.stringify(jsonValue(part[key]));
    }
  }
  return "";
}

function caseStatus(turn: AgentResult, expected: JsonRecord, resetOk: boolean): string {
  if (turn.error || turn.status === ERROR || !resetOk) {
    return ERROR;
  }
  return gradeResult("scenario", turn, expected, PASSED, resetOk).passed ? PASSED : FAILED;
}

function gradeResult(scenarioId: string, turn: AgentResult, expected: JsonRecord, status: string, resetOk: boolean): LocalGradeResult {
  const expectedText = expected.text ?? expected.final_text;
  const expectedTools = expected.tool_calls ?? expected.tools ?? [];
  const textOk = expectedText === undefined ? true : String(expectedText) === turn.text;
  const toolsOk = toolsMatch(expectedTools, turn.tool_calls);
  let passed = status === PASSED && resetOk && textOk && toolsOk && turn.error === undefined;
  if (Object.keys(expected).length === 0 && resetOk && turn.error === undefined) {
    passed = true;
  }
  const actual: JsonRecord = { text: turn.text, tool_calls: turn.tool_calls };
  if (turn.error !== undefined) {
    actual.error = turn.error;
  }
  return {
    scenario_id: scenarioId,
    passed,
    score: passed ? 1 : 0,
    label: passed ? PASSED : status,
    reason: passed ? "local checks passed" : "local expected/actual mismatch",
    expected,
    actual,
    metrics: { text_match: textOk, tool_match: toolsOk, reset_ok: resetOk, latency_ms: turn.latency_ms },
  };
}

function toolsMatch(expected: unknown, actual: JsonRecord[]): boolean {
  if (expected === undefined || expected === null || (Array.isArray(expected) && expected.length === 0)) {
    return true;
  }
  const expectedList = Array.isArray(expected) ? expected : [expected];
  const used = new Set<number>();
  for (const item of expectedList) {
    const [expectedName, expectedArgs, compareArgs] = expectedToolMatcher(item);
    const match = actual.findIndex((call, index) => {
      if (used.has(index)) {
        return false;
      }
      const actualName = String(call.name ?? call.tool ?? call.type ?? "");
      return actualName === expectedName && (!compareArgs || JSON.stringify(jsonValue(toolArguments(call))) === JSON.stringify(jsonValue(expectedArgs)));
    });
    if (match === -1) {
      return false;
    }
    used.add(match);
  }
  return true;
}

function expectedToolMatcher(expected: unknown): [string, unknown, boolean] {
  if (!isRecord(expected)) {
    return [String(expected), {}, false];
  }
  const name = String(expected.name ?? expected.tool ?? expected.type ?? "");
  const compareArgs = ["arguments", "args", "input", "arguments_json"].some((key) => key in expected);
  return [name, toolArguments(expected), compareArgs];
}

function toolArguments(call: JsonRecord): unknown {
  let args: unknown = call.arguments ?? call.args ?? call.input ?? {};
  if ((args === undefined || isEmptyRecord(args)) && call.arguments_json !== undefined) {
    args = call.arguments_json;
  }
  if (typeof args === "string") {
    try {
      return JSON.parse(args) as unknown;
    } catch {
      return { value: args };
    }
  }
  return args ?? {};
}

function observation(
  runId: string,
  caseId: string,
  turnIndex: number,
  eventType: string,
  role: string,
  content: unknown,
  startedAt: string,
  endedAt: string,
  options: {
    toolCalls?: JsonRecord[];
    latencyMs?: number;
    status?: string;
    error?: string;
    metadata?: JsonRecord;
    vmStream?: JsonRecord;
  } = {},
): LocalObservation {
  return dropUndefined({
    observation_id: observationId(runId, caseId, turnIndex, eventType),
    run_id: runId,
    case_id: caseId,
    turn_index: turnIndex,
    event_type: eventType,
    role,
    content: jsonValue(content),
    tool_calls: options.toolCalls ? jsonValue(options.toolCalls) : [],
    started_at: startedAt,
    ended_at: endedAt,
    latency_ms: options.latencyMs,
    status: options.status ?? "ok",
    error: options.error,
    metadata: jsonRecord(options.metadata ?? {}),
    vm_stream: options.vmStream ? jsonRecord(options.vmStream) : undefined,
  }) as LocalObservation;
}

function caseVmStream(caseRecord: JsonRecord, agentInput: AgentInput, turn: AgentResult, startedAt: string, endedAt: string): JsonRecord {
  const logs: JsonRecord[] = [
    { ts: 0, type: "action", data: { action: "respond", input: agentInput } },
    { ts: turn.latency_ms, type: "console", data: { level: turn.error ? ERROR : "log", message: turn.text } },
    ...turn.tool_calls.map((toolCall) => ({ ts: turn.latency_ms, type: "tool_call", data: toolCall })),
  ];
  return {
    provider: "local-runner",
    session_id: String(caseRecord.case_id ?? caseRecord.id ?? "local"),
    duration_ms: durationMs(startedAt, endedAt),
    logs: jsonValue(logs),
    metadata: { synthetic: true },
  };
}

function errorVmStream(caseRecord: JsonRecord, agentInput: AgentInput, errorType: string, message: string, status: string, latencyMs: number): JsonRecord {
  return {
    provider: "local-runner",
    session_id: String(caseRecord.case_id ?? caseRecord.id ?? "local"),
    duration_ms: latencyMs,
    logs: [
      { ts: 0, type: "action", data: { action: "respond", input: agentInput } },
      { ts: latencyMs, type: "console", data: { level: ERROR, message, error_type: errorType, status } },
    ],
    metadata: { synthetic: true, failure: status },
  };
}

function traceCompleteness(cases: LocalCaseResult[]): number {
  if (cases.length === 0) {
    return 1;
  }
  const complete = cases.filter((caseResult) =>
    caseResult.observations.length > 0
    && caseResult.observations.every((item) => item.started_at && item.ended_at)
    && caseResult.observations.some((item) => isRecord(item.vm_stream)),
  ).length;
  return Math.round((complete / cases.length) * 10000) / 10000;
}

function normalizeCase(caseValue: unknown, index: number): [JsonRecord, string] {
  const caseRecord = isRecord(caseValue) ? jsonRecord(caseValue) : { input: jsonValue(caseValue) };
  const caseId = caseIdFor(caseRecord, index);
  caseRecord.id ??= caseId;
  caseRecord.case_id ??= caseId;
  return [caseRecord, caseId];
}

function caseIdFor(caseRecord: JsonRecord, index: number): string {
  return String(caseRecord.id ?? caseRecord.case_id ?? caseRecord.name ?? `case-${String(index + 1).padStart(3, "0")}`);
}

function casePrompt(caseRecord: JsonRecord): unknown {
  for (const key of ["prompt", "input", "message", "user_text"]) {
    if (key in caseRecord) {
      return caseRecord[key];
    }
  }
  return "";
}

function expectedPayload(caseRecord: JsonRecord): JsonRecord {
  const expected = caseRecord.expected;
  if (isRecord(expected)) {
    return jsonRecord(expected);
  }
  if (expected === undefined || expected === null) {
    return {};
  }
  return { text: jsonValue(expected) };
}

function effectiveTimeoutSeconds(caseRecord: JsonRecord, defaultTimeout: number | null): number | null {
  for (const key of ["timeout_seconds", "timeoutSeconds", "timeout", "case_timeout_seconds", "caseTimeoutSeconds"]) {
    if (caseRecord[key] !== undefined && caseRecord[key] !== null) {
      return normalizeTimeoutSeconds(Number(caseRecord[key]), key);
    }
  }
  return defaultTimeout;
}

async function withTimeout<T>(promise: Promise<T>, timeoutSeconds: number, onTimeout: () => T): Promise<T> {
  let settled = false;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  return new Promise<T>((resolve, reject) => {
    timeout = setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(onTimeout());
    }, Math.max(0, timeoutSeconds * 1000));
    promise.then(
      (value) => {
        if (!settled) {
          settled = true;
          resolve(value);
        }
      },
      (error) => {
        if (!settled) {
          settled = true;
          reject(error);
        }
      },
    );
  }).finally(() => {
    if (timeout !== undefined) {
      clearTimeout(timeout);
    }
  });
}

function isEmptyRecord(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length === 0;
}

function jsonRecord(value: unknown): JsonRecord {
  const json = jsonValue(value);
  return isRecord(json) ? json : {};
}

function jsonValue(value: unknown): unknown {
  if (value instanceof AgentResult) {
    return value.toDict();
  }
  if (Array.isArray(value)) {
    return value.map((item) => jsonValue(item));
  }
  if (value instanceof Set) {
    return Array.from(value).sort((left, right) => String(left).localeCompare(String(right))).map((item) => jsonValue(item));
  }
  if (isRecord(value)) {
    const result: JsonRecord = {};
    for (const key of Object.keys(value).sort()) {
      result[key] = jsonValue(value[key]);
    }
    return result;
  }
  if (value === undefined) {
    return null;
  }
  try {
    JSON.stringify(value);
    return value;
  } catch {
    return String(value);
  }
}

function dropUndefined(value: JsonRecord): JsonRecord {
  const result: JsonRecord = {};
  for (const [key, item] of Object.entries(value)) {
    if (item === undefined) {
      continue;
    }
    if (Array.isArray(item)) {
      result[key] = item.map((entry) => (isRecord(entry) ? dropUndefined(entry) : entry));
    } else if (isRecord(item)) {
      result[key] = dropUndefined(item);
    } else {
      result[key] = item;
    }
  }
  return result;
}

function errorPayload(error: unknown): JsonRecord {
  return { type: errorName(error), message: errorMessage(error) };
}

function coerceError(error: unknown): JsonRecord {
  if (isRecord(error)) {
    return redactSensitive(error) as JsonRecord;
  }
  return { type: "AgentError", message: redactText(String(error)) };
}

function errorName(error: unknown): string {
  return error instanceof Error ? error.name : "AgentError";
}

function errorMessage(error: unknown): string {
  return redactText(String(error instanceof Error ? error.message : error));
}

function redactSensitive(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactSensitive(item));
  }
  if (isRecord(value)) {
    const redacted: JsonRecord = {};
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      if (normalized === "key" || ["api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential"].some((part) => normalized.includes(part))) {
        redacted[key] = "[redacted]";
      } else {
        redacted[key] = redactSensitive(item);
      }
    }
    return redacted;
  }
  return typeof value === "string" ? redactText(value) : value;
}

function redactText(value: string): string {
  let redacted = value.replace(/https?:\/\/[^\s?#]+(?:\?[^\s]*)/gi, (match) => `${match.split("?", 1)[0]}?[redacted]`);
  redacted = redacted.replace(/([?&](?:api_key|key|signature|sig|token)=)[^&\s]+/gi, "$1[redacted]");
  for (const pattern of [
    /tp_[A-Za-z0-9_-]+/g,
    /sk-[A-Za-z0-9_-]{8,}/g,
    /Bearer\s+[A-Za-z0-9._-]+/gi,
    /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  ]) {
    redacted = redacted.replace(pattern, "[redacted]");
  }
  return redacted;
}

function stableRunId(datasetId: string, runnerId: string, cases: unknown[], startedAt: string): string {
  return `run_${createHash("sha256").update(JSON.stringify(jsonValue({ dataset_id: datasetId, runner_id: runnerId, cases, started_at: startedAt }))).digest("hex").slice(0, 16)}`;
}

function observationId(runId: string, caseId: string, turnIndex: number, eventType: string): string {
  return `obs_${createHash("sha256").update(`${runId}:${caseId}:${turnIndex}:${eventType}`).digest("hex").slice(0, 16)}`;
}

function utcNow(): string {
  return new Date().toISOString();
}

function durationMs(startedAt: string, endedAt: string): number {
  return Math.max(0, Math.trunc(new Date(endedAt).getTime() - new Date(startedAt).getTime()));
}

function elapsedMs(started: number): number {
  return Math.max(0, Date.now() - started);
}

function addMs(startedAt: string, milliseconds: number): string {
  return new Date(new Date(startedAt).getTime() + milliseconds).toISOString();
}

function formatSeconds(seconds: number): string {
  return Number.isInteger(seconds) ? String(seconds) : String(seconds).replace(/0+$/, "").replace(/\.$/, "");
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
