import { createHash } from "node:crypto";

export type BillingJsonRecord = Record<string, unknown>;

export const BILLING_SCHEMA_VERSION = "ashr.clone.billing_provider_contract.v1";
export const SUPPORTED_BILLING_PROVIDERS = ["alipay", "stripe", "wechat_pay"] as const;
export const SUPPORTED_BILLING_MODES = ["live", "test"] as const;
export const SUPPORTED_BILLING_CURRENCIES = ["cny", "usd"] as const;
export const SUPPORTED_PAYMENT_METHODS: Record<string, string[]> = {
  stripe: ["card", "alipay", "wechat_pay"],
  wechat_pay: ["wechat_pay"],
  alipay: ["alipay"],
};

const secretKeyRe = /\b(?:sk|rk|whsec)_(?:test|live)_[A-Za-z0-9]{8,}\b/;
const cardNumberRe = /(?:\d[ -]*?){13,19}/;
const ledgerEventTypes = new Set(["checkout_created", "invoice_paid", "refund_created", "subscription_canceled", "usage_reconciled"]);
const providerEventTypes: Record<string, string> = {
  "checkout.session.completed": "checkout_created",
  "checkout.session.async_payment_succeeded": "checkout_created",
  "invoice.paid": "invoice_paid",
  "charge.refunded": "refund_created",
  "refund.created": "refund_created",
  "customer.subscription.deleted": "subscription_canceled",
  "wechat_pay.transaction.success": "invoice_paid",
  "wechat_pay.refund.success": "refund_created",
  "alipay.trade.success": "invoice_paid",
  "alipay.trade.refund.success": "refund_created",
  "ashr.usage.reconciled": "usage_reconciled",
};

export class BillingContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BillingContractError";
  }
}

export interface BillingPrice extends BillingJsonRecord {
  lookupKey?: string;
  lookup_key?: string;
  price_lookup_key?: string;
  unitAmountMinor?: number;
  unit_amount_minor?: number;
  currency?: string;
  interval?: string;
  metered?: boolean;
  includedUnits?: number;
  included_units?: number;
}

export interface BillingProviderConfig extends BillingJsonRecord {
  provider?: string;
  mode?: string;
  secretRef?: string;
  secret_ref?: string;
  webhookSecretRef?: string;
  webhook_secret_ref?: string;
  accountRef?: string;
  account_ref?: string;
  liveModeAck?: boolean;
  live_mode_ack?: boolean;
  allowedPaymentMethods?: string[];
  allowed_payment_methods?: string[];
}

export interface BillingLedgerEventInput extends BillingJsonRecord {
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  eventType?: string;
  event_type?: string;
  amountMinor?: number;
  amount_minor?: number;
  currency?: string;
  provider?: string;
  mode?: string;
  providerEventId?: string;
  provider_event_id?: string;
  customerRef?: string;
  customer_ref?: string;
  invoiceRef?: string;
  invoice_ref?: string;
  usageUnits?: number;
  usage_units?: number;
  metadata?: BillingJsonRecord;
  ledgerEventId?: string;
  ledger_event_id?: string;
}

export function billingProviderManifest(): BillingJsonRecord {
  return {
    schema_version: BILLING_SCHEMA_VERSION,
    providers: [...SUPPORTED_BILLING_PROVIDERS].sort(),
    modes: [...SUPPORTED_BILLING_MODES].sort(),
    currencies: [...SUPPORTED_BILLING_CURRENCIES].sort(),
    payment_methods: cloneJson(SUPPORTED_PAYMENT_METHODS),
    live_mode_guardrails: [
      "live mode requires live_mode_ack",
      "live mode requires secret_ref indirection",
      "raw provider secrets are rejected",
      "raw card numbers are rejected",
      "plans do not call providers until an executor with explicit credentials is wired",
    ],
  };
}

