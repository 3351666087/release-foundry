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

export const A3_STORE_SCHEMA_VERSION = "a3.store.v1";

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
    "trust_reports",
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
    "GET /api/a3/admin/console",
    "POST /api/a3/admin/actions/plan",
    "GET /api/a3/enterprise/readiness"
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
      return buildDashboardPayload(snapshot, this.storage_mode);
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
      return buildIngestReceipt("a3.a1_run_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture)
      });
    },

    async importA2GradeResult(gradeResult, options = {}) {
      const source = normalizeSourceKey(options.source || gradeResult?.source || "api-ingest");
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
      return buildIngestReceipt("a3.a2_grade_result_ingest.v1", normalized, {
        imported_run_count: extractRunRecords(normalized.runFixture).length,
        imported_grade_count: countGradeResults(normalized.gradeFixture)
      });
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
        organizationId: options.organizationId,
        projectId: options.projectId
      });
      reports.set(report.report_id, report);
      return report;
    },

    async getReport(reportId) {
      return reports.get(reportId) || null;
    },

    async listReports() {
      return [...reports.values()].map((report) => ({
        report_id: report.report_id,
        title: report.title,
        status: report.status,
        source: report.source,
        share_url_path: report.share_url_path,
        created_at: report.created_at
      }));
    },

    exportState() {
      return {
        schema_version: A3_STORE_SCHEMA_VERSION,
        storage_mode: this.storage_mode,
        sources: Object.fromEntries(snapshots.entries()),
        reports: [...reports.values()]
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

function buildDashboardPayload(snapshot, storageMode) {
  const cases = normalizeCases(snapshot.runFixture, snapshot.gradeFixture);
  return {
    schema_version: "a3.api_dashboard_payload.v1",
    source: snapshot.source,
    source_label: snapshot.source_label,
    storage: {
      ...snapshot.storage,
      mode: storageMode || snapshot.storage?.mode || "memory",
      db_contract: A3_DB_CONTRACT
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
  return {
    schema_version: schemaVersion,
    source: snapshot.source,
    source_label: snapshot.source_label,
    storage_mode: snapshot.storage?.mode || "memory",
    db_ready: true,
    imported_run_count: counts.imported_run_count || 0,
    imported_grade_count: counts.imported_grade_count || 0,
    dashboard_case_count: cases.length,
    summary: snapshot.summary,
    a1_a2_join_ready: cases.some((item) => (
      item.trace_ready
      || (item.judge_results || []).length > 0
      || item.grade
    ))
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
