import { readFile, readdir, writeFile, mkdir } from "node:fs/promises";
import { dirname, extname, resolve } from "node:path";

import { RELEASEFOUNDRY_API_FIELD_MAP_VERSION } from "./api-client.js";

export type CapabilityJsonRecord = Record<string, unknown>;

export const CAPABILITY_MATRIX_SCHEMA_VERSION = "releasefoundry.capability_matrix.v1";

export interface CapabilityMatrixInputs {
  publicEvidenceIndexPath: string;
  frontendMirrorIndexPath: string;
  testsRoot?: string | null;
  sourceLabel?: string;
}

const READ_PREFIXES = ["get_", "list_", "poll_", "validate_", "plan_"] as const;
const MUTATING_PREFIXES = ["create_", "update_", "delete_", "revoke_", "evaluate_"] as const;
const LOCAL_API_FUNCTIONS = new Set([
  "init",
  "keep_alive",
  "create_request",
  "create_run",
  "get_dataset",
  "get_request",
  "get_run",
  "list_agents",
  "list_datasets",
  "list_requests",
  "list_runs",
  "poll_request",
  "poll_run",
]);

const LOCAL_RUNTIME_CAPABILITIES = [
  ["agent_adapter", "local_runtime", ["AgentAdapter", "coerce_agent_input", "to_a2_judge_run"]],
  ["api_client", "local_runtime", ["ReleaseFoundryApiClient", "dry_run", "transport"]],
  ["api_preflight", "local_runtime", ["enforce_create_request_preflight", "summarize_generation_request"]],
  ["capability_matrix", "local_runtime", ["build_capability_matrix", "write_capability_matrix"]],
  ["dataset_adapter", "local_runtime", ["dataset_source_to_cases", "api_record_to_cases"]],
  ["evidence_index", "local_runtime", ["build_private_evidence_index", "validate_public_evidence_index"]],
  ["output_policy_guard", "local_runtime", ["output_policy", "private_output_required", "full_record_stdout_blocked"]],
  ["response_field_map", "local_runtime", ["build_response_field_map", "render_response_field_map_markdown"]],
  ["trace_fixture", "local_runtime", ["TraceRecorder", "build_run_fixture", "build_vm_stream"]],
] as const;

const SECRET_PATTERNS = [
  /tp_[A-Za-z0-9_-]+/u,
  /sk-[A-Za-z0-9_-]{8,}/u,
  /Bearer\s+[A-Za-z0-9._-]+/iu,
  /releasefoundry_live_[A-Za-z0-9_-]+/u,
] as const;

export async function loadPublicJson(path: string): Promise<CapabilityJsonRecord> {
  const normalized = path.replaceAll("\\", "/").toLowerCase();
  if (normalized.includes("private_refs") || normalized.includes("secrets") || normalized.endsWith(".env")) {
    throw new Error(`refusing to load non-public capability-matrix input: ${path}`);
  }
  const value: unknown = JSON.parse(await readFile(path, "utf8"));
  if (!isRecord(value)) {
    throw new Error(`expected object JSON input: ${path}`);
  }
  return cloneRecord(value);
}

