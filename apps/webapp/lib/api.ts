export type JsonRecord = Record<string, unknown>;

export type DashboardSummary = {
  totalRuns: number;
  totalCases: number;
  passed: number;
  failed: number;
  passRate: number;
  avgScore: number;
  traceCompleteness: number;
  mediaEvidenceCases: number;
  lastRunId: string;
};

export type NormalizedRun = {
  runId: string;
  datasetId: string;
  status: string;
  totalCases: number;
  passed: number;
  failed: number;
  durationMs: number;
  traceCompleteness: number;
  startedAt: string;
};

export type NormalizedCase = {
  caseId: string;
  runId: string;
  scenarioId: string;
  title: string;
  family: string;
  status: string;
  passed: boolean;
  score: number;
  severity: string;
  failureClass: string;
  failureSummary: string;
  expected: JsonRecord;
  actual: JsonRecord;
  observations: JsonRecord[];
  traceEvents: JsonRecord[];
  toolCalls: JsonRecord[];
  judgeResults: JsonRecord[];
};

export type AggregateScopeStatus = {
  status: "complete" | "partial";
  strictScopeEnforced: boolean;
  excludedRecordCount: number;
  excludedCounts: JsonRecord;
  reason: string;
  retry: string;
};

export type TrustedReleaseAuthority = {
  integrityVerified: boolean;
  releaseReady: boolean;
  status: "release_ready" | "blocked" | "review_required" | "integrity_invalid" | "not_ready" | "unknown";
  upstreamDecision: "allow" | "block" | "review" | "unknown";
  reasonCode: string;
  blockers: string[];
  ledgerHeadHash: string;
  recordId: string;
};

export type DashboardModel = {
  raw: JsonRecord;
  source: string;
  sourceLabel: string;
  summary: DashboardSummary;
  aggregateScopeStatus: AggregateScopeStatus;
  trustedReleaseAuthority: TrustedReleaseAuthority;
  runs: NormalizedRun[];
  cases: NormalizedCase[];
};

export type DashboardErrorKind =
  | "unauthenticated"
  | "denied"
  | "not_found"
  | "server"
  | "network"
  | "invalid_response"
  | "request_failed";

const dashboardErrorMessages: Record<DashboardErrorKind, string> = {
  unauthenticated: "Dashboard authentication is required.",
  denied: "Dashboard access is denied.",
  not_found: "Dashboard data was not found.",
  server: "Dashboard service is temporarily unavailable.",
  network: "Dashboard service could not be reached.",
  invalid_response: "Dashboard service returned an invalid response.",
  request_failed: "Dashboard request failed."
};

export class DashboardApiError extends Error {
  readonly kind: DashboardErrorKind;
  readonly status: number | null;
  readonly retryable: boolean;

  constructor(kind: DashboardErrorKind, status: number | null = null) {
    super(dashboardErrorMessages[kind]);
    this.name = "DashboardApiError";
    this.kind = kind;
    this.status = status;
    this.retryable = kind === "network" || kind === "server" || kind === "invalid_response";
  }
}

export async function fetchDashboard(source: string, signal?: AbortSignal): Promise<DashboardModel> {
  const url = new URL("/api/a3/dashboard", window.location.origin);
  url.searchParams.set("source", source);
  let response: Response;

  try {
    // Hosted identity comes only from same-origin cookies, never a browser-asserted x-a3-role, actor, or tenant.
    response = await fetch(url, {
      credentials: "include",
      signal
    });
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new DashboardApiError("network");
  }

  if (!response.ok) throw dashboardHttpError(response.status);

  try {
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new DashboardApiError("invalid_response", response.status);
    }
    return normalizeDashboard(payload as JsonRecord);
  } catch (reason) {
    if (reason instanceof DashboardApiError) throw reason;
    throw new DashboardApiError("invalid_response", response.status);
  }
}

export function toDashboardError(reason: unknown): DashboardApiError {
  return reason instanceof DashboardApiError
    ? reason
    : new DashboardApiError("request_failed");
}

