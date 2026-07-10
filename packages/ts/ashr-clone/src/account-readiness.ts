import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const ACCOUNT_READINESS_RECEIPT_VERSION = "a1-human-operator-receipt-v1";
export const ACCOUNT_READINESS_PROVIDERS = [
  "alipay_login",
  "alipay_merchant",
  "domestic_bank_card",
  "github_oauth",
  "google_oauth",
  "wechat_open_login",
  "wechat_pay",
] as const;
export const ACCOUNT_READINESS_ENVIRONMENTS = ["production", "sandbox"] as const;
export const ACCOUNT_READINESS_STATUSES = [
  "approved",
  "applied",
  "blocked",
  "configured",
  "not_started",
  "rejected",
  "revoked",
  "under_review",
] as const;

export type AccountReadinessProvider = (typeof ACCOUNT_READINESS_PROVIDERS)[number];
export type AccountReadinessEnvironment = (typeof ACCOUNT_READINESS_ENVIRONMENTS)[number];
export type AccountReadinessStatus = (typeof ACCOUNT_READINESS_STATUSES)[number];

export interface AccountReadinessReceipt {
  schema_version: typeof ACCOUNT_READINESS_RECEIPT_VERSION;
  provider: AccountReadinessProvider;
  environment: AccountReadinessEnvironment;
  status: AccountReadinessStatus;
  redirect_uris: string[];
  application_id_suffix?: string;
  application_fingerprint?: string;
  observed_at: string;
  submitted_at?: string;
  reviewed_at?: string;
  updated_at?: string;
  receipt_id?: string;
  operator_note?: string;
  contains_secrets: false;
  contains_payment_card_data: false;
  contains_kyc_material: false;
}

type JsonRecord = Record<string, unknown>;

const PROVIDER_SET = new Set<string>(ACCOUNT_READINESS_PROVIDERS);
const ENVIRONMENT_SET = new Set<string>(ACCOUNT_READINESS_ENVIRONMENTS);
const STATUS_SET = new Set<string>(ACCOUNT_READINESS_STATUSES);
const CALLBACK_PROVIDERS = new Set<AccountReadinessProvider>([
  "github_oauth",
  "google_oauth",
  "wechat_open_login",
  "alipay_login",
]);
const ALLOWED_FIELDS = new Set([
  "schema_version",
  "provider",
  "environment",
  "status",
  "redirect_uris",
  "application_id_suffix",
  "application_fingerprint",
  "observed_at",
  "submitted_at",
  "reviewed_at",
  "updated_at",
  "receipt_id",
  "operator_note",
]);
const TIMESTAMP_FIELDS = ["observed_at", "submitted_at", "reviewed_at", "updated_at"] as const;
const FORBIDDEN_KEY_PARTS = [
  "secret",
  "password",
  "passwd",
  "token",
  "private_key",
  "api_key",
  "authorization_code",
  "otp",
  "cvv",
  "cvc",
  "pin",
  "pan",
  "card_number",
  "track_data",
  "cryptogram",
  "id_card",
  "identity_card",
  "passport",
  "business_license",
  "kyc_document",
  "kyc_file",
];
const FORBIDDEN_VALUE_PATTERNS = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/iu,
  /\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}/iu,
  /\b(?:client_secret|access_token|refresh_token|api_key)\s*[:=]/iu,
  /\b(?:cvv|cvc|otp|pin)\s*[:=]\s*\S+/iu,
  /(?:\u8eab\u4efd\u8bc1|\u62a4\u7167|\u8425\u4e1a\u6267\u7167|KYC)\s*(?:\u626b\u63cf|\u7167\u7247|\u6587\u4ef6|\u53f7\u7801|\u53f7)/iu,
];
const SAFE_ID_SUFFIX = /^[A-Za-z0-9_-]{4,16}$/u;
const SHA256_FINGERPRINT = /^sha256:[0-9a-f]{64}$/u;
const RECEIPT_ID = /^[A-Za-z0-9._:-]{6,128}$/u;
const TIMEZONE_SUFFIX = /(?:Z|[+-]\d{2}:\d{2})$/u;

export class AccountReadinessError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AccountReadinessError";
  }
}

