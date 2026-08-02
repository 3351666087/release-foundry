import {
  BROWSER_SESSION_CAPABILITY_MANIFEST,
  BROWSER_SESSION_OPENAPI_DOCUMENT,
} from "./browser-session-openapi.generated.js";

export const BROWSER_SESSION_SCHEMA_VERSION = "releasefoundry.browser_session.v1";
export const BROWSER_SESSION_OPENAPI_SCHEMA_VERSION = "releasefoundry.browser_session.openapi.v1";
export const BROWSER_SESSION_CAPABILITY_SCHEMA_VERSION = "releasefoundry.browser_session.capabilities.v1";
export const BROWSER_SESSION_OPENAPI_VERSION = "3.1.0";
export const BROWSER_SESSION_COOKIE_NAMES = ["__Host-releasefoundry_session", "__Host-releasefoundry_refresh"] as const;
export const BROWSER_SESSION_MODALITIES = ["text", "image", "audio", "file", "video"] as const;
export const BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS = 24 * 60 * 60;
export const BROWSER_SESSION_REFRESH_MAX_AGE_SECONDS = 90 * 24 * 60 * 60;

export const BROWSER_SESSION_ERROR_CODES = [
  "browser_session_authentication_required",
  "browser_session_cookie_expired",
  "browser_session_idempotency_conflict",
  "browser_session_invalid_request",
  "browser_session_rate_limited",
  "browser_session_response_invalid",
  "browser_session_transport_failed",
  "browser_session_unavailable",
  "credential_link_conflict",
  "identity_session_handoff_failed",
  "identity_session_refresh_idempotency_required",
  "identity_session_refresh_invalid",
  "identity_session_refresh_origin_rejected",
  "identity_session_refresh_request_invalid",
  "identity_session_refresh_reused",
  "identity_session_refresh_unavailable",
  "identity_session_secure_transport_required",
  "identity_session_transport_unavailable",
  "identity_verification_failed",
  "identity_verification_policy_unavailable",
  "identity_verification_unavailable",
  "request_cancelled",
  "verification_code_invalid",
  "verification_consumed",
  "verification_expired",
  "verification_not_found",
  "verification_resend_cooldown",
] as const;

export type BrowserSessionErrorCode = typeof BROWSER_SESSION_ERROR_CODES[number];
export type BrowserSessionOperation = "complete_login" | "bootstrap" | "refresh" | "logout" | "revoke_all";
export type BrowserSessionModality = typeof BROWSER_SESSION_MODALITIES[number];

interface ErrorDetail {
  readonly status: number;
  readonly retryable: boolean;
  readonly message: string;
}

const ERROR_DETAILS: Readonly<Record<BrowserSessionErrorCode, ErrorDetail>> = Object.freeze({
  browser_session_authentication_required: { status: 401, retryable: false, message: "browser session authentication is required" },
  browser_session_cookie_expired: { status: 401, retryable: false, message: "browser session cookie has expired" },
  browser_session_idempotency_conflict: { status: 409, retryable: false, message: "idempotency key conflicts with an earlier request" },
  browser_session_invalid_request: { status: 400, retryable: false, message: "browser session request is invalid" },
  browser_session_rate_limited: { status: 429, retryable: true, message: "browser session request was rate limited" },
  browser_session_response_invalid: { status: 502, retryable: true, message: "browser session response is invalid" },
  browser_session_transport_failed: { status: 502, retryable: true, message: "browser session transport failed" },
  browser_session_unavailable: { status: 503, retryable: true, message: "browser session service is unavailable" },
  credential_link_conflict: { status: 409, retryable: false, message: "credential is already linked" },
  identity_session_handoff_failed: { status: 500, retryable: true, message: "identity session handoff failed" },
  identity_session_refresh_idempotency_required: { status: 400, retryable: false, message: "identity session refresh requires a valid idempotency key" },
  identity_session_refresh_invalid: { status: 401, retryable: false, message: "identity session refresh could not be authenticated" },
  identity_session_refresh_origin_rejected: { status: 403, retryable: false, message: "identity session refresh origin was rejected" },
  identity_session_refresh_request_invalid: { status: 400, retryable: false, message: "identity session refresh request is invalid" },
  identity_session_refresh_reused: { status: 409, retryable: false, message: "identity session refresh credential was reused" },
  identity_session_refresh_unavailable: { status: 503, retryable: true, message: "identity session refresh is not configured" },
  identity_session_secure_transport_required: { status: 426, retryable: false, message: "identity session requires HTTPS" },
  identity_session_transport_unavailable: { status: 503, retryable: true, message: "identity session handoff is not configured" },
  identity_verification_failed: { status: 500, retryable: true, message: "identity verification failed" },
  identity_verification_policy_unavailable: { status: 503, retryable: true, message: "identity verification policy is unavailable" },
  identity_verification_unavailable: { status: 503, retryable: true, message: "identity verification is unavailable" },
  request_cancelled: { status: 408, retryable: true, message: "browser session request was cancelled" },
  verification_code_invalid: { status: 401, retryable: false, message: "identity verification proof is invalid" },
  verification_consumed: { status: 401, retryable: false, message: "identity verification proof is invalid" },
  verification_expired: { status: 401, retryable: false, message: "identity verification proof has expired" },
  verification_not_found: { status: 401, retryable: false, message: "identity verification proof is invalid" },
  verification_resend_cooldown: { status: 429, retryable: true, message: "identity verification is rate limited" },
});

