export const ASHR_DEFAULT_BASE_URL = "https://api.ashr.io/testing-platform-api";
export const ASHR_API_ENV_VAR = "ASHR_API_KEY";
export const ASHR_LABS_API_ENV_VAR = "ASHR_LABS_API_KEY";
export const ASHR_LABS_BASE_URL_ENV_VAR = "ASHR_LABS_BASE_URL";
export const ASHR_API_FIELD_MAP_VERSION = "a1-api-calibration-2026-07-04";
export const ASHR_API_AGENT_INPUT_SCHEMA_VERSION = "ashr.clone.agent_input.v1";

type ApiJsonRecord = Record<string, unknown>;
type ApiTransportResponse = {
  statusCode: number;
  body: unknown;
  headers?: Record<string, string>;
};

export type AshrApiTransport = (
  url: string,
  headers: Record<string, string>,
  body: string,
  timeoutMs: number,
) => ApiTransportResponse | Promise<ApiTransportResponse>;

export interface AshrApiCallPlan {
  function: string;
  params: ApiJsonRecord;
  preflight?: ApiJsonRecord;
  purpose: string;
  estimated_calls: number;
  mutates: boolean;
  output_path?: string;
  notes: string[];
  base_url: string;
  field_map_version: typeof ASHR_API_FIELD_MAP_VERSION;
}

export interface AshrApiCallRecord {
  function: string;
  dry_run: boolean;
  purpose: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  attempts: number;
  status: "planned" | "ok" | "error" | "timeout";
  status_code: number | null;
  request: ApiJsonRecord;
  response?: ApiJsonRecord | null;
  response_headers: ApiJsonRecord;
  response_summary?: ApiJsonRecord;
  error?: ApiJsonRecord | null;
  output_path?: string;
  field_map_version: typeof ASHR_API_FIELD_MAP_VERSION;
}

export class MissingAshrApiKeyError extends Error {
  constructor(message = `${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} environment variable is not set`) {
    super(message);
    this.name = "MissingAshrApiKeyError";
  }
}

export class AshrApiError extends Error {
  readonly statusCode: number | null;
  readonly response: ApiJsonRecord;
  readonly responseHeaders: ApiJsonRecord;
  readonly errorKind: string;

  constructor(
    message: string,
    options: {
      statusCode?: number | null;
      response?: ApiJsonRecord;
      responseHeaders?: ApiJsonRecord;
      errorKind?: string;
    } = {},
  ) {
    super(redactApiText(message));
    this.name = "AshrApiError";
    this.statusCode = options.statusCode ?? null;
    this.response = redactApiSensitive(options.response ?? {}) as ApiJsonRecord;
    this.responseHeaders = redactApiSensitive(options.responseHeaders ?? {}) as ApiJsonRecord;
    this.errorKind = options.errorKind ?? "api";
  }

  toJSON(): ApiJsonRecord {
    return {
      message: this.message,
      status_code: this.statusCode,
      error_kind: this.errorKind,
      response: this.response,
      response_headers: this.responseHeaders,
    };
  }
}

export interface AshrApiClientOptions {
  apiKey?: string | null;
  baseUrl?: string;
  timeoutMs?: number;
  maxRetries?: number;
  retryBackoffMs?: number;
  transport?: AshrApiTransport;
}

export interface AshrApiCallOptions {
  params?: ApiJsonRecord;
  recordParams?: ApiJsonRecord;
  purpose?: string;
  estimatedCalls?: number;
  mutates?: boolean;
  preflight?: ApiJsonRecord;
  outputPath?: string;
  dryRun?: boolean;
}

