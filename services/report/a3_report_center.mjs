import { buildReportCenterManifest } from "./a3_report_center_manifest.mjs";
import { buildA3ArtifactRegistry } from "./a3_artifact_registry.mjs";

export const A3_REPORT_CENTER_INDEX_SCHEMA_VERSION = "a3.report_center_index.v1";

export function buildReportCenterIndex(reports = [], options = {}) {
  const usageLedger = options.usageLedger || {};
  const migrationPlan = options.migrationPlan || {};
  const now = options.now || new Date().toISOString();
  const items = reports.map((report) => reportCenterItem(report, {
    usageLedger,
    migrationPlan,
    now
  }));
  const statusCounts = countBy(items, "status");
  const productConsole = options.productConsole || {};
  const saasAdmin = options.saasAdmin || {};
  const artifactRegistry = buildA3ArtifactRegistry({
    source: options.source || "unknown",
    reportCenter: {
      source: options.source || "unknown",
      tenant_scope: {
        organization_id: options.organizationId || "org-local",
        project_id: options.projectId || "project-local"
      },
      reports: items
    },
    usageLedger,
    migrationPlan,
    productConsole,
    saasAdmin
  });

  return {
    schema_version: A3_REPORT_CENTER_INDEX_SCHEMA_VERSION,
    source: options.source || "unknown",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local"
    },
    generated_at: now,
    summary: {
      report_count: items.length,
      shareable_count: statusCounts.shareable || 0,
      expired_count: statusCounts.expired || 0,
      revoked_count: statusCounts.revoked || 0,
      blocked_count: statusCounts.blocked || 0,
      total_view_count: items.reduce((sum, item) => sum + item.view_count, 0),
      manifest_ready_count: items.filter((item) => item.manifest.completeness_score >= 80).length,
      firewall_pass_count: items.filter((item) => item.redaction.status === "passed").length,
      artifact_registry_count: artifactRegistry.summary.artifact_count,
      artifact_ready_count: artifactRegistry.summary.ready_count,
      artifact_billable_meter_count: artifactRegistry.summary.billable_meter_count,
      release_evidence_ready_count: items.filter((item) => item.release_evidence.available).length
    },
    control_plane: {
      usage_meter_count: Array.isArray(usageLedger.meters) ? usageLedger.meters.length : 0,
      migration_count: migrationPlan.migration_count || 0,
      billing_mutations_enabled: usageLedger.billing_mutations_enabled === true,
      sql_contract_ready: migrationPlan.status === "contract_ready",
      live_cloud_mutations_enabled: false
    },
    release_signoff_summary: buildReleaseSignoffSummary(items, artifactRegistry, usageLedger, migrationPlan),
    release_signoff_detail: buildReleaseSignoffDetail(items, artifactRegistry, usageLedger, migrationPlan),
    share_link_governance: buildShareLinkGovernance(items),
    reports: items,
    artifact_registry: artifactRegistry,
    next_actions: buildNextActions(items, usageLedger, migrationPlan)
  };
}

function buildReleaseSignoffSummary(items, artifactRegistry, usageLedger, migrationPlan) {
  const shareable = items.filter((item) => item.status === "shareable").length;
  const releaseReady = items.filter((item) => item.release_evidence.available).length;
  const manifestReady = items.filter((item) => item.manifest.completeness_score >= 80).length;
  const usageReady = Array.isArray(usageLedger.meters) && usageLedger.meters.length > 0;
  return {
    schema_version: "a3.release_signoff_summary.v1",
    status: shareable > 0 && releaseReady > 0 && manifestReady > 0 ? "signoff_packet_ready_for_review" : "signoff_packet_incomplete",
    shareable_count: shareable,
    release_evidence_ready_count: releaseReady,
    manifest_ready_count: manifestReady,
    artifact_ready_count: artifactRegistry.summary?.ready_count || 0,
    usage_ready: usageReady,
    migration_ready: (migrationPlan.migration_count || 0) > 0,
    next_actions: [
      "Attach reviewer approval or waiver before external sign-off.",
      "Keep release-evidence readbacks visible next to hosted report lifecycle.",
      "Treat usage and migration evidence as part of the release packet, not separate admin notes."
    ]
  };
}

