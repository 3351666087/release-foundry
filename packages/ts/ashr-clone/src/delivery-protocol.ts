export const IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION = "ashr.clone.identity_delivery_protocol.v1" as const;

export const IDENTITY_DELIVERY_STATUSES = Object.freeze([
  "pending",
  "leased",
  "retry",
  "provider_accepted",
  "delivered",
  "ambiguous",
  "dead",
] as const);

export const IDENTITY_DELIVERY_ACCEPTANCE_STATUSES = Object.freeze([
  "provider_accepted",
  "ambiguous",
] as const);

export const IDENTITY_DELIVERY_DTO_KINDS = Object.freeze([
  "task",
  "acceptance",
  "redrive_request",
  "redrive_receipt",
] as const);

export const IDENTITY_DELIVERY_ERROR_CODES = Object.freeze([
  "identity_delivery_invalid_request",
  "identity_delivery_secret_forbidden",
  "identity_delivery_unknown_field",
  "identity_delivery_status_conflict",
  "identity_delivery_scope_mismatch",
  "identity_delivery_not_found",
  "identity_delivery_lease_conflict",
  "identity_delivery_idempotency_conflict",
  "identity_delivery_not_redrivable",
  "identity_delivery_ambiguous",
  "identity_delivery_store_failed",
] as const);

export const IDENTITY_DELIVERY_FAILURE_CODES = Object.freeze([
  "malformed_task",
  "malformed_payload",
  "challenge_expired",
  "attempts_exhausted",
  "vault_unavailable",
  "vault_timeout",
  "smtp_delivery_failed",
  "sms_delivery_failed",
  "provider_timeout",
  "provider_rejected",
  "provider_result_ambiguous",
  "lease_expired",
  "lease_lost",
] as const);

export type IdentityDeliveryStatus = (typeof IDENTITY_DELIVERY_STATUSES)[number];
export type IdentityDeliveryAcceptanceStatus = (typeof IDENTITY_DELIVERY_ACCEPTANCE_STATUSES)[number];
export type IdentityDeliveryDtoKind = (typeof IDENTITY_DELIVERY_DTO_KINDS)[number];
export type IdentityDeliveryErrorCode = (typeof IDENTITY_DELIVERY_ERROR_CODES)[number];
export type IdentityDeliveryFailureCode = (typeof IDENTITY_DELIVERY_FAILURE_CODES)[number];
export type IdentityDeliveryChannel = "email" | "phone";
export type IdentityDeliveryPurpose = "binding" | "login" | "recovery";

export interface IdentityDeliveryAdminRoute {
  operation:
    | "identity_delivery_admin_list"
    | "identity_delivery_admin_get"
    | "identity_delivery_admin_acceptances"
    | "identity_delivery_admin_redrive"
    | "identity_delivery_admin_redrive_audit";
  method: "GET" | "POST";
  path: string;
}

export const IDENTITY_DELIVERY_ADMIN_ROUTES: readonly IdentityDeliveryAdminRoute[] = Object.freeze([
  { operation: "identity_delivery_admin_list", method: "GET", path: "/v1/projects/{project_id}/admin/identity-deliveries" },
  { operation: "identity_delivery_admin_get", method: "GET", path: "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}" },
  { operation: "identity_delivery_admin_acceptances", method: "GET", path: "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/acceptances" },
  { operation: "identity_delivery_admin_redrive", method: "POST", path: "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/redrive" },
  { operation: "identity_delivery_admin_redrive_audit", method: "GET", path: "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/redrives" },
]);

export interface IdentityDeliveryTaskDTO {
  schema_version: typeof IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION;
  task_id: string;
  tenant_id: string;
  project_id: string;
  challenge_id: string;
  channel: IdentityDeliveryChannel;
  purpose: IdentityDeliveryPurpose;
  status: IdentityDeliveryStatus;
  attempt: number;
  max_attempts: number;
  lease_generation: number;
  redrive_count: number;
  provider_idempotency_key: string;
  challenge_expires_at: string;
  lease_expires_at: string | null;
  next_attempt_at: string | null;
  provider_acceptance_present: boolean;
  accepted_at: string | null;
  completed_at: string | null;
  dead_at: string | null;
  last_failure_code: IdentityDeliveryFailureCode | null;
}

