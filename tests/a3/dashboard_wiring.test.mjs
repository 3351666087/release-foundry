import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadDashboardHtml() {
  const [html, app, apiClient, visualShell, styles] = await Promise.all([
    readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/app.mjs", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/api-client.mjs", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/visual-shell.mjs", import.meta.url), "utf8"),
    readFile(new URL("../../apps/dashboard/src/styles.css", import.meta.url), "utf8")
  ]);
  return [html, app, apiClient, visualShell, styles].join("\n");
}

function assertNavigationTarget(source, hash) {
  const escaped = hash.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.match(source, new RegExp(`(?:href="${escaped}"|href:\\s*["']${escaped}["'])`));
}

test("A3 dashboard is split into a webapp shell, module, and stylesheet", async () => {
  const html = await loadDashboardHtml();
  const indexHtml = await readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8");

  assert.match(indexHtml, /<link rel="stylesheet" href="\.\/src\/styles\.css" \/>/);
  assert.match(indexHtml, /<script type="module" src="\.\/src\/app\.mjs"><\/script>/);
  assert.doesNotMatch(indexHtml, /<style>/);
  assert.doesNotMatch(indexHtml, /<script type="module">\s*import/);
  assert.match(html, /from "\.\.\/\.\.\/\.\.\/services\/report\/report_builder\.mjs"/);
  assert.match(html, /from "\.\/visual-shell\.mjs"/);
  assert.match(html, /data-visual-shell="primary-nav"/);
  assert.match(html, /export const primaryAreas/);
  assert.match(html, /export const workspaceRailGroups/);
  assert.match(html, /className = "nav-group"/);
  assert.match(html, /className = "nav-sublist"/);
  assert.match(html, /function syncExpandedNavigation\(id\)/);
});

test("A3 dashboard wires optional A2 coverage into JSON and Markdown exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /coverage: \{\}/);
  assert.match(html, /evidenceReadiness: \{\}/);
  assert.match(html, /caseBook: \{\}/);
  assert.match(html, /regressionReplay: \{\}/);
  assert.match(html, /commercialReadiness: \{\}/);
  assert.match(html, /resultPersistence: \{\}/);
  assert.match(html, /releaseUnblockChecklist: \{\}/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_g3_coverage_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_evidence_readiness_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_case_book\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_regression_replay_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_commercial_readiness_report\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_result_persistence_manifest\.json"\)/);
  assert.match(html, /loadOptionalJson\("\.\.\/\.\.\/fixtures\/a2\/results\/a2_release_unblock_checklist\.json"\)/);
  assert.match(html, /buildJsonReport\(/);
  assert.match(html, /buildMarkdownReport\(/);
  assert.match(html, /state\.evidenceReadiness/);
  assert.match(html, /caseBook: state\.caseBook/);
  assert.match(html, /regressionReplay: state\.regressionReplay/);
  assert.match(html, /commercialReadiness: state\.commercialReadiness/);
  assert.match(html, /resultPersistence: state\.resultPersistence/);
  assert.match(html, /releaseUnblockChecklist: state\.releaseUnblockChecklist/);
  assert.match(html, /state\.mediaSignedUrlCoverage/);
  assert.match(html, /state\.authCheck/);
  assert.match(html, /state\.frontendSummary/);
  assert.match(html, /state\.frontendMirror/);
  assert.match(html, /buildCsvReport\(state\.runs, state\.grades\)/);
});

test("A3 dashboard wires A1/A2 schema drift radar into the API-backed console", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="schema-drift-radar"/);
  assert.match(html, /A1\/A2 Contract Radar/);
  assertNavigationTarget(html, "#schema-drift-radar");
  assert.match(html, /fetchA3SchemaDriftRadar/);
  assert.match(html, /\/api\/a3\/a1-a2\/schema-drift/);
  assert.match(html, /"x-a3-role": options\.role \|\| "auditor"/);
  assert.match(html, /schemaDriftRadar: \{\}/);
  assert.match(html, /state\.schemaDriftRadar = await fetchA3SchemaDriftRadar/);
  assert.match(html, /function resetSchemaDriftRadar\(\)/);
  assert.match(html, /function renderSchemaDriftRadar\(\)/);
  assert.match(html, /raw_schema_payload_embedded/);
  assert.match(html, /renderSchemaDriftRadar\(\)/);
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
  assertNavigationTarget(html, "#official-gap");
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
  assertNavigationTarget(html, "#official-mirror");
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
  assertNavigationTarget(html, "#official-code-crawl");
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
  assertNavigationTarget(html, "#official-roadmap");
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
  assertNavigationTarget(html, "#release-gate");
  assertNavigationTarget(html, "#pr-gate");
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

test("A3 dashboard wires GitHub publish evidence into reports and registry", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /githubPublishEvidence: \{\}/);
  assert.match(html, /loadGithubPublishEvidenceFixtures/);
  assert.match(html, /a3_github_check_publish_receipt_dry_run\.redacted\.json/);
  assert.match(html, /a3_github_pr_comment_publish_receipt_dry_run\.redacted\.json/);
  assert.match(html, /a3_github_required_check_plan\.redacted\.json/);
  assert.match(html, /github_publish_evidence/);
  assert.match(html, /state\.githubPublishEvidence/);
  assert.match(html, /githubPublishEvidence: state\.githubPublishEvidence/);
  assert.match(html, /state\.githubPublishEvidence = payload\.github_publish_evidence \|\| \{\}/);
});

