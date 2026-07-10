import assert from "node:assert/strict";
import test from "node:test";

import {
  UNIFIED_IDENTITY_ACCOUNT_STATUSES,
  UNIFIED_IDENTITY_CREDENTIAL_STATUSES,
  UNIFIED_IDENTITY_ERROR_CODES,
  UNIFIED_IDENTITY_MEMBERSHIP_ROLES,
  UNIFIED_IDENTITY_MEMBERSHIP_STATUSES,
  UNIFIED_IDENTITY_PROVIDERS,
  UNIFIED_IDENTITY_ROUTES,
  UNIFIED_IDENTITY_SCHEMA_VERSION,
  UnifiedIdentityContractError,
  UnifiedIdentityHttpClient,
  assertPublicUnifiedIdentityPayload,
  identityAccountRoute,
  identityCredentialsRoute,
  identityLinkRoute,
  identityMembershipsRoute,
  identityMergeRoute,
  identityRecoveryCompleteRoute,
  identityRecoveryStartRoute,
  identityUnlinkRoute,
  normalizeUnifiedIdentityProvider,
  parseIdentityCredential,
  parseIdentityLink,
  parseIdentityMembership,
  parseIdentityMerge,
  parseIdentityRecovery,
  parseIdentityUnlink,
  parseUnifiedAccount,
  parseUnifiedIdentityError,
  toCliSafeIdentityOutput,
  unifiedIdentityContractManifest,
} from "../dist/unified-identity.js";

import * as sdk from "../dist/index.js";

const now = "2026-07-10T10:00:00Z";

function credential(provider = "github", overrides = {}) {
  return {
    credential_id: `credential_${provider}`,
    account_id: "account_01",
    provider,
    provider_subject_present: true,
    status: "active",
    verified: true,
    display_hint: provider === "email" ? "a***@e***.com" : provider === "phone" ? "***1234" : `${provider}:linked`,
    linked_at: now,
    last_used_at: now,
    revoked_at: null,
    ...overrides,
  };
}

function membership(overrides = {}) {
  return {
    membership_id: "membership_01",
    account_id: "account_01",
    tenant_id: "tenant_01",
    project_id: "project_01",
    role: "owner",
    status: "active",
    joined_at: now,
    ...overrides,
  };
}

function account(overrides = {}) {
  return {
    schema_version: UNIFIED_IDENTITY_SCHEMA_VERSION,
    account_id: "account_01",
    status: "active",
    display_name: "Ashr User",
    created_at: now,
    updated_at: now,
    merged_into_account_id: null,
    credentials: [credential("github"), credential("google"), credential("phone")],
    memberships: [membership()],
    ...overrides,
  };
}

function recovery(overrides = {}) {
  return {
    recovery_id: "recovery_01",
    account_id: "account_01",
    provider: "phone",
    destination_hint: "***1234",
    status: "pending",
    expires_at: "2026-07-10T10:10:00Z",
    attempts_remaining: 3,
    ...overrides,
  };
}

function response(payload, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": contentType },
  });
}

test("barrel and package surface export unified identity", () => {
  assert.equal(typeof sdk.UnifiedIdentityHttpClient, "function");
  assert.equal(typeof sdk.parseUnifiedAccount, "function");
  assert.equal(sdk.UNIFIED_IDENTITY_SCHEMA_VERSION, UNIFIED_IDENTITY_SCHEMA_VERSION);
});

test("constants exactly match the Python public contract", () => {
  assert.deepEqual([...UNIFIED_IDENTITY_PROVIDERS], [
    "github", "google", "wechat", "qq", "alipay", "phone", "email",
  ]);
  assert.deepEqual([...UNIFIED_IDENTITY_ACCOUNT_STATUSES], [
    "active", "suspended", "merged", "recovery_locked",
  ]);
  assert.deepEqual([...UNIFIED_IDENTITY_CREDENTIAL_STATUSES], [
    "pending", "active", "revocation_pending", "revoked",
  ]);
  assert.deepEqual([...UNIFIED_IDENTITY_MEMBERSHIP_ROLES], [
    "owner", "admin", "developer", "viewer", "billing",
  ]);
  assert.deepEqual([...UNIFIED_IDENTITY_MEMBERSHIP_STATUSES], [
    "invited", "active", "suspended", "removed",
  ]);
  assert.deepEqual([...UNIFIED_IDENTITY_ERROR_CODES], [
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
  ]);
});

