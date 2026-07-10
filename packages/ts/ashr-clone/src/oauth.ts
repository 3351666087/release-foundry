import { createHash, timingSafeEqual } from "node:crypto";

export const OAUTH_PROVIDER_SCHEMA_VERSION = "ashr.clone.oauth_provider_adapter.v2";
export const OAUTH_ENVIRONMENTS = ["sandbox", "live"] as const;

export type OAuthProvider = "github" | "google" | "wechat" | "alipay";
export type OAuthEnvironment = (typeof OAUTH_ENVIRONMENTS)[number];
export type JsonRecord = Record<string, unknown>;

export class OAuthProviderContractError extends Error {}

export interface OAuthProviderMetadata {
  provider: OAuthProvider;
  protocol: "oauth2" | "oidc";
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint: string;
  discovery_document: string | null;
  default_scopes: readonly string[];
  subject_claim: string;
  audience_claim: string | null;
  nonce_supported: boolean;
  account_binding: string;
}

export interface OAuthClientConfig {
  provider: OAuthProvider | string;
  clientIdRef: string;
  clientSecretRef: string;
  redirectUri: string;
  scopes: readonly string[];
  environment?: OAuthEnvironment | string;
  redirectAllowlist?: readonly string[];
  enabled?: boolean;
  issuerAllowlist?: readonly string[];
  audienceAllowlist?: readonly string[];
}

interface ValidatedOAuthClientConfig {
  provider: OAuthProvider;
  client_id_ref: string;
  client_secret_ref: string;
  redirect_uri: string;
  scopes: string[];
  environment: OAuthEnvironment;
  redirect_allowlist: string[];
  enabled: boolean;
  issuer_allowlist: string[];
  audience_allowlist: string[];
}

