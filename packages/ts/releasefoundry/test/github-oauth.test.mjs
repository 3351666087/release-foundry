import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  GITHUB_OAUTH_SCHEMA_VERSION,
  GitHubOAuthError,
  GitHubOAuthHttpClient,
  GitHubOAuthProviderError,
  GitHubOAuthRouter,
  GitHubOAuthRuntime,
  MemoryGitHubOAuthTokenStore,
  exportGitHubOAuthOpenApiSpec,
} from "../dist/github-oauth.js";
import { runGitHubOAuthCli } from "../dist/github-oauth-cli.js";
import * as publicApi from "../dist/index.js";

const clientId = "mock-github-client-id";
const clientSecret = "mock-github-client-secret";
const accessToken = "mock-github-access-token";
const authorizationCode = "mock-github-authorization-code";
const redirectUri = "https://app.releasefoundry.invalid/oauth/github/callback";
const projectId = "project-ts-oauth";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function noContent(status = 204) {
  return new Response(null, { status });
}

function makeRuntime({ fetchImpl, now = "2026-07-10T00:00:00.000Z", tokenStore, timeoutMs, signal } = {}) {
  let randomCall = 0;
  let idCall = 0;
  const secretPurposes = [];
  const store = tokenStore ?? new MemoryGitHubOAuthTokenStore();
  const runtime = new GitHubOAuthRuntime({
    config: {
      clientIdRef: "env:GITHUB_CLIENT_ID",
      clientSecretRef: "vault:oauth/github/client-secret",
      redirectUri,
      scopes: ["read:user", "user:email", "read:user"],
    },
    fetch: fetchImpl ?? (async () => {
      throw new Error("unexpected provider request");
    }),
    timeoutMs,
    signal,
    resolveSecret(reference, purpose) {
      secretPurposes.push({ reference, purpose });
      return purpose === "client_id" ? clientId : clientSecret;
    },
    tokenStore: store,
    randomBytes(size) {
      randomCall += 1;
      return new Uint8Array(size).fill(randomCall);
    },
    now: typeof now === "function" ? now : () => now,
    idFactory(prefix) {
      idCall += 1;
      return `${prefix}_test_${idCall}`;
    },
  });
  return { runtime, store, secretPurposes };
}

function secretFree(value, secrets = [clientSecret, accessToken, authorizationCode]) {
  const text = JSON.stringify(value);
  for (const secret of secrets) assert.equal(text.includes(secret), false, `public value leaked ${secret}`);
  return text;
}

async function start(runtime, options = {}) {
  const result = await runtime.start({ projectId, ...options });
  const url = new URL(result.authorization_url);
  return { result, url, state: url.searchParams.get("state") };
}

function successfulProviderFetch(calls) {
  return async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith("/login/oauth/access_token")) {
      return jsonResponse({
        access_token: accessToken,
        token_type: "bearer",
        scope: "read:user,user:email",
      });
    }
    if (String(url).endsWith("/user")) {
      return jsonResponse({
        id: 4242,
        login: "octo-test",
        name: "Octo Test",
        email: "octo@example.invalid",
        avatar_url: "https://avatars.example.invalid/4242",
        html_url: "https://github.com/octo-test",
      });
    }
    if (String(url).includes("/applications/")) return noContent();
    throw new Error(`unexpected mocked URL: ${url}`);
  };
}

