import assert from "node:assert/strict";
import test from "node:test";

import {
  A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
  IdentityLifecycleHttpClient,
  IdentityLifecycleHttpError,
  IdentityLifecycleHTTPClient,
  IdentityLifecycleHTTPError,
  IdentityLifecycleHTTPResponse,
  IdentityLifecycleTransportError,
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
  a3IdentityContractManifest,
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
  parseIdentityLoginCompleteRequest,
  parseIdentityLoginStartRequest,
  parseIdentityLifecycleEnvelope,
  parseIdentityLink,
  parseIdentityMembership,
  parseIdentityMerge,
  parseIdentityRecovery,
  parseIdentityRegistrationCompleteRequest,
  parseIdentityRegistrationStartRequest,
  parseA3IdentityProviderCapability,
  parseIdentityUnlink,
  parseUnifiedAccount,
  parseUnifiedIdentityError,
  toCliSafeIdentityOutput,
  unifiedIdentityContractManifest,
} from "../dist/unified-identity.js";

test("Python-compatible identity lifecycle HTTP exports remain usable", () => {
  assert.equal(IdentityLifecycleHTTPClient, IdentityLifecycleHttpClient);
  assert.equal(IdentityLifecycleHTTPError, IdentityLifecycleHttpError);
  const response = new IdentityLifecycleHTTPResponse(200, providerCapabilities());
  assert.equal(response.status, 200);
  assert.equal(response.payload.schema_version, A3_IDENTITY_CONTRACT_SCHEMA_VERSION);
  assert.throws(
    () => new IdentityLifecycleHTTPResponse(99, {}),
    UnifiedIdentityContractError,
  );
});

function lifecycleEnvelope(operation, overrides = {}) {
  return {
    schema_version: A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
    operation,
    status: operation.endsWith("_start") ? "verification_required" : "completed",
    provider: "email",
    account: operation.endsWith("_start") ? null : {
      account_id: "account_01",
      password_status: "set",
      two_factor: { status: "disabled", optional: true, recommended: true },
    },
    next_action: operation.endsWith("_start") ? "verify_email" : "none",
    security: {
      server_verified_proof_required: true,
      recent_reauthentication_required: false,
      csrf_required: false,
      account_enumeration_safe: true,
    },
    receipt_id: operation.endsWith("_start") ? "receipt_01" : null,
    expires_at: operation.endsWith("_start") ? "2026-07-12T01:00:00Z" : null,
    authenticated_at: operation === "login_complete" ? "2026-07-12T00:00:00Z" : null,
    ...overrides,
  };
}

function providerCapabilities() {
  return {
    schema_version: A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
    providers: [{
      provider: "email",
      preferred: true,
      enabled: true,
      code_capability: "implemented",
      deployment_readiness: "ready",
      deployment_status_source: "runtime_configuration",
      environment: "production",
      qualification_status: "not_required",
      requires_business_qualification: false,
      registration_status: "available",
      login_status: "available",
      linking_status: "available",
      reason_code: null,
    }, {
      provider: "wechat",
      preferred: false,
      enabled: false,
      code_capability: "contract_only",
      deployment_readiness: "blocked",
      deployment_status_source: "business_qualification",
      environment: "production",
      qualification_status: "required",
      requires_business_qualification: true,
      registration_status: "unavailable",
      login_status: "unavailable",
      linking_status: "unavailable",
      reason_code: "business_qualification_required",
    }],
  };
}

