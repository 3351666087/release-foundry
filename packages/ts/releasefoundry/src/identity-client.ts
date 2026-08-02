export const IDENTITY_SCHEMA_VERSION = "releasefoundry.identity.v1";
export const IDENTITY_DEFAULT_BASE_URL = "http://127.0.0.1:8787";

export type IdentityJson = Record<string, unknown>;
export type OAuthIntent = "registration" | "login" | "link";

export interface IdentityTransportRequest {
  method: string;
  url: string;
  headers: Record<string, string>;
  body?: string;
  timeoutMs: number;
}

export interface IdentityTransportResponse {
  status: number;
  body: string | IdentityJson;
  headers?: Record<string, string>;
}

export type IdentityTransport = (
  request: IdentityTransportRequest,
) => Promise<IdentityTransportResponse>;

const SECRET_PATTERNS = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /"(?:session_token|binding_ticket_proof|proof|code|state)"\s*:\s*"[^"]+"/gi,
];

function redactText(value: string): string {
  return SECRET_PATTERNS.reduce((safe, pattern) => safe.replace(pattern, "[redacted]"), value);
}

export class IdentityClientError extends Error {
  readonly code: string;
  readonly statusCode?: number;

  constructor(
    message: string,
    options: { code?: string; statusCode?: number; cause?: unknown } = {},
  ) {
    super(redactText(message), { cause: options.cause });
    this.name = "IdentityClientError";
    this.code = options.code ?? "identity_client_error";
    this.statusCode = options.statusCode;
  }

  toJSON(): IdentityJson {
    return {
      code: this.code,
      message: this.message,
      status_code: this.statusCode ?? null,
    };
  }
}

export class IdentitySessionCredential {
  readonly accountId: string;
  readonly sessionId: string;
  readonly expiresAt: string;
  #sessionToken: string;

  constructor(options: {
    accountId: string;
    sessionId: string;
    sessionToken: string;
    expiresAt: string;
  }) {
    this.accountId = options.accountId;
    this.sessionId = options.sessionId;
    this.expiresAt = options.expiresAt;
    this.#sessionToken = options.sessionToken;
  }

  headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.#sessionToken}`,
      "X-ReleaseFoundry-Session-ID": this.sessionId,
    };
  }

  toJSON(): IdentityJson {
    return {
      account_id: this.accountId,
      session_id: this.sessionId,
      expires_at: this.expiresAt,
      session_token_present: this.#sessionToken.length > 0,
    };
  }
}

export interface IdentityChallenge {
  challengeId: string;
  purpose: string;
  deliveryMethod: string;
  deliveryHint: string;
  expiresAt: string;
}

export interface MFARequired {
  status: "mfa_required";
  mfaChallengeId: string;
  expiresAt: string;
}

export class OAuthBegin {
  readonly flowId: string;
  readonly provider: string;
  readonly intent: OAuthIntent;
  readonly expiresAt: string;
  #authorizationUrl: string;

  constructor(options: {
    flowId: string;
    provider: string;
    intent: OAuthIntent;
    authorizationUrl: string;
    expiresAt: string;
  }) {
    this.flowId = options.flowId;
    this.provider = options.provider;
    this.intent = options.intent;
    this.expiresAt = options.expiresAt;
    this.#authorizationUrl = options.authorizationUrl;
  }

  authorizationUrl(): string {
    return this.#authorizationUrl;
  }

  toJSON(): IdentityJson {
    return {
      flow_id: this.flowId,
      provider: this.provider,
      intent: this.intent,
      expires_at: this.expiresAt,
      authorization_url_present: this.#authorizationUrl.length > 0,
    };
  }
}

export class OAuthBindingTicket {
  readonly bindingTicketId: string;
  readonly provider: string;
  readonly expiresAt: string;
  #bindingTicketProof: string;

  constructor(options: {
    bindingTicketId: string;
    bindingTicketProof: string;
    provider: string;
    expiresAt: string;
  }) {
    this.bindingTicketId = options.bindingTicketId;
    this.provider = options.provider;
    this.expiresAt = options.expiresAt;
    this.#bindingTicketProof = options.bindingTicketProof;
  }

  bindingProof(): string {
    return this.#bindingTicketProof;
  }

  toJSON(): IdentityJson {
    return {
      binding_ticket_id: this.bindingTicketId,
      provider: this.provider,
      expires_at: this.expiresAt,
      binding_ticket_proof_present: this.#bindingTicketProof.length > 0,
    };
  }
}