test("start creates a state-bound S256 authorization contract without resolving a client secret", async () => {
  const { runtime, secretPurposes } = makeRuntime();
  const { result, url, state } = await start(runtime, {
    returnTo: "/settings/integrations?linked=github",
    login: "octo-test",
    allowSignup: false,
  });

  assert.equal(url.origin, "https://github.com");
  assert.equal(url.pathname, "/login/oauth/authorize");
  assert.equal(url.searchParams.get("client_id"), clientId);
  assert.equal(url.searchParams.get("redirect_uri"), redirectUri);
  assert.equal(url.searchParams.get("scope"), "read:user user:email");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.equal(url.searchParams.get("login"), "octo-test");
  assert.equal(url.searchParams.get("allow_signup"), "false");
  assert.equal(result.state_sha256, createHash("sha256").update(state).digest("hex"));
  assert.equal(result.code_challenge, url.searchParams.get("code_challenge"));
  assert.equal(result.network_io_performed, false);
  assert.equal(result.project_id, projectId);
  assert.deepEqual(secretPurposes, [{ reference: "env:GITHUB_CLIENT_ID", purpose: "client_id" }]);
  assert.equal(runtime.flow(result.flow_id).code_verifier_present, false);
  secretFree([result, runtime.publicSnapshot()], [clientSecret]);
});

test("start rejects open redirects and invalid endpoint or secret-reference configuration", async () => {
  const { runtime } = makeRuntime();
  await assert.rejects(runtime.start({ projectId, returnTo: "https://evil.invalid/steal" }), (error) => {
    assert.equal(error.code, "invalid_return_to");
    return true;
  });
  await assert.rejects(runtime.start({ projectId, returnTo: "//evil.invalid/steal" }), GitHubOAuthError);
  assert.throws(() => new GitHubOAuthRuntime({
    config: {
      clientIdRef: "literal-client-id",
      clientSecretRef: "literal-client-secret",
      redirectUri,
      tokenEndpoint: "http://github.example.invalid/token",
    },
    resolveSecret: () => "unused",
    tokenStore: new MemoryGitHubOAuthTokenStore(),
  }));
});

test("callback exchanges transient material, stores only a token reference, and rejects replay", async () => {
  const calls = [];
  const { runtime, store } = makeRuntime({ fetchImpl: successfulProviderFetch(calls) });
  const { result: begun, state } = await start(runtime);
  const completed = await runtime.callback({ state, code: authorizationCode });

  assert.equal(calls.length, 2);
  const tokenBody = new URLSearchParams(String(calls[0].init.body));
  assert.equal(tokenBody.get("client_id"), clientId);
  assert.equal(tokenBody.get("client_secret"), clientSecret);
  assert.equal(tokenBody.get("code"), authorizationCode);
  assert.equal(tokenBody.get("redirect_uri"), redirectUri);
  assert.ok(tokenBody.get("code_verifier").length >= 43);
  assert.equal(calls[1].init.headers.authorization, `Bearer ${accessToken}`);
  assert.equal(completed.session.status, "active");
  assert.equal(completed.session.project_id, projectId);
  assert.equal(completed.session.access_token_ref_present, true);
  assert.equal("access_token_ref" in completed.session, false);
  assert.equal(completed.account.github_user_id, 4242);
  assert.equal(completed.account.subject_ref, "provider-ref:github/user/4242");
  assert.deepEqual(store.publicSnapshot(), { token_reference_count: 1, token_values_present: false });
  secretFree([completed, runtime.publicSnapshot()]);

  await assert.rejects(
    runtime.callback({ state, code: authorizationCode }),
    (error) => error.code === "callback_replay" && error.status === 409,
  );
  assert.equal(calls.length, 2);
});

test("state mismatch performs no provider I/O and leaves the valid callback retryable", async () => {
  const calls = [];
  const { runtime } = makeRuntime({ fetchImpl: successfulProviderFetch(calls) });
  const { result: begun, state } = await start(runtime);

  await assert.rejects(
    runtime.callback({ state: "wrong-state", code: authorizationCode }),
    (error) => error.code === "state_mismatch",
  );
  assert.equal(calls.length, 0);
  assert.equal(runtime.flow(begun.flow_id).status, "pending");

  const completed = await runtime.callback({ state, code: authorizationCode });
  assert.equal(completed.accepted, true);
  assert.equal(calls.length, 2);
});

