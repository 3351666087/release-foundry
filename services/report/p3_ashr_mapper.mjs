import { normalizeScore } from "./report_builder.mjs";

const PASSING_TEXT_STATUSES = new Set(["exact", "similar", "match"]);
const PASSING_TOOL_STATUSES = new Set(["exact", "match"]);
const MEDIA_ACTION_TYPES = new Set(["audio", "file", "image", "video"]);

export function extractAshrRuns(input = {}) {
  if (Array.isArray(input)) {
    return input;
  }
  if (Array.isArray(input.runs)) {
    return input.runs;
  }
  if (Array.isArray(input.list_runs?.runs)) {
    return input.list_runs.runs;
  }
  if (Array.isArray(input.calls?.list_runs?.sample?.runs)) {
    return input.calls.list_runs.sample.runs;
  }
  if (input.sample?.id && input.sample?.result) {
    return [input.sample];
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
        "Derived from Ashr run.result.tests[].action_results[] or run.result.cases[].",
        "Failure classes are normalized for A3 triage and preserve raw action status evidence."
      ],
      grade_results: gradeResults
    }
  };
}

export function mapAshrRunToA3Run(run = {}, index = 0, options = {}) {
  const result = run.result || {};
  const tests = Array.isArray(result.tests) ? result.tests : [];
  const cases = Array.isArray(result.cases) ? result.cases : [];
  const sourceItems = tests.length ? tests : cases;
  const metrics = result.aggregate_metrics || {};
  const runId = textOr(run.id, result.run_id, `ashr_run_${index + 1}`);
  const totalCases = numberOr(metrics.total_tests, result.total_cases, metrics.total, sourceItems.length);
  const passed = numberOr(
    metrics.tests_passed,
    metrics.passed,
    result.passed,
    sourceItems.filter((item) => tests.length ? isPassingTest(item) : isPassingCaseResult(item)).length
  );
  const failed = numberOr(metrics.tests_failed, metrics.failed, result.failed, Math.max(0, totalCases - passed));

  return {
    run_id: runId,
    dataset_id: textOr(run.dataset, result.dataset_id, run.dataset_details?.id, "ashr_dataset_unknown"),
    runner_id: textOr(run.runner, result.runner_id, run.runner_details?.id, "ashr_runner_unknown"),
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
    trace_completeness: traceCompleteness(sourceItems),
    metadata: {
      source: "real_ashr_calibrated",
      source_schema: tests.length ? "ashr_labs.run.result.tests" : "ashr.clone.run_result.cases",
      p3_mapper_version: "0.1.0",
      ashr_created_at: run.created_at || null
    },
    cases: tests.length
      ? tests.map((test, caseIndex) => mapAshrTestToA3Case(test, run, caseIndex))
      : cases.map((caseResult, caseIndex) => mapAshrCaseResultToA3Case(caseResult, run, caseIndex))
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
  const mediaEvidence = mediaEvidenceFromActions(actionResults, test);

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
    media_evidence: mediaEvidence,
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
            match_statuses: actionResults.map((item) => item.match_status).filter(Boolean),
            media_types: mediaEvidence?.media_types || [],
            evidence_item_count: mediaEvidence?.evidence_items?.length || 0
          }
        }
      ]
    }
  };
}

