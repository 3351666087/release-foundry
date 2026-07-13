import assert from "node:assert/strict";
import test from "node:test";

import {
  buildA3DeploymentReceiptInbox,
  buildA3DeploymentReceiptSubmission,
  reviewA3DeploymentReceipt,
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
