import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  buildDashboardSummary,
  normalizeCases,
  summarizeReleaseEvidenceSummary,
  summarizeReleaseWorkflow
} from "./report_builder.mjs";
import {
  publishGitHubCheckRun as publishGitHubCheckRunReceipt,
  publishPrCommentUpsert as publishPrCommentUpsertReceipt
} from "./a3_github_integration.mjs";
import { mapAshrSampleToA3Fixtures } from "./p3_ashr_mapper.mjs";
import { buildShareableReportPayload } from "./a3_shareable_report.mjs";
import {
  buildReleaseEvidenceHealth,
  buildReleaseEvidenceSummaryV2,
  diffReleaseEvidenceSummaries
} from "./a3_release_evidence.mjs";
import {
  buildSaasAdminActionRequest,
  buildSaasAdminConsole,
  planSaasAdminAction,
  summarizeSaasAdminActionRequests
} from "./a3_saas_admin.mjs";
import { buildEnterpriseReadinessReport } from "./a3_enterprise_readiness.mjs";
import { buildReportCenterIndex } from "./a3_report_center.mjs";
import { buildReportCenterManifest } from "./a3_report_center_manifest.mjs";
import { buildA3SqlMigrationPlan } from "./a3_sql_migrations.mjs";
import { buildA3UsageLedger } from "./a3_usage_ledger.mjs";
import { buildA3BillingReadiness } from "./a3_billing_readiness.mjs";
import { buildA3BillingMigrationReadiness } from "./a3_billing_migration_readiness.mjs";
import { buildA3ProductConsole } from "./a3_product_console.mjs";
import { buildA3ArtifactRegistry } from "./a3_artifact_registry.mjs";
import { buildA3CommercialApiContract } from "./a3_commercial_api_contract.mjs";
import { summarizeA3PeerBranchCalibration } from "./a3_peer_branch_calibration.mjs";
import { buildA3SourceArtifacts } from "./a3_source_artifacts.mjs";
import { buildA3LiveWorkflowReadiness } from "./a3_live_workflow_readiness.mjs";
import { buildA3LiveOpsControlPlane } from "./a3_live_ops_control_plane.mjs";
import { buildA3NotificationControlPlane } from "./a3_notification_control_plane.mjs";
import { buildA3ReleaseDecisionProvenance } from "./a3_release_decision_provenance.mjs";
import { buildA3A1A2EvidenceSpine } from "./a3_a1_a2_evidence_spine.mjs";
import {
  buildA3TenantScope,
  tenantScopeMatches,
  tenantScopeToSnapshotFields
} from "./a3_tenant_scope.mjs";
import {
  buildA3EventEnvelope,
  validateA3EventEnvelope
} from "./a3_event_envelope.mjs";
import {
  buildReviewWorkflowIndex,
  buildReviewWorkflowRecord
} from "./a3_review_workflow.mjs";
import { evaluateA2TrustedReleaseAuthority } from "./a3_trusted_release_authority.mjs";
import {
  buildDeliveryGoldenPath,
  buildDeploymentAcceptance,
  normalizeA2GradeReport
} from "./a3_release_delivery.mjs";
import {
  bindA3ReleaseComparisonRuntimeAuthority,
  buildA3ReleaseComparison
} from "./a3_release_comparison.mjs";
import { buildA3DeploymentHandoff } from "./a3_deployment_handoff.mjs";
import {
  buildA3DeploymentAcceptanceProjection,
  buildA3DeploymentReceiptAuthoritativeReadback,
  buildA3DeploymentReceiptInbox,
  buildA3DeploymentReceiptSubmission,
  isTrustedA3DeploymentReceiptAuthoritativeReadback,
  reviewA3DeploymentReceipt
} from "./a3_deployment_receipt_workflow.mjs";
import {
  loadSelfHostSandboxCalibration,
  validateSelfHostSandboxCalibration
} from "./a3_self_host_sandbox.mjs";
import {
  buildA3MultimodalReviewQueue,
  validateA2MultimodalComparison
} from "./a3_multimodal_review_queue.mjs";
import {
  A3_MULTIMODAL_REVIEW_ASSIGNMENT_RECEIPT_SCHEMA_VERSION,
  buildA3MultimodalReviewAssignmentPacket,
  buildA3MultimodalReviewAssignmentProjection,
  planA3MultimodalReviewAssignmentTransition
} from "./a3_multimodal_review_assignment.mjs";

export const A3_STORE_SCHEMA_VERSION = "a3.store.v1";

export class A3StoreValidationError extends Error {
  constructor(message, details = [], options = {}) {
    super(message);
    this.name = "A3StoreValidationError";
    this.schema_version = "a3.api_validation_error.v1";
    this.statusCode = options.statusCode || 400;
    this.error = options.error || "validation_error";
    this.details = details;
    this.requestType = options.requestType || "unknown";
    this.source = options.source || "unknown";
  }
}

export class A3StoreResourceNotFoundError extends Error {
  constructor() {
    super("Tenant-scoped resource was not found.");
    this.name = "A3StoreResourceNotFoundError";
  }
}

export const A3_SOURCE_FIXTURES = {
  mock: {
    label: "A1/A2 Mock",
    runFixture: "fixtures/a3/mock_run_results.json",
    gradeFixture: "fixtures/a3/mock_grade_results.json",
    a2GradeResults: "fixtures/a2/results/a2_g3_grade_results.json",
    a2ReleaseGate: "fixtures/a2/results/a2_release_gate_report.json"
  },
  "raw-a1": {
    label: "Raw A1 RunResult",
    runFixture: "docs/a1/evidence/local_run_30.json"
  },
  "raw-a2": {
    label: "Raw A2 Single Case",
    runFixture: "fixtures/a2/runs/a2_s004_missing_tool.json",
    gradeFixture: "fixtures/a2/results/a2_s004_missing_tool_grade.json"
  },
  "p3-media": {
    label: "P3 Media Sample",
    ashrRunSample: "fixtures/a3/p3/ashr_run_detail_sample.redacted.json",
    datasetSample: "fixtures/a3/p3/ashr_dataset_detail_sample.redacted.json",
    fixtureId: "p3_ashr_media_dashboard_sample",
    gradeFixtureId: "p3_ashr_media_dashboard_grades",
    requestProvenance: "fixtures/a3/p3/ashr_request_detail_sample.redacted.json",
    usageQuota: "fixtures/a3/p3/ashr_usage_quota_sample.redacted.json",
    usageQuotaApiProbe: "fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json",
    mediaSignedUrlCoverage: "fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json",
    authCheck: "fixtures/a3/p3/ashr_auth_check.redacted.json",
    frontendSummary: "fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json",
    a2MultimodalComparison: "fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json",
    a2MultimodalComparisonSourceCommit: "564d4b0",
    a2MultimodalComparisonCapability: "peer_branch_contract_not_merged"
  },
  "p3-official-demo": {
    label: "P3 Official Demo 884/11926",
    ashrRunSample: "fixtures/a3/p3/ashr_dataset_884_run_11926_ui_tests_detail.redacted.json",
    datasetSample: "fixtures/a3/p3/ashr_after_generate_dataset_884.redacted.json",
    fixtureId: "p3_official_demo_884_11926_dashboard_sample",
    gradeFixtureId: "p3_official_demo_884_11926_dashboard_grades",
    requestProvenance: "fixtures/a3/p3/ashr_after_generate_frontend_summary.redacted.json",
    usageQuota: "fixtures/a3/p3/ashr_usage_quota_sample.redacted.json",
    usageQuotaApiProbe: "fixtures/a3/p3/ashr_usage_quota_api_probe.redacted.json",
    mediaSignedUrlCoverage: "fixtures/a3/p3/ashr_signed_media_url_coverage.redacted.json",
    authCheck: "fixtures/a3/p3/ashr_auth_check.redacted.json",
    frontendSummary: "fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json"
  },
  "a3-golden-path": {
    label: "A3 Golden Path 20260712",
    runFixture: "fixtures/a3/golden-path/a3_new_run_result.redacted.json",
    gradeFixture: "fixtures/a3/golden-path/a2_new_run_judge_response.redacted.json",
    a2TrustedSpine: "fixtures/a2/results/a2_trusted_spine_handoff.json",
    deploymentProbe: "fixtures/a3/golden-path/deployment_probe.redacted.json",
    deploymentAcceptance: "fixtures/a3/golden-path/deployment-acceptance.json",
    releaseArtifactManifest: "fixtures/a3/golden-path/release-artifact-manifest.json",
    releaseArtifactVerification: "fixtures/a3/golden-path/release-artifact-verification.json",
    deliveryGoldenPath: "fixtures/a3/golden-path/golden-path-status.json",
    githubCheckReadback: "fixtures/a3/golden-path/github-check-live-readback.redacted.json",
    githubPrCommentReadback: "fixtures/a3/golden-path/github-pr-comment-live-readback.redacted.json",
    githubRequiredCheckProof: "fixtures/a3/golden-path/github-required-check-live-readback.redacted.json",
    githubActionsArtifactReadback: "fixtures/a3/golden-path/github-actions-artifact-live-readback.redacted.json"
  },
  "a3-golden-path-rc2": {
    label: "A3 Golden Path rc.2 - A1/A2 3 of 3",
    comparisonBaselineSource: "a3-golden-path",
    runFixture: "fixtures/a3/golden-path/rc2/a3_new_run_result.redacted.json",
    gradeFixture: "fixtures/a3/golden-path/rc2/a2_new_run_judge_response.redacted.json",
    a2TrustedSpine: "fixtures/a2/results/a2_trusted_spine_handoff.json",
    deploymentProbe: "fixtures/a3/golden-path/rc2/deployment_probe.redacted.json",
    deploymentAcceptance: "fixtures/a3/golden-path/rc2/deployment-acceptance.json",
    releaseArtifactManifest: "fixtures/a3/golden-path/rc2/release-artifact-manifest.json",
    releaseArtifactVerification: "fixtures/a3/golden-path/rc2/release-artifact-verification.json",
    deliveryGoldenPath: "fixtures/a3/golden-path/rc2/golden-path-status.json",
    githubCheckReadback: "fixtures/a3/golden-path/rc2/github-check-live-readback.redacted.json",
    githubPrCommentReadback: "fixtures/a3/golden-path/rc2/github-pr-comment-live-readback.redacted.json",
    githubRequiredCheckProof: "fixtures/a3/golden-path/rc2/github-required-check-live-readback.redacted.json",
    githubActionsArtifactReadback: "fixtures/a3/golden-path/rc2/github-actions-artifact-live-readback.redacted.json"
  }
};

export const A3_DB_CONTRACT = {
  schema_version: "a3.saas_db_contract.v1",
  recommended_primary_db: "postgres",
  mysql_compatible: true,
  local_dev_store: "memory_or_file",
  tenant_columns_required: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"],
  tables: [
    "organizations",
    "users",
    "team_members",
    "roles",
    "auth_contexts",
    "rbac_policy_snapshots",
    "authz_decisions",
    "api_keys",
    "projects",
    "runs",
    "cases",
    "trace_events",
    "tool_calls",
    "grade_results",
    "failure_clusters",
    "media_evidence",
    "shareable_reports",
    "report_share_links",
    "report_view_events",
    "report_revocations",
    "trust_reports",
    "artifact_registry_entries",
    "artifact_lifecycle_events",
    "saas_admin_action_requests",
    "review_workflow_records",
    "multimodal_review_snapshots",
    "multimodal_review_assignment_events",
    "release_evidence_summaries",
    "release_evidence_snapshots",
    "release_evidence_diffs",
    "release_evidence_readbacks",
    "github_publish_receipts",
    "deployment_receipts",
    "deployment_receipt_readbacks",
    "self_host_sandbox_calibrations",
    "notification_channels",
    "notification_subscriptions",
    "notification_templates",
    "notification_deliveries",
    "webhook_deliveries",
    "idempotency_keys",
    "api_import_receipts",
    "audit_events",
    "usage_ledger",
    "billing_migration_readiness",
    "commercial_api_contracts",
    "peer_branch_calibrations",
    "live_workflow_readiness",
    "live_ops_control_plane",
    "notification_control_plane",
    "source_artifacts",
    "event_outbox"
  ],
  api_surfaces: [
    "GET /api/a3/auth/context",
    "GET /api/a3/auth/rbac-policy",
    "POST /api/a3/auth/authorize",
    "GET /api/a3/dashboard",
    "GET /api/a3/deployment/sandbox-calibration",
    "GET /api/a3/deployment/receipts",
    "POST /api/a3/deployment/receipts",
    "POST /api/a3/deployment/receipts/:receiptId/review",
    "POST /internal/a3/deployment/receipts/:receiptId/verify",
    "GET /api/a3/release-decision/provenance",
    "POST /api/a3/ui-actions/preflight",
    "GET /api/a3/runs",
    "GET /api/a3/runs/:runId",
    "GET /api/a3/cases/:caseId",
    "POST /api/a3/import/a1-run-result",
    "POST /api/a3/import/a2-grade-result",
    "POST /api/a3/import/a2-multimodal-comparison",
    "POST /api/a3/reports/share",
    "GET /api/a3/reports/:reportId",
    "GET /reports/:reportId",
    "GET /r/:shareToken",
    "POST /api/a3/reports/:reportId/revoke",
    "POST /api/a3/reports/:reportId/view",
    "GET /api/a3/admin/console",
    "POST /api/a3/admin/actions/plan",
    "POST /api/a3/admin/actions/submit",
    "GET /api/a3/admin/actions",
    "POST /api/a3/review/waivers",
    "POST /api/a3/review/approvals",
    "POST /api/a3/review/denials",
    "GET /api/a3/review/workflow",
    "GET /api/a3/review/multimodal-queue",
    "POST /api/a3/review/multimodal-queue/:queueId/assignment",
    "GET /api/a3/product/console",
    "GET /api/a3/enterprise/readiness",
    "GET /api/a3/db-migrations",
    "GET /api/a3/usage/ledger",
    "GET /api/a3/billing/readiness",
    "GET /api/a3/billing/migration-readiness",
    "GET /api/a3/live-workflow/readiness",
    "GET /api/a3/live-ops/control-plane",
    "GET /api/a3/notifications/control-plane",
    "GET /api/a3/commercial-api/contract",
    "GET /api/a3/peer-branches/calibration",
    "GET /api/a3/a1-a2/schema-drift",
    "GET /api/a3/a1-a2/evidence-spine",
    "GET /api/a3/events/outbox",
    "GET /api/a3/reports/center",
    "GET /api/a3/reports/:reportId/manifest",
    "GET /api/a3/artifacts/registry",
    "GET /api/a3/releases/:releaseId/evidence-summary",
    "POST /api/a3/github/check-run/publish",
    "POST /api/a3/github/pr-comment/publish",
    "POST /api/a3/releases/:releaseId/readbacks",
    "GET /api/a3/releases/:releaseId/readbacks"
  ],
  guardrails: [
    "Hosted reads require exact source plus organization, tenant, workspace, project, and environment scope equality.",
    "Memory, file, and SQLite stores are local reference implementations and are not production RLS evidence.",
    "Self-host sandbox calibrations are local A1 behavior evidence and never mutate production deployment acceptance.",
    "Auth context, RBAC policy, and authorization decisions are metadata-only until A1 hosted auth middleware is available.",
    "Shareable reports must pass the export redaction firewall.",
    "Secrets, cookies, tokens, emails, raw signed URLs, and local paths are never persisted in public report payloads.",
    "A1 runner payloads and A2 judge payloads are normalized at the A3 boundary without changing their source semantics."
  ]
};

const REPO_ROOT = new URL("../../", import.meta.url);

const A3_RELEASE_EVIDENCE_FIXTURES = {
  githubCheckPublishReceipt: "fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json",
  githubPrCommentPublishReceipt: "fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json",
  githubRequiredCheckPlan: "fixtures/a3/p3/a3_github_required_check_plan.redacted.json",
  githubCheckReadback: "fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json",
  githubPrCommentReadback: "fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json",
  githubRequiredCheckProof: "fixtures/a3/p3/a3_github_required_check_proof_plan_only.redacted.json",
  auditBundleVerification: "fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json",
  auditArchiveVerification: "fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json"
};

export async function loadA3SourceSnapshot(source = "mock", options = {}) {
  const sourceKey = normalizeSourceKey(source);
  const config = A3_SOURCE_FIXTURES[sourceKey];
  if (!config) {
    throw new Error(`Unknown A3 source: ${source}`);
  }

  const root = options.repoRoot ? pathToFileURL(`${resolve(options.repoRoot)}/`) : REPO_ROOT;
  let runFixture = {};
  let gradeFixture = {};
  const datasetSample = await readOptionalJson(root, config.datasetSample);

  if (config.ashrRunSample) {
    const sample = await readJson(root, config.ashrRunSample);
    const mapped = mapAshrSampleToA3Fixtures(sample, {
      fixtureId: config.fixtureId,
      gradeFixtureId: config.gradeFixtureId,
      datasetSample
    });
    runFixture = mapped.runFixture;
    gradeFixture = mapped.gradeFixture;
  } else {
    runFixture = await readJson(root, config.runFixture);
    gradeFixture = config.gradeFixture
      ? normalizeA2GradeReport(await readJson(root, config.gradeFixture))
      : {};
  }

  let snapshot = normalizeSnapshot({
    source: sourceKey,
    source_label: config.label,
    runFixture,
    gradeFixture,
    coverage: await readOptionalJson(root, "fixtures/a2/results/a2_g3_coverage_report.json"),
    requestProvenance: await readOptionalJson(root, config.requestProvenance),
    usageQuota: await readOptionalJson(root, config.usageQuota),
    usageQuotaApiProbe: await readOptionalJson(root, config.usageQuotaApiProbe),
    mediaSignedUrlCoverage: await readOptionalJson(root, config.mediaSignedUrlCoverage),
    authCheck: await readOptionalJson(root, config.authCheck),
    frontendSummary: await readOptionalJson(root, config.frontendSummary),
    frontendMirror: await readOptionalJson(root, "fixtures/a3/p3/ashr_frontend_mirror_summary.redacted.json"),
    frontendCodeCrawl: await readOptionalJson(root, "fixtures/a3/p3/ashr_frontend_code_crawl_summary.redacted.json"),
    peerBranchCalibration: await readOptionalJson(root, "fixtures/a3/p3/a3_peer_branch_calibration.redacted.json"),
    a2MultimodalComparison: await readOptionalJson(root, config.a2MultimodalComparison),
    a2MultimodalComparisonMeta: config.a2MultimodalComparison
      ? {
          ingest_mode: "peer_branch_redacted_sample",
          source_commit_alias: config.a2MultimodalComparisonSourceCommit || null,
          capability_state: config.a2MultimodalComparisonCapability || "contract_supported_not_production_verified"
        }
      : {},
    a2GradeResults: await readOptionalJson(root, config.a2GradeResults),
    a2ReleaseGate: await readOptionalJson(root, config.a2ReleaseGate),
    a2TrustedSpine: await readOptionalJson(
      root,
      config.a2TrustedSpine || "fixtures/a2/results/a2_trusted_spine_handoff.json"
    ),
    deploymentProbe: await readOptionalJson(root, config.deploymentProbe),
    deploymentAcceptance: await readOptionalJson(root, config.deploymentAcceptance),
    releaseArtifactManifest: await readOptionalJson(root, config.releaseArtifactManifest),
    releaseArtifactVerification: await readOptionalJson(root, config.releaseArtifactVerification),
    deliveryGoldenPath: await readOptionalJson(root, config.deliveryGoldenPath),
    githubCheckReadback: await readOptionalJson(root, config.githubCheckReadback),
    githubPrCommentReadback: await readOptionalJson(root, config.githubPrCommentReadback),
    githubRequiredCheckProof: await readOptionalJson(root, config.githubRequiredCheckProof),
    githubActionsArtifactReadback: await readOptionalJson(root, config.githubActionsArtifactReadback),
    releaseEvidence: await readReleaseEvidenceFixtures(root),
    storage: {
      mode: "fixture_file",
      db_ready: false,
      source_paths: Object.fromEntries(
        Object.entries(config).filter(([, value]) => typeof value === "string" && value.includes("/"))
      )
    }
  });

  if (config.comparisonBaselineSource && options.includeReleaseComparison !== false) {
    const baseline = await loadA3SourceSnapshot(config.comparisonBaselineSource, {
      ...options,
      includeReleaseComparison: false
    });
    snapshot = normalizeSnapshot({
      ...snapshot,
      releaseComparison: buildA3ReleaseComparison(baseline, snapshot)
    });
  }

  return snapshot;
}