const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$/u;
const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{7,254}$/u;
const SUCCESS_STATUSES: Readonly<Record<BrowserSessionOperation, ReadonlySet<number>>> = Object.freeze({
  complete_login: new Set([200, 303]),
  bootstrap: new Set([200, 204]),
  refresh: new Set([200, 204]),
  logout: new Set([204]),
  revoke_all: new Set([204]),
});
const OPERATION_STATUS: Readonly<Record<BrowserSessionOperation, string>> = Object.freeze({
  complete_login: "authenticated",
  bootstrap: "active",
  refresh: "rotated",
  logout: "logged_out",
  revoke_all: "revoked_all",
});

export class BrowserSessionError extends Error {
  readonly code: BrowserSessionErrorCode;
  readonly status: number;
  readonly retryable: boolean;
  readonly retryAfterSeconds: number | null;

  constructor(code: string, options: { status?: number; retryAfterSeconds?: number | null } = {}) {
    const normalized = isErrorCode(code) ? code : "browser_session_transport_failed";
    const detail = ERROR_DETAILS[normalized];
    super(detail.message);
    this.name = "BrowserSessionError";
    this.code = normalized;
    this.status = options.status ?? detail.status;
    this.retryable = detail.retryable;
    this.retryAfterSeconds = optionalRetryAfter(options.retryAfterSeconds ?? null);
  }

  toJSON(): Record<string, unknown> {
    return {
      schema_version: BROWSER_SESSION_SCHEMA_VERSION,
      status: "error",
      error: {
        code: this.code,
        message: this.message,
        http_status: this.status,
        retryable: this.retryable,
        retry_after_seconds: this.retryAfterSeconds,
      },
    };
  }

  override toString(): string {
    return `${this.name}(code=${this.code}, status=${this.status}, retryable=${this.retryable})`;
  }
}

export type BrowserHTTPResponseBody =
  | Uint8Array
  | string
  | Readonly<Record<string, unknown>>
  | null;

export type BrowserHTTPResponseHeaders =
  | Headers
  | Readonly<Record<string, string | readonly string[]>>
  | readonly (readonly [string, string])[];

export class BrowserHTTPResponse {
  readonly status: number;
  readonly headers: readonly (readonly [string, string])[];
  readonly body: BrowserHTTPResponseBody;

  constructor(
    status: number,
    headers: BrowserHTTPResponseHeaders = [],
    body: BrowserHTTPResponseBody = null,
  ) {
    if (!Number.isSafeInteger(status) || status < 100 || status > 599) {
      throw failure("browser_session_response_invalid");
    }
    this.status = status;
    this.headers = Object.freeze(normalizeResponseHeaders(headers));
    this.body = normalizeResponseBody(body);
    Object.freeze(this);
  }

  static create(
    status: number,
    options: {
      readonly headers?: BrowserHTTPResponseHeaders;
      readonly body?: BrowserHTTPResponseBody;
    } = {},
  ): BrowserHTTPResponse {
    return new BrowserHTTPResponse(status, options.headers, options.body);
  }

  headerValues(name: string): readonly string[] {
    const normalized = normalizeHeaderName(name);
    return this.headers
      .filter(([key]) => key.toLowerCase() === normalized)
      .map(([, value]) => value);
  }

  header_values(name: string): readonly string[] {
    return this.headerValues(name);
  }

  toHeaders(): Headers {
    const headers = new Headers();
    for (const [name, value] of this.headers) headers.append(name, value);
    return headers;
  }
}

export interface BrowserCookieDescriptorDTO {
  readonly name: typeof BROWSER_SESSION_COOKIE_NAMES[number];
  readonly expires_at: string;
  readonly max_age_seconds: number;
  readonly path: "/";
  readonly secure: true;
  readonly http_only: true;
  readonly same_site: "Strict";
  readonly host_only: true;
  readonly credential_present: true;
}

export class BrowserCookieDescriptor {
  readonly name: typeof BROWSER_SESSION_COOKIE_NAMES[number];
  readonly expiresAt: Date;
  readonly maxAgeSeconds: number;