test("A3 dashboard wires release war room into console and reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeReleaseWarRoom/);
  assertNavigationTarget(html, "#war-room");
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
  assertNavigationTarget(html, "#incident-replay");
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
  assertNavigationTarget(html, "#observability-replay");
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
  assertNavigationTarget(html, "#regression-factory");
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
  assertNavigationTarget(html, "#export-redaction");
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
  assertNavigationTarget(html, "#reviewer-workflow");
  assert.match(html, /id="reviewer-workflow"/);
  assert.match(html, /Reviewer Workflow/);
  assert.match(html, /id="reviewer-workflow-status"/);
  assert.match(html, /id="reviewer-workflow-summary"/);
  assert.match(html, /id="reviewer-workflow-metrics"/);
  assert.match(html, /id="reviewer-workflow-lanes"/);
  assert.match(html, /id="reviewer-workflow-items"/);
  assert.match(html, /id="review-workflow-records"/);
  assert.match(html, /function renderReviewerWorkflowBoard\(\)/);
  assert.match(html, /function reviewerWorkflowLaneRow\(lane\)/);
  assert.match(html, /function reviewerWorkflowItemRow\(item\)/);
  assert.match(html, /function renderReviewWorkflowRecords\(\)/);
  assert.match(html, /fetchA3ReviewWorkflow/);
  assert.match(html, /submitA3ReviewWaiver/);
  assert.match(html, /submitA3ReviewApproval/);
  assert.match(html, /submitA3ReviewDenial/);
  assert.match(html, /review_workflow/);
  assert.match(html, /GET \/api\/a3\/review\/workflow/);
  assert.match(html, /POST \/api\/a3\/review\/denials/);
  assert.match(html, /data-review-action="denial"/);
  assert.match(html, /Record Denial/);
  assert.match(html, /denial_count/);
  assert.match(html, /function submitReviewWorkflowAction\(action\)/);
  assert.match(html, /function buildDashboardDenialRecord\(\)/);
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
  assert.match(html, /fetchA3UsageLedger/);
  assert.match(html, /fetchA3BillingReadiness/);
  assert.match(html, /fetchA3LiveWorkflowReadiness/);
  assert.match(html, /fetchA3PeerBranchCalibration/);
  assert.match(html, /isA3ApiSource\(source\)/);
  assert.match(html, /renderSaasRuntime\(\)/);
  assert.match(html, /db_migrations/);
  assert.match(html, /usage_ledger/);
  assert.match(runtimeComponent, /Migration batches/);
  assert.match(runtimeComponent, /Usage meters/);
  assert.match(runtimeComponent, /Billing readiness/);
  assert.match(runtimeComponent, /invoice export/);
  assert.match(runtimeComponent, /A1 usage ready/);
  assert.match(html, /data-share-report/);
  assert.match(html, /createShareableA3Report/);
  assert.match(html, /revokeShareableA3Report/);
  assert.match(html, /fetchA3ArtifactRegistry/);
  assert.match(html, /fetchA3ReportCenter/);
  assert.match(html, /id="share-report-status"/);
  assert.match(html, /id="share-report-detail"/);
  assert.match(html, /state\.reportCenter/);
  assert.match(html, /state\.artifactRegistry/);
  assert.match(html, /GET \/api\/a3\/reports\/center/);
  assert.match(html, /GET \/api\/a3\/artifacts\/registry/);
  assert.match(html, /GET \/api\/a3\/usage\/ledger/);
  assert.match(html, /GET \/api\/a3\/billing\/readiness/);
  assert.match(html, /GET \/api\/a3\/live-workflow\/readiness/);
  assert.match(html, /GET \/api\/a3\/live-ops\/control-plane/);
  assert.match(html, /GET \/api\/a3\/peer-branches\/calibration/);
  assert.match(html, /function hostedReportRow\(report\)/);
  assert.match(html, /function revokeHostedReport\(report\)/);
  assert.match(html, /function refreshReportEvidence\(\)/);
  assert.match(html, /Revoke/);
  assert.match(html, /dashboard_revoke/);
  assert.match(html, /function artifactRegistrySummaryRow\(registry/);
  assert.match(html, /function artifactEntryRow\(entry/);
  assert.match(html, /Artifact Registry/);
  assert.match(html, /token \$\{escapeHtml\(report\.share_link\?\.token_hash_prefix/);
  assert.match(html, /manifest-ready report/);
  assert.match(html, /allowedSources = new Set\(\["mock", "api-mock", "raw-a1", "raw-a2", "p3-media", "p3-official-demo"\]\)/);
});

test("A3 dashboard wires live workflow readiness for GitHub, review, billing, and hosted reports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="live-workflow-readiness"/);
  assert.match(html, /Live Workflow Readiness/);
  assertNavigationTarget(html, "#live-workflow-readiness");
  assert.match(html, /liveWorkflowReadiness: \{\}/);
  assert.match(html, /buildA3LiveWorkflowReadiness/);
  assert.match(html, /fetchA3LiveWorkflowReadiness/);
  assert.match(html, /function refreshLiveWorkflowReadiness\(\)/);
  assert.match(html, /function renderLiveWorkflowReadiness\(\)/);
  assert.match(html, /state\.liveWorkflowReadiness = await fetchA3LiveWorkflowReadiness/);
  assert.match(html, /live_workflow_readiness/);
  assert.match(html, /GET \/api\/a3\/live-workflow\/readiness/);
  assert.match(html, /GitHub, reviewer, billing, and hosted-report readiness/);
  assert.match(html, /human records/);
  assert.match(html, /need live backend/);
});

test("A3 dashboard wires live ops control plane for PR, review, billing, human ops, and share links", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="live-ops-control-plane"/);
  assert.match(html, /Live Ops Control Plane/);
  assertNavigationTarget(html, "#live-ops-control-plane");
  assert.match(html, /liveOpsControlPlane: \{\}/);
  assert.match(html, /buildA3LiveOpsControlPlane/);
  assert.match(html, /fetchA3LiveOpsControlPlane/);
  assert.match(html, /function refreshLiveOpsControlPlane\(\)/);
  assert.match(html, /function renderLiveOpsControlPlane\(\)/);
  assert.match(html, /state\.liveOpsControlPlane = await fetchA3LiveOpsControlPlane/);
  assert.match(html, /live_ops_control_plane/);
  assert.match(html, /GET \/api\/a3\/live-ops\/control-plane/);
  assert.match(html, /PR publishing, review, human-operation, billing, and share-link control state/);
  assert.match(html, /local mutations/);
});