test("manifest declares one account with provider credentials and membership isolation", () => {
  const manifest = unifiedIdentityContractManifest();
  assert.equal(manifest.subject_model, "one_account_many_credentials");
  assert.deepEqual(manifest.providers, [...UNIFIED_IDENTITY_PROVIDERS]);
  assert.deepEqual(manifest.invariants, {
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
  });
  assert.deepEqual(
    {
      providers: manifest.verification.providers,
      purposes: manifest.verification.purposes,
      challenge_statuses: manifest.verification.challenge_statuses,
      receipt_statuses: manifest.verification.receipt_statuses,
      destination_input: manifest.verification.destination_input,
      code_input: manifest.verification.code_input,
      ttl_required: manifest.verification.ttl_required,
      attempt_cap_required: manifest.verification.attempt_cap_required,
      resend_cooldown_required: manifest.verification.resend_cooldown_required,
      single_use_required: manifest.verification.single_use_required,
    },
    {
    providers: ["email", "phone"],
    purposes: ["binding", "login", "recovery"],
    challenge_statuses: ["pending", "verified", "consumed", "expired", "locked"],
    receipt_statuses: ["verified", "consumed", "expired"],
    destination_input: "opaque_reference_only",
    code_input: "opaque_reference_only",
    ttl_required: true,
    attempt_cap_required: true,
    resend_cooldown_required: true,
    single_use_required: true,
    },
  );
  for (const capability of [
    "durable_receipt_records",
    "append_only_audit",
    "admin_queries_route_neutral",
    "digest_only_envelopes",
    "atomic_receipt_consumption",
    "anti_enumerating_public_failures",
    "media_safe_metadata",
  ]) {
    assert.equal(manifest.verification[capability], true, capability);
  }
  assert.deepEqual(manifest.verification.public_surface, [
    "IdentityVerificationAbuseDimensions",
    "IdentityVerificationAdminFilter",
    "IdentityVerificationAuditEvent",
    "IdentityVerificationAuditEventPage",
    "IdentityVerificationDigestEnvelope",
    "IdentityVerificationDurableReceipt",
    "IdentityVerificationDurableReceiptPage",
    "IdentityVerificationDurableStore",
    "IdentityVerificationMemoryStore",
    "IdentityVerificationTransactionCoordinator",
  ]);
  assert.equal(manifest.public_safety.oauth_token_present, false);
});

test("public DTO guard rejects normalized private reference aliases", () => {
  for (const field of [
    "tokenRef",
    "tokenref",
    "tokenRefId",
    "token-ref-id",
    "revocationOutboxId",
    "revocationoutboxid",
  ]) {
    assert.throws(
      () => assertPublicUnifiedIdentityPayload({ metadata: { nested: { [field]: "private" } } }),
      UnifiedIdentityContractError,
    );
  }
});

test("route manifest and builders exactly match Python routes", () => {
  assert.equal(UNIFIED_IDENTITY_ROUTES.length, 12);
  assert.equal(identityAccountRoute("account_01"), "/v1/accounts/account_01");
  assert.equal(identityCredentialsRoute("account_01"), "/v1/accounts/account_01/credentials");
  assert.equal(identityMembershipsRoute("account_01"), "/v1/accounts/account_01/memberships");
  assert.equal(
    identityLinkRoute("account_01", "google"),
    "/v1/accounts/account_01/credentials/google/link",
  );
  assert.equal(
    identityUnlinkRoute("account_01", "credential_01"),
    "/v1/accounts/account_01/credentials/credential_01/unlink",
  );
  assert.equal(identityMergeRoute("account_01"), "/v1/accounts/account_01/merge");
  assert.equal(identityRecoveryStartRoute("account_01"), "/v1/accounts/account_01/recovery/start");
  assert.equal(
    identityRecoveryCompleteRoute("account_01", "recovery_01"),
    "/v1/accounts/account_01/recovery/recovery_01/complete",
  );
});