test("expired callbacks and provider authorization errors are consumed without provider I/O or raw descriptions", async () => {
  let currentTime = "2026-07-10T00:00:00.000Z";
  const calls = [];
  const { runtime } = makeRuntime({
    now: () => currentTime,
    fetchImpl: async (...args) => {
      calls.push(args);
      throw new Error("must not run");
    },
  });
  const expired = await start(runtime);
  currentTime = "2026-07-10T00:11:00.000Z";
  await assert.rejects(
    runtime.callback({ state: expired.state, code: authorizationCode }),
    (error) => error.code === "flow_expired" && error.status === 410,
  );
  assert.equal(calls.length, 0);

  currentTime = "2026-07-10T00:12:00.000Z";
  const denied = await start(runtime);
  const providerDescription = "denied with mock-github-client-secret and mock-github-access-token";
  await assert.rejects(
    runtime.callback({
      state: denied.state,
      error: `unknown-${providerDescription}`,
      errorDescription: providerDescription,
    }),
    (error) => {
      assert.ok(error instanceof GitHubOAuthProviderError);
      assert.equal(error.code, "provider_authorization_failed");
      secretFree(error.toJSON());
      return true;
    },
  );
  assert.equal(calls.length, 0);
});

test("provider token errors, malformed payloads, oversized payloads, and network failures are redacted", async () => {
  const scenarios = [
    {
      name: "provider JSON error",
      fetchImpl: async () => jsonResponse({
        error: "bad_verification_code",
        error_description: `contains ${clientSecret} ${accessToken}`,
      }, 400),
      code: "bad_verification_code",
    },
    {
      name: "malformed provider response",
      fetchImpl: async () => new Response(`not-json ${clientSecret}`, { status: 502 }),
      code: "invalid_provider_response",
    },
    {
      name: "oversized provider response",
      fetchImpl: async () => new Response("x".repeat(1_000_001), { status: 502 }),
      code: "provider_response_too_large",
    },
    {
      name: "provider network failure",
      fetchImpl: async () => {
        throw new Error(`network ${clientSecret} ${accessToken}`);
      },
      code: "token_exchange_failed",
    },
    {
      name: "missing token value",
      fetchImpl: async () => jsonResponse({ token_type: "bearer" }),
      code: "invalid_token_response",
    },
  ];

  for (const scenario of scenarios) {
    const { runtime } = makeRuntime({ fetchImpl: scenario.fetchImpl });
    const begun = await start(runtime);
    await assert.rejects(
      runtime.callback({ state: begun.state, code: authorizationCode }),
      (error) => {
        assert.equal(error.code, scenario.code, scenario.name);
        secretFree(error.toJSON());
        assert.equal(error.toJSON().provider_response_included, false);
        return true;
      },
    );
  }
});

test("token exchange rejects missing or unsupported token types and scope escalation before storage", async () => {
  const scenarios = [
    { token_type: undefined, scope: "read:user,user:email", code: "unsupported_token_type" },
    { token_type: "mac", scope: "read:user,user:email", code: "unsupported_token_type" },
    { token_type: "Bearer", scope: "read:user,user:email,repo", code: "scope_escalation" },
  ];
  for (const scenario of scenarios) {
    const store = new MemoryGitHubOAuthTokenStore();
    const { runtime } = makeRuntime({
      tokenStore: store,
      fetchImpl: async () => jsonResponse({
        access_token: accessToken,
        token_type: scenario.token_type,
        scope: scenario.scope,
      }),
    });
    const begun = await start(runtime);
    await assert.rejects(
      runtime.callback({ state: begun.state, code: authorizationCode }),
      (error) => {
        assert.ok(error instanceof GitHubOAuthProviderError);
        assert.equal(error.code, scenario.code);
        assert.equal(error.retryable, false);
        secretFree(error.toJSON());
        return true;
      },
    );
    assert.deepEqual(store.publicSnapshot(), { token_reference_count: 0, token_values_present: false });
  }
});

