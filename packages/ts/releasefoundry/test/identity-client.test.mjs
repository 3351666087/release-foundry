import assert from "node:assert/strict";
import test from "node:test";

import {
  IDENTITY_SCHEMA_VERSION,
  IdentityClient,
  IdentityClientError,
  IdentitySessionCredential,
  OAuthBegin,
  OAuthBindingTicket,
} from "../dist/index.js";

function identityView() {
  return {
    account_id: "account-1",
    primary_email_hint: "o***@qq.com",
    display_name: "Owner",
    locale: "zh-CN",
    region: "cn",
    status: "active",
    preferred_registration_method: "email_magic_link",
    credentials: [{ provider: "email_magic_link", kind: "email" }],
    two_factor: { enabled: false, recommended: true, methods: [] },
    provider_capabilities: [
      {
        provider: "qq",
        kind: "oauth2",
        enabled: true,
        region: "cn",
        supports_registration: true,
        supports_login: true,
        supports_explicit_binding: true,
        pkce_required: true,
      },
      {
        provider: "wechat_open",
        kind: "oauth2",
        enabled: true,
        region: "cn",
        supports_registration: true,
        supports_login: true,
        supports_explicit_binding: true,
        pkce_required: true,
      },
    ],
  };
}

function response(payload, status = 200) {
  return {
    status,
    body: JSON.stringify({
      schema_version: IDENTITY_SCHEMA_VERSION,
      ...payload,
    }),
  };
}

function queuedTransport(responses) {
  const requests = [];
  return {
    requests,
    transport: async (request) => {
      requests.push(request);
      assert.ok(responses.length > 0, `unexpected request to ${request.url}`);
      return responses.shift();
    },
  };
}

test("registration and login use separate A3 paths and return typed MFA", async () => {
  const fake = queuedTransport([
    response({
      challenge_id: "register-challenge",
      purpose: "registration",
      delivery_method: "email_magic_link",
      delivery_hint: "o***@qq.com",
      expires_at: "2026-07-14T12:00:00Z",
    }),
    response({ status: "registered", identity: identityView() }, 201),
    response({
      challenge_id: "login-challenge",
      purpose: "login",
      delivery_method: "email_magic_link",
      delivery_hint: "o***@qq.com",
      expires_at: "2026-07-14T12:00:00Z",
    }),
    response({
      status: "mfa_required",
      mfa_challenge_id: "mfa-1",
      expires_at: "2026-07-14T12:05:00Z",
    }),
  ]);
  const client = new IdentityClient({ transport: fake.transport });

  const challenge = await client.beginEmailRegistration("owner@qq.com", {
    locale: "zh-CN",
    region: "cn",
  });
  assert.equal(challenge.purpose, "registration");
  const registered = await client.completeEmailRegistration(
    "register-challenge",
    "registration-proof",
    { displayName: "Owner" },
  );
  assert.equal(registered.preferredRegistrationMethod, "email_magic_link");
  assert.equal(registered.twoFactor.recommended, true);
  assert.deepEqual(
    registered.providerCapabilities.map((item) => item.provider),
    ["qq", "wechat_open"],
  );
  assert.equal(
    registered.providerCapabilities.every(
      (item) =>
        item.region === "cn" &&
        item.pkceRequired &&
        item.supportsRegistration &&
        item.supportsLogin &&
        item.supportsExplicitBinding,
    ),
    true,
  );

  await client.beginEmailLogin("owner@qq.com");
  const auth = await client.completeEmailLogin("login-challenge", "login-proof");
  assert.deepEqual(auth, {
    status: "mfa_required",
    mfaChallengeId: "mfa-1",
    expiresAt: "2026-07-14T12:05:00Z",
  });

  assert.deepEqual(
    fake.requests.map((request) => new URL(request.url).pathname),
    [
      "/v1/identity/registration/email/begin",
      "/v1/identity/registration/email/complete",
      "/v1/identity/login/email/begin",
      "/v1/identity/login/email/complete",
    ],
  );
  assert.deepEqual(JSON.parse(fake.requests[0].body), {
    email: "owner@qq.com",
    locale: "zh-CN",
    region: "cn",
  });
  assert.equal(
    JSON.parse(fake.requests[3].body).proof,
    "login-proof",
    "proof is sent only through the transport body",
  );
});

