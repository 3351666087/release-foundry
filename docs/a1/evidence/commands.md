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

## 2026-07-04 Create Request Preflight Guardrail

- `git fetch origin --prune`: success.
- `git status -sb`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; no tracked changes at round start.
- GitHub plugin PR check failed due to MCP transport to `chatgpt.com/backend-api/ps/mcp`; local `gh` fallback was used.
- `gh pr view 4 --repo 3351666087/ashr-codex-factory --json number,title,state,isDraft,mergeable,headRefName,baseRefName,headRefOid,updatedAt,url`: PR #4 open, draft, mergeable, head `07d93b3`.
- `gh pr diff 4 --repo 3351666087/ashr-codex-factory --name-only`: PR changed files stayed within A1 docs, SDK, runner, and tests.
- Chrome read-only calibration:
  - `https://lab.ashr.io/?tab=analysis` showed logged-in `Ashr Labs` title with `Datasets`, `Runs`, `Usage`, `Docs`, `New dataset`, and no sign-in text.
  - `https://lab.ashr.io/?tab=usage` showed `Usage`, `Monitor your resource consumption`, `Upgrade`, and `Loading usage...`; no visible quota/credits counters loaded.
  - Screenshots were stored in ignored private evidence as `ashr_lab_analysis_request_round_2026-07-04.png` and `ashr_lab_usage_request_round_2026-07-04.png`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `22 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `70 passed`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_dry_run.json`: planned create-request, `status=planned`, `attempts=0`.
- Safe preflight summary from the dry-run record: `mutates=true`, `estimated_calls=2`, `num_variations=1`, `num_variations_known=true`, `small_batch=true`, accepted input text only, `non_text_inputs_enabled=false`, media generation all false.
- No real `create-request` was executed in this round.

## 2026-07-04 Create Request Schema And Media Interface Calibration

- `git fetch origin --prune`: success; `origin/dev/g3-a2-calibration` advanced to `815eb31`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; tracked worktree clean at start; ignored `.secrets/`, `.pytest_cache/`, and private evidence present.
- `gh pr view 4 --repo 3351666087/ashr-codex-factory --json number,title,state,isDraft,mergeable,headRefName,baseRefName,headRefOid,updatedAt,url`: PR #4 open, draft, mergeable, head `f8e0f8b`.
- Peer impact: `origin/dev/g3-a2-calibration` is additive in A2/A3/judge/dashboard areas; its stale-ancestry deletion of current A1 API files is not an A1 rollback signal.
- Chrome read-only calibration:
  - Official homepage links docs at `https://ashr.io/docs/python-sdk/overview/`; `/docs` returned 404.
  - API reference lists `create_request`, `create_run`, `get_run`, `list_runs`, `get_dataset`, `list_datasets`, and `request_input_schema`.
  - API reference says `request_input_schema` is optional and a permissive default is sent if omitted.
  - Usage page intermittently showed visible Image/Audio/Files usage counters; direct reload also sometimes showed `Loading usage...`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration Round 2" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_round2_dry_run.json`: planned text-only create-request, `status=planned`, `attempts=0`, `mutates=true`, `estimated_calls=2`.
- `python -B -m services.runner.api_probe create-request --execute --allow-mutate --max-retries 0 --request-name "A1 Tiny Calibration Round 2" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_round2_real.json`: real text-only attempt returned API-level error, HTTP `200`, `attempts=1`, message `request_input_schema is required`.
- SDK parity fix: `AshrApiClient.create_request(...)` now sends a permissive default request input schema when omitted; agent tools are included under `tools`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration Round 2" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_round2_schema_dry_run.json`: planned create-request with default schema; schema keys `additionalProperties`, `tools`, `type`; text-only preflight still safe.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Media Interface Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_api_media_interface_create_request_dry_run.json`: planned dry-run-only media interface request; `generate_images=true`, `generate_audio=true`, image/audio accepted inputs true, `non_text_inputs_enabled=true`, `media_generation_enabled=true`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `25 passed in 0.89s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `73 passed in 2.68s`.

## 2026-07-04 Real Request And Media Boundary Calibration

- `git fetch --all --prune`: success; `origin/dev/g3-a2-calibration` advanced to `eec51c6`.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json number,title,headRefName,baseRefName,state,isDraft,author,updatedAt,headRefOid,url`: open PRs observed were A1 PR #4 and A3 PR #5; merged PRs #1/#2/#3 remained historical.
- Peer impact: `origin/dev/g3-a2-calibration` and `origin/codex/a3-p3-ashr-calibration` are additive in A2/A3/judge/report areas. Their stale-ancestry diffs still show A1 file deletions, but no A1 rollback signal was accepted.
- Chrome read-only Usage check: logged-in `https://lab.ashr.io/?tab=usage` showed Usage period text plus visible `Images`, `Audio`, and `Files` used-of-limit counters; screenshot stored in ignored private evidence. Public API reference confirmed `accepted_inputs` keys `text`, `audio`, `file`, `image`, `video`, `conversation`, media generation flags `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, and request fields including `request_status`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Tiny Calibration Round 2" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_round2_schema_dry_run.json`: safe text-only dry-run, default schema source `client_default`, `num_variations=1`, media generation false, non-text inputs false.
- `python -B -m services.runner.api_probe create-request --execute --allow-mutate --max-retries 0 --max-request-variations 1 --request-name "A1 Tiny Calibration Round 2" --request-file docs/a1/api_calibration/tiny_generation_request.json --output docs/evidence/private_refs/a1_api_tiny_create_request_round2_schema_real.json`: real text-only create-request succeeded, HTTP `200`, `status=ok`, `attempts=1`, response keys `_user`, `request`, `status`.
- `python -B -m services.runner.api_probe get-request --execute --max-retries 0 --request-id <private request id> --output docs/evidence/private_refs/a1_api_tiny_get_request_round2_schema_real.json`: real read-only follow-up succeeded, HTTP `200`, `status=ok`, `attempts=1`, request status initially `processing`.
- `python -B -m services.runner.api_probe poll-request --execute --max-retries 0 --request-id <private request id> --poll-timeout 90 --poll-interval 10 --output docs/evidence/private_refs/a1_api_tiny_poll_request_round2_schema_real.json`: real poll succeeded, HTTP `200`, `status=ok`, `attempts=1`, request status `completed`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Media Interface Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_api_media_interface_create_request_dry_run.json`: dry-run records Image/Audio/Files interface coverage with `generate_audio=true`, `generate_files=true`, `generate_images=true`, accepted inputs `audio/file/image/text=true`, and `num_variations=1`.
- `python -B -m services.runner.api_probe create-request --execute --allow-mutate --allow-media-generation --allow-non-text-inputs --max-retries 0 --max-request-variations 1 --request-name "A1 Media Interface Calibration" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_api_media_interface_create_request_real.json`: real media-interface create-request was accepted, HTTP `200`, `status=ok`, `attempts=1`.
- `python -B -m services.runner.api_probe get-request --execute --max-retries 0 --request-id <private media request id> --output docs/evidence/private_refs/a1_api_media_interface_get_request_real.json`: hosted media request returned `request_status=failed` with completion/duration fields present.
- `python -B -m services.runner.api_probe poll-request --execute --max-retries 0 --request-id <private media request id> --poll-timeout 30 --poll-interval 5 --output docs/evidence/private_refs/a1_api_media_interface_poll_request_real.json`: recorded failed request as error summary, HTTP `200`, `attempts=1`, message `request failed`; no duplicate create-request was attempted.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Text Batch Calibration" --request-file docs/a1/api_calibration/text_batch_generation_request.json --output docs/evidence/private_refs/a1_api_text_batch_create_request_dry_run.json`: 3-variation text-only dry-run passed local preflight.
- `python -B -m services.runner.api_probe create-request --execute --allow-mutate --max-retries 0 --max-request-variations 3 --request-name "A1 Text Batch Calibration" --request-file docs/a1/api_calibration/text_batch_generation_request.json --output docs/evidence/private_refs/a1_api_text_batch_create_request_real.json`: real batch execution returned API-level usage limit error, HTTP `200`, `status=error`, `attempts=1`; no retry was attempted.
- `python -B -m services.runner.api_probe list-requests --execute --max-retries 0 --limit 5 --output docs/evidence/private_refs/a1_api_list_requests_after_media_real.json`: read-only list succeeded, HTTP `200`, `status=ok`, `attempts=1`; safe aggregate showed 5 requests with status distribution `completed=3`, `failed=2`.
- `python -B -m services.runner.api_probe list-datasets --execute --max-retries 0 --limit 5 --output docs/evidence/private_refs/a1_api_list_datasets_after_request_real.json`: read-only list succeeded, HTTP `200`, `status=ok`, `attempts=1`; safe aggregate showed 3 datasets.
- Guardrail hardening: real mutating API calls now refuse nonzero `--max-retries` in both the CLI and direct SDK; `create-request` also treats malformed or unsupported `accepted_inputs` shapes as unsafe, accepts official `{enabled: bool}` input flags, and requires positive integer `num_variations`.
- Evidence hygiene hardening: create-request records now summarize request shape before writing evidence params; the real API body still receives the full request payload.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `37 passed in 1.22s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `85 passed in 3.13s`.

## 2026-07-04 AgentInput Multimodal Envelope

- `git fetch --all --prune`: success; `origin/dev/g3-a2-calibration` advanced to `c2d1561`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking origin; tracked changes at start were the in-progress A1 adapter draft only. Ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` remained unstaged.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json number,title,headRefName,baseRefName,state,isDraft,author,updatedAt,headRefOid,url`: open PRs observed were A1 PR #4 and A3 PR #5; merged PRs #1/#2/#3 remained historical.
- Peer impact: A2/G3 continued additive A2 calibration work and A3 PR #5 stayed in A3 dashboard/report scope. No live peer change required modifying A1 `AgentTurn`, A2 projection, judge semantics, or dashboard behavior.
- Bus-Auditor verdict before implementation: PASS for local `AgentInput` multimodal envelope; BLOCK for any new real `create-request` because hosted request quota was exhausted in the latest evidence. Main agent performed no new real generation request calls.
- Implemented `AgentInput` with `schema_version=ashr.clone.agent_input.v1`, `text`, `parts`, and `metadata`; parts support `text`, `image`, `audio`, and `file` without reading local files.
- Added explicit adapter methods `respond_input`, `arespond_input`, `run_input_turn`, and `arun_input_turn`; legacy `respond("text")` still passes a plain string by default.
- Fixed content-part output normalization so list-style text parts produce joined text instead of a JSON blob, and added adapter error redaction for token-like values, bearer tokens, emails, and signed URL query strings.
- Added schema snapshot `docs/a1/schemas/agent_input.schema.json` and top-level SDK exports for `AgentInput`, `AGENT_INPUT_SCHEMA_VERSION`, and `coerce_agent_input`.
- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `21 passed in 0.10s`.
- `python -B -m pytest tests/a1/test_trace_fixture.py -q -p no:cacheprovider`: `8 passed in 0.27s`.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_api_client.py -q -p no:cacheprovider`: `56 passed in 2.64s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `92 passed in 2.96s`.
- Chrome read-only calibration: logged-in `https://lab.ashr.io/?tab=usage` showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` with no sign-in copy; exact private usage values were not recorded in tracked docs. Official API reference at `https://ashr.io/docs/python-sdk/api-reference/` showed `create_request`, `accepted_inputs`, `generate_audio`, `generate_files`, `generate_images`, and `add_user_file`.
- Final remote recheck before staging: `git fetch --all --prune` advanced `origin/main` to `2205084` and `origin/dev/g3-a2-calibration` to `3c27179`; PR #4 and PR #5 are now merged. `origin/main` contains A1 plus additive A2/A3/judge/dashboard/report fixture work. Current A1 patch remains a follow-up on `codex/a1-local-sdk-runner`.
- Bus-Auditor final verdict: PASS. Safe to stage/commit self-made A1 SDK/tests/docs plus this shared worklog; no private raw evidence was read, and no new real `create-request` was made.
- Commit/push/PR: pushed `2624ea6` to `codex/a1-local-sdk-runner` and opened draft PR #6, `A1 AgentInput multimodal adapter envelope`, because earlier PR #4 had already merged.

## 2026-07-04 Media Request Input Schema Calibration

- `git fetch --all --prune`: success; `origin/dev/g3-a2-calibration` advanced to `145f6ad`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` remained untracked/ignored.
- `gh pr list --repo 3351666087/ashr-codex-factory --state all --limit 30 --json ...`: PR #6 open/draft at head `0870fc8`; PR #4 and PR #5 merged.
- Peer impact: A2/G3 new commit touched `docs/a2`, `fixtures/a2`, `services/judge`, `services/report`, and `tests/a2`/`tests/a3`; no A1-owned files or A1 rollback signal.
- Bus-Auditor start verdict: PASS for local/dry-run `AgentInput.parts` request schema support; keep real `create-request` blocked while quota state is exhausted/unclear.
- Chrome read-only calibration: official API reference showed `request_input_schema`, `accepted_inputs`, `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, `add_user_file`, `file_path`, `description`, and `action_index`. Usage page was logged in but only stably showed `Usage`, `Upgrade`, and `Loading usage`; exact private usage values were not recorded in tracked docs. Screenshot stored in ignored private evidence as `docs/evidence/private_refs/ashr_lab_usage_media_schema_round_2026-07-04.png`.
- Implemented default `request_input_schema` media shape: when accepted inputs include `image`, `audio`, or `file`, the client now includes permissive `AgentInput` properties and `$defs.agent_input_part` while preserving `additionalProperties=true`; part types match enabled accepted inputs.
- Implemented dry-run evidence shape fields: `request_input_schema.property_keys`, `defs_keys`, `agent_input_schema_version`, and `agent_input_part_types`; preflight now records `agent_input_part_types` and `agent_input_schema_version`.
- `python -B -m services.runner.api_probe create-request --request-name "A1 Media Interface Schema Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_api_media_interface_schema_dry_run.json`: planned media create-request, `status=planned`, `attempts=0`.
- Safe dry-run summary: `agent_input_schema_version=ashr.clone.agent_input.v1`, schema property keys `metadata`, `parts`, `schema_version`, `text`, schema defs `agent_input_part`, schema part types `audio`, `file`, `image`, `text`, preflight part types `text`, `image`, `audio`, `file`, media generation enabled, non-text inputs enabled.
- Bus-Auditor must-fix: direct `enum` schemas for non-text-only inputs were not reflected in schema summaries. Fixed `_schema_agent_input_part_types(...)` and added a dry-run record summary regression for image-only accepted input.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `41 passed in 1.16s`.
- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `21 passed in 0.09s`.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_adapter.py -q -p no:cacheprovider`: `62 passed in 1.15s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `96 passed in 2.92s`.
- `git diff --check`: clean except CRLF warnings.

## 2026-07-04 Hosted Media Failure Detail Calibration

- `git fetch origin --prune`: success.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`; tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and private evidence remained unstaged.
- `gh pr view 6 --repo 3351666087/ashr-codex-factory --json number,state,isDraft,mergeable,headRefName,headRefOid,url`: PR #6 open/draft/mergeable at head `87fd28c`.
- Peer impact: latest `origin/dev/g3-a2-calibration` commit `96ff7d5` touched A2 scenario/judge/report evidence paths. No live peer change required modifying A1 contract, judge semantics, or dashboard business logic.
- Existing ignored private evidence recheck: `python -B -m services.runner.api_probe get-request --execute --max-retries 0 --request-id <private media request id> --output docs/evidence/private_refs/a1_api_media_interface_get_request_recheck_real.json` succeeded before this patch with `status=ok`, HTTP `200`, `attempts=1`, hosted `request_status=failed`.
- Safe hosted failure shape from `docs/evidence/private_refs/a1_api_media_interface_get_request_recheck_real.json`: no top-level failure-like request keys; nested request keys included `_failure`, `agent`, `context`, `generation_options`, `metadata`, and `test_config`; `_failure` was an object with keys `at` and `error`, both string values. Raw values remain private.
- `python -B -c "... summarize_request_failure(...)"`: confirmed the SDK helper emits only safe shape fields: `request_status=failed`, `top_level_failure_like_keys=[]`, nested `_failure` keys `at` and `error`, string lengths, and field types.
- Chrome read-only calibration: official API reference at `https://ashr.io/docs/python-sdk/api-reference/` showed `create_request`, `request_input_schema`, `accepted_inputs`, `generate_audio`, `generate_images`, and `add_user_file`. Existing logged-in Usage tab at `https://lab.ashr.io/?tab=usage` showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without sign-in copy; exact counters remain private. Screenshots stored in ignored private evidence as `ashr_lab_usage_failure_detail_round_2026-07-04.png`, `ashr_lab_analysis_failure_detail_round_2026-07-04.png`, and `ashr_existing_usage_failure_detail_round_2026-07-04.png`.
- Implemented hosted failure summary extraction in `packages/sdk/ashr_clone/api_client.py`: failed `get-request` records gain `response_summary.request_failure`; failed `poll-request` records additionally include `error.failure_summary`. The summary records keys/types/lengths/counts only.
- Added a false-positive guard so ordinary hosted fields such as `requestor_details` do not create failure summaries on completed requests.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `44 passed in 1.18s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `99 passed in 2.94s`.
- `git diff --check`: exit 0; CRLF warnings only.
- Added-line sensitive scan: implementation/docs matched no real key, request id, email, or exact usage patterns. Test-only hits were synthetic redaction fixtures.
- No new real `create-request` was executed in this round.

## 2026-07-04 Read-Only API Parity Surface

- `git fetch origin --prune`: success; `origin/dev/g3-a2-calibration` advanced to `561aa0e`.
- `git status -sb --untracked-files=all --ignored`: branch `codex/a1-local-sdk-runner` tracked `origin/codex/a1-local-sdk-runner`; tracked worktree clean at round start. Ignored `.secrets/`, `.pytest_cache/`, and private evidence remained unstaged.
- `gh pr view 6 --repo 3351666087/ashr-codex-factory --json number,state,isDraft,mergeable,headRefName,headRefOid,url`: PR #6 open/draft/mergeable at head `05b4b44`.
- Peer impact: A2 commit `561aa0e` added a real API smoke summary with `init`, `health_check`, `list_datasets`, `list_runs`, `list_requests`, and `list_agents`; this exposed A1's missing read-only `health-check` / `list-agents` probe surface. No A2 files were merged into the A1 branch.
- Local official wheel check: `AshrLabsClient.health_check()` calls API function `keep_alive`; `AshrLabsClient.list_agents()` calls API function `list_agents`.
- Implemented `AshrApiClient.health_check(...)`, `AshrApiClient.list_agents(...)`, and CLI operations `health-check` and `list-agents`.
- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `47 passed in 1.57s`.
- `python -B -m services.runner.api_probe health-check --output docs/evidence/private_refs/a1_api_health_check_dry_run.json`: planned read-only probe, `status=planned`, `attempts=0`.
- `python -B -m services.runner.api_probe list-agents --output docs/evidence/private_refs/a1_api_list_agents_dry_run.json`: planned read-only probe, `status=planned`, `attempts=0`.
- `python -B -m services.runner.api_probe health-check --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_health_check_real.json`: real read-only probe succeeded, HTTP `200`, `status=ok`, `attempts=1`; safe response keys `db`, `message`, `status`.
- `python -B -m services.runner.api_probe list-agents --execute --max-retries 0 --output docs/evidence/private_refs/a1_api_list_agents_real.json`: real read-only probe succeeded, HTTP `200`, `status=ok`, `attempts=1`; safe response keys `_user`, `agents`, `status`, with current `agents_count=0`.
- Chrome read-only calibration: official API reference showed `health_check`, `list_agents`, `list_datasets`, `list_requests`, and `create_request`. Existing logged-in Usage tab showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without sign-in copy; exact counters remain private. Screenshots stored under ignored private evidence as `ashr_lab_analysis_readonly_parity_2026-07-04.png` and `ashr_lab_usage_readonly_parity_2026-07-04.png`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `102 passed in 3.27s`.
- `git diff --check`: exit 0; CRLF warnings only.
- Added-line value-oriented sensitive scan: no token-like key value, bearer token, email, private request id, or exact usage pattern. A broader scan matched only the public env var name `ASHR_LABS_API_KEY` in the field map.
- No real `create-request` or `create-run` was executed in this round.

## 2026-07-04 Local Cloud API Runtime Skeleton

- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `gh pr list --state all`: repo root `C:/Users/33516/Documents/Ashr`, remote `3351666087/ashr-codex-factory`, branch `codex/a1-local-sdk-runner`, PR #6 open/draft. Fetch advanced `origin/dev/g3-a2-calibration` to `ddd615a`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present.
- Peer impact: latest A2/G3 commit `ddd615a` touched A2 scenario/judge/report coverage files only. No A1-owned file or Gate contract impact observed.
- A1 scan: existing Python SDK/Adapter/Runner/Trace/API probe present; `services/api`, `services/cloud`, `packages/ts`, root `package.json`, `pyproject.toml`, and `requirements.txt` absent before this round.
- Three scored enhancements:
  - Local cloud API skeleton: demo 5, risk 4, contract impact 2, effort 3, API evidence 3. Selected as highest ROI because it creates the tenant/project/dataset/run/request anchor for later TS, queue, and quota work.
  - Standalone quota ledger module: demo 3, risk 4, contract impact 1, effort 2, API evidence 2.
  - TypeScript SDK quickstart scaffold: demo 4, risk 3, contract impact 2, effort 4, API evidence 2.
- Bus-Auditor start verdict: PASS with tight scope; keep implementation local-only, avoid new undeclared runtime dependencies, no real mutating API calls, and keep touched files in A1-owned dirs.
- Explorer-SDK/API: confirmed Python SDK/API probe surfaces are strong but no integrated local cloud runtime, runner is still text-first for batch cases, media semantics remain unresolved, quota is guardrail-based, and TS parity is absent.
- Explorer-Chrome/Product: official API reference exposed `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `request_status`, and media generation/file fields. Logged-in Usage page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; no exact private counter values recorded. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_hosted_media_failure_detail_round_2026-07-04.png`.
- Worker-Runtime: independently implemented/reviewed the bounded local runtime shape under `services/api`; main workspace includes `CloudApiService`, `InMemoryCloudStore`, and `QuotaLedger`.
- Worker-TS/Reviewer: confirmed no TypeScript package exists and proposed a future `packages/ts/ashr-clone` quickstart with injected `fetch`, dry-run default, env-key parity, and redaction tests.
- Implemented `services/api/runtime.py` and `services/api/__init__.py`: local-only tenant/project/dataset/request/run records, project-scoped quota ledger, run submit/poll, observation storage, and fixture export.
- Added schema snapshot `docs/a1/schemas/cloud_api.schema.json`.
- Added `tests/a1/test_cloud_api.py` plus schema snapshot guard in `tests/a1/test_trace_fixture.py`.
- `python -B -m pytest tests/a1/test_cloud_api.py -q -p no:cacheprovider`: 7 passed.
- `python -B -m pytest tests/a1/test_trace_fixture.py -q -p no:cacheprovider`: 8 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 109 passed.
- Final remote recheck before staging: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` to `bee20af`; latest peer files were `docs/a2/README.md`, `docs/evidence/a2_real_api_smoke.json`, `scripts/a2_regenerate_fixtures.py`, and `tests/a2/test_contracts.py`. No A1-owned file impact observed.
- No Ashr API call was made in this implementation round; only Chrome read-only checks were performed.

