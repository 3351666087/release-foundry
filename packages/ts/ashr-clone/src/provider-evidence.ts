import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";

export const PROVIDER_EVIDENCE_SCHEMA_VERSION = "ashr.a1.provider_execution_receipt.v1";
export const A1_RELEASE_RECEIPT_SCHEMA_VERSION = "ashr.a1.release_receipt.v1";
const HEX64 = /^[0-9a-f]{64}$/;
const CAPABILITIES = new Set(["text", "image", "audio", "file", "video", "stream", "tools", "usage"]);

export interface ProviderExecutionReceipt {
  receipt_id: string; provider: string; model: string; endpoint_sha256: string;
  invoked_at: string; completed_at: string; request_binding_sha256: string;
  response_binding_sha256: string; evidence_sha256: string; capabilities: string[];
  status: "succeeded" | "failed"; git_sha: string; release_candidate: string;
  request_id_sha256: string; previous_receipt_sha256: string;
  safe_response_shape: Record<string, unknown>; schema_version: string; receipt_sha256: string;
}

function normalized(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).sort().map(([k, v]) => [k, normalized(v)]));
  return value;
}
export function canonicalProviderEvidenceJson(value: unknown): string { return JSON.stringify(normalized(value)); }
export async function providerEvidenceDigest(value: unknown): Promise<string> {
  const bytes = value instanceof Uint8Array ? value : new TextEncoder().encode(typeof value === "string" ? value : canonicalProviderEvidenceJson(value));
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes).buffer))].map(v => v.toString(16).padStart(2, "0")).join("");
}
function timestamp(value: string): string {
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) || !Number.isFinite(Date.parse(value))) throw new Error("timestamp must be timezone-aware ISO-8601");
  return new Date(Math.floor(Date.parse(value) / 1000) * 1000).toISOString().replace(".000Z", "Z");
}
function hex(value: string, name: string, optional = false): void { if (!(optional && value === "") && !HEX64.test(value)) throw new Error(`${name} must be lowercase SHA-256 hex`); }
function payload(receipt: ProviderExecutionReceipt): Omit<ProviderExecutionReceipt, "receipt_sha256"> {
  const { receipt_sha256: _ignored, ...body } = receipt; return body;
}