export function validate_account_readiness_receipt(payload: unknown): AccountReadinessReceipt {
  if (!isRecord(payload)) {
    throw new AccountReadinessError("receipt must be a JSON object");
  }
  rejectSensitiveMaterial(payload);

  const unknown = Object.keys(payload).filter((key) => !ALLOWED_FIELDS.has(key)).sort();
  if (unknown.length > 0) {
    throw new AccountReadinessError(`unsupported receipt fields: ${unknown.join(", ")}`);
  }
  if (
    payload.schema_version !== undefined
    && payload.schema_version !== ACCOUNT_READINESS_RECEIPT_VERSION
  ) {
    throw new AccountReadinessError("unsupported receipt schema_version");
  }

  const provider = requiredString(payload, "provider");
  const environment = requiredString(payload, "environment");
  const status = requiredString(payload, "status");
  if (!PROVIDER_SET.has(provider)) {
    throw new AccountReadinessError("unsupported provider");
  }
  if (!ENVIRONMENT_SET.has(environment)) {
    throw new AccountReadinessError("environment must be sandbox or production");
  }
  if (!STATUS_SET.has(status)) {
    throw new AccountReadinessError("unsupported status");
  }

  const applicationIdSuffix = optionalString(payload, "application_id_suffix");
  const applicationFingerprint = optionalString(payload, "application_fingerprint");
  if (applicationIdSuffix === undefined && applicationFingerprint === undefined) {
    throw new AccountReadinessError("application_id_suffix or application_fingerprint is required");
  }
  if (applicationIdSuffix !== undefined && !SAFE_ID_SUFFIX.test(applicationIdSuffix)) {
    throw new AccountReadinessError("application_id_suffix must contain 4-16 safe suffix characters");
  }
  if (applicationFingerprint !== undefined && !SHA256_FINGERPRINT.test(applicationFingerprint)) {
    throw new AccountReadinessError("application_fingerprint must use sha256:<64 lowercase hex>");
  }

  if (!Array.isArray(payload.redirect_uris)) {
    throw new AccountReadinessError("redirect_uris must be a JSON array");
  }
  if (payload.redirect_uris.length > 10) {
    throw new AccountReadinessError("redirect_uris exceeds the maximum of 10");
  }
  const redirectUris = payload.redirect_uris.map((value) => validateRedirectUri(value, environment));
  if (CALLBACK_PROVIDERS.has(provider as AccountReadinessProvider) && redirectUris.length === 0) {
    throw new AccountReadinessError("login providers require at least one redirect URI");
  }

  const timestamps = new Map<string, string | undefined>();
  for (const field of TIMESTAMP_FIELDS) {
    const value = field === "observed_at" ? requiredString(payload, field) : optionalString(payload, field);
    timestamps.set(field, value === undefined ? undefined : validateTimestamp(value, field));
  }

  const receiptId = optionalString(payload, "receipt_id");
  if (receiptId !== undefined && !RECEIPT_ID.test(receiptId)) {
    throw new AccountReadinessError("receipt_id contains unsupported characters");
  }
  const operatorNote = optionalString(payload, "operator_note");
  if (operatorNote !== undefined && operatorNote.length > 500) {
    throw new AccountReadinessError("operator_note exceeds 500 characters");
  }

  return compactReceipt({
    schema_version: ACCOUNT_READINESS_RECEIPT_VERSION,
    provider: provider as AccountReadinessProvider,
    environment: environment as AccountReadinessEnvironment,
    status: status as AccountReadinessStatus,
    redirect_uris: redirectUris,
    application_id_suffix: applicationIdSuffix,
    application_fingerprint: applicationFingerprint,
    observed_at: timestamps.get("observed_at")!,
    submitted_at: timestamps.get("submitted_at"),
    reviewed_at: timestamps.get("reviewed_at"),
    updated_at: timestamps.get("updated_at"),
    receipt_id: receiptId,
    operator_note: operatorNote,
    contains_secrets: false,
    contains_payment_card_data: false,
    contains_kyc_material: false,
  });
}

export function build_receipt_template(
  provider: string,
  environment: string = "sandbox",
): AccountReadinessReceipt {
  if (!PROVIDER_SET.has(provider)) {
    throw new AccountReadinessError("unsupported provider");
  }
  if (!ENVIRONMENT_SET.has(environment)) {
    throw new AccountReadinessError("environment must be sandbox or production");
  }
  const typedProvider = provider as AccountReadinessProvider;
  return {
    schema_version: ACCOUNT_READINESS_RECEIPT_VERSION,
    provider: typedProvider,
    application_id_suffix: "last4",
    application_fingerprint: `sha256:${createHash("sha256").update(`${provider}:replace-with-local-id`).digest("hex")}`,
    environment: environment as AccountReadinessEnvironment,
    redirect_uris: CALLBACK_PROVIDERS.has(typedProvider)
      ? ["https://app.example.com/oauth/callback"]
      : [],
    status: "not_started",
    observed_at: "2026-01-01T00:00:00+08:00",
    receipt_id: `operator:${provider}:replace`,
    operator_note: "Non-sensitive status only. Do not include secrets, payment-card data, or KYC materials.",
    contains_secrets: false,
    contains_payment_card_data: false,
    contains_kyc_material: false,
  };
}