function buildShareLinkGovernance(items) {
  const total = items.length;
  const shareable = items.filter((item) => item.status === "shareable");
  const revoked = items.filter((item) => item.status === "revoked");
  const expired = items.filter((item) => item.status === "expired");
  const blocked = items.filter((item) => item.status === "blocked");
  return {
    schema_version: "a3.share_link_governance.v1",
    status: shareable.length > 0 ? "governed_links_visible" : "no_shareable_links",
    total_report_count: total,
    shareable_count: shareable.length,
    revoked_count: revoked.length,
    expired_count: expired.length,
    blocked_count: blocked.length,
    policy_summary: [
      "Every share link must be revocable and expireable.",
      "Hosted report access stays audit-visible even when the content is redacted.",
      "External sharing never reveals raw tokens in A3 evidence surfaces."
    ],
    next_actions: [
      "Expose revoke and expiry posture in the admin console and report center together.",
      "Keep audit event counts next to shareable report readiness for release sign-off.",
      "Add tenant and environment filters before enabling broader hosted sharing."
    ]
  };
}

function buildReleaseSignoffDetail(items, artifactRegistry, usageLedger, migrationPlan) {
  return {
    schema_version: "a3.release_signoff_detail.v1",
    checklist: [
      { id: "shareable_report", passed: items.some((item) => item.status === "shareable") },
      { id: "release_evidence", passed: items.some((item) => item.release_evidence.available) },
      { id: "manifest_ready", passed: items.some((item) => item.manifest.completeness_score >= 80) },
      { id: "usage_ready", passed: Array.isArray(usageLedger.meters) && usageLedger.meters.length > 0 },
      { id: "migration_ready", passed: (migrationPlan.migration_count || 0) > 0 },
      { id: "artifact_registry", passed: (artifactRegistry.summary?.ready_count || 0) > 0 }
    ],
    recommendations: [
      "Collect reviewer approval or waiver before claiming external sign-off.",
      "Keep audit bundle and readback receipts visible next to hosted reports.",
      "Use usage and migration evidence as part of the executive release packet."
    ]
  };
}

