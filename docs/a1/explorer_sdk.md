# Explorer SDK Map

Public `ashr-labs` package evidence was inspected without API calls or keys. Key public surfaces: `AshrLabsClient`, `EvalRunner`, `RunBuilder`, `TestBuilder`, `Agent.respond/reset`, `tool_calls`, `arguments`, `arguments_json`, VM stream helpers, and observability trace naming.

The downloaded upstream artifacts under `docs/a1/_pypi_artifacts/` are evidence only, not vendored implementation.

## Evidence Sources

- Public docs: Python SDK overview, testing-your-agent, VM integration, API reference, and TypeScript SDK overview were checked read-only on 2026-07-03.
- PyPI artifacts: `docs/a1/_pypi_artifacts/ashr_labs-0.3.1-py3-none-any.whl` and `docs/a1/_pypi_artifacts/ashr_labs-0.3.1.tar.gz` were retained as evidence only.
- Runtime import path: A1 code inserts `packages/sdk` into `sys.path`; it does not add `_pypi_artifacts` to the runtime path.
- Local clone exports: `ashr_clone.__all__` exposes adapter/result types plus TraceEvent and fixture/replay helpers for A3 consumption.
- Local schema snapshots: `docs/a1/schemas` records AgentTurn, RunResult, run fixture, trace event, and VM stream frame shapes for A3/Gate review.

## Field Source Groups

- Client/auth fields came from public docs/API reference and package metadata: `AshrLabsClient`, `from_env`, `ASHR_LABS_API_KEY`, `ASHR_LABS_BASE_URL`, `api_key`, `base_url`, `timeout`, `init`, `Session`, tenant/user fields.
- Dataset/run fields came from public docs/API reference and upstream package artifact names: `get_dataset`, `list_datasets`, `create_run`, `get_run`, `list_runs`, `delete_run`, `Run`, `result`, `status`, `score`, `metrics`.
- Runner/agent fields came from public testing docs: `EvalRunner`, `EvalRunner.from_dataset`, `EvalRunner.run`, `EvalRunner.run_and_deploy`, `max_workers`, `Agent.respond`, `Agent.reset`, `text`, `tool_calls`, `name`, `arguments`, `arguments_json`.
- VM/trace fields came from public VM integration and API reference docs: `set_vm_stream`, `client.trace`, `Trace`, `Span`, `Generation`, `observations`, `parent_observation_id`, `start_time`, `end_time`, `provider`, `session_id`, `duration_ms`, `logs`, `metadata`.

## Remaining SDK Gaps

- A2 final Scenario/Judge/Golden adapter remains deferred until Gate contract.
- TypeScript SDK parity is not implemented in A1; only docs were calibrated.
- There is no package installer metadata yet; fresh setup currently runs from the repository root with `packages/sdk` on `sys.path`.
- AgentTurn now emits `schema_version: ashr.clone.agent_turn.v1`; RunResult continues to expose the run contract version in `aggregate_metrics.schema_version`.
