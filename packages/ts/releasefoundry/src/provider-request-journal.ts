import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { ProviderStreamLedger, type ProviderStreamSnapshot } from "./provider-stream.js";

export const PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION = "releasefoundry.provider_request_journal.typescript.v1";
export const PROVIDER_REQUEST_MODALITIES = ["text", "image", "audio", "file", "video"] as const;
export const PROVIDER_JOURNAL_SCHEMA_VERSION = PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION;
export const PROVIDER_MODALITIES = PROVIDER_REQUEST_MODALITIES;
export const PROVIDER_JOURNAL_STATES = [
  "reserved", "in_flight", "retry_wait", "succeeded", "failed_terminal", "indeterminate",
] as const;

export type ProviderRequestModality = (typeof PROVIDER_REQUEST_MODALITIES)[number];
export type ProviderRequestState = (typeof PROVIDER_JOURNAL_STATES)[number];
export type ProviderJson = Record<string, unknown>;
export type ProviderRequestIdentity = ProviderRequestScope;
export type JournalDecision = ProviderRequestRunResult;

export interface ProviderRequestScope {
  tenantId: string;
  projectId: string;
  provider: string;
  model: string;
  operation?: string;
}

export interface ProviderRequestPart {
  type: ProviderRequestModality;
  text?: string;
  data?: string | Uint8Array;
  url?: string;
  path?: string;
  media_type?: string;
  mime_type?: string;
  filename?: string;
  name?: string;
}

export interface ProviderRequestMessage {
  role: string;
  parts?: ProviderRequestPart[];
  content?: string | ProviderRequestPart[];
}

export interface ProviderRequestUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cached_input_tokens?: number;
  reasoning_tokens?: number;
}

export interface ProviderRequestExecutionEvidence {
  usage?: Partial<ProviderRequestUsage>;
  finishReason?: string;
  toolCalls?: Array<{ id?: string; name?: string; arguments?: unknown }>;
  responseFingerprint?: string;
  providerRequestId?: string;
  metadata?: ProviderJson;
  streamSnapshot?: ProviderStreamSnapshot;
}

export interface ProviderRequestJournalEntry {
  schema_version: typeof PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION;
  entry_id: string;
  scope_fingerprint: string;
  request_fingerprint: string;
  idempotency_fingerprint: string;
  request_evidence: ProviderRequestEvidence;
  state: ProviderRequestState;
  attempt_count: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  next_retry_at: string | null;
  lease_owner_fingerprint: string | null;
  lease_expires_at: string | null;
  fencing_token: number;
  stream_observed: boolean;
  stream_snapshot: ProviderStreamSnapshot | null;
  part_evidence: ProviderModalityEvidence[];
  usage_evidence: ProviderRequestUsage | null;
  completion_evidence: ProviderCompletionEvidence | null;
  error_evidence: ProviderErrorEvidence | null;
  recovery_count: number;
  persistence_capabilities: ProviderJournalPersistenceCapabilities;
  /** @deprecated Use entry_id. Public compatibility alias; never persisted. */
  journal_key?: string;
  /** @deprecated Use attempt_count. Public compatibility alias; never persisted. */
  attempts?: number;
  /** @deprecated Use lease_owner_fingerprint. Public compatibility alias; never persisted. */
  lease_owner_sha256?: string | null;
  /** @deprecated Use part_evidence or request_evidence. Public compatibility alias; never persisted. */
  modality_evidence?: ProviderModalityEvidence[];
}

export interface ProviderRequestEvidence {
  modality_counts: Record<ProviderRequestModality, number>;
  modalities_present: ProviderRequestModality[];
  raw_prompt_persisted: false;
  raw_media_persisted: false;
  raw_url_persisted: false;
  raw_credential_persisted: false;
}

export interface ProviderJournalPersistenceCapabilities {
  storage_kind: "local_json_file";
  restart_persistent: true;
  atomic_replace: true;
  same_process_identity_claim: true;
  cross_process_lock: false;
  multi_process_safe: false;
  multi_host_safe: false;
  power_loss_durability_proven: false;
  crash_recovery: "in_flight_to_indeterminate";
}

export interface ProviderModalityEvidence {
  type: ProviderRequestModality;
  media_type: string | null;
  filename_sha256: string | null;
  content_sha256: string;
  byte_length: number;
}

export interface ProviderCompletionEvidence {
  finish_reason: string;
  tool_call_count: number;
  tool_call_evidence: Array<{ id_sha256: string | null; name: string; arguments_sha256: string }>;
  response_fingerprint: string | null;
  provider_request_id_sha256: string | null;
  metadata: ProviderJson;
}

export interface ProviderErrorEvidence {
  kind: string;
  message_sha256: string;
  retryable: boolean;
  status_code: number | null;
}

