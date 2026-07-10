export * from "./api-client.js";
export * from "./account-readiness.js";
export * from "./billing.js";
export * from "./calibrate.js";
export * from "./china-payments.js";
export * from "./cloud-queue.js";
export * from "./commercial.js";
export * from "./dataset-adapter.js";
export * from "./evidence.js";
export * from "./github-oauth.js";
export * from "./github-oauth-cli.js";
export * from "./runner.js";
export * from "./saas.js";
export * from "./stripe-executor.js";
export * from "./trace.js";

export const CLOUD_API_SCHEMA_VERSION = "ashr.clone.cloud_api.v1";
export const AGENT_INPUT_SCHEMA_VERSION = "ashr.clone.agent_input.v1";
export const AGENT_TURN_SCHEMA_VERSION = "ashr.clone.agent_turn.v1";
export const RUN_RESULT_SCHEMA_VERSION = "ashr.clone.run_result.v1";
export const DEFAULT_QUEUE_LEASE_SECONDS = 300;

export type JsonRecord = Record<string, unknown>;
export type AgentInputPartType = "text" | "image" | "audio" | "file" | "video";
export type AgentHandler = (agentInput: AgentInput, caseRecord: JsonRecord) => AgentTurnLike | Promise<AgentTurnLike>;
export type AgentTurnLike = string | Partial<AgentTurn> | JsonRecord;

export interface AgentInputPart extends JsonRecord {
  type: AgentInputPartType;
  text?: string;
  path?: string;
  url?: string;
  uri?: string;
  source?: string;
  mime_type?: string;
  mimeType?: string;
  name?: string;
  filename?: string;
  fileName?: string;
  description?: string;
}

export interface AgentInput {
  schema_version: typeof AGENT_INPUT_SCHEMA_VERSION;
  text: string;
  parts: AgentInputPart[];
  metadata: JsonRecord;
}

export interface AgentTurn {
  schema_version: typeof AGENT_TURN_SCHEMA_VERSION;
  text: string;
  tool_calls: JsonRecord[];
  status: string;
  latency_ms: number;
  metadata: JsonRecord;
  error?: JsonRecord;
}

export interface CaseResult extends JsonRecord {
  case_id: string;
  scenario_id?: string;
  status: string;
  prompt?: string;
  expected?: JsonRecord;
  actual?: string;
  agent_output: AgentTurn;
  observations: JsonRecord[];
}

export interface TenantRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  name: string;
  created_at: string;
  metadata: JsonRecord;
}

export interface ProjectRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  name: string;
  created_at: string;
  metadata: JsonRecord;
}

export interface DatasetRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  dataset_id: string;
  name: string;
  case_count: number;
  cases: JsonRecord[];
  created_at: string;
  metadata: JsonRecord;
}

export interface RequestRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  request_id: string;
  name: string;
  status: string;
  request_input_schema: JsonRecord;
  accepted_inputs: JsonRecord;
  created_at: string;
  updated_at: string;
  metadata: JsonRecord;
}

export interface RunResult extends JsonRecord {
  run_id?: string;
  dataset_id?: string;
  runner_id?: string;
  status?: string;
  total_cases?: number;
  cases?: JsonRecord[];
}

export interface CloudDemoSummary extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant: { tenant_id: string; name: string };
  project: { tenant_id: string; project_id: string; name: string };
  dataset: { dataset_id: string; case_count: number; name: string };
  run: {
    run_id: string;
    dataset_id: string;
    status: string;
    result_status: string;
    runner_id: string;
    total_cases: number;
    passed: number;
    failed: number;
    errored: number;
    timed_out: number;
    trace_completeness: number;
    observations: number;
    total_tool_calls: number;
  };
  poll: { status: string; run_id: string };
  cases: Array<{
    case_id: string;
    status: string;
    expected: JsonRecord;
    actual: JsonRecord;
    tool_calls: JsonRecord[];
    observations: number;
  }>;
  replay: { available: boolean; local_only: true; run_id: string; event_count: number; vm_stream_count: number };
  sdk_submission?: JsonRecord;
  quota: Pick<QuotaSnapshot, "used" | "remaining">;
  fixture: CloudRunFixture;
  metadata: { local_only: true; ashr_api_used: false };
}

export interface CloudDemoSdkSubmitter {
  sdkSubmit(
    tenantId: string,
    projectId: string,
    options: {
      datasetId?: string;
      dataset_id?: string;
      agentRef?: string;
      agent_ref?: string;
      runId?: string;
      run_id?: string;
      metadata?: JsonRecord;
      idempotencyKey?: string;
      idempotency_key?: string;
      requestId?: string;
      request_id?: string;
    },
  ): JsonRecord;
}

export interface RunRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  dataset_id: string;
  run_id: string;
  status: string;
  result_status: string;
  runner_id: string;
  total_cases: number;
  observations: JsonRecord[];
  result: JsonRecord;
  created_at: string;
  updated_at: string;
  status_history?: JsonRecord[];
  lease_owner_id?: string | null;
  lease_expires_at?: string | null;
  lease_heartbeat_at?: string | null;
  lease_reclaim_count?: number;
  error?: JsonRecord;
  metadata: JsonRecord;
}

export interface PollRunRecord extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: string;
  updated_at: string;
  run: RunRecord;
}

export interface QuotaSnapshot extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  limits: Record<string, number>;
  used: Record<string, number>;
  remaining: Record<string, number>;
}

export interface CloudRunFixture {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenant_id: string;
  project_id: string;
  dataset_id: string;
  run_id: string;
  status: string;
  run_result: JsonRecord;
  observations: JsonRecord[];
  metadata: {
    local_only: true;
    ashr_api_used: false;
  };
}

export interface CloudStoreSnapshot {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  tenants: Record<string, TenantRecord>;
  projects: Record<string, ProjectRecord>;
  datasets: Record<string, DatasetRecord>;
  requests: Record<string, RequestRecord>;
  runs: Record<string, RunRecord>;
}

export interface CloudStateSnapshot extends JsonRecord {
  schema_version: typeof CLOUD_API_SCHEMA_VERSION;
  state_version: 1;
  kind: "local_cloud_state";
  store: CloudStoreSnapshot;
  quota: JsonRecord;
  metadata: { local_only: true; ashr_api_used: false };
}

export const DEFAULT_QUOTA_LIMITS: Record<string, number> = {
  "dataset.create": 1000,
  "observation.write": 100000,
  "request.create": 1000,
  "run.submit": 10000,
};

export const DEFAULT_REQUEST_INPUT_SCHEMA: JsonRecord = {
  type: "object",
  additionalProperties: true,
};

export const AGENT_INPUT_PART_TYPES: AgentInputPartType[] = ["text", "image", "audio", "file", "video"];
export const NON_TEXT_AGENT_INPUT_PART_TYPES: AgentInputPartType[] = ["image", "audio", "file", "video"];

export class CloudApiError extends Error {
  code = "cloud_api_error";