function reportCenterItem(report = {}, options = {}) {
  const status = lifecycleStatus(report, options.now);
  const manifest = buildReportCenterManifest({ ...report, status }, {
    usageLedger: options.usageLedger,
    migrationPlan: options.migrationPlan
  });
  const completeness = manifestCompleteness(manifest, report, status);

  return {
    report_id: report.report_id || "unknown",
    title: report.title || "Untitled report",
    source: report.source || "unknown",
    status,
    share_url_path: report.share_url_path || null,
    internal_url_path: report.internal_url_path || null,
    created_at: report.created_at || null,
    expires_at: report.expires_at || null,
    revoked_at: report.revoked_at || null,
    view_count: report.view_audit?.view_count || 0,
    lifecycle: {
      revocable: report.lifecycle?.revocable === true && status === "shareable",
      view_audit_enabled: report.lifecycle?.view_audit_enabled === true,
      public_indexing_allowed: report.lifecycle?.public_indexing_allowed === true,
      expired: status === "expired",
      revoked: status === "revoked"
    },
    share_link: {
      token_hash_prefix: report.share_link?.token_hash_prefix || null,
      scope: report.share_link?.scope || "private_link",
      raw_token_stored: false,
      expires_at: report.share_link?.expires_at || report.expires_at || null,
      revoked_at: report.share_link?.revoked_at || report.revoked_at || null
    },
    redaction: {
      status: report.redaction?.status || "unknown",
      blocked: report.redaction?.blocked === true || status === "blocked",
      residual_finding_count: report.redaction?.residual_finding_count || 0
    },
    sealed_evidence: {
      hash_algorithm: report.sealed_evidence?.hash_algorithm || "unknown",
      payload_hash_present: Boolean(report.sealed_evidence?.payload_hash),
      secret_free: report.sealed_evidence?.secret_free === true
    },
    release_evidence: {
      available: report.release_evidence_summary?.available === true,
      overall_status: report.release_evidence_summary?.overall_status || "missing",
      summary_snapshot_id: report.release_evidence_snapshot?.snapshot_id || null,
      summary_hash_present: Boolean(report.release_evidence_snapshot?.summary_hash),
      github_check_status: report.release_evidence_summary?.github_check_publish?.status || "missing",
      pr_comment_status: report.release_evidence_summary?.github_pr_comment_publish?.status || "missing",
      bundle_status: report.release_evidence_summary?.audit_bundle_verification?.status || "missing",
      archive_status: report.release_evidence_summary?.audit_archive_verification?.status || "missing"
    },
    manifest: {
      schema_version: manifest.schema_version,
      artifact_count: manifest.artifacts.length,
      usage_meter_count: manifest.release_packet.usage_meter_count,
      migration_count: manifest.release_packet.migration_count,
      hosted_report_ready: manifest.release_packet.hosted_report_ready,
      release_evidence_summary_ready: manifest.release_packet.release_evidence_summary_ready === true,
      release_evidence_snapshot_id: manifest.release_packet.release_evidence_snapshot_id || null,
      redaction_status: manifest.release_packet.redaction_status,
      completeness_score: completeness.score,
      missing: completeness.missing
    }
  };
}

function manifestCompleteness(manifest, report, status) {
  const checks = [
    ["share_url_path", Boolean(report.share_url_path)],
    ["share_token_hash", Boolean(report.share_link?.token_hash)],
    ["payload_hash", Boolean(report.sealed_evidence?.payload_hash)],
    ["redaction_passed", report.redaction?.status === "passed" && report.redaction?.blocked !== true],
    ["hosted_report_ready", manifest.release_packet.hosted_report_ready || status !== "shareable"],
    ["release_evidence_summary", manifest.release_packet.release_evidence_summary_ready === true],
    ["usage_ledger", manifest.release_packet.usage_meter_count > 0],
    ["db_migration_plan", manifest.release_packet.migration_count > 0],
    ["artifact_registry", Array.isArray(manifest.artifacts) && manifest.artifacts.length >= 5],
    ["view_audit", report.lifecycle?.view_audit_enabled === true]
  ];
  const missing = checks.filter(([, ok]) => !ok).map(([name]) => name);
  return {
    score: Math.round(((checks.length - missing.length) / checks.length) * 100),
    missing
  };
}

function lifecycleStatus(report = {}, now = new Date().toISOString()) {
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

function buildNextActions(items, usageLedger = {}, migrationPlan = {}) {
  const actions = [];
  if (!items.length) {
    actions.push("Create the first hosted report from an API-backed dashboard source.");
  }
  if (!Array.isArray(usageLedger.meters) || usageLedger.meters.length === 0) {
    actions.push("Attach a usage ledger before presenting Report Center as billable evidence.");
  }
  if (!migrationPlan.migration_count) {
    actions.push("Attach DB migration evidence before claiming self-host readiness.");
  }
  if (items.some((item) => item.redaction.blocked)) {
    actions.push("Fix blocked redaction findings before sharing customer-facing reports.");
  }
  if (items.some((item) => item.status === "expired" || item.status === "revoked")) {
    actions.push("Keep expired and revoked reports visible for audit, but block hosted access.");
  }
  if (!actions.length) {
    actions.push("Link the Report Center manifest to PR Gate and audit bundle verification.");
  }
  return actions;
}

function countBy(items, key) {
  return items.reduce((counts, item) => {
    const value = item[key] || "unknown";
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

