export const A3_NOTIFICATION_CONTROL_PLANE_SCHEMA_VERSION = "a3.notification_control_plane.v1";

const SECRET_VALUE_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{12,}\b/,
  /\bghp_[A-Za-z0-9]{12,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bxox[baprs]-[A-Za-z0-9-]{12,}\b/i,
  /\bwhsec_[A-Za-z0-9_=-]{12,}\b/i,
  /hooks\.slack\.com\/services/i,
  /outlook\.office\.com\/webhook/i,
  /https:\/\/[^"\s]*(?:hook|webhook|secret|token)[^"\s]*/i,
  /authorization:\s*[A-Za-z]+\s+[A-Za-z0-9._-]{12,}/i,
  /cookie:\s*[^"\s]{12,}/i,
  /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
  /C:\\Users\\/i,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/
];

export function buildA3NotificationControlPlane(inputs = {}, options = {}) {
  const usageLedger = inputs.usageLedger || inputs.usage_ledger || {};
  const liveOpsControlPlane = inputs.liveOpsControlPlane || inputs.live_ops_control_plane || {};
  const liveWorkflowReadiness = inputs.liveWorkflowReadiness || inputs.live_workflow_readiness || {};
  const releaseEvidence = inputs.releaseEvidence || inputs.release_evidence || {};
  const reviewWorkflow = inputs.reviewWorkflow || inputs.review_workflow || {};
  const source = options.source
    || inputs.source
    || liveOpsControlPlane.source
    || liveWorkflowReadiness.source
    || usageLedger.source
    || "mock";
  const tenantScope = {
    organization_id: options.organizationId
      || liveOpsControlPlane.tenant_scope?.organization_id
      || liveWorkflowReadiness.tenant_scope?.organization_id
      || usageLedger.tenant_scope?.organization_id
      || "org-local",
    project_id: options.projectId
      || liveOpsControlPlane.tenant_scope?.project_id
      || liveWorkflowReadiness.tenant_scope?.project_id
      || usageLedger.tenant_scope?.project_id
      || "project-local"
  };
  const context = {
    tenantScope,
    releaseEvidenceReady: Boolean(releaseEvidence.schema_version || liveOpsControlPlane.schema_version),
    reviewWorkflowReady: reviewWorkflow.schema_version === "a3.review_workflow_index.v1"
      || numberOr(reviewWorkflow.record_count, 0) > 0,
    usageLedgerReady: usageLedger.schema_version === "a3.usage_ledger.v1"
  };
  const lanes = [
    slackLane(providerInput(inputs, "slack"), context),
    teamsLane(providerInput(inputs, "teams"), context),
    emailLane(providerInput(inputs, "email"), context),
    webhookLane(providerInput(inputs, "webhook"), context)
  ];
  const apiRoutes = unique(lanes.flatMap((item) => item.api.routes));
  const dbTables = unique(lanes.flatMap((item) => item.db.tables));
  const eventTypes = unique(lanes.flatMap((item) => item.event.types));
  const artifactTypes = unique(lanes.flatMap((item) => item.artifact.types));
  const auditEvents = unique(lanes.flatMap((item) => item.audit.events));
  const usageMeters = unique(lanes.flatMap((item) => item.usage.meters));
  const configuredCount = lanes.filter((item) => item.provider_metadata_present).length;
  const contractReadyCount = lanes.filter((item) => item.status === "contract_ready_needs_provider_config").length;
  const channels = lanes.map(channelProjection);
  const triggerMatrix = lanes.map(triggerProjection);
  const growthPoints = buildGrowthPoints(lanes);
  const humanSummary = liveOpsControlPlane.human_operation_summary || {};
  const billingSummary = liveOpsControlPlane.billing_state_summary || {};
  const shareSummary = liveOpsControlPlane.report_link_summary || {};

  return {
    schema_version: A3_NOTIFICATION_CONTROL_PLANE_SCHEMA_VERSION,
    generated_at: options.generatedAt || "2026-07-09T00:00:00.000Z",
    source,
    tenant_scope: tenantScope,
    status: configuredCount > 0
      ? "metadata_present_delivery_disabled"
      : "contract_ready_needs_provider_config",
    summary: {
      channel_count: lanes.length,
      provider_count: lanes.length,
      api_backed_count: lanes.filter((item) => item.api.routes.length > 0).length,
      audit_backed_count: lanes.filter((item) => item.audit.events.length > 0).length,
      usage_metered_count: lanes.filter((item) => item.usage.meters.length > 0).length,
      configured_metadata_count: configuredCount,
      contract_ready_count: contractReadyCount,
      live_mutation_count: 0,
      growth_point_count: growthPoints.length,
      strongest_money_path: "PR gate + incident replay + enterprise audit notifications"
    },
    live_ops_alignment: {
      review_record_count: numberOr(humanSummary.review_record_count, 0),
      approval_count: numberOr(humanSummary.approval_count, 0),
      denial_count: numberOr(humanSummary.denial_count, 0),
      waiver_count: numberOr(humanSummary.waiver_count, 0),
      event_outbox_count: numberOr(humanSummary.event_outbox_count, 0),
      visible_human_ops: Boolean(humanSummary.dashboard_visible),
      usage_meter_count: numberOr(billingSummary.meter_count, 0),
      billing_readiness_status: billingSummary.billing_readiness_status || "unknown",
      billing_mutations_enabled: billingSummary.billing_mutations_enabled === true,
      shareable_report_count: numberOr(shareSummary.shareable_count, 0),
      revoked_report_count: numberOr(shareSummary.revoked_count, 0),
      expired_report_count: numberOr(shareSummary.expired_count, 0),
      total_report_views: numberOr(shareSummary.total_view_count, 0),
      why_it_sells: "Notifications become more valuable when tied to reviewer actions, billing/usage visibility, and shareable audit reports."
    },
    counts: {
      lane_count: lanes.length,
      configured_metadata_count: configuredCount,
      api_contract_count: apiRoutes.length,
      db_contract_count: dbTables.length,
      event_contract_count: eventTypes.length,
      artifact_contract_count: artifactTypes.length,
      rbac_guarded_count: lanes.filter((item) => item.RBAC.permissions.length > 0).length,
      usage_meter_count: usageMeters.length,
      audit_backed_count: lanes.filter((item) => item.audit.events.length > 0).length,
      local_external_mutation_count: 0
    },
    commercial_value: {
      sellable_claim: "Enterprise release decisions can reach Slack, Teams, email digests, and customer webhooks with tenant scope, audit evidence, and usage metering.",
      buyer_outcomes: [
        "shorter reviewer SLA for blocked releases",
        "on-call notification for risky agent behavior",
        "customer-owned webhook automation without exposing private payloads",
        "auditable notification history for enterprise release governance"
      ],
      growth_dimensions: ["revenue", "risk", "audit", "usage", "integrations", "e2e"],
      monetization_hooks: [
        "notification_delivery_attempts",
        "notification_delivery_successes",
        "webhook_delivery_attempts",
        "review_escalation_notifications"
      ],
      readiness_note: "This is a contract surface only; provider sends remain disabled until A1 owns hosted credentials, queues, tenant middleware, and usage writes."
    },
    api: {
      response_schema: A3_NOTIFICATION_CONTROL_PLANE_SCHEMA_VERSION,
      public_routes: [
        "GET /api/a3/notifications/control-plane",
        "GET /api/a3/notifications/preferences",
        "POST /api/a3/notifications/test-plan"
      ],
      internal_routes: [
        "POST /internal/notifications/slack/deliver",
        "POST /internal/notifications/teams/deliver",
        "POST /internal/notifications/email/deliver",
        "POST /internal/notifications/webhook/deliver"
      ],
      idempotency_key_required: true,
      provider_routes: lanes.map((item) => ({ lane_id: item.id, routes: item.api.routes }))
    },
    db: {
      tables: dbTables,
      tenant_columns_required: ["organization_id", "project_id"],
      uniqueness: ["organization_id + project_id + provider + channel_ref_hash", "delivery_id", "idempotency_key"]
    },
    event: {
      types: eventTypes,
      envelope_fields: [
        "event_id",
        "event_type",
        "schema_version",
        "organization_id",
        "project_id",
        "actor_id",
        "request_id",
        "trace_id",
        "resource_type",
        "resource_id",
        "payload_ref",
        "redaction_status"
      ],
      payload_policy: "metadata-only ids, hashes, statuses, counts, and artifact refs"
    },
    artifact: {
      types: artifactTypes,
      registry_required: true,
      redaction_required_before_export: true,
      bundle_reseal_triggers: [
        "notification delivery receipt changed",
        "notification preference changed",
        "webhook schema changed",
        "audit receipt changed"
      ]
    },
    tenant: {
      required_scope_fields: ["organization_id", "project_id", "environment_id", "release_id"],
      cross_tenant_default: "404_or_empty",
      per_provider_preference_scope: "organization + project + channel_or_endpoint_ref_hash",
      storage_policy: "No tenant-owned notification row is durable without organization_id and project_id."
    },
    RBAC: {
      roles: ["organization owner", "organization admin", "project admin", "reviewer", "auditor", "service account"],
      permissions: [
        "notifications:read",
        "notifications:configure",
        "notifications:test",
        "notifications:deliver",
        "audit:read",
        "usage:read"
      ],
      mutation_permissions: ["notifications:configure", "notifications:test"],
      delivery_worker_role: "service_account:notification_delivery_worker",
      fail_closed_policy: "Provider sends are denied unless tenant scope, actor, permission, idempotency key, and audit intent are present."
    },
    usage: {
      meters: usageMeters,
      chargeback_state: "metered_preview",
      billing_mutations_enabled: false,
      ledger_dependency: "A1 usage ledger must write authoritative notification and webhook delivery events before billing claims."
    },
    audit: {
      events: auditEvents,
      append_only_required: true,
      actor_binding_required: true,
      payload_policy: "No private message body, raw endpoint, recipient address, token, cookie, or provider secret is stored."
    },
    dependencies: {
      A1: {
        consumed_contracts: ["tenant middleware", "hosted auth/session", "RBAC backend", "event outbox", "queue worker", "usage ledger", "webhook delivery backend", "artifact registry"],
        owns: ["provider credentials", "webhook signing verification", "delivery retries", "dead letter queue", "rate limit", "tenant enforcement", "usage event writes"],
        boundary: "A3 can design notification preferences and previews, but A1 owns hosted delivery execution and secret custody."
      },
      A2: {
        consumed_contracts: ["ReleaseGate", "GradeResult", "failure taxonomy", "security policy", "cost/risk policy"],
        owns: ["which risks are notify-worthy", "abuse/security verification", "redaction correctness", "policy drift detection"],
        boundary: "A3 routes A2 decisions and risk labels downstream; it does not change judge scoring, thresholds, failure classes, or release policy semantics."
      }
    },
    a1_a2_boundary: {
      downstream_only: true,
      a3_mutates_a1_a2_semantics: false,
      note: "Notification lanes consume A1/A2 evidence and release decisions; they never rewrite runner traces, usage ledger facts, judge scores, pass/fail state, or policy thresholds."
    },
    a1_a2_alignment: {
      a1_consumed_contracts: ["RunResult", "Trace", "ToolCall", "event outbox", "usage ledger", "webhook delivery worker"],
      a2_consumed_contracts: ["GradeResult", "ReleaseGate", "failure taxonomy", "security policy", "cost/risk policy"],
      a3_mutates_a1_a2_semantics: false,
      note: "A3 only routes notification-ready evidence downstream; A1 runner/API facts and A2 judge/release policy facts remain authoritative."
    },
    lanes,
    channels,
    trigger_matrix: triggerMatrix,
    growth_points: growthPoints,
    safety: {
      secret_values_included: false,
      raw_tokens_included: false,
      raw_cookies_included: false,
      raw_emails_included: false,
      raw_webhook_urls_included: false,
      raw_provider_payloads_included: false,
      raw_signed_urls_included: false,
      local_absolute_paths_included: false,
      provider_credentials_echoed: false,
      real_external_mutation_performed_locally: false,
      real_slack_mutation_performed_locally: false,
      real_teams_mutation_performed_locally: false,
      real_email_mutation_performed_locally: false,
      real_webhook_mutation_performed_locally: false,
      slack_message_sent: false,
      teams_message_sent: false,
      email_sent: false,
      webhook_called: false
    },
    next_actions: nextActions(lanes)
  };
}

export function findA3NotificationSecretLeaks(value) {
  const serialized = JSON.stringify(value);
  return SECRET_VALUE_PATTERNS
    .filter((pattern) => pattern.test(serialized))
    .map((pattern) => ({ pattern: pattern.source }));
}

function slackLane(config = {}, context = {}) {
  return notificationLane({
    id: "slack_release_notifications",
    provider: "slack",
    label: "Slack release and reviewer notifications",
    product_surface: "Slack app / Release Service",
    provider_metadata_present: hasProviderMetadata(config),
    triggers: ["release_gate.blocked", "release_gate.approved", "review_item.escalated", "quota.exceeded"],
    api_routes: ["POST /internal/notifications/slack/deliver", "GET /api/a3/notifications/slack/preferences"],
    db_tables: baseTables(["notification_slack_installations"]),
    events: [
      "notification.slack_delivery_planned",
      "notification.slack_delivery_succeeded",
      "notification.slack_delivery_failed"
    ],
    artifacts: ["slack_message_preview", "notification_delivery_receipt", "redaction_report"],
    usage_meters: ["slack_notification_delivery_attempts", "slack_notification_delivery_successes"],
    audit_events: ["notification.slack_configured", "notification.slack_test_planned", "notification.slack_delivery_recorded"],
    A1: "A1 owns Slack app credentials, bot tokens, queue execution, tenant middleware, and usage event writes.",
    A2: "A2 owns release-gate and security policy semantics that decide when a Slack alert is justified.",
    next_action: context.releaseEvidenceReady
      ? "Create an A1-owned Slack installation record and keep A3 limited to preference preview plus delivery receipts."
      : "Bind Slack notification previews to release evidence before enabling hosted provider configuration."
  });
}

function teamsLane(config = {}, context = {}) {
  return notificationLane({
    id: "teams_release_notifications",
    provider: "teams",
    label: "Microsoft Teams release and reviewer notifications",
    product_surface: "Teams workflow / Release Service",
    provider_metadata_present: hasProviderMetadata(config),
    triggers: ["release_gate.blocked", "release_gate.approved", "review_item.assigned", "review_item.escalated"],
    api_routes: ["POST /internal/notifications/teams/deliver", "GET /api/a3/notifications/teams/preferences"],
    db_tables: baseTables(["notification_teams_installations"]),
    events: [
      "notification.teams_delivery_planned",
      "notification.teams_delivery_succeeded",
      "notification.teams_delivery_failed"
    ],
    artifacts: ["teams_card_preview", "notification_delivery_receipt", "redaction_report"],
    usage_meters: ["teams_notification_delivery_attempts", "teams_notification_delivery_successes"],
    audit_events: ["notification.teams_configured", "notification.teams_test_planned", "notification.teams_delivery_recorded"],
    A1: "A1 owns Microsoft identity integration, Teams credentials, delivery worker execution, retries, and tenant enforcement.",
    A2: "A2 owns policy and risk labels included in Teams cards without changing release decisions.",
    next_action: context.reviewWorkflowReady
      ? "Map reviewer assignment and escalation events into Teams card previews, then hand delivery to A1."
      : "Attach Teams notification preferences after reviewer workflow records are tenant-scoped and audited."
  });
}

function emailLane(config = {}, context = {}) {
  return notificationLane({
    id: "email_release_notifications",
    provider: "email",
    label: "Email digest and escalation notifications",
    product_surface: "Email digest / Reviewer Workflow",
    provider_metadata_present: hasProviderMetadata(config),
    triggers: ["review_item.assigned", "review_item.escalated", "release_gate.blocked", "audit_packet.exported"],
    api_routes: ["POST /internal/notifications/email/deliver", "GET /api/a3/notifications/email/preferences"],
    db_tables: baseTables(["notification_email_preferences"]),
    events: [
      "notification.email_digest_planned",
      "notification.email_delivery_succeeded",
      "notification.email_delivery_failed"
    ],
    artifacts: ["email_digest_preview", "notification_delivery_receipt", "redaction_report"],
    usage_meters: ["email_notification_delivery_attempts", "email_notification_delivery_successes"],
    audit_events: ["notification.email_preferences_changed", "notification.email_test_planned", "notification.email_delivery_recorded"],
    A1: "A1 owns email provider credentials, recipient identity resolution, bounce handling, unsubscribe enforcement, and usage writes.",
    A2: "A2 owns safety and privacy checks that determine which evidence can appear in an email digest.",
    next_action: context.usageLedgerReady
      ? "Meter email delivery attempts through the A1 usage ledger while keeping recipient addresses outside A3 artifacts."
      : "Wait for authoritative A1 usage rows before turning email delivery receipts into billable evidence."
  });
}

function webhookLane(config = {}, context = {}) {
  return notificationLane({
    id: "customer_webhook_notifications",
    provider: "webhook",
    label: "Customer webhook notifications",
    product_surface: "Customer webhook / Integration API",
    provider_metadata_present: hasProviderMetadata(config),
    triggers: ["release_gate.blocked", "release_gate.approved", "bundle.verified", "report.shared"],
    api_routes: ["POST /internal/notifications/webhook/deliver", "GET /api/a3/notifications/webhooks"],
    db_tables: baseTables(["webhooks", "webhook_deliveries"]),
    events: [
      "notification.webhook_delivery_planned",
      "notification.webhook_delivery_succeeded",
      "notification.webhook_delivery_failed"
    ],
    artifacts: ["webhook_schema", "webhook_delivery_receipt", "redaction_report"],
    usage_meters: ["webhook_delivery_attempts", "webhook_delivery_successes"],
    audit_events: ["notification.webhook_configured", "notification.webhook_test_planned", "notification.webhook_delivery_recorded"],
    A1: "A1 owns endpoint secret custody, signing, replay defense, delivery worker execution, rate limits, and dead-letter handling.",
    A2: "A2 owns redaction and policy verification for event payloads before webhooks leave the tenant boundary.",
    next_action: context.releaseEvidenceReady
      ? "Publish only versioned webhook schemas and receipt hashes until A1 provides signed delivery workers."
      : "Bind webhook schemas to release evidence and bundle verification events before exposing customer configuration."
  });
}

function notificationLane(value = {}) {
  return {
    id: value.id,
    provider: value.provider,
    label: value.label,
    product_surface: value.product_surface,
    status: value.provider_metadata_present
      ? "metadata_config_present_delivery_disabled"
      : "contract_ready_needs_provider_config",
    current_mode: "plan_only_no_provider_send",
    provider_metadata_present: value.provider_metadata_present === true,
    delivery_triggers: value.triggers || [],
    api: {
      routes: value.api_routes || [],
      auth: "tenant_scoped_notification_permission",
      idempotency_key_required: true,
      response_schema: A3_NOTIFICATION_CONTROL_PLANE_SCHEMA_VERSION
    },
    db: {
      tables: value.db_tables || [],
      tenant_columns_required: ["organization_id", "project_id"],
      stores_secret_values: false
    },
    event: {
      types: value.events || [],
      payload_policy: "metadata-only ids, hashes, statuses, counts, and artifact refs"
    },
    artifact: {
      types: value.artifacts || [],
      registry_required: true,
      export_redaction_required: true
    },
    tenant: {
      scope_fields: ["organization_id", "project_id", "environment_id", "release_id"],
      cross_tenant_default: "404_or_empty"
    },
    RBAC: {
      permissions: ["notifications:read", "notifications:configure", "notifications:test", "notifications:deliver"],
      configure_role: "organization_admin_or_project_admin",
      read_roles: ["reviewer", "auditor", "read-only viewer"],
      delivery_worker_role: "service_account:notification_delivery_worker"
    },
    usage: {
      meters: value.usage_meters || [],
      billing_mutations_enabled: false,
      billable_when: "A1 usage ledger marks delivery attempts authoritative"
    },
    audit: {
      events: value.audit_events || [],
      append_only_required: true,
      payload_policy: "ids, hashes, status codes, retry class, and artifact refs only"
    },
    dependencies: {
      A1: value.A1,
      A2: value.A2
    },
    safety: {
      secret_values_included: false,
      raw_provider_endpoint_included: false,
      raw_recipient_included: false,
      raw_message_body_included: false,
      provider_credentials_echoed: false,
      external_mutation_performed_locally: false
    },
    next_action: value.next_action
  };
}

function baseTables(extra = []) {
  return [
    "notification_channels",
    "notification_subscriptions",
    "notification_deliveries",
    "notification_delivery_attempts",
    "notification_preferences",
    "event_outbox",
    "audit_events",
    "usage_events",
    ...extra
  ];
}

function providerInput(inputs = {}, provider) {
  return inputs[provider]
    || inputs[`${provider}Notification`]
    || inputs[`${provider}_notification`]
    || inputs.providers?.[provider]
    || {};
}

function hasProviderMetadata(value) {
  if (!value || typeof value !== "object") {
    return false;
  }
  return Object.values(value).some((item) => {
    if (Array.isArray(item)) return item.length > 0;
    if (item && typeof item === "object") return Object.keys(item).length > 0;
    return item !== undefined && item !== null && String(item).trim() !== "";
  });
}

function nextActions(lanes = []) {
  return lanes
    .map((item) => item.next_action)
    .filter(Boolean)
    .slice(0, 4);
}

function channelProjection(lane = {}) {
  return {
    id: lane.id,
    provider: lane.provider,
    label: lane.label,
    status: lane.status,
    current_mode: lane.current_mode,
    api_routes: lane.api.routes,
    db_tables: lane.db.tables,
    event_types: lane.event.types,
    artifact_types: lane.artifact.types,
    tenant_scope_fields: lane.tenant.scope_fields,
    rbac_permissions: lane.RBAC.permissions,
    usage_meters: lane.usage.meters,
    audit_events: lane.audit.events,
    payload_fields: [
      "release_id",
      "release_gate_status",
      "review_record_id",
      "primary_failure_class",
      "policy_version",
      "artifact_refs",
      "delivery_id",
      "redaction_status"
    ],
    a1_dependency: lane.dependencies.A1,
    a2_dependency: lane.dependencies.A2,
    next_action: lane.next_action
  };
}

function triggerProjection(lane = {}) {
  return {
    label: `${lane.provider} trigger plan`,
    provider: lane.provider,
    lane_id: lane.id,
    channels: [lane.provider],
    triggers: lane.delivery_triggers,
    dashboard_state: lane.status,
    customer_value: lane.label,
    payload_fields: [
      "release_id",
      "release_gate_status",
      "primary_failure_class",
      "artifact_refs",
      "audit_event_id"
    ],
    event_contract: lane.event.types,
    delivery_worker: "A1 notification delivery worker",
    policy_owner: "A2 release and security policy",
    local_mutation_performed: false
  };
}

function buildGrowthPoints(lanes = []) {
  const basePoints = [
    gp("NC-01", "Slack blocked-release alert", ["revenue", "risk", "audit"], "slack"),
    gp("NC-02", "Slack reviewer SLA escalation", ["risk", "e2e", "review"], "slack"),
    gp("NC-03", "Slack usage quota alert", ["usage", "billing", "revenue"], "slack"),
    gp("NC-04", "Slack audit receipt readback", ["audit", "risk"], "slack"),
    gp("NC-05", "Teams blocked-release card", ["revenue", "risk", "audit"], "teams"),
    gp("NC-06", "Teams reviewer assignment card", ["review", "e2e"], "teams"),
    gp("NC-07", "Teams security policy escalation", ["risk", "audit"], "teams"),
    gp("NC-08", "Teams enterprise identity binding", ["rbac", "audit"], "teams"),
    gp("NC-09", "Email reviewer digest", ["review", "revenue"], "email"),
    gp("NC-10", "Email audit packet export notice", ["audit", "self-host"], "email"),
    gp("NC-11", "Email usage anomaly notice", ["usage", "billing", "risk"], "email"),
    gp("NC-12", "Email unsubscribe and privacy guard", ["risk", "audit"], "email"),
    gp("NC-13", "Customer webhook release blocked event", ["api", "revenue", "risk"], "webhook"),
    gp("NC-14", "Customer webhook release approved event", ["api", "e2e"], "webhook"),
    gp("NC-15", "Customer webhook bundle verified event", ["audit", "self-host"], "webhook"),
    gp("NC-16", "Customer webhook report shared event", ["revenue", "audit"], "webhook"),
    gp("NC-17", "Notification delivery usage ledger", ["usage", "billing", "revenue"], "all"),
    gp("NC-18", "Notification redaction receipt artifact", ["risk", "audit"], "all"),
    gp("NC-19", "Notification tenant/RBAC negative tests", ["rbac", "risk", "e2e"], "all"),
    gp("NC-20", "Notification replay and dead-letter evidence", ["audit", "self-host", "e2e"], "all")
  ];
  const providers = new Set(lanes.map((item) => item.provider));
  return basePoints.map((point) => ({
    ...point,
    priority: point.provider === "all" ? "P1" : "P2",
    surface: point.provider === "all" ? "all notification lanes" : point.provider,
    expected_artifact: "notification_delivery_receipt",
    status: point.provider === "all" || providers.has(point.provider)
      ? "contract_ready"
      : "waiting_for_lane",
    contract_surface: {
      api: ["GET /api/a3/notifications/control-plane", `POST /internal/notifications/${point.provider === "all" ? "webhook" : point.provider}/deliver`],
      db: ["notification_deliveries", "notification_delivery_attempts", "audit_events", "usage_events"],
      events: ["notification.delivery_planned", "notification.delivery_recorded"],
      artifacts: ["notification_delivery_receipt", "redaction_report"]
    }
  }));
}

function gp(id, title, dimensions, provider) {
  return {
    id,
    title,
    dimensions,
    provider,
    customer_value: "Makes release governance visible in the collaboration channel customers already operate.",
    sellable_claim: title
  };
}

function unique(items = []) {
  return [...new Set(items.filter((item) => item !== undefined && item !== null && String(item).trim() !== ""))];
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
