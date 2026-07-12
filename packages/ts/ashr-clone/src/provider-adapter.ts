export type ModelProvider = "openai-compatible" | "ollama";
export type ProviderModality = "text" | "image" | "audio" | "file" | "video";
export type ProviderCapabilityState = "discovered" | "planned" | "callable" | "failed" | "unsupported";
export type ProviderErrorCode =
  | "authentication_error"
  | "rate_limit"
  | "provider_unavailable"
  | "invalid_request"
  | "invalid_response"
  | "invalid_stream"
  | "timeout"
  | "network_error";

export const MODEL_INPUT_PART_TYPES = Object.freeze([
  "text",
  "image",
  "audio",
  "file",
  "video",
] as const);
export const MODEL_PROVIDERS = Object.freeze([
  "openai_compatible",
  "ollama",
] as const);

export interface ProviderInputPart {
  type: ProviderModality;
  text?: string;
  url?: string;
  path?: string;
  source?: string;
  data?: string;
  mime_type?: string;
  name?: string;
}
export interface ProviderTool { name: string; description?: string; parameters?: Record<string, unknown> }
export interface ProviderToolCall { id: string; name: string; arguments: string }
export interface ProviderUsage { input_tokens: number; output_tokens: number; total_tokens: number }
export interface ProviderRequest {
  model: string;
  input: string | ProviderInputPart[];
  tools?: ProviderTool[];
  stream?: boolean;
  temperature?: number;
  max_tokens?: number;
}
export interface ProviderResult {
  provider: ModelProvider;
  model: string;
  text: string;
  tool_calls: ProviderToolCall[];
  usage: ProviderUsage;
  finish_reason: string | null;
  request_id?: string;
  raw: unknown;
}
export type ModelInputPart = ProviderInputPart;
export type ModelToolCall = ProviderToolCall;
export type ModelUsage = ProviderUsage;
export type ModelResponse = ProviderResult;
export interface ModelMessage {
  role: "system" | "user" | "assistant" | "tool" | string;
  parts: ModelInputPart[];
  name?: string;
  tool_call_id?: string;
}
export interface ModelStreamChunk {
  text: string;
  tool_calls: ModelToolCall[];
  usage?: ModelUsage;
  finish_reason?: string | null;
  raw?: unknown;
}
export interface ModelHTTPResponse {
  status_code: number;
  body:
    | Uint8Array
    | string
    | Record<string, unknown>
    | AsyncIterable<Uint8Array | string | Record<string, unknown>>;
  headers?: Readonly<Record<string, string>>;
}
export type ModelHTTPTransport = (
  method: string,
  url: string,
  headers: Readonly<Record<string, string>>,
  body: Uint8Array,
  timeoutSeconds: number,
  stream: boolean,
) => ModelHTTPResponse | Promise<ModelHTTPResponse>;
export interface ModelProviderAdapterOptions {
  provider: ModelProvider;
  baseUrl: string;
  apiKey?: string;
  fetch?: typeof globalThis.fetch;
  headers?: Record<string, string>;
  timeoutMs?: number;
  maxRetries?: number;
  retryBackoffMs?: number;
  sleep?: (milliseconds: number) => Promise<void>;
}
export interface ProviderCapabilityEvidence {
  state: ProviderCapabilityState;
  checked_at?: string;
  detail?: string;
}
export interface ProviderCapabilityProfile {
  provider: ModelProvider;
  model: string;
  modalities: Record<ProviderModality, ProviderCapabilityEvidence>;
  stream: ProviderCapabilityEvidence;
  tools: ProviderCapabilityEvidence;
  usage: ProviderCapabilityEvidence;
}
export interface ModelCapabilityCalibration {
  provider: ModelProvider;
  model: string;
  endpoint_sha256: string;
  calibrated_at: string;
  evidence_sha256: string;
  capabilities: Readonly<Record<string, "callable" | "failed" | "unsupported">>;
}

