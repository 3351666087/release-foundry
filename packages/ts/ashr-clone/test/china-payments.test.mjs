import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  ChinaPaymentContractError,
  PaymentIdempotencyConflictError,
  PaymentIdempotencyRegistry,
  PaymentReconciliationConflictError,
  PaymentReconciliationStore,
  buildCnyTradePlan,
  buildNotificationEnvelope,
  buildPaymentQueryPlan,
  buildProviderAccountBinding,
  buildRefundPlan,
  chinaPaymentCapabilityManifest,
  normalizeDailyBillRecord,
  normalizeProviderEvent,
  normalizeRefundStatus,
} from "../dist/china-payments.js";

const scope = { tenantId: "tenant-cn-a", projectId: "project-cn-a" };
const refs = {
  credentialRef: "vault:payments/merchant-signing-key",
  verificationKeyRef: "vault:payments/provider-verification-key",
  accountRef: "provider-ref:merchant-account-mainland",
};

function trade(provider, overrides = {}) {
  return buildCnyTradePlan({
    provider,
    ...scope,
    ...refs,
    orderRef: `order-${provider}-0001`,
    amountMinor: 1888,
    description: "Ashr team plan",
    returnUrl: "https://app.example.test/payments/return",
    notifyUrl: "https://api.example.test/payments/notify",
    idempotencyKey: `trade-${provider}-00000001`,
    metadata: { plan: "team", region: "cn" },
    ...(provider === "domestic_bank_card" ? { paymentMethodRef: "provider-ref:acquirer/payment-method-token-1" } : {}),
    ...overrides,
  });
}

function assertPublicSafe(value) {
  const serialized = JSON.stringify(value).toLowerCase();
  for (const forbidden of [
    "sk_test_executoronly",
    "-----begin private key-----",
    "4242 4242 4242 4242",
    "\"raw_body\":",
    "\"raw_headers\":",
    "\"payer\":",
    "\"buyer\":",
    "\"openid\":",
  ]) {
    assert.equal(serialized.includes(forbidden), false, `public payment object leaked ${forbidden}`);
  }
}

test("capability manifest makes mainland rails first class while retaining the full Stripe compatibility branch", () => {
  const manifest = chinaPaymentCapabilityManifest();
  assert.deepEqual(manifest.default_provider_order, ["wechat_pay", "alipay", "domestic_bank_card", "stripe"]);
  assert.deepEqual(manifest.first_class_payment_rails, ["wechat_pay", "alipay", "domestic_bank_card"]);
  assert.equal(manifest.default_currency, "CNY");
  assert.equal(manifest.providers.wechat_pay.protocol, "wechat_pay_api_v3");
  assert.equal(manifest.providers.wechat_pay.trade_operation, "v3.pay.transactions.native");
  assert.equal(manifest.providers.wechat_pay.refund_operation, "v3.refund.domestic.refunds.create");
  assert.equal(manifest.providers.alipay.trade_operation, "alipay.trade.page.pay");
  assert.equal(manifest.providers.domestic_bank_card.protocol, "mainland_acquirer_gateway");
  assert.equal(manifest.providers.domestic_bank_card.amount_unit, "fen");
  assert.deepEqual(manifest.providers.domestic_bank_card.allowed_payment_method_flows, ["hosted", "acquirer_token", "provider_reference"]);
  assert.deepEqual(manifest.providers.domestic_bank_card.prohibited_data_collection, ["PAN", "CVC", "OTP"]);
  assert.equal(manifest.compatibility.stripe_preserved, true);
  assert.equal(manifest.compatibility.stripe_branch, "compatibility");
  assert.equal(manifest.compatibility.stripe_capability_reduction, false);
  assert.deepEqual(manifest.compatibility.stripe_cny_payment_methods, ["alipay", "wechat_pay", "card"]);
  assertPublicSafe(manifest);
});

