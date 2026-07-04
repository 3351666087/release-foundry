import { normalizeScore } from "./report_builder.mjs";

const PASSING_TEXT_STATUSES = new Set(["exact", "similar", "match"]);
const PASSING_TOOL_STATUSES = new Set(["exact", "match"]);

export function extractAshrRuns(input = {}) {
  if (Array.isArray(input)) {
    return input;
  }
  if (Array.isArray(input.runs)) {
    return input.runs;
  }
  if (Array.isArray(input.calls?.list_runs?.sample?.runs)) {
    return input.calls.list_runs.sample.runs;
  }
  if (input.id && input.result) {
    return [input];
  }
  return [];
}

export function mapAshrSampleToA3Fixtures(input = {}, options = {}) {
  const runs = extractAshrRuns(input);
  const mappedRuns = runs.map((run, index) => mapAshrRunToA3Run(run, index, options));
  const gradeResults = mappedRuns.flatMap((run) => run.cases.map((item) => item.grade_result));

  return {
    runFixture: {
      schema_version: "a3.dashboard_fixture.v1",
      fixture_id: options.fixtureId || "p3_ashr_calibrated_sample",
      source_notes: [
        "P3 mapper output from sanitized real Ashr run shape.",
        "Does not contain real API keys or account identifiers."
      ],
      runs: mappedRuns.map(({ cases, ...run }) => ({
        ...run,
        cases: cases.map(({ grade_result, ...caseResult }) => caseResult)
      }))
    },
    gradeFixture: {
      schema_version: "a3.grade_fixture.v1",
      fixture_id: options.gradeFixtureId || "p3_ashr_calibrated_grades",
      source_notes: [
        "Derived from Ashr run.result.tests[].action_results[].",
        "Failure classes are normalized for A3 triage and preserve raw action status evidence."
      ],
      grade_results: gradeResults
    }
  };
}

export function mapAshrRunToA3Run(run = {}, index = 0, options = {}) {
  const result = run.result || {};
  const tests = Array.isArray(result.tests) ? result.tests : [];
  const metrics = result.aggregate_metrics || {};
  const runId = textOr(run.id, `ashr_run_${index + 1}`);
  const totalCases = numberOr(metrics.total_tests, tests.length);
  const passed = numberOr(metrics.tests_passed, tests.filter(isPassingTest).length);
  const failed = numberOr(metrics.tests_failed, Math.max(0, totalCases - passed));

  return {
    run_id: runId,
    dataset_id: textOr(run.dataset, run.dataset_details?.id, "ashr_dataset_unknown"),
    runner_id: textOr(run.runner, run.runner_details?.id, "ashr_runner_unknown"),
    status: failed > 0 ? "failed" : result.status === "completed" ? "passed" : textOr(result.status, "unknown"),
    total_cases: totalCases,
    passed,
    failed,
    errored: 0,
    timed_out: 0,
    started_at: textOr(result.started_at, run.created_at, ""),
    ended_at: textOr(result.completed_at, result.ended_at, ""),
    duration_ms: durationMs(result.started_at, result.completed_at),
    max_workers: numberOr(options.maxWorkers, 1),
    trace_completeness: traceCompleteness(tests),
    metadata: {
      source: "real_ashr_calibrated",
      source_schema: "ashr_labs.run.result",
      p3_mapper_version: "0.1.0",
      ashr_created_at: run.created_at || null
    },
    cases: tests.map((test, caseIndex) => mapAshrTestToA3Case(test, run, caseIndex))
  };
}

