import { CloudApiService, NotFoundError, ValidationError } from "./index.js";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import type { JsonRecord } from "./index.js";

export const CONTROL_PLANE_SCHEMA_VERSION = "ashr.clone.saas_control_plane.v1";
export const SAAS_CLIENT_VERSION = "ashr.clone.ts_saas_ingestion_client.v1";
export const SAAS_OPENAPI_SCHEMA_VERSION = "ashr.clone.saas_openapi.v1";
export const SAAS_QUOTA_LIMITS: Record<string, number> = {
  "api_key.create": 100,
  "run.upload": 10000,
  "sdk.submit": 10000,
  "trace.ingest": 100000,
};

export const API_KEY_ADMIN_SCOPE = "api_key:write";
export const API_KEY_READ_SCOPE = "api_key:read";
export const RUN_CREATE_SCOPE = "run:create";
export const RUN_UPLOAD_SCOPE = "run:upload";
export const TRACE_INGEST_SCOPE = "trace:ingest";
export const ADMIN_ALL_SCOPE = "admin:all";
export const USAGE_READ_SCOPE = "usage:read";
export const AUDIT_READ_SCOPE = "audit:read";

const SCOPE_ALIASES: Record<string, string[]> = {
  "key:admin": [API_KEY_ADMIN_SCOPE, API_KEY_READ_SCOPE],
  "key:read": [API_KEY_READ_SCOPE],
  "sdk:submit": [RUN_CREATE_SCOPE],
  "runs:write": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE],
  "write:runs": [RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE],
  "traces:write": [TRACE_INGEST_SCOPE],
  [API_KEY_ADMIN_SCOPE]: [API_KEY_READ_SCOPE],
  [ADMIN_ALL_SCOPE]: ["*"],
};

export interface SaaSControlPlaneStore {
  api_keys: Record<string, JsonRecord>;
  uploads: Record<string, JsonRecord>;
  trace_batches: Record<string, JsonRecord>;
  sdk_submissions: Record<string, JsonRecord>;
  audit_log: Record<string, JsonRecord>;
  usage_ledger: Record<string, JsonRecord>;
  idempotency_keys: Record<string, JsonRecord>;
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
    uploads: { ...(seed.uploads ?? {}) },
    trace_batches: { ...(seed.trace_batches ?? {}) },
    sdk_submissions: { ...(seed.sdk_submissions ?? {}) },
    audit_log: { ...(seed.audit_log ?? {}) },
    usage_ledger: { ...(seed.usage_ledger ?? {}) },
    idempotency_keys: { ...(seed.idempotency_keys ?? {}) },
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

