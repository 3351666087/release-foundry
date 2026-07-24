export type OAuthProvider = "google" | "github";

export const authContractCapabilities = {
  sourceSha: "6897997",
  sourceState: "merged_to_a3",
  oauthAccountLinking: true,
  oauthInitialLoginCoordinator: true,
  oauthInitialLogin: false,
  emailRegistration: true,
  emailLogin: true,
  emailChallengeRequest: true,
  emailBrowserCompletion: true,
  emailLoginSessionCookie: true,
  browserIdentityRead: true,
  browserLogout: true,
  browserSessionRefresh: true,
  productionReady: false
} as const;

export type AuthRuntimeConfig = {
  apiBaseUrl: string | null;
  projectId: string;
  tenantId: string;
  configured: boolean;
  scopeConfigured: boolean;
  reason:
    | "ready"
    | "api_base_missing"
    | "api_base_invalid"
    | "browser_origin_insecure"
    | "browser_origin_mismatch";
};

type OAuthAccountLinkStartResponse = {
  schema_version: string;
  provider: OAuthProvider;
  authorize_url: string;
  expires_at: string;
};

export type EmailIdentityChallenge = {
  schema_version: string;
  challenge_id: string;
  intent_id: string;
  expires_at: string;
  resend_after: string;
};

export type EmailIdentityCompletion = {
  status: "authenticated";
  redirect_to: "/console";
};

export type IdentitySessionRefreshResponse = {
  schema_version: "ashr.identity_session_refresh.v1";
  status: "rotated";
};

export type CurrentIdentity = {
  schema_version: string;
  account_id: string;
  primary_principal_id: string;
  display_name?: string;
  status: string;
  credential_count: number;
  membership_count: number;
};

const rawApiBase = process.env.NEXT_PUBLIC_A1_API_BASE_URL || "";
const projectId = (process.env.NEXT_PUBLIC_A1_PROJECT_ID || "").trim();
const tenantId = (process.env.NEXT_PUBLIC_A1_TENANT_ID || "").trim();

export class AuthApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number | null = null
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

export function getAuthRuntimeConfig(): AuthRuntimeConfig {
  const apiBaseUrl = normalizeApiBase(rawApiBase);
  let reason: AuthRuntimeConfig["reason"] = "ready";
  if (!rawApiBase.trim()) reason = "api_base_missing";
  else if (!apiBaseUrl) reason = "api_base_invalid";
  else if (typeof window !== "undefined" && window.location.protocol !== "https:") reason = "browser_origin_insecure";
  else if (typeof window !== "undefined" && new URL(apiBaseUrl).origin !== window.location.origin) reason = "browser_origin_mismatch";
  return {
    apiBaseUrl,
    projectId,
    tenantId,
    configured: reason === "ready",
    scopeConfigured: reason === "ready" && Boolean(projectId) && Boolean(tenantId),
    reason
  };
}

export async function startOAuthAccountLinking(provider: OAuthProvider): Promise<OAuthAccountLinkStartResponse> {
  const config = requireScopedConfig();
  const payload = await fetchJson(
    `${config.apiBaseUrl}/v1/projects/${encodeURIComponent(config.projectId)}/oauth/${provider}/start`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Ashr-Tenant-ID": config.tenantId
      },
      credentials: "include",
      body: JSON.stringify({ tenant_id: config.tenantId })
    }
  );
  const authorizeUrl = readString(payload, "authorize_url");
  validateProviderUrl(provider, authorizeUrl);
  return {
    schema_version: readString(payload, "schema_version"),
    provider,
    authorize_url: authorizeUrl,
    expires_at: readString(payload, "expires_at")
  };
}

export async function beginEmailRegistration(email: string): Promise<EmailIdentityChallenge> {
  return beginEmailIdentity("registration", email);
}

export async function beginEmailLogin(email: string): Promise<EmailIdentityChallenge> {
  return beginEmailIdentity("login", email);
}