export const PROVIDER_CAPABILITY_MANIFEST = {
  modalities: {
    text: "callable",
    image: "discovered",
    audio: "discovered",
    file: "discovered",
    video: "discovered",
  } satisfies Record<ProviderModality, ProviderCapabilityState>,
  providers: {
    "openai-compatible": { stream: "callable", tools: "callable", usage: "callable", protocol: "sse" },
    ollama: { stream: "callable", tools: "discovered", usage: "callable", protocol: "ndjson" },
  },
} as const;

export function createCapabilityProfile(
  provider: ModelProvider,
  model: string,
  evidence: Partial<Record<ProviderModality | "stream" | "tools" | "usage", ProviderCapabilityEvidence>> = {},
): ProviderCapabilityProfile {
  const defaults = PROVIDER_CAPABILITY_MANIFEST.providers[provider];
  const capability = (
    name: ProviderModality | "stream" | "tools" | "usage",
    fallback: ProviderCapabilityState,
  ): ProviderCapabilityEvidence => evidence[name] ?? { state: fallback };
  return {
    provider,
    model,
    modalities: {
      text: capability("text", "callable"),
      image: capability("image", "discovered"),
      audio: capability("audio", "discovered"),
      file: capability("file", "discovered"),
      video: capability("video", "discovered"),
    },
    stream: capability("stream", defaults.stream),
    tools: capability("tools", defaults.tools),
    usage: capability("usage", defaults.usage),
  };
}

export async function createCapabilityCalibration(options: {
  provider: ModelProvider;
  model: string;
  baseUrl: string;
  calibratedAt: string;
  evidence: string | Uint8Array;
  capabilities: Readonly<Record<string, "callable" | "failed" | "unsupported">>;
}): Promise<ModelCapabilityCalibration> {
  const allowed = new Set(["text", "image", "audio", "file", "video", "stream", "tools", "usage"]);
  const terminalStates = new Set(["callable", "failed", "unsupported"]);
  const entries = Object.entries(options.capabilities);
  if (!options.model.trim() || !/^https?:\/\//.test(options.baseUrl)) {
    throw new Error("model and HTTP(S) baseUrl are required");
  }
  if (!entries.length || entries.some(([name]) => !allowed.has(name))) {
    throw new Error("unsupported or empty capability calibration");
  }
  if (entries.some(([, state]) => !terminalStates.has(state))) {
    throw new Error("calibrated capabilities require terminal evidence states");
  }
  const evidenceBytes =
    typeof options.evidence === "string" ? new TextEncoder().encode(options.evidence) : options.evidence;
  if (!evidenceBytes.byteLength) {
    throw new Error("calibration evidence is required");
  }
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(options.calibratedAt);
  if (!hasTimezone || !Number.isFinite(Date.parse(options.calibratedAt))) {
    throw new Error("calibratedAt must be a valid timezone-aware ISO-8601 timestamp");
  }
  return {
    provider: options.provider,
    model: options.model,
    endpoint_sha256: await digest(options.baseUrl.replace(/\/$/, "")),
    calibrated_at: options.calibratedAt,
    evidence_sha256: await digest(evidenceBytes),
    capabilities: Object.freeze(Object.fromEntries(entries)),
  };
}

export class ModelProviderError extends Error {
  constructor(
    public readonly code: ProviderErrorCode,
    message: string,
    public readonly retryable: boolean,
    public readonly status?: number,
    public readonly request_id?: string,
  ) {
    super(redact(message));
    this.name = "ModelProviderError";
  }
}

export class ModelAdapterError extends ModelProviderError {
  constructor(
    kind: ProviderErrorCode,
    message: string,
    options: { retryable?: boolean; status_code?: number; request_id?: string } = {},
  ) {
    super(kind, message, options.retryable ?? false, options.status_code, options.request_id);
    this.name = "ModelAdapterError";
  }

  get kind(): ProviderErrorCode {
    return this.code;
  }

  get status_code(): number | undefined {
    return this.status;
  }

