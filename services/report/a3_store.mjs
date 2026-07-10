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

export const A3_SOURCE_FIXTURES = {
  mock: {
    label: "A1/A2 Mock",
    runFixture: "fixtures/a3/mock_run_results.json",
    gradeFixture: "fixtures/a3/mock_grade_results.json"
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
    frontendSummary: "fixtures/a3/p3/ashr_frontend_relogin_top_level_summary.redacted.json"
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
  }
};

export const A3_DB_CONTRACT = {
  schema_version: "a3.saas_db_contract.v1",
  recommended_primary_db: "postgres",
  mysql_compatible: true,
  local_dev_store: "memory_or_file",
  tenant_columns_required: ["organization_id", "tenant_id", "workspace_id", "project_id"],
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
    "release_evidence_summaries",
    "release_evidence_snapshots",
    "release_evidence_diffs",
    "release_evidence_readbacks",
    "github_publish_receipts",
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
    "GET /api/a3/runs",
    "GET /api/a3/runs/:runId",
    "GET /api/a3/cases/:caseId",
    "POST /api/a3/import/a1-run-result",
    "POST /api/a3/import/a2-grade-result",
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
    "All reads are project scoped before real multi-tenant auth is enabled.",
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
    gradeFixture = config.gradeFixture ? await readJson(root, config.gradeFixture) : {};
  }

  return normalizeSnapshot({
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
    releaseEvidence: await readReleaseEvidenceFixtures(root),
    storage: {
      mode: "fixture_file",
      db_ready: true,
      source_paths: Object.fromEntries(
        Object.entries(config).filter(([, value]) => typeof value === "string" && value.includes("/"))
      )
    }
  });
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
  const releaseEvidenceReadbacks = [];
  const githubPublishReceipts = [];

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
    snapshots.set(snapshot.source, snapshot);
  }
  for (const report of seed.reports || []) {
    reports.set(report.report_id, report);
    registerShareLink(shareLinks, report);
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
  for (const readback of seed.releaseEvidenceReadbacks || []) {
    releaseEvidenceReadbacks.push(sanitizeReleaseEvidenceReadback(readback));
  }
  for (const receipt of seed.githubPublishReceipts || []) {
    githubPublishReceipts.push(sanitizeGitHubPublishReceipt(receipt));
  }

  return {
    schema_version: A3_STORE_SCHEMA_VERSION,
    db_contract: A3_DB_CONTRACT,
    storage_mode: seed.storageMode || "memory",

    async upsertSnapshot(source, snapshot) {
      const normalized = normalizeSnapshot({ source, ...snapshot });
      snapshots.set(normalized.source, normalized);
      return normalized;
    },

    async getDashboardSnapshot(source = "mock") {
      const snapshot = selectSnapshot(snapshots, source);
      return buildDashboardPayload(snapshot, this.storage_mode, {
        reports: filterReportsForSnapshot([...reports.values()], snapshot),
        auditEvents,
        eventOutbox,
        adminActionRequests,
        reviewWorkflowRecords,
        releaseEvidenceReadbacks,
        githubPublishReceipts,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts)
      });
    },

    async listRuns(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      return extractRunSummaries(snapshot);
    },

    async getRun(runId, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const replay = getIdempotentReplay(idempotencyReceipts, "a1_run_result_import", source, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const existing = snapshots.get(source);
      const normalized = normalizeSnapshot({
        ...(existing || {}),
        source,
        source_label: options.sourceLabel || existing?.source_label || "API Ingest",
        organizationId: options.organizationId || existing?.organizationId || runResult?.organization_id,
        projectId: options.projectId || existing?.projectId || runResult?.project_id,
        runFixture: runResult || {},
        gradeFixture: existing?.gradeFixture || {},
        storage: {
          mode: this.storage_mode || "memory",
          db_ready: true,
          ingest_source: "a1_run_result_api"
        }
      });
      snapshots.set(source, normalized);
      const receipt = buildIngestReceipt("a3.a1_run_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture),
        idempotencyKey: options.idempotencyKey,
        payloadHash
      });
      rememberIdempotentReceipt(idempotencyReceipts, "a1_run_result_import", source, options.idempotencyKey, payloadHash, receipt);
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
      const replay = getIdempotentReplay(idempotencyReceipts, "a2_grade_result_import", source, options.idempotencyKey, payloadHash);
      if (replay) {
        return replay;
      }
      const existing = snapshots.get(source);
      const mergedGradeFixture = mergeGradeFixtures(existing?.gradeFixture, gradeResult);
      const normalized = normalizeSnapshot({
        ...(existing || {}),
        source,
        source_label: options.sourceLabel || existing?.source_label || "API Ingest",
        organizationId: options.organizationId || existing?.organizationId || gradeResult?.organization_id,
        projectId: options.projectId || existing?.projectId || gradeResult?.project_id,
        runFixture: existing?.runFixture || {},
        gradeFixture: mergedGradeFixture,
        storage: {
          mode: this.storage_mode || "memory",
          db_ready: true,
          ingest_source: "a2_grade_result_api"
        }
      });
      snapshots.set(source, normalized);
      const receipt = buildIngestReceipt("a3.a2_grade_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture),
        idempotencyKey: options.idempotencyKey,
        payloadHash
      });
      rememberIdempotentReceipt(idempotencyReceipts, "a2_grade_result_import", source, options.idempotencyKey, payloadHash, receipt);
      return receipt;
    },

    async getSaasAdminConsole(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      return attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), adminActionRequests, {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
    },

    async getEnterpriseReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const adminConsole = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), adminActionRequests, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return buildA3UsageLedger(snapshot, {
        reports: filterReportsForSnapshot([...reports.values()], scopedSnapshot),
        auditEvents,
        releaseEvidenceReadbacks,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        periodStart: options.periodStart,
        periodEnd: options.periodEnd
      });
    },

    async getBillingReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const usageLedger = await this.getUsageLedger(options);
      const adminConsole = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId
      }), adminActionRequests, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      return buildA3BillingMigrationReadiness({
        source: snapshot.source,
        organizationId: scopedSnapshot.organizationId,
        projectId: scopedSnapshot.projectId,
        environmentId: scopedSnapshot.environmentId
      });
    },

    async getLiveWorkflowReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, githubPublishReceipts, {
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
      }), adminActionRequests, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, githubPublishReceipts, {
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
      }), adminActionRequests, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const releaseEvidenceInput = mergeReleaseEvidenceWithGitHubReceipts(snapshot.releaseEvidence, githubPublishReceipts, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const snapshot = selectSnapshot(snapshots, options.source);
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

    async planSaasAdminAction(action, options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
        source: snapshot.source,
        request_hash: requestHash,
        requested_by_hash: actorHash,
        reason: options.reason || request.reason,
        target: sanitizeAdminActionTarget(options.target)
      });
      adminActionRequests.push(storedRequest);
      auditEvents.push({
        event_id: `aar_evt_${sha256(`${storedRequest.request_id}:${auditEvents.length}`).slice(0, 12)}`,
        organization_id: storedRequest.organization_id,
        project_id: storedRequest.project_id,
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
        request_id: storedRequest.request_id,
        action: storedRequest.action,
        area: storedRequest.area,
        mode: storedRequest.mode,
        status: storedRequest.status,
        organization_id: storedRequest.organization_id,
        project_id: storedRequest.project_id,
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const organizationId = options.organizationId || snapshot.organizationId;
      const projectId = options.projectId || snapshot.projectId;
      const requests = filterAdminActionRequests(adminActionRequests, { organizationId, projectId });
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const idempotencyPayloadHash = sha256(stableJson({
        record_type: "approval",
        source: snapshot.source,
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        approval: redactPotentialSecret(approval),
        waiver: redactPotentialSecret(options.waiver || {})
      }));
      const replay = getIdempotentReplay(idempotencyReceipts, "review_approval_submit", snapshot.source, options.idempotencyKey, idempotencyPayloadHash);
      if (replay) {
        return replay;
      }
      const waiverRecord = options.waiver
        ? { payload: options.waiver }
        : [...reviewWorkflowRecords].reverse().find((item) => item.record_type === "waiver" && item.subject?.waiver_id === approval?.waiver_id);
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
        waiver: options.waiver || waiverRecord?.payload || {}
        }),
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const snapshot = selectSnapshot(snapshots, options.source);
      return buildReviewWorkflowIndex(filterReviewWorkflowRecords(reviewWorkflowRecords, {
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        durableStorageReady: true
      });
    },

    async publishGitHubCheckRun(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (!snapshotMatchesTenantScope(snapshot, options)) {
        return null;
      }
      const gatePayload = buildGitHubPublishGatePayload(snapshot, options);
      const dryRun = options.dryRun !== false;
      const payloadHash = sha256(stableJson({
        kind: "github_check",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        repo: options.repo,
        head_sha: options.headSha,
        details_url: options.detailsUrl,
        check_run_id: options.checkRunId || null,
        dry_run: dryRun,
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
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        actor_hash: options.actor ? sha256(String(options.actor)).slice(0, 16) : options.actorHash || "actor_[REDACTED_HASH]",
        published_at: options.publishedAt || new Date().toISOString(),
        payload_hash: payloadHash
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (!snapshotMatchesTenantScope(snapshot, options)) {
        return null;
      }
      const gatePayload = buildGitHubPublishGatePayload(snapshot, options);
      const dryRun = options.dryRun !== false;
      const payloadHash = sha256(stableJson({
        kind: "pr_comment",
        source: snapshot.source,
        release_id: canonicalReleaseId,
        repo: options.repo,
        pull_number: options.pullNumber,
        dry_run: dryRun,
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
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
        actor_hash: options.actor ? sha256(String(options.actor)).slice(0, 16) : options.actorHash || "actor_[REDACTED_HASH]",
        published_at: options.publishedAt || new Date().toISOString(),
        payload_hash: payloadHash
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
        organization_id: options.organizationId || snapshot.organizationId,
        project_id: options.projectId || snapshot.projectId,
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
        tenant_scope: {
          organization_id: storedReadback.organization_id,
          project_id: storedReadback.project_id
        },
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
      const snapshot = selectSnapshot(snapshots, options.source);
      const canonicalReleaseId = releaseEvidenceReleaseId(snapshot);
      if (
        !releaseEvidenceIdMatches(releaseId, canonicalReleaseId, snapshot)
        || !snapshotMatchesTenantScope(snapshot, options)
      ) {
        return null;
      }
      const readbacks = filterReleaseEvidenceReadbacks(releaseEvidenceReadbacks, {
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
        reports: [...reports.values()],
        auditEvents,
        releaseEvidenceReadbacks,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
        version: options.version || options.schemaVersion
      });
    },

    async getReleaseEvidenceDiff(releaseId = "current", options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
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
        reports: [...reports.values()],
        auditEvents,
        releaseEvidenceReadbacks,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
        version: "1"
      }).release_evidence_summary;
      const after = buildReleaseEvidenceApiResponse(snapshot, {
        releaseId: canonicalReleaseId,
        storageMode: this.storage_mode,
        reports: [...reports.values()],
        auditEvents,
        releaseEvidenceReadbacks,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
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
      const snapshot = selectSnapshot(snapshots, options.source);
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
      const report = buildShareableReportPayload(snapshot, {
        source: snapshot.source,
        title: options.title,
        visibility: options.visibility,
        createdBy: options.createdBy,
        createdAt: options.createdAt,
        expiresAt: options.expiresAt,
        shareToken: options.shareToken,
        organizationId: options.organizationId,
        projectId: options.projectId
      });
      reports.set(report.report_id, sanitizeStoredReport(report));
      registerShareLink(shareLinks, report);
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
      const report = reports.get(reportId);
      if (!report || !reportMatchesRequestScope(report, snapshots, options)) {
        return null;
      }
      return report ? sanitizeReportForRead(report) : null;
    },

    async getReportManifest(reportId, options = {}) {
      const report = reports.get(reportId);
      if (!report || !reportMatchesRequestScope(report, snapshots, options)) {
        return null;
      }
      const snapshot = selectSnapshot(snapshots, options.source || report.source);
      const reportScope = reportTenantScope(report);
      const scopedSnapshot = snapshotWithScope(snapshot, {
        organizationId: options.organizationId || reportScope.organizationId,
        projectId: options.projectId || reportScope.projectId
      });
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      return buildReportCenterManifest(report, {
        usageLedger: buildA3UsageLedger(snapshot, {
          reports: scopedReports,
          auditEvents,
          importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
          organizationId: scopedSnapshot.organizationId,
          projectId: scopedSnapshot.projectId
        }),
        migrationPlan: buildA3SqlMigrationPlan()
      });
    },

    async getReportCenter(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
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
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts)
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
        }), adminActionRequests, {
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId
        })
      });
    },

    async getArtifactRegistry(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
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
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts)
      });
      const saasAdmin = attachAdminActionRequests(buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      }), adminActionRequests, {
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
        releaseEvidenceReadbacks: filterReleaseEvidenceReadbacks(releaseEvidenceReadbacks, {
          organizationId: scopedSnapshot.organizationId,
          projectId: scopedSnapshot.projectId
        })
      });
    },

    async getProductConsole(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const scopedSnapshot = snapshotWithScope(snapshot, options);
      const scopedReports = filterReportsForSnapshot([...reports.values()], scopedSnapshot);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: scopedReports,
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts),
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
        auditEvents,
        importReceipts: apiImportReceiptsFromLedger(idempotencyReceipts)
      });
    },

    async getReportForView(reportId, options = {}) {
      const report = reports.get(reportId);
      if (!report || !reportMatchesRequestScope(report, snapshots, options)) {
        return null;
      }
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
          organization_id: reportScope.organizationId,
          project_id: reportScope.projectId,
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

      const report = reports.get(link.report_id);
      if (!report) {
        recordReportAccessEvent(auditEvents, {
          reportId: link.report_id,
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

      const status = shareLinkLifecycleStatus(report, link, now);
      if (status === "shareable") {
        const event = recordReportAccessEvent(auditEvents, {
          reportId: report.report_id,
          tokenHash,
          accessResult: "allowed",
          viewedAt: now,
          viewer: options.viewer || "share_link"
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
        viewer: options.viewer || "share_link"
      });
      return deniedShareReport(status, report, {
        tokenHash,
        viewedAt: now
      });
    },

    async revokeReport(reportId, options = {}) {
      const report = reports.get(reportId);
      if (!report || !reportMatchesRequestScope(report, snapshots, options)) {
        return null;
      }
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
      reports.set(reportId, revoked);
      revokeShareLink(shareLinks, reportId, revokedAt);
      auditEvents.push({
        event_id: `rrv_${sha256(`${reportId}:${revokedAt}:${auditEvents.length}`).slice(0, 12)}`,
        report_id: reportId,
        organization_id: reportScope.organizationId,
        project_id: reportScope.projectId,
        event_type: "report_revoke",
        revoked_at: revokedAt,
        revoked_by: revoked.revoked_by,
        reason: revoked.revocation_reason,
        redacted: true
      });
      const receipt = {
        schema_version: "a3.report_revoke_receipt.v1",
        report_id: reportId,
        organization_id: reportScope.organizationId,
        project_id: reportScope.projectId,
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

    async listEventOutbox(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
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
        releaseEvidenceReadbacks
      };
    }
  };
}

export async function createFixtureBackedA3Store(options = {}) {
  const sources = {};
  for (const source of options.sources || Object.keys(A3_SOURCE_FIXTURES)) {
    sources[source] = await loadA3SourceSnapshot(source, options);
  }
  return createMemoryA3Store({
    sources,
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
    releaseEvidence: snapshot.releaseEvidence || snapshot.release_evidence || {},
    summary: buildDashboardSummary(runFixture, gradeFixture),
    case_count: cases.length,
    storage: snapshot.storage || {
      mode: "memory",
      db_ready: true
    }
  };
}

function buildDashboardPayload(snapshot, storageMode, options = {}) {
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  const releaseId = releaseEvidenceReleaseId(snapshot);
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
  return {
    schema_version: "a3.api_dashboard_payload.v1",
    source: snapshot.source,
    source_label: snapshot.source_label,
    storage: {
      ...snapshot.storage,
      mode: storageMode || snapshot.storage?.mode || "memory",
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
    peer_branch_calibration: summarizeA3PeerBranchCalibration(snapshot.peerBranchCalibration),
    release_evidence: releaseEvidenceForDashboard,
    release_evidence_summary: releaseEvidenceForDashboard,
    release_evidence_readbacks: releaseEvidenceReadbackHistory,
    github_publish_receipts: githubPublishReceiptDashboard,
    github_publish_evidence: githubPublishReceiptDashboard,
    event_outbox: eventOutboxDashboard,
    source_artifacts: sourceArtifacts,
    billing_readiness: billingReadiness,
    billing_migration_readiness: billingMigrationReadiness,
    live_workflow_readiness: liveWorkflowReadiness,
    live_ops_control_plane: liveOpsControlPlane,
    notification_control_plane: notificationControlPlane,
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
      notificationControlPlane
    }),
    commercial_api_contract: buildA3CommercialApiContract({
      source: "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
      organizationId: snapshot.organizationId,
      tenantId: snapshot.tenantId,
      workspaceId: snapshot.workspaceId,
      projectId: snapshot.projectId
    }),
    review_workflow: reviewWorkflow,
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
      db_ready: true,
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
  const reportScope = reportTenantScope(report);
  return reportScope.organizationId === (snapshot.organizationId || "org-local")
    && reportScope.projectId === (snapshot.projectId || "project-local");
}

function filterReportsForSnapshot(reports = [], snapshot = {}) {
  return (Array.isArray(reports) ? reports : []).filter((report) => reportMatchesSnapshotScope(report, snapshot));
}

function reportMatchesRequestScope(report = {}, snapshots = new Map(), options = {}) {
  const requestScope = resolveReportRequestScope(report, snapshots, options);
  if (requestScope.source && normalizeSourceKey(report.source || "unknown") !== requestScope.source) {
    return false;
  }
  const reportScope = reportTenantScope(report);
  if (requestScope.organizationId && requestScope.organizationId !== reportScope.organizationId) {
    return false;
  }
  if (requestScope.projectId && requestScope.projectId !== reportScope.projectId) {
    return false;
  }
  return true;
}

function resolveReportRequestScope(report = {}, snapshots = new Map(), options = {}) {
  const source = options.source ? normalizeSourceKey(options.source) : undefined;
  const snapshot = source ? snapshots.get(source) : null;
  return {
    source,
    organizationId: options.organizationId || snapshot?.organizationId,
    projectId: options.projectId || snapshot?.projectId
  };
}

function reportTenantScope(report = {}) {
  return {
    organizationId: report.tenant_scope?.organization_id || report.organization_id || "org-local",
    projectId: report.tenant_scope?.project_id || report.project_id || "project-local"
  };
}

function snapshotWithScope(snapshot = {}, options = {}) {
  const fields = tenantScopeToSnapshotFields(buildA3TenantScope(options, snapshot));
  return {
    ...snapshot,
    ...fields,
    tenant_scope: buildA3TenantScope(fields)
  };
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
    project_id: sanitized.project_id || "project-local",
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
    organization_id: receipt.organization_id || "org-local",
    project_id: receipt.project_id || "project-local",
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
    project_id: sanitizedPayload.project_id || "project-local",
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
    organization_id: readback.organization_id || "org-local",
    project_id: readback.project_id || "project-local",
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
    project_id: request.project_id || "project-local",
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
    organization_id: record.organization_id || "org-local",
    project_id: record.project_id || "project-local",
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
    record_id: record.record_id,
    record_type: record.record_type,
    status: record.status,
    accepted: record.accepted === true,
    automatic_unblock: record.automatic_unblock === true,
    organization_id: record.organization_id,
    project_id: record.project_id,
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

function selectSnapshot(snapshots, source = "mock") {
  const sourceKey = normalizeSourceKey(source || "mock");
  const snapshot = snapshots.get(sourceKey) || snapshots.values().next().value;
  if (!snapshot) {
    throw new Error("A3 store has no dashboard snapshots loaded");
  }
  return snapshot;
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
    source_label: snapshot.source_label,
    storage_mode: snapshot.storage?.mode || "memory",
    db_ready: true,
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
    .filter((item) => ["a1_run_result_import", "a2_grade_result_import"].includes(item.request_type))
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

function registerShareLink(shareLinks, report = {}) {
  const tokenHash = report.share_link?.token_hash;
  if (!tokenHash || !report.report_id) {
    return;
  }
  const existing = shareLinks.get(tokenHash) || {};
  shareLinks.set(tokenHash, {
    ...existing,
    schema_version: "a3.report_share_link_index.v1",
    token_hash: tokenHash,
    token_hash_prefix: report.share_link.token_hash_prefix || tokenHash.slice(0, 12),
    report_id: report.report_id,
    scope: report.share_link.scope || "private_link",
    created_at: report.share_link.created_at || report.created_at,
    expires_at: report.share_link.expires_at || report.expires_at || null,
    revoked_at: report.share_link.revoked_at || report.revoked_at || null,
    last_viewed_at: existing.last_viewed_at || report.share_link.last_viewed_at || null,
    last_event_id: existing.last_event_id || report.share_link.last_event_id || null
  });
}

function revokeShareLink(shareLinks, reportId, revokedAt) {
  for (const link of shareLinks.values()) {
    if (link.report_id === reportId) {
      link.revoked_at = revokedAt;
    }
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
