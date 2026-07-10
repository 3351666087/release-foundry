export const UNIFIED_IDENTITY_SCHEMA_VERSION = "ashr.clone.unified_identity.v1" as const;

export const UNIFIED_IDENTITY_PROVIDERS = [
  "github",
  "google",
  "wechat",
  "qq",
  "alipay",
  "phone",
  "email",
] as const;

export const UNIFIED_IDENTITY_ACCOUNT_STATUSES = [
  "active",
  "suspended",
  "merged",
  "recovery_locked",
] as const;

export const UNIFIED_IDENTITY_CREDENTIAL_STATUSES = [
  "pending",
  "active",
  "revocation_pending",
  "revoked",
] as const;

export const UNIFIED_IDENTITY_MEMBERSHIP_ROLES = [
  "owner",
  "admin",
  "developer",
  "viewer",
  "billing",
] as const;

export const UNIFIED_IDENTITY_MEMBERSHIP_STATUSES = [
  "invited",
  "active",
  "suspended",
  "removed",
] as const;

export const UNIFIED_IDENTITY_ERROR_CODES = [
  "identity_invalid_request",
  "identity_account_not_found",
  "identity_account_suspended",
  "identity_provider_not_supported",
  "identity_credential_not_found",
  "identity_credential_already_linked",
  "identity_credential_conflict",
  "identity_last_credential_unlink_forbidden",
  "identity_membership_not_found",
  "identity_membership_forbidden",
  "identity_link_expired",
  "identity_link_replayed",
  "identity_merge_conflict",
  "identity_merge_cycle",
  "identity_merge_requires_step_up",
  "identity_recovery_not_found",
  "identity_recovery_expired",
  "identity_recovery_replayed",
  "identity_recovery_rate_limited",
  "identity_recovery_locked",
  "identity_verification_required",
  "identity_verification_failed",
  "identity_verification_expired",
  "identity_verification_locked",
  "identity_verification_replayed",
  "identity_verification_rate_limited",
  "identity_verification_resend_too_soon",
  "identity_store_failed",
] as const;

export const IDENTITY_VERIFICATION_PROVIDERS = ["email", "phone"] as const;

export const IDENTITY_VERIFICATION_PURPOSES = [
  "binding",
  "login",
  "recovery",
] as const;

export const IDENTITY_VERIFICATION_CHALLENGE_STATUSES = [
  "pending",
  "verified",
  "consumed",
  "expired",
  "locked",
] as const;

export const IDENTITY_VERIFICATION_RECEIPT_STATUSES = [
  "verified",
  "consumed",
  "expired",
] as const;

export type UnifiedIdentityProvider = (typeof UNIFIED_IDENTITY_PROVIDERS)[number];
export type UnifiedAccountStatus = (typeof UNIFIED_IDENTITY_ACCOUNT_STATUSES)[number];
export type UnifiedCredentialStatus = (typeof UNIFIED_IDENTITY_CREDENTIAL_STATUSES)[number];
export type UnifiedMembershipRole = (typeof UNIFIED_IDENTITY_MEMBERSHIP_ROLES)[number];
export type UnifiedMembershipStatus = (typeof UNIFIED_IDENTITY_MEMBERSHIP_STATUSES)[number];
export type UnifiedIdentityErrorCode = (typeof UNIFIED_IDENTITY_ERROR_CODES)[number];
export type IdentityVerificationProvider = (typeof IDENTITY_VERIFICATION_PROVIDERS)[number];
export type IdentityVerificationPurpose = (typeof IDENTITY_VERIFICATION_PURPOSES)[number];
export type IdentityVerificationChallengeStatus =
  (typeof IDENTITY_VERIFICATION_CHALLENGE_STATUSES)[number];
export type IdentityVerificationReceiptStatus =
  (typeof IDENTITY_VERIFICATION_RECEIPT_STATUSES)[number];
export type UnifiedIdentityFetch = typeof fetch;

