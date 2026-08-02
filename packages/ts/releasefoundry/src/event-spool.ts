import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { JsonRecord } from "./index.js";

export const EVENT_ENVELOPE_SCHEMA_VERSION = "releasefoundry.event.v1";
export const EVENT_SPOOL_BATCH_SCHEMA_VERSION = "releasefoundry.event_spool_batch.v1";
export const EVENT_SPOOL_CONTRACT_VERSION = "releasefoundry.event_spool.v1";
export const NON_DROPPABLE_PURPOSES = new Set(["audit", "billing", "evidence", "security"]);

export class EventSpoolError extends Error {}
export class EventValidationError extends EventSpoolError {}
export class EventBackpressureError extends EventSpoolError {}
export class RetryableDeliveryError extends EventSpoolError {}
export class PermanentDeliveryError extends EventSpoolError {}

export interface EventEnvelope extends JsonRecord {
  schema_version: typeof EVENT_ENVELOPE_SCHEMA_VERSION;
  event_id: string;
  tenant_id: string;
  project_id: string;
  run_id: string;
  source: string;
  event_type: string;
  sequence: number;
  occurred_at: string;
  purpose: string;
  data_class: string;
  consent: string;
  residency: string;
  retention_class: string;
  learning_allowed: boolean;
  payload: unknown;
  causal_parent: string | null;
  metadata: JsonRecord;
  integrity_sha256: string;
}

export interface EventSpoolBatch extends JsonRecord {
  schema_version: typeof EVENT_SPOOL_BATCH_SCHEMA_VERSION;
  batch_id: string;
  idempotency_key: string;
  payload_sha256: string;
  events: EventEnvelope[];
  attempts: number;
  next_attempt_at: string;
  status: "pending" | "leased" | "dead_letter";
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_failure_code: string | null;
  last_failure_message: string | null;
  created_at: string;
  updated_at: string;
  dead_lettered_at?: string;
}

export interface EventSpoolBatchMetadata extends JsonRecord {
  schema_version: typeof EVENT_SPOOL_BATCH_SCHEMA_VERSION;
  batch_id: string;
  idempotency_key: string;
  payload_sha256: string;
  event_count: number;
  purposes: string[];
  tenant_ids: string[];
  project_ids: string[];
  run_ids: string[];
  status: EventSpoolBatch["status"];
  attempts: number;
  next_attempt_at: string;
  lease_expires_at: string | null;
  last_failure_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventFlushReport extends JsonRecord {
  attempted: number;
  delivered: number;
  retried: number;
  dead_lettered: number;
  remaining: number;
}

export type EventSpoolSender = (batch: EventSpoolBatchDelivery) => unknown;

export interface EventSpoolBatchDelivery extends JsonRecord {
  schema_version: typeof EVENT_SPOOL_BATCH_SCHEMA_VERSION;
  batch_id: string;
  idempotency_key: string;
  payload_sha256: string;
  events: EventEnvelope[];
}

const SECRET_KEY_RE = /(?:^|[_-])(api[_-]?key|bearer|authorization|password|secret|token|oauth[_-]?(?:code|state|token)|smtp|otp|private[_-]?key)(?:$|[_-])/i;

export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortJson(value));
}

export function sha256Json(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => sortJson(item));
  if (isRecord(value)) {
    const result: JsonRecord = {};
    for (const key of Object.keys(value).sort()) result[key] = sortJson(value[key]);
    return result;
  }
  return value;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new EventValidationError(`${field} must be a non-empty string`);
  return value;
}

function utcIso(value?: Date | string): string {
  const date = value === undefined ? new Date() : new Date(value);
  if (!Number.isFinite(date.getTime())) throw new EventValidationError("timestamp must be ISO-8601");
  return date.toISOString();
}

function validatePublicMetadata(metadata: JsonRecord): void {
  for (const [key, value] of Object.entries(metadata)) {
    if (SECRET_KEY_RE.test(key)) throw new EventValidationError(`secret-bearing metadata key is not allowed: ${key}`);
    if (isRecord(value)) validatePublicMetadata(value);
    if (Array.isArray(value)) {
      for (const item of value) if (isRecord(item)) validatePublicMetadata(item);
    }
  }
}

function withoutIntegrity(event: JsonRecord): JsonRecord {
  const result = { ...event };
  delete result.integrity_sha256;
  return result;
}

