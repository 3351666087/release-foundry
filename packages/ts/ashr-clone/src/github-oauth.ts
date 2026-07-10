import { createHash, timingSafeEqual } from "node:crypto";

import { OAuthProviderContractError, derivePkceS256, validateOAuthClientConfig } from "./oauth.js";

export const GITHUB_OAUTH_SCHEMA_VERSION = "ashr.clone.github_oauth.v1";
export const GITHUB_OAUTH_OPENAPI_VERSION = "3.0.3";
export const GITHUB_OAUTH_DEFAULT_SCOPES = ["read:user", "user:email"] as const;

export type GitHubOAuthFetch = typeof fetch;
export type GitHubOAuthSecretPurpose = "client_id" | "client_secret";
export type GitHubOAuthSessionStatus = "active" | "revoked";
export type GitHubOAuthFlowStatus = "pending" | "completed" | "failed";

export interface GitHubOAuthConfig {
  clientIdRef: string;
  clientSecretRef: string;
  redirectUri: string;
  scopes?: readonly string[];
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
  apiBaseUrl?: string;
}

export interface GitHubOAuthRuntimeOptions {
  config: GitHubOAuthConfig;
  fetch?: GitHubOAuthFetch;
  timeoutMs?: number;
  signal?: AbortSignal;
  resolveSecret: (reference: string, purpose: GitHubOAuthSecretPurpose) => string | Promise<string>;
  tokenStore: GitHubOAuthTokenStore;
  randomBytes?: (size: number) => Uint8Array;
  now?: () => string;
  idFactory?: (prefix: "github_flow" | "github_session") => string;
}

export interface GitHubOAuthTokenStore {
  store(token: GitHubOAuthTokenMaterial): string | Promise<string>;
  resolve(reference: string): GitHubOAuthTokenMaterial | undefined | Promise<GitHubOAuthTokenMaterial | undefined>;
  delete(reference: string): void | Promise<void>;
}

export interface GitHubOAuthTokenMaterial {
  accessToken: string;
  tokenType: string;
  scopes: string[];
}

export interface GitHubOAuthStartOptions {
  projectId: string;
  returnTo?: string;
  login?: string;
  allowSignup?: boolean;
}

export interface GitHubOAuthStartResult {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  operation: "github_oauth_start";
  provider: "github";
  project_id: string;
  flow_id: string;
  authorization_url: string;
  redirect_uri: string;
  scopes: string[];
  state_sha256: string;
  code_challenge: string;
  code_challenge_method: "S256";
  expires_at: string;
  return_to: string | null;
  network_io_performed: false;
  code_verifier_present: false;
  client_secret_present: false;
  token_value_present: false;
}

export interface GitHubOAuthCallbackOptions {
  flowId?: string;
  state?: string;
  code?: string;
  error?: string;
  errorDescription?: string;
}

export interface GitHubOAuthCallbackResult {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  operation: "github_oauth_callback";
  provider: "github";
  accepted: true;
  flow_id: string;
  session: GitHubOAuthSession;
  account: GitHubOAuthAccount;
  return_to: string | null;
  raw_code_present: false;
  raw_state_present: false;
  code_verifier_present: false;
  token_value_present: false;
  client_secret_present: false;
}

export interface GitHubOAuthDisconnectResult {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  operation: "github_oauth_disconnect";
  provider: "github";
  disconnected: boolean;
  already_disconnected: boolean;
  session: GitHubOAuthSession;
  provider_revocation_attempted: boolean;
  token_value_present: false;
  client_secret_present: false;
}

export interface GitHubOAuthSession {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  provider: "github";
  project_id: string;
  session_id: string;
  flow_id: string;
  status: GitHubOAuthSessionStatus;
  account_id: string;
  subject_ref: string;
  access_token_ref_present: boolean;
  granted_scopes: string[];
  created_at: string;
  revoked_at: string | null;
  token_value_present: false;
  client_secret_present: false;
}

export interface GitHubOAuthAccount {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  provider: "github";
  account_id: string;
  github_user_id: number;
  login: string;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
  html_url: string | null;
  subject_ref: string;
  token_value_present: false;
}

export interface GitHubOAuthFlowSnapshot {
  schema_version: typeof GITHUB_OAUTH_SCHEMA_VERSION;
  provider: "github";
  project_id: string;
  flow_id: string;
  status: GitHubOAuthFlowStatus;
  state_sha256: string;
  code_challenge: string;
  redirect_uri: string;
  scopes: string[];
  return_to: string | null;
  created_at: string;
  expires_at: string;
  session_id: string | null;
  failure_code: string | null;
  raw_state_present: false;
  code_verifier_present: false;
}

export interface GitHubOAuthHttpResponse {
  status_code: number;
  body: Record<string, unknown>;
}

export class GitHubOAuthError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 400) {
    super(message);
    this.name = "GitHubOAuthError";
    this.code = normalizeErrorCode(code);
    this.status = status;
  }

  toJSON(): Record<string, unknown> {
    return {
      schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
      error: this.code,
      message: this.message,
      status: this.status,
      provider: "github",
      provider_response_included: false,
      secret_value_present: false,
      token_value_present: false,
    };
  }
}

export class GitHubOAuthProviderError extends GitHubOAuthError {
  readonly providerStatus: number | null;
  readonly retryable: boolean;

  constructor(code: string, options: { status?: number; providerStatus?: number | null; retryable?: boolean } = {}) {
    const status = options.status ?? (options.providerStatus === 429 ? 503 : 502);
    super(code, providerErrorMessage(code), status);
    this.name = "GitHubOAuthProviderError";
    this.providerStatus = options.providerStatus ?? null;
    this.retryable = options.retryable ?? (this.providerStatus === 429 || (this.providerStatus ?? 0) >= 500);
  }

  override toJSON(): Record<string, unknown> {
    return {
      ...super.toJSON(),
      provider_status: this.providerStatus,
      retryable: this.retryable,
    };
  }
}

