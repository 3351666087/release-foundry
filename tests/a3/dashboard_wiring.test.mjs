import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadDashboardHtml() {
  const [html, app, styles] = await Promise.all([
    readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/app.mjs", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/styles.css", import.meta.url), "utf8")
  ]);
  return [html, app, styles].join("\n");
}

test("A3 dashboard is split into a webapp shell, module, and stylesheet", async () => {
  const html = await loadDashboardHtml();
  const indexHtml = await readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8");

  assert.match(indexHtml, /<link rel="stylesheet" href="\.\/src\/styles\.css" \/>/);
  assert.match(indexHtml, /<script type="module" src="\.\/src\/app\.mjs"><\/script>/);
  assert.doesNotMatch(indexHtml, /<style>/);
  assert.doesNotMatch(indexHtml, /<script type="module">\s*import/);
  assert.match(html, /from "\.\.\/\.\.\/\.\.\/services\/report\/report_builder\.mjs"/);
});

test("A3 dashboard wires optional A2 coverage into JSON and Markdown exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /coverage: \{\}/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_g3_coverage_report\.json"\)/);
  assert.match(html, /buildJsonReport\(/);
  assert.match(html, /buildMarkdownReport\(/);
  assert.match(html, /state\.mediaSignedUrlCoverage/);
  assert.match(html, /state\.authCheck/);
  assert.match(html, /state\.frontendSummary/);
  assert.match(html, /state\.frontendMirror/);
  assert.match(html, /buildCsvReport\(state\.runs, state\.grades\)/);
});

test("A3 dashboard wires product-console operations panels", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeCoverage/);
  assert.match(html, /id="operations"/);
  assert.match(html, /id="coverage-status"/);
  assert.match(html, /id="coverage-grid"/);
  assert.match(html, /id="triage-queue"/);
  assert.match(html, /id="report-center"/);
  assert.match(html, /function renderCoverageHealth\(\)/);
  assert.match(html, /function renderTriageQueue\(\)/);
  assert.match(html, /function renderReportCenter\(\)/);
  assert.match(html, /querySelectorAll\("\[data-export\]"\)/);
});

test("A3 dashboard wires judge-mode filtering", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="filter-judge"/);
  assert.match(html, /label for="filter-judge">Judge Mode/);
  assert.match(html, /fillSelect\("filter-judge", filterOptions\.judgeModes\)/);
  assert.match(html, /judgeMode/);
  assert.match(html, /"filter-status", "filter-family", "filter-failure", "filter-run", "filter-severity", "filter-score", "filter-judge"/);
});

test("A3 dashboard passes P3 dataset sample into mapper", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /ashr_dataset_detail_sample\.redacted\.json/);
  assert.match(html, /const datasetSample = await loadOptionalJson/);
  assert.match(html, /datasetSample/);
});

test("A3 dashboard wires official generated demo dataset 884 and run 11926 source", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /value="p3-official-demo"/);
  assert.match(html, /P3 Official Demo 884\/11926/);
  assert.match(html, /ashr_dataset_884_run_11926_ui_tests_detail\.redacted\.json/);
  assert.match(html, /ashr_after_generate_dataset_884\.redacted\.json/);
  assert.match(html, /ashr_after_generate_frontend_summary\.redacted\.json/);
  assert.match(html, /p3_official_demo_884_11926_dashboard_sample/);
  assert.match(html, /allowedSources = new Set\(\["mock", "api-mock", "raw-a1", "raw-a2", "p3-media", "p3-official-demo"\]\)/);
  assert.match(html, /P3 official Ashr demo dataset 884 \/ run 11926/);
});

test("A3 dashboard wires raw A1 and raw A2 source options into the webapp", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /value="raw-a1"/);
  assert.match(html, /Raw A1 RunResult/);
  assert.match(html, /value="raw-a2"/);
  assert.match(html, /Raw A2 Single Case/);
  assert.match(html, /docs\/a1\/evidence\/local_run_30\.json/);
  assert.match(html, /fixtures\/a2\/runs\/a2_s004_missing_tool\.json/);
  assert.match(html, /fixtures\/a2\/results\/a2_s004_missing_tool_grade\.json/);
  assert.match(html, /Raw A1 RunResult fixture/);
  assert.match(html, /Raw A2 single-case fixture/);
  assert.match(html, /function resetCalibrationState\(\)/);
});