  constructor(name: string, expiresAt: Date | string, maxAgeSeconds: number) {
    if (!isCookieName(name)) throw failure("browser_session_invalid_request");
    this.name = name;
    this.expiresAt = parseDate("expires_at", expiresAt);
    this.maxAgeSeconds = boundedInteger("max_age_seconds", maxAgeSeconds, 0, BROWSER_SESSION_REFRESH_MAX_AGE_SECONDS);
  }

  toJSON(): BrowserCookieDescriptorDTO {
    return {
      name: this.name,
      expires_at: timestamp(this.expiresAt),
      max_age_seconds: this.maxAgeSeconds,
      path: "/",
      secure: true,
      http_only: true,
      same_site: "Strict",
      host_only: true,
      credential_present: true,
    };
  }
}

export interface BrowserCookieReplacementDTO {
  readonly schema_version: typeof BROWSER_SESSION_SCHEMA_VERSION;
  readonly issued_at: string;
  readonly replayed_at: string | null;
  readonly cookies: readonly BrowserCookieDescriptorDTO[];
  readonly replacement_is_atomic: true;
  readonly expires_is_stable_across_replay: true;
  readonly max_age_decreases_with_elapsed_seconds: true;
  readonly contains_credential_values: false;
}

export class BrowserCookieReplacement {
  readonly issuedAt: Date;
  readonly access: BrowserCookieDescriptor;
  readonly refresh: BrowserCookieDescriptor;
  readonly replayedAt: Date | null;

  constructor(options: {
    issuedAt: Date | string;
    access: BrowserCookieDescriptor;
    refresh: BrowserCookieDescriptor;
    replayedAt?: Date | string | null;
  }) {
    this.issuedAt = parseDate("issued_at", options.issuedAt);
    this.access = options.access;
    this.refresh = options.refresh;
    this.replayedAt = options.replayedAt === undefined || options.replayedAt === null
      ? null
      : parseDate("replayed_at", options.replayedAt);
  }

  replay(replayedAt: Date | string): BrowserCookieReplacement {
    const replay = parseDate("replayed_at", replayedAt);
    if (replay.getTime() < this.issuedAt.getTime()) throw failure("browser_session_invalid_request");
    return new BrowserCookieReplacement({
      issuedAt: this.issuedAt,
      access: replayedDescriptor(this.access, replay),
      refresh: replayedDescriptor(this.refresh, replay),
      replayedAt: replay,
    });
  }

  toJSON(): BrowserCookieReplacementDTO {
    return {
      schema_version: BROWSER_SESSION_SCHEMA_VERSION,
      issued_at: timestamp(this.issuedAt),
      replayed_at: this.replayedAt === null ? null : timestamp(this.replayedAt),
      cookies: [this.access.toJSON(), this.refresh.toJSON()],
      replacement_is_atomic: true,
      expires_is_stable_across_replay: true,
      max_age_decreases_with_elapsed_seconds: true,
      contains_credential_values: false,
    };
  }
}

export interface BuildBrowserCookieReplacementOptions {
  readonly issuedAt: Date | string;
  readonly accessExpiresAt: Date | string;
  readonly refreshExpiresAt: Date | string;
  readonly accessCapSeconds?: number;
  readonly refreshCapSeconds?: number;
}

export function buildBrowserCookieReplacement(options: BuildBrowserCookieReplacementOptions): BrowserCookieReplacement {
  const issuedAt = parseDate("issued_at", options.issuedAt);
  const accessExpiresAt = parseDate("access_expires_at", options.accessExpiresAt);
  const refreshExpiresAt = parseDate("refresh_expires_at", options.refreshExpiresAt);
  const accessCap = boundedInteger(
    "access_cap_seconds",
    options.accessCapSeconds ?? BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS,
    1,
    BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS,
  );
  const refreshCap = boundedInteger(
    "refresh_cap_seconds",
    options.refreshCapSeconds ?? 30 * 24 * 60 * 60,
    1,
    BROWSER_SESSION_REFRESH_MAX_AGE_SECONDS,
  );
  const effectiveAccess = new Date(Math.min(accessExpiresAt.getTime(), issuedAt.getTime() + accessCap * 1000));
  const effectiveRefresh = new Date(Math.min(refreshExpiresAt.getTime(), issuedAt.getTime() + refreshCap * 1000));
  const accessMaxAge = Math.floor((effectiveAccess.getTime() - issuedAt.getTime()) / 1000);
  const refreshMaxAge = Math.floor((effectiveRefresh.getTime() - issuedAt.getTime()) / 1000);
  if (accessMaxAge < 1 || refreshMaxAge < 1 || effectiveRefresh.getTime() <= effectiveAccess.getTime()) {
    throw failure("browser_session_invalid_request");
  }
  return new BrowserCookieReplacement({
    issuedAt,
    access: new BrowserCookieDescriptor(BROWSER_SESSION_COOKIE_NAMES[0], effectiveAccess, accessMaxAge),
    refresh: new BrowserCookieDescriptor(BROWSER_SESSION_COOKIE_NAMES[1], effectiveRefresh, refreshMaxAge),
  });
}

