import { createHash } from "node:crypto";

export const A3_RELEASE_EVIDENCE_HEALTH_SCHEMA_VERSION = "a3.release_evidence_health.v1";
export const A3_RELEASE_EVIDENCE_DIFF_SCHEMA_VERSION = "a3.release_evidence_diff.v1";

export function buildReleaseEvidenceHealth(summary = {}, context = {}) {
  const safeSummary = sanitizeSummary(summary);
  const summaryHash = sha256(stableJson(safeSummary));
  const nextAction = computeReleaseEvidenceNextAction(safeSummary, context);
  return {
    schema_version: A3_RELEASE_EVIDENCE_HEALTH_SCHEMA_VERSION,
    release_id: context.releaseId || safeSummary.release_id || "current",
    source: context.source || "unknown",
    tenant_scope: {
      organization_id: context.organizationId || context.organization_id || "org-local",
      project_id: context.projectId || context.project_id || "project-local"
    },
    summary_id: context.summaryId || `res_${summaryHash.slice(0, 16)}`,
    summary_hash: summaryHash,
    summary_schema_version: safeSummary.schema_version || "unknown",
    overall_status: safeSummary.overall_status || "missing",
    next_action: nextAction,
    publish_readiness: {
      github_check_ready: publishReady(safeSummary.github_check_publish),
      pr_comment_ready: publishReady(safeSummary.github_pr_comment_publish),
      required_check_ready: Boolean(safeSummary.github_required_check_plan?.check_name),
      dry_run_only: safeSummary.safety?.dry_run_only !== false
    },
    verifier_readiness: {
      audit_bundle_passed: safeSummary.audit_bundle_verification?.status === "passed"
        && safeSummary.audit_bundle_verification?.root_hash_passed === true,
      audit_archive_passed: safeSummary.audit_archive_verification?.status === "passed"
        && safeSummary.audit_archive_verification?.root_hash_passed === true
        && safeSummary.audit_archive_verification?.signature_passed === true
    },
    hosted_report_readiness: {
      snapshot_id: context.hostedReportSnapshotId || context.summarySnapshotId || null,
      immutable_snapshot_present: Boolean(context.hostedReportSnapshotId || context.summarySnapshotId),
      shareable_report_count: Number.isFinite(context.shareableReportCount) ? context.shareableReportCount : 0
    },
    safety: {
      raw_secret_values_allowed: false,
      raw_fixture_exposed: false,
      raw_request_body_exposed: false,
      token_included: safeSummary.safety?.token_included === true,
      contains_secret_values: safeSummary.safety?.contains_secret_values === true,
      raw_private_key_stored: safeSummary.safety?.raw_private_key_stored === true
    },
    commercial_flags: {
      pr_gate_reference_ready: Boolean(context.prGateReferenceReady || safeSummary.github_check_publish?.available),
      audit_packet_ready: safeSummary.audit_bundle_verification?.status === "passed"
        && safeSummary.audit_archive_verification?.status === "passed",
      external_share_ready: Boolean(context.hostedReportSnapshotId || context.summarySnapshotId)
        && safeSummary.safety?.contains_secret_values !== true,
      enterprise_readiness_gap: nextAction.action === "ready_for_release_review" ? "identity_and_live_readback" : nextAction.reason
    }
  };
}