const REFERENCE_PREFIXES = ["env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:"];
const PKCE_VERIFIER = /^[A-Za-z0-9._~-]{43,128}$/u;
const PKCE_CHALLENGE = /^[A-Za-z0-9_-]{43}$/u;
const DIGEST = /^[a-f0-9]{64}$/u;
const RAW_SECRET = /(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bya29\.[A-Za-z0-9._-]{20,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----)/u;

export const PROVIDER_METADATA: Readonly<Record<OAuthProvider, OAuthProviderMetadata>> = {
  github: {
    provider: "github", protocol: "oauth2", issuer: "https://github.com",
    authorization_endpoint: "https://github.com/login/oauth/authorize",
    token_endpoint: "https://github.com/login/oauth/access_token",
    userinfo_endpoint: "https://api.github.com/user", discovery_document: null,
    default_scopes: ["read:user", "user:email"], subject_claim: "id",
    audience_claim: null, nonce_supported: false, account_binding: "github_user_id",
  },
  google: {
    provider: "google", protocol: "oidc", issuer: "https://accounts.google.com",
    authorization_endpoint: "https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint: "https://oauth2.googleapis.com/token",
    userinfo_endpoint: "https://openidconnect.googleapis.com/v1/userinfo",
    discovery_document: "https://accounts.google.com/.well-known/openid-configuration",
    default_scopes: ["openid", "email", "profile"], subject_claim: "sub",
    audience_claim: "aud", nonce_supported: true, account_binding: "google_subject",
  },
  wechat: {
    provider: "wechat", protocol: "oauth2", issuer: "https://open.weixin.qq.com",
    authorization_endpoint: "https://open.weixin.qq.com/connect/qrconnect",
    token_endpoint: "https://api.weixin.qq.com/sns/oauth2/access_token",
    userinfo_endpoint: "https://api.weixin.qq.com/sns/userinfo", discovery_document: null,
    default_scopes: ["snsapi_login"], subject_claim: "unionid_or_openid",
    audience_claim: "appid", nonce_supported: false,
    account_binding: "wechat_unionid_with_appid_openid_fallback",
  },
  alipay: {
    provider: "alipay", protocol: "oauth2", issuer: "https://openauth.alipay.com",
    authorization_endpoint: "https://openauth.alipay.com/oauth2/publicAppAuthorize.htm",
    token_endpoint: "https://openapi.alipay.com/gateway.do",
    userinfo_endpoint: "https://openapi.alipay.com/gateway.do", discovery_document: null,
    default_scopes: ["auth_user"], subject_claim: "user_id",
    audience_claim: "app_id", nonce_supported: false, account_binding: "alipay_user_id",
  },
};

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

export function normalizeOAuthProvider(value: string): OAuthProvider {
  const aliases: Record<string, OAuthProvider> = { wechat_login: "wechat", weixin: "wechat", alipay_login: "alipay" };
  const normalized = value.trim().toLowerCase();
  const provider = aliases[normalized] ?? normalized;
  if (!(provider in PROVIDER_METADATA)) {
    throw new OAuthProviderContractError("OAuth provider must be github, google, wechat, or alipay");
  }
  return provider as OAuthProvider;
}

export function normalizeOAuthEnvironment(value = "sandbox"): OAuthEnvironment {
  const normalized = value.trim().toLowerCase();
  if (normalized !== "sandbox" && normalized !== "live") {
    throw new OAuthProviderContractError("OAuth environment must be sandbox or live");
  }
  return normalized;
}

export function oauthProviderMetadata(provider: string): JsonRecord {
  const metadata = PROVIDER_METADATA[normalizeOAuthProvider(provider)];
  return {
    ...metadata,
    default_scopes: [...metadata.default_scopes],
    pkce_methods: ["S256"],
    supported_environments: [...OAUTH_ENVIRONMENTS],
    metadata_fetch_performed: false,
  };
}

export function validateOAuthClientConfig(config: OAuthClientConfig): ValidatedOAuthClientConfig {
  const provider = normalizeOAuthProvider(config.provider);
  const environment = normalizeOAuthEnvironment(config.environment);
  validateRef("client_id_ref", config.clientIdRef);
  validateRef("client_secret_ref", config.clientSecretRef);
  const redirectUri = normalizeRedirectUri(config.redirectUri);
  const redirectAllowlist = unique((config.redirectAllowlist?.length ? config.redirectAllowlist : [redirectUri]).map(normalizeRedirectUri));
  if (!redirectAllowlist.includes(redirectUri)) {
    throw new OAuthProviderContractError("OAuth redirect URI must exactly match redirect_allowlist");
  }
  const scopes = unique(config.scopes.map((value) => value.trim()));
  if (scopes.length === 0 || scopes.some((value) => value.length === 0)) {
    throw new OAuthProviderContractError("OAuth scopes must not be empty");
  }
  const issuerAllowlist = unique((config.issuerAllowlist?.length ? config.issuerAllowlist : [PROVIDER_METADATA[provider].issuer]).map((value) => normalizeHttpsIssuer("issuer", value)));
  const audienceAllowlist = unique((config.audienceAllowlist ?? []).map((value) => validateIdentifier("audience", value)));
  return {
    provider, environment, client_id_ref: config.clientIdRef,
    client_secret_ref: config.clientSecretRef, redirect_uri: redirectUri, scopes,
    redirect_allowlist: redirectAllowlist, enabled: config.enabled === true,
    issuer_allowlist: issuerAllowlist, audience_allowlist: audienceAllowlist,
  };
}

export function publicOAuthClientConfig(config: OAuthClientConfig): JsonRecord {
  const safe = validateOAuthClientConfig(config);
  return { ...safe, disabled_by_default: !safe.enabled, secret_value_present: false };
}

export function derivePkceS256(codeVerifier: string): JsonRecord {
  if (!PKCE_VERIFIER.test(codeVerifier)) {
    throw new OAuthProviderContractError("PKCE code_verifier must be 43-128 unreserved characters");
  }
  const digest = createHash("sha256").update(codeVerifier, "ascii").digest();
  return {
    method: "S256",
    code_challenge: digest.toString("base64url"),
    code_verifier_sha256: digest.toString("hex"),
    code_verifier_present: false,
  };
}

export function hashOAuthState(state: string): JsonRecord {
  return hashTransient("state", state);
}

export function hashOAuthNonce(nonce: string): JsonRecord {
  return hashTransient("nonce", nonce);
}

export class OAuthReplayLedger {
  readonly #consumed = new Set<string>();

  consume(provider: string, environment: string, replayKey: string): boolean {
    const providerName = normalizeOAuthProvider(provider);
    const environmentName = normalizeOAuthEnvironment(environment);
    if (replayKey.length < 16 || replayKey.length > 1024) {
      throw new OAuthProviderContractError("OAuth replay key must be 16-1024 characters");
    }
    const digest = sha256(`${providerName}\0${environmentName}\0${replayKey}`);
    if (this.#consumed.has(digest)) return false;
    this.#consumed.add(digest);
    return true;
  }

  publicSnapshot(): JsonRecord {
    return { consumed_digest_count: this.#consumed.size, raw_replay_keys_present: false };
  }
}

export function buildAuthorizationEnvelope(options: {
  config: OAuthClientConfig;
  stateRef: string;
  stateSha256: string;
  pkceCodeChallenge: string;
  prompt?: string;
  nonceRef?: string;
  nonceSha256?: string;
}): JsonRecord {
  const config = validateOAuthClientConfig(options.config);
  validateRef("state_ref", options.stateRef);
  validateDigest("state_sha256", options.stateSha256);
  if (!PKCE_CHALLENGE.test(options.pkceCodeChallenge)) {
    throw new OAuthProviderContractError("PKCE challenge must be an S256 base64url digest");
  }
  if ((options.nonceRef === undefined) !== (options.nonceSha256 === undefined)) {
    throw new OAuthProviderContractError("OAuth nonce_ref and nonce_sha256 must be paired");
  }
  if (options.nonceRef !== undefined) {
    validateRef("nonce_ref", options.nonceRef);
    validateDigest("nonce_sha256", options.nonceSha256!);
  }
  if (PROVIDER_METADATA[config.provider].nonce_supported && config.enabled && options.nonceRef === undefined) {
    throw new OAuthProviderContractError(`${config.provider} authorization requires nonce binding`);
  }
  const parameters: JsonRecord = {
    response_type: "code", client_id_ref: config.client_id_ref,
    redirect_uri: config.redirect_uri, scopes: config.scopes,
    state_ref: options.stateRef, code_challenge: options.pkceCodeChallenge,
    code_challenge_method: "S256",
  };
  if (options.nonceRef !== undefined) parameters.nonce_ref = options.nonceRef;
  if (options.prompt !== undefined) parameters.prompt = options.prompt;
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION, envelope_type: "authorization_request",
    provider: config.provider, environment: config.environment, enabled: config.enabled,
    ready: false, provider_metadata: oauthProviderMetadata(config.provider), parameters,
    state_sha256: options.stateSha256, nonce_sha256: options.nonceSha256 ?? null,
    redirect_allowlist: config.redirect_allowlist,
    executor_contract: {
      resolve_client_id_ref: true, resolve_state_ref: true,
      resolve_nonce_ref: options.nonceRef !== undefined, network_io_performed: false,
    },
    raw_state_present: false, raw_nonce_present: false, code_verifier_present: false,
    secret_value_present: false, token_value_present: false,
  };
}

export function verifyCallbackState(options: {
  receivedState: string;
  expectedStateSha256: string;
  authorizationCodeRef?: string;
  errorCode?: string;
  provider?: string;
  environment?: string;
  replayKey?: string;
  replayLedger?: OAuthReplayLedger;
}): JsonRecord {
  validateDigest("expected_state_sha256", options.expectedStateSha256);
  const receivedDigest = sha256(options.receivedState);
  const stateMatches = safeEqual(receivedDigest, options.expectedStateSha256);
  if (options.authorizationCodeRef !== undefined) validateRef("authorization_code_ref", options.authorizationCodeRef);
  let replayAccepted = true;
  if (options.replayKey !== undefined) {
    if (options.replayLedger === undefined) throw new OAuthProviderContractError("OAuth replay ledger is required");
    replayAccepted = options.replayLedger.consume(options.provider ?? "github", options.environment ?? "sandbox", options.replayKey);
  }
  const accepted = stateMatches && replayAccepted && options.authorizationCodeRef !== undefined && options.errorCode === undefined;
  const reasons: string[] = [];
  if (!stateMatches) reasons.push("state_mismatch");
  if (!replayAccepted) reasons.push("callback_replay");
  if (options.authorizationCodeRef === undefined) reasons.push("authorization_code_ref_missing");
  if (options.errorCode !== undefined) reasons.push("provider_error");
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION, envelope_type: "authorization_callback",
    accepted, state_matches: stateMatches, replay_accepted: replayAccepted,
    failure_reasons: reasons, received_state_sha256: receivedDigest,
    authorization_code_ref: accepted ? options.authorizationCodeRef : null,
    error_code: options.errorCode ?? null, raw_state_present: false,
    raw_authorization_code_present: false, secret_value_present: false,
  };
}

export function verifyCallbackIdentity(options: {
  config: OAuthClientConfig;
  issuer: string;
  audience?: string | readonly string[];
  subject: string;
  accountBindingRef: string;
  expectedAccountBindingRef?: string;
  receivedNonce?: string;
  expectedNonceSha256?: string;
}): JsonRecord {
  const config = validateOAuthClientConfig(options.config);
  const issuer = normalizeHttpsIssuer("issuer", options.issuer);
  const audiences = options.audience === undefined ? [] : (typeof options.audience === "string" ? [options.audience] : [...options.audience]).map((value) => validateIdentifier("audience", value));
  const subject = validateIdentifier("subject", options.subject);
  validateRef("account_binding_ref", options.accountBindingRef);
  if (options.expectedAccountBindingRef !== undefined) validateRef("expected_account_binding_ref", options.expectedAccountBindingRef);
  const issuerMatches = config.issuer_allowlist.includes(issuer);
  const audienceMatches = config.audience_allowlist.length === 0 || audiences.some((value) => config.audience_allowlist.includes(value));
  const accountMatches = options.expectedAccountBindingRef === undefined || safeEqual(options.accountBindingRef, options.expectedAccountBindingRef);
  const nonceRequired = PROVIDER_METADATA[config.provider].nonce_supported;
  let nonceMatches = !nonceRequired;
  let receivedNonceSha256: string | null = null;
  if (options.expectedNonceSha256 !== undefined) {
    validateDigest("expected_nonce_sha256", options.expectedNonceSha256);
    receivedNonceSha256 = sha256(options.receivedNonce ?? "");
    nonceMatches = options.receivedNonce !== undefined && safeEqual(receivedNonceSha256, options.expectedNonceSha256);
  } else if (nonceRequired) nonceMatches = false;
  const failureReasons: string[] = [];
  if (!issuerMatches) failureReasons.push("issuer_mismatch");
  if (!audienceMatches) failureReasons.push("audience_mismatch");
  if (!nonceMatches) failureReasons.push("nonce_mismatch");
  if (!accountMatches) failureReasons.push("account_binding_mismatch");
  const accepted = failureReasons.length === 0 && config.enabled;
  if (!config.enabled) failureReasons.push("provider_disabled");
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION,
    envelope_type: "callback_identity_verification", provider: config.provider,
    environment: config.environment, accepted, failure_reasons: failureReasons,
    issuer: issuerMatches ? issuer : null, issuer_matches: issuerMatches,
    audience_matches: audienceMatches, nonce_required: nonceRequired,
    nonce_matches: nonceMatches, account_binding_matches: accountMatches,
    subject_sha256: sha256(subject), received_nonce_sha256: receivedNonceSha256,
    account_binding_ref: accountMatches ? options.accountBindingRef : null,
    raw_subject_present: false, raw_nonce_present: false, secret_value_present: false,
  };
}

