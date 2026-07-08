#!/usr/bin/env node
import { CloudApiService, NotFoundError, ValidationError } from "./index.js";
import { resolve } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import type { JsonRecord } from "./index.js";

export const CONTROL_PLANE_SCHEMA_VERSION = "ashr.clone.saas_control_plane.v1";
export const SAAS_CLIENT_VERSION = "ashr.clone.ts_saas_ingestion_client.v1";
export const SAAS_OPENAPI_SCHEMA_VERSION = "ashr.clone.saas_openapi.v1";
export const CONTROL_PLANE_OPENAPI_VERSION = "3.0.3";
export const SAAS_QUOTA_LIMITS: Record<string, number> = {
  "api_key.create": 100,
  "run.upload": 10000,
  "sdk.submit": 10000,
  "trace.ingest": 100000,
  "artifact.manifest": 10000,
  "audit_chain.verify": 10000,
  "release_evidence.verify": 10000,
};

export const API_KEY_ADMIN_SCOPE = "api_key:write";
export const API_KEY_READ_SCOPE = "api_key:read";
export const RUN_CREATE_SCOPE = "run:create";
export const RUN_UPLOAD_SCOPE = "run:upload";
export const TRACE_INGEST_SCOPE = "trace:ingest";
export const ARTIFACT_MANIFEST_SCOPE = "artifact:upload";
export const ADMIN_ALL_SCOPE = "admin:all";
export const USAGE_READ_SCOPE = "usage:read";
export const AUDIT_READ_SCOPE = "audit:read";

const SCOPE_ALIASES: Record<string, string[]> = {
  "key:admin": [API_KEY_ADMIN_SCOPE, API_KEY_READ_SCOPE],
  "key:read": [API_KEY_READ_SCOPE],
  "sdk:submit": [RUN_CREATE_SCOPE],
  "runs:write": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"],
  "write:runs": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"],
  "traces:write": [TRACE_INGEST_SCOPE],
  "artifact:write": [ARTIFACT_MANIFEST_SCOPE],
  "artifacts:write": [ARTIFACT_MANIFEST_SCOPE],
  [API_KEY_ADMIN_SCOPE]: [API_KEY_READ_SCOPE],
  [ADMIN_ALL_SCOPE]: ["*"],
};

export interface SaaSControlPlaneStore {
  api_keys: Record<string, JsonRecord>;
  api_key_rate_limits: Record<string, JsonRecord>;
  uploads: Record<string, JsonRecord>;
  trace_batches: Record<string, JsonRecord>;
  sdk_submissions: Record<string, JsonRecord>;
  audit_log: Record<string, JsonRecord>;
  usage_ledger: Record<string, JsonRecord>;
  idempotency_keys: Record<string, JsonRecord>;
  artifact_manifests: Record<string, JsonRecord>;
}

export interface SaaSControlPlaneState extends JsonRecord {
  schema_version: typeof CONTROL_PLANE_SCHEMA_VERSION;
  state_schema_version: number;
  cloud: JsonRecord;
  metadata: { local_only: true; ashr_api_used: false };
  state_metadata: JsonRecord;
  control_plane: SaaSControlPlaneStore;
  integrity: JsonRecord;
}

export interface SaaSRouterResponse extends JsonRecord {
  status_code: number;
  body: JsonRecord;
}

export type SaaSFetchLike = (input: string | URL, init?: {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}) => Promise<{ ok: boolean; status: number; json(): Promise<unknown>; text(): Promise<string> }>;

export interface SaaSHttpTransportOptions {
  baseUrl: string;
  fetch?: SaaSFetchLike;
  headers?: Record<string, string>;
}

export interface SaaSClientTransport {
  requestJson(method: string, path: string, body?: JsonRecord): Promise<JsonRecord>;
}

export function createSaaSControlPlaneStore(seed: Partial<SaaSControlPlaneStore> = {}): SaaSControlPlaneStore {
  return {
    api_keys: { ...(seed.api_keys ?? {}) },
    api_key_rate_limits: { ...(seed.api_key_rate_limits ?? {}) },
    uploads: { ...(seed.uploads ?? {}) },
    trace_batches: { ...(seed.trace_batches ?? {}) },
    sdk_submissions: { ...(seed.sdk_submissions ?? {}) },
    audit_log: { ...(seed.audit_log ?? {}) },
    usage_ledger: { ...(seed.usage_ledger ?? {}) },
    idempotency_keys: { ...(seed.idempotency_keys ?? {}) },
    artifact_manifests: { ...(seed.artifact_manifests ?? {}) },
  };
}

export class SaaSControlPlaneService {
  readonly cloud: CloudApiService;
  readonly store: SaaSControlPlaneStore;

  constructor(options: { cloud?: CloudApiService; store?: Partial<SaaSControlPlaneStore> } = {}) {
    this.cloud = options.cloud ?? new CloudApiService();
    this.store = createSaaSControlPlaneStore(options.store);
  }