export interface IdentityDeliveryAcceptanceDTO {
  schema_version: typeof IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION;
  task_id: string;
  tenant_id: string;
  project_id: string;
  challenge_id: string;
  status: IdentityDeliveryAcceptanceStatus;
  attempt: number;
  lease_generation: number;
  provider_idempotency_key: string;
  provider_acceptance_present: boolean;
  accepted_at: string | null;
  recorded_at: string;
  failure_code: IdentityDeliveryFailureCode | null;
}

export interface IdentityDeliveryRedriveRequestDTO {
  schema_version: typeof IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION;
  task_id: string;
  tenant_id: string;
  project_id: string;
  expected_lease_generation: number;
  actor_id: string;
  reason_code: string;
  request_id: string;
}

export interface IdentityDeliveryRedriveReceiptDTO {
  schema_version: typeof IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION;
  task_id: string;
  tenant_id: string;
  project_id: string;
  request_id: string;
  audit_id: string;
  actor_id: string;
  reason_code: string;
  status: "pending";
  previous_lease_generation: number;
  lease_generation: number;
  previous_provider_idempotency_key: string;
  provider_idempotency_key: string;
  redriven_at: string;
}

export type IdentityDeliveryDTO =
  | IdentityDeliveryTaskDTO
  | IdentityDeliveryAcceptanceDTO
  | IdentityDeliveryRedriveRequestDTO
  | IdentityDeliveryRedriveReceiptDTO;

const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/u;
const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,255}$/u;
const REASON_PATTERN = /^[a-z][a-z0-9_.-]{1,63}$/u;
const TIMESTAMP_PATTERN = /^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}Z$/u;
const PRIVATE_REFERENCE_PATTERN = /(?:^|\s)(?:vault|env|kms|secret|provider-ref|opaque-ref):/iu;
const EMAIL_PATTERN = /\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+\b/iu;
const PHONE_PATTERN = /(?:^|[^A-Za-z0-9])\+[1-9][0-9]{7,14}(?![0-9])/u;
const TOKEN_PATTERNS = [
  /\bbearer\s+[A-Za-z0-9._~+/-]+=*/iu,
  /\b(?:access_token|refresh_token|client_secret|password|authorization)\s*[:=]/iu,
  /\b(?:sk-|tp_|ghp_|ashr_live_)[A-Za-z0-9_-]{6,}/iu,
  /\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b/u,
] as const;
const FORBIDDEN_PUBLIC_KEYS = new Set([
  "authorization",
  "code",
  "destination",
  "destinationdigest",
  "email",
  "otp",
  "opaqueref",
  "password",
  "phone",
  "privateevidencepath",
  "privateref",
  "provideracceptanceid",
  "provideracceptanceref",
  "secret",
  "secretref",
  "token",
  "vaultref",
  "verificationcode",
]);
const FORBIDDEN_PUBLIC_SUFFIXES = [
  "accesstoken",
  "destination",
  "opaqueref",
  "privateref",
  "provideracceptanceref",
  "refreshtoken",
  "secret",
  "sessiontoken",
  "vaultref",
] as const;
const MAX_CANONICAL_JSON_BYTES = 64 * 1024;

const TASK_KEYS = new Set([
  "schema_version",
  "task_id",
  "tenant_id",
  "project_id",
  "challenge_id",
  "channel",
  "purpose",
  "status",
  "attempt",
  "max_attempts",
  "lease_generation",
  "redrive_count",
  "provider_idempotency_key",
  "challenge_expires_at",
  "lease_expires_at",
  "next_attempt_at",
  "provider_acceptance_present",
  "accepted_at",
  "completed_at",
  "dead_at",
  "last_failure_code",
]);
const ACCEPTANCE_KEYS = new Set([
  "schema_version",
  "task_id",
  "tenant_id",
  "project_id",
  "challenge_id",
  "status",
  "attempt",
  "lease_generation",
  "provider_idempotency_key",
  "provider_acceptance_present",
  "accepted_at",
  "recorded_at",
  "failure_code",
]);
const REDRIVE_REQUEST_KEYS = new Set([
  "schema_version",
  "task_id",
  "tenant_id",
  "project_id",
  "expected_lease_generation",
  "actor_id",
  "reason_code",
  "request_id",
]);
const REDRIVE_RECEIPT_KEYS = new Set([
  "schema_version",
  "task_id",
  "tenant_id",
  "project_id",
  "request_id",
  "audit_id",
  "actor_id",
  "reason_code",
  "status",
  "previous_lease_generation",
  "lease_generation",
  "previous_provider_idempotency_key",
  "provider_idempotency_key",
  "redriven_at",
]);