export interface IdentityCredential {
  credential_id: string;
  account_id: string;
  provider: UnifiedIdentityProvider;
  provider_subject_present: boolean;
  status: UnifiedCredentialStatus;
  verified: boolean;
  display_hint: string;
  linked_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface IdentityMembership {
  membership_id: string;
  account_id: string;
  tenant_id: string;
  project_id: string | null;
  role: UnifiedMembershipRole;
  status: UnifiedMembershipStatus;
  joined_at: string;
}

export interface UnifiedAccount {
  schema_version: typeof UNIFIED_IDENTITY_SCHEMA_VERSION;
  account_id: string;
  status: UnifiedAccountStatus;
  display_name: string | null;
  created_at: string;
  updated_at: string;
  merged_into_account_id: string | null;
  credentials: IdentityCredential[];
  memberships: IdentityMembership[];
}

export interface IdentityLink {
  link_id: string;
  account_id: string;
  provider: UnifiedIdentityProvider;
  status: "pending" | "linked" | "expired";
  expires_at: string;
  authorize_url: string | null;
  verification_required: boolean;
}

export interface IdentityUnlink {
  account_id: string;
  credential_id: string;
  provider: UnifiedIdentityProvider;
  unlinked: boolean;
  revocation_status: "revoked" | "not_required" | "pending" | "failed";
}

export interface IdentityMerge {
  merge_id: string;
  canonical_account: UnifiedAccount;
  merged_account_ids: string[];
  credentials_repointed: number;
  memberships_repointed: number;
  completed_at: string;
}

export interface IdentityRecovery {
  recovery_id: string;
  account_id: string;
  provider: "phone" | "email";
  destination_hint: string;
  status: "pending" | "verified" | "completed" | "expired" | "locked";
  expires_at: string;
  attempts_remaining: number;
}

export interface IdentityVerificationChallenge {
  challenge_id: string;
  provider: IdentityVerificationProvider;
  purpose: IdentityVerificationPurpose;
  status: IdentityVerificationChallengeStatus;
  destination_hint: string;
  destination_digest_ref: string;
  created_at: string;
  expires_at: string;
  ttl_seconds: number;
  attempt_cap: number;
  attempts_remaining: number;
  resend_cooldown_seconds: number;
  resend_available_at: string;
  single_use: true;
  account_id: string | null;
  verified_at: string | null;
  consumed_at: string | null;
}

export interface IdentityVerificationReceipt {
  receipt_id: string;
  challenge_id: string;
  provider: IdentityVerificationProvider;
  purpose: IdentityVerificationPurpose;
  status: IdentityVerificationReceiptStatus;
  destination_digest_ref: string;
  verified_at: string;
  expires_at: string;
  single_use: true;
  account_id: string | null;
  consumed_at: string | null;
}

export interface UnifiedIdentityError {
  code: UnifiedIdentityErrorCode;
  message: string;
  retryable: boolean;
  provider: UnifiedIdentityProvider | null;
  retry_after_seconds: number | null;
}

// Compatibility aliases retained for callers of the first TS draft.
export type UnifiedCredential = IdentityCredential;
export type UnifiedMembership = IdentityMembership;
export type UnifiedCredentialLink = IdentityLink;
export type UnifiedCredentialUnlink = IdentityUnlink;
export type UnifiedAccountMerge = IdentityMerge;
export type UnifiedRecovery = IdentityRecovery;
export type UnifiedVerificationChallenge = IdentityVerificationChallenge;
export type UnifiedVerificationReceipt = IdentityVerificationReceipt;

export interface UnifiedIdentityRoute {
  operation:
    | "account_get"
    | "credential_list"
    | "membership_list"
    | "credential_link"
    | "credential_unlink"
    | "account_merge"
    | "recovery_start"
    | "recovery_complete"
    | "verification_challenge_create"
    | "verification_challenge_get"
    | "verification_challenge_resend"
    | "verification_challenge_verify";
  method: "GET" | "POST";
  path: string;
}

export const UNIFIED_IDENTITY_ROUTES: readonly UnifiedIdentityRoute[] = Object.freeze([
  { operation: "account_get", method: "GET", path: "/v1/accounts/{account_id}" },
  { operation: "credential_list", method: "GET", path: "/v1/accounts/{account_id}/credentials" },
  { operation: "membership_list", method: "GET", path: "/v1/accounts/{account_id}/memberships" },
  { operation: "credential_link", method: "POST", path: "/v1/accounts/{account_id}/credentials/{provider}/link" },
  { operation: "credential_unlink", method: "POST", path: "/v1/accounts/{account_id}/credentials/{credential_id}/unlink" },
  { operation: "account_merge", method: "POST", path: "/v1/accounts/{canonical_account_id}/merge" },
  { operation: "recovery_start", method: "POST", path: "/v1/accounts/{account_id}/recovery/start" },
  { operation: "recovery_complete", method: "POST", path: "/v1/accounts/{account_id}/recovery/{recovery_id}/complete" },
  { operation: "verification_challenge_create", method: "POST", path: "/v1/identity/verifications/challenges" },
  { operation: "verification_challenge_get", method: "GET", path: "/v1/identity/verifications/challenges/{challenge_id}" },
  { operation: "verification_challenge_resend", method: "POST", path: "/v1/identity/verifications/challenges/{challenge_id}/resend" },
  { operation: "verification_challenge_verify", method: "POST", path: "/v1/identity/verifications/challenges/{challenge_id}/verify" },
]);

export interface UnifiedIdentityClientOptions {
  baseUrl: string;
  fetch?: UnifiedIdentityFetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

export interface LinkCredentialOptions {
  accountId: string;
  provider: UnifiedIdentityProvider | string;
  verificationReceiptId?: string;
  idempotencyKey: string;
}

export interface UnlinkCredentialOptions {
  accountId: string;
  credentialId: string;
  stepUpReceiptId: string;
  idempotencyKey: string;
}

export interface MergeAccountsOptions {
  canonicalAccountId: string;
  sourceAccountId: string;
  stepUpReceiptId: string;
  idempotencyKey: string;
}

export interface StartRecoveryOptions {
  accountId: string;
  provider: "phone" | "email";
  idempotencyKey: string;
}

export interface CompleteRecoveryOptions {
  accountId: string;
  recoveryId: string;
  verificationReceiptId: string;
  idempotencyKey: string;
}

export interface StartVerificationOptions {
  provider: IdentityVerificationProvider | string;
  purpose: IdentityVerificationPurpose | string;
  destinationRef: string;
  accountId?: string;
  idempotencyKey: string;
}

export interface ResendVerificationOptions {
  challengeId: string;
  idempotencyKey: string;
}

export interface VerifyChallengeOptions {
  challengeId: string;
  verificationCodeRef: string;
  idempotencyKey: string;
}

export type CreateVerificationChallengeOptions = StartVerificationOptions;
export type VerifyVerificationChallengeOptions = VerifyChallengeOptions;

const FORBIDDEN_PUBLIC_KEYS = new Set([
  "access_token",
  "authorization",
  "authorization_code",
  "client_secret",
  "code_verifier",
  "cookie",
  "email",
  "email_address",
  "id_token",
  "nonce",
  "otp",
  "password",
  "phone",
  "phone_number",
  "refresh_token",
  "secret",
  "session_token",
  "state",
  "provider_subject_sha256",
  "subject_digest",
  "identifier_sha256",
  "token",
  "token_ref",
  "token_ref_id",
  "destination",
  "destination_value",
  "verification_code",
  "verification_value",
  "revocation_outbox_id",
]);

const FORBIDDEN_KEY_SUFFIXES = [
  "_access_token",
  "_authorization_code",
  "_client_secret",
  "_code_verifier",
  "_id_token",
  "_otp",
  "_password",
  "_refresh_token",
  "_secret",
  "_session_token",
];

const RECOVERY_PROVIDERS = new Set<UnifiedIdentityProvider>(["phone", "email"]);
const VERIFICATION_PROVIDERS = new Set<UnifiedIdentityProvider>(["phone", "email"]);
const FORBIDDEN_CANONICAL_KEYS = new Set(
  [...FORBIDDEN_PUBLIC_KEYS].map((key) => key.replace(/[^a-z0-9]/gu, "")),
);
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$/u;

export class UnifiedIdentityContractError extends Error {
  readonly code: UnifiedIdentityErrorCode;