for (const provider of UNIFIED_IDENTITY_PROVIDERS) {
  test(`parses ${provider} as a credential of one canonical account`, () => {
    assert.equal(normalizeUnifiedIdentityProvider(provider), provider);
    const parsed = parseIdentityCredential(credential(provider));
    assert.equal(parsed.account_id, "account_01");
    assert.equal(parsed.provider, provider);
    assert.equal(parsed.provider_subject_present, true);
  });
}

test("provider normalization is strict like Python", () => {
  assert.throws(
    () => normalizeUnifiedIdentityProvider("google_oidc"),
    (error) => error instanceof UnifiedIdentityContractError
      && error.code === "identity_provider_not_supported",
  );
});

test("parses nested account credentials and memberships", () => {
  const parsed = parseUnifiedAccount(account());
  assert.equal(parsed.credentials.length, 3);
  assert.equal(parsed.memberships.length, 1);
  assert.equal(parsed.credentials[1].provider, "google");
  assert.equal(parsed.memberships[0].tenant_id, "tenant_01");
});

test("rejects nested resources belonging to another account", () => {
  assert.throws(() => parseUnifiedAccount(account({
    credentials: [credential("github", { account_id: "account_other" })],
  })), /account mismatch/u);
});

test("parses membership roles and joined_at field", () => {
  for (const role of UNIFIED_IDENTITY_MEMBERSHIP_ROLES) {
    assert.equal(parseIdentityMembership(membership({ role })).role, role);
  }
  assert.equal(parseIdentityMembership(membership()).joined_at, now);
});

test("parses link and unlink DTOs", () => {
  const link = parseIdentityLink({
    link_id: "link_01",
    account_id: "account_01",
    provider: "wechat",
    status: "pending",
    expires_at: "2026-07-10T10:10:00Z",
    authorize_url: "https://open.weixin.qq.com/connect",
    verification_required: true,
  });
  const unlink = parseIdentityUnlink({
    account_id: "account_01",
    credential_id: "credential_wechat",
    provider: "wechat",
    unlinked: true,
    revocation_status: "pending",
  });
  assert.equal(link.provider, "wechat");
  assert.equal(unlink.revocation_status, "pending");
});

test("parses merge with canonical account and counts", () => {
  const parsed = parseIdentityMerge({
    merge_id: "merge_01",
    canonical_account: account(),
    merged_account_ids: ["account_source"],
    credentials_repointed: 2,
    memberships_repointed: 1,
    completed_at: now,
  });
  assert.equal(parsed.canonical_account.account_id, "account_01");
  assert.equal(parsed.credentials_repointed, 2);
});

test("merge rejects the canonical account in merged ids", () => {
  assert.throws(
    () => parseIdentityMerge({
      merge_id: "merge_01",
      canonical_account: account(),
      merged_account_ids: ["account_01"],
      credentials_repointed: 0,
      memberships_repointed: 0,
      completed_at: now,
    }),
    (error) => error.code === "identity_merge_cycle",
  );
});

test("recovery permits only phone and email with masked destinations", () => {
  assert.equal(parseIdentityRecovery(recovery()).provider, "phone");
  assert.equal(parseIdentityRecovery(recovery({
    provider: "email",
    destination_hint: "a***@e***.com",
  })).provider, "email");
  assert.throws(
    () => parseIdentityRecovery(recovery({ provider: "github", destination_hint: "github:linked" })),
    (error) => error.code === "identity_provider_not_supported",
  );
});

