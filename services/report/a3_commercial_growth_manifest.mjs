import { createHash } from "node:crypto";

export const A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION = "a3.commercial_growth_manifest.v1";
export const A3_COMMERCIAL_GROWTH_MANIFEST_ID = "a3cgm_2026_07_09";
export const A3_COMMERCIAL_GROWTH_MANIFEST_GENERATED_AT = "2026-07-09T00:00:00.000Z";

export const REQUIRED_COMMERCIAL_GROWTH_DIMENSIONS = [
  "revenue",
  "risk",
  "audit",
  "self-host",
  "usage",
  "billing",
  "e2e"
];

const SECRET_VALUE_PATTERNS = [
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
  /\bghp_[A-Za-z0-9]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /Authorization:\s*Bearer\s+(?!\[REDACTED\])/i,
  /Cookie:\s*(?!\[REDACTED\])/i,
  /RELEASEFOUNDRY_API_KEY\s*=\s*(?!\[REDACTED\])/i,
  /C:\\Users\\/i
];

export function buildA3CommercialGrowthManifest(options = {}) {
  const growthPoints = DEFAULT_GROWTH_POINTS.map((point, index) => ({
    ...point,
    order: index + 1,
    dimensions: [...new Set(point.dimensions)],
    evidence_state: evidenceState(point.evidence_bindings)
  }));
  const body = {
    schema_version: A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION,
    manifest_id: options.manifestId || A3_COMMERCIAL_GROWTH_MANIFEST_ID,
    generated_at: options.generatedAt || A3_COMMERCIAL_GROWTH_MANIFEST_GENERATED_AT,
    source: options.source || "a3-local-commercial-evidence",
    tenant_scope: {
      organization_id: options.organizationId || "org-local",
      project_id: options.projectId || "project-local"
    },
    release_identity: {
      release_id: options.releaseId || "a3-commercial-growth-2026-07-09",
      branch: options.branch || "agent/a3-commercial-growth-round2",
      tracking_branch: options.trackingBranch || "origin/agent/a3-commercial-cl-gate",
      semantic_boundary: "A3 manifest only; A1 runner and A2 judge semantics are unchanged."
    },
    required_dimensions: REQUIRED_COMMERCIAL_GROWTH_DIMENSIONS,
    summary: {
      growth_point_count: growthPoints.length,
      dimensions: summarizeDimensions(growthPoints),
      evidence: summarizeEvidence(growthPoints),
      points_with_explicit_gaps: countPoints(growthPoints, "gaps"),
      points_with_a1_source: countPoints(growthPoints, "a1"),
      points_with_a2_source: countPoints(growthPoints, "a2"),
      points_with_a3_source: countPoints(growthPoints, "a3"),
      sellable_package: "Enforced Agent PR/CL Gate plus Release Evidence Authority plus Enterprise Audit Packet plus Identity-Bound Review Workflow"
    },
    contract: {
      api: [
        route("GET /api/a3/commercial-growth/manifest", "planned_contract", "tenant_reader_or_auditor"),
        route("GET /api/a3/releases/:releaseId/commercial-growth", "planned_contract", "release_reader"),
        route("POST /api/a3/commercial-growth/refresh", "plan_only_until_rbac", "admin_or_release_owner")
      ],
      db: [
        "commercial_growth_manifests",
        "commercial_growth_points",
        "commercial_growth_evidence_links",
        "commercial_growth_gap_events"
      ],
      events: [
        "commercial_growth.manifest_generated",
        "commercial_growth.point_recorded",
        "commercial_growth.gap_recorded",
        "commercial_growth.point_promoted",
        "commercial_growth.manifest_exported"
      ],
      artifacts: [
        "a3_commercial_growth_manifest.redacted.json",
        "p3_commercial_growth_manifest_2026_07_09.md",
        "release_evidence_summary",
        "report_center_manifest",
        "audit_bundle_index"
      ]
    },
    tenant_auth_rbac_usage_audit: {
      tenant: {
        required_scope_fields: ["organization_id", "project_id", "release_id"],
        cross_tenant_default: "404_or_empty",
        storage_policy: "tenant columns required before durable SaaS claim"
      },
      auth: {
        current_state: "local metadata only",
        required_before_live_refresh: ["hosted auth middleware", "service account identity", "nonce and timestamp replay defense"],
        live_credentials_stored: false
      },
      rbac: {
        roles: ["owner", "admin", "developer", "reviewer", "auditor", "billing_admin"],
        required_permissions: ["growth:read", "growth:refresh", "evidence:read", "audit:read", "usage:read"],
        enforcement_state: "planned until A1 auth middleware exists"
      },
      usage: {
        meter_candidates: ["growth_manifest_exports", "growth_point_promotions", "readback_checks", "audit_packet_exports"],
        billing_mutations_enabled: false,
        chargeback_state: "read_only_preview"
      },
      audit: {
        append_only_events_required: true,
        event_payload_policy: "ids, hashes, paths, statuses, and counts only",
        verifier_link: "audit_bundle_index"
      }
    },
    a1_a2_integration: {
      a1: {
        consumed_contracts: ["RunResult", "Trace", "ToolCall", "Observation", "WorkerDataModel", "SaaSControlPlane"],
        must_not_change: "A3 reads A1 evidence projections and does not alter runner behavior or A1 API semantics."
      },
      a2: {
        consumed_contracts: ["GradeResult", "ReleaseGate", "ScenarioSelection", "JudgeVersions", "CommercialReadiness", "CalibrationMatrix"],
        must_not_change: "A3 reads A2 outputs additively and does not alter judge scoring, thresholds, or release policy semantics."
      },
      a3: {
        downstream_only: true,
        role: "Bind A1/A2 evidence into report, gate, review, audit, usage, billing, and self-host contracts."
      }
    },
    growth_points: growthPoints,
    safety: {
      contains_secret_values: false,
      raw_tokens_allowed: false,
      raw_cookies_allowed: false,
      raw_api_keys_allowed: false,
      raw_signed_urls_allowed: false,
      local_absolute_paths_allowed: false,
      live_cloud_mutations_performed: false,
      fixture_output_path: "fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json"
    },
    acceptance: {
      node_test: "node --test tests/a3/a3_commercial_growth_manifest.test.mjs",
      fixture: "fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json",
      documentation: "docs/a3/p3_commercial_growth_manifest_2026_07_09.md",
      checklist: "docs/a3/acceptance_checklist.md"
    }
  };

  return {
    ...body,
    manifest_hash: sha256(stableJson(body))
  };
}