  constructor(message: string, code: UnifiedIdentityErrorCode = "identity_invalid_request") {
    super(redactIdentityText(message));
    this.name = "UnifiedIdentityContractError";
    this.code = code;
  }

  toJSON(): UnifiedIdentityError {
    return {
      code: this.code,
      message: this.message,
      retryable: false,
      provider: null,
      retry_after_seconds: null,
    };
  }
}

export class UnifiedIdentityHttpClient {
  readonly baseUrl: string;
  readonly #fetch: UnifiedIdentityFetch;
  readonly #headers: Record<string, string>;
  readonly #timeoutMs: number;

  constructor(options: UnifiedIdentityClientOptions) {
    const baseUrl = String(options.baseUrl ?? "").trim().replace(/\/+$/u, "");
    let parsed: URL;
    try {
      parsed = new URL(baseUrl);
    } catch {
      throw new UnifiedIdentityContractError("base_url must be HTTP or HTTPS");
    }
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
      throw new UnifiedIdentityContractError("base_url must be HTTP or HTTPS");
    }
    this.baseUrl = baseUrl;
    this.#fetch = options.fetch ?? fetch;
    this.#headers = validateHeaders(options.headers ?? {});
    this.#timeoutMs = validateTimeout(options.timeoutMs ?? 30_000);
  }

  getAccount(accountId: string): Promise<UnifiedAccount> {
    return this.#request("GET", identityAccountRoute(accountId), {}, parseUnifiedAccount);
  }

  async listCredentials(accountId: string): Promise<IdentityCredential[]> {
    const result = await this.#requestRecord("GET", identityCredentialsRoute(accountId), {});
    return mappingSequence(result, "credentials").map(parseIdentityCredential);
  }

  async listMemberships(accountId: string): Promise<IdentityMembership[]> {
    const result = await this.#requestRecord("GET", identityMembershipsRoute(accountId), {});
    return mappingSequence(result, "memberships").map(parseIdentityMembership);
  }

  linkCredential(options: LinkCredentialOptions): Promise<IdentityLink> {
    const provider = normalizeUnifiedIdentityProvider(options.provider);
    const payload: Record<string, unknown> = {
      provider,
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
    };
    if (options.verificationReceiptId) {
      payload.verification_receipt_id = requireIdentifier(
        "verification_receipt_id",
        options.verificationReceiptId,
      );
    }
    return this.#request(
      "POST",
      identityLinkRoute(options.accountId, provider),
      payload,
      parseIdentityLink,
    );
  }

  unlinkCredential(options: UnlinkCredentialOptions): Promise<IdentityUnlink> {
    return this.#request(
      "POST",
      identityUnlinkRoute(options.accountId, options.credentialId),
      {
        step_up_receipt_id: requireIdentifier("step_up_receipt_id", options.stepUpReceiptId),
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseIdentityUnlink,
    );
  }

  mergeAccounts(options: MergeAccountsOptions): Promise<IdentityMerge> {
    const canonicalAccountId = requireIdentifier("canonical_account_id", options.canonicalAccountId);
    const sourceAccountId = requireIdentifier("source_account_id", options.sourceAccountId);
    if (canonicalAccountId === sourceAccountId) {
      throw new UnifiedIdentityContractError(
        "source and canonical accounts must differ",
        "identity_merge_cycle",
      );
    }
    return this.#request(
      "POST",
      identityMergeRoute(canonicalAccountId),
      {
        source_account_id: sourceAccountId,
        step_up_receipt_id: requireIdentifier("step_up_receipt_id", options.stepUpReceiptId),
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseIdentityMerge,
    );
  }

  startRecovery(options: StartRecoveryOptions): Promise<IdentityRecovery> {
    const provider = normalizeRecoveryProvider(options.provider);
    return this.#request(
      "POST",
      identityRecoveryStartRoute(options.accountId),
      {
        provider,
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseIdentityRecovery,
    );
  }

  completeRecovery(options: CompleteRecoveryOptions): Promise<UnifiedAccount> {
    return this.#request(
      "POST",
      identityRecoveryCompleteRoute(options.accountId, options.recoveryId),
      {
        verification_receipt_id: requireIdentifier(
          "verification_receipt_id",
          options.verificationReceiptId,
        ),
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseUnifiedAccount,
    );
  }