  toJSON(): Record<string, unknown> {
    return {
      kind: this.kind,
      message: this.message,
      status_code: this.status_code,
      retryable: this.retryable,
    };
  }
}

export class ModelProviderAdapter {
  private readonly fetchImpl: typeof globalThis.fetch;

  constructor(private readonly options: ModelProviderAdapterOptions) {
    this.fetchImpl = options.fetch ?? globalThis.fetch;
    if (!this.fetchImpl) throw new ModelProviderError("network_error", "fetch unavailable", false);
  }

  async run(request: ProviderRequest): Promise<ProviderResult> {
    const maxRetries = Math.max(0, this.options.maxRetries ?? 2);
    let lastError: ModelProviderError | undefined;
    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      try {
        return await this.runAttempt(request);
      } catch (error) {
        const normalized = normalizeError(error);
        lastError = normalized;
        if (!normalized.retryable || attempt >= maxRetries) throw normalized;
        const delay = Math.max(0, this.options.retryBackoffMs ?? 250) * (2 ** attempt);
        await (this.options.sleep ?? sleep)(delay);
      }
    }
    throw lastError ?? new ModelProviderError("network_error", "provider request failed", true);
  }

  private async runAttempt(request: ProviderRequest): Promise<ProviderResult> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 60_000);
    try {
      const openai = this.options.provider === "openai-compatible";
      const response = await this.fetchImpl(
        `${this.options.baseUrl.replace(/\/$/, "")}${openai ? "/chat/completions" : "/api/chat"}`,
        {
          method: "POST",
          signal: controller.signal,
          headers: {
            "content-type": "application/json",
            ...(this.options.apiKey ? { authorization: `Bearer ${this.options.apiKey}` } : {}),
            ...this.options.headers,
          },
          body: JSON.stringify(openai ? openAIRequest(request) : ollamaRequest(request)),
        },
      );
      const requestId = response.headers.get("x-request-id") ?? undefined;
      if (!response.ok) throw await httpError(response, requestId);
      if (request.stream) {
        if (!response.body) {
          throw new ModelProviderError("invalid_stream", "missing stream body", true, response.status, requestId);
        }
        // Stream consumption is observable, so failures after this point cannot replay the request.
        try {
          return await (
            openai
              ? parseOpenAIStream(response.body, request.model, requestId)
              : parseOllamaStream(response.body, request.model, requestId)
          );
        } catch (error) {
          const normalized = normalizeError(error);
          throw new ModelProviderError(
            normalized.code,
            normalized.message,
            false,
            normalized.status,
            normalized.request_id,
          );
        }
      }
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        throw new ModelProviderError("invalid_response", "invalid provider JSON", false, response.status, requestId);
      }
      return openai
        ? normalizeOpenAI(payload, request.model, requestId)
        : normalizeOllama(payload, request.model, requestId);
    } finally {
      clearTimeout(timer);
    }
  }
}

export const ProviderNeutralModelAdapter = ModelProviderAdapter;

function openAIRequest(request: ProviderRequest): Record<string, unknown> {
  const parts = normalizeParts(request.input);
  return compact({
    model: request.model,
    stream: Boolean(request.stream),
    stream_options: request.stream ? { include_usage: true } : undefined,
    temperature: request.temperature,
    max_tokens: request.max_tokens,
    messages: [{ role: "user", content: parts.map(openAIPart) }],
    tools: request.tools?.map((tool) => ({
      type: "function",
      function: { name: tool.name, description: tool.description, parameters: tool.parameters ?? {} },
    })),
  });
}

