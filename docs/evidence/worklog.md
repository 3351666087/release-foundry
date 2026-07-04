# A1 Worklog

## 2026-07-03 Round 1

Goal: build the local A1 SDK/Runner/Adapter/Trace loop without Ashr API calls, real keys, judge semantic edits, or dashboard business changes.

Start protocol: `origin` was missing, so it was added as `https://github.com/3351666087/ashr-codex-factory`; `origin/main` was fetched and checked out. Remote PR list returned no PRs; peer changes: none observed.

Implemented:

- `packages/sdk/ashr_clone`: adapter, serializable types, trace/replay/VM stream helpers.
- `services/runner`: generic batch runner, agent eval runner, deterministic JSON CLI.
- `examples/agents`: deterministic MockAgent, RespondingMockAgent, A3 fixtures.
- `tests/a1`: adapter, runner, and trace fixture coverage.

Verification:

- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `15 passed in 0.63s`.
- Runner CLI wrote `docs/a1/evidence/local_run_30.json` with 30 cases, 30 passed, `max_workers=4`, and trace completeness 1.0.
- `python -B examples\agents\mock_agent.py --write-fixtures examples\agents\fixtures` wrote three fixtures for A3.

Recovery note: a PowerShell cache cleanup pattern using recursive `-Include` deleted ordinary files in this environment. The repo was restored from `origin/main`, files were rebuilt, and that cleanup pattern must not be reused.

## 2026-07-03 Round 2 Follow-Up

Goal: answer whether Round 1 was genuinely complete; continue if gaps remain. A follow-up goal was created for A1 local SDK/Runner/Adapter/Trace closure and evidence hardening.

Start protocol:

- `git fetch origin`: success.
- `git status -sb`: branch `codex/a1-local-sdk-runner` tracking `origin/codex/a1-local-sdk-runner`.
- PR check: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`, merge state clean.
- Recent logs and final audit were read before changes.

Three proposed enhancements:

1. Gate-readiness hardening: official product evidence coverage, Runner stateful-agent isolation, failure-path tests, and A3 helper export polish.
2. Strict VM frame schema validation for every replay frame.
3. TypeScript SDK parity.

Implemented highest ROI enhancement: Gate-readiness hardening. Deferred strict VM frame validation and TypeScript parity.

Subagent findings:

- Bus-Auditor: implementation was largely complete, but evidence/audit handoff lagged branch/PR state.
- Explorer-Chrome/Product: public site accessibility passed, but product evidence coverage failed because pricing/usage, dashboard shell limits, API boundaries, and known gaps were not recorded.
- Explorer-SDK: field count passed; source grouping and top-level A3 fixture helper exports needed clearer evidence.
- Worker-Runner: core runner passed, but existing stateful agent instances could be shared across concurrent cases; mixed failure/CLI failure tests were weak.
- Worker-Trace: trace and fixture requirements passed; suggested stricter fixture/frame assertions as nonblocking.
- Worker-Adapter: basic wrapping passed but sync wrapping of async agents inside an existing event loop, non-callable `respond` attributes, and JSON-safe `AgentResult.to_dict()` needed hardening. Adapter-level timeout was noted, but timeout remains Runner-level because arbitrary sync agent code cannot be safely cancelled in-process.
- Reviewer: second-round contract review failed on missing agent-mode `RunResult` failure-path tests, missing agent CLI failure test, and missing deepcopy/shared-lock fallback coverage. These were fixed before final verification.

Implemented:

- `services/runner/runner.py`: added a per-case agent factory. Classes and string class targets instantiate per case; existing instances use `clone()` when available, then `copy.deepcopy()`, and only non-cloneable shared instances are serialized with a lock.
- `packages/sdk/ashr_clone/adapter.py`: hardened callable detection, event-loop-safe sync wrapping of awaitables, and JSON-safe `AgentResult.to_dict()`.
- `packages/sdk/ashr_clone/__init__.py`: exported `TraceEvent`, run fixture load/write/validate/build helpers, `stable_id`, and VM replay helpers at top level for A3.
- `tests/a1/test_adapter.py`: added event-loop sync/async wrapping, callable-with-non-callable-respond, and JSON-safe serialization coverage.
- `tests/a1/test_runner.py`: added generic and agent-mode mixed pass/fail/error/timeout accounting, CLI `--fail-on-case-failure` nonzero/output JSON checks for generic and agent paths, and stateful existing-agent clone/deepcopy/shared-lock coverage.
- `tests/a1/test_trace_fixture.py`: added committed fixture loading, `a3` label assertions, and top-level SDK fixture helper import coverage.
- `docs/a1/explorer_chrome.md`: added public homepage/docs/API/VM/TypeScript/Plans/dashboard-shell calibration, including Developer `$39/mo`, Startup `$500/mo`, and usage limits.
- `docs/evidence/official_site_gaps.md`: added explicit unverified dashboard, billing, API key, hosted grading, observability feature flag, and TypeScript runtime gaps.
- `docs/a1/explorer_sdk.md`, `docs/a1/sdk_field_map.md`, `docs/a1/README.md`, `docs/a1/reviewer_notes.md`, and `docs/a1/evidence/commands.md`: updated source notes, fresh setup, and follow-up verification.

Verification:

- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `9 passed in 0.07s`.
- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: `13 passed in 1.01s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `27 passed in 1.15s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `30 passed`, `0 failed`, `0 errors`, `0 timeouts`, trace `100.00%`.
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`: rewrote `echo_success.json`, `tool_math_success.json`, `recoverable_error.json`.
- Evidence summary: `total_cases=30`, `passed=30`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_vm_stream=30`.
- Cache cleanup: after listing `__pycache__`, removed only explicit literal paths under `packages/sdk/ashr_clone/__pycache__` and `services/runner/__pycache__` after workspace path verification.

Remaining:

- A2 `Scenario` / Judge / Golden adapter waits for Gate contract.
- A3 should confirm final `RunResult` / `Observation` / `GradeResult` schema expectations.
- Strict VM frame schema validation and TypeScript parity remain optional future enhancements.

## 2026-07-03 Round 3 Schema/Timeout Hardening

Goal: run a new A1 enhancement/review loop after Round 2, with official site recalibration, Bus-Auditor/role reviews, and one highest-ROI implementation.

Start protocol:

- `git fetch origin`: success.
- `git status -sb --untracked-files=all`: clean at start, branch `codex/a1-local-sdk-runner` tracking origin.
- PR check: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`.
- Peer changes: none observed; local and remote branch were synchronized at `074c510`.
- Recent worklog and previous top remaining items were read before implementation.

Three proposed enhancements:

1. A3 failure/schema hardening: timeout/error cases remain replayable, VM frames are strictly validated, AgentTurn has a stable schema version, and schema snapshots exist for A3/Gate review.
2. Strict RunResult golden snapshots across all-pass, mixed failure, and timeout runs.
3. TypeScript SDK parity.

Implemented highest ROI enhancement: A3 failure/schema hardening. TypeScript parity and final A2 Scenario/Judge/Golden adapter remain deferred.

Subagent findings:

- Bus-Auditor: initial repo/PR/tooling state passed; suggested updating stale final bus audit evidence.
- Explorer-Chrome/Product: public homepage/Python/TypeScript/monthly Plans records still accurate, but annual prices, unauthenticated `lab.ashr.io` onboarding shell, API key list/revoke docs, and VM stream signature needed evidence updates.
- Explorer-SDK: A3 helpers are usable, but lack of schema snapshots/strict validation was a contract risk.
- Worker-Adapter: `AgentResult.text`, non-JSON content extraction, direct `ToolCall.to_dict()`, and AgentTurn schema version needed hardening.
- Worker-Runner: agent timeout cases only had one system observation and no VM stream, lowering mixed-run trace completeness; 80-case regression and shared-lock active-count coverage were recommended.
- Worker-Trace: `validate_run_fixture` accepted malformed VM frames and `trace_events_from_vm_stream` treated unknown streams as lifecycle control.

