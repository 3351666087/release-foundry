import {
  OAuthProviderContractError,
  hashOAuthNonce,
  normalizeOAuthProvider,
  verifyCallbackIdentity,
} from "./oauth.js";

export const ACCOUNT_CONNECTION_SCHEMA_VERSION = "releasefoundry.account_connection.v1";
export const ACCOUNT_CONNECTION_PROVIDERS = ["github", "google"] as const;
export const ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS = [
  "github",
  "google",
  "wechat",
  "qq",
  "alipay",
  "phone",
  "email",
] as const;
export const ACCOUNT_CONNECTION_EXACT_SCOPES = {
  github: ["read:user", "user:email"],
  google: ["openid", "email", "profile"],
} as const;
export const GOOGLE_ACCOUNT_CONNECTION_ISSUERS = [
  "https://accounts.google.com",
  "accounts.google.com",
] as const;
export const ACCOUNT_CONNECTION_ERROR_CODES = [
  "invalid_oauth_binding",
  "invalid_oauth_callback",
  "invalid_oauth_state",
  "oauth_binding_mismatch",
  "oauth_connection_not_found",
  "oauth_credentials_unavailable",
  "oauth_provider_error",
  "oauth_provider_revoke_failed",
  "oauth_reconnect_revoke_failed",
  "oauth_secret_store_failed",
  "oauth_secret_resolve_failed",
  "oauth_secret_delete_failed",
  "oauth_connection_store_failed",
  "oauth_disconnect_failed",
  "oidc_issuer_mismatch",
  "oidc_audience_mismatch",
  "oidc_nonce_mismatch",
  "oauth_email_unverified",
] as const;

export type AccountConnectionProvider = (typeof ACCOUNT_CONNECTION_PROVIDERS)[number];
export type AccountConnectionStableErrorCode = (typeof ACCOUNT_CONNECTION_ERROR_CODES)[number];
export type AccountConnectionFetch = typeof fetch;
export type AccountConnectionStatus = "active" | "revoked" | "disconnected";

export interface AccountConnectionBinding {
  tenant_id: string;
  project_id: string;
  account_id: string;
  provider: AccountConnectionProvider;
}

export interface PublicAccountConnectionStart {
  schema_version: string;
  provider: AccountConnectionProvider;
  authorize_url: string;
  expires_at: string;
}

export interface PublicAccountConnection {
  schema_version: string;
  provider: AccountConnectionProvider;
  account_id: string;
  credential_id: string;
  provider_subject_present: boolean;
  provider_login: string | null;
  email_present: boolean;
  email_verified: boolean;
  connected_at: string;
  disconnected_at: string | null;
}

export interface PublicAccountConnectionDisconnect {
  schema_version: string;
  provider: AccountConnectionProvider;
  disconnected: boolean;
  revocation_status: "revoked" | "not_required" | "pending" | "failed";
  connection: PublicAccountConnection;
}

export interface PublicAccountConnectionError {
  code: AccountConnectionStableErrorCode;
  message: string;
  retryable: boolean;
  provider: AccountConnectionProvider | null;
  revocation_pending: boolean;
}

export interface AccountConnectionRouteDeclaration {
  method: "GET" | "POST";
  path: string;
  operation:
    | "start"
    | "callback"
    | "connection"
    | "disconnect"
    | "session"
    | "identity";
  provider: AccountConnectionProvider;
}

const FORBIDDEN_ACCOUNT_CONNECTION_PUBLIC_KEYS = new Set([
  "access_token",
  "authorization_code",
  "client_secret",
  "code_verifier",
  "email",
  "id_token",
  "nonce",
  "phone",
  "refresh_token",
  "state",
  "provider_subject_sha256",
  "subject_digest",
  "identifier_sha256",
  "token",
  "token_ref",
  "token_ref_id",
  "revocation_outbox_id",
]);
const FORBIDDEN_ACCOUNT_CONNECTION_CANONICAL_KEYS = new Set(
  [...FORBIDDEN_ACCOUNT_CONNECTION_PUBLIC_KEYS].map((key) =>
    key.replace(/[^a-z0-9]/gu, "")
  ),
);