test("A3 dashboard wires field-level argument diff rendering", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /argument-diff-row/);
  assert.match(html, /function renderArgumentDiffs\(diff\)/);
  assert.match(html, /diff\.argument_diffs/);
  assert.match(html, /Argument fields/);
  assert.match(html, /formatDiffValue/);
});

test("A3 dashboard wires judge evidence under tool diffs", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /judge-evidence-list/);
  assert.match(html, /function renderJudgeEvidence\(diff\)/);
  assert.match(html, /diff\.judge_evidence/);
  assert.match(html, /Judge evidence/);
  assert.match(html, /Trace events/);
  assert.match(html, /trace_event_ids/);
  assert.match(html, /renderEvidenceLines/);
});

test("A3 dashboard shows tool-call matching strategy", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /function toolDiffMatchLabel\(diff\)/);
  assert.match(html, /diff\.match_strategy/);
  assert.match(html, /expected #/);
  assert.match(html, /actual #/);
});

test("A3 dashboard wires print-ready report preview", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="report-preview"/);
  assert.match(html, /id="print-report"/);
  assert.match(html, /data-print/);
  assert.match(html, /@media print/);
  assert.match(html, /function renderPrintReport\(\)/);
  assert.match(html, /function printReport\(\)/);
  assert.match(html, /window\.print\(\)/);
  assert.match(html, /renderReportTable/);
  assert.match(html, /Report Preview/);
});

test("A3 dashboard wires P3 request provenance into console and exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeRequestProvenance/);
  assert.match(html, /id="request-status"/);
  assert.match(html, /id="request-provenance"/);
  assert.match(html, /function renderRequestProvenance\(\)/);
  assert.match(html, /ashr_request_detail_sample\.redacted\.json/);
  assert.match(html, /state\.requestProvenance/);
  assert.match(html, /state\.requestProvenance,\s*state\.usageQuota,\s*state\.usageQuotaApiProbe,\s*state\.mediaSignedUrlCoverage/s);
  assert.match(html, /Request Provenance/);
});

test("A3 dashboard wires Usage / Quota calibration into console and exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeUsageQuota/);
  assert.match(html, /id="usage-quota-list"/);
  assert.match(html, /function renderUsageQuota\(summary\)/);
  assert.match(html, /ashr_usage_quota_sample\.redacted\.json/);
  assert.match(html, /ashr_usage_quota_api_probe\.redacted\.json/);
  assert.match(html, /state\.usageQuota/);
  assert.match(html, /state\.usageQuotaApiProbe/);
  assert.match(html, /OAuth-gated/);
});

test("A3 dashboard wires official Ashr gap map into console and print report", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeOfficialAshrGap/);
  assert.match(html, /href="#official-gap"/);
  assert.match(html, /id="official-gap"/);
  assert.match(html, /Official Ashr Gap/);
  assert.match(html, /id="official-gap-summary"/);
  assert.match(html, /id="official-gap-counts"/);
  assert.match(html, /id="official-gap-list"/);
  assert.match(html, /gap-row/);
  assert.match(html, /function gapRow\(page\)/);
  assert.match(html, /read-only map/);
  assert.match(html, /officialGap\.official_pages/);
});

test("A3 dashboard wires official frontend mirror into console and exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeOfficialFrontendMirror/);
  assert.match(html, /href="#official-mirror"/);
  assert.match(html, /id="official-mirror"/);
  assert.match(html, /Official Frontend Mirror/);
  assert.match(html, /clean-room/);
  assert.match(html, /id="official-mirror-summary"/);
  assert.match(html, /id="official-mirror-counts"/);
  assert.match(html, /id="official-mirror-pages"/);
  assert.match(html, /id="official-mirror-api"/);
  assert.match(html, /function renderOfficialFrontendMirror\(\)/);
  assert.match(html, /function mirrorPageRow\(page\)/);
  assert.match(html, /function mirrorApiRow\(group\)/);
  assert.match(html, /ashr_frontend_mirror_summary\.redacted\.json/);
  assert.match(html, /state\.frontendMirror = await loadOptionalJson/);
  assert.match(html, /state\.frontendSummary,\s*state\.frontendMirror/s);
  assert.match(html, /officialMirror\.api_method_groups/);
});

