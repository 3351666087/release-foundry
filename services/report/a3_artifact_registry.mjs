export const A3_ARTIFACT_REGISTRY_SCHEMA_VERSION = "a3.artifact_registry.v1";

const REPORT_ARTIFACTS = [
  ["json_report", "application/json", "automation and CI consumers"],
  ["markdown_report", "text/markdown", "PR reviewers and engineering handoff"],
  ["hosted_report", "text/html", "controlled customer-facing share link"],
  ["release_evidence_summary", "application/json", "API-backed release evidence health and audit handoff"],
  ["report_manifest", "application/json", "audit manifest and bundle verification"]
];

export function buildA3ArtifactRegistry(inputs = {}, options = {}) {
  const reportCenter = options.reportCenter || inputs.reportCenter || {};
  const usageLedger = options.usageLedger || inputs.usageLedger || {};
  const releaseEvidenceReadbacks = Array.isArray(options.releaseEvidenceReadbacks)
    ? options.releaseEvidenceReadbacks
    : Array.isArray(inputs.releaseEvidenceReadbacks)
      ? inputs.releaseEvidenceReadbacks
      : [];
  const migrationPlan = options.migrationPlan || inputs.migrationPlan || {};
  const productConsole = options.productConsole || inputs.productConsole || {};
  const saasAdmin = options.saasAdmin || inputs.saasAdmin || {};
  const githubPublishEvidence = options.githubPublishEvidence || inputs.githubPublishEvidence || {};
  const billingMigrationReadiness = options.billingMigrationReadiness || inputs.billingMigrationReadiness || inputs.billingMigration || {};
  const notificationControlPlane = options.notificationControlPlane || inputs.notificationControlPlane || inputs.notification_control_plane || {};
  const sourceArtifacts = options.sourceArtifacts || inputs.sourceArtifacts || {};
  const source = options.source || inputs.source || reportCenter.source || "unknown";
  const tenantScope = {
    organization_id: options.organizationId || inputs.organizationId || reportCenter.tenant_scope?.organization_id || "org-local",
    tenant_id: options.tenantId || inputs.tenantId || reportCenter.tenant_scope?.tenant_id || "tenant-local",
    workspace_id: options.workspaceId || inputs.workspaceId || reportCenter.tenant_scope?.workspace_id || "workspace-local",
    project_id: options.projectId || inputs.projectId || reportCenter.tenant_scope?.project_id || "project-local"
  };
  const reports = Array.isArray(reportCenter.reports)
    ? reportCenter.reports
    : Array.isArray(inputs.reports)
      ? inputs.reports
      : [];
  const reportEntries = reports.flatMap((report) => reportArtifactEntries(report, tenantScope));
  const controlEntries = controlArtifactEntries({
    tenantScope,
    source,
    usageLedger,
    releaseEvidenceReadbacks,
    migrationPlan,
    productConsole,
    saasAdmin,
    githubPublishEvidence,
    billingMigrationReadiness,
    notificationControlPlane
  });
  const entries = [...reportEntries, ...controlEntries, ...sourceArtifactEntries(sourceArtifacts, {
    tenantScope,
    source
  })];
  const summary = summarizeEntries(entries);

  return {
    schema_version: A3_ARTIFACT_REGISTRY_SCHEMA_VERSION,
    source,
    tenant_scope: tenantScope,
    registry_status: entries.length ? "evidence_available" : "empty",
    summary,
    entries,
    packet_presets: buildPacketPresets(entries),
    safety: {
      raw_secret_values_allowed: false,
      raw_share_tokens_stored: false,
      real_cloud_mutations_enabled: false,
      redaction_fail_closed_required: true,
      local_absolute_paths_allowed: false
    },
    next_actions: buildNextActions(summary, entries)
  };
}

