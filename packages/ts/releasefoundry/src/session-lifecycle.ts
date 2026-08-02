import { createHash, randomUUID } from "node:crypto";

export const SESSION_LIFECYCLE_SCHEMA_VERSION = "releasefoundry.session_lifecycle.v1" as const;

export const SESSION_LIFECYCLE_STATUSES = Object.freeze([
  "active",
  "rotated",
  "revoked",
  "expired",
] as const);

export const SESSION_ASSURANCE_LEVELS = Object.freeze(["aal1", "aal2", "aal3"] as const);

export const SESSION_REVOCATION_REASONS = Object.freeze([
  "user_revoked",
  "revoke_all",
  "account_recovery",
  "refresh_reuse_detected",
  "security_event",
  "administrative",
] as const);

export const SESSION_LIFECYCLE_ERROR_CODES = Object.freeze([
  "session_invalid_request",
  "session_not_found",
  "session_expired",
  "session_revoked",
  "session_refresh_reused",
  "session_scope_mismatch",
  "session_recent_auth_required",
  "session_digest_conflict",
  "session_store_failed",
] as const);

export type SessionLifecycleStatus = (typeof SESSION_LIFECYCLE_STATUSES)[number];
export type SessionAssuranceLevel = (typeof SESSION_ASSURANCE_LEVELS)[number];
export type SessionRevocationReason = (typeof SESSION_REVOCATION_REASONS)[number];
export type SessionLifecycleErrorCode = (typeof SESSION_LIFECYCLE_ERROR_CODES)[number];

export interface SessionLifecycleRoute {
  operation:
    | "session_issue"
    | "session_authenticate"
    | "session_list"
    | "session_refresh"
    | "browser_session_refresh"
    | "session_revoke"
    | "session_revoke_all"
    | "session_recent_auth"
    | "session_recovery_invalidate";
  method: "GET" | "POST";
  path: string;
}