export class AshrApiClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  readonly maxRetries: number;
  readonly retryBackoffMs: number;
  private readonly apiKey: string | null;
  private readonly transport: AshrApiTransport;
  private tenantId: number | null = null;
  private userId: number | null = null;

  constructor(options: AshrApiClientOptions = {}) {
    this.apiKey = options.apiKey ?? null;
    this.baseUrl = (options.baseUrl ?? ASHR_DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = positiveInteger(options.timeoutMs ?? 30000, "timeoutMs");
    this.maxRetries = Math.max(0, Math.trunc(options.maxRetries ?? 2));
    this.retryBackoffMs = Math.max(0, Math.trunc(options.retryBackoffMs ?? 500));
    this.transport = options.transport ?? fetchTransport;
  }

  static fromEnv(
    env: Record<string, string | undefined> = processEnv(),
    options: Omit<AshrApiClientOptions, "apiKey" | "baseUrl"> & { required?: boolean; baseUrl?: string } = {},
  ): AshrApiClient {
    const apiKey = env[ASHR_API_ENV_VAR] ?? env[ASHR_LABS_API_ENV_VAR] ?? null;
    if (options.required !== false && !apiKey) {
      throw new MissingAshrApiKeyError();
    }
    return new AshrApiClient({
      ...options,
      apiKey,
      baseUrl: options.baseUrl ?? env[ASHR_LABS_BASE_URL_ENV_VAR] ?? ASHR_DEFAULT_BASE_URL,
    });
  }

  plan(functionName: string, options: AshrApiCallOptions = {}): AshrApiCallPlan {
    const estimatedCalls = Math.max(1, Math.trunc(options.estimatedCalls ?? 1));
    const plan: AshrApiCallPlan = {
      function: functionName,
      params: redactApiSensitive(options.recordParams ?? options.params ?? {}) as ApiJsonRecord,
      purpose: options.purpose ?? "",
      estimated_calls: estimatedCalls,
      mutates: Boolean(options.mutates),
      notes: [],
      base_url: this.baseUrl,
      field_map_version: ASHR_API_FIELD_MAP_VERSION,
    };
    if (options.preflight !== undefined) {
      plan.preflight = redactApiSensitive(options.preflight) as ApiJsonRecord;
    }
    if (options.outputPath !== undefined) {
      plan.output_path = options.outputPath;
    }
    return plan;
  }

  async call(functionName: string, options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    const dryRun = options.dryRun ?? true;
    const purpose = options.purpose ?? "";
    const mutates = Boolean(options.mutates);
    const plan = this.plan(functionName, options);
    const requestSummary = requestSummaryFor(functionName, plan.params, plan.estimated_calls, mutates, plan.preflight);
    const startedAt = utcNow();
    const started = Date.now();

    if (dryRun) {
      return {
        function: functionName,
        dry_run: true,
        purpose,
        started_at: startedAt,
        ended_at: utcNow(),
        duration_ms: elapsedMs(started),
        attempts: 0,
        status: "planned",
        status_code: null,
        request: requestSummary,
        response: { plan: redactApiSensitive(plan) as ApiJsonRecord },
        response_headers: {},
        output_path: options.outputPath,
        field_map_version: ASHR_API_FIELD_MAP_VERSION,
      };
    }

    if (!this.apiKey) {
      throw new MissingAshrApiKeyError(`${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} environment variable is required for non-dry-run calls`);
    }

    let attempts = 0;
    let statusCode: number | null = null;
    let lastError: AshrApiError | null = null;
    for (let retryIndex = 0; retryIndex <= this.maxRetries; retryIndex += 1) {
      attempts += 1;
      try {
        const response = await this.request(functionName, options.params ?? {});
        statusCode = response.statusCode;
        const record: AshrApiCallRecord = {
          function: functionName,
          dry_run: false,
          purpose,
          started_at: startedAt,
          ended_at: utcNow(),
          duration_ms: elapsedMs(started),
          attempts,
          status: "ok",
          status_code: response.statusCode,
          request: requestSummary,
          response: response.body,
          response_headers: response.headers,
          output_path: options.outputPath,
          field_map_version: ASHR_API_FIELD_MAP_VERSION,
        };
        attachResponseSummary(record);
        return redactApiSensitive(record) as AshrApiCallRecord;
      } catch (error) {
        lastError = error instanceof AshrApiError ? error : new AshrApiError(String(error), { errorKind: "client" });
        statusCode = lastError.statusCode;
        if (!isRetryableStatus(statusCode) || retryIndex >= this.maxRetries) {
          break;
        }
        await sleep(this.retryBackoffMs * 2 ** retryIndex);
      }
    }

    const record: AshrApiCallRecord = {
      function: functionName,
      dry_run: false,
      purpose,
      started_at: startedAt,
      ended_at: utcNow(),
      duration_ms: elapsedMs(started),
      attempts,
      status: "error",
      status_code: statusCode,
      request: requestSummary,
      response_headers: {},
      error: lastError?.toJSON() ?? { message: "unknown Ashr API error", status_code: statusCode },
      output_path: options.outputPath,
      field_map_version: ASHR_API_FIELD_MAP_VERSION,
    };
    const payload = redactApiSensitive(record) as AshrApiCallRecord;
    throw new AshrApiError(String(payload.error?.message ?? "Ashr API error"), {
      statusCode,
      response: payload as unknown as ApiJsonRecord,
      errorKind: String(payload.error?.error_kind ?? "api"),
    });
  }

  init(options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("init", { purpose: "Resolve Ashr session context", estimatedCalls: 1, mutates: false, ...options });
  }

  healthCheck(options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("keep_alive", { purpose: "Check Ashr API reachability", estimatedCalls: 1, mutates: false, ...options });
  }

  listAgents(options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("list_agents", { purpose: "List tenant agents for SDK parity calibration", estimatedCalls: 1, mutates: false, ...options });
  }

  listDatasets(options: AshrApiCallOptions & { limit?: number; cursor?: number } = {}): Promise<AshrApiCallRecord> {
    const params: ApiJsonRecord = { limit: options.limit ?? 5, include_signed_urls: false };
    if (options.cursor !== undefined) {
      params.cursor = options.cursor;
    }
    return this.callWithSession("list_datasets", { ...options, params, purpose: options.purpose ?? "List datasets for field calibration", estimatedCalls: 2, mutates: false }, { tenant: true });
  }

  getDataset(datasetId: number, options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("get_dataset", {
      purpose: "Fetch one dataset shape for replay calibration",
      estimatedCalls: 2,
      mutates: false,
      ...options,
      params: { dataset_id: datasetId, include_signed_urls: false },
    });
  }

  listRuns(options: AshrApiCallOptions & { datasetId?: number; limit?: number } = {}): Promise<AshrApiCallRecord> {
    const params: ApiJsonRecord = { limit: options.limit ?? 5 };
    if (options.datasetId !== undefined) {
      params.dataset_id = options.datasetId;
    }
    return this.callWithSession("list_runs", { ...options, params, purpose: options.purpose ?? "List run shapes for polling calibration", estimatedCalls: 2, mutates: false }, { tenant: true });
  }

  getRun(runId: number, options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("get_run", { purpose: "Fetch one run shape for polling calibration", estimatedCalls: 1, mutates: false, ...options, params: { run_id: runId } });
  }

  createRun(options: AshrApiCallOptions & { datasetId: number; result: ApiJsonRecord; runnerId?: number }):
    Promise<AshrApiCallRecord> {
    this.requireZeroRetriesForMutation("create_run", options.dryRun ?? true);
    const params: ApiJsonRecord = { dataset_id: options.datasetId, result: options.result };
    if (options.runnerId !== undefined) {
      params.runner_id = options.runnerId;
    }
    return this.callWithSession("create_run", { ...options, params, purpose: options.purpose ?? "Deploy local run result to Ashr", estimatedCalls: 2, mutates: true }, { tenant: true });
  }

  pollRun(options: AshrApiCallOptions & { runId: number; timeoutSeconds?: number; pollIntervalSeconds?: number }): Promise<AshrApiCallRecord> {
    const timeoutSeconds = options.timeoutSeconds ?? 300;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 20;
    const estimatedCalls = Math.max(1, Math.trunc(timeoutSeconds / Math.max(1, pollIntervalSeconds)) + 1);
    const params = { run_id: options.runId, timeout_seconds: timeoutSeconds, poll_interval_seconds: pollIntervalSeconds };
    if (options.dryRun ?? true) {
      return this.call("poll_run", { ...options, params, purpose: options.purpose ?? "Poll deployed run grading status", estimatedCalls, mutates: false });
    }
    return this.pollUntil({
      functionName: "get_run",
      params: { run_id: options.runId },
      complete: (response) => runHasResult(response.run),
      failure: () => null,
      purpose: options.purpose ?? "Poll deployed run grading status",
      estimatedCalls,
      timeoutSeconds,
      pollIntervalSeconds,
      outputPath: options.outputPath,
    });
  }

  listRequests(options: AshrApiCallOptions & { limit?: number; status?: string; cursor?: number } = {}): Promise<AshrApiCallRecord> {
    const params: ApiJsonRecord = { limit: options.limit ?? 5 };
    if (options.status !== undefined) {
      params.status = options.status;
    }
    if (options.cursor !== undefined) {
      params.cursor = options.cursor;
    }
    return this.callWithSession("list_requests", { ...options, params, purpose: options.purpose ?? "List generation request shapes", estimatedCalls: 2, mutates: false }, { tenant: true });
  }

  getRequest(requestId: number, options: AshrApiCallOptions = {}): Promise<AshrApiCallRecord> {
    return this.call("get_request", { purpose: "Poll one generation request", estimatedCalls: 1, mutates: false, ...options, params: { request_id: requestId } });
  }

  pollRequest(options: AshrApiCallOptions & { requestId: number; timeoutSeconds?: number; pollIntervalSeconds?: number }): Promise<AshrApiCallRecord> {
    const timeoutSeconds = options.timeoutSeconds ?? 600;
    const pollIntervalSeconds = options.pollIntervalSeconds ?? 5;
    const estimatedCalls = Math.max(1, Math.trunc(timeoutSeconds / Math.max(1, pollIntervalSeconds)) + 1);
    const params = { request_id: options.requestId, timeout_seconds: timeoutSeconds, poll_interval_seconds: pollIntervalSeconds };
    if (options.dryRun ?? true) {
      return this.call("poll_request", { ...options, params, purpose: options.purpose ?? "Poll generation request status", estimatedCalls, mutates: false });
    }
    return this.pollUntil({
      functionName: "get_request",
      params: { request_id: options.requestId },
      complete: (response) => isRecord(response.request) && response.request.request_status === "completed",
      failure: requestFailureResult,
      purpose: options.purpose ?? "Poll generation request status",
      estimatedCalls,
      timeoutSeconds,
      pollIntervalSeconds,
      outputPath: options.outputPath,
    });
  }

  createRequest(
    options: AshrApiCallOptions & {
      requestName: string;
      request: ApiJsonRecord;
      requestInputSchema?: ApiJsonRecord;
      requestorId?: number;
      allowMediaGeneration?: boolean;
      allowNonTextInputs?: boolean;
      maxRequestVariations?: number;
    },
  ): Promise<AshrApiCallRecord> {
    this.requireZeroRetriesForMutation("create_request", options.dryRun ?? true);
    const requestInputSchema = options.requestInputSchema ?? buildDefaultApiRequestInputSchema(options.request);
    const params: ApiJsonRecord = {
      request_name: options.requestName,
      request: options.request,
      request_input_schema: requestInputSchema,
    };
    if (options.requestorId !== undefined) {
      params.requestor_id = options.requestorId;
    }
    const preflight = summarizeGenerationRequest(options.request);
    preflight.request_input_schema_source = options.requestInputSchema === undefined ? "client_default" : "file";
    if (!(options.dryRun ?? true)) {
      enforceCreateRequestPreflight(preflight, {
        allowMediaGeneration: Boolean(options.allowMediaGeneration),
        allowNonTextInputs: Boolean(options.allowNonTextInputs),
        maxRequestVariations: options.maxRequestVariations ?? 1,
      });
    }
    return this.callWithSession(
      "create_request",
      {
        ...options,
        params,
        recordParams: createRequestRecordParams(params, preflight),
        preflight,
        purpose: options.purpose ?? "Create dataset generation request",
        estimatedCalls: 2,
        mutates: true,
      },
      { tenant: true, user: options.requestorId === undefined },
    );
  }

  toString(): string {
    return `AshrApiClient(baseUrl="${this.baseUrl}", apiKey=${this.apiKey ? "set" : "unset"})`;
  }

  private async callWithSession(
    functionName: string,
    options: AshrApiCallOptions,
    session: { tenant?: boolean; user?: boolean },
  ): Promise<AshrApiCallRecord> {
    const dryRun = options.dryRun ?? true;
    const params = { ...(options.params ?? {}) };
    if (!dryRun && (session.tenant || session.user)) {
      await this.ensureSessionContext();
      if (session.tenant && params.tenant_id === undefined) {
        params.tenant_id = this.tenantId;
      }
      if (session.user && params.requestor_id === undefined && params.user_id === undefined) {
        params.requestor_id = this.userId;
      }
    }
    return this.call(functionName, { ...options, params });
  }

  private async ensureSessionContext(): Promise<void> {
    if (this.tenantId !== null && this.userId !== null) {
      return;
    }
    if (!this.apiKey) {
      throw new MissingAshrApiKeyError(`${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} environment variable is required for session resolution`);
    }
    const response = await this.request("init", {});
    const tenant = isRecord(response.body.tenant) ? response.body.tenant : {};
    const user = isRecord(response.body.user) ? response.body.user : {};
    this.tenantId = Number(tenant.id);
    this.userId = Number(user.id);
    if (!Number.isFinite(this.tenantId) || !Number.isFinite(this.userId)) {
      throw new AshrApiError("init response did not include tenant.id and user.id", { response: response.body, errorKind: "api" });
    }
  }

  private requireZeroRetriesForMutation(functionName: string, dryRun: boolean): void {
    if (!dryRun && this.maxRetries !== 0) {
      throw new Error(`${functionName} execution requires maxRetries=0 to avoid duplicate mutation on retry`);
    }
  }

  private async request(functionName: string, params: ApiJsonRecord): Promise<{ statusCode: number; body: ApiJsonRecord; headers: ApiJsonRecord }> {
    if (!this.apiKey) {
      throw new MissingAshrApiKeyError(`${ASHR_API_ENV_VAR} or ${ASHR_LABS_API_ENV_VAR} environment variable is required for non-dry-run calls`);
    }
    const payload = { function: functionName, ...params };
    const body = JSON.stringify(payload);
    const headers = { "Content-Type": "application/json", Authorization: `Bearer ${this.apiKey}` };
    const response = await this.transport(this.baseUrl, headers, body, this.timeoutMs);
    const parsedBody = parseApiJsonBody(response.body);
    const selectedHeaders = selectedResponseHeaders(response.headers ?? {});
    if (response.statusCode >= 400) {
      throw new AshrApiError(errorMessage(parsedBody, `HTTP ${response.statusCode}`), {
        statusCode: response.statusCode,
        response: parsedBody,
        responseHeaders: selectedHeaders,
        errorKind: "http",
      });
    }
    if (parsedBody.status === "error") {
      throw new AshrApiError(errorMessage(parsedBody, "Ashr API error"), {
        statusCode: response.statusCode,
        response: parsedBody,
        responseHeaders: selectedHeaders,
        errorKind: "api",
      });
    }
    return { statusCode: response.statusCode, body: parsedBody, headers: selectedHeaders };
  }

  private async pollUntil(options: {
    functionName: string;
    params: ApiJsonRecord;
    complete: (response: ApiJsonRecord) => boolean;
    failure: (response: ApiJsonRecord) => null | string | ApiJsonRecord;
    purpose: string;
    estimatedCalls: number;
    timeoutSeconds: number;
    pollIntervalSeconds: number;
    outputPath?: string;
  }): Promise<AshrApiCallRecord> {
    const startedAt = utcNow();
    const started = Date.now();
    let attempts = 0;
    let lastResponse: ApiJsonRecord | null = null;
    let lastStatusCode: number | null = null;
    let lastHeaders: ApiJsonRecord = {};
    while (true) {
      attempts += 1;
      const response = await this.request(options.functionName, options.params);
      lastResponse = response.body;
      lastStatusCode = response.statusCode;
      lastHeaders = response.headers;
      const failureResult = options.failure(response.body);
      if (failureResult) {
        const failureError = pollFailureError(failureResult, response.statusCode);
        const record = {
          function: options.functionName,
          dry_run: false,
          purpose: options.purpose,
          started_at: startedAt,
          ended_at: utcNow(),
          duration_ms: elapsedMs(started),
          attempts,
          status: "error",
          status_code: response.statusCode,
          request: requestSummaryFor(options.functionName, redactApiSensitive(options.params) as ApiJsonRecord, options.estimatedCalls, false),
          response: response.body,
          response_headers: response.headers,
          error: failureError,
          output_path: options.outputPath,
          field_map_version: ASHR_API_FIELD_MAP_VERSION,
        } satisfies AshrApiCallRecord;
        attachResponseSummary(record);
        throw new AshrApiError(String(failureError.message ?? "request failed"), { statusCode: response.statusCode, response: redactApiSensitive(record) as ApiJsonRecord });
      }
      if (options.complete(response.body)) {
        const record = {
          function: options.functionName,
          dry_run: false,
          purpose: options.purpose,
          started_at: startedAt,
          ended_at: utcNow(),
          duration_ms: elapsedMs(started),
          attempts,
          status: "ok",
          status_code: response.statusCode,
          request: requestSummaryFor(options.functionName, redactApiSensitive(options.params) as ApiJsonRecord, options.estimatedCalls, false),
          response: response.body,
          response_headers: response.headers,
          output_path: options.outputPath,
          field_map_version: ASHR_API_FIELD_MAP_VERSION,
        } satisfies AshrApiCallRecord;
        attachResponseSummary(record);
        return redactApiSensitive(record) as AshrApiCallRecord;
      }
      if ((Date.now() - started) / 1000 >= options.timeoutSeconds) {
        const record = {
          function: options.functionName,
          dry_run: false,
          purpose: options.purpose,
          started_at: startedAt,
          ended_at: utcNow(),
          duration_ms: elapsedMs(started),
          attempts,
          status: "timeout",
          status_code: lastStatusCode,
          request: requestSummaryFor(options.functionName, redactApiSensitive(options.params) as ApiJsonRecord, options.estimatedCalls, false),
          response: lastResponse,
          response_headers: lastHeaders,
          error: { message: `${options.functionName} did not complete within ${options.timeoutSeconds}s`, status_code: lastStatusCode },
          output_path: options.outputPath,
          field_map_version: ASHR_API_FIELD_MAP_VERSION,
        } satisfies AshrApiCallRecord;
        throw new AshrApiError(String(record.error.message), { statusCode: lastStatusCode, response: redactApiSensitive(record) as ApiJsonRecord, errorKind: "timeout" });
      }
      await sleep(Math.max(0, options.pollIntervalSeconds) * 1000);
    }
  }
}

