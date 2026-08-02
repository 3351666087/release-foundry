import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  ACCOUNT_CONNECTION_EXACT_SCOPES,
  ACCOUNT_CONNECTION_SCHEMA_VERSION,
  AccountConnectionError,
  AccountConnectionHttpClient,
  accountConnectionContractManifest,
  hashGoogleAccountConnectionNonce,
  normalizeAccountConnectionProvider,
  validateExactAccountConnectionScopes,
  verifyGoogleAccountConnectionClaims,
} from "../dist/account-connections.js";
import { runAccountConnectionCli } from "../dist/account-connections-cli.js";
import {
  OAuthReplayLedger,
  hashOAuthState,
  verifyCallbackState,
} from "../dist/oauth.js";
import * as publicApi from "../dist/index.js";

const baseUrl = "https://accounts-api.example.invalid";
const projectId = "project_account_connection";

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function assertSecretFree(value) {
  const serialized = JSON.stringify(value);
  for (const marker of ["client_secret", "access_token", "refresh_token", "id_token", "authorization_code"]) {
    assert.equal(serialized.includes(`raw-${marker}`), false);
  }
  assert.equal(serialized.includes("provider stack trace"), false);
}

test("provider-neutral contract fixes exact GitHub and Google scopes and OIDC controls", () => {
  const manifest = accountConnectionContractManifest();
  assert.equal(manifest.schema_version, ACCOUNT_CONNECTION_SCHEMA_VERSION);
  assert.deepEqual(manifest.providers.github.exact_scopes, ["read:user", "user:email"]);
  assert.deepEqual(manifest.providers.google.exact_scopes, ["openid", "email", "profile"]);
  assert.equal(manifest.providers.google.nonce_required, true);
  assert.equal(manifest.providers.google.issuer_validation, true);
  assert.equal(manifest.providers.google.audience_validation, true);
  assert.equal(manifest.providers.google.verified_email_required, true);
  assert.equal(manifest.disconnect_contract.revoke_provider_token_before_local_delete, true);
  assert.ok(manifest.callback_errors.includes("invalid_oauth_state"));
  assert.ok(manifest.callback_errors.includes("oauth_callback_replayed"));
  assert.ok(manifest.disconnect_errors.includes("provider_revoke_failed"));
  assert.equal(manifest.callback_errors.includes("provider_revoke_failed"), false);
  assert.deepEqual(validateExactAccountConnectionScopes("github", ["user:email", "read:user"]), ["read:user", "user:email"]);
  assert.deepEqual(validateExactAccountConnectionScopes("google", ["profile", "openid", "email"]), ["openid", "email", "profile"]);
  assert.throws(
    () => validateExactAccountConnectionScopes("google", ["openid", "email"]),
    (error) => error instanceof AccountConnectionError && error.code === "invalid_oauth_scopes",
  );
  assert.throws(
    () => validateExactAccountConnectionScopes("github", ["repo", "read:user", "user:email"]),
    (error) => error instanceof AccountConnectionError && error.code === "invalid_oauth_scopes",
  );
  assert.equal(normalizeAccountConnectionProvider("GITHUB"), "github");
  assert.equal(normalizeAccountConnectionProvider("google"), "google");
  assert.throws(
    () => normalizeAccountConnectionProvider("wechat"),
    (error) => error.code === "unsupported_oauth_provider",
  );
});