  bootstrapProject(options: { tenantName: string; projectName: string; tenantId?: string; projectId?: string }): JsonRecord {
    const tenant = this.cloud.createTenant(options.tenantName, { tenantId: options.tenantId });
    const project = this.cloud.createProject(tenant.tenant_id, options.projectName, { projectId: options.projectId });
    this.cloud.quota.configure(tenant.tenant_id, project.project_id, SAAS_QUOTA_LIMITS);
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, tenant, project, quota: this.cloud.quotaSnapshot(tenant.tenant_id, project.project_id) };
  }

  createApiKey(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; revealSecret?: boolean }): JsonRecord {
    const project = this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const scopes = options.scopes.map((scope) => normalizeScope(scope));
    if (scopes.length === 0) {
      throw new ValidationError("api key scopes must not be empty");
    }
    this.cloud.quota.consume(project.tenant_id, project.project_id, "api_key.create");
    const keyId = options.keyId ?? newId("key");
    if (this.store.api_keys[keyId] !== undefined) {
      throw new ValidationError(`api key already exists: ${keyId}`);
    }
    const syntheticSecret = `ashr_local_${keyId}_${randomUUID().replaceAll("-", "")}`;
    const now = utcNow();
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      key_id: keyId,
      name: options.name,
      prefix: "ashr_local_***",
      secret_hash_sha256: secretHash(syntheticSecret),
      secret_value_present: false,
      one_time_secret_displayed: options.revealSecret === true,
      verify_mode: "sha256",
      status: "active",
      scopes,
      created_at: now,
      revoked_at: null,
      last_used_at: null,
    };
    this.store.api_keys[keyId] = record;
    const publicRecord = publicApiKey(record);
    this.appendAudit(tenantId, projectId, "api_key.create", { targetId: keyId, apiKeyId: options.authKeyId, after: publicRecord });
    if (options.revealSecret === true) {
      return { ...publicRecord, one_time_secret: syntheticSecret, one_time_secret_displayed: true, secret_value_present: true };
    }
    return publicRecord;
  }

  revokeApiKey(tenantId: string, projectId: string, keyId: string, options: { authKeyId?: string } = {}): JsonRecord {
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const record = this.apiKeyRecord(tenantId, projectId, keyId);
    const before = publicApiKey(record);
    record.status = "revoked";
    record.revoked_at = utcNow();
    const after = publicApiKey(record);
    this.appendAudit(tenantId, projectId, "api_key.revoke", { targetId: keyId, apiKeyId: options.authKeyId, before, after });
    return after;
  }

  listApiKeys(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord[] {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_READ_SCOPE });
    }
    return Object.values(this.store.api_keys)
      .filter((record) => record.tenant_id === tenantId && record.project_id === projectId)
      .map((record) => publicApiKey(record));
  }

  authenticateApiKey(tenantId: string, projectId: string, options: { keyId: string; scope: string; consumeRate?: boolean }): JsonRecord {
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    const requiredScope = normalizeScope(options.scope);
    if (record.status !== "active") {
      throw new ValidationError(`api key is not active: ${options.keyId}`);
    }
    if (!scopeAllows(record.scopes, requiredScope)) {
      throw new ValidationError(`api key ${options.keyId} missing required scope: ${requiredScope}`);
    }
    if (options.consumeRate !== false) this.consumeApiKeyRate(record, requiredScope);
    record.last_used_at = utcNow();
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      authenticated: true,
      required_scope: requiredScope,
      api_key: publicApiKey(record),
      secret_value_present: false,
    };
  }

  verifyApiKeySecret(tenantId: string, projectId: string, options: { keyId: string; secret: string; scope?: string }): JsonRecord {
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    if (record.status !== "active") {
      throw new ValidationError(`api key is not active: ${options.keyId}`);
    }
    if (secretHash(options.secret) !== record.secret_hash_sha256) {
      throw new ValidationError("api key secret verification failed");
    }
    if (options.scope !== undefined) {
      return this.authenticateApiKey(tenantId, projectId, { keyId: options.keyId, scope: options.scope });
    }
    record.last_used_at = utcNow();
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      verified: true,
      api_key: publicApiKey(record),
      secret_value_present: false,
    };
  }

  configureApiKeyRateLimit(tenantId: string, projectId: string, options: { keyId: string; operation: string; limit: number; period?: string; authKeyId?: string }): JsonRecord {
    if (options.authKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: API_KEY_ADMIN_SCOPE });
    }
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    const limit = Number(options.limit);
    if (!Number.isFinite(limit) || limit <= 0) {
      throw new ValidationError("api key rate limit must be positive");
    }
    const operation = normalizeScope(options.operation);
    const period = options.period ?? "local-window";
    const bucketKey = apiKeyRateKey(tenantId, projectId, options.keyId, operation, period);
    const bucket: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId,
      operation,
      period,
      limit: Math.trunc(limit),
      used: 0,
      remaining: Math.trunc(limit),
      created_at: utcNow(),
    };
    this.store.api_key_rate_limits[bucketKey] = bucket;
    this.appendAudit(tenantId, projectId, "api_key.rate_limit.configure", { targetId: options.keyId, apiKeyId: options.authKeyId, after: { api_key: publicApiKey(record), rate_limit: bucket } });
    return cloneJson(bucket) as JsonRecord;
  }

  apiKeyRateLimitSnapshot(tenantId: string, projectId: string, options: { keyId?: string } = {}): JsonRecord {
    const buckets = Object.values(this.store.api_key_rate_limits)
      .filter((bucket) => bucket.tenant_id === tenantId && bucket.project_id === projectId && (options.keyId === undefined || bucket.key_id === options.keyId));
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      key_id: options.keyId ?? null,
      rate_limits: cloneJson(buckets),
    };
  }

  sdkSubmitRun(tenantId: string, projectId: string, options: { datasetId: string; agentRef: string; runId?: string; metadata?: JsonRecord; apiKeyId?: string; idempotencyKey?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: "sdk:submit", consumeRate: false });
    }
    const requestFingerprint = requestFingerprintSha256({ dataset_id: options.datasetId, agent_ref: options.agentRef, run_id: options.runId ?? null, metadata: options.metadata ?? {}, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "sdk.submit", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), "sdk:submit");
    this.cloud.quota.check(tenantId, projectId, "sdk.submit");
    const run = this.cloud.createQueuedRun(tenantId, projectId, {
      datasetId: options.datasetId,
      runId: options.runId,
      runnerId: "sdk-submit",
      metadata: { submitted_by: "sdk", agent_ref: options.agentRef, ...(options.metadata ?? {}) },
    });
    this.consumeUsage(tenantId, projectId, "sdk.submit", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId: run.run_id });
    const submission: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      submission_id: newId("sdksub"),
      tenant_id: tenantId,
      project_id: projectId,
      dataset_id: options.datasetId,
      run_id: run.run_id,
      agent_ref: options.agentRef,
      status: "accepted",
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.store.sdk_submissions[String(submission.submission_id)] = submission;
    const response = cloneJson({ submission, run }) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "sdk.submit", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "sdk.submit", { targetId: run.run_id, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { run_id: run.run_id, submission_id: submission.submission_id } });
    return response;
  }

  uploadRunResult(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: { uploadId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: RUN_UPLOAD_SCOPE, consumeRate: false });
    }
    const payload = jsonRecord(result);
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, result: payload, upload_id: options.uploadId ?? null, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "run.upload", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), RUN_UPLOAD_SCOPE);
    const run = this.cloud.getRun(tenantId, projectId, runId);
    this.consumeUsage(tenantId, projectId, "run.upload", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const digest = sha256(JSON.stringify(sortJson(payload)));
    const uploadId = options.uploadId ?? newId("upload");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      upload_id: uploadId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: run.run_id,
      payload_sha256: digest,
      payload_keys: Object.keys(payload).sort(),
      raw_payload_included: false,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      status: "uploaded",
      created_at: utcNow(),
    };
    this.store.uploads[uploadId] = record;
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "run.upload", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "run.upload", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { upload_id: uploadId, payload_sha256: digest } });
    return response;
  }

  ingestTrace(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: TRACE_INGEST_SCOPE, consumeRate: false });
    }
    const normalized = observations.map((item) => jsonRecord(item));
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, observations: normalized, batch_id: options.batchId ?? null, api_key_id: options.apiKeyId ?? null });
    const idem = this.idempotencyLookup(tenantId, projectId, "trace.ingest", options.idempotencyKey, requestFingerprint);
    if (idem !== null) return idem;
    if (options.apiKeyId !== undefined) this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), TRACE_INGEST_SCOPE);
    this.cloud.getRun(tenantId, projectId, runId);
    if (observations.length === 0) {
      throw new ValidationError("trace ingestion requires at least one observation");
    }
    this.consumeUsage(tenantId, projectId, "trace.ingest", { units: observations.length, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const batchSha = sha256(JSON.stringify(sortJson(normalized)));
    const appended = normalized.map((item) => this.cloud.appendObservation(tenantId, projectId, runId, item));
    const batchId = options.batchId ?? newId("tracebatch");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      batch_id: batchId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      observation_count: appended.length,
      observation_ids: appended.map((item) => item.observation_id),
      batch_sha256: batchSha,
      raw_payload_included: false,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      status: "ingested",
      created_at: utcNow(),
    };
    this.store.trace_batches[batchId] = record;
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "trace.ingest", options.idempotencyKey, requestFingerprint, response);
    this.appendAudit(tenantId, projectId, "trace.ingest", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { batch_id: batchId, batch_sha256: batchSha } });
    return response;
  }

  lifecycleSnapshot(tenantId: string, projectId: string, runId: string): JsonRecord {
    const tenant = this.cloud.getTenant(tenantId);
    const project = this.cloud.getProject(tenantId, projectId);
    const run = this.cloud.getRun(tenantId, projectId, runId);
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenant.tenant_id,
      project_id: project.project_id,
      run_id: run.run_id,
      tenant_status: "active",
      project_status: "active",
      run_status: run.status,
      run_result_status: run.result_status,
      status_history: run.status_history,
      quota: this.cloud.quotaSnapshot(tenantId, projectId),
      api_keys: this.listApiKeys(tenantId, projectId),
      uploads: Object.values(this.store.uploads).filter((item) => item.run_id === runId),
      trace_batches: Object.values(this.store.trace_batches).filter((item) => item.run_id === runId),
      usage_ledger: Object.values(this.store.usage_ledger).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (item.run_id === undefined || item.run_id === null || item.run_id === runId)),
      audit_log: Object.values(this.store.audit_log).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (item.target_id === undefined || item.target_id === null || item.target_id === runId)),
    };
  }

  usageSnapshot(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId === undefined) throw new ValidationError("usage snapshot requires authKeyId with usage:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: USAGE_READ_SCOPE });
    const events = Object.values(this.store.usage_ledger).filter((item) => item.tenant_id === tenantId && item.project_id === projectId);
    const totals: Record<string, number> = {};
    for (const event of events) {
      const op = String(event.operation);
      totals[op] = (totals[op] ?? 0) + Number(event.units ?? 0);
    }
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, tenant_id: tenantId, project_id: projectId, events, totals, quota: this.cloud.quotaSnapshot(tenantId, projectId) };
  }

  createArtifactManifest(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId === undefined) throw new ValidationError("artifact manifest upload requires apiKeyId with artifact:upload scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: ARTIFACT_MANIFEST_SCOPE, consumeRate: false });
    const manifestCopy = cloneJson(manifest) as JsonRecord;
    const requestFingerprint = requestFingerprintSha256({ run_id: runId, manifest: manifestCopy, artifact_id: options.artifactId ?? null, api_key_id: options.apiKeyId });
    const cached = this.idempotencyLookup(tenantId, projectId, "artifact.manifest", options.idempotencyKey, requestFingerprint);
    if (cached !== null) return { ...cached, idempotent_replay: true };
    this.consumeApiKeyRate(this.apiKeyRecord(tenantId, projectId, options.apiKeyId), ARTIFACT_MANIFEST_SCOPE);
    this.cloud.getRun(tenantId, projectId, runId);
    const usage = this.consumeUsage(tenantId, projectId, "artifact.manifest", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const artifactId = options.artifactId ?? newId("artifact");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      artifact_id: artifactId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      manifest_schema_version: String(manifestCopy.schema_version ?? "ashr.clone.artifact_manifest.v1"),
      manifest_keys: Object.keys(manifestCopy).sort(),
      manifest_sha256: sha256(JSON.stringify(sortJson(manifestCopy))),
      raw_manifest_included: false,
      api_key_id: options.apiKeyId ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
      usage_event_id: usage.usage_event_id,
    };
    this.store.artifact_manifests[artifactId] = record;
    this.appendAudit(tenantId, projectId, "artifact.manifest", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: record });
    const response = cloneJson(record) as JsonRecord;
    this.idempotencyStore(tenantId, projectId, "artifact.manifest", options.idempotencyKey, requestFingerprint, response);
    return response;
  }

  listArtifactManifests(tenantId: string, projectId: string, runId?: string, options: { authKeyId?: string } = {}): JsonRecord[] {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId === undefined) throw new ValidationError("artifact manifest read requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    return Object.values(this.store.artifact_manifests).filter((item) => item.tenant_id === tenantId && item.project_id === projectId && (runId === undefined || item.run_id === runId)).map((item) => cloneJson(item) as JsonRecord);
  }

  evaluateReleaseGate(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): JsonRecord {
    this.cloud.getRun(tenantId, projectId, runId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const lifecycle = this.lifecycleSnapshot(tenantId, projectId, runId);
    const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
    const traceBatches = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
    const observationCount = traceBatches.reduce((total, batch) => total + Number(isRecord(batch) ? batch.observation_count ?? 0 : 0), 0);
    const uploadStatuses = uploads.map((item) => String(isRecord(item) ? item.status ?? "" : "")).filter(Boolean).sort();
    const traceCompleteness = uploads.length === 0 ? 0 : Math.min(1, observationCount / Math.max(1, uploads.length));
    const hasUploadedResult = uploadStatuses.includes("uploaded");
    const score = Math.min(1, Number((0.35 + Math.min(0.35, observationCount * 0.12) + (hasUploadedResult ? 0.3 : 0)).toFixed(4)));
    const minScore = options.minScore ?? 0.72;
    const requiredTraceCompleteness = options.requiredTraceCompleteness ?? 0.95;
    const blockers = [
      score >= minScore ? null : "score_below_threshold",
      traceCompleteness >= requiredTraceCompleteness ? null : "trace_completeness_below_threshold",
      hasUploadedResult ? null : "missing_run_upload",
    ].filter((item): item is string => item !== null);
    const result: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      evaluator: options.evaluator ?? "local-deterministic-release-gate",
      decision: blockers.length === 0 ? "pass" : "block",
      score,
      min_score: minScore,
      trace_completeness: Number(traceCompleteness.toFixed(4)),
      required_trace_completeness: requiredTraceCompleteness,
      upload_count: uploads.length,
      trace_batch_count: traceBatches.length,
      observation_count: observationCount,
      blockers,
      local_only: true,
      ashr_api_used: false,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.appendAudit(tenantId, projectId, "release_gate.evaluate", { targetId: runId, apiKeyId: options.authKeyId, requestId: options.requestId, after: result });
    return result;
  }

  auditSnapshot(tenantId: string, projectId: string, options: { runId?: string; actionPrefix?: string; authKeyId?: string; limit?: number } = {}): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const limit = Math.max(1, Math.min(500, Math.trunc(options.limit ?? 100)));
    const ledgerEvents = Object.values(this.store.audit_log)
      .filter((item) => item.tenant_id === tenantId && item.project_id === projectId) as JsonRecord[];
    const chain = verifyAuditHashChain(ledgerEvents);
    const events = auditEventsInChainOrder(ledgerEvents
      .filter((item) => options.runId === undefined || item.target_id === options.runId || item.target_id === null)
      .filter((item) => options.actionPrefix === undefined || String(item.action).startsWith(options.actionPrefix)))
      .slice(-limit)
      .map((item) => cloneJson(item) as JsonRecord);
    return {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: options.runId ?? null,
      action_prefix: options.actionPrefix ?? null,
      limit,
      event_count: events.length,
      events,
      chain,
      raw_payload_included: false,
      secret_value_present: false,
    };
  }

  verifyAuditChain(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): JsonRecord {
    if (options.authKeyId === undefined) throw new ValidationError("audit-chain verification requires authKeyId with audit:read scope");
    const snapshot = this.auditSnapshot(tenantId, projectId, { authKeyId: options.authKeyId, limit: 500 });
    const usage = this.consumeUsage(tenantId, projectId, "audit_chain.verify", { apiKeyId: options.authKeyId, requestId: options.requestId });
    const response: JsonRecord = {
      schema_version: "ashr.clone.audit_chain_verification.v1",
      tenant_id: tenantId,
      project_id: projectId,
      ...cloneJson(snapshot.chain) as JsonRecord,
      usage_event_id: usage.usage_event_id,
      raw_payload_included: false,
      secret_value_present: false,
    };
    this.appendAudit(tenantId, projectId, "audit_chain.verify", { apiKeyId: options.authKeyId, requestId: options.requestId, after: { verified: response.verified, event_count: response.event_count, usage_event_id: usage.usage_event_id } });
    return response;
  }

  buildReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { releaseGate?: JsonRecord; authKeyId?: string } = {}): JsonRecord {
    const lifecycle = this.lifecycleSnapshot(tenantId, projectId, runId);
    if (options.authKeyId !== undefined) this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: AUDIT_READ_SCOPE });
    const releaseGate = options.releaseGate ?? this.evaluateReleaseGate(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    if (options.authKeyId === undefined) throw new ValidationError("release evidence read requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    const artifacts = this.listArtifactManifests(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    const usage = this.usageSnapshot(tenantId, projectId, { authKeyId: options.authKeyId });
    const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
    const traces = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
    const audit = this.auditSnapshot(tenantId, projectId, { runId, limit: 200, authKeyId: options.authKeyId });
    const payload = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      packet_schema_version: "ashr.clone.release_evidence_packet.v1",
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      generated_at: utcNow(),
      local_only: true,
      ashr_api_used: false,
      lifecycle: {
        run_status: lifecycle.run_status,
        run_result_status: lifecycle.run_result_status,
        status_history_count: Array.isArray(lifecycle.status_history) ? lifecycle.status_history.length : 0,
      },
      release_gate: cloneJson(releaseGate),
      counts: {
        uploads: uploads.length,
        trace_batches: traces.length,
        observations: traces.reduce((total, batch) => total + Number(isRecord(batch) ? batch.observation_count ?? 0 : 0), 0),
        artifacts: artifacts.length,
        audit_events: audit.event_count,
        usage_events: Array.isArray(usage.events) ? usage.events.length : 0,
      },
      hashes: {
        uploads_sha256: sha256(JSON.stringify(sortJson(uploads))),
        traces_sha256: sha256(JSON.stringify(sortJson(traces))),
        artifacts_sha256: sha256(JSON.stringify(sortJson(artifacts))),
        audit_sha256: sha256(JSON.stringify(sortJson(audit.events))),
      },
      audit_chain: audit.chain,
      usage_totals: usage.totals,
      redaction: { raw_payload_included: false, secret_value_present: false, secret_hash_included: false },
    };
    return { ...payload, integrity: { packet_sha256: sha256(JSON.stringify(sortJson(payload))) } };
  }

  verifyReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): JsonRecord {
    if (options.authKeyId === undefined) throw new ValidationError("release-evidence verification requires authKeyId with evidence:read scope");
    this.authenticateApiKey(tenantId, projectId, { keyId: options.authKeyId, scope: "evidence:read" });
    const packet = options.packet ?? this.buildReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId: options.authKeyId });
    const verification = verifyReleaseEvidencePacket(packet);
    const failures = Array.isArray(verification.failures) ? [...verification.failures] : [];
    if (String(packet.tenant_id ?? "") !== tenantId) failures.push({ reason: "tenant_id_mismatch", expected: tenantId, actual: packet.tenant_id ?? null });
    if (String(packet.project_id ?? "") !== projectId) failures.push({ reason: "project_id_mismatch", expected: projectId, actual: packet.project_id ?? null });
    if (String(packet.run_id ?? "") !== runId) failures.push({ reason: "run_id_mismatch", expected: runId, actual: packet.run_id ?? null });
    const bindings = releasePacketBindings(this, tenantId, projectId, runId, options.authKeyId);
    failures.push(...verifyReleasePacketBindings(packet, bindings));
    const usage = this.consumeUsage(tenantId, projectId, "release_evidence.verify", { apiKeyId: options.authKeyId, requestId: options.requestId, runId });
    const response: JsonRecord = {
      tenant_id: tenantId,
      project_id: projectId,
      run_id: runId,
      ...verification,
      verified: failures.length === 0,
      failures,
      bindings,
      usage_event_id: usage.usage_event_id,
      source: options.packet === undefined ? "current_snapshot" : "submitted_packet",
      raw_payload_included: false,
      secret_value_present: false,
    };
    this.appendAudit(tenantId, projectId, "release_evidence.verify", { targetId: runId, apiKeyId: options.authKeyId, requestId: options.requestId, after: { verified: response.verified, packet_sha256: response.packet_sha256, actual_packet_sha256: response.actual_packet_sha256, usage_event_id: usage.usage_event_id } });
    return {
      ...response,
    };
  }

  snapshotState(): SaaSControlPlaneState {
    const payload = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      state_schema_version: 2,
      cloud: this.cloud.snapshotState() as JsonRecord,
      metadata: { local_only: true as const, ashr_api_used: false as const },
      state_metadata: { writer: "packages/ts/ashr-clone/saas", updated_at: utcNow() },
      control_plane: cloneJson(this.store),
    };
    return { ...payload, integrity: { payload_sha256: sha256(JSON.stringify(sortJson(payload))) } };
  }

  async writeState(outputPath: string): Promise<string> {
    assertPublicControlPlanePath(outputPath);
    const fs = await import("node:fs/promises");
    const pathModule = await import("node:path");
    const resolved = pathModule.resolve(outputPath);
    await fs.mkdir(pathModule.dirname(resolved), { recursive: true });
    const tmp = `${resolved}.tmp`;
    await fs.writeFile(tmp, `${JSON.stringify(sortJson(this.snapshotState()), null, 2)}\n`, "utf8");
    await fs.rename(tmp, resolved);
    return resolved;
  }

  static fromState(payload: unknown): SaaSControlPlaneService {
    if (!isRecord(payload)) {
      throw new ValidationError("control-plane state payload must be an object");
    }
    const version = Number(payload.state_schema_version ?? 1);
    if (![1, 2].includes(version)) {
      throw new ValidationError(`unsupported control-plane state schema version: ${version}`);
    }
    const control = isRecord(payload.control_plane) ? payload.control_plane : {};
    return new SaaSControlPlaneService({
      cloud: CloudApiService.fromState(payload.cloud),
      store: {
        api_keys: stateBucket(control, "api_keys"),
        api_key_rate_limits: stateBucket(control, "api_key_rate_limits"),
        uploads: stateBucket(control, "uploads"),
        trace_batches: stateBucket(control, "trace_batches"),
        sdk_submissions: stateBucket(control, "sdk_submissions"),
        audit_log: stateBucket(control, "audit_log"),
        usage_ledger: stateBucket(control, "usage_ledger"),
        idempotency_keys: stateBucket(control, "idempotency_keys"),
        artifact_manifests: stateBucket(control, "artifact_manifests"),
      },
    });
  }

  static async fromStateFile(inputPath: string): Promise<SaaSControlPlaneService> {
    assertPublicControlPlanePath(inputPath);
    const fs = await import("node:fs/promises");
    return SaaSControlPlaneService.fromState(JSON.parse(await fs.readFile(inputPath, "utf8")) as unknown);
  }

  private apiKeyRecord(tenantId: string, projectId: string, keyId: string): JsonRecord {
    const record = this.store.api_keys[keyId];
    if (record === undefined || record.tenant_id !== tenantId || record.project_id !== projectId) {
      throw new NotFoundError("api key not found for project");
    }
    return record;
  }

  private consumeUsage(tenantId: string, projectId: string, operation: string, options: { units?: number; apiKeyId?: string; idempotencyKey?: string; requestId?: string; runId?: string } = {}): JsonRecord {
    const units = options.units ?? 1;
    this.cloud.quota.consume(tenantId, projectId, operation, units);
    const usageEventId = newId("usage");
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      usage_event_id: usageEventId,
      tenant_id: tenantId,
      project_id: projectId,
      run_id: options.runId ?? null,
      api_key_id: options.apiKeyId ?? null,
      operation,
      units,
      source: "local_control_plane",
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.store.usage_ledger[usageEventId] = record;
    return cloneJson(record) as JsonRecord;
  }

  private appendAudit(tenantId: string, projectId: string, action: string, options: { targetId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string; before?: JsonRecord; after?: JsonRecord } = {}): JsonRecord {
    const auditEventId = newId("audit");
    const before = options.before ?? {};
    const after = options.after ?? {};
    const previousEvent = auditChainTail(Object.values(this.store.audit_log), tenantId, projectId);
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      audit_event_id: auditEventId,
      tenant_id: tenantId,
      project_id: projectId,
      chain_position: previousEvent === null ? 0 : Number(previousEvent.chain_position ?? -1) + 1,
      previous_audit_event_id: previousEvent?.audit_event_id ?? null,
      previous_audit_event_sha256: previousEvent?.audit_event_sha256 ?? null,
      api_key_id: options.apiKeyId ?? null,
      action,
      target_id: options.targetId ?? null,
      before_sha256: Object.keys(before).length > 0 ? sha256(JSON.stringify(sortJson(before))) : null,
      after_sha256: Object.keys(after).length > 0 ? sha256(JSON.stringify(sortJson(after))) : null,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    record.audit_event_sha256 = auditEventHash(record);
    this.store.audit_log[auditEventId] = record;
    return cloneJson(record) as JsonRecord;
  }

  private consumeApiKeyRate(record: JsonRecord, operation: string): void {
    const keyId = String(record.key_id);
    const tenantId = String(record.tenant_id);
    const projectId = String(record.project_id);
    const candidates = Object.values(this.store.api_key_rate_limits)
      .filter((bucket) => bucket.tenant_id === tenantId && bucket.project_id === projectId && bucket.key_id === keyId && (bucket.operation === operation || bucket.operation === "*"));
    for (const bucket of candidates) {
      const used = Number(bucket.used ?? 0);
      const limit = Number(bucket.limit ?? 0);
      if (used + 1 > limit) {
        throw new ValidationError(`api key rate limit exceeded for ${keyId}: ${operation}`);
      }
    }
    for (const bucket of candidates) {
      bucket.used = Number(bucket.used ?? 0) + 1;
      bucket.remaining = Math.max(0, Number(bucket.limit ?? 0) - Number(bucket.used ?? 0));
      bucket.last_used_at = utcNow();
    }
  }

  private idempotencyLookup(tenantId: string, projectId: string, operation: string, idempotencyKey: string | undefined, requestFingerprintSha256: string): JsonRecord | null {
    if (idempotencyKey === undefined) return null;
    const record = this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)];
    if (record === undefined || !isRecord(record.response)) return null;
    if (record.request_fingerprint_sha256 !== requestFingerprintSha256) {
      throw new ValidationError(`idempotency key conflict for ${operation}: request fingerprint mismatch`);
    }
    return { ...cloneJson(record.response), idempotent_replay: true } as JsonRecord;
  }

  private idempotencyStore(tenantId: string, projectId: string, operation: string, idempotencyKey: string | undefined, requestFingerprintSha256: string, response: JsonRecord): void {
    if (idempotencyKey === undefined) return;
    this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)] = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      operation,
      idempotency_key: idempotencyKey,
      request_fingerprint_sha256: requestFingerprintSha256,
      response: cloneJson(response),
      created_at: utcNow(),
    };
  }
}

