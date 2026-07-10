import assert from "node:assert/strict";
import test from "node:test";

import {
  IDENTITY_VERIFICATION_CHALLENGE_STATUSES,
  IDENTITY_VERIFICATION_PROVIDERS,
  IDENTITY_VERIFICATION_PURPOSES,
  IDENTITY_VERIFICATION_RECEIPT_STATUSES,
  UnifiedIdentityContractError,
  UnifiedIdentityHttpClient,
  assertPublicUnifiedIdentityPayload,
  identityVerificationChallengeCreateRoute,
  identityVerificationChallengeRoute,
  identityVerificationChallengeVerifyRoute,
  identityVerificationChallengesRoute,
  identityVerificationResendRoute,
  identityVerificationVerifyRoute,
  parseIdentityVerificationChallenge,
  parseIdentityVerificationReceipt,
} from "../dist/unified-identity.js";

const createdAt = "2026-07-10T10:00:00.000Z";
const expiresAt = "2026-07-10T10:10:00.000Z";

function challenge(provider = "email", overrides = {}) {
  return {
    challenge_id: `challenge_${provider}_01`,
    provider,
    purpose: "binding",
    status: "pending",
    destination_hint: provider === "email" ? "a***@e***.com" : "***1234",
    destination_digest_ref: `digest-store:${provider}-01`,
    created_at: createdAt,
    expires_at: expiresAt,
    ttl_seconds: 600,
    attempt_cap: 5,
    attempts_remaining: 5,
    resend_cooldown_seconds: 60,
    resend_available_at: "2026-07-10T10:01:00.000Z",
    single_use: true,
    account_id: "account_01",
    verified_at: null,
    consumed_at: null,
    ...overrides,
  };
}

function receipt(provider = "email", overrides = {}) {
  return {
    receipt_id: `receipt_${provider}_01`,
    challenge_id: `challenge_${provider}_01`,
    provider,
    purpose: "binding",
    status: "verified",
    destination_digest_ref: `digest-store:${provider}-01`,
    verified_at: "2026-07-10T10:01:00.000Z",
    expires_at: "2026-07-10T10:06:00.000Z",
    single_use: true,
    account_id: "account_01",
    consumed_at: null,
    ...overrides,
  };
}

