import { CloudApiService, DEFAULT_QUEUE_LEASE_SECONDS, NotFoundError, ValidationError, redactText } from "./index.js";
import { DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, normalizeMaxWorkers, normalizeTimeoutSeconds, runAgentBatch } from "./runner.js";
import type { AgentLike } from "./runner.js";
import type { JsonRecord, RunRecord } from "./index.js";

export const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);
const MIN_HEARTBEAT_INTERVAL_SECONDS = 0.05;

export interface QueueRunRequest {
  tenantId: string;
  projectId: string;
  datasetId: string;
  agent: AgentLike;
  runnerId?: string;
  runId?: string;
  maxWorkers?: number | null;
  timeoutSeconds?: number | null;
  leaseOwnerId?: string | null;
  leaseSeconds?: number | null;
  metadata?: JsonRecord;
}

export interface ReplayIncompleteRunsOptions {
  agent: AgentLike;
  datasetId?: string;
  statuses?: string[];
  maxRuns?: number;
  maxWorkers?: number | null;
  timeoutSeconds?: number | null;
  leaseOwnerId?: string | null;
  leaseSeconds?: number | null;
  metadata?: JsonRecord;
}

export class CloudQueueWorker {
  readonly service: CloudApiService;
  readonly queueWorkers: number;
  private readonly workerId: string;
  private readonly futures = new Map<string, Promise<RunRecord>>();
  private activeRuns = 0;
  private readonly pendingRuns: Array<{
    request: QueueRunRequest;
    resolve: (run: RunRecord) => void;
    reject: (error: unknown) => void;
  }> = [];

  constructor(service: CloudApiService = new CloudApiService(), options: { queueWorkers?: number | null } = {}) {
    this.service = service;
    this.queueWorkers = normalizeMaxWorkers(options.queueWorkers ?? DEFAULT_MAX_WORKERS);
    this.workerId = `worker-${randomId()}`;
  }

  enqueueAgentRun(request: QueueRunRequest): RunRecord {
    const runnerWorkers = normalizeMaxWorkers(request.maxWorkers ?? DEFAULT_MAX_WORKERS);
    const queued = this.service.createQueuedRun(request.tenantId, request.projectId, {
      datasetId: request.datasetId,
      runnerId: request.runnerId ?? "a1-ts-cloud-queue-worker",
      runId: request.runId,
      metadata: this.executionMetadata(request, runnerWorkers),
    });
    const normalized = {
      ...request,
      runId: queued.run_id,
      runnerId: queued.runner_id,
      maxWorkers: runnerWorkers,
      timeoutSeconds: normalizeTimeoutSeconds(request.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS),
      leaseOwnerId: request.leaseOwnerId ?? this.leaseOwnerId(queued.run_id),
      leaseSeconds: request.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : request.leaseSeconds,
    };
    this.trackFuture(queued.run_id, this.schedule(normalized));
    return queued;
  }

  pollRun(tenantId: string, projectId: string, runId: string): ReturnType<CloudApiService["pollRun"]> {
    return this.service.pollRun(tenantId, projectId, runId);
  }

