# A1 API Calibration

Round date: 2026-07-04

This folder records public, non-sensitive summaries from subscription-era A1 calibration. Raw API records and dashboard screenshots are kept under `docs/evidence/private_refs/`, which is locally ignored and must not be committed.

## Safety Contract

- API keys are read only from `ASHR_API_KEY` or the official SDK-compatible `ASHR_LABS_API_KEY`.
- Optional base URL override follows `ASHR_LABS_BASE_URL`.
- The probe CLI defaults to dry-run and writes a call plan before any real call.
- Real calls require `--execute`.
- Mutating operations, currently `create-request` and `create-run`, additionally require `--allow-mutate`.
- Records redact sensitive keys and selected headers; committed docs must contain only field names, counts, command summaries, and private evidence paths.

## Probe Surface

Implemented in `packages/sdk/ashr_clone/api_client.py` and `services/runner/api_probe.py`:

- `init`
- `health-check`
- `list-datasets`
- `get-dataset`
- `list-runs`
- `get-run`
- `poll-run`
- `list-requests`
- `list-agents`
- `get-request`
- `poll-request`
- `create-request`
- `create-run`

The client follows the observed official Python SDK shape: one POST endpoint at `https://api.ashr.io/testing-platform-api` dispatches by a `function` field. List/create operations that need tenant or user context resolve session through `init` before the target function when executing real calls.

## Real Read-Only Calibration

Private evidence files:

- `docs/evidence/private_refs/a1_api_init_real_v2.json`
- `docs/evidence/private_refs/a1_api_health_check_dry_run.json`
- `docs/evidence/private_refs/a1_api_health_check_real.json`
- `docs/evidence/private_refs/a1_api_list_agents_dry_run.json`
- `docs/evidence/private_refs/a1_api_list_agents_real.json`
- `docs/evidence/private_refs/a1_api_list_datasets_real_v2.json`
- `docs/evidence/private_refs/a1_api_list_runs_real.json`
- `docs/evidence/private_refs/a1_api_list_requests_real.json`
- `docs/evidence/private_refs/a1_api_get_dataset_first_real.json`
- `docs/evidence/private_refs/a1_api_get_dataset_0_error_real.json`
- `docs/evidence/private_refs/a1_api_create_run_dry_run.json`
- `docs/evidence/private_refs/a1_api_create_run_real.json`
- `docs/evidence/private_refs/a1_api_get_created_run_real.json`
- `docs/evidence/private_refs/a1_api_poll_created_run_real_v2.json`
- `docs/evidence/private_refs/a1_api_tiny_create_request_dry_run.json`
- `docs/evidence/private_refs/a1_api_tiny_create_request_round2_dry_run.json`
- `docs/evidence/private_refs/a1_api_tiny_create_request_round2_real.json`
- `docs/evidence/private_refs/a1_api_tiny_create_request_round2_schema_dry_run.json`
- `docs/evidence/private_refs/a1_api_media_interface_create_request_dry_run.json`
- `docs/evidence/private_refs/a1_api_media_interface_get_request_recheck_real.json`
- `docs/evidence/private_refs/a1_real_dataset_cases.json`
- `docs/evidence/private_refs/a1_real_dataset_run_mock.json`
- `docs/evidence/private_refs/ashr_lab_analysis_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_analysis_create_run_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_analysis_request_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_usage_next_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_usage_request_round_2026-07-04.png`

Observed non-sensitive field keys:

- `init` response keys: `features`, `notes`, `status`, `tenant`, `user`.
- `health_check` official SDK method sends API function `keep_alive`; response keys: `db`, `message`, `status`.
- `init.user` keys: `created_at`, `email`, `id`, `is_active`, `is_owner`, `name`, `tenant_id`.
- `init.tenant` keys: `created_at`, `id`, `is_active`, `owner_email`, `plan`, `signup_method`, `tenant_name`.
- `list_agents` response keys: `_user`, `agents`, `status`; current private real account returned an empty `agents` list.
- `list_datasets` response keys: `_user`, `datasets`, `next_cursor`, `status`.
- Dataset item keys: `agent_details`, `agent_id`, `created_at`, `creator`, `creator_details`, `dataset_source`, `dataset_type`, `description`, `id`, `name`, `repo_id`, `request_id`, `run_count`, `tenant`.
- Full dataset source keys observed by Explorer-API: `dataset_type`, `runs`, `total_runs`; first run shape included `run_id`, `title`, `description`, `intent`, `intent_tags`, `audio_tags`, `simulation`, `actions`.
- `list_runs` response keys: `_user`, `runs`, `status`.
- Run item keys: `created_at`, `dataset`, `dataset_details`, `id`, `result`, `runner`, `runner_details`, `tenant`.
- `list_requests` response keys: `_user`, `next_cursor`, `requests`, `status`.
- Request item keys: `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `request`, `request_name`, `request_status`, `requestor_details`, `requestor_id`, `requestor_tenant`.

## Create Run And Poll Calibration

One real `create-run` probe was executed after reviewing a dry-run plan:

- Dry-run plan: `status=planned`, `attempts=0`, `mutates=true`, `estimated_calls=2`, 3-case private local result input.
- Real call: `status=ok`, HTTP `200`, `attempts=1`, response keys `_user`, `run`, `status`.
- Created run keys: `created_at`, `dataset`, `id`, `result`, `runner`, `tenant`.
- Hosted run result keys mirrored local A1 output: `aggregate_metrics`, `cases`, `dataset_id`, `duration_ms`, `ended_at`, `errored`, `failed`, `field_map_version`, `max_workers`, `metadata`, `passed`, `run_id`, `runner_id`, `started_at`, `status`, `timed_out`, `total_cases`, `trace_completeness`.
- Follow-up `get-run` succeeded with HTTP `200`, `attempts=1`, and the same run/result shape.
- First short `poll-run` exposed a real parity bug: `get_run` returned a complete `run.result`, but the local poll completion predicate only looked for `aggregate_metrics.tests_passed`, then timed out after 4 attempts and the CLI printed a traceback.
- Fixed behavior: poll completion now accepts the observed run-result shape, CLI catches `TimeoutError`, and the same private created run polls successfully with `status=ok`, HTTP `200`, `attempts=1`.

## Create Request And Media Interface Calibration

Official API reference says `request_input_schema` is optional and that a permissive default is sent if omitted. A real text-only `create-request` probe without this field instead returned an API-level error: HTTP `200`, `status=error`, `attempts=1`, message `request_input_schema is required`. A1 now mirrors the documented SDK behavior by sending a permissive default schema when omitted:

- default schema keys: `type`, `additionalProperties`
- when the request agent declares tools, the default schema also includes `tools`
- when accepted inputs include `text`, `audio`, `file`, `image`, or `video`, the default schema also advertises the local `AgentInput` envelope: `schema_version`, `text`, `parts`, `metadata`, and `$defs.agent_input_part`
- CLI dry-run preflight records `request_input_schema_source=client_default`

The tiny generation config at `docs/a1/api_calibration/tiny_generation_request.json` is text-only and bounded to one variation. The dry-run record now includes a local preflight summary:

- `num_variations=1`
- `num_variations_known=true`
- `small_batch=true`
- accepted inputs: text only; `non_text_inputs_enabled=false`
- media generation: audio/files/images/videos/simulations all disabled
- `mutates=true`, `estimated_calls=2`, `attempts=0`

Text/Audio/File/Image/Video interface coverage now has a committed dry-run-first fixture at `docs/a1/api_calibration/media_interface_request.json`:

- accepted inputs include text, audio, file, image, and video
- `generate_audio=true`, `generate_files=true`, `generate_images=true`, `generate_videos=true`
- simulations remain false
- `num_variations=1`
- default request input schema dry-run shape includes `agent_input_schema_version=ashr.clone.agent_input.v1`, property keys `metadata`, `parts`, `schema_version`, `text`, and part types `audio`, `file`, `image`, `text`, `video`
- dry-run only; real execution is blocked by default because both `media_generation_enabled` and `non_text_inputs_enabled` are true

Real request calibration after the default schema patch:

- Text-only tiny request with `num_variations=1` succeeded: `create-request` returned `status=ok`, HTTP `200`, `attempts=1`, response keys `_user`, `request`, `status`.
- Follow-up `get-request` returned `request_status=processing`, then bounded `poll-request` returned `request_status=completed` with `status=ok`, HTTP `200`, `attempts=1`.
- The completed request shape includes `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `prompt_version_id`, `request`, `request_input_schema`, `request_name`, `request_status`, `requestor_id`, and `requestor_tenant`.
- One real Image/Audio/Files interface request was submitted after a fresh Usage page review and explicit `--allow-media-generation --allow-non-text-inputs`; it returned `create-request status=ok`, then `get-request request_status=failed`. Bounded `poll-request` recorded an error summary with HTTP `200`, `attempts=1`, and message `request failed`.
- A later read-only recheck of that failed media request found no top-level failure/reason/message/detail fields on the hosted request object. The nested original request payload contained `_failure` with safe shape keys `at` and `error`; both values were strings. A1 records this as `response_summary.request_failure.failure_sources.request._failure` and, for failed polling, `error.failure_summary`, using only keys, types, string lengths, and counts.
- A text-only 3-variation batch dry-run passed local preflight, but real execution returned a hosted API-level usage error: request quota exhausted for the current period. No retry was attempted.

