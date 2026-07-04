import { createHash } from "node:crypto";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { buildRunFixture, type LocalObservation, type LocalRunResult } from "./runner.js";

export type DatasetJsonRecord = Record<string, unknown>;

export const DATASET_ADAPTER_VERSION = "ashr.clone.dataset_adapter.v1";
export const DATASET_SOURCE_ADAPTER_VERSION = DATASET_ADAPTER_VERSION;

export interface DatasetSourceCaseOptions {
  maxCases?: number | null;
  includeAgentlessRuns?: boolean;
}

export interface SourceRunCaseOptions {
  actionIndex?: number | null;
  agentActionOrdinal?: number;
  runKey?: string;
  datasetType?: string;
  totalRuns?: unknown;
}

export function extractDatasetSource(recordOrDataset: DatasetJsonRecord): DatasetJsonRecord {
  let current: unknown = recordOrDataset;
  if (isRecord(current) && "response" in current) {
    current = current.response ?? {};
  }
  if (isRecord(current) && "dataset" in current) {
    current = current.dataset ?? {};
  }
  const source = isRecord(current) && "dataset_source" in current ? current.dataset_source : current;
  if (!isRecord(source)) {
    throw new Error("dataset_source must be a JSON object");
  }
  if (!("runs" in source)) {
    throw new Error("dataset_source must contain runs");
  }
  return jsonRecord(source);
}

export function datasetSourceToCases(datasetSource: DatasetJsonRecord, options: DatasetSourceCaseOptions = {}): DatasetJsonRecord[] {
  const maxCases = normalizeMaxCases(options.maxCases);
  if (maxCases === 0) {
    return [];
  }
  const datasetType = textValue(datasetSource.dataset_type);
  const totalRuns = datasetSource.total_runs;
  const cases: DatasetJsonRecord[] = [];
  for (const [runKey, rawRun] of runsItems(datasetSource.runs)) {
    if (!isRecord(rawRun)) {
      continue;
    }
    const actions = actionList(rawRun.actions);
    let emittedForRun = 0;
    for (const [actionIndex, action] of actions.entries()) {
      if (actor(action) !== "agent") {
        continue;
      }
      cases.push(
        caseFromSourceRun(rawRun, {
          actionIndex,
          runKey,
          datasetType,
          totalRuns,
        }),
      );
      emittedForRun += 1;
      if (maxCases !== null && cases.length >= maxCases) {
        return cases;
      }
    }
    if (options.includeAgentlessRuns && emittedForRun === 0 && actions.length > 0) {
      cases.push(agentlessCase(rawRun, actions, runKey, datasetType, totalRuns));
      if (maxCases !== null && cases.length >= maxCases) {
        return cases;
      }
    }
  }
  return cases;
}

export function casesFromDatasetSource(datasetSource: DatasetJsonRecord, options: DatasetSourceCaseOptions = {}): DatasetJsonRecord[] {
  return datasetSourceToCases(datasetSource, options);
}

export function caseFromSourceRun(sourceRun: DatasetJsonRecord, options: SourceRunCaseOptions = {}): DatasetJsonRecord {
  const actions = actionList(sourceRun.actions);
  const runId = textValue(sourceRun.run_id) || options.runKey || stableId("source_run", sourceRun);
  const selectedIndex = selectAgentActionIndex(actions, options.actionIndex ?? null, options.agentActionOrdinal ?? 0);
  const action = actions[selectedIndex];
  const expected = expectedFromAgentAction(action);
  const actionName = textValue(action.name) || `agent_action_${selectedIndex}`;
  const caseId = `${safeId(runId)}-a${String(selectedIndex).padStart(3, "0")}`;
  return {
    id: caseId,
    case_id: caseId,
    scenario_id: runId,
    title: caseTitle(sourceRun, actionName),
    prompt: promptForAgentAction(sourceRun, actions.slice(0, selectedIndex), selectedIndex),
    expected,
    metadata: metadataForAction({
      run: sourceRun,
      action,
      actionIndex: selectedIndex,
      datasetType: options.datasetType ?? "",
      totalRuns: options.totalRuns,
      actionCount: actions.length,
      requiresExternalJudge: requiresExternalJudge(action, expected),
    }),
  };
}

export function apiRecordToCases(record: DatasetJsonRecord, options: DatasetSourceCaseOptions = {}): DatasetJsonRecord[] {
  return datasetSourceToCases(extractDatasetSource(record), options);
}

