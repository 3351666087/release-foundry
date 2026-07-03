# A1/A3 Handoff Contract

This page describes the current local G1-G2 handoff around Kay's A2 module.

## A1 -> A2 Run Input

A1 should produce a run object with normalized tool calls and a final response:

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

Required fields:

- `tool_calls`: ordered list of tool calls. Use `tool` and `args`.
- `final_response`: assistant's final text.

Optional fields for G2 deterministic checks:

- `expected_keywords`: strings that should appear in the final response.
- `forbidden_keywords`: strings that should not appear in the final response.

## A2 Local Grading

```python
from services.judge.runner import grade_run

result = grade_run("A2-S005", run)
```

`grade_run` currently runs:

1. `ToolPolicyJudge`
2. `OutcomeJudge`

The combined result includes:

- `passed`
- `score`
- `primary_failure_class`
- `judge_results`

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

## Known Boundary

This is a local deterministic handoff. It is intentionally not yet the real Ashr server-side grading result. G3 will calibrate field names and scoring behavior against real Ashr API evidence.
