export const PROVIDER_DISPATCH_SCHEMA_VERSION = "ashr.clone.control_plane.v1" as const;
export const PROVIDER_DISPATCH_CLIENT_VERSION = "ashr.clone.provider_dispatch.v1" as const;
export const PROVIDER_DISPATCH_STATUSES = [
  "pending",
  "claimed",
  "indeterminate",
  "reconciling",
  "completed",
  "failed",
  "cancelled",
] as const;
export const PROVIDER_DISPATCH_STATES = PROVIDER_DISPATCH_STATUSES;
export const PROVIDER_DISPATCH_TERMINAL_STATES = [
  "completed",
  "failed",
  "cancelled",
] as const;
export const PROVIDER_DISPATCH_RECONCILIATION_OUTCOMES =
  PROVIDER_DISPATCH_TERMINAL_STATES;
export const PROVIDER_DISPATCH_ERROR_CODES = [
  "provider_dispatch_conflict",
  "provider_dispatch_fence",
  "provider_dispatch_not_found",
  "provider_dispatch_cancelled",
  "provider_dispatch_deadline",
  "provider_dispatch_contention",
  "provider_dispatch_unavailable",
  "provider_dispatch_indeterminate",
  "provider_dispatch_validation",
  "provider_dispatch_transport",
] as const;
export const PROVIDER_DISPATCH_CAPABILITIES = Object.freeze({
  authoritative_store: "postgresql",
  transactional_claim: true,
  skip_locked_claim: true,
  lease_heartbeat: true,
  monotonic_fencing_token: true,
  request_fingerprint_conflict_detection: true,
  terminal_stream_proof_binding: true,
  indeterminate_reconciliation: true,
  tenant_project_isolation: true,
  raw_request_persisted: false,
  raw_response_persisted: false,
  credentials_persisted: false,
});

export type ProviderDispatchStatus = (typeof PROVIDER_DISPATCH_STATUSES)[number];
export type ProviderDispatchState = ProviderDispatchStatus;
export type ProviderDispatchJson =
  | null
  | boolean
  | number
  | string
  | ProviderDispatchJson[]
  | { [key: string]: ProviderDispatchJson };
export type ProviderDispatchRecord = { [key: string]: ProviderDispatchJson };

export interface ProviderDispatchScope {
  tenantId: string;
  projectId: string;
}

export interface ProviderDispatchSubmit {
  provider: string;
  operation: string;
  request: ProviderDispatchRecord;
  dispatchId?: string;
}

export type ProviderDispatchReservation = ProviderDispatchSubmit;
export type ProviderDispatchTransport = typeof globalThis.fetch;

export interface ProviderDispatch {
  schema_version: string;
  tenant_id: string;
  project_id: string;
  dispatch_id: string;
  provider: string;
  operation: string;
  request_fingerprint: string;
  status: ProviderDispatchStatus;
  attempts: number;
  fencing_token: number;
  lease_owner_id?: string;
  lease_expires_at?: string;
  provider_request_id?: string;
  stream_observed: boolean;
  stream_observed_sha256?: string;
  stream_observed_fencing_token?: number;
  stream_observed_at?: string;
  terminal_proof_sha256?: string;
  terminal_response_sha256?: string;
  reconciliation_reason?: string;
  reconciliation_attempts: number;
  next_reconcile_at?: string;
  last_error_sha256?: string;
  created_at: string;
  updated_at: string;
  claimed_at?: string;
  completed_at?: string;
  failed_at?: string;
  raw_payload_included: boolean;
}

export type ProviderDispatchEntry = ProviderDispatch;

export interface ProviderDispatchClaim {
  schema_version: string;
  status: "claimed" | "reconciling" | "empty";
  claimed: boolean;
  dispatch?: ProviderDispatch;
}

export interface ProviderDispatchClientOptions {
  baseUrl: string;
  apiKey?: string;
  fetch?: typeof globalThis.fetch;
  headers?: Record<string, string>;
}

export interface ProviderDispatchRequestOptions {
  signal?: AbortSignal;
  requestId?: string;
}