export function load_account_readiness_receipt(path: string): AccountReadinessReceipt {
  const resolved = resolve(path);
  const parts = resolved.split(/[\\/]+/u).map((part) => part.toLowerCase());
  if (parts.includes(".secrets") || parts.includes("private_refs")) {
    throw new AccountReadinessError("refusing to read receipt from a secret/private evidence directory");
  }
  let parsed: unknown;
  try {
    const text = readFileSync(resolved, "utf8").replace(/^\uFEFF/u, "");
    parsed = JSON.parse(text);
  } catch (error) {
    const kind = error instanceof SyntaxError ? "invalid JSON" : "unable to read receipt file";
    throw new AccountReadinessError(kind);
  }
  return validate_account_readiness_receipt(parsed);
}

function compactReceipt(receipt: AccountReadinessReceipt): AccountReadinessReceipt {
  return Object.fromEntries(
    Object.entries(receipt).filter(([, value]) => value !== undefined),
  ) as unknown as AccountReadinessReceipt;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(payload: JsonRecord, field: string): string {
  const value = optionalString(payload, field);
  if (value === undefined) {
    throw new AccountReadinessError(`${field} is required`);
  }
  return value;
}

function optionalString(payload: JsonRecord, field: string): string | undefined {
  const value = payload[field];
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value !== "string" || value.trim() === "") {
    throw new AccountReadinessError(`${field} must be a non-empty string`);
  }
  return value.trim();
}

function validateRedirectUri(value: unknown, environment: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new AccountReadinessError("redirect URI must be a non-empty string");
  }
  const uri = value.trim();
  let parsed: URL;
  try {
    parsed = new URL(uri);
  } catch {
    throw new AccountReadinessError("redirect URI must include a host");
  }
  if (parsed.username !== "" || parsed.password !== "" || parsed.hash !== "") {
    throw new AccountReadinessError("redirect URI must not include userinfo or fragments");
  }
  const localhost = new Set(["localhost", "127.0.0.1", "[::1]"]).has(parsed.hostname);
  if (parsed.protocol !== "https:" && !(environment === "sandbox" && localhost && parsed.protocol === "http:")) {
    throw new AccountReadinessError("redirect URI must use HTTPS; sandbox localhost may use HTTP");
  }
  if (parsed.hostname === "") {
    throw new AccountReadinessError("redirect URI must include a host");
  }
  return uri;
}

function validateTimestamp(value: string, field: string): string {
  if (!TIMEZONE_SUFFIX.test(value) || Number.isNaN(Date.parse(value))) {
    throw new AccountReadinessError(`${field} must be an ISO-8601 timestamp with timezone`);
  }
  return value;
}

function rejectSensitiveMaterial(value: unknown, path: string = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((nested, index) => rejectSensitiveMaterial(nested, `${path}[${index}]`));
    return;
  }
  if (isRecord(value)) {
    for (const [key, nested] of Object.entries(value)) {
      const normalized = key.trim().toLowerCase().replaceAll("-", "_");
      if (FORBIDDEN_KEY_PARTS.some((part) => normalized.includes(part))) {
        throw new AccountReadinessError(`sensitive field is forbidden at ${path}`);
      }
      rejectSensitiveMaterial(nested, `${path}.${key}`);
    }
    return;
  }
  if (typeof value !== "string") {
    return;
  }
  if (FORBIDDEN_VALUE_PATTERNS.some((pattern) => pattern.test(value))) {
    throw new AccountReadinessError(`sensitive value is forbidden at ${path}`);
  }
  for (const candidate of value.match(/(?:\d[ -]?){13,19}/gu) ?? []) {
    const digits = candidate.replace(/\D/gu, "");
    if (digits.length >= 13 && digits.length <= 19 && luhnValid(digits)) {
      throw new AccountReadinessError(`payment-card number is forbidden at ${path}`);
    }
  }
}

function luhnValid(digits: string): boolean {
  let total = 0;
  const parity = digits.length % 2;
  for (const [index, character] of [...digits].entries()) {
    let number = Number(character);
    if (index % 2 === parity) {
      number *= 2;
      if (number > 9) {
        number -= 9;
      }
    }
    total += number;
  }
  return total % 10 === 0;
}