test("CNY trade plans expose provider-specific request shapes without executing", () => {
  const wechat = trade("wechat_pay");
  assert.equal(wechat.request_shape.operation, "v3.pay.transactions.native");
  assert.equal(wechat.request_shape.amount.total, 1888);
  assert.equal(wechat.request_shape.amount.currency, "CNY");
  assert.equal(wechat.hosted_surface, "native_qr");

  const alipay = trade("alipay");
  assert.equal(alipay.request_shape.operation, "alipay.trade.page.pay");
  assert.equal(alipay.request_shape.total_amount, "18.88");
  assert.equal(alipay.request_shape.product_code, "FAST_INSTANT_TRADE_PAY");

  const domesticCard = trade("domestic_bank_card");
  assert.equal(domesticCard.request_shape.operation, "acquirer.orders.create");
  assert.deepEqual(domesticCard.request_shape.amount, { fen: 1888, currency: "CNY" });
  assert.equal(domesticCard.request_shape.payment_method_ref, "provider-ref:acquirer/payment-method-token-1");
  assert.equal(domesticCard.request_shape.provider_account_ref, refs.accountRef);
  assert.equal(domesticCard.request_shape.pan_collected_by_sdk, false);
  assert.equal(domesticCard.request_shape.cvc_collected_by_sdk, false);
  assert.equal(domesticCard.request_shape.otp_collected_by_sdk, false);
  assert.equal(domesticCard.hosted_surface, "hosted_acquirer");

  const stripe = trade("stripe");
  assert.equal(stripe.request_shape.operation, "checkout.sessions.create");
  assert.equal(stripe.request_shape.checkout_mode, "payment");
  assert.equal(stripe.request_shape.line_items[0].price_data.currency, "cny");
  assert.deepEqual(stripe.request_shape.payment_method_types, ["alipay", "wechat_pay", "card"]);

  for (const plan of [wechat, alipay, domesticCard, stripe]) {
    assert.equal(plan.amount.currency, "CNY");
    assert.equal(plan.amount.fen, 1888);
    assert.equal(plan.side_effects.provider_called, false);
    assert.equal(plan.side_effects.network_io_performed, false);
    assert.match(plan.idempotency.request_fingerprint_sha256, /^[a-f0-9]{64}$/u);
    assertPublicSafe(plan);
  }
});

test("trade plans reject non-HTTPS callbacks, unsafe idempotency, raw secrets, card data, and rich metadata", () => {
  assert.throws(() => trade("wechat_pay", { notifyUrl: "http://api.example.test/notify" }), /HTTPS URL/u);
  assert.throws(() => trade("alipay", { idempotencyKey: "short" }), /8-255/u);
  assert.throws(() => trade("stripe", { credentialRef: "sk_test_executoronly123" }), /raw provider secret/u);
  assert.throws(() => trade("stripe", { description: "use 4242 4242 4242 4242" }), /card data/u);
  assert.throws(() => trade("domestic_bank_card", { paymentMethodRef: undefined }), /payment_method_ref/u);
  assert.throws(() => trade("domestic_bank_card", { accountRef: undefined }), /provider account binding/u);
  assert.throws(() => trade("domestic_bank_card", { paymentMethodRef: "6222020202020202020" }), /card data/u);
  assert.throws(() => trade("wechat_pay", { metadata: { payer_openid: "hidden" } }), /sensitive payment field/u);
  assert.throws(() => trade("wechat_pay", { metadata: { nested: { unsafe: true } } }), /public-safe scalars/u);
});

test("notification envelopes retain only digests and header names for all providers", () => {
  const rawBody = Buffer.from('{"event":"trade.success","buyer":"must-not-serialize"}');
  const cases = [
    ["wechat_pay", {
      "Wechatpay-Signature": "private-signature",
      "Wechatpay-Timestamp": "1700000000",
      "Wechatpay-Nonce": "private-nonce",
      "Wechatpay-Serial": "serial-1",
    }],
    ["alipay", { sign: "private-signature", sign_type: "RSA2", app_id: "app-1", trade_no: "trade-1" }],
    ["domestic_bank_card", {
      "X-Acquirer-Signature": "private-signature",
      "X-Acquirer-Timestamp": "1700000000",
      "X-Acquirer-Event-Id": "provider-event-1",
    }],
    ["stripe", { "Stripe-Signature": "t=1,v1=private-signature" }],
  ];
  for (const [provider, headers] of cases) {
    const envelope = buildNotificationEnvelope({
      provider,
      ...scope,
      rawBody,
      headers,
      verified: true,
      verifierCalled: true,
      eventIdRef: `provider-ref:${provider}/event-1`,
      eventType: "trade.success",
      livemode: false,
    });
    assert.equal(envelope.verified, true);
    assert.equal(envelope.payload_sha256, createHash("sha256").update(rawBody).digest("hex"));
    assert.equal(envelope.raw_body_included, false);
    assert.equal(envelope.raw_headers_included, false);
    assert.equal(envelope.signature_header_shape.raw_header_values_included, false);
    const text = JSON.stringify(envelope);
    assert.equal(text.includes("private-signature"), false);
    assert.equal(text.includes("private-nonce"), false);
    assert.equal(text.includes("must-not-serialize"), false);
    assertPublicSafe(envelope);
  }
});

