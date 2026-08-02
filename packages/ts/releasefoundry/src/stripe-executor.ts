import { createHash } from "node:crypto";

export const STRIPE_EXECUTOR_SCHEMA_VERSION = "releasefoundry.stripe_test_hosted_executor.v1";

type JsonRecord = Record<string, unknown>;

export class StripeExecutorContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StripeExecutorContractError";
  }
}

export interface SecretRefResolver {
  resolveSecret(reference: string): string | Promise<string>;
}

export class EnvSecretRefResolver implements SecretRefResolver {
  readonly #environment: Readonly<Record<string, string | undefined>>;

  constructor(environment: Readonly<Record<string, string | undefined>> = process.env) {
    this.#environment = environment;
  }

  resolveSecret(reference: string): string {
    const match = /^env:([A-Za-z_][A-Za-z0-9_]*)$/.exec(reference);
    if (!match) throw new StripeExecutorContractError("only valid env secret references are supported");
    const value = this.#environment[match[1]];
    if (typeof value !== "string" || value.length === 0) {
      throw new StripeExecutorContractError("secret reference could not be resolved");
    }
    return value;
  }
}

export interface StripeTransportContext {
  apiSecret: string;
  idempotencyKey: string;
  mode: "test";
  tenantId: string;
  projectId: string;
}

export interface StripeWebhookTransportRequest {
  rawBody: Uint8Array;
  signatureHeader: string;
  webhookSecret: string;
  mode: "test";
}

export interface StripeWebhookTransportResult {
  verified: boolean;
  eventIdRef?: string | null;
  event_id_ref?: string | null;
  eventType?: string | null;
  event_type?: string | null;
  livemode?: boolean | null;
  reasonCodes?: string[];
  reason_codes?: string[];
  [key: string]: unknown;
}

export interface StripeHostedTransport {
  createCheckoutSession(request: JsonRecord, context: StripeTransportContext): Promise<JsonRecord>;
  createBillingPortalSession(request: JsonRecord, context: StripeTransportContext): Promise<JsonRecord>;
  verifyWebhook(request: StripeWebhookTransportRequest): Promise<StripeWebhookTransportResult>;
}

export interface StripeHostedSessionResult extends JsonRecord {
  schema_version: typeof STRIPE_EXECUTOR_SCHEMA_VERSION;
  plan_type: "hosted_payment_execution";
  provider: "stripe";
  hosted_surface: "stripe_checkout" | "stripe_billing_portal";
  operation: "checkout.sessions.create" | "billing_portal.sessions.create";
  mode: "test";
  tenant_id: string;
  project_id: string;
  idempotency_key: string;
  request_fingerprint_sha256: string;
  provider_session_id: string;
  hosted_url: string;
  replayed: boolean;
  side_effects: {
    provider_called: true;
    checkout_or_portal_called: true;
    real_charge_possible: false;
  };
  secret_value_present: false;
  raw_card_data_present: false;
  raw_provider_response_included: false;
}

export interface StripeWebhookVerificationEnvelope extends JsonRecord {
  schema_version: typeof STRIPE_EXECUTOR_SCHEMA_VERSION;
  plan_type: "signature_verification";
  provider: "stripe";
  mode: "test";
  verified: boolean;
  event_id_ref: string | null;
  event_type: string | null;
  livemode: boolean | null;
  payload_sha256: string;
  reason_codes: string[];
  signature_header_shape: {
    expected_headers: ["stripe-signature"];
    provided_headers: string[];
    missing_headers: string[];
    raw_header_values_included: false;
  };
  integration_hook: {
    interface: "StripeHostedTransport.verifyWebhook";
    verifier_called: boolean;
  };
  raw_body_included: false;
  secret_value_present: false;
}

interface RegistryEntry<T> {
  fingerprint: string;
  result: Promise<T>;
}

export class IdempotencyFingerprintRegistry<T = StripeHostedSessionResult> {
  readonly #entries = new Map<string, RegistryEntry<T>>();