export function buildEventEnvelope(options: {
  tenantId: string;
  projectId: string;
  runId: string;
  source: string;
  eventType: string;
  payload: unknown;
  sequence?: number;
  occurredAt?: Date | string;
  purpose?: string;
  dataClass?: string;
  consent?: string;
  residency?: string;
  retentionClass?: string;
  learningAllowed?: boolean;
  causalParent?: string | null;
  eventId?: string;
  metadata?: JsonRecord;
}): EventEnvelope {
  const sequence = options.sequence ?? 0;
  if (!Number.isInteger(sequence) || sequence < 0) throw new EventValidationError("sequence must be a non-negative integer");
  const learningAllowed = options.learningAllowed ?? false;
  if (typeof learningAllowed !== "boolean") throw new EventValidationError("learning_allowed must be boolean");
  const event: JsonRecord = {
    schema_version: EVENT_ENVELOPE_SCHEMA_VERSION,
    event_id: requiredText(options.eventId ?? `evt_${randomUUID().replaceAll("-", "")}`, "event_id"),
    tenant_id: requiredText(options.tenantId, "tenant_id"),
    project_id: requiredText(options.projectId, "project_id"),
    run_id: requiredText(options.runId, "run_id"),
    source: requiredText(options.source, "source"),
    event_type: requiredText(options.eventType, "event_type"),
    sequence,
    occurred_at: utcIso(options.occurredAt),
    purpose: requiredText(options.purpose ?? "telemetry", "purpose"),
    data_class: requiredText(options.dataClass ?? "operational", "data_class"),
    consent: requiredText(options.consent ?? "product_use_not_training", "consent"),
    residency: requiredText(options.residency ?? "customer_region", "residency"),
    retention_class: requiredText(options.retentionClass ?? "standard", "retention_class"),
    learning_allowed: learningAllowed,
    payload: options.payload,
    causal_parent: options.causalParent ?? null,
    metadata: options.metadata ?? {},
  };
  if (!isRecord(event.metadata)) throw new EventValidationError("metadata must be an object");
  validatePublicMetadata(event.metadata);
  const eventWithIntegrity = { ...event, integrity_sha256: sha256Json(event) } as EventEnvelope;
  JSON.stringify(eventWithIntegrity);
  return eventWithIntegrity;
}

export function validateEventEnvelope(value: JsonRecord): EventEnvelope {
  if (value.schema_version !== EVENT_ENVELOPE_SCHEMA_VERSION) throw new EventValidationError("unsupported event schema_version");
  for (const field of ["event_id", "tenant_id", "project_id", "run_id", "source", "event_type", "occurred_at", "purpose", "data_class", "consent", "residency", "retention_class"]) {
    requiredText(value[field], field);
  }
  if (!Number.isInteger(value.sequence) || Number(value.sequence) < 0) throw new EventValidationError("sequence must be a non-negative integer");
  if (typeof value.learning_allowed !== "boolean") throw new EventValidationError("learning_allowed must be boolean");
  if (!("payload" in value)) throw new EventValidationError("payload is required");
  if (!isRecord(value.metadata)) throw new EventValidationError("metadata must be an object");
  validatePublicMetadata(value.metadata);
  if (value.integrity_sha256 !== sha256Json(withoutIntegrity(value))) throw new EventValidationError("event integrity_sha256 mismatch");
  return JSON.parse(JSON.stringify(value)) as EventEnvelope;
}

export function deterministicSample(eventId: string, rate: number): boolean {
  if (!Number.isFinite(rate) || rate < 0 || rate > 1) throw new EventValidationError("sampling_rate must be between 0 and 1");
  if (rate >= 1) return true;
  if (rate <= 0) return false;
  const digest = createHash("sha256").update(eventId, "utf8").digest("hex").slice(0, 16);
  const bucket = Number.parseInt(digest, 16);
  return bucket / 0xffffffffffffffff < rate;
}

export function buildTraceIngestionSender(
  ingestTrace: (tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId: string; idempotencyKey: string; apiKeyId?: string }) => unknown,
  options: { tenantId: string; projectId: string; runId: string; apiKeyId?: string },
): EventSpoolSender {
  return (batch) => {
    const observations: JsonRecord[] = [];
    for (const event of batch.events) {
      if (!isRecord(event.payload)) throw new PermanentDeliveryError("trace ingestion requires mapping event payloads");
      observations.push(JSON.parse(JSON.stringify(event.payload)) as JsonRecord);
    }
    return ingestTrace(options.tenantId, options.projectId, options.runId, observations, {
      batchId: batch.batch_id,
      idempotencyKey: batch.idempotency_key,
      apiKeyId: options.apiKeyId,
    });
  };
}