interface PendingFlow {
  projectId: string;
  flowId: string;
  status: GitHubOAuthFlowStatus;
  stateSha256: string;
  codeVerifier: string;
  codeChallenge: string;
  redirectUri: string;
  scopes: string[];
  returnTo: string | null;
  createdAt: string;
  expiresAt: string;
  sessionId: string | null;
  failureCode: string | null;
}

interface StoredSession {
  projectId: string;
  sessionId: string;
  flowId: string;
  status: GitHubOAuthSessionStatus;
  accountId: string;
  subjectRef: string;
  accessTokenRef: string | null;
  grantedScopes: string[];
  createdAt: string;
  revokedAt: string | null;
}

interface GitHubTokenResponse {
  access_token?: unknown;
  token_type?: unknown;
  scope?: unknown;
  error?: unknown;
  error_description?: unknown;
}

interface GitHubUserResponse {
  id?: unknown;
  login?: unknown;
  name?: unknown;
  email?: unknown;
  avatar_url?: unknown;
  html_url?: unknown;
}

interface GitHubEmailResponse {
  email?: unknown;
  primary?: unknown;
  verified?: unknown;
}

export class MemoryGitHubOAuthTokenStore implements GitHubOAuthTokenStore {
  readonly #tokens = new Map<string, GitHubOAuthTokenMaterial>();
  #counter = 0;

  store(token: GitHubOAuthTokenMaterial): string {
    this.#counter += 1;
    const reference = `vault:github/oauth/access/${String(this.#counter).padStart(8, "0")}`;
    this.#tokens.set(reference, cloneToken(token));
    return reference;
  }

  resolve(reference: string): GitHubOAuthTokenMaterial | undefined {
    const token = this.#tokens.get(reference);
    return token === undefined ? undefined : cloneToken(token);
  }

  delete(reference: string): void {
    this.#tokens.delete(reference);
  }

  publicSnapshot(): Record<string, unknown> {
    return {
      token_reference_count: this.#tokens.size,
      token_values_present: false,
    };
  }
}