export function mapAshrCaseResultToA3Case(caseItem = {}, run = {}, index = 0) {
  const result = run.result || {};
  const runId = textOr(run.id, result.run_id, `ashr_run_unknown`);
  const caseId = textOr(caseItem.case_id, `${runId}_case_${index + 1}`);
  const grade = caseItem.grade || {};
  const expected = normalizeExpected(caseItem.expected || grade.expected || {});
  const actual = normalizeActual(grade.actual || caseItem.actual || caseItem.agent_output || {});
  const passed = typeof grade.passed === "boolean" ? grade.passed : caseItem.status === "passed";
  const score = normalizeScore(numberOr(grade.score, caseItem.score, passed ? 100 : 0));
  const failure = classifyCaseResultFailure(caseItem, grade, expected, actual, passed);
  const mediaEvidence = mediaEvidenceFromCaseResult(caseItem);
  const observations = Array.isArray(caseItem.observations) ? caseItem.observations : [];
  const traceEvents = Array.isArray(caseItem.trace_events) && caseItem.trace_events.length
    ? caseItem.trace_events
    : traceEventsFromObservations(observations, runId, caseId);

  const caseResult = {
    case_id: caseId,
    scenario_id: textOr(caseItem.scenario_id, grade.scenario_id, caseId),
    title: textOr(caseItem.title, caseId),
    family: textOr(caseItem.family, caseItem.metadata?.dataset_type, "real_ashr_media_run"),
    status: passed ? "passed" : "failed",
    score,
    latency_ms: numberOr(caseItem.latency_ms, grade.metrics?.latency_ms, 0),
    primary_failure_class: failure.primary_failure_class,
    severity: caseItem.severity || (passed ? "none" : score < 50 ? "critical" : "major"),
    failure_summary: failure.summary,
    expected,
    actual,
    media_evidence: mediaEvidence,
    observations,
    trace_events: traceEvents,
    metadata: {
      ...(caseItem.metadata || {}),
      source: "real_ashr_case_result",
      raw_status: caseItem.status || null
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
          judge_mode: "p3_ashr_case_result_judge",
          passed,
          score,
          max_score: 100,
          failure_analysis: {
            schema_version: "a2.failure_analysis.v1",
            primary_failure_class: failure.primary_failure_class,
            failure_classes: failure.primary_failure_class === "none" ? [] : [failure.primary_failure_class],
            severity: caseResult.severity,
            blame_stage: failure.blame_stage,
            summary: failure.summary,
            details: failure.details,
            remediation: failure.remediation,
            safety_blocking: false
          },
          evidence: {
            grade_metrics: grade.metrics || {},
            media_types: mediaEvidence?.media_types || [],
            evidence_item_count: mediaEvidence?.evidence_items?.length || 0,
            vm_stream_count: mediaEvidence?.vm_streams?.length || 0
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
      .flatMap((action) => (action.tool_calls || []).map((call) => call.expected).filter(Boolean))
      .concat(actionResults.flatMap((action) => action.expected_response?.tool_calls || [])),
    final_response_points: actionResults
      .filter((action) => action.actor === "agent" && action.expected_response)
      .map((action) => action.expected_response?.text || action.expected_response)
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
      match_status: action.match_status || null,
      action_tags: action.action_tags || null,
      output_path: action.output_path || null,
      semantic_similarity: action.semantic_similarity ?? null,
      divergence_notes: action.divergence_notes || null
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
    } else if (MEDIA_ACTION_TYPES.has(action.action_type)) {
      events.push(traceEvent(
        events.length,
        runId,
        caseId,
        "media",
        action.action_type,
        action.actor || "system",
        actionStatus(action),
        {
          text: observationContent(action),
          action_type: action.action_type,
          action_tags: action.action_tags || null,
          output_path: action.output_path || null,
          match_status: action.match_status || null
        }
      ));
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

function traceEventsFromObservations(observations, runId, caseId) {
  return observations.map((observation, index) => {
    const hasVmStream = Boolean(observation.vm_stream);
    return traceEvent(
      index,
      runId,
      caseId,
      hasVmStream ? "media" : "dialogue",
      hasVmStream ? "vm_stream" : observation.event_type || "message",
      observation.role || "system",
      observation.status || "unknown",
      {
        text: observation.content || observation.event_type || "",
        tool_calls: observation.tool_calls || [],
        vm_stream: hasVmStream ? summarizeVmStream(observation.vm_stream) : null
      }
    );
  });
}

function normalizeExpected(value = {}) {
  return {
    summary: value.summary || value.text || "Expected fields extracted from real Ashr case grade.",
    tool_calls: Array.isArray(value.tool_calls) ? value.tool_calls : [],
    final_response_points: Array.isArray(value.final_response_points)
      ? value.final_response_points
      : [value.text].filter(Boolean)
  };
}

function normalizeActual(value = {}) {
  const finalResponse = value.final_response || value.text || "";
  return {
    final_response: finalResponse,
    tool_calls: Array.isArray(value.tool_calls) ? value.tool_calls : [],
    responses: [finalResponse].filter(Boolean)
  };
}

function classifyCaseResultFailure(caseItem, grade, expected, actual, passed) {
  if (passed) {
    return {
      primary_failure_class: "none",
      blame_stage: "reasoning",
      summary: caseItem.failure_summary || grade.reason || "Real Ashr case grade passed.",
      details: [],
      remediation: []
    };
  }

  const metrics = grade.metrics || {};
  const hasExpectedTool = Array.isArray(expected.tool_calls) && expected.tool_calls.length > 0;
  const hasActualTool = Array.isArray(actual.tool_calls) && actual.tool_calls.length > 0;
  if (metrics.tool_match === false && hasExpectedTool && !hasActualTool) {
    return {
      primary_failure_class: "missing_required_tool",
      blame_stage: "tool_use",
      summary: grade.reason || "Expected tool call was not present in the actual response.",
      details: ["grade.metrics.tool_match=false", "expected.tool_calls present", "actual.tool_calls empty"],
      remediation: ["Compare expected tool calls and actual tool calls in A3 case detail."]
    };
  }

  if (metrics.tool_match === false) {
    return {
      primary_failure_class: "wrong_arguments",
      blame_stage: "tool_use",
      summary: grade.reason || "Tool call comparison failed.",
      details: ["grade.metrics.tool_match=false"],
      remediation: ["Inspect tool-call name and argument differences."]
    };
  }

  if (metrics.text_match === false) {
    return {
      primary_failure_class: "bad_final_response",
      blame_stage: "final_response",
      summary: grade.reason || "Final response text did not match the expected response.",
      details: ["grade.metrics.text_match=false"],
      remediation: ["Compare expected response points and actual final response."]
    };
  }

  return {
    primary_failure_class: caseItem.primary_failure_class || "unknown_failure",
    blame_stage: "reasoning",
    summary: caseItem.failure_summary || grade.reason || "Real Ashr case failed without a mapped failure class.",
    details: [],
    remediation: ["Inspect raw grade metrics and media evidence."]
  };
}

function mediaEvidenceFromActions(actionResults, test = {}) {
  const mediaActions = actionResults.filter((action) => (
    MEDIA_ACTION_TYPES.has(action.action_type)
    || action.output_path
    || hasMeaningful(action.action_tags)
    || action.vm_stream
  ));
  const vmStreams = actionResults.map((action) => action.vm_stream).filter(Boolean).map(summarizeVmStream);
  const mediaTypes = unique(mediaActions.map((action) => action.action_type).filter((type) => MEDIA_ACTION_TYPES.has(type)));
  const evidenceItems = mediaActions.map((action) => ({
    type: action.action_type || "unknown",
    actor: action.actor || null,
    name: action.name || null,
    output_path: action.output_path || null,
    action_tags: action.action_tags || null,
    match_status: action.match_status || null
  }));

  if (!mediaTypes.length && !evidenceItems.length && !vmStreams.length) {
    return null;
  }

  return {
    schema_version: "a3.media_evidence.v1",
    source: "ashr_action_results",
    primary_media_type: mediaTypes[0] || "unknown",
    media_types: mediaTypes,
    evidence_items: evidenceItems,
    action_tags: mediaActions.map((action) => action.action_tags).filter(hasMeaningful),
    output_paths: mediaActions.map((action) => action.output_path).filter(Boolean),
    audio_tags: normalizeTagList(test.audio_tags || test.metadata?.audio_tags),
    intent_tags: normalizeTagList(test.intent_tags || test.metadata?.intent_tags),
    vm_streams: vmStreams,
    known_gaps: mediaTypes.length && !mediaActions.some((action) => action.output_path)
      ? ["No output_path or signed media URL was present in this sanitized run sample."]
      : []
  };
}

function mediaEvidenceFromCaseResult(caseItem = {}) {
  const metadata = caseItem.metadata || {};
  const observations = Array.isArray(caseItem.observations) ? caseItem.observations : [];
  const actionType = metadata.action_type;
  const hasMediaType = MEDIA_ACTION_TYPES.has(actionType);
  const vmStreams = observations.map((item) => item.vm_stream).filter(Boolean).map(summarizeVmStream);
  const evidenceItems = [];

  if (hasMediaType || metadata.output_path || hasMeaningful(metadata.action_tags)) {
    evidenceItems.push({
      type: actionType || "unknown",
      actor: metadata.actor || null,
      name: metadata.action_name || null,
      action_index: metadata.action_index ?? null,
      output_path: metadata.output_path || null,
      action_tags: metadata.action_tags || null
    });
  }
  for (const stream of vmStreams) {
    evidenceItems.push({
      type: "vm_stream",
      provider: stream.provider,
      session_id: stream.session_id,
      log_count: stream.log_count
    });
  }

  const mediaTypes = unique([
    hasMediaType ? actionType : null,
    ...evidenceItems.map((item) => item.type).filter((type) => MEDIA_ACTION_TYPES.has(type))
  ].filter(Boolean));

  if (!mediaTypes.length && !evidenceItems.length && !vmStreams.length) {
    return null;
  }

  const knownGaps = [];
  if (mediaTypes.length && !metadata.output_path) {
    knownGaps.push("Sanitized sample did not include a downloadable media URL for this case.");
  }
  if (!vmStreams.length) {
    knownGaps.push("No VM stream was attached to this case.");
  }

  return {
    schema_version: "a3.media_evidence.v1",
    source: "ashr_result_cases",
    primary_media_type: mediaTypes[0] || "vm_stream",
    media_types: mediaTypes,
    evidence_items: evidenceItems,
    action_tags: normalizeTagList(metadata.action_tags),
    output_paths: [metadata.output_path].filter(Boolean),
    audio_tags: normalizeTagList(metadata.audio_tags),
    intent_tags: normalizeTagList(metadata.intent_tags),
    vm_streams: vmStreams,
    known_gaps: knownGaps
  };
}

function summarizeVmStream(stream = {}) {
  const logs = Array.isArray(stream.logs) ? stream.logs : [];
  return {
    provider: stream.provider || null,
    session_id: stream.session_id || null,
    duration_ms: numberOr(stream.duration_ms, 0),
    log_count: logs.length,
    log_types: unique(logs.map((log) => log.type).filter(Boolean)),
    synthetic: Boolean(stream.metadata?.synthetic)
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

function isPassingCaseResult(caseItem = {}) {
  if (typeof caseItem.grade?.passed === "boolean") {
    return caseItem.grade.passed;
  }
  return caseItem.status === "passed";
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
  return tests.filter((test) => (
    (Array.isArray(test.action_results) && test.action_results.length > 0)
    || (Array.isArray(test.observations) && test.observations.length > 0)
    || (Array.isArray(test.trace_events) && test.trace_events.length > 0)
  )).length / tests.length;
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

function unique(values) {
  return [...new Set(values)];
}

function normalizeTagList(value) {
  if (!hasMeaningful(value)) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function hasMeaningful(value) {
  if (value === undefined || value === null || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.values(value).some(hasMeaningful);
  }
  return true;
}
