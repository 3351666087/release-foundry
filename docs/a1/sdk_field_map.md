# A1 SDK Field Map

Confirmed public/docs/PyPI field names used for local clone shape: `AshrLabsClient`, `from_env`, `ASHR_LABS_API_KEY`, `ASHR_LABS_BASE_URL`, `api_key`, `base_url`, `timeout`, `init`, `health_check`, `keep_alive`, `list_agents`, `agents`, `Session`, `user.id`, `user.email`, `tenant.id`, `tenant.tenant_name`, `get_dataset`, `dataset_id`, `list_datasets`, `create_request`, `request_name`, `request_input_schema`, `properties`, `$defs`, `agent_input_part`, `create_run`, `get_run`, `list_runs`, `delete_run`, `Run`, `result`, `status`, `score`, `metrics`, `EvalRunner`, `EvalRunner.from_dataset`, `EvalRunner.run`, `EvalRunner.run_and_deploy`, `max_workers`, `RunBuilder`, `TestBuilder`, `set_vm_stream`, `Agent.respond`, `Agent.reset`, `AgentInput`, `schema_version`, `text`, `parts`, `image`, `audio`, `file`, `path`, `url`, `source`, `mime_type`, `name`, `tool_calls`, `arguments`, `arguments_json`, `expected`, `actual`, `match_status`, `client.trace`, `Trace`, `Span`, `Generation`, `observations`, `parent_observation_id`, `start_time`, `end_time`, `provider`, `session_id`, `duration_ms`, `logs`, `metadata`, `CloudApiService`, `CloudQueueWorker`, `QueueRunRequest`, `tenant_id`, `project_id`, `request_id`, `run_id`, `run_ids`, `case_count`, `result_status`, `status_history`, `queued`, `running`, `completed`, `failed`, `cancelled`, `quota`, `limits`, `used`, `remaining`, `operation`, `units`, `local_cloud_state`, `state_version`, `snapshot_state`, `write_state`, `from_state_file`, `replay_incomplete_runs`, `queue-run`, `replay-queued`, `export-fixture`, `batch_index`, `batch_size`, `replay_order`, `fixtures`, `run_results`, `ashr-clone-probe`, `ashr-clone-api-probe`, `--execute`, `--allow-mutate`, `--print-record`, `--output`, `--run-count`, `--fixture-output-dir`, and `--run-output-dir`.

Source groups:

- Public docs/API reference: client/auth/session, dataset/run, EvalRunner, Agent protocol, VM stream, and observability naming.
- Public Plans page: plan/usage fields were calibrated for evidence only and are not part of the local runner schema.
- PyPI wheel/sdist under `docs/a1/_pypi_artifacts`: retained as evidence only, not imported by runtime code.
- Local A1 clone: `AgentAdapter`, `AgentInput`, `LocalEvalRunner`, `TraceRecorder`, `MockAgent`, `RunResult`, `Observation`, and `GradeResult` are local-only and do not call hosted Ashr services.
- Local A1 cloud runtime: `CloudApiService`, `InMemoryCloudStore`, and `QuotaLedger` are local-only scaffolds for tenant/project isolation, dataset import, request records, run submission/polling, fixture export, and quota checks. They do not call hosted Ashr services and are not Gate contract changes.
- Local TypeScript parity: `packages/ts/ashr-clone` mirrors the local-only `AgentInput`, `AgentTurn`, `RunResult`, default request schema, cloud runtime, quota, redaction, TS agent demo, fixture export surfaces, and a dry-run-first API probe CLI. It also exposes a dry-run-first, transport-injected hosted API client that does not call network or require keys unless `dryRun: false` is explicitly requested.

Top-level local SDK exports now include `AgentInput`, `AGENT_INPUT_SCHEMA_VERSION`, `TraceEvent`, `build_run_fixture`, `load_run_fixture`, `write_run_fixture`, `validate_run_fixture`, and `trace_events_from_vm_stream` so A3 can import fixture helpers without depending on internal module paths.

Adapter input envelope exports now include `AgentInput`, `coerce_agent_input`, `respond_input`, `arespond_input`, `run_input_turn`, and `arun_input_turn`. The envelope schema is `ashr.clone.agent_input.v1` and supports `parts` with `type` values `text`, `image`, `audio`, and `file`. Legacy `AgentAdapter.respond("text")` remains string-first.