export interface ProviderDispatchClaimOptions {
  leaseOwnerId: string;
  leaseSeconds?: number;
  provider?: string;
  operation?: string;
}

export interface ProviderDispatchLeaseOptions {
  leaseOwnerId: string;
  fencingToken: number;
}

export type ProviderDispatchErrorCode =
  | "invalid_input"
  | "authentication_failed"
  | "permission_denied"
  | "not_found"
  | "idempotency_conflict"
  | "state_conflict"
  | "lease_conflict"
  | "stale_fence"
  | "stream_proof_required"
  | "provider_dispatch_cancelled"
  | "provider_dispatch_deadline"
  | "provider_dispatch_contention"
  | "provider_dispatch_unavailable"
  | "provider_dispatch_indeterminate"
  | "rate_limited"
  | "unavailable"
  | "protocol_error";

export class ProviderDispatchError extends Error {
  constructor(
    public readonly code: ProviderDispatchErrorCode,
    message: string,
    public readonly status: number | null = null,
    public readonly requestId: string | null = null,
    public readonly retryable = false,
    public readonly details: ProviderDispatchRecord = {},
  ) {
    super(message);
    this.name = "ProviderDispatchError";
  }
}

export class ProviderDispatchConflict extends ProviderDispatchError {}

export class ProviderDispatchFenceRejected extends ProviderDispatchError {}

export class ProviderDispatchLeaseExpired extends ProviderDispatchFenceRejected {}

export class ProviderDispatchNotFound extends ProviderDispatchError {}

export class ProviderDispatchValidationError extends ProviderDispatchError {}

export class ProviderDispatchConflictError extends ProviderDispatchConflict {
  constructor(
    code: Extract<ProviderDispatchErrorCode, "idempotency_conflict" | "state_conflict">,
    message: string,
    status: number,
    requestId: string | null,
    details: ProviderDispatchRecord,
  ) {
    super(code, message, status, requestId, false, details);
    this.name = "ProviderDispatchConflictError";
  }
}

export class ProviderDispatchLeaseError extends ProviderDispatchFenceRejected {
  constructor(
    code: Extract<ProviderDispatchErrorCode, "lease_conflict" | "stale_fence">,
    message: string,
    status: number,
    requestId: string | null,
    details: ProviderDispatchRecord,
  ) {
    super(code, message, status, requestId, false, details);
    this.name = "ProviderDispatchLeaseError";
  }
}

export class ProviderDispatchProtocolError extends ProviderDispatchError {
  constructor(message: string, status: number | null = null, requestId: string | null = null) {
    super("protocol_error", message, status, requestId);
    this.name = "ProviderDispatchProtocolError";
  }
}

export function provider_dispatch_capability_manifest(): ProviderDispatchRecord {
  return {
    schema_version: PROVIDER_DISPATCH_CLIENT_VERSION,
    capabilities: { ...PROVIDER_DISPATCH_CAPABILITIES },
    states: [...PROVIDER_DISPATCH_STATES].sort(),
    error_codes: [...PROVIDER_DISPATCH_ERROR_CODES].sort(),
    public_safe: true,
    routes: [
      "submit",
      "claim",
      "heartbeat",
      "observe-stream",
      "complete",
      "indeterminate",
      "reconciliation/claim",
      "get",
    ],
  };
}