Implemented:

- `packages/sdk/ashr_clone/adapter.py`: added `AGENT_TURN_SCHEMA_VERSION`, schema-versioned `AgentResult.to_dict()`, JSON-safe text/status/latency fields, and safe text extraction for non-JSON content.
- `packages/sdk/ashr_clone/types.py`: made direct dataclass `to_dict()` paths JSON-safe for mappings, tuples, sets, and non-JSON values.
- `services/runner/runner.py`: agent error/timeout cases now emit user + system observations, synthetic VM stream metadata, `agent_output.schema_version`, and `grade.actual.error`.
- `packages/sdk/ashr_clone/trace.py`: added strict VM frame shape/type/schema/sequence validation and event-frame consistency checks; unknown VM streams are rejected instead of silently replayed as lifecycle.
- `tests/a1`: added Adapter JSON/schema tests, 80-case runner regression, A3 timeout trace completeness assertions, shared-lock active-count assertion, schema snapshot tests, VM frame negative tests, and bad VM replay rejection.
- `docs/a1/schemas`: added local schema snapshots for `agent_turn`, `run_result`, `case_result`, `observation`, `grade_result`, `run_fixture`, `trace_event`, and `vm_stream_frame`.
- `docs/a1/explorer_chrome.md` and `docs/evidence/official_site_gaps.md`: updated annual pricing, unauthenticated dashboard/onboarding shell, API key list/revoke docs, and VM stream signature notes.

Verification:

- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `33 passed in 1.46s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `30 passed`, `0 failed`, `0 errors`, `0 timeouts`, trace `100.00%`.
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`: rewrote three A3 fixtures.
- Evidence summary: `total_cases=30`, `passed=30`, `trace_completeness=1.0`, `max_workers=4`, `agent_output.schema_version=ashr.clone.agent_turn.v1`.

Remaining:

- A2 final Scenario/Judge/Golden adapter waits for Gate contract.
- A3 should confirm final schema snapshots and optional-field behavior.
- Timeout still uses daemon threads and cannot safely cancel arbitrary sync agent code; stronger isolation would require process-level execution or a cancellable agent contract.
- TypeScript runtime parity remains optional future work.

## 2026-07-03 Round 4 Evidence Hygiene

Goal: verify whether the long-running A1 goal was actually complete, keep it active if not, and continue only on concrete gaps.

Start protocol:

- `git fetch origin`: success.
- `git status -sb`: clean at start, branch `codex/a1-local-sdk-runner` tracking origin.
- PR check: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks.
- Recent worklog, command evidence, and final bus audit were read before changes.
- Peer changes: none observed; local and remote branch were synchronized at `aa3c2fd`.

Three proposed enhancements:

1. Documentation/evidence hygiene for Gate handoff: correct stale audit state, field count, VM stream evidence wording, and current official-site notes.
2. SDK packaging metadata for fresh consumers that do not insert `packages/sdk` manually.
3. Process-level timeout isolation for arbitrary sync agents.

Implemented highest ROI enhancement: documentation/evidence hygiene, then reviewer-driven negative-timeout schema safety. Packaging metadata and process-level timeout isolation remain optional future work because current tests and fresh setup evidence pass inside the agreed local clone scope.

Subagent findings:

- Bus-Auditor: PASS for A1 protocol and completion criteria; requested a tiny docs-only cleanup for stale audit wording, field count, and observation-level VM stream evidence.
- Explorer-SDK: PASS; SDK field map count is 56, top-level A3 helpers and schema versions are exported, JSON-safe serialization is covered, and no Ashr API/key use was found in runtime/test code.
- Worker-Adapter: PASS; adapter tests and all A1 tests passed, including event-loop-safe wrapping and JSON-safe `AgentResult.to_dict()`.
- Worker-Runner: PASS; runner tests passed, including 80-case regression, `max_workers >= 4`, per-case isolation, CLI failure behavior, and timeout/error trace completeness.
- Worker-Trace: PASS; three committed A3 fixtures load and regenerate deterministically, VM frame validation is strict, and trace evidence is 30/30.
- Explorer-Chrome/Product: public homepage, Python docs, TypeScript docs, plans, API reference, authentication/API-key docs, testing docs, and VM integration docs were rechecked read-only. `lab.ashr.io` reached public Home/Docs/Blog links and a dashboard-like `Datasets`/loading shell only in this pass; earlier sign-in/onboarding plan-copy state was not reproduced, and no private dashboard fields were used.
- Reviewer: found P2 negative timeout schema risk. Negative timeout inputs could produce negative latency/duration fields that violate A3 schema snapshots; fixed in runner/CLI and covered with regression tests.

Verification:

- `python -B -m pytest tests/a1/test_runner.py -q -p no:cacheprovider`: `17 passed in 1.59s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `37 passed in 1.72s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `30 passed`, `0 failed`, `0 errors`, `0 timeouts`, trace `100.00%`.
- `python -B examples/agents/mock_agent.py --write-fixtures examples/agents/fixtures`: rewrote three A3 fixtures.
- Evidence summary: `total_cases=30`, `passed=30`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_observation_level_vm_stream=30`, `agent_output.schema_version=ashr.clone.agent_turn.v1`, `local_only=True`, `ashr_api_used=False`.

Implemented:

- `docs/a1/audit/final-bus-audit-2026-07-03.md`: corrected pushed commit/PR state, field count, and observation-level VM stream wording.
- `docs/a1/explorer_chrome.md`: added Round 4 read-only official-site calibration notes.
- `docs/evidence/official_site_gaps.md`: recorded that this pass saw only the lab loading shell and did not use authenticated dashboard/private data.
- `docs/a1/evidence/commands.md` and `docs/evidence/worklog.md`: recorded Round 4 commands, evidence summary, cache cleanup, and subagent findings.
- `services/runner/runner.py` and `services/runner/cli.py`: added non-negative timeout normalization so global negative timeouts fail fast and case-level negative timeouts become schema-safe error results.
- `tests/a1/test_runner.py`: added negative timeout regression tests and an emitted A3 RunResult schema guard.

Remaining:

- A2 final Scenario/Judge/Golden adapter waits for Gate contract.
- A3 should confirm final schema snapshots and optional-field behavior.
- Timeout still uses daemon threads and cannot safely cancel arbitrary sync agent code; stronger isolation would require process-level execution or a cancellable agent contract.
- TypeScript runtime parity and SDK packaging metadata remain optional future work.

## 2026-07-04 Subscription API Calibration Round 1

Goal: begin post-subscription A1 high-fidelity SDK/Runner calibration using the Ashr API through environment-only key handling, dry-run-first plans, private evidence, and small read-only real probes.

Start protocol:

- `git fetch origin`: success.
- `git status -sb --untracked-files=all --ignored`: started on `codex/a1-api-calibration`, then user requested the original branch; switched back to `codex/a1-local-sdk-runner` with self-made A1 changes preserved and deleted the temporary local branch.
- GitHub plugin PR check: PR #1 was closed/merged; user explicitly requested continuing on the original A1 branch anyway.
- Recent `docs/evidence/worklog.md`, `docs/a1/evidence/commands.md`, and A1 docs were read before implementation.
- Peer changes/impact: no new peer code pulled into the original branch this round. `origin/main` contains merged A1/A2/A3 integration, but this round intentionally stayed on `codex/a1-local-sdk-runner`.
- Secret handling: `.secrets/` is locally ignored via `.git/info/exclude`; `docs/evidence/private_refs/` is ignored by `docs/evidence/.gitignore`; key was loaded only into the PowerShell process for real calls and was not printed.

Three proposed enhancements:

1. Quota-safe API client wrapper and dry-run/record CLI for real `init/list/generate/deploy/poll` growth.
2. Immediate mutating `create-run` / `create-request` sample after dry-run.
3. TypeScript SDK parity.

Implemented highest ROI enhancement: quota-safe API client wrapper and dry-run/record CLI. Mutating calls remain gated behind `--execute --allow-mutate`; no mutating real API call was performed in this round.

Subagent findings:

- Bus-Auditor: flagged stale integration docs and secret staging risks. Main agent accepted the staging/secret warnings but did not downgrade the round to docs-only because the active user goal is post-subscription API calibration.
- Explorer-API: performed additional small real probes and confirmed `init`, `list_datasets`, `get_dataset`, `list_runs`, `list_requests`, plus HTTP 200 API-level error shape. Recommended dual env var support, response header capture, API error kind, and mutating double-confirmation; all were implemented.

Implemented:

- `packages/sdk/ashr_clone/api_client.py`: added `AshrApiClient`, dry-run plans, redacted records, dual env var support (`ASHR_API_KEY` and `ASHR_LABS_API_KEY`), optional `ASHR_LABS_BASE_URL`, session-context resolution, selected response header capture, retry handling, API-level error classification, and helper methods for `init`, list/get datasets/runs/requests, poll run/request, create request, and create run.
- `packages/sdk/ashr_clone/__init__.py`: exported API calibration client symbols.
- `services/runner/api_probe.py`: added dry-run-first CLI, real-call `--execute`, mutating `--allow-mutate`, private output defaults, and operation coverage for read/list/poll/create surfaces.
- `tests/a1/test_api_client.py`: added 14 tests for dry-run, injected transport execution, env vars, redaction, retry, API-level errors, polling, mutating plans, CLI gates, and string-level error redaction.
- `docs/a1/api_calibration/README.md`, `docs/a1/README.md`, `docs/a1/evidence/commands.md`, and this worklog: recorded non-sensitive field differences, commands, evidence paths, and next candidates.

Verification:

- `python -B -m pytest tests/a1/test_api_client.py -q -p no:cacheprovider`: `14 passed in 0.62s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `53 passed in 2.17s`.
- Dry-run plans written under ignored `docs/evidence/private_refs/`: `init`, `list-datasets`, `list-runs`, `list-requests`, `poll-run`, and `create-request`.
- Real read-only calls: `init`, `list-datasets`, `list-runs`, `list-requests`, `get-dataset` for one existing dataset, and invalid `get-dataset` for error-shape calibration. Successful calls were HTTP `200` / status `ok` / attempts `1`; invalid dataset produced HTTP `200` / `status=error` / `error_kind=api`.
- Chrome dashboard check reached logged-in `Ashr Labs` shell at `https://lab.ashr.io/?tab=analysis`; screenshot stored in ignored private evidence.

