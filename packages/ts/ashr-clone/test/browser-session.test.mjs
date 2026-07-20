import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  BROWSER_SESSION_COOKIE_NAMES,
  BROWSER_SESSION_ERROR_CODES,
  BROWSER_SESSION_MODALITIES,
  BrowserHTTPResponse,
  BrowserSessionClient,
  BrowserSessionCookieJar,
  BrowserSessionError,
  browserSessionCapabilityManifest,
  browserSessionOpenApiDocument,
  buildBrowserCookieReplacement,
  secureBrowserSessionRefreshRoute,
} from "../dist/browser-session.js";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const repoRoot = fileURLToPath(new URL("../../../../", import.meta.url));
const parity = JSON.parse(readFileSync(new URL("../../../../tests/a1/fixtures/browser_session_sdk_parity.json", import.meta.url), "utf8"));
const openapiFixture = JSON.parse(readFileSync(new URL("../../../../tests/a1/fixtures/browser_session_openapi_3_1.json", import.meta.url), "utf8"));

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function fingerprint(value) {
  return createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("hex");
}

function cookie(name, value, maxAge, now = new Date()) {
  const expires = new Date(now.getTime() + maxAge * 1000).toUTCString();
  return `${name}=${value}; Path=/; Expires=${expires}; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`;
}

function clearCookie(name) {
  return `${name}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT; Max-Age=-1; HttpOnly; Secure; SameSite=Strict`;
}

function response(status, body, headers = []) {
  const resolvedHeaders = new Headers(headers);
  if (body !== undefined && !resolvedHeaders.has("content-type")) resolvedHeaders.set("content-type", "application/json");
  return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: resolvedHeaders });
}

function loginResponse(access = "synthetic-access-one", refresh = "synthetic-refresh-one") {
  const now = new Date();
  return response(200, {
    schema_version: "ashr.clone.unified_identity.v1",
    purpose: "login",
    credential_created: false,
  }, [
    ["cache-control", "no-store"],
    ["set-cookie", cookie(BROWSER_SESSION_COOKIE_NAMES[0], access, 1800, now)],
    ["set-cookie", cookie(BROWSER_SESSION_COOKIE_NAMES[1], refresh, 86400, now)],
  ]);
}

function scriptedFetch(...factories) {
  const calls = [];
  let index = 0;
  const fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const factory = factories[index++];
    assert.ok(factory, "unexpected fetch call");
    return typeof factory === "function" ? factory() : factory;
  };
  return { fetch, calls };
}

test("BrowserHTTPResponse preserves multi-value headers and immutable body snapshots", () => {
  const source = new Uint8Array([1, 2, 3]);
  const response = BrowserHTTPResponse.create(202, {
    headers: {
      "x-request-id": "request_round54",
      "set-cookie": ["a=one", "b=two"],
    },
    body: source,
  });
  source[0] = 9;
  assert.equal(response.status, 202);
  assert.deepEqual(response.headerValues("Set-Cookie"), ["a=one", "b=two"]);
  assert.deepEqual(response.header_values("X-Request-ID"), ["request_round54"]);
  assert.deepEqual([...response.body], [1, 2, 3]);
  assert.equal(Object.isFrozen(response), true);
  assert.equal(Object.isFrozen(response.headers), true);
});

test("BrowserHTTPResponse rejects malformed status and header injection", () => {
  assert.throws(
    () => BrowserHTTPResponse.create(99),
    (error) => error instanceof BrowserSessionError && error.code === "browser_session_response_invalid",
  );
  assert.throws(
    () => BrowserHTTPResponse.create(200, { headers: [["x-safe", "ok\r\nx-injected: yes"]] }),
    (error) => error instanceof BrowserSessionError && error.code === "browser_session_response_invalid",
  );
});