  replayIncompleteRuns(tenantId: string, projectId: string, options: ReplayIncompleteRunsOptions): RunRecord[] {
    const statuses = new Set((options.statuses ?? ["queued", "running"]).map((status) => String(status)));
    if (statuses.size === 0) {
      throw new ValidationError("replay statuses must not be empty");
    }
    for (const status of statuses) {
      if (!["queued", "running"].includes(status)) {
        throw new ValidationError(`unsupported replay status: ${status}`);
      }
    }
    const maxRuns = normalizeReplayLimit(options.maxRuns ?? 100);
    const runnerWorkers = normalizeMaxWorkers(options.maxWorkers ?? DEFAULT_MAX_WORKERS);
    const timeoutSeconds = normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS);
    const leaseSeconds = options.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : options.leaseSeconds;
    this.service.reclaimExpiredRunLeases(tenantId, projectId, { datasetId: options.datasetId, statuses: Array.from(statuses) });
    const candidates = this.service
      .listRuns(tenantId, projectId, { datasetId: options.datasetId })
      .sort(replayOrderCompare);
    const replayed: RunRecord[] = [];
    for (const run of candidates) {
      if (replayed.length >= maxRuns) {
        break;
      }
      if (!statuses.has(run.status)) {
        continue;
      }
      if (run.lease_owner_id !== undefined && run.lease_owner_id !== null) {
        continue;
      }
      const current = this.futures.get(run.run_id);
      if (current !== undefined) {
        continue;
      }
      const request: QueueRunRequest = {
        tenantId: run.tenant_id,
        projectId: run.project_id,
        datasetId: run.dataset_id,
        agent: options.agent,
        runnerId: run.runner_id,
        runId: run.run_id,
        maxWorkers: runnerWorkers,
        timeoutSeconds,
        leaseOwnerId: this.leaseOwnerId(run.run_id),
        leaseSeconds,
        metadata: { source: "packages/ts/ashr-clone/cloud-queue-replay", ...(options.metadata ?? {}) },
      };
      this.trackFuture(run.run_id, this.schedule(request));
      replayed.push(run);
    }
    return replayed;
  }

  async waitForRun(
    tenantId: string,
    projectId: string,
    runId: string,
    options: { timeoutSeconds?: number | null; requireTerminal?: boolean } = {},
  ): Promise<ReturnType<CloudApiService["pollRun"]>> {
    const poll = this.service.pollRun(tenantId, projectId, runId);
    if (TERMINAL_RUN_STATUSES.has(poll.status)) {
      return poll;
    }
    const future = this.futures.get(runId);
    if (!future) {
      throw new NotFoundError("queued run future not found");
    }
    const timeoutSeconds = normalizeTimeoutSeconds(options.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS, "timeoutSeconds");
    if (timeoutSeconds === null) {
      await future;
    } else {
      await withTimeout(future, timeoutSeconds, runId, Boolean(options.requireTerminal));
    }
    const finalPoll = this.service.pollRun(tenantId, projectId, runId);
    if (options.requireTerminal && !TERMINAL_RUN_STATUSES.has(finalPoll.status)) {
      throw new Error(`queued run ${runId} did not reach a terminal status; current status=${finalPoll.status}`);
    }
    return finalPoll;
  }

  cancelRun(tenantId: string, projectId: string, runId: string, options: { reason?: string } = {}): RunRecord {
    return this.service.cancelRun(tenantId, projectId, runId, { reason: options.reason ?? "cancelled" });
  }

  private async execute(request: QueueRunRequest): Promise<RunRecord> {
    const runId = String(request.runId);
    const leaseOwnerId = request.leaseOwnerId ?? this.leaseOwnerId(runId);
    const leaseSeconds = request.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : request.leaseSeconds;
    try {
      const running = this.service.markRunRunning(request.tenantId, request.projectId, runId, {
        leaseOwnerId,
        leaseSeconds,
        reclaimExpired: true,
      });
      if (running.status === "cancelled") {
        return running;
      }
      const dataset = this.service.getDataset(request.tenantId, request.projectId, request.datasetId);
      this.service.heartbeatRun(request.tenantId, request.projectId, runId, { leaseOwnerId, leaseSeconds });
      this.mergeExecutionMetadata(request, leaseOwnerId);
      const result = await this.withLeaseRenewal(request, leaseOwnerId, () => runAgentBatch(request.agent, dataset.cases, {
        datasetId: dataset.dataset_id,
        runnerId: request.runnerId ?? "a1-ts-cloud-queue-worker",
        runId,
        maxWorkers: request.maxWorkers ?? DEFAULT_MAX_WORKERS,
        timeoutSeconds: request.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS,
        metadata: { local_only: true, ashr_api_used: false, queued: true },
      }));
      return this.service.completeRun(request.tenantId, request.projectId, runId, result, { leaseOwnerId });
    } catch (error) {
      return this.failOrPollAfterWorkerError(request, leaseOwnerId, error);
    }
  }

  private async withLeaseRenewal<T>(request: QueueRunRequest, leaseOwnerId: string, operation: () => Promise<T>): Promise<T> {
    if (request.leaseSeconds === null) {
      return operation();
    }
    const leaseSeconds = request.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : request.leaseSeconds;
    const interval = setInterval(() => {
      try {
        this.service.heartbeatRun(request.tenantId, request.projectId, String(request.runId), { leaseOwnerId, leaseSeconds });
      } catch {
        clearInterval(interval);
      }
    }, heartbeatIntervalMs(leaseSeconds));
    try {
      return await operation();
    } finally {
      clearInterval(interval);
    }
  }

  private failOrPollAfterWorkerError(request: QueueRunRequest, leaseOwnerId: string, error: unknown): RunRecord {
    try {
      return this.service.failRun(request.tenantId, request.projectId, String(request.runId), {
        leaseOwnerId,
        error: {
          type: error instanceof Error ? error.name : "QueueRunError",
          message: redactText(error instanceof Error ? error.message : String(error)),
        },
      });
    } catch (failError) {
      if (failError instanceof ValidationError) {
        return this.service.pollRun(request.tenantId, request.projectId, String(request.runId)).run;
      }
      throw failError;
    }
  }

  private schedule(request: QueueRunRequest): Promise<RunRecord> {
    return new Promise<RunRecord>((resolve, reject) => {
      this.pendingRuns.push({ request, resolve, reject });
      this.drainQueue();
    });
  }

  private trackFuture(runId: string, future: Promise<RunRecord>): void {
    this.futures.set(runId, future);
    void future.finally(() => {
      if (this.futures.get(runId) === future) {
        this.futures.delete(runId);
      }
    });
  }

  private drainQueue(): void {
    while (this.activeRuns < this.queueWorkers) {
      const next = this.pendingRuns.shift();
      if (!next) {
        return;
      }
      this.activeRuns += 1;
      void this.execute(next.request)
        .then(next.resolve, next.reject)
        .finally(() => {
          this.activeRuns -= 1;
          this.drainQueue();
        });
    }
  }

  private leaseOwnerId(runId: string): string {
    return `${this.workerId}:${runId}`;
  }

  private executionMetadata(request: QueueRunRequest, runnerWorkers: number): JsonRecord {
    return {
      source: "packages/ts/ashr-clone/cloud-queue",
      queue_workers: this.queueWorkers,
      runner_max_workers: runnerWorkers,
      lease_owner_id: request.leaseOwnerId ?? null,
      lease_seconds: request.leaseSeconds === undefined ? DEFAULT_QUEUE_LEASE_SECONDS : request.leaseSeconds,
      ...(request.metadata ?? {}),
    };
  }

  private mergeExecutionMetadata(request: QueueRunRequest, leaseOwnerId: string): void {
    const run = this.service.store.runs[String(request.runId)];
    if (!run) {
      return;
    }
    run.metadata = {
      ...(run.metadata ?? {}),
      ...this.executionMetadata({ ...request, leaseOwnerId }, normalizeMaxWorkers(request.maxWorkers ?? DEFAULT_MAX_WORKERS)),
    };
  }
}