test("notification envelopes fail closed for missing signatures and provider mode mismatch", () => {
  const missing = buildNotificationEnvelope({
    provider: "wechat_pay",
    ...scope,
    rawBody: "{}",
    headers: { "wechatpay-signature": "present" },
    verified: true,
    verifierCalled: true,
  });
  assert.equal(missing.verified, false);
  assert.equal(missing.reason_codes.includes("missing_signature_headers"), true);
  assert.deepEqual(missing.signature_header_shape.missing_headers.sort(), [
    "wechatpay-nonce",
    "wechatpay-serial",
    "wechatpay-timestamp",
  ]);

  const mismatch = buildNotificationEnvelope({
    provider: "alipay",
    mode: "test",
    ...scope,
    rawBody: "{}",
    headers: { sign: "x", sign_type: "RSA2", app_id: "a", trade_no: "t" },
    verified: true,
    livemode: true,
    verifierCalled: true,
  });
  assert.equal(mismatch.verified, false);
  assert.deepEqual(mismatch.reason_codes, ["provider_mode_mismatch"]);
});

test("refund plans cover all mainland rails and Stripe with normalized statuses", () => {
  const common = {
    ...scope,
    credentialRef: refs.credentialRef,
    accountRef: refs.accountRef,
    orderRef: "order-refund-0001",
    refundRef: "refund-0001",
    amountMinor: 500,
    totalAmountMinor: 1888,
    reason: "service adjustment",
    notifyUrl: "https://api.example.test/refunds/notify",
    idempotencyKey: "refund-idempotency-0001",
    metadata: { ticket: "support-17" },
  };
  const wechat = buildRefundPlan({ provider: "wechat_pay", ...common });
  const alipay = buildRefundPlan({ provider: "alipay", ...common });
  const domesticCard = buildRefundPlan({ provider: "domestic_bank_card", ...common });
  const stripe = buildRefundPlan({ provider: "stripe", ...common });
  assert.equal(wechat.request_shape.operation, "v3.refund.domestic.refunds.create");
  assert.deepEqual(wechat.request_shape.amount, { refund: 500, total: 1888, currency: "CNY" });
  assert.equal(alipay.request_shape.operation, "alipay.trade.refund");
  assert.equal(alipay.request_shape.refund_amount, "5.00");
  assert.equal(domesticCard.request_shape.operation, "acquirer.refunds.create");
  assert.deepEqual(domesticCard.request_shape.amount, { refund_fen: 500, total_fen: 1888, currency: "CNY" });
  assert.equal(domesticCard.request_shape.provider_account_ref, refs.accountRef);
  assert.equal(domesticCard.amount.refund_fen, 500);
  assert.equal(stripe.request_shape.operation, "refunds.create");
  assert.equal(stripe.request_shape.amount, 500);
  assert.equal(normalizeRefundStatus("wechat_pay", "REFUND.SUCCESS"), "succeeded");
  assert.equal(normalizeRefundStatus("alipay", "refund_failed"), "failed");
  assert.equal(normalizeRefundStatus("domestic_bank_card", "REFUND_SUCCEEDED"), "succeeded");
  assert.equal(normalizeRefundStatus("stripe", "refund.created"), "processing");
  assert.throws(() => buildRefundPlan({ provider: "wechat_pay", ...common, amountMinor: 2000 }), /must not exceed/u);
});