test("account lookup uses only the verified primary email and skips email lookup when /user already supplies one", async () => {
  const emailCalls = [];
  const { runtime } = makeRuntime({
    fetchImpl: async (url) => {
      emailCalls.push(String(url));
      if (String(url).endsWith("/login/oauth/access_token")) {
        return jsonResponse({ access_token: accessToken, token_type: "bearer", scope: "read:user,user:email" });
      }
      if (String(url).endsWith("/user")) {
        return jsonResponse({ id: 4242, login: "octo-test", email: null });
      }
      if (String(url).endsWith("/user/emails")) {
        return jsonResponse([
          { email: "unverified@example.invalid", primary: true, verified: false },
          { email: "secondary@example.invalid", primary: false, verified: true },
          { email: "primary@example.invalid", primary: true, verified: true },
        ]);
      }
      throw new Error("unexpected mocked URL");
    },
  });
  const begun = await start(runtime);
  const completed = await runtime.callback({ state: begun.state, code: authorizationCode });
  assert.equal(completed.account.email, "primary@example.invalid");
  assert.equal(emailCalls.filter((url) => url.endsWith("/user/emails")).length, 1);

  const directCalls = [];
  const { runtime: directRuntime } = makeRuntime({
    fetchImpl: async (url) => {
      directCalls.push(String(url));
      if (String(url).endsWith("/login/oauth/access_token")) {
        return jsonResponse({ access_token: accessToken, token_type: "bearer", scope: "read:user,user:email" });
      }
      if (String(url).endsWith("/user")) {
        return jsonResponse({ id: 4243, login: "octo-direct", email: "direct@example.invalid" });
      }
      throw new Error("unexpected mocked URL");
    },
  });
  const directBegun = await start(directRuntime);
  const directCompleted = await directRuntime.callback({ state: directBegun.state, code: authorizationCode });
  assert.equal(directCompleted.account.email, "direct@example.invalid");
  assert.equal(directCalls.some((url) => url.endsWith("/user/emails")), false);
});

test("provider requests honor timeout and caller AbortSignal with redacted errors", async () => {
  const waitForAbort = async (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(new Error(`${clientSecret} ${accessToken}`)), { once: true });
  });
  const timed = makeRuntime({ fetchImpl: waitForAbort, timeoutMs: 5 });
  const timedBegun = await start(timed.runtime);
  await assert.rejects(
    timed.runtime.callback({ state: timedBegun.state, code: authorizationCode }),
    (error) => {
      assert.equal(error.code, "provider_request_timeout");
      assert.equal(error.retryable, true);
      secretFree(error.toJSON());
      return true;
    },
  );

  const controller = new AbortController();
  controller.abort();
  const aborted = makeRuntime({ fetchImpl: waitForAbort, signal: controller.signal });
  const abortedBegun = await start(aborted.runtime);
  await assert.rejects(
    aborted.runtime.callback({ state: abortedBegun.state, code: authorizationCode }),
    (error) => {
      assert.equal(error.code, "provider_request_aborted");
      assert.equal(error.retryable, false);
      secretFree(error.toJSON());
      return true;
    },
  );
});

test("token exchange failure consumes the callback and requires a new authorization flow", async () => {
  let providerCalls = 0;
  const { runtime } = makeRuntime({
    fetchImpl: async () => {
      providerCalls += 1;
      throw new Error(`ambiguous network failure ${clientSecret} ${authorizationCode}`);
    },
  });
  const begun = await start(runtime);

  await assert.rejects(
    runtime.callback({
      state: begun.state,
      code: authorizationCode,
    }),
    (error) => {
      assert.equal(error.code, "token_exchange_failed");
      secretFree(error.toJSON());
      return true;
    },
  );

  assert.equal(runtime.flow(begun.result.flow_id).status, "failed");
  assert.equal(runtime.flow(begun.result.flow_id).code_verifier_present, false);

  await assert.rejects(
    runtime.callback({
      state: begun.state,
      code: authorizationCode,
    }),
    (error) => error.code === "callback_replay" && error.status === 409,
  );

  assert.equal(providerCalls, 1);
});