export function summarizeGenerationRequest(request: ApiJsonRecord): ApiJsonRecord {
  const generationOptions = isRecord(request.generation_options) ? request.generation_options : {};
  const testConfig = isRecord(request.test_config) ? request.test_config : {};
  const agent = isRecord(request.agent) ? request.agent : {};
  const acceptedInputsRaw = isRecord(agent.accepted_inputs) ? agent.accepted_inputs : undefined;
  const acceptedInputsProvided = acceptedInputsRaw !== undefined;
  const acceptedFlags: Record<string, boolean> = {};
  const acceptedFlagShapes: Record<string, boolean> = {};
  for (const key of ["text", "audio", "file", "image", "video", "conversation"]) {
    if (!acceptedInputsProvided) {
      acceptedFlags[key] = key === "text";
      acceptedFlagShapes[key] = true;
      continue;
    }
    const [enabled, shapeSupported] = acceptedInputEnabled(acceptedInputsRaw[key]);
    acceptedFlags[key] = enabled;
    acceptedFlagShapes[key] = shapeSupported;
  }
  const agentInputPartTypes: string[] = [];
  if (acceptedFlags.text) {
    agentInputPartTypes.push("text");
  }
  for (const key of ["image", "audio", "file", "video"]) {
    if (acceptedFlags[key]) {
      agentInputPartTypes.push(key);
    }
  }
  const mediaGeneration = {
    audio: Boolean(generationOptions.generate_audio),
    files: Boolean(generationOptions.generate_files),
    images: Boolean(generationOptions.generate_images),
    videos: Boolean(generationOptions.generate_videos),
    simulations: Boolean(generationOptions.generate_simulations),
  };
  const rawVariations = testConfig.num_variations ?? request.num_variations;
  const numVariations = coercePositiveInt(rawVariations);
  return {
    num_variations: numVariations,
    num_variations_known: numVariations !== null,
    media_generation: mediaGeneration,
    media_generation_enabled: Object.values(mediaGeneration).some(Boolean),
    accepted_inputs_known: Object.values(acceptedFlagShapes).every(Boolean),
    accepted_input_flags: acceptedFlags,
    agent_input_part_types: agentInputPartTypes,
    agent_input_schema_version: agentInputPartTypes.some((partType) => partType !== "text") ? ASHR_API_AGENT_INPUT_SCHEMA_VERSION : null,
    non_text_inputs_enabled: ["audio", "file", "image", "video", "conversation"].some((key) => acceptedFlags[key]),
    small_batch: numVariations !== null && numVariations <= 1,
    notes: [
      "dry-run-first mutating create_request calibration",
      "use maxRetries=0 for real mutating execution",
      "request params are recorded as shape summaries; raw API responses stay private",
    ],
  };
}

