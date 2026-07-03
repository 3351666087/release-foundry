# A2 Scenario Schema v0

Kay owns A2 / Scenario & Judge. This contract is the local G1-G2 version used before real Ashr API calibration.

## Core Principle

Each scenario evaluates the behavior required for that specific task. A tool call is not automatically good. Tool use is graded through `toolPolicy`:

- `required`: the tool must be called when the scenario cannot be solved reliably without it.
- `optional`: the tool is allowed, but absence is not a failure.
- `forbidden`: the tool must not be called for this scenario.

## Scenario Object

```json
{
  "id": "A2-S001",
  "title": "Concise No-Tool Rewrite",
  "tags": ["no-tool", "instruction-following"],
  "difficulty": "D1",
  "family": "direct_answer",
  "userTask": "Rewrite one sentence warmly.",
  "actions": [
    {
      "index": 1,
      "actor": "user",
      "content": "Rewrite this sentence...",
      "expectedToolCalls": [],
      "expectedResponse": "One warmer sentence",
      "environment": "local"
    }
  ],
  "expectedBehaviors": [
    "Preserve the original meaning",
    "Do not call tools"
  ],
  "toolPolicy": {
    "required": [],
    "optional": [],
    "forbidden": [
      {"tool": "*", "severity": "major"}
    ],
    "order": []
  },
  "rubric": {
    "classes": ["task_completion", "skill_protocol", "argument_fidelity", "safety_permissions", "final_response_quality"]
  },
  "failureSignals": ["unnecessary_tool_call", "output_schema_invalid"],
  "fixtureRefs": []
}
```

## Judge Output

A2 judges emit `GradeResult` objects with a nested `FailureAnalysis`. A1 can produce trace/run data, A2 grades it, and A3 can display scores and failure locations.

See `services/judge/schemas.py` for the executable local shape.