test("provider account bindings are scoped, reference-only, and require an acquirer for domestic cards", () => {
  const binding = buildProviderAccountBinding({
    provider: "domestic_bank_card",
    ...scope,
    ...refs,
    acquirerRef: "provider-ref:acquirer/mainland-processor",
  });
  assert.equal(binding.envelope_type, "provider_account_binding");
  assert.equal(binding.provider, "domestic_bank_card");
  assert.equal(binding.currency, "CNY");
  assert.equal(binding.amount_unit, "fen");
  assert.equal(binding.account_ref, refs.accountRef);
  assert.equal(binding.acquirer_ref, "provider-ref:acquirer/mainland-processor");
  assert.match(binding.binding_fingerprint_sha256, /^[a-f0-9]{64}$/u);
  assert.equal(binding.pan_collected, false);
  assert.equal(binding.cvc_collected, false);
  assert.equal(binding.otp_collected, false);
  assert.equal(binding.side_effects.network_io_performed, false);
  assertPublicSafe(binding);

  assert.throws(
    () => buildProviderAccountBinding({ provider: "domestic_bank_card", ...scope, ...refs }),
    /requires acquirer_ref/u,
  );
  assert.throws(
    () => buildProviderAccountBinding({
      provider: "domestic_bank_card",
      ...scope,
      ...refs,
      acquirerRef: "provider-ref:acquirer/mainland-processor",
      accountRef: "6222020202020202020",
    }),
    /card data/u,
  );
});

test("trade and refund query plans have provider parity and keep Stripe operations intact", () => {
  const providers = ["wechat_pay", "alipay", "domestic_bank_card", "stripe"];
  const expectedTrade = [
    "v3.pay.transactions.out-trade-no.get",
    "alipay.trade.query",
    "acquirer.orders.query",
    "checkout.sessions.retrieve",
  ];
  const expectedRefund = [
    "v3.refund.domestic.refunds.out-refund-no.get",
    "alipay.trade.fastpay.refund.query",
    "acquirer.refunds.query",
    "refunds.retrieve",
  ];
  providers.forEach((provider, index) => {
    const common = {
      provider,
      ...scope,
      credentialRef: refs.credentialRef,
      accountRef: refs.accountRef,
      orderRef: `order-query-${provider}-0001`,
    };
    const tradeQuery = buildPaymentQueryPlan(common);
    const refundQuery = buildPaymentQueryPlan({ ...common, queryType: "refund", refundRef: `refund-query-${provider}-0001` });
    assert.equal(tradeQuery.operation, expectedTrade[index]);
    assert.equal(tradeQuery.request_shape.operation, expectedTrade[index]);
    assert.equal(refundQuery.operation, expectedRefund[index]);
    assert.equal(refundQuery.request_shape.operation, expectedRefund[index]);
    assert.equal(tradeQuery.currency, "CNY");
    assert.equal(tradeQuery.amount_unit, "fen");
    assert.equal(tradeQuery.side_effects.provider_called, false);
    assertPublicSafe(tradeQuery);
    assertPublicSafe(refundQuery);
  });
});

test("provider events normalize trade and refund states with strict scope and currency", () => {
  const wechat = normalizeProviderEvent({
    provider: "wechat_pay",
    ...scope,
    providerEventId: "wx-event-0001",
    eventType: "TRANSACTION.SUCCESS",
    orderRef: "order-wx-0001",
    amountMinor: 1888,
    occurredAt: "2026-07-10T08:00:00+08:00",
    payloadSha256: "a".repeat(64),
  });
  assert.equal(wechat.event_type, "trade_succeeded");
  assert.equal(wechat.occurred_at, "2026-07-10T00:00:00.000Z");

  const alipay = normalizeProviderEvent({
    provider: "alipay",
    ...scope,
    providerEventId: "ali-event-0001",
    status: "TRADE_CLOSED",
    orderRef: "order-ali-0001",
    occurredAt: "2026-07-10T00:00:00Z",
  });
  assert.equal(alipay.event_type, "trade_closed");

  const stripe = normalizeProviderEvent({
    provider: "stripe",
    ...scope,
    providerEventId: "evt_refund_0001",
    eventType: "charge.refunded",
    refundRef: "re_stripe_0001",
    amountMinor: 500,
    currency: "USD",
    occurredAt: "2026-07-10T00:00:00Z",
  });
  assert.equal(stripe.event_type, "refund_succeeded");
  assert.equal(stripe.refund_status, "succeeded");

  const domesticCard = normalizeProviderEvent({
    provider: "domestic_bank_card",
    ...scope,
    providerEventId: "acquirer-event-0001",
    eventType: "ORDER_PAID",
    orderRef: "order-card-0001",
    amountMinor: 1888,
    occurredAt: "2026-07-10T00:00:00Z",
  });
  assert.equal(domesticCard.event_type, "trade_succeeded");
  assert.deepEqual(domesticCard.amount, { minor: 1888, currency: "CNY" });
  assert.throws(() => normalizeProviderEvent({ ...wechat, tenantId: "", projectId: "" }), /tenant_id and project_id/u);
  assert.throws(() => normalizeProviderEvent({ ...wechat, currency: "USD" }), /currency is not supported/u);
});