export function buildCheckoutSessionPlan(options: {
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  customerRef?: string;
  customer_ref?: string;
  price: BillingPrice;
  successUrl?: string;
  success_url?: string;
  cancelUrl?: string;
  cancel_url?: string;
  providerConfig?: BillingProviderConfig;
  provider_config?: BillingProviderConfig;
  usageRollup?: BillingJsonRecord;
  usage_rollup?: BillingJsonRecord;
  metadata?: BillingJsonRecord;
  quantity?: number;
  idempotencyKey?: string;
  idempotency_key?: string;
}): BillingJsonRecord {
  const tenantId = stringValue(options.tenantId ?? options.tenant_id);
  const projectId = stringValue(options.projectId ?? options.project_id);
  const customerRef = stringValue(options.customerRef ?? options.customer_ref);
  validateTenantProject(tenantId, projectId);
  const config = normalizeProviderConfig(options.providerConfig ?? options.provider_config ?? { provider: "stripe", mode: "test", secret_ref: "env:STRIPE_TEST_REF" });
  const price = normalizePrice(options.price);
  const successUrl = stringValue(options.successUrl ?? options.success_url);
  const cancelUrl = stringValue(options.cancelUrl ?? options.cancel_url);
  rejectSensitivePayload({ metadata: options.metadata, customerRef, successUrl, cancelUrl });
  if (!successUrl.startsWith("https://") || !cancelUrl.startsWith("https://")) throw new BillingContractError("checkout redirect urls must be https");
  const quantity = Number(options.quantity ?? 1);
  if (!Number.isInteger(quantity) || quantity < 1) throw new BillingContractError("quantity must be >= 1");
  const idempotencyKey = stringValue(options.idempotencyKey ?? options.idempotency_key, "");
  const planId = planIdFor("checkout", tenantId, projectId, customerRef, price.lookup_key, config.provider, config.mode, idempotencyKey);
  return assertPublicSafe({
    schema_version: BILLING_SCHEMA_VERSION,
    plan_type: "checkout_session",
    plan_id: planId,
    provider: config.provider,
    mode: config.mode,
    tenant_id: tenantId,
    project_id: projectId,
    customer_ref: customerRef,
    price,
    quantity,
    currency: price.currency,
    payment_methods: config.allowed_payment_methods,
    success_url: successUrl,
    cancel_url: cancelUrl,
    metadata: publicMetadata(options.metadata),
    usage_rollup: publicUsageRollup(options.usageRollup ?? options.usage_rollup, tenantId, projectId),
    provider_request: providerCheckoutRequest(config, price, tenantId, projectId, customerRef, quantity),
    side_effects: { provider_called: false, checkout_or_portal_called: false, real_charge_possible: false },
    created_at: utcNow(),
    idempotency_key: idempotencyKey || planId,
  });
}

export function buildBillingPortalPlan(options: {
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  customerRef?: string;
  customer_ref?: string;
  returnUrl?: string;
  return_url?: string;
  providerConfig?: BillingProviderConfig;
  provider_config?: BillingProviderConfig;
  idempotencyKey?: string;
  idempotency_key?: string;
}): BillingJsonRecord {
  const tenantId = stringValue(options.tenantId ?? options.tenant_id);
  const projectId = stringValue(options.projectId ?? options.project_id);
  const customerRef = stringValue(options.customerRef ?? options.customer_ref);
  const returnUrl = stringValue(options.returnUrl ?? options.return_url);
  validateTenantProject(tenantId, projectId);
  rejectSensitivePayload({ customerRef, returnUrl });
  if (!returnUrl.startsWith("https://")) throw new BillingContractError("billing portal return_url must be https");
  const config = normalizeProviderConfig(options.providerConfig ?? options.provider_config ?? { provider: "stripe", mode: "test", secret_ref: "env:STRIPE_TEST_REF" });
  if (config.provider !== "stripe") throw new BillingContractError("billing portal is currently only available through stripe");
  const idempotencyKey = stringValue(options.idempotencyKey ?? options.idempotency_key, "");
  const planId = planIdFor("portal", tenantId, projectId, customerRef, config.provider, config.mode, idempotencyKey);
  return assertPublicSafe({
    schema_version: BILLING_SCHEMA_VERSION,
    plan_type: "billing_portal",
    plan_id: planId,
    provider: config.provider,
    mode: config.mode,
    tenant_id: tenantId,
    project_id: projectId,
    customer_ref: customerRef,
    return_url: returnUrl,
    provider_request: { provider: "stripe", operation: "billing_portal.sessions.create", customer: customerRef, return_url: returnUrl, secret_ref: config.secret_ref },
    side_effects: { provider_called: false, checkout_or_portal_called: false, real_charge_possible: false },
    created_at: utcNow(),
    idempotency_key: idempotencyKey || planId,
  });
}