export class GitHubOAuthRuntime {
  readonly #config: Required<Pick<GitHubOAuthConfig, "authorizationEndpoint" | "tokenEndpoint" | "apiBaseUrl">> & {
    clientIdRef: string;
    clientSecretRef: string;
    redirectUri: string;
    scopes: string[];
  };
  readonly #fetch: GitHubOAuthFetch;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;
  readonly #resolveSecret: GitHubOAuthRuntimeOptions["resolveSecret"];
  readonly #tokenStore: GitHubOAuthTokenStore;
  readonly #randomBytes: (size: number) => Uint8Array;
  readonly #now: () => string;
  readonly #idFactory: (prefix: "github_flow" | "github_session") => string;
  readonly #flows = new Map<string, PendingFlow>();
  readonly #sessions = new Map<string, StoredSession>();
  readonly #accounts = new Map<string, GitHubOAuthAccount>();
  #idCounter = 0;

  constructor(options: GitHubOAuthRuntimeOptions) {
    const scopes = unique(options.config.scopes ?? GITHUB_OAUTH_DEFAULT_SCOPES);
    const validated = validateOAuthClientConfig({
      provider: "github",
      clientIdRef: options.config.clientIdRef,
      clientSecretRef: options.config.clientSecretRef,
      redirectUri: options.config.redirectUri,
      redirectAllowlist: [options.config.redirectUri],
      scopes,
      enabled: true,
    });
    this.#config = {
      clientIdRef: validated.client_id_ref,
      clientSecretRef: validated.client_secret_ref,
      redirectUri: validated.redirect_uri,
      scopes: validated.scopes,
      authorizationEndpoint: normalizeEndpoint(options.config.authorizationEndpoint ?? "https://github.com/login/oauth/authorize"),
      tokenEndpoint: normalizeEndpoint(options.config.tokenEndpoint ?? "https://github.com/login/oauth/access_token"),
      apiBaseUrl: normalizeEndpoint(options.config.apiBaseUrl ?? "https://api.github.com"),
    };
    this.#fetch = options.fetch ?? globalThis.fetch;
    if (typeof this.#fetch !== "function") throw new GitHubOAuthError("fetch_unavailable", "A fetch implementation is required", 500);
    this.#timeoutMs = validateTimeoutMs(options.timeoutMs);
    this.#signal = options.signal;
    this.#resolveSecret = options.resolveSecret;
    this.#tokenStore = options.tokenStore;
    this.#randomBytes = options.randomBytes ?? secureRandomBytes;
    this.#now = options.now ?? (() => new Date().toISOString());
    this.#idFactory = options.idFactory ?? ((prefix) => {
      this.#idCounter += 1;
      return `${prefix}_${String(this.#idCounter).padStart(8, "0")}`;
    });
  }

  async start(options: GitHubOAuthStartOptions): Promise<GitHubOAuthStartResult> {
    const projectId = boundedId("project_id", options.projectId);
    const clientId = validateResolvedClientId(await this.#resolveSecret(this.#config.clientIdRef, "client_id"));
    const state = randomBase64Url(this.#randomBytes, 32);
    const codeVerifier = randomBase64Url(this.#randomBytes, 48);
    const pkce = derivePkceS256(codeVerifier);
    const now = this.#now();
    const expiresAt = new Date(Date.parse(now) + 10 * 60 * 1000).toISOString();
    const flowId = this.#idFactory("github_flow");
    const returnTo = normalizeReturnTo(options.returnTo);
    const url = new URL(this.#config.authorizationEndpoint);
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("redirect_uri", this.#config.redirectUri);
    url.searchParams.set("scope", this.#config.scopes.join(" "));
    url.searchParams.set("state", state);
    url.searchParams.set("code_challenge", String(pkce.code_challenge));
    url.searchParams.set("code_challenge_method", "S256");
    if (options.login !== undefined) url.searchParams.set("login", boundedText("login", options.login, 256));
    if (options.allowSignup !== undefined) url.searchParams.set("allow_signup", options.allowSignup ? "true" : "false");
    this.#flows.set(flowId, {
      projectId,
      flowId,
      status: "pending",
      stateSha256: sha256(state),
      codeVerifier,
      codeChallenge: String(pkce.code_challenge),
      redirectUri: this.#config.redirectUri,
      scopes: [...this.#config.scopes],
      returnTo,
      createdAt: now,
      expiresAt,
      sessionId: null,
      failureCode: null,
    });
    return {
      schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
      operation: "github_oauth_start",
      provider: "github",
      project_id: projectId,
      flow_id: flowId,
      authorization_url: url.toString(),
      redirect_uri: this.#config.redirectUri,
      scopes: [...this.#config.scopes],
      state_sha256: sha256(state),
      code_challenge: String(pkce.code_challenge),
      code_challenge_method: "S256",
      expires_at: expiresAt,
      return_to: returnTo,
      network_io_performed: false,
      code_verifier_present: false,
      client_secret_present: false,
      token_value_present: false,
    };
  }

  async callback(options: GitHubOAuthCallbackOptions): Promise<GitHubOAuthCallbackResult> {
    const receivedState = options.state ?? "";
    const flow = this.#flowForCallback(receivedState, options.flowId);
    if (flow.status !== "pending") throw new GitHubOAuthError("callback_replay", "OAuth callback has already been consumed", 409);
    if (Date.parse(flow.expiresAt) <= Date.parse(this.#now())) {
      flow.status = "failed";
      flow.failureCode = "flow_expired";
      flow.codeVerifier = "";
      throw new GitHubOAuthError("flow_expired", "OAuth flow has expired", 410);
    }
    if (!constantEqual(sha256(receivedState), flow.stateSha256)) {
      throw new GitHubOAuthError("state_mismatch", "OAuth state did not match", 400);
    }
    if (options.error !== undefined) {
      flow.status = "failed";
      flow.failureCode = safeProviderCode(options.error, "provider_authorization_failed");
      flow.codeVerifier = "";
      throw new GitHubOAuthProviderError(flow.failureCode, { status: 400, providerStatus: null, retryable: false });
    }
    const code = boundedSecret("authorization code", options.code);
    flow.status = "failed";
    flow.failureCode = "callback_failed";
    try {
      const token = await this.#exchangeCode(code, flow.codeVerifier);
      const account = await this.#fetchAccount(token.accessToken, token.scopes);
      const accessTokenRef = validateTokenRef(await this.#tokenStore.store(token));
      const sessionId = this.#idFactory("github_session");
      const session: StoredSession = {
        projectId: flow.projectId,
        sessionId,
        flowId: flow.flowId,
        status: "active",
        accountId: account.account_id,
        subjectRef: account.subject_ref,
        accessTokenRef,
        grantedScopes: [...token.scopes],
        createdAt: this.#now(),
        revokedAt: null,
      };
      this.#sessions.set(sessionId, session);
      this.#accounts.set(account.account_id, account);
      flow.status = "completed";
      flow.failureCode = null;
      flow.sessionId = sessionId;
      return {
        schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
        operation: "github_oauth_callback",
        provider: "github",
        accepted: true,
        flow_id: flow.flowId,
        session: publicSession(session),
        account: cloneAccount(account),
        return_to: flow.returnTo,
        raw_code_present: false,
        raw_state_present: false,
        code_verifier_present: false,
        token_value_present: false,
        client_secret_present: false,
      };
    } catch (error) {
      flow.failureCode = error instanceof GitHubOAuthError ? error.code : "provider_request_failed";
      throw redactRuntimeError(error);
    } finally {
      flow.codeVerifier = "";
    }
  }

  async disconnect(projectId: string, sessionId: string): Promise<GitHubOAuthDisconnectResult> {
    const session = this.#sessionRecord(sessionId);
    if (session.projectId !== boundedId("project_id", projectId)) {
      throw new GitHubOAuthError("session_not_found", "OAuth session was not found", 404);
    }
    if (session.status === "revoked") {
      return {
        schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
        operation: "github_oauth_disconnect",
        provider: "github",
        disconnected: true,
        already_disconnected: true,
        session: publicSession(session),
        provider_revocation_attempted: false,
        token_value_present: false,
        client_secret_present: false,
      };
    }
    const tokenRef = session.accessTokenRef;
    if (tokenRef === null) throw new GitHubOAuthError("token_reference_missing", "OAuth session has no token reference", 409);
    const token = await this.#tokenStore.resolve(tokenRef);
    if (token === undefined) throw new GitHubOAuthError("token_reference_unresolved", "OAuth token reference could not be resolved", 409);
    const clientId = validateResolvedClientId(await this.#resolveSecret(this.#config.clientIdRef, "client_id"));
    const clientSecret = boundedSecret("client secret", await this.#resolveSecret(this.#config.clientSecretRef, "client_secret"));
    const response = await this.#providerFetch(`${this.#config.apiBaseUrl}/applications/${encodeURIComponent(clientId)}/token`, {
      method: "DELETE",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Basic ${encodeBasicAuth(clientId, clientSecret)}`,
        "content-type": "application/json",
        "user-agent": "ashr-clone-ts-github-oauth",
        "x-github-api-version": "2022-11-28",
      },
      body: JSON.stringify({ access_token: token.accessToken }),
    }, "provider_revoke_failed");
    if (response.status !== 204 && response.status !== 404 && !response.ok) {
      throw new GitHubOAuthProviderError("provider_revoke_failed", { providerStatus: response.status });
    }
    await this.#tokenStore.delete(tokenRef);
    session.status = "revoked";
    session.revokedAt = this.#now();
    session.accessTokenRef = null;
    return {
      schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
      operation: "github_oauth_disconnect",
      provider: "github",
      disconnected: true,
      already_disconnected: false,
      session: publicSession(session),
      provider_revocation_attempted: true,
      token_value_present: false,
      client_secret_present: false,
    };
  }

  session(sessionId: string): GitHubOAuthSession {
    return publicSession(this.#sessionRecord(sessionId));
  }

  account(sessionId: string): GitHubOAuthAccount {
    const session = this.#sessionRecord(sessionId);
    if (session.status !== "active") throw new GitHubOAuthError("session_revoked", "OAuth session is revoked", 401);
    const account = this.#accounts.get(session.accountId);
    if (account === undefined) throw new GitHubOAuthError("account_not_found", "GitHub account was not found", 404);
    return cloneAccount(account);
  }

  flow(flowId: string): GitHubOAuthFlowSnapshot {
    return publicFlow(this.#flow(flowId));
  }

  publicSnapshot(): Record<string, unknown> {
    return {
      schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
      provider: "github",
      flows: [...this.#flows.values()].map(publicFlow),
      sessions: [...this.#sessions.values()].map(publicSession),
      accounts: [...this.#accounts.values()].map(cloneAccount),
      raw_state_present: false,
      raw_code_present: false,
      code_verifier_present: false,
      client_secret_present: false,
      token_value_present: false,
    };
  }

  async #exchangeCode(code: string, verifier: string): Promise<GitHubOAuthTokenMaterial> {
    const clientId = validateResolvedClientId(await this.#resolveSecret(this.#config.clientIdRef, "client_id"));
    const clientSecret = boundedSecret("client secret", await this.#resolveSecret(this.#config.clientSecretRef, "client_secret"));
    const response = await this.#providerFetch(this.#config.tokenEndpoint, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "ashr-clone-ts-github-oauth",
      },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        code,
        redirect_uri: this.#config.redirectUri,
        code_verifier: verifier,
      }).toString(),
    }, "token_exchange_failed");
    const payload = await parseProviderPayload(response);
    if (!response.ok) throw new GitHubOAuthProviderError(providerCode(payload, "token_exchange_failed"), { providerStatus: response.status });
    if (payload.error !== undefined) throw new GitHubOAuthProviderError(providerCode(payload, "token_exchange_failed"), { providerStatus: response.status, retryable: false });
    if (typeof payload.access_token !== "string" || payload.access_token.length === 0 || payload.access_token.length > 4096) {
      throw new GitHubOAuthProviderError("invalid_token_response", { providerStatus: response.status, retryable: false });
    }
    const accessToken = boundedSecret("access token", payload.access_token);
    return {
      accessToken,
      tokenType: validateTokenType(payload.token_type, response.status),
      scopes: validateGrantedScopes(parseScopes(payload.scope, this.#config.scopes), this.#config.scopes, response.status),
    };
  }

  async #fetchAccount(accessToken: string, grantedScopes: readonly string[]): Promise<GitHubOAuthAccount> {
    const response = await this.#providerFetch(`${this.#config.apiBaseUrl}/user`, {
      method: "GET",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${accessToken}`,
        "user-agent": "ashr-clone-ts-github-oauth",
        "x-github-api-version": "2022-11-28",
      },
    }, "account_fetch_failed");
    const payload = await parseProviderPayload(response);
    if (!response.ok) throw new GitHubOAuthProviderError(providerCode(payload, "account_fetch_failed"), { providerStatus: response.status });
    const id = positiveInteger(payload.id, "GitHub user id");
    const login = boundedText("GitHub login", stringValue(payload.login), 256);
    const subjectRef = `provider-ref:github/user/${id}`;
    let email = optionalBoundedText(payload.email, 512);
    if (email === null && grantedScopes.includes("user:email")) {
      email = await this.#fetchVerifiedPrimaryEmail(accessToken);
    }
    return {
      schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
      provider: "github",
      account_id: `github:${id}`,
      github_user_id: id,
      login,
      name: optionalBoundedText(payload.name, 512),
      email,
      avatar_url: optionalHttpsUrl(payload.avatar_url),
      html_url: optionalHttpsUrl(payload.html_url),
      subject_ref: subjectRef,
      token_value_present: false,
    };
  }

  async #fetchVerifiedPrimaryEmail(accessToken: string): Promise<string | null> {
    const response = await this.#providerFetch(`${this.#config.apiBaseUrl}/user/emails`, {
      method: "GET",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${accessToken}`,
        "user-agent": "ashr-clone-ts-github-oauth",
        "x-github-api-version": "2022-11-28",
      },
    }, "account_email_fetch_failed");
    const payload = await parseProviderJson(response);
    if (!response.ok) {
      throw new GitHubOAuthProviderError(
        isRecord(payload) ? providerCode(payload, "account_email_fetch_failed") : "account_email_fetch_failed",
        { providerStatus: response.status },
      );
    }
    if (!Array.isArray(payload)) {
      throw new GitHubOAuthProviderError("invalid_account_response", { providerStatus: response.status, retryable: false });
    }
    for (const entry of payload) {
      if (!isRecord(entry)) continue;
      const email = entry as GitHubEmailResponse;
      if (email.primary === true && email.verified === true) return optionalBoundedText(email.email, 512);
    }
    return null;
  }

  async #providerFetch(url: string, init: RequestInit, failureCode: string): Promise<Response> {
    const abort = composeAbortSignals(this.#timeoutMs, [this.#signal, init.signal]);
    try {
      if (abort.signal.aborted) {
        throw new GitHubOAuthProviderError("provider_request_aborted", { providerStatus: null, retryable: false });
      }
      return await this.#fetch(url, { ...init, signal: abort.signal });
    } catch (error) {
      if (error instanceof GitHubOAuthProviderError) throw error;
      if (abort.timedOut()) throw new GitHubOAuthProviderError("provider_request_timeout", { providerStatus: null, retryable: true });
      if (abort.signal.aborted) throw new GitHubOAuthProviderError("provider_request_aborted", { providerStatus: null, retryable: false });
      throw new GitHubOAuthProviderError(failureCode, { providerStatus: null, retryable: true });
    } finally {
      abort.cleanup();
    }
  }

  #flowForCallback(state: string, flowId?: string): PendingFlow {
    const stateSha256 = sha256(state);
    if (flowId !== undefined) {
      const flow = this.#flow(flowId);
      if (!constantEqual(stateSha256, flow.stateSha256)) throw new GitHubOAuthError("state_mismatch", "OAuth state did not match", 400);
      return flow;
    }
    for (const flow of this.#flows.values()) {
      if (constantEqual(stateSha256, flow.stateSha256)) return flow;
    }
    throw new GitHubOAuthError("state_mismatch", "OAuth state did not match", 400);
  }

  #flow(flowId: string): PendingFlow {
    const flow = this.#flows.get(boundedId("flow_id", flowId));
    if (flow === undefined) throw new GitHubOAuthError("flow_not_found", "OAuth flow was not found", 404);
    return flow;
  }

  #sessionRecord(sessionId: string): StoredSession {
    const session = this.#sessions.get(boundedId("session_id", sessionId));
    if (session === undefined) throw new GitHubOAuthError("session_not_found", "OAuth session was not found", 404);
    return session;
  }
}

export class GitHubOAuthRouter {
  constructor(readonly runtime: GitHubOAuthRuntime) {}

  async handle(method: string, path: string, input: Record<string, unknown> = {}): Promise<GitHubOAuthHttpResponse> {
    try {
      const upperMethod = method.toUpperCase();
      const url = new URL(path, "http://localhost");
      const body = { ...Object.fromEntries(url.searchParams), ...input };
      const parts = url.pathname.split("/").filter(Boolean);
      if (upperMethod === "GET" && (url.pathname === "/openapi.json" || url.pathname === "/v1/openapi.json")) {
        return { status_code: 200, body: exportGitHubOAuthOpenApiSpec() };
      }
      if ((upperMethod === "GET" || upperMethod === "POST") && parts.length === 6
        && parts[0] === "v1" && parts[1] === "projects" && parts[3] === "oauth"
        && parts[4] === "github" && parts[5] === "start") {
        return { status_code: 201, body: await this.runtime.start({
          projectId: decodeURIComponent(parts[2]),
          returnTo: optionalString(body.return_to),
          login: optionalString(body.login),
          allowSignup: optionalBoolean(body.allow_signup),
        }) as unknown as Record<string, unknown> };
      }
      if (upperMethod === "GET" && url.pathname === "/oauth/github/callback") {
        return { status_code: 200, body: await this.runtime.callback({
          state: optionalString(body.state),
          code: optionalString(body.code),
          error: optionalString(body.error),
          errorDescription: optionalString(body.error_description),
        }) as unknown as Record<string, unknown> };
      }
      if ((upperMethod === "POST" || upperMethod === "DELETE") && parts.length === 6
        && parts[0] === "v1" && parts[1] === "projects" && parts[3] === "oauth"
        && parts[4] === "github" && parts[5] === "disconnect") {
        return { status_code: 200, body: await this.runtime.disconnect(
          decodeURIComponent(parts[2]),
          requiredString(body.session_id, "session_id"),
        ) as unknown as Record<string, unknown> };
      }
      if (upperMethod === "GET" && parts.length === 5 && parts.slice(0, 4).join("/") === "v1/oauth/github/session") {
        return { status_code: 200, body: this.runtime.session(decodeURIComponent(parts[4])) as unknown as Record<string, unknown> };
      }
      if (upperMethod === "GET" && parts.length === 5 && parts.slice(0, 4).join("/") === "v1/oauth/github/account") {
        return { status_code: 200, body: this.runtime.account(decodeURIComponent(parts[4])) as unknown as Record<string, unknown> };
      }
      return { status_code: 404, body: new GitHubOAuthError("route_not_found", "GitHub OAuth route was not found", 404).toJSON() };
    } catch (error) {
      const safe = redactRuntimeError(error);
      return { status_code: safe.status, body: safe.toJSON() };
    }
  }
}

export interface GitHubOAuthHttpClientOptions {
  baseUrl: string;
  fetch?: GitHubOAuthFetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export class GitHubOAuthHttpClient {
  readonly #baseUrl: string;
  readonly #fetch: GitHubOAuthFetch;
  readonly #headers: Record<string, string>;
  readonly #timeoutMs: number;
  readonly #signal: AbortSignal | undefined;

  constructor(options: GitHubOAuthHttpClientOptions) {
    this.#baseUrl = options.baseUrl.replace(/\/+$/u, "");
    this.#fetch = options.fetch ?? globalThis.fetch;
    this.#headers = { ...(options.headers ?? {}) };
    this.#timeoutMs = validateTimeoutMs(options.timeoutMs);
    this.#signal = options.signal;
  }

  start(projectId: string, options: Omit<GitHubOAuthStartOptions, "projectId"> = {}): Promise<GitHubOAuthStartResult> {
    return this.#request<GitHubOAuthStartResult>("POST", `/v1/projects/${encodeURIComponent(boundedId("project_id", projectId))}/oauth/github/start`, {
      return_to: options.returnTo,
      login: options.login,
      allow_signup: options.allowSignup,
    });
  }

  callback(options: GitHubOAuthCallbackOptions): Promise<GitHubOAuthCallbackResult> {
    const query = new URLSearchParams(stripUndefined({
      state: options.state,
      code: options.code,
      error: options.error,
      error_description: options.errorDescription,
    }) as Record<string, string>);
    return this.#request<GitHubOAuthCallbackResult>("GET", `/oauth/github/callback?${query.toString()}`);
  }

  disconnect(projectId: string, sessionId: string): Promise<GitHubOAuthDisconnectResult> {
    return this.#request<GitHubOAuthDisconnectResult>(
      "POST",
      `/v1/projects/${encodeURIComponent(boundedId("project_id", projectId))}/oauth/github/disconnect`,
      { session_id: sessionId },
    );
  }

  session(sessionId: string): Promise<GitHubOAuthSession> {
    return this.#request<GitHubOAuthSession>("GET", `/v1/oauth/github/session/${encodeURIComponent(sessionId)}`);
  }

  account(sessionId: string): Promise<GitHubOAuthAccount> {
    return this.#request<GitHubOAuthAccount>("GET", `/v1/oauth/github/account/${encodeURIComponent(sessionId)}`);
  }

  openApi(): Promise<Record<string, unknown>> {
    return this.#request<Record<string, unknown>>("GET", "/openapi.json");
  }

  async #request<T>(method: string, path: string, body?: Record<string, unknown>): Promise<T> {
    const abort = composeAbortSignals(this.#timeoutMs, [this.#signal]);
    let response: Response;
    try {
      if (abort.signal.aborted) throw new GitHubOAuthError("http_request_aborted", "GitHub OAuth HTTP request was aborted", 499);
      response = await this.#fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          accept: "application/json",
          ...(body === undefined ? {} : { "content-type": "application/json" }),
          ...this.#headers,
        },
        body: body === undefined ? undefined : JSON.stringify(stripUndefined(body)),
        signal: abort.signal,
      });
    } catch (error) {
      if (error instanceof GitHubOAuthError) throw error;
      if (abort.timedOut()) throw new GitHubOAuthError("http_request_timeout", "GitHub OAuth HTTP request timed out", 504);
      if (abort.signal.aborted) throw new GitHubOAuthError("http_request_aborted", "GitHub OAuth HTTP request was aborted", 499);
      throw new GitHubOAuthError("http_request_failed", "GitHub OAuth HTTP request failed", 502);
    } finally {
      abort.cleanup();
    }
    const payload = await parseJsonObject(response);
    if (!response.ok) {
      throw new GitHubOAuthError(
        safeHttpErrorCode(payload.error),
        "GitHub OAuth HTTP request failed",
        response.status,
      );
    }
    return payload as T;
  }
}

export function exportGitHubOAuthOpenApiSpec(): Record<string, unknown> {
  const json = { "application/json": { schema: { type: "object" } } };
  const response = (description: string) => ({ description, content: json });
  const safeError = (description: string) => ({
    description,
    content: {
      "application/json": {
        schema: { $ref: "#/components/schemas/GitHubOAuthSafeError" },
      },
    },
  });
  const discovery = (operationId: string) => ({
    get: {
      operationId,
      responses: { "200": response("GitHub OAuth OpenAPI document") },
    },
  });
  return {
    openapi: GITHUB_OAUTH_OPENAPI_VERSION,
    info: {
      title: "Ashr Clone GitHub OAuth API",
      version: GITHUB_OAUTH_SCHEMA_VERSION,
      description: "PKCE-bound GitHub OAuth runtime with token-reference-only public contracts.",
    },
    paths: {
      "/openapi.json": discovery("getGitHubOAuthOpenApi"),
      "/v1/openapi.json": discovery("getGitHubOAuthOpenApiV1"),
      "/v1/projects/{project_id}/oauth/github/start": {
        get: {
          operationId: "startGitHubOAuthGet",
          parameters: [pathParameter("project_id")],
          responses: { "201": response("GitHub authorization redirect contract"), "400": safeError("Safe OAuth error") },
        },
        post: {
          operationId: "startGitHubOAuth",
          parameters: [pathParameter("project_id")],
          requestBody: { required: false, content: json },
          responses: { "201": response("GitHub authorization redirect contract"), "400": safeError("Safe OAuth error") },
        },
      },
      "/oauth/github/callback": {
        get: {
          operationId: "callbackGitHubOAuthGet",
          parameters: ["state", "code", "error", "error_description"].map(queryParameter),
          responses: { "200": response("GitHub OAuth callback result"), "400": safeError("Safe OAuth error"), "409": safeError("Replay rejected") },
        },
      },
      "/v1/projects/{project_id}/oauth/github/disconnect": {
        post: {
          operationId: "disconnectGitHubOAuth",
          parameters: [pathParameter("project_id")],
          requestBody: { required: true, content: json },
          responses: { "200": response("Revoked GitHub OAuth session"), "404": safeError("Session not found"), "502": safeError("Provider revocation failed") },
        },
        delete: {
          operationId: "disconnectGitHubOAuthDelete",
          parameters: [pathParameter("project_id")],
          requestBody: { required: true, content: json },
          responses: { "200": response("Revoked GitHub OAuth session"), "404": safeError("Session not found"), "502": safeError("Provider revocation failed") },
        },
      },
      "/v1/oauth/github/session/{session_id}": {
        get: {
          operationId: "getGitHubOAuthSession",
          parameters: [pathParameter("session_id")],
          responses: { "200": response("Token-reference-only session"), "404": safeError("Session not found") },
        },
      },
      "/v1/oauth/github/account/{session_id}": {
        get: {
          operationId: "getGitHubOAuthAccount",
          parameters: [pathParameter("session_id")],
          responses: { "200": response("Linked GitHub account"), "401": safeError("Session revoked"), "404": safeError("Account not found") },
        },
      },
    },
    components: {
      schemas: {
        GitHubOAuthSafeError: {
          type: "object",
          required: [
            "schema_version",
            "error",
            "message",
            "status",
            "provider",
            "provider_response_included",
            "secret_value_present",
            "token_value_present",
          ],
          properties: {
            schema_version: { type: "string", enum: [GITHUB_OAUTH_SCHEMA_VERSION] },
            error: { type: "string" },
            message: { type: "string" },
            status: { type: "integer" },
            provider: { type: "string", enum: ["github"] },
            provider_response_included: { type: "boolean", enum: [false] },
            secret_value_present: { type: "boolean", enum: [false] },
            token_value_present: { type: "boolean", enum: [false] },
            provider_status: { type: "integer", nullable: true },
            retryable: { type: "boolean" },
          },
          additionalProperties: false,
        },
      },
    },
    "x-ashr-runtime-contract": {
      provider: "github",
      pkce: "S256",
      state_replay_protection: true,
      token_refs_only: true,
      injectable_fetch: true,
      request_timeout: true,
      abort_signal: true,
      provider_errors_redacted: true,
      real_provider_calls_required: false,
    },
  };
}

function publicSession(session: StoredSession): GitHubOAuthSession {
  return {
    schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
    provider: "github",
    project_id: session.projectId,
    session_id: session.sessionId,
    flow_id: session.flowId,
    status: session.status,
    account_id: session.accountId,
    subject_ref: session.subjectRef,
    access_token_ref_present: session.accessTokenRef !== null,
    granted_scopes: [...session.grantedScopes],
    created_at: session.createdAt,
    revoked_at: session.revokedAt,
    token_value_present: false,
    client_secret_present: false,
  };
}

function publicFlow(flow: PendingFlow): GitHubOAuthFlowSnapshot {
  return {
    schema_version: GITHUB_OAUTH_SCHEMA_VERSION,
    provider: "github",
    project_id: flow.projectId,
    flow_id: flow.flowId,
    status: flow.status,
    state_sha256: flow.stateSha256,
    code_challenge: flow.codeChallenge,
    redirect_uri: flow.redirectUri,
    scopes: [...flow.scopes],
    return_to: flow.returnTo,
    created_at: flow.createdAt,
    expires_at: flow.expiresAt,
    session_id: flow.sessionId,
    failure_code: flow.failureCode,
    raw_state_present: false,
    code_verifier_present: false,
  };
}

function cloneAccount(account: GitHubOAuthAccount): GitHubOAuthAccount {
  return { ...account };
}

function cloneToken(token: GitHubOAuthTokenMaterial): GitHubOAuthTokenMaterial {
  return { accessToken: token.accessToken, tokenType: token.tokenType, scopes: [...token.scopes] };
}

function secureRandomBytes(size: number): Uint8Array {
  const bytes = new Uint8Array(size);
  globalThis.crypto.getRandomValues(bytes);
  return bytes;
}

function randomBase64Url(randomBytes: (size: number) => Uint8Array, size: number): string {
  return Buffer.from(randomBytes(size)).toString("base64url");
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function constantEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

function normalizeEndpoint(value: string): string {
  const parsed = new URL(value);
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname))) {
    throw new GitHubOAuthError("invalid_endpoint", "GitHub OAuth endpoints must use HTTPS or localhost", 400);
  }
  if (parsed.username || parsed.password || parsed.hash) throw new GitHubOAuthError("invalid_endpoint", "GitHub OAuth endpoint is invalid", 400);
  return value.replace(/\/+$/u, "");
}

function normalizeReturnTo(value: string | undefined): string | null {
  if (value === undefined) return null;
  const text = boundedText("return_to", value, 2048);
  if (!text.startsWith("/") || text.startsWith("//") || text.includes("\\")) {
    throw new GitHubOAuthError("invalid_return_to", "return_to must be an application-relative path", 400);
  }
  return text;
}

function validateResolvedClientId(value: string): string {
  const clientId = boundedText("client id", value, 256);
  if (/\s/u.test(clientId)) throw new GitHubOAuthError("invalid_client_id", "Resolved client id is invalid", 500);
  return clientId;
}

function validateTokenRef(reference: string): string {
  if (!/^(?:vault|kms|provider-ref):[^\s]+$/u.test(reference)) {
    throw new GitHubOAuthError("invalid_token_reference", "Token store returned an unsafe reference", 500);
  }
  return reference;
}

function boundedSecret(name: string, value: string | undefined): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 4096 || /[\r\n]/u.test(value)) {
    throw new GitHubOAuthError(`${name.replaceAll(" ", "_")}_missing`, `${name} is missing or invalid`, 400);
  }
  return value;
}

function boundedText(name: string, value: string, max: number): string {
  const text = value.trim();
  if (!text || text.length > max || /[\u0000-\u001f\u007f]/u.test(text)) {
    throw new GitHubOAuthError(`invalid_${name.replaceAll(" ", "_")}`, `${name} is invalid`, 400);
  }
  return text;
}

function boundedId(name: string, value: string): string {
  const text = boundedText(name, value, 256);
  if (!/^[A-Za-z0-9._:-]+$/u.test(text)) throw new GitHubOAuthError(`invalid_${name}`, `${name} is invalid`, 400);
  return text;
}

function optionalBoundedText(value: unknown, max: number): string | null {
  if (value === undefined || value === null || value === "") return null;
  return boundedText("provider field", stringValue(value), max);
}

function optionalHttpsUrl(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  const text = stringValue(value);
  try {
    const url = new URL(text);
    return url.protocol === "https:" && !url.username && !url.password ? text : null;
  } catch {
    return null;
  }
}

function positiveInteger(value: unknown, name: string): number {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number <= 0) throw new GitHubOAuthProviderError("invalid_account_response", { providerStatus: 200, retryable: false });
  return number;
}

function parseScopes(value: unknown, fallback: readonly string[]): string[] {
  if (typeof value !== "string") return [...fallback];
  const scopes = value.split(/[,\s]+/u).map((item) => item.trim()).filter(Boolean).map((scope) => boundedText("scope", scope, 256));
  return scopes.length === 0 ? [...fallback] : unique(scopes);
}

async function parseProviderPayload(response: Response): Promise<Record<string, unknown> & GitHubTokenResponse & GitHubUserResponse> {
  const parsed = await parseProviderJson(response);
  if (isRecord(parsed)) return parsed;
  throw new GitHubOAuthProviderError("invalid_provider_response", { providerStatus: response.status, retryable: false });
}

async function parseProviderJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length > 1_000_000) throw new GitHubOAuthProviderError("provider_response_too_large", { providerStatus: response.status });
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    if (!text.includes("=")) {
      throw new GitHubOAuthProviderError("invalid_provider_response", { providerStatus: response.status, retryable: false });
    }
    const params = new URLSearchParams(text);
    return Object.fromEntries(params);
  }
}

function validateTokenType(value: unknown, providerStatus: number): string {
  const tokenType = optionalBoundedText(value, 64);
  if (tokenType === null || tokenType.toLowerCase() !== "bearer") {
    throw new GitHubOAuthProviderError("unsupported_token_type", { providerStatus, retryable: false });
  }
  return "bearer";
}

function validateGrantedScopes(granted: string[], requested: readonly string[], providerStatus: number): string[] {
  const requestedSet = new Set(requested);
  if (granted.some((scope) => !requestedSet.has(scope))) {
    throw new GitHubOAuthProviderError("scope_escalation", { providerStatus, retryable: false });
  }
  return granted;
}

function validateTimeoutMs(value: number | undefined): number {
  const timeoutMs = value ?? 10_000;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 300_000) {
    throw new GitHubOAuthError("invalid_timeout", "OAuth request timeout is invalid", 400);
  }
  return timeoutMs;
}

function composeAbortSignals(timeoutMs: number, signals: readonly (AbortSignal | null | undefined)[]): {
  signal: AbortSignal;
  timedOut: () => boolean;
  cleanup: () => void;
} {
  const controller = new AbortController();
  let timeoutTriggered = false;
  const listeners: Array<{ signal: AbortSignal; listener: () => void }> = [];
  for (const signal of signals) {
    if (signal === undefined || signal === null) continue;
    if (signal.aborted) {
      controller.abort();
      break;
    }
    const listener = () => controller.abort();
    signal.addEventListener("abort", listener, { once: true });
    listeners.push({ signal, listener });
  }
  const timer = setTimeout(() => {
    timeoutTriggered = true;
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    timedOut: () => timeoutTriggered,
    cleanup: () => {
      clearTimeout(timer);
      for (const item of listeners) item.signal.removeEventListener("abort", item.listener);
    },
  };
}

async function parseJsonObject(response: Response): Promise<Record<string, unknown>> {
  const text = await response.text();
  if (!text) return {};
  try {
    const value = JSON.parse(text);
    return isRecord(value) ? value : {};
  } catch {
    throw new GitHubOAuthError("invalid_http_response", "GitHub OAuth HTTP response was not JSON", 502);
  }
}

function providerCode(payload: Record<string, unknown>, fallback: string): string {
  return safeProviderCode(payload.error, fallback);
}

function safeProviderCode(value: unknown, fallback: string): string {
  const code = typeof value === "string" ? normalizeErrorCode(value) : normalizeErrorCode(fallback);
  const allowed = new Set([
    "access_denied",
    "bad_verification_code",
    "incorrect_client_credentials",
    "redirect_uri_mismatch",
    "unverified_user_email",
  ]);
  return allowed.has(code) ? code : normalizeErrorCode(fallback);
}

function safeHttpErrorCode(value: unknown): string {
  const code = typeof value === "string" ? normalizeErrorCode(value) : "http_request_failed";
  const allowed = new Set([
    "account_not_found",
    "callback_replay",
    "flow_expired",
    "flow_not_found",
    "invalid_boolean",
    "invalid_http_response",
    "invalid_return_to",
    "http_request_aborted",
    "http_request_timeout",
    "missing_flow_id",
    "missing_session_id",
    "provider_authorization_failed",
    "provider_revoke_failed",
    "provider_request_aborted",
    "provider_request_timeout",
    "route_not_found",
    "session_not_found",
    "session_revoked",
    "state_mismatch",
    "token_exchange_failed",
    "scope_escalation",
    "unsupported_token_type",
    "token_reference_missing",
    "token_reference_unresolved",
  ]);
  return allowed.has(code) ? code : "http_request_failed";
}

function normalizeErrorCode(value: string): string {
  const normalized = value.toLowerCase().replace(/[^a-z0-9._-]+/gu, "_").replace(/^_+|_+$/gu, "").slice(0, 80);
  return normalized || "provider_error";
}

function providerErrorMessage(code: string): string {
  const safeCode = normalizeErrorCode(code);
  const messages: Record<string, string> = {
    access_denied: "GitHub authorization was denied",
    bad_verification_code: "GitHub rejected the authorization code",
    incorrect_client_credentials: "GitHub rejected the OAuth client credentials",
    redirect_uri_mismatch: "GitHub rejected the redirect URI",
    unverified_user_email: "GitHub requires a verified user email",
  };
  return messages[safeCode] ?? "GitHub OAuth provider request failed";
}

function redactRuntimeError(error: unknown): GitHubOAuthError {
  if (error instanceof GitHubOAuthError) return error;
  if (error instanceof OAuthProviderContractError) return new GitHubOAuthError("invalid_oauth_contract", error.message, 400);
  return new GitHubOAuthError("github_oauth_internal_error", "GitHub OAuth request failed", 500);
}

function encodeBasicAuth(username: string, password: string): string {
  return Buffer.from(`${username}:${password}`, "utf8").toString("base64");
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value === "") throw new GitHubOAuthError(`missing_${name}`, `${name} is required`, 400);
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

function optionalBoolean(value: unknown): boolean | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  throw new GitHubOAuthError("invalid_boolean", "Boolean query value is invalid", 400);
}

function unique<T>(values: readonly T[]): T[] {
  return [...new Set(values)];
}

function stripUndefined(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

function pathParameter(name: string): Record<string, unknown> {
  return { name, in: "path", required: true, schema: { type: "string" } };
}

function queryParameter(name: string): Record<string, unknown> {
  return { name, in: "query", required: name === "state", schema: { type: "string" } };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
