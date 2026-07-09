import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const A3_SCHEMA_DRIFT_RADAR_VERSION = "a3.a1_a2_schema_drift_radar.v1";

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

export async function buildA1A2SchemaDriftRadar(options = {}) {
  const repoRoot = resolve(options.repoRoot || REPO_ROOT);
  const contracts = [];
  for (const definition of options.contracts || A3_A1_A2_SCHEMA_CONTRACTS) {
    contracts.push(await inspectSchemaContract(definition, repoRoot));
  }
  const missing = contracts.filter((item) => item.status === "missing");
  const drifted = contracts.filter((item) => item.status === "drift_detected");
  const pass = contracts.filter((item) => item.status === "compatible");
  const status = missing.length || drifted.length ? "needs_attention" : "compatible";
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
    a3_action: status === "compatible"
      ? "A3 can keep consuming current A1/A2 source schemas."
      : "Review A1/A2 schema changes before merging A3 report, dashboard, and release-gate changes.",
    a1_a2_boundary: "Radar validates consumer compatibility only; it does not modify A1 runner semantics or A2 judge semantics.",
    safety: {
      raw_schema_payload_embedded: false,
      schema_hashes_only: true,
      raw_secret_values_allowed: false,
      local_paths_public_safe: true
    }
  };
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