export const ACCOUNT_CONNECTION_ROUTES: readonly AccountConnectionRouteDeclaration[] = Object.freeze(
  ACCOUNT_CONNECTION_PROVIDERS.flatMap((provider) => [
    {
      method: "POST" as const,
      path: `/v1/projects/{project_id}/oauth/${provider}/start`,
      operation: "start" as const,
      provider,
    },
    {
      method: "GET" as const,
      path: `/oauth/${provider}/callback`,
      operation: "callback" as const,
      provider,
    },
    {
      method: "GET" as const,
      path: `/v1/projects/{project_id}/oauth/${provider}/connection`,
      operation: "connection" as const,
      provider,
    },
    {
      method: "POST" as const,
      path: `/v1/projects/{project_id}/oauth/${provider}/disconnect`,
      operation: "disconnect" as const,
      provider,
    },
    {
      method: "GET" as const,
      path: `/v1/oauth/${provider}/session/{session_id}`,
      operation: "session" as const,
      provider,
    },
    {
      method: "GET" as const,
      path: `/v1/oauth/${provider}/account/{session_id}`,
      operation: "identity" as const,
      provider,
    },
  ]),
);

export interface AccountConnectionStartOptions {
  provider: AccountConnectionProvider | string;
  projectId: string;
  tenantId?: string;
  accountId?: string;
  returnTo?: string;
  loginHint?: string;
  allowSignup?: boolean;
}

export interface AccountConnectionCallbackOptions {
  provider: AccountConnectionProvider | string;
  state?: string;
  code?: string;
  error?: string;
  errorDescription?: string;
}

export interface AccountConnectionDisconnectOptions {
  provider: AccountConnectionProvider | string;
  projectId: string;
  sessionId?: string;
  tenantId?: string;
  accountId?: string;
}

export interface AccountConnectionReadOptions {
  provider: AccountConnectionProvider | string;
  projectId: string;
  tenantId: string;
  accountId: string;
}

export interface AccountConnectionStartResult {
  schema_version: typeof ACCOUNT_CONNECTION_SCHEMA_VERSION;
  operation: "oauth_account_connection_start";
  provider: AccountConnectionProvider;
  project_id: string;
  authorization_url: string;
  redirect_uri: string;
  scopes: string[];
  state_sha256: string;
  nonce_sha256: string | null;
  nonce_required: boolean;
  code_challenge_method: "S256";
  expires_at: string;
  token_value_present: false;
  secret_value_present: false;
}

export interface AccountConnectionIdentity {
  provider: AccountConnectionProvider;
  subject_ref: string;
  account_id: string;
  login: string | null;
  display_name: string | null;
  email: string | null;
  email_verified: boolean;
  avatar_url: string | null;
  issuer: string;
  audience: string | string[] | null;
}

export interface AccountConnectionSession {
  schema_version: typeof ACCOUNT_CONNECTION_SCHEMA_VERSION;
  provider: AccountConnectionProvider;
  project_id: string;
  session_id: string;
  status: AccountConnectionStatus;
  account_id: string;
  subject_ref: string;
  granted_scopes: string[];
  access_token_ref_present: boolean;
  refresh_token_ref_present: boolean;
  id_token_ref_present: boolean;
  created_at: string;
  revoked_at: string | null;
  token_value_present: false;
  secret_value_present: false;
}

export interface AccountConnectionCallbackResult {
  schema_version: typeof ACCOUNT_CONNECTION_SCHEMA_VERSION;
  operation: "oauth_account_connection_callback";
  provider: AccountConnectionProvider;
  accepted: true;
  session: AccountConnectionSession;
  identity: AccountConnectionIdentity;
  return_to: string | null;
  state_matches: true;
  replay_accepted: true;
  issuer_matches: boolean;
  audience_matches: boolean;
  nonce_required: boolean;
  nonce_matches: boolean;
  email_verification_required: boolean;
  email_verified: boolean;
  raw_code_present: false;
  raw_state_present: false;
  raw_nonce_present: false;
  token_value_present: false;
  secret_value_present: false;
}

export interface AccountConnectionDisconnectResult {
  schema_version: typeof ACCOUNT_CONNECTION_SCHEMA_VERSION;
  operation: "oauth_account_connection_disconnect";
  provider: AccountConnectionProvider;
  disconnected: boolean;
  already_disconnected: boolean;
  provider_revocation_attempted: boolean;
  provider_revocation_succeeded: boolean;
  session: AccountConnectionSession;
  token_value_present: false;
  secret_value_present: false;
}