interface StoredCookie {
  readonly value: string;
  readonly expiresAt: Date;
}

const ingestCookies = Symbol("ingestCookies");
const requestCookieHeader = Symbol("requestCookieHeader");

export interface BrowserSessionCookieJarSnapshot {
  readonly schema_version: typeof BROWSER_SESSION_SCHEMA_VERSION;
  readonly management: "sdk_cookie_jar";
  readonly origin: string;
  readonly cookie_count: number;
  readonly access_credential_present: boolean;
  readonly refresh_credential_present: boolean;
  readonly credential_values_exposed: false;
}

export class BrowserSessionCookieJar {
  readonly #origin: string;
  readonly #cookies = new Map<typeof BROWSER_SESSION_COOKIE_NAMES[number], StoredCookie>();

  constructor(origin: string) {
    this.#origin = normalizeOrigin(origin, true);
  }

  clear(): void {
    this.#cookies.clear();
  }

  snapshot(now: Date | string = new Date()): BrowserSessionCookieJarSnapshot {
    this.#discardExpired(parseDate("now", now));
    return {
      schema_version: BROWSER_SESSION_SCHEMA_VERSION,
      management: "sdk_cookie_jar",
      origin: this.#origin,
      cookie_count: this.#cookies.size,
      access_credential_present: this.#cookies.has(BROWSER_SESSION_COOKIE_NAMES[0]),
      refresh_credential_present: this.#cookies.has(BROWSER_SESSION_COOKIE_NAMES[1]),
      credential_values_exposed: false,
    };
  }

  toJSON(): BrowserSessionCookieJarSnapshot {
    return this.snapshot();
  }

  toString(): string {
    const snapshot = this.snapshot();
    return `BrowserSessionCookieJar(origin=${snapshot.origin}, cookie_count=${snapshot.cookie_count}, credential_values_exposed=false)`;
  }

  [ingestCookies](headers: Headers, now = new Date()): BrowserCookieDescriptor[] {
    const current = parseDate("now", now);
    const descriptors: BrowserCookieDescriptor[] = [];
    for (const header of setCookieHeaders(headers)) {
      const parsed = parseSetCookie(header, current);
      if (parsed === null) continue;
      if (parsed.stored === null) {
        this.#cookies.delete(parsed.name);
        continue;
      }
      this.#cookies.set(parsed.name, parsed.stored);
      descriptors.push(parsed.descriptor);
    }
    this.#discardExpired(current);
    return descriptors;
  }

  [requestCookieHeader](url: string, now = new Date()): string | undefined {
    if (originFromUrl(url) !== this.#origin) throw failure("browser_session_invalid_request");
    this.#discardExpired(parseDate("now", now));
    const values: string[] = [];
    for (const name of BROWSER_SESSION_COOKIE_NAMES) {
      const stored = this.#cookies.get(name);
      if (stored !== undefined) values.push(`${name}=${stored.value}`);
    }
    return values.length === 0 ? undefined : values.join("; ");
  }

  matchesOrigin(origin: string): boolean {
    return this.#origin === origin;
  }

  #discardExpired(now: Date): void {
    for (const [name, stored] of this.#cookies.entries()) {
      if (stored.expiresAt.getTime() <= now.getTime()) this.#cookies.delete(name);
    }
  }
}

export interface BrowserSessionReceiptDTO {
  readonly schema_version: typeof BROWSER_SESSION_SCHEMA_VERSION;
  readonly operation: BrowserSessionOperation;
  readonly http_status: number;
  readonly status: string;
  readonly redirect_to: string | null;
  readonly cookie_state: BrowserSessionCookieJarSnapshot | {
    readonly management: "browser";
    readonly credential_values_exposed: false;
  };
  readonly replacement_cookies: readonly BrowserCookieDescriptorDTO[];
  readonly credential_values_exposed: false;
}

export class BrowserSessionReceipt {
  readonly operation: BrowserSessionOperation;
  readonly httpStatus: number;
  readonly status: string;
  readonly redirectTo: string | null;
  readonly cookieState: BrowserSessionReceiptDTO["cookie_state"];
  readonly replacementCookies: readonly BrowserCookieDescriptor[];

  constructor(options: {
    operation: BrowserSessionOperation;
    httpStatus: number;
    status: string;
    redirectTo: string | null;
    cookieState: BrowserSessionReceiptDTO["cookie_state"];
    replacementCookies?: readonly BrowserCookieDescriptor[];
  }) {
    this.operation = options.operation;
    this.httpStatus = options.httpStatus;
    this.status = options.status;
    this.redirectTo = options.redirectTo;
    this.cookieState = options.cookieState;
    this.replacementCookies = [...(options.replacementCookies ?? [])];
  }