## 2026-07-04 Local Cloud API Demo CLI

- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `gh pr list --state all`: repo root `C:/Users/33516/Documents/Ashr`, remote `3351666087/ashr-codex-factory`, branch `codex/a1-local-sdk-runner`, PR #6 open/draft.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present.
- Peer impact at round start: latest `origin/dev/g3-a2-calibration` commit `bee20af` touched A2 docs/evidence/scripts/tests only. No A1-owned file or Gate contract impact observed.
- A1 scan: Python SDK/Adapter/Runner/Trace/API probe and `services/api` runtime skeleton present; `services/api/cli.py`, `services/api/demo.py`, `packages/ts`, and root `package.json` absent before this round.
- Three scored enhancements:
  - Local cloud API demo CLI: demo 5, risk 4, contract impact 2, effort 3, API evidence 3. Selected because it proves the fresh-setup cloud runtime path.
  - TypeScript SDK quickstart scaffold: demo 4, risk 3, contract impact 2, effort 4, API evidence 2.
  - Hosted media read-only semantics calibration: demo 3, risk 4, contract impact 1, effort 3, API evidence 4.
- Implemented `services/api/demo.py`: `run_agent_cloud_demo(...)` loads cases, creates local tenant/project/dataset, runs an external agent target, submits the `RunResult`, polls, writes fixture/run-result JSON, and emits a safe summary.
- Implemented `services/api/cli.py`: `python -B -m services.api.cli run-agent ...` fresh-setup command with `--fixture-output`, `--summary-output`, `--run-output`, and `--fail-on-case-failure`.
- Updated `services/api/__init__.py` to export `run_agent_cloud_demo`.
- Added/kept A1 tests in `tests/a1/test_cloud_api.py` and `tests/a1/test_cloud_api_cli.py` covering helper use, CLI success, and CLI failure return code while still writing outputs.
- Local smoke command: `python -B -m services.api.cli run-agent --input docs/a1/evidence/local_agent_cases_30.json --agent examples.agents.mock_agent:RespondingMockAgent --fixture-output docs/evidence/private_refs/a1_cloud_demo_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_cloud_demo_summary_smoke.json --run-output docs/evidence/private_refs/a1_cloud_demo_run_smoke.json --tenant-id tenant_a1_smoke --project-id project_a1_smoke --dataset-id dataset_a1_smoke --max-workers 4 --timeout 5 --fail-on-case-failure`: completed locally with 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, trace completeness 1.0, and quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- Chrome read-only calibration: official API reference showed `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_dataset`, `list_datasets`, `request_input_schema`, `accepted_inputs`, `request_status`, `health_check`, and `list_agents`. Usage page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` without sign-in copy; exact counters not recorded. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_cloud_demo_2026-07-04.png`.
- Redaction hardening: `services.api.cli` now redacts operational error text through the SDK redaction helper, and `redact_text(...)` covers `sk-...` style key strings in addition to existing token/Bearer/email patterns.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 15 passed.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 62 passed.
- Bus-Auditor final must-fix: adapter error redaction did not yet cover `sk-...`; fixed `packages/sdk/ashr_clone/adapter.py` and added fixture/run-output leak regressions for the sensitive-agent CLI path.
- `python -B -m pytest tests/a1/test_adapter.py tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 83 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 117 passed.
- Final remote recheck before staging: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` to `31ff317`; latest peer files were A2 docs/worklog/fixtures/scripts and `services/judge`/`tests/a2` only. No A1-owned file impact observed.
- `git log --oneline HEAD..origin/codex/a1-local-sdk-runner`: empty before staging.
- `gh pr view 6 --json number,title,state,isDraft,headRefName,baseRefName,headRefOid,url`: PR #6 remained open/draft on `codex/a1-local-sdk-runner`, head `1e06731`.
- `git diff --check`: no whitespace errors; Windows line-ending warnings only.
- Sensitive scan over changed A1/docs files: matches were public env var names, redaction constants, private-evidence path references, and synthetic test strings only. No real key, `.secrets/`, or private raw evidence file was staged.
- Final Chrome main-thread recheck: API reference still exposed run/dataset/request/health/agent fields; Usage page loaded asynchronously and then showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade` with no `Login`/`Sign in`. Exact private counters were not recorded.
- Final Bus-Auditor: PASS after adapter redaction fix; required staging note was to include the four untracked source/test files with tracked changes and leave `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` unstaged.
- Real Ashr API calls: none in this implementation round.

## 2026-07-04 TypeScript SDK Quickstart Parity

- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `gh pr list --state all`: repo root `C:/Users/33516/Documents/Ashr`, remote `3351666087/ashr-codex-factory`, branch `codex/a1-local-sdk-runner`, PR #6 open/draft. Fetch advanced `origin/dev/g3-a2-calibration` to `a6ee272`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` present.
- Peer impact: `a6ee272` touched A2 docs/fixtures/importer plus `services/judge` and `tests/a2`; no A1-owned conflict. A1 did not modify `services/judge`.
- A1 scan: Python SDK/Adapter/Runner/Trace/API probe, `services/api` runtime, cloud demo CLI, and A1 docs/tests present; `packages/ts` absent before this round.
- Three scored enhancements:
  - TypeScript SDK quickstart parity: demo 5, risk 4, contract impact 1, effort 3, API evidence 3. Selected as highest ROI.
  - Queue worker facade: demo 4, risk 4, contract impact 2, effort 4, API evidence 2.
  - Hosted media semantics read-only calibration: demo 3, risk 4, contract impact 1, effort 3, API evidence 4; real calls blocked this round.
- Implemented `packages/ts/ashr-clone`: TypeScript source, package metadata, package lock, tests, README, and quickstart example.
- Consolidated concurrent Worker-TS JS+d.ts draft into the TypeScript-source package and removed the duplicate source JS/d.ts path before staging.
- `npm install --prefix packages/ts/ashr-clone`: installed TypeScript dev dependency, audited 2 packages, 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 13 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 117 passed.
- `git diff --check`: no whitespace errors; Windows line-ending warnings only.
- `node packages/ts/ashr-clone/examples/quickstart.mjs docs/a1/evidence/local_run_30.json docs/evidence/private_refs/a1_ts_quickstart_fixture_smoke.json`: wrote a local-only 30-case TS fixture under ignored private evidence; summary status `ok`, `total_cases=30`, `local_only=true`, `ashr_api_used=false`.
- Sensitive scan over intended files: matches were public env var names, private-evidence path references, package-lock public npm URL, and synthetic test tokens/emails/URLs only. No real key, secret file contents, or raw private evidence was read or staged.
- Chrome/Product subagent recheck: public API reference still exposed TypeScript reference/tab and dataset/run/request/media boundary terms. Lab Usage loaded without sign-in blocker, but media counters were still asynchronous/unstable in that pass.
- Final Bus-Auditor: PASS. Stage only six modified docs and nine new `packages/ts/ashr-clone` package/source/test/example files; leave `dist/`, `node_modules/`, `.secrets/`, `.pytest_cache/`, and `docs/evidence/private_refs/` unstaged.
- Real Ashr API calls: none in this implementation round.

## 2026-07-04 Local Queue Worker Facade

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced to `fe01f94`.
- Final remote recheck before staging: `origin/dev/g3-a2-calibration` advanced again to `4af23c4`, PR #6 was merged, and `origin/main` advanced to `e786c98` containing prior A1 head `7c94460`. The current A1 branch was fast-forwarded to `origin/main`, then this round's stash was reapplied; only `docs/evidence/official_site_gaps.md` conflicted and was resolved by preserving main's A1/A2/A3 gap wording plus the new A1 queue-worker gap.
- Round-start `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view`; `gh pr list --state all`: repo root `C:/Users/33516/Documents/Ashr`, remote `3351666087/ashr-codex-factory`, branch `codex/a1-local-sdk-runner`, PR #6 open/draft at that time.
- `git status -sb --untracked-files=all --ignored`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, `packages/ts/ashr-clone/dist/`, and `node_modules/` present.
- Peer impact: latest `fe01f94` touched A2 docs/worklog/fixtures, A2 merge script, `services/judge`, and `tests/a2`; no A1-owned file or Gate contract impact observed.
- Three scored enhancements:
  - Queue worker facade: demo 5, risk reduction 5, contract impact 2, effort 3, API evidence 2. Selected because queue/run lifecycle is an explicit phase target and unblocks batch/cloud runtime behavior.
  - TypeScript API-client dry-run/transport-injected parity: demo 4, risk reduction 4, contract impact 1, effort 4, API evidence 4.
  - Public-safe A2 grading import from private hosted evidence: demo 3, risk reduction 3, contract impact 2, effort 3, API evidence 3.
- Chrome read-only calibration: public API reference still exposed `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `request_status`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`.
- Chrome Usage calibration: `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy in this pass; `Images`, `Audio`, `Files`, `Usage`, and `Upgrade` were not confirmed. No private counters recorded.
- Implemented `services/api/queue_worker.py`: `CloudQueueWorker` and `QueueRunRequest` for local queued agent runs, max worker normalization to at least 4, background execution, status polling, cancellation guard, quota-safe completion, and redacted failure handling.
- Extended `services/api/runtime.py`: queued run creation, running/completed/failed/cancelled transitions, `status_history`, phase-correct quota consumption, and completion into the existing A3 fixture/export shape.
- Extended `services/runner/runner.py`: optional `run_id` injection so queued run ids match `RunResult` and observation `run_id` values.
- Extended `services/api/demo.py` and `services/api/cli.py`: `run_agent_cloud_queue_demo(...)` and `python -B -m services.api.cli run-agent-queued ...`.
- Updated `services/api/__init__.py`, `docs/a1/schemas/cloud_api.schema.json`, `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, and this command log.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 21 passed after adding queue worker and wait-timeout coverage.
- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: 19 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 123 passed.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 13 Node tests passed.
- `python -B -m services.api.cli run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples.agents.mock_agent:RespondingMockAgent --fixture-output docs/evidence/private_refs/a1_queue_demo_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_demo_summary_smoke.json --run-output docs/evidence/private_refs/a1_queue_demo_run_smoke.json --tenant-id tenant_a1_queue_smoke --project-id project_a1_queue_smoke --dataset-id dataset_a1_queue_smoke --runner-id a1-queue-smoke --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure`: local-only queued smoke completed with 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, trace completeness 1.0, status history `queued -> running -> completed`, and quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- Bus-Auditor must-fix: queued demo could export incomplete output after wait timeout. Fixed by requiring terminal status before writing fixture/run/summary output, and added helper/CLI timeout regressions that assert no incomplete outputs are written and CLI exits nonzero.
- Real Ashr API calls: none in this implementation round.

## 2026-07-04 TypeScript API Client Dry-Run Parity

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced from `085c439` to `6efe390`.
- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,defaultBranchRef,url`; `gh pr list --state all --limit 30 --json ...`: repo root `C:/Users/33516/Documents/Ashr`, remote `3351666087/ashr-codex-factory`, branch `codex/a1-local-sdk-runner`, default branch `main`, PR #7 open/draft/mergeable at `23b4af0`.
- `git status -sb --untracked-files=all --ignored`: tracked worktree was clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, `packages/ts/ashr-clone/dist/`, and `node_modules/` remained unstaged.
- Peer impact: latest peer commit `6efe390 G3: add A2 batch planning gate` touched `docs/a2`, `fixtures/a2`, `scripts/a2_regenerate_fixtures.py`, `services/judge`, `tests/a2`, and `docs/worklog/Kay.md`. No A1-owned conflict observed.
- Chrome main-thread check:
  - `https://ashr.io/docs/api-reference/` returned `404 Not Found`.
  - `https://ashr.io/docs/python-sdk/api-reference/` was reachable and exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, `generate_files`, `Trace`, `Span`, and `Generation`.
  - `https://lab.ashr.io/?tab=usage` loaded as `Ashr Labs` but showed sign-in copy during this pass; no usage counters were recorded.
  - Private screenshot paths: `docs/evidence/private_refs/ashr_api_reference_ts_client_round_2026-07-04.png` and `docs/evidence/private_refs/ashr_usage_ts_client_round_2026-07-04.png`.
- Explorer-Chrome subagent also recorded private evidence under `docs/evidence/private_refs/ashr_a1_chrome_verification_2026-07-04.md` and screenshots for homepage/docs/lab login block.
- Implemented `packages/ts/ashr-clone/src/api-client.ts`: `AshrApiClient`, `AshrApiError`, `MissingAshrApiKeyError`, env/base-url constants, field-map version, dry-run call plans/records, injected transport execution, session context injection, retry handling, read-only methods, mutating `createRun`/`createRequest` guardrails, media/non-text preflight summaries, and safe failed-request summary shapes.
- Updated `packages/ts/ashr-clone/src/index.ts` to export the API client layer.
- Added `packages/ts/ashr-clone/test/api-client.test.mjs`: 11 Node tests for dry-run no-fetch behavior, env construction, injected transport, `keep_alive`, `list_agents`, missing-key guard, media schema dry-runs, mutation guardrails, retry, API error redaction, failed-request summaries, and preflight helpers.
- Incorporated Worker-Runtime follow-up in `services/api/queue_worker.py` and `tests/a1/test_cloud_api.py`: cancelled queued/running runs now return terminal `cancelled` state from `wait_for_run(...)` without leaking executor `CancelledError`.
- Bus-Auditor final block: non-dry-run `pollRun` / `pollRequest` could reach injected transport without an API key through the internal `pollUntil(...)` path. Fixed by adding the missing-key guard inside `AshrApiClient.request(...)`; tests now assert `init`, `pollRun`, and `pollRequest` reject with `MissingAshrApiKeyError` and do not call transport when no key is configured.
- `npm test --prefix packages/ts/ashr-clone`: `tsc` build plus 24 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 125 passed.
- Real Ashr API calls: none in this round. No env key, `.secrets`, desktop key file, or private evidence contents were read.

## 2026-07-04 Queue Persistence And Replay CLI

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success.
- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,url,defaultBranchRef`; `gh pr list --state all --limit 20 --json ...`: repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`, PR #7 open/draft/mergeable at `c81e60d`.
- `git status -sb --untracked-files=all`: tracked changes at round start were in-progress A1 queue persistence files only: `services/api/runtime.py`, `services/api/queue_worker.py`, and `tests/a1/test_cloud_api.py`.
- Peer impact: latest `origin/dev/g3-a2-calibration` was `007c650 G3: add A2 semantic judge harness`, touching `docs/a2`, `docs/worklog/Kay.md`, `fixtures/a2`, `scripts/a2_regenerate_fixtures.py`, `services/judge`, and `tests/a2`. No A1-owned conflict observed; future integration must preserve those peer files.
- Three scored enhancements:
  - Queue persistence/replay CLI controls: demo value 5, risk reduction 5, contract impact 1, estimated effort 2, API evidence value 2. Selected because the core library slice already existed and this makes cross-process replay/A3 fixture export operable.
  - TypeScript probe CLI wrapper around dry-run `AshrApiClient`: demo value 4, risk reduction 4, contract impact 1, estimated effort 3, API evidence value 4.
  - Public-safe A2 grading import from selected hosted evidence: demo value 3, risk reduction 3, contract impact 2, estimated effort 3, API evidence value 3.