test("Google identity verifier requires exact issuer audience nonce and verified email", () => {
  const nonce = "google-account-connection-nonce-20260710";
  const accepted = verifyGoogleAccountConnectionClaims({
    issuer: "https://accounts.google.com",
    audience: ["secondary-audience", "google-client-id"],
    subject: "google-subject-123",
    accountBindingRef: "provider-ref:google/account/123",
    expectedAccountBindingRef: "provider-ref:google/account/123",
    receivedNonce: nonce,
    expectedNonceSha256: hashGoogleAccountConnectionNonce(nonce),
    emailVerified: true,
    audienceAllowlist: ["google-client-id"],
  });
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.issuer_matches, true);
  assert.equal(accepted.audience_matches, true);
  assert.equal(accepted.nonce_matches, true);
  assert.equal(accepted.email_verified, true);
  assert.equal(accepted.raw_subject_present, false);
  assert.equal(accepted.raw_nonce_present, false);

  const cases = [
    {
      field: "issuer",
      value: "https://issuer.attacker.invalid",
      code: "issuer_mismatch",
    },
    {
      field: "audience",
      value: "attacker-client-id",
      code: "audience_mismatch",
    },
    {
      field: "receivedNonce",
      value: "wrong-google-account-connection-nonce",
      code: "nonce_mismatch",
    },
    {
      field: "emailVerified",
      value: false,
      code: "email_unverified",
    },
  ];
  for (const item of cases) {
    const options = {
      issuer: "https://accounts.google.com",
      audience: "google-client-id",
      subject: "google-subject-123",
      accountBindingRef: "provider-ref:google/account/123",
      expectedAccountBindingRef: "provider-ref:google/account/123",
      receivedNonce: nonce,
      expectedNonceSha256: hashGoogleAccountConnectionNonce(nonce),
      emailVerified: true,
      audienceAllowlist: ["google-client-id"],
      [item.field]: item.value,
    };
    assert.throws(
      () => verifyGoogleAccountConnectionClaims(options),
      (error) => {
        assert.equal(error.code, item.code);
        assertSecretFree(error.toJSON());
        return true;
      },
    );
  }
  assert.throws(
    () => verifyGoogleAccountConnectionClaims({
      issuer: "https://accounts.google.com",
      audience: "google-client-id",
      subject: "google-subject-123",
      accountBindingRef: "provider-ref:google/account/123",
      receivedNonce: nonce,
      expectedNonceSha256: hashGoogleAccountConnectionNonce(nonce),
      emailVerified: true,
      audienceAllowlist: [],
    }),
    (error) => error.code === "google_audience_required",
  );
});

test("invalid callback state and provider errors do not consume the replay ledger", () => {
  const ledger = new OAuthReplayLedger();
  const state = "valid-state-that-is-never-logged";
  const expectedStateSha256 = hashOAuthState(state).state_sha256;
  const common = {
    expectedStateSha256,
    authorizationCodeRef: "vault:oauth/google/codes/attempt-1",
    replayKey: "google-callback-event-0001",
    replayLedger: ledger,
    provider: "google",
    environment: "sandbox",
  };
  const invalid = verifyCallbackState({ ...common, receivedState: "wrong-state" });
  const providerError = verifyCallbackState({
    ...common,
    receivedState: state,
    errorCode: "access_denied",
  });
  assert.equal(invalid.accepted, false);
  assert.deepEqual(invalid.failure_reasons, ["state_mismatch"]);
  assert.equal(providerError.accepted, false);
  assert.deepEqual(providerError.failure_reasons, ["provider_error"]);
  assert.deepEqual(ledger.publicSnapshot(), {
    consumed_digest_count: 0,
    raw_replay_keys_present: false,
  });
  const accepted = verifyCallbackState({ ...common, receivedState: state });
  const replay = verifyCallbackState({ ...common, receivedState: state });
  assert.equal(accepted.accepted, true);
  assert.deepEqual(replay.failure_reasons, ["callback_replay"]);
  assert.equal(ledger.publicSnapshot().consumed_digest_count, 1);
});