  toJSON(): BrowserSessionReceiptDTO {
    return {
      schema_version: BROWSER_SESSION_SCHEMA_VERSION,
      operation: this.operation,
      http_status: this.httpStatus,
      status: this.status,
      redirect_to: this.redirectTo,
      cookie_state: this.cookieState,
      replacement_cookies: this.replacementCookies.map((cookie) => cookie.toJSON()),
      credential_values_exposed: false,
    };
  }
}

export interface BrowserSessionClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof fetch;
  readonly cookieJar?: BrowserSessionCookieJar;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
  readonly allowInsecureLocalhost?: boolean;
}

export interface BrowserSessionScope {
  readonly projectId: string;
  readonly accountId: string;
}

export interface BrowserSessionIdempotentScope extends BrowserSessionScope {
  readonly idempotencyKey: string;
}

export interface BrowserSessionLoginOptions {
  readonly tenantId: string;
  readonly accountId: string;
  readonly challengeId: string;
  readonly verificationCode: string;
  readonly channel: "email" | "phone" | string;
  readonly identifier: string;
  readonly displayName?: string;
}

export class BrowserSessionClient {
  readonly #origin: string;
  readonly #fetch: typeof fetch;
  readonly #cookieJar: BrowserSessionCookieJar | undefined;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;

  constructor(options: BrowserSessionClientOptions) {
    this.#origin = normalizeOrigin(options.baseUrl, options.allowInsecureLocalhost === true);
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#cookieJar = options.cookieJar;
    if (this.#cookieJar !== undefined && !this.#cookieJar.matchesOrigin(this.#origin)) {
      throw failure("browser_session_invalid_request");
    }
    this.#timeoutMs = boundedInteger("timeout_ms", options.timeoutMs ?? 30_000, 1, 300_000);
    this.#signal = options.signal;
  }

