import {
  buildCsvReport,
  buildDashboardSummary,
  buildJsonReport,
  buildMarkdownReport,
  buildToolCallDiffs,
  clusterFailures,
  filterCases,
  getFilterOptions,
  normalizeCases,
  summarizeCoverage,
  summarizeCloudConsoleShell,
  summarizeArtifactRegistryExport,
  summarizeMediaReadiness,
  summarizeOfficialAshrGap,
  summarizeOfficialCodeCrawlParity,
  summarizeOfficialFrontendMirror,
  summarizeOfficialParityRoadmap,
  summarizeObservabilityReplayMatrix,
  summarizeProductConsoleExport,
  summarizeSaasAdminExport,
  summarizeRegressionFactory,
  summarizeExportRedactionFirewall,
  summarizeIncidentReplayQueue,
  summarizeReviewerWorkflowBoard,
  summarizeReleaseGate,
  summarizeReleaseEvidenceSummary,
  summarizeReleaseWarRoom,
  summarizeReleaseWorkflow,
  summarizeRequestProvenance,
  summarizeUsageQuota
} from "../../../services/report/report_builder.mjs";
import { mapAshrSampleToA3Fixtures } from "../../../services/report/p3_ashr_mapper.mjs?v=a3-polish";
import {
  createShareableA3Report,
  fetchA3AdminConsole,
  fetchA3ArtifactRegistry,
  fetchA3DashboardSnapshot,
  fetchA3ProductConsole,
  fetchA3ReportCenter,
  fetchA3ReviewWorkflow,
  fetchA3SchemaDriftRadar,
  fetchA3UsageLedger,
  fetchA3BillingReadiness,
  fetchA3BillingMigrationReadiness,
  fetchA3LiveWorkflowReadiness,
  fetchA3LiveOpsControlPlane,
  fetchA3NotificationControlPlane,
  fetchA3PeerBranchCalibration,
  planA3AdminAction,
  submitA3AdminAction,
  submitA3ReviewWaiver,
  submitA3ReviewApproval,
  submitA3ReviewDenial,
  revokeShareableA3Report,
  isA3ApiSource
} from "./api-client.mjs";
import { renderSaasRuntimePanel } from "./components/saas-runtime-panel.mjs";
import { renderSaasAdminConsole } from "./components/saas-admin-console.mjs";
import { renderEnterpriseReadinessPanel } from "./components/enterprise-readiness-panel.mjs";
import { renderProductConsolePanel } from "./components/product-console-panel.mjs";
import { renderNotificationControlPlanePanel } from "./components/notification-control-plane.mjs";
import { buildSaasAdminConsole } from "../../../services/report/a3_saas_admin.mjs";
import { buildEnterpriseReadinessReport } from "../../../services/report/a3_enterprise_readiness.mjs";
import { buildA3ProductConsole } from "../../../services/report/a3_product_console.mjs";
import { buildA3ArtifactRegistry } from "../../../services/report/a3_artifact_registry.mjs";
import { buildA3BillingReadiness } from "../../../services/report/a3_billing_readiness.mjs";
import { summarizeA3PeerBranchCalibration } from "../../../services/report/a3_peer_branch_calibration.mjs";
import { buildA3LiveWorkflowReadiness } from "../../../services/report/a3_live_workflow_readiness.mjs";
import { buildA3LiveOpsControlPlane } from "../../../services/report/a3_live_ops_control_plane.mjs";
import { buildA3NotificationControlPlane } from "../../../services/report/a3_notification_control_plane.mjs";
import { setupVisualShell, visualNavigationSelector } from "./visual-shell.mjs";

const state = {
  runs: null,
  grades: null,
  coverage: {},
  evidenceReadiness: {},
  caseBook: {},
  regressionReplay: {},
  commercialReadiness: {},
  resultPersistence: {},
  releaseUnblockChecklist: {},
  releaseGate: {},
  requestProvenance: {},
  usageQuota: {},
  usageQuotaApiProbe: {},
  mediaSignedUrlCoverage: {},
  authCheck: {},
  frontendSummary: {},
  frontendMirror: {},
  frontendCodeCrawl: {},
  saasRuntime: {},
  saasAdmin: {},
  enterpriseReadiness: {},
  productConsole: {},
  usageLedger: {},
  billingReadiness: {},
  billingMigrationReadiness: {},
  liveWorkflowReadiness: {},
  liveOpsControlPlane: {},
  notificationControlPlane: {},
  reportCenter: {},
  artifactRegistry: {},
  schemaDriftRadar: {},
  peerBranchCalibration: {},
  githubPublishEvidence: {},
  reviewWorkflow: {},
  releaseEvidence: {},
  releaseEvidenceReadbacks: {},
  selectedAdminAction: "view_usage",
  selectedAdminPlan: null,
  selectedAdminReceipt: null,
  selectedReviewReceipt: null,
  reviewFilter: { releaseVersion: "", environment: "", actorHash: "" },
  cases: [],
  filteredCases: [],
  selectedCaseId: null,
  source: "mock"
};

const $ = (id) => document.getElementById(id);

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
}

async function loadOptionalJson(path) {
  try {
    return await loadJson(path);
  } catch (error) {
    console.warn(error.message);
    return {};
  }
}

async function loadReleaseEvidenceFixtures() {
  const githubCheckReadback = await loadOptionalJson("../../fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json");
  const githubPrCommentReadback = await loadOptionalJson("../../fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json");
  const githubRequiredCheckProof = await loadOptionalJson("../../fixtures/a3/p3/a3_github_required_check_proof_plan_only.redacted.json");
  return {
    githubCheckPublishReceipt: await loadOptionalJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
    githubPrCommentPublishReceipt: await loadOptionalJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
    githubRequiredCheckPlan: await loadOptionalJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json"),
    githubCheckReadback,
    githubPrCommentReadback,
    githubRequiredCheckProof,
    readback_records: [githubCheckReadback, githubPrCommentReadback, githubRequiredCheckProof]
      .filter((item) => item && item.schema_version),
    auditBundleVerification: await loadOptionalJson("../../fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json"),
    auditArchiveVerification: await loadOptionalJson("../../fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json")
  };
}

function formatJson(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildA3BillingMigrationReadiness(options = {}) {
  return {
    schema_version: "a3.billing_migration_readiness.v1",
    contract_id: "a3_billing_migration_readiness_browser_view",
    source_branch: "origin/codex/a1-local-sdk-runner",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local",
      environment_id: options.environmentId || "staging"
    },
    purpose: "Browser-safe A3 view of A1 billing ledger migration readiness. The complete hashed contract is served by the local A3 API.",
    summary: {
      status: "read_only_migration_contract_ready",
      ready_for_live_customer_billing: false,
      consumed_evidence_count: 4,
      upstream_commit_count: 3,
      a3_customer_claim: "A3 can display billing migration readiness and safety boundaries, but cannot claim live billing until A1 exposes authenticated billing ledger APIs."
    },
    upstream_evidence: {
      durable_billing_ledger_migration: {
        source_commit: "91213fc",
        a3_consumption_state: "schema_and_safety_contract_consumed"
      },
      replay_evidence: {
        source_commit: "f8ee956",
        fixture_path: "docs/a1/evidence/billing_replay_fixture_round35.json",
        a3_consumption_state: "public_replay_fixture_consumed_as_redacted_read_model"
      },
      live_smoke: {
        source_commit: "11ac03e",
        a3_consumption_state: "live_smoke_contract_read_from_diff_not_replayed"
      },
      official_api_readonly_summary: {
        source_commit: "f8ee956",
        summary_path: "docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json",
        status: "ok"
      }
    },
    db_contract: {
      durable_backend_owner: "A1",
      a3_db_mutation_required: false,
      tables: [
        {
          name: "billing_accounts",
          purpose: "Provider customer/account reference per organization and project.",
          tenant_column: "organization_id",
          project_column: "project_id"
        },
        {
          name: "billing_provider_events",
          purpose: "Provider webhook idempotency, signature summary, replay status, and hash-only payload reference.",
          tenant_column: "organization_id",
          project_column: "project_id"
        },
        {
          name: "billing_ledger_events",
          purpose: "Append-only normalized billing ledger rows for invoices, refunds, cancellations, checkout, and usage reconciliation.",
          tenant_column: "organization_id",
          project_column: "project_id"
        }
      ]
    },
    api_contract: [
      {
        route: "GET /api/a3/billing/readiness",
        owner_lane: "A3",
        status: "existing_read_only_surface"
      },
      {
        route: "future GET /v1/projects/{project_id}/billing/ledger-summary",
        owner_lane: "A1",
        status: "required_before_live_a3_customer_display"
      },
      {
        route: "future GET /v1/projects/{project_id}/billing/provider-events",
        owner_lane: "A1",
        status: "required_for_audit_readback"
      }
    ],
    safety: {
      browser_safe_view: true,
      env_local_read: false,
      real_api_called_by_a3: false,
      real_payment_provider_called: false,
      billing_mutation_performed_by_a3: false
    }
  };
}

function fillSelect(selectId, values) {
  const select = $(selectId);
  while (select.options.length > 1) {
    select.remove(1);
  }
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

function applyFilters() {
  const status = $("filter-status").value;
  const family = $("filter-family").value;
  const failure = $("filter-failure").value;
  const run = $("filter-run").value;
  const severity = $("filter-severity").value;
  const selectedScoreBand = $("filter-score").value;
  const judgeMode = $("filter-judge").value;

  state.filteredCases = filterCases(state.cases, {
    status,
    family,
    failureClass: failure,
    runId: run,
    severity,
    scoreBand: selectedScoreBand,
    judgeMode
  });

  if (!state.filteredCases.some((item) => item.case_id === state.selectedCaseId)) {
    state.selectedCaseId = state.filteredCases[0]?.case_id || null;
  }

  renderCaseList();
  renderTriageQueue();
  renderPrintReport();
  renderDetail();
}

function renderSummary() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  $("metric-runs").textContent = summary.totalRuns;
  $("metric-cases").textContent = summary.totalCases;
  $("metric-pass-rate").textContent = `${summary.passRate}%`;
  $("metric-score").textContent = summary.avgScore;
  $("metric-trace").textContent = `${summary.traceCompleteness}%`;
  $("metric-media").textContent = summary.mediaEvidenceCases;
  const coverageLabel = state.coverage?.pack_id ? `; Coverage: ${state.coverage.pack_id}` : "";
  $("data-source").textContent = `${sourceLabel(state.source)}: ${summary.lastRunId}${coverageLabel}`;
  setMetricState("metric-pass-card", summary.passRate >= 80 ? "good" : summary.passRate >= 50 ? "warn" : "risk");
  setMetricState("metric-score-card", summary.avgScore >= 80 ? "good" : summary.avgScore >= 60 ? "warn" : "risk");
  setMetricState("metric-trace-card", summary.traceCompleteness >= 90 ? "good" : summary.traceCompleteness >= 70 ? "warn" : "risk");
}

function setMetricState(cardId, stateName) {
  const card = $(cardId);
  card.classList.remove("good", "warn", "risk");
  card.classList.add(stateName);
}

function renderConsoleStats() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  const runs = Array.isArray(state.runs?.runs) ? state.runs.runs : [];
  const datasets = new Set(runs.map((item) => item.dataset_id).filter(Boolean));
  const runners = new Set(runs.map((item) => item.runner_id).filter(Boolean));
  $("workflow-requests").textContent = workflowRequestLabel(state.source);
  $("workflow-datasets").textContent = `${datasets.size || 1} dataset`;
  $("workflow-runs").textContent = `${summary.totalRuns} run`;
  $("workflow-analysis").textContent = `${summary.failed} failed`;
  renderUsageQuota(summary);
  renderMediaReadiness();
  $("object-summary").replaceChildren(...[
    miniRow("Requests", workflowRequestDetail(state.source)),
    miniRow("Datasets", String(datasets.size || 1)),
    miniRow("Runs", String(summary.totalRuns)),
    miniRow("Runners", String(runners.size || 1)),
    miniRow("Export", "JSON / CSV / Markdown")
  ]);
  renderCloudShell();
  renderOfficialGap();
  renderOfficialFrontendMirror();
  renderOfficialCodeCrawlParity();
  renderOfficialParityRoadmap();
  renderRequestProvenance();
}

function renderUsageQuota(summary) {
  const usageQuota = summarizeUsageQuota(state.usageQuota, state.usageQuotaApiProbe);
  const channelText = usageQuota.channels.join(", ") || "unknown";
  const apiAccess = usageQuota.direct_api_accessible ? "API-key accessible" : usageQuota.oauth_only_functions.length ? "OAuth-gated API" : "frontend confirmed";
  $("usage-detail").textContent = usageQuota.available
    ? `${usageQuota.frontend_modules.join(", ") || "Usage modules"} observed in Ashr Lab; ${channelText} channels. ${apiAccess}.`
    : `${summary.traceCompleteness}% trace coverage, ${summary.mediaEvidenceCases} media case(s), ${summary.vmStreamCases} VM stream case(s). Quota is tracked as a known external field until Ashr usage API is exposed to A3.`;
  $("usage-bar").style.width = `${Math.min(100, Math.max(0, usageQuota.channels.length ? usageQuota.channels.length * 25 : summary.traceCompleteness))}%`;
  $("usage-quota-list").replaceChildren(...[
    miniRow("Channels", channelText),
    miniRow("Frontend functions", usageQuota.frontend_source_functions.join(", ") || "unknown"),
    miniRow("API-key access", usageQuota.direct_api_accessible ? "yes" : "no"),
    miniRow("OAuth-gated", usageQuota.oauth_only_functions.join(", ") || "none"),
    miniRow("Decision", usageQuota.direct_api_accessible ? "map API fields" : "show frontend-confirmed quota state")
  ]);
}

function renderMediaReadiness() {
  const media = summarizeMediaReadiness(state.runs, state.grades, state.usageQuota, state.mediaSignedUrlCoverage);
  const policy = $("media-render-policy");
  policy.className = `badge ${media.live_rendering_allowed ? "pass" : "warn"}`;
  policy.textContent = media.live_rendering_allowed ? "live preview" : "metadata only";
  $("media-readiness-summary").textContent = media.available
    ? `${media.media_case_count} media case(s), ${media.evidence_item_count} evidence item(s), ${media.vm_stream_count} VM stream(s). ${media.guidance}`
    : "No media evidence is loaded for this data source. Use the P3 Media Sample to inspect calibrated media behavior.";
  $("media-channel-strip").replaceChildren(...(
    media.channels.length
      ? media.channels.map((channel) => {
        const node = document.createElement("span");
        node.className = `channel-pill ${media.signed_url_unconfirmed_types.includes(channel) ? "warn" : ""}`;
        node.textContent = channel;
        return node;
      })
      : [emptyPill("no media channels")]
  ));
  $("media-readiness-list").replaceChildren(
    miniRow("Output paths", `${media.output_path_key_count} key(s)`),
    miniRow("Signed URL keys", `${media.signed_url_key_count} key(s)`),
    miniRow("Signed URL confirmed", media.signed_url_confirmed_types.join(", ") || "none"),
    miniRow("Still unconfirmed", media.signed_url_unconfirmed_types.join(", ") || "none"),
    miniRow("Live rendering", media.live_rendering_allowed ? "allowed" : "blocked by safety"),
    miniRow("Values saved", media.values_redacted ? "redacted only" : "unknown")
  );
  $("media-channel-matrix").replaceChildren(...(
    media.channel_matrix.length
      ? media.channel_matrix.map((channel) => mediaMatrixRow(channel))
      : [emptyMatrixRow("No channel matrix is available for this source.")]
  ));
  $("media-evidence-queue").replaceChildren(...(
    media.evidence_queue.length
      ? media.evidence_queue.map((item) => mediaQueueRow(item))
      : [emptyMatrixRow("No media evidence queue is available for this source.")]
  ));
}

function emptyPill(label) {
  const node = document.createElement("span");
  node.className = "channel-pill warn";
  node.textContent = label;
  return node;
}

function mediaMatrixRow(channel) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(channel.channel)}</strong>
      <span class="badge ${channel.live_preview_allowed ? "pass" : channel.signed_url_confirmed ? "warn" : "neutral"}">${escapeHtml(channel.preview_policy)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(channel.case_evidence_count)} case(s)</span>
      <span>output path ${channel.output_path_confirmed ? "yes" : "no"}</span>
      <span>signed URL ${channel.signed_url_confirmed ? "yes" : "no"}</span>
    </div>
    <div class="muted">${escapeHtml(channel.decision)}</div>
  `;
  return node;
}

function mediaQueueRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(item.case_id)}</strong>
      <span class="badge ${item.safe_to_render ? "pass" : item.signed_url_status === "unconfirmed" ? "warn" : "neutral"}">${escapeHtml(item.preview_policy)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(report.tenant_scope?.workspace_id || "workspace-local")}</span>
      <span>${escapeHtml(report.tenant_scope?.project_id || "project-local")}</span>
      <span>${escapeHtml(report.tenant_scope?.environment_id || "staging")}</span>
      <span>${escapeHtml(report.share_link?.scope || "private_link")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(item.primary_media_type)}</span>
      <span>${escapeHtml(item.media_types.join(", ") || "unknown")}</span>
      <span>${escapeHtml(item.evidence_count)} evidence</span>
      <span>${escapeHtml(item.vm_stream_count)} vm</span>
    </div>
    <div class="muted">${escapeHtml(item.title)}</div>
    <div class="muted">${escapeHtml(item.next_action)}</div>
  `;
  return node;
}

function emptyMatrixRow(message) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `<div class="muted">${escapeHtml(message)}</div>`;
  return node;
}

function renderCloudShell() {
  const shell = summarizeCloudConsoleShell(
    state.authCheck,
    state.frontendSummary,
    state.requestProvenance,
    state.usageQuota,
    state.usageQuotaApiProbe
  );
  $("cloud-shell-summary").textContent = shell.available
    ? `${shell.observed_page_count} official page(s) observed. Real cloud mutations are ${shell.real_mutations_enabled ? "enabled" : "disabled"} in A3.`
    : "Cloud/admin areas are shown as a local mock shell only. No real auth, team, key, billing, or mutation controls are wired.";
  $("cloud-shell-list").replaceChildren(...shell.sections.map((section) => cloudRow(section)));
  $("cloud-action-list").replaceChildren(...shell.actions.map((action) => cloudActionRow(action)));
}

function cloudRow(section) {
  const node = document.createElement("div");
  node.className = "cloud-row";
  node.innerHTML = `
    <div class="cloud-head">
      <strong>${escapeHtml(section.area)}</strong>
      <span class="badge ${cloudStatusClass(section.status)}">${escapeHtml(section.status)}</span>
    </div>
    <div class="muted">${escapeHtml(section.detail)}</div>
  `;
  return node;
}

function cloudActionRow(action) {
  const node = document.createElement("div");
  node.className = "action-row";
  node.innerHTML = `
    <div class="action-head">
      <strong>${escapeHtml(action.action)}</strong>
      <span class="badge ${action.enabled ? "pass" : "neutral"}">${escapeHtml(action.mode)}</span>
    </div>
    <div class="muted">${escapeHtml(action.surface)} / ${escapeHtml(action.reason)}</div>
  `;
  return node;
}

function cloudStatusClass(status) {
  if (["observed", "read-only samples", "frontend-confirmed", "report-only"].includes(status)) {
    return "info";
  }
  if (["redacted", "OAuth-gated", "known gap", "mock-only"].includes(status)) {
    return "warn";
  }
  return "neutral";
}

function renderOfficialGap() {
  const gap = summarizeOfficialAshrGap(
    state.runs,
    state.grades,
    state.coverage,
    state.requestProvenance,
    state.usageQuota,
    state.usageQuotaApiProbe
  );
  $("official-gap-summary").textContent = gap.recommendation;
  $("official-gap-counts").replaceChildren(
    healthTile(String(gap.copied_count), "copied"),
    healthTile(String(gap.partial_count), "partial"),
    healthTile(String(gap.blocked_count), "blocked"),
    healthTile(String(gap.out_of_scope_count), "out of scope")
  );
  $("official-gap-list").replaceChildren(
    ...gap.official_pages.map((page) => gapRow(page))
  );
}

function renderOfficialFrontendMirror() {
  const mirror = summarizeOfficialFrontendMirror(state.frontendMirror);
  $("official-mirror-summary").textContent = mirror.available
    ? `${mirror.page_count} official navigation item(s), ${mirror.api_method_count} API method name(s), ${mirror.confirmed_label_count} UI label(s) summarized from the clean-room mirror.`
    : "No official frontend mirror summary is loaded.";
  $("official-mirror-counts").replaceChildren(
    healthTile(String(mirror.page_count), "pages"),
    healthTile(String(mirror.api_method_count), "api methods"),
    healthTile(String(mirror.copied_count), "copy"),
    healthTile(String(mirror.out_of_scope_count), "do not copy")
  );
  $("official-mirror-pages").replaceChildren(...(
    mirror.pages.length
      ? mirror.pages.map((page) => mirrorPageRow(page))
      : [emptyMatrixRow("No official navigation summary is available.")]
  ));
  $("official-mirror-api").replaceChildren(...(
    mirror.api_method_groups.length
      ? mirror.api_method_groups.map((group) => mirrorApiRow(group))
      : [emptyMatrixRow("No official API method summary is available.")]
  ));
}

function renderOfficialCodeCrawlParity() {
  const crawl = summarizeOfficialCodeCrawlParity(state.frontendCodeCrawl);
  $("official-code-crawl-summary").textContent = crawl.available
    ? `${crawl.recommendation} ${crawl.lab_javascript_chunk_count} lab JS chunk(s), ${crawl.parity_target_count} parity target(s), source committed ${crawl.safety.official_source_committed ? "yes" : "no"}.`
    : "No official code crawl summary is loaded.";
  $("official-code-crawl-counts").replaceChildren(
    healthTile(String(crawl.lab_javascript_chunk_count), "js chunks"),
    healthTile(String(crawl.copy_now_count), "copy now"),
    healthTile(String(crawl.partial_count), "partial"),
    healthTile(String(crawl.out_of_scope_count), "do not copy")
  );
  $("official-code-crawl-chunks").replaceChildren(...(
    crawl.chunks.length
      ? crawl.chunks.map((chunk) => codeCrawlChunkRow(chunk))
      : [emptyMatrixRow("No official code crawl chunks are available.")]
  ));
  $("official-code-crawl-targets").replaceChildren(...(
    crawl.parity_targets.length
      ? crawl.parity_targets.map((target) => codeCrawlTargetRow(target))
      : [emptyMatrixRow("No official code crawl parity targets are available.")]
  ));
}

