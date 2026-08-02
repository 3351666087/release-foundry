import { createHash } from "node:crypto";

export const CHINA_PAYMENT_SCHEMA_VERSION = "releasefoundry.china_payment_contract.v1";
export const PAYMENT_RECONCILIATION_SCHEMA_VERSION = "releasefoundry.payment_reconciliation.v1";

export type PaymentJsonRecord = Record<string, unknown>;
export type PaymentProvider = "wechat_pay" | "alipay" | "domestic_bank_card" | "stripe";
export type PaymentMode = "test" | "live";
export type NormalizedPaymentEventType =
  | "trade_created"
  | "trade_succeeded"
  | "trade_closed"
  | "refund_processing"
  | "refund_succeeded"
  | "refund_failed"
  | "unknown";
export type NormalizedRefundStatus = "created" | "processing" | "succeeded" | "failed" | "closed" | "unknown";
export type ReconciliationStatus = "received" | "verified" | "applied" | "failed";

const PROVIDER_ORDER: PaymentProvider[] = ["wechat_pay", "alipay", "domestic_bank_card", "stripe"];
const REFERENCE_PREFIXES = ["env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:"] as const;
const SAFE_IDEMPOTENCY_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,254}$/;
const SHA256_RE = /^[a-f0-9]{64}$/;
const SENSITIVE_KEY_RE = /(?:authorization|private.?key|api.?key|secret|token|password|credential|certificate|signature|nonce|payer|buyer|openid|card|pan|cvc)/i;
const RAW_SECRET_RE = /\b(?:sk|rk|whsec)_(?:test|live)_[A-Za-z0-9]{8,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----/i;
const CARD_NUMBER_RE = /(?:\d[ -]*?){13,19}/;
const FORBIDDEN_PAYMENT_VALUE_RE = /\b(?:pan|primary[ _-]*account[ _-]*(?:number|no)|card[ _-]*(?:number|no)|account[ _-]*(?:number|no)|exp(?:iry|iration)?(?:[ _-]*(?:month|year|date))?|valid[ _-]*(?:thru|through)|cvv|cvc|cvn|cid|security[ _-]*code|pin|one[ _-]*time[ _-]*(?:password|code)|otp|sms[ _-]*code|track[ _-]*(?:1|2|data)|cryptogram|cardholder|kyc[ _-]*(?:doc|docs|document|documents|data))\b(?:\s*(?:=|:)\s*|\s+)\S+/i;
const FORBIDDEN_PAYMENT_FIELD_NAMES = new Set([
  "pan",
  "primary_account_number",
  "primary_account_no",
  "card_number",
  "card_no",
  "account_number",
  "account_no",
  "expiry",
  "expiration",
  "expiry_date",
  "expiration_date",
  "exp",
  "exp_date",
  "exp_month",
  "expiry_month",
  "expiration_month",
  "exp_year",
  "expiry_year",
  "expiration_year",
  "valid_thru",
  "valid_through",
  "cvv",
  "cvc",
  "cvn",
  "cid",
  "security_code",
  "card_security_code",
  "pin",
  "pin_block",
  "otp",
  "one_time_password",
  "one_time_code",
  "sms_code",
  "sms_otp",
  "track1",
  "track_1",
  "track2",
  "track_2",
  "track_data",
  "cryptogram",
  "payment_cryptogram",
  "cardholder",
  "card_holder",
  "cardholder_name",
  "card_holder_name",
  "cardholder_data",
  "card_holder_data",
  "raw_cardholder",
  "raw_cardholder_data",
  "kyc",
  "kyc_data",
  "kyc_doc",
  "kyc_docs",
  "kyc_document",
  "kyc_documents",
  "raw_kyc",
  "raw_kyc_data",
  "raw_kyc_doc",
  "raw_kyc_docs",
  "raw_kyc_document",
  "raw_kyc_documents",
]);

const PROVIDER_CAPABILITIES: Record<PaymentProvider, PaymentJsonRecord> = {
  wechat_pay: {
    priority: 1,
    protocol: "wechat_pay_api_v3",
    trade_surfaces: ["native_qr"],
    trade_operation: "v3.pay.transactions.native",
    query_operation: "v3.pay.transactions.out-trade-no.get",
    close_operation: "v3.pay.transactions.out-trade-no.close",
    refund_operation: "v3.refund.domestic.refunds.create",
    refund_query_operation: "v3.refund.domestic.refunds.out-refund-no.get",
    daily_bill_types: ["transaction", "fundflow"],
    notification_headers: ["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"],
    currencies: ["CNY"],
  },
  alipay: {
    priority: 2,
    protocol: "alipay_open_api",
    trade_surfaces: ["trade_page_pay"],
    trade_operation: "alipay.trade.page.pay",
    query_operation: "alipay.trade.query",
    close_operation: "alipay.trade.close",
    refund_operation: "alipay.trade.refund",
    refund_query_operation: "alipay.trade.fastpay.refund.query",
    daily_bill_types: ["trade", "signcustomer"],
    notification_headers: ["sign", "sign_type", "app_id", "trade_no"],
    currencies: ["CNY"],
  },
  domestic_bank_card: {
    priority: 3,
    protocol: "mainland_acquirer_gateway",
    payment_rail: "domestic_bank_card",
    trade_surfaces: ["hosted_acquirer"],
    allowed_payment_method_flows: ["hosted", "acquirer_token", "provider_reference"],
    prohibited_data_collection: ["PAN", "CVC", "OTP"],
    trade_operation: "acquirer.orders.create",
    query_operation: "acquirer.orders.query",
    close_operation: "acquirer.orders.close",
    refund_operation: "acquirer.refunds.create",
    refund_query_operation: "acquirer.refunds.query",
    daily_bill_types: ["trade", "settlement"],
    notification_headers: ["x-acquirer-signature", "x-acquirer-timestamp", "x-acquirer-event-id"],
    currencies: ["CNY"],
    amount_unit: "fen",
    provider_account_binding_required: true,
  },
  stripe: {
    priority: 4,
    protocol: "stripe_api",
    trade_surfaces: ["hosted_checkout"],
    trade_operation: "checkout.sessions.create",
    query_operation: "checkout.sessions.retrieve",
    close_operation: "checkout.sessions.expire",
    refund_operation: "refunds.create",
    refund_query_operation: "refunds.retrieve",
    daily_bill_types: ["balance_transactions"],
    notification_headers: ["stripe-signature"],
    currencies: ["CNY", "USD"],
  },
};

const PROVIDER_EVENT_TYPES: Record<PaymentProvider, Record<string, NormalizedPaymentEventType>> = {
  wechat_pay: {
    "transaction.created": "trade_created",
    "transaction.success": "trade_succeeded",
    "transaction.closed": "trade_closed",
    "refund.processing": "refund_processing",
    "refund.success": "refund_succeeded",
    "refund.abnormal": "refund_failed",
    "refund.closed": "refund_failed",
  },
  alipay: {
    wait_buyer_pay: "trade_created",
    trade_success: "trade_succeeded",
    trade_finished: "trade_succeeded",
    trade_closed: "trade_closed",
    refund_processing: "refund_processing",
    refund_success: "refund_succeeded",
    refund_failed: "refund_failed",
  },
  domestic_bank_card: {
    order_created: "trade_created",
    order_pending: "trade_created",
    order_succeeded: "trade_succeeded",
    order_paid: "trade_succeeded",
    order_closed: "trade_closed",
    order_failed: "trade_closed",
    refund_created: "refund_processing",
    refund_processing: "refund_processing",
    refund_succeeded: "refund_succeeded",
    refund_failed: "refund_failed",
    refund_closed: "refund_failed",
  },
  stripe: {
    "checkout.session.completed": "trade_succeeded",
    "checkout.session.async_payment_succeeded": "trade_succeeded",
    "checkout.session.async_payment_failed": "trade_closed",
    "checkout.session.expired": "trade_closed",
    "refund.created": "refund_processing",
    "refund.updated": "refund_processing",
    "refund.failed": "refund_failed",
    "charge.refunded": "refund_succeeded",
  },
};

export class ChinaPaymentContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChinaPaymentContractError";
  }
}

