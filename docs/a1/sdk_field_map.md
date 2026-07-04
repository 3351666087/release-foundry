# A1 SDK Field Map

Confirmed public/docs/PyPI field names used for local clone shape: `AshrLabsClient`, `from_env`, `ASHR_LABS_API_KEY`, `ASHR_LABS_BASE_URL`, `api_key`, `base_url`, `timeout`, `init`, `Session`, `user.id`, `user.email`, `tenant.id`, `tenant.tenant_name`, `get_dataset`, `dataset_id`, `list_datasets`, `create_request`, `request_name`, `request_input_schema`, `create_run`, `get_run`, `list_runs`, `delete_run`, `Run`, `result`, `status`, `score`, `metrics`, `EvalRunner`, `EvalRunner.from_dataset`, `EvalRunner.run`, `EvalRunner.run_and_deploy`, `max_workers`, `RunBuilder`, `TestBuilder`, `set_vm_stream`, `Agent.respond`, `Agent.reset`, `text`, `tool_calls`, `name`, `arguments`, `arguments_json`, `expected`, `actual`, `match_status`, `client.trace`, `Trace`, `Span`, `Generation`, `observations`, `parent_observation_id`, `start_time`, `end_time`, `provider`, `session_id`, `duration_ms`, `logs`, `metadata`.

Source groups:

- Public docs/API reference: client/auth/session, dataset/run, EvalRunner, Agent protocol, VM stream, and observability naming.
- Public Plans page: plan/usage fields were calibrated for evidence only and are not part of the local runner schema.
- PyPI wheel/sdist under `docs/a1/_pypi_artifacts`: retained as evidence only, not imported by runtime code.
- Local A1 clone: `AgentAdapter`, `LocalEvalRunner`, `TraceRecorder`, `MockAgent`, `RunResult`, `Observation`, and `GradeResult` are local-only and do not call hosted Ashr services.

Top-level local SDK exports now include `TraceEvent`, `build_run_fixture`, `load_run_fixture`, `write_run_fixture`, `validate_run_fixture`, and `trace_events_from_vm_stream` so A3 can import fixture helpers without depending on internal module paths.

Dataset source adapter exports now include `DATASET_SOURCE_ADAPTER_VERSION`, `cases_from_dataset_source`, `case_from_source_run`, and `replay_fixture_from_source_run`. The adapter maps observed `dataset_source.runs` shapes into existing A1 runner cases and strict A3 replay fixtures without changing Gate contracts.

## 2026-07-04 API Calibration Addendum

Post-subscription A1 probes confirmed these additional real API fields without committing raw responses:

- `init`: `features`, `notes`, `status`, `tenant`, `user`.
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
- Request item: `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `request`, `request_name`, `request_status`, `requestor_details`, `requestor_id`, `requestor_tenant`.
- `create_request` request: `request_name`, `request`, `request_input_schema`, `tenant_id`, `requestor_id`.
- Default request input schema: `type`, `additionalProperties`, and optional `tools`.
- Local create-request preflight record: `num_variations`, `num_variations_known`, `media_generation`, `media_generation_enabled`, `accepted_input_flags`, `non_text_inputs_enabled`, `small_batch`, `request_input_schema_source`, `notes`.
- Media interface flags: `generate_images`, `generate_audio`, `generate_files`, `generate_videos`, `generate_simulations`, plus accepted input flags for `image`, `audio`, `file`, `video`, `conversation`, and `text`.

Error calibration:

- API-level errors can be HTTP `200` with body `status: error`; local records label this as `error_kind: api`.
- Rate-limit and retry headers were not present in the small successful calls, but the wrapper captures `retry-after` and `x-ratelimit-*` when returned.