export class IdentityDeliveryProtocolError extends Error {
  readonly code: IdentityDeliveryErrorCode;

  constructor(
    message: string,
    code: IdentityDeliveryErrorCode = "identity_delivery_invalid_request",
  ) {
    if (!IDENTITY_DELIVERY_ERROR_CODES.includes(code)) {
      throw new TypeError("unknown identity delivery protocol error code");
    }
    super(publicErrorMessage(message));
    this.name = "IdentityDeliveryProtocolError";
    this.code = code;
  }
}

export function identityDeliveryProtocolContractManifest(): Record<string, unknown> {
  const manifest = {
    schema_version: IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    dto_kinds: [...IDENTITY_DELIVERY_DTO_KINDS],
    statuses: [...IDENTITY_DELIVERY_STATUSES],
    acceptance_statuses: [...IDENTITY_DELIVERY_ACCEPTANCE_STATUSES],
    stable_error_codes: [...IDENTITY_DELIVERY_ERROR_CODES],
    failure_codes: [...IDENTITY_DELIVERY_FAILURE_CODES],
    routes: IDENTITY_DELIVERY_ADMIN_ROUTES.map((route) => ({ ...route })),
    invariants: {
      tenant_project_scope_required: true,
      raw_delivery_material_absent: true,
      private_reference_absent: true,
      provider_idempotency_stable_on_retry: true,
      provider_idempotency_rotates_only_on_audited_redrive: true,
      provider_acceptance_presence_marker_only: true,
      ambiguous_provider_outcome_fails_closed: true,
      redrive_requires_generation_actor_reason_request: true,
      admin_authorization_required: true,
      routes_are_contract_only: true,
      canonical_json_cross_language: true,
    },
  };
  assertPublicIdentityDeliveryPayload(manifest);
  return manifest;
}

export function identityDeliveryAdminCollectionRoute(projectId: string): string {
  return `/v1/projects/${routeSegment("project_id", projectId)}/admin/identity-deliveries`;
}

export function identityDeliveryAdminTaskRoute(projectId: string, taskId: string): string {
  return `${identityDeliveryAdminCollectionRoute(projectId)}/${routeSegment("task_id", taskId)}`;
}

export function identityDeliveryAdminAcceptancesRoute(projectId: string, taskId: string): string {
  return `${identityDeliveryAdminTaskRoute(projectId, taskId)}/acceptances`;
}

export function identityDeliveryAdminRedriveRoute(projectId: string, taskId: string): string {
  return `${identityDeliveryAdminTaskRoute(projectId, taskId)}/redrive`;
}

export function identityDeliveryAdminRedrivesRoute(projectId: string, taskId: string): string {
  return `${identityDeliveryAdminTaskRoute(projectId, taskId)}/redrives`;
}

export function assertPublicIdentityDeliveryPayload(value: unknown): void {
  const seen = new Set<object>();
  const visit = (item: unknown): void => {
    if (typeof item === "string") {
      if (containsPrivateMaterial(item)) {
        throw fail(
          "identity_delivery_secret_forbidden",
          "public identity delivery payload contains forbidden material",
        );
      }
      return;
    }
    if (item instanceof Uint8Array || item instanceof ArrayBuffer) {
      throw fail(
        "identity_delivery_secret_forbidden",
        "public identity delivery payload contains forbidden binary material",
      );
    }
    if (item === null || ["boolean", "number", "undefined"].includes(typeof item)) return;
    if (typeof item !== "object") {
      throw fail("identity_delivery_invalid_request", "public identity delivery payload contains an unsupported value");
    }
    if (seen.has(item)) {
      throw fail("identity_delivery_invalid_request", "public identity delivery payload contains a cycle");
    }
    seen.add(item);
    if (Array.isArray(item)) {
      item.forEach(visit);
      seen.delete(item);
      return;
    }
    if (!isRecord(item)) {
      throw fail("identity_delivery_invalid_request", "public identity delivery payload contains an unsupported object");
    }
    for (const [key, nested] of Object.entries(item)) {
      const canonical = canonicalKey(key);
      if (
        FORBIDDEN_PUBLIC_KEYS.has(canonical)
        || FORBIDDEN_PUBLIC_SUFFIXES.some((suffix) => canonical.endsWith(suffix))
      ) {
        throw fail(
          "identity_delivery_secret_forbidden",
          "public identity delivery payload contains forbidden material",
        );
      }
      visit(nested);
    }
    seen.delete(item);
  };
  visit(value);
}

