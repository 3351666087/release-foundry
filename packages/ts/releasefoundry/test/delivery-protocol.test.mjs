import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { delimiter } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  IDENTITY_DELIVERY_ACCEPTANCE_STATUSES,
  IDENTITY_DELIVERY_ADMIN_ROUTES,
  IDENTITY_DELIVERY_DTO_KINDS,
  IDENTITY_DELIVERY_ERROR_CODES,
  IDENTITY_DELIVERY_FAILURE_CODES,
  IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
  IDENTITY_DELIVERY_STATUSES,
  IdentityDeliveryProtocolError,
  assertPublicIdentityDeliveryPayload,
  canonicalIdentityDeliveryJson,
  identityDeliveryAdminAcceptancesRoute,
  identityDeliveryAdminCollectionRoute,
  identityDeliveryAdminRedriveRoute,
  identityDeliveryAdminRedrivesRoute,
  identityDeliveryAdminTaskRoute,
  identityDeliveryProtocolContractManifest,
  parseIdentityDeliveryCanonicalJson,
  validateIdentityDeliveryAcceptance,
  validateIdentityDeliveryRedriveReceipt,
  validateIdentityDeliveryRedriveRequest,
  validateIdentityDeliveryTask,
} from "../dist/delivery-protocol.js";

const SCHEMA = IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION;

function task(overrides = {}) {
  return {
    schema_version: SCHEMA,
    task_id: "task_001",
    tenant_id: "tenant_001",
    project_id: "project_001",
    challenge_id: "challenge_001",
    channel: "email",
    purpose: "login",
    status: "leased",
    attempt: 1,
    max_attempts: 8,
    lease_generation: 4,
    redrive_count: 0,
    provider_idempotency_key: "identity-delivery:challenge_001:0",
    challenge_expires_at: "2026-07-11T05:10:00.000Z",
    lease_expires_at: "2026-07-11T05:01:00.000Z",
    next_attempt_at: null,
    provider_acceptance_present: false,
    accepted_at: null,
    completed_at: null,
    dead_at: null,
    last_failure_code: null,
    ...overrides,
  };
}

function acceptance(overrides = {}) {
  return {
    schema_version: SCHEMA,
    task_id: "task_001",
    tenant_id: "tenant_001",
    project_id: "project_001",
    challenge_id: "challenge_001",
    status: "provider_accepted",
    attempt: 1,
    lease_generation: 4,
    provider_idempotency_key: "identity-delivery:challenge_001:0",
    provider_acceptance_present: true,
    accepted_at: "2026-07-11T05:00:10.000Z",
    recorded_at: "2026-07-11T05:00:11.000Z",
    failure_code: null,
    ...overrides,
  };
}

function redriveRequest(overrides = {}) {
  return {
    schema_version: SCHEMA,
    task_id: "task_001",
    tenant_id: "tenant_001",
    project_id: "project_001",
    expected_lease_generation: 4,
    actor_id: "account_admin",
    reason_code: "operator_retry",
    request_id: "request_redrive_001",
    ...overrides,
  };
}

function redriveReceipt(overrides = {}) {
  return {
    schema_version: SCHEMA,
    task_id: "task_001",
    tenant_id: "tenant_001",
    project_id: "project_001",
    request_id: "request_redrive_001",
    audit_id: "audit_redrive_001",
    actor_id: "account_admin",
    reason_code: "operator_retry",
    status: "pending",
    previous_lease_generation: 4,
    lease_generation: 5,
    previous_provider_idempotency_key: "identity-delivery:challenge_001:0",
    provider_idempotency_key: "identity-delivery:challenge_001:1",
    redriven_at: "2026-07-11T05:05:00.000Z",
    ...overrides,
  };
}

function assertProtocolError(fn, code) {
  assert.throws(fn, (error) => {
    assert.ok(error instanceof IdentityDeliveryProtocolError);
    assert.equal(error.code, code);
    return true;
  });
}