  startVerification(options: StartVerificationOptions): Promise<IdentityVerificationChallenge> {
    const provider = normalizeVerificationProvider(options.provider);
    const purpose = normalizeVerificationPurpose(options.purpose);
    const payload: Record<string, unknown> = {
      provider,
      purpose,
      destination_ref: requirePrivateInputReference("destination_ref", options.destinationRef),
      idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
    };
    if (options.accountId !== undefined) {
      payload.account_id = requireIdentifier("account_id", options.accountId);
    }
    if ((purpose === "binding" || purpose === "recovery") && payload.account_id === undefined) {
      throw new UnifiedIdentityContractError(`${purpose} verification requires account_id`);
    }
    return this.#request(
      "POST",
      identityVerificationChallengesRoute(),
      payload,
      parseIdentityVerificationChallenge,
    );
  }

  getVerification(challengeId: string): Promise<IdentityVerificationChallenge> {
    return this.#request(
      "GET",
      identityVerificationChallengeRoute(challengeId),
      {},
      parseIdentityVerificationChallenge,
    );
  }

  resendVerification(options: ResendVerificationOptions): Promise<IdentityVerificationChallenge> {
    return this.#request(
      "POST",
      identityVerificationResendRoute(options.challengeId),
      {
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseIdentityVerificationChallenge,
    );
  }

  verifyChallenge(options: VerifyChallengeOptions): Promise<IdentityVerificationReceipt> {
    return this.#request(
      "POST",
      identityVerificationVerifyRoute(options.challengeId),
      {
        verification_code_ref: requirePrivateInputReference(
          "verification_code_ref",
          options.verificationCodeRef,
        ),
        idempotency_key: requireIdentifier("idempotency_key", options.idempotencyKey),
      },
      parseIdentityVerificationReceipt,
    );
  }

  createVerificationChallenge(
    options: CreateVerificationChallengeOptions,
  ): Promise<IdentityVerificationChallenge> {
    return this.startVerification(options);
  }

  verifyVerificationChallenge(
    options: VerifyVerificationChallengeOptions,
  ): Promise<IdentityVerificationReceipt> {
    return this.verifyChallenge(options);
  }

  async #request<T>(
    method: "GET" | "POST",
    path: string,
    payload: Record<string, unknown>,
    parser: (value: unknown) => T,
  ): Promise<T> {
    return parser(await this.#requestRecord(method, path, payload));
  }

  async #requestRecord(
    method: "GET" | "POST",
    path: string,
    payload: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    assertPublicUnifiedIdentityPayload(payload);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.#timeoutMs);
    try {
      const response = await this.#fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          accept: "application/json",
          ...(method === "POST" ? { "content-type": "application/json" } : {}),
          ...this.#headers,
        },
        ...(method === "POST" ? { body: JSON.stringify(payload) } : {}),
        signal: controller.signal,
      });
      const envelope = await parseCliSafeIdentityJson(response);
      if (!response.ok || isRecord(envelope.error)) {
        const parsed = parseUnifiedIdentityError(envelope);
        throw new UnifiedIdentityContractError(parsed.message || parsed.code, parsed.code);
      }
      const result = isRecord(envelope.result) ? envelope.result : envelope;
      assertPublicUnifiedIdentityPayload(result);
      return result;
    } catch (error) {
      if (error instanceof UnifiedIdentityContractError) throw error;
      if (error instanceof Error && error.name === "AbortError") {
        throw new UnifiedIdentityContractError("identity request timed out", "identity_store_failed");
      }
      throw new UnifiedIdentityContractError("identity transport failed", "identity_store_failed");
    } finally {
      clearTimeout(timeout);
    }
  }
}

export function unifiedIdentityContractManifest(): Record<string, unknown> {
  return {
    schema_version: UNIFIED_IDENTITY_SCHEMA_VERSION,
    subject_model: "one_account_many_credentials",
    providers: [...UNIFIED_IDENTITY_PROVIDERS],
    account_statuses: [...UNIFIED_IDENTITY_ACCOUNT_STATUSES],
    credential_statuses: [...UNIFIED_IDENTITY_CREDENTIAL_STATUSES],
    membership_roles: [...UNIFIED_IDENTITY_MEMBERSHIP_ROLES],
    membership_statuses: [...UNIFIED_IDENTITY_MEMBERSHIP_STATUSES],
    stable_error_codes: [...UNIFIED_IDENTITY_ERROR_CODES],
    invariants: {
      provider_identity_is_credential_not_account: true,
      email_match_does_not_merge_accounts: true,
      memberships_attach_to_canonical_account: true,
      merge_preserves_memberships: true,
      merge_repoints_credentials_atomically: true,
      last_active_credential_cannot_be_unlinked: true,
      recovery_requires_single_use_verification_receipt: true,
      verification_challenges_are_provider_neutral: true,
      verification_receipts_are_single_use: true,
      verification_login_does_not_merge_by_destination: true,
    },
    verification: {
      providers: [...IDENTITY_VERIFICATION_PROVIDERS],
      purposes: [...IDENTITY_VERIFICATION_PURPOSES],
      challenge_statuses: [...IDENTITY_VERIFICATION_CHALLENGE_STATUSES],
      receipt_statuses: [...IDENTITY_VERIFICATION_RECEIPT_STATUSES],
      destination_input: "opaque_reference_only",
      code_input: "opaque_reference_only",
      ttl_required: true,
      attempt_cap_required: true,
      resend_cooldown_required: true,
      single_use_required: true,
    },
    public_safety: {
      raw_email_present: false,
      raw_phone_present: false,
      raw_password_present: false,
      raw_otp_present: false,
      oauth_code_present: false,
      oauth_token_present: false,
      provider_secret_present: false,
      provider_subject_digest_present: false,
      provider_subject_presence_marker_only: true,
    },
  };
}

