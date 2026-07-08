import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildReleaseEvidenceHealth,
  computeReleaseEvidenceNextAction,
  diffReleaseEvidenceSummaries
} from "../../services/report/a3_release_evidence.mjs";

const verifiedSummary = {
  schema_version: "a3.release_evidence_summary.v1",
  available: true,
  overall_status: "verified",
  github_check_publish: { available: true, status: "posted", posted: true, dry_run: false },
  github_pr_comment_publish: { available: true, status: "posted", posted: true, dry_run: false },
  github_required_check_plan: { available: true, check_name: "Ashr++ Release Gate" },
  audit_bundle_verification: { available: true, status: "passed", root_hash_passed: true },
  audit_archive_verification: { available: true, status: "passed", root_hash_passed: true, signature_passed: true },
  safety: {
    token_included: false,
    contains_secret_values: false,
    raw_private_key_stored: false,
    dry_run_only: false
  }
};

test("A3 release evidence health marks verified evidence ready for review", () => {
  const health = buildReleaseEvidenceHealth(verifiedSummary, {
    releaseId: "run-health",
    source: "mock",
    organizationId: "org-unit",
    projectId: "project-unit",
    hostedReportSnapshotId: "resnap_unit",
    shareableReportCount: 1
  });

  assert.equal(health.schema_version, "a3.release_evidence_health.v1");
  assert.equal(health.release_id, "run-health");
  assert.equal(health.tenant_scope.organization_id, "org-unit");
  assert.equal(health.next_action.action, "ready_for_release_review");
  assert.equal(health.verifier_readiness.audit_bundle_passed, true);
  assert.equal(health.verifier_readiness.audit_archive_passed, true);
  assert.equal(health.hosted_report_readiness.immutable_snapshot_present, true);
  assert.equal(health.safety.raw_secret_values_allowed, false);
});

test("A3 release evidence next action drives missing GitHub and archive work", () => {
  assert.equal(computeReleaseEvidenceNextAction({
    ...verifiedSummary,
    github_check_publish: { available: true, status: "planned", posted: false, dry_run: true }
  }).action, "publish_github_check");

  assert.equal(computeReleaseEvidenceNextAction({
    ...verifiedSummary,
    audit_archive_verification: { available: true, status: "failed", root_hash_passed: false, signature_passed: false }
  }, {
    hostedReportSnapshotId: "resnap_unit"
  }).action, "verify_archive");
});

test("A3 release evidence diff reports status movement without raw details", () => {
  const diff = diffReleaseEvidenceSummaries({
    ...verifiedSummary,
    overall_status: "planned",
    raw_details: "Authorization: Bearer should-not-leak"
  }, {
    ...verifiedSummary,
    overall_status: "verified",
    audit_archive_verification: {
      ...verifiedSummary.audit_archive_verification,
      signature_passed: true
    }
  });

  assert.equal(diff.schema_version, "a3.release_evidence_diff.v1");
  assert.equal(diff.status_changed, true);
  assert.equal(diff.improvement_count, 1);
  assert.equal(diff.regression_count, 0);
  assert.ok(diff.changed_fields.some((item) => item.field === "overall_status"));
  assert.equal(diff.safe_summary.raw_details_exposed, false);
  assert.doesNotMatch(JSON.stringify(diff), /should-not-leak|Bearer/);
});