test("delivery protocol manifest and admin route operations match Python contract", () => {
  const manifest = identityDeliveryProtocolContractManifest();
  assert.equal(manifest.schema_version, SCHEMA);
  assert.deepEqual(manifest.dto_kinds, [...IDENTITY_DELIVERY_DTO_KINDS]);
  assert.deepEqual(manifest.statuses, [...IDENTITY_DELIVERY_STATUSES]);
  assert.deepEqual(manifest.acceptance_statuses, [...IDENTITY_DELIVERY_ACCEPTANCE_STATUSES]);
  assert.deepEqual(manifest.stable_error_codes, [...IDENTITY_DELIVERY_ERROR_CODES]);
  assert.deepEqual(manifest.failure_codes, [...IDENTITY_DELIVERY_FAILURE_CODES]);
  assert.deepEqual(manifest.routes, [...IDENTITY_DELIVERY_ADMIN_ROUTES]);
  assert.ok(Object.values(manifest.invariants).every((value) => value === true));
  assertPublicIdentityDeliveryPayload(manifest);

  assert.equal(
    identityDeliveryAdminCollectionRoute("project_001"),
    "/v1/projects/project_001/admin/identity-deliveries",
  );
  assert.match(identityDeliveryAdminTaskRoute("project_001", "task_001"), /\/task_001$/u);
  assert.match(identityDeliveryAdminAcceptancesRoute("project_001", "task_001"), /\/acceptances$/u);
  assert.match(identityDeliveryAdminRedriveRoute("project_001", "task_001"), /\/redrive$/u);
  assert.match(identityDeliveryAdminRedrivesRoute("project_001", "task_001"), /\/redrives$/u);
});

test("task validator enforces lease, stable retry key, acceptance, ambiguity, and terminal states", () => {
  const leased = validateIdentityDeliveryTask(task());
  const retry = validateIdentityDeliveryTask(task({
    status: "retry",
    lease_expires_at: null,
    next_attempt_at: "2026-07-11T05:02:00.000Z",
    last_failure_code: "provider_timeout",
  }));
  const accepted = validateIdentityDeliveryTask(task({
    status: "provider_accepted",
    lease_expires_at: null,
    provider_acceptance_present: true,
    accepted_at: "2026-07-11T05:00:10.000Z",
  }));
  const delivered = validateIdentityDeliveryTask(task({
    status: "delivered",
    lease_expires_at: null,
    provider_acceptance_present: true,
    accepted_at: "2026-07-11T05:00:10.000Z",
    completed_at: "2026-07-11T05:00:12.000Z",
  }));
  const ambiguous = validateIdentityDeliveryTask(task({
    status: "ambiguous",
    lease_expires_at: null,
    last_failure_code: "provider_result_ambiguous",
  }));
  const dead = validateIdentityDeliveryTask(task({
    status: "dead",
    lease_expires_at: null,
    dead_at: "2026-07-11T05:03:00.000Z",
    last_failure_code: "attempts_exhausted",
  }));

  assert.equal(retry.provider_idempotency_key, leased.provider_idempotency_key);
  assert.equal(accepted.provider_acceptance_present, true);
  assert.equal(delivered.completed_at, "2026-07-11T05:00:12.000Z");
  assert.equal(ambiguous.provider_acceptance_present, false);
  assert.equal(dead.status, "dead");

  for (const payload of [
    task({ status: "leased", lease_expires_at: null }),
    task({ status: "retry", lease_expires_at: null }),
    task({
      status: "ambiguous",
      lease_expires_at: null,
      provider_acceptance_present: true,
      accepted_at: "2026-07-11T05:00:10.000Z",
      last_failure_code: "provider_result_ambiguous",
    }),
  ]) {
    assertProtocolError(() => validateIdentityDeliveryTask(payload), "identity_delivery_status_conflict");
  }
});

test("acceptance validator never upgrades ambiguous provider results", () => {
  assert.equal(validateIdentityDeliveryAcceptance(acceptance()).status, "provider_accepted");
  const ambiguous = validateIdentityDeliveryAcceptance(acceptance({
    status: "ambiguous",
    provider_acceptance_present: false,
    accepted_at: null,
    failure_code: "provider_result_ambiguous",
  }));
  assert.equal(ambiguous.provider_acceptance_present, false);
  assert.equal(ambiguous.accepted_at, null);

  assertProtocolError(
    () => validateIdentityDeliveryAcceptance(acceptance({
      status: "ambiguous",
      failure_code: "provider_result_ambiguous",
    })),
    "identity_delivery_status_conflict",
  );
});

test("redrive request and receipt require audit identity, fencing, and key rotation", () => {
  const request = validateIdentityDeliveryRedriveRequest(redriveRequest());
  const receipt = validateIdentityDeliveryRedriveReceipt(redriveReceipt());
  assert.equal(receipt.lease_generation, request.expected_lease_generation + 1);
  assert.notEqual(receipt.provider_idempotency_key, receipt.previous_provider_idempotency_key);

  assertProtocolError(
    () => validateIdentityDeliveryRedriveReceipt(redriveReceipt({ lease_generation: 6 })),
    "identity_delivery_status_conflict",
  );
  assertProtocolError(
    () => validateIdentityDeliveryRedriveReceipt(redriveReceipt({
      provider_idempotency_key: "identity-delivery:challenge_001:0",
    })),
    "identity_delivery_idempotency_conflict",
  );
});