export function validateIdentityDeliveryTask(value: unknown): IdentityDeliveryTaskDTO {
  assertPublicIdentityDeliveryPayload(value);
  const record = requireRecord("delivery task", value);
  assertExactKeys("delivery task", record, TASK_KEYS);
  requireLiteral("schema_version", record.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION);
  const task: IdentityDeliveryTaskDTO = {
    schema_version: IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    task_id: requireIdentifier("task_id", record.task_id),
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    challenge_id: requireIdentifier("challenge_id", record.challenge_id),
    channel: requireEnum("channel", record.channel, ["email", "phone"] as const),
    purpose: requireEnum("purpose", record.purpose, ["binding", "login", "recovery"] as const),
    status: requireEnum("status", record.status, IDENTITY_DELIVERY_STATUSES),
    attempt: requireInteger("attempt", record.attempt, 0, 1000),
    max_attempts: requireInteger("max_attempts", record.max_attempts, 1, 1000),
    lease_generation: requireInteger("lease_generation", record.lease_generation, 0, Number.MAX_SAFE_INTEGER),
    redrive_count: requireInteger("redrive_count", record.redrive_count, 0, 1000),
    provider_idempotency_key: requireIdempotencyKey(record.provider_idempotency_key),
    challenge_expires_at: requireTimestamp("challenge_expires_at", record.challenge_expires_at),
    lease_expires_at: optionalTimestamp("lease_expires_at", record.lease_expires_at),
    next_attempt_at: optionalTimestamp("next_attempt_at", record.next_attempt_at),
    provider_acceptance_present: requireBoolean("provider_acceptance_present", record.provider_acceptance_present),
    accepted_at: optionalTimestamp("accepted_at", record.accepted_at),
    completed_at: optionalTimestamp("completed_at", record.completed_at),
    dead_at: optionalTimestamp("dead_at", record.dead_at),
    last_failure_code: optionalFailureCode(record.last_failure_code),
  };
  if (task.attempt > task.max_attempts) statusConflict("attempt cannot exceed max_attempts");
  validateTaskState(task);
  return task;
}

export function validateIdentityDeliveryAcceptance(value: unknown): IdentityDeliveryAcceptanceDTO {
  assertPublicIdentityDeliveryPayload(value);
  const record = requireRecord("delivery acceptance", value);
  assertExactKeys("delivery acceptance", record, ACCEPTANCE_KEYS);
  requireLiteral("schema_version", record.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION);
  const acceptance: IdentityDeliveryAcceptanceDTO = {
    schema_version: IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    task_id: requireIdentifier("task_id", record.task_id),
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    challenge_id: requireIdentifier("challenge_id", record.challenge_id),
    status: requireEnum("status", record.status, IDENTITY_DELIVERY_ACCEPTANCE_STATUSES),
    attempt: requireInteger("attempt", record.attempt, 1, 1000),
    lease_generation: requireInteger("lease_generation", record.lease_generation, 1, Number.MAX_SAFE_INTEGER),
    provider_idempotency_key: requireIdempotencyKey(record.provider_idempotency_key),
    provider_acceptance_present: requireBoolean("provider_acceptance_present", record.provider_acceptance_present),
    accepted_at: optionalTimestamp("accepted_at", record.accepted_at),
    recorded_at: requireTimestamp("recorded_at", record.recorded_at),
    failure_code: optionalFailureCode(record.failure_code),
  };
  if (acceptance.status === "provider_accepted") {
    if (
      !acceptance.provider_acceptance_present
      || acceptance.accepted_at === null
      || acceptance.failure_code !== null
    ) {
      statusConflict("accepted delivery requires confirmed provider acceptance");
    }
    if (acceptance.accepted_at > acceptance.recorded_at) {
      statusConflict("provider acceptance cannot be recorded before it occurs");
    }
  } else if (
    acceptance.provider_acceptance_present
    || acceptance.accepted_at !== null
    || acceptance.failure_code !== "provider_result_ambiguous"
  ) {
    statusConflict("ambiguous delivery cannot claim provider acceptance");
  }
  return acceptance;
}