export async function loadCasesFromApiRecord(path: string, options: DatasetSourceCaseOptions = {}): Promise<DatasetJsonRecord[]> {
  const payload = JSON.parse(await readFile(path, "utf8")) as unknown;
  if (!isRecord(payload)) {
    throw new Error("API record must be a JSON object");
  }
  return apiRecordToCases(payload, options);
}

export async function writeCases(path: string, cases: Iterable<DatasetJsonRecord>): Promise<string> {
  const payload = { adapter_version: DATASET_ADAPTER_VERSION, cases: Array.from(cases).map((item) => jsonRecord(item)) };
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return path;
}

export function replayFixtureFromSourceRun(
  sourceRun: DatasetJsonRecord,
  options: { runKey?: string; agent?: string; name?: string } = {},
): DatasetJsonRecord {
  const actions = actionList(sourceRun.actions);
  const sourceRunId = textValue(sourceRun.run_id) || options.runKey || stableId("source_run", sourceRun);
  const runId = stableId("dataset_replay", sourceRunId, actions.map((action, index) => actionSummary(action, index)));
  const startedAt = utcNow();
  const observations = actions.map((action, index) => sourceActionObservation(runId, sourceRunId, action, index, startedAt));
  const toolCalls = actions.flatMap((action) => actionToolCalls(action));
  const endedAt = utcNow();
  const agentActionCount = actions.filter((action) => actor(action) === "agent").length;
  const runResult: LocalRunResult = {
    schema_version: "ashr.clone.run_result.v1",
    run_id: runId,
    dataset_id: `dataset_source_${safeId(sourceRunId)}`,
    runner_id: options.agent ?? "ashr-dataset-source",
    status: "passed",
    total_cases: 1,
    passed: 1,
    failed: 0,
    errored: 0,
    timed_out: 0,
    started_at: startedAt,
    ended_at: endedAt,
    duration_ms: 0,
    max_workers: 4,
    trace_completeness: observations.some((observation) => isRecord(observation.vm_stream)) ? 1 : 0,
    cases: [
      {
        case_id: `${safeId(sourceRunId)}-replay`,
        scenario_id: sourceRunId,
        title: caseTitle(sourceRun, "source-run-replay"),
        status: "passed",
        started_at: startedAt,
        ended_at: endedAt,
        latency_ms: 0,
        observations,
        grade: {
          scenario_id: sourceRunId,
          passed: true,
          score: 1,
          label: "passed",
          reason: "source run replay converted",
          expected: { source_actions: actions.length, agent_actions: agentActionCount },
          actual: { source_actions: actions.length, agent_actions: agentActionCount },
          metrics: { source_actions: actions.length, agent_actions: agentActionCount },
        },
        agent_output: {
          schema_version: "ashr.clone.agent_turn.v1",
          text: textValue(sourceRun.intent ?? sourceRun.description ?? sourceRun.title ?? sourceRunId),
          tool_calls: toolCalls,
          status: "ok",
          latency_ms: 0,
          metadata: { source: "ashr_dataset_source" },
        },
        expected: { source_actions: actions.length, agent_actions: agentActionCount },
        metadata: {
          adapter_version: DATASET_SOURCE_ADAPTER_VERSION,
          source: "ashr_dataset_source",
          source_run_hash: stableId("source_run", sourceRunId),
          action_count: actions.length,
          agent_action_count: agentActionCount,
        },
      },
    ],
    aggregate_metrics: {
      schema_version: "ashr.clone.run_result.v1",
      trace_completeness: 1,
      passed: 1,
      failed: 0,
      errored: 0,
      timed_out: 0,
      total_tool_calls: toolCalls.length,
    },
    metadata: { local_only: true, ashr_api_used: false, source: "ashr_dataset_source" },
    field_map_version: "a1.ts.dataset_source.v1",
  };
  return buildRunFixture(runResult, {
    name: options.name ?? `${sourceRunId} replay fixture`,
    labels: ["a1", "typescript", "ashr-dataset-source"],
    metadata: { adapter_version: DATASET_SOURCE_ADAPTER_VERSION },
  });
}