export function verifyBillingWebhookEnvelope(options: {
  provider: string;
  mode: string;
  eventType?: string;
  event_type?: string;
  eventId?: string;
  event_id?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  payloadSha256?: string;
  payload_sha256?: string;
  signatureHeaderPresent?: boolean;
  signature_header_present?: boolean;
  webhookSecretRef?: string;
  webhook_secret_ref?: string;
  livemode?: boolean;
}): BillingJsonRecord {
  const provider = normalizeProvider(options.provider);
  const mode = normalizeMode(options.mode);
  const tenantId = stringValue(options.tenantId ?? options.tenant_id);
  const projectId = stringValue(options.projectId ?? options.project_id);
  validateTenantProject(tenantId, projectId);
  const payloadSha256 = stringValue(options.payloadSha256 ?? options.payload_sha256).toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(payloadSha256)) throw new BillingContractError("payload_sha256 must be a sha256 hex digest");
  const failures: BillingJsonRecord[] = [];
  const signaturePresent = Boolean(options.signatureHeaderPresent ?? options.signature_header_present);
  if (!signaturePresent) failures.push({ reason: "missing_signature_header" });
  const webhookSecretRef = stringValue(options.webhookSecretRef ?? options.webhook_secret_ref, "");
  if (mode === "live" && !webhookSecretRef) failures.push({ reason: "missing_live_webhook_secret_ref" });
  if (mode === "test" && Boolean(options.livemode)) failures.push({ reason: "live_event_received_in_test_mode" });
  return assertPublicSafe({
    schema_version: BILLING_SCHEMA_VERSION,
    plan_type: "webhook_envelope_verification",
    provider,
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    event_type: stringValue(options.eventType ?? options.event_type),
    event_id: stringValue(options.eventId ?? options.event_id),
    payload_sha256: payloadSha256,
    signature_header_present: signaturePresent,
    webhook_secret_ref: webhookSecretRef || undefined,
    verified: failures.length === 0,
    failures,
    raw_payload_included: false,
    secret_value_present: false,
    created_at: utcNow(),
  });
}

export class BillingLedger {
  readonly ledgerEvents: BillingJsonRecord[] = [];
  readonly providerEvents = new Map<string, BillingJsonRecord>();
  readonly billingAccounts = new Map<string, BillingJsonRecord>();

  upsertBillingAccount(options: { tenantId?: string; tenant_id?: string; projectId?: string; project_id?: string; customerRef?: string; customer_ref?: string; provider: string; mode?: string; accountRef?: string; account_ref?: string; metadata?: BillingJsonRecord }): BillingJsonRecord {
    const tenantId = stringValue(options.tenantId ?? options.tenant_id);
    const projectId = stringValue(options.projectId ?? options.project_id);
    const provider = normalizeProvider(options.provider);
    const mode = normalizeMode(options.mode ?? "test");
    const customerRef = stringValue(options.customerRef ?? options.customer_ref);
    const accountRef = stringValue(options.accountRef ?? options.account_ref, "");
    validateTenantProject(tenantId, projectId);
    rejectSensitivePayload({ customerRef, accountRef, metadata: options.metadata });
    const key = accountKey(tenantId, projectId, provider, mode, customerRef);
    const existing = this.billingAccounts.get(key);
    const record = assertPublicSafe({
      schema_version: BILLING_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      provider,
      mode,
      customer_ref: customerRef,
      account_ref: accountRef || undefined,
      metadata: publicMetadata(options.metadata),
      created_at: existing?.created_at ?? utcNow(),
      updated_at: utcNow(),
      raw_secret_present: false,
      raw_payload_included: false,
    });
    this.billingAccounts.set(key, record);
    return cloneJson(record);
  }