- Bus-Auditor start verdict: PASS for local-only queue persistence/replay next; required worklog update from stale PR/peer refs to PR #7 head `c81e60d` and peer `007c650`; no private evidence contents, `.secrets`, or desktop key file read.
- Explorer-SDK/API: confirmed Python API client/probe are mature, TS has library parity but no CLI probe yet, and queue persistence/replay already had library tests but lacked CLI/product controls.
- Explorer-Chrome: Chrome subagent could not stably claim lab tabs, but recorded no secret/API-key actions. Main-thread Chrome confirmed public API reference fields and current Usage labels.
- Worker-Runtime: implemented the bounded library slice for `snapshot_state`, `write_state`, `from_state_file`, and `replay_incomplete_runs`; main thread added CLI/demo controls on top.
- Main-thread Chrome read-only calibration: API reference exposed `AshrLabsClient`, `health_check`, `list_agents`, `create_run`, `get_run`, `list_runs`, `poll_run`, `create_request`, `get_request`, `list_requests`, `request_input_schema`, `accepted_inputs`, `generate_images`, `generate_audio`, and `generate_files`. Usage page showed labels `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private counters were not recorded.
- Implemented `services/api/demo.py` helpers: `create_agent_cloud_queue_state(...)`, `replay_agent_cloud_queue_state(...)`, `export_run_fixture_from_state(...)`, optional `state_output_path` for direct/queued demos, and terminal-status guard before restored-state fixture export.
- Implemented `services/api/cli.py` commands: `queue-run`, `replay-queued`, and `export-fixture`, plus optional `--state-output` for `run-agent` and `run-agent-queued`.
- Updated `services/api/__init__.py`, `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, this command log, and `docs/evidence/worklog.md`.
- Added CLI regressions in `tests/a1/test_cloud_api_cli.py` for `queue-run -> replay-queued -> export-fixture` across subprocesses and for blocking fixture export from an incomplete queued state.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 28 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 130 passed.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 24 Node tests passed.
- `python -B -m services.api.cli queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_queue_state_snapshot_smoke.json --summary-output docs/evidence/private_refs/a1_queue_state_summary_smoke.json --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --dataset-id dataset_a1_replay_smoke --runner-id a1-replay-smoke --run-id run_a1_replay_smoke`: wrote ignored local queued state with 30 cases and `queued` run status.
- `python -B -m services.api.cli replay-queued --state-input docs/evidence/private_refs/a1_queue_state_snapshot_smoke.json --agent examples.agents.mock_agent:RespondingMockAgent --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --dataset-id dataset_a1_replay_smoke --fixture-output docs/evidence/private_refs/a1_queue_replay_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_replay_summary_smoke.json --run-output docs/evidence/private_refs/a1_queue_replay_run_smoke.json --state-output docs/evidence/private_refs/a1_queue_replayed_state_smoke.json --max-runs 1 --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: completed locally with 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, status history `queued -> running -> completed`, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `python -B -m services.api.cli export-fixture --state-input docs/evidence/private_refs/a1_queue_replayed_state_smoke.json --tenant-id tenant_a1_replay_smoke --project-id project_a1_replay_smoke --run-id run_a1_replay_smoke --fixture-output docs/evidence/private_refs/a1_queue_exported_fixture_smoke.json --summary-output docs/evidence/private_refs/a1_queue_export_summary_smoke.json`: exported a completed run fixture from restored state; incomplete exports remain blocked by default.
- Final remote recheck before staging: `origin/dev/g3-a2-calibration` advanced from `007c650` to `18e4a96 G3: add A2 semantic judge import bridge`, touching `docs/a2`, `docs/worklog/Kay.md`, `fixtures/a2/calibration`, `scripts/a2_import_semantic_judge.py`, `scripts/a2_merge_calibration_observations.py`, `services/judge`, and `tests/a2`. No A1-owned conflict observed; current branch remained even with `origin/codex/a1-local-sdk-runner`.
- Real Ashr API calls: none in this round. No env key, `.secrets`, desktop key file, or raw private evidence contents were read.

## 2026-07-04 TypeScript Probe CLI

- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,url,defaultBranchRef`: repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced to `8542b19`, and `origin/codex/a3-p3-ashr-calibration` advanced to `5872ef3`.
- `gh pr list --state all --limit 30 --json ...`: PR #7 open/draft on `codex/a1-local-sdk-runner` at `7942516`.
- `git status -sb --untracked-files=all`: tracked worktree clean at round start; ignored `.secrets/`, `.pytest_cache/`, `docs/evidence/private_refs/`, TS `dist/`, and TS `node_modules/` remained unstaged.
- Peer impact: A2 latest `8542b19 G3: add A2 regression replay evidence` touched A2 docs/fixtures/scripts plus `services/judge` and `tests/a2`; A3 latest `5872ef3 Add A3 product console media evidence` touched dashboard/report/A3 docs/screenshots/fixtures/tests. No A1-owned conflict observed.
- Baseline A1 scan: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime/queue/replay CLI, TypeScript local SDK and hosted dry-run API client, tests/schemas/docs, and ignored private evidence filenames are present. TS package has no `bin` or probe CLI yet.
- Three scored enhancements:
  - TypeScript probe CLI wrapper around dry-run `AshrApiClient`: demo value 5, risk reduction 5, contract impact 1, effort 3, API evidence 5. Selected.
  - Persistent queue batch controls for multiple queued runs: demo value 4, risk reduction 4, contract impact 1, effort 3, API evidence 2.
  - Public-safe A2/A3 calibration bridge from selected hosted evidence: demo value 4, risk reduction 3, contract impact 2, effort 4, API evidence 4.
- Spawned Bus-Auditor, Explorer-SDK/API, Explorer-Chrome, and Worker-TS. Runtime/Reviewer spawn was deferred because the agent thread limit was reached.
- Bus-Auditor initial verdict: BLOCK until TS probe CLI stopped printing full real records by default, wrote evidence files under ignored private refs, and persisted redacted error records on failure.
- Explorer-SDK/API: recommended exact Python-parity operations and flags; noted TS `outputPath` was only metadata until the CLI wrote files.
- Explorer-Chrome: verified public TypeScript API/auth docs and Usage labels. TS auth docs showed `ASHR_LABS_API_KEY`, optional `ASHR_LABS_BASE_URL`, `fromEnv`, `apiKey` / `baseUrl`, and API key list/revoke/security guidance. Usage page showed `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact counters were not recorded.
- Worker-TS implemented the first CLI draft; main thread tightened stdout/error-record safety per Bus.
- Implemented `packages/ts/ashr-clone/src/probe.ts`: dry-run-first TS API probe CLI, Python-parity operations, env-only key loading for real calls, mutating execution gates, media/non-text/variation guardrails, default ignored private evidence output, one-line stdout summaries by default, opt-in `--print-record`, and redacted error-record persistence.
- Added `packages/ts/ashr-clone/test/probe.test.mjs`: covers no-network dry-run, output-file writing, full JSON only with `--print-record`, read-only mappings, create-request preflight, create-run dry-run, missing-key guard, mutation guard, and media guard before transport.
- Updated TS package metadata/docs plus A1 README, field map, API calibration README, Explorer SDK note, official site gaps, and worklog.
- `npm install --package-lock-only --prefix packages/ts/ashr-clone`: up to date, 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 33 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 130 passed.
- `node packages/ts/ashr-clone/dist/probe.js init --output docs/evidence/private_refs/a1_ts_api_init_dry_run.json`: dry-run planned `init`, wrote ignored private evidence, stdout summary only.
- `node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json`: dry-run planned Image/Audio/Files create-request, wrote ignored private evidence, stdout summary only.
- Final remote recheck before staging: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` to `1cc07a7 G3: deepen A2 media API calibration` and `origin/codex/a3-p3-ashr-calibration` to `02f6ce7 Add A3 tool call diff panel`; changed paths were A2/A3 docs/fixtures/tests plus `services/judge`, `services/report`, and `apps/dashboard`, with no A1-owned conflict or staged peer files.
- Final validation: `npm test --prefix packages/ts/ashr-clone` passed 33 Node tests; `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed 130 tests; `git diff --check` exited 0 with only CRLF warnings.
- Public-file secret scan: `rg` checks for desktop key paths, local key filenames, GitHub-token prefixes, model-key prefixes, and bearer-token literals in the intended TS/A1 docs files found no matches.
- Real Ashr API calls: none in this round. No env key, `.secrets`, desktop key file, or raw private evidence contents were read.

## 2026-07-04 Queue Batch Replay Controls

- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,url,defaultBranchRef`: repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`.
- `git status -sb --untracked-files=all`: tracked worktree clean at round start.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success, no fetch output in this pass.
- `gh pr list --state all --limit 30 --json ...`: PR #7 open/draft on `codex/a1-local-sdk-runner` at `4163a5e`; PR #8 open/draft for A3 at `02f6ce7`.
- Baseline scan: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime/queue/replay CLI, TS local SDK and hosted dry-run API/probe, tests/schemas/docs, and ignored private evidence filenames are present. Raw private evidence contents were not read.
- Env key presence check: `ASHR_API_KEY` and `ASHR_LABS_API_KEY` were not present in the current process, so live hosted API work was blocked for this round. The desktop key file, `.secrets`, and raw private evidence contents were not read.
- Peer impact: A2 branch `origin/dev/g3-a2-calibration` remained at `1cc07a7`, and A3 branch `origin/codex/a3-p3-ashr-calibration` remained at `02f6ce7`; peer paths are A2/A3/judge/dashboard/report areas with no A1-owned conflict observed.
- Three scored enhancements:
  - Persistent queue batch controls for multiple queued runs with deterministic replay ordering and summary export: demo value 5, risk reduction 5, contract impact 1, effort 2, API evidence 2. Selected.
  - TypeScript local runner/adapter body (`AgentAdapter`, `runAgentBatch`, `LocalEvalRunner`, CLI): demo value 5, risk reduction 4, contract impact 1, effort 4, API evidence 2.
  - TS injected-transport API error/quota fixtures: demo value 3, risk reduction 4, contract impact 1, effort 2, API evidence 3.
- Bus-Auditor verdict: PASS for local-only queue batch controls; BLOCK for live hosted API work because env keys are absent; BLOCK for A2/A3 hosted-evidence bridge until explicit public-safe evidence selection rules exist.
- Explorer-SDK/API: confirmed TS still lacks the Python-sized adapter/runner/dataset/trace/queue CLI body; recommended TS local runner/adapter as the next high-ROI TS growth slice after this queue batch round.
- Explorer-Chrome subagent ran against unrelated OpenAI docs, so its result is not used as Ashr evidence.
- Main-thread Chrome: `https://ashr.io/docs/typescript-sdk/api-reference/` and `https://ashr.io/docs/python-sdk/api-reference/` were reachable; TS docs showed run/request/health/trace fields plus `generate_audio` and `generate_files`, while Python docs also showed `generate_images`. `https://lab.ashr.io/?tab=usage` settled to `Usage`, `Images`, `Audio`, `Files`, and `Upgrade`; exact private counter values were not recorded. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_queue_batch_round_2026-07-04.png`.
- Worker-Runtime partial patch was integrated by the main thread: deterministic replay sort now uses `metadata.replay_order` / `batch_index` before `created_at` and `run_id`; queued batch summaries include run IDs/status histories; replay can write per-run fixture/result directories.
- Implemented `services/api/demo.py`: `create_agent_cloud_queue_state(...)` accepts `run_ids` / `run_count`, writes `batch_index`, `batch_size`, and `replay_order`; `replay_agent_cloud_queue_state(...)` defaults to batch replay, writes `outputs.fixtures` and `outputs.run_results`, and keeps singleton output paths blocked for multi-run replay.
- Implemented `services/api/cli.py`: `queue-run --run-id` is repeatable, `queue-run --run-count` can generate local run IDs, and `replay-queued` supports `--fixture-output-dir` / `--run-output-dir` with default `--max-runs 100`.
- Implemented `services/api/queue_worker.py`: replay ordering is explicit and replayed runs receive normalized queue/runner worker metadata.
- Added tests in `tests/a1/test_cloud_api.py` and `tests/a1/test_cloud_api_cli.py` for batch replay order, multi-run CLI export, quota counts, per-run fixture/result outputs, and singleton output guardrails.
- `python -B -m py_compile services/api/demo.py services/api/queue_worker.py services/api/cli.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py`: passed.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 31 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 33 Node tests passed.
- `git diff --check`: exited 0 with only CRLF warnings.
- `python -B -m services.api.cli queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --summary-output docs/evidence/private_refs/a1_queue_batch_state_summary_smoke.json --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --runner-id a1-batch-replay-smoke --run-id run_a1_batch_replay_002 --run-id run_a1_batch_replay_001`: wrote ignored local batch queued state with two 30-case runs, explicit run order, `dataset.create=1`, and `run.submit=2`.
- `python -B -m services.api.cli replay-queued --state-input docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --agent examples.agents.mock_agent:RespondingMockAgent --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --fixture-output-dir docs/evidence/private_refs/a1_queue_batch_replay_fixtures --summary-output docs/evidence/private_refs/a1_queue_batch_replay_summary_smoke.json --run-output-dir docs/evidence/private_refs/a1_queue_batch_replay_runs --state-output docs/evidence/private_refs/a1_queue_batch_replayed_state_smoke.json --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: replayed two runs in deterministic batch order; each completed 30 passed, 0 failed, 0 errored, 0 timed out, with 60 observations; total quota used `dataset.create=1`, `run.submit=2`, `observation.write=120`; per-run fixture/result files were written under ignored private evidence.
- Final remote recheck before audit: `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` advanced `origin/dev/g3-a2-calibration` to `ea1039a G3: surface A2 evidence readiness in A3 reports` and `origin/codex/a3-p3-ashr-calibration` to `e39b823 Merge latest main into A3 product console PR`. Direct new peer paths were A2 docs/worklog/fixtures/scripts/judge/tests and A3 dashboard/report/tests; no A1-owned working tree conflict or staged peer files observed.
- Real Ashr API calls: none in this round because env keys were absent and local key files remain unread.

## 2026-07-04 TypeScript Runner/Dataset/Trace Parity

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success.
- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,url,defaultBranchRef`; `gh pr list --state all --limit 20 --json ...`: repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`, PR #7 already merged and current branch had unmerged local head `b95ef5b`.
- `git status -sb`: clean at round start; after implementation only A1/TS-owned files were modified/added.
- Baseline scan: Python SDK/Adapter/Runner/Trace/API probe, local cloud runtime/queue/replay CLI, TS API client/probe/cloud runtime, A1 tests/schemas/docs, and ignored private evidence filenames were present. Raw private evidence contents, `.secrets`, and desktop key files were not read.
- Env presence check: `ASHR_API_KEY=false`, `ASHR_LABS_API_KEY=false`; no real hosted API call was run in this round.
- Peer impact: `origin/main` had advanced beyond the A1 branch and PR #7 was merged; current A1 branch still needs a new PR for unmerged branch commits. A2/A3 remote branches touched judge/dashboard/report/doc areas with no working-tree conflict in A1-owned files observed during this implementation pass.
- Ten scored enhancements:
  - TS local runner/adapter/CLI: demo 5, risk 5, contract 1, effort 4, API evidence 2. Implemented.
  - TS dataset-source adapter: demo 5, risk 4, contract 1, effort 3, API evidence 4. Implemented.
  - TS strict trace/replay helpers: demo 4, risk 5, contract 1, effort 3, API evidence 2. Implemented.
  - TS dataset adapter CLI: demo 4, risk 4, contract 1, effort 2, API evidence 3. Implemented.
  - TS `runCase`/`runBatch`/`BatchRunner` and `toA2JudgeRun`: demo 4, risk 4, contract 1, effort 2, API evidence 1. Implemented.
  - TS cloud queue/replay parity: demo 5, risk 4, contract 1, effort 5, API evidence 2. Deferred.
  - TS quota/error injected fixture pack: demo 3, risk 4, contract 1, effort 2, API evidence 4. Deferred.
  - Real API read-only batch when env key exists: demo 3, risk 3, contract 1, effort 2, API evidence 5. Blocked by absent env key.
  - Hosted media failure shape calibration: demo 3, risk 4, contract 1, effort 3, API evidence 5. Blocked for mutation by quota/env; read-only docs only this round.
  - TS docs/fresh setup polish: demo 3, risk 3, contract 1, effort 2, API evidence 1. Partially implemented through README/field map updates.
- Bus-Auditor: PASS for TS local runner/adapter after queue PR hygiene warning; required no live API calls without env key and a new PR for unmerged branch work.
- Explorer-SDK/API: confirmed the new TS runner/dataset files and flagged remaining TS gaps: strict trace exports, runner breadth, dataset adapter CLI, A2 projection, docs. These were implemented in this pass.
- Explorer-Chrome/Product: verified TypeScript and Python public API docs plus logged-in Usage labels. Private screenshot path: `docs/evidence/private_refs/ashr_lab_usage_ts_python_parity_2026-07-04.png`.
- Worker-TS: implemented the core `packages/ts/ashr-clone/src/runner.ts` slice; main thread integrated it, added dataset adapter, trace helpers, CLIs, tests, and docs.
- Implemented `packages/ts/ashr-clone/src/runner.ts`: `AgentAdapter`, `AgentResult`, `LocalEvalRunner`, `BatchRunner`, `runAgentBatch`, `runCase`, `runBatch`, `runFile`, `runAgentFile`, `buildRunFixture`, `buildCloudRunFixture`, `loadAgentTarget`, `coerceRunnerAgentInput`, and `toA2JudgeRun`.
- Implemented `packages/ts/ashr-clone/src/runner-cli.ts`: `ashr-clone-runner` CLI for external TS agents, 30+ case batches, `maxWorkers >= 4`, timeout, fixture output, and fail-on-case-failure.
- Implemented `packages/ts/ashr-clone/src/dataset-adapter.ts`: `extractDatasetSource`, `datasetSourceToCases`, `caseFromSourceRun`, API-record loading/writing, and `replayFixtureFromSourceRun`.
- Implemented `packages/ts/ashr-clone/src/dataset-adapter-cli.ts`: `ashr-clone-dataset-adapter cases` and `replay-fixture`.
- Implemented `packages/ts/ashr-clone/src/trace.ts`: `TraceRecorder`, `TraceEvent`, VM stream frames, fixture build/validate/load/write, and VM stream replay projection.
- Implemented `examples/agents/mock_agent_ts.mjs`: TS mock agent compatible with the 30-case local calculator/echo smoke.
- Added tests: `packages/ts/ashr-clone/test/runner.test.mjs`, `dataset-adapter.test.mjs`, and `trace.test.mjs`.
- Updated docs: `packages/ts/ashr-clone/README.md`, `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/evidence/official_site_gaps.md`, `docs/a1/evidence/commands.md`, and `docs/evidence/worklog.md`.
- `npm install --package-lock-only --prefix packages/ts/ashr-clone`: up to date, 0 vulnerabilities.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 47 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/runner-cli.js --input docs/a1/evidence/local_agent_cases_30.json --output docs/evidence/private_refs/a1_ts_runner_run_30_smoke.json --agent examples/agents/mock_agent_ts.mjs:default --dataset-id a2-local-scenarios-ts --runner-id a1-ts-local-runner --run-id run_a1_ts_runner_30_smoke --max-workers 4 --timeout 5 --fixture-output docs/evidence/private_refs/a1_ts_runner_fixture_30_smoke.json --fail-on-case-failure`: completed 30 passed, 0 failed, 0 errored, 0 timed out, trace completeness 1.0.
- Private evidence paths created/updated: `docs/evidence/private_refs/a1_ts_runner_run_30_smoke.json`, `docs/evidence/private_refs/a1_ts_runner_fixture_30_smoke.json`, and `docs/evidence/private_refs/ashr_lab_usage_ts_python_parity_2026-07-04.png`.
- Real Ashr API calls: none. This process had no `ASHR_API_KEY` / `ASHR_LABS_API_KEY`; local key files were not read.