test("custom cookie caps and replay preserve expiry while Max-Age decreases", () => {
  const issuedAt = "2026-07-11T04:00:00Z";
  const replacement = buildBrowserCookieReplacement({
    issuedAt,
    accessExpiresAt: "2026-07-11T10:00:00Z",
    refreshExpiresAt: "2026-09-11T04:00:00Z",
    accessCapSeconds: 1800,
    refreshCapSeconds: 7 * 24 * 60 * 60,
  });
  const replay = replacement.replay("2026-07-11T04:00:37Z");
  assert.equal(replacement.access.maxAgeSeconds, 1800);
  assert.equal(replacement.refresh.maxAgeSeconds, 7 * 24 * 60 * 60);
  assert.equal(replay.access.expiresAt.toISOString(), replacement.access.expiresAt.toISOString());
  assert.equal(replay.refresh.expiresAt.toISOString(), replacement.refresh.expiresAt.toISOString());
  assert.equal(replay.access.maxAgeSeconds, 1763);
  assert.equal(replay.refresh.maxAgeSeconds, 7 * 24 * 60 * 60 - 37);
  assert.equal(replay.toJSON().contains_credential_values, false);
  assert.deepEqual(replay.toJSON().cookies.map((item) => item.name), [...BROWSER_SESSION_COOKIE_NAMES]);
});

test("cookie replay closes at expiry and caps reject invalid values", () => {
  const replacement = buildBrowserCookieReplacement({
    issuedAt: "2026-07-11T04:00:00Z",
    accessExpiresAt: "2026-07-11T04:10:00Z",
    refreshExpiresAt: "2026-07-11T05:00:00Z",
  });
  assert.throws(
    () => replacement.replay("2026-07-11T04:10:00Z"),
    (error) => error instanceof BrowserSessionError && error.code === "browser_session_cookie_expired",
  );
  assert.throws(
    () => buildBrowserCookieReplacement({
      issuedAt: "2026-07-11T04:00:00Z",
      accessExpiresAt: "2026-07-11T04:10:00Z",
      refreshExpiresAt: "2026-07-11T05:00:00Z",
      accessCapSeconds: 0,
    }),
    (error) => error instanceof BrowserSessionError && error.code === "browser_session_invalid_request",
  );
});

test("login establishes an origin-bound jar without public credential serialization", async () => {
  const access = "synthetic-access-private";
  const refresh = "synthetic-refresh-private";
  const proof = "synthetic-one-time-proof";
  const jar = new BrowserSessionCookieJar("https://sessions.example.test");
  const scripted = scriptedFetch(() => loginResponse(access, refresh));
  const client = new BrowserSessionClient({
    baseUrl: "https://sessions.example.test",
    fetch: scripted.fetch,
    cookieJar: jar,
  });
  const receipt = await client.completeLogin({
    tenantId: "tenant_main",
    accountId: "account_main",
    challengeId: "challenge_main",
    verificationCode: proof,
    channel: "email",
    identifier: "operator@example.test",
    displayName: "Operator",
  });

  const [{ url, init }] = scripted.calls;
  assert.equal(url, "https://sessions.example.test/v1/identity-verification/verify");
  assert.equal(init.method, "POST");
  assert.equal(init.credentials, "include");
  assert.equal(init.redirect, "manual");
  assert.equal(init.cache, "no-store");
  assert.equal(init.headers.get("origin"), "https://sessions.example.test");
  assert.equal(init.headers.get("sec-fetch-site"), "same-origin");
  assert.equal(init.headers.has("cookie"), false);
  assert.equal(JSON.parse(init.body).code, proof);
  assert.equal(receipt.status, "authenticated");
  assert.equal(receipt.cookieState.cookie_count, 2);

  const rendered = `${String(jar)} ${JSON.stringify(jar)} ${JSON.stringify(receipt)}`;
  assert.equal(rendered.includes(access), false);
  assert.equal(rendered.includes(refresh), false);
  assert.equal(rendered.includes(proof), false);
  assert.match(rendered, /credential_values_exposed(?:"|)=?(?::)?false/u);
});

test("cookie jar JSON protocol ignores stringify keys while snapshot accepts an explicit clock", () => {
  const jar = new BrowserSessionCookieJar("https://sessions.example.test");
  assert.doesNotThrow(() => JSON.stringify({ jar }));
  assert.deepEqual(jar.snapshot("2026-07-11T04:00:00Z"), jar.toJSON());
});

test("refresh uses Idempotency-Key, same-origin headers, cookies, and rotates atomically", async () => {
  const oldAccess = "synthetic-access-old";
  const oldRefresh = "synthetic-refresh-old";
  const newAccess = "synthetic-access-new";
  const newRefresh = "synthetic-refresh-new";
  const jar = new BrowserSessionCookieJar("https://sessions.example.test");
  const scripted = scriptedFetch(
    () => loginResponse(oldAccess, oldRefresh),
    () => {
      const now = new Date();
      return response(200, { schema_version: "ashr.identity_session_refresh.v1", status: "rotated" }, [
        ["set-cookie", cookie(BROWSER_SESSION_COOKIE_NAMES[0], newAccess, 900, now)],
        ["set-cookie", cookie(BROWSER_SESSION_COOKIE_NAMES[1], newRefresh, 7200, now)],
      ]);
    },
  );
  const client = new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: scripted.fetch, cookieJar: jar });
  await client.completeLogin({
    tenantId: "tenant_main", accountId: "account_main", challengeId: "challenge_main",
    verificationCode: "synthetic-proof", channel: "phone", identifier: "13800000000",
  });
  const receipt = await client.refresh({ projectId: "project_main", accountId: "account_main", idempotencyKey: "refresh_round54_0001" });
  const call = scripted.calls[1];
  assert.equal(call.url, "https://sessions.example.test/v1/projects/project_main/accounts/account_main/browser-sessions/refresh");
  assert.equal(call.init.headers.get("idempotency-key"), "refresh_round54_0001");
  assert.match(call.init.headers.get("cookie"), /synthetic-access-old/u);
  assert.match(call.init.headers.get("cookie"), /synthetic-refresh-old/u);
  assert.equal(call.init.body, undefined);
  assert.equal(receipt.status, "rotated");
  assert.deepEqual(receipt.replacementCookies.map((item) => item.maxAgeSeconds), [900, 7200]);
  const rendered = JSON.stringify(receipt);
  for (const privateValue of [oldAccess, oldRefresh, newAccess, newRefresh]) assert.equal(rendered.includes(privateValue), false);
});