test("lifecycle HTTP client executes provider, registration, and login routes", async () => {
  const calls = [];
  const replies = [
    response(providerCapabilities()),
    response(lifecycleEnvelope("register_start")),
    response(lifecycleEnvelope("register_complete")),
    response(lifecycleEnvelope("login_start")),
    response(lifecycleEnvelope("login_complete", { status: "authenticated" })),
  ];
  const client = new IdentityLifecycleHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (url, init) => {
      calls.push({
        url: String(url),
        method: init.method,
        body: init.body ? JSON.parse(init.body) : null,
      });
      return replies.shift();
    },
  });

  const capabilities = await client.providerCapabilities();
  assert.equal(capabilities.providers[0].code_capability, "implemented");
  assert.equal(capabilities.providers[1].qualification_status, "required");
  await client.registrationStart({
    provider: "email", tenant_id: "tenant_01", project_id: "project_01",
  });
  await client.registrationComplete({
    proof_receipt_id: "receipt_register",
    tenant_id: "tenant_01",
    project_id: "project_01",
  });
  await client.loginStart({
    provider: "email", tenant_id: "tenant_01", project_id: "project_01",
  });
  await client.loginComplete({
    proof_receipt_id: "receipt_login",
    tenant_id: "tenant_01",
    project_id: "project_01",
  });

  assert.deepEqual(calls.map(({ method, url }) => [method, new URL(url).pathname]), [
    ["GET", "/v1/identity/providers"],
    ["POST", "/v1/identity/registration/start"],
    ["POST", "/v1/identity/registration/complete"],
    ["POST", "/v1/identity/login/start"],
    ["POST", "/v1/identity/login/complete"],
  ]);
  assert.deepEqual(calls[2].body, {
    receipt_id: "receipt_register", tenant_id: "tenant_01", project_id: "project_01",
  });
  assert.deepEqual(calls[4].body, {
    receipt_id: "receipt_login", tenant_id: "tenant_01", project_id: "project_01",
  });
  for (const call of calls.slice(1)) {
    assert.equal("create_account" in call.body, false);
    assert.equal("bind_credential" in call.body, false);
    assert.equal("merge_accounts" in call.body, false);
    assert.equal("match_by_email" in call.body, false);
  }
});

test("unknown identity and invalid credential share one anti-enumeration error", async () => {
  const failures = ["unknown", "invalid"];
  for (const failure of failures) {
    const client = new IdentityLifecycleHttpClient({
      baseUrl: "http://127.0.0.1:8787",
      fetch: async () => response(lifecycleEnvelope("login_complete", {
        status: "failed",
        account: null,
        next_action: "none",
        receipt_id: null,
        expires_at: null,
        authenticated_at: null,
        error: {
          code: "authentication_failed",
          http_status: 401,
          anti_enumeration: true,
          retryable: false,
          public_safe: true,
        },
      }), 401),
    });
    await assert.rejects(
      client.loginComplete({
        proof_receipt_id: `receipt_${failure}`,
        tenant_id: "tenant_01",
        project_id: "project_01",
      }),
      (error) => error instanceof IdentityLifecycleHttpError
        && error.code === "authentication_failed"
        && error.httpStatus === 401
        && error.antiEnumeration === true
        && !error.message.includes(failure),
    );
  }
});

test("provider GET retries bounded transient failures but lifecycle POST never retries", async () => {
  const delays = [];
  let gets = 0;
  const getClient = new IdentityLifecycleHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    maxRetries: 2,
    retryBackoffMs: 5,
    sleep: async (delay) => delays.push(delay),
    fetch: async () => {
      gets += 1;
      return gets < 3
        ? response({ error: { code: "service_unavailable" } }, 503)
        : response(providerCapabilities());
    },
  });
  assert.equal((await getClient.providerCapabilities()).providers.length, 2);
  assert.equal(gets, 3);
  assert.deepEqual(delays, [5, 10]);

  let posts = 0;
  const postClient = new IdentityLifecycleHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    maxRetries: 9,
    fetch: async () => {
      posts += 1;
      throw new TypeError("network unavailable");
    },
  });
  await assert.rejects(
    postClient.loginStart({
      provider: "email", tenant_id: "tenant_01", project_id: "project_01",
    }),
    (error) => error instanceof IdentityLifecycleTransportError
      && error.retryable === false
      && error.publicSafe === true,
  );
  assert.equal(posts, 1);
});