export interface AccountConnectionHttpClientOptions {
  baseUrl: string;
  fetch?: AccountConnectionFetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export class AccountConnectionError extends Error {
  readonly code: string;
  readonly status: number;
  readonly provider: AccountConnectionProvider | null;
  readonly retryable: boolean;

  constructor(
    code: string,
    message: string,
    status = 400,
    options: { provider?: AccountConnectionProvider | string; retryable?: boolean } = {},
  ) {
    super(message);
    this.name = "AccountConnectionError";
    this.code = safeErrorCode(code);
    this.status = normalizeStatus(status);
    this.provider = options.provider === undefined ? null : normalizeAccountConnectionProvider(options.provider);
    this.retryable = options.retryable === true;
  }

  toJSON(): Record<string, unknown> {
    return {
      schema_version: ACCOUNT_CONNECTION_SCHEMA_VERSION,
      error: this.code,
      message: this.message,
      status: this.status,
      provider: this.provider,
      retryable: this.retryable,
      provider_response_included: false,
      raw_state_present: false,
      raw_code_present: false,
      raw_nonce_present: false,
      token_value_present: false,
      secret_value_present: false,
    };
  }
}

export class AccountConnectionHttpClient {
  readonly #baseUrl: string;
  readonly #fetch: AccountConnectionFetch;
  readonly #headers: Record<string, string>;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;

  constructor(options: AccountConnectionHttpClientOptions) {
    let baseUrl: URL;
    try {
      baseUrl = new URL(options.baseUrl);
    } catch {
      throw new AccountConnectionError("invalid_base_url", "Account connection base URL is invalid");
    }
    if (!["http:", "https:"].includes(baseUrl.protocol) || baseUrl.username || baseUrl.password) {
      throw new AccountConnectionError("invalid_base_url", "Account connection base URL must be HTTP or HTTPS");
    }
    this.#baseUrl = baseUrl.toString().replace(/\/+$/u, "");
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#headers = { ...(options.headers ?? {}) };
    this.#timeoutMs = normalizeTimeout(options.timeoutMs);
    this.#signal = options.signal;
  }

  start(options: AccountConnectionStartOptions): Promise<AccountConnectionStartResult> {
    const provider = normalizeAccountConnectionProvider(options.provider);
    return this.#request<AccountConnectionStartResult>(
      "POST",
      `/v1/projects/${encodeURIComponent(requireId("project_id", options.projectId))}/oauth/${provider}/start`,
      stripUndefined({
        tenant_id: options.tenantId,
        account_id: options.accountId,
        return_to: options.returnTo,
        login_hint: options.loginHint,
        allow_signup: options.allowSignup,
        scopes: [...ACCOUNT_CONNECTION_EXACT_SCOPES[provider]],
      }),
      provider,
    );
  }