async function beginEmailIdentity(
  purpose: "registration" | "login",
  email: string
): Promise<EmailIdentityChallenge> {
  const config = requireBrowserConfig();
  const payload = await fetchJson(`${config.apiBaseUrl}/v1/identity/${purpose}/email/begin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email: normalizeEmail(email) })
  });
  return {
    schema_version: readString(payload, "schema_version"),
    challenge_id: readString(payload, "challenge_id"),
    intent_id: readString(payload, "intent_id"),
    expires_at: readDateString(payload, "expires_at"),
    resend_after: readDateString(payload, "resend_after")
  };
}

export async function completeEmailRegistration(input: {
  challengeId: string;
  intentId: string;
  code: string;
  displayName: string;
}): Promise<EmailIdentityCompletion> {
  return completeEmailIdentity("registration", {
    challengeId: input.challengeId,
    intentId: input.intentId,
    code: input.code,
    displayName: input.displayName
  });
}

export async function completeEmailLogin(input: {
  challengeId: string;
  intentId: string;
  code: string;
}): Promise<EmailIdentityCompletion> {
  return completeEmailIdentity("login", input);
}

async function completeEmailIdentity(
  purpose: "registration" | "login",
  input: { challengeId: string; intentId: string; code: string; displayName?: string }
): Promise<EmailIdentityCompletion> {
  const config = requireBrowserConfig();
  const code = input.code.trim();
  if (!/^\d{6}$/.test(code)) throw new AuthApiError("Enter a six-digit verification code.", "verification_code_invalid");
  const challengeId = normalizeHandle(input.challengeId, "challenge_id");
  const intentId = normalizeHandle(input.intentId, "intent_id");
  const body: Record<string, string> = {
    challenge_id: challengeId,
    intent_id: intentId,
    proof: code
  };
  if (purpose === "registration") {
    const displayName = input.displayName?.trim();
    if (!displayName) throw new AuthApiError("Enter a display name.", "display_name_missing");
    body.display_name = displayName;
  }
  return fetchIdentityCompletion(`${config.apiBaseUrl}/v1/identity/${purpose}/email/complete`, body);
}

export async function refreshIdentitySession(accountId: string): Promise<IdentitySessionRefreshResponse> {
  const config = requireScopedConfig();
  const apiOrigin = new URL(config.apiBaseUrl).origin;
  if (window.location.origin !== apiOrigin) {
    throw new AuthApiError(
      "Browser session refresh requires the webapp and identity API to share one origin.",
      "identity_session_same_origin_required"
    );
  }
  const normalizedAccountId = normalizeScopeId(accountId, "account_id");
  const payload = await fetchJson(
    `${config.apiBaseUrl}/v1/projects/${encodeURIComponent(config.projectId)}/accounts/${encodeURIComponent(normalizedAccountId)}/browser-sessions/refresh`,
    {
      method: "POST",
      headers: { "Idempotency-Key": `a3-refresh-${crypto.randomUUID()}` },
      credentials: "include"
    }
  );
  if (readString(payload, "status") !== "rotated") {
    throw new AuthApiError("The identity service returned an unexpected session refresh status.", "identity_session_refresh_invalid");
  }
  return {
    schema_version: "ashr.identity_session_refresh.v1",
    status: "rotated"
  };
}

export async function getCurrentIdentity(): Promise<CurrentIdentity> {
  const config = requireBrowserConfig();
  const payload = await fetchJson(`${config.apiBaseUrl}/v1/me`, {
    method: "GET",
    credentials: "include"
  });
  return {
    schema_version: readString(payload, "schema_version"),
    account_id: readString(payload, "account_id"),
    primary_principal_id: readString(payload, "primary_principal_id"),
    display_name: optionalString(payload.display_name),
    status: readString(payload, "status"),
    credential_count: readNonNegativeInteger(payload, "credential_count"),
    membership_count: readNonNegativeInteger(payload, "membership_count")
  };
}

export async function logoutIdentity(): Promise<void> {
  const config = requireBrowserConfig();
  let payload: Record<string, unknown>;
  try {
    payload = await fetchJson(`${config.apiBaseUrl}/v1/identity/sessions/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: "{}"
    });
  } catch (error) {
    // A missing or already-revoked session is already in the requested state.
    if (error instanceof AuthApiError && error.status === 401) return;
    throw error;
  }
  if (readString(payload, "status") !== "revoked") {
    throw new AuthApiError("The identity service did not confirm logout.", "identity_logout_invalid");
  }
}

function requireBrowserConfig(): AuthRuntimeConfig & { apiBaseUrl: string } {
  const config = getAuthRuntimeConfig();
  if (!config.configured || !config.apiBaseUrl) {
    throw new AuthApiError("The identity service is not configured for this build.", config.reason);
  }
  return { ...config, apiBaseUrl: config.apiBaseUrl };
}