export class DurableEventSpool {
  readonly directory: string;
  readonly pendingDirectory: string;
  readonly deadDirectory: string;
  readonly maxBatches: number;
  readonly maxBytes: number;
  readonly samplingRate: number;
  readonly dropPolicy: "reject" | "drop_oldest";
  readonly leaseSeconds: number;
  readonly maxAttempts: number;
  readonly retryBaseSeconds: number;
  readonly retryMaxSeconds: number;

  constructor(options: {
    directory: string;
    maxBatches?: number;
    maxBytes?: number;
    samplingRate?: number;
    dropPolicy?: "reject" | "drop_oldest";
    leaseSeconds?: number;
    maxAttempts?: number;
    retryBaseSeconds?: number;
    retryMaxSeconds?: number;
  }) {
    this.directory = options.directory;
    this.pendingDirectory = join(this.directory, "pending");
    this.deadDirectory = join(this.directory, "dead-letter");
    this.maxBatches = options.maxBatches ?? 1_000;
    this.maxBytes = options.maxBytes ?? 64 * 1024 * 1024;
    this.samplingRate = options.samplingRate ?? 1;
    this.dropPolicy = options.dropPolicy ?? "reject";
    this.leaseSeconds = options.leaseSeconds ?? 60;
    this.maxAttempts = options.maxAttempts ?? 8;
    this.retryBaseSeconds = options.retryBaseSeconds ?? 1;
    this.retryMaxSeconds = options.retryMaxSeconds ?? 300;
    if (this.maxBatches < 1 || this.maxBytes < 1 || this.leaseSeconds < 1 || this.maxAttempts < 1) throw new EventValidationError("spool bounds and lease settings must be positive");
    deterministicSample("validation", this.samplingRate);
    mkdirSync(this.pendingDirectory, { recursive: true });
    mkdirSync(this.deadDirectory, { recursive: true });
  }

  append(event: JsonRecord): EventSpoolBatchMetadata | null {
    return this.enqueue([event]);
  }

  enqueue(events: JsonRecord[], options: { batchId?: string; idempotencyKey?: string; now?: Date | string } = {}): EventSpoolBatchMetadata | null {
    if (events.length === 0) throw new EventValidationError("spool enqueue requires at least one event");
    const normalized = events.map((event) => validateEventEnvelope(event));
    const sampled = normalized.filter((event) => NON_DROPPABLE_PURPOSES.has(event.purpose) || deterministicSample(event.event_id, this.samplingRate));
    if (sampled.length === 0) return null;
    const batch = this.newBatch(sampled, options);
    const encoded = Buffer.byteLength(canonicalJson(batch), "utf8");
    this.recoverExpiredLeases(options.now);
    this.makeCapacity(encoded, batch);
    this.atomicWrite(join(this.pendingDirectory, `${batch.batch_id}.json`), batch);
    return this.batchMetadata(batch);
  }

  listBatches(options: { includeDeadLetters?: boolean; now?: Date | string } = {}): EventSpoolBatchMetadata[] {
    this.recoverExpiredLeases(options.now);
    const files = [...this.batchFiles(this.pendingDirectory)];
    if (options.includeDeadLetters) files.push(...this.batchFiles(this.deadDirectory));
    return files
      .map((file) => this.readBatch(file))
      .map((batch) => this.batchMetadata(batch))
      .sort((left, right) => `${left.created_at}:${left.batch_id}`.localeCompare(`${right.created_at}:${right.batch_id}`));
  }

  batchMetadata(batch: EventSpoolBatch): EventSpoolBatchMetadata {
    return {
      schema_version: EVENT_SPOOL_BATCH_SCHEMA_VERSION,
      batch_id: batch.batch_id,
      idempotency_key: batch.idempotency_key,
      payload_sha256: batch.payload_sha256,
      event_count: batch.events.length,
      purposes: [...new Set(batch.events.map((event) => event.purpose))].sort(),
      tenant_ids: [...new Set(batch.events.map((event) => event.tenant_id))].sort(),
      project_ids: [...new Set(batch.events.map((event) => event.project_id))].sort(),
      run_ids: [...new Set(batch.events.map((event) => event.run_id))].sort(),
      status: batch.status,
      attempts: batch.attempts,
      next_attempt_at: batch.next_attempt_at,
      lease_expires_at: batch.lease_expires_at,
      last_failure_code: batch.last_failure_code,
      created_at: batch.created_at,
      updated_at: batch.updated_at,
    };
  }