function codeCrawlChunkRow(chunk) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(chunk.chunk)}</strong>
      <span class="badge ${officialStatusClass(chunk.a3_status)}">${escapeHtml(chunk.a3_status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(chunk.role)}</span>
      <span>${escapeHtml(chunk.signal_count)} signal(s)</span>
      <span>${escapeHtml(chunk.size_bytes)} bytes</span>
    </div>
    <div class="muted">${escapeHtml(chunk.top_signals.map((item) => `${item.signal}:${item.count}`).join(", ") || "no signals")} è·?${escapeHtml(chunk.a3_decision)}</div>
  `;
  return node;
}

function codeCrawlTargetRow(target) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(target.target)}</strong>
      <span class="badge ${officialStatusClass(target.a3_status)}">${escapeHtml(target.a3_status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(target.official_evidence.length)} official chunk(s)</span>
    </div>
    <div class="muted">${escapeHtml(target.a3_dependency)}</div>
  `;
  return node;
}

function officialStatusClass(status) {
  if (status === "copy") {
    return "pass";
  }
  if (status === "partial" || status === "future") {
    return "warn";
  }
  if (status === "out_of_scope") {
    return "neutral";
  }
  return "neutral";
}

function renderOfficialParityRoadmap() {
  const roadmap = summarizeOfficialParityRoadmap(
    state.runs,
    state.grades,
    state.coverage,
    state.requestProvenance,
    state.usageQuota,
    state.usageQuotaApiProbe,
    state.mediaSignedUrlCoverage,
    state.frontendMirror
  );
  $("official-roadmap-summary").textContent = roadmap.available
    ? roadmap.recommendation
    : "No official parity roadmap is available.";
  $("official-roadmap-counts").replaceChildren(
    healthTile(String(roadmap.copied_page_count), "copy now"),
    healthTile(String(roadmap.partial_page_count), "partial"),
    healthTile(String(roadmap.future_page_count), "future"),
    healthTile(String(roadmap.out_of_scope_page_count), "do not copy")
  );
  $("official-roadmap-priorities").replaceChildren(...(
    roadmap.priorities.length
      ? roadmap.priorities.map((item) => roadmapActionRow(item))
      : [emptyMatrixRow("No official parity priorities are available.")]
  ));
  $("official-roadmap-media").replaceChildren(...(
    roadmap.media_actions.length
      ? roadmap.media_actions.map((item) => roadmapActionRow(item))
      : [emptyMatrixRow("No media parity actions are available.")]
  ));
  $("official-roadmap-next").replaceChildren(...(
    roadmap.next_build_order.length
      ? roadmap.next_build_order.map((item, index) => roadmapNextRow(index + 1, item))
      : [emptyMatrixRow("No next build order is available.")]
  ));
}

function roadmapActionRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(item.area)}</strong>
      <span class="badge ${item.action === "do_not_copy" ? "neutral" : item.confirmed ? "info" : "warn"}">${escapeHtml(item.action)}</span>
    </div>
    <div class="muted">${escapeHtml(item.note)}</div>
  `;
  return node;
}

function roadmapNextRow(index, item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Next ${escapeHtml(index)}</strong>
      <span class="badge neutral">roadmap</span>
    </div>
    <div class="muted">${escapeHtml(item)}</div>
  `;
  return node;
}

function gapRow(page) {
  const node = document.createElement("div");
  const statusClass = page.a3_status === "out of scope" || page.a3_status === "not needed"
    ? "neutral"
    : page.a3_status === "partial" || page.a3_status === "known gap"
      ? "warn"
      : "info";
  node.className = "gap-row";
  node.innerHTML = `
    <div class="gap-head">
      <strong>${escapeHtml(page.page)}</strong>
      <span class="badge ${statusClass}">${escapeHtml(page.a3_status)}</span>
    </div>
    <div class="muted">${escapeHtml(page.path)}</div>
    <div class="muted">${escapeHtml(page.mvp_decision)}</div>
  `;
  return node;
}

function mirrorPageRow(page) {
  const node = document.createElement("div");
  node.className = "gap-row";
  node.innerHTML = `
    <div class="gap-head">
      <strong>${escapeHtml(page.label)}</strong>
      <span class="badge ${officialMirrorStatusClass(page.a3_status)}">${escapeHtml(page.a3_status)}</span>
    </div>
    <div class="muted">${escapeHtml(page.tab_id)} / ${escapeHtml(page.chunk)}</div>
    <div class="muted">${escapeHtml(page.a3_decision)}</div>
  `;
  return node;
}

function mirrorApiRow(group) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(group.group)}</strong>
      <span class="badge ${officialMirrorStatusClass(group.a3_status)}">${escapeHtml(group.a3_status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(group.method_count)} method(s)</span>
      <span>${escapeHtml(group.methods.slice(0, 4).join(", ") || "no methods")}${group.methods.length > 4 ? "..." : ""}</span>
    </div>
    <div class="muted">${escapeHtml(group.a3_decision)}</div>
  `;
  return node;
}

function officialMirrorStatusClass(status) {
  if (status === "copy") {
    return "info";
  }
  if (status === "partial" || status === "future") {
    return "warn";
  }
  if (status === "out_of_scope") {
    return "neutral";
  }
  return "neutral";
}

function renderReleaseGate() {
  const gate = summarizeReleaseGate(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage
  );
  const status = $("release-gate-status");
  status.className = `badge ${gate.decision === "approve_release" ? "pass" : gate.decision === "needs_review" ? "warn" : "fail"}`;
  status.textContent = gate.decision_label;
  $("release-gate-summary").textContent = `${gate.summary} ${gate.commercial_value}`;
  $("release-gate-metrics").replaceChildren(
    healthTile(String(gate.risk_score), "risk score"),
    healthTile(String(gate.failed_check_count), "failed checks"),
    healthTile(gate.pr_gate.blocks_merge ? "yes" : "no", "blocks merge"),
    healthTile(gate.required_approvers.length ? String(gate.required_approvers.length) : "0", "approvers")
  );
  $("release-gate-checks").replaceChildren(...(
    gate.checks.length
      ? gate.checks.map((check) => releaseGateCheckRow(check))
      : [emptyMatrixRow("No release gate checks are available.")]
  ));
  $("release-gate-blockers").replaceChildren(...(
    gate.top_risk_cases.length
      ? gate.top_risk_cases.map((item) => warningItem(`${item.case_id}: ${item.primary_failure_class} / ${item.severity} / ${item.score} - ${item.summary}`))
      : [warningItem("No high-risk cases in the loaded evidence package.")]
  ));
}

function releaseGateCheckRow(check) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(check.id)}</strong>
      <span class="badge ${check.passed ? "pass" : "fail"}">${check.passed ? "pass" : "fail"}</span>
    </div>
    <div class="muted">${escapeHtml(check.observed)}</div>
    <div class="muted">${escapeHtml(check.detail)}</div>
  `;
  return node;
}

function renderReleaseWarRoom() {
  const warRoom = summarizeReleaseWarRoom(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage,
    state.requestProvenance,
    state.usageQuota,
    state.usageQuotaApiProbe,
    state.frontendMirror
  );
  const status = $("war-room-status");
  status.className = `badge ${warRoom.decision === "ship_ready" ? "pass" : warRoom.decision === "review_required" ? "warn" : "fail"}`;
  status.textContent = warRoom.decision_label;
  $("war-room-summary").textContent = `${warRoom.customer_value} Current urgency: ${warRoom.urgency}.`;
  $("war-room-metrics").replaceChildren(
    healthTile(String(warRoom.revenue_risk_score), "revenue risk"),
    healthTile(warRoom.blocks_merge ? "yes" : "no", "blocks merge"),
    healthTile(warRoom.waiver_required ? "yes" : "no", "waiver"),
    healthTile(String(warRoom.required_artifact_count), "audit artifacts")
  );
  $("war-room-brief").replaceChildren(...warRoom.executive_brief.slice(0, 4).map((item) => warningItem(item)));
  const notificationChannels = Array.isArray(state.notificationControlPlane?.channels) ? state.notificationControlPlane.channels : [];
  const notificationCaption = document.createElement("div");
  notificationCaption.className = "caption";
  notificationCaption.textContent = `Notification lanes: ${notificationChannels.map((item) => item.provider).join(", ") || "none"}`;
  $("war-room-brief").appendChild(notificationCaption);
  $("war-room-lanes").replaceChildren(...(
    warRoom.lanes.length
      ? warRoom.lanes.map((lane) => warRoomLaneRow(lane))
      : [emptyMatrixRow("No war-room lanes are available.")]
  ));
}

function warRoomLaneRow(lane) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(lane.lane)}</strong>
      <span class="badge ${warRoomStatusClass(lane.status)}">${escapeHtml(lane.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(lane.owner)}</span>
      <span>${escapeHtml(lane.evidence)}</span>
    </div>
    <div class="muted">${escapeHtml(lane.next_action)}</div>
  `;
  return node;
}

function warRoomStatusClass(status) {
  if (["ready", "mapped"].includes(status)) {
    return "pass";
  }
  if (["review", "active", "waiting_for_review", "required"].includes(status)) {
    return "warn";
  }
  if (["blocked", "missing"].includes(status)) {
    return "fail";
  }
  return "neutral";
}

function renderIncidentReplayQueue() {
  const replay = summarizeIncidentReplayQueue(
    state.runs,
    state.grades,
    state.mediaSignedUrlCoverage
  );
  const status = $("incident-replay-status");
  status.className = `badge ${replay.blocker_count > 0 ? "fail" : replay.queue_count > 0 ? "warn" : "pass"}`;
  status.textContent = replay.queue_count > 0 ? `${replay.queue_count} queued` : "clear";
  $("incident-replay-summary").textContent = replay.available
    ? `${replay.commercial_value} ${replay.trace_ready_count} trace-ready, ${replay.tool_diff_ready_count} tool-diff-ready, ${replay.judge_evidence_ready_count} judge-evidence-ready case(s).`
    : "No failed cases require incident replay for the current evidence package.";
  $("incident-replay-metrics").replaceChildren(
    healthTile(String(replay.queue_count), "queued cases"),
    healthTile(String(replay.blocker_count), "release blockers"),
    healthTile(String(replay.trace_ready_count), "trace ready"),
    healthTile(String(replay.judge_evidence_ready_count), "judge evidence")
  );
  $("incident-replay-list").replaceChildren(...(
    replay.queue.length
      ? replay.queue.map((item) => incidentReplayRow(item))
      : [emptyMatrixRow("No incident replay cases are queued.")]
  ));
  $("incident-replay-steps").replaceChildren(...(
    replay.replay_steps.length
      ? replay.replay_steps.map((step, index) => incidentReplayStepRow(index + 1, step))
      : [emptyMatrixRow("No replay steps are available.")]
  ));
}

function incidentReplayRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.case_id)}</strong>
      <span class="badge ${item.release_blocker ? "fail" : "warn"}">${escapeHtml(item.owner_lane)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(item.primary_failure_class)}</span>
      <span>${escapeHtml(item.severity)}</span>
      <span>${escapeHtml(item.score)}</span>
      <span>${escapeHtml(item.tool_diff_count)} diff(s)</span>
      <span>${escapeHtml(item.trace_event_count)} trace</span>
      <span>${escapeHtml(item.judge_evidence_count)} judge</span>
      <span>${escapeHtml(item.media_evidence_count)} media</span>
    </div>
    <div class="muted">${escapeHtml(item.failure_summary)}</div>
  `;
  node.addEventListener("click", () => {
    state.selectedCaseId = item.case_id;
    renderCaseList();
    renderTriageQueue();
    renderPrintReport();
    renderDetail();
  });
  return node;
}

function incidentReplayStepRow(index, step) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Replay ${escapeHtml(index)}</strong>
      <span class="badge neutral">required</span>
    </div>
    <div class="muted">${escapeHtml(step)}</div>
  `;
  return node;
}

function renderObservabilityReplayMatrix() {
  const matrix = summarizeObservabilityReplayMatrix(
    state.runs,
    state.grades,
    state.mediaSignedUrlCoverage,
    state.frontendCodeCrawl
  );
  const status = $("observability-replay-status");
  status.className = `badge ${matrix.blocked_replay_count > 0 ? "fail" : matrix.replay_case_count > 0 ? "warn" : "pass"}`;
  status.textContent = matrix.replay_case_count > 0 ? `${matrix.replay_case_count} replay` : "clear";
  $("observability-replay-summary").textContent = matrix.available
    ? `${matrix.commercial_value} Trace ${matrix.trace_ready_count}, tool/error ${matrix.tool_error_case_count}, judge ${matrix.judge_linked_count}, official Observability ${matrix.official_observability_confirmed ? "mapped" : "unconfirmed"}.`
    : "No failed cases require observability replay for this source.";
  $("observability-replay-metrics").replaceChildren(
    healthTile(String(matrix.replay_case_count), "replay cases"),
    healthTile(String(matrix.trace_ready_count), "trace ready"),
    healthTile(String(matrix.tool_error_case_count), "tool/error"),
    healthTile(String(matrix.judge_linked_count), "judge linked")
  );
  $("observability-replay-lanes").replaceChildren(...(
    matrix.lanes.length
      ? matrix.lanes.map((lane) => observabilityLaneRow(lane))
      : [emptyMatrixRow("No observability replay lanes are available.")]
  ));
  $("observability-replay-items").replaceChildren(...(
    matrix.items.length
      ? matrix.items.map((item) => observabilityReplayItemRow(item))
      : [emptyMatrixRow("No observability replay items are queued.")]
  ));
}

function observabilityLaneRow(lane) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(lane.lane)}</strong>
      <span class="badge ${observabilityStatusClass(lane.status)}">${escapeHtml(lane.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(lane.ready_count)}/${escapeHtml(lane.total_count)} ready</span>
    </div>
    <div class="muted">${escapeHtml(lane.next_action)}</div>
  `;
  return node;
}

function observabilityReplayItemRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.case_id)}</strong>
      <span class="badge ${observabilityStatusClass(item.production_risk)}">${escapeHtml(item.production_risk)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(item.observability_state)}</span>
      <span>${escapeHtml(item.primary_failure_class)}</span>
      <span>trace ${escapeHtml(item.trace_event_count)}</span>
      <span>tool errors ${escapeHtml(item.tool_error_count)}</span>
      <span>judge ${escapeHtml(item.judge_evidence_count)}</span>
      <span>media ${escapeHtml(item.media_evidence_count)}</span>
    </div>
    <div class="muted">${escapeHtml(item.next_action)}</div>
  `;
  node.addEventListener("click", () => {
    state.selectedCaseId = item.case_id;
    renderCaseList();
    renderTriageQueue();
    renderPrintReport();
    renderDetail();
  });
  return node;
}

function observabilityStatusClass(status) {
  if (["ready", "replay_ready", "mapped", "metadata_only"].includes(status)) {
    return "pass";
  }
  if (["needs_replay", "active", "watch", "needs_evidence", "unconfirmed"].includes(status)) {
    return "warn";
  }
  if (["blocker", "blocked_with_evidence"].includes(status)) {
    return "fail";
  }
  return "neutral";
}

function renderRegressionFactory() {
  const factory = summarizeRegressionFactory(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage,
    state.frontendCodeCrawl
  );
  const status = $("regression-factory-status");
  status.className = `badge ${regressionFactoryStatusClass(factory.factory_state)}`;
  status.textContent = factory.factory_state;
  $("regression-factory-summary").textContent = factory.available
    ? `${factory.commercial_value} ${factory.ready_count} ready, ${factory.blocked_count} blocked, ${factory.coverage_gap_count} coverage gap(s), official Results ${factory.official_results_review_confirmed ? "mapped" : "unconfirmed"}.`
    : "No failed cases are available for regression generation.";
  $("regression-factory-metrics").replaceChildren(
    healthTile(String(factory.candidate_count), "candidates"),
    healthTile(String(factory.ready_count), "ready"),
    healthTile(String(factory.blocked_count), "blocked"),
    healthTile(String(factory.coverage_gap_count), "coverage gaps")
  );
  $("regression-factory-lanes").replaceChildren(...(
    factory.lanes.length
      ? factory.lanes.map((lane) => regressionFactoryLaneRow(lane))
      : [emptyMatrixRow("No regression factory lanes are available.")]
  ));
  $("regression-factory-candidates").replaceChildren(...(
    factory.candidates.length
      ? factory.candidates.map((item) => regressionCandidateRow(item))
      : [emptyMatrixRow("No regression candidates are queued.")]
  ));
}

function regressionFactoryLaneRow(lane) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(lane.lane)}</strong>
      <span class="badge ${regressionFactoryStatusClass(lane.status)}">${escapeHtml(lane.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(lane.ready_count)}/${escapeHtml(lane.total_count)} ready</span>
    </div>
    <div class="muted">${escapeHtml(lane.next_action)}</div>
  `;
  return node;
}

function regressionCandidateRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>#${escapeHtml(item.rank)} ${escapeHtml(item.regression_id)}</strong>
      <span class="badge ${regressionFactoryStatusClass(item.generator_state)}">${escapeHtml(item.generator_state)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(item.case_id)}</span>
      <span>${escapeHtml(item.owner_lane)}</span>
      <span>${escapeHtml(item.primary_failure_class)}</span>
      <span>${escapeHtml(item.coverage_status)}</span>
      <span>trace ${escapeHtml(item.trace_event_count)}</span>
      <span>diffs ${escapeHtml(item.tool_diff_count)}</span>
      <span>judge ${escapeHtml(item.judge_evidence_count)}</span>
    </div>
    <div class="muted">${escapeHtml(item.next_action)}</div>
    <div class="case-meta">
      <span>contracts ${escapeHtml(item.required_contracts.join(", ") || "none")}</span>
    </div>
  `;
  node.addEventListener("click", () => {
    state.selectedCaseId = item.case_id;
    renderCaseList();
    renderTriageQueue();
    renderPrintReport();
    renderDetail();
  });
  return node;
}

function regressionFactoryStatusClass(status) {
  if (["ready", "ready_to_promote"].includes(status)) {
    return "pass";
  }
  if (["partial", "needs_evidence", "unknown"].includes(status)) {
    return "warn";
  }
  if (["blocked", "coverage_gap"].includes(status)) {
    return "fail";
  }
  return "neutral";
}

function renderReviewerWorkflowBoard() {
  const board = summarizeReviewerWorkflowBoard(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage
  );
  const status = $("reviewer-workflow-status");
  status.className = `badge ${reviewerWorkflowStatusClass(board.board_state)}`;
  status.textContent = board.board_label;
  $("reviewer-workflow-summary").textContent = board.available
    ? `${board.commercial_value} A1 trace ${board.a1_a2_calibration.a1_trace_ready_count}, A1 tool diffs ${board.a1_a2_calibration.a1_tool_diff_ready_count}, A2 judge evidence ${board.a1_a2_calibration.a2_judge_evidence_ready_count}.`
    : "No reviewer workflow can be built until A1/A2 evidence is loaded.";
  $("reviewer-workflow-metrics").replaceChildren(
    healthTile(String(board.open_item_count), "open items"),
    healthTile(String(board.blocked_item_count), "blocked"),
    healthTile(String(board.needs_evidence_count), "needs evidence"),
    healthTile(String(board.required_reviewer_count), "reviewers")
  );
  $("reviewer-workflow-lanes").replaceChildren(...(
    board.lanes.length
      ? board.lanes.map((lane) => reviewerWorkflowLaneRow(lane))
      : [emptyMatrixRow("No reviewer lanes are available.")]
  ));
  $("reviewer-workflow-items").replaceChildren(...(
    board.items.length
      ? board.items.map((item) => reviewerWorkflowItemRow(item))
      : [emptyMatrixRow("No reviewer workflow items are open.")]
  ));
  renderReviewWorkflowRecords();
}

function renderReviewWorkflowRecords() {
  const workflow = state.reviewWorkflow || {};
  const records = Array.isArray(workflow.records) ? workflow.records : [];
  const filteredRecords = applyReviewWorkflowFilters(records, state.reviewFilter || {});
  const reportCenter = state.reportCenter || {};
  const shareableCount = reportCenter.summary?.shareable_count || 0;
  const revokedCount = reportCenter.summary?.revoked_count || 0;
  const manifestReadyCount = reportCenter.summary?.manifest_ready_count || 0;
  const block = $("review-workflow-records");
  if (!block) {
    return;
  }
  const recordRows = records.length
    ? records.slice(-4).reverse().map((record) => reviewWorkflowRecordRow(record))
    : [emptyMatrixRow("No durable waiver or approval records have been submitted through the A3 API yet.")];
  block.replaceChildren(
    matrixKicker("Durable Review Records"),
    miniRow("Records", String(filteredRecords.length || workflow.record_count || records.length || 0)),
    miniRow("Waivers", String(workflow.waiver_count || 0)),
    miniRow("Approvals", String(workflow.approval_count || 0)),
    miniRow("Denials", String(workflow.denial_count || 0)),
    miniRow("Accepted", String(workflow.accepted_count || 0)),
    miniRow("Storage", workflow.durable_storage_ready ? "durable-ready" : "not durable"),
    miniRow("Shareable", `${shareableCount} ready / ${revokedCount} revoked`),
    miniRow("Manifest-ready", String(manifestReadyCount || 0)),
    reviewWorkflowActionBar(),
    reviewWorkflowReceiptRow(),
    reviewWorkflowScopeRow(workflow),
    reviewWorkflowFilterRow(workflow),
    reviewWorkflowFilterScopeRow(filteredRecords, state.reviewFilter || {}),
    reviewWorkflowTrendRow(workflow),
    reviewWorkflowShareReadinessRow(workflow, reportCenter),
    ...recordRows
  );
}

function reviewWorkflowActionBar() {
  const node = document.createElement("div");
  node.className = "action-row review-action-row";
  node.innerHTML = `
    <button class="button subtle" type="button" data-review-action="waiver">Record Waiver</button>
    <button class="button subtle" type="button" data-review-action="approval">Record Approval</button>
    <button class="button subtle" type="button" data-review-action="denial">Record Denial</button>
  `;
  for (const button of node.querySelectorAll("[data-review-action]")) {
    button.addEventListener("click", () => submitReviewWorkflowAction(button.dataset.reviewAction));
  }
  return node;
}

function reviewWorkflowFilterRow(workflow = {}) {
  const options = workflow.filter_options || {};
  const defaults = options.default_scope || {};
  const current = state.reviewFilter || {};
  const node = document.createElement("div");
  node.className = "matrix-row";
  const releaseOptions = ['<option value="">all releases</option>'].concat((options.release_versions || []).map((value) => `<option value="${escapeHtml(value)}" ${current.releaseVersion === value ? "selected" : ""}>${escapeHtml(value)}</option>`)).join("");
  const environmentOptions = ['<option value="">all environments</option>'].concat((options.environments || []).map((value) => `<option value="${escapeHtml(value)}" ${current.environment === value ? "selected" : ""}>${escapeHtml(value)}</option>`)).join("");
  const actorOptions = ['<option value="">all actors</option>'].concat((options.actor_hashes || []).map((value) => `<option value="${escapeHtml(value)}" ${current.actorHash === value ? "selected" : ""}>${escapeHtml(shortHash(value))}</option>`)).join("");
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Review Filters</strong>
      <span class="badge info">interactive</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml((options.release_versions || []).length)} release option(s)</span>
      <span>${escapeHtml((options.environments || []).length)} environment option(s)</span>
      <span>${escapeHtml((options.actor_hashes || []).length)} actor hash option(s)</span>
    </div>
    <div class="inline-select-grid">
      <select data-review-filter="releaseVersion">${releaseOptions}</select>
      <select data-review-filter="environment">${environmentOptions}</select>
      <select data-review-filter="actorHash">${actorOptions}</select>
    </div>
    <div class="muted">Default scope ${escapeHtml(defaults.release_version || "unknown")} / ${escapeHtml(defaults.environment || "unknown")} / ${escapeHtml(shortHash(defaults.actor_hash || "none"))}.</div>
  `;
  for (const select of node.querySelectorAll("[data-review-filter]")) {
    select.addEventListener("change", () => {
      state.reviewFilter[select.dataset.reviewFilter] = select.value;
      console.log("review-filter-change", select.dataset.reviewFilter, select.value, JSON.stringify(state.reviewFilter));
      syncReviewFilterQuery();
      console.log("review-filter-url", window.location.href);
      renderReviewWorkflowRecords();
    });
  }
  return node;
}
function reviewWorkflowFilterScopeRow(filteredRecords = [], filter = {}) {
  const active = [
    filter.releaseVersion ? `release ${filter.releaseVersion}` : null,
    filter.environment ? `env ${filter.environment}` : null,
    filter.actorHash ? `actor ${shortHash(filter.actorHash)}` : null
  ].filter(Boolean);
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Active Filter Scope</strong>
      <span class="badge ${active.length ? "info" : "neutral"}">${active.length ? "filtered" : "all"}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(filteredRecords.length)} visible record(s)</span>
      <span>${escapeHtml(active.length)} active scope(s)</span>
    </div>
    <div class="muted">${escapeHtml(active.join(", ") || "Showing all durable review records.")}</div>
  `;
  return node;
}

function reviewWorkflowTrendRow(workflow = {}) {
  const trends = workflow.decision_trends || {};
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Decision Trends</strong>
      <span class="badge ${(Number(trends.denials || 0) > 0) ? "warn" : "pass"}">${(Number(trends.denials || 0) > 0) ? "watch" : "stable"}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(trends.approvals || 0)} approval(s)</span>
      <span>${escapeHtml(trends.waivers || 0)} waiver(s)</span>
      <span>${escapeHtml(trends.denials || 0)} denial(s)</span>
      <span>${escapeHtml(trends.latest_release_version || "unknown")}</span>
    </div>
    <div class="muted">Latest environment ${escapeHtml(trends.latest_environment || "unknown")}; releases ${(trends.release_breakdown || []).map((item) => `${item.label}:${item.count}`).join(", ") || "none"}.</div>
  `;
  return node;
}