function agentlessCase(run: DatasetJsonRecord, actions: DatasetJsonRecord[], runKey: string, datasetType: string, totalRuns: unknown): DatasetJsonRecord {
  const runId = textValue(run.run_id) || runKey;
  const caseId = `${safeId(runId)}-agentless`;
  return {
    id: caseId,
    case_id: caseId,
    scenario_id: runId,
    title: caseTitle(run, "agentless"),
    prompt: promptForAgentAction(run, actions, actions.length),
    expected: {},
    metadata: metadataForAction({
      run,
      action: {},
      actionIndex: null,
      datasetType,
      totalRuns,
      actionCount: actions.length,
      requiresExternalJudge: true,
    }),
  };
}

function promptForAgentAction(run: DatasetJsonRecord, previousActions: DatasetJsonRecord[], actionIndex: number): string {
  const lines: string[] = [];
  const title = textValue(run.title);
  const description = textValue(run.description);
  const intent = textValue(run.intent);
  if (title) {
    lines.push(`Scenario: ${title}`);
  }
  if (description) {
    lines.push(`Description: ${description}`);
  }
  if (intent) {
    lines.push(`Intent: ${intent}`);
  }
  lines.push(`Target agent action index: ${actionIndex}`, "", "Conversation so far:");
  if (previousActions.length) {
    for (const [index, action] of previousActions.entries()) {
      const name = textValue(action.name);
      const label = name ? `${actor(action)} (${name})` : actor(action);
      const content = textValue(action.content ?? action.message ?? action.text);
      if (content) {
        lines.push(`${index}. ${label}: ${content}`);
      }
    }
  } else {
    lines.push("(no prior actions)");
  }
  lines.push("", "Respond as the agent to the latest user/environment context.");
  return lines.join("\n");
}

function expectedFromAgentAction(action: DatasetJsonRecord): DatasetJsonRecord {
  const expected = isRecord(action.expected_response) ? jsonRecord(action.expected_response) : {};
  if (!("text" in expected) && action.content !== undefined && action.content !== "") {
    expected.text = textValue(action.content);
  }
  if (expected.tool_calls !== undefined) {
    expected.tool_calls = normalizeToolCalls(expected.tool_calls);
  }
  return expected;
}

function actionToolCalls(action: DatasetJsonRecord): DatasetJsonRecord[] {
  const expected = expectedFromAgentAction(action);
  return Array.isArray(expected.tool_calls) ? expected.tool_calls.filter(isRecord).map((call) => jsonRecord(call)) : [];
}

function normalizeToolCalls(toolCalls: unknown): DatasetJsonRecord[] {
  const list = Array.isArray(toolCalls) ? toolCalls : isRecord(toolCalls) ? [toolCalls] : [];
  return list.map((call, index) => {
    if (!isRecord(call)) {
      return { name: textValue(call), arguments: {} };
    }
    let args: unknown = call.arguments ?? call.args ?? call.input ?? {};
    if ((args === undefined || (isRecord(args) && Object.keys(args).length === 0)) && call.arguments_json !== undefined) {
      args = call.arguments_json;
    }
    if (typeof args === "string") {
      try {
        args = JSON.parse(args) as unknown;
      } catch {
        args = { value: args };
      }
    }
    return {
      name: textValue(call.name ?? call.tool ?? call.type ?? `tool_${index}`),
      arguments: isRecord(args) ? jsonRecord(args) : {},
    };
  });
}

function metadataForAction(options: {
  run: DatasetJsonRecord;
  action: DatasetJsonRecord;
  actionIndex: number | null;
  datasetType: string;
  totalRuns: unknown;
  actionCount: number;
  requiresExternalJudge: boolean;
}): DatasetJsonRecord {
  const sourceRunId = textValue(options.run.run_id);
  return {
    adapter_version: DATASET_SOURCE_ADAPTER_VERSION,
    source: "ashr_dataset_source",
    dataset_type: options.datasetType,
    total_runs: options.totalRuns ?? null,
    source_run_hash: sourceRunId ? stableId("source_run", sourceRunId) : "",
    action_count: options.actionCount,
    action_index: options.actionIndex,
    action_name: textValue(options.action.name),
    action_type: textValue(options.action.action_type),
    requires_external_judge: options.requiresExternalJudge,
    intent_tags: jsonList(options.run.intent_tags),
    audio_tags: jsonList(options.run.audio_tags),
    action_tags: jsonList(options.action.action_tags),
  };
}