export function validateA3CommercialGrowthManifest(manifest = {}) {
  const errors = [];
  if (manifest.schema_version !== A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION) {
    errors.push("schema_version must be a3.commercial_growth_manifest.v1");
  }
  const points = Array.isArray(manifest.growth_points) ? manifest.growth_points : [];
  if (points.length < 20) {
    errors.push("manifest must contain at least 20 growth points");
  }
  const dimensions = new Set(points.flatMap((point) => point.dimensions || []));
  for (const dimension of REQUIRED_COMMERCIAL_GROWTH_DIMENSIONS) {
    if (!dimensions.has(dimension)) {
      errors.push(`missing required dimension: ${dimension}`);
    }
  }
  const ids = new Set();
  for (const point of points) {
    if (!point.id) {
      errors.push("growth point missing id");
      continue;
    }
    if (ids.has(point.id)) {
      errors.push(`duplicate growth point id: ${point.id}`);
    }
    ids.add(point.id);
    if (!hasEvidenceOrGap(point.evidence_bindings)) {
      errors.push(`${point.id} must bind A1/A2/A3 evidence or an explicit gap`);
    }
    if (!hasContractSurface(point.contract_surface)) {
      errors.push(`${point.id} must include API, DB, event, or artifact contract surface`);
    }
  }
  for (const leak of findPotentialSecretLeaks(manifest)) {
    errors.push(`potential secret leak: ${leak.pattern}`);
  }
  return { valid: errors.length === 0, errors };
}

export function findPotentialSecretLeaks(value) {
  const serialized = JSON.stringify(value);
  return SECRET_VALUE_PATTERNS
    .filter((pattern) => pattern.test(serialized))
    .map((pattern) => ({ pattern: pattern.source }));
}

function gp(id, title, dimensions, evidence_bindings, contract_surface, extras = {}) {
  return {
    id,
    title,
    dimensions,
    priority: extras.priority || "medium",
    maturity: extras.maturity || "contract_ready",
    sellable_claim: extras.sellable_claim || title,
    next_build: extras.next_build || "Promote this growth point from contract evidence to durable API, DB, event, and artifact proof.",
    customer_value: extras.customer_value || "Strengthens A3 as a commercial release-governance evidence product.",
    evidence_bindings: normalizeBindings(evidence_bindings),
    contract_surface: normalizeSurface(contract_surface)
  };
}

function src(path, contract, status = "available", source_type = "contract") {
  return { path, contract, status, source_type };
}

function gap(id, description, owner_lane, blocks_enterprise_claim = true) {
  return { id, description, owner_lane, blocks_enterprise_claim };
}