test("refresh reuse clears credentials and discards arbitrary server message", async () => {
  const privateDetail = "synthetic-private-server-detail";
  const jar = new BrowserSessionCookieJar("https://sessions.example.test");
  const scripted = scriptedFetch(
    () => loginResponse(),
    () => response(409, {
      status: "error",
      error: { code: "identity_session_refresh_reused", message: privateDetail },
    }, [
      ["set-cookie", clearCookie(BROWSER_SESSION_COOKIE_NAMES[0])],
      ["set-cookie", clearCookie(BROWSER_SESSION_COOKIE_NAMES[1])],
    ]),
  );
  const client = new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: scripted.fetch, cookieJar: jar });
  await client.completeLogin({
    tenantId: "tenant_main", accountId: "account_main", challengeId: "challenge_main",
    verificationCode: "synthetic-proof", channel: "email", identifier: "operator@example.test",
  });
  await assert.rejects(
    client.refresh({ projectId: "project_main", accountId: "account_main", idempotencyKey: "refresh_round54_0002" }),
    (error) => {
      assert.equal(error.code, "identity_session_refresh_reused");
      assert.equal(error.status, 409);
      assert.equal(error.message, "identity session refresh credential was reused");
      assert.equal(JSON.stringify(error).includes(privateDetail), false);
      return true;
    },
  );
  assert.equal(jar.toJSON().cookie_count, 0);
});

test("logout and revoke-all clear the SDK jar on 204", async () => {
  for (const operation of ["logout", "revokeAll"]) {
    const jar = new BrowserSessionCookieJar("https://sessions.example.test");
    const scripted = scriptedFetch(() => loginResponse(), () => response(204));
    const client = new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: scripted.fetch, cookieJar: jar });
    await client.completeLogin({
      tenantId: "tenant_main", accountId: "account_main", challengeId: "challenge_main",
      verificationCode: "synthetic-proof", channel: "email", identifier: "operator@example.test",
    });
    const receipt = await client[operation]({
      projectId: "project_main", accountId: "account_main", idempotencyKey: `${operation}_round54`,
    });
    assert.equal(receipt.httpStatus, 204);
    assert.equal(jar.toJSON().cookie_count, 0);
  }
});

test("browser-managed mode uses credentials include without exposing Set-Cookie", async () => {
  const scripted = scriptedFetch(() => response(204));
  const client = new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: scripted.fetch });
  const receipt = await client.bootstrap({ projectId: "project_main", accountId: "account_main" });
  assert.deepEqual(receipt.cookieState, { management: "browser", credential_values_exposed: false });
  assert.equal(scripted.calls[0].init.credentials, "include");
  assert.equal(scripted.calls[0].init.headers.has("cookie"), false);
});