function reviewWorkflowScopeRow(workflow = {}) {
  const scope = workflow.scope_summary || {};
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Review Scope Summary</strong>
      <span class="badge info">scoped</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(scope.release_count || 0)} release(s)</span>
      <span>${escapeHtml(scope.environment_count || 0)} environment(s)</span>
      <span>${escapeHtml(scope.actor_role_count || 0)} role(s)</span>
      <span>${escapeHtml(scope.actor_hash_count || 0)} actor hash(es)</span>
    </div>
    <div class="muted">Latest ${escapeHtml(scope.latest_release_version || "unknown")} / ${escapeHtml(scope.latest_environment || "unknown")}; roles ${escapeHtml((scope.actor_roles || []).join(", ") || "unknown")}.</div>
  `;
  return node;
}

function reviewWorkflowShareReadinessRow(workflow = {}, reportCenter = {}) {
  const summary = reportCenter.summary || {};
  const approvals = Number(workflow.approval_count || 0);
  const accepted = Number(workflow.accepted_count || 0);
  const shareable = Number(summary.shareable_count || 0);
  const manifestReady = Number(summary.manifest_ready_count || 0);
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Report Share Readiness</strong>
      <span class="badge ${accepted > 0 || shareable > 0 ? "pass" : "warn"}">${accepted > 0 || shareable > 0 ? "linked" : "waiting"}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(approvals)} approval(s)</span>
      <span>${escapeHtml(accepted)} accepted record(s)</span>
      <span>${escapeHtml(shareable)} shareable report(s)</span>
      <span>${escapeHtml(manifestReady)} manifest-ready</span>
    </div>
    <div class="muted">Reviewer actions, hosted reports, and export evidence should converge before external sharing or release sign-off.</div>
  `;
  return node;
}

function reviewWorkflowReceiptRow() {
  const receipt = state.selectedReviewReceipt || {};
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = receipt.schema_version
    ? `
      <div class="matrix-head">
        <strong>${escapeHtml(receipt.record_type || "review")}</strong>
        <span class="badge ${receipt.accepted ? "pass" : "warn"}">${escapeHtml(receipt.status || "unknown")}</span>
      </div>
      <div class="case-meta">
        <span>${escapeHtml(receipt.record_id || "no record")}</span>
        <span>${escapeHtml(receipt.event_envelope?.event_type || "no event")}</span>
        <span>${receipt.real_cloud_mutation_performed ? "real write" : "no real cloud write"}</span>
      </div>
      <div class="muted">payload ${escapeHtml(shortHash(receipt.payload_hash))} / review ${escapeHtml(shortHash(receipt.review_hash))}</div>
    `
    : `<div class="muted">Use Record Waiver / Approval / Denial in API-backed mode to create a durable human review record.</div>`;
  return node;
}

function matrixKicker(label) {
  const node = document.createElement("div");
  node.className = "section-kicker";
  node.textContent = label;
  return node;
}

function syncReviewFilterQuery() {
  const params = new URLSearchParams(window.location.search);
  if (state.reviewFilter.releaseVersion) {
    params.set("reviewRelease", state.reviewFilter.releaseVersion);
  } else {
    params.delete("reviewRelease");
  }
  if (state.reviewFilter.environment) {
    params.set("reviewEnv", state.reviewFilter.environment);
  } else {
    params.delete("reviewEnv");
  }
  if (state.reviewFilter.actorHash) {
    params.set("reviewActor", state.reviewFilter.actorHash);
  } else {
    params.delete("reviewActor");
  }
  const next = `${window.location.pathname}?${params.toString()}${window.location.hash || ""}`.replace(/\?($|#)/, "$1");
  console.log("syncReviewFilterQuery", next);
  window.history.replaceState({}, "", next);
}

function applyReviewWorkflowFilters(records = [], filter = {}) {
  return records.filter((record) => {
    if (filter.releaseVersion && record.release_version !== filter.releaseVersion) {
      return false;
    }
    if (filter.environment && record.environment !== filter.environment) {
      return false;
    }
    if (filter.actorHash && record.payload_hash !== filter.actorHash && record.review_hash !== filter.actorHash) {
      return false;
    }
    return true;
  });
}

function reviewWorkflowRecordRow(record) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(record.record_type || "record")}</strong>
      <span class="badge ${record.accepted ? "pass" : "warn"}">${escapeHtml(record.status || "unknown")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(record.record_id)}</span>
      <span>${escapeHtml(record.run_id || "no run")}</span>
      <span>${escapeHtml(record.signature?.status || "hash sealed")}</span>
    </div>
    <div class="muted">${escapeHtml(record.subject?.decision || record.subject?.follow_up_issue || record.release_version || "")}</div>
  `;
  return node;
}

function reviewerWorkflowLaneRow(lane) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(lane.lane)}</strong>
      <span class="badge ${reviewerWorkflowStatusClass(lane.status)}">${escapeHtml(lane.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(lane.item_count)} item(s)</span>
      <span>${escapeHtml(lane.blocked_count)} blocked</span>
      <span>${escapeHtml(lane.missing_evidence_count)} missing evidence</span>
      <span>${escapeHtml(lane.approval_ready_count)} approval-ready</span>
    </div>
    <div class="muted">${escapeHtml(lane.next_action)}</div>
  `;
  return node;
}

function reviewerWorkflowItemRow(item) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(item.case_id)}</strong>
      <span class="badge ${reviewerWorkflowStatusClass(item.review_state)}">${escapeHtml(item.review_state)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(item.owner_lane)}</span>
      <span>${escapeHtml(item.primary_failure_class)}</span>
      <span>${escapeHtml(item.severity)}</span>
      <span>${escapeHtml(item.score)}</span>
      <span>trace ${escapeHtml(item.evidence_counts.trace_events)}</span>
      <span>diffs ${escapeHtml(item.evidence_counts.tool_diffs)}</span>
      <span>judge ${escapeHtml(item.evidence_counts.judge_evidence)}</span>
    </div>
    <div class="muted">Missing: ${escapeHtml(item.missing_artifacts.join(", ") || "none")} è·?${escapeHtml(item.next_action)}</div>
  `;
  node.addEventListener("click", () => {
    state.selectedCaseId = item.case_id;
    renderCaseList();
    renderTriageQueue();
    renderPrintReport();
    renderDetail();
  });
  return node;
}

function reviewerWorkflowStatusClass(status) {
  if (["ready", "approval_ready", "standby"].includes(status)) {
    return "pass";
  }
  if (["needs_review", "needs_owner_review", "needs_evidence", "waiver_allowed"].includes(status)) {
    return "warn";
  }
  if (["blocked", "waiver_blocked", "executive_exception_required"].includes(status)) {
    return "fail";
  }
  return "neutral";
}

function renderReleaseWorkflow() {
  const workflow = summarizeReleaseWorkflow(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage
  );
  const status = $("pr-gate-status");
  status.className = `badge ${workflow.github_check.conclusion === "success" ? "pass" : workflow.github_check.conclusion === "neutral" ? "warn" : "fail"}`;
  status.textContent = workflow.github_check.conclusion;
  $("pr-gate-summary").textContent = `${workflow.github_check.output.summary} ${workflow.commercial_value}`;
  $("pr-gate-metrics").replaceChildren(
    healthTile(workflow.github_check.blocks_merge ? "yes" : "no", "blocks merge"),
    healthTile(workflow.waiver_policy.required ? "yes" : "no", "waiver required"),
    healthTile(workflow.waiver_policy.expiry_max_days ? `${workflow.waiver_policy.expiry_max_days}d` : "none", "waiver max"),
    healthTile(String(workflow.incident_replay.case_ids.length), "replay cases")
  );
  $("pr-gate-review").replaceChildren(
    miniRow("Check name", workflow.github_check.name),
    miniRow("Release", workflow.release_version),
    miniRow("Environment", workflow.environment),
    miniRow("Review state", workflow.reviewer_workflow.state),
    miniRow("Review lanes", workflow.reviewer_workflow.review_lanes.join(", ") || "none"),
    miniRow("Waiver policy", workflow.waiver_policy.guidance)
  );
  $("audit-bundle-list").replaceChildren(...workflow.audit_bundle.artifacts.map((artifact) => auditArtifactRow(artifact)));
}

function auditArtifactRow(artifact) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(artifact.id)}</strong>
      <span class="badge ${artifact.required ? "info" : "neutral"}">${artifact.required ? "required" : "optional"}</span>
    </div>
    <div class="muted">${escapeHtml(artifact.path)}</div>
    <div class="muted">${escapeHtml(artifact.purpose)}</div>
  `;
  return node;
}

function releaseEvidenceStatusClass(summary) {
  if (!summary.available) {
    return "warn";
  }
  if (summary.overall_status === "verified") {
    return "pass";
  }
  if (summary.overall_status === "planned" || summary.overall_status === "partial") {
    return "warn";
  }
  return "fail";
}

function renderReleaseEvidenceSummary() {
  const releaseEvidence = summarizeReleaseEvidenceSummary(state.releaseEvidence);
  const status = $("release-evidence-status");
  status.className = `badge ${releaseEvidenceStatusClass(releaseEvidence)}`;
  status.textContent = releaseEvidence.overall_status;
  $("release-evidence-summary").textContent = releaseEvidence.available
    ? `${releaseEvidence.commercial_value} Safety: tokens ${releaseEvidence.safety.token_included ? "included" : "not included"}, real GitHub mutation ${releaseEvidence.safety.real_github_mutation_performed ? "yes" : "no"}.`
    : releaseEvidence.recommendation;
  $("release-evidence-metrics").replaceChildren(
    healthTile(String(releaseEvidence.available_surface_count), "evidence surfaces"),
    healthTile(releaseEvidence.github_check_publish.dry_run ? "dry-run" : releaseEvidence.github_check_publish.posted ? "posted" : "missing", "GitHub check"),
    healthTile(String(releaseEvidence.readback_record_count || 0), "readbacks"),
    healthTile(releaseEvidence.audit_bundle_verification.root_hash_passed ? "pass" : "missing", "bundle hash"),
    healthTile(releaseEvidence.audit_archive_verification.signature_passed ? "pass" : "missing", "archive signature")
  );
  $("release-evidence-github").replaceChildren(
    releaseEvidenceRow("Check run", `${releaseEvidence.github_check_publish.status} / ${releaseEvidence.github_check_publish.check_name}`, `${releaseEvidence.github_check_publish.repo}; dry-run ${releaseEvidence.github_check_publish.dry_run ? "yes" : "no"}; posted ${releaseEvidence.github_check_publish.posted ? "yes" : "no"}`),
    releaseEvidenceRow("PR comment", `${releaseEvidence.github_pr_comment_publish.status} / PR ${releaseEvidence.github_pr_comment_publish.pull_number || "unknown"}`, `${releaseEvidence.github_pr_comment_publish.repo}; dry-run ${releaseEvidence.github_pr_comment_publish.dry_run ? "yes" : "no"}; posted ${releaseEvidence.github_pr_comment_publish.posted ? "yes" : "no"}`),
    releaseEvidenceRow("Required check", `${releaseEvidence.github_required_check_plan.status} / ${releaseEvidence.github_required_check_plan.check_name}`, `${releaseEvidence.github_required_check_plan.repo}@${releaseEvidence.github_required_check_plan.branch}; maintainer approval ${releaseEvidence.github_required_check_plan.maintainer_approval_required ? "required" : "not required"}`),
    releaseEvidenceRow("Check readback", `${releaseEvidence.github_check_readback.readback_status} / ${releaseEvidence.github_check_readback.check_name}`, `confirmed ${releaseEvidence.github_check_readback.readback_confirmed ? "yes" : "no"}; head SHA match ${releaseEvidence.github_check_readback.head_sha_match === null ? "unknown" : releaseEvidence.github_check_readback.head_sha_match ? "yes" : "no"}; hash ${shortHash(releaseEvidence.github_check_readback.payload_hash)}`),
    releaseEvidenceRow("PR comment readback", `${releaseEvidence.pr_comment_readback.readback_status} / PR ${releaseEvidence.pr_comment_readback.pull_number || "unknown"}`, `marker ${releaseEvidence.pr_comment_readback.marker_match === null ? "unknown" : releaseEvidence.pr_comment_readback.marker_match ? "match" : "mismatch"}; body hash ${releaseEvidence.pr_comment_readback.body_hash_match === null ? "unknown" : releaseEvidence.pr_comment_readback.body_hash_match ? "match" : "mismatch"}; hash ${shortHash(releaseEvidence.pr_comment_readback.payload_hash)}`),
    releaseEvidenceRow("Required-check readback", `${releaseEvidence.required_check_proof.readback_status} / enforced ${releaseEvidence.required_check_proof.enforced ? "yes" : "no"}`, `plan-only guard ${releaseEvidence.required_check_proof.plan_only_must_not_claim_enforcement ? "on" : "off"}; checked ${releaseEvidence.required_check_proof.checked_count || 0}; hash ${shortHash(releaseEvidence.required_check_proof.payload_hash)}`)
  );
  $("release-evidence-verification").replaceChildren(
    releaseEvidenceRow("Readback history", `${releaseEvidence.readback_record_count || 0} record(s)`, `confirmed ${releaseEvidence.readback_status_counts?.readback_confirmed || 0}, stale ${releaseEvidence.readback_status_counts?.stale || 0}, missing ${releaseEvidence.readback_status_counts?.missing || 0}. ${releaseEvidence.readback_history?.a1_a2_boundary || "Readback does not replace A1/A2 evidence."}`),
    releaseEvidenceRow("Audit bundle", `${releaseEvidence.audit_bundle_verification.status} / hash ${releaseEvidence.audit_bundle_verification.root_hash_passed ? "pass" : "missing"}`, `${releaseEvidence.audit_bundle_verification.artifact_passed}/${releaseEvidence.audit_bundle_verification.artifact_total} artifacts, ${releaseEvidence.audit_bundle_verification.custody_passed}/${releaseEvidence.audit_bundle_verification.custody_total} custody events, root ${releaseEvidence.audit_bundle_verification.root_hash_prefix || "n/a"}`),
    releaseEvidenceRow("Audit archive", `${releaseEvidence.audit_archive_verification.status} / signature ${releaseEvidence.audit_archive_verification.signature_passed ? "pass" : "missing"}`, `${releaseEvidence.audit_archive_verification.entry_passed}/${releaseEvidence.audit_archive_verification.entry_total} entries, ${releaseEvidence.audit_archive_verification.signature_algorithm}, root ${releaseEvidence.audit_archive_verification.root_hash_prefix || "n/a"}`),
    releaseEvidenceRow("Safety", releaseEvidence.safety.dry_run_only ? "dry-run only" : "live mutation seen", `secret values ${releaseEvidence.safety.contains_secret_values || releaseEvidence.safety.secret_values_allowed ? "present/allowed" : "blocked"}, raw private key ${releaseEvidence.safety.raw_private_key_stored ? "stored" : "not stored"}`)
  );
}

function shortHash(value) {
  return typeof value === "string" && value.length ? value.slice(0, 12) : "missing";
}