test("sessions, OAuth URLs, and binding proofs serialize only safe presence flags", async () => {
  const session = new IdentitySessionCredential({
    accountId: "account-1",
    sessionId: "session-1",
    sessionToken: "session-secret-value",
    expiresAt: "2026-07-15T00:00:00Z",
  });
  const begin = new OAuthBegin({
    flowId: "flow-1",
    provider: "qq",
    intent: "link",
    authorizationUrl: "https://oauth.example/authorize?state=secret-state",
    expiresAt: "2026-07-14T12:00:00Z",
  });
  const ticket = new OAuthBindingTicket({
    bindingTicketId: "ticket-1",
    bindingTicketProof: "binding-proof-secret",
    provider: "qq",
    expiresAt: "2026-07-14T12:00:00Z",
  });

  assert.equal(begin.authorizationUrl().includes("secret-state"), true);
  assert.equal(ticket.bindingProof(), "binding-proof-secret");
  for (const [value, forbidden] of [
    [session, "session-secret-value"],
    [begin, "secret-state"],
    [ticket, "binding-proof-secret"],
  ]) {
    const serialized = JSON.stringify(value);
    assert.equal(serialized.includes(forbidden), false);
    assert.equal(serialized.includes("_present"), true);
  }
  assert.deepEqual(session.headers(), {
    Authorization: "Bearer session-secret-value",
    "X-ReleaseFoundry-Session-ID": "session-1",
  });
});

test("OAuth link and opaque binding require an explicit authenticated session and consent", async () => {
  const session = new IdentitySessionCredential({
    accountId: "account-1",
    sessionId: "session-1",
    sessionToken: "session-secret-value",
    expiresAt: "2026-07-15T00:00:00Z",
  });
  const fake = queuedTransport([
    response({
      flow_id: "flow-link",
      provider: "qq",
      intent: "link",
      authorization_url: "https://oauth.example/authorize?state=secret-state",
      expires_at: "2026-07-14T12:00:00Z",
    }),
    response({
      status: "binding_ticket_issued",
      binding_ticket_id: "ticket-1",
      binding_ticket_proof: "binding-proof-secret",
      provider: "qq",
      expires_at: "2026-07-14T12:05:00Z",
    }),
    response({ status: "bound", identity: identityView() }),
    response({ status: "revoked" }),
  ]);
  const client = new IdentityClient({ transport: fake.transport }).withSession(session);

  const begin = await client.beginOAuth(
    "qq",
    "link",
    "https://app.example/oauth/callback",
  );
  assert.ok(begin instanceof OAuthBegin);
  const ticket = await client.completeOAuth(
    "flow-link",
    "state-secret",
    "code-secret",
  );
  assert.ok(ticket instanceof OAuthBindingTicket);
  await assert.rejects(
    client.bindCredential(ticket, { explicitConsent: false }),
    /explicitConsent must be true/,
  );
  const bound = await client.bindCredential(ticket, { explicitConsent: true });
  assert.equal(bound.accountId, "account-1");
  await client.revokeSession();

  assert.equal(fake.requests.length, 4);
  assert.equal(fake.requests[0].headers.Authorization, "Bearer session-secret-value");
  assert.equal(fake.requests[0].headers["X-ReleaseFoundry-Session-ID"], "session-1");
  assert.deepEqual(JSON.parse(fake.requests[0].body), {
    provider: "qq",
    intent: "link",
    redirect_uri: "https://app.example/oauth/callback",
  });
  assert.deepEqual(JSON.parse(fake.requests[1].body), {
    flow_id: "flow-link",
    state: "state-secret",
    code: "code-secret",
  });
  assert.deepEqual(JSON.parse(fake.requests[2].body), {
    binding_ticket_id: "ticket-1",
    binding_ticket_proof: "binding-proof-secret",
    explicit_consent: true,
  });

  const anonymous = new IdentityClient({ transport: fake.transport });
  await assert.rejects(
    anonymous.beginOAuth("qq", "link", "https://app.example/oauth/callback"),
    (error) =>
      error instanceof IdentityClientError && error.code === "session_required",
  );
});

test("errors are sanitized and unsupported schema versions fail closed", async () => {
  const errorTransport = queuedTransport([
    {
      status: 401,
      body: JSON.stringify({
        schema_version: IDENTITY_SCHEMA_VERSION,
        error: {
          code: "invalid_proof",
          message:
            'denied Bearer session-secret and "proof":"registration-proof-secret"',
        },
      }),
    },
    {
      status: 200,
      body: JSON.stringify({
        schema_version: "releasefoundry.identity.v999",
        challenge_id: "challenge-1",
      }),
    },
  ]);
  const client = new IdentityClient({ transport: errorTransport.transport });

  await assert.rejects(
    client.beginEmailLogin("owner@qq.com"),
    (error) => {
      assert.ok(error instanceof IdentityClientError);
      assert.equal(error.code, "invalid_proof");
      assert.equal(error.statusCode, 401);
      const serialized = JSON.stringify(error);
      assert.equal(serialized.includes("session-secret"), false);
      assert.equal(serialized.includes("registration-proof-secret"), false);
      return true;
    },
  );
  await assert.rejects(
    client.beginEmailLogin("owner@qq.com"),
    (error) =>
      error instanceof IdentityClientError &&
      error.code === "invalid_response" &&
      /unsupported identity schema version/.test(error.message),
  );
});