test("A3 dashboard wires peer branch calibration into console and exports", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /id="peer-branch-calibration"/);
  assert.match(html, /Peer Branch Calibration/);
  assert.match(html, /id="peer-branch-status"/);
  assert.match(html, /id="peer-branch-body"/);
  assertNavigationTarget(html, "#peer-branch-calibration");
  assert.match(html, /Peer branches/);
  assert.match(html, /Peer Branches/);
  assert.match(html, /peerBranchCalibration: \{\}/);
  assert.match(html, /summarizeA3PeerBranchCalibration/);
  assert.match(html, /function renderPeerBranchCalibration\(\)/);
  assert.match(html, /state\.peerBranchCalibration = await loadOptionalJson\("\.\.\/\.\.\/fixtures\/a3\/p3\/a3_peer_branch_calibration\.redacted\.json"\)/);
  assert.match(html, /state\.peerBranchCalibration = await fetchA3PeerBranchCalibration/);
  assert.match(html, /peer_branch_calibration/);
  assert.match(html, /a3_peer_branch_calibration\.redacted\.json/);
  assert.match(html, /state\.peerBranchCalibration/);
  assert.match(html, /Peer Branch Calibration", `\$\{peerBranchCalibration\.status\}/);
  assert.match(html, /A1\/A2 peer delta/);
  assert.match(html, /does not modify A1/);
});

