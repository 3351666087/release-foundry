import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const A3_SCHEMA_DRIFT_RADAR_VERSION = "a3.a1_a2_schema_drift_radar.v1";
export const A3_A1_A2_INTEGRATION_MATRIX_VERSION = "a3.a1_a2_integration_matrix.v1";

const REPO_ROOT = resolve(fileURLToPath(new URL("../../", import.meta.url)));

export const A3_A1_A2_SCHEMA_CONTRACTS = [
  contract("a1_run_result", "A1", "docs/a1/schemas/run_result.schema.json", [
    "run_id",
    "dataset_id",
    "runner_id",
    "status",
    "total_cases",
    "passed",
    "failed",
    "trace_completeness",
    "cases",
    "aggregate_metrics",
    "metadata",
    "field_map_version"
  ], {
    requiredConst: [["properties.aggregate_metrics.properties.schema_version.const", "ashr.clone.run_result.v1"]],
    a3Surfaces: ["run_list", "case_detail", "usage_ledger", "release_evidence", "report_export"]
  }),
  contract("a1_case_result", "A1", "docs/a1/schemas/case_result.schema.json", [
    "case_id",
    "scenario_id",
    "title",
    "status",
    "started_at",
    "ended_at",
    "observations",
    "grade",
    "agent_output",
    "expected",
    "metadata"
  ], {
    a3Surfaces: ["case_detail", "expected_vs_actual", "tool_call_diff", "media_evidence"]
  }),
  contract("a1_trace_event", "A1", "docs/a1/schemas/trace_event.schema.json", [
    "schema",
    "type",
    "event_type",
    "run_id",
    "event_id",
    "seq",
    "phase",
    "source",
    "observation"
  ], {
    requiredConst: [
      ["properties.schema.const", "ashr.clone.trace.v1"],
      ["properties.type.const", "trace_event"]
    ],
    nestedRequired: [["properties.observation", ["kind", "channel", "status", "text", "data"]]],
    a3Surfaces: ["trace_timeline", "tool_call_diff", "incident_replay", "observability_replay"]
  }),
  contract("a1_observation", "A1", "docs/a1/schemas/observation.schema.json", [
    "observation_id",
    "run_id",
    "case_id",
    "turn_index",
    "event_type",
    "role",
    "started_at",
    "ended_at",
    "status",
    "metadata"
  ], {
    a3Surfaces: ["trace_timeline", "tool_call_diff", "review_workflow"]
  }),
  contract("a2_grade_results", "A2", "docs/a2/schemas/grade_results.schema.json", [
    "schema_version",
    "report_id",
    "dataset_id",
    "scenario_pack",
    "total_cases",
    "passed",
    "failed",
    "grade_results"
  ], {
    requiredConst: [["properties.schema_version.const", "a2.grade_results.v1"]],
    nestedRequired: [
      ["$defs.local_judge_run", ["schema_version", "scenario_id", "case_id", "passed", "score", "primary_failure_class", "judge_results"]],
      ["$defs.grade_result", ["schema_version", "scenario_id", "case_id", "judge_mode", "judge_version", "passed", "score", "max_score", "rubric_scores", "failure_analysis", "evidence", "metadata"]],
      ["$defs.failure_analysis", ["schema_version", "primary_failure_class", "failure_classes", "severity", "summary", "details", "remediation", "safety_blocking"]]
    ],
    enumPath: "$defs.failure_class.enum",
    enumMustInclude: [
      "none",
      "wrong_intent",
      "missing_required_tool",
      "wrong_arguments",
      "unsafe_or_policy_violation"
    ],
    a3Surfaces: ["failure_cluster", "release_gate", "review_workflow", "billing_usage", "report_export"]
  }),
  contract("a2_release_gate", "A2", "docs/a2/schemas/release_gate.schema.json", [
    "schema_version",
    "report_id",
    "release_candidate",
    "decision",
    "exit_code",
    "risk_score",
    "hard_gate_ids",
    "current_commercial_gate",
    "ready_for_commercial_gate",
    "blockers",
    "warnings",
    "required_evidence",
    "pr_annotations",
    "review_workflow",
    "machine_contract",
    "evidence_refs",
    "metadata"
  ], {
    requiredConst: [["properties.schema_version.const", "a2.release_gate.v1"]],
    enumPath: "properties.decision.enum",
    enumMustInclude: ["pass", "warn", "block"],
    nestedRequired: [
      ["$defs.required_evidence", ["source", "required_count", "current_available", "private_input_ref", "collection_packet_ref", "commands"]],
      ["$defs.pr_annotation", ["level", "title", "message", "evidence_refs"]]
    ],
    a3Surfaces: ["release_war_room", "github_pr_gate", "review_workflow", "audit_export"]
  }),
  contract("a2_result_persistence_manifest", "A2", "docs/a2/schemas/result_persistence_manifest.schema.json", [
    "schema_version",
    "manifest_id",
    "tenant_id",
    "org",
    "project",
    "run",
    "dataset_id",
    "created_at",
    "source_refs",
    "record_count",
    "record_type_counts",
    "metadata",
    "records"
  ], {
    a3Surfaces: ["report_export", "audit_export", "artifact_registry"]
  }),
  contract("a2_release_unblock_checklist", "A2", "docs/a2/schemas/release_unblock_checklist.schema.json", [
    "schema_version",
    "checklist_id",
    "source_release_gate",
    "overall_status",
    "release_gate_decision",
    "gate_items",
    "a3_consumption_summary"
  ], {
    a3Surfaces: ["review_workflow", "release_war_room", "report_export"]
  })
];