  async executeOnce(scope: string, fingerprint: string, producer: () => Promise<T>): Promise<{ result: T; replayed: boolean }> {
    const existing = this.#entries.get(scope);
    if (existing) {
      if (existing.fingerprint !== fingerprint) {
        throw new StripeExecutorContractError("idempotency key was reused with a different request fingerprint");
      }
      return { result: await existing.result, replayed: true };
    }

    const result = producer();
    this.#entries.set(scope, { fingerprint, result });
    try {
      return { result: await result, replayed: false };
    } catch (error) {
      if (this.#entries.get(scope)?.result === result) this.#entries.delete(scope);
      throw error;
    }
  }

  get size(): number {
    return this.#entries.size;
  }
}

export interface StripeTestHostedExecutorOptions {
  secretResolver: SecretRefResolver;
  transport: StripeHostedTransport;
  registry?: IdempotencyFingerprintRegistry<StripeHostedSessionResult>;
}

export interface StripeWebhookVerificationInput {
  rawBody: Uint8Array;
  headers?: Readonly<Record<string, string | undefined>>;
  signatureHeader?: string;
  signature_header?: string;
  verificationKeyRef?: string;
  verification_key_ref?: string;
  mode?: string;
}

interface NormalizedPlan {
  hostedSurface: "stripe_checkout" | "stripe_billing_portal";
  operation: "checkout.sessions.create" | "billing_portal.sessions.create";
  mode: "test";
  tenantId: string;
  projectId: string;
  credentialRef: string;
  idempotencyKey: string;
  request: JsonRecord;
  fingerprint: string;
}

export class StripeTestHostedExecutor {
  readonly #secretResolver: SecretRefResolver;
  readonly #transport: StripeHostedTransport;
  readonly #registry: IdempotencyFingerprintRegistry<StripeHostedSessionResult>;

  constructor(options: StripeTestHostedExecutorOptions) {
    if (!options?.secretResolver || !options.transport) {
      throw new StripeExecutorContractError("secretResolver and transport are required");
    }
    this.#secretResolver = options.secretResolver;
    this.#transport = options.transport;
    this.#registry = options.registry ?? new IdempotencyFingerprintRegistry<StripeHostedSessionResult>();
  }

  async execute(plan: Readonly<JsonRecord>): Promise<StripeHostedSessionResult> {
    const normalized = normalizePlan(plan);
    const scope = [
      "stripe",
      normalized.mode,
      normalized.tenantId,
      normalized.projectId,
      normalized.operation,
      normalized.idempotencyKey,
    ].join(":");

    const execution = await this.#registry.executeOnce(scope, normalized.fingerprint, async () => {
      const apiSecret = await this.#secretResolver.resolveSecret(normalized.credentialRef);
      if (typeof apiSecret !== "string" || apiSecret.length === 0) {
        throw new StripeExecutorContractError("secret resolver returned an invalid value");
      }
      const context: StripeTransportContext = {
        apiSecret,
        idempotencyKey: normalized.idempotencyKey,
        mode: "test",
        tenantId: normalized.tenantId,
        projectId: normalized.projectId,
      };
      const providerResult = normalized.operation === "checkout.sessions.create"
        ? await this.#transport.createCheckoutSession(cloneJson(normalized.request), context)
        : await this.#transport.createBillingPortalSession(cloneJson(normalized.request), context);
      return publicSessionResult(normalized, providerResult);
    });