  appendLedgerEvent(input: BillingLedgerEventInput): BillingJsonRecord {
    const tenantId = stringValue(input.tenantId ?? input.tenant_id);
    const projectId = stringValue(input.projectId ?? input.project_id);
    validateTenantProject(tenantId, projectId);
    const eventType = normalizeLedgerEventType(stringValue(input.eventType ?? input.event_type));
    const provider = normalizeProvider(stringValue(input.provider ?? "stripe"));
    const mode = normalizeMode(stringValue(input.mode ?? "test"));
    const currency = stringValue(input.currency ?? "usd").toLowerCase();
    if (!SUPPORTED_BILLING_CURRENCIES.includes(currency as typeof SUPPORTED_BILLING_CURRENCIES[number])) throw new BillingContractError(`unsupported currency: ${currency}`);
    const amountMinor = Number(input.amountMinor ?? input.amount_minor ?? 0);
    if (amountMinor < 0 && eventType !== "refund_created") throw new BillingContractError("negative amounts are only allowed for refunds");
    const customerRef = stringValue(input.customerRef ?? input.customer_ref, "");
    const invoiceRef = stringValue(input.invoiceRef ?? input.invoice_ref, "");
    rejectSensitivePayload({ customerRef, invoiceRef, metadata: input.metadata });
    const providerEventId = stringValue(input.providerEventId ?? input.provider_event_id, "");
    const ledgerEventId = stringValue(input.ledgerEventId ?? input.ledger_event_id, "") || ledgerEventIdFor(tenantId, projectId, eventType, provider, mode, providerEventId, this.ledgerEvents.length);
    const record = assertPublicSafe({
      schema_version: BILLING_SCHEMA_VERSION,
      ledger_event_id: ledgerEventId,
      tenant_id: tenantId,
      project_id: projectId,
      event_type: eventType,
      provider,
      mode,
      provider_event_id: providerEventId || undefined,
      customer_ref: customerRef || undefined,
      invoice_ref: invoiceRef || undefined,
      amount_minor: amountMinor,
      currency,
      usage_units: Number(input.usageUnits ?? input.usage_units ?? 0),
      metadata: publicMetadata(input.metadata),
      raw_payload_included: false,
      secret_value_present: false,
      created_at: utcNow(),
    });
    this.ledgerEvents.push(record);
    return cloneJson(record);
  }

  ingestProviderWebhook(options: { envelope: BillingJsonRecord; customerRef?: string; customer_ref?: string; amountMinor?: number; amount_minor?: number; currency?: string; invoiceRef?: string; invoice_ref?: string; usageUnits?: number; usage_units?: number; metadata?: BillingJsonRecord }): BillingJsonRecord {
    const envelope = options.envelope;
    if (!envelope.verified) throw new BillingContractError("cannot ingest unverified billing webhook envelope");
    const provider = normalizeProvider(stringValue(envelope.provider));
    const mode = normalizeMode(stringValue(envelope.mode));
    const tenantId = stringValue(envelope.tenant_id);
    const projectId = stringValue(envelope.project_id);
    const eventId = stringValue(envelope.event_id);
    const payloadSha256 = stringValue(envelope.payload_sha256).toLowerCase();
    const eventType = stringValue(envelope.event_type);
    if (!eventId) throw new BillingContractError("provider event_id is required");
    if (!/^[a-f0-9]{64}$/.test(payloadSha256)) throw new BillingContractError("provider payload_sha256 must be a sha256 hex digest");
    const key = providerEventKey(provider, mode, tenantId, projectId, eventId);
    const existing = this.providerEvents.get(key);
    if (existing) {
      if (existing.payload_sha256 !== payloadSha256) return assertPublicSafe({ ...existing, ingest_status: "conflict", conflict_payload_sha256: payloadSha256, ledger_mutation_count: 0 });
      return assertPublicSafe({ ...existing, ingest_status: "duplicate", ledger_mutation_count: 0 });
    }
    const ledgerEventType = providerEventTypes[eventType] ?? (eventType.startsWith("ashr.usage") ? "usage_reconciled" : "checkout_created");
    const ledger = this.appendLedgerEvent({
      tenantId,
      projectId,
      eventType: ledgerEventType,
      provider,
      mode,
      providerEventId: eventId,
      customerRef: options.customerRef ?? options.customer_ref,
      invoiceRef: options.invoiceRef ?? options.invoice_ref,
      amountMinor: options.amountMinor ?? options.amount_minor ?? 0,
      currency: options.currency ?? "usd",
      usageUnits: options.usageUnits ?? options.usage_units ?? 0,
      metadata: options.metadata,
    });
    const record = assertPublicSafe({
      schema_version: BILLING_SCHEMA_VERSION,
      provider_event_key: key,
      provider,
      mode,
      tenant_id: tenantId,
      project_id: projectId,
      event_id: eventId,
      event_type: eventType,
      payload_sha256: payloadSha256,
      ledger_event_id: ledger.ledger_event_id,
      ledger_event_type: ledger.event_type,
      ingest_status: "accepted",
      ledger_mutation_count: 1,
      raw_payload_included: false,
      secret_value_present: false,
      created_at: utcNow(),
    });
    this.providerEvents.set(key, record);
    return cloneJson(record);
  }