export class PaymentIdempotencyConflictError extends ChinaPaymentContractError {
  readonly idempotencyKey: string;

  constructor(idempotencyKey: string) {
    super("idempotency key was already used with a different request fingerprint");
    this.name = "PaymentIdempotencyConflictError";
    this.idempotencyKey = idempotencyKey;
  }
}

export class PaymentReconciliationConflictError extends ChinaPaymentContractError {
  readonly provider: PaymentProvider;
  readonly providerEventId: string;

  constructor(provider: PaymentProvider, providerEventId: string) {
    super("payment event identity was already received with different hashes");
    this.name = "PaymentReconciliationConflictError";
    this.provider = provider;
    this.providerEventId = providerEventId;
  }
}

export function chinaPaymentCapabilityManifest(): PaymentJsonRecord {
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    default_provider_order: [...PROVIDER_ORDER],
    default_currency: "CNY",
    providers: cloneJson(PROVIDER_CAPABILITIES),
    common_capabilities: {
      cny_trade_plans: true,
      explicit_fen_amounts: true,
      provider_account_bindings: true,
      trade_and_refund_queries: true,
      notification_hash_envelopes: true,
      refunds: true,
      daily_bill_reconciliation: true,
      provider_event_normalization: true,
      tenant_project_scope: true,
      idempotency_conflict_detection: true,
      public_safe_serialization: true,
    },
    compatibility: {
      stripe_preserved: true,
      stripe_branch: "compatibility",
      stripe_capability_reduction: false,
      stripe_cny_payment_methods: ["alipay", "wechat_pay", "card"],
      network_calls_performed: false,
    },
    first_class_payment_rails: ["wechat_pay", "alipay", "domestic_bank_card"],
    public_safety: {
      raw_notification_body_included: false,
      raw_header_values_included: false,
      raw_provider_response_included: false,
      secret_value_present: false,
      payer_identity_included: false,
    },
  });
}

export function buildCnyTradePlan(options: {
  provider: string;
  mode?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  orderRef?: string;
  order_ref?: string;
  amountMinor?: number;
  amount_minor?: number;
  description: string;
  returnUrl?: string;
  return_url?: string;
  notifyUrl?: string;
  notify_url?: string;
  credentialRef?: string;
  credential_ref?: string;
  verificationKeyRef?: string;
  verification_key_ref?: string;
  accountRef?: string;
  account_ref?: string;
  paymentMethodRef?: string;
  payment_method_ref?: string;
  idempotencyKey?: string;
  idempotency_key?: string;
  metadata?: PaymentJsonRecord;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const mode = normalizeMode(options.mode ?? "test");
  const { tenantId, projectId } = scopeFrom(options);
  const orderRef = requirePublicRef("order_ref", options.orderRef ?? options.order_ref);
  const amountMinor = positiveMinor(options.amountMinor ?? options.amount_minor);
  const description = safeText("description", options.description);
  const returnUrl = requireHttpsUrl("return_url", options.returnUrl ?? options.return_url);
  const notifyUrl = requireHttpsUrl("notify_url", options.notifyUrl ?? options.notify_url);
  const credentialRef = requireSecretRef("credential_ref", options.credentialRef ?? options.credential_ref);
  const verificationKeyRef = requireSecretRef("verification_key_ref", options.verificationKeyRef ?? options.verification_key_ref);
  const accountRef = optionalPublicRef("account_ref", options.accountRef ?? options.account_ref);
  const paymentMethodRef = optionalPublicRef("payment_method_ref", options.paymentMethodRef ?? options.payment_method_ref);
  if (provider === "domestic_bank_card" && !accountRef) {
    throw new ChinaPaymentContractError("domestic_bank_card requires provider account binding");
  }
  if (provider === "domestic_bank_card" && !paymentMethodRef) {
    throw new ChinaPaymentContractError("domestic_bank_card requires a hosted/acquirer payment_method_ref");
  }
  const idempotencyKey = requireIdempotencyKey(options.idempotencyKey ?? options.idempotency_key);
  const metadata = publicMetadata(options.metadata);
  const requestShape = tradeRequest(provider, {
    orderRef,
    amountMinor,
    description,
    returnUrl,
    notifyUrl,
    accountRef,
    paymentMethodRef,
    metadata,
    tenantId,
    projectId,
  });
  const fingerprint = fingerprintFor({
    provider,
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    idempotency_key: idempotencyKey,
    request_shape: requestShape,
  });
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    plan_type: "cny_trade",
    provider,
    hosted_surface: firstString(PROVIDER_CAPABILITIES[provider].trade_surfaces),
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    order_ref: orderRef,
    amount: { minor: amountMinor, fen: amountMinor, currency: "CNY" },
    credential_ref: credentialRef,
    verification_key_ref: verificationKeyRef,
    account_ref: accountRef,
    payment_method_ref: paymentMethodRef,
    idempotency: {
      required: true,
      key: idempotencyKey,
      request_fingerprint_sha256: fingerprint,
      reuse_requires_identical_fingerprint: true,
    },
    request_shape: requestShape,
    execution_hook: { interface: "HostedPaymentExecutor", adapter_executes: false, secret_resolution_deferred: true },
    side_effects: noSideEffects(),
    raw_secret_present: false,
    raw_card_data_present: false,
    pan_collected: false,
    cvc_collected: false,
    otp_collected: false,
  });
}

