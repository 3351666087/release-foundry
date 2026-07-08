import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BUILDER_VERSION = "0.1.0";

export function buildScenarioIndex(scenarioPack = {}) {
  const scenarios = Array.isArray(scenarioPack.scenarios) ? scenarioPack.scenarios : [];
  return new Map(scenarios.map((scenario) => [scenario.id, scenario]));
}

export function buildA3FixturesFromA2({ scenarioPack = {}, gradeFixture = {}, runFixtures = [] } = {}, options = {}) {
  const scenarioIndex = buildScenarioIndex(scenarioPack);
  const runByCase = new Map(runFixtures.map((item) => [item.case_id, item]));
  const gradeResults = Array.isArray(gradeFixture.grade_results) ? gradeFixture.grade_results : [];
  const cases = gradeResults.map((grade, index) => (
    buildA3CaseFromA2({
      grade,
      runFixture: runByCase.get(grade.case_id),
      scenario: scenarioIndex.get(grade.scenario_id),
      index
    })
  ));
  const passed = cases.filter((item) => item.status === "passed").length;
  const failed = cases.length - passed;
  const runId = options.runId || "run_a3_generated_from_a2_g3";

  return {
    runFixture: {
      schema_version: "a3.dashboard_fixture.v1",
      fixture_id: options.fixtureId || "a3_generated_from_merged_a2_outputs",
      source_notes: [
        {
          source: "Merged A2 scenario pack",
          paths: ["packages/scenarios/a2_g3_full_pack.json"]
        },
        {
          source: "Merged A2 aggregate grade results",
          paths: ["fixtures/a2/results/a2_g3_grade_results.json"]
        },
        {
          source: "Merged A2 executable run fixtures",
          paths: ["fixtures/a2/runs/*.json"]
        },
        {
          source: "A3 fixture builder",
          paths: ["services/report/a3_fixture_builder.mjs"]
        }
      ],
      runs: [
        {
          run_id: runId,
          dataset_id: gradeFixture.dataset_id || "a2-g3-calibration",
          runner_id: options.runnerId || "a1-local-runner",
          status: failed > 0 ? "failed" : "passed",
          total_cases: cases.length,
          passed,
          failed,
          errored: 0,
          timed_out: 0,
          started_at: "",
          ended_at: "",
          duration_ms: 0,
          max_workers: 1,
          trace_completeness: cases.length ? 1 : 0,
          metadata: {
            local_only: true,
            ashr_api_used: false,
            source: "merged_a2_outputs",
            builder_version: BUILDER_VERSION,
            scenario_pack: gradeFixture.scenario_pack || scenarioPack.pack_id || "packages/scenarios/a2_g3_full_pack.json",
            source_grade_report_id: gradeFixture.report_id || null
          },
          cases
        }
      ]
    },
    gradeFixture: {
      schema_version: "a3.grade_fixture.v1",
      fixture_id: options.gradeFixtureId || "a3_generated_from_a2_g3_grades",
      source_notes: [
        "Generated from fixtures/a2/results/a2_g3_grade_results.json.",
        "A3 preserves A2 judge_results and only changes the top-level fixture wrapper."
      ],
      grade_results: gradeResults
    }
  };
}