Remaining:

- Mutating `create-run` has not been exercised; it requires reviewing the dry-run plan and passing `--allow-mutate`.
- `create-request` generation remains dry-run only; quota/plan wording should be checked before any mutating generation call.
- Need second adapter mapping real `dataset_source.runs` into A1 local runner cases.
- Response headers did not include quota counters in the small successful calls, though the wrapper now captures `retry-after` and `x-ratelimit-*` if present.
- Bus-Auditor must-fix was resolved after initial review: error message strings now pass through `redact_text(...)` before being stored or raised, and tests verify token/email strings do not appear in records or exceptions. The follow-up repo-level ignore for `docs/evidence/private_refs/` was added in `docs/evidence/.gitignore`.

## 2026-07-03 Round 5 Completion Audit And A2 Projection Helper

Goal: perform a current-state completion audit after goal continuation, including peer remote impact, fresh local validation, and official public-site recalibration.

Start protocol:

- `git fetch origin`: success.
- `git status -sb --untracked-files=all`: clean at start, branch `codex/a1-local-sdk-runner` tracking origin.
- PR check: draft PR #1 open, base `main`, head `codex/a1-local-sdk-runner`, mergeable, no status checks, head `3617fd2`.
- Recent worklog, command evidence, final bus audit, and A2 peer handoff docs were read before implementation.
- Peer changes/impact: `origin/dev/a2-scenario-judge` adds local A2 judge docs and fixtures. Its handoff doc expects `tool_calls` plus `final_response`; A1 already has `agent_output.text` and `agent_output.tool_calls`, but not a zero-transform export shape.