export function buildTokenExchangeEnvelope(options: {
  config: OAuthClientConfig;
  authorizationCodeRef: string;
  codeVerifierRef: string;
}): JsonRecord {
  const config = validateOAuthClientConfig(options.config);
  validateRef("authorization_code_ref", options.authorizationCodeRef);
  validateRef("code_verifier_ref", options.codeVerifierRef);
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION, envelope_type: "token_exchange",
    provider: config.provider, environment: config.environment, enabled: config.enabled,
    ready: false, token_endpoint: PROVIDER_METADATA[config.provider].token_endpoint,
    client_id_ref: config.client_id_ref, client_secret_ref: config.client_secret_ref,
    authorization_code_ref: options.authorizationCodeRef, code_verifier_ref: options.codeVerifierRef,
    redirect_uri: config.redirect_uri, grant_type: "authorization_code",
    executor_contract: {
      interface: "OAuthTokenExchangeExecutor", network_io_performed: false,
      secret_resolution_deferred: true,
    },
    raw_authorization_code_present: false, code_verifier_present: false,
    secret_value_present: false, token_value_present: false,
  };
}

export function buildTokenRefEnvelope(options: {
  provider: string;
  subjectRef: string;
  accessTokenRef: string;
  refreshTokenRef?: string;
  idTokenRef?: string;
  grantedScopes?: readonly string[];
  environment?: string;
  accountBindingRef?: string;
}): JsonRecord {
  const provider = normalizeOAuthProvider(options.provider);
  const environment = normalizeOAuthEnvironment(options.environment);
  validateRef("subject_ref", options.subjectRef);
  validateRef("access_token_ref", options.accessTokenRef);
  if (options.refreshTokenRef !== undefined) validateRef("refresh_token_ref", options.refreshTokenRef);
  if (options.idTokenRef !== undefined) validateRef("id_token_ref", options.idTokenRef);
  if (options.accountBindingRef !== undefined) validateRef("account_binding_ref", options.accountBindingRef);
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION, envelope_type: "token_references",
    provider, environment, subject_ref: options.subjectRef,
    account_binding_ref: options.accountBindingRef ?? null,
    access_token_ref: options.accessTokenRef, refresh_token_ref: options.refreshTokenRef ?? null,
    id_token_ref: options.idTokenRef ?? null, granted_scopes: unique([...(options.grantedScopes ?? [])]),
    token_value_present: false, secret_value_present: false,
  };
}