test("session/account reads and disconnect revoke remotely then clear the local token reference idempotently", async () => {
  const calls = [];
  const { runtime, store } = makeRuntime({ fetchImpl: successfulProviderFetch(calls) });
  const begun = await start(runtime);
  const completed = await runtime.callback({ state: begun.state, code: authorizationCode });
  const sessionId = completed.session.session_id;

  assert.equal(runtime.session(sessionId).status, "active");
  assert.equal(runtime.account(sessionId).login, "octo-test");
  const disconnected = await runtime.disconnect(projectId, sessionId);
  assert.equal(disconnected.already_disconnected, false);
  assert.equal(disconnected.provider_revocation_attempted, true);
  assert.equal(disconnected.session.status, "revoked");
  assert.equal(disconnected.session.access_token_ref_present, false);
  assert.equal("access_token_ref" in disconnected.session, false);
  assert.deepEqual(store.publicSnapshot(), { token_reference_count: 0, token_values_present: false });

  const revoke = calls[2];
  assert.match(revoke.url, /\/applications\/mock-github-client-id\/token$/u);
  assert.equal(revoke.init.method, "DELETE");
  assert.equal(revoke.init.headers.authorization, `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString("base64")}`);
  assert.deepEqual(JSON.parse(revoke.init.body), { access_token: accessToken });
  secretFree(disconnected);
  assert.throws(() => runtime.account(sessionId), (error) => error.code === "session_revoked");

  const again = await runtime.disconnect(projectId, sessionId);
  assert.equal(again.already_disconnected, true);
  assert.equal(again.provider_revocation_attempted, false);
  assert.equal(calls.length, 3);
});

test("failed provider revocation preserves the active session and token reference", async () => {
  const calls = [];
  const provider = successfulProviderFetch(calls);
  const { runtime, store } = makeRuntime({
    fetchImpl: async (url, init) => {
      if (String(url).includes("/applications/")) {
        calls.push({ url: String(url), init });
        return jsonResponse({ message: `do not expose ${clientSecret} ${accessToken}` }, 500);
      }
      return provider(url, init);
    },
  });
  const begun = await start(runtime);
  const completed = await runtime.callback({ state: begun.state, code: authorizationCode });

  await assert.rejects(runtime.disconnect(projectId, completed.session.session_id), (error) => {
    assert.equal(error.code, "provider_revoke_failed");
    secretFree(error.toJSON());
    return true;
  });
  assert.equal(runtime.session(completed.session.session_id).status, "active");
  assert.equal(runtime.session(completed.session.session_id).access_token_ref_present, true);
  assert.equal("access_token_ref" in runtime.session(completed.session.session_id), false);
  assert.deepEqual(store.publicSnapshot(), { token_reference_count: 1, token_values_present: false });
});

