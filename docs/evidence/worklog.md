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