export function buildProviderAccountBinding(options: {
  provider: string;
  mode?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  accountRef?: string;
  account_ref?: string;
  credentialRef?: string;
  credential_ref?: string;
  verificationKeyRef?: string;
  verification_key_ref?: string;
  acquirerRef?: string;
  acquirer_ref?: string;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const mode = normalizeMode(options.mode ?? "test");
  const { tenantId, projectId } = scopeFrom(options);
  const accountRef = requirePublicRef("account_ref", options.accountRef ?? options.account_ref);
  const credentialRef = requireSecretRef("credential_ref", options.credentialRef ?? options.credential_ref);
  const verificationKeyRef = requireSecretRef("verification_key_ref", options.verificationKeyRef ?? options.verification_key_ref);
  const acquirerRef = optionalPublicRef("acquirer_ref", options.acquirerRef ?? options.acquirer_ref);
  if (provider === "domestic_bank_card" && !acquirerRef) {
    throw new ChinaPaymentContractError("domestic_bank_card account binding requires acquirer_ref");
  }
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    envelope_type: "provider_account_binding",
    tenant_id: tenantId,
    project_id: projectId,
    provider,
    mode,
    account_ref: accountRef,
    acquirer_ref: acquirerRef,
    credential_ref: credentialRef,
    verification_key_ref: verificationKeyRef,
    currency: "CNY",
    amount_unit: "fen",
    binding_fingerprint_sha256: fingerprintFor({ tenant_id: tenantId, project_id: projectId, provider, mode, account_ref: accountRef, acquirer_ref: acquirerRef }),
    secret_resolution_deferred: true,
    raw_secret_present: false,
    raw_provider_response_included: false,
    pan_collected: false,
    cvc_collected: false,
    otp_collected: false,
    side_effects: noSideEffects(),
  });
}

export function buildPaymentQueryPlan(options: {
  provider: string;
  queryType?: "trade" | "refund";
  query_type?: "trade" | "refund";
  mode?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  orderRef?: string;
  order_ref?: string;
  refundRef?: string;
  refund_ref?: string;
  accountRef?: string;
  account_ref?: string;
  credentialRef?: string;
  credential_ref?: string;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const queryType = options.queryType ?? options.query_type ?? "trade";
  if (queryType !== "trade" && queryType !== "refund") throw new ChinaPaymentContractError("query_type must be trade or refund");
  const mode = normalizeMode(options.mode ?? "test");
  const { tenantId, projectId } = scopeFrom(options);
  const orderRef = requirePublicRef("order_ref", options.orderRef ?? options.order_ref);
  const refundRef = queryType === "refund" ? requirePublicRef("refund_ref", options.refundRef ?? options.refund_ref) : undefined;
  const accountRef = optionalPublicRef("account_ref", options.accountRef ?? options.account_ref);
  if (provider === "domestic_bank_card" && !accountRef) {
    throw new ChinaPaymentContractError("domestic_bank_card requires provider account binding");
  }
  const credentialRef = requireSecretRef("credential_ref", options.credentialRef ?? options.credential_ref);
  const operation = String(PROVIDER_CAPABILITIES[provider][queryType === "trade" ? "query_operation" : "refund_query_operation"]);
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    plan_type: "payment_query",
    query_type: queryType,
    tenant_id: tenantId,
    project_id: projectId,
    provider,
    mode,
    order_ref: orderRef,
    refund_ref: refundRef,
    account_ref: accountRef,
    credential_ref: credentialRef,
    currency: "CNY",
    amount_unit: "fen",
    request_shape: queryRequest(provider, queryType, orderRef, refundRef, accountRef),
    operation,
    raw_provider_response_included: false,
    side_effects: noSideEffects(),
  });
}

export function buildRefundPlan(options: {
  provider: string;
  mode?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  orderRef?: string;
  order_ref?: string;
  refundRef?: string;
  refund_ref?: string;
  amountMinor?: number;
  amount_minor?: number;
  totalAmountMinor?: number;
  total_amount_minor?: number;
  reason?: string;
  notifyUrl?: string;
  notify_url?: string;
  credentialRef?: string;
  credential_ref?: string;
  accountRef?: string;
  account_ref?: string;
  idempotencyKey?: string;
  idempotency_key?: string;
  metadata?: PaymentJsonRecord;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const mode = normalizeMode(options.mode ?? "test");
  const { tenantId, projectId } = scopeFrom(options);
  const orderRef = requirePublicRef("order_ref", options.orderRef ?? options.order_ref);
  const refundRef = requirePublicRef("refund_ref", options.refundRef ?? options.refund_ref);
  const amountMinor = positiveMinor(options.amountMinor ?? options.amount_minor);
  const totalAmountMinor = positiveMinor(options.totalAmountMinor ?? options.total_amount_minor);
  if (amountMinor > totalAmountMinor) throw new ChinaPaymentContractError("refund amount must not exceed original trade amount");
  const credentialRef = requireSecretRef("credential_ref", options.credentialRef ?? options.credential_ref);
  const accountRef = optionalPublicRef("account_ref", options.accountRef ?? options.account_ref);
  if (provider === "domestic_bank_card" && !accountRef) {
    throw new ChinaPaymentContractError("domestic_bank_card requires provider account binding");
  }
  const notifyUrl = optionalHttpsUrl("notify_url", options.notifyUrl ?? options.notify_url);
  const reason = safeText("reason", options.reason ?? "customer_requested");
  const metadata = publicMetadata(options.metadata);
  const idempotencyKey = requireIdempotencyKey(options.idempotencyKey ?? options.idempotency_key);
  const requestShape = refundRequest(provider, { orderRef, refundRef, amountMinor, totalAmountMinor, reason, notifyUrl, accountRef, metadata });
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    plan_type: "refund",
    provider,
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    order_ref: orderRef,
    refund_ref: refundRef,
    amount: { refund_minor: amountMinor, refund_fen: amountMinor, total_minor: totalAmountMinor, total_fen: totalAmountMinor, currency: "CNY" },
    credential_ref: credentialRef,
    account_ref: accountRef,
    idempotency: {
      required: true,
      key: idempotencyKey,
      request_fingerprint_sha256: fingerprintFor({ provider, mode, tenant_id: tenantId, project_id: projectId, request_shape: requestShape }),
      reuse_requires_identical_fingerprint: true,
    },
    request_shape: requestShape,
    expected_statuses: ["created", "processing", "succeeded", "failed", "closed", "unknown"],
    side_effects: noSideEffects(),
    raw_secret_present: false,
    raw_provider_response_included: false,
    pan_collected: false,
    cvc_collected: false,
    otp_collected: false,
  });
}