    return { ...execution.result, replayed: execution.replayed };
  }

  async verifyWebhook(input: StripeWebhookVerificationInput): Promise<StripeWebhookVerificationEnvelope> {
    if (String(input.mode ?? "test").trim().toLowerCase() !== "test") {
      throw new StripeExecutorContractError("live Stripe webhook verification is not supported by the test executor");
    }
    if (!(input.rawBody instanceof Uint8Array) || input.rawBody.byteLength === 0) {
      throw new StripeExecutorContractError("webhook verification requires non-empty raw bytes");
    }

    const payloadSha256 = sha256(input.rawBody);
    const normalizedHeaders = normalizeHeaders(input.headers ?? {});
    const explicitSignature = stringValue(input.signatureHeader ?? input.signature_header);
    const signatureHeader = explicitSignature || normalizedHeaders["stripe-signature"] || "";
    const providedHeaders = Object.keys(normalizedHeaders).sort();
    if (explicitSignature && !providedHeaders.includes("stripe-signature")) providedHeaders.push("stripe-signature");
    if (!signatureHeader) {
      return webhookEnvelope({
        payloadSha256,
        verified: false,
        eventIdRef: null,
        eventType: null,
        livemode: null,
        reasonCodes: ["missing_signature_headers"],
        providedHeaders,
        missingHeaders: ["stripe-signature"],
        verifierCalled: false,
      });
    }

    const verificationKeyRef = stringValue(input.verificationKeyRef ?? input.verification_key_ref);
    if (!verificationKeyRef) throw new StripeExecutorContractError("verification key reference is required");
    const webhookSecret = await this.#secretResolver.resolveSecret(verificationKeyRef);
    if (typeof webhookSecret !== "string" || webhookSecret.length === 0) {
      throw new StripeExecutorContractError("secret resolver returned an invalid value");
    }
    const result = await this.#transport.verifyWebhook({
      rawBody: input.rawBody,
      signatureHeader,
      webhookSecret,
      mode: "test",
    });
    if (!isRecord(result)) throw new StripeExecutorContractError("webhook verifier returned an unsupported result");

    const livemode = typeof result.livemode === "boolean" ? result.livemode : null;
    const reasons = uniqueStrings(result.reasonCodes ?? result.reason_codes ?? []);
    if (livemode === true) reasons.push("provider_mode_mismatch");
    const reasonCodes = [...new Set(reasons)];
    return webhookEnvelope({
      payloadSha256,
      verified: Boolean(result.verified) && reasonCodes.length === 0,
      eventIdRef: nullableSafeReference(result.eventIdRef ?? result.event_id_ref),
      eventType: nullablePublicString(result.eventType ?? result.event_type),
      livemode,
      reasonCodes,
      providedHeaders,
      missingHeaders: [],
      verifierCalled: true,
    });
  }
}

function normalizePlan(plan: Readonly<JsonRecord>): NormalizedPlan {
  if (!isRecord(plan)) throw new StripeExecutorContractError("Stripe hosted plan must be an object");
  if (stringValue(plan.provider).toLowerCase() !== "stripe") {
    throw new StripeExecutorContractError("only Stripe hosted plans are supported");
  }
  const modeGate = isRecord(plan.mode_gate) ? plan.mode_gate : {};
  const mode = stringValue(plan.mode ?? modeGate.mode).trim().toLowerCase();
  if (mode !== "test") throw new StripeExecutorContractError("live Stripe execution is not supported by the test executor");

  const providerRequest = isRecord(plan.provider_request) ? plan.provider_request : {};
  const requestShape = isRecord(plan.request_shape) ? plan.request_shape : {};
  const operationValue = stringValue(providerRequest.operation ?? requestShape.operation);
  if (operationValue !== "checkout.sessions.create" && operationValue !== "billing_portal.sessions.create") {
    throw new StripeExecutorContractError("unsupported Stripe hosted operation");
  }
  const operation = operationValue;
  const expectedSurface = operation === "checkout.sessions.create" ? "stripe_checkout" : "stripe_billing_portal";
  const suppliedSurface = stringValue(plan.hosted_surface, expectedSurface);
  if (suppliedSurface !== expectedSurface) throw new StripeExecutorContractError("hosted surface does not match Stripe operation");

  const tenantId = requiredPublicString(plan.tenant_id, "tenant_id");
  const projectId = requiredPublicString(plan.project_id, "project_id");
  const credentialRef = requiredPublicString(plan.credential_ref ?? providerRequest.secret_ref, "credential reference");
  validateEnvReference(credentialRef);
  const idempotency = isRecord(plan.idempotency) ? plan.idempotency : {};
  const idempotencyKey = requiredPublicString(plan.idempotency_key ?? idempotency.key, "idempotency key");
  if (!/^[A-Za-z0-9._:-]{8,255}$/.test(idempotencyKey)) {
    throw new StripeExecutorContractError("idempotency key must be 8-255 safe characters");
  }

  const request = buildTransportRequest(plan, providerRequest, requestShape, operation);
  rejectSensitiveRequest(request);
  const fingerprint = sha256(canonicalJson({
    provider: "stripe",
    mode,
    tenant_id: tenantId,
    project_id: projectId,
    idempotency_key: idempotencyKey,
    request_shape: request,
  }));
  return {
    hostedSurface: expectedSurface,
    operation,
    mode: "test",
    tenantId,
    projectId,
    credentialRef,
    idempotencyKey,
    request,
    fingerprint,
  };
}