Dataset source adapter exports now include `DATASET_SOURCE_ADAPTER_VERSION`, `cases_from_dataset_source`, `case_from_source_run`, and `replay_fixture_from_source_run`. The adapter maps observed `dataset_source.runs` shapes into existing A1 runner cases and strict A3 replay fixtures without changing Gate contracts.

Local cloud API exports now include `CLOUD_API_SCHEMA_VERSION`, `CloudApiService`, `CloudQueueWorker`, `QueueRunRequest`, `InMemoryCloudStore`, `QuotaLedger`, `CloudApiError`, `ValidationError`, `NotFoundError`, `QuotaExceededError`, `run_agent_cloud_demo`, `run_agent_cloud_queue_demo`, `create_agent_cloud_queue_state`, `replay_agent_cloud_queue_state`, and `export_run_fixture_from_state`. Current local record fields include `tenant_id`, `project_id`, `dataset_id`, `request_id`, `run_id`, `status`, `result_status`, `status_history`, `request_input_schema`, `accepted_inputs`, `observations`, `result`, `limits`, `used`, and `remaining`. State snapshot payloads emit `kind=local_cloud_state`, `state_version`, `store`, `quota`, and local-only metadata. The local CLI surfaces are `python -m services.api.cli run-agent`, `run-agent-queued`, `queue-run`, `replay-queued`, and `export-fixture`; queued summaries additionally emit `queue.queued_status`, `queue.queue_workers`, `queue.runner_max_workers`, `queue.status_history`, `queue.run_ids`, and `queue.batch_size`, while replay summaries emit `replay.replayed`, `replay.completed`, per-run `replay.status_histories`, restored-state output paths, and optional `outputs.fixtures` / `outputs.run_results` maps for batch replay.

TypeScript package exports now include `AGENT_INPUT_SCHEMA_VERSION`, `AGENT_TURN_SCHEMA_VERSION`, `RUN_RESULT_SCHEMA_VERSION`, `CLOUD_API_SCHEMA_VERSION`, `AgentInput`, `AgentTurn`, `RunResult`, `CloudApiService`, `InMemoryCloudStore`, `QuotaLedger`, `buildDefaultRequestInputSchema`, `runAgentCloudDemo`, `coerceAgentInput`, `agentInputFromText`, `agentInputFromParts`, `redactText`, and `redactSensitive`. Hosted API parity exports now include `AshrApiClient`, `AshrApiError`, `MissingAshrApiKeyError`, `AshrApiCallPlan`, `AshrApiCallRecord`, `AshrApiTransport`, `ASHR_DEFAULT_BASE_URL`, `ASHR_API_ENV_VAR`, `ASHR_LABS_API_ENV_VAR`, `ASHR_LABS_BASE_URL_ENV_VAR`, `ASHR_API_FIELD_MAP_VERSION`, `summarizeGenerationRequest`, `enforceCreateRequestPreflight`, `redactApiText`, and `redactApiSensitive`. TypeScript CLI parity now includes `packages/ts/ashr-clone/src/probe.ts`, built as `dist/probe.js` and exposed as `ashr-clone-probe` / `ashr-clone-api-probe`; it writes probe records to ignored private evidence by default and prints only one-line summaries unless `--print-record` is used.

## 2026-07-04 API Calibration Addendum

Post-subscription A1 probes confirmed these additional real API fields without committing raw responses:

- `init`: `features`, `notes`, `status`, `tenant`, `user`.
- `health_check`: official SDK method name; underlying API function `keep_alive`; real response keys `db`, `message`, `status`.
- `list_agents`: real response keys `_user`, `agents`, `status`; current private account returned `agents` as an empty list.
- `user`: `created_at`, `email`, `id`, `is_active`, `is_owner`, `name`, `tenant_id`.
- `tenant`: `created_at`, `id`, `is_active`, `owner_email`, `plan`, `signup_method`, `tenant_name`.
- `list_datasets`: `_user`, `datasets`, `next_cursor`, `status`.
- Dataset item: `agent_details`, `agent_id`, `created_at`, `creator`, `creator_details`, `dataset_source`, `dataset_type`, `description`, `id`, `name`, `repo_id`, `request_id`, `run_count`, `tenant`.
- `dataset_source`: `dataset_type`, `runs`, `total_runs`.
- Source run item: `run_id`, `title`, `description`, `intent`, `intent_tags`, `audio_tags`, `simulation`, `actions`.
- Source action item: `actor`, `content`, `name`, `action_type`, `output_path`, `expected_response`, `action_tags`.
- Source expected response: `tool_calls`; observed as either object or list and normalized to local `{name, arguments}` calls.
- `list_runs`: `_user`, `runs`, `status`.
- Run item: `created_at`, `dataset`, `dataset_details`, `id`, `result`, `runner`, `runner_details`, `tenant`.
- `create_run` / `get_run` response: `_user`, `run`, `status`.
- Created run item: `created_at`, `dataset`, `id`, `result`, `runner`, `tenant`.
- Hosted run result: `aggregate_metrics`, `cases`, `dataset_id`, `duration_ms`, `ended_at`, `errored`, `failed`, `field_map_version`, `max_workers`, `metadata`, `passed`, `run_id`, `runner_id`, `started_at`, `status`, `timed_out`, `total_cases`, `trace_completeness`.
- `list_requests`: `_user`, `next_cursor`, `requests`, `status`.
- Request item: `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `prompt_version_id`, `request`, `request_input_schema`, `request_name`, `request_status`, `requestor_details`, `requestor_id`, `requestor_tenant`.
- `create_request` request: `request_name`, `request`, `request_input_schema`, `tenant_id`, `requestor_id`.
- Default request input schema: `type`, `additionalProperties`, and optional `tools`.
- Default request input schema for media accepted inputs: optional `properties.schema_version`, `properties.text`, `properties.parts`, `properties.metadata`, and `$defs.agent_input_part`; this mirrors the local `AgentInput` envelope while keeping `additionalProperties=true` and matching part types to enabled accepted inputs.
- Request config media source paths: `request.agent.accepted_inputs.{text,audio,file,image,video,conversation}` and `request.generation_options.{generate_audio,generate_files,generate_images,generate_videos,generate_simulations}`.
- Local create-request preflight record: `num_variations`, `num_variations_known`, `media_generation`, `media_generation_enabled`, `accepted_inputs_known`, `accepted_input_flags`, `agent_input_part_types`, `agent_input_schema_version`, `non_text_inputs_enabled`, `small_batch`, `request_input_schema_source`, `notes`.
- Local create-request record params are summary-shaped before evidence writing: `request.top_level_keys`, `request.agent_keys`, `request.tools_count`, `request.accepted_input_flags`, `request.generation_options`, `request.metadata_keys`, `request.test_config_keys`, `request.num_variations`, and `request_input_schema.{keys,type,additionalProperties,tools_count,property_keys,defs_keys,agent_input_schema_version,agent_input_part_types}`.
- Media interface flags: `generate_images`, `generate_audio`, `generate_files`, `generate_videos`, `generate_simulations`, plus accepted input flags for `image`, `audio`, `file`, `video`, `conversation`, and `text`.
- Local AgentInput envelope: `schema_version`, `text`, `parts`, `metadata`; part fields include `type`, `text`, `path`, `url`, `source`, `mime_type`, `name`, and `description`.
- Local hosted request failure summary: `response_summary.request_failure.request_status`, `top_level_failure_like_keys`, `nested_request_keys`, and `failure_sources.request._failure.{type,present,keys,fields}`. Field shapes include only `type`, `present`, `length`, `count`, `item_types`, and nested `keys`; raw hosted failure values stay out of tracked docs.

Error calibration:

- API-level errors can be HTTP `200` with body `status: error`; local records label this as `error_kind: api`.
- Hosted request generation can end with `request_status: failed` after an accepted `create_request`; local `get-request` and `poll-request` records capture safe nested failure-shape summaries without retrying creation.
- Hosted request quota errors can also arrive as HTTP `200` / `status: error`; one real text-batch probe returned a request usage limit message after local preflight passed.
- Rate-limit and retry headers were not present in the small successful calls, but the wrapper captures `retry-after` and `x-ratelimit-*` when returned.
