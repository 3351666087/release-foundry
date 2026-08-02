import assert from "node:assert/strict";
import test from "node:test";

import {
  ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS,
  ACCOUNT_CONNECTION_ERROR_CODES,
  ACCOUNT_CONNECTION_ROUTES,
  GOOGLE_ACCOUNT_CONNECTION_ISSUERS,
  AccountConnectionError,
  accountConnectionContractManifest,
  assertPublicAccountConnectionPayload,
  createAccountConnectionBinding,
  parseAccountConnection,
  parseAccountConnectionDisconnect,
  parseAccountConnectionError,
  parseAccountConnectionStart,
  validateGoogleAccountConnectionAuthorizeUrl,
  validateGoogleOidcPublicContract,
  verifyGoogleAccountConnectionClaims,
  hashGoogleAccountConnectionNonce,
} from "../dist/account-connections.js";

const digest = "a".repeat(64);
const connectedAt = "2026-07-10T06:00:00Z";

function googleAuthorizeUrl(overrides = {}) {
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  const values = {
    client_id: "google-client",
    redirect_uri: "https://app.example.invalid/oauth/google/callback",
    response_type: "code",
    scope: "openid email profile",
    state: "opaque-state",
    nonce: "opaque-nonce",
    code_challenge: "challenge",
    code_challenge_method: "S256",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) url.searchParams.set(key, value);
  return url.toString();
}

test("TS publishes Python-parity providers, stable errors, issuers, and hosted connection routes", () => {
  assert.deepEqual([...ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS], [
    "github", "google", "wechat", "qq", "alipay", "phone", "email",
  ]);
  assert.deepEqual(GOOGLE_ACCOUNT_CONNECTION_ISSUERS, [
    "https://accounts.google.com",
    "accounts.google.com",
  ]);
  assert.equal(ACCOUNT_CONNECTION_ERROR_CODES.length, 18);
  assert.equal(ACCOUNT_CONNECTION_ROUTES.length, 12);
  for (const provider of ["github", "google"]) {
    assert.equal(ACCOUNT_CONNECTION_ROUTES.filter((route) => route.provider === provider).length, 6);
    assert.ok(ACCOUNT_CONNECTION_ROUTES.some((route) => (
      route.provider === provider
      && route.operation === "connection"
      && route.method === "GET"
    )));
  }
  const manifest = accountConnectionContractManifest();
  assert.deepEqual(manifest.providers.google.issuer_allowlist, [...GOOGLE_ACCOUNT_CONNECTION_ISSUERS]);
  assert.deepEqual(manifest.stable_error_codes, [...ACCOUNT_CONNECTION_ERROR_CODES]);
  assert.equal(manifest.routes.length, 12);
});

test("account connection public guard rejects normalized private reference aliases", () => {
  for (const field of ["tokenRef", "tokenrefid", "token-ref-id", "revocationOutboxId"]) {
    assert.throws(
      () => assertPublicAccountConnectionPayload({ metadata: { [field]: "private" } }),
      /must not include/i,
    );
  }
});

test("binding constructor validates tenant, project, account, and provider without credentials", () => {
  assert.deepEqual(createAccountConnectionBinding({
    tenantId: "tenant_1",
    projectId: "project_1",
    accountId: "account_1",
    provider: "GOOGLE",
  }), {
    tenant_id: "tenant_1",
    project_id: "project_1",
    account_id: "account_1",
    provider: "google",
  });
  assert.throws(
    () => createAccountConnectionBinding({
      tenantId: "tenant with spaces",
      projectId: "project_1",
      accountId: "account_1",
      provider: "google",
    }),
    (error) => error instanceof AccountConnectionError && error.code === "invalid_oauth_binding",
  );
});

test("recursive public payload guard rejects every Python forbidden key at arbitrary depth", () => {
  const forbidden = [
    "access_token",
    "authorization_code",
    "client_secret",
    "code_verifier",
    "id_token",
    "nonce",
    "refresh_token",
    "state",
    "provider_subject_sha256",
    "subject_digest",
    "identifier_sha256",
    "token",
    "token_ref",
  ];
  for (const key of forbidden) {
    assert.throws(
      () => assertPublicAccountConnectionPayload({ envelope: [{ nested: { [key]: "must-not-appear" } }] }),
      (error) => error instanceof AccountConnectionError && error.code === "invalid_oauth_callback",
      key,
    );
  }
  assert.doesNotThrow(() => assertPublicAccountConnectionPayload({
    state_sha256: digest,
    nonce_sha256: digest,
    access_token_ref_present: true,
  }));
});

