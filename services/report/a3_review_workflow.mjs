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
  if (!["waiver", "approval"].includes(type)) {
    throw new Error("Review workflow record type must be waiver or approval.");
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
  const review = type === "waiver"
    ? validateWaiverRequest(payload, gate, workflow, summary, {
      releaseVersion: workflow.release_version,
      environment: workflow.environment,
      headSha: workflow.head_sha,
      generatedAt: options.generatedAt || options.requestedAt
    })
    : validateApprovalRecord(payload, gate, workflow, summary, {
      waiver: options.waiver || {},
      releaseVersion: workflow.release_version,
      environment: workflow.environment,
      headSha: workflow.head_sha,
      generatedAt: options.generatedAt || options.requestedAt
    });
  const payloadHash = sha256(stableJson(payload || {}));
  const reviewHash = sha256(stableJson(review || {}));
  const createdAt = options.requestedAt || options.createdAt || new Date().toISOString();
  const recordId = options.recordId || `rwr_${sha256(`${type}:${payloadHash}:${reviewHash}:${createdAt}`).slice(0, 12)}`;
  const subject = type === "waiver" ? review.waiver || {} : review.approval || {};

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
  const accepted = items.filter((item) => item.accepted === true);
  return {
    schema_version: A3_REVIEW_WORKFLOW_INDEX_SCHEMA_VERSION,
    source: options.source || items[0]?.source || "mock",
    organization_id: options.organizationId || items[0]?.organization_id || "org-local",
    project_id: options.projectId || items[0]?.project_id || "project-local",
    record_count: items.length,
    waiver_count: waiverRecords.length,
    approval_count: approvalRecords.length,
    accepted_count: accepted.length,
    latest_record_id: items[items.length - 1]?.record_id || null,
    durable_storage_ready: options.durableStorageReady !== false,
    real_cloud_mutations_performed: false,
    records: items.slice(-10)
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
