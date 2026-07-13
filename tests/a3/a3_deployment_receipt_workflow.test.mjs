import assert from "node:assert/strict";
import test from "node:test";

import {
  A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
  buildA3DeploymentAcceptanceProjection,
  buildA3DeploymentReceiptAuthoritativeReadback,
  buildA3DeploymentReceiptInbox,
  buildA3DeploymentReceiptSubmission,
  isTrustedA3DeploymentReceiptAuthoritativeReadback,
  reviewA3DeploymentReceipt,
  validateA3DeploymentReceiptAuthoritativeReadback,
  validateA3DeploymentReceiptSubmission
} from "../../services/report/a3_deployment_receipt_workflow.mjs";

const scope = {
  organization_id: "org-local",
  tenant_id: "tenant-local",
  workspace_id: "workspace-local",
  project_id: "project-local",
  environment_id: "staging"
};

const context = {
  source: "a3-golden-path-rc2",
  expected_candidate_id: "candidate-sha",
  expected_run_id: "run-002",
  tenant_scope: scope,
  actor_hash: "actor_submitter_hash",
  submitted_at: "2026-07-13T05:00:00.000Z"
};

const submission = {
  blocker_id: "deployment_health",
  candidate_id: "candidate-sha",
  run_id: "run-002",
  evidence_ref: "receipt:deployment-health:20260713-001",
  evidence_sha256: "a".repeat(64),
  evidence_kind: "deployment_health_receipt",
  verifier_class: "deployment_probe",
  captured_at: "2026-07-13T04:59:00.000Z",
  selectors: {
    deployment_id_alias: "deploy-staging-001",
    image_digest: `sha256:${"b".repeat(64)}`,
    health_status: "healthy"
  }
};

test("deployment receipt submission stores metadata but never promotes production acceptance", () => {
  const result = buildA3DeploymentReceiptSubmission(submission, context);

  assert.equal(result.valid, true);
  assert.equal(result.record.schema_version, "a3.deployment_receipt.v1");
  assert.equal(result.record.status, "submitted");
  assert.equal(result.record.version, 1);
  assert.equal(result.record.owner, "A1/A3");
  assert.equal(result.record.evidence_sha256, `sha256:${"a".repeat(64)}`);
  assert.deepEqual(result.record.tenant_scope, scope);
  assert.equal(result.record.authority_validation.status, "pending_external_verifier");
  assert.equal(result.record.authority_validation.production_verified, false);
  assert.equal(result.record.acceptance_effect.changes_deployment_acceptance, false);
  assert.equal(result.record.acceptance_effect.changes_release_ready, false);
  assert.equal(result.record.safety.raw_evidence_embedded, false);
});

test("deployment receipt submission rejects wrong candidates, signed URLs, and sensitive material", () => {
  const wrongCandidate = validateA3DeploymentReceiptSubmission({
    ...submission,
    candidate_id: "another-candidate"
  }, context);
  assert.equal(wrongCandidate.valid, false);
  assert.ok(wrongCandidate.errors.some((item) => item.issue === "candidate_mismatch"));

  const signedUrl = validateA3DeploymentReceiptSubmission({
    ...submission,
    evidence_ref: "https://storage.example.test/object?X-Amz-Signature=secret"
  }, context);
  assert.equal(signedUrl.valid, false);
  assert.ok(signedUrl.errors.some((item) => item.field === "evidence_ref"));
  assert.ok(signedUrl.errors.some((item) => item.issue === "sensitive_material_forbidden"));

  const token = validateA3DeploymentReceiptSubmission({
    ...submission,
    selectors: { deployment_id_alias: `Bearer ${"x".repeat(32)}` }
  }, context);
  assert.equal(token.valid, false);
  assert.ok(token.errors.some((item) => item.issue === "unsafe_or_invalid_value"));
});

test("receipt review requires optimistic concurrency and remains non-authoritative", () => {
  const record = buildA3DeploymentReceiptSubmission(submission, context).record;
  const conflict = reviewA3DeploymentReceipt(record, {
    action: "acknowledge",
    expected_version: 2,
    reason_code: "metadata_complete"
  }, context);
  assert.equal(conflict.valid, false);
  assert.ok(conflict.errors.some((item) => item.issue === "version_conflict"));

  const reviewed = reviewA3DeploymentReceipt(record, {
    action: "acknowledge",
    expected_version: 1,
    reason_code: "metadata_complete"
  }, {
    actor_hash: "actor_reviewer_hash",
    reviewed_at: "2026-07-13T05:10:00.000Z"
  });
  assert.equal(reviewed.valid, true);
  assert.equal(reviewed.record.status, "acknowledged");
  assert.equal(reviewed.record.version, 2);
  assert.equal(reviewed.record.authority_validation.status, "awaiting_authoritative_readback");
  assert.equal(reviewed.record.authority_validation.production_verified, false);
  assert.equal(reviewed.record.acceptance_effect.changes_deployment_acceptance, false);
});