test("domestic bank card daily bills reconcile in CNY fen without payment credentials", () => {
  const record = normalizeDailyBillRecord({
    provider: "domestic_bank_card",
    ...scope,
    billDate: "2026-07-10",
    billType: "settlement",
    lineId: "card-bill-line-0001",
    orderRef: "order-card-0001",
    providerTradeRef: "provider-ref:acquirer/trade-1",
    tradeStatus: "SETTLED",
    grossAmountMinor: 1888,
    feeAmountMinor: 8,
    netAmountMinor: 1880,
    occurredAt: "2026-07-10T16:00:00+08:00",
    sourceSha256: "9".repeat(64),
    metadata: { settlement_batch: "batch-1" },
  });
  assert.deepEqual(record.amount, {
    gross_minor: 1888,
    gross_fen: 1888,
    fee_minor: 8,
    fee_fen: 8,
    net_minor: 1880,
    net_fen: 1880,
    currency: "CNY",
  });
  const store = new PaymentReconciliationStore();
  assert.equal(store.ingestDailyBill(record).idempotent_replay, false);
  assert.equal(store.ingestDailyBill(record).idempotent_replay, true);
  assert.equal(store.list(scope).daily_bill_record_count, 1);
  assertPublicSafe(record);
});

test("daily bill records are deterministic, scoped, public safe, and conflict checked", () => {
  const base = {
    provider: "wechat_pay",
    ...scope,
    billDate: "2026-07-10",
    billType: "transaction",
    lineId: "wx-bill-line-0001",
    orderRef: "order-wx-0001",
    providerTradeRef: "provider-ref:wechat/trade-1",
    tradeStatus: "SUCCESS",
    grossAmountMinor: 1888,
    feeAmountMinor: 12,
    netAmountMinor: 1876,
    occurredAt: "2026-07-10T00:01:00Z",
    sourceSha256: "b".repeat(64),
    metadata: { channel: "native" },
  };
  const record = normalizeDailyBillRecord(base);
  assert.match(record.reconciliation_key, /^[a-f0-9]{64}$/u);
  assert.deepEqual(record.amount, {
    gross_minor: 1888,
    gross_fen: 1888,
    fee_minor: 12,
    fee_fen: 12,
    net_minor: 1876,
    net_fen: 1876,
    currency: "CNY",
  });
  assert.equal(record.raw_bill_line_included, false);

  const store = new PaymentReconciliationStore();
  const accepted = store.ingestDailyBill(record);
  const replay = store.ingestDailyBill(record);
  assert.equal(accepted.idempotent_replay, false);
  assert.equal(replay.idempotent_replay, true);
  assert.throws(
    () => store.ingestDailyBill({ ...record, amount: { ...record.amount, net_minor: 1 } }),
    (error) => error instanceof PaymentReconciliationConflictError,
  );
  assert.equal(store.list(scope).daily_bill_record_count, 1);
  assert.equal(store.list({ tenantId: "tenant-other", projectId: "project-other" }).daily_bill_record_count, 0);
});