export function normalizeUnifiedIdentityProvider(value: string): UnifiedIdentityProvider {
  const provider = String(value ?? "").trim().toLowerCase();
  if (!(UNIFIED_IDENTITY_PROVIDERS as readonly string[]).includes(provider)) {
    throw new UnifiedIdentityContractError(
      "identity provider is not supported",
      "identity_provider_not_supported",
    );
  }
  return provider as UnifiedIdentityProvider;
}

export function identityAccountRoute(accountId: string): string {
  return `/v1/accounts/${segment("account_id", accountId)}`;
}

export function identityCredentialsRoute(accountId: string): string {
  return `${identityAccountRoute(accountId)}/credentials`;
}

export function identityMembershipsRoute(accountId: string): string {
  return `${identityAccountRoute(accountId)}/memberships`;
}

export function identityLinkRoute(accountId: string, provider: string): string {
  return `${identityCredentialsRoute(accountId)}/${encodeURIComponent(
    normalizeUnifiedIdentityProvider(provider),
  )}/link`;
}

export function identityUnlinkRoute(accountId: string, credentialId: string): string {
  return `${identityCredentialsRoute(accountId)}/${segment("credential_id", credentialId)}/unlink`;
}

export function identityMergeRoute(canonicalAccountId: string): string {
  return `${identityAccountRoute(canonicalAccountId)}/merge`;
}

export function identityRecoveryStartRoute(accountId: string): string {
  return `${identityAccountRoute(accountId)}/recovery/start`;
}

export function identityRecoveryCompleteRoute(accountId: string, recoveryId: string): string {
  return `${identityAccountRoute(accountId)}/recovery/${segment("recovery_id", recoveryId)}/complete`;
}

export function identityVerificationChallengesRoute(): string {
  return "/v1/identity/verifications/challenges";
}

export function identityVerificationChallengeRoute(challengeId: string): string {
  return `${identityVerificationChallengesRoute()}/${segment("challenge_id", challengeId)}`;
}

export function identityVerificationResendRoute(challengeId: string): string {
  return `${identityVerificationChallengeRoute(challengeId)}/resend`;
}

export function identityVerificationVerifyRoute(challengeId: string): string {
  return `${identityVerificationChallengeRoute(challengeId)}/verify`;
}

export const identityVerificationChallengeCreateRoute = identityVerificationChallengesRoute;
export const identityVerificationChallengeVerifyRoute = identityVerificationVerifyRoute;

export function assertPublicUnifiedIdentityPayload(
  value: unknown,
): asserts value is Record<string, unknown> {
  if (!isRecord(value)) {
    throw new UnifiedIdentityContractError("identity payload must be an object");
  }
  visitPublicPayload(value, []);
}

export function parseIdentityCredential(value: unknown): IdentityCredential {
  assertPublicUnifiedIdentityPayload(value);
  const provider = normalizeUnifiedIdentityProvider(requireString(value, "provider"));
  return {
    credential_id: requireIdentifier("credential_id", value.credential_id),
    account_id: requireIdentifier("account_id", value.account_id),
    provider,
    provider_subject_present: requireBoolean(
      "provider_subject_present",
      value.provider_subject_present,
    ),
    status: requireEnum("credential status", value.status, UNIFIED_IDENTITY_CREDENTIAL_STATUSES),
    verified: requireBoolean("verified", value.verified),
    display_hint: requireDisplayHint(provider, value.display_hint),
    linked_at: requireTimestamp("linked_at", value.linked_at),
    last_used_at: optionalTimestamp("last_used_at", value.last_used_at),
    revoked_at: optionalTimestamp("revoked_at", value.revoked_at),
  };
}

export function parseIdentityMembership(value: unknown): IdentityMembership {
  assertPublicUnifiedIdentityPayload(value);
  return {
    membership_id: requireIdentifier("membership_id", value.membership_id),
    account_id: requireIdentifier("account_id", value.account_id),
    tenant_id: requireIdentifier("tenant_id", value.tenant_id),
    project_id: optionalIdentifier("project_id", value.project_id),
    role: requireEnum("membership role", value.role, UNIFIED_IDENTITY_MEMBERSHIP_ROLES),
    status: requireEnum("membership status", value.status, UNIFIED_IDENTITY_MEMBERSHIP_STATUSES),
    joined_at: requireTimestamp("joined_at", value.joined_at),
  };
}

export function parseUnifiedAccount(value: unknown): UnifiedAccount {
  assertPublicUnifiedIdentityPayload(value);
  const accountId = requireIdentifier("account_id", value.account_id);
  const credentials = mappingSequence(value, "credentials", true).map(parseIdentityCredential);
  const memberships = mappingSequence(value, "memberships", true).map(parseIdentityMembership);
  if ([...credentials, ...memberships].some((item) => item.account_id !== accountId)) {
    throw new UnifiedIdentityContractError("nested identity resource account mismatch");
  }
  if (value.schema_version !== undefined && value.schema_version !== UNIFIED_IDENTITY_SCHEMA_VERSION) {
    throw new UnifiedIdentityContractError("unified identity schema version mismatch");
  }
  return {
    schema_version: UNIFIED_IDENTITY_SCHEMA_VERSION,
    account_id: accountId,
    status: requireEnum("account status", value.status, UNIFIED_IDENTITY_ACCOUNT_STATUSES),
    display_name: optionalPublicText(value.display_name),
    created_at: requireTimestamp("created_at", value.created_at),
    updated_at: requireTimestamp("updated_at", value.updated_at),
    merged_into_account_id: optionalIdentifier("merged_into_account_id", value.merged_into_account_id),
    credentials,
    memberships,
  };
}

