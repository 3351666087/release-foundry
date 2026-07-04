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
- `list-datasets`
- `get-dataset`
- `list-runs`
- `get-run`
- `poll-run`
- `list-requests`
- `get-request`
- `poll-request`
- `create-request`
- `create-run`

The client follows the observed official Python SDK shape: one POST endpoint at `https://api.ashr.io/testing-platform-api` dispatches by a `function` field. List/create operations that need tenant or user context resolve session through `init` before the target function when executing real calls.

## Real Read-Only Calibration

Private evidence files:

- `docs/evidence/private_refs/a1_api_init_real_v2.json`
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
- `docs/evidence/private_refs/a1_real_dataset_cases.json`
- `docs/evidence/private_refs/a1_real_dataset_run_mock.json`
- `docs/evidence/private_refs/ashr_lab_analysis_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_analysis_create_run_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_analysis_request_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_usage_next_round_2026-07-04.png`
- `docs/evidence/private_refs/ashr_lab_usage_request_round_2026-07-04.png`

Observed non-sensitive field keys:

- `init` response keys: `features`, `notes`, `status`, `tenant`, `user`.
- `init.user` keys: `created_at`, `email`, `id`, `is_active`, `is_owner`, `name`, `tenant_id`.
- `init.tenant` keys: `created_at`, `id`, `is_active`, `owner_email`, `plan`, `signup_method`, `tenant_name`.
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
- CLI dry-run preflight records `request_input_schema_source=client_default`

The tiny generation config at `docs/a1/api_calibration/tiny_generation_request.json` is text-only and bounded to one variation. The dry-run record now includes a local preflight summary:

- `num_variations=1`
- `num_variations_known=true`
- `small_batch=true`
- accepted inputs: text only; `non_text_inputs_enabled=false`
- media generation: audio/files/images/videos/simulations all disabled
- `mutates=true`, `estimated_calls=2`, `attempts=0`

Image/Audio/Files interface coverage now has a committed dry-run-first fixture at `docs/a1/api_calibration/media_interface_request.json`:

- accepted inputs include text, image, audio, and file
- `generate_images=true`, `generate_audio=true`, `generate_files=true`
- videos/simulations remain false
- `num_variations=1`
- dry-run only; real execution is blocked by default because both `media_generation_enabled` and `non_text_inputs_enabled` are true

Real request calibration after the default schema patch:

- Text-only tiny request with `num_variations=1` succeeded: `create-request` returned `status=ok`, HTTP `200`, `attempts=1`, response keys `_user`, `request`, `status`.
- Follow-up `get-request` returned `request_status=processing`, then bounded `poll-request` returned `request_status=completed` with `status=ok`, HTTP `200`, `attempts=1`.
- The completed request shape includes `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `prompt_version_id`, `request`, `request_input_schema`, `request_name`, `request_status`, `requestor_id`, and `requestor_tenant`.
- One real Image/Audio/Files interface request was submitted after a fresh Usage page review and explicit `--allow-media-generation --allow-non-text-inputs`; it returned `create-request status=ok`, then `get-request request_status=failed`. Bounded `poll-request` recorded an error summary with HTTP `200`, `attempts=1`, and message `request failed`.
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

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: 37 passed.
- `python -B -m pytest tests/a1/test_runner.py tests/a1/test_dataset_adapter.py -q -p no:cacheprovider`: 26 passed.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: 85 passed.
- Real read-only probes executed: `init`, `list-datasets`, `list-runs`, `list-requests`, `get-dataset` for one existing dataset, and negative `get-dataset` for an invalid dataset.
- Real mutating probes executed: one `create-run` against an existing private dataset; one successful text-only `create-request`; one accepted Image/Audio/Files `create-request` that later reached hosted `request_status=failed`; one blocked text-batch `create-request` that returned hosted request quota exhaustion.
- Real read-only follow-up probes executed against the created run/request resources: `get-run`, fixed `poll-run`, `get-request`, `poll-request`, post-media `list-requests`, and post-request `list-datasets`.
- Chrome dashboard check reached logged-in `Ashr Labs` at `https://lab.ashr.io/?tab=analysis`; visible shell hints included `Datasets` and `Runs`.
- Error string redaction is covered at the text level: token-like values, bearer tokens, and email addresses are replaced before records or exception text are emitted.

## Next Candidates

1. Add a canonical multimodal `AgentInput` envelope to `AgentAdapter` so future Image/Audio/Files inputs can be wrapped consistently while preserving legacy text behavior.
2. Inspect/adjust the media request schema or official UI/docs before repeating media generation; the first real media request was accepted but hosted processing failed.
3. Continue read/list/get/poll calibration and runner replay until request generation quota resets or plan changes.