function releaseEvidenceRow(title, value, detail) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(title)}</strong>
      <span class="badge neutral">${escapeHtml(value)}</span>
    </div>
    <div class="muted">${escapeHtml(detail)}</div>
  `;
  return node;
}

function renderRequestProvenance() {
  const provenance = summarizeRequestProvenance(state.requestProvenance);
  const statusBadge = $("request-status");
  if (!provenance.available) {
    statusBadge.className = "badge warn";
    statusBadge.textContent = "not wired";
    $("request-summary").textContent = "No Ashr request sample is loaded for this data source. Mock fixtures start after request generation.";
    $("request-provenance").replaceChildren(
      miniRow("Source", "none"),
      miniRow("Status", "unknown"),
      miniRow("Inputs", "unknown"),
      miniRow("Outputs", "unknown")
    );
    return;
  }

  const latest = provenance.latest_request;
  statusBadge.className = latest.request_status === "completed" ? "badge pass" : latest.request_status === "failed" ? "badge fail" : "badge neutral";
  statusBadge.textContent = latest.request_status;
  $("request-summary").textContent = `${provenance.total_requests} request sample(s); latest ${latest.request_name} ran ${latest.actual_duration_s ?? "?"}s actual / ${latest.estimated_duration_s ?? "?"}s estimated.`;
  $("request-provenance").replaceChildren(
    miniRow("Accepted inputs", latest.accepted_input_types.join(", ") || "none"),
    miniRow("Generation", latest.generation_outputs.join(", ") || "none"),
    miniRow("Tools", String(latest.tool_count)),
    miniRow("Strategy", latest.test_strategy),
    miniRow("Failure noted", latest.has_failure ? "yes" : "no")
  );
}

function miniRow(label, value) {
  const node = document.createElement("div");
  node.className = "mini-row";
  node.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return node;
}

function sourceLabel(source) {
  if (source === "api-mock") {
    return "API-backed A1/A2 mock fixture";
  }
  if (source === "raw-a1") {
    return "Raw A1 RunResult fixture";
  }
  if (source === "raw-a2") {
    return "Raw A2 single-case fixture";
  }
  if (source === "p3-media") {
    return "P3 redacted Ashr media sample";
  }
  if (source === "p3-official-demo") {
    return "P3 official Ashr demo dataset 884 / run 11926";
  }
  return "Local A1/A2 mock fixture";
}

function workflowRequestLabel(source) {
  if (source === "raw-a1") {
    return "A1 raw run";
  }
  if (source === "raw-a2") {
    return "A2 raw case";
  }
  if (source === "p3-official-demo") {
    return "official run";
  }
  return source === "p3-media" ? "API sample" : "mock seed";
}

function workflowRequestDetail(source) {
  if (source === "raw-a1") {
    return "raw run result";
  }
  if (source === "raw-a2") {
    return "single run + grade";
  }
  if (source === "p3-official-demo") {
    return "official dataset/run";
  }
  return source === "p3-media" ? "sampled read-only" : "mock only";
}

function renderCoverageHealth() {
  const coverage = summarizeCoverage(state.coverage);
  if (!coverage.available) {
    $("coverage-status").className = "badge warn";
    $("coverage-status").textContent = "missing";
    $("coverage-summary").textContent = "No A2 coverage fixture is available. Dashboard still works, but report coverage evidence is incomplete.";
    $("coverage-grid").replaceChildren(
      healthTile("0", "scenarios"),
      healthTile("0", "executable cases"),
      healthTile("0", "rubric classes"),
      healthTile("unknown", "assignment minimums")
    );
    $("coverage-warnings").replaceChildren();
    return;
  }

  const dimensionTotal = Object.keys(coverage.scenario_dimension_checks).length;
  const dimensionMet = Object.values(coverage.scenario_dimension_checks).filter(Boolean).length;
  const warnings = [
    ...coverage.scenario_quality_warnings,
    ...coverage.coverage_warnings
  ];
  $("coverage-status").className = `badge ${coverage.meets_assignment_minimums && warnings.length === 0 ? "pass" : "warn"}`;
  $("coverage-status").textContent = coverage.meets_assignment_minimums ? "healthy" : "needs review";
  $("coverage-summary").textContent = `${coverage.pack_id} has ${coverage.scenario_count} scenarios. Dimensions met: ${dimensionMet}/${dimensionTotal}.`;
  $("coverage-grid").replaceChildren(
    healthTile(String(coverage.scenario_count), "scenarios"),
    healthTile(String(coverage.executable_run_case_count), "executable cases"),
    healthTile(String(coverage.rubric_class_count), "rubric classes"),
    healthTile(String(coverage.primary_failure_class_count), "failure classes")
  );
  $("coverage-warnings").replaceChildren(...(
    warnings.length
      ? warnings.slice(0, 3).map((warning) => warningItem(warning))
      : [warningItem("No coverage warnings in the loaded fixture.")]
  ));
}

function healthTile(value, label) {
  const node = document.createElement("div");
  node.className = "health-tile";
  node.innerHTML = `<strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span>`;
  return node;
}

function warningItem(message) {
  const node = document.createElement("div");
  node.className = "warning-item";
  node.textContent = message;
  return node;
}

function renderTriageQueue() {
  const failedCases = state.filteredCases
    .filter((item) => !item.passed)
    .sort((left, right) => triageWeight(right) - triageWeight(left) || left.score - right.score)
    .slice(0, 5);

  if (!failedCases.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No failed cases in the current filter. This is the happy path.";
    $("triage-queue").replaceChildren(empty);
    return;
  }

  $("triage-queue").replaceChildren(...failedCases.map((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `triage-row ${item.case_id === state.selectedCaseId ? "active" : ""}`;
    row.addEventListener("click", () => {
      state.selectedCaseId = item.case_id;
      renderCaseList();
      renderTriageQueue();
      renderPrintReport();
      renderDetail();
    });
    row.innerHTML = `
      <div class="triage-head">
        <span class="triage-title">${escapeHtml(item.title)}</span>
        <span class="badge fail">${escapeHtml(String(item.score))}</span>
      </div>
      <div class="case-meta">
        <span>${escapeHtml(item.case_id)}</span>
        <span>${escapeHtml(item.primary_failure_class)}</span>
        <span>${escapeHtml(item.severity)}</span>
      </div>
      <div class="muted">${escapeHtml(item.failure_summary)}</div>
    `;
    return row;
  }));
}

function triageWeight(item) {
  const severityWeight = {
    critical: 4,
    blocker: 4,
    high: 3,
    major: 3,
    medium: 2,
    minor: 1,
    low: 1,
    none: 0
  };
  return (severityWeight[item.severity] || 0) * 1000 + (100 - Number(item.score || 0));
}

function renderReportCenter() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  const coverage = summarizeCoverage(state.coverage);
  const requestProvenance = summarizeRequestProvenance(state.requestProvenance);
  const usageQuota = summarizeUsageQuota(state.usageQuota, state.usageQuotaApiProbe);
  const mediaReadiness = summarizeMediaReadiness(state.runs, state.grades, state.usageQuota, state.mediaSignedUrlCoverage);
  const cloudShell = summarizeCloudConsoleShell(state.authCheck, state.frontendSummary, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe);
  const productConsole = summarizeProductConsoleExport(state.productConsole);
  const saasAdmin = summarizeSaasAdminExport(state.saasAdmin);
  const officialParityRoadmap = summarizeOfficialParityRoadmap(state.runs, state.grades, state.coverage, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe, state.mediaSignedUrlCoverage, state.frontendMirror);
  const officialCodeCrawl = summarizeOfficialCodeCrawlParity(state.frontendCodeCrawl);
  const peerBranchCalibration = summarizeA3PeerBranchCalibration(state.peerBranchCalibration);
  const liveWorkflowReadiness = state.liveWorkflowReadiness || {};
  const liveOpsControlPlane = state.liveOpsControlPlane || {};
  const notificationControlPlane = state.notificationControlPlane || {};
  const reviewWorkflow = state.reviewWorkflow || {};
  const billingMigrationReadiness = state.billingMigrationReadiness || {};
  const incidentReplay = summarizeIncidentReplayQueue(state.runs, state.grades, state.mediaSignedUrlCoverage);
  const observabilityReplay = summarizeObservabilityReplayMatrix(state.runs, state.grades, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const regressionFactory = summarizeRegressionFactory(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const exportRedactionFirewall = summarizeExportRedactionFirewall(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const reviewerWorkflowBoard = summarizeReviewerWorkflowBoard(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseGate = summarizeReleaseGate(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseWorkflow = summarizeReleaseWorkflow(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseWarRoom = summarizeReleaseWarRoom(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe, state.frontendMirror);
  const releaseEvidence = summarizeReleaseEvidenceSummary(state.releaseEvidence);
  const reportCenter = state.reportCenter || {};
  const artifactRegistry = state.artifactRegistry || reportCenter.artifact_registry || {};
  const hostedReports = Array.isArray(reportCenter.reports) ? reportCenter.reports : [];
  const commercialLoopSummary = buildReportCommercialLoopSummary({ reportCenter, reviewWorkflow, notificationControlPlane, liveOpsControlPlane });
  const audienceFilterSummary = buildAudienceFilterSummary(reportCenter.audience_filters || {});
  const workspaceGroupSummary = buildGroupedScopeSummary(reportCenter.workspace_groups || {}, "workspace");
  const environmentGroupSummary = buildGroupedScopeSummary(reportCenter.environment_groups || {}, "environment");
  const externalPublishBlockerSummary = buildExternalPublishBlockerSummary(reportCenter.external_publish_blockers || {});
  $("report-status").className = "badge info";
  $("report-status").textContent = hostedReports.length ? `${hostedReports.length} hosted` : `${summary.totalCases} cases`;
  $("report-summary").textContent = `Current exports package ${summary.totalCases} normalized case(s), ${summary.failed} failure(s), ${summary.mediaEvidenceCases} media evidence case(s), ${releaseGate.decision_label} release gate, ${releaseWorkflow.github_check.name} ${releaseWorkflow.github_check.conclusion} check, ${releaseWarRoom.decision_label} war room, ${releaseEvidence.available ? `${releaseEvidence.overall_status} release evidence with ${releaseEvidence.readback_record_count || 0} readback record(s)` : "no release evidence"}, ${liveWorkflowReadiness.schema_version ? `${liveWorkflowReadiness.ready_capability_count || 0} live-workflow ready capability(s)` : "no live workflow readiness"}, ${notificationControlPlane.schema_version ? `${notificationControlPlane.summary?.channel_count || 0} notification channel(s)` : "no notification control plane"}, ${incidentReplay.queue_count} incident replay case(s), ${observabilityReplay.replay_case_count} observability replay case(s), ${regressionFactory.candidate_count} regression candidate(s), ${exportRedactionFirewall.status} export firewall, ${reviewerWorkflowBoard.board_label} reviewer workflow, ${productConsole.available ? `${productConsole.onboarding.completion_rate}% onboarding / ${productConsole.audit_log.event_count} audit event(s)` : "no product console workflow"}, ${saasAdmin.available ? `${saasAdmin.team.member_count} SaaS admin member(s) / ${saasAdmin.api_keys.key_count} API-key metadata row(s)` : "no SaaS admin export"}, ${hostedReports.length} hosted report(s), ${reportCenter.summary?.manifest_ready_count || 0} manifest-ready report(s), ${artifactRegistry.summary?.artifact_count || 0} registry artifact(s), ${peerBranchCalibration.available ? `${peerBranchCalibration.peer_delta_count} peer branch delta(s)` : "no peer branch calibration"}, ${officialCodeCrawl.available ? "official code crawl parity" : "no official code crawl parity"}, ${officialParityRoadmap.available ? "official parity roadmap" : "no official parity roadmap"}, ${coverage.available ? "A2 coverage" : "no coverage fixture"}, ${requestProvenance.available ? "request provenance" : "no request provenance"}, ${usageQuota.available ? "usage/quota calibration" : "no usage/quota calibration"}, ${mediaReadiness.available ? "media readiness" : "no media readiness"}, and ${cloudShell.available ? "cloud shell safety map" : "no cloud shell evidence"}.`;
  const tiles = [
    reportTile("JSON", "Full machine-readable payload with release gate, war room, incident replay queue, observability replay matrix, regression factory, export redaction firewall, reviewer workflow board, product console workflow, SaaS admin guardrails, PR workflow, official code crawl parity, official parity roadmap, cases, tool-call diffs, media readiness, cloud shell safety, coverage, request provenance, and usage/quota evidence."),
    reportTile("CSV", "Spreadsheet-friendly triage list for sorting by score, severity, and failure class, with cell-level secret scrubbing and formula hardening."),
    reportTile("Markdown", "Human-readable release-gate and war-room report with product console onboarding/audit state, SaaS admin guardrails, incident replay queue, observability replay matrix, regression factory, reviewer workflow board, official code crawl parity, official parity roadmap, PR comment template, waiver guidance, media policy, cloud boundaries, worklogs, and group updates."),
    reportTile("Print/PDF", "Browser-printable executive sign-off report with metrics, release gate, war room, incident replay, observability replay, regression factory, reviewer workflow, official code crawl parity, parity roadmap, media readiness, cloud safety, failures, and selected case evidence."),
    reportTile("Commercial Loop", commercialLoopSummary),
    reportTile("Release Sign-Off", buildReleaseSignoffTile(reportCenter))
  ];
    if (releaseEvidence.available) {
      tiles.push(reportTile("Release Evidence", `${releaseEvidence.overall_status}: check ${releaseEvidence.github_check_publish.status}, PR comment ${releaseEvidence.github_pr_comment_publish.status}, bundle ${releaseEvidence.audit_bundle_verification.status}, archive ${releaseEvidence.audit_archive_verification.status}, readbacks ${releaseEvidence.readback_record_count || 0} (${releaseEvidence.readback_status_counts?.readback_confirmed || 0} confirmed).`));
    }
    if (peerBranchCalibration.available) {
      tiles.push(reportTile("Peer Branch Calibration", `${peerBranchCalibration.status}: ${peerBranchCalibration.peer_delta_count} A1/A2 peer delta(s), ${peerBranchCalibration.blocking_delta_count} blocking, ${peerBranchCalibration.growth_point_count} growth point(s).`));
    }
    if (liveWorkflowReadiness.schema_version) {
      tiles.push(reportTile("Live Workflow Readiness", `${liveWorkflowReadiness.status}: ${liveWorkflowReadiness.ready_capability_count || 0}/${liveWorkflowReadiness.capability_count || 0} ready, ${liveWorkflowReadiness.human_action_count || 0} human record(s), ${liveWorkflowReadiness.needs_backend_or_credentials_count || 0} need live backend/credentials.`));
    }
    if (liveOpsControlPlane.schema_version) {
      tiles.push(reportTile("Live Ops Control Plane", `${liveOpsControlPlane.status}: ${liveOpsControlPlane.counts?.api_backed_count || 0}/${liveOpsControlPlane.counts?.lane_count || 0} API-backed lane(s), ${liveOpsControlPlane.counts?.audit_backed_count || 0} audit-backed, ${liveOpsControlPlane.counts?.local_external_mutation_count || 0} local external mutation(s).`));
    }
    if (notificationControlPlane.schema_version) {
      tiles.push(reportTile("Notification Control Plane", `${notificationControlPlane.status}: ${notificationControlPlane.summary?.channel_count || 0} channel(s), ${notificationControlPlane.summary?.contract_ready_count || 0} contract-ready, ${notificationControlPlane.summary?.growth_point_count || 0} growth point(s), live mutations ${notificationControlPlane.summary?.live_mutation_count || 0}.`));
    }
    if (billingMigrationReadiness.schema_version) {
      tiles.push(reportTile("Billing Migration Readiness", `${billingMigrationReadiness.summary?.status || "unknown"}: ${billingMigrationReadiness.summary?.upstream_commit_count || 0} A1 commit(s), ${billingMigrationReadiness.db_contract?.tables?.length || 0} billing table(s), live billing ${billingMigrationReadiness.summary?.ready_for_live_customer_billing ? "ready" : "blocked"}.`));
    }
  if (hostedReports.length) {
    tiles.push(reportTile("Hosted Reports", `${reportCenter.summary?.shareable_count || 0} shareable, ${reportCenter.summary?.revoked_count || 0} revoked, ${reportCenter.summary?.expired_count || 0} expired, ${reportCenter.summary?.total_view_count || 0} total view(s). Scope ${(reportCenter.tenant_scope?.organization_id || "org-local")} / ${(reportCenter.tenant_scope?.workspace_id || "workspace-local")} / ${(reportCenter.tenant_scope?.project_id || "project-local")} / ${(reportCenter.tenant_scope?.environment_id || "staging")}.`));
    tiles.push(reportTile("Share Link Governance", buildShareLinkGovernanceTile(reportCenter)));
    tiles.push(reportTile("Export Audience", buildExportAudienceTile(reportCenter)));
    tiles.push(reportTile("Audience Filters", audienceFilterSummary));
    tiles.push(reportTile("Workspace Groups", workspaceGroupSummary));
    tiles.push(reportTile("Environment Groups", environmentGroupSummary));
    tiles.push(reportTile("External Publish Blockers", externalPublishBlockerSummary));
    tiles.push(reportTile("Release Sign-Off", buildReleaseSignoffTile(reportCenter)));
    tiles.push(reportTile("Sign-Off Detail", buildReleaseSignoffDetailTile(reportCenter)));
    tiles.push(...hostedReports.map(hostedReportRow));
  }
  if (artifactRegistry.schema_version === "a3.artifact_registry.v1") {
    tiles.push(artifactRegistrySummaryRow(artifactRegistry));
    tiles.push(...(artifactRegistry.entries || []).slice(0, 8).map(artifactEntryRow));
  }
  $("report-center").replaceChildren(...tiles);
}

function renderExportRedactionFirewall() {
  const firewall = summarizeExportRedactionFirewall(
    state.runs,
    state.grades,
    state.coverage,
    state.mediaSignedUrlCoverage,
    state.frontendCodeCrawl
  );
  const status = $("export-redaction-status");
  status.className = `badge ${exportFirewallStatusClass(firewall.status)}`;
  status.textContent = firewall.status;
  $("export-redaction-summary").textContent = firewall.available
    ? `${firewall.commercial_value} ${firewall.replacement_count} replacement(s), ${firewall.residual_finding_count} residual finding(s), ${firewall.surface_count} surface(s) checked.`
    : "No export firewall scan is available.";
  $("export-redaction-metrics").replaceChildren(
    healthTile(firewall.secret_free_exports ? "yes" : "no", "secret-free"),
    healthTile(String(firewall.replacement_count), "replacements"),
    healthTile(String(firewall.residual_finding_count), "residuals"),
    healthTile(String(firewall.surface_count), "surfaces")
  );
  $("export-redaction-surfaces").replaceChildren(...(
    firewall.checked_surfaces.length
      ? firewall.checked_surfaces.map((surface) => exportSurfaceRow(surface))
      : [emptyMatrixRow("No export surfaces were scanned.")]
  ));
  $("export-redaction-guardrails").replaceChildren(...firewall.guardrails.map((guardrail) => miniRow("Guardrail", guardrail)));
}

function exportSurfaceRow(surface) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(surface.surface)}</strong>
      <span class="badge ${exportFirewallStatusClass(surface.status)}">${escapeHtml(surface.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(surface.replacement_count)} replacement(s)</span>
      <span>${escapeHtml(surface.residual_finding_count)} residual(s)</span>
      <span>${escapeHtml(surface.blocked ? "blocked" : "shareable")}</span>
    </div>
    <div class="muted">${escapeHtml(surface.rules_triggered.join(", ") || "no rules triggered")}</div>
  `;
  return node;
}

function exportFirewallStatusClass(status) {
  if (status === "passed") {
    return "pass";
  }
  if (status === "cleaned") {
    return "warn";
  }
  if (status === "blocked") {
    return "fail";
  }
  return "neutral";
}

function buildReportCommercialLoopSummary({ reportCenter = {}, reviewWorkflow = {}, notificationControlPlane = {}, liveOpsControlPlane = {} } = {}) {
  const reportSummary = reportCenter.summary || {};
  const notificationSummary = notificationControlPlane.summary || {};
  const liveOpsCounts = liveOpsControlPlane.counts || {};
  const reviewCount = Number(reviewWorkflow.record_count || 0);
  return `${reviewCount} review record(s), ${reportSummary.shareable_count || 0} shareable report(s), ${reportSummary.revoked_count || 0} revoked, ${notificationSummary.channel_count || 0} notification lane(s), ${notificationSummary.contract_ready_count || 0} contract-ready, and ${liveOpsCounts.audit_backed_count || 0} audit-backed live-op lane(s).`;
}

function buildGithubPublishPostureTile(githubEvidence = {}, releaseWorkflow = {}, releaseEvidence = {}) {
  const check = githubEvidence.check_publish || {};
  const comment = githubEvidence.pr_comment_publish || {};
  const required = githubEvidence.required_check_plan || {};
  const mode = check.posted === true || comment.posted === true ? "posted" : "dry-run";
  return `${mode}: check ${check.status || "unknown"}, comment ${comment.status || "unknown"}, required check ${required.required_check_name || releaseWorkflow.github_check?.name || "unknown"}, release evidence ${releaseEvidence.overall_status || "unknown"}.`;
}

function buildShareLinkGovernanceTile(reportCenter = {}) {
  const governance = reportCenter.share_link_governance || {};
  return `${governance.status || "unknown"}: ${governance.shareable_count || 0} shareable, ${governance.revoked_count || 0} revoked, ${governance.expired_count || 0} expired, ${governance.blocked_count || 0} blocked. ${(governance.policy_summary || []).slice(0, 1).join(" ")}`;
}

function buildExportAudienceTile(reportCenter = {}) {
  const governance = reportCenter.export_audience_governance || {};
  const filters = reportCenter.audience_filters || {};
  const allowed = Array.isArray(governance.audiences)
    ? governance.audiences.filter((item) => item.allowed).map((item) => item.audience)
    : [];
  const blocked = Array.isArray(governance.audiences)
    ? governance.audiences.filter((item) => item.allowed === false).map((item) => item.audience)
    : [];
  const defaultFilter = filters.default_filter || "internal_ops";
  return `${governance.status || "unknown"}: ${(allowed.length ? allowed.join(", ") : "no audience approved")}; blocked ${(blocked.join(", ") || "none")}; default ${defaultFilter}. ${(governance.governance_rules || []).slice(0, 1).join(" ")}`;
}

function buildReleaseSignoffDetailTile(reportCenter = {}) {
  const detail = reportCenter.release_signoff_detail || {};
  const passed = Array.isArray(detail.checklist) ? detail.checklist.filter((item) => item.passed).length : 0;
  const total = Array.isArray(detail.checklist) ? detail.checklist.length : 0;
  return `${passed}/${total} checklist item(s) passed; ${(detail.recommendations || []).slice(0, 2).join(" ") || "No recommendation loaded."}`;
}

function buildReleaseSignoffTile(reportCenter = {}) {
  const signoff = reportCenter.release_signoff_summary || {};
  return `${signoff.status || "unknown"}: ${signoff.shareable_count || 0} shareable, ${signoff.release_evidence_ready_count || 0} release-evidence-ready, ${signoff.manifest_ready_count || 0} manifest-ready, usage ${signoff.usage_ready ? "ready" : "missing"}, migration ${signoff.migration_ready ? "ready" : "missing"}.`;
}

function buildAudienceFilterSummary(filters = {}) {
  const entries = Array.isArray(filters.filters) ? filters.filters : [];
  const visible = entries.filter((item) => item.allowed_count > 0).map((item) => item.audience);
  const blocked = entries.filter((item) => item.state === "blocked").map((item) => item.audience);
  return `${filters.status || "unknown"}: visible ${(visible.join(", ") || "none")}, blocked ${(blocked.join(", ") || "none")}, default ${filters.default_filter || "internal_ops"}.`;
}

function buildGroupedScopeSummary(grouped = {}, label) {
  const groups = Array.isArray(grouped.groups) ? grouped.groups : [];
  if (!groups.length) {
    return `${grouped.status || "unknown"}: no ${label} grouping yet.`;
  }
  const top = groups[0] || {};
  const topValue = top[`${label}_id`] || top.workspace_id || top.environment_id || "unknown";
  return `${grouped.status || "unknown"}: ${groups.length} ${label} group(s), top ${topValue}, ${top.shareable_count || 0} shareable, ${top.release_evidence_ready_count || 0} release-evidence-ready.`;
}

function buildExternalPublishBlockerSummary(blockers = {}) {
  const reasons = Array.isArray(blockers.reasons) ? blockers.reasons : [];
  return `${blockers.status || "unknown"}: ${blockers.blocker_count || 0} blocked report(s). ${(reasons[0] || "No blocker reason loaded.")}`;
}

function reportTile(label, description) {
  const node = document.createElement("div");
  node.className = "report-tile";
  node.innerHTML = `<strong>${escapeHtml(label)}</strong><span>${escapeHtml(description)}</span>`;
  return node;
}

function hostedReportRow(report) {
  const node = document.createElement("div");
  node.className = "matrix-row";
  const audience = Array.isArray(report.export_audience?.allowed) ? report.export_audience.allowed : [];
  const blockedAudience = Array.isArray(report.export_audience?.blocked) ? report.export_audience.blocked : [];
  const blockerState = report.export_audience?.customer_external_blocked ? "customer external blocked" : "external publish open";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(report.title || report.report_id)}</strong>
      <span class="badge ${reportStatusClass(report.status)}">${escapeHtml(report.status)}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(report.report_id)}</span>
      <span>${escapeHtml(report.share_url_path || "no share path")}</span>
      <span>${escapeHtml(report.view_count || 0)} view(s)</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(report.tenant_scope?.workspace_id || "workspace-local")}</span>
      <span>${escapeHtml(report.tenant_scope?.project_id || "project-local")}</span>
      <span>${escapeHtml(report.tenant_scope?.environment_id || "staging")}</span>
      <span>${escapeHtml(report.share_link?.scope || "private_link")}</span>
    </div>
    <div class="case-meta">
      <span>audience ${(audience.join(", ") || "none")}</span>
      <span>blocked ${(blockedAudience.join(", ") || "none")}</span>
      <span>${escapeHtml(blockerState)}</span>
      <span>token ${escapeHtml(report.share_link?.token_hash_prefix || "n/a")}</span>
    </div>
    <div class="case-meta">
      <span>manifest ${escapeHtml(report.manifest?.completeness_score ?? 0)}%</span>
      <span>${escapeHtml(report.redaction?.status || "unknown")} redaction</span>
      <span>${report.release_evidence?.available ? "release evidence ready" : "release evidence missing"}</span>
      <span>${report.lifecycle?.view_audit_enabled ? "audit visible" : "audit missing"}</span>
    </div>
    <div class="muted">${escapeHtml((report.manifest?.missing || []).length ? `Missing: ${report.manifest.missing.join(", ")}` : "Manifest evidence is ready for PR gate and audit bundle linkage.")}</div>
  `;
  const canRevoke = isA3ApiSource(state.source)
    && report.lifecycle?.revocable !== false
    && !["revoked", "expired"].includes(report.status);
  if (canRevoke) {
    const actions = document.createElement("div");
    actions.className = "report-actions compact";
    const revokeButton = document.createElement("button");
    revokeButton.type = "button";
    revokeButton.className = "button danger";
    revokeButton.textContent = "Revoke";
    revokeButton.title = "Revoke hosted report link and refresh Report Center evidence";
    revokeButton.addEventListener("click", () => revokeHostedReport(report));
    actions.append(revokeButton);
    node.append(actions);
  }
  return node;
}

function artifactRegistrySummaryRow(registry = {}) {
  const summary = registry.summary || {};
  const node = document.createElement("div");
  node.className = "matrix-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>Artifact Registry</strong>
      <span class="badge ${summary.blocked_count ? "fail" : summary.artifact_count ? "pass" : "neutral"}">${escapeHtml(registry.registry_status || "unknown")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(summary.artifact_count || 0)} artifact(s)</span>
      <span>${escapeHtml(summary.ready_count || 0)} ready</span>
      <span>${escapeHtml(summary.hash_ready_count || 0)} hash-ready</span>
      <span>${escapeHtml(summary.billable_meter_count || 0)} billable meter(s)</span>
    </div>
    <div class="muted">${escapeHtml((registry.next_actions || []).join(" "))}</div>
  `;
  return node;
}