  completeLogin(options: BrowserSessionLoginOptions): Promise<BrowserSessionReceipt> {
    const channel = options.channel.trim().toLowerCase();
    if (channel !== "email" && channel !== "phone") throw failure("browser_session_invalid_request");
    const code = String(options.verificationCode);
    const identifier = String(options.identifier).trim();
    if (code.length < 1 || code.length > 1024 || code.includes("\0") || identifier.length < 1 || identifier.length > 512) {
      throw failure("browser_session_invalid_request");
    }
    const displayName = options.displayName?.trim();
    if (options.displayName !== undefined && (displayName === undefined || displayName.length < 1 || displayName.length > 255)) {
      throw failure("browser_session_invalid_request");
    }
    return this.#request("complete_login", "POST", browserSessionLoginRoute(), {
      tenant_id: identifierValue("tenant_id", options.tenantId),
      account_id: identifierValue("account_id", options.accountId),
      challenge_id: identifierValue("challenge_id", options.challengeId),
      code,
      channel,
      identifier,
      purpose: "login",
      ...(displayName === undefined ? {} : { display_name: displayName }),
    });
  }

  loginAndBootstrapSession(options: BrowserSessionLoginOptions): Promise<BrowserSessionReceipt> {
    return this.completeLogin(options);
  }

  bootstrap(options: BrowserSessionScope): Promise<BrowserSessionReceipt> {
    return this.#request("bootstrap", "GET", browserSessionBootstrapRoute(options.projectId, options.accountId));
  }

  refresh(options: BrowserSessionIdempotentScope): Promise<BrowserSessionReceipt> {
    return this.#request(
      "refresh",
      "POST",
      secureBrowserSessionRefreshRoute(options.projectId, options.accountId),
      undefined,
      options.idempotencyKey,
    );
  }

  logout(options: BrowserSessionIdempotentScope): Promise<BrowserSessionReceipt> {
    return this.#request(
      "logout",
      "POST",
      browserSessionLogoutRoute(options.projectId, options.accountId),
      undefined,
      options.idempotencyKey,
    );
  }

  revokeAll(options: BrowserSessionIdempotentScope): Promise<BrowserSessionReceipt> {
    return this.#request(
      "revoke_all",
      "POST",
      browserSessionRevokeAllRoute(options.projectId, options.accountId),
      undefined,
      options.idempotencyKey,
    );
  }

  revokeAllSessions(options: BrowserSessionIdempotentScope): Promise<BrowserSessionReceipt> {
    return this.revokeAll(options);
  }

  async #request(
    operation: BrowserSessionOperation,
    method: "GET" | "POST",
    path: string,
    payload?: Record<string, unknown>,
    rawIdempotencyKey?: string,
  ): Promise<BrowserSessionReceipt> {
    const url = `${this.#origin}${path}`;
    const headers = new Headers({
      accept: "application/json",
      "cache-control": "no-store",
      origin: this.#origin,
      pragma: "no-cache",
      "sec-fetch-site": "same-origin",
    });
    let body: string | undefined;
    if (payload !== undefined) {
      headers.set("content-type", "application/json");
      body = JSON.stringify(payload);
    }
    if (rawIdempotencyKey !== undefined) headers.set("idempotency-key", idempotencyKey(rawIdempotencyKey));
    const cookie = this.#cookieJar?.[requestCookieHeader](url);
    if (cookie !== undefined) headers.set("cookie", cookie);

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#timeoutMs);
    const abortFromCaller = () => controller.abort();
    this.#signal?.addEventListener("abort", abortFromCaller, { once: true });
    try {
      if (this.#signal?.aborted) controller.abort();
      const response = await this.#fetch(url, {
        method,
        headers,
        body,
        credentials: "include",
        redirect: "manual",
        cache: "no-store",
        signal: controller.signal,
      });
      const replacement = this.#cookieJar?.[ingestCookies](response.headers) ?? [];
      if (!SUCCESS_STATUSES[operation].has(response.status)) throw await errorFromResponse(response);
      if (operation === "logout" || operation === "revoke_all") this.#cookieJar?.clear();
      let redirectTo: string | null = null;
      if (response.status === 303) redirectTo = safeRedirect(this.#origin, singleHeader(response.headers, "location", true));
      await validateSuccessBody(operation, response);
      return new BrowserSessionReceipt({
        operation,
        httpStatus: response.status,
        status: OPERATION_STATUS[operation],
        redirectTo,
        cookieState: this.#cookieJar?.snapshot() ?? { management: "browser", credential_values_exposed: false },
        replacementCookies: replacement,
      });
    } catch (error) {
      if (error instanceof BrowserSessionError) throw error;
      if (timedOut || controller.signal.aborted) throw failure("request_cancelled");
      throw failure("browser_session_transport_failed");
    } finally {
      clearTimeout(timer);
      this.#signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}

export function browserSessionLoginRoute(): string {
  return "/v1/identity-verification/verify";
}

export function browserSessionCollectionRoute(projectId: string, accountId: string): string {
  return `/v1/projects/${routeSegment("project_id", projectId)}/accounts/${routeSegment("account_id", accountId)}/browser-sessions`;
}

export function browserSessionBootstrapRoute(projectId: string, accountId: string): string {
  return `${browserSessionCollectionRoute(projectId, accountId)}/bootstrap`;
}

export function secureBrowserSessionRefreshRoute(projectId: string, accountId: string): string {
  return `${browserSessionCollectionRoute(projectId, accountId)}/refresh`;
}

export function browserSessionLogoutRoute(projectId: string, accountId: string): string {
  return `${browserSessionCollectionRoute(projectId, accountId)}/logout`;
}

export function browserSessionRevokeAllRoute(projectId: string, accountId: string): string {
  return `${browserSessionCollectionRoute(projectId, accountId)}/revoke-all`;
}

export function browserSessionCapabilityManifest(): Record<string, unknown> {
  return clonePublic(BROWSER_SESSION_CAPABILITY_MANIFEST);
}

export function browserSessionOpenApiDocument(): Record<string, unknown> {
  return clonePublic(BROWSER_SESSION_OPENAPI_DOCUMENT);
}

export const build_browser_cookie_replacement = buildBrowserCookieReplacement;
export const browser_session_bootstrap_route = browserSessionBootstrapRoute;
export const browser_session_capability_manifest = browserSessionCapabilityManifest;
export const browser_session_collection_route = browserSessionCollectionRoute;
export const browser_session_login_route = browserSessionLoginRoute;
export const browser_session_logout_route = browserSessionLogoutRoute;
export const browser_session_openapi_document = browserSessionOpenApiDocument;
export const secure_browser_session_refresh_route = secureBrowserSessionRefreshRoute;
export const browser_session_revoke_all_route = browserSessionRevokeAllRoute;

function failure(code: BrowserSessionErrorCode, options: { status?: number; retryAfterSeconds?: number | null } = {}): BrowserSessionError {
  return new BrowserSessionError(code, options);
}

function isErrorCode(value: string): value is BrowserSessionErrorCode {
  return (BROWSER_SESSION_ERROR_CODES as readonly string[]).includes(value);
}

function isCookieName(value: string): value is typeof BROWSER_SESSION_COOKIE_NAMES[number] {
  return (BROWSER_SESSION_COOKIE_NAMES as readonly string[]).includes(value);
}

function parseDate(_name: string, value: Date | string): Date {
  const parsed = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!Number.isFinite(parsed.getTime()) || (typeof value === "string" && !/(?:Z|[+-]\d{2}:\d{2})$/u.test(value))) {
    throw failure("browser_session_invalid_request");
  }
  return parsed;
}

function timestamp(value: Date): string {
  return value.toISOString().replace(".000Z", "Z");
}

function boundedInteger(_name: string, value: number, minimum: number, maximum: number): number {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) throw failure("browser_session_invalid_request");
  return value;
}