function reportArtifactEntries(report = {}, tenantScope) {
  const redactionStatus = report.redaction?.status || "unknown";
  const blocked = report.redaction?.blocked === true || report.status === "blocked";
  const manifestMissing = Array.isArray(report.manifest?.missing) ? report.manifest.missing : [];
  const hashReady = report.sealed_evidence?.payload_hash_present === true
    || report.sealed_evidence?.secret_free === true
    || report.manifest?.redaction_status === "passed";
  return REPORT_ARTIFACTS.map(([type, contentType, customerValue]) => ({
    artifact_id: `${report.report_id || "report"}:${type}`,
    artifact_type: type,
    content_type: contentType,
    source: report.source || "unknown",
    tenant_scope: tenantScope,
    report_id: report.report_id || "unknown",
    manifest_join_key: `${report.report_id || "unknown"}:manifest`,
    lifecycle_state: artifactLifecycleState(report, blocked, type),
    hash_status: hashReady ? "hash_or_sealed_payload_present" : "pending_hash",
    redaction_status: redactionStatus,
    retention_class: report.status === "revoked" || report.status === "expired" ? "audit_retained" : "release_evidence",
    share_scope: report.share_link?.scope || "private_link",
    billable_meter: "report_exports",
    audit_events_required: ["artifact_generated", "redaction_scanned", "report_shared", "report_viewed"],
    missing_controls: blocked ? ["redaction_blocked"] : manifestMissing,
    customer_value: customerValue,
    raw_secret_values_allowed: false,
    raw_share_token_stored: false
  }));
}

function controlArtifactEntries(context) {
  const entries = [];
  const usageMeters = Array.isArray(context.usageLedger.meters) ? context.usageLedger.meters : [];
  entries.push(controlArtifact("usage_ledger", {
    context,
    ready: context.usageLedger.schema_version === "a3.usage_ledger.v1",
    contentType: "application/json",
    billableMeter: "usage_ledger_events",
    customerValue: "billing, quota, chargeback, and adoption evidence",
    missingControls: usageMeters.length ? ["content_hash"] : ["usage_meters", "content_hash"]
  }));
  entries.push(...context.releaseEvidenceReadbacks.slice(-12).map((readback) => controlArtifact(`release_evidence_readback:${readback.resource_kind || "unknown"}:${readback.readback_id || "unknown"}`, {
    context,
    ready: Boolean(readback.payload_hash),
    contentType: "application/json",
    billableMeter: "release_evidence_readbacks",
    customerValue: "external GitHub readback proof for PR gate, reviewer workflow, and audit packets",
    missingControls: readback.payload_hash ? ["live_provider_attestation"] : ["payload_hash", "live_provider_attestation"],
    resourceId: readback.readback_id || null,
    lifecycleState: readback.readback_status === "readback_confirmed" ? "generated" : "planned"
  })));
  entries.push(controlArtifact("db_migration_plan", {
    context,
    ready: context.migrationPlan.schema_version === "a3.sql_migration_plan.v1" && context.migrationPlan.status === "contract_ready",
    contentType: "application/sql",
    billableMeter: "self_host_readiness",
    customerValue: "self-host and enterprise deployment evidence",
    missingControls: context.migrationPlan.migration_count ? ["applied_migration_receipt"] : ["migration_plan"]
  }));
  entries.push(controlArtifact("product_console_state", {
    context,
    ready: context.productConsole.schema_version === "a3.product_console.v1",
    contentType: "application/json",
    billableMeter: "product_workflow_evidence",
    customerValue: "onboarding, project readiness, and audit-log state",
    missingControls: context.productConsole.schema_version ? ["signed_snapshot_hash"] : ["product_console_state"]
  }));
  entries.push(controlArtifact("saas_admin_guardrails", {
    context,
    ready: context.saasAdmin.schema_version === "a3.saas_admin_console.v1",
    contentType: "application/json",
    billableMeter: "admin_governance_evidence",
    customerValue: "login, team, API-key, usage, trust, and cloud-management safety map",
    missingControls: context.saasAdmin.schema_version ? ["rbac_enforcement_receipt"] : ["saas_admin_state"]
  }));
  entries.push(controlArtifact("auth_rbac_boundary", {
    context,
    ready: context.saasAdmin.auth_boundary?.schema_version === "a3.saas_admin_auth_boundary.v1",
    contentType: "application/json",
    billableMeter: "admin_governance_evidence",
    customerValue: "actor context, role policy, and denied-state evidence for hosted SaaS readiness",
    missingControls: context.saasAdmin.auth_boundary?.schema_version
      ? ["hosted_auth_enforcement_receipt", "rbac_decision_persistence"]
      : ["auth_rbac_boundary"]
  }));
  entries.push(billingMigrationReadinessArtifact(context));
  entries.push(notificationControlPlaneArtifact(context));
  entries.push(...githubPublishArtifactEntries(context));
  return entries;
}