test("A3 dashboard wires official code crawl parity into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeOfficialCodeCrawlParity/);
  assert.match(html, /href="#official-code-crawl"/);
  assert.match(html, /id="official-code-crawl"/);
  assert.match(html, /Official Code Crawl/);
  assert.match(html, /id="official-code-crawl-summary"/);
  assert.match(html, /id="official-code-crawl-counts"/);
  assert.match(html, /id="official-code-crawl-chunks"/);
  assert.match(html, /id="official-code-crawl-targets"/);
  assert.match(html, /function renderOfficialCodeCrawlParity\(\)/);
  assert.match(html, /function codeCrawlChunkRow\(chunk\)/);
  assert.match(html, /function codeCrawlTargetRow\(target\)/);
  assert.match(html, /ashr_frontend_code_crawl_summary\.redacted\.json/);
  assert.match(html, /state\.frontendCodeCrawl = await loadOptionalJson/);
  assert.match(html, /state\.frontendMirror,\s*state\.frontendCodeCrawl/s);
  assert.match(html, /renderOfficialCodeCrawlParity\(\)/);
  assert.match(html, /officialCodeCrawl\.available/);
  assert.match(html, /Official Code Crawl Parity<\/h4>/);
});

test("A3 dashboard wires official parity roadmap into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeOfficialParityRoadmap/);
  assert.match(html, /href="#official-roadmap"/);
  assert.match(html, /id="official-roadmap"/);
  assert.match(html, /Official Parity Roadmap/);
  assert.match(html, /id="official-roadmap-summary"/);
  assert.match(html, /id="official-roadmap-counts"/);
  assert.match(html, /id="official-roadmap-priorities"/);
  assert.match(html, /id="official-roadmap-media"/);
  assert.match(html, /id="official-roadmap-next"/);
  assert.match(html, /function renderOfficialParityRoadmap\(\)/);
  assert.match(html, /function roadmapActionRow\(item\)/);
  assert.match(html, /function roadmapNextRow\(index, item\)/);
  assert.match(html, /renderOfficialParityRoadmap\(\)/);
  assert.match(html, /officialParityRoadmap\.recommendation/);
  assert.match(html, /Official Parity Roadmap<\/h4>/);
});

test("A3 dashboard wires commercial release gate into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeReleaseGate/);
  assert.match(html, /summarizeReleaseWorkflow/);
  assert.match(html, /href="#release-gate"/);
  assert.match(html, /href="#pr-gate"/);
  assert.match(html, /id="release-gate"/);
  assert.match(html, /id="pr-gate"/);
  assert.match(html, /Release Gate/);
  assert.match(html, /PR Gate & Audit/);
  assert.match(html, /id="release-gate-status"/);
  assert.match(html, /id="release-gate-metrics"/);
  assert.match(html, /id="release-gate-checks"/);
  assert.match(html, /id="release-gate-blockers"/);
  assert.match(html, /id="pr-gate-status"/);
  assert.match(html, /id="pr-gate-metrics"/);
  assert.match(html, /id="pr-gate-review"/);
  assert.match(html, /id="audit-bundle-list"/);
  assert.match(html, /function renderReleaseGate\(\)/);
  assert.match(html, /function renderReleaseWorkflow\(\)/);
  assert.match(html, /renderReleaseGate\(\)/);
  assert.match(html, /renderReleaseWorkflow\(\)/);
  assert.match(html, /releaseGate\.decision_label/);
  assert.match(html, /releaseWorkflow\.github_check\.name/);
  assert.match(html, /workflow\.waiver_policy\.guidance/);
  assert.match(html, /function auditArtifactRow\(artifact\)/);
  assert.match(html, /Required approvers/);
  assert.match(html, /Blocks merge/);
  assert.match(html, /PR Gate & Audit Workflow/);
});

