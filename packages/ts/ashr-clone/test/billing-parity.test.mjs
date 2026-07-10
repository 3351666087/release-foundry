import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BILLING_SCHEMA_VERSION,
  BillingContractError,
  BillingLedger,
  billingEvidenceSnapshot,
  billingProviderManifest,
  buildBillingPortalPlan,
  buildCheckoutSessionPlan,
  verifyBillingWebhookEnvelope,
} from "../dist/billing.js";

function text(value) {
  return JSON.stringify(value, Object.keys(value).sort());
}

test("TS billing checkout and portal plans mirror Python public-safe contracts", () => {
  const checkout = buildCheckoutSessionPlan({
    tenantId: "tenant_bill",
    projectId: "project_bill",
    customerRef: "cus_test_123",
    price: { lookupKey: "ashr_scale_monthly", unitAmountMinor: 9900, currency: "usd", includedUnits: 10000 },
    successUrl: "https://app.ashr-clone.invalid/billing/success",
    cancelUrl: "https://app.ashr-clone.invalid/billing/cancel",
    providerConfig: { provider: "stripe", mode: "test", secretRef: "env:STRIPE_TEST_REF" },
    usageRollup: { tenant_id: "tenant_bill", project_id: "project_bill", billing_period: "2026-07", operation_totals: { "sdk.submit": 12 }, billable_units: 12 },
  });
  assert.equal(checkout.schema_version, BILLING_SCHEMA_VERSION);
  assert.equal(checkout.provider, "stripe");
  assert.equal(checkout.provider_request.operation, "checkout.sessions.create");
  assert.deepEqual(checkout.provider_request.payment_method_types, ["card", "alipay", "wechat_pay"]);
  assert.equal(checkout.side_effects.provider_called, false);
  assert.equal(text(checkout).includes("sk_test"), false);

  const portal = buildBillingPortalPlan({
    tenantId: "tenant_bill",
    projectId: "project_bill",
    customerRef: "cus_test_123",
    returnUrl: "https://app.ashr-clone.invalid/billing",
    providerConfig: { provider: "stripe", mode: "test", secretRef: "env:STRIPE_TEST_REF" },
  });
  assert.equal(portal.plan_type, "billing_portal");
  assert.equal(portal.provider_request.operation, "billing_portal.sessions.create");
});

test("TS billing treats WeChat and Alipay hosted rails as first-class providers", () => {
  const wechat = buildCheckoutSessionPlan({
    tenantId: "tenant_cn",
    projectId: "project_cn",
    customerRef: "wechat-openid-ref",
    price: { lookupKey: "ashr_cn_team_monthly", unitAmountMinor: 68800, currency: "cny" },
    successUrl: "https://app.ashr-clone.invalid/cn/success",
    cancelUrl: "https://app.ashr-clone.invalid/cn/cancel",
    providerConfig: { provider: "wechat", mode: "test", secretRef: "vault:wechat/test/mch_private_key", accountRef: "mch:demo" },
  });
  const alipay = buildCheckoutSessionPlan({
    tenantId: "tenant_cn",
    projectId: "project_cn",
    customerRef: "alipay-user-ref",
    price: { lookupKey: "ashr_cn_team_monthly", unitAmountMinor: 68800, currency: "cny" },
    successUrl: "https://app.ashr-clone.invalid/cn/success",
    cancelUrl: "https://app.ashr-clone.invalid/cn/cancel",
    providerConfig: { provider: "alipay_plus", mode: "test", secretRef: "vault:alipay/test/app_private_key", accountRef: "alipay-app:demo" },
  });
  assert.equal(wechat.provider, "wechat_pay");
  assert.equal(wechat.provider_request.trade_type, "NATIVE");
  assert.equal(alipay.provider, "alipay");
  assert.equal(alipay.provider_request.total_amount, "688.00");
});

