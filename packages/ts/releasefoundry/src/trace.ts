import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

export type TraceJsonRecord = Record<string, unknown>;

export const TRACE_EVENT_SCHEMA_VERSION = "releasefoundry.trace.v1";
export const RUN_FIXTURE_SCHEMA_VERSION = "releasefoundry.run.v1";
export const VM_STREAM_SCHEMA_VERSION = "releasefoundry.vm_stream.v1";

const VM_STREAMS = new Set(["stdin", "stdout", "tool_call", "tool_result", "lifecycle", "metric", "stderr", "state"]);

export interface TraceObservation extends TraceJsonRecord {
  kind: string;
  channel: string;
  status: string;
  text: string;
  data: TraceJsonRecord;
}

export interface TraceEvent extends TraceJsonRecord {
  schema: typeof TRACE_EVENT_SCHEMA_VERSION;
  type: "trace_event";
  event_type: string;
  run_id: string;
  event_id: string;
  seq: number;
  timestamp: string;
  phase: string;
  source: string;
  parent_id: string | null;
  tags: string[];
  observation: TraceObservation;
  metadata: TraceJsonRecord;
}

export interface VmStreamFrame extends TraceJsonRecord {
  schema: typeof VM_STREAM_SCHEMA_VERSION;
  seq: number;
  timestamp: string;
  event_id: string;
  stream: string;
  status: string;
  text: string;
  data: TraceJsonRecord;
}

export class TraceValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TraceValidationError";
  }
}

export class TraceRecorder {
  readonly runId: string;
  readonly source: string;
  readonly startedAt: string;
  private readonly items: TraceEvent[] = [];

  constructor(options: { runId: string; source?: string; startedAt?: string }) {
    this.runId = options.runId;
    this.source = options.source ?? "ts-trace-recorder";
    this.startedAt = options.startedAt ?? "2026-01-01T00:00:00.000Z";
  }

  append(eventType: string, payload: TraceJsonRecord = {}, options: { role?: string; caseId?: string; turnIndex?: number; phase?: string; tags?: string[]; metadata?: TraceJsonRecord } = {}): TraceEvent {
    const seq = this.items.length;
    const phase = options.phase ?? eventTypePhase(eventType);
    const observation = observationFromPayload(eventType, payload, options.role);
    const event: TraceEvent = {
      schema: TRACE_EVENT_SCHEMA_VERSION,
      type: "trace_event",
      event_type: `${phase}.${observation.kind}`,
      run_id: this.runId,
      event_id: `evt_${seq + 1}`,
      seq,
      timestamp: timestampFor(seq, this.startedAt),
      phase,
      source: this.source,
      parent_id: null,
      tags: options.tags ?? [],
      observation,
      metadata: jsonRecord({ case_id: options.caseId, turn_index: options.turnIndex, ...(options.metadata ?? {}) }),
    };
    this.items.push(dropUndefined(event) as TraceEvent);
    return this.items[this.items.length - 1];
  }

  message(role: string, content: unknown, data: TraceJsonRecord = {}): TraceEvent {
    return this.append("message", { content: jsonValue(content), metadata: jsonRecord(data) }, { role, phase: role === "user" ? "input" : "output" });
  }

  toolCall(name: string, argumentsValue: unknown = {}, options: { callId?: string; output?: unknown; error?: unknown } = {}): TraceEvent {
    return this.append("tool_call", {
      name,
      call_id: options.callId ?? `tool_${this.items.length + 1}`,
      arguments: jsonValue(argumentsValue),
      output: options.output === undefined ? undefined : jsonValue(options.output),
      error: options.error === undefined ? undefined : jsonValue(options.error),
    }, { phase: "tool" });
  }

  metric(name: string, value: unknown): TraceEvent {
    return this.append("metric", { name, value: jsonValue(value), unit: "count" }, { phase: "metric" });
  }

  control(name: string, data: TraceJsonRecord = {}): TraceEvent {
    return this.append("control", { name, data: jsonRecord(data) }, { phase: "lifecycle" });
  }

  events(): TraceEvent[] {
    return this.items.map((item) => jsonRecord(item) as TraceEvent);
  }
}

export function buildVmStream(events: TraceEvent[], _options: { provider?: string; sessionId?: string } = {}): VmStreamFrame[] {
  return events
    .map(validateTraceEvent)
    .sort((left, right) => left.seq - right.seq)
    .map((event) => buildVmFrame(event));
}

export function traceEventsFromVmStream(runId: string, vmStream: unknown, options: { source?: string; startedAt?: string } = {}): TraceEvent[] {
  const frames = normalizeVmStream(vmStream).sort((left, right) => left.seq - right.seq);
  return frames.map((frame) => ({
    schema: TRACE_EVENT_SCHEMA_VERSION,
    type: "trace_event",
    event_type: `${frame.stream}.${frame.stream === "stdout" ? "message" : frame.stream}`,
    run_id: runId,
    event_id: frame.event_id,
    seq: frame.seq,
    timestamp: frame.timestamp,
    phase: frame.stream,
    source: options.source ?? "vm_replay",
    parent_id: null,
    tags: ["replay"],
    observation: {
      kind: frame.stream === "stdout" ? "message" : frame.stream,
      channel: frame.stream,
      status: frame.status,
      text: frame.text,
      data: jsonRecord(frame.data),
    },
    metadata: jsonRecord({ replay_started_at: options.startedAt ?? null }),
  }));
}