export function buildNotificationEnvelope(options: {
  provider: string;
  mode?: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  rawBody?: Uint8Array | string;
  raw_body?: Uint8Array | string;
  headers?: Record<string, string | string[] | undefined>;
  eventIdRef?: string;
  event_id_ref?: string;
  eventType?: string;
  event_type?: string;
  livemode?: boolean;
  verified?: boolean;
  reasonCodes?: string[];
  reason_codes?: string[];
  verifierCalled?: boolean;
  verifier_called?: boolean;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const mode = normalizeMode(options.mode ?? "test");
  const { tenantId, projectId } = scopeFrom(options);
  const rawBody = options.rawBody ?? options.raw_body;
  if ((typeof rawBody !== "string" && !(rawBody instanceof Uint8Array)) || rawBody.length === 0) {
    throw new ChinaPaymentContractError("notification raw_body must be non-empty bytes or text");
  }
  const bodyBytes = typeof rawBody === "string" ? Buffer.from(rawBody, "utf8") : Buffer.from(rawBody);
  const normalizedHeaders = Object.fromEntries(
    Object.entries(options.headers ?? {}).map(([name, value]) => [name.trim().toLowerCase(), Array.isArray(value) ? value.join(",") : String(value ?? "")]),
  );
  const expectedHeaders = stringArray(PROVIDER_CAPABILITIES[provider].notification_headers);
  const providedHeaders = Object.keys(normalizedHeaders).filter((name) => normalizedHeaders[name] !== "").sort();
  const missingHeaders = expectedHeaders.filter((name) => !normalizedHeaders[name]);
  const reasons = [...(options.reasonCodes ?? options.reason_codes ?? [])];
  if (missingHeaders.length > 0) reasons.push("missing_signature_headers");
  if (options.livemode !== undefined && options.livemode !== (mode === "live")) reasons.push("provider_mode_mismatch");
  const eventIdRef = optionalPublicRef("event_id_ref", options.eventIdRef ?? options.event_id_ref);
  const verified = Boolean(options.verified) && reasons.length === 0;
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    envelope_type: "payment_notification",
    provider,
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    verified,
    event_id_ref: eventIdRef,
    event_type: safeOptionalText("event_type", options.eventType ?? options.event_type),
    livemode: options.livemode,
    payload_sha256: sha256(bodyBytes),
    headers_sha256: sha256(Buffer.from(stableJson(Object.keys(normalizedHeaders).sort()), "utf8")),
    signature_header_shape: {
      expected_headers: expectedHeaders,
      provided_headers: providedHeaders,
      missing_headers: missingHeaders,
      raw_header_values_included: false,
    },
    reason_codes: [...new Set(reasons)],
    integration_hook: { interface: "PaymentSignatureVerifier", verifier_called: Boolean(options.verifierCalled ?? options.verifier_called) && missingHeaders.length === 0 },
    raw_body_included: false,
    raw_headers_included: false,
    secret_value_present: false,
    payer_identity_included: false,
    side_effects: noSideEffects(),
  });
}

export function normalizeProviderEvent(options: {
  provider: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  providerEventId?: string;
  provider_event_id?: string;
  eventType?: string;
  event_type?: string;
  status?: string;
  orderRef?: string;
  order_ref?: string;
  refundRef?: string;
  refund_ref?: string;
  amountMinor?: number;
  amount_minor?: number;
  currency?: string;
  occurredAt?: string;
  occurred_at?: string;
  payloadSha256?: string;
  payload_sha256?: string;
  metadata?: PaymentJsonRecord;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const { tenantId, projectId } = scopeFrom(options);
  const providerEventId = requirePublicRef("provider_event_id", options.providerEventId ?? options.provider_event_id);
  const rawType = String(options.eventType ?? options.event_type ?? options.status ?? "").trim();
  if (!rawType) throw new ChinaPaymentContractError("event_type or status is required");
  const eventType = normalizeEventType(provider, rawType);
  const currency = String(options.currency ?? "CNY").toUpperCase();
  if (!["CNY", "USD"].includes(currency) || (provider !== "stripe" && currency !== "CNY")) {
    throw new ChinaPaymentContractError(`${provider} event currency is not supported`);
  }
  const amountMinor = nonNegativeMinor(options.amountMinor ?? options.amount_minor ?? 0);
  const payloadSha256 = optionalSha256("payload_sha256", options.payloadSha256 ?? options.payload_sha256);
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    record_type: "normalized_provider_event",
    tenant_id: tenantId,
    project_id: projectId,
    provider,
    provider_event_id: providerEventId,
    provider_event_type: rawType,
    event_type: eventType,
    order_ref: optionalPublicRef("order_ref", options.orderRef ?? options.order_ref),
    refund_ref: optionalPublicRef("refund_ref", options.refundRef ?? options.refund_ref),
    amount: { minor: amountMinor, currency },
    refund_status: eventType.startsWith("refund_") ? normalizeRefundStatus(provider, rawType) : undefined,
    occurred_at: requireIsoTimestamp(options.occurredAt ?? options.occurred_at),
    payload_sha256: payloadSha256,
    metadata: publicMetadata(options.metadata),
    raw_payload_included: false,
    raw_provider_response_included: false,
    secret_value_present: false,
    payer_identity_included: false,
  });
}

export function normalizeRefundStatus(providerValue: string, statusValue: string): NormalizedRefundStatus {
  const provider = normalizeProvider(providerValue);
  const status = statusValue.trim().toLowerCase().replaceAll("-", "_");
  const normalizedEvent = PROVIDER_EVENT_TYPES[provider][status] ?? PROVIDER_EVENT_TYPES[provider][status.replaceAll("_", ".")];
  if (normalizedEvent === "refund_succeeded") return "succeeded";
  if (normalizedEvent === "refund_failed") return "failed";
  if (normalizedEvent === "refund_processing") return "processing";
  const direct: Record<string, NormalizedRefundStatus> = {
    created: "created",
    pending: "processing",
    processing: "processing",
    success: "succeeded",
    succeeded: "succeeded",
    refunded: "succeeded",
    failed: "failed",
    abnormal: "failed",
    canceled: "closed",
    cancelled: "closed",
    closed: "closed",
  };
  return direct[status] ?? "unknown";
}