export class ProviderDispatchClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof globalThis.fetch;
  private readonly headers: Record<string, string>;

  constructor(options: ProviderDispatchClientOptions) {
    this.baseUrl = requiredUrl(options.baseUrl);
    this.fetcher = options.fetch ?? globalThis.fetch;
    if (typeof this.fetcher !== "function") {
      throw new ProviderDispatchError("invalid_input", "fetch implementation is required");
    }
    this.headers = { ...options.headers };
    if (options.apiKey !== undefined) {
      this.headers.authorization = `Bearer ${requiredString(options.apiKey, "apiKey")}`;
    }
  }

  submit(
    scope: ProviderDispatchScope,
    input: ProviderDispatchSubmit,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    const body: ProviderDispatchRecord = {
      provider: requiredString(input.provider, "input.provider"),
      operation: requiredString(input.operation, "input.operation"),
      request: jsonRecord(input.request, "input.request"),
    };
    if (input.dispatchId !== undefined) {
      body.dispatch_id = requiredString(input.dispatchId, "input.dispatchId");
    }
    return this.request("POST", this.collectionPath(scope), body, options, isDispatch);
  }

  claim(
    scope: ProviderDispatchScope,
    claim: ProviderDispatchClaimOptions,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatchClaim> {
    return this.claimAt(`${this.collectionPath(scope)}/claim`, claim, options);
  }

  claimReconciliation(
    scope: ProviderDispatchScope,
    claim: Pick<ProviderDispatchClaimOptions, "leaseOwnerId" | "leaseSeconds">,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatchClaim> {
    return this.claimAt(`${this.collectionPath(scope)}/reconciliation/claim`, claim, options);
  }

  heartbeat(
    scope: ProviderDispatchScope,
    dispatchId: string,
    lease: ProviderDispatchLeaseOptions,
    leaseSeconds: number,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    return this.fencedMutation(scope, dispatchId, "heartbeat", lease, {
      lease_seconds: positiveInteger(leaseSeconds, "leaseSeconds"),
    }, options);
  }

  observeStream(
    scope: ProviderDispatchScope,
    dispatchId: string,
    lease: ProviderDispatchLeaseOptions,
    stream: ProviderDispatchRecord,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    return this.fencedMutation(scope, dispatchId, "observe-stream", lease, {
      stream: jsonRecord(stream, "stream"),
    }, options);
  }

  complete(
    scope: ProviderDispatchScope,
    dispatchId: string,
    lease: ProviderDispatchLeaseOptions,
    proof: ProviderDispatchRecord,
    response: ProviderDispatchRecord,
    providerRequestId = "",
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    return this.fencedMutation(scope, dispatchId, "complete", lease, {
      proof: nonEmptyRecord(proof, "proof"),
      response: nonEmptyRecord(response, "response"),
      provider_request_id: optionalString(providerRequestId, "providerRequestId"),
    }, options);
  }

  markIndeterminate(
    scope: ProviderDispatchScope,
    dispatchId: string,
    lease: ProviderDispatchLeaseOptions,
    reason: string,
    failure: ProviderDispatchRecord,
    nextReconcileAt?: string,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    const body: ProviderDispatchRecord = {
      reason: requiredString(reason, "reason"),
      failure: jsonRecord(failure, "failure"),
    };
    if (nextReconcileAt !== undefined) {
      body.next_reconcile_at = requiredTimestamp(nextReconcileAt, "nextReconcileAt");
    }
    return this.fencedMutation(scope, dispatchId, "indeterminate", lease, body, options);
  }

  get(
    scope: ProviderDispatchScope,
    dispatchId: string,
    options: ProviderDispatchRequestOptions = {},
  ): Promise<ProviderDispatch> {
    return this.request("GET", this.entryPath(scope, dispatchId), undefined, options, isDispatch);
  }

  private claimAt(
    path: string,
    claim: Pick<ProviderDispatchClaimOptions, "leaseOwnerId" | "leaseSeconds" | "provider" | "operation">,
    options: ProviderDispatchRequestOptions,
  ): Promise<ProviderDispatchClaim> {
    const body: ProviderDispatchRecord = {
      lease_owner_id: requiredString(claim.leaseOwnerId, "claim.leaseOwnerId"),
      lease_seconds: positiveInteger(claim.leaseSeconds ?? 300, "claim.leaseSeconds"),
    };
    if (claim.provider !== undefined) body.provider = requiredString(claim.provider, "claim.provider");
    if (claim.operation !== undefined) body.operation = requiredString(claim.operation, "claim.operation");
    return this.request("POST", path, body, options, isClaim);
  }

  private fencedMutation(
    scope: ProviderDispatchScope,
    dispatchId: string,
    operation: string,
    lease: ProviderDispatchLeaseOptions,
    body: ProviderDispatchRecord,
    options: ProviderDispatchRequestOptions,
  ): Promise<ProviderDispatch> {
    return this.request("POST", `${this.entryPath(scope, dispatchId)}/${operation}`, {
      lease_owner_id: requiredString(lease.leaseOwnerId, "lease.leaseOwnerId"),
      fencing_token: positiveInteger(lease.fencingToken, "lease.fencingToken"),
      ...body,
    }, options, isDispatch);
  }

  private collectionPath(scope: ProviderDispatchScope): string {
    return `/v1/tenants/${segment(scope.tenantId, "scope.tenantId")}/projects/${segment(scope.projectId, "scope.projectId")}/provider-dispatches`;
  }

  private entryPath(scope: ProviderDispatchScope, dispatchId: string): string {
    return `${this.collectionPath(scope)}/${segment(dispatchId, "dispatchId")}`;
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    body: ProviderDispatchRecord | undefined,
    options: ProviderDispatchRequestOptions,
    validate: (value: unknown) => value is T,
  ): Promise<T> {
    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        method,
        headers: {
          accept: "application/json",
          ...(body === undefined ? {} : { "content-type": "application/json" }),
          ...this.headers,
          ...(options.requestId === undefined
            ? {}
            : { "x-request-id": requiredString(options.requestId, "options.requestId") }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: options.signal,
      });
    } catch (error) {
      if (error instanceof ProviderDispatchError) throw error;
      throw new ProviderDispatchError(
        options.signal?.aborted ? "provider_dispatch_cancelled" : "provider_dispatch_unavailable",
        options.signal?.aborted
          ? "provider dispatch request was cancelled"
          : "provider dispatch service is unavailable",
        null,
        null,
        !options.signal?.aborted,
      );
    }
    const requestId = response.headers.get("x-request-id");
    const payload = await parsePayload(response);
    if (!response.ok) throw mapError(response.status, requestId, payload);
    const result = unwrapResult(payload);
    if (!validate(result)) {
      throw new ProviderDispatchProtocolError(
        "provider dispatch response has an invalid shape",
        response.status,
        requestId,
      );
    }
    return result;
  }
}

