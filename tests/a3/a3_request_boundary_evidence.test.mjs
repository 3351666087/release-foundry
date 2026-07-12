import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const EVIDENCE_PATH = new URL(
  "../../fixtures/a3/p3/a3_request_boundary_audit_evidence.redacted.json",
  import.meta.url
);

test("request-boundary evidence covers sanitized status precedence and protected OPTIONS", async () => {
  const text = await readFile(EVIDENCE_PATH, "utf8");
  const evidence = JSON.parse(text);

  assert.equal(evidence.schema_version, "a3.request_boundary_audit_evidence.v1");
  assert.equal(evidence.proof_level, "implemented_local");
  assert.equal(evidence.production_validated, false);
  assert.equal(evidence.authority.identity_and_session, "A1");
  assert.equal(evidence.authority.release_decision, "A2");

  const cases = new Map(evidence.cases.map((item) => [item.case_id, item]));
  assert.equal(cases.get("malformed_json_authorized").expected_status, 400);
  assert.equal(cases.get("malformed_json_unauthenticated").expected_status, 401);
  assert.equal(cases.get("malformed_json_unauthenticated").body_read, false);
  assert.equal(cases.get("malformed_json_forbidden").expected_status, 403);
  assert.equal(cases.get("malformed_json_forbidden").body_read, false);
  assert.equal(cases.get("body_read_timeout_authorized").expected_status, 408);
  assert.equal(cases.get("payload_too_large_authorized").expected_status, 413);
  assert.equal(cases.get("unsupported_media_type_authorized").expected_status, 415);
  assert.equal(cases.get("invalid_json_shape_authorized").expected_status, 422);
  assert.equal(cases.get("protected_options_authorized").expected_status, 204);
  assert.equal(cases.get("protected_options_authorized").access_audit, "route_access.allowed");
  assert.equal(cases.get("protected_options_unregistered").expected_status, 403);
  assert.equal(cases.get("protected_options_unsupported_method").expected_status, 403);
  assert.equal(cases.get("public_health_options").expected_status, 204);

  assert.equal(evidence.audit_policy.payload_inline, false);
  assert.equal(evidence.audit_policy.redaction_status, "metadata_only");
  assert.equal(evidence.audit_policy.raw_request_body_stored, false);
  assert.equal(evidence.audit_policy.raw_identity_stored, false);
  assert.equal(evidence.audit_policy.raw_token_stored, false);
  assert.equal(evidence.audit_policy.raw_cookie_stored, false);
  assert.equal(evidence.audit_policy.raw_origin_stored, false);
  assert.equal(evidence.audit_policy.default_maximum_body_bytes, 1048576);
  assert.equal(evidence.audit_policy.default_body_read_timeout_ms, 10000);
  assert.equal(evidence.audit_policy.required_media_type, "application/json");
  assert.equal(evidence.audit_policy.required_top_level_shape, "object");

  for (const forbidden of [
    /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
    /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
    /Cookie:\s*(?!\[REDACTED\])/i,
    /@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i,
    /X-Amz-Signature=/i
  ]) {
    assert.equal(forbidden.test(text), false, `redacted evidence leaked: ${forbidden.source}`);
  }
});