Execution guardrails:

- `create-request --execute` still requires `--allow-mutate`.
- Real mutating `create-run` and `create-request` execution requires `--max-retries 0` to avoid duplicate creation on retry.
- Real execution blocks unknown `num_variations`; the request config must set a known value no larger than `--max-request-variations` before mutation.
- `num_variations` must be a positive integer or digit-only positive integer string; `0`, booleans, floats, and decimal strings are treated as unknown and blocked before mutation.
- `accepted_inputs` may use booleans or `{enabled: bool}` values. Unsupported shapes are treated as unknown and blocked before mutation.
- The CLI blocks media generation unless `--allow-media-generation` is passed.
- The CLI blocks non-text accepted inputs unless `--allow-non-text-inputs` is passed.
- The CLI blocks known `num_variations` values above `--max-request-variations`, which defaults to `1`.
- Chrome usage checks reached the logged-in Usage page. The page sometimes showed visible Image/Audio/Files usage counters; a direct reload also sometimes showed only `Loading usage...`. Treat usage counters as visible but unstable, and do not execute media generation without a fresh usage read.
- The media-schema round reached the logged-in Usage page again, but it only stably showed `Usage`, `Upgrade`, and `Loading usage`; media counters remained unstable in tracked evidence. A private screenshot was stored under ignored private evidence.

## Dataset Source Adapter

Implemented in `packages/sdk/ashr_clone/dataset_adapter.py` and `services/runner/dataset_adapter.py`.

- `dataset_source.runs` accepts either a map or list.
- `cases_from_dataset_source(...)` emits one A1 local runner case per agent-side source action.
- `case_from_source_run(...)` selects a single agent action by absolute `action_index` or agent action ordinal.
- `replay_fixture_from_source_run(...)` builds strict A3 replay fixtures through `TraceRecorder` and `build_run_fixture(...)`; VM frames are not hand-written.
- Case metadata is summary-only and does not include raw actions or raw source run ids. Missing machine-checkable expected output is marked with `requires_external_judge: true`.
- Converted cases are content-bearing because `prompt`, `expected`, `title`, and identifiers are derived from source actions. Real conversions must stay in ignored private evidence or be redacted before committing.
- Local runner grading now compares tool-call arguments when the expected tool call explicitly includes `arguments`, `args`, `input`, or `arguments_json`; name-only expectations remain name-only for backward compatibility.

Private real-shape smoke test:

- `a1_api_get_dataset_first_real.json` converted to 3 local runner cases.
- The first real source run produced a replay fixture with 11 trace events and 11 VM stream frames; `validate_run_fixture(...)` passed.
- The converted cases ran through the local mock agent with `0 errors`, `0 timeouts`, and trace completeness `100%`; content mismatches failed as expected for the mock agent.

## Error And Retry Findings

- API-level errors can arrive with HTTP 200 and body `status: error`.
- A real invalid dataset probe produced a redacted record with `status=error`, `status_code=200`, and `error_kind=api`.
- HTTP status alone is insufficient for runner success classification.
- Local tests cover retry behavior for retryable HTTP status codes including 429.
- No quota counters or rate-limit headers were returned by the small successful calls in this round; the client now captures `retry-after` and `x-ratelimit-*` if present.

## Current Verification

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: 47 passed.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: 26 passed.
- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: 21 passed.
- `python -B -m pytest tests/a1/test_trace_fixture.py -q -p no:cacheprovider`: 8 passed.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_api_client.py -q -p no:cacheprovider`: 56 passed.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 15 passed.
- `python -B -m pytest tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 62 passed.
- `python -B -m pytest tests/a1/test_adapter.py tests/a1/test_api_client.py tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 83 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 125 passed.
- `npm test --prefix packages/ts/ashr-clone`: TypeScript build plus 33 Node tests passed.
- `node packages/ts/ashr-clone/dist/probe.js init --output docs/evidence/private_refs/a1_ts_api_init_dry_run.json`: TypeScript probe CLI dry-run wrote a planned record under ignored private evidence and printed only a one-line summary to stdout.
- `node packages/ts/ashr-clone/dist/probe.js create-request --request-name "A1 TS Media Dry Run" --request-file docs/a1/api_calibration/media_interface_request.json --output docs/evidence/private_refs/a1_ts_api_media_create_request_dry_run.json`: TypeScript probe CLI dry-run recorded Text/Audio/File/Image/Video preflight shape without network or key use.
- `python -B -m pytest tests/a1/test_cloud_api.py tests/a1/test_cloud_api_cli.py -q -p no:cacheprovider`: 31 passed after adding queue batch replay/export coverage.
- `python -B -m services.api.cli queue-run --input docs/a1/evidence/local_agent_cases_30.json --state-output docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --summary-output docs/evidence/private_refs/a1_queue_batch_state_summary_smoke.json --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --runner-id a1-batch-replay-smoke --run-id run_a1_batch_replay_002 --run-id run_a1_batch_replay_001`: wrote an ignored local state snapshot with two queued 30-case runs in explicit batch order.
- `python -B -m services.api.cli replay-queued --state-input docs/evidence/private_refs/a1_queue_batch_state_snapshot_smoke.json --agent examples.agents.mock_agent:RespondingMockAgent --tenant-id tenant_a1_batch_replay_smoke --project-id project_a1_batch_replay_smoke --dataset-id dataset_a1_batch_replay_smoke --fixture-output-dir docs/evidence/private_refs/a1_queue_batch_replay_fixtures --summary-output docs/evidence/private_refs/a1_queue_batch_replay_summary_smoke.json --run-output-dir docs/evidence/private_refs/a1_queue_batch_replay_runs --state-output docs/evidence/private_refs/a1_queue_batch_replayed_state_smoke.json --queue-workers 4 --max-workers 4 --timeout 5 --wait-timeout 30`: replayed two runs in deterministic batch order; each completed 30 passed, 0 failed, 0 errored, 0 timed out, with 60 observations, and wrote per-run fixture/result files under ignored private evidence.
- `node packages/ts/ashr-clone/examples/quickstart.mjs docs/a1/evidence/local_run_30.json docs/evidence/private_refs/a1_ts_quickstart_fixture_smoke.json`: wrote a local-only TS cloud fixture for 30 cases under ignored private evidence.
- Real read-only probes executed: `init`, `list-datasets`, `list-runs`, `list-requests`, `get-dataset` for one existing dataset, and negative `get-dataset` for an invalid dataset.
- Real mutating probes executed: one `create-run` against an existing private dataset; one successful text-only `create-request`; one accepted Image/Audio/Files `create-request` that later reached hosted `request_status=failed`; one blocked text-batch `create-request` that returned hosted request quota exhaustion.
- Real read-only follow-up probes executed against the created run/request resources: `get-run`, fixed `poll-run`, `get-request`, `poll-request`, post-media `list-requests`, and post-request `list-datasets`.
- Chrome dashboard check reached logged-in `Ashr Labs` at `https://lab.ashr.io/?tab=analysis`; visible shell hints included `Datasets` and `Runs`.
- Error string redaction is covered at the text level: token-like values, bearer tokens, and email addresses are replaced before records or exception text are emitted.
- Local multimodal adapter coverage now includes `AgentInput` with `text`, `audio`, `file`, `image`, and `video` parts, explicit `respond_input`/`arespond_input`, content-part output text extraction, and adapter error redaction for token-like strings, bearer tokens, emails, and signed URL query strings.
- Local media request schema coverage now verifies that dry-run `create-request` records include `AgentInput` schema shape for Text/Audio/File/Image/Video before real execution is allowed, and that part types match enabled accepted inputs.
- Local hosted request failure coverage verifies that failed `get-request` / `poll-request` records include safe nested `_failure` field-shape summaries without recording raw failure text in tracked docs.
- Local read-only SDK parity coverage now includes `health-check` and `list-agents`, matching official SDK `health_check()` / `list_agents()` and A2's real API smoke surface.
- Local cloud API skeleton coverage now includes in-memory tenant/project/dataset/request/run records, run polling, fixture export, and project-scoped quota blocking before writes. The local cloud demo CLI coverage runs an external agent target, submits the result into `CloudApiService`, polls the stored run, writes a summary, writes an A3-consumable fixture, preserves failure output semantics, and redacts operational error text. Adapter/API redaction now both cover `sk-...` style key strings. This path made no real Ashr API calls.
- Local queue worker coverage now includes queued run creation, queued/running/completed status history, failed completion when observation quota is exhausted, max worker normalization to at least 4, run id propagation into `RunResult` and observations, `run-agent-queued` fixture export, and wait-timeout guards that prevent incomplete fixture/run/summary writes. This path made no real Ashr API calls.
- Local queue batch coverage now includes repeated `--run-id` creation, generated `--run-count` support, `batch_index`/`replay_order` metadata, deterministic replay ordering, per-run fixture/result directory exports, summary `run_ids`, `replay.status_histories`, batch quota accounting, and guards that keep singleton `--fixture-output` / `--run-output` paths blocked for multi-run replay. This path made no real Ashr API calls.
- TypeScript quickstart parity now covers local-only `AgentInput`, media request schema construction, `CloudApiService`, `QuotaLedger`, TS agent demo execution, fixture export, no-network checks, and redaction for token-like strings, `sk-...`, bearer values, emails, and signed query values.
- TypeScript hosted API-client parity now covers dry-run call plans, env-compatible constants, injected transport execution, session context injection, `keep_alive` / `list_agents`, media `createRequest` preflight summaries, mutation guardrails, retryable status handling, API-level error redaction, safe failed-request summary shapes, and a dry-run-first probe CLI that writes redacted JSON evidence while keeping stdout to summaries by default. No real Ashr API calls were made for the TS parity/probe CLI rounds.

## Next Candidates

1. Add a TypeScript local runner/adapter slice (`AgentAdapter`, `runAgentBatch`, `LocalEvalRunner`, and an `ashr-clone-runner` CLI) so TS begins matching Python SDK/Runner body, not only API probe parity.
2. Add optional TS injected-transport probe fixtures for API-level error and quota header shapes before any hosted TS execution.
3. Convert selected private hosted run evidence through the A2/A3 calibration import bridges into public-safe observations after explicit evidence-selection rules.
