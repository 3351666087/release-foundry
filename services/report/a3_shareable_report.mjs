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
  const productConsoleFixture = inputs.productConsole || inputs.product_console || {};
  const saasAdminFixture = inputs.saasAdmin || inputs.saas_admin_console || {};
  const a2ReadinessBundle = inputs.a2ReadinessBundle || inputs.a2_readiness_bundle || {};
  const artifactRegistryFixture = inputs.artifactRegistry || inputs.artifact_registry || {};
  const reviewWorkflowFixture = inputs.reviewWorkflow || inputs.review_workflow || {};
  const multimodalReviewQueueFixture = inputs.multimodalReviewQueue || inputs.multimodal_review_queue || {};
  const releaseEvidenceFixture = inputs.releaseEvidence
    || inputs.release_evidence
    || inputs.releaseEvidenceSummary
    || inputs.release_evidence_summary
    || {};

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
    frontendCodeCrawlFixture,
    productConsoleFixture,
    saasAdminFixture,
    a2ReadinessBundle,
    artifactRegistryFixture,
    reviewWorkflowFixture,
    releaseEvidenceFixture,
    {},
    {},
    {},
    {},
    multimodalReviewQueueFixture
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
    frontendCodeCrawlFixture,
    productConsoleFixture,
    saasAdminFixture,
    a2ReadinessBundle,
    artifactRegistryFixture,
    releaseEvidenceFixture,
    {},
    {},
    {},
    {},
    multimodalReviewQueueFixture
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
    release_evidence_summary: jsonReport.release_evidence_summary,
    multimodal_review_queue: jsonReport.multimodal_review_queue,
    multimodal_repeat_stability: jsonReport.multimodal_repeat_stability,
    cases: jsonReport.cases,
    markdown_report: markdownReport
  }, { surface: "shareable_report" });

  const createdAt = options.createdAt || new Date().toISOString();
  const expiresAt = options.expiresAt || defaultExpiry(createdAt);
  const reportId = options.reportId || stableReportId(safeEnvelope.value, createdAt);
  const shareToken = options.shareToken || stableShareToken(reportId, createdAt);
  const shareTokenHash = sha256(shareToken);
  const payloadHash = sha256(stableJson(safeEnvelope.value));
  const blocked = Boolean(safeEnvelope.blocked || jsonReport.export_redaction_firewall?.status === "blocked");
  const releaseEvidenceSummary = safeEnvelope.value.release_evidence_summary || jsonReport.release_evidence_summary || {};
  const releaseEvidenceSnapshot = buildReleaseEvidenceSnapshot(releaseEvidenceSummary, {
    reportId,
    source: options.source || inputs.source || "unknown",
    createdAt
  });

  return {
    schema_version: SHAREABLE_REPORT_SCHEMA_VERSION,
    report_id: reportId,
    title: safeEnvelope.value.title,
    source: safeEnvelope.value.source,
    visibility: safeEnvelope.value.visibility,
    internal_url_path: `/reports/${reportId}`,
    share_url_path: `/r/${shareToken}`,
    status: blocked ? "blocked" : "shareable",
    created_at: createdAt,
    expires_at: expiresAt,
    created_by: options.createdBy || "a3-system",
    lifecycle: {
      expiry_policy: "default_30_days",
      revocable: true,
      view_audit_enabled: true,
      public_indexing_allowed: false
    },
    view_audit: {
      view_count: 0,
      last_viewed_at: null,
      last_event_id: null
    },
    share_link: {
      schema_version: "a3.report_share_link.v1",
      token_hash: shareTokenHash,
      token_hash_prefix: shareTokenHash.slice(0, 12),
      scope: "private_link",
      created_at: createdAt,
      expires_at: expiresAt,
      revoked_at: null,
      raw_token_returned_once: true
    },
    tenant_scope: {
      organization_id: options.organizationId || inputs.organizationId || "org-local",
      project_id: options.projectId || inputs.projectId || "project-local"
    },
    summary: safeEnvelope.value.summary,
    release_gate: safeEnvelope.value.release_gate,
    multimodal_review_queue: safeEnvelope.value.multimodal_review_queue,
    multimodal_repeat_stability: safeEnvelope.value.multimodal_repeat_stability,
    markdown_report: safeEnvelope.value.markdown_report,
    report_center: {
      json_available: true,
      markdown_available: true,
      hosted_page_available: !blocked,
      pdf_export_ready: true,
      audit_bundle_ready: Boolean(jsonReport.release_workflow?.audit_bundle),
      pr_comment_ready: Boolean(jsonReport.release_workflow?.pr_comment_markdown),
      release_evidence_ready: releaseEvidenceSummary.available === true
    },
    artifacts: [
      artifactDescriptor("json_report", "application/json", jsonReport),
      artifactDescriptor("markdown_report", "text/markdown", markdownReport),
      artifactDescriptor("hosted_report", "text/html", safeEnvelope.value),
      artifactDescriptor("release_evidence_summary", "application/json", releaseEvidenceSummary)
    ],
    release_evidence_summary: releaseEvidenceSummary,
    release_evidence_snapshot: releaseEvidenceSnapshot,
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
  const releaseEvidence = report.release_evidence_summary || payload.release_evidence_summary || {};
  const multimodalReviewQueue = report.multimodal_review_queue || payload.multimodal_review_queue || {};
  const multimodalRepeatStability = report.multimodal_repeat_stability
    || payload.multimodal_repeat_stability
    || {};
  const cases = Array.isArray(payload.cases) ? payload.cases.slice(0, 12) : [];
  const status = report.status || "unknown";

  if (status !== "shareable") {
    return renderDeniedReportHtml(report, status);
  }

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
        <div class="muted">${escapeHtml(report.report_id || "local-report")} / ${escapeHtml(report.created_at || "")} / expires ${escapeHtml(report.expires_at || "unknown")}</div>
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

    ${renderReleaseEvidenceHtml(releaseEvidence)}

    ${renderMultimodalRepeatStabilityHtml(multimodalRepeatStability)}

    ${renderMultimodalEvidenceRequestsHtml(multimodalReviewQueue)}

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

function renderDeniedReportHtml(report, status) {
  const reason = report.access_result || status || "unavailable";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A3 Report Unavailable</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fb; color: #172033; }
    main { max-width: 760px; margin: 0 auto; padding: 48px 20px; }
    .card { background: #fff; border: 1px solid #d9dee8; border-radius: 8px; padding: 20px; }
    .pill { display: inline-flex; border: 1px solid #c9d3e5; border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; background: #fff; }
    .muted { color: #667085; font-size: 13px; line-height: 1.5; }
    pre { white-space: pre-wrap; background: #101828; color: #f8fafc; border-radius: 8px; padding: 12px; overflow: auto; }
  </style>
</head>
<body>
  <main>
    <section class="card">
      <span class="pill">${escapeHtml(reason)}</span>
      <h1>A3 report is not available</h1>
      <p class="muted">This shared report link is expired, revoked, blocked, or unknown. The report body is not rendered for denied external access.</p>
      <pre>${escapeHtml(JSON.stringify({
    report_id: report.report_id || null,
    status,
    access_result: reason,
    token_hash_prefix: report.share_link?.token_hash_prefix || null,
    payload_hash_present: Boolean(report.sealed_evidence?.payload_hash)
  }, null, 2))}</pre>
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

function buildReleaseEvidenceSnapshot(summary = {}, options = {}) {
  const summaryHash = sha256(stableJson(summary || {}));
  return {
    schema_version: "a3.release_evidence_snapshot.v1",
    snapshot_id: `resnap_${summaryHash.slice(0, 12)}`,
    report_id: options.reportId || "unknown",
    source: options.source || "unknown",
    created_at: options.createdAt || null,
    summary_hash: summaryHash,
    summary_schema_version: summary.schema_version || "unknown",
    immutable_in_hosted_report: true,
    raw_fixture_exposed: false,
    raw_request_body_exposed: false,
    raw_share_token_exposed: false
  };
}

function renderReleaseEvidenceHtml(releaseEvidence = {}) {
  if (releaseEvidence.available !== true) {
    return "";
  }
  const rows = [
    ["Overall", releaseEvidence.overall_status || "unknown"],
    ["GitHub Check", `${releaseEvidence.github_check_publish?.status || "unknown"} / dry-run ${releaseEvidence.github_check_publish?.dry_run ? "yes" : "no"} / posted ${releaseEvidence.github_check_publish?.posted ? "yes" : "no"}`],
    ["PR Comment", `${releaseEvidence.github_pr_comment_publish?.status || "unknown"} / dry-run ${releaseEvidence.github_pr_comment_publish?.dry_run ? "yes" : "no"} / posted ${releaseEvidence.github_pr_comment_publish?.posted ? "yes" : "no"}`],
    ["Required Check", `${releaseEvidence.github_required_check_plan?.check_name || "unknown"} / maintainer approval ${releaseEvidence.github_required_check_plan?.maintainer_approval_required ? "required" : "not required"}`],
    ["Audit Bundle", `${releaseEvidence.audit_bundle_verification?.status || "unknown"} / root hash ${releaseEvidence.audit_bundle_verification?.root_hash_passed ? "pass" : "missing"}`],
    ["Audit Archive", `${releaseEvidence.audit_archive_verification?.status || "unknown"} / signature ${releaseEvidence.audit_archive_verification?.signature_passed ? "pass" : "missing"}`],
    ["Safety", `tokens ${releaseEvidence.safety?.token_included ? "included" : "not included"} / secrets ${releaseEvidence.safety?.contains_secret_values || releaseEvidence.safety?.secret_values_allowed ? "present" : "blocked"}`]
  ];
  return `<section class="card" style="margin-top: 20px;">
      <h2>Release Evidence</h2>
      <p class="muted">${escapeHtml(releaseEvidence.commercial_value || "Release evidence is summarized for hosted review.")}</p>
      <table>
        <tbody>
          ${rows.map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`).join("")}
        </tbody>
      </table>
    </section>`;
}

function renderMultimodalEvidenceRequestsHtml(queue = {}) {
  if (queue.available !== true) return "";
  const summary = queue.summary || {};
  const rows = (Array.isArray(queue.items) ? queue.items : []).flatMap((item) => (
    (Array.isArray(item.evidence_requests) ? item.evidence_requests : []).map((request) => ({
      case_id: item.case_id || "unknown",
      status: request.status || "unknown",
      owner_lane: request.owner_lane || "unknown",
      required_kinds: Array.isArray(request.required_evidence_kinds) ? request.required_evidence_kinds.join(", ") : "none",
      submitted_hashes: (Array.isArray(request.evidence_refs) ? request.evidence_refs : [])
        .map((reference) => `${reference.kind || "evidence"}:${hashPrefix(reference.evidence_hash)}`)
        .join(", ") || "pending",
      due_at: request.due_at || "unknown",
      event_count: request.event_count || 0
    }))
  ));
  return `<section class="card" style="margin-top: 20px;">
      <h2>Multimodal Review Evidence Requests</h2>
      <p class="muted">Hash-only coordination records. Evidence acceptance is not a human disposition and cannot change A2 grading or release authority.</p>
      <div class="grid" aria-label="Evidence request metrics">
        ${metric("Requests", summary.evidence_request_count || 0)}
        ${metric("Open", summary.evidence_request_open_count || 0)}
        ${metric("Overdue", summary.evidence_request_overdue_count || 0)}
        ${metric("Submitted", summary.evidence_request_submitted_count || 0)}
        ${metric("Accepted", summary.evidence_request_accepted_count || 0)}
      </div>
      ${rows.length ? `<table>
        <thead><tr><th>Case</th><th>Status</th><th>Owner</th><th>Required evidence</th><th>Submitted hashes</th><th>Due</th></tr></thead>
        <tbody>${rows.map((row) => `<tr>
          <td>${escapeHtml(row.case_id)}</td>
          <td>${escapeHtml(row.status)}</td>
          <td>${escapeHtml(row.owner_lane)}</td>
          <td>${escapeHtml(row.required_kinds)}</td>
          <td>${escapeHtml(row.submitted_hashes)}</td>
          <td>${escapeHtml(row.due_at)} / ${escapeHtml(row.event_count)} event(s)</td>
        </tr>`).join("")}</tbody>
      </table>` : `<p class="muted">No evidence requests are recorded for this report snapshot.</p>`}
    </section>`;
}

function renderMultimodalRepeatStabilityHtml(stability = {}) {
  if (stability.available !== true) return "";
  const summary = stability.summary || {};
  const humanReview = stability.human_review || {};
  const candidate = stability.candidate_binding || {};
  const metrics = Array.isArray(stability.metrics) ? stability.metrics : [];
  const metricRows = metrics.map((item) => `<tr>
            <th>${escapeHtml(item.metric_id || "metric")}</th>
            <td>${escapeHtml((item.repeat_estimates || []).join(" / ") || "unavailable")}</td>
            <td>${item.complete_across_repeats ? "complete" : "incomplete"}</td>
          </tr>`).join("");
  return `<section class="card" style="margin-top: 20px;">
      <h2>Multimodal Repeat Stability</h2>
      <p class="${summary.quality_qualified ? "passed" : "blocked"}">${escapeHtml(
        stability.interpretation || "Repeat stability is evidence only."
      )}</p>
      <p class="muted">Stable repetition does not mean qualified quality. This evidence cannot change A2 grading or release authority.</p>
      <div class="grid" aria-label="Repeat stability metrics">
        ${metric("Repeats", summary.repeat_count || 0)}
        ${metric("Required units", summary.required_source_unit_count || 0)}
        ${metric("Blocked repeats", summary.retained_blocked_count || 0)}
        ${metric("Human receipts", humanReview.receipt_count || 0)}
      </div>
      ${metricRows ? `<table>
        <thead><tr><th>Metric</th><th>Repeat estimates</th><th>Coverage</th></tr></thead>
        <tbody>${metricRows}</tbody>
      </table>` : ""}
      <p class="muted">Human review: ${escapeHtml(humanReview.collection_state || "unknown")} / pending queue ${escapeHtml(humanReview.pending_queue_receipt_count || 0)}. Shared candidate verified: ${candidate.verified ? "yes" : "no"}. Release authority: no.</p>
    </section>`;
}

function hashPrefix(value) {
  const text = String(value || "missing");
  return text.length > 22 ? `${text.slice(0, 18)}...` : text;
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

function stableShareToken(reportId, createdAt) {
  try {
    return `a3s_${randomUUID().replaceAll("-", "").slice(0, 24)}`;
  } catch {
    return `a3s_${sha256(`${reportId}:${createdAt}`).slice(0, 24)}`;
  }
}

function defaultExpiry(createdAt) {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  date.setUTCDate(date.getUTCDate() + 30);
  return date.toISOString();
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