export interface IdentityCredentialView {
  provider: string;
  kind: string;
}

export interface TwoFactorView {
  enabled: boolean;
  recommended: boolean;
  methods: string[];
}

export interface ProviderCapability {
  provider: string;
  kind: string;
  enabled: boolean;
  region: string;
  supportsRegistration: boolean;
  supportsLogin: boolean;
  supportsExplicitBinding: boolean;
  pkceRequired: boolean;
}

export interface IdentityView {
  accountId: string;
  primaryEmailHint: string;
  displayName: string;
  locale: string;
  region: string;
  status: string;
  preferredRegistrationMethod: string;
  credentials: IdentityCredentialView[];
  twoFactor: TwoFactorView;
  providerCapabilities: ProviderCapability[];
}

export type IdentityAuthResult = IdentitySessionCredential | MFARequired;
export type OAuthCompletion =
  | IdentityView
  | IdentityAuthResult
  | OAuthBindingTicket;

export interface IdentityClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  transport?: IdentityTransport;
  session?: IdentitySessionCredential;
}

export class IdentityClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  readonly #transport: IdentityTransport;
  readonly #session?: IdentitySessionCredential;

  constructor(options: IdentityClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? IDENTITY_DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = Math.max(1, Math.trunc(options.timeoutMs ?? 30_000));
    this.#transport = options.transport ?? fetchIdentityTransport;
    this.#session = options.session;
  }

  withSession(session?: IdentitySessionCredential): IdentityClient {
    return new IdentityClient({
      baseUrl: this.baseUrl,
      timeoutMs: this.timeoutMs,
      transport: this.#transport,
      session,
    });
  }

  async beginEmailRegistration(
    email: string,
    options: { locale?: string; region?: string } = {},
  ): Promise<IdentityChallenge> {
    const payload: IdentityJson = { email };
    if (options.locale) payload.locale = options.locale;
    if (options.region) payload.region = options.region;
    return parseChallenge(
      await this.request("POST", "/v1/identity/registration/email/begin", payload),
    );
  }

  async completeEmailRegistration(
    challengeId: string,
    proof: string,
    options: { displayName?: string } = {},
  ): Promise<IdentityView> {
    const payload: IdentityJson = { challenge_id: challengeId, proof };
    if (options.displayName) payload.display_name = options.displayName;
    const response = await this.request(
      "POST",
      "/v1/identity/registration/email/complete",
      payload,
    );
    return parseIdentity(objectValue(response.identity, "identity"));
  }

  async beginEmailLogin(email: string): Promise<IdentityChallenge> {
    return parseChallenge(
      await this.request("POST", "/v1/identity/login/email/begin", { email }),
    );
  }

  async completeEmailLogin(
    challengeId: string,
    proof: string,
  ): Promise<IdentityAuthResult> {
    return parseAuth(
      await this.request("POST", "/v1/identity/login/email/complete", {
        challenge_id: challengeId,
        proof,
      }),
    );
  }

  async completeMfa(
    challengeId: string,
    proof: string,
  ): Promise<IdentitySessionCredential> {
    const result = parseAuth(
      await this.request("POST", "/v1/identity/mfa/complete", {
        challenge_id: challengeId,
        proof,
      }),
    );
    if (!(result instanceof IdentitySessionCredential)) {
      throw new IdentityClientError("MFA completion returned another MFA challenge", {
        code: "invalid_response",
      });
    }
    return result;
  }

  async beginOAuth(
    provider: string,
    intent: OAuthIntent,
    redirectUri: string,
    options: { session?: IdentitySessionCredential } = {},
  ): Promise<OAuthBegin> {
    if (!["registration", "login", "link"].includes(intent)) {
      throw new TypeError("intent must be registration, login, or link");
    }
    const response = await this.request(
      "POST",
      "/v1/identity/oauth/begin",
      { provider, intent, redirect_uri: redirectUri },
      intent === "link" ? this.requiredSession(options.session) : undefined,
    );
    const responseIntent = stringValue(response, "intent");
    if (!["registration", "login", "link"].includes(responseIntent)) {
      throw invalidResponse("intent must be registration, login, or link");
    }
    return new OAuthBegin({
      flowId: stringValue(response, "flow_id"),
      provider: stringValue(response, "provider"),
      intent: responseIntent as OAuthIntent,
      authorizationUrl: stringValue(response, "authorization_url"),
      expiresAt: stringValue(response, "expires_at"),
    });
  }

  async completeOAuth(
    flowId: string,
    state: string,
    code: string,
    options: {
      registrationDisplayName?: string;
      registrationLocale?: string;
      registrationRegion?: string;
    } = {},
  ): Promise<OAuthCompletion> {
    const payload: IdentityJson = { flow_id: flowId, state, code };
    if (options.registrationDisplayName) {
      payload.display_name = options.registrationDisplayName;
    }
    if (options.registrationLocale) payload.locale = options.registrationLocale;
    if (options.registrationRegion) payload.region = options.registrationRegion;
    const response = await this.request(
      "POST",
      "/v1/identity/oauth/complete",
      payload,
    );
    const status = stringValue(response, "status");
    if (status === "registered" || status === "bound") {
      return parseIdentity(objectValue(response.identity, "identity"));
    }
    if (status === "authenticated" || status === "mfa_required") {
      return parseAuth(response);
    }
    if (status === "binding_ticket_issued") {
      return new OAuthBindingTicket({
        bindingTicketId: stringValue(response, "binding_ticket_id"),
        bindingTicketProof: stringValue(response, "binding_ticket_proof"),
        provider: stringValue(response, "provider"),
        expiresAt: stringValue(response, "expires_at"),
      });
    }
    throw invalidResponse("unexpected OAuth completion response");
  }

  async bindCredential(
    ticket: OAuthBindingTicket,
    options: {
      explicitConsent: boolean;
      session?: IdentitySessionCredential;
    },
  ): Promise<IdentityView> {
    if (options.explicitConsent !== true) {
      throw new TypeError("explicitConsent must be true");
    }
    const response = await this.request(
      "POST",
      "/v1/identity/credentials/bind",
      {
        binding_ticket_id: ticket.bindingTicketId,
        binding_ticket_proof: ticket.bindingProof(),
        explicit_consent: true,
      },
      this.requiredSession(options.session),
    );
    return parseIdentity(objectValue(response.identity, "identity"));
  }

  async me(options: { session?: IdentitySessionCredential } = {}): Promise<IdentityView> {
    return parseIdentity(
      await this.request(
        "GET",
        "/v1/me",
        undefined,
        this.requiredSession(options.session),
      ),
    );
  }

  async revokeSession(
    options: { session?: IdentitySessionCredential } = {},
  ): Promise<void> {
    const response = await this.request(
      "POST",
      "/v1/identity/sessions/revoke",
      {},
      this.requiredSession(options.session),
    );
    if (stringValue(response, "status") !== "revoked") {
      throw invalidResponse("unexpected session revoke response");
    }
  }

  private requiredSession(
    session?: IdentitySessionCredential,
  ): IdentitySessionCredential {
    const selected = session ?? this.#session;
    if (!selected) {
      throw new IdentityClientError("authenticated session is required", {
        code: "session_required",
      });
    }
    return selected;
  }

  private async request(
    method: string,
    path: string,
    payload?: IdentityJson,
    session?: IdentitySessionCredential,
  ): Promise<IdentityJson> {
    const headers: Record<string, string> = { Accept: "application/json" };
    let body: string | undefined;
    if (payload !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(payload);
    }
    if (session) Object.assign(headers, session.headers());

    let transportResponse: IdentityTransportResponse;
    try {
      transportResponse = await this.#transport({
        method,
        url: `${this.baseUrl}${path}`,
        headers,
        body,
        timeoutMs: this.timeoutMs,
      });
    } catch (error) {
      if (error instanceof IdentityClientError) throw error;
      throw new IdentityClientError("identity transport failed", {
        code: "transport_error",
        cause: error,
      });
    }

    let decoded: unknown;
    try {
      decoded =
        typeof transportResponse.body === "string"
          ? JSON.parse(transportResponse.body)
          : transportResponse.body;
    } catch (error) {
      throw new IdentityClientError("identity service returned invalid JSON", {
        code: "invalid_response",
        statusCode: transportResponse.status,
        cause: error,
      });
    }
    const response = objectValue(decoded, "response");
    if (transportResponse.status < 200 || transportResponse.status >= 300) {
      const error = isRecord(response.error) ? response.error : {};
      throw new IdentityClientError(
        typeof error.message === "string" && error.message
          ? error.message
          : "identity request failed",
        {
          code:
            typeof error.code === "string" && error.code
              ? error.code
              : "identity_request_failed",
          statusCode: transportResponse.status,
        },
      );
    }
    if (response.schema_version !== IDENTITY_SCHEMA_VERSION) {
      throw new IdentityClientError("unsupported identity schema version", {
        code: "invalid_response",
        statusCode: transportResponse.status,
      });
    }
    return response;
  }
}