async function parsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text === "") return {};
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ProviderDispatchProtocolError(
      "provider dispatch response is not valid JSON",
      response.status,
      response.headers.get("x-request-id"),
    );
  }
}

function unwrapResult(value: unknown): unknown {
  return isRecord(value) && "result" in value ? value.result : value;
}

function mapError(status: number, requestId: string | null, payload: unknown): ProviderDispatchError {
  const record = isRecord(payload) ? payload : {};
  const nested = isRecord(record.error) ? record.error : record;
  const rawCode = typeof nested.code === "string" ? nested.code : "";
  const message = typeof nested.message === "string" && nested.message.trim() !== ""
    ? nested.message
    : `provider dispatch request failed with HTTP ${status}`;
  const details = isRecord(nested.details) ? nested.details as ProviderDispatchRecord : {};
  const code = normalizeErrorCode(status, rawCode);
  if (code === "idempotency_conflict" || code === "state_conflict") {
    return new ProviderDispatchConflictError(code, message, status, requestId, details);
  }
  if (code === "lease_conflict" || code === "stale_fence") {
    return new ProviderDispatchLeaseError(code, message, status, requestId, details);
  }
  if (code === "not_found") {
    return new ProviderDispatchNotFound(code, message, status, requestId, false, details);
  }
  if (code === "invalid_input") {
    return new ProviderDispatchValidationError(code, message, status, requestId, false, details);
  }
  const retryable = code === "provider_dispatch_contention"
    || code === "provider_dispatch_unavailable"
    || code === "provider_dispatch_indeterminate"
    || code === "rate_limited"
    || code === "unavailable";
  return new ProviderDispatchError(code, message, status, requestId, retryable, details);
}