test("TS billing guardrails reject live ambiguity raw secrets cards and insecure urls", () => {
  const base = {
    tenantId: "tenant_secret",
    projectId: "project_secret",
    customerRef: "cus_secret",
    price: { lookupKey: "team", unitAmountMinor: 1000, currency: "usd" },
    successUrl: "https://app.ashr-clone.invalid/success",
    cancelUrl: "https://app.ashr-clone.invalid/cancel",
  };
  assert.throws(() => buildCheckoutSessionPlan({ ...base, providerConfig: { provider: "stripe", mode: "live", secretRef: "env:STRIPE_LIVE_REF" } }), BillingContractError);
  assert.throws(() => buildCheckoutSessionPlan({ ...base, providerConfig: { provider: "stripe", mode: "test", secretRef: "sk_test_should_not_be_here123456" } }), BillingContractError);
  assert.throws(() => buildCheckoutSessionPlan({ ...base, metadata: { card_number: "4242 4242 4242 4242" }, providerConfig: { provider: "stripe", mode: "test" } }), BillingContractError);
  assert.throws(() => buildCheckoutSessionPlan({ ...base, successUrl: "http://localhost/success", providerConfig: { provider: "stripe", mode: "test" } }), BillingContractError);
  const live = buildCheckoutSessionPlan({ ...base, providerConfig: { provider: "stripe", mode: "live", secretRef: "env:STRIPE_LIVE_REF", liveModeAck: true } });
  assert.equal(live.mode, "live");
  assert.equal(live.side_effects.real_charge_possible, false);
});

test("TS billing ledger ingests provider webhooks idempotently", () => {
  const ledger = new BillingLedger();
  ledger.upsertBillingAccount({ tenantId: "tenant_bill", projectId: "project_bill", provider: "stripe", mode: "test", customerRef: "cus_test_123", accountRef: "acct_test_ref" });
  const envelope = verifyBillingWebhookEnvelope({
    provider: "stripe",
    mode: "test",
    eventType: "invoice.paid",
    eventId: "evt_invoice_paid_1",
    tenantId: "tenant_bill",
    projectId: "project_bill",
    payloadSha256: "c".repeat(64),
    signatureHeaderPresent: true,
    webhookSecretRef: "env:STRIPE_WEBHOOK_REF_TEST",
  });
  const accepted = ledger.ingestProviderWebhook({ envelope, customerRef: "cus_test_123", amountMinor: 9900, currency: "usd", invoiceRef: "in_test_123" });
  const duplicate = ledger.ingestProviderWebhook({ envelope, customerRef: "cus_test_123", amountMinor: 9900, currency: "usd", invoiceRef: "in_test_123" });
  const conflict = ledger.ingestProviderWebhook({ envelope: { ...envelope, payload_sha256: "d".repeat(64) }, customerRef: "cus_test_123" });

  assert.equal(accepted.ingest_status, "accepted");
  assert.equal(accepted.ledger_event_type, "invoice_paid");
  assert.equal(duplicate.ingest_status, "duplicate");
  assert.equal(duplicate.ledger_mutation_count, 0);
  assert.equal(conflict.ingest_status, "conflict");
  const publicLedger = ledger.publicLedger({ tenantId: "tenant_bill", projectId: "project_bill" });
  assert.equal(publicLedger.ledger_event_count, 1);
  assert.equal(publicLedger.provider_event_count, 1);
  assert.deepEqual(publicLedger.totals_by_currency_minor, { usd: 9900 });
  const evidence = billingEvidenceSnapshot({ ledger, tenantId: "tenant_bill", projectId: "project_bill" });
  assert.match(evidence.billing_snapshot_sha256, /^[a-f0-9]{64}$/);
  assert.equal(text(publicLedger).includes("sk_test"), false);
  assert.equal(text(publicLedger).includes("whsec"), false);
});

test("TS billing ledger reconciles usage and scopes tenant readback", () => {
  const ledger = new BillingLedger();
  ledger.reconcileUsageRollup({ tenant_id: "tenant_a", project_id: "project_a", billing_period: "2026-07", operation_totals: { "sdk.submit": 7, "trace.ingest": 13 }, billable_units: 20 }, { customerRef: "cus_a" });
  ledger.reconcileUsageRollup({ tenant_id: "tenant_b", project_id: "project_b", billing_period: "2026-07", operation_totals: { "sdk.submit": 99 }, billable_units: 99 }, { customerRef: "cus_b" });
  const a = ledger.publicLedger({ tenantId: "tenant_a", projectId: "project_a" });
  const b = ledger.publicLedger({ tenantId: "tenant_b", projectId: "project_b" });
  assert.equal(a.ledger_event_count, 1);
  assert.equal(a.usage_units, 20);
  assert.equal(b.usage_units, 99);
  assert.equal(JSON.stringify(a).includes("cus_b"), false);
  assert.equal(JSON.stringify(a).includes("tenant_b"), false);
});

test("TS billing manifest names commercial payment rails", () => {
  const manifest = billingProviderManifest();
  assert.deepEqual(new Set(manifest.providers), new Set(["stripe", "wechat_pay", "alipay"]));
  assert.deepEqual(manifest.payment_methods.stripe, ["card", "alipay", "wechat_pay"]);
});