export async function createProviderExecutionReceipt(options: {
  provider: string; model: string; endpoint: string; invokedAt: string; completedAt: string;
  requestBinding: unknown; responseBinding: unknown; evidence: string | Uint8Array;
  capabilities: string[]; status: "succeeded" | "failed"; gitSha: string;
  releaseCandidate: string; requestId?: string; previousReceiptSha256?: string;
  safeResponseShape?: Record<string, unknown>;
}): Promise<ProviderExecutionReceipt> {
  if (!options.provider.trim() || !options.model.trim() || !/^https?:\/\//.test(options.endpoint)) throw new Error("provider, model, and HTTP(S) endpoint are required");
  let capabilities = [...new Set(options.capabilities)].sort();
  if (!capabilities.length || capabilities.some(v => !CAPABILITIES.has(v))) throw new Error("unsupported or empty capabilities");
  if (options.status === "failed") capabilities = [];
  if (!/^[0-9a-f]{7,64}$/.test(options.gitSha)) throw new Error("gitSha must be lowercase Git hex");
  const invoked_at = timestamp(options.invokedAt), completed_at = timestamp(options.completedAt);
  if (Date.parse(completed_at) < Date.parse(invoked_at)) throw new Error("completedAt precedes invokedAt");
  const evidenceBytes = typeof options.evidence === "string" ? new TextEncoder().encode(options.evidence) : options.evidence;
  if (!evidenceBytes.byteLength) throw new Error("evidence is required");
  const previous = options.previousReceiptSha256 ?? ""; hex(previous, "previous_receipt_sha256", true);
  const base = {
    receipt_id: "pending", provider: options.provider, model: options.model,
    endpoint_sha256: await providerEvidenceDigest(options.endpoint.replace(/\/$/, "")), invoked_at, completed_at,
    request_binding_sha256: await providerEvidenceDigest(options.requestBinding), response_binding_sha256: await providerEvidenceDigest(options.responseBinding),
    evidence_sha256: await providerEvidenceDigest(evidenceBytes), capabilities, status: options.status,
    git_sha: options.gitSha, release_candidate: options.releaseCandidate.trim(),
    request_id_sha256: options.requestId ? await providerEvidenceDigest(options.requestId) : "",
    previous_receipt_sha256: previous, safe_response_shape: options.safeResponseShape ?? {}, schema_version: PROVIDER_EVIDENCE_SCHEMA_VERSION,
  };
  const receipt_id = `provider_receipt_${(await providerEvidenceDigest({ ...base, receipt_id: "" })).slice(0, 20)}`;
  const body = { ...base, receipt_id };
  return { ...body, receipt_sha256: await providerEvidenceDigest(body) };
}

export async function verifyProviderExecutionReceipt(value: ProviderExecutionReceipt, expectedPrevious?: string): Promise<ProviderExecutionReceipt> {
  for (const name of ["endpoint_sha256", "request_binding_sha256", "response_binding_sha256", "evidence_sha256", "receipt_sha256"] as const) hex(value[name], name);
  hex(value.request_id_sha256, "request_id_sha256", true); hex(value.previous_receipt_sha256, "previous_receipt_sha256", true);
  if (value.schema_version !== PROVIDER_EVIDENCE_SCHEMA_VERSION || await providerEvidenceDigest(payload(value)) !== value.receipt_sha256) throw new Error("provider receipt integrity verification failed");
  if (expectedPrevious !== undefined && value.previous_receipt_sha256 !== expectedPrevious) throw new Error("provider receipt chain mismatch");
  timestamp(value.invoked_at); timestamp(value.completed_at);
  if (!(["succeeded", "failed"] as string[]).includes(value.status) || value.capabilities.some(v => !CAPABILITIES.has(v)) || JSON.stringify(value.capabilities) !== JSON.stringify([...new Set(value.capabilities)].sort()) || (value.status === "failed" && value.capabilities.length)) throw new Error("provider receipt semantics invalid");
  return value;
}

export class ProviderExecutionReceiptStore {
  constructor(readonly path: string) {}
  async load(): Promise<ProviderExecutionReceipt[]> {
    let raw: string; try { raw = await readFile(this.path, "utf8"); } catch (e) { if ((e as NodeJS.ErrnoException).code === "ENOENT") return []; throw e; }
    const values = JSON.parse(raw) as ProviderExecutionReceipt[]; if (!Array.isArray(values)) throw new Error("receipt store must contain an array");
    let previous = ""; for (const value of values) { await verifyProviderExecutionReceipt(value, previous); previous = value.receipt_sha256; } return values;
  }
  async append(receipt: ProviderExecutionReceipt): Promise<void> {
    const values = await this.load(); await verifyProviderExecutionReceipt(receipt, values.at(-1)?.receipt_sha256 ?? "");
    await mkdir(dirname(this.path), { recursive: true }); const temp = `${this.path}.${randomUUID()}.tmp`;
    await writeFile(temp, `${JSON.stringify([...values, receipt], null, 2)}\n`, { encoding: "utf8", flag: "wx" }); await rename(temp, this.path);
  }
}

export async function buildA1ReleaseReceipt(options: { gitSha: string; releaseCandidate: string; providerReceipts: ProviderExecutionReceipt[]; evidenceFiles: Record<string, string | Uint8Array>; generatedAt: string }): Promise<Record<string, unknown>> {
  for (const receipt of options.providerReceipts) await verifyProviderExecutionReceipt(receipt);
  const refs = await Promise.all(Object.entries(options.evidenceFiles).sort().map(async ([name, value]) => ({ name, sha256: await providerEvidenceDigest(value) })));
  const body = { schema_version: A1_RELEASE_RECEIPT_SCHEMA_VERSION, git_sha: options.gitSha, release_candidate: options.releaseCandidate, generated_at: timestamp(options.generatedAt), provider_receipt_sha256s: options.providerReceipts.map(v => v.receipt_sha256).sort(), evidence_refs: refs };
  return { ...body, release_receipt_sha256: await providerEvidenceDigest(body) };
}
export async function verifyA1ReleaseReceipt(value: Record<string, unknown>): Promise<boolean> {
  const body = { ...value }; const claimed = String(body.release_receipt_sha256 ?? ""); delete body.release_receipt_sha256; hex(claimed, "release_receipt_sha256");
  if (body.schema_version !== A1_RELEASE_RECEIPT_SCHEMA_VERSION || await providerEvidenceDigest(body) !== claimed) throw new Error("release receipt integrity verification failed"); return true;
}
// Python-compatible names keep root and subpath imports at full parity.
export const ProviderReceiptStore = ProviderExecutionReceiptStore;
export const canonical_provider_evidence_json = canonicalProviderEvidenceJson;
export const create_provider_receipt = createProviderExecutionReceipt;
export const verify_provider_receipt = verifyProviderExecutionReceipt;
export const build_release_receipt = buildA1ReleaseReceipt;
export const verify_release_receipt = verifyA1ReleaseReceipt;