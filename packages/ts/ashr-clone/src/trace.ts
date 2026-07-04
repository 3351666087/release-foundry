import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

export type TraceJsonRecord = Record<string, unknown>;

export const TRACE_EVENT_SCHEMA_VERSION = "ashr.clone.trace.v1";
export const RUN_FIXTURE_SCHEMA_VERSION = "ashr.clone.run_fixture.v1";

export interface TraceEvent extends TraceJsonRecord {
  schema: typeof TRACE_EVENT_SCHEMA_VERSION;
  type: "trace_event";
  event_id: string;
  timestamp: string;
  run_id: string;
  case_id?: string;
  turn_index?: number;
  event_type: string;
  role?: string;
  payload: TraceJsonRecord;
}

export interface VmStreamFrame extends TraceJsonRecord {
  frame_id: string;
  observation_id?: string;
  provider: string;
  session_id: string;
  ts: number;
  type: string;
  data: TraceJsonRecord;
  metadata: TraceJsonRecord;
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
    this.startedAt = options.startedAt ?? new Date().toISOString();
  }

  append(eventType: string, payload: TraceJsonRecord = {}, options: { role?: string; caseId?: string; turnIndex?: number } = {}): TraceEvent {
    const event: TraceEvent = {
      schema: TRACE_EVENT_SCHEMA_VERSION,
      type: "trace_event",
      event_id: `evt_${this.items.length + 1}`,
      timestamp: new Date().toISOString(),
      run_id: this.runId,
      case_id: options.caseId,
      turn_index: options.turnIndex,
      event_type: eventType,
      role: options.role,
      payload: jsonRecord({ source: this.source, ...payload }),
    };
    this.items.push(dropUndefined(event) as TraceEvent);
    return this.items[this.items.length - 1];
  }

  message(role: string, content: unknown, data: TraceJsonRecord = {}): TraceEvent {
    return this.append("message", { content: jsonValue(content), metadata: jsonRecord(data) }, { role });
  }

  toolCall(name: string, argumentsValue: unknown = {}, options: { callId?: string; output?: unknown; error?: unknown } = {}): TraceEvent {
    return this.append("tool_call", {
      name,
      call_id: options.callId ?? `tool_${this.items.length + 1}`,
      arguments: jsonValue(argumentsValue),
      output: options.output === undefined ? undefined : jsonValue(options.output),
      error: options.error === undefined ? undefined : jsonValue(options.error),
    });
  }

  metric(name: string, value: unknown): TraceEvent {
    return this.append("metric", { name, value: jsonValue(value) });
  }

  control(name: string, data: TraceJsonRecord = {}): TraceEvent {
    return this.append("control", { name, data: jsonRecord(data) });
  }

  events(): TraceEvent[] {
    return this.items.map((item) => jsonRecord(item) as TraceEvent);
  }
}

export function buildVmStream(events: TraceEvent[], options: { provider?: string; sessionId?: string } = {}): VmStreamFrame[] {
  return events.map((event, index) => ({
    frame_id: `frame_${index + 1}`,
    provider: options.provider ?? "ts-trace-recorder",
    session_id: options.sessionId ?? event.run_id,
    ts: index,
    type: event.event_type,
    data: jsonRecord(event.payload),
    metadata: { event_id: event.event_id, schema: event.schema },
  }));
}

export function traceEventsFromVmStream(runId: string, vmStream: unknown, options: { source?: string } = {}): TraceEvent[] {
  const frames = normalizeVmStream(vmStream);
  return frames.map((frame, index) => ({
    schema: TRACE_EVENT_SCHEMA_VERSION,
    type: "trace_event",
    event_id: String(frame.metadata.event_id ?? `evt_from_frame_${index + 1}`),
    timestamp: new Date().toISOString(),
    run_id: runId,
    event_type: frame.type,
    role: typeof frame.data.role === "string" ? frame.data.role : undefined,
    payload: jsonRecord({ source: options.source ?? frame.provider, ...frame.data }),
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
  const fixture = {
    schema: RUN_FIXTURE_SCHEMA_VERSION,
    name: options.name,
    labels: options.labels ?? ["a1", "typescript", "trace"],
    run: {
      run_id: options.runId,
      dataset_id: options.datasetId ?? "trace-dataset",
      runner_id: options.runnerId ?? "ts-trace-recorder",
      status: "passed",
      total_cases: 1,
      trace_completeness: options.events.length > 0 ? 1 : 0,
    },
    events: options.events.map((event) => jsonRecord(event)),
    vm_stream: buildVmStream(options.events),
    expected: jsonRecord(options.expected ?? {}),
    replay: { source: "packages/ts/ashr-clone", deterministic: false, ...jsonRecord(options.replay ?? {}) },
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
  for (const key of ["event_id", "timestamp", "run_id", "event_type"]) {
    if (typeof event[key] !== "string" || !event[key]) {
      throw new TraceValidationError(`trace event ${key} must be a non-empty string`);
    }
  }
  if (!isRecord(event.payload)) {
    throw new TraceValidationError("trace event payload must be an object");
  }
  return event as TraceEvent;
}

export function validateVmStreamFrame(frame: unknown): VmStreamFrame {
  if (!isRecord(frame)) {
    throw new TraceValidationError("VM stream frame must be an object");
  }
  for (const key of ["frame_id", "provider", "session_id", "type"]) {
    if (typeof frame[key] !== "string" || !frame[key]) {
      throw new TraceValidationError(`VM stream frame ${key} must be a non-empty string`);
    }
  }
  if (typeof frame.ts !== "number" || !Number.isFinite(frame.ts) || frame.ts < 0) {
    throw new TraceValidationError("VM stream frame ts must be a non-negative number");
  }
  if (!isRecord(frame.data)) {
    throw new TraceValidationError("VM stream frame data must be an object");
  }
  if (!isRecord(frame.metadata)) {
    throw new TraceValidationError("VM stream frame metadata must be an object");
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
  for (const key of ["run_id", "dataset_id", "runner_id", "status"]) {
    if (typeof fixture.run[key] !== "string" || !fixture.run[key]) {
      throw new TraceValidationError(`run fixture run.${key} must be a non-empty string`);
    }
  }
  if (!Array.isArray(fixture.events)) {
    throw new TraceValidationError("run fixture events must be an array");
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

function normalizeVmStream(vmStream: unknown): VmStreamFrame[] {
  if (!Array.isArray(vmStream)) {
    throw new TraceValidationError("VM stream must be an array");
  }
  return vmStream.map(validateVmStreamFrame);
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