function buildTransportRequest(
  plan: Readonly<JsonRecord>,
  providerRequest: JsonRecord,
  requestShape: JsonRecord,
  operation: NormalizedPlan["operation"],
): JsonRecord {
  const source = Object.keys(requestShape).length > 0 ? requestShape : providerRequest;
  const request = stripSecretReferences(source);
  request.operation = operation;
  if (operation === "checkout.sessions.create") {
    if (plan.success_url !== undefined) request.success_url = plan.success_url;
    if (plan.cancel_url !== undefined) request.cancel_url = plan.cancel_url;
    const checkoutMode = stringValue(request.checkout_mode ?? request.mode).trim().toLowerCase();
    if (checkoutMode !== "payment" && checkoutMode !== "subscription") {
      throw new StripeExecutorContractError("Stripe Checkout mode must be payment or subscription");
    }
    request.checkout_mode = checkoutMode;
    request.mode = checkoutMode;
    validateHttps(request.success_url, "success_url");
    validateHttps(request.cancel_url, "cancel_url");
  } else {
    if (plan.return_url !== undefined) request.return_url = plan.return_url;
    validateHttps(request.return_url, "return_url");
  }
  return request;
}

function publicSessionResult(normalized: NormalizedPlan, providerResult: JsonRecord): StripeHostedSessionResult {
  if (!isRecord(providerResult)) throw new StripeExecutorContractError("Stripe transport returned an unsupported result");
  const providerSessionId = requiredPublicString(
    providerResult.id ?? providerResult.session_id ?? providerResult.sessionId,
    "provider session id",
  );
  if (!/^[A-Za-z0-9_:-]{3,255}$/.test(providerSessionId)) {
    throw new StripeExecutorContractError("Stripe transport returned an invalid session id");
  }
  const hostedUrl = requiredPublicString(providerResult.url ?? providerResult.hosted_url ?? providerResult.hostedUrl, "hosted url");
  validateHttps(hostedUrl, "hosted url");
  return {
    schema_version: STRIPE_EXECUTOR_SCHEMA_VERSION,
    plan_type: "hosted_payment_execution",
    provider: "stripe",
    hosted_surface: normalized.hostedSurface,
    operation: normalized.operation,
    mode: "test",
    tenant_id: normalized.tenantId,
    project_id: normalized.projectId,
    idempotency_key: normalized.idempotencyKey,
    request_fingerprint_sha256: normalized.fingerprint,
    provider_session_id: providerSessionId,
    hosted_url: hostedUrl,
    replayed: false,
    side_effects: {
      provider_called: true,
      checkout_or_portal_called: true,
      real_charge_possible: false,
    },
    secret_value_present: false,
    raw_card_data_present: false,
    raw_provider_response_included: false,
  };
}

function webhookEnvelope(options: {
  payloadSha256: string;
  verified: boolean;
  eventIdRef: string | null;
  eventType: string | null;
  livemode: boolean | null;
  reasonCodes: string[];
  providedHeaders: string[];
  missingHeaders: string[];
  verifierCalled: boolean;
}): StripeWebhookVerificationEnvelope {
  return {
    schema_version: STRIPE_EXECUTOR_SCHEMA_VERSION,
    plan_type: "signature_verification",
    provider: "stripe",
    mode: "test",
    verified: options.verified,
    event_id_ref: options.eventIdRef,
    event_type: options.eventType,
    livemode: options.livemode,
    payload_sha256: options.payloadSha256,
    reason_codes: options.reasonCodes,
    signature_header_shape: {
      expected_headers: ["stripe-signature"],
      provided_headers: [...new Set(options.providedHeaders)].sort(),
      missing_headers: options.missingHeaders,
      raw_header_values_included: false,
    },
    integration_hook: {
      interface: "StripeHostedTransport.verifyWebhook",
      verifier_called: options.verifierCalled,
    },
    raw_body_included: false,
    secret_value_present: false,
  };
}