  callback(options: AccountConnectionCallbackOptions): Promise<AccountConnectionCallbackResult> {
    const provider = normalizeAccountConnectionProvider(options.provider);
    const query = new URLSearchParams(stripUndefined({
      state: options.state,
      code: options.code,
      error: options.error,
      error_description: options.errorDescription,
    }) as Record<string, string>);
    return this.#request<AccountConnectionCallbackResult>(
      "GET",
      `/oauth/${provider}/callback?${query.toString()}`,
      undefined,
      provider,
    );
  }

  connection(options: AccountConnectionReadOptions): Promise<PublicAccountConnection> {
    const provider = normalizeAccountConnectionProvider(options.provider);
    const query = new URLSearchParams({
      tenant_id: requireId("tenant_id", options.tenantId),
      account_id: requireId("account_id", options.accountId),
    });
    return this.#request<PublicAccountConnection>(
      "GET",
      `/v1/projects/${encodeURIComponent(requireId("project_id", options.projectId))}/oauth/${provider}/connection?${query.toString()}`,
      undefined,
      provider,
    );
  }

  disconnect(options: AccountConnectionDisconnectOptions): Promise<AccountConnectionDisconnectResult> {
    const provider = normalizeAccountConnectionProvider(options.provider);
    return this.#request<AccountConnectionDisconnectResult>(
      "POST",
      `/v1/projects/${encodeURIComponent(requireId("project_id", options.projectId))}/oauth/${provider}/disconnect`,
      stripUndefined({
        session_id: options.sessionId === undefined ? undefined : requireId("session_id", options.sessionId),
        tenant_id: options.tenantId,
        account_id: options.accountId,
      }),
      provider,
    );
  }

  session(providerValue: AccountConnectionProvider | string, sessionId: string): Promise<AccountConnectionSession> {
    const provider = normalizeAccountConnectionProvider(providerValue);
    return this.#request<AccountConnectionSession>(
      "GET",
      `/v1/oauth/${provider}/session/${encodeURIComponent(requireId("session_id", sessionId))}`,
      undefined,
      provider,
    );
  }

  identity(providerValue: AccountConnectionProvider | string, sessionId: string): Promise<AccountConnectionIdentity> {
    const provider = normalizeAccountConnectionProvider(providerValue);
    return this.#request<AccountConnectionIdentity>(
      "GET",
      `/v1/oauth/${provider}/account/${encodeURIComponent(requireId("session_id", sessionId))}`,
      undefined,
      provider,
    );
  }

  async #request<T>(
    method: string,
    path: string,
    body: Record<string, unknown> | undefined,
    provider: AccountConnectionProvider,
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
      const payload = await parseSafeJson(response);
      if (!response.ok) {
        throw new AccountConnectionError(
          typeof payload.error === "string" ? payload.error : statusErrorCode(response.status),
          "Account connection HTTP request failed",
          response.status,
          { provider, retryable: response.status >= 500 || response.status === 429 },
        );
      }
      assertPublicAccountConnectionPayload(payload);
      return payload as T;
    } catch (error) {
      if (error instanceof AccountConnectionError) throw error;
      if (timedOut) {
        throw new AccountConnectionError("http_request_timeout", "Account connection HTTP request timed out", 504, { provider, retryable: true });
      }
      if (controller.signal.aborted) {
        throw new AccountConnectionError("http_request_aborted", "Account connection HTTP request was aborted", 499, { provider });
      }
      throw new AccountConnectionError("http_request_failed", "Account connection HTTP request failed", 502, { provider, retryable: true });
    } finally {
      clearTimeout(timeout);
      this.#signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}

export function normalizeAccountConnectionProvider(value: string): AccountConnectionProvider {
  let provider: string;
  try {
    provider = normalizeOAuthProvider(value);
  } catch {
    throw new AccountConnectionError("unsupported_oauth_provider", "Account connection provider must be github or google");
  }
  if (provider !== "github" && provider !== "google") {
    throw new AccountConnectionError("unsupported_oauth_provider", "Account connection provider must be github or google");
  }
  return provider;
}

export function validateExactAccountConnectionScopes(
  providerValue: AccountConnectionProvider | string,
  scopes: readonly string[],
): string[] {
  const provider = normalizeAccountConnectionProvider(providerValue);
  const normalized = [...new Set(scopes.map((scope) => scope.trim()).filter(Boolean))].sort();
  const expected = [...ACCOUNT_CONNECTION_EXACT_SCOPES[provider]].sort();
  if (normalized.length !== expected.length || normalized.some((scope, index) => scope !== expected[index])) {
    throw new AccountConnectionError(
      "invalid_oauth_scopes",
      `${provider} account connection requires exact scopes: ${expected.join(" ")}`,
      400,
      { provider },
    );
  }
  return [...ACCOUNT_CONNECTION_EXACT_SCOPES[provider]];
}

export function createAccountConnectionBinding(options: {
  tenantId: string;
  projectId: string;
  accountId: string;
  provider: AccountConnectionProvider | string;
}): AccountConnectionBinding {
  try {
    return {
      tenant_id: requireId("tenant_id", options.tenantId),
      project_id: requireId("project_id", options.projectId),
      account_id: requireId("account_id", options.accountId),
      provider: normalizeAccountConnectionProvider(options.provider),
    };
  } catch {
    throw new AccountConnectionError("invalid_oauth_binding", "Account connection binding is invalid");
  }
}

export function assertPublicAccountConnectionPayload(value: unknown): asserts value is Record<string, unknown> {
  const visit = (item: unknown, path: string): void => {
    if (Array.isArray(item)) {
      item.forEach((child, index) => visit(child, `${path}[${index}]`));
      return;
    }
    if (!isRecord(item)) return;
    for (const [key, child] of Object.entries(item)) {
      const normalized = key.trim().toLowerCase().replaceAll("-", "_");
      const canonical = normalized.replace(/[^a-z0-9]/gu, "");
      if (
        FORBIDDEN_ACCOUNT_CONNECTION_PUBLIC_KEYS.has(normalized)
        || FORBIDDEN_ACCOUNT_CONNECTION_CANONICAL_KEYS.has(canonical)
      ) {
        throw new AccountConnectionError(
          "invalid_oauth_callback",
          `Public account connection payload must not include ${normalized} at ${path}`,
        );
      }
      visit(child, `${path}.${key}`);
    }
  };
  if (!isRecord(value)) {
    throw new AccountConnectionError("invalid_oauth_callback", "Public account connection payload must be an object");
  }
  visit(value, "$");
}

export function parseAccountConnectionStart(
  value: unknown,
  options: {
    expectedProvider: AccountConnectionProvider | string;
    expectedGoogleAudience?: string;
  },
): PublicAccountConnectionStart {
  assertPublicAccountConnectionPayload(value);
  const provider = normalizeAccountConnectionProvider(requireString(value, "provider"));
  const expectedProvider = normalizeAccountConnectionProvider(options.expectedProvider);
  if (provider !== expectedProvider) {
    throw new AccountConnectionError("oauth_binding_mismatch", "Account connection response provider mismatch");
  }
  const authorizeUrl = requireHttpsUrl(
    "authorize_url",
    typeof value.authorize_url === "string" ? value.authorize_url : value.authorization_url,
  );
  if (provider === "google") {
    validateGoogleAccountConnectionAuthorizeUrl(authorizeUrl, {
      expectedAudience: options.expectedGoogleAudience,
    });
  }
  return {
    schema_version: requireString(value, "schema_version"),
    provider,
    authorize_url: authorizeUrl,
    expires_at: requireTimestamp("expires_at", value.expires_at),
  };
}

export function parseAccountConnection(
  value: unknown,
  options: {
    expectedProvider: AccountConnectionProvider | string;
    requireVerifiedEmail?: boolean;
  },
): PublicAccountConnection {
  assertPublicAccountConnectionPayload(value);
  const expectedProvider = normalizeAccountConnectionProvider(options.expectedProvider);
  const provider = normalizeAccountConnectionProvider(
    typeof value.provider === "string" ? value.provider : expectedProvider,
  );
  if (provider !== expectedProvider) {
    throw new AccountConnectionError("oauth_binding_mismatch", "Account connection provider mismatch");
  }
  const emailPresent = requireBoolean(value, "email_present");
  const emailVerified = requireBoolean(value, "email_verified");
  const requireVerifiedEmail = options.requireVerifiedEmail ?? provider === "google";
  if (requireVerifiedEmail && (!emailPresent || !emailVerified)) {
    throw new AccountConnectionError("oauth_email_unverified", "Account connection requires a verified email", 401, { provider });
  }
  const credentialId = requireId("credential_id", requireString(value, "credential_id"));
  const providerSubjectPresent = requireBoolean(value, "provider_subject_present");
  if (!providerSubjectPresent) {
    throw new AccountConnectionError(
      "invalid_oauth_callback",
      "provider_subject_present must be true for an account connection",
    );
  }
  const providerLogin = value.provider_login ?? value[`${provider}_login`];
  return {
    schema_version: optionalString(value.schema_version) ?? ACCOUNT_CONNECTION_SCHEMA_VERSION,
    provider,
    account_id: requireId("account_id", requireString(value, "account_id")),
    credential_id: credentialId,
    provider_subject_present: providerSubjectPresent,
    provider_login: optionalString(providerLogin),
    email_present: emailPresent,
    email_verified: emailVerified,
    connected_at: requireTimestamp("connected_at", value.connected_at),
    disconnected_at: value.disconnected_at === null || value.disconnected_at === undefined
      ? null
      : requireTimestamp("disconnected_at", value.disconnected_at),
  };
}

export function parseAccountConnectionDisconnect(
  value: unknown,
  options: { expectedProvider: AccountConnectionProvider | string },
): PublicAccountConnectionDisconnect {
  assertPublicAccountConnectionPayload(value);
  const expectedProvider = normalizeAccountConnectionProvider(options.expectedProvider);
  const provider = normalizeAccountConnectionProvider(
    typeof value.provider === "string" ? value.provider : expectedProvider,
  );
  if (provider !== expectedProvider) {
    throw new AccountConnectionError("oauth_binding_mismatch", "Account connection provider mismatch");
  }
  const disconnected = requireBoolean(value, "disconnected");
  const revocationStatus = optionalString(value.revocation_status) ?? (disconnected ? "revoked" : "pending");
  if (!["revoked", "not_required", "pending", "failed"].includes(revocationStatus)) {
    throw new AccountConnectionError("oauth_disconnect_failed", "Invalid account connection revocation status");
  }
  return {
    schema_version: optionalString(value.schema_version) ?? ACCOUNT_CONNECTION_SCHEMA_VERSION,
    provider,
    disconnected,
    revocation_status: revocationStatus as PublicAccountConnectionDisconnect["revocation_status"],
    connection: parseAccountConnection(value.connection, {
      expectedProvider: provider,
      requireVerifiedEmail: false,
    }),
  };
}

export function parseAccountConnectionError(value: unknown): PublicAccountConnectionError {
  assertPublicAccountConnectionPayload(value);
  const source = isRecord(value.error) ? value.error : value;
  const code = requireString(source, "code") as AccountConnectionStableErrorCode;
  if (!(ACCOUNT_CONNECTION_ERROR_CODES as readonly string[]).includes(code)) {
    throw new AccountConnectionError("invalid_oauth_callback", "Unknown account connection error code");
  }
  return {
    code,
    message: optionalString(source.message) ?? "",
    retryable: source.retryable === true,
    provider: source.provider === null || source.provider === undefined
      ? null
      : normalizeAccountConnectionProvider(requireString(source, "provider")),
    revocation_pending: source.revocation_pending === true,
  };
}

export function validateGoogleOidcPublicContract(value: unknown): Record<string, unknown> {
  assertPublicAccountConnectionPayload(value);
  const issuer = requireString(value, "issuer");
  if (!(GOOGLE_ACCOUNT_CONNECTION_ISSUERS as readonly string[]).includes(issuer) || value.issuer_matches !== true) {
    throw new AccountConnectionError("oidc_issuer_mismatch", "Google OIDC issuer validation failed", 401, { provider: "google" });
  }
  if (requireBoolean(value, "audience_matches") !== true) {
    throw new AccountConnectionError("oidc_audience_mismatch", "Google OIDC audience validation failed", 401, { provider: "google" });
  }
  if (value.nonce_required !== true || requireBoolean(value, "nonce_matches") !== true) {
    throw new AccountConnectionError("oidc_nonce_mismatch", "Google OIDC nonce validation failed", 401, { provider: "google" });
  }
  if (requireBoolean(value, "email_verified") !== true) {
    throw new AccountConnectionError("oauth_email_unverified", "Google account email is not verified", 401, { provider: "google" });
  }
  return {
    issuer,
    issuer_matches: true,
    audience_matches: true,
    nonce_required: true,
    nonce_matches: true,
    email_verified: true,
    raw_nonce_present: false,
    raw_token_present: false,
  };
}

export function validateGoogleAccountConnectionAuthorizeUrl(
  value: string,
  options: { expectedAudience?: string } = {},
): URL {
  const url = new URL(requireHttpsUrl("authorize_url", value));
  if (!["accounts.google.com", "accounts.google.cn"].includes(url.hostname)) {
    throw new AccountConnectionError("invalid_oauth_callback", "Google authorize_url must use an official Google host");
  }
  validateExactAccountConnectionScopes("google", (url.searchParams.get("scope") ?? "").split(/\s+/u));
  if (url.searchParams.get("code_challenge_method") !== "S256" || !url.searchParams.get("code_challenge")) {
    throw new AccountConnectionError("invalid_oauth_callback", "Google account connection requires PKCE S256");
  }
  if (!url.searchParams.get("state") || !url.searchParams.get("nonce")) {
    throw new AccountConnectionError("invalid_oauth_state", "Google account connection requires state and nonce");
  }
  if (options.expectedAudience !== undefined && url.searchParams.get("client_id") !== options.expectedAudience) {
    throw new AccountConnectionError("oidc_audience_mismatch", "Google OAuth client audience mismatch", 401, { provider: "google" });
  }
  return url;
}

export function verifyGoogleAccountConnectionClaims(options: {
  issuer: string;
  audience: string | readonly string[];
  subject: string;
  accountBindingRef: string;
  expectedAccountBindingRef?: string;
  receivedNonce: string;
  expectedNonceSha256: string;
  emailVerified: boolean;
  clientIdRef?: string;
  clientSecretRef?: string;
  redirectUri?: string;
  audienceAllowlist: readonly string[];
}): Record<string, unknown> {
  if (options.audienceAllowlist.length === 0) {
    throw new AccountConnectionError("google_audience_required", "Google account connection requires an audience allowlist", 400, { provider: "google" });
  }
  const normalizedIssuer = options.issuer === "accounts.google.com"
    ? "https://accounts.google.com"
    : options.issuer;
  const result = verifyCallbackIdentity({
    config: {
      provider: "google",
      clientIdRef: options.clientIdRef ?? "env:RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_ID",
      clientSecretRef: options.clientSecretRef ?? "env:RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_SECRET",
      redirectUri: options.redirectUri ?? "http://localhost:8787/oauth/google/callback",
      scopes: ACCOUNT_CONNECTION_EXACT_SCOPES.google,
      enabled: true,
      issuerAllowlist: ["https://accounts.google.com"],
      audienceAllowlist: options.audienceAllowlist,
    },
    issuer: normalizedIssuer,
    audience: options.audience,
    subject: options.subject,
    accountBindingRef: options.accountBindingRef,
    expectedAccountBindingRef: options.expectedAccountBindingRef,
    receivedNonce: options.receivedNonce,
    expectedNonceSha256: options.expectedNonceSha256,
    emailVerified: options.emailVerified,
  });
  if (result.accepted !== true) {
    throw new AccountConnectionError(
      googleFailureCode(result.failure_reasons),
      "Google OIDC identity validation failed",
      401,
      { provider: "google" },
    );
  }
  return result;
}

export function accountConnectionContractManifest(): Record<string, unknown> {
  return {
    schema_version: ACCOUNT_CONNECTION_SCHEMA_VERSION,
    credential_providers: [...ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS],
    credential_model: "one_account_many_credentials",
    provider_boundaries: {
      hosted_oauth: [...ACCOUNT_CONNECTION_PROVIDERS],
      domestic_oauth_contract: ["wechat", "qq", "alipay"],
      verification_contract: ["phone", "email"],
    },
    providers: {
      github: {
        protocol: "oauth2",
        exact_scopes: [...ACCOUNT_CONNECTION_EXACT_SCOPES.github],
        callback_path: "/oauth/github/callback",
        issuer_validation: false,
        audience_validation: false,
        nonce_required: false,
        verified_email_required: true,
      },
      google: {
        protocol: "oidc",
        exact_scopes: [...ACCOUNT_CONNECTION_EXACT_SCOPES.google],
        callback_path: "/oauth/google/callback",
        issuer_allowlist: [...GOOGLE_ACCOUNT_CONNECTION_ISSUERS],
        issuer_validation: true,
        audience_validation: true,
        nonce_required: true,
        verified_email_required: true,
      },
    },
    operations: ["start", "callback", "session", "identity", "disconnect"],
    routes: ACCOUNT_CONNECTION_ROUTES.map((route) => ({ ...route })),
    stable_error_codes: [...ACCOUNT_CONNECTION_ERROR_CODES],
    disconnect_contract: {
      revoke_provider_token_before_local_delete: true,
      idempotent_after_success: true,
      provider_revoke_failure_code: "provider_revoke_failed",
    },
    disconnect_errors: [
      "provider_revoke_failed",
      "session_not_found",
      "session_revoked",
    ],
    callback_errors: [
      "invalid_oauth_state",
      "oauth_callback_replayed",
      "provider_error",
      "issuer_mismatch",
      "audience_mismatch",
      "nonce_mismatch",
      "email_unverified",
    ],
    public_safety: {
      raw_state_present: false,
      raw_code_present: false,
      raw_nonce_present: false,
      token_value_present: false,
      secret_value_present: false,
    },
    network_io_performed: false,
  };
}

export function hashGoogleAccountConnectionNonce(nonce: string): string {
  const result = hashOAuthNonce(nonce);
  return String(result.nonce_sha256);
}

function googleFailureCode(value: unknown): string {
  if (!Array.isArray(value)) return "google_identity_invalid";
  const failures = value.filter((item): item is string => typeof item === "string");
  const priority = ["issuer_mismatch", "audience_mismatch", "nonce_mismatch", "email_unverified", "account_binding_mismatch"];
  return priority.find((code) => failures.includes(code)) ?? "google_identity_invalid";
}

function requireId(name: string, value: string): string {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/u.test(normalized)) {
    throw new AccountConnectionError(`invalid_${name}`, `${name} is invalid`);
  }
  return normalized;
}