export function normalizeDailyBillRecord(options: {
  provider: string;
  tenantId?: string;
  tenant_id?: string;
  projectId?: string;
  project_id?: string;
  billDate?: string;
  bill_date?: string;
  billType?: string;
  bill_type?: string;
  lineId?: string;
  line_id?: string;
  orderRef?: string;
  order_ref?: string;
  providerTradeRef?: string;
  provider_trade_ref?: string;
  tradeStatus?: string;
  trade_status?: string;
  grossAmountMinor?: number;
  gross_amount_minor?: number;
  feeAmountMinor?: number;
  fee_amount_minor?: number;
  netAmountMinor?: number;
  net_amount_minor?: number;
  currency?: string;
  occurredAt?: string;
  occurred_at?: string;
  sourceSha256?: string;
  source_sha256?: string;
  metadata?: PaymentJsonRecord;
}): PaymentJsonRecord {
  const provider = normalizeProvider(options.provider);
  const { tenantId, projectId } = scopeFrom(options);
  const billDate = requireDate(options.billDate ?? options.bill_date);
  const billType = safeText("bill_type", options.billType ?? options.bill_type ?? "trade");
  const lineId = requirePublicRef("line_id", options.lineId ?? options.line_id);
  const currency = String(options.currency ?? "CNY").toUpperCase();
  if (currency !== "CNY" && provider !== "stripe") throw new ChinaPaymentContractError("mainland payment bill records require CNY");
  const gross = signedMinor(options.grossAmountMinor ?? options.gross_amount_minor ?? 0);
  const fee = nonNegativeMinor(options.feeAmountMinor ?? options.fee_amount_minor ?? 0);
  const net = signedMinor(options.netAmountMinor ?? options.net_amount_minor ?? gross - fee);
  const sourceSha256 = requireSha256("source_sha256", options.sourceSha256 ?? options.source_sha256);
  const occurredAt = requireIsoTimestamp(options.occurredAt ?? options.occurred_at);
  const identity = { tenant_id: tenantId, project_id: projectId, provider, bill_date: billDate, bill_type: billType, line_id: lineId };
  return publicSafe({
    schema_version: CHINA_PAYMENT_SCHEMA_VERSION,
    record_type: "daily_bill_reconciliation",
    ...identity,
    reconciliation_key: sha256(Buffer.from(stableJson(identity), "utf8")),
    order_ref: optionalPublicRef("order_ref", options.orderRef ?? options.order_ref),
    provider_trade_ref: optionalPublicRef("provider_trade_ref", options.providerTradeRef ?? options.provider_trade_ref),
    trade_status: safeOptionalText("trade_status", options.tradeStatus ?? options.trade_status),
    amount: { gross_minor: gross, gross_fen: gross, fee_minor: fee, fee_fen: fee, net_minor: net, net_fen: net, currency },
    occurred_at: occurredAt,
    source_sha256: sourceSha256,
    metadata: publicMetadata(options.metadata),
    raw_bill_line_included: false,
    raw_provider_response_included: false,
    secret_value_present: false,
    payer_identity_included: false,
  });
}

export class PaymentIdempotencyRegistry {
  private readonly records = new Map<string, { fingerprint: string; result: PaymentJsonRecord }>();

  register(options: {
    tenantId?: string;
    tenant_id?: string;
    projectId?: string;
    project_id?: string;
    operation: string;
    idempotencyKey?: string;
    idempotency_key?: string;
    request: PaymentJsonRecord;
    result: PaymentJsonRecord;
  }): PaymentJsonRecord {
    const { tenantId, projectId } = scopeFrom(options);
    const operation = safeText("operation", options.operation);
    const idempotencyKey = requireIdempotencyKey(options.idempotencyKey ?? options.idempotency_key);
    publicSafe(options.request);
    publicSafe(options.result);
    const key = stableJson({ tenant_id: tenantId, project_id: projectId, operation, idempotency_key: idempotencyKey });
    const fingerprint = fingerprintFor(options.request);
    const existing = this.records.get(key);
    if (existing) {
      if (existing.fingerprint !== fingerprint) throw new PaymentIdempotencyConflictError(idempotencyKey);
      return publicSafe({ ...cloneJson(existing.result), idempotent_replay: true, request_fingerprint_sha256: fingerprint });
    }
    const result = publicSafe({ ...cloneJson(options.result), idempotent_replay: false, request_fingerprint_sha256: fingerprint });
    this.records.set(key, { fingerprint, result: cloneJson(result) });
    return cloneJson(result);
  }
}

export class PaymentReconciliationStore {
  private readonly events = new Map<string, PaymentJsonRecord>();
  private readonly dailyBills = new Map<string, PaymentJsonRecord>();
  private readonly clock: () => string;

  constructor(options: { clock?: () => string } = {}) {
    this.clock = options.clock ?? (() => new Date().toISOString());
  }

  receiveEvent(options: {
    tenantId?: string;
    tenant_id?: string;
    projectId?: string;
    project_id?: string;
    provider: string;
    providerEventId?: string;
    provider_event_id?: string;
    eventType?: string;
    event_type?: string;
    payloadSha256?: string;
    payload_sha256?: string;
    headersSha256?: string;
    headers_sha256?: string;
  }): PaymentJsonRecord {
    const provider = normalizeProvider(options.provider);
    const { tenantId, projectId } = scopeFrom(options);
    const providerEventId = requirePublicRef("provider_event_id", options.providerEventId ?? options.provider_event_id);
    const eventType = safeText("event_type", options.eventType ?? options.event_type ?? "unknown");
    const payloadSha256 = requireSha256("payload_sha256", options.payloadSha256 ?? options.payload_sha256);
    const headersSha256 = optionalSha256("headers_sha256", options.headersSha256 ?? options.headers_sha256);
    const key = eventKey(tenantId, projectId, provider, providerEventId);
    const existing = this.events.get(key);
    if (existing) {
      if (existing.payload_sha256 !== payloadSha256 || (existing.headers_sha256 ?? undefined) !== headersSha256) {
        throw new PaymentReconciliationConflictError(provider, providerEventId);
      }
      return publicSafe({ ...cloneJson(existing), idempotent_replay: true });
    }
    const now = this.clock();
    const record = publicSafe({
      schema_version: PAYMENT_RECONCILIATION_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      provider,
      provider_event_id: providerEventId,
      event_type: eventType,
      payload_sha256: payloadSha256,
      headers_sha256: headersSha256,
      status: "received",
      failure_sha256: undefined,
      raw_payload_included: false,
      raw_headers_included: false,
      secret_value_present: false,
      received_at: now,
      verified_at: undefined,
      applied_at: undefined,
      failed_at: undefined,
      updated_at: now,
      idempotent_replay: false,
    });
    this.events.set(key, cloneJson(record));
    return cloneJson(record);
  }