function ollamaRequest(request: ProviderRequest): Record<string, unknown> {
  const parts = normalizeParts(request.input);
  const images = parts.filter((part) => part.type === "image").map(sourceOf).filter(Boolean);
  const attachments = parts
    .filter((part) => ["audio", "file", "video"].includes(part.type))
    .map((part) => compact({
      type: part.type,
      source: sourceOf(part),
      mime_type: part.mime_type,
      name: part.name,
    }));
  return compact({
    model: request.model,
    stream: Boolean(request.stream),
    messages: [{
      role: "user",
      content: parts.filter((part) => part.type === "text").map((part) => part.text ?? "").join("\n"),
      images: images.length ? images : undefined,
      attachments: attachments.length ? attachments : undefined,
    }],
    tools: request.tools?.map((tool) => ({
      type: "function",
      function: { name: tool.name, description: tool.description, parameters: tool.parameters ?? {} },
    })),
    options: compact({ temperature: request.temperature, num_predict: request.max_tokens }),
  });
}

function openAIPart(part: ProviderInputPart): Record<string, unknown> {
  const source = sourceOf(part);
  if (part.type === "text") return { type: "text", text: part.text ?? "" };
  if (part.type === "image") return { type: "image_url", image_url: { url: source } };
  if (part.type === "audio") {
    return {
      type: "input_audio",
      input_audio: { data: part.data ?? source, format: part.mime_type?.split("/")[1] ?? "wav" },
    };
  }
  if (part.type === "file") return compact({ type: "input_file", file_url: source, filename: part.name });
  return compact({ type: "input_video", video_url: source, filename: part.name });
}

function normalizeOpenAI(payload: unknown, model: string, request_id?: string): ProviderResult {
  const root = rec(payload);
  const choice = rec(arr(root.choices)[0]);
  const message = rec(choice.message);
  return {
    provider: "openai-compatible",
    model,
    text: text(message.content),
    tool_calls: openAITools(message.tool_calls),
    usage: openAIUsage(root.usage),
    finish_reason: nullable(choice.finish_reason),
    request_id,
    raw: payload,
  };
}

function normalizeOllama(payload: unknown, model: string, request_id?: string): ProviderResult {
  const root = rec(payload);
  const message = rec(root.message);
  return {
    provider: "ollama",
    model,
    text: text(message.content),
    tool_calls: ollamaTools(message.tool_calls),
    usage: ollamaUsage(root),
    finish_reason: root.done ? String(root.done_reason ?? "stop") : null,
    request_id,
    raw: payload,
  };
}

async function parseOpenAIStream(
  stream: ReadableStream<Uint8Array>,
  model: string,
  request_id?: string,
): Promise<ProviderResult> {
  const result = empty("openai-compatible", model, request_id);
  for await (const line of lines(stream)) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (!data || data === "[DONE]") continue;
    const root = rec(json(data));
    const choice = rec(arr(root.choices)[0]);
    const delta = rec(choice.delta);
    result.text += text(delta.content);
    mergeTools(result.tool_calls, delta.tool_calls);
    if (choice.finish_reason != null) result.finish_reason = String(choice.finish_reason);
    if (root.usage) result.usage = openAIUsage(root.usage);
    result.raw = root;
  }
  return result;
}

async function parseOllamaStream(
  stream: ReadableStream<Uint8Array>,
  model: string,
  request_id?: string,
): Promise<ProviderResult> {
  const result = empty("ollama", model, request_id);
  for await (const line of lines(stream)) {
    if (!line.trim()) continue;
    const root = rec(json(line));
    const message = rec(root.message);
    result.text += text(message.content);
    result.tool_calls.push(...ollamaTools(message.tool_calls));
    if (root.done) {
      result.finish_reason = String(root.done_reason ?? "stop");
      result.usage = ollamaUsage(root);
    }
    result.raw = root;
  }
  return result;
}

function mergeTools(target: ProviderToolCall[], value: unknown): void {
  for (const item of arr(value)) {
    const call = rec(item);
    const fn = rec(call.function);
    const index = Number(call.index ?? target.length);
    target[index] ??= { id: "", name: "", arguments: "" };
    target[index].id += typeof call.id === "string" ? call.id : "";
    target[index].name += typeof fn.name === "string" ? fn.name : "";
    target[index].arguments += typeof fn.arguments === "string" ? fn.arguments : "";
  }
}