export async function buildCapabilityMatrix(inputs: CapabilityMatrixInputs): Promise<CapabilityJsonRecord> {
  const evidenceIndex = await loadPublicJson(inputs.publicEvidenceIndexPath);
  const frontendIndex = await loadPublicJson(inputs.frontendMirrorIndexPath);
  const testsText = inputs.testsRoot ? await readPublicTests(inputs.testsRoot) : "";
  const evidenceByFunction = summarizePublicEvidence(evidenceIndex);
  const frontendFunctions = stringArray(frontendIndex.api_functions).sort();
  const names = new Set([...Object.keys(evidenceByFunction), ...frontendFunctions, ...LOCAL_API_FUNCTIONS]);
  const capabilities = new Map<string, CapabilityJsonRecord>();

  for (const name of [...names].sort()) {
    const evidence = evidenceByFunction[name] ?? {};
    const mutating = isMutating(name);
    const realReadVerified = !mutating && numberValue(evidence.real_ok_count) > 0;
    const mutatingPlannedOrQuotaBlocked = mutating && (
      numberValue(evidence.planned_count) > 0
      || numberValue(evidence.quota_block_count) > 0
      || numberValue(evidence.real_error_count) > 0
    );
    const frontendMirrored = frontendFunctions.includes(name);
    const localRuntime = LOCAL_API_FUNCTIONS.has(name);
    capabilities.set(name, capabilityEntry({
      name,
      category: "api_function",
      localRuntime,
      localOnly: false,
      realReadVerified,
      mutatingPlannedOrQuotaBlocked,
      frontendMirrored,
      testCovered: tokenCovered(testsText, name),
      evidence,
      sourceNotes: sourceNotes(localRuntime, realReadVerified, mutatingPlannedOrQuotaBlocked, frontendMirrored),
    }));
  }

  for (const [name, category, coverageTokens] of LOCAL_RUNTIME_CAPABILITIES) {
    capabilities.set(name, capabilityEntry({
      name,
      category,
      localRuntime: true,
      localOnly: true,
      realReadVerified: false,
      mutatingPlannedOrQuotaBlocked: false,
      frontendMirrored: false,
      testCovered: [name, ...coverageTokens].some((token) => tokenCovered(testsText, token)),
      evidence: {},
      sourceNotes: ["local SDK/runtime implementation"],
    }));
  }

  const entries = [...capabilities.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([, value]) => value);
  const matrix: CapabilityJsonRecord = {
    schema_version: CAPABILITY_MATRIX_SCHEMA_VERSION,
    label: inputs.sourceLabel ?? "a1-round15-commercial-capability-matrix",
    field_map_version: RELEASEFOUNDRY_API_FIELD_MAP_VERSION,
    public_safe: true,
    secret_policy: {
      private_evidence_read: false,
      tokens_included: false,
      raw_private_payloads_included: false,
      input_sources: [
        "public_evidence_index",
        "frontend_mirror_index",
        "local_runtime_symbols",
        "tests_a1_static_coverage",
      ],
    },
    source_indexes: {
      public_evidence: {
        schema_version: evidenceIndex.schema_version ?? null,
        label: evidenceIndex.label ?? null,
        total_records: numberValue(evidenceIndex.total_records),
        function_count: Object.keys(evidenceByFunction).length,
        quota_block_count: numberValue(evidenceIndex.quota_block_count),
      },
      frontend_mirror: {
        schema_version: frontendIndex.schema_version ?? null,
        raw_files_committed: frontendIndex.raw_files_committed ?? null,
        public_safe_summary: frontendIndex.public_safe_summary ?? null,
        api_function_count: frontendFunctions.length,
        api_entrypoints: stringArray(frontendIndex.api_entrypoints).sort(),
      },
    },
    summary: matrixSummary(entries),
    capabilities: entries,
  };
  assertCapabilityMatrixSafe(matrix);
  return matrix;
}