function response(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("verification constants exactly match Python canonical contract", () => {
  assert.deepEqual([...IDENTITY_VERIFICATION_PROVIDERS], ["email", "phone"]);
  assert.deepEqual([...IDENTITY_VERIFICATION_PURPOSES], ["binding", "login", "recovery"]);
  assert.deepEqual([...IDENTITY_VERIFICATION_CHALLENGE_STATUSES], [
    "pending", "verified", "consumed", "expired", "locked",
  ]);
  assert.deepEqual([...IDENTITY_VERIFICATION_RECEIPT_STATUSES], [
    "verified", "consumed", "expired",
  ]);
});

test("verification route builders expose the four canonical routes", () => {
  assert.equal(
    identityVerificationChallengesRoute(),
    "/v1/identity/verifications/challenges",
  );
  assert.equal(
    identityVerificationChallengeRoute("challenge:01"),
    "/v1/identity/verifications/challenges/challenge%3A01",
  );
  assert.equal(
    identityVerificationResendRoute("challenge:01"),
    "/v1/identity/verifications/challenges/challenge%3A01/resend",
  );
  assert.equal(
    identityVerificationVerifyRoute("challenge:01"),
    "/v1/identity/verifications/challenges/challenge%3A01/verify",
  );
  assert.equal(identityVerificationChallengeCreateRoute(), identityVerificationChallengesRoute());
  assert.equal(
    identityVerificationChallengeVerifyRoute("challenge:01"),
    identityVerificationVerifyRoute("challenge:01"),
  );
});

for (const provider of IDENTITY_VERIFICATION_PROVIDERS) {
  test(`parses canonical ${provider} challenge and receipt DTOs`, () => {
    const parsedChallenge = parseIdentityVerificationChallenge(challenge(provider));
    assert.equal(parsedChallenge.provider, provider);
    assert.equal(parsedChallenge.attempt_cap, 5);
    assert.equal(parsedChallenge.resend_cooldown_seconds, 60);
    assert.equal(parsedChallenge.destination_digest_ref, `digest-store:${provider}-01`);
    assert.equal(parsedChallenge.single_use, true);

    const parsedReceipt = parseIdentityVerificationReceipt(receipt(provider));
    assert.equal(parsedReceipt.provider, provider);
    assert.equal(parsedReceipt.receipt_id, `receipt_${provider}_01`);
    assert.equal(parsedReceipt.status, "verified");
    assert.equal(parsedReceipt.single_use, true);
  });
}

test("challenge parser enforces canonical attempts, lifecycle, refs, and single use", () => {
  for (const invalid of [
    challenge("email", { attempts_remaining: 6 }),
    challenge("email", { attempt_cap: 0 }),
    challenge("email", { ttl_seconds: 0 }),
    challenge("email", { resend_cooldown_seconds: 0 }),
    challenge("email", { single_use: false }),
    challenge("email", { status: "verified", verified_at: null }),
    challenge("email", { status: "consumed", consumed_at: null }),
    challenge("email", { destination_hint: "raw@example.com" }),
    challenge("phone", { destination_hint: "+8613812345678" }),
    challenge("email", { destination_digest_ref: "sha256:abc" }),
    challenge("email", { destination_digest_ref: "missing-namespace" }),
    challenge("github"),
  ]) {
    assert.throws(() => parseIdentityVerificationChallenge(invalid), UnifiedIdentityContractError);
  }
});

test("receipt parser enforces canonical receipt fields and single-use lifecycle", () => {
  for (const invalid of [
    receipt("email", { single_use: false }),
    receipt("email", { status: "consumed", consumed_at: null }),
    receipt("email", { destination_digest_ref: "sha-256:abc" }),
    receipt("email", { destination_digest_ref: "mailto:owner@example.com" }),
    receipt("github"),
  ]) {
    assert.throws(() => parseIdentityVerificationReceipt(invalid), UnifiedIdentityContractError);
  }
});

test("public guard exactly protects Python forbidden verification aliases", () => {
  for (const key of [
    "email",
    "email_address",
    "phone",
    "phone_number",
    "destination",
    "destination_value",
    "otp",
    "verification_code",
    "verification_value",
  ]) {
    assert.throws(
      () => assertPublicUnifiedIdentityPayload({ challenge_id: "challenge_01", [key]: "leak" }),
      UnifiedIdentityContractError,
    );
  }
  assert.doesNotThrow(() => assertPublicUnifiedIdentityPayload({
    destination_ref: "vault:destination-01",
    verification_code_ref: "vault:code-01",
    code: "stable_public_code",
    challenge_digest: "public-compatible-field",
  }));
});

test("error details destination exception is path-sensitive and still rejects raw contacts", () => {
  assert.doesNotThrow(() => assertPublicUnifiedIdentityPayload({
    error: {
      code: "identity_verification_failed",
      details: { destination: "masked email destination" },
    },
  }));
  for (const destination of ["owner@example.com", "+8613812345678"]) {
    assert.throws(
      () => assertPublicUnifiedIdentityPayload({
        error: { code: "identity_verification_failed", details: { destination } },
      }),
      UnifiedIdentityContractError,
    );
  }
  assert.throws(
    () => assertPublicUnifiedIdentityPayload({
      result: { details: { destination: "masked email destination" } },
    }),
    UnifiedIdentityContractError,
  );
});

test("client start/get/resend/verify requests exactly match Python transport", async () => {
  const calls = [];
  const replies = [
    challenge(),
    challenge(),
    challenge("email", {
      attempts_remaining: 4,
      resend_available_at: "2026-07-10T10:02:00.000Z",
    }),
    receipt(),
  ];
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (url, init) => {
      calls.push({
        url: String(url),
        method: init.method,
        body: init.body === undefined ? {} : JSON.parse(init.body),
      });
      return response({ result: replies.shift() });
    },
  });

  await client.startVerification({
    provider: "email",
    purpose: "binding",
    destinationRef: "vault:destination-email-01",
    accountId: "account_01",
    idempotencyKey: "idem_start_01",
  });
  await client.getVerification("challenge_email_01");
  await client.resendVerification({
    challengeId: "challenge_email_01",
    idempotencyKey: "idem_resend_01",
  });
  await client.verifyChallenge({
    challengeId: "challenge_email_01",
    verificationCodeRef: "vault:verification-code-01",
    idempotencyKey: "idem_verify_01",
  });

  assert.deepEqual(calls, [
    {
      url: "http://127.0.0.1:8787/v1/identity/verifications/challenges",
      method: "POST",
      body: {
        provider: "email",
        purpose: "binding",
        destination_ref: "vault:destination-email-01",
        idempotency_key: "idem_start_01",
        account_id: "account_01",
      },
    },
    {
      url: "http://127.0.0.1:8787/v1/identity/verifications/challenges/challenge_email_01",
      method: "GET",
      body: {},
    },
    {
      url: "http://127.0.0.1:8787/v1/identity/verifications/challenges/challenge_email_01/resend",
      method: "POST",
      body: { idempotency_key: "idem_resend_01" },
    },
    {
      url: "http://127.0.0.1:8787/v1/identity/verifications/challenges/challenge_email_01/verify",
      method: "POST",
      body: {
        verification_code_ref: "vault:verification-code-01",
        idempotency_key: "idem_verify_01",
      },
    },
  ]);
});