export const SESSION_LIFECYCLE_ROUTES: readonly SessionLifecycleRoute[] = Object.freeze([
  { operation: "session_issue", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions" },
  { operation: "session_authenticate", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/authenticate" },
  { operation: "session_list", method: "GET", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions" },
  { operation: "session_refresh", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/refresh" },
  { operation: "browser_session_refresh", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh" },
  { operation: "session_revoke", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/revoke" },
  { operation: "session_revoke_all", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/revoke-all" },
  { operation: "session_recent_auth", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/recent-auth" },
  { operation: "session_recovery_invalidate", method: "POST", path: "/v1/projects/{project_id}/accounts/{account_id}/sessions/recovery-invalidate" },
]);

export interface SessionScope {
  tenantId: string;
  projectId: string;
  accountId: string;
}

export interface SessionDTO {
  schema_version: typeof SESSION_LIFECYCLE_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  account_id: string;
  session_id: string;
  rotation_family_id: string;
  generation: number;
  status: SessionLifecycleStatus;
  assurance_level: SessionAssuranceLevel;
  authenticated_at: string;
  created_at: string;
  access_expires_at: string;
  refresh_expires_at: string;
  last_rotated_at: string | null;
  revoked_at: string | null;
  revoke_reason_code: SessionRevocationReason | null;
  access_token_present: boolean;
  refresh_token_present: boolean;
}

export type SessionPublicDTO = SessionDTO;
export type SessionPublicDto = SessionDTO;

export interface SessionRevocationDTO {
  schema_version: typeof SESSION_LIFECYCLE_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  account_id: string;
  reason_code: SessionRevocationReason;
  revoked_at: string;
  revoked_session_ids: string[];
  revoked_count: number;
}

export interface RecentAuthDTO {
  schema_version: typeof SESSION_LIFECYCLE_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  account_id: string;
  session_id: string;
  assurance_level: SessionAssuranceLevel;
  authenticated_at: string;
  valid_until: string;
  recent: true;
}

export interface SessionPageDTO {
  sessions: SessionDTO[];
}

interface SessionGenerationSnapshot {
  generation: number;
  access_token_digest: string;
  refresh_token_digest: string;
  status: SessionLifecycleStatus;
  assurance_level: SessionAssuranceLevel;
  authenticated_at: string;
  created_at: string;
  access_expires_at: string;
  refresh_expires_at: string;
  rotated_at: string | null;
  revoked_at: string | null;
  revoke_reason_code: SessionRevocationReason | null;
}

interface SessionFamilySnapshot {
  tenant_id: string;
  project_id: string;
  account_id: string;
  session_id: string;
  rotation_family_id: string;
  rotation_family_digest: string;
  created_at: string;
  reuse_detected_at: string | null;
  generations: SessionGenerationSnapshot[];
}

interface SessionIdempotencySnapshot {
  tenant_id: string;
  project_id: string;
  account_id: string;
  operation: string;
  key_digest: string;
  request_digest: string;
  response_type: "session" | "revocation";
  response: SessionDTO | SessionRevocationDTO;
}

export interface SessionLifecycleSnapshot {
  schema_version: typeof SESSION_LIFECYCLE_SCHEMA_VERSION;
  storage_mode: "digest_only";
  families: SessionFamilySnapshot[];
  idempotency: SessionIdempotencySnapshot[];
  integrity: {
    algorithm: "sha256";
    payload_sha256: string;
  };
}

interface SessionGeneration {
  generation: number;
  accessTokenDigest: string;
  refreshTokenDigest: string;
  status: SessionLifecycleStatus;
  assuranceLevel: SessionAssuranceLevel;
  authenticatedAt: string;
  createdAt: string;
  accessExpiresAt: string;
  refreshExpiresAt: string;
  rotatedAt: string | null;
  revokedAt: string | null;
  revokeReasonCode: SessionRevocationReason | null;
}

interface SessionFamily {
  scope: SessionScope;
  sessionId: string;
  rotationFamilyId: string;
  rotationFamilyDigest: string;
  createdAt: string;
  reuseDetectedAt: string | null;
  generations: SessionGeneration[];
}

interface SessionIdempotencyRecord {
  scope: SessionScope;
  operation: string;
  keyDigest: string;
  requestDigest: string;
  responseType: "session" | "revocation";
  response: SessionDTO | SessionRevocationDTO;
}

export interface SessionIssueOptions extends SessionScope {
  accessTokenDigest: string | SessionAccessTokenDigest;
  refreshTokenDigest: string | SessionRefreshTokenDigest;
  rotationFamilyDigest: string | SessionRotationFamilyDigest;
  accessExpiresAt: Date | string;
  refreshExpiresAt: Date | string;
  idempotencyKey: string;
  authenticatedAt?: Date | string;
  assuranceLevel?: SessionAssuranceLevel | string;
  sessionId?: string;
  rotationFamilyId?: string;
  familyId?: string;
  now?: Date | string;
}

export interface SessionAuthenticateOptions extends SessionScope {
  accessTokenDigest: string | SessionAccessTokenDigest;
  now?: Date | string;
}

export interface SessionRefreshOptions extends SessionScope {
  currentRefreshTokenDigest?: string | SessionRefreshTokenDigest;
  newAccessTokenDigest?: string | SessionAccessTokenDigest;
  newRefreshTokenDigest?: string | SessionRefreshTokenDigest;
  refreshTokenDigest?: string | SessionRefreshTokenDigest;
  nextAccessTokenDigest?: string | SessionAccessTokenDigest;
  nextRefreshTokenDigest?: string | SessionRefreshTokenDigest;
  accessExpiresAt: Date | string;
  refreshExpiresAt?: Date | string;
  idempotencyKey: string;
  now?: Date | string;
}

export interface SessionByIdOptions extends SessionScope {
  sessionId: string;
  now?: Date | string;
}

export interface SessionListOptions extends SessionScope {
  includeInactive?: boolean;
  now?: Date | string;
}

export interface SessionRevokeOptions extends SessionByIdOptions {
  idempotencyKey: string;
  reasonCode?: SessionRevocationReason | string;
}

export interface SessionRevokeAllOptions extends SessionScope {
  idempotencyKey: string;
  reasonCode?: SessionRevocationReason | string;
  now?: Date | string;
}

export interface SessionRecoveryOptions extends SessionScope {
  recoveryId: string;
  idempotencyKey: string;
  now?: Date | string;
}

export interface SessionRecentAuthOptions extends SessionByIdOptions {
  maxAgeSeconds: number;
  minimumAssuranceLevel?: SessionAssuranceLevel | string;
}

export interface SessionLifecycleStoreOptions {
  now?: () => Date;
  clock?: () => Date;
  idFactory?: (kind: "session" | "family") => string;
}

export interface SessionLifecycleHttpClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export interface SessionDigestIssueRequest extends SessionScope {
  accessTokenDigest: string | SessionAccessTokenDigest;
  refreshTokenDigest: string | SessionRefreshTokenDigest;
  accessExpiresAt: Date | string;
  refreshExpiresAt: Date | string;
  rotationFamilyDigest?: string | SessionRotationFamilyDigest;
  assuranceLevel?: SessionAssuranceLevel | string;
}

export interface SessionDigestRefreshRequest extends SessionScope {
  refreshTokenDigest: string | SessionRefreshTokenDigest;
  nextAccessTokenDigest: string | SessionAccessTokenDigest;
  nextRefreshTokenDigest: string | SessionRefreshTokenDigest;
  accessExpiresAt: Date | string;
  refreshExpiresAt: Date | string;
}

export interface SessionCreateRequest extends SessionScope {
  credentialId: string;
  idempotencyKey: string;
  assuranceLevel?: SessionAssuranceLevel | string;
}

export interface SessionServerRefreshRequest extends SessionByIdOptions {
  idempotencyKey: string;
}

const ERROR_ALIASES: Readonly<Record<string, SessionLifecycleErrorCode>> = Object.freeze({
  session_idempotency_conflict: "session_digest_conflict",
  session_access_expired: "session_expired",
  session_refresh_expired: "session_expired",
  session_refresh_reuse_detected: "session_refresh_reused",
  session_assurance_required: "session_recent_auth_required",
  session_snapshot_invalid: "session_invalid_request",
  session_transport_failed: "session_store_failed",
  session_forbidden_secret: "session_invalid_request",
});

interface SessionLifecycleErrorOptions {
  code?: string;
  status?: number;
  retryable?: boolean;
}

export class SessionLifecycleError extends Error {
  readonly code: SessionLifecycleErrorCode;
  readonly status: number;
  readonly retryable: boolean;

  constructor(code: string, message: string, options?: SessionLifecycleErrorOptions);
  constructor(message: string, options?: SessionLifecycleErrorOptions);
  constructor(
    codeOrMessage: string,
    messageOrOptions: string | SessionLifecycleErrorOptions = {},
    trailingOptions: SessionLifecycleErrorOptions = {},
  ) {
    const hasSeparateMessage = typeof messageOrOptions === "string";
    const rawCode = hasSeparateMessage ? codeOrMessage : messageOrOptions.code ?? "session_invalid_request";
    const options = hasSeparateMessage ? trailingOptions : messageOrOptions;
    const code = normalizeErrorCode(rawCode);
    const message = hasSeparateMessage ? messageOrOptions : codeOrMessage;
    super(redactErrorText(message));
    this.name = "SessionLifecycleError";
    this.code = code;
    this.status = options.status ?? statusForError(code);
    this.retryable = options.retryable === true;
  }

  toJSON(): Record<string, unknown> {
    return {
      schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
      error: this.code,
      message: this.message,
      status: this.status,
      retryable: this.retryable,
      access_token_present: false,
      refresh_token_present: false,
    };
  }
}

class TypedSessionDigestValue {
  readonly #value: string;
  readonly #displayName: string;
  readonly #publicMarker: string;

  protected constructor(value: string, digestName: string, displayName: string, publicMarker: string) {
    this.#value = requireDigest(digestName, value);
    this.#displayName = displayName;
    this.#publicMarker = publicMarker;
  }

  forStorage(): string {
    return this.#value;
  }

  toJSON(): Record<string, boolean> {
    return { [this.#publicMarker]: true };
  }

  toString(): string {
    return `${this.#displayName}<redacted>`;
  }
}

export class SessionAccessTokenDigest extends TypedSessionDigestValue {
  constructor(value: string) {
    super(value, "access_token_digest", "SessionAccessTokenDigest", "access_token_present");
  }
}

export class SessionRefreshTokenDigest extends TypedSessionDigestValue {
  constructor(value: string) {
    super(value, "refresh_token_digest", "SessionRefreshTokenDigest", "refresh_token_present");
  }
}

export class SessionRotationFamilyDigest extends TypedSessionDigestValue {
  constructor(value: string) {
    super(value, "rotation_family_digest", "SessionRotationFamilyDigest", "rotation_family_present");
  }

  static fromMaterial(value: string): SessionRotationFamilyDigest {
    const material = sessionTokenMaterial(value);
    try {
      return new SessionRotationFamilyDigest(createHash("sha256").update(material).digest("hex"));
    } finally {
      material.fill(0);
    }
  }
}

abstract class SessionTokenValue<Digest extends TypedSessionDigestValue> {
  #material: Uint8Array;
  #taken = false;
  readonly #displayName: string;
  readonly #tokenClass: "access" | "refresh";

  protected constructor(value: string, displayName: string, tokenClass: "access" | "refresh") {
    this.#material = sessionTokenMaterial(value);
    this.#displayName = displayName;
    this.#tokenClass = tokenClass;
  }

  get tokenClass(): "access" | "refresh" {
    return this.#tokenClass;
  }

  get available(): boolean {
    return !this.#taken && this.#material.length > 0;
  }

  protected digestValue(): string {
    if (!this.available) throw fail("session_invalid_request", "session token is unavailable");
    return createHash("sha256").update(this.#material).digest("hex");
  }

  abstract digest(): Digest;

  take(): string {
    if (!this.available) throw fail("session_invalid_request", "session token is unavailable");
    let value: string;
    try {
      value = new TextDecoder("ascii", { fatal: true }).decode(this.#material);
    } finally {
      this.#material.fill(0);
      this.#material = new Uint8Array();
      this.#taken = true;
    }
    return value;
  }

  discard(): void {
    this.#material.fill(0);
    this.#material = new Uint8Array();
    this.#taken = true;
  }

  toJSON(): Record<string, boolean> {
    return {
      access_token_present: this.available && this.#tokenClass === "access",
      refresh_token_present: this.available && this.#tokenClass === "refresh",
    };
  }

  toString(): string {
    return `${this.#displayName}<${this.available ? "present" : "consumed"},redacted>`;
  }
}

export class SessionAccessToken extends SessionTokenValue<SessionAccessTokenDigest> {
  constructor(value: string) {
    super(value, "SessionAccessToken", "access");
  }

  digest(): SessionAccessTokenDigest {
    return new SessionAccessTokenDigest(this.digestValue());
  }
}

export class SessionRefreshToken extends SessionTokenValue<SessionRefreshTokenDigest> {
  constructor(value: string) {
    super(value, "SessionRefreshToken", "refresh");
  }

  digest(): SessionRefreshTokenDigest {
    return new SessionRefreshTokenDigest(this.digestValue());
  }
}

export class SessionTokenPair {
  readonly #accessToken: SessionAccessToken;
  readonly #refreshToken: SessionRefreshToken;

  constructor(accessToken: SessionAccessToken, refreshToken: SessionRefreshToken) {
    if (!(accessToken instanceof SessionAccessToken) || !(refreshToken instanceof SessionRefreshToken)) {
      throw fail("session_invalid_request", "session token pair requires distinct access and refresh token classes");
    }
    if (!accessToken.available || !refreshToken.available) {
      throw fail("session_invalid_request", "session token pair contains unavailable material");
    }
    if (accessToken.digest().forStorage() === refreshToken.digest().forStorage()) {
      throw fail("session_invalid_request", "session access and refresh token material must be distinct");
    }
    this.#accessToken = accessToken;
    this.#refreshToken = refreshToken;
  }

  get available(): boolean {
    return this.#accessToken.available && this.#refreshToken.available;
  }

  accessDigest(): SessionAccessTokenDigest {
    return this.#accessToken.digest();
  }

  refreshDigest(): SessionRefreshTokenDigest {
    return this.#refreshToken.digest();
  }

  takeAccessToken(): string {
    return this.#accessToken.take();
  }

  takeRefreshToken(): string {
    return this.#refreshToken.take();
  }

  discard(): void {
    this.#accessToken.discard();
    this.#refreshToken.discard();
  }

  toJSON(): Record<string, boolean> {
    const payload = {
      access_token_present: this.#accessToken.available,
      refresh_token_present: this.#refreshToken.available,
    };
    assertPublicSessionPayload(payload);
    return payload;
  }

  toString(): string {
    const payload = this.toJSON();
    return `SessionTokenPair{access_token:<redacted:${payload.access_token_present}>,refresh_token:<redacted:${payload.refresh_token_present}>}`;
  }
}

export interface SessionTokenPairReceiptOptions {
  sessionId: string;
  keyVersion: string;
  accessExpiresAt: Date | string;
  refreshExpiresAt: Date | string;
  tokenPair: SessionTokenPair;
  now?: Date | string;
}

export class SessionTokenPairReceipt {
  readonly sessionId: string;
  readonly keyVersion: string;
  readonly accessExpiresAt: string;
  readonly refreshExpiresAt: string;
  #tokenPair: SessionTokenPair | null;
  #taken = false;

  constructor(options: SessionTokenPairReceiptOptions) {
    if (!(options.tokenPair instanceof SessionTokenPair)) {
      throw fail("session_invalid_request", "session token receipt requires a token pair");
    }
    if (!options.tokenPair.available) {
      throw fail("session_invalid_request", "session token receipt requires a complete pair");
    }
    const accessExpiresAt = normalizeTimestamp("access_expires_at", options.accessExpiresAt);
    const refreshExpiresAt = normalizeTimestamp("refresh_expires_at", options.refreshExpiresAt);
    if (timestampMs(accessExpiresAt) >= timestampMs(refreshExpiresAt)) {
      throw fail("session_invalid_request", "access expiration must precede refresh expiration");
    }
    if (options.now !== undefined) {
      const now = normalizeTimestamp("now", options.now);
      if (timestampMs(accessExpiresAt) <= timestampMs(now) || timestampMs(refreshExpiresAt) <= timestampMs(now)) {
        throw fail("session_invalid_request", "session token receipt is expired");
      }
    }
    this.sessionId = requireIdentifier("session_id", options.sessionId);
    this.keyVersion = requireIdentifier("key_version", options.keyVersion);
    this.accessExpiresAt = accessExpiresAt;
    this.refreshExpiresAt = refreshExpiresAt;
    this.#tokenPair = options.tokenPair;
  }

  takeTokenPair(): SessionTokenPair {
    if (this.#taken || this.#tokenPair === null) {
      throw fail("session_invalid_request", "session token receipt is unavailable");
    }
    const tokenPair = this.#tokenPair;
    this.#tokenPair = null;
    this.#taken = true;
    return tokenPair;
  }

  discard(): void {
    this.#tokenPair?.discard();
    this.#tokenPair = null;
    this.#taken = true;
  }

  toJSON(): Record<string, unknown> {
    const markers = !this.#taken && this.#tokenPair !== null
      ? this.#tokenPair.toJSON()
      : { access_token_present: false, refresh_token_present: false };
    const payload = {
      schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
      session_id: this.sessionId,
      key_version: this.keyVersion,
      access_expires_at: this.accessExpiresAt,
      refresh_expires_at: this.refreshExpiresAt,
      ...markers,
    };
    assertPublicSessionPayload(payload);
    return payload;
  }

  toString(): string {
    const payload = this.toJSON();
    return `SessionTokenPairReceipt{session_id:${JSON.stringify(this.sessionId)},key_version:${JSON.stringify(this.keyVersion)},access_expires_at:${JSON.stringify(this.accessExpiresAt)},refresh_expires_at:${JSON.stringify(this.refreshExpiresAt)},access_token:<redacted:${String(payload.access_token_present)}>,refresh_token:<redacted:${String(payload.refresh_token_present)}>` + "}";
  }
}

export class SessionLifecycleMemoryStore {
  #families = new Map<string, SessionFamily>();
  #rotationFamilyIds = new Set<string>();
  #digestIndex = new Map<string, { kind: "access" | "refresh" | "rotation_family"; sessionId: string; generation: number }>();
  #idempotency = new Map<string, SessionIdempotencyRecord>();
  readonly #clock: () => Date;
  readonly #idFactory: (kind: "session" | "family") => string;

  constructor(options: SessionLifecycleStoreOptions = {}) {
    this.#clock = options.clock ?? options.now ?? (() => new Date());
    this.#idFactory = options.idFactory ?? defaultIdFactory;
  }

  issueSession(options: SessionIssueOptions): SessionDTO {
    const scope = normalizeScope(options);
    const currentTime = this.#time(options.now);
    const authenticatedAt = this.#time(options.authenticatedAt, currentTime);
    const accessExpiresAt = this.#time(options.accessExpiresAt);
    const refreshExpiresAt = this.#time(options.refreshExpiresAt);
    const accessDigest = requireAccessDigest("access_token_digest", options.accessTokenDigest);
    const refreshDigest = requireRefreshDigest("refresh_token_digest", options.refreshTokenDigest);
    const familyDigest = requireRotationFamilyDigest("rotation_family_digest", options.rotationFamilyDigest);
    const assurance = normalizeAssurance(options.assuranceLevel ?? "aal1");
    const requestedSessionId = options.sessionId === undefined ? null : requireIdentifier("session_id", options.sessionId);
    const requestedFamilyIdValue = options.rotationFamilyId ?? options.familyId;
    const requestedFamilyId = requestedFamilyIdValue === undefined
      ? null
      : requireIdentifier("rotation_family_id", requestedFamilyIdValue);
    if (timestampMs(authenticatedAt) > timestampMs(currentTime)) {
      throw fail("session_invalid_request", "authenticated_at cannot be in the future");
    }
    validateExpirations(currentTime, accessExpiresAt, refreshExpiresAt);
    const requestDigest = fingerprint({
      ...scopeToSnake(scope),
      access_token_digest: accessDigest,
      refresh_token_digest: refreshDigest,
      rotation_family_digest: familyDigest,
      access_expires_at: accessExpiresAt,
      refresh_expires_at: refreshExpiresAt,
      authenticated_at: authenticatedAt,
      assurance_level: assurance,
      session_id: requestedSessionId,
      rotation_family_id: requestedFamilyId,
    });
    const replay = this.#idempotencyResponse(scope, "session_create", options.idempotencyKey, requestDigest, "session");
    if (replay !== null) return parseSessionDTO(replay);

    this.#assertDigestsAvailable(accessDigest, refreshDigest, familyDigest);
    const sessionId = requestedSessionId ?? this.#newId("session", new Set(this.#families.keys()));
    const rotationFamilyId = requestedFamilyId ?? this.#newId("family", this.#rotationFamilyIds);
    if (this.#families.has(sessionId) || this.#rotationFamilyIds.has(rotationFamilyId)) {
      throw fail("session_digest_conflict", "session identifier already exists");
    }
    const generation: SessionGeneration = {
      generation: 0,
      accessTokenDigest: accessDigest,
      refreshTokenDigest: refreshDigest,
      status: "active",
      assuranceLevel: assurance,
      authenticatedAt,
      createdAt: currentTime,
      accessExpiresAt,
      refreshExpiresAt,
      rotatedAt: null,
      revokedAt: null,
      revokeReasonCode: null,
    };
    const family: SessionFamily = {
      scope,
      sessionId,
      rotationFamilyId,
      rotationFamilyDigest: familyDigest,
      createdAt: currentTime,
      reuseDetectedAt: null,
      generations: [generation],
    };
    this.#families.set(sessionId, family);
    this.#rotationFamilyIds.add(rotationFamilyId);
    this.#digestIndex.set(familyDigest, { kind: "rotation_family", sessionId, generation: 0 });
    this.#digestIndex.set(accessDigest, { kind: "access", sessionId, generation: 0 });
    this.#digestIndex.set(refreshDigest, { kind: "refresh", sessionId, generation: 0 });
    const result = this.#publicSession(family, currentTime);
    this.#rememberIdempotency(scope, "session_create", options.idempotencyKey, requestDigest, "session", result);
    return result;
  }

  issue(options: SessionIssueOptions): SessionDTO {
    return this.issueSession(options);
  }

  refreshSession(options: SessionRefreshOptions): SessionDTO {
    const scope = normalizeScope(options);
    const currentTime = this.#time(options.now);
    const presentedDigest = requireRefreshDigest(
      "current_refresh_token_digest",
      options.currentRefreshTokenDigest ?? options.refreshTokenDigest,
    );
    const accessDigest = requireAccessDigest(
      "new_access_token_digest",
      options.newAccessTokenDigest ?? options.nextAccessTokenDigest,
    );
    const refreshDigest = requireRefreshDigest(
      "new_refresh_token_digest",
      options.newRefreshTokenDigest ?? options.nextRefreshTokenDigest,
    );
    const accessExpiresAt = this.#time(options.accessExpiresAt);
    const requestedRefreshExpiresAt = options.refreshExpiresAt === undefined
      ? null
      : this.#time(options.refreshExpiresAt);
    const requestDigest = fingerprint({
      ...scopeToSnake(scope),
      current_refresh_token_digest: presentedDigest,
      new_access_token_digest: accessDigest,
      new_refresh_token_digest: refreshDigest,
      access_expires_at: accessExpiresAt,
      refresh_expires_at: requestedRefreshExpiresAt,
    });
    const replay = this.#idempotencyResponse(scope, "session_refresh", options.idempotencyKey, requestDigest, "session");
    if (replay !== null) return parseSessionDTO(replay);

    const located = this.#digestIndex.get(presentedDigest);
    if (located === undefined || located.kind !== "refresh") {
      throw fail("session_not_found", "session refresh credential is unavailable");
    }
    const family = this.#families.get(located.sessionId);
    if (family === undefined) throw fail("session_store_failed", "session digest index is inconsistent");
    if (!scopeEquals(family.scope, scope)) throw fail("session_scope_mismatch", "session scope does not match");
    const generation = family.generations[located.generation];
    if (generation === undefined) throw fail("session_store_failed", "session generation index is inconsistent");
    if (generation.status === "rotated") {
      family.reuseDetectedAt ??= currentTime;
      this.#revokeFamily(family, currentTime, "refresh_reuse_detected");
      throw fail("session_refresh_reused", "refresh credential reuse detected; session family revoked");
    }
    if (generation.revokeReasonCode === "refresh_reuse_detected" || family.reuseDetectedAt !== null) {
      throw fail("session_refresh_reused", "refresh credential reuse detected; session family revoked");
    }
    if (generation.status === "revoked") throw fail("session_revoked", "session is revoked");
    if (generation.status === "expired" || timestampMs(currentTime) >= timestampMs(generation.refreshExpiresAt)) {
      generation.status = "expired";
      throw fail("session_expired", "refresh credential is expired");
    }
    if (generation !== currentGeneration(family) || generation.status !== "active") {
      throw fail("session_not_found", "session refresh credential is unavailable");
    }
    const nextRefreshExpiresAt = requestedRefreshExpiresAt ?? generation.refreshExpiresAt;
    validateExpirations(currentTime, accessExpiresAt, nextRefreshExpiresAt);
    if (timestampMs(nextRefreshExpiresAt) > timestampMs(generation.refreshExpiresAt)) {
      throw fail("session_invalid_request", "refresh rotation cannot extend the family lifetime");
    }
    this.#assertDigestsAvailable(accessDigest, refreshDigest);
    generation.status = "rotated";
    generation.rotatedAt = currentTime;
    const next: SessionGeneration = {
      generation: generation.generation + 1,
      accessTokenDigest: accessDigest,
      refreshTokenDigest: refreshDigest,
      status: "active",
      assuranceLevel: generation.assuranceLevel,
      authenticatedAt: generation.authenticatedAt,
      createdAt: currentTime,
      accessExpiresAt,
      refreshExpiresAt: nextRefreshExpiresAt,
      rotatedAt: null,
      revokedAt: null,
      revokeReasonCode: null,
    };
    family.generations.push(next);
    this.#digestIndex.set(accessDigest, { kind: "access", sessionId: family.sessionId, generation: next.generation });
    this.#digestIndex.set(refreshDigest, { kind: "refresh", sessionId: family.sessionId, generation: next.generation });
    const result = this.#publicSession(family, currentTime);
    this.#rememberIdempotency(scope, "session_refresh", options.idempotencyKey, requestDigest, "session", result);
    return result;
  }

  refresh(options: SessionRefreshOptions): SessionDTO {
    return this.refreshSession(options);
  }

  rotateRefreshToken(options: SessionRefreshOptions): SessionDTO {
    return this.refreshSession(options);
  }

  authenticateAccess(options: SessionAuthenticateOptions): SessionDTO {
    const scope = normalizeScope(options);
    const currentTime = this.#time(options.now);
    const digest = requireAccessDigest("access_token_digest", options.accessTokenDigest);
    const located = this.#digestIndex.get(digest);
    if (located === undefined || located.kind !== "access") {
      throw fail("session_not_found", "session access credential is unavailable");
    }
    const family = this.#families.get(located.sessionId);
    if (family === undefined) throw fail("session_store_failed", "session digest index is inconsistent");
    if (!scopeEquals(family.scope, scope)) throw fail("session_scope_mismatch", "session scope does not match");
    const generation = family.generations[located.generation];
    if (generation === undefined) throw fail("session_store_failed", "session generation index is inconsistent");
    if (family.reuseDetectedAt !== null) {
      throw fail("session_refresh_reused", "session family was revoked after refresh reuse");
    }
    if (generation.status === "revoked") throw fail("session_revoked", "session is revoked");
    if (generation !== currentGeneration(family) || generation.status === "rotated") {
      throw fail("session_revoked", "session access credential is unavailable");
    }
    if (timestampMs(currentTime) >= timestampMs(generation.refreshExpiresAt)) {
      generation.status = "expired";
      throw fail("session_expired", "session is expired");
    }
    if (timestampMs(currentTime) >= timestampMs(generation.accessExpiresAt)) {
      throw fail("session_expired", "access credential is expired");
    }
    if (generation.status !== "active") throw fail("session_not_found", "session access credential is unavailable");
    return this.#publicSession(family, currentTime);
  }

  authenticateAccessToken(options: SessionAuthenticateOptions): SessionDTO {
    return this.authenticateAccess(options);
  }

  authenticate(options: SessionAuthenticateOptions): SessionDTO {
    return this.authenticateAccess(options);
  }

  getSession(options: SessionByIdOptions): SessionDTO {
    const scope = normalizeScope(options);
    const currentTime = this.#time(options.now);
    const family = this.#familyForScope(scope, requireIdentifier("session_id", options.sessionId));
    expireFamily(family, currentTime);
    return this.#publicSession(family, currentTime);
  }

  listSessions(options: SessionListOptions | SessionScope): SessionDTO[] {
    const scope = normalizeScope(options);
    const currentTime = this.#time("now" in options ? options.now : undefined);
    const includeInactive = "includeInactive" in options ? options.includeInactive ?? true : true;
    if (typeof includeInactive !== "boolean") throw fail("session_invalid_request", "include_inactive must be a boolean");
    const values: SessionDTO[] = [];
    for (const family of this.#families.values()) {
      if (!scopeEquals(family.scope, scope)) continue;
      expireFamily(family, currentTime);
      if (includeInactive || currentGeneration(family).status === "active") {
        values.push(this.#publicSession(family, currentTime));
      }
    }
    return values.sort((left, right) => left.created_at.localeCompare(right.created_at) || left.session_id.localeCompare(right.session_id));
  }

  revokeSession(options: SessionRevokeOptions): SessionRevocationDTO {
    const scope = normalizeScope(options);
    const sessionId = requireIdentifier("session_id", options.sessionId);
    const reason = normalizeReason(options.reasonCode ?? "user_revoked");
    const requestDigest = fingerprint({ ...scopeToSnake(scope), session_id: sessionId, reason_code: reason });
    const replay = this.#idempotencyResponse(scope, "session_revoke", options.idempotencyKey, requestDigest, "revocation");
    if (replay !== null) return parseSessionRevocationDTO(replay);
    const currentTime = this.#time(options.now);
    const family = this.#familyForScope(scope, sessionId);
    const changed = this.#revokeFamily(family, currentTime, reason);
    const result = revocationResult(scope, reason, currentTime, changed ? [sessionId] : []);
    this.#rememberIdempotency(scope, "session_revoke", options.idempotencyKey, requestDigest, "revocation", result);
    return result;
  }

  revokeOne(options: SessionRevokeOptions): SessionRevocationDTO {
    return this.revokeSession(options);
  }

  revokeAllSessions(options: SessionRevokeAllOptions): SessionRevocationDTO {
    const scope = normalizeScope(options);
    const reason = normalizeReason(options.reasonCode ?? "revoke_all");
    const requestDigest = fingerprint({ ...scopeToSnake(scope), reason_code: reason });
    const replay = this.#idempotencyResponse(scope, "session_revoke_all", options.idempotencyKey, requestDigest, "revocation");
    if (replay !== null) return parseSessionRevocationDTO(replay);
    const currentTime = this.#time(options.now);
    const revokedIds = [...this.#families.values()]
      .filter((family) => scopeEquals(family.scope, scope) && this.#revokeFamily(family, currentTime, reason))
      .map((family) => family.sessionId)
      .sort();
    const result = revocationResult(scope, reason, currentTime, revokedIds);
    this.#rememberIdempotency(scope, "session_revoke_all", options.idempotencyKey, requestDigest, "revocation", result);
    return result;
  }

  revokeAll(options: SessionRevokeAllOptions): SessionRevocationDTO {
    return this.revokeAllSessions(options);
  }

  invalidateForRecovery(options: SessionRecoveryOptions): SessionRevocationDTO {
    const scope = normalizeScope(options);
    const recoveryId = requireIdentifier("recovery_id", options.recoveryId);
    const requestDigest = fingerprint({ ...scopeToSnake(scope), recovery_id: recoveryId });
    const replay = this.#idempotencyResponse(scope, "session_recovery_invalidate", options.idempotencyKey, requestDigest, "revocation");
    if (replay !== null) return parseSessionRevocationDTO(replay);
    const currentTime = this.#time(options.now);
    const revokedIds = [...this.#families.values()]
      .filter((family) => scopeEquals(family.scope, scope) && this.#revokeFamily(family, currentTime, "account_recovery"))
      .map((family) => family.sessionId)
      .sort();
    const result = revocationResult(scope, "account_recovery", currentTime, revokedIds);
    this.#rememberIdempotency(scope, "session_recovery_invalidate", options.idempotencyKey, requestDigest, "revocation", result);
    return result;
  }

  invalidateSessionsForRecovery(options: SessionRecoveryOptions): SessionRevocationDTO {
    return this.invalidateForRecovery(options);
  }

  recoveryInvalidate(options: SessionRecoveryOptions): SessionRevocationDTO {
    return this.invalidateForRecovery(options);
  }

  assertRecentAuth(options: SessionRecentAuthOptions): RecentAuthDTO {
    const scope = normalizeScope(options);
    const sessionId = requireIdentifier("session_id", options.sessionId);
    const maxAge = requireBoundedInteger("max_age_seconds", options.maxAgeSeconds, 0, 86_400);
    const minimum = normalizeAssurance(options.minimumAssuranceLevel ?? "aal1");
    const currentTime = this.#time(options.now);
    const family = this.#familyForScope(scope, sessionId);
    expireFamily(family, currentTime);
    const current = currentGeneration(family);
    if (current.status !== "active" || timestampMs(currentTime) >= timestampMs(current.accessExpiresAt)) {
      throw fail("session_recent_auth_required", "recent authentication is required");
    }
    if (assuranceRank(current.assuranceLevel) < assuranceRank(minimum)) {
      throw fail("session_recent_auth_required", "higher authentication assurance is required");
    }
    const validUntil = addSeconds(current.authenticatedAt, maxAge);
    if (timestampMs(currentTime) > timestampMs(validUntil)) {
      throw fail("session_recent_auth_required", "recent authentication is required");
    }
    return parseRecentAuthDTO({
      schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
      ...scopeToSnake(scope),
      session_id: family.sessionId,
      assurance_level: current.assuranceLevel,
      authenticated_at: current.authenticatedAt,
      valid_until: validUntil,
      recent: true,
    });
  }

  requireRecentAuthentication(options: SessionRecentAuthOptions): RecentAuthDTO {
    return this.assertRecentAuth(options);
  }

  requireRecentAuth(options: SessionRecentAuthOptions): RecentAuthDTO {
    return this.assertRecentAuth(options);
  }

  snapshotState(): SessionLifecycleSnapshot {
    const families = [...this.#families.values()]
      .sort((left, right) => left.sessionId.localeCompare(right.sessionId))
      .map(familySnapshot);
    const idempotency = [...this.#idempotency.values()]
      .sort(compareIdempotency)
      .map((record) => ({
        ...scopeToSnake(record.scope),
        operation: record.operation,
        key_digest: record.keyDigest,
        request_digest: record.requestDigest,
        response_type: record.responseType,
        response: cloneJson(record.response),
      }));
    const payload = {
      schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
      storage_mode: "digest_only" as const,
      families,
      idempotency,
    };
    return {
      ...payload,
      integrity: { algorithm: "sha256", payload_sha256: fingerprint(payload) },
    };
  }

  snapshot(): SessionLifecycleSnapshot {
    return this.snapshotState();
  }

  restoreState(snapshot: unknown): void {
    const restored = this.#parseSnapshot(snapshot);
    this.#families = restored.#families;
    this.#rotationFamilyIds = restored.#rotationFamilyIds;
    this.#digestIndex = restored.#digestIndex;
    this.#idempotency = restored.#idempotency;
  }

  restore(snapshot: unknown): void {
    this.restoreState(snapshot);
  }

  static fromSnapshot(
    snapshot: unknown,
    options: SessionLifecycleStoreOptions = {},
  ): SessionLifecycleMemoryStore {
    const store = new SessionLifecycleMemoryStore(options);
    store.restoreState(snapshot);
    return store;
  }

  static restore(
    snapshot: unknown,
    options: SessionLifecycleStoreOptions = {},
  ): SessionLifecycleMemoryStore {
    return SessionLifecycleMemoryStore.fromSnapshot(snapshot, options);
  }

  #parseSnapshot(value: unknown): SessionLifecycleMemoryStore {
    const snapshot = requireRecord("session snapshot", value);
    assertExactKeys("session snapshot", snapshot, SNAPSHOT_TOP_LEVEL_KEYS);
    requireLiteral("schema_version", snapshot.schema_version, SESSION_LIFECYCLE_SCHEMA_VERSION);
    requireLiteral("storage_mode", snapshot.storage_mode, "digest_only");
    const integrity = requireRecord("session snapshot integrity", snapshot.integrity);
    assertExactKeys("session snapshot integrity", integrity, INTEGRITY_KEYS);
    requireLiteral("algorithm", integrity.algorithm, "sha256");
    const expectedDigest = requireDigest("payload_sha256", integrity.payload_sha256);
    const payload = {
      schema_version: snapshot.schema_version,
      storage_mode: snapshot.storage_mode,
      families: cloneJson(snapshot.families),
      idempotency: cloneJson(snapshot.idempotency),
    };
    if (fingerprint(payload) !== expectedDigest) {
      throw fail("session_invalid_request", "session snapshot integrity check failed");
    }
    if (!Array.isArray(snapshot.families) || !Array.isArray(snapshot.idempotency)) {
      throw fail("session_invalid_request", "session snapshot collections are invalid");
    }
    const restored = new SessionLifecycleMemoryStore({ clock: this.#clock, idFactory: this.#idFactory });
    for (const family of snapshot.families) restored.#restoreFamily(family);
    for (const record of snapshot.idempotency) restored.#restoreIdempotency(record);
    return restored;
  }

  #restoreFamily(value: unknown): void {
    const payload = requireRecord("session snapshot family", value);
    assertExactKeys("session snapshot family", payload, FAMILY_SNAPSHOT_KEYS);
    const scope = normalizeSnakeScope(payload);
    const sessionId = requireIdentifier("session_id", payload.session_id);
    const familyId = requireIdentifier("rotation_family_id", payload.rotation_family_id);
    const familyDigest = requireDigest("rotation_family_digest", payload.rotation_family_digest);
    const createdAt = normalizeTimestamp("created_at", payload.created_at);
    const reuseDetectedAt = optionalTimestamp("reuse_detected_at", payload.reuse_detected_at);
    if (!Array.isArray(payload.generations) || payload.generations.length === 0) {
      throw fail("session_invalid_request", "session snapshot generations are invalid");
    }
    if (this.#families.has(sessionId) || this.#rotationFamilyIds.has(familyId)) {
      throw fail("session_invalid_request", "session snapshot identifier conflict");
    }
    this.#assertDigestsAvailable(familyDigest, true);
    const generations: SessionGeneration[] = [];
    let priorCreatedAt: string | null = null;
    payload.generations.forEach((item, index) => {
      const generation = restoreGeneration(item, index);
      if (priorCreatedAt !== null && timestampMs(generation.createdAt) < timestampMs(priorCreatedAt)) {
        throw fail("session_invalid_request", "session snapshot generation order is invalid");
      }
      priorCreatedAt = generation.createdAt;
      generations.push(generation);
    });
    if (createdAt !== generations[0]?.createdAt) {
      throw fail("session_invalid_request", "session snapshot creation time mismatch");
    }
    if (generations.slice(0, -1).some((item) => item.status === "active")) {
      throw fail("session_invalid_request", "session snapshot has multiple active generations");
    }
    if (reuseDetectedAt !== null && generations.some((item) => (
      item.status !== "revoked" || item.revokeReasonCode !== "refresh_reuse_detected"
    ))) {
      throw fail("session_invalid_request", "session snapshot reuse state is invalid");
    }
    const family: SessionFamily = {
      scope,
      sessionId,
      rotationFamilyId: familyId,
      rotationFamilyDigest: familyDigest,
      createdAt,
      reuseDetectedAt,
      generations,
    };
    this.#families.set(sessionId, family);
    this.#rotationFamilyIds.add(familyId);
    this.#digestIndex.set(familyDigest, { kind: "rotation_family", sessionId, generation: 0 });
    for (const generation of generations) {
      this.#assertDigestsAvailable(generation.accessTokenDigest, generation.refreshTokenDigest, true);
      this.#digestIndex.set(generation.accessTokenDigest, { kind: "access", sessionId, generation: generation.generation });
      this.#digestIndex.set(generation.refreshTokenDigest, { kind: "refresh", sessionId, generation: generation.generation });
    }
  }

  #restoreIdempotency(value: unknown): void {
    const payload = requireRecord("session snapshot idempotency record", value);
    assertExactKeys("session snapshot idempotency record", payload, IDEMPOTENCY_SNAPSHOT_KEYS);
    const scope = normalizeSnakeScope(payload);
    const operation = requireIdentifier("operation", payload.operation);
    const keyDigest = requireDigest("key_digest", payload.key_digest);
    const requestDigest = requireDigest("request_digest", payload.request_digest);
    const responseType = requireEnum("response_type", payload.response_type, ["session", "revocation"] as const);
    const response = responseType === "session"
      ? parseSessionDTO(payload.response)
      : parseSessionRevocationDTO(payload.response);
    const key = idempotencyMapKey(scope, operation, keyDigest);
    if (this.#idempotency.has(key)) throw fail("session_invalid_request", "session snapshot idempotency key is duplicated");
    this.#idempotency.set(key, { scope, operation, keyDigest, requestDigest, responseType, response });
  }

  #publicSession(family: SessionFamily, currentTime: string): SessionDTO {
    const current = currentGeneration(family);
    const lastRotatedAt = [...family.generations.slice(0, -1)]
      .reverse()
      .find((item) => item.rotatedAt !== null)?.rotatedAt ?? null;
    const active = current.status === "active";
    return parseSessionDTO({
      schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
      ...scopeToSnake(family.scope),
      session_id: family.sessionId,
      rotation_family_id: family.rotationFamilyId,
      generation: current.generation,
      status: current.status,
      assurance_level: current.assuranceLevel,
      authenticated_at: current.authenticatedAt,
      created_at: family.createdAt,
      access_expires_at: current.accessExpiresAt,
      refresh_expires_at: current.refreshExpiresAt,
      last_rotated_at: lastRotatedAt,
      revoked_at: current.revokedAt,
      revoke_reason_code: current.revokeReasonCode,
      access_token_present: active && timestampMs(currentTime) < timestampMs(current.accessExpiresAt),
      refresh_token_present: active && timestampMs(currentTime) < timestampMs(current.refreshExpiresAt),
    });
  }

  #revokeFamily(family: SessionFamily, revokedAt: string, reason: SessionRevocationReason): boolean {
    const changed = family.generations.some((item) => item.status !== "revoked");
    if (!changed) return false;
    for (const generation of family.generations) {
      generation.status = "revoked";
      generation.revokedAt = revokedAt;
      generation.revokeReasonCode = reason;
    }
    return true;
  }

  #familyForScope(scope: SessionScope, sessionId: string): SessionFamily {
    const family = this.#families.get(sessionId);
    if (family === undefined) throw fail("session_not_found", "session is unavailable");
    if (!scopeEquals(family.scope, scope)) throw fail("session_scope_mismatch", "session scope does not match");
    return family;
  }

  #assertDigestsAvailable(...values: Array<string | boolean>): void {
    const snapshot = typeof values.at(-1) === "boolean" ? values.pop() as boolean : false;
    const digests = values as string[];
    if (new Set(digests).size !== digests.length || digests.some((digest) => this.#digestIndex.has(digest))) {
      throw fail(snapshot ? "session_invalid_request" : "session_digest_conflict", "session digest conflict");
    }
  }

  #idempotencyResponse(
    scope: SessionScope,
    operation: string,
    key: string,
    requestDigest: string,
    responseType: "session" | "revocation",
  ): SessionDTO | SessionRevocationDTO | null {
    const keyDigest = idempotencyDigest(key);
    const record = this.#idempotency.get(idempotencyMapKey(scope, operation, keyDigest));
    if (record === undefined) return null;
    if (record.requestDigest !== requestDigest || record.responseType !== responseType) {
      throw fail("session_digest_conflict", "idempotency key was used with a different request");
    }
    return cloneJson(record.response);
  }

  #rememberIdempotency(
    scope: SessionScope,
    operation: string,
    key: string,
    requestDigest: string,
    responseType: "session" | "revocation",
    response: SessionDTO | SessionRevocationDTO,
  ): void {
    assertPublicSessionPayload(response);
    const keyDigest = idempotencyDigest(key);
    this.#idempotency.set(idempotencyMapKey(scope, operation, keyDigest), {
      scope: { ...scope },
      operation,
      keyDigest,
      requestDigest,
      responseType,
      response: cloneJson(response),
    });
  }

  #newId(kind: "session" | "family", existing: ReadonlySet<string>): string {
    for (let attempt = 0; attempt < 16; attempt += 1) {
      const candidate = requireIdentifier(`${kind}_id`, this.#idFactory(kind));
      if (!existing.has(candidate)) return candidate;
    }
    throw fail("session_store_failed", "identifier allocation failed");
  }

  #time(value?: Date | string, fallback?: string): string {
    if (value !== undefined) return normalizeTimestamp("timestamp", value);
    if (fallback !== undefined) return fallback;
    const resolved = this.#clock();
    if (!(resolved instanceof Date) || !Number.isFinite(resolved.getTime())) {
      throw fail("session_store_failed", "session clock returned an invalid timestamp");
    }
    return formatTimestamp(resolved);
  }
}

export const SessionLifecycleStore = SessionLifecycleMemoryStore;
export type SessionLifecycleStore = SessionLifecycleMemoryStore;

export class SessionLifecycleHttpClient {
  readonly #baseUrl: string;
  readonly #fetch: typeof fetch;
  readonly #headers: Record<string, string>;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;

  constructor(options: SessionLifecycleHttpClientOptions) {
    this.#baseUrl = normalizeBaseUrl(options.baseUrl);
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#headers = validateHeaders(options.headers ?? {});
    this.#timeoutMs = requireBoundedInteger("timeout_ms", options.timeoutMs ?? 30_000, 1, 300_000);
    this.#signal = options.signal;
  }

  issueSession(options: SessionDigestIssueRequest): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionCollectionRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      access_token_digest: requireAccessDigest("access_token_digest", options.accessTokenDigest),
      refresh_token_digest: requireRefreshDigest("refresh_token_digest", options.refreshTokenDigest),
      access_expires_at: normalizeTimestamp("access_expires_at", options.accessExpiresAt),
      refresh_expires_at: normalizeTimestamp("refresh_expires_at", options.refreshExpiresAt),
      assurance_level: normalizeAssurance(options.assuranceLevel ?? "aal1"),
      ...(options.rotationFamilyDigest === undefined
        ? {}
        : { rotation_family_digest: requireRotationFamilyDigest("rotation_family_digest", options.rotationFamilyDigest) }),
    }, parseSessionDTO);
  }

  authenticateAccessToken(options: SessionAuthenticateOptions): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionAuthenticateRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      access_token_digest: requireAccessDigest("access_token_digest", options.accessTokenDigest),
    }, parseSessionDTO);
  }

  rotateRefreshToken(options: SessionDigestRefreshRequest): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRefreshRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      refresh_token_digest: requireRefreshDigest("refresh_token_digest", options.refreshTokenDigest),
      next_access_token_digest: requireAccessDigest("next_access_token_digest", options.nextAccessTokenDigest),
      next_refresh_token_digest: requireRefreshDigest("next_refresh_token_digest", options.nextRefreshTokenDigest),
      access_expires_at: normalizeTimestamp("access_expires_at", options.accessExpiresAt),
      refresh_expires_at: normalizeTimestamp("refresh_expires_at", options.refreshExpiresAt),
    }, parseSessionDTO);
  }

  async listSessions(options: SessionScope): Promise<SessionDTO[]> {
    const scope = normalizeScope(options);
    const query = new URLSearchParams({ tenant_id: scope.tenantId });
    const page = await this.#request(
      "GET",
      `${sessionCollectionRoute(scope.projectId, scope.accountId)}?${query.toString()}`,
      undefined,
      parseSessionPageDTO,
    );
    return page.sessions;
  }

  getSession(options: SessionByIdOptions): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    const query = new URLSearchParams({ tenant_id: scope.tenantId });
    return this.#request(
      "GET",
      `${sessionRoute(scope.projectId, scope.accountId, options.sessionId)}?${query.toString()}`,
      undefined,
      parseSessionDTO,
    );
  }

  createSession(options: SessionCreateRequest): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionCollectionRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      credential_id: requireIdentifier("credential_id", options.credentialId),
      assurance_level: normalizeAssurance(options.assuranceLevel ?? "aal1"),
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
    }, parseSessionDTO);
  }

  refreshSession(options: SessionServerRefreshRequest): Promise<SessionDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRefreshRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      session_id: requireIdentifier("session_id", options.sessionId),
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
    }, parseSessionDTO);
  }

  revokeSession(options: SessionRevokeOptions): Promise<SessionRevocationDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRevokeRoute(scope.projectId, scope.accountId, options.sessionId), {
      tenant_id: scope.tenantId,
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      reason_code: normalizeReason(options.reasonCode ?? "user_revoked"),
    }, parseSessionRevocationDTO);
  }

  revokeAllSessions(options: SessionRevokeAllOptions): Promise<SessionRevocationDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRevokeAllRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      reason_code: normalizeReason(options.reasonCode ?? "revoke_all"),
    }, parseSessionRevocationDTO);
  }

  assertRecentAuth(options: SessionRecentAuthOptions): Promise<RecentAuthDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRecentAuthRoute(scope.projectId, scope.accountId, options.sessionId), {
      tenant_id: scope.tenantId,
      max_age_seconds: requireBoundedInteger("max_age_seconds", options.maxAgeSeconds, 0, 86_400),
      minimum_assurance_level: normalizeAssurance(options.minimumAssuranceLevel ?? "aal1"),
    }, parseRecentAuthDTO);
  }

  requireRecentAuthentication(options: SessionRecentAuthOptions): Promise<RecentAuthDTO> {
    return this.assertRecentAuth(options);
  }

  invalidateForRecovery(options: SessionRecoveryOptions): Promise<SessionRevocationDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRecoveryInvalidationRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
      recovery_id: requireIdentifier("recovery_id", options.recoveryId),
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
    }, parseSessionRevocationDTO);
  }

  invalidateSessionsForRecovery(options: SessionScope): Promise<SessionRevocationDTO> {
    const scope = normalizeScope(options);
    return this.#request("POST", sessionRecoveryInvalidationRoute(scope.projectId, scope.accountId), {
      tenant_id: scope.tenantId,
    }, parseSessionRevocationDTO);
  }

  async #request<T>(
    method: "GET" | "POST",
    path: string,
    body: Record<string, unknown> | undefined,
    parser: (value: unknown) => T,
  ): Promise<T> {
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#timeoutMs);
    const abortFromCaller = () => controller.abort();
    this.#signal?.addEventListener("abort", abortFromCaller, { once: true });
    try {
      if (this.#signal?.aborted) controller.abort();
      const response = await this.#fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          accept: "application/json",
          ...(body === undefined ? {} : { "content-type": "application/json" }),
          ...this.#headers,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const payload = await parseHttpPayload(response);
      if (!response.ok) throw parseHttpError(payload, response.status);
      assertPublicSessionPayload(payload);
      return parser(unwrapResult(payload));
    } catch (error) {
      if (error instanceof SessionLifecycleError) throw error;
      if (timedOut) throw new SessionLifecycleError("session_store_failed", "session request timed out", { status: 504, retryable: true });
      if (controller.signal.aborted) throw new SessionLifecycleError("session_store_failed", "session request was aborted", { status: 499 });
      throw new SessionLifecycleError("session_store_failed", "session request failed", { status: 502, retryable: true });
    } finally {
      clearTimeout(timeout);
      this.#signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}

export const SessionLifecycleClient = SessionLifecycleHttpClient;
export type SessionLifecycleClient = SessionLifecycleHttpClient;

export function sessionLifecycleContractManifest(): Record<string, unknown> {
  const manifest = {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    digest_only: true,
    rotation: true,
    reuse_detection: true,
    revocation: true,
    recent_auth: true,
    recovery: true,
    statuses: [...SESSION_LIFECYCLE_STATUSES],
    stable_error_codes: [...SESSION_LIFECYCLE_ERROR_CODES],
    routes: SESSION_LIFECYCLE_ROUTES.map((route) => ({ ...route })),
    invariants: {
      tenant_project_account_isolation: true,
      one_active_generation_per_rotation_family: true,
      refresh_rotation_is_atomic: true,
      reused_refresh_revokes_active_family: true,
      revoke_one_is_scoped: true,
      revoke_all_is_scoped: true,
      recent_auth_uses_original_authentication_time: true,
      recovery_invalidates_active_sessions: true,
      snapshots_are_digest_only: true,
      public_dto_excludes_token_digests: true,
      access_refresh_token_classes_are_distinct: true,
      session_token_receipts_are_one_time: true,
      refresh_bearer_never_authenticates_as_access: true,
      public_serialization_redacts_bearers: true,
    },
  };
  assertPublicSessionPayload(manifest);
  return manifest;
}

export function sessionCollectionRoute(projectId: string, accountId: string): string {
  return `/v1/projects/${routeSegment("project_id", projectId)}/accounts/${routeSegment("account_id", accountId)}/sessions`;
}

export function sessionRoute(projectId: string, accountId: string, sessionId: string): string {
  return `${sessionCollectionRoute(projectId, accountId)}/${routeSegment("session_id", sessionId)}`;
}

export function sessionAuthenticateRoute(projectId: string, accountId: string): string {
  return `${sessionCollectionRoute(projectId, accountId)}/authenticate`;
}

export function sessionRefreshRoute(projectId: string, accountId: string): string {
  return `${sessionCollectionRoute(projectId, accountId)}/refresh`;
}

export function browserSessionRefreshRoute(projectId: string, accountId: string): string {
  return `/v1/projects/${routeSegment("project_id", projectId)}/accounts/${routeSegment("account_id", accountId)}/browser-sessions/refresh`;
}

export function sessionRevokeRoute(projectId: string, accountId: string, sessionId: string): string {
  return `${sessionRoute(projectId, accountId, sessionId)}/revoke`;
}

export function sessionRevokeAllRoute(projectId: string, accountId: string): string {
  return `${sessionCollectionRoute(projectId, accountId)}/revoke-all`;
}

export function sessionRecentAuthRoute(projectId: string, accountId: string, sessionId: string): string {
  return `${sessionRoute(projectId, accountId, sessionId)}/recent-auth`;
}

export function sessionRecoveryInvalidationRoute(projectId: string, accountId: string): string {
  return `${sessionCollectionRoute(projectId, accountId)}/recovery-invalidate`;
}

export const sessionRecoveryInvalidateRoute = sessionRecoveryInvalidationRoute;

const PUBLIC_SESSION_KEYS = new Set([
  "schema_version", "tenant_id", "project_id", "account_id", "session_id",
  "rotation_family_id", "generation", "status", "assurance_level", "authenticated_at",
  "created_at", "access_expires_at", "refresh_expires_at", "last_rotated_at", "revoked_at",
  "revoke_reason_code", "access_token_present", "refresh_token_present",
]);
const PUBLIC_REVOCATION_KEYS = new Set([
  "schema_version", "tenant_id", "project_id", "account_id", "reason_code",
  "revoked_at", "revoked_session_ids", "revoked_count",
]);
const RECENT_AUTH_KEYS = new Set([
  "schema_version", "tenant_id", "project_id", "account_id", "session_id",
  "assurance_level", "authenticated_at", "valid_until", "recent",
]);
const SNAPSHOT_TOP_LEVEL_KEYS = new Set(["schema_version", "storage_mode", "families", "idempotency", "integrity"]);
const INTEGRITY_KEYS = new Set(["algorithm", "payload_sha256"]);
const FAMILY_SNAPSHOT_KEYS = new Set([
  "tenant_id", "project_id", "account_id", "session_id", "rotation_family_id",
  "rotation_family_digest", "created_at", "reuse_detected_at", "generations",
]);
const GENERATION_SNAPSHOT_KEYS = new Set([
  "generation", "access_token_digest", "refresh_token_digest", "status", "assurance_level",
  "authenticated_at", "created_at", "access_expires_at", "refresh_expires_at", "rotated_at",
  "revoked_at", "revoke_reason_code",
]);
const IDEMPOTENCY_SNAPSHOT_KEYS = new Set([
  "tenant_id", "project_id", "account_id", "operation", "key_digest", "request_digest",
  "response_type", "response",
]);
const FORBIDDEN_PUBLIC_CANONICAL_KEYS = new Set([
  "accesstoken", "accesstokendigest", "apikey", "authorization", "authorizationcode",
  "clientsecret", "cookie", "credentialsecret", "idtoken", "password", "refreshtoken",
  "refreshtokendigest", "rotationfamilydigest", "secret", "sessiontoken", "tokendigest", "token",
]);
const ALLOWED_PUBLIC_CREDENTIAL_MARKERS = new Set(["accesstokenpresent", "refreshtokenpresent"]);
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/u;
const DIGEST_PATTERN = /^[0-9a-f]{64}$/u;
const CREDENTIAL_VALUE_PATTERNS = [
  /\bbearer\s+[A-Za-z0-9._~+/-]+=*/giu,
  /\b(?:access_token|refresh_token|client_secret|password|authorization)\s*[:=]/giu,
  /\b(?:sk-|tp_|ghp_|releasefoundry_live_)[A-Za-z0-9_-]{6,}/giu,
  /\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b/gu,
] as const;

export function assertPublicSessionPayload(value: unknown): void {
  if (!isRecord(value)) throw fail("session_invalid_request", "public session payload must be an object");
  const seen = new Set<unknown>();
  const visit = (item: unknown): void => {
    if (typeof item === "string") {
      if (containsCredentialValue(item)) throw fail("session_invalid_request", "public session payload contains forbidden credential material");
      return;
    }
    if (item instanceof Uint8Array || item instanceof ArrayBuffer) {
      throw fail("session_invalid_request", "public session payload contains binary credential material");
    }
    if (typeof item !== "object" || item === null) return;
    if (seen.has(item)) throw fail("session_invalid_request", "public session payload contains a cycle");
    seen.add(item);
    if (Array.isArray(item)) {
      item.forEach(visit);
    } else {
      for (const [key, nested] of Object.entries(item)) {
        const canonical = canonicalKey(key);
        const forbiddenSuffix = ["token", "tokendigest", "secret", "password"].some((suffix) => canonical.endsWith(suffix));
        if (!ALLOWED_PUBLIC_CREDENTIAL_MARKERS.has(canonical) && (
          FORBIDDEN_PUBLIC_CANONICAL_KEYS.has(canonical) || forbiddenSuffix
        )) {
          throw fail("session_invalid_request", "public session payload contains forbidden credential material");
        }
        visit(nested);
      }
    }
    seen.delete(item);
  };
  visit(value);
}

export function parseSessionDTO(value: unknown): SessionDTO {
  assertPublicSessionPayload(value);
  const record = requireRecord("session dto", value);
  assertExactKeys("session dto", record, PUBLIC_SESSION_KEYS);
  requireLiteral("schema_version", record.schema_version, SESSION_LIFECYCLE_SCHEMA_VERSION);
  const status = requireEnum("status", record.status, SESSION_LIFECYCLE_STATUSES);
  const reason = record.revoke_reason_code === null ? null : normalizeReason(record.revoke_reason_code);
  const revokedAt = optionalTimestamp("revoked_at", record.revoked_at);
  const accessPresent = requireBoolean("access_token_present", record.access_token_present);
  const refreshPresent = requireBoolean("refresh_token_present", record.refresh_token_present);
  if (status === "revoked" && (revokedAt === null || reason === null)) {
    throw fail("session_invalid_request", "revoked session requires revocation metadata");
  }
  if (status !== "revoked" && (revokedAt !== null || reason !== null)) {
    throw fail("session_invalid_request", "non-revoked session has revocation metadata");
  }
  if (status !== "active" && (accessPresent || refreshPresent)) {
    throw fail("session_invalid_request", "inactive session cannot expose token markers");
  }
  const accessExpiresAt = normalizeTimestamp("access_expires_at", record.access_expires_at);
  const refreshExpiresAt = normalizeTimestamp("refresh_expires_at", record.refresh_expires_at);
  if (timestampMs(accessExpiresAt) > timestampMs(refreshExpiresAt)) {
    throw fail("session_invalid_request", "access expiration cannot exceed refresh expiration");
  }
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    account_id: requireIdentifier("account_id", record.account_id),
    session_id: requireIdentifier("session_id", record.session_id),
    rotation_family_id: requireIdentifier("rotation_family_id", record.rotation_family_id),
    generation: requireNonNegativeInteger("generation", record.generation),
    status,
    assurance_level: normalizeAssurance(record.assurance_level),
    authenticated_at: normalizeTimestamp("authenticated_at", record.authenticated_at),
    created_at: normalizeTimestamp("created_at", record.created_at),
    access_expires_at: accessExpiresAt,
    refresh_expires_at: refreshExpiresAt,
    last_rotated_at: optionalTimestamp("last_rotated_at", record.last_rotated_at),
    revoked_at: revokedAt,
    revoke_reason_code: reason,
    access_token_present: accessPresent,
    refresh_token_present: refreshPresent,
  };
}

export const parseSessionPublicDto = parseSessionDTO;

export function parseSessionRevocationDTO(value: unknown): SessionRevocationDTO {
  assertPublicSessionPayload(value);
  const record = requireRecord("session revocation dto", value);
  assertExactKeys("session revocation dto", record, PUBLIC_REVOCATION_KEYS);
  requireLiteral("schema_version", record.schema_version, SESSION_LIFECYCLE_SCHEMA_VERSION);
  if (!Array.isArray(record.revoked_session_ids)) throw fail("session_invalid_request", "revoked_session_ids must be an array");
  const ids = record.revoked_session_ids.map((item) => requireIdentifier("revoked_session_ids", item));
  if (new Set(ids).size !== ids.length) throw fail("session_invalid_request", "revoked_session_ids must not contain duplicates");
  const count = requireNonNegativeInteger("revoked_count", record.revoked_count);
  if (count !== ids.length) throw fail("session_invalid_request", "revoked session count mismatch");
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    account_id: requireIdentifier("account_id", record.account_id),
    reason_code: normalizeReason(record.reason_code),
    revoked_at: normalizeTimestamp("revoked_at", record.revoked_at),
    revoked_session_ids: ids,
    revoked_count: count,
  };
}

export const parseSessionRevocationDto = parseSessionRevocationDTO;

export function parseRecentAuthDTO(value: unknown): RecentAuthDTO {
  assertPublicSessionPayload(value);
  const record = requireRecord("recent auth dto", value);
  assertExactKeys("recent auth dto", record, RECENT_AUTH_KEYS);
  requireLiteral("schema_version", record.schema_version, SESSION_LIFECYCLE_SCHEMA_VERSION);
  requireLiteral("recent", record.recent, true);
  const authenticatedAt = normalizeTimestamp("authenticated_at", record.authenticated_at);
  const validUntil = normalizeTimestamp("valid_until", record.valid_until);
  if (timestampMs(validUntil) < timestampMs(authenticatedAt)) {
    throw fail("session_invalid_request", "recent authentication interval is invalid");
  }
  return {
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    tenant_id: requireIdentifier("tenant_id", record.tenant_id),
    project_id: requireIdentifier("project_id", record.project_id),
    account_id: requireIdentifier("account_id", record.account_id),
    session_id: requireIdentifier("session_id", record.session_id),
    assurance_level: normalizeAssurance(record.assurance_level),
    authenticated_at: authenticatedAt,
    valid_until: validUntil,
    recent: true,
  };
}

export const parseSessionRecentAuthDto = parseRecentAuthDTO;

export function parseSessionPageDTO(value: unknown): SessionPageDTO {
  assertPublicSessionPayload(value);
  const record = requireRecord("session page", value);
  assertExactKeys("session page", record, new Set(["sessions"]));
  if (!Array.isArray(record.sessions)) throw fail("session_invalid_request", "sessions response must be an array");
  return { sessions: record.sessions.map(parseSessionDTO) };
}

export const parseSessionPageDto = parseSessionPageDTO;

function familySnapshot(family: SessionFamily): SessionFamilySnapshot {
  return {
    ...scopeToSnake(family.scope),
    session_id: family.sessionId,
    rotation_family_id: family.rotationFamilyId,
    rotation_family_digest: family.rotationFamilyDigest,
    created_at: family.createdAt,
    reuse_detected_at: family.reuseDetectedAt,
    generations: family.generations.map((generation) => ({
      generation: generation.generation,
      access_token_digest: generation.accessTokenDigest,
      refresh_token_digest: generation.refreshTokenDigest,
      status: generation.status,
      assurance_level: generation.assuranceLevel,
      authenticated_at: generation.authenticatedAt,
      created_at: generation.createdAt,
      access_expires_at: generation.accessExpiresAt,
      refresh_expires_at: generation.refreshExpiresAt,
      rotated_at: generation.rotatedAt,
      revoked_at: generation.revokedAt,
      revoke_reason_code: generation.revokeReasonCode,
    })),
  };
}

function restoreGeneration(value: unknown, expected: number): SessionGeneration {
  const record = requireRecord("session snapshot generation", value);
  assertExactKeys("session snapshot generation", record, GENERATION_SNAPSHOT_KEYS);
  const generation = requireNonNegativeInteger("generation", record.generation);
  if (generation !== expected) throw fail("session_invalid_request", "session snapshot generation sequence is invalid");
  const status = requireEnum("status", record.status, SESSION_LIFECYCLE_STATUSES);
  const authenticatedAt = normalizeTimestamp("authenticated_at", record.authenticated_at);
  const createdAt = normalizeTimestamp("created_at", record.created_at);
  const accessExpiresAt = normalizeTimestamp("access_expires_at", record.access_expires_at);
  const refreshExpiresAt = normalizeTimestamp("refresh_expires_at", record.refresh_expires_at);
  if (timestampMs(authenticatedAt) > timestampMs(createdAt) || timestampMs(accessExpiresAt) > timestampMs(refreshExpiresAt)) {
    throw fail("session_invalid_request", "session snapshot time ordering is invalid");
  }
  const rotatedAt = optionalTimestamp("rotated_at", record.rotated_at);
  const revokedAt = optionalTimestamp("revoked_at", record.revoked_at);
  const reason = record.revoke_reason_code === null ? null : normalizeReason(record.revoke_reason_code);
  if (status === "rotated" && rotatedAt === null) throw fail("session_invalid_request", "session snapshot rotation state is invalid");
  if (status === "revoked" && (revokedAt === null || reason === null)) throw fail("session_invalid_request", "session snapshot revocation state is invalid");
  if (status !== "revoked" && (revokedAt !== null || reason !== null)) throw fail("session_invalid_request", "session snapshot revocation state is invalid");
  return {
    generation,
    accessTokenDigest: requireDigest("access_token_digest", record.access_token_digest),
    refreshTokenDigest: requireDigest("refresh_token_digest", record.refresh_token_digest),
    status,
    assuranceLevel: normalizeAssurance(record.assurance_level),
    authenticatedAt,
    createdAt,
    accessExpiresAt,
    refreshExpiresAt,
    rotatedAt,
    revokedAt,
    revokeReasonCode: reason,
  };
}

function revocationResult(
  scope: SessionScope,
  reason: SessionRevocationReason,
  revokedAt: string,
  ids: string[],
): SessionRevocationDTO {
  return parseSessionRevocationDTO({
    schema_version: SESSION_LIFECYCLE_SCHEMA_VERSION,
    ...scopeToSnake(scope),
    reason_code: reason,
    revoked_at: revokedAt,
    revoked_session_ids: [...ids],
    revoked_count: ids.length,
  });
}

function expireFamily(family: SessionFamily, currentTime: string): void {
  const current = currentGeneration(family);
  if (current.status === "active" && timestampMs(currentTime) >= timestampMs(current.refreshExpiresAt)) {
    current.status = "expired";
  }
}

function currentGeneration(family: SessionFamily): SessionGeneration {
  const current = family.generations.at(-1);
  if (current === undefined) throw fail("session_store_failed", "session family has no generation");
  return current;
}

function normalizeScope(value: SessionScope): SessionScope {
  return {
    tenantId: requireIdentifier("tenant_id", value.tenantId),
    projectId: requireIdentifier("project_id", value.projectId),
    accountId: requireIdentifier("account_id", value.accountId),
  };
}

function normalizeSnakeScope(value: Record<string, unknown>): SessionScope {
  return {
    tenantId: requireIdentifier("tenant_id", value.tenant_id),
    projectId: requireIdentifier("project_id", value.project_id),
    accountId: requireIdentifier("account_id", value.account_id),
  };
}

function scopeToSnake(scope: SessionScope): { tenant_id: string; project_id: string; account_id: string } {
  return { tenant_id: scope.tenantId, project_id: scope.projectId, account_id: scope.accountId };
}

function scopeEquals(left: SessionScope, right: SessionScope): boolean {
  return left.tenantId === right.tenantId && left.projectId === right.projectId && left.accountId === right.accountId;
}

function normalizeAssurance(value: unknown): SessionAssuranceLevel {
  return requireEnum("assurance_level", typeof value === "string" ? value.trim().toLowerCase() : value, SESSION_ASSURANCE_LEVELS);
}

function normalizeReason(value: unknown): SessionRevocationReason {
  return requireEnum("reason_code", typeof value === "string" ? value.trim().toLowerCase() : value, SESSION_REVOCATION_REASONS);
}

function assuranceRank(value: SessionAssuranceLevel): number {
  return SESSION_ASSURANCE_LEVELS.indexOf(value);
}

function validateExpirations(currentTime: string, accessExpiresAt: string, refreshExpiresAt: string): void {
  if (timestampMs(accessExpiresAt) <= timestampMs(currentTime)) throw fail("session_invalid_request", "access expiration must be in the future");
  if (timestampMs(refreshExpiresAt) <= timestampMs(accessExpiresAt)) throw fail("session_invalid_request", "refresh expiration must follow access expiration");
}

function addSeconds(value: string, seconds: number): string {
  return formatTimestampMicros(timestampMs(value) + BigInt(seconds) * 1_000_000n);
}

function timestampMs(value: string): bigint {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw fail("session_invalid_request", "timestamp must be ISO-8601");
  const fraction = /\.(\d{1,6})(?=Z|[+-]\d{2}:\d{2}$)/u.exec(value)?.[1] ?? "";
  const subMilliseconds = fraction.padEnd(6, "0").slice(3, 6) || "0";
  return BigInt(parsed) * 1_000n + BigInt(subMilliseconds);
}

function formatTimestamp(value: Date): string {
  return formatTimestampMicros(BigInt(value.getTime()) * 1_000n);
}

function formatTimestampMicros(value: bigint): string {
  const wholeSecondMicros = value - (value % 1_000_000n);
  const date = new Date(Number(wholeSecondMicros / 1_000n));
  const fraction = (value % 1_000_000n).toString().padStart(6, "0");
  return `${date.toISOString().slice(0, 19)}.${fraction}Z`;
}

function normalizeTimestamp(name: string, value: unknown): string {
  if (value instanceof Date) {
    if (!Number.isFinite(value.getTime())) throw fail("session_invalid_request", `${name} must be an ISO-8601 timestamp`);
    return formatTimestamp(value);
  }
  if (typeof value !== "string") throw fail("session_invalid_request", `${name} must be an ISO-8601 timestamp`);
  const normalized = value.trim();
  if (!/(?:Z|[+-]\d{2}:\d{2})$/u.test(normalized)) {
    throw fail("session_invalid_request", `${name} must include a timezone`);
  }
  const fraction = /\.(\d+)(?=Z|[+-]\d{2}:\d{2}$)/u.exec(normalized)?.[1] ?? "";
  if (fraction.length > 6) throw fail("session_invalid_request", `${name} exceeds microsecond precision`);
  const parsed = Date.parse(normalized);
  if (!Number.isFinite(parsed)) throw fail("session_invalid_request", `${name} must be an ISO-8601 timestamp`);
  const subMilliseconds = fraction.padEnd(6, "0").slice(3, 6) || "0";
  return formatTimestampMicros(BigInt(parsed) * 1_000n + BigInt(subMilliseconds));
}

function optionalTimestamp(name: string, value: unknown): string | null {
  return value === null ? null : normalizeTimestamp(name, value);
}

function requireDigest(name: string, value: unknown): string {
  if (typeof value !== "string" || !DIGEST_PATTERN.test(value.trim())) {
    throw fail("session_invalid_request", `${name} must be a lowercase sha256 digest`);
  }
  return value.trim();
}

type TypedSessionDigestConstructor<T extends TypedSessionDigestValue> = new (value: string) => T;

function requireTypedDigest<T extends TypedSessionDigestValue>(
  name: string,
  value: unknown,
  expectedType: TypedSessionDigestConstructor<T>,
): string {
  if (value instanceof expectedType) return value.forStorage();
  if (value instanceof TypedSessionDigestValue) {
    throw fail("session_invalid_request", `${name} token class is invalid`);
  }
  return requireDigest(name, value);
}

function requireAccessDigest(name: string, value: unknown): string {
  return requireTypedDigest(name, value, SessionAccessTokenDigest);
}

function requireRefreshDigest(name: string, value: unknown): string {
  return requireTypedDigest(name, value, SessionRefreshTokenDigest);
}

function requireRotationFamilyDigest(name: string, value: unknown): string {
  return requireTypedDigest(name, value, SessionRotationFamilyDigest);
}

function sessionTokenMaterial(value: unknown): Uint8Array {
  if (typeof value !== "string" || !/^[\x21-\x7e]{1,4096}$/u.test(value)) {
    throw fail("session_invalid_request", "session token material must be bounded printable ASCII");
  }
  return new TextEncoder().encode(value);
}

function requireIdentifier(name: string, value: unknown): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!IDENTIFIER_PATTERN.test(normalized)) throw fail("session_invalid_request", `${name} must be a non-empty opaque identifier`);
  return normalized;
}