  toJSON(): JsonRecord {
    return { code: this.code, message: this.message };
  }
}

export class ValidationError extends CloudApiError {
  override code = "validation_error";
}

export class NotFoundError extends CloudApiError {
  override code = "not_found";
}

export class QuotaExceededError extends CloudApiError {
  override code = "quota_exceeded";
}

export class QuotaLedger {
  readonly defaultLimits: Record<string, number>;
  private readonly limits = new Map<string, Record<string, number>>();
  private readonly used = new Map<string, Record<string, number>>();

  constructor(defaultLimits: Record<string, number> = DEFAULT_QUOTA_LIMITS) {
    this.defaultLimits = { ...defaultLimits };
  }

  configure(tenantId: string, projectId: string, limits: Record<string, number>): QuotaSnapshot {
    const key = this.key(tenantId, projectId);
    const current = { ...(this.limits.get(key) ?? this.defaultLimits) };
    for (const [operation, limit] of Object.entries(limits)) {
      const parsed = Number(limit);
      if (!Number.isInteger(parsed) || parsed < 0) {
        throw new ValidationError("quota limits must be non-negative");
      }
      current[operation] = parsed;
    }
    this.limits.set(key, current);
    if (!this.used.has(key)) {
      this.used.set(key, {});
    }
    return this.snapshot(tenantId, projectId);
  }

  check(tenantId: string, projectId: string, operation: string, units = 1): void {
    const parsedUnits = positiveUnits(units);
    const key = this.key(tenantId, projectId);
    const limit = this.limitFor(key, operation);
    const used = this.used.get(key)?.[operation] ?? 0;
    if (used + parsedUnits > limit) {
      throw new QuotaExceededError(`quota exceeded for ${operation}: requested ${parsedUnits}, remaining ${Math.max(0, limit - used)}`);
    }
  }

  consume(tenantId: string, projectId: string, operation: string, units = 1): JsonRecord {
    const parsedUnits = positiveUnits(units);
    this.check(tenantId, projectId, operation, parsedUnits);
    const key = this.key(tenantId, projectId);
    const bucket = this.used.get(key) ?? {};
    bucket[operation] = (bucket[operation] ?? 0) + parsedUnits;
    this.used.set(key, bucket);
    const limit = this.limitFor(key, operation);
    return {
      operation,
      units: parsedUnits,
      used: bucket[operation],
      limit,
      remaining: Math.max(0, limit - bucket[operation]),
    };
  }

  snapshot(tenantId: string, projectId: string): QuotaSnapshot {
    const key = this.key(tenantId, projectId);
    const limits = { ...(this.limits.get(key) ?? this.defaultLimits) };
    const used = { ...(this.used.get(key) ?? {}) };
    const remaining: Record<string, number> = {};
    for (const [operation, limit] of Object.entries(limits)) {
      remaining[operation] = Math.max(0, limit - (used[operation] ?? 0));
    }
    return {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: tenantId,
      project_id: projectId,
      limits,
      used,
      remaining,
    };
  }

  state(): JsonRecord {
    const projectKeys = new Set([...this.limits.keys(), ...this.used.keys()]);
    return cloneJson({
      default_limits: this.defaultLimits,
      projects: Array.from(projectKeys)
        .sort()
        .map((key) => {
          const [tenantId, projectId] = this.splitKey(key);
          return {
            tenant_id: tenantId,
            project_id: projectId,
            limits: this.limits.get(key) ?? {},
            used: this.used.get(key) ?? {},
          };
        }),
    });
  }

  static fromState(payload: unknown): QuotaLedger {
    if (!isRecord(payload)) {
      return new QuotaLedger();
    }
    const defaultLimits = isRecord(payload.default_limits) ? numberRecord(payload.default_limits, "default_limits") : DEFAULT_QUOTA_LIMITS;
    const ledger = new QuotaLedger(defaultLimits);
    const projects = Array.isArray(payload.projects) ? payload.projects : [];
    for (const entry of projects) {
      if (!isRecord(entry)) {
        throw new ValidationError("quota project entries must be objects");
      }
      const tenantId = String(entry.tenant_id ?? "");
      const projectId = String(entry.project_id ?? "");
      requireId(tenantId, "tenant_id");
      requireId(projectId, "project_id");
      const key = ledger.key(tenantId, projectId);
      ledger.limits.set(key, isRecord(entry.limits) ? numberRecord(entry.limits, "quota limits") : {});
      ledger.used.set(key, isRecord(entry.used) ? numberRecord(entry.used, "quota used") : {});
    }
    return ledger;
  }

  private key(tenantId: string, projectId: string): string {
    return `${tenantId}\u0000${projectId}`;
  }

  private splitKey(key: string): [string, string] {
    const index = key.indexOf("\u0000");
    if (index === -1) {
      return [key, ""];
    }
    return [key.slice(0, index), key.slice(index + 1)];
  }

  private limitFor(key: string, operation: string): number {
    const configured = this.limits.get(key) ?? this.defaultLimits;
    return configured[operation] ?? this.defaultLimits[operation] ?? 0;
  }
}

export class InMemoryCloudStore {
  tenants: Record<string, TenantRecord> = {};
  projects: Record<string, ProjectRecord> = {};
  datasets: Record<string, DatasetRecord> = {};
  requests: Record<string, RequestRecord> = {};
  runs: Record<string, RunRecord> = {};

  snapshot(): CloudStoreSnapshot {
    return cloneJson({
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenants: this.tenants,
      projects: this.projects,
      datasets: this.datasets,
      requests: this.requests,
      runs: this.runs,
    });
  }

  static fromState(payload: unknown): InMemoryCloudStore {
    const storePayload = isRecord(payload) && isRecord(payload.store) ? payload.store : payload;
    if (!isRecord(storePayload)) {
      throw new ValidationError("cloud state store must be a JSON object");
    }
    const store = new InMemoryCloudStore();
    store.tenants = stateBucket<TenantRecord>(storePayload, "tenants");
    store.projects = stateBucket<ProjectRecord>(storePayload, "projects");
    store.datasets = stateBucket<DatasetRecord>(storePayload, "datasets");
    store.requests = stateBucket<RequestRecord>(storePayload, "requests");
    store.runs = stateBucket<RunRecord>(storePayload, "runs");
    return store;
  }
}

export interface CloudApiServiceOptions {
  store?: InMemoryCloudStore;
  quota?: QuotaLedger;
  clock?: () => string;
}

export class CloudApiService {
  readonly store: InMemoryCloudStore;
  readonly quota: QuotaLedger;
  private readonly clock: () => string;

  constructor(options: CloudApiServiceOptions = {}) {
    this.store = options.store ?? new InMemoryCloudStore();
    this.quota = options.quota ?? new QuotaLedger();
    this.clock = options.clock ?? utcNow;
  }