  createApiKey(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string }): JsonRecord {
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
    const now = utcNow();
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      key_id: keyId,
      name: options.name,
      prefix: "ashr_local_***",
      secret_value_present: false,
      status: "active",
      scopes,
      created_at: now,
      revoked_at: null,
      last_used_at: null,
    };
    this.store.api_keys[keyId] = record;
    const publicRecord = publicApiKey(record);
    this.appendAudit(tenantId, projectId, "api_key.create", { targetId: keyId, apiKeyId: options.authKeyId, after: publicRecord });
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

  authenticateApiKey(tenantId: string, projectId: string, options: { keyId: string; scope: string }): JsonRecord {
    const record = this.apiKeyRecord(tenantId, projectId, options.keyId);
    const requiredScope = normalizeScope(options.scope);
    if (record.status !== "active") {
      throw new ValidationError(`api key is not active: ${options.keyId}`);
    }
    if (!scopeAllows(record.scopes, requiredScope)) {
      throw new ValidationError(`api key ${options.keyId} missing required scope: ${requiredScope}`);
    }
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

  sdkSubmitRun(tenantId: string, projectId: string, options: { datasetId: string; agentRef: string; runId?: string; metadata?: JsonRecord; apiKeyId?: string; idempotencyKey?: string; requestId?: string }): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: "sdk:submit" });
    }
    const idem = this.idempotencyLookup(tenantId, projectId, "sdk.submit", options.idempotencyKey);
    if (idem !== null) return idem;
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
    this.idempotencyStore(tenantId, projectId, "sdk.submit", options.idempotencyKey, response);
    this.appendAudit(tenantId, projectId, "sdk.submit", { targetId: run.run_id, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { run_id: run.run_id, submission_id: submission.submission_id } });
    return response;
  }

  uploadRunResult(tenantId: string, projectId: string, runId: string, result: JsonRecord, options: { uploadId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: RUN_UPLOAD_SCOPE });
    }
    const idem = this.idempotencyLookup(tenantId, projectId, "run.upload", options.idempotencyKey);
    if (idem !== null) return idem;
    const run = this.cloud.getRun(tenantId, projectId, runId);
    this.consumeUsage(tenantId, projectId, "run.upload", { apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const payload = jsonRecord(result);
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
    this.idempotencyStore(tenantId, projectId, "run.upload", options.idempotencyKey, response);
    this.appendAudit(tenantId, projectId, "run.upload", { targetId: runId, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, after: { upload_id: uploadId, payload_sha256: digest } });
    return response;
  }

  ingestTrace(tenantId: string, projectId: string, runId: string, observations: JsonRecord[], options: { batchId?: string; apiKeyId?: string; idempotencyKey?: string; requestId?: string } = {}): JsonRecord {
    if (options.apiKeyId !== undefined) {
      this.authenticateApiKey(tenantId, projectId, { keyId: options.apiKeyId, scope: TRACE_INGEST_SCOPE });
    }
    const idem = this.idempotencyLookup(tenantId, projectId, "trace.ingest", options.idempotencyKey);
    if (idem !== null) return idem;
    this.cloud.getRun(tenantId, projectId, runId);
    if (observations.length === 0) {
      throw new ValidationError("trace ingestion requires at least one observation");
    }
    this.consumeUsage(tenantId, projectId, "trace.ingest", { units: observations.length, apiKeyId: options.apiKeyId, idempotencyKey: options.idempotencyKey, requestId: options.requestId, runId });
    const normalized = observations.map((item) => jsonRecord(item));
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
    this.idempotencyStore(tenantId, projectId, "trace.ingest", options.idempotencyKey, response);
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

  usageSnapshot(tenantId: string, projectId: string): JsonRecord {
    this.cloud.getProject(tenantId, projectId);
    const events = Object.values(this.store.usage_ledger).filter((item) => item.tenant_id === tenantId && item.project_id === projectId);
    const totals: Record<string, number> = {};
    for (const event of events) {
      const op = String(event.operation);
      totals[op] = (totals[op] ?? 0) + Number(event.units ?? 0);
    }
    return { schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION, tenant_id: tenantId, project_id: projectId, events, totals, quota: this.cloud.quotaSnapshot(tenantId, projectId) };
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
        uploads: stateBucket(control, "uploads"),
        trace_batches: stateBucket(control, "trace_batches"),
        sdk_submissions: stateBucket(control, "sdk_submissions"),
        audit_log: stateBucket(control, "audit_log"),
        usage_ledger: stateBucket(control, "usage_ledger"),
        idempotency_keys: stateBucket(control, "idempotency_keys"),
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
    const record: JsonRecord = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      audit_event_id: auditEventId,
      tenant_id: tenantId,
      project_id: projectId,
      api_key_id: options.apiKeyId ?? null,
      action,
      target_id: options.targetId ?? null,
      before_sha256: Object.keys(before).length > 0 ? sha256(JSON.stringify(sortJson(before))) : null,
      after_sha256: Object.keys(after).length > 0 ? sha256(JSON.stringify(sortJson(after))) : null,
      idempotency_key: options.idempotencyKey ?? null,
      request_id: options.requestId ?? null,
      created_at: utcNow(),
    };
    this.store.audit_log[auditEventId] = record;
    return cloneJson(record) as JsonRecord;
  }

  private idempotencyLookup(tenantId: string, projectId: string, operation: string, idempotencyKey?: string): JsonRecord | null {
    if (idempotencyKey === undefined) return null;
    const record = this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)];
    if (record === undefined || !isRecord(record.response)) return null;
    return { ...cloneJson(record.response), idempotent_replay: true } as JsonRecord;
  }

  private idempotencyStore(tenantId: string, projectId: string, operation: string, idempotencyKey: string | undefined, response: JsonRecord): void {
    if (idempotencyKey === undefined) return;
    this.store.idempotency_keys[idempotencyRecordKey(tenantId, projectId, operation, idempotencyKey)] = {
      schema_version: CONTROL_PLANE_SCHEMA_VERSION as typeof CONTROL_PLANE_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      operation,
      idempotency_key: idempotencyKey,
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
      if (upperMethod === "GET" && (parts.join("/") === "openapi" || parts.join("/") === "healthz/openapi" || parts.join("/") === "v1/openapi")) {
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
          return { status_code: 201, body: this.service.createApiKey(tenantId, projectId, { name: String(body.name ?? "API key"), scopes: arrayOfStrings(body.scopes), keyId: optionalString(body.key_id), authKeyId }) };
        }
        if (upperMethod === "GET" && parts.length === 4 && parts[3] === "api-keys") {
          return { status_code: 200, body: { api_keys: this.service.listApiKeys(tenantId, projectId, { authKeyId }) } };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "authenticate") {
          return { status_code: 200, body: this.service.authenticateApiKey(tenantId, projectId, { keyId: parts[4], scope: String(body.scope ?? "") }) };
        }
        if (upperMethod === "POST" && parts.length === 6 && parts[3] === "api-keys" && parts[5] === "revoke") {
          return { status_code: 200, body: this.service.revokeApiKey(tenantId, projectId, parts[4], { authKeyId }) };
        }
        if (upperMethod === "POST" && parts.length === 4 && parts[3] === "sdk-submit") {
          return { status_code: 202, body: this.service.sdkSubmitRun(tenantId, projectId, { datasetId: String(body.dataset_id ?? ""), agentRef: String(body.agent_ref ?? ""), runId: optionalString(body.run_id), metadata: isRecord(body.metadata) ? body.metadata : undefined, apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
        }
        if (parts.length === 6 && parts[3] === "runs") {
          const runId = parts[4];
          if (upperMethod === "POST" && parts[5] === "upload") {
            return { status_code: 202, body: this.service.uploadRunResult(tenantId, projectId, runId, isRecord(body.result) ? body.result : body, { uploadId: optionalString(body.upload_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "POST" && parts[5] === "trace-events") {
            return { status_code: 202, body: this.service.ingestTrace(tenantId, projectId, runId, Array.isArray(body.observations) ? (body.observations.filter(isRecord) as JsonRecord[]) : [], { batchId: optionalString(body.batch_id), apiKeyId: authKeyId, idempotencyKey: optionalString(body.idempotency_key), requestId: optionalString(body.request_id) }) };
          }
          if (upperMethod === "GET" && parts[5] === "lifecycle") {
            return { status_code: 200, body: this.service.lifecycleSnapshot(tenantId, projectId, runId) };
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
    service: "ashr-clone-saas-control-plane",
    client_version: SAAS_CLIENT_VERSION,
    openapi_path: "/healthz/openapi",
  };
}

export function exportSaaSOpenApiSpec(options: { title?: string; version?: string; serverUrl?: string } = {}): JsonRecord {
  const title = options.title ?? "Ashr Clone SaaS Control Plane";
  const version = options.version ?? SAAS_OPENAPI_SCHEMA_VERSION;
  const serverUrl = options.serverUrl ?? "http://localhost";
  const json = { "application/json": { schema: { type: "object", additionalProperties: true } } };
  const response = (description: string): JsonRecord => ({ description, content: json });
  return {
    openapi: "3.1.0",
    info: { title, version, "x-schema-version": SAAS_OPENAPI_SCHEMA_VERSION, "x-client-version": SAAS_CLIENT_VERSION },
    servers: [{ url: serverUrl }],
    paths: {
      "/healthz": { get: { operationId: "healthz", responses: { "200": response("Health check") } } },
      "/healthz/openapi": { get: { operationId: "exportOpenApi", responses: { "200": response("OpenAPI document") } } },
      "/v1/bootstrap": { post: { operationId: "bootstrapProject", requestBody: { content: json }, responses: { "201": response("Bootstrap result") } } },
      "/v1/projects/{project_id}/api-keys": {
        get: { operationId: "listApiKeys", parameters: pathTenantParameters(), responses: { "200": response("API keys") } },
        post: { operationId: "createApiKey", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "201": response("API key") } },
      },
      "/v1/projects/{project_id}/api-keys/{key_id}/authenticate": { post: { operationId: "authenticateApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Authentication result") } } },
      "/v1/projects/{project_id}/api-keys/{key_id}/revoke": { post: { operationId: "revokeApiKey", parameters: pathTenantParameters("key_id"), requestBody: { content: json }, responses: { "200": response("Revocation result") } } },
      "/v1/projects/{project_id}/sdk-submit": { post: { operationId: "sdkSubmit", parameters: [{ name: "project_id", in: "path", required: true, schema: { type: "string" } }], requestBody: { content: json }, responses: { "202": response("Submitted run") } } },
      "/v1/projects/{project_id}/runs/{run_id}/upload": { post: { operationId: "uploadRun", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Uploaded run result") } } },
      "/v1/projects/{project_id}/runs/{run_id}/trace-events": { post: { operationId: "ingestTrace", parameters: pathTenantParameters("run_id"), requestBody: { content: json }, responses: { "202": response("Trace batch") } } },
      "/v1/projects/{project_id}/runs/{run_id}/lifecycle": { get: { operationId: "lifecycle", parameters: pathTenantParameters("run_id"), responses: { "200": response("Run lifecycle") } } },
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
    if (this.transport !== undefined) return this.requestJson("GET", "/healthz/openapi");
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

  createApiKey(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; apiKey?: string }): JsonRecord {
    rejectRawApiKey(options.apiKey);
    return envelope("create_api_key", this.service.createApiKey(tenantId, projectId, options));
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

  usage(tenantId: string, projectId: string): JsonRecord {
    return envelope("usage", this.service.usageSnapshot(tenantId, projectId));
  }

  async createApiKeyHttp(tenantId: string, projectId: string, options: { name: string; scopes: string[]; keyId?: string; authKeyId?: string; apiKey?: string }): Promise<JsonRecord> {
    rejectRawApiKey(options.apiKey);
    const body = await this.requestJson("POST", `/v1/projects/${encodeURIComponent(projectId)}/api-keys`, { tenant_id: tenantId, name: options.name, scopes: options.scopes, key_id: options.keyId, auth_key_id: options.authKeyId });
    return envelope("create_api_key", body);
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
}
export const snapshotSaaSControlPlane = (service: SaaSControlPlaneService): SaaSControlPlaneState => service.snapshotState();
export const writeSaaSControlPlaneState = (service: SaaSControlPlaneService, outputPath: string): Promise<string> => service.writeState(outputPath);
export const saasControlPlaneFromState = (payload: unknown): SaaSControlPlaneService => SaaSControlPlaneService.fromState(payload);
export const saasControlPlaneFromStateFile = (inputPath: string): Promise<SaaSControlPlaneService> => SaaSControlPlaneService.fromStateFile(inputPath);


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
    secret_hash_present: false,
    secret_value_present: false,
    status: record.status,
    scopes: Array.isArray(record.scopes) ? [...record.scopes] : [],
    created_at: record.created_at,
    revoked_at: record.revoked_at,
    last_used_at: record.last_used_at,
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

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
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