function stripSecretReferences(source: JsonRecord): JsonRecord {
  const result: JsonRecord = {};
  for (const [key, value] of Object.entries(source)) {
    if (["secret_ref", "credential_ref", "webhook_secret_ref", "verification_key_ref"].includes(key)) continue;
    result[key] = cloneJson(value);
  }
  return result;
}

function rejectSensitiveRequest(value: unknown, path = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectSensitiveRequest(item, `${path}[${index}]`));
    return;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      const normalizedKey = key.toLowerCase().replaceAll("-", "_");
      if (["card_number", "pan", "cvc", "cvv", "expiry", "api_secret", "api_key", "authorization"].includes(normalizedKey)) {
        throw new StripeExecutorContractError(`sensitive Stripe request field is not allowed at ${path}.${key}`);
      }
      rejectSensitiveRequest(item, `${path}.${key}`);
    }
    return;
  }
  if (typeof value === "string" && (looksLikeSecret(value) || looksLikeCardNumber(value))) {
    throw new StripeExecutorContractError(`sensitive Stripe request value is not allowed at ${path}`);
  }
}

function validateEnvReference(reference: string): void {
  if (!/^env:[A-Za-z_][A-Za-z0-9_]*$/.test(reference)) {
    throw new StripeExecutorContractError("executor requires a valid env secret reference");
  }
}

function validateHttps(value: unknown, field: string): void {
  const text = requiredPublicString(value, field);
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    throw new StripeExecutorContractError(`${field} must be an https URL`);
  }
  if (parsed.protocol !== "https:" || !parsed.hostname) {
    throw new StripeExecutorContractError(`${field} must be an https URL`);
  }
}

function requiredPublicString(value: unknown, field: string): string {
  const text = stringValue(value).trim();
  if (!text) throw new StripeExecutorContractError(`${field} is required`);
  if (looksLikeSecret(text) || looksLikeCardNumber(text)) {
    throw new StripeExecutorContractError(`${field} failed public-safety validation`);
  }
  return text;
}

function nullableSafeReference(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  const text = requiredPublicString(value, "event id reference");
  if (!/^(?:provider-ref|dashboard-ref|event-ref):[A-Za-z0-9._:-]+$/.test(text)) {
    throw new StripeExecutorContractError("event id reference must be an opaque public reference");
  }
  return text;
}

function nullablePublicString(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  return requiredPublicString(value, "event type");
}

function normalizeHeaders(headers: Readonly<Record<string, string | undefined>>): Record<string, string> {
  const normalized: Record<string, string> = {};
  for (const [name, value] of Object.entries(headers)) {
    if (typeof value === "string" && value.length > 0) normalized[name.trim().toLowerCase()] = value;
  }
  return normalized;
}

function uniqueStrings(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.map((value) => String(value).trim()).filter(Boolean))];
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(sortJson(value));
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJson);
  if (!isRecord(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function looksLikeSecret(value: string): boolean {
  return /(?:^|\b)(?:sk|rk)_(?:test|live)_[A-Za-z0-9]{8,}\b/.test(value)
    || /(?:^|\b)whsec_[A-Za-z0-9]{8,}\b/.test(value)
    || /^(?:bearer|basic)\s/i.test(value);
}

function looksLikeCardNumber(value: string): boolean {
  const compact = value.replace(/\D/g, "");
  return compact.length >= 13 && compact.length <= 19 && /(?:\d[ -]*?){13,19}/.test(value);
}

function stringValue(value: unknown, fallback = ""): string {
  return value === undefined || value === null ? fallback : String(value);
}

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneJson<T>(value: T): T {
  if (value === undefined) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}