function notificationControlPlaneArtifact(context) {
  const controlPlane = context.notificationControlPlane || {};
  const ready = controlPlane.schema_version === "a3.notification_control_plane.v1";
  const summary = controlPlane.summary || {};
  const safety = controlPlane.safety || {};
  const safe = safety.secret_values_included !== true
    && safety.raw_webhook_urls_included !== true
    && safety.raw_tokens_included !== true
    && safety.raw_emails_included !== true
    && safety.real_slack_mutation_performed_locally !== true
    && safety.real_teams_mutation_performed_locally !== true
    && safety.real_email_mutation_performed_locally !== true
    && safety.real_webhook_mutation_performed_locally !== true;
  return controlArtifact("notification_control_plane", {
    context,
    ready: ready && safe,
    contentType: "application/json",
    billableMeter: "notification_plans",
    customerValue: "Slack, Teams, email, and webhook release-notification readiness for enterprise sign-off without storing connector secrets.",
    billableValue: `${summary.channel_count || 0} planned notification channel(s), ${summary.growth_point_count || 0} commercial growth point(s), strongest path ${summary.strongest_money_path || "PR gate + incident replay"}.`,
    selfHostValue: "Maps notification_channels, notification_deliveries, event_outbox, audit_events, and usage_events into self-host deployment planning.",
    auditValue: "Shows who would be notified, which trigger fired, which evidence fields are included, and why A1 hosted workers must own live delivery.",
    missingControls: !ready
      ? ["notification_control_plane_contract"]
      : [
        "a1_hosted_notification_worker",
        "encrypted_connector_secret_reference",
        "live_delivery_receipts"
      ]
  });
}

function billingMigrationReadinessArtifact(context) {
  const readiness = context.billingMigrationReadiness || {};
  const ready = readiness.schema_version === "a3.billing_migration_readiness.v1";
  const liveReady = readiness.summary?.ready_for_live_customer_billing === true;
  const safety = readiness.safety || {};
  const safe = safety.env_local_read !== true
    && safety.real_api_called_by_a3 !== true
    && safety.real_payment_provider_called !== true
    && safety.billing_mutation_performed_by_a3 !== true
    && safety.provider_secret_values_included !== true
    && safety.raw_provider_payload_included !== true
    && safety.raw_card_data_included !== true
    && safety.raw_customer_email_included !== true;
  return controlArtifact("billing_migration_readiness", {
    context,
    ready: ready && safe,
    contentType: "application/json",
    billableMeter: "billing_readiness_artifacts",
    customerValue: "customer-safe billing ledger migration readiness for buyer review without live payment mutation claims",
    billableValue: "Shows invoice-preview and usage-unit migration readiness while keeping A3 billing writes disabled.",
    selfHostValue: "Maps A1-owned Postgres billing ledger tables, RLS, and replay expectations into self-host readiness evidence.",
    auditValue: "Carries provider-event hash, replay-status, tenant/RBAC, and no-raw-payload controls into audit packets.",
    missingControls: !ready
      ? ["billing_migration_readiness_contract"]
      : liveReady
        ? []
        : [
          "a1_authenticated_billing_ledger_read_api",
          "hosted_auth_rbac_enforcement",
          "a1_provider_webhook_executor",
          "live_billing_readback_receipts"
        ]
  });
}