export interface ProviderRequestRunOptions {
  scope: ProviderRequestScope;
  idempotencyKey: string;
  messages: ProviderRequestMessage[];
  execute: (context: {
    attempt: number;
    requestFingerprint: string;
    journalKey: string;
    fencingToken: number;
    markStreamObserved: (snapshot: ProviderStreamSnapshot) => Promise<void>;
  }) => Promise<ProviderRequestExecutionEvidence>;
  leaseOwner?: string;
  leaseDurationMs?: number;
  maxAttempts?: number;
  retryDelayMs?: number | ((attempt: number) => number);
  shouldRetry?: (error: unknown, attempt: number) => boolean;
}

export type ProviderRequestReconcileDecision =
  | { outcome: "retry"; reason: string }
  | { outcome: "reserved"; reason: string }
  | { outcome: "succeeded"; evidence: ProviderRequestExecutionEvidence; reason: string }
  | { outcome: "terminal_failed"; reason: string; statusCode?: number };

export interface ProviderRequestRunResult {
  entry: ProviderRequestJournalEntry;
  replayed: boolean;
  executed: boolean;
}

interface ProviderRequestJournalSnapshot {
  schema_version: typeof PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION;
  entries: Record<string, ProviderRequestJournalEntry>;
}

export class ProviderRequestJournalError extends Error {
  constructor(
    public readonly code: "invalid_input" | "idempotency_conflict" | "attempts_exhausted" | "indeterminate" | "persistence_error",
    message: string,
  ) {
    super(message);
    this.name = "ProviderRequestJournalError";
  }
}

export class ProviderJournalError extends ProviderRequestJournalError {}
export class ProviderJournalConflict extends ProviderJournalError {}
export class ProviderJournalStateError extends ProviderJournalError {}

export class ProviderRequestJournal {
  private readonly entries = new Map<string, ProviderRequestJournalEntry>();
  private readonly identityClaims = new Map<string, Promise<ProviderRequestRunResult>>();
  private writeChain: Promise<void> = Promise.resolve();

  private constructor(
    readonly path: string,
    private readonly clock: () => Date,
  ) {}

  static async open(path: string, options: { clock?: () => Date } = {}): Promise<ProviderRequestJournal> {
    const journal = new ProviderRequestJournal(resolve(path), options.clock ?? (() => new Date()));
    await journal.load();
    return journal;
  }

  list(scope?: ProviderRequestScope): ProviderRequestJournalEntry[] {
    return [...this.entries.values()]
      .filter((entry) => scope === undefined || entry.scope_fingerprint === scopeFingerprint(assertScope(scope)))
      .map(cloneEntry)
      .sort((left, right) => left.created_at.localeCompare(right.created_at) || left.entry_id.localeCompare(right.entry_id));
  }

  get(journalKey: string): ProviderRequestJournalEntry | null {
    const entry = this.entries.get(journalKey);
    return entry === undefined ? null : cloneEntry(entry);
  }

  async reconcile(journalKey: string, decision: ProviderRequestReconcileDecision): Promise<ProviderRequestJournalEntry> {
    const entry = this.entries.get(requiredString(journalKey, "journalKey"));
    if (entry === undefined) {
      throw new ProviderRequestJournalError("invalid_input", "provider request journal entry does not exist");
    }
    if (entry.state !== "indeterminate") {
      throw new ProviderRequestJournalError("invalid_input", "only an indeterminate provider request can be reconciled");
    }
    const reason = requiredString(decision.reason, "reconcile.reason");
    entry.updated_at = this.clock().toISOString();
    entry.lease_owner_fingerprint = null;
    entry.lease_expires_at = null;
    entry.next_retry_at = null;
    if (decision.outcome === "retry" || decision.outcome === "reserved") {
      if (entry.stream_observed) {
        throw new ProviderRequestJournalError("indeterminate", "stream-observed provider requests cannot reconcile to reserved or retry");
      }
      if (entry.attempt_count >= entry.max_attempts) {
        throw new ProviderRequestJournalError("attempts_exhausted", "provider request has no retry attempts remaining");
      }
      entry.state = decision.outcome === "reserved" ? "reserved" : "retry_wait";
      entry.error_evidence = reconciliationEvidence("reconcile_retry", reason, true, null);
    } else if (decision.outcome === "succeeded") {
      entry.state = "succeeded";
      entry.usage_evidence = normalizeUsage(decision.evidence.usage);
      entry.completion_evidence = normalizeCompletionEvidence(decision.evidence);
      entry.error_evidence = reconciliationEvidence("reconcile_succeeded", reason, false, null);
    } else {
      entry.state = "failed_terminal";
      entry.error_evidence = reconciliationEvidence("reconcile_terminal_failed", reason, false, decision.statusCode ?? null);
    }
    await this.persist();
    return cloneEntry(entry);
  }