test("deployment receipt inbox joins receipts to blockers without changing blocker status", () => {
  const record = buildA3DeploymentReceiptSubmission(submission, context).record;
  const inbox = buildA3DeploymentReceiptInbox([record], {
    blocking_items: [
      { id: "deployment_health", label: "Deployment health", owner: "A1/A3", status: "not_proven", required_receipt: "health receipt" },
      { id: "required_check_enforcement", label: "Required Check", owner: "Repository maintainer", status: "not_proven", required_receipt: "policy receipt" }
    ]
  }, context);

  assert.equal(inbox.schema_version, "a3.deployment_receipt_inbox.v1");
  assert.equal(inbox.receipt_count, 1);
  assert.equal(inbox.blocker_slot_count, 2);
  assert.equal(inbox.missing_slot_count, 1);
  assert.equal(inbox.submitted_or_acknowledged_count, 1);
  assert.equal(inbox.production_verified_count, 0);
  assert.equal(inbox.slots[0].intake_status, "submitted");
  assert.equal(inbox.slots[0].deployment_check_status, "not_proven");
  assert.equal(inbox.safety.deployment_acceptance_mutated, false);
});

test("trusted server readback verifies every deployment-health binding and required claim", () => {
  const acknowledged = acknowledgedReceipt();
  const result = buildA3DeploymentReceiptAuthoritativeReadback(
    acknowledged,
    authoritativeReadbackInput(acknowledged),
    authoritativeReadbackContext()
  );

  assert.equal(result.valid, true, JSON.stringify(result.errors));
  assert.equal(result.record.schema_version, A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION);
  assert.equal(result.record.verification_status, "verified");
  assert.equal(result.record.production_verified, true);
  assert.equal(result.record.binding_validation.all_passed, true);
  assert.equal(result.record.sequence, 1);
  assert.equal(result.record.previous_readback_hash, null);
  assert.match(result.record.readback_hash, /^sha256:[a-f0-9]{64}$/);
  assert.equal(isTrustedA3DeploymentReceiptAuthoritativeReadback(result.record), true);

  const tampered = structuredClone(result.record);
  tampered.claims.health_verified = false;
  assert.equal(isTrustedA3DeploymentReceiptAuthoritativeReadback(tampered), false);
});

test("authoritative readback rejects mismatched bindings, missing claims, and client promotion fields", () => {
  const acknowledged = acknowledgedReceipt();
  const wrongCandidate = validateA3DeploymentReceiptAuthoritativeReadback(acknowledged, {
    ...authoritativeReadbackInput(acknowledged),
    candidate_id: "wrong-candidate"
  }, authoritativeReadbackContext());
  assert.equal(wrongCandidate.valid, false);
  assert.ok(wrongCandidate.errors.some((item) => item.issue === "candidate_mismatch"));

  const missingClaimInput = authoritativeReadbackInput(acknowledged);
  delete missingClaimInput.claims.tenant_isolation_verified;
  const missingClaim = validateA3DeploymentReceiptAuthoritativeReadback(
    acknowledged,
    missingClaimInput,
    authoritativeReadbackContext()
  );
  assert.equal(missingClaim.valid, false);
  assert.ok(missingClaim.errors.some((item) => item.field === "claims.tenant_isolation_verified"));

  const failedVerifiedClaim = validateA3DeploymentReceiptAuthoritativeReadback(acknowledged, {
    ...authoritativeReadbackInput(acknowledged),
    claims: {
      ...authoritativeReadbackInput(acknowledged).claims,
      health_verified: false
    }
  }, authoritativeReadbackContext());
  assert.equal(failedVerifiedClaim.valid, false);
  assert.ok(failedVerifiedClaim.errors.some((item) => (
    item.field === "claims.health_verified" && item.issue === "verified_claim_must_pass"
  )));

  const clientPromotion = validateA3DeploymentReceiptAuthoritativeReadback(acknowledged, {
    ...authoritativeReadbackInput(acknowledged),
    production_verified: true
  }, authoritativeReadbackContext());
  assert.equal(clientPromotion.valid, false);
  assert.ok(clientPromotion.errors.some((item) => item.field === "production_verified"));
});