test("canonical JSON parser rejects whitespace, duplicate-equivalent, and unknown fields", () => {
  const canonical = canonicalIdentityDeliveryJson("task", task());
  assert.deepEqual(parseIdentityDeliveryCanonicalJson("task", canonical), task());
  assertProtocolError(
    () => parseIdentityDeliveryCanonicalJson("task", `${canonical}\n`),
    "identity_delivery_invalid_request",
  );

  const duplicate = canonical.replace(
    '"accepted_at":null,',
    '"accepted_at":null,"accepted_at":null,',
  );
  assertProtocolError(
    () => parseIdentityDeliveryCanonicalJson("task", duplicate),
    "identity_delivery_invalid_request",
  );
  assertProtocolError(
    () => validateIdentityDeliveryTask({ ...task(), provider_name: "mail-relay" }),
    "identity_delivery_unknown_field",
  );
});

test("public guard recursively rejects destination, code, token, and private references", () => {
  const forbidden = [
    { destination: "masked" },
    { nested: { verification_code: "synthetic" } },
    { nested: [{ opaque_ref: "masked" }] },
    { metadata: `vault${":identity-delivery/example"}` },
    { metadata: `person${"@example.invalid"}` },
    { metadata: "+8613800000000" },
    { metadata: `Bearer ${"synthetic-token-value"}` },
  ];
  for (const payload of forbidden) {
    assertProtocolError(
      () => assertPublicIdentityDeliveryPayload(payload),
      "identity_delivery_secret_forbidden",
    );
  }
  assert.doesNotThrow(() => assertPublicIdentityDeliveryPayload({
    provider_acceptance_present: true,
    provider_idempotency_key: "identity-delivery:challenge_001:0",
    failure_code: "provider_timeout",
    audit_id: "audit_001",
  }));

  const error = new IdentityDeliveryProtocolError(
    `Bearer ${"synthetic-token-value"}`,
    "identity_delivery_secret_forbidden",
  );
  assert.equal(error.message, "identity delivery payload rejected");
});

test("Python and TypeScript canonical JSON are byte-identical in both directions", () => {
  const vectors = [
    ["task", task()],
    ["acceptance", acceptance()],
    ["redrive_request", redriveRequest()],
    ["redrive_receipt", redriveReceipt()],
  ];
  for (const [kind, payload] of vectors) {
    const pythonCanonical = runPython({ mode: "encode", kind, payload });
    const tsFromPython = canonicalIdentityDeliveryJson(
      kind,
      parseIdentityDeliveryCanonicalJson(kind, pythonCanonical),
    );
    assert.equal(tsFromPython, pythonCanonical, `${kind} Python -> TypeScript drift`);

    const typescriptCanonical = canonicalIdentityDeliveryJson(kind, payload);
    const pythonFromTs = runPython({ mode: "decode", kind, canonical: typescriptCanonical });
    assert.equal(pythonFromTs, typescriptCanonical, `${kind} TypeScript -> Python drift`);
  }
});

function runPython(request) {
  const pythonSdk = fileURLToPath(new URL("../../../../packages/sdk", import.meta.url));
  const script = String.raw`
import json
import sys
from releasefoundry.delivery_protocol import (
    canonical_identity_delivery_json,
    parse_identity_delivery_canonical_json,
)
request = json.load(sys.stdin)
if request["mode"] == "encode":
    result = canonical_identity_delivery_json(request["kind"], request["payload"])
else:
    dto = parse_identity_delivery_canonical_json(request["kind"], request["canonical"])
    result = canonical_identity_delivery_json(request["kind"], dto)
sys.stdout.write(result)
`;
  const candidates = [process.env.PYTHON, process.platform === "win32" ? "python" : "python3", "python"]
    .filter((value, index, values) => value && values.indexOf(value) === index);
  let lastResult;
  for (const executable of candidates) {
    const result = spawnSync(executable, ["-c", script], {
      encoding: "utf8",
      input: JSON.stringify(request),
      env: {
        ...process.env,
        PYTHONPATH: [pythonSdk, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
      },
    });
    lastResult = result;
    if (result.error?.code === "ENOENT") continue;
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    return result.stdout;
  }
  assert.fail(`Python interpreter unavailable: ${lastResult?.error?.message ?? "not found"}`);
}
