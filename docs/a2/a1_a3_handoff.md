# A1/A3 Handoff Contract

This page describes the current local G1-G2 handoff around Kay's A2 module.

## A1 -> A2 Run Input

A1 can produce a normalized A2 run object with tool calls and a final response:

```json
{
  "tool_calls": [
    {
      "id": "call-1",
      "tool": "file.read",
      "args": {"path": "fixtures/a2/notes/launch-review.md"}
    }
  ],
  "final_response": "Three grounded bullets...",
  "expected_keywords": [],
  "forbidden_keywords": []
}
```

Required fields for the normalized A2 shape:

- `tool_calls`: ordered list of tool calls. Use `tool` and `args`.
- `final_response`: assistant's final text.

Optional fields for G2 deterministic checks:

- `expected_keywords`: strings that should appear in the final response.
- `forbidden_keywords`: strings that should not appear in the final response.

## A1 Native Shapes

A2 now also accepts A1 local runner output directly. This lets A1 call A2 without pre-projecting every run by hand.

Accepted native A1 inputs:

1. `AgentTurn` / `agent_output`

```json
{
  "schema_version": "ashr.clone.agent_turn.v1",
  "text": "The grounded answer...",
  "tool_calls": [
    {
      "name": "file.read",
      "arguments": {"path": "fixtures/a2/notes/launch-review.md"},
      "call_id": "call-1"
    }
  ],
  "status": "ok",
  "latency_ms": 0,
  "metadata": {}
}
```

2. `CaseResult`

```json
{
  "case_id": "math-00",
  "scenario_id": "A2-S005",
  "status": "passed",
  "agent_output": {
    "schema_version": "ashr.clone.agent_turn.v1",
    "text": "The grounded answer...",
    "tool_calls": [{"name": "file.read", "arguments": {"path": "fixtures/a2/notes/launch-review.md"}}],
    "status": "ok",
    "latency_ms": 0,
    "metadata": {}
  }
}
```

`grade_run` normalizes A1 `text` into A2 `final_response`, and A1 `tool_calls[].name` / `arguments` into A2 `tool_calls[].tool` / `args`. It also accepts OpenAI-style `function.name` / `function.arguments` tool calls.

Boundary: A2 regrades the behavior against the `scenario_id` passed to `grade_run`; it does not inherit A1's `status`, `grade`, or `expected` fields. Tool names remain exact A2 contract names such as `web.search`, `web.open`, and `file.read`; alias mapping can be added later if A1/A3 agree on a shared tool registry.

## A2 Local Grading

```python
from services.judge.runner import grade_run

result = grade_run("A2-S005", run)
```

`grade_run` currently runs:

1. `ToolPolicyJudge`
2. `OutcomeJudge`
3. `TraceIntegrityJudge`
4. `GroundingJudge`
5. `SafetyBoundaryJudge`

The combined result includes:

- `passed`
- `score`
- canonical `primary_failure_class`
- `judge_results`

`primary_failure_class` is reserved for the 12 canonical A2 failure classes or `none`, so A3 failure clusters stay stable. Local debug signals can remain inside nested `failure_analysis.failure_classes`; A3 normalizes legacy local signals before clustering.

## A2 -> A3 Display Output

A3 can display:

- run pass/fail status,
- overall score,
- primary failure class,
- per-judge score,
- nested `failure_analysis.summary`,
- `evidence.tool_call_ids`,
- `evidence.final_response_excerpt`.

Sample outputs:

- `fixtures/a2/results/a2_s001_pass_grade.json`
- `fixtures/a2/results/a2_s004_missing_tool_grade.json`
- `fixtures/a2/results/a2_s010_wrong_arguments_grade.json`

For dashboard/report consumption, A2 also provides an aggregate wrapper:

- `fixtures/a2/results/a2_g3_grade_results.json`
- `fixtures/a2/results/a2_g3_coverage_report.json`

The aggregate wrapper uses:

- `schema_version`: `a2.grade_results.v1`
- `grade_results[]`: list of normal `grade_run` outputs
- `total_cases`, `passed`, `failed`
- `scenario_pack`, `dataset_id`, `report_id`

A2 aggregate scores use a 0-100 scale with `max_score: 100` on per-judge results. A3 also normalizes A1 nested `case.grade.score` values on the 0-1 scale when no A2 aggregate grade is joined.

The coverage wrapper uses `schema_version: a2.coverage_report.v1` and lets A3 display scenario/rubric/judge coverage, golden case coverage, executable failure calibration coverage, assignment minimum checks, and thin-calibration warnings without rerunning A2 code.

A3 can also use `golden_failure_class_cases` and `executable_failure_class_cases` as drilldown evidence for each canonical failure class. The Markdown report surfaces the same evidence in a compact `Failure Class Evidence` section for manual review.

## Known Boundary

This is a local deterministic handoff. It is intentionally not yet the real Ashr server-side grading result. G3 will calibrate field names and scoring behavior against real Ashr API evidence.

## Recommended Codex Workflow

Use the current thread as the main supervisor/integrator. Use background subAgents for narrow audits or disjoint implementation slices, then let the supervisor review, test, commit, and push. Visible threads are useful for long design discussions, but routine A1/A2/A3 compatibility passes can use hidden subAgents so the work stays fast and the Git history stays controlled.