  createTenant(name: string, options: { tenantId?: string; metadata?: JsonRecord } = {}): TenantRecord {
    const tenantId = options.tenantId ?? newId("tenant");
    requireId(tenantId, "tenant_id");
    if (this.store.tenants[tenantId]) {
      throw new ValidationError(`tenant already exists: ${tenantId}`);
    }
    const record: TenantRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: tenantId,
      name: requireText(name, "name"),
      created_at: this.clock(),
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.tenants[tenantId] = record;
    return cloneJson(record);
  }

  createProject(tenantId: string, name: string, options: { projectId?: string; metadata?: JsonRecord } = {}): ProjectRecord {
    const tenant = this.getTenant(tenantId);
    const projectId = options.projectId ?? newId("project");
    requireId(projectId, "project_id");
    if (this.store.projects[projectId]) {
      throw new ValidationError(`project already exists: ${projectId}`);
    }
    const record: ProjectRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: tenant.tenant_id,
      project_id: projectId,
      name: requireText(name, "name"),
      created_at: this.clock(),
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.projects[projectId] = record;
    this.quota.configure(tenant.tenant_id, projectId, {});
    return cloneJson(record);
  }

  getTenant(tenantId: string): TenantRecord {
    const tenant = this.store.tenants[tenantId];
    if (!tenant) {
      throw new NotFoundError("tenant not found");
    }
    return cloneJson(tenant);
  }

  getProject(tenantId: string, projectId: string): ProjectRecord {
    const project = this.store.projects[projectId];
    if (!project || project.tenant_id !== tenantId) {
      throw new NotFoundError("project not found for tenant");
    }
    return cloneJson(project);
  }

  createDataset(
    tenantId: string,
    projectId: string,
    options: { name: string; cases: JsonRecord[]; datasetId?: string; metadata?: JsonRecord },
  ): DatasetRecord {
    const project = this.getProject(tenantId, projectId);
    const cases = options.cases.map((item) => jsonRecord(item));
    if (cases.length === 0) {
      throw new ValidationError("dataset cases must not be empty");
    }
    this.quota.check(project.tenant_id, project.project_id, "dataset.create");
    const datasetId = options.datasetId ?? newId("dataset");
    requireId(datasetId, "dataset_id");
    if (this.store.datasets[datasetId]) {
      throw new ValidationError(`dataset already exists: ${datasetId}`);
    }
    this.quota.consume(project.tenant_id, project.project_id, "dataset.create");
    const record: DatasetRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      dataset_id: datasetId,
      name: requireText(options.name, "name"),
      case_count: cases.length,
      cases,
      created_at: this.clock(),
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.datasets[datasetId] = record;
    return cloneJson(record);
  }

  getDataset(tenantId: string, projectId: string, datasetId: string): DatasetRecord {
    const dataset = this.store.datasets[datasetId];
    if (!dataset || dataset.tenant_id !== tenantId || dataset.project_id !== projectId) {
      throw new NotFoundError("dataset not found for tenant/project");
    }
    return cloneJson(dataset);
  }

  listDatasets(tenantId: string, projectId: string): DatasetRecord[] {
    this.getProject(tenantId, projectId);
    return Object.values(this.store.datasets)
      .filter((dataset) => dataset.tenant_id === tenantId && dataset.project_id === projectId)
      .map((dataset) => cloneJson(dataset));
  }

  createRequest(
    tenantId: string,
    projectId: string,
    options: {
      name: string;
      requestInputSchema?: JsonRecord;
      acceptedInputs?: JsonRecord;
      requestId?: string;
      metadata?: JsonRecord;
    },
  ): RequestRecord {
    const project = this.getProject(tenantId, projectId);
    this.quota.check(project.tenant_id, project.project_id, "request.create");
    const requestId = options.requestId ?? newId("request");
    requireId(requestId, "request_id");
    if (this.store.requests[requestId]) {
      throw new ValidationError(`request already exists: ${requestId}`);
    }
    this.quota.consume(project.tenant_id, project.project_id, "request.create");
    const now = this.clock();
    const record: RequestRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: project.tenant_id,
      project_id: project.project_id,
      request_id: requestId,
      name: requireText(options.name, "name"),
      status: "created",
      request_input_schema: jsonRecord(options.requestInputSchema ?? {}),
      accepted_inputs: jsonRecord(options.acceptedInputs ?? { text: true }),
      created_at: now,
      updated_at: now,
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.requests[requestId] = record;
    return cloneJson(record);
  }

  getRequest(tenantId: string, projectId: string, requestId: string): RequestRecord {
    const request = this.store.requests[requestId];
    if (!request || request.tenant_id !== tenantId || request.project_id !== projectId) {
      throw new NotFoundError("request not found for tenant/project");
    }
    return cloneJson(request);
  }

  listRequests(tenantId: string, projectId: string): RequestRecord[] {
    this.getProject(tenantId, projectId);
    return Object.values(this.store.requests)
      .filter((request) => request.tenant_id === tenantId && request.project_id === projectId)
      .map((request) => cloneJson(request));
  }

  submitRun(
    tenantId: string,
    projectId: string,
    options: { datasetId: string; runResult: RunResult; runId?: string; metadata?: JsonRecord },
  ): RunRecord {
    const dataset = this.getDataset(tenantId, projectId, options.datasetId);
    const result = jsonRecord(options.runResult);
    const observations = extractObservations(result);
    this.quota.check(dataset.tenant_id, dataset.project_id, "run.submit");
    this.quota.check(dataset.tenant_id, dataset.project_id, "observation.write", Math.max(1, observations.length));
    const runId = options.runId ?? String(result.run_id ?? newId("run"));
    requireId(runId, "run_id");
    if (this.store.runs[runId]) {
      throw new ValidationError(`run already exists: ${runId}`);
    }
    this.quota.consume(dataset.tenant_id, dataset.project_id, "run.submit");
    this.quota.consume(dataset.tenant_id, dataset.project_id, "observation.write", Math.max(1, observations.length));
    const now = this.clock();
    const cases = Array.isArray(result.cases) ? result.cases : [];
    const status = cloudRunStatus(result);
    const record: RunRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: dataset.tenant_id,
      project_id: dataset.project_id,
      dataset_id: dataset.dataset_id,
      run_id: runId,
      status,
      result_status: String(result.status ?? ""),
      runner_id: String(result.runner_id ?? "a1-local-runner"),
      total_cases: Number(result.total_cases ?? cases.length),
      observations,
      result,
      created_at: now,
      updated_at: now,
      status_history: [{ status, at: now }],
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.runs[runId] = record;
    return cloneJson(record);
  }

