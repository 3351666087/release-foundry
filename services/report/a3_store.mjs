import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  buildDashboardSummary,
  normalizeCases
} from "./report_builder.mjs";
import { mapAshrSampleToA3Fixtures } from "./p3_ashr_mapper.mjs";
import { buildShareableReportPayload } from "./a3_shareable_report.mjs";
import {
  buildSaasAdminConsole,
  planSaasAdminAction
} from "./a3_saas_admin.mjs";
import { buildEnterpriseReadinessReport } from "./a3_enterprise_readiness.mjs";
import { buildReportCenterIndex } from "./a3_report_center.mjs";
import { buildReportCenterManifest } from "./a3_report_center_manifest.mjs";
import { buildA3SqlMigrationPlan } from "./a3_sql_migrations.mjs";
import { buildA3UsageLedger } from "./a3_usage_ledger.mjs";
import { buildA3ProductConsole } from "./a3_product_console.mjs";
import { buildA3ArtifactRegistry } from "./a3_artifact_registry.mjs";

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
  tenant_columns_required: ["organization_id", "project_id"],
  tables: [
    "organizations",
    "users",
    "team_members",
    "roles",
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
    "idempotency_keys",
    "api_import_receipts",
    "audit_events",
    "usage_ledger"
  ],
  api_surfaces: [
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
    "GET /api/a3/product/console",
    "GET /api/a3/enterprise/readiness",
    "GET /api/a3/db-migrations",
    "GET /api/a3/usage/ledger",
    "GET /api/a3/reports/center",
    "GET /api/a3/reports/:reportId/manifest",
    "GET /api/a3/artifacts/registry"
  ],
  guardrails: [
    "All reads are project scoped before real multi-tenant auth is enabled.",
    "Shareable reports must pass the export redaction firewall.",
    "Secrets, cookies, tokens, emails, raw signed URLs, and local paths are never persisted in public report payloads.",
    "A1 runner payloads and A2 judge payloads are normalized at the A3 boundary without changing their source semantics."
  ]
};