export function validateIdentityDeliveryRedriveRequest(value: unknown): IdentityDeliveryRedriveRequestDTO {
  assertPublicIdentityDeliveryPayload(value);
  const record = requireRecord("delivery redrive request", value);
  assertExactKeys("delivery redrive request", record, REDRIVE_REQUEST_KEYS);
  requireLiteral("schema_version", record.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION);
  return {
    schema_version: IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    task_id: requireIdentifier("task_id", record.task_id),
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    expected_lease_generation: requireInteger(
      "expected_lease_generation",
      record.expected_lease_generation,
      1,
      Number.MAX_SAFE_INTEGER - 1,
    ),
    actor_id: requireIdentifier("actor_id", record.actor_id),
    reason_code: requireReasonCode(record.reason_code),
    request_id: requireIdentifier("request_id", record.request_id),
  };
}

export function validateIdentityDeliveryRedriveReceipt(value: unknown): IdentityDeliveryRedriveReceiptDTO {
  assertPublicIdentityDeliveryPayload(value);
  const record = requireRecord("delivery redrive receipt", value);
  assertExactKeys("delivery redrive receipt", record, REDRIVE_RECEIPT_KEYS);
  requireLiteral("schema_version", record.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION);
  const receipt: IdentityDeliveryRedriveReceiptDTO = {
    schema_version: IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
    task_id: requireIdentifier("task_id", record.task_id),
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    request_id: requireIdentifier("request_id", record.request_id),
    audit_id: requireIdentifier("audit_id", record.audit_id),
    actor_id: requireIdentifier("actor_id", record.actor_id),
    reason_code: requireReasonCode(record.reason_code),
    status: requireLiteral("status", record.status, "pending"),
    previous_lease_generation: requireInteger(
      "previous_lease_generation",
      record.previous_lease_generation,
      1,
      Number.MAX_SAFE_INTEGER - 1,
    ),
    lease_generation: requireInteger("lease_generation", record.lease_generation, 2, Number.MAX_SAFE_INTEGER),
    previous_provider_idempotency_key: requireIdempotencyKey(record.previous_provider_idempotency_key),
    provider_idempotency_key: requireIdempotencyKey(record.provider_idempotency_key),
    redriven_at: requireTimestamp("redriven_at", record.redriven_at),
  };
  if (receipt.lease_generation !== receipt.previous_lease_generation + 1) {
    statusConflict("redrive must advance the lease generation exactly once");
  }
  if (receipt.provider_idempotency_key === receipt.previous_provider_idempotency_key) {
    throw fail(
      "identity_delivery_idempotency_conflict",
      "audited redrive must rotate the provider idempotency key",
    );
  }
  return receipt;
}

export function canonicalIdentityDeliveryJson(
  kind: IdentityDeliveryDtoKind | string,
  value: unknown,
): string {
  const normalizedKind = requireEnum("dto kind", kind, IDENTITY_DELIVERY_DTO_KINDS);
  const dto = validateByKind(normalizedKind, value);
  assertPublicIdentityDeliveryPayload(dto);
  const encoded = JSON.stringify(sortJsonValue(dto));
  if (new TextEncoder().encode(encoded).byteLength > MAX_CANONICAL_JSON_BYTES) {
    throw fail("identity_delivery_invalid_request", "identity delivery payload is too large");
  }
  return encoded;
}