  transitionEvent(options: {
    tenantId?: string;
    tenant_id?: string;
    projectId?: string;
    project_id?: string;
    provider: string;
    providerEventId?: string;
    provider_event_id?: string;
    status: ReconciliationStatus;
    failureSha256?: string;
    failure_sha256?: string;
  }): PaymentJsonRecord {
    const provider = normalizeProvider(options.provider);
    const { tenantId, projectId } = scopeFrom(options);
    const providerEventId = requirePublicRef("provider_event_id", options.providerEventId ?? options.provider_event_id);
    const key = eventKey(tenantId, projectId, provider, providerEventId);
    const existing = this.events.get(key);
    if (!existing) throw new ChinaPaymentContractError("payment reconciliation event was not found for tenant/project");
    const target = options.status;
    const current = String(existing.status) as ReconciliationStatus;
    if (current === target) return publicSafe({ ...cloneJson(existing), idempotent_replay: true });
    const allowed = current === "received" ? ["verified"] : current === "verified" ? ["applied", "failed"] : [];
    if (!allowed.includes(target)) throw new ChinaPaymentContractError(`invalid payment reconciliation transition: ${current} -> ${target}`);
    const now = this.clock();
    const next: PaymentJsonRecord = { ...cloneJson(existing), status: target, updated_at: now, idempotent_replay: false };
    if (target === "verified") next.verified_at = now;
    if (target === "applied") next.applied_at = now;
    if (target === "failed") {
      next.failed_at = now;
      next.failure_sha256 = requireSha256("failure_sha256", options.failureSha256 ?? options.failure_sha256);
    }
    this.events.set(key, publicSafe(next));
    return cloneJson(next);
  }

  ingestDailyBill(record: PaymentJsonRecord): PaymentJsonRecord {
    if (record.record_type !== "daily_bill_reconciliation") throw new ChinaPaymentContractError("daily bill record has an unsupported record_type");
    const { tenantId, projectId } = scopeFrom(record);
    const provider = normalizeProvider(String(record.provider));
    const reconciliationKey = requireSha256("reconciliation_key", record.reconciliation_key);
    const key = stableJson({ tenant_id: tenantId, project_id: projectId, provider, reconciliation_key: reconciliationKey });
    const fingerprint = fingerprintFor(record);
    const existing = this.dailyBills.get(key);
    if (existing) {
      if (existing.record_fingerprint_sha256 !== fingerprint) throw new PaymentReconciliationConflictError(provider, String(record.line_id));
      return publicSafe({ ...cloneJson(existing), idempotent_replay: true });
    }
    const stored = publicSafe({ ...cloneJson(record), record_fingerprint_sha256: fingerprint, idempotent_replay: false });
    this.dailyBills.set(key, cloneJson(stored));
    return stored;
  }

  list(options: { tenantId?: string; tenant_id?: string; projectId?: string; project_id?: string; status?: ReconciliationStatus }): PaymentJsonRecord {
    const { tenantId, projectId } = scopeFrom(options);
    const events = [...this.events.values()].filter(
      (event) => event.tenant_id === tenantId && event.project_id === projectId && (options.status === undefined || event.status === options.status),
    );
    const dailyBills = [...this.dailyBills.values()].filter((record) => record.tenant_id === tenantId && record.project_id === projectId);
    return publicSafe({
      schema_version: PAYMENT_RECONCILIATION_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      status: options.status,
      events: events.map(cloneJson),
      event_count: events.length,
      daily_bill_records: dailyBills.map(cloneJson),
      daily_bill_record_count: dailyBills.length,
      raw_payload_included: false,
      raw_headers_included: false,
      raw_bill_lines_included: false,
      secret_value_present: false,
    });
  }
}

function tradeRequest(provider: PaymentProvider, value: {
  orderRef: string;
  amountMinor: number;
  description: string;
  returnUrl: string;
  notifyUrl: string;
  accountRef?: string;
  paymentMethodRef?: string;
  metadata: PaymentJsonRecord;
  tenantId: string;
  projectId: string;
}): PaymentJsonRecord {
  if (provider === "wechat_pay") {
    return {
      operation: "v3.pay.transactions.native",
      out_trade_no: value.orderRef,
      description: value.description,
      amount: { total: value.amountMinor, currency: "CNY" },
      notify_url: value.notifyUrl,
      attach: { tenant_id: value.tenantId, project_id: value.projectId, metadata: value.metadata },
      merchant_account_ref: value.accountRef,
    };
  }
  if (provider === "alipay") {
    return {
      operation: "alipay.trade.page.pay",
      out_trade_no: value.orderRef,
      subject: value.description,
      total_amount: minorToMajor(value.amountMinor),
      product_code: "FAST_INSTANT_TRADE_PAY",
      return_url: value.returnUrl,
      notify_url: value.notifyUrl,
      passback_params: { tenant_id: value.tenantId, project_id: value.projectId, metadata: value.metadata },
      app_account_ref: value.accountRef,
    };
  }
  if (provider === "domestic_bank_card") {
    return {
      operation: "acquirer.orders.create",
      merchant_order_ref: value.orderRef,
      amount: { fen: value.amountMinor, currency: "CNY" },
      description: value.description,
      hosted_return_url: value.returnUrl,
      notification_url: value.notifyUrl,
      payment_method_ref: value.paymentMethodRef,
      provider_account_ref: value.accountRef,
      scope: { tenant_id: value.tenantId, project_id: value.projectId },
      metadata: value.metadata,
      pan_collected_by_sdk: false,
      cvc_collected_by_sdk: false,
      otp_collected_by_sdk: false,
    };
  }
  return {
    operation: "checkout.sessions.create",
    checkout_mode: "payment",
    client_reference_id: `${value.tenantId}:${value.projectId}`,
    line_items: [{ price_data: { currency: "cny", unit_amount: value.amountMinor, product_data: { name: value.description } }, quantity: 1 }],
    payment_method_types: ["alipay", "wechat_pay", "card"],
    success_url: value.returnUrl,
    cancel_url: value.returnUrl,
    metadata: { order_ref: value.orderRef, ...value.metadata },
    account_ref: value.accountRef,
  };
}

