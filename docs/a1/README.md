# A1 Local SDK/Runner

Local SDK/Runner/Adapter/Trace loop. The G2 baseline wraps external agents, runs 30-80 case batches, records observations and VM stream metadata, and emits JSON fixtures for A2/A3. Subscription-era A1 calibration now adds a quota-safe Ashr API probe wrapper without committing keys or private responses.

Fresh setup:

Prerequisite: run from the repository root with Python 3.12+ and `pytest` available in the environment.

```powershell
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure
python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures
```

Current follow-up verification: `51 passed`, 30/30 local agent cases passed, trace completeness 1.0, three A3 fixtures generated, and real read-only API probes for `init`, `list-datasets`, `list-runs`, `list-requests`, and negative `get-dataset` recorded under private evidence.

Schema snapshots for A3/Gate review live in `docs/a1/schemas/`. They describe local-only `RunResult`, `CaseResult`, `Observation`, `GradeResult`, `AgentTurn`, run fixture, trace event, and VM stream frame shapes.

A2 local judge handoff: `ashr_clone.to_a2_judge_run(agent_output)` projects A1 `AgentTurn` / `agent_output` data into the current local A2 shape with `final_response`, `tool_calls[].tool`, and `tool_calls[].args`. This is a local compatibility helper, not a Gate contract change.

Subscription calibration quickstart:

```powershell
# Dry-run plan, no API key required.
python -B -m services.runner.api_probe init --output docs/evidence/private_refs/a1_api_init_dry_run.json

# Real read-only probe. Load ASHR_API_KEY or ASHR_LABS_API_KEY in the current process first.
python -B -m services.runner.api_probe init --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_init_real.json

# Mutating probes need both --execute and --allow-mutate after reviewing the dry-run plan.
python -B -m services.runner.api_probe create-run --execute --allow-mutate --dataset-id <id> --result-file <run-result.json>

# Safe generation dry-run config for later review.
python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration" --request-file docs/a1/api_calibration/tiny_generation_request.json
```

Non-sensitive API calibration notes live in `docs/a1/api_calibration/`. Raw records and screenshots stay in ignored `docs/evidence/private_refs/`.
