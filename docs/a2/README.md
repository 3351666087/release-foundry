# A2 Scenario & Judge

Kay owns A2 for the Ashr reproduction project.

This module provides the local G1-G2 foundation for:

- scenario packs,
- `toolPolicy`,
- deterministic local judges,
- failure taxonomy,
- golden cases,
- sample run fixtures.

## Current Deliverables

- 20 G2 seed scenarios: `packages/scenarios/a2_g2_seed_pack.json`
- 20 golden case seeds: `fixtures/golden/a2_g2_golden_cases.json`
- 12 failure classes: `docs/a2/failure_taxonomy_v0.md`
- Tool policy judge: `services/judge/tool_policy.py`
- Output contract judge: `services/judge/outcome.py`
- Local runner: `services/judge/runner.py`

## Local Run Shape

A1 can hand A2 a run object like this:

```json
{
  "tool_calls": [
    {"id": "call-1", "tool": "web.search", "args": {"query": "Acme MiniDock official price"}}
  ],
  "final_response": "The official Acme MiniDock page lists the price as $79.",
  "expected_keywords": ["$79"],
  "forbidden_keywords": []
}
```

A2 can grade it with:

```python
from services.judge.runner import grade_run

result = grade_run("A2-S004", run)
```

The result contains:

- overall `passed`,
- average `score`,
- `primary_failure_class`,
- per-judge `GradeResult` entries,
- nested `FailureAnalysis` objects for A3 display.

## G1-G2 Boundary

G1-G2 is deterministic and local. It should not depend on real Ashr API access, LLM judge calls, or live external tools.

G3 can add Ashr server-side grading calibration after the local contract is stable.