export function computeReleaseEvidenceNextAction(summary = {}, context = {}) {
  const safeSummary = sanitizeSummary(summary);
  if (!publishReady(safeSummary.github_check_publish)) {
    return action("publish_github_check", "github_check_missing_or_not_posted", "Publish or read back the Ashr++ GitHub Check before claiming PR gate evidence.");
  }
  if (!publishReady(safeSummary.github_pr_comment_publish)) {
    return action("publish_pr_comment", "pr_comment_missing_or_not_posted", "Publish or read back the PR comment evidence for reviewer handoff.");
  }
  if (!safeSummary.github_required_check_plan?.check_name) {
    return action("plan_required_check", "required_check_missing", "Attach a required-check plan or readback receipt.");
  }
  if (safeSummary.audit_bundle_verification?.status !== "passed" || safeSummary.audit_bundle_verification?.root_hash_passed !== true) {
    return action("verify_bundle", "audit_bundle_not_verified", "Run the audit bundle verifier and attach a passing receipt.");
  }
  if (
    safeSummary.audit_archive_verification?.status !== "passed"
    || safeSummary.audit_archive_verification?.root_hash_passed !== true
    || safeSummary.audit_archive_verification?.signature_passed !== true
  ) {
    return action("verify_archive", "audit_archive_not_verified", "Verify the signed archive root hash and signature.");
  }
  if (safeSummary.safety?.contains_secret_values || safeSummary.safety?.token_included || safeSummary.safety?.raw_private_key_stored) {
    return action("block_external_share", "redaction_or_secret_risk", "Block external sharing until release evidence has no secret-bearing fields.");
  }
  if (!context.hostedReportSnapshotId && !context.summarySnapshotId) {
    return action("share_hosted_report", "hosted_snapshot_missing", "Create an immutable hosted report snapshot for reviewer evidence.");
  }
  if (context.reviewerApprovalRequired === true && context.reviewerApproved !== true) {
    return action("request_reviewer_approval", "reviewer_approval_missing", "Request reviewer approval before release sign-off.");
  }
  return action("ready_for_release_review", "release_evidence_ready", "Release evidence is ready for human release review.");
}

export function diffReleaseEvidenceSummaries(before = {}, after = {}) {
  const safeBefore = sanitizeSummary(before);
  const safeAfter = sanitizeSummary(after);
  const fields = [
    ["overall_status", safeBefore.overall_status, safeAfter.overall_status],
    ["github_check_publish.status", safeBefore.github_check_publish?.status, safeAfter.github_check_publish?.status],
    ["github_pr_comment_publish.status", safeBefore.github_pr_comment_publish?.status, safeAfter.github_pr_comment_publish?.status],
    ["audit_bundle_verification.status", safeBefore.audit_bundle_verification?.status, safeAfter.audit_bundle_verification?.status],
    ["audit_archive_verification.status", safeBefore.audit_archive_verification?.status, safeAfter.audit_archive_verification?.status],
    ["audit_archive_verification.signature_passed", safeBefore.audit_archive_verification?.signature_passed, safeAfter.audit_archive_verification?.signature_passed]
  ];
  const changedFields = fields
    .filter(([, oldValue, newValue]) => oldValue !== newValue)
    .map(([field, oldValue, newValue]) => ({ field, before: oldValue ?? null, after: newValue ?? null }));
  const beforeRank = statusRank(safeBefore.overall_status);
  const afterRank = statusRank(safeAfter.overall_status);
  return {
    schema_version: A3_RELEASE_EVIDENCE_DIFF_SCHEMA_VERSION,
    before_summary_id: `res_${sha256(stableJson(safeBefore)).slice(0, 16)}`,
    after_summary_id: `res_${sha256(stableJson(safeAfter)).slice(0, 16)}`,
    status_changed: safeBefore.overall_status !== safeAfter.overall_status,
    changed_fields: changedFields,
    improvement_count: afterRank > beforeRank ? 1 : 0,
    regression_count: afterRank < beforeRank ? 1 : 0,
    safe_summary: {
      before_status: safeBefore.overall_status || "missing",
      after_status: safeAfter.overall_status || "missing",
      changed_field_count: changedFields.length,
      raw_details_exposed: false,
      secret_values_exposed: false
    }
  };
}

function publishReady(item = {}) {
  return item?.posted === true || item?.status === "posted" || item?.status === "readback_confirmed";
}

function action(actionName, reason, label) {
  return {
    action: actionName,
    reason,
    label
  };
}

function statusRank(status) {
  return {
    missing: 0,
    partial: 1,
    planned: 2,
    verified: 3,
    readback_confirmed: 4
  }[status] ?? 0;
}

function sanitizeSummary(value = {}) {
  return JSON.parse(JSON.stringify(value || {}, (key, item) => (
    /raw_details|authorization|cookie|token_value|private_key|secret_value|signed_url/i.test(key)
      && typeof item !== "boolean"
      && typeof item !== "number"
      ? "[REDACTED]"
      : item
  )));
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortForStableJson(value));
}

function sortForStableJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortForStableJson);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, sortForStableJson(item)])
    );
  }
  return value;
}
