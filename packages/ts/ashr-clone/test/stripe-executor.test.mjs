import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  EnvSecretRefResolver,
  IdempotencyFingerprintRegistry,
  StripeExecutorContractError,
  StripeTestHostedExecutor,
} from "../dist/stripe-executor.js";

const API_SECRET = ["sk", "test", "executorOnlySecret123"].join("_");
const WEBHOOK_SECRET = ["whsec", "executorOnlyWebhook123"].join("_");
const SIGNATURE = "t=1700000000,v1=private-signature-value";
const PAN = "4242 4242 4242 4242";
const CVC = "123";

function checkoutPlan(overrides = {}) {
  return {
    schema_version: "ashr.clone.billing_provider_contract.v1",
    plan_type: "checkout_session",
    provider: "stripe",
    mode: "test",
    tenant_id: "tenant-a",
    project_id: "project-a",
    success_url: "https://app.example.test/success",
    cancel_url: "https://app.example.test/cancel",
    provider_request: {
      provider: "stripe",
      operation: "checkout.sessions.create",
      mode: "subscription",
      customer: "cus_public",
      line_items: [{ price_lookup_key: "pro_monthly", quantity: 1 }],
      secret_ref: "env:STRIPE_TEST_SECRET",
    },
    idempotency_key: "checkout-key-0001",
    ...overrides,
  };
}

function pythonPortalPlan(overrides = {}) {
  return {
    schema_version: "ashr.clone.payment_provider_adapter.v1",
    plan_type: "hosted_payment",
    provider: "stripe",
    hosted_surface: "stripe_billing_portal",
    tenant_id: "tenant-a",
    project_id: "project-a",
    mode_gate: { mode: "test" },
    credential_ref: "env:STRIPE_TEST_SECRET",
    verification_key_ref: "env:STRIPE_WEBHOOK_SECRET",
    idempotency: { required: true, key: "portal-key-000001" },
    request_shape: {
      operation: "billing_portal.sessions.create",
      customer_ref: "provider-ref:customer-1",
      return_url: "https://app.example.test/billing",
    },
    ...overrides,
  };
}

function harness(options = {}) {
  const calls = { checkout: 0, portal: 0, webhook: 0 };
  const seen = {};
  const resolver = options.resolver ?? new EnvSecretRefResolver({
    STRIPE_TEST_SECRET: API_SECRET,
    STRIPE_WEBHOOK_SECRET: WEBHOOK_SECRET,
  });
  const transport = {
    async createCheckoutSession(request, context) {
      calls.checkout += 1;
      seen.checkout = { request, context };
      return options.checkoutResult ?? {
        id: "cs_test_public_1",
        url: "https://checkout.stripe.test/session/1",
        secret: API_SECRET,
        card_number: PAN,
        cvc: CVC,
        raw_response: { authorization: `Bearer ${API_SECRET}` },
      };
    },
    async createBillingPortalSession(request, context) {
      calls.portal += 1;
      seen.portal = { request, context };
      return {
        id: "bps_test_public_1",
        url: "https://billing.stripe.test/session/1",
        client_secret: API_SECRET,
      };
    },
    async verifyWebhook(request) {
      calls.webhook += 1;
      seen.webhook = request;
      return options.webhookResult ?? {
        verified: true,
        event_id_ref: "provider-ref:evt_test_public_1",
        event_type: "checkout.session.completed",
        livemode: false,
        raw_body: Buffer.from(PAN),
        signature: SIGNATURE,
        secret: WEBHOOK_SECRET,
      };
    },
  };
  return {
    calls,
    seen,
    executor: new StripeTestHostedExecutor({
      secretResolver: resolver,
      transport,
      registry: options.registry ?? new IdempotencyFingerprintRegistry(),
    }),
  };
}

function assertSerializedSafe(value) {
  const serialized = JSON.stringify(value);
  for (const forbidden of [API_SECRET, WEBHOOK_SECRET, SIGNATURE, PAN, PAN.replaceAll(" ", ""), CVC, "raw_response"]) {
    assert.equal(serialized.includes(forbidden), false, `public result leaked ${forbidden}`);
  }
}