  createQueuedRun(
    tenantId: string,
    projectId: string,
    options: { datasetId: string; runnerId?: string; runId?: string; metadata?: JsonRecord },
  ): RunRecord {
    const dataset = this.getDataset(tenantId, projectId, options.datasetId);
    this.quota.check(dataset.tenant_id, dataset.project_id, "run.submit");
    const runId = options.runId ?? newId("run");
    requireId(runId, "run_id");
    if (this.store.runs[runId]) {
      throw new ValidationError(`run already exists: ${runId}`);
    }
    this.quota.consume(dataset.tenant_id, dataset.project_id, "run.submit");
    const now = this.clock();
    const runnerId = options.runnerId ?? "a1-ts-cloud-queue-worker";
    const result: JsonRecord = {
      schema_version: RUN_RESULT_SCHEMA_VERSION,
      run_id: runId,
      dataset_id: dataset.dataset_id,
      runner_id: runnerId,
      status: "queued",
      total_cases: dataset.case_count,
      passed: 0,
      failed: 0,
      errored: 0,
      timed_out: 0,
      cases: [],
      metadata: { local_only: true, ashr_api_used: false, queued: true },
    };
    const record: RunRecord = {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: dataset.tenant_id,
      project_id: dataset.project_id,
      dataset_id: dataset.dataset_id,
      run_id: runId,
      status: "queued",
      result_status: "queued",
      runner_id: runnerId,
      total_cases: dataset.case_count,
      observations: [],
      result,
      created_at: now,
      updated_at: now,
      status_history: [{ status: "queued", at: now }],
      lease_owner_id: null,
      lease_expires_at: null,
      lease_heartbeat_at: null,
      lease_reclaim_count: 0,
      metadata: jsonRecord(options.metadata ?? {}),
    };
    this.store.runs[runId] = record;
    return cloneJson(record);
  }