function routeSegment(name: string, value: unknown): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (normalized.length === 0 || normalized.length > 255) throw fail("session_invalid_request", `${name} must be a non-empty route identifier`);
  return encodeURIComponent(normalized);
}

function requireBoolean(name: string, value: unknown): boolean {
  if (typeof value !== "boolean") throw fail("session_invalid_request", `${name} must be a boolean`);
  return value;
}

function requireNonNegativeInteger(name: string, value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw fail("session_invalid_request", `${name} must be a non-negative integer`);
  return value as number;
}

function requireBoundedInteger(name: string, value: unknown, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw fail("session_invalid_request", `${name} must be between ${minimum} and ${maximum}`);
  }
  return value as number;
}

function requireLiteral<T>(name: string, value: unknown, expected: T): T {
  if (value !== expected) throw fail("session_invalid_request", `${name} is invalid`);
  return expected;
}

function requireEnum<const T extends readonly string[]>(name: string, value: unknown, allowed: T): T[number] {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) throw fail("session_invalid_request", `${name} is invalid`);
  return value as T[number];
}

function requireRecord(name: string, value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw fail("session_invalid_request", `${name} must be an object`);
  return value;
}

function assertExactKeys(name: string, record: Record<string, unknown>, expected: ReadonlySet<string>): void {
  const keys = Object.keys(record);
  if (keys.length !== expected.size || keys.some((key) => !expected.has(key))) {
    throw fail("session_invalid_request", `${name} fields are invalid`);
  }
}

