export type OAuthProvider = "google" | "github";

export type AuthRuntimeConfig = {
  apiBaseUrl: string | null;
  projectId: string;
  tenantId: string;
  configured: boolean;
  reason: "ready" | "api_base_missing" | "api_base_invalid" | "project_missing" | "tenant_missing";
};

type OAuthStartResponse = {
  schema_version: string;
  provider: OAuthProvider;
  authorize_url: string;
  expires_at: string;
};

type VerificationStartResponse = {
  schema_version: string;
  status: "accepted";
  message: string;
};

export type VerificationCompleteResponse = {
  schema_version: string;
  challenge_id: string;
  credential_created: boolean;
  verified_at: string;
  account: {
    account_id: string;
    status: string;
    display_name?: string;
  };
  credential: {
    credential_id: string;
    kind: string;
    verified: boolean;
  };
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
  else if (!projectId) reason = "project_missing";
  else if (!tenantId) reason = "tenant_missing";
  return {
    apiBaseUrl,
    projectId,
    tenantId,
    configured: reason === "ready",
    reason
  };
}

export async function startOAuth(provider: OAuthProvider): Promise<OAuthStartResponse> {
  const config = requireConfig();
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

export async function requestEmailVerification(email: string): Promise<VerificationStartResponse> {
  const config = requireConfig();
  const payload = await fetchJson(`${config.apiBaseUrl}/v1/identity-verification/challenges`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      channel: "email",
      identifier: normalizeEmail(email),
      purpose: "binding",
      tenant_id: config.tenantId
    })
  });
  const status = readString(payload, "status");
  if (status !== "accepted") {
    throw new AuthApiError("Identity verification returned an unexpected status.", "verification_response_invalid");
  }
  return {
    schema_version: readString(payload, "schema_version"),
    status: "accepted",
    message: readString(payload, "message")
  };
}

export async function completeEmailVerification(input: {
  challengeId: string;
  code: string;
  email: string;
  displayName: string;
}): Promise<VerificationCompleteResponse> {
  const config = requireConfig();
  const code = input.code.trim();
  if (!/^\d{6}$/.test(code)) throw new AuthApiError("Enter a six-digit verification code.", "verification_code_invalid");
  if (!input.challengeId.trim()) throw new AuthApiError("Secure challenge context is missing.", "verification_challenge_missing");
  const payload = await fetchJson(`${config.apiBaseUrl}/v1/identity-verification/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      challenge_id: input.challengeId.trim(),
      code,
      channel: "email",
      identifier: normalizeEmail(input.email),
      purpose: "binding",
      tenant_id: config.tenantId,
      display_name: input.displayName.trim()
    })
  });
  const account = readRecord(payload, "account");
  const credential = readRecord(payload, "credential");
  return {
    schema_version: readString(payload, "schema_version"),
    challenge_id: readString(payload, "challenge_id"),
    credential_created: payload.credential_created === true,
    verified_at: readString(payload, "verified_at"),
    account: {
      account_id: readString(account, "account_id"),
      status: readString(account, "status"),
      display_name: optionalString(account.display_name)
    },
    credential: {
      credential_id: readString(credential, "credential_id"),
      kind: readString(credential, "kind"),
      verified: credential.verified === true
    }
  };
}

function requireConfig(): AuthRuntimeConfig & { apiBaseUrl: string } {
  const config = getAuthRuntimeConfig();
  if (!config.configured || !config.apiBaseUrl) {
    throw new AuthApiError("A1 identity service is not configured for this build.", config.reason);
  }
  return { ...config, apiBaseUrl: config.apiBaseUrl };
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
    throw new AuthApiError("A1 returned an invalid OAuth authorization URL.", "oauth_authorize_url_invalid");
  }
  const expectedHost = provider === "google" ? "accounts.google.com" : "github.com";
  if (url.protocol !== "https:" || url.hostname !== expectedHost || url.username || url.password) {
    throw new AuthApiError("A1 returned an untrusted OAuth authorization URL.", "oauth_authorize_url_untrusted");
  }
}

function normalizeEmail(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
    throw new AuthApiError("Enter a valid email address.", "email_invalid");
  }
  return normalized;
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
      throw new AuthApiError("A1 identity service timed out.", "identity_service_timeout");
    }
    throw new AuthApiError("A1 identity service could not be reached.", "identity_service_unreachable");
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
  if (!value) throw new AuthApiError(`A1 response is missing ${key}.`, "identity_response_invalid");
  return value;
}

function readRecord(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new AuthApiError(`A1 response is missing ${key}.`, "identity_response_invalid");
  }
  return value as Record<string, unknown>;
}

function optionalString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function publicErrorMessage(status: number) {
  if (status === 401) return "A trusted A1 identity session is required.";
  if (status === 403) return "This identity action is outside the current tenant scope.";
  if (status === 429) return "Too many attempts. Wait before trying again.";
  if (status === 503) return "The requested identity provider is not configured in A1.";
  return "The identity request could not be completed.";
}