export const A3_A1_A2_INTEGRATION_ARTIFACTS = [
  integrationArtifact("a1_route_scope_and_quota", "A1", "runtime", "docs/a1/evidence/go_route_scope_docs.json", {
    expectedSchema: "ashr.clone.go_route_scope_docs_artifact.v1",
    requiredPaths: ["route_scope_docs.route_groups", "route_scope_docs.plan_limits", "route_scope_docs.plan_metrics"],
    expectedValues: [["public_safe", true], ["raw_payloads_included", false]],
    a3Surfaces: ["saas_runtime", "usage_billing", "api_key_admin"],
    a3Action: "Render route scopes and plan limits read-only; A1 remains authoritative for enforcement.",
    summarize: summarizeRouteScope
  }),
  integrationArtifact("a1_billing_ledger", "A1", "billing", "docs/a1/schemas/a1_billing_ledger_migration_manifest.json", {
    expectedSchema: "ashr.clone.a1_billing_ledger_migration_manifest.v1",
    requiredPaths: ["tables", "providers", "ledger_event_types", "semantic_contracts"],
    a3Surfaces: ["billing_migration", "collections", "usage_billing"],
    a3Action: "Consume A1 ledger summaries and migration evidence without enabling A3 billing mutations.",
    summarize: summarizeBillingLedger
  }),
  integrationArtifact("a1_payment_provider_readiness", "A1", "payments", "docs/a1/evidence/payment_provider_readiness_public.json", {
    expectedSchema: "ashr.clone.a1.payment_provider_readiness.v1",
    requiredPaths: ["providers", "provider_mode_matrix", "payment_call_policy"],
    expectedValues: [["public_safe", true], ["payment_call_policy.provider_called", false], ["payment_call_policy.real_charge_possible", false]],
    a3Surfaces: ["billing_admin", "procurement", "trust_center"],
    a3Action: "Show WeChat Pay and Alipay first while keeping provider execution human-controlled and outside A3.",
    summarize: summarizePaymentReadiness
  }),
  integrationArtifact("a1_object_storage", "A1", "evidence_storage", "docs/a1/evidence/object_storage_contract_20260709.md", {
    format: "text",
    requiredAnchors: ["ashr.clone.object_storage.v1", "local-filesystem", "s3-compatible", "sha256"],
    a3Surfaces: ["media_evidence", "report_center", "audit_bundle"],
    a3Action: "Reference signed object manifests in reports; never embed payload bytes, endpoints, or storage credentials.",
    summarize: () => ({ backends: 2, signed_manifests: true, live_object_readback_observed: false })
  }),
  integrationArtifact("a2_cross_lane_security", "A2", "security", "fixtures/a2/results/a2_cross_lane_security_context.json", {
    expectedSchema: "a2.cross_lane_security_context.v1",
    requiredPaths: ["a1_route_scope", "a3_auth_rbac_boundary", "a2_policy_implications", "a2_security_followups"],
    a3Surfaces: ["auth_rbac", "release_gate", "audit_timeline"],
    a3Action: "Keep hosted mutations fail-closed and surface A2 security policy blockers beside A1 route scope.",
    summarize: summarizeCrossLaneSecurity
  }),
  integrationArtifact("a2_sql_evaluation_store", "A2", "evaluation_storage", "fixtures/a2/results/a2_sql_store_report.json", {
    expectedSchema: "a2.sql_store_report.v1",
    requiredPaths: ["database", "table_counts", "write_counts", "query_checks"],
    a3Surfaces: ["case_history", "failure_clusters", "report_export"],
    a3Action: "Read A2 evaluation history through a stable adapter; production Postgres ownership remains with A1.",
    summarize: summarizeSqlStore
  }),
  integrationArtifact("a2_scenario_generation", "A2", "scenario_growth", "fixtures/a2/results/a2_scenario_generation_backlog.json", {
    expectedSchema: "a2.scenario_generation_backlog.v1",
    requiredPaths: ["candidate_count", "candidates", "promotion_gate", "gap_signals"],
    a3Surfaces: ["regression_factory", "coverage_health", "release_war_room"],
    a3Action: "Display candidates and blockers, but require A2 owner review before promoting any scenario into the main pack.",
    summarize: summarizeScenarioBacklog
  })
];