function replayedDescriptor(descriptor: BrowserCookieDescriptor, replayedAt: Date): BrowserCookieDescriptor {
  const maxAge = Math.floor((descriptor.expiresAt.getTime() - replayedAt.getTime()) / 1000);
  if (maxAge < 1) throw failure("browser_session_cookie_expired");
  return new BrowserCookieDescriptor(descriptor.name, descriptor.expiresAt, maxAge);
}

function normalizeOrigin(value: string, allowInsecureLocalhost: boolean): string {
  let url: URL;
  try {
    url = new URL(String(value).trim());
  } catch {
    throw failure("browser_session_invalid_request");
  }
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "[::1]" || url.hostname === "::1";
  if (url.username || url.password || url.search || url.hash || (url.pathname !== "/" && url.pathname !== "")) {
    throw failure("browser_session_invalid_request");
  }
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local && allowInsecureLocalhost)) {
    throw failure("identity_session_secure_transport_required");
  }
  return url.origin.toLowerCase();
}

function originFromUrl(value: string): string {
  try {
    return new URL(value).origin.toLowerCase();
  } catch {
    throw failure("browser_session_invalid_request");
  }
}

function identifierValue(_name: string, value: string): string {
  const normalized = String(value).trim();
  if (!IDENTIFIER_PATTERN.test(normalized)) throw failure("browser_session_invalid_request");
  return normalized;
}

function routeSegment(name: string, value: string): string {
  return encodeURIComponent(identifierValue(name, value));
}

function idempotencyKey(value: string): string {
  const normalized = String(value);
  if (normalized !== normalized.trim() || !IDEMPOTENCY_PATTERN.test(normalized)) throw failure("browser_session_invalid_request");
  return normalized;
}

function setCookieHeaders(headers: Headers): string[] {
  const getter = (headers as Headers & { getSetCookie?: () => string[] }).getSetCookie;
  if (typeof getter === "function") {
    return getter.call(headers).flatMap(splitCombinedSetCookieHeader);
  }
  const combined = headers.get("set-cookie");
  if (combined === null) return [];
  return splitCombinedSetCookieHeader(combined);
}

function splitCombinedSetCookieHeader(value: string): string[] {
  return value.split(/,\s*(?=__Host-releasefoundry_(?:session|refresh)=)/u);
}

function parseSetCookie(header: string, now: Date): {
  name: typeof BROWSER_SESSION_COOKIE_NAMES[number];
  stored: StoredCookie | null;
  descriptor: BrowserCookieDescriptor;
} | null {
  const parts = header.split(";").map((part) => part.trim());
  const first = parts.shift();
  if (first === undefined) throw failure("browser_session_response_invalid");
  const separator = first.indexOf("=");
  if (separator < 1) throw failure("browser_session_response_invalid");
  const name = first.slice(0, separator);
  if (!isCookieName(name)) return null;
  const value = first.slice(separator + 1);
  const attributes = new Map<string, string>();
  for (const part of parts) {
    const index = part.indexOf("=");
    const key = (index < 0 ? part : part.slice(0, index)).trim().toLowerCase();
    const item = index < 0 ? "" : part.slice(index + 1).trim();
    if (attributes.has(key)) throw failure("browser_session_response_invalid");
    attributes.set(key, item);
  }
  if (
    attributes.get("path") !== "/" ||
    !attributes.has("secure") ||
    !attributes.has("httponly") ||
    attributes.get("samesite")?.toLowerCase() !== "strict" ||
    attributes.has("domain")
  ) throw failure("browser_session_response_invalid");
  const maxAgeText = attributes.get("max-age");
  if (maxAgeText === undefined || !/^-?\d+$/u.test(maxAgeText)) throw failure("browser_session_response_invalid");
  const maxAge = Number(maxAgeText);
  if (!Number.isSafeInteger(maxAge)) throw failure("browser_session_response_invalid");
  if (maxAge <= 0) {
    return { name, stored: null, descriptor: new BrowserCookieDescriptor(name, now, 0) };
  }
  if (value.length < 1 || value.length > 8192) throw failure("browser_session_response_invalid");
  const expiresText = attributes.get("expires");
  if (expiresText === undefined) throw failure("browser_session_response_invalid");
  const expiresAt = new Date(expiresText);
  if (!Number.isFinite(expiresAt.getTime())) throw failure("browser_session_response_invalid");
  const expected = now.getTime() + maxAge * 1000;
  if (Math.abs(expiresAt.getTime() - expected) > 1000) throw failure("browser_session_response_invalid");
  return {
    name,
    stored: { value, expiresAt },
    descriptor: new BrowserCookieDescriptor(name, expiresAt, maxAge),
  };
}

function singleHeader(headers: Headers, name: string, required = false): string | null {
  const value = headers.get(name);
  if (required && (value === null || value.trim() === "")) throw failure("browser_session_response_invalid");
  return value;
}

