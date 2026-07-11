import assert from "node:assert/strict";
import test from "node:test";

import { runSaaSCli, SecretInputError } from "../dist/saas.js";

const baseUrl = "http://127.0.0.1:8787";
const connectedAt = "2026-07-10T06:00:00Z";

function response(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function connection(provider) {
  return {
    schema_version: "ashr.clone.account_connection.v1",
    provider,
    account_id: "account_primary",
    credential_id: `cred_${provider}`,
    provider_subject_present: true,
    provider_login: `${provider}-login`,
    email_present: true,
    email_verified: true,
    connected_at: connectedAt,
    disconnected_at: null,
  };
}

async function withFetch(fetchImpl, action) {
  const previous = globalThis.fetch;
  globalThis.fetch = fetchImpl;
  try {
    return await action();
  } finally {
    globalThis.fetch = previous;
  }
}

test("SaaS CLI advertises all hosted account-connection commands", async () => {
  const help = await runSaaSCli(["--help"]);
  assert.match(help.usage, /oauth-connect-start/u);
  assert.match(help.usage, /oauth-connection/u);
  assert.match(help.usage, /oauth-disconnect/u);
});

test("SaaS CLI maps GitHub and Google to account-bound hosted routes", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url: String(url), init });
    const parsed = new URL(String(url));
    const provider = parsed.pathname.includes("/google/") ? "google" : "github";
    if (parsed.pathname.endsWith("/start")) {
      const authorize = new URL(provider === "google"
        ? "https://accounts.google.com/o/oauth2/v2/auth"
        : "https://github.com/login/oauth/authorize");
      authorize.searchParams.set("client_id", `${provider}-client`);
      authorize.searchParams.set("scope", provider === "google" ? "openid email profile" : "read:user user:email");
      authorize.searchParams.set("state", "state-public-reference");
      authorize.searchParams.set("code_challenge", "challenge-public-reference");
      authorize.searchParams.set("code_challenge_method", "S256");
      if (provider === "google") authorize.searchParams.set("nonce", "nonce-public-reference");
      return response({
        schema_version: "ashr.clone.account_connection.v1",
        provider,
        authorize_url: authorize.toString(),
        expires_at: "2026-07-10T06:10:00Z",
      });
    }
    if (parsed.pathname.endsWith("/connection")) return response(connection(provider));
    if (parsed.pathname.endsWith("/disconnect")) {
      return response({
        schema_version: "ashr.clone.account_connection.v1",
        provider,
        disconnected: true,
        revocation_status: "revoked",
        connection: { ...connection(provider), disconnected_at: "2026-07-10T06:05:00Z" },
      });
    }
    throw new Error(`unexpected path ${parsed.pathname}`);
  };

  await withFetch(fetchImpl, async () => {
    const start = await runSaaSCli([
      "--base-url", baseUrl,
      "oauth-connect-start",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--account-id", "account_primary",
      "--provider", "google",
      "--expected-google-audience", "google-client",
    ]);
    assert.equal(start.provider, "google");

    const read = await runSaaSCli([
      "--base-url", baseUrl,
      "oauth-connection",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--account-id", "account_primary",
      "--provider", "github",
    ]);
    assert.equal(read.credential_id, "cred_github");

    const disconnected = await runSaaSCli([
      "--base-url", baseUrl,
      "oauth-disconnect",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--account-id", "account_primary",
      "--provider", "github",
    ]);
    assert.equal(disconnected.disconnected, true);
  });

  const startCall = calls[0];
  assert.equal(startCall.init.method, "POST");
  assert.equal(new URL(startCall.url).pathname, "/v1/projects/project_local/oauth/google/start");
  assert.deepEqual(JSON.parse(startCall.init.body), {
    tenant_id: "tenant_local",
    account_id: "account_primary",
    scopes: ["openid", "email", "profile"],
  });

  const readCall = calls[1];
  const readUrl = new URL(readCall.url);
  assert.equal(readCall.init.method, "GET");
  assert.equal(readUrl.pathname, "/v1/projects/project_local/oauth/github/connection");
  assert.equal(readUrl.searchParams.get("tenant_id"), "tenant_local");
  assert.equal(readUrl.searchParams.get("account_id"), "account_primary");
  assert.equal(readCall.init.body, undefined);

  const disconnectCall = calls[2];
  assert.equal(disconnectCall.init.method, "POST");
  assert.deepEqual(JSON.parse(disconnectCall.init.body), {
    tenant_id: "tenant_local",
    account_id: "account_primary",
  });
});

test("hosted account-connection commands reject local mode and incomplete bindings", async () => {
  await assert.rejects(
    runSaaSCli([
      "oauth-connection",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--account-id", "account_primary",
      "--provider", "github",
    ]),
    (error) => error instanceof SecretInputError && /require --base-url/u.test(error.message),
  );
  await assert.rejects(
    runSaaSCli([
      "--base-url", baseUrl,
      "oauth-connection",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--provider", "github",
    ]),
    /missing required --account-id/u,
  );
  await assert.rejects(
    runSaaSCli([
      "--base-url", baseUrl,
      "oauth-connection",
      "--tenant-id", "tenant_local",
      "--project-id", "project_local",
      "--account-id", "account_primary",
      "--provider", "wechat",
    ]),
    /github or google/u,
  );
});

test("SaaS CLI fails closed when hosted payload contains nested credential material", async () => {
  await withFetch(async () => response({
    ...connection("github"),
    metadata: {
      nested: {
        provider_subject_sha256: "a".repeat(64),
      },
    },
  }), async () => {
    await assert.rejects(
      runSaaSCli([
        "--base-url", baseUrl,
        "oauth-connection",
        "--tenant-id", "tenant_local",
        "--project-id", "project_local",
        "--account-id", "account_primary",
        "--provider", "github",
      ]),
      /must not include provider_subject_sha256/u,
    );
  });
});