function githubPublishArtifactEntries(context) {
  const evidence = context.githubPublishEvidence || {};
  return [
    githubArtifact("github_check_publish_receipt", evidence.check_publish, {
      context,
      billableMeter: "pr_gate_publish_events",
      customerValue: "machine-readable GitHub Check Run publish evidence",
      missingControls: ["live_check_receipt", "content_hash"]
    }),
    githubArtifact("github_pr_comment_publish_receipt", evidence.pr_comment_publish, {
      context,
      billableMeter: "pr_gate_publish_events",
      customerValue: "human-readable PR release comment publish evidence",
      missingControls: ["live_comment_receipt", "content_hash"]
    }),
    githubArtifact("github_required_check_plan", evidence.required_check_plan, {
      context,
      billableMeter: "release_gate_enforcement",
      customerValue: "branch-protection plan for making Ashr++ Release Gate required",
      missingControls: ["maintainer_branch_protection_receipt"]
    })
  ];
}

function githubArtifact(type, payload, options) {
  const ready = payload && typeof payload === "object" && payload.schema_version;
  const posted = payload?.posted === true || payload?.status === "posted";
  const planned = ready && (payload?.dry_run === true || payload?.mode?.startsWith?.("plan_") || payload?.status === "planned");
  return controlArtifact(type, {
    context: options.context,
    ready,
    contentType: "application/json",
    billableMeter: options.billableMeter,
    customerValue: options.customerValue,
    missingControls: posted
      ? ["content_hash"]
      : planned
        ? options.missingControls
        : [type]
  });
}

function controlArtifact(type, options) {
  return {
    artifact_id: `control:${type}`,
    artifact_type: type.startsWith("release_evidence_readback:") ? "release_evidence_readback" : type,
    content_type: options.contentType,
    source: options.context.source,
    tenant_scope: options.context.tenantScope,
    report_id: null,
    manifest_join_key: `control:${type}`,
    lifecycle_state: options.lifecycleState || (options.ready ? "generated" : "planned"),
    hash_status: options.ready ? "schema_reference_present" : "pending_source",
    redaction_status: "metadata_only",
    retention_class: "control_plane_evidence",
    share_scope: "internal_admin",
    billable_meter: options.billableMeter,
    audit_events_required: ["artifact_generated", "redaction_scanned", "admin_reviewed"],
    missing_controls: options.missingControls,
    customer_value: options.customerValue,
    billable_value: options.billableValue || null,
    self_host_value: options.selfHostValue || null,
    audit_value: options.auditValue || null,
    resource_id: options.resourceId || null,
    raw_secret_values_allowed: false,
    raw_share_token_stored: false
  };
}

function artifactLifecycleState(report, blocked, type) {
  if (blocked) {
    return "blocked";
  }
  if (report.status === "revoked" || report.status === "expired") {
    return "retained";
  }
  if (report.status === "shareable" && type === "hosted_report") {
    return "shared";
  }
  if (report.status === "shareable") {
    return "generated";
  }
  return "planned";
}

function summarizeEntries(entries) {
  return {
    artifact_count: entries.length,
    report_artifact_count: entries.filter((item) => item.report_id).length,
    control_artifact_count: entries.filter((item) => !item.report_id).length,
    ready_count: entries.filter((item) => ["generated", "shared", "retained"].includes(item.lifecycle_state)).length,
    planned_count: entries.filter((item) => item.lifecycle_state === "planned").length,
    blocked_count: entries.filter((item) => item.lifecycle_state === "blocked").length,
    hash_ready_count: entries.filter((item) => !item.hash_status.startsWith("pending")).length,
    redaction_pass_count: entries.filter((item) => ["passed", "metadata_only"].includes(item.redaction_status)).length,
    shareable_count: entries.filter((item) => item.lifecycle_state === "shared").length,
    billable_meter_count: new Set(entries.map((item) => item.billable_meter).filter(Boolean)).size,
    audit_required_count: entries.filter((item) => item.audit_events_required.length > 0).length
  };
}