test("A3 dashboard wires release war room into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeReleaseWarRoom/);
  assert.match(html, /href="#war-room"/);
  assert.match(html, /id="war-room"/);
  assert.match(html, /Release War Room/);
  assert.match(html, /id="war-room-status"/);
  assert.match(html, /id="war-room-summary"/);
  assert.match(html, /id="war-room-metrics"/);
  assert.match(html, /id="war-room-brief"/);
  assert.match(html, /id="war-room-lanes"/);
  assert.match(html, /function renderReleaseWarRoom\(\)/);
  assert.match(html, /function warRoomLaneRow\(lane\)/);
  assert.match(html, /renderReleaseWarRoom\(\)/);
  assert.match(html, /releaseWarRoom\.decision_label/);
  assert.match(html, /Release War Room<\/h4>/);
  assert.match(html, /Revenue risk score/);
});

test("A3 dashboard wires incident replay queue into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeIncidentReplayQueue/);
  assert.match(html, /href="#incident-replay"/);
  assert.match(html, /id="incident-replay"/);
  assert.match(html, /Incident Replay/);
  assert.match(html, /id="incident-replay-status"/);
  assert.match(html, /id="incident-replay-summary"/);
  assert.match(html, /id="incident-replay-metrics"/);
  assert.match(html, /id="incident-replay-list"/);
  assert.match(html, /id="incident-replay-steps"/);
  assert.match(html, /function renderIncidentReplayQueue\(\)/);
  assert.match(html, /function incidentReplayRow\(item\)/);
  assert.match(html, /function incidentReplayStepRow\(index, step\)/);
  assert.match(html, /renderIncidentReplayQueue\(\)/);
  assert.match(html, /incidentReplay\.queue_count/);
  assert.match(html, /Incident Replay Queue<\/h4>/);
});

test("A3 dashboard wires observability replay matrix into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeObservabilityReplayMatrix/);
  assert.match(html, /href="#observability-replay"/);
  assert.match(html, /id="observability-replay"/);
  assert.match(html, /Observability Replay/);
  assert.match(html, /id="observability-replay-status"/);
  assert.match(html, /id="observability-replay-summary"/);
  assert.match(html, /id="observability-replay-metrics"/);
  assert.match(html, /id="observability-replay-lanes"/);
  assert.match(html, /id="observability-replay-items"/);
  assert.match(html, /function renderObservabilityReplayMatrix\(\)/);
  assert.match(html, /function observabilityLaneRow\(lane\)/);
  assert.match(html, /function observabilityReplayItemRow\(item\)/);
  assert.match(html, /renderObservabilityReplayMatrix\(\)/);
  assert.match(html, /observabilityReplay\.replay_case_count/);
  assert.match(html, /Observability Replay Matrix<\/h4>/);
  assert.match(html, /Official Observability/);
});

test("A3 dashboard wires regression factory into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeRegressionFactory/);
  assert.match(html, /href="#regression-factory"/);
  assert.match(html, /id="regression-factory"/);
  assert.match(html, /Regression Factory/);
  assert.match(html, /id="regression-factory-status"/);
  assert.match(html, /id="regression-factory-summary"/);
  assert.match(html, /id="regression-factory-metrics"/);
  assert.match(html, /id="regression-factory-lanes"/);
  assert.match(html, /id="regression-factory-candidates"/);
  assert.match(html, /function renderRegressionFactory\(\)/);
  assert.match(html, /function regressionFactoryLaneRow\(lane\)/);
  assert.match(html, /function regressionCandidateRow\(item\)/);
  assert.match(html, /renderRegressionFactory\(\)/);
  assert.match(html, /regressionFactory\.candidate_count/);
  assert.match(html, /Regression Factory<\/h4>/);
  assert.match(html, /Generated Suite Plan|Coverage gaps/);
});