## 2026-07-04 TypeScript Cloud Queue And Five-Modality Envelope

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: success; `origin/dev/g3-a2-calibration` advanced to `91391a0 G3: add semantic judge risk tracking`.
- `pwd`; `git rev-parse --show-toplevel`; `git remote -v`; `gh repo view --json nameWithOwner,url,defaultBranchRef`; `gh pr list --state all --limit 30 --json ...`: repo root `C:/Users/33516/Documents/Ashr`, branch `codex/a1-local-sdk-runner`, remote `3351666087/ashr-codex-factory`, default branch `main`, PR #9 open/draft/clean at round start.
- `git status -sb --untracked-files=all`: tracked worktree clean at round start.
- Peer impact: `origin/dev/g3-a2-calibration` changed A2/G3 judge/report/worklog paths; no A1-owned conflict observed. Explorer-Chrome later noted remote `main` may advance to an A2/G3 merge; keep A1 changes staged separately.
- Env presence: `ASHR_API_KEY=false`, `ASHR_LABS_API_KEY=false`, `ASHR_LABS_BASE_URL=false`; no real hosted API calls were made, and local key files were not read.
- Top 10 scored enhancements: TS cloud queue/replay parity (implemented), five-modality `AgentInput`/request schema parity (implemented), TS cloud CLI fresh-setup loop (implemented), TS quota/state restore tests (implemented), TS media dry-run fixture with `video` (implemented), injected hosted quota/error fixture pack (deferred), real TS hosted read-only probe when env exists (blocked), public-safe hosted evidence bridge (deferred), one-command Python+TS smoke script (deferred), hosted dashboard counter calibration (blocked/unverified).
- Subagents: Bus-Auditor reported the in-progress TS patch was initially incomplete and required finishing `cloud-queue.ts`, helper functions, tests, docs, and full validation before staging. Explorer-Chrome verified TS docs accepted inputs include `text`, `audio`, `file`, `image`, and `video`; TS docs still omit `pollRun`, `listAgents`, `generate_images`, and `generate_videos` in the observed pass. Explorer-SDK/API failed due model capacity, so main thread covered that review locally.
- Implemented `packages/ts/ashr-clone/src/cloud-queue.ts`: `CloudQueueWorker`, `QueueRunRequest`, terminal statuses, deterministic replay ordering by `replay_order` / `batch_index`, queued/running/completed/failed/cancelled lifecycle execution, status polling, cancellation, and redacted failure handling.
- Implemented `packages/ts/ashr-clone/src/cloud-cli.ts`: `ashr-clone-cloud` commands `queue-run`, `replay-queued`, and `export-fixture`; repeated `--run-id`, generated `--run-count`, per-run fixture/result directories, restored-state fixture export, and singleton-output guardrails for batches.
- Extended `packages/ts/ashr-clone/src/index.ts`: five-modality `AgentInputPartType` including `video`, cloud state snapshot/restore, quota state serialization, queued run lifecycle methods, status history, fixture/state file writing, and deterministic clock option.
- Extended `packages/ts/ashr-clone/src/api-client.ts` and media fixture/docs so dry-run request schemas and summaries cover `text`, `audio`, `file`, `image`, and `video`; `generate_videos` is represented locally from Python docs while remaining an official TS-doc gap.
- Added `packages/ts/ashr-clone/test/cloud-queue.test.mjs` plus updated API/cloud/runner/runtime tests for five-modality coverage and CLI state replay.
- Updated docs: `packages/ts/ashr-clone/README.md`, `docs/a1/README.md`, `docs/a1/sdk_field_map.md`, `docs/a1/api_calibration/README.md`, `docs/a1/api_calibration/media_interface_request.json`, `docs/a1/schemas/agent_input.schema.json`, `docs/evidence/official_site_gaps.md`, this command log, and `docs/evidence/worklog.md`.
- `npm run build --prefix packages/ts/ashr-clone`: passed after completing TS cloud queue/helper files.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 50 Node tests passed.
- `npm install --package-lock-only --prefix packages/ts/ashr-clone`: up to date, 0 vulnerabilities.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/cloud-cli.js queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_ts_cloud_queue_state_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_queue_summary_30_smoke.json --tenant-id tenant_a1_ts_cloud_smoke --project-id project_a1_ts_cloud_smoke --dataset-id dataset_a1_ts_cloud_smoke --runner-id a1-ts-cloud-smoke --run-id run_a1_ts_cloud_002 --run-id run_a1_ts_cloud_001`: wrote ignored local TS cloud state with two queued 30-case runs, `dataset.create=1`, `run.submit=2`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js replay-queued --state-input docs/evidence/private_refs/a1_ts_cloud_queue_state_30_smoke.json --agent examples/agents/mock_agent_ts.mjs:default --tenant-id tenant_a1_ts_cloud_smoke --project-id project_a1_ts_cloud_smoke --fixture-output-dir docs/evidence/private_refs/a1_ts_cloud_replay_fixtures_30_smoke --run-output-dir docs/evidence/private_refs/a1_ts_cloud_replay_runs_30_smoke --summary-output docs/evidence/private_refs/a1_ts_cloud_replay_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_replayed_state_30_smoke.json --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: replayed two runs; each completed 30 passed, 0 failed, 0 errored, 0 timed out, 60 observations, status history `queued -> running -> completed`; quota used `dataset.create=1`, `run.submit=2`, `observation.write=120`.
- `node packages/ts/ashr-clone/dist/cloud-cli.js export-fixture --state-input docs/evidence/private_refs/a1_ts_cloud_replayed_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_smoke --project-id project_a1_ts_cloud_smoke --run-id run_a1_ts_cloud_001 --fixture-output docs/evidence/private_refs/a1_ts_cloud_exported_fixture_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_export_summary_30_smoke.json`: exported a completed restored-state fixture.
- `node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json`: planned Text/Audio/File/Image/Video dry-run, no key or network call.
- Real Ashr API calls: none this round because env keys were absent; no `.secrets`, desktop key file, or raw private evidence payload was read.

### 2026-07-05 follow-up after SDK/API review

- Explorer-SDK/API found cross-SDK drift: TS and A1 schema supported `video`, while Python SDK/default request-schema constants omitted it. Fixed `packages/sdk/ashr_clone/adapter.py`, `packages/sdk/ashr_clone/api_client.py`, and `services/runner/api_probe.py` so `text`, `audio`, `file`, `image`, and `video` are same-level Python/TS local envelope parts.
- Updated `tests/a1/test_api_client.py` and `tests/a1/test_cloud_api.py` to require video in media request schemas and preflight summaries.
- Added `ashr-clone-cloud run-agent-queued` to `packages/ts/ashr-clone/src/cloud-cli.ts`, mirroring Python's one-shot queued demo path with fixture/run/summary/state outputs, tenant/project/dataset display names, queue worker controls, `--no-timeout`, wait timeout, and fail-on-case-failure.
- Added `packages/ts/ashr-clone/test/cloud-queue.test.mjs` coverage for the one-shot CLI path.
- `npm run build --prefix packages/ts/ashr-clone; node --test packages/ts/ashr-clone/test/cloud-queue.test.mjs`: 5 passed.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_cloud_api.py -q -p no:cacheprovider`: 67 passed.

### 2026-07-05 final verification before staging

- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 52 Node tests passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 133 passed.
- `node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_one_shot_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_one_shot_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_one_shot_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_one_shot_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_one_shot --project-id project_a1_ts_cloud_one_shot --tenant-name "A1 TS Cloud One Shot Tenant" --project-name "A1 TS Cloud One Shot Project" --dataset-id dataset_a1_ts_cloud_one_shot --dataset-name "A1 TS Cloud One Shot Dataset" --runner-id a1-ts-cloud-one-shot --run-id run_a1_ts_cloud_one_shot --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure`: completed one 30-case queued TS run, wrote ignored fixture/run/summary/state evidence, and used quota `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `git diff --check`: exit 0 with CRLF warnings only.

## 2026-07-05 TS Full Parity Sprint Commands

```powershell
pwd
git rev-parse --show-toplevel
git remote -v
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
gh repo view --json nameWithOwner,defaultBranchRef,url
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,updatedAt,url
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
node packages/ts/ashr-clone/dist/cloud-cli.js run-agent --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_direct_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_direct_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_direct_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_direct_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_direct --project-id project_a1_ts_cloud_direct --tenant-name "A1 TS Cloud Direct Tenant" --project-name "A1 TS Cloud Direct Project" --dataset-id dataset_a1_ts_cloud_direct --dataset-name "A1 TS Cloud Direct Dataset" --runner-id a1-ts-cloud-direct --run-id run_a1_ts_cloud_direct --max-workers 4 --timeout 5 --fail-on-case-failure
node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_cloud_queued_fixture_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_cloud_queued_run_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_cloud_queued_summary_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_cloud_queued_state_30_smoke.json --tenant-id tenant_a1_ts_cloud_queued --project-id project_a1_ts_cloud_queued --tenant-name "A1 TS Cloud Queued Tenant" --project-name "A1 TS Cloud Queued Project" --dataset-id dataset_a1_ts_cloud_queued --dataset-name "A1 TS Cloud Queued Dataset" --runner-id a1-ts-cloud-queued --run-id run_a1_ts_cloud_queued --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure
```

Results:

- TypeScript: `npm test --prefix packages/ts/ashr-clone` passed with `133` Node test items and `133` passes.
- Python: `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed with `133 passed in 9.80s`.
- TS direct cloud `run-agent`: 30/30 cases passed, trace completeness `1`, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- TS queued cloud `run-agent-queued`: run completed with quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- Real Ashr API: not called in this sprint. Environment keys were not used or read from files; no secrets were written to logs or repo files.
```
## 2026-07-05 TS Schema Contract Commands

```powershell
pwd
git rev-parse --show-toplevel
git remote -v
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
gh pr list --state all --limit 20
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
node packages/ts/ashr-clone/dist/cloud-cli.js run-agent --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_direct_schema_fixture_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_direct_schema_summary_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_direct_schema_run_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_direct_schema_state_30_smoke.json --tenant-id tenant_a1_ts_schema_direct --project-id project_a1_ts_schema_direct --dataset-id dataset_a1_ts_schema_direct --runner-id a1-ts-schema-direct --max-workers 4 --timeout 5 --fail-on-case-failure
node packages/ts/ashr-clone/dist/cloud-cli.js run-agent-queued --input docs/a1/evidence/local_agent_cases_30.json --agent examples/agents/mock_agent_ts.mjs:default --fixture-output docs/evidence/private_refs/a1_ts_queued_schema_fixture_30_smoke.json --summary-output docs/evidence/private_refs/a1_ts_queued_schema_summary_30_smoke.json --run-output docs/evidence/private_refs/a1_ts_queued_schema_run_30_smoke.json --state-output docs/evidence/private_refs/a1_ts_queued_schema_state_30_smoke.json --tenant-id tenant_a1_ts_schema_queued --project-id project_a1_ts_schema_queued --dataset-id dataset_a1_ts_schema_queued --runner-id a1-ts-schema-queued --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30 --fail-on-case-failure
git diff --check
```

Results:

- TypeScript: `npm test --prefix packages/ts/ashr-clone` passed with `138` Node test items and `138` passes.
- Python: `python -B -m pytest tests/a1 -q -p no:cacheprovider` passed with `133 passed in 9.31s`.
- TS direct schema smoke: 30/30 cases passed, trace completeness `1`, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- TS queued schema smoke: completed, quota used `dataset.create=1`, `run.submit=1`, `observation.write=60`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Real Ashr API: not called; no key files or private payloads read or stored.
## 2026-07-05 Real API Batch Calibration Commands

```powershell
$env:ASHR_API_KEY = [Environment]::GetEnvironmentVariable('ASHR_API_KEY', 'User')
node packages/ts/ashr-clone/dist/probe.js init --execute --max-retries 0 --output docs/evidence/private_refs/a1_real_init_small_batch.json --print-record
node packages/ts/ashr-clone/dist/probe.js health-check --execute --max-retries 0 --output docs/evidence/private_refs/a1_real_health_small_batch.json --print-record
node packages/ts/ashr-clone/dist/probe.js list-agents --execute --max-retries 0 --output docs/evidence/private_refs/a1_real_list_agents_small_batch.json --print-record
node packages/ts/ashr-clone/dist/probe.js list-datasets --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_real_list_datasets_small_batch.json --print-record
node packages/ts/ashr-clone/dist/probe.js list-requests --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_real_list_requests_small_batch.json --print-record
node packages/ts/ashr-clone/dist/probe.js get-dataset --execute --max-retries 0 --dataset-id 883 --output docs/evidence/private_refs/a1_real_get_dataset_883_small_batch.json
node packages/ts/ashr-clone/dist/probe.js list-runs --execute --max-retries 0 --dataset-id 883 --limit 2 --output docs/evidence/private_refs/a1_real_list_runs_dataset_883_small_batch.json
node packages/ts/ashr-clone/dist/probe.js get-request --execute --max-retries 0 --request-id 580 --output docs/evidence/private_refs/a1_real_get_request_580_failed_media_small_batch.json
node packages/ts/ashr-clone/dist/probe.js get-request --execute --max-retries 0 --request-id 581 --output docs/evidence/private_refs/a1_real_get_request_581_completed_text_small_batch.json
node packages/ts/ashr-clone/dist/probe.js poll-request --execute --max-retries 0 --request-id 580 --poll-timeout 1 --poll-interval 1 --output docs/evidence/private_refs/a1_real_poll_request_580_failed_media_small_batch.json
node packages/ts/ashr-clone/dist/calibrate.js --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_dry_run.json --print-record
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_real_readonly.json --print-record
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --include-mutating --modality text --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_real_text_mutating.json --print-record
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
git diff --check
```

Results:

- Real read-only Ashr API calls succeeded for `init`, `keep_alive`, `list_agents`, `list_datasets`, `list_requests`, `get_dataset(883)`, `list_runs(dataset=883)`, `get_request(580)`, and `get_request(581)`, each with status_code `200` and attempts `1`.
- `poll_request(580)` produced a controlled failure record for an already failed media request and preserved only safe failure shape summaries.
- `ashr-clone-calibrate` dry-run manifest covered 10 steps including first-class `text`, `image`, `audio`, `file`, and `video` create-request plans.
- `ashr-clone-calibrate` real read-only small-batch manifest succeeded with 5/5 read steps and no raw key/payload in public evidence.
- Text-only mutating small-batch was attempted once and blocked by hosted quota; exact quota counts remain only in ignored private evidence, and no retry was attempted.
- Tests: TS `145/145`; Python A1 `133 passed`; `git diff --check` exit 0 with CRLF warnings only.

## A1 Python calibrator and evidence index - 2026-07-05T06:33:05Z

Commands:

``powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,isDraft,updatedAt,author
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
$env:ASHR_API_KEY = [Environment]::GetEnvironmentVariable('ASHR_API_KEY', 'User')
python -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_dry_run.json --print-record
python -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real_readonly.json --print-record
python -c "from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, write_private_evidence_index; patterns=['docs/evidence/private_refs/a1_real_*.json','docs/evidence/private_refs/a1_ts_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_calibration_*.json']; paths=[]; [paths.extend(Path('.').glob(pattern)) for pattern in patterns]; index=build_private_evidence_index(sorted(paths), label='a1-real-api-2026-07-05'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'error_kind_counts': index['error_kind_counts'], 'quota_block_count': index['quota_block_count']})"
git diff --check
``

Results:
- Python A1 tests: 144 passed.
- TypeScript tests: 145 passed.
- Python calibrator dry-run: planned, 10 steps, five modalities covered as first-class text/image/audio/file/video create-request plans.
- Python real read-only small-batch: ok, 5 read steps, response keys recorded under private refs.
- Public-safe evidence index: docs/a1/api_calibration/real_api_evidence_index.json, 61 records, quota block count 1.
- Secret policy: only environment presence/length was observed; raw API key was not printed, logged, or committed.

## A1 queue lease runtime and round2 API calibration - 2026-07-05T17:20:07Z

Commands:

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
gh pr list --state all --limit 30 --json number,title,state,headRefName,baseRefName,isDraft,updatedAt,author,url
python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
$env:ASHR_API_KEY = [Environment]::GetEnvironmentVariable('ASHR_API_KEY', 'User')
python -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round2_dry_run.json
python -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round2_real_readonly.json
python -B -m services.runner.api_probe get-dataset --execute --max-retries 0 --dataset-id 999999 --output docs/evidence/private_refs/a1_python_api_get_dataset_999999_round2_real.json
python -B -m services.runner.api_probe get-request --execute --max-retries 0 --request-id 999999 --output docs/evidence/private_refs/a1_python_api_get_request_999999_round2_real.json
python -c "from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, write_private_evidence_index; patterns=['docs/evidence/private_refs/a1_real_*.json','docs/evidence/private_refs/a1_ts_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_get_*_round2_real.json']; paths=[]; [paths.extend(Path('.').glob(pattern)) for pattern in patterns]; index=build_private_evidence_index(sorted(paths), label='a1-real-api-2026-07-06'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'function_counts': index['function_counts'], 'error_kind_counts': index['error_kind_counts'], 'quota_block_count': index['quota_block_count']})"
git diff --check
```

Results:
- Cloud API/CLI focused tests: 35 passed.
- Python A1 tests: 148 passed.
- TypeScript tests: 147 passed.
- Python dry-run calibration: planned, 10 steps, five modalities.
- Python real read-only calibration: ok, 5 read steps.
- Missing-resource probes: controlled Dataset not found and Request not found API errors.
- Public-safe evidence index: docs/a1/api_calibration/real_api_evidence_index.json, 67 records, quota block count 1.
- Secret policy: key was read from process environment only; raw key and private payloads were not staged.

## A1 TS/Python queue lease parity and readiness - 2026-07-06