  async run(options: ProviderRequestRunOptions): Promise<ProviderRequestRunResult> {
    const scope = assertScope(options.scope);
    const idempotencyKey = requiredString(options.idempotencyKey, "idempotencyKey");
    const identityKey = sha256(`claim\0${scopeFingerprint(scope)}\0${idempotencyKey}`);
    const active = this.identityClaims.get(identityKey);
    if (active !== undefined) {
      const result = await active;
      return { entry: cloneEntry(result.entry), replayed: true, executed: false };
    }
    const claim = this.runClaimed(options, scope, idempotencyKey);
    this.identityClaims.set(identityKey, claim);
    try {
      return await claim;
    } finally {
      if (this.identityClaims.get(identityKey) === claim) {
        this.identityClaims.delete(identityKey);
      }
    }
  }

  private async runClaimed(
    options: ProviderRequestRunOptions,
    scope: ProviderRequestScope,
    idempotencyKey: string,
  ): Promise<ProviderRequestRunResult> {
    const maxAttempts = positiveInteger(options.maxAttempts ?? 3, "maxAttempts");
    const leaseOwner = options.leaseOwner ?? `process:${process.pid}:${randomUUID()}`;
    const leaseDurationMs = positiveInteger(options.leaseDurationMs ?? 60_000, "leaseDurationMs");
    const modalityEvidence = requestModalityEvidence(options.messages);
    const requestFingerprint = providerRequestFingerprint(scope, options.messages);
    const scopedFingerprint = scopeFingerprint(scope);
    const journalKey = sha256(`journal\0${scopedFingerprint}\0${idempotencyKey}`);
    let entry = this.entries.get(journalKey);

    if (entry !== undefined) {
      if (entry.request_fingerprint !== requestFingerprint) {
        throw new ProviderRequestJournalError("idempotency_conflict", "idempotency key is already bound to a different scoped provider request");
      }
      if (entry.state === "succeeded") {
        return { entry: cloneEntry(entry), replayed: true, executed: false };
      }
      if (entry.state === "in_flight" && isExpired(entry.lease_expires_at, this.clock())) {
        markIndeterminate(entry, this.clock(), "stale_claim", "provider request lease expired before durable completion");
        await this.persist();
      }
      if (entry.state === "in_flight" || entry.state === "indeterminate") {
        throw new ProviderRequestJournalError("indeterminate", "provider request outcome requires explicit reconciliation");
      }
      if (entry.state === "failed_terminal" || entry.attempt_count >= entry.max_attempts) {
        throw new ProviderRequestJournalError("attempts_exhausted", "provider request has no retry attempts remaining");
      }
    } else {
      const now = this.clock().toISOString();
      entry = {
        schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
        entry_id: journalKey,
        scope_fingerprint: scopedFingerprint,
        request_fingerprint: requestFingerprint,
        idempotency_fingerprint: sha256(idempotencyKey),
        request_evidence: summarizeRequestEvidence(modalityEvidence),
        state: "reserved",
        attempt_count: 0,
        max_attempts: maxAttempts,
        created_at: now,
        updated_at: now,
        next_retry_at: null,
        lease_owner_fingerprint: null,
        lease_expires_at: null,
        fencing_token: 0,
        stream_observed: false,
        stream_snapshot: null,
        part_evidence: modalityEvidence,
        usage_evidence: null,
        completion_evidence: null,
        error_evidence: null,
        recovery_count: 0,
        persistence_capabilities: persistenceCapabilities(),
      };
      this.entries.set(journalKey, entry);
      await this.persist();
    }

    while (entry.attempt_count < entry.max_attempts) {
      entry.state = "in_flight";
      entry.attempt_count += 1;
      entry.fencing_token += 1;
      entry.lease_owner_fingerprint = sha256(requiredString(leaseOwner, "leaseOwner"));
      entry.lease_expires_at = new Date(this.clock().getTime() + leaseDurationMs).toISOString();
      entry.stream_observed = false;
      entry.stream_snapshot = null;
      entry.updated_at = this.clock().toISOString();
      entry.next_retry_at = null;
      entry.error_evidence = null;
      await this.persist();
      const executionFencingToken = entry.fencing_token;
      try {
        const evidence = await options.execute({
          attempt: entry.attempt_count,
          requestFingerprint,
          journalKey,
          fencingToken: entry.fencing_token,
          markStreamObserved: async (snapshot) => {
            const current = this.entries.get(journalKey);
            if (current !== entry || current.state !== "in_flight") {
              throw new ProviderRequestJournalError("indeterminate", "provider request lease is no longer active");
            }
            const validated = new ProviderStreamLedger(snapshot, {
              entry_id: entry.entry_id,
              fencing_token: entry.fencing_token,
            }).snapshot();
            if (validated.frame_count <= 0) {
              throw new ProviderRequestJournalError("invalid_input", "stream snapshot must contain at least one frame");
            }
            entry.stream_observed = true;
            entry.stream_snapshot = validated;
            entry.updated_at = this.clock().toISOString();
            await this.persist();
          },
        });
        if (isExpired(entry.lease_expires_at, this.clock())) {
          markIndeterminate(entry, this.clock(), "stale_claim", "provider request lease expired before durable completion");
          await this.persist();
          throw new ProviderRequestJournalError("indeterminate", "provider request completion arrived after its lease expired");
        }
        if (entry.state !== "in_flight" || entry.fencing_token !== executionFencingToken) {
          throw new ProviderRequestJournalError("indeterminate", "stale provider request completion was rejected by fencing");
        }
        if (entry.stream_observed) {
          const snapshot = (entry as ProviderRequestJournalEntry).stream_snapshot;
          if (
            snapshot === null
            || snapshot.entry_id !== entry.entry_id
            || snapshot.fencing_token !== executionFencingToken
            || snapshot.terminal_observed !== true
          ) {
            throw new ProviderRequestJournalError(
              "indeterminate",
              "streamed success requires a terminal snapshot under the active fence",
            );
          }
        }
        entry.state = "succeeded";
        entry.usage_evidence = normalizeUsage(evidence.usage);
        entry.completion_evidence = normalizeCompletionEvidence(evidence);
        entry.updated_at = this.clock().toISOString();
        entry.lease_owner_fingerprint = null;
        entry.lease_expires_at = null;
        await this.persist();
        return { entry: cloneEntry(entry), replayed: false, executed: true };
      } catch (error) {
        if (entry.state !== "in_flight" || entry.fencing_token !== executionFencingToken) {
          throw new ProviderRequestJournalError("indeterminate", "stale provider request execution lost its lease");
        }
        if (entry.stream_observed) {
          markIndeterminate(entry, this.clock(), "stream_observed", "provider stream was observed before completion failed");
          await this.persist();
          throw new ProviderRequestJournalError("indeterminate", "stream-observed provider request outcome requires explicit reconciliation");
        }
        const retryable = (options.shouldRetry ?? defaultShouldRetry)(error, entry.attempt_count);
        entry.error_evidence = normalizeErrorEvidence(error, retryable);
        entry.state = retryable && entry.attempt_count < entry.max_attempts ? "retry_wait" : "failed_terminal";
        entry.updated_at = this.clock().toISOString();
        entry.lease_owner_fingerprint = null;
        entry.lease_expires_at = null;
        const delayMs = retryable ? retryDelay(options.retryDelayMs, entry.attempt_count) : 0;
        entry.next_retry_at = delayMs > 0 ? new Date(this.clock().getTime() + delayMs).toISOString() : null;
        await this.persist();
        if (entry.state === "failed_terminal") {
          throw error;
        }
        if (delayMs > 0) {
          await new Promise((resolveDelay) => setTimeout(resolveDelay, delayMs));
        }
      }
    }
    throw new ProviderRequestJournalError("attempts_exhausted", "provider request has no retry attempts remaining");
  }