function fingerprint(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalValue(value)).replace(/[\u007f-\uffff]/gu, (character) => (
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
  ));
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (isRecord(value)) return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  return value;
}

function idempotencyDigest(value: unknown): string {
  return createHash("sha256").update(requireIdentifier("idempotency_key", value), "utf8").digest("hex");
}

function idempotencyMapKey(scope: SessionScope, operation: string, keyDigest: string): string {
  return JSON.stringify([scope.tenantId, scope.projectId, scope.accountId, operation, keyDigest]);
}

function compareIdempotency(left: SessionIdempotencyRecord, right: SessionIdempotencyRecord): number {
  return idempotencyMapKey(left.scope, left.operation, left.keyDigest)
    .localeCompare(idempotencyMapKey(right.scope, right.operation, right.keyDigest));
}

function containsCredentialValue(value: string): boolean {
  return CREDENTIAL_VALUE_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function canonicalKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/gu, "");
}

function redactErrorText(value: unknown): string {
  let message = String(value ?? "session lifecycle request failed").trim();
  for (const pattern of CREDENTIAL_VALUE_PATTERNS) {
    pattern.lastIndex = 0;
    message = message.replace(pattern, "[redacted]");
  }
  message = message.replace(/\b[0-9a-f]{64}\b/giu, "[redacted]");
  return message.slice(0, 500) || "session lifecycle request failed";
}