export async function writeCapabilityMatrix(path: string, matrix: CapabilityJsonRecord): Promise<string> {
  assertCapabilityMatrixSafe(matrix);
  const output = resolve(path);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(matrix, null, 2)}\n`, "utf8");
  return output;
}

export function validateCapabilityMatrix(matrix: CapabilityJsonRecord): CapabilityJsonRecord[] {
  const issues: CapabilityJsonRecord[] = [];
  if (matrix.schema_version !== CAPABILITY_MATRIX_SCHEMA_VERSION) {
    issues.push({ severity: "error", kind: "bad_schema_version" });
  }
  if (matrix.public_safe !== true) {
    issues.push({ severity: "error", kind: "not_marked_public_safe" });
  }
  const text = JSON.stringify(matrix);
  if (text.includes("private_refs")) {
    issues.push({ severity: "error", kind: "private_ref_path_leaked" });
  }
  for (const pattern of SECRET_PATTERNS) {
    if (pattern.test(text)) {
      issues.push({ severity: "error", kind: "secret_like_value_leaked", pattern: pattern.source });
    }
  }
  const names = new Set<string>();
  const entries = Array.isArray(matrix.capabilities) ? matrix.capabilities : [];
  entries.forEach((value, index) => {
    if (!isRecord(value)) {
      issues.push({ severity: "error", kind: "bad_capability_entry", index });
      return;
    }
    const name = value.name;
    if (typeof name !== "string" || name.length === 0) {
      issues.push({ severity: "error", kind: "missing_capability_name", index });
    } else if (names.has(name)) {
      issues.push({ severity: "error", kind: "duplicate_capability_name", name });
    } else {
      names.add(name);
    }
    for (const field of ["local_only", "real_read_verified", "mutating_planned_or_quota_blocked", "frontend_mirrored", "test_covered"]) {
      if (typeof value[field] !== "boolean") {
        issues.push({ severity: "error", kind: "non_boolean_axis", name: name ?? null, field });
      }
    }
  });
  return issues;
}

export function assertCapabilityMatrixSafe(matrix: CapabilityJsonRecord): void {
  const blockers = validateCapabilityMatrix(matrix).filter((issue) => issue.severity === "error");
  if (blockers.length > 0) {
    throw new Error(`capability matrix has ${blockers.length} public-safety/schema issue(s)`);
  }
}

function summarizePublicEvidence(index: CapabilityJsonRecord): Record<string, CapabilityJsonRecord> {
  const result: Record<string, CapabilityJsonRecord> = {};
  const records = Array.isArray(index.records) ? index.records : [];
  for (const value of records) {
    if (!isRecord(value) || typeof value.function !== "string" || value.function.length === 0) continue;
    const name = value.function;
    const item = result[name] ?? {
      records: 0,
      planned_count: 0,
      real_ok_count: 0,
      real_error_count: 0,
      quota_block_count: 0,
      status_counts: {},
      status_codes: [],
      response_keys: [],
      error_keys: [],
    };
    item.records = numberValue(item.records) + 1;
    const status = value.status === undefined || value.status === null ? "unknown" : String(value.status);
    const statusCounts = isRecord(item.status_counts) ? item.status_counts : {};
    statusCounts[status] = numberValue(statusCounts[status]) + 1;
    item.status_counts = statusCounts;
    if (value.dry_run === true || status === "planned") item.planned_count = numberValue(item.planned_count) + 1;
    else if (status === "ok") item.real_ok_count = numberValue(item.real_ok_count) + 1;
    else if (status === "error") item.real_error_count = numberValue(item.real_error_count) + 1;
    if (isRecord(value.quota) && value.quota.blocked === true) item.quota_block_count = numberValue(item.quota_block_count) + 1;
    if (typeof value.status_code === "number") item.status_codes = uniqueNumbers([...(numberArray(item.status_codes)), value.status_code]);
    for (const field of ["response_keys", "error_keys"] as const) {
      item[field] = [...new Set([...stringArray(item[field]), ...stringArray(value[field])])].sort();
    }
    result[name] = item;
  }
  return Object.fromEntries(Object.entries(result).sort(([left], [right]) => left.localeCompare(right)));
}

async function readPublicTests(root: string): Promise<string> {
  const chunks: string[] = [];
  for (const entry of (await readdir(root, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name))) {
    if (!entry.isFile() || extname(entry.name) !== ".py" || !entry.name.startsWith("test_")) continue;
    chunks.push(await readFile(resolve(root, entry.name), "utf8"));
  }
  return chunks.join("\n");
}

function capabilityEntry(options: {
  name: string;
  category: string;
  localRuntime: boolean;
  localOnly: boolean;
  realReadVerified: boolean;
  mutatingPlannedOrQuotaBlocked: boolean;
  frontendMirrored: boolean;
  testCovered: boolean;
  evidence: CapabilityJsonRecord;
  sourceNotes: string[];
}): CapabilityJsonRecord {
  return {
    name: options.name,
    category: options.category,
    local_runtime: options.localRuntime,
    local_only: options.localOnly,
    real_read_verified: options.realReadVerified,
    mutating_planned_or_quota_blocked: options.mutatingPlannedOrQuotaBlocked,
    frontend_mirrored: options.frontendMirrored,
    test_covered: options.testCovered,
    evidence: cloneRecord(options.evidence),
    source_notes: [...new Set(options.sourceNotes)].sort(),
  };
}

function sourceNotes(localRuntime: boolean, realRead: boolean, mutating: boolean, frontend: boolean): string[] {
  const notes: string[] = [];
  if (localRuntime) notes.push("local SDK method present");
  if (realRead) notes.push("real read evidence has public-safe ok record");
  if (mutating) notes.push("mutating capability observed as dry-run plan, error, or quota block");
  if (frontend) notes.push("frontend mirror names this API function");
  return notes;
}

function matrixSummary(entries: CapabilityJsonRecord[]): CapabilityJsonRecord {
  const axes = ["local_only", "real_read_verified", "mutating_planned_or_quota_blocked", "frontend_mirrored", "test_covered"];
  const categories: Record<string, number> = {};
  for (const entry of entries) {
    if (typeof entry.category === "string") categories[entry.category] = (categories[entry.category] ?? 0) + 1;
  }
  return {
    total_capabilities: entries.length,
    axis_counts: Object.fromEntries(axes.map((axis) => [axis, entries.filter((entry) => entry[axis] === true).length])),
    categories: Object.fromEntries(Object.entries(categories).sort(([left], [right]) => left.localeCompare(right))),
  };
}

function isMutating(name: string): boolean {
  return MUTATING_PREFIXES.some((prefix) => name.startsWith(prefix)) || name.startsWith("billing_create_");
}

function tokenCovered(text: string, token: string): boolean {
  if (text.length === 0 || token.length === 0) return false;
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  return new RegExp(`(^|[^A-Za-z0-9_])${escaped}([^A-Za-z0-9_]|$)`, "u").test(text);
}

function isRecord(value: unknown): value is CapabilityJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cloneRecord(value: CapabilityJsonRecord): CapabilityJsonRecord {
  return JSON.parse(JSON.stringify(value)) as CapabilityJsonRecord;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function numberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [];
}

function uniqueNumbers(values: number[]): number[] {
  return [...new Set(values)].sort((left, right) => left - right);
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

void READ_PREFIXES;