test("303 continuation accepts only same-origin locations", async () => {
  const safe = scriptedFetch(() => response(303, undefined, [["location", "/console?login=complete"]]));
  const receipt = await new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: safe.fetch }).completeLogin({
    tenantId: "tenant_main", accountId: "account_main", challengeId: "challenge_main",
    verificationCode: "synthetic-proof", channel: "email", identifier: "operator@example.test",
  });
  assert.equal(receipt.redirectTo, "/console?login=complete");

  const unsafe = scriptedFetch(() => response(303, undefined, [["location", "https://other.example.test/"]]));
  await assert.rejects(
    new BrowserSessionClient({ baseUrl: "https://sessions.example.test", fetch: unsafe.fetch }).completeLogin({
      tenantId: "tenant_main", accountId: "account_main", challengeId: "challenge_main",
      verificationCode: "synthetic-proof", channel: "email", identifier: "operator@example.test",
    }),
    (error) => error.code === "browser_session_response_invalid",
  );
});

test("HTTPS is default and localhost HTTP requires explicit opt-in", () => {
  assert.throws(
    () => new BrowserSessionClient({ baseUrl: "http://localhost:8787" }),
    (error) => error.code === "identity_session_secure_transport_required",
  );
  assert.doesNotThrow(() => new BrowserSessionClient({ baseUrl: "http://localhost:8787", allowInsecureLocalhost: true }));
  assert.throws(
    () => new BrowserSessionClient({ baseUrl: "http://example.test", allowInsecureLocalhost: true }),
    (error) => error.code === "identity_session_secure_transport_required",
  );
});

test("OpenAPI 3.1 and capability manifests exactly match generated Python fixtures", () => {
  const openapi = browserSessionOpenApiDocument();
  const capabilities = browserSessionCapabilityManifest();
  assert.deepEqual(openapi, openapiFixture);
  assert.deepEqual(capabilities, parity.python_typescript_contract);
  assert.equal(fingerprint(openapi), parity.openapi.sha256);
  assert.equal(openapi.openapi, "3.1.0");
  assert.deepEqual(openapi["x-ashr-modalities"], [...BROWSER_SESSION_MODALITIES]);
  assert.deepEqual(capabilities.stable_error_codes, [...BROWSER_SESSION_ERROR_CODES]);
  const statuses = new Set();
  for (const pathItem of Object.values(openapi.paths)) {
    for (const operation of Object.values(pathItem)) {
      for (const status of Object.keys(operation.responses)) statuses.add(status);
    }
  }
  for (const status of ["303", "204", "401", "409", "429", "503"]) assert.ok(statuses.has(status));
  const serialized = JSON.stringify(openapi);
  for (const marker of ["ashr_live_", "Bearer ", "synthetic-private", "cookie=value"]) assert.equal(serialized.includes(marker), false);
});

test("route and generated Go capability gates preserve known gaps", () => {
  assert.equal(
    secureBrowserSessionRefreshRoute("project_main", "account_main"),
    "/v1/projects/project_main/accounts/account_main/browser-sessions/refresh",
  );
  assert.deepEqual(parity.go.executable_operations, ["complete_login", "refresh"]);
  assert.deepEqual(parity.go.unsupported_operations, ["bootstrap", "logout", "revoke_all"]);
  assert.deepEqual(parity.go.refresh_response_fields, ["schema_version", "status"]);
  assert.equal(parity.go.security_invariants.refresh_reuse_clears_cookies, true);
});

test("browser-session CLI exports public-safe capability, OpenAPI, and replay contracts", () => {
  const cli = fileURLToPath(new URL("../dist/browser-session-cli.js", import.meta.url));
  for (const command of ["capabilities", "openapi"]) {
    const result = spawnSync(process.execPath, [cli, command], { cwd: packageRoot, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    const output = JSON.parse(result.stdout);
    assert.equal(JSON.stringify(output).includes("ashr_live_"), false);
  }
  const result = spawnSync(process.execPath, [
    cli, "cookie-contract",
    "--issued-at", "2026-07-11T04:00:00Z",
    "--access-expires-at", "2026-07-11T06:00:00Z",
    "--refresh-expires-at", "2026-08-11T04:00:00Z",
    "--access-cap-seconds", "1800",
    "--refresh-cap-seconds", "604800",
    "--replayed-at", "2026-07-11T04:00:30Z",
  ], { cwd: repoRoot, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const contract = JSON.parse(result.stdout);
  assert.equal(contract.cookies[0].max_age_seconds, 1770);
  assert.equal(contract.contains_credential_values, false);
});