  reconcileUsageRollup(usageRollup: BillingJsonRecord, options: { provider?: string; mode?: string; customerRef?: string; customer_ref?: string; billingPeriod?: string; billing_period?: string } = {}): BillingJsonRecord {
    const tenantId = stringValue(usageRollup.tenant_id);
    const projectId = stringValue(usageRollup.project_id);
    const period = stringValue(options.billingPeriod ?? options.billing_period ?? usageRollup.billing_period ?? "unperiodized");
    return this.appendLedgerEvent({
      tenantId,
      projectId,
      eventType: "usage_reconciled",
      provider: options.provider ?? "stripe",
      mode: options.mode ?? "test",
      providerEventId: `usage:${tenantId}:${projectId}:${period}`,
      customerRef: options.customerRef ?? options.customer_ref,
      usageUnits: Number(usageRollup.billable_units ?? 0),
      metadata: { billing_period: period, operation_totals: isRecord(usageRollup.operation_totals) ? usageRollup.operation_totals : {} },
    });
  }

  publicLedger(options: { tenantId?: string; tenant_id?: string; projectId?: string; project_id?: string }): BillingJsonRecord {
    const tenantId = stringValue(options.tenantId ?? options.tenant_id);
    const projectId = stringValue(options.projectId ?? options.project_id);
    const ledgerEvents = this.ledgerEvents.filter((item) => item.tenant_id === tenantId && item.project_id === projectId).map(cloneJson);
    const providerEvents = [...this.providerEvents.values()].filter((item) => item.tenant_id === tenantId && item.project_id === projectId).map(cloneJson);
    const billingAccounts = [...this.billingAccounts.values()].filter((item) => item.tenant_id === tenantId && item.project_id === projectId).map(cloneJson);
    const totals: Record<string, number> = {};
    let usageUnits = 0;
    for (const event of ledgerEvents) {
      const currency = stringValue(event.currency ?? "usd");
      totals[currency] = (totals[currency] ?? 0) + Number(event.amount_minor ?? 0);
      usageUnits += Number(event.usage_units ?? 0);
    }
    return assertPublicSafe({
      schema_version: BILLING_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      ledger_events: ledgerEvents,
      provider_events: providerEvents,
      billing_accounts: billingAccounts,
      totals_by_currency_minor: totals,
      usage_units: usageUnits,
      ledger_event_count: ledgerEvents.length,
      provider_event_count: providerEvents.length,
      raw_payload_included: false,
      secret_value_present: false,
    });
  }
}

export function billingEvidenceSnapshot(options: { ledger: BillingLedger; tenantId?: string; tenant_id?: string; projectId?: string; project_id?: string }): BillingJsonRecord {
  const tenantId = stringValue(options.tenantId ?? options.tenant_id);
  const projectId = stringValue(options.projectId ?? options.project_id);
  const snapshot = options.ledger.publicLedger({ tenantId, projectId });
  return assertPublicSafe({
    schema_version: "ashr.clone.billing_evidence_snapshot.v1",
    tenant_id: tenantId,
    project_id: projectId,
    billing_snapshot_sha256: sha256(JSON.stringify(sortJson(snapshot))),
    ledger_event_count: snapshot.ledger_event_count,
    provider_event_count: snapshot.provider_event_count,
    totals_by_currency_minor: snapshot.totals_by_currency_minor,
    usage_units: snapshot.usage_units,
    raw_payload_included: false,
    secret_value_present: false,
  });
}