  markRunRunning(
    tenantId: string,
    projectId: string,
    runId: string,
    options: { leaseOwnerId?: string | null; leaseSeconds?: number | null; reclaimExpired?: boolean } = {},
  ): RunRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    if (run.status === "cancelled") {
      return cloneJson(run);
    }
    if (!["queued", "submitted", "running"].includes(run.status)) {
      throw new ValidationError(`run cannot transition to running from ${run.status}`);
    }
    const now = this.clock();
    this.claimOrValidateRunLease(run, {
      leaseOwnerId: options.leaseOwnerId ?? null,
      leaseSeconds: options.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : options.leaseSeconds,
      now,
      reclaimExpired: Boolean(options.reclaimExpired),
    });
    run.status = "running";
    run.result_status = "running";
    run.updated_at = now;
    run.result.status = "running";
    appendStatusHistory(run, "running", now);
    return cloneJson(run);
  }

  heartbeatRun(
    tenantId: string,
    projectId: string,
    runId: string,
    options: { leaseOwnerId: string; leaseSeconds?: number | null },
  ): RunRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    if (!["queued", "submitted", "running"].includes(run.status)) {
      throw new ValidationError(`run cannot heartbeat from ${run.status}`);
    }
    this.requireRunLeaseOwner(run, options.leaseOwnerId);
    const now = this.clock();
    if (options.leaseSeconds === null) {
      throw new ValidationError("leaseSeconds is required when renewing a run lease");
    }
    run.lease_heartbeat_at = now;
    run.lease_expires_at = leaseExpiresAt(now, options.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : options.leaseSeconds);
    run.updated_at = now;
    return cloneJson(run);
  }

  reclaimExpiredRunLeases(
    tenantId: string,
    projectId: string,
    options: { datasetId?: string; statuses?: string[]; now?: string } = {},
  ): RunRecord[] {
    this.getProject(tenantId, projectId);
    const statuses = new Set((options.statuses ?? ["queued", "running", "submitted"]).map((status) => String(status)));
    const now = options.now ?? this.clock();
    const reclaimed: RunRecord[] = [];
    for (const run of Object.values(this.store.runs)) {
      if (run.tenant_id !== tenantId || run.project_id !== projectId) {
        continue;
      }
      if (options.datasetId !== undefined && run.dataset_id !== options.datasetId) {
        continue;
      }
      if (!statuses.has(run.status)) {
        continue;
      }
      if (run.lease_owner_id === undefined || run.lease_owner_id === null || !leaseExpired(run.lease_expires_at, now)) {
        continue;
      }
      run.lease_owner_id = null;
      run.lease_expires_at = null;
      run.lease_heartbeat_at = null;
      run.lease_reclaim_count = Number(run.lease_reclaim_count ?? 0) + 1;
      if (run.status === "running") {
        run.status = "queued";
        run.result_status = "queued";
        run.result.status = "queued";
        appendStatusHistory(run, "queued", now);
      }
      run.updated_at = now;
      reclaimed.push(cloneJson(run));
    }
    return reclaimed;
  }

  completeRun(tenantId: string, projectId: string, runId: string, runResult: RunResult | JsonRecord, options: { leaseOwnerId?: string | null } = {}): RunRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    if (run.status === "cancelled") {
      return cloneJson(run);
    }
    if (!["queued", "running", "submitted"].includes(run.status)) {
      throw new ValidationError(`run cannot complete from ${run.status}`);
    }
    if ((run.lease_owner_id ?? null) !== null && (options.leaseOwnerId === undefined || options.leaseOwnerId === null)) {
      throw new ValidationError("run lease owner is required for leased run");
    }
    if (options.leaseOwnerId !== undefined && options.leaseOwnerId !== null) {
      this.requireRunLeaseOwner(run, options.leaseOwnerId);
    }
    const result = jsonRecord(runResult);
    const nextStatus = cloudRunStatus(result);
    if (!["completed", "failed", "cancelled"].includes(nextStatus)) {
      throw new ValidationError(`run completion requires a terminal status, got ${nextStatus}`);
    }
    const observations = extractObservations(result);
    this.quota.check(tenantId, projectId, "observation.write", Math.max(1, observations.length));
    this.quota.consume(tenantId, projectId, "observation.write", Math.max(1, observations.length));
    const now = this.clock();
    run.status = nextStatus;
    run.result_status = String(result.status ?? "");
    run.runner_id = String(result.runner_id ?? run.runner_id ?? "a1-local-runner");
    run.total_cases = Number(result.total_cases ?? (Array.isArray(result.cases) ? result.cases.length : run.total_cases));
    run.observations = observations;
    run.result = result;
    run.updated_at = now;
    clearRunLease(run);
    appendStatusHistory(run, run.status, now);
    return cloneJson(run);
  }

  failRun(
    tenantId: string,
    projectId: string,
    runId: string,
    options: { error: unknown; resultStatus?: string; leaseOwnerId?: string | null } = { error: "failed" },
  ): RunRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    if (run.status === "cancelled") {
      return cloneJson(run);
    }
    if ((run.lease_owner_id ?? null) !== null && (options.leaseOwnerId === undefined || options.leaseOwnerId === null)) {
      throw new ValidationError("run lease owner is required for leased run");
    }
    if (options.leaseOwnerId !== undefined && options.leaseOwnerId !== null) {
      this.requireRunLeaseOwner(run, options.leaseOwnerId);
    }
    const now = this.clock();
    const errorPayload = isRecord(options.error)
      ? (redactSensitive(options.error) as JsonRecord)
      : { type: "Error", message: redactText(String(options.error)) };
    const resultStatus = options.resultStatus ?? "error";
    run.status = "failed";
    run.result_status = resultStatus;
    run.updated_at = now;
    run.observations = [];
    run.error = errorPayload;
    run.result = {
      schema_version: RUN_RESULT_SCHEMA_VERSION,
      run_id: run.run_id,
      dataset_id: run.dataset_id,
      runner_id: run.runner_id,
      status: resultStatus,
      total_cases: run.total_cases,
      passed: 0,
      failed: 0,
      errored: run.total_cases,
      timed_out: 0,
      cases: [],
      error: errorPayload,
      metadata: { local_only: true, ashr_api_used: false, queued: true },
    };
    clearRunLease(run);
    appendStatusHistory(run, "failed", now);
    return cloneJson(run);
  }

  cancelRun(tenantId: string, projectId: string, runId: string, options: { reason?: string } = {}): RunRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    if (["completed", "failed"].includes(run.status)) {
      throw new ValidationError(`run cannot be cancelled from ${run.status}`);
    }
    const now = this.clock();
    const error = { type: "Cancelled", message: redactText(options.reason ?? "cancelled") };
    run.status = "cancelled";
    run.result_status = "cancelled";
    run.updated_at = now;
    run.error = error;
    run.result.status = "cancelled";
    run.result.error = error;
    clearRunLease(run);
    appendStatusHistory(run, "cancelled", now);
    return cloneJson(run);
  }

  appendObservation(tenantId: string, projectId: string, runId: string, observation: JsonRecord): JsonRecord {
    const run = this.getRunRecord(tenantId, projectId, runId);
    this.quota.consume(tenantId, projectId, "observation.write");
    const payload = jsonRecord(observation);
    run.observations.push(payload);
    run.updated_at = this.clock();
    return cloneJson(payload);
  }

  getRun(tenantId: string, projectId: string, runId: string): RunRecord {
    return cloneJson(this.getRunRecord(tenantId, projectId, runId));
  }

  listRuns(tenantId: string, projectId: string, options: { datasetId?: string } = {}): RunRecord[] {
    this.getProject(tenantId, projectId);
    return Object.values(this.store.runs)
      .filter((run) => run.tenant_id === tenantId && run.project_id === projectId && (options.datasetId === undefined || run.dataset_id === options.datasetId))
      .map((run) => cloneJson(run));
  }

  pollRun(tenantId: string, projectId: string, runId: string): PollRunRecord {
    const run = this.getRun(tenantId, projectId, runId);
    return {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: run.tenant_id,
      project_id: run.project_id,
      run_id: run.run_id,
      status: run.status,
      updated_at: run.updated_at,
      run,
    };
  }

  quotaSnapshot(tenantId: string, projectId: string): QuotaSnapshot {
    this.getProject(tenantId, projectId);
    return this.quota.snapshot(tenantId, projectId);
  }

  exportRunFixture(tenantId: string, projectId: string, runId: string): CloudRunFixture {
    const run = this.getRun(tenantId, projectId, runId);
    return {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      tenant_id: run.tenant_id,
      project_id: run.project_id,
      dataset_id: run.dataset_id,
      run_id: run.run_id,
      status: run.status,
      run_result: cloneJson(run.result),
      observations: cloneJson(run.observations),
      metadata: { local_only: true, ashr_api_used: false },
    };
  }

  async writeRunFixture(tenantId: string, projectId: string, runId: string, outputPath: string): Promise<string> {
    await writeJsonFile(outputPath, this.exportRunFixture(tenantId, projectId, runId));
    return outputPath;
  }

  snapshotState(): CloudStateSnapshot {
    return {
      schema_version: CLOUD_API_SCHEMA_VERSION,
      state_version: 1,
      kind: "local_cloud_state",
      store: this.store.snapshot(),
      quota: this.quota.state(),
      metadata: { local_only: true, ashr_api_used: false },
    };
  }

  async writeState(outputPath: string): Promise<string> {
    await writeJsonFile(outputPath, this.snapshotState());
    return outputPath;
  }

  static fromState(payload: unknown): CloudApiService {
    if (!isRecord(payload)) {
      throw new ValidationError("cloud state payload must be a JSON object");
    }
    return new CloudApiService({
      store: InMemoryCloudStore.fromState(payload),
      quota: QuotaLedger.fromState(payload.quota),
    });
  }

  static async fromStateFile(inputPath: string): Promise<CloudApiService> {
    const fs = await import("node:fs/promises");
    return CloudApiService.fromState(JSON.parse(await fs.readFile(inputPath, "utf8")) as unknown);
  }

  private claimOrValidateRunLease(
    run: RunRecord,
    options: { leaseOwnerId: string | null; leaseSeconds: number | null; now: string; reclaimExpired: boolean },
  ): void {
    const currentOwner = run.lease_owner_id ?? null;
    if (options.leaseOwnerId === null) {
      if (currentOwner !== null) {
        throw new ValidationError("run lease owner is required for leased run");
      }
      return;
    }
    const owner = requireText(options.leaseOwnerId, "leaseOwnerId");
    if (options.leaseSeconds === null) {
      throw new ValidationError("leaseSeconds is required when claiming a run lease");
    }
    if (currentOwner !== null && currentOwner !== owner) {
      if (!(options.reclaimExpired && leaseExpired(run.lease_expires_at, options.now))) {
        throw new ValidationError("run is leased by another worker");
      }
      run.lease_reclaim_count = Number(run.lease_reclaim_count ?? 0) + 1;
    }
    run.lease_owner_id = owner;
    run.lease_heartbeat_at = options.now;
    run.lease_expires_at = leaseExpiresAt(options.now, options.leaseSeconds);
  }

  private requireRunLeaseOwner(run: RunRecord, leaseOwnerId: string): void {
    const owner = requireText(leaseOwnerId, "leaseOwnerId");
    if ((run.lease_owner_id ?? null) !== owner) {
      throw new ValidationError("run lease is not owned by this worker");
    }
  }
  private getRunRecord(tenantId: string, projectId: string, runId: string): RunRecord {
    const run = this.store.runs[runId];
    if (!run || run.tenant_id !== tenantId || run.project_id !== projectId) {
      throw new NotFoundError("run not found for tenant/project");
    }
    return run;
  }
}

export function coerceAgentInput(value: unknown, options: { parts?: unknown; metadata?: JsonRecord } = {}): AgentInput {
  let input: AgentInput;
  if (isRecord(value) && (value.schema_version === AGENT_INPUT_SCHEMA_VERSION || "text" in value || "parts" in value || "metadata" in value)) {
    input = {
      schema_version: AGENT_INPUT_SCHEMA_VERSION,
      text: textValue(value.text ?? ""),
      parts: normalizeInputParts(value.parts ?? []),
      metadata: isRecord(value.metadata) ? jsonRecord(value.metadata) : {},
    };
  } else {
    input = {
      schema_version: AGENT_INPUT_SCHEMA_VERSION,
      text: textValue(value),
      parts: [],
      metadata: {},
    };
  }
  if (options.parts !== undefined) {
    input.parts = normalizeInputParts(options.parts);
  }
  if (options.metadata) {
    input.metadata = { ...input.metadata, ...jsonRecord(options.metadata) };
  }
  if (input.parts.length === 0 && input.text) {
    input.parts = [{ type: "text", text: input.text }];
  }
  if (!input.text) {
    input.text = textFromInputParts(input.parts);
  }
  return input;
}