export function buildTraceRunFixture(options: {
  name: string;
  runId: string;
  datasetId?: string;
  runnerId?: string;
  events: TraceEvent[];
  expected?: TraceJsonRecord;
  labels?: string[];
  replay?: TraceJsonRecord;
}): TraceJsonRecord {
  const events = options.events.map(validateTraceEvent).sort((left, right) => left.seq - right.seq);
  if (events.length === 0) {
    throw new TraceValidationError("run fixture requires at least one event");
  }
  const startedAt = events[0].timestamp;
  const finishedAt = events[events.length - 1].timestamp;
  const fixture = {
    schema: RUN_FIXTURE_SCHEMA_VERSION,
    name: options.name,
    labels: options.labels ?? ["a1", "typescript", "trace"],
    run: {
      run_id: options.runId,
      agent: options.runnerId ?? "ts-trace-recorder",
      task: options.datasetId ?? "trace-dataset",
      status: "passed",
      started_at: startedAt,
      finished_at: finishedAt,
      dataset_id: options.datasetId ?? "trace-dataset",
      runner_id: options.runnerId ?? "ts-trace-recorder",
      total_cases: 1,
      trace_completeness: 1,
    },
    events: events.map((event) => jsonRecord(event)),
    vm_stream: buildVmStream(events),
    expected: jsonRecord(options.expected ?? {}),
    replay: { source: "packages/ts/releasefoundry", deterministic: false, ...jsonRecord(options.replay ?? {}) },
  };
  validateRunFixture(fixture);
  return fixture;
}

export function validateTraceEvent(event: unknown): TraceEvent {
  if (!isRecord(event)) {
    throw new TraceValidationError("trace event must be an object");
  }
  if (event.schema !== TRACE_EVENT_SCHEMA_VERSION || event.type !== "trace_event") {
    throw new TraceValidationError("trace event schema/type mismatch");
  }
  for (const key of ["event_id", "timestamp", "run_id", "event_type", "phase", "source"]) {
    if (typeof event[key] !== "string" || !event[key]) {
      throw new TraceValidationError(`trace event ${key} must be a non-empty string`);
    }
  }
  if (!Number.isInteger(event.seq) || Number(event.seq) < 0) {
    throw new TraceValidationError("trace event seq must be a non-negative integer");
  }
  if (!Array.isArray(event.tags)) {
    throw new TraceValidationError("trace event tags must be an array");
  }
  if (!isRecord(event.observation)) {
    throw new TraceValidationError("trace event observation must be an object");
  }
  validateObservation(event.observation);
  if (!isRecord(event.metadata)) {
    throw new TraceValidationError("trace event metadata must be an object");
  }
  return event as TraceEvent;
}

export function validateVmStreamFrame(frame: unknown): VmStreamFrame {
  if (!isRecord(frame)) {
    throw new TraceValidationError("VM stream frame must be an object");
  }
  const keys = Object.keys(frame).sort();
  const expected = ["data", "event_id", "schema", "seq", "status", "stream", "text", "timestamp"].sort();
  if (keys.join("\0") !== expected.join("\0")) {
    throw new TraceValidationError("VM stream frame keys do not match schema contract");
  }
  if (frame.schema !== VM_STREAM_SCHEMA_VERSION) {
    throw new TraceValidationError("VM stream frame schema mismatch");
  }
  if (!Number.isInteger(frame.seq) || Number(frame.seq) < 0) {
    throw new TraceValidationError("VM stream frame seq must be a non-negative integer");
  }
  for (const key of ["timestamp", "event_id", "stream", "status", "text"]) {
    if (typeof frame[key] !== "string") {
      throw new TraceValidationError(`VM stream frame ${key} must be a string`);
    }
  }
  if (!VM_STREAMS.has(frame.stream as string)) {
    throw new TraceValidationError(`unsupported VM stream: ${String(frame.stream)}`);
  }
  if (!isRecord(frame.data)) {
    throw new TraceValidationError("VM stream frame data must be an object");
  }
  return frame as VmStreamFrame;
}

export function validateRunFixture(fixture: unknown): TraceJsonRecord {
  if (!isRecord(fixture)) {
    throw new TraceValidationError("run fixture must be an object");
  }
  if (fixture.schema !== RUN_FIXTURE_SCHEMA_VERSION) {
    throw new TraceValidationError("run fixture schema mismatch");
  }
  if (typeof fixture.name !== "string" || !fixture.name) {
    throw new TraceValidationError("run fixture name must be a non-empty string");
  }
  if (!Array.isArray(fixture.labels)) {
    throw new TraceValidationError("run fixture labels must be an array");
  }
  if (!isRecord(fixture.run)) {
    throw new TraceValidationError("run fixture run must be an object");
  }
  for (const key of ["run_id", "agent", "task", "status", "started_at", "finished_at"]) {
    if (typeof fixture.run[key] !== "string" || !fixture.run[key]) {
      throw new TraceValidationError(`run fixture run.${key} must be a non-empty string`);
    }
  }
  if (!Array.isArray(fixture.events) || fixture.events.length === 0) {
    throw new TraceValidationError("run fixture events must be a non-empty array");
  }
  fixture.events.forEach(validateTraceEvent);
  normalizeVmStream(fixture.vm_stream);
  if (!isRecord(fixture.expected)) {
    throw new TraceValidationError("run fixture expected must be an object");
  }
  if (!isRecord(fixture.replay)) {
    throw new TraceValidationError("run fixture replay must be an object");
  }
  return fixture;
}