function replayOrderCompare(left: RunRecord, right: RunRecord): number {
  const leftKey = replayOrderKey(left);
  const rightKey = replayOrderKey(right);
  for (let index = 0; index < leftKey.length; index += 1) {
    if (leftKey[index] < rightKey[index]) {
      return -1;
    }
    if (leftKey[index] > rightKey[index]) {
      return 1;
    }
  }
  return 0;
}

function replayOrderKey(run: RunRecord): [number, number, string, string] {
  const metadata = run.metadata ?? {};
  const orderValue = metadata.replay_order ?? metadata.batch_index;
  const order = Number(orderValue);
  const hasOrder = orderValue === undefined || !Number.isFinite(order) ? 1 : 0;
  return [hasOrder, Number.isFinite(order) ? Math.trunc(order) : 0, run.created_at, run.run_id];
}

function normalizeReplayLimit(maxRuns: number): number {
  const value = Math.trunc(Number(maxRuns));
  if (!Number.isFinite(value) || value < 1) {
    throw new ValidationError("maxRuns must be positive");
  }
  return value;
}

async function withTimeout<T>(promise: Promise<T>, timeoutSeconds: number, _runId: string, _requireTerminal: boolean): Promise<T | undefined> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<undefined>((resolve) => {
        timeout = setTimeout(() => {
          resolve(undefined);
        }, Math.max(0, timeoutSeconds * 1000));
      }),
    ]);
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

function heartbeatIntervalMs(leaseSeconds: number): number {
  const seconds = Number(leaseSeconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new ValidationError("leaseSeconds must be positive");
  }
  return Math.max(MIN_HEARTBEAT_INTERVAL_SECONDS * 1000, Math.min((seconds * 1000) / 3, 5000));
}

function randomId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