export function agentInputFromText(text: unknown, metadata: JsonRecord = {}): AgentInput {
  return coerceAgentInput(text, { metadata });
}

export function agentInputFromParts(parts: unknown, options: { text?: unknown; metadata?: JsonRecord } = {}): AgentInput {
  return coerceAgentInput(options.text ?? "", { parts, metadata: options.metadata });
}

export function buildDefaultRequestInputSchema(request: JsonRecord | undefined = undefined): JsonRecord {
  const schema = jsonRecord(DEFAULT_REQUEST_INPUT_SCHEMA);
  const agent = isRecord(request?.agent) ? request.agent : undefined;
  if (agent && Array.isArray(agent.tools)) {
    schema.tools = redactSensitive(agent.tools);
  }
  const enabledPartTypes = enabledAgentInputPartTypes(request);
  if (enabledPartTypes.some((partType) => NON_TEXT_AGENT_INPUT_PART_TYPES.includes(partType))) {
    Object.assign(schema, agentInputSchema(enabledPartTypes));
  }
  return schema;
}

export async function runAgentCloudDemo(options: {
  cases: JsonRecord[];
  agent: AgentHandler;
  tenantId?: string;
  tenantName?: string;
  projectId?: string;
  projectName?: string;
  datasetId?: string;
  datasetName?: string;
  runnerId?: string;
  service?: CloudApiService;
  sdkSubmitter?: CloudDemoSdkSubmitter;
  agentRef?: string;
  sdkRunId?: string;
}): Promise<CloudDemoSummary> {
  if (!Array.isArray(options.cases) || options.cases.length === 0) {
    throw new ValidationError("demo cases must not be empty");
  }
  const service = options.service ?? new CloudApiService();
  const tenant = service.createTenant(options.tenantName ?? "TS Local Tenant", {
    tenantId: options.tenantId ?? "tenant_ts_demo",
    metadata: { local_only: true },
  });
  const project = service.createProject(tenant.tenant_id, options.projectName ?? "TS Local Project", {
    projectId: options.projectId ?? "project_ts_demo",
    metadata: { local_only: true },
  });
  const dataset = service.createDataset(tenant.tenant_id, project.project_id, {
    datasetId: options.datasetId ?? "dataset_ts_demo",
    name: options.datasetName ?? "TS Local Dataset",
    cases: options.cases,
    metadata: { source: "packages/ts/ashr-clone", local_only: true },
  });
  const caseResults: CaseResult[] = [];
  for (const [index, caseRecord] of options.cases.entries()) {
    caseResults.push(await runDemoCase(options.agent, caseRecord, index));
  }
  const passed = caseResults.filter((item) => item.status === "passed").length;
  const failed = caseResults.filter((item) => item.status === "failed").length;
  const errored = caseResults.filter((item) => item.status === "error").length;
  const runResult: RunResult = {
    run_id: `run_${dataset.dataset_id}`,
    dataset_id: dataset.dataset_id,
    runner_id: options.runnerId ?? "ts-local-runner",
    status: failed || errored ? "failed" : "passed",
    total_cases: caseResults.length,
    passed,
    failed,
    errored,
    timed_out: 0,
    started_at: utcNow(),
    ended_at: utcNow(),
    duration_ms: 0,
    max_workers: 4,
    trace_completeness: caseResults.every((item) => item.observations.length > 0) ? 1 : 0,
    cases: caseResults,
    aggregate_metrics: {
      schema_version: RUN_RESULT_SCHEMA_VERSION,
      trace_completeness: caseResults.every((item) => item.observations.length > 0) ? 1 : 0,
      passed,
      failed,
      errored,
      timed_out: 0,
      total_tool_calls: caseResults.reduce((total, item) => total + item.agent_output.tool_calls.length, 0),
    },
    metadata: { local_only: true, ashr_api_used: false },
    field_map_version: "a1.ts.local.v1",
  };
  const run = service.submitRun(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    runResult,
    metadata: { source: "packages/ts/ashr-clone" },
  });
  const poll = service.pollRun(tenant.tenant_id, project.project_id, run.run_id);
  const fixture = service.exportRunFixture(tenant.tenant_id, project.project_id, run.run_id);
  const totalToolCalls = caseResults.reduce((total, item) => total + item.agent_output.tool_calls.length, 0);
  const sdkSubmission = options.sdkSubmitter?.sdkSubmit(tenant.tenant_id, project.project_id, {
    datasetId: dataset.dataset_id,
    agentRef: options.agentRef ?? options.runnerId ?? "ts-local-runner",
    runId: options.sdkRunId ?? `${run.run_id}_hosted_submit`,
    idempotencyKey: `${run.run_id}:sdk-submit`,
    requestId: `${run.run_id}:quickstart`,
    metadata: {
      source: "runAgentCloudDemo",
      local_run_id: run.run_id,
      expected_vs_actual_cases: caseResults.length,
      trace_events: run.observations.length,
      tool_calls: totalToolCalls,
    },
  });
  const quota = service.quotaSnapshot(tenant.tenant_id, project.project_id);
  return {
    schema_version: CLOUD_API_SCHEMA_VERSION,
    tenant: { tenant_id: tenant.tenant_id, name: tenant.name },
    project: { tenant_id: project.tenant_id, project_id: project.project_id, name: project.name },
    dataset: { dataset_id: dataset.dataset_id, case_count: dataset.case_count, name: dataset.name },
    run: {
      run_id: run.run_id,
      dataset_id: run.dataset_id,
      status: run.status,
      result_status: run.result_status,
      runner_id: run.runner_id,
      total_cases: run.total_cases,
      passed,
      failed,
      errored,
      timed_out: 0,
      trace_completeness: Number(runResult.trace_completeness ?? 0),
      observations: run.observations.length,
      total_tool_calls: totalToolCalls,
    },
    poll: { status: poll.status, run_id: poll.run_id },
    cases: caseResults.map((item) => ({
      case_id: item.case_id,
      status: item.status,
      expected: isRecord(item.expected) ? jsonRecord(item.expected) : {},
      actual: expectedActualFromTurn(item.agent_output),
      tool_calls: item.agent_output.tool_calls.map((call) => jsonRecord(call)),
      observations: item.observations.length,
    })),
    replay: { available: true, local_only: true, run_id: run.run_id, event_count: run.observations.length, vm_stream_count: 0 },
    ...(sdkSubmission !== undefined ? { sdk_submission: sdkSubmission } : {}),
    quota: { used: quota.used, remaining: quota.remaining },
    fixture,
    metadata: { local_only: true, ashr_api_used: false },
  };
}