test("parses stable nested error contract", () => {
  const parsed = parseUnifiedIdentityError({
    error: {
      code: "identity_credential_conflict",
      message: "credential is linked elsewhere",
      retryable: false,
      provider: "github",
      retry_after_seconds: null,
    },
  });
  assert.equal(parsed.code, "identity_credential_conflict");
  assert.equal(parsed.provider, "github");
});

for (const forbidden of [
  "access_token",
  "authorization_code",
  "client_secret",
  "code_verifier",
  "email",
  "email_address",
  "id_token",
  "nonce",
  "otp",
  "password",
  "phone",
  "phone_number",
  "refresh_token",
  "session_token",
  "state",
  "token",
  "destination",
  "destination_value",
  "verification_code",
  "verification_value",
]) {
  test(`rejects nested secret field ${forbidden}`, () => {
    assert.throws(() => assertPublicUnifiedIdentityPayload({
      nested: [{ [forbidden]: "must-not-escape" }],
    }));
  });
}

test("allows opaque receipt references required by the public contract", () => {
  assert.doesNotThrow(() => assertPublicUnifiedIdentityPayload({
    verification_receipt_id: "verify_01",
    step_up_receipt_id: "stepup_01",
    idempotency_key: "idem_01",
  }));
});

for (const forbidden of [
  "provider_subject_sha256",
  "subject_digest",
  "identifier_sha256",
]) {
  test(`rejects stable provider subject field ${forbidden}`, () => {
    assert.throws(() => parseIdentityCredential(credential("wechat", {
      [forbidden]: "a".repeat(64),
    })));
  });
}

test("provider subject presence marker is required and boolean", () => {
  const missing = credential("qq");
  delete missing.provider_subject_present;
  assert.throws(() => parseIdentityCredential(missing), /provider_subject_present/u);
  assert.throws(
    () => parseIdentityCredential(credential("qq", { provider_subject_present: "true" })),
    /provider_subject_present/u,
  );
});

test("masked display hints reject raw email and phone", () => {
  assert.throws(() => parseIdentityCredential(credential("email", { display_hint: "user@example.com" })));
  assert.throws(() => parseIdentityCredential(credential("phone", { display_hint: "+8613812345678" })));
});

test("CLI-safe output rejects secrets and stays single-line", () => {
  assert.equal(toCliSafeIdentityOutput(account()), `${JSON.stringify(account())}\n`);
  assert.throws(() => toCliSafeIdentityOutput({ account: account(), refresh_token: "secret" }));
});

test("HTTP client get and list methods parse Python envelopes", async () => {
  const calls = [];
  const replies = [
    response({ result: account() }),
    response({ result: { credentials: [credential("github")] } }),
    response({ result: { memberships: [membership()] } }),
  ];
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (url, init) => {
      calls.push({ url: String(url), init });
      return replies.shift();
    },
  });
  assert.equal((await client.getAccount("account_01")).account_id, "account_01");
  assert.equal((await client.listCredentials("account_01"))[0].provider, "github");
  assert.equal((await client.listMemberships("account_01"))[0].role, "owner");
  assert.deepEqual(calls.map((call) => call.init.method), ["GET", "GET", "GET"]);
});

test("link request exactly matches Python verification receipt contract", async () => {
  let captured;
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (url, init) => {
      captured = { url: String(url), body: JSON.parse(init.body) };
      return response({ result: {
        link_id: "link_01",
        account_id: "account_01",
        provider: "google",
        status: "pending",
        expires_at: "2026-07-10T10:10:00Z",
        authorize_url: "https://accounts.google.com/o/oauth2/v2/auth",
        verification_required: true,
      } });
    },
  });
  await client.linkCredential({
    accountId: "account_01",
    provider: "google",
    verificationReceiptId: "verify_01",
    idempotencyKey: "idem_link_01",
  });
  assert.match(captured.url, /credentials\/google\/link$/u);
  assert.deepEqual(captured.body, {
    provider: "google",
    idempotency_key: "idem_link_01",
    verification_receipt_id: "verify_01",
  });
});