test("compatibility aliases only accept canonical opaque reference options", async () => {
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async (_url, init) => response({
      result: init.method === "POST" && JSON.parse(init.body).verification_code_ref
        ? receipt()
        : challenge(),
    }),
  });
  const created = await client.createVerificationChallenge({
    provider: "phone",
    purpose: "login",
    destinationRef: "vault:destination-phone-01",
    idempotencyKey: "idem_create_01",
  });
  const verified = await client.verifyVerificationChallenge({
    challengeId: created.challenge_id,
    verificationCodeRef: "vault:verification-code-02",
    idempotencyKey: "idem_verify_02",
  });
  assert.equal(created.provider, "email");
  assert.equal(verified.receipt_id, "receipt_email_01");
});

test("client rejects account and opaque-reference violations before fetch", () => {
  let calls = 0;
  const client = new UnifiedIdentityHttpClient({
    baseUrl: "http://127.0.0.1:8787",
    fetch: async () => {
      calls += 1;
      return response({});
    },
  });
  for (const options of [
    {
      provider: "email",
      purpose: "binding",
      destinationRef: "vault:destination-01",
      idempotencyKey: "idem_01",
    },
    {
      provider: "phone",
      purpose: "recovery",
      destinationRef: "vault:destination-02",
      idempotencyKey: "idem_02",
    },
    {
      provider: "email",
      purpose: "login",
      destinationRef: "owner@example.com",
      idempotencyKey: "idem_03",
    },
    {
      provider: "phone",
      purpose: "login",
      destinationRef: "tel:+8613812345678",
      idempotencyKey: "idem_04",
    },
    {
      provider: "email",
      purpose: "step_up",
      destinationRef: "vault:destination-05",
      idempotencyKey: "idem_05",
    },
  ]) {
    assert.throws(() => client.startVerification(options), UnifiedIdentityContractError);
  }
  assert.throws(() => client.verifyChallenge({
    challengeId: "challenge_01",
    verificationCodeRef: "123456",
    idempotencyKey: "idem_06",
  }), UnifiedIdentityContractError);
  assert.equal(calls, 0);
});