export class SaaSControlPlaneRouter {
  readonly service: SaaSControlPlaneService;

  constructor(service = new SaaSControlPlaneService()) {
    this.service = service;
  }

  handle(method: string, path: string, body: JsonRecord = {}): SaaSRouterResponse {
    const upperMethod = method.toUpperCase();
    const parts = path.split("/").filter(Boolean);
    try {
      if (upperMethod === "GET" && (parts.join("/") === "healthz" || parts.join("/") === "v1/healthz")) {
        return { status_code: 200, body: saasHealthz() };
      }
      if (upperMethod === "GET" && (parts.join("/") === "openapi.json" || parts.join("/") === "openapi" || parts.join("/") === "healthz/openapi" || parts.join("/") === "v1/openapi")) {
        return { status_code: 200, body: exportSaaSOpenApiSpec() };
      }
      if (upperMethod === "POST" && parts.join("/") === "v1/bootstrap") {
        return { status_code: 201, body: this.service.bootstrapProject({ tenantName: String(body.tenant_name ?? body.tenantName ?? ""), projectName: String(body.project_name ?? body.projectName ?? ""), tenantId: optionalString(body.tenant_id), projectId: optionalString(body.project_id) }) };
      }
      if (parts.length >= 4 && parts[0] === "v1" && parts[1] === "projects") {
        const projectId = parts[2];
        const tenantId = String(body.tenant_id ?? body.organization_id ?? body.tenant ?? "");
        if (!tenantId) throw new ValidationError("tenant_id is required");
        const authKeyId = optionalString(body.auth_key_id ?? body.api_key_id);
        if (upperMethod === "POST" && parts.length === 4 && parts[3] === "api-keys") {
          return { status_code: 201, body: this.service.createApiKey(tenantId, projectId, { name: String(body.name ?? "API key"), scopes: arrayOfStrings(body.scopes), keyId: optionalString(body.key_id), authKeyId, revealSecret: Boolean(body.reveal_secret) }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "api-keys") {
          return { status_code: 200, body: { api_keys: this.service.listApiKeys(tenantId, projectId, { authKeyId }) } };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "authenticate") {
          return { status_code: 200, body: this.service.authenticateApiKey(tenantId, projectId, { keyId: parts[4], scope: String(body.scope ?? "") }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "verify") {
          return { status_code: 200, body: this.service.verifyApiKeySecret(tenantId, projectId, { keyId: parts[4], secret: String(body.secret ?? ""), scope: optionalString(body.scope) }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "rate-limit") {
          return { status_code: 200, body: this.service.configureApiKeyRateLimit(tenantId, projectId, { keyId: parts[4], operation: String(body.operation ?? "*"), limit: Number(body.limit ?? 0), period: optionalString(body.period), authKeyId }) };
        }
        if (upperMethod === "GET" && parts.length === 5 && parts[3] === "api-keys" && parts[4] === "rate-limits") {
          return { status_code: 200, body: this.service.apiKeyRateLimitSnapshot(tenantId, projectId, { keyId: optionalString(body.key_id) }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "revoke") {
          return { status_code: 200, body: this.service.revokeApiKey(tenantId, projectId, parts[4], { authKeyId }) };
        }
        if (upperMethod === "POST" && parts.length === 4 && parts[3] === "sdk-submit") {
          return { status_code: 202, body: this.service.sdkSubmitRun(tenantId, projectId, { datasetId: String(body.dataset_id ?? ""), agentRef: String(body.agent_ref ?? ""), runId: optionalString(body.run_id), metadata: isRecord(body.metadata) ? body.metadata : undefined, apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "usage") {
          return { status_code: 200, body: this.service.usageSnapshot(tenantId, projectId, { authKeyId }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "audit-log") {
          return { status_code: 200, body: this.service.auditSnapshot(tenantId, projectId, { authKeyId, runId: optionalString(body.run_id), actionPrefix: optionalString(body.action_prefix), limit: body.limit === undefined ? undefined : Number(body.limit) }) };
        }
        if (upperMethod === "POST" && parts.length === 5 && parts[3] === "audit-chain" && parts[4] === "verify") {
          return { status_code: 200, body: this.service.verifyAuditChain(tenantId, projectId, { authKeyId, requestId: optionalString(body.request_id) }) };
        }
        if (parts.length >= 6 && parts[3] === "runs") {
          const runId = parts[4];
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "upload") {
            return { status_code: 202, body: this.service.uploadRunResult(tenantId, projectId, runId, isRecord(body.result) ? body.result : body, { uploadId: optionalString(body.upload_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "trace-events") {
            return { status_code: 202, body: this.service.ingestTrace(tenantId, projectId, runId, Array.isArray(body.observations) ? (body.observations.filter(isRecord) as JsonRecord[]) : [], { batchId: optionalString(body.batch_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "lifecycle") {
            return { status_code: 200, body: this.service.lifecycleSnapshot(tenantId, projectId, runId) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "release-gate") {
            return { status_code: 200, body: this.service.evaluateReleaseGate(tenantId, projectId, runId, { evaluator: optionalString(body.evaluator), minScore: body.min_score === undefined ? undefined : Number(body.min_score), requiredTraceCompleteness: body.required_trace_completeness === undefined ? undefined : Number(body.required_trace_completeness), authKeyId, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "release-evidence") {
            return { status_code: 200, body: this.service.buildReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId }) };
          }
          if (upperMethod === "POST" && parts.length === 7 && parts[5] === "release-evidence" && parts[6] === "verify") {
            return { status_code: 200, body: this.service.verifyReleaseEvidencePacket(tenantId, projectId, runId, { authKeyId, packet: isRecord(body.packet) ? body.packet : undefined, requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts.length === 6 && parts[5] === "artifact-manifests") {
            return { status_code: 202, body: this.service.createArtifactManifest(tenantId, projectId, runId, isRecord(body.manifest) ? body.manifest : body, { artifactId: optionalString(body.artifact_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts.length === 6 && parts[5] === "artifact-manifests") {
            return { status_code: 200, body: { artifact_manifests: this.service.listArtifactManifests(tenantId, projectId, runId, { authKeyId }) } };
          }
        }
      }
      throw new ValidationError(`unsupported route: ${upperMethod} ${path}`);
    } catch (error) {
      const code = error instanceof Error && "code" in error ? String((error as Error & { code?: string }).code) : "validation_error";
      return { status_code: code === "not_found" ? 404 : 400, body: { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, error: { code, message: error instanceof Error ? error.message : String(error) } } };
    }
  }
}


export class SaaSHttpJsonTransport implements SaaSClientTransport {
  readonly baseUrl: string;
  readonly headers: Record<string, string>;
  private readonly fetchImpl: SaaSFetchLike;

  constructor(options: SaaSHttpTransportOptions) {
    if (!options.baseUrl || !String(options.baseUrl).trim()) throw new ValidationError("baseUrl must be a non-empty string");
    const candidate = options.fetch ?? (globalThis.fetch as unknown as SaaSFetchLike | undefined);
    if (candidate === undefined) throw new ValidationError("fetch implementation is required for SaaS HTTP transport");
    this.baseUrl = String(options.baseUrl).replace(/\/+$/, "");
    this.headers = { ...(options.headers ?? {}) };
    this.fetchImpl = candidate;
  }

  async requestJson(method: string, path: string, body: JsonRecord = {}): Promise<JsonRecord> {
    const upperMethod = method.toUpperCase();
    const url = new URL(path.startsWith("/") ? path : `/${path}`, `${this.baseUrl}/`);
    const init: { method: string; headers: Record<string, string>; body?: string } = {
      method: upperMethod,
      headers: { accept: "application/json", ...this.headers },
    };
    if (upperMethod === "GET") {
      for (const [key, value] of Object.entries(body)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
      }
    } else {
      init.headers["content-type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const response = await this.fetchImpl(url, init);
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = { error: { code: "invalid_json", message: await response.text() } };
    }
    if (!isRecord(payload)) {
      throw new ValidationError(`SaaS HTTP response must be a JSON object for ${upperMethod} ${url.pathname}`);
    }
    if (!response.ok) {
      const err = isRecord(payload.error) ? payload.error : {};
      throw new ValidationError(String(err.message ?? `SaaS HTTP request failed with status ${response.status}`));
    }
    return payload;
  }
}

export function saasHealthz(): JsonRecord {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    status: "ok",
    local_only: true,
    ashr_api_used: false,
    service: "ashr-saas-control-plane",
    client_version: SAAS_CLIENT_VERSION,
    openapi_path: "/openapi.json",
    legacy_openapi_path: "/healthz/openapi",
  };
}

export function exportSaaSOpenApiSpec(options: { title?: string; version?: string; serverUrl?: string } = {}): JsonRecord {
  const title = options.title ?? "Ashr SaaS Control Plane Runtime";
  const version = options.version ?? CONTROL_PLANE_SCHEMA_VERSION;
  const serverUrl = options.serverUrl ?? "http://localhost";
  const json = { "application/json": { schema: { type: "object", additionalProperties: true } } };
  const response = (description: string): JsonRecord => ({ description, content: json });
  return {
    openapi: CONTROL_PLANE_OPENAPI_VERSION,
    info: { title, version, description: "Local hosted/self-host control-plane HTTP adapter for SaaSControlPlaneRouter.", "x-schema-version": SAAS_OPENAPI_SCHEMA_VERSION, "x-client-version": SAAS_CLIENT_VERSION },
    servers: [{ url: serverUrl }],
    paths: {
      "/healthz": { get: { operationId: "healthz", responses: { "200": response("Health check") } } },
      "/openapi.json": { get: { operationId: "exportOpenApi", responses: { "200": response("OpenAPI document") } } },
      "/healthz/openapi": { get: { operationId: "exportOpenApiLegacy", responses: { "200": response("OpenAPI document") } } },
      "/v1/bootstrap": { post: { operationId: "bootstrapProject", requestBody: { content: json }, responses: { "201": response("Bootstrap result") } } },
      "/v1/projects/{project_id}/api-keys": {
        get: { operationId: "listApiKeys", parameters: pathTenantParameters(), responses: { "200": response("API keys") } },
        post: { operationId: "createApiKey", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "201": response("API key") } },
      },
      "/v1/projects/{project_id}/api-keys/{key_id}/authenticate": { post: { operationId: "authenticateApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Authentication result") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/verify": { post: { operationId: "verifyApiKeySecret", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Secret verification result") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/rate-limit": {
        post: { operationId: "configureApiKeyRateLimit", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("API key rate limit") } },
      },
      "/v1/projects/{project_id}/api-keys/rate-limits": { get: { operationId: "apiKeyRateLimitSnapshot", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], responses: { "200": response("API key rate limit snapshot") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/revoke": { post: { operationId: "revokeApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Revocation result") } } },
      "/v1/projects/{project_id}/sdk-submit": { post: { operationId: "sdkSubmit", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "202": response("Submitted run") } } },
      "/v1/projects/{project_id}/runs/{run_id}/upload": { post: { operationId: "uploadRun", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Uploaded run result") } } },
      "/v1/projects/{project_id}/runs/{run_id}/trace-events": { post: { operationId: "ingestTrace", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Trace batch") } } },
      "/v1/projects/{project_id}/runs/{run_id}/lifecycle": { get: { operationId: "lifecycle", parameters: pathTenantParameters("run_id"), responses: { "200": response("Run lifecycle") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-gate": { post: { operationId: "evaluateReleaseGate", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "200": response("Release gate decision") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-evidence": { get: { operationId: "buildReleaseEvidencePacket", parameters: pathTenantParameters("run_id"), responses: { "200": response("Release evidence packet") } } },
      "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": { post: { operationId: "verifyReleaseEvidencePacket", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "200": response("Release evidence packet verification") } } },
      "/v1/projects/{project_id}/usage": { get: { operationId: "usageSnapshot", parameters: pathTenantParameters(), responses: { "200": response("Usage ledger snapshot") } } },
      "/v1/projects/{project_id}/audit-log": { get: { operationId: "auditSnapshot", parameters: pathTenantParameters(), responses: { "200": response("Audit log snapshot") } } },
      "/v1/projects/{project_id}/audit-chain/verify": { post: { operationId: "verifyAuditChain", parameters: pathTenantParameters(), requestBody: { content: json }, responses: { "200": response("Audit chain verification") } } },
      "/v1/projects/{project_id}/runs/{run_id}/artifact-manifests": {
        get: { operationId: "listArtifactManifests", parameters: pathTenantParameters("run_id"), responses: { "200": response("Artifact manifests") } },
        post: { operationId: "createArtifactManifest", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Artifact manifest receipt") } },
      },
    },
    components: { schemas: { JsonRecord: { type: "object", additionalProperties: true } } },
    "x-local-only": true,
    "x-ashr-api-used": false,
  };
}



export class SecretInputError extends Error {
  code = "secret_input_error";
}

export class SaaSIngestionClient {
  readonly service: SaaSControlPlaneService;
  readonly transport?: SaaSClientTransport;

  constructor(options: { service?: SaaSControlPlaneService; transport?: SaaSClientTransport; baseUrl?: string; fetch?: SaaSFetchLike; headers?: Record<string, string> } = {}) {
    this.service = options.service ?? new SaaSControlPlaneService();
    this.transport = options.transport ?? (options.baseUrl !== undefined ? new SaaSHttpJsonTransport({ baseUrl: options.baseUrl, fetch: options.fetch, headers: options.headers }) : undefined);
  }

  static forBaseUrl(baseUrl: string, options: { fetch?: SaaSFetchLike; headers?: Record<string, string> } = {}): SaaSIngestionClient {
    return new SaaSIngestionClient({ baseUrl, fetch: options.fetch, headers: options.headers });
  }

  async requestJson(method: string, path: string, body: JsonRecord = {}): Promise<JsonRecord> {
    if (this.transport !== undefined) return this.transport.requestJson(method, path, body);
    return new SaaSControlPlaneRouter(this.service).handle(method, path, body).body;
  }

  async healthz(): Promise<JsonRecord> {
    return this.requestJson("GET", "/healthz");
  }

  async openApi(options: { serverUrl?: string } = {}): Promise<JsonRecord> {
    if (this.transport !== undefined) return this.requestJson("GET", "/openapi.json");
    return exportSaaSOpenApiSpec({ serverUrl: options.serverUrl });
  }

  static async fromStateFile(inputPath: string): Promise<SaaSIngestionClient> {
    return new SaaSIngestionClient({ service: await SaaSControlPlaneService.fromStateFile(inputPath) });
  }

  async writeState(outputPath: string): Promise<string> {
    return this.service.writeState(outputPath);
  }

  snapshotState(): SaaSControlPlaneState {
    return this.service.snapshotState();
  }

  bootstrapProject(options: { tenantName: string; projectName: string; tenantId?: string; projectId?: string; datasetId?: string; datasetName?: string; cases?: JsonRecord[] }): JsonRecord {
    const result = this.service.bootstrapProject(options);
    if (options.datasetId !== undefined) {
      const tenant = result.tenant as JsonRecord;
      const project = result.project as JsonRecord;
      result.dataset = this.service.cloud.createDataset(String(tenant.tenant_id), String(project.project_id), {
        datasetId: options.datasetId,
        name: options.datasetName ?? "SDK Bootstrap Dataset",
        cases: options.cases ?? [{ id: "sdk-bootstrap-case", prompt: "local bootstrap", expected: { text: "local bootstrap" } }],
        metadata: { created_by: "ashr_clone.ts_saas_client", local_only: true },
      });
    }
    return envelope("bootstrap_project", result);
  }

  createApiKey(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; revealSecret?: boolean; apiKey?: string }): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("create_api_key", this.service.createApiKey(tenantId, projectId, options));
  }

  verifyApiKeySecret(tenantId: string, projectId: string, options: { keyId: string; secret: string; scope?: string }): JsonRecord {
    return envelope("verify_api_key_secret", this.service.verifyApiKeySecret(tenantId, projectId, options));
  }

  configureApiKeyRateLimit(tenantId: string, projectId: string, options: { keyId: string; operation: string; limit: number; period?: string; authKeyId?: string }): JsonRecord {
    return envelope("configure_api_key_rate_limit", this.service.configureApiKeyRateLimit(tenantId, projectId, options));
  }

  apiKeyRateLimitSnapshot(tenantId: string, projectId: string, options: { keyId?: string } = {}): JsonRecord {
    return envelope("api_key_rate_limit_snapshot", this.service.apiKeyRateLimitSnapshot(tenantId, projectId, options));
  }

  listApiKeys(tenantId: string, projectId: string, options: { authKeyId?: string; apiKey?: string } = {}): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("list_api_keys", { api_keys: this.service.listApiKeys(tenantId, projectId, options) });
  }

  revokeApiKey(tenantId: string, projectId: string, keyId: string, options: { authKeyId?: string; apiKey?: string } = {}): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("revoke_api_key", this.service.revokeApiKey(tenantId, projectId, keyId, options));
  }

  sdkSubmit(tenantId: string, projectId: string, options: { datasetId: string; agentRef: string; runId?: string; metadata?: JsonRecord; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string }): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("sdk_submit", this.service.sdkSubmitRun(tenantId, projectId, {
      datasetId: options.datasetId,
      agentRef: options.agentRef,
      runId: options.runId,
      metadata: { client: SAAS_CLIENT_VERSION, ...(options.metadata ?? {}) },
      apiKeyId: options.apiKeyId,
      idempotencyKey: options.idempotencyKey,
      requestId: options.requestId,
    }));
  }

  uploadRun(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: { uploadId?: string; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("upload_run", this.service.uploadRunResult(tenantId, projectId, runId, result, options));
  }

  ingestTrace(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId?: string; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("ingest_trace", this.service.ingestTrace(tenantId, projectId, runId, observations, options));
  }

  lifecycle(tenantId: string, projectId: string, runId: string): JsonRecord {
    return envelope("lifecycle", this.service.lifecycleSnapshot(tenantId, projectId, runId));
  }

  usage(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): JsonRecord {
    return envelope("usage", this.service.usageSnapshot(tenantId, projectId, options));
  }

  auditLog(tenantId: string, projectId: string, options: { runId?: string; actionPrefix?: string; authKeyId?: string; limit?: number } = {}): JsonRecord {
    return envelope("audit_log", this.service.auditSnapshot(tenantId, projectId, options));
  }

  verifyAuditChain(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): JsonRecord {
    return envelope("audit_chain_verify", this.service.verifyAuditChain(tenantId, projectId, options));
  }

  evaluateReleaseGate(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): JsonRecord {
    return envelope("release_gate", this.service.evaluateReleaseGate(tenantId, projectId, runId, options));
  }

  buildReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string } = {}): JsonRecord {
    return envelope("release_evidence", this.service.buildReleaseEvidencePacket(tenantId, projectId, runId, options));
  }

  verifyReleaseEvidencePacket(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): JsonRecord {
    return envelope("release_evidence_verify", this.service.verifyReleaseEvidencePacket(tenantId, projectId, runId, options));
  }

  createArtifactManifest(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    return envelope("artifact_manifest", this.service.createArtifactManifest(tenantId, projectId, runId, manifest, options));
  }

  listArtifactManifests(tenantId: string, projectId: string, runId?: string, options: { authKeyId?: string } = {}): JsonRecord {
    return envelope("artifact_manifests", { artifact_manifests: this.service.listArtifactManifests(tenantId, projectId, runId, options) });
  }

  async createApiKeyHttp(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; revealSecret?: boolean; apiKey?: string }): Promise<JsonRecord> {
    rejectRawApiKey(options.apiKey);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { tenant_id: tenantId, name: options.name, scopes: options.scopes, key_id: options.keyId, auth_key_id: options.authKeyId, reveal_secret: options.revealSecret });
    return envelope("create_api_key", body);
  }

  async listApiKeysHttp(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { tenant_id: tenantId, auth_key_id: options.authKeyId });
    return envelope("list_api_keys", body);
  }

  async verifyApiKeySecretHttp(tenantId: string, projectId: string, options: { keyId: string; secret: string; scope?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(options.keyId)}/verify`, { tenant_id: tenantId, secret: options.secret, scope: options.scope });
    return envelope("verify_api_key_secret", body);
  }

  async configureApiKeyRateLimitHttp(tenantId: string, projectId: string, options: { keyId: string; operation: string; limit: number; period?: string; authKeyId?: string }): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(options.keyId)}/rate-limit`, { tenant_id: tenantId, operation: options.operation, limit: options.limit, period: options.period, auth_key_id: options.authKeyId });
    return envelope("configure_api_key_rate_limit", body);
  }

  async apiKeyRateLimitSnapshotHttp(tenantId: string, projectId: string, options: { keyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/api-keys/rate-limits`, { tenant_id: tenantId, key_id: options.keyId });
    return envelope("api_key_rate_limit_snapshot", body);
  }

  async sdkSubmitHttp(tenantId: string, projectId: string, options: { datasetId: string; agentRef: string; runId?: string; metadata?: JsonRecord; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string }): Promise<JsonRecord> {
    rejectRawApiKey(options.apiKey);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/sdk-submit`, { tenant_id: tenantId, dataset_id: options.datasetId, agent_ref: options.agentRef, run_id: options.runId, metadata: { client: SAAS_CLIENT_VERSION, ...(options.metadata ?? {}) }, api_key_id: options.apiKeyId, idempotency_key: options.idempotencyKey, request_id: options.requestId });
    return envelope("sdk_submit", body);
  }

  async uploadRunHttp(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: { uploadId?: string; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string } = {}): Promise<JsonRecord> {
    rejectRawApiKey(options.apiKey);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/upload`, { tenant_id: tenantId, result, upload_id: options.uploadId, api_key_id: options.apiKeyId, idempotency_key: options.idempotencyKey, request_id: options.requestId });
    return envelope("upload_run", body);
  }

  async ingestTraceHttp(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId?: string; apiKeyId?: string; apiKey?: string; idempotencyKey?: string; requestId?: string } = {}): Promise<JsonRecord> {
    rejectRawApiKey(options.apiKey);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/trace-events`, { tenant_id: tenantId, observations, batch_id: options.batchId, api_key_id: options.apiKeyId, idempotency_key: options.idempotencyKey, request_id: options.requestId });
    return envelope("ingest_trace", body);
  }

  async lifecycleHttp(tenantId: string, projectId: string, runId: string): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/lifecycle`, { tenant_id: tenantId });
    return envelope("lifecycle", body);
  }

  async usageHttp(tenantId: string, projectId: string, options: { authKeyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/usage`, { tenant_id: tenantId, auth_key_id: options.authKeyId });
    return envelope("usage", body);
  }

  async auditLogHttp(tenantId: string, projectId: string, options: { runId?: string; actionPrefix?: string; authKeyId?: string; limit?: number } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/audit-log`, { tenant_id: tenantId, run_id: options.runId, action_prefix: options.actionPrefix, auth_key_id: options.authKeyId, limit: options.limit });
    return envelope("audit_log", body);
  }

  async verifyAuditChainHttp(tenantId: string, projectId: string, options: { authKeyId?: string; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/audit-chain/verify`, { tenant_id: tenantId, auth_key_id: options.authKeyId, request_id: options.requestId });
    return envelope("audit_chain_verify", body);
  }

  async evaluateReleaseGateHttp(tenantId: string, projectId: string, runId: string, options: { evaluator?: string; minScore?: number; requiredTraceCompleteness?: number; authKeyId?: string; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-gate`, { tenant_id: tenantId, evaluator: options.evaluator, min_score: options.minScore, required_trace_completeness: options.requiredTraceCompleteness, auth_key_id: options.authKeyId, request_id: options.requestId });
    return envelope("release_gate", body);
  }

  async buildReleaseEvidencePacketHttp(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-evidence`, { tenant_id: tenantId, auth_key_id: options.authKeyId });
    return envelope("release_evidence", body);
  }

  async verifyReleaseEvidencePacketHttp(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string; packet?: JsonRecord; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/release-evidence/verify`, { tenant_id: tenantId, auth_key_id: options.authKeyId, packet: options.packet, request_id: options.requestId });
    return envelope("release_evidence_verify", body);
  }

  async createArtifactManifestHttp(tenantId: string, projectId: string, runId: string, manifest: JsonRecord, options: { artifactId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/artifact-manifests`, { tenant_id: tenantId, manifest, artifact_id: options.artifactId, api_key_id: options.apiKeyId, idempotency_key: options.idempotencyKey, request_id: options.requestId });
    return envelope("artifact_manifest", body);
  }

  async listArtifactManifestsHttp(tenantId: string, projectId: string, runId: string, options: { authKeyId?: string } = {}): Promise<JsonRecord> {
    const body = await this.requestJson("GET", `/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/artifact-manifests`, { tenant_id: tenantId, auth_key_id: options.authKeyId });
    return envelope("artifact_manifests", body);
  }
}
export const snapshotSaaSControlPlane = (service: SaaSControlPlaneService): SaaSControlPlaneState => service.snapshotState();
export const writeSaaSControlPlaneState = (service: SaaSControlPlaneService, outputPath: string): Promise<string> => service.writeState(outputPath);
export const saasControlPlaneFromState = (payload: unknown): SaaSControlPlaneService => SaaSControlPlaneService.fromState(payload);
export const saasControlPlaneFromStateFile = (inputPath: string): Promise<SaaSControlPlaneService> => SaaSControlPlaneService.fromStateFile(inputPath);

type CliOptions = Record<string, string | boolean | string[]>;

const SAAS_CLI_COMMANDS = new Set(["api-key-create", "api-key-list", "api-key-verify", "api-key-rate-limit", "api-key-rate-limits", "release-gate", "audit-log", "audit-chain-verify", "release-evidence", "release-evidence-verify"]);

export async function runSaaSCli(argv: string[] = process.argv.slice(2)): Promise<JsonRecord> {
  const commandIndex = argv.findIndex((arg) => SAAS_CLI_COMMANDS.has(arg));
  const command = commandIndex >= 0 ? argv[commandIndex] : "state";
  const options = parseCliArgs(commandIndex >= 0 ? [...argv.slice(0, commandIndex), ...argv.slice(commandIndex + 1)] : argv);
  if (options.help || options.h) {
    return { operation: "help", usage: saasCliUsage() };
  }
  const baseUrl = stringOption(options, "base-url", false);
  const stateInput = stringOption(options, "state-input", false);
  const stateOutput = stringOption(options, "state-output", false);
  if (baseUrl !== undefined && stateInput !== undefined) throw new SecretInputError("--base-url cannot be combined with --state-input");
  if (baseUrl !== undefined && stateOutput !== undefined) throw new SecretInputError("--base-url cannot be combined with --state-output");
  const client = baseUrl !== undefined ? SaaSIngestionClient.forBaseUrl(baseUrl) : (stateInput !== undefined ? await SaaSIngestionClient.fromStateFile(stateInput) : new SaaSIngestionClient());
  let result: JsonRecord;
  switch (command) {
    case "api-key-create":
      result = baseUrl !== undefined
        ? await client.createApiKeyHttp(projectTenant(options).tenantId, projectTenant(options).projectId, {
          name: stringOption(options, "name", true), scopes: stringListOption(options, "scope", true), keyId: stringOption(options, "key-id", false), authKeyId: stringOption(options, "auth-key-id", false), revealSecret: Boolean(options["reveal-secret"]),
        })
        : client.createApiKey(projectTenant(options).tenantId, projectTenant(options).projectId, {
          name: stringOption(options, "name", true), scopes: stringListOption(options, "scope", true), keyId: stringOption(options, "key-id", false), authKeyId: stringOption(options, "auth-key-id", false), revealSecret: Boolean(options["reveal-secret"]),
        });
      break;
    case "api-key-list":
      result = baseUrl !== undefined
        ? await client.listApiKeysHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.listApiKeys(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "api-key-verify":
      result = baseUrl !== undefined
        ? await client.verifyApiKeySecretHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), secret: stringOption(options, "secret", true), scope: stringOption(options, "scope", false) })
        : client.verifyApiKeySecret(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), secret: stringOption(options, "secret", true), scope: stringOption(options, "scope", false) });
      break;
    case "api-key-rate-limit":
      result = baseUrl !== undefined
        ? await client.configureApiKeyRateLimitHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), operation: stringOption(options, "operation", true), limit: numberOption(options, "limit", true), period: stringOption(options, "period", false), authKeyId: stringOption(options, "auth-key-id", false) })
        : client.configureApiKeyRateLimit(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", true), operation: stringOption(options, "operation", true), limit: numberOption(options, "limit", true), period: stringOption(options, "period", false), authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "api-key-rate-limits":
      result = baseUrl !== undefined
        ? await client.apiKeyRateLimitSnapshotHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", false) })
        : client.apiKeyRateLimitSnapshot(projectTenant(options).tenantId, projectTenant(options).projectId, { keyId: stringOption(options, "key-id", false) });
      break;
    case "release-gate":
      result = baseUrl !== undefined
        ? await client.evaluateReleaseGateHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { evaluator: stringOption(options, "evaluator", false), minScore: optionalNumberOption(options, "min-score"), requiredTraceCompleteness: optionalNumberOption(options, "required-trace-completeness"), authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.evaluateReleaseGate(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { evaluator: stringOption(options, "evaluator", false), minScore: optionalNumberOption(options, "min-score"), requiredTraceCompleteness: optionalNumberOption(options, "required-trace-completeness"), authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "audit-log":
      result = baseUrl !== undefined
        ? await client.auditLogHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { runId: stringOption(options, "run-id", false), actionPrefix: stringOption(options, "action-prefix", false), authKeyId: stringOption(options, "auth-key-id", false), limit: optionalNumberOption(options, "limit") })
        : client.auditLog(projectTenant(options).tenantId, projectTenant(options).projectId, { runId: stringOption(options, "run-id", false), actionPrefix: stringOption(options, "action-prefix", false), authKeyId: stringOption(options, "auth-key-id", false), limit: optionalNumberOption(options, "limit") });
      break;
    case "audit-chain-verify":
      result = baseUrl !== undefined
        ? await client.verifyAuditChainHttp(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) })
        : client.verifyAuditChain(projectTenant(options).tenantId, projectTenant(options).projectId, { authKeyId: stringOption(options, "auth-key-id", false), requestId: stringOption(options, "request-id", false) });
      break;
    case "release-evidence":
      result = baseUrl !== undefined
        ? await client.buildReleaseEvidencePacketHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false) })
        : client.buildReleaseEvidencePacket(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false) });
      break;
    case "release-evidence-verify":
      {
        const packet = await packetOption(options);
      result = baseUrl !== undefined
        ? await client.verifyReleaseEvidencePacketHttp(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false), packet, requestId: stringOption(options, "request-id", false) })
        : client.verifyReleaseEvidencePacket(projectTenant(options).tenantId, projectTenant(options).projectId, stringOption(options, "run-id", true), { authKeyId: stringOption(options, "auth-key-id", false), packet, requestId: stringOption(options, "request-id", false) });
      }
      break;
    default:
      throw new SecretInputError(`unsupported command: ${command}`);
  }
  if (stateOutput !== undefined) result.state_output = await client.writeState(stateOutput);
  return result;
}

function parseCliArgs(args: string[]): CliOptions {
  const options: CliOptions = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) throw new SecretInputError(`unexpected argument: ${arg}`);
    const name = arg.slice(2);
    const next = args[index + 1];
    if (next === undefined || next.startsWith("--")) {
      options[name] = true;
      continue;
    }
    const current = options[name];
    if (current === undefined) options[name] = next;
    else if (Array.isArray(current)) current.push(next);
    else options[name] = [String(current), next];
    index += 1;
  }
  return options;
}

function stringOption(options: CliOptions, name: string, required: true): string;
function stringOption(options: CliOptions, name: string, required: false): string | undefined;
function stringOption(options: CliOptions, name: string, required: boolean): string | undefined {
  const value = options[name];
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[value.length - 1];
  if (required) throw new SecretInputError(`missing required --${name}`);
  return undefined;
}

function stringListOption(options: CliOptions, name: string, required: true): string[];
function stringListOption(options: CliOptions, name: string, required: false): string[] | undefined;
function stringListOption(options: CliOptions, name: string, required: boolean): string[] | undefined {
  const value = options[name];
  const list = Array.isArray(value) ? value.map(String) : (typeof value === "string" ? [value] : []);
  if (list.length === 0 && required) throw new SecretInputError(`missing required --${name}`);
  return list.length > 0 ? list : undefined;
}

function numberOption(options: CliOptions, name: string, required: boolean): number {
  const raw = options[name];
  const value = typeof raw === "string" ? raw : (Array.isArray(raw) ? raw[raw.length - 1] : undefined);
  if (value === undefined) throw new SecretInputError(`missing required --${name}`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new SecretInputError(`--${name} must be numeric`);
  return parsed;
}

function optionalNumberOption(options: CliOptions, name: string): number | undefined {
  const raw = options[name];
  const value = typeof raw === "string" ? raw : (Array.isArray(raw) ? raw[raw.length - 1] : undefined);
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new SecretInputError(`--${name} must be numeric`);
  return parsed;
}

async function packetOption(options: CliOptions): Promise<JsonRecord | undefined> {
  const packetJson = stringOption(options, "packet-json", false);
  const packetFile = stringOption(options, "packet-file", false);
  if (packetJson !== undefined && packetFile !== undefined) throw new SecretInputError("provide only one of --packet-json or --packet-file");
  if (packetJson !== undefined) {
    const parsed = JSON.parse(packetJson) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError("--packet-json must decode to an object");
    return parsed;
  }
  if (packetFile !== undefined) {
    assertPublicControlPlanePath(packetFile);
    const fs = await import("node:fs/promises");
    const parsed = JSON.parse(await fs.readFile(packetFile, "utf8")) as unknown;
    if (!isRecord(parsed)) throw new SecretInputError("--packet-file must contain a JSON object");
    return parsed;
  }
  return undefined;
}

function projectTenant(options: CliOptions): { tenantId: string; projectId: string } {
  return { tenantId: stringOption(options, "tenant-id", true), projectId: stringOption(options, "project-id", true) };
}

function saasCliUsage(): string {
  return "usage: node dist/saas.js [--state-input PATH] [--state-output PATH] [--base-url URL] <api-key-create|api-key-list|api-key-verify|api-key-rate-limit|api-key-rate-limits|release-gate|audit-log|audit-chain-verify|release-evidence|release-evidence-verify> [options]";
}

async function mainSaaSCli(): Promise<number> {
  try {
    process.stdout.write(`${JSON.stringify(await runSaaSCli(), null, 0)}\n`);
    return 0;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`saas ingestion cli error: ${message}\n`);
    return 2;
  }
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  void mainSaaSCli().then((code) => { process.exitCode = code; });
}


function envelope(operation: string, result: JsonRecord): JsonRecord { return { schema_version: CONTROL_PLANE_SCHEMA_VERSION, client_version: SAAS_CLIENT_VERSION, operation, result: cloneJson(result) }; }
function rejectRawApiKey(value: unknown): void { if (value !== undefined && value !== null && String(value).trim() !== "") throw new SecretInputError("raw API key values are not accepted by the local SaaS client; pass apiKeyId/keyId handles only"); }
function assertPublicControlPlanePath(inputPath: string): void { const normalized = resolve(inputPath).replaceAll("\\", "/").toLowerCase(); for (const part of [".secrets", "private_refs"]) { if (normalized.includes("/" + part + "/") || normalized.endsWith("/" + part)) throw new SecretInputError("refusing to read or write control-plane state under " + part); } }

function pathTenantParameters(extraPathName?: string): JsonRecord[] {
  const params: JsonRecord[] = [
    { name: "project_id", in: "path", required: true, schema: { type: "string" } },
    { name: "tenant_id", in: "query", required: false, schema: { type: "string" } },
  ];
  if (extraPathName !== undefined) params.splice(1, 0, { name: extraPathName, in: "path", required: true, schema: { type: "string" } });
  return params;
}

function publicApiKey(record: JsonRecord): JsonRecord {
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    tenant_id: record.tenant_id,
    project_id: record.project_id,
    key_id: record.key_id,
    name: record.name,
    prefix: record.prefix,
    secret_hash_present: Boolean(record.secret_hash_sha256),
    secret_value_present: false,
    status: record.status,
    scopes: Array.isArray(record.scopes) ? [...record.scopes] : [],
    created_at: record.created_at,
    revoked_at: record.revoked_at,
    last_used_at: record.last_used_at,
    one_time_secret_displayed: Boolean(record.one_time_secret_displayed),
    verify_mode: record.verify_mode ?? null,
  };
}

function normalizeScope(scope: string): string {
  const parsed = String(scope).trim();
  if (!parsed) throw new ValidationError("required scope must not be empty");
  return parsed;
}

function scopeAllows(grantedScopes: unknown, requiredScope: string): boolean {
  const granted = new Set((Array.isArray(grantedScopes) ? grantedScopes : []).map((scope) => String(scope).trim()).filter(Boolean));
  const expanded = new Set(granted);
  for (const scope of granted) {
    for (const item of SCOPE_ALIASES[scope] ?? []) expanded.add(item);
  }
  if (expanded.has("*") || expanded.has(ADMIN_ALL_SCOPE) || expanded.has(requiredScope)) return true;
  for (const scope of expanded) {
    if (scope.endsWith(":*") && requiredScope.startsWith(`${scope.slice(0, -2)}:`)) return true;
  }
  return false;
}

function idempotencyRecordKey(tenantId: string, projectId: string, operation: string, idempotencyKey: string): string {
  return sha256(`${tenantId}:${projectId}:${operation}:${idempotencyKey}`);
}

function apiKeyRateKey(tenantId: string, projectId: string, keyId: string, operation: string, period: string): string {
  return sha256(`${tenantId}:${projectId}:${keyId}:${operation}:${period}`);
}

function auditEventHash(event: JsonRecord): string {
  const payload = cloneJson(event) as JsonRecord;
  delete payload.audit_event_sha256;
  return sha256(JSON.stringify(sortJson(payload)));
}

function auditEventsInChainOrder(events: JsonRecord[]): JsonRecord[] {
  return events
    .map((event) => cloneJson(event) as JsonRecord)
    .sort((left, right) => {
      const position = Number(left.chain_position ?? 0) - Number(right.chain_position ?? 0);
      if (position !== 0) return position;
      const created = String(left.created_at ?? "").localeCompare(String(right.created_at ?? ""));
      if (created !== 0) return created;
      return String(left.audit_event_id ?? "").localeCompare(String(right.audit_event_id ?? ""));
    });
}

function auditChainTail(events: JsonRecord[], tenantId: string, projectId: string): JsonRecord | null {
  const ordered = auditEventsInChainOrder(events.filter((event) => event.tenant_id === tenantId && event.project_id === projectId));
  return ordered.length > 0 ? ordered[ordered.length - 1] : null;
}

export function verifyAuditHashChain(events: JsonRecord[]): JsonRecord {
  const ordered = auditEventsInChainOrder(events);
  let previousHash: string | null = null;
  let previousId: string | null = null;
  const failures: JsonRecord[] = [];
  ordered.forEach((event, index) => {
    const eventId = String(event.audit_event_id ?? "");
    const expectedHash = auditEventHash(event);
    if (event.audit_event_sha256 !== expectedHash) failures.push({ audit_event_id: eventId, reason: "event_hash_mismatch" });
    if ((event.previous_audit_event_id ?? null) !== previousId) failures.push({ audit_event_id: eventId, reason: "previous_event_id_mismatch" });
    if ((event.previous_audit_event_sha256 ?? null) !== previousHash) failures.push({ audit_event_id: eventId, reason: "previous_event_hash_mismatch" });
    if (Number(event.chain_position ?? -1) !== index) failures.push({ audit_event_id: eventId, reason: "chain_position_mismatch" });
    previousHash = String(event.audit_event_sha256 ?? expectedHash);
    previousId = eventId;
  });
  return {
    verified: failures.length === 0,
    event_count: ordered.length,
    head_audit_event_id: ordered[0]?.audit_event_id ?? null,
    head_audit_event_sha256: ordered[0]?.audit_event_sha256 ?? null,
    tail_audit_event_id: ordered[ordered.length - 1]?.audit_event_id ?? null,
    tail_audit_event_sha256: ordered[ordered.length - 1]?.audit_event_sha256 ?? null,
    failures,
  };
}

export function verifyReleaseEvidencePacket(packet: JsonRecord): JsonRecord {
  const payload = cloneJson(packet) as JsonRecord;
  const integrity = isRecord(payload.integrity) ? payload.integrity : {};
  const expectedHash = integrity.packet_sha256 ?? null;
  delete payload.integrity;
  const actualHash = sha256(JSON.stringify(sortJson(payload)));
  const failures: JsonRecord[] = [];
  if (expectedHash !== actualHash) failures.push({ reason: "packet_sha256_mismatch", expected: expectedHash, actual: actualHash });
  const redaction = isRecord(packet.redaction) ? packet.redaction : {};
  if (redaction.raw_payload_included === true) failures.push({ reason: "raw_payload_included" });
  if (redaction.secret_value_present === true) failures.push({ reason: "secret_value_present" });
  failures.push(...findSuspiciousReleasePacketFields(packet));
  return {
    schema_version: "ashr.clone.release_evidence_packet_verification.v1",
    verified: failures.length === 0,
    packet_sha256: expectedHash,
    actual_packet_sha256: actualHash,
    failures,
  };
}

function releasePacketBindings(service: SaaSControlPlaneService, tenantId: string, projectId: string, runId: string, authKeyId: string): JsonRecord {
  const lifecycle = service.lifecycleSnapshot(tenantId, projectId, runId);
  const artifacts = service.listArtifactManifests(tenantId, projectId, runId, { authKeyId });
  const usage = service.usageSnapshot(tenantId, projectId, { authKeyId });
  const audit = service.auditSnapshot(tenantId, projectId, { runId, limit: 200, authKeyId });
  const uploads = Array.isArray(lifecycle.uploads) ? lifecycle.uploads : [];
  const traces = Array.isArray(lifecycle.trace_batches) ? lifecycle.trace_batches : [];
  const events = Array.isArray(usage.events) ? usage.events : [];
  const operationTotals = isRecord(usage.totals) ? usage.totals : {};
  const auditChain = isRecord(audit.chain) ? audit.chain : {};
  return {
    schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
    counts: { uploads: uploads.length, trace_batches: traces.length, artifacts: artifacts.length },
    hashes: {
      uploads_sha256: sha256(JSON.stringify(sortJson(uploads))),
      trace_batches_sha256: sha256(JSON.stringify(sortJson(traces))),
      artifact_manifests_sha256: sha256(JSON.stringify(sortJson(artifacts))),
      usage_ledger_sha256: sha256(JSON.stringify(sortJson(events))),
    },
    usage: { operation_totals: cloneJson(operationTotals), billable_units: Object.values(operationTotals).reduce<number>((total, item) => total + Number(item ?? 0), 0) },
    audit_chain: { verified: auditChain.verified ?? null, event_count: auditChain.event_count ?? 0, tail_audit_event_sha256: auditChain.tail_audit_event_sha256 ?? null },
    bundle_root_sha256: sha256(JSON.stringify(sortJson({ artifacts, usage: operationTotals, audit_chain: auditChain }))),
  };
}

function verifyReleasePacketBindings(packet: JsonRecord, expected: JsonRecord): JsonRecord[] {
  const failures: JsonRecord[] = [];
  const packetCounts = isRecord(packet.counts) ? packet.counts : {};
  const expectedCounts = isRecord(expected.counts) ? expected.counts : {};
  for (const key of ["uploads", "trace_batches", "artifacts"]) {
    if (packetCounts[key] !== undefined && packetCounts[key] !== expectedCounts[key]) failures.push({ reason: `${key}_count_mismatch`, expected: expectedCounts[key], actual: packetCounts[key] });
  }
  const packetUsage = isRecord(packet.usage) ? packet.usage : {};
  const expectedUsage = isRecord(expected.usage) ? expected.usage : {};
  if (packetUsage.operation_totals !== undefined && JSON.stringify(sortJson(packetUsage.operation_totals)) !== JSON.stringify(sortJson(expectedUsage.operation_totals))) failures.push({ reason: "usage_operation_totals_mismatch", expected: expectedUsage.operation_totals, actual: packetUsage.operation_totals });
  if (packetUsage.billable_units !== undefined && packetUsage.billable_units !== expectedUsage.billable_units) failures.push({ reason: "usage_billable_units_mismatch", expected: expectedUsage.billable_units, actual: packetUsage.billable_units });
  const packetAudit = isRecord(packet.audit_chain) ? packet.audit_chain : {};
  const expectedAudit = isRecord(expected.audit_chain) ? expected.audit_chain : {};
  if (packetAudit.tail_audit_event_sha256 !== undefined && packetAudit.tail_audit_event_sha256 !== null && packetAudit.tail_audit_event_sha256 !== expectedAudit.tail_audit_event_sha256) failures.push({ reason: "audit_chain_tail_mismatch", expected: expectedAudit.tail_audit_event_sha256, actual: packetAudit.tail_audit_event_sha256 });
  const packetHashes = isRecord(packet.hashes) ? packet.hashes : {};
  const expectedHashes = isRecord(expected.hashes) ? expected.hashes : {};
  const artifactHash = packetHashes.artifacts_sha256 ?? packetHashes.artifact_manifests_sha256;
  if (artifactHash !== undefined && artifactHash !== expectedHashes.artifact_manifests_sha256) failures.push({ reason: "artifact_manifest_hash_mismatch", expected: expectedHashes.artifact_manifests_sha256, actual: artifactHash });
  const packetBindings = isRecord(packet.bindings) ? packet.bindings : {};
  if (packetBindings.bundle_root_sha256 !== undefined && packetBindings.bundle_root_sha256 !== expected.bundle_root_sha256) failures.push({ reason: "bundle_root_sha256_mismatch", expected: expected.bundle_root_sha256, actual: packetBindings.bundle_root_sha256 });
  return failures;
}

const SUSPICIOUS_RELEASE_PACKET_KEYS = new Set([
  "api_key",
  "authorization",
  "bearer",
  "cookie",
  "set_cookie",
  "password",
  "token",
  "access_token",
  "refresh_token",
  "client_secret",
  "secret",
  "raw_payload",
  "payload",
]);

function findSuspiciousReleasePacketFields(value: unknown, path = "$" ): JsonRecord[] {
  const failures: JsonRecord[] = [];
  if (Array.isArray(value)) {
    value.forEach((item, index) => failures.push(...findSuspiciousReleasePacketFields(item, `${path}[${index}]`)));
    return failures;
  }
  if (isRecord(value)) {
    Object.entries(value).forEach(([key, item]) => {
      const normalizedKey = key.toLowerCase().replace(/-/g, "_");
      const itemPath = `${path}.${key}`;
      if (SUSPICIOUS_RELEASE_PACKET_KEYS.has(normalizedKey)) failures.push({ reason: "suspicious_field_present", path: itemPath });
      failures.push(...findSuspiciousReleasePacketFields(item, itemPath));
    });
    return failures;
  }
  if (typeof value === "string") {
    const lowered = value.toLowerCase();
    if (lowered.startsWith("bearer ") || lowered.includes("ashr_api_key=")) failures.push({ reason: "suspicious_value_present", path });
  }
  return failures;
}

function secretHash(secret: string): string {
  return sha256(String(secret));
}

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function requestFingerprintSha256(request: JsonRecord): string {
  return sha256(JSON.stringify(sortJson(request)));
}

function newId(prefix: string): string {
  return `${prefix}_${Math.random().toString(16).slice(2, 14).padEnd(12, "0")}`;
}

function utcNow(): string {
  return new Date().toISOString();
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function jsonRecord(value: JsonRecord): JsonRecord {
  return cloneJson(sortJson(value)) as JsonRecord;
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => sortJson(item));
  if (isRecord(value)) {
    const result: JsonRecord = {};
    for (const key of Object.keys(value).sort()) result[key] = sortJson(value[key]);
    return result;
  }
  if (value === undefined) return null;
  return value;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stateBucket(payload: JsonRecord, key: string): Record<string, JsonRecord> {
  const value = payload[key] ?? {};
  if (!isRecord(value)) throw new ValidationError(`control-plane state ${key} must be an object`);
  const result: Record<string, JsonRecord> = {};
  for (const [itemKey, itemValue] of Object.entries(value)) {
    if (!isRecord(itemValue)) throw new ValidationError(`control-plane state ${key} records must be objects`);
    result[itemKey] = cloneJson(itemValue);
  }
  return result;
}

function optionalString(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  const parsed = String(value);
  return parsed.length > 0 ? parsed : undefined;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}