function requireScopedConfig(): AuthRuntimeConfig & { apiBaseUrl: string } {
  const config = requireBrowserConfig();
  if (!config.projectId) throw new AuthApiError("The identity project is not configured.", "project_missing");
  if (!config.tenantId) throw new AuthApiError("The identity tenant is not configured.", "tenant_missing");
  return config;
}

function normalizeApiBase(value: string): string | null {
  try {
    const url = new URL(value.trim());
    const loopback = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
    if (url.username || url.password || url.search || url.hash) return null;
    if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) return null;
    return url.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

function validateProviderUrl(provider: OAuthProvider, value: string) {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new AuthApiError("The identity service returned an invalid OAuth authorization URL.", "oauth_authorize_url_invalid");
  }
  const expectedHost = provider === "google" ? "accounts.google.com" : "github.com";
  if (url.protocol !== "https:" || url.hostname !== expectedHost || url.username || url.password) {
    throw new AuthApiError("The identity service returned an untrusted OAuth authorization URL.", "oauth_authorize_url_untrusted");
  }
}

function normalizeEmail(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
    throw new AuthApiError("Enter a valid email address.", "email_invalid");
  }
  return normalized;
}

function normalizeScopeId(value: string, field: string) {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{1,255}$/.test(normalized)) {
    throw new AuthApiError(`${field} is invalid.`, "identity_scope_invalid");
  }
  return normalized;
}

function normalizeHandle(value: string, field: "challenge_id" | "intent_id") {
  const normalized = value.trim();
  if (!/^[A-Za-z0-9._:-]{8,256}$/.test(normalized)) {
    throw new AuthApiError(`Secure ${field} context is missing.`, "verification_challenge_missing");
  }
  return normalized;
}

async function fetchIdentityCompletion(
  url: string,
  body: Record<string, string>
): Promise<EmailIdentityCompletion> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      cache: "no-store",
      redirect: "follow",
      signal: controller.signal,
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      const payload = await readResponsePayload(response);
      throw new AuthApiError(
        optionalString(payload.message) || publicErrorMessage(response.status),
        optionalString(payload.code) || `http_${response.status}`,
        response.status
      );
    }
    const finalUrl = new URL(response.url);
    if (!response.redirected || finalUrl.origin !== window.location.origin || finalUrl.pathname !== "/console") {
      throw new AuthApiError("The identity service did not complete the trusted console handoff.", "identity_handoff_invalid");
    }
    return { status: "authenticated", redirect_to: "/console" };
  } catch (error) {
    if (error instanceof AuthApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new AuthApiError("The identity service timed out.", "identity_service_timeout");
    }
    throw new AuthApiError("The identity service could not be reached.", "identity_service_unreachable");
  } finally {
    window.clearTimeout(timeout);
  }
}

async function fetchJson(url: string, init: RequestInit): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal, cache: "no-store" });
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new AuthApiError(
        optionalString(payload.message) || publicErrorMessage(response.status),
        optionalString(payload.code) || `http_${response.status}`,
        response.status
      );
    }
    return payload;
  } catch (error) {
    if (error instanceof AuthApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new AuthApiError("The identity service timed out.", "identity_service_timeout");
    }
    throw new AuthApiError("The identity service could not be reached.", "identity_service_unreachable");
  } finally {
    window.clearTimeout(timeout);
  }
}

async function readResponsePayload(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload: unknown = await response.json();
    return payload !== null && typeof payload === "object" && !Array.isArray(payload)
      ? payload as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function readString(record: Record<string, unknown>, key: string) {
  const value = optionalString(record[key]);
  if (!value) throw new AuthApiError(`The identity response is missing ${key}.`, "identity_response_invalid");
  return value;
}

function readDateString(record: Record<string, unknown>, key: string) {
  const value = readString(record, key);
  if (Number.isNaN(Date.parse(value))) {
    throw new AuthApiError(`The identity response contains an invalid ${key}.`, "identity_response_invalid");
  }
  return value;
}

function readNonNegativeInteger(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new AuthApiError(`The identity response contains an invalid ${key}.`, "identity_response_invalid");
  }
  return value;
}

function optionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function publicErrorMessage(status: number) {
  if (status === 401) return "A trusted identity session is required.";
  if (status === 403) return "This identity action is outside the current tenant scope.";
  if (status === 429) return "Too many attempts. Wait before trying again.";
  if (status === 503) return "The requested identity provider is not configured.";
  return "The identity request could not be completed.";
}