function buildPacketPresets(entries) {
  return [
    packetPreset("pr_review_packet", ["json_report", "markdown_report", "release_evidence_summary", "report_manifest"], entries),
    packetPreset("github_pr_gate_packet", ["github_check_publish_receipt", "github_pr_comment_publish_receipt", "github_required_check_plan"], entries),
    packetPreset("executive_signoff_packet", ["hosted_report", "markdown_report", "product_console_state"], entries),
    packetPreset("security_audit_packet", ["report_manifest", "release_evidence_summary", "usage_ledger", "saas_admin_guardrails", "auth_rbac_boundary", "db_migration_plan", "billing_migration_readiness", "notification_control_plane"], entries),
    packetPreset("billing_migration_packet", ["billing_migration_readiness", "usage_ledger", "db_migration_plan", "report_manifest"], entries),
    packetPreset("notification_readiness_packet", ["notification_control_plane", "release_evidence_summary", "usage_ledger", "report_manifest"], entries),
    packetPreset("source_evidence_packet", ["a1_run_result", "a1_trace_event_batch", "a2_grade_result", "a2_release_gate"], entries),
    packetPreset("customer_safe_packet", ["hosted_report", "release_evidence_summary", "report_manifest"], entries)
  ];
}

function sourceArtifactEntries(sourceArtifacts = {}, context = {}) {
  const artifacts = Array.isArray(sourceArtifacts.artifacts) ? sourceArtifacts.artifacts : [];
  return artifacts.map((artifact) => ({
    artifact_id: artifact.source_artifact_id,
    artifact_type: artifact.artifact_type,
    content_type: "application/json",
    source: context.source,
    tenant_scope: artifact.tenant_scope || context.tenantScope,
    report_id: null,
    manifest_join_key: `source:${artifact.artifact_type}`,
    lifecycle_state: artifact.record_count > 0 ? "generated" : "planned",
    hash_status: artifact.content_hash ? "content_hash_present" : "pending_source",
    redaction_status: artifact.redaction_status || "hash_only",
    retention_class: "source_evidence",
    share_scope: "internal_audit",
    billable_meter: artifact.artifact_type?.startsWith("a1_") ? "run_evidence_sources" : "judge_evidence_sources",
    audit_events_required: ["source_artifact_registered", "redaction_scanned", "bundle_reseal_checked"],
    missing_controls: artifact.record_count > 0 ? [] : ["source_payload_missing"],
    customer_value: `${artifact.source_lane || "source"} ${artifact.source_contracts?.join("/") || "contract"} hash evidence`,
    source_lane: artifact.source_lane,
    source_contracts: artifact.source_contracts || [],
    content_hash: artifact.content_hash || null,
    record_count: artifact.record_count || 0,
    raw_secret_values_allowed: false,
    raw_share_token_stored: false,
    raw_payload_embedded: false
  }));
}

function packetPreset(id, requiredTypes, entries) {
  const availableTypes = new Set(entries
    .filter((item) => !["blocked", "planned"].includes(item.lifecycle_state))
    .map((item) => item.artifact_type));
  const missing = requiredTypes.filter((type) => !availableTypes.has(type));
  return {
    preset_id: id,
    required_artifact_types: requiredTypes,
    status: missing.length ? "incomplete" : "ready",
    missing_artifact_types: missing
  };
}

function buildNextActions(summary, entries) {
  const actions = [];
  if (!summary.report_artifact_count) {
    actions.push("Create a hosted report so JSON, Markdown, hosted HTML, and manifest artifacts can enter the registry.");
  }
  if (summary.blocked_count) {
    actions.push("Resolve redaction-blocked artifact entries before sharing customer packets.");
  }
  if (entries.some((item) => item.hash_status.startsWith("pending"))) {
    actions.push("Attach content hashes for all generated artifacts, including PDF and screenshot outputs.");
  }
  if (entries.some((item) => item.missing_controls.includes("rbac_enforcement_receipt"))) {
    actions.push("Back admin artifact entries with hosted RBAC enforcement receipts.");
  }
  if (!actions.length) {
    actions.push("Bind artifact registry entries into PR Gate, audit bundle verification, and usage billing events.");
  }
  return actions;
}