test("checkout resolves env secret transiently and returns a public-safe hosted result", async () => {
  const { executor, calls, seen } = harness();
  const result = await executor.execute(checkoutPlan());

  assert.equal(calls.checkout, 1);
  assert.equal(calls.portal, 0);
  assert.equal(seen.checkout.context.apiSecret, API_SECRET);
  assert.equal(seen.checkout.context.idempotencyKey, "checkout-key-0001");
  assert.equal("secret_ref" in seen.checkout.request, false);
  assert.equal(seen.checkout.request.success_url, "https://app.example.test/success");
  assert.equal(seen.checkout.request.mode, "subscription");
  assert.equal(result.provider_session_id, "cs_test_public_1");
  assert.equal(result.hosted_url, "https://checkout.stripe.test/session/1");
  assert.equal(result.mode, "test");
  assert.equal(result.side_effects.real_charge_possible, false);
  assert.equal(result.secret_value_present, false);
  assert.equal(result.raw_card_data_present, false);
  assert.equal(result.raw_provider_response_included, false);
  assertSerializedSafe(result);
});

test("checkout preserves an explicit one-time payment mode", async () => {
  const { executor, seen } = harness();
  const plan = checkoutPlan();
  plan.provider_request.mode = "payment";

  await executor.execute(plan);

  assert.equal(seen.checkout.request.checkout_mode, "payment");
  assert.equal(seen.checkout.request.mode, "payment");
});

test("checkout rejects an ambiguous provider mode before transport", async () => {
  const { executor, calls } = harness();
  const plan = checkoutPlan();
  delete plan.provider_request.mode;

  await assert.rejects(
    () => executor.execute(plan),
    /Stripe Checkout mode must be payment or subscription/,
  );
  assert.equal(calls.checkout, 0);
});

test("Python-style billing portal plan executes through the same contract", async () => {
  const { executor, calls, seen } = harness();
  const result = await executor.execute(pythonPortalPlan());

  assert.equal(calls.portal, 1);
  assert.equal(seen.portal.context.apiSecret, API_SECRET);
  assert.equal(seen.portal.request.customer_ref, "provider-ref:customer-1");
  assert.equal(result.hosted_surface, "stripe_billing_portal");
  assert.equal(result.operation, "billing_portal.sessions.create");
  assert.equal(result.provider_session_id, "bps_test_public_1");
  assertSerializedSafe(result);
});

test("same idempotency key and fingerprint replays without a second provider call", async () => {
  const { executor, calls } = harness();
  const first = await executor.execute(checkoutPlan());
  const second = await executor.execute(checkoutPlan());

  assert.equal(first.replayed, false);
  assert.equal(second.replayed, true);
  assert.equal(calls.checkout, 1);
  assert.equal(second.request_fingerprint_sha256, first.request_fingerprint_sha256);
});

test("concurrent identical executions share the in-flight provider call", async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let calls = 0;
  const executor = new StripeTestHostedExecutor({
    secretResolver: new EnvSecretRefResolver({ STRIPE_TEST_SECRET: API_SECRET }),
    transport: {
      async createCheckoutSession() {
        calls += 1;
        await gate;
        return { id: "cs_test_concurrent", url: "https://checkout.stripe.test/concurrent" };
      },
      async createBillingPortalSession() {
        throw new Error("unexpected portal call");
      },
      async verifyWebhook() {
        throw new Error("unexpected webhook call");
      },
    },
  });
  const firstPromise = executor.execute(checkoutPlan());
  const secondPromise = executor.execute(checkoutPlan());
  release();
  const [first, second] = await Promise.all([firstPromise, secondPromise]);

  assert.equal(calls, 1);
  assert.equal(first.replayed, false);
  assert.equal(second.replayed, true);
});

test("idempotency key reuse with a changed request is rejected", async () => {
  const { executor, calls } = harness();
  await executor.execute(checkoutPlan());
  const changed = checkoutPlan({
    cancel_url: "https://app.example.test/a-different-cancel",
  });

  await assert.rejects(
    () => executor.execute(changed),
    (error) => error instanceof StripeExecutorContractError && /different request fingerprint/.test(error.message),
  );
  assert.equal(calls.checkout, 1);
});

test("live and unsupported plans are rejected before secrets or transport are touched", async () => {
  let resolverCalls = 0;
  let transportCalls = 0;
  const executor = new StripeTestHostedExecutor({
    secretResolver: {
      resolveSecret() {
        resolverCalls += 1;
        return API_SECRET;
      },
    },
    transport: {
      async createCheckoutSession() { transportCalls += 1; return {}; },
      async createBillingPortalSession() { transportCalls += 1; return {}; },
      async verifyWebhook() { transportCalls += 1; return { verified: false }; },
    },
  });

  await assert.rejects(() => executor.execute(checkoutPlan({ mode: "live" })), /live Stripe execution is not supported/);
  await assert.rejects(
    () => executor.execute(checkoutPlan({
      provider_request: { operation: "payment_intents.create", secret_ref: "env:STRIPE_TEST_SECRET" },
    })),
    /unsupported Stripe hosted operation/,
  );
  assert.equal(resolverCalls, 0);
  assert.equal(transportCalls, 0);
});