function artifactEntryRow(entry = {}) {
  const node = document.createElement("div");
  node.className = "matrix-row artifact-row";
  node.innerHTML = `
    <div class="matrix-head">
      <strong>${escapeHtml(entry.artifact_type || entry.artifact_id)}</strong>
      <span class="badge ${artifactLifecycleClass(entry.lifecycle_state)}">${escapeHtml(entry.lifecycle_state || "unknown")}</span>
    </div>
    <div class="case-meta">
      <span>${escapeHtml(entry.content_type || "unknown")}</span>
      <span>${escapeHtml(entry.hash_status || "unknown")}</span>
      <span>${escapeHtml(entry.redaction_status || "unknown")} redaction</span>
      <span>${escapeHtml(entry.billable_meter || "no meter")}</span>
    </div>
    <div class="muted">${escapeHtml(entry.customer_value || "")}</div>
  `;
  return node;
}

function artifactLifecycleClass(stateValue) {
  if (stateValue === "shared" || stateValue === "generated" || stateValue === "retained") {
    return "pass";
  }
  if (stateValue === "planned") {
    return "warn";
  }
  if (stateValue === "blocked") {
    return "fail";
  }
  return "neutral";
}

function reportStatusClass(status) {
  if (status === "shareable") {
    return "pass";
  }
  if (status === "expired" || status === "revoked") {
    return "warn";
  }
  if (status === "blocked") {
    return "fail";
  }
  return "neutral";
}