test("router exposes canonical project routes, only the callback query path, and uniform safe errors", async () => {
  const calls = [];
  const { runtime } = makeRuntime({ fetchImpl: successfulProviderFetch(calls) });
  const router = new GitHubOAuthRouter(runtime);
  const openapiRoot = await router.handle("GET", "/openapi.json");
  const openapiV1 = await router.handle("GET", "/v1/openapi.json");
  assert.equal(openapiRoot.status_code, 200);
  assert.deepEqual(openapiV1.body, openapiRoot.body);

  const begun = await router.handle("POST", `/v1/projects/${projectId}/oauth/github/start`, {
    return_to: "/integrations",
    allow_signup: false,
  });
  assert.equal(begun.status_code, 201);
  assert.equal(begun.body.project_id, projectId);
  const begunGet = await router.handle("GET", `/v1/projects/${projectId}/oauth/github/start?return_to=%2Fintegrations`);
  assert.equal(begunGet.status_code, 201);
  const state = new URL(begun.body.authorization_url).searchParams.get("state");
  const query = new URLSearchParams({
    state,
    code: authorizationCode,
  });
  const completed = await router.handle("GET", `/oauth/github/callback?${query}`);
  assert.equal(completed.status_code, 200);
  assert.equal("access_token_ref" in completed.body.session, false);
  secretFree(completed.body);

  const removedCallbackAlias = await router.handle("GET", `/v1/oauth/github/callback?${query}`);
  assert.equal(removedCallbackAlias.status_code, 404);
  const removedCallbackPost = await router.handle("POST", "/oauth/github/callback", { state, code: authorizationCode });
  assert.equal(removedCallbackPost.status_code, 404);

  const replay = await router.handle("GET", `/oauth/github/callback?${query}`);
  assert.equal(replay.status_code, 409);
  assert.deepEqual(
    {
      provider_response_included: replay.body.provider_response_included,
      secret_value_present: replay.body.secret_value_present,
      token_value_present: replay.body.token_value_present,
    },
    {
      provider_response_included: false,
      secret_value_present: false,
      token_value_present: false,
    },
  );
  secretFree(replay.body);

  const wrongProject = await router.handle("POST", "/v1/projects/other-project/oauth/github/disconnect", {
    session_id: completed.body.session.session_id,
  });
  assert.equal(wrongProject.status_code, 404);
  const disconnected = await router.handle("DELETE", `/v1/projects/${projectId}/oauth/github/disconnect`, {
    session_id: completed.body.session.session_id,
  });
  assert.equal(disconnected.status_code, 200);
  assert.equal(disconnected.body.session.access_token_ref_present, false);

  const secondState = new URL(begunGet.body.authorization_url).searchParams.get("state");
  const secondQuery = new URLSearchParams({ state: secondState, code: authorizationCode });
  const secondCompleted = await router.handle("GET", `/oauth/github/callback?${secondQuery}`);
  const disconnectedPost = await router.handle("POST", `/v1/projects/${projectId}/oauth/github/disconnect`, {
    session_id: secondCompleted.body.session.session_id,
  });
  assert.equal(disconnectedPost.status_code, 200);

  const missing = await router.handle("GET", "/v1/oauth/github/session/not-found");
  assert.equal(missing.status_code, 404);
  assert.equal(missing.body.error, "session_not_found");
  secretFree(missing.body);
});

test("HTTP client sends canonical project-scoped contracts, callback query values, and redacts remote errors", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    const pathname = new URL(String(url)).pathname;
    if (pathname.endsWith("/start")) return jsonResponse({ operation: "github_oauth_start" }, 201);
    if (pathname.endsWith("/callback")) return jsonResponse({ operation: "github_oauth_callback" });
    if (pathname.endsWith("/disconnect")) return jsonResponse({ operation: "github_oauth_disconnect" });
    if (pathname.includes("/session/")) return jsonResponse({ status: "active" });
    if (pathname.includes("/account/")) return jsonResponse({ login: "octo-test" });
    if (pathname.endsWith("/openapi.json")) return jsonResponse({ openapi: "3.0.3" });
    return jsonResponse({
      error: "remote_error",
      message: `remote leaked ${clientSecret} ${accessToken}`,
    }, 502);
  };
  const client = new GitHubOAuthHttpClient({
    baseUrl: "https://oauth-api.example.invalid/",
    fetch: fetchImpl,
    headers: { "x-test-auth": "reference-only" },
  });

  await client.start(projectId, { returnTo: "/settings", login: "octo", allowSignup: false });
  await client.callback({
    state: "state",
    code: authorizationCode,
    errorDescription: "ignored",
  });
  await client.disconnect(projectId, "github_session_1");
  await client.session("session/with space");
  await client.account("session/with space");
  await client.openApi();

  assert.deepEqual(JSON.parse(calls[0].init.body), {
    return_to: "/settings",
    login: "octo",
    allow_signup: false,
  });
  assert.equal(calls[0].url.includes(`/v1/projects/${projectId}/oauth/github/start`), true);
  assert.equal(calls[1].init.method, "GET");
  assert.equal(calls[1].init.body, undefined);
  const callbackUrl = new URL(calls[1].url);
  assert.equal(callbackUrl.pathname, "/oauth/github/callback");
  assert.equal(callbackUrl.searchParams.get("state"), "state");
  assert.equal(callbackUrl.searchParams.get("code"), authorizationCode);
  assert.equal(callbackUrl.searchParams.get("error_description"), "ignored");
  assert.deepEqual(JSON.parse(calls[2].init.body), { session_id: "github_session_1" });
  assert.equal(calls[2].url.includes(`/v1/projects/${projectId}/oauth/github/disconnect`), true);
  assert.match(calls[3].url, /session\/session%2Fwith%20space$/u);
  assert.match(calls[4].url, /account\/session%2Fwith%20space$/u);
  assert.match(calls[5].url, /\/openapi\.json$/u);

  const failing = new GitHubOAuthHttpClient({
    baseUrl: "https://oauth-api.example.invalid",
    fetch: async () => jsonResponse({
      error: `remote-${clientSecret}`,
      message: `remote leaked ${accessToken}`,
    }, 502),
  });
  await assert.rejects(failing.session("missing"), (error) => {
    assert.equal(error.message, "GitHub OAuth HTTP request failed");
    secretFree(error.toJSON());
    return true;
  });
});