test("A3 dashboard wires release evidence publish and verification display", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /summarizeReleaseEvidenceSummary/);
  assert.match(html, /releaseEvidence: \{\}/);
  assert.match(html, /releaseEvidenceReadbacks: \{\}/);
  assert.match(html, /id="release-evidence"/);
  assert.match(html, /id="release-evidence-status"/);
  assert.match(html, /id="release-evidence-metrics"/);
  assert.match(html, /id="release-evidence-github"/);
  assert.match(html, /id="release-evidence-verification"/);
  assert.match(html, /function loadReleaseEvidenceFixtures\(\)/);
  assert.match(html, /a3_github_check_publish_receipt_dry_run\.redacted\.json/);
  assert.match(html, /a3_github_pr_comment_publish_receipt_dry_run\.redacted\.json/);
  assert.match(html, /a3_github_required_check_plan\.redacted\.json/);
  assert.match(html, /a3_github_check_readback_confirmed\.redacted\.json/);
  assert.match(html, /a3_github_pr_comment_readback_confirmed\.redacted\.json/);
  assert.match(html, /a3_github_required_check_proof_plan_only\.redacted\.json/);
  assert.match(html, /a3_audit_bundle_verification_passed\.redacted\.json/);
  assert.match(html, /a3_audit_archive_verification_passed\.redacted\.json/);
  assert.match(html, /function renderReleaseEvidenceSummary\(\)/);
  assert.match(html, /function shortHash\(value\)/);
  assert.match(html, /function releaseEvidenceRow\(title, value, detail\)/);
  assert.match(html, /renderReleaseEvidenceSummary\(\)/);
  assert.match(html, /state\.releaseEvidence/);
  assert.match(html, /state\.releaseEvidenceReadbacks/);
  assert.match(html, /release_evidence_summary/);
  assert.match(html, /release_evidence_readbacks/);
  assert.match(html, /Release Evidence/);
  assert.match(html, /Check readback/);
  assert.match(html, /PR comment readback/);
  assert.match(html, /Required-check readback/);
  assert.match(html, /Readback history/);
  assert.match(html, /A1\/A2 boundary/);
  assert.match(html, /archive signature/);
  assert.match(html, /real GitHub mutation/);
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
  assert.match(html, /submitA3AdminAction/);
  assert.match(html, /data-admin-action-select/);
  assert.match(html, /data-admin-action-submit/);
  assert.match(html, /function submitAdminActionRequest\(\)/);
  assert.match(html, /login, team, usage, API key, and trust state/);
  assert.match(adminComponent, /RBAC Matrix/);
  assert.match(adminComponent, /Invite Workflow/);
  assert.match(adminComponent, /API Key Lifecycle/);
  assert.match(adminComponent, /Trust Center/);
  assert.match(adminComponent, /Cloud Management/);
  assert.match(adminComponent, /Product Console Map/);
  assert.match(adminComponent, /Admin Action Requests/);
  assert.match(adminComponent, /Record Request|Record Guardrail/);
  assert.match(adminModel, /quota_mutations_enabled/);
  assert.match(adminModel, /buildSaasAdminActionRequest/);
  assert.match(html, /state\.saasRuntime\.usage_ledger/);
  assert.match(html, /state\.saasRuntime\.billing_readiness/);
  assert.match(html, /billingReadiness/);
  assert.match(html, /saas_admin_console/);
  assert.match(html, /selectedAdminAction/);
  assert.match(html, /selectedAdminPlan/);
  assert.match(html, /selectedAdminReceipt/);
  assert.match(html, /POST \/api\/a3\/admin\/actions\/submit/);
  assert.match(html, /GET \/api\/a3\/admin\/actions/);
  assert.match(html, /clean-room shell/);
});

test("A3 dashboard wires product console onboarding, project, and audit workflow", async () => {
  const html = await loadDashboardHtml();
  const productComponent = await readFile(new URL("../../apps/dashboard/src/components/product-console-panel.mjs", import.meta.url), "utf8");

  assert.match(html, /a3_product_console\.mjs/);
  assert.match(html, /summarizeProductConsoleExport/);
  assert.match(html, /summarizeSaasAdminExport/);
  assert.match(html, /components\/product-console-panel\.mjs/);
  assert.match(html, /fetchA3ProductConsole/);
  assertNavigationTarget(html, "#product-console");
  assert.match(html, /id="product-console"/);
  assert.match(html, /id="product-console-body"/);
  assert.match(html, /function refreshLocalProductConsole\(\)/);
  assert.match(html, /function renderProductConsole\(\)/);
  assert.match(html, /Product Console \/ Onboarding \/ Audit/);
  assert.match(html, /SaaS Admin \/ Login \/ Team \/ Trust/);
  assert.match(html, /state\.productConsole/);
  assert.match(html, /state\.saasAdmin/);
  assert.match(html, /product console workflow/);
  assert.match(html, /SaaS admin guardrails/);
  assert.match(html, /product_console/);
  assert.match(html, /GET \/api\/a3\/product\/console/);
  assert.match(productComponent, /Onboarding Flow/);
  assert.match(productComponent, /Project Console/);
  assert.match(productComponent, /Audit Log/);
  assert.match(productComponent, /Commercial Readiness/);
});

test("A3 dashboard wires enterprise readiness for self-host and audit review", async () => {
  const html = await loadDashboardHtml();

  assert.match(html, /a3_enterprise_readiness\.mjs/);
  assert.match(html, /components\/enterprise-readiness-panel\.mjs/);
  assertNavigationTarget(html, "#enterprise-readiness");
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