Commands:

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
pwd
git rev-parse --show-toplevel
git remote -v
git status -sb
gh repo view --json nameWithOwner,url,defaultBranchRef
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,updatedAt,url,isDraft
git diff --stat origin/codex/a1-local-sdk-runner...origin/dev/g3-a2-calibration
git diff --name-only origin/codex/a1-local-sdk-runner...origin/dev/g3-a2-calibration
npm test --prefix packages/ts/ashr-clone -- --test-name-pattern "CloudQueueWorker|CloudApiService leases"
python -B -m pytest tests/a1/test_cloud_api.py::test_cloud_api_run_lease_heartbeat_and_owner_validation tests/a1/test_cloud_api.py::test_cloud_api_rejects_permanent_queue_lease tests/a1/test_cloud_api.py::test_cloud_queue_worker_renews_active_lease_and_blocks_double_replay tests/a1/test_cloud_api.py::test_cloud_queue_worker_replay_reclaims_expired_running_lease -q -p no:cacheprovider
python -B -c "import os; print({'ASHR_API_KEY_present': bool(os.environ.get('ASHR_API_KEY')), 'ASHR_LABS_API_KEY_present': bool(os.environ.get('ASHR_LABS_API_KEY'))})"
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B tests/integration/a1_readiness.py --real-readonly --summary-output docs/evidence/private_refs/a1_readiness_round4_real_readonly.json
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_round4_real_readonly.json
python -B -c "from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, write_private_evidence_index; patterns=['docs/evidence/private_refs/a1_real_*.json','docs/evidence/private_refs/a1_ts_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_get_*_round2_real.json','docs/evidence/private_refs/a1_readiness_calibration_*.json']; paths=[]; [paths.extend(Path('.').glob(pattern)) for pattern in patterns]; index=build_private_evidence_index(sorted(set(paths)), label='a1-real-api-2026-07-06-round4'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'function_counts': index['function_counts'], 'error_kind_counts': index['error_kind_counts'], 'quota_block_count': index['quota_block_count']})"
python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider
git diff --check
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_final_safety.json
```

Results:
- Peer impact: `origin/dev/g3-a2-calibration` advanced to `bf5028a A2: add external preflight schema`. Read-only diff showed A2/A3/Judge/Report changes plus A1-adjacent Python calibrator/evidence tests. These were not merged into this commit.
- `tmp/` and `output/` were added to local `.git/info/exclude` only; they are not staged or committed.
- Targeted TS queue command passed; because the npm script appends args after the test runner, it effectively ran the package suite and reported 152 Node test items passed.
- Targeted Python lease tests: 4 passed.
- Full Python A1 tests: 149 passed.
- Full TypeScript tests: 152 passed.
- Readiness matrix with real read-only Python calibrator: status ok, 6 steps, summary `docs/evidence/private_refs/a1_readiness_round4_real_readonly.json`.
- TS real read-only calibrator: `status=ok`, 5 read steps, 0 errors, output `docs/evidence/private_refs/a1_ts_api_calibration_manifest_round4_real_readonly.json`.
- Public-safe evidence index refreshed: 71 records, status counts `error=8`, `failed=1`, `ok=32`, `partial=1`, `planned=28`, quota block count 1.
- Evidence-index focused tests: 4 passed.
- Final readiness safety smoke: status ok, 2 steps.
- `git diff --check`: exit 0 with CRLF warnings only.
- Failed command: a bash heredoc inspection command failed under PowerShell; rerun with `python -B -c` succeeded.
- Real Ashr API: read-only only. `ASHR_API_KEY` was present in environment; raw key was not printed, stored, or committed. No mutating call was run in this round.

## A1 Python create_request preflight and round5 API calibration - 2026-07-06

Commands:

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
pwd
git rev-parse --show-toplevel
git remote -v
git status -sb --untracked-files=all
gh repo view
gh pr list --state all
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_dry_run.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_readonly.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --include-mutating --modality text --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_text_mutation.json
python -B -c "import json; from pathlib import Path; paths=['docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_readonly.json','docs/evidence/private_refs/a1_python_api_calibration_manifest_round5_real_text_mutation.json']; [print(p, json.loads(Path(p).read_text()).get('status'), json.loads(Path(p).read_text()).get('summary'), json.loads(Path(p).read_text()).get('errors')) for p in paths]"
python -B -c "from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, write_private_evidence_index; patterns=['docs/evidence/private_refs/a1_real_*.json','docs/evidence/private_refs/a1_ts_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_get_*_round2_real.json','docs/evidence/private_refs/a1_readiness_calibration_*.json']; paths=[]; [paths.extend(Path('.').glob(pattern)) for pattern in patterns]; index=build_private_evidence_index(sorted(set(paths)), label='a1-real-api-2026-07-06-round5-python-preflight'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'function_counts': index['function_counts'], 'error_kind_counts': index['error_kind_counts'], 'quota_block_count': index['quota_block_count']})"
python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round5_final_safety.json
git diff --check
Select-String -Path packages/sdk/ashr_clone/api_client.py,packages/sdk/ashr_clone/calibrate.py,services/runner/api_probe.py,tests/a1/test_api_client.py,tests/a1/test_python_calibrator.py,docs/a1/explorer_chrome.md,docs/a1/api_calibration/real_api_evidence_index.json -Pattern 'tp_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+|ashr_live_[A-Za-z0-9_-]+' -AllMatches | Select-Object Path,LineNumber,Line
```

Results:
- Focused Python API client/calibrator tests: 60 passed.
- Full Python A1 tests: 154 passed.
- Full TypeScript SDK tests: 152 passed.
- Python dry-run calibration: planned, 10 steps, five first-class modalities, no quota block.
- Python real read-only calibration: ok, 5 read steps, 0 errors.
- Python text-only mutating calibration: partial, 5 read steps ok, one `create_request` quota block; exact quota counts remain only in ignored private evidence, and no retry or media mutating calls were run.
- Public-safe evidence index refreshed at `docs/a1/api_calibration/real_api_evidence_index.json`: 75 records, status counts `error=9`, `failed=1`, `ok=33`, `partial=2`, `planned=29`, quota block count 2.
- Evidence index schema tests: 4 passed.
- Final readiness safety smoke: ok, 2 steps, output `docs/evidence/private_refs/a1_readiness_round5_final_safety.json`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret scan: matches were intentional synthetic test-token fixtures; no real API key was printed or written to tracked docs/code/evidence index.
- Growth-Auditor quota-detail follow-up: public evidence index quota summaries now use `*_present` booleans and generic quota-block text; tracked public docs/index scan found no exact hosted quota count phrase or numeric `used/requested/remaining` tuple.
- One failed inspection command used bash-style `\n` in a PowerShell `python -c` string and produced a SyntaxError; it was rerun with a PowerShell-compatible one-liner.

## A1 round6 risk field-map and evidence linter commands - 2026-07-06

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb --untracked-files=all
gh pr list --state all --limit 30
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_evidence_index.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round6_real_readonly.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, build_response_field_map, validate_public_evidence_index, write_private_evidence_index; patterns=['docs/evidence/private_refs/a1_real_*.json','docs/evidence/private_refs/a1_ts_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_calibration_*.json','docs/evidence/private_refs/a1_python_api_get_*_round2_real.json','docs/evidence/private_refs/a1_readiness_calibration_*.json']; paths=[]; [paths.extend(Path('.').glob(pattern)) for pattern in patterns]; index=build_private_evidence_index(sorted(set(paths)), label='a1-real-api-2026-07-06-round6-cost-field-map'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); field_map=build_response_field_map(index); Path('docs/a1/api_calibration/real_api_response_field_map.json').write_text(json.dumps(field_map, indent=2, sort_keys=True)+'\n', encoding='utf-8'); print({'records': index['total_records'], 'issues': len(validate_public_evidence_index(index)), 'functions': len(field_map['functions']), 'quota_block_count': index['quota_block_count']})"
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round6_safety.json
git diff --check
```

Results:
- Python focused tests: 59 passed.
- TypeScript package tests: 152 passed.
- Python real read-only round6 calibration: ok, 5 read steps, 0 errors, output `docs/evidence/private_refs/a1_python_api_calibration_manifest_round6_real_readonly.json`.
- Public evidence index regenerated: 76 records, 10 functions in `docs/a1/api_calibration/real_api_response_field_map.json`, lint issues 0, quota block count 2.
- Python A1 full tests: 158 passed after Growth-Auditor P1 linter fix.
- Public evidence linter regression: `tests/a1/test_evidence_index.py` now covers raw `tp_`, `sk-`, `Bearer`, and `ashr_live_` detection before redaction; current public index lint issues remain 0.
- Readiness safety smoke: ok, output `docs/evidence/private_refs/a1_readiness_round6_safety.json`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Official docs check: Python public API reference loaded and still exposes Testing Platform and Observability products plus create/list/run methods. TypeScript public API reference returned an internal error in this pass; no fields were inferred from that failed page.

## A1 round7 main rebase, batch planner, TS evidence parity, and API refresh - 2026-07-06

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb --untracked-files=all
gh repo view --json nameWithOwner,url,defaultBranchRef
gh pr list --state all --limit 20 --json number,title,state,isDraft,headRefName,updatedAt,url
git rebase origin/main
python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_evidence_index.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B -m services.runner.api_probe plan-batch --request-file docs/a1/api_calibration/media_interface_request.json --allow-media-generation --allow-non-text-inputs --max-request-variations 1 --small-batch-size 1 --batch-size 3 --output docs/evidence/private_refs/a1_api_probe_batch_plan_round7_media.json
python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round7_dry_run.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_round7_real_readonly.json
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_ts_api_calibration_manifest_round7_real_readonly.json
python -B -m services.runner.api_probe plan-batch --request-file docs/a1/api_calibration/tiny_generation_request.json --quota-record docs/evidence/private_refs/a1_python_api_calibration_create-request-text_real.json --output docs/evidence/private_refs/a1_api_probe_batch_plan_round7_quota_stop.json
```

Results:
- Rebased A1 branch onto `origin/main`; conflict resolution kept the richer 200-record evidence index as base and regenerated A1 field-map artifacts.
- API probe batch planner added planning-only `plan-batch`, dry-run/small-batch/batch phase metadata, text-first media sequencing, quota/reset stop-go gates, and create-request dry-run plan attachment.
- Python evidence helpers now include merge-safe public quota normalization plus JSON/Markdown response field-map reports. TypeScript evidence parity now includes public linter and response field-map builder.
- Chrome read-only check reached logged-in Usage view and confirmed `Usage`, `Images`, `Audio`, and `Files` counters were visible. Exact counter values remain only in ignored private evidence at `docs/evidence/private_refs/a1_chrome_official_usage_round7.json`.
- Python dry-run calibration: planned, 10 steps, five modalities, estimated calls 17.
- Python real read-only calibration: ok, 5 read steps.
- TypeScript real read-only calibration: ok, 5 read steps.
- Quota-stop planner: blocked, based on prior private `create_request` quota record. No real paid mutating call was run this round because reset evidence was absent.
- Public evidence index regenerated at 323 records, 15 response-field functions, quota block count 41, lint issues 0.
- Focused Python API/evidence tests: 65 passed. TypeScript package tests: 153 passed.
- Full Python A1 tests: 163 passed.
- Readiness safety smoke: ok, output `docs/evidence/private_refs/a1_readiness_round7_safety.json`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret-pattern scan over touched public files matched only historical synthetic/documentation references; no operational key material was found.

## A1 round8 mutating quota-gate hardening - 2026-07-06

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb --untracked-files=all
gh pr list --state all --limit 20 --json number,title,state,isDraft,headRefName,updatedAt,url
python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider
python -B -m py_compile services/runner/api_probe.py tests/a1/test_api_client.py
python -B -m services.runner.api_probe list-requests --execute --limit 1 --output docs/evidence/private_refs/a1_api_list_requests_round8_real.json
```

Results:
- `services.runner.api_probe` now requires mutating `--execute` to provide `--quota-gate-record` from `plan-batch` or an explicit `--allow-quota-override --quota-override-reason`.
- Missing gate and stop gate both block before API key lookup or client construction; audited override is covered by tests.
- Focused API-client tests: 59 passed.
- Python compile check passed.
- Official API read-only `list-requests` probe succeeded with status ok, attempts 1. Raw key was not printed or written.
- Public evidence index refreshed to 325 records, 15 response-field functions, quota block count 41, lint issues 0.
- Full Python A1 tests: 166 passed.
- TypeScript package tests: 153 passed.
- Readiness safety smoke: ok, output `docs/evidence/private_refs/a1_readiness_round8_safety.json`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret-pattern scan matched historical docs and synthetic test tokens only; no operational key material was found.

## A1 round9 repo-wide mutating quota-gate parity evidence draft superseded by final below - 2026-07-07

```powershell
git status -sb --untracked-files=all
rg -n "quota-gate|quotaGate|quota_gate|plan-batch|allow-quota|override reason|override_reason|mutating|create-request" services packages tests docs/a1 -S
rg -n -C 4 "enforce_mutating_quota_gate|extract_quota_gate|quota-gate-record|allow-quota-override|quota-override-reason|quota_stop_go|plan-batch" services/runner/api_probe.py tests/a1/test_api_client.py
rg -n -C 4 "quota-gate|quotaGate|allow-quota|quota override|allow-mutate|MUTATING_OPERATIONS|plan-batch|override" packages/ts/ashr-clone/src/probe.ts packages/ts/ashr-clone/test/probe.test.mjs packages/ts/ashr-clone/src/api-client.ts packages/ts/ashr-clone/test/api-client.test.mjs
python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
git diff -- packages/sdk/ashr_clone/calibrate.py
git diff -- packages/ts/ashr-clone/src/probe.ts
git diff -- packages/ts/ashr-clone/src/calibrate.ts
git diff -- tests/a1/test_python_calibrator.py packages/ts/ashr-clone/test/calibrate.test.mjs
python -B -m py_compile packages/sdk/ashr_clone/calibrate.py
python -B -m pytest tests/a1/test_python_calibrator.py -q -p no:cacheprovider
git diff --check
```

Results:
- Scope note: this evidence/docs worker only edited `docs/evidence/worklog.md` and `docs/a1/evidence/commands.md`. Code/test changes observed during this pass are peer-owned and were not reverted.
- Dirty peer files observed after validation started: `packages/sdk/ashr_clone/calibrate.py`, `packages/ts/ashr-clone/src/calibrate.ts`, `packages/ts/ashr-clone/src/probe.ts`, `packages/ts/ashr-clone/test/probe.test.mjs`, and `tests/a1/test_python_calibrator.py`.
- Python probe guard validation: `tests/a1/test_api_client.py` passed, 59 tests.
- Python calibrator validation: `packages/sdk/ashr_clone/calibrate.py` compiled, and `tests/a1/test_python_calibrator.py` passed, 13 tests.
- Historical draft observation: TypeScript validation was still in progress during the docs-only pass; the final section below supersedes this with passing results.
- `git diff --check`: exit 0 with CRLF warnings only.
- Operator error recorded: `python -B -m py_compile packages/sdk/ashr_clone/calibrate.py packages/ts/ashr-clone/src/probe.ts` was invalid because Python was pointed at a TypeScript file; it was replaced by a valid Python compile and TS `npm test`.
- No live API calls were made, no ignored private evidence files were opened, and no raw private evidence or API keys were printed.

Superseded placeholders:
- The final section below records the completed Python/TS validation, readiness smoke, public evidence refresh, linter, and secret scan.

## A1 round9 repo-wide money-grade quota gate final - 2026-07-07

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
pwd
git rev-parse --show-toplevel
git remote -v
git status -sb --untracked-files=all
gh repo view --json nameWithOwner,url,defaultBranchRef
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,author,updatedAt,url
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
$env:ASHR_API_KEY = [Environment]::GetEnvironmentVariable('ASHR_API_KEY', 'User'); $env:ASHR_LABS_API_KEY = [Environment]::GetEnvironmentVariable('ASHR_LABS_API_KEY', 'User'); python -B -m services.runner.api_probe list-requests --execute --limit 1 --output docs/evidence/private_refs/a1_api_list_requests_round9_real_readonly.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, build_response_field_map, merge_evidence_indices, validate_public_evidence_index, write_private_evidence_index, write_response_field_map_markdown; existing=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); fresh=build_private_evidence_index([Path('docs/evidence/private_refs/a1_api_list_requests_round9_real_readonly.json')], label='a1-real-api-2026-07-07-round9-quota-gate-parity-fresh'); index=merge_evidence_indices(existing, fresh, label='a1-real-api-2026-07-07-round9-quota-gate-parity'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); field_map=build_response_field_map(index); Path('docs/a1/api_calibration/real_api_response_field_map.json').write_text(json.dumps(field_map, indent=2, sort_keys=True)+'\n', encoding='utf-8'); write_response_field_map_markdown('docs/a1/api_calibration/real_api_response_field_map.md', field_map); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'functions': len(field_map['functions']), 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round9_safety.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; index=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records': index['total_records'], 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
git diff --check
Select-String -Path docs/a1/api_calibration/real_api_evidence_index.json,docs/a1/api_calibration/real_api_response_field_map.json,docs/a1/api_calibration/real_api_response_field_map.md,docs/a1/evidence/commands.md,docs/evidence/worklog.md,packages/sdk/ashr_clone/calibrate.py,packages/ts/ashr-clone/src/calibrate.ts,packages/ts/ashr-clone/src/probe.ts,packages/ts/ashr-clone/test/calibrate.test.mjs,packages/ts/ashr-clone/test/probe.test.mjs,services/runner/api_probe.py,tests/a1/test_api_client.py,tests/a1/test_python_calibrator.py -Pattern 'tp_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+|ashr_live_[A-Za-z0-9_-]+' -AllMatches | Select-Object Path,LineNumber,Line
```

Results:
- Repo-wide mutating quota gate parity is implemented for Python runner, Python calibrator, TS probe, and TS calibrator.
- `plan-batch` without quota/reset evidence now produces a conservative wait/block state; no-evidence `decision=go` records are rejected before API key/client lookup.
- Override reason persistence is covered in Python and TS emitted evidence.
- Focused Python quota-gate tests: 76 passed.
- TypeScript package tests: 161 passed.
- Real Ashr API read-only probe: `list-requests`, status ok, attempts 1, private evidence at `docs/evidence/private_refs/a1_api_list_requests_round9_real_readonly.json`.
- Public evidence index refreshed merge-safely: 326 records, 15 response-field functions, quota block count 41, lint issues 0.
- Full Python A1 tests: 175 passed.
- Readiness safety smoke: ok, output `docs/evidence/private_refs/a1_readiness_round9_safety.json`.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret scan matches are historical docs/synthetic test tokens only; no operational API key was printed or written.
- Chrome/docs read-only calibration this round confirmed logged-in Usage labels and Python SDK overview product boundaries; exact usage counts remain private only.