export function parseIdentityDeliveryCanonicalJson(
  kind: IdentityDeliveryDtoKind | string,
  value: string,
): IdentityDeliveryDTO {
  const normalizedKind = requireEnum("dto kind", kind, IDENTITY_DELIVERY_DTO_KINDS);
  if (typeof value !== "string") {
    throw fail("identity_delivery_invalid_request", "identity delivery JSON must be text");
  }
  const byteLength = new TextEncoder().encode(value).byteLength;
  if (byteLength === 0 || byteLength > MAX_CANONICAL_JSON_BYTES) {
    throw fail("identity_delivery_invalid_request", "identity delivery JSON size is invalid");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(value) as unknown;
  } catch {
    throw fail("identity_delivery_invalid_request", "identity delivery JSON is invalid");
  }
  const dto = validateByKind(normalizedKind, payload);
  if (canonicalIdentityDeliveryJson(normalizedKind, dto) !== value) {
    throw fail("identity_delivery_invalid_request", "identity delivery JSON is not canonical");
  }
  return dto;
}

function validateByKind(kind: IdentityDeliveryDtoKind, value: unknown): IdentityDeliveryDTO {
  switch (kind) {
    case "task": return validateIdentityDeliveryTask(value);
    case "acceptance": return validateIdentityDeliveryAcceptance(value);
    case "redrive_request": return validateIdentityDeliveryRedriveRequest(value);
    case "redrive_receipt": return validateIdentityDeliveryRedriveReceipt(value);
  }
}

function validateTaskState(task: IdentityDeliveryTaskDTO): void {
  const leased = task.status === "leased";
  if (leased !== (task.lease_expires_at !== null)) {
    statusConflict("only leased delivery tasks carry lease expiration");
  }
  if (leased && task.lease_generation < 1) {
    statusConflict("leased delivery tasks require a positive generation");
  }
  const retry = task.status === "retry";
  if (retry !== (task.next_attempt_at !== null)) {
    statusConflict("only retry delivery tasks carry a next attempt time");
  }
  if (retry && task.last_failure_code === null) {
    statusConflict("retry delivery tasks require a failure code");
  }

  let valid: boolean;
  if (task.status === "provider_accepted") {
    valid = task.provider_acceptance_present
      && task.accepted_at !== null
      && task.completed_at === null
      && task.dead_at === null
      && task.last_failure_code === null;
  } else if (task.status === "delivered") {
    valid = task.provider_acceptance_present
      && task.accepted_at !== null
      && task.completed_at !== null
      && task.dead_at === null
      && task.last_failure_code === null
      && task.accepted_at <= task.completed_at;
  } else if (task.status === "ambiguous") {
    valid = !task.provider_acceptance_present
      && task.accepted_at === null
      && task.completed_at === null
      && task.dead_at === null
      && task.last_failure_code === "provider_result_ambiguous";
  } else if (task.status === "dead") {
    valid = !task.provider_acceptance_present
      && task.accepted_at === null
      && task.completed_at === null
      && task.dead_at !== null
      && task.last_failure_code !== null;
  } else {
    valid = !task.provider_acceptance_present
      && task.accepted_at === null
      && task.completed_at === null
      && task.dead_at === null;
  }
  if (!valid) statusConflict("delivery task terminal metadata conflicts with status");
}

function assertExactKeys(name: string, record: Record<string, unknown>, expected: ReadonlySet<string>): void {
  const actual = Object.keys(record);
  if (actual.some((key) => !expected.has(key))) {
    throw fail("identity_delivery_unknown_field", `${name} contains an unknown field`);
  }
  if ([...expected].some((key) => !Object.hasOwn(record, key))) {
    throw fail("identity_delivery_invalid_request", `${name} is missing a required field`);
  }
}

function requireRecord(name: string, value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw fail("identity_delivery_invalid_request", `${name} must be an object`);
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value) as object | null;
  return prototype === Object.prototype || prototype === null;
}

function requireIdentifier(name: string, value: unknown): string {
  if (typeof value !== "string" || !IDENTIFIER_PATTERN.test(value)) {
    throw fail("identity_delivery_invalid_request", `${name} must be a valid identifier`);
  }
  return value;
}

function requireIdempotencyKey(value: unknown): string {
  if (typeof value !== "string" || !IDEMPOTENCY_PATTERN.test(value)) {
    throw fail("identity_delivery_invalid_request", "provider idempotency key is invalid");
  }
  return value;
}