export function enforceCreateRequestPreflight(
  preflight: ApiJsonRecord,
  options: { allowMediaGeneration?: boolean; allowNonTextInputs?: boolean; maxRequestVariations?: number } = {},
): void {
  if (preflight.accepted_inputs_known === false) {
    throw new Error("create-request accepted_inputs shape is unsupported; use booleans or {enabled: bool} before real execution");
  }
  if (preflight.num_variations_known === false) {
    throw new Error("create-request num_variations is unknown; set test_config.num_variations before real execution");
  }
  if (preflight.media_generation_enabled === true && !options.allowMediaGeneration) {
    throw new Error("create-request enables media generation; rerun with allowMediaGeneration only after reviewing usage/cost risk");
  }
  if (preflight.non_text_inputs_enabled === true && !options.allowNonTextInputs) {
    throw new Error("create-request accepts non-text inputs; rerun with allowNonTextInputs only after reviewing usage/cost risk");
  }
  const maxRequestVariations = Math.max(1, Math.trunc(options.maxRequestVariations ?? 1));
  if (typeof preflight.num_variations === "number" && preflight.num_variations > maxRequestVariations) {
    throw new Error(`create-request num_variations=${preflight.num_variations} exceeds maxRequestVariations=${maxRequestVariations}`);
  }
}