test("HTTP client emits provider-neutral GitHub and Google routes with exact scopes", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    const parsed = new URL(String(url));
    const provider = parsed.pathname.includes("/google/") ? "google" : "github";
    if (parsed.pathname.endsWith("/start")) {
      return jsonResponse({ operation: "oauth_account_connection_start", provider }, 201);
    }
    if (parsed.pathname.endsWith("/callback")) {
      return jsonResponse({ operation: "oauth_account_connection_callback", provider, accepted: true });
    }
    if (parsed.pathname.endsWith("/disconnect")) {
      return jsonResponse({ operation: "oauth_account_connection_disconnect", provider, disconnected: true });
    }
    if (parsed.pathname.includes("/session/")) return jsonResponse({ provider, status: "active" });
    if (parsed.pathname.includes("/account/")) return jsonResponse({ provider, email_verified: true });
    throw new Error("unexpected request");
  };
  const client = new AccountConnectionHttpClient({
    baseUrl: `${baseUrl}/`,
    fetch: fetchImpl,
    headers: { "x-auth-ref": "session-ref-only" },
  });

  await client.start({
    provider: "github",
    projectId,
    tenantId: "tenant_local",
    accountId: "account_local",
    returnTo: "/settings/connections",
    allowSignup: false,
  });
  await client.start({
    provider: "google",
    projectId,
    loginHint: "person@example.invalid",
  });
  await client.callback({
    provider: "google",
    state: "opaque-google-state",
    code: "opaque-google-code",
  });
  await client.disconnect({
    provider: "github",
    projectId,
    sessionId: "github_session_1",
  });
  await client.session("google", "session:with.space");
  await client.identity("github", "session:with.space");

  assert.equal(new URL(calls[0].url).pathname, `/v1/projects/${projectId}/oauth/github/start`);
  assert.deepEqual(JSON.parse(calls[0].init.body).scopes, [...ACCOUNT_CONNECTION_EXACT_SCOPES.github]);
  assert.deepEqual(JSON.parse(calls[1].init.body).scopes, [...ACCOUNT_CONNECTION_EXACT_SCOPES.google]);
  assert.equal(new URL(calls[2].url).pathname, "/oauth/google/callback");
  assert.equal(new URL(calls[2].url).searchParams.get("state"), "opaque-google-state");
  assert.deepEqual(JSON.parse(calls[3].init.body), { session_id: "github_session_1" });
  assert.match(calls[4].url, /\/v1\/oauth\/google\/session\/session%3Awith\.space$/u);
  assert.match(calls[5].url, /\/v1\/oauth\/github\/account\/session%3Awith\.space$/u);
});

test("client normalizes callback replay, provider revoke, rate limit, timeout, and abort errors", async () => {
  const cases = [
    [409, { error: "invalid_oauth_state", detail: "provider stack trace raw-access_token" }, "invalid_oauth_state"],
    [409, { error: "oauth_callback_replayed" }, "oauth_callback_replayed"],
    [502, { error: "provider_revoke_failed", provider_body: "raw-client_secret" }, "provider_revoke_failed"],
    [429, { error: "anything-provider-specific" }, "oauth_request_failed"],
  ];
  for (const [status, payload, code] of cases) {
    const client = new AccountConnectionHttpClient({
      baseUrl,
      fetch: async () => jsonResponse(payload, status),
    });
    await assert.rejects(
      client.disconnect({ provider: "google", projectId, sessionId: "session_1" }),
      (error) => {
        assert.equal(error.code, code);
        assert.equal(error.status, status);
        assertSecretFree(error.toJSON());
        return true;
      },
    );
  }

  const timeoutClient = new AccountConnectionHttpClient({
    baseUrl,
    timeoutMs: 5,
    fetch: async (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("raw-refresh_token")), { once: true });
    }),
  });
  await assert.rejects(
    timeoutClient.session("google", "session_timeout"),
    (error) => error.code === "http_request_timeout" && error.retryable === true,
  );

  const controller = new AbortController();
  controller.abort();
  const abortedClient = new AccountConnectionHttpClient({
    baseUrl,
    signal: controller.signal,
    fetch: async () => {
      throw new Error("raw-id_token");
    },
  });
  await assert.rejects(
    abortedClient.session("github", "session_aborted"),
    (error) => error.code === "http_request_aborted",
  );
});