test("missing environment values fail without exposing the reference or a secret", async () => {
  const { executor } = harness({ resolver: new EnvSecretRefResolver({}) });
  await assert.rejects(
    () => executor.execute(checkoutPlan()),
    (error) => {
      assert.equal(error instanceof StripeExecutorContractError, true);
      assert.equal(error.message.includes("STRIPE_TEST_SECRET"), false);
      assert.equal(error.message.includes(API_SECRET), false);
      return true;
    },
  );
});

test("hosted session URL must be https and malicious provider fields remain private", async () => {
  const unsafe = harness({
    checkoutResult: {
      id: "cs_test_public",
      url: "http://checkout.example.test/session",
      secret: API_SECRET,
      card_number: PAN,
    },
  });
  await assert.rejects(() => unsafe.executor.execute(checkoutPlan()), /hosted url must be an https URL/);
});

test("verified test webhook maps to a digest-only public envelope", async () => {
  const { executor, calls, seen } = harness();
  const rawBody = Buffer.from('{"id":"evt_test_public_1","type":"checkout.session.completed"}');
  const result = await executor.verifyWebhook({
    rawBody,
    headers: { "Stripe-Signature": SIGNATURE, "Content-Type": "application/json" },
    verificationKeyRef: "env:STRIPE_WEBHOOK_SECRET",
  });

  assert.equal(calls.webhook, 1);
  assert.equal(seen.webhook.webhookSecret, WEBHOOK_SECRET);
  assert.equal(seen.webhook.signatureHeader, SIGNATURE);
  assert.deepEqual(Buffer.from(seen.webhook.rawBody), rawBody);
  assert.equal(result.verified, true);
  assert.equal(result.event_id_ref, "provider-ref:evt_test_public_1");
  assert.equal(result.payload_sha256, createHash("sha256").update(rawBody).digest("hex"));
  assert.equal(result.raw_body_included, false);
  assert.equal(result.signature_header_shape.raw_header_values_included, false);
  assertSerializedSafe(result);
});

test("live webhook event is mapped to an unverified mode mismatch", async () => {
  const { executor } = harness({
    webhookResult: {
      verified: true,
      event_id_ref: "provider-ref:evt_live_public_1",
      event_type: "invoice.paid",
      livemode: true,
    },
  });
  const result = await executor.verifyWebhook({
    rawBody: Buffer.from("{}"),
    signatureHeader: SIGNATURE,
    verificationKeyRef: "env:STRIPE_WEBHOOK_SECRET",
  });

  assert.equal(result.verified, false);
  assert.deepEqual(result.reason_codes, ["provider_mode_mismatch"]);
  assert.equal(result.livemode, true);
  assertSerializedSafe(result);
});

test("missing signature returns a safe failure without resolving or invoking verifier", async () => {
  let resolverCalls = 0;
  const base = harness({
    resolver: {
      resolveSecret() {
        resolverCalls += 1;
        return WEBHOOK_SECRET;
      },
    },
  });
  const result = await base.executor.verifyWebhook({
    rawBody: Buffer.from("{}"),
    verificationKeyRef: "env:STRIPE_WEBHOOK_SECRET",
  });

  assert.equal(result.verified, false);
  assert.deepEqual(result.reason_codes, ["missing_signature_headers"]);
  assert.deepEqual(result.signature_header_shape.missing_headers, ["stripe-signature"]);
  assert.equal(result.integration_hook.verifier_called, false);
  assert.equal(resolverCalls, 0);
  assert.equal(base.calls.webhook, 0);
});

test("raw card data in a plan is rejected before execution", async () => {
  const { executor, calls } = harness();
  const plan = checkoutPlan({
    provider_request: {
      operation: "checkout.sessions.create",
      secret_ref: "env:STRIPE_TEST_SECRET",
      mode: "subscription",
      card_number: PAN,
    },
  });
  await assert.rejects(() => executor.execute(plan), /sensitive Stripe request field/);
  assert.equal(calls.checkout, 0);
});
