import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";

import {
  createMemoryA3Store
} from "./a3_store.mjs";
import { buildA3SqlMigrationPlan } from "./a3_sql_migrations.mjs";

export const A3_SQLITE_STORE_SCHEMA_VERSION = "a3.sqlite_store.v1";

export async function createSqliteA3Store(options = {}) {
  if (!options.dbPath) {
    throw new Error("createSqliteA3Store requires dbPath.");
  }
  const db = new DatabaseSync(options.dbPath);
  applySqliteA3Schema(db);

  const existingState = loadPersistedState(db);
  const seed = existingState || options.seed || {};
  const store = createMemoryA3Store({
    ...seed,
    storageMode: "sqlite"
  });

  const persist = async () => {
    await persistSqliteState(db, store);
  };
  if (!existingState) {
    await persist();
  }

  return {
    ...store,
    schema_version: A3_SQLITE_STORE_SCHEMA_VERSION,
    storage_mode: "sqlite",

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

    async persist() {
      await persist();
    },

    inspectSqliteState() {
      return inspectSqliteA3Store(db);
    },

    close() {
      db.close();
    }
  };
}

export function inspectSqliteA3Store(db) {
  return {
    schema_version: "a3.sqlite_store_inspection.v1",
    storage_mode: "sqlite",
    migration_contract: buildA3SqlMigrationPlan({ dialect: "sqlite" }).schema_version,
    operational_tables: {
      a3_store_state: countRows(db, "a3_store_state"),
      dashboard_snapshots: countRows(db, "dashboard_snapshots"),
      runs: countRows(db, "runs"),
      cases: countRows(db, "cases"),
      shareable_reports: countRows(db, "shareable_reports"),
      report_share_links: countRows(db, "report_share_links"),
      report_view_events: countRows(db, "report_view_events"),
      report_revocations: countRows(db, "report_revocations"),
      idempotency_keys: countRows(db, "idempotency_keys"),
      api_import_receipts: countRows(db, "api_import_receipts"),
      saas_admin_action_requests: countRows(db, "saas_admin_action_requests"),
      review_workflow_records: countRows(db, "review_workflow_records"),
      release_evidence_summaries: countRows(db, "release_evidence_summaries"),
      audit_events: countRows(db, "audit_events"),
      usage_ledger: countRows(db, "usage_ledger")
    },
    safety: {
      raw_share_tokens_stored: false,
      raw_api_keys_stored: false,
      state_payload_secret_scan: scanSqliteStateForSecrets(db)
    }
  };
}

function applySqliteA3Schema(db) {
  db.exec("PRAGMA foreign_keys = ON");
  for (const item of buildA3SqlMigrationPlan({ dialect: "sqlite" }).statements) {
    db.exec(item.sql);
  }
  db.exec(`
CREATE TABLE IF NOT EXISTS a3_store_state (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dashboard_snapshots (
  source TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  case_count INTEGER NOT NULL,
  total_runs INTEGER NOT NULL,
  pass_rate REAL NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);`);
}

function loadPersistedState(db) {
  const row = db.prepare("SELECT value_json FROM a3_store_state WHERE key = ?").get("state");
  if (!row) {
    return null;
  }
  return JSON.parse(row.value_json);
}

