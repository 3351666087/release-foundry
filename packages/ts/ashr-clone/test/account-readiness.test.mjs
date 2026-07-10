import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  ACCOUNT_READINESS_ENVIRONMENTS,
  ACCOUNT_READINESS_PROVIDERS,
  ACCOUNT_READINESS_RECEIPT_VERSION,
  ACCOUNT_READINESS_STATUSES,
  AccountReadinessError,
  build_receipt_template,
  validate_account_readiness_receipt,
} from "../dist/index.js";

const packageRoot = new URL("../", import.meta.url);
const baseReceipt = () => ({
  schema_version: ACCOUNT_READINESS_RECEIPT_VERSION,
  provider: "github_oauth",
  application_id_suffix: "a1b2",
  application_fingerprint: `sha256:${"a".repeat(64)}`,
  environment: "sandbox",
  redirect_uris: ["http://localhost:8080/callback"],
  status: "configured",
  observed_at: "2026-07-10T12:00:00+08:00",
  receipt_id: "operator:github:123",
  operator_note: "Public status only",
});

test("exports the complete account-readiness vocabulary", () => {
  assert.equal(ACCOUNT_READINESS_RECEIPT_VERSION, "a1-human-operator-receipt-v1");
  assert.deepEqual(
    [...ACCOUNT_READINESS_PROVIDERS],
    ["alipay_login", "alipay_merchant", "domestic_bank_card", "github_oauth", "google_oauth", "wechat_open_login", "wechat_pay"],
  );
  assert.deepEqual([...ACCOUNT_READINESS_ENVIRONMENTS], ["production", "sandbox"]);
  assert.equal(ACCOUNT_READINESS_STATUSES.includes("configured"), true);
});

for (const provider of ACCOUNT_READINESS_PROVIDERS) {
  test(`builds a public-safe ${provider} template`, () => {
    const receipt = build_receipt_template(provider);
    assert.equal(receipt.provider, provider);
    assert.equal(receipt.contains_secrets, false);
    assert.equal(receipt.contains_payment_card_data, false);
    assert.equal(receipt.contains_kyc_material, false);
    assert.match(receipt.application_fingerprint, /^sha256:[0-9a-f]{64}$/u);
  });
}

test("normalizes public fields and sandbox localhost", () => {
  const receipt = validate_account_readiness_receipt(baseReceipt());
  assert.equal(receipt.environment, "sandbox");
  assert.deepEqual(receipt.redirect_uris, ["http://localhost:8080/callback"]);
  assert.equal(receipt.contains_secrets, false);
});

test("production requires HTTPS and login providers require redirects", () => {
  assert.throws(
    () => validate_account_readiness_receipt({ ...baseReceipt(), environment: "production" }),
    /must use HTTPS/u,
  );
  assert.throws(
    () => validate_account_readiness_receipt({ ...baseReceipt(), redirect_uris: [] }),
    /require at least one redirect/u,
  );
});

test("rejects unsupported fields, status, fingerprints, and timezone-free timestamps", () => {
  assert.throws(() => validate_account_readiness_receipt({ ...baseReceipt(), unexpected: true }), /unsupported receipt fields/u);
  assert.throws(() => validate_account_readiness_receipt({ ...baseReceipt(), status: "ready" }), /unsupported status/u);
  assert.throws(() => validate_account_readiness_receipt({ ...baseReceipt(), application_fingerprint: "sha256:bad" }), /64 lowercase hex/u);
  assert.throws(() => validate_account_readiness_receipt({ ...baseReceipt(), observed_at: "2026-07-10T12:00:00" }), /with timezone/u);
});

for (const [field, value] of [
  ["client_secret", "do-not-store"],
  ["access_token", "do-not-store"],
  ["private_key", "-----BEGIN PRIVATE KEY-----"],
  ["card_number", "4111111111111111"],
  ["cvv", "123"],
  ["kyc_document", "identity material"],
]) {
  test(`rejects forbidden ${field} field without echoing its value`, () => {
    let thrown;
    try {
      validate_account_readiness_receipt({ ...baseReceipt(), [field]: value });
    } catch (error) {
      thrown = error;
    }
    assert.ok(thrown instanceof AccountReadinessError);
    assert.equal(thrown.message.includes(value), false);
  });
}

test("rejects PAN and KYC material embedded in public notes", () => {
  assert.throws(
    () => validate_account_readiness_receipt({ ...baseReceipt(), operator_note: "card 4111 1111 1111 1111" }),
    /payment-card number/u,
  );
  assert.throws(
    () => validate_account_readiness_receipt({ ...baseReceipt(), operator_note: "\u8eab\u4efd\u8bc1\u626b\u63cf" }),
    /sensitive value/u,
  );
});

test("CLI creates templates and validates PowerShell UTF-8 BOM receipts", () => {
  const template = spawnSync(
    process.execPath,
    ["dist/account-readiness-cli.js", "template", "--provider", "wechat_pay", "--environment", "production"],
    { cwd: packageRoot, encoding: "utf8" },
  );
  assert.equal(template.status, 0, template.stderr);
  assert.equal(JSON.parse(template.stdout).provider, "wechat_pay");

  const directory = mkdtempSync(join(tmpdir(), "ashr-account-readiness-"));
  const file = join(directory, "receipt.json");
  writeFileSync(file, `\uFEFF${JSON.stringify(baseReceipt())}`, "utf8");
  const validated = spawnSync(
    process.execPath,
    ["dist/account-readiness-cli.js", "validate", "--file", file],
    { cwd: packageRoot, encoding: "utf8" },
  );
  assert.equal(validated.status, 0, validated.stderr);
  assert.equal(JSON.parse(validated.stdout).provider, "github_oauth");
});

test("CLI rejection never echoes a supplied secret", () => {
  const directory = mkdtempSync(join(tmpdir(), "ashr-account-readiness-secret-"));
  const file = join(directory, "receipt.json");
  const secret = "super-private-value";
  writeFileSync(file, JSON.stringify({ ...baseReceipt(), client_secret: secret }), "utf8");
  const rejected = spawnSync(
    process.execPath,
    ["dist/account-readiness-cli.js", "validate", "--file", file],
    { cwd: packageRoot, encoding: "utf8" },
  );
  assert.equal(rejected.status, 2);
  assert.equal(rejected.stderr.includes(secret), false);
  assert.equal(JSON.parse(rejected.stderr).status, "rejected");
});