export function parseIdentityLink(value: unknown): IdentityLink {
  assertPublicUnifiedIdentityPayload(value);
  return {
    link_id: requireIdentifier("link_id", value.link_id),
    account_id: requireIdentifier("account_id", value.account_id),
    provider: normalizeUnifiedIdentityProvider(requireString(value, "provider")),
    status: requireEnum("link status", value.status, ["pending", "linked", "expired"] as const),
    expires_at: requireTimestamp("expires_at", value.expires_at),
    authorize_url: optionalPublicUrl("authorize_url", value.authorize_url),
    verification_required: requireBoolean(
      "verification_required",
      value.verification_required ?? true,
    ),
  };
}

export function parseIdentityUnlink(value: unknown): IdentityUnlink {
  assertPublicUnifiedIdentityPayload(value);
  return {
    account_id: requireIdentifier("account_id", value.account_id),
    credential_id: requireIdentifier("credential_id", value.credential_id),
    provider: normalizeUnifiedIdentityProvider(requireString(value, "provider")),
    unlinked: requireBoolean("unlinked", value.unlinked),
    revocation_status: requireEnum(
      "revocation status",
      value.revocation_status,
      ["revoked", "not_required", "pending", "failed"] as const,
    ),
  };
}

export function parseIdentityMerge(value: unknown): IdentityMerge {
  assertPublicUnifiedIdentityPayload(value);
  if (!isRecord(value.canonical_account)) {
    throw new UnifiedIdentityContractError("canonical_account is required");
  }
  const canonicalAccount = parseUnifiedAccount(value.canonical_account);
  const mergedAccountIds = scalarSequence(value, "merged_account_ids").map((item) =>
    requireIdentifier("merged_account_id", item),
  );
  if (mergedAccountIds.includes(canonicalAccount.account_id)) {
    throw new UnifiedIdentityContractError(
      "canonical account cannot be listed as merged",
      "identity_merge_cycle",
    );
  }
  return {
    merge_id: requireIdentifier("merge_id", value.merge_id),
    canonical_account: canonicalAccount,
    merged_account_ids: mergedAccountIds,
    credentials_repointed: requireNonNegativeInteger(
      "credentials_repointed",
      value.credentials_repointed,
    ),
    memberships_repointed: requireNonNegativeInteger(
      "memberships_repointed",
      value.memberships_repointed,
    ),
    completed_at: requireTimestamp("completed_at", value.completed_at),
  };
}

export function parseIdentityRecovery(value: unknown): IdentityRecovery {
  assertPublicUnifiedIdentityPayload(value);
  const provider = normalizeRecoveryProvider(requireString(value, "provider"));
  return {
    recovery_id: requireIdentifier("recovery_id", value.recovery_id),
    account_id: requireIdentifier("account_id", value.account_id),
    provider,
    destination_hint: requireDisplayHint(provider, value.destination_hint),
    status: requireEnum(
      "recovery status",
      value.status,
      ["pending", "verified", "completed", "expired", "locked"] as const,
    ),
    expires_at: requireTimestamp("expires_at", value.expires_at),
    attempts_remaining: requireNonNegativeInteger(
      "attempts_remaining",
      value.attempts_remaining,
    ),
  };
}

export function parseIdentityVerificationChallenge(
  value: unknown,
): IdentityVerificationChallenge {
  assertPublicUnifiedIdentityPayload(value);
  const provider = normalizeVerificationProvider(requireString(value, "provider"));
  const status = requireEnum(
    "verification challenge status",
    value.status,
    IDENTITY_VERIFICATION_CHALLENGE_STATUSES,
  );
  const createdAt = requireTimestamp("created_at", value.created_at);
  const expiresAt = requireTimestamp("expires_at", value.expires_at);
  const ttlSeconds = requirePositiveInteger("ttl_seconds", value.ttl_seconds);
  const attemptCap = requirePositiveInteger("attempt_cap", value.attempt_cap);
  const attemptsRemaining = requireNonNegativeInteger(
    "attempts_remaining", value.attempts_remaining,
  );
  if (attemptsRemaining > attemptCap) {
    throw new UnifiedIdentityContractError("attempts_remaining cannot exceed attempt_cap");
  }
  if (value.single_use !== true) {
    throw new UnifiedIdentityContractError("verification challenge must be single-use");
  }
  const verifiedAt = optionalTimestamp("verified_at", value.verified_at);
  const consumedAt = optionalTimestamp("consumed_at", value.consumed_at);
  if (status === "verified" && verifiedAt === null) {
    throw new UnifiedIdentityContractError("verified challenge requires verified_at");
  }
  if (status === "consumed" && consumedAt === null) {
    throw new UnifiedIdentityContractError("consumed challenge requires consumed_at");
  }
  return {
    challenge_id: requireIdentifier("challenge_id", value.challenge_id),
    provider,
    purpose: normalizeVerificationPurpose(requireString(value, "purpose")),
    status,
    destination_hint: requireDisplayHint(provider, value.destination_hint),
    destination_digest_ref: requireDigestReference(
      "destination_digest_ref",
      value.destination_digest_ref,
    ),
    created_at: createdAt,
    expires_at: expiresAt,
    ttl_seconds: ttlSeconds,
    attempt_cap: attemptCap,
    attempts_remaining: attemptsRemaining,
    resend_cooldown_seconds: requirePositiveInteger(
      "resend_cooldown_seconds",
      value.resend_cooldown_seconds,
    ),
    resend_available_at: requireTimestamp("resend_available_at", value.resend_available_at),
    single_use: true,
    account_id: optionalIdentifier("account_id", value.account_id),
    verified_at: verifiedAt,
    consumed_at: consumedAt,
  };
}

