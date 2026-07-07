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

export function renderShareableReportHtml(report = {}) {
  const payload = report.payload || {};
  const summary = report.summary || payload.summary || {};
  const releaseGate = report.release_gate || payload.release_gate || {};
  const cases = Array.isArray(payload.cases) ? payload.cases.slice(0, 12) : [];
  const status = report.status || "unknown";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(report.title || payload.title || "A3 Shareable Report")}</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fb; color: #172033; }
    main { max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; border-bottom: 1px solid #d9dee8; padding-bottom: 18px; }
    h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    .muted { color: #667085; font-size: 13px; }
    .pill { display: inline-flex; border: 1px solid #c9d3e5; border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; background: #fff; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }
    .card { background: #fff; border: 1px solid #d9dee8; border-radius: 8px; padding: 16px; }
    .metric strong { display: block; font-size: 24px; }
    table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9dee8; border-radius: 8px; overflow: hidden; }
    th, td { text-align: left; border-bottom: 1px solid #edf0f5; padding: 10px 12px; font-size: 13px; vertical-align: top; }
    th { background: #f1f4f9; color: #465367; }
    tr:last-child td { border-bottom: 0; }
    .blocked { color: #b42318; }
    .passed { color: #067647; }
    pre { white-space: pre-wrap; background: #101828; color: #f8fafc; border-radius: 8px; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>${escapeHtml(report.title || payload.title || "A3 Shareable Report")}</h1>
        <div class="muted">${escapeHtml(report.report_id || "local-report")} / ${escapeHtml(report.created_at || "")}</div>
      </div>
      <span class="pill">${escapeHtml(status)}</span>
    </header>

    <section class="grid" aria-label="Report metrics">
      ${metric("Runs", summary.totalRuns ?? summary.total_runs ?? 0)}
      ${metric("Cases", summary.totalCases ?? summary.total_cases ?? 0)}
      ${metric("Failed", summary.failed ?? summary.failed_cases ?? 0)}
      ${metric("Pass Rate", `${summary.passRate ?? summary.pass_rate ?? 0}%`)}
    </section>

    <section class="card">
      <h2>Release Gate</h2>
      <p class="${releaseGate.decision === "block_release" ? "blocked" : "passed"}">
        ${escapeHtml(releaseGate.decision_label || releaseGate.decision || "unknown")}
      </p>
      <p class="muted">${escapeHtml(releaseGate.summary || releaseGate.reason || "No release gate summary available.")}</p>
    </section>

    <section style="margin-top: 20px;">
      <h2>Case Evidence</h2>
      <table>
        <thead><tr><th>Case</th><th>Status</th><th>Score</th><th>Failure Class</th><th>Summary</th></tr></thead>
        <tbody>
          ${cases.map((item) => `<tr>
            <td>${escapeHtml(item.case_id || item.title || "case")}</td>
            <td>${escapeHtml(item.passed ? "passed" : "failed")}</td>
            <td>${escapeHtml(item.score ?? "")}</td>
            <td>${escapeHtml(item.primary_failure_class || "none")}</td>
            <td>${escapeHtml(item.failure_summary || "")}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </section>

    <section class="card" style="margin-top: 20px;">
      <h2>Sealed Evidence</h2>
      <pre>${escapeHtml(JSON.stringify(report.sealed_evidence || {}, null, 2))}</pre>
    </section>
  </main>
</body>
</html>`;
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

function metric(label, value) {
  return `<div class="card metric"><strong>${escapeHtml(value)}</strong><span class="muted">${escapeHtml(label)}</span></div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