test("reconciliation event lifecycle is idempotent, conflict aware, and tenant/project isolated", () => {
  let tick = 0;
  const store = new PaymentReconciliationStore({ clock: () => `2026-07-10T00:00:0${tick++}.000Z` });
  const input = {
    provider: "wechat_pay",
    ...scope,
    providerEventId: "wx-event-reconcile-0001",
    eventType: "TRANSACTION.SUCCESS",
    payloadSha256: "c".repeat(64),
    headersSha256: "d".repeat(64),
  };
  const received = store.receiveEvent(input);
  const replay = store.receiveEvent(input);
  assert.equal(received.status, "received");
  assert.equal(received.idempotent_replay, false);
  assert.equal(replay.idempotent_replay, true);
  assert.throws(
    () => store.receiveEvent({ ...input, payloadSha256: "e".repeat(64) }),
    (error) => error instanceof PaymentReconciliationConflictError,
  );

  const verified = store.transitionEvent({ provider: "wechat_pay", ...scope, providerEventId: input.providerEventId, status: "verified" });
  const verifiedReplay = store.transitionEvent({ provider: "wechat_pay", ...scope, providerEventId: input.providerEventId, status: "verified" });
  const applied = store.transitionEvent({ provider: "wechat_pay", ...scope, providerEventId: input.providerEventId, status: "applied" });
  assert.equal(verified.verified_at, "2026-07-10T00:00:01.000Z");
  assert.equal(verifiedReplay.idempotent_replay, true);
  assert.equal(applied.status, "applied");
  assert.throws(
    () => store.transitionEvent({ provider: "wechat_pay", ...scope, providerEventId: input.providerEventId, status: "failed", failureSha256: "f".repeat(64) }),
    /invalid payment reconciliation transition/u,
  );
  assert.equal(store.list(scope).event_count, 1);
  assert.equal(store.list({ tenantId: "tenant-other", projectId: "project-other" }).event_count, 0);
  assert.throws(
    () => store.transitionEvent({ provider: "wechat_pay", tenantId: "tenant-other", projectId: "project-other", providerEventId: input.providerEventId, status: "verified" }),
    /not found for tenant\/project/u,
  );
});

test("failed reconciliation requires a digest and preserves the verified timestamp", () => {
  const store = new PaymentReconciliationStore({ clock: () => "2026-07-10T00:00:00.000Z" });
  const input = {
    provider: "alipay",
    ...scope,
    providerEventId: "ali-event-failed-0001",
    eventType: "TRADE_SUCCESS",
    payloadSha256: "1".repeat(64),
  };
  store.receiveEvent(input);
  store.transitionEvent({ provider: "alipay", ...scope, providerEventId: input.providerEventId, status: "verified" });
  assert.throws(
    () => store.transitionEvent({ provider: "alipay", ...scope, providerEventId: input.providerEventId, status: "failed", failureSha256: "bad" }),
    /lowercase SHA-256/u,
  );
  const failed = store.transitionEvent({
    provider: "alipay",
    ...scope,
    providerEventId: input.providerEventId,
    status: "failed",
    failureSha256: "2".repeat(64),
  });
  assert.equal(failed.status, "failed");
  assert.equal(failed.verified_at, "2026-07-10T00:00:00.000Z");
  assert.equal(failed.failure_sha256, "2".repeat(64));
  assertPublicSafe(failed);
});

test("idempotency registry replays same fingerprint and rejects changed requests within the same scope", () => {
  const registry = new PaymentIdempotencyRegistry();
  const plan = trade("alipay");
  const options = {
    ...scope,
    operation: "trade.create",
    idempotencyKey: "registry-trade-0001",
    request: plan.request_shape,
    result: { accepted: true, provider: "alipay", provider_trade_ref: "provider-ref:alipay/trade-1" },
  };
  const first = registry.register(options);
  const replay = registry.register(options);
  assert.equal(first.idempotent_replay, false);
  assert.equal(replay.idempotent_replay, true);
  assert.throws(
    () => registry.register({ ...options, request: { ...plan.request_shape, total_amount: "99.00" } }),
    (error) => error instanceof PaymentIdempotencyConflictError,
  );

  const otherScope = registry.register({ ...options, tenantId: "tenant-other", projectId: "project-other" });
  assert.equal(otherScope.idempotent_replay, false);
});

test("public serializer rejects sensitive result fields even when callers try to register them", () => {
  const registry = new PaymentIdempotencyRegistry();
  assert.throws(
    () => registry.register({
      ...scope,
      operation: "trade.create",
      idempotencyKey: "registry-unsafe-0001",
      request: { operation: "safe" },
      result: { accepted: true, private_key: "provider secret" },
    }),
    (error) => error instanceof ChinaPaymentContractError && /sensitive field/u.test(error.message),
  );
});