export async function buildA1A2SchemaDriftRadar(options = {}) {
  const repoRoot = resolve(options.repoRoot || REPO_ROOT);
  const contracts = await Promise.all((options.contracts || A3_A1_A2_SCHEMA_CONTRACTS)
    .map((definition) => inspectSchemaContract(definition, repoRoot)));
  const integrationMatrix = await buildIntegrationMatrix(
    options.integrationArtifacts || A3_A1_A2_INTEGRATION_ARTIFACTS,
    repoRoot
  );
  const missing = contracts.filter((item) => item.status === "missing");
  const drifted = contracts.filter((item) => item.status === "drift_detected");
  const pass = contracts.filter((item) => item.status === "compatible");
  const status = missing.length || drifted.length || integrationMatrix.status !== "aligned" ? "needs_attention" : "compatible";
  return {
    schema_version: A3_SCHEMA_DRIFT_RADAR_VERSION,
    status,
    generated_at: options.generatedAt || "2026-07-09T00:00:00.000Z",
    repo_ref: options.repoRef || "local-worktree",
    compared_against: options.comparedAgainst || "docs/a1/schemas + docs/a2/schemas",
    contract_count: contracts.length,
    compatible_count: pass.length,
    drift_count: drifted.length,
    missing_count: missing.length,
    contracts,
    integration_matrix: integrationMatrix,
    a3_action: status === "compatible"
      ? "A3 can consume current A1/A2 schemas and public-safe commercial artifacts through the mapped read-only surfaces."
      : "Review A1/A2 schema or artifact changes before merging A3 report, dashboard, and release-gate changes.",
    a1_a2_boundary: "Radar validates consumer compatibility only; it does not modify A1 runner semantics or A2 judge semantics.",
    safety: {
      raw_schema_payload_embedded: false,
      schema_hashes_only: true,
      raw_secret_values_allowed: false,
      local_paths_public_safe: true
    }
  };
}

