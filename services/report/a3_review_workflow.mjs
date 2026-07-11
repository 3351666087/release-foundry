import { createHash } from "node:crypto";

import {
  buildDashboardSummary,
  summarizeReleaseGate,
  summarizeReleaseWorkflow
} from "./report_builder.mjs";
import {
  validateApprovalRecord,
  validateWaiverRequest
} from "./a3_gate_cli.mjs";

export const A3_REVIEW_WORKFLOW_RECORD_SCHEMA_VERSION = "a3.review_workflow_record.v1";
export const A3_REVIEW_WORKFLOW_INDEX_SCHEMA_VERSION = "a3.review_workflow_index.v1";

export function buildReviewWorkflowRecord(type, payload = {}, snapshot = {}, options = {}) {
  if (!["waiver", "approval", "denial"].includes(type)) {
    throw new Error("Review workflow record type must be waiver, approval, or denial.");
  }
  const runFixture = snapshot.runFixture || snapshot.runs || {};
  const gradeFixture = snapshot.gradeFixture || snapshot.grades || {};
  const coverage = snapshot.coverage || {};
  const mediaSignedUrlCoverage = snapshot.mediaSignedUrlCoverage || {};
  const summary = buildDashboardSummary(runFixture, gradeFixture);
  const gate = summarizeReleaseGate(runFixture, gradeFixture, coverage, mediaSignedUrlCoverage);
  const workflow = summarizeReleaseWorkflow(runFixture, gradeFixture, coverage, mediaSignedUrlCoverage, {
    release_version: options.releaseVersion || payload.release_version,
    environment: options.environment || payload.environment,
    headSha: options.headSha || payload.head_sha,
    generatedAt: options.generatedAt || options.requestedAt
  });
  const review = buildReview(type, payload, gate, workflow, summary, options);
  const payloadHash = sha256(stableJson(payload || {}));
  const reviewHash = sha256(stableJson(review || {}));
  const createdAt = options.requestedAt || options.createdAt || new Date().toISOString();
  const recordId = options.recordId || `rwr_${sha256(`${type}:${payloadHash}:${reviewHash}:${createdAt}`).slice(0, 12)}`;
  const subject = type === "waiver"
    ? review.waiver || {}
    : type === "approval"
      ? review.approval || {}
      : review.denial || {};

  return {
    schema_version: A3_REVIEW_WORKFLOW_RECORD_SCHEMA_VERSION,
    record_id: recordId,
    record_type: type,
    source: snapshot.source || options.source || "mock",
    organization_id: options.organizationId || snapshot.organizationId || "org-local",
    project_id: options.projectId || snapshot.projectId || "project-local",
    run_id: subject.run_id || payload.run_id || summary.lastRunId || null,
    release_version: subject.release_version || payload.release_version || workflow.release_version || null,
    environment: subject.environment || payload.environment || workflow.environment || null,
    status: review.status || "unknown",
    accepted: review.accepted === true,
    automatic_unblock: review.automatic_unblock === true,
    payload_hash: payloadHash,
    review_hash: reviewHash,
    signature: {
      status: payload.signature || payload.signer ? "hash_sealed_signer_record" : "hash_sealed_unsigned_record",
      algorithm: "sha256",
      payload_hash: payloadHash,
      review_hash: reviewHash,
      signer_role: payload.signer?.role || firstRole(payload.approved_by) || null,
      raw_signature_stored: false
    },
    subject: summarizeSubject(type, payload, review),
    review,
    created_at: createdAt,
    safety: {
      secret_values_included: false,
      raw_signature_stored: false,
      raw_identity_values_redacted: true,
      real_cloud_mutation_performed: false
    }
  };
}

export function buildReviewWorkflowIndex(records = [], options = {}) {
  const items = Array.isArray(records) ? records : [];
  const waiverRecords = items.filter((item) => item.record_type === "waiver");
  const approvalRecords = items.filter((item) => item.record_type === "approval");
  const denialRecords = items.filter((item) => item.record_type === "denial");
  const accepted = items.filter((item) => item.accepted === true);
  return {
    schema_version: A3_REVIEW_WORKFLOW_INDEX_SCHEMA_VERSION,
    source: options.source || items[0]?.source || "mock",
    organization_id: options.organizationId || items[0]?.organization_id || "org-local",
    project_id: options.projectId || items[0]?.project_id || "project-local",
    record_count: items.length,
    waiver_count: waiverRecords.length,
    approval_count: approvalRecords.length,
    denial_count: denialRecords.length,
    accepted_count: accepted.length,
    human_action_count: items.length,
    latest_human_action: items[items.length - 1]?.record_type || null,
    latest_record_id: items[items.length - 1]?.record_id || null,
    scope_summary: buildWorkflowScopeSummary(items),
    decision_trends: buildDecisionTrendSummary(items),
    filter_options: buildWorkflowFilterOptions(items),
    durable_storage_ready: options.durableStorageReady !== false,
    real_cloud_mutations_performed: false,
    records: items.slice(-10)
  };
}