export function isAbortError(reason: unknown): boolean {
  return Boolean(reason && typeof reason === "object" && "name" in reason && reason.name === "AbortError");
}

function dashboardHttpError(status: number): DashboardApiError {
  if (status === 401) return new DashboardApiError("unauthenticated", status);
  if (status === 403) return new DashboardApiError("denied", status);
  if (status === 404) return new DashboardApiError("not_found", status);
  if (status >= 500) return new DashboardApiError("server", status);
  return new DashboardApiError("request_failed", status);
}

export function normalizeDashboard(payload: JsonRecord): DashboardModel {
  const summary = record(payload.summary);
  const aggregateScopeStatus = record(payload.aggregate_scope_status);
  const trustedReleaseAuthority = record(payload.trusted_release_authority);
  const trustedLedger = record(trustedReleaseAuthority.decision_ledger);
  const runFixture = record(payload.run_fixture);
  const gradeFixture = record(payload.grade_fixture);
  const gradeResults = array(gradeFixture.grade_results).map(record);
  const gradeByCase = new Map(gradeResults.map((grade) => [string(grade.case_id), grade]));
  const nestedRunResult = record(runFixture.run_result);
  const runs = array(runFixture.runs).length
    ? array(runFixture.runs).map(record)
    : array(runFixture.cases).length
      ? [runFixture]
      : array(nestedRunResult.cases).length
        ? [nestedRunResult]
        : [];

  const normalizedRuns = runs.map<NormalizedRun>((run) => ({
    runId: string(run.run_id, "run-unknown"),
    datasetId: string(run.dataset_id, "dataset-unknown"),
    status: string(run.status),
    totalCases: number(run.total_cases),
    passed: number(run.passed),
    failed: number(run.failed),
    durationMs: number(run.duration_ms),
    traceCompleteness: number(run.trace_completeness),
    startedAt: string(run.started_at)
  }));

  const cases = runs.flatMap((run) => array(run.cases).map(record).map<NormalizedCase>((item) => {
    const caseId = string(item.case_id, "case-unknown");
    const grade = gradeByCase.get(caseId) || {};
    const explicitActual = record(item.actual);
    const agentOutput = record(item.agent_output);
    const actual = Object.keys(explicitActual).length ? explicitActual : agentOutput;
    const observations = array(item.observations).map(record);
    const traceEvents = array(item.trace_events).map(record);
    const toolCalls = [
      ...array(actual.tool_calls).map(record),
      ...observations.flatMap((observation) => array(observation.tool_calls).map(record))
    ];
    const judgeResults = array(grade.judge_results).map(record);
    const failureAnalyses = judgeResults.map((judge) => record(judge.failure_analysis));
    const failureSummary = failureAnalyses.find((analysis) => string(analysis.summary, ""))?.summary;
    const status = string(item.status, boolean(grade.passed) ? "passed" : "failed");

    return {
      caseId,
      runId: string(run.run_id, "run-unknown"),
      scenarioId: string(item.scenario_id),
      title: string(item.title, string(item.scenario_id, caseId)),
      family: string(item.family, "general"),
      status,
      passed: typeof grade.passed === "boolean" ? grade.passed : status === "passed",
      score: number(grade.score, number(item.score)),
      severity: string(item.severity, string(failureAnalyses[0]?.severity, "none")),
      failureClass: string(grade.primary_failure_class, string(item.primary_failure_class, "none")),
      failureSummary: string(item.failure_summary, string(failureSummary, "No failure summary.")),
      expected: record(item.expected),
      actual,
      observations,
      traceEvents,
      toolCalls,
      judgeResults
    };
  }));
  const reportedAggregateStatus = string(aggregateScopeStatus.status, "unknown");
  const authorityIntegrityVerified = boolean(trustedReleaseAuthority.integrity_verified);
  const authorityStatus = trustedAuthorityStatus(trustedReleaseAuthority.status);
  const authorityDecision = authorityIntegrityVerified
    ? trustedAuthorityDecision(trustedReleaseAuthority.upstream_decision)
    : "unknown";

  const source = string(payload.source, "api-mock");
  return {
    raw: payload,
    source,
    sourceLabel: customerSourceLabel(source, string(payload.source_label, "API evidence projection")),
    aggregateScopeStatus: {
      status: reportedAggregateStatus === "complete" ? "complete" : "partial",
      strictScopeEnforced: boolean(aggregateScopeStatus.strict_scope_enforced),
      excludedRecordCount: number(aggregateScopeStatus.excluded_record_count),
      excludedCounts: record(aggregateScopeStatus.excluded_counts),
      reason: string(
        aggregateScopeStatus.reason,
        "Scoped aggregate status is missing or unrecognized, so this response is treated as partial."
      ),
      retry: string(
        aggregateScopeStatus.retry,
        "Re-import records with organization, tenant, workspace, project, and environment scope; refresh only after import succeeds."
      )
    },
    trustedReleaseAuthority: {
      integrityVerified: authorityIntegrityVerified,
      releaseReady: authorityIntegrityVerified
        && authorityStatus === "release_ready"
        && authorityDecision === "allow"
        && boolean(trustedReleaseAuthority.release_ready),
      status: authorityIntegrityVerified ? authorityStatus : "integrity_invalid",
      upstreamDecision: authorityDecision,
      reasonCode: string(trustedReleaseAuthority.reason_code, "trusted_authority_missing"),
      blockers: array(trustedReleaseAuthority.blockers).map((item) => string(item)).filter(Boolean),
      ledgerHeadHash: string(trustedLedger.head_hash, "unavailable"),
      recordId: string(trustedLedger.record_id, "unavailable")
    },
    summary: {
      totalRuns: number(summary.totalRuns, normalizedRuns.length),
      totalCases: number(summary.totalCases, cases.length),
      passed: number(summary.passed, cases.filter((item) => item.passed).length),
      failed: number(summary.failed, cases.filter((item) => !item.passed).length),
      passRate: number(summary.passRate),
      avgScore: number(summary.avgScore),
      traceCompleteness: number(summary.traceCompleteness),
      mediaEvidenceCases: number(summary.mediaEvidenceCases),
      lastRunId: string(summary.lastRunId, normalizedRuns[0]?.runId || "none")
    },
    runs: normalizedRuns,
    cases
  };
}