function route(routeName, status, auth) {
  return {
    route: routeName,
    status,
    auth,
    response_schema: A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION
  };
}

function normalizeBindings(value = {}) {
  return {
    a1: Array.isArray(value.a1) ? value.a1 : [],
    a2: Array.isArray(value.a2) ? value.a2 : [],
    a3: Array.isArray(value.a3) ? value.a3 : [],
    gaps: Array.isArray(value.gaps) ? value.gaps : []
  };
}

function normalizeSurface(value = {}) {
  return {
    api: Array.isArray(value.api) ? value.api : [],
    db: Array.isArray(value.db) ? value.db : [],
    events: Array.isArray(value.events) ? value.events : [],
    artifacts: Array.isArray(value.artifacts) ? value.artifacts : []
  };
}

function hasEvidenceOrGap(bindings = {}) {
  return ["a1", "a2", "a3", "gaps"].some((lane) => Array.isArray(bindings[lane]) && bindings[lane].length > 0);
}

function hasContractSurface(surface = {}) {
  return ["api", "db", "events", "artifacts"].some((lane) => Array.isArray(surface[lane]) && surface[lane].length > 0);
}

function evidenceState(bindings = {}) {
  const sourceCount = ["a1", "a2", "a3"].reduce((sum, lane) => sum + (bindings[lane] || []).length, 0);
  const gapCount = (bindings.gaps || []).length;
  if (sourceCount && gapCount) return "evidence_backed_with_gap";
  if (sourceCount) return "evidence_backed";
  return "gap_explicit";
}

function summarizeDimensions(points) {
  return Object.fromEntries([...new Set(points.flatMap((point) => point.dimensions))]
    .sort()
    .map((dimension) => [
      dimension,
      {
        count: points.filter((point) => point.dimensions.includes(dimension)).length,
        point_ids: points.filter((point) => point.dimensions.includes(dimension)).map((point) => point.id)
      }
    ]));
}

function summarizeEvidence(points) {
  return Object.fromEntries(["a1", "a2", "a3", "gaps"].map((lane) => [
    lane,
    {
      count: points.reduce((sum, point) => sum + point.evidence_bindings[lane].length, 0),
      point_ids: points.filter((point) => point.evidence_bindings[lane].length > 0).map((point) => point.id)
    }
  ]));
}