test("lifecycle parser rejects unsafe errors and operation mismatch", async () => {
  assert.throws(
    () => parseIdentityLifecycleEnvelope(lifecycleEnvelope("login_complete", {
      status: "failed",
      account: null,
      error: {
        code: "authentication_failed",
        http_status: 401,
        anti_enumeration: true,
        retryable: false,
        public_safe: false,
      },
    })),
    /public-safe/u,
  );
  const client = new IdentityLifecycleHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async () => response(lifecycleEnvelope("register_start")),
  });
  await assert.rejects(
    client.loginStart({
      provider: "email", tenant_id: "tenant_01", project_id: "project_01",
    }),
    /operation mismatch/u,
  );
});

test("A3 registration and login contract is explicit and fail closed", () => {
  const contract = a3IdentityContractManifest();
  const routes = new Map(contract.routes.map((route) => [route.operation, route]));
  const providers = new Map(contract.providers.map((provider) => [provider.provider, provider]));

  assert.equal(contract.schema_version, A3_IDENTITY_CONTRACT_SCHEMA_VERSION);
  assert.notEqual(routes.get("register_start").path, routes.get("login_start").path);
  assert.equal(contract.registration.may_create_account, true);
  assert.equal(contract.login.may_create_account, false);
  assert.equal(contract.login.may_merge_accounts, false);
  assert.equal(contract.login.may_link_credentials, false);
  assert.equal(contract.login.existing_verified_credential_required, true);
  assert.equal(contract.login.unknown_identity_status, "failed");
  assert.equal(contract.login.verified_email_conflict_status, "merge_required");
  assert.equal(contract.login.public_failure_code, "authentication_failed");
  assert.equal(contract.login.public_failure_http_status, 401);
  assert.equal(contract.login.account_enumeration_safe, true);
  assert.equal(contract.login.unknown_and_invalid_secret_share_public_failure, true);
  assert.equal(contract.login.unknown_identity_next_action, null);
  for (const name of ["public_registration", "public_login"]) {
    const security = contract.operation_security[name];
    assert.equal(security.authenticated_actor_required, false);
    assert.equal(security.matching_authenticated_actor_required, false);
    assert.equal(security.recent_reauthentication_required, false);
    assert.equal(security.csrf_required, false);
    assert.equal(security.verified_assertion_required, true);
    assert.equal(security.verified_assertion_source, "server_owned_single_use_proof_receipt");
    if (name === "public_registration") {
      assert.equal(security.legacy_accountless_binding_http_rejected, true);
    }
    assert.equal(security.route_lifecycle, "active");
    assert.equal(security.client_callable, true);
  }
  const bindingSecurity = contract.operation_security.existing_account_binding;
  assert.equal(bindingSecurity.explicit_user_action_required, true);
  assert.equal(bindingSecurity.authenticated_actor_required, true);
  assert.equal(bindingSecurity.matching_authenticated_actor_required, true);
  assert.equal(bindingSecurity.recent_reauthentication_required, true);
  assert.equal(bindingSecurity.csrf_required, true);
  assert.equal(bindingSecurity.verified_assertion_required, true);
  assert.equal(bindingSecurity.atomic_completion_required, true);
  assert.equal(bindingSecurity.proof_receipt_consumed_with_mutation, true);
  assert.equal(bindingSecurity.mutation_ticket_consumed_with_step_up, true);
  assert.equal(bindingSecurity.activation_requires_postgres_coordinator, true);
  assert.equal(
    bindingSecurity.go_atomic_coordinator_contract,
    "IdentityCredentialLinkCoordinator",
  );
  assert.equal(bindingSecurity.route_lifecycle, "proposed");
  assert.equal(bindingSecurity.client_callable, false);
  for (const route of contract.routes) {
    assert.equal(["active", "proposed", "non_routable", "unavailable"].includes(route.lifecycle), true);
    assert.equal(route.client_callable, route.lifecycle === "active");
  }
  for (const operation of [
    "link_start", "link_complete", "unlink", "password_set", "password_change",
    "two_factor_enroll", "two_factor_verify", "two_factor_recovery", "two_factor_disable",
  ]) {
    assert.equal(routes.get(operation).lifecycle, "proposed");
    assert.equal(routes.get(operation).client_callable, false);
  }
  assert.equal(contract.preferred_registration_provider, "email");
  assert.equal(providers.get("email").preferred_registration, true);
  assert.equal(providers.get("github").login, "runtime_configuration_required");
  assert.equal(providers.get("google").login, "runtime_configuration_required");
  for (const name of ["github", "google"]) {
    assert.equal(providers.get(name).code_capability, "route_and_handler_implemented");
    assert.equal(providers.get(name).deployment_readiness, "runtime_configuration_required");
    assert.equal(providers.get(name).deployment_status_source, "runtime_configuration");
    assert.equal(providers.get(name).reason_code, "provider_not_configured");
  }
  for (const name of ["email", "github", "google"]) {
    assert.equal(providers.get(name).linking, "proposed");
  }
  for (const name of ["wechat", "qq", "alipay"]) {
    assert.equal(providers.get(name).login, "unavailable");
    assert.equal(providers.get(name).linking, "unavailable");
    assert.equal(providers.get(name).requires_business_qualification, true);
    assert.equal(providers.get(name).deployment_readiness, "business_qualification_required");
    assert.equal(providers.get(name).deployment_status_source, "business_qualification");
  }
  assert.equal(providers.get("phone").linking, "unavailable");
  assert.equal(contract.account_mutations.two_factor_optional, true);
  assert.equal(contract.account_mutations.two_factor_recommended, true);
});