test("HTTP client timeout and caller abort are safe and forward an AbortSignal", async () => {
  let observedSignal;
  const client = new GitHubOAuthHttpClient({
    baseUrl: "https://oauth-api.example.invalid",
    timeoutMs: 5,
    fetch: async (_url, init) => new Promise((_resolve, reject) => {
      observedSignal = init.signal;
      init.signal.addEventListener("abort", () => reject(new Error(`leak ${clientSecret}`)), { once: true });
    }),
  });
  await assert.rejects(client.openApi(), (error) => {
    assert.equal(error.code, "http_request_timeout");
    secretFree(error.toJSON());
    return true;
  });
  assert.ok(observedSignal instanceof AbortSignal);
  assert.equal(observedSignal.aborted, true);

  const controller = new AbortController();
  controller.abort();
  const aborted = new GitHubOAuthHttpClient({
    baseUrl: "https://oauth-api.example.invalid",
    signal: controller.signal,
    fetch: async (_url, init) => {
      assert.equal(init.signal.aborted, true);
      throw new Error(`leak ${accessToken}`);
    },
  });
  await assert.rejects(aborted.openApi(), (error) => {
    assert.equal(error.code, "http_request_aborted");
    secretFree(error.toJSON());
    return true;
  });
});

test("OpenAPI documents canonical runtime paths, both discovery aliases, and safe response contracts", () => {
  const spec = exportGitHubOAuthOpenApiSpec();
  const paths = spec.paths;
  assert.ok(paths["/openapi.json"]);
  assert.ok(paths["/v1/openapi.json"]);
  assert.ok(paths["/v1/projects/{project_id}/oauth/github/start"].get);
  assert.ok(paths["/v1/projects/{project_id}/oauth/github/start"].post);
  assert.ok(paths["/oauth/github/callback"].get);
  assert.equal(paths["/oauth/github/callback"].post, undefined);
  assert.equal(paths["/v1/oauth/github/callback"], undefined);
  assert.ok(paths["/v1/projects/{project_id}/oauth/github/disconnect"].post);
  assert.ok(paths["/v1/projects/{project_id}/oauth/github/disconnect"].delete);
  assert.ok(paths["/v1/oauth/github/session/{session_id}"]);
  assert.ok(paths["/v1/oauth/github/account/{session_id}"]);
  assert.equal(spec["x-releasefoundry-runtime-contract"].pkce, "S256");
  assert.equal(spec["x-releasefoundry-runtime-contract"].token_refs_only, true);
  assert.equal(spec["x-releasefoundry-runtime-contract"].injectable_fetch, true);
  assert.equal(spec["x-releasefoundry-runtime-contract"].provider_errors_redacted, true);
  const safeError = spec.components.schemas.GitHubOAuthSafeError;
  assert.deepEqual(safeError.properties.secret_value_present.enum, [false]);
  assert.deepEqual(safeError.properties.token_value_present.enum, [false]);
  assert.deepEqual(safeError.properties.provider_response_included.enum, [false]);
  assert.equal(
    paths["/oauth/github/callback"].get.responses["400"].content["application/json"].schema.$ref,
    "#/components/schemas/GitHubOAuthSafeError",
  );
});

