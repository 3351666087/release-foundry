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

## 2026-07-04 Subscription API Calibration

- `git fetch origin`: success.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present locally and not staged.
- `git check-ignore -v docs/evidence/private_refs/a1_api_init_real_v2.json .secrets/ashr.env`: `docs/evidence/.gitignore` ignores `private_refs/`; local `.git/info/exclude` ignores `.secrets/`.
- GitHub plugin PR check: PR #1 was already merged into `main`; user asked to continue on original A1 branch, so this round remained on `codex/a1-local-sdk-runner`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `14 passed in 0.62s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `53 passed in 2.17s`.
- Dry-run plans written under ignored private evidence: `init`, `list-datasets`, `list-runs`, `list-requests`, `poll-run`, and `create-request`.
- Real read-only probes, all loaded the key from the current process environment and did not print it: `init`, `list-datasets --limit 1`, `list-runs --limit 2`, `list-requests --limit 2`, and invalid `get-dataset` for error-shape calibration.
- Real probe summary: successful calls returned status `ok`, HTTP `200`, attempts `1`; invalid dataset returned a redacted record with `status=error`, HTTP `200`, and `error_kind=api`.
- Chrome read-only dashboard check: logged-in `Ashr Labs` shell at `https://lab.ashr.io/?tab=analysis`; screenshot stored as ignored private evidence.
- Bus-Auditor must-fix remediation: error strings now redact token-like values, bearer tokens, and email addresses before records or CLI exception text can include them; regression tests cover redacted exception/file output and `redact_text(...)`.

## 2026-07-04 Dataset Source Adapter

- `git fetch origin`: success; new remote peer branch observed: `origin/codex/a3-p3-ashr-calibration`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; ignored `.secrets/`, `.pytest_cache/`, and private evidence present locally and not staged.
- `gh pr view 4 --json number,state,isDraft,mergeable,headRefName,baseRefName,headRefOid,url,title,statusCheckRollup`: draft PR #4 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `f508399`.
- Peer impact: `origin/codex/a3-p3-ashr-calibration` adds A3 P3 mapping docs/tests and redacted fixtures; current A1 dataset-source adapter keeps A3-facing run fixtures on the existing strict `build_run_fixture(...)`/`validate_run_fixture(...)` path.
- `python -B -m pytest tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: `6 passed in 0.33s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `59 passed in 2.32s`.
- `python -B -m services.runner.dataset_adapter --input docs/evidence/private_refs/a1_api_get_dataset_first_real.json --output docs/evidence/private_refs/a1_real_dataset_cases.json --max-cases 10`: converted 3 Ashr dataset cases into ignored private evidence.
- Private strict replay check: first real source run produced a valid replay fixture with 11 events and 11 VM stream frames; `validate_run_fixture(...)` passed and `build_vm_stream(events)` matched `vm_stream`.
- `python -B -m services.runner.cli --input docs/evidence/private_refs/a1_real_dataset_cases.json --output docs/evidence/private_refs/a1_real_dataset_run_mock.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id ashr-real-dataset-private --runner-id a1-real-dataset-adapter --max-workers 4 --timeout 5`: ran 3 cases, `0 passed`, `3 failed`, `0 errors`, `0 timeouts`, trace `100.00%`; failures are expected content mismatches against the mock agent.
- Chrome read-only check: existing or new Chrome tab at `https://lab.ashr.io/?tab=analysis` showed title `Ashr Labs`, visible hints `Datasets` and `Runs`, and no sign-in text.
- Reviewer follow-up: fixed explicit expected tool-call argument grading so wrong arguments fail while name-only expectations remain compatible; fixed `max_cases=0` to emit no cases and negative `max_cases` to reject.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: `26 passed in 1.57s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `62 passed in 2.70s`.

## 2026-07-04 Create Run Calibration

- `git fetch origin`: success; new remote peer branch observed: `origin/dev/g3-a2-calibration`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; no tracked changes at start; ignored `.secrets/`, `.pytest_cache/`, and private evidence present locally.
- `gh pr view 4 --json number,state,isDraft,mergeable,headRefName,baseRefName,headRefOid,url,title,statusCheckRollup,body`: draft PR #4 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `de9d9f5`.
- Peer impact: `origin/dev/g3-a2-calibration` adds A2 `wrong_arguments` evidence, confirming A1's explicit tool-argument comparison remains relevant. `origin/codex/a3-p3-ashr-calibration` remains a report mapper branch and does not require A1 contract changes this round.
- Chrome read-only calibration: `https://lab.ashr.io/?tab=analysis` showed title `Ashr Labs`, visible hints `Datasets` and `Runs`, no sign-in text, and no visible usage/quota text. Screenshot stored in ignored private evidence.
- Public docs read-only calibration: `https://ashr.io/` and Python SDK docs remained reachable and showed Docs/Plans/Python SDK/TypeScript/API links plus `AshrLabsClient`, `EvalRunner`, and `run_and_deploy`/deploy hints.
- `python -B -m services.runner.api_probe create-run --dataset-id <private numeric id> --result-file docs/evidence/private_refs/a1_real_dataset_run_mock.json --output docs/evidence/private_refs/a1_api_create_run_dry_run.json`: planned create-run, `status=planned`, `attempts=0`, `mutates=true`, `estimated_calls=2`, 3-case private result input.
- `python -B -m services.runner.api_probe create-run --execute --allow-mutate --max-retries 0 --dataset-id <private numeric id> --result-file docs/evidence/private_refs/a1_real_dataset_run_mock.json --output docs/evidence/private_refs/a1_api_create_run_real.json`: executed one real mutating create-run, `status=ok`, HTTP `200`, `attempts=1`.
- Safe create-run shape: response keys `_user`, `run`, `status`; run keys `created_at`, `dataset`, `id`, `result`, `runner`, `tenant`; result keys mirror local A1 RunResult including `aggregate_metrics`, `cases`, `total_cases`, `passed`, `failed`, `trace_completeness`, and `field_map_version`.
- `python -B -m services.runner.api_probe get-run --execute --max-retries 0 --run-id <private run id> --output docs/evidence/private_refs/a1_api_get_created_run_real.json`: `status=ok`, HTTP `200`, `attempts=1`.
- First short `poll-run` against the created run returned complete `run.result` but timed out after 4 attempts because the local completion predicate only checked `aggregate_metrics.tests_passed`; the CLI also emitted a traceback for `TimeoutError`.
- Fix implemented in `packages/sdk/ashr_clone/api_client.py` and `services/runner/api_probe.py`: poll-run accepts observed run-result shapes and CLI catches `TimeoutError`.
- `python -B -m services.runner.api_probe poll-run --execute --max-retries 0 --run-id <private run id> --poll-timeout 10 --poll-interval 2 --output docs/evidence/private_refs/a1_api_poll_created_run_real_v2.json`: fixed poll-run succeeded with `status=ok`, HTTP `200`, `attempts=1`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `16 passed in 0.68s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `64 passed in 2.41s`.
