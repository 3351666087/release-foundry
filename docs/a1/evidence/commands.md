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