test("A3 dashboard wires export redaction firewall into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeExportRedactionFirewall/);
  assert.match(html, /href="#export-redaction"/);
  assert.match(html, /id="export-redaction"/);
  assert.match(html, /Export Safety/);
  assert.match(html, /id="export-redaction-status"/);
  assert.match(html, /id="export-redaction-summary"/);
  assert.match(html, /id="export-redaction-metrics"/);
  assert.match(html, /id="export-redaction-surfaces"/);
  assert.match(html, /id="export-redaction-guardrails"/);
  assert.match(html, /function renderExportRedactionFirewall\(\)/);
  assert.match(html, /function exportSurfaceRow\(surface\)/);
  assert.match(html, /function exportFirewallStatusClass\(status\)/);
  assert.match(html, /renderExportRedactionFirewall\(\)/);
  assert.match(html, /exportRedactionFirewall\.status/);
  assert.match(html, /Export Redaction Firewall<\/h4>/);
});

test("A3 dashboard wires reviewer workflow board into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeReviewerWorkflowBoard/);
  assert.match(html, /href="#reviewer-workflow"/);
  assert.match(html, /id="reviewer-workflow"/);
  assert.match(html, /Reviewer Workflow/);
  assert.match(html, /id="reviewer-workflow-status"/);
  assert.match(html, /id="reviewer-workflow-summary"/);
  assert.match(html, /id="reviewer-workflow-metrics"/);
  assert.match(html, /id="reviewer-workflow-lanes"/);
  assert.match(html, /id="reviewer-workflow-items"/);
  assert.match(html, /function renderReviewerWorkflowBoard\(\)/);
  assert.match(html, /function reviewerWorkflowLaneRow\(lane\)/);
  assert.match(html, /function reviewerWorkflowItemRow\(item\)/);
  assert.match(html, /renderReviewerWorkflowBoard\(\)/);
  assert.match(html, /reviewerWorkflowBoard\.board_label/);
  assert.match(html, /Reviewer Workflow Board<\/h4>/);
  assert.match(html, /A1 trace ready/);
  assert.match(html, /A2 judge ready/);
});

test("A3 dashboard wires media readiness and safe cloud shell panels", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeMediaReadiness/);
  assert.match(html, /summarizeCloudConsoleShell/);
  assert.match(html, /id="media-readiness"/);
  assert.match(html, /id="media-channel-strip"/);
  assert.match(html, /id="media-readiness-list"/);
  assert.match(html, /id="media-channel-matrix"/);
  assert.match(html, /id="media-evidence-queue"/);
  assert.match(html, /function renderMediaReadiness\(\)/);
  assert.match(html, /function mediaMatrixRow\(channel\)/);
  assert.match(html, /function mediaQueueRow\(item\)/);
  assert.match(html, /media\.evidence_queue/);
  assert.match(html, /ashr_signed_media_url_coverage\.redacted\.json/);
  assert.match(html, /metadata only/);
  assert.match(html, /id="cloud-shell"/);
  assert.match(html, /id="cloud-shell-list"/);
  assert.match(html, /id="cloud-action-list"/);
  assert.match(html, /function renderCloudShell\(\)/);
  assert.match(html, /function cloudActionRow\(action\)/);
  assert.match(html, /ashr_auth_check\.redacted\.json/);
  assert.match(html, /ashr_frontend_relogin_top_level_summary\.redacted\.json/);
  assert.match(html, /No cloud mutations/);
});