async function persistSqliteState(db, store) {
  const state = store.exportState();
  const updatedAt = new Date().toISOString();
  db.exec("BEGIN");
  try {
    replaceStateTable(db, state, updatedAt);
    clearOperationalRows(db);
    persistOrganizationsAndProjects(db, state, updatedAt);
    await persistSnapshots(db, store, state, updatedAt);
    persistReports(db, state, updatedAt);
    persistIdempotencyReceipts(db, state, updatedAt);
    persistSaasAdminActionRequests(db, state, updatedAt);
    persistReviewWorkflowRecords(db, state, updatedAt);
    persistAuditEvents(db, state, updatedAt);
    await persistUsageLedger(db, store, state, updatedAt);
    db.exec("COMMIT");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

function replaceStateTable(db, state, updatedAt) {
  db.prepare(`
INSERT INTO a3_store_state (key, value_json, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
`).run("state", JSON.stringify(state), updatedAt);
}

function clearOperationalRows(db) {
  for (const table of [
    "usage_ledger",
    "report_revocations",
    "report_view_events",
    "audit_events",
    "artifact_lifecycle_events",
    "artifact_registry_entries",
    "release_evidence_summaries",
    "saas_admin_action_requests",
    "review_workflow_records",
    "api_import_receipts",
    "idempotency_keys",
    "report_share_links",
    "shareable_reports",
    "grade_results",
    "tool_calls",
    "trace_events",
    "cases",
    "runs",
    "dashboard_snapshots",
    "trust_reports",
    "api_keys",
    "team_members",
    "roles",
    "users",
    "projects",
    "organizations"
  ]) {
    db.prepare(`DELETE FROM ${table}`).run();
  }
}

function persistOrganizationsAndProjects(db, state, updatedAt) {
  const seenOrganizations = new Set();
  const seenProjects = new Set();
  for (const snapshot of Object.values(state.sources || {})) {
    const organizationId = snapshot.organizationId || "org-local";
    const projectId = snapshot.projectId || "project-local";
    if (!seenOrganizations.has(organizationId)) {
      db.prepare(`
INSERT INTO organizations (id, display_name, plan, created_at)
VALUES (?, ?, ?, ?)
`).run(organizationId, organizationId, "local_dev", updatedAt);
      seenOrganizations.add(organizationId);
    }
    if (seenProjects.has(projectId)) {
      continue;
    }
    db.prepare(`
INSERT INTO projects (id, organization_id, display_name, environment, created_at)
VALUES (?, ?, ?, ?, ?)
`).run(projectId, organizationId, projectId, "staging", updatedAt);
    seenProjects.add(projectId);
  }
}

async function persistSnapshots(db, store, state, updatedAt) {
  for (const [source, snapshot] of Object.entries(state.sources || {})) {
    const dashboard = await store.getDashboardSnapshot(source);
    db.prepare(`
INSERT INTO dashboard_snapshots (source, organization_id, project_id, case_count, total_runs, pass_rate, payload_json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      source,
      snapshot.organizationId || "org-local",
      snapshot.projectId || "project-local",
      dashboard.cases.length,
      dashboard.summary.totalRuns || 0,
      dashboard.summary.passRate || 0,
      JSON.stringify(dashboard),
      updatedAt
    );
    for (const run of await store.listRuns({ source })) {
      db.prepare(`
INSERT INTO runs (id, organization_id, project_id, dataset_id, runner_id, status, trace_completeness, raw_payload_hash, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        run.run_id,
        snapshot.organizationId || "org-local",
        snapshot.projectId || "project-local",
        run.dataset_id || "local-dataset",
        run.runner_id || "a1-local-runner",
        run.status || "unknown",
        run.trace_completeness ?? null,
        sha256(JSON.stringify(run)),
        updatedAt
      );
    }
    for (const item of dashboard.cases) {
      db.prepare(`
INSERT INTO cases (id, organization_id, project_id, run_id, scenario_id, status, score, primary_failure_class, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        item.case_id,
        snapshot.organizationId || "org-local",
        snapshot.projectId || "project-local",
        item.run_id,
        item.scenario_id || null,
        item.status || "unknown",
        item.score ?? null,
        item.primary_failure_class || "unknown",
        JSON.stringify(item)
      );
    }
    const releaseEvidenceSummary = dashboard.release_evidence_summary || {};
    if (releaseEvidenceSummary.available === true) {
      const releaseId = dashboard.release_evidence_api?.release_id || `${source}-release`;
      const summaryHash = sha256(JSON.stringify(releaseEvidenceSummary));
      db.prepare(`
INSERT INTO release_evidence_summaries (id, organization_id, project_id, release_id, source, summary_schema_version, overall_status, summary_hash, payload, hosted_report_snapshot_id, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        `res_${summaryHash.slice(0, 16)}`,
        snapshot.organizationId || "org-local",
        snapshot.projectId || "project-local",
        releaseId,
        source,
        releaseEvidenceSummary.schema_version || "unknown",
        releaseEvidenceSummary.overall_status || "unknown",
        summaryHash,
        JSON.stringify(releaseEvidenceSummary),
        null,
        updatedAt
      );
    }
  }
}

function persistReports(db, state, updatedAt) {
  for (const report of state.reports || []) {
    const organizationId = report.organization_id || "org-local";
    const projectId = report.project_id || "project-local";
    db.prepare(`
INSERT INTO shareable_reports (id, organization_id, project_id, source, status, payload_hash, expires_at, revoked_at, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      report.report_id,
      organizationId,
      projectId,
      report.source || "mock",
      report.status || "unknown",
      report.sealed_evidence?.payload_hash || sha256(JSON.stringify(report)),
      report.expires_at || null,
      report.revoked_at || null,
      JSON.stringify(report),
      report.created_at || updatedAt
    );
    if (report.share_link?.token_hash) {
      db.prepare(`
INSERT INTO report_share_links (token_hash, organization_id, project_id, report_id, scope, expires_at, revoked_at, created_by, created_at, last_viewed_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        report.share_link.token_hash,
        organizationId,
        projectId,
        report.report_id,
        report.share_link.scope || "private_link",
        report.share_link.expires_at || report.expires_at || null,
        report.share_link.revoked_at || report.revoked_at || null,
        report.created_by || "a3-api",
        report.share_link.created_at || report.created_at || updatedAt,
        report.share_link.last_viewed_at || null
      );
    }
  }
}

function persistIdempotencyReceipts(db, state, updatedAt) {
  for (const item of state.idempotencyReceipts || []) {
    const receipt = item.receipt || {};
    const organizationId = receipt.organization_id || "org-local";
    const projectId = receipt.project_id || "project-local";
    db.prepare(`
INSERT INTO idempotency_keys (key_hash, organization_id, project_id, request_type, source, payload_hash, response_payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      item.idempotency_key_hash || sha256(item.key || JSON.stringify(item)),
      organizationId,
      projectId,
      item.request_type || "unknown",
      item.source || receipt.source || "unknown",
      item.payload_hash || receipt.payload_hash || "",
      JSON.stringify(receipt),
      updatedAt
    );
    db.prepare(`
INSERT INTO api_import_receipts (organization_id, project_id, source, request_type, payload_hash, imported_run_count, imported_grade_count, dashboard_case_count, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      organizationId,
      projectId,
      item.source || receipt.source || "unknown",
      item.request_type || "unknown",
      item.payload_hash || receipt.payload_hash || "",
      receipt.imported_run_count || 0,
      receipt.imported_grade_count || 0,
      receipt.dashboard_case_count || 0,
      updatedAt
    );
  }
}

function persistSaasAdminActionRequests(db, state, updatedAt) {
  for (const request of state.adminActionRequests || []) {
    db.prepare(`
INSERT INTO saas_admin_action_requests (id, organization_id, project_id, action, area, mode, status, actor_hash, request_hash, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      request.request_id,
      request.organization_id || "org-local",
      request.project_id || "project-local",
      request.action || "unknown",
      request.area || "unknown",
      request.mode || "unknown",
      request.status || "unknown",
      request.actor_hash || request.requested_by_hash || null,
      request.request_hash || sha256(JSON.stringify(request)),
      JSON.stringify(request),
      request.requested_at || updatedAt
    );
  }
}

function persistReviewWorkflowRecords(db, state, updatedAt) {
  for (const record of state.reviewWorkflowRecords || []) {
    db.prepare(`
INSERT INTO review_workflow_records (id, organization_id, project_id, record_type, run_id, release_version, environment, status, accepted, payload_hash, review_hash, signature_status, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      record.record_id,
      record.organization_id || "org-local",
      record.project_id || "project-local",
      record.record_type || "unknown",
      record.run_id || null,
      record.release_version || null,
      record.environment || null,
      record.status || "unknown",
      record.accepted === true ? 1 : 0,
      record.payload_hash || sha256(JSON.stringify(record.payload || {})),
      record.review_hash || sha256(JSON.stringify(record.review || {})),
      record.signature?.status || "hash_sealed_unsigned_record",
      JSON.stringify(record),
      record.created_at || updatedAt
    );
  }
}

function persistAuditEvents(db, state, updatedAt) {
  for (const event of state.auditEvents || []) {
    const id = event.event_id || sha256(JSON.stringify(event)).slice(0, 16);
    const organizationId = event.organization_id || "org-local";
    const projectId = event.project_id || "project-local";
    db.prepare(`
INSERT INTO audit_events (id, organization_id, project_id, event_type, subject_id, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
`).run(
      id,
      organizationId,
      projectId,
      event.event_type || "unknown",
      event.report_id || event.subject_id || null,
      JSON.stringify(event),
      event.created_at || event.viewed_at || event.revoked_at || updatedAt
    );
    if ((event.event_type === "report_share_link_viewed" || event.event_type === "report_view") && event.report_id) {
      db.prepare(`
INSERT INTO report_view_events (id, organization_id, project_id, report_id, token_hash_prefix, access_result, viewer_hash, viewed_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        id,
        organizationId,
        projectId,
        event.report_id,
        event.token_hash_prefix || null,
        event.access_result || "allowed",
        event.viewer ? sha256(event.viewer).slice(0, 16) : null,
        event.viewed_at || updatedAt
      );
    }
    if (event.event_type === "report_revoke") {
      db.prepare(`
INSERT INTO report_revocations (id, organization_id, project_id, report_id, reason, revoked_at)
VALUES (?, ?, ?, ?, ?, ?)
`).run(
        id,
        organizationId,
        projectId,
        event.report_id || "missing-report",
        event.reason || "manual_revoke",
        event.revoked_at || updatedAt
      );
    }
  }
}

async function persistUsageLedger(db, store, state, updatedAt) {
  for (const source of Object.keys(state.sources || {})) {
    const ledger = await store.getUsageLedger({ source });
    for (const meter of ledger.meters || []) {
      db.prepare(`
INSERT INTO usage_ledger (organization_id, project_id, meter, quantity, source, period_start, period_end)
VALUES (?, ?, ?, ?, ?, ?, ?)
`).run(
        ledger.organization_id || "org-local",
        ledger.project_id || "project-local",
        meter.meter,
        meter.quantity || 0,
        source,
        ledger.period?.start || updatedAt,
        ledger.period?.end || updatedAt
      );
    }
  }
}

function countRows(db, table) {
  return db.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count;
}

function scanSqliteStateForSecrets(db) {
  const rows = db.prepare("SELECT value_json FROM a3_store_state").all();
  const text = rows.map((row) => row.value_json).join("\n");
  return {
    api_key_assignment_found: /\bASHR_API_KEY\s*=\s*[^.\s"']+/i.test(text),
    bearer_token_found: /\bBearer\s+[A-Za-z0-9._-]{20,}/.test(text),
    raw_share_token_hint_found: /unit_[A-Za-z0-9_]*share_token/.test(text)
  };
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}