async function buildIntegrationMatrix(definitions, repoRoot) {
  const domains = await Promise.all(definitions.map((definition) => inspectIntegrationArtifact(definition, repoRoot)));
  const aligned = domains.filter((item) => item.status === "aligned");
  const a1 = domains.filter((item) => item.source_lane === "A1");
  const a2 = domains.filter((item) => item.source_lane === "A2");
  const byId = Object.fromEntries(domains.map((item) => [item.integration_id, item]));
  const scenarioCount = numberOr(byId.a2_scenario_generation?.public_summary?.candidate_count, 0);
  const sqlRows = numberOr(byId.a2_sql_evaluation_store?.public_summary?.judge_result_rows, 0);
  const status = aligned.length === domains.length ? "aligned" : "needs_attention";

  return {
    schema_version: A3_A1_A2_INTEGRATION_MATRIX_VERSION,
    status,
    domain_count: domains.length,
    aligned_domain_count: aligned.length,
    attention_domain_count: domains.length - aligned.length,
    a1_domain_count: a1.length,
    a2_domain_count: a2.length,
    domains,
    bridges: [
      bridge("runtime_to_judge", "A1 runtime -> A2 judge -> A3 release console", ["a1_route_scope_and_quota", "a2_cross_lane_security", "a2_scenario_generation"], "release_war_room"),
      bridge("evidence_to_report", "A1 object evidence -> A2 evaluation history -> A3 report", ["a1_object_storage", "a2_sql_evaluation_store"], "report_center"),
      bridge("billing_to_signoff", "A1 billing ledger -> A2 policy -> A3 commercial sign-off", ["a1_billing_ledger", "a1_payment_provider_readiness", "a2_cross_lane_security"], "billing_admin")
    ],
    commercial_summary: {
      china_payment_contract_ready: includesAll(byId.a1_payment_provider_readiness?.public_summary?.providers, ["wechat_pay", "alipay"]),
      object_storage_contract_ready: byId.a1_object_storage?.status === "aligned",
      durable_eval_store_ready: byId.a2_sql_evaluation_store?.status === "aligned" && sqlRows > 0,
      scenario_candidate_count: scenarioCount,
      live_payment_call_observed: false,
      live_object_storage_readback_observed: false,
      main_scenario_pack_mutated_by_a3: false
    },
    top_actions: status === "aligned"
      ? [
          "Promote A2 scenario candidates only after A2 review and executable fixture evidence.",
          "Attach A1 signed object-manifest references to A3 reports without embedding payloads.",
          "Keep WeChat Pay and Alipay customer-facing posture contract-only until A1 hosted auth and provider operations are live."
        ]
      : domains.filter((item) => item.status !== "aligned").slice(0, 3).map((item) => item.a3_action),
    ownership_boundary: "A1 owns runtime, route, billing, payment, quota, and object-storage authority. A2 owns scenarios, judge policy, security implications, and evaluation persistence. A3 reads and presents those outputs without mutating their semantics.",
    safety: {
      raw_artifact_payload_embedded: false,
      content_hashes_only: true,
      secret_values_allowed: false,
      external_mutations_performed: false
    }
  };
}

async function inspectIntegrationArtifact(definition, repoRoot) {
  const absolutePath = resolve(repoRoot, definition.path);
  let text = "";
  try {
    text = await readFile(absolutePath, "utf8");
  } catch (error) {
    return integrationResult(definition, {
      status: "missing",
      findings: [finding("missing_integration_artifact", "blocking", `Integration artifact is missing: ${definition.path}`)]
    });
  }

  if (definition.format === "text") {
    const findings = (definition.requiredAnchors || [])
      .filter((anchor) => !text.includes(anchor))
      .map((anchor) => finding("missing_artifact_anchor", "blocking", `Required public-safe anchor is missing: ${anchor}`, { anchor }));
    return integrationResult(definition, {
      status: findings.length ? "needs_attention" : "aligned",
      contentHash: sha256(text),
      publicSummary: definition.summarize?.(text) || {},
      findings
    });
  }

  let payload = {};
  try {
    payload = JSON.parse(text);
  } catch (error) {
    return integrationResult(definition, {
      status: "needs_attention",
      contentHash: sha256(text),
      findings: [finding("invalid_integration_json", "blocking", "Integration artifact is not valid JSON.")]
    });
  }

  const findings = [];
  if (definition.expectedSchema && payload.schema_version !== definition.expectedSchema) {
    findings.push(finding("integration_schema_mismatch", "blocking", `Expected ${definition.expectedSchema}.`, {
      expected: definition.expectedSchema,
      actual: payload.schema_version || null
    }));
  }
  for (const path of definition.requiredPaths || []) {
    const value = getPath(payload, path);
    if (value === undefined || value === null || (Array.isArray(value) && value.length === 0)) {
      findings.push(finding("missing_integration_field", "blocking", `Required integration field is missing: ${path}`, { path }));
    }
  }
  for (const [path, expected] of definition.expectedValues || []) {
    const actual = getPath(payload, path);
    if (actual !== expected) {
      findings.push(finding("integration_value_mismatch", "blocking", `${path} does not match the public-safe contract.`, { path, expected, actual: actual ?? null }));
    }
  }
  return integrationResult(definition, {
    status: findings.length ? "needs_attention" : "aligned",
    contentHash: sha256(text),
    sourceSchemaVersion: payload.schema_version || null,
    publicSummary: definition.summarize?.(payload) || {},
    findings
  });
}