function parseChallenge(response: IdentityJson): IdentityChallenge {
  return {
    challengeId: stringValue(response, "challenge_id"),
    purpose: stringValue(response, "purpose"),
    deliveryMethod: stringValue(response, "delivery_method"),
    deliveryHint: stringValue(response, "delivery_hint"),
    expiresAt: stringValue(response, "expires_at"),
  };
}

function parseAuth(response: IdentityJson): IdentityAuthResult {
  const status = stringValue(response, "status");
  if (status === "mfa_required") {
    return {
      status,
      mfaChallengeId: stringValue(response, "mfa_challenge_id"),
      expiresAt: stringValue(response, "expires_at"),
    };
  }
  if (status !== "authenticated") {
    throw invalidResponse("unexpected authentication response");
  }
  return new IdentitySessionCredential({
    accountId: stringValue(response, "account_id"),
    sessionId: stringValue(response, "session_id"),
    sessionToken: stringValue(response, "session_token"),
    expiresAt: stringValue(response, "expires_at"),
  });
}

function parseIdentity(value: IdentityJson): IdentityView {
  const credentials = arrayValue(value, "credentials").map((item) => {
    const credential = objectValue(item, "credential");
    return {
      provider: stringValue(credential, "provider"),
      kind: stringValue(credential, "kind"),
    };
  });
  const twoFactor = objectValue(value.two_factor, "two_factor");
  const providerCapabilities = arrayValue(value, "provider_capabilities").map(
    (item) => {
      const capability = objectValue(item, "provider_capability");
      return {
        provider: stringValue(capability, "provider"),
        kind: stringValue(capability, "kind"),
        enabled: booleanValue(capability, "enabled"),
        region: stringValue(capability, "region"),
        supportsRegistration: booleanValue(
          capability,
          "supports_registration",
        ),
        supportsLogin: booleanValue(capability, "supports_login"),
        supportsExplicitBinding: booleanValue(
          capability,
          "supports_explicit_binding",
        ),
        pkceRequired: booleanValue(capability, "pkce_required"),
      };
    },
  );
  return {
    accountId: stringValue(value, "account_id"),
    primaryEmailHint: stringValue(value, "primary_email_hint"),
    displayName: typeof value.display_name === "string" ? value.display_name : "",
    locale: stringValue(value, "locale"),
    region: stringValue(value, "region"),
    status: stringValue(value, "status"),
    preferredRegistrationMethod: stringValue(
      value,
      "preferred_registration_method",
    ),
    credentials,
    twoFactor: {
      enabled: booleanValue(twoFactor, "enabled"),
      recommended: booleanValue(twoFactor, "recommended"),
      methods: arrayValue(twoFactor, "methods").map((item) => {
        if (typeof item !== "string") {
          throw invalidResponse("two_factor methods must be strings");
        }
        return item;
      }),
    },
    providerCapabilities,
  };
}

