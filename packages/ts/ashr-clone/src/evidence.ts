import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { ASHR_API_FIELD_MAP_VERSION, redactApiSensitive, redactApiText } from "./api-client.js";

type JsonRecord = Record<string, unknown>;

export const EVIDENCE_INDEX_SCHEMA_VERSION = "ashr.clone.evidence_index.v1";
const PUBLIC_SECRET_PATTERNS = [/tp_[A-Za-z0-9_-]+/, /sk-[A-Za-z0-9_-]{8,}/, /Bearer\s+[A-Za-z0-9._-]+/i, /ashr_live_[A-Za-z0-9_-]+/];

export interface EvidenceIndexOptions {
  label?: string;
  maxFiles?: number | null;
}

export async function buildPrivateEvidenceIndex(paths: Iterable<string>, options: EvidenceIndexOptions = {}): Promise<JsonRecord> {
  const entries: JsonRecord[] = [];
  for (const path of paths) {
    const entry = await summarizeRecordPath(path);
    if (entry !== null) {
      entries.push(entry);
    }
  }
  entries.sort((left, right) => String(left.path).localeCompare(String(right.path)));
  const limited = options.maxFiles === null || options.maxFiles === undefined ? entries : entries.slice(0, normalizeMaxFiles(options.maxFiles));
  return redactApiSensitive({
    schema_version: EVIDENCE_INDEX_SCHEMA_VERSION,
    label: options.label ?? "a1-real-api",
    field_map_version: ASHR_API_FIELD_MAP_VERSION,
    total_records: limited.length,
    status_counts: countBy(limited, "status"),
    function_counts: countBy(limited, "function"),
    error_kind_counts: countBy(limited, "error_kind"),
    quota_block_count: limited.filter((entry) => isRecord(entry.quota) && entry.quota.blocked === true).length,
    records: limited,
  }) as JsonRecord;
}