export function redactApiText(value: string): string {
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

export function redactApiSensitive(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactApiSensitive(item));
  }
  if (isRecord(value)) {
    const redacted: ApiJsonRecord = {};
    for (const [key, item] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      if (normalized === "key" || ["api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential"].some((part) => normalized.includes(part))) {
        redacted[key] = "[redacted]";
      } else {
        redacted[key] = redactApiSensitive(item);
      }
    }
    return redacted;
  }
  return typeof value === "string" ? redactApiText(value) : value;
}

async function fetchTransport(url: string, headers: Record<string, string>, body: string, timeoutMs: number): Promise<ApiTransportResponse> {
  const fetchFn = globalThis.fetch;
  if (typeof fetchFn !== "function") {
    throw new AshrApiError("No fetch transport is available; pass an injected AshrApiTransport", { errorKind: "client" });
  }
  const controller = typeof AbortController !== "undefined" ? new AbortController() : undefined;
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : undefined;
  try {
    const response = await fetchFn(url, {
      method: "POST",
      headers,
      body,
      signal: controller?.signal,
    });
    const responseHeaders: Record<string, string> = {};
    response.headers.forEach((value, key) => {
      responseHeaders[key] = value;
    });
    return { statusCode: response.status, body: await response.text(), headers: responseHeaders };
  } catch (error) {
    throw new AshrApiError(`Network error: ${error instanceof Error ? error.message : String(error)}`, { errorKind: "network" });
  } finally {
    if (timeout !== undefined) {
      clearTimeout(timeout);
    }
  }
}

