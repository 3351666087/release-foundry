# A1 Local SDK/Runner

Local SDK/Runner/Adapter/Trace loop. The G2 baseline wraps external agents, runs 30-80 case batches, records observations and VM stream metadata, and emits JSON fixtures for A2/A3. Subscription-era A1 calibration now adds a quota-safe Ashr API probe wrapper and a real `dataset_source.runs` adapter without committing keys or private responses.

Fresh setup:

Prerequisite: run from the repository root with Python 3.12+ and `pytest` available in the environment.

```powershell
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure
python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures
```

Current follow-up verification: `102 passed`, 30/30 local agent cases passed, trace completeness 1.0, three A3 fixtures generated, real read-only API probes for `init`, `health-check`, `list-datasets`, `list-runs`, `list-requests`, `list-agents`, `get-run`, `poll-run`, and negative `get-dataset` recorded under private evidence. One quota-safe real `create-run` probe succeeded against an existing private dataset after dry-run review; raw records remain private. A private real dataset source smoke test converted 3 cases and preserved runner trace completeness at 100%. `create-request` now sends a permissive default `request_input_schema` when omitted, matching the official SDK docs and the observed API requirement; for Image/Audio/Files accepted inputs, that default schema also advertises the local `AgentInput` `parts` envelope and reports part types that match accepted inputs. A text-only real `create-request -> get-request -> poll-request` chain completed successfully. A real Image/Audio/Files interface request was accepted but ended in hosted `request_status=failed`; read-only recheck found failure detail under a nested `_failure` object and the SDK now records only its safe field shape. A follow-up text batch probe hit the hosted request usage boundary. The CLI and direct SDK block unsafe mutating retries before real execution.

Schema snapshots for A3/Gate review live in `docs/a1/schemas/`. They describe local-only `RunResult`, `CaseResult`, `Observation`, `GradeResult`, `AgentInput`, `AgentTurn`, run fixture, trace event, and VM stream frame shapes.

Agent adapter multimodal input: `ashr_clone.AgentInput` wraps text plus `parts` for `text`, `image`, `audio`, and `file` inputs under `schema_version: ashr.clone.agent_input.v1`. Existing `AgentAdapter.respond("text")` behavior stays text-first and passes a plain string to legacy agents. New `respond_input(...)`, `arespond_input(...)`, `run_input_turn(...)`, and `arun_input_turn(...)` pass the canonical envelope as the agent argument for future Image/Audio/Files interface work.

A2 local judge handoff: `ashr_clone.to_a2_judge_run(agent_output)` projects A1 `AgentTurn` / `agent_output` data into the current local A2 shape with `final_response`, `tool_calls[].tool`, and `tool_calls[].args`. This is a local compatibility helper, not a Gate contract change.

Subscription calibration quickstart:

```powershell
# Dry-run plan, no API key required.
python -B -m services.runner.api_probe init --output docs/evidence/private_refs/a1_api_init_dry_run.json

# Real read-only probe. Load ASHR_API_KEY or ASHR_LABS_API_KEY in the current process first.
python -B -m services.runner.api_probe init --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_init_real.json

# Real read-only SDK parity probes.
python -B -m services.runner.api_probe health-check --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_health_check_real.json
python -B -m services.runner.api_probe list-agents --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_list_agents_real.json

# Mutating probes need --execute, --allow-mutate, and --max-retries 0 after reviewing the dry-run plan.
python -B -m services.runner.api_probe create-run --execute --allow-mutate --max-retries 0 --dataset-id <id> --result-file <run-result.json>

# Safe generation dry-run config for later review. The record includes a preflight summary.
python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration" --request-file docs/a1/api_calibration/tiny_generation_request.json

# Dry-run-first media interface coverage for Image/Audio/Files. Real execution requires explicit allowance flags.
python -B -m services.runner.api_probe create-request --request-name "A1 Media Interface Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json
```

Mutating `create-run --execute` and `create-request --execute` require `--allow-mutate` and `--max-retries 0` to avoid duplicate mutation on retry. Real `create-request` execution requires a known positive integer `num_variations` value no larger than `--max-request-variations` and text-only accepted inputs by default. Media generation requires `--allow-media-generation`; non-text accepted inputs require `--allow-non-text-inputs`. Current hosted request quota can block additional generation even when the local preflight passes. The media dry-run record should show `ashr.clone.agent_input.v1`, `parts`, and text/image/audio/file part types before any future media execution is considered.

Non-sensitive API calibration notes live in `docs/a1/api_calibration/`. Raw records and screenshots stay in ignored `docs/evidence/private_refs/`.

Dataset source adapter quickstart:

```powershell
python -B -m services.runner.dataset_adapter --input docs/evidence/private_refs/a1_api_get_dataset_first_real.json --output docs/evidence/private_refs/a1_real_dataset_cases.json --max-cases 10
python -B -m services.runner.cli --input docs/evidence/private_refs/a1_real_dataset_cases.json --output docs/evidence/private_refs/a1_real_dataset_run_mock.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id ashr-real-dataset-private --runner-id a1-real-dataset-adapter --max-workers 4 --timeout 5
```

Public SDK helpers for this path are `cases_from_dataset_source(...)`, `case_from_source_run(...)`, and `replay_fixture_from_source_run(...)`.