const REPO_ROOT = new URL("../../", import.meta.url);

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
        reports: [...reports.values()],
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt)
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
      return buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
    },

    async getEnterpriseReadiness(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const adminConsole = buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
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
      return buildA3UsageLedger(snapshot, {
        reports: [...reports.values()],
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt),
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        periodStart: options.periodStart,
        periodEnd: options.periodEnd
      });
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

    async createShareableReport(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
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
      return report;
    },

    async getReport(reportId) {
      const report = reports.get(reportId);
      return report ? sanitizeReportForRead(report) : null;
    },

    async getReportManifest(reportId, options = {}) {
      const report = reports.get(reportId);
      if (!report) {
        return null;
      }
      const snapshot = selectSnapshot(snapshots, options.source || report.source);
      return buildReportCenterManifest(report, {
        usageLedger: buildA3UsageLedger(snapshot, {
          reports: [...reports.values()],
          auditEvents,
          importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt),
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId
        }),
        migrationPlan: buildA3SqlMigrationPlan()
      });
    },

    async getReportCenter(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: [...reports.values()],
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt),
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      const migrationPlan = buildA3SqlMigrationPlan();
      const baseReportCenter = buildReportCenterIndex([...reports.values()], {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        migrationPlan
      });
      const productConsole = buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        reportCenter: baseReportCenter,
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt)
      });
      return buildReportCenterIndex([...reports.values()], {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        migrationPlan,
        productConsole,
        saasAdmin: buildSaasAdminConsole(snapshot, {
          source: snapshot.source,
          organizationId: options.organizationId || snapshot.organizationId,
          projectId: options.projectId || snapshot.projectId
        })
      });
    },

    async getArtifactRegistry(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: [...reports.values()],
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt),
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      const migrationPlan = buildA3SqlMigrationPlan();
      const reportCenter = buildReportCenterIndex([...reports.values()], {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        migrationPlan
      });
      const productConsole = buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        reportCenter,
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt)
      });
      const saasAdmin = buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      return buildA3ArtifactRegistry({
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        reportCenter,
        usageLedger,
        migrationPlan,
        productConsole,
        saasAdmin
      });
    },

    async getProductConsole(options = {}) {
      const snapshot = selectSnapshot(snapshots, options.source);
      const usageLedger = buildA3UsageLedger(snapshot, {
        reports: [...reports.values()],
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt),
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId
      });
      const reportCenter = buildReportCenterIndex([...reports.values()], {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        migrationPlan: buildA3SqlMigrationPlan()
      });
      return buildA3ProductConsole(snapshot, {
        source: snapshot.source,
        organizationId: options.organizationId || snapshot.organizationId,
        projectId: options.projectId || snapshot.projectId,
        usageLedger,
        reportCenter,
        auditEvents,
        importReceipts: [...idempotencyReceipts.values()].map((item) => item.receipt)
      });
    },

    async getReportForView(reportId, options = {}) {
      const report = reports.get(reportId);
      if (!report) {
        return null;
      }
      const now = options.viewedAt || new Date().toISOString();
      const status = reportLifecycleStatus(report, now);
      if (status === "shareable") {
        const event = {
          event_id: `rve_${sha256(`${reportId}:${now}:${auditEvents.length}`).slice(0, 12)}`,
          report_id: reportId,
          event_type: "report_view",
          viewed_at: now,
          viewer: options.viewer || "anonymous",
          source: report.source,
          redacted: true
        };
        auditEvents.push(event);
        report.view_audit = {
          ...(report.view_audit || {}),
          view_count: (report.view_audit?.view_count || 0) + 1,
          last_viewed_at: now,
          last_event_id: event.event_id
        };
      }
      return {
        ...report,
        status
      };
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
        report.view_audit = {
          ...(report.view_audit || {}),
          view_count: (report.view_audit?.view_count || 0) + 1,
          last_viewed_at: now,
          last_event_id: event.event_id
        };
        link.last_viewed_at = now;
        link.last_event_id = event.event_id;
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
      if (!report) {
        return null;
      }
      const revokedAt = options.revokedAt || new Date().toISOString();
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
        event_type: "report_revoke",
        revoked_at: revokedAt,
        revoked_by: revoked.revoked_by,
        reason: revoked.revocation_reason,
        redacted: true
      });
      return {
        schema_version: "a3.report_revoke_receipt.v1",
        report_id: reportId,
        status: "revoked",
        revoked_at: revokedAt,
        revoked_by: revoked.revoked_by,
        reason: revoked.revocation_reason
      };
    },

    async listReports() {
      return [...reports.values()].map((report) => ({
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
        auditEvents
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
  return {
    schema_version: "a3.dashboard_snapshot.v1",
    source,
    source_label: snapshot.source_label || A3_SOURCE_FIXTURES[source]?.label || source,
    organizationId: snapshot.organizationId || "org-local",
    projectId: snapshot.projectId || "project-local",
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
  const usageLedger = buildA3UsageLedger(snapshot, {
    reports: options.reports || [],
    auditEvents: options.auditEvents || [],
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
    saas_admin_console: buildSaasAdminConsole(snapshot, {
      source: snapshot.source,
      organizationId: snapshot.organizationId,
      projectId: snapshot.projectId
    }),
    enterprise_readiness: buildEnterpriseReadinessReport({
      runFixture: snapshot.runFixture,
      gradeFixture: snapshot.gradeFixture,
      adminConsole: buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: snapshot.organizationId,
        projectId: snapshot.projectId
      }),
      dbContract: A3_DB_CONTRACT
    }),
    usage_ledger: usageLedger,
    report_center: reportCenter,
    artifact_registry: buildA3ArtifactRegistry({
      source: snapshot.source,
      organizationId: snapshot.organizationId,
      projectId: snapshot.projectId,
      reportCenter,
      usageLedger,
      migrationPlan,
      productConsole,
      saasAdmin: buildSaasAdminConsole(snapshot, {
        source: snapshot.source,
        organizationId: snapshot.organizationId,
        projectId: snapshot.projectId
      })
    }),
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

function normalizeSourceKey(source) {
  return source === "api-mock" ? "mock" : source;
}
