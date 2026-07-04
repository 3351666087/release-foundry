# A1 SDK Field Map

Confirmed public/docs/PyPI field names used for local clone shape: `AshrLabsClient`, `from_env`, `ASHR_LABS_API_KEY`, `ASHR_LABS_BASE_URL`, `api_key`, `base_url`, `timeout`, `init`, `Session`, `user.id`, `user.email`, `tenant.id`, `tenant.tenant_name`, `get_dataset`, `dataset_id`, `list_datasets`, `create_run`, `get_run`, `list_runs`, `delete_run`, `Run`, `result`, `status`, `score`, `metrics`, `EvalRunner`, `EvalRunner.from_dataset`, `EvalRunner.run`, `EvalRunner.run_and_deploy`, `max_workers`, `RunBuilder`, `TestBuilder`, `set_vm_stream`, `Agent.respond`, `Agent.reset`, `text`, `tool_calls`, `name`, `arguments`, `arguments_json`, `expected`, `actual`, `match_status`, `client.trace`, `Trace`, `Span`, `Generation`, `observations`, `parent_observation_id`, `start_time`, `end_time`, `provider`, `session_id`, `duration_ms`, `logs`, `metadata`.

Source groups:

- Public docs/API reference: client/auth/session, dataset/run, EvalRunner, Agent protocol, VM stream, and observability naming.
- Public Plans page: plan/usage fields were calibrated for evidence only and are not part of the local runner schema.
- PyPI wheel/sdist under `docs/a1/_pypi_artifacts`: retained as evidence only, not imported by runtime code.
- Local A1 clone: `AgentAdapter`, `LocalEvalRunner`, `TraceRecorder`, `MockAgent`, `RunResult`, `Observation`, and `GradeResult` are local-only and do not call hosted Ashr services.

Top-level local SDK exports now include `TraceEvent`, `build_run_fixture`, `load_run_fixture`, `write_run_fixture`, `validate_run_fixture`, and `trace_events_from_vm_stream` so A3 can import fixture helpers without depending on internal module paths.

## 2026-07-04 API Calibration Addendum

Post-subscription A1 probes confirmed these additional real API fields without committing raw responses:

- `init`: `features`, `notes`, `status`, `tenant`, `user`.
- `user`: `created_at`, `email`, `id`, `is_active`, `is_owner`, `name`, `tenant_id`.
- `tenant`: `created_at`, `id`, `is_active`, `owner_email`, `plan`, `signup_method`, `tenant_name`.
- `list_datasets`: `_user`, `datasets`, `next_cursor`, `status`.
- Dataset item: `agent_details`, `agent_id`, `created_at`, `creator`, `creator_details`, `dataset_source`, `dataset_type`, `description`, `id`, `name`, `repo_id`, `request_id`, `run_count`, `tenant`.
- `dataset_source`: `dataset_type`, `runs`, `total_runs`.
- Source run item: `run_id`, `title`, `description`, `intent`, `intent_tags`, `audio_tags`, `simulation`, `actions`.
- `list_runs`: `_user`, `runs`, `status`.
- Run item: `created_at`, `dataset`, `dataset_details`, `id`, `result`, `runner`, `runner_details`, `tenant`.
- `list_requests`: `_user`, `next_cursor`, `requests`, `status`.
- Request item: `actual_duration_s`, `completed_at`, `created_at`, `estimated_duration_s`, `id`, `request`, `request_name`, `request_status`, `requestor_details`, `requestor_id`, `requestor_tenant`.

Error calibration:

- API-level errors can be HTTP `200` with body `status: error`; local records label this as `error_kind: api`.
- Rate-limit and retry headers were not present in the small successful calls, but the wrapper captures `retry-after` and `x-ratelimit-*` when returned.
