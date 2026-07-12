import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as sdk from "../dist/index.js";

test("TS publishes every Python top-level A1 entry point with executable aliases", () => {
  for (const name of [
    "account_connection_contract_manifest",
    "api_record_to_cases",
    "assert_capability_matrix_safe",
    "build_capability_matrix",
    "build_default_request_input_schema",
    "build_object_manifest",
    "build_private_evidence_index_from_dir",
    "build_run_fixture",
    "build_vm_stream",
    "canonical_identity_delivery_json",
    "coerce_agent_input",
    "identity_delivery_protocol_contract_manifest",
    "merge_evidence_indices",
    "replay_observations",
    "stable_id",
    "summarize_quota_error",
    "unified_identity_contract_manifest",
    "validate_identity_delivery_task",
    "write_response_field_map_markdown",
  ]) {
    assert.equal(typeof sdk[name], "function", `${name} is not executable`);
  }
  assert.equal(sdk.UnifiedIdentityClient, sdk.UnifiedIdentityHttpClient);
  assert.equal(sdk.AccountConnectionContractError, sdk.AccountConnectionError);
  assert.deepEqual(sdk.GOOGLE_ACCOUNT_CONNECTION_SCOPES, ["openid", "email", "profile"]);
  assert.deepEqual(sdk.GOOGLE_OIDC_ISSUERS, ["https://accounts.google.com", "accounts.google.com"]);
});

test("snake_case identity and API helpers preserve the canonical behavior", () => {
  assert.deepEqual(sdk.account_connection_contract_manifest(), sdk.accountConnectionContractManifest());
  assert.deepEqual(sdk.unified_identity_contract_manifest(), sdk.unifiedIdentityContractManifest());
  assert.equal(sdk.identity_account_route("acct_1"), sdk.identityAccountRoute("acct_1"));
  assert.equal(sdk.normalize_identity_provider(" GitHub "), "github");
  assert.equal(sdk.normalize_verification_provider(" EMAIL "), "email");
  assert.equal(sdk.normalize_verification_purpose(" BINDING "), "binding");
  assert.throws(() => sdk.normalize_verification_provider("github"), /must be one of/u);
  assert.deepEqual(sdk.build_default_request_input_schema(), sdk.buildDefaultRequestInputSchema());
});

test("stable_id and observation replay match Python deterministic semantics", () => {
  assert.equal(sdk.stable_id("evt", "run", 1, { b: 2, a: 1 }), "evt_fcc69dbf242c1b4c");
  const events = [
    { seq: 1, observation: { kind: "message", text: "second", data: {}, channel: "assistant", status: "ok" } },
    { seq: 0, observation: { kind: "message", text: "first", data: {}, channel: "user", status: "ok" } },
  ];
  assert.deepEqual(sdk.replay_observations(events).map((item) => item.text), ["first", "second"]);
  assert.throws(() => sdk.replay_observations([{ seq: 0 }]), /observation must be an object/u);
});

test("TS build removes stale dist before compiling source", () => {
  const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(packageJson.scripts.clean, /rmSync\('dist'/u);
  assert.equal(packageJson.scripts.prebuild, "npm run clean");
  assert.equal(packageJson.scripts.test.startsWith("npm run build"), true);
  assert.deepEqual(Object.keys(packageJson.exports).sort(), [
    ".",
    "./account-connections",
    "./account-readiness",
    "./api-client",
    "./billing",
    "./browser-session",
    "./calibrate",
    "./capability-matrix",
    "./china-payments",
    "./cloud-queue",
    "./commercial",
    "./dataset-adapter",
    "./delivery-protocol",
    "./evidence",
    "./github-oauth",
    "./oauth",
    "./provider-adapter",
    "./python-parity",
    "./runner",
    "./saas",
    "./session-lifecycle",
    "./storage",
    "./stripe-executor",
    "./trace",
    "./unified-identity",
  ]);
  for (const target of Object.values(packageJson.exports)) {
    assert.equal(readFileSync(new URL(`../${target.import}`, import.meta.url), "utf8").length > 0, true);
    assert.equal(readFileSync(new URL(`../${target.types}`, import.meta.url), "utf8").length > 0, true);
  }
});
