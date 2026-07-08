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
    multimodal_provider_readiness: jsonReport.multimodal_provider_readiness,
    multimodal_release_readiness: jsonReport.multimodal_release_readiness,
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
    multimodal_provider_readiness: safeEnvelope.value.multimodal_provider_readiness,
    multimodal_release_readiness: safeEnvelope.value.multimodal_release_readiness,
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
  const multimodalProviderReadiness = report.multimodal_provider_readiness
    || payload.multimodal_provider_readiness
    || {};
  const multimodalReleaseReadiness = report.multimodal_release_readiness
    || payload.multimodal_release_readiness
    || {};
  const cases = Array.isArray(payload.cases) ? payload.cases.slice(0, 12) : [];
  const status = report.status || "unknown";

  if (status !== "shareable") {
    return renderDeniedReportHtml(report, status);
  }

  const gateBlocked = releaseGate.decision === "block_release";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(report.title || payload.title || "A3 Shareable Report")}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef1f8;
      --bg-deep: #e5e9f4;
      --panel: #ffffff;
      --line: rgba(23, 32, 58, 0.1);
      --text: #141a2e;
      --muted: #6b7690;
      --brand: #6366f1;
      --accent: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #38bdf8 100%);
      --shadow: 0 18px 46px -18px rgba(20, 26, 46, 0.35), 0 2px 6px -2px rgba(20, 26, 46, 0.12);
      font-family: "Inter var", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; color: var(--text);
      background:
        radial-gradient(1100px 620px at 12% -8%, rgba(124, 92, 255, 0.16), transparent 60%),
        radial-gradient(980px 560px at 105% 0%, rgba(56, 189, 248, 0.16), transparent 55%),
        linear-gradient(180deg, var(--bg), var(--bg-deep));
      background-attachment: fixed;
    }
    main { max-width: 1120px; margin: 0 auto; padding: 40px 24px 56px; }
    header {
      position: relative; overflow: hidden;
      background: linear-gradient(135deg, rgba(255,255,255,0.96), rgba(255,255,255,0.82));
      border: 1px solid var(--line); border-radius: 18px; box-shadow: var(--shadow);
      display: flex; justify-content: space-between; gap: 18px; align-items: flex-start;
      padding: 26px 28px;
    }
    header::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 4px; background: var(--accent); }
    h1 {
      margin: 0; font-size: 30px; line-height: 1.15; font-weight: 800; letter-spacing: -0.02em;
      background: linear-gradient(120deg, #141a2e 20%, #4b3fd6 60%, #2b8fd6 100%);
      -webkit-background-clip: text; background-clip: text; color: transparent;
    }
    h2 { margin: 0 0 14px; font-size: 15px; font-weight: 750; letter-spacing: -0.01em; }
    .muted { color: var(--muted); font-size: 13px; line-height: 1.5; margin-top: 8px; }
    .pill {
      display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(99,102,241,0.24);
      border-radius: 999px; padding: 6px 14px; font-size: 12px; font-weight: 800; letter-spacing: 0.03em;
      text-transform: uppercase; color: #4b3fd6; background: linear-gradient(135deg, rgba(99,102,241,0.14), rgba(56,189,248,0.12));
    }
    .pill::before { content: ""; width: 7px; height: 7px; border-radius: 999px; background: currentColor; box-shadow: 0 0 0 3px rgba(99,102,241,0.16); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0; }
    .card {
      background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 20px;
      box-shadow: var(--shadow);
    }
    .metric { position: relative; overflow: hidden; }
    .metric::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 5px; background: var(--accent); }
    .metric strong { display: block; font-size: 30px; font-weight: 800; letter-spacing: -0.02em; }
    .metric span { color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
    table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; box-shadow: var(--shadow); }
    th, td { text-align: left; border-bottom: 1px solid #eef1f7; padding: 12px 14px; font-size: 13px; vertical-align: top; }
    th { background: #f5f7fc; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; font-size: 11px; }
    tbody tr:nth-child(even) td { background: rgba(99,102,241,0.03); }
    tr:last-child td { border-bottom: 0; }
    .tag { display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 10px; font-size: 11.5px; font-weight: 700; border: 1px solid transparent; }
    .tag.passed { color: #0f8a54; background: #dff5e9; border-color: rgba(15,138,84,0.2); }
    .tag.failed { color: #d92d20; background: #fdeceb; border-color: rgba(217,45,32,0.2); }
    .blocked { color: #d92d20; font-weight: 800; font-size: 18px; margin: 0; }
    .passed { color: #0f8a54; font-weight: 800; font-size: 18px; margin: 0; }
    pre {
      white-space: pre-wrap; background: linear-gradient(160deg, #171b2e, #0d1020); color: #e6ebff;
      border-radius: 12px; padding: 16px; overflow: auto; font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12.5px; line-height: 1.6; border: 1px solid rgba(124,92,255,0.24);
    }
    @media (max-width: 640px) { header { flex-direction: column; } h1 { font-size: 24px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>${escapeHtml(report.title || payload.title || "A3 Shareable Report")}</h1>
        <div class="muted">${escapeHtml(report.report_id || "local-report")} &middot; ${escapeHtml(report.created_at || "")} &middot; expires ${escapeHtml(report.expires_at || "unknown")}</div>
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
      <p class="${gateBlocked ? "blocked" : "passed"}">
        ${escapeHtml(releaseGate.decision_label || releaseGate.decision || "unknown")}
      </p>
      <p class="muted">${escapeHtml(releaseGate.summary || releaseGate.reason || "No release gate summary available.")}</p>
    </section>

    ${renderReleaseEvidenceHtml(releaseEvidence)}

    ${renderMultimodalRepeatStabilityHtml(multimodalRepeatStability)}

    ${renderMultimodalProviderReadinessHtml(multimodalProviderReadiness)}
    ${renderMultimodalReleaseReadinessHtml(multimodalReleaseReadiness)}

    ${renderMultimodalEvidenceRequestsHtml(multimodalReviewQueue)}

    <section style="margin-top: 24px;">
      <h2>Case Evidence</h2>
      <table>
        <thead><tr><th>Case</th><th>Status</th><th>Score</th><th>Failure Class</th><th>Summary</th></tr></thead>
        <tbody>
          ${cases.map((item) => `<tr>
            <td>${escapeHtml(item.case_id || item.title || "case")}</td>
            <td><span class="tag ${item.passed ? "passed" : "failed"}">${escapeHtml(item.passed ? "passed" : "failed")}</span></td>
            <td>${escapeHtml(item.score ?? "")}</td>
            <td>${escapeHtml(item.primary_failure_class || "none")}</td>
            <td>${escapeHtml(item.failure_summary || "")}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </section>

    <section class="card" style="margin-top: 24px;">
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
    :root {
      color-scheme: light;
      --line: rgba(23, 32, 58, 0.1);
      --muted: #6b7690;
      --shadow: 0 18px 46px -18px rgba(20, 26, 46, 0.35), 0 2px 6px -2px rgba(20, 26, 46, 0.12);
      font-family: "Inter var", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; color: #141a2e; min-height: 100vh; display: grid; place-items: center;
      background:
        radial-gradient(900px 520px at 20% -10%, rgba(124, 92, 255, 0.16), transparent 60%),
        radial-gradient(820px 480px at 108% 0%, rgba(56, 189, 248, 0.16), transparent 55%),
        linear-gradient(180deg, #eef1f8, #e5e9f4);
    }
    main { max-width: 620px; margin: 0 auto; padding: 40px 24px; width: 100%; }
    .card {
      position: relative; overflow: hidden; text-align: center;
      background: linear-gradient(160deg, #ffffff, #f5f7fc);
      border: 1px solid var(--line); border-radius: 20px; padding: 40px 32px; box-shadow: var(--shadow);
    }
    .card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 4px; background: linear-gradient(135deg, #f97066, #f59e0b); }
    .pill {
      display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(180,83,9,0.28);
      border-radius: 999px; padding: 6px 14px; font-size: 12px; font-weight: 800; letter-spacing: 0.03em;
      text-transform: uppercase; color: #b45309; background: #fdf1dc;
    }
    h1 { margin: 20px 0 10px; font-size: 26px; font-weight: 800; letter-spacing: -0.02em; }
    .muted { color: var(--muted); font-size: 13.5px; line-height: 1.6; max-width: 440px; margin: 0 auto 20px; }
    pre {
      text-align: left; white-space: pre-wrap; background: linear-gradient(160deg, #171b2e, #0d1020); color: #e6ebff;
      border-radius: 12px; padding: 16px; overflow: auto; border: 1px solid rgba(124,92,255,0.24);
      font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; line-height: 1.6;
    }
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

function renderMultimodalProviderReadinessHtml(readiness = {}) {
  if (readiness.available !== true) return "";
  const summary = readiness.summary || {};
  const latency = readiness.latency_diagnostic || {};
  const providers = Array.isArray(readiness.providers) ? readiness.providers : [];
  const profiles = Array.isArray(latency.profiles) ? latency.profiles : [];
  return `<section class="card" style="margin-top: 20px;">
      <h2>Multimodal Provider Readiness</h2>
      <p class="blocked">${escapeHtml(readiness.interpretation || "Provider diagnostics are blocked.")}</p>
      <p class="muted">This is evaluation availability evidence, not production routing, capacity, operational health, quality comparison, or release authority.</p>
      <div class="grid" aria-label="Provider readiness metrics">
        ${metric("Attempts", summary.attempted_count || 0)}
        ${metric("Completed", summary.completed_count || 0)}
        ${metric("Timeouts", summary.timeout_case_count || 0)}
        ${metric("Eligible", summary.eligible_count || 0)}
      </div>
      ${providers.length ? `<table>
        <thead><tr><th>Model</th><th>Qualification</th><th>Completed</th><th>Timeout</th><th>Eligible</th><th>P95</th></tr></thead>
        <tbody>${providers.map((provider) => `<tr>
          <td>${escapeHtml(provider.model_id || "model")}</td>
          <td>${escapeHtml(provider.qualification_state || "unknown")}</td>
          <td>${escapeHtml(`${provider.completed_count || 0}/${provider.attempted_count || 0}`)}</td>
          <td>${escapeHtml(provider.timeout_case_count || 0)}</td>
          <td>${escapeHtml(provider.eligible_count || 0)}</td>
          <td>${escapeHtml(provider.latency_seconds?.p95_nearest_rank ?? "unavailable")}s</td>
        </tr>`).join("")}</tbody>
      </table>` : ""}
      ${profiles.length ? `<table style="margin-top: 12px;">
        <thead><tr><th>Profile</th><th>State</th><th>Parse</th><th>Wall time</th><th>Diagnosis</th></tr></thead>
        <tbody>${profiles.map((profile) => `<tr>
          <td>${escapeHtml(profile.profile || "profile")}</td>
          <td>${escapeHtml(profile.state || "unknown")}</td>
          <td>${escapeHtml(profile.parse_state || "unknown")}</td>
          <td>${escapeHtml(profile.phase_seconds?.caller_wall_seconds ?? "unavailable")}s</td>
          <td>${escapeHtml(profile.error_class || "none")}</td>
        </tr>`).join("")}</tbody>
      </table>` : ""}
      <p class="muted">Cold wall ${escapeHtml(latency.cold_wall_seconds ?? "unavailable")}s; fastest warm wall ${escapeHtml(latency.fastest_warm_wall_seconds ?? "unavailable")}s. Valid structured profiles ${escapeHtml(summary.valid_structured_profile_count || 0)}/${escapeHtml(summary.profile_count || 0)}. Release authority: no.</p>
    </section>`;
}

function renderMultimodalReleaseReadinessHtml(readiness = {}) {
  if (readiness.available !== true) return "";
  const summary = readiness.summary || {};
  const controls = readiness.control_policy || {};
  const local = readiness.local_runtime || {};
  const repeat = readiness.repeat_evidence || {};
  const review = readiness.human_review || {};
  const persistence = readiness.persistence || {};
  const candidate = readiness.candidate_binding || {};
  const taxonomy = Array.isArray(controls.taxonomy_assessments) ? controls.taxonomy_assessments : [];
  return `<section class="card" style="margin-top: 20px;">
      <h2>Multimodal Release Readiness</h2>
      <p class="blocked">${escapeHtml(readiness.interpretation || "Multimodal release readiness remains blocked.")}</p>
      <p class="muted">Safe controls, attack sensitivity, runtime structure, repeat quality, human review, persistence, and candidate binding are independent gates. A3 does not recompute A2 qualification.</p>
      <div class="grid" aria-label="Multimodal release readiness metrics">
        ${metric("Cloud controls", summary.cloud_eligible_count || 0)}
        ${metric("Safe false positives", `${summary.safe_control_false_positive_count || 0}/${summary.safe_control_count || 0}`)}
        ${metric("Attack detections", `${summary.taxonomy_detected_count || 0}/${summary.taxonomy_eligible_count || 0}`)}
        ${metric("Structured profiles", summary.local_completed_profile_count || 0)}
      </div>
      ${taxonomy.length ? `<table>
        <thead><tr><th>Control</th><th>Detected</th><th>Sensitivity</th><th>Minimum</th><th>Result</th></tr></thead>
        <tbody>${taxonomy.map((item) => `<tr>
          <td>${escapeHtml(item.taxonomy_id || "taxonomy")}</td>
          <td>${escapeHtml(`${item.detected_count || 0}/${item.eligible_count || 0}`)}</td>
          <td>${escapeHtml(item.sensitivity ?? "unavailable")}</td>
          <td>${escapeHtml(item.minimum_sensitivity ?? "unavailable")}</td>
          <td>${item.passed ? "passed" : "blocked"}</td>
        </tr>`).join("")}</tbody>
      </table>` : ""}
      <p class="muted">Local candidate ${escapeHtml(local.model_id || "unknown")}: ${escapeHtml(local.runtime_promotion_state || "unknown")}. Repeat quality/stability: ${escapeHtml(repeat.quality_state || "unknown")} / ${escapeHtml(repeat.stability_state || "unknown")}. Human review: ${escapeHtml(review.collection_state || "unknown")}. PostgreSQL: ${escapeHtml(persistence.proof_state || "unknown")}. Shared candidate verified: ${candidate.verified ? "yes" : "no"}. Release authority: no.</p>
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
