import { createHash } from "node:crypto";

export const A3_RELEASE_EVIDENCE_HEALTH_SCHEMA_VERSION = "a3.release_evidence_health.v1";
export const A3_RELEASE_EVIDENCE_DIFF_SCHEMA_VERSION = "a3.release_evidence_diff.v1";
export const A3_RELEASE_EVIDENCE_SUMMARY_V2_SCHEMA_VERSION = "a3.release_evidence_summary.v2";

export function buildReleaseEvidenceSummaryV2(summary = {}, context = {}) {
  const safeSummary = sanitizeSummary(summary);
  const summaryHash = sha256(stableJson(safeSummary));
  const summaryId = context.summaryId || `res_${summaryHash.slice(0, 16)}`;
  const health = context.health || buildReleaseEvidenceHealth(safeSummary, {
    ...context,
    summaryId
  });
  const usageLedger = context.usageLedger || {};
  return {
    schema_version: A3_RELEASE_EVIDENCE_SUMMARY_V2_SCHEMA_VERSION,
    summary_id: summaryId,
    summary_hash: summaryHash,
    source_summary_schema_version: safeSummary.schema_version || "unknown",
    source: context.source || "unknown",
    tenant_scope: {
      organization_id: context.organizationId || context.organization_id || "org-local",
      tenant_id: context.tenantId || context.tenant_id || "tenant-local",
      workspace_id: context.workspaceId || context.workspace_id || "workspace-local",
      project_id: context.projectId || context.project_id || "project-local"
    },
    release_identity: {
      release_id: context.releaseId || safeSummary.release_id || "current",
      environment: context.environment || "local",
      source_snapshot_id: context.sourceSnapshotId || null,
      head_sha_alias: context.headShaAlias || null,
      source_import_receipt_ids: arrayOrEmpty(context.sourceImportReceiptIds),
      run_ids: arrayOrEmpty(context.runIds),
      case_count: numberOrZero(context.caseCount)
    },
    health,
    a1_evidence: {
      contracts: ["RunResult", "Trace", "ToolCall", "Observation"],
      run_count: numberOrZero(context.a1?.runCount),
      case_count: numberOrZero(context.a1?.caseCount),
      trace_event_count: numberOrZero(context.a1?.traceEventCount),
      observation_count: numberOrZero(context.a1?.observationCount),
      tool_call_case_count: numberOrZero(context.a1?.toolCallCaseCount),
      missing_required_fields: arrayOrEmpty(context.a1?.missingRequiredFields)
    },
    a2_evidence: {
      contracts: ["Scenario", "Judge", "GradeResult", "FailureTaxonomy"],
      grade_count: numberOrZero(context.a2?.gradeCount),
      judge_result_count: numberOrZero(context.a2?.judgeResultCount),
      failed_case_count: numberOrZero(context.a2?.failedCaseCount),
      failure_class_count: numberOrZero(context.a2?.failureClassCount),
      missing_required_fields: arrayOrEmpty(context.a2?.missingRequiredFields)
    },
    source_artifacts: normalizeSourceArtifacts(context.sourceArtifacts),
    github_check_readback: readbackState(context.githubCheckReadback || safeSummary.github_check_readback || safeSummary.github_check_publish, {
      generated_status: safeSummary.github_check_publish?.status,
      readback_status: context.githubCheckReadback?.readback_status || safeSummary.github_check_readback?.readback_status || safeSummary.github_check_publish?.readback_status || "missing",
      required_before_enforced: true
    }),
    pr_comment_readback: readbackState(context.prCommentReadback || safeSummary.pr_comment_readback || safeSummary.github_pr_comment_publish, {
      generated_status: safeSummary.github_pr_comment_publish?.status,
      readback_status: context.prCommentReadback?.readback_status || safeSummary.pr_comment_readback?.readback_status || safeSummary.github_pr_comment_publish?.readback_status || "missing"
    }),
    required_check_proof: {
      plan_available: Boolean(safeSummary.github_required_check_plan?.check_name),
      check_name: context.requiredCheckProof?.check_name || safeSummary.required_check_proof?.check_name || safeSummary.github_required_check_plan?.check_name || null,
      proof_id: context.requiredCheckProof?.proof_id || safeSummary.required_check_proof?.proof_id || null,
      readback_status: context.requiredCheckProof?.readback_status || safeSummary.required_check_proof?.readback_status || safeSummary.github_required_check_plan?.enforcement_readback_status || "plan_only",
      enforcement_readback_status: context.requiredCheckProof?.enforcement_readback_status || safeSummary.required_check_proof?.enforcement_readback_status || safeSummary.github_required_check_plan?.enforcement_readback_status || "plan_only",
      enforced: context.requiredCheckProof?.enforced === true || safeSummary.required_check_proof?.enforced === true || safeSummary.github_required_check_plan?.enforced === true,
      payload_hash: context.requiredCheckProof?.payload_hash || safeSummary.required_check_proof?.payload_hash || null,
      plan_only_must_not_claim_enforcement: !(context.requiredCheckProof?.enforced === true || safeSummary.required_check_proof?.enforced === true || safeSummary.github_required_check_plan?.enforced === true)
    },
    hosted_report: {
      snapshot_id: context.hostedReportSnapshotId || context.summarySnapshotId || null,
      immutable_snapshot_present: Boolean(context.hostedReportSnapshotId || context.summarySnapshotId),
      shareable_report_count: numberOrZero(context.shareableReportCount),
      denied_body_leakage_allowed: false,
      external_share_ready: Boolean(context.hostedReportSnapshotId || context.summarySnapshotId)
        && safeSummary.safety?.contains_secret_values !== true
    },
    storage: {
      mode: context.storageMode || "memory",
      db_ready: context.dbReady === true,
      durable_summary_table: "release_evidence_summaries",
      postgres_contract_required: true,
      immutable_snapshot_table_required: true
    },
    usage_ledger: {
      schema_version: usageLedger.schema_version || "a3.usage_ledger.v1",
      linked_summary_id: summaryId,
      meter_count: Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0,
      billable_unit_count: numberOrZero(usageLedger.billable_unit_count),
      billing_mutations_enabled: usageLedger.billing_mutations_enabled === true
    },
    redaction: {
      external_publish_allowed: safeSummary.safety?.contains_secret_values !== true
        && safeSummary.safety?.token_included !== true
        && safeSummary.safety?.raw_private_key_stored !== true,
      fail_closed_surfaces: ["json", "markdown", "csv", "html", "hosted_report", "github_check", "pr_comment", "manifest", "bundle", "archive"],
      raw_secret_values_allowed: false
    },
    compliance: {
      retention_policy: context.retentionPolicy || "local_demo_retention",
      legal_hold_state: context.legalHoldState || "not_configured",
      audit_chain_required: true,
      self_host_offline_verifier_required: true
    },
    safety: {
      raw_fixture_exposed: false,
      raw_request_body_exposed: false,
      raw_share_token_exposed: false,
      raw_secret_values_allowed: false,
      live_credentials_included: false
    },
    next_actions: [
      "Persist v2 summaries and immutable snapshots with tenant/project/release keys.",
      "Attach live GitHub Check and PR comment readback before claiming external enforcement.",
      "Join usage, audit, manifest, bundle, and archive artifacts through this summary_id."
    ]
  };
}

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
      tenant_id: context.tenantId || context.tenant_id || "tenant-local",
      workspace_id: context.workspaceId || context.workspace_id || "workspace-local",
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
    ["schema_version", safeBefore.schema_version, safeAfter.schema_version],
    ["overall_status", summaryOverallStatus(safeBefore), summaryOverallStatus(safeAfter)],
    ["next_action.action", summaryNextAction(safeBefore), summaryNextAction(safeAfter)],
    ["github_check.status", summaryGithubCheckStatus(safeBefore), summaryGithubCheckStatus(safeAfter)],
    ["github_pr_comment.status", summaryPrCommentStatus(safeBefore), summaryPrCommentStatus(safeAfter)],
    ["required_check.proof", summaryRequiredCheckStatus(safeBefore), summaryRequiredCheckStatus(safeAfter)],
    ["audit_bundle_verification.status", safeBefore.audit_bundle_verification?.status, safeAfter.audit_bundle_verification?.status],
    ["audit_archive_verification.status", safeBefore.audit_archive_verification?.status, safeAfter.audit_archive_verification?.status],
    ["audit_archive_verification.signature_passed", safeBefore.audit_archive_verification?.signature_passed, safeAfter.audit_archive_verification?.signature_passed]
  ];
  const changedFields = fields
    .filter(([, oldValue, newValue]) => oldValue !== newValue)
    .map(([field, oldValue, newValue]) => ({ field, before: oldValue ?? null, after: newValue ?? null }));
  const beforeRank = statusRank(summaryOverallStatus(safeBefore));
  const afterRank = statusRank(summaryOverallStatus(safeAfter));
  return {
    schema_version: A3_RELEASE_EVIDENCE_DIFF_SCHEMA_VERSION,
    before_summary_id: `res_${sha256(stableJson(safeBefore)).slice(0, 16)}`,
    after_summary_id: `res_${sha256(stableJson(safeAfter)).slice(0, 16)}`,
    status_changed: safeBefore.overall_status !== safeAfter.overall_status,
    changed_fields: changedFields,
    improvement_count: afterRank > beforeRank ? 1 : 0,
    regression_count: afterRank < beforeRank ? 1 : 0,
    safe_summary: {
      before_status: summaryOverallStatus(safeBefore),
      after_status: summaryOverallStatus(safeAfter),
      changed_field_count: changedFields.length,
      raw_details_exposed: false,
      secret_values_exposed: false
    }
  };
}

