export const A3_REPORT_CENTER_MANIFEST_SCHEMA_VERSION = "a3.report_center_manifest.v1";

export function buildReportCenterManifest(report = {}, options = {}) {
  const usageLedger = options.usageLedger || {};
  const migrationPlan = options.migrationPlan || {};
  return {
    schema_version: A3_REPORT_CENTER_MANIFEST_SCHEMA_VERSION,
    report_id: report.report_id || "unknown",
    status: report.status || "unknown",
    source: report.source || "unknown",
    share_url_path: report.share_url_path || null,
    lifecycle: {
      expires_at: report.expires_at || null,
      revoked_at: report.revoked_at || null,
      view_count: report.view_audit?.view_count || 0,
      revocable: report.lifecycle?.revocable === true
    },
    artifacts: [
      artifact("json_report", "application/json", report.artifacts?.find((item) => item.id === "json_report")?.sha256),
      artifact("markdown_report", "text/markdown", report.artifacts?.find((item) => item.id === "markdown_report")?.sha256),
      artifact("hosted_report", "text/html", report.artifacts?.find((item) => item.id === "hosted_report")?.sha256),
      artifact("release_evidence_summary", "application/json", report.release_evidence_snapshot?.summary_hash || report.artifacts?.find((item) => item.id === "release_evidence_summary")?.sha256),
      artifact("usage_ledger", "application/json", usageLedger.schema_version),
      artifact("db_migration_plan", "application/sql", migrationPlan.schema_version)
    ],
    release_packet: {
      hosted_report_ready: report.status === "shareable",
      redaction_status: report.redaction?.status || "unknown",
      sealed_payload_hash: report.sealed_evidence?.payload_hash || null,
      release_evidence_summary_ready: report.release_evidence_summary?.available === true,
      release_evidence_snapshot_id: report.release_evidence_snapshot?.snapshot_id || null,
      usage_meter_count: Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0,
      migration_count: migrationPlan.migration_count || 0
    },
    next_actions: [
      "Attach this manifest to PR gate comments.",
      "Persist manifest rows in report_center_manifests once SQL adapter lands.",
      "Require manifest hash in audit bundle verification."
    ]
  };
}

function artifact(id, contentType, hashOrVersion) {
  return {
    id,
    content_type: contentType,
    reference: hashOrVersion || "pending",
    redacted: true
  };
}