function buildDefaultApiRequestInputSchema(request: ApiJsonRecord | undefined = undefined): ApiJsonRecord {
  const schema: ApiJsonRecord = { type: "object", additionalProperties: true };
  const agent = isRecord(request?.agent) ? request.agent : undefined;
  if (agent && Array.isArray(agent.tools)) {
    schema.tools = redactApiSensitive(agent.tools);
  }
  const enabledPartTypes = enabledAgentInputPartTypes(request);
  if (enabledPartTypes.some((partType) => ["image", "audio", "file", "video"].includes(partType))) {
    Object.assign(schema, agentInputSchema(enabledPartTypes));
  }
  return schema;
}

function createRequestRecordParams(params: ApiJsonRecord, preflight: ApiJsonRecord): ApiJsonRecord {
  const request = isRecord(params.request) ? params.request : {};
  const schema = isRecord(params.request_input_schema) ? params.request_input_schema : {};
  const record: ApiJsonRecord = {
    request_name: params.request_name,
    request: generationRequestShape(request),
    request_input_schema: schemaShape(schema),
    preflight_summary: redactApiSensitive(preflight),
  };
  if ("requestor_id" in params) {
    record.requestor_id_present = params.requestor_id !== undefined && params.requestor_id !== null;
  }
  return record;
}

function generationRequestShape(request: ApiJsonRecord): ApiJsonRecord {
  const agent = isRecord(request.agent) ? request.agent : {};
  const generationOptions = isRecord(request.generation_options) ? request.generation_options : {};
  const testConfig = isRecord(request.test_config) ? request.test_config : {};
  const metadata = isRecord(request.metadata) ? request.metadata : {};
  const acceptedInputs = isRecord(agent.accepted_inputs) ? agent.accepted_inputs : {};
  return {
    top_level_keys: sortedKeys(request),
    agent_keys: sortedKeys(agent),
    agent_name_present: Boolean(agent.name),
    tools_count: Array.isArray(agent.tools) ? agent.tools.length : 0,
    accepted_input_flags: Object.fromEntries(["text", "audio", "file", "image", "video", "conversation"].map((key) => [key, truthyEnabled(acceptedInputs[key])])),
    generation_options: Object.fromEntries(["generate_audio", "generate_files", "generate_images", "generate_videos", "generate_simulations"].map((key) => [key, Boolean(generationOptions[key])])),
    metadata_keys: sortedKeys(metadata),
    test_config_keys: sortedKeys(testConfig),
    num_variations: testConfig.num_variations ?? null,
  };
}