export function mapAshrTestToA3Case(test = {}, run = {}, index = 0) {
  const runId = textOr(run.id, `ashr_run_unknown`);
  const caseId = textOr(test.test_id, `${runId}_case_${index + 1}`);
  const actionResults = Array.isArray(test.action_results) ? test.action_results : [];
  const failure = classifyFailure(actionResults, test);
  const passed = failure.primary_failure_class === "none";
  const score = caseScore(actionResults, passed);
  const expected = expectedFromActions(actionResults);
  const actual = actualFromActions(actionResults);

  const caseResult = {
    case_id: caseId,
    scenario_id: caseId,
    title: textOr(test.title, caseId),
    family: "real_ashr_run",
    status: passed ? "passed" : "failed",
    score,
    latency_ms: durationMs(test.started_at, test.completed_at),
    primary_failure_class: failure.primary_failure_class,
    severity: passed ? "none" : "major",
    failure_summary: failure.summary,
    expected,
    actual,
    observations: observationsFromActions(actionResults, runId, caseId),
    trace_events: traceEventsFromActions(actionResults, runId, caseId),
    metadata: {
      source: "real_ashr_test",
      raw_status: test.status || null,
      coherence: test.coherence || null
    }
  };

  return {
    ...caseResult,
    grade_result: {
      schema_version: "a3.p3_ashr_grade_result.v1",
      scenario_id: caseResult.scenario_id,
      case_id: caseResult.case_id,
      passed,
      score,
      primary_failure_class: failure.primary_failure_class,
      judge_results: [
        {
          judge_mode: "p3_ashr_action_results_judge",
          passed,
          score,
          max_score: 100,
          failure_analysis: {
            schema_version: "a2.failure_analysis.v1",
            primary_failure_class: failure.primary_failure_class,
            failure_classes: failure.primary_failure_class === "none" ? [] : [failure.primary_failure_class],
            severity: passed ? "none" : "major",
            blame_stage: failure.blame_stage,
            summary: failure.summary,
            details: failure.details,
            remediation: failure.remediation,
            safety_blocking: false
          },
          evidence: {
            action_indexes: failure.action_indexes,
            match_statuses: actionResults.map((item) => item.match_status).filter(Boolean)
          }
        }
      ]
    }
  };
}

function expectedFromActions(actionResults) {
  return {
    summary: "Expected fields extracted from real Ashr action_results.",
    tool_calls: actionResults
      .filter((action) => action.action_type === "tool_call")
      .flatMap((action) => (action.tool_calls || []).map((call) => call.expected).filter(Boolean)),
    final_response_points: actionResults
      .filter((action) => action.actor === "agent" && action.expected_response)
      .map((action) => action.expected_response)
  };
}

function actualFromActions(actionResults) {
  const finalResponses = actionResults
    .filter((action) => action.actor === "agent" && action.actual_response)
    .map((action) => action.actual_response?.text || action.actual_response);

  return {
    final_response: finalResponses.at(-1) || "",
    tool_calls: actionResults
      .filter((action) => action.action_type === "tool_call")
      .flatMap((action) => (action.tool_calls || []).map((call) => call.actual).filter(Boolean)),
    responses: finalResponses
  };
}

function observationsFromActions(actionResults, runId, caseId) {
  return actionResults.map((action, index) => ({
    observation_id: `${caseId}_obs_${index}`,
    run_id: runId,
    case_id: caseId,
    turn_index: numberOr(action.action_index, index),
    event_type: action.action_type || "unknown",
    role: action.actor || "system",
    content: observationContent(action),
    tool_calls: action.tool_calls || [],
    started_at: "",
    ended_at: "",
    latency_ms: 0,
    status: actionStatus(action),
    metadata: {
      match_status: action.match_status || null
    }
  }));
}

function traceEventsFromActions(actionResults, runId, caseId) {
  const events = [];
  for (const action of actionResults) {
    if (action.action_type === "tool_call") {
      for (const call of action.tool_calls || []) {
        events.push(traceEvent(events.length, runId, caseId, "tool", "tool_call", "tool", actionStatus(action), {
          name: call.actual?.tool_name || call.actual?.name || call.expected?.tool_name || call.expected?.name || "tool",
          args: call.actual?.arguments || {},
          expected: call.expected || null,
          actual: call.actual || null,
          match_status: call.match_status || action.match_status || null
        }));
      }
    } else {
      events.push(traceEvent(
        events.length,
        runId,
        caseId,
        "dialogue",
        "message",
        action.actor || "system",
        actionStatus(action),
        { text: observationContent(action), match_status: action.match_status || null }
      ));
    }
  }
  return events;
}

function traceEvent(seq, runId, caseId, phase, kind, channel, status, data) {
  return {
    schema: "ashr.clone.trace.v1",
    type: "trace_event",
    event_type: `${phase}.${kind}`,
    run_id: runId,
    event_id: `${caseId}_evt_${seq}`,
    seq,
    timestamp: "",
    phase,
    source: "ashr_p3_mapper",
    parent_id: null,
    tags: [phase, kind],
    observation: {
      kind,
      channel,
      status,
      text: data.text || data.name || kind,
      data
    },
    metadata: {
      p3_mapper_version: "0.1.0"
    }
  };
}

