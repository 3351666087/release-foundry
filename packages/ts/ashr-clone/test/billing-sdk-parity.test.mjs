import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { SaaSIngestionClient } from "../dist/saas.js";

const contract = JSON.parse(await readFile(path.resolve("../../../tests/a1/fixtures/billing_sdk_parity_contract.json"), "utf8"));

function assertPublicSafe(value) {
  const text = JSON.stringify(value);
  for (const fragment of contract.forbidden_public_fragments) assert.equal(text.includes(fragment), false, `${fragment} leaked into public billing response`);
}

function resultKeys(envelope) {
  assert.match(envelope.client_version, /^ashr\.clone\..*saas_ingestion_client\.v1$/u);
  return new Set(Object.keys(envelope.result));
}

function assertContainsAll(actual, expected) {
  for (const item of expected) assert.equal(actual.has(item), true, `missing public field ${item}`);
}

function billingFlow(client) {
  client.bootstrapProject({ tenantName: "Tenant", projectName: "Project", tenantId: "tenant_ts_bill_sdk", projectId: "project_ts_bill_sdk" });
  const checkout = client.billingCheckoutPlan("tenant_ts_bill_sdk", "project_ts_bill_sdk", {
    customerRef: "cus_test_123",
    price: { lookupKey: "team", unitAmountMinor: 9900, currency: "usd" },
    successUrl: "https://app.ashr-clone.invalid/billing/success",
    cancelUrl: "https://app.ashr-clone.invalid/billing/cancel",
    providerConfig: { provider: "stripe", mode: "test", secretRef: "env:STRIPE_TEST_REF" },
    metadata: { safe_note: "checkout" },
    idempotencyKey: "checkout_ts_bill_sdk",
  });
  const portal = client.billingPortalPlan("tenant_ts_bill_sdk", "project_ts_bill_sdk", {
    customerRef: "cus_test_123",
    returnUrl: "https://app.ashr-clone.invalid/billing",
    providerConfig: { provider: "stripe", mode: "test", secretRef: "env:STRIPE_TEST_REF" },
    idempotencyKey: "portal_ts_bill_sdk",
  });
  const webhook = client.billingWebhookIngest("tenant_ts_bill_sdk", "project_ts_bill_sdk", {
    provider: "stripe",
    mode: "test",
    eventType: "invoice.paid",
    eventId: "evt_ts_bill_sdk",
    payloadSha256: "a".repeat(64),
    signatureHeaderPresent: true,
    webhookSecretRef: "env:STRIPE_WEBHOOK_REF_TEST",
    customerRef: "cus_test_123",
    amountMinor: 9900,
    currency: "usd",
    invoiceRef: "in_ts_bill_sdk",
    metadata: { billing_period: "2026-07" },
  });
  const ledger = client.billingLedger("tenant_ts_bill_sdk", "project_ts_bill_sdk");
  return { checkout_plan: checkout, portal_plan: portal, webhook_ingest: webhook, ledger_readback: ledger };
}

test("TS SaaS billing client matches shared operation contract", () => {
  for (const operation of Object.values(contract.operations)) {
    assert.equal(typeof SaaSIngestionClient.prototype[operation.ts_client_method], "function");
    assert.equal(typeof SaaSIngestionClient.prototype[operation.ts_http_method], "function");
  }

  const envelopes = billingFlow(new SaaSIngestionClient());
  for (const [key, envelope] of Object.entries(envelopes)) {
    const operation = contract.operations[key];
    assert.equal(envelope.operation, operation.operation);
    assertContainsAll(resultKeys(envelope), operation.required_result_fields);
    assertPublicSafe(envelope);
  }

  assert.equal(envelopes.checkout_plan.result.provider_request.operation, "checkout.sessions.create");
  assert.equal(envelopes.portal_plan.result.provider_request.operation, "billing_portal.sessions.create");
  assert.equal(envelopes.webhook_ingest.result.ingest_status, "accepted");
  assert.equal(envelopes.ledger_readback.result.ledger_event_count, 1);
  assert.deepEqual(envelopes.ledger_readback.result.totals_by_currency_minor, { usd: 9900 });
});

test("TS SaaS billing HTTP routes match shared contract", async () => {
  const calls = [];
  const client = SaaSIngestionClient.forBaseUrl("https://api.ashr-clone.invalid", {
    fetch: async (url, options = {}) => {
      calls.push({ url: String(url), method: options.method, body: JSON.parse(String(options.body ?? "{}")) });
      return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true }) };
    },
  });

  await client.billingCheckoutPlanHttp("tenant route", "project route", { customerRef: "cus", price: { lookupKey: "team", unitAmountMinor: 1000, currency: "usd" }, successUrl: "https://app.ashr-clone.invalid/success", cancelUrl: "https://app.ashr-clone.invalid/cancel", authKeyId: "key_bill" });
  await client.billingPortalPlanHttp("tenant route", "project route", { customerRef: "cus", returnUrl: "https://app.ashr-clone.invalid/billing", authKeyId: "key_bill" });
  await client.billingWebhookIngestHttp("tenant route", "project route", { provider: "stripe", mode: "test", eventType: "invoice.paid", eventId: "evt", payloadSha256: "b".repeat(64), signatureHeaderPresent: true, webhookSecretRef: "env:STRIPE_WEBHOOK_REF_TEST", authKeyId: "key_bill" });
  await client.billingLedgerHttp("tenant route", "project route", { authKeyId: "key_bill" });

  assert.equal(calls.length, Object.keys(contract.operations).length);
  for (const [index, operation] of Object.values(contract.operations).entries()) {
    const call = calls[index];
    const parsed = new URL(call.url);
    assert.equal(call.method, operation.route.method);
    assert.equal(`${parsed.origin}${parsed.pathname}`, `https://api.ashr-clone.invalid${operation.route.path.replace("{project_id}", "project%20route")}`);
    const bodyOrQuery = call.method === "GET" ? Object.fromEntries(parsed.searchParams.entries()) : call.body;
    assert.equal(bodyOrQuery.tenant_id, "tenant route");
    assert.equal(bodyOrQuery.auth_key_id, "key_bill");
  }
});