function openAITools(value: unknown): ProviderToolCall[] {
  return arr(value).map((item, index) => {
    const call = rec(item);
    const fn = rec(call.function);
    return {
      id: String(call.id ?? `call_${index}`),
      name: String(fn.name ?? ""),
      arguments: args(fn.arguments),
    };
  });
}

function ollamaTools(value: unknown): ProviderToolCall[] {
  return arr(value).map((item, index) => {
    const call = rec(item);
    const fn = rec(call.function);
    return {
      id: String(call.id ?? `call_${index}`),
      name: String(fn.name ?? ""),
      arguments: args(fn.arguments),
    };
  });
}

function openAIUsage(value: unknown): ProviderUsage {
  const item = rec(value);
  return usage(item.prompt_tokens, item.completion_tokens, item.total_tokens);
}
function ollamaUsage(value: unknown): ProviderUsage {
  const item = rec(value);
  return usage(item.prompt_eval_count, item.eval_count);
}
function usage(input: unknown, output: unknown, total?: unknown): ProviderUsage {
  const inputTokens = num(input);
  const outputTokens = num(output);
  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: total == null ? inputTokens + outputTokens : num(total),
  };
}

async function httpError(response: Response, requestId?: string): Promise<ModelProviderError> {
  const body = await response.text();
  const code: ProviderErrorCode =
    [401, 403].includes(response.status)
      ? "authentication_error"
      : response.status === 429
        ? "rate_limit"
        : response.status >= 500
          ? "provider_unavailable"
          : "invalid_request";
  return new ModelProviderError(
    code,
    body || `HTTP ${response.status}`,
    code === "rate_limit" || code === "provider_unavailable",
    response.status,
    requestId,
  );
}

async function* lines(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const split = buffer.split(/\r?\n/);
    buffer = split.pop() ?? "";
    for (const line of split) yield line;
    if (done) break;
  }
  if (buffer) yield buffer;
}

function empty(provider: ModelProvider, model: string, request_id?: string): ProviderResult {
  return {
    provider,
    model,
    text: "",
    tool_calls: [],
    usage: usage(0, 0),
    finish_reason: null,
    request_id,
    raw: null,
  };
}
function normalizeParts(input: string | ProviderInputPart[]): ProviderInputPart[] {
  return typeof input === "string" ? [{ type: "text", text: input }] : input;
}
function sourceOf(part: ProviderInputPart): string {
  return part.data ?? part.url ?? part.path ?? part.source ?? "";
}
function compact(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}
function rec(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
function arr(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function nullable(value: unknown): string | null { return value == null ? null : String(value); }
function text(value: unknown): string {
  return typeof value === "string"
    ? value
    : arr(value).map((item) => typeof item === "string" ? item : String(rec(item).text ?? "")).join("");
}
function args(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value ?? {});
}
function num(value: unknown): number {
  const result = Number(value ?? 0);
  return Number.isFinite(result) ? result : 0;
}
function json(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new ModelProviderError("invalid_stream", "invalid streamed JSON", false);
  }
}
function normalizeError(error: unknown): ModelProviderError {
  if (error instanceof ModelProviderError) return error;
  if (error instanceof Error && error.name === "AbortError") {
    return new ModelProviderError("timeout", "provider request timed out", true);
  }
  return new ModelProviderError(
    "network_error",
    error instanceof Error ? error.message : "provider network failure",
    true,
  );
}
function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
function redact(value: string): string {
  return value
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, "[redacted]")
    .replace(/((?:api[_-]?key|token|secret)\s*[:=]\s*)\S+/gi, "$1[redacted]")
    .replace(/https?:\/\/[^\s?#]+\?[^\s]+/gi, "[redacted-url]");
}

async function digest(value: string | Uint8Array): Promise<string> {
  const source = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const bytes = Uint8Array.from(source);
  const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((item) => item.toString(16).padStart(2, "0")).join("");
}
