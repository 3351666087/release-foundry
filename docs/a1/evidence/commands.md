# A1 Round 1 Command Evidence

Commands:

- `python -B -m pytest tests/a1 -q -p no:cacheprovider`
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`

Observed runner result on the 2026-07-03 follow-up pass:

- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `9 passed in 0.07s`.
- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: `13 passed in 1.01s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `27 passed in 1.15s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `ran 30 agent cases: 30 passed, 0 failed, 0 errors, 0 timeouts, trace 100.00%`.
- `python -B examples\agents\mock_agent.py --write-fixtures examples\agents\fixtures`: wrote `echo_success.json`, `tool_math_success.json`, `recoverable_error.json`.
- `python -B -c "..."` local evidence summary: `total_cases=30`, `passed=30`, `failed=0`, `errored=0`, `timed_out=0`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_vm_stream=30`.
- Explicit cache cleanup after test/import side effects removed only `C:\Users\33516\Documents\Ashr\packages\sdk\ashr_clone\__pycache__` and `C:\Users\33516\Documents\Ashr\services\runner\__pycache__` after verifying both paths were inside the workspace.

Cleanup note:

- Use `python -B` and `pytest -p no:cacheprovider` for fresh setup checks to avoid bytecode/cache files.
- Do not use recursive PowerShell cleanup with `-Include '*.pyc'` in this workspace; it behaved unexpectedly during recovery. If cleanup is needed, delete only explicit, already-listed cache paths.

## 2026-07-03 Round 3 Evidence

- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `33 passed in 1.46s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `ran 30 agent cases: 30 passed, 0 failed, 0 errors, 0 timeouts, trace 100.00%`.
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`: rewrote `echo_success.json`, `tool_math_success.json`, `recoverable_error.json`.
- Evidence summary: `total_cases=30`, `passed=30`, `failed=0`, `errored=0`, `timed_out=0`, `trace_completeness=1.0`, `max_workers=4`, `agent_output.schema_version=ashr.clone.agent_turn.v1`.

## 2026-07-03 Round 4 Evidence Hygiene

- `git fetch origin`: success.
- `git status -sb`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; clean before docs-only hygiene edit.
- `gh pr view 1 --json number,title,state,isDraft,headRefName,baseRefName,url,mergeable,statusCheckRollup`: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks.
- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: `17 passed in 1.59s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `37 passed in 1.72s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `ran 30 agent cases: 30 passed, 0 failed, 0 errors, 0 timeouts, trace 100.00%`.
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`: rewrote `echo_success.json`, `tool_math_success.json`, `recoverable_error.json`.
- Evidence summary: `total_cases=30`, `passed=30`, `failed=0`, `errored=0`, `timed_out=0`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_observation_level_vm_stream=30`, `agent_output.schema_version=ashr.clone.agent_turn.v1`, `local_only=True`, `ashr_api_used=False`.
- Reviewer P2 remediation: negative default `timeout_seconds` / CLI `--timeout` values are rejected before execution; negative per-case timeouts become schema-safe A3 error cases with zero latency/duration instead of negative timing fields. Tests cover CLI rejection, case-level handling, and an emitted mixed RunResult schema guard.
- Cache cleanup removed only explicit `*.pyc` files and empty `__pycache__` directories inside `C:\Users\33516\Documents\Ashr` after workspace path verification.
- Final status before staging showed only self-made A1 docs/evidence modifications.

## 2026-07-03 Round 5 Completion Audit

- `git fetch origin`: success.
- `git status -sb --untracked-files=all`: clean at start, branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`.
- `gh pr view 1 --json number,title,state,isDraft,headRefName,baseRefName,url,mergeable,statusCheckRollup,headRefOid`: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `3617fd2`.
- Peer impact: `origin/dev/a2-scenario-judge` adds `docs/a2/a1_a3_handoff.md`; A2 expects local judge runs with `tool_calls` plus `final_response`. A1 added `to_a2_judge_run(...)` as an A1-owned projection helper instead of changing A2 judge semantics or Gate contracts.
- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `14 passed in 0.09s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `39 passed in 1.48s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.audit.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `ran 30 agent cases: 30 passed, 0 failed, 0 errors, 0 timeouts, trace 100.00%`.
- Temporary audit output summary: `total_cases=30`, `passed=30`, `failed=0`, `errored=0`, `timed_out=0`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_observation_level_vm_stream=30`, `agent_output.schema_version=ashr.clone.agent_turn.v1`, `local_only=True`, `ashr_api_used=False`.
- Temporary `docs/a1/evidence/local_run_30.audit.json` and test-created `__pycache__` files/directories were removed by explicit workspace-verified paths after extracting the summary.