function sourceActionObservation(runId: string, sourceRunId: string, action: DatasetJsonRecord, index: number, startedAt: string): LocalObservation {
  const actionActor = actor(action);
  const content = textValue(action.content ?? action.message ?? action.text ?? action.name ?? actionActor);
  return {
    observation_id: `obs_${stableId(runId, sourceRunId, index).slice(0, 16)}`,
    run_id: runId,
    case_id: `${safeId(sourceRunId)}-replay`,
    turn_index: index,
    event_type: actionActor === "agent" ? "agent_response" : actionActor === "user" ? "message" : "state",
    role: actionActor === "agent" ? "assistant" : actionActor || "system",
    content,
    tool_calls: actionActor === "agent" ? actionToolCalls(action) : [],
    started_at: startedAt,
    ended_at: startedAt,
    status: "ok",
    metadata: actionSummary(action, index),
    vm_stream: {
      provider: "ashr-dataset-source",
      session_id: sourceRunId,
      duration_ms: 0,
      logs: [{ ts: index, type: "source_action", data: actionSummary(action, index) }],
      metadata: { synthetic: true, source: "ashr_dataset_source" },
    },
  } as LocalObservation;
}

function runsItems(runs: unknown): Array<[string, unknown]> {
  if (Array.isArray(runs)) {
    return runs.map((value, index) => [String(index), value]);
  }
  if (isRecord(runs)) {
    return Object.entries(runs);
  }
  return [];
}

function actionList(actions: unknown): DatasetJsonRecord[] {
  return Array.isArray(actions) ? actions.filter(isRecord).map((action) => jsonRecord(action)) : [];
}

function selectAgentActionIndex(actions: DatasetJsonRecord[], actionIndex: number | null, agentActionOrdinal: number): number {
  if (actionIndex !== null) {
    if (actionIndex < 0 || actionIndex >= actions.length) {
      throw new Error("actionIndex is out of range");
    }
    if (actor(actions[actionIndex]) !== "agent") {
      throw new Error("selected action is not an agent action");
    }
    return actionIndex;
  }
  const agentIndexes = actions.flatMap((action, index) => (actor(action) === "agent" ? [index] : []));
  if (agentActionOrdinal < 0 || agentActionOrdinal >= agentIndexes.length) {
    throw new Error("source_run does not contain the requested agent action");
  }
  return agentIndexes[agentActionOrdinal];
}

function actor(action: DatasetJsonRecord): string {
  return textValue(action.actor).trim().toLowerCase();
}

function caseTitle(run: DatasetJsonRecord, actionName: string): string {
  return `${textValue(run.title) || textValue(run.run_id) || "Ashr scenario"} / ${actionName}`;
}

function requiresExternalJudge(action: DatasetJsonRecord, expected: DatasetJsonRecord): boolean {
  return Object.keys(expected).length === 0 && (action.content === undefined || action.content === "");
}

function actionSummary(action: DatasetJsonRecord, index: number): DatasetJsonRecord {
  return {
    action_index: index,
    actor: actor(action),
    name: textValue(action.name),
    action_type: textValue(action.action_type),
    has_content: action.content !== undefined && action.content !== "",
    has_expected_response: isRecord(action.expected_response),
    has_output_path: action.output_path !== undefined && action.output_path !== "",
  };
}

function normalizeMaxCases(maxCases: number | null | undefined): number | null {
  if (maxCases === undefined || maxCases === null) {
    return null;
  }
  const parsed = Math.trunc(Number(maxCases));
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error("maxCases must be non-negative");
  }
  return parsed;
}

function jsonList(value: unknown): unknown[] {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function safeId(value: string): string {
  return value.trim().replace(/[^A-Za-z0-9_-]+/g, "-") || "run";
}

function stableId(...parts: unknown[]): string {
  return createHash("sha256").update(JSON.stringify(parts.map((part) => jsonValue(part)))).digest("hex").slice(0, 16);
}

function textValue(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  return typeof value === "string" ? value : JSON.stringify(jsonValue(value));
}

function jsonRecord(value: unknown): DatasetJsonRecord {
  const json = jsonValue(value);
  return isRecord(json) ? json : {};
}

function jsonValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => jsonValue(item));
  }
  if (isRecord(value)) {
    const result: DatasetJsonRecord = {};
    for (const key of Object.keys(value).sort()) {
      const item = value[key];
      if (item !== undefined) {
        result[key] = jsonValue(item);
      }
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

function utcNow(): string {
  return new Date().toISOString();
}

function isRecord(value: unknown): value is DatasetJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