export async function writePrivateEvidenceIndex(path: string, index: JsonRecord): Promise<string> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(redactApiSensitive(index), null, 2)}\n`, "utf8");
  return path;
}

export function validatePublicEvidenceIndex(index: JsonRecord): JsonRecord[] {
  const issues: JsonRecord[] = [];
  const rawText = JSON.stringify(index);
  const redactedText = JSON.stringify(redactApiSensitive(index));
  const quotaDetailChecks: Array<{ pattern: string; test: (value: string) => boolean }> = [
    { pattern: "5/5 used", test: (value) => value.includes("5/5 used") },
    { pattern: '"remaining": 0', test: (value) => /"remaining"\s*:\s*0/.test(value) },
    { pattern: '"requested": 1', test: (value) => /"requested"\s*:\s*1/.test(value) },
    { pattern: '"used": 5', test: (value) => /"used"\s*:\s*5/.test(value) },
  ];
  for (const check of quotaDetailChecks) {
    if (check.test(redactedText)) {
      issues.push({ severity: "error", kind: "exact_quota_detail", pattern: check.pattern });
    }
  }
  for (const pattern of PUBLIC_SECRET_PATTERNS) {
    if (pattern.test(rawText)) {
      issues.push({ severity: "error", kind: "secret_like_text", pattern: pattern.source });
    }
  }
  const records = Array.isArray(index.records) ? index.records : [];
  records.forEach((record, recordIndex) => {
    if (!isRecord(record)) {
      issues.push({ severity: "error", kind: "malformed_record", record_index: recordIndex });
      return;
    }
    const quota = record.quota;
    if (!isRecord(quota)) {
      return;
    }
    for (const key of ["limit", "used", "requested", "remaining"] as const) {
      if (Object.prototype.hasOwnProperty.call(quota, key)) {
        issues.push({ severity: "error", kind: "quota_value_not_public_safe", record_index: recordIndex, field: key });
      }
    }
  });
  return issues;
}

export function buildResponseFieldMap(index: JsonRecord): JsonRecord {
  const records = Array.isArray(index.records) ? index.records : [];
  const functions: Record<string, JsonRecord> = {};
  for (const record of records) {
    if (!isRecord(record)) {
      continue;
    }
    const functionName = String(record.function ?? "unknown");
    const item =
      functions[functionName] ??
      {
        records: 0,
        statuses: {},
        response_keys: [],
        response_summary_keys: [],
        error_keys: [],
        quota_block_count: 0,
        top_count_keys: [],
      };
    item.records = Number(item.records) + 1;
    if (record.status !== null && record.status !== undefined && isRecord(item.statuses)) {
      const status = String(record.status);
      item.statuses[status] = Number(item.statuses[status] ?? 0) + 1;
    }
    for (const [sourceKey, targetKey] of [
      ["response_keys", "response_keys"],
      ["response_summary_keys", "response_summary_keys"],
      ["error_keys", "error_keys"],
    ] as const) {
      item[targetKey] = mergeStringArrays(item[targetKey], record[sourceKey]);
    }
    const topCounts = isRecord(record.top_counts) ? record.top_counts : {};
    item.top_count_keys = mergeStringArrays(item.top_count_keys, Object.keys(topCounts));
    const quota = isRecord(record.quota) ? record.quota : {};
    if (quota.blocked === true) {
      item.quota_block_count = Number(item.quota_block_count) + 1;
    }
    functions[functionName] = item;
  }
  return {
    schema_version: "ashr.clone.response_field_map.v1",
    source_label: index.label,
    source_total_records: index.total_records,
    field_map_version: index.field_map_version,
    functions: Object.fromEntries(Object.entries(functions).sort(([left], [right]) => left.localeCompare(right))),
  };
}

async function summarizeRecordPath(path: string): Promise<JsonRecord | null> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  const response = isRecord(parsed.response) ? parsed.response : {};
  const error = isRecord(parsed.error) ? parsed.error : {};
  const request = isRecord(parsed.request) ? parsed.request : {};
  const quota = publicSafeQuotaSummary(summarizeQuotaError(parsed));
  const entry: JsonRecord = {
    path: path.replaceAll("\\", "/"),
    function: parsed.function,
    dry_run: parsed.dry_run,
    status: parsed.status,
    status_code: parsed.status_code,
    attempts: parsed.attempts,
    request_keys: keys(request),
    response_keys: keys(response),
    response_status: typeof response.status === "string" ? response.status : null,
    response_summary_keys: keys(parsed.response_summary),
    error_keys: keys(error),
    error_kind: typeof error.error_kind === "string" ? error.error_kind : null,
    top_counts: topCounts(response),
  };
  if (quota !== null) {
    entry.quota = quota;
  }
  return redactApiSensitive(entry) as JsonRecord;
}

function summarizeQuotaError(value: JsonRecord): JsonRecord | null {
  const candidates = quotaCandidates(value);
  const quotaCandidatesFirst = candidates.filter((candidate) => isRecord(candidate.quota));
  const messageCandidates = candidates.filter((candidate) => !isRecord(candidate.quota));
  for (const candidate of [...quotaCandidatesFirst, ...messageCandidates]) {
    const quota = candidate.quota;
    const message = candidate.message;
    if (isRecord(quota)) {
      const summary: JsonRecord = {
        blocked: true,
        message: typeof message === "string" ? redactApiText(message) : null,
        quota_keys: keys(quota),
      };
      for (const key of ["resource", "limit", "used", "requested", "remaining"] as const) {
        const item = quota[key];
        if (["string", "number", "boolean"].includes(typeof item)) {
          summary[key] = item;
        }
      }
      return redactApiSensitive(summary) as JsonRecord;
    }
    if (typeof message === "string" && message.includes("Usage limit exceeded")) {
      return { blocked: true, message: redactApiText(message), quota_keys: [] };
    }
  }
  return null;
}

function publicSafeQuotaSummary(quota: JsonRecord | null): JsonRecord | null {
  if (quota === null) {
    return null;
  }
  const quotaKeys = Array.isArray(quota.quota_keys) ? quota.quota_keys.map(String).sort() : [];
  const summary: JsonRecord = {
    blocked: quota.blocked === true,
    message: quota.blocked === true ? "Usage limit exceeded; exact quota details are kept in private evidence" : null,
    quota_keys: quotaKeys,
  };
  if (["string", "number", "boolean"].includes(typeof quota.resource)) {
    summary.resource = quota.resource;
  }
  for (const key of ["limit", "used", "requested", "remaining"] as const) {
    if (key in quota) {
      summary[`${key}_present`] = true;
    }
  }
  return summary;
}

function quotaCandidates(value: JsonRecord): JsonRecord[] {
  const candidates: JsonRecord[] = [value];
  for (const key of ["error", "response"] as const) {
    const nested = value[key];
    if (!isRecord(nested)) {
      continue;
    }
    candidates.push(nested);
    if (isRecord(nested.response)) {
      candidates.push(nested.response);
    }
    if (isRecord(nested.error)) {
      candidates.push(nested.error);
    }
  }
  return candidates;
}

function keys(value: unknown): string[] {
  return isRecord(value) ? Object.keys(value).map(String).sort() : [];
}

function topCounts(response: JsonRecord): JsonRecord {
  const counts: JsonRecord = {};
  for (const key of ["agents", "datasets", "requests", "runs"] as const) {
    if (Array.isArray(response[key])) {
      counts[key] = response[key].length;
    }
  }
  return counts;
}

function countBy(entries: JsonRecord[], key: string): JsonRecord {
  const counts: Record<string, number> = {};
  for (const entry of entries) {
    const value = entry[key];
    if (value === null || value === undefined) {
      continue;
    }
    const countKey = String(value);
    counts[countKey] = (counts[countKey] ?? 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function mergeStringArrays(left: unknown, right: unknown): string[] {
  const values = new Set<string>();
  for (const item of arrayItems(left)) {
    if (typeof item === "string") {
      values.add(item);
    }
  }
  for (const item of arrayItems(right)) {
    if (typeof item === "string") {
      values.add(item);
    }
  }
  return Array.from(values).sort();
}

function arrayItems(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function normalizeMaxFiles(value: number): number {
  const normalized = Math.trunc(Number(value));
  if (!Number.isFinite(normalized) || normalized < 0) {
    throw new Error("maxFiles must be non-negative");
  }
  return normalized;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
