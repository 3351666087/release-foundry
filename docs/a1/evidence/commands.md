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