function stripUndefined(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

async function parseSafeJson(response: Response): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await response.json();
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  } catch {
    // The public error below deliberately omits provider response bodies.
  }
  if (!response.ok) return {};
  throw new AccountConnectionError("invalid_http_response", "Account connection response must be a JSON object", 502);
}

function normalizeTimeout(value = 10_000): number {
  if (!Number.isInteger(value) || value < 1 || value > 120_000) {
    throw new AccountConnectionError("invalid_timeout", "timeoutMs must be between 1 and 120000");
  }
  return value;
}

function normalizeStatus(value: number): number {
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : 500;
}

function statusErrorCode(status: number): string {
  if (status === 409) return "oauth_callback_replayed";
  if (status === 429) return "oauth_rate_limited";
  if (status >= 500) return "oauth_provider_unavailable";
  return "oauth_request_rejected";
}

function safeErrorCode(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9_]+/gu, "_").replace(/^_+|_+$/gu, "");
  if (!normalized || normalized.length > 64) return "oauth_request_failed";
  const allowed = new Set([
    "account_binding_mismatch",
    "audience_mismatch",
    "email_unverified",
    "google_audience_required",
    "google_identity_invalid",
    "http_request_aborted",
    "http_request_failed",
    "http_request_timeout",
    "invalid_base_url",
    "invalid_http_response",
    "invalid_oauth_scopes",
    "invalid_oauth_state",
    "invalid_oauth_binding",
    "invalid_oauth_callback",
    "invalid_project_id",
    "invalid_session_id",
    "invalid_timeout",
    "issuer_mismatch",
    "nonce_mismatch",
    "oauth_binding_mismatch",
    "oauth_connection_not_found",
    "oauth_credentials_unavailable",
    "oauth_disconnect_failed",
    "oauth_email_unverified",
    "oauth_provider_error",
    "oauth_provider_revoke_failed",
    "oauth_reconnect_revoke_failed",
    "oauth_secret_store_failed",
    "oauth_secret_resolve_failed",
    "oauth_secret_delete_failed",
    "oauth_connection_store_failed",
    "oauth_callback_replayed",
    "oauth_provider_unavailable",
    "oauth_rate_limited",
    "oauth_request_failed",
    "oauth_request_rejected",
    "provider_error",
    "provider_revoke_failed",
    "oidc_issuer_mismatch",
    "oidc_audience_mismatch",
    "oidc_nonce_mismatch",
    "session_not_found",
    "session_revoked",
    "unsupported_oauth_provider",
  ]);
  return allowed.has(normalized) ? normalized : "oauth_request_failed";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: Record<string, unknown>, name: string): string {
  const normalized = optionalString(value[name]);
  if (normalized === null) {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} is required`);
  }
  return normalized;
}

function optionalString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

function requireBoolean(value: Record<string, unknown>, name: string): boolean {
  if (typeof value[name] !== "boolean") {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} must be a boolean`);
  }
  return value[name] as boolean;
}

function requireHttpsUrl(name: string, value: unknown): string {
  const normalized = optionalString(value);
  if (normalized === null) {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} is required`);
  }
  let parsed: URL;
  try {
    parsed = new URL(normalized);
  } catch {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} must be an HTTPS URL`);
  }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password) {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} must be an HTTPS URL`);
  }
  return parsed.toString();
}

function requireTimestamp(name: string, value: unknown): string {
  const normalized = optionalString(value);
  if (normalized === null || !Number.isFinite(Date.parse(normalized))) {
    throw new AccountConnectionError("invalid_oauth_callback", `${name} must be an ISO-8601 timestamp`);
  }
  return normalized;
}