function normalizeProviderConfig(value: BillingProviderConfig): BillingJsonRecord {
  const provider = normalizeProvider(stringValue(value.provider ?? "stripe"));
  const mode = normalizeMode(stringValue(value.mode ?? "test"));
  const secretRef = stringValue(value.secretRef ?? value.secret_ref, "");
  const webhookSecretRef = stringValue(value.webhookSecretRef ?? value.webhook_secret_ref, "");
  const accountRef = stringValue(value.accountRef ?? value.account_ref, "");
  for (const ref of [secretRef, webhookSecretRef, accountRef]) if (ref && looksLikeRawSecret(ref)) throw new BillingContractError("secret_ref must be an indirection, not a raw secret");
  const allowed = value.allowedPaymentMethods ?? value.allowed_payment_methods ?? SUPPORTED_PAYMENT_METHODS[provider];
  const unsupported = allowed.filter((item) => !SUPPORTED_PAYMENT_METHODS[provider]?.includes(item));
  if (unsupported.length) throw new BillingContractError(`unsupported payment methods for ${provider}: ${unsupported.join(",")}`);
  const liveAck = Boolean(value.liveModeAck ?? value.live_mode_ack);
  if (mode === "live" && !liveAck) throw new BillingContractError("live mode requires live_mode_ack=True");
  if (mode === "live" && !secretRef) throw new BillingContractError("live mode requires secret_ref indirection");
  return { provider, mode, secret_ref: secretRef || undefined, webhook_secret_ref: webhookSecretRef || undefined, account_ref: accountRef || undefined, live_mode_ack: liveAck, allowed_payment_methods: allowed, raw_secret_present: false };
}

function normalizeProvider(provider: string): string {
  const normalized = provider.trim().toLowerCase().replaceAll("-", "_");
  const aliases: Record<string, string> = { stripe_checkout: "stripe", wechat: "wechat_pay", weixin: "wechat_pay", alipay_plus: "alipay" };
  const result = aliases[normalized] ?? normalized;
  if (!SUPPORTED_BILLING_PROVIDERS.includes(result as typeof SUPPORTED_BILLING_PROVIDERS[number])) throw new BillingContractError(`unsupported billing provider: ${provider}`);
  return result;
}

function normalizeMode(mode: string): string {
  const normalized = mode.trim().toLowerCase();
  if (!SUPPORTED_BILLING_MODES.includes(normalized as typeof SUPPORTED_BILLING_MODES[number])) throw new BillingContractError(`unsupported billing mode: ${mode}`);
  return normalized;
}

function normalizePrice(value: BillingPrice): BillingJsonRecord {
  const lookupKey = stringValue(value.lookupKey ?? value.lookup_key ?? value.price_lookup_key ?? "ashr_enterprise_monthly");
  if (!lookupKey || /\s/.test(lookupKey)) throw new BillingContractError("price lookup_key must be non-empty and space-free");
  const unitAmountMinor = Number(value.unitAmountMinor ?? value.unit_amount_minor ?? 0);
  if (unitAmountMinor < 0) throw new BillingContractError("unit_amount_minor must be >= 0");
  const currency = stringValue(value.currency ?? "usd").toLowerCase();
  if (!SUPPORTED_BILLING_CURRENCIES.includes(currency as typeof SUPPORTED_BILLING_CURRENCIES[number])) throw new BillingContractError(`unsupported currency: ${currency}`);
  return { lookup_key: lookupKey, unit_amount_minor: unitAmountMinor, currency, interval: stringValue(value.interval ?? "month"), metered: Boolean(value.metered), included_units: Number(value.includedUnits ?? value.included_units ?? 0) };
}

function providerCheckoutRequest(config: BillingJsonRecord, price: BillingJsonRecord, tenantId: string, projectId: string, customerRef: string, quantity: number): BillingJsonRecord {
  if (config.provider === "stripe") return { provider: "stripe", operation: "checkout.sessions.create", mode: price.interval ? "subscription" : "payment", customer: customerRef, line_items: [{ price_lookup_key: price.lookup_key, quantity }], payment_method_types: config.allowed_payment_methods, client_reference_id: `${tenantId}:${projectId}`, secret_ref: config.secret_ref, webhook_secret_ref: config.webhook_secret_ref };
  if (config.provider === "wechat_pay") return { provider: "wechat_pay", operation: "hosted_checkout.prepay", trade_type: "NATIVE", customer: customerRef, amount: { total: price.unit_amount_minor, currency: stringValue(price.currency).toUpperCase() }, description: price.lookup_key, tenant_project_ref: `${tenantId}:${projectId}`, merchant_account_ref: config.account_ref, secret_ref: config.secret_ref };
  return { provider: "alipay", operation: "hosted_checkout.trade_page_pay", customer: customerRef, total_amount: (Number(price.unit_amount_minor) / 100).toFixed(2), currency: stringValue(price.currency).toUpperCase(), subject: price.lookup_key, tenant_project_ref: `${tenantId}:${projectId}`, merchant_account_ref: config.account_ref, secret_ref: config.secret_ref };
}