function integrationResult(definition, result = {}) {
  return {
    integration_id: definition.id,
    source_lane: definition.sourceLane,
    domain: definition.domain,
    path: definition.path,
    status: result.status || "aligned",
    source_schema_version: result.sourceSchemaVersion || definition.expectedSchema || null,
    content_hash: result.contentHash || null,
    hash_algorithm: "sha256",
    required_by_a3_surfaces: definition.a3Surfaces,
    a3_action: definition.a3Action,
    public_summary: result.publicSummary || {},
    finding_count: (result.findings || []).length,
    findings: result.findings || [],
    raw_artifact_payload_embedded: false
  };
}

function integrationArtifact(id, sourceLane, domain, path, options = {}) {
  return {
    id,
    sourceLane,
    domain,
    path,
    format: options.format || "json",
    expectedSchema: options.expectedSchema || null,
    requiredPaths: options.requiredPaths || [],
    expectedValues: options.expectedValues || [],
    requiredAnchors: options.requiredAnchors || [],
    a3Surfaces: options.a3Surfaces || [],
    a3Action: options.a3Action || "Review the upstream artifact before expanding A3 claims.",
    summarize: options.summarize
  };
}

function bridge(id, label, evidenceIds, a3Surface) {
  return {
    bridge_id: id,
    label,
    evidence_ids: evidenceIds,
    a3_surface: a3Surface
  };
}

function summarizeRouteScope(payload = {}) {
  const docs = payload.route_scope_docs || {};
  return {
    route_group_count: (docs.route_groups || []).length,
    plan_count: (docs.plan_limits || []).length,
    plan_metric_count: (docs.plan_metrics || []).length,
    public_safe: payload.public_safe === true
  };
}

function summarizeBillingLedger(payload = {}) {
  return {
    table_count: (payload.tables || []).length,
    providers: payload.providers || [],
    ledger_event_type_count: (payload.ledger_event_types || []).length,
    real_provider_call_observed: false
  };
}

function summarizePaymentReadiness(payload = {}) {
  return {
    providers: (payload.providers || []).map((item) => item.provider).filter(Boolean),
    provider_called: payload.payment_call_policy?.provider_called === true,
    real_charge_possible: payload.payment_call_policy?.real_charge_possible === true,
    public_safe: payload.public_safe === true
  };
}

function summarizeCrossLaneSecurity(payload = {}) {
  return {
    route_count: numberOr(payload.a1_route_scope?.route_count, 0),
    tenant_route_count: numberOr(payload.a1_route_scope?.tenant_route_count, 0),
    hosted_auth_required: payload.a3_auth_rbac_boundary?.hosted_auth_required_before_live_saas === true,
    fail_closed_writes_required: payload.a2_policy_implications?.should_require_fail_closed_a3_writes === true
  };
}

function summarizeSqlStore(payload = {}) {
  const tableCounts = payload.table_counts || {};
  return {
    database_engine: payload.database?.engine || "unknown",
    table_count: Object.keys(tableCounts).length,
    judge_result_rows: numberOr(tableCounts.a2_judge_results, 0),
    golden_case_rows: numberOr(tableCounts.a2_golden_cases, 0),
    case_history_join_ready: payload.query_checks?.can_join_case_level_history === true
  };
}

function summarizeScenarioBacklog(payload = {}) {
  return {
    candidate_count: numberOr(payload.candidate_count, 0),
    policy_experiment_count: numberOr(payload.policy_experiment_count, 0),
    promotion_status: payload.promotion_gate?.status || "unknown",
    main_pack_mutation_allowed: payload.promotion_gate?.may_mutate_main_pack === true,
    media_candidate_pressure: numberOr(payload.gap_signals?.environment_pressure?.media_or_multimodal_count, 0)
  };
}

function includesAll(values, expected) {
  const set = new Set(Array.isArray(values) ? values : []);
  return expected.every((value) => set.has(value));
}

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

