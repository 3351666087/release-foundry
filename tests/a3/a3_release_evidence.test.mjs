import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildReleaseEvidenceHealth,
  buildReleaseEvidenceSummaryV2,
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

test("A3 release evidence v2 authority summary is additive and tenant scoped", () => {
  const summary = buildReleaseEvidenceSummaryV2(verifiedSummary, {
    releaseId: "run-v2",
    source: "mock",
    organizationId: "org-unit",
    projectId: "project-unit",
    hostedReportSnapshotId: "resnap_unit",
    shareableReportCount: 2,
    runIds: ["run-v2"],
    caseCount: 4,
    a1: {
      runCount: 1,
      caseCount: 4,
      traceEventCount: 8,
      observationCount: 3,
      toolCallCaseCount: 2
    },
    a2: {
      gradeCount: 4,
      judgeResultCount: 6,
      failedCaseCount: 1,
      failureClassCount: 2
    },
    usageLedger: {
      schema_version: "a3.usage_ledger.v1",
      meters: [{ meter: "runs", quantity: 1 }],
      billable_unit_count: 10,
      billing_mutations_enabled: false
    }
  });

  assert.equal(summary.schema_version, "a3.release_evidence_summary.v2");
  assert.equal(summary.release_identity.release_id, "run-v2");
  assert.equal(summary.tenant_scope.organization_id, "org-unit");
  assert.equal(summary.tenant_scope.tenant_id, "tenant-local");
  assert.equal(summary.tenant_scope.workspace_id, "workspace-local");
  assert.equal(summary.a1_evidence.contracts.includes("RunResult"), true);
  assert.equal(summary.a1_evidence.trace_event_count, 8);
  assert.equal(summary.a2_evidence.contracts.includes("GradeResult"), true);
  assert.equal(summary.a2_evidence.failed_case_count, 1);
  assert.equal(summary.source_artifacts.schema_version, "a3.source_artifacts.v1");
  assert.equal(summary.source_artifacts.source_artifact_count, 0);
  assert.equal(summary.github_check_readback.readback_status, "missing");
  assert.equal(summary.required_check_proof.plan_only_must_not_claim_enforcement, true);
  assert.equal(summary.hosted_report.immutable_snapshot_present, true);
  assert.equal(summary.usage_ledger.linked_summary_id, summary.summary_id);
  assert.equal(summary.redaction.raw_secret_values_allowed, false);
  assert.doesNotMatch(JSON.stringify(summary), /Bearer should-not-leak|secret_live_value/);
});

test("A3 release evidence v2 carries GitHub readback and required-check proof without overstating enforcement", () => {
  const summary = buildReleaseEvidenceSummaryV2(verifiedSummary, {
    releaseId: "run-readback",
    source: "mock",
    githubCheckReadback: {
      schema_version: "a3.github_check_readback_receipt.v1",
      readback_id: "ghcrb_unit",
      readback_status: "readback_confirmed",
      readback_confirmed: true,
      posted: true,
      payload_hash: "hash_check",
      matches: { head_sha: true, output_hash: true },
      expected: { check_run_id_alias: 9001 }
    },
    prCommentReadback: {
      schema_version: "a3.github_pr_comment_readback_receipt.v1",
      readback_id: "ghprb_unit",
      readback_status: "stale",
      stale: true,
      payload_hash: "hash_comment",
      matches: { marker: true, body_hash: false },
      expected: { comment_id_alias: 2001 }
    },
    requiredCheckProof: {
      schema_version: "a3.github_required_check_proof.v1",
      proof_id: "ghrcp_unit",
      check_name: "Ashr++ Release Gate",
      enforcement_readback_status: "plan_only",
      readback_status: "plan_only",
      enforced: false,
      payload_hash: "hash_required"
    }
  });

  assert.equal(summary.github_check_readback.readback_status, "readback_confirmed");
  assert.equal(summary.github_check_readback.readback_confirmed, true);
  assert.equal(summary.github_check_readback.head_sha_match, true);
  assert.equal(summary.pr_comment_readback.readback_status, "stale");
  assert.equal(summary.pr_comment_readback.body_hash_match, false);
  assert.equal(summary.required_check_proof.enforcement_readback_status, "plan_only");
  assert.equal(summary.required_check_proof.enforced, false);
  assert.equal(summary.required_check_proof.plan_only_must_not_claim_enforcement, true);
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