function publicUsageRollup(value: unknown, tenantId: string, projectId: string): BillingJsonRecord {
  const rollup = isRecord(value) ? value : {};
  rejectSensitivePayload(rollup);
  return { tenant_id: stringValue(rollup.tenant_id ?? tenantId), project_id: stringValue(rollup.project_id ?? projectId), billing_period: rollup.billing_period, operation_totals: isRecord(rollup.operation_totals) ? cloneJson(rollup.operation_totals) : {}, billable_units: Number(rollup.billable_units ?? 0) };
}

function publicMetadata(value: unknown): BillingJsonRecord {
  const metadata = isRecord(value) ? value : {};
  rejectSensitivePayload(metadata);
  return cloneJson(metadata);
}

function rejectSensitivePayload(value: unknown, path = "$"): void {
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      if (["card", "card_number", "cvc", "cvv", "pan", "secret", "client_secret", "api_key", "authorization", "token"].includes(normalized)) throw new BillingContractError(`sensitive billing field is not allowed at ${path}.${key}`);
      rejectSensitivePayload(item, `${path}.${key}`);
    }
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => rejectSensitivePayload(item, `${path}[${index}]`));
  } else if (typeof value === "string" && (looksLikeRawSecret(value) || looksLikeCardNumber(value))) {
    throw new BillingContractError(`sensitive billing value is not allowed at ${path}`);
  }
}

function assertPublicSafe<T extends BillingJsonRecord>(value: T): T {
  const text = JSON.stringify(value);
  if (secretKeyRe.test(text) || text.includes("Bearer ") || looksLikeCardNumber(text)) throw new BillingContractError("billing payload failed public-safety scan");
  return value;
}

function looksLikeRawSecret(value: string): boolean {
  const lowered = value.toLowerCase();
  return secretKeyRe.test(value) || ["sk_test_", "sk_live_", "rk_test_", "rk_live_", "whsec_", "bearer ", "basic "].some((prefix) => lowered.startsWith(prefix));
}

function looksLikeCardNumber(value: string): boolean {
  const compact = value.replace(/\D/g, "");
  return compact.length >= 13 && compact.length <= 19 && cardNumberRe.test(value);
}

function validateTenantProject(tenantId: string, projectId: string): void {
  if (!tenantId.trim() || !projectId.trim()) throw new BillingContractError("tenant_id and project_id are required");
}

function normalizeLedgerEventType(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[.-]/g, "_");
  if (!ledgerEventTypes.has(normalized)) throw new BillingContractError(`unsupported billing ledger event type: ${value}`);
  return normalized;
}

function providerEventKey(provider: string, mode: string, tenantId: string, projectId: string, eventId: string): string {
  return [provider, mode, tenantId, projectId, eventId].join(":");
}

function accountKey(tenantId: string, projectId: string, provider: string, mode: string, customerRef: string): string {
  return [tenantId, projectId, provider, mode, customerRef].join(":");
}

function planIdFor(...parts: unknown[]): string {
  return `billplan_${sha256(parts.filter((part) => part !== undefined && part !== null).join("|")).slice(0, 24)}`;
}

function ledgerEventIdFor(...parts: unknown[]): string {
  return `ble_${sha256(parts.filter((part) => part !== undefined && part !== null).join("|")).slice(0, 24)}`;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function utcNow(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function stringValue(value: unknown, fallback = ""): string {
  return value === undefined || value === null ? fallback : String(value);
}

function isRecord(value: unknown): value is BillingJsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJson);
  if (isRecord(value)) return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, sortJson(item)]));
  return value;
}