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

export type DashboardModel = {
  raw: JsonRecord;
  source: string;
  sourceLabel: string;
  summary: DashboardSummary;
  runs: NormalizedRun[];
  cases: NormalizedCase[];
};

export async function fetchDashboard(source: string, signal?: AbortSignal): Promise<DashboardModel> {
  const url = new URL("/api/a3/dashboard", window.location.origin);
  url.searchParams.set("source", source);
  const response = await fetch(url, {
    signal,
    headers: {
      "x-a3-role": "auditor",
      "x-a3-client": "next-product-console"
    }
  });
  if (!response.ok) throw new Error(`Dashboard API returned ${response.status}`);
  return normalizeDashboard(await response.json() as JsonRecord);
}

export function normalizeDashboard(payload: JsonRecord): DashboardModel {
  const summary = record(payload.summary);
  const runFixture = record(payload.run_fixture);
  const gradeFixture = record(payload.grade_fixture);
  const gradeResults = array(gradeFixture.grade_results).map(record);
  const gradeByCase = new Map(gradeResults.map((grade) => [string(grade.case_id), grade]));
  const runs = array(runFixture.runs).map(record);

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
    const actual = record(item.actual);
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

  return {
    raw: payload,
    source: string(payload.source, "api-mock"),
    sourceLabel: string(payload.source_label, "A1/A2 API-backed evidence"),
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