async function inspectSchemaContract(definition, repoRoot) {
  const absolutePath = resolve(repoRoot, definition.path);
  let text = "";
  try {
    text = await readFile(absolutePath, "utf8");
  } catch (error) {
    return contractResult(definition, {
      status: "missing",
      contentHash: null,
      findings: [finding("missing_schema_file", "blocking", `Schema file is missing: ${definition.path}`)]
    });
  }

  let schema = {};
  try {
    schema = JSON.parse(text);
  } catch (error) {
    return contractResult(definition, {
      status: "drift_detected",
      contentHash: sha256(text),
      findings: [finding("invalid_json_schema", "blocking", "Schema file is not valid JSON.")]
    });
  }

  const findings = [
    ...missingRequiredFields(schema, definition.requiredFields),
    ...missingNestedRequiredFields(schema, definition.nestedRequired),
    ...mismatchedConstFields(schema, definition.requiredConst),
    ...missingEnumValues(schema, definition.enumPath, definition.enumMustInclude)
  ];
  return contractResult(definition, {
    status: findings.some((item) => item.severity === "blocking") ? "drift_detected" : "compatible",
    contentHash: sha256(text),
    schemaTitle: schema.title || null,
    declaredRequired: Array.isArray(schema.required) ? schema.required : [],
    findings
  });
}

function contractResult(definition, result = {}) {
  return {
    schema_contract_id: definition.id,
    source_lane: definition.sourceLane,
    path: definition.path,
    status: result.status || "compatible",
    schema_title: result.schemaTitle || null,
    content_hash: result.contentHash,
    hash_algorithm: "sha256",
    required_fields: definition.requiredFields,
    declared_required_fields: result.declaredRequired || [],
    required_by_a3_surfaces: definition.a3Surfaces,
    finding_count: (result.findings || []).length,
    findings: result.findings || [],
    raw_schema_payload_embedded: false
  };
}

function contract(id, sourceLane, path, requiredFields, options = {}) {
  return {
    id,
    sourceLane,
    path,
    requiredFields,
    nestedRequired: options.nestedRequired || [],
    requiredConst: options.requiredConst || [],
    enumPath: options.enumPath || null,
    enumMustInclude: options.enumMustInclude || [],
    a3Surfaces: options.a3Surfaces || []
  };
}

function missingRequiredFields(schema = {}, fields = []) {
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  return fields
    .filter((field) => !required.has(field))
    .map((field) => finding("missing_required_field", "blocking", `Root required field is missing: ${field}`, { field }));
}

function missingNestedRequiredFields(schema = {}, checks = []) {
  const findings = [];
  for (const [path, fields] of checks || []) {
    const node = getPath(schema, path);
    const required = new Set(Array.isArray(node?.required) ? node.required : []);
    for (const field of fields || []) {
      if (!required.has(field)) {
        findings.push(finding("missing_nested_required_field", "blocking", `${path} is missing required field: ${field}`, { path, field }));
      }
    }
  }
  return findings;
}

function mismatchedConstFields(schema = {}, checks = []) {
  const findings = [];
  for (const [path, expected] of checks || []) {
    const actual = getPath(schema, path);
    if (actual !== expected) {
      findings.push(finding("schema_const_mismatch", "blocking", `${path} expected ${expected}.`, { path, expected, actual: actual ?? null }));
    }
  }
  return findings;
}

function missingEnumValues(schema = {}, path, values = []) {
  if (!path || !values.length) {
    return [];
  }
  const actual = getPath(schema, path);
  if (!Array.isArray(actual)) {
    return [finding("schema_enum_missing", "blocking", `${path} must be an enum array.`, { path })];
  }
  return values
    .filter((value) => !actual.includes(value))
    .map((value) => finding("schema_enum_value_missing", "blocking", `${path} missing enum value: ${value}`, { path, value }));
}

function finding(code, severity, message, details = {}) {
  return {
    code,
    severity,
    message,
    ...details
  };
}

function getPath(value = {}, path = "") {
  return String(path).split(".").reduce((current, key) => (
    current && Object.prototype.hasOwnProperty.call(current, key) ? current[key] : undefined
  ), value);
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}