test("trusted rejection is chained but remains non-production", () => {
  const acknowledged = acknowledgedReceipt();
  const input = authoritativeReadbackInput(acknowledged, {
    verification_status: "rejected",
    reason_code: "policy_not_satisfied",
    claims: {
      image_config_migration_verified: true,
      health_verified: true,
      network_policy_verified: false,
      tenant_isolation_verified: false
    }
  });
  const first = buildA3DeploymentReceiptAuthoritativeReadback(
    acknowledged,
    input,
    authoritativeReadbackContext()
  );
  assert.equal(first.valid, true, JSON.stringify(first.errors));
  assert.equal(first.record.production_verified, false);
  assert.equal(isTrustedA3DeploymentReceiptAuthoritativeReadback(first.record), true);

  const second = buildA3DeploymentReceiptAuthoritativeReadback(
    acknowledged,
    authoritativeReadbackInput(acknowledged, { verified_at: "2026-07-13T05:20:00.000Z" }),
    { ...authoritativeReadbackContext(), previous_readback: first.record }
  );
  assert.equal(second.valid, true, JSON.stringify(second.errors));
  assert.equal(second.record.sequence, 2);
  assert.equal(second.record.previous_readback_hash, first.record.readback_hash);
  assert.equal(second.record.production_verified, true);
});

test("inbox and acceptance projection consume only hash-valid authoritative readbacks", () => {
  const acknowledged = acknowledgedReceipt();
  const verified = buildA3DeploymentReceiptAuthoritativeReadback(
    acknowledged,
    authoritativeReadbackInput(acknowledged),
    authoritativeReadbackContext()
  ).record;
  const handoff = {
    blocking_items: [
      { id: "deployment_health", label: "Deployment health", owner: "A1/A3", status: "not_proven", required_receipt: "health receipt" }
    ]
  };
  const inbox = buildA3DeploymentReceiptInbox([acknowledged], handoff, context, [verified]);
  assert.equal(inbox.production_verified_count, 1);
  assert.equal(inbox.authoritative_readback_count, 1);
  assert.equal(inbox.slots[0].production_verified, true);
  assert.equal(inbox.slots[0].deployment_check_status, "production_verified");
  assert.equal(inbox.receipts[0].authority_validation.authoritative_readback_id, verified.readback_id);

  const acceptance = {
    acceptance_id: "dpa_source",
    status: "blocked",
    summary: { total_checks: 2, passed: 1 },
    checks: [
      { id: "a1_run_evidence", required: true, status: "passed", production_proof: false },
      { id: "deployment_health", required: true, status: "not_proven", production_proof: false }
    ]
  };
  const projection = buildA3DeploymentAcceptanceProjection(acceptance, inbox);
  assert.equal(projection.schema_version, "a3.deployment_acceptance_projection.v1");
  assert.equal(projection.status, "ready_for_rebuild");
  assert.equal(projection.projected_production_accepted, true);
  assert.equal(projection.production_accepted, false);
  assert.equal(projection.requires_acceptance_rebuild, true);
  assert.deepEqual(projection.changed_check_ids, ["deployment_health"]);
  assert.equal(projection.safety.source_acceptance_mutated, false);
});

function acknowledgedReceipt() {
  const record = buildA3DeploymentReceiptSubmission(submission, context).record;
  return reviewA3DeploymentReceipt(record, {
    action: "acknowledge",
    expected_version: 1,
    reason_code: "metadata_complete"
  }, {
    actor_hash: "actor_reviewer_hash",
    reviewed_at: "2026-07-13T05:10:00.000Z"
  }).record;
}

function authoritativeReadbackContext(overrides = {}) {
  return {
    trusted_resolver: true,
    principal_kind: "service_account",
    resolver_id_alias: "svc-deployment-verifier-01",
    expected_version: 2,
    ...overrides
  };
}

function authoritativeReadbackInput(receipt, overrides = {}) {
  return {
    schema_version: A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
    external_readback_id_alias: "deploy-readback-20260713-001",
    receipt_id: receipt.receipt_id,
    blocker_id: receipt.blocker_id,
    candidate_id: receipt.candidate_id,
    run_id: receipt.run_id,
    tenant_scope: receipt.tenant_scope,
    evidence_sha256: receipt.evidence_sha256,
    verifier_class: receipt.verifier_class,
    verifier_authority: "a1_a3_deployment_verifier",
    verification_status: "verified",
    reason_code: "all_bindings_verified",
    verified_at: "2026-07-13T05:15:00.000Z",
    attestation_sha256: `sha256:${"c".repeat(64)}`,
    claims: {
      image_config_migration_verified: true,
      health_verified: true,
      network_policy_verified: true,
      tenant_isolation_verified: true
    },
    ...overrides
  };
}
