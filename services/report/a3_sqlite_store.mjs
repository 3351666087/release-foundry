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
    storageMode: "sqlite",
    dbReady: true,
    githubExecutorAuthority: options.githubExecutorAuthority
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

    async publishGitHubCheckRun(options = {}) {
      const result = await store.publishGitHubCheckRun(options);
      await persist();
      return result;
    },

    async publishGitHubPrComment(options = {}) {
      const result = await store.publishGitHubPrComment(options);
      await persist();
      return result;
    },

    async recordAccessDecision(decision, options = {}) {
      const result = await store.recordAccessDecision(decision, options);
      await persist();
      return {
        ...result,
        storage_mode: "sqlite"
      };
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
      release_evidence_snapshots: countRows(db, "release_evidence_snapshots"),
      release_evidence_diffs: countRows(db, "release_evidence_diffs"),
      release_evidence_readbacks: countRows(db, "release_evidence_readbacks"),
      audit_events: countRows(db, "audit_events"),
      event_outbox: countRows(db, "event_outbox"),
      github_publish_receipts: countRows(db, "github_publish_receipts"),
      deployment_receipts: countRows(db, "deployment_receipts"),
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
    persistEventOutbox(db, state, updatedAt);
    persistGitHubPublishReceipts(db, state, updatedAt);
    persistDeploymentReceipts(db, state, updatedAt);
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
    "event_outbox",
    "github_publish_receipts",
    "deployment_receipts",
    "artifact_lifecycle_events",
    "artifact_registry_entries",
    "release_evidence_readbacks",
    "release_evidence_diffs",
    "release_evidence_snapshots",
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
  for (const [storageKey, snapshot] of Object.entries(state.sources || {})) {
    const canonicalSource = snapshot.source || storageKey;
    const scopeOptions = sqliteSnapshotScopeOptions(snapshot, canonicalSource);
    const dashboard = await store.getDashboardSnapshot(canonicalSource, scopeOptions);
    db.prepare(`
INSERT INTO dashboard_snapshots (source, organization_id, project_id, case_count, total_runs, pass_rate, payload_json, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      storageKey,
      snapshot.organizationId || "org-local",
      snapshot.projectId || "project-local",
      dashboard.cases.length,
      dashboard.summary.totalRuns || 0,
      dashboard.summary.passRate || 0,
      JSON.stringify(dashboard),
      updatedAt
    );
    const runIdMap = new Map();
    for (const run of await store.listRuns(scopeOptions)) {
      const scopedRunId = sqliteScopedEntityId("run", snapshot, run.run_id);
      runIdMap.set(run.run_id, scopedRunId);
      db.prepare(`
INSERT INTO runs (id, organization_id, project_id, dataset_id, runner_id, status, trace_completeness, raw_payload_hash, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        scopedRunId,
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
      const scopedCaseId = sqliteScopedEntityId("case", snapshot, item.case_id);
      const scopedRunId = runIdMap.get(item.run_id) || sqliteScopedEntityId("run", snapshot, item.run_id);
      db.prepare(`
INSERT INTO cases (id, organization_id, project_id, run_id, scenario_id, status, score, primary_failure_class, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        scopedCaseId,
        snapshot.organizationId || "org-local",
        snapshot.projectId || "project-local",
        scopedRunId,
        item.scenario_id || null,
        item.status || "unknown",
        item.score ?? null,
        item.primary_failure_class || "unknown",
        JSON.stringify(item)
      );
    }
    const releaseEvidenceSummary = dashboard.release_evidence_summary || {};
    if (releaseEvidenceSummary.available === true) {
      const releaseId = dashboard.release_evidence_api?.release_id || `${canonicalSource}-release`;
      const summaryHash = sha256(JSON.stringify(releaseEvidenceSummary));
      let authority = null;
      let authorityDiff = null;
      try {
        authority = await store.getReleaseEvidenceSummary(releaseId, { ...scopeOptions, version: "2" });
        authorityDiff = await store.getReleaseEvidenceDiff(releaseId, scopeOptions);
      } catch {
        authority = null;
        authorityDiff = null;
      }
      db.prepare(`
INSERT INTO release_evidence_summaries (id, organization_id, project_id, release_id, source, summary_schema_version, overall_status, summary_hash, payload, hosted_report_snapshot_id, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
        `res_${summaryHash.slice(0, 16)}`,
        snapshot.organizationId || "org-local",
        snapshot.projectId || "project-local",
        releaseId,
        canonicalSource,
        releaseEvidenceSummary.schema_version || "unknown",
        releaseEvidenceSummary.overall_status || "unknown",
        summaryHash,
        JSON.stringify(releaseEvidenceSummary),
        null,
        updatedAt
      );
      if (authority?.release_evidence_summary?.schema_version === "a3.release_evidence_summary.v2") {
        const payload = authority.release_evidence_summary;
        const contentHash = sha256(JSON.stringify(payload));
        db.prepare(`
INSERT INTO release_evidence_snapshots (id, organization_id, project_id, release_id, summary_id, source_snapshot_id, summary_schema_version, summary_hash, content_hash, health_status, next_action, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
          `resnap_${contentHash.slice(0, 16)}`,
          snapshot.organizationId || "org-local",
          snapshot.projectId || "project-local",
          releaseId,
          authority.summary_id,
          payload.release_identity?.source_snapshot_id || null,
          payload.schema_version,
          payload.summary_hash,
          contentHash,
          payload.health?.overall_status || "unknown",
          payload.health?.next_action?.action || authority.next_action?.action || null,
          JSON.stringify(payload),
          updatedAt
        );
        const readbackRows = [
          ["github_check", payload.github_check_readback],
          ["pr_comment", payload.pr_comment_readback],
          ["required_check", payload.required_check_proof],
          ...((state.releaseEvidenceReadbacks || [])
            .filter((item) => (
              (item.source || canonicalSource) === canonicalSource
              && (item.release_id || releaseId) === releaseId
              && (item.organization_id || "org-local") === (snapshot.organizationId || "org-local")
              && (item.project_id || "project-local") === (snapshot.projectId || "project-local")
            ))
            .map((item) => [item.resource_kind || "readback", item]))
        ];
        const seenReadbackKeys = new Set();
        for (const [provider, item] of readbackRows) {
          const readbackPayload = item || {};
          const readbackIdSeed = readbackPayload.readback_id || readbackPayload.proof_id || `${authority.summary_id}:${provider}`;
          const dedupeKey = `${provider}:${readbackIdSeed}:${readbackPayload.payload_hash || "no_hash"}`;
          if (seenReadbackKeys.has(dedupeKey)) {
            continue;
          }
          seenReadbackKeys.add(dedupeKey);
          db.prepare(`
INSERT INTO release_evidence_readbacks (id, organization_id, project_id, release_id, summary_id, provider, readback_status, head_sha_alias, external_id_alias, payload_hash, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
            `rerb_${sha256(`${authority.summary_id}:${provider}:${readbackIdSeed}`).slice(0, 16)}`,
            snapshot.organizationId || "org-local",
            snapshot.projectId || "project-local",
            releaseId,
            authority.summary_id,
            provider,
            readbackPayload.readback_status || readbackPayload.enforcement_readback_status || "plan_only",
            readbackPayload.head_sha_alias || payload.release_identity?.head_sha_alias || null,
            readbackPayload.external_id_alias || readbackPayload.check_name || null,
            readbackPayload.payload_hash || sha256(JSON.stringify(readbackPayload)),
            JSON.stringify(readbackPayload),
            readbackPayload.captured_at || updatedAt
          );
        }
      }
      if (authorityDiff?.diff?.schema_version === "a3.release_evidence_diff.v1") {
        const diffHash = sha256(JSON.stringify(authorityDiff.diff));
        db.prepare(`
INSERT INTO release_evidence_diffs (id, organization_id, project_id, release_id, from_summary_id, to_summary_id, diff_hash, changed_field_count, regression_count, improvement_count, payload, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
          `rediff_${diffHash.slice(0, 16)}`,
          snapshot.organizationId || "org-local",
          snapshot.projectId || "project-local",
          releaseId,
          authorityDiff.diff.before_summary_id,
          authorityDiff.diff.after_summary_id,
          diffHash,
          authorityDiff.diff.safe_summary?.changed_field_count || 0,
          authorityDiff.diff.regression_count || 0,
          authorityDiff.diff.improvement_count || 0,
          JSON.stringify(authorityDiff.diff),
          updatedAt
        );
      }
    }
  }
}

function persistReports(db, state, updatedAt) {
  for (const report of state.reports || []) {
    const organizationId = report.tenant_scope?.organization_id || report.organization_id || "org-local";
    const projectId = report.tenant_scope?.project_id || report.project_id || "project-local";
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
    if (!["a1_run_result_import", "a2_grade_result_import"].includes(item.request_type)) {
      continue;
    }
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

function persistEventOutbox(db, state, updatedAt) {
  for (const row of state.eventOutbox || []) {
    db.prepare(`
INSERT INTO event_outbox (
  id, event_type, event_schema_version, organization_id, tenant_id, workspace_id,
  project_id, environment_id, actor_id, request_id, trace_id, resource_type,
  resource_id, payload_ref, payload_hash, redaction_status, delivery_status, created_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      row.event_id || row.id,
      row.event_type || "unknown.event",
      row.event_schema_version || "a3.event_envelope.v1",
      row.organization_id || "org-local",
      row.tenant_id || "tenant-local",
      row.workspace_id || "workspace-local",
      row.project_id || "project-local",
      row.environment_id || "staging",
      row.actor_id || "actor_[REDACTED_HASH]",
      row.request_id || "req_unknown",
      row.trace_id || "trace_unknown",
      row.resource_type || "unknown",
      row.resource_id || "unknown",
      row.payload_ref || null,
      row.payload_hash || sha256(JSON.stringify(row)),
      row.redaction_status || "metadata_only",
      row.delivery_status || "pending",
      row.created_at || updatedAt
    );
  }
}

function persistGitHubPublishReceipts(db, state, updatedAt) {
  for (const receipt of state.githubPublishReceipts || []) {
    db.prepare(`
INSERT INTO github_publish_receipts (
  id, organization_id, tenant_id, workspace_id, project_id, environment_id,
  source, release_id, resource_kind, repo_alias, external_id_alias,
  publish_status, dry_run, posted, payload_hash, payload, created_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      receipt.publish_id,
      receipt.organization_id || "org-local",
      receipt.tenant_id || "tenant-local",
      receipt.workspace_id || "workspace-local",
      receipt.project_id || "project-local",
      receipt.environment_id || "staging",
      receipt.source || "mock",
      receipt.release_id || "current",
      receipt.resource_kind || "unknown",
      typeof receipt.repo === "string" ? receipt.repo : null,
      receipt.external_id_alias == null ? null : String(receipt.external_id_alias),
      receipt.status || "unknown",
      receipt.dry_run !== false ? 1 : 0,
      receipt.posted === true ? 1 : 0,
      receipt.payload_hash || sha256(JSON.stringify(receipt)),
      JSON.stringify(receipt),
      receipt.published_at || updatedAt
    );
  }
}

function persistDeploymentReceipts(db, state, updatedAt) {
  for (const receipt of state.deploymentReceipts || []) {
    db.prepare(`
INSERT INTO deployment_receipts (
  id, organization_id, tenant_id, workspace_id, project_id, environment_id,
  source, blocker_id, candidate_id, run_id, status, version, evidence_kind,
  verifier_class, evidence_ref, evidence_sha256, production_verified,
  payload_hash, payload, created_at, reviewed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`).run(
      receipt.receipt_id,
      receipt.organization_id || "org-local",
      receipt.tenant_id || "tenant-local",
      receipt.workspace_id || "workspace-local",
      receipt.project_id || "project-local",
      receipt.environment_id || "staging",
      receipt.source || "unknown",
      receipt.blocker_id || "unknown",
      receipt.candidate_id || "unknown",
      receipt.run_id || "unknown",
      receipt.status || "submitted",
      Number(receipt.version || 1),
      receipt.evidence_kind || "unknown",
      receipt.verifier_class || "unknown",
      receipt.evidence_ref || "[REDACTED_UNSAFE_REF]",
      receipt.evidence_sha256 || `sha256:${sha256(JSON.stringify(receipt))}`,
      0,
      receipt.metadata_validation?.payload_hash || sha256(JSON.stringify(receipt)),
      JSON.stringify(receipt),
      receipt.submitted_at || updatedAt,
      receipt.reviewed_at || null
    );
  }
}

async function persistUsageLedger(db, store, state, updatedAt) {
  for (const [storageKey, snapshot] of Object.entries(state.sources || {})) {
    const source = snapshot.source || storageKey;
    const ledger = await store.getUsageLedger(sqliteSnapshotScopeOptions(snapshot, source));
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

function sqliteSnapshotScopeOptions(snapshot = {}, source = "mock") {
  const nested = snapshot.tenant_scope || {};
  return {
    source,
    organizationId: snapshot.organizationId || snapshot.organization_id || nested.organization_id || "org-local",
    tenantId: snapshot.tenantId || snapshot.tenant_id || nested.tenant_id || "tenant-local",
    workspaceId: snapshot.workspaceId || snapshot.workspace_id || nested.workspace_id || "workspace-local",
    projectId: snapshot.projectId || snapshot.project_id || nested.project_id || "project-local",
    environmentId: snapshot.environmentId || snapshot.environment_id || nested.environment_id || "staging",
    enforceScope: true
  };
}

function sqliteScopedEntityId(kind, snapshot = {}, externalId = "unknown") {
  return `${kind}_${sha256(JSON.stringify({
    scope: sqliteSnapshotScopeOptions(snapshot, snapshot.source || "mock"),
    external_id: externalId
  })).slice(0, 24)}`;
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