function refundRequest(provider: PaymentProvider, value: {
  orderRef: string;
  refundRef: string;
  amountMinor: number;
  totalAmountMinor: number;
  reason: string;
  notifyUrl?: string;
  accountRef?: string;
  metadata: PaymentJsonRecord;
}): PaymentJsonRecord {
  if (provider === "wechat_pay") {
    return {
      operation: "v3.refund.domestic.refunds.create",
      out_trade_no: value.orderRef,
      out_refund_no: value.refundRef,
      reason: value.reason,
      notify_url: value.notifyUrl,
      amount: { refund: value.amountMinor, total: value.totalAmountMinor, currency: "CNY" },
      merchant_account_ref: value.accountRef,
      metadata: value.metadata,
    };
  }
  if (provider === "alipay") {
    return {
      operation: "alipay.trade.refund",
      out_trade_no: value.orderRef,
      out_request_no: value.refundRef,
      refund_amount: minorToMajor(value.amountMinor),
      refund_reason: value.reason,
      app_account_ref: value.accountRef,
      metadata: value.metadata,
    };
  }
  if (provider === "domestic_bank_card") {
    return {
      operation: "acquirer.refunds.create",
      merchant_order_ref: value.orderRef,
      merchant_refund_ref: value.refundRef,
      amount: { refund_fen: value.amountMinor, total_fen: value.totalAmountMinor, currency: "CNY" },
      reason: value.reason,
      notification_url: value.notifyUrl,
      provider_account_ref: value.accountRef,
      metadata: value.metadata,
      pan_collected_by_sdk: false,
      cvc_collected_by_sdk: false,
      otp_collected_by_sdk: false,
    };
  }
  return {
    operation: "refunds.create",
    payment_intent_ref: value.orderRef,
    amount: value.amountMinor,
    currency: "cny",
    reason: "requested_by_customer",
    metadata: { refund_ref: value.refundRef, reason: value.reason, ...value.metadata },
    account_ref: value.accountRef,
  };
}

function queryRequest(
  provider: PaymentProvider,
  queryType: "trade" | "refund",
  orderRef: string,
  refundRef: string | undefined,
  accountRef: string | undefined,
): PaymentJsonRecord {
  if (provider === "wechat_pay") {
    return queryType === "trade"
      ? { operation: "v3.pay.transactions.out-trade-no.get", out_trade_no: orderRef, merchant_account_ref: accountRef }
      : { operation: "v3.refund.domestic.refunds.out-refund-no.get", out_refund_no: refundRef, merchant_account_ref: accountRef };
  }
  if (provider === "alipay") {
    return queryType === "trade"
      ? { operation: "alipay.trade.query", out_trade_no: orderRef, app_account_ref: accountRef }
      : { operation: "alipay.trade.fastpay.refund.query", out_trade_no: orderRef, out_request_no: refundRef, app_account_ref: accountRef };
  }
  if (provider === "domestic_bank_card") {
    return {
      operation: queryType === "trade" ? "acquirer.orders.query" : "acquirer.refunds.query",
      merchant_order_ref: orderRef,
      merchant_refund_ref: refundRef,
      provider_account_ref: accountRef,
      raw_provider_response_included: false,
    };
  }
  return queryType === "trade"
    ? { operation: "checkout.sessions.retrieve", checkout_session_ref: orderRef, account_ref: accountRef }
    : { operation: "refunds.retrieve", refund_ref: refundRef, account_ref: accountRef };
}

function normalizeEventType(provider: PaymentProvider, value: string): NormalizedPaymentEventType {
  const lower = value.trim().toLowerCase();
  return PROVIDER_EVENT_TYPES[provider][lower] ?? PROVIDER_EVENT_TYPES[provider][lower.replaceAll("_", ".")] ?? "unknown";
}

function normalizeProvider(value: string): PaymentProvider {
  const normalized = String(value).trim().toLowerCase().replaceAll("-", "_");
  const aliases: Record<string, PaymentProvider> = {
    wechat: "wechat_pay",
    weixin: "wechat_pay",
    alipay_plus: "alipay",
    bank_card: "domestic_bank_card",
    domestic_card: "domestic_bank_card",
    unionpay_card: "domestic_bank_card",
    stripe_checkout: "stripe",
  };
  const provider = aliases[normalized] ?? normalized;
  if (!PROVIDER_ORDER.includes(provider as PaymentProvider)) throw new ChinaPaymentContractError(`unsupported payment provider: ${provider}`);
  return provider as PaymentProvider;
}

function normalizeMode(value: string): PaymentMode {
  const mode = String(value).trim().toLowerCase();
  if (mode !== "test" && mode !== "live") throw new ChinaPaymentContractError("payment mode must be test or live");
  return mode;
}

function scopeFrom(value: {
  tenantId?: unknown;
  tenant_id?: unknown;
  projectId?: unknown;
  project_id?: unknown;
}): { tenantId: string; projectId: string } {
  const tenantId = String(value.tenantId ?? value.tenant_id ?? "").trim();
  const projectId = String(value.projectId ?? value.project_id ?? "").trim();
  if (!tenantId || !projectId) throw new ChinaPaymentContractError("tenant_id and project_id are required");
  safeText("tenant_id", tenantId);
  safeText("project_id", projectId);
  return { tenantId, projectId };
}

function requirePublicRef(name: string, value: unknown): string {
  const text = safeText(name, value);
  rejectSensitive(name, text);
  return text;
}

function optionalPublicRef(name: string, value: unknown): string | undefined {
  if (value === undefined || value === null || String(value).trim() === "") return undefined;
  return requirePublicRef(name, value);
}

function requireSecretRef(name: string, value: unknown): string {
  const text = requirePublicRef(name, value);
  if (!REFERENCE_PREFIXES.some((prefix) => text.startsWith(prefix))) {
    throw new ChinaPaymentContractError(`${name} must use an approved secret reference prefix`);
  }
  if (/\s/.test(text)) throw new ChinaPaymentContractError(`${name} must not contain whitespace`);
  return text;
}

function requireIdempotencyKey(value: unknown): string {
  const text = String(value ?? "");
  if (!SAFE_IDEMPOTENCY_RE.test(text)) throw new ChinaPaymentContractError("idempotency_key must be 8-255 safe characters");
  return text;
}

function requireHttpsUrl(name: string, value: unknown): string {
  const text = String(value ?? "");
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    throw new ChinaPaymentContractError(`${name} must be an HTTPS URL`);
  }
  if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) {
    throw new ChinaPaymentContractError(`${name} must be an HTTPS URL without embedded credentials`);
  }
  rejectSensitive(name, text);
  return text;
}