  private async load(): Promise<void> {
    let parsed: unknown;
    try {
      parsed = JSON.parse(await readFile(this.path, "utf8")) as unknown;
    } catch (error) {
      if (isNodeError(error) && error.code === "ENOENT") {
        return;
      }
      throw new ProviderRequestJournalError("persistence_error", "provider request journal could not be loaded");
    }
    if (!isRecord(parsed) || parsed.schema_version !== PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION || !isRecord(parsed.entries)) {
      throw new ProviderRequestJournalError("persistence_error", "provider request journal has an unsupported or malformed snapshot");
    }
    let recovered = false;
    for (const [key, value] of Object.entries(parsed.entries)) {
      const entry = validatePersistedEntry(value);
      if (entry.entry_id !== key) {
        throw new ProviderRequestJournalError("persistence_error", "provider request journal key binding is invalid");
      }
      if (entry.state === "in_flight") {
        markIndeterminate(entry, this.clock(), "restart_recovery", "provider request interrupted before durable completion");
        recovered = true;
      }
      this.entries.set(key, entry);
    }
    if (recovered) {
      await this.persist();
    }
  }

  private async persist(): Promise<void> {
    const snapshot: ProviderRequestJournalSnapshot = {
      schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
      entries: Object.fromEntries([...this.entries.entries()].map(([key, value]) => [key, cloneEntry(value)])),
    };
    this.writeChain = this.writeChain.catch(() => undefined).then(async () => {
      try {
        await mkdir(dirname(this.path), { recursive: true });
        const temporaryPath = `${this.path}.${process.pid}.${randomUUID()}.tmp`;
        await writeFile(temporaryPath, `${JSON.stringify(snapshot, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
        await rename(temporaryPath, this.path);
      } catch {
        throw new ProviderRequestJournalError("persistence_error", "provider request journal could not be persisted");
      }
    });
    return this.writeChain;
  }
}

export function providerRequestFingerprint(scopeValue: ProviderRequestScope, messages: ProviderRequestMessage[]): string {
  const scope = assertScope(scopeValue);
  const messageEvidence = messages.map((message) => ({
    role: requiredString(message.role, "message.role"),
    parts: requestParts(message).map(partEvidence),
  }));
  return sha256(canonicalJson({
    scope: {
      tenant_id: scope.tenantId,
      project_id: scope.projectId,
      provider: scope.provider,
      model: scope.model,
      operation: scope.operation ?? "model.complete",
    },
    messages: messageEvidence,
  }));
}

export function requestModalityEvidence(messages: ProviderRequestMessage[]): ProviderModalityEvidence[] {
  return messages.flatMap((message) => requestParts(message).map(partEvidence));
}

function requestParts(message: ProviderRequestMessage): ProviderRequestPart[] {
  const content = message.parts ?? message.content;
  if (typeof content === "string") {
    return [{ type: "text", text: content }];
  }
  if (!Array.isArray(content)) {
    throw new ProviderRequestJournalError("invalid_input", "provider request messages require string content or typed parts");
  }
  return content.map(validatePart);
}

function validatePart(value: ProviderRequestPart): ProviderRequestPart {
  if (!isRecord(value) || !PROVIDER_REQUEST_MODALITIES.includes(value.type as ProviderRequestModality)) {
    throw new ProviderRequestJournalError("invalid_input", "provider request part has an unsupported modality");
  }
  return value as ProviderRequestPart;
}

function partEvidence(part: ProviderRequestPart): ProviderModalityEvidence {
  const content = partContent(part);
  const mediaType = optionalString(part.media_type ?? part.mime_type);
  const filename = optionalString(part.filename ?? part.name);
  return {
    type: part.type,
    media_type: mediaType,
    filename_sha256: filename === null ? null : sha256(filename),
    content_sha256: sha256Bytes(content),
    byte_length: content.byteLength,
  };
}

function partContent(part: ProviderRequestPart): Uint8Array {
  if (part.type === "text") {
    return Buffer.from(requiredString(part.text, "text part text"), "utf8");
  }
  if (part.data instanceof Uint8Array) {
    return part.data;
  }
  if (typeof part.data === "string") {
    return Buffer.from(part.data, "utf8");
  }
  const reference = part.url ?? part.path;
  if (typeof reference === "string" && reference.length > 0) {
    return Buffer.from(reference, "utf8");
  }
  throw new ProviderRequestJournalError("invalid_input", `${part.type} part requires data, url, or path`);
}

function normalizeUsage(value: Partial<ProviderRequestUsage> | undefined): ProviderRequestUsage {
  const input = nonNegativeInteger(value?.input_tokens ?? 0);
  const output = nonNegativeInteger(value?.output_tokens ?? 0);
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: nonNegativeInteger(value?.total_tokens ?? input + output),
    ...(value?.cached_input_tokens === undefined ? {} : { cached_input_tokens: nonNegativeInteger(value.cached_input_tokens) }),
    ...(value?.reasoning_tokens === undefined ? {} : { reasoning_tokens: nonNegativeInteger(value.reasoning_tokens) }),
  };
}

function normalizeCompletionEvidence(value: ProviderRequestExecutionEvidence): ProviderCompletionEvidence {
  const calls = value.toolCalls ?? [];
  return {
    finish_reason: safeLabel(value.finishReason ?? "unknown", "finishReason"),
    tool_call_count: calls.length,
    tool_call_evidence: calls.map((call) => ({
      id_sha256: call.id === undefined ? null : sha256(call.id),
      name: safeLabel(call.name ?? "unknown", "tool call name"),
      arguments_sha256: sha256(canonicalJson(call.arguments ?? null)),
    })),
    response_fingerprint: value.responseFingerprint === undefined ? null : safeDigest(value.responseFingerprint),
    provider_request_id_sha256: value.providerRequestId === undefined ? null : sha256(value.providerRequestId),
    metadata: safeMetadata(value.metadata ?? {}),
  };
}

function normalizeErrorEvidence(error: unknown, retryable: boolean): ProviderErrorEvidence {
  const record = isRecord(error) ? error : {};
  const kind = safeLabel(String(record.kind ?? record.name ?? (error instanceof Error ? error.name : "provider_error")), "error kind");
  const message = error instanceof Error ? error.message : String(record.message ?? "provider request failed");
  const statusCode = typeof record.statusCode === "number" ? record.statusCode : typeof record.status_code === "number" ? record.status_code : null;
  return { kind, message_sha256: sha256(message), retryable, status_code: statusCode };
}

function reconciliationEvidence(kind: string, reason: string, retryable: boolean, statusCode: number | null): ProviderErrorEvidence {
  return {
    kind,
    message_sha256: sha256(reason),
    retryable,
    status_code: statusCode,
  };
}

function markIndeterminate(entry: ProviderRequestJournalEntry, now: Date, kind: string, reason: string): void {
  entry.state = "indeterminate";
  entry.recovery_count += 1;
  entry.updated_at = now.toISOString();
  entry.next_retry_at = null;
  entry.lease_owner_fingerprint = null;
  entry.lease_expires_at = null;
  entry.error_evidence = reconciliationEvidence(kind, reason, false, null);
}

function isExpired(expiresAt: string | null, now: Date): boolean {
  if (expiresAt === null) {
    return true;
  }
  const expires = Date.parse(expiresAt);
  return !Number.isFinite(expires) || expires <= now.getTime();
}

function defaultShouldRetry(error: unknown): boolean {
  if (isRecord(error) && typeof error.retryable === "boolean") {
    return error.retryable;
  }
  const status = isRecord(error) ? error.statusCode ?? error.status_code : undefined;
  return typeof status === "number" ? [408, 409, 425, 429, 500, 502, 503, 504].includes(status) : true;
}

function safeMetadata(value: ProviderJson): ProviderJson {
  const output: ProviderJson = {};
  for (const [key, item] of Object.entries(value)) {
    const lower = key.toLowerCase();
    if (["prompt", "content", "endpoint", "url", "path"].includes(lower) || ["secret", "token", "authorization", "api_key", "apikey", "password", "credential"].some((term) => lower.includes(term))) {
      continue;
    }
    if (typeof item === "string" && item.length <= 128 && /^[A-Za-z0-9_.:/ -]*$/.test(item)) {
      output[key] = item;
    } else if (typeof item === "number" || typeof item === "boolean" || item === null) {
      output[key] = item;
    }
  }
  return output;
}

function validatePersistedEntry(value: unknown): ProviderRequestJournalEntry {
  if (!isRecord(value) || value.schema_version !== PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION) {
    throw new ProviderRequestJournalError("persistence_error", "provider request journal entry is malformed");
  }
  const expectedKeys = [
    "attempt_count", "completion_evidence", "created_at", "entry_id", "error_evidence",
    "fencing_token", "idempotency_fingerprint", "lease_expires_at", "lease_owner_fingerprint",
    "max_attempts", "next_retry_at", "part_evidence", "persistence_capabilities",
    "recovery_count", "request_evidence", "request_fingerprint", "schema_version",
    "scope_fingerprint", "state", "stream_observed", "stream_snapshot", "updated_at", "usage_evidence",
  ];
  if (Object.keys(value).sort().join(",") !== expectedKeys.sort().join(",")) {
    throw new ProviderRequestJournalError("persistence_error", "provider request journal entry fields are not canonical TypeScript journal format");
  }
  const state = value.state;
  if (!PROVIDER_JOURNAL_STATES.includes(state as ProviderRequestState)) {
    throw new ProviderRequestJournalError("persistence_error", "provider request journal entry state is invalid");
  }
  const entry = structuredClone(value) as unknown as ProviderRequestJournalEntry;
  if (
    !isSha256(entry.entry_id)
    || !isSha256(entry.scope_fingerprint)
    || !isSha256(entry.request_fingerprint)
    || !isSha256(entry.idempotency_fingerprint)
    || !isNonNegativeSafeInteger(entry.attempt_count)
    || !isPositiveSafeInteger(entry.max_attempts)
    || entry.attempt_count > entry.max_attempts
    || !isNonNegativeSafeInteger(entry.fencing_token)
    || entry.fencing_token < entry.attempt_count
    || !isNonNegativeSafeInteger(entry.recovery_count)
    || typeof entry.stream_observed !== "boolean"
    || !isTimestamp(entry.created_at)
    || !isTimestamp(entry.updated_at)
    || !isNullableTimestamp(entry.next_retry_at)
    || !isNullableTimestamp(entry.lease_expires_at)
    || !(entry.lease_owner_fingerprint === null || isSha256(entry.lease_owner_fingerprint))
    || !validateRequestEvidence(entry.request_evidence)
    || !Array.isArray(entry.part_evidence)
    || !entry.part_evidence.every(validatePartEvidence)
    || !validatePersistenceCapabilities(entry.persistence_capabilities)
    || !validateUsageEvidence(entry.usage_evidence)
    || !validateCompletionEvidence(entry.completion_evidence)
    || !validateErrorEvidence(entry.error_evidence)
    || !validateStreamSnapshot(entry)
  ) {
    throw new ProviderRequestJournalError("persistence_error", "provider request journal entry is not canonical TypeScript journal format");
  }
  const active = entry.state === "in_flight";
  if (
    active !== (entry.lease_owner_fingerprint !== null)
    || active !== (entry.lease_expires_at !== null)
    || (active && entry.attempt_count === 0)
    || (entry.state === "reserved" && entry.attempt_count !== 0)
    || (entry.state === "retry_wait" && (entry.attempt_count === 0 || entry.error_evidence === null))
    || (entry.state === "succeeded" && entry.completion_evidence === null)
    || (entry.state === "failed_terminal" && entry.error_evidence === null)
    || (entry.state === "indeterminate" && entry.error_evidence === null)
  ) {
    throw new ProviderRequestJournalError("persistence_error", "provider request journal entry state invariants are invalid");
  }
  return entry;
}

function validateStreamSnapshot(entry: ProviderRequestJournalEntry): boolean {
  if (entry.stream_snapshot === null) return entry.stream_observed === false;
  if (!entry.stream_observed) return false;
  try {
    return new ProviderStreamLedger(entry.stream_snapshot, {
      entry_id: entry.entry_id,
      fencing_token: entry.fencing_token,
    }).snapshot().frame_count > 0;
  } catch {
    return false;
  }
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function isPositiveSafeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) > 0;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isNullableTimestamp(value: unknown): value is string | null {
  return value === null || isTimestamp(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).sort().join(",") === [...keys].sort().join(",");
}

function validateRequestEvidence(value: unknown): value is ProviderRequestEvidence {
  if (!isRecord(value) || !hasExactKeys(value, [
    "modality_counts", "modalities_present", "raw_credential_persisted",
    "raw_media_persisted", "raw_prompt_persisted", "raw_url_persisted",
  ]) || !isRecord(value.modality_counts) || !Array.isArray(value.modalities_present)) return false;
  if (
    value.raw_prompt_persisted !== false || value.raw_media_persisted !== false
    || value.raw_url_persisted !== false || value.raw_credential_persisted !== false
  ) return false;
  const counts = value.modality_counts as Record<string, unknown>;
  const present = value.modalities_present as unknown[];
  if (!hasExactKeys(counts, [...PROVIDER_REQUEST_MODALITIES])) return false;
  return PROVIDER_REQUEST_MODALITIES.every((type) => isNonNegativeSafeInteger(counts[type]))
    && present.every((type) => PROVIDER_REQUEST_MODALITIES.includes(type as ProviderRequestModality))
    && new Set(present).size === present.length
    && PROVIDER_REQUEST_MODALITIES.every(
      (type) => present.includes(type) === ((counts[type] as number) > 0),
    );
}

function validatePartEvidence(value: unknown): value is ProviderModalityEvidence {
  return isRecord(value)
    && hasExactKeys(value, ["byte_length", "content_sha256", "filename_sha256", "media_type", "type"])
    && PROVIDER_REQUEST_MODALITIES.includes(value.type as ProviderRequestModality)
    && (value.media_type === null || typeof value.media_type === "string")
    && (value.filename_sha256 === null || isSha256(value.filename_sha256))
    && isSha256(value.content_sha256)
    && isNonNegativeSafeInteger(value.byte_length);
}

function validatePersistenceCapabilities(value: unknown): value is ProviderJournalPersistenceCapabilities {
  return isRecord(value)
    && hasExactKeys(value, [
      "atomic_replace", "crash_recovery", "cross_process_lock", "multi_host_safe",
      "multi_process_safe", "power_loss_durability_proven", "restart_persistent",
      "same_process_identity_claim", "storage_kind",
    ])
    && value.storage_kind === "local_json_file" && value.restart_persistent === true
    && value.atomic_replace === true && value.same_process_identity_claim === true
    && value.cross_process_lock === false && value.multi_process_safe === false
    && value.multi_host_safe === false && value.power_loss_durability_proven === false
    && value.crash_recovery === "in_flight_to_indeterminate";
}

function validateUsageEvidence(value: unknown): value is ProviderRequestUsage | null {
  if (value === null) return true;
  if (!isRecord(value)) return false;
  const allowed = new Set(["input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_tokens"]);
  return Object.keys(value).every((key) => allowed.has(key))
    && ["input_tokens", "output_tokens", "total_tokens"].every((key) => isNonNegativeSafeInteger(value[key]))
    && (value.cached_input_tokens === undefined || isNonNegativeSafeInteger(value.cached_input_tokens))
    && (value.reasoning_tokens === undefined || isNonNegativeSafeInteger(value.reasoning_tokens));
}

function validateCompletionEvidence(value: unknown): value is ProviderCompletionEvidence | null {
  if (value === null) return true;
  return isRecord(value)
    && hasExactKeys(value, [
      "finish_reason", "metadata", "provider_request_id_sha256", "response_fingerprint",
      "tool_call_count", "tool_call_evidence",
    ])
    && typeof value.finish_reason === "string"
    && isNonNegativeSafeInteger(value.tool_call_count)
    && Array.isArray(value.tool_call_evidence)
    && value.tool_call_count === value.tool_call_evidence.length
    && value.tool_call_evidence.every((item) => isRecord(item)
      && hasExactKeys(item, ["arguments_sha256", "id_sha256", "name"])
      && (item.id_sha256 === null || isSha256(item.id_sha256))
      && typeof item.name === "string" && isSha256(item.arguments_sha256))
    && (value.response_fingerprint === null || isSha256(value.response_fingerprint))
    && (value.provider_request_id_sha256 === null || isSha256(value.provider_request_id_sha256))
    && isRecord(value.metadata);
}

function validateErrorEvidence(value: unknown): value is ProviderErrorEvidence | null {
  return value === null || (
    isRecord(value)
    && hasExactKeys(value, ["kind", "message_sha256", "retryable", "status_code"])
    && typeof value.kind === "string" && isSha256(value.message_sha256)
    && typeof value.retryable === "boolean"
    && (value.status_code === null || isNonNegativeSafeInteger(value.status_code))
  );
}

function summarizeRequestEvidence(parts: ProviderModalityEvidence[]): ProviderRequestEvidence {
  const modalityCounts = Object.fromEntries(
    PROVIDER_REQUEST_MODALITIES.map((modality) => [
      modality,
      parts.filter((part) => part.type === modality).length,
    ]),
  ) as Record<ProviderRequestModality, number>;
  return {
    modality_counts: modalityCounts,
    modalities_present: PROVIDER_REQUEST_MODALITIES.filter((modality) => modalityCounts[modality] > 0),
    raw_prompt_persisted: false,
    raw_media_persisted: false,
    raw_url_persisted: false,
    raw_credential_persisted: false,
  };
}

function persistenceCapabilities(): ProviderJournalPersistenceCapabilities {
  return {
    storage_kind: "local_json_file",
    restart_persistent: true,
    atomic_replace: true,
    same_process_identity_claim: true,
    cross_process_lock: false,
    multi_process_safe: false,
    multi_host_safe: false,
    power_loss_durability_proven: false,
    crash_recovery: "in_flight_to_indeterminate",
  };
}

function assertScope(value: ProviderRequestScope): ProviderRequestScope {
  return {
    tenantId: requiredString(value.tenantId, "scope.tenantId"),
    projectId: requiredString(value.projectId, "scope.projectId"),
    provider: safeLabel(value.provider, "scope.provider"),
    model: safeLabel(value.model, "scope.model"),
    operation: safeLabel(value.operation ?? "model.complete", "scope.operation"),
  };
}

function scopeFingerprint(scope: ProviderRequestScope): string {
  return sha256(canonicalJson({
    tenant_id: scope.tenantId,
    project_id: scope.projectId,
    provider: scope.provider,
    model: scope.model,
    operation: scope.operation ?? "model.complete",
  }));
}

function retryDelay(value: ProviderRequestRunOptions["retryDelayMs"], attempt: number): number {
  const delay = typeof value === "function" ? value(attempt) : value ?? 0;
  return nonNegativeInteger(delay);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new ProviderRequestJournalError("invalid_input", `${field} must be a non-empty string`);
  }
  return value;
}

function safeLabel(value: unknown, field: string): string {
  const label = requiredString(value, field);
  if (label.length > 128 || !/^[A-Za-z0-9_.:/ -]+$/.test(label)) {
    throw new ProviderRequestJournalError("invalid_input", `${field} contains unsafe characters`);
  }
  return label;
}

function safeDigest(value: string): string {
  return /^[a-f0-9]{64}$/i.test(value) || /^sha256:[a-f0-9]{64}$/i.test(value) ? value.toLowerCase() : sha256(value);
}

function positiveInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ProviderRequestJournalError("invalid_input", `${field} must be a positive integer`);
  }
  return value;
}

function nonNegativeInteger(value: number): number {
  if (!Number.isFinite(value) || value < 0) {
    throw new ProviderRequestJournalError("invalid_input", "usage and retry values must be non-negative");
  }
  return Math.trunc(value);
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortValue);
  }
  if (isRecord(value)) {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortValue(value[key])]));
  }
  return value;
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256Bytes(value: Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function cloneEntry(value: ProviderRequestJournalEntry): ProviderRequestJournalEntry {
  const clone = structuredClone(value);
  Object.defineProperties(clone, {
    journal_key: { value: clone.entry_id, enumerable: false },
    attempts: { value: clone.attempt_count, enumerable: false },
    lease_owner_sha256: { value: clone.lease_owner_fingerprint, enumerable: false },
    modality_evidence: { value: structuredClone(clone.part_evidence), enumerable: false },
  });
  return clone;
}

function isRecord(value: unknown): value is ProviderJson {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNodeError(value: unknown): value is NodeJS.ErrnoException {
  return value instanceof Error && "code" in value;
}