function buildWorkflowFilterOptions(items = []) {
  const releases = [...new Set(items.map((item) => item.release_version).filter(Boolean))];
  const environments = [...new Set(items.map((item) => item.environment).filter(Boolean))];
  const actorHashes = [...new Set(items.map((item) => item.review?.approval?.payload_hash || item.payload_hash).filter(Boolean))].slice(0, 12);
  return {
    schema_version: "a3.review_workflow_filter_options.v1",
    release_versions: releases,
    environments,
    actor_hashes: actorHashes,
    default_scope: {
      release_version: releases[releases.length - 1] || null,
      environment: environments[0] || null,
      actor_hash: actorHashes[0] || null
    }
  };
}

function buildDecisionTrendSummary(items = []) {
  const ordered = [...items].slice(-12);
  const releaseCounts = new Map();
  const environmentCounts = new Map();
  const actorCounts = new Map();
  for (const item of ordered) {
    if (item.release_version) {
      releaseCounts.set(item.release_version, (releaseCounts.get(item.release_version) || 0) + 1);
    }
    if (item.environment) {
      environmentCounts.set(item.environment, (environmentCounts.get(item.environment) || 0) + 1);
    }
    const actor = item.review?.approval?.reviewer_role
      || item.review?.waiver?.latest_approver_role
      || item.review?.denial?.reviewer_role
      || "unknown";
    actorCounts.set(actor, (actorCounts.get(actor) || 0) + 1);
  }
  return {
    approvals: ordered.filter((item) => item.record_type === "approval").length,
    waivers: ordered.filter((item) => item.record_type === "waiver").length,
    denials: ordered.filter((item) => item.record_type === "denial").length,
    latest_release_version: ordered[ordered.length - 1]?.release_version || null,
    latest_environment: ordered[ordered.length - 1]?.environment || null,
    release_breakdown: [...releaseCounts.entries()].map(([label, count]) => ({ label, count })),
    environment_breakdown: [...environmentCounts.entries()].map(([label, count]) => ({ label, count })),
    actor_breakdown: [...actorCounts.entries()].map(([label, count]) => ({ label, count }))
  };
}

function buildWorkflowScopeSummary(items = []) {
  const releases = [...new Set(items.map((item) => item.release_version).filter(Boolean))];
  const environments = [...new Set(items.map((item) => item.environment).filter(Boolean))];
  const actorRoles = [...new Set(items.map((item) => item.signature?.signer_role).filter(Boolean))];
  const actorHashes = [...new Set(items.map((item) => item.subject?.approved_by_actor_hash).filter(Boolean))];
  return {
    release_count: releases.length,
    environment_count: environments.length,
    actor_role_count: actorRoles.length,
    actor_hash_count: actorHashes.length,
    latest_release_version: items[items.length - 1]?.release_version || null,
    latest_environment: items[items.length - 1]?.environment || null,
    actor_roles: actorRoles.slice(0, 6),
    releases: releases.slice(0, 6),
    environments: environments.slice(0, 6)
  };
}

function buildReview(type, payload = {}, gate = {}, workflow = {}, summary = {}, options = {}) {
  if (type === "waiver") {
    return validateWaiverRequest(payload, gate, workflow, summary, {
      releaseVersion: workflow.release_version,
      environment: workflow.environment,
      headSha: workflow.head_sha,
      generatedAt: options.generatedAt || options.requestedAt
    });
  }
  if (type === "approval") {
    return validateApprovalRecord(payload, gate, workflow, summary, {
      waiver: options.waiver || {},
      releaseVersion: workflow.release_version,
      environment: workflow.environment,
      headSha: workflow.head_sha,
      generatedAt: options.generatedAt || options.requestedAt
    });
  }
  return validateDenialRecord(payload, gate, workflow, summary, options);
}