export async function loadRunFixture(path: string): Promise<TraceJsonRecord> {
  return validateRunFixture(JSON.parse(await readFile(path, "utf8")) as unknown);
}

export async function writeRunFixture(path: string, fixture: unknown): Promise<string> {
  const validated = validateRunFixture(fixture);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(validated, null, 2)}\n`, "utf8");
  return path;
}

function buildVmFrame(event: TraceEvent): VmStreamFrame {
  const observation = validateObservation(event.observation);
  const stream = vmStreamForObservation(observation);
  return {
    schema: VM_STREAM_SCHEMA_VERSION,
    seq: event.seq,
    timestamp: event.timestamp,
    event_id: event.event_id,
    stream,
    status: observation.status,
    text: observation.text,
    data: jsonRecord(observation.data),
  };
}

function vmStreamForObservation(observation: TraceObservation): string {
  if (observation.kind === "tool_call") {
    return "tool_call";
  }
  if (observation.kind === "tool_result") {
    return "tool_result";
  }
  if (observation.kind === "metric") {
    return "metric";
  }
  if (observation.kind === "control") {
    return "lifecycle";
  }
  if (observation.kind === "error") {
    return "stderr";
  }
  if (observation.channel === "user") {
    return "stdin";
  }
  return "stdout";
}

function observationFromPayload(eventType: string, payload: TraceJsonRecord, role?: string): TraceObservation {
  if (eventType === "tool_call") {
    return {
      kind: "tool_call",
      channel: "tool",
      status: payload.error === undefined ? "ok" : "error",
      text: `call ${String(payload.name ?? "tool")}`,
      data: jsonRecord({ name: payload.name, args: payload.arguments ?? {}, call_id: payload.call_id, output: payload.output, error: payload.error }),
    };
  }
  if (eventType === "metric") {
    return {
      kind: "metric",
      channel: "system",
      status: "ok",
      text: String(payload.name ?? "metric"),
      data: jsonRecord({ name: payload.name, value: payload.value, unit: payload.unit ?? "count" }),
    };
  }
  if (eventType === "control") {
    return {
      kind: "control",
      channel: "system",
      status: "ok",
      text: String(payload.name ?? "control"),
      data: jsonRecord(payload.data ?? {}),
    };
  }
  return {
    kind: "message",
    channel: role ?? "agent",
    status: "ok",
    text: textValue(payload.content ?? payload.text ?? ""),
    data: jsonRecord(payload.metadata ?? {}),
  };
}

function eventTypePhase(eventType: string): string {
  if (eventType.includes(".")) {
    return eventType.split(".")[0] || "event";
  }
  if (eventType === "message") {
    return "output";
  }
  if (eventType === "tool_call") {
    return "tool";
  }
  if (eventType === "metric") {
    return "metric";
  }
  if (eventType === "control") {
    return "lifecycle";
  }
  return eventType || "event";
}

function validateObservation(value: unknown): TraceObservation {
  if (!isRecord(value)) {
    throw new TraceValidationError("trace observation must be an object");
  }
  for (const key of ["kind", "channel", "status", "text"]) {
    if (typeof value[key] !== "string") {
      throw new TraceValidationError(`trace observation ${key} must be a string`);
    }
  }
  if (!isRecord(value.data)) {
    throw new TraceValidationError("trace observation data must be an object");
  }
  return value as TraceObservation;
}

function normalizeVmStream(vmStream: unknown): VmStreamFrame[] {
  if (!Array.isArray(vmStream)) {
    throw new TraceValidationError("VM stream must be an array");
  }
  return vmStream.map(validateVmStreamFrame);
}

function timestampFor(seq: number, startedAt: string): string {
  const parsed = Date.parse(startedAt);
  const base = Number.isFinite(parsed) ? parsed : Date.parse("2026-01-01T00:00:00.000Z");
  return new Date(base + seq * 50).toISOString();
}

function textValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(jsonValue(value));
}

function dropUndefined(value: TraceJsonRecord): TraceJsonRecord {
  const result: TraceJsonRecord = {};
  for (const [key, item] of Object.entries(value)) {
    if (item !== undefined) {
      result[key] = item;
    }
  }
  return result;
}

function jsonRecord(value: unknown): TraceJsonRecord {
  const json = jsonValue(value);
  return isRecord(json) ? json : {};
}

function jsonValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => jsonValue(item));
  }
  if (isRecord(value)) {
    const result: TraceJsonRecord = {};
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

function isRecord(value: unknown): value is TraceJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