test("provider capability parser rejects contradictory machine status fields", () => {
  const github = a3IdentityContractManifest().providers.find((item) => item.provider === "github");
  assert.deepEqual(parseA3IdentityProviderCapability(github), github);
  assert.throws(
    () => parseA3IdentityProviderCapability({
      ...github,
      deployment_readiness: "ready",
    }),
    (error) => error instanceof UnifiedIdentityContractError,
  );
  assert.throws(
    () => parseA3IdentityProviderCapability({
      ...github,
      deployment_status_source: "business_qualification",
    }),
    (error) => error instanceof UnifiedIdentityContractError,
  );
});

test("registration and login public DTOs are distinct and receipt driven", () => {
  const scope = { tenant_id: "tenant_contract", project_id: "project_contract" };
  assert.deepEqual(
    parseIdentityRegistrationStartRequest({ ...scope, provider: "email" }),
    { ...scope, provider: "email" },
  );
  assert.deepEqual(
    parseIdentityLoginStartRequest({ ...scope, provider: "github" }),
    { ...scope, provider: "github" },
  );
  assert.deepEqual(
    parseIdentityRegistrationCompleteRequest({ ...scope, proof_receipt_id: "receipt_register" }),
    { ...scope, proof_receipt_id: "receipt_register" },
  );
  assert.deepEqual(
    parseIdentityLoginCompleteRequest({ ...scope, proof_receipt_id: "receipt_login" }),
    { ...scope, proof_receipt_id: "receipt_login" },
  );
  for (const parser of [
    parseIdentityRegistrationStartRequest,
    parseIdentityRegistrationCompleteRequest,
    parseIdentityLoginStartRequest,
    parseIdentityLoginCompleteRequest,
  ]) {
    assert.throws(
      () => parser({ ...scope, provider: "email", proof_receipt_id: "receipt", verified: true }),
      (error) => error instanceof UnifiedIdentityContractError,
    );
  }
});

test("canonical account parses OAuth email, absent password, and recommended 2FA posture", () => {
  const account = parseUnifiedAccount({
    account_id: "acct_canonical",
    status: "active",
    display_name: "Owner",
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
    credentials: [],
    memberships: [],
    security_posture: {
      primary_email: { present: true, verified: true, source: "google" },
      password: { status: "absent", settable: true },
      two_factor: { status: "disabled", optional: true, recommended: true },
    },
  });
  assert.deepEqual(account.security_posture, {
    primary_email: { present: true, verified: true, source: "google" },
    password: { status: "absent", settable: true },
    two_factor: { status: "disabled", optional: true, recommended: true },
  });
});

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
    display_name: "ReleaseFoundry User",
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