export function parseIdentityVerificationReceipt(value: unknown): IdentityVerificationReceipt {
  assertPublicUnifiedIdentityPayload(value);
  const status = requireEnum(
    "verification receipt status", value.status, IDENTITY_VERIFICATION_RECEIPT_STATUSES,
  );
  if (value.single_use !== true) {
    throw new UnifiedIdentityContractError("verification receipt must be single-use");
  }
  const verifiedAt = requireTimestamp("verified_at", value.verified_at);
  const expiresAt = requireTimestamp("expires_at", value.expires_at);
  const consumedAt = optionalTimestamp("consumed_at", value.consumed_at);
  if (status === "consumed" && consumedAt === null) {
    throw new UnifiedIdentityContractError("consumed receipt requires consumed_at");
  }
  return {
    receipt_id: requireIdentifier("receipt_id", value.receipt_id),
    challenge_id: requireIdentifier("challenge_id", value.challenge_id),
    provider: normalizeVerificationProvider(requireString(value, "provider")),
    purpose: normalizeVerificationPurpose(requireString(value, "purpose")),
    status,
    destination_digest_ref: requireDigestReference(
      "destination_digest_ref",
      value.destination_digest_ref,
    ),
    verified_at: verifiedAt,
    expires_at: expiresAt,
    single_use: true,
    account_id: optionalIdentifier("account_id", value.account_id),
    consumed_at: consumedAt,
  };
}

export function parseUnifiedIdentityError(value: unknown): UnifiedIdentityError {
  assertPublicUnifiedIdentityPayload(value);
  const error = isRecord(value.error) ? value.error : value;
  const code = requireEnum("identity error code", error.code, UNIFIED_IDENTITY_ERROR_CODES);
  const provider = error.provider === undefined || error.provider === null
    ? null
    : normalizeUnifiedIdentityProvider(requireString(error, "provider"));
  return {
    code,
    message: optionalPublicText(error.message) ?? "",
    retryable: requireBoolean("retryable", error.retryable ?? false),
    provider,
    retry_after_seconds: error.retry_after_seconds === undefined || error.retry_after_seconds === null
      ? null
      : requireNonNegativeInteger("retry_after_seconds", error.retry_after_seconds),
  };
}

export async function parseCliSafeIdentityJson(
  response: Response,
): Promise<Record<string, unknown>> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.includes("application/json")) {
    throw new UnifiedIdentityContractError("identity response must be JSON", "identity_store_failed");
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new UnifiedIdentityContractError(
      "identity response contained invalid JSON",
      "identity_store_failed",
    );
  }
  assertPublicUnifiedIdentityPayload(payload);
  return payload;
}

export function toCliSafeIdentityOutput(value: unknown): string {
  assertPublicUnifiedIdentityPayload(value);
  return `${JSON.stringify(value)}\n`;
}

export const parseUnifiedCredential = parseIdentityCredential;
export const parseUnifiedMembership = parseIdentityMembership;
export const parseUnifiedCredentialLink = parseIdentityLink;
export const parseUnifiedCredentialUnlink = parseIdentityUnlink;
export const parseUnifiedAccountMerge = parseIdentityMerge;
export const parseUnifiedRecovery = parseIdentityRecovery;

function visitPublicPayload(value: unknown, path: string[]): void {
  if (Array.isArray(value)) {
    value.forEach((item) => visitPublicPayload(item, path));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.trim().toLowerCase().replaceAll("-", "_");
    const canonical = normalized.replace(/[^a-z0-9]/gu, "");
    const itemPath = [...path, normalized];
    const safeErrorDestination = normalized === "destination"
      && isSafeErrorDetailsDestination(path, item);
    const stableErrorCode = normalized === "code"
      && path.length === 1
      && path[0] === "error";
    const contextuallySafeKey = safeErrorDestination || stableErrorCode;
    if (
      !contextuallySafeKey
      && (
        FORBIDDEN_PUBLIC_KEYS.has(normalized)
        || FORBIDDEN_KEY_SUFFIXES.some((suffix) => normalized.endsWith(suffix))
        || FORBIDDEN_CANONICAL_KEYS.has(canonical)
      )
    ) {
      throw new UnifiedIdentityContractError("identity payload contains raw sensitive material");
    }
    visitPublicPayload(item, itemPath);
  }
}

function isSafeErrorDetailsDestination(path: string[], value: unknown): boolean {
  if (
    path.length !== 2
    || path[0] !== "error"
    || path[1] !== "details"
    || typeof value !== "string"
    || value.length === 0
    || value.length > 160
  ) {
    return false;
  }
  return !/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/u.test(value)
    && !/\+?[1-9]\d{7,14}/u.test(value);
}

function normalizeRecoveryProvider(value: string): "phone" | "email" {
  const provider = normalizeUnifiedIdentityProvider(value);
  if (!RECOVERY_PROVIDERS.has(provider)) {
    throw new UnifiedIdentityContractError(
      "recovery provider must be phone or email",
      "identity_provider_not_supported",
    );
  }
  return provider as "phone" | "email";
}

function normalizeVerificationProvider(value: string): IdentityVerificationProvider {
  const provider = normalizeUnifiedIdentityProvider(value);
  if (!VERIFICATION_PROVIDERS.has(provider)) {
    throw new UnifiedIdentityContractError(
      "verification provider must be phone or email",
      "identity_provider_not_supported",
    );
  }
  return provider as IdentityVerificationProvider;
}

function normalizeVerificationPurpose(value: string): IdentityVerificationPurpose {
  return requireEnum("verification purpose", value, IDENTITY_VERIFICATION_PURPOSES);
}

function segment(field: string, value: unknown): string {
  return encodeURIComponent(requireIdentifier(field, value));
}