function schemaShape(schema: ApiJsonRecord): ApiJsonRecord {
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const defs = isRecord(schema.$defs) ? schema.$defs : {};
  const partSchema = isRecord(defs.agent_input_part) ? defs.agent_input_part : {};
  return {
    keys: sortedKeys(schema),
    type: schema.type,
    additionalProperties: schema.additionalProperties,
    tools_count: Array.isArray(schema.tools) ? schema.tools.length : 0,
    property_keys: sortedKeys(properties),
    defs_keys: sortedKeys(defs),
    agent_input_schema_version: isRecord(properties.schema_version) ? properties.schema_version.const ?? null : null,
    agent_input_part_types: schemaAgentInputPartTypes(partSchema),
  };
}

function requestFailureResult(response: ApiJsonRecord): null | ApiJsonRecord {
  const request = isRecord(response.request) ? response.request : {};
  if (request.request_status !== "failed") {
    return null;
  }
  return { message: "request failed", failure_summary: summarizeRequestFailure(response) };
}

function summarizeRequestFailure(response: ApiJsonRecord): ApiJsonRecord {
  const request = isRecord(response.request) ? response.request : {};
  const nestedRequest = isRecord(request.request) ? request.request : {};
  const summary: ApiJsonRecord = {
    request_status: typeof request.request_status === "string" ? request.request_status : null,
    top_level_failure_like_keys: sortedKeys(request).filter(isFailureLikeKey),
    nested_request_keys: sortedKeys(nestedRequest),
  };
  const failureSources: ApiJsonRecord = {};
  if (nestedRequest._failure !== undefined) {
    failureSources["request._failure"] = safeValueShape(nestedRequest._failure, 2);
  }
  if (request._failure !== undefined) {
    failureSources._failure = safeValueShape(request._failure, 2);
  }
  for (const key of ["failure", "error", "message", "detail", "reason"]) {
    if (request[key] !== undefined) {
      failureSources[key] = safeValueShape(request[key], 1);
    }
  }
  if (Object.keys(failureSources).length > 0) {
    summary.failure_sources = failureSources;
  }
  return summary;
}

function attachResponseSummary(record: AshrApiCallRecord): void {
  if (!isRecord(record.response)) {
    return;
  }
  const requestFailure = summarizeRequestFailure(record.response);
  if (requestFailure.request_status === "failed" || (Array.isArray(requestFailure.top_level_failure_like_keys) && requestFailure.top_level_failure_like_keys.length > 0) || isRecord(requestFailure.failure_sources)) {
    record.response_summary = { request_failure: requestFailure };
  }
}

function parseApiJsonBody(body: unknown): ApiJsonRecord {
  let parsed: unknown;
  if (typeof body === "string") {
    try {
      parsed = JSON.parse(body);
    } catch (error) {
      throw new AshrApiError(`Invalid JSON response: ${error instanceof Error ? error.message : String(error)}`, { errorKind: "client" });
    }
  } else {
    parsed = body;
  }
  if (!isRecord(parsed)) {
    throw new AshrApiError(`Expected JSON object response, got ${Array.isArray(parsed) ? "array" : typeof parsed}`, { errorKind: "client" });
  }
  return cloneJson(parsed);
}

function enabledAgentInputPartTypes(request: ApiJsonRecord | undefined): string[] {
  const agent = isRecord(request?.agent) ? request.agent : undefined;
  const acceptedInputs = agent && isRecord(agent.accepted_inputs) ? agent.accepted_inputs : undefined;
  const enabled: string[] = [];
  if (acceptedInputs === undefined || truthyEnabled(acceptedInputs.text)) {
    enabled.push("text");
  }
  for (const partType of ["image", "audio", "file", "video"]) {
    if (acceptedInputs !== undefined && truthyEnabled(acceptedInputs[partType])) {
      enabled.push(partType);
    }
  }
  return enabled;
}

function agentInputSchema(enabledPartTypes: string[]): ApiJsonRecord {
  const partTypes = ["text", "image", "audio", "file", "video"].filter((partType) => enabledPartTypes.includes(partType));
  return {
    properties: {
      schema_version: { const: ASHR_API_AGENT_INPUT_SCHEMA_VERSION },
      text: { type: "string" },
      parts: { type: "array", items: { $ref: "#/$defs/agent_input_part" } },
      metadata: { type: "object" },
    },
    $defs: { agent_input_part: agentInputPartSchema(partTypes) },
  };
}