export function redactText(value: string): string {
  let redacted = value.replace(/https?:\/\/[^\s?#]+(?:\?[^\s]*)/gi, (match) => `${match.split("?", 1)[0]}?[redacted]`);
  redacted = redacted.replace(/([?&](?:api_key|key|signature|sig|token)=)[^&\s]+/gi, "$1[redacted]");
  for (const pattern of [
    /tp_[A-Za-z0-9_-]+/g,
    /sk-[A-Za-z0-9_-]{8,}/g,
    /Bearer\s+[A-Za-z0-9._-]+/gi,
    /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  ]) {
    redacted = redacted.replace(pattern, "[redacted]");
  }
  return redacted;
}

async function runDemoCase(agent: AgentHandler, caseRecord: JsonRecord, index: number): Promise<CaseResult> {
  const caseId = String(caseRecord.id ?? caseRecord.case_id ?? `case-${index + 1}`);
  const prompt = textValue(caseRecord.prompt ?? caseRecord.input ?? "");
  const agentInput = coerceAgentInput(prompt, { metadata: { case_id: caseId } });
  const observations: JsonRecord[] = [
    {
      observation_id: `${caseId}:user`,
      case_id: caseId,
      event_type: "message",
      role: "user",
      content: prompt,
      metadata: { local_only: true },
    },
  ];
  let output: AgentTurn;
  let status = "passed";
  try {
    output = normalizeAgentTurn(await agent(agentInput, caseRecord));
    observations.push({
      observation_id: `${caseId}:assistant`,
      case_id: caseId,
      event_type: "message",
      role: "assistant",
      content: output.text,
      tool_calls: output.tool_calls,
      metadata: { local_only: true },
    });
    const expected = isRecord(caseRecord.expected) ? caseRecord.expected : undefined;
    if (expected && typeof expected.text === "string" && output.text !== expected.text) {
      status = "failed";
    }
    if (expected && expected.tool_calls !== undefined && !jsonEqual(toJson(expected.tool_calls), toJson(output.tool_calls))) {
      status = "failed";
    }
  } catch (error) {
    status = "error";
    output = {
      schema_version: AGENT_TURN_SCHEMA_VERSION,
      text: "",
      tool_calls: [],
      status: "error",
      latency_ms: 0,
      metadata: { local_only: true },
      error: { type: error instanceof Error ? error.name : "AgentError", message: redactText(String(error instanceof Error ? error.message : error)) },
    };
    observations.push({
      observation_id: `${caseId}:error`,
      case_id: caseId,
      event_type: "error",
      role: "assistant",
      content: output.error?.message ?? "",
      metadata: { local_only: true },
    });
  }
  return {
    case_id: caseId,
    scenario_id: typeof caseRecord.scenario_id === "string" ? caseRecord.scenario_id : undefined,
    prompt,
    expected: isRecord(caseRecord.expected) ? jsonRecord(caseRecord.expected) : undefined,
    actual: output.text,
    status,
    agent_output: output,
    observations,
  };
}

function expectedActualFromTurn(turn: AgentTurn): JsonRecord {
  return {
    text: turn.text,
    tool_calls: turn.tool_calls.map((call) => jsonRecord(call)),
    status: turn.status,
  };
}

function jsonEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function normalizeAgentTurn(value: AgentTurnLike): AgentTurn {
  if (typeof value === "string") {
    return {
      schema_version: AGENT_TURN_SCHEMA_VERSION,
      text: value,
      tool_calls: [],
      status: "ok",
      latency_ms: 0,
      metadata: { local_only: true },
    };
  }
  const record = jsonRecord(value);
  return {
    schema_version: AGENT_TURN_SCHEMA_VERSION,
    text: textValue(record.text ?? record.content ?? record.message ?? ""),
    tool_calls: Array.isArray(record.tool_calls) ? record.tool_calls.filter(isRecord).map((item) => jsonRecord(item)) : [],
    status: String(record.status ?? "ok"),
    latency_ms: Number(record.latency_ms ?? 0),
    metadata: isRecord(record.metadata) ? jsonRecord(record.metadata) : { local_only: true },
    error: isRecord(record.error) ? jsonRecord(redactSensitive(record.error) as JsonRecord) : undefined,
  };
}

function enabledAgentInputPartTypes(request: JsonRecord | undefined): AgentInputPartType[] {
  const agent = isRecord(request?.agent) ? request.agent : undefined;
  const acceptedInputs = agent && isRecord(agent.accepted_inputs) ? agent.accepted_inputs : undefined;
  const enabled: AgentInputPartType[] = [];
  if (acceptedInputs === undefined || truthyEnabled(acceptedInputs.text)) {
    enabled.push("text");
  }
  for (const partType of NON_TEXT_AGENT_INPUT_PART_TYPES) {
    if (acceptedInputs !== undefined && truthyEnabled(acceptedInputs[partType])) {
      enabled.push(partType);
    }
  }
  return enabled;
}

function agentInputSchema(enabledPartTypes: AgentInputPartType[]): JsonRecord {
  const enabled = new Set(enabledPartTypes);
  const partTypes = AGENT_INPUT_PART_TYPES.filter((partType) => enabled.has(partType));
  return {
    properties: {
      schema_version: { const: AGENT_INPUT_SCHEMA_VERSION },
      text: { type: "string" },
      parts: { type: "array", items: { $ref: "#/$defs/agent_input_part" } },
      metadata: { type: "object" },
    },
    $defs: { agent_input_part: agentInputPartSchema(partTypes) },
  };
}

function agentInputPartSchema(partTypes: AgentInputPartType[]): JsonRecord {
  const textPart = {
    type: "object",
    required: ["type", "text"],
    properties: { type: { const: "text" }, text: { type: "string" } },
    additionalProperties: true,
  };
  const mediaPartTypes = partTypes.filter((partType) => NON_TEXT_AGENT_INPUT_PART_TYPES.includes(partType));
  const variants: JsonRecord[] = [];
  if (partTypes.includes("text")) {
    variants.push(textPart);
  }
  if (mediaPartTypes.length) {
    variants.push({
      type: "object",
      required: ["type"],
      properties: {
        type: { enum: mediaPartTypes },
        path: { type: "string" },
        url: { type: "string" },
        source: { type: "string" },
        mime_type: { type: "string" },
        name: { type: "string" },
        description: { type: "string" },
      },
      additionalProperties: true,
    });
  }
  if (variants.length === 0) {
    return textPart;
  }
  if (variants.length === 1) {
    return variants[0];
  }
  return { oneOf: variants };
}

function truthyEnabled(value: unknown): boolean {
  return isRecord(value) ? Boolean(value.enabled) : Boolean(value);
}

export function redactSensitive(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactSensitive(item));
  }
  if (isRecord(value)) {
    const redacted: JsonRecord = {};
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      if (normalized === "key" || ["api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential"].some((part) => normalized.includes(part))) {
        redacted[key] = "[redacted]";
      } else {
        redacted[key] = redactSensitive(item);
      }
    }
    return redacted;
  }
  return typeof value === "string" ? redactText(value) : value;
}