function customerSourceLabel(source: string, sourceLabel: string): string {
  const labels: Record<string, string> = {
    "api-mock": "API 聚合证据",
    "p3-media": "多模态分歧校准",
    "p3-a2-round50": "三方模型复核 · Round 50",
    "p3-a2-round51": "重复稳定性 · Round 51",
    "p3-official-demo": "官方校准样本",
    "raw-a1": "执行证据原始样本",
    "raw-a2": "评测结论原始样本",
    "a3-golden-path-rc2": "发布候选 rc.2",
    "a3-golden-path": "发布候选 rc.1"
  };
  if (labels[source]) return labels[source];
  return /\bA[123](?:\/A[123])*\b/.test(sourceLabel) ? "发布证据数据源" : sourceLabel;
}

function trustedAuthorityStatus(value: unknown): TrustedReleaseAuthority["status"] {
  const normalized = string(value, "unknown");
  return ["release_ready", "blocked", "review_required", "integrity_invalid", "not_ready"].includes(normalized)
    ? normalized as TrustedReleaseAuthority["status"]
    : "unknown";
}

function trustedAuthorityDecision(value: unknown): TrustedReleaseAuthority["upstreamDecision"] {
  const normalized = string(value, "unknown");
  return ["allow", "block", "review"].includes(normalized)
    ? normalized as TrustedReleaseAuthority["upstreamDecision"]
    : "unknown";
}

export function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

export function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function string(value: unknown, fallback = "unknown"): string {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

export function number(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function boolean(value: unknown): boolean {
  return value === true;
}

export function pretty(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}
