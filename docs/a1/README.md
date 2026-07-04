# A1 Local SDK/Runner

Local-only SDK/Runner/Adapter/Trace loop. It wraps external agents, runs 30-80 case batches, records observations and VM stream metadata, and emits JSON fixtures for A2/A3 without Ashr API calls or real keys.

Fresh setup:

Prerequisite: run from the repository root with Python 3.12+ and `pytest` available in the environment.

```powershell
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure
python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures
```

Current follow-up verification: `39 passed`, 30/30 local agent cases passed, trace completeness 1.0, and three A3 fixtures generated.

Schema snapshots for A3/Gate review live in `docs/a1/schemas/`. They describe local-only `RunResult`, `CaseResult`, `Observation`, `GradeResult`, `AgentTurn`, run fixture, trace event, and VM stream frame shapes.

A2 local judge handoff: `ashr_clone.to_a2_judge_run(agent_output)` projects A1 `AgentTurn` / `agent_output` data into the current local A2 shape with `final_response`, `tool_calls[].tool`, and `tool_calls[].args`. This is a local compatibility helper, not a Gate contract change.