  storageMetadata(): JsonRecord {
    const pending = this.batchFiles(this.pendingDirectory);
    const dead = this.batchFiles(this.deadDirectory);
    return {
      schema_version: EVENT_SPOOL_CONTRACT_VERSION,
      directory: this.directory,
      pending_batches: pending.length,
      dead_letter_batches: dead.length,
      stored_bytes: [...pending, ...dead].reduce((total, file) => total + statSync(file).size, 0),
      max_batches: this.maxBatches,
      max_bytes: this.maxBytes,
      sampling_rate: this.samplingRate,
      drop_policy: this.dropPolicy,
    };
  }

  flush(sender: EventSpoolSender, options: { maxBatches?: number; now?: Date | string; leaseOwner?: string } = {}): EventFlushReport {
    const now = new Date(options.now ?? Date.now());
    const owner = options.leaseOwner ?? `spool_${randomUUID().replaceAll("-", "")}`;
    let attempted = 0;
    let delivered = 0;
    let retried = 0;
    let deadLettered = 0;
    this.recoverExpiredLeases(now);
    for (const file of this.batchFiles(this.pendingDirectory)) {
      if (options.maxBatches !== undefined && attempted >= options.maxBatches) break;
      const batch = this.readBatch(file);
      if (new Date(batch.next_attempt_at) > now) continue;
      const leased = this.lease(file, owner, now);
      if (leased === null) continue;
      attempted += 1;
      let failed = false;
      try {
        const result = sender(this.deliveryPayload(leased));
        if (isRecord(result) && result.accepted === false) {
          const error = result.error_code ? String(result.error_code) : "delivery_rejected";
          if (result.retryable === true) throw new RetryableDeliveryError(error);
          throw new PermanentDeliveryError(error);
        }
      } catch (error) {
        failed = true;
        if (error instanceof RetryableDeliveryError && leased.attempts < this.maxAttempts) {
          this.retry(file, leased, error, now);
          retried += 1;
        } else {
          this.deadLetter(file, leased, error instanceof Error ? error : new Error(String(error)), now);
          deadLettered += 1;
        }
      }
      if (!failed) {
        if (existsSync(file)) unlinkSync(file);
        delivered += 1;
      }
    }
    return { attempted, delivered, retried, dead_lettered: deadLettered, remaining: this.batchFiles(this.pendingDirectory).length };
  }

  redrive(batchId: string, options: { now?: Date | string } = {}): EventSpoolBatchMetadata {
    requiredText(batchId, "batch_id");
    const source = join(this.deadDirectory, `${batchId}.json`);
    if (!existsSync(source)) throw new EventSpoolError("dead-letter batch not found");
    const batch = this.readBatch(source);
    const now = utcIso(options.now);
    batch.status = "pending";
    batch.attempts = 0;
    batch.next_attempt_at = now;
    batch.lease_owner = null;
    batch.lease_expires_at = null;
    batch.last_failure_code = null;
    batch.last_failure_message = null;
    batch.updated_at = now;
    this.makeCapacity(Buffer.byteLength(canonicalJson(batch), "utf8"), batch);
    this.atomicWrite(join(this.pendingDirectory, `${batch.batch_id}.json`), batch);
    unlinkSync(source);
    return this.batchMetadata(batch);
  }

  private newBatch(events: EventEnvelope[], options: { batchId?: string; idempotencyKey?: string; now?: Date | string }): EventSpoolBatch {
    const batchId = requiredText(options.batchId ?? `batch_${randomUUID().replaceAll("-", "")}`, "batch_id");
    const idempotencyKey = requiredText(options.idempotencyKey ?? `spool_${batchId}`, "idempotency_key");
    const now = utcIso(options.now);
    return {
      schema_version: EVENT_SPOOL_BATCH_SCHEMA_VERSION,
      batch_id: batchId,
      idempotency_key: idempotencyKey,
      payload_sha256: sha256Json(events),
      events,
      attempts: 0,
      next_attempt_at: now,
      status: "pending",
      lease_owner: null,
      lease_expires_at: null,
      last_failure_code: null,
      last_failure_message: null,
      created_at: now,
      updated_at: now,
    };
  }

  private deliveryPayload(batch: EventSpoolBatch): EventSpoolBatchDelivery {
    return {
      schema_version: EVENT_SPOOL_BATCH_SCHEMA_VERSION,
      batch_id: batch.batch_id,
      idempotency_key: batch.idempotency_key,
      payload_sha256: batch.payload_sha256,
      events: batch.events,
    };
  }