test("Google authorize URL parser enforces official host, exact scopes, PKCE, state, nonce, and audience", () => {
  const accepted = validateGoogleAccountConnectionAuthorizeUrl(googleAuthorizeUrl(), {
    expectedAudience: "google-client",
  });
  assert.equal(accepted.hostname, "accounts.google.com");
  assert.throws(
    () => validateGoogleAccountConnectionAuthorizeUrl(googleAuthorizeUrl({ scope: "openid email profile drive" })),
    (error) => error.code === "invalid_oauth_scopes",
  );
  assert.throws(
    () => validateGoogleAccountConnectionAuthorizeUrl(googleAuthorizeUrl({ code_challenge_method: "plain" })),
    (error) => error.code === "invalid_oauth_callback",
  );
  assert.throws(
    () => validateGoogleAccountConnectionAuthorizeUrl(googleAuthorizeUrl({ nonce: "" })),
    (error) => error.code === "invalid_oauth_state",
  );
  assert.throws(
    () => validateGoogleAccountConnectionAuthorizeUrl(
      googleAuthorizeUrl({ client_id: "wrong-client" }),
      { expectedAudience: "google-client" },
    ),
    (error) => error.code === "oidc_audience_mismatch",
  );
  assert.throws(
    () => validateGoogleAccountConnectionAuthorizeUrl(
      googleAuthorizeUrl().replace("accounts.google.com", "attacker.invalid"),
    ),
    (error) => error.code === "invalid_oauth_callback",
  );
});

test("public start, connection, disconnect, and stable error DTO parsers match Python shapes", () => {
  const start = parseAccountConnectionStart({
    schema_version: "releasefoundry.account_connection.v1",
    provider: "google",
    authorize_url: googleAuthorizeUrl(),
    expires_at: "2026-07-10T06:05:00Z",
  }, {
    expectedProvider: "google",
    expectedGoogleAudience: "google-client",
  });
  assert.equal(start.provider, "google");
  assert.equal(new URL(start.authorize_url).hostname, "accounts.google.com");

  const connectionPayload = {
    provider: "google",
    account_id: "account_1",
    credential_id: "credential_google_1",
    provider_subject_present: true,
    provider_login: "person",
    email_present: true,
    email_verified: true,
    connected_at: connectedAt,
    disconnected_at: null,
  };
  const connection = parseAccountConnection(connectionPayload, { expectedProvider: "google" });
  assert.equal(connection.schema_version, "releasefoundry.account_connection.v1");
  assert.equal(connection.credential_id, "credential_google_1");
  assert.equal(connection.provider_subject_present, true);
  assert.equal("provider_subject_sha256" in connection, false);
  const disconnected = parseAccountConnectionDisconnect({
    provider: "google",
    disconnected: true,
    revocation_status: "revoked",
    connection: connectionPayload,
  }, { expectedProvider: "google" });
  assert.equal(disconnected.connection.provider, "google");
  assert.equal(disconnected.revocation_status, "revoked");
  assert.deepEqual(parseAccountConnectionError({
    error: {
      code: "oauth_provider_revoke_failed",
      message: "Provider revocation is pending",
      retryable: true,
      provider: "google",
      revocation_pending: true,
    },
  }), {
    code: "oauth_provider_revoke_failed",
    message: "Provider revocation is pending",
    retryable: true,
    provider: "google",
    revocation_pending: true,
  });
});

test("Google public OIDC contract accepts both canonical issuers and emits canonical failures", () => {
  for (const issuer of GOOGLE_ACCOUNT_CONNECTION_ISSUERS) {
    assert.deepEqual(validateGoogleOidcPublicContract({
      issuer,
      issuer_matches: true,
      audience_matches: true,
      nonce_required: true,
      nonce_matches: true,
      email_verified: true,
    }), {
      issuer,
      issuer_matches: true,
      audience_matches: true,
      nonce_required: true,
      nonce_matches: true,
      email_verified: true,
      raw_nonce_present: false,
      raw_token_present: false,
    });
  }
  assert.throws(
    () => validateGoogleOidcPublicContract({
      issuer: "https://issuer.invalid",
      issuer_matches: false,
      audience_matches: true,
      nonce_required: true,
      nonce_matches: true,
      email_verified: true,
    }),
    (error) => error.code === "oidc_issuer_mismatch",
  );
});

test("runtime Google claim verifier also accepts the issuer spelling used by Google ID tokens", () => {
  const nonce = "google-account-nonce";
  const result = verifyGoogleAccountConnectionClaims({
    issuer: "accounts.google.com",
    audience: "google-client",
    subject: "subject-1",
    accountBindingRef: "provider-ref:google/account/1",
    receivedNonce: nonce,
    expectedNonceSha256: hashGoogleAccountConnectionNonce(nonce),
    emailVerified: true,
    audienceAllowlist: ["google-client"],
  });
  assert.equal(result.accepted, true);
  assert.equal(result.issuer_matches, true);
});