function normalizeErrorCode(status: number, rawCode: string): ProviderDispatchErrorCode {
  const aliases: Record<string, ProviderDispatchErrorCode> = {
    fingerprint_conflict: "idempotency_conflict",
    provider_dispatch_conflict: "idempotency_conflict",
    provider_dispatch_fence: "stale_fence",
    stale_fencing_token: "stale_fence",
    lease_owner_mismatch: "lease_conflict",
    terminal_stream_proof_required: "stream_proof_required",
  };
  const known = aliases[rawCode] ?? rawCode;
  if ([
    "invalid_input", "authentication_failed", "permission_denied", "not_found",
    "idempotency_conflict", "state_conflict", "lease_conflict", "stale_fence",
    "stream_proof_required", "provider_dispatch_cancelled", "provider_dispatch_deadline",
    "provider_dispatch_contention", "provider_dispatch_unavailable",
    "provider_dispatch_indeterminate", "rate_limited", "unavailable", "protocol_error",
  ].includes(known)) return known as ProviderDispatchErrorCode;
  if (status === 400 || status === 422) return "invalid_input";
  if (status === 401) return "authentication_failed";
  if (status === 403) return "permission_denied";
  if (status === 404) return "not_found";
  if (status === 409) return "state_conflict";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "provider_dispatch_unavailable";
  return "protocol_error";
}

function isClaim(value: unknown): value is ProviderDispatchClaim {
  if (!isRecord(value)
    || typeof value.schema_version !== "string"
    || !["claimed", "reconciling", "empty"].includes(String(value.status))
    || typeof value.claimed !== "boolean") return false;
  if (!value.claimed) return value.status === "empty" && value.dispatch === undefined;
  return value.dispatch !== undefined
    && isDispatch(value.dispatch)
    && value.dispatch.status === value.status;
}

function isDispatch(value: unknown): value is ProviderDispatch {
  if (!isRecord(value)) return false;
  const requiredStrings = [
    "schema_version", "tenant_id", "project_id", "dispatch_id", "provider", "operation",
    "request_fingerprint", "status", "created_at", "updated_at",
  ];
  return requiredStrings.every((key) => typeof value[key] === "string")
    && PROVIDER_DISPATCH_STATUSES.includes(value.status as ProviderDispatchStatus)
    && Number.isInteger(value.attempts) && Number(value.attempts) >= 0
    && Number.isInteger(value.fencing_token) && Number(value.fencing_token) >= 0
    && Number.isInteger(value.reconciliation_attempts) && Number(value.reconciliation_attempts) >= 0
    && typeof value.stream_observed === "boolean"
    && typeof value.raw_payload_included === "boolean";
}

function requiredUrl(value: string): string {
  const text = requiredString(value, "baseUrl").replace(/\/+$/, "");
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    throw new ProviderDispatchError("invalid_input", "baseUrl must be an absolute HTTP URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ProviderDispatchError("invalid_input", "baseUrl must be an absolute HTTP URL");
  }
  return text;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ProviderDispatchError("invalid_input", `${field} must be a non-empty string`);
  }
  return value.trim();
}

function optionalString(value: unknown, field: string): string {
  if (value === "") return "";
  return requiredString(value, field);
}

function requiredTimestamp(value: unknown, field: string): string {
  const text = requiredString(value, field);
  if (Number.isNaN(Date.parse(text))) {
    throw new ProviderDispatchError("invalid_input", `${field} must be an ISO timestamp`);
  }
  return text;
}

function positiveInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || Number(value) < 1) {
    throw new ProviderDispatchError("invalid_input", `${field} must be a positive integer`);
  }
  return Number(value);
}

function jsonRecord(value: unknown, field: string): ProviderDispatchRecord {
  if (!isRecord(value)) {
    throw new ProviderDispatchError("invalid_input", `${field} must be a JSON object`);
  }
  try {
    JSON.stringify(value);
  } catch {
    throw new ProviderDispatchError("invalid_input", `${field} must be JSON serializable`);
  }
  return value as ProviderDispatchRecord;
}

function nonEmptyRecord(value: unknown, field: string): ProviderDispatchRecord {
  const record = jsonRecord(value, field);
  if (Object.keys(record).length === 0) {
    throw new ProviderDispatchError("invalid_input", `${field} must not be empty`);
  }
  return record;
}

function segment(value: unknown, field: string): string {
  return encodeURIComponent(requiredString(value, field));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
