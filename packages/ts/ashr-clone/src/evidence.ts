import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import { ASHR_API_FIELD_MAP_VERSION, redactApiSensitive, redactApiText } from "./api-client.js";

type JsonRecord = Record<string, unknown>;

export const EVIDENCE_INDEX_SCHEMA_VERSION = "ashr.clone.evidence_index.v1";

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
