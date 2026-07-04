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
- 60 G3 full scenarios: `packages/scenarios/a2_g3_full_pack.json`
- 23 golden cases: `fixtures/golden/a2_g2_golden_cases.json`
- 12 failure classes: `docs/a2/failure_taxonomy_v0.md`
- Tool policy judge: `services/judge/tool_policy.py`
- Output contract judge: `services/judge/outcome.py`
- Replay/trace recovery judge: `services/judge/trace_integrity.py`
- Grounding judge: `services/judge/grounding.py`
- Safety boundary judge: `services/judge/safety_boundary.py`
- Local runner: `services/judge/runner.py`
- Coverage report helper: `services/judge/coverage.py`
- A3 aggregate grade fixture: `fixtures/a2/results/a2_g3_grade_results.json`
- G3 coverage audit fixture: `fixtures/a2/results/a2_g3_coverage_report.json`
- 18 executable calibration run fixtures, including G3 tool/workflow cases in `fixtures/a2/runs`

## Local Run Shapes

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

A2 also accepts A1's native local runner shapes directly:

- `agent_output` / `AgentTurn` with `text` and `tool_calls[].name` / `arguments`
- `CaseResult` with `case_id`, `scenario_id`, and nested `agent_output`
- OpenAI-style tool calls with `function.name` / `function.arguments`

`services.judge.runner.grade_run` normalizes those shapes into A2's internal `final_response` plus `tool_calls[].tool` / `args` form before judging.

A2 regrades behavior against its own `scenario_id` and `toolPolicy`; it does not inherit A1's existing `status`, `grade`, or `expected` result. Tool names are exact contract names such as `web.search` and `file.read`, not aliases like `search` or `read`.

A2 can grade it with:

```python
from services.judge.runner import grade_run

result = grade_run("A2-S004", run)
```

The result contains:

- overall `passed`,
- average `score`,
- canonical `primary_failure_class` for A3 clustering,
- 5 per-judge `GradeResult` entries,
- nested `FailureAnalysis` objects for A3 display.

Local debug signals such as `bad_final_response` can appear inside `failure_analysis.failure_classes`, but they should not be used as the top-level `primary_failure_class`.

## G1-G2 Boundary

G1-G2 is deterministic and local. It should not depend on real Ashr API access, LLM judge calls, or live external tools.

G3 can add Ashr server-side grading calibration after the local contract is stable.

## Agent Workflow

Recommended Codex workflow for this track:

1. Main supervisor thread owns the branch, final code edits, tests, commit, and push.
2. Background subAgents can run read-only audits or bounded disjoint patches.
3. A subAgent should not push directly unless the supervisor explicitly gives it an isolated branch and clear ownership.
4. Main supervisor integrates subAgent findings, checks schema drift, runs A2 tests, stages explicit paths, and pushes.

This keeps the work visible enough for review while avoiding four long-running visible design threads for every small iteration.