function requireIdentifier(field: string, value: unknown): string {
  const text = String(value ?? "").trim();
  if (!IDENTIFIER_PATTERN.test(text)) {
    throw new UnifiedIdentityContractError(`${field} is invalid`);
  }
  return text;
}

function optionalIdentifier(field: string, value: unknown): string | null {
  return value === undefined || value === null || value === "" ? null : requireIdentifier(field, value);
}

function requireString(value: Record<string, unknown>, field: string): string {
  if (typeof value[field] !== "string") {
    throw new UnifiedIdentityContractError(`${field} is required`);
  }
  return value[field];
}

function requireBoolean(field: string, value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new UnifiedIdentityContractError(`${field} must be boolean`);
  }
  return value;
}

function requireNonNegativeInteger(field: string, value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new UnifiedIdentityContractError(`${field} must be a non-negative integer`);
  }
  return value;
}

function requirePositiveInteger(field: string, value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new UnifiedIdentityContractError(`${field} must be a positive integer`);
  }
  return value;
}

function requireBoundedPositiveInteger(
  field: string,
  value: unknown,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number"
    || !Number.isInteger(value)
    || value < minimum
    || value > maximum
  ) {
    throw new UnifiedIdentityContractError(
      `${field} must be an integer from ${minimum} through ${maximum}`,
    );
  }
  return value;
}

function requireBoundedNonNegativeInteger(
  field: string,
  value: unknown,
  maximum: number,
): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > maximum) {
    throw new UnifiedIdentityContractError(
      `${field} must be a non-negative integer no greater than ${maximum}`,
    );
  }
  return value;
}

function requirePrivateInputReference(field: string, value: unknown): string {
  const reference = requireIdentifier(field, value);
  const lowered = reference.toLowerCase();
  if (
    !reference.includes(":")
    || reference.includes("@")
    || lowered.startsWith("mailto:")
    || lowered.startsWith("tel:")
    || lowered.startsWith("sms:")
  ) {
    throw new UnifiedIdentityContractError(
      `${field} must not contain raw destination or verification material`,
    );
  }
  return reference;
}

function requireDigestReference(field: string, value: unknown): string {
  const reference = requireIdentifier(field, value);
  const lowered = reference.toLowerCase();
  if (
    !reference.includes(":")
    || lowered.startsWith("sha256:")
    || lowered.startsWith("sha-256:")
    || lowered.startsWith("mailto:")
    || lowered.startsWith("tel:")
  ) {
    throw new UnifiedIdentityContractError(
      `${field} must be an opaque server-side digest reference`,
    );
  }
  return reference;
}

function requireEnum<T extends string>(
  field: string,
  value: unknown,
  allowed: readonly T[],
): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new UnifiedIdentityContractError(`${field} is invalid`);
  }
  return value as T;
}

function requireTimestamp(field: string, value: unknown): string {
  if (typeof value !== "string" || value.trim() === "" || Number.isNaN(Date.parse(value))) {
    throw new UnifiedIdentityContractError(`${field} must be a timestamp`);
  }
  return value;
}

function optionalTimestamp(field: string, value: unknown): string | null {
  return value === undefined || value === null || value === "" ? null : requireTimestamp(field, value);
}

function optionalPublicText(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || value.length > 512) {
    throw new UnifiedIdentityContractError("public identity text is invalid");
  }
  return redactIdentityText(value);
}

function requireDisplayHint(provider: UnifiedIdentityProvider, value: unknown): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 160) {
    throw new UnifiedIdentityContractError("identity display hint is invalid");
  }
  if (provider === "email" && (!value.includes("@") || !value.includes("*"))) {
    throw new UnifiedIdentityContractError("email display hint must be masked");
  }
  if (provider === "phone" && (!value.includes("*") || /\d{5,}/u.test(value))) {
    throw new UnifiedIdentityContractError("phone display hint must be masked");
  }
  return value;
}

function optionalPublicUrl(field: string, value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string" || value.length > 4096) {
    throw new UnifiedIdentityContractError(`${field} is invalid`);
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new UnifiedIdentityContractError(`${field} is invalid`);
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new UnifiedIdentityContractError(`${field} is invalid`);
  }
  return value;
}

function mappingSequence(
  value: Record<string, unknown>,
  field: string,
  optional = false,
): Record<string, unknown>[] {
  const items = value[field];
  if (optional && items === undefined) return [];
  if (!Array.isArray(items) || items.some((item) => !isRecord(item))) {
    throw new UnifiedIdentityContractError(`${field} must be an array of objects`);
  }
  return items as Record<string, unknown>[];
}

function scalarSequence(value: Record<string, unknown>, field: string): unknown[] {
  if (!Array.isArray(value[field])) {
    throw new UnifiedIdentityContractError(`${field} must be an array`);
  }
  return value[field];
}

function validateHeaders(headers: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (/[\r\n]/u.test(key) || /[\r\n]/u.test(value)) {
      throw new UnifiedIdentityContractError("identity headers must not contain newlines");
    }
    result[key] = value;
  }
  return result;
}

function validateTimeout(value: number): number {
  if (!Number.isInteger(value) || value < 1 || value > 120_000) {
    throw new UnifiedIdentityContractError("timeoutMs must be between 1 and 120000");
  }
  return value;
}

function redactIdentityText(value: string): string {
  return String(value)
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/gu, "[redacted]")
    .replace(/\+?\d[\d\s()-]{8,}\d/gu, "[redacted]")
    .replace(/\b(?:gh[opsu]_[A-Za-z0-9_]+|ya29\.[A-Za-z0-9._-]+)\b/gu, "[redacted]");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