test("provider-neutral CLI exposes only hosted safe operations", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    const parsed = new URL(String(url));
    if (parsed.pathname.endsWith("/start")) return jsonResponse({ operation: "oauth_account_connection_start" }, 201);
    if (parsed.pathname.endsWith("/connection")) return jsonResponse({ provider: "google", account_id: "account_cli" });
    if (parsed.pathname.endsWith("/disconnect")) return jsonResponse({ operation: "oauth_account_connection_disconnect" });
    if (parsed.pathname.includes("/session/")) return jsonResponse({ status: "active" });
    if (parsed.pathname.includes("/account/")) return jsonResponse({ email_verified: true });
    throw new Error("unexpected request");
  };

  const help = await runAccountConnectionCli(["help"]);
  assert.match(help.usage, /callbacks are browser-only/u);
  const contract = await runAccountConnectionCli(["contract"]);
  assert.equal(contract.schema_version, ACCOUNT_CONNECTION_SCHEMA_VERSION);
  assert.equal(calls.length, 0);

  await runAccountConnectionCli([
    "start",
    "--base-url", baseUrl,
    "--provider", "google",
    "--project-id", projectId,
    "--login-hint", "person@example.invalid",
  ], { fetch: fetchImpl });
  await runAccountConnectionCli([
    "connection",
    "--base-url", baseUrl,
    "--provider", "google",
    "--project-id", projectId,
    "--tenant-id", "tenant_cli",
    "--account-id", "account_cli",
  ], { fetch: fetchImpl });
  await runAccountConnectionCli([
    "disconnect",
    "--base-url", baseUrl,
    "--provider", "github",
    "--project-id", projectId,
    "--tenant-id", "tenant_cli",
    "--account-id", "account_cli",
  ], { fetch: fetchImpl });

  assert.equal(new URL(calls[0].url).pathname, `/v1/projects/${projectId}/oauth/google/start`);
  assert.equal(new URL(calls[1].url).pathname, `/v1/projects/${projectId}/oauth/google/connection`);
  assert.equal(new URL(calls[2].url).pathname, `/v1/projects/${projectId}/oauth/github/disconnect`);
  await assert.rejects(
    runAccountConnectionCli(["start", "--base-url", baseUrl, "--project-id", projectId]),
    (error) => error.code === "oauth_request_rejected",
  );
  await assert.rejects(
    runAccountConnectionCli(["start", "--base-url", baseUrl, "--provider", "wechat", "--project-id", projectId], { fetch: fetchImpl }),
    (error) => error.code === "unsupported_oauth_provider",
  );
  for (const [command, flag] of [
    ["callback", "--code"],
    ["session", "--session-id"],
    ["identity", "--state"],
    ["disconnect", "--token"],
  ]) {
    await assert.rejects(
      runAccountConnectionCli([
        command,
        "--base-url", baseUrl,
        "--provider", "google",
        "--project-id", projectId,
        flag, "forbidden-value",
      ], { fetch: fetchImpl }),
      (error) => error.code === "oauth_request_rejected" && !JSON.stringify(error.toJSON()).includes("forbidden-value"),
    );
  }
});

test("HTTP client rejects forbidden fields in every successful public payload", async () => {
  for (const [forbiddenPayload, privateValue] of [
    [{ provider: "google", access_token: "raw-access-value" }, "raw-access-value"],
    [{ provider: "github", nested: { subject_digest: "raw-subject-value" } }, "raw-subject-value"],
    [{ provider: "google", connection: { email: "person@example.invalid" } }, "person@example.invalid"],
  ]) {
    const client = new AccountConnectionHttpClient({
      baseUrl,
      fetch: async () => jsonResponse(forbiddenPayload),
    });
    await assert.rejects(
      client.connection({
        provider: "google",
        projectId,
        tenantId: "tenant_local",
        accountId: "account_local",
      }),
      (error) => error.code === "invalid_oauth_callback"
        && !JSON.stringify(error.toJSON()).includes(privateValue),
    );
  }
});

test("package public entrypoint and bin publish provider-neutral account connections", async () => {
  assert.equal(publicApi.ACCOUNT_CONNECTION_SCHEMA_VERSION, ACCOUNT_CONNECTION_SCHEMA_VERSION);
  assert.equal(publicApi.AccountConnectionHttpClient, AccountConnectionHttpClient);
  assert.equal(publicApi.runAccountConnectionCli, runAccountConnectionCli);
  assert.equal(typeof publicApi.verifyCallbackIdentity, "function");
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(
    packageJson.bin["releasefoundry-account-connections"],
    "./dist/account-connections-cli.js",
  );
});