test("unlink request exactly matches Python step-up contract", async () => {
  let body;
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (_url, init) => {
      body = JSON.parse(init.body);
      return response({ result: {
        account_id: "account_01",
        credential_id: "credential_google",
        provider: "google",
        unlinked: true,
        revocation_status: "revoked",
      } });
    },
  });
  await client.unlinkCredential({
    accountId: "account_01",
    credentialId: "credential_google",
    stepUpReceiptId: "stepup_01",
    idempotencyKey: "idem_unlink_01",
  });
  assert.deepEqual(body, {
    step_up_receipt_id: "stepup_01",
    idempotency_key: "idem_unlink_01",
  });
});

test("merge request and response exactly match Python contract", async () => {
  let captured;
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (url, init) => {
      captured = { url: String(url), body: JSON.parse(init.body) };
      return response({ result: {
        merge_id: "merge_01",
        canonical_account: account(),
        merged_account_ids: ["account_source"],
        credentials_repointed: 1,
        memberships_repointed: 1,
        completed_at: now,
      } });
    },
  });
  const merged = await client.mergeAccounts({
    canonicalAccountId: "account_01",
    sourceAccountId: "account_source",
    stepUpReceiptId: "stepup_01",
    idempotencyKey: "idem_merge_01",
  });
  assert.match(captured.url, /accounts\/account_01\/merge$/u);
  assert.deepEqual(captured.body, {
    source_account_id: "account_source",
    step_up_receipt_id: "stepup_01",
    idempotency_key: "idem_merge_01",
  });
  assert.equal(merged.canonical_account.account_id, "account_01");
  assert.throws(() => client.mergeAccounts({
    canonicalAccountId: "account_01",
    sourceAccountId: "account_01",
    stepUpReceiptId: "stepup_01",
    idempotencyKey: "idem_merge_02",
  }), (error) => error.code === "identity_merge_cycle");
});

test("recovery start and completion exactly match Python receipt contract", async () => {
  const bodies = [];
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (_url, init) => {
      bodies.push(JSON.parse(init.body));
      return bodies.length === 1
        ? response({ result: recovery() })
        : response({ result: account() });
    },
  });
  await client.startRecovery({
    accountId: "account_01",
    provider: "phone",
    idempotencyKey: "idem_recovery_start",
  });
  const recovered = await client.completeRecovery({
    accountId: "account_01",
    recoveryId: "recovery_01",
    verificationReceiptId: "verify_recovery_01",
    idempotencyKey: "idem_recovery_complete",
  });
  assert.deepEqual(bodies, [
    { provider: "phone", idempotency_key: "idem_recovery_start" },
    {
      verification_receipt_id: "verify_recovery_01",
      idempotency_key: "idem_recovery_complete",
    },
  ]);
  assert.equal(recovered.account_id, "account_01");
});

test("HTTP error becomes a stable redacted contract error", async () => {
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async () => response({
      error: {
        code: "identity_credential_conflict",
        message: "user@example.com conflicts with +8613812345678",
        retryable: false,
        provider: "email",
      },
    }, 409),
  });
  await assert.rejects(
    client.getAccount("account_01"),
    (error) => error.code === "identity_credential_conflict"
      && !/example\.com|13812345678/u.test(error.message),
  );
});

test("client validates URL, headers, timeout, and JSON response", async () => {
  assert.throws(() => new UnifiedIdentityHttpClient({ baseUrl: "ftp://example.com" }));
  assert.throws(() => new UnifiedIdentityHttpClient({ baseUrl: "http://user:pass@example.com" }));
  assert.throws(() => new UnifiedIdentityHttpClient({ baseUrl: "http://localhost", timeoutMs: 0 }));
  assert.throws(() => new UnifiedIdentityHttpClient({
    baseUrl: "http://localhost",
    headers: { "x-test": "bad\nvalue" },
  }));
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://localhost",
    fetch: async () => response("<html>", 502, "text/html"),
  });
  await assert.rejects(
    client.getAccount("account_01"),
    (error) => error.code === "identity_store_failed",
  );
});