export function buildA3CaseFromA2({ grade = {}, runFixture = {}, scenario = {}, index = 0 } = {}) {
  const caseId = grade.case_id || runFixture.case_id || `a2-generated-case-${index + 1}`;
  const scenarioId = grade.scenario_id || runFixture.scenario_id || scenario.id || caseId;
  const passed = typeof grade.passed === "boolean"
    ? grade.passed
    : runFixture.expected?.passed === true;
  const actualToolCalls = normalizeActualToolCalls(runFixture.run?.tool_calls);
  const finalResponse = textOr(runFixture.run?.final_response, "");
  const primaryFailureClass = grade.primary_failure_class || runFixture.expected?.primary_failure_class || (passed ? "none" : "wrong_intent");
  const expected = buildExpectedFromScenario(scenario, actualToolCalls, primaryFailureClass);
  const failureAnalysis = selectFailureAnalysis(grade, passed);

  return {
    case_id: caseId,
    scenario_id: scenarioId,
    title: scenario.title || caseId,
    family: scenario.family || "a2_g3_calibration",
    status: passed ? "passed" : "failed",
    score: typeof grade.score === "number" ? grade.score : passed ? 100 : 0,
    latency_ms: 0,
    primary_failure_class: primaryFailureClass,
    severity: failureAnalysis?.severity || (passed ? "none" : "major"),
    failure_summary: failureAnalysis?.summary || (passed ? "Passed." : "Failure requires triage."),
    expected,
    actual: {
      final_response: finalResponse,
      tool_calls: actualToolCalls,
      expected_facts: arrayOr(runFixture.run?.expected_facts),
      forbidden_facts: arrayOr(runFixture.run?.forbidden_facts)
    },
    observations: buildObservations(scenario, finalResponse, actualToolCalls),
    trace_events: buildTraceEvents(caseId, scenario, finalResponse, actualToolCalls),
    metadata: {
      source: "merged_a2_outputs",
      a2_primary_rubric: scenario.primaryRubric || null,
      a2_difficulty: scenario.difficulty || null,
      a2_tags: arrayOr(scenario.tags)
    }
  };
}

export async function buildA3FixturesFromA2Paths(paths = {}) {
  const repoRoot = paths.repoRoot || resolve(dirname(fileURLToPath(import.meta.url)), "../..");
  const scenarioPackPath = paths.scenarioPackPath || join(repoRoot, "packages/scenarios/a2_g3_full_pack.json");
  const gradeFixturePath = paths.gradeFixturePath || join(repoRoot, "fixtures/a2/results/a2_g3_grade_results.json");
  const runFixturesDir = paths.runFixturesDir || join(repoRoot, "fixtures/a2/runs");
  const [scenarioPack, gradeFixture, runFixtures] = await Promise.all([
    readJson(scenarioPackPath),
    readJson(gradeFixturePath),
    readRunFixtures(runFixturesDir)
  ]);

  return buildA3FixturesFromA2({ scenarioPack, gradeFixture, runFixtures }, paths.options || {});
}

export async function writeGeneratedA3Fixtures(paths = {}) {
  const repoRoot = paths.repoRoot || resolve(dirname(fileURLToPath(import.meta.url)), "../..");
  const outputRunPath = paths.outputRunPath || join(repoRoot, "fixtures/a3/mock_run_results.json");
  const outputGradePath = paths.outputGradePath || join(repoRoot, "fixtures/a3/mock_grade_results.json");
  const { runFixture, gradeFixture } = await buildA3FixturesFromA2Paths({ ...paths, repoRoot });

  await Promise.all([
    writeJson(outputRunPath, runFixture),
    writeJson(outputGradePath, gradeFixture)
  ]);

  return { outputRunPath, outputGradePath, runFixture, gradeFixture };
}

function buildExpectedFromScenario(scenario = {}, actualToolCalls = [], primaryFailureClass = "none") {
  const actions = Array.isArray(scenario.actions) ? scenario.actions : [];
  const expectedToolCalls = actions.flatMap((action) => (
    Array.isArray(action.expectedToolCalls) ? action.expectedToolCalls : []
  ));
  const requiredToolCalls = expectedToolCalls.length
    ? []
    : arrayOr(scenario.toolPolicy?.required).map((item) => ({
      tool: item.tool,
      min_count: item.min_count,
      severity: item.severity
    }));

  const toolCalls = [...expectedToolCalls, ...requiredToolCalls].map(normalizeExpectedToolCall);

  return {
    summary: scenario.userTask || actions.map((action) => action.expectedResponse).filter(Boolean).join(" "),
    tool_calls: hydrateExpectedArgsForOrderCases(toolCalls, actualToolCalls, primaryFailureClass),
    final_response_points: arrayOr(scenario.expectedBehaviors),
    expected_responses: actions.map((action) => action.expectedResponse).filter(Boolean),
    tool_policy: scenario.toolPolicy || {}
  };
}