function requireReasonCode(value: unknown): string {
  if (typeof value !== "string" || !REASON_PATTERN.test(value)) {
    throw fail("identity_delivery_invalid_request", "reason code is invalid");
  }
  return value;
}

function requireInteger(name: string, value: unknown, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw fail("identity_delivery_invalid_request", `${name} is outside the supported range`);
  }
  return value as number;
}

function requireBoolean(name: string, value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw fail("identity_delivery_invalid_request", `${name} must be a boolean`);
  }
  return value;
}

function requireLiteral<const T extends string>(name: string, value: unknown, expected: T): T {
  if (value !== expected) throw fail("identity_delivery_invalid_request", `${name} is not supported`);
  return expected;
}

function requireEnum<const T extends readonly string[]>(name: string, value: unknown, allowed: T): T[number] {
  if (typeof value !== "string" || !allowed.includes(value as T[number])) {
    throw fail("identity_delivery_invalid_request", `${name} is not supported`);
  }
  return value as T[number];
}

function optionalFailureCode(value: unknown): IdentityDeliveryFailureCode | null {
  if (value === null) return null;
  return requireEnum("failure code", value, IDENTITY_DELIVERY_FAILURE_CODES);
}

function requireTimestamp(name: string, value: unknown): string {
  if (typeof value !== "string" || !TIMESTAMP_PATTERN.test(value)) {
    throw fail("identity_delivery_invalid_request", `${name} must be a canonical UTC timestamp`);
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw fail("identity_delivery_invalid_request", `${name} must be a canonical UTC timestamp`);
  }
  return value;
}

function optionalTimestamp(name: string, value: unknown): string | null {
  if (value === null) return null;
  return requireTimestamp(name, value);
}

function routeSegment(name: string, value: unknown): string {
  return encodeURIComponent(requireIdentifier(name, value));
}

function canonicalKey(value: string): string {
  return [...value].filter((character) => /[A-Za-z0-9]/u.test(character)).join("").toLowerCase();
}

function containsPrivateMaterial(value: string): boolean {
  return PRIVATE_REFERENCE_PATTERN.test(value)
    || EMAIL_PATTERN.test(value)
    || PHONE_PATTERN.test(value)
    || TOKEN_PATTERNS.some((pattern) => pattern.test(value));
}

function publicErrorMessage(message: string): string {
  const candidate = String(message || "identity delivery payload rejected");
  return containsPrivateMaterial(candidate) ? "identity delivery payload rejected" : candidate;
}

function fail(code: IdentityDeliveryErrorCode, message: string): IdentityDeliveryProtocolError {
  return new IdentityDeliveryProtocolError(message, code);
}

function statusConflict(message: string): never {
  throw fail("identity_delivery_status_conflict", message);
}

function sortJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJsonValue);
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, sortJsonValue(value[key])]),
    );
  }
  return value;
}

// Python-compatible names keep public contract quickstarts source-compatible.
export const assert_public_identity_delivery_payload = assertPublicIdentityDeliveryPayload;
export const canonical_identity_delivery_json = canonicalIdentityDeliveryJson;
export const identity_delivery_admin_acceptances_route = identityDeliveryAdminAcceptancesRoute;
export const identity_delivery_admin_collection_route = identityDeliveryAdminCollectionRoute;
export const identity_delivery_admin_redrive_route = identityDeliveryAdminRedriveRoute;
export const identity_delivery_admin_redrives_route = identityDeliveryAdminRedrivesRoute;
export const identity_delivery_admin_task_route = identityDeliveryAdminTaskRoute;
export const identity_delivery_protocol_contract_manifest = identityDeliveryProtocolContractManifest;
export const parse_identity_delivery_canonical_json = parseIdentityDeliveryCanonicalJson;
export const validate_identity_delivery_acceptance = validateIdentityDeliveryAcceptance;
export const validate_identity_delivery_redrive_receipt = validateIdentityDeliveryRedriveReceipt;
export const validate_identity_delivery_redrive_request = validateIdentityDeliveryRedriveRequest;
export const validate_identity_delivery_task = validateIdentityDeliveryTask;