Three proposed enhancements:

1. A2 local judge projection helper: project A1 `AgentTurn` / `agent_output` into `final_response` and normalized `tool_calls[].tool` / `tool_calls[].args`.
2. SDK packaging metadata for fresh consumers that do not insert `packages/sdk` manually.
3. Process-level timeout isolation for arbitrary sync agents.

Implemented highest ROI enhancement: A2 local judge projection helper. Packaging metadata and process-level timeout isolation remain optional future work.

Subagent findings:

- Bus-Auditor: initial read-only audit passed the local A1 loop at `3617fd2` and identified A2 handoff mapping as nonblocking but useful before integration.
- Explorer-SDK: PASS; A2 handoff is not a blocker because A2 accepts `name`/`arguments`, but adding a tiny tested mapper was the highest ROI follow-up.
- Explorer-Chrome/Product: public homepage, Python/TypeScript docs, plans, API reference, auth/API-key docs, testing docs, and VM integration docs remain reachable. Lab shell varied between `Datasets` loading and unauthenticated sign-in/onboarding; no authenticated/private data was used.
- Worker-Adapter: PASS; adapter tests and all A1 tests passed before the helper. The helper was added in the adapter module and exported top-level.
- Worker-Runner: PASS; runner tests and all A1 tests passed, including negative-timeout schema safety.
- Worker-Trace: PASS; three committed A3 fixtures, strict frame validation, schema snapshots, and trace evidence all passed.

Implemented:

- `packages/sdk/ashr_clone/adapter.py`: added `to_a2_judge_run(...)` plus normalized A2 tool-call projection.
- `packages/sdk/ashr_clone/__init__.py`: exported `to_a2_judge_run` at top level.
- `tests/a1/test_adapter.py`: covered projection from `AgentResult` and raw `agent_output` mappings, including JSON safety and `tool`/`args` plus preserved `name`/`arguments`.
- `docs/a1/README.md`, `docs/a1/reviewer_notes.md`, `docs/a1/evidence/commands.md`, `docs/a1/explorer_chrome.md`, `docs/a1/audit/final-bus-audit-2026-07-03.md`, `docs/evidence/official_site_gaps.md`, and this worklog were updated with Round 5 evidence.

Verification:

- `python -B -m pytest tests/a1/test_adapter.py -q -p no:cacheprovider`: `14 passed in 0.09s`.
- `python -B -m pytest tests/a1 -q -p no:cacheprovider`: `39 passed in 1.48s`.
- `python -B -m services.runner.cli --input docs/a1/evidence/local_agent_cases_30.json --output docs/a1/evidence/local_run_30.audit.json --agent examples.agents.mock_agent:RespondingMockAgent --dataset-id a2-local-scenarios --runner-id a1-local-runner --max-workers 4 --timeout 5 --fail-on-case-failure`: `30 passed`, `0 failed`, `0 errors`, `0 timeouts`, trace `100.00%`.
- Temporary audit output summary: `total_cases=30`, `passed=30`, `trace_completeness=1.0`, `max_workers=4`, `cases_with_observations=30`, `cases_with_observation_level_vm_stream=30`, `agent_output.schema_version=ashr.clone.agent_turn.v1`, `local_only=True`, `ashr_api_used=False`.

Remaining:

- A2 final Scenario/Judge/Golden adapter waits for Gate contract.
- A3 should confirm final schema snapshots and optional-field behavior.
- Timeout still uses daemon threads and cannot safely cancel arbitrary sync agent code; stronger isolation would require process-level execution or a cancellable agent contract.
- TypeScript runtime parity and SDK packaging metadata remain optional future work.