function countPoints(points, lane) {
  return points.filter((point) => point.evidence_bindings[lane].length > 0).length;
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

const DEFAULT_GROWTH_POINTS = [
  gp("CG-01", "GitHub Check readback worker", ["revenue", "risk", "audit", "e2e", "api"], {
    a2: [src("docs/a2/schemas/release_gate.schema.json", "a2.release_gate")],
    a3: [
      src("services/report/a3_release_evidence.mjs", "a3.release_evidence_summary.v2"),
      src("services/report/a3_readback_capture_cli.mjs", "a3.readback_capture_cli"),
      src("fixtures/a3/p3/a3_github_check_readback_confirmed.redacted.json", "a3.github_check_readback_receipt.v1")
    ],
    gaps: [gap("live_provider_worker", "Maintainer-approved live GitHub worker is future integration evidence.", "A3/GitHub")]
  }, {
    api: ["POST /api/a3/releases/:releaseId/readbacks"],
    db: ["release_evidence_readbacks"],
    events: ["release_evidence.readback_captured"],
    artifacts: ["release_evidence_readback", "github_check_run"]
  }, { priority: "high" }),

  gp("CG-02", "PR comment readback worker", ["revenue", "risk", "audit", "e2e", "api"], {
    a3: [
      src("services/report/a3_github_integration.mjs", "a3.github_pr_comment_publish_receipt.v1"),
      src("fixtures/a3/p3/a3_github_pr_comment_readback_confirmed.redacted.json", "a3.github_pr_comment_readback_receipt.v1")
    ],
    gaps: [gap("live_pr_comment_query", "Live PR comment query and provider readback remain future integration evidence.", "A3/GitHub")]
  }, {
    api: ["POST /api/a3/releases/:releaseId/readbacks"],
    db: ["release_evidence_readbacks", "audit_events"],
    events: ["release_evidence.readback_captured", "pr_comment.readback_stale"],
    artifacts: ["pr_comment_markdown", "release_evidence_readback"]
  }, { priority: "high" }),

  gp("CG-03", "Required branch-protection proof", ["revenue", "risk", "audit", "e2e"], {
    a3: [
      src("fixtures/a3/p3/a3_github_required_check_plan.redacted.json", "a3.github_required_check_plan.v1"),
      src("docs/a3/p3_pr_comment_required_check_plan_2026_07_08.md", "required-check plan-only documentation", "available", "doc")
    ],
    gaps: [gap("branch_protection_readback", "Plan-only evidence cannot prove branch protection enforcement.", "A3/GitHub")]
  }, {
    api: ["GET /api/a3/releases/:releaseId/required-check-proof"],
    db: ["release_evidence_readbacks"],
    events: ["required_check.proof_captured"],
    artifacts: ["github_required_check_proof"]
  }, { priority: "high", maturity: "gap_explicit" }),

  gp("CG-04", "Immutable release evidence authority", ["audit", "risk", "db", "e2e"], {
    a1: [src("docs/a1/schemas/run_result.schema.json", "A1 RunResult")],
    a2: [src("docs/a2/schemas/grade_results.schema.json", "A2 GradeResult")],
    a3: [src("services/report/a3_release_evidence.mjs", "a3.release_evidence_summary.v2")]
  }, {
    api: ["GET /api/a3/releases/:releaseId/evidence-summary", "GET /api/a3/releases/:releaseId/evidence-health"],
    db: ["release_evidence_summaries", "release_evidence_snapshots", "release_evidence_diffs"],
    events: ["release_evidence.snapshot_created", "release_evidence.diff_created"],
    artifacts: ["release_evidence_summary"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-05", "A1/A2 source snapshot ledger", ["audit", "risk", "db", "self-host"], {
    a1: [src("docs/a1/schemas/run_result.schema.json", "RunResult"), src("docs/a1/schemas/trace_event.schema.json", "TraceEvent")],
    a2: [src("docs/a2/schemas/grade_results.schema.json", "GradeResult"), src("docs/a2/schemas/release_policy.schema.json", "ReleasePolicy")],
    a3: [src("docs/a3/p3_a1_a2_release_evidence_v2_contract_map_2026_07_08.md", "A1/A2 release evidence v2 map", "available", "doc")],
    gaps: [gap("mandatory_source_hash_projection", "Not every A1/A2 source artifact is hash-linked into v2 authority rows yet.", "A3")]
  }, {
    api: ["POST /api/a3/import/a1-run-result", "POST /api/a3/import/a2-grade-result"],
    db: ["api_import_receipts", "idempotency_keys", "release_evidence_snapshots"],
    events: ["a1.imported", "a2.imported", "source_snapshot.created"],
    artifacts: ["source_snapshot_ledger", "api_import_receipt"]
  }, { priority: "high" }),

  gp("CG-06", "Report Center packet detail", ["revenue", "audit", "e2e", "api"], {
    a3: [
      src("services/report/a3_report_center_manifest.mjs", "a3.report_center_manifest.v1"),
      src("services/report/a3_artifact_registry.mjs", "a3.artifact_registry.v1"),
      src("docs/a3/p3_report_center_manifest_growth_2026_07_07.md", "Report Center manifest contract", "available", "doc")
    ]
  }, {
    api: ["GET /api/a3/report-center", "GET /api/a3/reports/:reportId/manifest"],
    db: ["shareable_reports", "report_share_links", "artifact_registry_entries"],
    events: ["report.snapshot_created", "report.manifest_generated"],
    artifacts: ["report_center_manifest", "hosted_report", "usage_ledger"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-07", "Artifact hash coverage for every customer packet", ["audit", "risk", "self-host"], {
    a3: [
      src("services/report/a3_artifact_registry.mjs", "a3.artifact_registry.v1"),
      src("fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json", "a3.generated_artifact_manifest.v1"),
      src("fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json", "a3.audit_bundle_index.v1")
    ],
    gaps: [gap("visual_artifact_hashes", "PDF, screenshot, and hosted HTML hashes are not universally covered yet.", "A3")]
  }, {
    api: ["GET /api/a3/artifacts/registry"],
    db: ["artifact_registry_entries", "artifact_lifecycle_events"],
    events: ["artifact.hash_recorded", "artifact.verified"],
    artifacts: ["generated_artifact_manifest", "audit_bundle_index", "audit_archive_manifest"]
  }, { priority: "high" }),

  gp("CG-08", "Universal export redaction firewall", ["risk", "audit", "e2e"], {
    a3: [
      src("services/report/export_redaction_firewall.mjs", "a3.export_redaction_firewall.v1"),
      src("tests/a3/export_firewall_generated_artifacts.test.mjs", "redaction firewall tests", "available", "test"),
      src("docs/a3/p3_redaction_firewall_evidence_map_2026_07_07.md", "redaction evidence map", "available", "doc")
    ],
    gaps: [gap("all_surface_enforcement", "Newer surfaces still need one universal publish gate.", "A3")]
  }, {
    api: ["POST /api/a3/reports/share"],
    db: ["redaction_scans", "artifact_registry_entries"],
    events: ["artifact.redaction_scanned", "artifact.redaction_blocked"],
    artifacts: ["export_redaction_firewall", "redaction_findings_log"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-09", "Hosted auth and tenant-bound RBAC", ["risk", "audit", "rbac", "self-host", "api"], {
    a1: [src("docs/a1/schemas/saas_control_plane.schema.json", "A1 SaaS control plane")],
    a3: [src("services/report/a3_saas_admin.mjs", "a3.saas_admin_console.v1")],
    gaps: [gap("hosted_auth_middleware", "Local tenant options are not hosted auth or RBAC enforcement.", "A1/A3")]
  }, {
    api: ["all /api/a3/* tenant routes"],
    db: ["users", "roles", "team_members", "api_keys", "audit_events"],
    events: ["auth.session_started", "rbac.denied", "audit.actor_bound"],
    artifacts: ["rbac_matrix", "auth_boundary_receipt"]
  }, { priority: "high", maturity: "gap_explicit" }),

  gp("CG-10", "Cross-tenant negative tests", ["risk", "audit", "e2e", "db"], {
    a3: [
      src("tests/a3/a3_api_server.test.mjs", "A3 API tenant-scope tests", "available", "test"),
      src("tests/a3/a3_sqlite_store.test.mjs", "SQLite tenant persistence tests", "available", "test")
    ],
    gaps: [gap("real_auth_negative_tests", "Real hosted auth/RBAC tenant tests are blocked until auth middleware exists.", "A1/A3")]
  }, {
    api: ["GET /api/a3/reports/:reportId", "GET /api/a3/releases/:releaseId/readbacks"],
    db: ["shareable_reports", "release_evidence_readbacks", "usage_ledger"],
    events: ["tenant_scope.denied"],
    artifacts: ["tenant_scope_negative_test_report"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-11", "Usage ledger event ids", ["usage", "billing", "revenue", "audit"], {
    a1: [src("docs/a1/schemas/worker_data_model.schema.json", "A1 worker usage model")],
    a3: [src("services/report/a3_usage_ledger.mjs", "a3.usage_ledger.v1"), src("services/report/a3_sql_migrations.mjs", "usage_ledger SQL contract")],
    gaps: [gap("append_only_usage_event_ids", "Meters exist, but all billable events are not durable append-only rows yet.", "A3")]
  }, {
    api: ["GET /api/a3/usage/ledger"],
    db: ["usage_ledger"],
    events: ["usage.recorded", "usage.adjustment_planned"],
    artifacts: ["usage_ledger"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-12", "Quota and chargeback preview", ["usage", "billing", "revenue", "risk"], {
    a3: [
      src("services/report/a3_saas_admin.mjs", "a3.saas_admin_console.v1"),
      src("fixtures/a3/p3/releasefoundry_usage_quota_sample.redacted.json", "redacted usage quota fixture")
    ],
    gaps: [gap("real_entitlements", "No billing or entitlement provider is wired; preview must stay read-only.", "A3/Billing")]
  }, {
    api: ["GET /api/a3/admin/console", "POST /api/a3/admin/actions/submit"],
    db: ["saas_admin_action_requests", "usage_ledger"],
    events: ["usage.quota_viewed", "admin_action.requested"],
    artifacts: ["saas_admin_guardrails", "usage_quota_snapshot"]
  }),

  gp("CG-13", "Billing export with explicit approval", ["billing", "revenue", "audit", "usage"], {
    a3: [
      src("services/report/a3_usage_ledger.mjs", "a3.usage_ledger.v1"),
      src("services/report/a3_review_workflow.mjs", "a3.approval_review.v1")
    ],
    gaps: [gap("billing_export_artifact", "No billing export artifact exists yet; live billing mutation remains out of scope.", "A3/Billing")]
  }, {
    api: ["POST /api/a3/billing/export-plan"],
    db: ["usage_ledger", "audit_events", "review_workflow_records"],
    events: ["billing_export.planned", "billing_export.approved", "billing_export.generated"],
    artifacts: ["billing_export_preview", "approval_record"]
  }, { maturity: "gap_explicit" }),

  gp("CG-14", "Self-host smoke package", ["self-host", "revenue", "risk", "e2e"], {
    a1: [
      src("infra/docker/docker-compose.self-host.yml", "A1 self-host compose scaffold"),
      src("docs/a1/self_host_runtime_scaffold.md", "A1 self-host runtime scaffold", "available", "doc")
    ],
    a3: [
      src("services/report/a3_enterprise_readiness.mjs", "a3.enterprise_readiness.v1"),
      src("docs/a3/p3_self_host_console_growth_2026_07_07.md", "A3 self-host console direction", "available", "doc")
    ],
    gaps: [gap("installable_package", "No single installable A3 self-host package with backup/restore proof exists yet.", "A3/Self-host")]
  }, {
    api: ["GET /api/a3/health", "GET /api/a3/self-host/status"],
    db: ["organizations", "projects", "artifact_registry_entries", "usage_ledger"],
    events: ["self_host.smoke_started", "self_host.smoke_passed"],
    artifacts: ["self_host_smoke_receipt", "offline_verifier_packet"]
  }, { priority: "high" }),

  gp("CG-15", "Postgres/RLS and object-storage custody", ["self-host", "db", "risk", "audit"], {
    a1: [src("docs/a1/schemas/a1_control_plane_postgres_migration.sql", "A1 Postgres migration contract")],
    a3: [src("services/report/a3_sql_migrations.mjs", "a3.sql_migration_plan.v1")],
    gaps: [gap("rls_apply_receipt", "Postgres/RLS and object-storage apply receipts are not present in local A3 evidence.", "A3/Self-host")]
  }, {
    api: ["GET /api/a3/storage/health"],
    db: ["all tenant-owned tables", "artifact_lifecycle_events"],
    events: ["storage.object_verified", "backup.verified", "restore.verified"],
    artifacts: ["storage_health_receipt", "backup_restore_receipt"]
  }, { priority: "high" }),

  gp("CG-16", "Offline verifier packet", ["self-host", "audit", "revenue", "risk"], {
    a3: [
      src("fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json", "a3.audit_bundle_verification.v1"),
      src("fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json", "a3.audit_archive_verification.v1"),
      src("services/report/a3_audit_archive.mjs", "a3.audit_archive_manifest.v1")
    ],
    gaps: [gap("single_packet_export", "Bundle/archive pieces exist, but one offline verifier packet route is not complete.", "A3")]
  }, {
    api: ["GET /api/a3/audit/packet/:packetId"],
    db: ["artifact_registry_entries", "artifact_lifecycle_events", "audit_events"],
    events: ["audit_packet.exported", "audit_packet.verified"],
    artifacts: ["audit_bundle_index", "audit_archive_manifest", "offline_verifier_packet"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-17", "Retention and legal hold workflow", ["audit", "risk", "self-host", "billing"], {
    a3: [
      src("docs/a3/p3_report_center_manifest_growth_2026_07_07.md", "retention fields in manifest contract", "available", "doc"),
      src("services/report/a3_artifact_registry.mjs", "retention_class registry field")
    ],
    gaps: [gap("retention_job", "No enforced retention/legal-hold job or purge receipt exists yet.", "A3/Self-host")]
  }, {
    api: ["POST /api/a3/artifacts/:artifactId/legal-hold", "POST /api/a3/artifacts/:artifactId/purge-plan"],
    db: ["artifact_registry_entries", "artifact_lifecycle_events", "usage_ledger"],
    events: ["retention.legal_hold_applied", "retention.purge_planned", "retention.purge_completed"],
    artifacts: ["retention_policy_receipt", "legal_hold_receipt"]
  }),

  gp("CG-18", "Identity-bound approvals", ["risk", "audit", "review", "rbac"], {
    a3: [
      src("services/report/a3_review_workflow.mjs", "a3.approval_review.v1"),
      src("fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json", "a3.approval.v1 fixture"),
      src("docs/a3/p3_signed_approval_validation_growth_2026_07_07.md", "signed approval growth doc", "available", "doc")
    ],
    gaps: [gap("real_actor_binding", "Approval signer is not backed by hosted identity/RBAC enforcement yet.", "A1/A3")]
  }, {
    api: ["POST /api/a3/reviews/approvals"],
    db: ["review_workflow_records", "audit_events"],
    events: ["approval.recorded", "approval.rejected", "approval.expired"],
    artifacts: ["approval_record", "approval_review"]
  }, { priority: "high" }),

  gp("CG-19", "Waiver expiry and remediation tracking", ["risk", "audit", "review"], {
    a3: [
      src("services/report/a3_review_workflow.mjs", "a3.waiver_review.v1"),
      src("fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json", "waiver review fixture"),
      src("docs/a3/p3_waiver_validation_growth_2026_07_07.md", "waiver validation growth doc", "available", "doc")
    ],
    gaps: [gap("issue_tracker_binding", "Follow-up issue tracker binding is not implemented.", "A3/Review")]
  }, {
    api: ["POST /api/a3/reviews/waivers"],
    db: ["review_workflow_records", "audit_events"],
    events: ["waiver.requested", "waiver.accepted", "waiver.expired"],
    artifacts: ["waiver_request", "waiver_review"]
  }),

  gp("CG-20", "Reviewer SLA and escalation", ["revenue", "risk", "review", "e2e"], {
    a3: [
      src("docs/a3/p3_reviewer_workflow_board_growth_2026_07_07.md", "reviewer workflow board contract", "available", "doc"),
      src("tests/a3/a3_review_workflow.test.mjs", "review workflow tests", "available", "test")
    ],
    gaps: [gap("notification_provider", "No notification or escalation provider is wired.", "A3/Review")]
  }, {
    api: ["GET /api/a3/reviews/board", "PATCH /api/a3/reviews/items/:itemId"],
    db: ["review_workflow_records", "audit_events"],
    events: ["review_item.assigned", "review_item.escalated", "review_item.resolved"],
    artifacts: ["reviewer_board", "pr_comment_markdown"]
  }),

  gp("CG-21", "Production trace ingestion API", ["api", "revenue", "risk", "e2e"], {
    a1: [src("docs/a1/schemas/trace_event.schema.json", "TraceEvent"), src("docs/a1/schemas/observation.schema.json", "Observation")],
    a3: [src("docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md", "observability replay matrix", "available", "doc")],
    gaps: [gap("production_trace_import_route", "A3 does not expose a production trace ingestion route yet.", "A3/API")]
  }, {
    api: ["POST /api/a3/traces/import", "GET /api/a3/traces/:traceId"],
    db: ["trace_events", "tool_calls", "api_import_receipts"],
    events: ["trace.imported", "trace.validation_failed"],
    artifacts: ["trace_ingestion_receipt"]
  }, { priority: "high", maturity: "gap_explicit" }),

  gp("CG-22", "Replay pack and runner receipts", ["revenue", "risk", "e2e", "audit"], {
    a1: [src("docs/a1/schemas/trace_event.schema.json", "TraceEvent")],
    a2: [src("docs/a2/schemas/regression_replay.schema.json", "A2 regression replay")],
    a3: [
      src("docs/a3/p3_incident_replay_queue_growth_2026_07_07.md", "incident replay queue contract", "available", "doc"),
      src("docs/a3/p3_regression_factory_growth_2026_07_07.md", "regression factory contract", "available", "doc")
    ],
    gaps: [gap("executable_replay_runner", "Replay queue exists as evidence/workflow, but production runner receipt is future work.", "A3")]
  }, {
    api: ["POST /api/a3/replay-packs", "POST /api/a3/replay-packs/:packId/receipts"],
    db: ["artifact_registry_entries", "audit_events", "usage_ledger"],
    events: ["replay_pack.generated", "replay.receipt_recorded"],
    artifacts: ["replay_pack", "replay_runner_receipt"]
  }, { priority: "high" }),

  gp("CG-23", "Judge calibration and drift in gate health", ["risk", "audit", "e2e"], {
    a2: [
      src("fixtures/a2/results/a2_g3_calibration_matrix.json", "a2.calibration_matrix.v1"),
      src("fixtures/a2/results/a2_judge_versions.json", "a2.judge_versions.v1")
    ],
    a3: [src("services/report/a3_release_evidence.mjs", "release evidence health")],
    gaps: [gap("live_drift_monitor", "No live judge drift monitor is wired into A3 gate health.", "A2/A3")]
  }, {
    api: ["GET /api/a3/releases/:releaseId/evidence-health"],
    db: ["release_evidence_snapshots"],
    events: ["judge_calibration.linked", "judge_drift.detected"],
    artifacts: ["calibration_matrix", "judge_version_registry", "release_evidence_summary"]
  }),

  gp("CG-24", "Versioned A3 OpenAPI and webhooks", ["api", "revenue", "e2e", "audit"], {
    a2: [src("docs/a2/openapi/a2_judge_service.openapi.json", "A2 OpenAPI precedent")],
    a3: [src("services/report/a3_api_server.mjs", "A3 local API routes")],
    gaps: [gap("a3_openapi_file", "No versioned A3 OpenAPI artifact is committed yet.", "A3/API")]
  }, {
    api: ["docs/a3/openapi/a3_release_governance.openapi.json"],
    db: ["audit_events", "idempotency_keys"],
    events: ["webhook.delivery_planned", "webhook.delivery_failed"],
    artifacts: ["openapi_contract", "webhook_schema"]
  }, { maturity: "gap_explicit" }),

  gp("CG-25", "SaaS admin action-request audit path", ["risk", "audit", "rbac", "api"], {
    a3: [
      src("services/report/a3_saas_admin.mjs", "a3.saas_admin_action_request.v1"),
      src("services/report/a3_sql_migrations.mjs", "saas_admin_action_requests SQL contract"),
      src("docs/a3/p3_saas_admin_action_requests_2026_07_08.md", "admin action request doc", "available", "doc")
    ],
    gaps: [gap("hosted_rbac_for_admin_actions", "Action requests are not authorized by real hosted RBAC yet.", "A1/A3")]
  }, {
    api: ["POST /api/a3/admin/actions/submit", "GET /api/a3/admin/actions"],
    db: ["saas_admin_action_requests", "audit_events"],
    events: ["admin_action.requested", "admin_action.blocked", "admin_action.reviewed"],
    artifacts: ["saas_admin_action_request_summary"]
  }),

  gp("CG-26", "Hosted report share gating by health", ["revenue", "risk", "audit", "e2e"], {
    a3: [
      src("services/report/a3_shareable_report.mjs", "a3.shareable_report.v1"),
      src("services/report/a3_report_center.mjs", "Report Center lifecycle"),
      src("tests/a3/shareable_report.test.mjs", "hosted report redaction tests", "available", "test")
    ],
    gaps: [gap("external_auth_mode", "External auth-required hosted report mode is not production-wired.", "A1/A3")]
  }, {
    api: ["POST /api/a3/reports/share", "GET /r/:shareToken"],
    db: ["shareable_reports", "report_share_links", "report_view_events"],
    events: ["report.share_link_created", "report.share_link_viewed", "report.share_link_revoked", "report.share_blocked"],
    artifacts: ["hosted_report", "release_evidence_summary", "report_center_manifest"]
  }, { priority: "high", maturity: "local_evidence_ready" }),

  gp("CG-27", "Customer evidence packet presets", ["revenue", "audit", "self-host", "usage"], {
    a3: [
      src("services/report/a3_artifact_registry.mjs", "packet_presets"),
      src("docs/a3/p3_growth_auditor_artifact_registry_2026_07_07.md", "artifact registry packet presets", "available", "doc")
    ],
    gaps: [gap("one_click_packet_api", "Packet presets are modeled but no packet build endpoint exists.", "A3")]
  }, {
    api: ["POST /api/a3/packets/:presetId/build"],
    db: ["artifact_registry_entries", "usage_ledger", "audit_events"],
    events: ["packet.build_requested", "packet.generated", "usage.recorded"],
    artifacts: ["pr_review_packet", "security_audit_packet", "customer_safe_packet"]
  }),

  gp("CG-28", "Commercial CL gate selector visibility", ["risk", "audit", "e2e"], {
    a1: [src("docs/a1/schemas/evidence_index.schema.json", "A1 evidence index anchor")],
    a2: [src("docs/a2/schemas/commercial_readiness.schema.json", "A2 commercial readiness anchor")],
    a3: [
      src("scripts/cl_guard.py", "commercial anchor gate"),
      src("docs/a3/p3_cl_gate_a1_a2_contract_alignment_2026_07_09.md", "CL contract alignment doc", "available", "doc")
    ],
    gaps: [gap("manifest_specific_cl_selector", "The CL guard does not inspect this manifest schema directly yet.", "A3/CL")]
  }, {
    events: ["cl_gate.commercial_checked"],
    artifacts: ["cl_gate_plan", "commercial_growth_manifest"]
  }),

  gp("CG-29", "Current visual E2E evidence lane", ["e2e", "risk", "revenue"], {
    a3: [
      src("tests/a3/dashboard_wiring.test.mjs", "dashboard wiring smoke", "available", "test"),
      src("docs/screenshots/a3-dashboard-release-war-room.png", "existing dashboard screenshot evidence", "available", "screenshot"),
      src("docs/a3/p3_cl_gate_typescript_playwright_gap_2026_07_09.md", "Playwright gap doc", "available", "doc")
    ],
    gaps: [gap("playwright_ts_lane", "Playwright TS E2E lane is advisory until the toolchain exists.", "A3/E2E")]
  }, {
    api: ["GET /api/a3/dashboard", "GET /r/:shareToken"],
    db: ["report_view_events"],
    events: ["visual_e2e.screenshot_captured", "visual_e2e.leak_scan_passed"],
    artifacts: ["dashboard_screenshot", "hosted_report_screenshot", "mobile_screenshot"]
  })
];
