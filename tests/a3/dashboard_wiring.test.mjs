import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadDashboardHtml() {
  return readFile(new URL("../../apps/dashboard/index.html", import.meta.url), "utf8");
}

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
  assert.match(html, /allowedSources = new Set\(\["mock", "p3-media", "p3-official-demo"\]\)/);
  assert.match(html, /P3 official Ashr demo dataset 884 \/ run 11926/);
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