export function createMemoryA3Store(seed = {}) {
  const snapshots = new Map();
  const reports = new Map();
  const shareLinks = new Map();
  const idempotencyReceipts = new Map();
  const auditEvents = [];
  const eventOutbox = [];
  const adminActionRequests = [];
  const reviewWorkflowRecords = [];
  const multimodalReviewAssignmentEvents = [];
  const releaseEvidenceReadbacks = [];
  const githubPublishReceipts = [];
  const deploymentReceipts = [];
  const deploymentReceiptReadbacks = [];
  const selfHostSandboxCalibrations = [];

  for (const [source, snapshot] of Object.entries(seed.sources || {})) {
    snapshots.set(source, normalizeSnapshot({ source, ...snapshot }));
  }
  if (seed.snapshot || seed.runFixture || seed.runs) {
    const snapshot = normalizeSnapshot({
      source: seed.source || "mock",
      runFixture: seed.runFixture || seed.runs || seed.snapshot?.runFixture || {},
      gradeFixture: seed.gradeFixture || seed.grades || seed.snapshot?.gradeFixture || {},
      ...seed.snapshot
    });
    storeSnapshotByScope(snapshots, snapshot);
  }
  for (const report of seed.reports || []) {
    const storageKey = reportStorageKey(report, snapshotForReport(snapshots, report));
    reports.set(storageKey, report);
    registerShareLink(shareLinks, report, storageKey);
  }
  for (const entry of seed.idempotencyReceipts || []) {
    idempotencyReceipts.set(entry.key, entry);
  }
  for (const event of seed.auditEvents || []) {
    auditEvents.push(event);
  }
  for (const event of seed.eventOutbox || []) {
    eventOutbox.push(sanitizeEventOutboxRow(event));
  }
  for (const request of seed.adminActionRequests || []) {
    adminActionRequests.push(request);
  }
  for (const record of seed.reviewWorkflowRecords || []) {
    reviewWorkflowRecords.push(record);
  }
  for (const event of seed.multimodalReviewAssignmentEvents || []) {
    multimodalReviewAssignmentEvents.push(event);
  }
  for (const readback of seed.releaseEvidenceReadbacks || []) {
    releaseEvidenceReadbacks.push(sanitizeReleaseEvidenceReadback(readback));
  }
  for (const receipt of seed.githubPublishReceipts || []) {
    githubPublishReceipts.push(sanitizeGitHubPublishReceipt(receipt));
  }
  for (const receipt of seed.deploymentReceipts || []) {
    deploymentReceipts.push(sanitizeDeploymentReceiptRecord(receipt));
  }
  for (const readback of seed.deploymentReceiptReadbacks || []) {
    if (isTrustedA3DeploymentReceiptAuthoritativeReadback(readback)) {
      deploymentReceiptReadbacks.push(structuredClone(readback));
    }
  }
  for (const calibration of seed.selfHostSandboxCalibrations || []) {
    selfHostSandboxCalibrations.push(validateSelfHostSandboxCalibration(calibration));
  }

  return {
    schema_version: A3_STORE_SCHEMA_VERSION,
    db_contract: A3_DB_CONTRACT,
    storage_mode: seed.storageMode || "memory",
    db_ready: seed.dbReady === true,
    github_executor_authority: seed.githubExecutorAuthority || "unavailable",

    async upsertSnapshot(source, snapshot) {
      const normalized = normalizeSnapshot({ source, ...snapshot });
      storeSnapshotByScope(snapshots, normalized);
      return normalized;
    },

    async getDashboardSnapshot(source = "mock", requestOptions = {}) {
      const snapshot = selectSnapshot(snapshots, source, requestOptions);
      const scopedAuditEvents = filterTenantScopedRecords(auditEvents, snapshot, requestOptions);
      const scopedAdminActionRequests = filterTenantScopedRecords(adminActionRequests, snapshot, requestOptions);
      const scopedReviewWorkflowRecords = filterTenantScopedRecords(reviewWorkflowRecords, snapshot, requestOptions);
      const scopedMultimodalReviewAssignmentEvents = filterTenantScopedRecords(
        multimodalReviewAssignmentEvents,
        snapshot,
        requestOptions
      );
      const scopedReleaseEvidenceReadbacks = filterTenantScopedRecords(releaseEvidenceReadbacks, snapshot, requestOptions);
      const scopedGitHubPublishReceipts = filterTenantScopedRecords(githubPublishReceipts, snapshot, requestOptions);
      const scopedDeploymentReceipts = filterTenantScopedRecords(deploymentReceipts, snapshot, requestOptions);
      const scopedDeploymentReceiptReadbacks = filterTenantScopedRecords(deploymentReceiptReadbacks, snapshot, requestOptions);
      const importReceipts = apiImportReceiptsFromLedger(idempotencyReceipts);
      const scopedImportReceipts = filterTenantScopedRecords(importReceipts, snapshot, requestOptions);
      return buildDashboardPayload(snapshot, this.storage_mode, {
        dbReady: this.db_ready,
        reports: filterReportsForSnapshot([...reports.values()], snapshot),
        auditEvents: scopedAuditEvents,
        eventOutbox,
        adminActionRequests: scopedAdminActionRequests,
        reviewWorkflowRecords: scopedReviewWorkflowRecords,
        multimodalReviewAssignmentEvents: scopedMultimodalReviewAssignmentEvents,
        releaseEvidenceReadbacks: scopedReleaseEvidenceReadbacks,
        githubPublishReceipts: scopedGitHubPublishReceipts,
        deploymentReceipts: scopedDeploymentReceipts,
        deploymentReceiptReadbacks: scopedDeploymentReceiptReadbacks,
        actor: requestOptions.actor,
        auth: requestOptions.auth,
        importReceipts: scopedImportReceipts,
        enforceScope: requestOptions.enforceScope === true,
        aggregateScopeStatus: buildAggregateScopeStatus({
          auditEvents,
          adminActionRequests,
          reviewWorkflowRecords,
          multimodalReviewAssignmentEvents,
          releaseEvidenceReadbacks,
          githubPublishReceipts,
          deploymentReceipts,
          deploymentReceiptReadbacks,
          importReceipts
        }, snapshot, requestOptions)
      });
    },

    async getSelfHostSandboxCalibration(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const tenantScope = {
        organization_id: scopedSnapshot.organizationId,
        tenant_id: scopedSnapshot.tenantId,
        workspace_id: scopedSnapshot.workspaceId,
        project_id: scopedSnapshot.projectId,
        environment_id: scopedSnapshot.environmentId
      };
      const calibration = selfHostSandboxCalibrations
        .filter((item) => tenantScopeMatches(item.tenant_scope, tenantScope))
        .sort((left, right) => String(right.observed_at).localeCompare(String(left.observed_at)))[0];
      if (!calibration) return null;
      return {
        ...structuredClone(calibration),
        dashboard_source: snapshot.source,
        access_contract: {
          required_permission: "deployment:read",
          tenant_scope_enforced: options.enforceScope === true,
          hosted_read_audited: options.enforceScope === true,
          raw_probe_payload_exposed: false
        }
      };
    },

    async listRuns(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      return extractRunSummaries(snapshot);
    },

    async getRun(runId, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture)
        .filter((item) => item.run_id === runId);
      const run = extractRunRecords(snapshot.runFixture)
        .find((item) => item.run_id === runId);
      if (!run && !cases.length) {
        return null;
      }
      return {
        schema_version: "a3.api_run_detail.v1",
        source: snapshot.source,
        run: run || { run_id: runId, cases },
        cases,
        summary: summarizeCases(cases)
      };
    },

    async getCase(caseId, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const item = normalizeCases(snapshot.runFixture, snapshot.gradeFixture)
        .find((candidate) => candidate.case_id === caseId);
      if (!item) {
        return null;
      }
      return {
        schema_version: "a3.api_case_detail.v1",
        source: snapshot.source,
        case: item
      };
    },

    async importA1RunResult(runResult, options = {}) {
      const source = normalizeSourceKey(options.source || runResult?.source || "api-ingest");
      const validation = validateA1RunResult(runResult);
      if (!validation.valid) {
        throw new A3StoreValidationError("A1 RunResult import failed validation.", validation.details, {
          requestType: "a1_run_result_import",
          source
        });
      }
      const payloadHash = sha256(stableJson(runResult || {}));
      const idempotencySource = scopedIdempotencySource(source, options, runResult);
      const replay = getIdempotentReplay(idempotencyReceipts, "a1_run_result_import", idempotencySource, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const existing = findSnapshotForMutation(snapshots, source, options);
      const normalized = normalizeSnapshot({
        ...(existing || {}),
        source,
        source_label: options.sourceLabel || existing?.source_label || "API Ingest",
        organizationId: options.organizationId || existing?.organizationId || runResult?.organization_id,
        tenantId: options.tenantId || existing?.tenantId || runResult?.tenant_id,
        workspaceId: options.workspaceId || existing?.workspaceId || runResult?.workspace_id,
        projectId: options.projectId || existing?.projectId || runResult?.project_id,
        environmentId: options.environmentId || existing?.environmentId || runResult?.environment_id,
        runFixture: runResult || {},
        gradeFixture: existing?.gradeFixture || {},
        storage: {
          mode: this.storage_mode || "memory",
          db_ready: this.db_ready === true,
          ingest_source: "a1_run_result_api"
        }
      });
      storeSnapshotByScope(snapshots, normalized);
      const receipt = buildIngestReceipt("a3.a1_run_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture),
        idempotencyKey: options.idempotencyKey,
        payloadHash
      });
      rememberIdempotentReceipt(idempotencyReceipts, "a1_run_result_import", idempotencySource, options.idempotencyKey, payloadHash, receipt);
      return receipt;
    },

    async importA2GradeResult(gradeResult, options = {}) {
      const source = normalizeSourceKey(options.source || gradeResult?.source || "api-ingest");
      const validation = validateA2GradeResult(gradeResult);
      if (!validation.valid) {
        throw new A3StoreValidationError("A2 GradeResult import failed validation.", validation.details, {
          requestType: "a2_grade_result_import",
          source
        });
      }
      const payloadHash = sha256(stableJson(gradeResult || {}));
      const idempotencySource = scopedIdempotencySource(source, options, gradeResult);
      const replay = getIdempotentReplay(idempotencyReceipts, "a2_grade_result_import", idempotencySource, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const existing = findSnapshotForMutation(snapshots, source, options);
      const mergedGradeFixture = mergeGradeFixtures(existing?.gradeFixture, gradeResult);
      const normalized = normalizeSnapshot({
        ...(existing || {}),
        source,
        source_label: options.sourceLabel || existing?.source_label || "API Ingest",
        organizationId: options.organizationId || existing?.organizationId || gradeResult?.organization_id,
        tenantId: options.tenantId || existing?.tenantId || gradeResult?.tenant_id,
        workspaceId: options.workspaceId || existing?.workspaceId || gradeResult?.workspace_id,
        projectId: options.projectId || existing?.projectId || gradeResult?.project_id,
        environmentId: options.environmentId || existing?.environmentId || gradeResult?.environment_id,
        runFixture: existing?.runFixture || {},
        gradeFixture: mergedGradeFixture,
        storage: {
          mode: this.storage_mode || "memory",
          db_ready: this.db_ready === true,
          ingest_source: "a2_grade_result_api"
        }
      });
      storeSnapshotByScope(snapshots, normalized);
      const receipt = buildIngestReceipt("a3.a2_grade_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture),
        idempotencyKey: options.idempotencyKey,
        payloadHash
      });
      rememberIdempotentReceipt(idempotencyReceipts, "a2_grade_result_import", idempotencySource, options.idempotencyKey, payloadHash, receipt);
      return receipt;
    },

    async importA2MultimodalComparison(comparison, options = {}) {
      const source = normalizeSourceKey(options.source || "api-ingest");
      requireMutationIdempotencyKey(options, "a2_multimodal_comparison_import", source);
      const existing = findSnapshotForMutation(snapshots, source, options);
      const tenantScope = tenantScopeRecordFields(options, existing || {});
      const validation = validateA2MultimodalComparison(comparison, { tenantScope });
      if (!validation.valid) {
        throw new A3StoreValidationError("A2 multimodal comparison import failed validation.", validation.details, {
          requestType: "a2_multimodal_comparison_import",
          source
        });
      }
      const payloadHash = sha256(stableJson(comparison));
      const idempotencySource = scopedIdempotencySource(source, options, existing || tenantScope);
      const replay = getIdempotentReplay(
        idempotencyReceipts,
        "a2_multimodal_comparison_import",
        idempotencySource,
        options.idempotencyKey,
        payloadHash
      );
      if (replay) return replay;

      const importedAt = options.importedAt || new Date().toISOString();
      const normalized = normalizeSnapshot({
        ...(existing || {}),
        source,
        source_label: options.sourceLabel || existing?.source_label || "A2 Multimodal API Ingest",
        ...tenantScope,
        runFixture: existing?.runFixture || {},
        gradeFixture: existing?.gradeFixture || {},
        a2MultimodalComparison: comparison,
        a2MultimodalComparisonMeta: {
          ingest_mode: "tenant_scoped_api",
          source_commit_alias: null,
          capability_state: "contract_supported_unverified_candidate_binding",
          imported_at: importedAt,
          payload_hash: payloadHash
        },
        storage: {
          mode: this.storage_mode || "memory",
          db_ready: this.db_ready === true,
          ingest_source: "a2_multimodal_comparison_api"
        }
      });
      storeSnapshotByScope(snapshots, normalized);
      const queue = buildMultimodalQueueForSnapshot(normalized);
      const receipt = {
        schema_version: "a3.a2_multimodal_comparison_ingest.v1",
        source,
        ...tenantScope,
        storage_mode: normalized.storage.mode,
        db_ready: normalized.storage.db_ready === true,
        payload_hash: payloadHash,
        comparison_count: queue.summary.comparison_count,
        review_required_count: queue.summary.review_required_count,
        queue_receipt_count: queue.summary.queue_receipt_count,
        upstream_release_authority: false,
        candidate_binding_verified: false,
        release_decision_changed: false,
        imported_at: importedAt,
        idempotency: {
          key_present: true,
          duplicate: false,
          status: "recorded"
        }
      };
      auditEvents.push(multimodalComparisonAuditEvent(receipt, auditEvents.length));
      const outboxRow = recordEventOutbox(eventOutbox, {
        source,
        eventType: "a2.multimodal_comparison_imported",
        resourceType: "multimodal_review_snapshot",
        resourceId: payloadHash,
        tenantScope,
        actorHash: options.actorHash || options.actor,
        createdAt: importedAt,
        payload: receipt,
        usageMeter: {
          meter: "a2_multimodal_comparison_imports",
          quantity: 1
        }
      });
      const receiptWithEvent = attachEventEnvelopeReceipt(receipt, outboxRow);
      rememberIdempotentReceipt(
        idempotencyReceipts,
        "a2_multimodal_comparison_import",
        idempotencySource,
        options.idempotencyKey,
        payloadHash,
        receiptWithEvent
      );
      return receiptWithEvent;
    },

    async getMultimodalReviewQueue(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      return buildMultimodalQueueForSnapshot(
        snapshot,
        filterTenantScopedRecords(multimodalReviewAssignmentEvents, snapshot, options),
        { now: options.now }
      );
    },

    async mutateMultimodalReviewAssignment(queueId, input = {}, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      requireMutationIdempotencyKey(options, "multimodal_review_assignment", snapshot.source);
      const scopedEvents = filterTenantScopedRecords(multimodalReviewAssignmentEvents, snapshot, options);
      const queue = buildMultimodalQueueForSnapshot(snapshot, scopedEvents, { now: options.now });
      const tenantScope = eventTenantScopeFromRecord({}, snapshot);
      const payloadHash = sha256(stableJson({
        queue_id: queueId,
        assignment: input,
        tenant_scope: tenantScope
      }));
      const idempotencySource = scopedIdempotencySource(snapshot.source, options, snapshot);
      const replay = getIdempotentReplay(
        idempotencyReceipts,
        "multimodal_review_assignment",
        idempotencySource,
        options.idempotencyKey,
        payloadHash
      );
      if (replay) return replay;

      const transition = planA3MultimodalReviewAssignmentTransition(queue, scopedEvents, input, {
        queueId,
        source: snapshot.source,
        tenantScope,
        actorHash: options.actorHash,
        actorRole: options.actorRole,
        now: options.now
      });
      if (!transition.valid) {
        if (transition.statusCode === 404) throw new A3StoreResourceNotFoundError();
        throw new A3StoreValidationError("Multimodal review assignment action was rejected.", transition.details, {
          requestType: "multimodal_review_assignment",
          source: snapshot.source,
          statusCode: transition.statusCode,
          error: transition.error
        });
      }

      multimodalReviewAssignmentEvents.push(transition.event);
      auditEvents.push(multimodalReviewAssignmentAuditEvent(
        transition.event,
        multimodalReviewAssignmentEvents.length - 1
      ));
      const receipt = {
        schema_version: A3_MULTIMODAL_REVIEW_ASSIGNMENT_RECEIPT_SCHEMA_VERSION,
        source: snapshot.source,
        ...tenantScopeRecordFields(snapshot),
        queue_id: queueId,
        event_id: transition.event.event_id,
        event_hash: transition.event.event_hash,
        action: input.action,
        status: transition.operational_state.status,
        version: transition.operational_state.version,
        assigned_reviewer_hash: transition.operational_state.assigned_reviewer_hash,
        lease_expires_at: transition.operational_state.lease_expires_at,
        reason_code: transition.operational_state.reason_code,
        release_authority: false,
        a2_decision_recomputed: false,
        release_decision_changed: false,
        created_at: transition.event.created_at,
        safety: {
          raw_reviewer_identity_included: false,
          raw_model_payload_included: false,
          raw_media_included: false,
          signed_url_included: false,
          secret_values_included: false
        }
      };
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: `review.multimodal_assignment.${transition.event.event_type}`,
        resourceType: "multimodal_review_assignment",
        resourceId: transition.event.event_id,
        tenantScope,
        actorHash: options.actorHash,
        createdAt: transition.event.created_at,
        payload: receipt,
        usageMeter: {
          meter: "multimodal_review_assignment_actions",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(
        attachEventEnvelopeReceipt(receipt, outboxRow),
        options.idempotencyKey
      );
      rememberIdempotentReceipt(
        idempotencyReceipts,
        "multimodal_review_assignment",
        idempotencySource,
        options.idempotencyKey,
        payloadHash,
        receiptWithEvent
      );
      return receiptWithEvent;
    },

    async getSaasAdminConsole(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      return attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, snapshot, options), {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
    },

    async getEnterpriseReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const adminConsole = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, snapshot, options), {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      return buildEnterpriseReadinessReport({
        runFixture: snapshot.runFixture,
        gradeFixture: snapshot.gradeFixture,
        adminConsole,
        dbContract: A3_DB_CONTRACT
      });
    },

    async getDbMigrationPlan(options = {}) {
      return buildA3SqlMigrationPlan({
        dialect: options.dialect || "postgres"
      });
    },

    async getUsageLedger(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return buildA3UsageLedger(snapshot, {
        reports: filterReportsForSnapshot([...reports.values()], scopedSnapshot),
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        releaseEvidenceReadbacks: filterTenantScopedRecords(releaseEvidenceReadbacks, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        periodStart: options.periodStart,
        periodEnd: options.periodEnd
      });
    },

    async getBillingReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const usageLedger = await this.getUsageLedger(options);
      const adminConsole = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, scopedSnapshot, options), {
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      return buildA3BillingReadiness({
        usageLedger,
        adminConsole
      }, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
    },

    async getBillingMigrationReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return buildA3BillingMigrationReadiness({
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
    },

    async getLiveWorkflowReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, filterTenantScopedRecords(githubPublishReceipts, scopedSnapshot, options), {
        source: snapshot.source,
        releaseId: releaseEvidenceReleaseId(snapshot),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const usageLedger = await this.getUsageLedger(options);
      const billingReadiness = await this.getBillingReadiness(options);
      const reportCenter = await this.getReportCenter(options);
      const reviewWorkflow = await this.getReviewWorkflow(options);
      const saasAdmin = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, scopedSnapshot, options), {
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const eventOutboxDashboard = buildEventOutboxDashboard(eventOutbox, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
      return buildA3LiveWorkflowReadiness({
        source: snapshot.source,
        releaseEvidence: releaseEvidenceInput,
        reviewWorkflow,
        usageLedger,
        billingReadiness,
        reportCenter,
        saasAdmin,
        eventOutbox: eventOutboxDashboard
      }, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
    },

    async getLiveOpsControlPlane(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, filterTenantScopedRecords(githubPublishReceipts, scopedSnapshot, options), {
        source: snapshot.source,
        releaseId: releaseEvidenceReleaseId(snapshot),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const usageLedger = await this.getUsageLedger(options);
      const billingReadiness = await this.getBillingReadiness(options);
      const reportCenter = await this.getReportCenter(options);
      const reviewWorkflow = await this.getReviewWorkflow(options);
      const saasAdmin = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, scopedSnapshot, options), {
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const eventOutboxDashboard = buildEventOutboxDashboard(eventOutbox, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
      const liveWorkflowReadiness = await this.getLiveWorkflowReadiness(options);
      return buildA3LiveOpsControlPlane({
        source: snapshot.source,
        releaseEvidence: releaseEvidenceInput,
        reviewWorkflow,
        usageLedger,
        billingReadiness,
        reportCenter,
        saasAdmin,
        eventOutbox: eventOutboxDashboard,
        liveWorkflowReadiness
      }, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
    },

    async getNotificationControlPlane(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, filterTenantScopedRecords(githubPublishReceipts, scopedSnapshot, options), {
        source: snapshot.source,
        releaseId: releaseEvidenceReleaseId(snapshot),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const usageLedger = await this.getUsageLedger(options);
      const reportCenter = await this.getReportCenter(options);
      const reviewWorkflow = await this.getReviewWorkflow(options);
      const eventOutboxDashboard = buildEventOutboxDashboard(eventOutbox, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
      const liveOpsControlPlane = await this.getLiveOpsControlPlane(options);
      return buildA3NotificationControlPlane({
        source: snapshot.source,
        releaseEvidence: releaseEvidenceInput,
        liveOpsControlPlane,
        reviewWorkflow,
        eventOutbox: eventOutboxDashboard,
        reportCenter,
        usageLedger
      }, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
    },

    async getCommercialApiContract(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return buildA3CommercialApiContract({
        source: "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: options.environmentId || "staging"
      });
    },

    async getPeerBranchCalibration(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return {
        ...summarizeA3PeerBranchCalibration(snapshot.peerBranchCalibration),
        tenant_scope: {
          organization_id: scopedSnapshot.organizationId,
          tenant_id: scopedSnapshot.tenantId,
          workspace_id: scopedSnapshot.workspaceId,
          project_id: scopedSnapshot.projectId,
          environment_id: scopedSnapshot.environmentId
        }
      };
    },

    async getA1A2EvidenceSpine(options = {}) {
      const dashboard = await this.getDashboardSnapshot(options.source || "mock", {
        actor: options.actor,
        auth: options.auth
      });
      return dashboard.a1_a2_evidence_spine;
    },

    async planSaasAdminAction(action, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const consoleState = buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      return planSaasAdminAction(action, {
        releaseGate: {
          decision: consoleState.trust.release_gate_decision,
          decision_label: consoleState.trust.release_gate_label
        },
        usage: consoleState.usage,
        cloudShell: consoleState.cloud_management,
        organizationId: consoleState.organization.organization_id,
        projectId: consoleState.project.project_id,
        createdAt: options.createdAt
      });
    },

    async submitSaasAdminAction(action, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const recordScope = tenantScopeRecordFields(options, snapshot);
      const plannedAt = options.requestedAt || options.createdAt || new Date().toISOString();
      const plan = await this.planSaasAdminAction(action, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        createdAt: plannedAt
      });
      const actorHash = options.actor
        ? sha256(String(options.actor)).slice(0, 16)
        : options.actorHash || "actor_[REDACTED_HASH]";
      const idempotencyPayloadHash = sha256(stableJson({
        action: plan.action,
        source: snapshot.source,
        organization_id: plan.organization_id,
        project_id: plan.project_id,
        actor_hash: actorHash,
        reason: options.reason || plan.reason || "",
        target: sanitizeAdminActionTarget(options.target)
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "saas_admin_action_request", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const requestHash = sha256(stableJson({
        action: plan.action,
        source: snapshot.source,
        organization_id: plan.organization_id,
        project_id: plan.project_id,
        actor_hash: actorHash,
        requested_at: plannedAt,
        reason: options.reason || plan.reason || ""
      }));
      const request = buildSaasAdminActionRequest(plan.action, {
        plan,
        requestId: `aar_${requestHash.slice(0, 12)}`,
        actorHash,
        requestedAt: plannedAt,
        organizationId: plan.organization_id,
        projectId: plan.project_id
      });
      const storedRequest = sanitizeAdminActionRequest({
        ...request,
        ...recordScope,
        source: snapshot.source,
        request_hash: requestHash,
        requested_by_hash: actorHash,
        reason: options.reason || request.reason,
        target: sanitizeAdminActionTarget(options.target)
      });
      adminActionRequests.push(storedRequest);
      auditEvents.push({
        event_id: `aar_evt_${sha256(`${storedRequest.request_id}:${auditEvents.length}`).slice(0, 12)}`,
        source: snapshot.source,
        ...recordScope,
        event_type: "saas_admin_action_requested",
        subject_id: storedRequest.request_id,
        payload: {
          schema_version: storedRequest.schema_version,
          request_id: storedRequest.request_id,
          action: storedRequest.action,
          area: storedRequest.area,
          mode: storedRequest.mode,
          status: storedRequest.status,
          real_cloud_mutation_performed: false,
          secret_values_included: false
        },
        created_at: storedRequest.requested_at,
        redacted: true
      });
      const receipt = {
        schema_version: "a3.saas_admin_action_receipt.v1",
        source: snapshot.source,
        ...recordScope,
        request_id: storedRequest.request_id,
        action: storedRequest.action,
        area: storedRequest.area,
        mode: storedRequest.mode,
        status: storedRequest.status,
        request_hash: storedRequest.request_hash,
        real_cloud_mutation_performed: false,
        secret_values_included: false,
        audit_event_recorded: true,
        safety: storedRequest.safety,
        next_step: storedRequest.next_step
      };
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "admin.action_requested",
        resourceType: "saas_admin_action_request",
        resourceId: storedRequest.request_id,
        tenantScope: {
          organization_id: storedRequest.organization_id,
          tenant_id: snapshot.tenantId,
          workspace_id: snapshot.workspaceId,
          project_id: storedRequest.project_id,
          environment_id: snapshot.environmentId
        },
        actorHash: storedRequest.actor_hash,
        createdAt: storedRequest.requested_at,
        payload: receipt,
        usageMeter: {
          meter: "admin_action_requests",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(receipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "saas_admin_action_request", snapshot.source, options.idempotencyKey, idempotencyPayloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async listSaasAdminActionRequests(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const organizationId = options.organizationId || snapshot.organizationId;
      const projectId = options.projectId || snapshot.projectId;
      const requests = filterAdminActionRequests(
        filterTenantScopedRecords(adminActionRequests, snapshot, options),
        { organizationId, projectId }
      );
      return {
        schema_version: "a3.saas_admin_action_request_list.v1",
        source: snapshot.source,
        organization_id: organizationId,
        project_id: projectId,
        summary: summarizeSaasAdminActionRequests(requests),
        requests
      };
    },

    async submitReviewWaiver(waiver, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const idempotencyPayloadHash = sha256(stableJson({
        record_type: "waiver",
        source: snapshot.source,
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        waiver: redactPotentialSecret(waiver)
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "review_waiver_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const record = sanitizeReviewWorkflowRecord({
        ...buildReviewWorkflowRecord("waiver", waiver, snapshot, {
          source: snapshot.source,
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId,
          requestedAt: options.requestedAt,
          generatedAt: options.generatedAt,
          releaseVersion: options.releaseVersion,
          environment: options.environment,
          headSha: options.headSha
        }),
        ...tenantScopeRecordFields(options, snapshot),
        payload: waiver
      });
      reviewWorkflowRecords.push(record);
      auditEvents.push(reviewWorkflowAuditEvent(record, auditEvents.length));
      const receipt = reviewWorkflowReceipt(record);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "waiver.submitted",
        resourceType: "review_workflow_record",
        resourceId: record.record_id,
        tenantScope: eventTenantScopeFromRecord(record, snapshot),
        actorHash: record.actor_hash || record.requested_by_hash,
        createdAt: record.created_at || record.requested_at,
        payload: receipt,
        usageMeter: {
          meter: "review_waivers",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(receipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "review_waiver_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async submitReviewApproval(approval, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const idempotencyPayloadHash = sha256(stableJson({
        record_type: "approval",
        source: snapshot.source,
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        approval: redactPotentialSecret(approval),
        waiver_id: approval?.waiver_id || null
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "review_approval_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const waiverRecord = [...reviewWorkflowRecords].reverse().find((item) => (
        item.record_type === "waiver"
        && item.subject?.waiver_id === approval?.waiver_id
        && strictTenantRecordMatches(item, snapshot)
      ));
      const record = sanitizeReviewWorkflowRecord({
        ...buildReviewWorkflowRecord("approval", approval, snapshot, {
          source: snapshot.source,
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId,
          requestedAt: options.requestedAt,
          generatedAt: options.generatedAt,
          releaseVersion: options.releaseVersion,
          environment: options.environment,
          headSha: options.headSha,
          waiver: waiverRecord?.payload || {}
        }),
        ...tenantScopeRecordFields(options, snapshot),
        payload: approval
      });
      reviewWorkflowRecords.push(record);
      auditEvents.push(reviewWorkflowAuditEvent(record, auditEvents.length));
      const receipt = reviewWorkflowReceipt(record);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "approval.submitted",
        resourceType: "review_workflow_record",
        resourceId: record.record_id,
        tenantScope: eventTenantScopeFromRecord(record, snapshot),
        actorHash: record.actor_hash || record.requested_by_hash,
        createdAt: record.created_at || record.requested_at,
        payload: receipt,
        usageMeter: {
          meter: "review_approvals",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(receipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "review_approval_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async submitReviewDenial(denial, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const idempotencyPayloadHash = sha256(stableJson({
        record_type: "denial",
        source: snapshot.source,
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        denial: redactPotentialSecret(denial)
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "review_denial_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const record = sanitizeReviewWorkflowRecord({
        ...buildReviewWorkflowRecord("denial", denial, snapshot, {
          source: snapshot.source,
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId,
          requestedAt: options.requestedAt,
          generatedAt: options.generatedAt,
          releaseVersion: options.releaseVersion,
          environment: options.environment,
          headSha: options.headSha
        }),
        ...tenantScopeRecordFields(options, snapshot),
        payload: denial
      });
      reviewWorkflowRecords.push(record);
      auditEvents.push(reviewWorkflowAuditEvent(record, auditEvents.length));
      const receipt = reviewWorkflowReceipt(record);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "denial.submitted",
        resourceType: "review_workflow_record",
        resourceId: record.record_id,
        tenantScope: eventTenantScopeFromRecord(record, snapshot),
        actorHash: record.actor_hash || record.requested_by_hash,
        createdAt: record.created_at || record.requested_at,
        payload: receipt,
        usageMeter: {
          meter: "review_denials",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(receipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "review_denial_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async getReviewWorkflow(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      return buildReviewWorkflowIndex(filterReviewWorkflowRecords(filterTenantScopedRecords(reviewWorkflowRecords, snapshot, options), {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        durableStorageReady: true
      });
    },

    async listDeploymentReceipts(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const dashboard = await this.getDashboardSnapshot(snapshot.source, options);
      return dashboard.deployment_receipt_inbox;
    },

    async submitDeploymentReceipt(input = {}, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      requireIdempotencyKey(options, "deployment_receipt_submit", snapshot.source);
      const dashboard = await this.getDashboardSnapshot(snapshot.source, options);
      const context = deploymentReceiptContext(snapshot, dashboard, options);
      const openBlockers = new Set((dashboard.deployment_handoff?.blocking_items || []).map((item) => item.id));
      if (!openBlockers.has(input.blocker_id || input.blockerId)) {
        throw new A3StoreValidationError("Deployment receipt does not match a current blocker.", [
          { field: "blocker_id", issue: "blocker_not_currently_open" }
        ], {
          requestType: "deployment_receipt_submit",
          source: snapshot.source
        });
      }
      const built = buildA3DeploymentReceiptSubmission(input, context);
      if (!built.valid) {
        throw new A3StoreValidationError("Deployment receipt failed metadata validation.", built.errors, {
          requestType: "deployment_receipt_submit",
          source: snapshot.source
        });
      }
      const idempotencySource = scopedIdempotencySource(snapshot.source, options, snapshot);
      const replay = getIdempotentReplay(
        idempotencyReceipts,
        "deployment_receipt_submit",
        idempotencySource,
        options.idempotencyKey,
        built.fingerprint
      );
      if (replay) return replay;

      const existing = deploymentReceipts.find((item) => (
        item.receipt_id === built.record.receipt_id && strictTenantRecordMatches(item, snapshot)
      ));
      if (existing) {
        const duplicate = attachIdempotencyReceipt({
          ...existing,
          duplicate_content: true
        }, options.idempotencyKey);
        duplicate.idempotency.status = "duplicate_content";
        duplicate.idempotency.duplicate = true;
        rememberIdempotentReceipt(
          idempotencyReceipts,
          "deployment_receipt_submit",
          idempotencySource,
          options.idempotencyKey,
          built.fingerprint,
          duplicate
        );
        return duplicate;
      }

      const auditEvent = deploymentReceiptAuditEvent(built.record, "submitted", auditEvents.length);
      const storedRecord = sanitizeDeploymentReceiptRecord({
        ...built.record,
        audit_event_id: auditEvent.event_id
      });
      deploymentReceipts.push(storedRecord);
      auditEvents.push(auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "deployment.receipt_submitted",
        resourceType: "deployment_receipt",
        resourceId: storedRecord.receipt_id,
        tenantScope: storedRecord.tenant_scope,
        actorHash: storedRecord.submitted_by_hash,
        createdAt: storedRecord.submitted_at,
        payload: deploymentReceiptEventPayload(storedRecord, "submitted"),
        usageMeter: { meter: "deployment_receipt_submissions", quantity: 1 }
      });
      const receipt = attachIdempotencyReceipt(
        attachEventEnvelopeReceipt(storedRecord, outboxRow),
        options.idempotencyKey
      );
      rememberIdempotentReceipt(
        idempotencyReceipts,
        "deployment_receipt_submit",
        idempotencySource,
        options.idempotencyKey,
        built.fingerprint,
        receipt
      );
      return receipt;
    },

    async reviewDeploymentReceipt(receiptId, review = {}, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      requireIdempotencyKey(options, "deployment_receipt_review", snapshot.source);
      const index = deploymentReceipts.findIndex((item) => (
        item.receipt_id === receiptId && strictTenantRecordMatches(item, snapshot)
      ));
      if (index < 0) return null;

      const current = deploymentReceipts[index];
      const payloadHash = sha256(stableJson({
        receipt_id: receiptId,
        action: review.action,
        reason_code: review.reason_code || review.reasonCode,
        expected_version: review.expected_version ?? review.expectedVersion,
        source: snapshot.source,
        tenant_scope: current.tenant_scope
      }));
      const idempotencySource = scopedIdempotencySource(snapshot.source, options, snapshot);
      const replay = getIdempotentReplay(
        idempotencyReceipts,
        "deployment_receipt_review",
        idempotencySource,
        options.idempotencyKey,
        payloadHash
      );
      if (replay) return replay;

      const reviewed = reviewA3DeploymentReceipt(current, review, {
        actor_hash: options.actor
          ? sha256(String(options.actor)).slice(0, 16)
          : options.actorHash || "actor_[REDACTED_HASH]",
        reviewed_at: options.reviewedAt
      });
      if (!reviewed.valid) {
        const versionConflict = reviewed.errors.some((item) => item.issue === "version_conflict");
        throw new A3StoreValidationError("Deployment receipt review failed validation.", reviewed.errors, {
          requestType: "deployment_receipt_review",
          source: snapshot.source,
          statusCode: versionConflict ? 409 : 400,
          error: versionConflict ? "version_conflict" : "validation_error"
        });
      }

      const auditEvent = deploymentReceiptAuditEvent(reviewed.record, "reviewed", auditEvents.length);
      const storedRecord = sanitizeDeploymentReceiptRecord({
        ...reviewed.record,
        audit_event_id: current.audit_event_id,
        latest_audit_event_id: auditEvent.event_id
      });
      deploymentReceipts[index] = storedRecord;
      auditEvents.push(auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: `deployment.receipt_${storedRecord.status}`,
        resourceType: "deployment_receipt",
        resourceId: storedRecord.receipt_id,
        tenantScope: storedRecord.tenant_scope,
        actorHash: storedRecord.reviewed_by_hash,
        createdAt: storedRecord.reviewed_at,
        payload: deploymentReceiptEventPayload(storedRecord, "reviewed"),
        usageMeter: { meter: "deployment_receipt_reviews", quantity: 1 }
      });
      const receipt = attachIdempotencyReceipt(
        attachEventEnvelopeReceipt(storedRecord, outboxRow),
        options.idempotencyKey
      );
      rememberIdempotentReceipt(
        idempotencyReceipts,
        "deployment_receipt_review",
        idempotencySource,
        options.idempotencyKey,
        payloadHash,
        receipt
      );
      return receipt;
    },

    async verifyDeploymentReceiptAuthoritatively(receiptId, resolver, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      requireIdempotencyKey(options, "deployment_receipt_authoritative_verify", snapshot.source);
      if (options.trustedResolver !== true || options.principalKind !== "service_account" || typeof resolver !== "function") {
        throw new A3StoreValidationError("Authoritative verification requires a trusted server resolver and service account.", [
          { field: "resolver", issue: "trusted_server_resolver_required" },
          { field: "principal_kind", issue: "service_account_required" }
        ], {
          requestType: "deployment_receipt_authoritative_verify",
          source: snapshot.source,
          statusCode: 403,
          error: "trusted_deployment_verifier_required"
        });
      }
      const index = deploymentReceipts.findIndex((item) => (
        item.receipt_id === receiptId && strictTenantRecordMatches(item, snapshot)
      ));
      if (index < 0) return null;

      const current = deploymentReceipts[index];
      const expectedVersion = Number(options.expectedVersion ?? options.expected_version);
      const requestHash = sha256(stableJson({
        receipt_id: receiptId,
        expected_version: expectedVersion,
        source: snapshot.source,
        tenant_scope: current.tenant_scope,
        resolver_id_alias: options.resolverIdAlias || options.resolver_id_alias || "unknown"
      }));
      const idempotencySource = scopedIdempotencySource(snapshot.source, options, snapshot);
      const replay = getIdempotentReplay(
        idempotencyReceipts,
        "deployment_receipt_authoritative_verify",
        idempotencySource,
        options.idempotencyKey,
        requestHash
      );
      if (replay) return replay;
      if (!Number.isInteger(expectedVersion) || expectedVersion < 1 || expectedVersion !== Number(current.version)) {
        throw new A3StoreValidationError("Deployment receipt authoritative verification has a stale version.", [
          { field: "expected_version", issue: "version_conflict" }
        ], {
          requestType: "deployment_receipt_authoritative_verify",
          source: snapshot.source,
          statusCode: 409,
          error: "version_conflict"
        });
      }
      if (current.status !== "acknowledged") {
        throw new A3StoreValidationError("Deployment receipt must be acknowledged before authoritative verification.", [
          { field: "receipt.status", issue: "acknowledged_receipt_required" }
        ], {
          requestType: "deployment_receipt_authoritative_verify",
          source: snapshot.source
        });
      }

      const previous = deploymentReceiptReadbacks
        .filter((item) => item.receipt_id === receiptId && strictTenantRecordMatches(item, snapshot))
        .sort((left, right) => Number(right.sequence || 0) - Number(left.sequence || 0))[0] || null;
      let resolverOutput;
      try {
        resolverOutput = await resolver({
          receipt: structuredClone(current),
          previous_readback: previous ? structuredClone(previous) : null,
          source: snapshot.source,
          tenant_scope: structuredClone(current.tenant_scope)
        });
      } catch {
        throw new A3StoreValidationError("The authoritative deployment verifier did not return a usable readback.", [
          { field: "resolver", issue: "resolver_failed" }
        ], {
          requestType: "deployment_receipt_authoritative_verify",
          source: snapshot.source,
          statusCode: 502,
          error: "authoritative_verifier_failed"
        });
      }
      const built = buildA3DeploymentReceiptAuthoritativeReadback(current, resolverOutput, {
        trusted_resolver: true,
        principal_kind: "service_account",
        resolver_id_alias: options.resolverIdAlias || options.resolver_id_alias,
        expected_version: expectedVersion,
        previous_readback: previous
      });
      if (!built.valid) {
        throw new A3StoreValidationError("The authoritative deployment verifier returned an invalid readback.", built.errors, {
          requestType: "deployment_receipt_authoritative_verify",
          source: snapshot.source,
          statusCode: 502,
          error: "authoritative_verifier_invalid"
        });
      }

      const existing = deploymentReceiptReadbacks.find((item) => (
        item.readback_id === built.record.readback_id && strictTenantRecordMatches(item, snapshot)
      ));
      if (existing) {
        const duplicate = attachIdempotencyReceipt({ ...existing, duplicate_content: true }, options.idempotencyKey);
        duplicate.idempotency.status = "duplicate_content";
        duplicate.idempotency.duplicate = true;
        rememberIdempotentReceipt(
          idempotencyReceipts,
          "deployment_receipt_authoritative_verify",
          idempotencySource,
          options.idempotencyKey,
          requestHash,
          duplicate
        );
        return duplicate;
      }

      const storedReadback = structuredClone(built.record);
      deploymentReceiptReadbacks.push(storedReadback);
      const auditEvent = deploymentReceiptReadbackAuditEvent(storedReadback, auditEvents.length);
      auditEvents.push(auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: storedReadback.production_verified
          ? "deployment.receipt_authoritatively_verified"
          : "deployment.receipt_authoritatively_rejected",
        resourceType: "deployment_receipt_readback",
        resourceId: storedReadback.readback_id,
        tenantScope: storedReadback.tenant_scope,
        actorHash: options.actorHash || options.actor_hash || storedReadback.resolver_id_alias,
        createdAt: storedReadback.verified_at,
        payload: deploymentReceiptReadbackEventPayload(storedReadback),
        usageMeter: { meter: "deployment_receipt_authoritative_verifications", quantity: 1 }
      });
      const result = attachIdempotencyReceipt(
        attachEventEnvelopeReceipt({
          ...storedReadback,
          audit_event_id: auditEvent.event_id
        }, outboxRow),
        options.idempotencyKey
      );
      rememberIdempotentReceipt(
        idempotencyReceipts,
        "deployment_receipt_authoritative_verify",
        idempotencySource,
        options.idempotencyKey,
        requestHash,
        result
      );
      return result;
    },

    async authorizeLiveRelease(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      return buildLiveReleaseAuthorization(snapshot, options);
    },

    async publishGitHubCheckRun(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (!snapshotMatchesTenantScope(snapshot, options)) {
        return null;
      }
      const gatePayload = buildGitHubPublishGatePayload(snapshot, options);
      const dryRun = options.dryRun !== false;
      const integrityAuthorization = dryRun ? null : assertLiveReleaseAuthorization(snapshot, options);
      const liveAuthorization = dryRun
        ? null
        : assertTrustedLiveMutationAuthority(this, snapshot, options, integrityAuthorization);
      const payloadHash = sha256(stableJson({
        kind: "github_check",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        repo: options.repo,
        head_sha: options.headSha,
        details_url: options.detailsUrl,
        check_run_id: options.checkRunId || null,
        dry_run: dryRun,
        decision_ledger_head_hash: liveAuthorization?.decision_ledger?.head_hash || null,
        decision_record_id: liveAuthorization?.decision_ledger?.record_id || null,
        github_check_run: gatePayload.github_check_run
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "github_check_publish", snapshot.source, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const receipt = await publishGitHubCheckRunReceipt(gatePayload, {
        repo: options.repo,
        headSha: options.headSha,
        detailsUrl: options.detailsUrl,
        checkRunId: options.checkRunId,
        apiBaseUrl: options.apiBaseUrl,
        token: options.token,
        tokenEnvName: options.tokenEnvName,
        dryRun,
        fetchImpl: options.fetchImpl
      });
      const storedReceipt = sanitizeGitHubPublishReceipt({
        ...receipt,
        resource_kind: "github_check",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        ...tenantScopeRecordFields(options, snapshot),
        actor_hash: options.actor ? sha256(String(options.actor)).slice(0, 16) : options.actorHash || "actor_[REDACTED_HASH]",
        published_at: options.publishedAt || new Date().toISOString(),
        payload_hash: payloadHash,
        a2_decision_authorization: liveAuthorization
      });
      githubPublishReceipts.push(storedReceipt);
      const auditEvent = githubPublishAuditEvent(storedReceipt, auditEvents.length);
      auditEvents.push(auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "github.check_publish_requested",
        resourceType: "github_publish_receipt",
        resourceId: storedReceipt.publish_id,
        tenantScope: {
          organization_id: storedReceipt.organization_id,
          tenant_id: snapshot.tenantId,
          workspace_id: snapshot.workspaceId,
          project_id: storedReceipt.project_id,
          environment_id: snapshot.environmentId
        },
        actorHash: storedReceipt.actor_hash,
        createdAt: storedReceipt.published_at,
        payload: storedReceipt,
        usageMeter: {
          meter: "github_check_publish_requests",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(storedReceipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "github_check_publish", snapshot.source, options.idempotencyKey, payloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async publishGitHubPrComment(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (!snapshotMatchesTenantScope(snapshot, options)) {
        return null;
      }
      const gatePayload = buildGitHubPublishGatePayload(snapshot, options);
      const dryRun = options.dryRun !== false;
      const integrityAuthorization = dryRun ? null : assertLiveReleaseAuthorization(snapshot, options);
      const liveAuthorization = dryRun
        ? null
        : assertTrustedLiveMutationAuthority(this, snapshot, options, integrityAuthorization);
      const payloadHash = sha256(stableJson({
        kind: "pr_comment",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        repo: options.repo,
        pull_number: options.pullNumber,
        dry_run: dryRun,
        decision_ledger_head_hash: liveAuthorization?.decision_ledger?.head_hash || null,
        decision_record_id: liveAuthorization?.decision_ledger?.record_id || null,
        pr_comment_markdown: gatePayload.pr_comment_markdown
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "github_pr_comment_publish", snapshot.source, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const receipt = await publishPrCommentUpsertReceipt(gatePayload, {
        repo: options.repo,
        pullNumber: options.pullNumber,
        apiBaseUrl: options.apiBaseUrl,
        token: options.token,
        tokenEnvName: options.tokenEnvName,
        dryRun,
        fetchImpl: options.fetchImpl
      });
      const storedReceipt = sanitizeGitHubPublishReceipt({
        ...receipt,
        resource_kind: "pr_comment",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        ...tenantScopeRecordFields(options, snapshot),
        actor_hash: options.actor ? sha256(String(options.actor)).slice(0, 16) : options.actorHash || "actor_[REDACTED_HASH]",
        published_at: options.publishedAt || new Date().toISOString(),
        payload_hash: payloadHash,
        a2_decision_authorization: liveAuthorization
      });
      githubPublishReceipts.push(storedReceipt);
      const auditEvent = githubPublishAuditEvent(storedReceipt, auditEvents.length);
      auditEvents.push(auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "github.pr_comment_publish_requested",
        resourceType: "github_publish_receipt",
        resourceId: storedReceipt.publish_id,
        tenantScope: {
          organization_id: storedReceipt.organization_id,
          tenant_id: snapshot.tenantId,
          workspace_id: snapshot.workspaceId,
          project_id: storedReceipt.project_id,
          environment_id: snapshot.environmentId
        },
        actorHash: storedReceipt.actor_hash,
        createdAt: storedReceipt.published_at,
        payload: storedReceipt,
        usageMeter: {
          meter: "github_pr_comment_publish_requests",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(storedReceipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "github_pr_comment_publish", snapshot.source, options.idempotencyKey, payloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async submitReleaseEvidenceReadback(releaseId = "current", readback = {}, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (
        !releaseEvidenceIdMatches(releaseId, canonicalReleaseId, snapshot)
        || !snapshotMatchesTenantScope(snapshot, options)
      ) {
        return null;
      }
      const payloadHash = sha256(stableJson(readback || {}));
      const replay = getIdempotentReplay(idempotencyReceipts, "release_evidence_readback_capture", snapshot.source, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const storedReadback = sanitizeReleaseEvidenceReadback({
        ...readback,
        source: snapshot.source,
        release_id: canonicalReleaseId,
        ...tenantScopeRecordFields(options, snapshot),
        captured_at: options.capturedAt || new Date().toISOString(),
        actor_hash: options.actor ? sha256(String(options.actor)).slice(0, 16) : options.actorHash || "actor_[REDACTED_HASH]"
      });
      releaseEvidenceReadbacks.push(storedReadback);
      const auditEvent = releaseEvidenceReadbackAuditEvent(storedReadback, auditEvents.length);
      auditEvents.push(auditEvent);
      const receipt = {
        schema_version: "a3.release_evidence_readback_capture_receipt.v1",
        release_id: canonicalReleaseId,
        source: snapshot.source,
        ...tenantScopeRecordFields(storedReadback, snapshot),
        readback_id: storedReadback.readback_id,
        provider: storedReadback.provider,
        resource_kind: storedReadback.resource_kind,
        readback_status: storedReadback.readback_status,
        payload_hash: storedReadback.payload_hash,
        audit_event_id: auditEvent.event_id,
        idempotency: {
          key_present: Boolean(options.idempotencyKey),
          duplicate: false,
          status: options.idempotencyKey ? "recorded" : "not_provided"
        },
        persisted: true,
        secret_values_included: false,
        raw_body_stored: false,
        real_cloud_mutation_performed: false
      };
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "release_evidence.readback_captured",
        resourceType: "release_evidence_readback",
        resourceId: storedReadback.readback_id,
        tenantScope: {
          organization_id: storedReadback.organization_id,
          tenant_id: snapshot.tenantId,
          workspace_id: snapshot.workspaceId,
          project_id: storedReadback.project_id,
          environment_id: snapshot.environmentId
        },
        actorHash: storedReadback.actor_hash,
        createdAt: storedReadback.captured_at,
        payload: receipt,
        usageMeter: {
          meter: "release_evidence_readbacks",
          quantity: 1
        }
      });
      const receiptWithEvent = attachEventEnvelopeReceipt(receipt, outboxRow);
      rememberIdempotentReceipt(idempotencyReceipts, "release_evidence_readback_capture", snapshot.source, options.idempotencyKey, payloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async listReleaseEvidenceReadbacks(releaseId = "current", options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (
        !releaseEvidenceIdMatches(releaseId, canonicalReleaseId, snapshot)
        || !snapshotMatchesTenantScope(snapshot, options)
      ) {
        return null;
      }
      const readbacks = filterReleaseEvidenceReadbacks(filterTenantScopedRecords(releaseEvidenceReadbacks, snapshot, options), {
        source: snapshot.source,
        releaseId: canonicalReleaseId,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      return {
        schema_version: "a3.release_evidence_readback_list.v1",
        release_id: canonicalReleaseId,
        source: snapshot.source,
        tenant_scope: {
          organization_id: options.organizationId || snapshot.organizationId,
          project_id: options.projectId || snapshot.projectId
        },
        readback_count: readbacks.length,
        status_counts: countBy(readbacks, "readback_status"),
        readbacks,
        safety: {
          raw_body_stored: false,
          token_included: false,
          secret_values_allowed: false
        }
      };
    },

    async getReleaseEvidenceSummary(releaseId = "current", options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (
        !releaseEvidenceIdMatches(releaseId, canonicalReleaseId, snapshot)
        || !snapshotMatchesTenantScope(snapshot, options)
      ) {
        return null;
      }
      return buildReleaseEvidenceApiResponse(snapshot, {
        releaseId: canonicalReleaseId,
        storageMode: this.storage_mode,
        dbReady: this.db_ready,
        reports: [...reports.values()],
        auditEvents: filterTenantScopedRecords(auditEvents, snapshot, options),
        releaseEvidenceReadbacks: filterTenantScopedRecords(releaseEvidenceReadbacks, snapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), snapshot, options),
        version: options.version || options.schemaVersion
      });
    },

    async getReleaseEvidenceDiff(releaseId = "current", options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (
        !releaseEvidenceIdMatches(releaseId, canonicalReleaseId, snapshot)
        || !snapshotMatchesTenantScope(snapshot, options)
      ) {
        return null;
      }
      const before = buildReleaseEvidenceApiResponse(snapshot, {
        releaseId: canonicalReleaseId,
        storageMode: this.storage_mode,
        dbReady: this.db_ready,
        reports: [...reports.values()],
        auditEvents: filterTenantScopedRecords(auditEvents, snapshot, options),
        releaseEvidenceReadbacks: filterTenantScopedRecords(releaseEvidenceReadbacks, snapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), snapshot, options),
        version: "1"
      }).release_evidence_summary;
      const after = buildReleaseEvidenceApiResponse(snapshot, {
        releaseId: canonicalReleaseId,
        storageMode: this.storage_mode,
        dbReady: this.db_ready,
        reports: [...reports.values()],
        auditEvents: filterTenantScopedRecords(auditEvents, snapshot, options),
        releaseEvidenceReadbacks: filterTenantScopedRecords(releaseEvidenceReadbacks, snapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), snapshot, options),
        version: "2"
      }).release_evidence_summary;
      const diff = diffReleaseEvidenceSummaries(before, after);
      return {
        schema_version: "a3.release_evidence_diff_api_response.v1",
        release_id: canonicalReleaseId,
        source: snapshot.source,
        tenant_scope: {
          organization_id: snapshot.organizationId,
          project_id: snapshot.projectId
        },
        from: options.from || "v1-current",
        to: options.to || "v2-authority",
        diff,
        safety: {
          raw_fixture_exposed: false,
          raw_request_body_exposed: false,
          raw_secret_values_allowed: false
        }
      };
    },

    async createShareableReport(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const idempotencyPayloadHash = sha256(stableJson({
        source: snapshot.source,
        title: options.title,
        visibility: options.visibility,
        created_by: safeActorId(options.createdBy),
        expires_at: options.expiresAt,
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        share_token_hash: options.shareToken ? sha256(options.shareToken) : null
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "report_share_create", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const tenantScope = buildA3TenantScope(options, snapshot);
      const report = {
        ...buildShareableReportPayload({
          ...snapshot,
          multimodalReviewQueue: buildMultimodalQueueForSnapshot(
            snapshot,
            filterTenantScopedRecords(multimodalReviewAssignmentEvents, snapshot, options),
            { now: options.createdAt || options.now }
          )
        }, {
          source: snapshot.source,
          title: options.title,
          visibility: options.visibility,
          createdBy: options.createdBy,
          createdAt: options.createdAt,
          expiresAt: options.expiresAt,
          shareToken: options.shareToken,
          organizationId: options.organizationId,
          projectId: options.projectId
        }),
        tenant_scope: tenantScope
      };
      const storedReport = sanitizeStoredReport(report);
      const storageKey = reportStorageKey(storedReport, snapshot);
      reports.set(storageKey, storedReport);
      registerShareLink(shareLinks, storedReport, storageKey);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: snapshot.source,
        eventType: "report.share_link_created",
        resourceType: "shareable_report",
        resourceId: report.report_id,
        tenantScope: reportTenantScope(report),
        actorId: safeActorId(options.createdBy || report.created_by),
        createdAt: report.created_at,
        payload: shareReportEventPayload(report),
        usageMeter: {
          meter: "shareable_reports",
          quantity: 1
        }
      });
      const reportWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(report, outboxRow), options.idempotencyKey);
      const replayReceipt = attachIdempotencyReceipt(sanitizeReportForRead(sanitizeStoredReport(reportWithEvent)), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "report_share_create", snapshot.source, options.idempotencyKey, idempotencyPayloadHash, replayReceipt);
      return reportWithEvent;
    },

    async getReport(reportId, options = {}) {
      const entry = findReportEntry(reports, reportId, snapshots, options);
      if (!entry) {
        return null;
      }
      return sanitizeReportForRead(entry.report);
    },

    async getReportManifest(reportId, options = {}) {
      const entry = findReportEntry(reports, reportId, snapshots, options);
      if (!entry) {
        return null;
      }
      const report = entry.report;
      const snapshot = selectSnapshot(snapshots, options.source || report.source, options);
      const reportScope = reportTenantScope(report);
      const scopedSnapshot = snapshotWithScope(snapshot, {
        organizationId: options.organizationId || reportScope.organizationId,
        projectId: options.projectId || reportScope.projectId
      });
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      return buildReportCenterManifest(report, {
        usageLedger: buildA3UsageLedger(snapshot, {
          reports: scopedReports,
          auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
          importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options),
          organizationId: scopedSnapshot.organizationId,
          projectId: scopedSnapshot.projectId
        }),
        migrationPlan: buildA3SqlMigrationPlan()
      });
    },

    async getReportCenter(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const migrationPlan = buildA3SqlMigrationPlan();
      const baseReportCenter = buildReportCenterIndex(scopedReports, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        migrationPlan
      });
      const productConsole = buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        reportCenter: baseReportCenter,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options)
      });
      return buildReportCenterIndex(scopedReports, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        migrationPlan,
        productConsole,
        saasAdmin: attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
          source: snapshot.source,
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId
        }), filterTenantScopedRecords(adminActionRequests, scopedSnapshot, options), {
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId
        })
      });
    },

    async getArtifactRegistry(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const migrationPlan = buildA3SqlMigrationPlan();
      const reportCenter = buildReportCenterIndex(scopedReports, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        migrationPlan
      });
      const productConsole = buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        reportCenter,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options)
      });
      const saasAdmin = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), filterTenantScopedRecords(adminActionRequests, scopedSnapshot, options), {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      const notificationControlPlane = await this.getNotificationControlPlane(options);
      return buildA3ArtifactRegistry({
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        sourceArtifacts: buildA3SourceArtifacts(scopedSnapshot, {
          source: snapshot.source,
          organizationId: scopedSnapshot.organizationId,
          tenantId: scopedSnapshot.tenantId,
          workspaceId: scopedSnapshot.workspaceId,
          projectId: scopedSnapshot.projectId,
          environmentId: scopedSnapshot.environmentId
        }),
        reportCenter,
        usageLedger,
        migrationPlan,
        productConsole,
        saasAdmin,
        notificationControlPlane,
        releaseEvidenceReadbacks: filterReleaseEvidenceReadbacks(filterTenantScopedRecords(releaseEvidenceReadbacks, scopedSnapshot, options), {
          organizationId: scopedSnapshot.organizationId,
          projectId: scopedSnapshot.projectId
        })
      });
    },

    async getProductConsole(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      });
      const reportCenter = buildReportCenterIndex(scopedReports, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        migrationPlan: buildA3SqlMigrationPlan()
      });
      return buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        usageLedger,
        reportCenter,
        auditEvents: filterTenantScopedRecords(auditEvents, scopedSnapshot, options),
        importReceipts: filterTenantScopedRecords(apiImportReceiptsFromLedger(idempotencyReceipts), scopedSnapshot, options)
      });
    },

    async getReportForView(reportId, options = {}) {
      const entry = findReportEntry(reports, reportId, snapshots, options);
      if (!entry) {
        return null;
      }
      const report = entry.report;
      const now = options.viewedAt || new Date().toISOString();
      const status = reportLifecycleStatus(report, now);
      const idempotencyPayloadHash = sha256(stableJson({
        report_id: reportId,
        source: report.source,
        viewer: safeActorId(options.viewer),
        status,
        tenant_scope: reportTenantScope(report)
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "report_view", report.source || "mock", options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      if (status === "shareable") {
        const reportScope = reportTenantScope(report);
        const event = {
          event_id: `rve_${sha256(`${reportId}:${now}:${auditEvents.length}`).slice(0, 12)}`,
          report_id: reportId,
          source: report.source,
          ...tenantScopeRecordFields(reportScope),
          event_type: "report_view",
          viewed_at: now,
          viewer: options.viewer || "anonymous",
          source: report.source,
          redacted: true
        };
        auditEvents.push(event);
        const outboxRow = recordEventOutbox(eventOutbox, {
          source: report.source,
          eventType: "report.viewed",
          resourceType: "shareable_report",
          resourceId: reportId,
          tenantScope: reportScope,
          actorId: safeActorId(options.viewer),
          createdAt: now,
          payload: reportViewEventPayload(event),
          usageMeter: {
            meter: "report_views",
            quantity: 1
          }
        });
        report.view_audit = {
          ...(report.view_audit || {}),
          view_count: (report.view_audit?.view_count || 0) + 1,
          last_viewed_at: now,
          last_event_id: event.event_id,
          last_event_outbox_id: outboxRow.event_id
        };
      }
      const viewedReport = {
        ...report,
        status,
        idempotency: idempotencyState(options.idempotencyKey)
      };
      rememberIdempotentReceipt(idempotencyReceipts, "report_view", report.source || "mock", options.idempotencyKey, idempotencyPayloadHash, viewedReport);
      return viewedReport;
    },

    async getReportForShareToken(shareToken, options = {}) {
      const now = options.viewedAt || new Date().toISOString();
      const tokenHash = sha256(shareToken || "");
      const link = shareLinks.get(tokenHash);
      if (!link) {
        recordReportAccessEvent(auditEvents, {
          reportId: null,
          tokenHash,
          accessResult: "not_found",
          viewedAt: now,
          viewer: options.viewer || "share_link"
        });
        return deniedShareReport("not_found", null, {
          tokenHash,
          viewedAt: now
        });
      }

      const report = reports.get(link.report_storage_key)
        || findReportEntry(reports, link.report_id, snapshots, {
          source: link.source,
          ...tenantScopeToSnapshotFields(link.tenant_scope || {})
        })?.report;
      if (!report) {
        recordReportAccessEvent(auditEvents, {
          reportId: link.report_id,
          tokenHash,
          accessResult: "not_found",
          viewedAt: now,
          viewer: options.viewer || "share_link",
          source: link.source,
          tenantScope: link.tenant_scope
        });
        return deniedShareReport("not_found", null, {
          tokenHash,
          viewedAt: now
        });
      }

      const status = shareLinkLifecycleStatus(report, link, now);
      if (status === "shareable") {
        const event = recordReportAccessEvent(auditEvents, {
          reportId: report.report_id,
          tokenHash,
          accessResult: "allowed",
          viewedAt: now,
          viewer: options.viewer || "share_link",
          source: report.source,
          tenantScope: reportTenantScope(report)
        });
        const reportScope = reportTenantScope(report);
        const outboxRow = recordEventOutbox(eventOutbox, {
          source: report.source,
          eventType: "report.share_link_viewed",
          resourceType: "shareable_report",
          resourceId: report.report_id,
          tenantScope: reportScope,
          actorId: safeActorId(options.viewer || "share_link"),
          createdAt: now,
          payload: reportViewEventPayload(event),
          usageMeter: {
            meter: "report_views",
            quantity: 1
          }
        });
        report.view_audit = {
          ...(report.view_audit || {}),
          view_count: (report.view_audit?.view_count || 0) + 1,
          last_viewed_at: now,
          last_event_id: event.event_id,
          last_event_outbox_id: outboxRow.event_id
        };
        link.last_viewed_at = now;
        link.last_event_id = event.event_id;
        link.last_event_outbox_id = outboxRow.event_id;
        return {
          ...report,
          status: "shareable",
          access_result: "allowed"
        };
      }

      recordReportAccessEvent(auditEvents, {
        reportId: report.report_id,
        tokenHash,
        accessResult: status,
        viewedAt: now,
        viewer: options.viewer || "share_link",
        source: report.source,
        tenantScope: reportTenantScope(report)
      });
      return deniedShareReport(status, report, {
        tokenHash,
        viewedAt: now
      });
    },

    async revokeReport(reportId, options = {}) {
      const entry = findReportEntry(reports, reportId, snapshots, options);
      if (!entry) {
        return null;
      }
      const report = entry.report;
      const revokedAt = options.revokedAt || new Date().toISOString();
      const reportScope = reportTenantScope(report);
      const idempotencyPayloadHash = sha256(stableJson({
        report_id: reportId,
        source: report.source,
        reason: options.reason || "manual_revoke",
        revoked_by: safeActorId(options.revokedBy || "a3-api"),
        tenant_scope: reportScope
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "report_revoke", report.source || "mock", options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const revoked = {
        ...report,
        status: "revoked",
        revoked_at: revokedAt,
        revoked_by: options.revokedBy || "a3-api",
        revocation_reason: options.reason || "manual_revoke",
        share_link: {
          ...(report.share_link || {}),
          revoked_at: revokedAt
        }
      };
      reports.set(entry.key, revoked);
      revokeShareLink(shareLinks, report, revokedAt);
      auditEvents.push({
        event_id: `rrv_${sha256(`${reportId}:${revokedAt}:${auditEvents.length}`).slice(0, 12)}`,
        report_id: reportId,
        source: report.source,
        ...tenantScopeRecordFields(reportScope),
        event_type: "report_revoke",
        revoked_at: revokedAt,
        revoked_by: revoked.revoked_by,
        reason: revoked.revocation_reason,
        redacted: true
      });
      const receipt = {
        schema_version: "a3.report_revoke_receipt.v1",
        source: report.source,
        ...tenantScopeRecordFields(reportScope),
        report_id: reportId,
        status: "revoked",
        revoked_at: revokedAt,
        revoked_by: revoked.revoked_by,
        reason: revoked.revocation_reason
      };
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: report.source,
        eventType: "report.revoked",
        resourceType: "shareable_report",
        resourceId: reportId,
        tenantScope: reportScope,
        actorId: safeActorId(revoked.revoked_by),
        createdAt: revokedAt,
        payload: receipt,
        usageMeter: {
          meter: "report_revocations",
          quantity: 1
        }
      });
      const receiptWithEvent = attachIdempotencyReceipt(attachEventEnvelopeReceipt(receipt, outboxRow), options.idempotencyKey);
      rememberIdempotentReceipt(idempotencyReceipts, "report_revoke", report.source || "mock", options.idempotencyKey, idempotencyPayloadHash, receiptWithEvent);
      return receiptWithEvent;
    },

    async recordAccessDecision(decision, options = {}) {
      const normalized = normalizeAccessDecisionAudit(decision, options);
      const existing = auditEvents.find((event) => event.event_id === normalized.auditEvent.event_id);
      if (existing) {
        return {
          schema_version: "a3.access_decision_audit_receipt.v1",
          audit_event_id: existing.event_id,
          event_outbox_id: eventOutbox.find((event) => event.resource_id === existing.event_id)?.event_id || null,
          persisted: true,
          idempotent_replay: true,
          storage_mode: this.storage_mode,
          safety: accessDecisionAuditSafety()
        };
      }

      auditEvents.push(normalized.auditEvent);
      const outboxRow = recordEventOutbox(eventOutbox, {
        source: options.source || "hosted-access",
        eventType: normalized.auditEvent.event_type,
        resourceType: "access_decision",
        resourceId: normalized.auditEvent.event_id,
        tenantScope: normalized.tenantScope,
        actorId: normalized.auditEvent.actor_id,
        createdAt: normalized.auditEvent.created_at,
        payload: normalized.publicDecision,
        usageMeter: {
          meter: "api_requests",
          quantity: 1
        }
      });

      return {
        schema_version: "a3.access_decision_audit_receipt.v1",
        audit_event_id: normalized.auditEvent.event_id,
        event_outbox_id: outboxRow.event_id,
        persisted: true,
        idempotent_replay: false,
        storage_mode: this.storage_mode,
        safety: accessDecisionAuditSafety()
      };
    },

    async listEventOutbox(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source, options);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const rows = filterEventOutboxRows(eventOutbox, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        tenantId: scopedSnapshot.tenantId,
        workspaceId: scopedSnapshot.workspaceId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId,
        eventType: options.eventType,
        deliveryStatus: options.deliveryStatus
      });
      return {
        schema_version: "a3.event_outbox_list.v1",
        source: snapshot.source,
        tenant_scope: {
          organization_id: scopedSnapshot.organizationId,
          tenant_id: scopedSnapshot.tenantId,
          workspace_id: scopedSnapshot.workspaceId,
          project_id: scopedSnapshot.projectId,
          environment_id: scopedSnapshot.environmentId
        },
        event_count: rows.length,
        status_counts: countBy(rows, "delivery_status"),
        event_type_counts: countBy(rows, "event_type"),
        events: rows,
        safety: {
          metadata_only: true,
          raw_payload_embedded: false,
          raw_secret_values_allowed: false,
          raw_cookie_values_allowed: false,
          raw_signed_urls_allowed: false,
          raw_actor_identity_exposed: false
        }
      };
    },

    async listReports(options = {}) {
      if (options.enforceScope === true) {
        selectSnapshot(snapshots, options.source, options);
      }
      return [...reports.values()]
        .filter((report) => reportMatchesRequestScope(report, snapshots, options))
        .map((report) => ({
        report_id: report.report_id,
        title: report.title,
        status: reportLifecycleStatus(report),
        source: report.source,
        share_url_path: report.share_url_path,
        internal_url_path: report.internal_url_path,
        share_link: safeShareLinkSummary(report.share_link),
        created_at: report.created_at,
        expires_at: report.expires_at,
        revoked_at: report.revoked_at,
        view_count: report.view_audit?.view_count || 0
      }));
    },

    exportState() {
      return {
        schema_version: A3_STORE_SCHEMA_VERSION,
        storage_mode: this.storage_mode,
        sources: Object.fromEntries(snapshots.entries()),
        reports: [...reports.values()],
        shareLinks: [...shareLinks.values()],
        idempotencyReceipts: [...idempotencyReceipts.entries()].map(([key, value]) => ({ key, ...value })),
        auditEvents,
        eventOutbox,
        adminActionRequests,
        reviewWorkflowRecords,
        multimodalReviewAssignmentEvents,
        releaseEvidenceReadbacks,
        githubPublishReceipts,
        deploymentReceipts,
        deploymentReceiptReadbacks,
        selfHostSandboxCalibrations
      };
    }
  };
}

function normalizeAccessDecisionAudit(decision = {}, options = {}) {
  const auditEvent = decision.audit_event || decision.authz_audit_event || decision.access_audit_event;
  if (!auditEvent || typeof auditEvent !== "object" || Array.isArray(auditEvent)) {
    throw new A3StoreValidationError("Access decision requires a metadata-only audit event.", [
      { field: "audit_event", reason: "missing" }
    ], {
      requestType: "access_decision_audit",
      source: options.source || "hosted-access"
    });
  }

  const tenantScope = {
    organization_id: auditEvent.organization_id,
    tenant_id: auditEvent.tenant_id,
    workspace_id: auditEvent.workspace_id,
    project_id: auditEvent.project_id,
    environment_id: auditEvent.environment_id
  };
  const missingScope = Object.entries(tenantScope)
    .filter(([, value]) => typeof value !== "string" || !value.trim())
    .map(([field]) => ({ field, reason: "required" }));
  const serialized = JSON.stringify({ decision, auditEvent });
  const unsafe = /Bearer\s+[A-Za-z0-9._-]+|ASHR(?:_LABS)?_API_KEY\s*[:=]|Cookie:|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i.test(serialized);
  const metadataOnly = auditEvent.payload_inline === false
    && auditEvent.redaction_status === "metadata_only"
    && auditEvent.safety?.raw_secret_values_allowed === false;

  const details = [...missingScope];
  if (!auditEvent.event_id || !auditEvent.event_type || !auditEvent.actor_id) {
    details.push({ field: "audit_event", reason: "event_id, event_type, and actor_id are required" });
  }
  if (!metadataOnly) {
    details.push({ field: "audit_event", reason: "metadata_only audit envelope required" });
  }
  if (unsafe) {
    details.push({ field: "audit_event", reason: "sensitive-looking material is forbidden" });
  }
  if (details.length) {
    throw new A3StoreValidationError("Access decision audit failed validation.", details, {
      requestType: "access_decision_audit",
      source: options.source || "hosted-access"
    });
  }

  const publicDecision = {
    schema_version: "a3.access_decision_audit.v1",
    operation: String(decision.operation || "unknown"),
    allowed: decision.allowed === true,
    decision: String(decision.decision || "unknown"),
    required_permission: String(decision.required_permission || "unknown"),
    role: String(decision.role || "unknown"),
    http_status: Number(decision.http_status || decision.denied_state?.http_status || (decision.allowed ? 200 : 403)),
    audit_event_id: auditEvent.event_id,
    tenant_scope: tenantScope,
    payload_inline: false
  };

  return {
    auditEvent: {
      ...auditEvent,
      source: normalizeSourceKey(auditEvent.source || options.source || "hosted-access"),
      organization_id: tenantScope.organization_id,
      tenant_id: tenantScope.tenant_id,
      workspace_id: tenantScope.workspace_id,
      project_id: tenantScope.project_id,
      environment_id: tenantScope.environment_id,
      payload_inline: false,
      redaction_status: "metadata_only"
    },
    tenantScope,
    publicDecision
  };
}

function accessDecisionAuditSafety() {
  return {
    metadata_only: true,
    raw_request_body_stored: false,
    raw_actor_identity_stored: false,
    raw_token_stored: false,
    raw_cookie_stored: false,
    raw_api_key_stored: false
  };
}

export async function createFixtureBackedA3Store(options = {}) {
  const sources = {};
  for (const source of options.sources || Object.keys(A3_SOURCE_FIXTURES)) {
    sources[source] = await loadA3SourceSnapshot(source, options);
  }
  const selfHostSandboxCalibrations = options.selfHostSandboxCalibrations || [
    await loadSelfHostSandboxCalibration(
      options.selfHostSandboxCalibrationPath
        || fileURLToPath(new URL("../../fixtures/a3/p3/a3_self_host_sandbox_calibration_20260713.redacted.json", import.meta.url))
    )
  ];
  return createMemoryA3Store({
    sources,
    selfHostSandboxCalibrations,
    storageMode: "fixture_file"
  });
}

export async function createFileBackedA3Store(options = {}) {
  const filePath = options.filePath;
  if (!filePath) {
    throw new Error("createFileBackedA3Store requires filePath");
  }

  let state = options.seed || {};
  try {
    state = JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  const store = createMemoryA3Store({
    ...state,
    storageMode: "json_file"
  });
  const persist = async () => {
    await mkdir(dirname(filePath), { recursive: true });
    await writeFile(filePath, `${JSON.stringify(store.exportState(), null, 2)}\n`, "utf8");
  };

  return {
    ...store,
    async upsertSnapshot(source, snapshot) {
      const result = await store.upsertSnapshot(source, snapshot);
      await persist();
      return result;
    },
    async importA1RunResult(runResult, options = {}) {
      const result = await store.importA1RunResult(runResult, options);
      await persist();
      return result;
    },
    async importA2GradeResult(gradeResult, options = {}) {
      const result = await store.importA2GradeResult(gradeResult, options);
      await persist();
      return result;
    },
    async importA2MultimodalComparison(comparison, options = {}) {
      const result = await store.importA2MultimodalComparison(comparison, options);
      await persist();
      return result;
    },
    async mutateMultimodalReviewAssignment(queueId, input, options = {}) {
      const result = await store.mutateMultimodalReviewAssignment(queueId, input, options);
      await persist();
      return result;
    },
    async createShareableReport(options = {}) {
      const result = await store.createShareableReport(options);
      await persist();
      return result;
    },
    async revokeReport(reportId, options = {}) {
      const result = await store.revokeReport(reportId, options);
      await persist();
      return result;
    },
    async getReportForView(reportId, options = {}) {
      const result = await store.getReportForView(reportId, options);
      await persist();
      return result;
    },
    async getReportForShareToken(shareToken, options = {}) {
      const result = await store.getReportForShareToken(shareToken, options);
      await persist();
      return result;
    },
    async submitSaasAdminAction(action, options = {}) {
      const result = await store.submitSaasAdminAction(action, options);
      await persist();
      return result;
    },
    async submitReviewWaiver(waiver, options = {}) {
      const result = await store.submitReviewWaiver(waiver, options);
      await persist();
      return result;
    },
    async submitReviewApproval(approval, options = {}) {
      const result = await store.submitReviewApproval(approval, options);
      await persist();
      return result;
    },
    async submitReviewDenial(denial, options = {}) {
      const result = await store.submitReviewDenial(denial, options);
      await persist();
      return result;
    },
    async submitReleaseEvidenceReadback(releaseId, readback, options = {}) {
      const result = await store.submitReleaseEvidenceReadback(releaseId, readback, options);
      await persist();
      return result;
    },
    async submitDeploymentReceipt(input, options = {}) {
      const result = await store.submitDeploymentReceipt(input, options);
      await persist();
      return result;
    },
    async reviewDeploymentReceipt(receiptId, review, options = {}) {
      const result = await store.reviewDeploymentReceipt(receiptId, review, options);
      await persist();
      return result;
    },
    async verifyDeploymentReceiptAuthoritatively(receiptId, resolver, options = {}) {
      const result = await store.verifyDeploymentReceiptAuthoritatively(receiptId, resolver, options);
      await persist();
      return result;
    },
    async recordAccessDecision(decision, options = {}) {
      const result = await store.recordAccessDecision(decision, options);
      await persist();
      return result;
    },
    async persist() {
      await persist();
    }
  };
}

function normalizeSnapshot(snapshot = {}) {
  const source = normalizeSourceKey(snapshot.source || "mock");
  const runFixture = snapshot.runFixture || snapshot.runs || {};
  const gradeFixture = snapshot.gradeFixture || snapshot.grades || {};
  const cases = normalizeCases(runFixture, gradeFixture);
  const tenantScope = buildA3TenantScope(snapshot);
  return {
    schema_version: "a3.dashboard_snapshot.v1",
    source,
    source_label: snapshot.source_label || A3_SOURCE_FIXTURES[source]?.label || source,
    organizationId: tenantScope.organization_id,
    tenantId: tenantScope.tenant_id,
    workspaceId: tenantScope.workspace_id,
    projectId: tenantScope.project_id,
    environmentId: tenantScope.environment_id,
    tenant_scope: tenantScope,
    runFixture,
    gradeFixture,
    coverage: snapshot.coverage || {},
    requestProvenance: snapshot.requestProvenance || {},
    usageQuota: snapshot.usageQuota || {},
    usageQuotaApiProbe: snapshot.usageQuotaApiProbe || {},
    mediaSignedUrlCoverage: snapshot.mediaSignedUrlCoverage || {},
    authCheck: snapshot.authCheck || {},
    frontendSummary: snapshot.frontendSummary || {},
    frontendMirror: snapshot.frontendMirror || {},
    frontendCodeCrawl: snapshot.frontendCodeCrawl || {},
    peerBranchCalibration: snapshot.peerBranchCalibration || snapshot.peer_branch_calibration || {},
    a2MultimodalComparison: snapshot.a2MultimodalComparison || snapshot.a2_multimodal_comparison || {},
    a2MultimodalComparisonMeta: snapshot.a2MultimodalComparisonMeta || snapshot.a2_multimodal_comparison_meta || {},
    releaseEvidence: snapshot.releaseEvidence || snapshot.release_evidence || {},
    a2GradeResults: snapshot.a2GradeResults || snapshot.a2_grade_results || {},
    a2ReleaseGate: snapshot.a2ReleaseGate || snapshot.a2_release_gate || {},
    a2TrustedSpine: snapshot.a2TrustedSpine || snapshot.a2_trusted_spine || {},
    deploymentProbe: snapshot.deploymentProbe || snapshot.deployment_probe || {},
    deploymentAcceptance: snapshot.deploymentAcceptance || snapshot.deployment_acceptance || {},
    releaseArtifactManifest: snapshot.releaseArtifactManifest || snapshot.release_artifact_manifest || {},
    releaseArtifactVerification: snapshot.releaseArtifactVerification || snapshot.release_artifact_verification || {},
    deliveryGoldenPath: snapshot.deliveryGoldenPath || snapshot.delivery_golden_path || {},
    githubCheckReadback: snapshot.githubCheckReadback || snapshot.github_check_readback || {},
    githubPrCommentReadback: snapshot.githubPrCommentReadback || snapshot.github_pr_comment_readback || {},
    githubRequiredCheckProof: snapshot.githubRequiredCheckProof || snapshot.github_required_check_proof || {},
    githubActionsArtifactReadback: snapshot.githubActionsArtifactReadback || snapshot.github_actions_artifact_readback || {},
    releaseComparison: snapshot.releaseComparison || snapshot.release_comparison || {},
    summary: buildDashboardSummary(runFixture, gradeFixture),
    case_count: cases.length,
    storage: snapshot.storage || {
      mode: "memory",
      db_ready: false
    }
  };
}

function buildDashboardPayload(snapshot, storageMode, options = {}) {
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  const releaseId = releaseEvidenceReleaseId(snapshot);
  const trustedReleaseAuthority = evaluateA2TrustedReleaseAuthority(
    snapshot.a2TrustedSpine || snapshot.a2_trusted_spine || {},
    { expectedScope: tenantScopeRecordFields(snapshot) }
  );
  const githubPublishReceiptDashboard = buildGitHubPublishReceiptDashboard(options.githubPublishReceipts || [], {
    source: snapshot.source,
    releaseId,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, options.githubPublishReceipts || [], {
    source: snapshot.source,
    releaseId,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const releaseEvidenceSummary = summarizeReleaseEvidenceSummary(releaseEvidenceInput);
  const sourceArtifacts = buildA3SourceArtifacts(snapshot, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    tenantId: snapshot.tenantId,
    workspaceId: snapshot.workspaceId,
    projectId: snapshot.projectId,
    environmentId: snapshot.environmentId
  });
  const releaseEvidenceReadbackHistory = buildReleaseEvidenceReadbackDashboardHistory(options.releaseEvidenceReadbacks || [], {
    source: snapshot.source,
    releaseId,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const releaseEvidenceForDashboard = {
    ...releaseEvidenceSummary,
    readback_history: releaseEvidenceReadbackHistory,
    readback_records: releaseEvidenceReadbackHistory.latest_records,
    readback_record_count: releaseEvidenceReadbackHistory.readback_count,
    readback_status_counts: releaseEvidenceReadbackHistory.status_counts,
    readback_resource_counts: releaseEvidenceReadbackHistory.resource_counts
  };
  const usageLedger = buildA3UsageLedger(snapshot, {
    reports: options.reports || [],
    auditEvents: options.auditEvents || [],
    releaseEvidenceReadbacks: options.releaseEvidenceReadbacks || [],
    importReceipts: options.importReceipts || []
  });
  const migrationPlan = buildA3SqlMigrationPlan();
  const reportCenter = buildReportCenterIndex(options.reports || [], {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId,
    usageLedger,
    migrationPlan
  });
  const productConsole = buildA3ProductConsole(snapshot, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId,
    usageLedger,
    reportCenter,
    auditEvents: options.auditEvents || [],
    importReceipts: options.importReceipts || []
  });
  const saasAdmin = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  }), options.adminActionRequests || [], {
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const billingReadiness = buildA3BillingReadiness({
    usageLedger,
    adminConsole: saasAdmin
  }, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const billingMigrationReadiness = buildA3BillingMigrationReadiness({
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId,
    environmentId: snapshot.environmentId
  });
  const eventOutboxDashboard = buildEventOutboxDashboard(options.eventOutbox || [], {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    tenantId: snapshot.tenantId,
    workspaceId: snapshot.workspaceId,
    projectId: snapshot.projectId,
    environmentId: snapshot.environmentId
  });
  const reviewWorkflow = buildReviewWorkflowIndex(filterReviewWorkflowRecords(options.reviewWorkflowRecords || [], {
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  }), {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId,
    durableStorageReady: true
  });
  const liveWorkflowReadiness = buildA3LiveWorkflowReadiness({
    source: snapshot.source,
    releaseEvidence: releaseEvidenceInput,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    saasAdmin,
    eventOutbox: eventOutboxDashboard
  }, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const liveOpsControlPlane = buildA3LiveOpsControlPlane({
    source: snapshot.source,
    releaseEvidence: releaseEvidenceInput,
    reviewWorkflow,
    usageLedger,
    billingReadiness,
    reportCenter,
    saasAdmin,
    eventOutbox: eventOutboxDashboard,
    liveWorkflowReadiness
  }, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const notificationControlPlane = buildA3NotificationControlPlane({
    source: snapshot.source,
    releaseEvidence: releaseEvidenceInput,
    liveOpsControlPlane,
    reviewWorkflow,
    eventOutbox: eventOutboxDashboard,
    reportCenter,
    usageLedger
  }, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    tenantId: snapshot.tenantId,
    workspaceId: snapshot.workspaceId,
    projectId: snapshot.projectId,
    environmentId: snapshot.environmentId
  });
  const releaseDecisionProvenance = buildA3ReleaseDecisionProvenance({
    a1RunResult: extractRunRecords(snapshot.runFixture)[0],
    a2GradeResults: snapshot.a2GradeResults,
    a2ReleaseGate: snapshot.a2ReleaseGate,
    reviewWorkflow,
    shareableReport: reportCenter.reports?.[0],
    usageLedger,
    billingVisibility: billingReadiness,
    audit: (options.auditEvents || []).at(-1)
  }, {
    tenantScope: snapshot.tenant_scope,
    actor: options.actor || {},
    auth: options.auth || {}
  });
  const peerBranchCalibration = summarizeA3PeerBranchCalibration(snapshot.peerBranchCalibration);
  const multimodalReviewQueue = buildMultimodalQueueForSnapshot(
    snapshot,
    options.multimodalReviewAssignmentEvents || [],
    { now: options.now }
  );
  const multimodalReviewAssignmentPacket = multimodalReviewQueue.review_packet;
  const a1A2EvidenceSpine = buildA3A1A2EvidenceSpine({
    source: snapshot.source,
    runFixture: snapshot.runFixture,
    gradeFixture: snapshot.gradeFixture,
    a2ReleaseGate: snapshot.a2ReleaseGate,
    releaseDecisionProvenance,
    reviewWorkflow,
    reportCenter,
    peerBranchCalibration: snapshot.peerBranchCalibration
  }, {
    source: snapshot.source
  });
  const deliveryInputs = {
    runFixture: snapshot.runFixture,
    gradeFixture: snapshot.gradeFixture,
    trustedReleaseAuthority,
    a2TrustedSpine: snapshot.a2TrustedSpine,
    deploymentProbe: snapshot.deploymentProbe,
    releaseArtifactManifest: snapshot.releaseArtifactManifest,
    releaseArtifactVerification: snapshot.releaseArtifactVerification,
    githubCheckReadback: snapshot.githubCheckReadback || releaseEvidenceInput.githubCheckReadback || releaseEvidenceInput.github_check_readback || {},
    githubPrCommentReadback: snapshot.githubPrCommentReadback || releaseEvidenceInput.githubPrCommentReadback || releaseEvidenceInput.github_pr_comment_readback || {},
    githubRequiredCheckProof: snapshot.githubRequiredCheckProof || releaseEvidenceInput.githubRequiredCheckProof || releaseEvidenceInput.github_required_check_proof || {},
    githubActionsArtifactReadback: snapshot.githubActionsArtifactReadback || releaseEvidenceInput.githubActionsArtifactReadback || releaseEvidenceInput.github_actions_artifact_readback || {},
    auditBundleVerification: releaseEvidenceInput.auditBundleVerification || releaseEvidenceInput.audit_bundle_verification || {},
    auditArchiveVerification: releaseEvidenceInput.auditArchiveVerification || releaseEvidenceInput.audit_archive_verification || {},
    releaseVersion: snapshot.releaseArtifactManifest?.release?.version || `candidate-${releaseId}`,
    environment: snapshot.environmentId,
    generatedAt: "runtime"
  };
  const deploymentAcceptance = snapshot.deploymentAcceptance?.schema_version === "a3.deployment_acceptance.v1"
    ? snapshot.deploymentAcceptance
    : buildDeploymentAcceptance(deliveryInputs, deliveryInputs);
  const deliveryGoldenPath = snapshot.deliveryGoldenPath?.schema_version === "a3.delivery_golden_path.v1"
    ? snapshot.deliveryGoldenPath
    : buildDeliveryGoldenPath({ ...deliveryInputs, deploymentAcceptance }, deliveryInputs);
  const releaseComparison = bindA3ReleaseComparisonRuntimeAuthority(
    snapshot.releaseComparison,
    trustedReleaseAuthority
  );
  const deploymentHandoff = buildA3DeploymentHandoff({
    deploymentAcceptance,
    deliveryGoldenPath,
    trustedReleaseAuthority,
    a2TrustedSpine: snapshot.a2TrustedSpine,
    runFixture: snapshot.runFixture,
    releaseArtifactManifest: snapshot.releaseArtifactManifest
  }, {
    source: snapshot.source,
    tenantScope: snapshot.tenant_scope
  });
  const receiptContext = deploymentReceiptContext(snapshot, {
    deployment_handoff: deploymentHandoff,
    release_artifact_manifest: snapshot.releaseArtifactManifest
  });
  const deploymentReceiptInbox = buildA3DeploymentReceiptInbox(
    options.deploymentReceipts || [],
    deploymentHandoff,
    receiptContext,
    options.deploymentReceiptReadbacks || []
  );
  const deploymentAcceptanceProjection = buildA3DeploymentAcceptanceProjection(
    deploymentAcceptance,
    deploymentReceiptInbox
  );
  return {
    schema_version: "a3.api_dashboard_payload.v1",
    source: snapshot.source,
    source_label: snapshot.source_label,
    storage: {
      ...snapshot.storage,
      mode: storageMode || snapshot.storage?.mode || "memory",
      db_ready: options.dbReady === true,
      db_contract: A3_DB_CONTRACT,
      db_migrations: migrationPlan
    },
    run_fixture: snapshot.runFixture,
    grade_fixture: snapshot.gradeFixture,
    coverage: snapshot.coverage,
    request_provenance: snapshot.requestProvenance,
    usage_quota: snapshot.usageQuota,
    usage_quota_api_probe: snapshot.usageQuotaApiProbe,
    media_signed_url_coverage: snapshot.mediaSignedUrlCoverage,
    auth_check: snapshot.authCheck,
    frontend_summary: snapshot.frontendSummary,
    frontend_mirror: snapshot.frontendMirror,
    frontend_code_crawl: snapshot.frontendCodeCrawl,
    peer_branch_calibration: peerBranchCalibration,
    multimodal_review_queue: multimodalReviewQueue,
    release_evidence: releaseEvidenceForDashboard,
    release_evidence_summary: releaseEvidenceForDashboard,
    release_evidence_readbacks: releaseEvidenceReadbackHistory,
    github_publish_receipts: githubPublishReceiptDashboard,
    github_publish_evidence: githubPublishReceiptDashboard,
    event_outbox: eventOutboxDashboard,
    aggregate_scope_status: options.aggregateScopeStatus || buildAggregateScopeStatus({}, snapshot, options),
    source_artifacts: sourceArtifacts,
    billing_readiness: billingReadiness,
    billing_migration_readiness: billingMigrationReadiness,
    live_workflow_readiness: liveWorkflowReadiness,
    live_ops_control_plane: liveOpsControlPlane,
    notification_control_plane: notificationControlPlane,
    trusted_release_authority: trustedReleaseAuthority,
    release_decision_provenance: releaseDecisionProvenance,
    a1_a2_evidence_spine: a1A2EvidenceSpine,
    deployment_probe: snapshot.deploymentProbe,
    deployment_acceptance: deploymentAcceptance,
    deployment_acceptance_projection: deploymentAcceptanceProjection,
    deployment_handoff: deploymentHandoff,
    deployment_receipt_inbox: deploymentReceiptInbox,
    release_artifact_manifest: snapshot.releaseArtifactManifest,
    release_artifact_verification: snapshot.releaseArtifactVerification,
    delivery_golden_path: deliveryGoldenPath,
    github_check_readback: snapshot.githubCheckReadback,
    github_pr_comment_readback: snapshot.githubPrCommentReadback,
    github_required_check_proof: snapshot.githubRequiredCheckProof,
    github_actions_artifact_readback: snapshot.githubActionsArtifactReadback,
    release_comparison: releaseComparison,
    release_evidence_api: {
      schema_version: "a3.release_evidence_api_link.v1",
      release_id: releaseId,
      path: `/api/a3/releases/${encodeURIComponent(releaseId)}/evidence-summary?source=${encodeURIComponent(snapshot.source)}`,
      api_backed: true,
      raw_fixture_exposed: false
    },
    saas_admin_console: saasAdmin,
    enterprise_readiness: buildEnterpriseReadinessReport({
      runFixture: snapshot.runFixture,
      gradeFixture: snapshot.gradeFixture,
      adminConsole: saasAdmin,
      dbContract: A3_DB_CONTRACT
    }),
    usage_ledger: usageLedger,
    report_center: reportCenter,
    artifact_registry: buildA3ArtifactRegistry({
      source: snapshot.source,
      organizationId: snapshot.organizationId,
      tenantId: snapshot.tenantId,
      workspaceId: snapshot.workspaceId,
      projectId: snapshot.projectId,
      environmentId: snapshot.environmentId,
      sourceArtifacts,
      reportCenter,
      usageLedger,
      releaseEvidenceReadbacks: options.releaseEvidenceReadbacks || [],
      migrationPlan,
      productConsole,
      saasAdmin,
      notificationControlPlane,
      multimodalReviewAssignmentPacket
    }),
    commercial_api_contract: buildA3CommercialApiContract({
      source: "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
      organizationId: snapshot.organizationId,
      tenantId: snapshot.tenantId,
      workspaceId: snapshot.workspaceId,
      projectId: snapshot.projectId
    }),
    review_workflow: reviewWorkflow,
    multimodal_review_assignment_packet: multimodalReviewAssignmentPacket,
    product_console: productConsole,
    summary: snapshot.summary,
    cases: cases.map((item) => ({
      run_id: item.run_id,
      case_id: item.case_id,
      scenario_id: item.scenario_id,
      status: item.passed ? "passed" : "failed",
      score: item.score,
      primary_failure_class: item.primary_failure_class
    }))
  };
}

function buildReleaseEvidenceApiResponse(snapshot, options = {}) {
  const releaseId = options.releaseId || releaseEvidenceReleaseId(snapshot);
  const summary = summarizeReleaseEvidenceSummary(snapshot.releaseEvidence);
  const summaryHash = sha256(stableJson(summary));
  const reports = (options.reports || [])
    .filter((report) => (
      (report.source || snapshot.source) === snapshot.source
      && reportMatchesSnapshotScope(report, snapshot)
    ))
    .map((report) => ({
      report_id: report.report_id,
      status: reportLifecycleStatus(report),
      source: report.source || snapshot.source,
      summary_snapshot_id: report.release_evidence_snapshot?.snapshot_id || null,
      summary_hash: report.release_evidence_snapshot?.summary_hash || null,
      sealed_payload_hash_present: Boolean(report.sealed_evidence?.payload_hash),
      raw_share_token_exposed: false
    }));
  const primarySnapshot = reports.find((item) => item.summary_snapshot_id) || {};
  const health = buildReleaseEvidenceHealth(summary, {
    releaseId,
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId,
    dbReady: options.dbReady === true,
    hostedReportSnapshotId: primarySnapshot.summary_snapshot_id,
    shareableReportCount: reports.length
  });
  const usageLedger = buildA3UsageLedger(snapshot, {
    reports: reports.map((item) => ({ report_id: item.report_id, status: item.status })),
    auditEvents: options.auditEvents || [],
    releaseEvidenceReadbacks: options.releaseEvidenceReadbacks || [],
    importReceipts: options.importReceipts || [],
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const releaseStats = buildReleaseEvidenceV2Stats(snapshot);
  const sourceArtifacts = buildA3SourceArtifacts(snapshot, {
    source: snapshot.source,
    organizationId: snapshot.organizationId,
    tenantId: snapshot.tenantId,
    workspaceId: snapshot.workspaceId,
    projectId: snapshot.projectId,
    environmentId: snapshot.environmentId
  });
  const latestReadbacks = latestReleaseEvidenceReadbacks(options.releaseEvidenceReadbacks || [], {
    source: snapshot.source,
    releaseId,
    organizationId: snapshot.organizationId,
    projectId: snapshot.projectId
  });
  const summaryV2 = buildReleaseEvidenceSummaryV2(summary, {
    releaseId,
    summaryId: `res_${summaryHash.slice(0, 16)}`,
    source: snapshot.source,
    sourceSnapshotId: `${snapshot.source}:${summaryHash.slice(0, 12)}`,
    organizationId: snapshot.organizationId,
    tenantId: snapshot.tenantId,
    workspaceId: snapshot.workspaceId,
    projectId: snapshot.projectId,
    storageMode: options.storageMode || snapshot.storage?.mode || "memory",
    hostedReportSnapshotId: primarySnapshot.summary_snapshot_id,
    shareableReportCount: reports.length,
    usageLedger,
    githubCheckReadback: latestReadbacks.github_check,
    prCommentReadback: latestReadbacks.pr_comment,
    requiredCheckProof: latestReadbacks.required_check,
    health,
    sourceArtifacts,
    ...releaseStats
  });
  if (releaseEvidenceVersion(options) === "v2") {
    return {
      schema_version: "a3.release_evidence_api_response.v2",
      release_id: releaseId,
      summary_id: summaryV2.summary_id,
      source: snapshot.source,
      tenant_scope: summaryV2.tenant_scope,
      api_backed: true,
      release_evidence_summary: summaryV2,
      release_evidence_health: health,
      next_action: health.next_action,
      compatibility: {
        default_version: "v1",
        requested_version: "v2",
        v1_stable: true,
        v2_additive: true
      },
      safety: summaryV2.safety,
      readback_records: latestReadbacks.records,
      next_actions: summaryV2.next_actions
    };
  }
  return {
    schema_version: "a3.release_evidence_api_response.v1",
    release_id: releaseId,
    summary_id: `res_${summaryHash.slice(0, 16)}`,
    source: snapshot.source,
    tenant_scope: {
      organization_id: snapshot.organizationId,
      project_id: snapshot.projectId
    },
    api_backed: true,
    storage: {
      mode: options.storageMode || snapshot.storage?.mode || "memory",
      db_ready: options.dbReady === true,
      durable_summary_table: "release_evidence_summaries",
      immutable_hosted_snapshots: reports.some((item) => item.summary_snapshot_id)
    },
    release_evidence_summary: summary,
    release_evidence_health: health,
    next_action: health.next_action,
    hosted_report_snapshots: reports,
    safety: {
      raw_fixture_exposed: false,
      raw_request_body_exposed: false,
      raw_share_token_exposed: false,
      raw_secret_values_allowed: false,
      dry_run_receipts_labeled: summary.github_check_publish?.dry_run === true
        || summary.github_pr_comment_publish?.dry_run === true
        || summary.github_required_check_plan?.dry_run === true
    },
    next_actions: [
      "Persist this summary in Postgres with tenant/project/release keys.",
      "Bind live GitHub readback receipts before claiming required-check enforcement.",
      "Use hosted report snapshot ids so external reports keep the exact evidence shown at share time."
    ]
  };
}

function releaseEvidenceVersion(options = {}) {
  const value = String(options.version || options.schemaVersion || "").toLowerCase();
  return ["2", "v2", "a3.release_evidence_summary.v2", "a3.release_evidence_api_response.v2"].includes(value)
    ? "v2"
    : "v1";
}

function buildReleaseEvidenceV2Stats(snapshot = {}) {
  const runRecords = extractRunRecords(snapshot.runFixture);
  const grades = extractGradeResults(snapshot.gradeFixture);
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  return {
    runIds: runRecords.map((run) => run.run_id).filter(Boolean),
    caseCount: cases.length,
    a1: {
      runCount: runRecords.length,
      caseCount: cases.length,
      traceEventCount: cases.reduce((sum, item) => sum + (Array.isArray(item.trace_events) ? item.trace_events.length : 0), 0),
      observationCount: cases.reduce((sum, item) => sum + (Array.isArray(item.observations) ? item.observations.length : 0), 0),
      toolCallCaseCount: cases.filter((item) => (
        (Array.isArray(item.expected?.tool_calls) && item.expected.tool_calls.length > 0)
        || (Array.isArray(item.actual?.tool_calls) && item.actual.tool_calls.length > 0)
      )).length,
      missingRequiredFields: []
    },
    a2: {
      gradeCount: grades.length,
      judgeResultCount: cases.reduce((sum, item) => sum + (Array.isArray(item.judge_results) ? item.judge_results.length : item.grade ? 1 : 0), 0),
      failedCaseCount: cases.filter((item) => item.passed === false).length,
      failureClassCount: new Set(cases.map((item) => item.primary_failure_class).filter(Boolean)).size,
      missingRequiredFields: []
    }
  };
}

function releaseEvidenceReleaseId(snapshot = {}) {
  const direct = snapshot.releaseEvidence?.release_id || snapshot.release_evidence?.release_id;
  if (direct) {
    return direct;
  }
  return extractRunRecords(snapshot.runFixture)[0]?.run_id || `${snapshot.source || "mock"}-release`;
}

function releaseEvidenceIdMatches(requestedId, canonicalReleaseId, snapshot = {}) {
  const value = String(requestedId || "current");
  if (["current", canonicalReleaseId, snapshot.source].includes(value)) {
    return true;
  }
  return extractRunRecords(snapshot.runFixture).some((run) => run.run_id === value);
}

function snapshotMatchesTenantScope(snapshot = {}, options = {}) {
  return tenantScopeMatches(snapshot, options);
}

function reportMatchesSnapshotScope(report = {}, snapshot = {}) {
  const reportScope = reportTenantScope(report, snapshot);
  const snapshotScope = reportTenantScope(snapshot);
  return normalizeSourceKey(report.source || snapshot.source || "unknown") === normalizeSourceKey(snapshot.source || "unknown")
    && tenantScopeFieldsMatch(reportScope, snapshotScope);
}

function filterReportsForSnapshot(reports = [], snapshot = {}) {
  return (Array.isArray(reports) ? reports : []).filter((report) => reportMatchesSnapshotScope(report, snapshot));
}

function reportMatchesRequestScope(report = {}, snapshots = new Map(), options = {}) {
  const requestScope = resolveReportRequestScope(report, snapshots, options);
  if (requestScope.source && normalizeSourceKey(report.source || "unknown") !== requestScope.source) {
    return false;
  }
  const reportScope = reportTenantScope(report, snapshotForReport(snapshots, report));
  return tenantScopeMatches(reportScope, requestScope);
}

function resolveReportRequestScope(report = {}, snapshots = new Map(), options = {}) {
  const source = options.source ? normalizeSourceKey(options.source) : undefined;
  const snapshot = source ? findSnapshotForMutation(snapshots, source, options) : null;
  return {
    source,
    organizationId: options.organizationId || snapshot?.organizationId,
    tenantId: options.tenantId || snapshot?.tenantId,
    workspaceId: options.workspaceId || snapshot?.workspaceId,
    projectId: options.projectId || snapshot?.projectId,
    environmentId: options.environmentId || snapshot?.environmentId
  };
}

function reportTenantScope(report = {}, fallback = {}) {
  const scope = buildA3TenantScope(report, fallback || {});
  return {
    organizationId: scope.organization_id,
    tenantId: scope.tenant_id,
    workspaceId: scope.workspace_id,
    projectId: scope.project_id,
    environmentId: scope.environment_id
  };
}

function snapshotWithScope(snapshot = {}, options = {}) {
  if (options.enforceScope === true) {
    assertSnapshotScope(snapshot, options);
    return snapshot;
  }
  const fields = tenantScopeToSnapshotFields(buildA3TenantScope(options, snapshot));
  return {
    ...snapshot,
    ...fields,
    tenant_scope: buildA3TenantScope(fields)
  };
}

function assertSnapshotScope(snapshot, options = {}) {
  if (snapshot && !tenantScopeMatches(snapshot, options)) {
    throw new A3StoreResourceNotFoundError();
  }
  return snapshot;
}

function tenantScopeFieldsMatch(left = {}, right = {}) {
  return ["organizationId", "tenantId", "workspaceId", "projectId", "environmentId"]
    .every((field) => String(left[field]) === String(right[field]));
}

function snapshotForReport(snapshots = new Map(), report = {}) {
  return findSnapshotForMutation(
    snapshots,
    normalizeSourceKey(report.source || "unknown"),
    reportTenantScope(report)
  );
}

function reportStorageKey(report = {}, fallback = {}) {
  const scope = reportTenantScope(report, fallback);
  return `report:${sha256(stableJson({
    report_id: report.report_id || "missing",
    source: normalizeSourceKey(report.source || fallback.source || "unknown"),
    ...scope
  }))}`;
}

function findReportEntry(reports = new Map(), reportId, snapshots = new Map(), options = {}) {
  for (const [key, report] of reports.entries()) {
    if (report.report_id === reportId && reportMatchesRequestScope(report, snapshots, options)) {
      return { key, report };
    }
  }
  return null;
}

function filterTenantScopedRecords(records = [], snapshot = {}, options = {}) {
  const values = Array.isArray(records) ? records : [];
  if (options.enforceScope !== true) return values;
  return values.filter((record) => strictTenantRecordMatches(record, snapshot));
}

function strictTenantRecordMatches(record = {}, snapshot = {}) {
  if (!record || typeof record !== "object" || Array.isArray(record)) return false;
  const nested = record.tenant_scope || record.tenantScope || {};
  const explicitScope = {
    organization_id: record.organization_id ?? record.organizationId ?? nested.organization_id ?? nested.organizationId,
    tenant_id: record.tenant_id ?? record.tenantId ?? nested.tenant_id ?? nested.tenantId,
    workspace_id: record.workspace_id ?? record.workspaceId ?? nested.workspace_id ?? nested.workspaceId,
    project_id: record.project_id ?? record.projectId ?? nested.project_id ?? nested.projectId,
    environment_id: record.environment_id ?? record.environmentId ?? nested.environment_id ?? nested.environmentId
  };
  if (Object.values(explicitScope).some((value) => typeof value !== "string" || value.length === 0)) {
    return false;
  }
  if (!record.source || normalizeSourceKey(record.source) !== normalizeSourceKey(snapshot.source)) {
    return false;
  }
  return tenantScopeMatches(explicitScope, snapshot);
}

function buildAggregateScopeStatus(collections = {}, snapshot = {}, options = {}) {
  const excludedCounts = Object.fromEntries(Object.entries(collections).map(([name, records]) => (
    [name, options.enforceScope === true
      ? (Array.isArray(records) ? records : []).filter((record) => legacyRecordMatchesSnapshot(record, snapshot)).length
      : 0]
  )));
  const excludedTotal = Object.values(excludedCounts).reduce((total, value) => total + value, 0);
  return {
    schema_version: "a3.aggregate_scope_status.v1",
    strict_scope_enforced: options.enforceScope === true,
    status: options.enforceScope === true && excludedTotal > 0 ? "partial" : "complete",
    excluded_record_count: excludedTotal,
    excluded_counts: excludedCounts,
    reason: excludedTotal > 0
      ? "Legacy records for this source without an exact five-level tenant scope were excluded from hosted aggregates."
      : "All aggregate records matched the selected scope.",
    retry: "Re-ingest legacy records with organization, tenant, workspace, project, and environment scope.",
    safety: {
      unscoped_records_included: false,
      cross_tenant_fallback_allowed: false,
      foreign_record_counts_exposed: false
    }
  };
}

function legacyRecordMatchesSnapshot(record = {}, snapshot = {}) {
  if (!record || typeof record !== "object" || Array.isArray(record)) return false;
  if (!record.source || normalizeSourceKey(record.source) !== normalizeSourceKey(snapshot.source)) return false;
  const nested = record.tenant_scope || record.tenantScope || {};
  const scopePairs = [
    [record.organization_id ?? record.organizationId ?? nested.organization_id ?? nested.organizationId, snapshot.organizationId],
    [record.tenant_id ?? record.tenantId ?? nested.tenant_id ?? nested.tenantId, snapshot.tenantId],
    [record.workspace_id ?? record.workspaceId ?? nested.workspace_id ?? nested.workspaceId, snapshot.workspaceId],
    [record.project_id ?? record.projectId ?? nested.project_id ?? nested.projectId, snapshot.projectId],
    [record.environment_id ?? record.environmentId ?? nested.environment_id ?? nested.environmentId, snapshot.environmentId]
  ];
  const missingScope = scopePairs.some(([value]) => typeof value !== "string" || value.length === 0);
  const presentScopeMatches = scopePairs.every(([value, expected]) => (
    value === undefined || value === null || value === "" || String(value) === String(expected)
  ));
  return missingScope && presentScopeMatches;
}

function attachAdminActionRequests(adminConsole = {}, requests = [], options = {}) {
  const filteredRequests = filterAdminActionRequests(requests, options);
  return {
    ...adminConsole,
    action_requests: filteredRequests.slice(-8),
    action_request_summary: summarizeSaasAdminActionRequests(filteredRequests)
  };
}

function filterAdminActionRequests(requests = [], options = {}) {
  const organizationId = options.organizationId || "org-local";
  const projectId = options.projectId || "project-local";
  return (Array.isArray(requests) ? requests : []).filter((item) => (
    (item.organization_id || "org-local") === organizationId
    && (item.project_id || "project-local") === projectId
  ));
}

function filterReleaseEvidenceReadbacks(readbacks = [], options = {}) {
  const source = options.source ? normalizeSourceKey(options.source) : null;
  const releaseId = options.releaseId || "current";
  const organizationId = options.organizationId || "org-local";
  const projectId = options.projectId || "project-local";
  return (Array.isArray(readbacks) ? readbacks : []).filter((item) => (
    (!source || normalizeSourceKey(item.source || "unknown") === source)
    && (item.release_id || "current") === releaseId
    && (item.organization_id || "org-local") === organizationId
    && (item.project_id || "project-local") === projectId
  ));
}

function deploymentReceiptContext(snapshot = {}, dashboard = {}, options = {}) {
  const handoff = dashboard.deployment_handoff || {};
  const expected = handoff.candidate_binding?.expected || {};
  const release = dashboard.release_artifact_manifest?.release || snapshot.releaseArtifactManifest?.release || {};
  const run = extractRunRecords(snapshot.runFixture)[0] || {};
  return {
    source: snapshot.source || "unknown",
    expected_candidate_id: expected.candidate_sha_alias || release.git_sha_alias || snapshot.source || "unknown",
    expected_run_id: expected.run_id || run.run_id || "unknown",
    tenant_scope: eventTenantScopeFromRecord({}, snapshot),
    actor_hash: options.actor
      ? sha256(String(options.actor)).slice(0, 16)
      : options.actorHash || "actor_[REDACTED_HASH]",
    submitted_at: options.submittedAt || options.submitted_at
  };
}

function requireIdempotencyKey(options = {}, requestType, source) {
  if (typeof options.idempotencyKey === "string" && options.idempotencyKey.trim()) return;
  throw new A3StoreValidationError("Deployment receipt mutation requires an Idempotency-Key.", [
    { field: "Idempotency-Key", issue: "required" }
  ], {
    requestType,
    source
  });
}

function requireMutationIdempotencyKey(options = {}, requestType, source) {
  if (typeof options.idempotencyKey === "string" && options.idempotencyKey.trim()) return;
  throw new A3StoreValidationError("Mutation requires an Idempotency-Key.", [
    { field: "Idempotency-Key", issue: "required" }
  ], {
    requestType,
    source
  });
}

function sanitizeDeploymentReceiptRecord(record = {}) {
  const scope = eventTenantScopeFromRecord(record, {});
  const evidenceRef = typeof record.evidence_ref === "string"
    && !/^(?:https?|file):/i.test(record.evidence_ref)
    && !/[?#@\\]/.test(record.evidence_ref)
      ? record.evidence_ref.slice(0, 240)
      : "[REDACTED_UNSAFE_REF]";
  const evidenceSha256 = /^sha256:[a-f0-9]{64}$/i.test(String(record.evidence_sha256 || ""))
    ? String(record.evidence_sha256).toLowerCase()
    : null;
  return {
    schema_version: "a3.deployment_receipt.v1",
    receipt_id: safeIdentifier(record.receipt_id, "dpr"),
    source: normalizeSourceKey(record.source || "unknown"),
    tenant_scope: scope,
    ...scope,
    blocker_id: safeIdentifier(record.blocker_id, "blocker"),
    owner: String(record.owner || "Unassigned"),
    candidate_id: safeIdentifier(record.candidate_id, "candidate"),
    run_id: safeIdentifier(record.run_id, "run"),
    evidence_ref: evidenceRef,
    evidence_sha256: evidenceSha256,
    evidence_kind: safeIdentifier(record.evidence_kind, "evidence"),
    verifier_class: safeIdentifier(record.verifier_class, "verifier"),
    captured_at: record.captured_at || null,
    selectors: redactPotentialSecret(record.selectors || {}),
    status: String(record.status || "submitted"),
    version: Number.isInteger(Number(record.version)) ? Number(record.version) : 1,
    submitted_at: record.submitted_at || null,
    submitted_by_hash: safeActorId(record.submitted_by_hash),
    reviewed_at: record.reviewed_at || null,
    reviewed_by_hash: record.reviewed_by_hash ? safeActorId(record.reviewed_by_hash) : null,
    review_reason_code: record.review_reason_code || null,
    audit_event_id: record.audit_event_id ? safeIdentifier(record.audit_event_id, "event") : null,
    latest_audit_event_id: record.latest_audit_event_id ? safeIdentifier(record.latest_audit_event_id, "event") : null,
    metadata_validation: {
      status: record.metadata_validation?.status || "passed",
      schema_version: "a3.deployment_receipt.v1",
      payload_hash: String(record.metadata_validation?.payload_hash || "")
    },
    authority_validation: {
      status: record.authority_validation?.status || "pending_external_verifier",
      production_verified: false,
      authoritative_readback_id: null
    },
    acceptance_effect: {
      changes_deployment_acceptance: false,
      changes_release_ready: false,
      reason: String(record.acceptance_effect?.reason || "submission_is_not_authoritative_readback")
    },
    history: (Array.isArray(record.history) ? record.history : []).map((item, index) => ({
      sequence: Number(item.sequence || index + 1),
      action: String(item.action || "unknown"),
      status: String(item.status || "unknown"),
      actor_hash: safeActorId(item.actor_hash),
      reason_code: String(item.reason_code || "unknown"),
      created_at: item.created_at || null
    })),
    safety: {
      raw_evidence_embedded: false,
      raw_secret_values_allowed: false,
      raw_signed_urls_allowed: false,
      production_verified_by_submission: false,
      a2_decision_recomputed: false,
      deployment_acceptance_mutated: false
    }
  };
}

function deploymentReceiptAuditEvent(record = {}, phase = "submitted", index = 0) {
  const createdAt = phase === "reviewed" ? record.reviewed_at : record.submitted_at;
  return {
    event_id: `dpr_evt_${sha256(`${record.receipt_id}:${record.version}:${phase}:${index}`).slice(0, 16)}`,
    source: record.source,
    ...record.tenant_scope,
    event_type: phase === "reviewed" ? "deployment_receipt_reviewed" : "deployment_receipt_submitted",
    subject_id: record.receipt_id,
    actor_hash: phase === "reviewed" ? record.reviewed_by_hash : record.submitted_by_hash,
    payload: deploymentReceiptEventPayload(record, phase),
    created_at: createdAt,
    redacted: true
  };
}

function deploymentReceiptEventPayload(record = {}, phase = "submitted") {
  return {
    schema_version: "a3.deployment_receipt_event_payload.v1",
    receipt_id: record.receipt_id,
    blocker_id: record.blocker_id,
    candidate_id: record.candidate_id,
    run_id: record.run_id,
    phase,
    status: record.status,
    version: record.version,
    evidence_kind: record.evidence_kind,
    verifier_class: record.verifier_class,
    evidence_sha256: record.evidence_sha256,
    production_verified: false,
    deployment_acceptance_changed: false,
    a2_release_ready_changed: false,
    raw_evidence_embedded: false
  };
}

function deploymentReceiptReadbackAuditEvent(readback = {}, index = 0) {
  return {
    event_id: `dprv_evt_${sha256(`${readback.readback_id}:${readback.sequence}:${index}`).slice(0, 16)}`,
    source: readback.source,
    ...readback.tenant_scope,
    event_type: readback.production_verified
      ? "deployment_receipt_authoritatively_verified"
      : "deployment_receipt_authoritatively_rejected",
    subject_id: readback.readback_id,
    actor_hash: readback.resolver_id_alias,
    payload: deploymentReceiptReadbackEventPayload(readback),
    created_at: readback.verified_at,
    redacted: true
  };
}

function deploymentReceiptReadbackEventPayload(readback = {}) {
  return {
    schema_version: "a3.deployment_receipt_readback_event_payload.v1",
    readback_id: readback.readback_id,
    receipt_id: readback.receipt_id,
    blocker_id: readback.blocker_id,
    candidate_id: readback.candidate_id,
    run_id: readback.run_id,
    verification_status: readback.verification_status,
    reason_code: readback.reason_code,
    sequence: readback.sequence,
    evidence_sha256: readback.evidence_sha256,
    attestation_sha256: readback.attestation_sha256,
    readback_hash: readback.readback_hash,
    production_verified: readback.production_verified === true,
    source_acceptance_mutated: false,
    a2_release_ready_changed: false,
    raw_evidence_embedded: false
  };
}

function recordEventOutbox(eventOutbox, input = {}) {
  const createdAt = input.createdAt || input.created_at || new Date().toISOString();
  const resourceType = input.resourceType || input.resource_type || "unknown";
  const resourceId = input.resourceId || input.resource_id || "unknown";
  const eventType = input.eventType || input.event_type || "unknown.event";
  const eventSeed = stableJson({
    eventType,
    resourceType,
    resourceId,
    createdAt,
    source: input.source || "unknown"
  });
  const envelope = buildA3EventEnvelope({
    event_type: eventType,
    resource_type: resourceType,
    resource_id: resourceId,
    tenant_scope: input.tenantScope || input.tenant_scope || {},
    actor_id: input.actorId || input.actor_id || safeActorId(input.actor || input.actorHash || input.actor_hash),
    request_id: input.requestId || input.request_id || `req_${sha256(eventSeed).slice(0, 12)}`,
    trace_id: input.traceId || input.trace_id || `trace_${sha256(`${eventSeed}:trace`).slice(0, 12)}`,
    created_at: createdAt,
    payload_ref: input.payloadRef || input.payload_ref || null,
    payload: redactPotentialSecret(input.payload || {}),
    usage_meter: input.usageMeter || input.usage_meter || null
  });
  const validation = validateA3EventEnvelope(envelope);
  if (!validation.valid) {
    throw new A3StoreValidationError("A3 event envelope failed validation.", validation.errors.map((issue) => ({
      field: "event_outbox",
      issue
    })), {
      requestType: "event_outbox_record",
      source: input.source || "unknown",
      statusCode: 500,
      error: "event_outbox_validation_error"
    });
  }
  const row = sanitizeEventOutboxRow({
    source: input.source,
    envelope,
    delivery_status: input.deliveryStatus || input.delivery_status || "pending",
    delivery_attempts: input.deliveryAttempts || input.delivery_attempts || 0,
    next_attempt_at: input.nextAttemptAt || input.next_attempt_at || null,
    last_error_class: input.lastErrorClass || input.last_error_class || null
  });
  eventOutbox.push(row);
  return row;
}

function sanitizeEventOutboxRow(row = {}) {
  const envelope = row.envelope || row.event_envelope || row;
  return {
    schema_version: "a3.event_outbox_row.v1",
    id: row.id || envelope.event_id,
    event_id: envelope.event_id,
    source: normalizeSourceKey(row.source || envelope.source || "mock"),
    event_type: envelope.event_type,
    event_schema_version: envelope.schema_version,
    organization_id: envelope.organization_id || "org-local",
    tenant_id: envelope.tenant_id || "tenant-local",
    workspace_id: envelope.workspace_id || "workspace-local",
    project_id: envelope.project_id || "project-local",
    environment_id: envelope.environment_id || "staging",
    actor_id: safeActorId(envelope.actor_id),
    request_id: safeIdentifier(envelope.request_id, "req"),
    trace_id: safeIdentifier(envelope.trace_id, "trace"),
    resource_type: envelope.resource_type || "unknown",
    resource_id: safeIdentifier(envelope.resource_id, "resource"),
    payload_ref: envelope.payload_ref || null,
    payload_hash: envelope.payload_hash,
    payload_inline: false,
    payload_schema_version: envelope.payload_schema_version || null,
    redaction_status: envelope.redaction_status || "metadata_only",
    usage_meter: redactPotentialSecret(envelope.usage_meter || null),
    delivery_status: row.delivery_status || "pending",
    delivery_attempts: row.delivery_attempts || 0,
    next_attempt_at: row.next_attempt_at || null,
    last_error_class: row.last_error_class || null,
    created_at: envelope.created_at || row.created_at || new Date().toISOString(),
    envelope: {
      ...envelope,
      actor_id: safeActorId(envelope.actor_id),
      request_id: safeIdentifier(envelope.request_id, "req"),
      trace_id: safeIdentifier(envelope.trace_id, "trace"),
      resource_id: safeIdentifier(envelope.resource_id, "resource"),
      payload_inline: false
    },
    safety: {
      metadata_only: true,
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_cookie_values_allowed: false,
      raw_signed_urls_allowed: false,
      raw_actor_identity_exposed: false
    }
  };
}

function filterEventOutboxRows(rows = [], options = {}) {
  const source = options.source ? normalizeSourceKey(options.source) : null;
  return (Array.isArray(rows) ? rows : []).filter((row) => (
    (!source || normalizeSourceKey(row.source || "unknown") === source)
    && (!options.organizationId || row.organization_id === options.organizationId)
    && (!options.tenantId || row.tenant_id === options.tenantId)
    && (!options.workspaceId || row.workspace_id === options.workspaceId)
    && (!options.projectId || row.project_id === options.projectId)
    && (!options.environmentId || row.environment_id === options.environmentId)
    && (!options.eventType || row.event_type === options.eventType)
    && (!options.deliveryStatus || row.delivery_status === options.deliveryStatus)
  ));
}

function buildEventOutboxDashboard(rows = [], options = {}) {
  const events = filterEventOutboxRows(rows, options);
  return {
    schema_version: "a3.event_outbox_dashboard.v1",
    source: options.source || "unknown",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      tenant_id: options.tenantId || "tenant-local",
      workspace_id: options.workspaceId || "workspace-local",
      project_id: options.projectId || "project-local",
      environment_id: options.environmentId || "staging"
    },
    available: events.length > 0,
    event_count: events.length,
    status_counts: countBy(events, "delivery_status"),
    event_type_counts: countBy(events, "event_type"),
    latest_events: events.slice(-8).map((event) => ({
      event_id: event.event_id,
      event_type: event.event_type,
      resource_type: event.resource_type,
      resource_id: event.resource_id,
      delivery_status: event.delivery_status,
      created_at: event.created_at,
      payload_hash_prefix: typeof event.payload_hash === "string" ? event.payload_hash.slice(0, 16) : null
    })),
    a1_a2_boundary: "Outbox records A3 control-plane actions only; A1 RunResult and A2 GradeResult remain source-of-truth evidence.",
    safety: {
      metadata_only: true,
      raw_payload_embedded: false,
      raw_secret_values_allowed: false,
      raw_actor_identity_exposed: false
    }
  };
}

function attachEventEnvelopeReceipt(receipt = {}, row = {}) {
  return {
    ...receipt,
    event_outbox_id: row.event_id || null,
    event_outbox_delivery_status: row.delivery_status || "pending",
    event_envelope: row.envelope || null
  };
}

function attachIdempotencyReceipt(receipt = {}, idempotencyKey) {
  return {
    ...receipt,
    idempotency: idempotencyState(idempotencyKey)
  };
}

function idempotencyState(idempotencyKey) {
  return {
    key_present: Boolean(idempotencyKey),
    duplicate: false,
    status: idempotencyKey ? "recorded" : "not_provided"
  };
}

function shareReportEventPayload(report = {}) {
  return {
    schema_version: "a3.shareable_report_event_payload.v1",
    report_id: report.report_id,
    source: report.source,
    title: report.title,
    status: report.status,
    visibility: report.visibility || "private_link",
    share_url_path: "/r/[REDACTED_TOKEN]",
    token_hash_prefix: report.share_link?.token_hash_prefix || null,
    sealed_payload_hash_present: Boolean(report.sealed_evidence?.payload_hash),
    release_evidence_summary_available: report.release_evidence_summary?.available === true,
    raw_share_token_included: false
  };
}

function reportViewEventPayload(event = {}) {
  return {
    schema_version: "a3.report_view_event_payload.v1",
    event_id: event.event_id,
    report_id: event.report_id,
    event_type: event.event_type,
    access_result: event.access_result || "allowed",
    viewed_at: event.viewed_at,
    viewer: safeActorId(event.viewer),
    token_hash_prefix: event.token_hash_prefix || null,
    raw_share_token_included: false
  };
}

function eventTenantScopeFromRecord(record = {}, snapshot = {}) {
  return {
    organization_id: record.organization_id || snapshot.organizationId,
    tenant_id: record.tenant_id || snapshot.tenantId,
    workspace_id: record.workspace_id || snapshot.workspaceId,
    project_id: record.project_id || snapshot.projectId,
    environment_id: record.environment_id || snapshot.environmentId
  };
}

function tenantScopeRecordFields(primary = {}, fallback = {}) {
  const scope = buildA3TenantScope(primary, fallback);
  return {
    organization_id: scope.organization_id,
    tenant_id: scope.tenant_id,
    workspace_id: scope.workspace_id,
    project_id: scope.project_id,
    environment_id: scope.environment_id,
    tenant_scope: scope
  };
}

function optionalTenantScopeRecordFields(record = {}) {
  const nested = record.tenant_scope || record.tenantScope || {};
  return {
    schema_version: "a3.tenant_scope.v1",
    organization_id: record.organization_id ?? record.organizationId ?? nested.organization_id ?? nested.organizationId ?? null,
    tenant_id: record.tenant_id ?? record.tenantId ?? nested.tenant_id ?? nested.tenantId ?? null,
    workspace_id: record.workspace_id ?? record.workspaceId ?? nested.workspace_id ?? nested.workspaceId ?? null,
    project_id: record.project_id ?? record.projectId ?? nested.project_id ?? nested.projectId ?? null,
    environment_id: record.environment_id ?? record.environmentId ?? nested.environment_id ?? nested.environmentId ?? null
  };
}

function safeActorId(value) {
  const text = String(value || "actor-system");
  if (/Bearer\s+|Cookie:|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|sk-|ghp_|github_pat_|ashr_/i.test(text)) {
    return `actor_${sha256(text).slice(0, 16)}`;
  }
  return text.replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 80) || "actor-system";
}

function safeIdentifier(value, prefix = "id") {
  const text = String(value || `${prefix}-unknown`);
  if (/Bearer\s+|Cookie:|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|sk-|ghp_|github_pat_|ashr_/i.test(text)) {
    return `${prefix}_${sha256(text).slice(0, 16)}`;
  }
  return text.replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 120) || `${prefix}-unknown`;
}

function latestReleaseEvidenceReadbacks(readbacks = [], options = {}) {
  const filtered = filterReleaseEvidenceReadbacks(readbacks, options);
  const byKind = {};
  for (const readback of filtered) {
    byKind[readback.resource_kind] = readback;
  }
  return {
    github_check: byKind.github_check || byKind.check_run || null,
    pr_comment: byKind.pr_comment || null,
    required_check: byKind.required_check || null,
    records: filtered
  };
}

function buildReleaseEvidenceReadbackDashboardHistory(readbacks = [], options = {}) {
  const filtered = filterReleaseEvidenceReadbacks(readbacks, options);
  const records = filtered.map((readback) => ({
    schema_version: "a3.release_evidence_readback_dashboard_record.v1",
    readback_id: readback.readback_id,
    provider: readback.provider || "github",
    resource_kind: normalizeReadbackResourceKind(readback.resource_kind),
    readback_status: readback.readback_status || "missing",
    readback_confirmed: readback.readback_confirmed === true,
    stale: readback.stale === true,
    missing: readback.missing === true,
    deleted: readback.deleted === true,
    enforced: readback.enforced === true,
    check_name: readback.check_name || "unknown",
    external_id_alias: readback.external_id_alias || null,
    head_sha_alias: readback.head_sha_alias || null,
    payload_hash_prefix: typeof readback.payload_hash === "string" ? readback.payload_hash.slice(0, 16) : null,
    captured_at: readback.captured_at || null,
    actor_hash: readback.actor_hash || "actor_[REDACTED_HASH]",
    sanitized_error_class: readback.sanitized_error_class || null
  }));
  return {
    schema_version: "a3.release_evidence_readback_dashboard.v1",
    release_id: options.releaseId || "current",
    source: options.source || "unknown",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local"
    },
    available: records.length > 0,
    readback_count: records.length,
    status_counts: countBy(records, "readback_status"),
    resource_counts: countBy(records, "resource_kind"),
    latest_records: records.slice(-8),
    a1_a2_boundary: "Readback confirms external publication state; keep A1 RunResult and A2 GradeResult as separate source-of-truth evidence.",
    safety: {
      raw_payload_exposed: false,
      raw_secret_values_allowed: false,
      raw_actor_identity_exposed: false
    }
  };
}

function mergeReleaseEvidenceWithGitHubReceipts(releaseEvidence = {}, receipts = [], options = {}) {
  const filtered = filterGitHubPublishReceipts(receipts, options);
  const latestCheck = [...filtered].reverse().find((item) => item.resource_kind === "github_check");
  const latestPrComment = [...filtered].reverse().find((item) => item.resource_kind === "pr_comment");
  return {
    ...(releaseEvidence || {}),
    githubCheckPublishReceipt: latestCheck || releaseEvidence.githubCheckPublishReceipt || releaseEvidence.github_check_publish_receipt || releaseEvidence.github_check_publish || {},
    github_check_publish_receipt: latestCheck || releaseEvidence.github_check_publish_receipt || releaseEvidence.githubCheckPublishReceipt || releaseEvidence.github_check_publish || {},
    githubPrCommentPublishReceipt: latestPrComment || releaseEvidence.githubPrCommentPublishReceipt || releaseEvidence.github_pr_comment_publish_receipt || releaseEvidence.github_pr_comment_publish || {},
    github_pr_comment_publish_receipt: latestPrComment || releaseEvidence.github_pr_comment_publish_receipt || releaseEvidence.githubPrCommentPublishReceipt || releaseEvidence.github_pr_comment_publish || {}
  };
}

function buildLiveReleaseAuthorization(snapshot = {}, options = {}) {
  const spine = snapshot.a2TrustedSpine || snapshot.a2_trusted_spine || {};
  const authority = evaluateA2TrustedReleaseAuthority(spine, {
    expectedScope: tenantScopeRecordFields(snapshot),
    expectedHeadHash: options.decisionLedgerHeadHash
      || options.decision_ledger_head_hash
      || options.decisionHash
      || options.decision_hash,
    expectedRecordId: options.decisionRecordId || options.decision_record_id,
    requireSelectors: true
  });
  return {
    schema_version: "a3.live_release_authorization.v1",
    allowed: authority.allowed,
    decision: authority.decision,
    reason_code: authority.reason_code,
    blockers: authority.blockers,
    release_id: releaseEvidenceReleaseId(snapshot),
    source: snapshot.source,
    release_ready: authority.release_ready,
    upstream_decision: authority.upstream_decision,
    integrity_verified: authority.integrity_verified,
    decision_ledger: authority.decision_ledger,
    safety: authority.safety
  };
}

function assertLiveReleaseAuthorization(snapshot = {}, options = {}) {
  const authorization = buildLiveReleaseAuthorization(snapshot, options);
  if (!authorization.allowed) {
    throw new A3StoreValidationError(
      "Live publication requires a current release-ready A2 Decision Ledger record.",
      authorization.blockers.map((reason) => ({ field: "a2_decision_ledger", reason })),
      {
        requestType: "live_release_publish",
        source: snapshot.source,
        statusCode: 403,
        error: "a2_release_decision_required"
      }
    );
  }
  return authorization;
}

function assertTrustedLiveMutationAuthority(store = {}, snapshot = {}, options = {}, integrityAuthorization = {}) {
  if (store.github_executor_authority !== "a1_trusted_worker") {
    throw new A3StoreValidationError(
      "Live GitHub publication requires an A1 trusted worker.",
      [{ field: "github_executor_authority", reason: "a1_trusted_worker_required" }],
      {
        requestType: "live_release_publish",
        source: snapshot.source,
        statusCode: 403,
        error: "trusted_github_executor_required"
      }
    );
  }

  const trustedAuthorization = options.trustedReleaseAuthorization || {};
  const expectedHeadHash = options.decisionLedgerHeadHash || options.decision_ledger_head_hash;
  const expectedRecordId = options.decisionRecordId || options.decision_record_id;
  const trustedAuthorizationMatches = trustedAuthorization.authority === "a2_trusted_service"
    && trustedAuthorization.allowed === true
    && trustedAuthorization.release_ready === true
    && trustedAuthorization.upstream_decision === "allow"
    && trustedAuthorization.decision_ledger?.head_hash === expectedHeadHash
    && trustedAuthorization.decision_ledger?.record_id === expectedRecordId
    && tenantScopeMatches(snapshot, trustedAuthorization.tenant_scope || {});
  if (!trustedAuthorizationMatches) {
    throw new A3StoreValidationError(
      "Live publication requires a server-resolved A2 authority attestation.",
      [{ field: "trusted_release_authorization", reason: "a2_trusted_service_attestation_required" }],
      {
        requestType: "live_release_publish",
        source: snapshot.source,
        statusCode: 403,
        error: "a2_trusted_authority_required"
      }
    );
  }

  const githubTarget = options.trustedGitHubTarget || {};
  const githubTargetMatches = githubTarget.authority === "a1_github_installation"
    && githubTarget.repo === options.repo
    && tenantScopeMatches(snapshot, githubTarget.tenant_scope || {});
  if (!githubTargetMatches) {
    throw new A3StoreValidationError(
      "Live publication requires a tenant-bound GitHub installation target.",
      [{ field: "trusted_github_target", reason: "tenant_repository_binding_required" }],
      {
        requestType: "live_release_publish",
        source: snapshot.source,
        statusCode: 403,
        error: "trusted_github_target_required"
      }
    );
  }

  return {
    schema_version: "a3.trusted_live_release_authorization.v1",
    authority: trustedAuthorization.authority,
    allowed: true,
    release_ready: true,
    upstream_decision: "allow",
    integrity_verified: integrityAuthorization.integrity_verified === true,
    decision_ledger: {
      head_hash: expectedHeadHash,
      record_id: expectedRecordId,
      chain_verified: integrityAuthorization.decision_ledger?.chain_verified === true
    },
    github_target: {
      authority: githubTarget.authority,
      repo: githubTarget.repo,
      tenant_scope_bound: true
    },
    safety: {
      a2_authority_server_resolved: true,
      github_target_server_resolved: true,
      client_attestation_trusted: false
    }
  };
}

function buildGitHubPublishGatePayload(snapshot = {}, options = {}) {
  const releaseWorkflow = summarizeReleaseWorkflow(
    snapshot.runFixture,
    snapshot.gradeFixture,
    snapshot.coverage,
    snapshot.mediaSignedUrlCoverage,
    {
      release_version: options.releaseVersion,
      environment: options.environment,
      headSha: options.headSha,
      generatedAt: options.generatedAt
    }
  );
  return {
    schema_version: "a3.github_publish_gate_payload.v1",
    source: snapshot.source || "mock",
    summary: buildDashboardSummary(snapshot.runFixture, snapshot.gradeFixture),
    release_workflow: releaseWorkflow,
    github_check_run: releaseWorkflow.github_check,
    pr_comment_markdown: releaseWorkflow.pr_comment_markdown
  };
}

function sanitizeGitHubPublishReceipt(receipt = {}) {
  const sanitized = redactPotentialSecret(receipt || {});
  const resourceKind = normalizeGitHubPublishResourceKind(sanitized.resource_kind || sanitized.resourceKind || (
    sanitized.schema_version === "a3.github_pr_comment_publish_receipt.v1" ? "pr_comment" : "github_check"
  ));
  const payloadHash = sanitized.payload_hash || sha256(stableJson({
    schema_version: sanitized.schema_version,
    resource_kind: resourceKind,
    mode: sanitized.mode,
    dry_run: sanitized.dry_run,
    posted: sanitized.posted,
    status: sanitized.status,
    http_status: sanitized.http_status,
    request: sanitized.request || sanitized.plan
  }));
  return {
    schema_version: "a3.github_publish_receipt_record.v1",
    original_schema_version: sanitized.schema_version || "unknown",
    publish_id: sanitized.publish_id || `ghpub_${sha256(`${resourceKind}:${payloadHash}`).slice(0, 16)}`,
    provider: "github",
    resource_kind: resourceKind,
    source: normalizeSourceKey(sanitized.source || "mock"),
    release_id: sanitized.release_id || "current",
    organization_id: sanitized.organization_id || "org-local",
    tenant_id: sanitized.tenant_id || sanitized.tenant_scope?.tenant_id || null,
    workspace_id: sanitized.workspace_id || sanitized.tenant_scope?.workspace_id || null,
    project_id: sanitized.project_id || "project-local",
    environment_id: sanitized.environment_id || sanitized.tenant_scope?.environment_id || null,
    tenant_scope: optionalTenantScopeRecordFields(sanitized),
    mode: sanitized.mode || "unknown",
    status: sanitized.status || "unknown",
    dry_run: sanitized.dry_run !== false,
    posted: sanitized.posted === true,
    http_status: sanitized.http_status ?? null,
    github_request_id: sanitized.github_request_id || null,
    external_id_alias: sanitized.check_run?.id || sanitized.comment?.id || sanitized.plan?.existing_comment_id || null,
    check_name: sanitized.request?.body?.name || sanitized.check_run?.name || "Ashr++ Release Gate",
    pull_number: sanitized.plan?.pull_number || null,
    repo: sanitized.request?.repo || sanitized.plan?.repo || null,
    payload_hash: payloadHash,
    a2_decision_authorization: sanitizeLiveReleaseAuthorization(sanitized.a2_decision_authorization),
    actor_hash: sanitized.actor_hash || "actor_[REDACTED_HASH]",
    published_at: sanitized.published_at || new Date().toISOString(),
    safety: {
      ...(sanitized.safety || {}),
      token_included: false,
      secret_values_allowed: false,
      raw_response_body_stored: false,
      live_external_mutation_performed: sanitized.posted === true && sanitized.dry_run === false
    }
  };
}

function sanitizeLiveReleaseAuthorization(authorization) {
  if (!authorization || typeof authorization !== "object") return null;
  return {
    schema_version: "a3.live_release_authorization.v1",
    allowed: authorization.allowed === true,
    decision: authorization.decision || "unknown",
    reason_code: authorization.reason_code || "unknown",
    release_id: authorization.release_id || "current",
    release_ready: authorization.release_ready === true,
    upstream_decision: authorization.upstream_decision || "unknown",
    decision_ledger: {
      schema_version: authorization.decision_ledger?.schema_version || "missing",
      head_hash: authorization.decision_ledger?.head_hash || null,
      record_id: authorization.decision_ledger?.record_id || null,
      chain_verified: authorization.decision_ledger?.chain_verified === true
    },
    safety: {
      a2_authority_preserved: true,
      a3_score_recomputed: false,
      a3_release_ready_recomputed: false,
      raw_evidence_included: false,
      secret_values_allowed: false
    }
  };
}

function buildGitHubPublishReceiptDashboard(receipts = [], options = {}) {
  const filtered = filterGitHubPublishReceipts(receipts, options);
  const latestRecords = filtered.slice(-8).map((receipt) => ({
    publish_id: receipt.publish_id,
    provider: receipt.provider,
    resource_kind: receipt.resource_kind,
    status: receipt.status,
    dry_run: receipt.dry_run,
    posted: receipt.posted,
    mode: receipt.mode,
    http_status: receipt.http_status,
    check_name: receipt.check_name,
    pull_number: receipt.pull_number,
    payload_hash_prefix: typeof receipt.payload_hash === "string" ? receipt.payload_hash.slice(0, 16) : null,
    published_at: receipt.published_at,
    actor_hash: receipt.actor_hash
  }));
  return {
    schema_version: "a3.github_publish_receipt_dashboard.v1",
    source: options.source || "unknown",
    release_id: options.releaseId || "current",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local"
    },
    available: filtered.length > 0,
    receipt_count: filtered.length,
    posted_count: filtered.filter((item) => item.posted).length,
    dry_run_count: filtered.filter((item) => item.dry_run).length,
    status_counts: countBy(filtered, "status"),
    resource_counts: countBy(filtered, "resource_kind"),
    latest_records: latestRecords,
    a1_a2_boundary: "Publish receipts are A3 control-plane evidence; A1 RunResult and A2 GradeResult remain unchanged and readback must confirm external GitHub state.",
    safety: {
      token_included: false,
      raw_response_body_stored: false,
      raw_secret_values_allowed: false,
      real_github_mutation_possible_only_with_explicit_live_mode: true
    }
  };
}

function filterGitHubPublishReceipts(receipts = [], options = {}) {
  const source = options.source ? normalizeSourceKey(options.source) : null;
  const releaseId = options.releaseId || "current";
  const organizationId = options.organizationId || "org-local";
  const projectId = options.projectId || "project-local";
  return (Array.isArray(receipts) ? receipts : []).filter((item) => (
    (!source || normalizeSourceKey(item.source || "unknown") === source)
    && (item.release_id || "current") === releaseId
    && (item.organization_id || "org-local") === organizationId
    && (item.project_id || "project-local") === projectId
  ));
}

function normalizeGitHubPublishResourceKind(value) {
  const kind = String(value || "github_check").toLowerCase();
  if (["check_run", "github_check"].includes(kind)) {
    return "github_check";
  }
  if (["pr_comment", "pull_request_comment"].includes(kind)) {
    return "pr_comment";
  }
  return kind;
}

function githubPublishAuditEvent(receipt = {}, index = 0) {
  return {
    event_id: `ghpub_evt_${sha256(`${receipt.publish_id || "missing"}:${index}`).slice(0, 12)}`,
    source: receipt.source,
    ...tenantScopeRecordFields(receipt),
    event_type: receipt.resource_kind === "pr_comment"
      ? "github.pr_comment_publish_requested"
      : "github.check_publish_requested",
    subject_id: receipt.publish_id,
    payload: {
      schema_version: receipt.schema_version,
      publish_id: receipt.publish_id,
      release_id: receipt.release_id,
      resource_kind: receipt.resource_kind,
      mode: receipt.mode,
      status: receipt.status,
      dry_run: receipt.dry_run,
      posted: receipt.posted,
      payload_hash: receipt.payload_hash,
      token_included: false,
      secret_values_included: false
    },
    created_at: receipt.published_at || new Date().toISOString(),
    redacted: true
  };
}

function sanitizeReleaseEvidenceReadback(readback = {}) {
  const sanitizedPayload = redactPotentialSecret(readback);
  const resourceKind = normalizeReadbackResourceKind(sanitizedPayload.resource_kind || sanitizedPayload.resourceKind);
  const payloadHash = sanitizedPayload.payload_hash || sha256(stableJson({
    schema_version: sanitizedPayload.schema_version,
    resource_kind: resourceKind,
    readback_status: sanitizedPayload.readback_status,
    expected: sanitizedPayload.expected,
    observed: sanitizedPayload.observed,
    matches: sanitizedPayload.matches,
    proof_id: sanitizedPayload.proof_id
  }));
  return {
    schema_version: sanitizedPayload.schema_version || "a3.release_evidence_readback_record.v1",
    proof_id: sanitizedPayload.proof_id || null,
    readback_id: sanitizedPayload.readback_id
      || sanitizedPayload.proof_id
      || `rerb_${sha256(`${resourceKind}:${payloadHash}`).slice(0, 16)}`,
    provider: sanitizedPayload.provider || "github",
    resource_kind: resourceKind,
    source: normalizeSourceKey(sanitizedPayload.source || "mock"),
    release_id: sanitizedPayload.release_id || "current",
    organization_id: sanitizedPayload.organization_id || "org-local",
    tenant_id: sanitizedPayload.tenant_id || sanitizedPayload.tenant_scope?.tenant_id || null,
    workspace_id: sanitizedPayload.workspace_id || sanitizedPayload.tenant_scope?.workspace_id || null,
    project_id: sanitizedPayload.project_id || "project-local",
    environment_id: sanitizedPayload.environment_id || sanitizedPayload.tenant_scope?.environment_id || null,
    tenant_scope: optionalTenantScopeRecordFields(sanitizedPayload),
    readback_status: sanitizedPayload.readback_status || sanitizedPayload.enforcement_readback_status || "missing",
    enforcement_readback_status: sanitizedPayload.enforcement_readback_status || sanitizedPayload.readback_status || "missing",
    check_name: sanitizedPayload.check_name || sanitizedPayload.expected?.check_name || sanitizedPayload.matched_check?.context || null,
    posted: sanitizedPayload.posted === true,
    readback_confirmed: sanitizedPayload.readback_confirmed === true || sanitizedPayload.readback_status === "readback_confirmed",
    stale: sanitizedPayload.stale === true || sanitizedPayload.readback_status === "stale",
    missing: sanitizedPayload.missing === true || sanitizedPayload.readback_status === "missing",
    deleted: sanitizedPayload.deleted === true || sanitizedPayload.readback_status === "deleted",
    enforced: sanitizedPayload.enforced === true,
    payload_hash: payloadHash,
    external_id_alias: sanitizedPayload.expected?.check_run_id_alias
      || sanitizedPayload.expected?.comment_id_alias
      || sanitizedPayload.matched_check?.context
      || sanitizedPayload.check_name
      || null,
    head_sha_alias: sanitizedPayload.expected?.head_sha_alias || sanitizedPayload.observed?.head_sha_alias || null,
    sanitized_error_class: sanitizedPayload.sanitized_error_class || null,
    captured_at: sanitizedPayload.captured_at || sanitizedPayload.checked_at || new Date().toISOString(),
    actor_hash: sanitizedPayload.actor_hash || "actor_[REDACTED_HASH]",
    payload: {
      schema_version: sanitizedPayload.schema_version || "unknown",
      expected: sanitizedPayload.expected || null,
      observed: sanitizedPayload.observed || null,
      matches: sanitizedPayload.matches || null,
      safety: {
        ...(sanitizedPayload.safety || {}),
        token_included: false,
        secret_values_allowed: false,
        raw_body_stored: false
      }
    },
    safety: {
      token_included: false,
      secret_values_allowed: false,
      raw_body_stored: false,
      real_cloud_mutation_performed: false
    }
  };
}

function normalizeReadbackResourceKind(value) {
  const kind = String(value || "unknown").toLowerCase();
  if (["check_run", "github_check"].includes(kind)) {
    return "github_check";
  }
  if (["pr_comment", "pull_request_comment"].includes(kind)) {
    return "pr_comment";
  }
  if (["required_check", "branch_protection"].includes(kind)) {
    return "required_check";
  }
  return kind;
}

function releaseEvidenceReadbackAuditEvent(readback = {}, index = 0) {
  return {
    event_id: `rerb_evt_${sha256(`${readback.readback_id || "missing"}:${index}`).slice(0, 12)}`,
    source: readback.source,
    ...tenantScopeRecordFields(readback),
    event_type: "release_evidence.readback_captured",
    subject_id: readback.readback_id,
    payload: {
      schema_version: readback.schema_version,
      release_id: readback.release_id,
      provider: readback.provider,
      resource_kind: readback.resource_kind,
      readback_status: readback.readback_status,
      payload_hash: readback.payload_hash,
      raw_body_stored: false,
      secret_values_included: false
    },
    created_at: readback.captured_at || new Date().toISOString(),
    redacted: true
  };
}

function countBy(items = [], field) {
  return items.reduce((counts, item) => {
    const key = item[field] || "unknown";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function sanitizeAdminActionRequest(request = {}) {
  return {
    schema_version: request.schema_version || "a3.saas_admin_action_request.v1",
    request_id: request.request_id,
    source: request.source || "unknown",
    action: request.action || "unknown",
    area: request.area || "unknown",
    mode: request.mode || "unknown",
    status: request.status || "unknown",
    organization_id: request.organization_id || "org-local",
    tenant_id: request.tenant_id || request.tenant_scope?.tenant_id || null,
    workspace_id: request.workspace_id || request.tenant_scope?.workspace_id || null,
    project_id: request.project_id || "project-local",
    environment_id: request.environment_id || request.tenant_scope?.environment_id || null,
    tenant_scope: optionalTenantScopeRecordFields(request),
    actor_hash: request.actor_hash || request.requested_by_hash || "actor_[REDACTED_HASH]",
    requested_by_hash: request.requested_by_hash || request.actor_hash || "actor_[REDACTED_HASH]",
    requested_at: request.requested_at || new Date().toISOString(),
    request_hash: request.request_hash || sha256(stableJson(request)),
    reason: redactPotentialSecret(request.reason || ""),
    next_step: redactPotentialSecret(request.next_step || ""),
    requires_hosted_auth: request.requires_hosted_auth === true,
    requires_reviewer_approval: request.requires_reviewer_approval === true,
    real_cloud_mutation_performed: false,
    writes_real_ashr_cloud: request.writes_real_ashr_cloud === true,
    secret_values_included: false,
    target: sanitizeAdminActionTarget(request.target),
    safety: {
      ...(request.safety || {}),
      no_real_ashr_write: true,
      raw_api_key_values_allowed: false,
      raw_email_values_allowed: false,
      raw_token_values_allowed: false,
      redacted_identity_only: true
    },
    plan: {
      action: request.plan?.action || request.action || "unknown",
      area: request.plan?.area || request.area || "unknown",
      mode: request.plan?.mode || request.mode || "unknown",
      enabled: request.plan?.enabled === true,
      risk: request.plan?.risk || "unknown",
      writes_real_ashr_cloud: request.plan?.writes_real_ashr_cloud === true,
      secret_values_included: false
    }
  };
}

function sanitizeAdminActionTarget(target = {}) {
  if (!target || typeof target !== "object" || Array.isArray(target)) {
    return {};
  }
  return Object.fromEntries(Object.entries(target)
    .filter(([key]) => !/secret|token|cookie|email|password|key_value/i.test(key))
    .map(([key, value]) => [key, redactPotentialSecret(value)]));
}

function redactPotentialSecret(value) {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof value === "object") {
    return JSON.parse(JSON.stringify(value, (key, item) => (
      /authorization|secret|token|cookie|email|password|key_value|api_key|access_key|private_key/i.test(key)
        && typeof item !== "boolean"
        && typeof item !== "number"
        ? "[REDACTED]"
        : typeof item === "string"
          ? redactPotentialSecretString(item)
          : item
    )));
  }
  return redactPotentialSecretString(String(value));
}

function redactPotentialSecretString(value) {
  return String(value)
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]")
    .replace(/\b(Bearer\s+)[A-Za-z0-9._-]{12,}/g, "$1[REDACTED]")
    .replace(/\b(sk-|ghp_|github_pat_|ashr_)[A-Za-z0-9._-]{12,}/gi, "[REDACTED_SECRET]");
}

function filterReviewWorkflowRecords(records = [], options = {}) {
  const organizationId = options.organizationId || "org-local";
  const projectId = options.projectId || "project-local";
  return (Array.isArray(records) ? records : []).filter((item) => (
    (item.organization_id || "org-local") === organizationId
    && (item.project_id || "project-local") === projectId
  ));
}

function sanitizeReviewWorkflowRecord(record = {}) {
  return {
    ...record,
    payload: redactPotentialSecret(record.payload || {}),
    review: redactPotentialSecret(record.review || {}),
    subject: redactPotentialSecret(record.subject || {}),
    safety: {
      ...(record.safety || {}),
      secret_values_included: false,
      raw_signature_stored: false,
      raw_identity_values_redacted: true,
      real_cloud_mutation_performed: false
    },
    signature: {
      ...(record.signature || {}),
      raw_signature_stored: false
    }
  };
}

function reviewWorkflowAuditEvent(record = {}, index = 0) {
  return {
    event_id: `rwr_evt_${sha256(`${record.record_id || "missing"}:${index}`).slice(0, 12)}`,
    source: record.source,
    ...tenantScopeRecordFields(record),
    event_type: "review_workflow_record_submitted",
    subject_id: record.record_id,
    payload: {
      schema_version: record.schema_version,
      record_id: record.record_id,
      record_type: record.record_type,
      status: record.status,
      accepted: record.accepted === true,
      payload_hash: record.payload_hash,
      review_hash: record.review_hash,
      raw_signature_stored: false
    },
    created_at: record.created_at || new Date().toISOString(),
    redacted: true
  };
}

function reviewWorkflowReceipt(record = {}) {
  return {
    schema_version: "a3.review_workflow_receipt.v1",
    source: record.source,
    ...tenantScopeRecordFields(record),
    record_id: record.record_id,
    record_type: record.record_type,
    status: record.status,
    accepted: record.accepted === true,
    automatic_unblock: record.automatic_unblock === true,
    run_id: record.run_id,
    release_version: record.release_version,
    environment: record.environment,
    payload_hash: record.payload_hash,
    review_hash: record.review_hash,
    signature: record.signature,
    durable_storage_ready: true,
    real_cloud_mutation_performed: false,
    secret_values_included: false
  };
}

function multimodalComparisonAuditEvent(receipt = {}, index = 0) {
  return {
    event_id: `mmr_evt_${sha256(`${receipt.payload_hash || "missing"}:${index}`).slice(0, 12)}`,
    source: receipt.source,
    ...tenantScopeRecordFields(receipt),
    event_type: "a2_multimodal_comparison_imported",
    subject_id: receipt.payload_hash,
    payload: {
      schema_version: receipt.schema_version,
      payload_hash: receipt.payload_hash,
      comparison_count: receipt.comparison_count,
      review_required_count: receipt.review_required_count,
      queue_receipt_count: receipt.queue_receipt_count,
      upstream_release_authority: false,
      candidate_binding_verified: false,
      release_decision_changed: false
    },
    created_at: receipt.imported_at,
    redacted: true
  };
}

function multimodalReviewAssignmentAuditEvent(event = {}, index = 0) {
  return {
    event_id: `mmra_evt_${sha256(`${event.event_id || "missing"}:${index}`).slice(0, 12)}`,
    source: event.source,
    ...tenantScopeRecordFields(event),
    event_type: `multimodal_review_assignment_${event.event_type || "changed"}`,
    subject_id: event.queue_id,
    actor_hash: event.actor_hash,
    payload: {
      schema_version: event.schema_version,
      assignment_event_id: event.event_id,
      assignment_event_hash: event.event_hash,
      queue_id: event.queue_id,
      event_type: event.event_type,
      version: event.version,
      assigned_reviewer_hash: event.assigned_reviewer_hash,
      lease_expires_at: event.lease_expires_at,
      reason_code: event.reason_code,
      release_authority: false,
      a2_decision_recomputed: false,
      raw_reviewer_identity_included: false
    },
    created_at: event.created_at,
    redacted: true
  };
}

function buildMultimodalQueueForSnapshot(snapshot = {}, assignmentEvents = [], options = {}) {
  const metadata = snapshot.a2MultimodalComparisonMeta || {};
  const queue = buildA3MultimodalReviewQueue(snapshot.a2MultimodalComparison || {}, {
    source: snapshot.source,
    tenantScope: snapshot.tenant_scope || tenantScopeRecordFields(snapshot).tenant_scope,
    sourceCommitAlias: metadata.source_commit_alias,
    ingestMode: metadata.ingest_mode,
    capabilityState: metadata.capability_state
  });
  const projection = buildA3MultimodalReviewAssignmentProjection(queue, assignmentEvents, options);
  return {
    ...projection,
    review_packet: buildA3MultimodalReviewAssignmentPacket(projection, {
      generatedAt: options.now || "queue-read"
    })
  };
}

function selectSnapshot(snapshots, source = "mock", options = {}) {
  const sourceKey = normalizeSourceKey(source || "mock");
  const exactSnapshot = snapshots.get(sourceKey);
  const sourceSnapshots = [...snapshots.values()].filter((snapshot) => (
    normalizeSourceKey(snapshot.source || "unknown") === sourceKey
  ));
  if (options.enforceScope === true) {
    const scopedSnapshot = sourceSnapshots.find((snapshot) => tenantScopeMatches(snapshot, options));
    if (!scopedSnapshot) {
      throw new A3StoreResourceNotFoundError();
    }
    return scopedSnapshot;
  }
  const snapshot = exactSnapshot || sourceSnapshots[0] || snapshots.values().next().value;
  if (!snapshot) {
    throw new Error("A3 store has no dashboard snapshots loaded");
  }
  return snapshot;
}

function findSnapshotForMutation(snapshots, source = "mock", options = {}) {
  const sourceKey = normalizeSourceKey(source || "mock");
  const candidates = [...snapshots.values()].filter((snapshot) => (
    normalizeSourceKey(snapshot.source || "unknown") === sourceKey
  ));
  if (options.enforceScope === true || hasExplicitTenantScope(options)) {
    return candidates.find((snapshot) => tenantScopeMatches(snapshot, options)) || null;
  }
  return snapshots.get(sourceKey) || candidates[0] || null;
}

function storeSnapshotByScope(snapshots, snapshot = {}) {
  const normalizedSource = normalizeSourceKey(snapshot.source || "mock");
  const existingEntry = [...snapshots.entries()].find(([, candidate]) => (
    normalizeSourceKey(candidate.source || "unknown") === normalizedSource
    && tenantScopeMatches(candidate, snapshot)
  ));
  if (existingEntry) {
    snapshots.set(existingEntry[0], snapshot);
    return existingEntry[0];
  }
  const storageKey = snapshots.has(normalizedSource)
    ? `${normalizedSource}::${snapshotScopeHash(snapshot)}`
    : normalizedSource;
  snapshots.set(storageKey, snapshot);
  return storageKey;
}

function snapshotScopeHash(snapshot = {}) {
  return sha256(stableJson(buildA3TenantScope(snapshot))).slice(0, 16);
}

function scopedIdempotencySource(source, options = {}, fallback = {}) {
  const scope = buildA3TenantScope(options, fallback);
  return `${normalizeSourceKey(source || "mock")}::${sha256(stableJson(scope)).slice(0, 16)}`;
}

function hasExplicitTenantScope(options = {}) {
  return [
    "organization_id", "organizationId",
    "tenant_id", "tenantId",
    "workspace_id", "workspaceId",
    "project_id", "projectId",
    "environment_id", "environmentId"
  ].some((field) => options[field] !== undefined && options[field] !== null && options[field] !== "");
}

function extractRunSummaries(snapshot) {
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  const caseCounts = cases.reduce((counts, item) => {
    counts[item.run_id] = counts[item.run_id] || { total: 0, failed: 0 };
    counts[item.run_id].total += 1;
    counts[item.run_id].failed += item.passed ? 0 : 1;
    return counts;
  }, {});

  const runRecords = extractRunRecords(snapshot.runFixture);
  if (!runRecords.length) {
    return Object.entries(caseCounts).map(([runId, counts]) => ({
      run_id: runId,
      source: snapshot.source,
      status: counts.failed ? "failed" : "passed",
      total_cases: counts.total,
      failed_cases: counts.failed
    }));
  }

  return runRecords.map((run) => {
    const counts = caseCounts[run.run_id] || { total: 0, failed: 0 };
    return {
      run_id: run.run_id,
      source: snapshot.source,
      dataset_id: run.dataset_id || "local-dataset",
      runner_id: run.runner_id || "a1-local-runner",
      status: run.status || (counts.failed ? "failed" : "passed"),
      total_cases: counts.total,
      failed_cases: counts.failed,
      trace_completeness: run.trace_completeness ?? null
    };
  });
}

function extractRunRecords(runFixture = {}) {
  if (Array.isArray(runFixture)) {
    return runFixture.flatMap(extractRunRecords);
  }
  if (Array.isArray(runFixture.runs)) {
    return runFixture.runs;
  }
  if (runFixture.run_id && Array.isArray(runFixture.cases)) {
    return [runFixture];
  }
  const cases = normalizeCases(runFixture, {});
  const runIds = [...new Set(cases.map((item) => item.run_id))];
  return runIds.map((runId) => ({
    run_id: runId,
    dataset_id: cases.find((item) => item.run_id === runId)?.dataset_id || "local-dataset",
    cases: cases.filter((item) => item.run_id === runId)
  }));
}

function summarizeCases(cases = []) {
  const total = cases.length;
  const failed = cases.filter((item) => !item.passed).length;
  return {
    total_cases: total,
    failed_cases: failed,
    passed_cases: total - failed,
    pass_rate: total ? Math.round(((total - failed) / total) * 1000) / 10 : 0
  };
}

function buildIngestReceipt(schemaVersion, snapshot, counts = {}) {
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  const idempotencyKeyPresent = Boolean(counts.idempotencyKey);
  return {
    schema_version: schemaVersion,
    source: snapshot.source,
    ...tenantScopeRecordFields(snapshot),
    source_label: snapshot.source_label,
    storage_mode: snapshot.storage?.mode || "memory",
    db_ready: snapshot.storage?.db_ready === true,
    imported_run_count: counts.imported_run_count || 0,
    imported_grade_count: counts.imported_grade_count || 0,
    payload_hash: counts.payloadHash || null,
    idempotency: {
      key_present: idempotencyKeyPresent,
      duplicate: false,
      status: idempotencyKeyPresent ? "recorded" : "not_provided"
    },
    dashboard_case_count: cases.length,
    summary: snapshot.summary,
    a1_a2_join_ready: cases.some((item) => (
      item.trace_ready
      || (item.judge_results || []).length > 0
      || item.grade
    ))
  };
}

function validateA1RunResult(runResult = {}) {
  const details = [];
  if (!runResult || typeof runResult !== "object" || Array.isArray(runResult)) {
    details.push({ field: "run_result", issue: "must be an object" });
  } else {
    const runRecords = extractRunRecords(runResult);
    const cases = normalizeCases(runResult, {});
    if (runRecords.length === 0) {
      details.push({ field: "run_result.runs", issue: "must contain at least one run" });
    }
    if (cases.length === 0) {
      details.push({ field: "run_result.cases", issue: "must contain at least one case" });
    }
    for (const [index, item] of cases.entries()) {
      if (!item.case_id) {
        details.push({ field: `run_result.cases[${index}].case_id`, issue: "is required" });
      }
    }
  }
  return {
    valid: details.length === 0,
    details
  };
}

function validateA2GradeResult(gradeResult = {}) {
  const details = [];
  if (!gradeResult || typeof gradeResult !== "object" || Array.isArray(gradeResult)) {
    details.push({ field: "grade_result", issue: "must be an object" });
  } else {
    const grades = extractGradeResults(gradeResult);
    if (grades.length === 0) {
      details.push({ field: "grade_result", issue: "must contain at least one grade result" });
    }
    for (const [index, grade] of grades.entries()) {
      if (!grade.case_id) {
        details.push({ field: `grade_result[${index}].case_id`, issue: "is required" });
      }
      if (!("passed" in grade) && !("score" in grade) && !Array.isArray(grade.judge_results)) {
        details.push({ field: `grade_result[${index}]`, issue: "must include passed, score, or judge_results" });
      }
    }
  }
  return {
    valid: details.length === 0,
    details
  };
}

function getIdempotentReplay(idempotencyReceipts, requestType, source, idempotencyKey, payloadHash) {
  if (!idempotencyKey) {
    return null;
  }
  const ledgerKey = idempotencyLedgerKey(requestType, source, idempotencyKey);
  const existing = idempotencyReceipts.get(ledgerKey);
  if (!existing) {
    return null;
  }
  if (existing.payload_hash !== payloadHash) {
    throw new A3StoreValidationError("Idempotency key was already used with a different payload.", [
      { field: "Idempotency-Key", issue: "conflicts with a previous payload hash for this source and request type" }
    ], {
      requestType,
      source,
      statusCode: 409,
      error: "idempotency_conflict"
    });
  }
  return {
    ...existing.receipt,
    idempotency: {
      ...existing.receipt.idempotency,
      duplicate: true,
      status: "duplicate_replay"
    }
  };
}

function rememberIdempotentReceipt(idempotencyReceipts, requestType, source, idempotencyKey, payloadHash, receipt) {
  if (!idempotencyKey) {
    return;
  }
  const ledgerKey = idempotencyLedgerKey(requestType, source, idempotencyKey);
  idempotencyReceipts.set(ledgerKey, {
    request_type: requestType,
    source,
    idempotency_key_hash: sha256(idempotencyKey).slice(0, 16),
    payload_hash: payloadHash,
    receipt
  });
}

function apiImportReceiptsFromLedger(idempotencyReceipts) {
  return [...idempotencyReceipts.values()]
    .filter((item) => ["a1_run_result_import", "a2_grade_result_import", "a2_multimodal_comparison_import"].includes(item.request_type))
    .map((item) => item.receipt);
}

function idempotencyLedgerKey(requestType, source, idempotencyKey) {
  return `${requestType}:${source}:${sha256(idempotencyKey).slice(0, 32)}`;
}

function reportLifecycleStatus(report = {}, now = new Date().toISOString()) {
  if (report.revoked_at || report.status === "revoked") {
    return "revoked";
  }
  if (report.status === "blocked") {
    return "blocked";
  }
  if (report.expires_at && report.expires_at <= now) {
    return "expired";
  }
  return report.status || "unknown";
}

function registerShareLink(shareLinks, report = {}, storageKey = reportStorageKey(report)) {
  const tokenHash = report.share_link?.token_hash;
  if (!tokenHash || !report.report_id) {
    return;
  }
  const existing = shareLinks.get(tokenHash) || {};
  const tenantScope = buildA3TenantScope(report);
  shareLinks.set(tokenHash, {
    ...existing,
    schema_version: "a3.report_share_link_index.v1",
    token_hash: tokenHash,
    token_hash_prefix: report.share_link.token_hash_prefix || tokenHash.slice(0, 12),
    report_id: report.report_id,
    report_storage_key: storageKey,
    source: normalizeSourceKey(report.source || "unknown"),
    tenant_scope: tenantScope,
    scope: report.share_link.scope || "private_link",
    created_at: report.share_link.created_at || report.created_at,
    expires_at: report.share_link.expires_at || report.expires_at || null,
    revoked_at: report.share_link.revoked_at || report.revoked_at || null,
    last_viewed_at: existing.last_viewed_at || report.share_link.last_viewed_at || null,
    last_event_id: existing.last_event_id || report.share_link.last_event_id || null
  });
}

function revokeShareLink(shareLinks, report, revokedAt) {
  const tokenHash = report.share_link?.token_hash;
  const link = tokenHash ? shareLinks.get(tokenHash) : null;
  if (link) {
    link.revoked_at = revokedAt;
  }
}

function sanitizeStoredReport(report = {}) {
  return {
    ...report,
    share_url_path: report.share_link?.token_hash ? "/r/[REDACTED_TOKEN]" : report.share_url_path,
    share_link: {
      ...(report.share_link || {}),
      raw_token_returned_once: false
    }
  };
}

function sanitizeReportForRead(report = {}) {
  return {
    ...report,
    share_link: safeShareLinkSummary(report.share_link)
  };
}

function safeShareLinkSummary(shareLink = {}) {
  if (!shareLink.token_hash) {
    return null;
  }
  return {
    schema_version: shareLink.schema_version || "a3.report_share_link.v1",
    token_hash_prefix: shareLink.token_hash_prefix || shareLink.token_hash.slice(0, 12),
    scope: shareLink.scope || "private_link",
    created_at: shareLink.created_at || null,
    expires_at: shareLink.expires_at || null,
    revoked_at: shareLink.revoked_at || null,
    raw_token_returned_once: false
  };
}

function shareLinkLifecycleStatus(report = {}, link = {}, now = new Date().toISOString()) {
  if (link.revoked_at || report.revoked_at || report.status === "revoked") {
    return "revoked";
  }
  if (report.status === "blocked" || report.redaction?.blocked === true) {
    return "redaction_blocked";
  }
  const expiresAt = link.expires_at || report.expires_at;
  if (expiresAt && expiresAt <= now) {
    return "expired";
  }
  return report.status || "unknown";
}

function recordReportAccessEvent(auditEvents, options = {}) {
  const viewedAt = options.viewedAt || new Date().toISOString();
  const event = {
    event_id: `rsv_${sha256(`${options.reportId || "missing"}:${options.tokenHash || "missing"}:${options.accessResult}:${viewedAt}:${auditEvents.length}`).slice(0, 12)}`,
    ...(options.source ? { source: normalizeSourceKey(options.source) } : {}),
    ...(options.tenantScope ? tenantScopeRecordFields(options.tenantScope) : {}),
    report_id: options.reportId || null,
    event_type: "report_share_link_viewed",
    access_result: options.accessResult || "unknown",
    viewed_at: viewedAt,
    viewer: options.viewer || "share_link",
    token_hash_prefix: options.tokenHash ? options.tokenHash.slice(0, 12) : null,
    redacted: true
  };
  auditEvents.push(event);
  return event;
}

function deniedShareReport(status, report = {}, options = {}) {
  return {
    schema_version: "a3.shareable_report_denied.v1",
    report_id: report?.report_id || null,
    title: report?.title || "A3 Shareable Report",
    status,
    access_result: status,
    viewed_at: options.viewedAt || null,
    share_link: {
      token_hash_prefix: options.tokenHash ? options.tokenHash.slice(0, 12) : report?.share_link?.token_hash_prefix || null,
      expires_at: report?.share_link?.expires_at || report?.expires_at || null,
      revoked_at: report?.share_link?.revoked_at || report?.revoked_at || null
    },
    sealed_evidence: report?.sealed_evidence ? {
      hash_algorithm: report.sealed_evidence.hash_algorithm || "sha256",
      payload_hash_present: Boolean(report.sealed_evidence.payload_hash),
      secret_free: report.sealed_evidence.secret_free === true
    } : {},
    payload: null
  };
}

function mergeGradeFixtures(existing = {}, incoming = {}) {
  const existingGrades = extractGradeResults(existing);
  const incomingGrades = extractGradeResults(incoming);
  const byCaseId = new Map();
  for (const grade of [...existingGrades, ...incomingGrades]) {
    byCaseId.set(grade.case_id || `grade-${byCaseId.size + 1}`, grade);
  }
  return {
    schema_version: incoming.schema_version || existing.schema_version || "a3.api_ingest_grade_results.v1",
    grade_results: [...byCaseId.values()]
  };
}

function extractGradeResults(gradeFixture = {}) {
  if (Array.isArray(gradeFixture)) {
    return gradeFixture.flatMap(extractGradeResults);
  }
  if (Array.isArray(gradeFixture.grade_results)) {
    return gradeFixture.grade_results;
  }
  if (gradeFixture.grade_result && typeof gradeFixture.grade_result === "object") {
    return [gradeFixture.grade_result];
  }
  if (gradeFixture.case_id && (
    Array.isArray(gradeFixture.judge_results)
    || "passed" in gradeFixture
    || "score" in gradeFixture
    || "primary_failure_class" in gradeFixture
  )) {
    return [gradeFixture];
  }
  return [];
}

function countGradeResults(gradeFixture = {}) {
  return extractGradeResults(gradeFixture).length;
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

async function readJson(root, relativePath) {
  if (!relativePath) {
    return {};
  }
  return JSON.parse(await readFile(fileURLToPath(new URL(relativePath, root)), "utf8"));
}

async function readOptionalJson(root, relativePath) {
  if (!relativePath) {
    return {};
  }
  try {
    return await readJson(root, relativePath);
  } catch (error) {
    if (error.code === "ENOENT") {
      return {};
    }
    throw error;
  }
}

async function readReleaseEvidenceFixtures(root) {
  const entries = await Promise.all(Object.entries(A3_RELEASE_EVIDENCE_FIXTURES)
    .map(async ([key, relativePath]) => [key, await readOptionalJson(root, relativePath)]));
  return Object.fromEntries(entries);
}

function normalizeSourceKey(source) {
  return source === "api-mock" ? "mock" : source;
}