function normalizeErrorCode(value: string): SessionLifecycleErrorCode {
  if ((SESSION_LIFECYCLE_ERROR_CODES as readonly string[]).includes(value)) return value as SessionLifecycleErrorCode;
  return ERROR_ALIASES[value] ?? "session_invalid_request";
}

function statusForError(code: SessionLifecycleErrorCode): number {
  if (code === "session_not_found") return 404;
  if (code === "session_scope_mismatch") return 403;
  if (code === "session_recent_auth_required") return 401;
  if (code === "session_refresh_reused" || code === "session_digest_conflict") return 409;
  if (code === "session_store_failed") return 500;
  return 400;
}

function fail(code: SessionLifecycleErrorCode, message: string): SessionLifecycleError {
  return new SessionLifecycleError(code, message);
}

function defaultIdFactory(kind: "session" | "family"): string {
  return `${kind}_${randomUUID().replaceAll("-", "")}`;
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeBaseUrl(value: unknown): string {
  let parsed: URL;
  try {
    parsed = new URL(String(value ?? "").trim());
  } catch {
    throw fail("session_invalid_request", "base_url must be HTTP or HTTPS");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw fail("session_invalid_request", "base_url must be HTTP or HTTPS");
  }
  return parsed.toString().replace(/\/+$/u, "");
}

function validateHeaders(headers: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [name, value] of Object.entries(headers)) {
    if (!/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/u.test(name) || /[\r\n]/u.test(value)) {
      throw fail("session_invalid_request", "HTTP header is invalid");
    }
    result[name] = value;
  }
  return result;
}

async function parseHttpPayload(response: Response): Promise<unknown> {
  if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
    throw new SessionLifecycleError("session_store_failed", "session response must be JSON", { status: 502, retryable: true });
  }
  try {
    return await response.json();
  } catch {
    throw new SessionLifecycleError("session_store_failed", "session response JSON is invalid", { status: 502, retryable: true });
  }
}

function parseHttpError(payload: unknown, status: number): SessionLifecycleError {
  let code: SessionLifecycleErrorCode = "session_store_failed";
  let retryable = status === 429 || status >= 500;
  if (isRecord(payload)) {
    const error = isRecord(payload.error) ? payload.error : payload;
    const rawCode = typeof error.code === "string" ? error.code : typeof payload.error === "string" ? payload.error : "";
    if ((SESSION_LIFECYCLE_ERROR_CODES as readonly string[]).includes(rawCode)) code = rawCode as SessionLifecycleErrorCode;
    retryable = error.retryable === true || retryable;
  }
  return new SessionLifecycleError(code, "session HTTP request failed", { status, retryable });
}

function unwrapResult(value: unknown): unknown {
  if (!isRecord(value)) return value;
  return Object.keys(value).length === 1 && Object.hasOwn(value, "result") ? value.result : value;
}