## A1 round10 quota gate schema, validator, TTL, and request binding final - 2026-07-07

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb --untracked-files=all
git remote -v
gh repo view --json nameWithOwner,url,defaultBranchRef
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,updatedAt,url
Get-Content -Path docs/evidence/worklog.md -Tail 120
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 3 --output docs/evidence/private_refs/a1_python_api_calibration_round10_readonly_real.json
npm run build --prefix packages/ts/ashr-clone
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 3 --output docs/evidence/private_refs/a1_ts_api_calibration_round10_readonly_real.json
python -B -m services.runner.api_probe validate-gate --target-operation create-request --quota-gate-record docs/evidence/private_refs/a1_api_probe_batch_plan_round7_quota_stop.json --quota-gate-ttl-seconds 0 --output docs/evidence/private_refs/a1_api_validate_gate_round10_quota_stop.json
# first request-bound proof attempt failed because PowerShell Set-Content wrote UTF-8 BOM; rerun used UTF8Encoding(false)
python -B -m services.runner.api_probe plan-batch --target-operation create-request --request-file docs/evidence/private_refs/a1_round10_gate_request_original.json --quota-record docs/evidence/private_refs/a1_python_api_calibration_round10_readonly_real.json --output docs/evidence/private_refs/a1_api_probe_batch_plan_round10_request_bound.json
python -B -m services.runner.api_probe validate-gate --target-operation create-request --request-file docs/evidence/private_refs/a1_round10_gate_request_original.json --quota-gate-record docs/evidence/private_refs/a1_api_probe_batch_plan_round10_request_bound.json --output docs/evidence/private_refs/a1_api_validate_gate_round10_request_bound_ok.json
python -B -m services.runner.api_probe validate-gate --target-operation create-request --request-file docs/evidence/private_refs/a1_round10_gate_request_changed.json --quota-gate-record docs/evidence/private_refs/a1_api_probe_batch_plan_round10_request_bound.json --output docs/evidence/private_refs/a1_api_validate_gate_round10_request_bound_mismatch.json
python -B -m py_compile services/runner/api_probe.py tests/a1/test_api_client.py packages/sdk/ashr_clone/calibrate.py tests/a1/test_python_calibrator.py
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round10_safety.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; index=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records': index['total_records'], 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
git diff --check
Select-String -Path docs/a1/evidence/commands.md,docs/evidence/worklog.md,docs/a1/schemas/api_probe_quota_gate.schema.json,packages/sdk/ashr_clone/calibrate.py,packages/ts/ashr-clone/src/calibrate.ts,packages/ts/ashr-clone/src/probe.ts,packages/ts/ashr-clone/test/calibrate.test.mjs,packages/ts/ashr-clone/test/probe.test.mjs,services/runner/api_probe.py,tests/a1/test_api_client.py,tests/a1/test_python_calibrator.py -Pattern 'tp_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+|ashr_live_[A-Za-z0-9_-]+' -AllMatches
```

Results:
- Added quota gate schema at `docs/a1/schemas/api_probe_quota_gate.schema.json` with id `https://ashr.clone.local/schemas/api_probe_quota_gate.schema.json`.
- Python probe validator entry point: `services.runner.api_probe validate-gate`; mutating execute calls the same validator before API key/client lookup.
- Python/TS TTL default is `86400`; `--quota-gate-ttl-seconds 0` disables stale-age checks.
- Target binding fields include `target_operation`, `created_at`, `target_binding.fingerprint`, `request_fingerprint`, `request_input_schema_fingerprint`, `request_input_schema_source`, `allow_media_generation`, `allow_non_text_inputs`, `max_request_variations`, `small_batch_size`, `batch_size`, and `modalities`.
- Same-operation wrong request payload now fails with `target_binding_mismatch` before API key lookup.
- Python and TS calibrators now enforce target `create-request`, TTL, modality binding, and request fingerprint binding.
- Real Ashr API read-only calibration succeeded in both SDKs: Python and TS each ran 5 read steps, 0 mutating steps, estimated calls 7, status ok.
- Private real API evidence paths: `docs/evidence/private_refs/a1_python_api_calibration_round10_readonly_real.json` and `docs/evidence/private_refs/a1_ts_api_calibration_round10_readonly_real.json`.
- Response keys observed from real read-only calibration: `init` -> `features, notes, status, tenant, user`; `health-check` -> `db, message, status`; `list-agents` -> `_user, agents, status`; `list-datasets` -> `_user, datasets, next_cursor, status`; `list-requests` -> `_user, next_cursor, requests, status`.
- Chrome read-only Usage check confirmed logged-in dashboard quota labels: `Images 0 of 100`, `Audio 0 of 200`, `Files 1 of 100`.
- Chrome docs check confirmed Python SDK overview: Testing Platform, Observability, EvalRunner, RunBuilder, Agent, `client.trace()`, Span, Generation, VM Integration, and `pip install ashr-labs`.
- Focused Python tests: 90 passed.
- TypeScript package tests: 168 passed.
- Full Python A1 suite: 189 passed.
- Readiness smoke: ok, `docs/evidence/private_refs/a1_readiness_round10_safety.json`.
- Public evidence linter: 326 records, quota block count 41, lint issues 0.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret scan matched historical docs wording and intentional synthetic test strings only; no operational API key was printed or written.
- No mutating paid Ashr API call was run in this round; all official API calls were read-only.