test("CLI is HTTP-only for runtime commands and never accepts OAuth secret options", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    const pathname = new URL(String(url)).pathname;
    if (pathname.endsWith("/start")) return jsonResponse({ operation: "github_oauth_start", token_value_present: false }, 201);
    if (pathname.endsWith("/callback")) return jsonResponse({ operation: "github_oauth_callback", token_value_present: false });
    if (pathname.endsWith("/disconnect")) return jsonResponse({ operation: "github_oauth_disconnect", token_value_present: false });
    throw new Error("unexpected CLI request");
  };
  const help = await runGitHubOAuthCli(["help"]);
  assert.match(help.usage, /never read OAuth secrets/u);
  assert.equal(help.usage.includes("client-secret"), false);
  const openapi = await runGitHubOAuthCli(["openapi"]);
  assert.equal(openapi.openapi, "3.0.3");
  assert.equal(calls.length, 0);

  const started = await runGitHubOAuthCli([
    "start",
    "--base-url", "https://oauth-api.example.invalid",
    "--project-id", projectId,
    "--return-to", "/settings",
    "--allow-signup", "false",
  ], { fetch: fetchImpl });
  assert.equal(started.operation, "github_oauth_start");
  assert.equal(calls[0].url.includes(`/v1/projects/${projectId}/oauth/github/start`), true);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    return_to: "/settings",
    allow_signup: false,
  });
  secretFree(started);

  const callback = await runGitHubOAuthCli([
    "callback",
    "--base-url", "https://oauth-api.example.invalid",
    "--state", "callback-state",
    "--code", authorizationCode,
  ], { fetch: fetchImpl });
  assert.equal(callback.operation, "github_oauth_callback");
  assert.equal(new URL(calls[1].url).pathname, "/oauth/github/callback");
  assert.equal(new URL(calls[1].url).searchParams.get("state"), "callback-state");

  const disconnected = await runGitHubOAuthCli([
    "disconnect",
    "--base-url", "https://oauth-api.example.invalid",
    "--project-id", projectId,
    "--session-id", "github_session_cli",
  ], { fetch: fetchImpl });
  assert.equal(disconnected.operation, "github_oauth_disconnect");
  assert.equal(calls[2].url.includes(`/v1/projects/${projectId}/oauth/github/disconnect`), true);

  await assert.rejects(runGitHubOAuthCli(["session"]), (error) => error.code === "missing_base-url");
  await assert.rejects(
    runGitHubOAuthCli(["start", "--base-url", "https://oauth-api.example.invalid"]),
    (error) => error.code === "missing_project-id",
  );
  await assert.rejects(
    runGitHubOAuthCli([
      "disconnect",
      "--base-url", "https://oauth-api.example.invalid",
      "--session-id", "github_session_cli",
    ]),
    (error) => error.code === "missing_project-id",
  );
  await assert.rejects(
    runGitHubOAuthCli(["unknown", "--base-url", "https://oauth-api.example.invalid"]),
    (error) => error.code === "unknown_command",
  );
});

test("public package entrypoint exports GitHub OAuth runtime, client, CLI, and schema version", () => {
  assert.equal(publicApi.GITHUB_OAUTH_SCHEMA_VERSION, GITHUB_OAUTH_SCHEMA_VERSION);
  assert.equal(publicApi.GitHubOAuthRuntime, GitHubOAuthRuntime);
  assert.equal(publicApi.GitHubOAuthHttpClient, GitHubOAuthHttpClient);
  assert.equal(publicApi.runGitHubOAuthCli, runGitHubOAuthCli);
});

test("package publishes the GitHub account-connection CLI bin", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.equal(
    packageJson.bin["releasefoundry-github-oauth"],
    "./dist/github-oauth-cli.js",
  );
});