function extractObservations(runResult: JsonRecord): JsonRecord[] {
  const cases = Array.isArray(runResult.cases) ? runResult.cases : [];
  const observations: JsonRecord[] = [];
  for (const item of cases) {
    if (!isRecord(item) || !Array.isArray(item.observations)) {
      continue;
    }
    for (const observation of item.observations) {
      if (isRecord(observation)) {
        observations.push(jsonRecord(observation));
      }
    }
  }
  return observations;
}

function appendStatusHistory(run: RunRecord, status: string, at: string): void {
  const history = Array.isArray(run.status_history) ? run.status_history : [];
  if (history.length > 0 && isRecord(history[history.length - 1]) && history[history.length - 1].status === status) {
    history[history.length - 1].at = at;
  } else {
    history.push({ status, at });
  }
  run.status_history = history;
}

function cloudRunStatus(runResult: JsonRecord): string {
  const status = String(runResult.status ?? "").toLowerCase();
  if (["queued", "running", "completed", "failed", "cancelled"].includes(status)) {
    return status;
  }
  if (runResult.ended_at !== undefined && Array.isArray(runResult.cases)) {
    return "completed";
  }
  return "submitted";
}

function normalizeInputParts(parts: unknown): AgentInputPart[] {
  if (parts === undefined || parts === null) {
    return [];
  }
  const partList = Array.isArray(parts) ? parts : [parts];
  return partList.map((part, index) => normalizeInputPart(part, index));
}

function normalizeInputPart(part: unknown, index: number): AgentInputPart {
  if (typeof part === "string") {
    return { type: "text", text: part };
  }
  if (!isRecord(part)) {
    throw new ValidationError(`agent input part ${index} must be a mapping`);
  }
  const normalized = jsonRecord(part) as AgentInputPart;
  const partType = String(normalized.type ?? "text").toLowerCase();
  if (!AGENT_INPUT_PART_TYPES.includes(partType as AgentInputPartType)) {
    throw new ValidationError(`agent input part ${index} has unsupported type: ${partType}`);
  }
  normalized.type = partType as AgentInputPartType;
  if (normalized.mimeType !== undefined && normalized.mime_type === undefined) {
    normalized.mime_type = String(normalized.mimeType);
    delete normalized.mimeType;
  }
  if (normalized.uri !== undefined && normalized.url === undefined) {
    normalized.url = String(normalized.uri);
    delete normalized.uri;
  }
  if (normalized.fileName !== undefined && normalized.name === undefined) {
    normalized.name = String(normalized.fileName);
    delete normalized.fileName;
  }
  if (normalized.filename !== undefined && normalized.name === undefined) {
    normalized.name = String(normalized.filename);
    delete normalized.filename;
  }
  if (normalized.type === "text") {
    normalized.text = textValue(normalized.text ?? normalized.content ?? "");
    delete normalized.content;
  } else if (normalized.source !== undefined && normalized.url === undefined && normalized.path === undefined) {
    const source = String(normalized.source);
    if (/^https?:\/\//i.test(source)) normalized.url = source;
    else normalized.path = source;
  }
  return normalized;
}

function textFromInputParts(parts: AgentInputPart[]): string {
  return parts
    .filter((part) => part.type === "text" && part.text)
    .map((part) => String(part.text))
    .join("\n");
}

function textValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(toJson(value));
}

function positiveUnits(units: number): number {
  const parsed = Number(units);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new ValidationError("quota units must be positive");
  }
  return parsed;
}

function numberRecord(value: JsonRecord, fieldName: string): Record<string, number> {
  const result: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) {
    const parsed = Number(item);
    if (!Number.isInteger(parsed) || parsed < 0) {
      throw new ValidationError(`${fieldName} values must be non-negative integers`);
    }
    result[key] = parsed;
  }
  return result;
}

function stateBucket<T extends JsonRecord>(payload: JsonRecord, key: string): Record<string, T> {
  const bucket = payload[key] ?? {};
  if (!isRecord(bucket)) {
    throw new ValidationError(`cloud state ${key} must be an object`);
  }
  const result: Record<string, T> = {};
  for (const [itemKey, itemValue] of Object.entries(bucket)) {
    if (!isRecord(itemValue)) {
      throw new ValidationError(`cloud state ${key} records must be objects`);
    }
    result[itemKey] = jsonRecord(itemValue) as T;
  }
  return result;
}

function requireId(value: string, fieldName: string): void {
  if (typeof value !== "string" || !value.trim()) {
    throw new ValidationError(`${fieldName} must be a non-empty string`);
  }
}

function requireText(value: string, fieldName: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ValidationError(`${fieldName} must be a non-empty string`);
  }
  return value;
}

let idCounter = 0;

function newId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${String(idCounter).padStart(6, "0")}`;
}

function utcNow(): string {
  return new Date().toISOString();
}

function jsonRecord(value: JsonRecord): JsonRecord {
  return cloneJson(toJson(value)) as JsonRecord;
}

async function writeJsonFile(path: string, value: unknown): Promise<void> {
  const fs = await import("node:fs/promises");
  const pathModule = await import("node:path");
  const outputPath = pathModule.resolve(path);
  await fs.mkdir(pathModule.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(jsonRecord(isRecord(value) ? value : { value }), null, 2)}\n`, "utf8");
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toJson(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => toJson(item));
  }
  if (isRecord(value)) {
    const result: JsonRecord = {};
    for (const key of Object.keys(value).sort()) {
      const item = value[key];
      result[key] = toJson(item);
    }
    return result;
  }
  if (value === undefined) {
    return null;
  }
  return value;
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clearRunLease(run: RunRecord): void {
  run.lease_owner_id = null;
  run.lease_expires_at = null;
  run.lease_heartbeat_at = null;
}

function leaseExpiresAt(now: string, leaseSeconds: number | null): string | null {
  if (leaseSeconds === null) {
    return null;
  }
  const seconds = Number(leaseSeconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new ValidationError("leaseSeconds must be positive");
  }
  const parsed = Date.parse(now);
  const base = Number.isFinite(parsed) ? parsed : Date.now();
  return new Date(base + seconds * 1000).toISOString();
}

function leaseExpired(expiresAt: unknown, now: string): boolean {
  if (typeof expiresAt !== "string" || expiresAt.trim() === "") {
    return false;
  }
  const expires = Date.parse(expiresAt);
  const current = Date.parse(now);
  if (!Number.isFinite(expires)) {
    return false;
  }
  return expires <= (Number.isFinite(current) ? current : Date.now());
}