function renderPrintReport() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  const coverage = summarizeCoverage(state.coverage);
  const requestProvenance = summarizeRequestProvenance(state.requestProvenance);
  const usageQuota = summarizeUsageQuota(state.usageQuota, state.usageQuotaApiProbe);
  const mediaReadiness = summarizeMediaReadiness(state.runs, state.grades, state.usageQuota, state.mediaSignedUrlCoverage);
  const cloudShell = summarizeCloudConsoleShell(state.authCheck, state.frontendSummary, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe);
  const productConsole = summarizeProductConsoleExport(state.productConsole);
  const saasAdmin = summarizeSaasAdminExport(state.saasAdmin);
  const artifactRegistry = summarizeArtifactRegistryExport(state.artifactRegistry);
  const releaseEvidence = summarizeReleaseEvidenceSummary(state.releaseEvidence);
  const officialGap = summarizeOfficialAshrGap(state.runs, state.grades, state.coverage, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe);
  const officialMirror = summarizeOfficialFrontendMirror(state.frontendMirror);
  const officialCodeCrawl = summarizeOfficialCodeCrawlParity(state.frontendCodeCrawl);
  const officialParityRoadmap = summarizeOfficialParityRoadmap(state.runs, state.grades, state.coverage, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe, state.mediaSignedUrlCoverage, state.frontendMirror);
  const incidentReplay = summarizeIncidentReplayQueue(state.runs, state.grades, state.mediaSignedUrlCoverage);
  const observabilityReplay = summarizeObservabilityReplayMatrix(state.runs, state.grades, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const regressionFactory = summarizeRegressionFactory(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const exportRedactionFirewall = summarizeExportRedactionFirewall(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.frontendCodeCrawl);
  const reviewerWorkflowBoard = summarizeReviewerWorkflowBoard(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseGate = summarizeReleaseGate(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseWorkflow = summarizeReleaseWorkflow(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage);
  const releaseWarRoom = summarizeReleaseWarRoom(state.runs, state.grades, state.coverage, state.mediaSignedUrlCoverage, state.requestProvenance, state.usageQuota, state.usageQuotaApiProbe, state.frontendMirror);
  const clusters = clusterFailures(state.runs, state.grades);
  const selected = state.cases.find((item) => item.case_id === state.selectedCaseId) || state.filteredCases[0] || state.cases[0] || null;
  const failedCases = [...state.filteredCases]
    .filter((item) => !item.passed)
    .sort((left, right) => triageWeight(right) - triageWeight(left) || left.score - right.score)
    .slice(0, 6);
  const selectedDiffs = selected ? buildToolCallDiffs(selected).filter((diff) => diff.status !== "match") : [];

  $("print-report").innerHTML = `
    <div class="report-cover">
      <div class="section-kicker">A3 Dashboard & Triage</div>
      <h3>Agent Evaluation Report</h3>
      <div class="caption">${escapeHtml(sourceLabel(state.source))} / ${escapeHtml(summary.lastRunId)}${coverage.available ? ` / ${escapeHtml(coverage.pack_id)}` : ""}</div>
    </div>
    <div class="report-metrics">
      ${reportMetric("Runs", summary.totalRuns)}
      ${reportMetric("Cases", summary.totalCases)}
      ${reportMetric("Pass Rate", `${summary.passRate}%`)}
      ${reportMetric("Avg Score", summary.avgScore)}
      ${reportMetric("Trace", `${summary.traceCompleteness}%`)}
      ${reportMetric("Media", summary.mediaEvidenceCases)}
    </div>
    <div class="report-section">
      <h4>Release Gate</h4>
      <div class="muted">${escapeHtml(releaseGate.summary)} ${escapeHtml(releaseGate.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Decision", releaseGate.decision_label],
        ["Risk score", releaseGate.risk_score],
        ["Failed checks", releaseGate.failed_check_count],
        ["Blocks merge", releaseGate.pr_gate.blocks_merge ? "yes" : "no"],
        ["Required approvers", releaseGate.required_approvers.join(", ") || "none"]
      ])}
      ${renderReportTable(["Check", "Status", "Evidence"], releaseGate.checks.map((check) => [
        check.id,
        check.passed ? "pass" : "fail",
        `${check.observed}. ${check.detail}`
      ]), "No release gate checks.")}
    </div>
    <div class="report-section">
      <h4>PR Gate & Audit Workflow</h4>
      <div class="muted">${escapeHtml(releaseWorkflow.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["GitHub check", releaseWorkflow.github_check.name],
        ["Conclusion", releaseWorkflow.github_check.conclusion],
        ["Release", releaseWorkflow.release_version],
        ["Environment", releaseWorkflow.environment],
        ["Review state", releaseWorkflow.reviewer_workflow.state],
        ["Waiver", releaseWorkflow.waiver_policy.guidance],
        ["Incident replay", releaseWorkflow.incident_replay.case_ids.join(", ") || "none"]
      ])}
      ${renderReportTable(["Artifact", "Required", "Purpose"], releaseWorkflow.audit_bundle.artifacts.map((artifact) => [
        artifact.id,
        artifact.required ? "yes" : "no",
        `${artifact.path}: ${artifact.purpose}`
      ]))}
    </div>
    <div class="report-section">
      <h4>Product Console / Onboarding / Audit</h4>
      <div class="muted">${escapeHtml(productConsole.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Available", productConsole.available ? "yes" : "no"],
        ["Onboarding", productConsole.available ? `${productConsole.onboarding.status} / ${productConsole.onboarding.completed_steps}/${productConsole.onboarding.total_steps} / ${productConsole.onboarding.completion_rate}%` : "missing"],
        ["Project status", productConsole.available ? productConsole.project_console.status : "missing"],
        ["Project evidence", productConsole.available ? `${productConsole.project_console.run_count} run(s), ${productConsole.project_console.case_count} case(s), ${productConsole.project_console.failed_case_count} failed, ${productConsole.project_console.report_count} report(s)` : "missing"],
        ["Audit log", productConsole.available ? `${productConsole.audit_log.status}, ${productConsole.audit_log.event_count} event(s), redacted-only ${productConsole.audit_log.redacted_payload_only ? "yes" : "no"}` : "missing"],
        ["Commercial readiness", productConsole.available ? `${productConsole.commercial_readiness.status} / ${productConsole.commercial_readiness.readiness_score}` : "missing"],
        ["Money path", productConsole.available ? productConsole.commercial_readiness.strongest_money_path : "missing"]
      ])}
      ${renderReportTable(["Check", "Status", "Passed"], productConsole.available ? productConsole.commercial_readiness.checks.map((check) => [
        check.id,
        check.status,
        check.passed ? "yes" : "no"
      ]) : [], "No Product Console readiness checks.")}
    </div>
    <div class="report-section">
      <h4>SaaS Admin / Login / Team / Trust</h4>
      <div class="muted">${escapeHtml(saasAdmin.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Available", saasAdmin.available ? "yes" : "no"],
        ["Login", saasAdmin.available ? `${saasAdmin.login.status}, ${saasAdmin.login.provider}, identity redacted ${saasAdmin.login.user_identity_redacted ? "yes" : "no"}` : "missing"],
        ["Team", saasAdmin.available ? `${saasAdmin.team.status}, ${saasAdmin.team.member_count} member(s), invite ${saasAdmin.team.invite_mode}` : "missing"],
        ["Usage", saasAdmin.available ? `${saasAdmin.usage.status}, plan ${saasAdmin.usage.plan_name}, quota mutation ${saasAdmin.usage.quota_mutations_enabled ? "enabled" : "disabled"}` : "missing"],
        ["API keys", saasAdmin.available ? `${saasAdmin.api_keys.status}, ${saasAdmin.api_keys.key_count} metadata row(s), ${saasAdmin.api_keys.reveal_policy}` : "missing"],
        ["Trust", saasAdmin.available ? `${saasAdmin.trust.status}, publish ${saasAdmin.trust.publish_enabled ? "enabled" : "disabled"}, public publish ${saasAdmin.trust.public_publish_enabled ? "enabled" : "disabled"}` : "missing"],
        ["Cloud management", saasAdmin.available ? `${saasAdmin.cloud_management.status}, ${saasAdmin.cloud_management.resource_count} resource(s), real mutations ${saasAdmin.cloud_management.real_mutations_enabled ? "enabled" : "disabled"}` : "missing"],
        ["Action requests", saasAdmin.available ? `${saasAdmin.action_requests?.request_count || 0} recorded, ${saasAdmin.action_requests?.pending_count || 0} pending, real cloud writes ${saasAdmin.action_requests?.real_cloud_mutations_performed ? "yes" : "no"}` : "missing"],
        ["A1/A2 compatibility", saasAdmin.available ? `A1 ${saasAdmin.a1_a2_compatibility.a1_run_result_ready ? "ready" : "missing"}, A2 ${saasAdmin.a1_a2_compatibility.a2_grade_result_ready ? "ready" : "missing"}` : "missing"]
      ])}
      ${renderReportTable(["Action", "Mode", "Real Cloud Write"], saasAdmin.available ? saasAdmin.action_plans.map((action) => [
        action.action,
        action.mode,
        action.writes_real_ashr_cloud ? "yes" : "no"
      ]) : [], "No SaaS admin action guardrails.")}
      ${renderReportTable(["Request", "Action", "Status"], saasAdmin.available ? (saasAdmin.action_requests?.latest || []).map((request) => [
        request.request_id,
        request.action,
        request.status
      ]) : [], "No SaaS admin action requests recorded yet.")}
    </div>
    <div class="report-section">
      <h4>Artifact Registry</h4>
      <div class="muted">${escapeHtml(artifactRegistry.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Available", artifactRegistry.available ? "yes" : "no"],
        ["Status", artifactRegistry.available ? artifactRegistry.status : "missing"],
        ["Artifacts", artifactRegistry.available ? `${artifactRegistry.artifact_count} total, ${artifactRegistry.report_artifact_count} report, ${artifactRegistry.control_artifact_count} control` : "missing"],
        ["Ready / blocked", artifactRegistry.available ? `${artifactRegistry.ready_count} ready, ${artifactRegistry.blocked_count} blocked` : "missing"],
        ["Hash-ready", artifactRegistry.available ? String(artifactRegistry.hash_ready_count) : "missing"],
        ["Billable meters", artifactRegistry.available ? String(artifactRegistry.billable_meter_count) : "missing"],
        ["Safety", artifactRegistry.available ? `raw secrets ${artifactRegistry.safety.raw_secret_values_allowed ? "allowed" : "blocked"}, raw share tokens ${artifactRegistry.safety.raw_share_tokens_stored ? "stored" : "not stored"}` : "missing"]
      ])}
      ${renderReportTable(["Artifact", "Lifecycle", "Hash", "Meter"], artifactRegistry.available ? artifactRegistry.top_artifacts.map((artifact) => [
        artifact.artifact_type,
        artifact.lifecycle_state,
        artifact.hash_status,
        artifact.billable_meter
      ]) : [], "No Artifact Registry entries.")}
    </div>
    <div class="report-section">
      <h4>Release Evidence</h4>
      <div class="muted">${escapeHtml(releaseEvidence.available ? releaseEvidence.commercial_value : releaseEvidence.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Available", releaseEvidence.available ? "yes" : "no"],
        ["Overall status", releaseEvidence.overall_status],
        ["GitHub check", releaseEvidence.available ? `${releaseEvidence.github_check_publish.status}, dry-run ${releaseEvidence.github_check_publish.dry_run ? "yes" : "no"}, posted ${releaseEvidence.github_check_publish.posted ? "yes" : "no"}` : "missing"],
        ["PR comment", releaseEvidence.available ? `${releaseEvidence.github_pr_comment_publish.status}, dry-run ${releaseEvidence.github_pr_comment_publish.dry_run ? "yes" : "no"}, posted ${releaseEvidence.github_pr_comment_publish.posted ? "yes" : "no"}` : "missing"],
        ["Required check", releaseEvidence.available ? `${releaseEvidence.github_required_check_plan.check_name}, maintainer approval ${releaseEvidence.github_required_check_plan.maintainer_approval_required ? "required" : "not required"}` : "missing"],
        ["Check readback", releaseEvidence.available ? `${releaseEvidence.github_check_readback.readback_status}, head SHA match ${releaseEvidence.github_check_readback.head_sha_match === null ? "unknown" : releaseEvidence.github_check_readback.head_sha_match ? "yes" : "no"}` : "missing"],
        ["PR comment readback", releaseEvidence.available ? `${releaseEvidence.pr_comment_readback.readback_status}, body hash match ${releaseEvidence.pr_comment_readback.body_hash_match === null ? "unknown" : releaseEvidence.pr_comment_readback.body_hash_match ? "yes" : "no"}` : "missing"],
        ["Required-check readback", releaseEvidence.available ? `${releaseEvidence.required_check_proof.readback_status}, enforced ${releaseEvidence.required_check_proof.enforced ? "yes" : "no"}, plan-only guard ${releaseEvidence.required_check_proof.plan_only_must_not_claim_enforcement ? "on" : "off"}` : "missing"],
        ["Readback records", releaseEvidence.available ? `${releaseEvidence.readback_record_count || 0} total, ${releaseEvidence.readback_status_counts?.readback_confirmed || 0} confirmed, ${releaseEvidence.readback_status_counts?.stale || 0} stale` : "missing"],
        ["A1/A2 boundary", releaseEvidence.available ? releaseEvidence.readback_history?.a1_a2_boundary || "Readback does not replace A1/A2 evidence." : "missing"],
        ["Audit bundle", releaseEvidence.available ? `${releaseEvidence.audit_bundle_verification.status}, hash ${releaseEvidence.audit_bundle_verification.root_hash_passed ? "pass" : "missing"}, artifacts ${releaseEvidence.audit_bundle_verification.artifact_passed}/${releaseEvidence.audit_bundle_verification.artifact_total}` : "missing"],
        ["Audit archive", releaseEvidence.available ? `${releaseEvidence.audit_archive_verification.status}, signature ${releaseEvidence.audit_archive_verification.signature_passed ? "pass" : "missing"}, entries ${releaseEvidence.audit_archive_verification.entry_passed}/${releaseEvidence.audit_archive_verification.entry_total}` : "missing"],
        ["Safety", releaseEvidence.available ? `tokens ${releaseEvidence.safety.token_included ? "included" : "not included"}, real GitHub mutation ${releaseEvidence.safety.real_github_mutation_performed ? "yes" : "no"}, raw private key ${releaseEvidence.safety.raw_private_key_stored ? "stored" : "not stored"}` : "missing"]
      ])}
    </div>
    <div class="report-section">
      <h4>Release War Room</h4>
      <div class="muted">${escapeHtml(releaseWarRoom.customer_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Decision", releaseWarRoom.decision_label],
        ["Urgency", releaseWarRoom.urgency],
        ["Revenue risk score", releaseWarRoom.revenue_risk_score],
        ["Blocks merge", releaseWarRoom.blocks_merge ? "yes" : "no"],
        ["Waiver required", releaseWarRoom.waiver_required ? "yes" : "no"],
        ["Incident replay cases", releaseWarRoom.incident_replay_case_count],
        ["Required artifacts", releaseWarRoom.required_artifact_count]
      ])}
      ${renderReportTable(["Lane", "Status", "Next Action"], releaseWarRoom.lanes.map((lane) => [
        `${lane.lane} / ${lane.owner}`,
        lane.status,
        lane.next_action
      ]))}
    </div>
    <div class="report-section">
      <h4>Incident Replay Queue</h4>
      <div class="muted">${escapeHtml(incidentReplay.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Queued cases", incidentReplay.queue_count],
        ["Release blockers", incidentReplay.blocker_count],
        ["Trace ready", incidentReplay.trace_ready_count],
        ["Tool diff ready", incidentReplay.tool_diff_ready_count],
        ["Judge evidence ready", incidentReplay.judge_evidence_ready_count],
        ["Media evidence ready", incidentReplay.media_evidence_ready_count]
      ])}
      ${renderReportTable(["Case", "Owner", "Replay Evidence"], incidentReplay.queue.map((item) => [
        `${item.rank}. ${item.case_id}`,
        item.owner_lane,
        `${item.primary_failure_class} / ${item.severity} / trace ${item.trace_event_count} / diffs ${item.tool_diff_count} / judge ${item.judge_evidence_count}`
      ]), "No incident replay cases.")}
    </div>
    <div class="report-section">
      <h4>Observability Replay Matrix</h4>
      <div class="muted">${escapeHtml(observabilityReplay.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Replay cases", observabilityReplay.replay_case_count],
        ["Trace ready", observabilityReplay.trace_ready_count],
        ["Tool/error cases", observabilityReplay.tool_error_case_count],
        ["Latency/duration cases", observabilityReplay.latency_case_count],
        ["Judge linked", observabilityReplay.judge_linked_count],
        ["Blocked replay", observabilityReplay.blocked_replay_count],
        ["Official Observability", observabilityReplay.official_observability_confirmed ? "mapped" : "unconfirmed"]
      ])}
      ${renderReportTable(["Lane", "Status", "Next Action"], observabilityReplay.lanes.map((lane) => [
        `${lane.lane} (${lane.ready_count}/${lane.total_count})`,
        lane.status,
        lane.next_action
      ]), "No observability replay lanes.")}
      ${renderReportTable(["Case", "Risk", "Replay Evidence"], observabilityReplay.items.map((item) => [
        `${item.case_id} / ${item.owner_lane}`,
        item.production_risk,
        `${item.observability_state}; trace ${item.trace_event_count}; errors ${item.error_signal_count}; judge ${item.judge_evidence_count}`
      ]), "No observability replay items.")}
    </div>
    <div class="report-section">
      <h4>Regression Factory</h4>
      <div class="muted">${escapeHtml(regressionFactory.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Factory state", regressionFactory.factory_state],
        ["Candidates", regressionFactory.candidate_count],
        ["Ready", regressionFactory.ready_count],
        ["Needs evidence", regressionFactory.needs_evidence_count],
        ["Blocked", regressionFactory.blocked_count],
        ["Coverage gaps", regressionFactory.coverage_gap_count],
        ["Official Results", regressionFactory.official_results_review_confirmed ? "mapped" : "unconfirmed"]
      ])}
      ${renderReportTable(["Lane", "Status", "Next Action"], regressionFactory.lanes.map((lane) => [
        `${lane.lane} (${lane.ready_count}/${lane.total_count})`,
        lane.status,
        lane.next_action
      ]), "No regression factory lanes.")}
      ${renderReportTable(["Candidate", "State", "Contracts"], regressionFactory.candidates.map((item) => [
        `${item.regression_id} / ${item.case_id}`,
        `${item.generator_state} / ${item.coverage_status}`,
        item.required_contracts.join(", ") || "none"
      ]), "No regression candidates.")}
    </div>
    <div class="report-section">
      <h4>Export Redaction Firewall</h4>
      <div class="muted">${escapeHtml(exportRedactionFirewall.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Status", exportRedactionFirewall.status],
        ["Secret-free exports", exportRedactionFirewall.secret_free_exports ? "yes" : "no"],
        ["Replacement count", exportRedactionFirewall.replacement_count],
        ["Residual findings", exportRedactionFirewall.residual_finding_count],
        ["Checked surfaces", exportRedactionFirewall.surface_count],
        ["Fail-closed ready", exportRedactionFirewall.fail_closed_ready ? "yes" : "no"]
      ])}
      ${renderReportTable(["Surface", "Status", "Rules"], exportRedactionFirewall.checked_surfaces.map((surface) => [
        surface.surface,
        `${surface.status}; ${surface.replacement_count} replacement(s); ${surface.residual_finding_count} residual(s)`,
        surface.rules_triggered.join(", ") || "none"
      ]), "No export surfaces scanned.")}
    </div>
    <div class="report-section">
      <h4>Reviewer Workflow Board</h4>
      <div class="muted">${escapeHtml(reviewerWorkflowBoard.commercial_value)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Board state", reviewerWorkflowBoard.board_label],
        ["Open items", reviewerWorkflowBoard.open_item_count],
        ["Blocked items", reviewerWorkflowBoard.blocked_item_count],
        ["Needs evidence", reviewerWorkflowBoard.needs_evidence_count],
        ["Required reviewers", reviewerWorkflowBoard.required_reviewer_count],
        ["A1 trace ready", reviewerWorkflowBoard.a1_a2_calibration.a1_trace_ready_count],
        ["A2 judge ready", reviewerWorkflowBoard.a1_a2_calibration.a2_judge_evidence_ready_count]
      ])}
      ${renderReportTable(["Lane", "Status", "Next Action"], reviewerWorkflowBoard.lanes.map((lane) => [
        `${lane.lane} (${lane.item_count} item(s))`,
        lane.status,
        lane.next_action
      ]), "No reviewer workflow lanes.")}
      ${renderReportTable(["Case", "Review State", "Missing Evidence"], reviewerWorkflowBoard.items.map((item) => [
        `${item.case_id} / ${item.owner_lane}`,
        item.review_state,
        item.missing_artifacts.join(", ") || "none"
      ]), "No reviewer workflow items.")}
    </div>
    <div class="report-section">
      <h4>Official Code Crawl Parity</h4>
      <div class="muted">${escapeHtml(officialCodeCrawl.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Source archive", officialCodeCrawl.source_archive],
        ["Lab JS chunks", officialCodeCrawl.lab_javascript_chunk_count],
        ["Parity targets", officialCodeCrawl.parity_target_count],
        ["Copy now", officialCodeCrawl.copy_now_count],
        ["Partial", officialCodeCrawl.partial_count],
        ["Do not copy", officialCodeCrawl.out_of_scope_count],
        ["Official source committed", officialCodeCrawl.safety.official_source_committed ? "yes" : "no"]
      ])}
      ${renderReportTable(["Chunk", "A3 Status", "Top Signals"], officialCodeCrawl.chunks.slice(0, 6).map((chunk) => [
        `${chunk.chunk} / ${chunk.role}`,
        chunk.a3_status,
        chunk.top_signals.map((item) => `${item.signal}:${item.count}`).join(", ") || "none"
      ]), "No code crawl chunks.")}
      ${renderReportTable(["Target", "A3 Status", "A1/A2 Dependency"], officialCodeCrawl.parity_targets.map((target) => [
        target.target,
        target.a3_status,
        target.a3_dependency
      ]), "No code crawl parity targets.")}
    </div>
    <div class="report-section">
      <h4>Coverage Health</h4>
      <div class="muted">${coverage.available
        ? `${escapeHtml(coverage.scenario_count)} scenario(s), ${escapeHtml(coverage.executable_run_case_count)} executable case(s), ${escapeHtml(coverage.primary_failure_class_count)} failure class(es), assignment minimums ${coverage.meets_assignment_minimums ? "met" : "not met"}.`
        : "No A2 coverage fixture is available for this report."}</div>
    </div>
    <div class="report-section">
      <h4>Request Provenance</h4>
      <div class="muted">${requestProvenance.available
        ? `${escapeHtml(requestProvenance.total_requests)} request sample(s), latest status ${escapeHtml(requestProvenance.latest_request.request_status)}, accepted inputs ${escapeHtml(requestProvenance.latest_request.accepted_input_types.join(", ") || "none")}, generation outputs ${escapeHtml(requestProvenance.latest_request.generation_outputs.join(", ") || "none")}.`
        : "No Ashr request provenance fixture is available for this report."}</div>
    </div>
    <div class="report-section">
      <h4>Usage / Quota</h4>
      <div class="muted">${usageQuota.available
        ? `${escapeHtml(usageQuota.frontend_modules.join(", ") || "Usage modules")} observed; channels ${escapeHtml(usageQuota.channels.join(", ") || "unknown")}; API-key access ${usageQuota.direct_api_accessible ? "available" : "not available"}${usageQuota.oauth_only_functions.length ? `; OAuth-gated ${escapeHtml(usageQuota.oauth_only_functions.join(", "))}` : ""}.`
        : "No Ashr usage/quota calibration fixture is available for this report."}</div>
    </div>
    <div class="report-section">
      <h4>Media Readiness</h4>
      <div class="muted">${mediaReadiness.available
        ? `${escapeHtml(mediaReadiness.media_case_count)} media case(s), ${escapeHtml(mediaReadiness.channels.join(", ") || "unknown")} channel(s), ${escapeHtml(mediaReadiness.signed_url_key_count)} signed URL key(s), live rendering ${mediaReadiness.live_rendering_allowed ? "allowed" : "blocked by safety"}.`
        : "No media readiness evidence is available for this report."}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Evidence items", mediaReadiness.evidence_item_count],
        ["VM streams", mediaReadiness.vm_stream_count],
        ["Signed URL confirmed", mediaReadiness.signed_url_confirmed_types.join(", ") || "none"],
        ["Still unconfirmed", mediaReadiness.signed_url_unconfirmed_types.join(", ") || "none"],
        ["Guidance", mediaReadiness.guidance]
      ])}
      ${renderReportTable(["Channel", "Policy", "Decision"], mediaReadiness.channel_matrix.map((channel) => [
        channel.channel,
        channel.preview_policy,
        channel.decision
      ]), "No media channel matrix.")}
    </div>
    <div class="report-section">
      <h4>Cloud Console Shell</h4>
      <div class="muted">${escapeHtml(cloudShell.recommendation)}</div>
      ${renderReportTable(["Area", "Status", "Detail"], cloudShell.sections.map((section) => [
        section.area,
        section.status,
        section.detail
      ]))}
      ${renderReportTable(["Action", "Mode", "Reason"], cloudShell.actions.map((action) => [
        action.action,
        action.mode,
        action.reason
      ]))}
    </div>
    <div class="report-section">
      <h4>Official Ashr Gap</h4>
      <div class="muted">${escapeHtml(officialGap.recommendation)}</div>
      ${renderReportTable(["Official Page", "A3 Status", "MVP Decision"], officialGap.official_pages.map((page) => [
        `${page.page} (${page.path})`,
        page.a3_status,
        page.mvp_decision
      ]))}
    </div>
    <div class="report-section">
      <h4>Official Frontend Mirror</h4>
      <div class="muted">${escapeHtml(officialMirror.available
        ? `${officialMirror.page_count} page(s), ${officialMirror.api_method_count} API method name(s), ${officialMirror.confirmed_label_count} UI label(s). ${officialMirror.clean_room_boundary}`
        : "No official frontend mirror summary is available.")}</div>
      ${renderReportTable(["Page", "A3 Status", "Decision"], officialMirror.pages.map((page) => [
        `${page.label} (${page.tab_id})`,
        page.a3_status,
        page.a3_decision
      ]), "No official page mirror summary.")}
      ${renderReportTable(["API Group", "Methods", "A3 Status"], officialMirror.api_method_groups.map((group) => [
        group.group,
        group.method_count,
        group.a3_status
      ]), "No official API method mirror summary.")}
    </div>
    <div class="report-section">
      <h4>Official Parity Roadmap</h4>
      <div class="muted">${escapeHtml(officialParityRoadmap.recommendation)}</div>
      ${renderReportTable(["Signal", "Value"], [
        ["Official pages observed", officialParityRoadmap.official_pages_observed],
        ["Copy now", officialParityRoadmap.copied_page_count],
        ["Partial", officialParityRoadmap.partial_page_count],
        ["Future", officialParityRoadmap.future_page_count],
        ["Do not copy", officialParityRoadmap.out_of_scope_page_count],
        ["Official blocked gaps", officialParityRoadmap.official_gap_blocked_count]
      ])}
      ${renderReportTable(["Area", "Action", "Note"], officialParityRoadmap.priorities.map((item) => [
        item.area,
        item.action,
        item.note
      ]), "No parity priorities.")}
      ${renderReportTable(["Media Area", "Action", "Note"], officialParityRoadmap.media_actions.map((item) => [
        item.area,
        item.action,
        item.note
      ]), "No media parity actions.")}
    </div>
    <div class="report-section">
      <h4>Failure Clusters</h4>
      ${renderReportTable(["Failure Class", "Cases", "Severity", "Example"], clusters.slice(0, 6).map((cluster) => [
        cluster.failureClass,
        cluster.count,
        cluster.severity,
        cluster.summaries[0] || "No summary."
      ]), "No failure clusters.")}
    </div>
    <div class="report-section">
      <h4>Triage Queue</h4>
      ${renderReportTable(["Case", "Failure", "Severity", "Score"], failedCases.map((item) => [
        `${item.case_id} / ${item.title}`,
        item.primary_failure_class,
        item.severity,
        item.score
      ]), "No failed cases in the current filter.")}
    </div>
    <div class="report-section">
      <h4>Selected Case Evidence</h4>
      ${selected ? `
        <div class="muted">${escapeHtml(selected.case_id)} / ${escapeHtml(selected.scenario_id)} / ${selected.passed ? "PASS" : "FAIL"} / ${escapeHtml(selected.primary_failure_class)}</div>
        ${renderReportTable(["Signal", "Evidence"], [
          ["Summary", selected.failure_summary],
          ["Expected", selected.expected?.summary || formatJson(selected.expected)],
          ["Actual", selected.actual?.final_response || formatJson(selected.actual)]
        ])}
        ${renderReportTable(["Tool Diff", "Judge Evidence"], selectedDiffs.map((diff) => [
          `#${diff.index + 1} ${diff.status}: ${diff.summary}`,
          formatReportJudgeEvidence(diff)
        ]), "No tool-call differences for selected case.")}
      ` : "<div class=\"muted\">No selected case.</div>"}
    </div>
  `;
}

function formatReportJudgeEvidence(diff) {
  const entries = diff.judge_evidence || [];
  if (!entries.length) {
    return "No linked judge evidence.";
  }
  return entries.map((entry) => {
    const traceIds = entry.evidence?.trace_event_ids || [];
    const traceText = traceIds.length ? ` Trace: ${traceIds.join(", ")}` : "";
    return `${entry.judge_mode}: ${entry.summary}.${traceText}`;
  }).join(" | ");
}

function reportMetric(label, value) {
  return `
    <div class="report-metric">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </div>
  `;
}

function renderReportTable(headers, rows, emptyText = "No rows.") {
  if (!rows.length) {
    return `<div class="muted">${escapeHtml(emptyText)}</div>`;
  }
  return `
    <div class="report-table">
      <table>
        <thead>
          <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCaseList() {
  $("visible-count").textContent = `${state.filteredCases.length} visible`;
  if (!state.filteredCases.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No cases match the current filters.";
    $("case-list").replaceChildren(empty);
    return;
  }

  $("case-list").replaceChildren(...state.filteredCases.map((item) => {
    const button = document.createElement("button");
    button.className = `case-row ${item.case_id === state.selectedCaseId ? "active" : ""}`;
    button.type = "button";
    button.addEventListener("click", () => {
      state.selectedCaseId = item.case_id;
      renderCaseList();
      renderTriageQueue();
      renderPrintReport();
      renderDetail();
    });
    button.innerHTML = `
      <div class="case-title">${escapeHtml(item.title)}</div>
      <div class="case-meta">
        <span>${escapeHtml(item.case_id)}</span>
        <span>${escapeHtml(item.scenario_id)}</span>
        <span class="badge ${item.passed ? "pass" : "fail"}">${item.passed ? "PASS" : "FAIL"}</span>
        <span>${escapeHtml(item.primary_failure_class)}</span>
        <span>${escapeHtml(item.severity)}</span>
        <span>${escapeHtml(item.score)}</span>
      </div>
    `;
    return button;
  }));
}

function renderDetail() {
  const item = state.cases.find((candidate) => candidate.case_id === state.selectedCaseId);
  if (!item) {
    $("detail-status").className = "badge neutral";
    $("detail-status").textContent = "No case";
    $("case-heading").textContent = "Select a case to inspect expected vs actual.";
    $("expected-view").textContent = "{}";
    $("actual-view").textContent = "{}";
    $("timeline-view").textContent = "";
    $("judge-view").textContent = "";
    $("tool-diff-view").textContent = "";
    $("media-view").textContent = "";
    return;
  }

  $("detail-status").className = `badge ${item.passed ? "pass" : "fail"}`;
  $("detail-status").textContent = item.passed ? "PASS" : "FAIL";
  $("case-heading").textContent = `${item.case_id} / ${item.scenario_id} - ${item.failure_summary}`;
  $("expected-view").textContent = formatJson(item.expected);
  $("actual-view").textContent = formatJson(item.actual);
  renderToolDiff(item);
  renderMediaEvidence(item);
  $("judge-view").replaceChildren(...(item.judge_results || []).map((judge) => {
    const node = document.createElement("div");
    node.className = "judge";
    const analysis = judge.failure_analysis || {};
    node.innerHTML = `
      <div class="judge-head">
        <strong>${escapeHtml(judge.judge_mode || "judge")}</strong>
        <span class="badge ${judge.passed ? "pass" : "fail"}">${judge.passed ? "PASS" : "FAIL"} ${escapeHtml(judge.score ?? "")}</span>
      </div>
      <div class="muted">${escapeHtml(analysis.primary_failure_class || "none")} / ${escapeHtml(analysis.severity || "none")}</div>
      <div>${escapeHtml(analysis.summary || "No failure analysis summary.")}</div>
    `;
    return node;
  }));

  const events = Array.isArray(item.trace_events) && item.trace_events.length
    ? item.trace_events
    : (item.observations || []).map((obs, index) => ({
      seq: index,
      phase: obs.event_type,
      event_type: obs.event_type,
      source: obs.role,
      observation: {
        kind: obs.event_type,
        channel: obs.role,
        status: obs.status,
        text: obs.content,
        data: { tool_calls: obs.tool_calls }
      }
    }));

  $("timeline-view").replaceChildren(...events.map((event) => {
    const node = document.createElement("div");
    node.className = "event";
    const text = event.observation?.text || "";
    node.innerHTML = `
      <strong>#${escapeHtml(event.seq)} ${escapeHtml(event.event_type)}</strong>
      <span>${escapeHtml(event.phase)} / ${escapeHtml(event.source)} / ${escapeHtml(event.observation?.status || "unknown")}</span>
      <div>${escapeHtml(text)}</div>
    `;
    return node;
  }));
}

function renderClusters() {
  const clusters = clusterFailures(state.runs, state.grades);
  if (!clusters.length) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No failure clusters for the current data source.";
    $("cluster-list").replaceChildren(empty);
    return;
  }
  $("cluster-list").replaceChildren(...clusters.map((cluster) => {
    const node = document.createElement("div");
    node.className = "cluster";
    node.innerHTML = `
      <strong>${escapeHtml(cluster.failureClass)}</strong>
      <div class="muted">${escapeHtml(cluster.count)} case(s), severity ${escapeHtml(cluster.severity)}</div>
      <div>${escapeHtml(cluster.summaries[0] || "No summary.")}</div>
    `;
    return node;
  }));
}

function renderToolDiff(item) {
  const diffs = buildToolCallDiffs(item);
  if (!diffs.length) {
    $("tool-diff-view").innerHTML = `
      <h3>Tool Call Diff</h3>
      <div class="muted">No tool calls were expected or observed for this case.</div>
    `;
    return;
  }

  $("tool-diff-view").innerHTML = `
    <h3>Tool Call Diff</h3>
    <div class="diff-list">
      ${diffs.map((diff) => `
        <div class="diff-row">
          <div class="diff-head">
            <strong>#${diff.index + 1} ${escapeHtml(diff.summary)}</strong>
            <span class="badge ${diff.status === "match" ? "pass" : "fail"}">${escapeHtml(diff.status)}</span>
            <span class="badge neutral">${escapeHtml(toolDiffMatchLabel(diff))}</span>
          </div>
          <div class="diff-grid">
            <div class="diff-box">
              <strong>Expected: ${escapeHtml(diff.expected?.name || "none")}</strong>
              <pre>${escapeHtml(formatJson(diff.expected?.arguments || {}))}</pre>
            </div>
            <div class="diff-box">
              <strong>Actual: ${escapeHtml(diff.actual?.name || "none")}</strong>
              <pre>${escapeHtml(formatJson(diff.actual?.arguments || {}))}</pre>
            </div>
          </div>
          ${renderArgumentDiffs(diff)}
          ${renderJudgeEvidence(diff)}
        </div>
      `).join("")}
    </div>
  `;
}

function toolDiffMatchLabel(diff) {
  const expected = Number.isInteger(diff.expected_index) ? `expected #${diff.expected_index + 1}` : "expected none";
  const actual = Number.isInteger(diff.actual_index) ? `actual #${diff.actual_index + 1}` : "actual none";
  return `${diff.match_strategy || "index"} / ${expected} -> ${actual}`;
}

function renderArgumentDiffs(diff) {
  const rows = diff.argument_diffs || [];
  if (!rows.length) {
    return "";
  }

  return `
    <div class="argument-diff-list">
      <div class="section-kicker">Argument fields</div>
      ${rows.map((row) => `
        <div class="argument-diff-row">
          <div class="argument-diff-head">
            <div><strong>Path</strong> <code>${escapeHtml(row.path)}</code></div>
            <span class="badge warn">${escapeHtml(row.status)}</span>
          </div>
          <div class="argument-value-box"><strong>Expected</strong><span class="argument-value">${escapeHtml(formatDiffValue(row.expected))}</span></div>
          <div class="argument-value-box"><strong>Actual</strong><span class="argument-value">${escapeHtml(formatDiffValue(row.actual))}</span></div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderJudgeEvidence(diff) {
  const entries = diff.judge_evidence || [];
  if (!entries.length) {
    return "";
  }

  return `
    <div class="judge-evidence-list">
      <div class="section-kicker">Judge evidence</div>
      ${entries.map((entry) => `
        <div class="judge-evidence-block">
          <div class="judge-evidence-head">
            <strong>${escapeHtml(entry.judge_mode || "judge")}</strong>
            <span class="badge neutral">${escapeHtml(entry.primary_failure_class || "none")} / ${escapeHtml(entry.severity || "none")} / ${escapeHtml(entry.score ?? "n/a")}</span>
          </div>
          <div>${escapeHtml(entry.summary || "No judge summary.")}</div>
          ${renderEvidenceLines("Tool evidence", entry.evidence?.tool_call_ids || [])}
          ${renderEvidenceLines("Trace events", entry.evidence?.trace_event_ids || [])}
          ${renderEvidenceLines("Details", entry.details || [])}
          ${renderEvidenceLines("Remediation", entry.remediation || [])}
        </div>
      `).join("")}
    </div>
  `;
}

function renderEvidenceLines(label, values) {
  if (!Array.isArray(values) || !values.length) {
    return "";
  }
  return `
    <div class="evidence-lines">
      <strong>${escapeHtml(label)}</strong>
      ${values.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
    </div>
  `;
}

function formatDiffValue(value) {
  if (value === null || value === undefined) {
    return "none";
  }
  if (typeof value === "string") {
    return value;
  }
  return formatJson(value);
}

function renderMediaEvidence(item) {
  const media = item.media_evidence;
  if (!media || !((media.evidence_items || []).length || (media.vm_streams || []).length || (media.media_types || []).length)) {
    $("media-view").innerHTML = `
      <h3>Media Evidence</h3>
      <div class="muted">No image/audio/file/video/VM evidence is attached to this case. For mock fixtures this is expected; switch to the P3 Media Sample to inspect calibrated media fields.</div>
    `;
    return;
  }

  const knownGaps = (media.known_gaps || []).map((item) => `<div class="muted">${escapeHtml(item)}</div>`).join("");
  const evidenceItems = (media.evidence_items || []).map((entry) => `
    <div class="evidence-item">
      <strong>${escapeHtml(entry.type || "evidence")}</strong>
      <div class="muted">${escapeHtml(entry.name || entry.provider || "source")}</div>
      <div>${escapeHtml(entry.output_path || entry.session_id || "no direct media URL")}</div>
    </div>
  `).join("");
  $("media-view").innerHTML = `
    <h3>Media Evidence</h3>
    <div class="case-meta" style="margin-bottom: 8px;">
      <span class="badge neutral">${escapeHtml(media.primary_media_type || "media")}</span>
      <span>${escapeHtml((media.media_types || []).join(", ") || "vm_stream")}</span>
      <span>${escapeHtml((media.vm_streams || []).length)} VM stream(s)</span>
    </div>
    <div class="evidence-grid">${evidenceItems || "<div class=\"muted\">No evidence item details.</div>"}</div>
    ${knownGaps ? `<div style="margin-top: 8px;">${knownGaps}</div>` : ""}
  `;
}

function download(name, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportReport(format) {
  if (format === "json") {
    download("a3-dashboard-report.json", JSON.stringify(buildJsonReport(
      state.runs,
      state.grades,
      state.coverage,
      state.evidenceReadiness,
      state.requestProvenance,
      state.usageQuota,
      state.usageQuotaApiProbe,
      state.mediaSignedUrlCoverage,
      state.authCheck,
      state.frontendSummary,
      state.frontendMirror,
      state.frontendCodeCrawl,
      state.productConsole,
      state.saasAdmin,
      {
        caseBook: state.caseBook,
        regressionReplay: state.regressionReplay,
        commercialReadiness: state.commercialReadiness,
        resultPersistence: state.resultPersistence,
        releaseUnblockChecklist: state.releaseUnblockChecklist,
        releaseGate: state.releaseGate
      },
      state.artifactRegistry,
      state.reviewWorkflow,
      state.releaseEvidence,
      state.githubPublishEvidence,
      state.peerBranchCalibration,
      state.billingMigrationReadiness,
      state.notificationControlPlane
    ), null, 2), "application/json");
    return;
  }
  if (format === "csv") {
    download("a3-dashboard-report.csv", buildCsvReport(state.runs, state.grades), "text/csv");
    return;
  }
  download("a3-dashboard-report.md", buildMarkdownReport(
    state.runs,
    state.grades,
    state.coverage,
    state.evidenceReadiness,
    state.requestProvenance,
    state.usageQuota,
    state.usageQuotaApiProbe,
    state.mediaSignedUrlCoverage,
    state.authCheck,
    state.frontendSummary,
    state.frontendMirror,
    state.frontendCodeCrawl,
    state.productConsole,
    state.saasAdmin,
    {
      caseBook: state.caseBook,
      regressionReplay: state.regressionReplay,
      commercialReadiness: state.commercialReadiness,
      resultPersistence: state.resultPersistence,
      releaseUnblockChecklist: state.releaseUnblockChecklist,
      releaseGate: state.releaseGate
    },
    state.artifactRegistry,
    state.releaseEvidence,
    state.githubPublishEvidence,
    state.peerBranchCalibration,
    state.billingMigrationReadiness,
    state.notificationControlPlane
  ), "text/markdown");
}

async function shareReport() {
  const status = $("share-report-status");
  if (!isA3ApiSource(state.source)) {
    status.className = "badge warn";
    status.textContent = "API required";
    $("share-report-detail").textContent = "Switch Data to API-backed Mock before creating a hosted report link.";
    return;
  }

  status.className = "badge neutral";
  status.textContent = "creating";
  $("share-report-detail").textContent = "Calling the local A3 API and running export redaction before sharing.";
  try {
    const report = await createShareableA3Report({
      source: state.source,
      title: "A3 Release Intelligence Report",
      baseUrl: getA3ApiBaseUrl()
    });
    status.className = `badge ${report.status === "shareable" ? "pass" : "fail"}`;
    status.textContent = report.status;
    $("share-report-detail").textContent = `${report.share_url_path} / ${report.sealed_evidence.hash_algorithm}:${report.sealed_evidence.payload_hash.slice(0, 12)} / ${report.redaction.status}`;
    await refreshReportEvidence();
  } catch (error) {
    status.className = "badge fail";
    status.textContent = "failed";
    $("share-report-detail").textContent = error.message;
    console.error(error);
  }
}

async function revokeHostedReport(report) {
  const status = $("share-report-status");
  if (!isA3ApiSource(state.source)) {
    status.className = "badge warn";
    status.textContent = "API required";
    $("share-report-detail").textContent = "Switch Data to API-backed Mock before revoking a hosted report link.";
    return;
  }
  status.className = "badge neutral";
  status.textContent = "revoking";
  $("share-report-detail").textContent = `Revoking ${report.report_id} and refreshing Report Center evidence.`;
  try {
    const receipt = await revokeShareableA3Report({
      source: state.source,
      baseUrl: getA3ApiBaseUrl(),
      reportId: report.report_id,
      reason: "dashboard_revoke"
    });
    status.className = `badge ${receipt.status === "revoked" ? "pass" : "warn"}`;
    status.textContent = receipt.status;
    $("share-report-detail").textContent = `${receipt.report_id} revoked by ${receipt.revoked_by}; reason ${receipt.reason}.`;
    await refreshReportEvidence();
  } catch (error) {
    status.className = "badge fail";
    status.textContent = "failed";
    $("share-report-detail").textContent = error.message;
    console.error(error);
  }
}

async function submitReviewWorkflowAction(action) {
  if (!isA3ApiSource(state.source)) {
    state.selectedReviewReceipt = {
      schema_version: "a3.review_workflow_receipt.v1",
      record_id: "static_fixture_preview",
      record_type: action,
      status: "api_required",
      accepted: false,
      payload_hash: null,
      review_hash: null,
      real_cloud_mutation_performed: false
    };
    renderReviewerWorkflowBoard();
    return;
  }

  try {
    const base = {
      source: state.source,
      baseUrl: getA3ApiBaseUrl(),
      generatedAt: "2026-07-07T12:00:00.000Z",
      releaseVersion: "local-mock-commercial-gate",
      environment: "staging",
      headSha: "local-demo-head-sha"
    };
    if (action === "waiver") {
      state.selectedReviewReceipt = await submitA3ReviewWaiver({
        ...base,
        record: await loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json")
      });
    } else if (action === "approval") {
      const waiver = await loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json");
      state.selectedReviewReceipt = await submitA3ReviewApproval({
        ...base,
        waiver,
        record: await loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json")
      });
    } else {
      state.selectedReviewReceipt = await submitA3ReviewDenial({
        ...base,
        record: buildDashboardDenialRecord()
      });
    }
    await refreshReviewWorkflowEvidence();
  } catch (error) {
    state.selectedReviewReceipt = {
      schema_version: "a3.review_workflow_receipt.v1",
      record_id: "submit_failed",
      record_type: action,
      status: "failed",
      accepted: false,
      payload_hash: null,
      review_hash: null,
      real_cloud_mutation_performed: false,
      error_message: error.message
    };
    console.error(error);
    renderReviewerWorkflowBoard();
  }
}

function buildDashboardDenialRecord() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  return {
    schema_version: "a3.denial.v1",
    denial_id: `denial-${summary.lastRunId || "local"}-dashboard`,
    decision: "deny_release",
    reason: "Human reviewer keeps this release blocked until failed A1 trace and A2 judge evidence are remediated.",
    release_version: "local-mock-commercial-gate",
    environment: "staging",
    run_id: summary.lastRunId || "run_a3_generated_from_a2_g3",
    head_sha: "local-demo-head-sha",
    reviewer: {
      role: "Safety reviewer",
      name: "Safety reviewer",
      identity_source: "dashboard-demo",
      reviewed_at: "2026-07-07T12:50:00.000Z"
    },
    reviewed_artifacts: [
      {
        id: "a3_dashboard_report",
        path: "apps/dashboard",
        sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      },
      {
        id: "a2_release_gate_report",
        path: "fixtures/a2/results/a2_release_gate_report.json",
        sha256: "2222222222222222222222222222222222222222222222222222222222222222"
      }
    ]
  };
}

async function refreshReviewWorkflowEvidence() {
  state.reviewWorkflow = await fetchA3ReviewWorkflow({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  await refreshReportEvidence();
  renderReviewerWorkflowBoard();
  renderPrintReport();
}

async function refreshReportEvidence() {
  state.reportCenter = await fetchA3ReportCenter({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.artifactRegistry = await fetchA3ArtifactRegistry({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.productConsole = await fetchA3ProductConsole({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.reviewWorkflow = await fetchA3ReviewWorkflow({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.usageLedger = await fetchA3UsageLedger({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.billingReadiness = await fetchA3BillingReadiness({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.billingMigrationReadiness = await fetchA3BillingMigrationReadiness({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.liveWorkflowReadiness = await fetchA3LiveWorkflowReadiness({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.liveOpsControlPlane = await fetchA3LiveOpsControlPlane({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.notificationControlPlane = await fetchA3NotificationControlPlane({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.peerBranchCalibration = await fetchA3PeerBranchCalibration({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.saasRuntime.usage_ledger = state.usageLedger;
  state.saasRuntime.billing_readiness = state.billingReadiness;
  renderReportCenter();
  renderProductConsole();
  renderReviewerWorkflowBoard();
  renderReleaseEvidenceSummary();
  renderBillingMigrationReadiness();
  renderLiveWorkflowReadiness();
  renderLiveOpsControlPlane();
  renderNotificationControlPlane();
  renderPeerBranchCalibration();
  renderSaasRuntime();
  renderPrintReport();
}

async function refreshAdminEvidence() {
  state.saasAdmin = await fetchA3AdminConsole({
    source: state.source,
    baseUrl: getA3ApiBaseUrl()
  });
  state.selectedAdminPlan = (state.saasAdmin.actions || []).find((item) => item.action === state.selectedAdminAction) || state.selectedAdminPlan;
  refreshEnterpriseReadiness();
  await refreshReportEvidence();
  renderSaasAdmin();
  renderEnterpriseReadiness();
}

function printReport() {
  renderPrintReport();
  window.print();
}

function applyApiDashboardPayload(payload) {
  const releaseEvidenceReadbacks = payload.release_evidence_readbacks || {};
  const baseReleaseEvidence = payload.release_evidence || payload.release_evidence_summary || {};
  const readbackRecords = Array.isArray(releaseEvidenceReadbacks.latest_records)
    ? releaseEvidenceReadbacks.latest_records
    : Array.isArray(releaseEvidenceReadbacks.records)
      ? releaseEvidenceReadbacks.records
      : Array.isArray(releaseEvidenceReadbacks.readback_records)
        ? releaseEvidenceReadbacks.readback_records
        : [];
  state.runs = payload.run_fixture || {};
  state.grades = payload.grade_fixture || {};
  state.coverage = payload.coverage || {};
  state.requestProvenance = payload.request_provenance || {};
  state.usageQuota = payload.usage_quota || {};
  state.usageQuotaApiProbe = payload.usage_quota_api_probe || {};
  state.mediaSignedUrlCoverage = payload.media_signed_url_coverage || {};
  state.authCheck = payload.auth_check || {};
  state.frontendSummary = payload.frontend_summary || {};
  state.frontendMirror = payload.frontend_mirror || {};
  state.frontendCodeCrawl = payload.frontend_code_crawl || {};
  state.saasAdmin = payload.saas_admin_console || {};
  state.enterpriseReadiness = payload.enterprise_readiness || {};
  state.productConsole = payload.product_console || {};
  state.usageLedger = payload.usage_ledger || {};
  state.billingReadiness = payload.billing_readiness || {};
  state.billingMigrationReadiness = payload.billing_migration_readiness || {};
  state.liveWorkflowReadiness = payload.live_workflow_readiness || {};
  state.liveOpsControlPlane = payload.live_ops_control_plane || {};
  state.notificationControlPlane = payload.notification_control_plane || {};
  state.reportCenter = payload.report_center || {};
  state.artifactRegistry = payload.artifact_registry || payload.report_center?.artifact_registry || {};
  state.peerBranchCalibration = payload.peer_branch_calibration || {};
  state.reviewWorkflow = payload.review_workflow || {};
  state.releaseEvidenceReadbacks = releaseEvidenceReadbacks;
  state.releaseEvidence = {
    ...baseReleaseEvidence,
    ...(readbackRecords.length ? { readback_records: readbackRecords } : {}),
    readback_history: releaseEvidenceReadbacks.schema_version ? releaseEvidenceReadbacks : baseReleaseEvidence.readback_history,
    readback_record_count: releaseEvidenceReadbacks.readback_count ?? baseReleaseEvidence.readback_record_count,
    readback_status_counts: releaseEvidenceReadbacks.status_counts || baseReleaseEvidence.readback_status_counts,
    readback_resource_counts: releaseEvidenceReadbacks.resource_counts || baseReleaseEvidence.readback_resource_counts
  };
  state.githubPublishEvidence = payload.github_publish_evidence || {};
  state.selectedAdminPlan = (state.saasAdmin.actions || []).find((item) => item.action === state.selectedAdminAction) || null;
  state.saasRuntime = {
    ...(payload.storage || {}),
    source: payload.source,
    source_label: payload.source_label,
    summary: payload.summary,
    event_outbox: payload.event_outbox || {},
    usage_ledger: payload.usage_ledger
      || state.usageLedger,
    billing_readiness: payload.billing_readiness
      || state.billingReadiness
  };
}

function resetSaasRuntime(mode = "static_fixture") {
  state.saasRuntime = {
    mode,
    db_ready: mode !== "static_fixture",
    db_contract: {
      recommended_primary_db: "postgres",
      mysql_compatible: true,
      api_surfaces: [
        "GET /api/a3/dashboard",
        "GET /api/a3/runs",
        "GET /api/a3/cases/:caseId",
        "POST /api/a3/import/a1-run-result",
        "POST /api/a3/import/a2-grade-result",
        "GET /api/a3/enterprise/readiness",
        "GET /api/a3/admin/console",
        "POST /api/a3/admin/actions/plan",
        "POST /api/a3/admin/actions/submit",
        "GET /api/a3/admin/actions",
        "POST /api/a3/review/waivers",
        "POST /api/a3/review/approvals",
        "POST /api/a3/review/denials",
        "GET /api/a3/review/workflow",
        "GET /api/a3/usage/ledger",
        "GET /api/a3/billing/readiness",
        "GET /api/a3/billing/migration-readiness",
        "GET /api/a3/live-workflow/readiness",
        "GET /api/a3/live-ops/control-plane",
        "GET /api/a3/notifications/control-plane",
        "GET /api/a3/peer-branches/calibration",
        "GET /api/a3/product/console",
        "POST /api/a3/reports/share",
        "GET /api/a3/reports/center",
        "GET /api/a3/artifacts/registry"
      ],
      tables: ["organizations", "users", "team_members", "roles", "api_keys", "projects", "runs", "cases", "trace_events", "grade_results", "shareable_reports", "artifact_registry_entries", "artifact_lifecycle_events", "saas_admin_action_requests", "billing_migration_readiness", "live_ops_control_plane", "notification_channels", "notification_deliveries", "webhook_deliveries", "trust_reports"],
      guardrails: [
        "Static mode keeps existing fixtures working.",
        "API mode uses the same A1/A2 normalized fields.",
        "Login, team, API key, usage, and trust controls stay read-only or plan-only until hosted auth exists.",
        "Hosted reports must pass export redaction before sharing."
      ]
    },
    db_migrations: {
      migration_count: 0,
      statements: []
    },
    usage_ledger: state.usageLedger || {},
    billing_readiness: state.billingReadiness || {}
  };
}

function renderSaasRuntime() {
  renderSaasRuntimePanel($("saas-runtime-body"), state.saasRuntime);
}

function refreshLocalSaasAdmin() {
  state.saasAdmin = buildSaasAdminConsole({
    source: state.source,
    runFixture: state.runs,
    gradeFixture: state.grades,
    coverage: state.coverage,
    requestProvenance: state.requestProvenance,
    usageQuota: state.usageQuota,
    usageQuotaApiProbe: state.usageQuotaApiProbe,
    mediaSignedUrlCoverage: state.mediaSignedUrlCoverage,
    authCheck: state.authCheck,
    frontendSummary: state.frontendSummary
  });
  state.selectedAdminPlan = (state.saasAdmin.actions || []).find((item) => item.action === state.selectedAdminAction) || null;
}

function refreshLocalUsageLedger() {
  const summary = buildDashboardSummary(state.runs, state.grades);
  state.usageLedger = {
    schema_version: "a3.usage_ledger.v1",
    status: "local_estimate",
    billing_mutations_enabled: false,
    meters: [
      { meter: "runs", quantity: summary.totalRuns },
      { meter: "cases", quantity: summary.totalCases },
      { meter: "failed_cases", quantity: summary.failed },
      { meter: "media_evidence_cases", quantity: summary.mediaEvidenceCases }
    ]
  };
  state.billingReadiness = buildA3BillingReadiness({
    usageLedger: state.usageLedger,
    adminConsole: state.saasAdmin
  }, {
    source: state.source
  });
  state.saasRuntime.usage_ledger = state.usageLedger;
  state.saasRuntime.billing_readiness = state.billingReadiness;
}

function renderSaasAdmin() {
  renderSaasAdminConsole($("saas-admin-body"), {
    ...state.saasAdmin,
    notification_destinations: (state.notificationControlPlane?.channels || []).map((item) => ({
      label: item.label,
      provider: item.provider,
      status: item.status,
      current_mode: item.current_mode,
      secret_ref_present: false,
      next_action: item.next_action
    })),
    notification_summary: {
      channel_count: state.notificationControlPlane?.summary?.channel_count || 0,
      configured_count: state.notificationControlPlane?.summary?.configured_metadata_count || 0,
      secret_ref_count: 0,
      live_send_enabled: false
    }
  }, {
    selectedAction: state.selectedAdminAction,
    selectedPlan: state.selectedAdminPlan
  });
  const select = document.querySelector("[data-admin-action-select]");
  if (select) {
    select.addEventListener("change", async () => {
      state.selectedAdminAction = select.value;
      state.selectedAdminReceipt = null;
      if (isA3ApiSource(state.source)) {
        try {
          state.selectedAdminPlan = await planA3AdminAction({
            source: state.source,
            action: state.selectedAdminAction,
            baseUrl: getA3ApiBaseUrl()
          });
        } catch (error) {
          state.selectedAdminPlan = {
            action: state.selectedAdminAction,
            mode: "failed",
            enabled: false,
            area: "api",
            risk: "unknown",
            reason: error.message,
            next_step: "Check the local A3 API server."
          };
          console.error(error);
        }
      } else {
        state.selectedAdminPlan = (state.saasAdmin.actions || []).find((item) => item.action === state.selectedAdminAction) || null;
      }
      renderSaasAdmin();
    });
  }
  const submitButton = document.querySelector("[data-admin-action-submit]");
  if (submitButton) {
    submitButton.addEventListener("click", submitAdminActionRequest);
  }
}

async function submitAdminActionRequest() {
  const action = state.selectedAdminAction;
  const plan = state.selectedAdminPlan || {};
  if (!isA3ApiSource(state.source)) {
    state.selectedAdminReceipt = {
      schema_version: "a3.saas_admin_action_receipt.v1",
      request_id: "static_fixture_preview",
      action,
      status: "api_required",
      next_step: "Switch Data to API-backed Mock before recording a durable admin action request."
    };
    state.saasAdmin = {
      ...state.saasAdmin,
      action_requests: [
        ...(state.saasAdmin.action_requests || []),
        {
          request_id: "static_fixture_preview",
          action,
          area: plan.area || "unknown",
          mode: plan.mode || "preview",
          status: "api_required",
          real_cloud_mutation_performed: false,
          next_step: state.selectedAdminReceipt.next_step
        }
      ],
      action_request_summary: {
        ...(state.saasAdmin.action_request_summary || {}),
        request_count: ((state.saasAdmin.action_request_summary || {}).request_count || 0) + 1,
        real_cloud_mutations_performed: false
      }
    };
    renderSaasAdmin();
    renderPrintReport();
    return;
  }

  try {
    state.selectedAdminReceipt = await submitA3AdminAction({
      source: state.source,
      action,
      baseUrl: getA3ApiBaseUrl(),
      reason: "dashboard_admin_request",
      target: {
        mode: plan.mode,
        area: plan.area
      }
    });
    await refreshAdminEvidence();
  } catch (error) {
    state.selectedAdminReceipt = {
      schema_version: "a3.saas_admin_action_receipt.v1",
      request_id: "submit_failed",
      action,
      status: "failed",
      next_step: error.message
    };
    console.error(error);
    renderSaasAdmin();
  }
}

function refreshEnterpriseReadiness() {
  state.enterpriseReadiness = buildEnterpriseReadinessReport({
    runFixture: state.runs,
    gradeFixture: state.grades,
    adminConsole: state.saasAdmin,
    dbContract: state.saasRuntime?.db_contract
  });
}

function renderEnterpriseReadiness() {
  renderEnterpriseReadinessPanel($("enterprise-readiness-body"), state.enterpriseReadiness);
}

function renderSchemaDriftRadar() {
  const radar = state.schemaDriftRadar || {};
  const status = radar.status || "not_attached";
  const statusBadge = $("schema-drift-status");
  statusBadge.textContent = status;
  statusBadge.className = `badge ${status === "compatible" ? "pass" : status === "needs_attention" ? "fail" : "warn"}`;
  const contracts = Array.isArray(radar.contracts) ? radar.contracts : [];
  $("schema-drift-body").innerHTML = `
    <div class="caption">${escapeHtml(radar.a3_action || "A1/A2 schema drift radar is not attached.")}</div>
    <div class="health-grid">
      ${healthTile(radar.contract_count || contracts.length || 0, "contracts")}
      ${healthTile(radar.compatible_count || 0, "compatible")}
      ${healthTile(radar.drift_count || 0, "drift")}
      ${healthTile(radar.missing_count || 0, "missing")}
    </div>
    ${renderReportTable(["Contract", "Lane", "Status", "Hash"], contracts.slice(0, 8).map((item) => [
      item.schema_contract_id,
      item.source_lane,
      item.status,
      item.content_hash ? `${item.content_hash.slice(0, 12)}...` : "missing"
    ]), "No A1/A2 schema radar contracts are loaded.")}
    <div class="caption">Safety: raw schema payload ${radar.safety?.raw_schema_payload_embedded ? "embedded" : "not embedded"}, hashes only ${radar.safety?.schema_hashes_only ? "yes" : "unknown"}.</div>
  `;
}

function renderPeerBranchCalibration() {
  const calibration = summarizeA3PeerBranchCalibration(state.peerBranchCalibration || {});
  const statusBadge = $("peer-branch-status");
  statusBadge.textContent = calibration.status || "watching";
  statusBadge.className = `badge ${calibration.status === "ready_to_consume" ? "pass" : calibration.status === "needs_a3_action" || calibration.status === "unsafe" ? "fail" : "warn"}`;
  $("peer-branch-body").innerHTML = `
    <div class="caption">${escapeHtml(calibration.recommendation)}</div>
    <div class="health-grid">
      ${healthTile(calibration.peer_branch_count || 0, "branches")}
      ${healthTile(calibration.peer_delta_count || 0, "peer deltas")}
      ${healthTile(calibration.blocking_delta_count || 0, "blocking")}
      ${healthTile(calibration.growth_point_count || 0, "growth points")}
    </div>
    ${renderReportTable(["Delta", "Lane", "Surface", "Risk"], (calibration.top_deltas || []).slice(0, 6).map((item) => [
      item.contract || item.delta_id,
      item.owner_lane,
      item.a3_surface,
      item.risk_level
    ]), "No peer branch deltas are loaded.")}
    ${renderReportTable(["Priority", "Surface", "Action"], (calibration.action_items || []).slice(0, 5).map((item) => [
      item.priority,
      item.surface,
      item.action
    ]), "No peer branch actions are pending.")}
    <div class="caption">A1/A2 peer delta evidence is downstream only; A3 does not modify A1 runtime/auth/billing or A2 judge/release semantics.</div>
    <div class="caption">Boundary: ${escapeHtml(calibration.a1_a2_boundary)}</div>
  `;
}

function refreshLiveWorkflowReadiness() {
  state.liveWorkflowReadiness = buildA3LiveWorkflowReadiness({
    source: state.source,
    releaseEvidence: state.releaseEvidence,
    reviewWorkflow: state.reviewWorkflow,
    usageLedger: state.usageLedger,
    billingReadiness: state.billingReadiness,
    reportCenter: state.reportCenter,
    saasAdmin: state.saasAdmin,
    eventOutbox: state.saasRuntime?.event_outbox || {}
  }, {
    source: state.source
  });
}

function refreshBillingMigrationReadiness() {
  state.billingMigrationReadiness = buildA3BillingMigrationReadiness({
    source: state.source,
    organizationId: state.usageLedger?.tenant_scope?.organization_id,
    projectId: state.usageLedger?.tenant_scope?.project_id
  });
}

function renderBillingMigrationReadiness() {
  const readiness = state.billingMigrationReadiness || {};
  const statusBadge = $("billing-migration-status");
  const status = readiness.summary?.status || readiness.status || "checking";
  statusBadge.textContent = status;
  statusBadge.className = `badge ${readiness.summary?.ready_for_live_customer_billing ? "pass" : readiness.schema_version ? "warn" : "neutral"}`;
  const upstream = readiness.upstream_evidence || {};
  const dbTables = Array.isArray(readiness.db_contract?.tables) ? readiness.db_contract.tables : [];
  const apiRoutes = Array.isArray(readiness.api_contract) ? readiness.api_contract : [];
  $("billing-migration-body").innerHTML = `
    <div class="caption">${escapeHtml(readiness.purpose || "Billing migration readiness is not attached.")}</div>
    <div class="health-grid">
      ${healthTile(readiness.summary?.upstream_commit_count || 0, "A1 commits")}
      ${healthTile(dbTables.length, "billing tables")}
      ${healthTile(readiness.summary?.consumed_evidence_count || 0, "evidence inputs")}
      ${healthTile(readiness.summary?.ready_for_live_customer_billing ? "yes" : "no", "live billing")}
    </div>
    ${renderReportTable(["A1 evidence", "Source", "A3 state"], Object.entries(upstream).slice(0, 5).map(([key, item]) => [
      key,
      item.source_commit || item.summary_path || item.fixture_path || "local",
      item.a3_consumption_state || item.status || "mapped"
    ]), "No A1 billing migration evidence is loaded.")}
    ${renderReportTable(["DB table", "Purpose", "Tenant scope"], dbTables.map((table) => [
      table.name,
      table.purpose,
      `${table.tenant_column || "organization_id"} / ${table.project_column || "project_id"}`
    ]), "No billing migration DB tables are mapped.")}
    ${renderReportTable(["API route", "Owner", "Status"], apiRoutes.map((route) => [
      route.route,
      route.owner_lane,
      route.status
    ]), "No billing migration API routes are mapped.")}
    <div class="caption">A3 claim: ${escapeHtml(readiness.summary?.a3_customer_claim || "A3 stays read-only until A1 exposes authenticated billing ledger APIs.")}</div>
  `;
}

function refreshLiveOpsControlPlane() {
  state.liveOpsControlPlane = buildA3LiveOpsControlPlane({
    source: state.source,
    releaseEvidence: state.releaseEvidence,
    reviewWorkflow: state.reviewWorkflow,
    usageLedger: state.usageLedger,
    billingReadiness: state.billingReadiness,
    reportCenter: state.reportCenter,
    eventOutbox: state.saasRuntime?.event_outbox || {},
    liveWorkflowReadiness: state.liveWorkflowReadiness
  }, {
    source: state.source
  });
}

function renderLiveWorkflowReadiness() {
  const readiness = state.liveWorkflowReadiness || {};
  const statusBadge = $("live-workflow-status");
  statusBadge.textContent = readiness.status || "checking";
  statusBadge.className = `badge ${readiness.status === "live_evidence_observed" ? "pass" : readiness.status === "contract_ready_needs_live_credentials" ? "warn" : "neutral"}`;
  const capabilities = Array.isArray(readiness.capabilities) ? readiness.capabilities : [];
  $("live-workflow-body").innerHTML = `
    <div class="caption">${escapeHtml(readiness.commercial_value || "Live workflow readiness is not attached.")}</div>
    <div class="health-grid">
      ${healthTile(readiness.ready_capability_count || 0, "ready capabilities")}
      ${healthTile(readiness.needs_backend_or_credentials_count || 0, "need live backend")}
      ${healthTile(readiness.human_action_count || 0, "human records")}
      ${healthTile(readiness.audit_backed_count || 0, "audit backed")}
    </div>
    ${renderReportTable(["Next capability", "Status", "Dashboard value"], capabilities.map((item) => [
      item.label,
      item.status,
      item.dashboard_value
    ]), "No live workflow readiness capabilities are loaded.")}
    ${renderReportTable(["Next action"], (readiness.next_actions || []).map((item) => [item]), "No live workflow next actions are pending.")}
    <div class="caption">Boundary: ${escapeHtml(readiness.a1_a2_boundary || "A3 keeps live workflow evidence downstream of A1/A2 contracts.")}</div>
  `;
}

function renderLiveOpsControlPlane() {
  const controlPlane = state.liveOpsControlPlane || {};
  const statusBadge = $("live-ops-status");
  statusBadge.textContent = controlPlane.status || "checking";
  statusBadge.className = `badge ${controlPlane.status === "live_mutation_observed" || controlPlane.status === "control_plane_ready_needs_live_workers" ? "pass" : controlPlane.status === "needs_contracts" ? "warn" : "neutral"}`;
  const lanes = Array.isArray(controlPlane.lanes) ? controlPlane.lanes : [];
  const counts = controlPlane.counts || {};
  const human = controlPlane.human_operation_summary || {};
  const billing = controlPlane.billing_state_summary || {};
  const share = controlPlane.report_link_summary || {};
  $("live-ops-body").innerHTML = `
    <div class="caption">Six live SaaS workflows are tracked as API, DB, event, audit, and dashboard contracts. A3 keeps them safe until A1 hosted workers and A2 release policy are ready.</div>
    <div class="health-grid">
      ${healthTile(counts.lane_count || 0, "ops lanes")}
      ${healthTile(counts.api_backed_count || 0, "API-backed")}
      ${healthTile(counts.audit_backed_count || 0, "audit-backed")}
      ${healthTile(counts.local_external_mutation_count || 0, "local mutations")}
    </div>
    ${renderReportTable(["Workflow", "Surface", "Status", "Mode", "Next action"], lanes.map((item) => [
      item.label,
      item.product_surface,
      item.status,
      item.current_mode,
      item.next_action
    ]), "No live ops control-plane lanes are loaded.")}
    ${renderReportTable(["Summary", "Value"], [
      ["Human records", `${human.review_record_count || 0} review / ${human.event_outbox_count || 0} outbox`],
      ["Reviewer decisions", `${human.approval_count || 0} approve / ${human.denial_count || 0} deny / ${human.waiver_count || 0} waiver`],
      ["Billing state", `${billing.billing_readiness_status || "unknown"} / ${billing.meter_count || 0} meter(s)`],
      ["Share links", `${share.shareable_count || 0} shareable / ${share.revoked_count || 0} revoked / ${share.expired_count || 0} expired / ${share.total_view_count || 0} view(s)`]
    ])}
    ${renderReportTable(["Reviewer timeline", "Status", "Reason"], (controlPlane.reviewer_timeline || []).map((item) => [
      `${item.record_type} / ${item.actor_hash}` ,
      item.status,
      item.reason
    ]), "No reviewer timeline has been recorded yet.")}
    ${renderReportTable(["GitHub publish step", "Status", "Target"], (controlPlane.github_publish_timeline || []).map((item) => [
      `${item.step}${item.dry_run ? " (dry-run)" : ""}`,
      item.status,
      item.target
    ]), "No GitHub publish timeline is loaded.")}
    ${renderReportTable(["Share-link lifecycle", "Status", "Detail"], (controlPlane.share_link_timeline || []).map((item) => [
      item.timeline_id,
      item.status,
      `views ${item.view_count || 0} / expires ${item.expires_at || "n/a"} / revoked ${item.revoked_at || "n/a"}`
    ]), "No hosted report lifecycle history is loaded.")}
    ${renderReportTable(["Audit history", "Status"], (controlPlane.audit_history || []).map((item) => [
      item.event_type,
      item.status
    ]), "No audit history is visible yet.")}
    <div class="caption">A1: ${escapeHtml(controlPlane.a1_a2_alignment?.a1_consumed_contracts?.join(", ") || "usage, GitHub worker, billing ledger")}</div>
    <div class="caption">A2: ${escapeHtml(controlPlane.a1_a2_alignment?.a2_consumed_contracts?.join(", ") || "grade, release gate, failure taxonomy")}</div>
  `;
}

function refreshNotificationControlPlane() {
  state.notificationControlPlane = buildA3NotificationControlPlane({
    source: state.source,
    releaseEvidence: state.releaseEvidence,
    liveOpsControlPlane: state.liveOpsControlPlane,
    reviewWorkflow: state.reviewWorkflow,
    eventOutbox: state.saasRuntime?.event_outbox || {},
    reportCenter: state.reportCenter,
    usageLedger: state.usageLedger
  }, {
    source: state.source
  });
}

function renderNotificationControlPlane() {
  const controlPlane = state.notificationControlPlane || {};
  const statusBadge = $("notification-status");
  statusBadge.textContent = controlPlane.status || "checking";
  statusBadge.className = `badge ${String(controlPlane.status || "").includes("contract_ready") ? "pass" : String(controlPlane.status || "").includes("metadata_present") ? "warn" : "neutral"}`;
  renderNotificationControlPlanePanel($("notification-body"), controlPlane);
}

function refreshLocalProductConsole() {
  state.productConsole = buildA3ProductConsole({
    source: state.source,
    runFixture: state.runs,
    gradeFixture: state.grades,
    usageLedger: state.usageLedger,
    reviewWorkflow: state.reviewWorkflow || {},
    notificationControlPlane: state.notificationControlPlane || {}
  }, {
    source: state.source,
    usageLedger: state.usageLedger,
    reportCenter: state.reportCenter || {},
    reviewWorkflow: state.reviewWorkflow || {},
    notificationControlPlane: state.notificationControlPlane || {},
    auditEvents: [],
    importReceipts: []
  });
}

function refreshLocalArtifactRegistry() {
  state.artifactRegistry = buildA3ArtifactRegistry({
    source: state.source,
    reportCenter: state.reportCenter || {},
    usageLedger: state.usageLedger || {},
    productConsole: state.productConsole || {},
    saasAdmin: state.saasAdmin || {},
    githubPublishEvidence: state.githubPublishEvidence || {},
    notificationControlPlane: state.notificationControlPlane || {}
  }, {
    source: state.source
  });
}

function renderProductConsole() {
  renderProductConsolePanel($("product-console-body"), state.productConsole);
}

async function loadDataSource(source) {
  state.source = source;
  if (isA3ApiSource(source)) {
    applyApiDashboardPayload(await fetchA3DashboardSnapshot({ source, baseUrl: getA3ApiBaseUrl() }));
    try {
      state.schemaDriftRadar = await fetchA3SchemaDriftRadar({ source, baseUrl: getA3ApiBaseUrl() });
    } catch (error) {
      state.schemaDriftRadar = {
        schema_version: "a3.schema_drift_dashboard_state.v1",
        status: "unavailable",
        a3_action: error.message,
        safety: {
          raw_schema_payload_embedded: false,
          raw_secret_values_allowed: false
        }
      };
    }
    try {
      state.peerBranchCalibration = await fetchA3PeerBranchCalibration({ source, baseUrl: getA3ApiBaseUrl() });
    } catch (error) {
      state.peerBranchCalibration = {
        schema_version: "a3.peer_branch_calibration.v1",
        source: "api_error",
        peer_deltas: [],
        growth_points: [{
          id: "PBC-API-ERROR",
          title: error.message,
          surface: "api_platform",
          expected_artifact: "peer branch calibration API error",
          money_grade_reason: "A3 should fail visible when peer calibration cannot load."
        }]
      };
    }
    const [usageLedgerResult, billingReadinessResult, billingMigrationResult, liveWorkflowResult, liveOpsResult, notificationResult] = await Promise.allSettled([
      fetchA3UsageLedger({ source, baseUrl: getA3ApiBaseUrl() }),
      fetchA3BillingReadiness({ source, baseUrl: getA3ApiBaseUrl() }),
      fetchA3BillingMigrationReadiness({ source, baseUrl: getA3ApiBaseUrl() }),
      fetchA3LiveWorkflowReadiness({ source, baseUrl: getA3ApiBaseUrl() }),
      fetchA3LiveOpsControlPlane({ source, baseUrl: getA3ApiBaseUrl() }),
      fetchA3NotificationControlPlane({ source, baseUrl: getA3ApiBaseUrl() })
    ]);
    if (usageLedgerResult.status === "fulfilled") {
      state.usageLedger = usageLedgerResult.value;
    }
    if (billingReadinessResult.status === "fulfilled") {
      state.billingReadiness = billingReadinessResult.value;
    }
    if (billingMigrationResult.status === "fulfilled") {
      state.billingMigrationReadiness = billingMigrationResult.value;
    }
    if (liveWorkflowResult.status === "fulfilled") {
      state.liveWorkflowReadiness = liveWorkflowResult.value;
    }
    if (liveOpsResult.status === "fulfilled") {
      state.liveOpsControlPlane = liveOpsResult.value;
    }
    if (notificationResult.status === "fulfilled") {
      state.notificationControlPlane = notificationResult.value;
    }
    state.saasRuntime.usage_ledger = state.usageLedger;
    state.saasRuntime.billing_readiness = state.billingReadiness;
  } else if (source === "p3-media") {
    const sample = await loadJson("../../fixtures/a3/p3/ashr_run_detail_sample.redacted.json");
    const datasetSample = await loadOptionalJson("../../fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json");
    state.requestProvenance = await loadOptionalJson("../../fixtures/a3/p3/ashr_request_detail_sample.redacted.json");
    state.usageQuota = await loadOptionalJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
    state.usageQuotaApiProbe = await loadOptionalJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
    state.mediaSignedUrlCoverage = await loadOptionalJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
    state.authCheck = await loadOptionalJson("../../fixtures/a3/p3/ashr_auth_check.redacted.json");
    state.frontendSummary = await loadOptionalJson("../../fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json");
    const mapped = mapAshrSampleToA3Fixtures(sample, {
      fixtureId: "p3_ashr_media_dashboard_sample",
      gradeFixtureId: "p3_ashr_media_dashboard_grades",
      datasetSample
    });
    state.runs = mapped.runFixture;
    state.grades = mapped.gradeFixture;
  } else if (source === "p3-official-demo") {
    const sample = await loadJson("../../fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json");
    const datasetSample = await loadOptionalJson("../../fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json");
    state.requestProvenance = await loadOptionalJson("../../fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json");
    state.usageQuota = await loadOptionalJson("../../fixtures/a3/p3/ashr_usage_quota_sample.redacted.json");
    state.usageQuotaApiProbe = await loadOptionalJson("../../fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json");
    state.mediaSignedUrlCoverage = await loadOptionalJson("../../fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json");
    state.authCheck = await loadOptionalJson("../../fixtures/a3/p3/ashr_auth_check.redacted.json");
    state.frontendSummary = await loadOptionalJson("../../fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json");
    const mapped = mapAshrSampleToA3Fixtures(sample, {
      fixtureId: "p3_official_demo_884_11926_dashboard_sample",
      gradeFixtureId: "p3_official_demo_884_11926_dashboard_grades",
      datasetSample
    });
    state.runs = mapped.runFixture;
    state.grades = mapped.gradeFixture;
  } else if (source === "raw-a1") {
    state.runs = await loadJson("../../docs/a1/evidence/local_run_30.json");
    state.grades = {};
    resetCalibrationState();
  } else if (source === "raw-a2") {
    state.runs = await loadJson("../../fixtures/a2/runs/a2_s004_missing_tool.json");
    state.grades = await loadJson("../../fixtures/a2/results/a2_s004_missing_tool_grade.json");
    resetCalibrationState();
  } else {
    state.runs = await loadJson("../../fixtures/a3/mock_run_results.json");
    state.grades = await loadJson("../../fixtures/a3/mock_grade_results.json");
    resetCalibrationState();
  }
  if (!isA3ApiSource(source)) {
    resetSaasRuntime("static_fixture");
    state.frontendMirror = await loadOptionalJson("../../fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json");
    state.frontendCodeCrawl = await loadOptionalJson("../../fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json");
    state.coverage = await loadOptionalJson("../../fixtures/a2/results/a2_g3_coverage_report.json");
    state.evidenceReadiness = await loadOptionalJson("../../fixtures/a2/results/a2_evidence_readiness_report.json");
    state.caseBook = await loadOptionalJson("../../fixtures/a2/results/a2_case_book.json");
    state.regressionReplay = await loadOptionalJson("../../fixtures/a2/results/a2_regression_replay_report.json");
    state.commercialReadiness = await loadOptionalJson("../../fixtures/a2/results/a2_commercial_readiness_report.json");
    state.resultPersistence = await loadOptionalJson("../../fixtures/a2/results/a2_result_persistence_manifest.json");
    state.releaseUnblockChecklist = await loadOptionalJson("../../fixtures/a2/results/a2_release_unblock_checklist.json");
    state.releaseGate = await loadOptionalJson("../../fixtures/a2/results/a2_release_gate_report.json");
    state.peerBranchCalibration = await loadOptionalJson("../../fixtures/a3/p3/a3_peer_branch_calibration.redacted.json");
    state.releaseEvidence = await loadReleaseEvidenceFixtures();
    state.githubPublishEvidence = await loadGithubPublishEvidenceFixtures();
    refreshLocalSaasAdmin();
    refreshLocalUsageLedger();
    refreshLocalProductConsole();
    refreshBillingMigrationReadiness();
    refreshLiveWorkflowReadiness();
    refreshLiveOpsControlPlane();
    refreshNotificationControlPlane();
    refreshLocalArtifactRegistry();
  }
  refreshEnterpriseReadiness();
  state.cases = normalizeCases(state.runs, state.grades);
  state.filteredCases = state.cases;
  state.selectedCaseId = state.cases[0]?.case_id || null;

  const filterOptions = getFilterOptions(state.cases);
  fillSelect("filter-family", filterOptions.families);
  fillSelect("filter-failure", filterOptions.failureClasses);
  fillSelect("filter-run", filterOptions.runIds);
  fillSelect("filter-severity", filterOptions.severities);
  fillSelect("filter-score", filterOptions.scoreBands);
  fillSelect("filter-judge", filterOptions.judgeModes);
  for (const id of ["filter-status", "filter-family", "filter-failure", "filter-run", "filter-severity", "filter-score", "filter-judge"]) {
    $(id).value = "all";
  }

  renderSummary();
  renderConsoleStats();
  renderSaasRuntime();
  renderSaasAdmin();
  renderEnterpriseReadiness();
  renderSchemaDriftRadar();
  renderPeerBranchCalibration();
  renderBillingMigrationReadiness();
  renderLiveWorkflowReadiness();
  renderLiveOpsControlPlane();
  renderNotificationControlPlane();
  renderProductConsole();
  renderCoverageHealth();
  renderReleaseGate();
  renderReleaseWarRoom();
  renderIncidentReplayQueue();
  renderObservabilityReplayMatrix();
  renderRegressionFactory();
  renderReviewerWorkflowBoard();
  renderReleaseWorkflow();
  renderReleaseEvidenceSummary();
  renderReportCenter();
  renderExportRedactionFirewall();
  renderTriageQueue();
  renderCaseList();
  renderPrintReport();
  renderDetail();
  renderClusters();
}

async function loadGithubPublishEvidenceFixtures() {
  const [checkPublish, prCommentPublish, requiredCheckPlan] = await Promise.all([
    loadOptionalJson("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
    loadOptionalJson("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
    loadOptionalJson("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json")
  ]);
  return {
    schema_version: "a3.github_publish_evidence.v1",
    check_publish: checkPublish,
    pr_comment_publish: prCommentPublish,
    required_check_plan: requiredCheckPlan
  };
}

function getA3ApiBaseUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("apiBase") || window.A3_API_BASE_URL || "";
}

function resetCalibrationState() {
  state.requestProvenance = {};
  state.usageQuota = {};
  state.usageQuotaApiProbe = {};
  state.mediaSignedUrlCoverage = {};
  state.authCheck = {};
  state.frontendSummary = {};
  state.evidenceReadiness = {};
  state.caseBook = {};
  state.regressionReplay = {};
  state.commercialReadiness = {};
  state.resultPersistence = {};
  state.releaseUnblockChecklist = {};
  state.releaseGate = {};
  state.reportCenter = {};
  state.artifactRegistry = {};
  state.reviewWorkflow = {};
  state.billingReadiness = {};
  state.billingMigrationReadiness = {};
  state.liveWorkflowReadiness = {};
  state.liveOpsControlPlane = {};
  state.peerBranchCalibration = {};
  state.releaseEvidence = {};
  state.releaseEvidenceReadbacks = {};
  state.githubPublishEvidence = {};
  resetSchemaDriftRadar();
}

function resetSchemaDriftRadar() {
  state.schemaDriftRadar = {
    schema_version: "a3.schema_drift_dashboard_state.v1",
    status: "not_attached",
    contract_count: 0,
    compatible_count: 0,
    drift_count: 0,
    missing_count: 0,
    contracts: [],
    a3_action: "Use API-backed mode to read the RBAC-protected A1/A2 schema drift radar.",
    safety: {
      raw_schema_payload_embedded: false,
      schema_hashes_only: true,
      raw_secret_values_allowed: false
    }
  };
}

function setupSectionNavigation() {
  const navLinks = [...document.querySelectorAll(visualNavigationSelector)];
  const sections = [...new Set(navLinks
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean))];
  let navigationLockUntil = 0;

  const setActiveLink = (id) => {
    for (const link of navLinks) {
      link.classList.toggle("active", link.getAttribute("href") === `#${id}`);
    }
    syncExpandedNavigation(id);
  };

  const focusSection = (section) => {
    section.classList.remove("section-focus");
    window.requestAnimationFrame(() => section.classList.add("section-focus"));
  };

  for (const link of navLinks) {
    link.addEventListener("click", () => {
      const section = document.querySelector(link.getAttribute("href"));
      if (!section) return;
      navigationLockUntil = Date.now() + 750;
      setActiveLink(section.id);
      focusSection(section);
    });
  }

  if (!("IntersectionObserver" in window)) return;

  const observer = new IntersectionObserver((entries) => {
    if (Date.now() < navigationLockUntil) return;
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible?.target?.id) {
      setActiveLink(visible.target.id);
    }
  }, {
    rootMargin: "-20% 0px -65% 0px",
    threshold: [0.2, 0.45, 0.7]
  });

  for (const section of sections) {
    observer.observe(section);
  }

  const initialHash = window.location.hash.slice(1);
  if (initialHash && sections.some((section) => section.id === initialHash)) {
    setActiveLink(initialHash);
  }

  window.addEventListener("hashchange", () => {
    const id = window.location.hash.slice(1);
    const section = sections.find((item) => item.id === id);
    if (!section) return;
    setActiveLink(id);
    focusSection(section);
  });
}

function syncExpandedNavigation(id) {
  const targetHref = `#${id}`;
  for (const group of document.querySelectorAll(".nav-group")) {
    const containsTarget = Boolean(group.querySelector(`a[href="${targetHref}"]`));
    group.classList.toggle("expanded", containsTarget);
  }
}

async function init() {
  setupVisualShell();
  const initParams = new URLSearchParams(window.location.search);
  state.reviewFilter = {
    releaseVersion: initParams.get("reviewRelease") || "",
    environment: initParams.get("reviewEnv") || "",
    actorHash: initParams.get("reviewActor") || ""
  };
  const initialSource = initParams.get("source") || "mock";
  const allowedSources = new Set(["mock", "api-mock", "raw-a1", "raw-a2", "p3-media", "p3-official-demo"]);
  $("source-select").value = allowedSources.has(initialSource) ? initialSource : "mock";
  await loadDataSource($("source-select").value);

  for (const id of ["filter-status", "filter-family", "filter-failure", "filter-run", "filter-severity", "filter-score", "filter-judge"]) {
    $(id).addEventListener("change", applyFilters);
  }

  $("source-select").addEventListener("change", async () => {
    try {
      await loadDataSource($("source-select").value);
    } catch (error) {
      $("data-source").textContent = error.message;
      console.error(error);
    }
  });

  for (const button of document.querySelectorAll("[data-export]")) {
    button.addEventListener("click", () => exportReport(button.dataset.export));
  }
  for (const button of document.querySelectorAll("[data-share-report]")) {
    button.addEventListener("click", shareReport);
  }
  for (const button of document.querySelectorAll("[data-print]")) {
    button.addEventListener("click", printReport);
  }

  setupSectionNavigation();
}

init().catch((error) => {
  $("data-source").textContent = error.message;
  console.error(error);
});




