export function oauthProviderContractManifest(): JsonRecord {
  return {
    schema_version: OAUTH_PROVIDER_SCHEMA_VERSION,
    providers: Object.fromEntries(Object.keys(PROVIDER_METADATA).sort().map((provider) => [provider, oauthProviderMetadata(provider)])),
    environments: [...OAUTH_ENVIRONMENTS],
    required_controls: {
      pkce_method: "S256", state_hash_only: true, nonce_hash_only: true,
      redirect_exact_allowlist: true, sandbox_live_separation: true,
      issuer_validation: true, audience_validation: true, subject_hash_only: true,
      account_binding_required: true, callback_replay_protection: true,
      token_refs_only: true, raw_authorization_code_allowed: false,
      network_io_performed: false, disabled_by_default: true,
    },
  };
}

function validateRef(name: string, value: string): void {
  if (!REFERENCE_PREFIXES.some((prefix) => value.startsWith(prefix))) {
    throw new OAuthProviderContractError(`${name} must use an approved reference prefix`);
  }
  if (/\s/u.test(value)) throw new OAuthProviderContractError(`${name} must not contain whitespace`);
  if (RAW_SECRET.test(value)) throw new OAuthProviderContractError(`${name} contains raw OAuth secret material`);
}

function normalizeRedirectUri(value: string): string {
  let parsed: URL;
  try { parsed = new URL(value.trim()); } catch { throw new OAuthProviderContractError("OAuth redirect URI must be HTTPS or localhost; localhost requires an explicit port and path"); }
  const localhost = parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname) && parsed.port !== "";
  const https = parsed.protocol === "https:";
  if ((!localhost && !https) || parsed.username || parsed.password || parsed.hash || parsed.pathname === "/") {
    throw new OAuthProviderContractError("OAuth redirect URI must be HTTPS or localhost; localhost requires an explicit port and path");
  }
  return value.trim();
}

function normalizeHttpsIssuer(name: string, value: string): string {
  let parsed: URL;
  try { parsed = new URL(value.trim()); } catch { throw new OAuthProviderContractError(`OAuth ${name} must be an HTTPS issuer URL`); }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new OAuthProviderContractError(`OAuth ${name} must be an HTTPS issuer URL`);
  }
  return value.trim().replace(/\/+$/u, "");
}

function validateIdentifier(name: string, value: string): string {
  const text = value.trim();
  if (!text || text.length > 512 || /\s/u.test(text)) {
    throw new OAuthProviderContractError(`OAuth ${name} must be a bounded identifier`);
  }
  return text;
}

function validateDigest(name: string, value: string): void {
  if (!DIGEST.test(value)) throw new OAuthProviderContractError(`${name} must be a lowercase SHA-256 digest`);
}

function hashTransient(name: "state" | "nonce", value: string): JsonRecord {
  if (value.length < 16 || value.length > 512) {
    throw new OAuthProviderContractError(`OAuth ${name} must be 16-512 characters`);
  }
  return { [`${name}_sha256`]: sha256(value), [`raw_${name}_present`]: false };
}

function unique<T>(values: readonly T[]): T[] {
  return [...new Set(values)];
}