function hydrateExpectedArgsForOrderCases(expectedToolCalls = [], actualToolCalls = [], primaryFailureClass = "none") {
  if (primaryFailureClass !== "wrong_tool_order") {
    return expectedToolCalls;
  }

  const actualByName = new Map(actualToolCalls.map((call) => [call.name, call]));
  return expectedToolCalls.map((call) => {
    if (Object.keys(call.args || {}).length > 0) {
      return call;
    }
    const actual = actualByName.get(call.tool);
    return actual
      ? { ...call, args: actual.arguments || {} }
      : call;
  });
}

function normalizeExpectedToolCall(call = {}) {
  return compactObject({
    tool: call.tool || call.tool_name || call.name || "unknown_tool",
    args: call.args || call.arguments || {},
    min_count: call.min_count,
    severity: call.severity
  });
}

function normalizeActualToolCalls(toolCalls = []) {
  return arrayOr(toolCalls).map((call) => ({
    id: call.id || call.tool_call_id || null,
    name: call.name || call.tool || call.tool_name || "unknown_tool",
    arguments: call.args || call.arguments || {},
    output: call.output || null
  }));
}

function buildObservations(scenario = {}, finalResponse = "", toolCalls = []) {
  const userMessages = arrayOr(scenario.actions)
    .filter((action) => action.actor === "user" && action.content)
    .map((action, index) => ({
      turn_index: index,
      event_type: "message",
      role: "user",
      content: action.content,
      status: "ok",
      tool_calls: []
    }));

  return [
    ...userMessages,
    {
      turn_index: userMessages.length,
      event_type: "agent_response",
      role: "assistant",
      content: finalResponse,
      status: "ok",
      tool_calls: toolCalls
    }
  ];
}

function buildTraceEvents(caseId, scenario = {}, finalResponse = "", toolCalls = []) {
  const events = [];
  for (const action of arrayOr(scenario.actions)) {
    if (action.actor !== "user" || !action.content) {
      continue;
    }
    events.push({
      event_id: `${caseId}:trace:${events.length}`,
      seq: events.length,
      phase: "dialogue",
      event_type: "dialogue.message",
      source: "a2-scenario-pack",
      observation: {
        kind: "message",
        channel: "user",
        status: "ok",
        text: action.content
      }
    });
  }

  for (const call of toolCalls) {
    events.push({
      event_id: `${caseId}:trace:${events.length}`,
      seq: events.length,
      phase: "tool",
      event_type: "tool.tool_call",
      source: "a2-run-fixture",
      observation: {
        kind: "tool_call",
        status: "ok",
        data: {
          id: call.id,
          name: call.name,
          arguments: call.arguments,
          output: call.output
        }
      }
    });
  }

  events.push({
    event_id: `${caseId}:trace:${events.length}`,
    seq: events.length,
    phase: "dialogue",
    event_type: "dialogue.message",
    source: "a2-run-fixture",
    observation: {
      kind: "message",
      channel: "assistant",
      status: "ok",
      text: finalResponse
    }
  });

  return events;
}

function selectFailureAnalysis(grade = {}, passed = false) {
  const judgeResults = Array.isArray(grade.judge_results) ? grade.judge_results : [];
  if (passed) {
    return judgeResults
      .map((judge) => judge.failure_analysis)
      .find((analysis) => analysis?.primary_failure_class === "none") || null;
  }

  return judgeResults
    .map((judge) => judge.failure_analysis)
    .find((analysis) => analysis?.primary_failure_class && analysis.primary_failure_class !== "none") || null;
}

async function readRunFixtures(dirPath) {
  const names = (await readdir(dirPath))
    .filter((name) => name.endsWith(".json"))
    .sort();
  return Promise.all(names.map((name) => readJson(join(dirPath, name))));
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function arrayOr(value) {
  return Array.isArray(value) ? value : [];
}

function textOr(...values) {
  return values.find((value) => typeof value === "string" && value.length > 0) || "";
}

function compactObject(value = {}) {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

async function main() {
  if (!process.argv.includes("--write")) {
    console.log("Usage: node services/report/a3_fixture_builder.mjs --write");
    return;
  }

  const { outputRunPath, outputGradePath, runFixture } = await writeGeneratedA3Fixtures();
  console.log(`Wrote ${outputRunPath}`);
  console.log(`Wrote ${outputGradePath}`);
  console.log(`Cases: ${runFixture.runs[0]?.cases.length || 0}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