export function validateDenialRecord(denial = {}, gate = {}, workflow = {}, summary = {}, options = {}) {
  const hasDenial = denial && typeof denial === "object" && Object.keys(denial).length > 0;
  if (!hasDenial) {
    return {
      schema_version: "a3.denial_review.v1",
      available: false,
      status: "missing_denial",
      accepted: false,
      automatic_unblock: false,
      reason: "No denial record was provided.",
      findings: [denialFinding("missing_denial", "blocking", "No denial record was provided.")]
    };
  }

  const findings = [];
  const decision = denial.decision || "deny_release";
  const allowedDecisions = new Set(["deny_release", "reject_release", "request_changes"]);
  if (!["a3.denial.v1", "a3.review_denial.v1"].includes(denial.schema_version)) {
    findings.push(denialFinding("schema_version", "blocking", "Denial schema_version must be a3.denial.v1 or a3.review_denial.v1."));
  }
  for (const field of ["denial_id", "reason", "run_id", "release_version", "environment"]) {
    if (isBlank(denial[field])) {
      findings.push(denialFinding(`missing_${field}`, "blocking", `Denial is missing required field ${field}.`));
    }
  }
  if (!allowedDecisions.has(decision)) {
    findings.push(denialFinding("decision_invalid", "blocking", "Denial decision must be deny_release, reject_release, or request_changes."));
  }

  const expectedRunId = summary.lastRunId || "";
  if (denial.run_id && expectedRunId && denial.run_id !== expectedRunId) {
    findings.push(denialFinding("run_id_mismatch", "blocking", `Denial run_id ${denial.run_id} does not match gate run ${expectedRunId}.`));
  }
  if (denial.release_version && options.releaseVersion && denial.release_version !== options.releaseVersion) {
    findings.push(denialFinding("release_version_mismatch", "blocking", "Denial release_version does not match the gate release version."));
  }
  if (denial.environment && options.environment && denial.environment !== options.environment) {
    findings.push(denialFinding("environment_mismatch", "blocking", "Denial environment does not match the gate environment."));
  }
  if (denial.head_sha && options.headSha && denial.head_sha !== options.headSha) {
    findings.push(denialFinding("head_sha_mismatch", "blocking", "Denial head_sha does not match the gate head SHA."));
  }

  const reviewer = denial.reviewer || {};
  if (isBlank(reviewer.role) || isBlank(reviewer.name) || !parseDateOrNull(reviewer.reviewed_at)) {
    findings.push(denialFinding("reviewer_invalid", "blocking", "Denial reviewer must include role, name, and valid reviewed_at."));
  }

  const reviewedArtifacts = Array.isArray(denial.reviewed_artifacts) ? denial.reviewed_artifacts : [];
  if (!reviewedArtifacts.length) {
    findings.push(denialFinding("missing_reviewed_artifacts", "blocking", "Denial must include reviewed_artifacts."));
  }
  for (const artifact of reviewedArtifacts) {
    if (isBlank(artifact.id) || !/^[a-f0-9]{64}$/.test(String(artifact.sha256 || ""))) {
      findings.push(denialFinding("reviewed_artifact_invalid", "blocking", "Reviewed artifacts must include id and SHA-256 hash."));
      break;
    }
  }

  const blockingFindings = findings.filter((finding) => finding.severity === "blocking");
  const accepted = blockingFindings.length === 0;
  return {
    schema_version: "a3.denial_review.v1",
    available: true,
    status: accepted ? "valid_denial" : "invalid_denial",
    accepted,
    automatic_unblock: false,
    automatic_unblock_reason: "A denial records human review and keeps the release blocked; it never changes A1/A2 evidence or automatically unblocks.",
    denial: {
      denial_id: denial.denial_id || "unknown-denial",
      decision,
      run_id: denial.run_id || "",
      release_version: denial.release_version || workflow.release_version || "",
      environment: denial.environment || workflow.environment || "",
      head_sha: denial.head_sha || workflow.head_sha || "",
      reviewer_role: reviewer.role || "",
      reviewer_identity_source: reviewer.identity_source || "dashboard",
      reviewed_artifact_count: reviewedArtifacts.length,
      gate_decision: gate.decision || "unknown",
      gate_blocks_release: gate.blocks_release === true || gate.pr_gate?.blocks_merge === true
    },
    policy: {
      allowed_decisions: [...allowedDecisions],
      separation_of_duties_required: true,
      denial_keeps_release_blocked: true
    },
    findings,
    reason: accepted
      ? "Denial evidence satisfies the local A3 review policy and keeps the release blocked."
      : "Denial evidence does not satisfy the local A3 review policy."
  };
}

function summarizeSubject(type, payload = {}, review = {}) {
  if (type === "waiver") {
    const waiver = review.waiver || {};
    return {
      waiver_id: waiver.waiver_id || payload.waiver_id || "unknown-waiver",
      blocked_check_count: Array.isArray(payload.blocked_checks) ? payload.blocked_checks.length : 0,
      approved_by_count: Array.isArray(payload.approved_by) ? payload.approved_by.length : 0,
      reviewed_artifact_count: waiver.reviewed_artifact_count || 0,
      follow_up_issue: waiver.follow_up_issue || payload.follow_up_issue || null
    };
  }
  if (type === "denial") {
    const denial = review.denial || {};
    return {
      denial_id: denial.denial_id || payload.denial_id || "unknown-denial",
      decision: denial.decision || payload.decision || "deny_release",
      reviewer_role: denial.reviewer_role || payload.reviewer?.role || null,
      reviewed_artifact_count: denial.reviewed_artifact_count || 0,
      gate_decision: denial.gate_decision || "unknown"
    };
  }
  const approval = review.approval || {};
  return {
    approval_id: approval.approval_id || payload.approval_id || "unknown-approval",
    decision: approval.decision || payload.decision || "unknown",
    waiver_id: approval.waiver_id || payload.waiver_id || null,
    signer_role: payload.signer?.role || null,
    co_signer_count: approval.co_signer_count || 0,
    reviewed_artifact_count: approval.reviewed_artifact_count || 0
  };
}

function denialFinding(id, severity, message) {
  return { id, severity, message };
}

function isBlank(value) {
  return value === undefined || value === null || String(value).trim() === "";
}

function parseDateOrNull(value) {
  if (isBlank(value)) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function firstRole(values) {
  return Array.isArray(values) ? values.find((item) => item?.role)?.role || null : null;
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