function agentInputPartSchema(partTypes: string[]): ApiJsonRecord {
  const textPart = {
    type: "object",
    required: ["type", "text"],
    properties: { type: { const: "text" }, text: { type: "string" } },
    additionalProperties: true,
  };
  const mediaPartTypes = partTypes.filter((partType) => ["image", "audio", "file", "video"].includes(partType));
  const variants: ApiJsonRecord[] = [];
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

function schemaAgentInputPartTypes(partSchema: ApiJsonRecord): string[] {
  if (isRecord(partSchema.properties) && isRecord(partSchema.properties.type)) {
    if (partSchema.properties.type.const) {
      return [String(partSchema.properties.type.const)];
    }
    if (Array.isArray(partSchema.properties.type.enum)) {
      return partSchema.properties.type.enum.map(String).sort();
    }
  }
  const types = new Set<string>();
  const variants = Array.isArray(partSchema.oneOf) ? partSchema.oneOf : [];
  for (const variant of variants) {
    if (!isRecord(variant) || !isRecord(variant.properties) || !isRecord(variant.properties.type)) {
      continue;
    }
    if (variant.properties.type.const) {
      types.add(String(variant.properties.type.const));
    }
    if (Array.isArray(variant.properties.type.enum)) {
      for (const item of variant.properties.type.enum) {
        types.add(String(item));
      }
    }
  }
  return Array.from(types).sort();
}

function selectedResponseHeaders(headers: Record<string, string>): ApiJsonRecord {
  const selected: ApiJsonRecord = {};
  for (const [key, value] of Object.entries(headers)) {
    const lowerKey = key.toLowerCase();
    if (lowerKey === "retry-after" || lowerKey.startsWith("x-ratelimit")) {
      selected[key] = value;
    }
  }
  return selected;
}

function errorMessage(response: ApiJsonRecord, fallback: string): string {
  for (const key of ["message", "error", "detail"]) {
    if (typeof response[key] === "string" && response[key]) {
      return redactApiText(response[key]);
    }
  }
  return fallback;
}

function runHasResult(run: unknown): boolean {
  if (!isRecord(run) || !isRecord(run.result)) {
    return false;
  }
  if (run.result.aggregate_metrics !== undefined) {
    return true;
  }
  return ["status", "total_cases", "passed", "failed", "errored", "timed_out", "trace_completeness"].some((key) => key in (run.result as ApiJsonRecord));
}

function pollFailureError(failureResult: string | ApiJsonRecord, statusCode: number): ApiJsonRecord {
  if (isRecord(failureResult)) {
    const error = redactApiSensitive(failureResult) as ApiJsonRecord;
    error.message = typeof error.message === "string" && error.message ? redactApiText(error.message) : "request failed";
    error.status_code = statusCode;
    return error;
  }
  return { message: redactApiText(String(failureResult)), status_code: statusCode };
}

function requestSummaryFor(functionName: string, params: ApiJsonRecord, estimatedCalls: number, mutates: boolean, preflight?: ApiJsonRecord): ApiJsonRecord {
  const summary: ApiJsonRecord = {
    function: functionName,
    params,
    estimated_calls: estimatedCalls,
    mutates,
  };
  if (preflight !== undefined) {
    summary.preflight = preflight;
  }
  return summary;
}

function acceptedInputEnabled(value: unknown): [boolean, boolean] {
  if (value === undefined || value === null) {
    return [false, true];
  }
  if (typeof value === "boolean") {
    return [value, true];
  }
  if (isRecord(value) && typeof value.enabled === "boolean") {
    return [value.enabled, true];
  }
  return [false, false];
}

function truthyEnabled(value: unknown): boolean {
  return isRecord(value) ? Boolean(value.enabled) : Boolean(value);
}

function coercePositiveInt(value: unknown): number | null {
  if (value === undefined || value === null || typeof value === "boolean") {
    return null;
  }
  if (Number.isInteger(value) && Number(value) > 0) {
    return Number(value);
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    const parsed = Number(value);
    return parsed > 0 ? parsed : null;
  }
  return null;
}

function positiveInteger(value: number, fieldName: string): number {
  const parsed = Math.trunc(Number(value));
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${fieldName} must be a positive integer`);
  }
  return parsed;
}

function isRetryableStatus(statusCode: number | null): boolean {
  return statusCode !== null && [408, 409, 425, 429, 500, 502, 503, 504].includes(statusCode);
}

function sleep(ms: number): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeValueShape(value: unknown, depth: number): ApiJsonRecord {
  const shape: ApiJsonRecord = { type: safeTypeName(value), present: value !== undefined && value !== null };
  if (isRecord(value)) {
    shape.keys = sortedKeys(value);
    if (depth > 0) {
      shape.fields = Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, safeValueShape(item, depth - 1)]));
    }
  } else if (Array.isArray(value)) {
    shape.count = value.length;
    shape.item_types = Array.from(new Set(value.map(safeTypeName))).sort();
  } else if (typeof value === "string") {
    shape.length = value.length;
  }
  return shape;
}

function safeTypeName(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (Array.isArray(value)) {
    return "array";
  }
  return typeof value === "object" ? "object" : typeof value;
}

function isFailureLikeKey(key: string): boolean {
  const normalized = key.toLowerCase().replaceAll("-", "_");
  const exact = ["_failure", "failure", "failures", "failed", "error", "errors", "reason", "reasons", "message", "messages", "detail", "details", "exception", "traceback"];
  return exact.includes(normalized) || ["failure_", "error_", "reason_", "message_", "detail_", "exception_", "traceback_"].some((prefix) => normalized.startsWith(prefix)) || ["_failure", "_error", "_reason", "_message", "_detail", "_exception", "_traceback"].some((suffix) => normalized.endsWith(suffix));
}

function sortedKeys(value: ApiJsonRecord): string[] {
  return Object.keys(value).sort();
}

function utcNow(): string {
  return new Date().toISOString();
}

function elapsedMs(started: number): number {
  return Math.max(0, Date.now() - started);
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function isRecord(value: unknown): value is ApiJsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function processEnv(): Record<string, string | undefined> {
  const candidate = (globalThis as unknown as { process?: { env?: Record<string, string | undefined> } }).process;
  return candidate?.env ?? {};
}