function classifyFailure(actionResults, test) {
  const toolFailure = firstToolFailure(actionResults);
  if (toolFailure) {
    return toolFailure;
  }

  const textFailure = actionResults.find((action) => (
    action.actor === "agent"
    && action.action_type === "text"
    && action.match_status
    && !PASSING_TEXT_STATUSES.has(action.match_status)
  ));
  if (textFailure) {
    return {
      primary_failure_class: "bad_final_response",
      blame_stage: "final_response",
      summary: textFailure.divergence_notes || `Agent response match status was ${textFailure.match_status}.`,
      details: [`action_index=${textFailure.action_index ?? "unknown"}`],
      remediation: ["Compare expected_response and actual_response in the A3 case detail."],
      action_indexes: [textFailure.action_index].filter((item) => item !== undefined)
    };
  }

  if (test.status && !["completed", "passed"].includes(test.status)) {
    return {
      primary_failure_class: "run_error",
      blame_stage: "execution",
      summary: `Ashr test status was ${test.status}.`,
      details: [],
      remediation: ["Inspect raw Ashr test status and action results."],
      action_indexes: []
    };
  }

  return {
    primary_failure_class: "none",
    blame_stage: "reasoning",
    summary: "Real Ashr action results passed or had no failure signal.",
    details: [],
    remediation: [],
    action_indexes: []
  };
}

function firstToolFailure(actionResults) {
  for (const action of actionResults.filter((item) => item.action_type === "tool_call")) {
    for (const call of action.tool_calls || []) {
      const status = call.match_status || action.match_status || call.argument_comparison?.status;
      if (!status || PASSING_TOOL_STATUSES.has(status)) {
        continue;
      }
      const expected = call.expected || {};
      const actual = call.actual || {};
      const primary = !actual.tool_name && !actual.name
        ? "missing_required_tool"
        : !expected.tool_name && !expected.name
          ? "unexpected_tool_call"
          : "wrong_arguments";
      return {
        primary_failure_class: primary,
        blame_stage: "tool_use",
        summary: call.divergence_notes || action.divergence_notes || `Tool call match status was ${status}.`,
        details: [`action_index=${action.action_index ?? "unknown"}`, `match_status=${status}`],
        remediation: ["Compare expected and actual tool calls in the A3 expected-vs-actual panel."],
        action_indexes: [action.action_index].filter((item) => item !== undefined)
      };
    }
  }
  return null;
}

function isPassingTest(test = {}) {
  return classifyFailure(test.action_results || [], test).primary_failure_class === "none";
}

function caseScore(actionResults, passed) {
  const similarities = actionResults
    .map((action) => action.semantic_similarity)
    .filter((value) => typeof value === "number" && !Number.isNaN(value));
  if (similarities.length) {
    return normalizeScore(similarities.reduce((sum, value) => sum + value, 0) / similarities.length);
  }
  return passed ? 100 : 0;
}

function traceCompleteness(tests) {
  if (!tests.length) {
    return 0;
  }
  return tests.filter((test) => Array.isArray(test.action_results) && test.action_results.length > 0).length / tests.length;
}

function actionStatus(action) {
  if (!action.match_status) {
    return "ok";
  }
  return PASSING_TEXT_STATUSES.has(action.match_status) || PASSING_TOOL_STATUSES.has(action.match_status) ? "ok" : "error";
}

function observationContent(action) {
  if (action.text) {
    return action.text;
  }
  if (action.actual_response?.text) {
    return action.actual_response.text;
  }
  if (action.expected_response?.text) {
    return action.expected_response.text;
  }
  if (action.tool_calls) {
    return action.tool_calls;
  }
  return "";
}
function durationMs(startedAt, endedAt) {
  if (!startedAt || !endedAt) {
    return 0;
  }
  const started = Date.parse(startedAt);
  const ended = Date.parse(endedAt);
  if (Number.isNaN(started) || Number.isNaN(ended)) {
    return 0;
  }
  return Math.max(0, ended - started);
}

function numberOr(...values) {
  for (const value of values) {
    if (typeof value === "number" && !Number.isNaN(value)) {
      return value;
    }
  }
  return 0;
}

function textOr(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return String(value);
    }
  }
  return "";
}