function safeRedirect(origin: string, location: string | null): string {
  if (location === null || location.trim() !== location || location === "") throw failure("browser_session_response_invalid");
  let resolved: URL;
  try {
    resolved = new URL(location, `${origin}/`);
  } catch {
    throw failure("browser_session_response_invalid");
  }
  if (resolved.origin.toLowerCase() !== origin || resolved.username || resolved.password) throw failure("browser_session_response_invalid");
  return `${resolved.pathname}${resolved.search}`;
}

async function parseResponseRecord(response: Response): Promise<Record<string, unknown> | null> {
  const text = await response.text();
  if (text === "") return null;
  if (new TextEncoder().encode(text).length > 1_048_576) throw failure("browser_session_response_invalid");
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw failure("browser_session_response_invalid");
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw failure("browser_session_response_invalid");
  return value as Record<string, unknown>;
}

async function validateSuccessBody(operation: BrowserSessionOperation, response: Response): Promise<void> {
  const payload = await parseResponseRecord(response);
  if (response.status === 204 || response.status === 303) {
    if (payload !== null) throw failure("browser_session_response_invalid");
    return;
  }
  if (payload === null) throw failure("browser_session_response_invalid");
  if (operation === "refresh" && payload.status !== "rotated") throw failure("browser_session_response_invalid");
}

async function errorFromResponse(response: Response): Promise<BrowserSessionError> {
  let code: BrowserSessionErrorCode = "browser_session_transport_failed";
  try {
    const payload = await parseResponseRecord(response);
    const error = payload?.error;
    if (error !== null && typeof error === "object" && !Array.isArray(error)) {
      const candidate = (error as Record<string, unknown>).code;
      if (typeof candidate === "string" && isErrorCode(candidate)) code = candidate;
    }
  } catch {
    code = "browser_session_transport_failed";
  }
  if (code === "browser_session_transport_failed") {
    code = ({
      401: "browser_session_authentication_required",
      409: "browser_session_idempotency_conflict",
      429: "browser_session_rate_limited",
      503: "browser_session_unavailable",
    } as Readonly<Record<number, BrowserSessionErrorCode>>)[response.status] ?? code;
  }
  const retryHeader = response.headers.get("retry-after");
  const retryAfter = retryHeader !== null && /^\d+$/u.test(retryHeader) ? Number(retryHeader) : null;
  return new BrowserSessionError(code, { status: response.status, retryAfterSeconds: retryAfter });
}

function optionalRetryAfter(value: number | null): number | null {
  return value !== null && Number.isSafeInteger(value) && value >= 1 ? Math.min(value, 86_400) : null;
}

function normalizeHeaderName(value: string): string {
  const normalized = String(value).trim().toLowerCase();
  if (normalized === "" || !/^[!#$%&'*+\-.^_`|~0-9a-z]+$/u.test(normalized)) {
    throw failure("browser_session_response_invalid");
  }
  return normalized;
}

function normalizeHeaderValue(value: string): string {
  const normalized = String(value).trim();
  if (/[\0\r\n]/u.test(normalized)) throw failure("browser_session_response_invalid");
  return normalized;
}

function normalizeResponseHeaders(
  value: BrowserHTTPResponseHeaders,
): (readonly [string, string])[] {
  const normalized: (readonly [string, string])[] = [];
  const append = (name: string, item: string): void => {
    normalized.push(Object.freeze([
      normalizeHeaderName(name),
      normalizeHeaderValue(item),
    ]) as readonly [string, string]);
  };
  if (value instanceof Headers) {
    const getSetCookie = (value as Headers & { getSetCookie?: () => string[] }).getSetCookie;
    const setCookies = typeof getSetCookie === "function" ? getSetCookie.call(value) : [];
    value.forEach((item, name) => {
      if (name.toLowerCase() !== "set-cookie" || setCookies.length === 0) append(name, item);
    });
    for (const item of setCookies) append("set-cookie", item);
    return normalized;
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      if (!Array.isArray(entry) || entry.length !== 2) throw failure("browser_session_response_invalid");
      append(String(entry[0]), String(entry[1]));
    }
    return normalized;
  }
  for (const [name, items] of Object.entries(value)) {
    if (Array.isArray(items)) {
      for (const item of items) append(name, String(item));
    } else {
      append(name, String(items));
    }
  }
  return normalized;
}

function normalizeResponseBody(body: BrowserHTTPResponseBody): BrowserHTTPResponseBody {
  if (body === null || typeof body === "string") return body;
  // Node does not permit freezing non-empty typed-array views. A detached copy
  // still provides the immutable snapshot boundary promised by this DTO.
  if (body instanceof Uint8Array) return body.slice();
  if (typeof body !== "object" || Array.isArray(body)) throw failure("browser_session_response_invalid");
  return Object.freeze({ ...body });
}

function clonePublic<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