function summaryOverallStatus(summary = {}) {
  return summary.health?.overall_status || summary.overall_status || "missing";
}

function summaryNextAction(summary = {}) {
  return summary.health?.next_action?.action || summary.next_action?.action || null;
}

function summaryGithubCheckStatus(summary = {}) {
  return summary.github_check_readback?.readback_status
    || summary.github_check_readback?.generated_status
    || summary.github_check_publish?.readback_status
    || summary.github_check_publish?.status
    || null;
}

function summaryPrCommentStatus(summary = {}) {
  return summary.pr_comment_readback?.readback_status
    || summary.pr_comment_readback?.generated_status
    || summary.github_pr_comment_publish?.readback_status
    || summary.github_pr_comment_publish?.status
    || null;
}

function summaryRequiredCheckStatus(summary = {}) {
  return summary.required_check_proof?.enforced === true
    ? "enforced"
    : summary.required_check_proof?.enforcement_readback_status
      || summary.github_required_check_plan?.enforcement_readback_status
      || (summary.github_required_check_plan?.check_name ? "plan_only" : null);
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

function readbackState(item = {}, defaults = {}) {
  const readbackStatus = defaults.readback_status || item?.readback_status || item?.status || "missing";
  return {
    schema_version: item?.schema_version || null,
    readback_id: item?.readback_id || null,
    generated_status: item?.generated_status || defaults.generated_status || item?.status || "missing",
    posted: item?.posted === true || item?.status === "posted" || readbackStatus === "posted" || readbackStatus === "readback_confirmed",
    readback_status: readbackStatus,
    readback_confirmed: item?.readback_confirmed === true || item?.status === "readback_confirmed" || readbackStatus === "confirmed" || readbackStatus === "readback_confirmed",
    stale: readbackStatus === "stale" || item?.stale === true,
    missing: readbackStatus === "missing" || item?.missing === true,
    deleted: readbackStatus === "deleted" || item?.deleted === true,
    permission_denied: readbackStatus === "permission_denied",
    sanitized_error_class: item?.sanitized_error_class || null,
    payload_hash: item?.payload_hash || null,
    external_id_alias: item?.expected?.check_run_id_alias
      || item?.expected?.comment_id_alias
      || item?.payload?.expected?.check_run_id_alias
      || item?.payload?.expected?.comment_id_alias
      || item?.check_name
      || null,
    head_sha_match: item?.matches?.head_sha ?? item?.payload?.matches?.head_sha ?? null,
    marker_match: item?.matches?.marker ?? item?.payload?.matches?.marker ?? item?.marker_match ?? null,
    body_hash_match: item?.matches?.body_hash ?? item?.payload?.matches?.body_hash ?? item?.body_hash_match ?? null,
    required_before_enforced: defaults.required_before_enforced === true
  };
}

function arrayOrEmpty(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeSourceArtifacts(value = {}) {
  const artifacts = Array.isArray(value.artifacts) ? value.artifacts : Array.isArray(value) ? value : [];
  return {
    schema_version: value.schema_version || "a3.source_artifacts.v1",
    source_artifact_count: artifacts.length,
    hash_algorithm: value.hash_algorithm || "sha256",
    artifacts: artifacts.map((artifact) => ({
      source_artifact_id: artifact.source_artifact_id,
      artifact_type: artifact.artifact_type,
      source_lane: artifact.source_lane,
      source_contracts: arrayOrEmpty(artifact.source_contracts),
      content_hash: artifact.content_hash,
      record_count: numberOrZero(artifact.record_count),
      redaction_status: artifact.redaction_status || "hash_only",
      raw_payload_embedded: false,
      required_by_a3_surfaces: arrayOrEmpty(artifact.required_by_a3_surfaces)
    })),
    raw_payload_embedded: false,
    raw_secret_values_allowed: false
  };
}

function numberOrZero(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
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
