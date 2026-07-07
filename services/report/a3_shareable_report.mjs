import { createHash, randomUUID } from "node:crypto";

import {
  buildJsonReport,
  buildMarkdownReport
} from "./report_builder.mjs";
import { redactExport } from "./export_redaction_firewall.mjs";

export const SHAREABLE_REPORT_SCHEMA_VERSION = "a3.shareable_report.v1";

export function buildShareableReportPayload(inputs = {}, options = {}) {
  const runFixture = inputs.runFixture || inputs.runs || {};
  const gradeFixture = inputs.gradeFixture || inputs.grades || {};
  const coverageFixture = inputs.coverage || {};
  const evidenceReadinessFixture = inputs.evidenceReadiness || {};
  const requestFixture = inputs.requestProvenance || {};
  const usageFixture = inputs.usageQuota || {};
  const usageApiProbe = inputs.usageQuotaApiProbe || {};
  const mediaSignedUrlFixture = inputs.mediaSignedUrlCoverage || {};
  const authFixture = inputs.authCheck || {};
  const frontendFixture = inputs.frontendSummary || {};
  const frontendMirrorFixture = inputs.frontendMirror || {};
  const frontendCodeCrawlFixture = inputs.frontendCodeCrawl || {};

  const jsonReport = buildJsonReport(
    runFixture,
    gradeFixture,
    coverageFixture,
    evidenceReadinessFixture,
    requestFixture,
    usageFixture,
    usageApiProbe,
    mediaSignedUrlFixture,
    authFixture,
    frontendFixture,
    frontendMirrorFixture,
    frontendCodeCrawlFixture
  );
  const markdownReport = buildMarkdownReport(
    runFixture,
    gradeFixture,
    coverageFixture,
    evidenceReadinessFixture,
    requestFixture,
    usageFixture,
    usageApiProbe,
    mediaSignedUrlFixture,
    authFixture,
    frontendFixture,
    frontendMirrorFixture,
    frontendCodeCrawlFixture
  );

  const safeEnvelope = redactExport({
    title: options.title || "A3 Release Intelligence Report",
    source: options.source || inputs.source || "unknown",
    visibility: normalizeVisibility(options.visibility),
    summary: jsonReport.summary,
    release_gate: jsonReport.release_gate,
    release_war_room: jsonReport.release_war_room,
    reviewer_workflow_board: jsonReport.reviewer_workflow_board,
    incident_replay_queue: jsonReport.incident_replay_queue,
    observability_replay_matrix: jsonReport.observability_replay_matrix,
    regression_factory: jsonReport.regression_factory,
    export_redaction_firewall: jsonReport.export_redaction_firewall,
    cases: jsonReport.cases,
    markdown_report: markdownReport
  }, { surface: "shareable_report" });

  const createdAt = options.createdAt || new Date().toISOString();
  const reportId = options.reportId || stableReportId(safeEnvelope.value, createdAt);
  const payloadHash = sha256(stableJson(safeEnvelope.value));
  const blocked = Boolean(safeEnvelope.blocked || jsonReport.export_redaction_firewall?.status === "blocked");

  return {
    schema_version: SHAREABLE_REPORT_SCHEMA_VERSION,
    report_id: reportId,
    title: safeEnvelope.value.title,
    source: safeEnvelope.value.source,
    visibility: safeEnvelope.value.visibility,
    share_url_path: `/reports/${reportId}`,
    status: blocked ? "blocked" : "shareable",
    created_at: createdAt,
    created_by: options.createdBy || "a3-system",
    tenant_scope: {
      organization_id: options.organizationId || inputs.organizationId || "org-local",
      project_id: options.projectId || inputs.projectId || "project-local"
    },
    summary: safeEnvelope.value.summary,
    release_gate: safeEnvelope.value.release_gate,
    report_center: {
      json_available: true,
      markdown_available: true,
      hosted_page_available: !blocked,
      pdf_export_ready: true,
      audit_bundle_ready: Boolean(jsonReport.release_workflow?.audit_bundle),
      pr_comment_ready: Boolean(jsonReport.release_workflow?.pr_comment_markdown)
    },
    artifacts: [
      artifactDescriptor("json_report", "application/json", jsonReport),
      artifactDescriptor("markdown_report", "text/markdown", markdownReport),
      artifactDescriptor("hosted_report", "text/html", safeEnvelope.value)
    ],
    sealed_evidence: {
      payload_hash: payloadHash,
      hash_algorithm: "sha256",
      redaction_policy_version: jsonReport.export_redaction_firewall?.policy?.policy_version || "unknown",
      secret_free: !blocked,
      residual_finding_count: safeEnvelope.residual_findings.length
    },
    redaction: {
      status: safeEnvelope.status,
      replacement_count: safeEnvelope.replacement_count,
      residual_finding_count: safeEnvelope.residual_findings.length,
      blocked
    },
    payload: safeEnvelope.value
  };
}

function artifactDescriptor(id, contentType, value) {
  return {
    id,
    content_type: contentType,
    hash_algorithm: "sha256",
    sha256: sha256(typeof value === "string" ? value : stableJson(value)),
    redacted: true
  };
}

function normalizeVisibility(value) {
  if (["private_link", "team", "public"].includes(value)) {
    return value;
  }
  return "private_link";
}

function stableReportId(value, createdAt) {
  const hash = sha256(`${createdAt}:${stableJson(value)}`).slice(0, 12);
  try {
    return `a3r_${hash}_${randomUUID().slice(0, 8)}`;
  } catch {
    return `a3r_${hash}`;
  }
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
