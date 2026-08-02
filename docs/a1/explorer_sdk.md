# Explorer SDK Map

The local `releasefoundry` SDK is inspected without API calls or keys. Key public surfaces include `ReleaseFoundryClient`, `EvalRunner`, `RunBuilder`, `TestBuilder`, `Agent.respond/reset`, `tool_calls`, `arguments`, `arguments_json`, VM stream helpers, and observability trace naming.

## Evidence Sources

- Public docs: Python SDK overview, testing-your-agent, VM integration, API reference, and TypeScript SDK overview were checked read-only on 2026-07-03.
- Public API reference was rechecked read-only on 2026-07-04 for `request_input_schema`, `accepted_inputs`, media generation flags, and `TestBuilder.add_user_file(file_path, description, action_index)`.
- SDK source: `packages/sdk/releasefoundry` is the authoritative Python implementation; no third-party package archives are vendored.
- Runtime import path: repository tools insert `packages/sdk` into `sys.path` when the package is not installed.
- Local clone exports: `releasefoundry.__all__` exposes adapter/result types, the `AgentInput` envelope, TraceEvent, and fixture/replay helpers for A3 consumption.
- Local schema snapshots: `docs/a1/schemas` records AgentInput, AgentTurn, RunResult, run fixture, trace event, and VM stream frame shapes for A3/Gate review.

## Field Source Groups

- Client/auth fields came from public docs/API reference and package metadata: `ReleaseFoundryClient`, `from_env`, `RELEASEFOUNDRY_API_KEY`, `RELEASEFOUNDRY_BASE_URL`, `api_key`, `base_url`, `timeout`, `init`, `Session`, tenant/user fields.
- Dataset/run fields came from public docs/API reference and upstream package artifact names: `get_dataset`, `list_datasets`, `create_run`, `get_run`, `list_runs`, `delete_run`, `Run`, `result`, `status`, `score`, `metrics`.
- Runner/agent fields came from public testing docs: `EvalRunner`, `EvalRunner.from_dataset`, `EvalRunner.run`, `EvalRunner.run_and_deploy`, `max_workers`, `Agent.respond`, `Agent.reset`, `text`, `tool_calls`, `name`, `arguments`, `arguments_json`. Local A1 now adds `AgentInput` as a canonical clone envelope for future Image/Audio/Files inputs while preserving the upstream text-first `Agent.respond(content)` protocol.
- Request/media fields came from public API reference docs: `request_input_schema`, `accepted_inputs`, `generate_audio`, `generate_files`, `generate_images`, `generate_videos`, `generate_simulations`, `add_user_file`, `file_path`, `description`, and `action_index`.
- VM/trace fields came from public VM integration and API reference docs: `set_vm_stream`, `client.trace`, `Trace`, `Span`, `Generation`, `observations`, `parent_observation_id`, `start_time`, `end_time`, `provider`, `session_id`, `duration_ms`, `logs`, `metadata`.

## Remaining SDK Gaps

- A2 final Scenario/Judge/Golden adapter remains deferred until Gate contract.
- TypeScript SDK parity is implemented locally in `packages/ts/releasefoundry`, including `AgentInput`, local cloud runtime/quota helpers, hosted dry-run `ReleaseFoundryApiClient`, and a dry-run-first probe CLI. Hosted TypeScript execution remains unverified unless run through the env-only, dry-run-first probe flow.
- There is no package installer metadata yet; fresh setup currently runs from the repository root with `packages/sdk` on `sys.path`.
- AgentTurn now emits `schema_version: releasefoundry.agent_turn.v1`; RunResult continues to expose the run contract version in `aggregate_metrics.schema_version`.
- AgentInput now emits `schema_version: releasefoundry.agent_input.v1`; the local default `request_input_schema` advertises the AgentInput `parts` envelope for Image/Audio/Files accepted inputs. Hosted media failure-detail calibration remains a follow-up because the first real Image/Audio/Files request was accepted but later failed server-side.