## A1 round11 TypeScript standalone plan-batch / validate-gate parity - 2026-07-07

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
pwd
git rev-parse --show-toplevel
git status -sb --untracked-files=all
git remote -v
gh repo view --json nameWithOwner,defaultBranchRef,url
gh pr list --state all --limit 30 --json number,title,headRefName,baseRefName,state,author,updatedAt,url
Get-Content -Path docs/evidence/worklog.md -Tail 220
Get-Content -Path packages/ts/ashr-clone/src/probe.ts
Get-Content -Path packages/ts/ashr-clone/test/probe.test.mjs
npm run build --prefix packages/ts/ashr-clone
npm test --prefix packages/ts/ashr-clone
Get-ChildItem Env:ASHR_API_KEY | ForEach-Object { "ASHR_API_KEY=present(length=$($_.Value.Length))" }
node packages/ts/ashr-clone/dist/probe.js list-agents --output docs/evidence/private_refs/a1_ts_api_list_agents_round11_dry_run.json
node packages/ts/ashr-clone/dist/probe.js list-datasets --limit 1 --output docs/evidence/private_refs/a1_ts_api_list_datasets_round11_dry_run.json
node packages/ts/ashr-clone/dist/probe.js list-requests --limit 1 --output docs/evidence/private_refs/a1_ts_api_list_requests_round11_dry_run.json
node packages/ts/ashr-clone/dist/probe.js plan-batch --target-operation create-request --request-file docs/a1/api_calibration/media_interface_request.json --allow-media-generation --allow-non-text-inputs --max-request-variations 1 --small-batch-size 1 --batch-size 3 --output docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_media_noquota.json
node packages/ts/ashr-clone/dist/probe.js list-agents --execute --output docs/evidence/private_refs/a1_ts_api_list_agents_round11_real_readonly.json
node packages/ts/ashr-clone/dist/probe.js list-datasets --execute --limit 1 --output docs/evidence/private_refs/a1_ts_api_list_datasets_round11_real_readonly.json
node packages/ts/ashr-clone/dist/probe.js list-requests --execute --limit 1 --output docs/evidence/private_refs/a1_ts_api_list_requests_round11_real_readonly.json
node packages/ts/ashr-clone/dist/probe.js plan-batch --target-operation create-request --request-file docs/a1/api_calibration/tiny_generation_request.json --quota-record docs/evidence/private_refs/a1_ts_api_list_requests_round11_real_readonly.json --output docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_request_bound.json
node packages/ts/ashr-clone/dist/probe.js validate-gate --target-operation create-request --request-file docs/a1/api_calibration/media_interface_request.json --quota-gate-record docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_media_noquota.json --output docs/evidence/private_refs/a1_ts_api_validate_gate_round11_media_noquota.json
node packages/ts/ashr-clone/dist/probe.js validate-gate --target-operation create-request --request-file docs/a1/api_calibration/media_interface_request.json --allow-media-generation --allow-non-text-inputs --max-request-variations 1 --small-batch-size 1 --batch-size 3 --quota-gate-record docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_media_noquota.json --output docs/evidence/private_refs/a1_ts_api_validate_gate_round11_media_noquota_matched.json
node packages/ts/ashr-clone/dist/probe.js validate-gate --target-operation create-request --request-file docs/a1/api_calibration/tiny_generation_request.json --quota-gate-record docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_request_bound.json --output docs/evidence/private_refs/a1_ts_api_validate_gate_round11_request_bound.json
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round11_safety.json
python -B -m py_compile services/runner/api_probe.py tests/a1/test_api_client.py
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, build_response_field_map, merge_evidence_indices, validate_public_evidence_index, write_private_evidence_index, write_response_field_map_markdown; existing=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); paths=[Path('docs/evidence/private_refs/a1_ts_api_list_agents_round11_real_readonly.json'),Path('docs/evidence/private_refs/a1_ts_api_list_datasets_round11_real_readonly.json'),Path('docs/evidence/private_refs/a1_ts_api_list_requests_round11_real_readonly.json'),Path('docs/evidence/private_refs/a1_ts_api_probe_batch_plan_round11_request_bound.json'),Path('docs/evidence/private_refs/a1_ts_api_validate_gate_round11_request_bound.json'),Path('docs/evidence/private_refs/a1_ts_api_validate_gate_round11_media_noquota_matched.json'),Path('docs/evidence/private_refs/a1_ts_api_validate_gate_round11_media_noquota.json')]; fresh=build_private_evidence_index(paths, label='a1-real-api-2026-07-07-round11-ts-probe-parity-fresh'); index=merge_evidence_indices(existing, fresh, label='a1-real-api-2026-07-07-round11-ts-probe-parity'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', index); field_map=build_response_field_map(index); Path('docs/a1/api_calibration/real_api_response_field_map.json').write_text(json.dumps(field_map, indent=2, sort_keys=True)+'\n', encoding='utf-8'); write_response_field_map_markdown('docs/a1/api_calibration/real_api_response_field_map.md', field_map); print({'records': index['total_records'], 'status_counts': index['status_counts'], 'functions': len(field_map['functions']), 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; index=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records': index['total_records'], 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
git diff --check
Select-String -Path docs/a1/api_calibration/real_api_evidence_index.json,docs/a1/api_calibration/real_api_response_field_map.json,docs/a1/api_calibration/real_api_response_field_map.md,docs/a1/evidence/commands.md,docs/a1/evidence/round11_growth_auditor.md,docs/a1/evidence/round11_reviewer_test_matrix.md,docs/a1/evidence/round11_ts_probe_parity_checklist.md,docs/evidence/worklog.md,packages/ts/ashr-clone/src/api-client.ts,packages/ts/ashr-clone/src/probe.ts,packages/ts/ashr-clone/test/probe.test.mjs -Pattern 'tp_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+|ashr_live_[A-Za-z0-9_-]+' -AllMatches | Select-Object Path,LineNumber,Line
```

Results:
- TS probe now has standalone `plan-batch` and `validate-gate` parity with Python for local gate generation/validation.
- TypeScript package tests: 172 passed.
- Python A1 tests: 189 passed.
- Readiness safety smoke: ok, output `docs/evidence/private_refs/a1_readiness_round11_safety.json`.
- Real Ashr API read-only TS probes succeeded: `list-agents`, `list-datasets --limit 1`, and `list-requests --limit 1`, each status ok, attempts 1, status code 200.
- Chrome read-only Usage page confirmed logged-in labels for Usage, Images, Audio, Files, and Upgrade; docs overview confirmed Python SDK / Testing Platform / Observability / EvalRunner / RunBuilder / Agent / `client.trace` / Span / Generation / VM Integration.
- Public evidence index refreshed to 333 records, 16 response-field functions, quota block count 41, lint issues 0.
- `git diff --check`: exit 0 with CRLF warnings only.
- Secret scan matches were historical docs/pattern descriptions plus an intentional synthetic TS test-token fixture; no operational API key was printed or written.
- Failed point preserved: validation of the media no-quota gate without matching media flags and `--batch-size 3` failed with `target_binding_mismatch`; rerun with matching arguments passed.
- No mutating paid Ashr API call was executed; the request-bound gate from real read-only evidence remained blocked because no quota/reset go evidence was present.


## A1 round12 private API evidence guard - 2026-07-07

```powershell
pwd
git rev-parse --show-toplevel
git remote -v
git status -sb --untracked-files=all
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git branch -vv
gh repo view --json nameWithOwner,defaultBranchRef,url
gh pr list --state all --limit 20 --json number,title,state,headRefName,baseRefName,updatedAt,url
python -B -m services.runner.api_probe list-requests --execute --limit 1 --output docs/evidence/private_refs/a1_api_list_requests_round12_real_readonly.json
node packages/ts/ashr-clone/dist/probe.js list-requests --execute --limit 1 --output docs/evidence/private_refs/a1_ts_api_list_requests_round12_real_readonly.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_python_api_calibration_round12_readonly_real.json
node packages/ts/ashr-clone/dist/calibrate.js --execute --small-batch --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_ts_api_calibration_round12_readonly_real.json
python -B -m pytest tests/a1/test_api_client.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round12_safety.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; index=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records': index['total_records'], 'quota_block_count': index['quota_block_count'], 'lint_issues': len(validate_public_evidence_index(index))})"
git diff --check
```

Results:
- Focused Python private-output guard tests: `96 passed`.
- Full Python A1 suite: `195 passed`.
- TypeScript package tests: `179 passed`.
- Readiness safety smoke: status ok, private output `docs/evidence/private_refs/a1_readiness_round12_safety.json`.
- Real read-only API calibration: Python probe ok, TS probe ok, Python calibrator ok, TS calibrator ok; all outputs under `docs/evidence/private_refs`.
- Public evidence index after merge: 337 records, 16 response-field functions, quota block count 41, lint issues 0.
- Chrome retry after user opened Chrome failed at plugin runtime setup with `failed to write kernel assets: ??????????? (os error 3)`; no Ashr key was entered into Chrome or logs.
- `git diff --check`: exit 0 with CRLF warnings only after whitespace cleanup.


## 2026-07-07 Round13 A1 output policy and frontend mirror calibration

Baseline:
- Branch `codex/a1-local-sdk-runner` was synced with origin after Round12 push `44e22a6`.
- Peer update observed on `origin/dev/g3-a2-calibration`; no A2/A3 files were staged in this A1 round.
- Untracked `recon/` and `tools/` remain local reference artifacts and are not part of the commit.

20 growth points considered:
1. output_policy in Python probe; 2. output_policy in Python calibrator; 3. output_policy in TS probe; 4. output_policy in TS calibrator; 5. protected stdout policy tests; 6. synthetic override audit metadata; 7. repo-root private path metadata; 8. frontend mirror scan; 9. media parity labels; 10. Usage/nav labels; 11. TS/Python output_policy parity tests; 12. public-safe mirror evidence; 13. full A1 pytest; 14. full TS test; 15. readiness smoke; 16. public evidence lint; 17. secret scan; 18. Growth-Auditor review; 19. Reviewer P1 follow-up; 20. next-round frontend field map.

Implemented:
- Added `output_policy` metadata to Python/TS API probe records and Python/TS calibration manifests.
- `output_policy` records `schema_version`, `private_output_required`, `allow_nonprivate_output`, `nonprivate_output_override_used`, `output_is_private`, `sink`, `private_root`, `resolved_under_repo`, and `full_record_stdout_blocked`.
- Added tests proving dry-run nonprotected records, protected synthetic overrides, and calibrator manifests expose safe output policy metadata.
- Read-only scanned `C:/Users/33516/Desktop/Ashr_frontend_mirror_20260707_125507.zip` via `%TEMP%` and wrote public-safe summary `docs/a1/evidence/round13_frontend_mirror_findings.md`.

Validation so far:
- Focused Python probe/calibrator tests: `97 passed`.
- TypeScript package tests: `180 passed`.

Known gaps:
- Final validation: Python A1 full 196 passed, TS package 180 passed, readiness ok, public evidence lint 0, git diff check ok; secret scan only matched historical/synthetic tokens. Need Growth-Auditor follow-up and commit/push.


Growth-Auditor Round13 follow-up:
- P0 next: promote `output_policy` into a formal schema/readiness contract, aggregate it in public evidence index, and block unsafe public summaries from real nonprivate override records.
- P0 next: govern frontend mirror outputs through public-safe mirror indexes instead of committing raw `recon/`/zip artifacts.
- P0 next: convert real API evidence into a commercial capability matrix: local-only / real-read verified / mutating verified / quota-blocked / frontend-mirrored.
- P1 next: add `--nonprivate-output-reason`, stronger real execute override friction, official mirror diffing, and real API error taxonomy.
- Current round remains valid: output_policy metadata and frontend mirror findings move A1 toward enterprise evidence governance, but do not complete the long-running commercial goal.


## 2026-07-07 Round14 A1 evidence contract and frontend mirror index

Baseline:
- Continued on `codex/a1-local-sdk-runner` after Round13 push `726881b`.
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` completed; untracked `recon/` and `tools/` remain unstaged local references.

20 A1 growth points considered:
1. output_policy schema; 2. evidence index output_policy counts; 3. unsafe real nonprivate override blocker; 4. schema test; 5. public index refresh; 6. frontend mirror safe index; 7. frontend mirror schema; 8. mirror secret policy test; 9. mirror media labels; 10. mirror API entrypoint; 11. mirror lifecycle labels; 12. readiness smoke; 13. Python full regression; 14. TS full regression; 15. public evidence lint; 16. diff check; 17. secret scan; 18. Growth-Auditor review; 19. Worker-Mirror design alignment; 20. next-round commercial capability matrix.

Implemented:
- Added `docs/a1/schemas/output_policy.schema.json`.
- Extended `docs/a1/schemas/evidence_index.schema.json` with `output_policy_counts`.
- Updated `packages/sdk/ashr_clone/evidence.py` to preserve public-safe output policy metadata, aggregate output-policy counts, and flag unsafe real nonprivate output overrides.
- Refreshed `docs/a1/api_calibration/real_api_evidence_index.json` and response field map artifacts; historical records are counted as `output_policy_counts.missing=337` until regenerated from newer private evidence.
- Added `docs/a1/frontend_mirror/frontend_mirror_index.json` and `docs/a1/frontend_mirror/index.schema.json` as a public-safe index derived from the desktop frontend mirror zip without committing raw mirror files.
- Added `tests/a1/test_frontend_mirror_index.py` and expanded evidence-index tests.

Validation:
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 199 passed.
- `npm test --prefix packages/ts/ashr-clone`: 180 passed.
- `python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round14_contracts.json`: ok.
- Public evidence lint: 337 records, output_policy_counts present, lint issues 0.
- `git diff --check`: ok.

Growth-Auditor / Worker-Mirror follow-up:
- P0 remaining: turn output_policy into readiness gate across A2/A3, add stale/legacy evidence scanner, and expand frontend mirror safe index into route/assets/function-domain structure.
- P0 remaining: build commercial capability matrix from local-only / real-read verified / mutating verified / quota-blocked / frontend-mirrored evidence.
- Worker-Mirror recommended richer `frontend_mirror_index.v1`; this round lands an MVP public-safe index and tests, with full route/assets/domain expansion next.

## Round14 final hardening addendum - 2026-07-07

```powershell
python -B -m pytest tests/a1/test_evidence_index.py -q -p no:cacheprovider
python -B -m pytest tests/a1/test_frontend_mirror_index.py tests/a1/test_evidence_index.py -q -p no:cacheprovider
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round14_contracts_final.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; index=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records': index['total_records'], 'output_policy_counts': index.get('output_policy_counts'), 'lint_issues': len(validate_public_evidence_index(index))})"
git diff --check
```

Results:
- Focused frontend/evidence tests: 15 passed.
- Python A1 full suite: 202 passed.
- TypeScript package suite: 180 passed.
- Readiness smoke: ok, private summary at `docs/evidence/private_refs/a1_readiness_round14_contracts_final.json` (not committed).
- Public evidence index: 337 records, extended output policy counts present, lint issues 0.
- Diff whitespace check: ok.

## Round15 enterprise SaaS control plane expansion - 2026-07-07

```powershell
Get-ChildItem Env:ASHR_API_KEY, Env:ASHR_LABS_API_KEY -ErrorAction SilentlyContinue | ForEach-Object { "$($_.Name)=present(length=$($_.Value.Length))" }
python -B -m services.runner.api_probe health-check --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_round15_health-check_real_20260707_171150.json
python -B -m services.runner.api_probe list-datasets --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_round15_list-datasets_real_20260707_171150.json
python -B -m services.runner.api_probe list-runs --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_round15_list-runs_real_20260707_171150.json
python -B -m services.runner.api_probe list-requests --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_round15_list-requests_real_20260707_171150.json
python -B -m services.runner.api_probe list-agents --execute --max-retries 0 --limit 2 --output docs/evidence/private_refs/a1_round15_list-agents_real_20260707_171150.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import build_private_evidence_index, merge_evidence_indices, write_private_evidence_index, validate_public_evidence_index; existing=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); paths=sorted(Path('docs/evidence/private_refs').glob('a1_round15_*_real_20260707_171150.json')); fresh=build_private_evidence_index(paths,label='a1-round15-real-readonly'); merged=merge_evidence_indices(existing,fresh,label='a1-real-api-2026-07-07-round15-saas-control-plane'); write_private_evidence_index('docs/a1/api_calibration/real_api_evidence_index.json', merged, strict_public=True); print({'records': merged['total_records'], 'fresh': fresh['total_records'], 'output_policy_counts': merged['output_policy_counts'], 'lint_issues': len(validate_public_evidence_index(merged))})"
python -B -m pytest tests/a1/test_commercial_control_plane.py tests/a1/test_saas_control_plane.py tests/a1/test_capability_matrix.py tests/a1/test_legacy_evidence_scanner.py -q -p no:cacheprovider
```

Results:
- Env check recorded presence/length only; raw key was not printed or written.
- Real read-only probes: 5 ok records written to ignored private refs.
- Public evidence index: 342 records, 5 output-policy-present private records, lint issues 0.
- Focused SaaS/commercial tests: 13 passed.

## Round15 final validation and strategy alignment - 2026-07-07

```powershell
git show origin/main:docs/strategy/large-saas-a1-a2-a3-full-plan.md | Select-Object -First 260
python -B -m pytest tests/a1 -q -p no:cacheprovider
npm test --prefix packages/ts/ashr-clone
python -B tests/integration/a1_readiness.py --skip-python --skip-ts --skip-calibration --summary-output docs/evidence/private_refs/a1_readiness_round15_saas.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.evidence import validate_public_evidence_index; idx=json.loads(Path('docs/a1/api_calibration/real_api_evidence_index.json').read_text(encoding='utf-8')); print({'records':idx['total_records'],'output_policy_counts':idx['output_policy_counts'],'lint_issues':len(validate_public_evidence_index(idx))})"
git diff --check
```

Results:
- GitHub main strategy was read-only inspected; local branch did not contain the file yet.
- Python A1 full suite: 215 passed.
- TypeScript suite: 180 passed.
- A1 readiness: ok, private summary path ignored.
- Public evidence index: 342 records, 5 output-policy-present real read-only records, lint issues 0.
- Diff check: ok.

## Round21 official API field parity calibration plan - 2026-07-08

```powershell
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.calibrate import CalibrationArgs, build_field_parity_plan; plan=build_field_parity_plan(CalibrationArgs(include_mutating=True, modalities=('text',))); Path('docs/a1/api_calibration/official_api_field_parity_plan.json').write_text(json.dumps(plan, indent=2, sort_keys=True)+'\\n', encoding='utf-8'); print(json.dumps({'schema_version': plan['schema_version'], 'steps': plan['summary']['steps'], 'dry_run_calls': plan['summary']['estimated_calls_dry_run'], 'small_batch_calls': plan['summary']['estimated_calls_small_batch']}, sort_keys=True))"
python -B -m pytest tests/a1/test_python_calibrator.py -q -p no:cacheprovider
python -B -m packages.sdk.ashr_clone.calibrate --modality text --output docs/evidence/private_refs/a1_python_api_field_parity_dry_run_20260708.json
```

Results:
- Public field parity plan generated with schema `ashr.clone.api_field_parity_plan.v1`, 6 steps, zero dry-run API calls, and 9 estimated text-only small-batch calls.
- Focused calibrator tests: 24 passed.
- Read-only dry-run CLI completed with `status=planned`; no API key was required, no official API call was made, and full dry-run records were written only under ignored `docs/evidence/private_refs/`.

## Round22 multimodal calibrator guardrail refresh - 2026-07-08

```powershell
python -B -m pytest tests/a1/test_python_calibrator.py
python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --output docs/evidence/private_refs/a1_python_api_calibration_manifest_dry_run_local_check.json
python -B -c "import json; from pathlib import Path; from packages.sdk.ashr_clone.calibrate import CalibrationArgs, build_field_parity_plan; plan=build_field_parity_plan(CalibrationArgs(include_mutating=True)); Path('docs/a1/api_calibration/official_api_field_parity_plan.json').write_text(json.dumps(plan, indent=2, sort_keys=True)+'\\n', encoding='utf-8'); print(json.dumps({'schema_version': plan['schema_version'], 'steps': plan['summary']['steps'], 'modalities': plan['summary']['modalities'], 'dry_run_calls': plan['summary']['estimated_calls_dry_run'], 'small_batch_calls': plan['summary']['estimated_calls_small_batch']}, sort_keys=True))"
```

Results:
- Focused calibrator tests: 26 passed.
- Multimodal dry-run planned 10 steps across Text/Audio/File/Image/Video, estimated 17 small-batch calls, required no API key, and made no official API calls.
- Public field parity plan now covers all five modalities, keeps dry-run calls at zero, and records only request-shape/fingerprint metadata.
- Real mutating execution now requires explicit `--modality` selection before quota-gate validation can proceed; dry-run may still enumerate all modalities safely.

## Round23 public-safe official API evidence workflow - 2026-07-09

```powershell
python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest
python -B -m packages.sdk.ashr_clone.calibrate write-readiness-packet
python -B -m packages.sdk.ashr_clone.calibrate write-readiness-packet --evidence-index none --output docs/evidence/private_refs/a1_readiness_packet_public_safe_smoke.json
python -B -m pytest tests/a1/test_python_calibrator.py -q
```

Results:
- Public-safe manifest summary CLI completed with `status=missing` because the ignored private manifest was absent in this worktree.
- Readiness packet CLI completed with `status=ready`; it used tracked/public inputs, did not read desktop key files, and did not call the hosted API.
- The `--evidence-index none` readiness smoke also completed with `status=ready` to prove the artifact can be generated without private evidence context.
- Focused calibrator tests: 36 passed.

## Round24 lifecycle/quota parity and real read-only calibration - 2026-07-09

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
gh pr checks 27
go test ./...
go test ./...
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/a1 -q -p no:cacheprovider
python scripts/cl_guard.py hygiene
git diff --check
wsl -d Ubuntu-24.04-Ashr -- bash -lc "pwd; uname -a; command -v go || true; command -v python3 || true"
docker version --format '{{.Server.Version}}'
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_official_api_readonly_20260709_155325.json
python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_official_api_readonly_20260709_155325.json --output docs/a1/evidence/official_api_readonly_manifest_summary.json
python -B -m packages.sdk.ashr_clone.calibrate write-readiness-packet
python -B -m pytest tests/a1/test_python_calibrator.py tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_a1_foundation_migration_manifest.py tests/a1/test_ts_python_gap_matrix.py -q -p no:cacheprovider
python -B tests/a1/ts_python_parity_matrix.py --check
```

Results:
- PR #27 CL was green before this new slice: Plan/hygiene, Go, Python, TS, and summary passed; A3/Rust jobs were skipped by plan.
- Go SDK package and Go integration tests passed from their module roots.
- TS SDK suite passed with 321 tests, including SaaS route/scope, hosted client, CLI, and fixture parity.
- Python A1 suite passed with 336 tests after adding the migration manifest hook and route-scope hardening.
- `cl_guard.py hygiene` passed; `git diff --check` produced CRLF normalization warnings only.
- `Ubuntu-24.04-Ashr` WSL2 started successfully from the D-drive install and reached the current worktree; Python 3 was available. Docker daemon reported server version 29.6.1.
- Real official API read-only small batch completed with status `ok`: 5 read steps, 0 errors, 0 mutating steps, estimated 7 calls. Raw records stayed only under ignored `docs/evidence/private_refs/`.
- Public summary was regenerated from the private manifest and records only status/counts/response key names plus private path references. Readiness packet was regenerated without embedding key material or private payloads.

## Round25 WSL self-host Go readiness - 2026-07-09

```powershell
wsl -d Ubuntu-24.04-Ashr -- bash -lc "set -e; whoami; pwd; command -v go || true; go version 2>/dev/null || true; command -v apt-get || true; command -v sudo || true; cat /etc/os-release | head -5"
wsl -d Ubuntu-24.04-Ashr -- bash -lc "set -euo pipefail; apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y golang-go; go version"
wsl -d Ubuntu-24.04-Ashr -- bash -lc "set -euo pipefail; cd /mnt/c/Users/33516/Documents/Ashr_a1_clean_rebase/packages/go/ashrclone; go test ./..."
```

Results:
- `Ubuntu-24.04-Ashr` runs as root on Ubuntu 24.04.4 LTS with `apt-get` and `sudo` available.
- Installed Go toolchain in the D-drive WSL environment: `go version go1.22.2 linux/amd64`.
- Linux/WSL Go SDK tests passed from `packages/go/ashrclone`; this validates the self-host backend package on a Linux runtime, not just Windows.

## Round25 integrated A1 validation - 2026-07-09

```powershell
go test ./...
go test ./...
npm test --prefix packages/ts/ashr-clone
python -B -m pytest tests/integration/test_a1_large_saas_migration.py tests/a1/test_a1_foundation_migration_manifest.py tests/integration/test_a1_large_saas_migration_live.py tests/a1/test_local_self_host_smoke_compose.py -q -p no:cacheprovider
python -B tests/a1/ts_python_parity_matrix.py --write
python -B tests/a1/ts_python_parity_matrix.py --check
python -B -m pytest tests/a1 -q -p no:cacheprovider
docker compose -f services/runner/docker-compose.a1.yml config --quiet
docker compose -f infra/docker/docker-compose.self-host.yml config --quiet
python scripts/cl_guard.py hygiene
git diff --check
```

Results:
- Go package tests passed in `packages/go/ashrclone`; Go integration tests passed in `tests/integration/go`.
- TS SDK suite passed with 322 tests after quickstart parity growth.
- SQL/self-host focused tests passed with 18 passed and 2 live-DB tests skipped behind `A1_POSTGRES_TEST_DSN`.
- TS/Python gap matrix regenerated after TS export growth and checked successfully.
- Python A1 full suite passed with 340 tests.
- Both Docker compose config checks passed.
- CL hygiene passed with zero findings; `git diff --check` produced CRLF normalization warnings only.

## Round26 route docs, quota enforcement, live Postgres, and mutating API calibration - 2026-07-09

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
gh repo view --json nameWithOwner,defaultBranchRef,url
gh pr list --state all --limit 20 --json number,title,headRefName,baseRefName,state,url,updatedAt
python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --modality text,image,audio,file,video --max-retries 0 --output docs/evidence/private_refs/a1_official_api_mutating_all_modalities_dryrun_20260709_172241.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --modality text,image,audio,file,video --max-retries 0 --quota-gate-record docs/evidence/private_refs/a1_mutating_all_modalities_quota_gate_20260709_172259.json --output docs/evidence/private_refs/a1_official_api_mutating_all_modalities_20260709_172259.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --modality image --max-retries 0 --quota-gate-record docs/evidence/private_refs/a1_image_mutating_quota_gate_20260709_172407.json --output docs/evidence/private_refs/a1_official_api_mutating_image_20260709_172407.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --modality audio --max-retries 0 --quota-gate-record docs/evidence/private_refs/a1_audio_mutating_quota_gate_20260709_172414.json --output docs/evidence/private_refs/a1_official_api_mutating_audio_20260709_172414.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --modality file --max-retries 0 --quota-gate-record docs/evidence/private_refs/a1_file_mutating_quota_gate_20260709_172421.json --output docs/evidence/private_refs/a1_official_api_mutating_file_20260709_172421.json
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --modality video --max-retries 0 --quota-gate-record docs/evidence/private_refs/a1_video_mutating_quota_gate_20260709_172428.json --output docs/evidence/private_refs/a1_official_api_mutating_video_20260709_172428.json
python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_official_api_mutating_all_modalities_20260709_172259.json --output docs/a1/evidence/official_api_readonly_manifest_summary.json
python -B -m packages.sdk.ashr_clone.calibrate write-readiness-packet
python -B -m pytest tests/a1/test_python_calibrator.py tests/integration/test_a1_large_saas_migration.py tests/a1/test_a1_foundation_migration_manifest.py -q -p no:cacheprovider
docker run --rm -d --name ashr-a1-live-pg -e POSTGRES_DB=ashr -e POSTGRES_USER=ashr -e POSTGRES_HOST_AUTH_METHOD=trust -p 15433:5432 postgres:16-alpine
$env:A1_POSTGRES_TEST_DSN='docker://ashr-a1-live-pg'; $env:A1_PSQL_DOCKER_CONTAINER='ashr-a1-live-pg'; python -B -m pytest tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider
go test ./...
go test ./...
npm test --prefix packages/ts/ashr-clone
python -B tests/a1/ts_python_parity_matrix.py --write
python -B tests/a1/ts_python_parity_matrix.py --check
python -B -m pytest tests/a1 -q -p no:cacheprovider
docker compose -f services/runner/docker-compose.a1.yml config --quiet
docker compose -f infra/docker/docker-compose.self-host.yml config --quiet
python scripts/cl_guard.py hygiene
git diff --check
wsl -d Ubuntu-24.04-Ashr -- bash -lc "pwd; uname -a; command -v bash; command -v go; go version; command -v python3; python3 --version"
docker version --format '{{.Server.Version}}'
```

Results:
- Baseline observed peer movement on `origin/codex/a3-commercial-growth-round4` and `origin/dev/g3-a2-calibration`; no peer files were staged in this A1 slice.
- Mutating dry-run plan covered text/image/audio/file/video with 10 planned steps, 5 mutating steps, 17 estimated calls, and no local guard errors.
- Real official API mutating small batches were attempted with env-only `ASHR_API_KEY`, small-batch, zero retries, quota-gate records, and private ignored output paths. The all-modality run reached `create-request-text`; per-media runs reached `create-request-image`, `create-request-audio`, `create-request-file`, and `create-request-video`. Each returned `status=partial`, 5 read steps, 1 mutating attempt, and `quota_block_count=1`. This proves real hosted mutating/media boundary behavior without leaking raw payloads publicly.
- Public mutating evidence index was written to `docs/a1/evidence/official_api_mutating_calibration_index.json`; raw manifests and quota gates remain ignored under `docs/evidence/private_refs/`.
- Disposable Docker Postgres live migration proof passed with 2 tests after removing UTF-8 BOMs from the migration and live test.
- Go package tests passed; Go integration tests passed.
- TS SDK suite passed with 325 tests.
- Python A1 suite passed with 347 tests after adding public mutating index coverage.
- Focused calibrator/SQL tests passed with 50 tests, and Docker compose configs passed.
- `python scripts/cl_guard.py hygiene` passed with zero findings; `git diff --check` produced CRLF normalization warnings only.
- WSL `Ubuntu-24.04-Ashr` starts from the D-drive install and has Bash, Go `1.22.2`, and Python `3.12.3`; Docker daemon reports `29.6.1`.

## Round27 durable quota catalog and official mutating evidence SDK consumption - 2026-07-09

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags
git status -sb
gh pr checks 27
gh run view 29008613785 --json status,conclusion,updatedAt,jobs
python -B -m pytest tests/a1/test_python_calibrator.py -q -p no:cacheprovider
npm run build --prefix packages/ts/ashr-clone
node --test packages/ts/ashr-clone/test/route-scope-manifest.test.mjs
python -B -m pytest tests/a1/test_a1_foundation_migration_manifest.py tests/a1/test_a1_control_plane_postgres_migration.py tests/integration/test_a1_large_saas_migration.py tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_python_calibrator.py -q -p no:cacheprovider
go test ./...
docker run --rm -d --name ashr-a1-live-pg -e POSTGRES_DB=ashr -e POSTGRES_USER=ashr -e POSTGRES_HOST_AUTH_METHOD=trust -p 15433:5432 postgres:16-alpine
$env:A1_POSTGRES_TEST_DSN='docker://ashr-a1-live-pg'; $env:A1_PSQL_DOCKER_CONTAINER='ashr-a1-live-pg'; python -B -m pytest tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider
go test ./...
npm test --prefix packages/ts/ashr-clone
python -B tests/a1/ts_python_parity_matrix.py --write
python -B tests/a1/ts_python_parity_matrix.py --check
python -B -m pytest tests/a1 -q -p no:cacheprovider
python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_official_api_readonly_20260709_175938.json
python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_official_api_readonly_20260709_175938.json --output docs/a1/evidence/official_api_readonly_manifest_summary.json
python -B -m packages.sdk.ashr_clone.calibrate write-readiness-packet
docker compose -f services/runner/docker-compose.a1.yml config --quiet
docker compose -f infra/docker/docker-compose.self-host.yml config --quiet
python scripts/cl_guard.py hygiene
git diff --check
```

Results:
- PR #27 GitHub run `29008613785` was still queued at baseline; no failing logs were available.
- Peer movement observed again on `origin/codex/a3-commercial-growth-round4`; no peer files were staged.
- SQL durable quota foundation now includes operation-aware `usage_ledger`, `operation_meter_mapping`, `current_quota_policy`, `check_quota_and_insert_usage`, advisory lock usage, idempotency replay, and quota-denied audit insertion.
- Go quota surface now has `QuotaRepository`, operation catalog, canonical SQL-aligned meters (`runs`, `media`, `observations`, `storage_bytes`), structured public-safe quota error responses, and repository append/readback tests.
- Growth-Auditor flagged SQL/Go meter vocabulary drift as P1; fixed this round by aligning Go meters with SQL and adding a Python static contract test that parses SQL + Go mappings together.
- Python and TypeScript SDKs now consume `docs/a1/evidence/official_api_mutating_calibration_index.json` and reject private evidence paths.
- Added `docs/a1/schemas/official_api_mutating_calibration_index.schema.json` and schema validation for the public mutating evidence index.
- Official API read-only small batch refreshed successfully with env-only key, 5 read steps, 0 errors, 0 mutating steps, estimated 7 calls. Private evidence remains ignored under `docs/evidence/private_refs/a1_official_api_readonly_20260709_175938.json`.
- Focused Python/SQL/schema tests passed with 82 tests before the meter-catalog fix and 10 focused migration tests after the fix.
- Disposable Docker Postgres live migration proof passed with 2 tests after SQL quota additions and meter catalog fix.
- Go package tests passed; Go integration tests passed.
- TS package suite passed with 327 tests.
- Python A1 suite passed with 354 tests.
- Docker compose config checks passed; CL hygiene passed with zero findings; `git diff --check` reported CRLF normalization warnings only.


## Round28 durable quota runtime wiring + paid media mutating proof - 2026-07-09T10:33:59Z

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb`; `gh pr checks 27`; `gh run list --branch codex/a1-local-sdk-runner --limit 8 --json ...`: baseline fetched; peer change on `origin/dev/g3-a2-calibration`; PR #27 latest run `29010797860` later completed success.
- `python -B -m services.runner.api_probe plan-batch --target-operation create-request --request-name "A1 Paid Media Calibration 20260709_182610" --request-file docs/a1/api_calibration/media_interface_request.json --allow-media-generation --allow-non-text-inputs --small-batch-size 1 --batch-size 1 --output docs/evidence/private_refs/a1_api_media_paid_plan_20260709_182610.json`: planned paid media mutating batch; status `blocked` by quota gate.
- `python -B -m services.runner.api_probe create-request --execute --allow-mutate --allow-media-generation --allow-non-text-inputs --max-request-variations 1 --max-retries 0 --request-name "A1 Paid Media Calibration 20260709_182610" --request-file docs/a1/api_calibration/media_interface_request.json --quota-gate-record docs/evidence/private_refs/a1_api_media_paid_plan_20260709_182610.json --quota-gate-ttl-seconds 0 --allow-quota-override --quota-override-reason "user-authorized paid media calibration for A1 mutating/media contract coverage on 2026-07-09" --output docs/evidence/private_refs/a1_api_media_paid_real_20260709_182610.json`: real official paid-media mutating attempt; `function=create_request`, `status=error`, `status_code=200`, `attempts=1`; public-safe observation is request quota exhausted with counters `limit=5`, `used=5`, `requested=1`, `remaining=0`.
- `docker run --rm -d --name ashr-a1-live-pg ... postgres:16-alpine`; `python -B -m pytest tests/integration/test_a1_large_saas_migration_live.py -q -p no:cacheprovider`: disposable live Postgres proof after SQL fixes -> `3 passed`.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `npm test --prefix packages/ts/ashr-clone`: `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `354 passed`.
- Focused official mutating schema/SDK tests: `3 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet`: pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet`: pass.
- `python scripts/cl_guard.py hygiene`: pass, zero findings.
- `git diff --check`: no whitespace errors; CRLF normalization warning for `docs/a1/evidence/official_api_mutating_calibration_index.json` only.
- `gh pr checks 27`: CL Gate green; A3 checks skipped by rule, not failing.


## Round29 usage quota route parity + paid media quota boundary - 2026-07-09T10:50:14Z

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`; `git status -sb --untracked-files=all`; `gh pr view 27 --json ...`: baseline fetched; PR #27 green at run `29012107574`; local working tree had only A1 Round29 edits.
- Growth-Auditor read-only audit: flagged durable Postgres API key/preflight, route-level quota proof, RLS live negative proof, and official quota exhaustion as next blockers; no files modified by auditor.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider`: `20 passed`.
- `npm test --prefix packages/ts/ashr-clone`: `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet`: pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet`: pass.
- `python scripts/cl_guard.py hygiene`: passed with zero findings.
- `git diff --check`: no whitespace errors; JSON CRLF normalization warnings only.
- `python -c "import os; ..."`: key presence/length only confirmed, value not printed.
- `python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --modality text,image,audio,file,video --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_paid_media_all_modalities_dry_run_20260709_185014.json`: dry-run planned 17 estimated calls and 5 mutating modality steps.
- `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --include-mutating --allow-paid-media --modality text,image,audio,file,video --allow-quota-override --quota-override-reason ... --output docs/evidence/private_refs/a1_paid_media_all_modalities_real_20260709_185014.json`: real official call used env-only key; 5 read steps succeeded, first text mutating create_request hit quota boundary; result `partial`, quota block count 1.
- `python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_paid_media_all_modalities_real_20260709_185014.json --output docs/a1/evidence/official_api_paid_media_summary_20260709_185014.json`: wrote public-safe summary. A mistaken attempt to write summary into the mutating index was reverted with `git checkout -- docs/a1/evidence/official_api_mutating_calibration_index.json` before manual schema-safe index append.


## Round30 durable Postgres API key lifecycle and preflight - 2026-07-09T11:06:30Z

- `gh pr checks 27`: PR #27 commit `985f400` CL Gate green; Go, Python, TS, Plan/hygiene, and summary passed; A3/Rust jobs skipped by rule.
- Growth-Auditor read-only audit: P0 blockers were durable Postgres API key lifecycle, Postgres-backed preflight/rate-limit snapshot, `sdk-submit` route preflight, and future bearer-auth parity; P1 blockers were RLS live negative proof and successful official mutating baseline after quota reset.
- `go test ./...` from `packages/go/ashrclone`: pass after implementing durable Postgres API key create/list/revoke/verify/preflight/rate-limit/snapshot.
- `go test ./...` from `tests/integration/go`: pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider`: `20 passed`.
- `npm test --prefix packages/ts/ashr-clone`: `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet`: pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet`: pass.
- `python scripts/cl_guard.py hygiene`: passed with zero findings.
- `git diff --check`: pass.
- Official API note: no duplicate mutating call in this sub-slice because Round29 already proved hosted quota boundary with env-only key; next paid/API calibration should wait for quota reset or plan change to produce a successful text baseline before media writes.


## Round31 live Postgres API key proof - 2026-07-09T11:22:10Z

- `gh pr checks 27`: commit `4a68408b` CL Gate green; Go, Python, TS, Plan/hygiene, and summary passed; A3/Rust skipped by rule.
- Added `tests/integration/go/postgres_api_key_live_test.go`, gated by `A1_POSTGRES_TEST_DSN` so CI without a live DB skips it safely.
- `go test ./...` from `tests/integration/go` without DSN: pass; live test skipped.
- Disposable live proof: `docker run --rm -d --name ashr-a1-go-live-pg -e POSTGRES_USER=ashr -e POSTGRES_PASSWORD=ashr -e POSTGRES_DB=ashr -p 55433:5432 postgres:16-alpine`; set process-only `A1_POSTGRES_TEST_DSN=postgres://ashr:ashr@localhost:55433/ashr?sslmode=disable`; `go test ./... -run TestPostgresAPIKeyLifecycleLiveOptIn -count=1 -v` from `tests/integration/go` -> pass; container removed.
- The first live attempt failed because API key rate-limit configuration used public route operation `sdk_submit` while Postgres mutation evidence used durable operation `sdk.submit`; fixed by normalizing operation names in configure/preflight/load/consume paths.
- The second live attempt failed because non-UUID local key handles touched the commercial UUID `api_keys` table inside a transaction; fixed by skipping commercial table updates for non-UUID tenant/project/key handles.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider`: `20 passed`.
- `npm test --prefix packages/ts/ashr-clone -- --test-name-pattern "route|Go OpenAPI|route_scope"`: `327 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `354 passed`.
- `docker compose -f services/runner/docker-compose.a1.yml config --quiet`: pass.
- `docker compose -f infra/docker/docker-compose.self-host.yml config --quiet`: pass.
- `python scripts/cl_guard.py hygiene`: passed with zero findings.
- `git diff --check`: pass.
- `go test ./...` from repository root is a known invalid command for this multi-module repo and reports `directory prefix . does not contain main module`; correct Go test entrypoints are module-scoped and passed.


## Round32 live Postgres HTTP API key proof - 2026-07-09T11:33:20Z

- Extended `tests/integration/go/postgres_api_key_live_test.go` with `TestPostgresHTTPAPIKeyLifecycleLiveOptIn`, using `httptest.NewServer(ashrclone.NewHTTPHandler(repository))` over a real Postgres repository.
- `go test ./...` from `tests/integration/go` without DSN: pass; live tests skipped.
- Disposable HTTP live proof: `docker run --rm -d --name ashr-a1-go-http-live-pg -e POSTGRES_USER=ashr -e POSTGRES_PASSWORD=ashr -e POSTGRES_DB=ashr -p 55434:5432 postgres:16-alpine`; process-only `A1_POSTGRES_TEST_DSN=postgres://ashr:ashr@localhost:55434/ashr?sslmode=disable`; `go test ./... -run 'TestPostgres.*LiveOptIn' -count=1 -v` from `tests/integration/go` -> repository and HTTP live tests passed; container removed.

## Round33 bearer auth and admin API-key hardening - 2026-07-09T20:10:00+08:00

- `pwd; git rev-parse --show-toplevel; git remote -v; git branch --show-current; git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags; git status -sb --untracked-files=all; gh repo view --json nameWithOwner,defaultBranchRef,url; gh pr list --state all --limit 20 --json number,title,headRefName,baseRefName,state,isDraft,updatedAt,url; gh pr checks 27 --watch=false`: PR #27 green before this round; A3/Rust skipped by rule.
- `docker version; docker ps; wsl -l -v`: Docker Desktop daemon available; WSL distributions installed but stopped. Direct `/bin/bash` command in Codex failed with `/bin/bash: No such file or directory`, so this round used PowerShell.
- Growth-Auditor read-only review: recommended admin API-key auth truthfulness and live evidence.
- TS worker: changed `packages/ts/ashr-clone/src/saas.ts` and `packages/ts/ashr-clone/test/saas.test.mjs`; reported `npm test -- --runInBand` -> 328 passed and Python parity subset -> 12 passed.
- `go test ./...` from `packages/go/ashrclone`: pass after Bearer auth and admin API-key hardening.
- `go test ./...` from `tests/integration/go`: pass without DSN.
- Disposable Postgres live proof: `docker run --name ashr-a1-pg-live-55435 -e POSTGRES_PASSWORD=ashr -e POSTGRES_USER=ashr -e POSTGRES_DB=ashr -p 55435:5432 -d postgres:16-alpine`; set process-only `A1_POSTGRES_TEST_DSN=postgres://ashr:ashr@127.0.0.1:55435/ashr?sslmode=disable`; `go test ./... -run 'TestPostgres.*LiveOptIn' -count=1 -v` from `tests/integration/go` -> both live tests passed; container removed.
- `python -B -m pytest tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider`: 20 passed.
- `npm test --prefix packages/ts/ashr-clone`: 328 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 354 passed.


## Round34 commands - 2026-07-09T12:40:07Z

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: fetched remote branches; observed A3 branch update only.
- `gh pr list --state all --limit 20 --json ...`: PR #27 open draft for A1; PR #28 A3 open; PR #29 A2 open.
- `gh pr checks 27 --watch=false`: prior A1 head green for CL Gate summary, Go SDK/integration, Python A1/A2, TypeScript, Plan/hygiene; A3/Rust skipped.
- `python -m py_compile services/api/billing.py services/api/__init__.py`: pass after adding billing module/export.
- `python -B -m pytest tests/a1/test_billing_provider_contract.py -q -p no:cacheprovider`: `7 passed` after fixing raw Stripe secret prefix rejection.
- `python -B -m pytest tests/a1/test_billing_provider_contract.py tests/a1/test_saas_sdk_client.py tests/a1/test_saas_platform.py tests/a1/test_go_python_route_contract_evidence.py -q -p no:cacheprovider`: `47 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `365 passed`.
- `npm test --prefix packages/ts/ashr-clone`: `328 passed`.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `python scripts/cl_guard.py hygiene`: pass, `findings=[]`.
- `git diff --check`: pass.
- Official docs checked via web search: Stripe API keys/authentication, Stripe payment method support, Stripe Checkout, WeChat Pay Native pay docs, Alipay trade docs. No provider secret or real-card value was read or logged.


## Round35 commands - 2026-07-09T13:01:14Z

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: fetched remote branches; observed A2 branch update only.
- `gh pr view 27 --json ...` / `gh pr checks 27 --watch=false`: PR #27 prior head `2fec1b74`; Plan/hygiene queued at baseline.
- `python -m py_compile services/api/billing.py services/api/__init__.py`: pass after Python billing ledger/idempotency additions.
- `python -B -m pytest tests/a1/test_billing_provider_contract.py -q -p no:cacheprovider`: `10 passed`.
- `python tests/a1/ts_python_parity_matrix.py --write`: refreshed TS/Python parity matrix after adding TS billing module.
- `python -B -m pytest tests/a1/test_ts_python_gap_matrix.py -q -p no:cacheprovider`: pass.
- `python -B -m pytest tests/a1/test_evidence_index.py::test_tracked_a1_public_evidence_artifacts_are_secret_safe -q -p no:cacheprovider`: pass after public evidence wording/ref cleanup.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `368 passed`.
- `npm test --prefix packages/ts/ashr-clone`: `334 passed`.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `python scripts/cl_guard.py hygiene`: pass, `findings=[]`.
- `git diff --check`: pass.
- `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_readonly_round35_20260709_210008.json`: official Ashr API read-only small batch succeeded, 5 read steps, no mutating steps, raw record private/ignored.
- `python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_readonly_round35_20260709_210008.json --output docs/a1/evidence/official_api_readonly_round35_summary_20260709_210008.json`: wrote public-safe summary.


## Round36 commands - 2026-07-09T13:16:57Z

- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags`: fetched remote branches; observed A3 branch update only.
- `gh pr view 27 --json ...` / `gh pr checks 27 --watch=false`: PR #27 head `f8ee9564`; Plan/hygiene, Go, Python, and TypeScript passed; summary queued at inspection time.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py -q -p no:cacheprovider`: `5 passed`.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_billing_provider_contract.py tests/a1/test_evidence_index.py::test_tracked_a1_public_evidence_artifacts_are_secret_safe -q -p no:cacheprovider`: `16 passed`.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_billing_provider_contract.py -q -p no:cacheprovider`: `15 passed`.
- `python scripts/cl_guard.py hygiene`: pass, `findings=[]`.
- `git diff --check`: pass.
- Environment note: `Get-PSDrive` showed C: at 0 bytes free. Removed regenerateable workspace/tool caches only. Reinstalling TS package dependencies with npm cache on D: still failed because `node_modules` target remains on C:. No source/evidence/private refs were deleted.


## Round37 commands - 2026-07-09T13:25:51Z

- `gh pr checks 27 --watch=false`: PR #27 head `91213fc8` green for summary, Plan/hygiene, Go, Python, and TypeScript; A3/Rust skipped.
- `npm install --prefix packages/ts/ashr-clone --cache D:/codex-cache/npm --prefer-offline`: restored local TS dependencies after C: space recovered.
- `npm test --prefix packages/ts/ashr-clone -- --test-name-pattern billing`: `334 passed` because the current Node runner still executes the full package suite.
- `python -B -m pytest tests/integration/test_a1_billing_ledger_migration_live.py -q -p no:cacheprovider`: `1 skipped` without `A1_POSTGRES_TEST_DSN`.
- `python -B -m pytest tests/a1/test_billing_ledger_migration_manifest.py tests/integration/test_a1_billing_ledger_migration_live.py -q -p no:cacheprovider`: `5 passed, 1 skipped`.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `python scripts/cl_guard.py hygiene`: pass, `findings=[]`.
- `git diff --check`: pass.
- Docker note: `docker version --format '{.Server.Version}'` hung and was stopped by terminating the command process only; live Postgres proof not run locally.

### Round 38 billing route contract + payment provider readiness
- `git fetch origin '+refs/heads/*:refs/remotes/origin/*' --prune --tags` -> completed.
- `gh pr checks 27 --watch=false` -> latest pre-round PR #27 checks green; A3 checks skipped by gate policy.
- `go test ./...` from repo root -> invalid monorepo entry (`directory prefix . does not contain main module`); use package module paths instead.
- `go test ./...` in `packages/go/ashrclone` -> passed.
- `go test ./...` in `tests/integration/go` -> passed.
- `npm test --prefix packages/ts/ashr-clone -- --test-name-pattern "billing|route|SaaS"` -> 335 passed.
- `npm test --prefix packages/ts/ashr-clone` -> 335 passed.
- `python -B -m pytest tests/a1/test_saas_sdk_client.py tests/a1/test_billing_provider_contract.py tests/a1/test_go_python_route_contract_evidence.py tests/a1/test_payment_provider_readiness_docs.py -q -p no:cacheprovider` -> 51 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider` -> 378 passed, 1 skipped; Docker daemon probe timed out and skipped compose validation.
- `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --limit 1 --output docs/evidence/private_refs/a1_readonly_billing_route_round38_20260709_215947.json` -> status ok, 5 read steps, 0 mutating steps; public summary at `docs/a1/evidence/official_api_readonly_round38_summary_20260709_215947.json`.

## Round39 commands - 2026-07-09T14:25:00Z

- `git status -sb; git diff --name-only; git log --oneline -5`: confirmed branch `codex/a1-local-sdk-runner-clean`, previous PR head `5c4bc83`, and dirty A1 billing/provider files only.
- `python -B -m pytest tests/a1/test_billing_sdk_parity.py tests/a1/test_billing_ledger_migration_manifest.py tests/a1/test_payment_provider_readiness_docs.py -q -p no:cacheprovider`: first run found Python transport and SQL assertion mismatches; after fixes, `17 passed`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `384 passed, 1 skipped`.
- `npm test --prefix packages/ts/ashr-clone` with `npm_config_cache=D:/codex-cache/npm`: `337 passed`.
- `go test ./...` from `packages/go/ashrclone`: pass.
- `go test ./...` from `tests/integration/go`: pass.
- `python scripts/cl_guard.py hygiene`: pass, `findings=[]`.
- `git diff --check`: pass; Git emitted a CRLF normalization warning for `tests/a1/test_billing_provider_contract.py`.
- Targeted scan: `rg -n "sk_live_|sk_test_|rk_live_|rk_test_|whsec_|Bearer [A-Za-z0-9._-]+|4242[ -]?4242|card_number|cvv|cvc|client_secret|api_key_secret" ...` found only expected SQL guardrail regexes, synthetic tests, and SDK parameter names; no raw key/card/provider secret was added.
- Frontend mirror inspection from `C:/Users/33516/Desktop/Ashr_frontend_mirror_20260707_125507.zip` wrote `docs/a1/evidence/frontend_mirror_billing_usage_fields_20260709_221430.json`, public-safe markers only.
- `Get-ChildItem Env:ASHR_API_KEY,Env:ASHR_LABS_API_KEY`: `ASHR_API_KEY=present(length=46)`; raw value was not printed.
- `python -B -m packages.sdk.ashr_clone.calibrate --include-mutating --allow-paid-media --modality text,image,audio,file,video --limit 12 --output docs/evidence/private_refs/a1_paid_media_mutating_dryrun_round39_20260709_222232.json`: planned 5 read + 5 mutating modality steps, estimated 17 calls.
- `python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --include-mutating --allow-paid-media --allow-quota-override --quota-override-reason user_authorized_paid_media_calibration_round39_bounded_once --max-retries 0 --modality text,image,audio,file,video --limit 8 --output docs/evidence/private_refs/a1_paid_media_mutating_small_batch_round39_20260709_222232.json`: partial; 5 read steps ok, text mutating step quota/API blocked, non-text paid media did not proceed past gate.
- `python -B -m packages.sdk.ashr_clone.calibrate summarize-private-manifest --input docs/evidence/private_refs/a1_paid_media_mutating_small_batch_round39_20260709_222232.json --output docs/a1/evidence/official_api_paid_media_round39_summary_20260709_222232.json --print-record`: wrote public-safe summary and returned non-zero because source status was partial; summary contains only response keys/status/quota flags.