  private recoverExpiredLeases(nowValue?: Date | string): void {
    const now = new Date(nowValue ?? Date.now());
    for (const file of this.batchFiles(this.pendingDirectory)) {
      const batch = this.readBatch(file);
      if (batch.status === "leased" && batch.lease_expires_at !== null && new Date(batch.lease_expires_at) <= now) {
        batch.status = "pending";
        batch.lease_owner = null;
        batch.lease_expires_at = null;
        batch.updated_at = now.toISOString();
        this.atomicWrite(file, batch);
      }
    }
  }

  private lease(file: string, owner: string, now: Date): EventSpoolBatch | null {
    const batch = this.readBatch(file);
    if (batch.status !== "pending") return null;
    batch.status = "leased";
    batch.lease_owner = owner;
    batch.lease_expires_at = new Date(now.getTime() + this.leaseSeconds * 1000).toISOString();
    batch.attempts += 1;
    batch.updated_at = now.toISOString();
    this.atomicWrite(file, batch);
    return batch;
  }

  private retry(file: string, batch: EventSpoolBatch, error: Error, now: Date): void {
    const delay = Math.min(this.retryMaxSeconds, this.retryBaseSeconds * (2 ** Math.max(0, batch.attempts - 1)));
    batch.status = "pending";
    batch.lease_owner = null;
    batch.lease_expires_at = null;
    batch.next_attempt_at = new Date(now.getTime() + delay * 1000).toISOString();
    batch.last_failure_code = "retryable_delivery_failure";
    batch.last_failure_message = safeError(error);
    batch.updated_at = now.toISOString();
    this.atomicWrite(file, batch);
  }

  private deadLetter(file: string, batch: EventSpoolBatch, error: Error, now: Date): void {
    batch.status = "dead_letter";
    batch.lease_owner = null;
    batch.lease_expires_at = null;
    batch.last_failure_code = "delivery_failed";
    batch.last_failure_message = safeError(error);
    batch.dead_lettered_at = now.toISOString();
    batch.updated_at = now.toISOString();
    this.atomicWrite(join(this.deadDirectory, `${batch.batch_id}.json`), batch);
    if (existsSync(file)) unlinkSync(file);
  }

  private makeCapacity(incomingBytes: number, candidate: EventSpoolBatch): void {
    const files = [...this.batchFiles(this.pendingDirectory), ...this.batchFiles(this.deadDirectory)];
    let count = files.length;
    let bytes = files.reduce((total, file) => total + statSync(file).size, 0);
    if (count < this.maxBatches && bytes + incomingBytes <= this.maxBytes) return;
    if (this.dropPolicy !== "drop_oldest" || !batchIsDroppable(candidate)) throw new EventBackpressureError("event spool capacity exceeded; write rejected");
    for (const file of this.batchFiles(this.pendingDirectory).sort((left, right) => statSync(left).mtimeMs - statSync(right).mtimeMs)) {
      if (count < this.maxBatches && bytes + incomingBytes <= this.maxBytes) break;
      const batch = this.readBatch(file);
      if (batch.status !== "pending" || !batchIsDroppable(batch)) continue;
      bytes -= statSync(file).size;
      count -= 1;
      unlinkSync(file);
    }
    if (count >= this.maxBatches || bytes + incomingBytes > this.maxBytes) throw new EventBackpressureError("event spool capacity exceeded; non-droppable data blocks drop_oldest");
  }

  private batchFiles(directory: string): string[] {
    return readdirSync(directory).filter((name) => name.endsWith(".json")).map((name) => join(directory, name));
  }

  private readBatch(file: string): EventSpoolBatch {
    try {
      const value = JSON.parse(readFileSync(file, "utf8")) as JsonRecord;
      if (!isRecord(value) || value.schema_version !== EVENT_SPOOL_BATCH_SCHEMA_VERSION || !Array.isArray(value.events)) throw new Error("invalid schema");
      return value as EventSpoolBatch;
    } catch (error) {
      throw new EventSpoolError(`cannot read spool batch ${file.split(/[\\/]/).pop() ?? file}`);
    }
  }

  private atomicWrite(file: string, value: JsonRecord): void {
    const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`;
    writeFileSync(temporary, `${canonicalJson(value)}\n`, "utf8");
    renameSync(temporary, file);
  }
}

function batchIsDroppable(batch: EventSpoolBatch): boolean {
  return batch.events.length > 0 && batch.events.every((event) => event.purpose === "telemetry");
}

function safeError(error: Error): string {
  return `${error.name}: ${error.message}`
    .replace(SECRET_KEY_RE, "<redacted>")
    .replace(/(api[_-]?key|authorization|bearer|token|secret|password|otp|code|state)\s*[=:]\s*\S+/gi, "$1=<redacted>")
    .slice(0, 240);
}