function isRecord(value: unknown): value is IdentityJson {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function objectValue(value: unknown, name: string): IdentityJson {
  if (!isRecord(value)) throw invalidResponse(`${name} must be an object`);
  return value;
}

function arrayValue(value: IdentityJson, key: string): unknown[] {
  const selected = value[key];
  if (!Array.isArray(selected)) {
    throw invalidResponse(`${key} must be an array`);
  }
  return selected;
}

function stringValue(value: IdentityJson, key: string): string {
  const selected = value[key];
  if (typeof selected !== "string" || selected.length === 0) {
    throw invalidResponse(`${key} must be a non-empty string`);
  }
  return selected;
}

function booleanValue(value: IdentityJson, key: string): boolean {
  const selected = value[key];
  if (typeof selected !== "boolean") {
    throw invalidResponse(`${key} must be a boolean`);
  }
  return selected;
}

function invalidResponse(message: string): IdentityClientError {
  return new IdentityClientError(message, { code: "invalid_response" });
}

async function fetchIdentityTransport(
  request: IdentityTransportRequest,
): Promise<IdentityTransportResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), request.timeoutMs);
  try {
    const response = await fetch(request.url, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      signal: controller.signal,
    });
    return {
      status: response.status,
      body: await response.text(),
      headers: Object.fromEntries(response.headers.entries()),
    };
  } catch (error) {
    throw new IdentityClientError("identity service is unreachable", {
      code: "transport_error",
      cause: error,
    });
  } finally {
    clearTimeout(timeout);
  }
}