function optionalHttpsUrl(name: string, value: unknown): string | undefined {
  if (value === undefined || value === null || String(value).trim() === "") return undefined;
  return requireHttpsUrl(name, value);
}

function safeText(name: string, value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) throw new ChinaPaymentContractError(`${name} must not be empty`);
  rejectSensitive(name, text);
  return text;
}

function safeOptionalText(name: string, value: unknown): string | undefined {
  if (value === undefined || value === null || String(value).trim() === "") return undefined;
  return safeText(name, value);
}

function publicMetadata(value: unknown): PaymentJsonRecord {
  if (value === undefined) return {};
  if (!isRecord(value)) throw new ChinaPaymentContractError("metadata must be an object");
  inspectPaymentData(value, "metadata", false);
  return cloneJson(value);
}

function rejectSensitive(name: string, value: string): void {
  if (RAW_SECRET_RE.test(value)) throw new ChinaPaymentContractError(`${name} contains raw provider secret material`);
  if (CARD_NUMBER_RE.test(value)) throw new ChinaPaymentContractError(`${name} contains possible card data`);
  if (FORBIDDEN_PAYMENT_VALUE_RE.test(value)) {
    throw new ChinaPaymentContractError(`${name} contains forbidden payment data`);
  }
}

function positiveMinor(value: unknown): number {
  const amount = Number(value);
  if (!Number.isSafeInteger(amount) || amount <= 0) throw new ChinaPaymentContractError("amount_minor must be a positive safe integer");
  return amount;
}

function nonNegativeMinor(value: unknown): number {
  const amount = Number(value);
  if (!Number.isSafeInteger(amount) || amount < 0) throw new ChinaPaymentContractError("amount must be a non-negative safe integer");
  return amount;
}

function signedMinor(value: unknown): number {
  const amount = Number(value);
  if (!Number.isSafeInteger(amount)) throw new ChinaPaymentContractError("amount must be a safe integer");
  return amount;
}

function requireDate(value: unknown): string {
  const text = String(value ?? "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || Number.isNaN(Date.parse(`${text}T00:00:00Z`))) {
    throw new ChinaPaymentContractError("bill_date must be YYYY-MM-DD");
  }
  return text;
}

function requireIsoTimestamp(value: unknown): string {
  const text = String(value ?? "");
  if (!text || Number.isNaN(Date.parse(text))) throw new ChinaPaymentContractError("occurred_at must be an ISO timestamp");
  return new Date(text).toISOString();
}

function requireSha256(name: string, value: unknown): string {
  const text = String(value ?? "").toLowerCase();
  if (!SHA256_RE.test(text)) throw new ChinaPaymentContractError(`${name} must be a lowercase SHA-256 digest`);
  return text;
}

function optionalSha256(name: string, value: unknown): string | undefined {
  if (value === undefined || value === null || String(value) === "") return undefined;
  return requireSha256(name, value);
}

function minorToMajor(value: number): string {
  return (value / 100).toFixed(2);
}

function noSideEffects(): PaymentJsonRecord {
  return {
    provider_called: false,
    network_io_performed: false,
    real_charge_possible: false,
    refund_submitted: false,
  };
}

function publicSafe<T extends PaymentJsonRecord>(value: T): T {
  inspectPublic(value, "$");
  return cloneJson(value);
}

function inspectPublic(value: unknown, path: string): void {
  inspectPaymentData(value, path, true);
}

function inspectPaymentData(value: unknown, path: string, allowSafetyMarkers: boolean): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => inspectPaymentData(item, `${path}[${index}]`, allowSafetyMarkers));
    return;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      if (item === undefined) continue;
      const normalized = canonicalPaymentFieldName(key);
      if (isForbiddenPaymentField(key) && !(allowSafetyMarkers && isPaymentSafetyMarker(normalized, item))) {
        throw new ChinaPaymentContractError(`public payment object contains forbidden payment data field at ${path}.${key}`);
      }
      if (
        SENSITIVE_KEY_RE.test(normalized)
        && normalized !== "domestic_bank_card"
        && normalized !== "signature_header_shape"
        && normalized !== "secret_resolution_deferred"
        && normalized !== "provider_token"
        && !normalized.endsWith("_ref")
        && !normalized.endsWith("_present")
        && !normalized.endsWith("_collected")
        && !normalized.endsWith("_collected_by_sdk")
        && !normalized.includes("included")
        && !normalized.includes("headers")
      ) {
        throw new ChinaPaymentContractError(`public payment object contains sensitive payment field at ${path}.${key}`);
      }
      if (normalized.endsWith("_sha256") && typeof item === "string" && SHA256_RE.test(item)) continue;
      inspectPaymentData(item, `${path}.${key}`, allowSafetyMarkers);
    }
    return;
  }
  if (typeof value === "string") rejectSensitive(path, value);
}

function canonicalPaymentFieldName(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function isForbiddenPaymentField(value: string): boolean {
  const canonical = canonicalPaymentFieldName(value);
  return FORBIDDEN_PAYMENT_FIELD_NAMES.has(canonical)
    || canonical.startsWith("kyc_")
    || canonical.startsWith("raw_kyc_")
    || canonical.startsWith("cardholder_")
    || canonical.startsWith("card_holder_")
    || canonical.endsWith("_cryptogram")
    || canonical.endsWith("_track_data");
}

function isPaymentSafetyMarker(canonical: string, value: unknown): boolean {
  return typeof value === "boolean" && (
    canonical.endsWith("_present")
    || canonical.endsWith("_collected")
    || canonical.endsWith("_collected_by_sdk")
    || canonical.endsWith("_included")
  );
}

function eventKey(tenantId: string, projectId: string, provider: PaymentProvider, providerEventId: string): string {
  return stableJson({ tenant_id: tenantId, project_id: projectId, provider, provider_event_id: providerEventId });
}

function fingerprintFor(value: unknown): string {
  return sha256(Buffer.from(stableJson(value), "utf8"));
}

function sha256(value: Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function stableJson(value: unknown): string {
  return JSON.stringify(sortJson(value));
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJson);
  if (isRecord(value)) {
    const result: PaymentJsonRecord = {};
    for (const key of Object.keys(value).sort()) {
      if (value[key] !== undefined) result[key] = sortJson(value[key]);
    }
    return result;
  }
  return value;
}

function firstString(value: unknown): string {
  return stringArray(value)[0] ?? "";
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function isRecord(value: unknown): value is PaymentJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