test("A3 dashboard wires API-backed SaaS runtime and hosted report sharing", async () => {
  const html = await loadDashboardHtml();
  const runtimeComponent = await readFile(new URL("../../apps/dashboard/src/components/saas-runtime-panel.mjs", import.meta.url), "utf8");

  assert.match(html, /api-client\.mjs/);
  assert.match(html, /components\/saas-runtime-panel\.mjs/);
  assert.match(html, /value="api-mock"/);
  assert.match(html, /API-backed Mock/);
  assert.match(html, /id="saas-runtime"/);
  assert.match(html, /id="saas-runtime-body"/);
  assert.match(html, /function applyApiDashboardPayload\(payload\)/);
  assert.match(html, /function getA3ApiBaseUrl\(\)/);
  assert.match(html, /params\.get\("apiBase"\)/);
  assert.match(html, /fetchA3DashboardSnapshot/);
  assert.match(html, /isA3ApiSource\(source\)/);
  assert.match(html, /renderSaasRuntime\(\)/);
  assert.match(html, /db_migrations/);
  assert.match(html, /usage_ledger/);
  assert.match(runtimeComponent, /Migration batches/);
  assert.match(runtimeComponent, /Usage meters/);
  assert.match(html, /data-share-report/);
  assert.match(html, /createShareableA3Report/);
  assert.match(html, /fetchA3ReportCenter/);
  assert.match(html, /id="share-report-status"/);
  assert.match(html, /id="share-report-detail"/);
  assert.match(html, /state\.reportCenter/);
  assert.match(html, /GET \/api\/a3\/reports\/center/);
  assert.match(html, /function hostedReportRow\(report\)/);
  assert.match(html, /token \$\{escapeHtml\(report\.share_link\?\.token_hash_prefix/);
  assert.match(html, /manifest-ready report/);
  assert.match(html, /allowedSources = new Set\(\["mock", "api-mock", "raw-a1", "raw-a2", "p3-media", "p3-official-demo"\]\)/);
});

test("A3 dashboard wires SaaS admin shell for login, team, usage, API keys, and trust", async () => {
  const html = await loadDashboardHtml();
  const adminComponent = await readFile(new URL("../../apps/dashboard/src/components/saas-admin-console.mjs", import.meta.url), "utf8");
  const adminModel = await readFile(new URL("../../services/report/a3_saas_admin.mjs", import.meta.url), "utf8");

  assert.match(html, /a3_saas_admin\.mjs/);
  assert.match(html, /components\/saas-admin-console\.mjs/);
  assert.match(html, /id="saas-admin"/);
  assert.match(html, /id="saas-admin-body"/);
  assert.match(html, /SaaS Admin Console/);
  assert.match(html, /buildSaasAdminConsole/);
  assert.match(html, /function refreshLocalSaasAdmin\(\)/);
  assert.match(html, /function renderSaasAdmin\(\)/);
  assert.match(html, /state\.saasAdmin/);
  assert.match(html, /planA3AdminAction/);
  assert.match(html, /data-admin-action-select/);
  assert.match(html, /login, team, usage, API key, and trust state/);
  assert.match(adminComponent, /RBAC Matrix/);
  assert.match(adminComponent, /Invite Workflow/);
  assert.match(adminComponent, /API Key Lifecycle/);
  assert.match(adminComponent, /Trust Center/);
  assert.match(adminComponent, /Cloud Management/);
  assert.match(adminComponent, /Product Console Map/);
  assert.match(adminModel, /quota_mutations_enabled/);
  assert.match(html, /state\.saasRuntime\.usage_ledger/);
  assert.match(html, /saas_admin_console/);
  assert.match(html, /selectedAdminAction/);
  assert.match(html, /selectedAdminPlan/);
  assert.match(html, /clean-room shell/);
});

test("A3 dashboard wires enterprise readiness for self-host and audit review", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /a3_enterprise_readiness\.mjs/);
  assert.match(html, /components\/enterprise-readiness-panel\.mjs/);
  assert.match(html, /href="#enterprise-readiness"/);
  assert.match(html, /id="enterprise-readiness"/);
  assert.match(html, /id="enterprise-readiness-body"/);
  assert.match(html, /Enterprise Readiness/);
  assert.match(html, /buildEnterpriseReadinessReport/);
  assert.match(html, /renderEnterpriseReadinessPanel/);
  assert.match(html, /state\.enterpriseReadiness/);
  assert.match(html, /enterprise_readiness/);
  assert.match(html, /function refreshEnterpriseReadiness\(\)/);
  assert.match(html, /function renderEnterpriseReadiness\(\)/);
  assert.match(html, /renderEnterpriseReadiness\(\)/);
  assert.match(html, /GET \/api\/a3\/enterprise\/readiness/);
  assert.match(html, /self-host \/ audit/);
});
